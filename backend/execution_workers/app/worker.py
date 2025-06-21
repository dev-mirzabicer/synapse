from langgraph.checkpoint.redis import RedisSaver
from langchain_core.messages import ToolMessage

from shared.app.core.config import settings
from shared.app.agents.tools import TOOL_REGISTRY
from shared.app.agents.runner import run_agent
from shared.app.schemas.groups import GroupMemberRead
from shared.app.utils.message_serde import deserialize_messages # We will create this utility

# The worker must connect to the exact same checkpointer as the orchestrator.
checkpoint = RedisSaver.from_conn_string(settings.REDIS_URL)

async def run_tool(ctx, tool_name: str, tool_args: dict, thread_id: str):
    """Executes a tool and updates the graph state with the result."""
    arq_pool = ctx['redis']
    print(f"Executing tool '{tool_name}' for thread {thread_id}")
    
    tool_function = TOOL_REGISTRY.get(tool_name)
    if not tool_function:
        result = f"Error: Tool '{tool_name}' not found."
    else:
        try:
            result = tool_function.invoke(tool_args)
        except Exception as e:
            result = f"Error executing tool '{tool_name}': {e}"

    message = ToolMessage(content=str(result), name=tool_name)
    
    # Update the graph state in Redis with the tool's output.
    await checkpoint.update_state(
        {"configurable": {"thread_id": thread_id}},
        {"messages": [message]}
    )
    
    # CRITICAL: Enqueue a job for the orchestrator to continue the turn.
    await arq_pool.enqueue_job("continue_turn", thread_id=thread_id)

async def run_agent_llm(ctx, alias: str, messages_dict: list, group_members_dict: list, thread_id: str):
    """Runs an agent's LLM, updates state, and continues the orchestration."""
    arq_pool = ctx['redis']
    print(f"Running LLM for agent '{alias}' for thread {thread_id}")

    # Deserialize messages and schemas from dicts back into objects
    messages = deserialize_messages(messages_dict)
    group_members = [GroupMemberRead.model_validate(gm) for gm in group_members_dict]

    response = await run_agent(messages, group_members, alias)
    
    await checkpoint.update_state(
        {"configurable": {"thread_id": thread_id}},
        {"messages": [response]}
    )
    
    await arq_pool.enqueue_job("continue_turn", thread_id=thread_id)

class WorkerSettings:
    functions = [run_tool, run_agent_llm]
    
    async def on_startup(self, ctx):
        # We need an ARQ pool to enqueue jobs back to the orchestrator
        from arq import create_pool
        ctx['redis'] = await create_pool()

    async def on_shutdown(self, ctx):
        await ctx['redis'].close()