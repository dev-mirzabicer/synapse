import uuid
from pydantic import BaseModel, Field
from datetime import datetime # Added for GroupDetailRead


class AgentConfigCreate(BaseModel):
    """Configuration for creating a non-user agent member."""
    alias: str = Field(..., min_length=1, max_length=100)
    role_prompt: str = Field(..., min_length=1)
    tools: list[str] | None = []
    provider: str = "gemini"
    model: str = "gemini-2.5-pro"
    temperature: float = 0.1

class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    members: list[AgentConfigCreate] = Field(default_factory=list)

class GroupRead(BaseModel):
    id: uuid.UUID
    name: str

    class Config:
        from_attributes = True

class GroupMemberRead(BaseModel):
    """
    A schema for reading a group member's configuration.
    This will be used to populate the GraphState.
    """
    id: uuid.UUID
    alias: str = Field(..., min_length=1, max_length=100)
    system_prompt: str
    tools: list[str] | None = []
    provider: str
    model: str
    temperature: float

    class Config:
        from_attributes = True


class GroupDetailRead(BaseModel):
    """Detailed information about a chat group, including its members."""
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    members: list[GroupMemberRead]

    class Config:
        from_attributes = True