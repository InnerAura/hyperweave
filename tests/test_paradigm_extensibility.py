"""Extensibility proof: adding a new paradigm requires zero Python edits.

Invariant 12 (CLAUDE.md): *"Adding a new paradigm within the existing
frame contract requires zero Python edits."*

This suite proves the invariant from two directions:

1. **Plumbing smoke-test** — every installed paradigm loads as a valid
   ``ParadigmSpec``, every paradigm's config is reachable from the
   resolver via ``paradigm_spec.{frame}.{key}`` attribute access, and
   ``validate_genome_against_paradigms`` accepts the shipped genomes.

2. **Contract enforcement** — a fictional ``vellum`` paradigm declaring
   ``requires_genome_fields = [envelope_stops, well_top]`` rejects a
   genome that opts into it without declaring those fields, with a
   structured ``ValueError`` naming every missing field.

The workflow for shipping a new paradigm is documented at the top of
``PROFILE_CONTRACTS.md``: author ``data/paradigms/{slug}.yaml``, then
``templates/frames/{frame}/{slug}-defs.j2`` and
``templates/frames/{frame}/{slug}-content.j2`` — no Python file edits.
"""

from __future__ import annotations

import pytest

from hyperweave.compose.validate_paradigms import validate_genome_against_paradigms
from hyperweave.config.registry import get_genome_specs, get_paradigms, reset_registry
from hyperweave.core.paradigm import (
    ParadigmBadgeConfig,
    ParadigmSpec,
    ParadigmStripConfig,
)
from hyperweave.core.schema import GenomeSpec


def test_every_shipped_paradigm_loads_as_valid_spec() -> None:
    """Every YAML under data/paradigms/ Pydantic-validates into a ParadigmSpec."""
    reset_registry()
    paradigms = get_paradigms()
    assert "default" in paradigms
    assert "chrome" in paradigms
    assert "brutalist" in paradigms
    for slug, spec in paradigms.items():
        assert isinstance(spec, ParadigmSpec), f"paradigm '{slug}' must be a ParadigmSpec"
        assert spec.id == slug


def test_chrome_paradigm_requires_chromatic_genome_fields() -> None:
    """chrome.yaml declares the six fields every chrome genome must carry."""
    paradigms = get_paradigms()
    chrome = paradigms["chrome"]
    required = set(chrome.requires_genome_fields)
    assert {
        "envelope_stops",
        "well_top",
        "well_bottom",
        "chrome_text_gradient",
        "hero_text_gradient",
        "highlight_color",
    }.issubset(required)


def test_every_shipped_genome_passes_validation() -> None:
    """Shipped genomes all declare the fields their paradigms require."""
    paradigms = get_paradigms()
    for genome in get_genome_specs().values():
        # No exception = pass. This is the same gate ConfigLoader runs at startup.
        validate_genome_against_paradigms(genome, paradigms)


def test_paradigm_sub_configs_have_expected_shape() -> None:
    """Resolver-facing attribute access works as specified."""
    chrome = get_paradigms()["chrome"]
    # badge
    assert isinstance(chrome.badge, ParadigmBadgeConfig)
    assert chrome.badge.value_font_family == "Orbitron"
    # strip
    assert isinstance(chrome.strip, ParadigmStripConfig)
    assert chrome.strip.divider_render_mode == "gradient"
    assert chrome.strip.status_shape_rendering == "geometricPrecision"
    # chart + stats (the viewport and embed-chart flags)
    assert chrome.chart.viewport_w == 750
    assert chrome.stats.embeds_chart is True


def test_new_paradigm_constructs_from_config_without_python_edits() -> None:
    """A fictional ``vellum`` paradigm built from a YAML-shaped dict works.

    Proves the ``ParadigmSpec(**raw_yaml_dict)`` round-trip — the same path
    ``load_paradigms`` takes. Adding ``data/paradigms/vellum.yaml`` with
    these same keys + matching ``templates/frames/*/vellum-*.j2`` partials
    would wire a new paradigm into the system with zero Python edits.
    """
    raw = {
        "id": "vellum",
        "name": "Vellum",
        "description": "Test-only paradigm proving YAML → ParadigmSpec plumbing.",
        "requires_genome_fields": ["envelope_stops", "well_top"],
        "badge": {
            "label_font_family": "Inter",
            "value_font_family": "Orbitron",
            "label_font_size": 10,
            "value_font_size": 12,
            "value_font_weight": 800,
        },
        "strip": {
            "value_font_size": 16,
            "value_font_family": "Inter",
            "label_font_size": 8,
            "label_font_family": "JetBrains Mono",
            "divider_render_mode": "class",
            "status_shape_rendering": "crispEdges",
        },
        "chart": {"viewport_x": 100, "viewport_y": 160, "viewport_w": 700, "viewport_h": 240},
        "stats": {"card_height": 270, "embeds_chart": False},
        "icon": {"supported_shapes": ["circle"], "default_shape": "circle"},
    }
    spec = ParadigmSpec(**raw)
    assert spec.id == "vellum"
    assert spec.badge.value_font_family == "Orbitron"
    assert spec.chart.viewport_w == 700
    assert spec.stats.embeds_chart is False
    assert "envelope_stops" in spec.requires_genome_fields


def test_validator_rejects_genome_missing_paradigm_required_fields() -> None:
    """A genome opting into vellum without its required fields fails loudly."""
    vellum = ParadigmSpec(
        id="vellum",
        name="Vellum",
        requires_genome_fields=["envelope_stops", "well_top"],
    )
    # Construct a genome with chrome-family-style declarations but missing
    # envelope_stops/well_top — simulates what happens when a designer
    # forgets the chromatic declarations for a paradigm they opt into.
    from tests.helpers import build_partial_genome_for_testing

    partial = build_partial_genome_for_testing(
        id="test-partial",
        profile="chrome",
        paradigms={"badge": "vellum"},
    )
    genome = GenomeSpec(**partial)
    with pytest.raises(ValueError) as exc_info:
        validate_genome_against_paradigms(genome, {"vellum": vellum})
    message = str(exc_info.value)
    assert "vellum" in message
    assert "envelope_stops" in message
    assert "well_top" in message
