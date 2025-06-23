import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///file::memory:?cache=shared")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

import uuid
import pytest
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage, SystemMessage

from backend.orchestrator_service.app.graph.nodes import dispatcher_node
from backend.orchestrator_service.app.graph.state import GraphState

# Patch the langchain tool decorator before importing tools/worker
import langchain_core.tools as lctools

def dummy_tool_decorator(*args, **kwargs):
    def wrapper(fn):
        return fn
    return wrapper

lctools.tool = dummy_tool_decorator

from backend.execution_workers.app.worker import run_tool, run_agent_llm

class FakeArq:
    def __init__(self):
        self.jobs = []
    async def enqueue_job(self, *args, **kwargs):
        self.jobs.append((args, kwargs))

@pytest.mark.asyncio
async def test_dispatcher_node_tools():
    fake_arq = FakeArq()
    message = AIMessage(content="", tool_calls=[{"name":"web_search","id":"1","args":{}}])
    state = GraphState(messages=[message], group_id="g", group_members=[], next_actors=[], turn_count=0, last_saved_index=0, turn_id="t")
    await dispatcher_node(state, {"configurable": {"arq_pool": fake_arq, "thread_id": "g"}})
    assert fake_arq.jobs
    args, kwargs = fake_arq.jobs[0]
    assert args[0] == "run_tool" and kwargs["tool_name"] == "web_search"

@pytest.mark.asyncio
async def test_dispatcher_node_agents():
    fake_arq = FakeArq()
    msg = AIMessage(content="hi")
    from backend.shared.app.schemas.groups import GroupMemberRead
    member = GroupMemberRead(id=uuid.uuid4(), alias="AgentA", system_prompt="", tools=[], provider="openai", model="gpt-4o", temperature=0.1)
    state = GraphState(messages=[msg], group_id="g", group_members=[member], next_actors=["AgentA"], turn_count=0, last_saved_index=0, turn_id="t")
    await dispatcher_node(state, {"configurable": {"arq_pool": fake_arq, "thread_id": "g"}})
    assert fake_arq.jobs
    job = fake_arq.jobs[0]
    assert job[0][0] == "run_agent_llm" and job[1]["alias"] == "AgentA"

class DummyTool:
    async def ainvoke(self, args):
        return "tool-result"

@pytest.mark.asyncio
async def test_run_tool_enqueues():
    fake_arq = FakeArq()
    ctx = {"redis": fake_arq}
    from backend.shared.app.agents import tools
    original = tools.TOOL_REGISTRY
    tools.TOOL_REGISTRY = {"dummy": DummyTool()}
    try:
        await run_tool(ctx, tool_name="dummy", tool_args={}, thread_id="t", tool_call_id="1")
    finally:
        tools.TOOL_REGISTRY = original
    assert fake_arq.jobs
    job = fake_arq.jobs[0]
    assert job[0][0] == "update_graph_with_message"

class DummyResponse(SystemMessage):
    pass

@pytest.mark.asyncio
async def test_run_agent_llm_enqueues(monkeypatch):
    fake_arq = FakeArq()
    ctx = {"redis": fake_arq}
    async def fake_runner(messages, members, alias):
        return SystemMessage(content="result", name=alias)
    monkeypatch.setattr("backend.shared.app.agents.runner.run_agent", fake_runner)
    messages_dict = [{"type":"constructor","id":"1","kwargs":{"content":"hi","name":"User","lc":1,"id":None},"schema":"langchain_core.messages.human.HumanMessage"}]
    member = {"id": str(uuid.uuid4()), "alias": "AgentA", "system_prompt": "", "tools": [], "provider": "openai", "model": "gpt-4o", "temperature": 0.1}
    await run_agent_llm(ctx, alias="AgentA", messages_dict=messages_dict, group_members_dict=[member], thread_id="t")
    assert fake_arq.jobs
    assert fake_arq.jobs[0][0][0] == "update_graph_with_message"
