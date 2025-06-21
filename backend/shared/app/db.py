from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from collections.abc import AsyncGenerator
import structlog

from .core.config import settings
from .core.logging import setup_logging

setup_logging()
logger = structlog.get_logger(__name__)

DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

try:
    engine = create_async_engine(DATABASE_URL)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    logger.info("db.engine_created")
except SQLAlchemyError as e:
    logger.error("db.connection_failed", error=str(e))
    raise RuntimeError(f"Failed to connect to database: {e}")

async def get_db_session() -> AsyncGenerator[async_sessionmaker, None]:
    """Dependency to get a DB session."""
    logger.debug("db.session_requested")
    yield AsyncSessionLocal
