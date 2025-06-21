import sys, pathlib
root = pathlib.Path(__file__).resolve().parents[1]
sys.path.extend([
    str(root/"backend"),
    str(root/"backend/orchestrator_service"),
])
from orchestrator_service.app.graph.router import router_function
from orchestrator_service.app.graph.state import GraphState
from langchain_core.messages import SystemMessage


def test_router_handles_system_error():
    state: GraphState = {
        "messages": [SystemMessage(content="fail", name="system_error")],
        "group_id": "gid",
        "group_members": [],
        "next_actors": [],
        "turn_count": 0,
        "last_saved_index": 0,
        "turn_id": "tid",
    }
    result = router_function(state)
    assert result == "dispatch_agents"
    assert state["next_actors"] == ["Orchestrator"]
