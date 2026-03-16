from typing import Any, Dict
from pydantic import BaseModel


class CallToolRequest(BaseModel):
    name: str
    server: str
    args: Dict[str, Any]
