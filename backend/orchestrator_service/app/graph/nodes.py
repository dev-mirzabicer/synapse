from .state import GraphState
from shared.app.utils.message_serde import serialize_messages
from shared.app.db import AsyncSessionLocal
from shared.app.models.chat import Message
from sqlalchemy.dialects.postgresql import insert
import structlog
from shared.app.core.logging import setup_logging

setup_logging()
logger = structlog.get_logger(__name__)


async def dispatch_node(state: GraphState, config: dict) -> dict:
    """Dispatches jobs to execution_workers based on the last message."""
    arq_pool = config["arq_pool"]
    thread_id = config["configurable"]["thread_id"]
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
    """Saves the final, complete conversation history to PostgreSQL."""
    thread_id = config["configurable"]["thread_id"]
    logger.info("sync_to_postgres.start", thread_id=thread_id)

    full_state = await config["checkpoint"].get(config)
    messages_to_save = full_state["messages"]

    async with AsyncSessionLocal() as session:
        for msg in messages_to_save:
            # This is a simplified conversion. A real implementation needs to handle
            # different message types and serialize them correctly.
            stmt = (
                insert(Message)
                .values(
                    id=msg.id,
                    group_id=state["group_id"],
                    turn_id=state.get(
                        "turn_id", "legacy_turn"
                    ),  # Add turn_id to state if needed
                    sender_alias=getattr(msg, "name", "system"),
                    content=str(msg.content),
                    meta=msg.dict(),  # Store the full message object for perfect reconstruction
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )  # Idempotent insert
            await session.execute(stmt)
        await session.commit()
    logger.info("sync_to_postgres.complete", thread_id=thread_id)
    return {}
