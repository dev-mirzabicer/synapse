import asyncio
import structlog
from arq import ArqRedis
from arq.connections import RedisSettings
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from sqlalchemy import select

# Import the graph DEFINITION, not a pre-compiled app
from graph.graph import workflow
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
    logger.info("start_turn.initiated", group_id=group_id)

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
        # COMPILE the graph with the checkpointer. This is the crucial step.
        graph_app = workflow.compile(checkpointer=checkpointer)

        invocation_config = {
            "configurable": {
                "thread_id": group_id,
                # The arq_pool is passed for the nodes to use.
                "arq_pool": arq_pool,
            }
        }
        await graph_app.ainvoke(graph_input, config=invocation_config)
    logger.info("start_turn.complete", group_id=group_id)


async def update_graph_with_message(ctx, thread_id: str, message_dict: dict):
    """
    Receives a message from a worker, adds it to the graph's state,
    and continues the graph execution.
    """
    logger.info("update_graph_with_message.received", thread_id=thread_id)
    arq_pool: ArqRedis = ctx["redis"]

    try:
        new_message = deserialize_messages([message_dict])[0]
    except Exception as e:
        logger.error("update_graph_with_message.deserialization_error", error=str(e))
        return

    # The input is just the new message. LangGraph will use the checkpointer
    # (compiled into the graph) to load the previous state and append this message.
    input_payload = {
        "messages": [new_message],
    }

    async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
        # COMPILE the graph with the checkpointer for this continuation.
        graph_app = workflow.compile(checkpointer=checkpointer)

        invocation_config = {
            "configurable": {
                "thread_id": thread_id,
                "arq_pool": arq_pool,
            }
        }
        # `ainvoke` will now correctly load the checkpoint, merge the new
        # message, run the graph, and save the resulting state.
        await graph_app.ainvoke(input_payload, config=invocation_config)

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