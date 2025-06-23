import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "api_gateway"))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///file::memory:?cache=shared")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

import uuid
import pytest
from backend.api_gateway.app.api.routers import auth, groups
from backend.shared.app.schemas.auth import UserCreate
from backend.shared.app.schemas.groups import GroupCreate, AgentConfigCreate
from backend.shared.app.models.chat import User
from backend.api_gateway.app.core.security import get_password_hash

@pytest.mark.asyncio
async def test_register_and_login(db_session):
    user_in = UserCreate(email="u@example.com", password="pw")
    await auth.register_user(user_in, db=db_session)
    form = type("F", (), {"username": "u@example.com", "password": "pw"})()
    token = await auth.login_for_access_token(form, db=db_session)
    assert token["access_token"]

@pytest.mark.asyncio
async def test_create_group_and_send_message(db_session, monkeypatch):
    # create user
    async with db_session() as session:
        user = User(email="owner@example.com", hashed_password=get_password_hash("pw"))
        session.add(user)
        await session.commit()
        await session.refresh(user)
    # override arq pool
    class FakeArq:
        def __init__(self):
            self.jobs=[]
        async def enqueue_job(self,*a,**k):
            self.jobs.append((a,k))
    fake_arq = FakeArq()
    monkeypatch.setattr("backend.api_gateway.app.api.routers.groups.ArqRedis", object)
    monkeypatch.setattr("backend.api_gateway.app.api.routers.groups.get_arq_pool", lambda: fake_arq)
    group_data = GroupCreate(name="g", members=[AgentConfigCreate(alias="A", role_prompt="r")])
    group = await groups.create_group(group_data, db=db_session, current_user=user)
    assert group.id
    # send message
    msg = await groups.send_message(group.id, message_in=type("M", (), {"content":"hi"})(), db=db_session, arq_pool=fake_arq, current_user=user)
    assert msg.content == "hi"
    assert fake_arq.jobs
