from langchain_core.messages import BaseMessage, SystemMessage
from .tools import TOOL_REGISTRY
from ..schemas.groups import GroupMemberRead
from ..core.config import settings

async def run_agent(messages: list[BaseMessage], members: list[GroupMemberRead], alias: str) -> BaseMessage:
    """Encapsulates the logic for running a single agent's LLM call."""
    try:
        member_config = next((m for m in members if m.alias == alias), None)
        if not member_config:
            raise ValueError(f"Configuration not found for agent alias: {alias}")

        # Inject available member aliases into the system prompt for context.
        available_aliases = ", ".join([m.alias for m in members if m.alias != alias])
        prompt_template = member_config.system_prompt + f"\n\nAvailable team members for delegation: {available_aliases}."

        prompt = [SystemMessage(content=prompt_template), *messages]

        provider = getattr(member_config, "provider", "openai")
        model = getattr(member_config, "model", "gpt-4o")
        temperature = getattr(member_config, "temperature", 0.1)

        if provider == "openai":
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model=model,
                temperature=temperature,
                openai_api_key=settings.OPENAI_API_KEY,
            )
        elif provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model=model,
                temperature=temperature,
                google_api_key=settings.GEMINI_API_KEY,
            )
        elif provider == "claude":
            from langchain_anthropic import ChatAnthropic

            llm = ChatAnthropic(
                model=model,
                temperature=temperature,
                anthropic_api_key=settings.CLAUDE_API_KEY,
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")

        allowed_tools = [TOOL_REGISTRY[tool_name] for tool_name in member_config.tools or []]
        llm_with_tools = llm.bind_tools(allowed_tools) if allowed_tools else llm

        response = await llm_with_tools.ainvoke(prompt)
        # Assign the sender's name to the response for easier routing later.
        response.name = alias
        return response
    except Exception as e:
        return SystemMessage(content=f"Agent '{alias}' failed: {e}", name="system_error")
