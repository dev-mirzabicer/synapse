import os
import uuid
import json
from arq import ArqRedis
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from shared.app.core.config import settings
from shared.app.models.chat import Message

# --- Database Setup ---
engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# --- ARQ Redis Setup ---
# We need a separate Redis client for Pub/Sub within the worker
redis_settings = RedisSettings(host=settings.REDIS_URL.split("://")[1], port=6379)

async def process_turn(ctx, group_id: str, turn_id: str):
    """
    This function is executed by the ARQ worker.
    It represents the simplest version of our LangGraph orchestrator.
    """
    print(f"Processing turn {turn_id} for group {group_id}")
    arq_pool: ArqRedis = ctx['redis']

    # TODO (Phase 2): Implement the full LangGraph state machine here.
    # For now, we simulate the core logic.

    # 1. Fetch conversation history (omitted for Phase 1)
    # 2. Call a placeholder LLM
    orchestrator_response_content = f"This is a dummy response for turn {turn_id}."

    # 3. Save the response to the database
    orchestrator_message = Message(
        group_id=uuid.UUID(group_id),
        turn_id=uuid.UUID(turn_id),
        sender_alias="Orchestrator",
        content=orchestrator_response_content
    )
    async with AsyncSessionLocal() as session:
        session.add(orchestrator_message)
        await session.commit()
        await session.refresh(orchestrator_message)
        # Convert the SQLAlchemy model to a dictionary for JSON serialization
        message_data = {
            "id": str(orchestrator_message.id),
            "turn_id": str(orchestrator_message.turn_id),
            "sender_alias": orchestrator_message.sender_alias,
            "content": orchestrator_message.content
        }

    # 4. Notify frontend via Redis Pub/Sub
    channel = f"group:{group_id}"
    await arq_pool.publish(channel, json.dumps(message_data))
    print(f"Published message to Redis channel '{channel}'")

    return {"status": "ok", "response": orchestrator_response_content}


class WorkerSettings:
    functions = [process_turn]
    # This on_startup function ensures the redis pool is available in the context
    async def on_startup(self, ctx):
        ctx['redis'] = await create_pool(redis_settings)

    async def on_shutdown(self, ctx):
        await ctx['redis'].close()