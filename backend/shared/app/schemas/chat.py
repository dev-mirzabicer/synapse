import uuid
from pydantic import BaseModel, Field

class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)

class MessageRead(BaseModel):
    id: uuid.UUID
    turn_id: uuid.UUID
    sender_alias: str
    content: str

    class Config:
        from_attributes = True

