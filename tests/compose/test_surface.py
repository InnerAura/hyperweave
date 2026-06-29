"""Unified surface + content-addressed transport (alpha.5, Gate 1)."""

from __future__ import annotations

import pytest

from hyperweave.compose.artifact_store import get_artifact, reset_cache
from hyperweave.compose.surface import (
    ResponseEnvelope,
    SpecEnvelope,
    build_artifact_url,
    compose_surface,
    validate_surface,
)
from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.core.models import ComposeSpec


def test_compose_surface_returns_envelope_url_and_caches() -> None:
    reset_cache()
    resp = compose_surface(
        SpecEnvelope(
            type="badge",
            genome="primer",
            spec={"title": "STARS", "value": "1.2k"},
            emit=("payload", "compressed"),
        ),
        base_url="https://hyperweave.app",
    )
    assert isinstance(resp, ResponseEnvelope)
    assert resp.url.startswith("https://hyperweave.app/v1/a/")
    assert resp.compressed is not None and resp.compressed["id"].startswith("sha256:")
    assert resp.payload == {"title": "STARS", "value": "1.2k", "state": "active"}
    # the digest in the url addresses the cached SVG
    digest = resp.url.rsplit("/", 1)[-1]
    assert get_artifact(digest) is not None
    # svg not requested → suppressed (the pixels never travel)
    assert resp.svg == ""


def test_compose_surface_dedups_identical_content() -> None:
    reset_cache()
    a = compose_surface(
        SpecEnvelope(type="badge", genome="primer", spec={"title": "X", "value": "1"}, emit=("compressed",))
    )
    b = compose_surface(
        SpecEnvelope(type="badge", genome="primer", spec={"title": "X", "value": "1"}, emit=("compressed",))
    )
    assert a.url == b.url  # same content → same digest → same handle


def test_build_artifact_url_strips_sha_prefix() -> None:
    assert build_artifact_url("sha256:abc123") == "/v1/a/abc123"
    assert build_artifact_url("abc123", "https://h.app/") == "https://h.app/v1/a/abc123"


def test_validate_surface_good_and_bad() -> None:
    assert validate_surface(SpecEnvelope(type="badge", spec={"title": "X"}))["valid"] is True
    bad = validate_surface(SpecEnvelope(type="not-a-frame"))
    assert bad["valid"] is False
    assert bad["error"]["code"] == HwErrorCode.TYPE_UNKNOWN.value


def test_unknown_emit_target_raises_structured_error() -> None:
    with pytest.raises(HwError) as exc:
        compose_surface(SpecEnvelope(type="badge", spec={"title": "X"}, emit=("svg", "gif")))
    assert exc.value.code is HwErrorCode.SPEC_INVALID
    env = exc.value.envelope()
    assert set(env["error"]) == {"code", "message", "fix", "detail"}


def test_card_alias_canonicalizes_to_stats() -> None:
    spec = ComposeSpec(type="card", genome_id="brutalist", stats_username="eli64s")
    assert spec.type == "stats"


@pytest.mark.asyncio
async def test_durable_store_serves_from_disk_after_restart(tmp_path: object) -> None:
    """The README-survives-the-session case: a cold GET /v1/a/{digest} (LRU
    dropped, as on restart) must resolve FROM DISK when the durable tier is on."""
    from httpx import ASGITransport, AsyncClient

    from hyperweave.compose import artifact_store
    from hyperweave.serve.app import app

    try:
        artifact_store.configure_disk_cache(tmp_path)
        r = compose_surface(
            SpecEnvelope(type="badge", genome="primer", spec={"title": "X", "value": "Y"}, emit=("compressed",))
        )
        digest = r.url.rsplit("/", 1)[-1]
        artifact_store.reset_cache()  # drop the in-process LRU — simulate a restart
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            resp = await client.get(f"/v1/a/{digest}")
        assert resp.status_code == 200  # served from disk, not the LRU
        assert "<svg" in resp.text
    finally:
        artifact_store.configure_disk_cache(None)
        artifact_store.reset_cache()


@pytest.mark.asyncio
async def test_cold_handle_with_no_durable_tier_404s() -> None:
    """The honest fallback: no LRU entry and no disk tier → 404 (caller re-composes)."""
    from httpx import ASGITransport, AsyncClient

    from hyperweave.compose import artifact_store
    from hyperweave.serve.app import app

    artifact_store.reset_cache()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/v1/a/" + "deadbeef" * 8)
    assert resp.status_code == 404
