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
distributes the session total evenly across tool calls so the tool-spend
bars remain proportional to call frequency.
"""

from __future__ import annotations

import json
import logging
import re
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any

from .context import DEFAULT_CONTEXT_WINDOW
from .models import (
    CommandEvent,
    CommandResetKind,
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


# ── Codex shell exit-code classification (the shell-outcome table) ───────────
# Codex encodes shell success/failure as "Process exited with code N" in the
# output preamble, not the word "error". Outcome is a command-aware table, not a
# `!= 0` test: exit-1 from a predicate tool (grep/rg/test/diff) means "no match" —
# a normal SUCCESS — while the same code from anything else is a real ERROR.
# Every runtime parser must have a STRUCTURED outcome path, never a substring guess.
_EXIT_RE = re.compile(r"Process exited with code (\d+)")
_RUNNING_RE = re.compile(r"Process running with session ID")
_PREDICATE_TOOLS = frozenset({"grep", "rg", "test", "diff", "cmp", "["})
_INTERRUPTED_CODES = frozenset({130, 137, 143})  # SIGINT / SIGKILL / SIGTERM
_CRASH_CODES = frozenset({134, 139})  # SIGABRT / SIGSEGV — crashes, not interrupts


def _leading_program(command: str) -> str:
    """The effective leading program: unwrap ``bash -lc "…"``, strip ``cd … &&``
    and ``VAR=val`` env prefixes, descend the first pipeline stage, drop any path."""
    try:
        toks = shlex.split(command)
    except ValueError:
        toks = command.split()
    if not toks:
        return ""
    if toks[0] in ("bash", "sh", "zsh") and len(toks) >= 3 and toks[1] in ("-c", "-lc", "-lic", "-ic"):
        return _leading_program(toks[2])
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == "cd" and i + 1 < len(toks):  # cd DIR && …
            i += 2
            if i < len(toks) and toks[i] in ("&&", ";", "||"):
                i += 1
            continue
        if t in ("env", "exec", "command", "sudo", "time"):
            i += 1
            continue
        if "=" in t and not t.startswith(("-", "/")) and t.split("=", 1)[0].replace("_", "").isalnum():
            i += 1  # VAR=val env prefix
            continue
        break
    return toks[i].rsplit("/", 1)[-1] if i < len(toks) else ""


def _classify_exit(code: int, command: str | None) -> ToolOutcome:
    """Map a shell exit code (+ its command) to an outcome — the shell-outcome table."""
    if code == 0:
        return ToolOutcome.SUCCESS
    if code in _INTERRUPTED_CODES:
        return ToolOutcome.INTERRUPTED
    if code in _CRASH_CODES:
        return ToolOutcome.ERROR
    if code == 1 and command and _leading_program(command) in _PREDICATE_TOOLS:
        return ToolOutcome.SUCCESS  # predicate "no match / false" — a normal result
    return ToolOutcome.ERROR


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
# CONTEXT-WINDOW OCCUPANCY (Codex)
# --------------------------------------------------------------------------- #


def _model_context_events(
    raw_lines: list[_JsonObj],
) -> tuple[int, int, list[CommandEvent]]:
    """Model Codex context occupancy from ``token_count`` events.

    Each ``event_msg/token_count`` event carries ``info.last_token_usage``
    (the *current-turn* context fed to the model — gross, cached portion
    included) and ``info.model_context_window``. We read ``last_token_usage``,
    NOT ``total_token_usage``: the latter is the session's CUMULATIVE token count
    (monotonic, reaching tens of millions), which would peg every curve to the
    window ceiling and — never collapsing — defeat reset detection. The per-turn
    series is a real occupancy trace (it rises, e.g. 18K→245K, and can drop on a
    reset).

    Codex has no explicit ``/compact`` marker in-band and ``/clear`` forks a
    new session file, so resets are detected behaviorally: a sharp collapse
    (>45%) from a near-ceiling peak (>80% of window) reads as auto-compaction.
    Returns ``(window, peak, events)``; window is 0 when no token_count event
    carried a window (the caller falls back to the default).
    """
    series: list[tuple[datetime, int]] = []
    window = 0
    for line in raw_lines:
        if line.get("type") != "event_msg":
            continue
        payload = line.get("payload") or {}
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        if not isinstance(info, dict):
            continue
        win = info.get("model_context_window")
        if isinstance(win, int) and win > 0:
            window = win
        usage = info.get("last_token_usage")
        if not isinstance(usage, dict):
            continue
        occ = int(usage.get("input_tokens", 0) or 0)
        if occ <= 0:
            continue
        ts = _parse_timestamp(line.get("timestamp"))
        series.append((ts, occ))

    peak = max((occ for _ts, occ in series), default=0)
    events: list[CommandEvent] = []
    ceiling = 0.80 * window if window > 0 else float("inf")
    for i in range(1, len(series)):
        _prev_ts, prev_occ = series[i - 1]
        cur_ts, cur_occ = series[i]
        if prev_occ >= ceiling and cur_occ < 0.55 * prev_occ:
            events.append(
                CommandEvent(
                    kind=CommandResetKind.AUTO,
                    timestamp=cur_ts,
                    occupancy_before=prev_occ,
                    occupancy_after=cur_occ,
                )
            )
    return window, peak, events


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
    git_branch: str | None = None
    session_name = ""
    model: str | None = None
    for line in raw_lines:
        ltype = line.get("type")
        payload = line.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if ltype == "session_meta":
            session_id = session_id or str(payload.get("id", ""))
            project_path = project_path or str(payload.get("cwd", ""))
            git_data = payload.get("git") or {}
            if isinstance(git_data, dict):
                branch = git_data.get("branch")
                if isinstance(branch, str) and branch:
                    git_branch = branch
        elif ltype == "turn_context":
            # turn_context refines model + cwd over time; the latest wins.
            cwd = payload.get("cwd")
            if cwd:
                project_path = str(cwd)
            mdl = payload.get("model")
            if mdl:
                model = str(mdl)
        elif ltype == "event_msg" and payload.get("type") == "thread_name_updated":
            # Codex's equivalent of Claude Code's customTitle — driven by
            # task-naming flow. Latest-wins so renames mid-session are honored.
            tname = payload.get("thread_name")
            if isinstance(tname, str) and tname:
                session_name = tname

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

    # ── Pass 3: shell outcomes from function_call_output exit codes ──
    # Codex shells report "Process exited with code N" in the output preamble (not
    # the word "error"). apply_patch / web_search are NOT touched here — their
    # status field already classified them at build time. Classification joins the
    # exit code (here) with the command (Pass 1) by call_id, since the command and
    # the exit code never co-occur in one payload.
    exit_code_map: dict[str, int] = {}
    backgrounded: set[str] = set()
    for line in raw_lines:
        if line.get("type") != "response_item":
            continue
        payload = line.get("payload") or {}
        if not isinstance(payload, dict) or payload.get("type") != "function_call_output":
            continue
        call_id = str(payload.get("call_id", ""))
        if not call_id:
            continue
        output = payload.get("output", "")
        text = output if isinstance(output, str) else str(output)
        match = _EXIT_RE.search(text)
        if match is not None:
            exit_code_map[call_id] = int(match.group(1))
        elif _RUNNING_RE.search(text):
            backgrounded.add(call_id)

    by_id = {tc.tool_id: tc for tc in all_tool_calls if tc.tool_id}
    for call_id, code in exit_code_map.items():
        tc = by_id.get(call_id)
        if tc is not None:
            tc.outcome = _classify_exit(code, tc.command)
    for call_id in backgrounded - set(exit_code_map):
        tc = by_id.get(call_id)
        if tc is not None:
            tc.outcome = ToolOutcome.NO_VERDICT

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
    # Codex doesn't attach per-call usage). The tool-spend bars stay proportional
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
    # Codex emits no per-turn duration events analogous to Claude Code's
    # `system.turn_duration`, so `turn_duration_minutes` stays None and the
    # receipt's active-duration line falls back to min(stage-span sum,
    # wall-clock span). Wall-clock is the only signal available here.
    timestamps = [_parse_timestamp(line.get("timestamp")) for line in raw_lines if line.get("timestamp")]
    session_start = min(timestamps) if timestamps else datetime.now()
    session_end = max(timestamps) if timestamps else session_start
    duration_minutes = max((session_end - session_start).total_seconds() / 60, 0.0)

    # ── Context-window occupancy from token_count events ──
    # Codex reports a real window + occupancy series, so the receipt's burn
    # curve is data-backed here, not a flagged gap. Fall back to the default
    # window only when no token_count event carried one.
    ctx_window, peak_context_tokens, command_events = _model_context_events(raw_lines)
    context_window = ctx_window or DEFAULT_CONTEXT_WINDOW

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
        session_name=session_name,
        project_path=project_path,
        git_branch=git_branch,
        model=model,
        runtime=_REGISTRY.runtime,
        timestamp=session_start,
        duration_minutes=round(duration_minutes, 2),
        turn_duration_minutes=None,  # Codex has no per-turn duration events
        context_window=context_window,
        peak_context_tokens=peak_context_tokens,
        tool_calls=all_tool_calls,
        stages=[],  # populated by stages.detect_stages
        agents=[],  # Codex has no Task-style subagent dispatch
        user_events=user_events,
        command_events=command_events,
        tool_summary=tool_summary,
        totals=totals,
        files_accessed=files_accessed,
    )
