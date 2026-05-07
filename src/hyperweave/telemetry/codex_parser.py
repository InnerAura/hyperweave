"""JSONL Transcript Parser for Codex CLI sessions.

Parallel to ``parser.py`` (Claude Code) but built around the Codex
``{timestamp, type, payload}`` envelope rather than Claude Code's flat
``{sessionId, type, message}`` shape. Both parsers expose the same
public ``parse_transcript`` contract so ``contract.parse_transcript_auto``
can dispatch dynamically through ``data/telemetry/runtimes/*.yaml``.

Codex emits THREE distinct tool-call shapes (vs Claude's one
``tool_use`` block):

* ``response_item/function_call`` — has ``name`` field. Used for
  ``exec_command``, ``shell_command``, ``write_stdin``, ``view_image``,
  ``request_user_input``, ``update_plan``.
* ``response_item/custom_tool_call`` — also has ``name`` field. Used
  for ``apply_patch`` (patch text in the ``input`` field).
* ``response_item/web_search_call`` — NO ``name`` field. Has
  ``action.type ∈ {open_page, find_in_page, search}`` and an optional
  ``query`` / ``url`` / ``pattern``. The parser synthesizes the name
  ``"web_search"`` so the runtime registry resolves it to ``explore``.

Token attribution differs from Claude as well: Codex emits cumulative
``event_msg/token_count`` events at intervals (with nullable ``info``
in early events). Per-call attribution is not available; the parser
distributes the session total evenly across tool calls so the treemap
remains proportional to call frequency.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    ConfidenceLevel,
    SessionTelemetry,
    SessionTotals,
    ToolCall,
    ToolClass,
    ToolOutcome,
    ToolSummary,
    UserEvent,
    UserEventCategory,
)
from .runtimes import classify_tool, get_runtime

logger = logging.getLogger(__name__)

_JsonObj = dict[str, Any]
_REGISTRY = get_runtime("codex")
_WEB_SEARCH_TOOL_NAME = "web_search"  # synthesized — web_search_call payloads have no `name`


# --------------------------------------------------------------------------- #
# HELPERS
# --------------------------------------------------------------------------- #


def _parse_timestamp(ts: str | None) -> datetime:
    """Parse ISO-8601 timestamp, falling back to epoch on failure."""
    if not ts:
        return datetime.fromtimestamp(0)
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return datetime.fromtimestamp(0)


def _classify(name: str) -> ToolClass:
    return classify_tool(_REGISTRY, name)


def _safe_json_loads(s: str) -> _JsonObj:
    """Parse a JSON-encoded string defensively. Codex stores function_call.arguments
    as a JSON string; malformed entries fall back to an empty dict rather than crash.
    """
    try:
        result = json.loads(s)
    except (TypeError, json.JSONDecodeError):
        return {}
    return result if isinstance(result, dict) else {}


def _extract_command(args: _JsonObj) -> str | None:
    """Pull a representative command string from function_call arguments.

    Codex shells use ``cmd`` (newer) or ``command`` (older). For other
    function_call types the field is absent; returning None is correct.
    """
    cmd = args.get("cmd") or args.get("command")
    if isinstance(cmd, str):
        return cmd
    if isinstance(cmd, list):
        # exec_command sometimes sends an argv array
        return " ".join(str(x) for x in cmd)
    return None


def _extract_apply_patch_path(patch_input: str) -> str | None:
    """Best-effort: pull the first file path out of an apply_patch payload.

    The patch format leads each hunk with a header like
    ``*** Update File: path/to/file.py`` or ``*** Add File: ...``.
    Falls back to None when the payload isn't recognizable — the
    receipt's file-path heatmap silently skips entries with no path.
    """
    if not isinstance(patch_input, str):
        return None
    for line in patch_input.splitlines():
        stripped = line.strip()
        for marker in ("*** Update File:", "*** Add File:", "*** Delete File:"):
            if stripped.startswith(marker):
                return stripped[len(marker) :].strip() or None
    return None


# --------------------------------------------------------------------------- #
# PASS 1: TOOL CALL EXTRACTION (3 shapes)
# --------------------------------------------------------------------------- #


def _build_tool_call_from_function_call(payload: _JsonObj, ts: datetime, model: str | None) -> ToolCall | None:
    """``response_item/function_call`` → ToolCall.

    Has ``name`` (e.g. ``exec_command``), ``arguments`` (JSON-string),
    and ``call_id``. We extract a representative ``command`` for the
    codebase heatmap when present.
    """
    name = payload.get("name", "")
    if not name:
        return None
    call_id = str(payload.get("call_id", ""))
    args_raw = payload.get("arguments", "")
    args = _safe_json_loads(args_raw) if isinstance(args_raw, str) else {}
    return ToolCall(
        tool_name=name,
        tool_id=call_id,
        tool_input_keys=sorted(args.keys()),
        tool_class=_classify(name),
        timestamp=ts,
        outcome=ToolOutcome.SUCCESS,
        model=model,
        command=_extract_command(args),
        file_path=None,
    )


def _build_tool_call_from_custom_tool_call(payload: _JsonObj, ts: datetime, model: str | None) -> ToolCall | None:
    """``response_item/custom_tool_call`` → ToolCall.

    apply_patch is the canonical example: ``input`` is the patch text.
    The first ``*** Update File:`` line is captured as the heatmap path.
    """
    name = payload.get("name", "")
    if not name:
        return None
    call_id = str(payload.get("call_id", ""))
    raw_input = payload.get("input", "")
    file_path = _extract_apply_patch_path(raw_input) if name == "apply_patch" else None
    # Custom tools don't expose structured args; use a synthetic single key
    # so the input-keys list isn't empty.
    return ToolCall(
        tool_name=name,
        tool_id=call_id,
        tool_input_keys=["input"] if raw_input else [],
        tool_class=_classify(name),
        timestamp=ts,
        outcome=ToolOutcome.SUCCESS if payload.get("status") in ("completed", "success", "") else ToolOutcome.ERROR,
        model=model,
        command=None,
        file_path=file_path,
    )


def _build_tool_call_from_web_search(payload: _JsonObj, ts: datetime, model: str | None) -> ToolCall:
    """``response_item/web_search_call`` → ToolCall.

    web_search_call has no ``name`` field; we synthesize ``"web_search"``
    so the runtime registry resolves it. ``action`` carries the payload
    detail (open_page, find_in_page, search) which we expose as input keys.
    """
    action = payload.get("action") or {}
    if not isinstance(action, dict):
        action = {}
    return ToolCall(
        tool_name=_WEB_SEARCH_TOOL_NAME,
        tool_id=str(payload.get("call_id", payload.get("id", ""))),
        tool_input_keys=sorted(k for k in action if k != "type"),
        tool_class=_classify(_WEB_SEARCH_TOOL_NAME),
        timestamp=ts,
        outcome=ToolOutcome.SUCCESS if payload.get("status") in ("completed", "success", "") else ToolOutcome.ERROR,
        model=model,
        command=None,
        file_path=None,
    )


# --------------------------------------------------------------------------- #
# MAIN PARSER
# --------------------------------------------------------------------------- #


def parse_transcript(transcript_path: str | Path) -> SessionTelemetry:
    """Parse a Codex JSONL transcript into SessionTelemetry.

    Mirrors ``parser.parse_transcript`` (Claude Code) so
    ``contract.parse_transcript_auto`` can swap them dynamically. Stages
    are left empty — populated by ``stages.detect_stages`` downstream.
    """
    path = Path(transcript_path)
    if not path.exists():
        raise FileNotFoundError(f"Transcript not found: {path}")

    raw_lines: list[_JsonObj] = []
    with open(path) as f:
        for line_num, raw_line in enumerate(f):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                raw_lines.append(json.loads(stripped))
            except json.JSONDecodeError:
                logger.warning("codex_parser: skipping malformed line %d in %s", line_num, path)

    # ── Pass 1: session_meta + turn_context derive session metadata ──
    session_id = ""
    project_path = ""
    model: str | None = None
    for line in raw_lines:
        ltype = line.get("type")
        payload = line.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if ltype == "session_meta":
            session_id = session_id or str(payload.get("id", ""))
            project_path = project_path or str(payload.get("cwd", ""))
        elif ltype == "turn_context":
            # turn_context refines model + cwd over time; the latest wins.
            cwd = payload.get("cwd")
            if cwd:
                project_path = str(cwd)
            mdl = payload.get("model")
            if mdl:
                model = str(mdl)

    # ── Pass 2: tool calls from response_item (3 shapes) ──
    all_tool_calls: list[ToolCall] = []
    for line in raw_lines:
        if line.get("type") != "response_item":
            continue
        payload = line.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        ts = _parse_timestamp(line.get("timestamp"))
        ptype = payload.get("type")
        tc: ToolCall | None
        if ptype == "function_call":
            tc = _build_tool_call_from_function_call(payload, ts, model)
        elif ptype == "custom_tool_call":
            tc = _build_tool_call_from_custom_tool_call(payload, ts, model)
        elif ptype == "web_search_call":
            tc = _build_tool_call_from_web_search(payload, ts, model)
        else:
            tc = None
        if tc is not None:
            all_tool_calls.append(tc)

    # ── Pass 3: outcomes from *_output payloads (matched by call_id) ──
    outcome_map: dict[str, ToolOutcome] = {}
    for line in raw_lines:
        if line.get("type") != "response_item":
            continue
        payload = line.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if payload.get("type") not in ("function_call_output", "custom_tool_call_output"):
            continue
        call_id = str(payload.get("call_id", ""))
        if not call_id:
            continue
        output = payload.get("output", "")
        # Codex output is plain text; check for error markers.
        # We treat any output text as success unless it explicitly mentions
        # an error envelope. The runtime's own ``status`` field on the call
        # payload already classified completion/error in pass 2; this pass
        # only flips outcomes when the output text disagrees.
        if isinstance(output, str) and ("error:" in output.lower()[:80] or '"error"' in output[:200]):
            outcome_map[call_id] = ToolOutcome.ERROR
        else:
            outcome_map.setdefault(call_id, ToolOutcome.SUCCESS)

    for tc in all_tool_calls:
        if tc.tool_id and tc.tool_id in outcome_map:
            tc.outcome = outcome_map[tc.tool_id]

    # ── Pass 4: token totals from event_msg/token_count (last non-null wins) ──
    last_total_usage: _JsonObj | None = None
    for line in raw_lines:
        if line.get("type") != "event_msg":
            continue
        payload = line.get("payload") or {}
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        if not isinstance(info, dict):
            continue  # early events emit info: null; skip
        usage = info.get("total_token_usage")
        if isinstance(usage, dict):
            last_total_usage = usage

    # Codex's ``total_token_usage`` has a different shape than Claude's. ``input_tokens``
    # is the GROSS input count; ``cached_input_tokens`` is the SUBSET that hit cache
    # (a discount, not a separate category). The receipt resolver sums the four token
    # fields (input + output + cache_read + cache_create) assuming Claude's NON-overlapping
    # shape. To keep that summation correct, subtract the cached portion from input so
    # the four are disjoint and ``total_tok`` matches Codex's reported total_tokens.
    raw_total_input = int((last_total_usage or {}).get("input_tokens", 0) or 0)
    total_cached = int((last_total_usage or {}).get("cached_input_tokens", 0) or 0)
    total_input = max(raw_total_input - total_cached, 0)  # fresh-input portion only
    total_output = int((last_total_usage or {}).get("output_tokens", 0) or 0)
    # Codex doesn't expose a "cache create" notion (cache writes are implicit). Map
    # cached_input_tokens onto Claude's cache_read slot, leave cache_create at zero.
    total_cache_create = 0

    # Distribute session totals evenly across tool calls (best-effort —
    # Codex doesn't attach per-call usage). The treemap stays proportional
    # to call frequency, which is the most honest summary at this resolution.
    n_calls = len(all_tool_calls)
    if n_calls:
        per_input = total_input // n_calls
        per_output = total_output // n_calls
        per_cached = total_cached // n_calls
        for tc in all_tool_calls:
            tc.tokens_input = per_input
            tc.tokens_output = per_output
            tc.cache_read_tokens = per_cached
            tc.cache_create_tokens = 0

    # ── Pass 5: user_message + agent_message events ──
    user_texts: list[tuple[datetime, str]] = []
    n_assistant_msgs = 0
    for line in raw_lines:
        if line.get("type") != "event_msg":
            continue
        payload = line.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        ptype = payload.get("type")
        ts = _parse_timestamp(line.get("timestamp"))
        if ptype == "user_message":
            text = payload.get("message") or payload.get("text") or ""
            if isinstance(text, str) and text.strip():
                user_texts.append((ts, text.strip()))
        elif ptype == "agent_message":
            n_assistant_msgs += 1

    # ── Compute timestamps + duration ──
    timestamps = [_parse_timestamp(line.get("timestamp")) for line in raw_lines if line.get("timestamp")]
    session_start = min(timestamps) if timestamps else datetime.now()
    session_end = max(timestamps) if timestamps else session_start
    duration_minutes = max((session_end - session_start).total_seconds() / 60, 0.0)

    # ── files_accessed: ordered unique file paths from apply_patch ──
    files_accessed: list[str] = []
    seen_files: set[str] = set()
    for tc in all_tool_calls:
        if tc.file_path and tc.file_path not in seen_files:
            files_accessed.append(tc.file_path)
            seen_files.add(tc.file_path)

    # ── tool_summary aggregation ──
    tool_summary: dict[str, ToolSummary] = {}
    for tc in all_tool_calls:
        s = tool_summary.setdefault(tc.tool_name, ToolSummary(tool_name=tc.tool_name, tool_class=tc.tool_class))
        s.call_count += 1
        s.total_input_tokens += tc.tokens_input
        s.total_output_tokens += tc.tokens_output
        s.total_cache_read += tc.cache_read_tokens
        s.total_cache_create += tc.cache_create_tokens
        if tc.outcome == ToolOutcome.SUCCESS:
            s.success_count += 1
        elif tc.outcome == ToolOutcome.BLOCKED:
            s.blocked_count += 1
        elif tc.outcome == ToolOutcome.ERROR:
            s.error_count += 1

    totals = SessionTotals(
        total_calls=n_calls,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cache_read=total_cached,
        total_cache_create=total_cache_create,
        total_user_messages=len(user_texts),
        total_assistant_messages=n_assistant_msgs,
    )

    user_events: list[UserEvent] = [
        UserEvent(
            category=UserEventCategory.CONTINUATION,
            message_preview=text[:80],
            timestamp=ts,
            confidence=ConfidenceLevel.LOW,
        )
        for ts, text in user_texts
    ]

    return SessionTelemetry(
        session_id=session_id,
        project_path=project_path,
        git_branch=None,  # Codex doesn't surface git_branch in transcripts
        model=model,
        runtime=_REGISTRY.runtime,
        timestamp=session_start,
        duration_minutes=round(duration_minutes, 2),
        tool_calls=all_tool_calls,
        stages=[],  # populated by stages.detect_stages
        agents=[],  # Codex has no Task-style subagent dispatch
        user_events=user_events,
        tool_summary=tool_summary,
        totals=totals,
        files_accessed=files_accessed,
    )
