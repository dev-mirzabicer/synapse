from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
)

# This mapping is robust and extensible.
MESSAGE_TYPE_MAP = {
    "human": HumanMessage,
    "ai": AIMessage,
    "system": SystemMessage,
    "tool": ToolMessage,
}

def serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    """Converts a list of LangChain message objects to a JSON-serializable list of dicts."""
    return [msg.dict() for msg in messages]

def deserialize_messages(messages_dict: list[dict]) -> list[BaseMessage]:
    """Converts a list of dicts back into LangChain message objects."""
    messages = []
    for m in messages_dict:
        msg_type = m.get("type")
        if msg_class := MESSAGE_TYPE_MAP.get(msg_type):
            # The tool_call_id is not part of the default AIMessage constructor,
            # so we handle it carefully.
            if msg_type == 'ai' and 'tool_calls' in m and m['tool_calls']:
                 # LangChain AIMessage expects tool_calls to be dicts, not objects
                 pass # It should already be in the correct format from .dict()
            messages.append(msg_class(**m))
    return messages