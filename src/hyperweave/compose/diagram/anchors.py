"""Shape-true connector anchoring.

A connector must end ON the node it meets — at the actual boundary of the
node's SHAPE (rect, circle, or pill) plus one uniform standoff constant
(``connector_standoff`` in data/config/diagram-frame.yaml; the specimens touch, so it
ships at 0). The circle-only assumption this replaces left dead gaps on
left/right approaches to rect cards: a card's half-WIDTH governed arcs
that approached its half-HEIGHT side.

Two primitives: ``boundary_anchor`` intersects the ray from a node's
center toward an external point with the node boundary (so spokes land
where they aim), and ``trim_arc_angle`` numerically finds where a circular
arc crosses a node's boundary + standoff (fixed-iteration bisection —
deterministic).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from hyperweave.compose.diagram.paths import point_on

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import NodePlacement
    from hyperweave.compose.spatial_records import RectSpec


def _center(p: NodePlacement) -> tuple[float, float]:
    if p.shape == "circle":
        return (p.cx, p.cy)
    b = p.box
    return (b.x + b.w / 2, b.y + b.h / 2)


def rect_distance(cx: float, cy: float, w: float, h: float, rx: float, x: float, y: float) -> float:
    """Signed distance from (x, y) to a rounded rect centered at (cx, cy):
    distance to the rect shrunk by rx, minus rx (negative inside)."""
    rx = min(rx, w / 2, h / 2)
    hx, hy = w / 2 - rx, h / 2 - rx
    qx, qy = abs(x - cx) - hx, abs(y - cy) - hy
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
    inside = min(max(qx, qy), 0.0)
    return outside + inside - rx


def _boundary_box(p: NodePlacement) -> RectSpec:
    """The rect a rect-shaped node's boundary is actually measured against:
    the terminal ring's outer face (``term_box``) when the node carries one
    — a state-machine final's ring is its TRUE outer face, 6px past the
    plain card on every side (graph.py computes it before any arrival
    resolves) — else the plain card box. Circles never carry a ``term_box``,
    so this is a no-op there (the ``shape == "circle"`` branches above never
    call it). The one primitive both ``boundary_distance`` and
    ``side_anchor`` read, so an arrival/label boundary check can no longer
    silently disagree about which face is the real one (recenter.py's own
    ``term_box=... if n.term_box is not None else None`` translation is the
    same presence check, applied to geometry instead of a boundary query)."""
    return p.term_box if p.term_box is not None else p.box


def boundary_distance(p: NodePlacement, x: float, y: float) -> float:
    """Signed distance from a point to the node boundary (negative inside)."""
    cx, cy = _center(p)
    if p.shape == "circle":
        return math.hypot(x - cx, y - cy) - p.r
    b = _boundary_box(p)
    return rect_distance(cx, cy, b.w, b.h, b.rx, x, y)


def boundary_anchor(p: NodePlacement, from_x: float, from_y: float, standoff: float) -> tuple[float, float]:
    """Where a straight connector from ``(from_x, from_y)`` lands on the
    node: the ray center -> source crosses the boundary, backed off by the
    standoff. Falls back to the center for degenerate zero-length rays."""
    cx, cy = _center(p)
    dx, dy = from_x - cx, from_y - cy
    dist = math.hypot(dx, dy)
    if dist == 0:
        return (cx, cy)
    ux, uy = dx / dist, dy / dist
    # March the SDF root along the ray (boundary distance is monotone
    # outward from the center): bisect t in [0, dist].
    lo, hi = 0.0, dist
    for _ in range(28):
        mid = (lo + hi) / 2
        if boundary_distance(p, cx + ux * mid, cy + uy * mid) < standoff:
            lo = mid
        else:
            hi = mid
    t = (lo + hi) / 2
    return (cx + ux * t, cy + uy * t)


def side_anchor(
    p: NodePlacement,
    *,
    side: str,
    at: float,
    standoff: float = 0.0,
) -> tuple[float, float]:
    """Boundary crossing of the axis-aligned approach line through ``at``.

    ``side`` names the node face the connector meets (``left``/``right`` take
    ``at`` as the approach y; ``top``/``bottom`` take it as the approach x).
    Exact-equivalent to the bbox extent for straight-sided rects — so rect
    layouts are byte-stable — while circles and pill caps resolve to the true
    rim instead of the bounding-box corner void (the 4.5px floating-arrowhead
    class). ``at`` is clamped into the shape's usable band so the line always
    intersects."""
    cx, cy = _center(p)
    b = _boundary_box(p)
    if side in ("left", "right"):
        half_band = (p.r if p.shape == "circle" else b.h / 2) - 1.0
        y = min(max(at, cy - half_band), cy + half_band)
        sign = 1.0 if side == "right" else -1.0
        reach = (p.r if p.shape == "circle" else b.w / 2) + standoff + 2.0
        lo, hi = 0.0, reach
        for _ in range(28):
            mid = (lo + hi) / 2
            if boundary_distance(p, cx + sign * mid, y) < standoff:
                lo = mid
            else:
                hi = mid
        return (cx + sign * (lo + hi) / 2, y)
    half_band = (p.r if p.shape == "circle" else b.w / 2) - 1.0
    x = min(max(at, cx - half_band), cx + half_band)
    sign = 1.0 if side == "bottom" else -1.0
    reach = (p.r if p.shape == "circle" else b.h / 2) + standoff + 2.0
    lo, hi = 0.0, reach
    for _ in range(28):
        mid = (lo + hi) / 2
        if boundary_distance(p, x, cy + sign * mid) < standoff:
            lo = mid
        else:
            hi = mid
    return (x, cy + sign * (lo + hi) / 2)


def trim_arc_angle(
    p: NodePlacement,
    *,
    arc_cx: float,
    arc_cy: float,
    arc_r: float,
    node_angle_deg: float,
    direction: int,
    standoff: float,
    max_delta_deg: float = 60.0,
) -> float:
    """The angle where an arc leaving a node at ``node_angle_deg`` clears
    the node's actual boundary + standoff (``direction`` +1 clockwise from
    the node, -1 approaching it). Replaces the angular half-width formula
    that treated every card as a circle of radius w/2."""

    def clearance(delta: float) -> float:
        ax, ay = point_on(arc_cx, arc_cy, arc_r, node_angle_deg + direction * delta)
        return boundary_distance(p, ax, ay)

    lo, hi = 0.0, max_delta_deg
    if clearance(hi) < standoff:  # node wider than the search window — cap
        return node_angle_deg + direction * max_delta_deg
    for _ in range(28):
        mid = (lo + hi) / 2
        if clearance(mid) < standoff:
            lo = mid
        else:
            hi = mid
    return node_angle_deg + direction * (lo + hi) / 2
