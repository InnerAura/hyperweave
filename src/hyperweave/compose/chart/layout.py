"""Chart-frame spatial layout.

Chart data projection still lives in :mod:`hyperweave.render.chart_engine`.
This module owns the frame/header/axis placement values that templates need
to render the projected data without doing coordinate arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hyperweave.compose.spatial_records import LineSpec, RectSpec, TextSpec
from hyperweave.core.text import measure_text
from hyperweave.render.chart_engine import LabelMetrics, Viewport

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hyperweave.core.paradigm import ParadigmChartConfig


@dataclass(frozen=True, slots=True)
class ChartLayout:
    """Frozen chart layout values consumed by templates."""

    width: int
    height: int
    viewport: Viewport
    viewport_right: int
    viewport_bottom: int
    right_16: int
    right_22: int
    right_24: int
    right_28: int
    y_label_x: int
    y_label_offset: int
    x_axis_y: int
    label_metrics: LabelMetrics
    header_identity_text_length: float
    chrome_scanlines: list[LineSpec]
    chrome_grid_guides: list[LineSpec]
    chrome_low_gridline: LineSpec
    chrome_outer_rect: RectSpec
    chrome_well_rect: RectSpec
    chrome_rail_rect: RectSpec
    chrome_top_highlight_rect: RectSpec
    chrome_header_rule: LineSpec
    chrome_title_rule: LineSpec
    chrome_x_axis_rule: LineSpec
    chrome_footer_rule: LineSpec
    chrome_horizon_rect: RectSpec
    y_axis_line: LineSpec
    x_axis_line: LineSpec
    rects: dict[str, RectSpec]
    lines: dict[str, LineSpec]
    texts: dict[str, TextSpec]
    brutalist_dark_grain_rect: RectSpec
    brutalist_perimeter_rect: RectSpec
    brutalist_right_3: int
    brutalist_right_6: int
    cellular_outer_rect: RectSpec
    cellular_footer_rule_y: int
    cellular_footer_text_y: int
    cellular_x_axis_y: int


def _identity_text_length(*, repo: str, header_label: str, chart: ParadigmChartConfig, width: int) -> float:
    """Clamp right-anchored header identity if it would collide with description."""
    description_x = 50
    description_w = measure_text(header_label, font_family="Orbitron", font_size=11, font_weight=700)
    identity_x = width - chart.header_identity_max_right_margin
    max_w = identity_x - (description_x + description_w + chart.header_identity_gap)
    if max_w <= 0:
        return 0.0
    natural = measure_text(
        repo,
        font_family=chart.identity_font_family,
        font_size=chart.identity_font_size,
        font_weight=chart.identity_font_weight,
        letter_spacing_em=chart.identity_letter_spacing_em,
    )
    return round(max_w, 1) if natural > max_w else 0.0


def compute_chart_layout(*, chart: ParadigmChartConfig, repo: str, header_label: str = "") -> ChartLayout:
    """Compute all non-data chart frame geometry."""
    vp = Viewport(x=chart.viewport_x, y=chart.viewport_y, w=chart.viewport_w, h=chart.viewport_h)
    viewport_right = vp.x + vp.w
    viewport_bottom = vp.y + vp.h
    right_16 = chart.chart_width - 16
    right_22 = chart.chart_width - 22
    right_24 = chart.chart_width - 24
    right_28 = chart.chart_width - 28
    label_metrics = LabelMetrics(
        font_family=chart.label_collision_font_family,
        font_size=chart.label_collision_font_size,
        font_weight=chart.label_collision_font_weight,
        letter_spacing_em=chart.label_collision_letter_spacing_em,
    )
    scanlines = [
        LineSpec(vp.x, vp.y + vp.h - 48 + idx * 4, viewport_right, vp.y + vp.h - 48 + idx * 4) for idx in range(12)
    ]
    grid_guides = [
        LineSpec(vp.x, vp.y + 10, viewport_right, vp.y + 10),
        LineSpec(vp.x, int(vp.y + vp.h * 0.36), viewport_right, int(vp.y + vp.h * 0.36)),
        LineSpec(vp.x, int(vp.y + vp.h * 0.68), viewport_right, int(vp.y + vp.h * 0.68)),
    ]
    chrome_header_rule = LineSpec(24.0, 60.0, chart.chart_width - 24.0, 60.0)
    chrome_title_rule = LineSpec(24.0, 148.0, chart.chart_width - 24.0, 148.0)
    chrome_x_axis_rule = LineSpec(24.0, 420.0, chart.chart_width - 24.0, 420.0)
    chrome_footer_rule = LineSpec(24.0, 460.0, chart.chart_width - 24.0, 460.0)
    y_axis_line = LineSpec(vp.x, vp.y, vp.x, viewport_bottom)
    x_axis_line = LineSpec(vp.x, viewport_bottom, viewport_right, viewport_bottom)
    brutalist_right_3 = chart.chart_width - 3
    brutalist_right_6 = chart.chart_width - 6
    cellular_footer_rule_y = chart.chart_height - 30
    cellular_footer_text_y = chart.chart_height - 14
    rects = {
        "brutalist_left_rail": RectSpec(0.0, 0.0, 6.0, float(chart.chart_height)),
        "brutalist_light_ink_bar": RectSpec(0.0, 0.0, 3.0, float(chart.chart_height)),
        "brutalist_light_seam_bar": RectSpec(3.0, 0.0, 3.0, float(chart.chart_height)),
        "brutalist_glyph": RectSpec(20.0, 13.0, 16.0, 16.0),
        "brutalist_status_dot": RectSpec(float(right_28), 17.0, 8.0, 8.0),
        "brutalist_light_header_panel": RectSpec(6.0, 0.0, float(brutalist_right_6), 42.0),
        "brutalist_light_header_seam": RectSpec(6.0, 42.0, float(brutalist_right_6), 2.5),
        "brutalist_light_title_panel": RectSpec(6.0, 44.0, float(brutalist_right_6), 78.0),
        "brutalist_light_title_hairline": RectSpec(6.0, 122.0, float(brutalist_right_6), 1.0),
        "chrome_glyph": RectSpec(24.0, 22.0, 16.0, 16.0),
        "chrome_status_anchor": RectSpec(32.0, 482.0, 0.0, 0.0),
        "chrome_status_diamond": RectSpec(-3.5, -3.5, 7.0, 7.0, 0.7),
        "chrome_clip": RectSpec(0.0, 0.0, float(chart.chart_width), float(chart.chart_height), 6.0),
        "cellular_clip": RectSpec(0.0, 0.0, float(chart.chart_width), float(chart.chart_height), 10.0),
        "cellular_header_band": RectSpec(0.0, 0.0, float(chart.chart_width), float(chart.header_band_height)),
        "primer_card": RectSpec(50.0, 36.0, float(chart.chart_width - 100), float(chart.chart_height - 72), 16.0),
        "primer_live_pill": RectSpec(float(chart.chart_width - 165), 64.0, 66.0, 22.0, 11.0),
        "primer_live_dot": RectSpec(float(chart.chart_width - 151), 72.5, 5.0, 5.0, 5.0),
        "primer_endpoint_shadow": RectSpec(0.0, 0.0, 0.0, 0.0),
        # Floating glass growth callout — sits in the upper-left empty region above
        # a rising curve (backdrop + top-highlight strip).
        "primer_callout": RectSpec(150.0, 210.0, 120.0, 72.0, 10.0),
        # Thin top-edge shine (not a tall oval): inset 1px, 2px tall, hugging the
        # rounded top so it reads as a glass highlight, not a pill.
        "primer_callout_hi": RectSpec(151.0, 211.0, 118.0, 2.0, 1.0),
    }
    lines = {
        "brutalist_header_rule": LineSpec(3.0, 42.0, float(brutalist_right_3), 42.0),
        "brutalist_title_rule": LineSpec(3.0, 122.0, float(brutalist_right_3), 122.0),
        "brutalist_footer_rule": LineSpec(3.0, 440.0, float(brutalist_right_3), 440.0),
        "brutalist_light_footer_rule": LineSpec(6.0, 448.0, float(brutalist_right_6), 448.0),
        "chrome_header_rule": chrome_header_rule,
        "chrome_title_rule": chrome_title_rule,
        "chrome_x_axis_rule": chrome_x_axis_rule,
        "chrome_footer_rule": chrome_footer_rule,
        "cellular_header_rule": LineSpec(
            0.0,
            float(chart.header_band_height),
            float(chart.chart_width),
            float(chart.header_band_height),
        ),
        "cellular_footer_rule": LineSpec(
            16.0,
            float(cellular_footer_rule_y),
            float(right_16),
            float(cellular_footer_rule_y),
        ),
        "primer_footer_rule": LineSpec(
            100.0, float(chart.chart_height - 60), float(chart.chart_width - 100), float(chart.chart_height - 60)
        ),
        # Metric triptych top rule + brand-bar rule (editorial footer band).
        "primer_triptych_rule": LineSpec(
            80.0, float(chart.chart_height - 130), float(chart.chart_width - 80), float(chart.chart_height - 130)
        ),
        "primer_brand_rule": LineSpec(
            80.0, float(chart.chart_height - 60), float(chart.chart_width - 80), float(chart.chart_height - 60)
        ),
    }
    texts = {
        "brutalist_header_user": TextSpec(42.0, 28.0, anchor="middle"),
        "brutalist_dark_title": TextSpec(24.0, 90.0, anchor="middle"),
        "brutalist_dark_subtitle": TextSpec(24.0, 108.0, anchor="middle"),
        "brutalist_dark_hero_value": TextSpec(float(right_24), 90.0, anchor="end"),
        "brutalist_dark_hero_label": TextSpec(float(right_24), 108.0, anchor="end"),
        "brutalist_light_title": TextSpec(24.0, 92.0, anchor="middle"),
        "brutalist_light_subtitle": TextSpec(24.0, 110.0, anchor="middle"),
        "brutalist_light_hero_value": TextSpec(float(right_24), 92.0, anchor="end"),
        "brutalist_light_hero_label": TextSpec(float(right_24), 110.0, anchor="end"),
        "brutalist_footer_url": TextSpec(20.0, 472.0, anchor="middle"),
        "brutalist_footer_brand": TextSpec(float(right_22), 472.0, anchor="end"),
        "chrome_label": TextSpec(50.0, 35.0, anchor="middle"),
        "chrome_identity": TextSpec(float(right_24), 35.0, anchor="end"),
        "chrome_title": TextSpec(28.0, 115.0, anchor="middle"),
        "chrome_hero_value": TextSpec(float(right_24), 118.0, anchor="end"),
        "chrome_subtitle": TextSpec(28.0, 138.0, anchor="middle"),
        "chrome_hero_label": TextSpec(float(right_24), 138.0, anchor="end"),
        "chrome_footer_url": TextSpec(46.0, 485.0, anchor="middle"),
        "chrome_footer_brand": TextSpec(float(right_24), 485.0, anchor="end"),
        "cellular_repo": TextSpec(22.0, 22.0, anchor="middle"),
        "cellular_title": TextSpec(22.0, 44.0, anchor="middle"),
        "cellular_hero_value": TextSpec(float(right_22), 36.0, anchor="end"),
        "cellular_hero_label": TextSpec(float(right_22), 54.0, anchor="end"),
        "cellular_footer_url": TextSpec(22.0, float(cellular_footer_text_y), anchor="middle"),
        "cellular_footer_brand": TextSpec(float(right_22), float(cellular_footer_text_y), anchor="end"),
        # Two-row header grid, both sides on the SAME baselines so the right reads
        # level with the left: row 1 (y90) = title | hero number; row 2 (y110) =
        # subtitle | "LIVE · <hero label>". No floating pill — the LIVE word itself
        # breathes as the live indicator, keeping the right block exactly 2 rows.
        "primer_title": TextSpec(100.0, 90.0, anchor="start"),
        "primer_subtitle": TextSpec(100.0, 110.0, anchor="start"),
        "primer_hero_value": TextSpec(float(chart.chart_width - 100), 90.0, anchor="end"),
        "primer_hero_label": TextSpec(float(chart.chart_width - 100), 110.0, anchor="end"),
        # Optional chart-header identity glyph (left of the title); rendered only
        # when a glyph resolves. Title shifts right via chart_title_x in the resolver.
        "primer_header_glyph": TextSpec(100.0, 73.0, anchor="start"),
        "primer_footer_url": TextSpec(100.0, float(chart.chart_height - 24), anchor="start"),
        "primer_footer_brand": TextSpec(float(chart.chart_width - 100), float(chart.chart_height - 24), anchor="end"),
        # Metric triptych: 3 label-over-value columns (CURRENT / DELTA / WINDOW).
        "primer_tri_l1": TextSpec(100.0, float(chart.chart_height - 108), anchor="start"),
        "primer_tri_l2": TextSpec(410.0, float(chart.chart_height - 108), anchor="start"),
        "primer_tri_l3": TextSpec(720.0, float(chart.chart_height - 108), anchor="start"),
        "primer_tri_v1": TextSpec(100.0, float(chart.chart_height - 84), anchor="start"),
        "primer_tri_v2": TextSpec(410.0, float(chart.chart_height - 84), anchor="start"),
        "primer_tri_v3": TextSpec(720.0, float(chart.chart_height - 84), anchor="start"),
        # Brand bar.
        "primer_brand": TextSpec(100.0, float(chart.chart_height - 44), anchor="start"),
        "primer_brand_date": TextSpec(float(chart.chart_width - 100), float(chart.chart_height - 44), anchor="end"),
        # Glass callout value + sublabel (centered in the callout box).
        "primer_callout_value": TextSpec(210.0, 254.0, anchor="middle"),
        "primer_callout_label": TextSpec(210.0, 270.0, anchor="middle"),
    }
    return ChartLayout(
        width=chart.chart_width,
        height=chart.chart_height,
        viewport=vp,
        viewport_right=viewport_right,
        viewport_bottom=viewport_bottom,
        right_16=right_16,
        right_22=right_22,
        right_24=right_24,
        right_28=right_28,
        y_label_x=vp.x + chart.axis_y_label_x_offset,
        y_label_offset=chart.axis_y_label_y_offset,
        x_axis_y=chart.x_axis_label_y,
        label_metrics=label_metrics,
        header_identity_text_length=_identity_text_length(
            repo=repo,
            header_label=header_label or repo,
            chart=chart,
            width=chart.chart_width,
        ),
        chrome_scanlines=scanlines,
        chrome_grid_guides=grid_guides,
        chrome_low_gridline=LineSpec(vp.x, vp.y + vp.h - 40, viewport_right, vp.y + vp.h - 40),
        chrome_outer_rect=RectSpec(2.0, 2.0, chart.chart_width - 4.0, chart.chart_height - 4.0, 4.5),
        chrome_well_rect=RectSpec(4.0, 4.0, chart.chart_width - 8.0, chart.chart_height - 8.0, 3.0),
        chrome_rail_rect=RectSpec(4.0, 4.0, 6.0, chart.chart_height - 8.0),
        chrome_top_highlight_rect=RectSpec(60.0, 4.0, chart.chart_width - 120.0, 0.6, 0.3),
        chrome_header_rule=chrome_header_rule,
        chrome_title_rule=chrome_title_rule,
        chrome_x_axis_rule=chrome_x_axis_rule,
        chrome_footer_rule=chrome_footer_rule,
        chrome_horizon_rect=RectSpec(vp.x, viewport_bottom - 1.0, vp.w, 2.0),
        y_axis_line=y_axis_line,
        x_axis_line=x_axis_line,
        rects=rects,
        lines=lines,
        texts=texts,
        brutalist_dark_grain_rect=RectSpec(3.0, 3.0, chart.chart_width - 6.0, chart.chart_height - 6.0),
        brutalist_perimeter_rect=RectSpec(0.75, 0.75, chart.chart_width - 1.5, chart.chart_height - 1.5),
        brutalist_right_3=brutalist_right_3,
        brutalist_right_6=brutalist_right_6,
        cellular_outer_rect=RectSpec(0.5, 0.5, chart.chart_width - 1.0, chart.chart_height - 1.0, 10.0),
        cellular_footer_rule_y=cellular_footer_rule_y,
        cellular_footer_text_y=cellular_footer_text_y,
        cellular_x_axis_y=vp.y + vp.h + 22,
    )


def _float_label_value(value: object) -> float:
    if not isinstance(value, int | float | str | bytes | bytearray):
        return 0.0
    return float(value)


def position_y_labels(labels: list[Mapping[str, object]], layout: ChartLayout) -> list[TextSpec]:
    """Attach x and baseline offsets to engine-generated Y labels."""
    out: list[TextSpec] = []
    for label in labels:
        out.append(
            TextSpec(
                x=layout.y_label_x,
                y=_float_label_value(label["y"]) + layout.y_label_offset,
                text=str(label["text"]),
                anchor="end",
            )
        )
    return out


def position_x_labels(labels: list[Mapping[str, object]], y: int) -> list[TextSpec]:
    """Attach a paradigm-owned baseline to engine-generated X labels."""
    return [
        TextSpec(
            x=_float_label_value(label["x"]),
            y=float(y),
            text=str(label["text"]),
            anchor=str(label.get("anchor", "middle")),
        )
        for label in labels
    ]
