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


def test_cellular_requires_state_and_pulse_fields() -> None:
    """v0.3.0: paradigm requires only structural fields (pulse animation
    timings + state palette). Tone shape is enforced by validate_genome_variants
    in compose/validate_paradigms.py — not by the paradigm requires_genome_fields
    list, since the variant_tones dict isn't a flat field-name match."""
    cellular = get_paradigms()["cellular"]
    required = set(cellular.requires_genome_fields)
    # Pulse animation config (paradigm infrastructure)
    assert {"cellular_pulse_base_duration", "cellular_pattern_opacity"}.issubset(required)
    # State palette (used by the shared state-signal cascade partial)
    assert {
        "state_passing_core",
        "state_passing_bright",
        "state_warning_core",
        "state_critical_core",
        "state_building_core",
        "state_offline_core",
    }.issubset(required)
    # Old flat variant_blue_* / variant_purple_* / variant_bifamily_bridge_*
    # requirements removed — those moved into variant_tones / variant_pairs.
    legacy_fields = {f for f in required if f.startswith(("variant_blue_", "variant_purple_", "variant_bifamily_"))}
    assert legacy_fields == set(), f"v0.3.0 should have no legacy variant_*_ requires; got {legacy_fields}"


def test_cellular_frame_variant_defaults() -> None:
    """v0.3.0 grammar refactor: every frame defaults to teal (the canonical
    solo flagship). Pairing is opt-in via ``?variant=teal&pair=violet`` —
    pre-grammar, the default was the paired ``violet-teal`` slug, but pairing
    is no longer a baked variant entry. The 12 solo tones each compose with
    any other solo tone via the URL grammar modifier."""
    cellular = get_paradigms()["cellular"]
    assert cellular.frame_variant_defaults.get("badge") == "teal"
    assert cellular.frame_variant_defaults.get("icon") == "teal"
    assert cellular.frame_variant_defaults.get("strip") == "teal"
    assert cellular.frame_variant_defaults.get("marquee-horizontal") == "teal"
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


# ────────────────────────────────────────────────────────────────────
#  v0.3.0 visual refresh — paradigm constants and dimensions
# ────────────────────────────────────────────────────────────────────


def test_cellular_stats_paradigm_constants() -> None:
    """Cellular stats paradigm declares streak_green / mid_gray / hero_white as
    genome-independent constants. These flow to template context as named
    template variables (not raw hex), keeping the variant-blind hex gate
    effective and letting paradigms override without genome edits."""
    cellular = get_paradigms()["cellular"]
    assert cellular.stats.streak_green == "#3FB950"
    assert cellular.stats.mid_gray == "#6B7A88"
    assert cellular.stats.hero_white == "#ECF2F8"


def test_cellular_stats_dimensions() -> None:
    """v0.3.0 visual refresh: stat card compacts to 530x233."""
    cellular = get_paradigms()["cellular"]
    assert cellular.stats.card_width == 530
    assert cellular.stats.card_height == 233
    assert cellular.stats.header_band_height == 39


def test_cellular_chart_dimensions() -> None:
    """v0.3.0 visual refresh: star chart restructures to 680x380 with
    a deliberate HUD-style header band at y=0..64. Cell stride 19 yields
    a 30-col x 13-row substrate grid in the 580x246 chart area."""
    cellular = get_paradigms()["cellular"]
    assert cellular.chart.chart_width == 680
    assert cellular.chart.chart_height == 380
    assert cellular.chart.viewport_x == 72
    assert cellular.chart.viewport_y == 80
    assert cellular.chart.viewport_w == 580
    assert cellular.chart.viewport_h == 246
    assert cellular.chart.cell_size == 19
    assert cellular.chart.header_band_height == 64


def test_cellular_icon_dimensions() -> None:
    """v0.3.0 visual refresh: icon recomposes at 48x48 with a 5x5 living
    cell grid (8x8 cells, 1px gap) and a centered glyph at 21.12x21.12."""
    cellular = get_paradigms()["cellular"]
    assert cellular.icon.card_width == 48
    assert cellular.icon.card_height == 48
    assert cellular.icon.cell_grid_cols == 5
    assert cellular.icon.cell_grid_rows == 5
    assert cellular.icon.cell_size == 8
    assert cellular.icon.cell_gap == 1
    assert cellular.icon.cell_rx == 1
    assert cellular.icon.glyph_size == 21.12
    assert cellular.icon.glyph_inset == 13.44
    assert cellular.icon.outer_border_rx == 6


def test_cellular_marquee_dimensions() -> None:
    """v0.3.0 visual refresh: marquee compacts to 800x32 with Orbitron-only
    font payload and monofamily mid_accent hairlines."""
    cellular = get_paradigms()["cellular"]
    assert cellular.marquee.width == 800
    assert cellular.marquee.height == 32
    assert cellular.marquee.font_family == "Orbitron, sans-serif"
    assert cellular.marquee.font_size == 11


def test_cellular_heatmap_fits_card_height() -> None:
    """Directive 8 regression gate: stats heatmap content (rows*cell + gaps)
    must fit the heatmap zone height. The v0.3.0 prototype computes
    7*11.080 + 6*1.2 = 84.76, filling a ~84.76px zone exactly. Off by more
    than 0.5px would clip the bottom edge of the heatmap against the card
    outline at 1px stroke tolerance."""
    cellular = get_paradigms()["cellular"]
    rows = cellular.stats.heatmap_rows
    cell = cellular.stats.heatmap_cell_size
    gap = cellular.stats.heatmap_cell_gap
    available = cellular.stats.heatmap_zone_height
    used = rows * cell + (rows - 1) * gap
    assert used <= available + 0.5, f"Heatmap content {used:.2f}px overflows {available:.2f}px zone"


def test_per_frame_font_filtering() -> None:
    """Directive 2: font embedding is filtered per frame so marquee + chart
    don't ship the full 3-font payload. Marquee gets Orbitron only; chart
    gets Orbitron + JBM (no Chakra Petch); icon embeds zero fonts."""
    from hyperweave.compose.assembler import fonts_for_frame
    from hyperweave.core.enums import FrameType

    assert fonts_for_frame(FrameType.STATS) == frozenset({"jetbrains-mono", "orbitron", "chakra-petch"})
    assert fonts_for_frame(FrameType.CHART) == frozenset({"jetbrains-mono", "orbitron"})
    assert fonts_for_frame(FrameType.MARQUEE_HORIZONTAL) == frozenset({"orbitron"})
    assert fonts_for_frame(FrameType.ICON) == frozenset()
    assert fonts_for_frame(FrameType.DIVIDER) == frozenset()
