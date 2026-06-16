"""Path-``d`` builders and curve measurement for the diagram solvers.

Every specimen connector reduces to five forms: straight line, horizontal
S-curve (control points at the x midpoint — verified exact against all
specimen curves), vertical S-curve, circular arc (sweep=1 clockwise), and
the radial ray (a collinear cubic so animateMotion pacing stays uniform).
Arc length is exact for lines/arcs and a fixed-step polyline for cubics —
deterministic by construction (no adaptive subdivision).
"""

from __future__ import annotations

import math

_CUBIC_SAMPLES = 32


def fmt(v: float) -> str:
    """Format a coordinate: one decimal, trailing zeros dropped."""
    r = round(v, 1)
    if r == int(r):
        return str(int(r))
    return f"{r:g}"


def line_d(x1: float, y1: float, x2: float, y2: float) -> str:
    return f"M {fmt(x1)},{fmt(y1)} L {fmt(x2)},{fmt(y2)}"


def s_curve_h(x1: float, y1: float, x2: float, y2: float) -> str:
    """Horizontal S-curve: both control points at the x midpoint."""
    mx = (x1 + x2) / 2
    return f"M {fmt(x1)},{fmt(y1)} C {fmt(mx)},{fmt(y1)} {fmt(mx)},{fmt(y2)} {fmt(x2)},{fmt(y2)}"


def s_curve_v(x1: float, y1: float, x2: float, y2: float) -> str:
    """Vertical S-curve: both control points at the y midpoint."""
    my = (y1 + y2) / 2
    return f"M {fmt(x1)},{fmt(y1)} C {fmt(x1)},{fmt(my)} {fmt(x2)},{fmt(my)} {fmt(x2)},{fmt(y2)}"


def point_on(cx: float, cy: float, r: float, deg: float) -> tuple[float, float]:
    rad = math.radians(deg)
    return (cx + r * math.cos(rad), cy + r * math.sin(rad))


def arc_d(cx: float, cy: float, r: float, a0_deg: float, a1_deg: float) -> str:
    """Clockwise circular arc from a0 to a1 (degrees, -90 = top)."""
    x0, y0 = point_on(cx, cy, r, a0_deg)
    x1, y1 = point_on(cx, cy, r, a1_deg)
    large = 1 if (a1_deg - a0_deg) % 360 > 180 else 0
    return f"M {fmt(x0)},{fmt(y0)} A {fmt(r)},{fmt(r)} 0 {large} 1 {fmt(x1)},{fmt(y1)}"


def ray_d(x1: float, y1: float, x2: float, y2: float) -> str:
    """Collinear cubic (controls at t=1/3, 2/3): a straight ray whose
    animateMotion pacing matches the curved family's."""
    cx1, cy1 = x1 + (x2 - x1) / 3, y1 + (y2 - y1) / 3
    cx2, cy2 = x1 + 2 * (x2 - x1) / 3, y1 + 2 * (y2 - y1) / 3
    return f"M {fmt(x1)},{fmt(y1)} C {fmt(cx1)},{fmt(cy1)} {fmt(cx2)},{fmt(cy2)} {fmt(x2)},{fmt(y2)}"


def line_len(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def cubic_len(
    x1: float,
    y1: float,
    cx1: float,
    cy1: float,
    cx2: float,
    cy2: float,
    x2: float,
    y2: float,
) -> float:
    """Fixed-step polyline length — deterministic for identical inputs."""
    total = 0.0
    px, py = x1, y1
    for i in range(1, _CUBIC_SAMPLES + 1):
        t = i / _CUBIC_SAMPLES
        mt = 1 - t
        bx = mt**3 * x1 + 3 * mt**2 * t * cx1 + 3 * mt * t**2 * cx2 + t**3 * x2
        by = mt**3 * y1 + 3 * mt**2 * t * cy1 + 3 * mt * t**2 * cy2 + t**3 * y2
        total += math.hypot(bx - px, by - py)
        px, py = bx, by
    return total


def s_curve_h_len(x1: float, y1: float, x2: float, y2: float) -> float:
    mx = (x1 + x2) / 2
    return cubic_len(x1, y1, mx, y1, mx, y2, x2, y2)


def s_curve_v_len(x1: float, y1: float, x2: float, y2: float) -> float:
    my = (y1 + y2) / 2
    return cubic_len(x1, y1, x1, my, x2, my, x2, y2)


def arc_len(r: float, a0_deg: float, a1_deg: float) -> float:
    return r * math.radians(abs(a1_deg - a0_deg))


def sagitta(r: float, span_deg: float) -> float:
    """Maximum chord-to-arc deviation for an arc of the given span."""
    return r * (1 - math.cos(math.radians(span_deg) / 2))


def subdivide_arc(
    a0_deg: float, a1_deg: float, r: float, threshold: float, max_segments: int
) -> list[tuple[float, float]]:
    """Split an arc into equal angular segments, each within the sagitta
    threshold (so a chord-aligned flow gradient tracks imperceptibly).
    Deterministic: segment count from a closed-form bound, capped."""
    span = abs(a1_deg - a0_deg)
    if sagitta(r, span) <= threshold:
        return [(a0_deg, a1_deg)]
    # Per-segment span s satisfying r(1 - cos(s/2)) <= threshold.
    limit = 2 * math.degrees(math.acos(max(-1.0, 1 - threshold / r)))
    k = min(max_segments, max(2, math.ceil(span / limit)))
    step = (a1_deg - a0_deg) / k
    return [(a0_deg + i * step, a0_deg + (i + 1) * step) for i in range(k)]


def chord_unit(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    """Unit vector along the chord — the gradient travel axis for beam/flow."""
    d = math.hypot(x2 - x1, y2 - y1)
    if d == 0:
        return (1.0, 0.0)
    return ((x2 - x1) / d, (y2 - y1) / d)
