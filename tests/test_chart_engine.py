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
    _build_x_year_labels,
    _format_y_tick,
    _nice_y_ticks,
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


def test_build_bezier_path_no_degenerate_segments_on_close_points() -> None:
    """When adjacent anchors are close in x, control handles must not cross.

    Regression for the chrome "flat-then-vertical" bug: the previous
    horizontal-handle implementation used ``dx = max(4, (x_cur - x_prev) // 3)``,
    which produced ``c2.x < c1.x`` when points were close. Catmull-Rom tangents
    scale with local chord length and avoid this.
    """
    import re

    # Points clustered tightly in x (simulates slow-growth early period).
    points = [(80, 410), (81, 390), (88, 368), (103, 348), (128, 325), (830, 169)]
    path = _build_bezier_path(points)
    segments = re.findall(r"C(\d+),(\d+) (\d+),(\d+) (\d+),(\d+)", path)
    assert len(segments) == len(points) - 1
    for c1x, _, c2x, _, _, _ in segments:
        assert int(c2x) >= int(c1x), f"degenerate segment: c1x={c1x}, c2x={c2x} (c2 must not precede c1)"


def test_build_bezier_path_tangents_follow_neighbor_slope() -> None:
    """Tangents should respect data slope — not force horizontal tangent at every anchor.

    With the old horizontal-handle approach, the first segment's c1 always had
    ``c1.y == y_prev``. For data that rises, the new Catmull-Rom code shifts c1
    toward the next point's y, producing a non-horizontal start.
    """
    # Rising data: y decreases (flipped SVG coords mean smaller y = higher on chart).
    points = [(0, 400), (100, 300), (200, 200), (300, 100)]
    path = _build_bezier_path(points)
    import re

    first_segment = re.match(r"M0,400 C(\d+),(\d+)", path)
    assert first_segment is not None
    c1y = int(first_segment.group(2))
    # Old code produced c1y == 400 (horizontal tangent). New code should
    # tilt toward y_next=300, so c1y < 400.
    assert c1y < 400, f"expected tangent to tilt upward, got c1y={c1y}"


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
    """Square (rect) markers carry crosshair geometry (half + cross) in the render dict."""
    out = _build_markers([(50, 50), (100, 200)], shape="square", size=10)
    # "square" is a legacy alias for "rect"; non-endpoint marker gets crosshair fields.
    assert out[0] == {
        "shape": "rect",
        "x": 50,
        "y": 50,
        "size": 10,
        "is_endpoint": False,
        "half": 5,
        "cross": 2,
    }
    # Final marker is the endpoint beacon (3-nested-square variant).
    assert out[-1]["is_endpoint"] is True
    assert out[-1]["shape"] == "rect"
    assert {"s1", "s2", "s3", "h1", "h2", "h3"} <= set(out[-1])


def test_build_markers_circle_emits_circle_radius() -> None:
    out = _build_markers([(50, 50), (100, 200)], shape="circle", size=6)
    # Non-endpoint circle carries r = size // 2, clamped >= 1.
    assert out[0] == {
        "shape": "circle",
        "x": 50,
        "y": 50,
        "size": 6,
        "is_endpoint": False,
        "r": 3,
    }
    # Circle has no dedicated endpoint partial; falls back to rect endpoint.
    assert out[-1]["shape"] == "rect"
    assert out[-1]["is_endpoint"] is True


def test_build_markers_diamond_emits_rotation_geometry() -> None:
    """Diamond markers carry half for the rotated-rect partial."""
    out = _build_markers([(50, 50), (100, 200)], shape="diamond", size=4)
    assert out[0]["shape"] == "diamond"
    assert out[0]["is_endpoint"] is False
    assert out[0]["half"] == 2
    # Final diamond is the endpoint (chrome 2-layer rotated rects).
    assert out[-1]["shape"] == "diamond"
    assert out[-1]["is_endpoint"] is True
    assert {"s1", "s2", "h1", "h2"} <= set(out[-1])


def test_build_markers_endpoint_is_last_only() -> None:
    """Only the final entry is the endpoint; the rest are regular markers."""
    out = _build_markers([(10, 10), (20, 20), (30, 30)], shape="square", size=10)
    assert len(out) == 3
    assert sum(1 for m in out if m["is_endpoint"]) == 1
    assert out[-1]["is_endpoint"] is True
    assert all(not m["is_endpoint"] for m in out[:-1])


def test_build_markers_empty_returns_empty_list() -> None:
    assert _build_markers([], shape="rect", size=5) == []


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
    assert isinstance(out, list)
    labels = [ms["label"] for ms in out]
    # With sample_viewport ~600px wide and points spread across 4 timestamps, all
    # three thresholds cross at well-spaced x positions → none get de-overlapped.
    assert "500" in labels
    assert "1K" in labels
    assert "2K" in labels
    # Structural guarantees every milestone dict needs
    for ms in out:
        assert {"x", "y", "bottom_y", "label", "value"} <= set(ms)


def test_build_milestones_empty_when_no_thresholds(sample_viewport: Viewport) -> None:
    pts = _normalize_points([{"date": "2025-01-01", "count": 100}])
    projected = _project_points(pts, sample_viewport)
    assert _build_milestones(pts, projected, sample_viewport, thresholds=[]) == []


def test_build_milestones_deoverlaps_clustered_crossings(sample_viewport: Viewport) -> None:
    """When multiple thresholds cross on nearly-adjacent x positions, only the
    first one in each cluster survives — prevents the openclaw-style
    '500/1K/5K/10K all stacked on top of each other' illegibility."""
    # Two data points very close in x so all crossings cluster in the gap.
    pts = _normalize_points(
        [
            {"date": "2025-01-01", "count": 100},
            {"date": "2025-01-02", "count": 20000},  # one-day jump through all thresholds
        ],
    )
    projected = _project_points(pts, sample_viewport)
    thresholds = [500, 1000, 2000, 5000, 10000, 15000]
    out = _build_milestones(pts, projected, sample_viewport, thresholds=thresholds)
    # All 6 crossings happen in one tight cluster; de-overlap keeps ≤ 2 labels.
    assert 1 <= len(out) <= 2
    # The surviving label(s) must be the first crossing (lowest threshold
    # value) — we keep oldest, drop the pileup following it.
    assert out[0]["value"] == 500


def test_build_milestones_keeps_all_when_well_spaced(sample_viewport: Viewport) -> None:
    """Milestones spread out beyond 40px pixel gap should all survive de-overlap."""
    # Four data points, one per crossing, evenly spaced across the viewport.
    pts = _normalize_points(
        [
            {"date": "2025-01-01", "count": 100},
            {"date": "2025-04-01", "count": 600},  # crosses 500
            {"date": "2025-07-01", "count": 1200},  # crosses 1000
            {"date": "2025-10-01", "count": 2500},  # crosses 2000
        ],
    )
    projected = _project_points(pts, sample_viewport)
    out = _build_milestones(pts, projected, sample_viewport, thresholds=[500, 1000, 2000])
    assert len(out) == 3  # all three crossings survive


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
    # polyline is now a structured dict; miter selects polyline kind.
    assert result["polyline"]["kind"] == "polyline"
    assert "points" in result["polyline"]
    # area is structured too; solid-area selects polygon kind.
    assert result["area"]["kind"] == "polygon"
    assert "points" in result["area"]
    # markers stays list[dict] (v0.2.7 contract unchanged).
    assert isinstance(result["markers"], list)
    assert result["markers"]
    assert all(m["shape"] == "rect" for m in result["markers"])


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
    # Round linejoin → path kind; smooth fill → path area too.
    assert result["polyline"]["kind"] == "path"
    assert "d" in result["polyline"]
    assert result["area"]["kind"] == "path"
    assert "Z" in result["area"]["d"]  # closed path
    assert isinstance(result["markers"], list)
    assert all(m["shape"] == "diamond" for m in result["markers"])


def test_build_chart_svg_empty_points_safe(sample_viewport: Viewport) -> None:
    """No points → data specs are None/empty, but scaffolding still present."""
    result = build_chart_svg([], sample_viewport, structural={})
    assert result["area"] is None
    assert result["polyline"] is None
    assert result["markers"] == []
    # Axes and gridlines are always drawn regardless of data.
    assert len(result["axes"]) == 2  # L-frame = 2 lines
    assert len(result["gridlines"]) > 0
    # Empty-state: labels collapse to a single "0" on the baseline, no X labels,
    # and no overlay unless the caller requested one.
    assert len(result["y_labels"]) == 1
    assert result["y_labels"][0]["text"] == "0"
    assert result["x_labels"] == []
    assert result["empty_state"] is None


def test_build_chart_svg_empty_with_message_renders_overlay(
    sample_viewport: Viewport,
) -> None:
    """Zero-data path with an empty_message emits a structured empty-state dict."""
    result = build_chart_svg([], sample_viewport, structural={}, empty_message="NEW REPO · NO STARS YET")
    assert result["empty_state"] is not None
    assert result["empty_state"]["text"] == "NEW REPO · NO STARS YET"
    assert "x" in result["empty_state"]
    assert "y" in result["empty_state"]


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
    assert isinstance(result["milestones"], list)
    assert len(result["milestones"]) >= 1


# ── Nice ticks (Y-axis tick computation) ─────────────────────────────


@pytest.mark.parametrize(
    "v_max,expected",
    [
        (0, [0]),
        (1, [0, 1]),
        (6, [0, 2, 4, 6]),
        (30, [0, 10, 20, 30]),
        (2850, [0, 1000, 2000, 3000]),
        (15000, [0, 5000, 10000, 15000]),
    ],
)
def test_nice_y_ticks_across_bands(v_max: int, expected: list[int]) -> None:
    """Tick algorithm produces round values from 0 up to >= v_max across orders of magnitude."""
    assert _nice_y_ticks(v_max) == expected


def test_format_y_tick_integer_and_k_notation() -> None:
    """< 1000 → integer; 1000..9999 → K notation with no trailing zeros; 10K+ → integer K."""
    assert _format_y_tick(0) == "0"
    assert _format_y_tick(6) == "6"
    assert _format_y_tick(500) == "500"
    assert _format_y_tick(1000) == "1K"
    assert _format_y_tick(1500) == "1.5K"
    assert _format_y_tick(2000) == "2K"
    assert _format_y_tick(10000) == "10K"


# ── X-axis year labels ────────────────────────────────────────────────


def test_x_year_labels_single_year(sample_viewport: Viewport) -> None:
    """Data entirely within one year → one label centered on the viewport."""
    pts = _normalize_points(
        [
            {"date": "2025-01-15", "count": 1},
            {"date": "2025-06-01", "count": 4},
            {"date": "2025-11-20", "count": 6},
        ]
    )
    labels = _build_x_year_labels(pts, sample_viewport)
    assert labels == [
        {
            "x": sample_viewport.x + sample_viewport.w // 2,
            "text": "2025",
            "anchor": "middle",
        }
    ]


def test_x_year_labels_multi_year_range(sample_viewport: Viewport) -> None:
    """Three-year span → start year at left, interior years at jan-1 positions."""
    pts = _normalize_points(
        [
            {"date": "2024-01-01", "count": 1},
            {"date": "2025-06-01", "count": 100},
            {"date": "2026-04-01", "count": 500},
        ]
    )
    labels = _build_x_year_labels(pts, sample_viewport)
    texts = [label["text"] for label in labels]
    # Expect every year in the range represented exactly once.
    assert texts == ["2024", "2025", "2026"]
    # Start year anchored at left, subsequent labels middle/end.
    assert labels[0]["anchor"] == "start"
    assert labels[0]["x"] == sample_viewport.x


def test_x_year_labels_empty_points() -> None:
    """No points → no labels (caller should render an empty-state overlay instead)."""
    vp = Viewport(x=0, y=0, w=100, h=50)
    assert _build_x_year_labels([], vp) == []


# ── Zero-time-span defense (bug 2 reproducer) ────────────────────────


def test_project_points_identical_timestamps_distributes_by_index(
    sample_viewport: Viewport,
) -> None:
    """All-same-timestamp points must not collapse to vp.x (bug 2 defense)."""
    same_date = datetime(2025, 5, 1, tzinfo=UTC)
    pts = [ChartPoint(date=same_date, value=i + 1) for i in range(4)]
    projected = _project_points(pts, sample_viewport)
    xs = [x for (x, _) in projected]
    # All x coords must be distinct — evenly spread across the viewport width.
    assert len(set(xs)) == 4
    # First point at left edge, last at right edge.
    assert xs[0] == sample_viewport.x
    assert xs[-1] == sample_viewport.x + sample_viewport.w


def test_project_points_v_min_override_uses_zero_baseline(
    sample_viewport: Viewport,
) -> None:
    """v_min=0 override means low-value points sit partway up, not at the baseline."""
    pts = _normalize_points(
        [
            {"date": "2025-01-01", "count": 100},
            {"date": "2025-12-01", "count": 200},
        ]
    )
    with_override = _project_points(pts, sample_viewport, v_min=0, v_max=1000)
    without_override = _project_points(pts, sample_viewport)
    # Without override: first point (value=100, data_min=100) sits at baseline.
    assert without_override[0][1] == sample_viewport.y + sample_viewport.h
    # With v_min=0, v_max=1000: value=100 is 10% of range, so sits 90% down from top.
    assert with_override[0][1] < sample_viewport.y + sample_viewport.h
    assert with_override[0][1] > sample_viewport.y


# ── Zero-star truthfulness: no placeholder leakage ───────────────────


def test_build_chart_svg_no_placeholder_1200_leak(sample_viewport: Viewport) -> None:
    """Zero-data renders must never leak the old 120→1200 placeholder numbers."""
    result = build_chart_svg([], sample_viewport, structural={})
    rendered = "".join(str(v) for v in result.values())
    assert "1200" not in rendered
    assert "1,200" not in rendered
