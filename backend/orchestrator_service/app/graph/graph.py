from langgraph.graph import StateGraph, END
from graph.state import GraphState
from graph.nodes import dispatch_node, sync_to_postgres_node
from graph.router import router_function

# Define the workflow structure without a checkpointer.
# The checkpointer will be added dynamically during compilation.
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
workflow.add_edge("sync_to_postgres", END)

# We export the uncompiled workflow. It will be compiled with a checkpointer
# inside the async worker functions.
graph_app_uncompiled = workflow.compile()