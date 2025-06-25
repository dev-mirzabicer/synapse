import re
import uuid
from typing import List, Union, Dict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
import structlog

from ..core.config import settings
from ..schemas.groups import GroupMemberRead
from .prompts import AGENT_BASE_PROMPT, ORCHESTRATOR_PROMPT, STOP_SEQUENCE
from .tools import TOOL_REGISTRY

logger = structlog.get_logger(__name__)


def _normalize_and_clean_llm_content(content: Union[str, List[Union[str, Dict[str, any]]]]) -> str:
    """
    Robustly normalizes LLM content and cleans the stop sequence. It handles:
    - Simple string content.
    - A list of strings.
    - Multi-part content (e.g., from Gemini), extracting and joining text parts.
    - Strips the STOP_SEQUENCE from the final output.
    """
    normalized_content = ""
    if isinstance(content, str):
        normalized_content = content
    elif isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                text_parts.append(str(part["text"]))
        
        if not text_parts:
            logger.warn("run_agent.normalize_content.no_text_parts_found", content_received=content)
            normalized_content = str(content) if content else ""
        else:
            normalized_content = "\n".join(text_parts)
            if len(text_parts) > 1:
                logger.info(
                    "run_agent.normalize_content.joined_multi_part_response",
                    parts_count=len(text_parts),
                    final_content_preview=normalized_content[:100]+"..."
                )
    else:
        logger.warn("run_agent.normalize_content.unhandled_content_type", content_type=type(content).__name__, content_preview=str(content)[:100]+"...")
        normalized_content = str(content)

    # Clean the stop sequence from the final, normalized content.
    if STOP_SEQUENCE in normalized_content:
        normalized_content = normalized_content.split(STOP_SEQUENCE, 1)[0].strip()
        
    return normalized_content


async def run_agent(
    messages: list[BaseMessage], members: list[GroupMemberRead], alias: str
) -> BaseMessage:
    logger.info(
        "run_agent.entry",
        agent_alias=alias,
        num_messages_history=len(messages),
        last_message_type=type(messages[-1]).__name__ if messages else "N/A",
        last_message_sender=getattr(messages[-1], "name", "N/A") if messages else "N/A",
        num_group_members_config=len(members),
    )

    try:
        member_config = next((m for m in members if m.alias == alias), None)
        if not member_config:
            logger.error("run_agent.config_not_found", agent_alias=alias)
            error_msg = SystemMessage(
                content=f"Configuration not found for agent alias: {alias}. Cannot proceed.",
                name="system_error",
            )
            error_msg.id = str(uuid.uuid4())
            return error_msg

        logger.debug(
            "run_agent.member_config_details",
            agent_alias=alias,
            config=member_config.model_dump(),
        )

        # --- Prompt Construction ---
        available_team_members_str = ", ".join(
            [f"@[{m.alias}]" for m in members if m.alias not in [alias, "Orchestrator", "User"]]
        ) or "None"

        if alias == "Orchestrator":
            system_prompt_content = ORCHESTRATOR_PROMPT.format(
                available_team_members=available_team_members_str
            )
        else:
            # Base prompt + tools + role-specific prompt
            base_prompt_with_alias = AGENT_BASE_PROMPT.replace("`Your Alias`", f"`{alias}`").replace(
                "{tool_list}",
                "\n".join(f"- {tool.name}: {tool.description}" for tool in TOOL_REGISTRY.values())
            ) # Adding this because for some reason LangGraph doesn't handle the list well # TODO: remove this when LangGraph is fixed
            system_prompt_content = f"{base_prompt_with_alias}\n{member_config.system_prompt}"

        prompt_for_llm: list[BaseMessage] = [
            SystemMessage(content=system_prompt_content),
            *messages,
        ]

        logger.debug(
            "run_agent.constructed_llm_prompt_summary",
            agent_alias=alias,
            system_prompt_length=len(system_prompt_content),
            num_history_messages_in_prompt=len(messages),
            total_messages_in_llm_prompt=len(prompt_for_llm),
        )

        # --- LLM and Tool Configuration ---
        provider = getattr(member_config, "provider", "openai")
        model = getattr(member_config, "model", "gpt-4o")
        temperature = getattr(member_config, "temperature", 0.1)
        logger.info(
            "run_agent.llm_parameters",
            agent_alias=alias,
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
        
        # Bind Stop Sequence
        llm_instance = llm_instance.bind(stop=[STOP_SEQUENCE])

        # --- Bind Tools ---
        allowed_tool_names = member_config.tools or []
        allowed_tools_resolved = [TOOL_REGISTRY[name] for name in allowed_tool_names if name in TOOL_REGISTRY]
        
        if len(allowed_tool_names) != len(allowed_tools_resolved):
            unresolved = set(allowed_tool_names) - set(t.name for t in allowed_tools_resolved)
            logger.warn("run_agent.tools_not_found_in_registry", agent_alias=alias, unresolved_tools=list(unresolved))

        llm_with_tools = llm_instance.bind_tools(allowed_tools_resolved) if allowed_tools_resolved else llm_instance

        # --- LLM Invocation and Response Handling ---
        logger.info("run_agent.invoking_llm", agent_alias=alias, has_tools_bound=bool(allowed_tools_resolved))
        raw_llm_response: BaseMessage = await llm_with_tools.ainvoke(prompt_for_llm)

        logger.debug(
            "run_agent.raw_llm_response_received",
            agent_alias=alias,
            details={
                "type": type(raw_llm_response).__name__,
                "content_preview": str(raw_llm_response.content)[:150] + "...",
                "tool_calls": getattr(raw_llm_response, "tool_calls", None),
            },
        )

        # Ensure we have an AIMessage to work with
        final_response_message = raw_llm_response if isinstance(raw_llm_response, AIMessage) else AIMessage(content=raw_llm_response.content)

        # Robustly normalize and clean the content
        final_response_message.content = _normalize_and_clean_llm_content(final_response_message.content)

        # Assign metadata
        final_response_message.name = alias
        final_response_message.id = str(uuid.uuid4())

        logger.info(
            "run_agent.success",
            agent_alias=alias,
            final_response_id=final_response_message.id,
            final_response_name=final_response_message.name,
            final_response_type=type(final_response_message).__name__,
            final_response_content_snippet=final_response_message.content[:100] + "...",
            final_response_tool_calls=getattr(final_response_message, "tool_calls", None),
        )
        return final_response_message

    except Exception as e:
        logger.error(
            "run_agent.unhandled_exception", agent_alias=alias, error=str(e), exc_info=True
        )
        error_msg = SystemMessage(
            content=f"Agent '{alias}' encountered an unhandled error: {str(e)}",
            name="system_error",
        )
        error_msg.id = str(uuid.uuid4())
        return error_msg