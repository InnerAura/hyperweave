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
        # v0.3.12: all three marquees reconciled to their 800x44 prototypes
        # (chrome was 1040x56, automata 800x32 — old dims that survived the v0.2.x
        # marquee rebuild; both now match marquee-dense-chrome / automata-bone-v4).
        ("chrome", 800, 44),
        ("brutalist", 800, 44),
        ("automata", 800, 44),
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
#  Marquee — per-paradigm liveness vocabulary (v0.3.12)
# ────────────────────────────────────────────────────────────────────


def test_marquee_liveness_vocabulary_per_paradigm() -> None:
    """v0.3.12 reverses the v0.2.16 LIVE-block deletion: each paradigm now
    carries its OWN static, purely DECORATIVE liveness markup with its own
    @keyframes — chrome a LIVE wordmark + pulsing diamond, brutalist a
    square-in-square strobe-cube in the left end-cap, automata a travelling
    wave-rail. None of it binds data-hw-status (it reflects no single status —
    a marquee has N cells), and all of it is prefers-reduced-motion-guarded."""
    chrome = compose(ComposeSpec(type="marquee-horizontal", genome_id="chrome", title="HW|TEST")).svg
    assert "LIVE</text>" in chrome, "chrome marquee missing LIVE wordmark"
    assert 'class="hw-mq-diamond"' in chrome, "chrome marquee missing pulsing diamond"

    brutalist = compose(ComposeSpec(type="marquee-horizontal", genome_id="brutalist", title="HW|TEST")).svg
    assert 'class="hw-mq-cube"' in brutalist, "brutalist marquee missing strobe-cube live node"
    assert 'data-hw-zone="cap-left"' in brutalist, "brutalist marquee missing left end-cap"

    automata = compose(ComposeSpec(type="marquee-horizontal", genome_id="automata", title="HW|TEST")).svg
    assert 'class="hw-mq-wv"' in automata, "automata marquee missing travelling wave-rail"

    # Liveness is DECORATIVE — no liveness element carries data-hw-status, and
    # every paradigm guards its motion with prefers-reduced-motion.
    for genome_id, svg in (("chrome", chrome), ("brutalist", brutalist), ("automata", automata)):
        assert "prefers-reduced-motion" in svg, f"{genome_id} liveness missing reduced-motion guard"
        for marker in ("hw-mq-diamond", "hw-mq-cube", "hw-mq-wv"):
            assert not re.search(rf'class="{marker}"[^>]*data-hw-status', svg), (
                f"{genome_id} liveness element {marker} must not bind data-hw-status"
            )


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
    # Chrome viewport is 800 (v0.3.12 reconciled to the prototype); a one-item
    # "HW" marquee easily fits → floor applies.
    assert sd >= 800, f"Expected scroll_distance >= viewport_width 800; got {sd}"


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

    v0.3.12: chrome moved to item_layout=module (stacked cells, no glyph
    separators), so the separator-after-every-item rhythm this guards now lives
    in the RIBBON layout — automata. Retargeted accordingly.
    """
    svg = compose(
        ComposeSpec(
            type="marquee-horizontal",
            genome_id="automata",
            variant="bone",
            title="HYPERWEAVE|CELLULAR AUTOMATA|LIVING SVG ARTIFACTS|v0.3.12",
        )
    ).svg
    # scroll_distance from animateTransform.
    sd_m = re.search(r'to="-(\d+) 0"', svg)
    assert sd_m
    sd = int(sd_m.group(1))
    # Extract all <text x=N> in Set-A (skip <rect> for separator-rect; automata
    # uses glyph separators (▪) which are <text>).
    set_a = svg.split('data-hw-zone="set-a"')[1].split('data-hw-zone="set-b"')[0]
    xs = [int(m) for m in re.findall(r'<text x="(\d+)"', set_a)]
    # 4 items + 4 separators (one after each) = 8 entries per cycle. v0.3.12:
    # chrome's smaller 11px font means short content may repeat to fill the
    # 800px viewport, so the count is a multiple of 8 (the per-cycle entry
    # count), not exactly 8. The boundary check below holds regardless.
    assert len(xs) >= 8 and len(xs) % 8 == 0, f"expected a multiple of 8 text nodes, got {len(xs)}"
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


# NOTE (v0.3.12): the former brutalist-rect-separators, brutalist-text-fill-
# cycle, and cellular-monofamily-info-accent tests asserted coloring/separator
# behavior the marquee upgrade removed — brutalist now renders MODULES (dividers,
# not inter-item rect bullets) and all paradigms color by role (category/state/
# hero) via the cascade bridge, not a per-item cycle or info_accent fill. The
# replacement behavior is pinned end-to-end in tests/test_marquee_v0_3_12.py.


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
    assert 'viewBox="0 0 800 44"' in svg
    # kv token should render as label+value tspan pair (paradigm independent).
    assert "VERSION" in svg
    assert "0.2.16" in svg


# ────────────────────────────────────────────────────────────────────
#  Icon — paradigm-driven viewBox override
# ────────────────────────────────────────────────────────────────────


def test_chrome_icon_circle_uses_108_unit_viewbox_at_64px() -> None:
    """Chrome paradigm's icon block declares viewbox_w=108, viewbox_h=108 (v0.3.12:
    trimmed from 120 to remove excess padding so the Ø92 bezel fills the box at
    ~85% — matching automata 100% / brutalist 94% — not 77%). Rendered output is
    64x64; the v2 specimen geometry (r=46/r=42 bezel, 0.6-unit hairlines) is
    preserved byte-for-byte — only the group origin recenters (54, not 60)."""
    svg = compose(ComposeSpec(type="icon", genome_id="chrome", glyph="github", shape="circle")).svg
    assert 'viewBox="0 0 108 108"' in svg
    assert 'width="64"' in svg
    assert 'height="64"' in svg
    # 5-layer chrome bezel uses the v2 specimen radii (unchanged by the trim).
    assert 'r="46"' in svg, "circle bezel outer radius (envelope ring) missing"
    assert 'r="42"' in svg, "circle bezel inner radius (well/hairline/rim) missing"
    # Recentered group origin: 108/2 = 54 (was 60 in the 120-unit field).
    assert "translate(54, 54)" in svg, "circle group should recenter at 54 in the 108 viewBox"


def test_chrome_icon_square_uses_108_unit_viewbox_at_64px() -> None:
    """Same viewBox-trim mechanism as the circle variant (120 → 108). The 96x96
    card body is unchanged; its group origin recenters to (6, 6)."""
    svg = compose(ComposeSpec(type="icon", genome_id="chrome", glyph="github", shape="square")).svg
    assert 'viewBox="0 0 108 108"' in svg
    assert 'width="64"' in svg
    # 96x96 card body (v2 specimen dimensions, unchanged by the trim).
    assert 'width="96" height="96" rx="6"' in svg
    assert "translate(6, 6)" in svg, "square card group should recenter at (6, 6) in the 108 viewBox"


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
    """Circle envelope stroke omits feSpecularLighting.

    The 5-unit annular geometry is too narrow for the kernel, which makes the
    highlight pixelate as visible grain at 64px display. The filter primitive
    is still defined for square icons, but the circle envelope relies on the
    stroke gradient for a clean metallic sweep.
    """
    svg = compose(ComposeSpec(type="icon", genome_id="chrome", glyph="github", shape="circle")).svg
    # The envelope <circle> with stroke-width="5" must not reference the bevel filter.
    # Search for the specific pattern to avoid false positives from other elements.
    assert 'stroke-width="5" filter="url(#' not in svg, (
        "circle envelope stroke must not apply bevel filter — narrow annular geometry "
        "produces grain at small display sizes"
    )
