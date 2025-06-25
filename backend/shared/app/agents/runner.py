from langchain_core.messages import BaseMessage, SystemMessage, AIMessage
import structlog
import uuid

from .tools import TOOL_REGISTRY
from ..schemas.groups import GroupMemberRead
from ..core.config import settings

logger = structlog.get_logger(__name__)

async def run_agent(messages: list[BaseMessage], members: list[GroupMemberRead], alias: str) -> BaseMessage:
    logger.info(
        "run_agent.entry",
        agent_alias=alias,
        num_messages_history=len(messages),
        last_message_type=type(messages[-1]).__name__ if messages else "N/A",
        last_message_sender=getattr(messages[-1], "name", "N/A") if messages else "N/A",
        num_group_members_config=len(members)
    )

    try:
        member_config = next((m for m in members if m.alias == alias), None)
        if not member_config:
            logger.error("run_agent.config_not_found", agent_alias=alias)
            error_msg = SystemMessage(
                content=f"Configuration not found for agent alias: {alias}. Cannot proceed.",
                name="system_error"
            )
            error_msg.id = str(uuid.uuid4())
            return error_msg

        logger.debug("run_agent.member_config_details", agent_alias=alias, config=member_config.model_dump())

        available_team_members = [f"@[{m.alias}]" for m in members if m.alias != alias and m.alias != "Orchestrator" and m.alias != "User"]
        available_team_members_str = ", ".join(available_team_members) if available_team_members else "None"
        
        system_prompt_content = f"{member_config.system_prompt}\n\nAvailable team members for delegation (excluding yourself, Orchestrator, User): {available_team_members_str}."
        
        prompt_for_llm: list[BaseMessage] = [SystemMessage(content=system_prompt_content), *messages]
        
        # For very detailed debugging, you might log the full prompt, but be wary of size/PII.
        logger.debug(
            "run_agent.constructed_llm_prompt_summary",
            agent_alias=alias,
            system_prompt_length=len(system_prompt_content),
            num_history_messages_in_prompt=len(messages),
            total_messages_in_llm_prompt=len(prompt_for_llm)
        )
        # Example of logging full prompt (can be very verbose):
        # logger.trace("run_agent.full_llm_prompt", agent_alias=alias, prompt_messages=[msg.model_dump() for msg in prompt_for_llm])


        provider = getattr(member_config, "provider", "openai")
        model = getattr(member_config, "model", "gpt-4o")
        temperature = getattr(member_config, "temperature", 0.1)
        logger.info("run_agent.llm_parameters", agent_alias=alias, provider=provider, model=model, temperature=temperature)

        llm_instance: BaseMessage # Placeholder for type hint
        if provider == "openai":
            from langchain_openai import ChatOpenAI
            if not settings.OPENAI_API_KEY:
                raise ValueError(f"OpenAI API key not configured for agent {alias}")
            llm_instance = ChatOpenAI(model=model, temperature=temperature, openai_api_key=settings.OPENAI_API_KEY)
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
            logger.error("run_agent.unknown_provider", agent_alias=alias, provider_name=provider)
            raise ValueError(f"Unknown or unsupported LLM provider: {provider} for agent {alias}")

        allowed_tool_names = member_config.tools or []
        allowed_tools_resolved = []
        if allowed_tool_names:
            for tool_name in allowed_tool_names:
                tool_obj = TOOL_REGISTRY.get(tool_name)
                if tool_obj:
                    allowed_tools_resolved.append(tool_obj)
                else:
                    logger.warn("run_agent.tool_not_found_in_registry", agent_alias=alias, tool_name=tool_name)
        
        logger.info("run_agent.tools_configuration", agent_alias=alias, requested_tools=allowed_tool_names, resolved_tools_count=len(allowed_tools_resolved), resolved_tool_names=[t.name for t in allowed_tools_resolved if hasattr(t, 'name')])

        llm_with_tools = llm_instance.bind_tools(allowed_tools_resolved) if allowed_tools_resolved else llm_instance

        logger.info("run_agent.invoking_llm_with_tools", agent_alias=alias, has_tools_bound=bool(allowed_tools_resolved))
        raw_llm_response: BaseMessage = await llm_with_tools.ainvoke(prompt_for_llm)
        
        # Log raw response details
        raw_response_details = {
            "type": type(raw_llm_response).__name__,
            "content_preview": str(raw_llm_response.content)[:100]+"...",
            "name_attr": getattr(raw_llm_response, "name", "N/A"),
            "id_attr": getattr(raw_llm_response, "id", "N/A"),
            "tool_calls_attr": getattr(raw_llm_response, "tool_calls", None)
        }
        logger.debug("run_agent.raw_llm_response_received", agent_alias=alias, details=raw_response_details)

        # Standardize response: AIMessage, content as string, name set, ID set.
        final_response_message: BaseMessage
        if isinstance(raw_llm_response, AIMessage):
            final_response_message = raw_llm_response
        else:
            logger.warn("run_agent.llm_response_not_aimessage", agent_alias=alias, actual_type=type(raw_llm_response).__name__)
            # Attempt to create an AIMessage from it
            final_response_message = AIMessage(
                content=str(raw_llm_response.content), # Ensure content is string
                tool_calls=getattr(raw_llm_response, "tool_calls", None) # Preserve tool calls if any
            )
            # Copy other relevant attributes if necessary, e.g., id, name if they exist on raw_llm_response

        current_content = final_response_message.content
        if isinstance(current_content, list):
            logger.debug("run_agent.normalizing_list_content_in_final_response", agent_alias=alias, original_content_parts_count=len(current_content))
            string_parts = []
            for part in current_content:
                if isinstance(part, dict) and "text" in part:
                    string_parts.append(str(part["text"]))
                else:
                    string_parts.append(str(part))
            final_response_message.content = "\n\n".join(string_parts)
            logger.debug("run_agent.normalized_content_to_string_in_final_response", agent_alias=alias, new_content_preview=final_response_message.content[:100]+"...")
        elif not isinstance(current_content, str):
            logger.warn("run_agent.final_response_content_not_string_or_list", agent_alias=alias, content_type=type(current_content).__name__)
            final_response_message.content = str(current_content)

        final_response_message.name = alias # Crucial: set the sender's name

        original_llm_id = getattr(final_response_message, 'id', None)
        new_app_id = str(uuid.uuid4())
        final_response_message.id = new_app_id
        if original_llm_id and original_llm_id != new_app_id:
            logger.debug(
                "run_agent.overwrote_llm_provided_id",
                agent_alias=alias,
                original_id=original_llm_id,
                assigned_app_id=new_app_id
            )
        else:
            logger.debug(
                "run_agent.assigned_app_id_to_final_response",
                agent_alias=alias,
                message_id=new_app_id
            )
       
        logger.info(
            "run_agent.success",
            agent_alias=alias,
            final_response_id=final_response_message.id,
            final_response_name=final_response_message.name,
            final_response_type=type(final_response_message).__name__,
            final_response_content_snippet=final_response_message.content[:100]+"...",
            final_response_tool_calls=getattr(final_response_message, "tool_calls", None)
        )
        return final_response_message

    except Exception as e:
        logger.error("run_agent.unhandled_exception", agent_alias=alias, error=str(e), exc_info=True)
        error_msg = SystemMessage(
            content=f"Agent '{alias}' encountered an unhandled error: {str(e)}",
            name="system_error"
        )
        error_msg.id = str(uuid.uuid4())
        return error_msg