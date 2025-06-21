import sys, pathlib, os
root = pathlib.Path(__file__).resolve().parents[1]
sys.path.extend([
    str(root/"backend"),
    str(root/"backend/api_gateway"),
])
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("TAVILY_API_KEY", "test")
import types
import uuid
import pytest
from fastapi.testclient import TestClient
from fastapi.security import OAuth2PasswordRequestForm

import shared.app.schemas.groups as _groups
import shared.app.schemas.chat as _chat
_chat.GroupCreate = _groups.GroupCreate
_chat.GroupRead = _groups.GroupRead

from api_gateway.app.main import app
from api_gateway.app.api.routers import auth as auth_router
from api_gateway.app.api.routers import groups as groups_router
from api_gateway.app.core import security

class FakeExecuteResult:
    def __init__(self, value=None):
        self._value = value
    def scalars(self):
        return types.SimpleNamespace(first=lambda: self._value)

class FakeSession:
    def __init__(self, execute_result=None):
        self.execute_result = execute_result
        self.added = []
        self.committed = False
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass
    async def execute(self, stmt):
        return self.execute_result
    def add(self, obj):
        self.added.append(obj)
    async def commit(self):
        self.committed = True
    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()

class FakeSessionMaker:
    def __init__(self, session):
        self.session = session
    def __call__(self):
        return self.session

def override_security(monkeypatch):
    monkeypatch.setattr(security, "get_password_hash", lambda pw: "hashed"+pw)
    monkeypatch.setattr(security, "verify_password", lambda p, h: p == h.replace("hashed", ""))
    monkeypatch.setattr(security, "create_access_token", lambda data: "token")
    monkeypatch.setattr(auth_router, "verify_password", lambda p, h: p == h.replace("hashed", ""))
    monkeypatch.setattr(auth_router, "create_access_token", lambda data: "token")
    monkeypatch.setattr(security.pwd_context, "verify", lambda a,b: True)

@pytest.fixture
def client(monkeypatch):
    return TestClient(app)

def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

def test_register_user(monkeypatch, client):
    session = FakeSession(FakeExecuteResult(None))
    override = lambda: FakeSessionMaker(session)
    app.dependency_overrides[auth_router.get_db_session] = override
    override_security(monkeypatch)
    resp = client.post("/auth/register", json={"email": "a@b.com", "password": "pw"})
    assert resp.status_code == 201
    assert session.committed
    app.dependency_overrides = {}

def test_register_existing_user(monkeypatch, client):
    session = FakeSession(FakeExecuteResult(object()))
    override = lambda: FakeSessionMaker(session)
    app.dependency_overrides[auth_router.get_db_session] = override
    override_security(monkeypatch)
    resp = client.post("/auth/register", json={"email": "a@b.com", "password": "pw"})
    assert resp.status_code == 400
    app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_login(monkeypatch):
    user = types.SimpleNamespace(id=uuid.uuid4(), email="a@b.com", hashed_password="hashedpw")
    session = FakeSession(FakeExecuteResult(user))
    sessionmaker = FakeSessionMaker(session)
    override_db = lambda: sessionmaker
    app.dependency_overrides[auth_router.get_db_session] = override_db
    override_security(monkeypatch)
    form = OAuth2PasswordRequestForm(username="a@b.com", password="pw", scope="")
    token = await auth_router.login_for_access_token(form, db=sessionmaker)
    assert token["access_token"] == "token"
    app.dependency_overrides = {}

def test_create_group(monkeypatch, client):
    user = types.SimpleNamespace(id=uuid.uuid4())
    result = FakeExecuteResult(user)
    session = FakeSession(result)
    override_db = lambda: FakeSessionMaker(session)
    app.dependency_overrides[groups_router.get_db_session] = override_db
    app.dependency_overrides[groups_router.get_current_user] = lambda: user
    app.dependency_overrides[groups_router.get_arq_pool] = lambda: types.SimpleNamespace(enqueue_job=lambda *a, **kw: None)
    resp = client.post("/groups/", json={"name": "g"})
    assert resp.status_code == 201
    assert session.committed
    app.dependency_overrides = {}

def test_send_message(monkeypatch, client):
    user = types.SimpleNamespace(id=uuid.uuid4())
    session = FakeSession()
    calls = {}
    class FakePool:
        async def enqueue_job(self, *a, **kw):
            calls['called']=True
    override_db = lambda: FakeSessionMaker(session)
    app.dependency_overrides[groups_router.get_db_session] = override_db
    app.dependency_overrides[groups_router.get_current_user] = lambda: user
    app.dependency_overrides[groups_router.get_arq_pool] = lambda: FakePool()
    gid = uuid.uuid4()
    resp = client.post(f"/groups/{gid}/messages", json={"content": "hi"})
    assert resp.status_code == 202
    assert calls.get('called')
    app.dependency_overrides = {}
