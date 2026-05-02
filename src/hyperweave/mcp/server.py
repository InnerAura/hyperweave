"""FastMCP v3 server -- MCP tools and resources for HyperWeave.

4 tools (compose, live, kit, discover) + 3 resources (schema, genomes, motions).
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

from hyperweave import __version__

mcp = FastMCP(
    name="HyperWeave",
    version=__version__,
    instructions=(
        "Compositor API for self-contained SVG artifacts from semantic parameters. "
        "Use hw_compose for any artifact type. Use hw_live for live-data badges. "
        "Use hw_discover to see available genomes, motions, glyphs, and frame types."
    ),
)


# ── Tools ────────────────────────────────────────────────────────────


@mcp.tool()
async def hw_compose(
    type: str = "badge",
    title: str = "",
    value: str = "",
    genome: str = "brutalist",
    state: str = "active",
    motion: str = "static",
    glyph: str = "",
    glyph_mode: str = "auto",
    regime: str = "normal",
    size: str = "default",
    shape: str = "",
    variant: str = "",
    divider_variant: str = "zeropoint",
    direction: str = "ltr",
    speeds: list[float] | None = None,
    data: str = "",
    telemetry_data: dict[str, Any] | None = None,
    genome_override: dict[str, Any] | None = None,
    connector_data: dict[str, Any] | None = None,
    stats_username: str = "",
    chart_owner: str = "",
    chart_repo: str = "",
) -> str:
    """Compose a HyperWeave artifact. Returns self-contained SVG.

    type: badge | strip | icon | divider | marquee-horizontal |
          receipt | rhythm-strip | master-card | catalog | stats | chart

    genome: brutalist (dark, sharp corners, emerald accent) |
            chrome (dark, metallic, blue-silver gradient) |
            automata (cellular bifamily; teal + amethyst)
            — or pass ``genome_override`` as an inline genome dict to bypass
              the built-in registry (equivalent to CLI ``--genome-file``).

    Content by frame type:
      badge:    title="STARS" value="12345" (two-panel badge)
                — or title="STARS" data="gh:owner/repo.stars" (data-driven)
      strip:    title="readme-ai" value="STARS:2.9k,FORKS:278" (metric strip)
                — or strip with data="gh:owner/repo.stars,gh:owner/repo.forks"
      icon:     glyph="github" (64x64 icon frame)
      divider:  divider_variant=block|current|takeoff|void|zeropoint|dissolve
      marquee:  title="ITEM1 | ITEM2" (pipe-separated for raw text)
                — or data="text:NEW,gh:owner/repo.stars,text:DOWNLOAD"
      receipt:  telemetry_data={session data contract dict}
      stats:    stats_username="eli64s" + connector_data={stars_total, ...}
      chart:    chart_owner/chart_repo + connector_data={points, current_stars}

    The ``data`` parameter is the unified data-token grammar. Forms:
      text:STRING          — raw display text
      kv:KEY=VALUE         — static literal, role-tagged
      gh:owner/repo.metric — GitHub
      pypi:pkg.metric      — PyPI
      npm:pkg.metric / hf:org/model.metric / arxiv:id.metric / docker:owner/image.metric

    Multiple tokens are separated by ``,``. Embedded commas in text/kv
    payloads escape as ``\\,``. When ``data`` is set, this tool fetches live
    values inline (network I/O), so callers don't need to pre-fetch via
    ``connector_data``. For stats/chart frames, ``connector_data`` remains
    the pre-fetched payload pathway and is preferred when the caller already
    has the data.

    motion (badge/strip/icon): chromatic-pulse | corner-trace | dual-orbit |
                                entanglement | rimrun
    state: active | passing | building | warning | critical | failing | offline
    glyph_mode: auto | fill | wire | none
    size: default | compact
    shape: square | circle (icon frame shape, genome-dependent)
    variant: blue | purple | bifamily (automata chromatic axis; empty = frame default)
    """
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    final_value = value
    data_tokens_resolved: list[Any] | None = None

    if data:
        from hyperweave.serve.data_tokens import (
            format_for_value,
            parse_data_tokens,
            resolve_data_tokens,
        )

        tokens = parse_data_tokens(data)
        resolved, _ttl = await resolve_data_tokens(tokens)
        if type == "marquee-horizontal":
            data_tokens_resolved = list(resolved)
        else:
            formatted = format_for_value(resolved)
            if formatted:
                final_value = formatted

    spec = ComposeSpec(
        type=type,
        genome_id=genome,
        title=title,
        value=final_value,
        state=state,
        motion=motion,
        glyph=glyph,
        glyph_mode=glyph_mode,
        regime=regime,
        size=size,
        shape=shape,
        variant=variant,
        divider_variant=divider_variant,
        marquee_direction=direction,
        marquee_speeds=speeds,
        telemetry_data=telemetry_data,
        genome_override=genome_override,
        connector_data=connector_data,
        stats_username=stats_username,
        chart_owner=chart_owner,
        chart_repo=chart_repo,
        data_tokens=data_tokens_resolved,
    )

    result = compose(spec)
    return result.svg


@mcp.tool()
async def hw_live(
    provider: str,
    identifier: str,
    metric: str,
    genome: str = "brutalist",
    glyph: str = "",
    state: str = "active",
) -> str:
    """Compose a data-driven badge — convenience wrapper over hw_compose.

    Equivalent to ``hw_compose(type="badge", title=metric.upper(),
    data=f"{provider}:{identifier}.{metric}", ...)``. Kept as a separate
    tool because the (provider, identifier, metric) triple is more
    discoverable than the colon/dot DSL for first-time agents. New code
    should prefer ``hw_compose`` with the unified ``data`` parameter.

    provider: gh | github | pypi | npm | arxiv | huggingface | hf | docker
    identifier: owner/repo (github), package-name (pypi/npm), paper-id (arxiv)
    metric: stars | forks | version | downloads | likes | pull_count
    """
    return await hw_compose(
        type="badge",
        title=metric.upper(),
        data=f"{provider}:{identifier}.{metric}",
        genome=genome,
        glyph=glyph,
        state=state,
    )


@mcp.tool()
async def hw_kit(
    type: str = "readme",
    genome: str = "brutalist",
    project: str = "",
    badges: str = "",
    social: str = "",
) -> dict[str, str]:
    """Compose a full artifact kit. Returns dict of SVGs keyed by artifact name.

    type: readme (default)
    badges: comma-separated "label:value" pairs, e.g. "build:passing,version:v0.6.3"
    social: comma-separated glyph IDs, e.g. "github,discord,x"
    """
    from hyperweave.kit import compose_kit

    results = compose_kit(type, genome, project, badges, social)
    return {name: result.svg for name, result in results.items()}


@mcp.tool()
async def hw_discover(
    what: str = "all",
) -> dict[str, Any]:
    """Discover available HyperWeave components.

    what: all | genomes | motions | glyphs | frames | url_grammar
    Returns structured data about available options for hw_compose.
    """
    from hyperweave.config.loader import get_loader
    from hyperweave.core.enums import FrameType

    loader = get_loader()
    result: dict[str, Any] = {}

    if what in ("all", "genomes"):
        result["genomes"] = [
            {
                "id": gid,
                "name": g.get("name", gid),
                "category": g.get("category", "dark"),
                "profile": g.get("profile", "brutalist"),
                "compatible_motions": g.get("compatible_motions", ["static"]),
            }
            for gid, g in loader.genomes.items()
        ]

    if what in ("all", "motions"):
        result["motions"] = [
            {
                "id": mid,
                "name": m.get("name", mid),
                "type": m.get("type", "unknown"),
                "applies_to": m.get("applies_to", m.get("frames", [])),
                "cim_compliant": m.get("cim_compliant", True),
            }
            for mid, m in loader.motions.items()
        ]

    if what in ("all", "glyphs"):
        result["glyphs"] = sorted(loader.glyphs.keys())

    if what in ("all", "frames"):
        result["frames"] = [ft.value for ft in FrameType]

    if what in ("all", "url_grammar"):
        data_grammar = (
            "Comma-separated tokens: text:STRING | kv:KEY=VALUE | "
            "gh:owner/repo.metric | pypi:pkg.metric | npm:pkg.metric | "
            "hf:org/model.metric | arxiv:id.metric | docker:owner/image.metric. "
            "Embedded commas in text/kv payloads escape as \\,."
        )
        result["url_grammar"] = {
            "badge (static)": {
                "pattern": "/v1/badge/{title}/{value}/{genome}.{motion}",
                "query_params": {
                    "glyph": "Glyph identifier (e.g. github, python)",
                    "glyph_mode": "auto | fill | wire | none",
                    "state": "active | passing | building | warning | critical | failing | offline",
                    "regime": "normal | permissive | ungoverned",
                    "size": "default | compact",
                    "variant": "blue | purple | bifamily (automata)",
                    "t": "Title override (use when title contains slashes)",
                },
                "example": "/v1/badge/build/passing/brutalist.static",
            },
            "badge (data-driven)": {
                "pattern": "/v1/badge/{title}/{genome}.{motion}?data=...",
                "query_params": {
                    "data": data_grammar,
                    "glyph": "Glyph identifier",
                    "glyph_mode": "auto | fill | wire | none",
                    "state": "Semantic state",
                    "regime": "normal | permissive | ungoverned",
                    "size": "default | compact",
                    "variant": "blue | purple | bifamily (automata)",
                },
                "example": "/v1/badge/STARS/brutalist.static?data=gh:anthropics/claude-code.stars",
            },
            "strip": {
                "pattern": "/v1/strip/{title}/{genome}.{motion}",
                "query_params": {
                    "value": "Static metrics: STARS:2.9k,FORKS:278",
                    "data": data_grammar,
                    "subtitle": "Subtitle under identity (cellular paradigm)",
                    "glyph": "Glyph identifier",
                    "state": "Semantic state",
                    "variant": "blue | purple | bifamily (automata)",
                    "t": "Title override (use when title contains slashes)",
                },
                "example": (
                    "/v1/strip/readme-ai/brutalist.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks"
                ),
            },
            "icon": {
                "pattern": "/v1/icon/{glyph}/{genome}.{motion}",
                "query_params": {
                    "shape": "square | circle",
                    "glyph_mode": "auto | fill | wire | none",
                    "state": "Semantic state",
                    "variant": "blue | purple | bifamily (automata)",
                },
                "example": "/v1/icon/github/chrome.static?shape=circle",
            },
            "divider": {
                "pattern": "/v1/divider/{variant}/{genome}.{motion}",
                "query_params": {
                    "variant": "blue | purple | bifamily (automata)",
                },
                "example": "/v1/divider/void/brutalist.static",
            },
            "marquee-horizontal": {
                "pattern": "/v1/marquee/{title}/{genome}.{motion}",
                "query_params": {
                    "data": data_grammar + " When set, drives the scroll directly and ignores title.",
                    "direction": "ltr | rtl",
                    "speeds": "Single float scroll speed multiplier",
                    "variant": "blue | purple | bifamily (automata)",
                    "t": "Title override (use when title contains slashes)",
                },
                "example": (
                    "/v1/marquee/SCROLL/brutalist.static?data=text:NEW%20RELEASE,gh:anthropics/claude-code.stars"
                ),
            },
            "stats": {
                "pattern": "/v1/stats/{username}/{genome}.{motion}",
                "query_params": {},
                "example": "/v1/stats/eli64s/chrome.static",
            },
            "chart-stars": {
                "pattern": "/v1/chart/stars/{owner}/{repo}/{genome}.{motion}",
                "query_params": {},
                "example": "/v1/chart/stars/torvalds/linux/brutalist.static",
            },
        }

    return result


# ── Resources ────────────────────────────────────────────────────────


@mcp.resource("hyperweave://schema")
async def schema_resource() -> str:
    """ComposeSpec parameter reference for hw_compose.

    Lists all valid parameter values and their constraints.
    """
    from hyperweave.core.enums import (
        ArtifactStatus,
        DividerVariant,
        FrameType,
        GenomeId,
        GlyphMode,
        MotionId,
        Regime,
    )

    schema = {
        "type": [ft.value for ft in FrameType],
        "genome": [g.value for g in GenomeId],
        "motion": [m.value for m in MotionId],
        "state": [s.value for s in ArtifactStatus],
        "glyph_mode": [g.value for g in GlyphMode],
        "regime": [r.value for r in Regime],
        "divider_variant": [d.value for d in DividerVariant],
    }
    return json.dumps(schema, indent=2)


@mcp.resource("hyperweave://genomes")
async def genomes_resource() -> str:
    """Full genome configurations with colors, motions, and profiles."""
    from hyperweave.config.loader import get_loader

    loader = get_loader()
    return json.dumps(
        {gid: g for gid, g in loader.genomes.items()},
        indent=2,
    )


@mcp.resource("hyperweave://motions")
async def motions_resource() -> str:
    """Motion primitives with frame compatibility and CIM compliance."""
    from hyperweave.config.loader import get_loader

    loader = get_loader()
    return json.dumps(
        {mid: m for mid, m in loader.motions.items()},
        indent=2,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
