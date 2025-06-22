import structlog
from arq import ArqRedis
from arq.connections import RedisSettings
from langchain_core.messages import HumanMessage
from graph.graph import graph_app_uncompiled
from graph.checkpoint import checkpointer_context
from sqlalchemy import select
from shared.app.db import AsyncSessionLocal
from shared.app.models.chat import GroupMember
from shared.app.schemas.groups import GroupMemberRead
from shared.app.core.logging import setup_logging
from shared.app.core.config import settings

setup_logging()
logger = structlog.get_logger(__name__)


async def start_turn(ctx, group_id: str, message_content: str, user_id: str, message_id: str, turn_id: str):
    """Starts a new turn initiated by a user."""
    logger.info("start_turn", group_id=group_id)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GroupMember).where(GroupMember.group_id == group_id)
        )
        members = [GroupMemberRead.model_validate(m) for m in result.scalars().all()]

    user_msg = HumanMessage(content=message_content)
    user_msg.id = message_id
    user_msg.name = "User"

    graph_input = {
        "messages": [user_msg],
        "group_id": group_id,
        "group_members": members,
        "turn_count": 0,
        "last_saved_index": 0,
        "turn_id": turn_id,
    }
    
    arq_pool: ArqRedis = ctx["redis"]
    
    with checkpointer_context as checkpointer:
        # CORRECT: All runtime resources and identifiers must be placed
        # inside the 'configurable' dictionary, as per LangGraph documentation.
        invocation_config = {
            "configurable": {
                "thread_id": group_id,
                "checkpointer": checkpointer,
                "arq_pool": arq_pool,
            }
        }
        
        # Pass the correctly structured config to ainvoke()
        await graph_app_uncompiled.ainvoke(graph_input, config=invocation_config)


async def continue_turn(ctx, thread_id: str):
    """Continues a turn after an execution_worker has updated the state."""
    logger.info("continue_turn", thread_id=thread_id)
    arq_pool: ArqRedis = ctx["redis"]

    with checkpointer_context as checkpointer:
        # CORRECT: The same structured config is needed here for consistency.
        invocation_config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpointer": checkpointer,
                "arq_pool": arq_pool,
            }
        }
        
        # We invoke with empty input and the structured config.
        await graph_app_uncompiled.ainvoke(None, config=invocation_config)


class WorkerSettings:
    functions = [start_turn, continue_turn]
    queue_name = "orchestrator_queue"
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    async def on_startup(ctx):
        logger.info("worker.startup", redis_host=settings.REDIS_URL)

    async def on_shutdown(ctx):
        logger.info("worker.shutdown")