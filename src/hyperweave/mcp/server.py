"""FastMCP v3 server -- MCP tools and resources for HyperWeave.

4 tools (compose, live, kit, discover) + 3 resources (schema, genomes, motions).
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

mcp = FastMCP(
    name="HyperWeave",
    version="0.1.0",
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
    genome: str = "brutalist-emerald",
    state: str = "active",
    motion: str = "static",
    glyph: str = "",
    glyph_mode: str = "auto",
    regime: str = "normal",
    variant: str = "default",
    divider_variant: str = "zeropoint",
    direction: str = "ltr",
    rows: int = 3,
    speeds: list[float] | None = None,
    telemetry_data: dict[str, Any] | None = None,
) -> str:
    """Compose a HyperWeave artifact. Returns self-contained SVG.

    type: badge | strip | banner | icon | divider |
          marquee-horizontal | marquee-vertical | marquee-counter |
          receipt | rhythm-strip | master-card | catalog

    genome: brutalist-emerald (dark, sharp corners, emerald accent) |
            chrome-horizon (dark, metallic, blue-silver gradient)

    Content by frame type:
      badge:    title="build" value="passing" (two-panel badge)
      strip:    title="readme-ai" value="STARS:2.9k,FORKS:278" (metric strip)
      banner:   title="HYPERWEAVE" value="Living Artifacts" (hero text)
      icon:     glyph="github" (64x64 icon frame)
      divider:  divider_variant=block|current|takeoff|void|zeropoint
      marquee:  title="TEXT | MORE" (pipe-separated for counter rows)
      receipt:  telemetry_data={session data contract dict}

    motion (banner): cascade | drop | broadcast | bars | breach |
                     collapse | converge | crash | pulse
    motion (badge/strip): chromatic-pulse | corner-trace | dual-orbit |
                          entanglement | rimrun

    state: active | passing | building | warning | critical | failing | offline
    glyph_mode: auto | fill | wire | none
    variant: default | compact (banner), squircle | circle | hexagon (icon)
    """
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type=type,
        genome_id=genome,
        title=title,
        value=value,
        state=state,
        motion=motion,
        glyph=glyph,
        glyph_mode=glyph_mode,
        regime=regime,
        variant=variant,
        divider_variant=divider_variant,
        marquee_direction=direction,
        marquee_rows=rows,
        marquee_speeds=speeds,
        telemetry_data=telemetry_data,
    )

    result = compose(spec)
    return result.svg


@mcp.tool()
async def hw_live(
    provider: str,
    identifier: str,
    metric: str,
    genome: str = "brutalist-emerald",
    glyph: str = "",
    state: str = "active",
) -> str:
    """Compose a badge with live data fetched from a provider.

    provider: github | pypi | npm | arxiv | huggingface | docker
    identifier: owner/repo (github), package-name (pypi/npm), paper-id (arxiv)
    metric: stars | forks | version | downloads | likes | pull_count

    Examples:
      provider="github", identifier="anthropics/claude-code", metric="stars"
      provider="pypi", identifier="fastmcp", metric="downloads"
      provider="npm", identifier="fastmcp", metric="version"
    """
    label = metric
    value = "n/a"

    try:
        from hyperweave.connectors import fetch_metric

        data = await fetch_metric(provider, identifier, metric)
        value = str(data.get("value", "n/a"))
    except Exception:
        value = "error"

    return await hw_compose(
        type="badge",
        title=label,
        value=value,
        genome=genome,
        glyph=glyph,
        state=state,
    )


@mcp.tool()
async def hw_kit(
    type: str = "readme",
    genome: str = "brutalist-emerald",
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

    what: all | genomes | motions | glyphs | frames
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
