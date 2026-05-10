"""Thin orchestration: parse -> stages -> corrections -> cost -> dict.

v0.2.23 adds ``parse_transcript_auto`` — a runtime-dispatching parser
that sniffs the first non-empty JSONL line, matches it against the
registered runtime detection rules (``telemetry.runtimes``), and
dynamically imports the matching parser module. ``build_contract`` is
now runtime-agnostic; the runtime identity travels on
``SessionTelemetry.runtime`` and is stamped into the assembled dict
for the resolver's skin + identity precedence chain.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hyperweave.telemetry.corrections import classify_user_events
from hyperweave.telemetry.cost import calculate_turn_cost
from hyperweave.telemetry.models import ToolOutcome
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
    return telemetry


def build_contract(transcript_path: str) -> dict[str, Any]:
    """Parse transcript (auto-routed to the matching runtime) and assemble data contract."""
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
            "model": t.model or "",
            "git_branch": t.git_branch or "",
            "project_path": t.project_path or "",
            # Load-bearing for v0.2.21+ skin auto-detection: the receipt
            # resolver's _resolve_telemetry_genome() reads this field to
            # select the matching telemetry-{runtime} genome JSON. As of
            # v0.2.23 it's stamped by the parser, not a contract constant.
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
