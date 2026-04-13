"""Tests for core domain models, text measurement, color math, contracts, thresholds."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from hyperweave.config.loader import load_glyphs, load_motions, load_policies
from hyperweave.core.color import (
    contrast_ratio,
    hex_to_rgb,
    is_wcag_aa,
    relative_luminance,
    rgb_to_hex,
)
from hyperweave.core.contracts import ArtifactContract
from hyperweave.core.models import (
    ComposeResult,
    ComposeSpec,
    FrameDef,
    SlotContent,
    ZoneDef,
)
from hyperweave.core.schema import GenomeSpec
from hyperweave.core.text import measure_text
from hyperweave.core.thresholds import resolve_threshold_state

if TYPE_CHECKING:
    from hyperweave.core.models import ProfileConfig


# ==========================================================================
# Domain Models
# ==========================================================================


def test_slot_content_creation() -> None:
    slot = SlotContent(zone="value", value="passing")
    assert slot.zone == "value"
    assert slot.value == "passing"
    assert slot.data is None


def test_slot_content_frozen() -> None:
    slot = SlotContent(zone="value", value="passing")
    with pytest.raises(ValidationError):
        slot.zone = "other"  # type: ignore[misc]


def test_compose_spec_defaults() -> None:
    spec = ComposeSpec(type="badge")
    assert spec.type == "badge"
    assert spec.genome_id == "brutalist-emerald"
    assert spec.state == "active"
    assert spec.motion == "static"
    assert spec.metadata_tier == 3
    assert spec.generation == 1
    assert spec.regime == "normal"
    assert spec.divider_variant == "zeropoint"
    assert spec.marquee_rows == 1


def test_compose_spec_frozen() -> None:
    spec = ComposeSpec(type="badge")
    with pytest.raises(ValidationError):
        spec.type = "strip"  # type: ignore[misc]


def test_compose_spec_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        ComposeSpec(type="badge", nonexistent_field="oops")  # type: ignore[call-arg]


def test_compose_result() -> None:
    result = ComposeResult(svg="<svg></svg>", width=100, height=22)
    assert result.svg == "<svg></svg>"
    assert result.width == 100
    assert result.height == 22
    assert result.metadata is None


def test_zone_def() -> None:
    zone = ZoneDef(id="value", name="Value Zone", x=50, y=0, width=60, height=22)
    assert zone.id == "value"
    assert zone.width == 60


def test_frame_def() -> None:
    frame = FrameDef(
        id="badge",
        name="Badge",
        default_width=150,
        default_height=22,
        zones=[ZoneDef(id="label", name="Label", x=0, y=0, width=50, height=22)],
    )
    assert frame.id == "badge"
    assert len(frame.zones) == 1


# ==========================================================================
# Genome Schema
# ==========================================================================


def test_genome_spec_brutalist_emerald(sample_genome: GenomeSpec) -> None:
    assert sample_genome.id == "brutalist-emerald"
    assert sample_genome.category == "dark"
    assert sample_genome.profile == "brutalist"
    assert sample_genome.surface_0 == "#0A2218"
    assert sample_genome.accent == "#10B981"
    assert "static" in sample_genome.compatible_motions


def test_genome_spec_css_mapping(sample_genome: GenomeSpec) -> None:
    mapping = sample_genome.genome_to_css()
    assert mapping["surface_0"] == "--dna-surface"
    assert mapping["accent"] == "--dna-signal"
    assert mapping["ink"] == "--dna-ink-primary"
    # Core (20) + Extended palette (13) + Material (2) = 35
    assert len(mapping) >= 20


def test_genome_spec_css_vars(sample_genome: GenomeSpec) -> None:
    css_vars = sample_genome.to_css_vars()
    assert css_vars["--dna-surface"] == "#0A2218"
    assert css_vars["--dna-signal"] == "#10B981"


def test_genome_spec_invalid_hex() -> None:
    with pytest.raises(ValidationError):
        GenomeSpec(
            id="bad",
            name="Bad",
            category="dark",
            profile="brutalist",
            surface_0="not-a-color",
            surface_1="#000000",
            surface_2="#000000",
            ink="#FFFFFF",
            ink_secondary="#CCCCCC",
            ink_on_accent="#FFFFFF",
            accent="#00FF00",
            accent_complement="#00CC00",
            accent_signal="#009900",
            accent_warning="#FFCC00",
            accent_error="#FF0000",
            stroke="#333333",
            shadow_color="#000000",
            shadow_opacity="0.1",
            corner="0",
            rhythm_base="2s",
            density="1.0",
            compatible_motions=["static"],
        )


def test_genome_spec_invalid_category() -> None:
    with pytest.raises(Exception, match="category"):
        GenomeSpec(
            id="bad",
            name="Bad",
            category="medium",
            profile="brutalist",
            surface_0="#000000",
            surface_1="#000000",
            surface_2="#000000",
            ink="#FFFFFF",
            ink_secondary="#CCCCCC",
            ink_on_accent="#FFFFFF",
            accent="#00FF00",
            accent_complement="#00CC00",
            accent_signal="#009900",
            accent_warning="#FFCC00",
            accent_error="#FF0000",
            stroke="#333333",
            shadow_color="#000000",
            shadow_opacity="0.1",
            corner="0",
            rhythm_base="2s",
            density="1.0",
            compatible_motions=["static"],
        )


def test_genome_spec_motions_must_include_static() -> None:
    with pytest.raises(Exception, match="static"):
        GenomeSpec(
            id="bad",
            name="Bad",
            category="dark",
            profile="brutalist",
            surface_0="#000000",
            surface_1="#000000",
            surface_2="#000000",
            ink="#FFFFFF",
            ink_secondary="#CCCCCC",
            ink_on_accent="#FFFFFF",
            accent="#00FF00",
            accent_complement="#00CC00",
            accent_signal="#009900",
            accent_warning="#FFCC00",
            accent_error="#FF0000",
            stroke="#333333",
            shadow_color="#000000",
            shadow_opacity="0.1",
            corner="0",
            rhythm_base="2s",
            density="1.0",
            compatible_motions=["bars"],
        )


def test_genome_rhythm_computed(sample_genome: GenomeSpec) -> None:
    """Rhythm slow and fast should be computed from base via phi."""
    assert sample_genome.rhythm_slow != ""
    assert sample_genome.rhythm_fast != ""
    # Base is 2.618s, phi is ~1.618
    # slow should be ~4.236, fast should be ~1.618
    slow_val = float(sample_genome.rhythm_slow.rstrip("s"))
    fast_val = float(sample_genome.rhythm_fast.rstrip("s"))
    assert 3.5 < slow_val < 5.0
    assert 1.2 < fast_val < 2.0


def test_genome_spec_paradigm_fields_default_empty() -> None:
    """New paradigm/structural dicts default to empty dicts (backward compat)."""
    # Minimal genome without any of the new optional fields
    genome = GenomeSpec(
        id="test",
        name="Test",
        category="dark",
        profile="brutalist",
        surface_0="#000000",
        surface_1="#111111",
        surface_2="#080808",
        ink="#FFFFFF",
        ink_secondary="#CCCCCC",
        ink_on_accent="#FFFFFF",
        accent="#00FF00",
        accent_complement="#00CC00",
        accent_signal="#009900",
        accent_warning="#FFCC00",
        accent_error="#FF0000",
        stroke="#333333",
        shadow_color="#000000",
        shadow_opacity="0.1",
        corner="0",
        rhythm_base="2s",
        density="1.0",
        compatible_motions=["static"],
    )
    assert genome.paradigms == {}
    assert genome.structural == {}
    assert genome.typography == {}
    assert genome.material == {}
    assert genome.motion_config == {}


def test_genome_spec_brutalist_emerald_has_paradigms(sample_genome: GenomeSpec) -> None:
    """The brutalist-emerald genome declares paradigms and structural dicts."""
    # Paradigms dispatch map (Principle 26)
    assert sample_genome.paradigms["badge"] == "default"
    assert sample_genome.paradigms["stats"] == "brutalist"
    assert sample_genome.paradigms["chart"] == "brutalist"
    assert sample_genome.paradigms["timeline"] == "default"
    # Structural cascade (Principle 24)
    assert sample_genome.structural["stroke_linejoin"] == "miter"
    assert sample_genome.structural["data_point_shape"] == "square"
    # Typography
    assert "JetBrains Mono" in sample_genome.typography["hero_font"]
    # Material
    assert sample_genome.material["surface"] == "matte"


# ==========================================================================
# Profile Config
# ==========================================================================


def test_profile_config_brutalist(sample_profile: ProfileConfig) -> None:
    assert sample_profile.id == "brutalist"
    assert sample_profile.badge_frame_height == 20
    assert sample_profile.badge_corner == 0
    assert sample_profile.glyph_backing == "square"
    assert sample_profile.status_shape == "square"
    assert sample_profile.strip_accent_width == 6


def test_profile_config_frozen(sample_profile: ProfileConfig) -> None:
    with pytest.raises(ValidationError):
        sample_profile.id = "other"  # type: ignore[misc]


# ==========================================================================
# Text Measurement
# ==========================================================================


def test_measure_text_returns_float() -> None:
    width = measure_text("hello")
    assert isinstance(width, float)
    assert width > 0


def test_measure_text_longer_is_wider() -> None:
    short = measure_text("hi")
    long = measure_text("hello world")
    assert long > short


def test_measure_text_bold_is_wider() -> None:
    normal = measure_text("build", bold=False)
    bold = measure_text("build", bold=True)
    assert bold > normal


def test_measure_text_font_size_scaling() -> None:
    small = measure_text("test", font_size=11.0)
    large = measure_text("test", font_size=22.0)
    assert abs(large - small * 2) < 0.1


def test_measure_text_empty_string() -> None:
    assert measure_text("") == 0.0


def test_measure_text_known_characters() -> None:
    """Single characters should return known LUT values."""
    width_a = measure_text("a")
    assert 4.0 < width_a < 8.0  # Inter 'a' at 11px should be ~5.7px


# ==========================================================================
# Color Math
# ==========================================================================


def test_hex_to_rgb() -> None:
    assert hex_to_rgb("#FFFFFF") == (255, 255, 255)
    assert hex_to_rgb("#000000") == (0, 0, 0)
    assert hex_to_rgb("#14532D") == (20, 83, 45)


def test_rgb_to_hex() -> None:
    assert rgb_to_hex(255, 255, 255) == "#FFFFFF"
    assert rgb_to_hex(0, 0, 0) == "#000000"


def test_hex_to_rgb_invalid() -> None:
    with pytest.raises(ValueError):
        hex_to_rgb("#FFF")


def test_relative_luminance_white() -> None:
    lum = relative_luminance("#FFFFFF")
    assert abs(lum - 1.0) < 0.001


def test_relative_luminance_black() -> None:
    lum = relative_luminance("#000000")
    assert abs(lum - 0.0) < 0.001


def test_contrast_ratio_black_white() -> None:
    ratio = contrast_ratio("#000000", "#FFFFFF")
    assert abs(ratio - 21.0) < 0.1


def test_contrast_ratio_same_color() -> None:
    ratio = contrast_ratio("#14532D", "#14532D")
    assert abs(ratio - 1.0) < 0.001


def test_is_wcag_aa_black_white() -> None:
    assert is_wcag_aa("#000000", "#FFFFFF") is True


def test_is_wcag_aa_similar_colors() -> None:
    assert is_wcag_aa("#333333", "#444444") is False


def test_contrast_ratio_brutalist_emerald() -> None:
    """Verify that brutalist-emerald ink on surface passes WCAG AA."""
    ratio = contrast_ratio("#14532D", "#A7F3D0")
    assert ratio >= 4.5


# ==========================================================================
# Artifact Contracts
# ==========================================================================


def test_badge_width_basic() -> None:
    width = ArtifactContract.badge_width("build", "passing")
    assert isinstance(width, int)
    assert 80 < width < 200


def test_badge_width_with_glyph() -> None:
    without = ArtifactContract.badge_width("build", "passing", has_glyph=False)
    with_glyph = ArtifactContract.badge_width("build", "passing", has_glyph=True)
    assert with_glyph > without


def test_badge_width_with_indicator() -> None:
    without = ArtifactContract.badge_width("build", "passing", has_indicator=False)
    with_ind = ArtifactContract.badge_width("build", "passing", has_indicator=True)
    assert with_ind > without


def test_badge_height_default() -> None:
    assert ArtifactContract.badge_height() == 22


def test_badge_height_with_brutalist_profile(sample_profile: ProfileConfig) -> None:
    assert ArtifactContract.badge_height(sample_profile) == 20


def test_strip_width_minimum() -> None:
    """Strip width should never go below 530px."""
    width = ArtifactContract.strip_width("hi")
    assert width >= 530


def test_strip_width_with_metrics() -> None:
    metrics = [("STARS", "2.9k"), ("FORKS", "278"), ("VERSION", "v0.6.3")]
    width = ArtifactContract.strip_width("readme-ai", metrics=metrics)
    assert width >= 530


# ==========================================================================
# Thresholds
# ==========================================================================


def test_threshold_coverage_passing() -> None:
    assert resolve_threshold_state("95%", "coverage") == "passing"


def test_threshold_coverage_warning() -> None:
    assert resolve_threshold_state("75", "coverage") == "warning"


def test_threshold_coverage_critical() -> None:
    assert resolve_threshold_state("50%", "coverage") == "critical"


def test_threshold_boundary_90() -> None:
    assert resolve_threshold_state("90", "coverage") == "passing"


def test_threshold_boundary_70() -> None:
    assert resolve_threshold_state("70", "coverage") == "warning"


def test_threshold_unknown_id() -> None:
    with pytest.raises(KeyError, match="nonexistent"):
        resolve_threshold_state("50", "nonexistent")


def test_threshold_invalid_value() -> None:
    with pytest.raises(ValueError, match="Cannot parse"):
        resolve_threshold_state("abc", "coverage")


# ==========================================================================
# Config Loaders
# ==========================================================================


def test_load_genomes(all_genomes: dict[str, GenomeSpec]) -> None:
    assert "brutalist-emerald" in all_genomes
    assert "chrome-horizon" in all_genomes
    assert len(all_genomes) >= 2


def test_load_profiles(all_profiles: dict[str, ProfileConfig]) -> None:
    assert "brutalist" in all_profiles
    assert "chrome" in all_profiles
    assert len(all_profiles) == 2


def test_load_glyphs() -> None:
    glyphs = load_glyphs()
    assert "github" in glyphs
    assert "python" in glyphs
    assert "triangle" in glyphs
    assert "diamond" in glyphs
    assert glyphs["github"]["category"] == "social"
    assert glyphs["triangle"]["category"] == "geometric"


def test_load_motions() -> None:
    motions = load_motions()
    assert "static" in motions
    assert "bars" in motions
    assert motions["static"]["cim_compliant"] is True


def test_load_policies() -> None:
    policies = load_policies()
    assert "normal" in policies
    assert "permissive" in policies
    assert "ungoverned" in policies
    assert policies["normal"]["cim_enforced"] is True
    assert policies["ungoverned"]["cim_enforced"] is False


# ==========================================================================
# Cross-Validation: Genome -> Profile reference
# ==========================================================================


def test_genome_profile_references_exist(
    all_genomes: dict[str, GenomeSpec],
    all_profiles: dict[str, ProfileConfig],
) -> None:
    """Every genome must reference an existing profile."""
    for genome_id, genome in all_genomes.items():
        assert genome.profile in all_profiles, (
            f"Genome '{genome_id}' references profile '{genome.profile}' which does not exist. "
            f"Available profiles: {list(all_profiles.keys())}"
        )
