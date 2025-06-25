from langchain_core.messages import BaseMessage, SystemMessage
import logging
from .tools import TOOL_REGISTRY
from ..schemas.groups import GroupMemberRead
from ..core.config import settings

logger = logging.getLogger(__name__)

async def run_agent(messages: list[BaseMessage], members: list[GroupMemberRead], alias: str) -> BaseMessage:
    """Encapsulates the logic for running a single agent's LLM call."""
    try:
        member_config = next((m for m in members if m.alias == alias), None)
        if not member_config:
            raise ValueError(f"Configuration not found for agent alias: {alias}")

        available_aliases = ", ".join([f"@[{m.alias}]" for m in members if m.alias != alias])
        prompt_template = member_config.system_prompt + f"\n\nAvailable team members for delegation: {available_aliases}."

        prompt = [SystemMessage(content=prompt_template), *messages]

        provider = getattr(member_config, "provider", "openai")
        model = getattr(member_config, "model", "gpt-4o")
        temperature = getattr(member_config, "temperature", 0.1)

        if provider == "openai":
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model=model, temperature=temperature, openai_api_key=settings.OPENAI_API_KEY)
        elif provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(model=model, temperature=temperature, google_api_key=settings.GEMINI_API_KEY)
        elif provider == "claude":
            from langchain_anthropic import ChatAnthropic
            llm = ChatAnthropic(model=model, temperature=temperature, anthropic_api_key=settings.CLAUDE_API_KEY)
        else:
            raise ValueError(f"Unknown provider: {provider}")

        allowed_tools = [TOOL_REGISTRY[tool_name] for tool_name in member_config.tools or []]
        logger.info(f"Running agent '{alias}' with tools: {allowed_tools}")
        llm_with_tools = llm.bind_tools(allowed_tools) if allowed_tools else llm

        response = await llm_with_tools.ainvoke(prompt)
        
        # Proactively normalize message content to be a string.
        if isinstance(response.content, list):
            # Intelligently join all parts, converting them to string representations.
            response.content = "\n\n".join(
                part.get("text", str(part)) if isinstance(part, dict) else str(part)
                for part in response.content
            )

        response.name = alias
        return response
    except Exception as e:
        logger.error(f"Agent '{alias}' failed", exc_info=True)
        return SystemMessage(content=f"Agent '{alias}' failed: {e}", name="system_error")
