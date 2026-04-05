"""
Model Reasoning Capability Management

参考 Codex 的设计，借鉴其架构思想但保持简洁。

提供:
1. ReasoningType - 类型区分 (SUMMARY/RAW/INTERLEAVED/NONE)
2. ReasoningEffort - 完整级别 (None/Minimal/Auto/Low/Medium/High/XHigh)
3. ReasoningItem - 内容存储
4. ModelReasoningCapability - 模型能力
5. InterleavedReasoningParser - 交错式内容解析
6. resolve_effort / get_resolved_effort - Effort 验证与回退
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict


class ReasoningType(Enum):
    """Reasoning 类型区分"""
    NONE = "none"           # 不支持 reasoning
    SUMMARY = "summary"     # OpenAI 风格 - 返回处理过的摘要 (如 o1, o3)
    RAW = "raw"             # 开源风格 - 返回原始推理内容 (如 deepseek-r1, qwq)
    INTERLEAVED = "interleaved"  # 交错式 - 推理与内容混合在同一流中 (如 Ollama)


class ReasoningEffort(Enum):
    """Reasoning Effort 级别"""
    NONE = "none"           # 禁用 reasoning
    MINIMAL = "minimal"     # 最小化推理
    AUTO = "auto"           # 模型自行决定
    LOW = "low"             # 简单推理
    MEDIUM = "medium"       # 标准推理
    HIGH = "high"           # 深度推理
    XHIGH = "xhigh"        # 超深度推理

    @staticmethod
    def effort_rank(effort: "ReasoningEffort") -> int:
        """返回 effort 的级别排名，用于回退计算"""
        ranks = {
            ReasoningEffort.NONE: 0,
            ReasoningEffort.MINIMAL: 1,
            ReasoningEffort.AUTO: 2,
            ReasoningEffort.LOW: 3,
            ReasoningEffort.MEDIUM: 4,
            ReasoningEffort.HIGH: 5,
            ReasoningEffort.XHIGH: 6,
        }
        return ranks.get(effort, 2)

    @staticmethod
    def from_string(s: str) -> "ReasoningEffort":
        """从字符串解析 Effort"""
        s = s.lower().strip()
        mapping = {
            "none": ReasoningEffort.NONE,
            "minimal": ReasoningEffort.MINIMAL,
            "auto": ReasoningEffort.AUTO,
            "low": ReasoningEffort.LOW,
            "medium": ReasoningEffort.MEDIUM,
            "high": ReasoningEffort.HIGH,
            "xhigh": ReasoningEffort.XHIGH,
        }
        return mapping.get(s, ReasoningEffort.AUTO)


@dataclass
class ModelReasoningCapability:
    """模型 Reasoning 能力"""
    supported: bool                              # 是否支持 reasoning
    reasoning_type: ReasoningType = ReasoningType.NONE  # 支持的 reasoning 类型
    default_effort: ReasoningEffort = ReasoningEffort.AUTO  # 默认 effort
    supported_efforts: List[ReasoningEffort] = field(
        default_factory=lambda: [ReasoningEffort.AUTO]
    )  # 支持的 effort 列表


@dataclass
class ReasoningItem:
    """
    Reasoning 内容存储

    Reasoning 类型与存储字段对应关系：
    - SUMMARY (OpenAI o1/o3): API 返回的 reasoning 字段是处理过的摘要
      → 存储在 summary_text

    - RAW (DeepSeek R1, QWQ): API 返回的 reasoning 字段是原始推理过程
      → 存储在 raw_content

    - INTERLEAVED (Ollama): API 返回的 content 中交错包含 reasoning 标签
      → 需要解析，存储在 interleaved_segments

    注意：每个 ReasoningItem 只使用一种存储字段，取决于模型的 reasoning_type
    """
    id: str
    summary_text: List[str] = field(default_factory=list)   # SUMMARY 类型存储
    raw_content: List[str] = field(default_factory=list)   # RAW 类型存储
    interleaved_segments: List[Dict[str, str]] = field(default_factory=list)  # INTERLEAVED 类型存储

    def add_summary(self, text: str):
        """添加 SUMMARY 类型内容 (OpenAI o1/o3 等)"""
        self.summary_text.append(text)

    def add_raw(self, text: str):
        """添加 RAW 类型内容 (DeepSeek R1, QWQ 等)"""
        self.raw_content.append(text)

    def add_interleaved(self, segment_type: str, text: str):
        """
        添加 INTERLEAVED 类型段落 (Ollama 等)

        Args:
            segment_type: "reasoning" 或 "content"
            text: 段落内容
        """
        self.interleaved_segments.append({"type": segment_type, "content": text})

    def get_interleaved_reasoning(self) -> str:
        """获取所有交错段落中的 reasoning 部分"""
        return "\n".join(
            seg["content"]
            for seg in self.interleaved_segments
            if seg["type"] == "reasoning"
        )

    def get_interleaved_content(self) -> str:
        """获取所有交错段落中的 content 部分"""
        return "".join(
            seg["content"]
            for seg in self.interleaved_segments
            if seg["type"] == "content"
        )

    @property
    def content(self) -> str:
        """统一访问入口 - 返回最终输出内容"""
        if self.summary_text:
            return "\n".join(self.summary_text)
        if self.raw_content:
            return "\n".join(self.raw_content)
        if self.interleaved_segments:
            return self.get_interleaved_content()
        return ""

    @property
    def reasoning_content(self) -> str:
        """获取 reasoning 内容（统一入口）"""
        if self.summary_text or self.raw_content:
            return self.content
        if self.interleaved_segments:
            return self.get_interleaved_reasoning()
        return ""

    @property
    def reasoning_type(self) -> ReasoningType:
        """返回当前内容的类型"""
        if self.summary_text:
            return ReasoningType.SUMMARY
        if self.raw_content:
            return ReasoningType.RAW
        if self.interleaved_segments:
            return ReasoningType.INTERLEAVED
        return ReasoningType.NONE


# 模型注册表
MODEL_REGISTRY: dict[str, ModelReasoningCapability] = {
    # OpenAI o1/o3 系列 - SUMMARY 类型
    "o1": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.SUMMARY,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.NONE, ReasoningEffort.MINIMAL, ReasoningEffort.AUTO, ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH, ReasoningEffort.XHIGH]
    ),
    "o1-mini": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.SUMMARY,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.NONE, ReasoningEffort.MINIMAL, ReasoningEffort.AUTO, ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH, ReasoningEffort.XHIGH]
    ),
    "o1-preview": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.SUMMARY,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.NONE, ReasoningEffort.MINIMAL, ReasoningEffort.AUTO, ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH, ReasoningEffort.XHIGH]
    ),
    "o3": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.SUMMARY,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.NONE, ReasoningEffort.MINIMAL, ReasoningEffort.AUTO, ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH, ReasoningEffort.XHIGH]
    ),
    "o3-mini": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.SUMMARY,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.NONE, ReasoningEffort.MINIMAL, ReasoningEffort.AUTO, ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH, ReasoningEffort.XHIGH]
    ),
    "o3-pro": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.SUMMARY,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.NONE, ReasoningEffort.MINIMAL, ReasoningEffort.AUTO, ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH, ReasoningEffort.XHIGH]
    ),

    # DeepSeek R1 系列 - RAW 类型
    "deepseek-r1": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.RAW,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.AUTO]
    ),
    "deepseek-r1-250120": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.RAW,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.AUTO]
    ),
    "deepseek-r1-distill-qwen-32b": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.RAW,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.AUTO]
    ),
    "deepseek-r1-distill-llama-70b": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.RAW,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.AUTO]
    ),

    # 阿里 QWQ 系列 - RAW 类型
    "qwq": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.RAW,
        default_effort=ReasoningEffort.LOW,
        supported_efforts=[ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH]
    ),
    "qwq-32b": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.RAW,
        default_effort=ReasoningEffort.LOW,
        supported_efforts=[ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH]
    ),
    "qwq-plus": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.RAW,
        default_effort=ReasoningEffort.LOW,
        supported_efforts=[ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH]
    ),

    # MiniMax 01 - RAW 类型
    "minimax-01": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.RAW,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.AUTO]
    ),

    # Ollama 本地模型 - INTERLEAVED 类型
    "llama3.1-70b": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.INTERLEAVED,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.AUTO]
    ),
    "llama3.1-405b": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.INTERLEAVED,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.AUTO]
    ),
    "qwen2.5-72b": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.INTERLEAVED,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.AUTO]
    ),
    "mistral-7b": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.INTERLEAVED,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.AUTO]
    ),
    "codellama-70b": ModelReasoningCapability(
        supported=True,
        reasoning_type=ReasoningType.INTERLEAVED,
        default_effort=ReasoningEffort.AUTO,
        supported_efforts=[ReasoningEffort.AUTO]
    ),

    # 非 reasoning 模型
    "gpt-4o": ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    ),
    "gpt-4o-mini": ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    ),
    "gpt-4-turbo": ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    ),
    "claude-3-5-sonnet": ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    ),
    "claude-3-5-haiku": ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    ),
    "claude-3-opus": ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    ),
    "deepseek-chat": ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    ),
    "deepseek-coder": ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    ),
    "qwen": ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    ),
    "qwen-turbo": ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    ),
    "qwen-plus": ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    ),
    "qwen-coder": ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    ),
    "minimax": ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    ),
}


def get_model_reasoning_capability(model: str) -> ModelReasoningCapability:
    """
    获取模型的 reasoning 能力

    1. 精确匹配模型名称
    2. 模糊匹配 (检查是否包含已知 reasoning 模型名称)
    3. 默认返回不支持
    """
    model_lower = model.lower()

    # 1. 精确匹配
    if model_lower in MODEL_REGISTRY:
        return MODEL_REGISTRY[model_lower]

    # 2. 模糊匹配
    reasoning_patterns = [
        ("r1", ReasoningType.RAW),
        ("qwq", ReasoningType.RAW),
        ("o1", ReasoningType.SUMMARY),
        ("o3", ReasoningType.SUMMARY),
        ("o4", ReasoningType.SUMMARY),
        ("minimax-01", ReasoningType.RAW),

        # {{reasoning}}...{{/reasoning}}
        re.compile(r'\{\{reasoning\}\}(.*?)\{\{\/reasoning\}\}', re.DOTALL),    ]

    for pattern, rtype in reasoning_patterns:
        if pattern in model_lower:
            return ModelReasoningCapability(
                supported=True,
                reasoning_type=rtype,
                default_effort=ReasoningEffort.AUTO,
                supported_efforts=[ReasoningEffort.AUTO]
            )

    # 3. 默认不支持
    return ModelReasoningCapability(
        supported=False,
        reasoning_type=ReasoningType.NONE
    )


def is_reasoning_model(model: str) -> bool:
    """判断模型是否支持 reasoning (简化接口)"""
    return get_model_reasoning_capability(model).supported


def get_reasoning_type(model: str) -> ReasoningType:
    """获取模型的 reasoning 类型"""
    return get_model_reasoning_capability(model).reasoning_type


def resolve_effort(
    requested: ReasoningEffort,
    supported_efforts: list[ReasoningEffort],
    default: ReasoningEffort = ReasoningEffort.AUTO
) -> ReasoningEffort:
    """
    解析并验证请求的 effort 级别

    如果请求的 effort 不在支持列表中，会回退到最接近的支持级别。
    """
    if not supported_efforts:
        return default

    if requested in supported_efforts:
        return requested

    requested_rank = ReasoningEffort.effort_rank(requested)

    best_match = default
    best_rank_diff = float('inf')

    for effort in supported_efforts:
        rank = ReasoningEffort.effort_rank(effort)
        diff = abs(rank - requested_rank)
        if rank <= requested_rank and diff < best_rank_diff:
            best_match = effort
            best_rank_diff = diff

    if best_match == default and best_rank_diff == float('inf'):
        for effort in supported_efforts:
            rank = ReasoningEffort.effort_rank(effort)
            diff = abs(rank - requested_rank)
            if diff < best_rank_diff:
                best_match = effort
                best_rank_diff = diff

    return best_match


def get_resolved_effort(model: str, requested_effort: ReasoningEffort) -> tuple[ReasoningEffort, ReasoningEffort]:
    """
    获取模型解析后的有效 effort 级别

    Args:
        model: 模型名称
        requested_effort: 请求的 effort（来自配置）

    Returns:
        (resolved_effort, is_fallback) - 解析后的 effort 和是否发生了回退
    """
    capability = get_model_reasoning_capability(model)

    if not capability.supported:
        return ReasoningEffort.NONE, False

    original = resolve_effort(
        requested_effort,
        capability.supported_efforts,
        capability.default_effort
    )

    is_fallback = original != requested_effort
    return original, is_fallback


class InterleavedReasoningParser:
    """
    解析交错式 Reasoning 内容

    支持的格式:
    1. <reasoning>...</reasoning>content
    2. <think>...</think>content
    3. {{reasoning}}...{{/reasoning}}content
    """

    # 匹配各种 reasoning 标签格式
    REASONING_PATTERNS = [
        # <reasoning>...</reasoning>
        re.compile(r'<reasoning>(.*?)</reasoning>', re.DOTALL),
        # <think>...</think> (Anthropic/Ollama format)
        re.compile(r'<think>\n(.*?)\n</think>', re.DOTALL),
        # {{reasoning}}...{{/reasoning}}
        re.compile(r'\{\{reasoning\}\}(.*?)\{\{\/reasoning\}\}', re.DOTALL),
    ]

    @classmethod
    def parse(cls, text: str, reasoning_item: ReasoningItem) -> str:
        """
        解析交错式内容，提取 reasoning 部分

        Args:
            text: 原始内容（可能包含 reasoning 和 content）
            reasoning_item: ReasoningItem 实例，用于存储提取的 reasoning

        Returns:
            清理后的纯内容（移除 reasoning 标签）
        """
        if not text:
            return ""

        remaining = text
        content_parts = []

        # Keep trying all patterns until no more reasoning tags are found
        while True:
            # Find the earliest match among all patterns
            earliest_match = None
            earliest_pattern = None
            earliest_start = len(remaining) + 1

            for pattern in cls.REASONING_PATTERNS:
                match = pattern.search(remaining)
                if match and match.start() < earliest_start:
                    earliest_match = match
                    earliest_pattern = pattern
                    earliest_start = match.start()

            if earliest_match is None:
                break

            # Parse with the pattern that has the earliest match
            remaining = cls._parse_with_pattern(remaining, earliest_pattern, reasoning_item, content_parts)

        # Append any remaining content after all reasoning tags
        if remaining:
            content_parts.append(remaining)

        return "".join(content_parts)

    @classmethod
    def _parse_with_pattern(
        cls,
        text: str,
        pattern: re.Pattern,
        reasoning_item: ReasoningItem,
        content_parts: list
    ) -> str:
        """使用指定模式解析内容"""
        last_end = 0
        for match in pattern.finditer(text):
            if match.start() > last_end:
                content_parts.append(text[last_end:match.start()])

            reasoning_content = match.group(1).strip()
            if reasoning_content:
                reasoning_item.add_interleaved("reasoning", reasoning_content)

            last_end = match.end()

        return text[last_end:]

    @classmethod
    def extract_from_stream(cls, text: str) -> tuple[str, str]:
        """
        从流式内容中提取 reasoning 和 content

        Args:
            text: 增量内容

        Returns:
            (reasoning, content) - 可能为空的 reasoning 和 content
        """
        reasoning = ""
        content = ""

        for pattern in cls.REASONING_PATTERNS:
            matches = list(pattern.finditer(text))
            if matches:
                last_end = 0
                for match in matches:
                    if match.start() > last_end:
                        content += text[last_end:match.start()]
                    reasoning_content = match.group(1).strip()
                    if reasoning_content:
                        reasoning += reasoning_content
                    last_end = match.end()
                content += text[last_end:]
                return reasoning, content

        return "", text
