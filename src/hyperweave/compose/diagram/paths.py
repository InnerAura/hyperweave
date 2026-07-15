"""Path-``d`` builders and curve measurement for the diagram solvers.

Every specimen connector reduces to five forms: straight line, horizontal
S-curve (control points at the x midpoint — verified exact against all
specimen curves), vertical S-curve, circular arc (sweep=1 clockwise), and
the radial ray (a collinear cubic so animateMotion pacing stays uniform).
Arc length is exact for lines/arcs and a fixed-step polyline for cubics —
deterministic by construction (no adaptive subdivision).
"""

from __future__ import annotations

import itertools
import math
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from hyperweave.compose.spatial_records import RectSpec

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


def diamond_d(cx: float, cy: float, r: float) -> str:
    """A filled diamond (rotated square) inscribed in radius ``r`` — one of
    the lanes category-by-SHAPE marks (obi-engine' morphology idiom)."""
    pts = ((cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy))
    x0, y0 = pts[0]
    rest = " ".join(f"L {fmt(x)},{fmt(y)}" for x, y in pts[1:])
    return f"M {fmt(x0)},{fmt(y0)} {rest} Z"


def square_d(cx: float, cy: float, r: float) -> str:
    """A filled square inscribed in radius ``r`` (half-diagonal) — the
    morphology idiom's fourth cycle shape."""
    half = r / math.sqrt(2)
    x0, y0 = cx - half, cy - half
    return (
        f"M {fmt(x0)},{fmt(y0)} L {fmt(x0 + 2 * half)},{fmt(y0)} "
        f"L {fmt(x0 + 2 * half)},{fmt(y0 + 2 * half)} L {fmt(x0)},{fmt(y0 + 2 * half)} Z"
    )


def line_stub_d(cx: float, cy: float, half_len: float) -> str:
    """A horizontal wire-stub swatch, centered at ``(cx, cy)`` — dep-audit's
    edge-type legend key (pp-tree-v2.svg/pp-tree-radial-v2.svg both measure
    a 12px stub, solid for direct-dep / dashed for transitive, drawn with
    the SAME stroke class its wires use; dashed is a template-side
    stroke-dasharray on this identical ``d``, never a different geometry)."""
    return f"M {fmt(cx - half_len)},{fmt(cy)} L {fmt(cx + half_len)},{fmt(cy)}"


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


def bisect_clearance_depth(
    build_points: Callable[[float], list[tuple[float, float]]],
    crossed: list[RectSpec],
    clearance: float,
    *,
    hi: float = 240.0,
    rounds: int = 24,
) -> tuple[float, float]:
    """(extra_depth, deepest_y) for an under-curve that must clear every box
    in ``crossed`` by ``clearance`` (G7 binds under-runs too): bisect the
    extra DEPTH down until the flattened curve clears, deterministic (fixed
    bisection rounds, ceil'd result). ``build_points`` samples the candidate
    curve at a given extra depth — the caller owns the cubic's shape (a
    state-machine's asymmetric hook, a pipeline return's symmetric flat-
    bottom sweep, or any other); this function only owns the search.

    Bisection assumes ``clears(extra)`` is monotonic (deeper always clears
    more) — true whenever every crossed box sits on one side of the sweep's
    natural path. A SANDWICHED pair (one box above the path, one below —
    agent-task-lifecycle's revise sweep threading between executing and its
    own dropped failed card) breaks that: past some depth the curve clears
    the upper box but drives its RETURN leg into the lower one, so no single
    extra in [0, hi] clears every box. When bisection's own answer does not
    actually clear, a 1px-resolution scan over the full range picks whichever
    extra holds the best worst-case gap — the closest the geometry gets, not
    ``hi`` (bisection's blind fallback when ``clears`` never returns True,
    provably the WORST choice in that shape: the return leg is deepest into
    the lower box exactly there)."""

    def worst_gap(extra: float) -> float:
        gap = math.inf
        for px, py in build_points(extra):
            for box in crossed:
                gx = max(box.x - px, px - (box.x + box.w), 0.0)
                gy = max(box.y - py, py - (box.y + box.h), 0.0)
                gap = min(gap, math.hypot(gx, gy))
        return gap

    def clears(extra: float) -> bool:
        return worst_gap(extra) >= clearance

    extra = 0.0
    if crossed and not clears(0.0):
        lo, hi_bound = 0.0, hi
        for _ in range(rounds):
            mid = (lo + hi_bound) / 2.0
            if clears(mid):
                hi_bound = mid
            else:
                lo = mid
        extra = float(math.ceil(hi_bound))
        if not clears(extra):
            steps = max(1, int(hi))
            extra = max((i * hi / steps for i in range(steps + 1)), key=worst_gap)
    deepest = max(py for _, py in build_points(extra))
    return extra, deepest


def chord_unit(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    """Unit vector along the chord — the gradient travel axis for beam/flow."""
    d = math.hypot(x2 - x1, y2 - y1)
    if d == 0:
        return (1.0, 0.0)
    return ((x2 - x1) / d, (y2 - y1) / d)


_PATH_TOKEN = re.compile(r"([A-Za-z])|(-?\d+(?:\.\d+)?(?:e-?\d+)?)")


def sample_path(d: str, per_cubic: int = 16) -> tuple[tuple[float, float], ...]:
    """Sample an absolute M/L/H/V/C/Q path into a coarse polyline.

    The subset is exactly what the solver builders emit (skip channels,
    under-curves, self-loops, tangent fans, the orthogonal over/under skip's
    L+Q corners). Cubics and quadratics sample at ``per_cubic`` steps; lines
    contribute their endpoints. Consumers are the annotate
    obstacle set and the content-extents union — a wire that dips outside
    its endpoint chord must carry the dip, or labels land on it and the
    canvas crops it (bugs d + e)."""
    pts: list[tuple[float, float]] = []
    nums: list[float] = []
    cmd = ""
    x = y = 0.0

    def flush() -> None:
        nonlocal x, y, nums
        if not cmd or not nums:
            nums = []
            return
        if cmd == "M" and len(nums) >= 2:
            x, y = nums[0], nums[1]
            pts.append((x, y))
            for i in range(2, len(nums) - 1, 2):
                x, y = nums[i], nums[i + 1]
                pts.append((x, y))
        elif cmd == "L":
            for i in range(0, len(nums) - 1, 2):
                x, y = nums[i], nums[i + 1]
                pts.append((x, y))
        elif cmd == "H":
            for v in nums:
                x = v
                pts.append((x, y))
        elif cmd == "V":
            for v in nums:
                y = v
                pts.append((x, y))
        elif cmd == "C":
            for i in range(0, len(nums) - 5, 6):
                c1x, c1y, c2x, c2y, ex, ey = nums[i : i + 6]
                for k in range(1, per_cubic + 1):
                    s = k / per_cubic
                    u = 1.0 - s
                    px = u * u * u * x + 3 * u * u * s * c1x + 3 * u * s * s * c2x + s * s * s * ex
                    py = u * u * u * y + 3 * u * u * s * c1y + 3 * u * s * s * c2y + s * s * s * ey
                    pts.append((px, py))
                x, y = ex, ey
        elif cmd == "Q":
            for i in range(0, len(nums) - 3, 4):
                cx, cy, ex, ey = nums[i : i + 4]
                for k in range(1, per_cubic + 1):
                    s = k / per_cubic
                    u = 1.0 - s
                    px = u * u * x + 2 * u * s * cx + s * s * ex
                    py = u * u * y + 2 * u * s * cy + s * s * ey
                    pts.append((px, py))
                x, y = ex, ey
        elif cmd == "A":
            # Endpoint-true arc handling: consume 7-number groups so radii
            # and flags never leak into the point stream. Arc-built geos get
            # exact analytic sampling in enrich (geo.arc); here the endpoint
            # suffices.
            for i in range(0, len(nums) - 6, 7):
                x, y = nums[i + 5], nums[i + 6]
                pts.append((x, y))
        nums = []

    for m in _PATH_TOKEN.finditer(d):
        if m.group(1):
            flush()
            cmd = m.group(1).upper()
            if cmd not in ("M", "L", "H", "V", "C", "Q", "A"):
                cmd = ""  # unhandled command: swallow its numbers
        else:
            nums.append(float(m.group(2)))
    flush()
    return tuple(pts)


def end_tangent_of(d: str) -> tuple[float, float] | None:
    """Unit tangent at an absolute path's END from the FINAL segment's
    analytic derivative — C: end-c2 (falling to end-c1, then end-start when
    controls coincide); Q: end-ctrl; L/H/V: the segment; A: the endpoint
    perpendicular signed by the sweep. One owner for arrival direction
    wherever a builder supplies no tangent: the polyline-secant fallback
    read curved arrivals up to 37° off (an over-arc chevron), and every
    hardcoded axis guess eventually meets a curve that doesn't arrive on
    the axis."""
    nums: list[float] = []
    cmd = ""
    x = y = 0.0
    last: tuple[float, float] | None = None

    def seg_tangent() -> None:
        nonlocal x, y, last, nums
        if not cmd or not nums:
            nums = []
            return
        if cmd == "M" and len(nums) >= 2:
            x, y = nums[-2], nums[-1]
        elif cmd == "L" and len(nums) >= 2:
            ex, ey = nums[-2], nums[-1]
            px, py = (nums[-4], nums[-3]) if len(nums) >= 4 else (x, y)
            last = (ex - px, ey - py)
            x, y = ex, ey
        elif cmd == "H" and nums:
            last = (nums[-1] - (nums[-2] if len(nums) >= 2 else x), 0.0)
            x = nums[-1]
        elif cmd == "V" and nums:
            last = (0.0, nums[-1] - (nums[-2] if len(nums) >= 2 else y))
            y = nums[-1]
        elif cmd == "C" and len(nums) >= 6:
            base = len(nums) - len(nums) % 6 - 6 if len(nums) % 6 else len(nums) - 6
            sx0, sy0 = (nums[base - 2], nums[base - 1]) if base >= 2 else (x, y)
            c1x, c1y, c2x, c2y, ex, ey = nums[base : base + 6]
            for px, py in ((c2x, c2y), (c1x, c1y), (sx0, sy0)):
                if abs(ex - px) > 1e-9 or abs(ey - py) > 1e-9:
                    last = (ex - px, ey - py)
                    break
            x, y = ex, ey
        elif cmd == "Q" and len(nums) >= 4:
            base = len(nums) - len(nums) % 4 - 4 if len(nums) % 4 else len(nums) - 4
            sx0, sy0 = (nums[base - 2], nums[base - 1]) if base >= 2 else (x, y)
            qx, qy, ex, ey = nums[base : base + 4]
            for px, py in ((qx, qy), (sx0, sy0)):
                if abs(ex - px) > 1e-9 or abs(ey - py) > 1e-9:
                    last = (ex - px, ey - py)
                    break
            x, y = ex, ey
        elif cmd == "A" and len(nums) >= 7:
            base = len(nums) - len(nums) % 7 - 7 if len(nums) % 7 else len(nums) - 7
            sx0, sy0 = (nums[base - 2], nums[base - 1]) if base >= 2 else (x, y)
            rx_, ry_, rot_deg, laf, swf, ex, ey = nums[base : base + 7]
            rx_, ry_ = abs(rx_), abs(ry_)
            if rx_ < 1e-9 or ry_ < 1e-9 or (abs(ex - sx0) < 1e-9 and abs(ey - sy0) < 1e-9):
                x, y = ex, ey
                nums = []
                return
            rot = math.radians(rot_deg)
            cosr, sinr = math.cos(rot), math.sin(rot)
            dx2, dy2 = (sx0 - ex) / 2.0, (sy0 - ey) / 2.0
            x1p = cosr * dx2 + sinr * dy2
            y1p = -sinr * dx2 + cosr * dy2
            lam = (x1p / rx_) ** 2 + (y1p / ry_) ** 2
            if lam > 1.0:
                s = math.sqrt(lam)
                rx_, ry_ = rx_ * s, ry_ * s
            num_ = rx_**2 * ry_**2 - rx_**2 * y1p**2 - ry_**2 * x1p**2
            den_ = rx_**2 * y1p**2 + ry_**2 * x1p**2
            co = math.sqrt(max(num_ / den_, 0.0)) * (-1.0 if laf == swf else 1.0)
            cxp, cyp = co * rx_ * y1p / ry_, -co * ry_ * x1p / rx_
            th2 = math.atan2((-y1p - cyp) / ry_, (-x1p - cxp) / rx_)
            sign = 1.0 if swf == 1 else -1.0
            last = (
                sign * (-rx_ * math.sin(th2) * cosr - ry_ * math.cos(th2) * sinr),
                sign * (-rx_ * math.sin(th2) * sinr + ry_ * math.cos(th2) * cosr),
            )
            x, y = ex, ey
        nums = []

    for m in _PATH_TOKEN.finditer(d):
        if m.group(1):
            seg_tangent()
            cmd = m.group(1).upper()
            if cmd not in ("M", "L", "H", "V", "C", "Q", "A"):
                cmd = ""
        else:
            nums.append(float(m.group(2)))
    seg_tangent()
    if last is None:
        return None
    n = math.hypot(*last)
    return (last[0] / n, last[1] / n) if n > 1e-9 else None


def _segment_cross(s: tuple[float, float, float, float], t: tuple[float, float, float, float]) -> bool:
    """Do open segments s=(x0,y0,x1,y1) and t cross? Strict sign test — a
    shared endpoint (incidence) does not count, only a true interior crossing."""

    def side(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

    d1 = side(s[0], s[1], s[2], s[3], t[0], t[1])
    d2 = side(s[0], s[1], s[2], s[3], t[2], t[3])
    d3 = side(t[0], t[1], t[2], t[3], s[0], s[1])
    d4 = side(t[0], t[1], t[2], t[3], s[2], s[3])
    return d1 * d2 < -1e-9 and d3 * d4 < -1e-9


def count_polyline_crossings(polylines: list[tuple[int, tuple[tuple[float, float], ...]]]) -> int:
    """Count DISTINCT polyline pairs that intersect (the §6 crossing-count
    diagnostic). Each element is (id, points); same-id pairs are skipped so
    an arc-subdivided edge never crosses itself."""

    def segs(pts: tuple[tuple[float, float], ...]) -> list[tuple[float, float, float, float]]:
        return [(a[0], a[1], b[0], b[1]) for a, b in itertools.pairwise(pts)]

    count = 0
    for (ia, pa), (ib, pb) in itertools.combinations(polylines, 2):
        if ia == ib:
            continue
        if any(_segment_cross(s, u) for s in segs(pa) for u in segs(pb)):
            count += 1
    return count
