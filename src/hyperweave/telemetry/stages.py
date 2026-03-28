"""Stage Detector -- Three-Signal Weighted Heuristic.

Segments a stream of tool calls into behavioral stages using
three independent signals, combined via weighted voting:

| Signal              | Weight | Method                                        |
|---------------------|--------|-----------------------------------------------|
| Temporal gaps       | 0.3    | Gap > 3x median inter-call interval           |
| Tool class shifts   | 0.4    | Dominant class changes in sliding window (N=6)|
| Explicit markers    | 0.3    | Agent spawns, mode transitions, directives    |

Ported from aura-research/systems/hooks/hw_claude_code_hook/stage_detector.py.
All tuning knobs loaded from data/telemetry/stage-config.yaml.
"""

from __future__ import annotations

import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from .models import (
    STAGE_LABEL_MAP,  # yaml config
    Stage,
    StageLabel,
    ToolCall,
    ToolClass,
)

# --------------------------------------------------------------------------- #
# LOAD CONFIG FROM YAML
# --------------------------------------------------------------------------- #

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "telemetry"


def _load_stage_config() -> dict[str, Any]:
    with (_DATA_DIR / "stage-config.yaml").open() as f:
        result: dict[str, Any] = yaml.safe_load(f)
        return result


_CFG = _load_stage_config()

WINDOW_SIZE: int = int(_CFG["window_size"])
_weights: dict[str, float] = _CFG["weights"]
TEMPORAL_WEIGHT: float = _weights["temporal"]
TOOL_CLASS_WEIGHT: float = _weights["tool_class"]
EXPLICIT_WEIGHT: float = _weights["explicit"]
BOUNDARY_THRESHOLD: float = float(_CFG["boundary_threshold"])
TEMPORAL_GAP_MULTIPLIER: float = float(_CFG["temporal_gap_multiplier"])
EXPLICIT_MARKER_TOOLS: set[str] = set(_CFG["explicit_marker_tools"])


# --------------------------------------------------------------------------- #
# SIGNAL COMPUTERS
# --------------------------------------------------------------------------- #


def _compute_inter_call_gaps(calls: list[ToolCall]) -> list[float]:
    """Compute gaps (in seconds) between consecutive tool calls."""
    gaps: list[float] = []
    for i in range(1, len(calls)):
        delta = (calls[i].timestamp - calls[i - 1].timestamp).total_seconds()
        gaps.append(max(delta, 0.0))
    return gaps


def _compute_temporal_boundaries(calls: list[ToolCall]) -> list[float]:
    """Signal 1: Temporal gaps exceeding 3x median."""
    if len(calls) < 3:
        return [0.0] * max(len(calls) - 1, 0)

    gaps = _compute_inter_call_gaps(calls)
    if not gaps:
        return []

    median_gap = statistics.median(gaps)
    if median_gap <= 0:
        median_gap = statistics.mean(gaps) if any(g > 0 for g in gaps) else 1.0

    threshold = TEMPORAL_GAP_MULTIPLIER * median_gap
    scores: list[float] = []
    for gap in gaps:
        if threshold > 0 and gap > threshold:
            scores.append(min(1.0, gap / (TEMPORAL_GAP_MULTIPLIER * median_gap)))
        else:
            scores.append(0.0)

    return scores


def _dominant_class(calls: list[ToolCall]) -> ToolClass:
    """Return the most common tool class in a list of calls."""
    if not calls:
        return ToolClass.EXPLORE
    counter = Counter(tc.tool_class for tc in calls)
    return counter.most_common(1)[0][0]


def _compute_tool_class_shifts(calls: list[ToolCall]) -> list[float]:
    """Signal 2: Sliding window dominant class changes."""
    n = len(calls)
    if n < 3:
        return [0.0] * max(n - 1, 0)

    w = WINDOW_SIZE
    scores: list[float] = []

    for i in range(n - 1):
        left_start = max(0, i - w + 1)
        left_window = calls[left_start : i + 1]
        right_end = min(n, i + 1 + w)
        right_window = calls[i + 1 : right_end]

        left_class = _dominant_class(left_window)
        right_class = _dominant_class(right_window)
        scores.append(1.0 if left_class != right_class else 0.0)

    return scores


def _compute_explicit_markers(calls: list[ToolCall]) -> list[float]:
    """Signal 3: Explicit markers (agent spawns, mode transitions)."""
    n = len(calls)
    if n < 2:
        return [0.0] * max(n - 1, 0)

    scores: list[float] = []
    for i in range(n - 1):
        if calls[i + 1].tool_name in EXPLICIT_MARKER_TOOLS:
            scores.append(1.0)
        else:
            scores.append(0.0)

    return scores


# --------------------------------------------------------------------------- #
# MAIN DETECTOR
# --------------------------------------------------------------------------- #


def detect_stages(calls: list[ToolCall]) -> list[Stage]:
    """Segment tool calls into behavioral stages.

    Parameters
    ----------
    calls
        Ordered list of tool calls from the session.

    Returns
    -------
    list[Stage]
        Detected stages with labels, boundaries, and confidence scores.
    """
    if not calls:
        return []

    if len(calls) == 1:
        return [
            Stage(
                label=STAGE_LABEL_MAP.get(  # yaml config
                    calls[0].tool_class, StageLabel.RECONNAISSANCE
                ),
                dominant_tool_class=calls[0].tool_class,
                tool_calls=calls,
                start_time=calls[0].timestamp,
                end_time=calls[0].timestamp,
                boundary_score=1.0,
            )
        ]

    # Compute boundary scores from three signals
    temporal = _compute_temporal_boundaries(calls)
    tool_class = _compute_tool_class_shifts(calls)
    explicit = _compute_explicit_markers(calls)

    n_boundaries = len(calls) - 1
    combined: list[float] = []
    for i in range(n_boundaries):
        t = temporal[i] if i < len(temporal) else 0.0
        c = tool_class[i] if i < len(tool_class) else 0.0
        e = explicit[i] if i < len(explicit) else 0.0
        score = (TEMPORAL_WEIGHT * t) + (TOOL_CLASS_WEIGHT * c) + (EXPLICIT_WEIGHT * e)
        combined.append(score)

    # Find boundaries above threshold
    boundary_indices: list[tuple[int, float]] = [
        (i, score) for i, score in enumerate(combined) if score >= BOUNDARY_THRESHOLD
    ]

    # Build stages from boundaries
    stages: list[Stage] = []
    start_idx = 0

    for boundary_idx, boundary_score in boundary_indices:
        stage_calls = calls[start_idx : boundary_idx + 1]
        if stage_calls:
            dominant = _dominant_class(stage_calls)
            label = STAGE_LABEL_MAP.get(dominant, StageLabel.RECONNAISSANCE)  # yaml config
            stages.append(
                Stage(
                    label=label,
                    dominant_tool_class=dominant,
                    tool_calls=stage_calls,
                    start_time=stage_calls[0].timestamp,
                    end_time=stage_calls[-1].timestamp,
                    boundary_score=boundary_score,
                )
            )
        start_idx = boundary_idx + 1

    # Final stage: remaining calls
    if start_idx < len(calls):
        remaining = calls[start_idx:]
        dominant = _dominant_class(remaining)
        label = STAGE_LABEL_MAP.get(dominant, StageLabel.RECONNAISSANCE)  # yaml config
        stages.append(
            Stage(
                label=label,
                dominant_tool_class=dominant,
                tool_calls=remaining,
                start_time=remaining[0].timestamp,
                end_time=remaining[-1].timestamp,
                boundary_score=1.0,
            )
        )

    return stages
