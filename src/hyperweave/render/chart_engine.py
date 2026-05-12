"""Pure chart rendering primitives.

This module is the shared rendering kernel for the ``chart`` frame (standalone
star history) and the embedded chart zone inside the ``stats`` frame's
``chrome`` paradigm. It takes a list of data points, a viewport rect, and a
small dict of structural hints (``stroke_linejoin``, ``data_point_shape``,
``fill_density``) and returns a dict of structured render data ready for
Jinja templates to iterate + include.

Architectural rules (Invariants 1 + 6):
    - Zero network I/O. Fetching happens at the CLI/HTTP layer before compose.
    - Zero CSS. Colors are passed as ``var(--dna-*)`` references by callers.
    - Zero SVG string assembly. Every visual element returns as structured
      Python data (dicts / list[dict]); templates under
      ``templates/components/chart-*.svg.j2`` render the final markup.
    - Pure functions. No classes, no state.

Public API:
    :func:`build_chart_svg` is the single entry point. It returns a dict:

        - ``axes``, ``gridlines``, ``markers``, ``milestones`` → ``list[dict]``
        - ``area``, ``polyline``, ``empty_state`` → ``dict`` or ``None``
        - ``y_labels``, ``x_labels`` → ``list[dict]`` for axis tick labels
        - ``defs`` → ``str`` (reserved for future per-chart CSS/filters)

    Templates iterate the lists and guard the optional dicts with ``{% if %}``;
    each element maps to a small Jinja partial such as
    ``components/chart-polyline.svg.j2``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

# ── Data types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Viewport:
    """Rectangular drawing region inside the host SVG."""

    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class ChartPoint:
    """A single (date, value) pair along the time axis."""

    date: datetime
    value: int


# ── Input normalisation ────────────────────────────────────────────────────


def _normalize_points(raw: list[Any]) -> list[ChartPoint]:
    """Accept raw connector data in several shapes and return sorted points.

    Supported shapes:
        - ``[{"date": "2026-04-11", "count": 2850}, ...]``
        - ``[{"date": datetime(...), "count": 2850}, ...]``
        - ``[(datetime(...), 2850), ...]``
    """
    points: list[ChartPoint] = []
    for entry in raw:
        if isinstance(entry, ChartPoint):
            points.append(entry)
            continue
        if isinstance(entry, tuple) and len(entry) == 2:
            d_raw, v_raw = entry
        elif isinstance(entry, dict):
            d_raw = entry.get("date")
            v_raw = entry.get("count", entry.get("value", 0))
        else:
            continue
        if isinstance(d_raw, str):
            try:
                d = datetime.fromisoformat(d_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
        elif isinstance(d_raw, datetime):
            d = d_raw
        else:
            continue
        if d.tzinfo is None:
            d = d.replace(tzinfo=UTC)
        try:
            v = int(v_raw)
        except (TypeError, ValueError):
            continue
        points.append(ChartPoint(date=d, value=v))
    points.sort(key=lambda p: p.date)
    return points


# ── Projection ─────────────────────────────────────────────────────────────


def _project_points(
    points: list[ChartPoint],
    vp: Viewport,
    *,
    v_min: int | None = None,
    v_max: int | None = None,
) -> list[tuple[int, int]]:
    """Project (date, value) points into pixel coordinates inside ``vp``.

    Returns a list of ``(x, y)`` int tuples. X is linear in time; Y is linear
    in value, flipped so y=vp.y is the top of the chart and y=vp.y+vp.h is the
    baseline.

    By default the Y range is inferred from the data's min/max. Callers (like
    :func:`build_chart_svg` for star charts) can override ``v_min=0`` and
    ``v_max=nice_tick_max`` so the polyline shares the same coordinate basis as
    the tick labels. Without that alignment the labels and curve would only
    agree by coincidence.

    When all timestamps are identical (``t_span == 0`` — a degenerate
    single-page low-star case), points are distributed evenly across the
    viewport width by index rather than collapsing to ``vp.x``.
    """
    if not points:
        return []
    if len(points) == 1:
        # Single point → center of the viewport (no time/value range to map).
        return [(vp.x + vp.w // 2, vp.y + vp.h // 2)]

    t0 = points[0].date.timestamp()
    t1 = points[-1].date.timestamp()
    t_span = t1 - t0
    v_hi = v_max if v_max is not None else max(p.value for p in points)
    v_lo = v_min if v_min is not None else min(p.value for p in points)
    v_span = max(1, v_hi - v_lo)

    out: list[tuple[int, int]] = []
    n = len(points)
    for i, p in enumerate(points):
        # When all timestamps are identical (t_span <= 0), distribute points
        # evenly by index rather than collapsing them all to vp.x.
        frac_t = i / max(1, n - 1) if t_span <= 0 else (p.date.timestamp() - t0) / t_span
        frac_v = (p.value - v_lo) / v_span
        px = vp.x + round(frac_t * vp.w)
        py = vp.y + vp.h - round(frac_v * vp.h)
        out.append((px, py))
    return out


# ── Path / polyline builders ───────────────────────────────────────────────


def _build_polyline_points(projected: list[tuple[int, int]]) -> str:
    """Return an SVG ``points="x,y x,y ..."`` attribute value."""
    return " ".join(f"{x},{y}" for x, y in projected)


def _build_bezier_path(projected: list[tuple[int, int]]) -> str:
    """Build a smooth cubic bezier path using Fritsch-Carlson monotonic cubic interpolation.

    This is the same curve D3 renders via ``curveMonotoneX``. For data with
    monotonically increasing x-coordinates (e.g. any time-series chart like
    star history), the curve is guaranteed to:

    - Pass through every anchor point (C0 continuity).
    - Be C1-continuous (smooth tangent at every anchor).
    - Be monotonic wherever the input is monotonic (no dips between rising
      points).
    - Not overshoot — control handles stay within their segment in x,
      regardless of uneven x-spacing.

    The previous implementation placed horizontal control handles at every
    anchor (``c1y = y_prev``, ``c2y = y_cur``). That shape produced two
    visual artifacts on real data:

    1. **Flat-then-vertical** for bursty growth — horizontal tangents forced
       each segment into a plateau → S-curve → plateau shape, so the chart
       read as flat sections punctuated by sharp rises.

    2. **Self-intersecting segments** when two adjacent anchors were close
       in x — the hard-coded ``dx = max(4, (x_cur - x_prev) // 3)`` produced
       ``c2.x < c1.x``, rasterizing badly on mobile/Camo.

    Fritsch-Carlson solves both by computing per-segment slopes, deriving a
    tangent at each point from the neighboring slopes, and then rescaling
    tangent magnitudes with the ``α² + β² > 9`` test so control handles
    never extend past their segment.

    References:
        Fritsch, F. N.; Carlson, R. E. (1980). "Monotone Piecewise Cubic
        Interpolation". SIAM Journal on Numerical Analysis. 17 (2): 238-246.
    """
    n = len(projected)
    if n == 0:
        return ""
    if n == 1:
        x, y = projected[0]
        return f"M{x},{y}"
    if n == 2:
        # Two points → straight-line bezier (no interior tangents to compute).
        x0, y0 = projected[0]
        x1, y1 = projected[1]
        dx = (x1 - x0) / 3
        c1x, c1y = round(x0 + dx), y0
        c2x, c2y = round(x1 - dx), y1
        return f"M{x0},{y0} C{c1x},{c1y} {c2x},{c2y} {x1},{y1}"

    # 1. Per-segment slopes m_i = (y_{i+1} - y_i) / (x_{i+1} - x_i).
    slopes: list[float] = []
    for i in range(n - 1):
        sx = projected[i + 1][0] - projected[i][0]
        sy = projected[i + 1][1] - projected[i][1]
        slopes.append(sy / sx if sx != 0 else 0.0)

    # 2. Initial tangents at each anchor. Endpoints use the one adjacent slope;
    # interior points use the average of the two adjacent slopes, but set to 0
    # at turning points (where the two slopes have opposite sign).
    tangents: list[float] = [0.0] * n
    tangents[0] = slopes[0]
    tangents[-1] = slopes[-1]
    for i in range(1, n - 1):
        if slopes[i - 1] * slopes[i] > 0:
            tangents[i] = (slopes[i - 1] + slopes[i]) / 2
        # else: turning point → tangent stays 0

    # 3. Fritsch-Carlson overshoot prevention. For each segment, if the
    # (alpha, beta) pair falls outside the monotonicity circle of radius 3,
    # rescale both tangents by tau = 3 / sqrt(alpha^2 + beta^2).
    for i in range(n - 1):
        if slopes[i] == 0:
            tangents[i] = 0.0
            tangents[i + 1] = 0.0
            continue
        alpha = tangents[i] / slopes[i]
        beta = tangents[i + 1] / slopes[i]
        if alpha * alpha + beta * beta > 9:
            tau = 3.0 / (alpha * alpha + beta * beta) ** 0.5
            tangents[i] = tau * alpha * slopes[i]
            tangents[i + 1] = tau * beta * slopes[i]

    # 4. Convert tangents to Bezier control points. For each segment, the
    # control x-offset is 1/3 of segment width; the y-offset is that same
    # 1/3 width scaled by the anchor's tangent (slope).
    parts: list[str] = [f"M{projected[0][0]},{projected[0][1]}"]
    for i in range(n - 1):
        x_prev, y_prev = projected[i]
        x_cur, y_cur = projected[i + 1]
        seg_dx = (x_cur - x_prev) / 3
        c1x = round(x_prev + seg_dx)
        c1y = round(y_prev + tangents[i] * seg_dx)
        c2x = round(x_cur - seg_dx)
        c2y = round(y_cur - tangents[i + 1] * seg_dx)
        parts.append(f"C{c1x},{c1y} {c2x},{c2y} {x_cur},{y_cur}")
    return " ".join(parts)


def _build_area_polygon_points(projected: list[tuple[int, int]], baseline_y: int) -> str:
    """Close the polyline into a filled area polygon along the baseline."""
    if not projected:
        return ""
    pts = list(projected)
    first_x = pts[0][0]
    last_x = pts[-1][0]
    pts.append((last_x, baseline_y))
    pts.append((first_x, baseline_y))
    return " ".join(f"{x},{y}" for x, y in pts)


def _build_area_path(projected: list[tuple[int, int]], baseline_y: int) -> str:
    """Build a closed bezier path for the area fill under a smooth curve."""
    if not projected:
        return ""
    curve = _build_bezier_path(projected)
    last_x = projected[-1][0]
    first_x = projected[0][0]
    return f"{curve} L{last_x},{baseline_y} L{first_x},{baseline_y} Z"


# ── Cellular area-fill (v2 star chart) ────────────────────────────────────
#
# Round 6 / Issue G replaces the v1 left-teal / right-amethyst flank cells with
# an area-fill approach: cells exist ONLY under the data polyline, with
# brightness encoding vertical proximity to the curve. The chart's chromatic
# identity migrates from border decoration to area substrate.
#
# Returns structured dicts per Invariant 6 (zero SVG strings in Python). The
# template renders each cell as a <rect> with the supplied class for animation
# cadence (b1/b2/b3/b4 — 4-phase breathe staggered 0/1.5/3/4.5s). Animation
# classes are declared in chart/cellular-defs.j2 with the namespaced
# @keyframes breathe-chart definition (4-stop timing for chart's bloom rhythm).

# Animation class rotation. Cycles through 4 phase-staggered breathe variants
# to break sync-beating across the cell grid. v0.3.0 visual refresh consolidated
# the prior 5-class system (cc1/cc2/cc3/cc4/ccf) to 4 — the dropped 'ccf' fast
# variant wasn't matching either prototype's pulse character and added
# unnecessary visual complexity to the cell grid.
_AREA_CELL_CLASSES: tuple[str, ...] = ("b1", "b2", "b3", "b4")

# Cellular automata chart algorithm constants.
#
# Round 14: smooth-ombré + tiny-noise approach. The position gradient
# (col_norm * 0.6 + row_from_top_norm * 0.4) produces a continuous trend
# from bottom-left dim → top-right bright; small ±0.08 perturbation per
# cell adds organic variance. The chart_levels list serves as 6 control
# points on a gradient ramp; per-cell `frac` values position each cell
# continuously between two adjacent control points via _lerp_rgb.
#
# Earlier rounds used neighbor smoothing (storing a 2D float grid and
# averaging with left/above neighbors). That approach amplified isolated
# noise nudges into vertical dark bands — once a cell got -1 noise, its
# rightward and downward neighbors averaged with the darker value and
# propagated the dim into 2-3 column-wide slices. Smooth gradient + tiny
# noise has no propagation chain, so isolated noise stays isolated.
_CHART_LEVEL_COUNT: int = 6
# Two independent multiplicative hash constants for breaking row/column
# correlation. The previous `(col * 7 + row * 13) * K` form was linear in
# (col, row), so for any fixed row the hash walked through evenly-spaced
# values as col incremented — producing visible horizontal periodicity.
# XORing two independent multiplications destroys that linearity since XOR
# has no algebraic distributivity over addition.
_CHART_HASH_COL_MULT: int = 2654435761  # Knuth's golden ratio hash constant
_CHART_HASH_ROW_MULT: int = 340573321  # second prime, no shared factors
_CHART_HASH_SALT: int = 0xDEAD  # non-zero so corner cell (0,0) doesn't hash to 0
# Noise amplitude range. ±0.08 is HALF a chart_levels segment (1/6 ≈ 0.167);
# large enough to push some cells across a control-point boundary creating
# cell-to-cell variation, small enough that the position gradient stays the
# dominant signal so adjacent cells have visually similar colors.
_CHART_NOISE_AMPLITUDE: float = 0.16
# Inset between cells (cell_size - inset = rendered cell width). v0.3.0 visual
# refresh sets this to 1 to match the v2 prototype's 18x18 cells in 19px stride
# (1px hairline between cells). Earlier rounds used 0 (edge-to-edge), but the
# v2 prototype's slight gap reads as a deliberate cellular grid boundary
# rather than visual noise — the chart operates at a denser 30-col x 13-row
# grid (vs prior 18x10) where the per-cell boundary is what carries the
# cellular automata identity.
_CHART_CELL_INSET: int = 1


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Parse "#RRGGBB" into an (r, g, b) integer tuple. Tolerates "#rgb"
    shorthand and missing leading hash. Returns (0, 0, 0) for malformed input
    rather than raising — the caller is rendering visuals, not parsing config."""
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def _lerp_rgb(c0: str, c1: str, t: float) -> str:
    """Linear interpolate between two hex colors in RGB space at fraction t∈[0,1].
    Returns "#RRGGBB". Used by the chart cell glow algorithm so the chromatic
    gradient between edge_color and peak_color is continuous instead of
    quantized into 5 discrete tiers."""
    t = max(0.0, min(1.0, t))
    r0, g0, b0 = _hex_to_rgb(c0)
    r1, g1, b1 = _hex_to_rgb(c1)
    r = round(r0 + (r1 - r0) * t)
    g = round(g0 + (g1 - g0) * t)
    b = round(b0 + (b1 - b0) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _polyline_y_at(x: int, projected: list[tuple[int, int]]) -> int | None:
    """Linear-interpolated polyline y at the given x. Returns None outside
    the projected x-range — caller decides whether to fill or skip the cell."""
    if not projected:
        return None
    if x < projected[0][0] or x > projected[-1][0]:
        return None
    for i in range(len(projected) - 1):
        x0, y0 = projected[i]
        x1, y1 = projected[i + 1]
        if x0 <= x <= x1:
            if x1 == x0:
                return y0
            t = (x - x0) / (x1 - x0)
            return round(y0 + t * (y1 - y0))
    return projected[-1][1]


def compute_dormant_cells(
    vp: Viewport,
    dormant_range: list[str],
    *,
    cell_size: int = 40,
) -> list[dict[str, Any]]:
    """Compute the dormant cell substrate that softens the chart's void area.

    Returns a flat tile of cells covering the FULL viewport (no clipping) with
    very-dark colors interpolated between dormant_range[0] (low) and
    dormant_range[1] (high). Each cell's interpolation fraction comes from a
    seeded hash so the dormant grid has subtle per-cell variation rather than
    a single solid fill, but the entire range stays at 2-5% luminance —
    barely distinguishable from black until you look closely.

    Purpose: the area ABOVE the polyline (where the bright cell layer is
    clipped away) gets a faint warm/cool undertone matching the variant's
    tone family instead of pure surface_0 black. This softens the clip
    boundary so the chart reads as one heated surface where the data zone
    glows brighter, instead of two discrete regions cut out of pure void.

    No animation classes — dormant is structural background, not living signal.
    """
    if len(dormant_range) != 2:
        return []
    low_color, high_color = dormant_range
    cells: list[dict[str, Any]] = []
    n_cols = (vp.w + cell_size - 1) // cell_size
    n_rows = (vp.h + cell_size - 1) // cell_size
    inner_size = cell_size - _CHART_CELL_INSET
    for col in range(n_cols):
        for row in range(n_rows):
            cx = vp.x + col * cell_size
            cy = vp.y + row * cell_size
            # Same XOR-mix hash as the active layer — uncorrelated noise
            # avoids horizontal periodicity in the dormant texture too.
            mixed = (col * _CHART_HASH_COL_MULT) ^ (row * _CHART_HASH_ROW_MULT) ^ _CHART_HASH_SALT
            hash_val = ((mixed >> 16) ^ mixed) & 0xFF
            frac = hash_val / 255.0
            fill = _lerp_rgb(low_color, high_color, frac)
            cells.append({"x": cx, "y": cy, "w": inner_size, "h": inner_size, "fill": fill})
    return cells


def compute_cellular_chart_cells(
    projected: list[tuple[int, int]],
    vp: Viewport,
    chart_levels: list[str],
    *,
    cell_size: int = 40,
) -> dict[str, Any]:
    """Compute cellular automata chart cells via smooth ombré + tiny noise.

    Cells exist ONLY under the polyline (clipped to a smooth-bezier polygon
    closed to the baseline). Each cell's color comes from:

    1. **Position gradient** — t = col_norm * 0.6 + row_from_top * 0.4 drives
       a continuous trend bottom-left dim → top-right bright. This IS the
       ombré: adjacent cells differ by ~5% in t (one step of grid resolution),
       so their colors differ by exactly the corresponding gradient step.
    2. **±0.08 hash perturbation** — a small per-cell offset from Knuth's
       multiplicative hash adds organic variance without producing outliers.
       At ±0.08 (half of one chart_levels segment width), some cells cross
       a control-point boundary while most stay within their gradient zone.
    3. **Continuous lerp through chart_levels** — the resulting `t ∈ [0, 1]`
       maps to a position between adjacent chart_levels stops via _lerp_rgb,
       so chart_levels acts as 6 control points on a gradient ramp rather
       than a quantized palette.

    No neighbor propagation. Earlier rounds averaged each cell with its
    left + above neighbors, but isolated noise nudges (e.g., -1 level)
    cascaded down/rightward chains creating visible 2-3 column-wide dark
    bands. Smooth gradient + tiny noise has no propagation, so isolated
    cells stay isolated and the surface flows continuously.

    Returns a dict with:
    - ``cells``: list of {x, y, w, h, fill, anim_class} dicts. Cells render
      edge-to-edge (40x40, inset=0) so color difference is the only visible
      boundary between neighbors. Animation classes cycled by index.
    - ``clip_path_d``: bezier-following path closed to baseline; cells outside
      the polyline polygon are masked at render time.
    """
    if not projected or len(chart_levels) != _CHART_LEVEL_COUNT:
        return {"cells": [], "clip_path_d": ""}

    baseline_y = vp.y + vp.h
    # ClipPath: smooth bezier following the polyline, closed to baseline.
    bezier_d = _build_bezier_path(projected)
    last_x = projected[-1][0]
    first_x = projected[0][0]
    if not bezier_d:
        return {"cells": [], "clip_path_d": ""}
    clip_path_d = f"{bezier_d} L {last_x} {baseline_y} L {first_x} {baseline_y} Z"

    # Tile cells across viewport. Ceiling division so the bottom row reaches
    # the baseline even when vp.h isn't a clean multiple of cell_size.
    n_cols = (vp.w + cell_size - 1) // cell_size
    n_rows = (vp.h + cell_size - 1) // cell_size
    col_div = max(1, n_cols - 1)
    row_div = max(1, n_rows - 1)
    inner_size = cell_size - _CHART_CELL_INSET
    max_level_idx = _CHART_LEVEL_COUNT - 1

    cells: list[dict[str, Any]] = []
    cell_idx = 0
    for col in range(n_cols):
        for row in range(n_rows):
            cx = vp.x + col * cell_size
            cy = vp.y + row * cell_size

            # Smooth position gradient — col*0.6 + (1-row)*0.4 → t ∈ [0, 1].
            # Top-right (high col, low row) → t near 1.0 (brightest);
            # bottom-left → t near 0.0 (darkest).
            col_norm = col / col_div
            row_from_top = 1.0 - (row / row_div)
            base = col_norm * 0.6 + row_from_top * 0.4

            # Tiny ±0.08 perturbation. XOR-mix hash breaks row/column
            # correlation: independent multiplications combined via XOR can't
            # be reduced to a linear function of (col, row), so adjacent cells
            # produce uncorrelated noise values. The right-shift-then-XOR
            # finalization mixes high bits (which carry the most entropy from
            # the multiplications) into the low byte before masking.
            mixed = (col * _CHART_HASH_COL_MULT) ^ (row * _CHART_HASH_ROW_MULT) ^ _CHART_HASH_SALT
            hash_val = ((mixed >> 16) ^ mixed) & 0xFF
            noise = (hash_val / 255.0 - 0.5) * _CHART_NOISE_AMPLITUDE

            # Clamp t into [0, 0.9999] — the upper clamp keeps int(scaled)
            # at most max_level_idx-1, so hi = lo+1 always selects a valid
            # adjacent stop without needing a special case at t=1.0.
            t = max(0.0, min(0.9999, base + noise))
            scaled = t * max_level_idx
            level_lo = int(scaled)
            level_hi = min(level_lo + 1, max_level_idx)
            frac = scaled - level_lo
            fill = _lerp_rgb(chart_levels[level_lo], chart_levels[level_hi], frac)

            anim_class = _AREA_CELL_CLASSES[cell_idx % len(_AREA_CELL_CLASSES)]
            cells.append(
                {
                    "x": cx,
                    "y": cy,
                    "w": inner_size,
                    "h": inner_size,
                    "fill": fill,
                    "anim_class": anim_class,
                }
            )
            cell_idx += 1

    return {"cells": cells, "clip_path_d": clip_path_d}


def compute_marker_color_progression(
    projected: list[tuple[int, int]],
    chart_levels: list[str],
) -> list[str]:
    """Smooth color progression for chart markers, indexed by position along curve.

    Returns a list of hex colors with length == len(projected). Marker[0] uses
    chart_levels[0] (darkest), marker[n-1] uses chart_levels[5] (brightest),
    with smooth RGB lerp between them. Endpoint marker is rendered separately
    by the template (always white).

    Cobalt-sapphire pattern: each marker tints its drop-shadow with the same
    color as its fill so the glow rhymes with the marker tone, building visual
    continuity across the curve.
    """
    if not projected or len(chart_levels) != _CHART_LEVEL_COUNT:
        return []
    n = len(projected)
    if n == 1:
        return [chart_levels[-1]]
    edge = chart_levels[0]
    peak = chart_levels[-1]
    return [_lerp_rgb(edge, peak, i / (n - 1)) for i in range(n)]


# ── Marker builders (structured output; rendered by Jinja partials) ────────
#
# Per Invariant 6 (zero f-string SVG in Python), marker geometry is emitted
# as structured dicts and rendered by partials under
# ``templates/components/chart-markers/{shape}.svg.j2``. Template dispatch
# via slug interpolation matches Invariant 12's include pattern:
#
#   {% set partial = 'endpoint-' ~ m.shape if m.is_endpoint else m.shape %}
#   {% include "components/chart-markers/" ~ partial ~ ".svg.j2" %}
#
# Each dict carries pre-computed derived dimensions so partials stay pure
# substitution — no arithmetic lives in the template.

_MARKER_SHAPES: frozenset[str] = frozenset({"square", "rect", "circle", "diamond"})


def _marker_spec(shape: str, x: int, y: int, size: int, *, is_endpoint: bool) -> dict[str, Any]:
    """Build the render dict for a single marker.

    Normalizes legacy aliases (``"square"`` → ``"rect"``), pre-computes the
    dimensions each partial needs, and flags the endpoint variant. Unknown
    shapes fall back to ``"rect"`` to preserve the old ``_MARKER_BUILDERS.get``
    behavior.
    """
    # Aliases + unknown-shape fallback (parity with the old dispatch dicts).
    if shape == "square" or shape not in _MARKER_SHAPES:
        shape = "rect"
    # Circle endpoint has no dedicated partial in the old code either — the
    # endpoint dispatch only covered rect/diamond. Fall back to rect so a
    # genome with data_point_shape="circle" still gets a visible endpoint.
    if is_endpoint and shape == "circle":
        shape = "rect"

    spec: dict[str, Any] = {"shape": shape, "x": x, "y": y, "size": size, "is_endpoint": is_endpoint}

    # Pre-compute derived dimensions per shape so the partials are pure
    # substitution — no arithmetic in Jinja.
    if shape == "circle":
        spec["r"] = max(1, size // 2)
    elif is_endpoint and shape == "rect":
        # 3 nested squares (brutalist endpoint beacon).
        s1, s2, s3 = size + 8, size + 2, max(4, size - 4)
        spec.update({"s1": s1, "s2": s2, "s3": s3, "h1": s1 // 2, "h2": s2 // 2, "h3": s3 // 2})
    elif is_endpoint and shape == "diamond":
        # 2-layer rotated rects (chrome endpoint diamond).
        s1, s2 = size + 10, size + 5
        spec.update({"s1": s1, "s2": s2, "h1": s1 // 2, "h2": s2 // 2})
    else:
        # rect + diamond (non-endpoint): crosshair geometry.
        spec.update({"half": size // 2, "cross": max(2, size // 5)})
    return spec


def _build_markers(
    projected: list[tuple[int, int]],
    shape: str,
    size: int,
) -> list[dict[str, Any]]:
    """Return a list of marker render dicts for each projected point.

    Regular data points use the standard marker for ``shape``. The final
    point uses the endpoint variant (nested squares for rect, larger
    glowing diamond for diamond) to visually mark "now." Templates loop
    this list and ``{% include %}`` the appropriate partial per entry.
    """
    if not projected:
        return []
    markers = [_marker_spec(shape, x, y, size, is_endpoint=False) for x, y in projected[:-1]]
    x_last, y_last = projected[-1]
    markers.append(_marker_spec(shape, x_last, y_last, size, is_endpoint=True))
    return markers


# ── Axes + gridlines + milestones (structured data; rendered by Jinja) ────
#
# Per Invariant 6, every visual element here returns a dict or list[dict]
# instead of a pre-rendered SVG string. Chart content templates consume the
# shapes via ``{% include %}`` partials under ``templates/components/``.

# Minimum horizontal pixel gap between two milestone labels. Clustered
# crossings (e.g. mega-repos where 500, 1K, 5K, 10K all happen in the same
# early-history window) would otherwise render labels stacked on top of each
# other. We keep only the first milestone in any cluster.
MILESTONE_MIN_GAP_PX: int = 40


def _build_axes(vp: Viewport) -> list[dict[str, Any]]:
    """L-frame axes at the viewport's left and bottom edges."""
    bottom_y = vp.y + vp.h
    return [
        {"x1": vp.x, "y1": bottom_y, "x2": vp.x + vp.w, "y2": bottom_y},
        {"x1": vp.x, "y1": vp.y, "x2": vp.x, "y2": bottom_y},
    ]


def _build_gridlines(vp: Viewport, rows: int = 4) -> list[dict[str, Any]]:
    """Horizontal gridlines evenly spaced across the viewport."""
    if rows <= 0:
        return []
    lines: list[dict[str, Any]] = []
    for i in range(1, rows + 1):
        y = vp.y + round(vp.h * i / (rows + 1))
        lines.append({"x1": vp.x, "y1": y, "x2": vp.x + vp.w, "y2": y})
    return lines


def _build_gridlines_from_ticks(
    y_labels: list[dict[str, Any]],
    vp: Viewport,
) -> list[dict[str, Any]]:
    """Horizontal gridlines at each Y-tick's Y-position.

    Used when real data is present — gridlines align to tick labels
    instead of floating at arbitrary ``vp.h / (rows + 1)`` positions.
    """
    return [{"x1": vp.x, "y1": int(label["y"]), "x2": vp.x + vp.w, "y2": int(label["y"])} for label in y_labels]


def _build_milestones(
    points: list[ChartPoint],
    projected: list[tuple[int, int]],
    vp: Viewport,
    thresholds: list[int],
) -> list[dict[str, Any]]:
    """Vertical marker lines at points where value crosses a threshold.

    Walks the series in order and emits a marker the first time a point's
    value meets or exceeds each threshold. After all crossings are found,
    applies de-overlap: milestones within ``MILESTONE_MIN_GAP_PX`` of an
    already-kept milestone are dropped so labels never stack (e.g. the
    openclaw mega-repo's ``500``/``1K``/``5K``/``10K`` cluster that
    rendered as an illegible pile before this fix).
    """
    if not points or not projected or not thresholds:
        return []

    bottom_y = vp.y + vp.h
    # Start one below the first value so we only mark *crossings*, not the
    # initial position. This mirrors how github-readme-stats draws milestones.
    last_val = points[0].value - 1
    raw: list[dict[str, Any]] = []
    for idx, p in enumerate(points):
        px, py = projected[idx]
        for t in thresholds:
            if last_val < t <= p.value:
                threshold_label = f"{t // 1000}K" if t >= 1000 else str(t)
                # Date suffix in `MMM YY` form (e.g. "APR 25") matches the
                # v0.3.2 brutalist chart prototypes' milestone label cadence
                # — `1K · APR 25` / `2K · NOV 25`. Skipping the apostrophe
                # before the year mirrors the prototype's literal string.
                date_suffix = p.date.strftime("%b %y").upper().lstrip("0")
                label = f"{threshold_label} · {date_suffix}"
                raw.append(
                    {
                        "x": px,
                        "y": py,
                        "bottom_y": bottom_y,
                        "label": label,
                        "value": t,
                    }
                )
        last_val = p.value

    # De-overlap: keep only the first crossing in any x-cluster so labels
    # stay legible when the polyline climbs rapidly through many thresholds.
    kept: list[dict[str, Any]] = []
    last_x = -(10**9)
    for ms in sorted(raw, key=lambda m: m["x"]):
        if ms["x"] - last_x >= MILESTONE_MIN_GAP_PX:
            kept.append(ms)
            last_x = ms["x"]
    return kept


# ── Axis label computation ─────────────────────────────────────────────────


def _nice_y_ticks(v_max: int, target_count: int = 4) -> list[int]:
    """Compute round tick values from ``0`` up to or just past ``v_max``.

    Picks a "nice" step (1, 2, 5, or 10 scaled by a power of 10) so labels
    land on round numbers regardless of the actual maximum. Used for both Y-axis text labels and
    gridline positions, so labels and gridlines always agree.

    Examples:
        v_max=6    → [0, 2, 4, 6]
        v_max=30   → [0, 10, 20, 30]
        v_max=2850 → [0, 1000, 2000, 3000]
        v_max=0    → [0]
    """
    if v_max <= 0:
        return [0]
    raw_step = max(v_max / target_count, 1.0)
    exp = math.floor(math.log10(raw_step))
    f = raw_step / (10**exp)
    if f <= 1:
        nf = 1.0
    elif f <= 2:
        nf = 2.0
    elif f <= 5:
        nf = 5.0
    else:
        nf = 10.0
    step = max(1, int(nf * (10**exp)))
    nice_max = int(math.ceil(v_max / step) * step)
    return list(range(0, nice_max + 1, step))


def _format_y_tick(value: int) -> str:
    """Format tick value: ``< 1000`` → integer, ``>= 1000`` → K notation.

    Examples: 0 → "0", 6 → "6", 1000 → "1K", 1500 → "1.5K", 10000 → "10K".
    Sibling of the hero-value ``_format_compact`` in chart.py, but breaks at
    1K instead of 10K since tick labels are tighter.
    """
    if value < 1000:
        return str(value)
    s = f"{value / 1000:.1f}".rstrip("0").rstrip(".")
    return f"{s}K"


def _build_y_labels(ticks: list[int], v_min: int, v_max: int, vp: Viewport) -> list[dict[str, Any]]:
    """Project tick values into ``{y, text}`` dicts for template consumption.

    Uses the same (v_min, v_max) range the caller passes to
    :func:`_project_points`, so the labels and data points share a coordinate
    system. The template positions the X coordinate itself (paradigm-specific).
    """
    if not ticks:
        return []
    v_span = max(1, v_max - v_min)
    out: list[dict[str, Any]] = []
    for t in ticks:
        frac_v = (t - v_min) / v_span
        py = vp.y + vp.h - round(frac_v * vp.h)
        out.append({"y": py, "text": _format_y_tick(t)})
    return out


# Width-aware label collision constants. The previous fixed 48px center-to-center
# gap let monthly labels ("Apr 2026", ~58px wide) overlap by ~10px on adjacent ticks
# even when the gap "rule" passed. We now compute each label's actual rendered
# bounding box and check edge-to-edge separation.

# Conservative per-character width covering the widest paradigm (brutalist:
# 9px sans-serif + 0.20em letter-spacing + uppercase). Cellular and chrome
# render narrower, so this estimate is a safe upper bound for all genome
# paradigms — it never under-estimates collision.
_LABEL_CHAR_WIDTH_PX: float = 7.5

# Minimum visual gap between two label bounding boxes. Smaller than the full
# character width — readers tolerate close-packed labels as long as the glyphs
# don't actually touch.
_LABEL_EDGE_PADDING_PX: float = 6.0


def _label_pixel_width(text: str) -> float:
    """Worst-case rendered width of `text` in pixels."""
    return len(text) * _LABEL_CHAR_WIDTH_PX


def _label_bounds(label: dict[str, Any]) -> tuple[float, float]:
    """Return (left_edge_px, right_edge_px) for a generated label dict.

    Honors the SVG `text-anchor` semantics: 'start' anchors the left edge
    at x, 'end' anchors the right edge at x, 'middle' centers the text on x.
    """
    x = float(label["x"])
    w = _label_pixel_width(str(label["text"]))
    anchor = label.get("anchor", "middle")
    if anchor == "start":
        return (x, x + w)
    if anchor == "end":
        return (x - w, x)
    return (x - w / 2, x + w / 2)


def _labels_collide(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """True if `right`'s left edge is closer than padding to `left`'s right edge."""
    _, left_right = _label_bounds(left)
    right_left, _ = _label_bounds(right)
    return right_left < left_right + _LABEL_EDGE_PADDING_PX


def _build_x_date_labels(points: list[ChartPoint], vp: Viewport) -> list[dict[str, Any]]:
    """Adaptive x-axis date labels — granularity follows the data's temporal span.

    Tick formats:
        < 14 days  → daily   ("Apr 05")
        < 90 days  → weekly  ("Apr 05" at 7-day steps)
        < 2 years  → monthly ("Apr 2026")
        < 10 years → yearly  ("2026")
        else       → every other year ("2012", "2014", ...)

    A single-point input renders one centered label with full "%b %d, %Y".
    After candidate generation, a width-aware de-overlap pass removes any
    middle label whose bounding box would touch the previously-kept one
    (see ``_labels_collide``). The first and last labels are preserved
    unconditionally because they're the temporal endpoints a reader
    expects to see.
    """
    if not points:
        return []
    if len(points) == 1:
        p = points[0]
        return [{"x": vp.x + vp.w // 2, "text": p.date.strftime("%b %d, %Y"), "anchor": "middle"}]

    t0 = points[0].date
    t1 = points[-1].date
    span = t1 - t0

    # Select granularity + format from the actual span.
    if span < timedelta(days=14):
        format_str = "%b %d"
        step = timedelta(days=1)
    elif span < timedelta(days=90):
        format_str = "%b %d"
        step = timedelta(days=7)
    elif span < timedelta(days=730):
        format_str = "%b %Y"
        step = timedelta(days=30)  # ≈ 1 month
    elif span < timedelta(days=3650):
        format_str = "%Y"
        step = timedelta(days=365)
    else:
        format_str = "%Y"
        step = timedelta(days=730)  # every other year

    # Generate candidate ticks, projecting each to pixel x via the same scale
    # as the polyline so labels sit directly under their corresponding data.
    t_span_s = max(span.total_seconds(), 1.0)
    candidates: list[dict[str, Any]] = []
    cursor = t0
    while cursor <= t1:
        frac_t = (cursor - t0).total_seconds() / t_span_s
        px = vp.x + round(frac_t * vp.w)
        candidates.append({"x": px, "text": cursor.strftime(format_str), "anchor": "middle"})
        cursor = cursor + step

    # Ensure the terminal endpoint is in the candidate set (may not land on a
    # step boundary otherwise).
    last_px = vp.x + vp.w
    if not candidates or candidates[-1]["x"] < last_px - 2:
        candidates.append({"x": last_px, "text": t1.strftime(format_str), "anchor": "end"})

    # First label flush with the y-axis for a cleaner left edge.
    candidates[0]["anchor"] = "start"

    # De-overlap: preserve first + last; drop any middle label whose
    # bounding box would touch the previously-kept one. Edge-to-edge
    # collision (not center-to-center) so labels of different widths
    # (e.g. monthly "Apr 2026" vs yearly "2026") behave correctly.
    if len(candidates) <= 2:
        return candidates
    kept: list[dict[str, Any]] = [candidates[0]]
    for label in candidates[1:-1]:
        if not _labels_collide(kept[-1], label):
            kept.append(label)
    # The terminal endpoint is always included. If it would collide with
    # the last-kept middle label, or has identical text (e.g. yearly
    # granularity where the last jan-1 tick and the terminal point both
    # read "2026"), replace that middle rather than duplicating.
    last_candidate = candidates[-1]
    same_text = last_candidate["text"] == kept[-1]["text"]
    if same_text or _labels_collide(kept[-1], last_candidate):
        kept[-1] = last_candidate
    else:
        kept.append(last_candidate)
    return kept


def _build_empty_state(vp: Viewport, message: str) -> dict[str, Any] | None:
    """Return structured data for the centered empty-state overlay, or None.

    Used for zero-star repos ("NEW REPO · NO STARS YET") and upstream-failure
    cases ("DATA UNAVAILABLE"). Templates render the ``<g data-hw-zone>``
    wrapper and text element from the fields below.
    """
    if not message:
        return None
    return {
        "x": vp.x + vp.w // 2,
        "y": vp.y + vp.h // 2,
        "text": message,
    }


# ── Public API ─────────────────────────────────────────────────────────────


def build_chart_svg(
    raw_points: list[Any],
    viewport: Viewport,
    structural: dict[str, Any] | None = None,
    *,
    milestones: list[int] | None = None,
    empty_message: str | None = None,
    cellular_chart_levels: list[str] | None = None,
    cellular_dormant_range: list[str] | None = None,
    cellular_cell_size: int = 40,
    y_tick_target: int = 4,
) -> dict[str, Any]:
    """Render a set of time-series points into SVG fragment strings + label data.

    Args:
        raw_points: connector-shaped point list (dicts or tuples). See
            ``_normalize_points``.
        viewport: drawing rectangle inside the host SVG.
        structural: genome structural dict. Respected keys:

            - ``stroke_linejoin``: ``"miter"`` or ``"round"``. Selects polyline
              vs bezier path rendering.
            - ``data_point_shape``: ``"square"`` | ``"circle"`` | ``"diamond"``.
              Default ``"square"``.
            - ``data_point_size``: int pixel size. Default ``5``.
            - ``fill_density``: ``"solid-area"`` | ``"bezier-smooth"`` | ``"none"``.
              Default ``"solid-area"``.
        milestones: integer thresholds to mark on the chart (e.g. ``[500, 1000, 2000]``).
        empty_message: when there is no data to plot, overlay this text in the
            chart area (e.g. ``"NEW REPO · NO STARS YET"``). Ignored when points
            are present.

    Returns:
        Dict keyed by zone name. String fragments: ``defs``, ``axes``,
        ``gridlines``, ``area``, ``polyline``, ``markers``, ``milestones``,
        ``empty_state``. Structured label data: ``y_labels`` (list of
        ``{"y": int, "text": str}``), ``x_labels`` (list of
        ``{"x": int, "text": str, "anchor": "start" | "middle" | "end"}``).
        Templates compose string fragments with ``{{ ... | safe }}`` and loop
        over label data.
    """
    structural = structural or {}
    points = _normalize_points(raw_points)

    # Compute nice ticks FIRST so label positions, gridlines, and the projected
    # polyline all share the same coordinate basis. Without this the "0" label
    # and the polyline's baseline only agree by coincidence.
    if points:
        v_max = max(p.value for p in points)
        ticks = _nice_y_ticks(v_max, target_count=y_tick_target)
        effective_max = ticks[-1] if ticks else max(v_max, 1)
        y_labels = _build_y_labels(ticks, 0, effective_max, viewport)
        x_labels = _build_x_date_labels(points, viewport)
        # Project with zero-baseline so the polyline aligns to the tick labels.
        projected = _project_points(points, viewport, v_min=0, v_max=effective_max)
    else:
        projected = []
        # Empty state: show a single "0" anchored at the baseline.
        y_labels = [{"y": viewport.y + viewport.h, "text": "0"}]
        x_labels = []

    linejoin = str(structural.get("stroke_linejoin", "miter"))
    shape = str(structural.get("data_point_shape", "square"))
    point_size = int(structural.get("data_point_size", 5))
    fill_density = str(structural.get("fill_density", "solid-area"))

    baseline_y = viewport.y + viewport.h

    # Polyline vs bezier — structured for the chart-polyline partial.
    polyline_spec: dict[str, Any] | None = None
    if linejoin == "round":
        polyline_attr = _build_bezier_path(projected)
        if polyline_attr:
            polyline_spec = {"kind": "path", "d": polyline_attr}
    else:
        polyline_attr = _build_polyline_points(projected)
        if polyline_attr:
            polyline_spec = {"kind": "polyline", "points": polyline_attr}

    # Area fill — structured for the chart-area partial.
    area_spec: dict[str, Any] | None = None
    if fill_density == "solid-area":
        pts = _build_area_polygon_points(projected, baseline_y)
        if pts:
            area_spec = {"kind": "polygon", "points": pts}
    elif fill_density == "bezier-smooth":
        path_d = _build_area_path(projected, baseline_y)
        if path_d:
            area_spec = {"kind": "path", "d": path_d}

    markers = _build_markers(projected, shape, point_size)
    axes = _build_axes(viewport)
    # Gridlines aligned to ticks when data exists; uniform fallback otherwise.
    if points and y_labels:
        gridlines = _build_gridlines_from_ticks(y_labels, viewport)
    else:
        gridlines = _build_gridlines(viewport, rows=4)
    milestones_list = _build_milestones(points, projected, viewport, milestones or [])

    # Empty state overlay: only when there are no data points AND a message
    # was provided. Without a message the chart degrades silently (useful for
    # embedded charts in stats.py that don't need a user-facing label).
    empty_state = _build_empty_state(viewport, empty_message or "") if not points else None

    # Cellular automata chart substrate (Round 13). Three layers:
    #   - dormant_cells: full-viewport tile in near-black tone-family hues,
    #     softens the clip boundary so the void area above the curve reads as
    #     warm undertone instead of pure black.
    #   - cells (active): edge-to-edge cells with continuous interpolation
    #     between chart_levels control points; clipped to bezier-baseline
    #     polygon. Neighbor smoothing creates organic regions; per-cell hash
    #     micro-noise + level interpolation creates the texture within regions.
    #   - marker_colors: per-position color progression along the curve.
    # Only computed when caller supplies chart_levels — brutalist + chrome
    # leave it None and get empty defaults.
    cellular_area: dict[str, Any] = {
        "cells": [],
        "clip_path_d": "",
        "marker_colors": [],
        "dormant_cells": [],
    }
    if cellular_chart_levels:
        dormant_cells: list[dict[str, Any]] = []
        if cellular_dormant_range:
            dormant_cells = compute_dormant_cells(viewport, cellular_dormant_range, cell_size=cellular_cell_size)
        if projected:
            bright = compute_cellular_chart_cells(
                projected, viewport, cellular_chart_levels, cell_size=cellular_cell_size
            )
            marker_colors = compute_marker_color_progression(projected, cellular_chart_levels)
            cellular_area = {**bright, "marker_colors": marker_colors, "dormant_cells": dormant_cells}
        else:
            # Empty/zero state — dormant still renders so the chart isn't visually empty.
            cellular_area = {
                "cells": [],
                "clip_path_d": "",
                "marker_colors": [],
                "dormant_cells": dormant_cells,
            }

    return {
        "defs": "",
        "axes": axes,
        "gridlines": gridlines,
        "area": area_spec,
        "polyline": polyline_spec,
        "markers": markers,
        "milestones": milestones_list,
        "y_labels": y_labels,
        "x_labels": x_labels,
        "empty_state": empty_state,
        "cellular_area": cellular_area,
    }
