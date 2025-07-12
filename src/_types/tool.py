from langchain_core.tools import BaseTool
from typing import Optional
from pydantic import BaseModel, Field


class SynapseTool(BaseModel):
    tool: BaseTool
    name: str = Field(..., description="Name of the tool")
    description: Optional[str] = Field(None, description="Description of the tool")
