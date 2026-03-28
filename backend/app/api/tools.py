from fastapi import APIRouter, HTTPException
from models.common import CallToolRequest
from mcp_client.client import mcp_client
from llm.openai_service import llm_service

router = APIRouter()


@router.get("/tools")
async def get_tools(reload: bool = False):
    if reload:
        await mcp_client.reload_tools()
    return {"tools": [t.model_dump() for t in mcp_client.all_tools]}


@router.post("/call-tool")
async def call_tool(req: CallToolRequest):
    result = await mcp_client.call_tool(req.server, req.name, req.args)
    content = llm_service.tool_executor.extract_content(result.content) if hasattr(result, 'content') else str(result)
    return {"result": content}