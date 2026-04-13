#!/usr/bin/env python3
"""Generate the full HyperWeave proof set -- all genomes x frame/motion/state taxonomy.

Usage:
    uv run python scripts/generate_proofset.py          # static only
    uv run python scripts/generate_proofset.py --live    # include network-dependent artifacts
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

# Ensure src/ is importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_genomes
from hyperweave.core.enums import (
    ArtifactStatus,
    BorderMotionId,
    DividerVariant,
    FrameType,
    GenomeId,
    KineticMotionId,
    Regime,
)
from hyperweave.core.models import ComposeSpec

OUT = Path(__file__).resolve().parent.parent / "outputs"


def _genome_motions(genome_id: str) -> tuple[list[str], list[str]]:
    """Return (border_motions, kinetic_motions) compatible with a genome.

    Intersects the genome's ``compatible_motions`` list from its JSON
    config with the BorderMotionId and KineticMotionId enum sets.
    Only motions that the genome has been tested with are returned.
    """
    genomes = load_genomes()
    genome_cfg = genomes.get(genome_id)
    compatible: set[str] = set(genome_cfg.compatible_motions) if genome_cfg else {"static"}
    border = [m for m in BorderMotionId if m.value in compatible]
    kinetic = [m for m in KineticMotionId if m.value in compatible]
    return border, kinetic


# ── Mock telemetry data for receipt / rhythm-strip / master-card ──

MOCK_TELEMETRY: dict[str, Any] = {
    "session": {"model": "claude-opus-4-6", "duration_s": 1932},
    "cost": {"total": 0.42, "input": 0.28, "output": 0.14},
    "tokens": {"input": 23765, "output": 2614},
    "tools": [
        {"name": "Read", "count": 38},
        {"name": "Bash", "count": 22},
        {"name": "Write", "count": 8},
        {"name": "Edit", "count": 5},
        {"name": "Task", "count": 12},
        {"name": "Grep", "count": 14},
    ],
    "stages": [
        {"name": "Read", "pct": 40},
        {"name": "Bash", "pct": 25},
        {"name": "Edit", "pct": 15},
        {"name": "Write", "pct": 10},
        {"name": "Task", "pct": 5},
        {"name": "Grep", "pct": 5},
    ],
    "velocity": {"loc_added": 284, "loc_removed": 31},
    "sessions": [
        {"tokens": 0, "corrections": 0, "label": "idle"},
        {"tokens": 36133, "corrections": 5, "label": "Feb 17"},
        {"tokens": 43552, "corrections": 0, "label": "Feb 17"},
        {"tokens": 8091, "corrections": 4, "label": "Feb 19"},
        {"tokens": 2559, "corrections": 0, "label": "Feb 20"},
        {"tokens": 4014, "corrections": 0, "label": "Feb 20"},
        {"tokens": 4951, "corrections": 0, "label": "Feb 20"},
        {"tokens": 56530, "corrections": 2, "label": "Feb 20"},
        {"tokens": 87079, "corrections": 1, "label": "Feb 20"},
        {"tokens": 26379, "corrections": 4, "label": "Feb 21"},
    ],
    "files": [
        {"path": "compose/engine.py", "reads": 42, "writes": 8, "last": "today"},
        {"path": "core/models.py", "reads": 38, "writes": 6, "last": "today"},
        {"path": "render/templates.py", "reads": 31, "writes": 4, "last": "yest"},
        {"path": "core/text.py", "reads": 24, "writes": 3, "last": "yest"},
        {"path": "frames/badge.svg.j2", "reads": 22, "writes": 7, "last": "today"},
        {"path": "frames/strip.svg.j2", "reads": 18, "writes": 5, "last": "today"},
        {"path": "config/loader.py", "reads": 15, "writes": 2, "last": "yest"},
        {"path": "genomes/brutalist.json", "reads": 14, "writes": 1, "last": "Feb 17"},
    ],
    "skills": [
        {"name": "SVG template authoring", "lang": "Jinja2", "attempts": 24, "accepted": 21, "state": "learning"},
        {"name": "Pydantic model design", "lang": "Python", "attempts": 12, "accepted": 11, "state": "mastered"},
        {"name": "Test writing", "lang": "Python", "attempts": 8, "accepted": 5, "state": "learning"},
    ],
}

# ── Live data specs (gated behind --live) ──

LIVE_SPECS: list[dict[str, Any]] = [
    {"provider": "github", "id": "eli64s/readme-ai", "metric": "stars", "frame": "badge", "title": "STARS"},
    {
        "provider": "github",
        "id": "eli64s/readme-ai",
        "metric": "stars,forks",
        "frame": "strip",
        "title": "readme-ai",
    },
    {"provider": "pypi", "id": "readmeai", "metric": "downloads", "frame": "badge", "title": "DOWNLOADS"},
    {"provider": "docker", "id": "zeroxeli/readme-ai", "metric": "pulls", "frame": "badge", "title": "PULLS"},
    {"provider": "npm", "id": "express", "metric": "downloads", "frame": "badge", "title": "DOWNLOADS"},
]


def _compose(
    frame_type: str,
    genome: str,
    title: str = "",
    description: str = "",
    state: str = "active",
    glyph: str = "",
    *,
    motion: str = "static",
    regime: str = "normal",
    glyph_mode: str = "auto",
    divider_variant: str = "zeropoint",
    variant: str = "default",
    telemetry_data: dict[str, Any] | None = None,
) -> str:
    spec = ComposeSpec(
        type=frame_type,
        genome_id=genome,
        title=title,
        value=description,
        state=state,
        glyph=glyph,
        motion=motion,
        regime=regime,
        glyph_mode=glyph_mode,
        divider_variant=divider_variant,
        variant=variant,
        telemetry_data=telemetry_data,
    )
    return compose(spec).svg


def _write(path: Path, svg: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg)


def generate_static() -> int:
    """Generate all static (non-network) artifacts. Returns count."""
    total = 0

    for genome in GenomeId:
        gdir = OUT / "proofset" / genome

        # ── 1. Base frames ──
        base = gdir / "base"

        svg = _compose("badge", genome, "BUILD", "passing", "passing", "github")
        _write(base / "badge.svg", svg)
        total += 1

        svg = _compose("strip", genome, "readme-ai", "STARS:12.4k,FORKS:1.2k,VERSION:v0.6.9", "active", "github")
        _write(base / "strip.svg", svg)
        total += 1

        svg = _compose("banner", genome, "HYPERWEAVE", "Living SVG artifacts for agent interfaces")
        _write(base / "banner_full.svg", svg)
        total += 1

        svg = _compose("banner", genome, "HYPERWEAVE", "Living Artifacts", variant="compact")
        _write(base / "banner_compact.svg", svg)
        total += 1

        svg = _compose("icon", genome, glyph="github")
        _write(base / "icon.svg", svg)
        total += 1

        for dv in DividerVariant:
            svg = _compose("divider", genome, divider_variant=dv)
            _write(base / f"divider_{dv}.svg", svg)
            total += 1

        for mtype in ("marquee-horizontal", "marquee-vertical", "marquee-counter"):
            svg = _compose(mtype, genome, "HYPERWEAVE LIVING ARTIFACTS AI-NATIVE SVG COMPOSITOR")
            _write(base / f"{mtype.replace('-', '_')}.svg", svg)
            total += 1

        # ── 2. State machine -- badges ──
        states = gdir / "states"
        for status in (
            ArtifactStatus.PASSING,
            ArtifactStatus.WARNING,
            ArtifactStatus.CRITICAL,
            ArtifactStatus.BUILDING,
            ArtifactStatus.OFFLINE,
        ):
            svg = _compose("badge", genome, "BUILD", status.value, status, "github")
            _write(states / f"badge_{status}.svg", svg)
            total += 1

        # ── 4. State machine -- strips ──
        for status in (ArtifactStatus.ACTIVE, ArtifactStatus.WARNING, ArtifactStatus.CRITICAL):
            svg = _compose(
                "strip",
                genome,
                "readme-ai",
                "STARS:12.4k,COVERAGE:94%",
                status,
                "github",
            )
            _write(states / f"strip_{status}.svg", svg)
            total += 1

        # ── 5. Policy lanes ──
        lanes = gdir / "policy-lanes"
        for reg in (Regime.NORMAL, Regime.UNGOVERNED):
            svg = _compose("badge", genome, "BUILD", "passing", "passing", "github", regime=reg)
            _write(lanes / f"badge_{reg}.svg", svg)
            total += 1

        # ── 6. Border motions (genome-compatible only) ──
        # Border motions are non-CIM (SMIL stroke-dashoffset etc.) so we use
        # permissive regime to allow them without downgrading to static.
        compat_border, compat_kinetic = _genome_motions(genome)
        border = gdir / "border-motions"
        for mid in compat_border:
            svg = _compose(
                "badge",
                genome,
                "BUILD",
                "passing",
                "active",
                "github",
                motion=mid,
                regime=Regime.PERMISSIVE,
            )
            _write(border / f"badge_{mid}.svg", svg)
            total += 1

            svg = _compose(
                "strip",
                genome,
                "readme-ai",
                "STARS:12.4k,FORKS:1.2k",
                "active",
                motion=mid,
                regime=Regime.PERMISSIVE,
            )
            _write(border / f"strip_{mid}.svg", svg)
            total += 1

        # ── 7. Kinetic typography (genome-compatible only) ──
        kinetic = gdir / "kinetic-typography"
        for mid in compat_kinetic:
            svg = _compose(
                "banner",
                genome,
                "HYPERWEAVE",
                "Living Artifacts",
                "active",
                motion=mid,
                regime=Regime.PERMISSIVE,
            )
            _write(kinetic / f"banner_{mid}.svg", svg)
            total += 1

    # ── 8. Telemetry frames (genome-independent, generated once) ──
    telemetry_dir = OUT / "proofset" / "telemetry"
    for ftype in (FrameType.RECEIPT, FrameType.RHYTHM_STRIP, FrameType.MASTER_CARD):
        svg = _compose(ftype, GenomeId.BRUTALIST_EMERALD, telemetry_data=MOCK_TELEMETRY)
        _write(telemetry_dir / f"{ftype.value.replace('-', '_')}.svg", svg)
        total += 1

    # ── 9. Session 2A+2B new frames (stats, chart, timeline) ──
    total += _generate_session_2a2b()

    return total


# ── Session 2A+2B proof set generation ─────────────────────────────────────


_MOCK_STATS_DATA: dict[str, Any] = {
    "username": "eli64s",
    "bio": "Building HyperWeave",
    "stars_total": 12847,
    "commits_total": 1203,
    "prs_total": 89,
    "issues_total": 47,
    "contrib_total": 234,
    "streak_days": 47,
    "top_language": "Python",
    "repo_count": 63,
    "language_breakdown": [
        {"name": "Python", "pct": 68.5, "count": 43},
        {"name": "TypeScript", "pct": 18.1, "count": 11},
        {"name": "Rust", "pct": 9.5, "count": 6},
        {"name": "Go", "pct": 3.9, "count": 2},
    ],
    "heatmap_grid": [],
}

# Six-point star history curve for the mock chart data.
_MOCK_CHART_POINTS: list[dict[str, Any]] = [
    {"date": "2025-01-01T00:00:00Z", "count": 180},
    {"date": "2025-04-01T00:00:00Z", "count": 410},
    {"date": "2025-07-01T00:00:00Z", "count": 820},
    {"date": "2025-10-01T00:00:00Z", "count": 1420},
    {"date": "2026-01-01T00:00:00Z", "count": 2180},
    {"date": "2026-04-01T00:00:00Z", "count": 2850},
]

_MOCK_TIMELINE_ITEMS: list[dict[str, Any]] = [
    {"title": "v0.1", "subtitle": "Foundation", "status": "passing", "date": "2025-10"},
    {"title": "v0.2", "subtitle": "Stats Card", "status": "active", "date": "2026-04"},
    {"title": "v0.3", "subtitle": "Storage", "status": "building", "date": "2026-07"},
    {"title": "v0.4", "subtitle": "Genome Blitz", "status": "warning", "date": "2026-09"},
]


def _compose_connector(
    frame_type: str,
    genome: str,
    *,
    connector_data: dict[str, Any] | None = None,
    timeline_items: list[dict[str, Any]] | None = None,
    stats_username: str = "",
    chart_owner: str = "",
    chart_repo: str = "",
    genome_override: dict[str, Any] | None = None,
) -> str:
    """Compose a Session 2A+2B frame with pre-fetched connector data."""
    spec = ComposeSpec(
        type=frame_type,
        genome_id=genome,
        connector_data=connector_data,
        timeline_items=timeline_items,
        stats_username=stats_username,
        chart_owner=chart_owner,
        chart_repo=chart_repo,
        genome_override=genome_override,
    )
    return compose(spec).svg


def _generate_session_2a2b() -> int:
    """Generate stats, chart, and timeline artifacts for each built-in genome.

    Fetches real data from GitHub for eli64s / eli64s/readme-ai. Falls back to
    mock connector data if the API is unreachable (CI/offline environments).
    """
    import asyncio

    stats_data: dict[str, Any] | None = None
    chart_data: dict[str, Any] | None = None

    # Fetch real data from GitHub.
    try:
        from hyperweave.connectors.github import fetch_stargazer_history, fetch_user_stats

        stats_data = asyncio.run(fetch_user_stats("eli64s"))
        print("  fetched real stats for eli64s")
    except Exception as exc:
        print(f"  stats fetch failed ({exc}), using mock data")

    try:
        from hyperweave.connectors.github import fetch_stargazer_history

        chart_data = asyncio.run(fetch_stargazer_history("eli64s", "readme-ai"))
        print("  fetched real star history for eli64s/readme-ai")
    except Exception as exc:
        print(f"  chart fetch failed ({exc}), using mock data")

    # Fall back to mock data if fetch failed.
    if not stats_data:
        stats_data = dict(_MOCK_STATS_DATA)
    if not chart_data:
        chart_data = {
            "points": _MOCK_CHART_POINTS,
            "current_stars": 2850,
            "repo": "eli64s/readme-ai",
        }

    # Cross-reference: if repos endpoint was rate-limited, stars_total may be 0.
    # Supplement from chart connector's current_stars (fetched via repo metadata).
    if stats_data.get("stars_total", 0) == 0 and chart_data.get("current_stars"):
        stats_data = dict(stats_data)
        stats_data["stars_total"] = chart_data["current_stars"]
        print(f"  patched stars_total from chart data: {chart_data['current_stars']}")

    total = 0

    for genome in GenomeId:
        gdir = OUT / "proofset" / genome / "session-2a2b"

        # Stats card — paradigm comes from genome.paradigms.stats
        svg = _compose_connector(
            "stats",
            genome,
            stats_username="eli64s",
            connector_data=stats_data,
        )
        _write(gdir / "stats.svg", svg)
        total += 1

        # Star chart — single full size (900x500)
        svg = _compose_connector(
            "chart",
            genome,
            chart_owner="eli64s",
            chart_repo="readme-ai",
            connector_data=chart_data,
        )
        _write(gdir / "chart_stars_full.svg", svg)
        total += 1

        # Timeline
        svg = _compose_connector(
            "timeline",
            genome,
            timeline_items=_MOCK_TIMELINE_ITEMS,
        )
        _write(gdir / "timeline.svg", svg)
        total += 1

    return total


async def generate_live() -> int:
    """Generate live data artifacts. Returns count."""
    total = 0
    try:
        from hyperweave.connectors import fetch_metric
    except ImportError:
        print("  connectors not available, skipping live data")
        return 0

    live_dir = OUT / "proofset" / "live-data"

    for spec in LIVE_SPECS:
        try:
            data = await fetch_metric(spec["provider"], spec["id"], spec["metric"])
            value = str(data.get("value", "N/A"))
            genome = GenomeId.BRUTALIST_EMERALD

            if spec["frame"] == "badge":
                svg = _compose("badge", genome, spec["title"], value, "active")
                _write(live_dir / f"{spec['provider']}_{spec['id'].replace('/', '_')}.svg", svg)
                total += 1
            elif spec["frame"] == "strip":
                desc = ",".join(f"{k.upper()}:{v}" for k, v in data.items() if k != "provider")
                svg = _compose("strip", genome, spec["title"], desc, "active")
                _write(live_dir / f"{spec['provider']}_{spec['id'].replace('/', '_')}_strip.svg", svg)
                total += 1
        except Exception as e:
            print(f"  SKIP {spec['provider']}/{spec['id']}: {e}")

    return total


def generate_readme(total: int, live_total: int) -> None:
    """Generate outputs/README.md with image references."""
    lines = ["# HyperWeave Proof Set", ""]

    for genome in GenomeId:
        g = genome.value
        lines.extend([f"## {g}", ""])

        # Base
        lines.extend(["### Base Frames", ""])
        lines.append(f"![badge](proofset/{g}/base/badge.svg)")
        lines.append("")
        lines.append(f"![strip](proofset/{g}/base/strip.svg)")
        lines.append("")
        lines.append(f"![banner full](proofset/{g}/base/banner_full.svg)")
        lines.append("")
        lines.append(f"![banner compact](proofset/{g}/base/banner_compact.svg)")
        lines.append("")
        lines.append(f"![icon](proofset/{g}/base/icon.svg)")
        lines.append("")
        for dv in DividerVariant:
            lines.append(f"![divider {dv}](proofset/{g}/base/divider_{dv}.svg)")
            lines.append("")
        for mt in ("marquee_horizontal", "marquee_vertical", "marquee_counter"):
            lines.append(f"![{mt}](proofset/{g}/base/{mt}.svg)")
            lines.append("")

        # States
        lines.extend(["### State Machine", ""])
        for s in (
            ArtifactStatus.PASSING,
            ArtifactStatus.WARNING,
            ArtifactStatus.CRITICAL,
            ArtifactStatus.BUILDING,
            ArtifactStatus.OFFLINE,
        ):
            lines.append(f"![badge {s}](proofset/{g}/states/badge_{s}.svg)")
        lines.append("")
        for s in (ArtifactStatus.ACTIVE, ArtifactStatus.WARNING, ArtifactStatus.CRITICAL):
            lines.append(f"![strip {s}](proofset/{g}/states/strip_{s}.svg)")
        lines.append("")

        # Policy lanes
        lines.extend(["### Policy Lanes", ""])
        for r in (Regime.NORMAL, Regime.UNGOVERNED):
            lines.append(f"![badge {r}](proofset/{g}/policy-lanes/badge_{r}.svg)")
        lines.append("")

        # Border motions (genome-compatible only)
        compat_border, compat_kinetic = _genome_motions(g)
        lines.extend(["### Border Motions", ""])
        for mid in compat_border:
            lines.append(f"![badge {mid}](proofset/{g}/border-motions/badge_{mid}.svg) ")
            lines.append(f"![strip {mid}](proofset/{g}/border-motions/strip_{mid}.svg)")
            lines.append("")

        # Kinetic (genome-compatible only)
        lines.extend(["### Kinetic Typography", ""])
        for mid in compat_kinetic:
            lines.append(f"![banner {mid}](proofset/{g}/kinetic-typography/banner_{mid}.svg)")
            lines.append("")

        lines.extend(["---", ""])

    # Telemetry (genome-independent)
    lines.extend(["## Telemetry", ""])
    lines.append("*Telemetry frames use their own built-in palette (no genome skinning).*")
    lines.append("")
    for ft in (FrameType.RECEIPT, FrameType.RHYTHM_STRIP, FrameType.MASTER_CARD):
        lines.append(f"![{ft}](proofset/telemetry/{ft.value.replace('-', '_')}.svg)")
        lines.append("")

    # ── Session 2A+2B sections ──
    lines.extend(["---", "", "## Stats Cards (Session 2A+2B)", ""])
    lines.append(
        "Profile summary cards with live GitHub data. Each genome's `paradigms.stats` "
        "field selects a layout variant — the two shown here render from the SAME "
        "data dict but produce structurally different output (Principle 26)."
    )
    lines.append("")
    for genome in GenomeId:
        g = genome.value
        lines.append(f"### {g}")
        lines.append("")
        lines.append(f"![stats {g}](proofset/{g}/session-2a2b/stats.svg)")
        lines.append("")

    lines.extend(["## Star Charts (Session 2A+2B)", ""])
    lines.append(
        "Star history charts using the shared chart engine. `paradigms.chart` "
        "dispatches between `brutalist` (angular polyline + square markers) "
        "and `chrome` (bezier + diamond markers)."
    )
    lines.append("")
    for genome in GenomeId:
        g = genome.value
        lines.append(f"### {g}")
        lines.append("")
        lines.append(f"![chart full {g}](proofset/{g}/session-2a2b/chart_stars_full.svg)")
        lines.append("")

    lines.extend(["## Timeline / Roadmap (Session 2A+2B)", ""])
    lines.append(
        "Vertical node chain with opacity cascade + dash-flow spine animation. "
        "Node shape is dispatched from `genome.structural.data_point_shape`."
    )
    lines.append("")
    for genome in GenomeId:
        g = genome.value
        lines.append(f"### {g}")
        lines.append("")
        lines.append(f"![timeline {g}](proofset/{g}/session-2a2b/timeline.svg)")
        lines.append("")

    if live_total > 0:
        lines.extend(["## Live Data (requires --live)", ""])
        lines.append("*Artifacts in `proofset/live-data/`*")
        lines.append("")

    (OUT / "README.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HyperWeave proof set")
    parser.add_argument("--live", action="store_true", help="Include network-dependent artifacts")
    args = parser.parse_args()

    print("Generating static proof set...")
    total = generate_static()
    print(f"  {total} static artifacts")

    live_total = 0
    if args.live:
        print("Generating live data artifacts...")
        live_total = asyncio.run(generate_live())
        print(f"  {live_total} live artifacts")

    generate_readme(total, live_total)
    grand = total + live_total
    print(f"Wrote {grand} artifacts + README to {OUT}/")


if __name__ == "__main__":
    main()
