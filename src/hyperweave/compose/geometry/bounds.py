"""Axis-aligned bounds arithmetic shared by every layout judgement.

Segment tests are exact (Liang-Barsky slab clipping), never sampled. A
judgement that must consume a flattening error inflates the box by that
error before asking — see :mod:`.paths`.
"""

from __future__ import annotations

import math
from dataclasses import replace
from itertools import pairwise

from hyperweave.compose.spatial_records import RectSpec

Point = tuple[float, float]


def inflate(rect: RectSpec, margin: float) -> RectSpec:
    """Grow (or, with a negative margin, shrink) a rect on all four sides."""
    return replace(rect, x=rect.x - margin, y=rect.y - margin, w=rect.w + 2 * margin, h=rect.h + 2 * margin)


def union(a: RectSpec, b: RectSpec) -> RectSpec:
    x0, y0 = min(a.x, b.x), min(a.y, b.y)
    x1, y1 = max(a.x + a.w, b.x + b.w), max(a.y + a.h, b.y + b.h)
    return RectSpec(x=x0, y=y0, w=x1 - x0, h=y1 - y0, rx=a.rx)


def overlap_area(a: RectSpec, b: RectSpec) -> float:
    """The intersection AREA of two rects (0 = disjoint or edge-touching)."""
    ix = max(0.0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    iy = max(0.0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    return ix * iy


def intersects(a: RectSpec, b: RectSpec) -> bool:
    return overlap_area(a, b) > 0.0


def clamp_non_negative(rect: RectSpec) -> RectSpec:
    """A rect that can be emitted: no negative width or height ever reaches SVG."""
    if rect.w >= 0.0 and rect.h >= 0.0:
        return rect
    return replace(rect, w=max(0.0, rect.w), h=max(0.0, rect.h))


def _clip_params(a: Point, b: Point, rect: RectSpec, *, strict: bool = False) -> tuple[float, float] | None:
    """Liang-Barsky parameters ``(t0, t1)`` of ``a→b`` against the box, or
    None when the segment misses it. ``strict`` treats a segment lying along
    a face as outside — the open-interior reading an inside-length needs."""
    x0, y0, x1, y1 = rect.x, rect.y, rect.x + rect.w, rect.y + rect.h
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0.0:
            if q < 0.0 or (strict and q == 0.0):
                return None
            continue
        t = q / p
        if p < 0.0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
    if t0 > t1:
        return None
    return t0, t1


def segment_crosses_box(a: Point, b: Point, rect: RectSpec) -> bool:
    """Does the closed segment touch the closed box (boundary contact counts)?"""
    return _clip_params(a, b, rect) is not None


def segment_inside_length(a: Point, b: Point, rect: RectSpec, *, margin: float = 0.0) -> float:
    """Length of ``a→b`` strictly inside the box inflated by ``margin``.

    A wire that only touches a face measures zero; a wire that travels
    through the interior measures the distance it spent there.
    """
    box = inflate(rect, margin) if margin else rect
    if box.w <= 0.0 or box.h <= 0.0:
        return 0.0
    params = _clip_params(a, b, box, strict=True)
    if params is None:
        return 0.0
    t0, t1 = params
    if t1 <= t0:
        return 0.0
    return math.hypot(b[0] - a[0], b[1] - a[1]) * (t1 - t0)


def polyline_inside_length(points: list[Point] | tuple[Point, ...], rect: RectSpec, *, margin: float = 0.0) -> float:
    return sum(segment_inside_length(a, b, rect, margin=margin) for a, b in pairwise(points))


def polyline_crosses_box(points: list[Point] | tuple[Point, ...], rect: RectSpec, *, margin: float = 0.0) -> bool:
    return any(segment_inside_length(a, b, rect, margin=margin) > 0.0 for a, b in pairwise(points))


def point_to_segment_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    denom = dx * dx + dy * dy
    if denom == 0.0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / denom))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def point_to_polyline_distance(p: Point, points: list[Point] | tuple[Point, ...]) -> float:
    if len(points) == 1:
        return math.hypot(p[0] - points[0][0], p[1] - points[0][1])
    return min((point_to_segment_distance(p, a, b) for a, b in pairwise(points)), default=math.inf)
