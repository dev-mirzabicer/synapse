import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from arq import ArqRedis
from app.core.arq_client import get_arq_pool
from shared.app.db import get_db_session
from shared.app.schemas.chat import GroupCreate, GroupRead
from shared.app.models.chat import ChatGroup, GroupMember, User, Message
from shared.app.schemas.chat import MessageCreate, MessageRead

router = APIRouter()

@router.post("/", response_model=GroupRead, status_code=201)
async def create_group(group_in: GroupCreate, db: AsyncSession = Depends(get_db_session)):
    # TODO (Phase 1): Get user_id from a real JWT token dependency
    async with db() as session:
        result = await session.execute(select(User).limit(1))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="No users found. Please register a user first.")

        new_group = ChatGroup(name=group_in.name, owner_id=user.id)
        
        # Every group has an Orchestrator and a User member by default
        orchestrator_member = GroupMember(alias="Orchestrator", group=new_group)
        user_member = GroupMember(alias="User", group=new_group)

        session.add(new_group)
        session.add(orchestrator_member)
        session.add(user_member)
        await session.commit()
        await session.refresh(new_group)
        return new_group

# TODO (Phase 1): Implement GET / endpoint to list groups for a user

@router.post("/{group_id}/messages", response_model=MessageRead, status_code=202)
async def send_message(
    group_id: uuid.UUID,
    message_in: MessageCreate,
    db: AsyncSession = Depends(get_db_session),
    arq_pool: ArqRedis = Depends(get_arq_pool)
):
    # TODO (Phase 1): Validate that user is a member of the group
    
    turn_id = uuid.uuid4()
    user_message = Message(
        group_id=group_id,
        turn_id=turn_id,
        sender_alias="User",
        content=message_in.content
    )

    async with db() as session:
        session.add(user_message)
        await session.commit()
        await session.refresh(user_message)

    # Enqueue the job for the orchestrator to process
    await arq_pool.enqueue_job(
        "process_turn", # This is the function name in the worker
        group_id=str(group_id),
        turn_id=str(turn_id)
    )

    return user_message