import os
from urllib.parse import urlparse
from arq import create_pool, ArqRedis
from arq.connections import RedisSettings

from shared.app.core.config import settings

REDIS_URL = settings.REDIS_URL
if not REDIS_URL:
    raise ValueError("REDIS_URL environment variable is not set")

# Parse the REDIS_URL using urllib for robustness
parsed = urlparse(REDIS_URL)
if not parsed.hostname or not parsed.port:
    raise ValueError(f"Invalid REDIS_URL format: {REDIS_URL}")

ARQ_REDIS_SETTINGS = RedisSettings(host=parsed.hostname, port=parsed.port)

_arq_pool: ArqRedis | None = None

async def init_arq_pool() -> ArqRedis:
    """Create the ARQ Redis pool if it doesn't already exist."""
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(ARQ_REDIS_SETTINGS)
    return _arq_pool


async def get_arq_pool() -> ArqRedis:
    """FastAPI dependency returning the initialized ARQ pool."""
    if _arq_pool is None:
        raise RuntimeError("ARQ pool has not been initialized")
    return _arq_pool


async def close_arq_pool() -> None:
    """Close the ARQ pool on application shutdown."""
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None
