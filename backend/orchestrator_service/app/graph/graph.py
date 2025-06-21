from langgraph.graph import StateGraph
from .state import GraphState
from .nodes import dispatch_node, sync_to_postgres_node
from .router import router_function
from .checkpoint import checkpoint

workflow = StateGraph(GraphState)

# We now have two primary nodes in the orchestrator
workflow.add_node("dispatch", dispatch_node)
workflow.add_node("sync_to_postgres", sync_to_postgres_node)

# The entry point is always the router, which decides the first action.
workflow.set_entry_point("dispatch")

# The router now directs traffic to the correct node.
workflow.add_conditional_edges(
    "dispatch",
    router_function,
    {
        "dispatch_tools": "dispatch",
        "dispatch_agents": "dispatch",
        "sync_to_postgres": "sync_to_postgres"
    }
)
# After syncing, the process is truly finished.
workflow.add_edge("sync_to_postgres", "__END__")

graph_app = workflow.compile(checkpointer=checkpoint)