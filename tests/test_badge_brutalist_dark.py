"""Per-variant chromatic, geometric, and var-routing pins for brutalist dark badges.

Asserts every of the six dark-substrate variants (celadon, carbon, alloy,
temper, pigment, ember) emits the prototype-derived hex values AND that the
badge template routes each visual role through the correct semantic CSS var.

v0.3.3 field hierarchy (post badge regression remediation):

  * Left panel  → var(--dna-brand-panel-fill) ← brand_panel_fill JSON field
                  (badge/strip-semantic; ELEVATED panel tone)
  * Right panel → var(--dna-surface)          ← surface_0 JSON field
                  (genome-wide CANVAS/ground; same value strip/stats use)
  * Label fill  → var(--dna-ink-primary)      ← ink JSON field
                  (badge cream; --dna-label-text holds muted strip tone)
  * Accent bar  → var(--dna-signal)           ← accent JSON field
  * Separator   → var(--hw-state-sep, var(--dna-signal))
                  (state-tinted; passing=accent, warn=accent_warning, fail=accent_error)
  * Seam gap    → var(--dna-seam-gap, var(--dna-surface)) when seam_w > 0
                  (fills the geometric gap so transparent doesn't leak
                  page-background through in cross-platform renderers)
  * Indicator   → 10x10 outer + 6x6 inner bit at offset 2, stroke-width 1.5
                  (--dna-status-color for the bit, paradigm-supplied geometry)

Source: tier2/genomes/brutalist/brutalist-v03/hw-elegant-mono-badge-matrix-v16.html
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

# Element contract — every dark variant must match these prototype values
# at the chromatic + geometric layer. ember has no prototype counterpart in
# the v16 matrix; its values follow the same warm-gold ramp pattern.
PROTOTYPE_VARIANTS: list[dict[str, str]] = [
    {
        "variant": "celadon",
        "canvas": "#06140c",  # surface_0 = right panel = strip/stats canvas
        "elevated": "#102818",  # brand_panel_fill = left panel
        "signal": "#48a870",  # accent bar + passing separator
        "ink_primary": "#d8f0e0",  # badge label cream (=ink)
        "label_text": "#308858",  # muted strip label (NOT used by badge)
        "badge_value_text": "#78c898",  # mid chassis (=ink_secondary)
        "pass_bit": "#68b888",  # passing inner bit (=accent_signal)
        "warn_sep": "#c8a028",
        "fail_sep": "#e05040",
    },
    {
        "variant": "carbon",
        "canvas": "#0e0c12",
        "elevated": "#222028",
        "signal": "#6e6888",
        "ink_primary": "#d8d4e0",
        "label_text": "#4a4460",
        "badge_value_text": "#a098b8",
        "pass_bit": "#9088a8",
        "warn_sep": "#c8a028",
        "fail_sep": "#d84848",
    },
    {
        "variant": "alloy",
        "canvas": "#040c16",
        "elevated": "#0e2030",
        "signal": "#3888b8",
        "ink_primary": "#d0e0f0",
        "label_text": "#206888",
        "badge_value_text": "#68b0d8",
        "pass_bit": "#58a8d0",
        "warn_sep": "#c8a020",
        "fail_sep": "#e04840",
    },
    {
        "variant": "temper",
        "canvas": "#10100a",
        "elevated": "#242018",
        "signal": "#988870",
        "ink_primary": "#e8e0d0",
        "label_text": "#686050",
        "badge_value_text": "#c0b098",
        "pass_bit": "#b0a088",
        "warn_sep": "#c0a028",
        "fail_sep": "#d84838",
    },
    {
        "variant": "pigment",
        "canvas": "#120c16",
        "elevated": "#241828",
        "signal": "#9860a0",
        "ink_primary": "#f0e8f0",
        "label_text": "#784880",
        "badge_value_text": "#c090c8",
        "pass_bit": "#b080b8",
        "warn_sep": "#c8a020",
        "fail_sep": "#e04858",
    },
    {
        "variant": "ember",
        "canvas": "#121004",
        "elevated": "#282010",
        "signal": "#c0a050",
        "ink_primary": "#f0e8d0",
        "label_text": "#807030",
        "badge_value_text": "#e0c878",
        "pass_bit": "#d8b868",
        "warn_sep": "#c8a020",
        "fail_sep": "#e04840",
    },
]

_HEX_LINE = re.compile(r"--dna-([a-z-]+):\s*(#[0-9a-fA-F]+|[^;]+);")


def _extract_dna_vars(svg: str) -> dict[str, str]:
    """Map every --dna-* declaration in the genome CSS block + the SVG-root
    inline style to its resolved value. Lowercased so prototype hex
    assertions are case-insensitive. Last-seen value wins (inline overrides
    genome CSS block, matching cascade order)."""
    out: dict[str, str] = {}
    for match in _HEX_LINE.finditer(svg):
        key = match.group(1).lower()
        value = match.group(2).strip().lower()
        out[key] = value
    return out


@pytest.mark.parametrize("spec", PROTOTYPE_VARIANTS, ids=lambda s: s["variant"])
def test_dark_variant_chromatics(spec: dict[str, str]) -> None:
    """Every dark variant emits the full prototype-matched palette through
    its CSS vars. --dna-surface carries the CANVAS (right panel + strip/stats
    background); --dna-brand-panel-fill carries the ELEVATED panel (badge
    left). Decoupling these two prevents the v0.3.2→v0.3.3 regression where
    the badge fix repurposed surface_0 and broke strip/stats canvas."""
    result = compose(
        ComposeSpec(
            type="badge",
            genome_id="brutalist",
            variant=spec["variant"],
            title="BUILD",
            value="passing",
            state="passing",
        )
    )
    dna = _extract_dna_vars(result.svg)
    assert dna.get("surface") == spec["canvas"], (
        f"{spec['variant']}: --dna-surface (CANVAS, also strip/stats ground) "
        f"expected {spec['canvas']}, got {dna.get('surface')}"
    )
    assert dna.get("brand-panel-fill") == spec["elevated"], (
        f"{spec['variant']}: --dna-brand-panel-fill (ELEVATED, badge left panel) "
        f"expected {spec['elevated']}, got {dna.get('brand-panel-fill')}"
    )
    assert dna.get("signal") == spec["signal"], (
        f"{spec['variant']}: --dna-signal expected {spec['signal']}, got {dna.get('signal')}"
    )
    assert dna.get("ink-primary") == spec["ink_primary"], (
        f"{spec['variant']}: --dna-ink-primary (BADGE label cream) "
        f"expected {spec['ink_primary']}, got {dna.get('ink-primary')}"
    )
    assert dna.get("label-text") == spec["label_text"], (
        f"{spec['variant']}: --dna-label-text (STRIP muted label, distinct from badge cream) "
        f"expected {spec['label_text']}, got {dna.get('label-text')}"
    )
    got_value = dna.get("badge-value-text")
    assert got_value == spec["badge_value_text"], (
        f"{spec['variant']}: --dna-badge-value-text expected mid-chassis {spec['badge_value_text']}, got {got_value}"
    )
    got_bit = dna.get("badge-pass-core")
    assert got_bit == spec["pass_bit"], (
        f"{spec['variant']}: --dna-badge-pass-core (passing inner bit) expected {spec['pass_bit']}, got {got_bit}"
    )
    got_warn = dna.get("status-warning-core")
    assert got_warn == spec["warn_sep"], (
        f"{spec['variant']}: --dna-status-warning-core expected {spec['warn_sep']}, got {got_warn}"
    )
    got_fail = dna.get("status-failing-core")
    assert got_fail == spec["fail_sep"], (
        f"{spec['variant']}: --dna-status-failing-core expected {spec['fail_sep']}, got {got_fail}"
    )


@pytest.mark.parametrize("variant", [v["variant"] for v in PROTOTYPE_VARIANTS])
def test_dark_variant_panel_routing(variant: str) -> None:
    """Badge template routes left panel through --dna-brand-panel-fill and
    right panel through --dna-surface (decoupled from surface_0/surface_2
    swap that the v0.3.3 badge regression introduced)."""
    result = compose(
        ComposeSpec(
            type="badge",
            genome_id="brutalist",
            variant=variant,
            title="BUILD",
            value="passing",
            state="passing",
        )
    )
    assert 'fill="var(--dna-brand-panel-fill)"' in result.svg, (
        f"{variant}: badge left panel must reference var(--dna-brand-panel-fill), not --dna-surface "
        f"(decoupling preserves strip/stats canvas integrity)"
    )
    # The right panel is the FIRST surface reference in the badge body's clip group.
    # Match the exact attribute signature so we don't false-positive on CSS-var
    # fallbacks elsewhere in the genome CSS block.
    assert re.search(r'<rect x="\d+" width="\d+" height="\d+" fill="var\(--dna-surface\)"', result.svg), (
        f"{variant}: badge right panel must reference var(--dna-surface) (canvas/ground tone)"
    )


@pytest.mark.parametrize("variant", [v["variant"] for v in PROTOTYPE_VARIANTS])
def test_dark_variant_label_routing(variant: str) -> None:
    """Badge label routes through --dna-ink-primary (cream tier), NOT
    --dna-label-text (which carries the strip's muted accent tone). This
    decoupling is what allows celadon's badge label to render cream while
    celadon's strip metric labels render muted dark green from the same
    genome palette."""
    result = compose(
        ComposeSpec(
            type="badge",
            genome_id="brutalist",
            variant=variant,
            title="BUILD",
            value="passing",
            state="passing",
        )
    )
    assert 'fill="var(--dna-ink-primary)"' in result.svg, (
        f"{variant}: badge label must reference var(--dna-ink-primary) for cream-tier rendering"
    )


@pytest.mark.parametrize("variant", [v["variant"] for v in PROTOTYPE_VARIANTS])
def test_dark_variant_seam_gap_present(variant: str) -> None:
    """Badge restores the seam_gap rect (when resolver computes seam_w > 0) so
    the geometric region between separator and right panel renders as a solid
    fill rather than transparent. Without this rect the gap shows the host
    page background through (white in light Markdown, dark in dark Markdown) —
    a cross-platform rendering bug we hit in v0.3.3 pre-remediation."""
    result = compose(
        ComposeSpec(
            type="badge",
            genome_id="brutalist",
            variant=variant,
            title="BUILD",
            value="passing",
            state="passing",
        )
    )
    assert 'fill="var(--dna-seam-gap, var(--dna-surface))"' in result.svg, (
        f"{variant}: badge must render the seam-gap rect with "
        f"fill=var(--dna-seam-gap, var(--dna-surface)) to fill the geometric gap "
        f"and prevent host-page-background bleed-through"
    )


@pytest.mark.parametrize("variant", [v["variant"] for v in PROTOTYPE_VARIANTS])
def test_dark_variant_no_perimeter_stroke(variant: str) -> None:
    """v0.3.3: dark badges drop the half-pixel perimeter stroke the v0.3.2
    template inherited from the light substrate. The prototype's flat-plate
    aesthetic uses panel + ground surface contrast as the only edge cue."""
    result = compose(
        ComposeSpec(
            type="badge",
            genome_id="brutalist",
            variant=variant,
            title="BUILD",
            value="passing",
            state="passing",
        )
    )
    assert 'x=".5" y=".5"' not in result.svg, (
        f"{variant}: dark badge must not render the perimeter stroke rect (prototype has none)"
    )


@pytest.mark.parametrize("variant", [v["variant"] for v in PROTOTYPE_VARIANTS])
def test_dark_variant_indicator_geometry(variant: str) -> None:
    """Indicator: 10x10 outer ring, 6x6 inner bit at offset 2, stroke-width
    1.5 — matches the v16 prototype's translate(138,5) → 10x10 + 6x6 bit."""
    result = compose(
        ComposeSpec(
            type="badge",
            genome_id="brutalist",
            variant=variant,
            title="BUILD",
            value="passing",
            state="passing",
        )
    )
    assert 'stroke-width="1.5" width="10" height="10"' in result.svg, (
        f"{variant}: indicator outer ring must be 10x10 with stroke-width 1.5"
    )
    assert 'width="6" height="6"' in result.svg, f"{variant}: indicator inner bit must be 6x6 (paradigm ratio 0.6)"


@pytest.mark.parametrize("variant", [v["variant"] for v in PROTOTYPE_VARIANTS])
def test_dark_variant_typography(variant: str) -> None:
    """Label + value typography: both weight 700, label tracking 0.06em,
    value tracking 0.04em (prototype reserves the tighter 0.04em for the
    lowercase state word)."""
    result = compose(
        ComposeSpec(
            type="badge",
            genome_id="brutalist",
            variant=variant,
            title="BUILD",
            value="passing",
            state="passing",
        )
    )
    assert 'font-weight="700"\n      fill="var(--dna-ink-primary)"\n      letter-spacing="0.06em"' in result.svg, (
        f"{variant}: label must be weight 700, fill=--dna-ink-primary, letter-spacing 0.06em"
    )
    assert 'letter-spacing="0.04em"' in result.svg, f"{variant}: value text must declare letter-spacing 0.04em"


def test_dark_variants_byte_distinct() -> None:
    """Every pair of dark variants must produce DIFFERENT SVG output. The
    pre-fix carbon/temper/etc. all rendered with the same base-genome
    label_text/badge_value_text — the variant identity got swallowed.
    Asserting pairwise distinctness catches a regression where a future
    refactor collapses variant overrides back to the base."""
    variants = [v["variant"] for v in PROTOTYPE_VARIANTS]
    svgs: dict[str, str] = {}
    for v in variants:
        svgs[v] = compose(
            ComposeSpec(
                type="badge",
                genome_id="brutalist",
                variant=v,
                title="BUILD",
                value="passing",
                state="passing",
            )
        ).svg
    seen: dict[str, str] = {}
    for v, svg in svgs.items():
        canonical = re.sub(r"hw-[0-9a-f]+", "hw-UID", svg)
        prior = seen.get(canonical)
        assert prior is None, f"variant {v} renders byte-identical to {prior} after uid canonicalization"
        seen[canonical] = v
