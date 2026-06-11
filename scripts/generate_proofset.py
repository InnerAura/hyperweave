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
from functools import lru_cache
from pathlib import Path
from typing import Any

# Ensure src/ is importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_genomes, load_paradigms
from hyperweave.core.enums import (
    ArtifactStatus,
    BorderMotionId,
    FrameType,
    GenomeId,
    Regime,
)
from hyperweave.core.models import ComposeSpec


def _paradigm_supports_compact(genome_cfg: Any, paradigms: dict[str, Any]) -> bool:
    """Whether the genome's badge paradigm declares compact-mode geometry.

    Compact rendering is paradigm geometry (frame_height_compact, glyph_size_compact,
    glyph_offset_left_compact), not genome chromatics. Cellular declares it; chrome
    doesn't. Without this gate the proofset would emit a chrome compact badge that
    has no paradigm-specific tuning, producing a misshapen artifact.
    """
    paradigm_slug = genome_cfg.paradigms.get("badge", "default") if genome_cfg else "default"
    paradigm = paradigms.get(paradigm_slug)
    if paradigm is None:
        return False
    badge = paradigm.badge
    # Compact is supported when the paradigm declares distinct compact geometry —
    # an explicit compact glyph size, a compact glyph ratio (primer: 0.5), OR a
    # compact frame height that differs from the default (primer: 20 vs 36).
    return (
        badge.glyph_size_compact > 0
        or badge.glyph_size_compact_ratio > 0
        or badge.frame_height_compact != badge.frame_height
    )


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


# ── Mock telemetry data for receipt / rhythm-strip ──

# ── Claude Code transcript fallback corpus ──
# Pinned paths used only when live discovery (``_discover_transcripts`` below)
# finds nothing — i.e. on a machine without ~/.claude history. Discovery is the
# primary source; these literals keep clean-env / CI behavior reproducible.
# Paths are user-machine-only (NOT committed) and may be stale on any given box.
_FALLBACK_TRANSCRIPTS: list[tuple[str, Path]] = [
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


# ── Codex transcript fallback corpus ──
# Codex sessions live at ``~/.codex/sessions/YYYY/MM/DD/rollout-TIMESTAMP-UUID.jsonl``.
# Same role as ``_FALLBACK_TRANSCRIPTS``: used only when discovery finds nothing.
_FALLBACK_CODEX_TRANSCRIPTS: list[tuple[str, Path]] = [
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


def _discover_transcripts(
    base: Path,
    pattern: str,
    label_prefix: str,
    fallback: list[tuple[str, Path]],
    *,
    max_candidates: int = 500,
    min_bytes: int = 4096,
) -> list[tuple[str, Path]]:
    """Discover size-varied real transcripts under ``base``.

    Globs ``base/pattern``, drops sub-floor / corrupt files (< ``min_bytes``),
    sorts by on-disk byte size (a deterministic proxy for token volume — avoids
    parsing everything), caps the candidate set at ``max_candidates`` by keeping
    an even spread across the size range (so a 10k-file machine doesn't stat-thrash
    and the scan stays bounded), then selects one representative per size bucket
    (small → xxlarge) across the distribution. Only the chosen few are parsed
    (try/except, backfilling from the next candidate on parse failure). Returns
    ``[(f"{label_prefix}{bucket}", Path), ...]`` with stable labels, or
    ``fallback`` when nothing usable is found (clean-env reproducibility).

    Selection is byte-size-spread, NOT exact token volume — a proxy that keeps the
    scan O(stat) rather than O(parse). Files below ``min_bytes`` are skipped to
    drop empty/corrupt sessions; this is not silent truncation of a real session.
    """
    if not base.is_dir():
        return fallback
    sized = sorted(
        ((p.stat().st_size, str(p), p) for p in base.glob(pattern) if p.is_file()),
        key=lambda t: (t[0], t[1]),
    )
    sized = [s for s in sized if s[0] >= min_bytes]
    if len(sized) > max_candidates:
        step = len(sized) / max_candidates
        sized = [sized[int(i * step)] for i in range(max_candidates)]
    if not sized:
        return fallback

    n = len(sized)
    buckets = ("small", "medium", "large", "xlarge", "xxlarge")
    # Fractional positions spanning small..very-large, avoiding degenerate extremes
    # (the absolute min/max can be empty stubs or pathological multi-MB sessions).
    fractions = (0.08, 0.30, 0.52, 0.74, 0.94)
    out: list[tuple[str, Path]] = []
    used: set[int] = set()
    for bucket, frac in zip(buckets, fractions, strict=True):
        idx = min(n - 1, int(frac * n))
        while idx < n:
            if idx not in used and _load_real_telemetry(sized[idx][2]) is not None:
                used.add(idx)
                out.append((f"{label_prefix}{bucket}", sized[idx][2]))
                break
            idx += 1
    return out or fallback


@lru_cache(maxsize=1)
def _real_transcripts() -> list[tuple[str, Path]]:
    """Discovered Claude Code transcripts (lazy + cached; not at import time)."""
    return _discover_transcripts(Path.home() / ".claude" / "projects", "**/*.jsonl", "", _FALLBACK_TRANSCRIPTS)


@lru_cache(maxsize=1)
def _real_codex_transcripts() -> list[tuple[str, Path]]:
    """Discovered Codex transcripts (lazy + cached; not at import time)."""
    return _discover_transcripts(
        Path.home() / ".codex" / "sessions", "**/rollout-*.jsonl", "codex-", _FALLBACK_CODEX_TRANSCRIPTS
    )


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


def _github_subtitle(token: str) -> dict[str, str]:
    """Derive connector_data with repo_slug for GitHub-sourced specs.

    Resolves ``gh:owner/repo`` (or raw ``owner/repo``) to a connector_data dict
    containing ``repo_slug``. The resolver then emits subtitle = ``owner/repo``,
    distinct from title (which is typically just the repo name). Returns an
    empty dict for non-GitHub tokens so callers can spread it unconditionally.
    """
    if token.startswith("gh:"):
        return {"repo_slug": token[len("gh:") :]}
    if "/" in token and not token.startswith(("pypi:", "npm:", "docker:", "hf:", "arxiv:")):
        return {"repo_slug": token}
    return {}


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
    pair: str = "",
    shape: str = "",
    state_glyph_shape: str = "",
    telemetry_data: dict[str, Any] | None = None,
    connector_data: dict[str, Any] | None = None,
    data_tokens: list[Any] | None = None,
    matrix: dict[str, Any] | None = None,
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
        pair=pair,
        shape=shape,
        state_glyph_shape=state_glyph_shape,
        telemetry_data=telemetry_data,
        connector_data=connector_data,
        data_tokens=list(data_tokens) if data_tokens else [],
        matrix=matrix,
    )
    return compose(spec).svg


def _write(path: Path, svg: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg)


def generate_static() -> int:
    """Generate all static (non-network) artifacts. Returns count."""
    total = 0

    # ── Pre-fetch marquee data tokens (v0.3.2 brutalist genome expansion) ──
    # Resolved once at the top of generate_static so per-variant marquees can
    # carry live GitHub/PyPI data rather than hardcoded brand strings. The
    # stats/chart fetch later in this function (line ~725) uses the SAME
    # asyncio loop pattern; both share one asyncio.run() per process because
    # the httpx singleton binds to its first loop. Failure path: empty list
    # → variant marquees fall back to the per-genome marquee_text strings.
    from hyperweave.connectors.base import close_client as _close_marquee_client
    from hyperweave.serve.data_tokens import parse_data_tokens as _parse_marquee_tokens
    from hyperweave.serve.data_tokens import resolve_data_tokens as _resolve_marquee_tokens

    _MARQUEE_PREFETCH_TOKENS = (
        "github:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks,pypi:readmeai.version,pypi:readmeai.downloads"
    )

    async def _prefetch_marquee_tokens() -> list[Any]:
        try:
            parsed = _parse_marquee_tokens(_MARQUEE_PREFETCH_TOKENS)
            resolved, _ttl = await _resolve_marquee_tokens(parsed)
            await _close_marquee_client()
            return list(resolved)
        except Exception:
            await _close_marquee_client()
            return []

    marquee_data_tokens: list[Any] = asyncio.run(_prefetch_marquee_tokens())
    print(
        f"  resolved {len(marquee_data_tokens)} marquee tokens"
        if marquee_data_tokens
        else "  marquee tokens fetch failed; using fallback text"
    )

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

        # ── 1b. v0.3.0 Variant matrix — every shipped variant rendered for the
        #       relevant frame types. Visual palette verification across the full
        #       chrome x automata variant surface so palette regressions surface
        #       in the proofset before they hit production. Skips genomes with no
        #       variant axis (brutalist). #}
        if genome_cfg and genome_cfg.variants:
            var_dir = gdir / "variants"
            # Per-variant marquee text mirrors the base map at line 308 so the
            # marquee voice stays consistent across base + variant artifacts.
            variant_marquee_text = marquee_text_by_genome.get(genome, "HYPERWEAVE|LIVING ARTIFACTS|v0.3.0")
            # Compact gate: cellular paradigm declares compact badge geometry;
            # chrome paradigm does not. Render compact only when the badge
            # paradigm supports it, so chrome variants emit just the default size
            # and don't produce misshapen un-tuned compact artifacts.
            paradigms = load_paradigms()
            supports_compact = _paradigm_supports_compact(genome_cfg, paradigms)
            # Each variant gets the full artifact suite: badge default (+ compact
            # when paradigm supports), 5 badge states, icon, strip, marquee,
            # divider. Skips border motions and policy lanes (not variant-sensitive).
            # The dissolve divider works for all automata variants (solo gets a
            # synthesized mirrored bridge from primary.cellular_cells via
            # resolve_cellular_palette).
            for variant in genome_cfg.variants:
                # Badge default — exercises label, value, glyph, indicator
                svg = _compose("badge", genome, "PYPI", "v0.3.0", "active", "python", variant=variant)
                _write(var_dir / f"badge_pypi_{variant}_default.svg", svg)
                total += 1
                if supports_compact:
                    svg = _compose(
                        "badge", genome, "PYPI", "v0.3.0", "active", "python", variant=variant, size="compact"
                    )
                    _write(var_dir / f"badge_pypi_{variant}_compact.svg", svg)
                    total += 1
                # Badge states per variant — full state-machine palette coverage
                for status in (
                    ArtifactStatus.PASSING,
                    ArtifactStatus.WARNING,
                    ArtifactStatus.CRITICAL,
                    ArtifactStatus.BUILDING,
                    ArtifactStatus.OFFLINE,
                ):
                    svg = _compose("badge", genome, "BUILD", status.value, status, "github", variant=variant)
                    _write(var_dir / f"badge_{status}_{variant}.svg", svg)
                    total += 1
                    # Compact badge across every state (when the paradigm supports
                    # compact geometry) — the 20px form of each state badge.
                    if supports_compact:
                        svg = _compose(
                            "badge", genome, "BUILD", status.value, status, "github", variant=variant, size="compact"
                        )
                        _write(var_dir / f"badge_{status}_{variant}_compact.svg", svg)
                        total += 1
                # Icon shapes — render every shape the genome's icon paradigm
                # declares in ``icon.supported_shapes`` (chrome/brutalist/primer:
                # [circle, square]; automata: [square] only). Data-driven so a
                # paradigm that supports both never silently emits just one.
                _icon_paradigm = paradigms.get(genome_cfg.paradigms.get("icon", "default")) if genome_cfg else None
                _icon_shapes = list(_icon_paradigm.icon.supported_shapes) if _icon_paradigm else []
                if len(_icon_shapes) > 1:
                    for _shape in _icon_shapes:
                        svg = _compose("icon", genome, glyph="github", shape=_shape, variant=variant)
                        _write(var_dir / f"icon_github_{variant}_{_shape}.svg", svg)
                        total += 1
                else:
                    svg = _compose("icon", genome, glyph="github", variant=variant)
                    _write(var_dir / f"icon_github_{variant}.svg", svg)
                    total += 1
                # Strip: identity + 3 metrics. Paired automata variants render
                # bifamily flanks; solo render content-only.
                svg = _compose(
                    "strip",
                    genome,
                    "readme-ai",
                    "STARS:12.4k,VERSION:v0.6.9,BUILD:passing",
                    "passing",
                    "github",
                    variant=variant,
                    connector_data={"repo_slug": "eli64s/readme-ai"},
                )
                _write(var_dir / f"strip_{variant}.svg", svg)
                total += 1
                # Marquee per variant — text + chromatic palette swap.
                # v0.3.2 brutalist genome expansion: when marquee_data_tokens
                # resolved at function-top, pass them so the marquee renders
                # real GitHub/PyPI values (stars, forks, version, downloads).
                # Empty token list falls back to the hardcoded text path.
                svg = _compose(
                    "marquee-horizontal",
                    genome,
                    variant_marquee_text,
                    variant=variant,
                    data_tokens=marquee_data_tokens or None,
                )
                _write(var_dir / f"marquee_horizontal_{variant}.svg", svg)
                total += 1
                # Divider per variant — chrome.band (vibration sweep across env);
                # automata.dissolve (bifamily bridge, solo synthesizes mirrored);
                # brutalist: light scholars default to sigil (ink rules + solid
                # center block), dark substrates keep seam (concrete joint).
                if genome == GenomeId.BRUTALIST:
                    # Both genome dividers per variant — seam (concrete joint) and
                    # sigil (ink rules + solid center block) — so each README
                    # variant section shows the full divider register. Light
                    # variants default to sigil, dark to seam at request time.
                    divider_slugs = ("seam", "sigil")
                elif genome == GenomeId.CHROME:
                    divider_slugs = ("band",)
                elif genome == GenomeId.PRIMER:
                    # Primer ships the luminous "aura" divider (lit filament + blurred aura).
                    divider_slugs = ("aura",)
                else:
                    divider_slugs = ("dissolve",)
                for divider_slug in divider_slugs:
                    svg = _compose("divider", genome, divider_variant=divider_slug, variant=variant)
                    _write(var_dir / f"divider_{divider_slug}_{variant}.svg", svg)
                    total += 1

        # ── 1c. v0.3.0 Freestyle pairings (automata only) ──
        # The pairing grammar modifier ?variant=primary&pair=secondary composes
        # any two solo tones at request time. Strip and divider are the
        # bifamily frames that visibly consume the pair (other frames
        # silently ignore it). Render ~10 representative pairings to disk
        # so README_AUTOMATA.md can showcase the grammar's combinatorial
        # surface without trying to enumerate the full 12x11=132 matrix.
        if genome == GenomeId.AUTOMATA:
            freestyle_dir = gdir / "pairings"
            freestyle_pairs: list[tuple[str, str]] = [
                ("teal", "violet"),  # legacy bifamily flagship
                ("bone", "steel"),  # legacy neutral pairing
                ("cobalt", "magenta"),  # warm/cool tension
                ("jade", "crimson"),  # complementary wheel opposites
                ("violet", "amber"),  # purple/gold royal pairing
                ("solar", "abyssal"),  # thermal opposites
                ("toxic", "jade"),  # adjacent greens
                ("crimson", "steel"),  # warm signal on cool substrate
                ("magenta", "bone"),  # saturated on neutral
                ("amber", "cobalt"),  # warm/cool inverted from cobalt+magenta
            ]
            for primary, secondary in freestyle_pairs:
                pair_slug = f"{primary}-{secondary}"
                svg = _compose(
                    "strip",
                    genome,
                    "readme-ai",
                    "STARS:12.4k,VERSION:v0.6.9,BUILD:passing",
                    "passing",
                    "github",
                    variant=primary,
                    pair=secondary,
                    connector_data={"repo_slug": "eli64s/readme-ai"},
                )
                _write(freestyle_dir / f"strip_{pair_slug}.svg", svg)
                total += 1
                svg = _compose(
                    "divider",
                    genome,
                    divider_variant="dissolve",
                    variant=primary,
                    pair=secondary,
                )
                _write(freestyle_dir / f"divider_dissolve_{pair_slug}.svg", svg)
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
    for label, transcript_path in _real_transcripts():
        contract = _load_real_telemetry(transcript_path)
        if contract is not None:
            transcript_corpus.append((label, contract))
    for label, transcript_path in _real_codex_transcripts():
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
    variant: str = "",
    data_tokens: list[Any] | None = None,
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
        variant=variant,
        data_tokens=data_tokens,
    )
    return compose(spec).svg


def _write_stats_family(
    *,
    genome: str,
    stem: str,
    stats_username: str,
    connector_data: dict[str, Any] | None = None,
    data_tokens: list[Any] | None = None,
) -> int:
    """Write a stats proof artifact plus per-variant siblings when available."""
    total = 0
    gdir = OUT / "proofset" / genome / "data-cards"
    svg = _compose_connector(
        "stats",
        genome,
        stats_username=stats_username,
        connector_data=connector_data,
        data_tokens=data_tokens,
    )
    _write(gdir / f"{stem}.svg", svg)
    total += 1

    genome_cfg = load_genomes().get(str(genome))
    if genome_cfg and genome_cfg.variants:
        var_dir = OUT / "proofset" / genome / "variants"
        for variant in genome_cfg.variants:
            svg = _compose_connector(
                "stats",
                genome,
                stats_username=stats_username,
                connector_data=connector_data,
                data_tokens=data_tokens,
                variant=variant,
            )
            _write(var_dir / f"{stem}_{variant}.svg", svg)
            total += 1
    return total


def _write_chart_family(
    *,
    genome: str,
    stem: str,
    connector_data: dict[str, Any],
) -> int:
    """Write a chart proof artifact plus per-variant siblings when available."""
    total = 0
    gdir = OUT / "proofset" / genome / "data-cards"
    svg = _compose_connector("chart", genome, connector_data=connector_data)
    _write(gdir / f"{stem}.svg", svg)
    total += 1

    genome_cfg = load_genomes().get(str(genome))
    if genome_cfg and genome_cfg.variants:
        var_dir = OUT / "proofset" / genome / "variants"
        for variant in genome_cfg.variants:
            svg = _compose_connector("chart", genome, connector_data=connector_data, variant=variant)
            _write(var_dir / f"{stem}_{variant}.svg", svg)
            total += 1
    return total


async def _fetch_snapshot_or_cache(
    fixtures: dict[str, Any],
    cache_key: str,
    label: str,
    fetcher: Any,
) -> dict[str, Any]:
    """Fetch a provider snapshot live, falling back to the proofset fixture cache."""
    import time

    try:
        result = await fetcher()
        fixtures[cache_key] = {"value": result, "fetched_at": time.time()}
        return result
    except Exception as exc:
        cached = fixtures.get(cache_key)
        if isinstance(cached, dict) and isinstance(cached.get("value"), dict):
            print(f"  [SNAPSHOT CACHE] {label}: live failed ({type(exc).__name__}), using cached live fixture")
            return dict(cached["value"])
        raise


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

        # Per-variant stats cards — same connector_data, variant-shifted palette.
        # Output to outputs/proofset/{genome}/variants/stats_{variant}.svg (flat
        # under variants/, matching the badge/icon/strip naming convention).
        genome_cfg = load_genomes().get(str(genome))
        if genome_cfg and genome_cfg.variants:
            var_dir = OUT / "proofset" / genome / "variants"
            for variant in genome_cfg.variants:
                svg = _compose_connector(
                    "stats",
                    genome,
                    stats_username="eli64s",
                    connector_data=stats_data,
                    variant=variant,
                )
                _write(var_dir / f"stats_{variant}.svg", svg)
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

        # Per-variant star charts — same chart data, variant-shifted palette.
        # Output to outputs/proofset/{genome}/variants/chart_stars_{variant}.svg.
        if genome_cfg and genome_cfg.variants:
            var_dir = OUT / "proofset" / genome / "variants"
            for variant in genome_cfg.variants:
                svg = _compose_connector(
                    "chart",
                    genome,
                    chart_owner="eli64s",
                    chart_repo="readme-ai",
                    connector_data=chart_data,
                    variant=variant,
                )
                _write(var_dir / f"chart_stars_{variant}.svg", svg)
                total += 1

    async def _fetch_multisource_cards(fixtures: dict[str, Any]) -> dict[str, Any]:
        from hyperweave.connectors.base import close_client as _close_client
        from hyperweave.connectors.snapshots import fetch_arxiv_snapshot, fetch_hf_snapshot, fetch_pypi_snapshot
        from hyperweave.serve.data_tokens import parse_data_tokens, resolve_data_tokens

        results: dict[str, Any] = {}
        try:
            tokens = parse_data_tokens(
                "github:zai-org/GLM-5.stars,"
                "hf:zai-org/GLM-5.1.downloads,"
                "hf:zai-org/GLM-5.1.likes,"
                "arxiv:2602.15763.title"
            )
            resolved, _ttl = await resolve_data_tokens(tokens)
            results["glm5_tokens"] = list(resolved)
        except Exception as exc:
            print(f"  [MULTI-SOURCE SKIP] GLM-5 data tokens: {type(exc).__name__}: {exc}")
        try:
            tokens = parse_data_tokens("github:n8n-io/n8n.stars,npm:n8n.downloads,docker:n8nio/n8n.pull_count")
            resolved, _ttl = await resolve_data_tokens(tokens)
            results["n8n_tokens"] = list(resolved)
        except Exception as exc:
            print(f"  [MULTI-SOURCE SKIP] n8n data tokens: {type(exc).__name__}: {exc}")
        try:
            tokens = parse_data_tokens(
                "github:eli64s/readme-ai.stars,pypi:readmeai.downloads,docker:zeroxeli/readme-ai.pull_count"
            )
            resolved, _ttl = await resolve_data_tokens(tokens)
            results["readmeai_tokens"] = list(resolved)
        except Exception as exc:
            print(f"  [MULTI-SOURCE SKIP] readme-ai data tokens: {type(exc).__name__}: {exc}")
        try:
            results["readmeai_pypi"] = await _fetch_snapshot_or_cache(
                fixtures,
                "snapshot:pypi:readmeai",
                "PyPI readmeai",
                lambda: fetch_pypi_snapshot("readmeai"),
            )
        except Exception as exc:
            print(f"  [MULTI-SOURCE SKIP] PyPI readmeai snapshot: {type(exc).__name__}: {exc}")
        try:
            results["hf_glm51"] = await _fetch_snapshot_or_cache(
                fixtures,
                "snapshot:huggingface:zai-org/GLM-5.1",
                "HuggingFace zai-org/GLM-5.1",
                lambda: fetch_hf_snapshot("zai-org/GLM-5.1"),
            )
        except Exception as exc:
            print(f"  [MULTI-SOURCE SKIP] HuggingFace GLM-5.1 snapshot: {type(exc).__name__}: {exc}")
        try:
            results["arxiv_2602"] = await _fetch_snapshot_or_cache(
                fixtures,
                "snapshot:arxiv:2602.15763",
                "arXiv 2602.15763",
                lambda: fetch_arxiv_snapshot("2602.15763"),
            )
        except Exception as exc:
            print(f"  [MULTI-SOURCE SKIP] arXiv 2602.15763 snapshot: {type(exc).__name__}: {exc}")
        try:
            results["vllm_pypi"] = await _fetch_snapshot_or_cache(
                fixtures,
                "snapshot:pypi:vllm",
                "PyPI vllm",
                lambda: fetch_pypi_snapshot("vllm"),
            )
        except Exception as exc:
            print(f"  [MULTI-SOURCE SKIP] PyPI vllm snapshot: {type(exc).__name__}: {exc}")
        await _close_client()
        return results

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from proofset_harness import load_fixtures, save_fixtures

    fixtures = load_fixtures()
    fixtures_before = dict(fixtures)
    multisource = asyncio.run(_fetch_multisource_cards(fixtures))
    if fixtures != fixtures_before:
        save_fixtures(fixtures)
        added = len(set(fixtures) - set(fixtures_before))
        if added:
            print(f"  cached {added} provider snapshots")
        else:
            print("  refreshed provider snapshot cache")

    hf_snapshot = multisource.get("hf_glm51")
    if isinstance(hf_snapshot, dict):
        total += _write_stats_family(
            genome=str(GenomeId.CHROME),
            stem="stats_glm51_hf",
            stats_username="GLM-5.1",
            connector_data=hf_snapshot,
        )
    arxiv_snapshot = multisource.get("arxiv_2602")
    if isinstance(arxiv_snapshot, dict):
        total += _write_stats_family(
            genome=str(GenomeId.AUTOMATA),
            stem="stats_arxiv_2602",
            stats_username="2602.15763",
            connector_data=arxiv_snapshot,
        )
    if isinstance(hf_snapshot, dict) and isinstance(arxiv_snapshot, dict):
        from hyperweave.connectors.snapshots import merge_stats_sources

        hf_arxiv = merge_stats_sources(hf_snapshot, arxiv_snapshot)
        hf_arxiv["identity"] = "zai-org/GLM-5.1"
        hf_arxiv["username"] = "GLM-5.1"
        hf_arxiv["identity_subtitle"] = "HuggingFace model + arXiv paper"
        total += _write_stats_family(
            genome=str(GenomeId.CHROME),
            stem="stats_zai_hf_arxiv",
            stats_username="GLM-5.1",
            connector_data=hf_arxiv,
        )

    if multisource.get("glm5_tokens"):
        total += _write_stats_family(
            genome=str(GenomeId.CHROME),
            stem="stats_glm5_multiprovider",
            stats_username="GLM-5",
            connector_data={
                "identity": "GLM-5",
                "identity_subtitle": "Z.AI ecosystem",
                "source_url": "https://github.com/zai-org/GLM-5",
            },
            data_tokens=multisource["glm5_tokens"],
        )
    if multisource.get("n8n_tokens"):
        total += _write_stats_family(
            genome=str(GenomeId.CHROME),
            stem="stats_n8n_distribution",
            stats_username="n8n",
            connector_data={
                "identity": "n8n",
                "identity_subtitle": "GitHub + npm + Docker",
                "source_url": "https://github.com/n8n-io/n8n",
            },
            data_tokens=multisource["n8n_tokens"],
        )
    vllm_snapshot = multisource.get("vllm_pypi")
    if isinstance(vllm_snapshot, dict):
        total += _write_stats_family(
            genome=str(GenomeId.BRUTALIST),
            stem="stats_vllm_pypi",
            stats_username="vllm",
            connector_data=vllm_snapshot,
        )
        if vllm_snapshot.get("series_points"):
            for genome_id in (GenomeId.BRUTALIST, GenomeId.CHROME, GenomeId.AUTOMATA):
                total += _write_chart_family(
                    genome=str(genome_id),
                    stem="chart_vllm_downloads",
                    connector_data=vllm_snapshot,
                )

    # v0.3.13 brutalist-LIGHT multi-source data cards — prove the light stats
    # card (horizontal row, ink header, accent data-viz) is source-agnostic
    # across providers AND variants. Every metric binds to a live connector; a
    # failed fetch skips the card so its README link breaks loudly rather than
    # ship fabricated numbers.
    light_dir = OUT / "proofset" / str(GenomeId.BRUTALIST) / "data-cards"

    def _light_card(
        *,
        variant: str,
        stem: str,
        username: str,
        connector_data: dict[str, Any] | None,
        data_tokens: list[Any] | None = None,
    ) -> int:
        svg = _compose_connector(
            "stats",
            str(GenomeId.BRUTALIST),
            stats_username=username,
            connector_data=connector_data,
            variant=variant,
            data_tokens=data_tokens,
        )
        _write(light_dir / f"{stem}.svg", svg)
        return 1

    # 1. GitHub user stats — eli64s, pulse (4-metric row + STREAK momentum tint).
    total += _light_card(
        variant="pulse", stem="stats_eli64s_brutalist_pulse", username="eli64s", connector_data=stats_data
    )
    # 2. PyPI package stats — vllm, archive (3 metrics + download sparkline).
    if isinstance(vllm_snapshot, dict):
        total += _light_card(
            variant="archive",
            stem="stats_vllm_pypi_brutalist_archive",
            username="vllm",
            connector_data=vllm_snapshot,
        )
    # 3. Z.AI combined card — HuggingFace + arXiv, depth (cross-provider on light).
    if isinstance(hf_snapshot, dict) and isinstance(arxiv_snapshot, dict):
        from hyperweave.connectors.snapshots import merge_stats_sources as _merge_sources

        _zai = _merge_sources(hf_snapshot, arxiv_snapshot)
        _zai["identity"] = "zai-org/GLM-5.1"
        _zai["username"] = "GLM-5.1"
        _zai["identity_subtitle"] = "HuggingFace model + arXiv paper"
        total += _light_card(
            variant="depth", stem="stats_zai_hf_arxiv_brutalist_depth", username="GLM-5.1", connector_data=_zai
        )
    # 4. readme-ai multi-provider — ozalid (GitHub stars + PyPI downloads +
    #    Docker pulls via tokens; the PyPI snapshot supplies the download sparkline).
    readmeai_pypi = multisource.get("readmeai_pypi")
    if multisource.get("readmeai_tokens") and isinstance(readmeai_pypi, dict):
        # The 3 tokens (GitHub stars + PyPI downloads + Docker pulls) ARE the
        # metrics; the PyPI snapshot contributes only its download sparkline +
        # series, so the card reads as a genuine multi-provider composition
        # rather than a PyPI card with one star metric grafted on.
        _readmeai = {
            "identity": "readme-ai",
            "username": "readme-ai",
            "identity_subtitle": "GitHub + PyPI + Docker",
            "source_url": "https://github.com/eli64s/readme-ai",
            "activity": readmeai_pypi.get("activity"),
            "series_points": readmeai_pypi.get("series_points"),
        }
        total += _light_card(
            variant="ozalid",
            stem="stats_readmeai_multi_brutalist_ozalid",
            username="readme-ai",
            connector_data=_readmeai,
            data_tokens=multisource["readmeai_tokens"],
        )

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
        "github:eli64s/readme-ai.stars,"
        "github:eli64s/readme-ai.forks,"
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
            variant="violet-teal" if genome == GenomeId.AUTOMATA else "",
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
    """Generate outputs/README.md — slim cross-reference + parity summary.

    Per-variant artifact matrices live in the genome-specific READMEs
    (README_BRUTALIST.md, README_CHROME.md, README_AUTOMATA.md). Telemetry
    artifacts live in README_TELEMETRY.md. The main README keeps a quick
    base-frames tour per genome, the editorial dividers, per-genome border
    motions, per-genome policy lanes (preserved as reference for future
    governance work), and the parity matrix summary.
    """
    lines = [
        "# HyperWeave Proof Set",
        "",
        "Quick-reference proofset for the three production genomes plus telemetry "
        "and parity surfaces. Per-variant artifact matrices live in dedicated files:",
        "",
        "- [README_BRUTALIST.md](README_BRUTALIST.md) — 22 brutalist variants (8 dark monochromes + 14 light scholars)",
        "- [README_PRIMER.md](README_PRIMER.md) — 8 primer substrates (4 dark + 4 light editorial)",
        "- [README_CHROME.md](README_CHROME.md) — 5 chrome material identities "
        "(horizon, abyssal, lightning, graphite, moth)",
        "- [README_AUTOMATA.md](README_AUTOMATA.md) — 16 automata solo tones plus pairing-grammar showcase",
        "- [README_TELEMETRY.md](README_TELEMETRY.md) — receipt + rhythm-strip across all 4 telemetry skins",
        "",
        "---",
        "",
    ]

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

        # Per-variant matrices (badge/icon/strip/marquee/divider/stats/chart
        # + 5 states) live in the genome-specific READMEs — see the
        # cross-link block at the top of this file. State Machine + Profile
        # Card + Star History Chart are mirrored there too. Policy lanes
        # and border motions stay inline below as governance + motion
        # reference scaffolding.

        # Policy lanes (kept as reference for future governance work —
        # data-hw-regime swaps surface scaffolding without rerendering).
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

    multi_source_cards = [
        ("proofset/chrome/data-cards/stats_glm51_hf.svg", "HuggingFace model stats — zai-org/GLM-5.1"),
        ("proofset/automata/data-cards/stats_arxiv_2602.svg", "arXiv paper stats — 2602.15763"),
        ("proofset/chrome/data-cards/stats_zai_hf_arxiv.svg", "Z.AI combined card — HuggingFace + arXiv"),
        ("proofset/chrome/data-cards/stats_glm5_multiprovider.svg", "Z.AI multi-provider tokens — GitHub + HF + arXiv"),
        ("proofset/chrome/data-cards/stats_n8n_distribution.svg", "n8n multi-provider tokens — GitHub + npm + Docker"),
        ("proofset/brutalist/data-cards/stats_vllm_pypi.svg", "PyPI package stats — vllm sparkline activity"),
        # v0.3.13 brutalist-LIGHT data cards — source-agnostic across providers + variants.
        (
            "proofset/brutalist/data-cards/stats_eli64s_brutalist_pulse.svg",
            "GitHub stats — eli64s, 4-metric row + STREAK tint, brutalist pulse (light)",
        ),
        (
            "proofset/brutalist/data-cards/stats_vllm_pypi_brutalist_archive.svg",
            "PyPI package stats — vllm, 3 metrics + sparkline, brutalist archive (light)",
        ),
        (
            "proofset/brutalist/data-cards/stats_zai_hf_arxiv_brutalist_depth.svg",
            "Z.AI combined — HuggingFace + arXiv (cross-provider), brutalist depth (light)",
        ),
        (
            "proofset/brutalist/data-cards/stats_readmeai_multi_brutalist_ozalid.svg",
            "readme-ai multi-provider — GitHub + PyPI + Docker, brutalist ozalid (light)",
        ),
        ("proofset/brutalist/data-cards/chart_vllm_downloads.svg", "PyPI download trend chart — vllm"),
        ("proofset/chrome/data-cards/chart_vllm_downloads.svg", "PyPI download trend chart — vllm chrome"),
        ("proofset/automata/data-cards/chart_vllm_downloads.svg", "PyPI download trend chart — vllm automata"),
    ]
    existing_multi_source_cards = [(path, label) for path, label in multi_source_cards if (OUT / path).exists()]
    if existing_multi_source_cards:
        lines.extend(
            [
                "## Multi-Source Data Cards",
                "",
                "Live provider snapshots and data-token compositions proving that stats and chart frames are "
                "source-agnostic.",
                "",
            ]
        )
        for path, label in existing_multi_source_cards:
            lines.append(f"**{label}**")
            lines.append("")
            lines.append(f"![{label}]({path})")
            lines.append("")

    # Genome-agnostic dividers (live at /a/inneraura/dividers/, generated once)
    lines.extend(["## `/a/inneraura/dividers/`", ""])
    for slug in ("block", "current", "takeoff", "void", "zeropoint"):
        lines.append(f"![divider {slug}](proofset/inneraura/dividers/{slug}.svg)")
        lines.append("")

    # Telemetry visual-fidelity matrix (v0.2.23): runtime-paired skins.
    # Each transcript renders only under its matched-runtime skin + voltage
    # Telemetry content lives in README_TELEMETRY.md — the main README only
    # cross-links there to keep the surface tour scannable.
    lines.extend(
        [
            "## Telemetry",
            "",
            "Receipt + rhythm-strip artifacts across all 4 telemetry skins "
            "(voltage, claude-code, cream, codex) — including mock data and "
            "real transcripts from Claude Code and Codex sessions — live in "
            "[README_TELEMETRY.md](README_TELEMETRY.md).",
            "",
        ]
    )

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
    _emit_automata_readme()
    _emit_brutalist_readme()
    _emit_primer_readme()
    _emit_matrix_readme()
    _emit_chrome_readme()
    _emit_telemetry_readme()
    _emit_state_readme()


def _emit_state_readme() -> None:
    """Emit outputs/README_STATE.md — the badge state-indicator shape matrix.

    3 genomes (spanning the badge paradigms) x 3 shapes (square / circle /
    diamond, forced via the request-time ?state_glyph_shape= override). Each shape
    renders a 3x3 grid: 3 variants (rows) x 3 states (passing / warning / critical,
    columns) so both the shape dispatch AND the per-variant state-glyph colour are
    comparable in one scroll. 81 badges into proofset/state-matrix/ — distinct from
    the per-genome <genome>/states/ dirs. Cross-paradigm diamonds (e.g. brutalist
    + diamond) show only the ring + bit because the housing routes through
    chrome-specific --dna-diamond-* vars; that is honest, not broken.
    """
    state_dir = OUT / "proofset" / "state-matrix"
    # Per genome: three variants spanning its colour range. Substrate noted because
    # brutalist mixes dark and light variants (a light variant forced to `square`
    # shows its state colour on a paper substrate).
    # (genome, [(variant, substrate)], shapes). brutalist/chrome/automata share the
    # configurable geometric shapes; primer's indicator is its own state-keyed
    # ANIMATED mark (status-glyph: ping/throb/shake per state), which is its only
    # shape — the geometric square/circle/diamond paths don't apply to it.
    geometric = ("square", "circle", "diamond")
    genomes = [
        (
            "brutalist",
            [("celadon", "dark — emerald phosphor"), ("ember", "dark — fired clay"), ("archive", "light — paper")],
            geometric,
        ),
        (
            "chrome",
            [("horizon", "frozen blue-silver"), ("moth", "umber iridescent"), ("abyssal", "teal-cyan")],
            geometric,
        ),
        (
            "automata",
            [("teal", "cellular teal"), ("violet", "cellular violet"), ("amber", "cellular amber")],
            geometric,
        ),
        (
            "primer",
            [("porcelain", "light flagship"), ("noir", "dark"), ("carbon", "dark — ember accent")],
            ("status-glyph",),
        ),
    ]
    states = (ArtifactStatus.PASSING, ArtifactStatus.WARNING, ArtifactStatus.CRITICAL)

    lines: list[str] = [
        "# HyperWeave Badge State-Indicator Shape Matrix",
        "",
        "The badge state indicator is a configurable shape — `square`, `circle`, "
        "or `diamond` — selectable per genome/variant or per request via "
        "`?state_glyph_shape=`. Each paradigm has a default (brutalist dark=square "
        "/ light=circle, chrome=diamond, cellular=square); the override flips it. "
        "Primer is the exception: its indicator is a state-KEYED animated mark "
        "(`status-glyph` — ping / throb / shake per state), its own system rather "
        "than a geometric, so it shows that one shape.",
        "",
        "Each shape shows a 3x3 grid — three variants (rows) across passing / "
        "warning / critical (columns) — so the shape dispatch and the per-variant "
        "state-glyph colour are both verifiable in one scroll.",
        "",
        "---",
        "",
    ]
    for genome, variants, shapes in genomes:
        lines.extend([f"## {genome}", ""])
        for shape in shapes:
            lines.extend([f"### shape = `{shape}`", ""])
            for variant, substrate in variants:
                lines.append(f"**{variant}** ({substrate})")
                lines.append("")
                row = []
                for status in states:
                    svg = _compose(
                        "badge",
                        genome,
                        title="BUILD",
                        description=status.value,
                        state=status.value,
                        glyph="github",
                        variant=variant,
                        state_glyph_shape=shape,
                    )
                    fname = f"badge_{genome}_{variant}_{shape}_{status.value}.svg"
                    _write(state_dir / fname, svg)
                    row.append(f"![{variant}-{shape}-{status.value}](proofset/state-matrix/{fname})")
                lines.append(" ".join(row))  # one line → states render side-by-side
                lines.append("")
    lines.extend(
        [
            "## Cross-reference",
            "",
            "- [Main README](README.md) — proofset overview + genome cross-links",
            "",
        ]
    )
    (OUT / "README_STATE.md").write_text("\n".join(lines) + "\n")


def _emit_telemetry_readme() -> None:
    """Emit outputs/README_TELEMETRY.md with the full telemetry artifact tour.

    Receipt + rhythm-strip rendered under each of the four telemetry skins
    (voltage, claude-code, cream, codex) with mock data, plus real
    transcripts from Claude Code and Codex sessions matched to their
    runtime-paired skin alongside the voltage fallback.

    Cross-runtime renders (codex data in cream skin, claude-code data in
    codex skin) are not generated — they're noise rather than signal.
    """
    lines: list[str] = [
        "# HyperWeave Telemetry — Receipt + Rhythm-Strip Matrix",
        "",
        "Telemetry artifacts (receipt cards, rhythm strips) are "
        "**genome-independent at the rendering layer** but render under one of "
        "four named skins: `telemetry-voltage` (universal fallback), "
        "`telemetry-claude-code`, `telemetry-cream`, `telemetry-codex`.",
        "",
        "Each real transcript renders against its matched-runtime skin plus "
        "voltage. Mock data demonstrates all 4 skins on a neutral baseline. "
        "Skin precedence chain: explicit `--genome` override → JSONL `runtime` "
        "field → `telemetry-voltage` fallback.",
        "",
        "---",
        "",
        "## Mock (all 4 skins — chromatic demonstration)",
        "",
    ]
    for skin in ("telemetry-voltage", "telemetry-claude-code", "telemetry-cream", "telemetry-codex"):
        lines.append(f"### {skin}")
        lines.append("")
        for ft in (FrameType.RECEIPT, FrameType.RHYTHM_STRIP):
            lines.append(f"![{ft}-{skin}-mock](proofset/telemetry/{ft.value.replace('-', '_')}_{skin}_mock.svg)")
            lines.append("")

    real_groups: list[tuple[str, list[tuple[str, Path]], str]] = [
        ("Claude Code transcripts", _real_transcripts(), "telemetry-claude-code"),
        ("Codex transcripts", _real_codex_transcripts(), "telemetry-codex"),
    ]
    for group_title, group_transcripts, matched_skin in real_groups:
        labels_present = [label for label, p in group_transcripts if p.exists()]
        if not labels_present:
            continue
        lines.extend([f"## {group_title} ({matched_skin} + telemetry-voltage)", ""])
        for label in labels_present:
            lines.append(f"### {label}")
            lines.append("")
            for skin in (matched_skin, "telemetry-voltage"):
                for ft in (FrameType.RECEIPT, FrameType.RHYTHM_STRIP):
                    lines.append(
                        f"![{ft}-{skin}-{label}](proofset/telemetry/{ft.value.replace('-', '_')}_{skin}_{label}.svg)"
                    )
                    lines.append("")

    lines.extend(
        [
            "## Cross-reference",
            "",
            "- [Main README](README.md) — proofset overview + genome cross-links",
            "",
        ]
    )

    (OUT / "README_TELEMETRY.md").write_text("\n".join(lines) + "\n")


def _emit_automata_readme() -> None:
    """Emit outputs/README_AUTOMATA.md with the full 16-tone variant matrix
    plus a freestyle pairings showcase. Lifted out of the main README to
    keep that file scannable; with 16 solo tones x 7 frame types + 5 badge
    states each, the full matrix dominates whatever else lives there.

    Image references point at LOCAL artifacts under outputs/proofset/automata/
    — this is a local gallery, not deployed URLs.
    """
    g = "automata"
    cfg = load_genomes().get(g)
    if cfg is None or not cfg.variants:
        return
    variants = cfg.variants

    lines: list[str] = [
        "# HyperWeave Automata — 16-Tone Variant Matrix",
        "",
        "Automata is the cellular paradigm: 16 solo tones (`violet`, `teal`, `bone`, `steel`, "
        "`amber`, `jade`, `magenta`, `cobalt`, `toxic`, `solar`, `abyssal`, `crimson`, "
        "`sulfur`, `indigo`, `burgundy`, `copper`) plus a "
        "request-time pairing grammar that composes any two tones into a bifamily strip or "
        "divider. Use `?variant=primary&pair=secondary` to pair, `?variant=primary` alone for solo.",
        "",
        "Every solo tone below renders the full artifact suite (badge default + compact, icon, "
        "strip, marquee, divider, stats card, star chart, 5 badge states). Pairing examples "
        "live in the [Freestyle Pairings](#freestyle-pairings) section at the bottom.",
        "",
        "---",
        "",
    ]

    for v in variants:
        lines.append(f"## `?variant={v}`")
        lines.append("")
        # Row 1: badge default + compact + icon
        row1 = f"![badge default](proofset/{g}/variants/badge_pypi_{v}_default.svg) "
        compact_path = OUT / "proofset" / g / "variants" / f"badge_pypi_{v}_compact.svg"
        if compact_path.exists():
            row1 += f"![badge compact](proofset/{g}/variants/badge_pypi_{v}_compact.svg) "
        row1 += f"![icon](proofset/{g}/variants/icon_github_{v}.svg)"
        lines.append(row1)
        lines.append("")
        # Row 2: strip
        lines.append(f"![strip](proofset/{g}/variants/strip_{v}.svg)")
        lines.append("")
        # Row 3: marquee
        lines.append(f"![marquee](proofset/{g}/variants/marquee_horizontal_{v}.svg)")
        lines.append("")
        # Row 4: dissolve divider — solo synthesizes mirrored bridge
        lines.append(f"![divider dissolve](proofset/{g}/variants/divider_dissolve_{v}.svg)")
        lines.append("")
        # Row 5: stats card
        stats_path = OUT / "proofset" / g / "variants" / f"stats_{v}.svg"
        if stats_path.exists():
            lines.append(f"![stats](proofset/{g}/variants/stats_{v}.svg)")
            lines.append("")
        # Row 6: star history chart
        chart_path = OUT / "proofset" / g / "variants" / f"chart_stars_{v}.svg"
        if chart_path.exists():
            lines.append(f"![chart](proofset/{g}/variants/chart_stars_{v}.svg)")
            lines.append("")
        # Rows 7-11: badge states stacked
        for s in (
            ArtifactStatus.PASSING,
            ArtifactStatus.WARNING,
            ArtifactStatus.CRITICAL,
            ArtifactStatus.BUILDING,
            ArtifactStatus.OFFLINE,
        ):
            lines.append(f"![{s.value}](proofset/{g}/variants/badge_{s.value}_{v}.svg)")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Freestyle pairings — the URL grammar modifier composes any two tones.
    # Mirrors the freestyle_pairs list in generate_static so the README
    # reflects what's actually on disk; if files are missing the link breaks
    # loudly rather than ships a fake.
    lines.extend(
        [
            "## Freestyle Pairings",
            "",
            "The pairing grammar (`?variant=primary&pair=secondary`) composes any two solo tones "
            "into bifamily strips and dissolve dividers. Other frame types (badge, stats, chart, "
            "marquee, icon) silently ignore the pair and render the primary tone solo. The 10 "
            "combinations below sample the combinatorial surface; any of the 16x15=240 possible "
            "pairings work the same way.",
            "",
        ]
    )
    freestyle_pairs: list[tuple[str, str]] = [
        ("teal", "violet"),
        ("bone", "steel"),
        ("cobalt", "magenta"),
        ("jade", "crimson"),
        ("violet", "amber"),
        ("solar", "abyssal"),
        ("toxic", "jade"),
        ("crimson", "steel"),
        ("magenta", "bone"),
        ("amber", "cobalt"),
    ]
    for primary, secondary in freestyle_pairs:
        pair_slug = f"{primary}-{secondary}"
        lines.append(f"### `?variant={primary}&pair={secondary}`")
        lines.append("")
        strip_path = OUT / "proofset" / g / "pairings" / f"strip_{pair_slug}.svg"
        divider_path = OUT / "proofset" / g / "pairings" / f"divider_dissolve_{pair_slug}.svg"
        if strip_path.exists():
            lines.append(f"![strip](proofset/{g}/pairings/strip_{pair_slug}.svg)")
            lines.append("")
        if divider_path.exists():
            lines.append(f"![divider dissolve](proofset/{g}/pairings/divider_dissolve_{pair_slug}.svg)")
            lines.append("")

    (OUT / "README_AUTOMATA.md").write_text("\n".join(lines) + "\n")


# Brutalist variant phenomenology — one-line identity statements emitted in the
# README header for each variant. Mirrors data/genomes/brutalist.json
# variant_phenomenology so both surfaces stay in sync; if you add a brutalist
# variant, append here too. Split into dark monochromes (substrate materials)
# and light scholars (functional roles) for the README's two-section structure.
_BRUTALIST_DARK_PHENOMENOLOGY: list[tuple[str, str]] = [
    (
        "celadon",
        "the ceramic glaze that survived the kiln — substance held (flagship; "
        "bare `brutalist.static` URL renders this for byte-equality with pre-v0.3.2)",
    ),
    ("carbon", "graphite under pressure — substrate compressed into mark"),
    ("alloy", "cold-rolled fusion — disparate metals made one surface"),
    ("temper", "heat-treated tin — toughness achieved through stress"),
    ("pigment", "amethyst ground to powder — color as physical material"),
    ("ember", "warm metal cooling — luminance held in mass"),
    ("umber", "fired clay holding the kiln's last heat — raw sienna substrate"),
    ("onyx", "polished obsidian — mass without hue; chroma only in the state register"),
]
_BRUTALIST_LIGHT_PHENOMENOLOGY: list[tuple[str, str]] = [
    ("archive", "knowledge preserved — paper as memory substrate"),
    ("signal", "transmission made visible — green terminal on cool white"),
    ("pulse", "rhythm marked in ink — oxblood on parchment"),
    ("depth", "measurement of below — royal blue plumbed"),
    ("afterimage", "the optical echo persisting — perception's residue"),
    ("primer", "the base coat applied — preparation as foundation"),
    ("ferro", "iron meeting air — oxide bloom on raw metal"),
    ("ozalid", "the diazo print developing — ammonia-fixed blueprint"),
    ("sulfur", "mineral brimstone ground fine — acid yellow on bone"),
    ("tyrian", "murex wrung from the shell — imperial dye on linen"),
    ("indigo", "vat-dyed cloth oxidizing — indigo deepening in air"),
    ("patina", "bronze weathered green — copper's slow age"),
    ("graphite", "pencil lead burnished — graphite sheen on tooth"),
    ("cyan", "cyanotype exposed — Prussian blue fixed by light"),
]
_CHROME_PHENOMENOLOGY: list[tuple[str, str]] = [
    (
        "horizon",
        "the frozen midnight envelope — slate held over copper sliver "
        "(flagship; bare `chrome.static` URL renders this for byte-equality)",
    ),
    ("abyssal", "deep-water teal — the cold-cyan envelope"),
    ("lightning", "electric blue arrest — voltage held still"),
    ("graphite", "warm gray cast — pencil lead under pressure"),
    ("moth", "umber iridescence — wing-dust spectra"),
]


def _emit_brutalist_readme() -> None:
    """Emit outputs/README_BRUTALIST.md with the full 22-variant matrix.

    Mirrors README_AUTOMATA's structure: each variant renders its full
    artifact suite (badge default, icon, strip, marquee, both dividers,
    stats card, star chart, 5 badge states) as inline image embeds.

    Brutalist differs from automata in two ways:
    1. Two substrate polarities — 8 dark monochromes (substrate materials)
       and 14 light scholars (functional roles) — split into two README
       sections so the substrate distinction is structural, not buried in
       prose.
    2. No pairing grammar — brutalist is mono-substrate per variant; no
       bifamily strips or freestyle pairings section.

    Brutalist declares two dividers (`seam`, `sigil`); light variants default
    to sigil, dark to seam, and every variant section shows both. Image
    references point at LOCAL artifacts under outputs/proofset/brutalist/.
    """
    g = "brutalist"
    cfg = load_genomes().get(g)
    if cfg is None or not cfg.variants:
        return

    lines: list[str] = [
        "# HyperWeave Brutalist — 22-Variant Substrate Matrix",
        "",
        "Brutalist is the only genome with two substrate polarities: **8 dark monochromes** "
        "(substrate materials — `celadon`, `carbon`, `alloy`, `temper`, `pigment`, `ember`, "
        "`umber`, `onyx`) and **14 light scholars** (functional roles — `archive`, `signal`, "
        "`pulse`, `depth`, `afterimage`, `primer`, `ferro`, `ozalid`, `sulfur`, `tyrian`, "
        "`indigo`, `patina`, `graphite`, `cyan`). Each variant declares `substrate_kind: "
        '"dark" | "light"` driving template include dispatch — same paradigm, two material '
        "identities.",
        "",
        "The dark monochromes follow brutalist material vocabulary: matte surfaces, sharp "
        "zero-radius corners, JetBrains Mono typography, no glow. Each name captures a "
        "substance you can hold. The light scholars invert substrate polarity: paper canvas "
        "hosts dark ink with accent seam colors carrying chromatic identity. Each name "
        "captures a function.",
        "",
        "Stratum: `002-TRIBE`. Flagship variant: `celadon` (byte-equal to pre-v0.3.2 "
        "brutalist palette for backwards compat).",
        "",
        "Brutalist supports both `circle` and `square` icon shapes; each variant embeds "
        "both. Every variant below renders the full artifact suite (default badge, "
        "circle + square icons, strip, marquee, both dividers (seam + sigil), stats card, "
        "star chart, 5 badge states).",
        "",
        "---",
        "",
        "## Dark Monochromes",
        "",
    ]

    def _emit_variant_block(v: str, phenomenology: str) -> None:
        lines.append(f"### `?variant={v}`")
        lines.append("")
        lines.append(f"_{phenomenology}_")
        lines.append("")
        # Row 1: badge default (alone, mirroring chrome's layout)
        lines.append(f"![badge default](proofset/{g}/variants/badge_pypi_{v}_default.svg)")
        lines.append("")
        # Row 2: icons (circle + square side by side)
        lines.append(
            f"![icon circle](proofset/{g}/variants/icon_github_{v}_circle.svg) "
            f"![icon square](proofset/{g}/variants/icon_github_{v}_square.svg)"
        )
        lines.append("")
        # Row 3: strip
        lines.append(f"![strip](proofset/{g}/variants/strip_{v}.svg)")
        lines.append("")
        # Row 4: marquee
        lines.append(f"![marquee](proofset/{g}/variants/marquee_horizontal_{v}.svg)")
        lines.append("")
        # Row 5: both dividers — seam (concrete joint) + sigil (ink rules +
        # solid center block). Light variants default to sigil, dark to seam,
        # but every variant section shows both for the full chromatic register.
        lines.append(
            f"![divider seam](proofset/{g}/variants/divider_seam_{v}.svg) "
            f"![divider sigil](proofset/{g}/variants/divider_sigil_{v}.svg)"
        )
        lines.append("")
        # Row 5: stats card
        stats_path = OUT / "proofset" / g / "variants" / f"stats_{v}.svg"
        if stats_path.exists():
            lines.append(f"![stats](proofset/{g}/variants/stats_{v}.svg)")
            lines.append("")
        # Row 6: star history chart
        chart_path = OUT / "proofset" / g / "variants" / f"chart_stars_{v}.svg"
        if chart_path.exists():
            lines.append(f"![chart](proofset/{g}/variants/chart_stars_{v}.svg)")
            lines.append("")
        # Rows 7-11: badge states stacked
        for s in (
            ArtifactStatus.PASSING,
            ArtifactStatus.WARNING,
            ArtifactStatus.CRITICAL,
            ArtifactStatus.BUILDING,
            ArtifactStatus.OFFLINE,
        ):
            lines.append(f"![{s.value}](proofset/{g}/variants/badge_{s.value}_{v}.svg)")
        lines.append("")
        lines.append("---")
        lines.append("")

    for v, phen in _BRUTALIST_DARK_PHENOMENOLOGY:
        if v in cfg.variants:
            _emit_variant_block(v, phen)

    lines.append("## Light Scholars")
    lines.append("")

    for v, phen in _BRUTALIST_LIGHT_PHENOMENOLOGY:
        if v in cfg.variants:
            _emit_variant_block(v, phen)

    # Architectural notes — what makes brutalist's variant grammar distinct.
    lines.extend(
        [
            "## Substrate Architecture",
            "",
            "`substrate_kind` is the variant-declared axis driving template include dispatch "
            "within the brutalist paradigm:",
            "",
            "```jinja2",
            "{# templates/frames/badge/brutalist-content.j2 (dispatcher) #}",
            '{% include "frames/badge/brutalist-" ~ (substrate_kind | default(\'dark\')) ~ "-content.j2" %}',
            "```",
            "",
            "Dark variants route to `brutalist-dark-content.j2`; light variants route to "
            "`brutalist-light-content.j2`. The dispatcher pattern applies to `badge`, `strip`, "
            "`stats`, and `chart`. Icon, divider, and marquee stay CSS-vars-only because their "
            "prototypes show color-only deltas.",
            "",
            "Validation at `compose/validate_paradigms.py:validate_genome_variants()` enforces "
            "the substrate contract: every variant declares `substrate_kind`; light variants "
            "additionally declare `panel_gradient_stops` (≥2 stops, for the dark academic "
            "panel) and `seam_color`; dark variants must NOT declare `panel_gradient_stops`.",
            "",
            "## Cross-reference",
            "",
            "- [Main README](../README.md) — installation, compose grammar, all genomes",
            "- [CHANGELOG](../CHANGELOG.md) — v0.3.2 release notes",
            "",
        ]
    )

    (OUT / "README_BRUTALIST.md").write_text("\n".join(lines) + "\n")


def _emit_primer_stress_section() -> list[str]:
    """Build the README "Schema-agnostic stress test" section.

    Proves the primer stats card + chart are CONTENT-AWARE: the layout adapts to
    any metric COUNT (1-6) and any connector SHAPE. Every metric binds to a REAL
    connector token (github / pypi / npm / crates) resolved live — NO fabricated
    kv: data. The metric count is varied by slicing a real cross-connector token
    list; the chart rides real GitHub star history. Writes artifacts under
    outputs/proofset/primer/stress/ and returns the markdown.
    """
    import asyncio

    from hyperweave.connectors.base import close_client
    from hyperweave.connectors.snapshots import fetch_pypi_snapshot
    from hyperweave.serve.data_tokens import parse_data_tokens, resolve_data_tokens

    # Six real cross-connector tokens — a single ecosystem footprint card whose
    # metrics span GitHub + PyPI + npm + crates. Sliced [:n] to vary the count.
    token_str = (
        "github:vllm-project/vllm.stars,"
        "github:vllm-project/vllm.forks,"
        "pypi:vllm.version,"
        "pypi:vllm.downloads,"
        "npm:n8n.downloads,"
        "crates:serde.downloads"
    )

    async def _resolve() -> tuple[list[Any], dict[str, Any]]:
        toks: list[Any] = []
        snap: dict[str, Any] = {}
        try:
            parsed = parse_data_tokens(token_str)
            resolved, _ttl = await resolve_data_tokens(parsed)
            toks = list(resolved)
        except Exception:
            toks = []
        try:
            # PyPI snapshot carries BOTH a download sparkline (activity) and a daily
            # download series (series_points) — the card's activity zone + a non-star
            # trend chart, on the same pipeline as the GitHub star chart. Routed
            # through the shared snapshot cache (same "snapshot:pypi:vllm" key the
            # brutalist vllm card uses) so a pypistats 429 under burst regeneration
            # falls back to the last good fixture instead of silently dropping the
            # sparkline card — the only direct, uncached pypi call in the proofset.
            from proofset_harness import load_fixtures

            snap = await _fetch_snapshot_or_cache(
                load_fixtures(),
                "snapshot:pypi:vllm",
                "PyPI vllm (primer stress)",
                lambda: fetch_pypi_snapshot("vllm"),
            )
        except Exception:
            snap = {}
        await close_client()
        return toks, snap

    tokens, pypi_snap = asyncio.run(_resolve())
    lines: list[str] = [
        "## Schema-agnostic stress test",
        "",
        "Every element in every primer frame is a measured, content-aware **slot** — "
        "not hand-placed geometry. The same stats-card and chart layouts adapt to any "
        "**metric count** and any **connector shape**. Below, the card is composed across "
        "**1-6 metrics** sliced from a single live cross-connector footprint "
        "(GitHub + PyPI + npm + crates); the count is the only variable. Every value "
        "binds to a **real connector token** — no fabricated data.",
        "",
    ]
    if not tokens:
        lines.append(
            "_Connector tokens did not resolve at generation time (offline / rate-limited); "
            "re-run `scripts/generate_proofset.py` with network access to populate this section._"
        )
        lines.append("")
        return lines
    sdir = OUT / "proofset" / "primer" / "stress"
    for n in range(1, len(tokens) + 1):
        svg = _compose("stats", "primer", title="vllm", data_tokens=tokens[:n], variant="porcelain")
        _write(sdir / f"stats_n{n}.svg", svg)
        plural = "metric" if n == 1 else "metrics"
        lines.append(f"**{n} {plural}** — card sizes to fit:")
        lines.append("")
        lines.append(f"![primer stats {n} metrics](proofset/primer/stress/stats_n{n}.svg)")
        lines.append("")
    lines.append(
        "The card never reflows to a fixed grid — the hero + secondary metric row flow from "
        "`compute_stats_layout` keyed on the resolved metric set, and the card height collapses "
        "to the data it carries (a single hero metric leaves no dead band).",
    )
    lines.append("")

    # Activity sparkline (the card's editorial activity viz) + non-star trend chart,
    # both from a live PyPI snapshot — the same layout engine, a different shape.
    if pypi_snap.get("activity") or pypi_snap.get("series_points"):
        lines.append("### Activity + non-star data")
        lines.append("")
    if pypi_snap.get("activity"):
        spark = _compose("stats", "primer", title="vllm", connector_data=pypi_snap, variant="porcelain")
        _write(sdir / "stats_sparkline.svg", spark)
        lines.append(
            "**Download sparkline** — the card's activity zone reads a live 30-day PyPI "
            "download series (primer's editorial activity viz; the denser contribution heatmap "
            "is a brutalist/automata form):"
        )
        lines.append("")
        lines.append("![primer stats sparkline](proofset/primer/stress/stats_sparkline.svg)")
        lines.append("")
    if pypi_snap.get("series_points"):
        for var in ("porcelain", "carbon"):
            chart = _compose("chart", "primer", connector_data=pypi_snap, variant=var)
            _write(sdir / f"chart_downloads_{var}.svg", chart)
            lines.append(f"**PyPI download trend — {var}** (non-star series, same chart pipeline):")
            lines.append("")
            lines.append(f"![primer download chart {var}](proofset/primer/stress/chart_downloads_{var}.svg)")
            lines.append("")
    lines.append("---")
    lines.append("")
    return lines


def _emit_primer_readme() -> None:
    """Emit outputs/README_PRIMER.md with the full 8-variant substrate matrix.

    Mirrors README_BRUTALIST's structure: each variant renders its full artifact
    suite (badge default, icon, strip, marquee, aura divider, stats card, star
    chart, 5 badge states) as inline image embeds. Primer is 4 dark + 4 light
    substrates on the flat profile; substrate_kind (read from each variant
    override) splits the two sections. Image refs point at LOCAL artifacts under
    outputs/proofset/primer/.
    """
    g = "primer"
    cfg = load_genomes().get(g)
    if cfg is None or not cfg.variants:
        return
    phen = cfg.variant_phenomenology or {}
    overrides = cfg.variant_overrides or {}

    lines: list[str] = [
        "# HyperWeave Primer — 8-Variant Substrate Matrix",
        "",
        "Primer is HyperWeave's minimal, editorial genome — the clean light-and-dark "
        "on-ramp. Eight substrates split **4 dark** (`noir`, `carbon`, `space`, `anvil`) "
        "and **4 light** (`porcelain`, `cream`, `dusk`, `petrol`), each declaring "
        '`substrate_kind: "dark" | "light"` to drive template include dispatch.',
        "",
        "Inter display type with JetBrains Mono numerals, soft vertical-gradient grounds, "
        "an accent seam fade, circle status dots, and a glassmorphic two-layer drop shadow "
        "lifting the light cards off the page. Rides the `flat` structural profile.",
        "",
        "Stratum: `002-TRIBE`. Flagship variant: `porcelain` (light cobalt-on-white; the "
        "bare `primer.static` URL renders this).",
        "",
        "Every variant below renders the full artifact suite (default badge, icon, strip, "
        "marquee, aura divider, stats card, star chart, 5 badge states).",
        "",
        "---",
        "",
        "## Dark Substrates",
        "",
    ]

    def _emit(v: str) -> None:
        lines.append(f"### `?variant={v}`")
        lines.append("")
        if phen.get(v):
            lines.append(f"_{phen[v]}_")
            lines.append("")
        lines.append(f"![badge default](proofset/{g}/variants/badge_pypi_{v}_default.svg)")
        if (OUT / "proofset" / g / "variants" / f"badge_pypi_{v}_compact.svg").exists():
            lines.append(f" ![badge compact](proofset/{g}/variants/badge_pypi_{v}_compact.svg)")
        lines.append("")
        lines.append(
            f"![icon circle](proofset/{g}/variants/icon_github_{v}_circle.svg) "
            f"![icon square](proofset/{g}/variants/icon_github_{v}_square.svg)"
        )
        lines.append("")
        lines.append(f"![strip](proofset/{g}/variants/strip_{v}.svg)")
        lines.append("")
        lines.append(f"![marquee](proofset/{g}/variants/marquee_horizontal_{v}.svg)")
        lines.append("")
        lines.append(f"![divider aura](proofset/{g}/variants/divider_aura_{v}.svg)")
        lines.append("")
        if (OUT / "proofset" / g / "variants" / f"stats_{v}.svg").exists():
            lines.append(f"![stats](proofset/{g}/variants/stats_{v}.svg)")
            lines.append("")
        if (OUT / "proofset" / g / "variants" / f"chart_stars_{v}.svg").exists():
            lines.append(f"![chart](proofset/{g}/variants/chart_stars_{v}.svg)")
            lines.append("")
        _states = (
            ArtifactStatus.PASSING,
            ArtifactStatus.WARNING,
            ArtifactStatus.CRITICAL,
            ArtifactStatus.BUILDING,
            ArtifactStatus.OFFLINE,
        )
        for s in _states:
            lines.append(f"![{s.value}](proofset/{g}/variants/badge_{s.value}_{v}.svg)")
        lines.append("")
        if (OUT / "proofset" / g / "variants" / f"badge_passing_{v}_compact.svg").exists():
            lines.append("**Compact (20px) across states:**")
            lines.append("")
            for s in _states:
                lines.append(f"![{s.value} compact](proofset/{g}/variants/badge_{s.value}_{v}_compact.svg)")
            lines.append("")
        lines.append("---")
        lines.append("")

    dark = [v for v in cfg.variants if (overrides.get(v) or {}).get("substrate_kind") == "dark"]
    light = [v for v in cfg.variants if (overrides.get(v) or {}).get("substrate_kind") == "light"]
    for v in dark:
        _emit(v)
    lines.append("## Light Substrates")
    lines.append("")
    for v in light:
        _emit(v)

    lines.extend(_emit_primer_stress_section())

    lines.extend(
        [
            "## Substrate Architecture",
            "",
            "`substrate_kind` is the variant-declared axis driving template include dispatch "
            "within the primer paradigm:",
            "",
            "```jinja2",
            "{# templates/frames/badge/primer-content.j2 (dispatcher) #}",
            '{% include "frames/badge/primer-" ~ (substrate_kind | default(\'light\')) ~ "-content.j2" %}',
            "```",
            "",
            "Dark variants route to `primer-dark-content.j2`; light variants to "
            "`primer-light-content.j2` (badge, strip, icon, marquee). The aura divider is "
            "substrate-invariant — one template, per-variant `--dna-*` overrides carry the hue. "
            "The fallback is `light` (primer's flagship is porcelain), and a bare `?genome=primer` "
            "resolves its substrate from `category: light`.",
            "",
            "Stats and chart now use first-class primer layout paths: Inter editorial "
            "stats cards, smooth area charts, and circular chart endpoints all flow "
            "through the same resolver/layout/template pipeline as the other frames.",
            "",
            "## Cross-reference",
            "",
            "- [Main README](../README.md) — installation, compose grammar, all genomes",
            "- [CHANGELOG](../CHANGELOG.md) — v0.4.0-alpha.1 release notes",
            "",
        ]
    )

    (OUT / "README_PRIMER.md").write_text("\n".join(lines) + "\n")


def _matrix_fixture_specs() -> dict[str, dict[str, Any]]:
    """The six canonical sub-variant specs: five JSON fixtures shared with the
    test suite + the connectors matrix generated from the registry."""
    import json as _json

    from hyperweave.compose.matrix_input import build_connector_registry_matrix
    from hyperweave.config.loader import load_connector_registry

    fixtures_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "matrix"
    specs = {p.stem: _json.loads(p.read_text()) for p in sorted(fixtures_dir.glob("*.json"))}
    specs["connectors"] = build_connector_registry_matrix(load_connector_registry()).model_dump(mode="json")
    return specs


def _matrix_edge_specs() -> dict[str, dict[str, Any]]:
    """The boundary suite: the specimens prove "does it look right"; these
    prove "does it break". Dimension, content, structural, and
    type-isolation boundaries — every render is eyeballed in
    README_MATRIX.md. Boundaries carry REAL-SHAPED data (actual metric
    names, plausible values) so the geometry stays judgeable even when the
    structure is deliberately degenerate.
    """
    edge: dict[str, dict[str, Any]] = {}
    # ── Dimension boundaries (structural proof, not design targets) ──
    edge["dim-single-row"] = {
        "title": "Single row",
        "subtitle": "one model across five gauged benchmarks — heat needs no neighbors",
        "row_glyph_tint": "brand",
        "columns": [
            {"id": "model", "label": "MODEL", "role": "label"},
            {"id": "mmlu", "label": "MMLU", "sublabel": "↑ higher", "kind": "numeric", "polarity": "higher"},
            {"id": "gsm", "label": "GSM8K", "sublabel": "↑ higher", "kind": "numeric", "polarity": "higher"},
            {"id": "human", "label": "HumanEval", "sublabel": "↑ higher", "kind": "numeric", "polarity": "higher"},
            {"id": "math", "label": "MATH", "sublabel": "↑ higher", "kind": "numeric", "polarity": "higher"},
            {
                "id": "price",
                "label": "$/Mtok",
                "sublabel": "↓ lower",
                "kind": "numeric",
                "polarity": "lower",
                "unit": "$",
            },
        ],
        "rows": [
            {
                "label": "Claude 3.5 Sonnet",
                "glyph": "anthropic",
                "cells": [{"value": 88.7}, {"value": 96.4}, {"value": 92.0}, {"value": 71.1}, {"value": 3.0}],
            }
        ],
    }
    edge["dim-single-col"] = {
        "title": "Single column",
        "subtitle": "one artifact, tri-state support per surface — dual-coded marks down a column",
        "columns": [
            {"id": "surface", "label": "SURFACE", "role": "label"},
            {"id": "svg", "label": "SVG support", "kind": "check"},
        ],
        "rows": [
            {"label": "GitHub README", "cells": [{"state": "full"}]},
            {"label": "GitHub PR / issue body", "cells": [{"state": "full"}]},
            {"label": "Notion embed", "cells": [{"state": "partial"}]},
            {"label": "Slack link preview", "cells": [{"state": "partial"}]},
            {"label": "Gmail body", "cells": [{"state": "none"}]},
            {"label": "VS Code markdown preview", "cells": [{"state": "full"}]},
        ],
    }
    edge["dim-1x1"] = {
        "title": "True minimum",
        "subtitle": "one cell still carries a semantic mark",
        "columns": [{"id": "svg", "label": "Renders in README", "kind": "check"}],
        "rows": [{"label": "hyperweave SVG", "cells": [{"state": "full"}]}],
    }
    _ENDPOINTS = [
        "badge",
        "strip",
        "icon",
        "divider",
        "marquee",
        "stats",
        "chart",
        "matrix",
        "compose",
        "frames",
        "health",
        "kit",
        "live",
        "discover",
        "genomes",
        "motions",
    ]
    edge["dim-soft-cap-16"] = {
        "title": "Soft cap",
        "subtitle": "16 rows of gauged latency — type and pitch tighten one step",
        "unit": "ms",
        "columns": [
            {"id": "route", "label": "ROUTE", "role": "label"},
            {"id": "p50", "label": "p50", "kind": "numeric", "polarity": "lower"},
            {"id": "p95", "label": "p95", "kind": "numeric", "polarity": "lower"},
        ],
        "rows": [
            {"label": f"GET /v1/{name}", "cells": [{"value": 8 + i * 3}, {"value": 21 + i * 7}]}
            for i, name in enumerate(_ENDPOINTS)
        ],
    }
    _SURFACES = [
        ("GitHub README", "full", "full"),
        ("GitHub PR / issue body", "full", "full"),
        ("GitHub wiki", "full", "partial"),
        ("GitHub gist", "full", "partial"),
        ("GitHub Pages", "full", "full"),
        ("GitLab README", "full", "partial"),
        ("Bitbucket README", "partial", "none"),
        ("npm package page", "full", "none"),
        ("PyPI project page", "full", "none"),
        ("crates.io readme", "partial", "none"),
        ("Notion embed", "partial", "none"),
        ("Obsidian vault", "full", "partial"),
        ("Slack link preview", "partial", "none"),
        ("Discord embed", "partial", "none"),
        ("VS Code markdown preview", "full", "partial"),
        ("JetBrains markdown", "full", "none"),
        ("Linear issue", "partial", "none"),
        ("Jira description", "none", "none"),
        ("Confluence page", "partial", "none"),
        ("Reddit post", "none", "none"),
        ("X / Twitter card", "none", "none"),
        ("Bluesky embed", "none", "none"),
        ("Mastodon preview", "partial", "none"),
        ("Apple Mail", "partial", "none"),
        ("Gmail body", "none", "none"),
        ("Outlook body", "none", "none"),
        ("Docusaurus site", "full", "full"),
        ("MkDocs site", "full", "full"),
        ("Sphinx docs", "full", "partial"),
        ("Hugo site", "full", "full"),
    ]
    edge["dim-hard-cap-30"] = {
        "title": "Hard cap",
        "subtitle": "a 30-surface support matrix — the ceiling still renders; 31 raises",
        "columns": [
            {"id": "surface", "label": "SURFACE", "role": "label"},
            {"id": "renders", "label": "Renders", "kind": "check"},
            {"id": "animates", "label": "Animates", "kind": "check"},
        ],
        "rows": [
            {"label": name, "cells": [{"state": renders}, {"state": animates}]} for name, renders, animates in _SURFACES
        ],
    }
    _EVALS = [
        ("mmlu", "MMLU", "higher"),
        ("gsm", "GSM8K", "higher"),
        ("human", "HumanEval", "higher"),
        ("math", "MATH", "higher"),
        ("gpqa", "GPQA", "higher"),
        ("mgsm", "MGSM", "higher"),
        ("drop", "DROP", "higher"),
        ("price", "$/Mtok", "lower"),
    ]
    _MODELS = [
        ("Claude 3.5 Sonnet", "anthropic", [88.7, 96.4, 92.0, 71.1, 59.4, 91.6, 87.1, 3.0]),
        ("GPT-4o", "openai", [88.7, 95.8, 90.2, 76.6, 53.6, 90.5, 83.4, 2.5]),
        ("Gemini 1.5 Pro", "gemini", [85.9, 91.7, 84.1, 67.7, 46.2, 88.7, 78.9, 1.25]),
        ("Qwen2.5-72B", "qwen", [86.1, 91.5, 86.6, 83.1, 49.0, 89.3, 76.7, 0.4]),
    ]
    edge["dim-max-cols-8"] = {
        "title": "Max columns",
        "subtitle": "a wall of gauged tiles — eight heat columns compress toward equal widths",
        "row_glyph_tint": "brand",
        "columns": [{"id": "model", "label": "MODEL", "role": "label"}]
        + [
            {
                "id": cid,
                "label": label,
                "sublabel": "↑ higher" if pol == "higher" else "↓ lower",
                "kind": "numeric",
                "polarity": pol,
            }
            for cid, label, pol in _EVALS
        ],
        "rows": [
            {"label": name, "glyph": glyph, "cells": [{"value": v} for v in values]} for name, glyph, values in _MODELS
        ],
    }
    edge["dim-label-floor"] = {
        "title": "Label column squeezed to its floor",
        "columns": [{"id": "l", "label": "CAPABILITY", "role": "label"}]
        + [{"id": f"c{j}", "label": f"TARGET {j + 1}", "kind": "check"} for j in range(6)],
        "rows": [
            {
                "label": "An extremely long capability label that must truncate with a measured ellipsis",
                "cells": [{"state": s} for s in ("full", "partial", "none", "full", "partial", "none")],
            }
            for _ in range(4)
        ],
    }
    # ── Cell content boundaries ──
    edge["content-chip-overflow-cap"] = {
        "title": "Chip overflow past the four-row cap",
        "subtitle": "chips always wrap; +N appears only when even four rows cannot hold them",
        "columns": [
            {"id": "pkg", "label": "PACKAGE", "role": "label"},
            {"id": "deps", "label": "DEPENDENCIES", "kind": "chip"},
            {"id": "lock", "label": "LOCKED", "kind": "pill"},
        ],
        "rows": [
            {
                "label": "hyperweave",
                "sublabel": "pyproject",
                "cells": [
                    {
                        "chips": [
                            "fastapi",
                            "pydantic",
                            "jinja2",
                            "typer",
                            "uvicorn",
                            "httpx",
                            "pyyaml",
                            "fastmcp",
                            "rich",
                            "anyio",
                            "starlette",
                            "click",
                            "fonttools",
                            "pillow",
                            "certifi",
                            "idna",
                            "sniffio",
                            "h11",
                            "httpcore",
                            "annotated-types",
                            "typing-extensions",
                            "markupsafe",
                            "shellingham",
                            "pygments",
                            "mdurl",
                            "markdown-it-py",
                            "python-multipart",
                            "websockets",
                            "watchfiles",
                            "httptools",
                            "uvloop",
                            "orjson",
                            "ujson",
                            "email-validator",
                            "dnspython",
                            "itsdangerous",
                            "pyperclip",
                            "docutils",
                            "packaging",
                            "six",
                        ]
                    },
                    {"state": "on"},
                ],
            }
        ],
    }
    edge["content-text-wrap-cap"] = {
        "title": "Long values wrap",
        "subtitle": "full commit subjects against narrow columns — wrap first, ellipsis last",
        "columns": [
            {"id": "sha", "label": "COMMIT", "role": "label"},
            {"id": "subject", "label": "SUBJECT", "kind": "text", "width": 150},
            {"id": "body", "label": "BODY", "kind": "text", "width": 150},
        ],
        "rows": [
            {
                "label": "1e15d4f",
                "cells": [
                    {"value": "docs: update README assets after the proofset regeneration pass"},
                    {
                        "value": "Regenerates every embedded artifact, refreshes the parity manifest, "
                        "re-runs the raster verification harness across all eight primer variants, "
                        "and pins the new solved widths in the acceptance README"
                    },
                ],
            },
            {
                "label": "4867b34",
                "cells": [
                    {"value": "feat: primer genome across all seven existing frame types"},
                    {"value": "Badge, strip, chart, stats, icon, marquee and divider all dispatch primer"},
                ],
            },
            {
                "label": "0059902",
                "cells": [
                    {"value": "fix: strip layout engine cell padding on chrome variants"},
                    {"value": "Cell padding now solves from the paradigm config"},
                ],
            },
        ],
    }
    edge["content-bar-identical"] = {
        "title": "Bars with identical values",
        "subtitle": "no differentiation to gauge — every bar fills alike",
        "unit": "ms",
        "columns": [
            {"id": "region", "label": "REGION", "role": "label"},
            {"id": "p50", "label": "p50 latency", "kind": "bar", "polarity": "lower"},
        ],
        "rows": [
            {"label": region, "cells": [{"value": 250}]} for region in ("us-east", "eu-west", "ap-south", "sa-east")
        ],
    }
    edge["content-bar-zero"] = {
        "title": "Bar containing a zero",
        "unit": "tok",
        "columns": [
            {"id": "path", "label": "CACHE PATH", "role": "label"},
            {"id": "tok", "label": "Tokens fetched", "kind": "bar"},
        ],
        "rows": [
            {"label": "warm cache hit", "cells": [{"value": 0}]},
            {"label": "cold fetch", "cells": [{"value": 1800}]},
        ],
    }
    edge["content-scattered-empty"] = {
        "title": "Scattered empty cells",
        "subtitle": "missing connector values stay blank, never fabricated",
        "columns": [
            {"id": "pkg", "label": "PACKAGE", "role": "label"},
            {"id": "pypi", "label": "PyPI DLs"},
            {"id": "npm", "label": "npm DLs"},
            {"id": "crates", "label": "Crates DLs"},
        ],
        "rows": [
            {"label": "hyperweave", "cells": [{"value": 4100}, {}, {}]},
            {"label": "readme-ai", "cells": [{"value": 9100}, {"value": 1200}, {}]},
            {"label": "svg-forge", "cells": [{}, {}, {"value": 880}]},
        ],
    }
    edge["content-empty-row"] = {
        "title": "One fully-empty row",
        "subtitle": "a package no connector resolves",
        "columns": [
            {"id": "pkg", "label": "PACKAGE", "role": "label"},
            {"id": "ver", "label": "Version"},
            {"id": "dls", "label": "Downloads"},
        ],
        "rows": [
            {"label": "hyperweave", "cells": [{"value": "0.4.0a2"}, {"value": 4100}]},
            {"label": "ghost-package", "cells": [{}, {}]},
            {"label": "readme-ai", "cells": [{"value": "3.2.1"}, {"value": 9100}]},
        ],
    }
    # ── Structural boundaries (each rhetoric block independently omitted) ──
    edge["struct-no-title"] = {
        "title": "",
        "columns": [
            {"id": "fmt", "label": "FORMAT", "role": "label"},
            {"id": "size", "label": "Size KB"},
            {"id": "tokens", "label": "Tokens"},
        ],
        "rows": [
            {"label": "raw SVG", "cells": [{"value": 44}, {"value": 3420}]},
            {"label": "hw:payload", "cells": [{"value": 2}, {"value": 480}]},
            {"label": "hwz/1 envelope", "cells": [{"value": 1}, {"value": 210}]},
        ],
    }
    edge["struct-no-sections"] = {
        "title": "Flat rows (no sections)",
        "columns": [
            {"id": "field", "label": "FIELD", "role": "label"},
            {"id": "naked", "label": "Naked", "kind": "dot"},
            {"id": "resonant", "label": "Resonant", "kind": "dot"},
        ],
        "rows": [
            {"label": "title", "cells": [{"state": "on"}, {"state": "on"}]},
            {"label": "created", "cells": [{"state": "on"}, {"state": "on"}]},
            {"label": "aesthetic", "cells": [{"state": "on"}, {"state": "off"}]},
            {"label": "reasoning", "cells": [{"state": "off"}, {"state": "on"}]},
        ],
    }
    edge["struct-no-headline"] = {
        "title": "Bar scale without a headline chip",
        "unit": "tok",
        "columns": [
            {"id": "form", "label": "REPRESENTATION", "role": "label"},
            {"id": "tok", "label": "Tokens", "kind": "bar", "polarity": "lower"},
        ],
        "rows": [
            {"label": "raw SVG source", "cells": [{"value": 3420}]},
            {"label": "hw:payload", "cells": [{"value": 480}]},
            {"label": "hwz/1 envelope", "cells": [{"value": 210}]},
        ],
    }
    edge["struct-no-summary"] = {
        "title": "Checks without a score band",
        "columns": [{"id": "cap", "label": "CAPABILITY", "role": "label"}]
        + [{"id": c, "label": c.upper(), "kind": "check"} for c in ("svg", "png")],
        "rows": [
            {"label": "Animation", "cells": [{"state": "full"}, {"state": "none"}]},
            {"label": "Crisp at any scale", "cells": [{"state": "full"}, {"state": "none"}]},
        ],
    }
    edge["struct-no-hero"] = {
        "title": "Pills without a recommended column",
        "columns": [{"id": "f", "label": "FEATURE", "role": "label"}]
        + [{"id": p, "label": p.title(), "kind": "pill"} for p in ("free", "pro")],
        "rows": [
            {"label": "API access", "cells": [{"value": False}, {"value": True}]},
            {"label": "SSO / SAML", "cells": [{"value": False}, {"value": True}]},
        ],
    }
    edge["struct-everything"] = {
        "title": "Everything at once",
        "subtitle": "headline + sections + hero + summary + axis + emphasis, composed",
        "unit": "pts",
        "hero_column": "b",
        "headline": {"value": "3x", "label": "hero over baseline"},
        "sections": ["First", "Second"],
        "summary_label": "TOTAL",
        "columns": [
            {"id": "l", "label": "ITEM", "role": "label"},
            {"id": "a", "label": "Baseline", "kind": "bar"},
            {"id": "b", "label": "Hero", "kind": "bar"},
        ],
        "rows": [
            {"label": "alpha", "section": "First", "cells": [{"value": 10}, {"value": 30}]},
            {"label": "beta", "section": "First", "emphasis": True, "cells": [{"value": 12}, {"value": 36}]},
            {"label": "gamma", "section": "Second", "cells": [{"value": 8}, {"value": 24}]},
        ],
        "summary_row": [{"value": "30"}, {"value": "90"}],
    }
    # ── Type isolation: one matrix per cell kind as the sole data column ──
    iso_rows = [("alpha", 0), ("beta", 1), ("gamma", 2)]
    edge["iso-text"] = {
        "title": "Isolation: text",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "NOTE", "kind": "text"}],
        "rows": [{"label": n, "cells": [{"value": f"note {i}"}]} for n, i in iso_rows],
    }
    edge["iso-check"] = {
        "title": "Isolation: check",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "STATE", "kind": "check"}],
        "rows": [
            {"label": n, "cells": [{"state": s}]}
            for (n, _), s in zip(iso_rows, ("full", "partial", "none"), strict=True)
        ],
    }
    edge["iso-dot"] = {
        "title": "Isolation: dot",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "TIER", "kind": "dot"}],
        "rows": [{"label": n, "cells": [{"state": "on" if i % 2 == 0 else "off"}]} for n, i in iso_rows],
    }
    edge["iso-bar"] = {
        "title": "Isolation: bar",
        "unit": "tok",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "Tokens", "kind": "bar"}],
        "rows": [{"label": n, "cells": [{"value": (i + 1) * 700}]} for n, i in iso_rows],
    }
    edge["iso-pill"] = {
        "title": "Isolation: pill",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "READY", "kind": "pill"}],
        "rows": [{"label": n, "cells": [{"value": i % 2 == 0}]} for n, i in iso_rows],
    }
    edge["iso-numeric"] = {
        "title": "Isolation: numeric heat",
        "columns": [
            {"id": "l", "label": "ROW", "role": "label"},
            {"id": "v", "label": "Score", "kind": "numeric", "polarity": "higher"},
        ],
        "rows": [{"label": n, "cells": [{"value": 60 + i * 18}]} for n, i in iso_rows],
    }
    edge["iso-chip"] = {
        "title": "Isolation: chip",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "TAGS", "kind": "chip"}],
        "rows": [{"label": n, "cells": [{"chips": [f"tag_{i}_{k}" for k in range(i + 2)]}]} for n, i in iso_rows],
    }
    edge["iso-glyph"] = {
        "title": "Isolation: glyph",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "MARK", "kind": "glyph"}],
        "rows": [
            {"label": n, "cells": [{"glyph": g}]}
            for (n, _), g in zip(iso_rows, ("github", "pypi", "huggingface"), strict=True)
        ],
    }
    return edge


_MATRIX_EDGE_NOTES: dict[str, str] = {
    "dim-single-row": "Tests: one model row across five gauged heat columns — column normalization "
    "with no neighbors. Correct: every tile reads the neutral mid hue (a range of one has no poles) "
    "and the frame solves to its natural width.",
    "dim-single-col": "Tests: one data column — the solver with nothing to balance against. Correct: "
    "the check column floors, the legend stays inline beside the subtitle, marks stay centered.",
    "dim-1x1": "Tests: the true minimum input (one row, one column). Correct: a complete card — "
    "masthead, headers, one mark, footer — at the width floor.",
    "dim-soft-cap-16": "Tests: 16 rows, the soft cap — the shrink step. Correct: the type drops one "
    "step and the pitch tightens; nothing clips.",
    "dim-hard-cap-30": "Tests: 30 rows, the hard cap — the engine's last legal input. Correct: every "
    "row still renders at compact pitch; row 31 raises instead.",
    "dim-max-cols-8": "Tests: 8 data columns, the column cap — maximum horizontal compression. "
    "Correct: columns compress toward their floors with no negative widths and no header collisions.",
    "dim-label-floor": "Tests: six data columns squeezing the label column to its floor. Correct: row "
    "labels truncate with a measured ellipsis; the key takes its own row under the wide title.",
    "content-text-wrap-cap": "Tests: prose against narrow text columns. Correct: values wrap up to "
    "three lines (rows grow to fit), and the ellipsis appears only on the final line of content that "
    "exceeds the cap — never as the first behavior.",
    "content-chip-overflow-cap": "Tests: a 40-dependency chip list against the four-row cap. Correct: "
    "chips pack and wrap; past the cap one `+N` chip absorbs the remainder (the full list stays in "
    "hw:payload).",
    "content-bar-identical": "Tests: every bar the same value — a range with no spread. Correct: all "
    "bars fill alike to the axis max; no fake differentiation.",
    "content-bar-zero": "Tests: a zero value on a bar scale. Correct: the zero keeps a minimum visible "
    "ink sliver against its track, and the axis still spans 0 to max.",
    "content-scattered-empty": "Tests: null/empty cells scattered through a populated table. Correct: "
    "empty cells render honest em-dashes — no invented zeros, no collapsed columns.",
    "content-empty-row": "Tests: one row with every cell empty. Correct: the row keeps its pitch and "
    "label; the cells stay quiet dashes.",
    "struct-no-title": "Tests: no title, subtitle, or headline at all. Correct: the masthead collapses "
    "entirely — the table starts near the top with no rail, scan, or legend.",
    "struct-no-sections": "Tests: flat rows with no section grouping, with NON-nested dot columns "
    "(inclusion sets that are not subsets of each other — the tier-dot fallback). Correct: the per-cell "
    "dot grid with extent bars and the included/omitted key, never spans; no bands, no indent, the "
    "primary row-title voice.",
    "struct-no-headline": "Tests: a bar matrix without the headline chip (top-right score badge). "
    "Correct: the masthead carries title and rail only; the axis still closes the scale.",
    "struct-no-hero": "Tests: a pill table without a recommended column. Correct: no hero lane, no cap "
    "tab — all columns carry equal visual weight.",
    "struct-no-summary": "Tests: omitting the summary row. Correct: the table closes at its last row; "
    "no empty score band reserves space.",
    "struct-everything": "Tests: every rhetoric block at once — headline chip, sections, hero lane, "
    "summary row, row emphasis — composed in one artifact. Correct: each block keeps its own zone "
    "(chip on the title line, bands behind rows, lane behind the hero column, score band before the "
    "footer) with zero collisions.",
    "iso-text": "Tests: text as the sole data column — the rendered CellPlacement leak test. Correct: "
    "text runs only; zero mark/dot/bar/pill/tile/chip/glyph markup.",
    "iso-check": "Tests: check marks as the sole kind. Correct: tri-valence vector marks and their "
    "masthead key only; no other kind's markup anywhere.",
    "iso-dot": "Tests: dots as the sole kind. Correct: filled/hollow dots and their key only; no other kind's markup.",
    "iso-bar": "Tests: bars as the sole kind. Correct: tracks, fills, and the shared axis only; no "
    "other kind's markup.",
    "iso-pill": "Tests: pills as the sole kind. Correct: capsule geometry only (gradient Yes, neutral "
    "values); no other kind's markup.",
    "iso-numeric": "Tests: numeric heat as the sole kind. Correct: column washes, tinted values, and "
    "gauged underlines only; no other kind's markup.",
    "iso-chip": "Tests: chips as the sole kind. Correct: packed chip capsules only; no other kind's markup.",
    "iso-glyph": "Tests: registry glyphs as the sole kind. Correct: brand marks only — and unknown "
    "registry ids fail loud at compose time, never silently.",
}


def _emit_matrix_readme() -> None:
    """Emit outputs/README_MATRIX.md + render the matrix proofset.

    Two halves, both required: the six sub-variant fixtures across primer
    variants prove "does it look right" against the porcelain-final
    specimens; the boundary suite proves "does it break" at the edges of
    the input space (dimension, content, structural, type isolation). The
    over-hard-cap entry intentionally raises and embeds the SMPTE error
    artifact a README embedder would actually see.
    """
    from hyperweave.compose.engine import compose as _do_compose
    from hyperweave.core.matrix import MatrixCapacityError
    from hyperweave.serve.app import _error_badge

    out_dir = OUT / "proofset" / "primer" / "matrix"
    out_dir.mkdir(parents=True, exist_ok=True)
    fixtures = _matrix_fixture_specs()
    variants = ["noir", "carbon", "space", "anvil", "porcelain", "cream", "dusk", "petrol"]

    def render(name: str, spec: dict[str, Any], variant: str = "porcelain") -> str:
        svg = _compose("matrix", "primer", variant=variant, matrix=spec)
        fname = f"{name}_{variant}.svg"
        _write(out_dir / fname, svg)
        return fname

    lines: list[str] = [
        "# HyperWeave Matrix — Sub-Variants + Boundary Suite",
        "",
        "One generative frame renders every structured table: columns declare a",
        "cell kind (`text · check · dot · bar · pill · numeric · chip · glyph`),",
        "a measured solver places every coordinate, and each artifact embeds its",
        "lossless `hw:payload` (matrix/1), an `hwz/1` envelope, and a GFM markdown",
        "shadow. The specimens prove *does it look right*; the boundary suite",
        "proves *does it break*. Both are required — this file is the acceptance",
        "surface.",
        "",
        "---",
        "",
        "## Sub-variants (porcelain)",
        "",
    ]
    captions = {
        "check": "Scored comparison — tri-valence marks, hero lane, score band, masthead legend.",
        "connectors": "Registry — row glyphs, packed metric chips with `+N` overflow, status pills, "
        "content-height rows. Generated from `data/connector_registry.yaml`.",
        "tiers": "Progressive inclusion — chained sets auto-select the tier-span projection: "
        "reach bars with terminal dots (3 spans for 27 marks), hero tier through the USE-FOR row, "
        "a one-entry tier-reach key. Non-nested dot data keeps the tier-dot grid.",
        "readcost": "Bar scale — shared axis with nice ticks, value column, load-bearing headline chip.",
        "plans": "Pill tags — emerald Yes capsules, neutral value capsules, recommended-column hero lane.",
        "benchmark": "Numeric heat — diverging teal-rose tiles, gauged underlines, brand-tinted row "
        "glyphs (Gemini's gradient spark).",
    }
    for name in ("check", "connectors", "tiers", "readcost", "plans", "benchmark"):
        fname = render(name, fixtures[name])
        lines += [f"### {name}", "", captions[name], "", f"![{name}](proofset/primer/matrix/{fname})", ""]

    lines += [
        "---",
        "",
        "## Substrate derivation (check across the other seven variants)",
        "",
        "The chassis is entirely `--dna-*`; the semantic indicator hues are",
        "genome-invariant (one hue per state, bright enough for both poles).",
        "",
    ]
    for variant in variants:
        if variant == "porcelain":
            continue
        fname = render("check", fixtures["check"], variant=variant)
        lines += [f"**{variant}**", "", f"![check-{variant}](proofset/primer/matrix/{fname})", ""]

    edge = _matrix_edge_specs()
    groups = [
        (
            "Dimension boundaries",
            "dim-",
            "*Structural proof at the dimensional limits — filled with payloads that "
            "exercise the cell kinds the matrix was built for (heat, checks, "
            "gauges), so the boundary render still earns the frame.*",
        ),
        (
            "Cell content boundaries",
            "content-",
            "*Packing, truncation, gauge degeneracy, and honest emptiness — the "
            "cell builders at the edges of their input space.*",
        ),
        (
            "Structural boundaries",
            "struct-",
            "*Each rhetoric block independently omitted (empty slots release "
            "their space), then everything composed at once.*",
        ),
        (
            "Type isolation (one kind per matrix — the visual CellPlacement leak test)",
            "iso-",
            "",
        ),
    ]
    lines += ["---", "", "## Boundary suite", ""]
    for heading, prefix, note in groups:
        lines += [f"### {heading}", ""]
        if note:
            lines += [note, ""]
        for name, spec in edge.items():
            if not name.startswith(prefix):
                continue
            fname = render(name, spec)
            lines += [
                f"### {name}",
                "",
                _MATRIX_EDGE_NOTES[name],
                "",
                f"![{name}](proofset/primer/matrix/{fname})",
                "",
            ]
        if prefix == "dim-":
            # Over-hard-cap: compose() raises; the embedder-visible artifact is
            # the SMPTE badge GET serves at HTTP 200 / X-HW-Error-Code: 422.
            over = {
                "title": "Over cap",
                "columns": [{"id": "v", "label": "V"}],
                "rows": [{"label": f"r{i}", "cells": [{"value": i}]} for i in range(31)],
            }
            try:
                _compose("matrix", "primer", variant="porcelain", matrix=over)
                raise AssertionError("31-row matrix must raise MatrixCapacityError")
            except MatrixCapacityError as exc:
                _write(out_dir / "dim-over-cap-31_porcelain.svg", _error_badge(str(exc), status_code=422))
                lines += [
                    "### dim-over-cap-31",
                    "",
                    "Tests: 31 rows, one past the hard cap. Correct: `compose()` raises",
                    "`MatrixCapacityError`; image surfaces serve this SMPTE artifact at",
                    "HTTP 200 / `X-HW-Error-Code: 422`:",
                    "",
                    f"> `{exc}`",
                    "",
                    "![dim-over-cap-31](proofset/primer/matrix/dim-over-cap-31_porcelain.svg)",
                    "",
                ]

    check_result = _do_compose(
        ComposeSpec(type="matrix", genome_id="primer", variant="porcelain", matrix=fixtures["check"])
    )
    lines += [
        "---",
        "",
        "## The markdown shadow",
        "",
        "Every matrix also projects to a GFM table (`--markdown-out` on the CLI,",
        '`respond: "json"` on POST /v1/compose, `render_target="markdown"` on MCP).',
        "This is the check fixture's actual shadow:",
        "",
        "<details><summary>check.md</summary>",
        "",
        check_result.markdown.rstrip(),
        "",
        "</details>",
        "",
        "---",
        "",
        "Cross-references:",
        "",
        "- [README_PRIMER](README_PRIMER.md) — the 8-variant substrate matrix",
        "- [Main README](../README.md) — installation, compose grammar, all genomes",
        "",
    ]
    (OUT / "README_MATRIX.md").write_text("\n".join(lines) + "\n")


def _emit_chrome_readme() -> None:
    """Emit outputs/README_CHROME.md mirroring brutalist/automata structure.

    Chrome ships 5 named variants (horizon/abyssal/lightning/graphite/moth);
    each renders the full artifact suite. Chrome's divider variant is `band`
    (per genome.dividers, distinct from brutalist `seam` and automata
    `dissolve`). Chrome supports both circular AND square icon shapes, so
    each variant block embeds both alongside the standard 12-artifact suite.

    Source data: `eli64s/readme-ai` to match the other two genome READMEs.
    Image refs point at LOCAL artifacts under outputs/proofset/chrome/.
    """
    g = "chrome"
    cfg = load_genomes().get(g)
    if cfg is None or not cfg.variants:
        return

    lines: list[str] = [
        "# HyperWeave Chrome — 5-Variant Material Identity Matrix",
        "",
        "Chrome is the dark-envelope flagship: midnight gradient + slate seam + sparing "
        "warm-metal accents. Each variant changes the **material identity** of the envelope "
        "while keeping the same structural chrome (envelope + well + rim + rhythm).",
        "",
        "Five variants: **`horizon`** (frozen midnight + slate + copper sliver; flagship), "
        "**`abyssal`** (deep-water teal), **`lightning`** (electric blue), "
        "**`graphite`** (warm gray cast), **`moth`** (umber iridescence).",
        "",
        "The bare `chrome.static` URL renders `horizon` for byte-equality with pre-v0.3 "
        "output. Named variants emit per-variant chromatic overrides via inline SVG-root "
        "style — every chrome envelope is hex-baked into its `url(#-env)` gradient stops "
        "and is therefore **scheme-stable** (light-mode CSS variables do not invert the "
        "envelope; that bug was fixed in v0.3.9 by removing the inherited `light_mode` "
        "block from the chrome genome).",
        "",
        "Chrome supports both `circle` and `square` icon shapes; each variant embeds both. "
        "Every variant below renders the full artifact suite (default badge, circle + "
        "square icons, strip, marquee, band divider, stats card, star chart, 5 badge states).",
        "",
        "---",
        "",
    ]

    def _emit_variant_block(v: str, phenomenology: str) -> None:
        lines.append(f"### `?variant={v}`")
        lines.append("")
        lines.append(f"_{phenomenology}_")
        lines.append("")
        # Row 1: default badge
        lines.append(f"![badge default](proofset/{g}/variants/badge_pypi_{v}_default.svg)")
        lines.append("")
        # Row 2: icons (circle + square)
        lines.append(
            f"![icon circle](proofset/{g}/variants/icon_github_{v}_circle.svg) "
            f"![icon square](proofset/{g}/variants/icon_github_{v}_square.svg)"
        )
        lines.append("")
        # Row 3: strip
        lines.append(f"![strip](proofset/{g}/variants/strip_{v}.svg)")
        lines.append("")
        # Row 4: marquee
        lines.append(f"![marquee](proofset/{g}/variants/marquee_horizontal_{v}.svg)")
        lines.append("")
        # Row 5: band divider (chrome's only declared divider)
        lines.append(f"![divider band](proofset/{g}/variants/divider_band_{v}.svg)")
        lines.append("")
        # Row 6: stats card
        stats_path = OUT / "proofset" / g / "variants" / f"stats_{v}.svg"
        if stats_path.exists():
            lines.append(f"![stats](proofset/{g}/variants/stats_{v}.svg)")
            lines.append("")
        # Row 7: star history chart
        chart_path = OUT / "proofset" / g / "variants" / f"chart_stars_{v}.svg"
        if chart_path.exists():
            lines.append(f"![chart](proofset/{g}/variants/chart_stars_{v}.svg)")
            lines.append("")
        # Rows 8-12: badge states stacked
        for s in (
            ArtifactStatus.PASSING,
            ArtifactStatus.WARNING,
            ArtifactStatus.CRITICAL,
            ArtifactStatus.BUILDING,
            ArtifactStatus.OFFLINE,
        ):
            lines.append(f"![{s.value}](proofset/{g}/variants/badge_{s.value}_{v}.svg)")
        lines.append("")
        lines.append("---")
        lines.append("")

    for v, phen in _CHROME_PHENOMENOLOGY:
        if v in cfg.variants:
            _emit_variant_block(v, phen)

    lines.extend(
        [
            "## Material Architecture",
            "",
            "Chrome's identity lives in the hex-baked envelope gradient (a multi-stop "
            "`<linearGradient>` at `templates/frames/{frame}/chrome-defs.j2`), the well "
            "(content background), and the rim (specular highlight band). Per-variant "
            "overrides in `data/genomes/chrome.json:variant_overrides` swap the stops "
            "without touching the structural geometry.",
            "",
            "Light-mode behavior: chrome is **scheme-stable**. The genome no longer "
            "declares a `light_mode` block (v0.3.9), so the assembler emits no "
            "`@media (prefers-color-scheme: light)` swap CSS. Chrome strips/badges/"
            "icons render identically on dark and light GitHub READMEs. See "
            "`docs/decisions/chrome-lightmode-removal.md` for the diagnosis.",
            "",
            "## Cross-reference",
            "",
            "- [Main README](../README.md) — installation, compose grammar, all genomes",
            "- [Brutalist README](README_BRUTALIST.md) — 22-variant substrate matrix",
            "- [Automata README](README_AUTOMATA.md) — 16-tone cellular matrix",
            "",
        ]
    )

    (OUT / "README_CHROME.md").write_text("\n".join(lines) + "\n")


# DATA_PROJECTS — the real-data corpus the parity matrix exercises against.
# Tokens shape: ``(provider, identifier, metric)``. Resolved once via
# ``fetch_or_cache`` (live fetch with fixture cache fallback) and shared
# across all three entry points so byte-equality is testable.
#
# Project list per v0.3.9 plan Part 3c: 19 gh repos + 8 pypi + 4 npm +
# 4 docker + 3 hf + 3 arxiv. Each provides at least one scalar metric the
# harness pre-fetches at proofset start. Future spec entries can reference
# any pre-fetched token via the resolved_data dict.
DATA_PROJECTS: dict[str, list[tuple[str, ...]]] = {
    # Provider keys match ``hyperweave.connectors._CONNECTORS`` canonical
    # names (github / pypi / npm / docker / huggingface / arxiv). The
    # user-facing ``gh:`` / ``hf:`` aliases live in serve/data_tokens.py
    # and don't apply at the fetch_metric layer the harness uses.
    #
    # corpus refresh: 16 GitHub agentic repos relevant to
    # May 2026, 7 PyPI packages, 4 npm packages (scoped paths work via
    # registry.npmjs.org directly), 3 Docker images with pull + star
    # counts, 3 HuggingFace models with downloads + likes, 3 arXiv papers
    # (transformer-era + recent agentic). Replaces v0.3.8 corpus
    # (eli64s/readme-ai + DeepSeek-R1 + 2203.02155 etc).
    "github": [
        ("openclaw/openclaw", "stars"),
        ("openclaw/openclaw", "forks"),
        ("openclaw/openclaw", "issues"),
        ("NousResearch/hermes-agent", "stars"),
        ("NousResearch/hermes-agent", "forks"),
        ("JuliusBrussee/caveman", "stars"),
        ("JuliusBrussee/caveman", "forks"),
        ("mattpocock/skills", "stars"),
        ("mattpocock/skills", "forks"),
        ("langflow-ai/langflow", "stars"),
        ("langflow-ai/langflow", "forks"),
        ("langflow-ai/langflow", "issues"),
        ("langgenius/dify", "stars"),
        ("langgenius/dify", "forks"),
        ("langgenius/dify", "issues"),
        ("n8n-io/n8n", "stars"),
        ("n8n-io/n8n", "forks"),
        ("n8n-io/n8n", "issues"),
        ("Significant-Gravitas/AutoGPT", "stars"),
        ("Significant-Gravitas/AutoGPT", "forks"),
        ("Significant-Gravitas/AutoGPT", "issues"),
        ("ollama/ollama", "stars"),
        ("ollama/ollama", "forks"),
        ("cline/cline", "stars"),
        ("cline/cline", "forks"),
        ("mem0ai/mem0", "stars"),
        ("mem0ai/mem0", "forks"),
        ("crewAIInc/crewAI", "stars"),
        ("crewAIInc/crewAI", "forks"),
        ("langchain-ai/langchain", "stars"),
        ("langchain-ai/langchain", "forks"),
        ("langchain-ai/langchain", "issues"),
        ("anthropics/claude-code", "stars"),
        ("anthropics/claude-code", "forks"),
        ("vllm-project/vllm", "stars"),
        ("vllm-project/vllm", "forks"),
        ("vllm-project/vllm", "issues"),
        ("FoundationAgents/MetaGPT", "stars"),
        ("FoundationAgents/MetaGPT", "forks"),
        # Z.AI GLM-5 ecosystem (cross-provider showcase)
        ("zai-org/GLM-5", "stars"),
        ("zai-org/GLM-5", "forks"),
    ],
    "pypi": [
        ("langchain", "version"),
        ("langchain", "downloads"),
        ("vllm", "version"),
        ("vllm", "downloads"),
        ("crewai", "version"),
        ("crewai", "downloads"),
        ("dify-client", "version"),
        ("dify-client", "downloads"),
        ("readmeai", "version"),
        ("readmeai", "downloads"),
        ("mem0ai", "version"),
        ("mem0ai", "downloads"),
        ("hyperweave", "version"),
        ("hyperweave", "downloads"),
    ],
    "npm": [
        # Scoped packages (@scope/name) — registry.npmjs.org accepts the
        # unencoded path directly; httpx passes it through. Verified
        # 2026-05-20 against @langchain/langgraph, @anthropic-ai/sdk,
        # @openai/agents (all 200 OK).
        ("@langchain/langgraph", "version"),
        ("@langchain/langgraph", "downloads"),
        ("@anthropic-ai/sdk", "version"),
        ("@anthropic-ai/sdk", "downloads"),
        ("@openai/agents", "version"),
        ("@openai/agents", "downloads"),
        ("n8n", "version"),
        ("n8n", "downloads"),
    ],
    "docker": [
        # Docker Hub connector exposes pull_count + star_count.
        ("ollama/ollama", "pull_count"),
        ("ollama/ollama", "star_count"),
        ("vllm/vllm-openai", "pull_count"),
        ("vllm/vllm-openai", "star_count"),
        ("n8nio/n8n", "pull_count"),
        ("n8nio/n8n", "star_count"),
    ],
    "hf": [
        ("meta-llama/Llama-4-Scout-17B-16E-Instruct", "downloads"),
        ("meta-llama/Llama-4-Scout-17B-16E-Instruct", "likes"),
        ("NousResearch/Hermes-3-Llama-3.1-8B", "downloads"),
        ("NousResearch/Hermes-3-Llama-3.1-8B", "likes"),
        ("Qwen/Qwen3-235B-A22B", "downloads"),
        ("Qwen/Qwen3-235B-A22B", "likes"),
        # Z.AI GLM-5 model card (HuggingFace side).
        ("zai-org/GLM-5.1", "downloads"),
        ("zai-org/GLM-5.1", "likes"),
    ],
    "arxiv": [
        # 2310.06825: Mistral 7B paper.
        # 2501.12948: DeepSeek-R1 reasoning paper.
        # 2505.09388: recent agentic paper.
        # 2602.15763: Z.AI GLM-5 paper (R13).
        ("2310.06825", "title"),
        ("2310.06825", "authors"),
        ("2501.12948", "title"),
        ("2501.12948", "authors"),
        ("2505.09388", "title"),
        ("2505.09388", "authors"),
        ("2602.15763", "title"),
        ("2602.15763", "authors"),
    ],
    # v0.3.12 connectors. crates.io (Rust packages) + OpenSSF Scorecard
    # (supply-chain trust, keyless) + GitHub Actions DORA (computed delivery
    # metrics). tokio is reliably in the weekly Scorecard scan set, so score is
    # always present (a 404 from an unscanned repo would render nothing).
    "crates": [
        ("serde", "version"),
        ("serde", "downloads"),
        ("serde", "recent_downloads"),
        ("serde", "license"),
    ],
    "scorecard": [
        ("tokio-rs/tokio", "score"),
        ("tokio-rs/tokio", "code_review"),
        ("tokio-rs/tokio", "maintained"),
        ("tokio-rs/tokio", "token_permissions"),
        # Two distinct n/a causes covered by the all-Scorecard card:
        #   vulnerabilities — ABSENT from tokio's variable-length checks[]
        #   signed_releases — PRESENT but scored -1 (did not run / inconclusive)
        # Both must render "n/a", never 0 or a negative gauge.
        ("tokio-rs/tokio", "vulnerabilities"),
        ("tokio-rs/tokio", "signed_releases"),
    ],
    # DORA's paginated fan-out rides the isolated github-actions breaker, so a
    # rate-limit can't trip the badge/star github-core breaker. Needs
    # HW_GITHUB_TOKENS for a real value; degrades to "--" otherwise.
    "dora": [
        ("fastapi/fastapi", "deploy_frequency"),
    ],
}


def _fmt_count(value: Any) -> str:
    """Format a raw connector value as a compact display string.

    Strings (versions, titles) pass through unchanged. None/missing becomes
    ``--`` (v0.3.9: was ``?``; the new sentinel reads as 'unavailable' rather
    than 'unknown question'). Integers compact to ``k``/``M`` for badge
    readability. Sub-1000 fractional floats (OpenSSF Scorecard score 6.9, DORA
    rates 3.27) keep up to two decimals — these metrics are inherently
    non-integer and truncating them to int misrepresents the signal. The same
    formatter runs for direct/http/mcp inputs so all three paths render the
    identical value string.
    """
    if value is None:
        return "--"
    if isinstance(value, str):
        return value
    try:
        n = int(value)
    except (TypeError, ValueError):
        return str(value)
    # Preserve fractional precision for sub-1000 floats; integer-valued inputs
    # (incl. float 312.0) and large compacted counts keep their integer display.
    if isinstance(value, float) and value != n and abs(value) < 1_000:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


async def _resolve_data_projects(fixtures: dict[str, Any]) -> dict[str, Any]:
    """Pre-fetch every DATA_PROJECTS token; return ``{token: value}`` map.

    Each fetch is wrapped in ``fetch_or_cache`` so live failures fall back
    to the committed fixture cache. The harness persists the cache to
    ``tests/fixtures/proofset_data.json`` after every successful live fetch
    so subsequent runs (or CI without network) hit the cache instantly.
    Network resilience contract: a project missing from BOTH live and cache
    is a hard failure surfaced as ``?`` in the rendered output.
    """
    import asyncio as _asyncio

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from proofset_harness import fetch_or_cache

    async def _one(provider: str, identifier: str, metric: str) -> tuple[str, Any]:
        token = f"{provider}:{identifier}.{metric}"
        try:
            value = await fetch_or_cache(provider, identifier, metric, fixtures)
        except Exception as exc:
            print(f"  [DATA FETCH FAIL] {token}: {type(exc).__name__}: {exc}")
            value = None
        return token, value

    tasks = []
    for provider, items in DATA_PROJECTS.items():
        for identifier, metric in items:
            tasks.append(_one(provider, identifier, metric))

    results = await _asyncio.gather(*tasks)
    return dict(results)


def _build_parity_matrix(resolved_data: dict[str, Any] | None = None) -> list[Any]:
    """Construct the 3-path parity verification matrix.

    Each entry encodes the SAME compositional intent across all three entry
    points: ``ComposeSpec`` (direct), URL path + query string (HTTP), tool
    args (MCP). Equivalent inputs must produce byte-identical SVG output
    after volatile-fragment normalization — any divergence is a parity bug
    per HyperWeave Invariant 9 (CLI/HTTP/MCP feature parity).

    Coverage spans:
      - all 3 user-facing genomes (brutalist, chrome, automata)
      - all 7 user-facing frame types (badge, strip, icon, divider,
        marquee-horizontal, stats, chart)
      - state-bearing vs data-only strips (Bug 3 indicator gating)
      - varying metric counts (Bug 1 cell distribution + Bug 2 height inv)
      - variant query-param routing (chrome.horizon, automata.teal)
      - long-namespace via subtitle (Significant-Gravitas/AutoGPT)
      - **real-data via 6 live connectors** (gh, pypi, npm, docker, hf,
        arxiv) — values pre-fetched once and passed identically to all
        three paths so the parity check tests path-equivalence, not
        connector flakiness
      - literal connectors (text:, kv:)

    Matrix entries are constructed inline so future contributors see a
    template per archetype rather than parsing an opaque data structure.
    """
    from proofset_harness import ParitySpec

    rd = resolved_data or {}
    specs: list[Any] = []

    # ── Badges ──────────────────────────────────────────────────────────
    specs.append(
        ParitySpec(
            spec_id="brutalist-badge-build-passing",
            compose_spec=ComposeSpec(type="badge", genome_id="brutalist", title="build", value="passing"),
            http_path="/v1/badge/build/passing/brutalist.static",
            mcp_args={"type": "badge", "title": "build", "value": "passing", "genome": "brutalist"},
        )
    )
    specs.append(
        ParitySpec(
            spec_id="chrome-horizon-badge-version",
            compose_spec=ComposeSpec(
                type="badge",
                genome_id="chrome",
                variant="horizon",
                title="version",
                value="v0.3.9",
            ),
            http_path="/v1/badge/version/v0.3.9/chrome.static?variant=horizon",
            mcp_args={
                "type": "badge",
                "title": "version",
                "value": "v0.3.9",
                "genome": "chrome",
                "variant": "horizon",
            },
        )
    )
    specs.append(
        ParitySpec(
            spec_id="automata-teal-badge-stars",
            compose_spec=ComposeSpec(
                type="badge",
                genome_id="automata",
                variant="teal",
                title="stars",
                value="2.9k",
            ),
            http_path="/v1/badge/stars/2.9k/automata.static?variant=teal",
            mcp_args={
                "type": "badge",
                "title": "stars",
                "value": "2.9k",
                "genome": "automata",
                "variant": "teal",
            },
        )
    )

    # ── Strips: cell distribution + state-indicator gating ──────────────
    # Bug 1 (n metrics fill canvas) — 4 brutalist strips at counts 1/2/3/4.
    for n, metrics_csv in [
        (1, "STARS:2.9k"),
        (2, "STARS:2.9k,FORKS:278"),
        (3, "STARS:2.9k,FORKS:278,ISSUES:14"),
        (4, "STARS:2.9k,FORKS:278,ISSUES:14,PRS:7"),
    ]:
        specs.append(
            ParitySpec(
                spec_id=f"brutalist-strip-{n}metric-data-only",
                compose_spec=ComposeSpec(
                    type="strip",
                    genome_id="brutalist",
                    title="readme-ai",
                    value=metrics_csv,
                ),
                http_path=f"/v1/strip/readme-ai/brutalist.static?value={metrics_csv}",
                mcp_args={
                    "type": "strip",
                    "title": "readme-ai",
                    "value": metrics_csv,
                    "genome": "brutalist",
                },
            )
        )

    # Bug 2 (chrome height invariance) — 4 chrome strips at counts 1/2/3/4.
    for n, metrics_csv in [
        (1, "STARS:2.9k"),
        (2, "STARS:2.9k,FORKS:278"),
        (3, "STARS:2.9k,FORKS:278,ISSUES:14"),
        (4, "STARS:2.9k,FORKS:278,ISSUES:14,PRS:7"),
    ]:
        specs.append(
            ParitySpec(
                spec_id=f"chrome-strip-{n}metric-data-only",
                compose_spec=ComposeSpec(
                    type="strip",
                    genome_id="chrome",
                    title="readme-ai",
                    value=metrics_csv,
                ),
                http_path=f"/v1/strip/readme-ai/chrome.static?value={metrics_csv}",
                mcp_args={
                    "type": "strip",
                    "title": "readme-ai",
                    "value": metrics_csv,
                    "genome": "chrome",
                },
            )
        )

    # Bug 3 (state indicator gating) — BUILD title triggers indicator.
    specs.append(
        ParitySpec(
            spec_id="brutalist-strip-state-bearing",
            compose_spec=ComposeSpec(
                type="strip",
                genome_id="brutalist",
                title="readme-ai",
                value="BUILD:passing,STARS:2.9k",
            ),
            http_path="/v1/strip/readme-ai/brutalist.static?value=BUILD:passing,STARS:2.9k",
            mcp_args={
                "type": "strip",
                "title": "readme-ai",
                "value": "BUILD:passing,STARS:2.9k",
                "genome": "brutalist",
            },
        )
    )

    # High-star data-only (openclaw 373k) — number formatting + NO indicator.
    specs.append(
        ParitySpec(
            spec_id="chrome-strip-highstars-data-only",
            compose_spec=ComposeSpec(
                type="strip",
                genome_id="chrome",
                title="openclaw",
                value="STARS:373k,FORKS:12k,ISSUES:234",
            ),
            http_path="/v1/strip/openclaw/chrome.static?value=STARS:373k,FORKS:12k,ISSUES:234",
            mcp_args={
                "type": "strip",
                "title": "openclaw",
                "value": "STARS:373k,FORKS:12k,ISSUES:234",
                "genome": "chrome",
            },
        )
    )

    # ── Icons ───────────────────────────────────────────────────────────
    # Icon: HTTP route sets title=glyph (see serve/app.py:compose_icon_url:441),
    # so ComposeSpec and mcp_args must mirror that to maintain parity.
    specs.append(
        ParitySpec(
            spec_id="chrome-horizon-icon-github-circle",
            compose_spec=ComposeSpec(
                type="icon",
                genome_id="chrome",
                variant="horizon",
                title="github",
                glyph="github",
                shape="circle",
            ),
            http_path="/v1/icon/github/chrome.static?variant=horizon&shape=circle",
            mcp_args={
                "type": "icon",
                "title": "github",
                "glyph": "github",
                "genome": "chrome",
                "variant": "horizon",
                "shape": "circle",
            },
        )
    )
    specs.append(
        ParitySpec(
            spec_id="brutalist-icon-github",
            compose_spec=ComposeSpec(
                type="icon",
                genome_id="brutalist",
                title="github",
                glyph="github",
            ),
            http_path="/v1/icon/github/brutalist.static",
            mcp_args={
                "type": "icon",
                "title": "github",
                "glyph": "github",
                "genome": "brutalist",
            },
        )
    )

    # ── Dividers ────────────────────────────────────────────────────────
    specs.append(
        ParitySpec(
            spec_id="brutalist-divider-seam",
            compose_spec=ComposeSpec(
                type="divider",
                genome_id="brutalist",
                divider_variant="seam",
            ),
            http_path="/v1/divider/seam/brutalist.static",
            mcp_args={
                "type": "divider",
                "genome": "brutalist",
                "divider_variant": "seam",
            },
        )
    )
    specs.append(
        ParitySpec(
            spec_id="chrome-divider-band",
            compose_spec=ComposeSpec(
                type="divider",
                genome_id="chrome",
                divider_variant="band",
            ),
            http_path="/v1/divider/band/chrome.static",
            mcp_args={
                "type": "divider",
                "genome": "chrome",
                "divider_variant": "band",
            },
        )
    )

    # ── Marquee ─────────────────────────────────────────────────────────
    specs.append(
        ParitySpec(
            spec_id="chrome-marquee-horizon",
            compose_spec=ComposeSpec(
                type="marquee-horizontal",
                genome_id="chrome",
                variant="horizon",
                title="ITEM1 | ITEM2 | ITEM3",
            ),
            http_path="/v1/marquee/ITEM1%20%7C%20ITEM2%20%7C%20ITEM3/chrome.static?variant=horizon",
            mcp_args={
                "type": "marquee-horizontal",
                "title": "ITEM1 | ITEM2 | ITEM3",
                "genome": "chrome",
                "variant": "horizon",
            },
        )
    )

    # ── Real-data badges (gh:, pypi:, npm:, docker:, hf:) ───────────────
    # Each spec resolves a DATA_PROJECTS token, formats the value once,
    # then ships the SAME literal value to all three paths. Parity tests
    # path-equivalence with real-world values (not connector flakiness).
    # If a token failed to resolve (no live + no cache) the value renders
    # as "?" — parity still passes because all three paths see the same "?".
    from urllib.parse import quote as _urlquote

    _real_data_badges: list[tuple[str, str, str, str, str, str]] = [
        # (spec_id, token, title, genome, variant, genome_motion)
        # v0.3.9 corpus refresh: dropped gh-readme-ai-stars (eli64s/readme-ai
        # no longer in DATA_PROJECTS); InnerAura/hyperweave kept as the
        # low-count brutalist baseline since it's still queried by the
        # existing chart/stats generators.
        ("gh-hyperweave-stars", "github:InnerAura/hyperweave.stars", "STARS", "brutalist", "", "brutalist.static"),
        ("gh-openclaw-stars", "github:openclaw/openclaw.stars", "STARS", "chrome", "abyssal", "chrome.static"),
        (
            "gh-autogpt-stars",
            "github:Significant-Gravitas/AutoGPT.stars",
            "STARS",
            "automata",
            "teal",
            "automata.static",
        ),
        ("gh-n8n-stars", "github:n8n-io/n8n.stars", "STARS", "chrome", "lightning", "chrome.static"),
        ("gh-claude-code-stars", "github:anthropics/claude-code.stars", "STARS", "brutalist", "", "brutalist.static"),
        ("gh-ollama-stars", "github:ollama/ollama.stars", "STARS", "chrome", "graphite", "chrome.static"),
        ("pypi-hyperweave-version", "pypi:hyperweave.version", "VERSION", "brutalist", "", "brutalist.static"),
        ("pypi-langchain-downloads", "pypi:langchain.downloads", "DOWNLOADS", "chrome", "moth", "chrome.static"),
        (
            "npm-langgraph-downloads",
            "npm:@langchain/langgraph.downloads",
            "NPM-WEEKLY",
            "chrome",
            "horizon",
            "chrome.static",
        ),
        (
            "docker-ollama-pulls",
            "docker:ollama/ollama.pull_count",
            "DOCKER-PULLS",
            "chrome",
            "abyssal",
            "chrome.static",
        ),
        (
            "hf-hermes-downloads",
            "hf:NousResearch/Hermes-3-Llama-3.1-8B.downloads",
            "HF-DL",
            "automata",
            "violet",
            "automata.static",
        ),
        # v0.3.12 — crates.io across genomes.
        ("crates-serde-downloads", "crates:serde.downloads", "CRATES-DL", "chrome", "moth", "chrome.static"),
        ("crates-serde-version", "crates:serde.version", "VERSION", "brutalist", "celadon", "brutalist.static"),
        ("crates-serde-recent", "crates:serde.recent_downloads", "RECENT", "chrome", "graphite", "chrome.static"),
        ("crates-serde-license", "crates:serde.license", "LICENSE", "automata", "teal", "automata.static"),
        # v0.3.12 — OpenSSF Scorecard. score=TRUST + a check sub-score, plus the
        # n/a edge (vulnerabilities is absent from tokio's checks[] → "n/a").
        ("scorecard-tokio-trust", "scorecard:tokio-rs/tokio.score", "TRUST", "chrome", "moth", "chrome.static"),
        (
            "scorecard-tokio-review",
            "scorecard:tokio-rs/tokio.code_review",
            "REVIEW",
            "brutalist",
            "signal",
            "brutalist.static",
        ),
        (
            "scorecard-tokio-maintained",
            "scorecard:tokio-rs/tokio.maintained",
            "MAINTAINED",
            "automata",
            "amber",
            "automata.static",
        ),
        # The Vulnerabilities n/a edge (absent check) is shown via the connector
        # STRIP below, not a path-route badge: "n/a" contains "/", which the
        # 3-segment /v1/badge/{title}/{value}/... path cannot carry (404s). The
        # strip's ?value= query param handles it cleanly.
        # v0.3.12 — GitHub Actions DORA (needs HW_GITHUB_TOKENS; degrades to --).
        (
            "dora-fastapi-deploy-freq",
            "dora:fastapi/fastapi.deploy_frequency",
            "DEPLOY FREQ",
            "chrome",
            "lightning",
            "chrome.static",
        ),
    ]
    for spec_id, token, title, genome, variant, http_gm in _real_data_badges:
        value_str = _fmt_count(rd.get(token))
        url_value = _urlquote(value_str, safe="")
        variant_q = f"?variant={variant}" if variant else ""
        specs.append(
            ParitySpec(
                spec_id=spec_id,
                compose_spec=ComposeSpec(
                    type="badge",
                    genome_id=genome,
                    variant=variant,
                    title=title,
                    value=value_str,
                ),
                http_path=f"/v1/badge/{title}/{url_value}/{http_gm}{variant_q}",
                mcp_args={
                    "type": "badge",
                    "title": title,
                    "value": value_str,
                    "genome": genome,
                    **({"variant": variant} if variant else {}),
                },
            )
        )

    # ── v0.3.12 connectors across frames ────────────────────────────────
    # Connectors are frame-agnostic — the same tokens drive any frame.
    from hyperweave.serve.data_tokens import ResolvedToken as _RT

    # all-crates card (item 6): the full crates.io output in one strip, rendered
    # in the rust-appropriate brutalist UMBER variant (fired clay). License is a
    # string with spaces, so http_path values are URL-encoded.
    crates_all = (
        f"VERSION:{_fmt_count(rd.get('crates:serde.version'))},"
        f"DOWNLOADS:{_fmt_count(rd.get('crates:serde.downloads'))},"
        f"RECENT:{_fmt_count(rd.get('crates:serde.recent_downloads'))},"
        f"LICENSE:{_fmt_count(rd.get('crates:serde.license'))}"
    )
    specs.append(
        ParitySpec(
            spec_id="crates-all-strip",
            compose_spec=ComposeSpec(
                type="strip", genome_id="brutalist", variant="umber", title="serde", value=crates_all
            ),
            http_path=f"/v1/strip/serde/brutalist.static?value={_urlquote(crates_all, safe='')}&variant=umber",
            mcp_args={
                "type": "strip",
                "title": "serde",
                "value": crates_all,
                "genome": "brutalist",
                "variant": "umber",
            },
        )
    )

    # all-Scorecard card (item 6): the full OpenSSF Scorecard output in one
    # strip, brutalist ONYX. Shows real scores (TRUST/REVIEW/MAINTAINED), a real
    # ZERO (token_permissions=0, NOT n/a), and TWO n/a causes — vulnerabilities
    # (absent from checks[]) and signed_releases (present but scored -1).
    scorecard_all = (
        f"TRUST:{_fmt_count(rd.get('scorecard:tokio-rs/tokio.score'))},"
        f"REVIEW:{_fmt_count(rd.get('scorecard:tokio-rs/tokio.code_review'))},"
        f"MAINTAINED:{_fmt_count(rd.get('scorecard:tokio-rs/tokio.maintained'))},"
        f"TOKEN:{_fmt_count(rd.get('scorecard:tokio-rs/tokio.token_permissions'))},"
        f"VULNS:{_fmt_count(rd.get('scorecard:tokio-rs/tokio.vulnerabilities'))},"
        f"SIGNED:{_fmt_count(rd.get('scorecard:tokio-rs/tokio.signed_releases'))}"
    )
    specs.append(
        ParitySpec(
            spec_id="scorecard-all-strip",
            compose_spec=ComposeSpec(
                type="strip", genome_id="brutalist", variant="onyx", title="tokio", value=scorecard_all
            ),
            http_path=f"/v1/strip/tokio/brutalist.static?value={_urlquote(scorecard_all, safe='')}&variant=onyx",
            mcp_args={
                "type": "strip",
                "title": "tokio",
                "value": scorecard_all,
                "genome": "brutalist",
                "variant": "onyx",
            },
        )
    )

    # Full-band marquees per genome (item 5): volume + activity + identity in one
    # scroll, so the resolver's auto-group (volume→activity→identity), role-based
    # hero, state coloring (passing/warning/critical), and missing-value (--)
    # rendering are ALL visible in the regen. A real connector downloads value
    # rides in as a volume cell so the band also surfaces connector health.
    # kv tokens are deterministic → parity-safe across all three paths.
    def _fullband_marquee(spec_id: str, genome: str, variant: str, gm: str, dl_token: str) -> ParitySpec:
        from hyperweave.serve.data_tokens import _download_window

        # The download-window subtitle is derived from the dl_token's
        # (provider, metric) — pypi/crates downloads are ALL-TIME, npm is 7D — so
        # the period is self-describing and matches the live path exactly.
        dl_window = _download_window(dl_token.split(":", 1)[0], dl_token.rsplit(".", 1)[-1])
        pairs = [
            ("STARS", "2907", ""),  # volume → hero (first volume cell)
            ("DOWNLOADS", _fmt_count(rd.get(dl_token)), dl_window),  # volume → real value + window
            ("BUILD", "passing", ""),  # activity → passing (green)
            ("COVERAGE", "72%", ""),  # activity → warning (yellow)
            ("TESTS", "failing", ""),  # activity → critical (red)
            ("ISSUES", "--", ""),  # activity → missing value (no state color)
            ("VERSION", "2.1.0", ""),  # identity → muted
            ("LICENSE", "MIT", ""),  # identity → muted
        ]
        toks = [_RT(kind="kv", label=k, value=v, ttl=0, window=w) for k, v, w in pairs]
        data = ",".join(f"kv:{k}={v}~{w}" if w else f"kv:{k}={v}" for k, v, w in pairs)
        return ParitySpec(
            spec_id=spec_id,
            # title is metadata-only (data_tokens drive content); it must match
            # the http path segment so <title>/dc:title agree across paths.
            compose_spec=ComposeSpec(
                type="marquee-horizontal", genome_id=genome, variant=variant, title="HYPERWEAVE", data_tokens=toks
            ),
            http_path=f"/v1/marquee/HYPERWEAVE/{gm}?variant={variant}&data={_urlquote(data, safe='')}",
            mcp_args={
                "type": "marquee-horizontal",
                "title": "HYPERWEAVE",
                "genome": genome,
                "variant": variant,
                "data": data,
            },
        )

    specs.append(
        _fullband_marquee(
            "marquee-fullband-brutalist", "brutalist", "celadon", "brutalist.static", "pypi:langchain.downloads"
        )
    )
    specs.append(
        _fullband_marquee("marquee-fullband-chrome", "chrome", "moth", "chrome.static", "crates:serde.downloads")
    )
    specs.append(
        _fullband_marquee("marquee-fullband-automata", "automata", "bone", "automata.static", "npm:n8n.downloads")
    )

    # ── Real-data strips: long namespace + multi-metric ─────────────────
    # AutoGPT exercises long-namespace identity text + 3-metric strip;
    # verifies cell redistribution still fits inside the pinned canvas.
    autogpt_value = (
        f"STARS:{_fmt_count(rd.get('github:Significant-Gravitas/AutoGPT.stars'))},"
        f"FORKS:{_fmt_count(rd.get('github:Significant-Gravitas/AutoGPT.forks'))},"
        f"ISSUES:{_fmt_count(rd.get('github:Significant-Gravitas/AutoGPT.issues'))}"
    )
    specs.append(
        ParitySpec(
            spec_id="gh-autogpt-strip-3metric",
            compose_spec=ComposeSpec(
                type="strip",
                genome_id="chrome",
                title="AutoGPT",
                value=autogpt_value,
            ),
            http_path=f"/v1/strip/AutoGPT/chrome.static?value={autogpt_value}",
            mcp_args={
                "type": "strip",
                "title": "AutoGPT",
                "value": autogpt_value,
                "genome": "chrome",
            },
        )
    )

    # anthropics/claude-code: short namespace + 2-metric strip.
    cc_value = (
        f"STARS:{_fmt_count(rd.get('github:anthropics/claude-code.stars'))},"
        f"FORKS:{_fmt_count(rd.get('github:anthropics/claude-code.forks'))}"
    )
    specs.append(
        ParitySpec(
            spec_id="gh-claude-code-strip-2metric",
            compose_spec=ComposeSpec(
                type="strip",
                genome_id="brutalist",
                title="claude-code",
                value=cc_value,
            ),
            http_path=f"/v1/strip/claude-code/brutalist.static?value={cc_value}",
            mcp_args={
                "type": "strip",
                "title": "claude-code",
                "value": cc_value,
                "genome": "brutalist",
            },
        )
    )

    # mattpocock/skills: small-repo baseline strip (automata.teal variant).
    # v0.3.9 corpus refresh swapped eli64s/readme-ai → mattpocock/skills as
    # the low-count GitHub reference; readme-ai remains queryable via the
    # PyPI package token (pypi:readmeai) for the new stress specs.
    skills_value = (
        f"STARS:{_fmt_count(rd.get('github:mattpocock/skills.stars'))},"
        f"FORKS:{_fmt_count(rd.get('github:mattpocock/skills.forks'))}"
    )
    specs.append(
        ParitySpec(
            spec_id="gh-skills-strip-2metric",
            compose_spec=ComposeSpec(
                type="strip",
                genome_id="automata",
                variant="teal",
                title="skills",
                value=skills_value,
            ),
            http_path=f"/v1/strip/skills/automata.static?value={skills_value}&variant=teal",
            mcp_args={
                "type": "strip",
                "title": "skills",
                "value": skills_value,
                "genome": "automata",
                "variant": "teal",
            },
        )
    )

    # ── Automata compact badges ─────────────────────
    # Compact variant is 112x20 (vs default 148x32). Exercises the smaller
    # cellular cell + label vocabulary against multiple tone primitives.
    _automata_compact: list[tuple[str, str, str, str, str, str]] = [
        # (spec_id, token, title, variant, fallback_value, glyph_or_empty)
        # 6 specs — 2 with glyphs verify glyph rendering at
        # the smaller 112x20 compact form. Glyphs render at paradigm.glyph_size_compact
        # (= 8 for automata) rather than the default 12.
        # Note: bone-steel was a paired tone in the locked mapping plan;
        # the automata genome ships solo variants only, so the swap is to
        # nearest-adjacent solo tone (steel).
        ("automata-compact-pypi-vllm-violet", "pypi:vllm.version", "PYPI", "violet", "v0.5.4", ""),
        ("automata-compact-npm-langgraph-teal", "npm:@langchain/langgraph.version", "NPM", "teal", "v0.2.x", ""),
        ("automata-compact-docker-ollama-amber", "docker:ollama/ollama.pull_count", "PULLS", "amber", "1.2M", ""),
        (
            "automata-compact-hf-llama-steel",
            "hf:meta-llama/Llama-4-Scout-17B-16E-Instruct.downloads",
            "HF-DL",
            "steel",
            "240k",
            "",
        ),
        # glyph variants — compact + glyph combination
        ("automata-compact-python-version-jade", "pypi:vllm.version", "PYPI", "jade", "v0.5.4", "python"),
        (
            "automata-compact-docker-pulls-cobalt",
            "docker:ollama/ollama.pull_count",
            "PULLS",
            "cobalt",
            "1.2M",
            "docker",
        ),
    ]
    for spec_id, token, title, variant, fallback, glyph_slug in _automata_compact:
        v = rd.get(token)
        value_str = _fmt_count(v) if v is not None else fallback
        url_value = _urlquote(value_str, safe="")
        glyph_q = f"&glyph={glyph_slug}" if glyph_slug else ""
        compose_kwargs_a: dict[str, Any] = {
            "type": "badge",
            "genome_id": "automata",
            "variant": variant,
            "title": title,
            "value": value_str,
            "size": "compact",
        }
        mcp_a: dict[str, Any] = {
            "type": "badge",
            "title": title,
            "value": value_str,
            "genome": "automata",
            "variant": variant,
            "size": "compact",
        }
        if glyph_slug:
            compose_kwargs_a["glyph"] = glyph_slug
            mcp_a["glyph"] = glyph_slug
        specs.append(
            ParitySpec(
                spec_id=spec_id,
                compose_spec=ComposeSpec(**compose_kwargs_a),
                http_path=f"/v1/badge/{title}/{url_value}/automata.static?variant={variant}&size=compact{glyph_q}",
                mcp_args=mcp_a,
            )
        )

    # ── arXiv data badges ───────────────────────────
    # arXiv connector data not previously exercised in proofset. Paper IDs
    # map to title strings via the arxiv provider; we render the paper ID
    # itself as the value (the canonical citation key).
    _arxiv_badges: list[tuple[str, str, str, str]] = [
        # (spec_id, arxiv_id, genome, variant)
        ("arxiv-mistral-brutalist-celadon", "2310.06825", "brutalist", "celadon"),
        ("arxiv-deepseek-chrome-abyssal", "2501.12948", "chrome", "abyssal"),
    ]
    for spec_id, arxiv_id, genome, variant in _arxiv_badges:
        variant_q = f"?variant={variant}" if variant else ""
        specs.append(
            ParitySpec(
                spec_id=spec_id,
                compose_spec=ComposeSpec(
                    type="badge",
                    genome_id=genome,
                    variant=variant,
                    title="ARXIV",
                    value=arxiv_id,
                ),
                http_path=f"/v1/badge/ARXIV/{arxiv_id}/{genome}.static{variant_q}",
                mcp_args={
                    "type": "badge",
                    "title": "ARXIV",
                    "value": arxiv_id,
                    "genome": genome,
                    **({"variant": variant} if variant else {}),
                },
            )
        )

    # ── Real-data badge coverage (locked paradigm-tone mapping) ───
    # 16 GitHub + 10 multi-provider specs exercising every brutalist variant
    # (12), all chrome tones (5), 8 automata tones (solo + paired). Half of
    # GitHub specs ship with glyph, half without. Light-substrate brutalist
    # tones (archive/signal/pulse/depth) are over-indexed on non-GitHub
    # providers since those variants are newer and less exercised.
    _realdata_specs: list[tuple[str, str, str, str, str, str]] = [
        # (spec_id, token, title, genome, variant, glyph_slug_or_empty)
        # GitHub (16) — alternating glyph / no-glyph
        (
            "openclaw-brutalist-celadon-glyph",
            "github:openclaw/openclaw.stars",
            "STARS",
            "brutalist",
            "celadon",
            "github",
        ),
        ("claude-code-chrome-abyssal", "github:anthropics/claude-code.forks", "FORKS", "chrome", "abyssal", ""),
        ("vllm-automata-violet-glyph", "github:vllm-project/vllm.stars", "STARS", "automata", "violet", "github"),
        ("hermes-brutalist-carbon", "github:NousResearch/hermes-agent.stars", "STARS", "brutalist", "carbon", ""),
        (
            "langflow-chrome-lightning-glyph",
            "github:langflow-ai/langflow.stars",
            "STARS",
            "chrome",
            "lightning",
            "github",
        ),
        ("dify-automata-teal", "github:langgenius/dify.stars", "STARS", "automata", "teal", ""),
        ("n8n-brutalist-alloy-glyph", "github:n8n-io/n8n.stars", "STARS", "brutalist", "alloy", "github"),
        ("autogpt-chrome-graphite", "github:Significant-Gravitas/AutoGPT.forks", "FORKS", "chrome", "graphite", ""),
        ("ollama-automata-bone-glyph", "github:ollama/ollama.stars", "STARS", "automata", "bone", "github"),
        ("cline-brutalist-temper", "github:cline/cline.stars", "STARS", "brutalist", "temper", ""),
        ("mem0-chrome-moth-glyph", "github:mem0ai/mem0.stars", "STARS", "chrome", "moth", "github"),
        ("crewai-automata-steel", "github:crewAIInc/crewAI.stars", "STARS", "automata", "steel", ""),
        (
            "langchain-brutalist-pigment-glyph",
            "github:langchain-ai/langchain.stars",
            "STARS",
            "brutalist",
            "pigment",
            "github",
        ),
        ("metagpt-chrome-horizon", "github:FoundationAgents/MetaGPT.forks", "FORKS", "chrome", "horizon", ""),
        (
            "caveman-automata-sulfur-glyph",
            "github:JuliusBrussee/caveman.stars",
            "STARS",
            "automata",
            "sulfur",
            "github",
        ),
        ("skills-brutalist-ember", "github:mattpocock/skills.stars", "STARS", "brutalist", "ember", ""),
        # Multi-provider (10) — light brutalist + chrome + automata pairs
        ("pypi-vllm-brutalist-archive-glyph", "pypi:vllm.downloads", "DOWNLOADS", "brutalist", "archive", "python"),
        ("pypi-langchain-chrome-abyssal", "pypi:langchain.downloads", "DOWNLOADS", "chrome", "abyssal", ""),
        ("pypi-crewai-automata-amber-glyph", "pypi:crewai.downloads", "DOWNLOADS", "automata", "amber", "python"),
        ("pypi-hyperweave-brutalist-signal", "pypi:hyperweave.version", "VERSION", "brutalist", "signal", ""),
        (
            "npm-anthropic-chrome-lightning-glyph",
            "npm:@anthropic-ai/sdk.downloads",
            "NPM",
            "chrome",
            "lightning",
            "npm",
        ),
        ("npm-n8n-automata-indigo", "npm:n8n.downloads", "NPM", "automata", "indigo", ""),
        (
            "docker-ollama-brutalist-pulse-glyph",
            "docker:ollama/ollama.pull_count",
            "PULLS",
            "brutalist",
            "pulse",
            "docker",
        ),
        ("docker-n8n-chrome-graphite", "docker:n8nio/n8n.pull_count", "PULLS", "chrome", "graphite", ""),
        (
            "hf-llama-automata-burgundy-glyph",
            "hf:meta-llama/Llama-4-Scout-17B-16E-Instruct.downloads",
            "HF-DL",
            "automata",
            "burgundy",
            "huggingface",
        ),
        ("hf-qwen-brutalist-depth", "hf:Qwen/Qwen3-235B-A22B.downloads", "HF-DL", "brutalist", "depth", ""),
    ]
    for spec_id, token, title, genome, variant, glyph_slug in _realdata_specs:
        value_str = _fmt_count(rd.get(token))
        url_value = _urlquote(value_str, safe="")
        variant_q = f"variant={variant}"
        glyph_q = f"&glyph={glyph_slug}" if glyph_slug else ""
        compose_kwargs: dict[str, Any] = {
            "type": "badge",
            "genome_id": genome,
            "variant": variant,
            "title": title,
            "value": value_str,
        }
        mcp_a: dict[str, Any] = {
            "type": "badge",
            "title": title,
            "value": value_str,
            "genome": genome,
            "variant": variant,
        }
        if glyph_slug:
            compose_kwargs["glyph"] = glyph_slug
            mcp_a["glyph"] = glyph_slug
        specs.append(
            ParitySpec(
                spec_id=spec_id,
                compose_spec=ComposeSpec(**compose_kwargs),
                http_path=f"/v1/badge/{title}/{url_value}/{genome}.static?{variant_q}{glyph_q}",
                mcp_args=mcp_a,
            )
        )

    # ── State badges with real CI/CD titles ─────────
    # Titles from data/badge_modes.yaml allowlist trigger indicator rendering
    # and state-aware CSS. Values are realistic for each domain.
    _state_badges: list[tuple[str, str, str, str, str, str]] = [
        # (spec_id, title, value, genome, variant, glyph_slug)
        ("state-build-passing", "BUILD", "passing", "brutalist", "celadon", ""),
        ("state-tests-failing", "TESTS", "failing", "chrome", "abyssal", ""),
        ("state-coverage-87", "COVERAGE", "87%", "automata", "teal", ""),
        ("state-lint-clean", "LINT", "clean", "brutalist", "pulse", ""),
        ("state-deploy-pending", "DEPLOY", "pending", "chrome", "graphite", ""),
        ("state-release-stable", "RELEASE", "stable", "automata", "amber", ""),
    ]
    for spec_id, title, value, genome, variant, glyph_slug in _state_badges:
        url_value = _urlquote(value, safe="")
        variant_q = f"?variant={variant}" if variant else ""
        compose_kwargs_d: dict[str, Any] = {
            "type": "badge",
            "genome_id": genome,
            "variant": variant,
            "title": title,
            "value": value,
        }
        mcp_d: dict[str, Any] = {
            "type": "badge",
            "title": title,
            "value": value,
            "genome": genome,
            "variant": variant,
        }
        if glyph_slug:
            compose_kwargs_d["glyph"] = glyph_slug
            mcp_d["glyph"] = glyph_slug
        specs.append(
            ParitySpec(
                spec_id=spec_id,
                compose_spec=ComposeSpec(**compose_kwargs_d),
                http_path=f"/v1/badge/{title}/{url_value}/{genome}.static{variant_q}",
                mcp_args=mcp_d,
            )
        )

    # ── Z.AI GLM-5 cross-provider showcase ──────────────
    # Same project (Z.AI's GLM-5 family) spans GitHub, HuggingFace, and
    # arXiv. Three badges + one combined strip + one arxiv badge exercise
    # the cross-provider story end-to-end. Different genomes used per
    # badge to also stress paradigm consistency across providers.
    _zai_specs: list[tuple[str, str, str, str, str, str, str]] = [
        # (spec_id, token, title, genome, variant, glyph, http_paradigm)
        (
            "zai-gh-stars-brutalist",
            "github:zai-org/GLM-5.stars",
            "STARS",
            "brutalist",
            "celadon",
            "github",
            "brutalist.static",
        ),
        (
            "zai-hf-downloads-chrome",
            "hf:zai-org/GLM-5.1.downloads",
            "HF-DL",
            "chrome",
            "abyssal",
            "huggingface",
            "chrome.static",
        ),
        ("zai-arxiv-paper-automata", "arxiv:2602.15763", "ARXIV", "automata", "violet", "", "automata.static"),
    ]
    for spec_id, token, title, genome, variant, glyph_slug, http_gm in _zai_specs:
        value_str = token[len("arxiv:") :] if token.startswith("arxiv:") else _fmt_count(rd.get(token))
        url_value = _urlquote(value_str, safe="")
        glyph_q = f"&glyph={glyph_slug}" if glyph_slug else ""
        ck_z: dict[str, Any] = {
            "type": "badge",
            "genome_id": genome,
            "variant": variant,
            "title": title,
            "value": value_str,
        }
        mcp_z: dict[str, Any] = {
            "type": "badge",
            "title": title,
            "value": value_str,
            "genome": genome,
            "variant": variant,
        }
        if glyph_slug:
            ck_z["glyph"] = glyph_slug
            mcp_z["glyph"] = glyph_slug
        specs.append(
            ParitySpec(
                spec_id=spec_id,
                compose_spec=ComposeSpec(**ck_z),
                http_path=f"/v1/badge/{title}/{url_value}/{http_gm}?variant={variant}{glyph_q}",
                mcp_args=mcp_z,
            )
        )

    # Z.AI multi-provider strip: combines GitHub stars + HuggingFace
    # downloads + arXiv paper ID into one identity, exercising the same
    # ecosystem-strip path as vllm. Chrome paradigm + identity glyph
    # consistent with cross-provider story.
    _zai_strip_value = (
        f"GH:{_fmt_count(rd.get('github:zai-org/GLM-5.stars'))},"
        f"HF:{_fmt_count(rd.get('hf:zai-org/GLM-5.1.downloads'))},"
        f"ARXIV:2602.15763"
    )
    specs.append(
        ParitySpec(
            spec_id="zai-glm5-ecosystem-strip",
            compose_spec=ComposeSpec(
                type="strip",
                genome_id="chrome",
                variant="abyssal",
                title="GLM-5",
                value=_zai_strip_value,
                connector_data={"repo_slug": "zai-org/GLM-5"},
            ),
            http_path=(
                f"/v1/strip/GLM-5/chrome.static?value={_zai_strip_value}"
                f"&variant=abyssal&subtitle={_urlquote('zai-org/GLM-5', safe='')}"
            ),
            mcp_args={
                "type": "strip",
                "title": "GLM-5",
                "value": _zai_strip_value,
                "genome": "chrome",
                "variant": "abyssal",
                "connector_data": {"repo_slug": "zai-org/GLM-5"},
            },
        )
    )

    # ── Spatial Matrix specs ────────────────────────────
    # 12 specs covering the 4 most common zone configurations across 3
    # paradigms (celadon, horizon, teal). Same label + value content so
    # the only variable is which zones are present. Directly exercises
    # the layout engine's zone-collapse behavior under known inputs.
    _spatial_matrix: list[tuple[str, str, str, str, str, str, str]] = [
        # (spec_id, paradigm, variant, title, value, glyph_or_empty, motion_label)
        # Config 1: label + value (no glyph, no state-bearing title)
        ("matrix-label-value-brutalist", "brutalist", "celadon", "STARS", "184.4k", "", "label+value only"),
        ("matrix-label-value-chrome", "chrome", "horizon", "STARS", "184.4k", "", "label+value only"),
        ("matrix-label-value-automata", "automata", "teal", "STARS", "184.4k", "", "label+value only"),
        # Config 2: glyph + label + value (no state-bearing title)
        ("matrix-glyph-label-value-brutalist", "brutalist", "celadon", "STARS", "184.4k", "github", "+ glyph"),
        ("matrix-glyph-label-value-chrome", "chrome", "horizon", "STARS", "184.4k", "github", "+ glyph"),
        ("matrix-glyph-label-value-automata", "automata", "teal", "STARS", "184.4k", "github", "+ glyph"),
        # Config 3: label + value + state (BUILD title triggers state indicator)
        ("matrix-state-brutalist", "brutalist", "celadon", "BUILD", "passing", "", "+ state"),
        ("matrix-state-chrome", "chrome", "horizon", "BUILD", "passing", "", "+ state"),
        ("matrix-state-automata", "automata", "teal", "BUILD", "passing", "", "+ state"),
        # Config 4: glyph + label + value + state (all zones)
        ("matrix-glyph-state-brutalist", "brutalist", "celadon", "BUILD", "passing", "github", "all zones"),
        ("matrix-glyph-state-chrome", "chrome", "horizon", "BUILD", "passing", "github", "all zones"),
        ("matrix-glyph-state-automata", "automata", "teal", "BUILD", "passing", "github", "all zones"),
    ]
    for spec_id, paradigm, variant, title, value, glyph_slug, _motion_label in _spatial_matrix:
        url_value = _urlquote(value, safe="")
        glyph_q = f"&glyph={glyph_slug}" if glyph_slug else ""
        compose_kwargs_m: dict[str, Any] = {
            "type": "badge",
            "genome_id": paradigm,
            "variant": variant,
            "title": title,
            "value": value,
        }
        mcp_m: dict[str, Any] = {
            "type": "badge",
            "title": title,
            "value": value,
            "genome": paradigm,
            "variant": variant,
        }
        if glyph_slug:
            compose_kwargs_m["glyph"] = glyph_slug
            mcp_m["glyph"] = glyph_slug
        specs.append(
            ParitySpec(
                spec_id=spec_id,
                compose_spec=ComposeSpec(**compose_kwargs_m),
                http_path=f"/v1/badge/{title}/{url_value}/{paradigm}.static?variant={variant}{glyph_q}",
                mcp_args=mcp_m,
            )
        )

    # ── Literal connectors (text:, kv: semantics) ───────────────────────
    specs.append(
        ParitySpec(
            spec_id="text-literal-beta",
            compose_spec=ComposeSpec(
                type="badge",
                genome_id="brutalist",
                title="STATUS",
                value="BETA",
            ),
            http_path="/v1/badge/STATUS/BETA/brutalist.static",
            mcp_args={
                "type": "badge",
                "title": "STATUS",
                "value": "BETA",
                "genome": "brutalist",
            },
        )
    )
    specs.append(
        ParitySpec(
            spec_id="kv-status-active",
            compose_spec=ComposeSpec(
                type="badge",
                genome_id="chrome",
                variant="horizon",
                title="STATUS",
                value="ACTIVE",
            ),
            http_path="/v1/badge/STATUS/ACTIVE/chrome.static?variant=horizon",
            mcp_args={
                "type": "badge",
                "title": "STATUS",
                "value": "ACTIVE",
                "genome": "chrome",
                "variant": "horizon",
            },
        )
    )
    specs.append(
        ParitySpec(
            spec_id="kv-env-production",
            compose_spec=ComposeSpec(
                type="badge",
                genome_id="brutalist",
                title="ENV",
                value="PRODUCTION",
            ),
            http_path="/v1/badge/ENV/PRODUCTION/brutalist.static",
            mcp_args={
                "type": "badge",
                "title": "ENV",
                "value": "PRODUCTION",
                "genome": "brutalist",
            },
        )
    )

    # ── Edge-case stress matrix (v0.3.9 round 2) ────────────────────────
    # 27 specs pushing layout limits: multi-source strips, value-length
    # extremes, label-length extremes, mixed-magnitude, all-states per
    # genome, numeric-format boundaries, special-char titles. The
    # additive strip layout (Phase 1 round 2) should handle every shape
    # below without overflow, blank space, or stretched cells.

    # --- vllm ecosystem strip (4 cells across vllm's footprint on 4 connectors) ---
    # v0.3.9 Bug 2 fix: was "ECOSYSTEM" (abstract; reviewer couldn't identify
    # the project). Renamed to "vllm" — every metric is from vllm-project
    # across github / pypi / docker / hf so the strip reads as "vllm's
    # cross-ecosystem footprint" instead of an opaque label.
    vllm_stars = _fmt_count(rd.get("github:vllm-project/vllm.stars"))
    vllm_dl = _fmt_count(rd.get("pypi:vllm.downloads"))
    vllm_pulls = _fmt_count(rd.get("docker:vllm/vllm-openai.pull_count"))
    llama4_dl = _fmt_count(rd.get("hf:meta-llama/Llama-4-Scout-17B-16E-Instruct.downloads"))
    vllm_value = f"STARS:{vllm_stars},PYPI:{vllm_dl},DOCKER:{vllm_pulls},HF:{llama4_dl}"
    specs.append(
        ParitySpec(
            spec_id="vllm-ecosystem-strip",
            compose_spec=ComposeSpec(
                type="strip",
                genome_id="chrome",
                variant="horizon",
                title="vllm",
                value=vllm_value,
            ),
            http_path=f"/v1/strip/vllm/chrome.static?value={vllm_value}&variant=horizon",
            mcp_args={
                "type": "strip",
                "title": "vllm",
                "value": vllm_value,
                "genome": "chrome",
                "variant": "horizon",
            },
        )
    )

    # --- Extreme value lengths (badges) ---
    for sid, value in [
        ("value-extreme-single-char", "0"),
        ("value-extreme-long-version", "v0.3.9-beta.2+gita1b2c3d4"),
        ("value-extreme-compact-magnitude", "1.2M"),
        ("value-extreme-fallback-mark", "?"),
    ]:
        from urllib.parse import quote as _q

        specs.append(
            ParitySpec(
                spec_id=sid,
                compose_spec=ComposeSpec(
                    type="badge",
                    genome_id="brutalist",
                    title="VERSION",
                    value=value,
                ),
                http_path=f"/v1/badge/VERSION/{_q(value, safe='')}/brutalist.static",
                mcp_args={
                    "type": "badge",
                    "title": "VERSION",
                    "value": value,
                    "genome": "brutalist",
                },
            )
        )

    # --- Extreme label lengths (badges) ---
    for sid, title, value in [
        ("label-extreme-single-char", "X", "1"),
        ("label-extreme-long-status", "BUILD-PASSING-WITH-WARNINGS", "OK"),
        ("label-extreme-single-letter-v", "v", "1"),
    ]:
        specs.append(
            ParitySpec(
                spec_id=sid,
                compose_spec=ComposeSpec(
                    type="badge",
                    genome_id="chrome",
                    variant="horizon",
                    title=title,
                    value=value,
                ),
                http_path=f"/v1/badge/{title}/{value}/chrome.static?variant=horizon",
                mcp_args={
                    "type": "badge",
                    "title": title,
                    "value": value,
                    "genome": "chrome",
                    "variant": "horizon",
                },
            )
        )

    # --- Long-namespace strips (4 metrics on long name, 1 metric on short) ---
    autogpt_stars2 = _fmt_count(rd.get("github:Significant-Gravitas/AutoGPT.stars"))
    autogpt_forks2 = _fmt_count(rd.get("github:Significant-Gravitas/AutoGPT.forks"))
    autogpt_issues2 = _fmt_count(rd.get("github:Significant-Gravitas/AutoGPT.issues"))
    autogpt_4m = f"STARS:{autogpt_stars2},FORKS:{autogpt_forks2},ISSUES:{autogpt_issues2},PRS:42"
    # FastAPI route /v1/strip/{title}/... treats slash as path separator.
    # The route exposes a ``?t=`` query param to carry slashed titles
    # (with the path segment as a placeholder). Use it here.
    specs.append(
        ParitySpec(
            spec_id="long-namespace-strip-4metric",
            compose_spec=ComposeSpec(
                type="strip",
                genome_id="brutalist",
                title="Significant-Gravitas/AutoGPT",
                value=autogpt_4m,
            ),
            http_path=(f"/v1/strip/_/brutalist.static?t=Significant-Gravitas%2FAutoGPT&value={autogpt_4m}"),
            mcp_args={
                "type": "strip",
                "title": "Significant-Gravitas/AutoGPT",
                "value": autogpt_4m,
                "genome": "brutalist",
            },
        )
    )
    # Cross-genome parity for the long-namespace 4-metric strip (v0.3.13):
    # chrome (cell_min_width 88 + identity textLength) and automata (bifamily
    # flanks + identity textLength) size identity to content like brutalist —
    # regression coverage for the cross-genome strip parity work.
    for _ns_genome in ("chrome", "automata"):
        specs.append(
            ParitySpec(
                spec_id=f"long-namespace-strip-4metric-{_ns_genome}",
                compose_spec=ComposeSpec(
                    type="strip",
                    genome_id=_ns_genome,
                    title="Significant-Gravitas/AutoGPT",
                    value=autogpt_4m,
                ),
                http_path=(f"/v1/strip/_/{_ns_genome}.static?t=Significant-Gravitas%2FAutoGPT&value={autogpt_4m}"),
                mcp_args={
                    "type": "strip",
                    "title": "Significant-Gravitas/AutoGPT",
                    "value": autogpt_4m,
                    "genome": _ns_genome,
                },
            )
        )
    cc_stars2 = _fmt_count(rd.get("github:anthropics/claude-code.stars"))
    specs.append(
        ParitySpec(
            spec_id="short-name-strip-1metric",
            compose_spec=ComposeSpec(
                type="strip",
                genome_id="chrome",
                variant="abyssal",
                title="claude-code",
                value=f"STARS:{cc_stars2}",
            ),
            http_path=f"/v1/strip/claude-code/chrome.static?value=STARS:{cc_stars2}&variant=abyssal",
            mcp_args={
                "type": "strip",
                "title": "claude-code",
                "value": f"STARS:{cc_stars2}",
                "genome": "chrome",
                "variant": "abyssal",
            },
        )
    )

    # --- Mixed-magnitude strip (each cell wildly different magnitude) ---
    # SYNTHETIC demo fixture — exercises strip cell layout under extreme
    # value-magnitude variance (6-digit, 2-digit, 1-digit, single-zero).
    # Title and values are obviously synthetic so this never gets misread
    # as a real project's stats. Real-data strips live in the per-provider
    # "Real-data badges" sections.
    mixed_mag = "STARS:999k,FORKS:99,ISSUES:9,PRS:0"
    _mixed_conn = {"repo_slug": "demo/synthetic-magnitude"}
    specs.append(
        ParitySpec(
            spec_id="mixed-magnitude-strip",
            compose_spec=ComposeSpec(
                type="strip",
                genome_id="automata",
                variant="violet",
                title="demo-repo",
                value=mixed_mag,
                connector_data=_mixed_conn,
            ),
            http_path=f"/v1/strip/demo-repo/automata.static?value={mixed_mag}&variant=violet&subtitle=demo%2Fsynthetic-magnitude",
            mcp_args={
                "type": "strip",
                "title": "demo-repo",
                "value": mixed_mag,
                "genome": "automata",
                "variant": "violet",
                "connector_data": _mixed_conn,
            },
        )
    )

    # --- All-state badges per genome (15 specs = 5 states x 3 genomes) ---
    _state_genomes: list[tuple[str, str, str]] = [
        # (genome, variant, http_genome_motion)
        ("brutalist", "", "brutalist.static"),
        ("chrome", "horizon", "chrome.static"),
        ("automata", "teal", "automata.static"),
    ]
    _states = ["passing", "warning", "critical", "building", "offline"]
    for genome, variant, http_gm in _state_genomes:
        for state in _states:
            variant_q = f"&variant={variant}" if variant else ""
            specs.append(
                ParitySpec(
                    spec_id=f"state-{genome}-{state}",
                    compose_spec=ComposeSpec(
                        type="badge",
                        genome_id=genome,
                        variant=variant,
                        title="BUILD",
                        value=state,
                        state=state,
                    ),
                    http_path=f"/v1/badge/BUILD/{state}/{http_gm}?state={state}{variant_q}",
                    mcp_args={
                        "type": "badge",
                        "title": "BUILD",
                        "value": state,
                        "state": state,
                        "genome": genome,
                        **({"variant": variant} if variant else {}),
                    },
                )
            )

    # --- Numeric format edges (boundary cases for k/M formatting) ---
    for sid, value in [
        ("numeric-zero", "0"),
        ("numeric-three-digit", "999"),
        ("numeric-k-boundary", "1.0k"),
        ("numeric-k-max", "999.9k"),
        ("numeric-m-boundary", "1.0M"),
    ]:
        specs.append(
            ParitySpec(
                spec_id=sid,
                compose_spec=ComposeSpec(
                    type="badge",
                    genome_id="brutalist",
                    title="STARS",
                    value=value,
                ),
                http_path=f"/v1/badge/STARS/{value}/brutalist.static",
                mcp_args={
                    "type": "badge",
                    "title": "STARS",
                    "value": value,
                    "genome": "brutalist",
                },
            )
        )

    # --- Special character titles (UTF-8 in title path segment) ---
    from urllib.parse import quote as _q2

    for sid, title in [
        ("special-char-middot", "STATUS · LIVE"),
        ("special-char-arrow", "BUILD → PASS"),
    ]:
        specs.append(
            ParitySpec(
                spec_id=sid,
                compose_spec=ComposeSpec(
                    type="badge",
                    genome_id="chrome",
                    variant="moth",
                    title=title,
                    value="OK",
                ),
                http_path=f"/v1/badge/{_q2(title, safe='')}/OK/chrome.static?variant=moth",
                mcp_args={
                    "type": "badge",
                    "title": title,
                    "value": "OK",
                    "genome": "chrome",
                    "variant": "moth",
                },
            )
        )

    # ── stress matrix ──────────────────────────────────────
    # 17 new specs covering identity-glyph strips, stats cards, star charts,
    # and marquees across all three genomes with magnitude + length
    # variations. Each routes through the full pipeline (direct / http / mcp)
    # with live tokens where possible.

    # --- D1: Strip identity glyph variety (5 specs) ---
    # Different paradigms x different glyphs to verify glyph rendering inside
    # the identity zone (previously only tested without glyphs).
    autogpt_stars = _fmt_count(rd.get("github:Significant-Gravitas/AutoGPT.stars"))
    autogpt_forks = _fmt_count(rd.get("github:Significant-Gravitas/AutoGPT.forks"))
    autogpt_issues = _fmt_count(rd.get("github:Significant-Gravitas/AutoGPT.issues"))
    vllm_stars3 = _fmt_count(rd.get("github:vllm-project/vllm.stars"))
    vllm_pypi_dl = _fmt_count(rd.get("pypi:vllm.downloads"))
    ollama_pulls = _fmt_count(rd.get("docker:ollama/ollama.pull_count"))
    ollama_stars3 = _fmt_count(rd.get("github:ollama/ollama.stars"))
    n8n_version = _fmt_count(rd.get("npm:n8n.version"))
    n8n_npm_dl = _fmt_count(rd.get("npm:n8n.downloads"))
    cc_stars3 = _fmt_count(rd.get("github:anthropics/claude-code.stars"))
    cc_forks3 = _fmt_count(rd.get("github:anthropics/claude-code.forks"))

    _strip_glyph_specs = [
        (
            "strip-glyph-github-brutalist",
            "github",
            "brutalist",
            "",
            "brutalist.static",
            "AutoGPT",
            f"STARS:{autogpt_stars},FORKS:{autogpt_forks},ISSUES:{autogpt_issues}",
        ),
        (
            "strip-glyph-python-chrome",
            "python",
            "chrome",
            "horizon",
            "chrome.static",
            "vllm",
            f"STARS:{vllm_stars3},PYPI:{vllm_pypi_dl}",
        ),
        (
            "strip-glyph-docker-automata",
            "docker",
            "automata",
            "teal",
            "automata.static",
            "ollama",
            f"STARS:{ollama_stars3},PULLS:{ollama_pulls}",
        ),
        (
            "strip-glyph-npm-brutalist",
            "npm",
            "brutalist",
            "",
            "brutalist.static",
            "n8n",
            f"VERSION:{n8n_version},NPM-DL:{n8n_npm_dl}",
        ),
        (
            # v0.3.12 fix: was glyph="openai" on a claude-code identity (a
            # mismatched proofset entry — the engine faithfully rendered the
            # requested OpenAI mark for a Claude project). claude-code's correct
            # mark is the Anthropic glyph.
            "strip-glyph-anthropic-chrome",
            "anthropic",
            "chrome",
            "moth",
            "chrome.static",
            "claude-code",
            f"STARS:{cc_stars3},FORKS:{cc_forks3}",
        ),
    ]
    for sid, glyph_slug, genome, variant, http_gm, title, value in _strip_glyph_specs:
        variant_q = f"&variant={variant}" if variant else ""
        specs.append(
            ParitySpec(
                spec_id=sid,
                compose_spec=ComposeSpec(
                    type="strip",
                    genome_id=genome,
                    title=title,
                    value=value,
                    glyph=glyph_slug,
                    **({"variant": variant} if variant else {}),
                ),
                http_path=f"/v1/strip/{title}/{http_gm}?value={value}&glyph={glyph_slug}{variant_q}",
                mcp_args={
                    "type": "strip",
                    "title": title,
                    "value": value,
                    "genome": genome,
                    "glyph": glyph_slug,
                    **({"variant": variant} if variant else {}),
                },
            )
        )

    # --- D4: Marquee stress — FREE-TEXT variations (inline ribbon for every
    # genome via the content-aware layout: no label+value to stack, so text
    # scrolls as a clean flow). Brutalist uses Barlow + ▮ bars, automata its
    # mid_accent ▪, chrome the · dot. Counterpart STACKED-DATA marquees are the
    # full-band specs above + the data-flavored kv spec below. #}
    _marquee_specs = [
        (
            "marquee-text-only-pipe",
            "brutalist",
            "",
            "brutalist.static",
            "DEPLOYMENTS | INCIDENTS | UPTIME | LATENCY | THROUGHPUT",
        ),
        (
            "marquee-mixed-content",
            "automata",
            "teal",
            "automata.static",
            f"vllm · {vllm_stars3} ★ · langchain · ollama · {ollama_pulls}",
        ),
    ]
    for sid, genome, variant, http_gm, title in _marquee_specs:
        variant_q = f"?variant={variant}" if variant else ""
        specs.append(
            ParitySpec(
                spec_id=sid,
                compose_spec=ComposeSpec(
                    type="marquee-horizontal",
                    genome_id=genome,
                    title=title,
                    **({"variant": variant} if variant else {}),
                ),
                http_path=f"/v1/marquee/{_q2(title, safe='')}/{http_gm}{variant_q}",
                mcp_args={
                    "type": "marquee-horizontal",
                    "title": title,
                    "genome": genome,
                    **({"variant": variant} if variant else {}),
                },
            )
        )

    # Data-flavored chrome marquee — real connector values as kv LABEL+VALUE
    # pairs so they STACK in chrome's dense-data module (consistent with the
    # full-band specs), instead of the prior inline "PYPI:78.3M" text-with-colons
    # that read as an ambiguous second chrome layout. Counterpart to the
    # free-text examples above: same genome, the other content mode.
    _df_pairs = [("STARS", autogpt_stars), ("PYPI", vllm_pypi_dl), ("DOCKER", ollama_pulls)]
    _df_toks = [_RT(kind="kv", label=k, value=v, ttl=0) for k, v in _df_pairs]
    _df_data = ",".join(f"kv:{k}={v}" for k, v in _df_pairs)
    specs.append(
        ParitySpec(
            spec_id="marquee-data-flavored",
            compose_spec=ComposeSpec(
                type="marquee-horizontal",
                genome_id="chrome",
                variant="horizon",
                title="HYPERWEAVE",
                data_tokens=_df_toks,
            ),
            http_path=f"/v1/marquee/HYPERWEAVE/chrome.static?variant=horizon&data={_urlquote(_df_data, safe='')}",
            mcp_args={
                "type": "marquee-horizontal",
                "title": "HYPERWEAVE",
                "genome": "chrome",
                "variant": "horizon",
                "data": _df_data,
            },
        )
    )

    # Stats card + star chart stress are generated as STATIC artifacts via
    # _generate_data_cards (each genome x variant), not through the parity
    # matrix. The HTTP endpoint fetches GitHub user data live, the direct
    # path renders with placeholders — the two paths diverge by design.
    # Parity matrix would report a false-positive failure even though both
    # paths render correct artifacts in their own right.

    # --- W2 Badge variant matrix (19 specs) ---
    # Per-genome x per-variant badge coverage with real provider data and
    # mixed CI/CD + telemetry titles. Earlier the edge cases section had
    # exactly ONE badge per genome at the default variant — leaves the
    # variant axis (substrate/tone) entirely untested. These specs cover
    # the remaining variants so visual review can spot any per-variant
    # chromatic regressions.

    # Automata solo tones (6 specs) — each pulls a different provider value
    # so the variant matrix doubles as a connector verification sweep.
    pypi_vllm_v = _fmt_count(rd.get("pypi:vllm.version"))
    npm_lg_dl = _fmt_count(rd.get("npm:@langchain/langgraph.downloads"))
    docker_ollama_pulls = _fmt_count(rd.get("docker:ollama/ollama.pull_count"))
    hf_qwen_dl = _fmt_count(rd.get("hf:Qwen/Qwen3-235B-A22B.downloads"))
    hermes_likes = _fmt_count(rd.get("hf:NousResearch/Hermes-3-Llama-3.1-8B.likes"))
    crewai_dl = _fmt_count(rd.get("pypi:crewai.downloads"))

    _automata_badges = [
        ("automata-violet-badge-pypi", "violet", "PYPI", pypi_vllm_v),
        ("automata-bone-badge-npm", "bone", "NPM-DL", npm_lg_dl),
        ("automata-steel-badge-docker", "steel", "PULLS", docker_ollama_pulls),
        ("automata-solar-badge-hf", "solar", "HF-DL", hf_qwen_dl),
        ("automata-amber-badge-likes", "amber", "LIKES", hermes_likes),
        ("automata-jade-badge-crewai", "jade", "DOWNLOADS", crewai_dl),
    ]
    for sid, variant, title, value in _automata_badges:
        specs.append(
            ParitySpec(
                spec_id=sid,
                compose_spec=ComposeSpec(
                    type="badge",
                    genome_id="automata",
                    variant=variant,
                    title=title,
                    value=value,
                ),
                http_path=f"/v1/badge/{title}/{_urlquote(value, safe='')}/automata.static?variant={variant}",
                mcp_args={
                    "type": "badge",
                    "title": title,
                    "value": value,
                    "genome": "automata",
                    "variant": variant,
                },
            )
        )

    # Brutalist substrate variety (5 specs) — 3 dark monochromes + 2 light scholars.
    autogpt_stars2 = _fmt_count(rd.get("github:Significant-Gravitas/AutoGPT.stars"))
    n8n_v = _fmt_count(rd.get("npm:n8n.version"))
    langflow_issues = _fmt_count(rd.get("github:langflow-ai/langflow.issues"))
    _brutalist_badges = [
        ("brutalist-carbon-badge-stars", "carbon", "STARS", autogpt_stars2),
        ("brutalist-alloy-badge-version", "alloy", "VERSION", n8n_v),
        ("brutalist-ember-badge-issues", "ember", "ISSUES", langflow_issues),
        ("brutalist-pulse-badge-build", "pulse", "BUILD", "passing"),
        ("brutalist-archive-badge-coverage", "archive", "COVERAGE", "94%"),
    ]
    for sid, variant, title, value in _brutalist_badges:
        specs.append(
            ParitySpec(
                spec_id=sid,
                compose_spec=ComposeSpec(
                    type="badge",
                    genome_id="brutalist",
                    variant=variant,
                    title=title,
                    value=value,
                ),
                http_path=f"/v1/badge/{title}/{_urlquote(value, safe='')}/brutalist.static?variant={variant}",
                mcp_args={
                    "type": "badge",
                    "title": title,
                    "value": value,
                    "genome": "brutalist",
                    "variant": variant,
                },
            )
        )

    # Chrome variant variety (4 specs).
    cc_forks_chrome = _fmt_count(rd.get("github:anthropics/claude-code.forks"))
    dify_issues = _fmt_count(rd.get("github:langgenius/dify.issues"))
    _chrome_badges = [
        ("chrome-abyssal-badge-stars", "abyssal", "STARS", cc_forks_chrome),
        ("chrome-lightning-badge-tests", "lightning", "TESTS", "passing"),
        ("chrome-moth-badge-license", "moth", "LICENSE", "Apache-2.0"),
        ("chrome-graphite-badge-issues", "graphite", "ISSUES", dify_issues),
    ]
    for sid, variant, title, value in _chrome_badges:
        specs.append(
            ParitySpec(
                spec_id=sid,
                compose_spec=ComposeSpec(
                    type="badge",
                    genome_id="chrome",
                    variant=variant,
                    title=title,
                    value=value,
                ),
                http_path=f"/v1/badge/{title}/{_urlquote(value, safe='')}/chrome.static?variant={variant}",
                mcp_args={
                    "type": "badge",
                    "title": title,
                    "value": value,
                    "genome": "chrome",
                    "variant": variant,
                },
            )
        )

    # Stateful CI/CD across genomes (4 specs) — exercise the state indicator
    # glyph + threshold-CSS tinting on titles in the badge-modes allowlist.
    _stateful_badges = [
        ("stateful-build-passing-brutalist-temper", "brutalist", "temper", "BUILD", "passing"),
        ("stateful-deploy-active-chrome-horizon", "chrome", "horizon", "DEPLOY", "active"),
        ("stateful-tests-warning-automata-cobalt", "automata", "cobalt", "TESTS", "warning"),
        ("stateful-security-critical-brutalist-signal", "brutalist", "signal", "SECURITY", "critical"),
        ("stateful-ci-failing-chrome-abyssal", "chrome", "abyssal", "CI", "failing"),
        ("stateful-deploy-rollback-automata-magenta", "automata", "magenta", "DEPLOY", "rollback"),
        ("stateful-coverage-passing-brutalist-pulse", "brutalist", "pulse", "COVERAGE", "98%"),
        ("stateful-uptime-active-chrome-moth", "chrome", "moth", "UPTIME", "99.99"),
    ]
    for sid, genome, variant, title, value in _stateful_badges:
        specs.append(
            ParitySpec(
                spec_id=sid,
                compose_spec=ComposeSpec(
                    type="badge",
                    genome_id=genome,
                    variant=variant,
                    title=title,
                    value=value,
                ),
                http_path=f"/v1/badge/{title}/{_urlquote(value, safe='')}/{genome}.static?variant={variant}",
                mcp_args={
                    "type": "badge",
                    "title": title,
                    "value": value,
                    "genome": genome,
                    "variant": variant,
                },
            )
        )

    # --- Glyph + no-glyph paired badges (8 specs = 4 pairs) ---
    # Each pair has identical title/value/genome — one with glyph, one without.
    # Directly tests compute_badge_zones zone-collapse: with-glyph has the
    # glyph slot rendered, no-glyph collapses to pad-glued label_first_x.
    _glyph_pairs = [
        ("github", "brutalist", "celadon", "STARS", "184.4k"),
        ("python", "chrome", "horizon", "PYPI", "v1.3.2"),
        ("docker", "automata", "teal", "PULLS", "135.9M"),
        ("npm", "brutalist", "carbon", "VERSION", "2.21.5"),
    ]
    for glyph_slug, genome, variant, title, value in _glyph_pairs:
        for has_glyph, suffix in [(True, "with-glyph"), (False, "no-glyph")]:
            kwargs: dict[str, Any] = {
                "type": "badge",
                "genome_id": genome,
                "variant": variant,
                "title": title,
                "value": value,
            }
            mcp = {"type": "badge", "title": title, "value": value, "genome": genome, "variant": variant}
            glyph_q = ""
            if has_glyph:
                kwargs["glyph"] = glyph_slug
                mcp["glyph"] = glyph_slug
                glyph_q = f"&glyph={glyph_slug}"
            specs.append(
                ParitySpec(
                    spec_id=f"paired-glyph-{glyph_slug}-{genome}-{suffix}",
                    compose_spec=ComposeSpec(**kwargs),
                    http_path=(
                        f"/v1/badge/{title}/{_urlquote(value, safe='')}/{genome}.static?variant={variant}{glyph_q}"
                    ),
                    mcp_args=mcp,
                )
            )

    # --- Strip variety: identity + multi-provider + state-bearing (5 specs) ---
    # Glyph-only identity (no text), label-only short, mixed-magnitude, single
    # strip pulling from gh+pypi+docker+hf, state-bearing 3-metric.
    vllm_v = _fmt_count(rd.get("pypi:vllm.version"))
    vllm_stars_v = _fmt_count(rd.get("github:vllm-project/vllm.stars"))
    ollama_pulls_v = _fmt_count(rd.get("docker:ollama/ollama.pull_count"))
    llama_dl_v = _fmt_count(rd.get("hf:meta-llama/Llama-4-Scout-17B-16E-Instruct.downloads"))
    _strip_variety = [
        (
            "strip-mixed-magnitude-brutalist",
            "brutalist",
            "celadon",
            "n8n",
            f"STARS:189k,FORKS:0,VERSION:{vllm_v}",
            "github",
            "n8n-io/n8n",
        ),
        (
            "strip-multi-provider-chrome",
            "chrome",
            "horizon",
            "vllm",
            f"GH:{vllm_stars_v},PYPI:{vllm_v},DOCKER:{ollama_pulls_v},HF:{llama_dl_v}",
            "python",
            "vllm-project/vllm",
        ),
        (
            "strip-state-bearing-build-brutalist",
            "brutalist",
            "celadon",
            "hyperweave",
            "BUILD:passing,TESTS:passing,COVERAGE:94%",
            "",
            "InnerAura/hyperweave",
        ),
        (
            "strip-5-metric-chrome",
            "chrome",
            "abyssal",
            "vllm",
            f"STARS:{vllm_stars_v},FORKS:9k,ISSUES:1.2k,PRS:340,VERSION:{vllm_v}",
            "",
            "vllm-project/vllm",
        ),
        (
            "strip-1-metric-with-glyph-automata",
            "automata",
            "violet",
            "claude-code",
            "STARS:125.3k",
            "openai",
            "anthropics/claude-code",  # subtitle: distinct from title="claude-code"
        ),
        # additions
        (
            "strip-state-bearing-chrome",
            "chrome",
            "lightning",
            "ollama",
            "BUILD:passing,STARS:189k,FORKS:9k",
            "github",
            "ollama/ollama",
        ),
        (
            "strip-2-metric-automata-teal",
            "automata",
            "teal",
            "langflow",
            "STARS:38.4k,FORKS:4.7k",
            "github",
            "langflow-ai/langflow",
        ),
        (
            "strip-multi-provider-brutalist",
            "brutalist",
            "alloy",
            "n8n",
            f"GH:189k,DOCKER:{ollama_pulls_v},NPM:5.6m",
            "n8n",
            "n8n-io/n8n",
        ),
        # state-bearing strips across paradigms.
        # Titles from data/badge_modes.yaml allowlist trigger indicator
        # rendering and (when state values use sentinel keywords) state-aware
        # CSS threshold tinting.
        (
            "strip-state-deploy-active-chrome",
            "chrome",
            "graphite",
            "claude-code",
            "DEPLOY:active,VERSION:0.3.0,RELEASE:stable",
            "github",
            "anthropics/claude-code",
        ),
        (
            "strip-state-tests-failing-automata",
            "automata",
            "amber",
            "langflow",
            "TESTS:failing,COVERAGE:73%,BUILD:warning",
            "github",
            "langflow-ai/langflow",
        ),
        (
            "strip-state-coverage-brutalist-light",
            "brutalist",
            "archive",
            "vllm",
            "COVERAGE:87%,LINT:clean,DEPLOY:pending",
            "github",
            "vllm-project/vllm",
        ),
    ]
    for sid, genome, variant, title, value, glyph_slug, subtitle in _strip_variety:
        kwargs2: dict[str, Any] = {
            "type": "strip",
            "genome_id": genome,
            "variant": variant,
            "title": title,
            "value": value,
        }
        mcp2: dict[str, Any] = {
            "type": "strip",
            "title": title,
            "value": value,
            "genome": genome,
            "variant": variant,
        }
        subtitle_q = ""
        if subtitle:
            # Three-path parity: direct uses connector_data, HTTP uses
            # ?subtitle= query param (serve/app.py line 386), MCP uses
            # connector_data kwarg.
            kwargs2["connector_data"] = {"repo_slug": subtitle}
            mcp2["connector_data"] = {"repo_slug": subtitle}
            subtitle_q = f"&subtitle={_urlquote(subtitle, safe='')}"
        glyph_q2 = ""
        if glyph_slug:
            kwargs2["glyph"] = glyph_slug
            mcp2["glyph"] = glyph_slug
            glyph_q2 = f"&glyph={glyph_slug}"
        specs.append(
            ParitySpec(
                spec_id=sid,
                compose_spec=ComposeSpec(**kwargs2),
                http_path=f"/v1/strip/{title}/{genome}.static?value={value}&variant={variant}{glyph_q2}{subtitle_q}",
                mcp_args=mcp2,
            )
        )

    # ── Matrix (v0.4.0-alpha.2) ─────────────────────────────────────────
    # The generated connector matrix across direct/HTTP/MCP. The envelope's
    # content-derived id is identical on all three paths by construction;
    # prov.ts normalizes with the other timestamps.
    specs.append(
        ParitySpec(
            spec_id="primer-matrix-connectors-porcelain",
            compose_spec=ComposeSpec(
                type="matrix",
                genome_id="primer",
                variant="porcelain",
                connector_data={"matrix_adapter": "connector-registry"},
            ),
            http_path="/v1/matrix/connectors/primer.static?variant=porcelain",
            mcp_args={
                "type": "matrix",
                "genome": "primer",
                "variant": "porcelain",
                "connector_data": {"matrix_adapter": "connector-registry"},
            },
        )
    )

    return specs


# render-only specs that bypass three-path parity. Stats
# cards and star charts fetch live data on the HTTP endpoint but render
# with placeholders via the direct path — parity is impossible without
# harness-level pre-fetched connector_data plumbing. These specs generate
# ONLY via direct render with pre-fetched data so the visual review
# surface includes them without false-positive parity failures.
#
# Each tuple: (spec_id, frame_type, username_or_owner, repo_or_none,
# genome, variant, label_for_readme).
_RENDER_ONLY_SPECS: list[tuple[str, str, str, str, str, str, str]] = [
    # stat cards exercise REAL individual GitHub accounts
    # exclusively (still had 2 orgs). One org spec retained
    # (vllm-project) as a reminder to design org-specific stat card cards
    # in a future round — orgs aggregate differently and the current
    # individual-tuned layout shows known overflow with long org names.
    # Username variety stress-tests the P2 78px header zone overflow fix:
    # - torvalds (8 chars): no overflow, naturally fits
    # - karpathy (8 chars): naturally fits
    # - sindresorhus (12 chars): borderline, may or may not overflow
    # - juliusBrussee (13 chars): overflows ~82px natural → clamps to 78
    # - yyx990803 (9 chars, Evan You's handle): mid-length, fits
    # - vllm-project (12 chars, ORG): retained for org-vs-individual contrast
    (
        "stats-torvalds-brutalist-celadon",
        "stats",
        "torvalds",
        "",
        "brutalist",
        "celadon",
        "torvalds (Linus Torvalds, ~227k followers) — brutalist celadon",
    ),
    (
        "stats-sindresorhus-chrome-horizon",
        "stats",
        "sindresorhus",
        "",
        "chrome",
        "horizon",
        "sindresorhus (open-source machine, ~64k followers) — chrome horizon",
    ),
    (
        "stats-karpathy-automata-teal",
        "stats",
        "karpathy",
        "",
        "automata",
        "teal",
        "karpathy (Andrej Karpathy, ML educator) — automata teal",
    ),
    (
        "stats-yyx990803-brutalist-pulse",
        "stats",
        "yyx990803",
        "",
        "brutalist",
        "pulse",
        "yyx990803 (Evan You, Vue.js creator) — brutalist pulse (light)",
    ),
    (
        "stats-juliusbrussee-chrome-moth",
        "stats",
        "juliusBrussee",
        "",
        "chrome",
        "moth",
        "juliusBrussee (caveman creator, 62k stars) — chrome moth",
    ),
    (
        "stats-vllm-automata-bone",
        "stats",
        "vllm-project",
        "",
        "automata",
        "bone",
        "vllm-project (ORG, retained as design reference) — automata bone",
    ),
    # Star charts — growth profiles plus a controlled same-series genome sweep.
    (
        "chart-langflow-chrome-lightning",
        "chart",
        "langflow-ai",
        "langflow",
        "chrome",
        "lightning",
        "High-growth repo (langflow-ai/langflow) — chrome lightning",
    ),
    (
        "chart-hyperweave-brutalist-celadon",
        "chart",
        "InnerAura",
        "hyperweave",
        "brutalist",
        "celadon",
        "Self-growth (InnerAura/hyperweave) — brutalist celadon",
    ),
    (
        "chart-claude-code-automata-teal",
        "chart",
        "anthropics",
        "claude-code",
        "automata",
        "teal",
        "Mid-growth (anthropics/claude-code) — automata teal",
    ),
    # additions
    (
        "chart-vllm-chrome-abyssal",
        "chart",
        "vllm-project",
        "vllm",
        "chrome",
        "abyssal",
        "High-growth (vllm-project/vllm) — chrome abyssal",
    ),
    (
        "chart-langchain-brutalist-celadon",
        "chart",
        "langchain-ai",
        "langchain",
        "brutalist",
        "celadon",
        "Mature, plateaued (langchain-ai/langchain) — brutalist celadon",
    ),
    (
        "chart-claude-code-same-chrome-horizon",
        "chart",
        "anthropics",
        "claude-code",
        "chrome",
        "horizon",
        "Same series check (anthropics/claude-code) — chrome horizon",
    ),
    (
        "chart-claude-code-same-brutalist-celadon",
        "chart",
        "anthropics",
        "claude-code",
        "brutalist",
        "celadon",
        "Same series check (anthropics/claude-code) — brutalist celadon",
    ),
    (
        "chart-claude-code-same-automata-teal",
        "chart",
        "anthropics",
        "claude-code",
        "automata",
        "teal",
        "Same series check (anthropics/claude-code) — automata teal",
    ),
]


async def _generate_render_only_specs() -> list[dict[str, Any]]:
    """Generate stats / star-chart artifacts that skip three-path parity.

    Each spec fetches its live data once, composes via the direct path with
    pre-resolved ``connector_data``, and writes ``proofset/parity/{spec_id}-
    direct.svg``. Returned manifest entries are appended to ``manifest.json``
    after the parity matrix runs so the README Edge Cases section embeds
    them via the same path pattern as parity specs.

    HTTP and MCP fields are set to None and ``all_match=True`` so the parity
    summary report doesn't flag these as failures — they're explicitly
    render-only by design.
    """
    from hyperweave.connectors.base import close_client
    from hyperweave.connectors.github import fetch_stargazer_history, fetch_user_stats

    # Reset httpx client singleton — the prior parity matrix loop closed when
    # asyncio.run() ended, leaving the client bound to a dead loop. Fresh
    # client in the current loop avoids "Event loop is closed" on first fetch.
    await close_client()
    out_dir = OUT / "proofset" / "parity"
    out_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []

    # Cache fetched data by source so we don't re-fetch for multiple variant specs.
    stats_cache: dict[str, Any] = {}
    chart_cache: dict[tuple[str, str], Any] = {}

    for sid, frame_type, owner_or_user, repo, genome, variant, _label in _RENDER_ONLY_SPECS:
        try:
            if frame_type == "stats":
                if owner_or_user not in stats_cache:
                    try:
                        stats_cache[owner_or_user] = await fetch_user_stats(owner_or_user)
                    except Exception as exc:
                        print(f"  [RENDER-ONLY FETCH FAIL] {sid}: {type(exc).__name__}: {exc}")
                        stats_cache[owner_or_user] = None
                svg = _compose_connector(
                    "stats",
                    genome,
                    stats_username=owner_or_user,
                    connector_data=stats_cache[owner_or_user],
                    variant=variant,
                )
            elif frame_type == "chart":
                cache_key = (owner_or_user, repo)
                if cache_key not in chart_cache:
                    try:
                        chart_cache[cache_key] = await fetch_stargazer_history(owner_or_user, repo)
                    except Exception as exc:
                        print(f"  [RENDER-ONLY FETCH FAIL] {sid}: {type(exc).__name__}: {exc}")
                        chart_cache[cache_key] = None
                svg = _compose_connector(
                    "chart",
                    genome,
                    chart_owner=owner_or_user,
                    chart_repo=repo,
                    connector_data=chart_cache[cache_key],
                    variant=variant,
                )
            else:
                continue
            _write(out_dir / f"{sid}-direct.svg", svg)
            entries.append(
                {
                    "spec_id": sid,
                    "direct": f"{sid}-direct.svg",
                    "http": None,
                    "mcp": None,
                    "parity_direct_http": None,
                    "parity_direct_mcp": None,
                    "parity_http_mcp": None,
                    "all_match": True,
                    "render_only": True,
                }
            )
        except Exception as exc:
            print(f"  [RENDER-ONLY GEN FAIL] {sid}: {type(exc).__name__}: {exc}")

    await close_client()
    return entries


async def generate_parity_matrix() -> tuple[int, int, int]:
    """Generate the 3-path parity verification matrix.

    Starts a uvicorn subprocess for FastAPI + an in-process MCP client,
    renders each ParitySpec via direct/http/mcp paths, saves all three
    SVGs to outputs/proofset/parity/, and asserts byte-equality after
    normalization. Returns (specs_rendered, parity_passed, parity_failed).

    Cleans up the server subprocess on any error path. Test order is
    irrelevant (each spec is independent), but the matrix is built once
    so the same order ships every run.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from proofset_harness import (
        ParityReport,
        fastapi_server,
        load_fixtures,
        mcp_client,
        render_and_save_three_paths,
        save_fixtures,
    )

    # Pre-fetch every DATA_PROJECTS token (live with fixture cache fallback).
    # Resolved values feed _build_parity_matrix so all three paths see the
    # same literal — parity tests path equivalence, not connector flakiness.
    fixtures = load_fixtures()
    fixture_count_before = len(fixtures)
    resolved_data = await _resolve_data_projects(fixtures)
    if len(fixtures) > fixture_count_before:
        save_fixtures(fixtures)
        print(f"  cached {len(fixtures) - fixture_count_before} new connector values")

    specs = _build_parity_matrix(resolved_data)
    out_dir = OUT / "proofset" / "parity"
    if out_dir.exists():
        import shutil

        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    reports: list[ParityReport] = []
    with fastapi_server(port=8765) as base_url:
        async with mcp_client() as mcp:
            for spec in specs:
                try:
                    report = await render_and_save_three_paths(spec, base_url, mcp, out_dir)
                    reports.append(report)
                except Exception as exc:
                    print(f"  [PARITY ERROR] {spec.spec_id}: {type(exc).__name__}: {exc}")

    # Manifest file lists every report so the README emitter can iterate.
    manifest = [
        {
            "spec_id": r.spec_id,
            "direct": r.direct_path.name,
            "http": r.http_path.name,
            "mcp": r.mcp_path.name,
            "parity_direct_http": r.parity_direct_http,
            "parity_direct_mcp": r.parity_direct_mcp,
            "parity_http_mcp": r.parity_http_mcp,
            "all_match": r.all_match,
        }
        for r in reports
    ]
    import json

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    passed = sum(1 for r in reports if r.all_match)
    failed = len(reports) - passed
    return len(reports), passed, failed


_EDGE_CASE_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    # (group_title, [(spec_id, label), ...]) — order ships verbatim in
    # outputs/README.md "Edge Cases" section so reviewers can scan
    # related stress-test axes together. Each row gets a label + the
    # single direct-render SVG at full width (HTTP / MCP renderings are
    # byte-equal — verified by the parity summary below this section).
    (
        "Value lengths",
        [
            ("value-extreme-single-char", "Single character value (`0`)"),
            ("value-extreme-long-version", "Long version string (`v0.3.9-beta.2+gita1b2c3d4`, 26 chars)"),
            ("value-extreme-compact-magnitude", "Compact magnitude format (`1.2M`)"),
            ("value-extreme-fallback-mark", "Fallback indicator (`?` — connector unreachable)"),
        ],
    ),
    (
        "Label lengths",
        [
            ("label-extreme-single-char", "Single character label (`X`)"),
            ("label-extreme-long-status", "28-character status label (`BUILD-PASSING-WITH-WARNINGS`)"),
            ("label-extreme-single-letter-v", "Single lowercase letter (`v`)"),
        ],
    ),
    (
        "Strip metric counts — brutalist",
        [
            ("brutalist-strip-1metric-data-only", "1 metric"),
            ("brutalist-strip-2metric-data-only", "2 metrics"),
            ("brutalist-strip-3metric-data-only", "3 metrics"),
            ("brutalist-strip-4metric-data-only", "4 metrics"),
        ],
    ),
    (
        "Strip metric counts — chrome",
        [
            ("chrome-strip-1metric-data-only", "1 metric"),
            ("chrome-strip-2metric-data-only", "2 metrics"),
            ("chrome-strip-3metric-data-only", "3 metrics"),
            ("chrome-strip-4metric-data-only", "4 metrics"),
        ],
    ),
    (
        "Multi-source strips",
        [
            (
                "vllm-ecosystem-strip",
                "vllm cross-connector footprint (GitHub stars + PyPI dl + Docker pulls + HF Llama-4 dl)",
            ),
        ],
    ),
    (
        "Namespace length — strips",
        [
            ("long-namespace-strip-4metric", "Long namespace (`Significant-Gravitas/AutoGPT`) + 4 metrics"),
            ("long-namespace-strip-4metric-chrome", "Long namespace + 4 metrics — chrome (cross-genome parity)"),
            ("long-namespace-strip-4metric-automata", "Long namespace + 4 metrics — automata (cross-genome parity)"),
            ("short-name-strip-1metric", "Short name (`claude-code`) + 1 metric"),
            ("gh-autogpt-strip-3metric", "AutoGPT + 3 real-data metrics"),
            ("gh-claude-code-strip-2metric", "claude-code + 2 real-data metrics"),
            ("gh-readme-ai-strip-2metric", "readme-ai + 2 real-data metrics (automata.teal)"),
        ],
    ),
    (
        "Mixed-magnitude strips",
        [
            (
                "mixed-magnitude-strip",
                "Extreme magnitude variance — synthetic demo (`STARS:999k,FORKS:99,ISSUES:9,PRS:0`)",
            ),
        ],
    ),
    (
        "All-state badges — brutalist",
        [
            ("state-brutalist-passing", "passing"),
            ("state-brutalist-warning", "warning"),
            ("state-brutalist-critical", "critical"),
            ("state-brutalist-building", "building"),
            ("state-brutalist-offline", "offline"),
        ],
    ),
    (
        "All-state badges — chrome.horizon",
        [
            ("state-chrome-passing", "passing"),
            ("state-chrome-warning", "warning"),
            ("state-chrome-critical", "critical"),
            ("state-chrome-building", "building"),
            ("state-chrome-offline", "offline"),
        ],
    ),
    (
        "All-state badges — automata.teal",
        [
            ("state-automata-passing", "passing"),
            ("state-automata-warning", "warning"),
            ("state-automata-critical", "critical"),
            ("state-automata-building", "building"),
            ("state-automata-offline", "offline"),
        ],
    ),
    (
        "Numeric format edges",
        [
            ("numeric-zero", "Value `0`"),
            ("numeric-three-digit", "Value `999` (3 digits, no k suffix)"),
            ("numeric-k-boundary", "Value `1.0k` (k formatting boundary)"),
            ("numeric-k-max", "Value `999.9k` (max before M)"),
            ("numeric-m-boundary", "Value `1.0M` (M formatting boundary)"),
        ],
    ),
    (
        "Special characters in titles",
        [
            ("special-char-middot", "Mid-dot character (`STATUS · LIVE`)"),
            ("special-char-arrow", "Right arrow character (`BUILD → PASS`)"),
        ],
    ),
    # ── stress matrix ──
    (
        "Strip identity glyph variety",
        [
            ("strip-glyph-github-brutalist", "GitHub glyph in identity (brutalist) — AutoGPT + 3 metrics"),
            ("strip-glyph-python-chrome", "Python glyph in identity (chrome horizon) — vllm + 2 metrics"),
            ("strip-glyph-docker-automata", "Docker glyph in identity (automata teal) — ollama + 2 metrics"),
            ("strip-glyph-npm-brutalist", "npm glyph in identity (brutalist) — n8n version + downloads"),
            ("strip-glyph-anthropic-chrome", "Anthropic glyph for claude-code identity (chrome moth) — 2 metrics"),
        ],
    ),
    (
        "Marquee stress",
        [
            ("marquee-text-only-pipe", "Free text → inline ribbon (brutalist celadon — Barlow + ▮ bars)"),
            ("marquee-data-flavored", "Connector data → stacked module (chrome horizon)"),
            ("marquee-mixed-content", "Mixed text + symbols → inline ribbon (automata violet-teal)"),
        ],
    ),
    # ── Spatial Matrix ──
    # Same content (STARS/184.4k or BUILD/passing) rendered across 4 zone
    # configurations and 3 paradigms. The only variable per row is which
    # zones are present — directly QAs the layout engine's zone-collapse
    # behavior. 3-column table layout naturally groups by paradigm
    # (brutalist | chrome | automata) so each row reads as a paradigm
    # comparison for one zone config.
    (
        "Spatial Matrix — zone configurations across paradigms (algorithm QA)",
        [
            ("matrix-label-value-brutalist", "label + value (brutalist celadon)"),
            ("matrix-label-value-chrome", "label + value (chrome horizon)"),
            ("matrix-label-value-automata", "label + value (automata teal)"),
            ("matrix-glyph-label-value-brutalist", "+ glyph (brutalist celadon)"),
            ("matrix-glyph-label-value-chrome", "+ glyph (chrome horizon)"),
            ("matrix-glyph-label-value-automata", "+ glyph (automata teal)"),
            ("matrix-state-brutalist", "+ state indicator (brutalist celadon)"),
            ("matrix-state-chrome", "+ state indicator (chrome horizon)"),
            ("matrix-state-automata", "+ state indicator (automata teal)"),
            ("matrix-glyph-state-brutalist", "all zones (brutalist celadon)"),
            ("matrix-glyph-state-chrome", "all zones (chrome horizon)"),
            ("matrix-glyph-state-automata", "all zones (automata teal)"),
        ],
    ),
    # Removed sections (deduped — content covered by Real-data section
    # real-data table and Spatial Matrix above):
    #   - "Automata badge variants — solo tones" (real-data section covers tone variety)
    #   - "Brutalist badge variants — substrate variety" (real-data section covers substrate)
    #   - "Chrome badge variants — material variety" (real-data section covers materials)
    # Variant tone showcases live in per-genome README files
    # (outputs/README_AUTOMATA.md etc).
    # ── Z.AI GLM-5 cross-provider showcase ──
    (
        "Z.AI GLM-5 — same project across three providers",
        [
            ("zai-gh-stars-brutalist", "GitHub: zai-org/GLM-5 STARS — brutalist celadon"),
            ("zai-hf-downloads-chrome", "HuggingFace: zai-org/GLM-5.1 DL — chrome abyssal"),
            ("zai-arxiv-paper-automata", "arXiv: 2602.15763 paper — automata violet"),
        ],
    ),
    (
        "Stateful CI/CD badges — state indicator coverage",
        [
            ("stateful-build-passing-brutalist-temper", "BUILD passing (brutalist temper)"),
            ("stateful-deploy-active-chrome-horizon", "DEPLOY active (chrome horizon)"),
            ("stateful-tests-warning-automata-cobalt", "TESTS warning (automata cobalt)"),
            ("stateful-security-critical-brutalist-signal", "SECURITY critical (brutalist signal)"),
        ],
    ),
    # ── render-only specs (skip parity, direct render only) ──
    (
        "Stats card stress (render-only)",
        [
            ("stats-torvalds-brutalist-celadon", "torvalds (Linus Torvalds, ~227k followers) — brutalist celadon"),
            (
                "stats-sindresorhus-chrome-horizon",
                "sindresorhus (open-source machine, ~64k followers) — chrome horizon",
            ),
            ("stats-karpathy-automata-teal", "karpathy (Andrej Karpathy, ML educator) — automata teal"),
            ("stats-yyx990803-brutalist-pulse", "yyx990803 (Evan You, Vue.js creator) — brutalist pulse (light)"),
            ("stats-juliusbrussee-chrome-moth", "juliusBrussee (caveman creator) — chrome moth"),
            ("stats-vllm-automata-bone", "vllm-project (ORG, retained as design reference) — automata bone"),
        ],
    ),
    (
        "Star chart stress (render-only)",
        [
            ("chart-langflow-chrome-lightning", "High-growth repo (langflow-ai/langflow) — chrome lightning"),
            ("chart-hyperweave-brutalist-celadon", "Self-growth (InnerAura/hyperweave) — brutalist celadon"),
            ("chart-claude-code-automata-teal", "Mid-growth (anthropics/claude-code) — automata teal"),
            ("chart-vllm-chrome-abyssal", "High-growth (vllm-project/vllm) — chrome abyssal"),
            ("chart-langchain-brutalist-celadon", "Mature, plateaued (langchain-ai/langchain) — brutalist celadon"),
        ],
    ),
    (
        "Star chart same-series genome sweep (render-only)",
        [
            ("chart-claude-code-same-chrome-horizon", "anthropics/claude-code — chrome horizon"),
            ("chart-claude-code-same-brutalist-celadon", "anthropics/claude-code — brutalist celadon"),
            ("chart-claude-code-same-automata-teal", "anthropics/claude-code — automata teal"),
        ],
    ),
    # ── paired-glyph zone-collapse coverage ──
    (
        "Glyph + no-glyph paired badges (zone collapse)",
        [
            ("paired-glyph-github-brutalist-with-glyph", "github glyph (brutalist celadon, STARS 184.4k)"),
            ("paired-glyph-github-brutalist-no-glyph", "same content, NO glyph — zone collapses"),
            ("paired-glyph-python-chrome-with-glyph", "python glyph (chrome horizon, PYPI v1.3.2)"),
            ("paired-glyph-python-chrome-no-glyph", "same content, NO glyph"),
            ("paired-glyph-docker-automata-with-glyph", "docker glyph (automata teal, PULLS 135.9M)"),
            ("paired-glyph-docker-automata-no-glyph", "same content, NO glyph"),
            ("paired-glyph-npm-brutalist-with-glyph", "npm glyph (brutalist carbon, VERSION 2.21.5)"),
            ("paired-glyph-npm-brutalist-no-glyph", "same content, NO glyph"),
        ],
    ),
    # ── strip variety (identity + provider + state) ──
    (
        "Strip variety — identity + multi-provider + state-bearing",
        [
            ("strip-mixed-magnitude-brutalist", "Mixed magnitude (189k / 0 / version) — brutalist celadon"),
            ("strip-multi-provider-chrome", "Single strip pulling gh + pypi + docker + hf — chrome horizon"),
            ("strip-state-bearing-build-brutalist", "State-bearing CI/CD strip — brutalist celadon"),
            ("strip-5-metric-chrome", "5-metric strip (extreme cell count) — chrome abyssal"),
            ("strip-1-metric-with-glyph-automata", "1-metric strip with identity glyph — automata violet"),
        ],
    ),
    # ── additional stateful badge titles ──
    (
        "Stateful CI/CD — extended title coverage",
        [
            ("stateful-ci-failing-chrome-abyssal", "CI failing (chrome abyssal)"),
            ("stateful-deploy-rollback-automata-magenta", "DEPLOY rollback (automata magenta)"),
            ("stateful-coverage-passing-brutalist-pulse", "COVERAGE 98% (brutalist pulse light)"),
            ("stateful-uptime-active-chrome-moth", "UPTIME 99.99 (chrome moth)"),
        ],
    ),
    # ── Real-data badges grouped by provider ────────────
    # Five provider sub-sections (GitHub / PyPI / npm / Docker / HuggingFace)
    # replace the prior single flat "Real-data badges" section + the standalone
    # "Automata compact badges" section. Compact-variant badges are folded
    # into the provider that supplies their data so each provider zone reads
    # as a complete sample (default + compact variants together).
    (
        "Real-data badges — GitHub",
        [
            ("openclaw-brutalist-celadon-glyph", "openclaw STARS + github — brutalist celadon"),
            ("claude-code-chrome-abyssal", "anthropics/claude-code FORKS — chrome abyssal"),
            ("vllm-automata-violet-glyph", "vllm-project STARS + github — automata violet"),
            ("hermes-brutalist-carbon", "NousResearch/hermes-agent STARS — brutalist carbon"),
            ("langflow-chrome-lightning-glyph", "langflow-ai STARS + github — chrome lightning"),
            ("dify-automata-teal", "langgenius/dify STARS — automata teal"),
            ("n8n-brutalist-alloy-glyph", "n8n-io STARS + github — brutalist alloy"),
            ("autogpt-chrome-graphite", "Significant-Gravitas/AutoGPT FORKS — chrome graphite"),
            ("ollama-automata-bone-glyph", "ollama STARS + github — automata bone"),
            ("cline-brutalist-temper", "cline/cline STARS — brutalist temper"),
            ("mem0-chrome-moth-glyph", "mem0ai/mem0 STARS + github — chrome moth"),
            ("crewai-automata-steel", "crewAIInc/crewAI STARS — automata steel"),
            ("langchain-brutalist-pigment-glyph", "langchain-ai/langchain STARS + github — brutalist pigment"),
            ("metagpt-chrome-horizon", "FoundationAgents/MetaGPT FORKS — chrome horizon"),
            ("caveman-automata-sulfur-glyph", "JuliusBrussee/caveman STARS + github — automata sulfur"),
            ("skills-brutalist-ember", "mattpocock/skills STARS — brutalist ember"),
        ],
    ),
    (
        "Real-data badges — PyPI",
        [
            ("pypi-vllm-brutalist-archive-glyph", "pypi:vllm DOWNLOADS + python — brutalist archive (light)"),
            ("pypi-langchain-chrome-abyssal", "pypi:langchain DOWNLOADS — chrome abyssal"),
            ("pypi-crewai-automata-amber-glyph", "pypi:crewai DOWNLOADS + python — automata amber"),
            ("pypi-hyperweave-brutalist-signal", "pypi:hyperweave VERSION — brutalist signal (light)"),
            ("automata-compact-pypi-vllm-violet", "pypi:vllm compact — automata violet (112x20)"),
            ("automata-compact-python-version-jade", "PYPI + python glyph compact — automata jade (112x20)"),
        ],
    ),
    (
        "Real-data badges — npm",
        [
            ("npm-anthropic-chrome-lightning-glyph", "npm:@anthropic-ai/sdk NPM + npm glyph — chrome lightning"),
            ("npm-n8n-automata-indigo", "npm:n8n DOWNLOADS — automata indigo"),
            ("automata-compact-npm-langgraph-teal", "npm:@langchain/langgraph compact — automata teal (112x20)"),
        ],
    ),
    (
        "Real-data badges — Docker",
        [
            ("docker-ollama-brutalist-pulse-glyph", "docker:ollama PULLS + docker — brutalist pulse (light)"),
            ("docker-n8n-chrome-graphite", "docker:n8nio/n8n PULLS — chrome graphite"),
            ("automata-compact-docker-ollama-amber", "docker:ollama PULLS compact — automata amber (112x20)"),
            ("automata-compact-docker-pulls-cobalt", "DOCKER PULLS + docker glyph compact — automata cobalt (112x20)"),
        ],
    ),
    (
        "Real-data badges — HuggingFace",
        [
            (
                "hf-llama-automata-burgundy-glyph",
                "hf:Llama-4-Scout DL + huggingface — automata burgundy",
            ),
            ("hf-qwen-brutalist-depth", "hf:Qwen3-235B DL — brutalist depth (light)"),
            ("automata-compact-hf-llama-steel", "hf:Llama-4-Scout DL compact — automata steel (112x20)"),
        ],
    ),
    # ── arXiv data badges (separate provider sub-section) ──
    (
        "Real-data badges — arXiv",
        [
            ("arxiv-mistral-brutalist-celadon", "arxiv:2310.06825 Mistral 7B — brutalist celadon"),
            ("arxiv-deepseek-chrome-abyssal", "arxiv:2501.12948 DeepSeek-R1 — chrome abyssal"),
        ],
    ),
    # ── v0.3.12 connectors: crates.io / OpenSSF Scorecard / GitHub Actions DORA ──
    (
        "Real-data badges — crates.io",
        [
            ("crates-serde-downloads", "crates:serde total downloads — chrome moth"),
            ("crates-serde-version", "crates:serde max-stable version — brutalist celadon"),
            ("crates-serde-recent", "crates:serde 90-day recent downloads — chrome graphite"),
            ("crates-serde-license", "crates:serde license (versions[0]) — automata teal"),
        ],
    ),
    (
        "Real-data badges — OpenSSF Scorecard",
        [
            ("scorecard-tokio-trust", "scorecard:tokio-rs/tokio aggregate trust score 0-10 — chrome moth"),
            ("scorecard-tokio-review", "scorecard:tokio-rs/tokio Code-Review check — brutalist signal (light)"),
            ("scorecard-tokio-maintained", "scorecard:tokio-rs/tokio Maintained check — automata amber"),
        ],
    ),
    (
        "Real-data badges — GitHub Actions DORA",
        [
            (
                "dora-fastapi-deploy-freq",
                "dora:fastapi/fastapi deploy frequency /day, 30-day window "
                "(needs HW_GITHUB_TOKENS; degrades to --) — chrome lightning",
            ),
        ],
    ),
    (
        "Full connector cards — all-crates + all-Scorecard",
        [
            (
                "crates-all-strip",
                "all crates.io output (VERSION/DOWNLOADS/RECENT/LICENSE) in one strip — rust card in brutalist UMBER",
            ),
            (
                "scorecard-all-strip",
                "all OpenSSF Scorecard output — real scores + a real ZERO (TOKEN) + TWO n/a "
                "causes (VULNS absent, SIGNED scored -1) — brutalist ONYX",
            ),
        ],
    ),
    (
        "Full-band marquees — category + state + empty-value coverage",
        [
            (
                "marquee-fullband-brutalist",
                "volume(hero STARS + pypi DOWNLOADS) / activity(BUILD pass, COVERAGE warn, "
                "TESTS crit, ISSUES --) / identity — brutalist celadon (module)",
            ),
            (
                "marquee-fullband-chrome",
                "same full band, crates DOWNLOADS volume cell — chrome moth (module)",
            ),
            (
                "marquee-fullband-automata",
                "same full band, npm DOWNLOADS volume cell — automata bone (ribbon)",
            ),
        ],
    ),
    # ── State badges with real CI/CD titles ──
    (
        "State badges — real CI/CD allowlist coverage",
        [
            ("state-build-passing", "BUILD passing — brutalist celadon"),
            ("state-tests-failing", "TESTS failing — chrome abyssal"),
            ("state-coverage-87", "COVERAGE 87% — automata teal"),
            ("state-lint-clean", "LINT clean — brutalist pulse (light)"),
            ("state-deploy-pending", "DEPLOY pending — chrome graphite"),
            ("state-release-stable", "RELEASE stable — automata amber"),
        ],
    ),
    # ── : Strip coverage additions ──
    (
        "Strip variety additions — state, multi-provider, automata subtitle",
        [
            ("strip-state-bearing-chrome", "BUILD passing + multi-metric — chrome lightning + GitHub subtitle"),
            ("strip-2-metric-automata-teal", "2-metric automata strip with GitHub subtitle — teal"),
            ("strip-multi-provider-brutalist", "3-provider strip (GH + DOCKER + NPM) — brutalist alloy"),
        ],
    ),
    # ── state-bearing strip coverage across paradigms ──
    (
        "State-bearing strips — real CI/CD titles across paradigms",
        [
            (
                "strip-state-bearing-build-brutalist",
                "BUILD passing + STARS — brutalist celadon (canonical pattern)",
            ),
            ("strip-state-deploy-active-chrome", "DEPLOY active + VERSION + RELEASE — chrome graphite"),
            ("strip-state-tests-failing-automata", "TESTS failing + COVERAGE + BUILD warning — automata amber"),
            ("strip-state-coverage-brutalist-light", "COVERAGE 87% + LINT clean + DEPLOY — brutalist archive (light)"),
        ],
    ),
]


def _is_badge_svg(svg_path: Path) -> bool:
    """Detect whether a proofset SVG renders a badge frame.

    Reads the first 1KB and looks for ``data-hw-type="badge"``. Badge
    sections render as 3-column tables in outputs/README.md while
    strips/stats/charts stay one-per-row.
    """
    if not svg_path.exists():
        return False
    try:
        head = svg_path.read_text(errors="ignore")[:1024]
    except OSError:
        return False
    return 'data-hw-type="badge"' in head


def _svg_genome_and_frame(svg_path: Path) -> tuple[str, str]:
    """Extract (genome, frame_type) from an SVG's root data-hw-* attributes.

    Returns ("unknown", "unknown") when the file is missing or attributes are
    absent. Used by the README emitter to group edge-case sections by genome
    and frame type ().
    """
    if not svg_path.exists():
        return ("unknown", "unknown")
    try:
        head = svg_path.read_text(errors="ignore")[:2048]
    except OSError:
        return ("unknown", "unknown")
    import re

    g = re.search(r'data-hw-genome="([^"]+)"', head)
    f = re.search(r'data-hw-frame="([^"]+)"', head)
    if not f:
        f = re.search(r'data-hw-type="([^"]+)"', head)
    return (g.group(1) if g else "unknown", f.group(1) if f else "unknown")


def _emit_edge_cases_readme_section() -> str:
    """Build the "Edge Cases" section for outputs/README.md.

    organized by genome (brutalist, chrome, automata, mixed)
    then by frame type (badges, strips, stats, charts) within each genome.
    Makes visual review systematic — all chrome badges read together, all
    brutalist strips read together, etc. Each group's primary genome and
    frame type are inferred from the manifest SVGs' data-hw-genome /
    data-hw-frame attributes; groups whose specs span multiple genomes go
    into the "Mixed" bucket.

    Badges render in 3-column tables; strips, stats, charts render
    full-width one-per-row. Direct render only — HTTP and MCP renderings
    are byte-equal (verified by the parity summary below).
    """
    manifest_path = OUT / "proofset" / "parity" / "manifest.json"
    if not manifest_path.exists():
        return ""
    import json

    manifest = json.loads(manifest_path.read_text())
    by_id = {e["spec_id"]: e for e in manifest}
    parity_dir = OUT / "proofset" / "parity"

    # Genome + frame-type ordering for predictable section sequence
    _GENOME_ORDER = ["brutalist", "chrome", "automata", "mixed"]
    _FRAME_ORDER = ["badge", "strip", "stats", "chart", "icon", "marquee-horizontal", "divider", "mixed"]

    # Bucket groups by inferred genome + frame_type
    buckets: dict[str, dict[str, list[tuple[str, list[tuple[str, str]]]]]] = {
        g: {f: [] for f in _FRAME_ORDER} for g in _GENOME_ORDER
    }
    for group_title, entries in _EDGE_CASE_GROUPS:
        present = [(sid, label) for sid, label in entries if sid in by_id]
        if not present:
            continue
        # Infer primary genome + frame_type from the group's manifest entries
        genomes = {_svg_genome_and_frame(parity_dir / by_id[sid]["direct"])[0] for sid, _ in present}
        frames = {_svg_genome_and_frame(parity_dir / by_id[sid]["direct"])[1] for sid, _ in present}
        group_genome = next(iter(genomes)) if len(genomes) == 1 else "mixed"
        group_frame = next(iter(frames)) if len(frames) == 1 else "mixed"
        if group_genome not in _GENOME_ORDER:
            group_genome = "mixed"
        if group_frame not in _FRAME_ORDER:
            group_frame = "mixed"
        buckets[group_genome][group_frame].append((group_title, present))

    lines: list[str] = [
        "## Edge Cases",
        "",
        "Organized by genome (brutalist → chrome → automata → mixed), then by frame "
        "type (badges → strips → stats → charts) within each genome. Direct-render "
        "SVG only — HTTP and MCP renderings are byte-equal (verified by the parity "
        "summary below). Badges render in 3-column tables; strips, stats, and charts "
        "render full-width.",
        "",
    ]

    def _emit_group(group_title: str, present: list[tuple[str, str]]) -> None:
        all_badges = all(_is_badge_svg(parity_dir / by_id[sid]["direct"]) for sid, _ in present)
        # glyph-paired sections render as 2-column tables
        # (with glyph | without glyph) so the visual comparison reads at a
        # glance instead of being split across 3-column rows. Detect by
        # spec_id pattern: paired sections alternate ``-with-glyph`` and
        # ``-no-glyph`` suffixes.
        is_paired_glyph = all_badges and all(
            sid.endswith("-with-glyph") or sid.endswith("-no-glyph") for sid, _ in present
        )
        # v0.3.9 Spatial Matrix horizontal layout: when all specs share the
        # ``matrix-`` prefix, render as a 4-row x 3-column table where rows
        # are zone configs (label+value / +glyph / +state / all zones) and
        # columns are paradigms (Brutalist / Chrome / Automata). Reads
        # left-to-right as a comparison across paradigms for the same zone
        # config — generic 3-column chunking grouped by index, losing the
        # row-as-config structure.
        is_spatial_matrix = all_badges and all(sid.startswith("matrix-") for sid, _ in present)
        lines.append(f"#### {group_title}")
        lines.append("")
        if is_spatial_matrix:
            _MATRIX_PARADIGMS = ["brutalist", "chrome", "automata"]
            _MATRIX_CONFIGS = [
                ("label-value", "label + value"),
                ("glyph-label-value", "+ glyph"),
                ("state", "+ state indicator"),
                ("glyph-state", "all zones"),
            ]
            # Index specs by (config_slug, paradigm_slug). spec_id pattern:
            # ``matrix-{config_slug}-{paradigm_slug}`` where paradigm_slug
            # is the trailing token (brutalist/chrome/automata).
            cell_by_key: dict[tuple[str, str], tuple[str, str]] = {}
            for spec_id, label in present:
                paradigm_slug = ""
                for candidate in _MATRIX_PARADIGMS:
                    if spec_id.endswith(f"-{candidate}"):
                        paradigm_slug = candidate
                        break
                if not paradigm_slug:
                    continue
                config_slug = spec_id[len("matrix-") : -(len(paradigm_slug) + 1)]
                cell_by_key[(config_slug, paradigm_slug)] = (spec_id, label)

            # Header row uses paradigm display names.
            header = "| Config | " + " | ".join(p.capitalize() for p in _MATRIX_PARADIGMS) + " |"
            sep = "|---|" + "---|" * len(_MATRIX_PARADIGMS)
            lines.append(header)
            lines.append(sep)
            for config_slug, config_label in _MATRIX_CONFIGS:
                row_cells: list[str] = [f"**{config_label}**"]
                for paradigm_slug in _MATRIX_PARADIGMS:
                    cell = cell_by_key.get((config_slug, paradigm_slug))
                    if cell is None:
                        row_cells.append("")
                        continue
                    spec_id, _label = cell
                    entry = by_id[spec_id]
                    row_cells.append(f"![{spec_id}](proofset/parity/{entry['direct']})<br/>`{spec_id}`")
                lines.append("| " + " | ".join(row_cells) + " |")
            lines.append("")
        elif is_paired_glyph:
            lines.append("| With glyph | Without glyph |")
            lines.append("|---|---|")
            # Pair consecutive specs: with-glyph then no-glyph
            pair_row: list[str] = []
            for spec_id, label in present:
                entry = by_id[spec_id]
                cell = f"**{label}**<br/>`{spec_id}`<br/>![{spec_id}](proofset/parity/{entry['direct']})"
                pair_row.append(cell)
                if len(pair_row) == 2:
                    lines.append("| " + " | ".join(pair_row) + " |")
                    pair_row = []
            if pair_row:
                pair_row.append("")
                lines.append("| " + " | ".join(pair_row) + " |")
            lines.append("")
        elif all_badges:
            lines.append("| | | |")
            lines.append("|---|---|---|")
            row: list[str] = []
            for spec_id, label in present:
                entry = by_id[spec_id]
                cell = f"**{label}**<br/>`{spec_id}`<br/>![{spec_id}](proofset/parity/{entry['direct']})"
                row.append(cell)
                if len(row) == 3:
                    lines.append("| " + " | ".join(row) + " |")
                    row = []
            if row:
                while len(row) < 3:
                    row.append("")
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")
        else:
            for spec_id, label in present:
                entry = by_id[spec_id]
                lines.append(f"**{label}** — `{spec_id}`")
                lines.append("")
                lines.append(f"![{spec_id}](proofset/parity/{entry['direct']})")
                lines.append("")

    for genome in _GENOME_ORDER:
        if not any(buckets[genome][f] for f in _FRAME_ORDER):
            continue
        lines.append(f"### {genome.capitalize()}")
        lines.append("")
        for frame_type in _FRAME_ORDER:
            groups = buckets[genome][frame_type]
            if not groups:
                continue
            for group_title, present in groups:
                _emit_group(group_title, present)
    return "\n".join(lines)


def _emit_parity_readme_section(specs_count: int, passed: int, failed: int) -> str:
    """Build the parity section embedded in outputs/README.md.

    Compact test-report only — full-width artifact embeds live in the
    preceding "Edge Cases" section. PASS/FAIL summary list per spec, plus
    a visual-diff block for any failing spec so divergence between the
    three rendering paths is immediately inspectable.
    """
    if specs_count == 0:
        return ""
    manifest_path = OUT / "proofset" / "parity" / "manifest.json"
    if not manifest_path.exists():
        return ""
    import json

    manifest = json.loads(manifest_path.read_text())

    lines: list[str] = [
        "## CLI / HTTP / MCP Parity (v0.3.9)",
        "",
        f"**{specs_count} specs rendered through all three interfaces** — "
        f"{passed} parity-passed, {failed} parity-failed. Equivalence "
        "verified after normalization (UIDs, timestamps, version strings, "
        "and font data scrubbed). Divergence between paths is a parity bug "
        "per HyperWeave Invariant 9 (CLI/HTTP/MCP feature parity).",
        "",
    ]

    failed_entries = [e for e in manifest if not e["all_match"]]
    passed_entries = [e for e in manifest if e["all_match"]]

    # Pass/fail summary list — terse, scannable.
    lines.extend(["### Summary", ""])
    for entry in passed_entries:
        lines.append(f"- ✓ `{entry['spec_id']}`")
    for entry in failed_entries:
        sid = entry["spec_id"]
        flags = []
        if not entry["parity_direct_http"]:
            flags.append("direct≠http")
        if not entry["parity_direct_mcp"]:
            flags.append("direct≠mcp")
        if not entry["parity_http_mcp"]:
            flags.append("http≠mcp")
        lines.append(f"- ✗ `{sid}` — {', '.join(flags)}")
    lines.append("")

    # Failure diffs — when something is broken, show all 3 paths inline
    # at full width so the divergence is visible.
    if failed_entries:
        lines.extend(["### Parity failures (visual diff)", ""])
        for entry in failed_entries:
            sid = entry["spec_id"]
            lines.append(f"**`{sid}`** — direct vs http vs mcp")
            lines.append("")
            lines.append(f"![{sid} direct](proofset/parity/{entry['direct']})")
            lines.append("")
            lines.append(f"![{sid} http](proofset/parity/{entry['http']})")
            lines.append("")
            lines.append(f"![{sid} mcp](proofset/parity/{entry['mcp']})")
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HyperWeave proof set")
    parser.add_argument("--live", action="store_true", help="Include network-dependent artifacts")
    args = parser.parse_args()

    # Wipe outputs/proofset/ before regenerating so renamed/retired artifacts
    # (paired-variant pairings, telemetry size variants) don't carry stale
    # payloads forward and create false audit noise. READMEs live one level up
    # (outputs/README*.md) and are preserved.
    import shutil

    proofset_dir = OUT / "proofset"
    if proofset_dir.exists():
        stale = sum(1 for _ in proofset_dir.rglob("*.svg"))
        shutil.rmtree(proofset_dir)
        print(f"Cleaned {stale} stale artifacts from {proofset_dir}")

    print("Generating static proof set...")
    total = generate_static()
    print(f"  {total} static artifacts")

    live_total = 0
    if args.live:
        print("Generating live data artifacts...")
        live_total = asyncio.run(generate_live())
        print(f"  {live_total} live artifacts")

    # 3-path parity matrix: render every spec via direct/http/mcp and verify
    # byte-equal output after normalization. Hard-fails the regression net
    # if CLI/HTTP/MCP feature parity drifts (Invariant 9).
    print("Generating 3-path parity matrix...")
    parity_count, parity_passed, parity_failed = asyncio.run(generate_parity_matrix())
    print(f"  {parity_count} parity specs ({parity_passed} passed, {parity_failed} failed)")

    # render-only stats + star-chart specs (skip parity).
    print("Generating render-only edge-case specs...")
    render_only_entries = asyncio.run(_generate_render_only_specs())
    print(f"  {len(render_only_entries)} render-only artifacts")
    if render_only_entries:
        manifest_path = OUT / "proofset" / "parity" / "manifest.json"
        if manifest_path.exists():
            import json as _json

            existing = _json.loads(manifest_path.read_text())
            existing.extend(render_only_entries)
            manifest_path.write_text(_json.dumps(existing, indent=2))

    generate_readme(total, live_total)
    # Append the Edge Cases section + parity summary to the freshly-emitted
    # README.md. Order matters: edge cases (full-width visual review) FIRST,
    # parity summary (test report) LAST. The user needs visible artifacts
    # to inspect, not just a PASS/FAIL list.
    readme_path = OUT / "README.md"
    edge_cases_section = _emit_edge_cases_readme_section()
    parity_section = _emit_parity_readme_section(parity_count, parity_passed, parity_failed)
    appended = []
    if edge_cases_section:
        appended.append(edge_cases_section)
    if parity_section:
        appended.append(parity_section)
    if appended:
        readme_path.write_text(readme_path.read_text() + "\n" + "\n".join(appended))

    grand = total + live_total + parity_count * 3
    print(f"Wrote {grand} artifacts + README to {OUT}/")

    if parity_failed > 0:
        print(f"\nPARITY FAILURES: {parity_failed} specs diverged across direct/http/mcp.")
        print("  See outputs/proofset/parity/manifest.json for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
