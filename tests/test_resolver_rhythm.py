"""Tests for :mod:`hyperweave.compose.rhythm` and its resolver integration.

The helper is shared between ``resolve_receipt`` (area_w=752, area_h=92)
and ``resolve_rhythm_strip`` (area_w=484, area_h=42). These tests lock
the invariants that the receipt's old in-line layout violated — so a
future drift can't silently reintroduce the overflow bug.
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

from hyperweave.compose.rhythm import BAR_HEIGHT, layout_rhythm_bars


def test_empty_stages_returns_empty_list() -> None:
    assert layout_rhythm_bars([], area_w=752, area_h=92) == []


def test_many_stage_session_fits_track() -> None:
    """79 stages in a 752px track — right edge must stay inside the track.

    Regression guard for the receipt's old layout that floored at 6px and
    ignored the gap budget, producing a rightmost bar at x=1048 — 319px
    past the 752px boundary.
    """
    stages: list[dict[str, Any]] = [{"pct": 1, "tool_class": "explore"} for _ in range(79)]
    bars = layout_rhythm_bars(stages, area_w=752, area_h=92)
    assert len(bars) == 79
    assert max(b["x"] + b["w"] for b in bars) <= 752


def test_rhythm_strip_484_area_fits_484() -> None:
    """Rhythm-strip 484px track — 40-stage session must fit within 484."""
    stages = [{"pct": 2, "tool_class": "mutate"} for _ in range(40)]
    bars = layout_rhythm_bars(stages, area_w=484, area_h=42)
    assert max(b["x"] + b["w"] for b in bars) <= 484


def test_all_bars_uniform_height() -> None:
    """§2.6: every bar is exactly BAR_HEIGHT tall regardless of pct."""
    stages = [{"pct": p, "tool_class": "explore"} for p in (1, 5, 25, 50, 100)]
    bars = layout_rhythm_bars(stages, area_w=484, area_h=42)
    assert {b["h"] for b in bars} == {BAR_HEIGHT}


def test_bars_align_bottom_of_track() -> None:
    """y = area_h - BAR_HEIGHT so bars sit flush to the bottom of the track."""
    stages = [{"pct": 50, "tool_class": "execute"}]
    bars = layout_rhythm_bars(stages, area_w=484, area_h=42)
    assert bars[0]["y"] == 42 - BAR_HEIGHT


def test_time_proportional_widths_when_timestamps_present() -> None:
    """§2.5: stages with start/end ISO timestamps get time-proportional widths.

    A 30-minute stage followed by a ~3-hour stage should render the second
    bar ~6x wider than the first — regardless of ``pct`` (which would have
    made them roughly equal in the old tool-call-share layout).
    """
    stages: list[dict[str, Any]] = [
        {
            "pct": 50,
            "tool_class": "explore",
            "start": "2026-04-19T00:00:00",
            "end": "2026-04-19T00:30:00",
        },
        {
            "pct": 50,
            "tool_class": "mutate",
            "start": "2026-04-19T00:30:00",
            "end": "2026-04-19T03:29:00",
        },
    ]
    bars = layout_rhythm_bars(stages, area_w=752, area_h=92)
    assert bars[1]["w"] > 5 * bars[0]["w"]


def test_pct_fallback_when_timestamps_missing() -> None:
    """Legacy contract without start/end falls back to pct-proportional widths."""
    stages = [
        {"pct": 10, "tool_class": "explore"},
        {"pct": 90, "tool_class": "mutate"},
    ]
    bars = layout_rhythm_bars(stages, area_w=800, area_h=40)
    # 90%-pct bar should be clearly wider than the 10%-pct bar.
    # Floor pressure + integer truncation keeps the ratio below 9x in practice.
    assert bars[1]["w"] > 3 * bars[0]["w"]


def test_gap_between_adjacent_bars_is_respected() -> None:
    """Adjacent bars are separated by gap_px; total layout respects the budget."""
    stages = [{"pct": 25, "tool_class": "execute"} for _ in range(4)]
    bars = layout_rhythm_bars(stages, area_w=100, area_h=30, gap_px=2)
    for prev, curr in pairwise(bars):
        assert curr["x"] == prev["x"] + prev["w"] + 2


def test_tool_class_propagates_to_bar() -> None:
    stages = [
        {"pct": 30, "tool_class": "explore"},
        {"pct": 70, "tool_class": "mutate"},
    ]
    bars = layout_rhythm_bars(stages, area_w=200, area_h=40)
    assert [b["tool_class"] for b in bars] == ["explore", "mutate"]


# ── End-to-end: receipt + rhythm-strip both wire through the helper ──


def _stress_telemetry(n_stages: int) -> dict[str, Any]:
    """Build telemetry with N stages so the 79-stage bug can't resurface."""
    return {
        "session": {"id": "s", "duration_minutes": 209, "model": "claude-opus"},
        "profile": {"total_input_tokens": 100, "total_output_tokens": 100, "total_cost": 0.1},
        "tools": {"Read": {"total_tokens": 100, "count": 1, "tool_class": "explore"}},
        "stages": [
            {
                "label": f"STG{i}",
                "dominant_class": "explore" if i % 2 else "mutate",
                "tools": 1,
            }
            for i in range(n_stages)
        ],
        "user_events": [],
        "agents": [],
    }


def test_receipt_rhythm_bars_fit_content_width_at_high_stage_count() -> None:
    """End-to-end: receipt compose with 79 stages fits the 752px content track."""
    from hyperweave.compose.resolver import resolve_receipt
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(type="receipt", telemetry_data=_stress_telemetry(79))
    result = resolve_receipt(spec, {}, {})
    bars = result["context"]["rhythm_bars"]
    assert len(bars) == 79
    assert max(b["x"] + b["w"] for b in bars) <= 752
    assert {b["h"] for b in bars} == {BAR_HEIGHT}


def test_rhythm_strip_bars_fit_484_at_high_stage_count() -> None:
    """End-to-end: rhythm-strip compose with 40 stages fits the 484px track.

    Note: the rhythm-strip resolver emits the bar list under context key
    ``stages`` (not ``rhythm_bars``) because its template consumes it there.
    """
    from hyperweave.compose.resolver import resolve_rhythm_strip
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(type="rhythm-strip", telemetry_data=_stress_telemetry(40))
    result = resolve_rhythm_strip(spec, {}, {})
    bars = result["context"]["stages"]
    assert len(bars) == 40
    assert max(b["x"] + b["w"] for b in bars) <= 484
    assert {b["h"] for b in bars} == {BAR_HEIGHT}
