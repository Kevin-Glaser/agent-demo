import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

CHARS_PER_TOKEN = 4


def estimate(text: str) -> int:
    return max(0, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def estimate_messages(messages: list) -> int:
    total = 0
    for msg in messages:
        if hasattr(msg, 'content'):
            total += estimate(msg.content)
        elif isinstance(msg, dict):
            total += estimate(msg.get('content', ''))
    return total


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    
    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_write_tokens
    
    @property
    def cache_total(self) -> int:
        return self.cache_read_tokens + self.cache_write_tokens
    
    def usable(self, max_output_tokens: int = 4096) -> int:
        return self.total - max_output_tokens
    
    def to_dict(self) -> Dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "total": self.total
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> "TokenUsage":
        return cls(
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cache_read_tokens=data.get("cache_read_tokens", 0),
            cache_write_tokens=data.get("cache_write_tokens", 0)
        )
    
    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens
        )


@dataclass
class TokenBudget:
    input_limit: int = 128000
    context_limit: int = 128000
    max_output_tokens: int = 4096
    
    @property
    def input_reserved(self) -> int:
        return self.context_limit - self.input_limit
    
    def is_overflow(self, usage: TokenUsage) -> bool:
        return usage.total >= (self.input_limit - self.max_output_tokens)
    
    def usable_tokens(self, usage: TokenUsage) -> int:
        return self.input_limit - usage.total - self.max_output_tokens


@dataclass
class CumulativeTokenTracker:
    total_input: int = 0
    total_output: int = 0
    total_cache_read: int = 0
    total_cache_write: int = 0
    total_tokens: int = 0
    step_count: int = 0
    step_tokens: List[int] = field(default_factory=list)
    step_costs: List[float] = field(default_factory=list)
    last_update: float = field(default_factory=time.time)
    
    def add_usage(self, usage: TokenUsage):
        self.total_input += usage.input_tokens
        self.total_output += usage.output_tokens
        self.total_cache_read += usage.cache_read_tokens
        self.total_cache_write += usage.cache_write_tokens
        self.total_tokens = self.total_input + self.total_output + self.total_cache_read + self.total_cache_write
        self.last_update = time.time()
    
    def add_step(self, tokens: int, cost: float = 0.0):
        self.step_count += 1
        self.step_tokens.append(tokens)
        self.step_costs.append(cost)
    
    @property
    def average_step_tokens(self) -> float:
        if not self.step_tokens:
            return 0.0
        return sum(self.step_tokens) / len(self.step_tokens)
    
    @property
    def total_cost(self) -> float:
        return sum(self.step_costs)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_input": self.total_input,
            "total_output": self.total_output,
            "total_cache_read": self.total_cache_read,
            "total_cache_write": self.total_cache_write,
            "total_tokens": self.total_tokens,
            "step_count": self.step_count,
            "average_step_tokens": self.average_step_tokens,
            "total_cost": self.total_cost
        }