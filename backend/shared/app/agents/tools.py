from langchain_core.tools import tool
from tavily import TavilyClient
from ..core.config import settings

# This check ensures the service will fail fast on startup if a key is missing.
if not settings.TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY is not set in the environment.")

tavily_client = TavilyClient(api_key=settings.TAVILY_API_KEY)

@tool
def web_search(query: str) -> str:
    """
    Performs a web search using the Tavily Search API to find information on a given query.
    This is best used for finding real-time information, specific facts, or broad overviews.
    """
    try:
        results = tavily_client.search(query=query, search_depth="advanced", max_results=5)
        return f"Search results for '{query}':\n{results['results']}"
    except Exception as e:
        return f"Error performing web search for '{query}': {e}"

TOOL_REGISTRY = {
    "web_search": web_search,
}