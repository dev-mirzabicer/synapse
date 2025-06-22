import json
import uuid
from redis.asyncio import Redis
from graph.state import GraphState
from shared.app.utils.message_serde import serialize_messages
from shared.app.db import AsyncSessionLocal
from shared.app.models.chat import Message
from sqlalchemy.dialects.postgresql import insert
from shared.app.core.config import settings
import structlog
from shared.app.core.logging import setup_logging

setup_logging()
logger = structlog.get_logger(__name__)


async def _persist_new_messages(state: GraphState, config: dict) -> None:
    """
    Persists any new messages from the state to the database and broadcasts
    them over a Redis pub/sub channel for real-time updates.
    """
    # The checkpointer is now passed in the config
    checkpointer = config.get("checkpointer")
    if not checkpointer:
        logger.warning("persist_new_messages.no_checkpointer")
        return

    last_saved = state.get("last_saved_index", 0)
    new_messages = state["messages"][last_saved:]
    if not new_messages:
        return

    async with AsyncSessionLocal() as session:
        redis = Redis.from_url(settings.REDIS_URL)
        try:
            for msg in new_messages:
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
                await redis.publish(
                    f"group:{state['group_id']}",
                    json.dumps(msg.dict()),
                )
            await session.commit()
        finally:
            await redis.close()

    # Use the checkpointer from config to update the state
    await checkpointer.update_state(
        config,
        {"last_saved_index": last_saved + len(new_messages)},
    )


async def dispatch_node(state: GraphState, config: dict) -> dict:
    """
    A node that persists new messages and then dispatches jobs to the appropriate
    execution workers based on the content of the last message in the state.
    """
    arq_pool = config["arq_pool"]
    thread_id = config["configurable"]["thread_id"]

    await _persist_new_messages(state, config)

    last_message = state["messages"][-1]

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

    # The graph passes the final state; we just need to persist from it.
    await _persist_new_messages(state, config)

    logger.info("sync_to_postgres.complete", thread_id=thread_id)
    return {}