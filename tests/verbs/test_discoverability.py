"""Discoverability gate + verb transport integration.

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
async def test_url_grammar_advertises_diagram_and_surface_axes() -> None:
    """The discovery grammar must advertise what the routes accept — the
    diagram entry went missing entirely once, and the surface axes
    (surface/ground/palette/face) lagged the routes that honored them."""
    grammar = (await hw_discover("url_grammar"))["url_grammar"]
    for frame in ("diagram", "matrix"):
        params = grammar[frame]["query_params"]
        for axis in ("surface", "ground", "palette", "face"):
            assert axis in params, f"{frame} grammar missing the {axis} axis"
    assert "/v1/diagram/" in grammar["diagram"]["pattern"]


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
        v = await c.post("/v1/verify", json={"source": svg})
        assert v.json()["valid"] is True
        t = await c.post(
            "/v1/transform", json={"source": svg, "mutations": [{"op": "replace", "path": "/title", "value": "Q"}]}
        )
        assert "url" in t.json() and t.json()["url"]
        q = await c.post("/v1/query", json={"source": svg, "question": "how many rows?"})
        assert q.json()["answer"] == "1"


def test_diagram_glyph_diagnostic_points_at_a_reachable_discover_call() -> None:
    """The unresolved-glyph suggestion names a ``discover`` call — that
    capability must be reachable on every surface that prints the diagnostic
    (no diagnostic may suggest a call the reader cannot run)."""
    result = compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            diagram={
                "topology": "pipeline",
                "title": "Probe",
                "nodes": [{"id": "a", "label": "A", "kind": "search"}, {"label": "B"}, {"label": "C"}],
            },
        )
    )
    notes = [d for d in result.diagnostics if d["rule"] == "unresolved-glyph"]
    assert notes, "expected the unresolved-glyph diagnostic to fire for kind-on-card"
    assert "discover" in notes[0]["suggestion"]

    from hyperweave.surfaces.discover import discover
    from hyperweave.surfaces.registry import all_capabilities

    cap = next(c for c in all_capabilities() if c.name == "discover")
    assert cap.cli_command and cap.http_path and cap.mcp_tool, "discover must be reachable on all three surfaces"
    assert discover("glyphs")["glyphs"], "the suggested selector must answer"


def test_diagram_discover_payload_lists_structural_edge_rules_per_topology() -> None:
    """The per-topology edge legality is knowable BEFORE compose: discover's
    diagram payload carries the structural rules the validators enforce."""
    from hyperweave.surfaces.discover import discover

    rules = discover("diagram")["diagram"]["edge_rules"]
    assert "incident" in rules["hub"] or "touches the hub" in rules["hub"]
    assert "dag" in rules["hub"]  # the exit is named, not just the rule
    assert "parent" in rules["tree"]
    assert "any" in rules  # the global laws every topology shares


def test_discover_schema_selector_returns_frame_json_schemas() -> None:
    """schema:<id> publishes the frame model's JSON Schema — structural,
    JSON-round-trippable, no new modeling."""
    import json

    from hyperweave.surfaces.discover import discover

    def _root(js: dict) -> dict:
        # A recursive model (diagram nests diagrams) roots at a $ref into $defs.
        if "$ref" in js:
            return js["$defs"][js["$ref"].split("/")[-1]]  # type: ignore[no-any-return]
        return js

    diagram = discover("schema:diagram/1")["schema"]
    assert diagram["id"] == "diagram/1"
    js = diagram["json_schema"]
    assert "topology" in _root(js)["properties"]
    assert json.loads(json.dumps(js)) == js

    matrix = _root(discover("schema:matrix/1")["schema"]["json_schema"])
    assert "columns" in matrix["properties"] and "rows" in matrix["properties"]


def test_discover_schema_selector_rejects_unknown_id_with_menu() -> None:
    import pytest

    from hyperweave.core.errors import HwError
    from hyperweave.surfaces.discover import discover

    with pytest.raises(HwError) as exc_info:
        discover("schema:nope/9")
    assert "matrix/1" in (exc_info.value.fix or "")


def test_discover_lists_schema_ids_in_bare_output() -> None:
    from hyperweave.surfaces.discover import discover

    assert discover("schemas")["schemas"] == ["diagram/1", "matrix/1"]


def test_every_listed_preset_resolves_through_the_example_selector() -> None:
    """Every preset name discover lists is fetchable as full content through
    the example selector — self-maintaining over new presets."""
    from hyperweave.compose.bundled_specs import resolve_bundled_spec
    from hyperweave.surfaces.discover import discover

    for frame_type in ("diagram", "matrix"):
        names = discover(frame_type)[frame_type]["presets"]
        assert names, f"no presets listed for {frame_type}"
        for name in names:
            example = discover(f"example:{frame_type}/{name}")["example"]
            bundled = resolve_bundled_spec(frame_type, name)
            assert example["field"] == bundled.field
            assert example["value"] == bundled.value


def test_example_selector_rejects_unknown_name_with_preset_menu() -> None:
    import pytest

    from hyperweave.core.errors import HwError
    from hyperweave.surfaces.discover import discover

    with pytest.raises(HwError) as exc_info:
        discover("example:diagram/no-such-preset")
    assert (exc_info.value.fix or "") != ""
