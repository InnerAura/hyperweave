"""automata genome — Phase 1 scaffolding validation.

Scope: load the JSON, validate field shape, profile routing, state-palette
fields, and bifamily chromatic fields. Paradigm dispatch is NOT exercised
here (cellular.yaml doesn't exist until Phase 3); validation silently skips
the unknown 'cellular' paradigm slug per validate_paradigms.py:49-50.
"""

from __future__ import annotations

from hyperweave.compose.validate_paradigms import validate_genome_against_paradigms
from hyperweave.config.registry import get_genome_specs, get_paradigms, reset_registry
from hyperweave.core.enums import GenomeId, ProfileId
from hyperweave.core.models import _GENOME_PROFILE_MAP


def test_automata_genome_id_enum_present() -> None:
    """GenomeId.AUTOMATA is registered and maps to brutalist profile."""
    assert GenomeId.AUTOMATA == "automata"
    assert _GENOME_PROFILE_MAP[GenomeId.AUTOMATA] == ProfileId.BRUTALIST


def test_automata_genome_loads() -> None:
    """data/genomes/automata.json loads as a valid GenomeSpec."""
    reset_registry()
    genomes = get_genome_specs()
    assert "automata" in genomes, "automata.json not discovered by ConfigLoader"
    spec = genomes["automata"]
    assert spec.id == "automata"
    assert spec.name == "Automata"
    assert spec.category == "dark"
    assert spec.profile == "brutalist"


def test_automata_bifamily_chromatic_fields_populated() -> None:
    """Both blue and purple families declare a complete palette."""
    spec = get_genome_specs()["automata"]
    # Blue family
    assert len(spec.variant_blue_rim_stops) == 7
    assert len(spec.variant_blue_pattern_cells) == 3
    assert spec.variant_blue_label_slab_fill == "#0A1C28"
    assert spec.variant_blue_value_text == "#A8D4F0"
    # Purple family
    assert len(spec.variant_purple_rim_stops) == 7
    assert len(spec.variant_purple_pattern_cells) == 3
    assert spec.variant_purple_label_slab_fill == "#150A22"
    assert spec.variant_purple_value_text == "#D8B4FE"
    # Bifamily bridge (divider palette)
    assert spec.variant_bifamily_bridge_teal_mid == "#147A90"
    assert spec.variant_bifamily_bridge_amethyst_core == "#5A3278"
    # Pulse config
    assert spec.cellular_pulse_base_duration == "6s"
    assert spec.cellular_pattern_opacity == "0.78"


def test_state_palette_backfilled_across_shipped_genomes() -> None:
    """Every shipped genome now carries a full 5-pair state palette."""
    genomes = get_genome_specs()
    for slug in (
        "automata",
        "brutalist",
        "chrome",
        "telemetry-voltage",
        "telemetry-claude-code",
        "telemetry-cream",
    ):
        spec = genomes[slug]
        assert spec.state_passing_core, f"{slug} missing state_passing_core"
        assert spec.state_passing_bright, f"{slug} missing state_passing_bright"
        assert spec.state_warning_core, f"{slug} missing state_warning_core"
        assert spec.state_critical_core, f"{slug} missing state_critical_core"
        assert spec.state_building_core, f"{slug} missing state_building_core"
        assert spec.state_offline_core, f"{slug} missing state_offline_core"


def test_automata_paradigm_validation_passes_with_unknown_cellular() -> None:
    """Phase 1: cellular.yaml doesn't exist yet; validator silently skips
    unknown paradigm slugs and falls through to default at render time."""
    reset_registry()
    paradigms = get_paradigms()
    spec = get_genome_specs()["automata"]
    # Should NOT raise: unknown 'cellular' slugs in paradigms dict are skipped.
    validate_genome_against_paradigms(spec, paradigms)


def test_every_shipped_genome_still_passes_validation_after_backfill() -> None:
    """Regression: backfilling state-palette fields must not break validation
    for brutalist/chrome/telemetry-voltage and the new telemetry-claude-code
    and telemetry-cream skins."""
    paradigms = get_paradigms()
    for genome in get_genome_specs().values():
        validate_genome_against_paradigms(genome, paradigms)
