import re
from .state import GraphState

# A more specific and robust regex for agent mentions.
# It safely captures aliases with letters, numbers, underscores, hyphens, periods, and spaces.
MENTION_REGEX = r'@\[([\w\s.-]+?)\]'
MAX_TURNS = 20


def route_logic(state: GraphState) -> dict:
    """
    Runs the routing logic and returns a dictionary of state updates.
    This is no longer a conditional edge function.
    """
    # Increment turn count at the start of the routing logic
    turn_count = state.get("turn_count", 0) + 1
    if turn_count > MAX_TURNS:
        # Signal to end by clearing next_actors
        return {"next_actors": [], "turn_count": turn_count}

    # The collector logic in worker.py ensures that when multiple agents
    # respond, their messages are added to the state in a single batch.
    # We only need to inspect the last message to determine the sender.
    last_message = state["messages"][-1]
    sender_name = getattr(last_message, "name", "system")

    # Defensively normalize content to always be a string for parsing.
    content_str = last_message.content
    if isinstance(content_str, list):
        content_str = "\n\n".join(map(str, content_str))

    if sender_name == "system_error":
        return {"next_actors": ["Orchestrator"], "turn_count": turn_count}

    # Use the normalized string content for all checks
    if "TASK_COMPLETE" in content_str and sender_name == "Orchestrator":
        return {"next_actors": [], "turn_count": turn_count}

    if getattr(last_message, "tool_calls", None):
        # Let the dispatcher handle tools; no change to next_actors needed.
        return {"turn_count": turn_count, "next_actors": []}

    mentions = re.findall(MENTION_REGEX, content_str)
    if mentions:
        # Filter out any self-mentions and DE-DUPLICATE the list.
        unique_mentions = set(m for m in mentions if m != sender_name)
        next_actors = list(unique_mentions)
        return {"next_actors": next_actors, "turn_count": turn_count}

    if sender_name != "Orchestrator":
        return {"next_actors": ["Orchestrator"], "turn_count": turn_count}

    # Default case: Orchestrator spoke with no commands, end the turn.
    return {"next_actors": [], "turn_count": turn_count}