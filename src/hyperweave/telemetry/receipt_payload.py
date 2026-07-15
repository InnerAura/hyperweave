"""``receipt/1`` payload assembler — the single source of receipt data.

`build_receipt_payload` folds a parsed `SessionTelemetry` into the canonical
``receipt/1`` dict. That dict is the one source of receipt data: it is embedded
verbatim as the artifact's ``hw:payload`` (and hashed into the ``hwz/1``
envelope id) AND consumed by the receipt resolver to draw the frame. Because
the embedded form is a hashed contract, the payload is **compact and data-only**
— raw numeric values, never formatted display strings (``cost_usd: 175.01``,
never ``"$175.01"``; ``cost_pct: 73``, never ``"73% spend"``). Human-readable
strings live in the render layer and the envelope's unhashed human fields.

Field shape (matches the receipt specimen exactly)::

    session, model, cost_usd, dominant,
    cost_basis = "public per-token rates", estimate = true,
    models[]   = {name, role, cost_usd, cost_pct},
    tokens     = {total, in, out, cache_read, cache_write, working},
    calls, stages, turns, errors, active_min,
    context    = {window, peak_ctx, events[]={min,cmd,to}, note},
    tools[]    = {name, tok, calls, err, class}     # sparse: low-use tools omit tok/err/class

Token identities (verified against the specimen)::

    tokens.working     = in + out                       (= SessionTotals.total_tokens)
    tokens.cache_write = total_cache_create
    tokens.cache_read  = total_cache_read
    tokens.total       = in + out + cache_read + cache_write
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from .context import build_context_summary
from .cost import calculate_turn_cost
from .models import ToolOutcome

if TYPE_CHECKING:
    from .models import SessionTelemetry, ToolCall

# Self-disclosure constants — the payload carries these so it is honest about
# being an estimate even when read in isolation from the footer disclaimer.
COST_BASIS = "public per-token rates"

# Roles attributed in cost-by-model. The session's main model is "main thread";
# every other model is subagent work (singular or "N subagents").
_ROLE_MAIN = "main thread"
_ROLE_SUBAGENT = "subagent"


def _model_label(raw: str | None) -> str:
    """Normalize a model id to the receipt's short display label.

    Mirrors the resolver's ``_format_model_label``: ``claude-opus-4-7`` →
    ``opus-4.7``, ``gpt-5.4`` → ``gpt-5.4``. Strips the ``claude-`` vendor
    prefix and rewrites the trailing ``major-minor`` to ``major.minor`` so the
    payload's ``name`` fields read the way the specimen's do (``opus-4.7``).
    Unknown shapes pass through unchanged.
    """
    if not raw:
        return ""
    label = raw
    if label.startswith("claude-"):
        label = label[len("claude-") :]
    parts = label.split("-")
    # Drop a trailing YYYYMMDD snapshot date (e.g. "haiku-4-5-20251001" →
    # "haiku-4-5") so a dated subagent id reads like the undated main-thread ones.
    if len(parts) >= 3 and len(parts[-1]) == 8 and parts[-1].isdigit():
        parts = parts[:-1]
    # family-major-minor (e.g. "opus-4-7") → "opus-4.7"; tolerate a -1m suffix.
    if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
        head = "-".join(parts[:-2])
        return f"{head}-{parts[-2]}.{parts[-1]}"
    return "-".join(parts)


def _call_cost(call: ToolCall) -> float:
    """Public-rate cost of a single tool call's API turn, in dollars."""
    usage: dict[str, object] = {
        "input_tokens": call.tokens_input,
        "output_tokens": call.tokens_output,
        "cache_creation_input_tokens": call.cache_create_tokens,
        "cache_read_input_tokens": call.cache_read_tokens,
    }
    # Forward the TTL split so 1h cache writes bill at 2x (5m stays 1.25x).
    # Without it cost.py's flat fallback prices everything at the 5m rate.
    if call.cache_create_1h_tokens:
        usage["cache_creation"] = {
            "ephemeral_5m_input_tokens": max(call.cache_create_tokens - call.cache_create_1h_tokens, 0),
            "ephemeral_1h_input_tokens": call.cache_create_1h_tokens,
        }
    return calculate_turn_cost(usage, call.model or "")


def _active_minutes(t: SessionTelemetry) -> int:
    """Active work duration in minutes (rounded).

    Promotes the receipt resolver's ``_active_window_minutes`` logic onto the
    parsed telemetry directly. The primary source is the per-turn compute sum
    (``turn_duration_minutes``); the fallback is ``min(stage-span sum,
    wall-clock span)``. The wall-clock span caps every source so the curve's
    time axis can never exceed the session's real length.
    """
    stages = t.stages
    fallback = float(t.duration_minutes)
    turn_m = t.turn_duration_minutes

    if not stages:
        if turn_m is not None and turn_m > 0:
            return max(round(turn_m), 1)
        return max(round(fallback), 0)

    starts = [s.start_time for s in stages]
    ends = [s.end_time for s in stages]
    wall_clock_m = (max(ends) - min(starts)).total_seconds() / 60.0

    if turn_m is not None and turn_m > 0:
        return max(round(min(turn_m, wall_clock_m)), 1)

    sum_m = sum((s.end_time - s.start_time).total_seconds() / 60.0 for s in stages)
    return max(round(min(sum_m, wall_clock_m)), 1)


def _build_models(t: SessionTelemetry, total_cost: float) -> tuple[list[dict[str, object]], str]:
    """Group tool calls by model → cost-by-model entries + dominant model.

    Each entry is ``{name, role, cost_usd, cost_pct}``. ``role`` is assigned by
    ORIGIN, not dominance: a model that ran on the main thread (any tool call
    with ``is_subagent=False``) is ``"main thread"`` — so a session that switched
    models mid-thread reads both as "main thread" rather than mislabelling the
    non-dominant one a subagent. A model seen ONLY in folded subagent sidechains
    is ``"subagent"`` (or ``"N subagents"`` when N spans ran it). ``dominant`` is
    the costliest model.

    Returns ``(models, dominant_label)``. Empty when there are no costed calls.
    """
    # Sum cost per raw model id (first-seen order) and record which models the
    # MAIN thread ran — the reconstruction tags subagent calls ``is_subagent``.
    cost_by_model: OrderedDict[str, float] = OrderedDict()
    main_models: set[str] = set()
    for call in t.tool_calls:
        mid = call.model or t.model or ""
        cost_by_model[mid] = cost_by_model.get(mid, 0.0) + _call_cost(call)
        if not call.is_subagent:
            main_models.add(mid)

    if not cost_by_model:
        return [], _model_label(t.model)

    # Subagent spans per model → the "N subagents" count for a subagent-only model.
    spans_by_model: dict[str, int] = {}
    for a in t.agents:
        spans_by_model[a.model or ""] = spans_by_model.get(a.model or "", 0) + 1

    models: list[dict[str, object]] = []
    for mid, cost in sorted(cost_by_model.items(), key=lambda kv: kv[1], reverse=True):
        if mid in main_models:
            role = _ROLE_MAIN
        else:
            n = spans_by_model.get(mid, 0)
            role = f"{n} subagents" if n > 1 else _ROLE_SUBAGENT
        pct = round((cost / total_cost) * 100) if total_cost > 0 else 0
        models.append(
            {
                "name": _model_label(mid),
                "role": role,
                "cost_usd": round(cost, 2),
                "cost_pct": pct,
            }
        )

    dominant = str(models[0]["name"])
    return models, dominant


def _build_tools(t: SessionTelemetry) -> list[dict[str, object]]:
    """Reshape the tool summary into the sparse ``tools[]`` array.

    Order is by working-token spend descending, then call count, so the
    heaviest tools lead (the resolver's top-N bar chart consumes this order).
    Each entry is sparse per the specimen convention: ``tok`` is emitted only
    when > 0, ``err`` only when > 0, ``class`` only when the tool was
    classified. A pure-tail tool carries just ``name`` + ``calls``.
    """
    # Per-tool MAIN-THREAD error count — the single error definition the whole
    # receipt uses (ERROR outcomes only; BLOCKED is a denial, not a failure; a
    # subagent erroring in its own context is off this main-thread timeline). These
    # badges SUM to the header `errors` and the count of curve ticks — the three
    # error surfaces count the identical set, so the numbers always reconcile.
    err_by_tool: dict[str, int] = {}
    for c in t.tool_calls:
        if c.outcome is ToolOutcome.ERROR and not c.is_subagent:
            err_by_tool[c.tool_name] = err_by_tool.get(c.tool_name, 0) + 1

    summaries = sorted(
        t.tool_summary.values(),
        key=lambda s: (s.total_tokens, s.call_count),
        reverse=True,
    )
    tools: list[dict[str, object]] = []
    for s in summaries:
        entry: dict[str, object] = {"name": s.tool_name}
        tok = s.total_tokens
        if tok > 0:
            entry["tok"] = tok
        entry["calls"] = s.call_count
        err = err_by_tool.get(s.tool_name, 0)
        if err > 0:
            entry["err"] = err
        if tok > 0:
            # class travels with token-bearing tools (the bar rows); tail tools
            # that only register call counts omit it, matching the specimen.
            entry["class"] = s.tool_class.value
        tools.append(entry)
    return tools


def build_receipt_payload(t: SessionTelemetry) -> dict[str, object]:
    """Assemble the canonical ``receipt/1`` payload dict from session telemetry.

    Compact, data-only, raw values. See module docstring for the field shape
    and token identities. This is the single source of receipt data — embedded
    as ``hw:payload`` and consumed by the resolver.
    """
    o = t.totals
    total_input = o.total_input_tokens
    total_output = o.total_output_tokens
    cache_read = o.total_cache_read
    cache_write = o.total_cache_create
    working = total_input + total_output
    total_tokens = total_input + total_output + cache_read + cache_write

    total_cost = sum(_call_cost(c) for c in t.tool_calls)
    models, dominant = _build_models(t, total_cost)

    return {
        "session": t.session_id,
        "model": _model_label(t.model),
        "cost_usd": round(total_cost, 2),
        "dominant": dominant,
        "cost_basis": COST_BASIS,
        "estimate": True,
        "models": models,
        "tokens": {
            "total": total_tokens,
            "in": total_input,
            "out": total_output,
            "cache_read": cache_read,
            "cache_write": cache_write,
            "working": working,
        },
        "calls": o.total_calls,
        "stages": len(t.stages),
        "turns": o.total_user_messages,
        # Genuine MAIN-THREAD failures only: ERROR outcomes (BLOCKED is a
        # permission/hook denial — the system working as intended — not a
        # failure) on the main thread (a subagent erroring in its own context is
        # not an event on this curve's main-thread timeline).
        "errors": sum(1 for c in t.tool_calls if c.outcome is ToolOutcome.ERROR and not c.is_subagent),
        "active_min": _active_minutes(t),
        "context": build_context_summary(t),
        "tools": _build_tools(t),
    }
