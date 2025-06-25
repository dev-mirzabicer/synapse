import asyncio
import json
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

# --- Constants for Redis keys ---
GATHER_KEY_PREFIX = "synapse:gather"
GATHER_TIMEOUT_SECONDS = 300  # 5 minutes


async def start_turn(
    ctx,
    group_id: str,
    message_content: str,
    user_id: str,
    message_id: str,
    turn_id: str,
):
    """Starts a new turn initiated by a user."""
    logger.info("start_turn.initiated", group_id=group_id, turn_id=turn_id)

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
        graph_app = workflow.compile(checkpointer=checkpointer)
        invocation_config = {
            "configurable": {
                "thread_id": group_id,
                "arq_pool": arq_pool,
            }
        }
        await graph_app.ainvoke(graph_input, config=invocation_config)
    logger.info("start_turn.complete", group_id=group_id, turn_id=turn_id)


async def process_worker_result(
    ctx, thread_id: str, message_dict: dict, gathering_id: str | None = None
):
    """
    Receives a result from an execution worker.
    If it's part of a parallel dispatch (has a gathering_id), it collects results.
    Once all results are collected, or if it's a single result, it updates the graph.
    """
    logger.info(
        "process_worker_result.received",
        thread_id=thread_id,
        gathering_id=gathering_id,
    )

    if not gathering_id:
        # This is a single, non-parallel response (e.g., from a tool call or single agent dispatch).
        # We can update the graph immediately.
        logger.info("process_worker_result.single_dispatch", thread_id=thread_id)
        await update_graph_with_messages(
            ctx, thread_id=thread_id, messages_dict=[message_dict]
        )
        return

    # --- Collector Logic for Parallel Responses ---
    arq_pool: ArqRedis = ctx["redis"]
    gather_hash_key = f"{GATHER_KEY_PREFIX}:{gathering_id}"
    gather_list_key = f"{gather_hash_key}:messages"

    # Atomically store the message and increment the received count
    pipe = arq_pool.pipeline()
    pipe.rpush(gather_list_key, json.dumps(message_dict))
    pipe.hincrby(gather_hash_key, "received", 1)
    pipe.expire(gather_hash_key, GATHER_TIMEOUT_SECONDS)  # Add TTL for safety
    pipe.expire(gather_list_key, GATHER_TIMEOUT_SECONDS)
    _, received_count, _, _ = await pipe.execute()

    # Get the expected count
    expected_count_str = await arq_pool.hget(gather_hash_key, "expected")
    if not expected_count_str:
        logger.error(
            "process_worker_result.missing_expected_count",
            gathering_id=gathering_id,
            thread_id=thread_id,
        )
        # Failsafe: process what we have to avoid losing the message.
        await update_graph_with_messages(
            ctx, thread_id=thread_id, messages_dict=[message_dict]
        )
        return

    expected_count = int(expected_count_str)
    logger.info(
        "process_worker_result.collection_status",
        gathering_id=gathering_id,
        received=received_count,
        expected=expected_count,
    )

    if received_count >= expected_count:
        # We are the "collector" job, the last one to arrive.
        logger.info(
            "process_worker_result.collection_complete",
            gathering_id=gathering_id,
            thread_id=thread_id,
        )

        # Atomically get all messages and delete the keys
        pipe = arq_pool.pipeline()
        pipe.lrange(gather_list_key, 0, -1)
        pipe.delete(gather_list_key)
        pipe.delete(gather_hash_key)
        all_message_strs, _, _ = await pipe.execute()

        all_messages_dict = [json.loads(m) for m in all_message_strs]

        # Update the graph with the complete batch of messages
        await update_graph_with_messages(
            ctx, thread_id=thread_id, messages_dict=all_messages_dict
        )
    else:
        # Not all results are in yet. This job's work is done.
        logger.info(
            "process_worker_result.waiting_for_more",
            gathering_id=gathering_id,
            thread_id=thread_id,
        )


async def update_graph_with_messages(ctx, thread_id: str, messages_dict: list[dict]):
    """
    Receives a list of messages, adds them to the graph's state,
    and continues the graph execution.
    """
    logger.info(
        "update_graph_with_messages.received",
        thread_id=thread_id,
        message_count=len(messages_dict),
    )
    arq_pool: ArqRedis = ctx["redis"]

    try:
        new_messages = deserialize_messages(messages_dict)
    except Exception as e:
        logger.error(
            "update_graph_with_messages.deserialization_error", error=str(e), exc_info=True
        )
        return

    # The input is the new list of messages. LangGraph will use the checkpointer
    # to load the previous state and append these messages.
    input_payload = {
        "messages": new_messages,
    }

    async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
        graph_app = workflow.compile(checkpointer=checkpointer)
        invocation_config = {
            "configurable": {
                "thread_id": thread_id,
                "arq_pool": arq_pool,
            }
        }
        # `ainvoke` will now correctly load the checkpoint, merge the new
        # messages, run the graph, and save the resulting state.
        await graph_app.ainvoke(input_payload, config=invocation_config)

    logger.info("update_graph_with_messages.invoked_continue", thread_id=thread_id)


class WorkerSettings:
    functions = [start_turn, process_worker_result]  # MODIFIED
    queue_name = "orchestrator_queue"
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    async def on_startup(ctx):
        logger.info("worker.startup", redis_host=settings.REDIS_URL)
        # Setup checkpointer tables/indices if they don't exist
        async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
            await checkpointer.asetup()
        logger.info("worker.startup.checkpointer_ready")

    async def on_shutdown(ctx):
        logger.info("worker.shutdown")