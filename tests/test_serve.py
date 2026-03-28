"""Tests for serve/app.py -- FastAPI HTTP endpoints.

Covers URL grammar routes, POST /v1/compose, /v1/live/ (mocked),
discovery endpoints, namespace routes (/g/, /a/, /d/), ETag 304
negotiation, error badge rendering, and Camo-hardening middleware.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from hyperweave.core.models import ComposeResult
from hyperweave.serve.app import (
    _etag_matches,
    _parse_genome_motion,
    app,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MOCK_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="22"><text>mock</text></svg>'
MOCK_RESULT = ComposeResult(svg=MOCK_SVG, width=120, height=22)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def client() -> Any:
    """Async test client wrapping the FastAPI app via ASGI transport."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture()
def mock_compose() -> Any:
    """Patch compose() in the engine module so HTTP tests stay fast."""
    with patch("hyperweave.compose.engine.compose", return_value=MOCK_RESULT) as m:
        yield m


@pytest.fixture(autouse=True)
def _reset_specimens_cache() -> Any:
    """Reset the module-level specimens cache between tests."""
    import hyperweave.serve.app as app_mod

    app_mod._specimens_cache = None
    yield
    app_mod._specimens_cache = None


# ===========================================================================
# Helpers
# ===========================================================================


def test_parse_genome_motion_with_dot() -> None:
    assert _parse_genome_motion("brutalist-emerald.cascade") == ("brutalist-emerald", "cascade")


def test_parse_genome_motion_without_dot() -> None:
    assert _parse_genome_motion("brutalist-emerald") == ("brutalist-emerald", "static")


def test_parse_genome_motion_multiple_dots() -> None:
    assert _parse_genome_motion("some.complex.name.drop") == ("some.complex.name", "drop")


def test_etag_matches_exact() -> None:
    assert _etag_matches('"abc123"', '"abc123"') is True


def test_etag_matches_without_quotes() -> None:
    assert _etag_matches("abc123", '"abc123"') is True


def test_etag_matches_wildcard() -> None:
    assert _etag_matches("*", '"anything"') is True


def test_etag_matches_comma_list() -> None:
    assert _etag_matches('"old", "abc123", "newer"', '"abc123"') is True


def test_etag_no_match() -> None:
    assert _etag_matches('"other"', '"abc123"') is False


# ===========================================================================
# URL Grammar Routes
# ===========================================================================


async def test_badge_url_returns_svg(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/badge/build/passing/brutalist-emerald.static")
    assert resp.status_code == 200
    assert "image/svg+xml" in resp.headers["content-type"]
    assert "<svg" in resp.text


async def test_badge_url_default_motion(client: AsyncClient, mock_compose: Any) -> None:
    """No dot in genome_motion defaults to static motion."""
    resp = await client.get("/v1/badge/build/passing/brutalist-emerald")
    assert resp.status_code == 200


async def test_badge_url_with_glyph(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/badge/build/passing/brutalist-emerald.static?glyph=github")
    assert resp.status_code == 200


async def test_strip_url_returns_svg(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/strip/readme-ai/brutalist-emerald.static?value=STARS:2.9k,FORKS:278")
    assert resp.status_code == 200
    assert "image/svg+xml" in resp.headers["content-type"]


async def test_banner_url_returns_svg(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/banner/HYPERWEAVE/brutalist-emerald.cascade?value=Living+Artifacts")
    assert resp.status_code == 200
    assert "image/svg+xml" in resp.headers["content-type"]


async def test_icon_url_returns_svg(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/icon/github/brutalist-emerald.static")
    assert resp.status_code == 200


async def test_divider_url_returns_svg(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/divider/void/brutalist-emerald.static")
    assert resp.status_code == 200


async def test_marquee_horizontal(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/marquee/HYPERWEAVE/brutalist-emerald.static?direction=ltr&rows=1")
    assert resp.status_code == 200


async def test_marquee_vertical(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/marquee/HYPERWEAVE/brutalist-emerald.static?direction=up&rows=1")
    assert resp.status_code == 200


async def test_marquee_counter(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/marquee/ROW1%7CROW2%7CROW3/brutalist-emerald.static?rows=3")
    assert resp.status_code == 200


# ===========================================================================
# POST /v1/compose
# ===========================================================================


async def test_compose_post_badge(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.post(
        "/v1/compose",
        json={"type": "badge", "title": "build", "value": "passing"},
    )
    assert resp.status_code == 200
    assert "image/svg+xml" in resp.headers["content-type"]


async def test_compose_post_strip(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.post(
        "/v1/compose",
        json={"type": "strip", "title": "readme-ai", "value": "STARS:2.9k"},
    )
    assert resp.status_code == 200


async def test_compose_post_defaults(client: AsyncClient, mock_compose: Any) -> None:
    """Empty body uses all defaults (badge, brutalist-emerald, static)."""
    resp = await client.post("/v1/compose", json={})
    assert resp.status_code == 200


# ===========================================================================
# /v1/live/ (mocked connector)
# ===========================================================================


async def test_live_badge_success(client: AsyncClient) -> None:
    mock_data = {"value": 5000, "ttl": 300}
    with (
        patch("hyperweave.connectors.fetch_metric", new_callable=AsyncMock, return_value=mock_data),
        patch("hyperweave.compose.engine.compose", return_value=MOCK_RESULT),
    ):
        resp = await client.get("/v1/live/github/anthropics/claude-code/stars/brutalist-emerald.static")
        assert resp.status_code == 200
        assert resp.headers.get("x-hw-provider") == "github"
        assert "stale-while-revalidate" in resp.headers.get("cache-control", "")


async def test_live_badge_connector_error(client: AsyncClient) -> None:
    with (
        patch("hyperweave.connectors.fetch_metric", new_callable=AsyncMock, side_effect=Exception("timeout")),
        patch("hyperweave.compose.engine.compose", return_value=MOCK_RESULT),
    ):
        resp = await client.get("/v1/live/github/anthropics/claude-code/stars/brutalist-emerald")
        assert resp.status_code == 200
        assert resp.headers.get("x-hw-cache-tier") == "error"


# ===========================================================================
# Discovery endpoints
# ===========================================================================


async def test_list_genomes(client: AsyncClient) -> None:
    resp = await client.get("/v1/genomes")
    assert resp.status_code == 200
    ids = [g["id"] for g in resp.json()]
    assert "brutalist-emerald" in ids
    assert "chrome-horizon" in ids


async def test_get_genome_found(client: AsyncClient) -> None:
    resp = await client.get("/v1/genomes/brutalist-emerald")
    assert resp.status_code == 200


async def test_get_genome_not_found(client: AsyncClient) -> None:
    resp = await client.get("/v1/genomes/nonexistent")
    assert resp.status_code == 404


async def test_list_motions(client: AsyncClient) -> None:
    resp = await client.get("/v1/motions")
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()]
    assert "static" in ids


async def test_list_glyphs(client: AsyncClient) -> None:
    resp = await client.get("/v1/glyphs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert "github" in data


# ===========================================================================
# Namespace /g/ -- Genome Registry
# ===========================================================================


async def test_genome_registry_found(client: AsyncClient) -> None:
    resp = await client.get("/g/brutalist-emerald")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert "stale-while-revalidate" in resp.headers.get("cache-control", "")


async def test_genome_registry_not_found(client: AsyncClient) -> None:
    resp = await client.get("/g/nonexistent-genome")
    assert resp.status_code == 404


# ===========================================================================
# Namespace /a/ -- Artifact Store
# ===========================================================================


async def test_list_specimens(client: AsyncClient) -> None:
    registry = {"badge-build": "genomes/brutalist-emerald/badge_build.svg"}
    with patch("hyperweave.serve.app._load_specimens_registry", return_value=registry):
        resp = await client.get("/a/inneraura")
        assert resp.status_code == 200
        slugs = [s["slug"] for s in resp.json()]
        assert "badge-build" in slugs


async def test_serve_specimen_not_found(client: AsyncClient) -> None:
    with patch("hyperweave.serve.app._load_specimens_registry", return_value={}):
        resp = await client.get("/a/inneraura/nonexistent")
        assert resp.status_code == 404


async def test_specimen_meta_not_found(client: AsyncClient) -> None:
    with patch("hyperweave.serve.app._load_specimens_registry", return_value={}):
        resp = await client.get("/a/inneraura/nonexistent/meta.json")
        assert resp.status_code == 404


# ===========================================================================
# Namespace /d/ -- Drop Events
# ===========================================================================


async def test_drop_metadata(client: AsyncClient) -> None:
    resp = await client.get("/d/001-brutalist-emerald")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "001-brutalist-emerald"
    assert data["sequence"] == "001"
    assert data["name"] == "brutalist-emerald"
    assert "/g/" in data["genome_url"]


# ===========================================================================
# ETag 304 Negotiation
# ===========================================================================


async def test_etag_returned_on_compose(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/badge/build/passing/brutalist-emerald")
    assert resp.status_code == 200
    assert "etag" in resp.headers


async def test_304_on_matching_etag(client: AsyncClient, mock_compose: Any) -> None:
    resp1 = await client.get("/v1/badge/build/passing/brutalist-emerald")
    etag = resp1.headers["etag"]

    resp2 = await client.get(
        "/v1/badge/build/passing/brutalist-emerald",
        headers={"if-none-match": etag},
    )
    assert resp2.status_code == 304


async def test_200_on_different_etag(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get(
        "/v1/badge/build/passing/brutalist-emerald",
        headers={"if-none-match": '"completely-different"'},
    )
    assert resp.status_code == 200


# ===========================================================================
# Error handling
# ===========================================================================


async def test_compose_error_returns_500_svg(client: AsyncClient) -> None:
    error_svg = '<svg xmlns="http://www.w3.org/2000/svg"><text>error</text></svg>'
    with (
        patch("hyperweave.compose.engine.compose", side_effect=ValueError("render failed")),
        patch("hyperweave.serve.app._error_badge", return_value=error_svg),
    ):
        resp = await client.get("/v1/badge/build/passing/brutalist-emerald")
        assert resp.status_code == 500
        assert "image/svg+xml" in resp.headers["content-type"]


# ===========================================================================
# Camo-hardening middleware
# ===========================================================================


async def test_svg_camo_headers(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/badge/build/passing/brutalist-emerald")
    assert resp.headers.get("access-control-allow-origin") == "*"
    assert "Accept" in resp.headers.get("vary", "")
    assert resp.headers.get("x-content-type-options") == "nosniff"


# ===========================================================================
# Kit endpoint
# ===========================================================================


async def test_kit_post(client: AsyncClient) -> None:
    with patch("hyperweave.kit.compose", return_value=MOCK_RESULT):
        resp = await client.post(
            "/v1/kit/readme",
            json={"genome": "brutalist-emerald", "project": "test", "badges": "build:passing"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "banner" in data
        assert "badge-build" in data


# ===========================================================================
# Health endpoint
# ===========================================================================


async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ===========================================================================
# /v1/frames discovery
# ===========================================================================


async def test_list_frames(client: AsyncClient) -> None:
    resp = await client.get("/v1/frames")
    assert resp.status_code == 200
    data = resp.json()
    types = [f["type"] for f in data]
    assert "badge" in types
    assert "strip" in types
    assert "icon" in types
    assert all("pattern" in f for f in data)


# ===========================================================================
# New query params
# ===========================================================================


async def test_badge_with_regime(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/badge/build/passing/brutalist-emerald.static?regime=permissive")
    assert resp.status_code == 200


async def test_icon_with_variant(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/icon/terminal/brutalist-emerald.static?variant=hexagon")
    assert resp.status_code == 200


async def test_banner_with_state(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/banner/HYPERWEAVE/brutalist-emerald.static?state=passing&value=Living+Artifacts")
    assert resp.status_code == 200


# ===========================================================================
# Strip live data
# ===========================================================================


async def test_strip_live_data(client: AsyncClient) -> None:
    mock_data = {"value": "2.9k", "ttl": 300}
    with (
        patch("hyperweave.connectors.fetch_metric", new_callable=AsyncMock, return_value=mock_data),
        patch("hyperweave.compose.engine.compose", return_value=MOCK_RESULT),
    ):
        resp = await client.get(
            "/v1/strip/readme-ai/brutalist-emerald.static?live=github:anthropics/claude-code:stars"
        )
        assert resp.status_code == 200
        assert "stale-while-revalidate" in resp.headers.get("cache-control", "")


async def test_strip_live_data_error(client: AsyncClient) -> None:
    with (
        patch("hyperweave.connectors.fetch_metric", new_callable=AsyncMock, side_effect=Exception("timeout")),
        patch("hyperweave.compose.engine.compose", return_value=MOCK_RESULT),
    ):
        resp = await client.get(
            "/v1/strip/readme-ai/brutalist-emerald.static?live=github:anthropics/claude-code:stars"
        )
        assert resp.status_code == 200


# ===========================================================================
# Discovery cache headers
# ===========================================================================


async def test_discovery_cache_headers(client: AsyncClient) -> None:
    resp = await client.get("/v1/genomes")
    assert "max-age=3600" in resp.headers.get("cache-control", "")
