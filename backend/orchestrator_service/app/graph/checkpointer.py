from langgraph.checkpoint.redis import RedisSaver
from shared.app.core.config import settings

# Instantiate the checkpointer.
# By creating it here, we can easily import this single instance
# wherever we need it, ensuring we use the same configuration everywhere.
# The checkpointer handles all the logic for saving and loading
# the state of our graph to and from Redis.
checkpoint = RedisSaver.from_conn_string(settings.REDIS_URL)