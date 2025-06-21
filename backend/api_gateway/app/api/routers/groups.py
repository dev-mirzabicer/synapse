import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from arq import ArqRedis
from app.core.arq_client import get_arq_pool
from app.core.security import get_current_user
import structlog
from shared.app.db import get_db_session
from shared.app.schemas.chat import GroupCreate, GroupRead
from shared.app.agents.prompts import ORCHESTRATOR_PROMPT, AGENT_BASE_PROMPT
from shared.app.models.chat import ChatGroup, GroupMember, User, Message
from shared.app.schemas.chat import MessageCreate, MessageRead

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post("/", response_model=GroupRead, status_code=201)
async def create_group(
    group_in: GroupCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),  # SECURE THIS ENDPOINT
):
    logger.info("create_group.start", owner_id=str(current_user.id))
    async with db() as session:
        try:
            new_group = ChatGroup(name=group_in.name, owner_id=current_user.id)

            orchestrator_member = GroupMember(
                alias="Orchestrator",
                group=new_group,
                system_prompt=ORCHESTRATOR_PROMPT,
                provider="gemini",
                model="models/gemini-pro",
                temperature=0.1,
            )

            session.add(new_group)
            session.add(orchestrator_member)

            for member in group_in.members:
                system_prompt = f"{AGENT_BASE_PROMPT}\n{member.role_prompt}"
                session.add(
                    GroupMember(
                        alias=member.alias,
                        group=new_group,
                        system_prompt=system_prompt,
                        tools=member.tools,
                        provider=member.provider,
                        model=member.model,
                        temperature=member.temperature,
                    )
                )

            await session.commit()
            await session.refresh(new_group)
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
    logger.info("list_groups", user_id=str(current_user.id))
    async with db() as session:
        result = await session.execute(
            select(ChatGroup).where(ChatGroup.owner_id == current_user.id)
        )
        groups = result.scalars().all()
        return groups


@router.post("/{group_id}/messages", response_model=MessageRead, status_code=202)
async def send_message(
    group_id: uuid.UUID,
    message_in: MessageCreate,
    db: AsyncSession = Depends(get_db_session),
    arq_pool: ArqRedis = Depends(get_arq_pool),
    current_user: User = Depends(get_current_user),  # SECURE THIS ENDPOINT
):
    logger.info("send_message.start", group_id=str(group_id))
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
                raise HTTPException(status_code=404, detail="Group not found")


            # Logic from 'main': Create the message object
            turn_id = uuid.uuid4()
            user_message = Message(
                group_id=group_id,
                turn_id=turn_id,
                sender_alias="User",
                content=message_in.content,
            )

            # Logic from both: Add, commit, and refresh the message
            session.add(user_message)
            await session.commit()
            await session.refresh(user_message)
            logger.info("send_message.saved", message_id=str(user_message.id))

        # Error handling from 'refactor' branch
        except Exception as e:
            if hasattr(session, "rollback"):
                await session.rollback()
            # We re-raise the original HTTPException if it's a validation error
            if isinstance(e, HTTPException):
                logger.warning("send_message.validation_error", error=str(e))
                raise
            # Otherwise, wrap it as a generic database error
            logger.error("send_message.db_error", error=str(e))
            raise HTTPException(status_code=500, detail=f"Database error: {e}")

    # Enqueue the job for the orchestrator to process
    try:
        # Job details from 'main' branch
        await arq_pool.enqueue_job(
            "start_turn",
            group_id=str(group_id),
            message_content=message_in.content,
            user_id=str(current_user.id),
            message_id=str(user_message.id),
            turn_id=str(turn_id),
        )
        logger.info("send_message.enqueued", group_id=str(group_id))
    # Error handling from 'refactor' branch
    except Exception as e:
        logger.error("send_message.enqueue_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to enqueue job: {e}")

    return user_message
