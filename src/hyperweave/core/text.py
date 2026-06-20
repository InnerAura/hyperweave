"""Text width measurement backed by per-font LUTs.

Deterministic width estimation for the shipped supported ASCII glyph set,
using per-codepoint advance widths scaled linearly by font size.
Kerning ignored. Ligatures ignored. Non-ASCII codepoints fall back to the
font's declared ``fallback_width``. Unknown font families fall back to
Inter metrics with a one-shot warning log per family — never to
genome-specific multipliers.

Add a new font LUT by running::

    uv run python scripts/extract_font_metrics.py <slug>

which writes ``src/hyperweave/data/font-metrics/<slug>.json``. The
:class:`hyperweave.core.font_metrics.FontRegistry` picks it up on the
next process start (or after :func:`hyperweave.core.font_metrics.reset_registry`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hyperweave.core.font_metrics import get_registry

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hyperweave.core.font_metrics import FontMetrics


@dataclass(frozen=True, slots=True)
class TextInkMetrics:
    """Advance and visible-ink bounds for a measured text run."""

    advance_width: float
    ink_width: float
    leading_bearing: float
    trailing_bearing: float
    ink_top_offset_y: float = 0.0
    """SVG y offset from baseline to the run's visible top edge."""
    ink_bottom_offset_y: float = 0.0
    """SVG y offset from baseline to the run's visible bottom edge."""
    ink_center_offset_y: float = 0.0
    """SVG y offset from baseline to the run's visible vertical center."""


def _nearest_weight_key(weighted: Mapping[str, object], font_weight: int) -> str | None:
    """Return the nearest available CSS weight key for a weighted metrics map."""
    if not weighted:
        return None
    numeric_keys: list[int] = []
    for key in weighted:
        try:
            numeric_keys.append(int(key))
        except ValueError:
            continue
    if not numeric_keys:
        return None
    nearest = min(numeric_keys, key=lambda value: abs(value - font_weight))
    return str(nearest)


def _widths_for_weight(metrics: FontMetrics, font_weight: int) -> tuple[dict[str, int], bool]:
    """Return width map plus whether it came from real weight-specific data."""
    key = _nearest_weight_key(metrics.widths_by_weight, font_weight)
    if key is None:
        return metrics.widths, False
    return metrics.widths_by_weight[key], True


def _bearings_for_weight(metrics: FontMetrics, font_weight: int) -> dict[str, list[int]]:
    """Return weight-specific bearings when available, else default bearings."""
    key = _nearest_weight_key(metrics.bearings_by_weight, font_weight)
    if key is None:
        return metrics.bearings
    return metrics.bearings_by_weight[key]


def _vertical_bounds_for_weight(metrics: FontMetrics, font_weight: int) -> dict[str, list[int]]:
    """Return weight-specific vertical ink bounds when available."""
    key = _nearest_weight_key(metrics.vertical_bounds_by_weight, font_weight)
    if key is None:
        return metrics.vertical_bounds
    return metrics.vertical_bounds_by_weight[key]


def measure_text(
    text: str,
    *,
    font_family: str = "Inter",
    font_size: float = 11.0,
    font_weight: int = 400,
    letter_spacing_em: float = 0.0,
) -> float:
    """Estimate the rendered width of ``text`` in pixels.

    The text measurement pipeline:

    1. Resolve ``font_family`` to a :class:`FontMetrics` LUT via the
       :class:`FontRegistry` (falls back to Inter + one-shot warning on
       unknown families).
    2. For monospace fonts, width = ``len(text) * char_width_px``
       scaled linearly by ``font_size / baseline_size_px``.
       For proportional fonts, sum per-codepoint advance widths (tenths
       of pixels at ``baseline_size_px``), divide by 10, scale by size.
    3. For variable fonts with per-weight LUT data, use the nearest real
       weight's advance widths. Otherwise apply ``bold_expansion_factor``
       when ``font_weight >= 700`` for non-monospace fonts.
    4. Absorb letter-spacing: add ``max(0, len(text) - 1) *
       font_size * letter_spacing_em`` so callers don't repeat the
       arithmetic themselves.
    """
    metrics = get_registry().get(font_family)
    baseline = metrics.baseline_size_px

    if metrics.is_monospace:
        base_px = len(text) * metrics.char_width_px * (font_size / baseline)
    else:
        widths, used_weighted_metrics = _widths_for_weight(metrics, font_weight)
        total_tenths = 0.0
        for ch in text:
            total_tenths += widths.get(ch, metrics.fallback_width)
        base_px = (total_tenths / 10.0) * (font_size / baseline)
        if not used_weighted_metrics and font_weight >= 700:
            base_px *= metrics.bold_expansion_factor

    if text and letter_spacing_em:
        base_px += max(0, len(text) - 1) * font_size * letter_spacing_em

    return base_px


def measure_text_ink_width(
    text: str,
    *,
    font_family: str = "Inter",
    font_size: float = 11.0,
    font_weight: int = 400,
    letter_spacing_em: float = 0.0,
) -> float:
    """Estimate the rendered visible-ink width of ``text`` in pixels.

    Like :func:`measure_text` but subtracts the first glyph's left side
    bearing (LSB) and the last glyph's right side bearing (RSB) from the
    advance width. The result is the distance between the leftmost
    visible ink and the rightmost visible ink — what a human perceives
    as the text's "actual width".

    For SEAM/right-edge placement (single-sided), use
    :func:`measure_text_trailing_bearing` instead — that returns only the
    last-glyph RSB which is the correct correction for cursor-walk
    placement at the text's right side.

    Fallback: when a legacy font LUT lacks the optional ``bearings`` map,
    returns the same value as :func:`measure_text`. Fonts extracted via
    ``scripts/extract_font_metrics.py`` carry bearings by default.

    Whitespace-only strings return 0 (no visible ink).
    """
    return measure_text_ink_metrics(
        text,
        font_family=font_family,
        font_size=font_size,
        font_weight=font_weight,
        letter_spacing_em=letter_spacing_em,
    ).ink_width


def measure_text_ink_metrics(
    text: str,
    *,
    font_family: str = "Inter",
    font_size: float = 11.0,
    font_weight: int = 400,
    letter_spacing_em: float = 0.0,
) -> TextInkMetrics:
    """Return advance width plus first/last side bearings for visual layout.

    SVG ``text-anchor="middle"`` centers the advance box, not the ink box.
    Layout code that needs visually balanced gaps must therefore know the
    first glyph's left side bearing and the last glyph's right side bearing,
    not just the total advance width.
    """
    if not text:
        return TextInkMetrics(advance_width=0.0, ink_width=0.0, leading_bearing=0.0, trailing_bearing=0.0)

    advance = measure_text(
        text,
        font_family=font_family,
        font_size=font_size,
        font_weight=font_weight,
        letter_spacing_em=letter_spacing_em,
    )
    metrics = get_registry().get(font_family)
    baseline = metrics.baseline_size_px
    scale = font_size / baseline
    bearings = _bearings_for_weight(metrics, font_weight)
    lsb_px = 0.0
    rsb_px = 0.0
    if bearings:
        first_char = text[0]
        last_char = text[-1]
        # bearings stored as tenths-of-pixels at baseline_size_px; scale to
        # the requested font_size and back to pixels.
        first_lsb_tenths, _first_rsb = bearings.get(first_char, [0, 0])
        _last_lsb, last_rsb_tenths = bearings.get(last_char, [0, 0])
        lsb_px = (first_lsb_tenths / 10.0) * scale
        rsb_px = (last_rsb_tenths / 10.0) * scale

    vertical_bounds = _vertical_bounds_for_weight(metrics, font_weight)
    top_offset_y = 0.0
    bottom_offset_y = 0.0
    center_offset_y = 0.0
    if vertical_bounds:
        ymin_values: list[int] = []
        ymax_values: list[int] = []
        for ch in text:
            bounds = vertical_bounds.get(ch)
            if bounds is None:
                continue
            ymin_values.append(bounds[0])
            ymax_values.append(bounds[1])
        if ymin_values and ymax_values:
            ymin_px = (min(ymin_values) / 10.0) * scale
            ymax_px = (max(ymax_values) / 10.0) * scale
            top_offset_y = -ymax_px
            bottom_offset_y = -ymin_px
            center_offset_y = (top_offset_y + bottom_offset_y) / 2.0

    return TextInkMetrics(
        advance_width=advance,
        ink_width=max(0.0, advance - lsb_px - rsb_px),
        leading_bearing=lsb_px,
        trailing_bearing=rsb_px,
        ink_top_offset_y=top_offset_y,
        ink_bottom_offset_y=bottom_offset_y,
        ink_center_offset_y=center_offset_y,
    )


def measure_text_trailing_bearing(
    text: str,
    *,
    font_family: str = "Inter",
    font_size: float = 11.0,
    font_weight: int = 400,
) -> float:
    """Return the last glyph's right-side bearing in pixels at ``font_size``.

    The cursor-walk in ``compute_badge_zones`` uses this to place the seam
    at ``visible_ink_end + pad/2`` instead of ``advance_end + pad/2``.
    For text-anchor=start paradigms (chrome), the trailing bearing
    accumulates on the right side as visual asymmetry — subtracting it
    closes the seam gap to the design-intent ``pad/2`` uniformly across
    all labels regardless of last-glyph identity (S, K, I all corrected
    appropriately by their own RSB, not a paradigm-wide scalar).

    Returns 0.0 when the font's LUT lacks bearings or when text is empty.
    """
    if not text:
        return 0.0
    return measure_text_ink_metrics(
        text,
        font_family=font_family,
        font_size=font_size,
        font_weight=font_weight,
    ).trailing_bearing


def format_duration(minutes: float) -> str:
    """Format a duration in minutes as a compact human label.

    Long agent sessions run for thousands of minutes — "3334m" is unreadable on
    an axis tick or a hero subline. This collapses the magnitude to the largest
    sensible unit, dropping a trailing ``.0`` so clean values stay terse:

    * ``< 60``       -> ``"{m}m"``         (e.g. ``45m``, ``0m``)
    * ``< 1440``     -> ``"{h}h"`` /``"{h.h}h"`` (e.g. ``2h``, ``10.8h``)
    * ``>= 1440``    -> ``"{d}d"`` /``"{d}d {h}h"`` (e.g. ``2d``, ``2d 8h``)

    The day form rounds the remainder to whole hours (a sub-hour remainder is
    dropped: ``2880`` → ``"2d"``, ``3334`` → ``"2d 8h"``). The hour form keeps
    one decimal only when it isn't whole, so adaptive "nice" tick steps that land
    on exact hours read as ``"10h"`` not ``"10.0h"``. Negative inputs clamp to 0.
    """
    if minutes < 0:
        minutes = 0.0

    if minutes < 60:
        return f"{round(minutes)}m"

    if minutes < 1440:
        hours = minutes / 60.0
        rounded = round(hours, 1)
        if rounded == int(rounded):
            return f"{int(rounded)}h"
        return f"{rounded:.1f}h"

    days = int(minutes // 1440)
    remainder_hours = round((minutes - days * 1440) / 60.0)
    # A remainder that rounds up to a full day rolls into the day count.
    if remainder_hours >= 24:
        days += remainder_hours // 24
        remainder_hours %= 24
    if remainder_hours == 0:
        return f"{days}d"
    return f"{days}d {remainder_hours}h"
