"""Token cost calculator for Claude Code sessions.

Rates loaded from data/telemetry/model-pricing.yaml — same pattern as
tool-colors.yaml and stage-config.yaml.  No hardcoded pricing in Python.

Rates are dated. A model may carry an ``introductory`` block with an ``until``
date, and a turn is priced by the rate in effect when it ran — so a receipt
regenerated months later still reports what the session actually cost, and a
promotional rate lapsing does not silently restate history. Callers that have
no timestamp get the durable sticker rate.
"""

from __future__ import annotations

import datetime as _dt
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_PRICING_PATH = Path(__file__).resolve().parent.parent / "data" / "telemetry" / "model-pricing.yaml"

# Below this year a timestamp is a parse failure, not a session date — both
# parsers fall back to the Unix epoch when a transcript's timestamp is unreadable.
_PLAUSIBLE_SESSION_YEAR = 2000


@lru_cache(maxsize=1)
def _load_pricing() -> dict[str, Any]:
    with _PRICING_PATH.open() as f:
        result: dict[str, Any] = yaml.safe_load(f)
        return result


def _rate_on(rates: dict[str, Any], at: _dt.datetime | _dt.date | None) -> dict[str, float]:
    """Pick the introductory or sticker rate for the moment a turn ran.

    ``at is None`` means the caller has no session date — the sticker is the
    honest answer there, since it is the rate that outlives the promotion.
    """
    intro = rates.get("introductory")
    if not isinstance(intro, dict) or at is None:
        return {"input": float(rates["input"]), "output": float(rates["output"])}

    until = intro.get("until")
    if not isinstance(until, _dt.date):
        # A malformed `until` must not silently hand out the cheaper rate.
        logger.warning("introductory rate ignored: `until` is not a date (%r)", until)
        return {"input": float(rates["input"]), "output": float(rates["output"])}

    ran_on = at.date() if isinstance(at, _dt.datetime) else at
    if ran_on.year < _PLAUSIBLE_SESSION_YEAR:
        # Both parsers fall back to the epoch on an unreadable timestamp. 1970
        # predates every `until`, so a parse failure would silently qualify for
        # any promotion ever recorded. Treat it as no date at all.
        return {"input": float(rates["input"]), "output": float(rates["output"])}
    if ran_on <= until:
        return {"input": float(intro["input"]), "output": float(intro["output"])}
    return {"input": float(rates["input"]), "output": float(rates["output"])}


def _get_rates(model: str, at: _dt.datetime | _dt.date | None = None) -> dict[str, float]:
    pricing = _load_pricing()
    models: dict[str, dict[str, Any]] = pricing.get("models", {})

    # Exact match first
    if model in models:
        return _rate_on(models[model], at)

    # Prefix match (e.g. "claude-opus-4-6-20260401" -> "claude-opus-4-6"),
    # LONGEST key first so "gpt-5.4" cannot swallow "gpt-5.4-mini". The order is
    # computed here rather than inherited from the YAML: key order in a data
    # file is an invariant no reader can see, and getting it wrong prices a
    # model at a sibling's rate with nothing to show for it.
    for known_model in sorted(models, key=len, reverse=True):
        if model.startswith(known_model):
            return _rate_on(models[known_model], at)

    # Parallel to `classify_tool`'s unknown_tool warning. A model reaching the
    # default is priced at a guess; a silent guess is how a flagship model can
    # bill at a placeholder rate for months without anything looking wrong.
    logger.warning(
        "unknown_model: %r — falling back to default pricing; add it to data/telemetry/model-pricing.yaml to silence",
        model,
    )
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


def calculate_turn_cost(
    usage: dict[str, Any],
    model: str = "",
    at: _dt.datetime | _dt.date | None = None,
) -> float:
    """Calculate the cost of a single turn from token usage.

    ``at`` is when the turn ran; it selects between a model's introductory and
    sticker rates. Omit it only when no date is available — the sticker applies.
    """
    pricing = _load_pricing()
    rates = _get_rates(model, at)
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
    """Calculate the total cost of a session from all turns.

    A turn may carry a ``timestamp`` so dated rates apply per turn; turns
    without one price at the sticker.
    """
    total = 0.0
    for turn in turns:
        usage = turn.get("usage", {})
        model = turn.get("model", "")
        at = turn.get("timestamp")
        total += calculate_turn_cost(usage, model, at if isinstance(at, _dt.date) else None)
    return total
