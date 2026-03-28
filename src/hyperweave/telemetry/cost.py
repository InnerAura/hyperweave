"""Token cost calculator for Claude Code sessions."""

from __future__ import annotations

from typing import Any

# Pricing per million tokens (USD)
# Source: Anthropic published rates
_MODEL_RATES: dict[str, dict[str, float]] = {
    "claude-opus-4-6": {
        "input": 15.0,
        "output": 75.0,
    },
    "claude-opus-4-20250918": {
        "input": 15.0,
        "output": 75.0,
    },
    "claude-sonnet-4-20250514": {
        "input": 3.0,
        "output": 15.0,
    },
    "claude-3-5-sonnet-20241022": {
        "input": 3.0,
        "output": 15.0,
    },
    "claude-3-5-haiku-20241022": {
        "input": 0.80,
        "output": 4.0,
    },
}

# Default to Opus 4 rates when model is unknown
_DEFAULT_RATES: dict[str, float] = {
    "input": 15.0,
    "output": 75.0,
}


def _get_rates(model: str) -> dict[str, float]:
    # Try exact match first, then prefix matching
    if model in _MODEL_RATES:
        return _MODEL_RATES[model]

    for known_model, rates in _MODEL_RATES.items():
        if model.startswith(known_model.rsplit("-", 1)[0]):
            return rates

    return _DEFAULT_RATES


def calculate_turn_cost(usage: dict[str, Any], model: str = "") -> float:
    """Calculate the cost of a single turn from token usage."""
    rates = _get_rates(model)
    input_rate = rates["input"] / 1_000_000  # per-token rate
    output_rate = rates["output"] / 1_000_000

    input_tokens: int = usage.get("input_tokens", 0)
    output_tokens: int = usage.get("output_tokens", 0)
    cache_creation: int = usage.get("cache_creation_input_tokens", 0)
    cache_read: int = usage.get("cache_read_input_tokens", 0)

    return float(
        (input_tokens * input_rate)
        + (output_tokens * output_rate)
        + (cache_creation * 1.25 * input_rate)
        + (cache_read * 0.1 * input_rate)
    )


def calculate_session_cost(turns: list[dict[str, Any]]) -> float:
    """Calculate the total cost of a session from all turns."""
    total = 0.0
    for turn in turns:
        usage = turn.get("usage", {})
        model = turn.get("model", "")
        total += calculate_turn_cost(usage, model)
    return total
