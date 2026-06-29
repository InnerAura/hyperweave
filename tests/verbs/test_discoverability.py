"""Discoverability gate + verb transport integration (alpha.5, Gate 3).

The gate: a cold agent given only an SVG finds the contract and round-trips it.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from hyperweave.compose.artifact_store import get_artifact
from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec
from hyperweave.mcp.server import (
    hw_compose,
    hw_compress,
    hw_discover,
    hw_extract,
    hw_transform,
    hw_verify,
)
from hyperweave.serve.app import app
from hyperweave.verbs import extract, transform, verify

_MATRIX = {
    "title": "Cost",
    "columns": [{"id": "m", "label": "MODEL"}, {"id": "c", "label": "COST", "kind": "numeric"}],
    "rows": [{"label": "Qwen", "cells": [{"value": "Qwen"}, {"value": "0.12"}]}],
}


def _matrix_svg() -> str:
    return compose(ComposeSpec(type="matrix", genome_id="primer", matrix=_MATRIX)).svg


def test_self_instruction_comment_in_every_artifact() -> None:
    svg = compose(ComposeSpec(type="badge", genome_id="primer", title="X", value="Y")).svg
    assert "agents:" in svg
    assert "llms.txt" in svg
    assert "hw:payload" in svg


def test_cold_agent_round_trip_from_svg_alone() -> None:
    # An agent with zero priors, given ONLY the SVG, can find + use the contract.
    svg = _matrix_svg()
    assert "agents:" in svg  # 1. reads the self-instruction
    payload = extract(svg, respond="payload").payload  # 2. extracts the seed
    assert payload is not None and payload["title"] == "Cost"
    r = transform(svg, [{"op": "replace", "path": "/title", "value": "Edited"}], ts="t")  # 3. mutates
    assert verify(r.svg).hash_valid  # 4. the result self-verifies


@pytest.mark.asyncio
async def test_llms_txt_route_carries_the_contract() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/llms.txt")
    assert r.status_code == 200
    for token in ("extract", "transform", "verify", "diff", "query", "hw:payload", "hw:envelope"):
        assert token in r.text


@pytest.mark.asyncio
async def test_hw_discover_verbs_has_signatures_and_example() -> None:
    d = await hw_discover("verbs")
    verbs = d["verbs"]
    assert "transform" in verbs and "extract" in verbs
    assert "worked_example" in verbs


@pytest.mark.asyncio
async def test_mcp_verb_round_trip() -> None:
    composed = await hw_compose(type="matrix", genome="primer", matrix=_MATRIX)
    svg = get_artifact(composed["url"].rsplit("/", 1)[-1])
    assert svg is not None

    ext = await hw_extract(svg, respond="payload")
    assert ext["payload"]["title"] == "Cost"

    comp = await hw_compress(svg)
    assert comp["envelope"]["k"] == "matrix"  # alias → envelope depth

    tr = await hw_transform(svg, [{"op": "replace", "path": "/title", "value": "Z"}])
    assert tr["url"] and tr["lineage"]
    new_svg = get_artifact(tr["url"].rsplit("/", 1)[-1])
    assert new_svg is not None
    assert (await hw_verify(new_svg))["valid"] is True


@pytest.mark.asyncio
async def test_http_verb_routes() -> None:
    svg = _matrix_svg()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        e = await c.post("/v1/extract", json={"source": svg, "respond": "envelope"})
        assert e.json()["envelope"]["k"] == "matrix"
        v = await c.post("/v1/verify", json={"svg": svg})
        assert v.json()["valid"] is True
        t = await c.post(
            "/v1/transform", json={"source": svg, "mutations": [{"op": "replace", "path": "/title", "value": "Q"}]}
        )
        assert "url" in t.json() and t.json()["url"]
        q = await c.post("/v1/query", json={"svg": svg, "question": "how many rows?"})
        assert q.json()["answer"] == "1"
