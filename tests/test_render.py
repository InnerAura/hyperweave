"""Tests for the render layer: templates.py, glyphs.py, motion.py.

Covers:
- Jinja2 environment creation and caching
- Custom template filters (css_color, format_number, truncate_text, xml_escape)
- Glyph loading, auto-inference, mode resolution, badge predicate
- Motion loading, validation, CIM compliance, context building
- Template rendering (document wrapper, component fragments)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# ==========================================================================
# Fixtures
# ==========================================================================

GLYPHS_PATH = Path(__file__).resolve().parent.parent / "src" / "hyperweave" / "data" / "glyphs.json"

MOTIONS_DIR = Path(__file__).resolve().parent.parent / "src" / "hyperweave" / "data" / "motions"

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "src" / "hyperweave" / "templates"


@pytest.fixture(scope="session")
def glyphs() -> dict[str, dict[str, Any]]:
    """Load the glyph registry once for the session."""
    from hyperweave.render.glyphs import load_glyphs

    return load_glyphs(GLYPHS_PATH)


@pytest.fixture(scope="session")
def motions() -> dict[str, dict[str, Any]]:
    """Load motion configs once for the session."""
    from hyperweave.render.motion import load_motions

    return load_motions(MOTIONS_DIR)


# ==========================================================================
# templates.py -- Jinja2 environment
# ==========================================================================


class TestJinjaEnvironment:
    """Tests for create_jinja_env, get/set_templates_dir."""

    def test_get_templates_dir_default(self) -> None:
        from hyperweave.render.templates import get_templates_dir

        result = get_templates_dir()
        assert result.is_dir(), f"templates dir does not exist: {result}"
        assert (result / "document.svg.j2").exists()

    def test_create_jinja_env_returns_environment(self) -> None:
        from hyperweave.render.templates import create_jinja_env

        env = create_jinja_env()
        assert hasattr(env, "get_template")
        assert env.undefined.__name__ == "StrictUndefined"

    def test_create_jinja_env_caches(self) -> None:
        from hyperweave.render.templates import create_jinja_env

        env1 = create_jinja_env()
        env2 = create_jinja_env()
        assert env1 is env2

    def test_env_has_custom_filters(self) -> None:
        from hyperweave.render.templates import create_jinja_env

        env = create_jinja_env()
        for name in ("css_color", "format_number", "truncate_text", "xml_escape"):
            assert name in env.filters, f"missing filter: {name}"

    def test_set_templates_dir_invalidates_cache(self, tmp_path: Path) -> None:
        from hyperweave.render.templates import (
            get_templates_dir,
            set_templates_dir,
        )

        original = get_templates_dir()
        try:
            set_templates_dir(tmp_path)
            assert get_templates_dir() == tmp_path
        finally:
            # Restore
            set_templates_dir(original)

    def test_autoescape_disabled(self) -> None:
        """SVG output must not be HTML-autoescaped."""
        from hyperweave.render.templates import create_jinja_env

        env = create_jinja_env()
        assert env.autoescape is False

    def test_trim_and_lstrip_blocks(self) -> None:
        from hyperweave.render.templates import create_jinja_env

        env = create_jinja_env()
        assert env.trim_blocks is True
        assert env.lstrip_blocks is True


# ==========================================================================
# templates.py -- Custom filters
# ==========================================================================


class TestCssColorFilter:
    """Tests for _filter_css_color."""

    @pytest.fixture(autouse=True)
    def _setup_filter(self) -> None:
        from hyperweave.render.templates import create_jinja_env

        env = create_jinja_env()
        self.filter = env.filters["css_color"]

    def test_empty_returns_black(self) -> None:
        assert self.filter("") == "#000000"

    def test_hex_passthrough(self) -> None:
        assert self.filter("#FF0000") == "#FF0000"

    def test_bare_hex_gets_prefix(self) -> None:
        assert self.filter("FF0000") == "#FF0000"

    def test_bare_hex_3_digit(self) -> None:
        assert self.filter("abc") == "#abc"

    def test_bare_hex_8_digit(self) -> None:
        assert self.filter("FF000080") == "#FF000080"

    def test_rgb_passthrough(self) -> None:
        assert self.filter("rgb(255, 0, 0)") == "rgb(255, 0, 0)"

    def test_hsl_passthrough(self) -> None:
        assert self.filter("hsl(0, 100%, 50%)") == "hsl(0, 100%, 50%)"

    def test_var_passthrough(self) -> None:
        assert self.filter("var(--dna-signal)") == "var(--dna-signal)"

    def test_url_passthrough(self) -> None:
        assert self.filter("url(#grad)") == "url(#grad)"

    def test_named_color_passthrough(self) -> None:
        assert self.filter("rebeccapurple") == "rebeccapurple"


class TestFormatNumberFilter:
    """Tests for _filter_format_number."""

    @pytest.fixture(autouse=True)
    def _setup_filter(self) -> None:
        from hyperweave.render.templates import create_jinja_env

        env = create_jinja_env()
        self.filter = env.filters["format_number"]

    def test_millions(self) -> None:
        assert self.filter(1_500_000) == "1.5M"

    def test_thousands(self) -> None:
        assert self.filter(2900) == "2.9K"

    def test_integer(self) -> None:
        assert self.filter(42) == "42"

    def test_decimal(self) -> None:
        assert self.filter(3.14) == "3.1"

    def test_non_numeric_passthrough(self) -> None:
        assert self.filter("N/A") == "N/A"

    def test_zero(self) -> None:
        assert self.filter(0) == "0"

    def test_custom_precision(self) -> None:
        assert self.filter(2900, precision=2) == "2.90K"


class TestTruncateTextFilter:
    """Tests for _filter_truncate_text."""

    @pytest.fixture(autouse=True)
    def _setup_filter(self) -> None:
        from hyperweave.render.templates import create_jinja_env

        env = create_jinja_env()
        self.filter = env.filters["truncate_text"]

    def test_short_passthrough(self) -> None:
        assert self.filter("hello") == "hello"

    def test_exact_boundary(self) -> None:
        text = "a" * 30
        assert self.filter(text) == text

    def test_truncation(self) -> None:
        text = "a" * 35
        result = self.filter(text)
        assert len(result) == 30
        assert result.endswith("\u2026")

    def test_custom_max_len(self) -> None:
        result = self.filter("hello world", max_len=5)
        assert result == "hell\u2026"


class TestXmlEscapeFilter:
    """Tests for _filter_xml_escape."""

    @pytest.fixture(autouse=True)
    def _setup_filter(self) -> None:
        from hyperweave.render.templates import create_jinja_env

        env = create_jinja_env()
        self.filter = env.filters["xml_escape"]

    def test_ampersand(self) -> None:
        assert self.filter("a & b") == "a &amp; b"

    def test_angle_brackets(self) -> None:
        assert self.filter("<svg>") == "&lt;svg&gt;"

    def test_quotes(self) -> None:
        assert self.filter('x="y"') == "x=&quot;y&quot;"

    def test_apostrophe(self) -> None:
        assert self.filter("it's") == "it&apos;s"

    def test_clean_passthrough(self) -> None:
        assert self.filter("hello world") == "hello world"


# ==========================================================================
# templates.py -- render_artifact / render_template
# ==========================================================================


class TestRenderFunctions:
    """Integration tests for render_artifact and render_template."""

    def test_render_template_component(self) -> None:
        """render_template can render a component fragment."""
        from hyperweave.render.templates import render_template

        # rule.svg.j2 expects rule_id, rule_x1, rule_x2, rule_y
        ctx: dict[str, Any] = {
            "rule_id": "straight",
            "uid": "test-001",
            "rule_x1": 10,
            "rule_x2": 200,
            "rule_y": 30,
        }
        result = render_template("components/rule.svg.j2", ctx)
        assert isinstance(result, str)
        assert len(result) > 0


# ==========================================================================
# glyphs.py -- Loading
# ==========================================================================


class TestGlyphLoading:
    """Tests for load_glyphs."""

    def test_load_real_glyphs(self, glyphs: dict[str, dict[str, Any]]) -> None:
        assert len(glyphs) > 0
        assert "github" in glyphs

    def test_each_glyph_has_path(self, glyphs: dict[str, dict[str, Any]]) -> None:
        for glyph_id, data in glyphs.items():
            assert "path" in data, f"glyph '{glyph_id}' missing 'path'"
            assert len(data["path"]) > 0, f"glyph '{glyph_id}' has empty path"

    def test_each_glyph_has_viewbox(self, glyphs: dict[str, dict[str, Any]]) -> None:
        for glyph_id, data in glyphs.items():
            assert "viewBox" in data, f"glyph '{glyph_id}' missing 'viewBox'"

    def test_load_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        from hyperweave.render.glyphs import load_glyphs

        result = load_glyphs(tmp_path / "does_not_exist.json")
        assert result == {}

    def test_geometric_glyphs_present(self, glyphs: dict[str, dict[str, Any]]) -> None:
        from hyperweave.render.glyphs import GEOMETRIC_GLYPHS

        for gid in GEOMETRIC_GLYPHS:
            assert gid in glyphs, f"geometric glyph '{gid}' not in registry"


# ==========================================================================
# glyphs.py -- Auto-inference
# ==========================================================================


class TestGlyphInference:
    """Tests for infer_glyph."""

    def test_exact_match(self) -> None:
        from hyperweave.render.glyphs import infer_glyph

        assert infer_glyph("github") == "github"
        assert infer_glyph("pypi") == "pypi"
        assert infer_glyph("npm") == "npm"

    def test_case_insensitive(self) -> None:
        from hyperweave.render.glyphs import infer_glyph

        assert infer_glyph("GitHub") == "github"
        assert infer_glyph("DOCKER") == "docker"

    def test_substring_match(self) -> None:
        from hyperweave.render.glyphs import infer_glyph

        assert infer_glyph("my-github-project") == "github"

    def test_stars_maps_to_github(self) -> None:
        """Project convention: 'stars' maps to 'github', not 'star'."""
        from hyperweave.render.glyphs import infer_glyph

        assert infer_glyph("stars") == "github"

    def test_star_singular_maps_to_star(self) -> None:
        from hyperweave.render.glyphs import infer_glyph

        assert infer_glyph("star") == "star"

    def test_version_suppressed(self) -> None:
        """'version' should return empty string (no glyph)."""
        from hyperweave.render.glyphs import infer_glyph

        assert infer_glyph("version") == ""

    def test_no_match_returns_empty(self) -> None:
        from hyperweave.render.glyphs import infer_glyph

        assert infer_glyph("zzzqqqwww") == ""

    def test_empty_input(self) -> None:
        from hyperweave.render.glyphs import infer_glyph

        assert infer_glyph("") == ""

    def test_license_maps_to_shield(self) -> None:
        from hyperweave.render.glyphs import infer_glyph

        assert infer_glyph("license") == "shield"
        assert infer_glyph("MIT") == "shield"

    def test_downloads_maps_to_diamond(self) -> None:
        from hyperweave.render.glyphs import infer_glyph

        assert infer_glyph("downloads") == "diamond"

    def test_coverage_maps_to_github(self) -> None:
        from hyperweave.render.glyphs import infer_glyph

        assert infer_glyph("coverage") == "github"

    def test_social_inference(self) -> None:
        from hyperweave.render.glyphs import infer_glyph

        assert infer_glyph("twitter") == "x"
        assert infer_glyph("discord") == "discord"
        assert infer_glyph("spotify") == "spotify"


# ==========================================================================
# glyphs.py -- Mode resolution & context
# ==========================================================================


class TestGlyphModeResolution:
    """Tests for render_glyph_context auto mode resolution."""

    def test_fill_passthrough(self, glyphs: dict[str, dict[str, Any]]) -> None:
        from hyperweave.render.glyphs import render_glyph_context

        ctx = render_glyph_context("github", glyphs, mode="fill")
        assert ctx["glyph_mode"] == "fill"

    def test_wire_passthrough(self, glyphs: dict[str, dict[str, Any]]) -> None:
        from hyperweave.render.glyphs import render_glyph_context

        ctx = render_glyph_context("github", glyphs, mode="wire")
        assert ctx["glyph_mode"] == "wire"

    def test_auto_resolves_fill(self, glyphs: dict[str, dict[str, Any]]) -> None:
        from hyperweave.render.glyphs import render_glyph_context

        ctx = render_glyph_context("github", glyphs, mode="auto")
        assert ctx["glyph_mode"] == "fill"

    def test_context_has_expected_keys(self, glyphs: dict[str, dict[str, Any]]) -> None:
        from hyperweave.render.glyphs import render_glyph_context

        ctx = render_glyph_context("github", glyphs)
        expected_keys = {
            "glyph_id",
            "glyph_path",
            "glyph_viewbox",
            "glyph_category",
            "glyph_mode",
            "glyph_size",
            "has_glyph",
        }
        assert expected_keys.issubset(ctx.keys())

    def test_unknown_glyph_has_no_path(self, glyphs: dict[str, dict[str, Any]]) -> None:
        from hyperweave.render.glyphs import render_glyph_context

        ctx = render_glyph_context("nonexistent_glyph", glyphs)
        assert ctx["has_glyph"] is False
        assert ctx["glyph_path"] == ""

    def test_render_glyph_svg_is_alias(self) -> None:
        from hyperweave.render.glyphs import render_glyph_context, render_glyph_svg

        assert render_glyph_svg is render_glyph_context


# ==========================================================================
# glyphs.py -- Badge predicate
# ==========================================================================


class TestCanRenderGlyph:
    """Tests for can_render_glyph and is_geometric."""

    def test_valid_brand_glyph(self, glyphs: dict[str, dict[str, Any]]) -> None:
        from hyperweave.render.glyphs import can_render_glyph

        assert can_render_glyph("github", glyphs) is True

    def test_valid_geometric_glyph(self, glyphs: dict[str, dict[str, Any]]) -> None:
        from hyperweave.render.glyphs import can_render_glyph

        assert can_render_glyph("circle", glyphs) is True
        assert can_render_glyph("diamond", glyphs) is True

    def test_empty_id_returns_false(self, glyphs: dict[str, dict[str, Any]]) -> None:
        from hyperweave.render.glyphs import can_render_glyph

        assert can_render_glyph("", glyphs) is False

    def test_unknown_id_returns_false(self, glyphs: dict[str, dict[str, Any]]) -> None:
        from hyperweave.render.glyphs import can_render_glyph

        assert can_render_glyph("nonexistent_xyz", glyphs) is False

    def test_is_geometric(self) -> None:
        from hyperweave.render.glyphs import is_geometric

        assert is_geometric("circle") is True
        assert is_geometric("diamond") is True
        assert is_geometric("github") is False
        assert is_geometric("python") is False


# ==========================================================================
# motion.py -- Loading
# ==========================================================================


class TestMotionLoading:
    """Tests for load_motions."""

    def test_load_real_motions(self, motions: dict[str, dict[str, Any]]) -> None:
        assert len(motions) > 0
        assert "static" in motions
        assert "bars" in motions

    def test_each_motion_has_id(self, motions: dict[str, dict[str, Any]]) -> None:
        for mid, data in motions.items():
            assert data["id"] == mid

    def test_each_motion_has_css(self, motions: dict[str, dict[str, Any]]) -> None:
        for mid, data in motions.items():
            assert "css" in data, f"motion '{mid}' missing 'css'"

    def test_static_has_empty_css(self, motions: dict[str, dict[str, Any]]) -> None:
        assert motions["static"]["css"] == ""

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path) -> None:
        from hyperweave.render.motion import load_motions

        result = load_motions(tmp_path / "nope")
        assert result == {}


# ==========================================================================
# motion.py -- CSS retrieval
# ==========================================================================


class TestMotionCSS:
    """Tests for get_motion_css."""

    def test_static_returns_empty(self) -> None:
        from hyperweave.render.motion import get_motion_css

        assert get_motion_css("static", []) == ""

    def test_bars_returns_keyframes(self) -> None:
        from hyperweave.render.motion import get_motion_css

        css = get_motion_css("bars", [])
        assert "@keyframes hw-motion-bars" in css
        assert ".hw-motion-bars" in css

    def test_unknown_motion_returns_empty(self) -> None:
        from hyperweave.render.motion import get_motion_css

        assert get_motion_css("nonexistent_motion_xyz", []) == ""


# ==========================================================================
# motion.py -- Validation
# ==========================================================================


class TestMotionValidation:
    """Tests for validate_motion."""

    def test_static_always_valid(self) -> None:
        from hyperweave.render.motion import validate_motion

        assert validate_motion("static", [], "normal") == "static"

    def test_compatible_motion_passes(self) -> None:
        from hyperweave.render.motion import validate_motion

        assert validate_motion("bars", ["bars", "cascade"], "normal") == "bars"

    def test_incompatible_falls_back_to_static(self) -> None:
        from hyperweave.render.motion import validate_motion

        result = validate_motion("bars", ["cascade", "drop"], "normal")
        assert result == "static"

    def test_ungoverned_allows_anything(self) -> None:
        from hyperweave.render.motion import validate_motion

        result = validate_motion("bars", ["cascade"], "ungoverned")
        assert result == "bars"

    def test_empty_genome_list_allows_all(self) -> None:
        from hyperweave.render.motion import validate_motion

        result = validate_motion("bars", [], "normal")
        assert result == "bars"


# ==========================================================================
# motion.py -- Frame compatibility
# ==========================================================================


class TestMotionFrameCompat:
    """Tests for validate_motion_compat."""

    def test_static_always_compatible(self) -> None:
        from hyperweave.render.motion import validate_motion_compat

        valid, reason = validate_motion_compat("static", "badge")
        assert valid is True
        assert reason == ""

    def test_bars_compatible_with_banner(self) -> None:
        from hyperweave.render.motion import validate_motion_compat

        valid, _reason = validate_motion_compat("bars", "banner")
        assert valid is True

    def test_bars_not_compatible_with_divider(self) -> None:
        """bars.yaml applies_to does not include divider."""
        from hyperweave.render.motion import validate_motion_compat

        valid, reason = validate_motion_compat("bars", "divider", "normal")
        assert valid is False
        assert "divider" in reason

    def test_permissive_allows_incompatible_frame(self) -> None:
        from hyperweave.render.motion import validate_motion_compat

        valid, _reason = validate_motion_compat("bars", "divider", "permissive")
        assert valid is True

    def test_unknown_motion_rejected(self) -> None:
        from hyperweave.render.motion import validate_motion_compat

        valid, reason = validate_motion_compat("fake_motion", "badge", "normal")
        assert valid is False
        assert "unknown" in reason


# ==========================================================================
# motion.py -- CIM compliance
# ==========================================================================


class TestCIMCompliance:
    """Tests for is_cim_compliant."""

    def test_static_is_compliant(self) -> None:
        from hyperweave.render.motion import is_cim_compliant

        assert is_cim_compliant("static") is True

    def test_bars_is_compliant(self) -> None:
        from hyperweave.render.motion import is_cim_compliant

        assert is_cim_compliant("bars") is True

    def test_cascade_is_compliant(self) -> None:
        from hyperweave.render.motion import is_cim_compliant

        assert is_cim_compliant("cascade") is True


# ==========================================================================
# motion.py -- Context builder
# ==========================================================================


class TestBuildMotionContext:
    """Tests for build_motion_context."""

    def test_static_context(self) -> None:
        from hyperweave.render.motion import build_motion_context

        ctx = build_motion_context("static", "badge")
        assert ctx["motion_id"] == "static"
        assert ctx["motion_css"] == ""
        assert ctx["motion_class"] == ""
        assert ctx["motion_valid"] is True
        assert ctx["motion_cim_compliant"] is True

    def test_bars_context(self) -> None:
        from hyperweave.render.motion import build_motion_context

        ctx = build_motion_context("bars", "banner")
        assert ctx["motion_id"] == "bars"
        assert "@keyframes" in ctx["motion_css"]
        assert ctx["motion_class"] == "hw-motion-bars"
        assert ctx["motion_valid"] is True

    def test_incompatible_falls_back(self) -> None:
        from hyperweave.render.motion import build_motion_context

        ctx = build_motion_context("bars", "divider", "normal")
        assert ctx["motion_id"] == "static"
        assert ctx["motion_class"] == ""

    def test_context_has_expected_keys(self) -> None:
        from hyperweave.render.motion import build_motion_context

        ctx = build_motion_context("static", "badge")
        expected_keys = {
            "motion_id",
            "motion_css",
            "motion_valid",
            "motion_reason",
            "motion_class",
            "motion_category",
            "motion_cim_compliant",
        }
        assert expected_keys == set(ctx.keys())


# ==========================================================================
# motion.py -- Introspection
# ==========================================================================


class TestListMotions:
    """Tests for list_motions."""

    def test_returns_list(self) -> None:
        from hyperweave.render.motion import list_motions

        result = list_motions()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_sorted_by_id(self) -> None:
        from hyperweave.render.motion import list_motions

        result = list_motions()
        ids = [m["id"] for m in result]
        assert ids == sorted(ids)

    def test_each_entry_has_required_keys(self) -> None:
        from hyperweave.render.motion import list_motions

        for entry in list_motions():
            assert "id" in entry
            assert "name" in entry
            assert "category" in entry
            assert "cim_compliant" in entry
            assert "applies_to" in entry

    def test_static_in_list(self) -> None:
        from hyperweave.render.motion import list_motions

        ids = {m["id"] for m in list_motions()}
        assert "static" in ids
        assert "bars" in ids


# ==========================================================================
# render/__init__.py -- Public API surface
# ==========================================================================


class TestRenderPackageExports:
    """Verify the render package exports all declared symbols."""

    def test_all_exports_importable(self) -> None:
        import hyperweave.render as render_pkg

        for name in render_pkg.__all__:
            assert hasattr(render_pkg, name), f"missing export: {name}"

    def test_template_functions_exported(self) -> None:
        from hyperweave.render import (
            create_jinja_env,
            get_templates_dir,
            render_artifact,
            render_template,
            set_templates_dir,
        )

        assert callable(create_jinja_env)
        assert callable(get_templates_dir)
        assert callable(render_artifact)
        assert callable(render_template)
        assert callable(set_templates_dir)

    def test_glyph_functions_exported(self) -> None:
        from hyperweave.render import (
            GEOMETRIC_GLYPHS,
            can_render_glyph,
            infer_glyph,
            is_geometric,
            load_glyphs,
            render_glyph_context,
            render_glyph_svg,
        )

        assert callable(infer_glyph)
        assert callable(load_glyphs)
        assert callable(render_glyph_context)
        assert callable(render_glyph_svg)
        assert callable(can_render_glyph)
        assert callable(is_geometric)
        assert isinstance(GEOMETRIC_GLYPHS, frozenset)

    def test_motion_functions_exported(self) -> None:
        from hyperweave.render import (
            build_motion_context,
            get_motion_css,
            get_motion_info,
            get_motions_dir,
            is_cim_compliant,
            list_motions,
            load_motions,
            validate_motion,
            validate_motion_compat,
        )

        assert callable(build_motion_context)
        assert callable(get_motion_css)
        assert callable(get_motion_info)
        assert callable(get_motions_dir)
        assert callable(is_cim_compliant)
        assert callable(list_motions)
        assert callable(load_motions)
        assert callable(validate_motion)
        assert callable(validate_motion_compat)
