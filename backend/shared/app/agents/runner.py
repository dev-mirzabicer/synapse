import re
import uuid
from typing import List, Union, Dict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain.load.dump import dumpd
import structlog

from ..core.config import settings
from ..schemas.groups import GroupMemberRead
from .prompts import AGENT_BASE_PROMPT, ORCHESTRATOR_PROMPT, STOP_SEQUENCE
from .tools import TOOL_REGISTRY
from ..utils.message_serde import serialize_messages # Import for logging

logger = structlog.get_logger(__name__)


def _normalize_and_clean_llm_content(content: Union[str, List[Union[str, Dict[str, any]]]]) -> str:
    """
    Robustly normalizes LLM content and cleans the stop sequence. It handles:
    - Simple string content.
    - A list of strings or dicts (e.g., from Gemini multi-part), taking only the first text part.
    - Strips the STOP_SEQUENCE from the final output.
    """
    text_content = ""
    
    # <<< START: FIX FOR MULTI-PART RESPONSE ANOMALY >>>
    # Defensively handle the case where the LLM returns a list of content parts.
    # We will treat the first text-like part as the primary response and discard others.
    if isinstance(content, list) and content:
        first_part = content[0]
        if isinstance(first_part, str):
            text_content = first_part
        elif isinstance(first_part, dict) and "text" in first_part:
            text_content = str(first_part["text"])
        else:
            # Fallback for unexpected list content
            logger.warn("run_agent.normalize_content.unhandled_list_part_type", part_type=type(first_part).__name__, content_preview=str(content)[:150]+"...")
            text_content = str(first_part)
        
        if len(content) > 1:
            logger.warn("run_agent.normalize_content.discarded_extra_parts", total_parts=len(content), first_part_preview=text_content[:100]+"...")

    elif isinstance(content, str):
        text_content = content
    # <<< END: FIX FOR MULTI-PART RESPONSE ANOMALY >>>
    
    else:
        logger.warn("run_agent.normalize_content.unhandled_content_type", content_type=type(content).__name__, content_preview=str(content)[:100]+"...")
        text_content = str(content)

    # Clean the stop sequence from the final, normalized content.
    if STOP_SEQUENCE in text_content:
        text_content = text_content.split(STOP_SEQUENCE, 1)[0].strip()
        
    return text_content


async def run_agent(
    messages: list[BaseMessage], members: list[GroupMemberRead], alias: str
) -> BaseMessage:
    turn_id_for_log = "N/A"
    if messages and messages[-1].additional_kwargs.get("turn_id"):
        turn_id_for_log = messages[-1].additional_kwargs.get("turn_id")
    
    logger.info(
        "run_agent.entry",
        agent_alias=alias,
        turn_id=turn_id_for_log,
        num_messages_history=len(messages),
        last_message_type=type(messages[-1]).__name__ if messages else "N/A",
        last_message_sender=getattr(messages[-1], "name", "N/A") if messages else "N/A",
        num_group_members_config=len(members),
    )

    try:
        member_config = next((m for m in members if m.alias == alias), None)
        if not member_config:
            logger.error("run_agent.config_not_found", agent_alias=alias, turn_id=turn_id_for_log)
            error_msg = SystemMessage(
                content=f"Configuration not found for agent alias: {alias}. Cannot proceed.",
                name="system_error",
            )
            error_msg.id = str(uuid.uuid4())
            return error_msg

        logger.debug(
            "run_agent.member_config_details",
            agent_alias=alias,
            turn_id=turn_id_for_log,
            config=member_config.model_dump(),
        )

        available_team_members_str = ", ".join(
            [f"@[{m.alias}]" for m in members if m.alias not in [alias, "Orchestrator", "User"]]
        ) or "None"
        
        if alias == "Orchestrator":
            system_prompt_content = member_config.system_prompt.format(
                available_team_members=available_team_members_str
            )
        else:
            tool_list_str = "\n".join(f"- {tool.name}: {tool.description}" for tool in TOOL_REGISTRY.values()) or "No tools available."
            system_prompt_content = member_config.system_prompt.replace("`Your Alias`", f"`{alias}`").replace(
                "{tool_list}", tool_list_str
            )

        prompt_for_llm: list[BaseMessage] = [
            SystemMessage(content=system_prompt_content),
            *messages,
        ]

        logger.debug(
            "run_agent.final_prompt_for_llm",
            agent_alias=alias,
            turn_id=turn_id_for_log,
            prompt_messages=serialize_messages(prompt_for_llm),
        )

        provider = getattr(member_config, "provider", "openai")
        model = getattr(member_config, "model", "gpt-4o")
        temperature = getattr(member_config, "temperature", 0.1)
        logger.info(
            "run_agent.llm_parameters",
            agent_alias=alias,
            turn_id=turn_id_for_log,
            provider=provider,
            model=model,
            temperature=temperature,
        )

        llm_instance = None
        if provider == "openai":
            from langchain_openai import ChatOpenAI
            if not settings.OPENAI_API_KEY:
                raise ValueError(f"OpenAI API key not configured for agent {alias}")
            llm_instance = ChatOpenAI(model=model, temperature=temperature, api_key=settings.OPENAI_API_KEY)
        elif provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            if not settings.GEMINI_API_KEY:
                raise ValueError(f"Gemini API key not configured for agent {alias}")
            llm_instance = ChatGoogleGenerativeAI(model=model, temperature=temperature, google_api_key=settings.GEMINI_API_KEY)
        elif provider == "claude":
            from langchain_anthropic import ChatAnthropic
            if not settings.CLAUDE_API_KEY:
                raise ValueError(f"Claude API key not configured for agent {alias}")
            llm_instance = ChatAnthropic(model=model, temperature=temperature, anthropic_api_key=settings.CLAUDE_API_KEY)
        else:
            raise ValueError(f"Unknown or unsupported LLM provider: {provider} for agent {alias}")
        
        llm_instance = llm_instance.bind(stop=[STOP_SEQUENCE])

        allowed_tool_names = member_config.tools or []
        allowed_tools_resolved = [TOOL_REGISTRY[name] for name in allowed_tool_names if name in TOOL_REGISTRY]
        
        if len(allowed_tool_names) != len(allowed_tools_resolved):
            unresolved = set(allowed_tool_names) - set(t.name for t in allowed_tools_resolved)
            logger.warn("run_agent.tools_not_found_in_registry", agent_alias=alias, unresolved_tools=list(unresolved))

        llm_with_tools = llm_instance.bind_tools(allowed_tools_resolved) if allowed_tools_resolved else llm_instance

        logger.info("run_agent.invoking_llm", agent_alias=alias, turn_id=turn_id_for_log, has_tools_bound=bool(allowed_tools_resolved))
        raw_llm_response: BaseMessage = await llm_with_tools.ainvoke(prompt_for_llm)

        logger.debug(
            "run_agent.raw_llm_response_received",
            agent_alias=alias,
            turn_id=turn_id_for_log,
            raw_response_object=dumpd(raw_llm_response),
        )

        final_response_message = raw_llm_response if isinstance(raw_llm_response, AIMessage) else AIMessage(content=raw_llm_response.content)
        final_response_message.content = _normalize_and_clean_llm_content(final_response_message.content)
        final_response_message.name = alias
        final_response_message.id = str(uuid.uuid4())

        # <<< START: FIX FOR turn_id PROPAGATION >>>
        # Ensure the turn_id is carried back with the response message.
        if turn_id_for_log != "N/A":
            final_response_message.additional_kwargs["turn_id"] = turn_id_for_log
        # <<< END: FIX FOR turn_id PROPAGATION >>>

        logger.info(
            "run_agent.success",
            agent_alias=alias,
            turn_id=turn_id_for_log,
            final_response_id=final_response_message.id,
            final_response_name=final_response_message.name,
            final_response_type=type(final_response_message).__name__,
            final_response_content_snippet=final_response_message.content[:100] + "...",
            final_response_tool_calls=getattr(final_response_message, "tool_calls", None),
        )
        return final_response_message

    except Exception as e:
        logger.error(
            "run_agent.unhandled_exception", agent_alias=alias, turn_id=turn_id_for_log, error=str(e), exc_info=True
        )
        error_msg = SystemMessage(
            content=f"Agent '{alias}' encountered an unhandled error: {str(e)}",
            name="system_error",
        )
        error_msg.id = str(uuid.uuid4())
        # Also propagate turn_id on error messages
        if turn_id_for_log != "N/A":
            error_msg.additional_kwargs["turn_id"] = turn_id_for_log
        return error_msg