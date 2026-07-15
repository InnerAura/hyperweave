"""Unified surface + content-addressed transport."""

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


def test_validate_shares_composes_gate_on_ir_frames() -> None:
    """Validate runs the IR frame's structural coercion, so it refuses
    anything compose refuses — no false green on an empty/misshaped IR
    envelope (the cold-agent dogfood finding)."""
    # Empty IR spec: composes to DiagramInputError → must NOT validate True.
    assert validate_surface(SpecEnvelope(type="diagram", spec={}))["valid"] is False
    assert validate_surface(SpecEnvelope(type="matrix", spec={}))["valid"] is False
    # A well-formed diagram still validates.
    good = {
        "topology": "pipeline",
        "title": "T",
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
    }
    assert validate_surface(SpecEnvelope(type="diagram", spec=good))["valid"] is True
    # A preset carried via connector_data (empty schema) is legal.
    preset = SpecEnvelope(type="diagram", spec={"connector_data": {"diagram_preset": "rag-pipeline"}})
    assert validate_surface(preset)["valid"] is True


def test_unknown_emit_target_raises_structured_error() -> None:
    with pytest.raises(HwError) as exc:
        compose_surface(SpecEnvelope(type="badge", spec={"title": "X"}, emit=("svg", "gif")))
    assert exc.value.code is HwErrorCode.SPEC_INVALID
    env = exc.value.envelope()
    assert set(env["error"]) == {"code", "message", "fix", "detail"}


def test_card_alias_canonicalizes_to_stats() -> None:
    spec = ComposeSpec(type="card", genome_id="brutalist", stats_username="eli64s")
    assert spec.type == "stats"


def test_ir_frame_lifts_compose_fields_but_keeps_ir_title() -> None:
    """The forwarding contract: an IR frame's `spec` may carry ComposeSpec-level
    fields alongside the nested schema. `performance` lifts to a top-level
    ComposeSpec field; the IR's own `title` stays in the diagram schema."""
    from hyperweave.compose.surface import SpecEnvelope, _to_compose_spec

    env = SpecEnvelope(
        type="diagram",
        genome="primer",
        spec={
            "topology": "pipeline",
            "title": "My Flow",
            "nodes": [{"label": "A"}, {"label": "B"}],
            "performance": "composite-only",
        },
    )
    spec = _to_compose_spec(env)
    assert spec.performance == "composite-only"  # lifted
    assert spec.diagram is not None
    assert spec.diagram.title == "My Flow"  # IR title stays in the schema
    assert spec.title == ""  # never became a badge label


def test_stray_chrome_key_is_silently_dropped_not_lifted() -> None:
    """`chrome` was the pre-gut diagram presentation axis (card/bare/caption),
    publicly settable via CLI/HTTP/MCP. It is now internal-only solver
    plumbing (sec 12.1 embeds); a stray key from an old stored payload must
    not reach ComposeSpec at all — it is dropped before the IR lift, so it
    can neither 500 nor resurrect external control of the retired axis."""
    from hyperweave.compose.surface import SpecEnvelope, _to_compose_spec

    env = SpecEnvelope(
        type="diagram",
        genome="primer",
        spec={
            "topology": "pipeline",
            "title": "My Flow",
            "nodes": [{"label": "A"}, {"label": "B"}],
            "chrome": "bare",
        },
    )
    spec = _to_compose_spec(env)
    assert spec.chrome == "caption"  # the internal default, NOT the stray "bare"
    assert spec.diagram is not None
    assert spec.diagram.title == "My Flow"


def test_matrix_empty_ir_with_connector_data_uses_adapter() -> None:
    """A matrix with only `connector_data` (no IR) leaves `matrix` None so the
    connector-registry adapter engages — the empty IR must not become `matrix={}`."""
    from hyperweave.compose.surface import SpecEnvelope, _to_compose_spec

    env = SpecEnvelope(
        type="matrix",
        genome="primer",
        spec={"connector_data": {"matrix_adapter": "connector-registry"}},
    )
    spec = _to_compose_spec(env)
    assert spec.matrix is None  # empty IR → adapter path, not a bad empty MatrixSpec
    assert spec.connector_data == {"matrix_adapter": "connector-registry"}


def test_format_axis_projects_static() -> None:
    """The `format` axis projects the response SVG (svg-static flattens vars)."""
    reset_cache()
    resp = compose_surface(
        SpecEnvelope(
            type="badge", genome="primer", variant="porcelain", spec={"title": "X", "value": "1"}, format="svg-static"
        )
    )
    assert "var(--dna" not in resp.svg  # flattened


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
