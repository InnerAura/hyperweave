"""Tests for :mod:`hyperweave.compose.rhythm_strip`.

Locks the v0.2.21 rhythm-strip-v2 helper invariants:

* :func:`compute_session_velocity` returns tokens-per-minute + a compact
  display label, with safe behavior for zero-duration sessions.
* :func:`compute_velocity_sparkline` returns 8 panel-relative points and
  closed/open SVG path strings.
* :func:`compute_status_dot` maps (errors, total_calls) to OK/WARN/ERR
  via the documented thresholds.
* :func:`compute_dominant_phase` picks the dominant tool class by time
  share when timestamps are present, falling back to call-count when
  they aren't.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from hyperweave.compose.rhythm_strip import (
    ERR_ERROR_RATE,
    WARN_ABS_THRESHOLD,
    WARN_ERROR_RATE,
    DominantPhase,
    StatusIndicator,
    VelocitySparkline,
    compute_dominant_phase,
    compute_session_velocity,
    compute_status_dot,
    compute_velocity_sparkline,
)


def _stage(
    cls: str = "explore",
    tokens: int = 1000,
    tools: int = 5,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    s: dict[str, Any] = {
        "dominant_class": cls,
        "tokens": tokens,
        "tools": tools,
    }
    if start:
        s["start"] = start
    if end:
        s["end"] = end
    return s


# --------------------------------------------------------------------------- #
# Velocity                                                                    #
# --------------------------------------------------------------------------- #


def test_velocity_zero_duration_returns_zero() -> None:
    v, label = compute_session_velocity([_stage(tokens=1000)], duration_m=0)
    assert v == 0
    assert label == "0"


def test_velocity_with_no_stages_returns_zero() -> None:
    v, label = compute_session_velocity([], duration_m=10)
    assert v == 0
    assert label == "0"


def test_velocity_basic_division() -> None:
    """1M tokens over 10 minutes = 100K tokens/min."""
    v, label = compute_session_velocity([_stage(tokens=1_000_000)], duration_m=10)
    assert v == 100_000
    assert label == "100K"


def test_velocity_label_compact_formatting() -> None:
    """High velocity formats as M when ≥1M; mid-range formats as K."""
    v, label = compute_session_velocity([_stage(tokens=20_000_000)], duration_m=10)
    assert v == 2_000_000
    assert label == "2.0M"

    v, label = compute_session_velocity([_stage(tokens=5_000)], duration_m=1)
    assert v == 5_000
    assert label == "5.0K"


def test_velocity_under_1k_renders_as_raw_number() -> None:
    v, label = compute_session_velocity([_stage(tokens=500)], duration_m=10)
    assert v == 50
    assert label == "50"


# --------------------------------------------------------------------------- #
# Sparkline                                                                   #
# --------------------------------------------------------------------------- #


def test_sparkline_returns_n_buckets_points() -> None:
    stages = [
        _stage(tokens=1000, start="2026-04-19T00:00:00", end="2026-04-19T00:10:00"),
        _stage(tokens=2000, start="2026-04-19T00:10:00", end="2026-04-19T00:20:00"),
    ]
    sparkline = compute_velocity_sparkline(
        stages, duration_m=20, x_left=210, x_right=256, y_top=56, y_bottom=68, n_buckets=8
    )
    assert len(sparkline.points) == 8


def test_sparkline_points_within_xy_bounds() -> None:
    stages = [_stage(tokens=t, start="2026-04-19T00:00:00", end="2026-04-19T00:30:00") for t in (500, 1000, 2000)]
    sparkline = compute_velocity_sparkline(stages, duration_m=30, x_left=210, x_right=256, y_top=56, y_bottom=68)
    for x, y in sparkline.points:
        assert 210 <= x <= 256, f"x out of bounds: {x}"
        assert 56 <= y <= 68, f"y out of bounds: {y}"


def test_sparkline_first_point_at_x_left_last_at_x_right() -> None:
    stages = [_stage(tokens=t, start="2026-04-19T00:00:00", end="2026-04-19T00:30:00") for t in (500, 1000, 2000)]
    sparkline = compute_velocity_sparkline(stages, duration_m=30, x_left=210, x_right=256, y_top=56, y_bottom=68)
    assert sparkline.points[0][0] == 210
    assert sparkline.points[-1][0] == 256


def test_sparkline_stroke_path_is_M_then_L_sequence() -> None:
    stages = [_stage(tokens=t, start="2026-04-19T00:00:00", end="2026-04-19T00:30:00") for t in (500, 1000, 2000)]
    sparkline = compute_velocity_sparkline(stages, duration_m=30, x_left=210, x_right=256, y_top=56, y_bottom=68)
    assert sparkline.stroke_path.startswith("M")
    # Should have N-1 L commands for N points.
    assert sparkline.stroke_path.count("L") == 7  # 8 points → 7 L segments


def test_sparkline_fill_path_closes_with_z() -> None:
    """Fill path must close back to the baseline (forms a polygon)."""
    stages = [_stage(tokens=t, start="2026-04-19T00:00:00", end="2026-04-19T00:30:00") for t in (500, 1000, 2000)]
    sparkline = compute_velocity_sparkline(stages, duration_m=30, x_left=210, x_right=256, y_top=56, y_bottom=68)
    assert sparkline.fill_path.startswith("M")
    assert sparkline.fill_path.endswith("Z")
    # Fill closes via 2 extra L commands (down to baseline, back to start) + Z.
    assert sparkline.fill_path.count("L") == 7 + 2


def test_sparkline_labels_show_session_time_range() -> None:
    sparkline = compute_velocity_sparkline(
        [_stage(tokens=1000, start="2026-04-19T00:00:00", end="2026-04-19T00:45:00")],
        duration_m=45,
        x_left=210,
        x_right=256,
        y_top=56,
        y_bottom=68,
    )
    assert sparkline.label_left == "0m"
    assert sparkline.label_right == "45m"


def test_sparkline_empty_session_returns_flat_baseline() -> None:
    """Zero stages → all sparkline points sit on the baseline (y=y_bottom)."""
    sparkline = compute_velocity_sparkline([], duration_m=20, x_left=210, x_right=256, y_top=56, y_bottom=68)
    assert all(y == 68 for _, y in sparkline.points)


def test_sparkline_high_velocity_bucket_renders_higher_on_chart() -> None:
    """Bucket with more tokens should produce a smaller y (visually higher)
    than buckets with fewer tokens."""
    stages = [
        # First half: low velocity (1K total)
        _stage(tokens=1000, start="2026-04-19T00:00:00", end="2026-04-19T00:10:00"),
        # Second half: high velocity (100K total)
        _stage(tokens=100_000, start="2026-04-19T00:10:00", end="2026-04-19T00:20:00"),
    ]
    sparkline = compute_velocity_sparkline(stages, duration_m=20, x_left=0, x_right=100, y_top=0, y_bottom=20)
    # Last bucket (high velocity) should be lower y (closer to y_top) than first bucket.
    first_y = sparkline.points[0][1]
    last_y = sparkline.points[-1][1]
    assert last_y < first_y


# --------------------------------------------------------------------------- #
# Status dot                                                                  #
# --------------------------------------------------------------------------- #


def test_status_zero_calls_returns_ok() -> None:
    indicator = compute_status_dot(n_errors=0, total_calls=0)
    assert indicator.word == "OK"
    assert indicator.severity == "ok"
    assert indicator.color_var == "--dna-status-passing-core"


def test_status_no_errors_returns_ok() -> None:
    indicator = compute_status_dot(n_errors=0, total_calls=100)
    assert indicator.word == "OK"


def test_status_low_error_rate_returns_ok() -> None:
    """1% error rate (1/100) with only 1 error → OK (below both thresholds)."""
    indicator = compute_status_dot(n_errors=1, total_calls=100)
    assert indicator.word == "OK"


def test_status_warn_error_rate_threshold() -> None:
    """3 errors / 100 = 3% → above WARN_ERROR_RATE (2%) → WARN."""
    indicator = compute_status_dot(n_errors=3, total_calls=100)
    assert indicator.word == "WARN"
    assert indicator.severity == "warn"
    assert indicator.color_var == "--dna-status-warning-core"


def test_status_warn_absolute_threshold() -> None:
    """5 errors / 1000 = 0.5% rate but 5 absolute → WARN_ABS_THRESHOLD trips."""
    assert WARN_ABS_THRESHOLD == 5
    indicator = compute_status_dot(n_errors=5, total_calls=1000)
    assert indicator.word == "WARN"


def test_status_err_threshold() -> None:
    """20% error rate → ERR."""
    indicator = compute_status_dot(n_errors=20, total_calls=100)
    assert indicator.word == "ERR"
    assert indicator.severity == "err"
    assert indicator.color_var == "--dna-status-failing-core"


@pytest.mark.parametrize(
    ("n_errors", "total", "expected_word"),
    [
        (0, 100, "OK"),
        (1, 100, "OK"),
        (2, 100, "WARN"),  # 2% = WARN_ERROR_RATE exactly
        (5, 1000, "WARN"),  # absolute threshold
        (10, 100, "ERR"),  # 10% = ERR_ERROR_RATE exactly
        (15, 100, "ERR"),
    ],
)
def test_status_threshold_table(n_errors: int, total: int, expected_word: str) -> None:
    assert compute_status_dot(n_errors=n_errors, total_calls=total).word == expected_word


def test_status_thresholds_are_documented_constants() -> None:
    """Document the threshold values so downstream consumers have a stable reference."""
    assert WARN_ERROR_RATE == 0.02
    assert ERR_ERROR_RATE == 0.10
    assert WARN_ABS_THRESHOLD == 5


# --------------------------------------------------------------------------- #
# Dominant phase                                                              #
# --------------------------------------------------------------------------- #


def test_dominant_phase_empty_stages() -> None:
    phase = compute_dominant_phase([], duration_m=10)
    assert phase.label == ""
    assert phase.tool_class == "explore"
    assert phase.pct_time == 0


def test_dominant_phase_picks_most_frequent_class_by_time() -> None:
    stages = [
        # 30 minutes of explore
        _stage(cls="explore", start="2026-04-19T00:00:00", end="2026-04-19T00:30:00"),
        # 10 minutes of mutate
        _stage(cls="mutate", start="2026-04-19T00:30:00", end="2026-04-19T00:40:00"),
    ]
    phase = compute_dominant_phase(stages, duration_m=40)
    assert phase.label == "EXPLORE"
    assert phase.tool_class == "explore"
    assert phase.pct_time == 75  # 30/40


def test_dominant_phase_falls_back_to_call_count_without_timestamps() -> None:
    """When stages lack start/end, weight by tools (call count) instead."""
    stages = [
        _stage(cls="explore", tools=80),
        _stage(cls="mutate", tools=20),
    ]
    phase = compute_dominant_phase(stages, duration_m=10)
    assert phase.tool_class == "explore"
    assert phase.pct_time == 80  # 80/100


def test_dominant_phase_label_is_uppercase() -> None:
    """Display label is uppercased for the strip's status zone treatment."""
    stages = [_stage(cls="coordinate", tools=10)]
    phase = compute_dominant_phase(stages, duration_m=5)
    assert phase.label == "COORDINATE"


def test_format_model_label_strips_xml_unsafe_chars() -> None:
    # Claude Code's synthetic-transcript marker would otherwise break SVG
    # parsing when injected into <text> body. Resolver strips brackets at
    # the source so the template never sees angle brackets in user data.
    from hyperweave.compose.resolver import _format_model_label

    assert _format_model_label("<synthetic>") == "synthetic"
    assert _format_model_label("<>") == ""
    assert _format_model_label("model&with&amps") == "modelwithamps"
    # Normal model identifiers remain unchanged.
    assert _format_model_label("claude-opus-4-7") == "opus-4.7"


def test_dominant_phase_pct_bounded_when_stages_exceed_session_duration() -> None:
    # Stages sum to 60 minutes; session duration_m says 15 (active vs total
    # divergence, e.g. session left open after work ended). Pre-fix divisor was
    # duration_m, producing pct=400. Post-fix denominator is sum of by_class.
    stages = [
        _stage(cls="mutate", start="2026-04-19T00:00:00", end="2026-04-19T00:30:00"),
        _stage(cls="mutate", start="2026-04-19T00:30:00", end="2026-04-19T01:00:00"),
    ]
    phase = compute_dominant_phase(stages, duration_m=15.0)
    assert phase.pct_time <= 100, f"pct_time {phase.pct_time} exceeds 100"
    assert phase.pct_time == 100  # single class, all classified time is mutate


# --------------------------------------------------------------------------- #
# Type discipline                                                             #
# --------------------------------------------------------------------------- #


def test_velocity_sparkline_is_frozen() -> None:
    sparkline = compute_velocity_sparkline([], duration_m=10, x_left=0, x_right=100, y_top=0, y_bottom=20)
    assert isinstance(sparkline, VelocitySparkline)
    with pytest.raises(dataclasses.FrozenInstanceError):
        sparkline.label_left = "x"  # type: ignore[misc]


def test_status_indicator_is_frozen() -> None:
    indicator = compute_status_dot(n_errors=0, total_calls=10)
    assert isinstance(indicator, StatusIndicator)
    with pytest.raises(dataclasses.FrozenInstanceError):
        indicator.word = "x"  # type: ignore[misc]


def test_dominant_phase_is_frozen() -> None:
    phase = compute_dominant_phase([_stage(cls="explore", tools=5)], duration_m=10)
    assert isinstance(phase, DominantPhase)
    with pytest.raises(dataclasses.FrozenInstanceError):
        phase.label = "x"  # type: ignore[misc]
