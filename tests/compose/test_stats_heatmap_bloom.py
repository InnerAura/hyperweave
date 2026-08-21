"""Radial-bloom motion on the cellular stats heatmap.

Specimen: ``.archive/v01_v02_v03/genomes/automata/automata_v2/
hyperweave-stats-eli64s-bloom.svg`` (``data-hw-motion="radial-bloom"``). Its
phase model keys each cell to the Manhattan distance from a seed at column 16,
row 3, folded mod 7 and inverted, so equidistant cells fire together and
concentric diamond wavefronts travel outward across the 40x7 lattice.

These guards read the composed artifact, not the layout function beneath it —
the CSS a browser actually applies is the surface that either blooms or
doesn't.
"""

from __future__ import annotations

import re

from hyperweave.compose import compose
from hyperweave.compose.schema import ComposeSpec
from hyperweave.config.registry import get_paradigms

# Cited from the specimen's own delay ladder: 2.618s / 7 phases = 0.374s per
# ring. Every animating rect in the specimen carries one of these seven.
SPECIMEN_DELAYS = ("-0.000s", "-0.374s", "-0.748s", "-1.122s", "-1.496s", "-1.870s", "-2.244s")

# Column 0 of the specimen lattice, rows 0..6, read off the rendered delays:
# distance from (16, 3) is 19, 18, 17, 16, 17, 18, 19 → phases 2, 3, 4, 5, 4,
# 3, 2. The row-3 crest is the seed's own isophase reaching the left edge.
SPECIMEN_COL0_PHASES = (2, 3, 4, 5, 4, 3, 2)


def _stats_svg(**overrides: object) -> str:
    """Compose an automata stats card over a fully-lit contribution grid."""
    grid = [
        {"date": f"2026-01-{(idx % 28) + 1:02d}", "count": (idx % 12) + 1, "level": (idx % 4) + 1} for idx in range(364)
    ]
    spec = ComposeSpec(
        type="stats",
        genome_id="automata",
        variant="bone",
        stats_username="eli64s",
        connector_data={"heatmap_grid": grid, "stars": 2973, "commits": 266},
        **overrides,  # type: ignore[arg-type]
    )
    return compose(spec).svg


def test_bloom_delay_ladder_matches_specimen() -> None:
    """The seven phase classes carry the specimen's exact delay ladder."""
    svg = _stats_svg()
    rules = dict(re.findall(r"\.(hb\d)\{animation:bloom-stats [^;]*infinite (-[\d.]+s);", svg))
    assert len(rules) == 7, f"expected 7 bloom phases, got {sorted(rules)}"
    for phase, delay in enumerate(SPECIMEN_DELAYS):
        assert rules[f"hb{phase}"] == delay, f"hb{phase} delay {rules[f'hb{phase}']} != specimen {delay}"


def test_bloom_phase_follows_manhattan_distance_from_seed() -> None:
    """Column 0 reproduces the specimen's isophase column, crest on row 3.

    The wavefront is what makes this radial rather than a diagonal sweep: the
    phase must fall away symmetrically either side of the seed row, so a
    column far from the seed still reads as an arriving ring.
    """
    svg = _stats_svg()
    stats = get_paradigms()["cellular"].stats
    stride = stats.heatmap_cell_size + stats.heatmap_cell_gap
    x = round(stats.heatmap_x0, 3)
    for row, expected in enumerate(SPECIMEN_COL0_PHASES):
        y = round(stats.heatmap_y0 + row * stride, 3)
        cell = re.search(rf'<rect x="{x}" y="{y}"[^/]*class="(hb\d)"', svg)
        assert cell is not None, f"column 0 row {row} (y={y}) is not animating"
        assert cell.group(1) == f"hb{expected}", f"row {row} phase {cell.group(1)} != hb{expected}"


def test_empty_cells_stay_still() -> None:
    """Level-0 cells carry no phase class — the rings ride real activity.

    Animating the empty tier would advertise contributions that never
    happened, which is the one thing a contribution heatmap may not do.
    """
    grid = [{"date": f"2026-01-{(idx % 28) + 1:02d}", "count": 0, "level": 0} for idx in range(364)]
    svg = compose(
        ComposeSpec(
            type="stats",
            genome_id="automata",
            variant="bone",
            stats_username="eli64s",
            connector_data={"heatmap_grid": grid, "stars": 2973},
        )
    ).svg
    zone = svg[svg.index('<g data-hw-zone="heatmap">') :]
    zone = zone[: zone.index("</g>")]
    assert 'class="hb' not in zone, "empty contribution grid must render a still heatmap"


def test_bloom_animates_opacity_only() -> None:
    """CIM: the keyframe touches opacity and nothing else."""
    svg = _stats_svg()
    keyframe = re.search(r"@keyframes bloom-stats\{(.*?)\}\n", svg)
    assert keyframe is not None, "bloom-stats keyframe missing"
    body = keyframe.group(1)
    assert body == "0%,100%{opacity:0.32}50%{opacity:1}", body
    properties = set(re.findall(r"([a-z-]+):", body))
    assert properties == {"opacity"}, f"non-compositor property in bloom keyframe: {properties}"


def test_reduced_motion_stills_every_heatmap_cell() -> None:
    """prefers-reduced-motion parks the whole lattice at one rest opacity."""
    svg = _stats_svg()
    assert (
        '@media(prefers-reduced-motion:reduce){[data-hw-zone="heatmap"] rect'
        "{animation:none!important;opacity:0.78!important}}" in svg
    )


def test_animated_heatmap_declares_its_motion() -> None:
    """honesty.motion-flag: an animating card may not claim it is static."""
    svg = _stats_svg()
    assert 'data-hw-motion="radial-bloom"' in svg
    assert 'vocabulary="radial-bloom" physics="diffusion"' in svg
    assert 'stagger-regime="radial-phase"' in svg


def test_still_heatmap_keeps_the_static_claim() -> None:
    """No animating cell means the static motion flag is the honest one."""
    grid = [{"date": f"2026-01-{(idx % 28) + 1:02d}", "count": 0, "level": 0} for idx in range(364)]
    svg = compose(
        ComposeSpec(
            type="stats",
            genome_id="automata",
            variant="bone",
            stats_username="eli64s",
            connector_data={"heatmap_grid": grid, "stars": 2973},
        )
    ).svg
    assert 'data-hw-motion="static"' in svg


def test_bloom_period_spans_the_lattice() -> None:
    """Phase count must divide the lattice into visible rings, not noise.

    With ``phases`` equal to the row count, a full ring occupies one phase per
    row and the 40-column axis shows ceil(40 / 7) ≈ 6 wavefronts at once —
    coarse enough to read as travel. A phase count above the column count
    would put every cell in its own phase and the field would read as static
    noise; below 3 and the rings merge into a single global blink.
    """
    stats = get_paradigms()["cellular"].stats
    assert 3 <= stats.heatmap_bloom_phases <= stats.heatmap_cols
    assert stats.heatmap_bloom_phases == stats.heatmap_rows
    assert 0 <= stats.heatmap_bloom_seed_col < stats.heatmap_cols
    assert 0 <= stats.heatmap_bloom_seed_row < stats.heatmap_rows
