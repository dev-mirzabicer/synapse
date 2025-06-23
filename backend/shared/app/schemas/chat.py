import uuid
from pydantic import BaseModel, Field
from datetime import datetime # Added for MessageHistoryRead

class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)

class MessageRead(BaseModel):
    id: uuid.UUID
    turn_id: uuid.UUID
    sender_alias: str
    content: str

    class Config:
        from_attributes = True


class MessageHistoryRead(BaseModel):
    """Schema for messages retrieved as part of chat history."""
    id: uuid.UUID
    group_id: uuid.UUID
    turn_id: uuid.UUID
    sender_alias: str
    content: str
    timestamp: datetime
    parent_message_id: uuid.UUID | None = None
    meta: dict | None = None

    class Config:
        from_attributes = True