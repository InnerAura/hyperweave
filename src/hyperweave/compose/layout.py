"""Centralized spatial-layout engine for badge / strip frames (v0.2.25).

Single source of truth for badge geometry. Replaces the inline arithmetic
that lived in ``compose/resolver.py:resolve_badge`` (lines 270-354) and
the duplicated geometry derivations in ``templates/frames/badge/*.j2``
(brutalist's right_x/right_w, cellular's inner_w/inner_off, the per-
template indicator_y duplicates).

Per Invariant 6 (CLAUDE.md): templates render, compose computes geometry.
Per ``feedback_compose_owns_geometry_template_renders.md``: layout
decisions belong in compose/, not Jinja2.

Two ``value_x`` regressions corrected by ``compute_badge_layout``:

1. **Geometric centering, not midpoint of unrelated bounds.** The old
   resolver used ``value_x = (right_x + val_pad_l + indicator_x) / 2``,
   which is the midpoint of [value_zone_left, indicator_left_edge].
   Indicator's left edge is val_min_gap inside the actual value-zone
   right boundary. Result: text drifts ``val_min_gap/2 = 1.5px``
   rightward. The new formula centers on the actual zone center.
2. **No-indicator case is undefined under the old formula.** When the
   indicator isn't rendered, ``indicator_x`` (still computed as
   ``total_w - ind_pad_r - indicator_size``) lands *inside* or *left
   of* the value text. The old midpoint averages two unrelated points.
   The new formula uses ``total_w - val_min_gap`` as the right bound
   when ``show_indicator=False`` and converges to a sane center.

Three orthogonal helpers live here so all layout-and-mode decisions
share a module:

- ``compute_badge_layout`` — geometry only; pure function over input
  measurements and paradigm constants.
- ``resolve_badge_mode`` — three-mode classification
  (stateful / stateless / explicit) keyed off the spec and a title
  allowlist loaded from ``data/badge_modes.yaml``.
- ``decide_strip_mode`` — same classification rolled up over a strip's
  metric labels.

The data-hw-statemode SVG-root attribute that gates threshold-CSS
auto-tinting in ``data/css/expression.css`` is derived from the badge
mode via ``data_hw_statemode_for``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable

    from hyperweave.core.models import ComposeSpec


BadgeMode = Literal["stateful", "stateless", "explicit"]


@dataclass(frozen=True)
class BadgeLayout:
    """Resolved spatial layout for a badge frame.

    Templates consume these directly via ``{{ width }}``, ``{{ label_x }}``,
    ``{{ value_x }}``, etc. — no template-side arithmetic. The
    ``value_zone_*`` fields are exported for unit-test assertions.
    """

    width: int
    height: int
    label_x: float
    value_x: float
    glyph_x: int
    glyph_y: float
    indicator_x: float
    indicator_y: float
    indicator_size: int
    left_panel_w: int
    right_panel_x: int
    right_panel_w: int
    value_zone_left: float
    value_zone_right: float
    value_zone_width: float
    text_y: float
    show_indicator: bool
    inner_bit_w: int
    inner_bit_offset: float


def compute_badge_layout(
    *,
    height: int,
    measured_label_w: float,
    measured_value_w: float,
    has_glyph: bool,
    show_indicator: bool,
    use_mono: bool,
    label_uppercase: bool,
    value_raw_len: int,
    accent_w: int,
    inset: int,
    glyph_size: int,
    glyph_gap: int,
    glyph_left_offset: int,
    sep_w: int,
    seam_w: int,
    indicator_size: int,
    ind_pad_r: int,
    val_pad_l: int,
    val_min_gap: int,
    text_y_factor: float,
    value_font_size: float,
    right_canvas_inset: int = 0,
    min_total_w: int = 60,
) -> BadgeLayout:
    """Compute every position the badge templates need from input measurements.

    All positional fields in the returned ``BadgeLayout`` are measured
    from the SVG origin (top-left). Geometry decisions (left/right panel
    widths, indicator centering, glyph centering, value-zone centering)
    are made here so all paradigms inherit the same correctness without
    re-deriving in templates.

    The centering correctness is verified by ``tests/test_badge_layout``
    against short / long / version / license / python_requires values.
    """
    # Glyph pixel position. Mirrors resolver.py logic: paradigms with a
    # left-edge decoration zone (cellular pattern strip x=2..~20) reserve
    # space via ``glyph_left_offset``; brutalist/chrome declare 0.
    if has_glyph:
        glyph_x = (inset + accent_w + 4) if inset else (accent_w + 3)
        glyph_x += glyph_left_offset
        glyph_y = round((height - glyph_size) / 2, 1)
    else:
        glyph_x, glyph_y = 0, 0.0

    # Label area starts after the glyph (or after the accent + paradigm
    # left-edge decoration when there's no glyph). The no-glyph branch
    # must respect glyph_left_offset too — cellular pattern strip runs
    # to ~x=20 even when no glyph is rendered.
    label_start = (glyph_x + glyph_size + glyph_gap) if has_glyph else (accent_w + 6 + glyph_left_offset)

    # Left panel width — fits the label plus paradigm-driven right padding.
    label_pad_r = 9 if use_mono else 8
    left_panel = round(label_start + measured_label_w + label_pad_r)
    left_panel = max(left_panel, 30)

    # Label text center is the midpoint of the label area. For uppercase
    # labels the visual right edge is 6px shy of the panel boundary so
    # the cap glyphs don't kiss the seam.
    label_area_end = left_panel - (6 if label_uppercase else 0)
    label_x = round((label_start + label_area_end) / 2, 1)

    # Right-panel allocation. ``ls_extra`` accounts for non-mono letter-
    # spacing overrun (each char carries 0.4 of trailing tracking).
    indicator_alloc = (indicator_size + ind_pad_r) if show_indicator else 0
    ls_extra = value_raw_len * 0.4 if (not use_mono and value_raw_len) else 0
    # right_panel reserves: val_pad_l (left interior gutter), the measured
    # value text + letter-spacing overrun, val_min_gap (right interior gutter),
    # and indicator_alloc when stateful. Pre-v0.3.0 reserved 2 * val_min_gap
    # which left ~val_min_gap of unaccounted slack on stateless badges
    # (visible as ~4.5px right padding instead of symmetric ~3px).
    right_panel = val_pad_l + measured_value_w + ls_extra + val_min_gap + indicator_alloc
    total_w = round(left_panel + sep_w + seam_w + right_panel)
    total_w = max(total_w, min_total_w)

    right_panel_x = left_panel + sep_w + seam_w
    right_panel_w = total_w - right_panel_x

    # Indicator position. Computed even when not shown — templates
    # gate the actual rendering on ``show_indicator``; the value-zone
    # center collapses to total_w-val_min_gap when the indicator is
    # absent so the value text reclaims the freed space.
    indicator_x = total_w - ind_pad_r - indicator_size

    # Value-zone bounds — the heart of the v0.2.25 centering fix. The
    # OLD resolver used ``(right_panel_x + val_pad_l + indicator_x) / 2``
    # which is the midpoint of [zone_left, indicator_left_edge], not
    # [zone_left, zone_right]. Old formula skewed text by val_min_gap/2
    # toward the indicator and was undefined when no indicator rendered.
    value_zone_left = right_panel_x + val_pad_l
    # When stateless (no indicator), the slab's right edge is total_w minus
    # any paradigm-specific canvas inset (cellular: 2; brutalist/chrome: 0).
    # val_min_gap is the symmetric trailing pad — together they place
    # value_zone_right at the slab's interior right boundary so a centered
    # text lands at slab geometric center.
    value_zone_right = (indicator_x - val_min_gap) if show_indicator else (total_w - right_canvas_inset - val_min_gap)
    value_zone_width = value_zone_right - value_zone_left
    value_x = round((value_zone_left + value_zone_right) / 2, 1)

    text_y = round(height * text_y_factor, 1)
    # Indicator vertical center pinned to value-text visual midline.
    # cap_height ≈ 70% of font_size across the genome's display fonts
    # (validated in data/font-metrics/), so visual_center = text_y -
    # 0.3 * font_size. Indicator is square; top-y = visual_center -
    # size/2. Single source of truth for vertical alignment across
    # paradigms.
    indicator_y = round(text_y - value_font_size * 0.3 - indicator_size / 2, 1)

    # Indicator inner-bit geometry — moved from cellular/brutalist
    # template-side arithmetic. The bit is half the indicator side,
    # centered.
    inner_bit_w = indicator_size // 2
    inner_bit_offset = (indicator_size - inner_bit_w) / 2

    return BadgeLayout(
        width=total_w,
        height=height,
        label_x=label_x,
        value_x=value_x,
        glyph_x=glyph_x,
        glyph_y=glyph_y,
        indicator_x=indicator_x,
        indicator_y=indicator_y,
        indicator_size=indicator_size,
        left_panel_w=left_panel,
        right_panel_x=right_panel_x,
        right_panel_w=right_panel_w,
        value_zone_left=value_zone_left,
        value_zone_right=value_zone_right,
        value_zone_width=value_zone_width,
        text_y=text_y,
        show_indicator=show_indicator,
        inner_bit_w=inner_bit_w,
        inner_bit_offset=inner_bit_offset,
    )


# ─────────────────────────────────────────────────────────────────────
# Three-mode state architecture
# ─────────────────────────────────────────────────────────────────────


def normalize_title(title: str | None) -> str:
    """Lowercase + strip hyphens/underscores so allowlist lookup is
    insensitive to common separator variants.

    ``BUILD-STATUS`` → ``buildstatus``; ``CI_CD`` → ``cicd``. URL slashes
    can't appear in path segments (they'd split into separate parts), so
    we don't need slash handling. Empty / None → empty string.
    """
    if not title:
        return ""
    return title.lower().replace("-", "").replace("_", "")


def resolve_badge_mode(spec: ComposeSpec, allowlist: frozenset[str]) -> BadgeMode:
    """Classify a badge as stateful / stateless / explicit.

    Three modes drive two orthogonal behaviors at render time:

    * Indicator rendering: ``show_indicator = mode != "stateless"``
    * Threshold-CSS auto-inference: gated by ``data-hw-statemode="auto"``
      on the SVG root, which fires only for ``stateful`` (auto-inferred
      from leading-digit value). ``stateless`` and ``explicit`` skip it.

    Title lookup normalizes via ``normalize_title`` (lowercase, strip
    hyphens/underscores) so ``BUILD-STATUS`` and ``BUILD_STATUS`` both
    match the canonical ``buildstatus`` allowlist entry without bloating
    the YAML with every separator variant.

    Note on ``spec.state == "active"``: ComposeSpec defaults ``state`` to
    the truthy sentinel ``"active"`` (Pydantic default in
    core/models.py:98), NOT empty string. Treat that sentinel as "user
    did not opine" — fall through to the allowlist check. Any other
    value (including ``"active"`` if explicitly re-set, which is fine)
    means the caller asked for a specific state → explicit mode.
    """
    if spec.state and spec.state != "active":
        return "explicit"
    title = normalize_title(spec.title)
    if title and title in allowlist:
        return "stateful"
    return "stateless"


def decide_strip_mode(
    metric_titles: Iterable[str | None],
    spec: ComposeSpec,
    allowlist: frozenset[str],
) -> BadgeMode:
    """Roll up the strip's mode from its metric cells' titles.

    Strip's right-edge indicator is the strip's overall health pixel.
    If ANY metric is stateful, the indicator renders with rolled-up
    state. Stateless cells coexist; per-cell indicators were already
    rejected (memory: ``feedback_strip_single_diamond.md``).

    Metric titles are normalized via ``normalize_title`` for the same
    reasons as ``resolve_badge_mode`` — ``BUILD-STATUS`` cell matches
    the same canonical ``buildstatus`` allowlist entry.
    """
    if spec.state and spec.state != "active":
        return "explicit"
    for title in metric_titles:
        if title and normalize_title(title) in allowlist:
            return "stateful"
    return "stateless"


def data_hw_statemode_for(mode: BadgeMode) -> str:
    """Map ``BadgeMode`` to the SVG-root ``data-hw-statemode`` attribute value.

    The CSS in ``data/css/expression.css`` qualifies its threshold
    selectors with ``[data-hw-statemode="auto"]`` so auto-inference
    only applies to ``stateful``. ``stateless`` ("off") and ``explicit``
    ("explicit") bypass auto-tinting; explicit-mode badges still get
    state colors via the ``[data-hw-status="..."]`` cascade.
    """
    return {"stateful": "auto", "explicit": "explicit", "stateless": "off"}[mode]
