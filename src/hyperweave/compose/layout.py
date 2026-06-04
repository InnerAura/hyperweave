"""Centralized spatial-layout engine for badge / strip frames.

Single source of truth for badge AND strip geometry. Replaces the inline
arithmetic that lived in ``compose/resolver.py:resolve_badge`` and
``resolve_strip``, and the duplicated geometry derivations in
``templates/frames/{badge,strip}/*.j2``.

Per Invariant 6 (CLAUDE.md): templates render, compose computes geometry.
Per ``feedback_compose_owns_geometry_template_renders.md``: layout
decisions belong in compose/, not Jinja2.

v0.3.9 equal-spacing rule:

    Every gap between PRESENT zones equals ``pad``. Absent zones collapse
    entirely — no phantom slot, no reserved width. The rule is paradigm-
    agnostic; ``pad`` comes from ``ParadigmBadgeConfig.pad`` so each
    paradigm tunes its visual rhythm without touching the layout code.

    Sequence (left → right) for a badge:
        accent_w  +  pad  +  [glyph + pad]  +  label + pad  +  [sep+seam]
                  +  pad  +  value + pad  +  [state_indicator + pad]
                  +  right_canvas_inset

    Glyph zone and state-indicator zone are gated by ``has_glyph`` and
    ``has_state_indicator``. When False, the cursor never advances into
    them — the badge shrinks accordingly.

Public surface:

- ``BadgeZones`` / ``compute_badge_zones`` — badge geometry (the v0.3.9
  zone-based replacement for the prior ``BadgeLayout`` / ``compute_badge_layout``).
- ``StripZones`` / ``compute_strip_zones`` — strip geometry (the v0.3.9
  introduction; supersedes inline arithmetic in ``resolve_strip``).
- ``resolve_badge_mode`` — three-mode classification (stateful / stateless
  / explicit) keyed off the spec and a title allowlist.
- ``decide_strip_mode`` — same classification rolled up over a strip's
  metric labels.
- ``data_hw_statemode_for`` — maps mode to the ``data-hw-statemode``
  SVG-root attribute that gates threshold-CSS auto-tinting in
  ``data/css/expression.css``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable

    from hyperweave.core.models import ComposeSpec


BadgeMode = Literal["stateful", "stateless", "explicit"]


def compute_strip_glyph_size(strip_height: int, strip_glyph_ratio: float) -> int:
    """Derive the strip identity glyph size from its container.

    The identity glyph is sized as a fraction of strip height so all
    paradigms scale uniformly. Default ratio 0.346 yields 18px at
    strip_height=52 — the v0.3.9 design constant established by brutalist's
    specimen (an 18px identity glyph in a 52px strip).

    Replaces v0.3.9-and-prior hand-synced pair
    (chrome ``glyph_size: 22`` + brutalist ``identity_glyph_size: 18``) that
    had to stay in proportional agreement by manual update. Single
    computation site so regression tests can pin the derivation.
    """
    return round(strip_height * strip_glyph_ratio)


def compute_badge_glyph_size(badge_height: int, badge_glyph_ratio: float, glyph_size_max: int = 0) -> int:
    """Derive a badge glyph render-box size from the badge height.

    Badges across paradigms share the same identity-glyph weight instead of
    carrying per-template magic sizes. ``glyph_size_max`` lets taller badge
    variants keep the canonical compact glyph weight while still using the
    same proportional rule for 20px badges.
    """
    size = round(badge_height * badge_glyph_ratio)
    if glyph_size_max > 0:
        size = min(size, glyph_size_max)
    return max(1, size)


@dataclass(frozen=True, slots=True)
class BadgeZones:
    """Resolved zone layout for a badge frame.

    Templates consume these directly via ``{{ width }}``, ``{{ label_x }}``,
    ``{{ value_x }}``, etc. — no template-side arithmetic. ``label_text_length``
    and ``value_text_length`` carry the SVG ``textLength`` attribute = the
    measured text width (the camo bound — pins a fallback font to the zone),
    overridden to the clamped width when shrink-to-fit is active.

    Equal-spacing rule (v0.3.9): every gap between PRESENT zones equals
    ``pad``. Absent zones (no glyph, no state indicator) collapse fully —
    no reserved width, no phantom gap.
    """

    width: int
    height: int
    glyph_x: float
    """Left edge of glyph zone. 0.0 when ``has_glyph=False``."""
    glyph_y: float
    """Top edge of glyph zone (vertically centered in badge). 0.0 when absent."""
    glyph_size: int
    """Glyph render-box side length. 0 when ``has_glyph=False``."""
    label_x: float
    """SVG x for label ``<text>``. ``text_anchor='middle'``: center of label.
    ``text_anchor='start'``: first character x. Determined by paradigm config."""
    label_w: float
    """Measured label render width (after any shrink-to-fit clamp)."""
    label_text_length: float
    """SVG ``textLength`` attribute value. 0.0 = no shrink-to-fit."""
    seam_x: float
    """x of the seam midline (left_panel_w + sep_w/2)."""
    seam_right_x: float
    """Right edge of the rendered seam/separator band."""
    value_x: float
    """SVG x for value ``<text>`` center."""
    value_w: float
    """Measured value render width (after any shrink-to-fit clamp)."""
    value_text_length: float
    """SVG ``textLength`` for value. 0.0 = no shrink-to-fit."""
    indicator_x: float
    """Left edge of state indicator. 0.0 when ``has_state_indicator=False``."""
    indicator_y: float
    """Top edge of state indicator (= indicator_center_y - size/2). 0.0 when absent."""
    indicator_center_y: float
    """Vertical center of the state indicator — the SINGLE source every shape
    anchors to (square top-left derives ``- size/2``; circle/diamond use it
    directly). Equals the content reading line (``text_visual_center +
    glyph_y_offset``) — i.e. the identity glyph's center — so the status glyph and
    the brand glyph share one line on every paradigm. 0.0 when absent."""
    indicator_size: int
    """State indicator side length. 0 when absent."""
    left_panel_w: int
    """Width of the left panel (glyph + label + interior padding)."""
    right_panel_x: int
    """x of the right panel's left edge (left_panel_w + sep_w + seam_w)."""
    right_panel_w: int
    """Right panel width (total_w - right_panel_x)."""
    text_y: float
    """Baseline y for label + value text."""
    show_indicator: bool
    """Mirror of ``has_state_indicator`` (kept for template compatibility)."""
    inner_bit_w: int
    """Inner bit side length inside the indicator's outer ring."""
    inner_bit_offset: float
    """Offset from indicator's outer ring to inner bit (= (size - bit_w) / 2)."""
    value_zone_left: float
    """Left bound of value text zone (kept for backward-compat with assertion tests)."""
    value_zone_right: float
    """Right bound of value text zone."""
    value_zone_width: float
    """value_zone_right - value_zone_left."""
    # Chrome etched seam (paradigm with seam_render_w > 0; 0 for other paradigms).
    seam_left_x: float = 0
    """Left hairline of the chrome etched seam (dark cut). 0 when no etched seam."""
    seam_specular_x: float = 0
    """Right hairline of the chrome etched seam (specular catch). 0 when no etched seam."""
    text_anchor: str = "middle"
    """SVG text-anchor for label/value. Paradigm-declared: ``middle`` (brutalist/cellular)
    centers text on ``label_x``/``value_x``; ``start`` (chrome) anchors first-character x."""


def compute_badge_zones(
    *,
    height: int,
    pad: int,
    measured_label_w: float,
    measured_value_w: float,
    has_glyph: bool,
    has_state_indicator: bool,
    accent_w: int,
    glyph_size: int,
    glyph_left_offset: int,
    sep_w: int,
    seam_w: int,
    indicator_size: int,
    right_canvas_inset: int = 0,
    min_total_w: int = 60,
    inner_bit_ratio: float = 0.5,
    text_y_factor: float = 0.69,
    label_font_size: float = 11,
    value_font_size: float = 11,
    max_label_w: float = 0,
    max_value_w: float = 0,
    label_w_floor: int = 30,
    text_anchor: str = "middle",
    seam_render_w: float = 0.0,
    seam_specular_offset: float = 0.0,
    label_end_bearing: float = 0.0,
    value_end_bearing: float = 0.0,
    measured_label_ink_w: float = 0.0,
    measured_value_ink_w: float = 0.0,
    label_start_bearing: float = 0.0,
    value_start_bearing: float = 0.0,
    glyph_y_offset: float = 0.0,
    text_visual_center_offset_em: float = 0.3,
    text_ink_center_offset_y: float = 0.0,
    center_glyph_on_text_ink: bool = False,
    glyph_visual_w: float = 0.0,
    left_adornment_width: float = 0.0,
    left_adornment_gap: float = 0.0,
    glyph_label_gap: float = 0.0,
    visual_gap: float = 0.0,
) -> BadgeZones:
    """Compute badge zone layout under the unified additive algorithm.

    Algorithm
    ---------
    Single additive cursor walk for ALL paradigms. Removes the prior
    fixed/budget mode split; paradigm-specific structural differences flow
    through config (``text_anchor``, ``seam_render_w``, ``seam_specular_offset``,
    ``pad``).

    Cursor walks left to right. By default it starts at
    ``accent_w + glyph_left_offset + pad`` (structural frame). Paradigms with
    a left adornment, such as cellular's pattern bookend, may instead declare
    the adornment's right edge and the post-adornment gap directly. For each
    PRESENT zone, the cursor advances by the zone's content width plus
    ``pad``. Absent zones (no glyph, no state indicator) are skipped entirely
    — the cursor never advances into a reserved slot.

    Panel separator handling (two orthogonal modes):

    * ``seam_render_w > 0`` (chrome): etched-seam slot between label and
      value zones with half-gaps on each side (``pad/2`` left + ``pad/2``
      right). Emits ``seam_left_x`` (dark cut) and ``seam_specular_x`` (catch,
      offset by ``seam_specular_offset``). Synthetic ``left_panel_w`` /
      ``right_panel_x`` derived from seam center for template backward-compat.
    * ``seam_render_w == 0`` (brutalist + cellular): structural panel
      separator (``sep_w`` stroke + ``seam_w`` mark). Full pad on each side
      of the panel boundary. No etched seam hairlines emitted.

    Shrink-to-fit + camo bound
    --------------------------
    ``label_text_length`` is ALWAYS the measured label width so templates emit
    ``textLength`` + ``lengthAdjust="spacingAndGlyphs"`` — a camo bound that
    keeps a fallback font (when ``@font-face`` is blocked) from rendering wider
    than the zone. When ``max_label_w > 0`` and ``measured_label_w >
    max_label_w`` the label additionally shrinks: ``label_w`` clamps to
    ``max_label_w`` and ``label_text_length`` becomes that clamped width. Same
    logic for value.

    SVG text anchoring
    ------------------
    Paradigm declares ``text_anchor``. ``middle`` (brutalist/cellular):
    ``label_x``/``value_x`` are zone centers. ``start`` (chrome): they are
    first-character positions. Templates render
    ``<text text-anchor="{{ text_anchor }}" x="{{ label_x }}">``.
    """
    # Clamp label and value to shrink-to-fit ceilings before geometry.
    # Camo bound (v0.3.13): textLength pins the rendered text to its
    # MEASURED width even when it fits (not just on shrink-to-fit), so a
    # fallback font can't render WIDER than the content-sized zone and cross
    # the seam. GitHub camo blocks @font-face, so Orbitron/JBM never load and
    # the wider sans-serif fallback would otherwise overflow (e.g. CHROME's "E"
    # past the seam). No-op when the real font loads. Same bound the strip
    # identity carries; one place, every genome's badge.
    label_w = measured_label_w
    label_ink_w = measured_label_ink_w if measured_label_ink_w > 0 else measured_label_w
    label_text_length = round(measured_label_w, 1) if measured_label_w > 0 else 0.0
    if max_label_w > 0 and measured_label_w > max_label_w:
        scale = max_label_w / measured_label_w if measured_label_w > 0 else 1.0
        label_w = max_label_w
        label_ink_w *= scale
        label_start_bearing *= scale
        label_end_bearing *= scale
        label_text_length = max_label_w

    value_w = measured_value_w
    value_ink_w = measured_value_ink_w if measured_value_ink_w > 0 else measured_value_w
    value_text_length = round(measured_value_w, 1) if measured_value_w > 0 else 0.0
    if max_value_w > 0 and measured_value_w > max_value_w:
        scale = max_value_w / measured_value_w if measured_value_w > 0 else 1.0
        value_w = max_value_w
        value_ink_w *= scale
        value_start_bearing *= scale
        value_end_bearing *= scale
        value_text_length = max_value_w

    # Text baseline (label + value share the same y for consistent reading line).
    text_y = round(height * text_y_factor, 1)

    # Content reading line — the single vertical anchor for BOTH the identity
    # glyph and the state indicator, so the two glyphs sit on one line on every
    # paradigm. ``text_visual_center`` is where text optically centers (real font
    # ink metrics when supplied, else the 0.3em heuristic); ``glyph_y_offset`` is
    # the paradigm's nudge onto the rendered reading line. Geometric center
    # (height/2) drifts off this line wherever the paradigm's content line isn't
    # the badge midline (e.g. chrome: reading line ≈10.5, midline 10.0).
    if center_glyph_on_text_ink:
        text_visual_center = text_y + text_ink_center_offset_y
    else:
        text_visual_center = text_y - label_font_size * text_visual_center_offset_em
    # Unrounded so each consumer rounds once (glyph_y stays byte-identical to the
    # original ``text_visual_center - glyph_size/2 + glyph_y_offset`` formula).
    content_reading_center = text_visual_center + glyph_y_offset

    # Structural frame ends at accent + legacy left-decoration offset, unless
    # a paradigm supplies the rendered left adornment boundary explicitly.
    # Cellular does this for its pattern bookend so compact badges can use a
    # tight bookend→glyph gap without distorting the rest of the pad rhythm.
    structural_left = left_adornment_width if left_adornment_width > 0 else accent_w + glyph_left_offset

    # Cursor starts after the structural edge. Most paradigms use pad for the
    # whole walk. Centered-text paradigms can opt into visual_gap so rendered
    # ink edges, not advance boxes, define the repeated rhythm.
    visual_gap_active = visual_gap > 0 and text_anchor == "middle" and seam_render_w <= 0
    resolved_visual_gap = visual_gap if visual_gap_active else 0.0
    first_gap = left_adornment_gap if left_adornment_width > 0 else pad
    if visual_gap_active:
        first_gap = resolved_visual_gap
    cursor = float(structural_left + first_gap)

    # Glyph zone (skip if absent — collapse entirely, no phantom gap).
    glyph_visible_w = glyph_visual_w if glyph_visual_w > 0 else float(glyph_size)
    if has_glyph:
        glyph_x = cursor + (glyph_visible_w - glyph_size) / 2.0 if visual_gap_active else cursor
        # Align the glyph box to the content reading line (computed once above):
        # glyph center == content_reading_center, so glyph_y = center - size/2.
        glyph_y = round(content_reading_center - glyph_size / 2, 1)
        next_gap = resolved_visual_gap if visual_gap_active else (glyph_label_gap if glyph_label_gap > 0 else pad)
        if visual_gap_active:
            cursor += glyph_visible_w + next_gap
        else:
            cursor = glyph_x + glyph_size + next_gap
    else:
        glyph_x = 0.0
        glyph_y = 0.0

    # Label zone: cursor at first char.
    if visual_gap_active:
        label_ink_left = cursor
        label_first_x = label_ink_left - label_start_bearing
        label_x = round(label_first_x + label_w / 2, 1)
        label_visual_right = label_ink_left + label_ink_w
    else:
        label_first_x = cursor
        label_x = round(label_first_x, 1) if text_anchor == "start" else round(label_first_x + label_w / 2, 1)
        label_visual_right = label_first_x + label_w - label_end_bearing
    # Algorithmic bearing correction: subtract the font's trailing
    # side-bearing from the cursor advance so the seam (placed at
    # cursor + pad/2) sits at ``visible_ink_end + pad/2`` instead of
    # ``advance_end + pad/2``. Closes the label-to-seam gap uniformly across
    # all chrome badges including the 28-char BUILD-PASSING-WITH-WARNINGS
    # case. Centered paradigms (text_anchor=middle) pass 0.0 because their
    # text balances bearing across both edges; only text_anchor=start
    # accumulates the bearing on the right side.
    cursor = label_visual_right

    # Panel separator: two orthogonal modes (etched seam OR structural separator).
    seam_left_x = 0.0
    seam_specular_x = 0.0
    seam_right_x = 0.0
    if seam_render_w > 0:
        # Chrome etched seam: half-gaps on each side, two-hairline rendering.
        cursor += pad / 2.0
        seam_left_x = cursor
        seam_specular_x = cursor + seam_specular_offset
        seam_right_x = seam_left_x + seam_render_w
        cursor += seam_render_w + pad / 2.0
        # Synthetic left_panel / right_panel boundary for template backward-compat.
        seam_center_x = seam_left_x + seam_render_w / 2.0
        seam_x = round(seam_center_x, 1)
        left_panel_w = round(seam_center_x)
        right_panel_x = round(seam_center_x + seam_render_w / 2.0)
    else:
        # Brutalist/cellular: structural separator (sep_w stroke + seam_w mark).
        # Full pad after label, then sep+seam, then full pad before value.
        cursor += resolved_visual_gap if visual_gap_active else pad
        left_panel_w = max(round(cursor), label_w_floor)
        seam_x = left_panel_w + sep_w / 2.0
        right_panel_x = left_panel_w + sep_w + seam_w
        seam_right_x = float(right_panel_x)
        cursor = float(right_panel_x + (resolved_visual_gap if visual_gap_active else pad))

    # Value zone: cursor at first char.
    if visual_gap_active:
        value_ink_left = cursor
        value_first_x = value_ink_left - value_start_bearing
        value_x = round(value_first_x + value_w / 2, 1)
        value_visual_right = value_ink_left + value_ink_w
    else:
        value_first_x = cursor
        value_x = round(value_first_x, 1) if text_anchor == "start" else round(value_first_x + value_w / 2, 1)
        value_visual_right = value_first_x + value_w - value_end_bearing
    # v0.3.9 algorithmic bearing correction (mirror of label): subtract
    # value-text trailing bearing before the trailing pad so the right edge
    # sits at ``visible_ink_end + pad`` instead of ``advance_end + pad``.
    cursor = value_visual_right + (resolved_visual_gap if visual_gap_active else pad)

    # Optional state-indicator zone. Every gap including the final one
    # (last content zone → right edge) is ``pad``. The cursor walk advances
    # by ``content + pad`` for each PRESENT zone, and the final pad added
    # after the last zone is the right-edge gap itself.
    if has_state_indicator:
        indicator_x = cursor  # cursor sits at start of state-indicator slot (pad already added after value)
        cursor = indicator_x + indicator_size + (resolved_visual_gap if visual_gap_active else pad)
    else:
        indicator_x = 0.0

    # Total width includes any paradigm-specific right-canvas inset (cellular: 2px
    # structural slab inset — adds on top of the right-edge pad gap).
    # v0.3.9 algorithmic: bearing correction is applied per-text in the cursor
    # walk above, NOT as a final-cursor trim. This produces a uniform
    # ``pad/2`` seam gap and uniform ``pad`` right-edge gap for ALL chrome
    # badges — including the 28-char BUILD-PASSING-WITH-WARNINGS case that
    # the prior flat-3px final-trim approach left visually broken (seam gap
    # was unchanged because trim affected total_w only).
    total_w = max(round(cursor + right_canvas_inset), min_total_w)
    right_panel_w = total_w - right_panel_x

    # Indicator vertical center: the content reading line (== the identity glyph's
    # center), the SINGLE source every shape anchors to. Square top-left derives
    # ``center - size/2``; circle/diamond consume ``indicator_center_y`` directly
    # (resolver reads it off zones). Anchoring to the reading line — not height/2 —
    # keeps the status glyph on the SAME line as the brand glyph and the value
    # text on every paradigm. (Geometric center drifts off this line wherever a
    # paradigm's content line isn't the badge midline, e.g. chrome's ≈10.5.)
    if has_state_indicator:
        indicator_center_y = round(content_reading_center, 1)
        indicator_y = round(content_reading_center - indicator_size / 2, 1)
        inner_bit_w = round(indicator_size * inner_bit_ratio)
        inner_bit_offset = (indicator_size - inner_bit_w) / 2
    else:
        indicator_center_y = 0.0
        indicator_y = 0.0
        inner_bit_w = 0
        inner_bit_offset = 0.0

    # Backward-compat value zone bounds (assertion tests + templates that
    # still reference these). Chrome: starts at synthetic right_panel_x (the
    # etched-seam half-gap already accounted for spacing). Brutalist/cellular:
    # right_panel_x + pad (full pad gutter after the structural separator).
    value_zone_left = (
        float(right_panel_x)
        if seam_render_w > 0
        else float(right_panel_x + (resolved_visual_gap if visual_gap_active else pad))
    )
    # Trailing pad is part of the right-edge gap. When
    # state indicator is present, value zone ends one pad before it. When
    # absent, value zone ends one pad before the right edge (= total_w -
    # right_canvas_inset - pad).
    trailing_gap = resolved_visual_gap if visual_gap_active else pad
    value_zone_right = (
        float(indicator_x - trailing_gap) if has_state_indicator else float(total_w - right_canvas_inset - trailing_gap)
    )
    value_zone_width = value_zone_right - value_zone_left

    return BadgeZones(
        width=total_w,
        height=height,
        glyph_x=glyph_x,
        glyph_y=glyph_y,
        glyph_size=glyph_size if has_glyph else 0,
        label_x=label_x,
        label_w=label_w,
        label_text_length=label_text_length,
        seam_x=seam_x,
        seam_right_x=round(seam_right_x, 1),
        value_x=value_x,
        value_w=value_w,
        value_text_length=value_text_length,
        indicator_x=indicator_x,
        indicator_y=indicator_y,
        indicator_center_y=indicator_center_y,
        indicator_size=indicator_size if has_state_indicator else 0,
        left_panel_w=left_panel_w,
        right_panel_x=right_panel_x,
        right_panel_w=right_panel_w,
        text_y=text_y,
        show_indicator=has_state_indicator,
        inner_bit_w=inner_bit_w,
        inner_bit_offset=inner_bit_offset,
        value_zone_left=value_zone_left,
        value_zone_right=value_zone_right,
        value_zone_width=value_zone_width,
        seam_left_x=round(seam_left_x, 1) if seam_render_w > 0 else 0.0,
        seam_specular_x=round(seam_specular_x, 1) if seam_render_w > 0 else 0.0,
        text_anchor=text_anchor,
    )


# ─────────────────────────────────────────────────────────────────────
# Strip zone layout (v0.3.9)
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StripCoreZones:
    """Resolved strip-wide geometry shared by every paradigm."""

    width: int
    height: int
    content_width: int
    glyph_zone_width: int
    glyph_zone_x_offset: float
    icon_box_x: float
    icon_box_y: float
    glyph_cx: float
    glyph_cy: float
    glyph_size: int
    glyph_svg_x: float
    glyph_svg_y: float
    identity_x: float
    identity_text_length: float
    identity_zone_width: float
    subtitle_text: str
    first_divider_x: int
    cell_widths: list[int]
    cell_layouts_records: list[dict[str, object]]
    seam_positions: list[float]
    status_x: float
    status_zone_width: int
    content_right: int
    bookend_x: int
    metric_pitch: int
    metrics_zone_width: int
    perimeter_w: float
    perimeter_h: float
    half_h: float
    metric_rule_y1: float
    metric_rule_y2: float
    brand_panel_x: int
    brand_panel_w: int
    triple_divider_x: int
    triple_divider_void_x: int
    triple_divider_right_x: int
    brand_divider_x: int


@dataclass(frozen=True, slots=True)
class StripChromeGeometry:
    """Chrome strip material geometry."""

    inner_w: int
    inner_h: int
    well_w: int
    well_h: int
    accent_h: int
    highlight_w: int


@dataclass(frozen=True, slots=True)
class StripCellularGeometry:
    """Cellular strip flank and panel geometry."""

    left_flank_cells: list[dict[str, object]]
    right_flank_cells: list[dict[str, object]]
    panel_x: int
    panel_w: int
    panel_h: int
    pattern_opacity: float


@dataclass(frozen=True, slots=True)
class StripStatusGeometry:
    """Status indicator geometry for all strip paradigms."""

    outer_x: float
    outer_y: float
    inner_x: float
    inner_y: float
    inner_w: float
    inner_h: float
    cellular_inner_x: float
    cellular_inner_y: float
    cellular_inner_w: float
    cellular_inner_h: float
    chrome_outer_x: float
    chrome_outer_y: float
    chrome_outer_size: float
    chrome_outer_rx: float
    chrome_inner_x: float
    chrome_inner_y: float
    chrome_inner_size: float
    chrome_inner_rx: float


@dataclass(frozen=True, slots=True)
class StripBookendGeometry:
    """Bookend and brand-glyph ornament geometry."""

    identity_glyph_x: float
    identity_glyph_y: float
    ornament_inner_x: int
    ornament_inner_y: int
    ornament_inner_w: int
    ornament_inner_h: int
    outer_x: float
    outer_y: float
    inner_x: float
    inner_y: float
    inner_w: int
    inner_h: int


@dataclass(frozen=True, slots=True)
class StripZones:
    """Resolved zone layout for a strip frame, grouped by responsibility."""

    core: StripCoreZones
    chrome: StripChromeGeometry
    cellular: StripCellularGeometry
    status: StripStatusGeometry
    bookend: StripBookendGeometry

    @property
    def width(self) -> int:
        return self.core.width

    @property
    def height(self) -> int:
        return self.core.height

    @property
    def content_width(self) -> int:
        return self.core.content_width

    @property
    def glyph_zone_width(self) -> int:
        return self.core.glyph_zone_width

    @property
    def glyph_zone_x_offset(self) -> float:
        return self.core.glyph_zone_x_offset

    @property
    def icon_box_x(self) -> float:
        return self.core.icon_box_x

    @property
    def icon_box_y(self) -> float:
        return self.core.icon_box_y

    @property
    def glyph_cx(self) -> float:
        return self.core.glyph_cx

    @property
    def glyph_cy(self) -> float:
        return self.core.glyph_cy

    @property
    def glyph_size(self) -> int:
        return self.core.glyph_size

    @property
    def glyph_svg_x(self) -> float:
        return self.core.glyph_svg_x

    @property
    def glyph_svg_y(self) -> float:
        return self.core.glyph_svg_y

    @property
    def identity_x(self) -> float:
        return self.core.identity_x

    @property
    def identity_text_length(self) -> float:
        return self.core.identity_text_length

    @property
    def identity_zone_width(self) -> float:
        return self.core.identity_zone_width

    @property
    def subtitle_text(self) -> str:
        return self.core.subtitle_text

    @property
    def first_divider_x(self) -> int:
        return self.core.first_divider_x

    @property
    def cell_widths(self) -> list[int]:
        return self.core.cell_widths

    @property
    def cell_layouts_records(self) -> list[dict[str, object]]:
        return self.core.cell_layouts_records

    @property
    def seam_positions(self) -> list[float]:
        return self.core.seam_positions

    @property
    def status_x(self) -> float:
        return self.core.status_x

    @property
    def status_zone_width(self) -> int:
        return self.core.status_zone_width

    @property
    def content_right(self) -> int:
        return self.core.content_right

    @property
    def bookend_x(self) -> int:
        return self.core.bookend_x

    @property
    def metric_pitch(self) -> int:
        return self.core.metric_pitch

    @property
    def metrics_zone_width(self) -> int:
        return self.core.metrics_zone_width

    @property
    def perimeter_w(self) -> float:
        return self.core.perimeter_w

    @property
    def perimeter_h(self) -> float:
        return self.core.perimeter_h

    @property
    def half_h(self) -> float:
        return self.core.half_h

    @property
    def metric_rule_y1(self) -> float:
        return self.core.metric_rule_y1

    @property
    def metric_rule_y2(self) -> float:
        return self.core.metric_rule_y2

    @property
    def brand_panel_x(self) -> int:
        return self.core.brand_panel_x

    @property
    def brand_panel_w(self) -> int:
        return self.core.brand_panel_w

    @property
    def triple_divider_x(self) -> int:
        return self.core.triple_divider_x

    @property
    def triple_divider_void_x(self) -> int:
        return self.core.triple_divider_void_x

    @property
    def triple_divider_right_x(self) -> int:
        return self.core.triple_divider_right_x

    @property
    def brand_divider_x(self) -> int:
        return self.core.brand_divider_x

    @property
    def chrome_inner_w(self) -> int:
        return self.chrome.inner_w

    @property
    def chrome_inner_h(self) -> int:
        return self.chrome.inner_h

    @property
    def chrome_well_w(self) -> int:
        return self.chrome.well_w

    @property
    def chrome_well_h(self) -> int:
        return self.chrome.well_h

    @property
    def chrome_accent_h(self) -> int:
        return self.chrome.accent_h

    @property
    def chrome_highlight_w(self) -> int:
        return self.chrome.highlight_w

    @property
    def cellular_left_flank_cells(self) -> list[dict[str, object]]:
        return self.cellular.left_flank_cells

    @property
    def cellular_right_flank_cells(self) -> list[dict[str, object]]:
        return self.cellular.right_flank_cells

    @property
    def cellular_panel_x(self) -> int:
        return self.cellular.panel_x

    @property
    def cellular_panel_w(self) -> int:
        return self.cellular.panel_w

    @property
    def cellular_panel_h(self) -> int:
        return self.cellular.panel_h

    @property
    def cellular_pattern_opacity(self) -> float:
        return self.cellular.pattern_opacity

    @property
    def status_outer_x(self) -> float:
        return self.status.outer_x

    @property
    def status_outer_y(self) -> float:
        return self.status.outer_y

    @property
    def status_inner_x(self) -> float:
        return self.status.inner_x

    @property
    def status_inner_y(self) -> float:
        return self.status.inner_y

    @property
    def status_inner_w(self) -> float:
        return self.status.inner_w

    @property
    def status_inner_h(self) -> float:
        return self.status.inner_h

    @property
    def status_cellular_inner_x(self) -> float:
        return self.status.cellular_inner_x

    @property
    def status_cellular_inner_y(self) -> float:
        return self.status.cellular_inner_y

    @property
    def status_cellular_inner_w(self) -> float:
        return self.status.cellular_inner_w

    @property
    def status_cellular_inner_h(self) -> float:
        return self.status.cellular_inner_h

    @property
    def status_chrome_outer_x(self) -> float:
        return self.status.chrome_outer_x

    @property
    def status_chrome_outer_y(self) -> float:
        return self.status.chrome_outer_y

    @property
    def status_chrome_outer_size(self) -> float:
        return self.status.chrome_outer_size

    @property
    def status_chrome_outer_rx(self) -> float:
        return self.status.chrome_outer_rx

    @property
    def status_chrome_inner_x(self) -> float:
        return self.status.chrome_inner_x

    @property
    def status_chrome_inner_y(self) -> float:
        return self.status.chrome_inner_y

    @property
    def status_chrome_inner_size(self) -> float:
        return self.status.chrome_inner_size

    @property
    def status_chrome_inner_rx(self) -> float:
        return self.status.chrome_inner_rx

    @property
    def identity_glyph_x(self) -> float:
        return self.bookend.identity_glyph_x

    @property
    def identity_glyph_y(self) -> float:
        return self.bookend.identity_glyph_y

    @property
    def ornament_inner_x(self) -> int:
        return self.bookend.ornament_inner_x

    @property
    def ornament_inner_y(self) -> int:
        return self.bookend.ornament_inner_y

    @property
    def ornament_inner_w(self) -> int:
        return self.bookend.ornament_inner_w

    @property
    def ornament_inner_h(self) -> int:
        return self.bookend.ornament_inner_h

    @property
    def bookend_outer_x(self) -> float:
        return self.bookend.outer_x

    @property
    def bookend_outer_y(self) -> float:
        return self.bookend.outer_y

    @property
    def bookend_inner_x(self) -> float:
        return self.bookend.inner_x

    @property
    def bookend_inner_y(self) -> float:
        return self.bookend.inner_y

    @property
    def bookend_inner_w(self) -> int:
        return self.bookend.inner_w

    @property
    def bookend_inner_h(self) -> int:
        return self.bookend.inner_h


def compute_strip_zones(
    *,
    height: int,
    # Paradigm-resolved structural inputs (owns_strip flag drives major branch).
    owns_strip: bool,
    # Adaptive-paradigm fields (used when owns_strip=False).
    accent_w: int,
    show_icon_box: bool,
    icon_box_size: int,
    icon_box_pad: int,
    has_identity_glyph: bool,
    strip_glyph_size: int = 18,
    # Owns_strip fields (used when owns_strip=True).
    brand_panel_x: int = 0,
    brand_panel_width: int = 0,
    identity_text_x: int = 0,
    brand_divider_x: int = 0,
    triple_divider_bar_width: int = 3,
    triple_divider_void_width: int = 2,
    bookend_x_fallback: int = 0,
    ornament_x: int = 0,
    ornament_y: int = 0,
    ornament_size: int = 14,
    ornament_inner_inset: int = 3,
    bookend_gap: int = 16,
    bookend_pad_right: int = 40,
    identity_panel_pad: int = 8,
    # Identity zone measurement (paradigm-agnostic).
    identity_w: float = 0,
    subtitle_w: float = 0,
    subtitle_text: str = "",
    # Per-cell layouts (pre-computed via compute_cell_layout).
    cell_widths: list[int] | None = None,
    cell_layouts_records: list[dict] | None = None,  # type: ignore[type-arg]
    metric_pitch_fallback: int = 0,
    # Status indicator zone.
    has_status_indicator: bool = False,
    status_indicator_size: int = 14,
    status_indicator_pre_gap: int = 16,
    status_indicator_post_gap: int = 4,
    # Bifamily flank widths (automata strips).
    flank_width: int = 0,
    flank_cell_size: int = 12,
    # Strip-min-width clamp (chrome's 320).
    strip_min_width: int = 0,
    # Identity-zone right padding (adaptive paradigms — gap after identity content).
    identity_right_pad: int = 14,
    # Minimum first_divider_x floor (legacy invariant).
    first_divider_x_floor: int = 80,
    # Cell start offset past first_divider_x (legacy non-zero in older releases).
    cell_offset: int = 0,
) -> StripZones:
    """Compute strip zone layout for both adaptive and owns_strip paradigms.

    Two-branch dispatch on ``owns_strip``:

    * **owns_strip=False** (chrome / cellular / default): identity zone is
      content-driven; ``first_divider_x = identity_x + identity_zone_w +
      identity_right_pad`` (floored at ``first_divider_x_floor``). Cells march
      from first_divider_x. Bookend not used.

    * **owns_strip=True** (brutalist): identity sits inside a fixed
      ``brand_panel_width`` zone. If ``identity_w > brand_panel_width -
      2 * identity_panel_pad``, ``identity_text_length`` is populated so the
      template emits ``textLength`` + ``lengthAdjust="spacingAndGlyphs"`` on
      the identity ``<text>`` element. Cells start at ``brand_divider_x``.
      Bookend snaps to right edge of last cell + ``bookend_gap``; total width
      = bookend_x + bookend_pad_right.

    Min-width clamp
    ---------------
    When ``strip_min_width > 0`` and the computed width is below the floor,
    width clamps to ``strip_min_width``. Adaptive paradigms apply this clamp;
    owns_strip ignores it (brutalist brand-panel grammar has its own minimum
    via brand_panel_width + cells + bookend_pad).
    """
    cell_widths = list(cell_widths or [])
    cell_layouts_records = list(cell_layouts_records or [])

    # Bifamily flank handling: every coordinate downstream of identity shifts
    # right by flank_width when flanks render (automata strips reserve 36px
    # of pattern cells on each side).
    has_flanks = flank_width > 0
    seam_offset = flank_width if has_flanks else 0
    flank_total = 2 * flank_width if has_flanks else 0

    # ── Identity / glyph zone width ──
    # Adaptive paradigms: icon_box wraps glyph; bare glyph reserves left
    # padding + rendered glyph + post-glyph gap; no glyph collapses entirely.
    # Coordinates emitted here are already shifted past any bifamily left
    # flank so templates can render them verbatim.
    # Owns_strip: identity glyph is part of the brand-panel grammar; we don't
    # reserve a separate zone — the partial draws the ornament at its own
    # paradigm-defined coordinates.
    icon_box_x = 0.0
    icon_box_y = 0.0
    glyph_cx = 0.0
    glyph_cy = 0.0
    glyph_size_resolved = 0
    if owns_strip:
        glyph_zone_width = 0
    elif show_icon_box and has_identity_glyph:
        glyph_zone_width = icon_box_pad + icon_box_size + 8
        icon_box_x = float(seam_offset + accent_w + icon_box_pad)
        icon_box_y = float((height - icon_box_size) // 2)
        glyph_size_resolved = max(1, icon_box_size - 10)
        glyph_cx = icon_box_x + icon_box_size / 2.0
        glyph_cy = icon_box_y + icon_box_size / 2.0
    elif show_icon_box:
        glyph_zone_width = icon_box_pad
    elif has_identity_glyph:
        glyph_size_resolved = max(1, strip_glyph_size)
        glyph_zone_width = 12 + glyph_size_resolved + 9
        glyph_cx = seam_offset + accent_w + 12 + glyph_size_resolved / 2.0
        glyph_cy = height / 2.0
    else:
        glyph_zone_width = 0

    # ── Identity x + zone width + shrink-to-fit ──
    identity_text_length = 0.0
    # Owns_strip-only outputs (populated below for brutalist; 0 for adaptive).
    brand_panel_x_resolved = 0
    brand_panel_w_resolved = 0
    triple_divider_x_resolved = 0
    brand_divider_x_resolved = 0
    identity_x_for_template = 0.0
    if owns_strip:
        # Content-driven brand panel sizing. brand_panel_width
        # is a MAX ceiling — the panel shrinks to content when identity is short
        # (N8N, 3 chars), and shrink-to-fit triggers via textLength when content
        # would overflow the ceiling (SIGNIFICANT-GRAVITAS/AUTOGPT, 28 chars).
        # All downstream geometry (triple_divider_x, brand_divider_x, bookend_x)
        # follows the resolved panel right edge so cells march compactly.
        identity_x_resolved = identity_text_x
        identity_x_for_template = float(identity_x_resolved)
        identity_left_inset = identity_text_x - brand_panel_x  # gap inside panel before text
        triple_divider_total_w = 2 * triple_divider_bar_width + triple_divider_void_width
        # Minimum panel width: text starts at identity_text_x, needs at least
        # identity_panel_pad to right edge for any content. min_w guards against
        # collapsing the panel entirely on zero-content edge cases.
        min_panel_w = identity_left_inset + identity_panel_pad
        # Required panel width to fit measured content with right pad. Ceiling
        # so a measured width of 23.4 lands at integer 24 — without it, panel
        # truncation would clip content by < 1px.
        required_panel_w = math.ceil(identity_left_inset + identity_w + identity_panel_pad)
        # v0.3.13 content-aware retune: the panel GROWS to fit the measured
        # identity (no ceiling), so long identities no longer squish. A
        # ``brand_panel_width > 0`` re-enables an optional ceiling; brutalist
        # sets it to 0 (unbounded).
        effective_panel_w = max(min_panel_w, required_panel_w)
        if brand_panel_width > 0:
            effective_panel_w = min(effective_panel_w, brand_panel_width)
        effective_panel_right = brand_panel_x + effective_panel_w
        # textLength = the natural measured width. A no-op when the embedded
        # font loads (the text is already that wide); a font-independent BOUND
        # when it can't — GitHub camo's CSP blocks @font-face, so the wider
        # fallback would otherwise bleed past the seam. If an explicit ceiling
        # squeezes the panel below the content, clamp to the available width.
        available_text_w = effective_panel_right - identity_text_x - identity_panel_pad
        identity_text_length = round(
            float(min(identity_w, available_text_w)) if available_text_w > 0 else float(identity_w), 1
        )
        # Downstream geometry follows the resolved panel right edge.
        brand_panel_x_resolved = brand_panel_x
        brand_panel_w_resolved = effective_panel_w
        triple_divider_x_resolved = effective_panel_right
        brand_divider_x_resolved = triple_divider_x_resolved + triple_divider_total_w
        identity_zone_width = float(effective_panel_w)
        first_divider_x = brand_divider_x_resolved
    else:
        # Adaptive: identity sits after the resolved glyph zone. Bare-glyph
        # zones already include the post-glyph gap; glyphless bare strips use
        # the legacy 14px identity inset after the accent rail.
        identity_x_resolved = accent_w + glyph_zone_width if show_icon_box or has_identity_glyph else accent_w + 14
        identity_x_for_template = identity_x_resolved + seam_offset
        identity_zone_width = max(identity_w, subtitle_w)
        # v0.3.13 camo bound: emit the identity's natural measured width as
        # textLength so chrome/cellular strips match brutalist's overflow guard.
        # A no-op when the embedded font loads; a hard bound when GitHub camo's
        # CSP blocks @font-face and the wider fallback would otherwise bleed.
        identity_text_length = round(float(identity_w), 1)
        first_divider_x = max(
            int(identity_x_resolved + identity_zone_width + identity_right_pad),
            first_divider_x_floor,
        )

    # ── Per-cell positions + seam cumulator ──
    # First seam at first_divider_x + seam_offset (shifted by flank when present).
    # Then one seam per cell trailing edge, cumulative widths.
    metric_pitch = max(cell_widths) if cell_widths else max(metric_pitch_fallback, 0)
    # Empty strips (no metrics) reserve NO metric zone — they collapse to a
    # minimal identity-only strip: no phantom 1-cell width, no metric-separator
    # divider, no trailing dead space, no min-width clamp (v0.3.13 coherent
    # empty-state — every genome ends right after the identity).
    is_empty_strip = not cell_widths
    metrics_zone_width = sum(cell_widths) if cell_widths else 0

    seams: list[float] = [float(first_divider_x + seam_offset)]
    cell_start = first_divider_x + cell_offset + seam_offset
    running = 0
    for cw in cell_widths:
        running += cw
        seams.append(float(cell_start + running))
    if not cell_widths:
        # Pad seam list for zero-metric strips (preserves legacy single-divider behavior).
        seams.append(float(cell_start + metric_pitch))

    # ── Status indicator zone ──
    if has_status_indicator:
        status_zone_width = status_indicator_pre_gap + status_indicator_size + status_indicator_post_gap
    else:
        status_zone_width = 0

    # ── Total width (additive layout) ──
    # A STATELESS strip has no status terminus, so the trailing space past the
    # last cell collapses to a thin stroke clearance. The cell's own internal
    # pad already supplies the right margin; adding a full strip_pad / bookend_gap
    # of trailing would seat the last value lopsided — more space on its right
    # than its left (v0.3.13 fix). One value, every genome.
    stateless_trailing = 2
    if owns_strip:
        # Dynamic bookend snaps to right edge of last cell + bookend_gap;
        # fallback to YAML constant for zero-cell strips. Uses the content-
        # driven brand_divider_x_resolved so short identities → tight strips
        # (N8N: bookend at ~120 not 520) and long identities → standard layout
        # (AUTOGPT: bookend follows the clamped 170 baseline).
        last_cell_right = brand_divider_x_resolved + sum(cell_widths)
        if is_empty_strip:
            # Empty: identity panel only — end at the panel right edge + a thin
            # clearance. No triple divider / metric zone / bookend (template
            # gates the divider on metrics). Replaces the bookend_x_fallback
            # constant that elongated empty brutalist strips to ~543px.
            bookend_x = triple_divider_x_resolved
            width = triple_divider_x_resolved + stateless_trailing
        elif has_status_indicator:
            # Stateful: reserve the bookend zone for the status diamond.
            bookend_x = last_cell_right + bookend_gap
            width = bookend_x + bookend_pad_right
        else:
            # Stateless: end at the last cell + stroke clearance (no decorative
            # ornament), so the last value's right margin mirrors its left.
            bookend_x = last_cell_right
            width = last_cell_right + stateless_trailing
    else:
        # Adaptive layout: identity + cells + status + flanks. The trailing
        # clearance sits outside content_width as transparent SVG canvas (not
        # visible dead space inside the envelope). Chrome keeps a hair of it so
        # the strip_min_width clamp still has room to grow; cellular (strip_min_
        # width 0) gets none — its bifamily flanks frame the right edge.
        natural_content_width = first_divider_x + cell_offset + metrics_zone_width + status_zone_width + flank_total
        # Empty strips: no trailing clearance and (below) no strip_min_width
        # clamp — that guards 1-metric aspect-warp, not the identity-only state.
        adaptive_trailing_pad = (
            stateless_trailing if (strip_min_width > 0 and not has_status_indicator and not is_empty_strip) else 0
        )
        width = natural_content_width + adaptive_trailing_pad
        bookend_x = 0

    # content_width tracks where strip content visually ends. The adaptive
    # trailing pad sits outside content_width so chrome envelope/well/rim snap
    # to the last cell with no visible dead space inside the envelope. Strip-
    # min-width clamp extends SVG viewBox only; content remains at content_width.
    # owns_strip paradigms (brutalist) render their own bookend ornament —
    # content_width matches width. Adaptive paradigms separate content from
    # trailing transparent canvas via natural_content_width.
    content_width = width if owns_strip else natural_content_width
    if strip_min_width > 0 and width < strip_min_width and not is_empty_strip:
        width = strip_min_width

    # Status indicator x. owns_strip (brutalist) renders the diamond off its own
    # bookend_x, so status_x is dead there — keep the legacy seam+pre_gap value.
    # Adaptive paradigms (chrome / cellular) render off status_x: CENTER the
    # indicator between the last cell's content-right edge and the trailing
    # content edge, so its leading gap (from the last metric) mirrors its
    # trailing gap (to the envelope edge / right flank). The pre-v0.3.13 formula
    # placed it at last_seam + pre_gap, but the last cell's own right gutter
    # (cell_pad/2) already sits between the value and the seam — so a constant
    # pre_gap stacked on a wide gutter seated the diamond closer to the edge than
    # to the value (chrome's 48px gutter: 40px lead vs 18px trail). Centering on
    # the content-right edge (derived from cell_w - content_w) cancels the gutter
    # uniformly: negligible for automata's 20px gutter, decisive for chrome's 48.
    # One code path, every adaptive genome — both adaptive status partials center
    # their indicator on the group origin (chrome diamond and cellular frame are
    # both anchored at status.outer_x), so status_x IS the center, no offset.
    if not has_status_indicator:
        status_x = 0.0
    elif owns_strip:
        last_seam_x = seams[-1] if seams else float(first_divider_x)
        status_x = last_seam_x + status_indicator_pre_gap
    else:
        last_pad = (
            float(cell_layouts_records[-1]["cell_w"]) - float(cell_layouts_records[-1]["content_w"])
            if cell_layouts_records
            else 0.0
        )
        last_content_right = (seams[-1] if seams else float(first_divider_x)) - last_pad / 2.0
        trailing_edge = content_width - (flank_width if has_flanks else 0)
        status_x = (last_content_right + trailing_edge) / 2.0

    # Content right edge (= width minus flank on right side, when flanked).
    content_right = width - (flank_width if has_flanks else 0)

    # Glyph zone x-offset: when bifamily flanks present, glyph must be pushed
    # past the left flank so it doesn't overlap pattern cells.
    glyph_zone_x_offset = float(flank_width if has_flanks else 0)

    # First divider x shifted into flank-aware coordinate frame (matches what
    # templates consume — identity, dividers, cells all in the same frame).
    first_divider_x_shifted = first_divider_x + seam_offset

    # Attach absolute cell origins and trailing seams directly to each record.
    # Templates can render cell groups from these named fields without a local
    # running namespace.
    def _pixel_number(value: float) -> int | float:
        return int(value) if value.is_integer() else round(value, 1)

    resolved_cell_layouts = []
    for index, record in enumerate(cell_layouts_records):
        resolved = dict(record)
        cell_x_value = seams[index] if index < len(seams) else float(cell_start)
        trailing_x_value = seams[index + 1] if index + 1 < len(seams) else float(cell_x_value + resolved["cell_w"])
        resolved["cell_x"] = _pixel_number(cell_x_value)
        resolved["trailing_x"] = _pixel_number(trailing_x_value)
        resolved["show_leading_rule"] = index > 0
        resolved_cell_layouts.append(resolved)

    # Secondary geometry derived from the primary zone outputs. These values
    # used to be recomputed piecemeal in strip templates.
    perimeter_w = width - 1
    perimeter_h = height - 1
    half_h = height // 2
    glyph_svg_x = -(glyph_size_resolved / 2.0) if has_identity_glyph else 0.0
    glyph_svg_y = glyph_svg_x
    triple_divider_void_x = triple_divider_x_resolved + triple_divider_bar_width
    triple_divider_right_x = triple_divider_void_x + triple_divider_void_width
    ornament_inner_w = max(0, ornament_size - 2 * ornament_inner_inset)
    ornament_inner_h = ornament_inner_w
    identity_glyph_x = ornament_x + (ornament_size - strip_glyph_size) / 2.0 if owns_strip else 0.0
    identity_glyph_y = ornament_y + (ornament_size - strip_glyph_size) / 2.0 if owns_strip else 0.0
    bookend_outer_x = -(ornament_size / 2.0)
    bookend_outer_y = bookend_outer_x
    bookend_inner_x = bookend_outer_x + ornament_inner_inset
    bookend_inner_y = bookend_outer_y + ornament_inner_inset
    bookend_inner_w = ornament_inner_w
    bookend_inner_h = ornament_inner_h
    metric_rule_y1 = 2.0
    metric_rule_y2 = float(height - 2)
    chrome_inner_w = max(0, content_width - 2)
    chrome_inner_h = max(0, height - 2)
    chrome_well_w = max(0, content_width - 4)
    chrome_well_h = max(0, height - 4)
    chrome_accent_h = chrome_well_h
    chrome_highlight_w = max(0, content_width - 16)
    cellular_panel_x = flank_width if has_flanks else 0
    cellular_panel_w = width - (2 * flank_width) if has_flanks else width
    cellular_panel_h = max(0, height - 4)

    cellular_left_flank_cells: list[dict] = []  # type: ignore[type-arg]
    cellular_right_flank_cells: list[dict] = []  # type: ignore[type-arg]
    if has_flanks and flank_cell_size > 0:
        n_rows = height // flank_cell_size
        n_cols = flank_width // flank_cell_size
        left_classes = ("cz1", "cz2", "cz3", "cz4", "czf")
        right_classes = ("cz2", "cz3", "cz4", "cz1", "czf")
        right_flank_x = width - flank_width
        for col in range(n_cols):
            for row in range(n_rows):
                color_idx = (col + row * 2) % 3
                class_idx = (col * 3 + row) % 5
                cellular_left_flank_cells.append(
                    {
                        "x": col * flank_cell_size,
                        "y": row * flank_cell_size,
                        "size": flank_cell_size,
                        "color_idx": color_idx,
                        "class_name": left_classes[class_idx],
                    }
                )
                cellular_right_flank_cells.append(
                    {
                        "x": right_flank_x + col * flank_cell_size,
                        "y": row * flank_cell_size,
                        "size": flank_cell_size,
                        "color_idx": color_idx,
                        "class_name": right_classes[class_idx],
                    }
                )

    status_outer_x = -(status_indicator_size / 2.0)
    status_outer_y = status_outer_x
    status_inner_size = max(0.0, status_indicator_size - 6.0)
    status_inner_x = status_outer_x + 3.0
    status_inner_y = status_inner_x

    return StripZones(
        core=StripCoreZones(
            width=width,
            height=height,
            content_width=content_width,
            glyph_zone_width=glyph_zone_width,
            glyph_zone_x_offset=glyph_zone_x_offset,
            icon_box_x=round(icon_box_x, 1),
            icon_box_y=round(icon_box_y, 1),
            glyph_cx=round(glyph_cx, 1),
            glyph_cy=round(glyph_cy, 1),
            glyph_size=glyph_size_resolved if has_identity_glyph else 0,
            glyph_svg_x=round(glyph_svg_x, 1),
            glyph_svg_y=round(glyph_svg_y, 1),
            identity_x=identity_x_for_template,
            identity_text_length=identity_text_length,
            identity_zone_width=identity_zone_width,
            subtitle_text=subtitle_text,
            first_divider_x=first_divider_x_shifted,
            cell_widths=cell_widths,
            cell_layouts_records=resolved_cell_layouts,
            seam_positions=seams,
            status_x=status_x,
            status_zone_width=status_zone_width,
            content_right=content_right,
            bookend_x=bookend_x,
            metric_pitch=metric_pitch,
            metrics_zone_width=metrics_zone_width,
            perimeter_w=perimeter_w,
            perimeter_h=perimeter_h,
            half_h=half_h,
            metric_rule_y1=metric_rule_y1,
            metric_rule_y2=metric_rule_y2,
            brand_panel_x=brand_panel_x_resolved,
            brand_panel_w=brand_panel_w_resolved,
            triple_divider_x=triple_divider_x_resolved,
            triple_divider_void_x=triple_divider_void_x,
            triple_divider_right_x=triple_divider_right_x,
            brand_divider_x=brand_divider_x_resolved,
        ),
        chrome=StripChromeGeometry(
            inner_w=chrome_inner_w,
            inner_h=chrome_inner_h,
            well_w=chrome_well_w,
            well_h=chrome_well_h,
            accent_h=chrome_accent_h,
            highlight_w=chrome_highlight_w,
        ),
        cellular=StripCellularGeometry(
            left_flank_cells=cellular_left_flank_cells,
            right_flank_cells=cellular_right_flank_cells,
            panel_x=cellular_panel_x,
            panel_w=cellular_panel_w,
            panel_h=cellular_panel_h,
            pattern_opacity=0.7,
        ),
        status=StripStatusGeometry(
            outer_x=status_outer_x,
            outer_y=status_outer_y,
            inner_x=status_inner_x,
            inner_y=status_inner_y,
            inner_w=status_inner_size,
            inner_h=status_inner_size,
            cellular_inner_x=status_outer_x + 4.0,
            cellular_inner_y=status_outer_y + 4.0,
            cellular_inner_w=6.0,
            cellular_inner_h=6.0,
            chrome_outer_x=-4.2,
            chrome_outer_y=-4.2,
            chrome_outer_size=8.4,
            chrome_outer_rx=0.7,
            chrome_inner_x=-2.2,
            chrome_inner_y=-2.2,
            chrome_inner_size=4.4,
            chrome_inner_rx=0.3,
        ),
        bookend=StripBookendGeometry(
            identity_glyph_x=identity_glyph_x,
            identity_glyph_y=identity_glyph_y,
            ornament_inner_x=ornament_x + ornament_inner_inset,
            ornament_inner_y=ornament_y + ornament_inner_inset,
            ornament_inner_w=ornament_inner_w,
            ornament_inner_h=ornament_inner_h,
            outer_x=bookend_outer_x,
            outer_y=bookend_outer_y,
            inner_x=bookend_inner_x,
            inner_y=bookend_inner_y,
            inner_w=bookend_inner_w,
            inner_h=bookend_inner_h,
        ),
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
