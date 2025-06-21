from arq import ArqRedis, create_pool
from langgraph.checkpoint.redis import RedisSaver
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

checkpoint = RedisSaver.from_conn_string(settings.REDIS_URL)


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

    await checkpoint.update_state(
        {"configurable": {"thread_id": thread_id}}, {"messages": [message]}
    )
    await arq_pool.enqueue_job("continue_turn", thread_id=thread_id)
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

    await checkpoint.update_state(
        {"configurable": {"thread_id": thread_id}}, {"messages": [response]}
    )
    await arq_pool.enqueue_job("continue_turn", thread_id=thread_id)
    logger.info("run_agent.enqueued", alias=alias, thread_id=thread_id)


class WorkerSettings:
    functions = [run_tool, run_agent_llm]

    async def on_startup(self, ctx):
        try:
            ctx['redis'] = await create_pool()
            logger.info("worker.startup")
        except Exception as e:
            logger.error("worker.startup_failed", error=str(e))
            raise RuntimeError(f"Failed to connect to Redis: {e}")

    async def on_shutdown(self, ctx):
        try:
            await ctx['redis'].close()
            logger.info("worker.shutdown")
        except Exception as e:
            logger.error("worker.shutdown_failed", error=str(e))
            raise RuntimeError(f"Error closing Redis connection: {e}")
