"""Tests for mcp/server.py -- MCP tools and resources.

Covers the 4 tools (hw_compose, hw_live, hw_kit, hw_discover) and
3 resources (schema, genomes, motions). Tool functions are called
directly with real compose for integration coverage.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from hyperweave.mcp.server import (
    genomes_resource,
    hw_compose,
    hw_discover,
    hw_kit,
    hw_live,
    motions_resource,
    schema_resource,
)

# ===========================================================================
# Tools
# ===========================================================================


async def test_hw_compose_badge() -> None:
    result = await hw_compose(type="badge", title="build", value="passing")
    assert isinstance(result, str)
    assert "<svg" in result


async def test_hw_compose_strip() -> None:
    result = await hw_compose(type="strip", title="readme-ai", value="STARS:2.9k,FORKS:278")
    assert "<svg" in result


async def test_hw_compose_divider() -> None:
    result = await hw_compose(type="divider", divider_variant="void")
    assert "<svg" in result


async def test_hw_live_success() -> None:
    mock_data = {"value": 5000, "ttl": 300}
    with patch("hyperweave.connectors.fetch_metric", new_callable=AsyncMock, return_value=mock_data):
        result = await hw_live(provider="github", identifier="anthropics/claude-code", metric="stars")
        assert "<svg" in result


async def test_hw_live_error_fallback() -> None:
    with patch("hyperweave.connectors.fetch_metric", new_callable=AsyncMock, side_effect=Exception("timeout")):
        result = await hw_live(provider="github", identifier="anthropics/claude-code", metric="stars")
        assert "<svg" in result  # Still returns a badge with "error" value


async def test_hw_kit_readme() -> None:
    result = await hw_kit(type="readme", genome="brutalist-emerald", project="test", badges="build:passing")
    assert isinstance(result, dict)
    assert "banner" in result
    assert "badge-build" in result
    assert all("<svg" in svg for svg in result.values())


async def test_hw_discover_all() -> None:
    result = await hw_discover(what="all")
    assert "genomes" in result
    assert "motions" in result
    assert "glyphs" in result
    assert "frames" in result


async def test_hw_discover_genomes() -> None:
    result = await hw_discover(what="genomes")
    assert "genomes" in result
    assert "motions" not in result
    ids = [g["id"] for g in result["genomes"]]
    assert "brutalist-emerald" in ids


async def test_hw_discover_motions() -> None:
    result = await hw_discover(what="motions")
    assert "motions" in result
    ids = [m["id"] for m in result["motions"]]
    assert "static" in ids


async def test_hw_discover_frames() -> None:
    result = await hw_discover(what="frames")
    assert "frames" in result
    assert "badge" in result["frames"]
    assert "strip" in result["frames"]
    assert "banner" in result["frames"]


# ===========================================================================
# Resources
# ===========================================================================


async def test_schema_resource() -> None:
    result = await schema_resource()
    data = json.loads(result)
    assert "type" in data
    assert "badge" in data["type"]
    assert "genome" in data
    assert "motion" in data
    assert "state" in data


async def test_genomes_resource() -> None:
    result = await genomes_resource()
    data = json.loads(result)
    assert "brutalist-emerald" in data
    assert "chrome-horizon" in data


async def test_motions_resource() -> None:
    result = await motions_resource()
    data = json.loads(result)
    assert "static" in data
