"""ComposeSpec.variant field — Path B grammar (v0.2.19).

Scope: ComposeSpec accepts any string at construction time (no Pydantic
field_validator). Validation moves to resolve-time and is driven by the
genome's `variants` whitelist (declared in genome JSON). This locks both
contracts: the lenient model boundary AND the strict resolve-time check.
"""

from __future__ import annotations

import pytest

from hyperweave.compose.resolver import resolve
from hyperweave.core.models import ComposeSpec


def test_variant_defaults_to_empty() -> None:
    """Empty default = 'frame-type default, resolved by paradigm/genome'."""
    spec = ComposeSpec(type="badge")
    assert spec.variant == ""


@pytest.mark.parametrize(
    "value",
    [
        "",
        # v0.3.0 automata: 16 production solo tones. Pairing is a URL grammar
        # modifier (?pair=...) that composes any two solo tones at request time;
        # see pair grammar tests below for paired-mode coverage.
        "violet",
        "teal",
        "bone",
        "steel",
        "amber",
        "jade",
        "magenta",
        "cobalt",
        "toxic",
        "solar",
        "abyssal",
        "crimson",
        "sulfur",
        "indigo",
        "burgundy",
        "copper",
    ],
)
def test_variant_accepts_automata_allowed_values(value: str) -> None:
    """Automata's v0.3.0 variants list — 16 solo tones."""
    spec = ComposeSpec(type="badge", genome_id="automata", variant=value)
    resolved = resolve(spec)
    # Empty resolves to paradigm default (teal); non-empty passes whitelist.
    expected = value or "teal"
    assert resolved.frame_context.get("variant", "") == expected


@pytest.mark.parametrize(
    "value",
    [
        # Legacy v0.2 slugs (clean delete, no shim)
        "blue",
        "purple",
        "bifamily",
        # Naming-convention violations (compound solo tones)
        "phosphor-green",
        "crt-green",
        # Casing mismatches
        "VIOLET",
        "Teal",
        # Unrelated tones (not in the v0.3.0 16-tone production set).
        "ruby",
        "phosphor",
    ],
)
def test_variant_rejects_unknown_values_at_resolve_time(value: str) -> None:
    """Path B: validation is resolve-time against genome.variants, not Pydantic."""
    spec = ComposeSpec(type="badge", genome_id="automata", variant=value)
    # Construction succeeds (lenient field). Resolve-time raises.
    with pytest.raises(ValueError) as exc_info:
        resolve(spec)
    assert "variant" in str(exc_info.value)


def test_variant_accepts_anything_when_genome_has_no_variants_axis() -> None:
    """Genomes with empty `variants` list accept variant='' only (no axis)."""
    # brutalist has variants=[]; passing variant="" is fine
    spec = ComposeSpec(type="badge", genome_id="brutalist", variant="")
    resolve(spec)  # no error


# v0.3.0 pairing grammar modifier: ?variant=primary&pair=secondary composes
# any two solo tones. Bifamily frames (strip, divider) consume the pair;
# other frames silently ignore it. Pair is automata-only — non-automata
# genomes get the param dropped without error.


def test_pair_grammar_paired_strip_resolves_with_secondary_tone() -> None:
    """Strip with ?variant=teal&pair=violet produces a paired cellular palette."""
    spec = ComposeSpec(type="strip", genome_id="automata", title="REPO", value="A:1", variant="teal", pair="violet")
    resolved = resolve(spec)
    cp = resolved.frame_context.get("cellular_palette") or {}
    assert cp.get("is_paired") is True
    assert cp["primary"]["seam_mid"] == "#3A9FB8"  # teal
    assert cp["secondary"]["seam_mid"] == "#A88AD4"  # violet


def test_pair_grammar_solo_strip_mirrors_primary_into_secondary() -> None:
    """Strip with ?variant=teal (no pair) renders solo: secondary mirrors primary."""
    spec = ComposeSpec(type="strip", genome_id="automata", title="REPO", value="A:1", variant="teal")
    resolved = resolve(spec)
    cp = resolved.frame_context.get("cellular_palette") or {}
    assert cp.get("is_paired") is False
    assert cp["primary"]["seam_mid"] == cp["secondary"]["seam_mid"] == "#3A9FB8"


def test_pair_grammar_silently_ignored_on_non_automata_genomes() -> None:
    """?pair=teal on chrome genome composes successfully — pair is dropped."""
    # Chrome has no variant_tones, so the palette resolver returns the empty
    # palette early and never inspects pair. No error, no warning.
    spec = ComposeSpec(type="badge", genome_id="chrome", variant="horizon", pair="teal")
    resolve(spec)  # no error


def test_pair_grammar_invalid_pair_raises() -> None:
    """?variant=teal&pair=nonexistent raises against the variant_tones whitelist."""
    spec = ComposeSpec(type="strip", genome_id="automata", title="X", value="A:1", variant="teal", pair="nonexistent")
    with pytest.raises(ValueError) as exc_info:
        resolve(spec)
    assert "pair" in str(exc_info.value)


def test_pair_grammar_defaults_to_empty() -> None:
    """ComposeSpec.pair defaults to empty when not specified."""
    spec = ComposeSpec(type="badge")
    assert spec.pair == ""
