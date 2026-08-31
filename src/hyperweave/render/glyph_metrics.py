"""Programmatic ink metrics for registry glyph paths."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from fontTools.pens.boundsPen import BoundsPen
from fontTools.svgLib.path import parse_path


@dataclass(frozen=True, slots=True)
class GlyphInkMetrics:
    """Source-space ink bounds for a glyph path."""

    glyph_id: str
    viewbox_x: float
    viewbox_y: float
    viewbox_w: float
    viewbox_h: float
    ink_x0: float
    ink_y0: float
    ink_x1: float
    ink_y1: float

    @property
    def ink_w(self) -> float:
        return max(0.0, self.ink_x1 - self.ink_x0)

    @property
    def ink_h(self) -> float:
        return max(0.0, self.ink_y1 - self.ink_y0)

    @property
    def ink_cx(self) -> float:
        return (self.ink_x0 + self.ink_x1) / 2.0

    @property
    def ink_cy(self) -> float:
        return (self.ink_y0 + self.ink_y1) / 2.0

    @property
    def area_ratio(self) -> float:
        viewbox_area = self.viewbox_w * self.viewbox_h
        if viewbox_area <= 0:
            return 1.0
        return max(0.0, (self.ink_w * self.ink_h) / viewbox_area)


@dataclass(frozen=True, slots=True)
class GlyphRenderMetrics:
    """Badge/icon render-space metrics derived from glyph ink bounds."""

    source: GlyphInkMetrics
    render_size: float
    optical_scale: float
    render_viewbox: str
    rendered_ink_w: float
    rendered_ink_h: float
    ink_left_inset: float
    ink_top_inset: float

    @property
    def rendered_ink_area(self) -> float:
        return self.rendered_ink_w * self.rendered_ink_h


def _fmt_number(value: float) -> str:
    rounded = round(value, 4)
    if abs(rounded) < 0.00005:
        rounded = 0.0
    return f"{rounded:g}"


def parse_viewbox(viewbox: str) -> tuple[float, float, float, float]:
    """Parse an SVG viewBox string, falling back to the registry default."""

    values: list[float]
    try:
        values = [float(part) for part in viewbox.replace(",", " ").split()]
    except ValueError:
        values = []
    if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
        return (0.0, 0.0, 24.0, 24.0)
    return (values[0], values[1], values[2], values[3])


@lru_cache(maxsize=512)
def compute_glyph_ink_metrics(glyph_id: str, path: str, viewbox: str) -> GlyphInkMetrics:
    """Compute source ink bounds from SVG path data."""

    vx, vy, vw, vh = parse_viewbox(viewbox)
    if not path:
        return GlyphInkMetrics(glyph_id, vx, vy, vw, vh, vx, vy, vx + vw, vy + vh)

    pen = BoundsPen(None)
    try:
        parse_path(path, pen)
    except Exception:
        return GlyphInkMetrics(glyph_id, vx, vy, vw, vh, vx, vy, vx + vw, vy + vh)

    if pen.bounds is None:
        return GlyphInkMetrics(glyph_id, vx, vy, vw, vh, vx, vy, vx + vw, vy + vh)

    x0, y0, x1, y1 = pen.bounds
    return GlyphInkMetrics(glyph_id, vx, vy, vw, vh, float(x0), float(y0), float(x1), float(y1))


def compute_glyph_render_metrics(
    glyph_id: str,
    path: str,
    viewbox: str,
    render_size: float,
    *,
    target_area_fill: float = 0.98,
    min_scale: float = 0.96,
    max_scale: float = 1.18,
) -> GlyphRenderMetrics:
    """Return a normalized viewBox and rendered ink metrics for one glyph size."""

    source = compute_glyph_ink_metrics(glyph_id, path, viewbox)
    area_ratio = max(source.area_ratio, 0.0001)
    optical_scale = target_area_fill / math.sqrt(area_ratio)
    optical_scale = min(max(optical_scale, min_scale), max_scale)

    render_vw = source.viewbox_w / optical_scale
    render_vh = source.viewbox_h / optical_scale
    render_vx = source.ink_cx - render_vw / 2.0
    render_vy = source.ink_cy - render_vh / 2.0
    render_viewbox = " ".join(
        (
            _fmt_number(render_vx),
            _fmt_number(render_vy),
            _fmt_number(render_vw),
            _fmt_number(render_vh),
        )
    )

    rendered_ink_w = source.ink_w / render_vw * render_size if render_vw > 0 else render_size
    rendered_ink_h = source.ink_h / render_vh * render_size if render_vh > 0 else render_size
    return GlyphRenderMetrics(
        source=source,
        render_size=render_size,
        optical_scale=optical_scale,
        render_viewbox=render_viewbox,
        rendered_ink_w=rendered_ink_w,
        rendered_ink_h=rendered_ink_h,
        ink_left_inset=(render_size - rendered_ink_w) / 2.0,
        ink_top_inset=(render_size - rendered_ink_h) / 2.0,
    )
