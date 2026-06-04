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


def test_automata_compositional_tones_populated() -> None:
    """v0.3.0: variant_tones declares 16 tone primitives, each with all 14 fields.
    Pairing happens at request time via the URL grammar modifier
    ?variant=primary&pair=secondary, which composes any two solo tones; bridge
    synthesis happens in compose/palette.py from each tone's cellular_cells[0:2].

    The 14-field shape is the original 11-field shape plus the three accent
    stops (info_accent / mid_accent / header_band) added for the v0.3.0 visual
    refresh — info_accent is the saturated brand-bright stop, mid_accent the
    70%-saturated mid stop, header_band the dark mid-band tone."""
    spec = get_genome_specs()["automata"]
    # 16 production tones.
    assert set(spec.variant_tones.keys()) == {
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
    }
    # Each tone has the full 14-field shape: area_tiers (5, brightest→darkest)
    # for stat card heatmap + chart_levels (6, darkest→brightest) for chart
    # cellular automata + dormant_range (2, low+high near-black) for chart
    # dormant substrate + the three accent stops (info_accent / mid_accent /
    # header_band) driving the new stat-card outline, chart header zone,
    # marquee hairlines, and icon mid-tier cells.
    for tone_name, tone in spec.variant_tones.items():
        assert set(tone.keys()) == {
            "rim_stops",
            "cellular_cells",
            "area_tiers",
            "chart_levels",
            "dormant_range",
            "label_slab",
            "seam_mid",
            "label_text",
            "value_text",
            "canvas_top",
            "canvas_bottom",
            "info_accent",
            "mid_accent",
            "header_band",
        }, f"variant_tones['{tone_name}'] shape mismatch"
        assert len(tone["rim_stops"]) == 7
        assert len(tone["cellular_cells"]) == 3
        assert len(tone["area_tiers"]) == 5, f"{tone_name} area_tiers must be 5 colors brightest→darkest"
        assert len(tone["chart_levels"]) == 6, f"{tone_name} chart_levels must be 6 colors darkest→brightest"
        assert len(tone["dormant_range"]) == 2, f"{tone_name} dormant_range must be 2 colors [low, high]"
        # Accent stops must be pairwise distinct (validator enforces; double-check at fixture level).
        accents = (tone["info_accent"], tone["mid_accent"], tone["header_band"])
        assert len(set(a.lower() for a in accents)) == 3, (
            f"{tone_name} accent stops must be pairwise distinct, got {accents}"
        )
        # header_band must differ from canvas stops (otherwise chart header invisible).
        assert tone["header_band"].lower() != tone["canvas_top"].lower(), (
            f"{tone_name} header_band must differ from canvas_top"
        )
        assert tone["header_band"].lower() != tone["canvas_bottom"].lower(), (
            f"{tone_name} header_band must differ from canvas_bottom"
        )

    # Spot-check existing values preserved 1:1 from the deleted flat fields
    teal = spec.variant_tones["teal"]
    assert teal["label_slab"] == "#0A1C28"
    assert teal["value_text"] == "#A8D4F0"
    violet = spec.variant_tones["violet"]
    assert violet["label_slab"] == "#150A22"
    assert violet["value_text"] == "#D8B4FE"

    # Pulse config (paradigm infrastructure, unchanged)
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
