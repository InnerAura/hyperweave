"""Token cost calculator for Claude Code sessions.

Rates loaded from data/telemetry/model-pricing.yaml — same pattern as
tool-colors.yaml and stage-config.yaml.  No hardcoded pricing in Python.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_PRICING_PATH = Path(__file__).resolve().parent.parent / "data" / "telemetry" / "model-pricing.yaml"


@lru_cache(maxsize=1)
def _load_pricing() -> dict[str, Any]:
    with _PRICING_PATH.open() as f:
        result: dict[str, Any] = yaml.safe_load(f)
        return result


def _get_rates(model: str) -> dict[str, float]:
    pricing = _load_pricing()
    models: dict[str, dict[str, float]] = pricing.get("models", {})

    # Exact match first
    if model in models:
        return models[model]

    # Prefix match (e.g. "claude-opus-4-6-20260401" -> "claude-opus-4-6")
    for known_model, rates in models.items():
        if model.startswith(known_model):
            return rates

    default: dict[str, float] = pricing.get("default", {"input": 5.0, "output": 25.0})
    return default


def _cache_write_cost(usage: dict[str, Any], pricing: dict[str, Any], input_rate: float) -> float:
    """Cache-write cost, TTL-aware.

    Claude Code splits cache writes by TTL in ``usage.cache_creation``
    (``{ephemeral_5m_input_tokens, ephemeral_1h_input_tokens}``) — 5-minute
    entries bill at 1.25x the input rate, 1-hour entries at 2x. Current
    Claude Code writes 1h exclusively, so pricing the flat total at the 5m
    multiplier undercounts. Transcripts that predate the split (and Codex,
    which forces cache_create to zero) fall back to the flat
    ``cache_creation_input_tokens`` field at the 5m rate.
    """
    write_mult_5m: float = pricing.get("cache_write_multiplier", 1.25)
    write_mult_1h: float = pricing.get("cache_write_multiplier_1h", 2.0)

    detail = usage.get("cache_creation")
    if isinstance(detail, dict):
        write_5m = int(detail.get("ephemeral_5m_input_tokens", 0) or 0)
        write_1h = int(detail.get("ephemeral_1h_input_tokens", 0) or 0)
        if write_5m + write_1h > 0:
            return (write_5m * write_mult_5m + write_1h * write_mult_1h) * input_rate

    cache_creation: int = usage.get("cache_creation_input_tokens", 0)
    return cache_creation * write_mult_5m * input_rate


def calculate_turn_cost(usage: dict[str, Any], model: str = "") -> float:
    """Calculate the cost of a single turn from token usage."""
    pricing = _load_pricing()
    rates = _get_rates(model)
    input_rate = rates["input"] / 1_000_000  # per-token rate
    output_rate = rates["output"] / 1_000_000

    cache_read_mult: float = pricing.get("cache_read_multiplier", 0.1)

    input_tokens: int = usage.get("input_tokens", 0)
    output_tokens: int = usage.get("output_tokens", 0)
    cache_read: int = usage.get("cache_read_input_tokens", 0)

    return float(
        (input_tokens * input_rate)
        + (output_tokens * output_rate)
        + _cache_write_cost(usage, pricing, input_rate)
        + (cache_read * cache_read_mult * input_rate)
    )


def calculate_session_cost(turns: list[dict[str, Any]]) -> float:
    """Calculate the total cost of a session from all turns."""
    total = 0.0
    for turn in turns:
        usage = turn.get("usage", {})
        model = turn.get("model", "")
        total += calculate_turn_cost(usage, model)
    return total
