import re
from .state import GraphState
import structlog

logger = structlog.get_logger(__name__)

MENTION_REGEX = r'@\[([\w\s.-]+?)\]'
MAX_TURNS = 20


def route_logic(state: GraphState) -> dict:
    """
    Runs the routing logic and returns a dictionary of state updates.
    This is no longer a conditional edge function.
    """
    turn_id = state.get("turn_id")
    group_id = state.get("group_id")
    
    logger.debug(
        "route_logic.entry",
        turn_id=turn_id,
        group_id=group_id,
        current_turn_count=state.get("turn_count", 0),
        messages_in_state_count=len(state.get("messages", [])),
        last_message_sender=getattr(state["messages"][-1], "name", "N/A") if state.get("messages") else "N/A",
        last_message_content_snippet=str(state["messages"][-1].content)[:50]+"..." if state.get("messages") else "N/A",
        current_next_actors=state.get("next_actors")
    )

    turn_count = state.get("turn_count", 0) + 1
    logger.info("route_logic.turn_increment", previous_turn_count=state.get("turn_count", 0), new_turn_count=turn_count, group_id=group_id, turn_id=turn_id)

    if turn_count > MAX_TURNS:
        logger.warn("route_logic.max_turns_exceeded", turn_count=turn_count, max_turns=MAX_TURNS, group_id=group_id, turn_id=turn_id)
        update = {"next_actors": [], "turn_count": turn_count}
        logger.info("route_logic.decision", reason="max_turns_exceeded", update=update, group_id=group_id, turn_id=turn_id)
        return update

    if not state["messages"]:
        logger.error("route_logic.no_messages_in_state", group_id=group_id, turn_id=turn_id)
        update = {"next_actors": ["Orchestrator"], "turn_count": turn_count, "error_reason": "No messages in state"}
        logger.info("route_logic.decision", reason="no_messages_in_state", update=update, group_id=group_id, turn_id=turn_id)
        return update

    last_message = state["messages"][-1]
    sender_name = getattr(last_message, "name", "system")

    content_str = last_message.content
    if isinstance(content_str, list):
        logger.warn("route_logic.list_content_in_last_message", last_message_content_type=type(content_str).__name__, group_id=group_id, turn_id=turn_id)
        content_str = "\n\n".join(map(str, content_str))
    elif not isinstance(content_str, str):
        logger.warn("route_logic.non_string_content_in_last_message", last_message_content_type=type(content_str).__name__, group_id=group_id, turn_id=turn_id)
        content_str = str(content_str)

    logger.debug(
        "route_logic.processing_message",
        sender_name=sender_name,
        content_snippet=content_str[:100] + "...",
        last_message_type=type(last_message).__name__,
        last_message_id=getattr(last_message, "id", "N/A"),
        turn_count=turn_count,
        group_id=group_id,
        turn_id=turn_id
    )

    if sender_name == "system_error":
        logger.warn("route_logic.system_error_detected", error_message_content=content_str, group_id=group_id, turn_id=turn_id)
        update = {"next_actors": ["Orchestrator"], "turn_count": turn_count}
        logger.info("route_logic.decision", reason="system_error_detected", update=update, group_id=group_id, turn_id=turn_id)
        return update

    if "TASK_COMPLETE" in content_str and sender_name == "Orchestrator":
        logger.info("route_logic.task_complete_detected", sender_name=sender_name, group_id=group_id, turn_id=turn_id)
        update = {"next_actors": [], "turn_count": turn_count}
        logger.info("route_logic.decision", reason="task_complete_detected", update=update, group_id=group_id, turn_id=turn_id)
        return update

    if getattr(last_message, "tool_calls", None):
        logger.info("route_logic.tool_calls_detected", tool_calls=getattr(last_message, "tool_calls"), group_id=group_id, turn_id=turn_id)
        update = {"turn_count": turn_count, "next_actors": []}
        logger.info("route_logic.decision", reason="tool_calls_detected", update=update, group_id=group_id, turn_id=turn_id)
        return update

    mentions = re.findall(MENTION_REGEX, content_str)
    if mentions:
        unique_mentions = set(m for m in mentions if m != sender_name)
        next_actors = list(unique_mentions)
        logger.info("route_logic.mentions_found", raw_mentions=mentions, unique_next_actors=next_actors, sender_name=sender_name, group_id=group_id, turn_id=turn_id)
        update = {"next_actors": next_actors, "turn_count": turn_count}
        logger.info("route_logic.decision", reason="mentions_found", update=update, group_id=group_id, turn_id=turn_id)
        return update

    if sender_name != "Orchestrator":
        logger.info("route_logic.non_orchestrator_sender_no_mentions_or_tools", sender_name=sender_name, action="defaulting_to_orchestrator", group_id=group_id, turn_id=turn_id)
        update = {"next_actors": ["Orchestrator"], "turn_count": turn_count}
        logger.info("route_logic.decision", reason="default_to_orchestrator", update=update, group_id=group_id, turn_id=turn_id)
        return update

    logger.info("route_logic.orchestrator_spoke_no_commands_or_mentions", sender_name=sender_name, action="ending_turn_no_further_dispatch", group_id=group_id, turn_id=turn_id)
    update = {"next_actors": [], "turn_count": turn_count}
    logger.info("route_logic.decision", reason="orchestrator_no_commands_end_turn", update=update, group_id=group_id, turn_id=turn_id)
    return update