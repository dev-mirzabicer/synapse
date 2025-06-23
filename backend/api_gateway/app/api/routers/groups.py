import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload # Added for eager loading
from arq import ArqRedis
from app.core.arq_client import get_arq_pool
from app.core.security import get_current_user
import structlog
from shared.app.db import get_db_session
from shared.app.schemas.groups import GroupCreate, GroupRead, GroupDetailRead # Added GroupDetailRead
from shared.app.schemas.chat import MessageCreate, MessageRead, MessageHistoryRead # Added MessageHistoryRead
from shared.app.agents.prompts import ORCHESTRATOR_PROMPT, AGENT_BASE_PROMPT
from shared.app.models.chat import ChatGroup, GroupMember, User, Message
from datetime import datetime # Added for Query

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post("/", response_model=GroupRead, status_code=201)
async def create_group(
    group_in: GroupCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    logger.info("create_group.start", owner_id=str(current_user.id))
    async with db() as session:
        try:
            new_group = ChatGroup(name=group_in.name, owner_id=current_user.id)

            orchestrator_member = GroupMember(
                alias="Orchestrator",
                group=new_group, # Associate with the group
                system_prompt=ORCHESTRATOR_PROMPT,
                provider="gemini", # Default, can be configured
                model="gemini-2.5-pro",
                temperature=0.1,
                tools=[] # Orchestrator typically doesn't use external tools directly in this design
            )

            session.add(new_group)
            session.add(orchestrator_member) # Add orchestrator to session

            for member_config in group_in.members:
                system_prompt = f"{AGENT_BASE_PROMPT}\n{member_config.role_prompt}"
                session.add(
                    GroupMember(
                        alias=member_config.alias,
                        group=new_group, # Associate with the group
                        system_prompt=system_prompt,
                        tools=member_config.tools,
                        provider=member_config.provider,
                        model=member_config.model,
                        temperature=member_config.temperature,
                    )
                )

            await session.commit()
            await session.refresh(new_group)
            # Eager load members for the response if GroupRead needs them,
            # or rely on GroupDetailRead for more comprehensive data.
            # For GroupRead, only id and name are needed.
            logger.info("create_group.success", group_id=str(new_group.id))
            return new_group
        except Exception as e:
            if hasattr(session, "rollback"):
                await session.rollback()
            logger.error("create_group.error", error=str(e))
            raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.get("/", response_model=list[GroupRead])
async def list_groups(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    logger.info("list_groups.start", user_id=str(current_user.id))
    async with db() as session:
        result = await session.execute(
            select(ChatGroup).where(ChatGroup.owner_id == current_user.id)
        )
        groups = result.scalars().all()
        logger.info("list_groups.success", count=len(groups))
        return groups


@router.get("/{group_id}", response_model=GroupDetailRead)
async def get_group_details(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    logger.info("get_group_details.start", group_id=str(group_id), user_id=str(current_user.id))
    async with db() as session:
        result = await session.execute(
            select(ChatGroup)
            .where(ChatGroup.id == group_id)
            .options(selectinload(ChatGroup.members)) # Eager load members
        )
        group = result.scalars().first()

        if not group:
            logger.warn("get_group_details.not_found", group_id=str(group_id))
            raise HTTPException(status_code=404, detail="Group not found")
        if group.owner_id != current_user.id:
            logger.warn("get_group_details.forbidden", group_id=str(group_id), owner_id=str(group.owner_id))
            raise HTTPException(status_code=403, detail="Not authorized to access this group")

        logger.info("get_group_details.success", group_id=str(group.id))
        return group


@router.get("/{group_id}/messages", response_model=list[MessageHistoryRead])
async def get_message_history(
    group_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    before_timestamp: datetime | None = Query(None, description="Fetch messages older than this timestamp (ISO 8601)"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    logger.info("get_message_history.start", group_id=str(group_id), user_id=str(current_user.id), limit=limit, before_timestamp=before_timestamp)
    async with db() as session:
        # First, verify group existence and ownership
        group_result = await session.execute(
            select(ChatGroup.id).where(ChatGroup.id == group_id, ChatGroup.owner_id == current_user.id)
        )
        if not group_result.scalars().first():
            logger.warn("get_message_history.group_not_found_or_forbidden", group_id=str(group_id))
            raise HTTPException(status_code=404, detail="Group not found or not authorized")

        query = (
            select(Message)
            .where(Message.group_id == group_id)
            .order_by(Message.timestamp.desc())
            .limit(limit)
        )

        if before_timestamp:
            query = query.where(Message.timestamp < before_timestamp)

        messages_result = await session.execute(query)
        messages = messages_result.scalars().all()
        
        # Messages are fetched in descending order, reverse for chronological display
        logger.info("get_message_history.success", group_id=str(group_id), count=len(messages))
        return messages[::-1]


@router.post("/{group_id}/messages", response_model=MessageRead, status_code=202)
async def send_message(
    group_id: uuid.UUID,
    message_in: MessageCreate,
    db: AsyncSession = Depends(get_db_session),
    arq_pool: ArqRedis = Depends(get_arq_pool),
    current_user: User = Depends(get_current_user),
):
    logger.info("send_message.start", group_id=str(group_id), user_id=str(current_user.id))
    async with db() as session:
        try:
            result = await session.execute(
                select(ChatGroup).where(
                    ChatGroup.id == group_id,
                    ChatGroup.owner_id == current_user.id,
                )
            )
            group = result.scalars().first()
            if not group:
                logger.warn("send_message.group_not_found", group_id=str(group_id))
                raise HTTPException(status_code=404, detail="Group not found")


            turn_id = uuid.uuid4()
            user_message = Message(
                group_id=group_id,
                turn_id=turn_id,
                sender_alias="User", # Standard alias for user-sent messages
                content=message_in.content,
                # timestamp is default=func.now()
            )

            session.add(user_message)
            await session.commit()
            await session.refresh(user_message)
            logger.info("send_message.saved_to_db", message_id=str(user_message.id))

        except HTTPException: # Re-raise HTTPExceptions directly
            raise
        except Exception as e:
            if hasattr(session, "rollback"):
                await session.rollback()
            logger.error("send_message.db_error", error=str(e))
            raise HTTPException(status_code=500, detail=f"Database error: {e}")

    for attempt in range(3): # Retry mechanism for enqueuing
        try:
            await arq_pool.enqueue_job(
                "start_turn",
                group_id=str(group_id),
                message_content=message_in.content,
                user_id=str(current_user.id),
                message_id=str(user_message.id), # Pass the persisted message ID
                turn_id=str(turn_id),
                _queue_name="orchestrator_queue",
            )
            logger.info("send_message.enqueued_to_orchestrator", group_id=str(group_id), message_id=str(user_message.id))
            break
        except Exception as e:
            logger.error("send_message.enqueue_attempt_failed", attempt=attempt + 1, error=str(e))
            if attempt == 2:
                # This is a critical failure. The message is saved but not processed.
                # Consider how to handle this: maybe a separate retry mechanism or admin alert.
                # For now, raise HTTPException to inform the client.
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to enqueue job for orchestrator after retries: {e}",
                )
            await asyncio.sleep(1) # Wait before retrying

    return user_message