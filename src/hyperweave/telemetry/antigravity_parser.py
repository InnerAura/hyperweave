"""JSONL Transcript Parser for Antigravity sessions.

Exposes the public ``parse_transcript`` contract so ``contract.parse_transcript_auto``
can dispatch dynamically through ``data/telemetry/runtimes/antigravity.yaml``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
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
from .runtimes import classify_tool, get_runtime

logger = logging.getLogger(__name__)

_JsonObj = dict[str, Any]
_REGISTRY = get_runtime("antigravity")


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


def _detect_agent_spans(tool_calls: list[ToolCall]) -> list[AgentSpan]:
    """Detect sub-agent spans from invoke_subagent tool calls."""
    agents: dict[str, AgentSpan] = {}
    for tc in tool_calls:
        if tc.tool_name == "invoke_subagent":
            # Generate a 12-char agent ID for visualization
            agent_id = tc.tool_id[:12] if tc.tool_id else "subagent"
            agents[agent_id] = AgentSpan(
                agent_id=agent_id,
                agent_type="general-purpose",
                start_time=tc.timestamp,
            )
    return list(agents.values())


# --------------------------------------------------------------------------- #
# MAIN PARSER
# --------------------------------------------------------------------------- #


def parse_transcript(transcript_path: str | Path) -> SessionTelemetry:
    """Parse an Antigravity JSONL transcript into SessionTelemetry.

    Mirrors ``parser.parse_transcript`` (Claude Code) and ``codex_parser.parse_transcript``
    so ``contract.parse_transcript_auto`` can swap them dynamically.
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
                logger.warning("antigravity_parser: skipping malformed line %d in %s", line_num, path)

    step_map = {step["step_index"]: step for step in raw_lines if "step_index" in step}

    # -- Sniff session metadata --
    session_id = "antigravity-session"
    if len(path.parts) >= 4:
        candidate = path.parts[-4]
        if len(candidate) == 36 or "-" in candidate:
            session_id = candidate

    session_name = "Antigravity Session"
    project_path = ""
    git_branch = "main"
    model = "Gemini 3.5 Flash"

    # Try to find project path from tool calls' Cwd
    for step in raw_lines:
        if step.get("type") == "PLANNER_RESPONSE":
            tcalls = step.get("tool_calls", [])
            for tc in tcalls:
                cwd = tc.get("args", {}).get("Cwd")
                if cwd:
                    project_path = str(cwd)
                    break
            if project_path:
                break

    # -- Tool call and token usage extraction --
    all_tool_calls: list[ToolCall] = []
    user_messages_count = 0
    assistant_messages_count = 0
    total_input_tokens = 0
    total_output_tokens = 0
    user_texts: list[tuple[datetime, str]] = []

    for step in raw_lines:
        stype = step.get("type")
        ts = _parse_timestamp(step.get("created_at"))

        if stype == "USER_INPUT":
            user_messages_count += 1
            content = step.get("content", "")
            if isinstance(content, str) and content.strip():
                # Estimate prompt tokens (4 chars ≈ 1 token, plus system overhead)
                total_input_tokens += len(content) // 4 + 1000
                user_texts.append((ts, content.strip()))

        elif stype == "PLANNER_RESPONSE":
            assistant_messages_count += 1
            thinking = step.get("thinking", "")
            tool_calls_raw = step.get("tool_calls", [])

            # Estimate response tokens
            content = thinking + str(tool_calls_raw)
            total_output_tokens += len(content) // 4 + 200

            step_idx = step.get("step_index", 0)

            for i, tc in enumerate(tool_calls_raw):
                name = tc.get("name", "Unknown")
                clean_name = name.split(":")[-1] if ":" in name else name
                tool_id = f"tc-{step_idx}-{i}"

                # Sniff outcome from subsequent execution step in the JSONL
                outcome = ToolOutcome.SUCCESS
                expected_type = clean_name.upper()
                for next_idx in range(step_idx + 1, len(raw_lines) + 1):
                    next_step = step_map.get(next_idx)
                    if not next_step:
                        continue
                    if next_step.get("type") == expected_type or (
                        clean_name == "list_permissions" and next_step.get("type") == "GENERIC"
                    ):
                        step_content = next_step.get("content", "")
                        status = next_step.get("status", "")
                        if "Encountered error" in step_content or status == "ERROR":
                            outcome = ToolOutcome.ERROR
                        elif any(
                            kw in step_content.lower()
                            for kw in ["blocked", "permission denied", "not allowed", "sandbox"]
                        ):
                            outcome = ToolOutcome.BLOCKED
                        break

                args = tc.get("args") or {}
                file_path = (
                    args.get("AbsolutePath")
                    or args.get("TargetFile")
                    or args.get("DirectoryPath")
                    or args.get("SearchPath")
                )
                command = args.get("CommandLine")

                all_tool_calls.append(
                    ToolCall(
                        tool_name=clean_name,
                        tool_id=tool_id,
                        tool_input_keys=sorted(args.keys()) if isinstance(args, dict) else [],
                        tool_class=_classify(clean_name),
                        timestamp=ts,
                        tokens_input=0,  # distributed later
                        tokens_output=0,  # distributed later
                        cache_read_tokens=0,
                        cache_create_tokens=0,
                        outcome=outcome,
                        parent_uuid=None,
                        model=model,
                        file_path=str(file_path) if file_path else None,
                        command=str(command) if command else None,
                    )
                )

    # Distribute total token counts across tool calls proportionally
    n_calls = len(all_tool_calls)
    if n_calls:
        per_input = total_input_tokens // n_calls
        per_output = total_output_tokens // n_calls
        for tc in all_tool_calls:
            tc.tokens_input = per_input
            tc.tokens_output = per_output

    # -- Timestamps and duration --
    timestamps = [_parse_timestamp(line.get("created_at")) for line in raw_lines if line.get("created_at")]
    session_start = min(timestamps) if timestamps else datetime.now()
    session_end = max(timestamps) if timestamps else session_start
    duration_minutes = max((session_end - session_start).total_seconds() / 60, 0.0)

    # -- Unique files accessed --
    files_accessed: list[str] = []
    seen_files: set[str] = set()
    for tc in all_tool_calls:
        if tc.file_path and tc.file_path not in seen_files:
            files_accessed.append(tc.file_path)
            seen_files.add(tc.file_path)

    # -- Tool summary aggregation --
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
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_cache_read=0,
        total_cache_create=0,
        total_user_messages=user_messages_count,
        total_assistant_messages=assistant_messages_count,
    )

    user_events = [
        UserEvent(
            category=UserEventCategory.CONTINUATION,
            message_preview=text[:80],
            timestamp=ts,
            confidence=ConfidenceLevel.LOW,
        )
        for ts, text in user_texts
    ]

    agents = _detect_agent_spans(all_tool_calls)

    return SessionTelemetry(
        session_id=session_id,
        session_name=session_name,
        project_path=project_path,
        git_branch=git_branch,
        model=model,
        runtime=_REGISTRY.runtime,
        timestamp=session_start,
        duration_minutes=round(duration_minutes, 2),
        turn_duration_minutes=None,
        tool_calls=all_tool_calls,
        stages=[],  # populated by stages.detect_stages
        agents=agents,
        user_events=user_events,
        tool_summary=tool_summary,
        totals=totals,
        files_accessed=files_accessed,
    )
