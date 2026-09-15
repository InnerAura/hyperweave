"""POST /v1/compose body contract.

Every field a caller can set on the CLI or MCP surfaces is a body field, and a
key the body does not know is reported on every response shape, never dropped
in silence. The GET routes, the CLI, and MCP all honored ``font_mode`` while
the JSON body composed an embedded artifact regardless; this file pins the
whole class, not the one field.
"""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.core.models import ComposeResult, ComposeSpec
from hyperweave.mcp.server import hw_compose
from hyperweave.serve.app import ComposeRequest, app

MOCK_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="22"><text>mock</text></svg>'

# Body names for the ComposeSpec fields the body spells differently.
BODY_ALIASES = {
    "genome_id": "genome",
    "marquee_direction": "direction",
    "marquee_speeds": "speeds",
    "surface_face": "face",
}

# ComposeSpec fields no surface lets a caller set: resolved, derived, or
# transport-populated. Adding a ComposeSpec field forces a decision here.
INTERNAL_SPEC_FIELDS = frozenset(
    {
        "frame_id",  # resolved from the frame type
        "profile_id",  # resolved from the genome
        "generation",  # artifact counter
        "data_tokens",  # resolved from `data` by the transport
        "chrome",  # diagram solver plumbing, never caller-set
        "slots",  # zone content no surface constructs
        "intent",  # reasoning metadata the engine derives
        "approach",
        "tradeoffs",
        "numeric_value",  # threshold evaluation, set by no surface
        "threshold_id",
        "series",  # provenance metadata
        "platform",
    }
)

# MCP parameters that are response shapes, not spec fields.
MCP_ONLY = frozenset({"render_target"})


@pytest.fixture()
async def client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def test_every_caller_facing_spec_field_is_a_body_field() -> None:
    body = set(ComposeRequest.model_fields)
    missing = [
        name
        for name in ComposeSpec.model_fields
        if name not in INTERNAL_SPEC_FIELDS and BODY_ALIASES.get(name, name) not in body
    ]
    assert not missing, f"ComposeSpec fields unreachable over POST /v1/compose: {missing}"


def test_every_mcp_compose_parameter_is_a_body_field() -> None:
    params = set(inspect.signature(hw_compose).parameters) - MCP_ONLY
    missing = sorted(params - set(ComposeRequest.model_fields))
    assert not missing, f"hw_compose parameters unreachable over POST /v1/compose: {missing}"


@pytest.mark.parametrize("respond", ["svg", "json", "envelope", "report"])
async def test_unknown_key_is_reported_on_every_response_shape(client: AsyncClient, respond: str) -> None:
    resp = await client.post(
        "/v1/compose",
        json={"type": "badge", "genome": "primer", "title": "X", "value": "y", "respond": respond, "colour": "red"},
    )
    assert resp.status_code == 200, resp.text
    if respond == "svg":
        assert "colour" in resp.headers["x-hw-warning"]
    else:
        warnings = resp.json()["warnings"]
        assert any("colour" in w for w in warnings), warnings


async def test_font_mode_reaches_every_response_shape(client: AsyncClient) -> None:
    """``system`` ships no @font-face on any shape; the default still embeds."""
    base = {"type": "badge", "genome": "primer", "title": "X", "value": "y"}
    embedded = await client.post("/v1/compose", json={**base, "respond": "svg"})
    assert "@font-face" in embedded.text
    for respond in ("svg", "json", "envelope"):
        resp = await client.post("/v1/compose", json={**base, "respond": respond, "font_mode": "system"})
        assert resp.status_code == 200, resp.text
        svg = resp.text if respond == "svg" else resp.json()["svg"]
        assert "@font-face" not in svg, respond
    report = await client.post("/v1/compose", json={**base, "respond": "report", "font_mode": "system"})
    assert report.status_code == 200, report.text
    assert report.json()["ok"] is True


async def test_font_mode_lifts_out_of_the_matrix_body(client: AsyncClient) -> None:
    tiny = {
        "title": "Tiny",
        "columns": [{"id": "v", "label": "V"}],
        "rows": [{"label": "one", "cells": [{"value": 1}]}],
    }
    resp = await client.post(
        "/v1/compose", json={"type": "matrix", "genome": "primer", "matrix": tiny, "font_mode": "system"}
    )
    assert resp.status_code == 200
    assert "@font-face" not in resp.text


async def test_public_fields_reach_the_inline_spec(client: AsyncClient) -> None:
    captured: list[ComposeSpec] = []

    def _capture(spec: ComposeSpec) -> ComposeResult:
        captured.append(spec)
        return ComposeResult(svg=MOCK_SVG, width=120, height=22)

    body = {
        "type": "badge",
        "title": "X",
        "value": "y",
        "pair": "violet",
        "state_glyph_shape": "diamond",
        "font_mode": "cdn",
        "telemetry_data": {"session": 1},
        "receipt_display_name": "review",
        "connector_data": {"stars": 2},
        "stats_username": "octocat",
        "chart_owner": "owner",
        "chart_repo": "repo",
    }
    with patch("hyperweave.serve.app.compose", side_effect=_capture):
        resp = await client.post("/v1/compose", json=body)
    assert resp.status_code == 200
    (spec,) = captured
    for name, expected in body.items():
        if name != "type":
            assert getattr(spec, name) == expected, name


async def test_public_fields_reach_the_envelope_spec(client: AsyncClient) -> None:
    captured: list[ComposeSpec] = []

    def _capture(spec: ComposeSpec) -> ComposeResult:
        captured.append(spec)
        return ComposeResult(svg=MOCK_SVG, width=120, height=22)

    body = {
        "type": "badge",
        "title": "X",
        "value": "y",
        "respond": "envelope",
        "pair": "violet",
        "state_glyph_shape": "diamond",
        "font_mode": "cdn",
        "telemetry_data": {"session": 1},
        "receipt_display_name": "review",
        "connector_data": {"stars": 2},
        "stats_username": "octocat",
        "chart_owner": "owner",
        "chart_repo": "repo",
    }
    with patch("hyperweave.compose.surface.compose", side_effect=_capture):
        resp = await client.post("/v1/compose", json=body)
    assert resp.status_code == 200, resp.text
    (spec,) = captured
    for name, expected in body.items():
        if name not in ("type", "respond"):
            assert getattr(spec, name) == expected, name


async def test_data_tokens_resolve_on_the_inline_shapes(client: AsyncClient) -> None:
    captured: list[ComposeSpec] = []

    def _capture(spec: ComposeSpec) -> ComposeResult:
        captured.append(spec)
        return ComposeResult(svg=MOCK_SVG, width=120, height=22)

    with patch("hyperweave.serve.app.compose", side_effect=_capture):
        badge = await client.post("/v1/compose", json={"type": "badge", "title": "STARS", "data": "kv:STARS=42"})
        marquee = await client.post(
            "/v1/compose", json={"type": "marquee", "title": "x", "data": "text:NEW,kv:V=1", "respond": "json"}
        )
    assert badge.status_code == 200 and marquee.status_code == 200
    assert "stale-while-revalidate" in badge.headers["cache-control"]
    assert captured[0].value == "STARS:42"
    assert captured[1].data_tokens is not None and len(captured[1].data_tokens) == 2


async def test_bad_data_token_is_refused(client: AsyncClient) -> None:
    resp = await client.post("/v1/compose", json={"type": "badge", "title": "X", "data": "nonsense"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SPEC_INVALID"


async def test_byte_format_on_an_inline_shape_is_reported(client: AsyncClient) -> None:
    svg = await client.post("/v1/compose", json={"type": "badge", "genome": "primer", "title": "X", "format": "png"})
    assert svg.status_code == 200
    assert "format='png'" in svg.headers["x-hw-warning"]
    js = await client.post(
        "/v1/compose", json={"type": "badge", "genome": "primer", "title": "X", "format": "png", "respond": "json"}
    )
    assert any("format='png'" in w for w in js.json()["warnings"])


async def test_diagram_motion_overrides_reach_both_paths(client: AsyncClient) -> None:
    diagram = dict(resolve_bundled_spec("diagram", "pipeline-head").value)
    captured: list[ComposeSpec] = []

    def _capture(spec: ComposeSpec) -> ComposeResult:
        captured.append(spec)
        return ComposeResult(svg=MOCK_SVG, width=120, height=22)

    body = {"type": "diagram", "genome": "primer", "diagram": diagram, "edge_motion": "particle"}
    with patch("hyperweave.serve.app.compose", side_effect=_capture):
        inline = await client.post("/v1/compose", json=body)
    with patch("hyperweave.compose.surface.compose", side_effect=_capture):
        envelope = await client.post("/v1/compose", json={**body, "respond": "envelope"})
    assert inline.status_code == 200 and envelope.status_code == 200, envelope.text
    assert all(spec.diagram is not None and spec.diagram.edge_motion.value == "particle" for spec in captured)
