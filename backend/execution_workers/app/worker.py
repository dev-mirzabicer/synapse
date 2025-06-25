from arq import ArqRedis
from arq.connections import RedisSettings
import uuid
from langchain.load.dump import dumpd
from langchain_core.messages import ToolMessage, SystemMessage, BaseMessage

import structlog

from shared.app.core.config import settings
from shared.app.core.logging import setup_logging
from shared.app.agents.tools import TOOL_REGISTRY
from shared.app.agents.runner import run_agent
from shared.app.schemas.groups import GroupMemberRead
from shared.app.utils.message_serde import deserialize_messages

setup_logging()
logger = structlog.get_logger(__name__)


async def run_tool(
    ctx,
    tool_name: str,
    tool_args: dict,
    thread_id: str,
    tool_call_id: str,
    gathering_id: str | None = None, # Expected to be None
):
    arq_pool: ArqRedis = ctx["redis"]
    logger.info(
        "run_tool.entry",
        tool_name=tool_name,
        tool_args_preview=str(tool_args)[:100]+"...",
        thread_id=thread_id, # group_id
        tool_call_id=tool_call_id,
        gathering_id=gathering_id 
    )

    tool_function = TOOL_REGISTRY.get(tool_name)
    tool_run_result_content: str

    if not tool_function:
        tool_run_result_content = f"Error: Tool '{tool_name}' not found in TOOL_REGISTRY."
        logger.error("run_tool.tool_not_found", tool_name=tool_name, thread_id=thread_id, tool_call_id=tool_call_id)
    else:
        try:
            raw_tool_output = await tool_function.ainvoke(tool_args)
            tool_run_result_content = str(raw_tool_output)
            logger.info("run_tool.execution_success", tool_name=tool_name, thread_id=thread_id, tool_call_id=tool_call_id, result_preview=tool_run_result_content[:100]+"...")
        except Exception as e:
            tool_run_result_content = f"Error executing tool '{tool_name}': {str(e)}"
            logger.error("run_tool.execution_error", tool_name=tool_name, thread_id=thread_id, tool_call_id=tool_call_id, error=str(e), exc_info=True)

    tool_message = ToolMessage(
        content=tool_run_result_content,
        name=tool_name, 
        tool_call_id=tool_call_id 
    )
    
    original_toolmsg_id = getattr(tool_message, 'id', None)
    new_app_id = str(uuid.uuid4())
    tool_message.id = new_app_id
    if original_toolmsg_id and original_toolmsg_id != new_app_id:
         logger.debug(
            "run_tool.overwrote_toolmessage_default_id",
            tool_name=tool_name,
            original_id=original_toolmsg_id,
            assigned_app_id=new_app_id,
            thread_id=thread_id
        )
    else:
        logger.debug(
            "run_tool.assigned_app_id_to_tool_message",
            tool_name=tool_name,
            message_id=new_app_id,
            thread_id=thread_id
        )
    
    logger.debug(
        "run_tool.constructed_tool_message", 
        message_id=tool_message.id,
        tool_name=tool_message.name, 
        tool_call_id=tool_message.tool_call_id, 
        content_snippet=tool_message.content[:50]+"...",
        thread_id=thread_id
    )

    serialized_message_dict = dumpd(tool_message)
    logger.debug("run_tool.serialized_tool_message_dict_preview", preview=str(serialized_message_dict)[:200]+"...", thread_id=thread_id)

    await arq_pool.enqueue_job(
        "process_worker_result",
        thread_id=thread_id,
        message_dict=serialized_message_dict,
        gathering_id=gathering_id, 
        _queue_name="orchestrator_queue",
    )
    logger.info(
        "run_tool.enqueued_result_to_orchestrator",
        thread_id=thread_id, tool_name=tool_name, tool_call_id=tool_call_id, enqueued_message_id=tool_message.id
    )


async def run_agent_llm(
    ctx,
    alias: str,
    messages_dict: list,
    group_members_dict: list,
    thread_id: str,
    gathering_id: str | None = None,
):
    arq_pool: ArqRedis = ctx["redis"]
    logger.info(
        "run_agent_llm.entry",
        alias=alias, thread_id=thread_id, gathering_id=gathering_id,
        num_messages_received=len(messages_dict),
        num_group_members_received=len(group_members_dict)
    )
    logger.debug("run_agent_llm.received_messages_dict_preview", alias=alias, thread_id=thread_id, messages_preview=[str(m)[:100]+"..." for m in messages_dict[:3]])
    logger.debug("run_agent_llm.received_group_members_dict_preview", alias=alias, thread_id=thread_id, member_aliases=[gm.get('alias') for gm in group_members_dict])

    agent_response_message: BaseMessage # Define type
    try:
        deserialized_messages: list[BaseMessage] = deserialize_messages(messages_dict)
        logger.debug("run_agent_llm.deserialized_messages_for_agent", alias=alias, thread_id=thread_id, count=len(deserialized_messages), types=[type(m).__name__ for m in deserialized_messages[:3]])
        
        deserialized_group_members: list[GroupMemberRead] = [GroupMemberRead.model_validate(gm) for gm in group_members_dict]
        logger.debug("run_agent_llm.deserialized_group_members_for_agent", alias=alias, thread_id=thread_id, count=len(deserialized_group_members), member_aliases=[gm.alias for gm in deserialized_group_members])

        agent_response_message = await run_agent(deserialized_messages, deserialized_group_members, alias)
    
    except Exception as e: # Catch errors during deserialization or if run_agent itself raises an unexpected one
        logger.error("run_agent_llm.agent_execution_pipeline_error", alias=alias, thread_id=thread_id, error=str(e), exc_info=True)
        agent_response_message = SystemMessage(
            content=f"Agent '{alias}' failed during execution pipeline: {str(e)}",
            name="system_error"
        )
        # Fallthrough to ensure agent_response_message is set for serialization and enqueueing

    if not getattr(agent_response_message, 'id', None): # Ensure ID, run_agent should do this
        agent_response_message.id = str(uuid.uuid4())
        logger.warn("run_agent_llm.agent_response_missing_id_post_run_agent", alias=alias, thread_id=thread_id, assigned_id=agent_response_message.id, response_type=type(agent_response_message).__name__)

    logger.info(
        "run_agent_llm.agent_run_completed_or_errored",
        alias=alias, thread_id=thread_id,
        response_message_id=agent_response_message.id,
        response_message_type=type(agent_response_message).__name__,
        response_sender_name=getattr(agent_response_message, 'name', 'N/A'), # run_agent sets this
        response_content_snippet=str(agent_response_message.content)[:100]+"..."
    )

    serialized_response_dict = dumpd(agent_response_message)
    logger.debug("run_agent_llm.serialized_agent_response_dict_preview", alias=alias, thread_id=thread_id, preview=str(serialized_response_dict)[:200]+"...")

    await arq_pool.enqueue_job(
        "process_worker_result",
        thread_id=thread_id,
        message_dict=serialized_response_dict,
        gathering_id=gathering_id,
        _queue_name="orchestrator_queue",
    )
    logger.info(
        "run_agent_llm.enqueued_agent_response_to_orchestrator",
        alias=alias, thread_id=thread_id, enqueued_message_id=agent_response_message.id
    )


class WorkerSettings:
    functions = [run_tool, run_agent_llm]
    queue_name = "execution_queue"
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    async def on_startup(ctx):
        logger.info("execution_worker.startup", redis_host=str(WorkerSettings.redis_settings.host), queue_name=WorkerSettings.queue_name, functions_registered=len(WorkerSettings.functions))

    async def on_shutdown(ctx):
        logger.info("execution_worker.shutdown", queue_name=WorkerSettings.queue_name)