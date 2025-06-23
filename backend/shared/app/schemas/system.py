from pydantic import BaseModel, Field

class ToolInfo(BaseModel):
    """Information about an available tool."""
    name: str
    description: str
    args_schema: dict = Field(description="JSON schema for the tool's arguments")

class ModelInfo(BaseModel):
    """Information about an available LLM model."""
    id: str = Field(description="The model identifier used in API requests")
    name: str = Field(description="A user-friendly name for the model")
    # Potentially add more fields like context_window, provider_specific_features, etc.

class ProviderInfo(BaseModel):
    """Information about an available LLM provider and its models."""
    provider_name: str
    models: list[ModelInfo]