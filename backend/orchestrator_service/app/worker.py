import json
from arq import ArqRedis
from langchain_core.messages import HumanMessage

from shared.app.core.config import settings
from .graph.graph import graph_app # Import our compiled graph application

# We need a separate Redis client for publishing, as ARQ's pool is for its internal use.
# This ensures our publishing doesn't interfere with ARQ's operations.
import redis.asyncio as redis
redis_pool = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)


async def process_new_message(ctx, group_id: str, message_content: str, user_id: str):
    """
    This ARQ task is the main entry point for processing a new user message.
    It streams the output of the LangGraph application to the frontend via Redis Pub/Sub.
    """
    print(f"Processing new message for group {group_id}")

    # 1. Prepare the input for the graph.
    # The graph's input is a dictionary with a "messages" key.
    graph_input = {"messages": [HumanMessage(content=message_content)]}

    # 2. Configure the graph run.
    # The `thread_id` is crucial for the checkpointer to save and load
    # the state of the conversation correctly. We use the group_id for this.
    config = {"configurable": {"thread_id": group_id}}

    # 3. Stream the events from the graph.
    # `astream_events` provides a detailed, real-time feed of the graph's execution.
    # This is perfect for building a rich, responsive UI.
    try:
        async for event in graph_app.astream_events(graph_input, config, version="v1"):
            kind = event["event"]
            name = event["name"]
            
            # We translate graph events into a structured format for the frontend.
            if kind == "on_chat_model_stream":
                # A new chunk of content is available from an LLM.
                content = event["data"]["chunk"].content
                if content:
                    await _publish_event(group_id, "llm_chunk", {"content": content, "sender_alias": name})
            
            elif kind == "on_tool_start":
                # An agent is about to use a tool.
                await _publish_event(group_id, "agent_activity", {
                    "activity": f"Using tool: {event['name']}",
                    "details": event['data'].get('input'),
                    "sender_alias": name
                })

            elif kind == "on_tool_end":
                # A tool has finished executing.
                # TODO: Decide if we want to show raw tool output to the user.
                # For now, we'll just confirm it finished.
                await _publish_event(group_id, "agent_activity", {
                    "activity": f"Tool {event['name']} finished.",
                    "sender_alias": name
                })

    except Exception as e:
        print(f"Error processing graph for group {group_id}: {e}")
        # In case of a catastrophic failure, notify the frontend.
        await _publish_event(group_id, "error", {"detail": str(e)})

    # TODO (Phase 4): Implement a finalizer task.
    # After the stream is complete, enqueue a low-priority job to sync the final
    # conversation state from the Redis checkpoint back to the PostgreSQL database
    # for long-term, durable storage. This is a critical step for production robustness.


async def _publish_event(group_id: str, event_type: str, payload: dict):
    """Helper function to publish a structured event to Redis Pub/Sub."""
    channel = f"group:{group_id}"
    message = json.dumps({
        "event_type": event_type,
        "payload": payload
    })
    await redis_pool.publish(channel, message)


class WorkerSettings:
    """
    ARQ worker settings.
    """
    functions = [process_new_message]
    # We no longer need on_startup or on_shutdown for the context pool,
    # as we are managing our own Redis pool for publishing.