import json
from arq import create_pool, ArqRedis
from langchain_core.messages import HumanMessage
from .graph.graph import graph_app
from shared.app.core.config import settings

# This is a bit of a hack to share the pool with the nodes.
# A better solution would use a proper dependency injection framework.
_arq_pool: ArqRedis = None

def get_arq_pool():
    return _arq_pool

async def start_turn(ctx, group_id: str, message_content: str, user_id: str):
    """Starts a new turn initiated by a user."""
    config = {"configurable": {"thread_id": group_id}}
    graph_input = {"messages": [HumanMessage(content=message_content)]}
    # The graph will run, dispatch a job, and then pause.
    await graph_app.ainvoke(graph_input, config={"arq_pool": get_arq_pool(), **config})

async def continue_turn(ctx, thread_id: str):
    """Continues a turn after an execution_worker has updated the state."""
    config = {"configurable": {"thread_id": thread_id}}
    # We invoke with empty input, as the graph will load the new state from the checkpointer.
    await graph_app.ainvoke(None, config={"arq_pool": get_arq_pool(), **config})

class WorkerSettings:
    functions = [start_turn, continue_turn]
    
    async def on_startup(self, ctx):
        global _arq_pool
        _arq_pool = await create_pool()
        ctx['redis'] = _arq_pool

    async def on_shutdown(self, ctx):
        await ctx['redis'].close()