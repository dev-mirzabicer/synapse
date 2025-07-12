from pydantic import BaseModel, Field
from services.actor import AgentActorService, OrchestratorActorService
from _types.chat import SynapseChat

from langgraph.graph import StateGraph


class SynapseChatService(BaseModel):
    chat: SynapseChat = Field(
        default_factory=lambda: SynapseChat(),
        description="Chat session management",
    )

    def _build_graph(self) -> StateGraph:
        # The graph will be as follows:
        # 1. Get user input
        # 2. Go to the orchestrator to decide the next agent (or user)
        # 3. Invoke the next agent's graph with the personalized history
        # 4. Update the history
        # 5. GOTO 2
        raise NotImplementedError("Graph building not implemented.")

    async def invoke(self) -> None:
        raise NotImplementedError("Chat invocation not implemented.")

    def _orchestrator_node(self, orchestrator: OrchestratorActorService) -> None:
        # This node will handle the decision-making process for the chat
        raise NotImplementedError("Orchestrator node not implemented.")

    def _agent_node(self, actor: AgentActorService) -> None:
        # This node will handle the interaction with a specific agent
        raise NotImplementedError("Agent node not implemented.")

    def _user_node(self) -> None:
        # This node will handle user interactions
        raise NotImplementedError("User node not implemented.")

    def _route_turn(self) -> None:
        # This method will route the turn to the appropriate actor
        raise NotImplementedError("Turn routing not implemented.")
