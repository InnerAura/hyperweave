"""One flattening contract for path judgements.

:func:`flatten` turns an SVG path into polylines whose every point lies
within ``tolerance`` of the true curve (adaptive de Casteljau subdivision
for Béziers, sagitta-bounded chords for arcs). A law that grades the result
inflates its forbidden boxes by that tolerance, so the approximation error is
consumed by the predicate rather than assumed away.

``curve_samples`` selects the legacy fixed-count mode — Bézier segments at
``k`` evenly spaced parameters, arcs as chords — for seat candidates and
pictures that need even coverage rather than a bound. It is never a proof.
"""

from __future__ import annotations

import math
import re
from itertools import pairwise

Point = tuple[float, float]

FLATTEN_TOL = 0.25
"""Maximum distance between the flattened polyline and the true curve, in px.
Chosen below half the clearance law's tolerance (0.6) so inflating a box by
``FLATTEN_TOL`` leaves the law's own margin intact."""

_MAX_DEPTH = 18
_TOKEN = re.compile(r"[MLHVCSQTAZ]|-?\d*\.?\d+(?:e[+-]?\d+)?", re.I)
_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def _dist_point_line(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    norm = math.hypot(dx, dy)
    if norm == 0.0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    return abs(dy * (p[0] - a[0]) - dx * (p[1] - a[1])) / norm


def _cubic_at(p0: Point, c1: Point, c2: Point, p3: Point, t: float) -> Point:
    u = 1.0 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * p3[1],
    )


def _flatten_cubic(p0: Point, c1: Point, c2: Point, p3: Point, tol: float, out: list[Point], depth: int = 0) -> None:
    """Emit points along the cubic until the control polygon lies within
    ``tol`` of the chord — the classic flatness criterion, which bounds the
    curve itself since a Bézier lies inside its control hull."""
    if depth >= _MAX_DEPTH or max(_dist_point_line(c1, p0, p3), _dist_point_line(c2, p0, p3)) <= tol:
        out.append(p3)
        return
    m01 = ((p0[0] + c1[0]) / 2, (p0[1] + c1[1]) / 2)
    m12 = ((c1[0] + c2[0]) / 2, (c1[1] + c2[1]) / 2)
    m23 = ((c2[0] + p3[0]) / 2, (c2[1] + p3[1]) / 2)
    m012 = ((m01[0] + m12[0]) / 2, (m01[1] + m12[1]) / 2)
    m123 = ((m12[0] + m23[0]) / 2, (m12[1] + m23[1]) / 2)
    mid = ((m012[0] + m123[0]) / 2, (m012[1] + m123[1]) / 2)
    _flatten_cubic(p0, m01, m012, mid, tol, out, depth + 1)
    _flatten_cubic(mid, m123, m23, p3, tol, out, depth + 1)


def _quad_to_cubic(p0: Point, c: Point, p1: Point) -> tuple[Point, Point]:
    return (
        (p0[0] + 2 / 3 * (c[0] - p0[0]), p0[1] + 2 / 3 * (c[1] - p0[1])),
        (p1[0] + 2 / 3 * (c[0] - p1[0]), p1[1] + 2 / 3 * (c[1] - p1[1])),
    )


def _sample_cubic(p0: Point, c1: Point, c2: Point, p3: Point, samples: int, out: list[Point]) -> None:
    for k in range(1, samples + 1):
        out.append(_cubic_at(p0, c1, c2, p3, k / samples))


def _sample_quad(p0: Point, c: Point, p1: Point, samples: int, out: list[Point]) -> None:
    for k in range(1, samples + 1):
        t = k / samples
        u = 1.0 - t
        out.append((u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0], u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1]))


def _flatten_arc(
    p0: Point, rx: float, ry: float, phi_deg: float, large: bool, sweep: bool, p1: Point, tol: float, out: list[Point]
) -> None:
    """SVG endpoint arc → center parametrization (spec F.6.5), then enough
    chords that every sagitta stays under ``tol``."""
    if p0 == p1:
        return
    rx, ry = abs(rx), abs(ry)
    if rx == 0.0 or ry == 0.0:
        out.append(p1)
        return
    phi = math.radians(phi_deg)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx2, dy2 = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1p = cos_p * dx2 + sin_p * dy2
    y1p = -sin_p * dx2 + cos_p * dy2
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1.0:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = 0.0 if den == 0.0 else math.sqrt(max(0.0, num / den))
    if large == sweep:
        coef = -coef
    cxp, cyp = coef * rx * y1p / ry, -coef * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (p0[0] + p1[0]) / 2
    cy = sin_p * cxp + cos_p * cyp + (p0[1] + p1[1]) / 2

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        mag = math.hypot(ux, uy) * math.hypot(vx, vy)
        ang = math.acos(max(-1.0, min(1.0, dot / mag))) if mag else 0.0
        return -ang if ux * vy - uy * vx < 0 else ang

    theta0 = angle(1.0, 0.0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2 * math.pi
    r_max = max(rx, ry)
    step = 2 * math.acos(max(-1.0, min(1.0, 1.0 - tol / r_max))) if r_max > tol else math.pi
    n = max(1, math.ceil(abs(dtheta) / step))
    for k in range(1, n + 1):
        th = theta0 + dtheta * k / n
        ex, ey = rx * math.cos(th), ry * math.sin(th)
        out.append((cos_p * ex - sin_p * ey + cx, sin_p * ex + cos_p * ey + cy))
    out[-1] = p1


def flatten(d: str, *, tolerance: float = FLATTEN_TOL, curve_samples: int | None = None) -> list[list[Point]]:
    """Every subpath of ``d`` as a polyline within ``tolerance`` of the curve.

    Relative commands are tracked through the cursor. With ``curve_samples``
    set, Béziers take that many evenly spaced samples and arcs become chords
    (the legacy sampler's shape); that mode is for candidate seats and
    pictures, not judgements.
    """
    tokens = _TOKEN.findall(d)
    subpaths: list[list[Point]] = []
    pts: list[Point] = []
    cur: Point = (0.0, 0.0)
    start: Point = (0.0, 0.0)
    last_ctrl: Point | None = None
    cmd = ""
    i = 0

    def flush() -> None:
        nonlocal pts
        if len(pts) > 1:
            subpaths.append(pts)
        pts = []

    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            i += 1
            if cmd.upper() == "Z":
                if pts and pts[-1] != start:
                    pts.append(start)
                flush()
                cur = start
                pts = [cur]
            continue
        upper = cmd.upper()
        arity = _ARITY[upper]
        nums = [float(n) for n in tokens[i : i + arity]]
        i += arity
        if len(nums) < arity:
            break
        rel = cmd.islower()
        ox, oy = cur if rel else (0.0, 0.0)
        if upper == "M":
            flush()
            cur = (ox + nums[0], oy + nums[1])
            start = cur
            pts = [cur]
            cmd = "l" if rel else "L"
            last_ctrl = None
        elif upper in ("L", "T"):
            if upper == "T":
                ctrl = (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1]) if last_ctrl else cur
                end = (ox + nums[0], oy + nums[1])
                c1, c2 = _quad_to_cubic(cur, ctrl, end)
                if curve_samples:
                    _sample_quad(cur, ctrl, end, curve_samples, pts)
                else:
                    _flatten_cubic(cur, c1, c2, end, tolerance, pts)
                cur, last_ctrl = end, ctrl
            else:
                cur = (ox + nums[0], oy + nums[1])
                pts.append(cur)
                last_ctrl = None
        elif upper == "H":
            cur = (ox + nums[0], cur[1])
            pts.append(cur)
            last_ctrl = None
        elif upper == "V":
            cur = (cur[0], oy + nums[0])
            pts.append(cur)
            last_ctrl = None
        elif upper in ("C", "S"):
            if upper == "C":
                c1 = (ox + nums[0], oy + nums[1])
                c2, end = (ox + nums[2], oy + nums[3]), (ox + nums[4], oy + nums[5])
            else:
                c1 = (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1]) if last_ctrl else cur
                c2, end = (ox + nums[0], oy + nums[1]), (ox + nums[2], oy + nums[3])
            if curve_samples:
                _sample_cubic(cur, c1, c2, end, curve_samples, pts)
            else:
                _flatten_cubic(cur, c1, c2, end, tolerance, pts)
            cur, last_ctrl = end, c2
        elif upper == "Q":
            ctrl, end = (ox + nums[0], oy + nums[1]), (ox + nums[2], oy + nums[3])
            if curve_samples:
                _sample_quad(cur, ctrl, end, max(1, curve_samples // 2), pts)
            else:
                c1, c2 = _quad_to_cubic(cur, ctrl, end)
                _flatten_cubic(cur, c1, c2, end, tolerance, pts)
            cur, last_ctrl = end, ctrl
        elif upper == "A":
            end = (ox + nums[5], oy + nums[6])
            if curve_samples:
                pts.append(end)
            else:
                _flatten_arc(cur, nums[0], nums[1], nums[2], nums[3] != 0.0, nums[4] != 0.0, end, tolerance, pts)
            cur, last_ctrl = end, None
    flush()
    return subpaths


def flatten_points(d: str, *, tolerance: float = FLATTEN_TOL, curve_samples: int | None = None) -> list[Point]:
    """All subpaths of ``d`` concatenated into one point list."""
    return [p for sub in flatten(d, tolerance=tolerance, curve_samples=curve_samples) for p in sub]


def polyline_length(points: list[Point] | tuple[Point, ...]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in pairwise(points))
