from uuid import UUID
from typing import Annotated, List, Optional
from pydantic import AfterValidator, BaseModel, Field
from langgraph.graph import StateGraph

from _types.tool import SynapseTool

ActorID = Annotated[
    UUID, AfterValidator(lambda v: v if isinstance(v, UUID) else UUID(v))
]

GroupID = Annotated[
    UUID, AfterValidator(lambda v: v if isinstance(v, UUID) else UUID(v))
]


class AgentConfig(BaseModel):
    model: str = Field(..., description="LLM model name")
    temperature: float = Field(0.7, description="Temperature for LLM responses")
    max_tokens: int = Field(1500, description="Maximum tokens for LLM responses")
    top_p: float = Field(1.0, description="Top-p sampling for LLM responses")


class GeminiConfig(AgentConfig):
    safety_settings: Optional[dict] = Field(
        None, description="Safety settings for Gemini LLM"
    )


class BaseActor(BaseModel):
    id: ActorID = Field(..., description="Unique identifier for the actor")
    name: str = Field(..., description="Name of the actor")
    description: Optional[str] = Field(None, description="Description of the actor")

    def __str__(self):
        return f"{self.name} ({self.id}) - {self.description or 'No description'}"


class UserActor(BaseActor):
    pass


class AgentActor(BaseActor):
    config: AgentConfig = Field(
        ..., description="LLM configuration for the agent actor"
    )
    tools: List[SynapseTool] = Field(
        default_factory=list, description="List of tools available to the agent"
    )
    graph: StateGraph = Field(
        ..., description="State graph defining the agent's behavior"
    )


class OrchestratorActor(AgentActor):
    pass


class ActorGroup(BaseModel):
    id: GroupID = Field(..., description="Unique identifier for the actor group")
    name: str = Field(..., description="Name of the actor group")
    agents: List[AgentActor] = Field(
        default_factory=list, description="List of agents in the group"
    )
    orchestrator: OrchestratorActor = Field(
        ..., description="Orchestrator actor for the group"
    )
    user: UserActor = Field(..., description="User actor for the group")

    def __str__(self):
        return f"Group {self.name} ({self.id}) with {len(self.agents)} agents and orchestrator {self.orchestrator}"
