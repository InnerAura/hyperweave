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
from datetime import UTC, datetime
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
                label = f"{t // 1000}K" if t >= 1000 else str(t)
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


def _build_x_year_labels(points: list[ChartPoint], vp: Viewport) -> list[dict[str, Any]]:
    """Return year-string labels positioned at jan-1 boundaries in the data range.

    Matches star-history.com's convention: just year numbers (2024, 2025, 2026)
    at the X positions where each year begins. No "EARLY '24", "MID '25", etc.

    Single-year spans collapse to one label at the viewport center.
    """
    if not points:
        return []
    y_start = points[0].date.year
    y_end = points[-1].date.year
    if len(points) == 1 or y_start == y_end:
        return [{"x": vp.x + vp.w // 2, "text": str(y_start), "anchor": "middle"}]

    t0 = points[0].date.timestamp()
    t1 = points[-1].date.timestamp()
    t_span = max(1.0, t1 - t0)

    labels: list[dict[str, Any]] = [{"x": vp.x, "text": str(y_start), "anchor": "start"}]
    for y in range(y_start + 1, y_end + 1):
        jan1 = datetime(y, 1, 1, tzinfo=UTC).timestamp()
        if t0 < jan1 <= t1:
            frac = (jan1 - t0) / t_span
            px = vp.x + round(frac * vp.w)
            # Anchor at right-edge if within 20px of viewport right; else middle.
            anchor = "end" if (vp.x + vp.w) - px < 20 else "middle"
            labels.append({"x": px, "text": str(y), "anchor": anchor})
    return labels


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
        ticks = _nice_y_ticks(v_max)
        effective_max = ticks[-1] if ticks else max(v_max, 1)
        y_labels = _build_y_labels(ticks, 0, effective_max, viewport)
        x_labels = _build_x_year_labels(points, viewport)
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
    }
