"""Tests for serve/app.py -- FastAPI HTTP endpoints.

Covers URL grammar routes, POST /v1/compose, the ?data= token-driven
endpoints (badge data-route, strip, marquee), discovery endpoints,
namespace routes (/g/, /a/, /d/), ETag 304 negotiation, error badge
rendering, and Camo-hardening middleware.
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
    with patch("hyperweave.serve.app.compose", return_value=MOCK_RESULT) as m:
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


async def test_icon_url_returns_svg(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/icon/github/brutalist-emerald.static")
    assert resp.status_code == 200


async def test_divider_url_returns_svg(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/divider/void/brutalist-emerald.static")
    assert resp.status_code == 200


async def test_marquee_horizontal(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/marquee/HYPERWEAVE/brutalist-emerald.static?direction=ltr")
    assert resp.status_code == 200


async def test_marquee_horizontal_with_data_tokens(client: AsyncClient) -> None:
    """marquee-horizontal accepts ?data= and routes through the data-token pipeline."""
    mock_data = {"value": 12345, "ttl": 300}
    with (
        patch("hyperweave.connectors.fetch_metric", new_callable=AsyncMock, return_value=mock_data),
        patch("hyperweave.serve.app.compose", return_value=MOCK_RESULT),
    ):
        resp = await client.get(
            "/v1/marquee/SCROLL/brutalist-emerald.static?data=text:NEW%20RELEASE,gh:anthropics/claude-code.stars",
        )
        assert resp.status_code == 200


async def test_marquee_horizontal_data_token_comma_escape(client: AsyncClient) -> None:
    """text: payload preserves embedded commas via the \\, escape."""
    with patch("hyperweave.serve.app.compose", return_value=MOCK_RESULT):
        resp = await client.get(
            "/v1/marquee/SCROLL/brutalist-emerald.static?data=text:Hello%5C%2C%20world",
        )
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
        json={"type": "strip", "title": "readme-ai", "value": "STARS:2.9k,FORKS:278"},
    )
    assert resp.status_code == 200


async def test_badge_data_route_requires_data_param(client: AsyncClient) -> None:
    """The 2-segment data-driven badge route returns a 400 SMPTE SVG when ?data= is missing."""
    resp = await client.get("/v1/badge/STARS/brutalist-emerald.static")
    # 200 to keep Camo happy; the error class travels in headers + SVG content
    assert resp.status_code == 200
    assert resp.headers.get("x-hw-error-code") == "400"


async def test_badge_data_route_resolves_live_token(client: AsyncClient) -> None:
    """The 2-segment data-driven badge route resolves a live token and renders just the value.

    Regression guard: an earlier implementation rendered the full ``LABEL:VALUE``
    pair (``"STARS:12345"``) into badge's value slot because it routed through
    ``format_for_value`` (which is correct for strip's multi-cell layout but
    wrong for badge's single-value slot). The route now uses ``format_for_badge``
    which extracts the value only.
    """
    captured_specs: list[Any] = []

    def _capture_spec(spec: Any) -> Any:
        captured_specs.append(spec)
        return MOCK_RESULT

    mock_data = {"value": 12345, "ttl": 300}
    with (
        patch("hyperweave.connectors.fetch_metric", new_callable=AsyncMock, return_value=mock_data),
        patch("hyperweave.serve.app.compose", side_effect=_capture_spec),
    ):
        resp = await client.get(
            "/v1/badge/STARS/brutalist-emerald.static?data=gh:anthropics/claude-code.stars",
        )
        assert resp.status_code == 200
        assert "image/svg+xml" in resp.headers["content-type"]
        assert "stale-while-revalidate" in resp.headers.get("cache-control", "")
        # Value passed to compose() is the raw resolved value, not "LABEL:VALUE".
        assert len(captured_specs) == 1
        assert captured_specs[0].value == "12345", (
            f"badge data route should render raw value '12345', not 'STARS:12345'; got {captured_specs[0].value!r}"
        )


async def test_badge_data_route_kv_token(client: AsyncClient) -> None:
    """kv: tokens encode static literals through the same data-route shape as live ones."""
    with patch("hyperweave.serve.app.compose", return_value=MOCK_RESULT):
        resp = await client.get(
            "/v1/badge/VERSION/brutalist-emerald.static?data=kv:VERSION=0.6.9",
        )
        assert resp.status_code == 200


async def test_compose_post_defaults(client: AsyncClient, mock_compose: Any) -> None:
    """Empty body uses all defaults (badge, brutalist-emerald, static)."""
    resp = await client.post("/v1/compose", json={})
    assert resp.status_code == 200


# ===========================================================================
# Legacy /v1/live/ route is deleted in v0.2.14 — replaced by ?data= on the
# 2-segment data-driven badge route. Live-data tests now live under
# `test_badge_data_route_*` above.
# ===========================================================================


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
        # HTTP 200 with X-HW-Error-Code header — Camo refuses to proxy 4xx
        # image responses, so the error class travels in the header instead.
        # See _classify_compose_exception docstring.
        assert resp.status_code == 200
        assert resp.headers["x-hw-error-code"] == "404"
        assert "image/svg+xml" in resp.headers["content-type"]


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
        patch("hyperweave.serve.app.compose", side_effect=ValueError("render failed")),
        patch("hyperweave.serve.app._error_badge", return_value=error_svg),
    ):
        resp = await client.get("/v1/badge/build/passing/brutalist-emerald")
        # HTTP 200 with X-HW-Error-Code: 500 — see _classify_compose_exception.
        assert resp.status_code == 200
        assert resp.headers["x-hw-error-code"] == "500"
        assert "image/svg+xml" in resp.headers["content-type"]


def test_classify_compose_exception_genome_not_found_is_404() -> None:
    from hyperweave.compose.resolver import GenomeNotFoundError
    from hyperweave.serve.app import _classify_compose_exception

    assert _classify_compose_exception(GenomeNotFoundError("xyz")) == 404


def test_classify_compose_exception_validation_is_422() -> None:
    from pydantic import BaseModel, ValidationError

    from hyperweave.serve.app import _classify_compose_exception

    class _M(BaseModel):
        x: int

    with pytest.raises(ValidationError) as excinfo:
        _M(x="not-an-int")  # type: ignore[arg-type]
    assert _classify_compose_exception(excinfo.value) == 422


def test_classify_compose_exception_generic_is_500() -> None:
    from hyperweave.serve.app import _classify_compose_exception

    assert _classify_compose_exception(RuntimeError("kaboom")) == 500


def test_error_badge_renders_smpte_template_with_status_code() -> None:
    from hyperweave.serve.app import _error_badge

    svg = _error_badge("genome 'xyz' not found", status_code=404)
    assert svg.startswith("<svg")
    assert "ERR_404" in svg
    assert "NO SIGNAL" in svg
    assert 'data-hw-genome="signal-loss"' in svg
    assert 'data-hw-class="error-state"' in svg


def test_error_badge_uid_isolates_dom_ids() -> None:
    import re

    from hyperweave.serve.app import _error_badge

    svg_a = _error_badge("first error", status_code=404)
    svg_b = _error_badge("second error totally different", status_code=500)
    uids_a = set(re.findall(r"hw-err-\d{5}", svg_a))
    uids_b = set(re.findall(r"hw-err-\d{5}", svg_b))
    assert len(uids_a) == 1
    assert len(uids_b) == 1
    assert uids_a.isdisjoint(uids_b)


async def test_unknown_genome_returns_404_smpte_pattern(client: AsyncClient) -> None:
    resp = await client.get("/v1/badge/TEST/value/nonexistent-genome.static")
    # HTTP envelope is 200 (Camo-friendly); the 404 lives in the X-HW-Error-Code
    # header and the SVG body (ERR_404 slab + data-hw-status-code attribute).
    assert resp.status_code == 200
    assert resp.headers["x-hw-error-code"] == "404"
    assert "image/svg+xml" in resp.headers["content-type"]
    body = resp.text
    assert "ERR_404" in body
    assert "NO SIGNAL" in body
    assert 'data-hw-class="error-state"' in body
    assert 'data-hw-status-code="404"' in body


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
        assert "badge-build" in data
        assert "divider" in data


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


async def test_icon_with_shape(client: AsyncClient, mock_compose: Any) -> None:
    resp = await client.get("/v1/icon/terminal/chrome-horizon.static?shape=circle")
    assert resp.status_code == 200


async def test_icon_brutalist_circle_shape(client: AsyncClient, mock_compose: Any) -> None:
    """Brutalist genome supports both circle and square icon shapes."""
    resp = await client.get("/v1/icon/terminal/brutalist-emerald.static?shape=circle")
    assert resp.status_code == 200


# ===========================================================================
# Strip data tokens (?data= replaces legacy ?live= in v0.2.14)
# ===========================================================================


async def test_strip_data_tokens(client: AsyncClient) -> None:
    mock_data = {"value": "2.9k", "ttl": 300}
    with (
        patch("hyperweave.connectors.fetch_metric", new_callable=AsyncMock, return_value=mock_data),
        patch("hyperweave.serve.app.compose", return_value=MOCK_RESULT),
    ):
        resp = await client.get(
            "/v1/strip/readme-ai/brutalist-emerald.static?data=gh:anthropics/claude-code.stars",
        )
        assert resp.status_code == 200
        assert "stale-while-revalidate" in resp.headers.get("cache-control", "")


async def test_strip_data_tokens_error(client: AsyncClient) -> None:
    with (
        patch("hyperweave.connectors.fetch_metric", new_callable=AsyncMock, side_effect=Exception("timeout")),
        patch("hyperweave.serve.app.compose", return_value=MOCK_RESULT),
    ):
        resp = await client.get(
            "/v1/strip/readme-ai/brutalist-emerald.static?data=gh:anthropics/claude-code.stars",
        )
        assert resp.status_code == 200


async def test_strip_data_tokens_malformed_returns_400_smpte(client: AsyncClient) -> None:
    """Malformed ?data= returns a 400-class SMPTE SVG (HTTP 200 for Camo)."""
    resp = await client.get("/v1/strip/readme-ai/brutalist-emerald.static?data=gh:no-dot-no-metric")
    assert resp.status_code == 200
    assert resp.headers.get("x-hw-error-code") == "400"


# ===========================================================================
# Discovery cache headers
# ===========================================================================


async def test_discovery_cache_headers(client: AsyncClient) -> None:
    resp = await client.get("/v1/genomes")
    assert "max-age=3600" in resp.headers.get("cache-control", "")
