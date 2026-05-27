"""Stats-card spatial layout.

The stats resolver prepares semantic data; this module freezes every repeated
coordinate list that stats templates consume. Templates should iterate these
records directly instead of deriving positions with Jinja arithmetic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from hyperweave.compose.spatial_records import LineSpec, RectSpec, TextSpec
from hyperweave.core.text import measure_text, measure_text_ink_width

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hyperweave.core.paradigm import ParadigmStatsConfig


MIN_IDENTITY_BIO_VISIBLE_GAP = 8.0
"""Minimum visible gap between header identity ink and bio text."""


@dataclass(frozen=True, slots=True)
class MetricSlot:
    """Resolved metric value/label placement."""

    value_x: float
    label_x: float
    value_y: float
    label_y: float
    css_value: str
    value_display: str
    label_text: str
    text_anchor: str = "start"
    value_text_length: float = 0.0


@dataclass(frozen=True, slots=True)
class ActivityBar:
    """Resolved weekly activity bar rectangle."""

    x: float
    y: float
    w: float
    h: float
    opacity: float


@dataclass(frozen=True, slots=True)
class LanguageSegment:
    """Resolved proportional language band segment."""

    x: float
    y: float
    w: float
    h: float
    opacity: float
    label_x: float
    label_y: float
    label_text: str
    show_label: bool


@dataclass(frozen=True, slots=True)
class InlineLanguageEntry:
    """Resolved cellular inline language legend entry."""

    swatch_x: float
    swatch_y: float
    swatch_w: float
    swatch_h: float
    swatch_rx: float
    swatch_color: str
    label_x: float
    label_y: float
    label_text: str


@dataclass(frozen=True, slots=True)
class HeatmapCell:
    """Resolved cellular contribution heatmap cell."""

    x: float
    y: float
    w: float
    h: float
    rx: float
    fill: str
    css_class: str


@dataclass(frozen=True, slots=True)
class LegendCell:
    """Resolved heatmap legend cell."""

    x: float
    y: float
    w: float
    h: float
    rx: float
    fill: str


@dataclass(frozen=True, slots=True)
class StatsZone:
    """Resolved vertical zone within a stats card."""

    name: str
    y: float
    h: float
    present: bool = True

    @property
    def end_y(self) -> float:
        """Bottom edge of the zone."""
        return self.y + self.h


@dataclass(frozen=True, slots=True)
class StatsLayout:
    """Frozen stats-card layout consumed by resolver context."""

    width: int
    height: int
    zones: dict[str, StatsZone]
    identity_x: int
    bio_x: int
    identity_text_length: float
    bio_text_length: float
    metric_slots: list[MetricSlot]
    metric_divider_xs: list[float]
    activity_bars: list[ActivityBar]
    language_segments: list[LanguageSegment]
    inline_language_entries: list[InlineLanguageEntry]
    heatmap_cells: list[HeatmapCell]
    heatmap_legend_cells: list[LegendCell]
    commits_text_length: float
    prs_text_length: float
    issues_text_length: float
    streak_text_length: float
    activity_baseline_y: float
    activity_present_x: float
    activity_present_y: float
    right_zone_w: float
    dark_perimeter: RectSpec
    light_perimeter: RectSpec
    light_bottom_strip_y: float
    chrome_outer_rect: RectSpec
    chrome_well_rect: RectSpec
    chrome_rail_rect: RectSpec
    chrome_top_highlight_rect: RectSpec
    cellular_outer_rect: RectSpec
    full_rect: RectSpec
    rects: dict[str, RectSpec]
    lines: dict[str, LineSpec]
    texts: dict[str, TextSpec]
    grain_right_rect: RectSpec
    header_right_rect: RectSpec
    language_shell_rect: RectSpec
    chrome_hero_rule: LineSpec
    chrome_activity_baseline: LineSpec
    chrome_footer_rule: LineSpec


def _float_value(value: object, default: float = 0.0) -> float:
    if not isinstance(value, int | float | str | bytes | bytearray):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_value(value: object, default: int = 0) -> int:
    if not isinstance(value, int | float | str | bytes | bytearray):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _string_value(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _metric_zone_height(metric_count: int, mode: str) -> float:
    if metric_count <= 0:
        return 0.0
    if mode == "cellular_inline":
        return 49.0
    if mode == "chrome_columns":
        return float(_chrome_metric_rows(metric_count) * 36)
    if metric_count <= 3:
        return 36.0
    return 72.0


def _chrome_metric_rows(metric_count: int) -> int:
    if metric_count <= 0:
        return 0
    if metric_count <= 4:
        return 1
    return math.ceil(metric_count / 3)


def _activity_zone_height(activity_type: str, present: bool) -> float:
    if not present:
        return 0.0
    if activity_type == "compact_bars_12w":
        return 24.0
    if activity_type == "sparkline_30d":
        return 50.0
    return 52.0


def compute_stats_card_height(
    *,
    stats: ParadigmStatsConfig,
    metric_count: int,
    activity_type: str = "",
    has_activity: bool,
    has_heatmap: bool,
    has_proportional_bar: bool,
) -> int:
    """Compute stats card height from present data zones."""
    mode = stats.metric_layout_mode
    if mode == "chrome_columns" and has_activity and metric_count > 0:
        extra_metric_h = max(0.0, _metric_zone_height(metric_count, mode) - 36.0)
        return int(stats.card_height + extra_metric_h)
    if mode == "brutalist_grid" and has_activity and has_proportional_bar and metric_count >= 4:
        return int(stats.card_height)
    if mode == "cellular_inline" and has_heatmap and has_proportional_bar and metric_count >= 4:
        return int(stats.card_height)

    if mode == "chrome_columns":
        metric_h = _metric_zone_height(metric_count, mode)
        activity_h = _activity_zone_height(activity_type, has_activity)
        if has_activity:
            footer_y = 128.0 + metric_h + 6.0 + activity_h
        else:
            footer_y = 128.0 + metric_h + 6.0 if metric_count > 0 else 120.0
        return math.ceil(footer_y + 28.0)
    if mode == "brutalist_grid":
        metric_h = _metric_zone_height(metric_count, mode)
        cursor = 128.0 + metric_h if metric_count > 0 else 128.0
        if has_activity:
            cursor += _activity_zone_height(activity_type, True)
        if has_proportional_bar:
            cursor += float(stats.language_zone_h)
        footer_h = 16.0 if metric_count == 4 else 28.0
        return math.ceil(cursor + footer_h)
    if mode == "cellular_inline":
        cursor = 88.0 if metric_count > 0 else float(stats.header_band_height or 39.0)
        if has_heatmap:
            cursor = 216.0
        if has_proportional_bar:
            cursor += float(stats.language_zone_h)
        return math.ceil(cursor + 16.0)

    header_h = float(stats.header_band_height or 32.0)
    hero_h = 0.0 if mode == "cellular_inline" else 52.0
    metric_h = _metric_zone_height(metric_count, mode)
    activity_h = _activity_zone_height(activity_type, has_activity)
    heatmap_h = float(stats.heatmap_zone_height if has_heatmap else 0.0)
    proportional_h = float(stats.language_zone_h if has_proportional_bar else 0.0)
    footer_h = 16.0
    return math.ceil(header_h + hero_h + metric_h + activity_h + heatmap_h + proportional_h + footer_h)


def _stats_zones(
    *,
    stats: ParadigmStatsConfig,
    card_height: int,
    metric_count: int,
    activity_type: str,
    has_activity: bool,
    has_heatmap: bool,
    has_proportional_bar: bool,
) -> dict[str, StatsZone]:
    mode = stats.metric_layout_mode
    if card_height >= int(stats.card_height):
        if mode == "chrome_columns":
            metric_h = _metric_zone_height(metric_count, mode)
            extra_metric_h = max(0.0, metric_h - 36.0)
            activity_y = 170.0 + extra_metric_h
            footer_y = 232.0 + extra_metric_h
            return {
                "header": StatsZone("header", 0.0, 40.0),
                "hero": StatsZone("hero", 40.0, 80.0),
                "metrics": StatsZone("metrics", 128.0, metric_h, metric_count > 0),
                "activity": StatsZone("activity", activity_y, 62.0 if has_activity else 0.0, has_activity),
                "heatmap": StatsZone("heatmap", 0.0, 0.0, False),
                "proportional": StatsZone("proportional", 0.0, 0.0, False),
                "footer": StatsZone("footer", footer_y, card_height - footer_y),
            }
        if mode == "cellular_inline":
            return {
                "header": StatsZone("header", 0.0, float(stats.header_band_height or 39.0)),
                "hero": StatsZone("hero", 0.0, 0.0, False),
                "metrics": StatsZone("metrics", 39.0, 49.0, metric_count > 0),
                "activity": StatsZone("activity", 0.0, 0.0, False),
                "heatmap": StatsZone("heatmap", 101.0, float(stats.heatmap_zone_height), has_heatmap),
                "proportional": StatsZone("proportional", 216.0, 10.0, has_proportional_bar),
                "footer": StatsZone("footer", 216.0, card_height - 216.0),
            }
        return {
            "header": StatsZone("header", 0.0, 32.0),
            "hero": StatsZone("hero", 32.0, 96.0),
            "metrics": StatsZone("metrics", 128.0, 72.0, metric_count > 0),
            "activity": StatsZone("activity", 200.0, 52.0, has_activity),
            "heatmap": StatsZone("heatmap", 0.0, 0.0, False),
            "proportional": StatsZone("proportional", 252.0, 12.0, has_proportional_bar),
            "footer": StatsZone("footer", 264.0, card_height - 264.0),
        }

    if mode == "chrome_columns":
        metric_h = _metric_zone_height(metric_count, mode)
        activity_y = 128.0 + metric_h + 6.0
        activity_h = _activity_zone_height(activity_type, has_activity)
        footer_y = activity_y + activity_h if has_activity else activity_y if metric_count > 0 else 120.0
        return {
            "header": StatsZone("header", 0.0, 40.0),
            "hero": StatsZone("hero", 40.0, 80.0),
            "metrics": StatsZone("metrics", 128.0, metric_h, metric_count > 0),
            "activity": StatsZone("activity", activity_y, activity_h, has_activity),
            "heatmap": StatsZone("heatmap", 0.0, 0.0, False),
            "proportional": StatsZone("proportional", 0.0, 0.0, False),
            "footer": StatsZone("footer", footer_y, max(0.0, float(card_height) - footer_y)),
        }
    if mode == "brutalist_grid":
        metric_h = _metric_zone_height(metric_count, mode)
        activity_y = 128.0 + metric_h if metric_count != 4 else 200.0
        activity_h = 52.0 if has_activity else 0.0
        proportional_y = activity_y + activity_h if has_activity else activity_y
        proportional_h = float(stats.language_zone_h if has_proportional_bar else 0.0)
        footer_y = proportional_y + proportional_h
        if not has_activity and not has_proportional_bar:
            footer_y = 128.0 + metric_h if metric_count > 0 else 128.0
        return {
            "header": StatsZone("header", 0.0, 32.0),
            "hero": StatsZone("hero", 32.0, 96.0),
            "metrics": StatsZone("metrics", 128.0, metric_h, metric_count > 0),
            "activity": StatsZone("activity", activity_y, activity_h, has_activity),
            "heatmap": StatsZone("heatmap", 0.0, 0.0, False),
            "proportional": StatsZone("proportional", proportional_y, proportional_h, has_proportional_bar),
            "footer": StatsZone("footer", footer_y, max(0.0, float(card_height) - footer_y)),
        }
    if mode == "cellular_inline":
        heatmap_y = 101.0
        heatmap_h = float(stats.heatmap_zone_height if has_heatmap else 0.0)
        proportional_y = 216.0 if has_heatmap else 88.0
        proportional_h = float(stats.language_zone_h if has_proportional_bar else 0.0)
        footer_y = proportional_y + proportional_h if has_proportional_bar else proportional_y
        return {
            "header": StatsZone("header", 0.0, float(stats.header_band_height or 39.0)),
            "hero": StatsZone("hero", 0.0, 0.0, False),
            "metrics": StatsZone("metrics", 39.0, 49.0, metric_count > 0),
            "activity": StatsZone("activity", 0.0, 0.0, False),
            "heatmap": StatsZone("heatmap", heatmap_y, heatmap_h, has_heatmap),
            "proportional": StatsZone("proportional", proportional_y, proportional_h, has_proportional_bar),
            "footer": StatsZone("footer", footer_y, max(0.0, float(card_height) - footer_y)),
        }

    zones: dict[str, StatsZone] = {}
    cursor = 0.0
    header_h = float(stats.header_band_height or 32.0)
    zones["header"] = StatsZone("header", cursor, header_h)
    cursor += header_h
    hero_h = 0.0 if mode == "cellular_inline" else 52.0
    zones["hero"] = StatsZone("hero", cursor, hero_h, hero_h > 0)
    cursor += hero_h
    metric_h = _metric_zone_height(metric_count, mode)
    zones["metrics"] = StatsZone("metrics", cursor, metric_h, metric_count > 0)
    cursor += metric_h
    activity_h = _activity_zone_height(activity_type, has_activity)
    zones["activity"] = StatsZone("activity", cursor, activity_h, has_activity)
    cursor += activity_h
    heatmap_h = float(stats.heatmap_zone_height if has_heatmap else 0.0)
    zones["heatmap"] = StatsZone("heatmap", cursor, heatmap_h, has_heatmap)
    cursor += heatmap_h
    proportional_h = float(stats.language_zone_h if has_proportional_bar else 0.0)
    zones["proportional"] = StatsZone("proportional", cursor, proportional_h, has_proportional_bar)
    cursor += proportional_h
    zones["footer"] = StatsZone("footer", cursor, max(0.0, float(card_height) - cursor))
    return zones


def _count_value(entry: Mapping[str, object]) -> int:
    return _int_value(entry.get("count"), 0)


def _pct_value(entry: Mapping[str, object]) -> float:
    return _float_value(entry.get("pct"), 0.0)


def _language_name(entry: Mapping[str, object]) -> str:
    return _string_value(entry.get("name"), "")


def compute_identity_layout(
    *,
    username: str,
    bio_text: str,
    stats: ParadigmStatsConfig,
    card_width: int,
) -> tuple[int, int, float, float]:
    """Compute identity/bio x positions and shrink-to-fit lengths."""
    identity_measure_text = username.upper() if stats.identity_text_transform == "uppercase" else username
    identity_natural = measure_text(
        identity_measure_text,
        font_family=stats.identity_font_family,
        font_size=stats.identity_font_size,
        font_weight=stats.identity_font_weight,
        letter_spacing_em=stats.identity_letter_spacing_em,
    )
    identity_zone_w = max(0, stats.bio_x - stats.identity_x - stats.identity_padding)
    identity_text_length = float(identity_zone_w) if identity_zone_w > 0 and identity_natural > identity_zone_w else 0.0

    identity_ink_w = measure_text_ink_width(
        identity_measure_text,
        font_family=stats.identity_font_family,
        font_size=stats.identity_font_size,
        font_weight=stats.identity_font_weight,
        letter_spacing_em=stats.identity_letter_spacing_em,
    )
    rendered_ink_w = float(identity_zone_w) if identity_text_length else identity_ink_w
    breathing_margin = max(float(stats.identity_breathing_margin), MIN_IDENTITY_BIO_VISIBLE_GAP)
    adaptive_bio_x = stats.identity_x + rendered_ink_w + breathing_margin
    bio_x = math.ceil(min(adaptive_bio_x, stats.bio_x)) if stats.bio_x > 0 else math.ceil(adaptive_bio_x)

    bio_text_length = 0.0
    if stats.bio_collision_clamp and bio_text:
        branding_w = measure_text(
            "HYPERWEAVE",
            font_family="JetBrains Mono",
            font_size=6.5,
            font_weight=700,
            letter_spacing_em=0.14,
        )
        branding_left = card_width - 20 - branding_w
        bio_max_width = branding_left - bio_x - 10
        bio_natural = measure_text(
            bio_text,
            font_family="JetBrains Mono",
            font_size=8.5,
            font_weight=400,
            letter_spacing_em=0.03,
        )
        if bio_max_width > 0 and bio_natural > bio_max_width:
            bio_text_length = round(bio_max_width, 1)

    return stats.identity_x, bio_x, identity_text_length, bio_text_length


def _build_chrome_slots(
    entries: Sequence[Mapping[str, object]],
    stats: ParadigmStatsConfig,
    *,
    card_width: int,
    metric_zone_y: float,
    metric_zone_h: float,
) -> tuple[list[MetricSlot], dict[str, float]]:
    visible_entries = list(entries[:6])
    if len(visible_entries) == 4:
        positions = [(center, metric_zone_y + 7.0, metric_zone_y + 30.0) for center in (62.0, 186.0, 309.0, 433.0)]
    elif len(visible_entries) <= 3:
        positions = _dynamic_chrome_metric_positions(
            count=len(visible_entries),
            card_width=card_width,
            metric_zone_y=metric_zone_y,
        )
    else:
        positions = []
        max_per_row = 3
        for idx, _entry in enumerate(visible_entries):
            row = idx // max_per_row
            col = idx % max_per_row
            remaining = len(visible_entries) - (row * max_per_row)
            cols_in_row = min(remaining, max_per_row)
            slot_w = (card_width - 44.0) / cols_in_row
            center = 22.0 + (slot_w * col) + (slot_w / 2.0)
            positions.append((center, metric_zone_y + 7.0 + (row * 36.0), metric_zone_y + 30.0 + (row * 36.0)))
    slots: list[MetricSlot] = []
    lengths: dict[str, float] = {}
    for center, label_y, value_y, entry in (
        (*position, entry) for position, entry in zip(positions, visible_entries, strict=True)
    ):
        label = _string_value(entry.get("label"), "").upper()
        display, force_text_length = _fit_metric_display(
            _string_value(entry.get("value"), "—"),
            stats=stats,
            budget=float(stats.metric_value_budget),
        )
        natural = measure_text(
            display,
            font_family=stats.metric_value_font_family,
            font_size=stats.metric_value_font_size,
            font_weight=stats.metric_value_font_weight,
            letter_spacing_em=stats.metric_value_letter_spacing_em,
        )
        text_length = (
            float(stats.metric_value_budget) if force_text_length or natural > stats.metric_value_budget else 0.0
        )
        lengths[f"{label.lower()}_text_length"] = text_length
        slots.append(
            MetricSlot(
                value_x=center,
                label_x=center,
                value_y=value_y,
                label_y=label_y,
                css_value="mval",
                value_display=display,
                label_text=label,
                text_anchor="middle",
                value_text_length=text_length,
            )
        )
    return slots, lengths


def _dynamic_chrome_metric_positions(
    *,
    count: int,
    card_width: int,
    metric_zone_y: float,
) -> list[tuple[float, float, float]]:
    """Compute equal chrome columns for non-4 metric counts."""
    if count <= 0:
        return []
    usable_start = 22.0
    usable_end = float(card_width) - 22.0
    slot_w = (usable_end - usable_start) / count
    return [
        (
            round(usable_start + (slot_w * idx) + (slot_w / 2.0), 3),
            metric_zone_y + 7.0,
            metric_zone_y + 30.0,
        )
        for idx in range(count)
    ]


def _fit_metric_display(
    display: str,
    *,
    stats: ParadigmStatsConfig,
    budget: float,
) -> tuple[str, bool]:
    """Keep long text metrics readable instead of crushing them with textLength."""
    if not display or budget <= 0:
        return display, False
    if len(display) <= 10:
        return display, False
    if any(ch.isalpha() for ch in display):
        candidate = display
        while len(candidate) > 4:
            measured = measure_text(
                candidate + "...",
                font_family=stats.metric_value_font_family,
                font_size=stats.metric_value_font_size,
                font_weight=stats.metric_value_font_weight,
                letter_spacing_em=stats.metric_value_letter_spacing_em,
            )
            if measured <= budget:
                return candidate + "...", False
            candidate = candidate[:-1]
        return display[:4] + "...", False
    return display, True


def _build_brutalist_slots(
    entries: Sequence[Mapping[str, object]],
    stats: ParadigmStatsConfig,
    *,
    card_width: int,
    metric_zone_y: float,
    metric_zone_h: float,
) -> list[MetricSlot]:
    visible_entries = list(entries[:4])
    if len(visible_entries) == 4 and metric_zone_h >= 72.0:
        return [
            MetricSlot(
                238.0,
                24.0,
                metric_zone_y + 26.0,
                metric_zone_y + 26.0,
                "sv",
                _string_value(visible_entries[0].get("value"), "—"),
                _string_value(visible_entries[0].get("label"), "").upper(),
                "end",
            ),
            MetricSlot(
                238.0,
                24.0,
                metric_zone_y + 62.0,
                metric_zone_y + 62.0,
                "sv",
                _string_value(visible_entries[1].get("value"), "—"),
                _string_value(visible_entries[1].get("label"), "").upper(),
                "end",
            ),
            MetricSlot(
                card_width - 15.0,
                270.0,
                metric_zone_y + 26.0,
                metric_zone_y + 26.0,
                "sv",
                _string_value(visible_entries[2].get("value"), "—"),
                _string_value(visible_entries[2].get("label"), "").upper(),
                "end",
            ),
            MetricSlot(
                card_width - 15.0,
                270.0,
                metric_zone_y + 62.0,
                metric_zone_y + 62.0,
                "sv",
                _string_value(visible_entries[3].get("value"), "—"),
                _string_value(visible_entries[3].get("label"), "").upper(),
                "end",
            ),
        ]

    if not visible_entries:
        return []
    usable_left = 6.0
    cell_w = (card_width - usable_left) / len(visible_entries)
    slots: list[MetricSlot] = []
    for idx, entry in enumerate(visible_entries):
        cell_left = usable_left + (cell_w * idx)
        cell_right = cell_left + cell_w
        label = _string_value(entry.get("label"), "").upper()
        value_x = round(cell_right - 14.0, 3)
        label_x = round(cell_left + 18.0, 3)
        label_w = measure_text(
            label,
            font_family=stats.metric_label_font_family,
            font_size=stats.metric_label_font_size,
            font_weight=stats.metric_label_font_weight,
            letter_spacing_em=stats.metric_label_letter_spacing_em,
        )
        value_budget = max(0.0, value_x - (label_x + label_w + 8.0))
        display, force_text_length = _fit_metric_display(
            _string_value(entry.get("value"), "—"),
            stats=stats,
            budget=value_budget,
        )
        natural = measure_text(
            display,
            font_family=stats.metric_value_font_family,
            font_size=stats.metric_value_font_size,
            font_weight=stats.metric_value_font_weight,
            letter_spacing_em=stats.metric_value_letter_spacing_em,
        )
        text_length = value_budget if value_budget > 0 and (force_text_length or natural > value_budget) else 0.0
        slots.append(
            MetricSlot(
                value_x,
                label_x,
                metric_zone_y + 26.0,
                metric_zone_y + 20.0,
                "sv",
                display,
                label,
                "end",
                round(text_length, 3),
            )
        )
    return slots


def _metric_divider_positions(
    *,
    mode: str,
    card_width: int,
    metric_slots: Sequence[MetricSlot],
    metric_zone_h: float,
) -> list[float]:
    count = len(metric_slots)
    if count <= 1:
        return []
    if mode == "chrome_columns":
        if count == 4:
            return [124.0, 248.0, 371.0][: count - 1]
        if count <= 3:
            slot_w = (card_width - 44.0) / count
            return [round(22.0 + (slot_w * idx), 3) for idx in range(1, count)]
        slot_w = (card_width - 44.0) / 3.0
        return [round(22.0 + slot_w, 3), round(22.0 + (slot_w * 2.0), 3)]
    if mode == "brutalist_grid":
        if count == 4 and metric_zone_h >= 72.0:
            return [250.0]
        cell_w = (card_width - 6.0) / count
        return [round(6.0 + (cell_w * idx), 3) for idx in range(1, count)]
    return []


def _measure_cellular_label(label_text: str, stats: ParadigmStatsConfig) -> float:
    return measure_text(
        label_text,
        font_family=stats.metric_label_font_family,
        font_size=stats.metric_label_font_size,
        font_weight=stats.metric_label_font_weight,
        letter_spacing_em=stats.metric_label_letter_spacing_em,
    )


def _build_cellular_slots(
    entries: Sequence[Mapping[str, object]],
    stats: ParadigmStatsConfig,
    card_width: int,
    metric_y: float,
) -> list[MetricSlot]:
    normalized = list(entries[:5])
    left_metrics: tuple[tuple[str, float, int, float, str, str], ...] = tuple(
        (
            "mvh" if idx == 0 else "mvm" if idx == 1 else "mvs",
            26.0 if idx == 0 else 20.0 if idx == 1 else 15.0,
            700 if idx < 2 else 600,
            -0.02 if idx < 2 else 0.0,
            _string_value(entry.get("value"), "—"),
            _string_value(entry.get("label"), "").upper(),
        )
        for idx, entry in enumerate(normalized[:4])
    )

    slots: list[MetricSlot] = []
    cursor = round(float(stats.cellular_metric_left_x), 3)
    for css_value, val_size, val_weight, val_ls, value_display, label_text in left_metrics:
        value_w = measure_text(
            value_display,
            font_family=stats.cellular_metric_value_font_family,
            font_size=val_size,
            font_weight=val_weight,
            letter_spacing_em=val_ls,
        )
        label_w = _measure_cellular_label(label_text, stats)
        slot_w = value_w + stats.cellular_metric_value_label_gap + label_w
        if cursor + slot_w > card_width - stats.cellular_metric_right_margin:
            break
        value_x = round(cursor, 3)
        label_x = round(cursor + value_w + stats.cellular_metric_value_label_gap, 3)
        slots.append(
            MetricSlot(
                value_x,
                label_x,
                metric_y,
                metric_y,
                css_value,
                value_display,
                label_text,
            )
        )
        cursor = round(label_x + label_w + stats.cellular_metric_inter_slot_gap, 3)

    if len(normalized) < 5:
        return slots

    streak_entry = normalized[4]
    streak_slot = (
        "mvg",
        15.0,
        600,
        0.0,
        _string_value(streak_entry.get("value"), "—"),
        _string_value(streak_entry.get("label"), "").upper(),
    )
    css_value, val_size, val_weight, val_ls, value_display, label_text = streak_slot
    value_w = measure_text(
        value_display,
        font_family=stats.cellular_metric_value_font_family,
        font_size=val_size,
        font_weight=val_weight,
        letter_spacing_em=val_ls,
    )
    label_w = _measure_cellular_label(label_text, stats)
    slot_w = value_w + stats.cellular_metric_value_label_gap + label_w
    value_x = round(card_width - stats.cellular_metric_right_margin - slot_w, 3)
    label_x = round(value_x + value_w + stats.cellular_metric_value_label_gap, 3)
    slots.append(
        MetricSlot(
            value_x,
            label_x,
            metric_y,
            metric_y,
            css_value,
            value_display,
            label_text,
        )
    )
    return slots


def _cellular_metric_entries(
    entries: Sequence[Mapping[str, object]],
    displays: Mapping[str, str],
    hero_label: str,
) -> list[Mapping[str, object]]:
    """Return cellular slots in schema order, with the hero prepended when absent."""
    hero = (hero_label or "STARS").upper()
    candidates: list[Mapping[str, object]] = list(entries)
    if not any(_string_value(entry.get("label"), "").upper() == hero for entry in candidates):
        candidates = [{"label": hero, "value": displays["stars"]}, *candidates]

    by_label: dict[str, Mapping[str, object]] = {}
    ordered: list[Mapping[str, object]] = []
    for entry in candidates:
        label = _string_value(entry.get("label"), "").upper()
        if not label or label in by_label:
            continue
        by_label[label] = entry
        ordered.append(entry)
    max_slots = 5
    if len(ordered) <= max_slots:
        return ordered

    temporal_labels = {"STREAK", "UPDATED", "PUBLISHED"}
    temporal_entry = next(
        (entry for entry in ordered if _string_value(entry.get("label"), "").upper() in temporal_labels),
        None,
    )
    if temporal_entry is None:
        return ordered[:max_slots]

    non_temporal = [entry for entry in ordered if entry is not temporal_entry]
    return [*non_temporal[: max_slots - 1], temporal_entry]


def _build_activity_bars(
    activity_bars: Sequence[Mapping[str, object]],
    *,
    activity_peak: int,
    stats: ParadigmStatsConfig,
    substrate_kind: str,
    baseline_y: float,
) -> list[ActivityBar]:
    peak = activity_peak if activity_peak > 0 else 1
    if substrate_kind == "light":
        op_min = stats.activity_bar_opacity_min_light
        op_max = stats.activity_bar_opacity_max_light
    else:
        op_min = stats.activity_bar_opacity_min
        op_max = stats.activity_bar_opacity_max
    out: list[ActivityBar] = []
    for idx, bar in enumerate(activity_bars):
        count = _count_value(bar)
        if count <= 0:
            height = stats.activity_bar_min_h
            opacity = op_min
        else:
            ratio = math.sqrt(count / peak)
            height = max(stats.activity_bar_min_h, float(int(ratio * stats.activity_bar_max_h)))
            opacity = op_min + (ratio * (op_max - op_min))
        x = stats.activity_bar_start_x + idx * stats.activity_bar_stride
        y = baseline_y - height
        out.append(ActivityBar(round(x, 3), round(y, 3), stats.activity_bar_w, round(height, 3), round(opacity, 2)))
    return out


def _build_language_segments(
    languages: Sequence[Mapping[str, object]],
    *,
    card_width: int,
    stats: ParadigmStatsConfig,
    substrate_kind: str,
    zone_y: float,
) -> list[LanguageSegment]:
    opacities = (
        stats.language_segment_opacities_light if substrate_kind == "light" else stats.language_segment_opacities
    )
    label_y = stats.language_label_y_light if substrate_kind == "light" else stats.language_label_y_dark
    cursor = stats.language_zone_x
    total_w = card_width - stats.language_zone_x
    out: list[LanguageSegment] = []
    for idx, lang in enumerate(languages):
        pct = max(0.0, min(100.0, _pct_value(lang)))
        width = int((pct / 100.0) * total_w)
        opacity = opacities[idx] if idx < len(opacities) else opacities[-1]
        name = _language_name(lang).upper()
        label = f"{name} · {math.floor(pct)}%"
        label_w = measure_text(
            label,
            font_family="JetBrains Mono",
            font_size=7.0,
            font_weight=700,
            letter_spacing_em=0.18,
        )
        label_left_padding = float(stats.language_label_offset_x)
        out.append(
            LanguageSegment(
                x=round(cursor, 3),
                y=zone_y,
                w=float(width),
                h=stats.language_zone_h,
                opacity=opacity,
                label_x=round(cursor + stats.language_label_offset_x, 3),
                label_y=label_y + (zone_y - stats.language_zone_y),
                label_text=label,
                show_label=idx < 2 and width >= label_w + label_left_padding + 4.0,
            )
        )
        cursor += width
    return out


def _build_inline_languages(
    languages: Sequence[Mapping[str, object]],
    *,
    card_width: int,
    stats: ParadigmStatsConfig,
    area_tiers: Sequence[str],
    y_offset: float = 0.0,
) -> list[InlineLanguageEntry]:
    if len(area_tiers) < 5:
        return []
    swatch_cycle = [area_tiers[2], area_tiers[0], area_tiers[1], area_tiers[3], area_tiers[4]]
    x = stats.inline_language_zone_left
    zone_right = card_width - stats.inline_language_zone_right_margin
    out: list[InlineLanguageEntry] = []
    for idx, lang in enumerate(languages[:4]):
        name = _language_name(lang)
        pct = int(_pct_value(lang))
        label = f"{name} {pct}%"
        label_w = measure_text(label, font_family="JetBrains Mono", font_size=7)
        entry_w = stats.inline_language_swatch_w + stats.inline_language_swatch_text_gap + label_w
        if x + entry_w > zone_right:
            break
        out.append(
            InlineLanguageEntry(
                swatch_x=round(x, 3),
                swatch_y=round(stats.inline_language_swatch_y + y_offset, 3),
                swatch_w=stats.inline_language_swatch_w,
                swatch_h=stats.inline_language_swatch_h,
                swatch_rx=stats.inline_language_swatch_rx,
                swatch_color=swatch_cycle[idx % len(swatch_cycle)],
                label_x=round(x + stats.inline_language_swatch_w + stats.inline_language_swatch_text_gap, 3),
                label_y=round(stats.inline_language_label_y + y_offset, 3),
                label_text=label,
            )
        )
        x += entry_w + stats.inline_language_entry_gap
    return out


def _build_heatmap_cells(
    heatmap_grid: Sequence[Mapping[str, object]],
    *,
    stats: ParadigmStatsConfig,
    area_tiers: Sequence[str],
    y_offset: float = 0.0,
) -> list[HeatmapCell]:
    if (
        not heatmap_grid
        or not area_tiers
        or stats.heatmap_rows <= 0
        or stats.heatmap_cols <= 0
        or stats.heatmap_cell_size <= 0
    ):
        return []
    grid_len = len(heatmap_grid)
    window_cells = stats.heatmap_cols * stats.heatmap_rows
    offset = grid_len - window_cells if grid_len > window_cells else 0
    anim_classes = ("b1", "b2", "b3", "b4")
    stride = stats.heatmap_cell_size + stats.heatmap_cell_gap
    out: list[HeatmapCell] = []
    for col in range(stats.heatmap_cols):
        for row in range(stats.heatmap_rows):
            idx = offset + col * stats.heatmap_rows + row
            level = _int_value(heatmap_grid[idx].get("level"), 0) if 0 <= idx < grid_len else 0
            level = max(0, min(4, level))
            fill = area_tiers[4 - level] if len(area_tiers) > 4 - level else area_tiers[-1]
            css_class = anim_classes[(col + row) % len(anim_classes)] if level >= 1 else ""
            out.append(
                HeatmapCell(
                    x=round(stats.heatmap_x0 + col * stride, 3),
                    y=round(stats.heatmap_y0 + y_offset + row * stride, 3),
                    w=stats.heatmap_cell_size,
                    h=stats.heatmap_cell_size,
                    rx=stats.heatmap_cell_rx,
                    fill=fill,
                    css_class=css_class,
                )
            )
    return out


def _build_legend_cells(
    stats: ParadigmStatsConfig,
    area_tiers: Sequence[str],
    *,
    y_offset: float = 0.0,
) -> list[LegendCell]:
    if len(area_tiers) < 5:
        return []
    return [
        LegendCell(
            x=x,
            y=round(stats.heatmap_legend_y + y_offset, 3),
            w=stats.heatmap_legend_size,
            h=stats.heatmap_legend_size,
            rx=stats.heatmap_legend_rx,
            fill=area_tiers[4 - idx],
        )
        for idx, x in enumerate(stats.heatmap_legend_xs[:5])
    ]


def _slot_layout(
    *,
    displays: Mapping[str, str],
    metric_entries: Sequence[Mapping[str, object]] | None,
    stats: ParadigmStatsConfig,
    card_width: int,
    metric_zone_y: float,
    metric_zone_h: float,
    hero_label: str = "STARS",
) -> tuple[list[MetricSlot], dict[str, float]]:
    if metric_entries is None:
        if stats.metric_layout_mode == "cellular_inline":
            metric_entries = (
                {"label": "STARS", "value": displays["stars"]},
                {"label": "COMMITS", "value": displays["commits"]},
                {"label": "PRS", "value": displays["prs"]},
                {"label": "CONTRIB", "value": displays["contrib"]},
                {"label": "STREAK", "value": displays["streak"]},
            )
        else:
            metric_entries = (
                {"label": "COMMITS", "value": displays["commits"]},
                {"label": "PRS", "value": displays["prs"]},
                {"label": "ISSUES", "value": displays["issues"]},
                {"label": "STREAK", "value": displays["streak"]},
            )
    entries = list(metric_entries)
    if stats.metric_layout_mode == "cellular_inline":
        entries = _cellular_metric_entries(entries, displays, hero_label)

    if stats.metric_layout_mode == "chrome_columns":
        return _build_chrome_slots(
            entries,
            stats,
            card_width=card_width,
            metric_zone_y=metric_zone_y,
            metric_zone_h=metric_zone_h,
        )
    if stats.metric_layout_mode == "cellular_inline":
        return _build_cellular_slots(entries, stats, card_width, metric_zone_y + 33.8), {}
    return (
        _build_brutalist_slots(
            entries,
            stats,
            card_width=card_width,
            metric_zone_y=metric_zone_y,
            metric_zone_h=metric_zone_h,
        ),
        {},
    )


def compute_stats_layout(
    *,
    stats: ParadigmStatsConfig,
    card_width: int,
    card_height: int,
    username: str,
    bio_text: str,
    displays: Mapping[str, str],
    activity_bars: Sequence[Mapping[str, object]],
    activity_peak: int,
    languages: Sequence[Mapping[str, object]],
    heatmap_grid: Sequence[Mapping[str, object]],
    area_tiers: Sequence[str],
    metric_entries: Sequence[Mapping[str, object]] | None = None,
    hero_label: str = "STARS",
    activity_type: str = "",
    has_activity: bool | None = None,
    has_heatmap: bool | None = None,
    has_proportional_bar: bool | None = None,
    substrate_kind: Literal["dark", "light"] | str = "dark",
) -> StatsLayout:
    """Compute all resolver-owned stats geometry for the active paradigm."""
    is_light = substrate_kind == "light"
    metric_count = len(metric_entries) if metric_entries is not None else 4
    has_activity = bool(activity_bars) if has_activity is None else has_activity
    has_heatmap = bool(heatmap_grid) if has_heatmap is None else has_heatmap
    has_proportional_bar = bool(languages) if has_proportional_bar is None else has_proportional_bar
    zones = _stats_zones(
        stats=stats,
        card_height=card_height,
        metric_count=metric_count,
        activity_type=activity_type,
        has_activity=has_activity,
        has_heatmap=has_heatmap,
        has_proportional_bar=has_proportional_bar,
    )
    header_zone = zones["header"]
    hero_zone = zones["hero"]
    metric_zone = zones["metrics"]
    activity_zone = zones["activity"]
    heatmap_zone = zones["heatmap"]
    proportional_zone = zones["proportional"]
    footer_zone = zones["footer"]
    identity_x, bio_x, identity_text_length, bio_text_length = compute_identity_layout(
        username=username,
        bio_text=bio_text,
        stats=stats,
        card_width=card_width,
    )
    metric_slots, text_lengths = _slot_layout(
        displays=displays,
        metric_entries=metric_entries,
        stats=stats,
        card_width=card_width,
        metric_zone_y=metric_zone.y,
        metric_zone_h=metric_zone.h,
        hero_label=hero_label,
    )
    metric_divider_xs = _metric_divider_positions(
        mode=stats.metric_layout_mode,
        card_width=card_width,
        metric_slots=metric_slots,
        metric_zone_h=metric_zone.h,
    )
    activity_baseline_y = activity_zone.end_y - 6.0 if activity_zone.present else activity_zone.y
    activity = _build_activity_bars(
        activity_bars,
        activity_peak=activity_peak,
        stats=stats,
        substrate_kind=substrate_kind,
        baseline_y=activity_baseline_y,
    )
    full_rect = RectSpec(0.0, 0.0, float(card_width), float(card_height))
    dark_perimeter = RectSpec(0.75, 0.75, card_width - 1.5, card_height - 1.5)
    light_perimeter = RectSpec(0.5, 0.5, card_width - 1.0, card_height - 1.0)
    light_bottom_strip_y = card_height - 2.0
    right_zone_w = card_width - 6.0
    grain_right_rect = RectSpec(6.0, 0.0, right_zone_w, float(card_height))
    header_right_rect = RectSpec(6.0, header_zone.y, right_zone_w, header_zone.h)
    language_shell_rect = RectSpec(6.0, proportional_zone.y, right_zone_w, proportional_zone.h)
    chrome_outer_rect = RectSpec(2.0, 2.0, card_width - 4.0, card_height - 4.0, 4.5)
    chrome_well_rect = RectSpec(4.0, 4.0, card_width - 8.0, card_height - 8.0, 3.0)
    chrome_rail_rect = RectSpec(4.0, 4.0, 6.0, card_height - 8.0)
    chrome_top_highlight_rect = RectSpec(40.0, 4.0, card_width - 80.0, 0.6, 0.3)
    cellular_outer_rect = RectSpec(0.5, 0.5, card_width - 1.0, card_height - 1.0, 8.0)
    hero_label_y = hero_zone.y + (22.0 if is_light else 20.0)
    hero_value_y = hero_zone.y + (84.0 if hero_zone.h >= 90 else max(34.0, hero_zone.h - 10.0))
    chrome_hero_rule_y = hero_zone.end_y if hero_zone.present else metric_zone.y
    chrome_hero_rule = LineSpec(22.0, chrome_hero_rule_y, card_width - 22.0, chrome_hero_rule_y)
    chrome_activity_baseline = LineSpec(22.0, activity_baseline_y, card_width - 22.0, activity_baseline_y)
    chrome_footer_rule = LineSpec(22.0, footer_zone.y, card_width - 22.0, footer_zone.y)
    rects = {
        "left_rail": RectSpec(0.0, 0.0, 6.0, float(card_height)),
        "brutalist_glyph": RectSpec(24.0, 11.0, 14.0, 14.0),
        "brutalist_status_dot": RectSpec(card_width - 23.0, 12.0, 8.0, 8.0),
        "light_top_strip": RectSpec(6.0, 0.0, right_zone_w, 2.0),
        "light_bottom_strip": RectSpec(6.0, light_bottom_strip_y, right_zone_w, 2.0),
        "light_header_panel": RectSpec(6.0, header_zone.y + 2.0, right_zone_w, max(0.0, header_zone.h - 2.0)),
        "light_header_seam": RectSpec(6.0, header_zone.end_y - 2.0, right_zone_w, 2.0),
        "chrome_glyph": RectSpec(22.0, 22.0, 14.0, 14.0),
        "chrome_horizon": RectSpec(22.0, metric_zone.end_y + 3.0, card_width - 44.0, 2.0),
        "chrome_status_anchor": RectSpec(30.0, footer_zone.y + 17.0, 0.0, 0.0),
        "chrome_status_diamond": RectSpec(-3.2, -3.2, 6.4, 6.4, 0.6),
        "chrome_present": RectSpec(-1.0, 0.0, 2.0, 4.0, 0.6),
        "chrome_clip": RectSpec(0.0, 0.0, float(card_width), float(card_height), 6.0),
        "cellular_clip": RectSpec(0.0, 0.0, float(card_width), float(card_height), cellular_outer_rect.rx),
        "cellular_header_band": RectSpec(0.0, header_zone.y, float(card_width), header_zone.h),
    }
    lines = {
        "header_rule": LineSpec(6.0, header_zone.end_y, float(card_width), header_zone.end_y),
        "hero_rule": LineSpec(6.0, hero_zone.end_y, float(card_width), hero_zone.end_y),
        "metric_vertical": LineSpec(250.0, metric_zone.y, 250.0, metric_zone.end_y),
        "metric_row": LineSpec(6.0, metric_zone.y + 36.0, float(card_width), metric_zone.y + 36.0),
        "activity_top": LineSpec(6.0, activity_zone.y, float(card_width), activity_zone.y),
        "activity_baseline": LineSpec(
            22.0,
            activity_baseline_y,
            card_width - 4.0,
            activity_baseline_y,
        ),
        "language_top": LineSpec(6.0, proportional_zone.y, float(card_width), proportional_zone.y),
        "language_footer": LineSpec(
            6.0,
            proportional_zone.end_y,
            float(card_width),
            proportional_zone.end_y,
        ),
        "chrome_metric_divider_span": LineSpec(0.0, metric_zone.y, 0.0, metric_zone.end_y),
        "chrome_hero_rule": chrome_hero_rule,
        "chrome_activity_baseline": chrome_activity_baseline,
        "chrome_footer_rule": chrome_footer_rule,
        "cellular_header_rule": LineSpec(
            0.0,
            header_zone.end_y,
            float(card_width),
            header_zone.end_y,
        ),
    }
    texts = {
        "identity": TextSpec(float(identity_x), header_zone.y + 22.0),
        "bio": TextSpec(float(bio_x), header_zone.y + 22.0),
        "hero_label": TextSpec(24.0, hero_label_y),
        "hero_delta": TextSpec(card_width - 17.0, hero_label_y, "end"),
        "hero_value": TextSpec(22.0, hero_value_y),
        "activity_label": TextSpec(24.0, activity_zone.y + 14.0),
        "activity_peak": TextSpec(card_width - 17.0, activity_zone.y + 14.0, "end"),
        "language_empty": TextSpec(14.0, stats.language_label_y_light if is_light else stats.language_label_y_dark),
        "footer_url": TextSpec(14.0, card_height - 5.0),
        "footer_brand": TextSpec(card_width - 17.0, card_height - 5.0, "end"),
        "chrome_identity": TextSpec(42.0, 33.0),
        "chrome_hero_value": TextSpec(24.0, hero_zone.y + (58.0 if hero_zone.h >= 80 else 36.0)),
        "chrome_hero_label": TextSpec(26.0, hero_zone.end_y - 6.0),
        "chrome_activity_label": TextSpec(22.0, activity_zone.y + 11.0),
        "chrome_activity_peak": TextSpec(card_width - 22.0, activity_zone.y + 11.0, "end"),
        "chrome_footer_url": TextSpec(44.0, card_height - 8.0),
        "chrome_footer_brand": TextSpec(card_width - 22.0, card_height - 8.0, "end"),
        "cellular_identity": TextSpec(float(identity_x), header_zone.y + 24.0),
        "cellular_bio": TextSpec(float(bio_x), header_zone.y + 24.0),
        "cellular_brand": TextSpec(card_width - 20.0, card_height - 12.0, "end"),
        "cellular_year": TextSpec(20.0, heatmap_zone.y + 5.6),
    }
    return StatsLayout(
        width=card_width,
        height=card_height,
        zones=zones,
        identity_x=identity_x,
        bio_x=bio_x,
        identity_text_length=identity_text_length,
        bio_text_length=bio_text_length,
        metric_slots=metric_slots,
        metric_divider_xs=metric_divider_xs,
        activity_bars=activity,
        language_segments=_build_language_segments(
            languages,
            card_width=card_width,
            stats=stats,
            substrate_kind=substrate_kind,
            zone_y=proportional_zone.y,
        ),
        inline_language_entries=_build_inline_languages(
            languages,
            card_width=card_width,
            stats=stats,
            area_tiers=area_tiers,
            y_offset=proportional_zone.y - 216.0 if stats.metric_layout_mode == "cellular_inline" else 0.0,
        ),
        heatmap_cells=_build_heatmap_cells(
            heatmap_grid,
            stats=stats,
            area_tiers=area_tiers,
            y_offset=heatmap_zone.y - 101.0 if stats.metric_layout_mode == "cellular_inline" else 0.0,
        ),
        heatmap_legend_cells=_build_legend_cells(
            stats,
            area_tiers,
            y_offset=heatmap_zone.y - 101.0 if stats.metric_layout_mode == "cellular_inline" else 0.0,
        ),
        commits_text_length=text_lengths.get("commits_text_length", 0.0),
        prs_text_length=text_lengths.get("prs_text_length", 0.0),
        issues_text_length=text_lengths.get("issues_text_length", 0.0),
        streak_text_length=text_lengths.get("streak_text_length", 0.0),
        activity_baseline_y=activity_baseline_y,
        activity_present_x=round(stats.activity_bar_start_x + len(activity_bars) * stats.activity_bar_stride, 3),
        activity_present_y=round(activity_baseline_y - stats.activity_bar_min_h, 3),
        right_zone_w=right_zone_w,
        dark_perimeter=dark_perimeter,
        light_perimeter=light_perimeter,
        light_bottom_strip_y=light_bottom_strip_y,
        chrome_outer_rect=chrome_outer_rect,
        chrome_well_rect=chrome_well_rect,
        chrome_rail_rect=chrome_rail_rect,
        chrome_top_highlight_rect=chrome_top_highlight_rect,
        cellular_outer_rect=cellular_outer_rect,
        full_rect=full_rect,
        rects=rects,
        lines=lines,
        texts=texts,
        grain_right_rect=grain_right_rect,
        header_right_rect=header_right_rect,
        language_shell_rect=language_shell_rect,
        chrome_hero_rule=chrome_hero_rule,
        chrome_activity_baseline=chrome_activity_baseline,
        chrome_footer_rule=chrome_footer_rule,
    )
