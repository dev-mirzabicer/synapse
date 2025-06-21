from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from collections.abc import AsyncGenerator

from .core.config import settings

DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

try:
    engine = create_async_engine(DATABASE_URL)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
except SQLAlchemyError as e:
    raise RuntimeError(f"Failed to connect to database: {e}")

async def get_db_session() -> AsyncGenerator[async_sessionmaker, None]:
    """Dependency to get a DB session."""
    yield AsyncSessionLocal
