import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///file::memory:?cache=shared")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

import pytest
from langchain_core.messages import HumanMessage, AIMessage
from backend.shared.app.utils.message_serde import serialize_messages, deserialize_messages

@pytest.mark.asyncio
async def test_message_roundtrip():
    messages = [HumanMessage(content="hi"), AIMessage(content="there")]
    serialized = serialize_messages(messages)
    deserialized = deserialize_messages(serialized)
    assert [m.content for m in deserialized] == ["hi", "there"]
    assert [type(m) for m in deserialized] == [HumanMessage, AIMessage]
