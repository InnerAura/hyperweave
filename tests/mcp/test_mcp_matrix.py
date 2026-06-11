"""Matrix MCP surface: hw_compose matrix + render_target, hw_discover."""

from __future__ import annotations

import pytest

from hyperweave.mcp.server import hw_compose, hw_discover

TINY = {
    "title": "Tiny",
    "columns": [{"id": "v", "label": "V"}],
    "rows": [{"label": "one", "cells": [{"value": 1}]}],
}


@pytest.mark.asyncio
async def test_hw_compose_matrix_svg() -> None:
    svg = await hw_compose(type="matrix", genome="primer", variant="porcelain", matrix=TINY)
    assert 'data-hw-frame="matrix"' in svg
    assert "<hw:payload" in svg and "<hw:envelope" in svg


@pytest.mark.asyncio
async def test_hw_compose_matrix_preset_adapter() -> None:
    svg = await hw_compose(type="matrix", genome="primer", connector_data={"matrix_adapter": "connector-registry"})
    assert 'data-hw-subvariant="registry"' in svg


@pytest.mark.asyncio
async def test_render_target_markdown() -> None:
    md = await hw_compose(type="matrix", genome="primer", matrix=TINY, render_target="markdown")
    assert md.startswith("**Tiny**")
    assert "| one | 1 |" in md


@pytest.mark.asyncio
async def test_render_target_html_is_a_reserved_seam() -> None:
    with pytest.raises(ValueError, match="reserved seam"):
        await hw_compose(type="matrix", genome="primer", matrix=TINY, render_target="html")


@pytest.mark.asyncio
async def test_render_target_markdown_rejects_frames_without_projection() -> None:
    with pytest.raises(ValueError, match="no markdown projection"):
        await hw_compose(type="badge", title="BUILD", value="passing", render_target="markdown")


@pytest.mark.asyncio
async def test_hw_discover_matrix() -> None:
    result = await hw_discover(what="matrix")
    matrix = result["matrix"]
    assert set(matrix["cell_kinds"]) == {"text", "check", "dot", "bar", "pill", "numeric", "chip", "glyph"}
    assert "connectors" in matrix["presets"]


@pytest.mark.asyncio
async def test_hw_discover_url_grammar_includes_matrix() -> None:
    result = await hw_discover(what="url_grammar")
    assert "matrix" in result["url_grammar"]
