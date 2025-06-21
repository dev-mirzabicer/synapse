import asyncio
from typing import List
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode

from .state import GraphState
from .tools import TOOL_REGISTRY

# --- NODE 1: The Tool Executor ---
# We use the pre-built ToolNode, which is the standard, robust way to execute tools in LangGraph.
# It takes a list of tools and automatically handles the execution logic.
tool_node = ToolNode(tools=list(TOOL_REGISTRY.values()))

# --- Private Helper Function for Agent Logic ---
async def _run_agent_for_alias(state: GraphState, alias: str) -> BaseMessage:
    """A private helper to encapsulate the logic for running a single agent."""
    try:
        # Find the configuration for the specified agent alias in the graph state.
        member_config = next((m for m in state['group_members'] if m.alias == alias), None)
        if not member_config:
            raise ValueError(f"No configuration found for agent alias: {alias}")

        # Construct the prompt for the LLM, including the full message history.
        prompt = [
            SystemMessage(content=member_config.system_prompt),
            *state['messages']
        ]

        # Initialize the LLM.
        # TODO (Phase 4): Allow per-agent model selection from member_config.
        llm = ChatOpenAI(model="gpt-4o")

        # Filter the main tool registry to get only the tools this agent is allowed to use.
        allowed_tools = [TOOL_REGISTRY[tool_name] for tool_name in member_config.tools or []]

        # Bind the allowed tools to the LLM. This is how the LLM knows what tools it can call.
        if allowed_tools:
            llm_with_tools = llm.bind_tools(allowed_tools)
        else:
            llm_with_tools = llm

        # Invoke the LLM with the constructed prompt.
        response = await llm_with_tools.ainvoke(prompt)
        return response
    except Exception as e:
        # If any part of the agent execution fails, we return the exception
        # to be handled by the calling node. This is crucial for robustness.
        return e

# --- NODE 2: The Main Orchestrator ---
async def orchestrator_node(state: GraphState) -> dict[str, List[BaseMessage]]:
    """Runs the main orchestrator agent."""
    response = await _run_agent_for_alias(state, "Orchestrator")
    
    if isinstance(response, Exception):
        # If the orchestrator itself fails, we wrap the error in a SystemMessage.
        return {"messages": [SystemMessage(content=f"Orchestrator failed: {response}")]}
        
    return {"messages": [response]}

# --- NODE 3: The Generic Agent Executor ---
async def agent_node(state: GraphState) -> dict[str, List[BaseMessage]]:
    """Runs the agent(s) specified in state['next_actors'] in parallel."""
    actor_aliases = state.get("next_actors", [])
    if not actor_aliases:
        return {}

    # Create a list of async tasks, one for each agent to be run.
    tasks = [_run_agent_for_alias(state, alias) for alias in actor_aliases]
    
    # Execute the tasks in parallel. return_exceptions=True is critical for robustness.
    # It ensures that even if one agent fails, the others can complete, and we get the error.
    results = await asyncio.gather(*tasks, return_exceptions=True)

    new_messages = []
    for alias, result in zip(actor_aliases, results):
        if isinstance(result, Exception):
            # If a task returned an exception, create a SystemMessage to record the failure.
            # This makes the graph self-healing; the orchestrator will see this error and can react.
            error_message = f"Agent '{alias}' failed with the following error: {result}"
            new_messages.append(SystemMessage(content=error_message))
        else:
            # Otherwise, add the successful agent response.
            new_messages.append(result)
            
    return {"messages": new_messages}