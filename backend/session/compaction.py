import time
import asyncio
from typing import List, Dict, Any, Optional, Callable, AsyncGenerator, Literal
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from models.chat import ChatMessage
from session.token import estimate, estimate_messages, TokenUsage, CumulativeTokenTracker
from core.config import settings, ModelLimits


class PartType(Enum):
    TEXT = "text"
    TOOL = "tool"
    REASONING = "reasoning"
    COMPACTION = "compaction"
    FILE = "file"
    SNAPSHOT = "snapshot"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    EMBEDDING = "embedding"
    FUNCTION_RESULT = "function_result"
    STREAMING = "streaming"
    STEP_START = "step-start"
    STEP_FINISH = "step-finish"
    PATCH = "patch"
    AGENT = "agent"
    SUBTASK = "subtask"
    RETRY = "retry"


class ToolCallState(Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RetryInfo:
    count: int = 0
    error: Optional[str] = None
    max_attempts: int = 3
    last_attempt: float = 0
    original_content: Optional[str] = None


@dataclass
class ToolState:
    status: ToolCallState = ToolCallState.PENDING
    input: Optional[str] = None
    output: Optional[str] = None
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    compacted: Optional[float] = None


@dataclass
class MessagePart:
    part_type: str
    content: str
    tool_name: Optional[str] = None
    compacted: bool = False
    timestamp: float = field(default_factory=time.time)
    reasoning_content: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_call_state: ToolCallState = ToolCallState.PENDING
    tool_call_error: Optional[str] = None
    token_count: int = 0
    media_url: Optional[str] = None
    media_mime_type: Optional[str] = None
    streaming_content: Optional[str] = None
    is_streaming_done: bool = False
    snapshot_data: Optional[Dict[str, Any]] = None
    patch_info: Optional[Dict[str, Any]] = None
    agent_info: Optional[Dict[str, Any]] = None
    subtask_info: Optional[Dict[str, Any]] = None
    retry_info: Optional[RetryInfo] = None
    step_tokens: Optional[int] = None
    step_cost: Optional[float] = None
    ignored: bool = False
    tool_state: Optional[ToolState] = None
    
    def get_tool_state(self) -> ToolState:
        if self.tool_state is None:
            self.tool_state = ToolState()
        return self.tool_state
    
    def mark_compacted(self):
        self.compacted = True
        if self.tool_state:
            self.tool_state.compacted = time.time()


@dataclass
class StreamChunk:
    chunk_type: Literal[
        "text-start", "text-delta", "text-end",
        "reasoning-start", "reasoning-delta", "reasoning-end",
        "tool-call", "tool-result",
        "start-step", "finish-step",
        "error", "done"
    ]
    content: str = ""
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    is_final: bool = False
    timestamp: float = field(default_factory=time.time)
    snapshot_data: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, int]] = None
    cost: Optional[float] = None
    tool_input: Optional[str] = None
    tool_output: Optional[str] = None
    delta: Optional[str] = None


@dataclass
class StreamState:
    current_text_part: Optional[MessagePart] = None
    current_reasoning_part: Optional[MessagePart] = None
    current_tool_call_id: Optional[str] = None
    current_step_start: Optional[MessagePart] = None
    text_content: str = ""
    reasoning_content: str = ""
    message_id: Optional[str] = None
    message_role: str = "assistant"


@dataclass
class Snapshot:
    files: Dict[str, str] = field(default_factory=dict)
    git_status: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    
    @staticmethod
    def track(files: Dict[str, str] = None, git_status: str = None) -> "Snapshot":
        return Snapshot(
            files=files or {},
            git_status=git_status
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "files": self.files,
            "git_status": self.git_status,
            "timestamp": self.timestamp
        }


@dataclass
class CostSummary:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    cache_cost: float = 0.0
    total_cost: float = 0.0
    
    @staticmethod
    def from_usage(usage: Dict[str, int], model: str = None) -> "CostSummary":
        summary = CostSummary()
        summary.input_tokens = usage.get("input_tokens", 0)
        summary.output_tokens = usage.get("output_tokens", 0)
        summary.cache_read_tokens = usage.get("cache_read", 0)
        summary.cache_write_tokens = usage.get("cache_write", 0)
        summary.total_tokens = summary.input_tokens + summary.output_tokens + summary.cache_read_tokens + summary.cache_write_tokens
        
        summary.input_cost = summary.input_tokens * 0.00001
        summary.output_cost = summary.output_tokens * 0.00003
        summary.cache_cost = (summary.cache_read_tokens * 0.00001 + summary.cache_write_tokens * 0.00002)
        summary.total_cost = summary.input_cost + summary.output_cost + summary.cache_cost
        
        return summary
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "total_tokens": self.total_tokens,
            "input_cost": self.input_cost,
            "output_cost": self.output_cost,
            "cache_cost": self.cache_cost,
            "total_cost": self.total_cost
        }


@dataclass
class MessageWithParts:
    role: str
    content: str
    parts: List[MessagePart] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    is_summary: bool = False
    reasoning: Optional[str] = None
    tool_calls: Dict[str, MessagePart] = field(default_factory=dict)
    pending_tool_count: int = 0
    completed_tool_count: int = 0
    message_id: Optional[str] = None
    total_tokens: int = 0
    mode: Optional[str] = None
    agent: Optional[str] = None
    finish: bool = False

    def update_tool_call_state(self, tool_call_id: str, state: ToolCallState, error: str = None):
        if tool_call_id in self.tool_calls:
            part = self.tool_calls[tool_call_id]
            part.tool_call_state = state
            if error:
                part.tool_call_error = error
            if state == ToolCallState.COMPLETED:
                self.completed_tool_count += 1
                self.pending_tool_count = max(0, self.pending_tool_count - 1)
            elif state == ToolCallState.EXECUTING:
                self.pending_tool_count = max(0, self.pending_tool_count - 1)
                self.completed_tool_count += 1

    def add_tool_call(self, tool_call_id: str, tool_name: str, content: str = "", call_state: ToolCallState = ToolCallState.PENDING):
        part = MessagePart(
            part_type=PartType.TOOL.value,
            content=content,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            tool_call_state=call_state,
            token_count=estimate(content)
        )
        self.parts.append(part)
        self.tool_calls[tool_call_id] = part
        self.pending_tool_count += 1
        self._recalc_tokens()
        return part

    def _recalc_tokens(self):
        self.total_tokens = sum(p.token_count for p in self.parts)


COMPACTION_BUFFER = 20000
PRUNE_MINIMUM = 20000
PROTECTED_TOOLS = ["skill"]
MAX_STREAMING_CHUNKS = 100

MEDIA_MIME_TYPES = frozenset([
    "image/", "audio/", "video/",
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
    "audio/mpeg", "audio/wav", "audio/ogg", "audio/webm",
    "video/mp4", "video/webm", "video/ogg"
])


def isMedia(mime_type: str) -> bool:
    if not mime_type:
        return False
    if mime_type.startswith(("image/", "audio/", "video/")):
        return True
    return mime_type in MEDIA_MIME_TYPES


CONTINUE_MESSAGE = "Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed."


class ConversationCompaction:
    def __init__(self):
        self.messages: List[MessageWithParts] = []
        self.total_tokens: int = 0
        self.reasoning_tokens: int = 0
        self._compaction_count: int = 0
        self._streaming_buffer: Dict[str, List[StreamChunk]] = defaultdict(list)
        self._active_streaming_message_id: Optional[str] = None
        self._token_tracker: CumulativeTokenTracker = CumulativeTokenTracker()
        self._current_model: str = settings.LLM_MODEL
    
    def add_message(self, role: str, content: str, parts: List[MessagePart] = None, reasoning: str = None, message_id: str = None):
        msg = MessageWithParts(
            role=role,
            content=content,
            parts=parts or [],
            reasoning=reasoning,
            message_id=message_id
        )
        if parts:
            msg.total_tokens = sum(p.token_count or estimate(p.content) for p in parts)
        else:
            msg.total_tokens = estimate(content)
        self.messages.append(msg)
        self.total_tokens += msg.total_tokens
        if reasoning:
            self.reasoning_tokens += estimate(reasoning)

    def start_streaming_message(self, role: str, message_id: str = None) -> str:
        msg = MessageWithParts(
            role=role,
            content="",
            message_id=message_id or f"stream_{len(self.messages)}"
        )
        self.messages.append(msg)
        self._active_streaming_message_id = msg.message_id
        return msg.message_id

    def add_streaming_chunk(self, message_id: str, chunk: StreamChunk):
        if message_id not in self._streaming_buffer:
            self._streaming_buffer[message_id] = []
        
        self._streaming_buffer[message_id].append(chunk)
        
        if len(self._streaming_buffer[message_id]) > MAX_STREAMING_CHUNKS:
            self._streaming_buffer[message_id] = self._streaming_buffer[message_id][-MAX_STREAMING_CHUNKS:]
        
        for msg in reversed(self.messages):
            if msg.message_id == message_id:
                if chunk.chunk_type == "text" and not chunk.tool_call_id:
                    msg.content += chunk.content
                elif chunk.tool_call_id:
                    if chunk.tool_call_id not in msg.tool_calls:
                        msg.add_tool_call(
                            tool_call_id=chunk.tool_call_id,
                            tool_name=chunk.tool_name or "unknown",
                            content=""
                        )
                    if chunk.content:
                        msg.tool_calls[chunk.tool_call_id].content += chunk.content
                break
        
        self._update_total_tokens()

    def finalize_streaming_message(self, message_id: str):
        if message_id in self._streaming_buffer:
            del self._streaming_buffer[message_id]
        
        for msg in self.messages:
            if msg.message_id == message_id:
                for part in msg.parts:
                    if part.tool_call_id:
                        part.is_streaming_done = True
                msg._recalc_tokens()
                break
        
        if self._active_streaming_message_id == message_id:
            self._active_streaming_message_id = None
        
        self._update_total_tokens()

    def _update_total_tokens(self):
        self.total_tokens = 0
        for msg in self.messages:
            msg_tokens = estimate(msg.content)
            msg_tokens += sum(p.token_count or estimate(p.content) for p in msg.parts)
            if msg.reasoning:
                msg_tokens += estimate(msg.reasoning)
            msg.total_tokens = msg_tokens
            self.total_tokens += msg_tokens

    def get_streaming_chunks(self, message_id: str) -> List[StreamChunk]:
        return self._streaming_buffer.get(message_id, [])
    
    def add_reasoning(self, content: str) -> MessagePart:
        reasoning_part = MessagePart(
            part_type=PartType.REASONING.value,
            content=content,
            reasoning_content=content,
            token_count=estimate(content)
        )
        return reasoning_part
    
    def process_streaming_response(self, role: str = "assistant") -> AsyncGenerator[StreamChunk, None]:
        message_id = self.start_streaming_message(role)
        try:
            yield StreamChunk(chunk_type="text", content="", is_final=False)
            accumulated_content = {}
            tool_accumulator = {}
            
            async def accumulator():
                return accumulated_content, tool_accumulator
            
            yield StreamChunk(chunk_type="done", content="", is_final=True, tool_call_id=message_id)
        finally:
            self.finalize_streaming_message(message_id)

    async def stream_to_compaction(self, async_generator: AsyncGenerator[StreamChunk, None]):
        message_id = None
        current_msg = None
        current_step_start: Optional[MessagePart] = None
        reasoning_part: Optional[MessagePart] = None
        text_part: Optional[MessagePart] = None
        stream_state = StreamState()
        
        async for chunk in async_generator:
            if chunk.chunk_type == "text-start":
                if current_msg is None:
                    message_id = self.start_streaming_message("assistant")
                    current_msg = message_id
                    stream_state.message_id = current_msg
                text_part = MessagePart(
                    part_type=PartType.TEXT.value,
                    content="",
                    token_count=0
                )
                stream_state.current_text_part = text_part
                for msg in self.messages:
                    if msg.message_id == current_msg:
                        msg.parts.append(text_part)
                        break
            elif chunk.chunk_type == "text-delta":
                if text_part:
                    delta = chunk.delta or chunk.content
                    text_part.content += delta
                    text_part.token_count = estimate(text_part.content)
                    for msg in self.messages:
                        if msg.message_id == current_msg:
                            msg.content += delta
                            break
            elif chunk.chunk_type == "text-end":
                if text_part:
                    text_part.is_streaming_done = True
                    text_part = None
                    stream_state.current_text_part = None
            elif chunk.chunk_type == "reasoning-start":
                if current_msg is None:
                    message_id = self.start_streaming_message("assistant")
                    current_msg = message_id
                    stream_state.message_id = current_msg
                reasoning_part = MessagePart(
                    part_type=PartType.REASONING.value,
                    content="",
                    token_count=0
                )
                stream_state.current_reasoning_part = reasoning_part
                for msg in self.messages:
                    if msg.message_id == current_msg:
                        msg.parts.append(reasoning_part)
                        break
            elif chunk.chunk_type == "reasoning-delta":
                if reasoning_part:
                    delta = chunk.delta or chunk.content
                    reasoning_part.content += delta
                    reasoning_part.token_count = estimate(reasoning_part.content)
                    self.reasoning_tokens = estimate(reasoning_part.content)
            elif chunk.chunk_type == "reasoning-end":
                if reasoning_part:
                    reasoning_part.is_streaming_done = True
                    reasoning_part = None
                    stream_state.current_reasoning_part = None
            elif chunk.chunk_type == "tool-call":
                if current_msg is None:
                    message_id = self.start_streaming_message("assistant")
                    current_msg = message_id
                    stream_state.message_id = current_msg
                tool_part = MessagePart(
                    part_type=PartType.TOOL.value,
                    content=chunk.tool_input or "",
                    tool_name=chunk.tool_name,
                    tool_call_id=chunk.tool_call_id,
                    tool_call_state=ToolCallState.EXECUTING,
                    token_count=estimate(chunk.tool_input or "")
                )
                for msg in self.messages:
                    if msg.message_id == current_msg:
                        msg.parts.append(tool_part)
                        msg.tool_calls[chunk.tool_call_id] = tool_part
                        msg.pending_tool_count += 1
                        break
                self.add_streaming_chunk(current_msg, chunk)
            elif chunk.chunk_type == "tool-result":
                if current_msg and chunk.tool_call_id:
                    for msg in self.messages:
                        if msg.message_id == current_msg:
                            if chunk.tool_call_id in msg.tool_calls:
                                tool_part = msg.tool_calls[chunk.tool_call_id]
                                tool_part.content = chunk.tool_output or chunk.content
                                tool_part.tool_call_state = ToolCallState.COMPLETED
                                tool_part.token_count = estimate(tool_part.content)
                                if tool_part.tool_state:
                                    tool_part.tool_state.status = ToolCallState.COMPLETED
                                    tool_part.tool_state.output = tool_part.content
                                    tool_part.tool_state.updated = time.time()
                                msg.completed_tool_count += 1
                                msg.pending_tool_count = max(0, msg.pending_tool_count - 1)
                            break
                self.add_streaming_chunk(current_msg, chunk)
            elif chunk.chunk_type == "start-step":
                if current_msg is None:
                    message_id = self.start_streaming_message("assistant")
                    current_msg = message_id
                    stream_state.message_id = current_msg
                snapshot_part = MessagePart(
                    part_type=PartType.STEP_START.value,
                    content="",
                    snapshot_data=chunk.snapshot_data or {}
                )
                stream_state.current_step_start = snapshot_part
                for msg in self.messages:
                    if msg.message_id == current_msg:
                        msg.parts.append(snapshot_part)
                        break
            elif chunk.chunk_type == "finish-step":
                if current_msg is None:
                    message_id = self.start_streaming_message("assistant")
                    current_msg = message_id
                    stream_state.message_id = current_msg
                step_finish_part = MessagePart(
                    part_type=PartType.STEP_FINISH.value,
                    content="",
                    step_tokens=chunk.usage.get("total") if chunk.usage else None,
                    step_cost=chunk.cost
                )
                for msg in self.messages:
                    if msg.message_id == current_msg:
                        msg.parts.append(step_finish_part)
                        break
                if chunk.usage:
                    usage = TokenUsage.from_dict(chunk.usage)
                    self._token_tracker.add_usage(usage)
                    if chunk.usage.get("total"):
                        self.add_step_tokens(chunk.usage.get("total"), chunk.cost or 0)
            elif chunk.chunk_type == "error":
                if current_msg and chunk.tool_call_id:
                    for msg in self.messages:
                        if msg.message_id == current_msg:
                            if chunk.tool_call_id in msg.tool_calls:
                                tool_part = msg.tool_calls[chunk.tool_call_id]
                                tool_part.tool_call_state = ToolCallState.FAILED
                                tool_part.tool_call_error = chunk.content
                                if tool_part.tool_state:
                                    tool_part.tool_state.status = ToolCallState.FAILED
                                    tool_part.tool_state.updated = time.time()
                            break
            elif chunk.chunk_type == "done":
                if current_msg:
                    self.finalize_streaming_message(current_msg)
                    current_msg = None
                    message_id = None
                    reasoning_part = None
                    text_part = None
                    current_step_start = None
                    stream_state = StreamState()
            yield chunk
    
    def update_part_delta(self, part_id: str, delta: str) -> bool:
        for msg in self.messages:
            for part in msg.parts:
                if id(part) == part_id or (hasattr(part, 'tool_call_id') and part.tool_call_id == part_id):
                    part.content += delta
                    part.token_count = estimate(part.content)
                    return True
        return False

    def get_pending_tool_calls(self) -> List[Dict[str, Any]]:
        pending = []
        for msg in self.messages:
            for tool_id, part in msg.tool_calls.items():
                if part.tool_call_state in (ToolCallState.PENDING, ToolCallState.EXECUTING):
                    pending.append({
                        "message_id": msg.message_id,
                        "tool_call_id": tool_id,
                        "tool_name": part.tool_name,
                        "state": part.tool_call_state.value,
                        "content": part.content
                    })
        return pending

    def get_tool_call_states(self) -> Dict[str, Dict[str, Any]]:
        states = {}
        for msg in self.messages:
            for tool_id, part in msg.tool_calls.items():
                states[tool_id] = {
                    "state": part.tool_call_state.value,
                    "tool_name": part.tool_name,
                    "error": part.tool_call_error,
                    "completed": part.tool_call_state == ToolCallState.COMPLETED
                }
        return states
    
    def get_messages_for_llm(self, strip_media: bool = False, include_reasoning: bool = True) -> List[Dict[str, Any]]:
        result = []
        for msg in self.messages:
            if msg.is_summary:
                continue
            
            msg_dict = {"role": msg.role, "content": msg.content}
            
            if include_reasoning and msg.reasoning:
                msg_dict["reasoning"] = msg.reasoning
            
            if msg.parts:
                parts_content = []
                reasoning_parts = []
                tool_calls_result = []
                files_result = []
                
                for part in msg.parts:
                    if part.compacted:
                        parts_content.append("[Old tool result content cleared]")
                    elif part.part_type == PartType.REASONING.value:
                        reasoning_parts.append(part.content)
                    elif part.part_type == PartType.COMPACTION.value:
                        parts_content.append("What did we do so far?")
                    elif part.part_type == PartType.TOOL.value:
                        if part.tool_call_state == ToolCallState.PENDING:
                            tool_calls_result.append({
                                "id": part.tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": part.tool_name,
                                    "arguments": part.content
                                }
                            })
                        elif part.tool_call_state == ToolCallState.EXECUTING:
                            parts_content.append(f"[{part.tool_name}: executing...]")
                        elif part.tool_call_state == ToolCallState.COMPLETED:
                            output = part.tool_state.output if part.tool_state and part.tool_state.compacted else part.content
                            if part.tool_state and part.tool_state.compacted:
                                output = "[Old tool result content cleared]"
                            parts_content.append(f"[{part.tool_name}: {output}]")
                        elif part.tool_call_state == ToolCallState.FAILED:
                            error_msg = part.tool_call_error or "unknown error"
                            parts_content.append(f"[{part.tool_name} failed: {error_msg}]")
                    elif part.part_type == PartType.FILE.value:
                        if strip_media and part.media_mime_type and isMedia(part.media_mime_type):
                            parts_content.append(f"[Attached {part.media_mime_type}: {part.content or 'file'}]")
                        elif not strip_media:
                            files_result.append({
                                "type": "file",
                                "url": part.media_url,
                                "mediaType": part.media_mime_type
                            })
                    elif part.part_type == PartType.IMAGE.value:
                        if strip_media:
                            parts_content.append(f"[Attached {part.media_mime_type or 'image'}: {part.content or 'image'}]")
                        else:
                            files_result.append({"type": "file", "url": part.media_url, "mediaType": part.media_mime_type})
                    elif part.part_type == PartType.AUDIO.value:
                        if strip_media:
                            parts_content.append(f"[Attached {part.media_mime_type or 'audio'}: {part.content or 'audio'}]")
                        else:
                            files_result.append({"type": "file", "url": part.media_url, "mediaType": part.media_mime_type})
                    elif part.part_type == PartType.VIDEO.value:
                        if strip_media:
                            parts_content.append(f"[Attached {part.media_mime_type or 'video'}: {part.content or 'video'}]")
                        else:
                            files_result.append({"type": "file", "url": part.media_url, "mediaType": part.media_mime_type})
                    elif part.part_type == PartType.STREAMING.value:
                        if part.is_streaming_done:
                            parts_content.append(f"[Streaming: {part.streaming_content}]")
                    elif part.tool_name:
                        parts_content.append(f"[{part.tool_name}: {part.content}]")
                    else:
                        if not part.ignored:
                            parts_content.append(part.content)
                
                if reasoning_parts and include_reasoning:
                    msg_dict["reasoning"] = "\n".join(reasoning_parts)
                
                if tool_calls_result:
                    msg_dict["tool_calls"] = tool_calls_result
                
                if files_result and not strip_media:
                    msg_dict["files"] = files_result
                
                if parts_content:
                    msg_dict["content"] = "\n".join(parts_content)
            
            result.append(msg_dict)
        
        return result
    
    def get_total_tokens_with_reasoning(self) -> int:
        return self.total_tokens + self.reasoning_tokens
    
    def get_token_usage(self) -> TokenUsage:
        if self._token_tracker.total_tokens > 0:
            return TokenUsage(
                input_tokens=self.total_tokens,
                output_tokens=self._token_tracker.total_output,
                cache_read_tokens=self._token_tracker.total_cache_read,
                cache_write_tokens=self._token_tracker.total_cache_write
            )
        return TokenUsage(
            input_tokens=self.total_tokens,
            output_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0
        )
    
    def update_usage_from_response(self, usage_data: Dict[str, int]):
        if not usage_data:
            return
        self._token_tracker.add_usage(TokenUsage.from_dict(usage_data))
    
    def is_auto_compact_enabled(self) -> bool:
        return getattr(settings, 'CONVERSATION_AUTO_COMPACT', True)
    
    def is_overflow(
        self,
        model: str = None,
        model_context_limit: int = None,
        reserved: int = None,
        max_output_tokens: int = None,
        model_limit_input: int = None,
        token_usage: TokenUsage = None
    ) -> bool:
        if not self.is_auto_compact_enabled():
            return False
        
        model = model or self._current_model
        model_limits = ModelLimits.get(model)
        
        if model_context_limit is None:
            model_context_limit = model_limits.get("context", settings.CONVERSATION_MAX_TOKENS)
        
        if model_context_limit == 0:
            return False
        
        if max_output_tokens is None:
            max_output_tokens = model_limits.get("output", 4096)
        
        if reserved is None:
            reserved = min(COMPACTION_BUFFER, max_output_tokens)
        
        count = self.get_total_tokens_with_reasoning()
        if token_usage:
            count = token_usage.total or (
                token_usage.input_tokens + token_usage.output_tokens +
                token_usage.cache_read_tokens + token_usage.cache_write_tokens
            )
        
        if model_limit_input is not None and model_limit_input > 0:
            usable = model_limit_input - reserved
        else:
            usable = model_context_limit - max_output_tokens
        
        return count >= usable
    
    def get_model_limits(self, model: str = None) -> Dict[str, int]:
        model = model or self._current_model
        return ModelLimits.get(model)
    
    def get_max_output_tokens(self, model: str = None) -> int:
        return ModelLimits.max_output_tokens(model or self._current_model)
    
    def get_usable_tokens(self, max_output_tokens: int = 4096) -> int:
        return self.get_total_tokens_with_reasoning() - max_output_tokens
    
    def prune(self, force: bool = False) -> int:
        if len(self.messages) < 4 and not force:
            return 0
        
        prune_protect = settings.CONVERSATION_PRUNE_PROTECT
        pruned_tokens = 0
        turns = 0
        msg_index = len(self.messages) - 1
        
        while msg_index >= 0:
            msg = self.messages[msg_index]
            
            if msg.role == "user":
                turns += 1
            
            if turns < 2 and not force:
                msg_index -= 1
                continue
            
            if msg.is_summary:
                break
            
            if msg.role == "assistant" and msg.parts:
                for part_index in range(len(msg.parts) - 1, -1, -1):
                    part = msg.parts[part_index]
                    
                    if part.part_type == PartType.TOOL.value and part.tool_name not in PROTECTED_TOOLS:
                        if part.compacted:
                            break
                        
                        if part.tool_call_state in (ToolCallState.PENDING, ToolCallState.EXECUTING):
                            continue
                        
                        part_tokens = part.token_count or estimate(part.content)
                        self.total_tokens -= part_tokens
                        part.compacted = True
                        part.content = ""
                        pruned_tokens += part_tokens
                        
                        if not force and self.get_total_tokens_with_reasoning() < prune_protect:
                            break
                else:
                    msg_index -= 1
                    continue
                break
            
            msg_index -= 1
        
        return pruned_tokens
    
    def prune_by_type(self, part_types: List[PartType], protect_active: bool = True) -> int:
        pruned_tokens = 0
        for msg in self.messages:
            for part in msg.parts:
                if part.part_type in [pt.value for pt in part_types]:
                    if protect_active and part.tool_call_state in (ToolCallState.PENDING, ToolCallState.EXECUTING):
                        continue
                    if part.compacted:
                        continue
                    part_tokens = part.token_count or estimate(part.content)
                    self.total_tokens -= part_tokens
                    part.compacted = True
                    part.content = ""
                    pruned_tokens += part_tokens
        return pruned_tokens
    
    def prune_reasoning_only(self) -> int:
        pruned = 0
        for msg in self.messages:
            if msg.reasoning:
                pruned += estimate(msg.reasoning)
                msg.reasoning = None
        for msg in self.messages:
            for part in msg.parts:
                if part.part_type == PartType.REASONING.value:
                    part_tokens = part.token_count or estimate(part.content)
                    pruned += part_tokens
                    part.compacted = True
                    part.content = ""
        self.reasoning_tokens = 0
        self._update_total_tokens()
        return pruned
    
    def compact_streaming_parts(self) -> int:
        compacted = 0
        for msg in self.messages:
            for part in msg.parts:
                if part.part_type == PartType.STREAMING.value and part.streaming_content:
                    if not part.is_streaming_done:
                        continue
                    part_tokens = part.token_count or estimate(part.content)
                    part.content = ""
                    part.compacted = True
                    compacted += part_tokens
        self._update_total_tokens()
        return compacted
    
    def create_summary(self, summary_content: str, agent: str = "compaction") -> int:
        pending_tools = self.get_pending_tool_calls()
        pending_summary = ""
        if pending_tools:
            pending_summary = f"\n\n[Pending tool calls: {', '.join(t['tool_name'] for t in pending_tools)}]"
        
        summary_msg = MessageWithParts(
            role="assistant",
            content=summary_content + pending_summary,
            is_summary=True,
            mode="compaction",
            agent=agent
        )
        
        self.messages.insert(0, summary_msg)
        
        compaction_marker = MessagePart(
            part_type=PartType.COMPACTION.value,
            content="[Previous conversation compacted]"
        )
        
        marker_msg = MessageWithParts(
            role="system",
            content="",
            parts=[compaction_marker]
        )
        self.messages.insert(1, marker_msg)
        
        self._compaction_count += 1
        return len(self.messages)
    
    @property
    def compaction_count(self) -> int:
        return self._compaction_count
    
    def get_stats(self) -> Dict[str, Any]:
        pending_tools = self.get_pending_tool_calls()
        tool_states = self.get_tool_call_states()
        usage = self.get_token_usage()
        model_limits = self.get_model_limits()
        tracker = self._token_tracker.to_dict()
        
        return {
            "message_count": len(self.messages),
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_read_tokens": usage.cache_read_tokens,
            "cache_write_tokens": usage.cache_write_tokens,
            "total_tokens": usage.total,
            "reasoning_tokens": self.reasoning_tokens,
            "total_with_reasoning": self.get_total_tokens_with_reasoning(),
            "compaction_count": self._compaction_count,
            "estimated_chars": self.total_tokens * 4,
            "pending_tool_calls": len(pending_tools),
            "tool_calls_states": tool_states,
            "streaming_buffer_size": sum(len(chunks) for chunks in self._streaming_buffer.values()),
            "active_streaming": self._active_streaming_message_id,
            "usable_tokens": self.get_usable_tokens(),
            "model": self._current_model,
            "model_limits": model_limits,
            "max_output_tokens": model_limits.get("output", 4096),
            "auto_compact": self.is_auto_compact_enabled(),
            "cumulative": tracker
        }
    
    def set_model(self, model: str):
        self._current_model = model
    
    def add_cumulative_usage(self, usage: TokenUsage):
        self._token_tracker.add_usage(usage)
    
    def add_step_tokens(self, tokens: int, cost: float = 0.0):
        self._token_tracker.add_step(tokens, cost)
    
    def filter_compacted(self) -> List["MessageWithParts"]:
        result = []
        for msg in self.messages:
            if msg.is_summary:
                continue
            
            new_parts = []
            has_compaction = False
            for part in msg.parts:
                if part.part_type == PartType.COMPACTION.value:
                    has_compaction = True
                    new_parts.append(MessagePart(
                        part_type=PartType.TEXT.value,
                        content="What did we do so far?",
                        ignored=False
                    ))
                elif not part.ignored:
                    new_parts.append(part)
            
            if has_compaction:
                msg.parts = new_parts
            
            result.append(msg)
        return result
    
    def process(self, llm_summarize: Callable[[str], str], abort_signal: Any = None, auto: bool = True) -> Dict[str, Any]:
        messages_for_summary = self.get_messages_for_llm(strip_media=True, include_reasoning=False)
        
        summary_prompt = self._build_summary_prompt_for_process(messages_for_summary)
        
        if abort_signal and getattr(abort_signal, "is_aborted", lambda: False)():
            return {"aborted": True}
        
        summary = llm_summarize(summary_prompt)
        
        self.create_summary(summary)
        
        result = {
            "summary_length": len(summary),
            "messages_before": len(self.messages),
            "compaction_count": self._compaction_count
        }
        
        if auto:
            self.add_continue_message()
            result["added_continue_message"] = True
        
        return result
    
    def _build_summary_prompt_for_process(self, messages: List[Dict[str, Any]]) -> str:
        lines = [
            "Provide a detailed prompt for continuing our conversation above.\n",
            "---"
        ]
        
        lines.append("## Goal\n[What goal(s) is the user trying to accomplish?]")
        lines.append("## Instructions\n[What important instructions did the user give you that are relevant]")
        lines.append("## Discoveries\n[What notable things were learned during this conversation]")
        lines.append("## Accomplished\n[What work has been completed, what work is still in progress]")
        lines.append("## Relevant files / directories\n[Construct a structured list of relevant files]")
        lines.append("---\n")
        
        for msg in messages[-10:]:
            lines.append(f"**{msg['role']}**: {msg.get('content', '')[:200]}...")
        
        return "\n".join(lines)
    
    def add_continue_message(self):
        continue_msg = MessageWithParts(
            role="user",
            content=CONTINUE_MESSAGE,
            is_summary=False
        )
        self.messages.append(continue_msg)
        return continue_msg


class ConversationManager:
    def __init__(self, max_tokens: int = None, reserved_tokens: int = None):
        self.max_tokens = max_tokens or settings.CONVERSATION_MAX_TOKENS
        self.reserved_tokens = reserved_tokens or settings.CONVERSATION_RESERVED_TOKENS
        self.compaction: ConversationCompaction = ConversationCompaction()
        self._history: List[ChatMessage] = []
        self._tool_call_handlers: Dict[str, Callable] = {}
    
    def add_user_message(self, content: str, message_id: str = None):
        self.compaction.add_message("user", content, message_id=message_id)
        self._history.append(ChatMessage(role="user", content=content))
    
    def add_assistant_message(self, content: str, parts: List[MessagePart] = None, reasoning: str = None, message_id: str = None):
        self.compaction.add_message("assistant", content, parts, reasoning, message_id=message_id)
        self._history.append(ChatMessage(role="assistant", content=content))
    
    def get_conversation_context(self) -> List[ChatMessage]:
        return self._history[-20:] if len(self._history) > 20 else self._history
    
    def check_and_compact(self, llm_summarize: Callable[[str], str], abort_signal: Any = None) -> Dict[str, Any]:
        stats = self.compaction.get_stats()
        
        if not self.compaction.is_overflow(model_context_limit=self.max_tokens):
            return stats
        
        pruned = self.compaction.prune()
        stats["pruned_tokens"] = pruned
        
        if self.compaction.is_overflow(model_context_limit=self.max_tokens):
            reasoning_pruned = self.compaction.prune_reasoning_only()
            stats["reasoning_pruned"] = reasoning_pruned
        
        if self.compaction.is_overflow(model_context_limit=self.max_tokens):
            result = self.compaction.process(llm_summarize, abort_signal=abort_signal, auto=True)
            stats["compacted"] = True
            stats["summary_length"] = result.get("summary_length", 0)
            stats["added_continue_message"] = result.get("added_continue_message", False)
            self._history = self._history[-10:] if len(self._history) > 10 else self._history
        
        return stats
    
    def _build_summary_prompt(self) -> str:
        recent_msgs = self.get_conversation_context()
        if not recent_msgs:
            return ""
        
        lines = ["请总结以下对话的关键信息：\n"]
        for msg in recent_msgs[:10]:
            lines.append(f"**{msg.role}**: {msg.content[:200]}...")
        
        lines.append("\n请用以下格式总结：")
        lines.append("## Goal: [用户目标]")
        lines.append("## Instructions: [重要指令]")
        lines.append("## Discoveries: [发现]")
        lines.append("## Accomplished: [已完成的工作]")
        lines.append("## Relevant files: [相关文件]")
        
        return "\n".join(lines)
    
    def should_compact(self) -> bool:
        return self.compaction.is_overflow(self.max_tokens, self.reserved_tokens)
    
    async def stream_response(self, async_generator: AsyncGenerator[StreamChunk, None]) -> List[StreamChunk]:
        chunks = []
        async for chunk in self.compaction.stream_to_compaction(async_generator):
            chunks.append(chunk)
        return chunks
    
    def update_tool_call_state(self, tool_call_id: str, state: ToolCallState, error: str = None):
        for msg in self.compaction.messages:
            if tool_call_id in msg.tool_calls:
                msg.update_tool_call_state(tool_call_id, state, error)
                break
    
    def register_tool_handler(self, tool_name: str, handler: Callable):
        self._tool_call_handlers[tool_name] = handler
    
    def get_pending_tool_calls(self) -> List[Dict[str, Any]]:
        return self.compaction.get_pending_tool_calls()
    
    def get_tool_call_states(self) -> Dict[str, Dict[str, Any]]:
        return self.compaction.get_tool_call_states()
    
    def compact_streaming(self) -> int:
        return self.compaction.compact_streaming_parts()
    
    def prune_by_type(self, part_types: List[PartType], protect_active: bool = True) -> int:
        return self.compaction.prune_by_type(part_types, protect_active)
    
    def force_compact(self) -> Dict[str, Any]:
        stats = {"actions": []}
        
        pruned = self.compaction.prune(force=True)
        stats["actions"].append({"action": "prune", "tokens": pruned})
        
        if self.compaction.get_total_tokens_with_reasoning() > self.max_tokens - self.reserved_tokens:
            reasoning_pruned = self.compaction.prune_reasoning_only()
            stats["actions"].append({"action": "prune_reasoning", "tokens": reasoning_pruned})
        
        if self.compaction.get_total_tokens_with_reasoning() > self.max_tokens - self.reserved_tokens:
            summary_prompt = self._build_summary_prompt()
            stats["actions"].append({"action": "create_summary", "summary_length": len(summary_prompt)})
        
        stats["final_tokens"] = self.compaction.get_total_tokens_with_reasoning()
        return stats


conversation_manager = ConversationManager()