"""Primer badge + strip two-plate geometry pins (v0.4 specimen extraction).

Pins the shields-anatomy redesign against the approved specimens:
``HyperWeave_-_Badge_PyPI_8_Variants.svg`` (badge: 113.1x20 rx4 exact mono
rail) and ``HyperWeave_-_Strip_README-AI_8_Variants.svg`` (strip: 46px rx10
card inset (8,6) in a shadow canvas).
"""

from __future__ import annotations

import re

from hyperweave.compose.engine import compose
from hyperweave.compose.resolver import resolve
from hyperweave.compose.strip.layout import compute_badge_zones
from hyperweave.core.models import ComposeSpec


def _badge(variant: str = "porcelain") -> ComposeSpec:
    return ComposeSpec(
        type="badge",
        genome_id="primer",
        variant=variant,
        title="PYPI",
        value="0.3.14",
        glyph="python",
    )


def test_primer_badge_rail_closes_at_exact_width() -> None:
    """The canonical PYPI/0.3.14 badge closes at exactly 112.1 x 20.

    Rail: 7 | 12 glyph | 6 | label 24.3 (JBM 600 9.5 ls 0.5px) | 7 | 2 seam |
    8 | value 37.8 (JBM 700 10.5) | 8. Exact only because the text is
    monospace and middle-anchored (no bearing corrections). The glyph is 12px
    (family-standard ratio 0.6), not the specimen's 13 — the solid silhouette
    blooms on dark substrates.
    """
    result = compose(_badge())
    assert 'viewBox="0 0 112.1 20"' in result.svg
    assert 'width="112.1"' in result.svg


def test_primer_badge_seam_pair_and_glyph_geometry() -> None:
    """Seam groove at 56.3, shine at 57.3; 12px glyph at (7, 4)."""
    resolved = resolve(_badge())
    ctx = resolved.frame_context
    assert ctx["badge_seam_pair"]["groove_x"] == 56.3
    assert ctx["badge_seam_pair"]["shine_x"] == 57.3
    assert ctx["badge_label_zone"]["w"] == 56.3
    assert ctx["glyph_x"] == 7.0
    assert ctx["glyph_y"] == 4.0
    assert ctx["glyph_render_size"] == 12
    # Specimen baselines: label 13.3, value 13.4.
    assert ctx["badge_label_text_y"] == 13.3
    assert ctx["text_y"] == 13.4
    # Double-stroke rim: inner highlight inset 0.6 at rx 3.4; border rx 4.
    assert ctx["badge_inner_highlight"]["rx"] == 3.4
    assert ctx["badge_outer_border"]["rx"] == 4


def test_primer_badge_emits_no_text_length() -> None:
    """Exact-rail badges suppress textLength — mono advance is exact, and the
    camo fallback bound would squeeze real JetBrains Mono."""
    result = compose(_badge())
    assert "textLength" not in result.svg


def test_primer_badge_label_is_muted_ink_secondary() -> None:
    """Label = muted ink_secondary; value = neutral ink; glyph carries the
    sole accent (porcelain: cobalt #1D4ED8)."""
    svg = compose(_badge()).svg
    assert 'fill="#5C7C9E"' in svg  # porcelain ink_secondary label
    assert 'fill="#1E3A5F"' in svg  # porcelain neutral-ink value
    noir = compose(_badge(variant="noir")).svg
    assert 'fill="#8A8A8A"' in noir  # noir ink_secondary label


def test_primer_stateful_badge_keeps_leading_status_glyph() -> None:
    """Stateful badges keep the locked status-glyph marks (ping leads value)."""
    result = compose(
        ComposeSpec(
            type="badge",
            genome_id="primer",
            variant="porcelain",
            title="BUILD",
            value="passing",
            state="passing",
        )
    )
    assert "hw-pri-ping" in result.svg
    assert 'data-hw-zone="status"' in result.svg


def test_badge_rail_kwargs_inert_by_default() -> None:
    """The rail kwargs at 0.0 reproduce the legacy half-gap/pad walk."""
    base = dict(
        height=20,
        pad=7,
        measured_label_w=24.3,
        measured_value_w=37.8,
        has_glyph=True,
        has_state_indicator=False,
        accent_w=0,
        glyph_size=13,
        glyph_left_offset=0,
        sep_w=2,
        seam_w=1,
        indicator_size=8,
        min_total_w=40,
        seam_render_w=2.0,
        seam_specular_offset=1.0,
        glyph_label_gap=6.0,
    )
    legacy = compute_badge_zones(**base)  # type: ignore[arg-type]
    explicit_legacy = compute_badge_zones(  # type: ignore[arg-type]
        **base, rail_start_pad=0.0, rail_end_pad=0.0, seam_gap_left=0.0, seam_gap_right=0.0
    )
    assert legacy == explicit_legacy
    # Legacy walk uses pad for entry and half-gaps (3.5) around the seam.
    assert legacy.seam_left_x == 7 + 13 + 6 + 24.3 + 3.5


def test_badge_rail_kwargs_produce_primer_rail() -> None:
    """Primer's declared rail (7 entry, 12 glyph, 7|seam|8, 8 exit) closes
    at 112.1."""
    zones = compute_badge_zones(
        height=20,
        pad=7,
        measured_label_w=24.3,
        measured_value_w=37.8,
        has_glyph=True,
        has_state_indicator=False,
        accent_w=0,
        glyph_size=12,
        glyph_left_offset=0,
        sep_w=2,
        seam_w=1,
        indicator_size=8,
        min_total_w=40,
        seam_render_w=2.0,
        seam_specular_offset=1.0,
        glyph_label_gap=6.0,
        rail_start_pad=7.0,
        rail_end_pad=8.0,
        seam_gap_left=7.0,
        seam_gap_right=8.0,
    )
    assert zones.seam_left_x == 56.3
    assert zones.seam_specular_x == 57.3
    assert zones.width_exact == 112.1
    assert zones.width == 112


def _strip(variant: str = "porcelain") -> ComposeSpec:
    return ComposeSpec(
        type="strip",
        genome_id="primer",
        variant=variant,
        title="README-AI",
        glyph="github",
        value="STARS:2913,FORKS:284,VERSION:0.6.3",
        state="passing",
    )


def test_primer_strip_card_is_full_bleed() -> None:
    """Full-bleed 46px rx10 card — canvas == card, no shadow-margin inset.

    An embedded artifact has no page for a drop shadow to fade into: an inset
    margin renders as a hard-clipped shadow box on the README ground (the
    blur far exceeds any practical margin), so the card spans the viewBox and
    the shadow clips behind it, exactly like the alpha.1 plate."""
    resolved = resolve(_strip())
    ctx = resolved.frame_context
    assert resolved.height == 46
    assert ctx["strip_card"]["x"] == 0.0
    assert ctx["strip_card"]["y"] == 0.0
    assert ctx["strip_card"]["h"] == 46.0
    assert ctx["strip_card"]["rx"] == 10
    assert resolved.width == ctx["strip_card"]["w"]
    assert ctx["strip_content_offset"] is None
    # Double-stroke rim mirrors the badge: inset 0.6 rx 9.4 / inset 0.5 rx 9.5.
    assert ctx["strip_inner_highlight"]["rx"] == 9.4
    assert ctx["strip_outer_border"]["rx"] == 9.5


def test_primer_strip_divider_pair_geometry_and_colors() -> None:
    """Paired 1px groove+shine dividers, 24px tall at card y=10, inverting
    per substrate: cool-on-white on lights, a dark groove on darks."""
    light = resolve(_strip())
    assert light.frame_context["strip_divider_pair"]["y"] == 10
    assert light.frame_context["strip_divider_pair"]["h"] == 24
    assert light.frame_context["strip_divider_groove_color"] == "rgba(30,58,95,0.10)"
    assert light.frame_context["strip_divider_shine_color"] == "rgba(255,255,255,0.7)"
    dark = resolve(_strip(variant="noir"))
    assert dark.frame_context["strip_divider_groove_color"] == "rgba(0,0,0,0.45)"
    assert dark.frame_context["strip_divider_shine_color"] == "rgba(255,255,255,0.10)"


def test_primer_strip_status_pinned_off_right_edge() -> None:
    """The pulse is a terminus pinned at content_width - 18 (card-space)."""
    resolved = resolve(_strip())
    zones = resolved.frame_context["strip_zones"]
    assert zones.core.status_x == zones.core.content_width - 18


def test_primer_strip_type_voices() -> None:
    """Identity Inter 800 14.5; metric labels muted JBM 600 8; values JBM 700
    16 in neutral ink — the rail shares the badges' type language."""
    svg = compose(_strip()).svg
    assert "font-weight: 800" in svg
    assert "font-size: 14.5px" in svg
    match = re.search(r"\.\S+-metric-label \{[^}]+\}", svg)
    assert match is not None
    label_class = match.group(0)
    assert "fill: #5C7C9E" in label_class  # porcelain ink_secondary, not accent
    assert "font-weight: 600" in label_class
    match = re.search(r"\.\S+-metric-value \{[^}]+\}", svg)
    assert match is not None
    value_class = match.group(0)
    assert "JetBrains Mono" in value_class
    assert "font-size: 16.0px" in value_class


def test_primer_strip_pulse_greens_per_substrate() -> None:
    """strip_status_dot: #34D17A on the four darks, #1AA35A on the four lights."""
    assert "#1AA35A" in compose(_strip()).svg
    assert "#34D17A" in compose(_strip(variant="carbon")).svg
