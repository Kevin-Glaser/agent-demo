"""Test token estimation."""
from session.token import estimate, TokenUsage, TokenBudget


def test_estimate():
    # 4 chars per token, so "hello" (5 chars) = 2 tokens
    assert estimate("hello") == 2
    assert estimate("") == 0


def test_token_usage_total():
    usage = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        cache_read_tokens=200,
        cache_write_tokens=100
    )
    assert usage.total == 1800
    assert usage.cache_total == 300


def test_token_budget_is_overflow():
    budget = TokenBudget(input_limit=10000, context_limit=10000, max_output_tokens=500)
    # is_overflow: usage.total >= (input_limit - max_output_tokens)
    # 9600 >= 9500 = True
    usage = TokenUsage(input_tokens=9600, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0)
    assert budget.is_overflow(usage) is True
