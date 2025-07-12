from abc import ABC, abstractmethod
from typing import List
from uuid import UUID

from langgraph.graph import StateGraph

from _types.actor import AgentActor, BaseActor, OrchestratorActor, UserActor
from _types.history import SynapseHistory
from _types.message import SynapseMessage


class ActorService(ABC):
    def __init__(self, actor: BaseActor):
        self._actor = actor

    @property
    def id(self) -> UUID:
        return self._actor.id

    @abstractmethod
    async def invoke(self, history: SynapseHistory) -> List[SynapseMessage]:
        raise NotImplementedError


class UserActorService(ActorService):
    def __init__(self, actor: UserActor):
        super().__init__(actor)
        self._actor: UserActor = actor

    async def invoke(self, history: SynapseHistory) -> List[SynapseMessage]:
        response: List[SynapseMessage] = await self._handle_user_interaction(history)
        return response

    async def _handle_user_interaction(
        self, history: SynapseHistory
    ) -> List[SynapseMessage]:
        raise NotImplementedError("User interaction handling not implemented.")


class AgentActorService(ActorService):
    def __init__(self, actor: AgentActor):
        super().__init__(actor)
        self._actor: AgentActor = actor

    def _build_graph(self) -> StateGraph:
        raise NotImplementedError("Graph building not implemented.")

    async def invoke(self, history: SynapseHistory) -> List[SynapseMessage]:
        # Assumed functionality:
        # 1. Personalize the history for the actor.
        # 2. Loop:
        #   - Invoke the agent's graph with the personalized history.
        #   - Collect the response message
        #   - If the response is a tool call, execute the tool and add the result to the history.
        #   - If the tool call is a group message, convert it to a public SynapseMessage and add it to the history.
        #   - If the response is a final message, finish the loop and return the messages.
        raise NotImplementedError("Agent invocation not implemented.")

    def set_custom_graph(self, graph: StateGraph) -> None:
        self._actor.graph = graph


class OrchestratorActorService(AgentActorService):
    def __init__(self, actor: OrchestratorActor):
        super().__init__(actor)
        self._actor: OrchestratorActor = actor

    def _build_graph(self) -> StateGraph:
        raise NotImplementedError("Orchestrator graph building not implemented.")

    async def invoke(self, history: SynapseHistory) -> List[SynapseMessage]:
        # Assumed functionality:
        # 1. Personalize the history for the orchestrator.
        # 2. Invoke the orchestrator's graph with the personalized history.
        # 3. Parse the decision from the response (e.g., which agent to invoke next).
        # 4. Return the decision.
        raise NotImplementedError("Orchestrator invocation not implemented.")
