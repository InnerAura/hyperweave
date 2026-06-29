"""Tests for mcp/server.py -- MCP tools and resources.

Covers the tools (hw_compose, hw_validate, hw_discover) and 3 resources
(schema, genomes, motions). Tool functions are called directly with real
compose for integration coverage. hw_compose returns {envelope, url}; the
pixels are fetched from the content cache by digest when a test needs them.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from hyperweave.compose.artifact_store import get_artifact
from hyperweave.mcp.server import (
    genomes_resource,
    hw_compose,
    hw_discover,
    hw_validate,
    motions_resource,
    schema_resource,
)


def _cached_svg(result: dict) -> str:
    """Resolve the SVG behind a {envelope, url} result via the content cache."""
    svg = get_artifact(result["url"].rsplit("/", 1)[-1])
    assert svg is not None, "composed artifact should be in the per-process cache"
    return svg


# ===========================================================================
# Tools
# ===========================================================================


def test_hw_compose_docstring_advertises_16_automata_tones() -> None:
    """MCP docs must match the 16-tone automata registry."""
    doc = hw_compose.__doc__ or ""
    assert "16 solo tones" in doc
    assert "12 solo tones" not in doc
    for tone in ("sulfur", "indigo", "burgundy", "copper"):
        assert tone in doc


async def test_hw_compose_badge_returns_envelope_and_url() -> None:
    result = await hw_compose(type="badge", title="build", value="passing")
    assert isinstance(result, dict)
    assert result["url"].endswith(tuple("0123456789abcdef"))  # content-addressed handle
    assert result["envelope"]["id"].startswith("sha256:")
    assert result["envelope"]["k"] == "badge"
    assert "<svg" in _cached_svg(result)  # pixels live in the cache, not the result


async def test_hw_compose_strip() -> None:
    result = await hw_compose(type="strip", title="readme-ai", value="STARS:2.9k,FORKS:278")
    assert result["url"] and "<svg" in _cached_svg(result)


async def test_hw_compose_stats_accepts_multi_provider_data_tokens() -> None:
    async def fake_fetch_metric(provider: str, identifier: str, metric: str) -> dict[str, object]:
        return {"value": 123 if provider == "github" else 456, "ttl": 300}

    with patch("hyperweave.connectors.fetch_metric", new_callable=AsyncMock, side_effect=fake_fetch_metric):
        result = await hw_compose(
            type="stats",
            title="GLM-5",
            stats_username="GLM-5",
            genome="chrome",
            data="github:zai-org/GLM-5.stars,hf:zai-org/GLM-5.1.downloads",
        )

    svg = _cached_svg(result)
    assert "GH STARS" in svg
    assert "HF DL" in svg


async def test_hw_compose_divider() -> None:
    result = await hw_compose(type="divider", divider_variant="void")
    assert result["url"] and "<svg" in _cached_svg(result)


async def test_hw_compose_markdown_target_returns_string() -> None:
    md = await hw_compose(type="badge", title="BUILD", value="passing", render_target="markdown")
    assert isinstance(md, str)
    assert "BUILD" in md


async def test_hw_compose_respond_svg_returns_raw_markup() -> None:
    # Opt-in inline pixels: respond="svg" returns the raw SVG string, while the
    # default still returns the {envelope, url} handle.
    svg = await hw_compose(type="badge", title="BUILD", value="passing", respond="svg")
    assert isinstance(svg, str)
    assert svg.lstrip().startswith("<svg") or "<svg" in svg
    default = await hw_compose(type="badge", title="BUILD", value="passing")
    assert isinstance(default, dict) and "url" in default


async def test_hw_validate_good_and_bad() -> None:
    good = await hw_validate({"type": "badge", "genome": "primer", "spec": {"title": "X"}})
    assert good["valid"] is True
    bad = await hw_validate({"type": "not-a-frame"})
    assert bad["valid"] is False
    assert bad["error"]["code"] == "TYPE_UNKNOWN"


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
    assert "brutalist" in ids


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
    assert "marquee" in result["frames"]
    # banner / marquee-counter / marquee-vertical / timeline removed in v0.2.14.
    assert "banner" not in result["frames"]
    assert "timeline" not in result["frames"]


async def test_hw_discover_url_grammar_advertises_data_token_routes() -> None:
    """url_grammar advertises both badge route shapes plus the data-bearing frames.

    Replaces the prior session-2A+2B test which exercised banner/timeline keys.
    """
    result = await hw_discover(what="url_grammar")
    grammar = result["url_grammar"]
    for key in ("badge (static)", "badge (data-driven)", "strip", "marquee", "stats", "chart-stars"):
        assert key in grammar, f"Missing {key} entry in url_grammar"
        entry = grammar[key]
        assert "pattern" in entry
        assert entry["pattern"].startswith("/v1/")
        assert "example" in entry
    # The data-driven shapes carry the unified `data` query param.
    assert "data" in grammar["badge (data-driven)"]["query_params"]
    assert "data" in grammar["strip"]["query_params"]
    assert "data" in grammar["marquee"]["query_params"]
    assert "data" in grammar["stats"]["query_params"]

    # Route-shape assertions lock the patterns against the HTTP route source of truth.
    assert grammar["stats"]["pattern"] == "/v1/stats/{username}/{genome}.{motion}"
    assert grammar["chart-stars"]["pattern"] == "/v1/chart/stars/{owner}/{repo}/{genome}.{motion}"
    # Banner / timeline routes were deleted in v0.2.14.
    assert "banner" not in grammar
    assert "timeline" not in grammar


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
    assert "brutalist" in data
    assert "chrome" in data


async def test_motions_resource() -> None:
    result = await motions_resource()
    data = json.loads(result)
    assert "static" in data
