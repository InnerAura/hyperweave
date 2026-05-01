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
    Regime,
)
from hyperweave.core.models import ComposeSpec

OUT = Path(__file__).resolve().parent.parent / "outputs"


def _genome_motions(genome_id: str) -> list[str]:
    """Return border motions compatible with a genome.

    Intersects the genome's ``compatible_motions`` list from its JSON
    config with the BorderMotionId enum set. Only motions that the
    genome has been tested with are returned. Kinetic typography
    motions were removed in v0.2.14 with the banner frame.
    """
    genomes = load_genomes()
    genome_cfg = genomes.get(genome_id)
    compatible: set[str] = set(genome_cfg.compatible_motions) if genome_cfg else {"static"}
    return [m for m in BorderMotionId if m.value in compatible]


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
    {"provider": "pypi", "id": "readmeai", "metric": "downloads", "frame": "badge", "title": "DOWNLOADS"},
    {"provider": "docker", "id": "zeroxeli/readme-ai", "metric": "pull_count", "frame": "badge", "title": "PULLS"},
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
    family: str = "",
    telemetry_data: dict[str, Any] | None = None,
    connector_data: dict[str, Any] | None = None,
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
        family=family,
        telemetry_data=telemetry_data,
        connector_data=connector_data,
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

        # Strip subtitle — resolver reads connector_data.repo_slug to render
        # the grayish "eli64s/readme-ai" under the identity line (cellular
        # paradigm opts in via strip.show_subtitle=true). Proof-set calls
        # that omit connector_data get an empty subtitle zone, which is
        # correct for paradigms that don't opt in.
        svg = _compose(
            "strip",
            genome,
            "readme-ai",
            "STARS:12.4k,FORKS:1.2k,VERSION:v0.6.9",
            "active",
            "github",
            connector_data={"repo_slug": "eli64s/readme-ai"},
        )
        _write(base / "strip.svg", svg)
        total += 1

        svg = _compose("icon", genome, glyph="github")
        _write(base / "icon.svg", svg)
        total += 1

        for dv in DividerVariant:
            # cellular-dissolve is automata-only; the other 5 variants
            # (block/current/takeoff/void/zeropoint) are generic inneraura-
            # namespace dividers shared across all genomes.
            if dv == DividerVariant.CELLULAR_DISSOLVE and genome != GenomeId.AUTOMATA:
                continue
            svg = _compose("divider", genome, divider_variant=dv)
            _write(base / f"divider_{dv}.svg", svg)
            total += 1

        # marquee-horizontal — pipe-separated items split into discrete tokens.
        # Cellular paradigm cycles colors per-item from its tspan palette
        # (teal/amethyst alternation); brutalist/chrome render as single-color runs.
        # Counter / vertical marquees were deleted in v0.2.14.
        marquee_text = "HYPERWEAVE|CELLULAR-AUTOMATA|LIVING ARTIFACTS|AGENT-READABLE|COMPOSITIONAL"
        svg = _compose("marquee-horizontal", genome, marquee_text)
        _write(base / "marquee_horizontal.svg", svg)
        total += 1

        # ── 1b. Automata-specific family-axis coverage (blue/purple x default/compact) ──
        if genome == GenomeId.AUTOMATA:
            fam_dir = gdir / "families"
            for fam in ("blue", "purple"):
                svg = _compose("badge", genome, "PYPI", "v0.2.5", "active", "python", family=fam)
                _write(fam_dir / f"badge_pypi_{fam}_default.svg", svg)
                total += 1
                svg = _compose("badge", genome, "PYPI", "v0.2.5", "active", "python", family=fam, variant="compact")
                _write(fam_dir / f"badge_pypi_{fam}_compact.svg", svg)
                total += 1
                svg = _compose("icon", genome, glyph="github", family=fam)
                _write(fam_dir / f"icon_github_{fam}.svg", svg)
                total += 1
            # Bifamily strip + cellular-dissolve divider
            svg = _compose(
                "strip",
                genome,
                "readme-ai",
                "STARS:12.4k,VERSION:v0.6.9,BUILD:passing",
                "passing",
                "github",
                family="bifamily",
                connector_data={"repo_slug": "eli64s/readme-ai"},
            )
            _write(fam_dir / "strip_bifamily.svg", svg)
            total += 1
            svg = _compose("divider", genome, divider_variant="cellular-dissolve")
            _write(fam_dir / "divider_cellular_dissolve.svg", svg)
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
                connector_data={"repo_slug": "eli64s/readme-ai"},
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
        compat_border = _genome_motions(genome)
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
                connector_data={"repo_slug": "eli64s/readme-ai"},
            )
            _write(border / f"strip_{mid}.svg", svg)
            total += 1

        # ── 7. Kinetic typography removed in v0.2.14 with the banner frame ──

    # ── 8. Telemetry frames (genome-independent, generated once) ──
    telemetry_dir = OUT / "proofset" / "telemetry"
    for ftype in (FrameType.RECEIPT, FrameType.RHYTHM_STRIP, FrameType.MASTER_CARD):
        svg = _compose(ftype, GenomeId.BRUTALIST_EMERALD, telemetry_data=MOCK_TELEMETRY)
        _write(telemetry_dir / f"{ftype.value.replace('-', '_')}.svg", svg)
        total += 1

    # ── 9. Stats / chart frames ──
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


def _compose_connector(
    frame_type: str,
    genome: str,
    *,
    connector_data: dict[str, Any] | None = None,
    stats_username: str = "",
    chart_owner: str = "",
    chart_repo: str = "",
    genome_override: dict[str, Any] | None = None,
) -> str:
    """Compose a stats/chart frame with pre-fetched connector data."""
    spec = ComposeSpec(
        type=frame_type,
        genome_id=genome,
        connector_data=connector_data,
        stats_username=stats_username,
        chart_owner=chart_owner,
        chart_repo=chart_repo,
        genome_override=genome_override,
    )
    return compose(spec).svg


def _generate_session_2a2b() -> int:
    """Generate stats and chart artifacts for each built-in genome.

    Fetches real data from GitHub for eli64s / eli64s/readme-ai. Falls back to
    mock connector data if the API is unreachable (CI/offline environments).
    Timeline removed in v0.2.14; the function name is preserved for git-history
    continuity.
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
                # For github-scoped live specs, spec["id"] is already "owner/repo" —
                # pass through as repo_slug so cellular subtitle renders correctly.
                _conn: dict[str, Any] = {"repo_slug": spec["id"]} if spec["provider"] == "github" else {}
                svg = _compose(
                    "strip",
                    genome,
                    spec["title"],
                    desc,
                    "active",
                    connector_data=_conn or None,
                )
                _write(live_dir / f"{spec['provider']}_{spec['id'].replace('/', '_')}_strip.svg", svg)
                total += 1
        except Exception as e:
            print(f"  SKIP {spec['provider']}/{spec['id']}: {e}")

    # ── Connector-strip adaptivity proof ──
    # Renders the SAME repo identity across three providers (GitHub, PyPI,
    # DockerHub) per genome, exercising strip construction against varied
    # metric counts (2 vs 3), value lengths (short '23', medium '12.4k',
    # long 'v0.6.9'), and provider-specific label vocabularies. Stale
    # sub-fetches surface as em-dash via _format_count's None sentinel.
    total += await _generate_connector_strips(live_dir.parent)
    # ── Multi-provider data-token marquee ──
    # Demonstrates the unified ?data= grammar mixing three providers in one
    # marquee URL. Renders across all three genomes so each paradigm's
    # treatment of the kv-pair scroll items is visible side-by-side.
    total += await _generate_multi_provider_marquee(live_dir.parent)
    return total


# ── Multi-provider data-token marquee ──


async def _generate_multi_provider_marquee(proofset_root: Path) -> int:
    """Compose a single marquee URL fanning out across GitHub + PyPI + Docker.

    Resolves five tokens from three providers via the unified ``?data=``
    grammar, then composes ``marquee-horizontal`` for each of the three
    genomes. The same resolved token list flows into all three composes —
    only the genome (and its paradigm-specific styling) differs. This
    isolates the genome-vs-data axis: same data, three skins.
    """
    from hyperweave.serve.data_tokens import parse_data_tokens, resolve_data_tokens

    # Docker Hub's connector exposes `pull_count` (matching the upstream JSON
    # field exactly), not `pulls`. The five tokens cross three providers:
    # GitHub (stars + forks), PyPI (version + downloads), Docker (pull_count).
    data_string = (
        "gh:eli64s/readme-ai.stars,"
        "gh:eli64s/readme-ai.forks,"
        "pypi:readmeai.version,"
        "pypi:readmeai.downloads,"
        "docker:zeroxeli/readme-ai.pull_count"
    )

    try:
        tokens = parse_data_tokens(data_string)
        resolved, _ttl = await resolve_data_tokens(tokens)
    except Exception as exc:
        print(f"  multi-provider marquee resolve failed: {exc}")
        return 0

    total = 0
    for genome in GenomeId:
        spec = ComposeSpec(
            type="marquee-horizontal",
            genome_id=genome,
            family="bifamily" if genome == GenomeId.AUTOMATA else "",
            data_tokens=list(resolved),
        )
        try:
            svg = compose(spec).svg
        except Exception as exc:
            print(f"  multi-provider marquee compose failed for {genome}: {exc}")
            continue
        _write(proofset_root / genome / "live-data" / "marquee_multi_provider.svg", svg)
        total += 1
    return total


# ── Connector strip adaptivity proof ──


_CONNECTOR_STRIP_PROVIDERS: list[dict[str, Any]] = [
    {
        "provider": "github",
        "ident": "eli64s/readme-ai",
        "title": "readme-ai",
        "glyph": "github",
        "subtitle": "eli64s/readme-ai",
        "metrics": [("STARS", "stars"), ("FORKS", "forks"), ("ISSUES", "issues")],
        "filename_stem": "github_eli64s_readme-ai",
    },
    {
        "provider": "pypi",
        "ident": "readmeai",
        "title": "readmeai",
        "glyph": "pypi",
        "subtitle": "pypi.org/project/readmeai",
        "metrics": [("VERSION", "version"), ("DOWNLOADS", "downloads")],
        "filename_stem": "pypi_readmeai",
    },
    {
        "provider": "docker",
        "ident": "zeroxeli/readme-ai",
        "title": "readme-ai",
        "glyph": "docker",
        "subtitle": "zeroxeli/readme-ai",
        "metrics": [("PULLS", "pull_count"), ("STARS", "star_count")],
        "filename_stem": "docker_zeroxeli_readme-ai",
    },
    # Multi-connector stress test — 5 metrics aggregated from GitHub +
    # PyPI + Docker. Stresses per-cell adaptive width logic against the
    # widest plausible label ("DOWNLOADS", 9 chars) and a heterogeneous
    # value vocabulary (count, version-string, K-cascade). Sources are
    # listed as ``(provider, ident, label, metric_key)`` tuples.
    {
        "provider": "multi",
        "ident": "eli64s/readme-ai",
        "title": "readme-ai",
        "glyph": "github",
        "subtitle": "eli64s/readme-ai",
        "metric_sources": [
            ("github", "eli64s/readme-ai", "STARS", "stars"),
            ("github", "eli64s/readme-ai", "FORKS", "forks"),
            ("pypi", "readmeai", "VERSION", "version"),
            ("pypi", "readmeai", "DOWNLOADS", "downloads"),
            ("docker", "zeroxeli/readme-ai", "PULLS", "pull_count"),
        ],
        "filename_stem": "multi_readme-ai_5metric",
    },
]


async def _generate_connector_strips(proofset_root: Path) -> int:
    """Fetch real connector data and render adaptivity-proof strips per genome.

    For each provider in _CONNECTOR_STRIP_PROVIDERS, fetch the configured
    metrics in parallel, format them via _format_count, and render one strip
    per genome. Failed sub-fetches become "—" so partial failure doesn't
    suppress the whole strip.
    """
    from hyperweave.compose.resolvers.stats import _format_count
    from hyperweave.connectors import fetch_metric

    async def _safe_fetch_value(provider: str, ident: str, metric: str) -> Any:
        try:
            data = await fetch_metric(provider, ident, metric)
            return data.get("value")
        except Exception as exc:
            print(f"  SKIP connector strip metric {provider}:{ident}:{metric} ({exc})")
            return None

    # Build resolved specs (one network round-trip per metric per provider).
    # Comma is the metric-list separator in spec.value (`STARS:12k,FORKS:5k`),
    # so values themselves must NOT contain commas. _format_count emits
    # comma-grouped digits for n < 10K (e.g. "2,896"); we strip those commas
    # so the parser doesn't fragment "2,896" into a phantom metric.
    def _format_metric_value(raw: Any, metric_key: str) -> str:
        if metric_key == "version":
            return str(raw) if raw else "—"
        formatted = _format_count(raw if isinstance(raw, int) else None)
        return formatted.replace(",", "")

    resolved: list[dict[str, Any]] = []
    for spec in _CONNECTOR_STRIP_PROVIDERS:
        metric_entries: list[dict[str, str]] = []
        if "metric_sources" in spec:
            # Multi-connector spec: each metric pulls from its own provider.
            for src_provider, src_ident, label, metric_key in spec["metric_sources"]:
                raw = await _safe_fetch_value(src_provider, src_ident, metric_key)
                metric_entries.append({"label": label, "value": _format_metric_value(raw, metric_key)})
        else:
            for label, metric_key in spec["metrics"]:
                raw = await _safe_fetch_value(spec["provider"], spec["ident"], metric_key)
                metric_entries.append({"label": label, "value": _format_metric_value(raw, metric_key)})
        resolved.append({**spec, "metric_entries": metric_entries})

    total = 0
    for genome in GenomeId:
        gdir = proofset_root / genome / "connectors"
        for spec in resolved:
            metrics_str = ",".join(f"{m['label']}:{m['value']}" for m in spec["metric_entries"])
            svg = _compose(
                "strip",
                genome,
                spec["title"],
                metrics_str,
                "active",
                spec["glyph"],
                connector_data={"repo_slug": spec["subtitle"]},
            )
            _write(gdir / f"{spec['filename_stem']}.svg", svg)
            total += 1
    return total


def _connector_strip_filenames() -> list[str]:
    """Return the per-provider strip filename stems for README inlining."""
    return [spec["filename_stem"] for spec in _CONNECTOR_STRIP_PROVIDERS]


def generate_readme(total: int, live_total: int) -> None:
    """Generate outputs/README.md with image references.

    Each genome gets its complete artifact suite inline — base frames,
    states, stats, chart, motions, and (for automata) the family-axis
    coverage. Telemetry lives at the bottom (genome-independent).
    """
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
        lines.append(f"![icon](proofset/{g}/base/icon.svg)")
        lines.append("")
        for dv in DividerVariant:
            # cellular-dissolve only renders for automata (mirror the guard
            # in generate_static); skip the broken image link in other genomes.
            if dv == DividerVariant.CELLULAR_DISSOLVE and genome != GenomeId.AUTOMATA:
                continue
            lines.append(f"![divider {dv}](proofset/{g}/base/divider_{dv}.svg)")
            lines.append("")
        lines.append(f"![marquee_horizontal (custom text)](proofset/{g}/base/marquee_horizontal.svg)")
        lines.append("")
        # Data-token marquee inline next to its custom-text sibling — same
        # frame, same paradigm dispatch, different input mode (live `?data=`
        # tokens vs raw pipe-split text). Only present when --live was run.
        multi_path = OUT / "proofset" / g / "live-data" / "marquee_multi_provider.svg"
        if multi_path.exists():
            lines.append(
                f"![marquee_horizontal (multi-provider data)](proofset/{g}/live-data/marquee_multi_provider.svg)"
            )
            lines.append("")
            lines.append(
                "<sub><code>?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,"
                "pypi:readmeai.version,pypi:readmeai.downloads,docker:zeroxeli/readme-ai.pull_count</code></sub>"
            )
            lines.append("")

        # Connector-strip adaptivity (only present when --live was run; the
        # files live alongside per-genome dirs so the section is genome-local).
        connector_dir = OUT / "proofset" / g / "connectors"
        if connector_dir.exists() and any(connector_dir.iterdir()):
            lines.extend(["### Connector Adaptivity (live)", ""])
            lines.append(
                "Real-data strips for the same project across three providers — "
                "exercising varied metric counts, value lengths, and label "
                "vocabularies through a single strip resolver."
            )
            lines.append("")
            for stem in _connector_strip_filenames():
                lines.append(f"![{stem}](proofset/{g}/connectors/{stem}.svg)")
                lines.append("")

        # Automata-specific family axis (blue/purple x default/compact)
        if genome == GenomeId.AUTOMATA:
            lines.extend(["### Family Axis (blue / purple x default / compact)", ""])
            lines.append(
                "Automata's bifamily chromatic axis: badges + icons pick "
                "`--family blue|purple`; strip/marquee-horizontal/divider render both simultaneously."
            )
            lines.append("")
            for fam in ("blue", "purple"):
                lines.append(f"**Family: `{fam}`**")
                lines.append("")
                lines.append(f"![badge pypi {fam} default](proofset/{g}/families/badge_pypi_{fam}_default.svg) ")
                lines.append(f"![badge pypi {fam} compact](proofset/{g}/families/badge_pypi_{fam}_compact.svg)")
                lines.append("")
                lines.append(f"![icon github {fam}](proofset/{g}/families/icon_github_{fam}.svg)")
                lines.append("")
            lines.append("**Bifamily compositions:**")
            lines.append("")
            lines.append(f"![strip bifamily](proofset/{g}/families/strip_bifamily.svg)")
            lines.append("")
            lines.append(f"![divider cellular-dissolve](proofset/{g}/families/divider_cellular_dissolve.svg)")
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

        # Stats card + Star chart inline per genome
        lines.extend(["### Profile Card (stats)", ""])
        lines.append(f"![stats {g}](proofset/{g}/session-2a2b/stats.svg)")
        lines.append("")

        lines.extend(["### Star History Chart", ""])
        lines.append(f"![chart full {g}](proofset/{g}/session-2a2b/chart_stars_full.svg)")
        lines.append("")

        # Policy lanes
        lines.extend(["### Policy Lanes", ""])
        for r in (Regime.NORMAL, Regime.UNGOVERNED):
            lines.append(f"![badge {r}](proofset/{g}/policy-lanes/badge_{r}.svg)")
        lines.append("")

        # Border motions (genome-compatible only)
        compat_border = _genome_motions(g)
        lines.extend(["### Border Motions", ""])
        for mid in compat_border:
            lines.append(f"![badge {mid}](proofset/{g}/border-motions/badge_{mid}.svg) ")
            lines.append(f"![strip {mid}](proofset/{g}/border-motions/strip_{mid}.svg)")
            lines.append("")

        # Kinetic typography removed in v0.2.14 with the banner frame.

        lines.extend(["---", ""])

    # Telemetry (genome-independent, bottom of page)
    lines.extend(["## Telemetry", ""])
    lines.append("*Telemetry frames use their own built-in palette (no genome skinning).*")
    lines.append("")
    for ft in (FrameType.RECEIPT, FrameType.RHYTHM_STRIP, FrameType.MASTER_CARD):
        lines.append(f"![{ft}](proofset/telemetry/{ft.value.replace('-', '_')}.svg)")
        lines.append("")

    if live_total > 0:
        lines.extend(["## Live Data (requires --live)", ""])
        lines.append(
            "*Live artifacts render inline per-genome above: connector-strip adaptivity in each genome's "
            "`### Connector Adaptivity (live)` subsection, and the multi-provider data-token marquee "
            "(`?data=gh:...stars,gh:...forks,pypi:...version,pypi:...downloads,docker:...pull_count`) "
            "next to the custom-text marquee in each `### Base Frames` block. Source files live under "
            "`proofset/{genome}/live-data/`.*"
        )
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
