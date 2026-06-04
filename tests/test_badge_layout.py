"""Unit tests for compose/layout.py — BadgeZones equal-spacing rule.

Badge layout moved from the legacy rhythm_gap/glyph_gap dual-constant system
to `compute_badge_zones` under a single equal-spacing rule:

    Every gap between PRESENT zones equals `pad`. Absent zones (no glyph,
    no state indicator) collapse entirely — no reserved width, no phantom
    gap. The Bug 3 fix (chrome no-glyph long-label badges had ~16px of
    empty space before the label) lives here.

Cases mirror real GitHub/PyPI data so failures map cleanly to user-visible
regressions:

* short percentage ("82%")
* full name ("RECONNAISSANCE")
* version string ("0.2.23")
* license SPDX ("Apache-2.0")
* python_requires (">=3.12")
* stateless STARS-like value ("42") with has_state_indicator=False
* no-glyph long label (the Bug 3 trigger from the v0.3.9 visual review)
"""

from __future__ import annotations

from hyperweave.compose.layout import compute_badge_glyph_size, compute_badge_zones

# Brutalist-paradigm constants reflecting data/paradigms/brutalist.yaml (pad=5).
BRUTALIST_INPUTS = dict(
    height=20,
    pad=5,
    has_glyph=False,
    has_state_indicator=True,
    accent_w=4,
    glyph_size=14,
    glyph_left_offset=0,
    sep_w=2,
    seam_w=3,
    indicator_size=8,
    text_y_factor=0.69,
    value_font_size=11.0,
)

# Cellular-paradigm constants reflecting data/paradigms/cellular.yaml (pad=8).
# sep_w=1 (overrides profile default of 2); right_canvas_inset=2 (inner-canvas
# inset shrinks the effective value slab right edge by 2px). Cellular's left
# adornment geometry starts the first content zone from the rendered bookend
# edge rather than from a reverse-engineered glyph offset.
CELLULAR_INPUTS = dict(
    height=32,
    pad=8,
    has_glyph=False,
    has_state_indicator=True,
    accent_w=4,
    glyph_size=12,
    glyph_left_offset=0,
    left_adornment_width=20,
    left_adornment_gap=4,
    glyph_label_gap=4,
    visual_gap=4,
    sep_w=1,
    seam_w=3,
    indicator_size=8,
    right_canvas_inset=2,
    text_y_factor=0.656,
    value_font_size=12.0,
)

CELLULAR_COMPACT_INPUTS = {
    **CELLULAR_INPUTS,
    "height": 20,
    "glyph_size": 10,
    "left_adornment_width": 14,
    "left_adornment_gap": 4,
}


def _zones(*, label_w: float, value_w: float, has_state_indicator: bool = True):
    inputs = {**BRUTALIST_INPUTS, "has_state_indicator": has_state_indicator}
    return compute_badge_zones(
        measured_label_w=label_w,
        measured_value_w=value_w,
        **inputs,
    )


def _zones_cellular(
    *,
    label_w: float,
    value_w: float,
    has_state_indicator: bool = True,
    compact: bool = False,
):
    inputs = CELLULAR_COMPACT_INPUTS if compact else CELLULAR_INPUTS
    inputs = {**inputs, "has_state_indicator": has_state_indicator}
    return compute_badge_zones(
        measured_label_w=label_w,
        measured_value_w=value_w,
        **inputs,
    )


def _assert_value_x_at_zone_center(zones) -> None:
    """value_x is the geometric center of the value zone."""
    expected = (zones.value_zone_left + zones.value_zone_right) / 2
    assert abs(zones.value_x - expected) < 0.6, (
        f"value_x={zones.value_x} but zone center = {expected} "
        f"(zone: {zones.value_zone_left}..{zones.value_zone_right})"
    )


# ─────────────────────────────────────────────────────────────────────
# Equal-spacing rule — Bug 3 fix verification
# ─────────────────────────────────────────────────────────────────────


def test_no_glyph_no_phantom_left_gap() -> None:
    """Bug 3 fix: glyph-absent badges have no reserved glyph slot.
    Label first char starts at `accent_w + pad`, no extra offset."""
    zones = _zones(label_w=50.0, value_w=30.0)
    pad = BRUTALIST_INPUTS["pad"]
    accent_w = BRUTALIST_INPUTS["accent_w"]
    # label_first_x = accent_w + pad (no glyph cursor advance)
    expected_label_first_x = accent_w + pad
    assert zones.glyph_x == 0.0
    assert zones.glyph_size == 0
    # label_x is the text-anchor='middle' center: first_x + w/2
    expected_label_x = expected_label_first_x + 50.0 / 2
    assert abs(zones.label_x - expected_label_x) < 0.6, (
        f"label_x={zones.label_x} but expected {expected_label_x} (first_x={expected_label_first_x} + label_w/2=25)"
    )


def test_no_state_indicator_no_phantom_right_gap() -> None:
    """Stateless badges have no reserved indicator slot.

    Every gap is pad including the right-edge gap (last zone → outer edge).
    value_zone_right =
    total_w - right_canvas_inset - pad (the final pad IS the right gap)."""
    zones = _zones(label_w=50.0, value_w=30.0, has_state_indicator=False)
    assert zones.indicator_x == 0.0
    assert zones.indicator_size == 0
    expected_right = zones.width - 0 - BRUTALIST_INPUTS["pad"]  # right_canvas_inset=0 for brutalist
    assert zones.value_zone_right == expected_right


def test_equal_spacing_with_glyph_and_state() -> None:
    """Every gap between PRESENT zones equals pad. Verifies the cursor
    advances by `content + pad` for each zone, with no extra adjustments."""
    inputs = {**BRUTALIST_INPUTS, "has_glyph": True}
    zones = compute_badge_zones(measured_label_w=40.0, measured_value_w=30.0, **inputs)
    pad = BRUTALIST_INPUTS["pad"]
    accent_w = BRUTALIST_INPUTS["accent_w"]
    # accent → glyph gap = pad
    assert zones.glyph_x == accent_w + pad
    # glyph → label gap = pad: label_first_x = glyph_x + glyph_size + pad
    expected_label_first_x = zones.glyph_x + 14 + pad
    expected_label_x = expected_label_first_x + 40.0 / 2
    assert abs(zones.label_x - expected_label_x) < 0.6
    # label_end + pad = left_panel_w
    expected_left_panel = round(expected_label_first_x + 40.0 + pad)
    assert zones.left_panel_w == expected_left_panel


def test_glyph_absent_collapses_width() -> None:
    """A badge with no glyph is narrower than the same badge with a glyph
    (no phantom 14 + pad reservation)."""
    common = dict(measured_label_w=50.0, measured_value_w=30.0)
    no_glyph = compute_badge_zones(**common, **BRUTALIST_INPUTS)  # type: ignore[arg-type]
    with_glyph = compute_badge_zones(
        **common,
        **{**BRUTALIST_INPUTS, "has_glyph": True},  # type: ignore[arg-type]
    )
    # With glyph: cursor advances by glyph_size + pad = 14 + 5 = 19px
    assert with_glyph.width - no_glyph.width >= 14 + BRUTALIST_INPUTS["pad"]


def test_state_indicator_absent_collapses_width() -> None:
    """A stateless badge is narrower than a stateful one — no reserved
    indicator zone (8 + 5 = 13px)."""
    with_state = _zones(label_w=33.0, value_w=22.0, has_state_indicator=True)
    without = _zones(label_w=33.0, value_w=22.0, has_state_indicator=False)
    assert without.width < with_state.width
    assert (with_state.width - without.width) >= 8 + BRUTALIST_INPUTS["pad"]


# ─────────────────────────────────────────────────────────────────────
# Value-zone centering invariant — preserved from v0.2.25
# ─────────────────────────────────────────────────────────────────────


def test_short_percentage_centers_in_value_zone() -> None:
    # "82%" — 3 characters, mono ~22px @ 11pt
    zones = _zones(label_w=33.0, value_w=22.0)
    _assert_value_x_at_zone_center(zones)


def test_long_value_centers() -> None:
    # "RECONNAISSANCE" as value, 14 chars
    zones = _zones(label_w=33.0, value_w=110.0)
    _assert_value_x_at_zone_center(zones)


def test_version_string_centers() -> None:
    zones = _zones(label_w=51.0, value_w=43.0)
    _assert_value_x_at_zone_center(zones)


def test_license_spdx_centers() -> None:
    zones = _zones(label_w=51.0, value_w=68.0)
    _assert_value_x_at_zone_center(zones)


def test_python_requires_centers() -> None:
    zones = _zones(label_w=51.0, value_w=42.0)
    _assert_value_x_at_zone_center(zones)


def test_stateless_value_recenters() -> None:
    """When the indicator collapses, the value zone reclaims its allocation
    and the text recenters within the wider zone."""
    zones = _zones(label_w=33.0, value_w=22.0, has_state_indicator=False)
    _assert_value_x_at_zone_center(zones)


# ─────────────────────────────────────────────────────────────────────
# Width / panel structure
# ─────────────────────────────────────────────────────────────────────


def test_total_width_clamped_to_minimum() -> None:
    """Tiny labels and values still produce a 60px-wide badge (min_total_w)."""
    zones = _zones(label_w=1.0, value_w=1.0)
    assert zones.width >= 60


def test_right_panel_x_consistent_with_left_panel_plus_seam() -> None:
    zones = _zones(label_w=40.0, value_w=30.0)
    sep_w = BRUTALIST_INPUTS["sep_w"]
    seam_w = BRUTALIST_INPUTS["seam_w"]
    assert zones.right_panel_x == zones.left_panel_w + sep_w + seam_w
    assert zones.right_panel_w == zones.width - zones.right_panel_x


# ─────────────────────────────────────────────────────────────────────
# Indicator geometry
# ─────────────────────────────────────────────────────────────────────


def test_indicator_inner_bit_centered() -> None:
    """The bit is half the indicator side, centered."""
    zones = _zones(label_w=33.0, value_w=44.0)
    assert zones.inner_bit_w == BRUTALIST_INPUTS["indicator_size"] // 2
    expected_offset = (BRUTALIST_INPUTS["indicator_size"] - zones.inner_bit_w) / 2
    assert zones.inner_bit_offset == expected_offset


def test_indicator_y_pinned_to_text_baseline() -> None:
    """text_y - 0.3 * font_size - indicator_size/2."""
    zones = _zones(label_w=33.0, value_w=44.0)
    expected = zones.text_y - BRUTALIST_INPUTS["value_font_size"] * 0.3 - BRUTALIST_INPUTS["indicator_size"] / 2
    assert abs(zones.indicator_y - expected) < 0.05


# ─────────────────────────────────────────────────────────────────────
# Glyph positioning
# ─────────────────────────────────────────────────────────────────────


def test_glyph_centered_vertically_when_present() -> None:
    inputs = {**BRUTALIST_INPUTS, "has_glyph": True}
    zones = compute_badge_zones(
        measured_label_w=33.0,
        measured_value_w=44.0,
        **inputs,
    )
    expected_text_center = zones.text_y - BRUTALIST_INPUTS["value_font_size"] * 0.3
    assert zones.glyph_y == round(expected_text_center - BRUTALIST_INPUTS["glyph_size"] / 2, 1)
    assert zones.glyph_x > 0


def test_badge_glyph_size_derives_from_ratio_with_cap() -> None:
    assert compute_badge_glyph_size(20, 0.6, 12) == 12
    assert compute_badge_glyph_size(32, 0.6, 12) == 12
    assert compute_badge_glyph_size(32, 0.6, 0) == 19


# ─────────────────────────────────────────────────────────────────────
# Cellular paradigm — sep_w=1 + right_canvas_inset=2 geometry
# ─────────────────────────────────────────────────────────────────────


def test_cellular_short_value_centers() -> None:
    zones = _zones_cellular(label_w=44.0, value_w=22.0)
    _assert_value_x_at_zone_center(zones)


def test_cellular_version_string_centers() -> None:
    zones = _zones_cellular(label_w=44.0, value_w=43.0)
    _assert_value_x_at_zone_center(zones)


def test_cellular_long_value_centers() -> None:
    zones = _zones_cellular(label_w=44.0, value_w=110.0)
    _assert_value_x_at_zone_center(zones)


def test_cellular_compact_centers() -> None:
    zones = _zones_cellular(label_w=33.0, value_w=22.0, compact=True)
    _assert_value_x_at_zone_center(zones)


def test_cellular_left_adornment_gap_keeps_large_badge_spacing() -> None:
    zones = compute_badge_zones(
        measured_label_w=33.0,
        measured_value_w=22.0,
        **{**CELLULAR_INPUTS, "has_glyph": True},
    )
    bookend_gap = zones.glyph_x - CELLULAR_INPUTS["left_adornment_width"]
    label_left = zones.label_x - zones.label_w / 2
    glyph_label_gap = label_left - (zones.glyph_x + zones.glyph_size)
    assert abs(bookend_gap - 4) < 0.1
    assert abs(glyph_label_gap - 4) < 0.1
    assert abs(bookend_gap - glyph_label_gap) <= 2


def test_cellular_badge_left_identity_cluster_is_symmetric() -> None:
    zones = compute_badge_zones(
        measured_label_w=33.0,
        measured_value_w=22.0,
        **{**CELLULAR_COMPACT_INPUTS, "has_glyph": True},
    )
    bookend_gap = zones.glyph_x - CELLULAR_COMPACT_INPUTS["left_adornment_width"]
    label_left = zones.label_x - zones.label_w / 2
    glyph_label_gap = label_left - (zones.glyph_x + zones.glyph_size)
    assert abs(bookend_gap - 4) < 0.1
    assert abs(glyph_label_gap - 4) < 0.1
    assert abs(bookend_gap - glyph_label_gap) <= 2


def test_cellular_stateless_zone_collapses_with_canvas_inset() -> None:
    """Cellular's 2px canvas inset shrinks the value zone right edge below
    total_w. visual_gap replaces pad for the visible trailing gap."""
    zones = _zones_cellular(label_w=44.0, value_w=22.0, has_state_indicator=False)
    _assert_value_x_at_zone_center(zones)
    expected_right = zones.width - CELLULAR_INPUTS["right_canvas_inset"] - CELLULAR_INPUTS["visual_gap"]
    assert zones.value_zone_right == expected_right


def test_cellular_right_panel_x_uses_paradigm_sep_w() -> None:
    """Cellular's sep_w=1 (vs brutalist's 2) places right_panel_x exactly
    where the cellular template paints the value slab."""
    zones = _zones_cellular(label_w=44.0, value_w=43.0)
    expected_right_panel_x = zones.left_panel_w + CELLULAR_INPUTS["sep_w"] + CELLULAR_INPUTS["seam_w"]
    assert zones.right_panel_x == expected_right_panel_x


# ─────────────────────────────────────────────────────────────────────
# Shrink-to-fit + camo bound (textLength emission)
# ─────────────────────────────────────────────────────────────────────


def test_label_text_length_is_measured_width_when_under_max() -> None:
    """When the label fits within max_label_w, no shrink — but textLength is
    still the measured width (the camo bound: a fallback font can't render
    wider than the zone when @font-face is blocked). label_w stays unclamped."""
    zones = compute_badge_zones(
        measured_label_w=40.0,
        measured_value_w=30.0,
        max_label_w=60.0,
        **BRUTALIST_INPUTS,
    )
    assert zones.label_text_length == 40.0
    assert zones.label_w == 40.0


def test_label_text_length_clamped_when_over_max() -> None:
    """Measured label exceeds max_label_w → textLength set to max, label_w clamped."""
    zones = compute_badge_zones(
        measured_label_w=200.0,
        measured_value_w=30.0,
        max_label_w=80.0,
        **BRUTALIST_INPUTS,
    )
    assert zones.label_text_length == 80.0
    assert zones.label_w == 80.0


def test_value_text_length_is_measured_width_by_default() -> None:
    """No max_value_w → no shrink, but value textLength is still the measured
    width (camo bound), matching the label."""
    zones = _zones(label_w=40.0, value_w=200.0)
    assert zones.value_text_length == 200.0
