from typing import List
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage]


class CallToolResult(BaseModel):
    name: str
    result: str | None = None
    error: str | None = None
    call_tool_id: str


class ChatResponse(BaseModel):
    response: str | None = ""
    callTools: List[CallToolResult]
