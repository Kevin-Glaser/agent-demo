import json
from typing import Any, List, cast
from mcp.types import TextContent
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam, ChatCompletionMessageFunctionToolCall

from openai import AsyncOpenAI
from core.config import settings
from core.exceptions import LLMException
from models.chat import ChatRequest, ChatResponse, CallToolResult
from mcp_client.client import mcp_client


class MessageBuilder:
    @staticmethod
    def build_messages(req: ChatRequest, skills_message: str = "") -> List[dict]:
        base_system_content = "你是一个智能助手,可以使用各种 MCP 工具或者Skill来帮助用户完成任务。如果不需要使用工具,直接返回回答。"
        
        if skills_message:
            system_content = f"{base_system_content}\n\n{skills_message}"
        else:
            system_content = base_system_content
        
        system_message = {
            "role": "system",
            "content": system_content
        }
        
        user_message = {
            "role": "user",
            "content": req.message
        }
        
        messages = [system_message]
        if req.history:
            for m in req.history:
                messages.append({"role": m.role, "content": m.content})
        messages.append(user_message)
        return messages


class ToolExecutor:
    @staticmethod
    def extract_content(content_list: List[Any]) -> str:
        content_text = []
        for content in content_list:
            if isinstance(content, TextContent):
                content_text.append(content.text)
            elif hasattr(content, 'text'):
                content_text.append(str(content.text))
            else:
                content_text.append(str(content))
        return "\n".join(content_text) if content_text else "已完成但无返回信息"
    
    @staticmethod
    async def execute_tool_call(tool_call: ChatCompletionMessageFunctionToolCall) -> CallToolResult:
        function_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        
        parts = function_name.split('_', 1)
        if len(parts) == 2:
            server_name, tool_name = parts
        else:
            server_name = mcp_client.all_tools[0].server if mcp_client.all_tools else ""
            tool_name = function_name
        
        try:
            result = await mcp_client.call_tool(server_name, tool_name, arguments)
            content = ToolExecutor.extract_content(result.content)
            return CallToolResult(
                name=tool_name,
                result=content,
                call_tool_id=tool_call.id
            )
        except Exception as e:
            return CallToolResult(
                name=tool_name,
                result=str(e),
                call_tool_id=tool_call.id
            )


class OpenAIService:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
            max_retries=settings.MAX_RETRIES
        )
        self.message_builder = MessageBuilder()
        self.tool_executor = ToolExecutor()
    
    def build_openai_tools(self) -> List[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": f"{tc.server}_{tc.name}",
                    "description": f"{tc.server} {tc.description}",
                    "parameters": tc.input_schema
                }
            }
            for tc in mcp_client.all_tools
        ]
    
    async def chat(self, req: ChatRequest, skills_message: str = "") -> ChatResponse:
        try:
            initial_message = self.message_builder.build_messages(req, skills_message)
            openai_tools = self.build_openai_tools()
            
            kwargs = {
                "model": settings.LLM_MODEL,
                "temperature": settings.TEMPERATURE,
                "messages": initial_message,
            }
            
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"
            
            response: ChatCompletion = await self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message
            
            if not hasattr(message, 'tool_calls') or not message.tool_calls:
                return ChatResponse(
                    response=message.content,
                    callTools=[]
                )
            
            function_tool_calls = [
                tc for tc in message.tool_calls
                if isinstance(tc, ChatCompletionMessageFunctionToolCall)
            ]
            
            final_message = initial_message.copy()
            assistant_msg = {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in function_tool_calls
                ]
            }
            final_message.append(assistant_msg)
            
            tool_call_results: List[CallToolResult] = []
            for tool_call in function_tool_calls:
                result = await self.tool_executor.execute_tool_call(tool_call)
                tool_call_results.append(result)
                
                tool_msg = {
                    "role": "tool",
                    "content": result.result or result.error,
                    "tool_call_id": tool_call.id
                }
                final_message.append(tool_msg)
            
            final_response: ChatCompletion = await self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                temperature=settings.TEMPERATURE,
                messages=cast(list[ChatCompletionMessageParam], final_message)
            )
            
            return ChatResponse(
                response=final_response.choices[0].message.content,
                callTools=tool_call_results
            )
        
        except Exception as e:
            raise LLMException(f"LLM processing failed: {e}")


llm_service = OpenAIService()
