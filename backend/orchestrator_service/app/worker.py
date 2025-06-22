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
    run_control_config = {"configurable": {"thread_id": group_id}}
    
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
        # CORRECTED: Inject both the checkpointer and arq_pool as resources
        # using with_config(). This is the robust way.
        graph_with_resources = graph_app_uncompiled.with_config({
            "checkpointer": checkpointer,
            "arq_pool": arq_pool
        })
        
        # Pass only the run-control config to ainvoke()
        await graph_with_resources.ainvoke(graph_input, config=run_control_config)


async def continue_turn(ctx, thread_id: str):
    """Continues a turn after an execution_worker has updated the state."""
    logger.info("continue_turn", thread_id=thread_id)
    run_control_config = {"configurable": {"thread_id": thread_id}}
    arq_pool: ArqRedis = ctx["redis"]

    with checkpointer_context as checkpointer:
        # CORRECTED: Inject resources here as well.
        graph_with_resources = graph_app_uncompiled.with_config({
            "checkpointer": checkpointer,
            "arq_pool": arq_pool
        })
        
        # We invoke with empty input and the run-control config.
        await graph_with_resources.ainvoke(None, config=run_control_config)


class WorkerSettings:
    functions = [start_turn, continue_turn]
    queue_name = "orchestrator_queue"
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    async def on_startup(ctx):
        logger.info("worker.startup", redis_host=settings.REDIS_URL)

    async def on_shutdown(ctx):
        logger.info("worker.shutdown")