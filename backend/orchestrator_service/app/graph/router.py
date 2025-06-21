import re
from langchain_core.messages import BaseMessage
from .state import GraphState

# A simple but effective regex to find @mentions in the message content.
MENTION_REGEX = r'@(\w+)'
MAX_TURNS = 15 # Safety limit for conversation length.

def router_function(state: GraphState) -> str:
    """
    This is the central brain of the graph. It inspects the current state
    and decides which node to execute next.

    The decision-making process follows a strict priority order.
    """
    
    # 1. Safety Check: Prevent infinite loops.
    # This is the most important check and should always be first.
    if state.get('turn_count', 0) > MAX_TURNS:
        return "__END__"

    # Get the last message added to the conversation.
    last_message = state['messages'][-1]

    # 2. Priority 1: Check for tool calls.
    # If the last message is an AIMessage with tool_calls, we must execute the tools.
    if getattr(last_message, 'tool_calls', None):
        return "call_tools"

    # 3. Priority 2: Check for @mentions for delegation.
    mentions = re.findall(MENTION_REGEX, last_message.content)
    if mentions:
        # Filter out any potential self-mentions to avoid loops.
        # The 'next_actors' field in the state is updated for the agent_node to use.
        state['next_actors'] = [m for m in mentions if m != last_message.sender.name]
        if state['next_actors']:
            return "call_agents"

    # 4. Priority 3: Return control to the Orchestrator.
    # If the last message was from any node other than the Orchestrator,
    # it's time for the Orchestrator to review the work and plan the next step.
    # We check `last_message.name` if it's a ToolMessage or `sender.name` for others.
    sender_name = getattr(last_message, 'name', getattr(last_message.sender, 'name', ''))
    if sender_name and sender_name != "Orchestrator":
        return "orchestrator"

    # 5. Default Case: End the turn.
    # If no other condition is met, it means the Orchestrator has spoken
    # without issuing any new commands. The turn is complete.
    return "__END__"