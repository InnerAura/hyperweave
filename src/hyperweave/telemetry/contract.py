"""Thin orchestration: parse -> stages -> corrections -> cost -> dict.

v0.2.23 adds ``parse_transcript_auto`` — a runtime-dispatching parser
that sniffs the first non-empty JSONL line, matches it against the
registered runtime detection rules (``telemetry.runtimes``), and
dynamically imports the matching parser module. ``build_contract`` is
now runtime-agnostic; the runtime identity travels on
``SessionTelemetry.runtime`` and is stamped into the assembled dict
for the receipt resolver's identity (glyph + wordmark) lookup.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hyperweave.telemetry.corrections import classify_user_events
from hyperweave.telemetry.cost import calculate_turn_cost
from hyperweave.telemetry.models import AgentSpan, SessionTotals, ToolOutcome, ToolSummary
from hyperweave.telemetry.receipt_payload import build_receipt_payload
from hyperweave.telemetry.runtimes import RuntimeRegistry, load_all_runtimes
from hyperweave.telemetry.stages import detect_stages

if TYPE_CHECKING:
    from hyperweave.telemetry.models import SessionTelemetry


def _find_matching_runtime(path: str | Path) -> RuntimeRegistry:
    """Walk the JSONL until a line matches some registry's detection rule.

    Real transcripts often open with metadata lines (Claude Code's
    leafUUID/summary pair, file-history-snapshot, permission-mode events)
    that lack runtime-identifying keys. This iterates past those and
    returns the first registry whose detection rule matches some line —
    making detection tolerant to header noise without requiring every
    metadata-line variant to be enumerated in YAML ``type_values``.

    Raises ``ValueError`` if no line in the file matches any registry.
    """
    registries = load_all_runtimes()
    p = Path(path)
    with p.open() as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            for reg in registries.values():
                if reg.detection.matches(parsed):
                    return reg
    msg = f"No registered runtime detection rule matched any line in: {path}"
    raise ValueError(msg)


def parse_transcript_auto(transcript_path: str) -> SessionTelemetry:
    """Detect the runtime by scanning the JSONL, then dispatch to its parser.

    The detection rule set is mutually exclusive across registered
    runtimes (enforced by ``tests/test_runtime_registries.py``), so a
    Claude Code transcript never sniffs as Codex and vice versa. The
    matched registry's ``parser_module`` is imported dynamically and
    its ``parse_transcript`` function is invoked. The returned
    SessionTelemetry already carries ``runtime`` stamped by its parser;
    we re-stamp defensively in case of parser-side bugs.
    """
    registry = _find_matching_runtime(transcript_path)
    parser_mod = importlib.import_module(registry.parser_module)
    parse_fn = parser_mod.parse_transcript  # contract every runtime parser exposes
    telemetry: SessionTelemetry = parse_fn(transcript_path)
    if not telemetry.runtime:
        telemetry.runtime = registry.runtime
    # Claude Code sessions are physically a main file + N subagent sidechains;
    # fold the children's cost/tokens/tools/models into the parent. Codex
    # sessions are self-contained, so this is a no-op for them.
    if telemetry.runtime == "claude-code":
        _stitch_subagent_sidechains(telemetry, Path(transcript_path))
    return telemetry


def _fold_totals(dst: SessionTotals, src: SessionTotals) -> None:
    """Add a subagent's token + call totals into the parent's.

    Turn counts (user/assistant messages) are deliberately NOT folded — a
    subagent invocation is not a user turn; the receipt's ``turns`` counts
    main-thread prompts only.
    """
    dst.total_calls += src.total_calls
    dst.total_input_tokens += src.total_input_tokens
    dst.total_output_tokens += src.total_output_tokens
    dst.total_cache_read += src.total_cache_read
    dst.total_cache_create += src.total_cache_create


def _merge_tool_summary(dst: dict[str, ToolSummary], src: dict[str, ToolSummary]) -> None:
    """Merge a subagent's per-tool summary into the parent's (additive)."""
    for name, s in src.items():
        d = dst.get(name)
        if d is None:
            d = ToolSummary(tool_name=name, tool_class=s.tool_class)
            dst[name] = d
        d.call_count += s.call_count
        d.total_input_tokens += s.total_input_tokens
        d.total_output_tokens += s.total_output_tokens
        d.total_cache_read += s.total_cache_read
        d.total_cache_create += s.total_cache_create
        d.success_count += s.success_count
        d.blocked_count += s.blocked_count
        d.error_count += s.error_count


def _stitch_subagent_sidechains(t: SessionTelemetry, main_path: Path) -> None:
    """Fold a Claude Code session's subagent sidechains into the main telemetry.

    A logical Claude Code session is physically a main transcript PLUS N subagent
    sidechains at ``<main-stem>/subagents/agent-*.jsonl`` (``isSidechain=True``,
    ``sessionId`` == the parent's). The subagent's token cost lives ONLY in the
    child files — the main's ``tool_result`` carries the subagent's text output,
    not its usage — so a main-only parse undercounts and never sees the subagent
    model. Each child is parsed and its tool calls (tagged ``is_subagent`` so
    cost-by-model roles read by origin), token totals, tool summary, and a span
    are folded into the parent.

    The context-occupancy curve is deliberately NOT folded: subagents run in
    their own context windows, so ``peak_ctx`` / ``window`` / reset ``events``
    (and ``turns`` / ``stages`` / ``active_min``) stay main-thread.
    """
    if main_path.name.startswith("agent-"):
        return  # a sidechain handed in directly is not a parent session
    subdir = main_path.with_suffix("")  # <projdir>/<session-uuid>/
    if not subdir.is_dir():
        return
    children = sorted(subdir.rglob("agent-*.jsonl"))
    if not children:
        return

    from hyperweave.telemetry.parser import parse_transcript as parse_claude

    spans: list[AgentSpan] = []
    for child in children:
        try:
            sub = parse_claude(child)
        except (OSError, ValueError):
            continue
        for call in sub.tool_calls:
            call.is_subagent = True
        t.tool_calls.extend(sub.tool_calls)
        _fold_totals(t.totals, sub.totals)
        _merge_tool_summary(t.tool_summary, sub.tool_summary)
        st = sub.totals
        spans.append(
            AgentSpan(
                agent_id=child.stem[:16],
                agent_type="general-purpose",
                model=sub.model,
                tool_calls=len(sub.tool_calls),
                total_tokens=(
                    st.total_input_tokens + st.total_output_tokens + st.total_cache_read + st.total_cache_create
                ),
                start_time=sub.timestamp,
            )
        )
    if spans:
        t.agents = spans


def build_contract(transcript_path: str) -> dict[str, Any]:
    """Parse transcript (auto-routed to the matching runtime) and assemble data contract.

    Emits the legacy nested ``{session, profile, tools, stages, ...}`` shape
    consumed by the current ``resolve_receipt`` and the proofset script. For
    the ``receipt/1`` payload that the v3 receipt embeds and renders, use
    :func:`build_receipt_contract`.
    """
    t = parse_transcript_auto(transcript_path)
    t.stages = detect_stages(t.tool_calls)
    t.user_events = classify_user_events(t.user_events, t.tool_calls)
    cost = sum(
        calculate_turn_cost(
            {
                "input_tokens": c.tokens_input,
                "output_tokens": c.tokens_output,
                "cache_creation_input_tokens": c.cache_create_tokens,
                "cache_read_input_tokens": c.cache_read_tokens,
            },
            c.model or "",
        )
        for c in t.tool_calls
    )
    return _assemble(t, cost)


def build_receipt_contract(transcript_path: str) -> dict[str, Any]:
    """Parse a transcript and assemble the canonical ``receipt/1`` payload.

    Same parse + stage-detection + correction pipeline as
    :func:`build_contract`, but emits the compact, data-only ``receipt/1``
    dict (see :mod:`hyperweave.telemetry.receipt_payload`). This is the single
    source of receipt data: it is embedded verbatim as the artifact's
    ``hw:payload`` and consumed by the receipt resolver. ``ComposeSpec``
    carries it opaquely on ``telemetry_data``, so the compact field names
    (``tok``/``calls``/``err``/``class``, ``tokens.working``, ``context.events``)
    flow through ``/v1/compose`` and MCP unchanged.
    """
    t = parse_transcript_auto(transcript_path)
    t.stages = detect_stages(t.tool_calls)
    t.user_events = classify_user_events(t.user_events, t.tool_calls)
    return build_receipt_payload(t)


def _assemble(t: SessionTelemetry, cost: float) -> dict[str, Any]:
    end = t.stages[-1].end_time.isoformat() if t.stages else t.timestamp.isoformat()
    o = t.totals
    return {
        "session": {
            "id": t.session_id,
            "name": t.session_name,
            "start": t.timestamp.isoformat(),
            "end": end,
            "duration_minutes": t.duration_minutes,
            # Per-turn compute sum when the runtime emits it (Claude Code's
            # `system.turn_duration` events). None for Codex and any runtime
            # without per-turn duration signal; the resolver falls back to
            # min(stage-span sum, wall-clock) in that case.
            "turn_duration_minutes": t.turn_duration_minutes,
            "model": t.model or "",
            "git_branch": t.git_branch or "",
            "project_path": t.project_path or "",
            # Identity selector: the receipt resolver maps this runtime to the
            # glyph + wordmark (claude-code → Claude Code, codex → Codex). It
            # selects identity only, never a theme — receipts render on primer.
            # Stamped by the parser, not a contract constant.
            "runtime": t.runtime,
        },
        "profile": {
            "total_input_tokens": o.total_input_tokens,
            "total_output_tokens": o.total_output_tokens,
            "total_cache_creation_tokens": o.total_cache_create,
            "total_cache_read_tokens": o.total_cache_read,
            "total_cost": round(cost, 6),
            "turns": o.total_user_messages + o.total_assistant_messages,
            "model": t.model or "",
        },
        "tools": {
            n: {
                "count": s.call_count,
                "total_tokens": s.total_tokens,
                "tool_class": s.tool_class.value,
                "success": s.success_count,
                "blocked": s.blocked_count,
                "errors": s.error_count,
            }
            for n, s in t.tool_summary.items()
        },
        "files_accessed": t.files_accessed,
        "stages": [
            {
                "label": s.label.value,
                "dominant_class": s.dominant_tool_class.value,
                "start": s.start_time.isoformat(),
                "end": s.end_time.isoformat(),
                "tools": s.call_count,
                # Per-stage token totals enable variable-height rhythm bars
                # in compose/bar_chart.py. Sum mirrors the receipt-level
                # `total_tok = input + output + cache_read + cache_create`.
                "tokens": sum(
                    tc.tokens_input + tc.tokens_output + tc.cache_read_tokens + tc.cache_create_tokens
                    for tc in s.tool_calls
                ),
                # Per-stage failure count for rhythm error-tick markers.
                # Includes BLOCKED + ERROR to match the receipt's tier-cell
                # "✗N" convention (treats both as one "failure" signal).
                "errors": sum(1 for tc in s.tool_calls if tc.outcome in (ToolOutcome.ERROR, ToolOutcome.BLOCKED)),
                "boundary_score": s.boundary_score,
            }
            for s in t.stages
        ],
        "user_events": [
            {"category": e.category.value, "preview": e.message_preview, "confidence": e.confidence.value}
            for e in t.user_events
        ],
        "agents": [
            {"id": a.agent_id, "type": a.agent_type, "tool_calls": a.tool_calls, "tokens": a.total_tokens}
            for a in t.agents
        ],
    }
