import uuid
from pydantic import BaseModel

class MessageCreate(BaseModel):
    content: str

class MessageRead(BaseModel):
    id: uuid.UUID
    turn_id: uuid.UUID
    sender_alias: str
    content: str

    class Config:
        from_attributes = True