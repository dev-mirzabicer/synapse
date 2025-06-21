from langgraph.graph import StateGraph

from .state import GraphState
from .nodes import agent_node, orchestrator_node, tool_node
from .router import router_function
from .checkpoint import checkpoint

# 1. Initialize the StateGraph with our GraphState definition.
# This graph will be stateful, with the state managed by the checkpointer.
workflow = StateGraph(GraphState)

# 2. Add the nodes to the graph.
# Each node is a function or a runnable that takes the state and returns a dictionary to update it.
workflow.add_node("orchestrator", orchestrator_node)
workflow.add_node("agents", agent_node)
workflow.add_node("tools", tool_node)

# 3. Define the entry point of the graph.
# Every conversation turn begins with the Orchestrator to evaluate the state.
workflow.set_entry_point("orchestrator")

# 4. Add the conditional edges that route the conversation.
# The router_function will be called after each of these nodes to decide where to go next.
workflow.add_conditional_edges(
    start_key="orchestrator",
    condition=router_function,
    # The path_map defines the mapping from the router's string output to the next node.
    path_map={
        "call_agents": "agents",
        "call_tools": "tools",
        "__END__": "__END__"
    }
)

workflow.add_conditional_edges(
    start_key="agents",
    condition=router_function,
    path_map={
        "orchestrator": "orchestrator",
        "call_tools": "tools",
        "__END__": "__END__"
    }
)

workflow.add_conditional_edges(
    start_key="tools",
    condition=router_function,
    path_map={
        "orchestrator": "orchestrator",
        "__END__": "__END__"
    }
)

# 5. Compile the graph into a runnable application.
# We pass in the Redis checkpointer to enable persistence. This is the key
# to making our application stateful and resilient.
graph_app = workflow.compile(checkpointer=checkpoint)

# For debugging and visualization, we can generate a diagram of the graph.
try:
    graph_app.get_graph().draw_mermaid_png(output_file_path="graph.png")
    print("Graph diagram saved to graph.png")
except Exception as e:
    print(f"Could not draw graph: {e}. Please install pygraphviz and pydot if you want to visualize it.")