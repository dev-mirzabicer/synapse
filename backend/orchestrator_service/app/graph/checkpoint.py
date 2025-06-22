from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from shared.app.core.config import settings

# CORRECT: Use the async-native saver for consistency and correctness.
checkpointer_context = AsyncRedisSaver.from_conn_string(settings.REDIS_URL)