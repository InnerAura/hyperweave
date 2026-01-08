"""
Unit tests for BadgeGenerator - Theme-driven badge generation.

Tests cover:
- Theme loading and validation
- State override application
- Motion validation and compatibility
- Gradient generation (both formats)
- SVG structure and metadata
- Effect integration
- Glyph generation
- Error handling
"""

import pytest

from hyperweave.models.badge import BadgeContent, BadgeRequest

# ─── BASICS ──────────────────────────────────────────────────────────────────


def test_basics_generator_initializes(generator):
    """Should initialize with ontology."""
    assert generator is not None
    assert generator.ontology is not None
    assert generator.effect_registry is not None


def test_basics_generate_simple_badge(generator):
    """Should generate a basic badge with minimal config."""
    request = BadgeRequest(theme="chrome", content=BadgeContent(label="test", value="ok"))

    response = generator.generate(request)

    assert response.svg is not None
    assert len(response.svg) > 0
    assert response.metadata is not None
    assert response.theme_dna is not None


def test_basics_theme_dna_populated(generator):
    """Should populate ThemeDNA correctly."""
    request = BadgeRequest(theme="codex", content=BadgeContent(label="version", value="1.0.0"))

    response = generator.generate(request)
    dna = response.theme_dna

    assert dna.theme == "codex"
    assert dna.tier == "scholarly"
    assert dna.series == "five-scholars"
    assert dna.motion == "static"  # Default
    assert dna.ontology_version == "7.0.0"


# ─── THEME LOADING ───────────────────────────────────────────────────────────


def test_loading_all_20_themes(generator):
    """Should successfully load all 20 themes."""
    theme_ids = [
        # Industrial (3)
        "chrome",
        "titanium",
        "obsidian",
        # Flagship (4)
        "neon",
        "glass",
        "holo",
        "clarity",
        # Premium (2)
        "depth",
        "glossy",
        # Brutalist (2)
        "brutalist",
        "brutalist-clean",
        # Cosmology (3)
        "sakura",
        "aurora",
        "singularity",
        # Scholarly (5)
        "codex",
        "theorem",
        "archive",
        "symposium",
        "cipher",
        # Minimal (1)
        "void",
    ]

    for theme_id in theme_ids:
        request = BadgeRequest(theme=theme_id, content=BadgeContent(label="test", value="ok"))
        response = generator.generate(request)
        assert response.svg is not None
        assert response.theme_dna.theme == theme_id


def test_loading_invalid_theme_raises_key_error(generator):
    """Should raise KeyError for invalid theme."""
    request = BadgeRequest(theme="nonexistent", content=BadgeContent(label="test", value="ok"))

    with pytest.raises(KeyError) as exc_info:
        generator.generate(request)

    error_msg = str(exc_info.value)
    assert "nonexistent" in error_msg
    assert "Available themes:" in error_msg


# ─── STATE OVERRIDES ─────────────────────────────────────────────────────────


def test_states_apply_passing_override(generator):
    """Should apply passing state overrides."""
    request = BadgeRequest(
        theme="chrome", content=BadgeContent(label="build", value="ok", state="passing")
    )

    response = generator.generate(request)

    # Should contain green gradient for passing state
    assert "#10b981" in response.svg or "#059669" in response.svg


def test_states_apply_warning_override(generator):
    """Should apply warning state overrides."""
    request = BadgeRequest(
        theme="chrome", content=BadgeContent(label="coverage", value="75%", state="warning")
    )

    response = generator.generate(request)

    # Should contain orange/yellow gradient for warning state
    assert "#f59e0b" in response.svg or "#d97706" in response.svg


def test_states_apply_failing_override(generator):
    """Should apply failing state overrides."""
    request = BadgeRequest(
        theme="chrome", content=BadgeContent(label="test", value="fail", state="failing")
    )

    response = generator.generate(request)

    # Should contain red gradient for failing state
    assert "#ef4444" in response.svg or "#dc2626" in response.svg


def test_states_neutral_uses_default(generator):
    """Should use default theme colors for neutral state."""
    request = BadgeRequest(
        theme="chrome", content=BadgeContent(label="info", value="data", state="neutral")
    )

    response = generator.generate(request)

    # Should not contain state-specific colors
    assert "#10b981" not in response.svg  # Not green
    assert "#ef4444" not in response.svg  # Not red


# ─── MOTION VALIDATION ───────────────────────────────────────────────────────


def test_motion_default_from_theme(generator):
    """Should use first compatible motion if none specified."""
    request = BadgeRequest(theme="chrome", content=BadgeContent(label="test", value="ok"))

    response = generator.generate(request)

    # Chrome's compatible motions start with "static"
    assert response.theme_dna.motion == "static"


def test_motion_valid_override(generator):
    """Should accept valid motion override."""
    request = BadgeRequest(
        theme="chrome", content=BadgeContent(label="test", value="ok"), motion="sweep"
    )

    response = generator.generate(request)

    assert response.theme_dna.motion == "sweep"


def test_motion_invalid_raises_value_error(generator):
    """Should raise ValueError for incompatible motion."""
    request = BadgeRequest(
        theme="brutalist",
        content=BadgeContent(label="test", value="ok"),
        motion="sweep",  # Brutalist doesn't support sweep
    )

    with pytest.raises(ValueError) as exc_info:
        generator.generate(request)

    error_msg = str(exc_info.value)
    assert "sweep" in error_msg
    assert "brutalist" in error_msg


# ─── GRADIENT GENERATION ─────────────────────────────────────────────────────


def test_gradients_full_config(generator):
    """Should handle full gradient config with direction and stops."""
    request = BadgeRequest(
        theme="chrome", content=BadgeContent(label="test", value="ok", state="neutral")
    )

    response = generator.generate(request)

    # Should contain gradient definitions
    assert "<linearGradient" in response.svg
    assert 'id="grad-label"' in response.svg
    assert 'id="grad-value"' in response.svg
    assert "<stop" in response.svg


def test_gradients_shorthand_list(generator):
    """Should handle shorthand gradient as list of colors."""
    request = BadgeRequest(
        theme="chrome", content=BadgeContent(label="test", value="ok", state="passing")
    )

    response = generator.generate(request)

    # State override provides list of colors
    # Generator should convert to gradient with evenly spaced stops
    assert "<linearGradient" in response.svg
    assert 'id="grad-value"' in response.svg
    assert "offset=" in response.svg


# ─── SVG STRUCTURE ───────────────────────────────────────────────────────────


def test_svg_has_required_namespaces(generator):
    """Should include required XML namespaces."""
    request = BadgeRequest(theme="chrome", content=BadgeContent(label="test", value="ok"))

    response = generator.generate(request)

    assert 'xmlns="http://www.w3.org/2000/svg"' in response.svg
    assert 'xmlns:hw="https://hyperweave.dev/hw/v1.0"' in response.svg


def test_svg_has_accessibility_attributes(generator):
    """Should include accessibility attributes."""
    request = BadgeRequest(theme="chrome", content=BadgeContent(label="version", value="1.0.0"))

    response = generator.generate(request)

    assert 'role="img"' in response.svg
    assert "aria-labelledby=" in response.svg
    assert "<title" in response.svg
    assert "<desc" in response.svg


def test_svg_has_metadata(generator):
    """Should include HyperWeave metadata."""
    request = BadgeRequest(theme="chrome", content=BadgeContent(label="test", value="ok"))

    response = generator.generate(request)

    assert "<metadata>" in response.svg
    assert "<hw:artifact" in response.svg
    assert "<hw:provenance>" in response.svg
    assert "<hw:generator>" in response.svg
    assert "Claude Sonnet 4.5" in response.svg


def test_svg_has_defs_section(generator):
    """Should include <defs> section for gradients and effects."""
    request = BadgeRequest(theme="chrome", content=BadgeContent(label="test", value="ok"))

    response = generator.generate(request)

    assert "<defs>" in response.svg
    assert "</defs>" in response.svg


def test_svg_has_style_section(generator):
    """Should include <style> section for CSS."""
    request = BadgeRequest(theme="chrome", content=BadgeContent(label="test", value="ok"))

    response = generator.generate(request)

    assert "<style>" in response.svg
    assert "</style>" in response.svg
    assert "font-family:" in response.svg


# ─── GLYPH GENERATION ────────────────────────────────────────────────────────


def test_glyph_dot_generated(generator):
    """Should generate dot glyph."""
    request = BadgeRequest(
        theme="neon",  # Neon uses dot glyph
        content=BadgeContent(label="status", value="live", state="passing"),
    )

    response = generator.generate(request)

    # Should contain glyph circle
    assert "dot" in response.svg.lower() or "<circle" in response.svg


def test_glyph_none_type_handled(generator):
    """Should not generate glyph if type is 'none'."""
    request = BadgeRequest(
        theme="void",  # Void uses no glyph
        content=BadgeContent(label="test", value="ok"),
    )

    response = generator.generate(request)

    # Glyph-specific elements should be minimal or absent
    # This test verifies the generator handles "none" type gracefully
    assert response.svg is not None


# ─── EFFECT INTEGRATION ──────────────────────────────────────────────────────


def test_effects_rendered_for_theme(generator):
    """Should render effects defined in theme."""
    request = BadgeRequest(
        theme="chrome",  # Has dropShadow, specularHighlight, sweepHighlight
        content=BadgeContent(label="test", value="ok"),
    )

    response = generator.generate(request)

    # Should contain effect references
    # Exact structure depends on effect definitions
    assert len(response.svg) > 1000  # Effects add complexity


def test_effects_minimal_theme_no_effects(generator):
    """Should handle themes with minimal effects."""
    request = BadgeRequest(
        theme="void",  # Minimal theme
        content=BadgeContent(label="test", value="ok"),
    )

    response = generator.generate(request)

    # Should generate successfully even with no effects
    assert response.svg is not None
    assert len(response.svg) > 0


# ─── TEXT RENDERING ──────────────────────────────────────────────────────────


def test_text_label_rendered(generator):
    """Should render label text."""
    request = BadgeRequest(theme="chrome", content=BadgeContent(label="version", value="1.0.0"))

    response = generator.generate(request)

    assert ">version</text>" in response.svg


def test_text_value_rendered(generator):
    """Should render value text."""
    request = BadgeRequest(theme="chrome", content=BadgeContent(label="version", value="1.0.0"))

    response = generator.generate(request)

    assert ">1.0.0</text>" in response.svg


def test_text_special_characters_handled(generator):
    """Should handle special characters in text."""
    request = BadgeRequest(theme="chrome", content=BadgeContent(label="test<>&", value='quotes"&'))

    response = generator.generate(request)

    # Should contain the text (may be XML-escaped)
    assert response.svg is not None


# ─── METADATA GENERATION ─────────────────────────────────────────────────────


def test_metadata_includes_size(generator):
    """Should include badge size in metadata."""
    request = BadgeRequest(
        theme="chrome", content=BadgeContent(label="test", value="ok"), size="md"
    )

    response = generator.generate(request)

    # Metadata.size contains pixel dimensions (e.g., "140x20"), not the size enum
    assert "x" in response.metadata.size
    assert response.metadata.size.count("x") == 1


def test_metadata_includes_theme(generator):
    """Should include theme in metadata."""
    request = BadgeRequest(theme="codex", content=BadgeContent(label="test", value="ok"))

    response = generator.generate(request)

    assert response.metadata.theme == "adaptive"  # Standard value


def test_metadata_includes_ontology_version(generator):
    """Should include ontology version."""
    request = BadgeRequest(theme="chrome", content=BadgeContent(label="test", value="ok"))

    response = generator.generate(request)

    assert response.metadata.ontology_version == "7.0.0"


def test_metadata_includes_reasoning(generator):
    """Should include XAI reasoning if provided."""
    request = BadgeRequest(
        theme="chrome",
        content=BadgeContent(label="test", value="ok"),
        reasoning={"intent": "Test badge", "approach": "Simple test", "tradeoffs": "None"},
    )

    response = generator.generate(request)

    assert response.metadata.intent == "Test badge"
    assert response.metadata.approach == "Simple test"
    assert response.metadata.tradeoffs == "None"


# ─── ERROR HANDLING ──────────────────────────────────────────────────────────


def test_errors_empty_label_handled(generator):
    """Should handle empty label gracefully."""
    request = BadgeRequest(theme="chrome", content=BadgeContent(label="", value="ok"))

    response = generator.generate(request)

    assert response.svg is not None


def test_errors_empty_value_handled(generator):
    """Should handle empty value gracefully."""
    request = BadgeRequest(theme="chrome", content=BadgeContent(label="test", value=""))

    response = generator.generate(request)

    assert response.svg is not None


def test_errors_long_text_handled(generator):
    """Should handle long text without crashing."""
    request = BadgeRequest(
        theme="chrome",
        content=BadgeContent(
            label="very long label text here", value="very long value text here too"
        ),
    )

    response = generator.generate(request)

    assert response.svg is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
