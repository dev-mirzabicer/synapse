from langchain_core.tools import tool
from tavily import TavilyClient
from ..core.config import settings
# CHANGE: Import BaseModel and Field from Pydantic v2
from pydantic import BaseModel, Field

# This check ensures the service will fail fast on startup if a key is missing.
if not settings.TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY is not set in the environment.")

tavily_client = TavilyClient(api_key=settings.TAVILY_API_KEY)

# Define an input schema for the web_search tool using Pydantic v2
class WebSearchInput(BaseModel):
    query: str = Field(description="The search query to find information on the web.")

# Explicitly name the tool and provide its input schema
@tool(args_schema=WebSearchInput)
def web_search(query: str) -> str:
    """
    Performs a web search using the Tavily Search API to find information on a given query.
    This is best used for finding real-time information, specific facts, or broad overviews.
    """
    try:
        # The 'query' argument is automatically extracted from the validated WebSearchInput model
        results = tavily_client.search(query=query, search_depth="advanced", max_results=5)
        return f"Search results for '{query}':\n{results['results']}"
    except Exception as e:
        return f"Error performing web search for '{query}': {e}"

TOOL_REGISTRY = {
    "web_search": web_search,
}
