from fastapi import APIRouter, Depends, HTTPException
import structlog

from shared.app.schemas.system import ToolInfo, ProviderInfo, ModelInfo
from shared.app.agents.tools import TOOL_REGISTRY, WebSearchInput # Assuming WebSearchInput is the example
from shared.app.core.config import settings

router = APIRouter()
logger = structlog.get_logger(__name__)

@router.get("/tools", response_model=list[ToolInfo])
async def list_available_tools():
    """Lists all available tools registered in the system."""
    logger.info("list_available_tools.start")
    tool_infos = []
    for tool_name, tool_obj in TOOL_REGISTRY.items():
        description = tool_obj.__doc__ or "No description available."
        args_schema_pydantic = getattr(tool_obj, 'args_schema', None)
        
        schema_dict = {}
        if args_schema_pydantic and hasattr(args_schema_pydantic, 'model_json_schema'):
            # For Pydantic v2 models
            schema_dict = args_schema_pydantic.model_json_schema()
        elif args_schema_pydantic and hasattr(args_schema_pydantic, 'schema'):
            # For Pydantic v1 models (fallback, ensure compatibility if mixed)
            schema_dict = args_schema_pydantic.schema()
            
        tool_infos.append(
            ToolInfo(
                name=tool_name,
                description=description.strip(),
                args_schema=schema_dict,
            )
        )
    logger.info("list_available_tools.success", count=len(tool_infos))
    return tool_infos


@router.get("/llm-options", response_model=list[ProviderInfo])
async def list_llm_options():
    """Lists available LLM providers and their models, filtered by configured API keys."""
    logger.info("list_llm_options.start")
    available_options: list[ProviderInfo] = []

    # OpenAI
    if settings.OPENAI_API_KEY:
        available_options.append(
            ProviderInfo(
                provider_name="openai",
                models=[
                    ModelInfo(id="gpt-4o", name="GPT-4 Omni"),
                    ModelInfo(id="gpt-4-turbo", name="GPT-4 Turbo"),
                    ModelInfo(id="gpt-3.5-turbo", name="GPT-3.5 Turbo"),
                ],
            )
        )

    # Gemini (Google)
    if settings.GEMINI_API_KEY:
        available_options.append(
            ProviderInfo(
                provider_name="gemini",
                models=[
                    ModelInfo(id="gemini-2.5-pro", name="Gemini 2.5 Pro"), # Corrected to 1.5, or use 2.5 if that's what you have access to
                    ModelInfo(id="gemini-1.5-pro-latest", name="Gemini 1.5 Pro Latest"),
                    ModelInfo(id="gemini-1.5-flash-latest", name="Gemini 1.5 Flash Latest"),
                    ModelInfo(id="gemini-1.0-pro", name="Gemini 1.0 Pro"),
                ],
            )
        )
    
    # Claude (Anthropic)
    if settings.CLAUDE_API_KEY:
        available_options.append(
            ProviderInfo(
                provider_name="claude",
                models=[
                    ModelInfo(id="claude-3-opus-20240229", name="Claude 3 Opus"),
                    ModelInfo(id="claude-3-sonnet-20240229", name="Claude 3 Sonnet"),
                    ModelInfo(id="claude-3-haiku-20240307", name="Claude 3 Haiku"),
                ],
            )
        )
    
    # Add other providers as needed

    logger.info("list_llm_options.success", count=len(available_options))
    return available_options