"""Pydantic models for parsed agent-runtime session telemetry.

These models represent the structured output of parsing a JSONL
transcript -- tool calls, agent spans, detected stages, user events,
and aggregate session metrics. Multi-runtime as of v0.2.23: each
SessionTelemetry instance carries the runtime that produced it
(``claude-code``, ``codex``, ...) so the receipt resolver can resolve
the identity glyph + wordmark without sniffing.

Ported from aura-research/systems/hooks/hw_claude_code_hook/models.py.
``STAGE_LABEL_MAP`` loaded from YAML at import time; tool-class
classification has moved to ``telemetry.runtimes`` (per-runtime
registries) per Phase A of v0.2.23.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 (Pydantic needs at runtime)
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- #
# YAML LOADER
# --------------------------------------------------------------------------- #

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "telemetry"


def _load_yaml(name: str) -> dict[str, str]:
    with (_DATA_DIR / name).open() as f:
        result: dict[str, str] = yaml.safe_load(f)
        return result


# --------------------------------------------------------------------------- #
# ENUMS
# --------------------------------------------------------------------------- #


class ToolOutcome(StrEnum):
    """Outcome of a tool invocation."""

    SUCCESS = "success"
    BLOCKED = "blocked"
    ERROR = "error"
    # Control-signal kills (SIGINT/SIGKILL/SIGTERM) — not failures. Excluded from
    # the receipt's `errors` count; surfaced as a quiet `interrupted` detail.
    INTERRUPTED = "interrupted"
    # Backgrounded process with no terminal verdict yet — neither pass nor fail.
    # Excluded from both error and success totals.
    NO_VERDICT = "no_verdict"


class ToolClass(StrEnum):
    """Functional classification of tools.

    Used by the stage detector to identify dominant behavioral modes
    in sliding windows of tool calls.
    """

    EXPLORE = "explore"
    MUTATE = "mutate"
    EXECUTE = "execute"
    COORDINATE = "coordinate"
    REFLECT = "reflect"


class StageLabel(StrEnum):
    """Human-readable stage labels derived from dominant tool class."""

    RECONNAISSANCE = "reconnaissance"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    ORCHESTRATION = "orchestration"
    DELIBERATION = "deliberation"


class UserEventCategory(StrEnum):
    """Classification of user messages by intent."""

    CORRECTION = "correction"
    REDIRECTION = "redirection"
    ELABORATION = "elaboration"
    CONTINUATION = "continuation"


class ConfidenceLevel(StrEnum):
    """Three-level ordinal confidence. No fake precision."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# --------------------------------------------------------------------------- #
# CONFIG MAPS (loaded from YAML)
# --------------------------------------------------------------------------- #

_raw_stage_labels: dict[str, str] = _load_yaml("stage-labels.yaml")
STAGE_LABEL_MAP: dict[ToolClass, StageLabel] = {  # loaded from yaml config
    ToolClass(cls): StageLabel(label) for cls, label in _raw_stage_labels.items()
}


# --------------------------------------------------------------------------- #
# CORE MODELS
# --------------------------------------------------------------------------- #


class ToolCall(BaseModel):
    """A single tool invocation extracted from an assistant message."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(description="Tool name (Read, Bash, Task, etc.)")
    tool_id: str = Field(description="Unique tool_use ID from the API response")
    tool_input_keys: list[str] = Field(
        default_factory=list,
        description="Keys of the input dict (values omitted for size)",
    )
    tool_class: ToolClass = Field(description="Functional classification of this tool")
    timestamp: datetime = Field(description="When this tool call was made")
    tokens_input: int = Field(default=0, description="Input tokens for this API turn")
    tokens_output: int = Field(default=0, description="Output tokens for this API turn")
    cache_read_tokens: int = Field(default=0, description="Cache read tokens")
    cache_create_tokens: int = Field(default=0, description="Cache creation tokens")
    outcome: ToolOutcome = Field(
        default=ToolOutcome.SUCCESS,
        description="Whether the tool call succeeded, was blocked, or errored",
    )
    parent_uuid: str | None = Field(default=None, description="Parent message UUID for tree reconstruction")
    model: str | None = Field(default=None, description="Model that generated this tool call")
    is_subagent: bool = Field(
        default=False,
        description=(
            "True when this call came from a subagent sidechain folded into the "
            "parent session (Claude Code session reconstruction), not the main "
            "thread. Drives cost-by-model role attribution by origin."
        ),
    )
    # Hyperweave additions for codebase heatmap
    file_path: str | None = Field(default=None, description="Resolved file path from tool input")
    command: str | None = Field(default=None, description="Command string from Bash tool input")


class ToolSummary(BaseModel):
    """Aggregate statistics for a single tool type."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    call_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read: int = 0
    total_cache_create: int = 0
    success_count: int = 0
    blocked_count: int = 0
    error_count: int = 0
    tool_class: ToolClass = ToolClass.EXPLORE

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


class AgentSpan(BaseModel):
    """Telemetry for a sub-agent spawned via the Task tool."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(description="UUID or short identifier")
    agent_type: str = Field(
        default="general-purpose",
        description="Agent type (general-purpose, Explore, Plan, etc.)",
    )
    model: str | None = Field(
        default=None,
        description=(
            "Model the subagent ran on, when distinguishable. Used by the "
            "receipt payload to attribute cost-by-model roles (a model that "
            "is not the session's main-thread model is attributed to "
            "subagents). None when the runtime gives no per-span model signal."
        ),
    )
    tool_calls: int = Field(default=0, description="Number of tool calls within span")
    total_tokens: int = Field(default=0, description="Total tokens consumed")
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def duration_ms(self) -> int:
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds() * 1000)
        return 0


class CommandResetKind(StrEnum):
    """Kind of context-window reset event.

    ``COMPACT`` / ``CLEAR`` are user slash-commands; ``AUTO`` is the
    harness auto-compacting near the window ceiling with no explicit
    command. Maps verbatim to the ``receipt/1`` ``context.events[].cmd``
    field, so the string values are part of the data contract.
    """

    COMPACT = "compact"
    CLEAR = "clear"
    AUTO = "auto"


class CommandEvent(BaseModel):
    """A context-window reset event detected in the transcript.

    Emitted by the parser when it sees a ``/compact`` or ``/clear``
    slash-command envelope, an ``isCompactSummary`` auto-compaction
    marker, or (Codex) a sharp occupancy drop near the ceiling. The
    receipt's context-load curve renders one reset glyph per event;
    ``occupancy_after`` anchors the curve's post-reset descent.
    """

    model_config = ConfigDict(extra="forbid")

    kind: CommandResetKind = Field(description="compact | clear | auto")
    timestamp: datetime = Field(description="When the reset occurred")
    occupancy_before: int = Field(
        default=0,
        description="Modelled context occupancy (tokens) at the turn before the reset",
    )
    occupancy_after: int = Field(
        default=0,
        description=(
            "Modelled context occupancy (tokens) at the first turn after the "
            "reset. The receipt's ``context.events[].to`` value."
        ),
    )


class Stage(BaseModel):
    """A detected behavioral stage in the session."""

    model_config = ConfigDict(extra="forbid")

    label: StageLabel = Field(description="Human-readable stage label")
    dominant_tool_class: ToolClass = Field(description="Most frequent tool class")
    tool_calls: list[ToolCall] = Field(default_factory=list)
    start_time: datetime
    end_time: datetime
    boundary_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the boundary detection (0-1)",
    )

    @property
    def duration_ms(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() * 1000)

    @property
    def call_count(self) -> int:
        return len(self.tool_calls)


class UserEvent(BaseModel):
    """A classified user message event."""

    model_config = ConfigDict(extra="forbid")

    category: UserEventCategory = Field(description="Classified intent")
    message_preview: str = Field(
        max_length=80,
        description="First 80 chars of the user message",
    )
    timestamp: datetime
    lexical_signal: str | None = Field(default=None, description="Keyword that triggered lexical classification")
    behavioral_signal: str | None = Field(default=None, description="Tool pattern that confirmed classification")
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MEDIUM)


class SessionTotals(BaseModel):
    """Aggregate session-level metrics."""

    model_config = ConfigDict(extra="forbid")

    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read: int = 0
    total_cache_create: int = 0
    total_user_messages: int = 0
    total_assistant_messages: int = 0
    correction_count: int = 0
    redirection_count: int = 0
    stage_count: int = 0

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


class SessionTelemetry(BaseModel):
    """Complete parsed session telemetry -- the top-level output model.

    This is what the JSONL parser produces and what downstream
    consumers (stage detector, correction classifier, contract
    builder) operate on.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    session_name: str = Field(
        default="",
        description=(
            "Human-readable session identifier. Claude Code: latest customTitle "
            "from `custom-title` records (driven by /rename and auto-titling). "
            "Codex: latest thread_name from `event_msg/thread_name_updated` events. "
            "Empty when neither is available — consumers fall back to first-prompt "
            "slug or session_id when constructing receipt filenames."
        ),
    )
    project_path: str
    git_branch: str | None = None
    model: str | None = None
    runtime: str = Field(
        description=(
            "Agent runtime identifier (claude-code, codex, ...). Stamped by the "
            "parser; consumed by the receipt resolver to select the identity "
            "package (glyph id + wordmark) only — never a theme. Receipts always "
            "render on the primer genome. See telemetry.runtimes."
        ),
    )
    timestamp: datetime = Field(description="Session start time")
    duration_minutes: float = Field(default=0.0, description="Wall-clock duration")
    context_window: int = Field(
        default=0,
        description=(
            "Model context window in tokens (200000 for Claude 200K models, "
            "1000000 for opus -1m, the runtime-reported window for Codex). "
            "0 signals the parser could not determine a window; the receipt "
            "falls back to the default-window map keyed on the model id."
        ),
    )
    peak_context_tokens: int = Field(
        default=0,
        description=(
            "Maximum modelled context occupancy across the session "
            "(input + cache_read + cache_create at any single assistant "
            "turn). Drives the receipt's peak marker. 0 when no assistant "
            "turn carried usage."
        ),
    )
    turn_duration_minutes: float | None = Field(
        default=None,
        description=(
            "Sum of per-turn compute durations when the runtime emits them. "
            "Claude Code emits `system.turn_duration` events and the parser "
            "sums them here; Codex has no equivalent and leaves this None. "
            "Receipts prefer this over stage-span sums because it counts "
            "agent compute time directly and never absorbs idle gaps that "
            "the stage detector failed to break on. None signals the "
            "fallback path (min of stage-span sum and wall-clock span)."
        ),
    )
    tool_calls: list[ToolCall] = Field(
        default_factory=list,
        description="Flat ordered list of all tool calls",
    )
    stages: list[Stage] = Field(default_factory=list)
    agents: list[AgentSpan] = Field(default_factory=list)
    user_events: list[UserEvent] = Field(default_factory=list)
    command_events: list[CommandEvent] = Field(
        default_factory=list,
        description=(
            "Context-window reset events (/compact, /clear, auto-compaction) "
            "in transcript order. Each carries the modelled occupancy on "
            "either side of the reset; the receipt's context-load curve "
            "renders one typed glyph per event and uses ``occupancy_after`` "
            "as the post-reset floor. Empty when no resets are detected."
        ),
    )
    tool_summary: dict[str, ToolSummary] = Field(
        default_factory=dict,
        description="tool_name -> aggregate stats",
    )
    totals: SessionTotals = Field(default_factory=SessionTotals)
    files_accessed: list[str] = Field(
        default_factory=list,
        description="Ordered unique file paths touched during session",
    )
