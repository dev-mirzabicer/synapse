import sys, pathlib, os
root = pathlib.Path(__file__).resolve().parents[1]
sys.path.extend([
    str(root/"backend"),
    str(root/"backend/orchestrator_service"),
    str(root/"backend/execution_workers"),
])
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("TAVILY_API_KEY", "test")
import types
import pytest
from langchain_core.messages import SystemMessage

from shared.app.core.config import settings as shared_settings
object.__setattr__(shared_settings, "TAVILY_API_KEY", "test")

# Stub graph_app to avoid circular imports when loading worker modules
stub_graph = types.ModuleType("orchestrator_service.app.graph.graph")
stub_graph.graph_app = types.SimpleNamespace(ainvoke=lambda *a, **kw: None)
sys.modules.setdefault("orchestrator_service.app.graph.graph", stub_graph)
redis_stub = types.ModuleType("langgraph.checkpoint.redis")
redis_stub.RedisSaver = type("RedisSaver", (), {"from_conn_string": classmethod(lambda cls, s: None)})
sys.modules.setdefault("langgraph.checkpoint.redis", redis_stub)

from orchestrator_service.app import worker as orch_worker
from execution_workers.app import worker as exec_worker

@pytest.mark.asyncio
async def test_start_turn(monkeypatch):
    called = {}
    async def fake_ainvoke(inp, config):
        called['input'] = inp
        called['config'] = config
    monkeypatch.setattr(orch_worker.graph_app, 'ainvoke', fake_ainvoke)
    orch_worker._arq_pool = 'pool'
    await orch_worker.start_turn({}, 'gid', 'hi', 'uid')
    assert called['input']['messages'][0].content == 'hi'
    assert called['config']['arq_pool'] == 'pool'

@pytest.mark.asyncio
async def test_continue_turn(monkeypatch):
    called = {}
    async def fake_ainvoke(inp, config):
        called['input'] = inp
        called['config'] = config
    monkeypatch.setattr(orch_worker.graph_app, 'ainvoke', fake_ainvoke)
    orch_worker._arq_pool = 'pool'
    await orch_worker.continue_turn({}, 'tid')
    assert called['config']['configurable']['thread_id'] == 'tid'
    assert called['config']['arq_pool'] == 'pool'

class DummyRedis:
    def __init__(self):
        self.jobs = []
    async def enqueue_job(self, name, **kwargs):
        self.jobs.append((name, kwargs))

class DummyCheckpoint:
    def __init__(self):
        self.updates = []
    async def update_state(self, state, data):
        self.updates.append((state, data))

@pytest.mark.asyncio
async def test_run_tool(monkeypatch):
    cp = DummyCheckpoint()
    redis = DummyRedis()
    ctx = {'redis': redis}
    monkeypatch.setattr(exec_worker, 'checkpoint', cp)
    exec_worker.TOOL_REGISTRY['echo'] = lambda args: 'ok'
    await exec_worker.run_tool(ctx, 'echo', {}, 'tid', 'cid')
    assert cp.updates
    assert redis.jobs

@pytest.mark.asyncio
async def test_run_agent_llm(monkeypatch):
    cp = DummyCheckpoint()
    redis = DummyRedis()
    ctx = {'redis': redis}
    async def fake_run_agent(msgs, members, alias):
        return SystemMessage(content='done', name=alias)
    monkeypatch.setattr(exec_worker, 'checkpoint', cp)
    monkeypatch.setattr(exec_worker, 'run_agent', fake_run_agent)
    await exec_worker.run_agent_llm(ctx, 'a', [], [], 'tid')
    assert cp.updates
    assert redis.jobs
