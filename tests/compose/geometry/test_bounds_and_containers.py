"""Bounds arithmetic and the container-inclusion law."""

from __future__ import annotations

import math

from hyperweave.compose.geometry.bounds import (
    clamp_non_negative,
    inflate,
    intersects,
    overlap_area,
    point_to_polyline_distance,
    segment_inside_length,
    union,
)
from hyperweave.compose.geometry.containers import container_width
from hyperweave.compose.spatial_records import RectSpec


def test_inflate_and_union() -> None:
    r = RectSpec(x=10.0, y=10.0, w=20.0, h=10.0, rx=4.0)
    assert inflate(r, 2.0) == RectSpec(x=8.0, y=8.0, w=24.0, h=14.0, rx=4.0)
    assert inflate(r, -2.0) == RectSpec(x=12.0, y=12.0, w=16.0, h=6.0, rx=4.0)
    assert union(r, RectSpec(x=0.0, y=25.0, w=5.0, h=5.0)) == RectSpec(x=0.0, y=10.0, w=30.0, h=20.0, rx=4.0)


def test_overlap_area_treats_touching_as_disjoint() -> None:
    a = RectSpec(x=0.0, y=0.0, w=10.0, h=10.0)
    assert overlap_area(a, RectSpec(x=10.0, y=0.0, w=10.0, h=10.0)) == 0.0
    assert overlap_area(a, RectSpec(x=5.0, y=5.0, w=10.0, h=10.0)) == 25.0
    assert intersects(a, RectSpec(x=9.0, y=9.0, w=1.0, h=1.0)) is True


def test_clamp_non_negative_never_emits_a_negative_rect() -> None:
    assert clamp_non_negative(RectSpec(x=0.0, y=0.0, w=-3.58, h=4.0)) == RectSpec(x=0.0, y=0.0, w=0.0, h=4.0)
    ok = RectSpec(x=0.0, y=0.0, w=3.0, h=4.0)
    assert clamp_non_negative(ok) is ok


def test_segment_inside_length_with_margin_and_degenerate_boxes() -> None:
    box = RectSpec(x=0.0, y=0.0, w=10.0, h=10.0)
    assert math.isclose(segment_inside_length((-5.0, 5.0), (15.0, 5.0), box), 10.0)
    assert math.isclose(segment_inside_length((-5.0, 5.0), (15.0, 5.0), box, margin=1.0), 12.0)
    assert segment_inside_length((-5.0, 5.0), (15.0, 5.0), box, margin=-6.0) == 0.0


def test_point_to_polyline_distance() -> None:
    assert point_to_polyline_distance((5.0, 3.0), [(0.0, 0.0), (10.0, 0.0)]) == 3.0
    assert point_to_polyline_distance((5.0, 3.0), [(0.0, 0.0)]) > 5.0


def test_container_width_is_the_max_of_members_furniture_and_floor() -> None:
    assert container_width(members_w=200.0, furniture_ink=225.0, pads=24.0, air=16.0, floor=120.0) == 265.0
    assert container_width(members_w=300.0, furniture_ink=100.0, pads=24.0) == 300.0
    assert container_width(members_w=50.0, furniture_ink=20.0, pads=10.0, floor=144.0) == 144.0
