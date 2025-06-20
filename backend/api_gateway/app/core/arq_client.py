import os
from arq import create_pool
from arq.connections import RedisSettings

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise ValueError("REDIS_URL environment variable is not set")

# Parse the URL to create RedisSettings
# This is a simple parser; a more robust one might be needed for complex URLs
host, port = REDIS_URL.replace("redis://", "").split(":")
ARQ_REDIS_SETTINGS = RedisSettings(host=host, port=int(port))

async def get_arq_pool():
    """Dependency to get the ARQ redis pool."""
    return await create_pool(ARQ_REDIS_SETTINGS)