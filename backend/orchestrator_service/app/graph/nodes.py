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

GATHER_KEY_PREFIX = "synapse:gather"
GATHER_TIMEOUT_SECONDS = 300


async def _persist_new_messages(state: GraphState) -> dict:
    logger.debug("_persist_new_messages.entry", group_id=state.get("group_id"), turn_id=state.get("turn_id"), current_last_saved_index=state.get("last_saved_index", 0), messages_in_state_count=len(state.get("messages", [])))
    last_saved = state.get("last_saved_index", 0)
    new_messages_to_persist = state["messages"][last_saved:]

    if not new_messages_to_persist:
        logger.debug("_persist_new_messages.no_new_messages_to_persist", group_id=state.get("group_id"), turn_id=state.get("turn_id"))
        return {}

    redis_client = None
    persisted_message_ids = []
    try:
        async with AsyncSessionLocal() as session:
            redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=False)
            for lc_msg_idx, lc_msg in enumerate(new_messages_to_persist):
                message_id_to_save = getattr(lc_msg, "id", None)
                if not message_id_to_save:
                    message_id_to_save = uuid.uuid4()
                    logger.warn(
                        "_persist_new_messages.missing_lc_msg_id",
                        sender_alias=getattr(lc_msg, "name", "system"),
                        assigned_id=str(message_id_to_save),
                        message_content_snippet=str(lc_msg.content)[:50] + "..." if lc_msg.content else "N/A",
                        message_type=type(lc_msg).__name__,
                        group_id=state.get("group_id"), turn_id=state.get("turn_id")
                    )

                sender_alias = getattr(lc_msg, "name", "system")
                content_value = lc_msg.content
                if not isinstance(content_value, str):
                    logger.warn("_persist_new_messages.content_not_string_before_save", type=type(content_value).__name__, msg_id=str(message_id_to_save))
                    content_value = str(content_value)

                db_message_values = {
                    "id": message_id_to_save,
                    "group_id": state["group_id"],
                    "turn_id": state["turn_id"],
                    "sender_alias": sender_alias,
                    "content": content_value,
                    "meta": lc_msg.model_dump(),
                }
                if hasattr(lc_msg, "parent_message_id") and lc_msg.parent_message_id:
                    db_message_values["parent_message_id"] = lc_msg.parent_message_id

                logger.debug(
                    "_persist_new_messages.persisting_message_to_db",
                    msg_idx_in_batch=lc_msg_idx,
                    total_in_batch=len(new_messages_to_persist),
                    message_id=str(message_id_to_save),
                    sender=sender_alias,
                    group_id=state.get("group_id"), turn_id=state.get("turn_id")
                )
                stmt = (
                    insert(Message)
                    .values(**db_message_values)
                    .on_conflict_do_nothing(index_elements=["id"])
                )
                await session.execute(stmt)
                persisted_message_ids.append(str(message_id_to_save))

                broadcast_timestamp_iso = datetime.now(timezone.utc).isoformat()
                broadcast_message_payload = {
                    "id": str(message_id_to_save),
                    "sender_alias": db_message_values["sender_alias"],
                    "content": db_message_values["content"], # Already ensured string
                    "turn_id": str(state["turn_id"]),
                    "timestamp": broadcast_timestamp_iso,
                    "meta": db_message_values["meta"],
                }
                if "parent_message_id" in db_message_values:
                    broadcast_message_payload["parent_message_id"] = str(
                        db_message_values["parent_message_id"]
                    )
                
                logger.debug(
                    "_persist_new_messages.broadcasting_to_redis",
                    channel=f"group:{state['group_id']}",
                    message_id=str(message_id_to_save),
                    sender=broadcast_message_payload["sender_alias"],
                    group_id=state.get("group_id"), turn_id=state.get("turn_id")
                )
                await redis_client.publish(
                    f"group:{state['group_id']}",
                    json.dumps(broadcast_message_payload),
                )
            await session.commit()
            logger.info(
                "_persist_new_messages.batch_success",
                count=len(new_messages_to_persist),
                group_id=state["group_id"],
                turn_id=state["turn_id"],
                persisted_ids=persisted_message_ids
            )
    except Exception as e:
        logger.error(
            "_persist_new_messages.error",
            group_id=state["group_id"],
            turn_id=state["turn_id"],
            error=str(e),
            exc_info=True,
        )
        # Rollback is handled by AsyncSessionLocal context manager if exception propagates
        raise
    finally:
        if redis_client:
            await redis_client.close()

    updated_last_saved_index = last_saved + len(new_messages_to_persist)
    logger.debug("_persist_new_messages.exit", group_id=state.get("group_id"), turn_id=state.get("turn_id"), updated_last_saved_index=updated_last_saved_index)
    return {"last_saved_index": updated_last_saved_index}


async def router_node(state: GraphState, config: dict) -> dict:
    logger.info(
        "router_node.entry",
        turn_id=state.get("turn_id"),
        group_id=state.get("group_id"),
        messages_count=len(state.get("messages", [])),
        last_saved_index=state.get("last_saved_index"),
        current_next_actors=state.get("next_actors"),
        thread_id=config.get("configurable", {}).get("thread_id") # thread_id is group_id
    )
    
    persistence_update = await _persist_new_messages(state)
    
    # Create a temporary state that includes the updates from persistence,
    # especially if route_logic might depend on last_saved_index.
    # However, LangGraph merges returned dicts. If route_logic needs the *absolute latest* state
    # *after* persistence for its own logic (which it currently doesn't seem to for last_saved_index),
    # this would need a more complex flow or direct state mutation (which is bad).
    # For now, route_logic uses the state as it entered the node.
    # state_after_persistence = {**state, **persistence_update} # For logging or if needed
    # logger.debug("router_node.state_after_persistence_for_routing", state_summary_after_persistence={"last_saved_index": state_after_persistence.get("last_saved_index")})

    routing_update = route_logic(state) # Pass original state as route_logic primarily uses messages list
    
    combined_update = {**persistence_update, **routing_update}
    logger.info(
        "router_node.exit", turn_id=state.get("turn_id"), group_id=state.get("group_id"), updates_made=combined_update
    )
    return combined_update


async def dispatcher_node(state: GraphState, config: dict) -> dict:
    configurable_config = config.get("configurable", {})
    arq_pool = configurable_config.get("arq_pool")
    thread_id = configurable_config.get("thread_id")

    logger.info(
        "dispatcher_node.entry", turn_id=state.get("turn_id"), group_id=state.get("group_id"), thread_id=thread_id,
        next_actors_from_state=state.get("next_actors"),
        last_message_type=type(state["messages"][-1]).__name__ if state["messages"] else "N/A",
        last_message_sender=getattr(state["messages"][-1], "name", "N/A") if state["messages"] else "N/A",
        last_message_content_snippet=str(state["messages"][-1].content)[:50]+"..." if state["messages"] else "N/A",
        last_message_tool_calls=getattr(state["messages"][-1], "tool_calls", None) if state["messages"] else None
    )

    if not arq_pool or not thread_id:
        logger.error(
            "dispatcher_node.missing_config",
            arq_pool_present=bool(arq_pool),
            thread_id_present=bool(thread_id),
            turn_id=state.get("turn_id"), group_id=state.get("group_id")
        )
        raise ValueError("arq_pool or thread_id missing from runtime configuration for dispatcher_node.")

    last_message = state["messages"][-1]
    gathering_id = None
    dispatched_jobs_count = 0

    if tool_calls := getattr(last_message, "tool_calls", []):
        logger.info("dispatcher_node.processing_tool_calls", tool_calls=tool_calls, group_id=state.get("group_id"), turn_id=state.get("turn_id"))
        for call_idx, call in enumerate(tool_calls):
            logger.info(
                "dispatcher_node.dispatching_tool_call",
                tool_name=call["name"],
                tool_args=call["args"],
                tool_call_id=call["id"],
                thread_id=thread_id,
                call_index=call_idx,
                total_tool_calls=len(tool_calls)
            )
            await arq_pool.enqueue_job(
                "run_tool",
                tool_name=call["name"],
                tool_args=call["args"],
                tool_call_id=call["id"],
                thread_id=thread_id,
                gathering_id=None,
                _queue_name="execution_queue",
            )
            dispatched_jobs_count += 1
    elif next_actors := state.get("next_actors"):
        if not next_actors:
            logger.info("dispatcher_node.no_next_actors_to_dispatch", thread_id=thread_id, group_id=state.get("group_id"), turn_id=state.get("turn_id"))
            return {}

        logger.info("dispatcher_node.processing_next_actors", next_actors=next_actors, group_id=state.get("group_id"), turn_id=state.get("turn_id"))
        
        # Serialize messages and members once for all dispatches in this batch
        messages_dict = serialize_messages(state["messages"])
        group_members_dict = [gm.model_dump() for gm in state["group_members"]]
        logger.debug("dispatcher_node.serialized_data_for_dispatch", messages_count=len(messages_dict), members_count=len(group_members_dict))

        if len(next_actors) > 1:
            gathering_id = str(uuid.uuid4())
            gather_hash_key = f"{GATHER_KEY_PREFIX}:{gathering_id}"
            await arq_pool.hmset(gather_hash_key, {"expected": len(next_actors), "received": 0}) # Init received to 0
            await arq_pool.expire(gather_hash_key, GATHER_TIMEOUT_SECONDS)
            logger.info(
                "dispatcher_node.setup_collector_for_parallel_dispatch",
                gathering_id=gathering_id,
                expected_count=len(next_actors),
                thread_id=thread_id,
                gather_hash_key=gather_hash_key
            )
        else:
            logger.info("dispatcher_node.single_actor_dispatch", actor=next_actors[0], thread_id=thread_id)

        for actor_idx, alias in enumerate(next_actors):
            logger.info(
                "dispatcher_node.dispatching_agent_llm",
                alias=alias,
                thread_id=thread_id,
                gathering_id=gathering_id,
                actor_index=actor_idx,
                total_actors_to_dispatch=len(next_actors)
            )
            await arq_pool.enqueue_job(
                "run_agent_llm",
                alias=alias,
                messages_dict=messages_dict,
                group_members_dict=group_members_dict,
                thread_id=thread_id,
                gathering_id=gathering_id,
                _queue_name="execution_queue",
            )
            dispatched_jobs_count += 1
    else:
        logger.info(
            "dispatcher_node.no_tool_calls_and_no_next_actors_list", thread_id=thread_id, group_id=state.get("group_id"), turn_id=state.get("turn_id")
        )

    logger.info(
        "dispatcher_node.exit", turn_id=state.get("turn_id"), group_id=state.get("group_id"), thread_id=thread_id, dispatched_jobs_count=dispatched_jobs_count, final_gathering_id_used=gathering_id
    )
    return {}


async def sync_to_postgres_node(state: GraphState, config: dict) -> dict:
    thread_id = config.get("configurable", {}).get("thread_id")
    logger.info(
        "sync_to_postgres_node.entry",
        thread_id=thread_id,
        turn_id=state.get("turn_id"),
        group_id=state.get("group_id"),
        messages_count=len(state.get("messages", [])),
        last_saved_index=state.get("last_saved_index")
    )
    persistence_update = await _persist_new_messages(state)
    logger.info(
        "sync_to_postgres_node.exit",
        thread_id=thread_id,
        turn_id=state.get("turn_id"),
        group_id=state.get("group_id"),
        updates_made=persistence_update
    )
    return persistence_update