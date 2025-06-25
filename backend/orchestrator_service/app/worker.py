import asyncio
import json
import structlog
from arq import ArqRedis
from arq.connections import RedisSettings
from langchain_core.messages import HumanMessage, BaseMessage
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from sqlalchemy import select
import uuid 

from graph.graph import workflow 
from shared.app.core.config import settings
from shared.app.core.logging import setup_logging
from shared.app.db import AsyncSessionLocal
from shared.app.models.chat import GroupMember
from shared.app.schemas.groups import GroupMemberRead
from shared.app.utils.message_serde import deserialize_messages

setup_logging()
logger = structlog.get_logger(__name__)

GATHER_KEY_PREFIX = "synapse:gather"
GATHER_TIMEOUT_SECONDS = 300


async def start_turn(
    ctx,
    group_id: str,
    message_content: str,
    user_id: str,
    message_id: str,
    turn_id: str,
):
    logger.info(
        "start_turn.initiated_by_user_message",
        group_id=group_id,
        user_id=user_id,
        user_message_id=message_id,
        turn_id=turn_id,
        message_content_snippet=message_content[:100]+"..."
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GroupMember).where(GroupMember.group_id == group_id)
        )
        members_orm = result.scalars().all()
        if not members_orm:
            logger.error("start_turn.no_group_members_found_in_db", group_id=group_id, turn_id=turn_id)
            # Consider how to handle this: raise error, or let graph handle empty members?
            # For now, log and continue, graph might handle it or fail.
            members_schema = []
        else:
            members_schema = [GroupMemberRead.model_validate(m) for m in members_orm]
        
        logger.debug("start_turn.loaded_group_members", group_id=group_id, turn_id=turn_id, member_aliases=[m.alias for m in members_schema], member_count=len(members_schema))

    user_msg = HumanMessage(content=message_content)
    user_msg.id = message_id 
    user_msg.name = "User"

    graph_input = {
        "messages": [user_msg],
        "group_id": group_id,
        "group_members": members_schema,
        "turn_count": 0,
        "last_saved_index": 0,
        "turn_id": turn_id,
    }
    logger.debug("start_turn.initial_graph_input", group_id=group_id, turn_id=turn_id, graph_input_details={"message_id": message_id, "turn_id": turn_id, "group_members_count": len(members_schema)})

    arq_pool: ArqRedis = ctx["redis"]

    async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
        graph_app = workflow.compile(checkpointer=checkpointer)
        invocation_config = {
            "configurable": {
                "thread_id": group_id, 
                "arq_pool": arq_pool,
            }
        }
        logger.info("start_turn.invoking_graph_app.ainvoke", group_id=group_id, turn_id=turn_id, thread_id_for_graph=group_id)
        await graph_app.ainvoke(graph_input, config=invocation_config)
    
    logger.info("start_turn.graph_invocation_complete", group_id=group_id, turn_id=turn_id)


async def process_worker_result(
    ctx, thread_id: str, message_dict: dict, gathering_id: str | None = None
):
    # Attempt to get sender from message_dict for logging
    sender_alias_log = "N/A"
    message_type_log = message_dict.get("type", "N/A")
    if message_type_log == "constructor" and "kwargs" in message_dict and "name" in message_dict["kwargs"]:
        sender_alias_log = message_dict["kwargs"]["name"]
    elif "name" in message_dict: # Fallback for other serialized formats if any
        sender_alias_log = message_dict["name"]
    
    message_id_log = "N/A"
    if message_type_log == "constructor" and "kwargs" in message_dict and "id" in message_dict["kwargs"] and message_dict["kwargs"]["id"]:
         message_id_log = str(message_dict["kwargs"]["id"][-1]) if isinstance(message_dict["kwargs"]["id"], list) else str(message_dict["kwargs"]["id"]) # Langchain id can be a list
    elif "id" in message_dict and message_dict["id"]: # Fallback
         message_id_log = str(message_dict["id"][-1]) if isinstance(message_dict["id"], list) else str(message_dict["id"])


    logger.info(
        "process_worker_result.entry",
        thread_id=thread_id,
        message_sender_alias=sender_alias_log,
        message_id_approx=message_id_log, # Approximate, as ID structure can vary
        message_type=message_type_log,
        gathering_id=gathering_id,
    )
    logger.debug("process_worker_result.received_message_dict_preview", thread_id=thread_id, message_dict_preview=str(message_dict)[:250]+"...")

    if not gathering_id:
        logger.info("process_worker_result.handling_single_dispatch_result", thread_id=thread_id, message_id_approx=message_id_log)
        await update_graph_with_messages(
            ctx, thread_id=thread_id, messages_dict_list=[message_dict]
        )
        return

    arq_pool: ArqRedis = ctx["redis"]
    gather_hash_key = f"{GATHER_KEY_PREFIX}:{gathering_id}"
    gather_list_key = f"{gather_hash_key}:messages"
    logger.debug("process_worker_result.collector_redis_keys", gather_hash_key=gather_hash_key, gather_list_key=gather_list_key, thread_id=thread_id)

    serialized_for_redis_list = json.dumps(message_dict)
    pipe = arq_pool.pipeline()
    pipe.rpush(gather_list_key, serialized_for_redis_list)
    pipe.hincrby(gather_hash_key, "received", 1)
    pipe.expire(gather_list_key, GATHER_TIMEOUT_SECONDS)
    pipe.expire(gather_hash_key, GATHER_TIMEOUT_SECONDS)
    
    _, received_count, _, _ = await pipe.execute() # list_len, received_count, expire_ok1, expire_ok2
    logger.debug(
        "process_worker_result.collector_pipeline_executed",
        gathering_id=gathering_id, thread_id=thread_id,
        current_received_count_from_hincrby=received_count
    )

    expected_count_str = await arq_pool.hget(gather_hash_key, "expected")
    if not expected_count_str:
        logger.error(
            "process_worker_result.collector_missing_expected_count_in_redis",
            gathering_id=gathering_id, thread_id=thread_id, gather_hash_key=gather_hash_key
        )
        logger.warn("process_worker_result.collector_failsafe_processing_single_message", gathering_id=gathering_id, thread_id=thread_id, message_id_approx=message_id_log)
        await update_graph_with_messages(
            ctx, thread_id=thread_id, messages_dict_list=[message_dict]
        )
        return

    expected_count = int(expected_count_str)
    logger.info(
        "process_worker_result.collection_status_update",
        gathering_id=gathering_id, thread_id=thread_id,
        received_now=received_count, expected=expected_count, message_id_approx=message_id_log
    )

    if received_count >= expected_count:
        logger.info(
            "process_worker_result.collection_complete_all_messages_received",
            gathering_id=gathering_id, thread_id=thread_id,
            received_count=received_count, expected_count=expected_count
        )

        pipe = arq_pool.pipeline()
        pipe.lrange(gather_list_key, 0, -1)
        pipe.delete(gather_list_key)
        pipe.delete(gather_hash_key)
        all_message_strs_from_redis, _, _ = await pipe.execute() # messages_list, del_ok1, del_ok2
        logger.debug(
            "process_worker_result.collector_cleanup_redis",
            gathering_id=gathering_id, thread_id=thread_id,
            retrieved_messages_count=len(all_message_strs_from_redis) if all_message_strs_from_redis else 0,
        )

        if not all_message_strs_from_redis:
            logger.error("process_worker_result.collector_no_messages_retrieved_from_list_after_completion_signal", gathering_id=gathering_id, thread_id=thread_id, gather_list_key=gather_list_key)
            return

        all_messages_as_dicts = [json.loads(m_str) for m_str in all_message_strs_from_redis]
        await update_graph_with_messages(
            ctx, thread_id=thread_id, messages_dict_list=all_messages_as_dicts
        )
    else:
        logger.info(
            "process_worker_result.collection_waiting_for_more_messages",
            gathering_id=gathering_id, thread_id=thread_id,
            received_so_far=received_count, expected_total=expected_count
        )


async def update_graph_with_messages(ctx, thread_id: str, messages_dict_list: list[dict]):
    sender_aliases_in_batch = []
    for msg_dict in messages_dict_list:
        alias = "N/A"
        msg_type = msg_dict.get("type", "N/A")
        if msg_type == "constructor" and "kwargs" in msg_dict and "name" in msg_dict["kwargs"]:
            alias = msg_dict["kwargs"]["name"]
        elif "name" in msg_dict:
            alias = msg_dict["name"]
        sender_aliases_in_batch.append(alias)

    logger.info(
        "update_graph_with_messages.entry",
        thread_id=thread_id,
        num_messages_to_add=len(messages_dict_list),
        sender_aliases_in_batch=sender_aliases_in_batch
    )
    logger.debug("update_graph_with_messages.messages_dict_list_preview", thread_id=thread_id, messages_preview=[str(m)[:100]+"..." for m in messages_dict_list])

    arq_pool: ArqRedis = ctx["redis"]

    try:
        new_lc_messages: list[BaseMessage] = deserialize_messages(messages_dict_list)
        message_ids_deserialized = [getattr(m, 'id', 'N/A') for m in new_lc_messages]
        logger.debug(
            "update_graph_with_messages.deserialized_lc_messages", 
            thread_id=thread_id, 
            deserialized_message_types=[type(m).__name__ for m in new_lc_messages], 
            deserialized_message_ids=message_ids_deserialized
        )
    except Exception as e:
        logger.error(
            "update_graph_with_messages.deserialization_error",
            thread_id=thread_id, error=str(e),
            messages_dict_list_problematic_preview=[str(m)[:100]+"..." for m in messages_dict_list],
            exc_info=True
        )
        return

    input_payload_for_graph = {"messages": new_lc_messages}
    logger.debug("update_graph_with_messages.input_payload_for_graph_ainvoke", thread_id=thread_id, payload_details={"messages_to_add_count": len(new_lc_messages), "first_message_id_to_add": message_ids_deserialized[0] if message_ids_deserialized else "N/A"})

    async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
        graph_app = workflow.compile(checkpointer=checkpointer)
        invocation_config = {
            "configurable": {
                "thread_id": thread_id,
                "arq_pool": arq_pool,
            }
        }
        logger.info("update_graph_with_messages.invoking_graph_app.ainvoke_to_continue", thread_id=thread_id)
        await graph_app.ainvoke(input_payload_for_graph, config=invocation_config)

    logger.info("update_graph_with_messages.graph_continue_invocation_complete", thread_id=thread_id)


class WorkerSettings:
    functions = [start_turn, process_worker_result]
    queue_name = "orchestrator_queue"
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    async def on_startup(ctx):
        logger.info("orchestrator_worker.startup", redis_host=str(WorkerSettings.redis_settings.host), queue_name=WorkerSettings.queue_name, functions_registered=len(WorkerSettings.functions))
        try:
            async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
                await checkpointer.asetup()
            logger.info("orchestrator_worker.startup.checkpointer_setup_verified")
        except Exception as e:
            logger.error("orchestrator_worker.startup.checkpointer_setup_failed", error=str(e), exc_info=True)

    async def on_shutdown(ctx):
        logger.info("orchestrator_worker.shutdown", queue_name=WorkerSettings.queue_name)