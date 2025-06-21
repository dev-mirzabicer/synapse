import operator
from typing import TypedDict, Annotated, List
from langchain_core.messages import BaseMessage

# Import the Pydantic schema we created in the previous step
from shared.app.schemas.groups import GroupMemberRead

class GraphState(TypedDict):
    """
    The complete state of our multi-agent graph.
    This TypedDict is passed between all nodes.
    """
    
    # The full, ordered history of the conversation.
    # The `Annotated` and `operator.add` ensure that when a node returns
    # a "messages" key, its value is appended to the existing list.
    messages: Annotated[List[BaseMessage], operator.add]

    # Configuration and context for the current run.
    group_id: str
    group_members: List[GroupMemberRead]

    # A list of agent aliases that the router has decided should act next.
    # This is populated by the router and consumed by the agent_node.
    next_actors: List[str]

    # A counter to prevent infinite loops, a crucial safety mechanism.
    turn_count: int

    # Index of the last message persisted to the database.
    last_saved_index: int

    # The ID representing this conversation turn.
    turn_id: str
