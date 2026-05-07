"""Unit tests for compose/layout.py — BadgeLayout geometry correctness.

The v0.2.25 centering fix is verified here: ``value_x`` MUST equal the
geometric center of the value zone (``(value_zone_left +
value_zone_right) / 2``) for every realistic value-string category. The
old resolver used a midpoint of two unrelated bounds and drifted text
1.5px rightward in the stateful case and was undefined in the stateless
case.

Cases mirror real GitHub/PyPI data so failures map cleanly to user-
visible regressions:

* short percentage ("82%")
* full name ("RECONNAISSANCE")
* version string ("0.2.23")
* license SPDX ("Apache-2.0")
* python_requires (">=3.12")
* stateless STARS-like value ("42") with show_indicator=False
"""

from __future__ import annotations

from hyperweave.compose.layout import compute_badge_layout

# Brutalist-paradigm constants reflecting current data/paradigms/brutalist.yaml
# defaults. sep_w=2, seam_w=3, no canvas inset.
BRUTALIST_INPUTS = dict(
    height=20,
    has_glyph=False,
    use_mono=True,
    label_uppercase=True,
    accent_w=4,
    inset=0,
    glyph_size=14,
    glyph_gap=4,
    glyph_left_offset=0,
    sep_w=2,
    seam_w=3,
    indicator_size=8,
    ind_pad_r=8,
    val_pad_l=3,
    val_min_gap=3,
    text_y_factor=0.69,
    value_font_size=11.0,
)

# Cellular-paradigm constants reflecting data/paradigms/cellular.yaml. The
# 1px gradient seam (sep_w=1) and 2px canvas inset (right_canvas_inset=2)
# produced a 1.5px right-drift in the first-pass v0.2.25 fix that snapshot
# tests caught only by accident; assertion-based coverage at this layer is
# the correct primary defense.
CELLULAR_INPUTS = dict(
    height=32,
    has_glyph=False,
    use_mono=False,
    label_uppercase=True,
    accent_w=4,
    inset=0,
    glyph_size=12,
    glyph_gap=4,
    glyph_left_offset=18,
    sep_w=1,
    seam_w=3,
    indicator_size=8,
    ind_pad_r=8,
    val_pad_l=3,
    val_min_gap=3,
    text_y_factor=0.656,
    value_font_size=12.0,
    right_canvas_inset=2,
)

CELLULAR_COMPACT_INPUTS = {**CELLULAR_INPUTS, "height": 20, "glyph_size": 8, "glyph_left_offset": 12}


def _layout(*, label_w: float, value_w: float, value_len: int, show_indicator: bool = True):
    return compute_badge_layout(
        measured_label_w=label_w,
        measured_value_w=value_w,
        value_raw_len=value_len,
        show_indicator=show_indicator,
        **BRUTALIST_INPUTS,
    )


def _layout_cellular(
    *, label_w: float, value_w: float, value_len: int, show_indicator: bool = True, compact: bool = False
):
    inputs = CELLULAR_COMPACT_INPUTS if compact else CELLULAR_INPUTS
    return compute_badge_layout(
        measured_label_w=label_w,
        measured_value_w=value_w,
        value_raw_len=value_len,
        show_indicator=show_indicator,
        **inputs,
    )


def _assert_value_x_at_zone_center(layout) -> None:
    """The v0.2.25 centering invariant — text MUST be at the zone center."""
    expected = (layout.value_zone_left + layout.value_zone_right) / 2
    assert abs(layout.value_x - expected) < 0.5, (
        f"value_x={layout.value_x} but zone center = {expected} "
        f"(zone: {layout.value_zone_left}..{layout.value_zone_right})"
    )


# ─────────────────────────────────────────────────────────────────────
# Centering invariant — six representative value categories
# ─────────────────────────────────────────────────────────────────────


def test_short_percentage_centers_in_value_zone() -> None:
    # "82%" — 3 characters, mono ~22px @ 11pt
    layout = _layout(label_w=33.0, value_w=22.0, value_len=3)
    _assert_value_x_at_zone_center(layout)


def test_long_label_centers() -> None:
    # "RECONNAISSANCE" as value, 14 chars
    layout = _layout(label_w=33.0, value_w=110.0, value_len=14)
    _assert_value_x_at_zone_center(layout)


def test_version_string_centers() -> None:
    # "0.2.23" — the headline regression case the v0.2.25 fix targets.
    layout = _layout(label_w=51.0, value_w=43.0, value_len=6)
    _assert_value_x_at_zone_center(layout)


def test_license_spdx_centers() -> None:
    # "Apache-2.0" license string
    layout = _layout(label_w=51.0, value_w=68.0, value_len=10)
    _assert_value_x_at_zone_center(layout)


def test_python_requires_centers() -> None:
    # ">=3.12" python_requires-style
    layout = _layout(label_w=51.0, value_w=42.0, value_len=6)
    _assert_value_x_at_zone_center(layout)


def test_stateless_no_indicator_zone_collapses() -> None:
    """When the indicator isn't rendered, the value zone reclaims its
    16px allocation (indicator_size=8 + ind_pad_r=8) and the text recenters.
    This was UNDEFINED under the old midpoint-of-unrelated-bounds formula."""
    layout = _layout(label_w=33.0, value_w=22.0, value_len=3, show_indicator=False)
    _assert_value_x_at_zone_center(layout)
    # value_zone_right should be at total_w - val_min_gap (no indicator carve-out)
    assert layout.value_zone_right == layout.width - BRUTALIST_INPUTS["val_min_gap"]


# ─────────────────────────────────────────────────────────────────────
# Width / panel structure
# ─────────────────────────────────────────────────────────────────────


def test_total_width_clamped_to_minimum() -> None:
    """Tiny labels and values still produce a 60px-wide badge."""
    layout = _layout(label_w=1.0, value_w=1.0, value_len=1)
    assert layout.width >= 60


def test_no_indicator_yields_narrower_badge() -> None:
    """Pre-v0.2.25 the indicator allocation was always reserved; now it
    collapses with show_indicator=False — visible width savings on STARS,
    VERSION, LICENSE, etc."""
    with_indicator = _layout(label_w=33.0, value_w=22.0, value_len=3, show_indicator=True)
    without = _layout(label_w=33.0, value_w=22.0, value_len=3, show_indicator=False)
    assert without.width < with_indicator.width
    assert (with_indicator.width - without.width) >= 16  # indicator_size + ind_pad_r


def test_right_panel_x_consistent_with_left_panel_plus_seam() -> None:
    layout = _layout(label_w=40.0, value_w=30.0, value_len=4)
    assert layout.right_panel_x == layout.left_panel_w + BRUTALIST_INPUTS["sep_w"] + BRUTALIST_INPUTS["seam_w"]
    assert layout.right_panel_w == layout.width - layout.right_panel_x


# ─────────────────────────────────────────────────────────────────────
# Indicator geometry
# ─────────────────────────────────────────────────────────────────────


def test_indicator_inner_bit_centered() -> None:
    """The bit is half the indicator side, centered."""
    layout = _layout(label_w=33.0, value_w=44.0, value_len=7)
    assert layout.inner_bit_w == BRUTALIST_INPUTS["indicator_size"] // 2
    expected_offset = (BRUTALIST_INPUTS["indicator_size"] - layout.inner_bit_w) / 2
    assert layout.inner_bit_offset == expected_offset


def test_indicator_y_pinned_to_text_baseline() -> None:
    """text_y - 0.3 * font_size - indicator_size/2 — pins the indicator
    visual center to the value-text midline (cap_height ≈ 70% of size)."""
    layout = _layout(label_w=33.0, value_w=44.0, value_len=7)
    expected = layout.text_y - BRUTALIST_INPUTS["value_font_size"] * 0.3 - BRUTALIST_INPUTS["indicator_size"] / 2
    assert abs(layout.indicator_y - expected) < 0.05  # rounded to 1dp


# ─────────────────────────────────────────────────────────────────────
# Glyph positioning
# ─────────────────────────────────────────────────────────────────────


def test_no_glyph_zeros_glyph_position() -> None:
    layout = _layout(label_w=33.0, value_w=44.0, value_len=7)
    assert layout.glyph_x == 0
    assert layout.glyph_y == 0.0


def test_glyph_centered_vertically_when_present() -> None:
    layout = compute_badge_layout(
        measured_label_w=33.0,
        measured_value_w=44.0,
        value_raw_len=7,
        show_indicator=True,
        has_glyph=True,
        height=20,
        use_mono=True,
        label_uppercase=True,
        accent_w=4,
        inset=0,
        glyph_size=14,
        glyph_gap=4,
        glyph_left_offset=0,
        sep_w=2,
        seam_w=3,
        indicator_size=8,
        ind_pad_r=8,
        val_pad_l=3,
        val_min_gap=3,
        text_y_factor=0.69,
        value_font_size=11.0,
    )
    assert layout.glyph_y == round((20 - 14) / 2, 1)
    assert layout.glyph_x > 0


# ─────────────────────────────────────────────────────────────────────
# Cellular paradigm — sep_w=1 + right_canvas_inset=2 geometry
# ─────────────────────────────────────────────────────────────────────


def test_cellular_short_value_centers() -> None:
    layout = _layout_cellular(label_w=44.0, value_w=22.0, value_len=3)
    _assert_value_x_at_zone_center(layout)


def test_cellular_version_string_centers() -> None:
    layout = _layout_cellular(label_w=44.0, value_w=43.0, value_len=6)
    _assert_value_x_at_zone_center(layout)


def test_cellular_long_value_centers() -> None:
    layout = _layout_cellular(label_w=44.0, value_w=110.0, value_len=14)
    _assert_value_x_at_zone_center(layout)


def test_cellular_compact_centers() -> None:
    layout = _layout_cellular(label_w=33.0, value_w=22.0, value_len=3, compact=True)
    _assert_value_x_at_zone_center(layout)


def test_cellular_stateless_zone_collapses_with_canvas_inset() -> None:
    """Cellular's 2px canvas inset shrinks the value zone right edge below
    total_w. Verifies zone_right tracks ``total_w - right_canvas_inset -
    val_min_gap`` rather than the brutalist ``total_w - val_min_gap``."""
    layout = _layout_cellular(label_w=44.0, value_w=22.0, value_len=3, show_indicator=False)
    _assert_value_x_at_zone_center(layout)
    expected_right = layout.width - CELLULAR_INPUTS["right_canvas_inset"] - CELLULAR_INPUTS["val_min_gap"]
    assert layout.value_zone_right == expected_right


def test_cellular_right_panel_x_uses_paradigm_sep_w() -> None:
    """Cellular's sep_w=1 (vs brutalist's 2) places right_panel_x exactly
    where the cellular template paints the value slab. A regression here
    would re-introduce the +1.5px drift this test pins out."""
    layout = _layout_cellular(label_w=44.0, value_w=43.0, value_len=6)
    expected_right_panel_x = layout.left_panel_w + CELLULAR_INPUTS["sep_w"] + CELLULAR_INPUTS["seam_w"]
    assert layout.right_panel_x == expected_right_panel_x
