import structlog
from arq import ArqRedis
from arq.connections import RedisSettings
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from sqlalchemy import select

from graph.graph import graph_app_uncompiled
from shared.app.core.config import settings
from shared.app.core.logging import setup_logging
from shared.app.db import AsyncSessionLocal
from shared.app.models.chat import GroupMember
from shared.app.schemas.groups import GroupMemberRead
from shared.app.utils.message_serde import deserialize_messages

setup_logging()
logger = structlog.get_logger(__name__)


async def start_turn(
    ctx,
    group_id: str,
    message_content: str,
    user_id: str,
    message_id: str,
    turn_id: str,
):
    """Starts a new turn initiated by a user."""
    logger.info("start_turn", group_id=group_id, user_id=user_id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GroupMember).where(GroupMember.group_id == group_id)
        )
        members = [GroupMemberRead.model_validate(m) for m in result.scalars().all()]

    user_msg = HumanMessage(content=message_content)
    user_msg.id = message_id
    user_msg.name = "User"

    graph_input = {
        "messages": [user_msg],
        "group_id": group_id,
        "group_members": members,
        "turn_count": 0,
        "last_saved_index": 0,
        "turn_id": turn_id,
    }

    arq_pool: ArqRedis = ctx["redis"]

    async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
        invocation_config = {
            "configurable": {
                "thread_id": group_id,
                "checkpointer": checkpointer,
                "arq_pool": arq_pool,
            }
        }
        await graph_app_uncompiled.ainvoke(graph_input, config=invocation_config)
    logger.info("start_turn.complete", group_id=group_id)


async def update_graph_with_message(ctx, thread_id: str, message_dict: dict):
    """
    Receives a message from a worker, fully re-hydrates the graph state,
    and continues the graph execution.
    """
    logger.info("update_graph_with_message.start", thread_id=thread_id)
    arq_pool: ArqRedis = ctx["redis"]

    try:
        new_message = deserialize_messages([message_dict])[0]
    except Exception as e:
        logger.error("update_graph_with_message.deserialization_error", error=str(e))
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GroupMember).where(GroupMember.group_id == thread_id)
        )
        members = [GroupMemberRead.model_validate(m) for m in result.scalars().all()]

    async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
        config = {"configurable": {"thread_id": thread_id}}
        
        # --- FIX: Fetch the checkpoint to get the current turn_id ---
        checkpoint = await checkpointer.aget(config)
        if not checkpoint:
            logger.error("update_graph_with_message.checkpoint_not_found", thread_id=thread_id)
            return
        
        # Extract the turn_id from the loaded state
        turn_id = checkpoint.get("channel_values", {}).get("turn_id")
        if not turn_id:
            logger.error("update_graph_with_message.turn_id_not_found_in_checkpoint", thread_id=thread_id)
            return

        # Construct the complete input payload
        input_payload = {
            "messages": [new_message],
            "group_members": members,
            "group_id": thread_id,
            "turn_id": turn_id,
        }
        # --- END FIX ---

        invocation_config = {"configurable": {**config["configurable"], "checkpointer": checkpointer, "arq_pool": arq_pool}}
        await graph_app_uncompiled.ainvoke(input_payload, config=invocation_config)

    logger.info("update_graph_with_message.invoked_continue", thread_id=thread_id)


class WorkerSettings:
    functions = [start_turn, update_graph_with_message]
    queue_name = "orchestrator_queue"
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    async def on_startup(ctx):
        logger.info("worker.startup", redis_host=settings.REDIS_URL)
        async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
            await checkpointer.asetup()
        logger.info("worker.startup.checkpointer_ready")

    async def on_shutdown(ctx):
        logger.info("worker.shutdown")