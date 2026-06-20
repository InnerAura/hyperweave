"""Tests for :mod:`hyperweave.compose.chart.area` — the context-load burn curve.

Pins the geometric contract the receipt (and the future chart-frame ``area``
kind) depend on:

* y-mapping: occ=window → plot top (y38), occ=0 → baseline (y138).
* x-mapping: min=0 → plot left, min=span_min → plot right.
* The curve rises to its apex and ends — there is NO on-panel peak marker; the
  header's '{peak} PEAK' carries the value.
* Resets produce vertical drops at the right x with the typed glyph.
* 0-reset sessions render a single smooth rising path (no ``L`` drop).
* Crowded resets de-collide in draw_x (≥ MIN_GLYPH_GAP_PX) without moving the
  path drop.
* Error ticks sit at real minutes below the baseline, de-collided.
* Time ticks adapt to ``span_min`` (terminal always present).
* Legend keys every mark in one row (context / window ceiling / resets / error).
"""

from __future__ import annotations

import itertools
import re

import pytest

from hyperweave.compose.chart.area import (
    MIN_ERROR_GAP_PX,
    MIN_GLYPH_GAP_PX,
    MIN_TICK_GAP_PX,
    PLOT_BOTTOM_INSET,
    PLOT_TOP_INSET,
    ContextLoadLayout,
    ResetEvent,
    layout_context_load,
)
from hyperweave.core.text import format_duration

# A 200K-window session with 4 resets (the receipt's working example).
_WINDOW = 200_000.0
_PEAK = 196_000.0
_ACTIVE_MIN = 157.0
_EVENTS: list[ResetEvent] = [
    {"min": 31.0, "cmd": "compact", "to": 38_000.0},
    {"min": 62.0, "cmd": "clear", "to": 6_000.0},
    {"min": 92.0, "cmd": "auto", "to": 40_000.0},
    {"min": 138.0, "cmd": "compact", "to": 38_000.0},
]
_PLOT_BOX = (34.0, 22.0, 718.0, 116.0)
# 15 errors spread across the span (real minutes, not a modelled spread).
_ERR15 = [i * 10.0 for i in range(15)]


def _layout(**overrides: object) -> ContextLoadLayout:
    kwargs: dict[str, object] = {
        "events": _EVENTS,
        "window": _WINDOW,
        "peak_ctx": _PEAK,
        "span_min": _ACTIVE_MIN,
        "error_minutes": _ERR15,
        "plot_box": _PLOT_BOX,
    }
    kwargs.update(overrides)
    return layout_context_load(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Coordinate maps                                                             #
# --------------------------------------------------------------------------- #


def test_plot_box_insets() -> None:
    """16px top inset (ceiling band), 0 bottom inset → y(window)=38, y(0)=138."""
    layout = _layout()
    assert PLOT_TOP_INSET == 16.0
    assert PLOT_BOTTOM_INSET == 0.0
    assert layout.plot_top == 22.0 + PLOT_TOP_INSET == 38.0
    assert layout.plot_bottom == 22.0 + 116.0 - PLOT_BOTTOM_INSET == 138.0
    assert layout.plot_left == 34.0
    assert layout.plot_right == 752.0


def test_ceiling_at_window_baseline_at_zero() -> None:
    """The ceiling line sits at y=plot_top (occ=window); baseline at y=plot_bottom."""
    layout = _layout()
    assert layout.ceiling_line.y == layout.plot_top == 38.0
    assert layout.ceiling_line.label == "200K"
    assert layout.ceiling_line.dashed is True
    assert layout.ceiling_line.emphatic is True
    assert layout.baseline.y == layout.plot_bottom == 138.0
    assert layout.baseline.label == "0"
    assert layout.baseline.dashed is False


def test_mid_gridline_is_round_half_window() -> None:
    """A 200K window draws one 100K mid gridline midway between ceiling and baseline."""
    layout = _layout()
    assert len(layout.gridlines) == 1
    grid = layout.gridlines[0]
    assert grid.label == "100K"
    # 100K = midpoint → y midway between ceiling (38) and baseline (138).
    assert grid.y == pytest.approx(88.0, abs=0.5)


# --------------------------------------------------------------------------- #
# Occupancy curve (no peak marker — it rises to its apex and ends)            #
# --------------------------------------------------------------------------- #


def test_no_on_panel_peak_marker() -> None:
    """The redesigned panel has no on-curve peak marker — the curve simply rises
    to its apex and ends; the header's '{peak} PEAK' carries the value. Regression
    guard against the dot that floated / clipped / detached over three rounds."""
    layout = _layout()
    assert not hasattr(layout, "peak_marker")
    assert layout.header.peak_label == "196K PEAK"


def test_curve_apex_maps_to_peak_ctx() -> None:
    """A monotonic curve rises from (left, baseline) to (right, y(peak_ctx))."""
    layout = _layout(events=[], error_minutes=[], peak_ctx=196_000.0)
    nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", layout.line_path)]
    end_x, end_y = nums[-2], nums[-1]
    assert end_x == pytest.approx(layout.plot_right, abs=0.5)
    # y(196K), window=200K, plot 38..138: 38 + (1-196/200)*100 = 40.0
    assert end_y == pytest.approx(40.0, abs=0.3)


def test_resets_produce_vertical_drops_at_event_x() -> None:
    """Each reset emits an ``L x,y`` jump at the event's mapped x."""
    layout = _layout()
    expected_xs = [34.0 + (m / 157.0) * 718.0 for m in (31.0, 62.0, 92.0)]
    l_jumps = re.findall(r"L (\d+\.\d+),(\d+\.\d+)", layout.line_path)
    jump_xs = [float(x) for x, _ in l_jumps]
    for ex in expected_xs:
        assert any(abs(jx - ex) < 1.0 for jx in jump_xs), f"no drop near x={ex:.1f}"


def test_reset_markers_typed_and_positioned() -> None:
    """Reset markers carry the right kind and the event minute/to-value."""
    layout = _layout()
    assert len(layout.reset_markers) == 4
    assert [m.kind for m in layout.reset_markers] == ["compact", "clear", "auto", "compact"]
    assert [m.minute for m in layout.reset_markers] == [31.0, 62.0, 92.0, 138.0]


def test_unknown_cmd_falls_back_to_compact() -> None:
    """A reset with an unrecognised cmd still renders (as a compact chevron)."""
    layout = _layout(events=[{"min": 50.0, "cmd": "mystery", "to": 10_000.0}], error_minutes=[])
    assert len(layout.reset_markers) == 1
    assert layout.reset_markers[0].kind == "compact"


# --------------------------------------------------------------------------- #
# Zero-reset extreme                                                          #
# --------------------------------------------------------------------------- #


def test_zero_resets_smooth_path_no_drop() -> None:
    """No events → one smooth rising segment, no ``L`` vertical drop in the line."""
    layout = _layout(events=[], error_minutes=[])
    assert layout.reset_markers == []
    # The line is M + bezier chain with no interior ``L`` drop (the area path
    # still has its closing ``L`` segments to the baseline).
    assert re.findall(r" L \d", layout.line_path) == []
    assert layout.line_path.startswith("M ")
    assert "C " in layout.line_path


def test_zero_resets_rises_from_zero_to_peak() -> None:
    """The single segment starts at occ=0 (baseline, y138) and ends at peak_ctx."""
    layout = _layout(events=[], error_minutes=[])
    m = re.match(r"M (\d+\.\d+),(\d+\.\d+)", layout.line_path)
    assert m is not None
    start_x, start_y = float(m.group(1)), float(m.group(2))
    assert start_x == pytest.approx(34.0, abs=0.5)
    assert start_y == pytest.approx(138.0, abs=0.5)


# --------------------------------------------------------------------------- #
# Many-reset de-collision                                                     #
# --------------------------------------------------------------------------- #


def test_many_resets_glyphs_min_spaced() -> None:
    """Crowded resets de-collide in draw_x to ≥ MIN_GLYPH_GAP_PX apart."""
    crowded: list[ResetEvent] = [{"min": float(i), "cmd": "compact", "to": 10_000.0} for i in range(2, 26, 2)]
    layout = _layout(events=crowded, error_minutes=[])
    draw_xs = sorted(m.draw_x for m in layout.reset_markers)
    for a, b in itertools.pairwise(draw_xs):
        assert b - a >= MIN_GLYPH_GAP_PX - 1e-6, f"glyphs too close: {a:.1f}, {b:.1f}"


def test_decollision_preserves_path_drop_x() -> None:
    """De-collision moves draw_x but the path drop stays at the true event x."""
    crowded: list[ResetEvent] = [
        {"min": 10.0, "cmd": "compact", "to": 10_000.0},
        {"min": 11.0, "cmd": "clear", "to": 8_000.0},
    ]
    layout = _layout(events=crowded, error_minutes=[])
    m0, m1 = layout.reset_markers
    assert m0.x == pytest.approx(34.0 + (10.0 / 157.0) * 718.0, abs=0.5)
    assert m1.x == pytest.approx(34.0 + (11.0 / 157.0) * 718.0, abs=0.5)
    assert m1.draw_x - m0.draw_x >= MIN_GLYPH_GAP_PX - 1e-6


def test_every_reset_gets_a_marker_even_when_crowded() -> None:
    """Resets are load-bearing — a glyph is emitted for every event, never dropped."""
    crowded: list[ResetEvent] = [{"min": 150.0 + i * 0.2, "cmd": "compact", "to": 5_000.0} for i in range(8)]
    layout = _layout(events=crowded, error_minutes=[])
    assert len(layout.reset_markers) == len(crowded)


# --------------------------------------------------------------------------- #
# Elapsed-span x-axis (resumed-across-days sessions)                          #
# --------------------------------------------------------------------------- #


def test_events_past_active_work_distribute_on_span() -> None:
    """Resets timestamped far past the active-work sum distribute across the span."""
    events: list[ResetEvent] = [
        {"min": 2325.0, "cmd": "auto", "to": 90_000.0},
        {"min": 5725.0, "cmd": "auto", "to": 70_000.0},
        {"min": 8461.0, "cmd": "auto", "to": 108_000.0},
    ]
    layout = layout_context_load(
        events=events,
        window=1_000_000.0,
        peak_ctx=999_000.0,
        span_min=8461.0,  # elapsed wall-clock span, NOT the ~648 active-work sum
        error_minutes=[],
        plot_box=_PLOT_BOX,
    )
    pl, pr = layout.plot_left, layout.plot_right
    fracs = [(m.draw_x - pl) / (pr - pl) for m in layout.reset_markers]
    assert fracs[0] == pytest.approx(0.27, abs=0.04)
    assert fracs[1] == pytest.approx(0.68, abs=0.04)
    assert fracs[2] == pytest.approx(1.0, abs=0.04)
    assert all(b - a > 0.2 for a, b in itertools.pairwise(fracs)), f"glyphs crushed: {fracs}"


# --------------------------------------------------------------------------- #
# Error ticks (real times, axis margin)                                       #
# --------------------------------------------------------------------------- #


def test_error_ticks_at_real_minutes() -> None:
    """Ticks sit at the x of each error's REAL minute (not a modelled spread)."""
    layout = _layout(error_minutes=[20.0, 80.0, 140.0])
    xs = sorted(t.x for t in layout.error_ticks)
    expected = sorted(34.0 + (m / _ACTIVE_MIN) * 718.0 for m in (20.0, 80.0, 140.0))
    for got, exp in zip(xs, expected, strict=True):
        assert abs(got - exp) < 0.5


def test_error_ticks_below_baseline() -> None:
    """Error ticks rise from the baseline DOWN into the axis margin — never up into
    the curve (the point of ticks: anchored to time, can't collide with the curve)."""
    layout = _layout()
    assert layout.error_ticks, "expected error ticks for the default error set"
    for t in layout.error_ticks:
        assert t.y1 == layout.plot_bottom  # starts at the baseline (y138)
        assert t.y2 > t.y1  # extends downward into the margin


def test_error_ticks_de_collided() -> None:
    """Clustered errors (same minute) de-collide to ≥ MIN_ERROR_GAP_PX apart."""
    layout = _layout(error_minutes=[50.0] * 6)
    xs = sorted(t.x for t in layout.error_ticks)
    for a, b in itertools.pairwise(xs):
        assert b - a >= MIN_ERROR_GAP_PX - 1e-6


def test_no_errors_no_ticks() -> None:
    """No errors → no ticks, no disclosure."""
    layout = _layout(error_minutes=[])
    assert layout.error_ticks == []
    assert layout.dropped_errors == 0


def test_error_tick_overflow_reports_dropped_not_clipped() -> None:
    """More ticks than fit the plot width are reported via dropped_errors."""
    minutes = [i * _ACTIVE_MIN / 400.0 for i in range(400)]
    layout = _layout(error_minutes=minutes)
    assert layout.dropped_errors > 0
    assert len(layout.error_ticks) + layout.dropped_errors == 400
    xs = sorted(t.x for t in layout.error_ticks)
    for a, b in itertools.pairwise(xs):
        assert b - a >= MIN_ERROR_GAP_PX - 1e-6


# --------------------------------------------------------------------------- #
# Time-tick adaptation                                                        #
# --------------------------------------------------------------------------- #


def test_time_ticks_origin_and_terminal() -> None:
    """span_min=157 → 0m origin (start-anchored) + terminal (end-anchored)."""
    layout = _layout()
    first, last = layout.time_ticks[0], layout.time_ticks[-1]
    assert first.label == "0m"
    assert first.label_anchor == "start"
    assert last.label == format_duration(_ACTIVE_MIN)  # "2.6h"
    assert last.label_anchor == "end"


@pytest.mark.parametrize("span_min", [1.0, 130.0, 648.0, 3334.0, 4000.0])
def test_adaptive_ticks_spaced_and_terminal(span_min: float) -> None:
    """For spans 1m-4000m: origin+terminal always present, all ≥ MIN gap apart."""
    layout = layout_context_load(
        events=[],
        window=200_000.0,
        peak_ctx=200_000.0,
        span_min=span_min,
        error_minutes=[],
        plot_box=_PLOT_BOX,
    )
    ticks = layout.time_ticks
    assert len(ticks) >= 2, f"missing origin/terminal for span_min={span_min}"
    if span_min >= 100.0:
        assert len(ticks) >= 3, f"too few ticks for span_min={span_min}"
    xs = [t.x for t in ticks]
    assert xs == sorted(xs)
    for a, b in itertools.pairwise(xs):
        assert b - a >= MIN_TICK_GAP_PX - 1e-6, f"ticks too close at span_min={span_min}"
    assert ticks[0].label == "0m"
    assert ticks[0].label_anchor == "start"
    assert ticks[-1].x == pytest.approx(layout.plot_right, abs=0.5)
    assert ticks[-1].label_anchor == "end"
    assert ticks[-1].label == format_duration(span_min)


def test_long_session_ticks_read_as_hours_days() -> None:
    """A 3334m codex session ticks in h/d, not raw minutes (no '3334m')."""
    layout = layout_context_load(
        events=[],
        window=258_400.0,
        peak_ctx=258_400.0,
        span_min=3334.0,
        error_minutes=[],
        plot_box=_PLOT_BOX,
    )
    labels = [t.label for t in layout.time_ticks]
    assert "0m" in labels
    assert labels[-1] == "2d 8h"
    assert not any(lbl.endswith("m") and lbl[:-1].isdigit() and len(lbl[:-1]) >= 4 for lbl in labels)


def test_terminal_tick_no_duplicate() -> None:
    """The terminal label appears exactly once even if a regular tick coincides."""
    layout = _layout(span_min=120.0, events=[], error_minutes=[])
    labels = [t.label for t in layout.time_ticks]
    assert labels.count(format_duration(120.0)) == 1


def test_small_span_collapses_to_endpoints() -> None:
    """A 5m session emits the 0m origin and the 5m terminal, no stray interior."""
    layout = _layout(span_min=5.0, events=[], error_minutes=[])
    labels = [t.label for t in layout.time_ticks]
    assert labels[0] == "0m"
    assert labels[-1] == "5m"
    assert all(t.x <= layout.plot_right + 0.5 for t in layout.time_ticks)


def test_interior_ticks_carry_gridlines_edges_do_not() -> None:
    """Interior ticks draw a faint full-height gridline; the 0m origin + terminal
    (which sit on the panel's left/right edges) draw only a mark."""
    layout = _layout(span_min=600.0, events=[])
    assert layout.time_ticks[0].gridline is False  # origin
    assert layout.time_ticks[-1].gridline is False  # terminal
    interior = layout.time_ticks[1:-1]
    assert interior, "expected interior ticks at span_min=600"
    assert all(t.gridline for t in interior)
    # The gridline spans the plot height (ceiling → baseline).
    g = interior[0]
    assert g.gridline_y1 == pytest.approx(layout.plot_top, abs=0.5)
    assert g.gridline_y2 == pytest.approx(layout.plot_bottom, abs=0.5)


# --------------------------------------------------------------------------- #
# Header + legend                                                             #
# --------------------------------------------------------------------------- #


def test_header_strings() -> None:
    """Header carries window/active/peak/reset-count strings."""
    layout = _layout()
    assert layout.header.eyebrow == "CONTEXT LOAD"
    assert "200K WINDOW" in layout.header.detail
    assert format_duration(_ACTIVE_MIN) in layout.header.detail  # "2.6h"
    assert "157m" not in layout.header.detail
    assert layout.header.peak_label == "196K PEAK"
    assert layout.header.resets_label == "4 RESETS"


def test_header_suppresses_reset_clause_when_zero() -> None:
    """0 resets → empty reset clause in the header."""
    layout = _layout(events=[], error_minutes=[])
    assert layout.header.resets_label == ""


def test_header_singular_reset() -> None:
    """Exactly 1 reset reads 'RESET' (no plural S)."""
    layout = _layout(events=[{"min": 40.0, "cmd": "clear", "to": 5_000.0}], error_minutes=[])
    assert layout.header.resets_label == "1 RESET"


def test_legend_items_measured_no_overlap() -> None:
    """Legend swatches advance past each measured label (monotonic x)."""
    layout = _layout()
    swatch_xs = [item.swatch_x for item in layout.legend]
    assert swatch_xs == sorted(swatch_xs)
    for prev, item in zip(layout.legend, layout.legend[1:], strict=False):
        assert item.swatch_x > prev.label_x


def test_legend_keys_only_ambiguous_marks() -> None:
    """Legend keys the marks a viewer can't read at a glance — the context curve,
    the 3 reset glyphs, and the error tick. The window-ceiling line is NOT keyed
    (its '1.0M' label + top position are self-evident), so the row stays uncrowded."""
    layout = _layout()
    assert [item.kind for item in layout.legend] == ["line", "compact", "clear", "auto", "error"]
    assert [item.label for item in layout.legend] == ["context", "compact", "clear", "auto-compact", "error"]
    assert "window ceiling" not in [item.label for item in layout.legend]


def test_legend_row_y() -> None:
    """Legend row sits at box_y + box_h + 23.4 (panel bottom 138 → ~161.4)."""
    layout = _layout()
    assert layout.legend_y == pytest.approx(161.4, abs=0.5)


# --------------------------------------------------------------------------- #
# Path integrity                                                              #
# --------------------------------------------------------------------------- #


def test_area_path_closed_to_baseline() -> None:
    """The area path closes (Z) and returns along the baseline."""
    layout = _layout()
    assert layout.area_path.endswith("Z")
    assert f",{layout.plot_bottom:.1f}" in layout.area_path


def test_line_path_open() -> None:
    """The line (stroke) path is not closed."""
    layout = _layout()
    assert not layout.line_path.endswith("Z")
    assert layout.line_path.startswith("M ")


def test_paths_stay_within_plot_bounds() -> None:
    """No path coordinate escapes the plot rectangle (x in [left,right], y in plot)."""
    layout = _layout()
    coords = re.findall(r"(-?\d+\.\d+),(-?\d+\.\d+)", layout.line_path)
    for x_str, y_str in coords:
        x, y = float(x_str), float(y_str)
        assert layout.plot_left - 0.5 <= x <= layout.plot_right + 0.5
        assert layout.plot_top - 0.5 <= y <= layout.plot_bottom + 0.5
