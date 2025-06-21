import json
import uuid
from redis.asyncio import Redis
from .state import GraphState
from shared.app.utils.message_serde import serialize_messages
from shared.app.db import AsyncSessionLocal
from shared.app.models.chat import Message
from sqlalchemy.dialects.postgresql import insert
from shared.app.core.config import settings
import structlog
from shared.app.core.logging import setup_logging

setup_logging()
logger = structlog.get_logger(__name__)


async def _persist_new_messages(state: GraphState, config: dict) -> None:
    """Persist any new messages and broadcast them over Redis."""
    last_saved = state.get("last_saved_index", 0)
    new_messages = state["messages"][last_saved:]
    if not new_messages:
        return

    async with AsyncSessionLocal() as session:
        redis = Redis.from_url(settings.REDIS_URL)
        try:
            for msg in new_messages:
                stmt = (
                    insert(Message)
                    .values(
                        id=getattr(msg, "id", uuid.uuid4()),
                        group_id=state["group_id"],
                        turn_id=state["turn_id"],
                        sender_alias=getattr(msg, "name", "system"),
                        content=str(msg.content),
                        meta=msg.dict(),
                    )
                    .on_conflict_do_nothing(index_elements=["id"])
                )
                await session.execute(stmt)
                await redis.publish(
                    f"group:{state['group_id']}",
                    json.dumps(msg.dict()),
                )
            await session.commit()
        finally:
            await redis.close()

    await config["checkpoint"].update_state(
        config,
        {"last_saved_index": last_saved + len(new_messages)},
    )


async def dispatch_node(state: GraphState, config: dict) -> dict:
    """Persist new messages and dispatch jobs based on the last message."""
    arq_pool = config["arq_pool"]
    thread_id = config["configurable"]["thread_id"]

    await _persist_new_messages(state, config)

    last_message = state["messages"][-1]

    if tool_calls := getattr(last_message, "tool_calls", []):
        messages_dict = serialize_messages(state["messages"])
        group_members_dict = [gm.dict() for gm in state["group_members"]]
        for call in tool_calls:
            logger.info("dispatch.tool", tool=call["name"], thread_id=thread_id)
            await arq_pool.enqueue_job(
                "run_tool",
                tool_name=call["name"],
                tool_args=call["args"],
                tool_call_id=call["id"],
                thread_id=thread_id,
            )
    elif next_actors := state.get("next_actors"):
        messages_dict = serialize_messages(state["messages"])
        group_members_dict = [gm.dict() for gm in state["group_members"]]
        for alias in next_actors:
            logger.info("dispatch.agent", alias=alias, thread_id=thread_id)
            await arq_pool.enqueue_job(
                "run_agent_llm",
                alias=alias,
                messages_dict=messages_dict,
                group_members_dict=group_members_dict,
                thread_id=thread_id,
            )
    return {}


async def sync_to_postgres_node(state: GraphState, config: dict) -> dict:
    """Persist any remaining messages before finishing the turn."""
    thread_id = config["configurable"]["thread_id"]
    logger.info("sync_to_postgres.start", thread_id=thread_id)

    full_state = await config["checkpoint"].get(config)
    await _persist_new_messages(full_state, config)

    logger.info("sync_to_postgres.complete", thread_id=thread_id)
    return {}
