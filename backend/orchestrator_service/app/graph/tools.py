from langchain_core.tools import tool
from tavily import TavilyClient
from shared.app.core.config import settings

# Initialize the client for the Tavily Search API.
# It automatically uses the TAVILY_API_KEY from the environment.
tavily_client = TavilyClient(api_key=settings.TAVILY_API_KEY)

@tool
def web_search(query: str) -> str:
    """
    Performs a web search using the Tavily Search API to find information on a given query.
    This is best used for finding real-time information or specific facts.
    """
    # This docstring is crucial. It's what the LLM sees as the tool's description.
    # The type hints (query: str) are also crucial for the LLM to know what arguments to provide.
    try:
        # Calling the Tavily client's search method.
        # 'search_depth="advanced"' provides more detailed, agent-optimized results.
        results = tavily_client.search(query=query, search_depth="advanced")
        return f"Search results for '{query}':\n{results['results']}"
    except Exception as e:
        # Robust error handling is essential for production tools.
        return f"Error performing web search for '{query}': {e}"

# The Tool Registry: A central place to define all available tools.
# This makes the system highly extensible. To add a new tool, simply
# define it with the @tool decorator and add it to this dictionary.
TOOL_REGISTRY = {
    "web_search": web_search,
}

# TODO (Phase 3/4): Refactor tool execution. The implementation of these tools
# should be moved to the `execution_workers` service. The orchestrator would
# then dispatch tool calls as jobs to that service instead of executing them directly.