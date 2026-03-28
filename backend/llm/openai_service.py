import json
from typing import Any, List, cast
from mcp.types import TextContent
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam, ChatCompletionMessageFunctionToolCall

from openai import AsyncOpenAI
from core.config import settings
from core.exceptions import LLMException
from models.chat import ChatRequest, ChatResponse, CallToolResult
from mcp_client.client import mcp_client
from skills.manager import skill_manager


class MessageBuilder:
    @staticmethod
    def build_messages(req: ChatRequest, skills_message: str = "") -> List[dict]:
        base_system_content = """你是一个智能助手。

你有两种扩展能力:
1. **MCP工具** - 来自外部MCP服务器的功能调用
2. **自定义Skills** - 你可以使用的专业技能

当需要使用某个技能时,使用 skill 工具加载该技能。"""
        
        if skills_message:
            system_content = f"{base_system_content}\n\n<available_skills>\n{skills_message}\n</available_skills>"
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
        
        if function_name == "skill":
            skill_name = arguments.get("name", "")
            skill = skill_manager.get_skill(skill_name)
            if not skill:
                available = [s.name for s in skill_manager.get_all_skills()]
                return CallToolResult(
                    name="skill",
                    result=f"技能 '{skill_name}' 不存在。可用技能: {', '.join(available) if available else '无'}",
                    call_tool_id=tool_call.id
                )
            return CallToolResult(
                name="skill",
                result=f"已加载技能: {skill.name}\n\n描述: {skill.description}\n\n{skill.skill_md_content}",
                call_tool_id=tool_call.id
            )
        
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
    
    def _build_skill_tool_description(self) -> str:
        skills = skill_manager.get_all_skills()
        if not skills:
            return "加载技能。当没有可用的技能时不要调用此工具。"
        
        skill_list = ", ".join([s.name for s in skills])
        return f"""加载技能。使用 skill 工具加载指定技能的完整内容。

可用技能: {skill_list}"""
    
    def _build_skill_tool(self) -> dict:
        skills = skill_manager.get_all_skills()
        skill_names = [s.name for s in skills]
        hint = f"可用技能: {', '.join(skill_names)}" if skill_names else "无可用技能"
        
        return {
            "type": "function",
            "function": {
                "name": "skill",
                "description": self._build_skill_tool_description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": hint
                        }
                    },
                    "required": ["name"]
                }
            }
        }
    
    def build_openai_tools(self) -> List[dict]:
        tools = []
        
        skill_tool = self._build_skill_tool()
        if skill_tool:
            tools.append(skill_tool)
        
        for tc in mcp_client.all_tools:
            tools.append({
                "type": "function",
                "function": {
                    "name": f"{tc.server}_{tc.name}",
                    "description": f"{tc.server} {tc.description}",
                    "parameters": tc.input_schema
                }
            })
        
        return tools
    
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
