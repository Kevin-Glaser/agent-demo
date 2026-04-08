import time
import json
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
    FILE = "file"           # 统一处理：IMAGE, AUDIO, VIDEO, EMBEDDING 等通过 mime 类型区分
    SNAPSHOT = "snapshot"
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
    attachments: List[Dict[str, Any]] = field(default_factory=list)


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
    filename: Optional[str] = None
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
    attachments: List[Dict[str, Any]] = field(default_factory=list)  # mime, url for tool results


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


COMPACTION_BUFFER = 20000        # 溢出检测的缓冲 token 数
PRUNE_MINIMUM = 20000          # 开始裁剪的最小 token 阈值（低于此值不裁剪）
PRUNE_PROTECT = 40000          # 保护最近 N token 不被裁剪
PROTECTED_TOOLS = ["skill"]     # 保护的工具列表，这些工具的输出不会被裁剪
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

# 可裁剪的上下文消息前缀模式
CONTEXTUAL_PREFIXES = [
    "<model_switch>",
    "<permissions>",
    "<model拒绝>",
    "<system-instructions>",
    "<context-",
    "<system-reminder>",
]

# 识别为上下文消息的正则模式
CONTEXTUAL_PATTERNS = [
    r"^<model_switch>.*?<\/model_switch>",
    r"^<permissions>.*?<\/permissions>",
    r"^<model拒绝>.*?<\/model拒绝>",
    r"^<system-instructions>.*?<\/system-instructions>",
    r"^<system-reminder>.*?<\/system-reminder>",
    r"^\s*<\|.*?\|>\s*$",  # <|...|> 格式的独立行
]


def is_contextual_message(content: str) -> bool:
    """
    检测消息内容是否为可裁剪的上下文消息。

    上下文消息通常是：
    - 系统级指令但不需要长期保留
    - 模型切换提示
    - 权限指令
    - 临时性系统提示

    Args:
        content: 消息内容

    Returns:
        True 如果是上下文消息，可以安全裁剪
    """
    if not content or not content.strip():
        return False

    stripped = content.strip()

    # 检查前缀匹配
    for prefix in CONTEXTUAL_PREFIXES:
        if stripped.startswith(prefix):
            return True

    # 检查正则模式匹配
    import re
    for pattern in CONTEXTUAL_PATTERNS:
        if re.match(pattern, stripped, re.DOTALL):
            return True

    return False


def extract_contextual_parts(content: str) -> List[Dict[str, Any]]:
    """
    从消息内容中提取所有上下文部分。

    Returns:
        包含 context_type, start, end, text 的字典列表
    """
    import re
    parts = []

    for pattern in CONTEXTUAL_PATTERNS:
        for match in re.finditer(pattern, content, re.DOTALL):
            parts.append({
                "pattern": pattern,
                "text": match.group(),
                "start": match.start(),
                "end": match.end()
            })

    return parts


def truncate_middle(text: str, max_tokens: int) -> tuple[str, int | None]:
    """
    使用 token 预算截断字符串，保留开头和结尾。

    参考 Codex 的 truncate_middle_with_token_budget() 实现。

    当文本超过 max_tokens 时，保留前一半和后一半，中间用省略标记连接。
    例如："开头...N tokens truncated...结尾"

    Args:
        text: 要截断的文本
        max_tokens: 最大 token 数

    Returns:
        (截断后的文本, 原始token数或None) 元组
        如果未截断返回(None, None)
    """
    if not text:
        return "", None

    if max_tokens <= 0:
        return f"…0 tokens truncated…", None

    # 4 字符约等于 1 token
    max_bytes = max_tokens * 4

    if len(text) <= max_bytes:
        return text, None

    # 将 budget 分成两半给前缀和后缀
    prefix_budget = max_bytes // 2
    suffix_budget = max_bytes - prefix_budget

    # 找到前缀的截断位置
    prefix_end = 0
    prefix_chars = 0
    for idx, char in enumerate(text):
        char_bytes = len(char.encode('utf-8'))
        if prefix_end + char_bytes <= prefix_budget:
            prefix_end += char_bytes
            prefix_chars += 1
        else:
            break

    # 找到后缀的开始位置（从末尾）
    suffix_start = len(text)
    suffix_chars = 0
    for idx in range(len(text) - 1, -1, -1):
        char_bytes = len(text[idx].encode('utf-8'))
        if len(text) - suffix_start + char_bytes <= suffix_budget:
            suffix_start -= char_bytes
            suffix_chars += 1
        else:
            break

    if suffix_start < prefix_end:
        suffix_start = prefix_end

    # 计算被移除的 token 数
    removed_chars = len(text) - (suffix_start - prefix_end)
    removed_tokens = removed_chars // 4

    prefix = text[:prefix_end]
    suffix = text[suffix_start:] if suffix_start < len(text) else ""

    marker = f"…{removed_tokens} tokens truncated…"

    return prefix + marker + suffix, (len(text) + 3) // 4


def truncate_middle_chars(text: str, max_chars: int) -> str:
    """
    使用字符数截断字符串，保留开头和结尾。

    Args:
        text: 要截断的文本
        max_chars: 最大字符数

    Returns:
        截断后的文本
    """
    if not text:
        return ""

    if max_chars <= 0:
        removed = len(text)
        return f"…{removed} chars truncated…"

    if len(text) <= max_chars:
        return text

    prefix_budget = max_chars // 2
    suffix_budget = max_chars - prefix_budget

    # 找到前缀
    prefix_end = 0
    for idx, char in enumerate(text):
        if prefix_end + 1 <= prefix_budget:
            prefix_end += 1
        else:
            break

    # 找到后缀
    suffix_start = len(text)
    for idx in range(len(text) - 1, -1, -1):
        if len(text) - suffix_start + 1 <= suffix_budget:
            suffix_start -= 1
        else:
            break

    if suffix_start < prefix_end:
        suffix_start = prefix_end

    prefix = text[:prefix_end]
    suffix = text[suffix_start:] if suffix_start < len(text) else ""
    removed_chars = len(text) - (suffix_start - prefix_end)

    return prefix + f"…{removed_chars} chars truncated…" + suffix


STRUCTURED_OUTPUT_DESCRIPTION = """Use this tool to return your final response in the requested structured format.

IMPORTANT:
- You MUST call this tool exactly once at the end of your response
- The input must be valid JSON matching the required schema
- Complete all necessary research and tool calls BEFORE calling this tool
- This tool provides your final answer - no further actions are taken after calling it"""

STRUCTURED_OUTPUT_SYSTEM_PROMPT = """IMPORTANT: The user has requested structured output. You MUST use the StructuredOutput tool to provide your final response. Do NOT respond with plain text - you MUST call the StructuredOutput tool with your answer formatted according to the schema."""

MAX_STEPS_MESSAGE = "You have reached the maximum number of steps. Please provide your final response now."


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
                                    if chunk.attachments:
                                        tool_part.tool_state.attachments = chunk.attachments
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

    def insert_reminders(self, last_finished_id: str = None) -> None:
        """
        Insert system reminders into user messages

        After the first turn, wraps queued user messages with a reminder to stay on track.
        This is called when step > 1 and there's a lastFinished message.
        """
        if not self.messages:
            return

        for msg in self.messages:
            # Only process user messages
            if msg.role != "user":
                continue

            # Skip if this user message is before or equal to lastFinished
            if last_finished_id and msg.message_id and msg.message_id <= last_finished_id:
                continue

            # Find text parts that are not ignored and not synthetic
            for part in msg.parts:
                if part.part_type == PartType.TEXT.value and not part.ignored:
                    if hasattr(part, 'streaming_content') and part.streaming_content:
                        text = part.streaming_content
                    else:
                        text = part.content

                    if text and text.strip():
                        # Wrap with system reminder
                        wrapped_text = [
                            "<system-reminder>",
                            "The user sent the following message:",
                            text,
                            "",
                            "Please address this message and continue with your tasks.",
                            "</system-reminder>",
                        ]
                        part.content = "\n".join(wrapped_text)
                        part.streaming_content = "\n".join(wrapped_text)

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
                            output = part.content
                            if part.tool_state:
                                if part.tool_state.compacted:
                                    output = "[Old tool result content cleared]"
                                    part.tool_state.attachments = []
                                elif strip_media:
                                    # When strip_media=true, clear attachments to reduce context size
                                    part.tool_state.attachments = []
                            parts_content.append(f"[{part.tool_name}: {output}]")
                        elif part.tool_call_state == ToolCallState.FAILED:
                            error_msg = part.tool_call_error or "unknown error"
                            parts_content.append(f"[{part.tool_name} failed: {error_msg}]")
                    elif part.part_type == PartType.FILE.value:
                        if strip_media and part.media_mime_type and isMedia(part.media_mime_type):
                            parts_content.append(f"[Attached {part.media_mime_type}: {part.filename or 'file'}]")
                        elif not strip_media:
                            files_result.append({
                                "type": "file",
                                "url": part.media_url,
                                "mediaType": part.media_mime_type,
                                "filename": part.filename
                            })
                    elif part.part_type == PartType.TEXT.value and part.is_streaming_done:
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
        """
        裁剪旧的 tool 结果输出。

        裁剪策略（参考 OpenCode）：
        1. 只有当需要裁剪的 token 数超过 PRUNE_MINIMUM (20000) 时才裁剪
        2. 保护最近 PRUNE_PROTECT (40000) token 不被裁剪
        3. 跳过 PROTECTED_TOOLS (["skill"]) 中的工具输出
        4. 跳过已 compacted 的 parts
        5. 跳过 PENDING/EXECUTING 状态的 tool calls

        Args:
            force: 是否强制裁剪（忽略阈值检查）

        Returns:
            裁剪的 token 数
        """
        if len(self.messages) < 4 and not force:
            return 0

        # 检查是否需要裁剪（token 总量是否超过最小阈值）
        current_tokens = self.get_total_tokens_with_reasoning()
        if current_tokens < PRUNE_MINIMUM and not force:
            return 0

        pruned_tokens = 0
        accumulated_pruned = 0  # 已裁剪的 token 累积量
        turns = 0
        msg_index = len(self.messages) - 1

        while msg_index >= 0:
            msg = self.messages[msg_index]

            if msg.role == "user":
                turns += 1

            # 保护最近 2 个 turn 不被裁剪（除非强制）
            if turns < 2 and not force:
                msg_index -= 1
                continue

            if msg.is_summary:
                break

            if msg.role == "assistant" and msg.parts:
                for part_index in range(len(msg.parts) - 1, -1, -1):
                    part = msg.parts[part_index]

                    # 只处理 tool 类型的 part
                    if part.part_type != PartType.TOOL.value:
                        continue

                    # 跳过受保护的工具
                    if part.tool_name in PROTECTED_TOOLS:
                        continue

                    # 跳过已 compacted 的 part
                    if part.compacted:
                        break

                    # 跳过 PENDING/EXECUTING 状态的 tool calls
                    if part.tool_call_state in (ToolCallState.PENDING, ToolCallState.EXECUTING):
                        continue

                    # 计算这个 part 的 token 数
                    part_tokens = part.token_count or estimate(part.content)
                    accumulated_pruned += part_tokens

                    # 检查是否达到保护阈值（停止裁剪）
                    # 当累积裁剪量超过 PRUNE_PROTECT 时停止
                    if not force and accumulated_pruned > PRUNE_PROTECT:
                        break

                    # 执行裁剪：清空内容，标记为 compacted
                    self.total_tokens -= part_tokens
                    part.compacted = True
                    part.content = ""
                    pruned_tokens += part_tokens

                    # 裁剪后再次检查总 token 是否低于保护阈值
                    if not force and self.get_total_tokens_with_reasoning() < PRUNE_PROTECT:
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

    def truncate_tool_outputs(self, max_tokens_per_output: int = 500) -> Dict[str, Any]:
        """
        使用中间保留截断缩小大型工具输出。

        与 prune() 不同，prune() 完全清空工具输出内容，
        而 truncate_tool_outputs() 保留首尾部分，用省略标记连接。

        Args:
            max_tokens_per_output: 每个工具输出的最大 token 数

        Returns:
            包含截断结果的字典
        """
        result = {
            "tools_truncated": 0,
            "tokens_saved": 0,
            "details": []
        }

        for msg in self.messages:
            for part in msg.parts:
                if part.part_type != PartType.TOOL.value:
                    continue

                if part.compacted:
                    continue

                if part.tool_call_state in (ToolCallState.PENDING, ToolCallState.EXECUTING):
                    continue

                current_tokens = part.token_count or estimate(part.content)
                if current_tokens <= max_tokens_per_output:
                    continue

                # 使用 truncate_middle 截断
                original_content = part.content
                truncated, _ = truncate_middle(original_content, max_tokens_per_output)

                tokens_saved = current_tokens - (len(truncated) // 4)
                part.content = truncated
                part.token_count = len(truncated) // 4
                self.total_tokens -= tokens_saved

                result["tools_truncated"] += 1
                result["tokens_saved"] += tokens_saved
                result["details"].append({
                    "tool_name": part.tool_name,
                    "original_tokens": current_tokens,
                    "truncated_tokens": part.token_count
                })

        return result

    def prune_contextual_messages(self, protect_recent: int = 2) -> Dict[str, Any]:
        """
        裁剪可识别的上下文消息。

        识别并裁剪：
        - <model_switch>...</model_switch>
        - <permissions>...</permissions>
        - <model拒绝>...</model拒绝>
        - <system-instructions>...</system-instructions>
        - <system-reminder>...</system-reminder>

        Args:
            protect_recent: 保留最近N条消息的上下文不被裁剪

        Returns:
            裁剪结果统计
        """
        result = {
            "messages_scanned": 0,
            "messages_modified": 0,
            "parts_removed": 0,
            "tokens_saved": 0,
            "details": []
        }

        # 跳过最近 N 条消息
        protected_start = max(0, len(self.messages) - protect_recent)

        for i, msg in enumerate(self.messages):
            result["messages_scanned"] += 1

            if i >= protected_start:
                continue

            # 检查主内容
            if msg.content and is_contextual_message(msg.content):
                tokens = estimate(msg.content)
                result["tokens_saved"] += tokens
                result["messages_modified"] += 1
                result["details"].append({
                    "message_index": i,
                    "role": msg.role,
                    "type": "full_content",
                    "tokens": tokens
                })
                # 清空内容但保留消息结构
                msg.content = "[Contextual message removed]"
                continue

            # 检查 parts
            if msg.parts:
                for part in msg.parts:
                    if part.part_type == PartType.TEXT.value:
                        if part.content and is_contextual_message(part.content):
                            tokens = part.token_count or estimate(part.content)
                            result["tokens_saved"] += tokens
                            result["parts_removed"] += 1
                            result["details"].append({
                                "message_index": i,
                                "role": msg.role,
                                "type": "text_part",
                                "tokens": tokens
                            })
                            part.content = "[Contextual content removed]"
                            part.compacted = True

        if result["tokens_saved"] > 0:
            self._update_total_tokens()

        return result

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

    def prune_to_user_boundary(self, protect_turns: int = 2, max_turns: int = None) -> int:
        """
        在用户Turn边界处裁剪整条消息。

        确保裁剪发生在用户消息边界上，保护最近N个完整Turn。

        Args:
            protect_turns: 保护最近N个完整Turn不被删除，默认2
            max_turns: 最多保留多少个Turn，None表示不限制

        Returns:
            删除的消息数量
        """
        if len(self.messages) < 4:
            return 0

        # 找到所有用户消息的位置（从后往前）
        user_positions = []
        for i, msg in enumerate(self.messages):
            if msg.role == "user":
                user_positions.append(i)

        if not user_positions:
            return 0

        # 确定要保护的最早用户消息位置
        protect_idx: int = None
        if max_turns is not None and len(user_positions) > max_turns:
            # 按max_turns限制
            protect_idx = user_positions[len(user_positions) - max_turns]
        elif len(user_positions) > protect_turns:
            # 保留protect_turns个用户Turn
            protect_idx = user_positions[len(user_positions) - protect_turns]

        if protect_idx is None:
            return 0

        # 找到实际的裁剪点：在protect_idx位置的消息之前，找最近的用户消息边界
        # 我们要删除protect_idx之前的所有消息
        pruned_count = 0
        tokens_saved = 0

        # 找出要删除的消息范围（从0到protect_idx）
        # 但要保留保护范围内的消息结构完整性
        messages_to_remove = []
        for i in range(protect_idx):
            msg = self.messages[i]
            # 计算这条消息的token
            msg_tokens = estimate(msg.content)
            msg_tokens += sum(p.token_count or estimate(p.content) for p in msg.parts)
            if msg.reasoning:
                msg_tokens += estimate(msg.reasoning)
            tokens_saved += msg_tokens
            messages_to_remove.append(i)

        # 从后往前删除，避免索引混乱
        for i in reversed(messages_to_remove):
            self.messages.pop(i)
            pruned_count += 1

        # 清理summary消息（如果第一条是summary，保留它）
        # 确保summary在compact之后的第一条消息位置
        if self.messages and self.messages[0].is_summary:
            # summary应该在最前面，检查是否需要移动
            pass

        self._update_total_tokens()
        return pruned_count

    def rollback(self, n_turns: int = 1, message_index: int = None) -> Dict[str, Any]:
        """
        回退消息历史。

        参考 Codex 的 drop_last_n_user_turns() 实现。
        支持两种模式：
        - 按 Turn 回退：删除最后 N 个用户 Turn（包括用户消息和对应的助手回复）
        - 按索引回退：删除指定消息索引之后的所有消息

        Args:
            n_turns: 要回退的 Turn 数量，默认为 1
            message_index: 要回滚到的消息索引（不包括此索引之后的消息），优先于 n_turns

        Returns:
            包含回退结果的字典：
            - rolled_back: 实际回退的 Turn 数量
            - messages_removed: 删除的消息数量
            - tokens_removed: 删除的 token 数量
            - remaining_messages: 剩余消息数量
        """
        result = {
            "requested_turns": n_turns,
            "requested_index": message_index,
            "rolled_back": 0,
            "messages_removed": 0,
            "tokens_removed": 0,
            "remaining_messages": len(self.messages)
        }

        if message_index is not None:
            # 按索引回退：删除 message_index 之后的所有消息
            if message_index < 0 or message_index >= len(self.messages):
                return result

            # 计算将被删除的 token 数
            tokens_to_remove = 0
            for i in range(message_index, len(self.messages)):
                msg = self.messages[i]
                tokens_to_remove += estimate(msg.content)
                tokens_to_remove += sum(p.token_count or estimate(p.content) for p in msg.parts)
                if msg.reasoning:
                    tokens_to_remove += estimate(msg.reasoning)

            removed_messages = self.messages[message_index:]
            self.messages = self.messages[:message_index]

            result["messages_removed"] = len(removed_messages)
            result["tokens_removed"] = tokens_to_remove
            result["remaining_messages"] = len(self.messages)

            # 计算回退的 turn 数（从 message_index 到末尾有多少个完整 turn）
            # 找到 message_index 之前的最后一个 user 消息
            user_count = 0
            for i in range(message_index, len(removed_messages) + message_index):
                if i < len(self.messages) and self.messages[i].role == "user":
                    user_count += 1
            # 加上 removed_messages 中的 user 消息
            for msg in removed_messages:
                if msg.role == "user":
                    user_count += 1
            result["rolled_back"] = user_count

            self._update_total_tokens()
            return result

        if n_turns <= 0 or len(self.messages) < 2:
            return result

        # 找到所有用户消息的位置
        user_positions = []
        for i, msg in enumerate(self.messages):
            if msg.role == "user":
                user_positions.append(i)

        if not user_positions:
            return result

        # 确定要回退到的位置
        # 如果请求回退 2 个 turn，而我们有 5 个 user turns，
        # 则回退到最后第 2 个 user turn 之前
        cut_idx: int
        if n_turns >= len(user_positions):
            # 回退所有 turn，保留到第一个用户消息之前
            cut_idx = user_positions[0]
        else:
            # 回退到最后 n_turns 个 turn
            cut_idx = user_positions[len(user_positions) - n_turns]

        # 计算将被删除的 token 数
        tokens_to_remove = 0
        for i in range(cut_idx, len(self.messages)):
            msg = self.messages[i]
            tokens_to_remove += estimate(msg.content)
            tokens_to_remove += sum(p.token_count or estimate(p.content) for p in msg.parts)
            if msg.reasoning:
                tokens_to_remove += estimate(msg.reasoning)

        # 删除 cut_idx 之后的所有消息
        removed_messages = self.messages[cut_idx:]
        self.messages = self.messages[:cut_idx]

        # 更新统计
        result["rolled_back"] = min(n_turns, len(user_positions))
        result["messages_removed"] = len(removed_messages)
        result["tokens_removed"] = tokens_to_remove
        result["remaining_messages"] = len(self.messages)

        # 重新计算 total_tokens
        self._update_total_tokens()

        return result

    def delete_turn(self, message_index: int) -> Dict[str, Any]:
        """
        删除指定位置的 Turn（用户消息 + 对应的助手回复）。

        给定一个用户消息的索引，删除该用户消息以及紧随其后的助手回复。
        如果指定的是助手消息索引，则删除该助手消息。
        如果是最后一条消息无法配对，则只删除该消息。

        Args:
            message_index: 要删除的消息索引

        Returns:
            包含删除结果的字典
        """
        result = {
            "removed": 0,
            "tokens_removed": 0,
            "remaining_messages": len(self.messages)
        }

        if message_index < 0 or message_index >= len(self.messages):
            return result

        msg = self.messages[message_index]

        # 计算这条消息的 token 数
        def calc_tokens(m: MessageWithParts) -> int:
            tokens = estimate(m.content)
            tokens += sum(p.token_count or estimate(p.content) for p in m.parts)
            if m.reasoning:
                tokens += estimate(m.reasoning)
            return tokens

        tokens_to_remove = calc_tokens(msg)
        to_delete = [message_index]

        # 如果是用户消息，尝试找到并删除紧随的助手回复
        if msg.role == "user" and message_index + 1 < len(self.messages):
            next_msg = self.messages[message_index + 1]
            if next_msg.role == "assistant":
                tokens_to_remove += calc_tokens(next_msg)
                to_delete.append(message_index + 1)
        # 如果是助手消息，尝试找到并删除紧随的用户消息（不常见）
        elif msg.role == "assistant" and message_index + 1 < len(self.messages):
            next_msg = self.messages[message_index + 1]
            if next_msg.role == "user":
                tokens_to_remove += calc_tokens(next_msg)
                to_delete.append(message_index + 1)

        # 删除消息（从后往前删，避免索引偏移）
        for idx in sorted(to_delete, reverse=True):
            self.messages.pop(idx)

        result["removed"] = len(to_delete)
        result["tokens_removed"] = tokens_to_remove
        result["remaining_messages"] = len(self.messages)

        self._update_total_tokens()
        return result

    def remove_oldest_messages(self, n: int) -> Dict[str, Any]:
        """
        删除最早的 N 条消息（FIFO 策略）。

        与 rollback() 不同：
        - rollback() 从消息末尾删除（删除最新的）
        - remove_oldest_messages() 从消息开头删除（删除最旧的）

        Args:
            n: 要删除的最早消息数量

        Returns:
            包含删除结果的字典
        """
        result = {
            "removed": 0,
            "tokens_removed": 0,
            "remaining_messages": len(self.messages)
        }

        if n <= 0 or not self.messages:
            return result

        # 保护第一条消息（通常是 summary，标记了 is_summary）
        protect_first = 1 if self.messages and self.messages[0].is_summary else 0

        # 计算要删除的消息数量（不能超过可删除范围）
        max_removable = len(self.messages) - protect_first
        to_remove = min(n, max_removable)

        if to_remove <= 0:
            return result

        # 计算将被删除的 token 数（从 protect_first 之后开始算）
        tokens_to_remove = 0
        for i in range(protect_first, protect_first + to_remove):
            msg = self.messages[i]
            tokens_to_remove += estimate(msg.content)
            tokens_to_remove += sum(p.token_count or estimate(p.content) for p in msg.parts)
            if msg.reasoning:
                tokens_to_remove += estimate(msg.reasoning)

        # 删除消息（跳过保护的消息）
        start_idx = protect_first
        end_idx = protect_first + to_remove
        removed = self.messages[start_idx:end_idx]
        self.messages = self.messages[:start_idx] + self.messages[end_idx:]

        result["removed"] = len(removed)
        result["tokens_removed"] = tokens_to_remove
        result["remaining_messages"] = len(self.messages)

        self._update_total_tokens()
        return result

    def smart_prune(self) -> Dict[str, Any]:
        """
        分层裁剪策略，按保守程度从低到高执行：

        Level 0: 裁剪上下文消息（如 <model_switch>, <permissions> 等）
        Level 1: 清理已完成tool的旧结果（保守，只清空内容）
        Level 2: 清理 reasoning 内容
        Level 3: 按边界裁剪整条消息（激进）

        Returns:
            包含各层级裁剪结果的字典
        """
        results = {
            "actions": [],
            "final_tokens": self.get_total_tokens_with_reasoning(),
            "overflow": self.is_overflow()
        }

        # Level 0: 裁剪上下文消息
        contextual_result = self.prune_contextual_messages(protect_recent=2)
        if contextual_result["tokens_saved"] > 0:
            results["actions"].append({
                "level": 0,
                "action": "prune_contextual",
                "pruned_tokens": contextual_result["tokens_saved"],
                "messages_modified": contextual_result["messages_modified"],
                "parts_removed": contextual_result["parts_removed"]
            })

        # Level 1: 清理已完成tool的旧结果
        pruned1 = self.prune()
        if pruned1 > 0:
            results["actions"].append({
                "level": 1,
                "action": "prune_tool_results",
                "pruned_tokens": pruned1
            })

        # 检查是否还需要继续
        if self.is_overflow():
            # Level 2: 清理 reasoning 内容
            pruned2 = self.prune_reasoning_only()
            if pruned2 > 0:
                results["actions"].append({
                    "level": 2,
                    "action": "prune_reasoning",
                    "pruned_tokens": pruned2
                })

        # 再次检查是否还需要继续
        if self.is_overflow():
            # Level 3: 按边界裁剪整条消息
            # 保护2个turn，保留最多20个turn
            protect_turns = 2
            max_turns = 20

            # 计算当前有多少个用户turn
            user_count = sum(1 for m in self.messages if m.role == "user")
            if user_count > protect_turns:
                pruned3 = self.prune_to_user_boundary(
                    protect_turns=protect_turns,
                    max_turns=max_turns
                )
                if pruned3 > 0:
                    results["actions"].append({
                        "level": 3,
                        "action": "prune_user_boundary",
                        "pruned_messages": pruned3
                    })

        results["final_tokens"] = self.get_total_tokens_with_reasoning()
        results["overflow"] = self.is_overflow()
        return results

    def compact_streaming_parts(self) -> int:
        compacted = 0
        for msg in self.messages:
            for part in msg.parts:
                if part.streaming_content and part.is_streaming_done:
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
        """
        Filter messages.
        - Skip compacted summary messages
        - Replace compaction parts with "What did we do so far?"
        - Stop at first user message that has compaction after an assistant summary
        """
        result = []
        completed_user_ids: set = set()

        for msg in reversed(self.messages):
            # Check if this is a user message that follows a completed summary
            if msg.role == "user" and msg.message_id in completed_user_ids:
                has_compaction = any(p.part_type == PartType.COMPACTION.value for p in msg.parts)
                if has_compaction:
                    break

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

            # If this is a summary assistant message with finish, mark parent as completed
            if msg.role == "assistant" and msg.is_summary and msg.finish:
                if hasattr(msg, 'message_id') and msg.message_id:
                    completed_user_ids.add(msg.message_id)
                new_parts = []
                continue  # Skip summary messages

            if has_compaction:
                msg.parts = new_parts

            result.append(msg)

        result.reverse()
        return result

    def get_last_user_message(self) -> Optional["MessageWithParts"]:
        """Get the last user message"""
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg
        return None

    def get_last_assistant_message(self) -> Optional["MessageWithParts"]:
        """Get the last assistant message"""
        for msg in reversed(self.messages):
            if msg.role == "assistant":
                return msg
        return None

    def get_last_finished_assistant(self) -> Optional["MessageWithParts"]:
        """Get the last finished assistant message"""
        for msg in reversed(self.messages):
            if msg.role == "assistant" and msg.finish:
                return msg
        return None

    def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """Get pending compaction/subtask parts"""
        tasks = []
        for msg in self.messages:
            if msg.role == "assistant" and msg.finish:
                continue  # Don't collect tasks after finished assistant
            for part in msg.parts:
                if part.part_type == PartType.COMPACTION.value:
                    tasks.append({"type": "compaction", "part": part})
                elif part.part_type == PartType.SUBTASK.value:
                    tasks.append({"type": "subtask", "part": part})
        return tasks
    
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
        self._step: int = 0
        self._abort: bool = False

    def add_user_message(self, content: str, message_id: str = None):
        self.compaction.add_message("user", content, message_id=message_id)
        self._history.append(ChatMessage(role="user", content=content))

    def add_assistant_message(self, content: str, parts: List[MessagePart] = None, reasoning: str = None, message_id: str = None):
        self.compaction.add_message("assistant", content, parts, reasoning, message_id=message_id)
        self._history.append(ChatMessage(role="assistant", content=content))

    def get_conversation_context(self) -> List[ChatMessage]:
        """
        Get conversation context.
        Uses filter_compacted to exclude compacted summaries and replace markers.
        """
        filtered = self.compaction.filter_compacted()
        result = []
        for msg in filtered:
            if msg.is_summary:
                continue
            result.append(ChatMessage(role=msg.role, content=msg.content))
        return result[-20:] if len(result) > 20 else result

    async def run_loop(
        self,
        llm_summarize: Callable[[str], str],
        llm_stream_generator: Callable,  # Callable that returns an async generator of StreamChunks
        abort_signal: Any = None,
        max_steps: int = 100,
        structured_output_schema: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Run the conversation loop similar to OpenCode's loop() function.

        This implements the full OpenCode loop architecture:
        1. while(true) loop with step tracking
        2. filter_compacted() to get messages
        3. Find lastUser, lastAssistant, lastFinished, tasks
        4. Check overflow and compact if needed
        5. Process pending tasks (compaction, subtask)
        6. SessionProcessor handles LLM stream internally
        7. insertReminders for multi-turn conversations
        8. structured_output for JSON schema mode

        Returns control flow:
        - "continue": Continue the loop
        - "compact": Request compaction
        - "stop": Stop the loop
        """
        stats = {"steps": 0, "compactions": 0, "pruned_tokens": 0}
        structured_output_result = None
        is_last_step = False

        while self._step < max_steps:
            self._step += 1
            stats["steps"] = self._step
            is_last_step = self._step >= max_steps

            # Check abort signal
            if abort_signal and getattr(abort_signal, "is_aborted", lambda: False)():
                self._abort = True
                break

            msgs = self.compaction.filter_compacted()

            if not msgs:
                break

            last_user = self.compaction.get_last_user_message()
            last_assistant = self.compaction.get_last_assistant_message()
            last_finished = self.compaction.get_last_finished_assistant()

            if not last_user:
                break  # No user message, exit

            # Get pending tasks (compaction/subtask parts)
            tasks = self.compaction.get_pending_tasks()

            # Process pending tasks first
            if tasks:
                for task in tasks:
                    if task["type"] == "compaction":
                        if self.compaction.is_overflow(model_context_limit=self.max_tokens):
                            result = self.compaction.process(llm_summarize, abort_signal=abort_signal, auto=True)
                            stats["compactions"] += 1
                            stats["summary_length"] = result.get("summary_length", 0)
                            self._history = self._history[-10:] if len(self._history) > 10 else self._history
                            continue  # After compaction, continue to next iteration
                    elif task["type"] == "subtask":
                        # Handle subtask
                        # Subtasks represent sub-tasks that should be executed
                        subtask_part = task["part"]
                        if subtask_part.subtask_info:
                            subtask_info = subtask_part.subtask_info
                            prompt = subtask_info.get("prompt", "")
                            description = subtask_info.get("description", "")
                            agent = subtask_info.get("agent", "default")

                            # Mark the subtask as completed with a placeholder result
                            # In a full implementation, this would execute via an Agent system
                            subtask_result = {
                                "title": description or "Subtask completed",
                                "description": description,
                                "prompt": prompt,
                                "agent": agent,
                                "output": f"[Subtask '{description}' would be executed by agent '{agent}']",
                                "status": "completed"
                            }

                            # Update the subtask part with the result
                            stats["subtasks_executed"] = stats.get("subtasks_executed", 0) + 1

            # Check if we should exit the loop
            # lastAssistant.finish && !["tool-calls", "unknown"].includes(lastAssistant.finish) && lastUser.id < lastAssistant.id
            # The id comparison ensures we don't exit on the first turn
            if last_assistant and last_assistant.finish:
                finish = getattr(last_assistant, 'finish', None)
                if finish and finish not in ["tool-calls", "unknown"]:
                    # Use timestamp for comparison since message_id is string
                    # Only exit if user message timestamp < assistant message timestamp (not first turn)
                    if last_user.timestamp < last_assistant.timestamp:
                        break  # Exit loop if assistant finished naturally

            if self._step > 1 and last_finished:
                self.compaction.insert_reminders(last_finished.message_id)

            # Normal processing - use SessionProcessor internally
            if llm_stream_generator:
                # Get messages for LLM
                messages_for_llm = self.compaction.get_messages_for_llm(strip_media=False, include_reasoning=True)

                # Build system prompt
                system_prompt = self.build_system_prompt(structured_output=structured_output_schema is not None)

                # Resolve tools
                tools = self.resolve_tools()

                # Add structured output tool if schema is provided
                if structured_output_schema:
                    tools.append(self.create_structured_output_tool(structured_output_schema))

                # Add max steps message if on last step
                if is_last_step:
                    # Append a message indicating max steps reached
                    messages_for_llm.append({
                        "role": "assistant",
                        "content": MAX_STEPS_MESSAGE
                    })

                # Create SessionProcessor for internal stream handling
                processor = SessionProcessor(
                    compaction=self.compaction,
                    model=settings.LLM_MODEL,
                    abort_signal=abort_signal
                )

                # Get the stream generator
                stream_gen = llm_stream_generator(
                    messages=messages_for_llm,
                    system=system_prompt,
                    tools=tools,
                    tool_choice="required" if structured_output_schema else "auto"
                )

                # Process stream internally
                # SessionProcessor 在 finish-step 时检测实际 token 消耗并设置 needs_compaction
                result = await processor.process_stream(stream_gen)

                # Handle structured output result
                if processor.structured_output is not None:
                    # Structured output was captured, exit the loop
                    stats["structured_output"] = processor.structured_output
                    break

                # 处理完成后的控制流
                if result == "stop":
                    break
                elif result == "continue":
                    continue
                elif result == "compact":
                    # 步骤完成后检测到溢出，使用分层裁剪策略
                    # 这是精确检测（基于 finish-step 返回的实际 token 消耗）
                    prune_result = self.compaction.smart_prune()
                    stats["prune_levels"] = prune_result.get("actions", [])
                    stats["pruned_tokens"] = prune_result.get("final_tokens", 0)

                    # 如果裁剪后仍然溢出，执行摘要压缩
                    if self.compaction.is_overflow(model_context_limit=self.max_tokens):
                        compact_result = self.compaction.process(llm_summarize, abort_signal=abort_signal, auto=True)
                        stats["compactions"] = stats.get("compactions", 0) + 1
                        stats["summary_length"] = compact_result.get("summary_length", 0)
                        self._history = self._history[-10:] if len(self._history) > 10 else self._history

        return stats
    
    def check_and_compact(self, llm_summarize: Callable[[str], str], abort_signal: Any = None) -> Dict[str, Any]:
        stats = self.compaction.get_stats()

        if not self.compaction.is_overflow(model_context_limit=self.max_tokens):
            return stats

        # 使用分层裁剪策略 (Level 0-3)
        prune_result = self.compaction.smart_prune()
        stats["prune_levels"] = prune_result.get("actions", [])

        # 如果裁剪后仍然溢出，执行摘要压缩
        if self.compaction.is_overflow(model_context_limit=self.max_tokens):
            result = self.compaction.process(llm_summarize, abort_signal=abort_signal, auto=True)
            stats["compacted"] = True
            stats["summary_length"] = result.get("summary_length", 0)
            stats["added_continue_message"] = result.get("added_continue_message", False)
            self._history = self._history[-10:] if len(self._history) > 10 else self._history

        return stats

    def resolve_tools(self, tools_config: Dict[str, bool] = None) -> List[Dict[str, Any]]:
        """
        Resolve tools for AI SDK format

        Builds a list of tools in OpenAI function calling format.
        Filters tools based on tools_config if provided.

        Returns:
            List of tools in OpenAI function calling format
        """
        from mcp_client.client import mcp_client
        from skills.manager import skill_manager

        tools = []

        # Add skill tool
        skills = skill_manager.get_all_skills()
        if skills:
            skill_names = [s.name for s in skills]
            skill_hint = f"可用技能: {', '.join(skill_names)}" if skill_names else "无可用技能"
            tools.append({
                "type": "function",
                "function": {
                    "name": "skill",
                    "description": "加载技能。当没有可用的技能时不要调用此工具。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": skill_hint
                            }
                        },
                        "required": ["name"]
                    }
                }
            })

        # Add MCP tools
        for tc in mcp_client.all_tools:
            # Filter by tools_config if provided
            if tools_config and tools_config.get(tc.name) is False:
                continue

            tool_name = f"{tc.server}_{tc.name}" if tc.server else tc.name
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": f"{tc.server}: {tc.description}" if tc.server else tc.description,
                    "parameters": tc.input_schema
                }
            })

        return tools

    def create_structured_output_tool(self, schema: Dict[str, Any], on_success: Callable = None) -> Dict[str, Any]:
        """
        Create a structured output tool for JSON schema mode, similar to OpenCode's createStructuredOutputTool.

        Args:
            schema: JSON schema for the output
            on_success: Callback when tool is called successfully

        Returns:
            Tool definition in OpenAI format
        """
        return {
            "type": "function",
            "function": {
                "name": "StructuredOutput",
                "description": STRUCTURED_OUTPUT_DESCRIPTION,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "output": {
                            "type": "string",
                            "description": "The structured output in JSON format matching the requested schema"
                        }
                    },
                    "required": ["output"]
                }
            }
        }

    def build_system_prompt(self, structured_output: bool = False) -> str:
        """
        Build the system prompt

        Args:
            structured_output: Whether to add structured output instructions

        Returns:
            System prompt string
        """
        base_system = """你是一个智能助手。

你有两种扩展能力:
1. **MCP工具** - 来自外部MCP服务器的功能调用
2. **自定义Skills** - 你可以使用的专业技能

当需要使用某个技能时,使用 skill 工具加载该技能。"""

        from skills.manager import skill_manager
        skills_message = skill_manager.build_skills_system_message(compact=False)

        if skills_message:
            system = f"{base_system}\n\n<available_skills>\n{skills_message}\n</available_skills>"
        else:
            system = base_system

        if structured_output:
            system = f"{system}\n\n{STRUCTURED_OUTPUT_SYSTEM_PROMPT}"

        return system

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

    def prune_to_user_boundary(self, protect_turns: int = 2, max_turns: int = None) -> int:
        return self.compaction.prune_to_user_boundary(protect_turns, max_turns)

    def prune_contextual_messages(self, protect_recent: int = 2) -> Dict[str, Any]:
        return self.compaction.prune_contextual_messages(protect_recent)

    def rollback(self, n_turns: int = 1, message_index: int = None) -> Dict[str, Any]:
        """
        回退消息历史。

        Args:
            n_turns: 要回退的 Turn 数量，默认为 1
            message_index: 要回滚到的消息索引，优先于 n_turns

        Returns:
            回退结果字典
        """
        return self.compaction.rollback(n_turns, message_index)

    def delete_turn(self, message_index: int) -> Dict[str, Any]:
        """
        删除指定位置的 Turn（用户消息 + 对应的助手回复）。

        Args:
            message_index: 要删除的消息索引

        Returns:
            删除结果字典
        """
        return self.compaction.delete_turn(message_index)

    def remove_oldest_messages(self, n: int = 1) -> Dict[str, Any]:
        """
        删除最早的 N 条消息（FIFO 策略）。

        Args:
            n: 要删除的最早消息数量

        Returns:
            删除结果字典
        """
        return self.compaction.remove_oldest_messages(n)

    def truncate_tool_outputs(self, max_tokens_per_output: int = 500) -> Dict[str, Any]:
        """
        使用中间保留截断缩小大型工具输出。

        Args:
            max_tokens_per_output: 每个工具输出的最大 token 数

        Returns:
            截断结果字典
        """
        return self.compaction.truncate_tool_outputs(max_tokens_per_output)

    def smart_prune(self) -> Dict[str, Any]:
        return self.compaction.smart_prune()

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


class SessionProcessor:
    """
    Internal LLM processor similar to OpenCode's SessionProcessor.

    Handles all stream events internally and returns control flow values:
    - "continue": Continue the loop
    - "compact": Request compaction
    - "stop": Stop the loop
    """

    def __init__(
        self,
        compaction: "ConversationCompaction",
        model: str = None,
        abort_signal: Any = None
    ):
        self.compaction = compaction
        self.model = model or settings.LLM_MODEL
        self.abort_signal = abort_signal
        self.toolcalls: Dict[str, MessagePart] = {}
        self.snapshot: Optional[Snapshot] = None
        self.blocked = False
        self.needs_compaction = False
        self._message_id: Optional[str] = None
        self._reasoning_parts: Dict[str, MessagePart] = {}
        self.structured_output: Optional[Dict[str, Any]] = None  # Captured structured output result

    async def process_stream(self, stream_async_generator) -> str:
        """
        Process LLM stream internally

        Handles:
        - text-start/delta/end
        - reasoning-start/delta/end
        - tool-call/input-start/input-delta/input-end
        - tool-result
        - start-step/finish-step
        - error
        - done

        Returns:
        - "continue": Normal completion, continue loop
        - "compact": Needs compaction
        - "stop": Should stop
        """
        self.needs_compaction = False

        async for chunk in stream_async_generator:
            # Check abort
            if self.abort_signal and getattr(self.abort_signal, "is_aborted", lambda: False)():
                break

            if chunk.chunk_type == "text-start":
                msg_id = self.compaction.start_streaming_message("assistant")
                self._message_id = msg_id
                text_part = MessagePart(
                    part_type=PartType.TEXT.value,
                    content="",
                    token_count=0
                )
                for msg in self.compaction.messages:
                    if msg.message_id == msg_id:
                        msg.parts.append(text_part)
                        break

            elif chunk.chunk_type == "text-delta":
                delta = chunk.delta or chunk.content
                if delta:
                    for msg in self.compaction.messages:
                        if msg.message_id == self._message_id:
                            msg.content += delta
                            for part in msg.parts:
                                if part.part_type == PartType.TEXT.value:
                                    part.content += delta
                                    part.token_count = estimate(part.content)
                            break
                self.compaction._update_total_tokens()

            elif chunk.chunk_type == "text-end":
                for msg in self.compaction.messages:
                    if msg.message_id == self._message_id:
                        for part in msg.parts:
                            if part.part_type == PartType.TEXT.value:
                                part.is_streaming_done = True
                                break
                        break

            elif chunk.chunk_type == "reasoning-start":
                reasoning_part = MessagePart(
                    part_type=PartType.REASONING.value,
                    content="",
                    reasoning_content="",
                    token_count=0
                )
                self._reasoning_parts[chunk.tool_call_id or "default"] = reasoning_part
                if self._message_id:
                    for msg in self.compaction.messages:
                        if msg.message_id == self._message_id:
                            msg.parts.append(reasoning_part)
                            msg.reasoning = ""
                            break

            elif chunk.chunk_type == "reasoning-delta":
                delta = chunk.delta or chunk.content
                if delta:
                    for msg in self.compaction.messages:
                        if msg.message_id == self._message_id:
                            if msg.reasoning is None:
                                msg.reasoning = ""
                            msg.reasoning += delta
                            self.compaction.reasoning_tokens += estimate(delta)
                            break
                    for rid, part in self._reasoning_parts.items():
                        if part.content is not None:
                            part.content += delta
                            part.reasoning_content = part.content
                            part.token_count = estimate(part.content)
                self.compaction._update_total_tokens()

            elif chunk.chunk_type == "reasoning-end":
                for msg in self.compaction.messages:
                    if msg.message_id == self._message_id:
                        for part in msg.parts:
                            if part.part_type == PartType.REASONING.value:
                                part.is_streaming_done = True
                                break
                        break
                self._reasoning_parts.clear()

            elif chunk.chunk_type == "tool-call":
                tool_part = MessagePart(
                    part_type=PartType.TOOL.value,
                    content=chunk.tool_input or "",
                    tool_name=chunk.tool_name,
                    tool_call_id=chunk.tool_call_id,
                    tool_call_state=ToolCallState.EXECUTING,
                    token_count=estimate(chunk.tool_input or "")
                )
                self.toolcalls[chunk.tool_call_id] = tool_part
                if self._message_id:
                    for msg in self.compaction.messages:
                        if msg.message_id == self._message_id:
                            msg.parts.append(tool_part)
                            msg.tool_calls[chunk.tool_call_id] = tool_part
                            msg.pending_tool_count += 1
                            break

            elif chunk.chunk_type == "tool-result":
                if self._message_id and chunk.tool_call_id in self.toolcalls:
                    tool_part = self.toolcalls[chunk.tool_call_id]
                    tool_part.content = chunk.tool_output or chunk.content
                    tool_part.tool_call_state = ToolCallState.COMPLETED
                    tool_part.token_count = estimate(tool_part.content)
                    if tool_part.tool_state:
                        tool_part.tool_state.status = ToolCallState.COMPLETED
                        tool_part.tool_state.output = tool_part.content
                        tool_part.tool_state.updated = time.time()
                        if chunk.attachments:
                            tool_part.tool_state.attachments = chunk.attachments
                    for msg in self.compaction.messages:
                        if msg.message_id == self._message_id:
                            msg.completed_tool_count += 1
                            msg.pending_tool_count = max(0, msg.pending_tool_count - 1)
                            break

                    # Capture structured output result
                    if tool_part.tool_name == "StructuredOutput" and chunk.tool_output:
                        try:
                            self.structured_output = json.loads(chunk.tool_output)
                        except json.JSONDecodeError:
                            self.structured_output = {"output": chunk.tool_output}

                    del self.toolcalls[chunk.tool_call_id]
                self.compaction._update_total_tokens()

            elif chunk.chunk_type == "start-step":
                if self._message_id:
                    snapshot_part = MessagePart(
                        part_type=PartType.STEP_START.value,
                        content="",
                        snapshot_data=chunk.snapshot_data or {}
                    )
                    for msg in self.compaction.messages:
                        if msg.message_id == self._message_id:
                            msg.parts.append(snapshot_part)
                            break

            elif chunk.chunk_type == "finish-step":
                if self._message_id:
                    step_finish_part = MessagePart(
                        part_type=PartType.STEP_FINISH.value,
                        content="",
                        step_tokens=chunk.usage.get("total") if chunk.usage else None,
                        step_cost=chunk.cost
                    )
                    for msg in self.compaction.messages:
                        if msg.message_id == self._message_id:
                            msg.parts.append(step_finish_part)
                            break
                    if chunk.usage:
                        usage = TokenUsage.from_dict(chunk.usage)
                        self.compaction._token_tracker.add_usage(usage)
                        if chunk.usage.get("total"):
                            self.compaction.add_step_tokens(chunk.usage.get("total"), chunk.cost or 0)
                    # Check overflow after step
                    if self.compaction.is_overflow(model_context_limit=settings.CONVERSATION_MAX_TOKENS):
                        self.needs_compaction = True

            elif chunk.chunk_type == "error":
                # Error handling - mark failed tool calls
                if self._message_id and chunk.tool_call_id in self.toolcalls:
                    tool_part = self.toolcalls[chunk.tool_call_id]
                    tool_part.tool_call_state = ToolCallState.FAILED
                    tool_part.tool_call_error = chunk.content
                    if tool_part.tool_state:
                        tool_part.tool_state.status = ToolCallState.FAILED
                        tool_part.tool_state.updated = time.time()
                    del self.toolcalls[chunk.tool_call_id]

            elif chunk.chunk_type == "done":
                # Finalize the message - create one if _message_id is None (no text content was streamed)
                if self._message_id is None:
                    # Create an assistant message if none exists
                    msg_id = self.compaction.start_streaming_message("assistant")
                    self._message_id = msg_id
                    # Create text part
                    text_part = MessagePart(
                        part_type=PartType.TEXT.value,
                        content="",
                        token_count=0
                    )
                    for msg in self.compaction.messages:
                        if msg.message_id == msg_id:
                            msg.parts.append(text_part)
                            break

                message_id = self._message_id
                if message_id:
                    for msg in self.compaction.messages:
                        if msg.message_id == message_id:
                            msg.finish = "stop"
                            break
                    self.compaction.finalize_streaming_message(message_id)

                # Mark remaining tool calls as failed
                for tool_id, tool_part in list(self.toolcalls.items()):
                    tool_part.tool_call_state = ToolCallState.FAILED
                    tool_part.tool_call_error = "Tool execution aborted"
                self.toolcalls.clear()

            if self.needs_compaction:
                break

        # Handle cleanup
        for tool_id, tool_part in list(self.toolcalls.items()):
            tool_part.tool_call_state = ToolCallState.FAILED
            tool_part.tool_call_error = "Tool execution aborted"
        self.toolcalls.clear()

        # Return control flow value
        if self.needs_compaction:
            return "compact"
        if self.blocked:
            return "stop"
        return "continue"


conversation_manager = ConversationManager()