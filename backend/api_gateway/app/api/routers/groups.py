import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from arq import ArqRedis
from app.core.arq_client import get_arq_pool
from app.core.security import get_current_user
from shared.app.db import get_db_session
from shared.app.schemas.chat import GroupCreate, GroupRead
from shared.app.models.chat import ChatGroup, GroupMember, User, Message
from shared.app.schemas.chat import MessageCreate, MessageRead

router = APIRouter()


@router.post("/", response_model=GroupRead, status_code=201)
async def create_group(
    group_in: GroupCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),  # SECURE THIS ENDPOINT
):
    async with db() as session:
        new_group = ChatGroup(name=group_in.name, owner_id=current_user.id)
        # Every group has an Orchestrator and a User member by default
        orchestrator_member = GroupMember(alias="Orchestrator", group=new_group)
        user_member = GroupMember(alias="User", group=new_group)

        session.add(new_group)
        session.add(orchestrator_member)
        session.add(user_member)
        await session.commit()
        await session.refresh(new_group)
        return new_group


@router.get("/", response_model=list[GroupRead])
async def list_groups(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
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
    async with db() as session:
        group = await session.get(ChatGroup, group_id)
        if not group or group.owner_id != current_user.id:
            raise HTTPException(status_code=404, detail="Group not found")

        member_check = await session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.alias == "User",
            )
        )
        if not member_check.scalars().first():
            raise HTTPException(
                status_code=400, detail="Sender not a member of this group"
            )

        turn_id = uuid.uuid4()
        user_message = Message(
            group_id=group_id,
            turn_id=turn_id,
            sender_alias="User",
            content=message_in.content,
        )

        session.add(user_message)
        await session.commit()
        await session.refresh(user_message)

    # Enqueue the job for the orchestrator to process
    await arq_pool.enqueue_job(
        "start_turn",
        group_id=str(group_id),
        message_content=message_in.content,
        user_id=str(current_user.id),  # Pass user context if needed later
    )

    return user_message
