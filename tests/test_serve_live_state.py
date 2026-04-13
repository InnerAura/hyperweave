"""HTTP integration tests for the state inference chokepoint.

BUG-003 deferred for four releases because the fix was framed as per-route
wiring. These tests exercise the single-point fix: a live badge fetching
``value="failing"`` must render as failing through the real HTTP pipeline,
with no per-route changes. Tests deliberately do NOT mock compose().

Note: the CSS stylesheet embedded in every SVG contains
``[data-hw-status="<state>"]`` selectors for every known state, so a naive
substring check is vacuously true. We parse the root <svg> element's
attribute instead.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from hyperweave.serve.app import app

_ROOT_STATUS_RE = re.compile(r'<svg\b[^>]*\bdata-hw-status="([^"]+)"')


def _root_status(svg: str) -> str:
    """Return the data-hw-status attribute on the root <svg> element."""
    match = _ROOT_STATUS_RE.search(svg)
    assert match is not None, "root <svg> element missing data-hw-status attribute"
    return match.group(1)


@pytest.fixture()
async def client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_badge_route_infers_failing_state(client: AsyncClient) -> None:
    """GET /v1/badge/build/failing/... must put failing on the root <svg>."""
    resp = await client.get("/v1/badge/build/failing/brutalist-emerald.static")
    assert resp.status_code == 200
    assert _root_status(resp.text) == "failing"


async def test_badge_route_infers_passing_state(client: AsyncClient) -> None:
    """GET /v1/badge/build/passing/... must put passing on the root <svg>."""
    resp = await client.get("/v1/badge/build/passing/brutalist-emerald.static")
    assert resp.status_code == 200
    assert _root_status(resp.text) == "passing"


async def test_badge_route_explicit_state_wins(client: AsyncClient) -> None:
    """?state=passing must override the "failing" value inference."""
    resp = await client.get("/v1/badge/build/failing/brutalist-emerald.static?state=passing")
    assert resp.status_code == 200
    assert _root_status(resp.text) == "passing"


async def test_badge_route_percentage_ladder(client: AsyncClient) -> None:
    """Coverage 95%% should infer passing; 50%% should infer critical."""
    resp_high = await client.get("/v1/badge/coverage/95%25/brutalist-emerald.static")
    assert resp_high.status_code == 200
    assert _root_status(resp_high.text) == "passing"

    resp_low = await client.get("/v1/badge/coverage/50%25/brutalist-emerald.static")
    assert resp_low.status_code == 200
    assert _root_status(resp_low.text) == "critical"


async def test_badge_route_version_value_stays_active(client: AsyncClient) -> None:
    """Values the inferrer can't classify (e.g. version strings) stay active."""
    resp = await client.get("/v1/badge/version/v1.2.3/brutalist-emerald.static")
    assert resp.status_code == 200
    assert _root_status(resp.text) == "active"
