import uuid
from pydantic import BaseModel

class GroupCreate(BaseModel):
    name: str

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
    alias: str
    system_prompt: str
    tools: list[str] | None = []

    class Config:
        from_attributes = True