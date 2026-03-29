import json
import asyncio
from typing import Any, List, cast, Dict, Optional, AsyncGenerator
from mcp.types import TextContent
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam, ChatCompletionMessageFunctionToolCall

from openai import AsyncOpenAI
from core.config import settings
from core.exceptions import LLMException
from models.chat import ChatRequest, ChatResponse, CallToolResult
from mcp_client.client import mcp_client
from skills.manager import skill_manager
from session.compaction import ConversationManager, MessagePart, PartType, StreamChunk


class MessageBuilder:
    @staticmethod
    def build_messages(req: ChatRequest, skills_message: str = "", history: List[Dict] = None) -> List[dict]:
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
        
        messages = [system_message]
        
        if history:
            for m in history:
                messages.append({"role": m["role"], "content": m["content"]})
        
        messages.append({"role": "user", "content": req.message})
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
    def create_tool_part(tool_name: str, result: str) -> MessagePart:
        return MessagePart(
            part_type=PartType.TOOL.value,
            content=result,
            tool_name=tool_name
        )
    
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
    
    @staticmethod
    async def execute_tool_call_by_data(tool_call_id: str, tool_name: str, arguments: str) -> CallToolResult:
        try:
            args_dict = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError:
            return CallToolResult(
                name=tool_name,
                result=f"参数解析失败: {arguments}",
                call_tool_id=tool_call_id
            )
        
        if tool_name == "skill":
            skill_name = args_dict.get("name", "")
            skill = skill_manager.get_skill(skill_name)
            if not skill:
                available = [s.name for s in skill_manager.get_all_skills()]
                return CallToolResult(
                    name="skill",
                    result=f"技能 '{skill_name}' 不存在。可用技能: {', '.join(available) if available else '无'}",
                    call_tool_id=tool_call_id
                )
            return CallToolResult(
                name="skill",
                result=f"已加载技能: {skill.name}\n\n描述: {skill.description}\n\n{skill.skill_md_content}",
                call_tool_id=tool_call_id
            )
        
        parts = tool_name.split('_', 1)
        if len(parts) == 2:
            server_name, actual_tool_name = parts
        else:
            server_name = mcp_client.all_tools[0].server if mcp_client.all_tools else ""
            actual_tool_name = tool_name
        
        try:
            result = await mcp_client.call_tool(server_name, actual_tool_name, args_dict)
            content = ToolExecutor.extract_content(result.content)
            return CallToolResult(
                name=actual_tool_name,
                result=content,
                call_tool_id=tool_call_id
            )
        except Exception as e:
            return CallToolResult(
                name=actual_tool_name,
                result=str(e),
                call_tool_id=tool_call_id
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
        self.conversation_manager = ConversationManager()
    
    def _is_reasoning_model(self) -> bool:
        model = settings.LLM_MODEL.lower()
        return "r1" in model or "o1" in model or "o3" in model
    
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
    
    def _get_history_dicts(self) -> List[Dict]:
        history = self.conversation_manager.get_conversation_context()
        return [{"role": m.role, "content": m.content} for m in history]
    
    def _extract_reasoning(self, message) -> Optional[str]:
        if hasattr(message, 'reasoning') and message.reasoning:
            return message.reasoning
        if hasattr(message, 'completion_reasoning'):
            return message.completion_reasoning
        if hasattr(message, 'opaque') and hasattr(message.opaque, 'reasoning'):
            return message.opaque.reasoning
        return None
    
    async def _generate_summary(self, summary_prompt: str) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                temperature=0.5,
                messages=[{"role": "user", "content": summary_prompt}]
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            print(f"Summary generation failed: {e}")
            return "[对话已压缩]"
    
    async def chat(self, req: ChatRequest, skills_message: str = "") -> ChatResponse:
        try:
            self.conversation_manager.add_user_message(req.message)
            
            initial_message = self.message_builder.build_messages(
                req, 
                skills_message,
                self._get_history_dicts()
            )
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
            
            reasoning = self._extract_reasoning(message) if self._is_reasoning_model() else None
            tool_parts: List[MessagePart] = []
            
            if not hasattr(message, 'tool_calls') or not message.tool_calls:
                self.conversation_manager.add_assistant_message(
                    message.content or "", 
                    reasoning=reasoning
                )
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
            if reasoning:
                assistant_msg["reasoning"] = reasoning
            
            final_message.append(assistant_msg)
            
            tool_call_results: List[CallToolResult] = []
            for tool_call in function_tool_calls:
                result = await self.tool_executor.execute_tool_call(tool_call)
                tool_call_results.append(result)
                tool_parts.append(self.tool_executor.create_tool_part(result.name, result.result or result.error or ""))
                
                tool_msg = {
                    "role": "tool",
                    "content": result.result or result.error,
                    "tool_call_id": tool_call.id
                }
                final_message.append(tool_msg)
            
            self.conversation_manager.add_assistant_message(
                message.content or "", 
                tool_parts,
                reasoning
            )
            
            if self.conversation_manager.should_compact():
                stats = self.conversation_manager.check_and_compact(self._generate_summary)
                print(f"Compaction stats: {stats}")
            
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
    
    async def chat_stream(self, req: ChatRequest, skills_message: str = "") -> AsyncGenerator[str, None]:
        def build_sse_chunk(chunk_type: str, content: str = "", **kwargs) -> str:
            chunk = {
                "chunk_type": chunk_type,
                "content": content,
                **kwargs
            }
            return f"data: {json.dumps(chunk)}\n\n"
        
        try:
            self.conversation_manager.add_user_message(req.message)
            
            initial_message = self.message_builder.build_messages(
                req, 
                skills_message,
                self._get_history_dicts()
            )
            openai_tools = self.build_openai_tools()
            
            kwargs = {
                "model": settings.LLM_MODEL,
                "temperature": settings.TEMPERATURE,
                "messages": initial_message,
                "stream": True
            }
            
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"
            
            reasoning_content = ""
            tool_calls_buffer: Dict[int, Dict[str, Any]] = {}
            reasoning_part: Optional[MessagePart] = None
            
            async with self.client.chat.completions.create(**kwargs) as stream:
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    
                    delta = chunk.choices[0].delta
                    if not delta:
                        continue
                    
                    if hasattr(delta, 'reasoning') and delta.reasoning:
                        if not reasoning_part:
                            reasoning_part = MessagePart(
                                part_type=PartType.REASONING.value,
                                content="",
                                token_count=0
                            )
                        reasoning_content += delta.reasoning
                        yield build_sse_chunk("reasoning-delta", delta.reasoning, delta=delta.reasoning)
                        continue
                    
                    if hasattr(delta, 'content') and delta.content:
                        yield build_sse_chunk("text-delta", delta.content, delta=delta.content)
                    
                    if hasattr(delta, 'tool_calls') and delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            index = tc_delta.index
                            if index not in tool_calls_buffer:
                                tool_calls_buffer[index] = {
                                    "id": "",
                                    "name": "",
                                    "arguments": ""
                                }
                            
                            if hasattr(tc_delta.id) and tc_delta.id:
                                tool_calls_buffer[index]["id"] = tc_delta.id
                            if hasattr(tc_delta.function) and tc_delta.function:
                                if hasattr(tc_delta.function, 'name') and tc_delta.function.name:
                                    tool_calls_buffer[index]["name"] = tc_delta.function.name
                                if hasattr(tc_delta.function, 'arguments') and tc_delta.function.arguments:
                                    tool_calls_buffer[index]["arguments"] += tc_delta.function.arguments
                            
                            if tool_calls_buffer[index]["name"]:
                                yield build_sse_chunk(
                                    "tool-call",
                                    "",
                                    tool_call_id=tool_calls_buffer[index]["id"],
                                    tool_name=tool_calls_buffer[index]["name"],
                                    tool_input=tool_calls_buffer[index]["arguments"]
                                )
            
            if reasoning_content:
                self.conversation_manager.compaction.reasoning_tokens = len(reasoning_content) // 4
            
            tool_parts: List[MessagePart] = []
            if tool_calls_buffer:
                final_message = initial_message.copy()
                assistant_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": ""
                }
                
                tool_calls_for_message = []
                for idx in sorted(tool_calls_buffer.keys()):
                    tc_data = tool_calls_buffer[idx]
                    if tc_data["id"] and tc_data["name"]:
                        tool_calls_for_message.append({
                            "id": tc_data["id"],
                            "type": "function",
                            "function": {
                                "name": tc_data["name"],
                                "arguments": tc_data["arguments"]
                            }
                        })
                
                if tool_calls_for_message:
                    assistant_msg["tool_calls"] = tool_calls_for_message
                
                final_message.append(assistant_msg)
                
                for idx in sorted(tool_calls_buffer.keys()):
                    tc_data = tool_calls_buffer[idx]
                    if tc_data["id"] and tc_data["name"]:
                        result = await self.tool_executor.execute_tool_call_by_data(
                            tool_call_id=tc_data["id"],
                            tool_name=tc_data["name"],
                            arguments=tc_data["arguments"]
                        )
                        tool_parts.append(self.tool_executor.create_tool_part(result.name, result.result or result.error or ""))
                        
                        yield build_sse_chunk(
                            "tool-result",
                            result.result or result.error or "",
                            tool_call_id=tc_data["id"],
                            tool_name=tc_data["name"]
                        )
                        
                        tool_msg = {
                            "role": "tool",
                            "content": result.result or result.error,
                            "tool_call_id": tc_data["id"]
                        }
                        final_message.append(tool_msg)
                
                if reasoning_content:
                    reasoning_part.content = reasoning_content
                    reasoning_part.token_count = len(reasoning_content) // 4
                
                self.conversation_manager.add_assistant_message(
                    "",
                    tool_parts,
                    reasoning_content if reasoning_content else None
                )
                
                if self.conversation_manager.should_compact():
                    stats = self.conversation_manager.check_and_compact(self._generate_summary)
                    yield build_sse_chunk("done", content=f"[Compacted: {stats.get('compacted', False)}]")
                
                second_response = await self.client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    temperature=settings.TEMPERATURE,
                    messages=cast(list[ChatCompletionMessageParam], final_message),
                    stream=True
                )
                
                async for chunk in second_response:
                    if not chunk.choices:
                        continue
                    
                    delta = chunk.choices[0].delta
                    if not delta:
                        continue
                    
                    if hasattr(delta, 'content') and delta.content:
                        yield build_sse_chunk("text-delta", delta.content, delta=delta.content)
            
            yield build_sse_chunk("done", content="")
            
        except Exception as e:
            yield build_sse_chunk("error", content=str(e))


llm_service = OpenAIService()