"""Cellular paradigm — Phase 3 scaffolding validation.

The cellular paradigm is the aesthetic vehicle for the automata genome.
These tests verify the paradigm loads, declares the expected requirement
set, and that automata satisfies every required field.
"""

from __future__ import annotations

from hyperweave.compose.validate_paradigms import validate_genome_against_paradigms
from hyperweave.config.registry import get_genome_specs, get_paradigms, reset_registry


def test_cellular_paradigm_loads() -> None:
    """data/paradigms/cellular.yaml loads as a valid ParadigmSpec."""
    reset_registry()
    paradigms = get_paradigms()
    assert "cellular" in paradigms
    spec = paradigms["cellular"]
    assert spec.id == "cellular"
    assert spec.name == "Cellular"


def test_cellular_requires_bifamily_fields() -> None:
    """Paradigm declares every automata-family chromatic field it needs."""
    cellular = get_paradigms()["cellular"]
    required = set(cellular.requires_genome_fields)
    # Blue family
    assert {
        "variant_blue_rim_stops",
        "variant_blue_pattern_cells",
        "variant_blue_label_text",
        "variant_blue_value_text",
    }.issubset(required)
    # Purple family
    assert {
        "variant_purple_rim_stops",
        "variant_purple_pattern_cells",
        "variant_purple_label_text",
        "variant_purple_value_text",
    }.issubset(required)
    # Bifamily bridge
    assert {
        "variant_bifamily_bridge_teal_mid",
        "variant_bifamily_bridge_amethyst_core",
    }.issubset(required)
    # State palette (used by the shared state-signal cascade partial)
    assert {"state_passing_core", "state_passing_bright", "state_critical_core"}.issubset(required)


def test_cellular_frame_variant_defaults() -> None:
    """Paradigm declares per-frame family defaults (data-driven, not Python)."""
    cellular = get_paradigms()["cellular"]
    assert cellular.frame_variant_defaults.get("badge") == "blue"
    assert cellular.frame_variant_defaults.get("icon") == "blue"
    assert cellular.frame_variant_defaults.get("strip") == "bifamily"
    assert cellular.frame_variant_defaults.get("marquee-horizontal") == "bifamily"
    # banner default removed in v0.2.14 with the banner frame type.
    assert "banner" not in cellular.frame_variant_defaults


def test_cellular_strip_config_exposes_status_flags() -> None:
    """Strip paradigm config exposes the new conditional-zone flags."""
    cellular = get_paradigms()["cellular"]
    assert cellular.strip.show_status_indicator is True
    assert cellular.strip.flank_width == 36
    assert cellular.strip.flank_cell_size == 12
    assert cellular.strip.value_font_family == "Chakra Petch"


def test_cellular_badge_config_exposes_indicator_flag() -> None:
    """Badge paradigm config exposes show_indicator flag."""
    cellular = get_paradigms()["cellular"]
    assert cellular.badge.show_indicator is True
    assert cellular.badge.value_font_family == "Chakra Petch"
    assert cellular.badge.label_font_family == "Orbitron"


def test_automata_satisfies_cellular_requirements() -> None:
    """automata genome declares every field cellular paradigm requires."""
    paradigms = get_paradigms()
    automata = get_genome_specs()["automata"]
    # Should not raise — every required field is populated.
    validate_genome_against_paradigms(automata, paradigms)
