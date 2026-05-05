"""Thin orchestration: parse -> stages -> corrections -> cost -> dict."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hyperweave.telemetry.corrections import classify_user_events
from hyperweave.telemetry.cost import calculate_turn_cost
from hyperweave.telemetry.models import ToolOutcome
from hyperweave.telemetry.parser import parse_transcript
from hyperweave.telemetry.stages import detect_stages

if TYPE_CHECKING:
    from hyperweave.telemetry.models import SessionTelemetry

# Identifier for the runtime that produced this transcript. The Claude Code
# parser is the only path through this module; v0.2.22 adds a parallel
# codex_parser.py that emits "codex" instead, and a `parse_transcript_auto`
# dispatcher will sniff JSONL schema markers to route between them. The
# receipt's skin precedence chain reads this field to auto-select the
# matching genome (telemetry-claude-code vs telemetry-codex etc).
_RUNTIME = "claude-code"


def build_contract(transcript_path: str) -> dict[str, Any]:
    """Parse transcript and assemble data contract for ComposeSpec."""
    t = parse_transcript(transcript_path)
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


def _assemble(t: SessionTelemetry, cost: float) -> dict[str, Any]:
    end = t.stages[-1].end_time.isoformat() if t.stages else t.timestamp.isoformat()
    o = t.totals
    return {
        "session": {
            "id": t.session_id,
            "start": t.timestamp.isoformat(),
            "end": end,
            "duration_minutes": t.duration_minutes,
            "model": t.model or "",
            "git_branch": t.git_branch or "",
            "project_path": t.project_path or "",
            # Load-bearing for v0.2.21+ skin auto-detection: the receipt
            # resolver's _resolve_telemetry_genome() reads this field to
            # select the matching telemetry-{runtime} genome JSON.
            "runtime": _RUNTIME,
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
            if e.category.value != "continuation"
        ],
        "agents": [
            {"id": a.agent_id, "type": a.agent_type, "tool_calls": a.tool_calls, "tokens": a.total_tokens}
            for a in t.agents
        ],
    }
