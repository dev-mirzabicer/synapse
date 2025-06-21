from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from collections.abc import AsyncGenerator

from .core.config import settings

DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db_session() -> AsyncGenerator[async_sessionmaker, None]:
    """Dependency to get a DB session."""
    yield AsyncSessionLocal
