"""Tests for the chart engine (Session 2A+2B Phase 4).

Covers point normalization, projection, polyline/bezier path building,
marker shape dispatch, and the public ``build_chart_svg`` entry point.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hyperweave.render.chart_engine import (
    ChartPoint,
    Viewport,
    _build_area_path,
    _build_area_polygon_points,
    _build_bezier_path,
    _build_markers,
    _build_milestones,
    _build_polyline_points,
    _normalize_points,
    _project_points,
    build_chart_svg,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def sample_viewport() -> Viewport:
    return Viewport(x=100, y=100, w=600, h=200)


@pytest.fixture()
def sample_points_dict() -> list[dict[str, object]]:
    """Six evenly-spaced points with a growing star count."""
    return [
        {"date": "2025-01-01", "count": 100},
        {"date": "2025-04-01", "count": 320},
        {"date": "2025-07-01", "count": 680},
        {"date": "2025-10-01", "count": 1200},
        {"date": "2026-01-01", "count": 2100},
        {"date": "2026-04-01", "count": 2850},
    ]


# ── _normalize_points ─────────────────────────────────────────────────


def test_normalize_points_dict_form(sample_points_dict: list[dict[str, object]]) -> None:
    pts = _normalize_points(sample_points_dict)
    assert len(pts) == 6
    assert pts[0].value == 100
    assert pts[-1].value == 2850
    # Sorted chronologically
    assert all(pts[i].date <= pts[i + 1].date for i in range(len(pts) - 1))


def test_normalize_points_accepts_tuples() -> None:
    pts = _normalize_points(
        [
            (datetime(2025, 1, 1, tzinfo=UTC), 100),
            (datetime(2025, 6, 1, tzinfo=UTC), 500),
        ],
    )
    assert len(pts) == 2
    assert pts[0].value == 100
    assert pts[1].value == 500


def test_normalize_points_skips_invalid_entries() -> None:
    pts = _normalize_points(
        [
            {"date": "2025-01-01", "count": 100},
            "not a dict",
            {"date": "invalid-date", "count": 200},  # unparseable, skipped
            {"date": "2025-06-01", "count": "not-a-number"},  # bad value, skipped
            {"date": "2025-12-01", "count": 500},
        ],
    )
    # Only the two valid entries survive.
    assert len(pts) == 2
    assert [p.value for p in pts] == [100, 500]


def test_normalize_points_handles_z_suffix() -> None:
    pts = _normalize_points([{"date": "2025-01-01T00:00:00Z", "count": 42}])
    assert len(pts) == 1
    assert pts[0].date.tzinfo is not None


# ── _project_points ───────────────────────────────────────────────────


def test_project_points_empty_returns_empty(sample_viewport: Viewport) -> None:
    assert _project_points([], sample_viewport) == []


def test_project_points_single_returns_center(sample_viewport: Viewport) -> None:
    pt = ChartPoint(date=datetime(2025, 6, 1, tzinfo=UTC), value=500)
    out = _project_points([pt], sample_viewport)
    assert out == [(400, 200)]  # center of the viewport


def test_project_points_range_hits_corners(
    sample_viewport: Viewport,
    sample_points_dict: list[dict[str, object]],
) -> None:
    pts = _normalize_points(sample_points_dict)
    projected = _project_points(pts, sample_viewport)
    # First point starts at left edge of viewport.
    assert projected[0][0] == sample_viewport.x
    # Last point ends at right edge.
    assert projected[-1][0] == sample_viewport.x + sample_viewport.w
    # Max-value point should sit at the top of the viewport (flipped Y).
    assert projected[-1][1] == sample_viewport.y
    # Min-value point should sit at the bottom.
    assert projected[0][1] == sample_viewport.y + sample_viewport.h


# ── Path builders ─────────────────────────────────────────────────────


def test_build_polyline_points() -> None:
    out = _build_polyline_points([(10, 20), (30, 40), (50, 60)])
    assert out == "10,20 30,40 50,60"


def test_build_polyline_points_empty() -> None:
    assert _build_polyline_points([]) == ""


def test_build_bezier_path_starts_with_M() -> None:
    out = _build_bezier_path([(10, 20), (30, 40), (50, 60)])
    assert out.startswith("M10,20")
    assert "C" in out  # cubic bezier control points present


def test_build_area_polygon_closes_to_baseline() -> None:
    pts = [(10, 50), (30, 30), (50, 20)]
    out = _build_area_polygon_points(pts, baseline_y=100)
    # Appends (last_x, baseline) then (first_x, baseline) to close the shape.
    assert "50,100" in out
    assert "10,100" in out


def test_build_area_path_closes_with_L_commands() -> None:
    pts = [(10, 50), (30, 30), (50, 20)]
    out = _build_area_path(pts, baseline_y=100)
    assert out.endswith("Z")
    assert " L50,100" in out
    assert " L10,100" in out


# ── Marker builders ───────────────────────────────────────────────────


def test_build_markers_square_emits_crosshair() -> None:
    """Square markers produce crosshair groups (rect + two lines) per target SVG."""
    out = _build_markers([(50, 50), (100, 200)], shape="square", size=10)
    assert "<rect" in out
    # Non-final marker: translate-centered group with crosshair lines.
    assert 'translate(50,50)' in out
    assert 'width="10"' in out
    assert "<line" in out  # crosshair lines present
    # Final marker: endpoint beacon (nested squares).
    assert 'data-hw-zone="endpoint"' in out


def test_build_markers_circle_emits_circle() -> None:
    out = _build_markers([(50, 50), (100, 200)], shape="circle", size=6)
    assert "<circle" in out
    assert 'r="3"' in out


def test_build_markers_diamond_emits_rotated_rect() -> None:
    """Diamond markers produce translate+rotate centered rects per target SVG."""
    out = _build_markers([(50, 50), (100, 200)], shape="diamond", size=4)
    assert "<rect" in out
    # Non-final diamond centered with translate + rotate.
    assert "translate(50 50) rotate(45)" in out
    # Final diamond: endpoint beacon with glow class.
    assert 'data-hw-zone="endpoint"' in out


def test_build_markers_endpoint_is_structurally_different() -> None:
    """The last marker uses a different builder — it's the 'now' beacon."""
    out = _build_markers([(10, 10), (20, 20), (30, 30)], shape="square", size=10)
    # Endpoint has nested rects (3 concentric squares for brutalist).
    assert 'data-hw-zone="endpoint"' in out
    assert out.count('data-hw-zone="endpoint"') == 1


# ── Milestones ────────────────────────────────────────────────────────


def test_build_milestones_marks_crossings(sample_viewport: Viewport) -> None:
    pts = _normalize_points(
        [
            {"date": "2025-01-01", "count": 100},
            {"date": "2025-06-01", "count": 600},  # crosses 500
            {"date": "2025-12-01", "count": 1100},  # crosses 1000
            {"date": "2026-06-01", "count": 2500},  # crosses 2000
        ],
    )
    projected = _project_points(pts, sample_viewport)
    out = _build_milestones(pts, projected, sample_viewport, thresholds=[500, 1000, 2000])
    assert ">500</text>" in out or ">5" in out  # tolerant of compact label format
    assert ">1K</text>" in out
    assert ">2K</text>" in out


def test_build_milestones_empty_when_no_thresholds(sample_viewport: Viewport) -> None:
    pts = _normalize_points([{"date": "2025-01-01", "count": 100}])
    projected = _project_points(pts, sample_viewport)
    assert _build_milestones(pts, projected, sample_viewport, thresholds=[]) == ""


# ── build_chart_svg (public entry point) ──────────────────────────────


def test_build_chart_svg_miter_angular(
    sample_viewport: Viewport,
    sample_points_dict: list[dict[str, object]],
) -> None:
    """Brutalist-style chart: polyline with miter joins, square markers, solid area."""
    result = build_chart_svg(
        sample_points_dict,
        sample_viewport,
        structural={
            "stroke_linejoin": "miter",
            "data_point_shape": "square",
            "data_point_size": 5,
            "fill_density": "solid-area",
        },
    )
    assert "<polyline" in result["polyline"]
    assert "stroke-linejoin=\"miter\"" in result["polyline"]
    assert "<polygon" in result["area"]
    assert "<rect" in result["markers"]


def test_build_chart_svg_round_smooth(
    sample_viewport: Viewport,
    sample_points_dict: list[dict[str, object]],
) -> None:
    """Chrome-style chart: bezier path, diamond markers, smooth gradient area."""
    result = build_chart_svg(
        sample_points_dict,
        sample_viewport,
        structural={
            "stroke_linejoin": "round",
            "data_point_shape": "diamond",
            "data_point_size": 6,
            "fill_density": "bezier-smooth",
        },
    )
    assert "<path" in result["polyline"]
    assert "rotate(45" in result["markers"]
    # Smooth area path ends with Z (closed).
    assert "Z" in result["area"]


def test_build_chart_svg_empty_points_safe(sample_viewport: Viewport) -> None:
    """No points → all fragments empty strings, no exceptions."""
    result = build_chart_svg([], sample_viewport, structural={})
    for key in ("area", "polyline", "markers"):
        assert result[key] == ""
    # Axes and gridlines are always drawn regardless of data.
    assert result["axes"] != ""
    assert result["gridlines"] != ""


def test_build_chart_svg_respects_milestones(
    sample_viewport: Viewport,
    sample_points_dict: list[dict[str, object]],
) -> None:
    result = build_chart_svg(
        sample_points_dict,
        sample_viewport,
        structural={"stroke_linejoin": "miter"},
        milestones=[500, 1000, 2000],
    )
    assert "milestones" in result
    assert result["milestones"] != ""
