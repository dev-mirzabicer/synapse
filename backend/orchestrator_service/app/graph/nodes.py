# /backend/orchestrator_service/app/graph/nodes.py

import json
import uuid
import inspect
from redis.asyncio import Redis
from graph.state import GraphState
from shared.app.utils.message_serde import serialize_messages
from shared.app.db import AsyncSessionLocal
from shared.app.models.chat import Message
from sqlalchemy.dialects.postgresql import insert
from shared.app.core.config import settings
import structlog
from shared.app.core.logging import setup_logging

# Import the single, shared checkpointer instance from the renamed file.
from graph.checkpointer import checkpoint as graph_checkpoint

setup_logging()
logger = structlog.get_logger(__name__)


async def _persist_new_messages(state: GraphState, config: dict) -> None:
    """
    Persists any new messages from the state to the database and broadcasts
    them over a Redis pub/sub channel for real-time updates.
    """
    # Get the index of the last message that was saved to the database.
    # This prevents us from re-saving messages that have already been persisted.
    last_saved = state.get("last_saved_index", 0)
    new_messages = state["messages"][last_saved:]
    if not new_messages:
        return

    async with AsyncSessionLocal() as session:
        # It's crucial to create and close the Redis connection within this scope
        # to ensure proper resource management.
        redis = Redis.from_url(settings.REDIS_URL)
        try:
            for msg in new_messages:
                # Use an INSERT ... ON CONFLICT DO NOTHING statement to prevent
                # errors if a message with the same ID somehow gets processed twice.
                stmt = (
                    insert(Message)
                    .values(
                        id=getattr(msg, "id", uuid.uuid4()),
                        group_id=state["group_id"],
                        turn_id=state["turn_id"],
                        sender_alias=getattr(msg, "name", "system"),
                        content=str(msg.content),
                        meta=msg.dict(),
                    )
                    .on_conflict_do_nothing(index_elements=["id"])
                )
                await session.execute(stmt)
                # Publish the new message to the group-specific Redis channel
                # so that connected WebSocket clients can receive it in real-time.
                await redis.publish(
                    f"group:{state['group_id']}",
                    json.dumps(msg.dict()),
                )
            await session.commit()
        finally:
            await redis.close()

    # After successfully saving the new messages, update the checkpointer state
    # with the new index. This is a critical step for statefulness.
    await graph_checkpoint.update_state(
        config,
        {"last_saved_index": last_saved + len(new_messages)},
    )


async def dispatch_node(state: GraphState, config: dict) -> dict:
    """
    A node that persists new messages and then dispatches jobs to the appropriate
    execution workers based on the content of the last message in the state.
    """
    # The arq_pool is injected into the config when the graph is invoked.
    arq_pool = config["arq_pool"]
    thread_id = config["configurable"]["thread_id"]

    # Always persist any new messages before dispatching new work.
    await _persist_new_messages(state, config)

    last_message = state["messages"][-1]

    # If the last message contains tool calls, enqueue a 'run_tool' job
    # for each call on the dedicated execution queue.
    if tool_calls := getattr(last_message, "tool_calls", []):
        for call in tool_calls:
            logger.info("dispatch.tool", tool=call["name"], thread_id=thread_id)
            await arq_pool.enqueue_job(
                "run_tool",
                tool_name=call["name"],
                tool_args=call["args"],
                tool_call_id=call["id"],
                thread_id=thread_id,
                _queue_name="execution_queue",
            )
    # If the router identified the next agents to act, enqueue a 'run_agent_llm'
    # job for each of them on the dedicated execution queue.
    elif next_actors := state.get("next_actors"):
        messages_dict = serialize_messages(state["messages"])
        group_members_dict = [gm.dict() for gm in state["group_members"]]
        for alias in next_actors:
            logger.info("dispatch.agent", alias=alias, thread_id=thread_id)
            await arq_pool.enqueue_job(
                "run_agent_llm",
                alias=alias,
                messages_dict=messages_dict,
                group_members_dict=group_members_dict,
                thread_id=thread_id,
                _queue_name="execution_queue",
            )
    return {}


async def sync_to_postgres_node(state: GraphState, config: dict) -> dict:
    """
    A terminal node that ensures any final messages are persisted before
    the graph finishes its run. This is a crucial cleanup step.
    """
    thread_id = config["configurable"]["thread_id"]
    logger.info("sync_to_postgres.start", thread_id=thread_id)

    # --- FIX ---
    # The previous code was calling `graph_checkpoint.aget(config)` directly,
    # which returns a context manager object instead of the state.
    # The correct way to get the state is to use `async with`, which enters
    # the context manager and yields the full, up-to-date state.
    async with graph_checkpoint.aget(config) as full_state:
        # It's possible for the state to be None if the checkpoint is empty.
        if full_state:
            # Pass the complete, retrieved state to the persistence function.
            await _persist_new_messages(full_state, config)

    logger.info("sync_to_postgres.complete", thread_id=thread_id)
    return {}