import json
import uuid
from redis.asyncio import Redis
from .state import GraphState
from shared.app.utils.message_serde import serialize_messages
from shared.app.db import AsyncSessionLocal
from shared.app.models.chat import Message
from sqlalchemy.dialects.postgresql import insert
from shared.app.core.config import settings
import structlog
from shared.app.core.logging import setup_logging
from .router import route_logic # Import the routing logic

setup_logging()
logger = structlog.get_logger(__name__)


async def _persist_new_messages(state: GraphState) -> dict:
    """
    Persists any new messages from the state to the application's database
    and returns a dictionary with the updated message index.
    """
    last_saved = state.get("last_saved_index", 0)
    new_messages = state["messages"][last_saved:]
    if not new_messages:
        return {}

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

                # Construct a dictionary that the frontend expects, including the sender_alias.
                broadcast_message = {
                    "id": str(getattr(msg, "id", uuid.uuid4())),
                    "sender_alias": getattr(msg, "name", "system"),
                    "content": str(msg.content),
                    "turn_id": str(state["turn_id"]),
                }

                await redis.publish(
                    f"group:{state['group_id']}",
                    json.dumps(broadcast_message),
                )
            await session.commit()
            logger.info("persist_new_messages.success", count=len(new_messages))
        except Exception as e:
            logger.error("persist_new_messages.error", error=str(e))
            await session.rollback()
            # --- FIX: Re-raise the exception to halt execution and fail the task ---
            raise
            # --- END FIX ---
        finally:
            await redis.close()
    
    return {"last_saved_index": last_saved + len(new_messages)}


async def router_node(state: GraphState, config: dict) -> dict:
    """
    This is the new primary node. It persists new messages and then runs
    the routing logic to determine the next step, updating the state accordingly.
    """
    # First, persist any new messages and get the updated index
    persistence_update = await _persist_new_messages(state)

    # Now, run the routing logic to get the state updates (e.g., next_actors)
    routing_update = route_logic(state)

    # Return the combined updates
    return {**persistence_update, **routing_update}


async def dispatcher_node(state: GraphState, config: dict) -> dict:
    """
    This node reads the state (updated by the router) and dispatches jobs
    to the appropriate execution workers.
    """
    configurable_config = config.get("configurable", {})
    arq_pool = configurable_config.get("arq_pool")
    thread_id = configurable_config.get("thread_id")

    if not arq_pool or not thread_id:
        raise ValueError("arq_pool or thread_id missing from runtime configuration.")

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
    # This node only performs side-effects (enqueuing jobs), it doesn't change the state.
    return {}


async def sync_to_postgres_node(state: GraphState, config: dict) -> dict:
    """
    A terminal node that ensures any final messages are persisted before
    the graph finishes its run.
    """
    thread_id = config.get("configurable", {}).get("thread_id")
    logger.info("sync_to_postgres.start", thread_id=thread_id)
    await _persist_new_messages(state)
    logger.info("sync_to_postgres.complete", thread_id=thread_id)
    return {}