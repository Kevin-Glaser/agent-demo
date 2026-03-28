from typing import Any, Dict
from pydantic import BaseModel


class MCPServerConfig(BaseModel):
    name: str
    url: str
    description: str | None = None


class MCPToolInfo(BaseModel):
    server: str
    name: str
    description: str
    input_schema: Dict[str, Any]
