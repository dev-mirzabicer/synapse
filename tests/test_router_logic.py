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
from langchain_core.messages import AIMessage, SystemMessage
from backend.orchestrator_service.app.graph.router import route_logic
from backend.orchestrator_service.app.graph.state import GraphState

@pytest.mark.asyncio
async def test_route_logic_with_mentions():
    state = GraphState(
        messages=[AIMessage(content="hello @AgentA")],
        group_id="g",
        group_members=[],
        next_actors=[],
        turn_count=0,
        last_saved_index=0,
        turn_id="t",
    )
    update = route_logic(state)
    assert update["next_actors"] == ["AgentA"]
    assert update["turn_count"] == 1

@pytest.mark.asyncio
async def test_route_logic_task_complete():
    state = GraphState(
        messages=[AIMessage(content="done TASK_COMPLETE", name="Orchestrator")],
        group_id="g",
        group_members=[],
        next_actors=[],
        turn_count=5,
        last_saved_index=0,
        turn_id="t",
    )
    update = route_logic(state)
    assert update["next_actors"] == []
    assert update["turn_count"] == 6

@pytest.mark.asyncio
async def test_route_logic_system_error():
    state = GraphState(
        messages=[SystemMessage(content="boom", name="system_error")],
        group_id="g",
        group_members=[],
        next_actors=[],
        turn_count=2,
        last_saved_index=0,
        turn_id="t",
    )
    update = route_logic(state)
    assert update["next_actors"] == ["Orchestrator"]
    assert update["turn_count"] == 3
