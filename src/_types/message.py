from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Any
from _types.actor import BaseActor
from langchain_core.messages import (
    ToolCall,
    BaseMessage,
)
from datetime import datetime


class MessageType(Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    TOOL_RESULT = "tool_result"


class Visibility(Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class SynapseMessage(BaseModel):
    type: MessageType = Field(..., description="Type of the message")
    # content: str = Field(..., description="Content of the message")
    lc_message: BaseMessage = Field(..., description="LangChain message object")
    # sender: ActorID = Field(..., description="Identifier of the sender")
    sender: BaseActor = Field(..., description="Actor who sent the message")
    timestamp: datetime = Field(
        ..., description="Timestamp of when the message was sent"
    )
    visibility: Visibility = Field(
        Visibility.PUBLIC, description="Visibility of the message"
    )
    # tool_calls: List[ToolCall] = Field(
    #     [], description="Tool calls associated with the message, if any"
    # )

    @property
    def content(self) -> str:
        content = self.lc_message.content if hasattr(self.lc_message, "content") else ""
        if not isinstance(content, str):
            raise ValueError("Content must be a string")
        return content

    @property
    def tool_calls(self) -> List[ToolCall]:
        return getattr(self.lc_message, "tool_calls", [])

    def __str__(self):
        return f"{self.type.value} message from {self.sender} at {self.timestamp.isoformat()}: {self.content}"


class ToolResultMessage(SynapseMessage):
    tool_name: str = Field(..., description="Name of the tool that produced the result")
    call_id: str = Field(..., description="Identifier of the tool call")
    result: Optional[Any] = Field(None, description="Result of the tool call")
    caller: BaseActor = Field(..., description="Actor who called the tool")

    def __str__(self):
        return (
            f"Tool result message from {self.sender} at {self.timestamp.isoformat()}: "
            f"{self.tool_name} with result {self.result}"
        )
