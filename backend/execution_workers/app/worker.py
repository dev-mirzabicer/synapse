from arq import ArqRedis
from arq.connections import RedisSettings
import uuid
from langchain.load.dump import dumpd
from langchain_core.messages import ToolMessage, SystemMessage

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
    gathering_id: str | None = None,
):
    """Executes a tool and enqueues the result for the orchestrator's collector."""
    arq_pool: ArqRedis = ctx["redis"]
    logger.info("run_tool.start", tool=tool_name, thread_id=thread_id, gathering_id=gathering_id)

    tool_function = TOOL_REGISTRY.get(tool_name)
    if not tool_function:
        result = f"Error: Tool '{tool_name}' not found."
        logger.warning("run_tool.not_found", tool=tool_name)
    else:
        try:
            # Tools can be sync or async, ainvoke handles both.
            result = await tool_function.ainvoke(tool_args)
        except Exception as e:
            result = f"Error executing tool '{tool_name}': {e}"
            logger.error("run_tool.error", tool=tool_name, error=str(e), exc_info=True)

    message = ToolMessage(
        content=str(result), name=tool_name, tool_call_id=tool_call_id
    )
    message.id = str(uuid.uuid4())
    serialized_message = dumpd(message)

    # Enqueue the result message for the orchestrator's collector.
    await arq_pool.enqueue_job(
        "process_worker_result",  # NEW task name
        thread_id=thread_id,
        message_dict=serialized_message,
        gathering_id=gathering_id,  # Pass the gathering_id through
        _queue_name="orchestrator_queue",
    )
    logger.info("run_tool.enqueued_to_collector", thread_id=thread_id, tool_name=tool_name)


async def run_agent_llm(
    ctx,
    alias: str,
    messages_dict: list,
    group_members_dict: list,
    thread_id: str,
    gathering_id: str | None = None,
):
    """Runs an agent's LLM and enqueues the response for the orchestrator's collector."""
    arq_pool: ArqRedis = ctx["redis"]
    logger.info("run_agent.start", alias=alias, thread_id=thread_id, gathering_id=gathering_id)

    messages = deserialize_messages(messages_dict)
    group_members = [GroupMemberRead.model_validate(gm) for gm in group_members_dict]

    response = await run_agent(messages, group_members, alias)
    response.id = str(uuid.uuid4())

    serialized_message = dumpd(response)

    # Enqueue the agent's response for the orchestrator's collector.
    await arq_pool.enqueue_job(
        "process_worker_result",  # NEW task name
        thread_id=thread_id,
        message_dict=serialized_message,
        gathering_id=gathering_id,  # Pass the gathering_id through
        _queue_name="orchestrator_queue",
    )
    logger.info("run_agent.enqueued_to_collector", alias=alias, thread_id=thread_id)


class WorkerSettings:
    """ARQ worker settings for the execution workers."""

    functions = [run_tool, run_agent_llm]
    queue_name = "execution_queue"
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    async def on_startup(ctx):
        """Logs a startup message."""
        logger.info("worker.startup", redis_host=settings.REDIS_URL)

    async def on_shutdown(ctx):
        """Logs a clean shutdown message."""
        logger.info("worker.shutdown")