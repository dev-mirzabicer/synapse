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


async def _persist_new_messages(state: GraphState) -> None:
    """
    Persists any new messages from the state to the application's database
    (Postgres) and broadcasts them over a Redis pub/sub channel.
    
    This function NO LONGER interacts with the LangGraph checkpointer.
    """
    last_saved = state.get("last_saved_index", 0)
    new_messages = state["messages"][last_saved:]
    if not new_messages:
        return

    async with AsyncSessionLocal() as session:
        # Use a single Redis client for all publications in this scope
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
                # Broadcast the message for real-time updates
                await redis.publish(
                    f"group:{state['group_id']}",
                    json.dumps(msg.dict()),
                )
            await session.commit()
            logger.info("persist_new_messages.success", count=len(new_messages))
        except Exception as e:
            logger.error("persist_new_messages.error", error=str(e))
            await session.rollback()
        finally:
            await redis.close()


async def dispatch_node(state: GraphState, config: dict) -> dict:
    """
    A node that persists new messages and then dispatches jobs to execution
    workers. It updates the graph state by returning the new last_saved_index.
    """
    configurable_config = config.get("configurable", {})
    arq_pool = configurable_config.get("arq_pool")
    thread_id = configurable_config.get("thread_id")

    if not arq_pool or not thread_id:
        raise ValueError("arq_pool or thread_id missing from runtime configuration.")

    # 1. Perform the side-effect of persisting messages
    await _persist_new_messages(state)

    # 2. Prepare state updates and actions
    last_saved = state.get("last_saved_index", 0)
    new_index = last_saved + len(state["messages"][last_saved:])
    last_message = state["messages"][-1]

    # 3. Enqueue jobs for workers
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
            
    # 4. CORRECT: Return the state update for LangGraph to handle.
    return {"last_saved_index": new_index}


async def sync_to_postgres_node(state: GraphState, config: dict) -> dict:
    """
    A terminal node that ensures any final messages are persisted before
    the graph finishes. It returns the final state update.
    """
    configurable_config = config.get("configurable", {})
    thread_id = configurable_config.get("thread_id")
    logger.info("sync_to_postgres.start", thread_id=thread_id)

    # 1. Persist any final messages
    await _persist_new_messages(state)

    # 2. Calculate the final index
    last_saved = state.get("last_saved_index", 0)
    new_index = last_saved + len(state["messages"][last_saved:])

    logger.info("sync_to_postgres.complete", thread_id=thread_id)
    
    # 3. CORRECT: Return the final state update.
    return {"last_saved_index": new_index}