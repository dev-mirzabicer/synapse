from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
)

def serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    """Converts a list of LangChain message objects to a JSON-serializable list of dicts."""
    return [msg.dict() for msg in messages]

def deserialize_messages(messages_dict: list[dict]) -> list[BaseMessage]:
    """Converts a list of dicts back into LangChain message objects."""
    messages = []
    for m in messages_dict:
        msg_type = m.get("type")
        if msg_type == "human":
            messages.append(HumanMessage(**m))
        elif msg_type == "ai":
            messages.append(AIMessage(**m))
        elif msg_type == "system":
            messages.append(SystemMessage(**m))
        elif msg_type == "tool":
            messages.append(ToolMessage(**m))
    return messages