"""Pure chart rendering primitives.

This module is the shared rendering kernel for the ``chart`` frame (standalone
star history) and the embedded chart zone inside the ``stats`` frame's
``chrome`` paradigm. It takes a list of data points, a viewport rect, and a
small dict of structural hints (``stroke_linejoin``, ``data_point_shape``,
``fill_density``) and returns a dict of SVG fragment strings ready for
templates to concatenate.

Architectural rules (Invariants 1 + 6):
    - Zero network I/O. Fetching happens at the CLI/HTTP layer before compose.
    - Zero CSS. Colors are passed as ``var(--dna-*)`` references by callers.
    - Zero f-string SVG for user data — templates produce the final SVG wrapper,
      this module emits small path/markup fragments via careful string joins.
    - Pure functions. No classes, no state.

Public API:
    :func:`build_chart_svg` is the single entry point. It returns a dict with
    keys ``defs``, ``axes``, ``gridlines``, ``area``, ``polyline``, ``markers``,
    ``milestones`` — each a string fragment (possibly empty). Templates decide
    which fragments to render and in what order.
"""

from __future__ import annotations

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


def _project_points(points: list[ChartPoint], vp: Viewport) -> list[tuple[int, int]]:
    """Project (date, value) points into pixel coordinates inside ``vp``.

    Returns a list of ``(x, y)`` int tuples. X is linear in time; Y is linear
    in value, flipped so y=vp.y is the top of the chart and y=vp.y+vp.h is the
    baseline (value=0).
    """
    if not points:
        return []
    if len(points) == 1:
        # Single point → center of the viewport (no time/value range to map).
        return [(vp.x + vp.w // 2, vp.y + vp.h // 2)]

    t0 = points[0].date.timestamp()
    t1 = points[-1].date.timestamp()
    t_span = max(1.0, t1 - t0)
    v_max = max(p.value for p in points)
    v_min = min(p.value for p in points)
    v_span = max(1, v_max - v_min)

    out: list[tuple[int, int]] = []
    for p in points:
        frac_t = (p.date.timestamp() - t0) / t_span
        frac_v = (p.value - v_min) / v_span
        px = vp.x + round(frac_t * vp.w)
        py = vp.y + vp.h - round(frac_v * vp.h)
        out.append((px, py))
    return out


# ── Path / polyline builders ───────────────────────────────────────────────


def _build_polyline_points(projected: list[tuple[int, int]]) -> str:
    """Return an SVG ``points="x,y x,y ..."`` attribute value."""
    return " ".join(f"{x},{y}" for x, y in projected)


def _build_bezier_path(projected: list[tuple[int, int]]) -> str:
    """Build a smooth cubic bezier path string through the projected points.

    Uses the "Catmull-Rom-ish" trick: each segment's control points are at
    one third of the previous/next delta. This produces a visually smooth
    curve without cornering at every data point — matches the chrome-horizon
    mockup's bezier style.
    """
    if not projected:
        return ""
    if len(projected) == 1:
        x, y = projected[0]
        return f"M{x},{y}"

    parts: list[str] = [f"M{projected[0][0]},{projected[0][1]}"]
    n = len(projected)
    for i in range(1, n):
        x_prev, y_prev = projected[i - 1]
        x_cur, y_cur = projected[i]
        # Horizontal offset for control handles — one third of segment width.
        dx = max(4, (x_cur - x_prev) // 3)
        c1x = x_prev + dx
        c1y = y_prev
        c2x = x_cur - dx
        c2y = y_cur
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


# ── Marker builders ────────────────────────────────────────────────────────


def _marker_rect(x: int, y: int, size: int) -> str:
    """Brutalist crosshair marker: slab-filled rect with cross lines."""
    half = size // 2
    cross = max(2, size // 5)
    return (
        f'<g transform="translate({x},{y})">'
        f'<rect x="-{half}" y="-{half}" width="{size}" height="{size}" '
        f'fill="var(--dna-surface)" stroke="var(--dna-signal-dim,var(--dna-signal))" stroke-width="1"/>'
        f'<line x1="-{cross}" y1="0" x2="{cross}" y2="0" '
        f'stroke="var(--dna-signal-dim,var(--dna-signal))" stroke-width="1"/>'
        f'<line x1="0" y1="-{cross}" x2="0" y2="{cross}" '
        f'stroke="var(--dna-signal-dim,var(--dna-signal))" stroke-width="1"/>'
        f'</g>'
    )


def _marker_circle(x: int, y: int, size: int) -> str:
    r = max(1, size // 2)
    return f'<circle cx="{x}" cy="{y}" r="{r}"/>'


def _marker_diamond(x: int, y: int, size: int) -> str:
    """Chrome diamond marker: white-filled rotated rect with dark stroke."""
    half = size // 2
    return (
        f'<rect x="-{half}" y="-{half}" width="{size}" height="{size}" '
        f'transform="translate({x} {y}) rotate(45)"/>'
    )


_MARKER_BUILDERS = {
    "square": _marker_rect,
    "rect": _marker_rect,
    "circle": _marker_circle,
    "diamond": _marker_diamond,
}


def _marker_endpoint_rect(x: int, y: int, size: int) -> str:
    """Brutalist endpoint beacon: 3 nested squares with pulse class."""
    s1 = size + 8
    s2 = size + 2
    s3 = max(4, size - 4)
    h1, h2, h3 = s1 // 2, s2 // 2, s3 // 2
    return (
        f'<g data-hw-zone="endpoint" shape-rendering="crispEdges">'
        f'<rect class="hw-chart-endpoint" x="{x - h1}" y="{y - h1}" '
        f'width="{s1}" height="{s1}" fill="var(--dna-signal)"/>'
        f'<rect x="{x - h2}" y="{y - h2}" width="{s2}" height="{s2}" '
        f'fill="var(--dna-surface)"/>'
        f'<rect x="{x - h3}" y="{y - h3}" width="{s3}" height="{s3}" '
        f'fill="var(--dna-ink-primary,#D1FAE5)"/>'
        f'</g>'
    )


def _marker_endpoint_diamond(x: int, y: int, size: int) -> str:
    """Chrome endpoint diamond: larger diamond with glow class."""
    s1 = size + 10
    s2 = size + 5
    h1, h2 = s1 // 2, s2 // 2
    return (
        f'<g data-hw-zone="endpoint" transform="translate({x},{y})">'
        f'<rect class="hw-chart-endpoint" x="-{h1}" y="-{h1}" '
        f'width="{s1}" height="{s1}" rx="0.6" transform="rotate(45)" '
        f'fill="#38BDF8"/>'
        f'<rect x="-{h2}" y="-{h2}" width="{s2}" height="{s2}" rx="0.4" '
        f'transform="rotate(45)" fill="#FFFFFF" stroke="#000A14" stroke-width="1"/>'
        f'</g>'
    )


_ENDPOINT_BUILDERS = {
    "square": _marker_endpoint_rect,
    "rect": _marker_endpoint_rect,
    "diamond": _marker_endpoint_diamond,
}


def _build_markers(
    projected: list[tuple[int, int]],
    shape: str,
    size: int,
) -> str:
    """Return an SVG ``<g>`` of marker shapes at each projected point.

    Regular data points use the standard marker builder. The final point
    uses a special endpoint builder (nested squares for brutalist, larger
    glowing diamond for chrome) to visually mark "now."
    """
    builder = _MARKER_BUILDERS.get(shape, _marker_rect)
    endpoint_builder = _ENDPOINT_BUILDERS.get(shape, _marker_endpoint_rect)
    if not projected:
        return ""
    # Regular markers for all points except the last.
    inner = "".join(builder(x, y, size) for x, y in projected[:-1])
    # Endpoint marker for the last point.
    x_last, y_last = projected[-1]
    inner += endpoint_builder(x_last, y_last, size)
    return f'<g data-hw-zone="markers">{inner}</g>'


# ── Axes + gridlines + milestones ──────────────────────────────────────────


def _build_axes(vp: Viewport) -> str:
    """L-frame axes at the viewport's left and bottom edges."""
    return (
        f'<line x1="{vp.x}" y1="{vp.y + vp.h}" x2="{vp.x + vp.w}" y2="{vp.y + vp.h}" '
        f'class="hw-chart-axis"/>'
        f'<line x1="{vp.x}" y1="{vp.y}" x2="{vp.x}" y2="{vp.y + vp.h}" '
        f'class="hw-chart-axis"/>'
    )


def _build_gridlines(vp: Viewport, rows: int = 4) -> str:
    """Horizontal gridlines across the viewport."""
    if rows <= 0:
        return ""
    lines: list[str] = []
    for i in range(1, rows + 1):
        y = vp.y + round(vp.h * i / (rows + 1))
        lines.append(
            f'<line x1="{vp.x}" y1="{y}" x2="{vp.x + vp.w}" y2="{y}" '
            f'class="hw-chart-gridline"/>'
        )
    return "".join(lines)


def _build_milestones(
    points: list[ChartPoint],
    projected: list[tuple[int, int]],
    vp: Viewport,
    thresholds: list[int],
) -> str:
    """Vertical marker lines at points where value crosses a threshold.

    Walks the series in order and emits a marker the first time a point's
    value meets or exceeds each threshold. Thresholds already crossed by the
    series' starting value are skipped.
    """
    if not points or not projected or not thresholds:
        return ""
    # Start one below the first value so we only mark *crossings*, not the
    # initial position. This mirrors how github-readme-stats draws milestones.
    last_val = points[0].value - 1
    out: list[str] = []
    for idx, p in enumerate(points):
        px, py = projected[idx]
        for t in thresholds:
            if last_val < t <= p.value:
                label = f"{t // 1000}K" if t >= 1000 else str(t)
                out.append(
                    f'<line x1="{px}" y1="{py}" x2="{px}" y2="{vp.y + vp.h}" '
                    f'class="hw-chart-milestone-line"/>'
                    f'<text x="{px}" y="{py - 6}" text-anchor="middle" '
                    f'class="hw-chart-milestone-label">{label}</text>'
                )
        last_val = p.value
    return "".join(out)


# ── Public API ─────────────────────────────────────────────────────────────


def build_chart_svg(
    raw_points: list[Any],
    viewport: Viewport,
    structural: dict[str, Any] | None = None,
    *,
    milestones: list[int] | None = None,
) -> dict[str, str]:
    """Render a set of time-series points into SVG fragment strings.

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

    Returns:
        Dict of SVG fragment strings keyed by zone name. All values are plain
        strings (possibly empty). Templates compose these with ``{{ ... | safe }}``.
    """
    structural = structural or {}
    points = _normalize_points(raw_points)
    projected = _project_points(points, viewport)

    linejoin = str(structural.get("stroke_linejoin", "miter"))
    shape = str(structural.get("data_point_shape", "square"))
    point_size = int(structural.get("data_point_size", 5))
    fill_density = str(structural.get("fill_density", "solid-area"))

    baseline_y = viewport.y + viewport.h

    # Polyline vs bezier
    if linejoin == "round":
        polyline_attr = _build_bezier_path(projected)
        polyline_fragment = (
            f'<path d="{polyline_attr}" fill="none" stroke="var(--dna-signal)" '
            f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" '
            f'class="hw-chart-line"/>'
            if polyline_attr
            else ""
        )
    else:
        polyline_attr = _build_polyline_points(projected)
        polyline_fragment = (
            f'<polyline points="{polyline_attr}" fill="none" stroke="var(--dna-signal)" '
            f'stroke-width="2.5" stroke-linejoin="miter" class="hw-chart-line"/>'
            if polyline_attr
            else ""
        )

    # Area fill
    area_fragment = ""
    if fill_density == "solid-area":
        pts = _build_area_polygon_points(projected, baseline_y)
        if pts:
            area_fragment = (
                f'<polygon points="{pts}" fill="var(--dna-signal)" '
                f'fill-opacity="0.65" class="hw-chart-area"/>'
            )
    elif fill_density == "bezier-smooth":
        path_d = _build_area_path(projected, baseline_y)
        if path_d:
            area_fragment = (
                f'<path d="{path_d}" fill="var(--dna-signal)" '
                f'fill-opacity="0.12" class="hw-chart-area-smooth"/>'
            )

    markers_fragment = _build_markers(projected, shape, point_size)
    axes_fragment = _build_axes(viewport)
    gridlines_fragment = _build_gridlines(viewport, rows=4)
    milestones_fragment = _build_milestones(points, projected, viewport, milestones or [])

    return {
        "defs": "",
        "axes": axes_fragment,
        "gridlines": gridlines_fragment,
        "area": area_fragment,
        "polyline": polyline_fragment,
        "markers": markers_fragment,
        "milestones": milestones_fragment,
    }
