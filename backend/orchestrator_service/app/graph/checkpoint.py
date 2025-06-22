from langgraph.checkpoint.redis import RedisSaver
from shared.app.core.config import settings

# This now correctly returns the async context manager from the factory method.
# It will be resolved within the worker functions.
checkpointer_context = RedisSaver.from_conn_string(settings.REDIS_URL)