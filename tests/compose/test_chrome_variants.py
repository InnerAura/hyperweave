"""Chrome 4-variant inline-style override emission (v0.3.0 PR 2).

Scope: chrome genome ships with 5 named variants (horizon/abyssal/lightning/
graphite/moth). Bare `chrome.static` URLs and `?variant=horizon` both resolve
to the frozen palette and emit NO inline style — preserving byte-equal output
against `tests/snapshots/url_stability/`. The 4 named overrides emit
`--dna-*:value;` declarations on the SVG root via `compute_variant_inline_style`.

Three independent invariants:
1. Override sparseness: chrome.json's `variant_overrides[name]` is a flat dict
   of genome-field keys, not an exhaustive palette. Only mentioned fields override.
2. Field→CSS-var translation: assembler's _ALL_CSS_MAPPING is the single source
   of truth. variant_overrides keys must be valid genome field names that map
   to a --dna-* property; unknown keys silently skip (validator catches typos
   at config-load time).
3. Whitelist enforcement: `?variant=` values not in `variants[]` raise
   ValueError at resolve-time (Path B grammar from v0.2.19).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hyperweave.compose.assembler import compute_variant_inline_style
from hyperweave.compose.resolver import resolve
from hyperweave.compose.validate_paradigms import validate_genome_variants
from hyperweave.config.loader import load_genomes
from hyperweave.config.registry import get_genomes
from hyperweave.core.models import ComposeSpec

if TYPE_CHECKING:
    from hyperweave.core.schema import GenomeSpec


def _chrome_genome() -> dict:
    """Return chrome.json contents as a dict (the resolver-facing shape).

    get_genomes() returns the dict-shaped registry; load_genomes() returns
    the GenomeSpec-typed registry. Tests targeting raw genome data use the
    former; tests targeting Pydantic invariants use the latter.
    """
    return get_genomes()["chrome"]


def _chrome_spec() -> GenomeSpec:
    """Return chrome.json as a typed GenomeSpec for Pydantic-level assertions."""
    return load_genomes()["chrome"]


# ── Inline-style emission ────────────────────────────────────────────


def test_bare_chrome_emits_no_inline_style() -> None:
    """`chrome.static` (no ?variant=) must emit zero inline-style declarations.

    The bare URL is a stability contract — one organic external user has it
    embedded 12+ times across their README. Adding any inline-style attribute
    breaks the byte-equal snapshot at `tests/snapshots/url_stability/`.
    """
    genome = _chrome_genome()
    # No resolved variant → empty inline style → conditional in document.svg.j2
    # suppresses the style attribute entirely.
    assert compute_variant_inline_style(genome, "") == ""


def test_horizon_alias_emits_no_inline_style() -> None:
    """`?variant=horizon` is the named alias for the bare palette.

    horizon is in genome.variants[] (so it passes the whitelist) but has NO
    entry in variant_overrides. That's the architectural promise: bare and
    horizon both resolve to the same byte output.
    """
    genome = _chrome_genome()
    assert compute_variant_inline_style(genome, "horizon") == ""


@pytest.mark.parametrize(
    "variant,expected_signal",
    [
        ("abyssal", "#38D8C0"),
        ("lightning", "#88A8FF"),
        ("graphite", "#B8B0A8"),
        ("moth", "#B89878"),
    ],
)
def test_named_variants_emit_dna_signal_override(variant: str, expected_signal: str) -> None:
    """Each of the 4 named variants emits at least its `accent` override as `--dna-signal`.

    Production HTML pattern: each variant's distinctive accent color is the
    primary chromatic identity carrier. Verifying signal alone is sufficient
    to prove the override mechanism works end-to-end without coupling the
    test to every field in the override dict (which would be brittle).
    """
    genome = _chrome_genome()
    style = compute_variant_inline_style(genome, variant)
    assert f"--dna-signal:{expected_signal};" in style


@pytest.mark.parametrize(
    "variant,expected_surface",
    [
        ("abyssal", "#020E12"),
        ("lightning", "#080418"),
        ("graphite", "#0E0C0A"),
        ("moth", "#0E0808"),
    ],
)
def test_named_variants_emit_dna_surface_override(variant: str, expected_surface: str) -> None:
    """Each named variant emits its `surface_0` override as `--dna-surface`.

    Surface is the dominant background color and must come through every
    override — visual identity falls apart if surface stays at chrome's base
    `#000A14` while signal jumps to abyssal's teal.
    """
    genome = _chrome_genome()
    style = compute_variant_inline_style(genome, variant)
    assert f"--dna-surface:{expected_surface};" in style


def test_compute_variant_inline_style_escapes_quote() -> None:
    """Inline style must escape `"` to prevent attribute-injection.

    A malicious genome JSON could attempt `"surface_0": "red\\"; foo:bar"`
    to break out of the style="..." attribute boundary. Escaping defangs it.
    """
    poisoned_genome: dict = {
        "variants": ["evil"],
        "variant_overrides": {"evil": {"surface_0": 'normal"; foo:bar'}},
    }
    style = compute_variant_inline_style(poisoned_genome, "evil")
    assert '"' not in style
    assert "&quot;" in style


def test_compute_variant_inline_style_escapes_lt_gt() -> None:
    """`<` and `>` are also escaped — they could close the SVG element early."""
    poisoned_genome: dict = {
        "variants": ["evil"],
        "variant_overrides": {"evil": {"surface_0": "<script>"}},
    }
    style = compute_variant_inline_style(poisoned_genome, "evil")
    assert "<" not in style
    assert ">" not in style
    assert "&lt;" in style
    assert "&gt;" in style


def test_unknown_field_in_overrides_silently_skips() -> None:
    """Fields not in _ALL_CSS_MAPPING produce no declaration (no crash)."""
    genome: dict = {
        "variants": ["weird"],
        "variant_overrides": {"weird": {"not_a_real_field": "#FF0000", "surface_0": "#0000FF"}},
    }
    style = compute_variant_inline_style(genome, "weird")
    # Real field translates; bogus field is ignored.
    assert "--dna-surface:#0000FF;" in style
    assert "not_a_real_field" not in style


# ── Resolver whitelist enforcement ───────────────────────────────────


@pytest.mark.parametrize("variant", ["horizon", "abyssal", "lightning", "graphite", "moth"])
def test_chrome_variants_pass_whitelist(variant: str) -> None:
    """All 5 declared variants resolve cleanly via the dispatcher."""
    spec = ComposeSpec(type="badge", genome_id="chrome", variant=variant)
    result = resolve(spec)
    assert result.resolved_variant == variant


@pytest.mark.parametrize("variant", ["nightfall", "AURORA", "horizon ", " moth", "violet-teal"])
def test_chrome_unknown_variants_raise_value_error(variant: str) -> None:
    """Unknown variants raise ValueError from resolve_variant's whitelist."""
    spec = ComposeSpec(type="badge", genome_id="chrome", variant=variant)
    with pytest.raises(ValueError) as exc_info:
        resolve(spec)
    assert "variant" in str(exc_info.value).lower()


# ── End-to-end: ResolvedArtifact carries inline_style ────────────────


def test_bare_chrome_resolved_artifact_has_empty_inline_style() -> None:
    """ResolvedArtifact.inline_style_overrides is empty for bare URLs."""
    spec = ComposeSpec(type="badge", genome_id="chrome", variant="")
    result = resolve(spec)
    assert result.resolved_variant == ""
    assert result.inline_style_overrides == ""


def test_chrome_moth_resolved_artifact_carries_inline_style() -> None:
    """`?variant=moth` produces a ResolvedArtifact with non-empty overrides."""
    spec = ComposeSpec(type="badge", genome_id="chrome", variant="moth")
    result = resolve(spec)
    assert result.resolved_variant == "moth"
    assert "--dna-surface:#0E0808;" in result.inline_style_overrides
    assert "--dna-signal:#B89878;" in result.inline_style_overrides


# ── Validator: variant_overrides keys ⊆ variants[] ────────────────────


def test_validate_genome_variants_rejects_overrides_outside_whitelist() -> None:
    """Override keys not present in variants[] are config errors.

    Use model_copy(update=...) on the real chrome spec rather than constructing
    a fresh GenomeSpec with all 50+ required fields — keeps the test focused
    on variant grammar, not schema completeness.
    """
    bad = _chrome_spec().model_copy(
        update={
            "variants": ["horizon", "abyssal"],
            "variant_overrides": {
                "abyssal": {"surface_0": "#020E12"},
                "stray": {"surface_0": "#000000"},  # NOT in variants[]
            },
        }
    )
    with pytest.raises(ValueError) as exc_info:
        validate_genome_variants(bad)
    msg = str(exc_info.value)
    assert "stray" in msg
    assert "variant_overrides" in msg


def test_validate_genome_variants_accepts_subset_overrides() -> None:
    """Sparse overrides (subset of variants[]) are valid — horizon being absent
    is the canonical no-op pattern."""
    good = _chrome_spec().model_copy(
        update={
            "variants": ["horizon", "moth"],
            "variant_overrides": {"moth": {"surface_0": "#0E0808"}},
        }
    )
    validate_genome_variants(good)  # no raise


def test_validate_genome_variants_accepts_real_chrome() -> None:
    """The actual chrome.json passes the validator end-to-end."""
    validate_genome_variants(_chrome_spec())  # no raise


# ── Regression: state_passing_core reconciliation ───────────────────


def test_chrome_state_passing_core_aligned_with_accent_signal() -> None:
    """v0.3.0 reconciliation: chrome.state_passing_core matches accent_signal.

    Pre-v0.3.0 had divergent values (#34D399 vs #22C55E). The threshold-CSS
    state machine and the accent-signal status indicator were emitting
    different shades of green for the same passing state — a UI inconsistency
    visible in stateful badges. Aligning to #22C55E (matching production HTML
    + accent_signal) collapses both into one perceptual green.
    """
    chrome = _chrome_spec()
    assert chrome.state_passing_core == "#22C55E"
    assert chrome.accent_signal == "#22C55E"
    # The bright (lighter) variant is intentionally different — used for
    # value-text contrast against the bezel, not for the signal indicator.
    assert chrome.state_passing_bright == "#A7F3D0"


# ── Specimen fidelity: variant envelopes match production HTML ─────


# (variant, expected_first_stop, expected_last_stop) — extracted from
# tier2/genomes/chrome/hw-chrome-horizon-production-set.html env linearGradients.
# abyssal: lines 147,157; lightning: 417,427; graphite: 687,697; moth: 957,967.
_VARIANT_SPECIMEN_ENVELOPES = [
    ("abyssal", "#00080F", "#000204"),
    ("lightning", "#050218", "#02020A"),
    ("graphite", "#1A1818", "#080604"),
    ("moth", "#0A0508", "#050202"),
]


@pytest.mark.parametrize("variant,first_stop,last_stop", _VARIANT_SPECIMEN_ENVELOPES)
def test_chrome_variant_envelope_matches_specimen(variant: str, first_stop: str, last_stop: str) -> None:
    """Each chrome variant's envelope_stops MUST be 11 stops with first + last
    colors matching the production HTML specimen byte-for-byte.

    Pre-v0.3.0 hardening these were 5-stop fabrications that didn't match the
    HTML's authored gradients. Specimen extraction at Issue 3 replaced them
    with the 11-stop authored sequences from
    tier2/genomes/chrome/hw-chrome-horizon-production-set.html.
    """
    overrides = _chrome_genome().get("variant_overrides", {}).get(variant, {})
    stops = overrides.get("envelope_stops", [])
    assert len(stops) == 11, f"{variant}: expected 11 stops, got {len(stops)}"
    assert stops[0]["color"] == first_stop, f"{variant} first stop mismatch"
    assert stops[-1]["color"] == last_stop, f"{variant} last stop mismatch"


@pytest.mark.parametrize("variant", ["abyssal", "lightning", "graphite", "moth"])
def test_chrome_variant_glyph_inner_matches_ink_secondary(variant: str) -> None:
    """Glyph fill for each variant should be the variant's `ink_secondary` (the
    muted/softer tone), NOT `ink` (the bright tone). The bright tone reads as a
    stark white sticker pasted on the badge surface; ink_secondary keeps the
    glyph in the variant's tonal range so it feels like part of the label-zone
    typography. Mirrors automata bone/steel (warm gray glyph on warm gray badge)
    — chrome v0.3.0 hardening adopts the same rule.
    """
    overrides = _chrome_genome().get("variant_overrides", {}).get(variant, {})
    assert overrides.get("glyph_inner") == overrides.get("ink_secondary"), (
        f"{variant}: glyph_inner ({overrides.get('glyph_inner')}) "
        f"should equal ink_secondary ({overrides.get('ink_secondary')})"
    )
