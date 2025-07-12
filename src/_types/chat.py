from types import Optional
from pydantic import BaseModel, Field
from services.history import HistoryService
from _types.history import SynapseHistory
from _types.actor import ActorGroup, BaseActor
from datetime import datetime
from uuid import UUID
from langgraph.graph import StateGraph


class SynapseChat(BaseModel):
    history: HistoryService = Field(
        default_factory=lambda: HistoryService(SynapseHistory()),
        description="Chat history",
    )
    group: ActorGroup = Field(
        default_factory=ActorGroup,
        description="Actor group involved in the chat",
    )
    title: str = Field(
        default="Synapse Chat",
        description="Title of the chat",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp when the chat was created",
    )
    owner_id: UUID = Field(
        default_factory=lambda: UUID("00000000-0000-0000-0000-000000000000"),
        description="Unique identifier for the chat owner",
    )
    description: Optional[str] = Field(
        None, description="Optional description of the chat"
    )
    last_actor: Optional[BaseActor] = Field(
        None, description="The last actor who interacted in the chat"
    )
    next_actor: Optional[BaseActor] = Field(
        None, description="The next actor expected to interact in the chat"
    )
    graph: StateGraph = Field(
        default_factory=StateGraph,
        description="State graph defining the chat's behavior",
    )
