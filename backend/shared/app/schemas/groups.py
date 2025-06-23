import uuid
from pydantic import BaseModel, Field, validator
from datetime import datetime


class AgentConfigCreate(BaseModel):
    """Configuration for creating a non-user agent member."""
    alias: str = Field(..., min_length=1, max_length=100)
    role_prompt: str = Field(..., min_length=1)
    tools: list[str] | None = Field(default_factory=list)
    provider: str = Field(default="gemini")
    model: str = Field(default="gemini-2.5-pro")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)

    @validator('alias')
    def alias_cannot_be_orchestrator_or_user(cls, v):
        if v.lower() in ["orchestrator", "user"]:
            raise ValueError('Alias cannot be "Orchestrator" or "User"')
        return v

class AgentConfigUpdate(BaseModel):
    """Configuration for updating a non-user agent member. All fields are optional."""
    alias: str | None = Field(default=None, min_length=1, max_length=100)
    role_prompt: str | None = Field(default=None, min_length=1)
    tools: list[str] | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)

    @validator('alias')
    def alias_cannot_be_orchestrator_or_user_optional(cls, v):
        if v is not None and v.lower() in ["orchestrator", "user"]:
            raise ValueError('Alias cannot be "Orchestrator" or "User"')
        return v

class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    members: list[AgentConfigCreate] = Field(default_factory=list)

class GroupUpdate(BaseModel):
    """Schema for updating a group's mutable properties (e.g., name)."""
    name: str = Field(..., min_length=1, max_length=100)


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
    group_id: uuid.UUID # Added for context
    alias: str = Field(..., min_length=1, max_length=100)
    system_prompt: str
    tools: list[str] | None = Field(default_factory=list)
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