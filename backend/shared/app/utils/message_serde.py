from langchain_core.messages import BaseMessage
from langchain.load.dump import dumpd
from langchain.load import load


def serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    """
    Converts a list of LangChain message objects to a JSON-serializable
    list of dicts using the robust `dumpd` method.
    """
    return [dumpd(msg) for msg in messages]


def deserialize_messages(messages_dict: list[dict]) -> list[BaseMessage]:
    """
    Converts a list of dicts (serialized by `dumpd`) back into
    LangChain message objects using the robust `loadd` method.
    """
    # The check for 'lc' is a simple way to identify if the dict is in the
    # new `dumpd` format or the old `.dict()` format, adding backward
    # compatibility during transitions.
    return [
        load(m) if "lc" in m and m.get("type") == "constructor" else load(m)
        for m in messages_dict
    ]