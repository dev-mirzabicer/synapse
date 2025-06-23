import os
import pytest
import pytest_asyncio

@pytest.fixture(scope="session", autouse=True)
def set_test_env():
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///file::memory:?cache=shared")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("SECRET_KEY", "testsecret")
    os.environ.setdefault("TAVILY_API_KEY", "dummy")
    os.environ.setdefault("OPENAI_API_KEY", "dummy")
    os.environ.setdefault("GEMINI_API_KEY", "dummy")
    os.environ.setdefault("CLAUDE_API_KEY", "dummy")
    yield

@pytest_asyncio.fixture(scope="session")
async def engine(set_test_env):
    from backend.shared.app.db import engine
    from backend.shared.app.models import base  # ensure models imported
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.drop_all)

@pytest.fixture
def db_session(engine):
    from backend.shared.app.db import AsyncSessionLocal
    return AsyncSessionLocal
