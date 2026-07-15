"""Derived-projection routes + compose destination-gutting on the HTTP surface.

Covers ``GET /v1/a/{digest}[.{ext}]`` (live svg, svg-static, raster, gif→501,
``?w=`` cap) and ``POST /v1/compose`` (respond=envelope, the ``target`` key
rejection). The digest route needs a real cached artifact, so these compose for
real rather than mocking.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from hyperweave.formats import raster_available
from hyperweave.serve.app import app

_HAS_RASTER = raster_available()


@pytest.fixture()
async def client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _compose_digest(client: AsyncClient) -> str:
    """Compose a real badge via respond=envelope and return its digest hex."""
    resp = await client.post(
        "/v1/compose",
        json={
            "type": "badge",
            "genome": "primer",
            "variant": "porcelain",
            "title": "STARS",
            "value": "1234",
            "respond": "envelope",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["url"].rsplit("/", 1)[-1]


async def test_compose_respond_envelope_returns_handle(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/compose",
        json={"type": "badge", "genome": "primer", "title": "X", "value": "y", "respond": "envelope"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "envelope" in body and "/v1/a/" in body["url"]


async def test_compose_target_key_rejected(client: AsyncClient) -> None:
    """A `target` key is a 400 with migration text — the destination axis is gone."""
    resp = await client.post(
        "/v1/compose",
        json={"type": "badge", "title": "X", "value": "y", "target": "github"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "SPEC_INVALID"
    assert "format" in body["error"]["fix"]


async def test_artifact_live_svg(client: AsyncClient) -> None:
    digest = await _compose_digest(client)
    resp = await client.get(f"/v1/a/{digest}")
    assert resp.status_code == 200
    assert "image/svg+xml" in resp.headers["content-type"]
    assert "immutable" in resp.headers["cache-control"]
    assert "var(--dna" in resp.text  # the live svg keeps its vars


async def test_artifact_static_svg_flattens(client: AsyncClient) -> None:
    digest = await _compose_digest(client)
    resp = await client.get(f"/v1/a/{digest}.static.svg")
    assert resp.status_code == 200
    assert "image/svg+xml" in resp.headers["content-type"]
    assert "var(--dna" not in resp.text  # flattened to hex


async def test_artifact_gif_is_501(client: AsyncClient) -> None:
    digest = await _compose_digest(client)
    resp = await client.get(f"/v1/a/{digest}.gif")
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == "FORMAT_UNAVAILABLE"


async def test_artifact_cold_digest_404(client: AsyncClient) -> None:
    resp = await client.get("/v1/a/deadbeef" * 8)
    assert resp.status_code == 404


@pytest.mark.skipif(not _HAS_RASTER, reason="raster extra not installed")
async def test_artifact_png_and_width_cap(client: AsyncClient) -> None:
    digest = await _compose_digest(client)
    resp = await client.get(f"/v1/a/{digest}.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"

    capped = await client.get(f"/v1/a/{digest}.png", params={"w": 100})
    assert capped.status_code == 200
    from io import BytesIO

    from PIL import Image

    assert Image.open(BytesIO(capped.content)).width <= 100
