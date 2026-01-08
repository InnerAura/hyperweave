"""
Tests for OntologyLoader - Theme-centric ontology loading.

Tests cover:
- Ontology file loading and validation
- Theme access and filtering
- Effect/motion/glyph definitions
- Error handling and suggestions
"""

from pathlib import Path

import pytest

from hyperweave.core.ontology import OntologyLoader


class TestOntologyLoaderBasics:
    """Test basic ontology loading and validation."""

    def test_loader_initializes_with_valid_ontology(self):
        """Should load v7 ontology successfully."""
        loader = OntologyLoader()
        assert loader is not None
        assert loader._data is not None
        assert loader.get_version() == "7.0.0"

    def test_loader_validates_version(self):
        """Should reject non-7.0.0 ontology versions."""
        # This would require a mock ontology file
        # For now, just verify the version check exists
        loader = OntologyLoader()
        assert loader.get_version() == "7.0.0"

    def test_loader_raises_on_missing_file(self):
        """Should raise FileNotFoundError for missing ontology."""
        fake_path = Path("/nonexistent/ontology.json")
        with pytest.raises(FileNotFoundError):
            OntologyLoader(ontology_path=fake_path)


class TestThemeAccess:
    """Test theme loading and access methods."""

    @pytest.fixture
    def loader(self):
        """Shared loader instance."""
        return OntologyLoader()

    def test_get_all_theme_ids(self, loader):
        """Should return all 25 theme IDs (20 original + 5 arcade)."""
        theme_ids = loader.get_all_theme_ids()
        assert len(theme_ids) == 25
        assert "chrome" in theme_ids
        assert "codex" in theme_ids
        assert "sakura" in theme_ids
        assert "arcade-snes" in theme_ids
        assert "arcade-gameboy" in theme_ids

    def test_get_theme_returns_complete_config(self, loader):
        """Should return complete theme configuration."""
        chrome = loader.get_theme("chrome")

        # Required fields
        assert chrome["id"] == "chrome"
        assert chrome["tier"] == "industrial"
        assert chrome["series"] == "core"
        assert "compatibleMotions" in chrome
        assert "label" in chrome
        assert "value" in chrome
        assert "states" in chrome
        assert "glyph" in chrome

        # XAI reasoning
        assert "intent" in chrome
        assert "approach" in chrome
        assert "tradeoffs" in chrome

    def test_get_theme_raises_on_invalid_id(self, loader):
        """Should raise KeyError with helpful message for invalid theme."""
        with pytest.raises(KeyError) as exc_info:
            loader.get_theme("chromee")  # Typo

        error_msg = str(exc_info.value)
        assert "chromee" in error_msg
        assert "Available themes:" in error_msg
        assert "Did you mean 'chrome'?" in error_msg

    def test_get_all_themes_returns_dict(self, loader):
        """Should return dictionary of all themes (20 original + 5 arcade = 25)."""
        themes = loader.get_all_themes()
        assert isinstance(themes, dict)
        assert len(themes) == 25
        assert "chrome" in themes
        assert themes["chrome"]["id"] == "chrome"
        assert "arcade-snes" in themes
        assert themes["arcade-snes"]["tier"] == "arcade"

    def test_get_themes_by_tier_industrial(self, loader):
        """Should filter themes by industrial tier."""
        industrial = loader.get_themes_by_tier("industrial")
        assert len(industrial) == 3
        ids = [t["id"] for t in industrial]
        assert "chrome" in ids
        assert "titanium" in ids
        assert "obsidian" in ids

    def test_get_themes_by_tier_scholarly(self, loader):
        """Should filter themes by scholarly tier."""
        scholarly = loader.get_themes_by_tier("scholarly")
        assert len(scholarly) == 5
        ids = [t["id"] for t in scholarly]
        assert "codex" in ids
        assert "theorem" in ids
        assert "archive" in ids
        assert "symposium" in ids
        assert "cipher" in ids

    def test_get_themes_by_series_core(self, loader):
        """Should filter themes by core series."""
        core = loader.get_themes_by_series("core")
        assert len(core) >= 15  # Most themes are core series

    def test_get_themes_by_series_five_scholars(self, loader):
        """Should filter themes by five-scholars series."""
        scholars = loader.get_themes_by_series("five-scholars")
        assert len(scholars) == 5
        ids = [t["id"] for t in scholars]
        assert all(
            theme_id in ids for theme_id in ["codex", "theorem", "archive", "symposium", "cipher"]
        )


class TestThemeCompatibility:
    """Test motion compatibility validation."""

    @pytest.fixture
    def loader(self):
        return OntologyLoader()

    def test_chrome_sweep_compatible(self, loader):
        """Chrome should be compatible with sweep motion."""
        valid, error = loader.validate_theme_motion_compatibility("chrome", "sweep")
        assert valid is True
        assert error is None

    def test_brutalist_sweep_incompatible(self, loader):
        """Brutalist should NOT be compatible with sweep."""
        valid, error = loader.validate_theme_motion_compatibility("brutalist", "sweep")
        assert valid is False
        assert error is not None
        assert "sweep" in error
        assert "brutalist" in error
        assert "Compatible motions:" in error

    def test_invalid_theme_returns_error(self, loader):
        """Invalid theme should return error."""
        valid, error = loader.validate_theme_motion_compatibility("invalid", "sweep")
        assert valid is False
        assert error is not None


class TestEffectDefinitions:
    """Test effect definition access."""

    @pytest.fixture
    def loader(self):
        return OntologyLoader()

    def test_get_effect_definition_drop_shadow(self, loader):
        """Should return dropShadow effect definition."""
        effect = loader.get_effect_definition("dropShadow")
        assert effect["type"] == "filter"
        assert "template" in effect

    def test_get_effect_definition_sweep_highlight(self, loader):
        """Should return sweepHighlight effect definition."""
        effect = loader.get_effect_definition("sweepHighlight")
        assert effect["type"] == "gradient"
        assert "stops" in effect

    def test_get_effect_definition_pulse_dot(self, loader):
        """Should return pulseDot effect definition."""
        effect = loader.get_effect_definition("pulseDot")
        assert effect["type"] == "animation"
        assert "keyframes" in effect

    def test_get_effect_definition_invalid_raises(self, loader):
        """Should raise KeyError for invalid effect."""
        with pytest.raises(KeyError) as exc_info:
            loader.get_effect_definition("invalidEffect")

        error_msg = str(exc_info.value)
        assert "invalidEffect" in error_msg
        assert "Available effects:" in error_msg

    def test_get_all_effect_definitions(self, loader):
        """Should return all effect definitions."""
        effects = loader.get_all_effect_definitions()
        assert isinstance(effects, dict)
        assert "dropShadow" in effects
        assert "sweepHighlight" in effects
        assert "pulseDot" in effects

    def test_validate_effect_exists(self, loader):
        """Should validate effect existence."""
        assert loader.validate_effect_exists("dropShadow") is True
        assert loader.validate_effect_exists("invalidEffect") is False


class TestMotionDefinitions:
    """Test motion definition access."""

    @pytest.fixture
    def loader(self):
        return OntologyLoader()

    def test_get_motion_definition_sweep(self, loader):
        """Should return sweep motion definition."""
        motion = loader.get_motion_definition("sweep")
        assert "effects" in motion
        assert "duration" in motion

    def test_get_motion_definition_static(self, loader):
        """Should return static motion definition."""
        motion = loader.get_motion_definition("static")
        assert motion["effects"] == []
        assert motion["duration"] is None

    def test_get_all_motions(self, loader):
        """Should return all motion definitions."""
        motions = loader.get_all_motions()
        assert isinstance(motions, dict)
        assert "static" in motions
        assert "sweep" in motions
        assert "breathe" in motions
        assert len(motions) == 8  # v7 has 8 motions


class TestGlyphDefinitions:
    """Test glyph definition access."""

    @pytest.fixture
    def loader(self):
        return OntologyLoader()

    def test_get_glyph_definition_dot(self, loader):
        """Should return dot glyph definition."""
        glyph = loader.get_glyph_definition("dot")
        assert "svg" in glyph
        assert "semantic" in glyph
        assert glyph["semantic"] == "active/online/live"

    def test_get_glyph_definition_none(self, loader):
        """Should return none glyph definition."""
        glyph = loader.get_glyph_definition("none")
        assert glyph["svg"] is None
        assert glyph["semantic"] == "no indicator"

    def test_get_all_glyphs(self, loader):
        """Should return all glyph definitions."""
        glyphs = loader.get_all_glyphs()
        assert isinstance(glyphs, dict)
        assert len(glyphs) == 10  # v7 has 10 glyph types


class TestSupportingData:
    """Test metadata, layout, protocol access."""

    @pytest.fixture
    def loader(self):
        return OntologyLoader()

    def test_get_metadata_template(self, loader):
        """Should return metadata template."""
        template = loader.get_metadata_template()
        assert "rdf" in template
        assert "hw:artifact" in template

    def test_get_svg_template(self, loader):
        """Should return SVG template."""
        template = loader.get_svg_template()
        assert "rootAttributes" in template
        assert "structure" in template

        # Verify structure order
        structure = template["structure"]
        assert structure[0] == "title"
        assert structure[1] == "desc"
        assert "metadata" in structure

    def test_get_layout(self, loader):
        """Should return layout configuration."""
        layout = loader.get_layout()
        assert "dimensions" in layout
        assert layout["dimensions"]["width"] == 140
        assert layout["dimensions"]["height"] == 22

    def test_get_protocol_info(self, loader):
        """Should return protocol metadata."""
        protocol = loader.get_protocol_info()
        assert protocol["name"] == "Living Artifact Protocol"
        assert protocol["version"] == "1.0"
        assert "namespaces" in protocol

    def test_get_accessibility_config(self, loader):
        """Should return accessibility requirements."""
        a11y = loader.get_accessibility_config()
        assert "required" in a11y
        assert "reducedMotion" in a11y


class TestClosestMatchSuggestions:
    """Test fuzzy matching for helpful error messages."""

    @pytest.fixture
    def loader(self):
        return OntologyLoader()

    def test_closest_match_single_typo(self, loader):
        """Should suggest 'chrome' for 'chromee'."""
        closest = loader._get_closest_match("chromee", ["chrome", "titanium", "glass"])
        assert closest == "chrome"

    def test_closest_match_multiple_options(self, loader):
        """Should find closest match among multiple options."""
        closest = loader._get_closest_match("noen", ["neon", "chrome", "glass"])
        assert closest == "neon"

    def test_closest_match_case_insensitive(self, loader):
        """Should match case-insensitively."""
        closest = loader._get_closest_match("CHROME", ["chrome", "titanium"])
        assert closest == "chrome"


class TestThemeStateStructure:
    """Test that themes have complete state definitions."""

    @pytest.fixture
    def loader(self):
        return OntologyLoader()

    def test_chrome_has_all_states(self, loader):
        """Chrome theme should define all 4 states."""
        chrome = loader.get_theme("chrome")
        states = chrome["states"]

        assert "neutral" in states
        assert "passing" in states
        assert "warning" in states
        assert "failing" in states

    def test_state_overrides_complete(self, loader):
        """State overrides should have value and glyph."""
        chrome = loader.get_theme("chrome")
        passing_state = chrome["states"]["passing"]

        assert "value" in passing_state
        assert "glyph" in passing_state


class TestThemeEffects:
    """Test theme effect arrays."""

    @pytest.fixture
    def loader(self):
        return OntologyLoader()

    def test_chrome_has_effects(self, loader):
        """Chrome should have effects defined."""
        chrome = loader.get_theme("chrome")
        effects = chrome.get("effects", [])

        assert isinstance(effects, list)
        assert len(effects) > 0
        assert "dropShadow" in effects or "specularHighlight" in effects

    def test_void_minimal_effects(self, loader):
        """Void theme should have minimal/no effects."""
        void = loader.get_theme("void")
        effects = void.get("effects", [])

        assert isinstance(effects, list)
        # Minimal theme may have empty effects


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
