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
    genome: str = "brutalist-emerald",
    state: str = "active",
    motion: str = "static",
    glyph: str = "",
    glyph_mode: str = "auto",
    regime: str = "normal",
    variant: str = "default",
    shape: str = "",
    divider_variant: str = "zeropoint",
    direction: str = "ltr",
    rows: int = 3,
    speeds: list[float] | None = None,
    telemetry_data: dict[str, Any] | None = None,
    # ── Session 2A+2B parity ──
    genome_override: dict[str, Any] | None = None,
    connector_data: dict[str, Any] | None = None,
    timeline_items: list[dict[str, Any]] | None = None,
    stats_username: str = "",
    chart_owner: str = "",
    chart_repo: str = "",
) -> str:
    """Compose a HyperWeave artifact. Returns self-contained SVG.

    type: badge | strip | banner | icon | divider |
          marquee-horizontal | marquee-vertical | marquee-counter |
          receipt | rhythm-strip | master-card | catalog |
          stats | chart | timeline

    genome: brutalist-emerald (dark, sharp corners, emerald accent) |
            chrome-horizon (dark, metallic, blue-silver gradient)
            — or pass ``genome_override`` as an inline genome dict to bypass
              the built-in registry (equivalent to CLI ``--genome-file``).

    Content by frame type:
      badge:    title="build" value="passing" (two-panel badge)
      strip:    title="readme-ai" value="STARS:2.9k,FORKS:278" (metric strip)
      banner:   title="HYPERWEAVE" value="Living Artifacts" (hero text)
      icon:     glyph="github" (64x64 icon frame)
      divider:  divider_variant=block|current|takeoff|void|zeropoint
      marquee:  title="TEXT | MORE" (pipe-separated for counter rows)
      receipt:  telemetry_data={session data contract dict}
      stats:    stats_username="eli64s" + connector_data={stars_total, ...}
      chart:    chart_owner/chart_repo + connector_data={points, current_stars}
      timeline: timeline_items=[{title, subtitle, status, date}, ...]

    Network I/O for stats/chart is NOT done inside this tool — callers must
    pre-fetch via hw_live or the connectors module and pass results through
    ``connector_data`` (or ``timeline_items`` for the timeline frame). This
    preserves the pure-function semantics of compose() and keeps the tool
    deterministic for agents.

    motion (banner): cascade | drop | broadcast | bars | breach |
                     collapse | converge | crash | pulse
    motion (badge/strip): chromatic-pulse | corner-trace | dual-orbit |
                          entanglement | rimrun

    state: active | passing | building | warning | critical | failing | offline
    glyph_mode: auto | fill | wire | none
    variant: default | compact (banner)
    shape: square | circle (icon frame shape, genome-dependent)
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
        shape=shape,
        divider_variant=divider_variant,
        marquee_direction=direction,
        marquee_rows=rows,
        marquee_speeds=speeds,
        telemetry_data=telemetry_data,
        genome_override=genome_override,
        connector_data=connector_data,
        timeline_items=timeline_items,
        stats_username=stats_username,
        chart_owner=chart_owner,
        chart_repo=chart_repo,
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
        result["url_grammar"] = {
            "badge": {
                "pattern": "/v1/badge/{title}/{value}/{genome}.{motion}",
                "query_params": {
                    "glyph": "Glyph identifier (e.g. github, python)",
                    "glyph_mode": "auto | fill | wire | none",
                    "state": "active | passing | building | warning | critical | failing | offline",
                    "regime": "normal | permissive | ungoverned",
                    "t": "Title override (use when title contains slashes)",
                },
                "example": "/v1/badge/build/passing/brutalist-emerald.static",
            },
            "strip": {
                "pattern": "/v1/strip/{title}/{genome}.{motion}",
                "query_params": {
                    "value": "Metrics text: STARS:2.9k,FORKS:278",
                    "live": "Live data: github:owner/repo:stars,pypi:pkg:version",
                    "glyph": "Glyph identifier",
                    "state": "Semantic state",
                    "t": "Title override (use when title contains slashes)",
                },
                "example": "/v1/strip/readme-ai/brutalist-emerald.static?value=STARS:2.9k",
            },
            "banner": {
                "pattern": "/v1/banner/{title}/{genome}.{motion}",
                "query_params": {
                    "subtitle": "Banner subtitle text",
                    "value": "Alias for subtitle",
                    "glyph": "Glyph identifier",
                    "state": "Semantic state",
                    "t": "Title override (use when title contains slashes)",
                },
                "example": "/v1/banner/HYPERWEAVE/brutalist-emerald.cascade?subtitle=Living+Artifacts",
            },
            "icon": {
                "pattern": "/v1/icon/{glyph}/{genome}.{motion}",
                "query_params": {
                    "shape": "square | circle",
                    "glyph_mode": "auto | fill | wire | none",
                    "state": "Semantic state",
                },
                "example": "/v1/icon/github/chrome-horizon.static?shape=circle",
            },
            "divider": {
                "pattern": "/v1/divider/{variant}/{genome}",
                "query_params": {},
                "example": "/v1/divider/void/brutalist-emerald",
            },
            "marquee": {
                "pattern": "/v1/marquee/{title}/{genome}.{motion}",
                "query_params": {
                    "direction": "ltr | rtl | up | down",
                    "rows": "Number of rows (counter variant uses 3)",
                    "speeds": "Comma-separated speed multipliers per row",
                    "t": "Title override (use when title contains slashes)",
                },
                "example": "/v1/marquee/HYPERWEAVE/brutalist-emerald.static?rows=3",
            },
            "live": {
                "pattern": "/v1/live/{provider}/{identifier}/{metric}/{genome}.{motion}",
                "query_params": {
                    "glyph": "Glyph identifier",
                    "state": "Semantic state",
                },
                "example": "/v1/live/github/eli64s/readme-ai/stars/brutalist-emerald.static",
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
