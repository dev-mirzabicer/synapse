import os
from urllib.parse import urlparse
from arq import create_pool
from arq.connections import RedisSettings

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise ValueError("REDIS_URL environment variable is not set")

# Parse the REDIS_URL using urllib for robustness
parsed = urlparse(REDIS_URL)
if not parsed.hostname or not parsed.port:
    raise ValueError(f"Invalid REDIS_URL format: {REDIS_URL}")

ARQ_REDIS_SETTINGS = RedisSettings(host=parsed.hostname, port=parsed.port)

async def get_arq_pool():
    """Dependency to get the ARQ redis pool."""
    try:
        return await create_pool(ARQ_REDIS_SETTINGS)
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Redis: {e}")


