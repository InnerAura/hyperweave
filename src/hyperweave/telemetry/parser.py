"""JSONL Transcript Parser for Claude Code sessions.

Five-pass architecture ported from aura-research, with hyperweave's
file path extraction added for codebase heatmap support.

Pass 1: Extract tool calls from assistant messages (with per-call token division)
Pass 2: Update outcomes from tool_result blocks in user messages
Pass 3: Extract user text for event classification
Pass 4: Detect agent spans from Task tools + progress messages
Pass 5: Extract turn durations from system.turn_duration
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .context import window_for_model
from .models import (
    AgentSpan,
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

# Type alias for parsed JSONL objects
_JsonObj = dict[str, Any]

# Resolved at import time — fail loud if claude-code.yaml is missing.
_REGISTRY = get_runtime("claude-code")

# Match content that consists entirely of one or more XML envelopes
# emitted by the Claude Code harness (e.g. <command-name>...</command-name>,
# <local-command-stdout>...</local-command-stdout>, <system-reminder>...</...>).
# These are non-prose framing — never count them as user turns.
_ENVELOPE_ONLY = re.compile(
    r"^<[a-z][a-z0-9-]*>.*</[a-z][a-z0-9-]*>$",
    re.DOTALL,
)

# Slash-command envelopes that reset the context window. Captured by a
# dedicated pass (`_extract_command_resets`) because `_extract_user_text`
# discards command envelopes — they must not count as turns, but they ARE
# context-load reset events the receipt's burn curve renders.
_COMMAND_NAME = re.compile(r"<command-name>\s*/?([a-z][a-z0-9_-]*)\s*</command-name>")
_RESET_COMMANDS: dict[str, CommandResetKind] = {
    "compact": CommandResetKind.COMPACT,
    "clear": CommandResetKind.CLEAR,
}


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


def _classify_tool(name: str) -> ToolClass:
    """Map tool name -> functional class via the claude-code runtime registry."""
    return classify_tool(_REGISTRY, name)


def _is_user_entry(obj: _JsonObj) -> bool:
    """Check if a JSONL entry is a user message (handles 'user' and 'human' types)."""
    return obj.get("type") in ("user", "human")


# --------------------------------------------------------------------------- #
# PASS 1: TOOL CALL EXTRACTION
# --------------------------------------------------------------------------- #


def _extract_tool_calls_from_assistant(obj: _JsonObj) -> list[ToolCall]:
    """Extract ToolCall records from an assistant message.

    Includes hyperweave file_path/command extraction for codebase heatmap.
    """
    msg = obj.get("message", {})
    if not isinstance(msg, dict):
        return []

    content = msg.get("content", [])
    if not isinstance(content, list):
        return []

    usage = msg.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}

    timestamp = _parse_timestamp(obj.get("timestamp"))
    model = msg.get("model")
    parent_uuid = obj.get("parentUuid") or obj.get("parentUUID")

    input_tokens = usage.get("input_tokens", 0) or 0
    output_tokens = usage.get("output_tokens", 0) or 0
    cache_read = usage.get("cache_read_input_tokens", 0) or 0
    cache_create = usage.get("cache_creation_input_tokens", 0) or 0
    # TTL split: usage.cache_creation breaks the flat total into 5m/1h buckets
    # (current Claude Code writes 1h exclusively). The 1h subset rides along so
    # cost attribution can bill it at 2x; absent on older transcripts → 0.
    cache_detail = usage.get("cache_creation")
    cache_create_1h = 0
    if isinstance(cache_detail, dict):
        cache_create_1h = int(cache_detail.get("ephemeral_1h_input_tokens", 0) or 0)

    # Count tool_use blocks for per-call token division
    tool_use_count = sum(1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use")
    divisor = max(tool_use_count, 1)

    tool_calls: list[ToolCall] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue

        name = block.get("name", "Unknown")
        tool_id = block.get("id", "")
        tool_input = block.get("input", {})
        input_keys = list(tool_input.keys()) if isinstance(tool_input, dict) else []

        # Hyperweave: extract actual values for codebase heatmap
        file_path = None
        command = None
        if isinstance(tool_input, dict):
            file_path = tool_input.get("file_path")
            command = tool_input.get("command")

        tc = ToolCall(
            tool_name=name,
            tool_id=tool_id,
            tool_input_keys=input_keys,
            tool_class=_classify_tool(name),
            timestamp=timestamp,
            tokens_input=input_tokens // divisor,
            tokens_output=output_tokens // divisor,
            cache_read_tokens=cache_read // divisor,
            cache_create_tokens=cache_create // divisor,
            cache_create_1h_tokens=cache_create_1h // divisor,
            outcome=ToolOutcome.SUCCESS,
            parent_uuid=parent_uuid,
            model=model,
            file_path=file_path,
            command=command,
        )
        tool_calls.append(tc)

    return tool_calls


# --------------------------------------------------------------------------- #
# PASS 2: TOOL OUTCOMES
# --------------------------------------------------------------------------- #


def _extract_tool_outcomes(obj: _JsonObj) -> dict[str, ToolOutcome]:
    """Extract outcomes from tool_result blocks in user messages."""
    msg = obj.get("message", {})
    if not isinstance(msg, dict):
        return {}

    content = msg.get("content", [])
    if not isinstance(content, list):
        return {}

    outcomes: dict[str, ToolOutcome] = {}
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue

        tool_use_id = block.get("tool_use_id", "")
        is_error = block.get("is_error", False)

        result_content = block.get("content", "")
        is_blocked = False
        if isinstance(result_content, str):
            is_blocked = any(
                kw in result_content.lower() for kw in ["blocked", "permission denied", "not allowed", "sandbox"]
            )

        if is_error:
            outcomes[tool_use_id] = ToolOutcome.ERROR
        elif is_blocked:
            outcomes[tool_use_id] = ToolOutcome.BLOCKED
        else:
            outcomes[tool_use_id] = ToolOutcome.SUCCESS

    return outcomes


# --------------------------------------------------------------------------- #
# PASS 3: USER TEXT EXTRACTION
# --------------------------------------------------------------------------- #


def _extract_user_text(obj: _JsonObj) -> str | None:
    """Extract plain text from a user message, ignoring tool_results and meta.

    Compact-summary messages (``isCompactSummary: true``) are machine-injected
    conversation summaries the harness writes after auto- or ``/compact``-
    compaction. Their content is prose (not an envelope), so without this
    guard they read as a human turn and inflate the turn count. They are
    excluded here so every turn tally derived from this function counts only
    human-authored prose; the reset itself is still captured separately by
    ``_extract_command_resets`` for the context-load curve.
    """
    if obj.get("isMeta") or obj.get("isCompactSummary"):
        return None

    msg = obj.get("message", {})
    if not isinstance(msg, dict):
        return None

    content = msg.get("content", "")

    if isinstance(content, str):
        text = content.strip()
        if _ENVELOPE_ONLY.match(text):
            return None
        return text if text else None

    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif isinstance(block, str):
                texts.append(block)
        combined = " ".join(texts).strip()
        if combined and not combined.startswith("<"):
            return combined

    return None


# --------------------------------------------------------------------------- #
# PASS 4: AGENT SPAN DETECTION
# --------------------------------------------------------------------------- #


# Subagent-dispatch tool names across Claude Code versions: current harnesses
# emit "Agent"; older transcripts emit "Task". (TaskCreate/TaskUpdate/etc. are
# the task-tracking tools, not dispatch — they never open a span.)
_DISPATCH_TOOLS = frozenset({"Agent", "Task"})


def _detect_agent_spans(tool_calls: list[ToolCall], raw_lines: list[_JsonObj]) -> list[AgentSpan]:
    """Detect sub-agent spans from Agent/Task dispatch calls and progress messages.

    The declared ``subagent_type`` is read from the raw tool_use block (the
    ToolCall record keeps input keys only, not values). Progress-message
    counting survives for older transcripts; current Claude Code no longer
    emits ``progress`` lines, so ``span.tool_calls`` stays 0 here and the
    sidechain reconstruction in ``contract.py`` supplies the real counts.
    """
    # tool_use id → declared subagent_type, from the raw assistant blocks.
    declared_types: dict[str, str] = {}
    for line in raw_lines:
        if line.get("type") != "assistant":
            continue
        msg = line.get("message", {})
        content = msg.get("content", []) if isinstance(msg, dict) else []
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") not in _DISPATCH_TOOLS:
                continue
            block_input = block.get("input", {})
            subagent_type = block_input.get("subagent_type") if isinstance(block_input, dict) else None
            if isinstance(subagent_type, str) and subagent_type:
                declared_types[str(block.get("id", ""))] = subagent_type

    agents: dict[str, AgentSpan] = {}
    for tc in tool_calls:
        if tc.tool_name in _DISPATCH_TOOLS:
            agent_id = tc.tool_id[:12]
            agents[agent_id] = AgentSpan(
                agent_id=agent_id,
                agent_type=declared_types.get(tc.tool_id, "general-purpose"),
                start_time=tc.timestamp,
            )

    progress_counts: dict[str, int] = {}
    for line in raw_lines:
        if line.get("type") == "progress":
            parent_id = line.get("parentToolUseID", "")
            if parent_id:
                short_id = parent_id[:12]
                progress_counts[short_id] = progress_counts.get(short_id, 0) + 1

    for agent_id, span in agents.items():
        span.tool_calls = progress_counts.get(agent_id, 0)

    return list(agents.values())


# --------------------------------------------------------------------------- #
# PASS 5: CONTEXT-WINDOW OCCUPANCY + RESET DETECTION
# --------------------------------------------------------------------------- #


def _assistant_occupancy(obj: _JsonObj) -> int:
    """Modelled context occupancy at an assistant turn, in tokens.

    Occupancy is the context *fed* to the model on this turn:
    ``input_tokens + cache_read_input_tokens + cache_creation_input_tokens``.
    Output tokens are excluded — they are produced, not loaded. This reads
    the *undivided* per-turn usage (not the per-call-divided ToolCall
    tokens), which is why it operates on the raw assistant line.
    """
    msg = obj.get("message", {})
    if not isinstance(msg, dict):
        return 0
    usage = msg.get("usage", {})
    if not isinstance(usage, dict):
        return 0
    return (
        int(usage.get("input_tokens", 0) or 0)
        + int(usage.get("cache_read_input_tokens", 0) or 0)
        + int(usage.get("cache_creation_input_tokens", 0) or 0)
    )


# A genuine session reads a few percent above its nominal window on the turn
# that triggers compaction (cache + token-accounting overhead), so only a peak
# that exceeds the window by MORE than this tolerance indicates the session
# actually ran on a larger window (a 200K-default model on the 1M beta). A
# few-K ceiling overshoot is NOT a promotion — a genuine 200K session stays 200K.
_WINDOW_PROMOTE_TOLERANCE = 1.25


def _model_window(model: str | None, observed_peak: int) -> int:
    """Resolve the context window, promoting only on a CLEAR overshoot.

    ``window_for_model`` gives the doc-sourced baseline (Opus 4.x / Fable 5 /
    Sonnet 4.6 = 1M; Haiku 4.5 / Sonnet 4.5 = 200K). The backstop recovers an
    opt-in larger window (the Sonnet-4.5 1M beta) from observed occupancy — but
    only when the peak exceeds the baseline by more than
    :data:`_WINDOW_PROMOTE_TOLERANCE`, so a genuine 200K session sitting at its
    ceiling (~200-215K) is NOT promoted to 1M (which would draw it ~20% full).
    The receipt never overshoots its own ceiling.
    """
    window = window_for_model(model)
    if observed_peak > window * _WINDOW_PROMOTE_TOLERANCE:
        return 1_000_000 if observed_peak <= 1_000_000 else observed_peak
    return window


def _detect_context_events(
    raw_lines: list[_JsonObj],
    window: int,
) -> tuple[list[CommandEvent], int]:
    """Model context occupancy over the session and detect reset events.

    Walks the transcript in order, tracking the running occupancy from each
    assistant turn. Resets are detected from three disjoint structural
    signals, in priority order so a single physical reset is counted once:

    * ``/compact`` or ``/clear`` slash-command envelope (explicit, user-driven).
    * ``isCompactSummary`` user message → AUTO-compaction by default. A manual
      ``/compact`` emits both a command envelope and a summary, so the fold step
      downgrades the summary to COMPACT when a command sits adjacent; a lone
      summary (no nearby command) is a genuine auto-compaction.
    * A sharp occupancy collapse near the window ceiling with no marker
      (auto-compaction inferred behaviorally; only fires above 80% of the
      window so ordinary cache turnover never trips it).

    A reset within two assistant turns of an already-recorded reset is
    folded into it (the explicit envelope and its summary are one event),
    so the three signals never double-count. ``occupancy_after`` is read
    from the first assistant turn following the reset; ``occupancy_before``
    from the last one preceding it.

    Returns ``(events, peak_occupancy)``.
    """
    # Build an ordered occupancy timeline of assistant turns: (line_index, ts, occ).
    timeline: list[tuple[int, datetime, int]] = []
    peak = 0
    for idx, line in enumerate(raw_lines):
        if line.get("type") != "assistant":
            continue
        occ = _assistant_occupancy(line)
        if occ <= 0:
            continue
        ts = _parse_timestamp(line.get("timestamp"))
        timeline.append((idx, ts, occ))
        peak = max(peak, occ)

    # Map a line index → position in the assistant timeline for fast lookup
    # of the surrounding occupancy at any reset.
    def _occ_around(line_idx: int) -> tuple[int, int]:
        before = 0
        after = 0
        for t_idx, _ts, occ in timeline:
            if t_idx < line_idx:
                before = occ
            elif t_idx >= line_idx and after == 0:
                after = occ
                break
        return before, after

    raw_events: list[tuple[int, datetime, CommandResetKind]] = []

    # Signal 1+2: explicit command envelopes and compact-summary markers.
    for idx, line in enumerate(raw_lines):
        if not _is_user_entry(line):
            continue
        if line.get("isCompactSummary"):
            # AUTO-compaction by default. The fold step below downgrades this to
            # COMPACT only when an explicit /compact command envelope sits
            # adjacent (a manual /compact emits both a command and a summary).
            ts = _parse_timestamp(line.get("timestamp"))
            raw_events.append((idx, ts, CommandResetKind.AUTO))
            continue
        msg = line.get("message", {})
        content = msg.get("content", "") if isinstance(msg, dict) else ""
        if not isinstance(content, str):
            continue
        m = _COMMAND_NAME.search(content)
        if m and (kind := _RESET_COMMANDS.get(m.group(1).lower())):
            ts = _parse_timestamp(line.get("timestamp"))
            raw_events.append((idx, ts, kind))

    # Signal 3: behavioral auto-compaction — a >45% occupancy collapse from a
    # near-ceiling peak with no structural marker nearby. Only meaningful when
    # the window is known; guards against ordinary cache eviction.
    ceiling = 0.80 * window if window > 0 else float("inf")
    marker_indices = {idx for idx, _ts, _k in raw_events}
    for i in range(1, len(timeline)):
        prev_idx, _pts, prev_occ = timeline[i - 1]
        cur_idx, cur_ts, cur_occ = timeline[i]
        if prev_occ >= ceiling and cur_occ < 0.55 * prev_occ:
            # Skip if a structural marker already sits between the two turns.
            if any(prev_idx <= mi <= cur_idx for mi in marker_indices):
                continue
            raw_events.append((cur_idx, cur_ts, CommandResetKind.AUTO))

    # Order by line index, then fold near-duplicate resets (explicit envelope
    # + its summary land within a couple of assistant turns of each other).
    raw_events.sort(key=lambda e: e[0])
    folded: list[tuple[int, datetime, CommandResetKind]] = []

    def _nearest_pos(line_idx: int) -> int:
        # Position in the assistant timeline at/after this line index.
        for pos, (t_idx, _ts, _occ) in enumerate(timeline):
            if t_idx >= line_idx:
                return pos
        return len(timeline)

    for idx, ts, kind in raw_events:
        if folded:
            last_idx, _lts, last_kind = folded[-1]
            if abs(_nearest_pos(idx) - _nearest_pos(last_idx)) <= 2:
                # Same physical reset: an explicit command kind (COMPACT/CLEAR)
                # wins over the AUTO summary inference — a manual /compact emits
                # both a command envelope and a summary, so the pair folds to
                # the manual kind; a lone summary stays AUTO (auto-compaction).
                if last_kind is CommandResetKind.AUTO and kind is not CommandResetKind.AUTO:
                    folded[-1] = (last_idx, _lts, kind)
                continue
        folded.append((idx, ts, kind))

    # Event minutes are derived downstream (context.build_context_summary)
    # from the timestamp so callers control rounding; we keep the timestamp
    # authoritative here rather than baking a minute value into the model.
    events: list[CommandEvent] = []
    for idx, ts, kind in folded:
        before, after = _occ_around(idx)
        events.append(
            CommandEvent(
                kind=kind,
                timestamp=ts,
                occupancy_before=before,
                occupancy_after=after,
            )
        )

    return events, peak


# --------------------------------------------------------------------------- #
# MAIN PARSER
# --------------------------------------------------------------------------- #


def parse_transcript(transcript_path: str | Path) -> SessionTelemetry:
    """Parse a Claude Code JSONL transcript into SessionTelemetry.

    Parameters
    ----------
    transcript_path
        Path to the .jsonl file.

    Returns
    -------
    SessionTelemetry
        Fully parsed session data with tool calls, user events, agent
        spans, tool summaries, file paths, and aggregate totals.
        Stages are left empty (populated by stages.detect_stages).
    """
    path = Path(transcript_path)
    if not path.exists():
        raise FileNotFoundError(f"Transcript not found: {path}")

    raw_lines: list[_JsonObj] = []
    with open(path) as f:
        for line_num, raw_line in enumerate(f):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                raw_lines.append(json.loads(raw_line))
            except json.JSONDecodeError:
                logger.warning("Skipping malformed line %d", line_num)

    # -- Extract session metadata --
    # sessionId may appear on a bare `permission-mode` line first; cwd and gitBranch
    # typically appear on a later user-message line. Fill each field from the first
    # line that has it, independently.
    session_id = ""
    project_path = ""
    git_branch: str | None = None
    model = None

    for line in raw_lines:
        if not session_id and line.get("sessionId"):
            session_id = line["sessionId"]
        if not project_path and line.get("cwd"):
            project_path = line["cwd"]
        if git_branch is None and line.get("gitBranch") is not None:
            git_branch = line["gitBranch"]
        if session_id and project_path and git_branch is not None:
            break

    # `custom-title` records carry the user-facing session name (driven by
    # /rename). Current Claude Code also emits `ai-title` records with the
    # auto-generated title — a session never renamed may carry ONLY an
    # ai-title. Both are latest-wins; an explicit rename outranks the
    # auto-title regardless of order.
    session_name = ""
    ai_title = ""
    for line in raw_lines:
        if line.get("type") == "custom-title":
            title = line.get("customTitle")
            if isinstance(title, str) and title:
                session_name = title
        elif line.get("type") == "ai-title":
            title = line.get("aiTitle")
            if isinstance(title, str) and title:
                ai_title = title
    session_name = session_name or ai_title

    # -- Pass 1: Extract all tool calls from assistant messages --
    all_tool_calls: list[ToolCall] = []
    for line in raw_lines:
        if line.get("type") == "assistant":
            calls = _extract_tool_calls_from_assistant(line)
            all_tool_calls.extend(calls)
            if not model:
                msg = line.get("message", {})
                if isinstance(msg, dict) and msg.get("model"):
                    model = msg["model"]

    # -- Pass 2: Update outcomes from tool_result blocks --
    outcome_map: dict[str, ToolOutcome] = {}
    for line in raw_lines:
        if _is_user_entry(line):
            outcomes = _extract_tool_outcomes(line)
            outcome_map.update(outcomes)

    for tc in all_tool_calls:
        if tc.tool_id in outcome_map:
            tc.outcome = outcome_map[tc.tool_id]

    # -- Pass 3: Extract user text for event classification --
    user_texts: list[tuple[datetime, str]] = []
    for line in raw_lines:
        if _is_user_entry(line):
            text = _extract_user_text(line)
            if text:
                ts = _parse_timestamp(line.get("timestamp"))
                user_texts.append((ts, text))

    # -- Pass 4: Detect agent spans --
    agents = _detect_agent_spans(all_tool_calls, raw_lines)

    # -- Pass 5: Extract turn durations --
    total_duration_ms = 0
    for line in raw_lines:
        if line.get("type") == "system" and line.get("subtype") == "turn_duration":
            total_duration_ms += line.get("durationMs", 0)

    # -- Compute timestamps and duration --
    timestamps = [_parse_timestamp(line.get("timestamp")) for line in raw_lines if line.get("timestamp")]
    session_start = min(timestamps) if timestamps else datetime.now()
    session_end = max(timestamps) if timestamps else session_start

    # -- Pass 6: Context-window occupancy + reset events --
    # Peak is observed first (some sessions run on a larger window than the
    # model id implies); the window resolution then defends against an
    # under-mapped id by promoting to the tier the peak demonstrates.
    _peak_probe = max((_assistant_occupancy(ln) for ln in raw_lines if ln.get("type") == "assistant"), default=0)
    context_window = _model_window(model, _peak_probe)
    command_events, peak_context_tokens = _detect_context_events(raw_lines, context_window)

    # turn_duration_minutes is the receipt's primary "active" source when present —
    # it measures per-turn compute time and ignores idle gaps the stage detector
    # silently absorbs into a stage span. None signals the fallback path.
    if total_duration_ms > 0:
        duration_minutes = total_duration_ms / 60_000
        turn_duration_minutes: float | None = duration_minutes
    else:
        duration_minutes = (session_end - session_start).total_seconds() / 60
        turn_duration_minutes = None

    # -- Extract unique file paths (ordered) --
    files_accessed: list[str] = []
    seen_files: set[str] = set()
    for tc in all_tool_calls:
        if tc.file_path and tc.file_path not in seen_files:
            files_accessed.append(tc.file_path)
            seen_files.add(tc.file_path)

    # -- Build tool summary --
    tool_summary: dict[str, ToolSummary] = {}
    for tc in all_tool_calls:
        name = tc.tool_name
        if name not in tool_summary:
            tool_summary[name] = ToolSummary(tool_name=name, tool_class=tc.tool_class)
        s = tool_summary[name]
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

    # -- Build totals --
    # Count only human-authored prose. type:"user" lines also wrap tool_results
    # and command-name/local-command-stdout envelopes; those are not turns.
    total_user_msgs = sum(1 for ln in raw_lines if _is_user_entry(ln) and _extract_user_text(ln) is not None)
    total_assistant_msgs = sum(1 for ln in raw_lines if ln.get("type") == "assistant")

    totals = SessionTotals(
        total_calls=len(all_tool_calls),
        total_input_tokens=sum(tc.tokens_input for tc in all_tool_calls),
        total_output_tokens=sum(tc.tokens_output for tc in all_tool_calls),
        total_cache_read=sum(tc.cache_read_tokens for tc in all_tool_calls),
        total_cache_create=sum(tc.cache_create_tokens for tc in all_tool_calls),
        total_user_messages=total_user_msgs,
        total_assistant_messages=total_assistant_msgs,
    )

    # Build placeholder user events (reclassified by corrections.classify_user_events)
    user_events: list[UserEvent] = []
    for ts, text in user_texts:
        user_events.append(
            UserEvent(
                category=UserEventCategory.CONTINUATION,
                message_preview=text[:80],
                timestamp=ts,
                confidence=ConfidenceLevel.LOW,
            )
        )

    return SessionTelemetry(
        session_id=session_id,
        session_name=session_name,
        project_path=project_path,
        git_branch=git_branch,
        model=model,
        runtime=_REGISTRY.runtime,
        timestamp=session_start,
        duration_minutes=round(duration_minutes, 2),
        turn_duration_minutes=(round(turn_duration_minutes, 2) if turn_duration_minutes is not None else None),
        context_window=context_window,
        peak_context_tokens=peak_context_tokens,
        tool_calls=all_tool_calls,
        stages=[],
        agents=agents,
        user_events=user_events,
        command_events=command_events,
        tool_summary=tool_summary,
        totals=totals,
        files_accessed=files_accessed,
    )
