from arq import ArqRedis
from arq.connections import RedisSettings
import uuid
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langchain_core.messages import ToolMessage, SystemMessage, BaseMessage
from langchain.load.dump import dumpd # <-- IMPORT THE CORRECT SERIALIZER

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
    ctx, tool_name: str, tool_args: dict, thread_id: str, tool_call_id: str
):
    """Executes a tool and updates the graph state with the result."""
    arq_pool: ArqRedis = ctx["redis"]
    logger.info("run_tool.start", tool=tool_name, thread_id=thread_id)

    tool_function = TOOL_REGISTRY.get(tool_name)
    if not tool_function:
        result = f"Error: Tool '{tool_name}' not found."
        logger.warning("run_tool.not_found", tool=tool_name)
    else:
        try:
            result = tool_function.invoke(tool_args)
        except Exception as e:
            result = f"Error executing tool '{tool_name}': {e}"
            logger.error("run_tool.error", tool=tool_name, error=str(e))

    message = ToolMessage(
        content=str(result), name=tool_name, tool_call_id=tool_call_id
    )
    message.id = str(uuid.uuid4())

    config = {"configurable": {"thread_id": thread_id}}
    async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpoint:
        current_checkpoint = await checkpoint.aget(config)
        if not current_checkpoint:
            logger.error("run_tool.checkpoint_not_found", thread_id=thread_id)
            return

        # ROBUSTNESS FIX: Use dumpd for correct LangChain serialization
        serialized_message = dumpd(message)
        current_checkpoint["channel_values"]["messages"].append(serialized_message)
        
        await checkpoint.aput(config, current_checkpoint)
        logger.info("run_tool.checkpoint_updated", thread_id=thread_id)

    await arq_pool.enqueue_job(
        "continue_turn", thread_id=thread_id, _queue_name="orchestrator_queue"
    )
    logger.info("run_tool.enqueued", thread_id=thread_id)


async def run_agent_llm(
    ctx, alias: str, messages_dict: list, group_members_dict: list, thread_id: str
):
    """Runs an agent's LLM, updates state, and continues the orchestration."""
    arq_pool: ArqRedis = ctx["redis"]
    logger.info("run_agent.start", alias=alias, thread_id=thread_id)

    messages = deserialize_messages(messages_dict)
    group_members = [GroupMemberRead.model_validate(gm) for gm in group_members_dict]

    response = await run_agent(messages, group_members, alias)
    response.id = str(uuid.uuid4())

    config = {"configurable": {"thread_id": thread_id}}
    async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpoint:
        current_checkpoint = await checkpoint.aget(config)
        if not current_checkpoint:
            logger.error("run_agent_llm.checkpoint_not_found", thread_id=thread_id)
            return

        # ROBUSTNESS FIX: Use dumpd for correct LangChain serialization
        serialized_message = dumpd(response)
        current_checkpoint["channel_values"]["messages"].append(serialized_message)

        await checkpoint.aput(config, current_checkpoint)
        logger.info("run_agent_llm.checkpoint_updated", thread_id=thread_id)

    await arq_pool.enqueue_job("continue_turn", thread_id=thread_id, _queue_name="orchestrator_queue")
    logger.info("run_agent.enqueued", alias=alias, thread_id=thread_id)


class WorkerSettings:
    functions = [run_tool, run_agent_llm]
    queue_name = "execution_queue"
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    async def on_startup(ctx):
        logger.info("worker.startup", redis_host=settings.REDIS_URL)
        async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
            await checkpointer.asetup()
        logger.info("worker.startup.checkpointer_ready")

    async def on_shutdown(ctx):
        logger.info("worker.shutdown")