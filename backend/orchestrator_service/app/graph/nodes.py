import json
import uuid
from datetime import datetime, timezone
from redis.asyncio import Redis
from .state import GraphState
from shared.app.utils.message_serde import serialize_messages
from shared.app.db import AsyncSessionLocal
from shared.app.models.chat import Message
from sqlalchemy.dialects.postgresql import insert
from shared.app.core.config import settings
import structlog
from shared.app.core.logging import setup_logging
from .router import route_logic

setup_logging()
logger = structlog.get_logger(__name__)

# --- Constants from worker.py for Redis keys ---
GATHER_KEY_PREFIX = "synapse:gather"
GATHER_TIMEOUT_SECONDS = 300  # 5 minutes


async def _persist_new_messages(state: GraphState) -> dict:
    """
    Persists any new messages from the state to the application's database
    and publishes them to Redis for real-time client updates.
    Returns a dictionary with the updated message index.
    """
    last_saved = state.get("last_saved_index", 0)
    new_messages_to_persist = state["messages"][last_saved:]
    if not new_messages_to_persist:
        return {}

    async with AsyncSessionLocal() as session:
        redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=False)
        try:
            for lc_msg in new_messages_to_persist:
                message_id_to_save = getattr(lc_msg, "id", None)
                if not message_id_to_save:
                    message_id_to_save = uuid.uuid4()
                    logger.warn(
                        "persist_new_messages.missing_lc_msg_id",
                        sender_alias=getattr(lc_msg, "name", "system"),
                        assigned_id=str(message_id_to_save),
                    )

                db_message_values = {
                    "id": message_id_to_save,
                    "group_id": state["group_id"],
                    "turn_id": state["turn_id"],
                    "sender_alias": getattr(lc_msg, "name", "system"),
                    "content": str(lc_msg.content),
                    "meta": lc_msg.model_dump(),
                }
                if hasattr(lc_msg, "parent_message_id") and lc_msg.parent_message_id:
                    db_message_values["parent_message_id"] = lc_msg.parent_message_id

                stmt = (
                    insert(Message)
                    .values(**db_message_values)
                    .on_conflict_do_nothing(index_elements=["id"])
                )
                await session.execute(stmt)

                broadcast_timestamp_iso = datetime.now(timezone.utc).isoformat()
                broadcast_message_payload = {
                    "id": str(message_id_to_save),
                    "sender_alias": db_message_values["sender_alias"],
                    "content": db_message_values["content"],
                    "turn_id": str(state["turn_id"]),
                    "timestamp": broadcast_timestamp_iso,
                    "meta": db_message_values["meta"],
                }
                if "parent_message_id" in db_message_values:
                    broadcast_message_payload["parent_message_id"] = str(
                        db_message_values["parent_message_id"]
                    )

                await redis_client.publish(
                    f"group:{state['group_id']}",
                    json.dumps(broadcast_message_payload),
                )
            await session.commit()
            logger.info(
                "persist_new_messages.success",
                count=len(new_messages_to_persist),
                group_id=state["group_id"],
            )
        except Exception as e:
            logger.error(
                "persist_new_messages.error",
                group_id=state["group_id"],
                error=str(e),
                exc_info=True,
            )
            await session.rollback()
            raise
        finally:
            await redis_client.close()

    return {"last_saved_index": last_saved + len(new_messages_to_persist)}


async def router_node(state: GraphState, config: dict) -> dict:
    """
    Persists new messages and then runs routing logic to determine the next step.
    """
    logger.debug(
        "router_node.start",
        turn_id=state.get("turn_id"),
        messages_count=len(state.get("messages", [])),
    )
    persistence_update = await _persist_new_messages(state)
    routing_update = route_logic(state)
    combined_update = {**persistence_update, **routing_update}
    logger.debug(
        "router_node.end", turn_id=state.get("turn_id"), updates=combined_update
    )
    return combined_update


async def dispatcher_node(state: GraphState, config: dict) -> dict:
    """
    Reads the state and dispatches jobs to execution workers.
    Sets up a "collector" if dispatching to multiple agents.
    """
    configurable_config = config.get("configurable", {})
    arq_pool = configurable_config.get("arq_pool")
    thread_id = configurable_config.get("thread_id")

    logger.debug(
        "dispatcher_node.start", turn_id=state.get("turn_id"), thread_id=thread_id
    )

    if not arq_pool or not thread_id:
        logger.error(
            "dispatcher_node.missing_config",
            arq_pool_present=bool(arq_pool),
            thread_id_present=bool(thread_id),
        )
        raise ValueError("arq_pool or thread_id missing from runtime configuration.")

    last_message = state["messages"][-1]
    gathering_id = None

    if tool_calls := getattr(last_message, "tool_calls", []):
        # Tool calls are handled one by one, no collector needed.
        for call in tool_calls:
            logger.info(
                "dispatcher_node.dispatch_tool_call",
                tool_name=call["name"],
                tool_call_id=call["id"],
                thread_id=thread_id,
            )
            await arq_pool.enqueue_job(
                "run_tool",
                tool_name=call["name"],
                tool_args=call["args"],
                tool_call_id=call["id"],
                thread_id=thread_id,
                gathering_id=None,  # Explicitly no gathering for tools
                _queue_name="execution_queue",
            )
    elif next_actors := state.get("next_actors"):
        if not next_actors:
            logger.info("dispatcher_node.no_next_actors", thread_id=thread_id)
            return {}

        messages_dict = serialize_messages(state["messages"])
        group_members_dict = [gm.model_dump() for gm in state["group_members"]]

        # --- Collector Setup for Parallel Dispatch ---
        if len(next_actors) > 1:
            gathering_id = str(uuid.uuid4())
            gather_hash_key = f"{GATHER_KEY_PREFIX}:{gathering_id}"
            await arq_pool.hset(gather_hash_key, "expected", len(next_actors))
            await arq_pool.expire(gather_hash_key, GATHER_TIMEOUT_SECONDS)
            logger.info(
                "dispatcher_node.setup_collector",
                gathering_id=gathering_id,
                expected_count=len(next_actors),
            )

        for alias in next_actors:
            logger.info(
                "dispatcher_node.dispatch_agent_llm",
                alias=alias,
                thread_id=thread_id,
                gathering_id=gathering_id,
            )
            await arq_pool.enqueue_job(
                "run_agent_llm",
                alias=alias,
                messages_dict=messages_dict,
                group_members_dict=group_members_dict,
                thread_id=thread_id,
                gathering_id=gathering_id,  # Pass the ID for collection
                _queue_name="execution_queue",
            )
    else:
        logger.info(
            "dispatcher_node.no_tool_calls_or_next_actors", thread_id=thread_id
        )

    logger.debug(
        "dispatcher_node.end", turn_id=state.get("turn_id"), thread_id=thread_id
    )
    return {}


async def sync_to_postgres_node(state: GraphState, config: dict) -> dict:
    """
    A terminal node that ensures any final messages are persisted.
    """
    thread_id = config.get("configurable", {}).get("thread_id")
    logger.info(
        "sync_to_postgres_node.start",
        thread_id=thread_id,
        turn_id=state.get("turn_id"),
    )
    persistence_update = await _persist_new_messages(state)
    logger.info(
        "sync_to_postgres_node.complete",
        thread_id=thread_id,
        turn_id=state.get("turn_id"),
    )
    return persistence_update