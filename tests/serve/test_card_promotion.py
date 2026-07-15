"""HTTP surface of the stats→card promotion and the /skill removal.

- /v1/card is the primary route; /v1/stats is a permanent alias on the SAME
  handler (no redirect — Camo-embedded READMEs must not follow redirects).
- /skill is removed entirely (no shim); discovery lives at /llms.txt → /llms-full.txt.
- /llms-full.txt is generated from the registry, so it names every capability;
  /llms.txt links to it and its surfaces block is registry-derived.
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from hyperweave.serve.app import app
from hyperweave.surfaces.registry import all_capabilities

MOCK_STATS: dict[str, Any] = {
    "username": "eli64s",
    "name": "Test User",
    "followers": 42,
    "public_repos": 7,
    "stars_total": 100,
    "commits_total": 30,
}


@pytest.fixture()
async def client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _strip_volatile(svg: str) -> str:
    """Normalize the two wall-clock fields (created timestamp, envelope ts) so a
    byte-equality comparison across two separate requests is meaningful — the
    established SVG-diff normalization (embedded timestamps are the only churn)."""
    svg = re.sub(r"<hw:created>[^<]+</hw:created>", "<hw:created>TS</hw:created>", svg)
    svg = re.sub(r"<dc:date>[^<]+</dc:date>", "<dc:date>TS</dc:date>", svg)
    return re.sub(r'"ts":"[^"]+"', '"ts":"TS"', svg)


# ── card / stats route parity ────────────────────────────────────────────────


async def test_card_and_stats_routes_are_byte_equal(client: AsyncClient) -> None:
    """Both paths bind to the same handler → identical bytes (timestamps aside)."""
    with patch("hyperweave.serve.app.fetch_user_stats", new_callable=AsyncMock, return_value=MOCK_STATS):
        r_card = await client.get("/v1/card/eli64s/chrome.static?variant=horizon")
        r_stats = await client.get("/v1/stats/eli64s/chrome.static?variant=horizon")

    assert r_card.status_code == 200
    assert r_stats.status_code == 200
    assert r_card.headers["content-type"] == "image/svg+xml"
    assert _strip_volatile(r_card.text) == _strip_volatile(r_stats.text)


async def test_card_route_emits_public_frame_name(client: AsyncClient) -> None:
    with patch("hyperweave.serve.app.fetch_user_stats", new_callable=AsyncMock, return_value=MOCK_STATS):
        r = await client.get("/v1/card/eli64s/chrome.static")
    assert 'data-hw-frame="card"' in r.text
    # Internal id survives on data-hw-type.
    assert 'data-hw-type="stats"' in r.text


async def test_stats_alias_is_not_a_redirect(client: AsyncClient) -> None:
    """The stats alias must serve the artifact directly (Camo does not follow
    redirects) — a 200 image, never a 3xx."""
    with patch("hyperweave.serve.app.fetch_user_stats", new_callable=AsyncMock, return_value=MOCK_STATS):
        r = await client.get("/v1/stats/eli64s/chrome.static", follow_redirects=False)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/svg+xml"


# ── /skill removed ───────────────────────────────────────────────────────────


async def test_skill_route_is_gone(client: AsyncClient) -> None:
    # No 308, no shim — the clean-break posture (matches verb bodies and
    # --target). Discovery lives at /llms.txt → /llms-full.txt.
    r = await client.get("/skill", follow_redirects=False)
    assert r.status_code == 404


# ── /llms.txt + /llms-full.txt ───────────────────────────────────────────────


async def test_llms_full_txt_names_every_registered_capability(client: AsyncClient) -> None:
    """The doc anti-drift pin: the capability index is generated from the
    registry, so every registered capability appears by construction."""
    r = await client.get("/llms-full.txt")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/plain; charset=utf-8"
    for cap in all_capabilities():
        assert f"### {cap.name}" in r.text, f"capability {cap.name!r} missing from /llms-full.txt"


async def test_llms_txt_links_to_llms_full(client: AsyncClient) -> None:
    r = await client.get("/llms.txt")
    assert r.status_code == 200
    assert "/llms-full.txt" in r.text


async def test_llms_txt_surfaces_block_reflects_the_registry(client: AsyncClient) -> None:
    """The surfaces enumeration is registry-derived, so the CLI verbs added in
    this release (extract/verify/transform/diff/query) appear — the drift the
    stale ``CLI: compose|validate`` line used to carry is gone."""
    r = await client.get("/llms.txt")
    for verb in ("extract", "verify", "transform", "diff", "query"):
        assert f"hyperweave {verb}" in r.text
