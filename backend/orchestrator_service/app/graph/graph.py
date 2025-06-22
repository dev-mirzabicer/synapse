from langgraph.graph import StateGraph, END
from .state import GraphState
from .nodes import router_node, dispatcher_node, sync_to_postgres_node

# Define the workflow structure with the new nodes.
workflow = StateGraph(GraphState)

workflow.add_node("router", router_node)
workflow.add_node("dispatcher", dispatcher_node)
workflow.add_node("sync_to_postgres", sync_to_postgres_node)

# The entry point is now the router node.
workflow.set_entry_point("router")

def should_dispatch_or_end(state: GraphState) -> str:
    """
    A conditional edge that decides whether to dispatch a worker or end the flow.
    """
    last_message = state["messages"][-1]
    # If the router decided on next_actors or the last message has tool_calls, dispatch.
    if state.get("next_actors") or getattr(last_message, 'tool_calls', None):
        return "dispatcher"
    # Otherwise, there's nothing to do, so sync and end.
    else:
        return "sync_to_postgres"

# Add the conditional edge from the router.
workflow.add_conditional_edges(
    "router",
    should_dispatch_or_end,
    {
        "dispatcher": "dispatcher",
        "sync_to_postgres": "sync_to_postgres"
    }
)

# After dispatching a job, the graph's current turn is over. It must END.
workflow.add_edge("dispatcher", END)

# The sync node is also a terminal state.
workflow.add_edge("sync_to_postgres", END)

# Compile the final graph.
graph_app_uncompiled = workflow.compile()