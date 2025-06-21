import sys, pathlib, os, types, uuid, asyncio
import pytest
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, SystemMessage

root = pathlib.Path(__file__).resolve().parents[1]
sys.path.extend([
    str(root/"backend"),
    str(root/"backend/orchestrator_service"),
    str(root/"backend/execution_workers"),
])

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("TAVILY_API_KEY", "test")

# Replace RedisSaver with in-memory saver before importing graph modules
redis_stub = types.ModuleType("langgraph.checkpoint.redis")
redis_stub.RedisSaver = type(
    "RedisSaver",
    (),
    {"from_conn_string": classmethod(lambda cls, s: MemorySaver())},
)
sys.modules.setdefault("langgraph.checkpoint.redis", redis_stub)

from orchestrator_service.app.graph import graph, nodes
from orchestrator_service.app import worker as orch_worker
from execution_workers.app import worker as exec_worker
from shared.app.agents import runner
from shared.app.schemas.groups import GroupMemberRead

@pytest.mark.asyncio
async def test_graph_basic_flow(monkeypatch):
    cp = MemorySaver()
    monkeypatch.setattr(graph, "checkpoint", cp, raising=False)
    monkeypatch.setattr(exec_worker, "checkpoint", cp, raising=False)
    monkeypatch.setattr(orch_worker.graph_app, "checkpoint", cp, raising=False)

    async def fake_persist(state, config):
        pass
    monkeypatch.setattr(nodes, "_persist_new_messages", fake_persist)

    async def fake_run_agent(messages, members, alias):
        return SystemMessage(content="TASK_COMPLETE", name=alias)
    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    state = {
        "messages": [SystemMessage(content="TASK_COMPLETE", name="Orchestrator")],
        "group_id": "gid",
        "group_members": [GroupMemberRead(id=uuid.uuid4(), alias="Orchestrator", system_prompt="s")],
        "next_actors": [],
        "turn_count": 0,
        "last_saved_index": 1,
        "turn_id": "tid",
    }

    config = {"arq_pool": types.SimpleNamespace(enqueue_job=lambda *a, **kw: None),
              "configurable": {"thread_id": "gid"}}

    await graph.graph_app.ainvoke(state, config=config)
