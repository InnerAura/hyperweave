"""Tests for :mod:`hyperweave.compose.bar_chart`.

Locks the v0.2.21 risograph-canonical layout invariants:

* Bars are baseline-aligned (no overflow above panel top — the Phase D bug).
* Heights encode token density; max bar fills the per-panel ``bar_max_h``.
* Peak marker positioned at the max-tokens bar.
* Error ticks emitted in a dedicated band, separate from per-bar geometry.
* Grid lines render at major time intervals when ``duration_m`` is provided.
* Sessions over ``max_bars`` collapse via ``merge_consecutive_same_class``.
* Width sums + gaps fit within ``area_w`` (no right-edge overflow).
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from hyperweave.compose.bar_chart import (
    BAR_MIN_H,
    BAR_TOP_Y,
    DEFAULT_PANEL_H,
    ERROR_BAND_Y,
    HEADER_H,
    LEGEND_H,
    TIME_AXIS_H,
    BarChartCell,
    BarChartLayout,
    ErrorTick,
    TimeAxisTick,
    _derive_panel_geometry,
    compute_time_axis_ticks,
    layout_bar_chart,
    merge_consecutive_same_class,
)


def _stage(
    cls: str = "explore",
    tokens: int = 1000,
    errors: int = 0,
    tools: int = 5,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    s: dict[str, Any] = {
        "dominant_class": cls,
        "tokens": tokens,
        "errors": errors,
        "tools": tools,
    }
    if start:
        s["start"] = start
    if end:
        s["end"] = end
    return s


# --------------------------------------------------------------------------- #
# Panel geometry derivation                                                   #
# --------------------------------------------------------------------------- #


def test_panel_geometry_derives_from_panel_h() -> None:
    """For panel_h=130 (canonical): baseline=108, track=78, max=35."""
    baseline, track, max_h = _derive_panel_geometry(130)
    assert baseline == 130 - LEGEND_H == 108
    assert track == baseline - BAR_TOP_Y == 78
    assert max_h == int(78 * 0.46) == 35


def test_panel_geometry_scales_with_panel_h() -> None:
    """Doubling panel_h grows track + bar_max_h coherently."""
    _, track_a, max_a = _derive_panel_geometry(130)
    _, track_b, max_b = _derive_panel_geometry(200)
    assert track_b > track_a
    assert max_b > max_a


def test_panel_geometry_respects_invariant() -> None:
    """BAR_MAX_H + BAR_TOP_Y must always be < BASELINE_Y (no overflow possible)."""
    for ph in (92, 130, 200, 300):
        baseline, _, max_h = _derive_panel_geometry(ph)
        assert BAR_TOP_Y + max_h < baseline, f"overflow possible at panel_h={ph}"


def test_module_constants_are_panel_h_independent() -> None:
    """HEADER_H, TIME_AXIS_H, BAR_TOP_Y, ERROR_BAND_Y, BAR_MIN_H, LEGEND_H stay constant."""
    assert HEADER_H == 12
    assert TIME_AXIS_H == 18
    assert BAR_TOP_Y == HEADER_H + TIME_AXIS_H == 30
    assert ERROR_BAND_Y == HEADER_H + 14 == 26
    assert BAR_MIN_H == 5
    assert LEGEND_H == 22


# --------------------------------------------------------------------------- #
# Empty / single-stage baselines                                              #
# --------------------------------------------------------------------------- #


def test_empty_stages_returns_empty_layout() -> None:
    layout = layout_bar_chart([], area_w=752)
    assert layout.bars == []
    assert layout.error_ticks == []
    assert layout.peak_marker is None
    assert layout.grid_lines == []
    assert layout.original_count == 0
    assert layout.shown_count == 0


def test_single_stage_renders_one_bar_at_full_width() -> None:
    layout = layout_bar_chart([_stage(tokens=1000)], area_w=752)
    assert len(layout.bars) == 1
    assert layout.original_count == 1
    assert layout.shown_count == 1
    assert layout.bars[0].x == 0
    assert layout.bars[0].w >= 2


# --------------------------------------------------------------------------- #
# Width invariants                                                            #
# --------------------------------------------------------------------------- #


def test_no_bar_exceeds_area_w() -> None:
    """50 stages in 752px must not push the rightmost edge past the track."""
    stages = [_stage(tokens=100 + i * 10) for i in range(50)]
    layout = layout_bar_chart(stages, area_w=752)
    assert max(b.x + b.w for b in layout.bars) <= 752


def test_widths_use_time_proportional_when_timestamps_present() -> None:
    stages = [
        _stage(start="2026-04-19T00:00:00", end="2026-04-19T00:05:00", tokens=1000),
        _stage(start="2026-04-19T00:05:00", end="2026-04-19T03:00:00", tokens=1000),
    ]
    layout = layout_bar_chart(stages, area_w=752)
    assert layout.bars[1].w > 5 * layout.bars[0].w


def test_widths_fall_back_to_token_share_when_timestamps_absent() -> None:
    stages = [_stage(tokens=1000), _stage(tokens=4000)]
    layout = layout_bar_chart(stages, area_w=752)
    assert layout.bars[1].w > layout.bars[0].w


# --------------------------------------------------------------------------- #
# Variable height — token-density encoding                                    #
# --------------------------------------------------------------------------- #


def test_heavy_stage_taller_than_light_stage() -> None:
    stages = [_stage(tokens=10_000), _stage(tokens=100)]
    layout = layout_bar_chart(stages, area_w=752)
    assert layout.bars[0].h > layout.bars[1].h


def test_max_token_stage_fills_per_panel_bar_max_h() -> None:
    """Tallest bar exactly equals the per-call ``layout.bar_max_h``."""
    stages = [_stage(tokens=10_000), _stage(tokens=2000), _stage(tokens=500)]
    layout = layout_bar_chart(stages, area_w=752)
    assert max(b.h for b in layout.bars) == layout.bar_max_h


def test_zero_token_stage_falls_back_to_bar_min_h() -> None:
    stages = [_stage(tokens=10_000), _stage(tokens=0)]
    layout = layout_bar_chart(stages, area_w=752)
    assert min(b.h for b in layout.bars) == BAR_MIN_H


def test_all_zero_tokens_does_not_divide_by_zero() -> None:
    stages = [_stage(tokens=0, tools=5), _stage(tokens=0, tools=3)]
    layout = layout_bar_chart(stages, area_w=752)
    assert all(b.h == BAR_MIN_H for b in layout.bars)


def test_bars_baseline_align_to_per_panel_baseline() -> None:
    """y + h equals the layout's computed baseline_y for every bar."""
    stages = [_stage(tokens=t) for t in (10_000, 5000, 2000, 100)]
    layout = layout_bar_chart(stages, area_w=752)
    for b in layout.bars:
        assert b.y + b.h == layout.baseline_y


def test_no_bar_overflows_panel_top() -> None:
    """The Phase D y=-1 overflow bug must not recur — bar tops stay in range.

    Specifically: bar.y >= BAR_TOP_Y for every bar at every panel_h ≥ 80.
    """
    stages = [_stage(tokens=t) for t in (10_000, 5000, 2000, 100, 50, 1, 0)]
    for panel_h in (92, 130, 200):
        layout = layout_bar_chart(stages, area_w=752, area_h=panel_h)
        for b in layout.bars:
            assert b.y >= BAR_TOP_Y, f"bar overflowed top at panel_h={panel_h}, y={b.y}"


# --------------------------------------------------------------------------- #
# Peak marker                                                                 #
# --------------------------------------------------------------------------- #


def test_peak_marker_positioned_at_max_tokens_bar() -> None:
    """The peak bar's ``is_peak`` flag is set, and the peak_marker rect's x
    matches that bar's x (signal-color tick spans the bar's full width)."""
    stages = [_stage(tokens=1000), _stage(tokens=10_000), _stage(tokens=500)]
    layout = layout_bar_chart(stages, area_w=752)
    assert layout.peak_marker is not None
    peak_bar = layout.bars[1]  # max tokens
    assert peak_bar.is_peak is True
    assert layout.peak_marker.x == peak_bar.x
    assert layout.peak_marker.w == peak_bar.w
    # Peak marker sits 1.5px above the peak bar's top.
    assert layout.peak_marker.y < peak_bar.y


def test_only_one_bar_carries_is_peak() -> None:
    stages = [_stage(tokens=t) for t in (1000, 10_000, 500, 2000)]
    layout = layout_bar_chart(stages, area_w=752)
    peak_count = sum(1 for b in layout.bars if b.is_peak)
    assert peak_count == 1


def test_peak_bar_has_higher_opacity() -> None:
    stages = [_stage(tokens=t) for t in (1000, 10_000, 500)]
    layout = layout_bar_chart(stages, area_w=752)
    peak_bar = next(b for b in layout.bars if b.is_peak)
    other_bars = [b for b in layout.bars if not b.is_peak]
    assert peak_bar.opacity > other_bars[0].opacity
    assert peak_bar.opacity == 0.85  # PEAK_OPACITY
    assert other_bars[0].opacity == 0.78  # BAR_OPACITY


def test_same_class_adjacent_bars_alternate_opacity_no_peak() -> None:
    # Three same-class bars with tokens=1 (peak detection disabled). Without
    # alternation, all three would render at BAR_OPACITY → reads as one
    # continuous rectangle. Alternation makes boundaries visible.
    stages = [_stage(cls="mutate", tokens=1, tools=t) for t in (5, 5, 5)]
    layout = layout_bar_chart(stages, area_w=752)
    assert len(layout.bars) == 3
    assert all(not b.is_peak for b in layout.bars)
    # Adjacent pairs differ; pattern is BAR / PEAK / BAR.
    assert [b.opacity for b in layout.bars] == [0.78, 0.85, 0.78]


def test_diverse_class_bars_all_use_base_opacity_except_peak() -> None:
    # When adjacent bars have DIFFERENT classes, the boundary is already
    # visible via color change — no opacity stagger needed. Regression guard
    # for diverse-class sessions: zero behavior change vs pre-stagger.
    stages = [
        _stage(cls="explore", tokens=500),
        _stage(cls="execute", tokens=2000),  # peak
        _stage(cls="mutate", tokens=800),
    ]
    layout = layout_bar_chart(stages, area_w=752)
    assert len(layout.bars) == 3
    non_peak = [b for b in layout.bars if not b.is_peak]
    # Both non-peak bars at base opacity.
    assert {b.opacity for b in non_peak} == {0.78}
    peak = next(b for b in layout.bars if b.is_peak)
    assert peak.opacity == 0.85


def test_peak_inside_same_class_run_does_not_disrupt_alternation() -> None:
    # Run of same-class bars with the peak in the middle. Bars around the peak
    # alternate against PEAK_OPACITY, so they land at BAR_OPACITY — visually
    # distinct from the peak.
    stages = [_stage(cls="mutate", tokens=t) for t in (500, 5000, 500)]
    layout = layout_bar_chart(stages, area_w=752)
    assert len(layout.bars) == 3
    assert [b.opacity for b in layout.bars] == [0.78, 0.85, 0.78]


def test_same_class_pair_with_first_as_peak_alternates() -> None:
    # Image-2 medium-session shape: 2 mutate stages, first one peak.
    # Pre-fix: 2 identical-color bars at 0.78 and 0.85 (peak-only differentiation).
    # Post-fix: same 0.85/0.78 — the peak vs non-peak contrast already
    # differentiates. This test pins behavior so a future "stagger every same
    # class regardless of peak" refactor doesn't accidentally land at 0.85/0.85.
    stages = [
        _stage(cls="mutate", tokens=5000),  # peak
        _stage(cls="mutate", tokens=1000),
    ]
    layout = layout_bar_chart(stages, area_w=752)
    assert layout.bars[0].is_peak
    assert layout.bars[0].opacity == 0.85
    assert layout.bars[1].opacity == 0.78
    assert layout.bars[0].opacity != layout.bars[1].opacity


def test_peak_marker_absent_when_all_zero_tokens() -> None:
    """Edge case: when no stage has billable tokens, no peak marker is
    rendered (the visual implication "this stage spent the most" is meaningless)."""
    stages = [_stage(tokens=0, tools=3), _stage(tokens=0, tools=5)]
    layout = layout_bar_chart(stages, area_w=752)
    assert layout.peak_marker is None
    assert all(not b.is_peak for b in layout.bars)


# --------------------------------------------------------------------------- #
# Error band                                                                  #
# --------------------------------------------------------------------------- #


def test_error_ticks_emitted_only_for_stages_with_errors() -> None:
    """A stage without errors produces no ErrorTick record."""
    stages = [
        _stage(tokens=1000, errors=0),
        _stage(tokens=2000, errors=3),
        _stage(tokens=500, errors=0),
        _stage(tokens=800, errors=1),
    ]
    layout = layout_bar_chart(stages, area_w=752)
    assert len(layout.error_ticks) == 2  # only the 2 stages with errors


def test_error_ticks_in_dedicated_band_at_fixed_y() -> None:
    """All error ticks render at ERROR_BAND_Y (constant), regardless of
    bar height. This is the v0.2.21 risograph treatment — dedicated row
    above the bars instead of per-bar inline marks."""
    stages = [
        _stage(tokens=10_000, errors=2),  # tall bar
        _stage(tokens=100, errors=1),  # short bar
    ]
    layout = layout_bar_chart(stages, area_w=752)
    for tick in layout.error_ticks:
        assert tick.y == ERROR_BAND_Y == 26


def test_error_ticks_centered_on_corresponding_bars() -> None:
    """Tick x-coordinate aligns to the center of the bar with errors."""
    stages = [
        _stage(tokens=1000, errors=0),
        _stage(tokens=2000, errors=3),
    ]
    layout = layout_bar_chart(stages, area_w=752)
    # Only the second stage has errors → 1 tick. Find which bar.
    bar_with_errors = layout.bars[1]
    tick = layout.error_ticks[0]
    assert tick.x == bar_with_errors.x + bar_with_errors.w // 2


def test_error_tick_count_field_propagates_from_stage() -> None:
    """ErrorTick.count records the underlying stage's error count for
    accessibility / data-hw-* attributes."""
    stages = [_stage(tokens=1000, errors=7)]
    layout = layout_bar_chart(stages, area_w=752)
    assert layout.error_ticks[0].count == 7


def test_per_bar_error_tick_y_legacy_field_still_populated() -> None:
    """Backwards-compat: BarChartCell.error_tick_y is still set so legacy
    template snippets render. The new rendering path uses the dedicated
    error_ticks band; this field is the older per-bar y-offset for
    callers that haven't migrated."""
    stages = [_stage(tokens=5000, errors=3)]
    layout = layout_bar_chart(stages, area_w=752)
    assert layout.bars[0].error_tick_y < layout.bars[0].y


# --------------------------------------------------------------------------- #
# Header labels (rhythm panel composite header)                               #
# --------------------------------------------------------------------------- #


def test_total_tokens_label_formatted_for_header() -> None:
    """Header right-side label shows total billed tokens."""
    stages = [_stage(tokens=1_000_000), _stage(tokens=2_000_000)]
    layout = layout_bar_chart(stages, area_w=752)
    assert layout.total_tokens_label == "3.0M"


def test_peak_tokens_label_includes_peak_prefix() -> None:
    stages = [_stage(tokens=10_000_000), _stage(tokens=500_000)]
    layout = layout_bar_chart(stages, area_w=752)
    assert layout.peak_tokens_label.startswith("PEAK ")
    assert "10M" in layout.peak_tokens_label


# --------------------------------------------------------------------------- #
# Grid lines (vertical strokes at major time intervals)                       #
# --------------------------------------------------------------------------- #


def test_grid_lines_at_major_time_intervals_for_long_session() -> None:
    """120-minute session → 30-minute majors at 30, 60, 90 (terminal not emitted)."""
    stages = [_stage(tokens=1000) for _ in range(5)]
    layout = layout_bar_chart(stages, area_w=480, duration_m=120)
    assert len(layout.grid_lines) == 3  # 30m, 60m, 90m (not 0m or 120m)
    # x positions scale to area_w.
    xs = [g.x for g in layout.grid_lines]
    assert xs == [int(480 * 30 / 120), int(480 * 60 / 120), int(480 * 90 / 120)]


def test_grid_lines_use_5m_intervals_for_short_session() -> None:
    """20-minute session → 5-minute majors at 5, 10, 15."""
    stages = [_stage(tokens=1000)]
    layout = layout_bar_chart(stages, area_w=480, duration_m=20)
    xs = [g.x for g in layout.grid_lines]
    assert len(xs) == 3
    assert xs[0] == int(480 * 5 / 20)


def test_grid_lines_empty_when_duration_not_provided() -> None:
    stages = [_stage(tokens=1000)]
    layout = layout_bar_chart(stages, area_w=480)
    assert layout.grid_lines == []


# --------------------------------------------------------------------------- #
# Overflow merge — sessions > max_bars                                        #
# --------------------------------------------------------------------------- #


def test_under_max_bars_no_merge() -> None:
    stages = [_stage(cls="explore" if i % 2 else "mutate") for i in range(30)]
    layout = layout_bar_chart(stages, area_w=752)
    assert layout.original_count == 30
    assert layout.shown_count == 30
    assert len(layout.bars) == 30


def test_over_max_bars_collapses_same_class_runs() -> None:
    stages = [_stage(cls="explore" if i % 2 else "mutate", tokens=100) for i in range(200)]
    layout = layout_bar_chart(stages, area_w=752, max_bars=60)
    assert layout.original_count == 200
    assert layout.shown_count <= 60


def test_run_of_same_class_collapses_into_one_bar() -> None:
    stages = [_stage(cls="explore", tokens=100, errors=1) for _ in range(100)]
    merged = merge_consecutive_same_class(stages, max_bars=60)
    assert len(merged) <= 60
    if len(merged) == 1:
        assert merged[0]["tokens"] == 100 * 100
        assert merged[0]["errors"] == 100 * 1


def test_merge_preserves_first_start_and_last_end() -> None:
    stages = [
        _stage(cls="explore", start="2026-04-19T00:00:00", end="2026-04-19T00:05:00"),
        _stage(cls="explore", start="2026-04-19T00:05:00", end="2026-04-19T00:10:00"),
        _stage(cls="explore", start="2026-04-19T00:10:00", end="2026-04-19T00:15:00"),
    ]
    merged = merge_consecutive_same_class(stages, max_bars=1)
    assert len(merged) == 1
    assert merged[0]["start"] == "2026-04-19T00:00:00"
    assert merged[0]["end"] == "2026-04-19T00:15:00"


def test_merge_breaks_on_class_boundary() -> None:
    stages = [
        _stage(cls="explore"),
        _stage(cls="explore"),
        _stage(cls="mutate"),
        _stage(cls="explore"),
    ]
    merged = merge_consecutive_same_class(stages, max_bars=10)
    assert len(merged) == 4


def test_merge_below_threshold_returns_unchanged() -> None:
    stages = [_stage() for _ in range(10)]
    merged = merge_consecutive_same_class(stages, max_bars=60)
    assert len(merged) == 10


# --------------------------------------------------------------------------- #
# Time-axis ticks                                                             #
# --------------------------------------------------------------------------- #


def test_short_session_uses_5_minute_intervals() -> None:
    ticks = compute_time_axis_ticks(duration_m=20.0, area_w=480)
    major_labels = [t.label for t in ticks if t.is_major]
    assert "0m" in major_labels
    assert "5m" in major_labels
    assert "10m" in major_labels
    assert "20m" in major_labels  # terminal


def test_long_session_uses_30_minute_intervals() -> None:
    ticks = compute_time_axis_ticks(duration_m=120.0, area_w=480)
    major_labels = [t.label for t in ticks if t.is_major]
    assert "0m" in major_labels
    assert "30m" in major_labels
    assert "60m" in major_labels
    assert "90m" in major_labels
    assert "120m" in major_labels


def test_terminal_tick_lands_at_area_w() -> None:
    ticks = compute_time_axis_ticks(duration_m=94.0, area_w=480)
    terminal = max(ticks, key=lambda t: t.x)
    assert terminal.x == 480
    assert terminal.is_major is True


def test_zero_duration_returns_no_ticks() -> None:
    assert compute_time_axis_ticks(duration_m=0.0, area_w=480) == []


def test_minor_ticks_are_unlabeled() -> None:
    ticks = compute_time_axis_ticks(duration_m=120.0, area_w=480)
    for t in ticks:
        if not t.is_major:
            assert t.label == ""


# --------------------------------------------------------------------------- #
# Type discipline                                                             #
# --------------------------------------------------------------------------- #


def test_bar_chart_layout_is_frozen() -> None:
    layout = layout_bar_chart([_stage()], area_w=752)
    assert isinstance(layout, BarChartLayout)
    with pytest.raises(dataclasses.FrozenInstanceError):
        layout.original_count = 999  # type: ignore[misc]


def test_bar_chart_cells_are_frozen() -> None:
    layout = layout_bar_chart([_stage()], area_w=752)
    bar = layout.bars[0]
    assert isinstance(bar, BarChartCell)
    with pytest.raises(dataclasses.FrozenInstanceError):
        bar.x = 999  # type: ignore[misc]


def test_error_ticks_are_frozen() -> None:
    layout = layout_bar_chart([_stage(tokens=1000, errors=1)], area_w=752)
    tick = layout.error_ticks[0]
    assert isinstance(tick, ErrorTick)
    with pytest.raises(dataclasses.FrozenInstanceError):
        tick.x = 999  # type: ignore[misc]


def test_peak_marker_is_frozen() -> None:
    layout = layout_bar_chart([_stage(tokens=1000), _stage(tokens=5000)], area_w=752)
    assert layout.peak_marker is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        layout.peak_marker.x = 999  # type: ignore[misc]


def test_grid_lines_are_frozen() -> None:
    layout = layout_bar_chart([_stage()], area_w=480, duration_m=120)
    assert layout.grid_lines
    with pytest.raises(dataclasses.FrozenInstanceError):
        layout.grid_lines[0].x = 999  # type: ignore[misc]


def test_time_axis_ticks_are_frozen() -> None:
    ticks = compute_time_axis_ticks(duration_m=20.0, area_w=480)
    assert ticks
    tick = ticks[0]
    assert isinstance(tick, TimeAxisTick)
    with pytest.raises(dataclasses.FrozenInstanceError):
        tick.x = 999  # type: ignore[misc]


def test_default_panel_h_is_canonical() -> None:
    """DEFAULT_PANEL_H matches the receipt's rhythm zone allocation."""
    assert DEFAULT_PANEL_H == 130
