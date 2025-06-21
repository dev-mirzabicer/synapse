import uuid
from pydantic import BaseModel, Field

class GroupCreate(BaseModel):
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
    alias: str = Field(..., min_length=1, max_length=100)
    system_prompt: str
    tools: list[str] | None = []
    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.1

    class Config:
        from_attributes = True


