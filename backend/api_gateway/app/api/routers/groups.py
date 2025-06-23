import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query, status # Added status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from arq import ArqRedis
from app.core.arq_client import get_arq_pool
from app.core.security import get_current_user
import structlog
from shared.app.db import get_db_session
from shared.app.schemas.groups import ( #ชัดเจนขึ้น
    GroupCreate,
    GroupRead,
    GroupDetailRead,
    AgentConfigCreate,
    AgentConfigUpdate,
    GroupMemberRead,
    GroupUpdate,
)
from shared.app.schemas.chat import MessageCreate, MessageRead, MessageHistoryRead
from shared.app.agents.prompts import ORCHESTRATOR_PROMPT, AGENT_BASE_PROMPT
from shared.app.models.chat import ChatGroup, GroupMember, User, Message
from datetime import datetime

router = APIRouter()
logger = structlog.get_logger(__name__)

# --- Helper Function to get and authorize group ---
async def get_group_and_authorize(
    group_id: uuid.UUID, session: AsyncSession, current_user: User, eager_load_members: bool = False
) -> ChatGroup:
    """Fetches a group and verifies ownership."""
    query = select(ChatGroup).where(ChatGroup.id == group_id)
    if eager_load_members:
        query = query.options(selectinload(ChatGroup.members))
    
    result = await session.execute(query)
    group = result.scalars().first()

    if not group:
        logger.warn("get_group_and_authorize.not_found", group_id=str(group_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if group.owner_id != current_user.id:
        logger.warn("get_group_and_authorize.forbidden", group_id=str(group_id), owner_id=str(group.owner_id), current_user_id=str(current_user.id))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this group")
    return group

# --- Helper Function to get and authorize group member ---
async def get_member_and_authorize(
    group_id: uuid.UUID, member_id: uuid.UUID, session: AsyncSession, current_user: User
) -> GroupMember:
    """Fetches a group member, ensuring it belongs to the specified group and user."""
    group = await get_group_and_authorize(group_id, session, current_user) # Authorization check for group

    result = await session.execute(
        select(GroupMember).where(GroupMember.id == member_id, GroupMember.group_id == group.id)
    )
    member = result.scalars().first()
    if not member:
        logger.warn("get_member_and_authorize.not_found", member_id=str(member_id), group_id=str(group_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group member not found")
    
    if member.alias == "Orchestrator":
        logger.warn("get_member_and_authorize.orchestrator_modification_attempt", member_id=str(member_id))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The Orchestrator member cannot be modified or deleted.")
    return member


@router.post("/", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
async def create_group(
    group_in: GroupCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    logger.info("create_group.start", owner_id=str(current_user.id), group_name=group_in.name)
    async with db() as session:
        try:
            new_group = ChatGroup(name=group_in.name, owner_id=current_user.id)
            session.add(new_group)
            # It's important to flush here so new_group.id is available if needed before commit,
            # though for associating members, adding them to session and then committing works.
            # await session.flush() # Ensure new_group.id is populated for member association

            orchestrator_member = GroupMember(
                alias="Orchestrator",
                # group_id=new_group.id, # Set after flush or rely on relationship
                group=new_group,
                system_prompt=ORCHESTRATOR_PROMPT,
                provider="gemini",
                model="gemini-2.5-pro",
                temperature=0.1,
                tools=[]
            )
            session.add(orchestrator_member)

            for member_config in group_in.members:
                system_prompt = f"{AGENT_BASE_PROMPT}\n{member_config.role_prompt}"
                session.add(
                    GroupMember(
                        alias=member_config.alias,
                        # group_id=new_group.id,
                        group=new_group,
                        system_prompt=system_prompt,
                        tools=member_config.tools,
                        provider=member_config.provider,
                        model=member_config.model,
                        temperature=member_config.temperature,
                    )
                )

            await session.commit()
            await session.refresh(new_group) # Refresh to get any DB-generated values
            logger.info("create_group.success", group_id=str(new_group.id))
            return new_group
        except Exception as e: # Catch generic exceptions last
            if hasattr(session, "rollback"):
                await session.rollback()
            logger.error("create_group.error", error=str(e), exc_info=True)
            if isinstance(e, HTTPException): # Re-raise HTTPExceptions
                 raise
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {e}")


@router.get("/", response_model=list[GroupRead])
async def list_groups(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    logger.info("list_groups.start", user_id=str(current_user.id))
    async with db() as session:
        result = await session.execute(
            select(ChatGroup).where(ChatGroup.owner_id == current_user.id).order_by(ChatGroup.created_at.desc())
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
        group = await get_group_and_authorize(group_id, session, current_user, eager_load_members=True)
        logger.info("get_group_details.success", group_id=str(group.id))
        return group

@router.put("/{group_id}", response_model=GroupRead)
async def update_group_name(
    group_id: uuid.UUID,
    group_in: GroupUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    logger.info("update_group_name.start", group_id=str(group_id), new_name=group_in.name, user_id=str(current_user.id))
    async with db() as session:
        group = await get_group_and_authorize(group_id, session, current_user)
        group.name = group_in.name
        try:
            await session.commit()
            await session.refresh(group)
            logger.info("update_group_name.success", group_id=str(group.id))
            return group
        except Exception as e:
            await session.rollback()
            logger.error("update_group_name.error", group_id=str(group_id), error=str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not update group name: {e}")


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    logger.info("delete_group.start", group_id=str(group_id), user_id=str(current_user.id))
    async with db() as session:
        group = await get_group_and_authorize(group_id, session, current_user)
        try:
            await session.delete(group)
            await session.commit()
            logger.info("delete_group.success", group_id=str(group_id))
        except Exception as e:
            await session.rollback()
            logger.error("delete_group.error", group_id=str(group_id), error=str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not delete group: {e}")
    return None # For 204 response

# --- Group Member (Agent) Management ---

@router.post("/{group_id}/members", response_model=GroupMemberRead, status_code=status.HTTP_201_CREATED)
async def add_group_member(
    group_id: uuid.UUID,
    member_in: AgentConfigCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    logger.info("add_group_member.start", group_id=str(group_id), alias=member_in.alias, user_id=str(current_user.id))
    async with db() as session:
        group = await get_group_and_authorize(group_id, session, current_user) # Authorizes group access

        # Optional: Check for alias conflict within the group
        existing_member_check = await session.execute(
            select(GroupMember.id).where(GroupMember.group_id == group_id, GroupMember.alias == member_in.alias)
        )
        if existing_member_check.scalars().first():
            logger.warn("add_group_member.alias_conflict", group_id=str(group_id), alias=member_in.alias)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"An agent with alias '{member_in.alias}' already exists in this group.")

        system_prompt = f"{AGENT_BASE_PROMPT}\n{member_in.role_prompt}"
        new_member = GroupMember(
            group_id=group.id,
            alias=member_in.alias,
            system_prompt=system_prompt,
            tools=member_in.tools,
            provider=member_in.provider,
            model=member_in.model,
            temperature=member_in.temperature,
        )
        session.add(new_member)
        try:
            await session.commit()
            await session.refresh(new_member)
            logger.info("add_group_member.success", member_id=str(new_member.id), group_id=str(group_id))
            return new_member
        except Exception as e:
            await session.rollback()
            logger.error("add_group_member.error", group_id=str(group_id), error=str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not add member: {e}")


@router.put("/{group_id}/members/{member_id}", response_model=GroupMemberRead)
async def update_group_member(
    group_id: uuid.UUID,
    member_id: uuid.UUID,
    member_in: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    logger.info("update_group_member.start", group_id=str(group_id), member_id=str(member_id), user_id=str(current_user.id))
    async with db() as session:
        member = await get_member_and_authorize(group_id, member_id, session, current_user) # Handles auth and "Orchestrator" check

        update_data = member_in.model_dump(exclude_unset=True)
        
        # Optional: Check for alias conflict if alias is being changed
        if "alias" in update_data and update_data["alias"] != member.alias:
            existing_member_check = await session.execute(
                select(GroupMember.id).where(
                    GroupMember.group_id == group_id, 
                    GroupMember.alias == update_data["alias"],
                    GroupMember.id != member_id # Exclude the current member from check
                )
            )
            if existing_member_check.scalars().first():
                logger.warn("update_group_member.alias_conflict", group_id=str(group_id), new_alias=update_data["alias"])
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"An agent with alias '{update_data['alias']}' already exists in this group.")

        for field, value in update_data.items():
            setattr(member, field, value)
        
        if "role_prompt" in update_data: # If role_prompt changes, system_prompt must be updated
            member.system_prompt = f"{AGENT_BASE_PROMPT}\n{member.role_prompt}"

        try:
            await session.commit()
            await session.refresh(member)
            logger.info("update_group_member.success", member_id=str(member.id), group_id=str(group_id))
            return member
        except Exception as e:
            await session.rollback()
            logger.error("update_group_member.error", member_id=str(member.id), error=str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not update member: {e}")


@router.delete("/{group_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group_member(
    group_id: uuid.UUID,
    member_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    logger.info("delete_group_member.start", group_id=str(group_id), member_id=str(member_id), user_id=str(current_user.id))
    async with db() as session:
        member = await get_member_and_authorize(group_id, member_id, session, current_user) # Handles auth and "Orchestrator" check
        try:
            await session.delete(member)
            await session.commit()
            logger.info("delete_group_member.success", member_id=str(member_id), group_id=str(group_id))
        except Exception as e:
            await session.rollback()
            logger.error("delete_group_member.error", member_id=str(member.id), error=str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not delete member: {e}")
    return None


# --- Message Endpoints (from Phase 1, ensure they are still correct) ---
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
        group = await get_group_and_authorize(group_id, session, current_user) # Verify group access

        query = (
            select(Message)
            .where(Message.group_id == group.id)
            .order_by(Message.timestamp.desc())
            .limit(limit)
        )

        if before_timestamp:
            query = query.where(Message.timestamp < before_timestamp)

        messages_result = await session.execute(query)
        messages = messages_result.scalars().all()
        
        logger.info("get_message_history.success", group_id=str(group.id), count=len(messages))
        return messages[::-1]


@router.post("/{group_id}/messages", response_model=MessageRead, status_code=status.HTTP_202_ACCEPTED)
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
            group = await get_group_and_authorize(group_id, session, current_user) # Verify group access

            turn_id = uuid.uuid4()
            user_message = Message(
                group_id=group.id,
                turn_id=turn_id,
                sender_alias="User",
                content=message_in.content,
            )

            session.add(user_message)
            await session.commit()
            await session.refresh(user_message)
            logger.info("send_message.saved_to_db", message_id=str(user_message.id))

        except HTTPException:
            raise
        except Exception as e:
            if hasattr(session, "rollback"):
                await session.rollback()
            logger.error("send_message.db_error", error=str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {e}")

    for attempt in range(3):
        try:
            await arq_pool.enqueue_job(
                "start_turn",
                group_id=str(group_id),
                message_content=message_in.content,
                user_id=str(current_user.id),
                message_id=str(user_message.id),
                turn_id=str(turn_id),
                _queue_name="orchestrator_queue",
            )
            logger.info("send_message.enqueued_to_orchestrator", group_id=str(group_id), message_id=str(user_message.id))
            break
        except Exception as e:
            logger.error("send_message.enqueue_attempt_failed", attempt=attempt + 1, error=str(e))
            if attempt == 2:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to enqueue job for orchestrator after retries: {e}",
                )
            await asyncio.sleep(1)

    return user_message