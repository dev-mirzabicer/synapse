import re
from .state import GraphState

MENTION_REGEX = r'@(\w+)'
MAX_TURNS = 20

def router_function(state: GraphState) -> str:
    """The definitive router for our orchestration graph."""
    if state.get('turn_count', 0) > MAX_TURNS:
        return "sync_to_postgres"

    last_message = state['messages'][-1]
    sender_name = getattr(last_message, 'name', 'system')

    if "TASK_COMPLETE" in last_message.content and sender_name == "Orchestrator":
        return "sync_to_postgres"

    if getattr(last_message, 'tool_calls', None):
        return "dispatch_tools"

    mentions = re.findall(MENTION_REGEX, last_message.content)
    if mentions:
        state['next_actors'] = [m for m in mentions if m != sender_name]
        return "dispatch_agents"

    if sender_name != "Orchestrator":
        state['next_actors'] = ["Orchestrator"]
        return "dispatch_agents"

    return "sync_to_postgres" # End if Orchestrator speaks with no commands