"""Flattening is bounded, exact tests consume the bound, and the legacy
sampler shape is reproducible on demand."""

from __future__ import annotations

import math
from itertools import pairwise

from hyperweave.compose.geometry.bounds import (
    polyline_crosses_box,
    polyline_inside_length,
    segment_crosses_box,
    segment_inside_length,
)
from hyperweave.compose.geometry.paths import FLATTEN_TOL, flatten, flatten_points, polyline_length
from hyperweave.compose.spatial_records import RectSpec


def _cubic(p0, c1, c2, p3, t):
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * p3[1],
    )


def _dist_to_polyline(p, pts):
    best = math.inf
    for a, b in pairwise(pts):
        dx, dy = b[0] - a[0], b[1] - a[1]
        denom = dx * dx + dy * dy or 1.0
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / denom))
        best = min(best, math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy)))
    return best


def test_cubic_flattening_stays_within_tolerance() -> None:
    p0, c1, c2, p3 = (0.0, 0.0), (300.0, 0.0), (0.0, 200.0), (300.0, 200.0)
    pts = flatten_points("M 0,0 C 300,0 0,200 300,200")
    assert pts[0] == p0 and pts[-1] == p3
    for k in range(1, 400):
        assert _dist_to_polyline(_cubic(p0, c1, c2, p3, k / 400), pts) <= FLATTEN_TOL + 1e-6


def test_arc_flattening_stays_within_tolerance() -> None:
    pts = flatten_points("M 100,0 A 100,100 0 0 1 0,100")
    assert math.isclose(pts[-1][0], 0.0, abs_tol=1e-9) and math.isclose(pts[-1][1], 100.0, abs_tol=1e-9)
    for a, b in pairwise(pts):
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        assert abs(100.0 - math.hypot(mid[0], mid[1])) <= FLATTEN_TOL + 1e-6


def test_legacy_sampler_shape_is_reproducible() -> None:
    pts = flatten_points("M 0,0 C 100,0 100,100 200,100 A 20,20 0 0 1 240,140", curve_samples=16)
    assert len(pts) == 1 + 16 + 1


def test_relative_and_closed_subpaths_flatten() -> None:
    subpaths = flatten("M 10,10 l 20,0 l 0,20 z M 50,50 L 60,60")
    assert len(subpaths) == 2
    assert subpaths[0][-1] == (10.0, 10.0)
    assert subpaths[1] == [(50.0, 50.0), (60.0, 60.0)]


def test_exact_clip_measures_axis_aligned_legs_through_a_card() -> None:
    card = RectSpec(x=30.0, y=188.0, w=150.0, h=54.0)
    assert math.isclose(segment_inside_length((105.0, 162.0), (105.0, 268.0), card), 54.0)
    assert segment_inside_length((30.0, 100.0), (30.0, 300.0), card) == 0.0
    assert segment_crosses_box((30.0, 100.0), (30.0, 300.0), card) is True


def test_a_grazing_curve_that_the_chord_misses_is_caught_with_the_inflated_box() -> None:
    """The chord from (0,0) to (200,0) clears the box; the true curve bulges
    to y = 15 and enters it. Flattened within FLATTEN_TOL and tested against
    the box inflated by that tolerance, the crossing is found."""
    box = RectSpec(x=80.0, y=12.0, w=40.0, h=40.0)
    d = "M 0,0 C 60,20 140,20 200,0"
    chord = [(0.0, 0.0), (200.0, 0.0)]
    assert polyline_crosses_box(chord, box) is False
    pts = flatten_points(d)
    assert polyline_crosses_box(pts, box, margin=FLATTEN_TOL) is True
    assert polyline_inside_length(pts, box) > 0.0


def test_polyline_length_sums_legs() -> None:
    assert polyline_length([(0.0, 0.0), (3.0, 4.0), (3.0, 10.0)]) == 11.0
