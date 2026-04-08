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


class RollbackRequest(BaseModel):
    n_turns: int = 1
    message_index: int | None = None  # 要回滚到的消息索引（不包括此索引本身之后的消息）


class DeleteTurnRequest(BaseModel):
    message_index: int
