import re
from .state import GraphState

MENTION_REGEX = r'@(\w+)'
MAX_TURNS = 20

def route_logic(state: GraphState) -> dict:
    """
    Runs the routing logic and returns a dictionary of state updates.
    This is no longer a conditional edge function.
    """
    # Increment turn count at the start of the routing logic
    turn_count = state.get('turn_count', 0) + 1
    if turn_count > MAX_TURNS:
        # Signal to end by clearing next_actors
        return {"next_actors": [], "turn_count": turn_count}

    last_message = state['messages'][-1]
    sender_name = getattr(last_message, 'name', 'system')

    if sender_name == "system_error":
        return {"next_actors": ["Orchestrator"], "turn_count": turn_count}

    if "TASK_COMPLETE" in last_message.content and sender_name == "Orchestrator":
        return {"next_actors": [], "turn_count": turn_count}

    if getattr(last_message, 'tool_calls', None):
        # Let the dispatcher handle tools; no change to next_actors needed.
        return {"turn_count": turn_count, "next_actors": []}

    mentions = re.findall(MENTION_REGEX, last_message.content)
    if mentions:
        next_actors = [m for m in mentions if m != sender_name]
        return {"next_actors": next_actors, "turn_count": turn_count}

    if sender_name != "Orchestrator":
        return {"next_actors": ["Orchestrator"], "turn_count": turn_count}

    # Default case: Orchestrator spoke with no commands, end the turn.
    return {"next_actors": [], "turn_count": turn_count}