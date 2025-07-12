from pydantic import BaseModel, Field
from typing import List
from _types.message import SynapseMessage
from datetime import datetime


class SynapseHistory(BaseModel):
    messages: List[SynapseMessage] = Field(
        default_factory=list, description="List of messages in the history"
    )
    last_updated: datetime = Field(
        ..., description="Timestamp of the last update to the history"
    )

    def __str__(self):
        return f"SynapseHistory with {len(self.messages)} messages, last updated at {self.last_updated}"

    def __init__(
        self, messages: List[SynapseMessage] = None, last_updated: datetime = None
    ):
        super().__init__(
            messages=messages or [], last_updated=last_updated or datetime.now()
        )
