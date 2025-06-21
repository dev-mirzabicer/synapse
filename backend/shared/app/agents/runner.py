from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .tools import TOOL_REGISTRY
from ..schemas.groups import GroupMemberRead

async def run_agent(messages: list[BaseMessage], members: list[GroupMemberRead], alias: str) -> BaseMessage:
    """
    Encapsulates the logic for running a single agent's LLM call.
    This is now a shared utility that the execution_worker will use.
    """
    try:
        member_config = next((m for m in members if m.alias == alias), None)
        if not member_config:
            raise ValueError(f"No configuration found for agent alias: {alias}")

        prompt = [SystemMessage(content=member_config.system_prompt), *messages]
        llm = ChatOpenAI(model="gpt-4o") # TODO: Make model configurable

        allowed_tools = [TOOL_REGISTRY[tool_name] for tool_name in member_config.tools or []]
        llm_with_tools = llm.bind_tools(allowed_tools) if allowed_tools else llm

        response = await llm_with_tools.ainvoke(prompt)
        return response
    except Exception as e:
        # Return the exception itself to be handled by the caller.
        return e