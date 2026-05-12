"""v0.2.16 marquee + icon template behavior — paradigm-driven dimensions,
content-aware scroll, LIVE-block removal, chrome icon viewBox override.

Lives separately from existing marquee tests because v0.2.16 changes the
marquee contract significantly: dimensions, separator-kind, text-fill mode,
and LIVE-block infrastructure are all new. Grouping the assertions here
makes the v0.2.16 spec readable as a single test module.
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

# ────────────────────────────────────────────────────────────────────
#  Marquee — paradigm-driven dimensions
# ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("genome_id", "expected_w", "expected_h"),
    [
        ("chrome", 1040, 56),
        ("brutalist", 720, 32),
        # Cellular v0.3.0 visual refresh: marquee compacts to 800x32 (was 800x40).
        # Matches the v3-sulfur prototype's tighter scroll strip — paired with
        # mid_accent hairlines and info_accent scroll text.
        ("automata", 800, 32),
    ],
)
def test_marquee_dimensions_paradigm_driven(genome_id: str, expected_w: int, expected_h: int) -> None:
    """Each paradigm renders marquee at its declared width/height (chrome.yaml,
    brutalist.yaml, cellular.yaml). Default 800x40 is the schema baseline."""
    spec = ComposeSpec(type="marquee-horizontal", genome_id=genome_id, title="HW|TEST")
    svg = compose(spec).svg
    assert f'viewBox="0 0 {expected_w} {expected_h}"' in svg, f"{genome_id} viewBox mismatch"
    assert f'width="{expected_w}"' in svg, f"{genome_id} width mismatch"
    assert f'height="{expected_h}"' in svg, f"{genome_id} height mismatch"


# ────────────────────────────────────────────────────────────────────
#  Marquee — LIVE-block residue check
# ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("genome_id", ["chrome", "brutalist", "automata"])
def test_marquee_no_live_block_residue(genome_id: str) -> None:
    """v0.2.16 deleted the LIVE label panel + status diamond + divider entirely.
    No paradigm should emit residue from the old LIVE-block infrastructure."""
    spec = ComposeSpec(type="marquee-horizontal", genome_id=genome_id, title="HW|TEST")
    svg = compose(spec).svg
    # Hard residue checks — these were textual artifacts of the LIVE block.
    assert "LIVE</text>" not in svg, f"{genome_id} still emits LIVE label text"
    # The status diamond was a 7x7 rotate(45) rect group; reducing-motion-tests
    # in CI catch the breathing animation, but the rect itself is the marker.
    assert 'transform="rotate(45)"' not in svg, f"{genome_id} still emits status diamond"
    # Edge fades were sized to the LIVE panel — fade-l / fade-r gradients gone.
    assert "-fade-l" not in svg, f"{genome_id} still emits LIVE-block fade-left"
    assert "-fade-r" not in svg, f"{genome_id} still emits LIVE-block fade-right"


# ────────────────────────────────────────────────────────────────────
#  Marquee — content-aware scroll distance
# ────────────────────────────────────────────────────────────────────


def _extract_scroll_distance(svg: str) -> int:
    """Extract scroll_distance from the SMIL animateTransform `to=-Xpx 0`."""
    m = re.search(r'to="-(\d+) 0"', svg)
    assert m is not None, "scroll_distance not found in SVG"
    return int(m.group(1))


def test_marquee_scroll_distance_grows_with_content() -> None:
    """Long content should produce a larger scroll_distance than short content,
    proving the resolver wired _layout_marquee_items correctly."""
    short = compose(ComposeSpec(type="marquee-horizontal", genome_id="chrome", title="HW")).svg
    long_text = "|".join(["A VERY LONG SCROLL ITEM"] * 8)
    long_ = compose(ComposeSpec(type="marquee-horizontal", genome_id="chrome", title=long_text)).svg
    short_sd = _extract_scroll_distance(short)
    long_sd = _extract_scroll_distance(long_)
    assert long_sd > short_sd, f"Expected long_sd > short_sd; got long={long_sd} short={short_sd}"


def test_marquee_short_content_floors_at_viewport_width() -> None:
    """When content is shorter than the viewport, scroll_distance floors at
    viewport_width so the cycle is still a full pass (matches chrome target)."""
    svg = compose(ComposeSpec(type="marquee-horizontal", genome_id="chrome", title="HW")).svg
    sd = _extract_scroll_distance(svg)
    # Chrome viewport is 1040; a one-item "HW" marquee easily fits → floor applies.
    assert sd >= 1040, f"Expected scroll_distance >= viewport_width 1040; got {sd}"


def test_marquee_loop_boundary_matches_inter_item_rhythm() -> None:
    """Regression guard for the v0.2.16-fix loop-smoothness bug.

    Layout MUST emit a separator after every item (including the last) so the
    boundary between Set-A's trailing separator and Set-B's first item has the
    same item_gap (20px) as every within-set sep-to-item gap. Without this,
    the loop boundary has ~19-30px more spacing than the natural rhythm,
    producing a perceptible "lag/restart" feel at every cycle.

    The test extracts Set-A positions, computes the boundary gap (last sep end
    -> Set-B first item start), and asserts it's within 2px of the within-set
    rhythm (the 2px tolerance is float-to-int rounding in the layout helper).
    """
    svg = compose(
        ComposeSpec(
            type="marquee-horizontal",
            genome_id="chrome",
            title="HYPERWEAVE|CHROME HORIZON|LIVING SVG ARTIFACTS|v0.2.16",
        )
    ).svg
    # scroll_distance from animateTransform.
    sd_m = re.search(r'to="-(\d+) 0"', svg)
    assert sd_m
    sd = int(sd_m.group(1))
    # Extract all <text x=N> in Set-A (skip <rect> for separator-rect; chrome
    # uses glyph separators which are <text>).
    set_a = svg.split('data-hw-zone="set-a"')[1].split('data-hw-zone="set-b"')[0]
    xs = [int(m) for m in re.findall(r'<text x="(\d+)"', set_a)]
    # 4 items + 4 separators (one after each) = 8 entries.
    assert len(xs) == 8, f"expected 4 items + 4 separators, got {len(xs)} text nodes"
    # The last entry should be a separator (the new trailing one). Set-B first
    # item is at world x = 16 + scroll_distance.
    set_b_first_x = 16 + sd
    last_sep_x = xs[-1]
    boundary_gap = set_b_first_x - last_sep_x
    # Within-set sep-to-item gap (e.g., entry 1 = sep at 271, entry 2 = CHROME
    # HORIZON at 308). The sep takes some width; we measure start-of-sep to
    # start-of-next-item which equals sep_width + item_gap.
    intra_sep_to_item = xs[2] - xs[1]
    assert abs(boundary_gap - intra_sep_to_item) <= 2, (
        f"loop boundary gap ({boundary_gap}) must match within-set "
        f"sep-to-next-item rhythm ({intra_sep_to_item}); diff > 2px would feel "
        f"like a restart at every cycle. Set-A positions: {xs}, scroll_distance: {sd}"
    )


def test_marquee_set_b_offset_equals_scroll_distance() -> None:
    """Set-B group is offset by scroll_distance for seamless loop. The
    SMIL animateTransform translates by -scroll_distance; if Set-B isn't
    at +scroll_distance the loop has a visible jump."""
    svg = compose(ComposeSpec(type="marquee-horizontal", genome_id="chrome", title="HW|TEST|MARQUEE")).svg
    sd = _extract_scroll_distance(svg)
    # Set B is rendered as <g data-hw-zone="set-b" transform="translate(SD, 0)">.
    assert f'data-hw-zone="set-b" transform="translate({sd}, 0)"' in svg


# ────────────────────────────────────────────────────────────────────
#  Marquee — text-fill mode dispatch
# ────────────────────────────────────────────────────────────────────


def test_chrome_marquee_uses_chrome_text_gradient() -> None:
    """Chrome paradigm declares text_fill_mode=gradient + text_fill_gradient_id=ct.
    Items should reference url(#{uid}-ct) in their fill attribute (not a hex)."""
    svg = compose(ComposeSpec(type="marquee-horizontal", genome_id="chrome", title="HW|TEST")).svg
    # The chrome-text gradient definition exists in defs.
    assert re.search(r'<linearGradient id="hw-[^"]+-ct"', svg), "chrome-text gradient missing"
    # At least one tspan/text fill references the gradient.
    assert re.search(r'fill="url\(#hw-[^"]+-ct\)"', svg), "items don't reference chrome-text gradient"


def test_brutalist_marquee_uses_rect_separators() -> None:
    """Brutalist paradigm declares separator_kind=rect with separator_size=6
    and separator_color=#10B981. Each item-gap should be a 6x6 rect whose fill
    routes through --dna-signal (so the variant's accent cascades through),
    with #10B981 as the fallback for renderers that don't resolve the var."""
    svg = compose(
        ComposeSpec(
            type="marquee-horizontal",
            genome_id="brutalist",
            title="LIVING ARTIFACTS|SELF-CONTAINED|AGENT INTERFACES",
        )
    ).svg
    # Two items between three labels → at least 2 separator rects per Set; 4 total.
    # Round 7 wraps separator_color in var(--dna-signal, ...) so chrome variants
    # cascade naturally; brutalist's accent (#10B981) matches its separator hex
    # so the fallback case still equals the original color.
    rect_seps = re.findall(
        r'<rect [^>]*width="6" height="6"[^>]*fill="var\(--dna-signal, #10B981\)"[^>]*shape-rendering="crispEdges"',
        svg,
    )
    assert len(rect_seps) >= 4, f"Expected ≥4 emerald rect separators (Set A + B); got {len(rect_seps)}"


def test_brutalist_marquee_alternates_text_fill_cycle() -> None:
    """Brutalist text_fill_cycle=[var(--dna-ink-primary), var(--dna-signal)] →
    items rotate through the polarity-correct text color (ink_primary) and
    the variant accent (signal). v0.3.2 follow-up replaced --dna-ink-bright
    (which resolved to the DARK surface color for dark variants, making
    marquee text invisible) with --dna-ink-primary which carries the bright
    text color for dark variants and the dark ink for light variants —
    visible across all 12 brutalist variants regardless of substrate polarity."""
    svg = compose(
        ComposeSpec(
            type="marquee-horizontal",
            genome_id="brutalist",
            title="LIVING|SELF-CONTAINED|AGENT|INTERFACES",
        )
    ).svg
    # Item 0 gets --dna-ink-primary, item 1 --dna-signal (accent), repeat.
    assert 'fill="var(--dna-ink-primary)"' in svg
    assert 'fill="var(--dna-signal)"' in svg


def test_cellular_marquee_uses_monofamily_info_accent() -> None:
    """Cellular v0.3.0 visual refresh: marquee adopts the variant's info_accent
    for scroll text and mid_accent for the top/bottom hairlines + bullet
    separators. Replaces the prior bifamily teal/amethyst alternation since
    the marquee's narrow chromatic bandwidth (32px tall, 0.5px hairlines at
    0.2 opacity) couldn't perceptually communicate a paired-variant signature.

    Tested at the default variant (which the cellular paradigm declares as
    violet-teal, primary=teal). Teal's info_accent is #5BE0F0 and mid_accent
    is #1A6A7E."""
    svg = compose(
        ComposeSpec(
            type="marquee-horizontal",
            genome_id="automata",
            title="HYPERWEAVE|CELLULAR|LIVING|ARTIFACTS",
        )
    ).svg
    assert "#5BE0F0" in svg, "teal info_accent hex missing (scroll text)"
    assert "#1A6A7E" in svg, "teal mid_accent hex missing (hairlines + separators)"
    # Pre-v0.3.0 amethyst chromosome should NOT appear — paired variants no
    # longer split the marquee into bifamily tones.
    assert "#A88AD4" not in svg, "amethyst hex must not appear in v0.3.0 monofamily marquee"


# ────────────────────────────────────────────────────────────────────
#  Marquee — ?data= token mode integration
# ────────────────────────────────────────────────────────────────────


def test_marquee_data_token_mode_uses_paradigm_dimensions() -> None:
    """Data-token input path goes through the same _resolve_horizontal as raw
    text mode, so paradigm dims still apply."""
    from hyperweave.serve.data_tokens import ResolvedToken

    tokens = [
        ResolvedToken(kind="text", label="", value="HYPERWEAVE", ttl=0),
        ResolvedToken(kind="kv", label="VERSION", value="0.2.16", ttl=0),
    ]
    spec = ComposeSpec(
        type="marquee-horizontal",
        genome_id="chrome",
        data_tokens=tokens,
    )
    svg = compose(spec).svg
    assert 'viewBox="0 0 1040 56"' in svg
    # kv token should render as label+value tspan pair (paradigm independent).
    assert "VERSION" in svg
    assert "0.2.16" in svg


# ────────────────────────────────────────────────────────────────────
#  Icon — paradigm-driven viewBox override
# ────────────────────────────────────────────────────────────────────


def test_chrome_icon_circle_uses_120_unit_viewbox_at_64px() -> None:
    """Chrome paradigm's icon block declares viewbox_w=120, viewbox_h=120.
    The rendered output is 64x64 but the internal coordinate system is 120-unit
    so v2 specimen geometry (r=46/r=42 bezel, 0.6-unit hairlines) is preserved."""
    svg = compose(ComposeSpec(type="icon", genome_id="chrome", glyph="github", shape="circle")).svg
    assert 'viewBox="0 0 120 120"' in svg
    assert 'width="64"' in svg
    assert 'height="64"' in svg
    # 5-layer chrome bezel uses the v2 specimen radii.
    assert 'r="46"' in svg, "circle bezel outer radius (envelope ring) missing"
    assert 'r="42"' in svg, "circle bezel inner radius (well/hairline/rim) missing"


def test_chrome_icon_square_uses_120_unit_viewbox_at_64px() -> None:
    """Same viewBox-override mechanism as the circle variant."""
    svg = compose(ComposeSpec(type="icon", genome_id="chrome", glyph="github", shape="square")).svg
    assert 'viewBox="0 0 120 120"' in svg
    assert 'width="64"' in svg
    # 96x96 card body (v2 specimen dimensions).
    assert 'width="96" height="96" rx="6"' in svg


def test_brutalist_icon_keeps_64x64_viewbox_regression() -> None:
    """Brutalist paradigm doesn't declare icon.viewbox_w/h, so viewBox stays
    aligned to the rendered 64x64 size. Regression guard against the chrome
    viewBox-override leaking into brutalist."""
    svg = compose(ComposeSpec(type="icon", genome_id="brutalist", glyph="github", shape="square")).svg
    assert 'viewBox="0 0 64 64"' in svg
    assert 'width="64"' in svg


def test_chrome_icon_circle_has_rim_sweep_animation() -> None:
    """Chrome icon's 17.944s phi³ rim sweep is the material-physics signature.
    Verifies the rim gradient + animations got plumbed into chrome-defs.j2."""
    svg = compose(ComposeSpec(type="icon", genome_id="chrome", glyph="github", shape="circle")).svg
    assert "17.944s" in svg, "phi³ rim sweep duration missing"
    assert 'attributeName="x1"' in svg, "rim sweep x1 animate missing"


def test_chrome_icon_square_has_env_rail() -> None:
    """Square variant has the 6-unit env-rail at (3, 3) — the card-family
    signature. Circle variant has no rail."""
    svg = compose(ComposeSpec(type="icon", genome_id="chrome", glyph="github", shape="square")).svg
    assert "-env-rail" in svg, "square icon env-rail gradient missing"


def test_chrome_icon_circle_has_no_env_rail() -> None:
    """Env-rail def is wrapped in {% if icon_variant == 'binary-square' %} —
    circle icon should NOT include it."""
    svg = compose(ComposeSpec(type="icon", genome_id="chrome", glyph="github", shape="circle")).svg
    assert "-env-rail" not in svg, "env-rail leaked into circle variant"


def test_chrome_icon_square_uses_bevel_filter_not_simple_shadow() -> None:
    """v0.2.16 expanded the chrome icon filter from a basic drop-shadow to a
    feSpecularLighting bevel. Ensures the upgrade landed (square retains it —
    96x96 fill geometry handles the specular kernel as smooth metallic surface)
    and the old filter id ({{uid}}-sh) is gone."""
    svg = compose(ComposeSpec(type="icon", genome_id="chrome", glyph="github", shape="square")).svg
    assert "feSpecularLighting" in svg, "bevel filter's feSpecularLighting missing from defs"
    assert 'filter="url(#hw-' in svg, "square envelope rect should reference the bevel filter"
    # Old id was {{uid}}-sh; new id is {{uid}}-bevel.
    assert "-bevel" in svg, "new bevel filter ID missing"


def test_chrome_icon_circle_omits_bevel_filter_application() -> None:
    """Round 6 removed feSpecularLighting from the circle envelope STROKE because
    the 5-unit annular geometry is too narrow for the kernel — highlight pixelated
    as visible grain at 64px display. The filter primitive is still defined (square
    consumes it), but the circle's envelope no longer applies it; the linearGradient
    on the stroke carries the metallic sweep cleanly without kernel artifacts."""
    svg = compose(ComposeSpec(type="icon", genome_id="chrome", glyph="github", shape="circle")).svg
    # The envelope <circle> with stroke-width="5" must not reference the bevel filter.
    # Search for the specific pattern to avoid false positives from other elements.
    assert 'stroke-width="5" filter="url(#' not in svg, (
        "circle envelope stroke must not apply bevel filter — narrow annular geometry "
        "produces grain at small display sizes"
    )
