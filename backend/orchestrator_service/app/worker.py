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
from shared.app.utils.message_serde import deserialize_messages, serialize_messages

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
            members_schema = []
        else:
            members_schema = [GroupMemberRead.model_validate(m) for m in members_orm]
        
        logger.debug("start_turn.loaded_group_members", group_id=group_id, turn_id=turn_id, member_aliases=[m.alias for m in members_schema], member_count=len(members_schema))

    user_msg = HumanMessage(content=message_content)
    user_msg.id = message_id 
    user_msg.name = "User"
    # Add turn_id to additional_kwargs for logging traceability in run_agent
    user_msg.additional_kwargs["turn_id"] = turn_id

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
    sender_alias_log = message_dict.get("kwargs", {}).get("name", "N/A")
    message_id_log = message_dict.get("kwargs", {}).get("id", "N/A")
    
    logger.info(
        "process_worker_result.entry",
        thread_id=thread_id,
        message_sender_alias=sender_alias_log,
        message_id_approx=message_id_log,
        gathering_id=gathering_id,
    )

    if not gathering_id:
        logger.info("process_worker_result.handling_single_dispatch_result", thread_id=thread_id, message_id_approx=message_id_log)
        await update_graph_with_messages(
            ctx, thread_id=thread_id, messages_dict_list=[message_dict]
        )
        return

    arq_pool: ArqRedis = ctx["redis"]
    gather_hash_key = f"{GATHER_KEY_PREFIX}:{gathering_id}"
    gather_list_key = f"{gather_hash_key}:messages"
    
    serialized_for_redis_list = json.dumps(message_dict)
    received_count = await arq_pool.hincrby(gather_hash_key, "received", 1)
    await arq_pool.rpush(gather_list_key, serialized_for_redis_list)
    
    expected_count_str = await arq_pool.hget(gather_hash_key, "expected")
    if not expected_count_str:
        logger.error("process_worker_result.collector_missing_expected_count", gathering_id=gathering_id, thread_id=thread_id)
        return

    expected_count = int(expected_count_str)
    logger.info(
        "process_worker_result.collection_status_update",
        gathering_id=gathering_id, thread_id=thread_id,
        received_now=received_count, expected=expected_count,
        sender_of_this_message=sender_alias_log,
    )

    if received_count >= expected_count:
        lock_acquired = await arq_pool.hsetnx(gather_hash_key, "processing_lock", "1")

        if not lock_acquired:
            logger.info(
                "process_worker_result.collection_already_locked",
                gathering_id=gathering_id,
                thread_id=thread_id,
                action="Another worker is handling this batch. Backing off.",
            )
            return

        logger.info(
            "process_worker_result.collection_complete_and_lock_acquired",
            gathering_id=gathering_id, thread_id=thread_id,
        )

        pipe = arq_pool.pipeline()
        pipe.lrange(gather_list_key, 0, -1)
        pipe.delete(gather_list_key)
        pipe.delete(gather_hash_key)
        all_message_strs_from_redis, _, _ = await pipe.execute()

        if not all_message_strs_from_redis:
            logger.error("process_worker_result.collector_no_messages_retrieved", gathering_id=gathering_id, thread_id=thread_id)
            return

        all_messages_as_dicts = [json.loads(m_str) for m_str in all_message_strs_from_redis]
        await update_graph_with_messages(
            ctx, thread_id=thread_id, messages_dict_list=all_messages_as_dicts
        )


async def update_graph_with_messages(ctx, thread_id: str, messages_dict_list: list[dict]):
    sender_aliases_in_batch = [msg.get("kwargs", {}).get("name", "N/A") for msg in messages_dict_list]
    turn_id_for_log = "N/A" # Attempt to find a turn_id for logging

    logger.info(
        "update_graph_with_messages.entry",
        thread_id=thread_id,
        num_messages_to_add=len(messages_dict_list),
        sender_aliases_in_batch=sender_aliases_in_batch
    )

    arq_pool: ArqRedis = ctx["redis"]

    try:
        new_lc_messages: list[BaseMessage] = deserialize_messages(messages_dict_list)
        # Find turn_id from the first available message for logging
        for msg in new_lc_messages:
            if msg.additional_kwargs.get("turn_id"):
                turn_id_for_log = msg.additional_kwargs.get("turn_id")
                break
    except Exception as e:
        logger.error(
            "update_graph_with_messages.deserialization_error",
            thread_id=thread_id, error=str(e), exc_info=True
        )
        return

    # Add turn_id to all messages if it's missing, to ensure it propagates
    if turn_id_for_log != "N/A":
        for msg in new_lc_messages:
            if not msg.additional_kwargs.get("turn_id"):
                msg.additional_kwargs["turn_id"] = turn_id_for_log

    input_payload_for_graph = {"messages": new_lc_messages}
    
    logger.debug(
        "update_graph_with_messages.payload_for_graph",
        thread_id=thread_id,
        turn_id=turn_id_for_log,
        payload_messages=serialize_messages(new_lc_messages)
    )

    async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
        graph_app = workflow.compile(checkpointer=checkpointer)
        invocation_config = {
            "configurable": {
                "thread_id": thread_id,
                "arq_pool": arq_pool,
            }
        }
        logger.info("update_graph_with_messages.invoking_graph_app.ainvoke_to_continue", thread_id=thread_id, turn_id=turn_id_for_log)
        await graph_app.ainvoke(input_payload_for_graph, config=invocation_config)

    logger.info("update_graph_with_messages.graph_continue_invocation_complete", thread_id=thread_id, turn_id=turn_id_for_log)


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