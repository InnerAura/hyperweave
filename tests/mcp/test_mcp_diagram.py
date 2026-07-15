"""Diagram MCP surface: hw_compose diagram + render_target, hw_discover."""

from __future__ import annotations

import json
import re

import pytest

from hyperweave.compose.artifact_store import get_artifact
from hyperweave.mcp.server import hw_compose, hw_discover

TINY = {
    "topology": "pipeline",
    "title": "Tiny",
    "nodes": [{"label": "A"}, {"label": "B", "role": "hero"}, {"label": "C"}],
}

_PAYLOAD_RE = re.compile(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>", re.DOTALL)


def _cached_svg(result: dict) -> str:
    """hw_compose returns {envelope, url}; fetch the cached SVG by its digest."""
    svg = get_artifact(result["url"].rsplit("/", 1)[-1])
    assert svg is not None
    return svg


@pytest.mark.asyncio
async def test_hw_compose_diagram_svg() -> None:
    svg = _cached_svg(await hw_compose(type="diagram", genome="primer", variant="porcelain", diagram=TINY))
    assert 'data-hw-type="diagram"' in svg
    assert "<hw:payload" in svg and "<hw:envelope" in svg


@pytest.mark.asyncio
async def test_composite_only_is_the_only_tier() -> None:
    # The kit grammar is compositor-only by construction (dash | particle) —
    # performance is always composite-only and nothing ladders down.
    svg = _cached_svg(
        await hw_compose(
            type="diagram",
            genome="primer",
            diagram=dict(TINY, edge_motion="particle"),
            performance="composite-only",
        )
    )
    m = _PAYLOAD_RE.search(svg)
    assert m, "hw:payload missing"
    payload = json.loads(m.group(1))
    assert payload["rendered"]["performance"] == "composite-only"
    assert set(payload["rendered"]["edge_motion"]) == {"particle"}
    assert payload["spec"]["edge_motion"] == "particle"


@pytest.mark.asyncio
async def test_render_target_markdown() -> None:
    md = await hw_compose(type="diagram", genome="primer", diagram=TINY, render_target="markdown")
    assert md.startswith("**Tiny**")
    assert "A → B" in md


@pytest.mark.asyncio
async def test_markdown_available_on_lightweight_frames() -> None:
    # Post-envelope-floor: every frame has a text-shadow projection,
    # so render_target=markdown returns it for a badge instead of rejecting.
    md = await hw_compose(type="badge", title="X", value="y", render_target="markdown")
    assert md.strip() and "X" in md


@pytest.mark.asyncio
async def test_hw_discover_diagram_section() -> None:
    result = await hw_discover(what="diagram")
    section = result["diagram"]
    assert "sequence" in section["topologies"]
    assert "state-machine" in section["topologies"]
    assert "rag-pipeline" in section["presets"]
    assert "dash" in section["edge_motion"] and "particle" in section["edge_motion"]
    assert "beam" not in section["edge_motion"] and "flow" not in section["edge_motion"]


@pytest.mark.asyncio
async def test_diagram_renders_caption_not_masthead() -> None:
    """The public diagram axis always renders kit chrome (caption): no
    masthead band, no brand-footer line. `chrome` is retired from hw_compose
    — bare only exists internally for sec 12.1 recursive embeds."""
    svg = _cached_svg(await hw_compose(type="diagram", genome="primer", diagram=TINY))
    assert "INNERAURA LABS" not in svg
    assert 'data-hw-region="masthead"' not in svg
    assert ">Tiny</text>" in svg  # the caption sentence (subtitle falls back to title)


@pytest.mark.asyncio
async def test_hw_compose_rejects_stray_chrome_kwarg() -> None:
    with pytest.raises(TypeError):
        await hw_compose(type="diagram", genome="primer", diagram=TINY, chrome="bare")  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_edge_motion_override() -> None:
    """hw_compose edge_motion overrides the spec's own (HTTP/CLI parity)."""
    svg = _cached_svg(
        await hw_compose(
            type="diagram", genome="primer", diagram=dict(TINY, edge_motion="dash"), edge_motion="particle"
        )
    )
    m = _PAYLOAD_RE.search(svg)
    assert m, "hw:payload missing"
    assert "particle" in json.loads(m.group(1))["rendered"]["edge_motion"]


@pytest.mark.asyncio
async def test_edge_motion_invalid_raises() -> None:
    with pytest.raises(ValueError, match="edge_motion must be one of"):
        await hw_compose(type="diagram", genome="primer", diagram=TINY, edge_motion="zoom")


@pytest.mark.asyncio
async def test_discover_emits_layout_slugs() -> None:
    """hw_discover('diagram') lists the flattened requestable layout slugs."""
    res = await hw_discover("diagram")
    data = json.loads(res) if isinstance(res, str) else res
    slugs = data["diagram"]["layout_slugs"]
    assert len(slugs) == 18
    assert {"fanout-radial", "fanout-downward", "tree-radial", "dag", "state-machine", "hub", "lanes"} <= set(slugs)
