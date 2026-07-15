"""Connector grammar — the routing layer above ``paths.py``/``anchors.py``.

A solver knows WHERE two nodes sit; this module turns that into the wire
between them under one vocabulary: an exit point on a node's boundary, a
routed path (straight | curved | orthogonal), a self-loop cubic, and a drawn
arrowhead. Every builder returns geometry PLUS the two quantities the later
passes need: an exact ``length`` (for the K1 speed law) and an
``end_tangent`` (the unit direction the wire arrives travelling, so an
arrowhead points correctly and the annotate/collide pass can lift a label
off the connector). Lengths are exact for lines/arcs/orthogonals and a
fixed-step polyline for cubics -- deterministic by construction, matching the
``paths.py`` discipline (no adaptive subdivision).

Markers are DRAWN chevrons, never SVG ``<marker>`` elements: the diagram
frame's direction_device doctrine (``core/paradigm.py``) keeps every artifact
an inert document whose ornament is baked geometry.
"""

from __future__ import annotations

import itertools
import math
from typing import TYPE_CHECKING

from hyperweave.compose.diagram.paths import (
    chord_unit,
    cubic_len,
    fmt,
    line_d,
    line_len,
    point_on,
    s_curve_h,
    s_curve_h_len,
    s_curve_v,
    s_curve_v_len,
)

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import NodePlacement

Vec = tuple[float, float]

# Which axis a compass side leaves along, and its outward unit normal. Shared
# by exit_point and self_loop so a side name resolves to geometry in one place.
_SIDE_NORMAL: dict[str, Vec] = {
    "top": (0.0, -1.0),
    "bottom": (0.0, 1.0),
    "left": (-1.0, 0.0),
    "right": (1.0, 0.0),
}


def _norm(dx: float, dy: float) -> Vec:
    """Unit vector, degenerate-safe (zero-length -> +x)."""
    d = math.hypot(dx, dy)
    if d == 0:
        return (1.0, 0.0)
    return (dx / d, dy / d)


def _perp(u: Vec) -> Vec:
    """Left-hand perpendicular (90 deg CCW): the chevron's spread axis."""
    return (-u[1], u[0])


def _center(p: NodePlacement) -> Vec:
    if p.shape == "circle":
        return (p.cx, p.cy)
    b = p.box
    return (b.x + b.w / 2, b.y + b.h / 2)


def exit_point(p: NodePlacement, side: str, *, standoff: float = 0.0) -> Vec:
    """The point a connector leaves ``p`` on the named side, backed off by
    ``standoff``. Rect/pill: the side-edge midpoint. Circle: the compass
    point on the rim. The outward normal is the side's normal, so the same
    ``standoff`` reads uniform whatever the shape."""
    nx, ny = _SIDE_NORMAL[side]
    cx, cy = _center(p)
    if p.shape == "circle":
        bx, by = cx + nx * p.r, cy + ny * p.r
    else:
        b = p.box
        bx = cx + nx * b.w / 2
        by = cy + ny * b.h / 2
    return (bx + nx * standoff, by + ny * standoff)


def arrow_d(tip: Vec, u: Vec, *, size: float = 11.0, half: float = 0.45) -> str:
    """A closed chevron at ``tip`` opening backward along ``-u`` (``u`` is
    the arrival tangent). Two legs to a shared apex, closed and FILLED in
    the connector's hue (the diagrams-v3 kit triangle) -- drawn geometry,
    never a ``<marker>`` element."""
    px, py = _perp(u)
    back_x, back_y = tip[0] - size * u[0], tip[1] - size * u[1]
    l1 = (back_x + size * half * px, back_y + size * half * py)
    l2 = (back_x - size * half * px, back_y - size * half * py)
    return f"M {fmt(l1[0])},{fmt(l1[1])} L {fmt(tip[0])},{fmt(tip[1])} L {fmt(l2[0])},{fmt(l2[1])} Z"


def _s_curve_end_tangent(x1: float, y1: float, x2: float, y2: float, *, axis: str) -> Vec:
    """An S-curve arrives along its construction axis: both control points
    of ``s_curve_h`` share the target's y (horizontal arrival), ``s_curve_v``
    share the target's x (vertical arrival). Direction is toward the target."""
    if axis == "h":
        return (1.0, 0.0) if x2 >= x1 else (-1.0, 0.0)
    return (0.0, 1.0) if y2 >= y1 else (0.0, -1.0)


def _sample_cubic(
    x1: float, y1: float, cx1: float, cy1: float, cx2: float, cy2: float, x2: float, y2: float, *, n: int = 8
) -> tuple[Vec, ...]:
    """A coarse polyline over a cubic (endpoints inclusive): the collide
    pass consumes it as an obstacle, so a light sampling is enough."""
    pts: list[Vec] = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        bx = mt**3 * x1 + 3 * mt**2 * t * cx1 + 3 * mt * t**2 * cx2 + t**3 * x2
        by = mt**3 * y1 + 3 * mt**2 * t * cy1 + 3 * mt * t**2 * cy2 + t**3 * y2
        pts.append((bx, by))
    return tuple(pts)


def route_path(
    sx: float,
    sy: float,
    tx: float,
    ty: float,
    *,
    style: str,
    axis: str = "h",
    mid: float | None = None,
    first_axis: str = "h",
    r: float = 10.0,
) -> tuple[str, float, tuple[Vec, ...], Vec]:
    """Route a wire from ``(sx, sy)`` to ``(tx, ty)`` in the chosen style.

    Returns ``(d, length, polyline, end_tangent)``. ``straight`` and
    ``curved`` reuse the ``paths.py`` builders (``axis`` selects the S-curve
    plane); ``orthogonal`` builds HVH/VHV legs with rounded elbows.
    ``polyline`` is a coarse point list (exact endpoints) for collision;
    ``end_tangent`` is the unit arrival direction.
    """
    if style == "straight":
        d = line_d(sx, sy, tx, ty)
        return d, line_len(sx, sy, tx, ty), ((sx, sy), (tx, ty)), chord_unit(sx, sy, tx, ty)
    if style == "curved":
        if axis == "v":
            d = s_curve_v(sx, sy, tx, ty)
            length = s_curve_v_len(sx, sy, tx, ty)
            my = (sy + ty) / 2
            poly = _sample_cubic(sx, sy, sx, my, tx, my, tx, ty)
        else:
            d = s_curve_h(sx, sy, tx, ty)
            length = s_curve_h_len(sx, sy, tx, ty)
            mx = (sx + tx) / 2
            poly = _sample_cubic(sx, sy, mx, sy, mx, ty, tx, ty)
        return d, length, poly, _s_curve_end_tangent(sx, sy, tx, ty, axis=axis)
    if style == "orthogonal":
        return orthogonal_d(sx, sy, tx, ty, mid=mid, first_axis=first_axis, r=r)
    raise ValueError(f"unknown route style {style!r} (straight | curved | orthogonal)")


def _corner_arc(
    join: Vec, incoming: Vec, outgoing: Vec, r_in: float, r_out: float
) -> tuple[str, Vec, Vec, float, bool]:
    """The rounded corner at ``join`` between an incoming leg (unit
    ``incoming``, toward the corner) and an outgoing leg (unit ``outgoing``,
    away). ``r_in``/``r_out`` cap the inset per adjacent leg. Returns the arc
    command, the point where the incoming leg ends (arc start), the point
    where the outgoing leg resumes (arc end), the radius used, and whether an
    arc was actually drawn (degenerate corners drop it)."""
    r = min(r_in, r_out)
    if r <= 0:
        return "", join, join, 0.0, False
    start = (join[0] - incoming[0] * r, join[1] - incoming[1] * r)
    end = (join[0] + outgoing[0] * r, join[1] + outgoing[1] * r)
    # Sweep sign from the turn direction (z of incoming cross outgoing): a
    # left-hand (CCW) turn sweeps 0, a right-hand (CW) turn sweeps 1 in SVG's
    # y-down space.
    cross = incoming[0] * outgoing[1] - incoming[1] * outgoing[0]
    sweep = 1 if cross > 0 else 0
    cmd = f"A {fmt(r)},{fmt(r)} 0 0 {sweep} {fmt(end[0])},{fmt(end[1])}"
    return cmd, start, end, r, True


def orthogonal_d(
    sx: float,
    sy: float,
    tx: float,
    ty: float,
    *,
    mid: float | None = None,
    first_axis: str = "h",
    r: float = 10.0,
) -> tuple[str, float, tuple[Vec, ...], Vec]:
    """A three-leg orthogonal route with rounded elbows.

    ``first_axis='h'`` gives HVH: run horizontally to ``mid`` (an x), turn
    vertically, turn back horizontally into the target. ``'v'`` gives VHV
    (``mid`` a y-split). Each corner rounds with radius ``min(r, |leg|/2)``
    over its two adjacent legs; a leg shorter than the corner's diameter drops
    that corner (a straight join). Length is exact: the sum of leg lengths
    minus the corner correction (each drawn corner replaces a sharp turn's
    ``2r`` of leg with a quarter-arc of length ``(pi/2)*r``)."""
    if first_axis == "h":
        mx = mid if mid is not None else (sx + tx) / 2
        corners = [(mx, sy), (mx, ty)]
        end_tangent: Vec = (1.0, 0.0) if tx >= mx else (-1.0, 0.0)
    else:
        my = mid if mid is not None else (sy + ty) / 2
        corners = [(sx, my), (tx, my)]
        end_tangent = (0.0, 1.0) if ty >= my else (0.0, -1.0)
    pts: list[Vec] = [(sx, sy), *corners, (tx, ty)]
    # Leg unit vectors and lengths between successive polyline points.
    legs: list[tuple[Vec, float]] = []
    for a, b in itertools.pairwise(pts):
        legs.append((_norm(b[0] - a[0], b[1] - a[1]), line_len(a[0], a[1], b[0], b[1])))
    # Per-corner radius cap: min(r, half of each adjacent leg). A corner
    # whose adjacent legs can't host the diameter drops to a sharp join.
    corner_r: list[float] = []
    for c in range(len(corners)):
        cap = min(r, legs[c][1] / 2, legs[c + 1][1] / 2)
        corner_r.append(cap if cap > 0.01 else 0.0)
    d_parts = [f"M {fmt(sx)},{fmt(sy)}"]
    length = sum(leg_len for _, leg_len in legs)
    for c, cxy in enumerate(corners):
        incoming = legs[c][0]
        outgoing = legs[c + 1][0]
        cmd, arc_start, _arc_end, r_used, drawn = _corner_arc(cxy, incoming, outgoing, corner_r[c], corner_r[c])
        d_parts.append(f"L {fmt(arc_start[0])},{fmt(arc_start[1])}")
        if drawn:
            d_parts.append(cmd)
            # Replace 2r of straight leg with a quarter-arc of length (pi/2)*r.
            length += (math.pi / 2) * r_used - 2 * r_used
    d_parts.append(f"L {fmt(tx)},{fmt(ty)}")
    # Corner-inset polyline: the sharp corners pulled back to their arc
    # endpoints (a coarse obstacle for collision; exact endpoints preserved).
    poly: list[Vec] = [(sx, sy)]
    for c, cxy in enumerate(corners):
        r_used = corner_r[c]
        if r_used > 0:
            incoming = legs[c][0]
            outgoing = legs[c + 1][0]
            poly.append((cxy[0] - incoming[0] * r_used, cxy[1] - incoming[1] * r_used))
            poly.append((cxy[0] + outgoing[0] * r_used, cxy[1] + outgoing[1] * r_used))
        else:
            poly.append(cxy)
    poly.append((tx, ty))
    return " ".join(d_parts), length, tuple(poly), end_tangent


def self_loop(
    p: NodePlacement,
    side: str,
    *,
    mouth: float = 24.0,
    reach: float = 46.0,
    pinch: float = 18.0,
    standoff: float = 0.0,
) -> tuple[str, float, Vec, Vec, Vec]:
    """A cubic self-loop leaving and re-entering ``p`` on the same ``side`` --
    the revise-in-place arc, generalizing the FSM back-loop to any node shape.

    Two boundary points ``a`` and ``b`` sit ``mouth`` apart, centred on the
    side midpoint (along the side segment for rect/pill; +/- half-mouth-angle
    around the compass point for a circle). With ``n`` the outward side normal
    and ``t`` the unit tangent from a to b: control points bow out by ``reach``
    along ``n`` and squeeze in by ``pinch`` along ``t`` (``c1 = a - pinch*t +
    reach*n``, ``c2 = b + pinch*t + reach*n``). Returns ``(d, length, apex,
    label_anchor, end_tangent)`` -- ``apex`` the cubic's t=0.5 point, the label
    anchored just outboard of the apex (text-anchor 'start'), the arrival
    tangent ``normalize(b - c2)``.
    """
    nx, ny = _SIDE_NORMAL[side]
    cx, cy = _center(p)
    half = mouth / 2
    if p.shape == "circle":
        base_deg = math.degrees(math.atan2(ny, nx))
        rr = p.r + standoff
        ang = half / rr if rr > 0 else 0.0  # small-angle chord approximates arc
        a = point_on(cx, cy, rr, base_deg - math.degrees(ang))
        b = point_on(cx, cy, rr, base_deg + math.degrees(ang))
    else:
        bmid = exit_point(p, side, standoff=standoff)
        tx, ty = _perp((nx, ny))  # along-side tangent
        a = (bmid[0] - tx * half, bmid[1] - ty * half)
        b = (bmid[0] + tx * half, bmid[1] + ty * half)
    tux, tuy = _norm(b[0] - a[0], b[1] - a[1])
    c1 = (a[0] - pinch * tux + reach * nx, a[1] - pinch * tuy + reach * ny)
    c2 = (b[0] + pinch * tux + reach * nx, b[1] + pinch * tuy + reach * ny)
    d = f"M {fmt(a[0])},{fmt(a[1])} C {fmt(c1[0])},{fmt(c1[1])} {fmt(c2[0])},{fmt(c2[1])} {fmt(b[0])},{fmt(b[1])}"
    length = cubic_len(a[0], a[1], c1[0], c1[1], c2[0], c2[1], b[0], b[1])
    # Apex at t=0.5 (De Casteljau midpoint of the cubic).
    ax = 0.125 * a[0] + 0.375 * c1[0] + 0.375 * c2[0] + 0.125 * b[0]
    ay = 0.125 * a[1] + 0.375 * c1[1] + 0.375 * c2[1] + 0.125 * b[1]
    apex = (ax, ay)
    label_anchor = (ax + mouth / 2 + 6.0, ay)
    end_tangent = _norm(b[0] - c2[0], b[1] - c2[1])
    return d, length, apex, label_anchor, end_tangent


def resolve_marker(edge_marker: str, spec_marker: str, direction_device: str) -> str:
    """The marker a connector draws: per-edge override > artifact default >
    genome direction_device > none. ``direction_device == 'arrowhead'`` opts
    the whole artifact into drawn arrows; any other value (the shipped
    'motion' default) yields none, so motion-carrying genomes stay unchanged.
    An explicit 'none' at either level wins over the genome device."""
    if edge_marker:
        return "" if edge_marker == "none" else edge_marker
    if spec_marker:
        return "" if spec_marker == "none" else spec_marker
    if direction_device == "arrowhead":
        return "arrow"
    return ""


def marker_path(tip: Vec, end_tangent: Vec | None, *, size: float, half: float, kind: str = "arrow") -> str:
    """A drawn terminal at a connector's end, or '' when the end tangent is
    unknown (a degenerate zero-length edge never earns a marker).

    ``arrow`` draws the chevron oriented to the end tangent; ``dot`` (the
    drift relation's terminal, §3) draws a small filled disc ON the
    terminus — on-terminus and deterministic by construction."""
    if end_tangent is None:
        return ""
    if kind == "dot":
        r = max(1.5, size * 0.22)
        x, y = tip
        from hyperweave.compose.diagram.paths import fmt as _fmt

        return (
            f"M {_fmt(x - r)},{_fmt(y)} "
            f"A {_fmt(r)},{_fmt(r)} 0 1 0 {_fmt(x + r)},{_fmt(y)} "
            f"A {_fmt(r)},{_fmt(r)} 0 1 0 {_fmt(x - r)},{_fmt(y)}"
        )
    return arrow_d(tip, end_tangent, size=size, half=half)
