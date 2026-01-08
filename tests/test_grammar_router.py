"""
Integration tests for URL Grammar Router (v7 theme-centric).

Tests cover:
- Dynamic theme loading from ontology
- Motion validation and compatibility
- BadgeRequest construction with theme field
- Error handling (404 theme, 400 motion)
- Response headers and metadata
"""

import pytest
from fastapi import HTTPException

from hyperweave.api.routers.grammar import (
    get_theme_config,
    parse_data_source,
    parse_style_chain,
    validate_motion,
)

# ─── THEME LOADING ───────────────────────────────────────────────────────────


def test_theme_loading_chrome():
    """Should load chrome theme from ontology."""
    theme = get_theme_config("chrome")

    assert theme["id"] == "chrome"
    assert theme["tier"] == "industrial"
    assert theme["series"] == "core"
    assert "compatibleMotions" in theme


def test_theme_loading_all_20_themes():
    """Should successfully load all 20 themes dynamically."""
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
        theme = get_theme_config(theme_id)
        assert theme["id"] == theme_id
        assert "tier" in theme
        assert "series" in theme
        assert "compatibleMotions" in theme


def test_theme_loading_invalid_raises_404():
    """Should raise HTTPException 404 for invalid theme."""
    with pytest.raises(HTTPException) as exc_info:
        get_theme_config("nonexistent-theme")

    assert exc_info.value.status_code == 404
    assert "Theme not found" in str(exc_info.value.detail)


def test_theme_loading_suggestion_for_typo():
    """Should suggest similar theme for typo."""
    with pytest.raises(HTTPException) as exc_info:
        get_theme_config("chrom")  # Missing 'e'

    detail = exc_info.value.detail
    assert detail["theme"] == "chrom"
    assert "suggestion" in detail
    assert detail["suggestion"] == "chrome"


def test_theme_loading_lists_available():
    """Should list all available themes in error (20 original + 5 arcade = 25)."""
    with pytest.raises(HTTPException) as exc_info:
        get_theme_config("invalid")

    detail = exc_info.value.detail
    assert "available_themes" in detail
    assert len(detail["available_themes"]) == 25
    assert "chrome" in detail["available_themes"]
    assert "arcade-snes" in detail["available_themes"]


# ─── MOTION VALIDATION ───────────────────────────────────────────────────────


def test_motion_validation_compatible():
    """Should validate compatible motion."""
    theme = get_theme_config("chrome")
    motion = validate_motion(theme, "sweep")

    assert motion == "sweep"


def test_motion_validation_default_when_none():
    """Should return first compatible motion when None."""
    theme = get_theme_config("chrome")
    motion = validate_motion(theme, None)

    # Chrome's compatibleMotions: ["static", "sweep", "breathe", ...]
    # First one is default
    assert motion == theme["compatibleMotions"][0]


def test_motion_validation_incompatible_raises_400():
    """Should raise HTTPException 400 for incompatible motion."""
    theme = get_theme_config("brutalist")

    with pytest.raises(HTTPException) as exc_info:
        validate_motion(theme, "sweep")  # Brutalist doesn't support sweep

    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert detail["error"] == "Motion incompatible with theme"
    assert detail["theme"] == "brutalist"
    assert detail["motion"] == "sweep"
    assert "compatible_motions" in detail


def test_motion_validation_all_themes_have_defaults():
    """Should validate all themes have default motion."""
    theme_ids = [
        "chrome",
        "glass",
        "neon",
        "titanium",
        "obsidian",
        "brutalist",
        "brutalist-clean",
        "codex",
        "theorem",
        "archive",
        "symposium",
        "cipher",
        "void",
        "sakura",
        "aurora",
        "singularity",
        "depth",
        "glossy",
        "holo",
        "clarity",
    ]

    for theme_id in theme_ids:
        theme = get_theme_config(theme_id)
        default_motion = validate_motion(theme, None)
        assert default_motion is not None
        assert default_motion in theme["compatibleMotions"]


# ─── DATA SOURCE PARSING ─────────────────────────────────────────────────────


def test_parse_data_source_github():
    """Should parse GitHub data source pattern."""
    provider, params = parse_data_source("github.readme-ai.eli64s.stars")

    assert provider == "github"
    assert params["owner"] == "readme-ai"
    assert params["repo"] == "eli64s"
    assert params["metric"] == "stars"


def test_parse_data_source_static():
    """Should parse static data source pattern."""
    provider, params = parse_data_source("static.passing")

    assert provider == "static"
    assert params["value"] == "passing"


def test_parse_data_source_invalid_raises_400():
    """Should raise HTTPException for invalid pattern."""
    with pytest.raises(HTTPException) as exc_info:
        parse_data_source("invalid")

    assert exc_info.value.status_code == 400


# ─── STYLE CHAIN PARSING ─────────────────────────────────────────────────────


def test_parse_style_chain_with_motion():
    """Should parse style chain with motion."""
    theme, motion, format_type = parse_style_chain("chrome.sweep.svg")

    assert theme == "chrome"
    assert motion == "sweep"
    assert format_type == "svg"


def test_parse_style_chain_without_motion():
    """Should parse style chain without motion."""
    theme, motion, format_type = parse_style_chain("glass.svg")

    assert theme == "glass"
    assert motion is None
    assert format_type == "svg"


def test_parse_style_chain_json_format():
    """Should parse JSON format."""
    theme, motion, format_type = parse_style_chain("neon.pulse.json")

    assert theme == "neon"
    assert motion == "pulse"
    assert format_type == "json"


def test_parse_style_chain_invalid_raises_400():
    """Should raise HTTPException for invalid pattern."""
    with pytest.raises(HTTPException) as exc_info:
        parse_style_chain("invalid")

    assert exc_info.value.status_code == 400


# ─── INTEGRATION TESTS (Endpoint) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_endpoint_static_chrome():
    """Should generate badge for static.passing/chrome.svg."""
    from httpx import ASGITransport, AsyncClient

    from hyperweave.api.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/static.passing/chrome.svg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml; charset=utf-8"
    assert response.headers["x-theme"] == "chrome"
    assert response.headers["x-theme-tier"] == "industrial"
    assert response.headers["x-ontology-version"] == "7.0.0"

    # Verify SVG content
    svg = response.text
    assert "<svg" in svg
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg
    assert 'xmlns:hw="https://hyperweave.dev/hw/v1.0"' in svg


@pytest.mark.asyncio
async def test_endpoint_static_with_motion():
    """Should generate badge with motion."""
    from httpx import ASGITransport, AsyncClient

    from hyperweave.api.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/static.passing/chrome.sweep.svg")

    assert response.status_code == 200
    assert response.headers["x-motion"] == "sweep"


@pytest.mark.asyncio
async def test_endpoint_json_format():
    """Should return JSON format."""
    from httpx import ASGITransport, AsyncClient

    from hyperweave.api.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/static.passing/chrome.json")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")

    data = response.json()
    assert "svg_content" in data
    assert "theme_dna" in data
    assert "metadata" in data
    assert data["theme_dna"]["theme"] == "chrome"


@pytest.mark.asyncio
async def test_endpoint_invalid_theme_404():
    """Should return 404 for invalid theme."""
    from httpx import ASGITransport, AsyncClient

    from hyperweave.api.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/static.passing/invalid-theme.svg")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"] == "Theme not found"


@pytest.mark.asyncio
async def test_endpoint_invalid_motion_400():
    """Should return 400 for incompatible motion."""
    from httpx import ASGITransport, AsyncClient

    from hyperweave.api.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/static.passing/brutalist.sweep.svg")

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "Motion incompatible with theme"


@pytest.mark.asyncio
async def test_endpoint_all_20_themes():
    """Should generate badges for all 20 themes."""
    from httpx import ASGITransport, AsyncClient

    from hyperweave.api.server import app

    theme_ids = [
        "chrome",
        "titanium",
        "obsidian",
        "neon",
        "glass",
        "holo",
        "clarity",
        "depth",
        "glossy",
        "brutalist",
        "brutalist-clean",
        "sakura",
        "aurora",
        "singularity",
        "codex",
        "theorem",
        "archive",
        "symposium",
        "cipher",
        "void",
    ]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for theme_id in theme_ids:
            response = await client.get(f"/static.passing/{theme_id}.svg")
            assert response.status_code == 200, f"Failed for theme: {theme_id}"
            assert response.headers["x-theme"] == theme_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
