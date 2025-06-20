import os
import uuid

# TODO (Phase 1): Set up proper DB session handling like in the api_gateway
# For now, we'll create a new engine here.
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from shared.app.models.chat import Message

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine)

async def process_turn(ctx, group_id: str, turn_id: str):
    """
    This function is executed by the ARQ worker.
    It represents the simplest version of our LangGraph orchestrator.
    """
    print(f"Processing turn {turn_id} for group {group_id}")
    
    # --- LangGraph v1 Logic ---
    # 1. Fetch conversation history (omitted for brevity)
    # 2. Call the LLM
    # TODO (Phase 1): Replace with a real LLM call
    orchestrator_response_content = f"This is a dummy response for turn {turn_id}."
    
    # 3. Save the response to the database
    orchestrator_message = Message(
        group_id=uuid.UUID(group_id),
        turn_id=uuid.UUID(turn_id),
        sender_alias="Orchestrator",
        content=orchestrator_response_content
    )
    async with AsyncSessionLocal() as session:
        session.add(orchestrator_message)
        await session.commit()

    # 4. Notify frontend via Redis Pub/Sub
    # TODO (Phase 1.4): Implement Redis Pub/Sub notification
    print(f"Finished processing turn {turn_id}. Response saved.")

    return {"status": "ok", "response": orchestrator_response_content}


class WorkerSettings:
    """
    ARQ worker settings.
    The 'functions' list tells ARQ which functions are available to be called as jobs.
    """
    functions = [process_turn]