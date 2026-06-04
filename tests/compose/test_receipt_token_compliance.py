"""Compliance tests for the v0.2.21 receipt compositor token surface.

Architectural mandate: receipt.svg.j2 is a compositor frame. It works exactly
like badge.svg.j2 and strip.svg.j2 — one template, zero conditionals on
skin/mode/genome. All visual variation flows through ``var(--dna-*)`` genome
tokens. When a skin doesn't want an element, its token is ``"transparent"``;
the template renders the rect but it paints no pixels.

These tests are guardrails to prevent the conditional regression that
introduced the ``{% if skin_mode %}`` branches in earlier sessions. Each
covers a different layer of the contract:

* :func:`test_receipt_template_has_zero_skin_conditionals` — template layer
* :func:`test_telemetry_genomes_carry_full_receipt_token_surface` — JSON layer
* :func:`test_assembler_emits_receipt_tokens_per_genome` — assembler layer
* :func:`test_compute_treemap_layout_accent_position_geometry` — resolver layer
* :func:`test_pill_rx_clamping_documented_per_genome` — SVG2 §10.6 contract

A failure here means a skin can't be added by JSON-only edits anymore — the
single most important architectural property of the compositor.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from hyperweave.compose.assembler import genome_to_css
from hyperweave.compose.engine import compose
from hyperweave.compose.treemap import compute_treemap_layout
from hyperweave.core.models import ComposeSpec
from hyperweave.core.schema import GenomeSpec

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_RECEIPT_TEMPLATE = _REPO_ROOT / "src/hyperweave/templates/frames/receipt.svg.j2"
_GLYPH_PARTIAL = _REPO_ROOT / "src/hyperweave/templates/partials/provider-glyphs.svg.j2"
_GENOMES_DIR = _REPO_ROOT / "src/hyperweave/data/genomes"

_TELEMETRY_GENOMES = (
    "telemetry-voltage",
    "telemetry-claude-code",
    "telemetry-cream",
)

_RECEIPT_TOKEN_FIELDS = frozenset(
    {
        "pill_outer_bg",
        "pill_outer_stroke",
        "pill_inner_bg",
        "pill_text",
        "pill_rule_top",
        "pill_rule_bottom",
        "pill_rx",
        "glyph_fill",
        "card_border",
        "card_border_top",
        "card_inner_glyph",
        "treemap_accent_side",
    },
)

# CSS vars consumed directly by receipt.svg.j2 (pill + card-frame surface).
_RECEIPT_TEMPLATE_CSS_VARS = frozenset(
    {
        "--dna-pill-outer-bg",
        "--dna-pill-outer-stroke",
        "--dna-pill-inner-bg",
        "--dna-pill-text",
        "--dna-pill-rule-top",
        "--dna-pill-rule-bottom",
        "--dna-card-border",
        "--dna-card-border-top",
    },
)

# CSS vars consumed by provider-glyphs.svg.j2 (included in receipt's <defs>).
_GLYPH_PARTIAL_CSS_VARS = frozenset({"--dna-glyph-fill", "--dna-card-inner-glyph"})

# Full surface — assembled by genome_to_css regardless of which file paints them.
_RECEIPT_CSS_VARS = _RECEIPT_TEMPLATE_CSS_VARS | _GLYPH_PARTIAL_CSS_VARS


def _load_genome(genome_id: str) -> dict:
    return json.loads((_GENOMES_DIR / f"{genome_id}.json").read_text())


# --------------------------------------------------------------------------- #
# Template layer                                                              #
# --------------------------------------------------------------------------- #


def test_receipt_template_has_zero_skin_conditionals() -> None:
    """receipt.svg.j2 must have zero skin/mode/genome-id branching.

    The receipt is a compositor frame: structural variation is paradigm-
    dispatched (template includes), visual variation is token-driven. Any
    ``{% if skin_mode %}`` / ``{% if mode == ... %}`` / ``{% if light %}``
    block here regresses the architecture and forces per-skin Python work
    when a new skin is added.
    """
    body = _RECEIPT_TEMPLATE.read_text()
    forbidden_patterns = [
        r"\{% *if .*skin_mode",
        r"\{% *if .*\bmode\b",
        r"\{% *if .*\blight\b",
        r"\{% *if .*\bdark\b",
        r"data-hw-mode=\"\{\{ *skin_mode",
    ]
    for pattern in forbidden_patterns:
        assert re.search(pattern, body) is None, f"receipt.svg.j2 contains forbidden skin-keyed pattern: {pattern}"


def test_receipt_template_uses_pill_and_card_css_vars() -> None:
    """receipt.svg.j2 must reference the pill + card-frame CSS-var tokens.

    Verifies the template is actually consuming the new token surface; a
    refactor that adds tokens to the genome JSON without using them in the
    template would silently miss the architectural target. Glyph tokens are
    checked separately because they live in the provider-glyphs partial
    (which the receipt includes via ``{% block defs %}``).
    """
    body = _RECEIPT_TEMPLATE.read_text()
    for css_var in _RECEIPT_TEMPLATE_CSS_VARS:
        assert css_var in body, f"receipt.svg.j2 missing reference to {css_var}"


def test_receipt_template_defines_card_shape_clippath() -> None:
    """receipt.svg.j2 must declare a ``#receipt-card-shape`` clipPath in defs.

    Matches the claude-code v9 specimen pattern (specimen line 82). Any element
    that paints to the SVG edges (substrate, top accent strip) must clip to
    this shape so its corners inherit the rounding instead of poking out as
    square corners around the rounded card border. Without this clipPath,
    the receipt looks tacky on light skins (claude-code, cream) where the
    host bg contrasts with the substrate at the unclipped corners.
    """
    body = _RECEIPT_TEMPLATE.read_text()
    assert '<clipPath id="receipt-card-shape">' in body, (
        "receipt.svg.j2 must define <clipPath id='receipt-card-shape'> for corner rounding"
    )


def test_receipt_substrate_has_rounded_corners() -> None:
    """The rendered receipt substrate must have rx="5.5" to match the card border.

    Without rx on the substrate, its square corners protrude past the card
    border's rounded shape (rx=5.5), creating the "outside square that boxes
    the rounded shape" visual artifact that's invisible on dark skins (host
    bg blends) but glaring on cream / claude-code paper substrates.
    """
    body = _RECEIPT_TEMPLATE.read_text()
    assert 'rx="{{ receipt_geom.card_rx }}" ry="{{ receipt_geom.card_rx }}"' in body
    svg = compose(
        ComposeSpec(
            type="receipt",
            genome_id="telemetry-voltage",
            telemetry_data={"session": {}, "profile": {}, "tools": {}, "stages": []},
        )
    ).svg
    substrate_pattern = (
        r'<rect width="800" height="500" '
        r'rx="5\.5" ry="5\.5" fill="var\(--dna-surface\)"'
    )
    assert re.search(substrate_pattern, svg), (
        "rendered receipt substrate must use rx='5.5' ry='5.5' to match card border"
    )


def test_top_accent_strip_clips_to_card_shape() -> None:
    """The top accent strip must use ``clip-path="url(#receipt-card-shape)"``.

    The strip paints from x=0 to x=width with square corners. Without
    clipping it inherits the SVG's bounding rectangle, overflowing the
    rounded card on the top-left and top-right corners. Clipping to the
    receipt-card-shape forces its corners to round in match with the card.
    """
    body = _RECEIPT_TEMPLATE.read_text()
    assert "var(--dna-card-border-top)" in body, "Top accent strip must reference --dna-card-border-top"
    # The accent strip line must include clip-path attribute alongside the fill
    accent_pattern = r'fill="var\(--dna-card-border-top\)"[^/]*clip-path="url\(#receipt-card-shape\)"'
    assert re.search(accent_pattern, body), "Top accent strip must carry clip-path='url(#receipt-card-shape)'"


def test_glyph_partial_uses_glyph_css_vars() -> None:
    """provider-glyphs.svg.j2 must reference the glyph + inner-cutout tokens.

    Glyph tokens decouple brand-mark color from running text color (so
    claude-code's terra-coral asterisk doesn't get painted in dark brown
    just because that's the body-text ink).
    """
    body = _GLYPH_PARTIAL.read_text()
    for css_var in _GLYPH_PARTIAL_CSS_VARS:
        assert css_var in body, f"provider-glyphs.svg.j2 missing reference to {css_var}"


def test_provider_glyphs_use_glyph_fill_token() -> None:
    """Provider glyph paths must paint with --dna-glyph-fill, not ink-primary.

    The claude-code v9 specimen renders the Claude asterisk in terra-coral
    (#D97757), not in ink-primary (#1a1410). Earlier code coupled glyph
    color to running text color, which painted the brand mark in dark
    brown on cream paper — wrong per the specimen.
    """
    body = _GLYPH_PARTIAL.read_text()
    # claude-glyph + codex-glyph outer rounded-square both use --dna-glyph-fill
    assert body.count("var(--dna-glyph-fill)") >= 2, "Expected ≥2 --dna-glyph-fill references (claude + codex outer)"
    # codex-glyph inner cutout uses --dna-card-inner-glyph (typically surface)
    assert "var(--dna-card-inner-glyph)" in body, "Expected --dna-card-inner-glyph for codex inner cutout"


# --------------------------------------------------------------------------- #
# Genome JSON layer                                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("genome_id", _TELEMETRY_GENOMES)
def test_telemetry_genomes_carry_full_receipt_token_surface(genome_id: str) -> None:
    """All 3 telemetry genomes must declare every receipt token field.

    A missing token would force the assembler to skip emitting its CSS var,
    causing the template to inherit the cascade default — typically resulting
    in a hard-to-trace visual regression (e.g. a transparent rect that should
    have been visible). This test fails loud at JSON-load time.
    """
    genome = _load_genome(genome_id)
    missing = _RECEIPT_TOKEN_FIELDS - genome.keys()
    assert not missing, f"{genome_id} missing receipt tokens: {sorted(missing)}"


@pytest.mark.parametrize("genome_id", _TELEMETRY_GENOMES)
def test_telemetry_genome_pill_rx_is_integer(genome_id: str) -> None:
    """pill_rx must be an integer; the template uses it as an SVG ``rx=``
    attribute value, and JSON's number type must round-trip cleanly."""
    genome = _load_genome(genome_id)
    assert isinstance(genome["pill_rx"], int), (
        f"{genome_id}.pill_rx must be int, got {type(genome['pill_rx']).__name__}"
    )
    assert genome["pill_rx"] in {0, 4, 11}, f"{genome_id}.pill_rx must be 0/4/11 per spec; got {genome['pill_rx']}"


@pytest.mark.parametrize("genome_id", _TELEMETRY_GENOMES)
def test_telemetry_genome_treemap_accent_side_is_valid(genome_id: str) -> None:
    """treemap_accent_side must be 'top' or 'left'.

    These map to compute_treemap_layout's ``accent_position`` parameter
    which only handles those two values. A typo would silently degrade
    to top-rendering without erroring.
    """
    genome = _load_genome(genome_id)
    assert genome["treemap_accent_side"] in {"top", "left"}, (
        f"{genome_id}.treemap_accent_side must be 'top' or 'left'; got {genome['treemap_accent_side']!r}"
    )


# --------------------------------------------------------------------------- #
# Assembler layer                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("genome_id", _TELEMETRY_GENOMES)
def test_assembler_emits_all_receipt_css_vars(genome_id: str) -> None:
    """genome_to_css must emit all 10 receipt CSS vars for telemetry genomes.

    The assembler's value-truthiness loop (``if val:``) skips empty strings
    but emits ``"transparent"`` (a non-empty string) correctly. This is
    load-bearing: claude-code's pill_outer_bg=transparent must produce
    ``--dna-pill-outer-bg: transparent;`` in the CSS, not silently omit
    the rule.
    """
    genome = _load_genome(genome_id)
    css = genome_to_css(genome, frame_type="receipt")
    for css_var in _RECEIPT_CSS_VARS:
        assert f"{css_var}:" in css, f"{genome_id} CSS missing {css_var} (assembler did not emit)"


def test_assembler_emits_transparent_for_invisible_pill_outer() -> None:
    """claude-code's pill_outer_bg=transparent must emit a CSS rule, not be skipped.

    The ``"transparent"`` keyword IS the architectural pattern that lets a
    skin opt out of an element without a template conditional. If the
    assembler's truthiness check filtered it out, the CSS var would fall
    through to the cascade default and the rect could paint as black.
    """
    genome = _load_genome("telemetry-claude-code")
    css = genome_to_css(genome, frame_type="receipt")
    assert "--dna-pill-outer-bg: transparent;" in css
    assert "--dna-pill-outer-stroke: transparent;" in css
    assert "--dna-pill-rule-top: transparent;" in css
    assert "--dna-pill-rule-bottom: transparent;" in css


# --------------------------------------------------------------------------- #
# Treemap geometry layer                                                      #
# --------------------------------------------------------------------------- #


def _sample_tools() -> list[dict]:
    return [
        {"name": "Read", "tool_class": "explore", "total_tokens": 60_000, "count": 100},
        {"name": "Bash", "tool_class": "execute", "total_tokens": 20_000, "count": 50},
        {"name": "Edit", "tool_class": "mutate", "total_tokens": 15_000, "count": 25},
        {"name": "Glob", "tool_class": "explore", "total_tokens": 5_000, "count": 10},
    ]


def test_compute_treemap_layout_top_accent_geometry() -> None:
    """accent_position='top' yields full-width 1.5px-tall accent bars.

    Voltage and cream specimens both use top accents — the bar runs the
    full cell width as a 1.5px-tall stripe. Tier-1 cells span content_w,
    so accent_w should equal cell.w (752).
    """
    cells = compute_treemap_layout(_sample_tools(), accent_position="top")
    assert cells, "Expected non-empty treemap"
    tier1 = next(c for c in cells if c.tier == 1)
    assert tier1.accent_position == "top"
    assert tier1.accent_w == tier1.w, "Top accent width must equal cell width (full-row stripe)"
    assert tier1.accent_h == 1.5, "Top accent height must be 1.5px per risograph spec"


def test_compute_treemap_layout_left_accent_geometry() -> None:
    """accent_position='left' yields per-tier-width full-height accent bars.

    Claude-code v9 specimen uses left accents: 4px wide on tier-1, 3px
    on tier-2/3 (per _LEFT_ACCENT_W). The bar spans the full cell height,
    so accent_h should equal cell.h (88 for tier-1).
    """
    cells = compute_treemap_layout(_sample_tools(), accent_position="left")
    assert cells, "Expected non-empty treemap"
    tier1 = next(c for c in cells if c.tier == 1)
    assert tier1.accent_position == "left"
    assert tier1.accent_w == 4, "Tier-1 left accent width must be 4px per claude-code v9 spec"
    assert tier1.accent_h == float(tier1.h), "Left accent height must equal cell height (full-column stripe)"


def test_compute_treemap_layout_default_is_top() -> None:
    """The default accent_position must be 'top' to preserve risograph-canonical behavior.

    Two of three telemetry genomes (voltage, cream) want top accents. Making
    'top' the default means a future genome that omits ``treemap_accent_side``
    inherits the more common case rather than silently rendering empty
    accent stripes.
    """
    cells = compute_treemap_layout(_sample_tools())
    tier1 = next(c for c in cells if c.tier == 1)
    assert tier1.accent_position == "top"


# --------------------------------------------------------------------------- #
# Cross-skin contract                                                         #
# --------------------------------------------------------------------------- #


def test_three_skins_produce_distinct_pill_inner_bg() -> None:
    """The three telemetry skins must paint pills with three different colors.

    A regression where all skins inherit the same pill color (e.g. via a
    shared CSS fallback firing) would silently flatten the visual identity.
    This test asserts the genomes carry distinct values, even though the
    template path is identical.
    """
    inner_bgs = {genome_id: _load_genome(genome_id)["pill_inner_bg"] for genome_id in _TELEMETRY_GENOMES}
    assert len(set(inner_bgs.values())) == 3, f"All 3 skins must have distinct pill_inner_bg; got {inner_bgs}"


def test_pill_rx_normalized_to_square_across_skins() -> None:
    """All telemetry skins must use square pills (pill_rx=0).

    Design choice (post-v0.2.21 user feedback): cross-skin coherence beats
    per-specimen fidelity for the pill silhouette. The v9 claude-code mock
    used a full-pill (rx=11) chip-style anchor, but the form-language across
    the telemetry receipt family is the square pill from voltage / cream.
    The token stays in place so a future skin can opt back into rounded
    pills via JSON without code changes — but today, square is canonical.
    """
    for genome_id in _TELEMETRY_GENOMES:
        genome = _load_genome(genome_id)
        assert genome["pill_rx"] == 0, (
            f"{genome_id}.pill_rx must be 0 (square pill across all telemetry skins); got {genome['pill_rx']}"
        )


def test_treemap_accent_side_per_skin_matches_specimen() -> None:
    """treemap_accent_side must match the per-specimen accent direction:
    voltage=top (titanium spec), claude-code=left (v9 spec), cream=top (riso spec).

    A regression where this defaults across all skins would visually
    mis-render one of the three. Catches the regression where someone
    re-introduces a hardcoded ``if genome.id == ...`` check anywhere in the
    pipeline.
    """
    expected = {
        "telemetry-voltage": "top",
        "telemetry-claude-code": "left",
        "telemetry-cream": "top",
    }
    for genome_id, expected_side in expected.items():
        genome = _load_genome(genome_id)
        assert genome["treemap_accent_side"] == expected_side, (
            f"{genome_id}.treemap_accent_side must be {expected_side!r}; got {genome['treemap_accent_side']!r}"
        )


# --------------------------------------------------------------------------- #
# Card top-highlight token (glass edge) — regression guard                     #
# --------------------------------------------------------------------------- #
#
# v0.3.10 tokenized the receipt card top-highlight gradient but pointed it at
# --dna-ink-primary. ink is text tone (near-black on the light codex skin), so
# the intended white glass edge rendered as a dark grey wash band. The fix
# routes the highlight through its own surface-light role (--dna-card-top-
# highlight, sourced from card_top_highlight_color) and enforces the gate↔color
# pair at genome load. These tests pin both halves so the wash can't return.

_MINIMAL_TELEMETRY = {"session": {}, "profile": {}, "tools": {}, "stages": []}


def test_codex_receipt_top_highlight_uses_surface_token_not_ink() -> None:
    """The codex card top-highlight must source --dna-card-top-highlight, not ink.

    Renders a real codex receipt and asserts the highlight gradient block paints
    the surface-light token (white), with zero ``ink-primary`` reference inside
    it. A reference to ink anywhere in the ``receipt-card-top-highlight``
    linearGradient reintroduces the dark-wash regression.
    """
    svg = compose(ComposeSpec(type="receipt", genome_id="telemetry-codex", telemetry_data=_MINIMAL_TELEMETRY)).svg
    assert "--dna-card-top-highlight: #FFFFFF;" in svg, "codex CSS must emit the surface-light highlight token"
    block = re.search(r"receipt-card-top-highlight.*?</linearGradient>", svg, re.S)
    assert block is not None, "codex receipt must define the card top-highlight gradient"
    grad = block.group(0)
    assert "var(--dna-card-top-highlight)" in grad, "highlight stops must reference --dna-card-top-highlight"
    assert "ink-primary" not in grad, "ink must NOT leak into the highlight gradient (the dark-wash regression)"


def test_codex_genome_declares_highlight_color() -> None:
    """telemetry-codex must declare both the gate and its surface-light color."""
    genome = _load_genome("telemetry-codex")
    assert genome["card_top_highlight"] is True
    assert genome["card_top_highlight_color"] == "#FFFFFF", "codex glass edge must be white per v0.3.7 aesthetic"


def test_card_top_highlight_gate_requires_color_at_load() -> None:
    """A genome with the gate on but no color must fail loud at GenomeSpec load.

    This is the contract that prevents the regression class permanently: you
    cannot enable the highlight without supplying its color, so the gradient can
    never render an empty/undefined CSS var again.
    """
    raw = _load_genome("telemetry-codex")
    raw["card_top_highlight_color"] = ""  # blank the color, keep the gate True
    with pytest.raises(ValidationError, match="card_top_highlight_color"):
        GenomeSpec(**raw)
