"""
Tests for HyperWeave MCP Server components.

Tests cover:
- Enum definitions for schema validation
- Ontology query logic (underlying data access)
- Specimen to theme mapping
- Badge generation through core generator
- SVG validation logic

Note: Direct MCP server import tests are skipped if FastMCP has Pydantic
compatibility issues. Core functionality is tested through the ontology
and generator modules.
"""

import pytest

from hyperweave.core.ontology import OntologyLoader
from hyperweave.models.ontology import (
    BadgeState,
    OntologyCategory,
    ThemeSeries,
    ThemeTier,
)


class TestEnumDefinitions:
    """Test enum definitions for MCP schema validation."""

    def test_ontology_category_values(self):
        """Should have all required ontology categories."""
        assert OntologyCategory.THEMES.value == "themes"
        assert OntologyCategory.MOTIONS.value == "motions"
        assert OntologyCategory.GLYPHS.value == "glyphs"
        assert OntologyCategory.EFFECTS.value == "effects"

    def test_theme_tier_values(self):
        """Should have all 8 theme tiers."""
        expected_tiers = [
            "minimal",
            "flagship",
            "premium",
            "industrial",
            "brutalist",
            "cosmology",
            "scholarly",
            "arcade",
        ]
        actual_tiers = [tier.value for tier in ThemeTier]
        assert sorted(actual_tiers) == sorted(expected_tiers)

    def test_theme_series_values(self):
        """Should have all 3 theme series."""
        assert ThemeSeries.CORE.value == "core"
        assert ThemeSeries.FIVE_SCHOLARS.value == "five-scholars"
        assert ThemeSeries.RETRO_CONSOLE.value == "retro-console"

    def test_badge_state_values(self):
        """Should have all badge states."""
        expected_states = [
            "passing",
            "warning",
            "failing",
            "neutral",
            "active",
            "live",
            "protected",
        ]
        actual_states = [state.value for state in BadgeState]
        assert sorted(actual_states) == sorted(expected_states)


class TestEnumStringComparison:
    """Test that str Enums work correctly in string comparisons."""

    def test_ontology_category_string_comparison(self):
        """Should support string comparison for category enums."""
        assert OntologyCategory.THEMES == "themes"
        assert OntologyCategory.MOTIONS == "motions"
        assert OntologyCategory.GLYPHS == "glyphs"
        assert OntologyCategory.EFFECTS == "effects"

        # Also test inequality
        assert OntologyCategory.THEMES != "motions"

    def test_theme_tier_string_comparison(self):
        """Should support string comparison for tier enums."""
        assert ThemeTier.MINIMAL == "minimal"
        assert ThemeTier.FLAGSHIP == "flagship"
        assert ThemeTier.INDUSTRIAL == "industrial"
        assert ThemeTier.SCHOLARLY == "scholarly"
        assert ThemeTier.ARCADE == "arcade"

    def test_theme_series_string_comparison(self):
        """Should support string comparison for series enums."""
        assert ThemeSeries.CORE == "core"
        assert ThemeSeries.FIVE_SCHOLARS == "five-scholars"
        assert ThemeSeries.RETRO_CONSOLE == "retro-console"

    def test_enum_in_dict_key_lookup(self):
        """Should work as dict key via string inheritance."""
        # This pattern is used in MCP server
        test_dict = {"themes": [1, 2, 3], "motions": [4, 5, 6]}

        # Enum should work as key
        assert test_dict[OntologyCategory.THEMES.value] == [1, 2, 3]


class TestOntologyQueryLogic:
    """Test ontology query logic (underlying function behavior)."""

    @pytest.fixture
    def ontology(self):
        """Shared ontology instance."""
        return OntologyLoader()

    def test_get_all_themes_returns_dict(self, ontology):
        """Should return dict of all themes."""
        themes = ontology.get_all_themes()
        assert isinstance(themes, dict)
        assert len(themes) == 25  # 20 original + 5 arcade
        assert "chrome" in themes

    def test_get_themes_by_tier_returns_list(self, ontology):
        """Should return list of themes for tier."""
        themes = ontology.get_themes_by_tier("industrial")
        assert isinstance(themes, list)
        assert len(themes) == 3  # chrome, titanium, obsidian

        # Verify each item is a dict with "id" key
        for theme in themes:
            assert isinstance(theme, dict)
            assert "id" in theme

    def test_get_themes_by_tier_accepts_enum(self, ontology):
        """Should accept ThemeTier enum as filter."""
        # str Enum should work since it inherits from str
        themes = ontology.get_themes_by_tier(ThemeTier.INDUSTRIAL)
        assert isinstance(themes, list)
        assert len(themes) == 3

    def test_get_themes_by_series_returns_list(self, ontology):
        """Should return list of themes for series."""
        themes = ontology.get_themes_by_series("five-scholars")
        assert isinstance(themes, list)
        assert len(themes) == 5  # codex, theorem, archive, symposium, cipher

        for theme in themes:
            assert isinstance(theme, dict)
            assert "id" in theme

    def test_get_themes_by_series_accepts_enum(self, ontology):
        """Should accept ThemeSeries enum as filter."""
        themes = ontology.get_themes_by_series(ThemeSeries.FIVE_SCHOLARS)
        assert isinstance(themes, list)
        assert len(themes) == 5

    def test_get_themes_by_arcade_tier(self, ontology):
        """Should return arcade themes."""
        themes = ontology.get_themes_by_tier(ThemeTier.ARCADE)
        assert isinstance(themes, list)
        assert len(themes) == 5  # 5 arcade themes

        arcade_ids = [t["id"] for t in themes]
        assert "arcade-snes" in arcade_ids
        assert "arcade-gameboy" in arcade_ids

    def test_get_all_motions_returns_dict(self, ontology):
        """Should return dict of all motion definitions."""
        motions = ontology.get_all_motions()
        assert isinstance(motions, dict)
        assert len(motions) >= 8  # At least 8 motion primitives
        assert "breathe" in motions

    def test_get_all_glyphs_returns_dict(self, ontology):
        """Should return dict of all glyph definitions."""
        glyphs = ontology.get_all_glyphs()
        assert isinstance(glyphs, dict)
        assert len(glyphs) >= 10  # At least 10 glyph types
        assert "dot" in glyphs

    def test_get_theme_returns_complete_config(self, ontology):
        """Should return complete theme configuration."""
        chrome = ontology.get_theme("chrome")
        assert chrome["id"] == "chrome"
        assert chrome["tier"] == "industrial"
        assert chrome["series"] == "core"
        assert "compatibleMotions" in chrome


class TestSpecimenToThemeMapping:
    """Test specimen to theme mapping logic."""

    SPECIMEN_THEME_MAP = {
        "chrome-protocol": "chrome",
        "obsidian-mirror": "obsidian",
        "titanium-forge": "titanium",
        "brutalist-signal": "brutalist",
        "brutalist-minimal": "brutalist-clean",
    }

    @pytest.fixture
    def ontology(self):
        """Shared ontology instance."""
        return OntologyLoader()

    def test_specimen_themes_exist(self, ontology):
        """All specimen themes should exist in ontology."""
        for specimen_id, theme_id in self.SPECIMEN_THEME_MAP.items():
            theme = ontology.get_theme(theme_id)
            assert theme is not None, f"Theme {theme_id} for specimen {specimen_id} not found"
            assert theme["id"] == theme_id

    def test_specimen_count(self):
        """Should have 5 pre-validated specimens."""
        assert len(self.SPECIMEN_THEME_MAP) == 5

    def test_specimen_theme_tiers(self, ontology):
        """Specimen themes should span multiple tiers."""
        tiers = set()
        for theme_id in self.SPECIMEN_THEME_MAP.values():
            theme = ontology.get_theme(theme_id)
            tiers.add(theme["tier"])

        # Should include industrial and brutalist at minimum
        assert "industrial" in tiers
        assert "brutalist" in tiers


class TestBadgeGenerationThroughCore:
    """Test badge generation through core generator."""

    @pytest.fixture
    def generator(self):
        """Create BadgeGenerator instance with ontology."""
        from hyperweave.core.generator import BadgeGenerator

        ontology = OntologyLoader()
        return BadgeGenerator(ontology=ontology)

    def test_generator_exists(self, generator):
        """Should instantiate BadgeGenerator."""
        assert generator is not None

    def test_chrome_theme_generation(self, generator):
        """Should generate badge with chrome theme."""
        from hyperweave.models.badge import BadgeContent, BadgeRequest

        request = BadgeRequest(
            theme="chrome",
            content=BadgeContent(label="status", value="passing"),
        )

        response = generator.generate(request)

        assert response.svg is not None
        assert "<svg" in response.svg
        assert response.theme_dna.theme == "chrome"
        assert response.theme_dna.tier == "industrial"

    def test_scholarly_theme_generation(self, generator):
        """Should generate badge with scholarly theme."""
        from hyperweave.models.badge import BadgeContent, BadgeRequest

        request = BadgeRequest(
            theme="codex",
            content=BadgeContent(label="docs", value="complete"),
        )

        response = generator.generate(request)

        assert response.svg is not None
        assert "<svg" in response.svg
        assert response.theme_dna.theme == "codex"
        assert response.theme_dna.tier == "scholarly"

    def test_arcade_theme_generation(self, generator):
        """Should generate badge with arcade theme."""
        from hyperweave.models.badge import BadgeContent, BadgeRequest

        request = BadgeRequest(
            theme="arcade-snes",
            content=BadgeContent(label="retro", value="gaming"),
        )

        response = generator.generate(request)

        assert response.svg is not None
        assert "<svg" in response.svg
        assert response.theme_dna.theme == "arcade-snes"
        assert response.theme_dna.tier == "arcade"

    def test_badge_with_state(self, generator):
        """Should apply state-specific styling."""
        from hyperweave.models.badge import BadgeContent, BadgeRequest

        request = BadgeRequest(
            theme="chrome",
            content=BadgeContent(label="build", value="passing", state=BadgeState.PASSING),
        )

        response = generator.generate(request)
        assert response.svg is not None
        assert "<svg" in response.svg

    def test_badge_with_motion(self, generator):
        """Should include motion when specified."""
        from hyperweave.models.badge import BadgeContent, BadgeRequest

        # Use 'sweep' which is compatible with chrome theme
        # Chrome compatibleMotions: static, breathe, sweep
        request = BadgeRequest(
            theme="chrome",
            content=BadgeContent(label="status", value="live"),
            motion="sweep",
        )

        response = generator.generate(request)
        assert response.svg is not None
        # Motion should be reflected in theme_dna
        assert response.theme_dna.motion == "sweep"


class TestSVGOutputStructure:
    """Test SVG output structure and validity."""

    @pytest.fixture
    def generator(self):
        """Create BadgeGenerator instance with ontology."""
        from hyperweave.core.generator import BadgeGenerator

        ontology = OntologyLoader()
        return BadgeGenerator(ontology=ontology)

    def test_svg_has_namespace(self, generator):
        """Generated SVG should have proper namespace."""
        from hyperweave.models.badge import BadgeContent, BadgeRequest

        request = BadgeRequest(
            theme="chrome",
            content=BadgeContent(label="test", value="badge"),
        )

        response = generator.generate(request)
        assert 'xmlns="http://www.w3.org/2000/svg"' in response.svg

    def test_svg_has_viewbox(self, generator):
        """Generated SVG should have viewBox attribute."""
        from hyperweave.models.badge import BadgeContent, BadgeRequest

        request = BadgeRequest(
            theme="chrome",
            content=BadgeContent(label="test", value="badge"),
        )

        response = generator.generate(request)
        assert "viewBox" in response.svg

    def test_svg_has_accessibility_attributes(self, generator):
        """Generated SVG should include accessibility elements."""
        from hyperweave.models.badge import BadgeContent, BadgeRequest

        request = BadgeRequest(
            theme="chrome",
            content=BadgeContent(label="build", value="passing"),
            artifact_tier="FULL",
        )

        response = generator.generate(request)
        # FULL tier should include title and desc for a11y
        # Note: Title has id attribute like <title id="hw-title">
        assert "<title" in response.svg
        assert "<desc" in response.svg
        assert 'role="img"' in response.svg

    def test_svg_is_self_contained(self, generator):
        """Generated SVG should not have external dependencies."""
        from hyperweave.models.badge import BadgeContent, BadgeRequest

        request = BadgeRequest(
            theme="chrome",
            content=BadgeContent(label="test", value="badge"),
        )

        response = generator.generate(request)
        # Should not reference external stylesheets or scripts
        assert 'href="http' not in response.svg
        assert "<script" not in response.svg


class TestMCPServerImportOptional:
    """Test MCP server import (skipped if FastMCP has compatibility issues)."""

    def test_server_module_structure(self):
        """Should have proper module structure."""
        try:
            from hyperweave.mcp import server

            # If import succeeds, verify structure
            assert hasattr(server, "mcp")
            assert hasattr(server, "get_ontology")
            assert hasattr(server, "wrap_response")
        except (TypeError, ImportError) as e:
            if "default and default_factory" in str(e):
                pytest.skip("FastMCP has Pydantic compatibility issue")
            raise

    def test_wrap_response_function(self):
        """Should have wrap_response helper."""
        try:
            from hyperweave.mcp.server import wrap_response

            result = wrap_response(
                data={"test": True},
                suggested_next_action="Next step",
            )
            assert result["data"] == {"test": True}
            assert result["suggested_next_action"] == "Next step"
        except (TypeError, ImportError) as e:
            if "default and default_factory" in str(e):
                pytest.skip("FastMCP has Pydantic compatibility issue")
            raise
