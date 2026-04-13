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
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    TOOL_CLASS_MAP,  # yaml config
    AgentSpan,
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

logger = logging.getLogger(__name__)

# Type alias for parsed JSONL objects
_JsonObj = dict[str, Any]


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
    """Map tool name -> functional class."""
    return TOOL_CLASS_MAP.get(name, ToolClass.EXPLORE)  # yaml config


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
    """Extract plain text from a user message, ignoring tool_results and meta."""
    if obj.get("isMeta"):
        return None

    msg = obj.get("message", {})
    if not isinstance(msg, dict):
        return None

    content = msg.get("content", "")

    if isinstance(content, str):
        text = content.strip()
        if text.startswith("<") and ("command-name" in text or "system-reminder" in text):
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


def _detect_agent_spans(tool_calls: list[ToolCall], raw_lines: list[_JsonObj]) -> list[AgentSpan]:
    """Detect sub-agent spans from Task tool calls and progress messages."""
    agents: dict[str, AgentSpan] = {}

    for tc in tool_calls:
        if tc.tool_name == "Task":
            agent_id = tc.tool_id[:12]
            agents[agent_id] = AgentSpan(
                agent_id=agent_id,
                agent_type="general-purpose",
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

    if total_duration_ms > 0:
        duration_minutes = total_duration_ms / 60_000
    else:
        duration_minutes = (session_end - session_start).total_seconds() / 60

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
    total_user_msgs = sum(1 for ln in raw_lines if _is_user_entry(ln))
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
        project_path=project_path,
        git_branch=git_branch,
        model=model,
        timestamp=session_start,
        duration_minutes=round(duration_minutes, 2),
        tool_calls=all_tool_calls,
        stages=[],
        agents=agents,
        user_events=user_events,
        tool_summary=tool_summary,
        totals=totals,
        files_accessed=files_accessed,
    )
