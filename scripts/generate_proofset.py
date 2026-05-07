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

# ── Real-transcript visual fidelity corpus (v0.2.21) ──
# Five transcripts spanning a range of sizes from the user's local Claude Code
# project history. Paths are user-machine-only (NOT committed). Falls back to
# MOCK_TELEMETRY when absent — keeps CI / clean-environment runs reproducible.
# xlarge + xxlarge stress-test bar count, tier-3 overflow, and label collision.
_REAL_TRANSCRIPTS: list[tuple[str, Path]] = [
    (
        "small",
        Path.home()
        / ".claude"
        / "projects"
        / "-Users-k01101011-Projects-GitHub-eli64s"
        / "d6ceeb70-599b-4c10-b827-ee267f0701dc.jsonl",
    ),
    (
        "medium",
        Path.home()
        / ".claude"
        / "projects"
        / "-Users-k01101011-Projects-InnerAura-hyperweave"
        / "b8e704a6-fb10-4887-b80d-86bd82d0eced.jsonl",
    ),
    (
        "large",
        Path.home()
        / ".claude"
        / "projects"
        / "-Users-k01101011-Projects-InnerAura-hyperweave--claude-worktrees-gracious-swirles-93af5c"
        / "4f7565a5-da44-4fbb-9234-b6f9cb2a1be6.jsonl",
    ),
    (
        "xlarge",
        Path.home()
        / ".claude"
        / "projects"
        / "-Users-k01101011-Projects-InnerAura-hyperweave"
        / "398ce70f-2632-4c61-9eee-659f3e5df19a.jsonl",
    ),
    (
        "xxlarge",
        Path.home()
        / ".claude"
        / "projects"
        / "-Users-k01101011-Projects-InnerAura-hyperweave"
        / "e313bc93-4f66-431b-b134-4c17d0af8d23.jsonl",
    ),
]


# ── Real-codex-transcript corpus (v0.2.23) ──
# Codex sessions live at ``~/.codex/sessions/YYYY/MM/DD/rollout-TIMESTAMP-UUID.jsonl``.
# Same pattern as ``_REAL_TRANSCRIPTS`` above: user-machine-only paths with
# graceful fallback when missing. Two sizes give the proofset both a sparse
# (web_search-heavy) and dense (apply_patch-heavy) codex receipt.
_REAL_CODEX_TRANSCRIPTS: list[tuple[str, Path]] = [
    (
        "codex-small",
        Path.home()
        / ".codex"
        / "sessions"
        / "2026"
        / "05"
        / "03"
        / "rollout-2026-05-03T19-16-03-019df057-8ee2-7543-974a-b0bb0bf3567d.jsonl",
    ),
    (
        "codex-large",
        Path.home()
        / ".codex"
        / "sessions"
        / "2026"
        / "04"
        / "30"
        / "rollout-2026-04-30T09-51-02-019ddedf-318a-7192-b29b-c0eab28e2308.jsonl",
    ),
]


def _load_real_telemetry(path: Path) -> dict[str, Any] | None:
    """Build a contract from a JSONL transcript, or return None if missing.

    The script ships paths to user-local Claude Code transcripts; on machines
    without those exact paths (CI, fresh checkout), this returns None and the
    caller should fall back to MOCK_TELEMETRY.
    """
    if not path.exists():
        return None
    from hyperweave.telemetry.contract import build_contract

    return build_contract(str(path))


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
    size: str = "default",
    variant: str = "",
    shape: str = "",
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
        size=size,
        variant=variant,
        shape=shape,
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

        # Icons: chrome/brutalist support both shapes (per v0.2.16 paradigms);
        # render only the explicit-shape pair to avoid duplicating the
        # paradigm default. Other genomes keep their single paradigm-default icon.
        if genome in (GenomeId.CHROME, GenomeId.BRUTALIST):
            svg = _compose("icon", genome, glyph="github", shape="circle")
            _write(base / "icon_circle.svg", svg)
            total += 1
            svg = _compose("icon", genome, glyph="github", shape="square")
            _write(base / "icon_square.svg", svg)
            total += 1
        else:
            svg = _compose("icon", genome, glyph="github")
            _write(base / "icon.svg", svg)
            total += 1

        # v0.2.19 divider proof set: only the genome's declared divider(s) render
        # at /v1/divider/. Editorial generics (block/current/takeoff/void/zeropoint)
        # are no longer per-genome — see the dedicated /a/inneraura/dividers/
        # generation block at the bottom of generate_static().
        from hyperweave.config.loader import load_genomes

        genome_cfg = load_genomes().get(genome)
        for slug in genome_cfg.dividers if genome_cfg else []:
            svg = _compose("divider", genome, divider_variant=slug)
            _write(base / f"divider_{slug}.svg", svg)
            total += 1

        # marquee-horizontal — pipe-separated items split into discrete tokens.
        # v0.2.16: paradigm-driven dimensions (chrome 1040x56, brutalist 720x32,
        # cellular 800x40), text-fill mode (chrome=gradient, brutalist=cycle,
        # cellular=bifamily palette), and separator kind (chrome=glyph,
        # brutalist=rect, cellular=glyph). Marquee text per genome matches its
        # paradigm voice.
        marquee_text_by_genome: dict[str, str] = {
            GenomeId.CHROME: "HYPERWEAVE|CHROME HORIZON|LIVING SVG ARTIFACTS|v0.2.16",
            GenomeId.BRUTALIST: "LIVING ARTIFACTS|SELF-CONTAINED SVG|AGENT INTERFACES",
            GenomeId.AUTOMATA: "HYPERWEAVE|CELLULAR-AUTOMATA|LIVING ARTIFACTS|AGENT-READABLE|COMPOSITIONAL",
        }
        marquee_text = marquee_text_by_genome.get(genome, "HYPERWEAVE|LIVING ARTIFACTS|v0.2.16")
        svg = _compose("marquee-horizontal", genome, marquee_text)
        _write(base / "marquee_horizontal.svg", svg)
        total += 1

        # ── 1b. Automata-specific family-axis coverage (blue/purple x default/compact) ──
        if genome == GenomeId.AUTOMATA:
            var_dir = gdir / "variants"
            for fam in ("blue", "purple"):
                svg = _compose("badge", genome, "PYPI", "v0.2.5", "active", "python", variant=fam)
                _write(var_dir / f"badge_pypi_{fam}_default.svg", svg)
                total += 1
                svg = _compose("badge", genome, "PYPI", "v0.2.5", "active", "python", variant=fam, size="compact")
                _write(var_dir / f"badge_pypi_{fam}_compact.svg", svg)
                total += 1
                svg = _compose("icon", genome, glyph="github", variant=fam)
                _write(var_dir / f"icon_github_{fam}.svg", svg)
                total += 1
            # Bifamily strip + dissolve divider
            svg = _compose(
                "strip",
                genome,
                "readme-ai",
                "STARS:12.4k,VERSION:v0.6.9,BUILD:passing",
                "passing",
                "github",
                variant="bifamily",
                connector_data={"repo_slug": "eli64s/readme-ai"},
            )
            _write(var_dir / "strip_bifamily.svg", svg)
            total += 1
            svg = _compose("divider", genome, divider_variant="dissolve")
            _write(var_dir / "divider_dissolve.svg", svg)
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

    # ── 8. Telemetry frames — visual fidelity matrix (v0.2.21) ──
    # Receipts and rhythm-strips render against 3 real session transcripts of
    # varying size (small / medium / large) when the user has them locally,
    # plus a baseline mock-data render. Each (skin x transcript x frame) tuple
    # produces one SVG. Real transcripts are user-local; on machines without
    # them, the matrix gracefully falls back to mock-only.
    telemetry_dir = OUT / "proofset" / "telemetry"

    # Available transcripts: always include "mock"; add each real transcript
    # only when its path exists. Mock data has no inherent runtime so it
    # renders under all four skins (chrome demonstration on a neutral base).
    # Real transcripts render only under (a) their runtime's matched skin and
    # (b) telemetry-voltage as the universal fallback — cross-skin renders
    # (codex data in cream skin, claude data in codex skin, etc.) produce
    # noise rather than signal.
    transcript_corpus: list[tuple[str, dict[str, Any]]] = [("mock", MOCK_TELEMETRY)]
    for label, transcript_path in _REAL_TRANSCRIPTS:
        contract = _load_real_telemetry(transcript_path)
        if contract is not None:
            transcript_corpus.append((label, contract))
    for label, transcript_path in _REAL_CODEX_TRANSCRIPTS:
        contract = _load_real_telemetry(transcript_path)
        if contract is not None:
            transcript_corpus.append((label, contract))

    # ── Skin matrix per transcript ──
    # Mock: all 4 skins (chrome showcase). Real transcript: matched-runtime skin
    # + telemetry-voltage. Matched skin is sourced from the runtime registry
    # (no string-literal coupling) — see telemetry.runtimes.get_runtime.
    from hyperweave.telemetry.runtimes import get_runtime

    all_skins = ("telemetry-voltage", "telemetry-claude-code", "telemetry-cream", "telemetry-codex")

    def _skins_for(label: str, telemetry: dict[str, Any]) -> tuple[str, ...]:
        if label == "mock":
            return all_skins
        runtime = telemetry.get("session", {}).get("runtime", "")
        if not runtime:
            return ("telemetry-voltage",)
        try:
            matched = get_runtime(runtime).genome
        except KeyError:
            return ("telemetry-voltage",)
        if matched == "telemetry-voltage":
            return (matched,)
        return (matched, "telemetry-voltage")

    for label, telemetry in transcript_corpus:
        for skin in _skins_for(label, telemetry):
            for ftype in (FrameType.RECEIPT, FrameType.RHYTHM_STRIP):
                svg = _compose(ftype, skin, telemetry_data=telemetry)
                filename = f"{ftype.value.replace('-', '_')}_{skin}_{label}.svg"
                _write(telemetry_dir / filename, svg)
                total += 1

    # Master-card single voltage variant (multi-skin master-card deferred to pre-v0.3.0).
    svg = _compose(FrameType.MASTER_CARD, "telemetry-voltage", telemetry_data=MOCK_TELEMETRY)
    _write(telemetry_dir / "master_card.svg", svg)
    total += 1

    # ── 9. Genome-agnostic dividers (live at /a/inneraura/dividers/, generated once) ──
    # Render via compose() with a default genome — the templates hardcode their
    # own colors and ignore the genome dict by design.
    inneraura_dir = OUT / "proofset" / "inneraura" / "dividers"
    for slug in ("block", "current", "takeoff", "void", "zeropoint"):
        svg = _compose("divider", GenomeId.BRUTALIST, divider_variant=slug)
        _write(inneraura_dir / f"{slug}.svg", svg)
        total += 1

    # ── 10. Stats / chart frames ──
    total += _generate_data_cards()

    return total


# ── Data cards (stats + chart) proof set generation ─────────────────────────────────────


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

# Note: a previous _MOCK_CHART_POINTS constant lived here. Removed in
# v0.2.16-fix3 — chart artifacts now SKIP entirely on data fetch failure
# rather than substitute fake history. A missing chart is honest; a
# plausible-looking fake curve presented as real data is not.


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


def _generate_data_cards() -> int:
    """Generate stats and chart artifacts for each built-in genome.

    Fetches real data from GitHub for eli64s / eli64s/readme-ai. Falls back to
    mock connector data if the API is unreachable (CI/offline environments).
    Timeline removed in v0.2.14; the function name is preserved for git-history
    continuity.
    """
    import asyncio

    stats_data: dict[str, Any] | None = None
    chart_data: dict[str, Any] | None = None

    # Fetch real data from GitHub. Both fetches share a single asyncio.run() —
    # the httpx singleton client binds to the loop on first use, so a second
    # asyncio.run() finds it bound to a closed loop ("Event loop is closed").
    from hyperweave.connectors.base import close_client
    from hyperweave.connectors.github import fetch_stargazer_history, fetch_user_stats

    async def _fetch_both() -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None, str | None]:
        s_err: str | None = None
        c_err: str | None = None
        s_data: dict[str, Any] | None = None
        c_data: dict[str, Any] | None = None
        try:
            s_data = await fetch_user_stats("eli64s")
        except Exception as exc:
            s_err = str(exc)
        try:
            c_data = await fetch_stargazer_history("eli64s", "readme-ai")
        except Exception as exc:
            c_err = str(exc)
        await close_client()
        return s_data, c_data, s_err, c_err

    stats_data, chart_data, _s_err, _c_err = asyncio.run(_fetch_both())
    print("  fetched real stats for eli64s" if stats_data else f"  stats fetch failed ({_s_err}), using mock data")
    print("  fetched real star history for eli64s/readme-ai" if chart_data else f"  chart fetch failed ({_c_err})")

    # Stats fallback: stats card has many cells, mock data keeps the showcase
    # rendering even when GitHub is unreachable. The mock here is documented
    # demo content for the proofset's structural showcase, not a substitute
    # for real numbers we're claiming are real.
    if not stats_data:
        stats_data = dict(_MOCK_STATS_DATA)

    # Chart fallback: NEVER substitute mock history for failed real data —
    # a fake curve presented as real is the kind of dishonesty we refuse to
    # ship. If the fetch failed (exception OR cross-check disagreement), we
    # SKIP the chart artifact entirely. README image links break loudly,
    # which is the right signal.
    chart_skipped = False
    if not chart_data:
        print("  ERROR: chart fetch returned no data — SKIPPING chart artifact")
        chart_skipped = True

    # Cross-reference: if repos endpoint was rate-limited, stars_total may be 0.
    # Supplement from chart connector's current_stars (fetched via repo metadata).
    if not chart_skipped and chart_data is not None and stats_data.get("stars_total", 0) == 0:
        chart_current = chart_data.get("current_stars")
        if chart_current:
            stats_data = dict(stats_data)
            stats_data["stars_total"] = chart_current
            print(f"  patched stars_total from chart data: {chart_current}")

    # Cross-check sanity guard: the chart connector now does its own GraphQL/
    # REST cross-check internally (v0.2.16-fix3, see fetch_stargazer_history)
    # and returns an empty-state response when total_stars sources disagree.
    # We add a second-level cross-check here against fetch_user_stats's
    # stars_total (which uses an entirely different code path) for defense
    # in depth. If they STILL disagree after retry, we SKIP the chart entirely
    # rather than ship a misleading proofset artifact — a missing chart is
    # honest (the README image link will be broken loudly), a fake chart is
    # the kind of dishonesty we refuse to ship. NEVER substitute mock data
    # for real data, no matter how plausible it would look.
    chart_stars = int(chart_data.get("current_stars") or 0) if chart_data else 0
    user_stars = int(stats_data.get("stars_total") or 0)
    if chart_stars > 0 and user_stars > 0:
        ratio = max(chart_stars, user_stars) / min(chart_stars, user_stars)
        if ratio > 2.0:
            print(
                f"  WARN: chart current_stars={chart_stars} disagrees with "
                f"stats stars_total={user_stars} by {ratio:.1f}x. Retrying chart fetch..."
            )
            try:
                from hyperweave.connectors.cache import get_cache

                # Drop the cached bad result before retrying.
                get_cache().clear()

                async def _retry() -> dict[str, Any]:
                    result = await fetch_stargazer_history("eli64s", "readme-ai")
                    await close_client()
                    return result

                chart_data = asyncio.run(_retry())
                chart_stars = int(chart_data.get("current_stars") or 0)
                ratio = max(chart_stars, user_stars) / max(min(chart_stars, user_stars), 1)
                print(f"  retry returned current_stars={chart_stars} (now {ratio:.1f}x)")
                if ratio > 2.0:
                    print(
                        "  ERROR: retry STILL disagrees with stats. SKIPPING chart artifact "
                        "rather than ship a misleading proofset. README image links for "
                        "chart_stars_full.svg will be broken — that's intentional."
                    )
                    chart_skipped = True
            except Exception as exc:
                print(
                    f"  ERROR: retry failed ({exc}). SKIPPING chart artifact rather than "
                    "ship one with stale/uncertain data."
                )
                chart_skipped = True

    total = 0

    for genome in GenomeId:
        gdir = OUT / "proofset" / genome / "data-cards"

        # Stats card — paradigm comes from genome.paradigms.stats
        svg = _compose_connector(
            "stats",
            genome,
            stats_username="eli64s",
            connector_data=stats_data,
        )
        _write(gdir / "stats.svg", svg)
        total += 1

        # Star chart — single full size (900x500). Skipped entirely when
        # cross-check failed; a missing artifact is honest (README link breaks
        # loudly) — a fake artifact would be dishonest.
        if chart_skipped:
            continue

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
            genome = GenomeId.BRUTALIST

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
            variant="bifamily" if genome == GenomeId.AUTOMATA else "",
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
        # Icons: chrome/brutalist render explicit shape pair only; other
        # genomes render their single paradigm-default icon.
        if genome in (GenomeId.CHROME, GenomeId.BRUTALIST):
            lines.append(f"![icon circle](proofset/{g}/base/icon_circle.svg)")
            lines.append("")
            lines.append(f"![icon square](proofset/{g}/base/icon_square.svg)")
            lines.append("")
        else:
            lines.append(f"![icon](proofset/{g}/base/icon.svg)")
            lines.append("")
        # Per-genome dividers: only the genome's declared dividers render
        # at /v1/divider/{slug}/{genome}.{motion}. Genome-agnostic dividers
        # (block/current/takeoff/void/zeropoint) live at /a/inneraura/dividers/
        # and are listed in their own section at the bottom of this README.
        from hyperweave.config.loader import load_genomes

        _genome_cfg = load_genomes().get(genome)
        for slug in _genome_cfg.dividers if _genome_cfg else []:
            lines.append(f"![divider {slug}](proofset/{g}/base/divider_{slug}.svg)")
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

        # Automata-specific variant axis (blue/purple/bifamily x default/compact)
        if genome == GenomeId.AUTOMATA:
            lines.extend(["### Variant Axis (blue / purple / bifamily)", ""])
            lines.append(
                "Automata's chromatic variant axis: badges + icons pick "
                "`?variant=blue|purple`; strip/marquee-horizontal/divider render bifamily."
            )
            lines.append("")
            for v in ("blue", "purple"):
                lines.append(f"**Variant: `{v}`**")
                lines.append("")
                lines.append(f"![badge pypi {v} default](proofset/{g}/variants/badge_pypi_{v}_default.svg) ")
                lines.append(f"![badge pypi {v} compact](proofset/{g}/variants/badge_pypi_{v}_compact.svg)")
                lines.append("")
                lines.append(f"![icon github {v}](proofset/{g}/variants/icon_github_{v}.svg)")
                lines.append("")
            lines.append("**Bifamily compositions:**")
            lines.append("")
            lines.append(f"![strip bifamily](proofset/{g}/variants/strip_bifamily.svg)")
            lines.append("")
            lines.append(f"![divider dissolve](proofset/{g}/variants/divider_dissolve.svg)")
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
        lines.append(f"![stats {g}](proofset/{g}/data-cards/stats.svg)")
        lines.append("")

        lines.extend(["### Star History Chart", ""])
        lines.append(f"![chart full {g}](proofset/{g}/data-cards/chart_stars_full.svg)")
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

    # Genome-agnostic dividers (live at /a/inneraura/dividers/, generated once)
    lines.extend(["## `/a/inneraura/dividers/`", ""])
    for slug in ("block", "current", "takeoff", "void", "zeropoint"):
        lines.append(f"![divider {slug}](proofset/inneraura/dividers/{slug}.svg)")
        lines.append("")

    # Telemetry visual-fidelity matrix (v0.2.23): runtime-paired skins.
    # Each transcript renders only under its matched-runtime skin + voltage
    # (the universal fallback). Mock data renders under all 4 skins for chrome
    # demonstration on a neutral baseline. Cross-runtime renders (codex data
    # in cream skin, claude-code data in codex skin) are NOT generated —
    # they're noise rather than signal.
    lines.extend(["## Telemetry", ""])
    lines.append(
        "*Each real transcript renders against its matched-runtime skin plus telemetry-voltage "
        "(the universal fallback). Mock data demonstrates all 4 skin chromes on a neutral baseline. "
        "Skin precedence chain: explicit `--genome` override → JSONL `runtime` field → `telemetry-voltage` fallback.*"
    )
    lines.append("")

    # Mock under all 4 skins
    lines.extend(["### Mock (all 4 skins — chrome demonstration)", ""])
    for skin in ("telemetry-voltage", "telemetry-claude-code", "telemetry-cream", "telemetry-codex"):
        lines.append(f"**{skin}**")
        lines.append("")
        for ft in (FrameType.RECEIPT, FrameType.RHYTHM_STRIP):
            lines.append(f"![{ft}-{skin}-mock](proofset/telemetry/{ft.value.replace('-', '_')}_{skin}_mock.svg)")
            lines.append("")

    # Real transcripts grouped by source runtime (matched skin + voltage)
    real_groups: list[tuple[str, list[tuple[str, Path]], str]] = [
        ("Claude Code transcripts", _REAL_TRANSCRIPTS, "telemetry-claude-code"),
        ("Codex transcripts", _REAL_CODEX_TRANSCRIPTS, "telemetry-codex"),
    ]
    for group_title, group_transcripts, matched_skin in real_groups:
        labels_present = [label for label, p in group_transcripts if p.exists()]
        if not labels_present:
            continue
        lines.extend([f"### {group_title} ({matched_skin} + telemetry-voltage)", ""])
        for label in labels_present:
            lines.append(f"**{label}**")
            lines.append("")
            for skin in (matched_skin, "telemetry-voltage"):
                for ft in (FrameType.RECEIPT, FrameType.RHYTHM_STRIP):
                    lines.append(
                        f"![{ft}-{skin}-{label}](proofset/telemetry/{ft.value.replace('-', '_')}_{skin}_{label}.svg)"
                    )
                    lines.append("")

    lines.append("### master-card (voltage only, deferred to v0.3.0)")
    lines.append("")
    lines.append("![master-card](proofset/telemetry/master_card.svg)")
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
