import json
from arq import create_pool, ArqRedis
from langchain_core.messages import HumanMessage
from .graph.graph import graph_app


async def start_turn(ctx, group_id: str, message_content: str, user_id: str):
    """Starts a new turn initiated by a user."""
    config = {"configurable": {"thread_id": group_id}}
    graph_input = {"messages": [HumanMessage(content=message_content)]}
    # The graph will run, dispatch a job, and then pause.
    arq_pool: ArqRedis = ctx["redis"]
    await graph_app.ainvoke(graph_input, config={"arq_pool": arq_pool, **config})


async def continue_turn(ctx, thread_id: str):
    """Continues a turn after an execution_worker has updated the state."""
    config = {"configurable": {"thread_id": thread_id}}
    # We invoke with empty input, as the graph will load the new state from the checkpointer.
    arq_pool: ArqRedis = ctx["redis"]
    await graph_app.ainvoke(None, config={"arq_pool": arq_pool, **config})


class WorkerSettings:
    functions = [start_turn, continue_turn]

    async def on_startup(self, ctx):
        global _arq_pool
        try:
            _arq_pool = await create_pool()
            ctx['redis'] = _arq_pool
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Redis: {e}")

    async def on_shutdown(self, ctx):
        try:
            await ctx['redis'].close()
        except Exception as e:
            raise RuntimeError(f"Error closing Redis connection: {e}")
