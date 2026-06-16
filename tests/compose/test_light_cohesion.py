"""v0.3.13 light-scholar cohesion pins.

The brutalist light variants are made to read as one family by a single rule
applied from shared light partials/tokens: STRUCTURE (rails, borders,
perimeters) is ``--dna-ink-primary``; ACCENT (``--dna-signal`` / seam) is a SPOT
(status dots, seam veins, thin caps); each glyph contrasts its zone (ink-mass
shapes carry paper knockouts, dark panels carry accent glyphs). Because the
fixes live in shared partials + substrate-aware tokens, all six scholars inherit
them — parametrized here to prove propagation.
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec
from tests.compose.test_stats_brutalist import MOCK_STATS

# All 14 light scholars (6 original + 8 v0.3.13 substrates). The structural
# pins below derive from shared light partials, so every variant inherits them.
LIGHT_VARIANTS = [
    "archive",
    "signal",
    "pulse",
    "depth",
    "afterimage",
    "primer",
    "ferro",
    "ozalid",
    "sulfur",
    "tyrian",
    "indigo",
    "patina",
    "graphite",
    "cyan",
]


def _svg(frame: str, variant: str, **kw: object) -> str:
    return compose(ComposeSpec(type=frame, genome_id="brutalist", variant=variant, **kw)).svg  # type: ignore[arg-type]


@pytest.mark.parametrize("variant", LIGHT_VARIANTS)
def test_icon_light_is_ink_mass_with_paper_glyph(variant: str) -> None:
    """Light icon = --dna-ink-primary shape (ink mass) + --dna-surface glyph
    (paper knockout). NOT the v0.3.2 paper-fill + signal-dim brown glyph that
    light-scholar review flagged as weightless + accent-as-structure."""
    svg = _svg("icon", variant, title="GH", glyph="github")
    assert 'fill="var(--dna-ink-primary)"' in svg, f"{variant}: icon shape must carry ink mass"
    # Glyph is a paper (surface) knockout — NOT the retired signal-dim brown.
    glyph_fills = re.findall(r'<path d="[^"]+" fill="(var\(--dna-[a-z-]+\))"', svg)
    assert glyph_fills, f"{variant}: icon glyph path not found"
    assert all(f == "var(--dna-surface)" for f in glyph_fills), (
        f"{variant}: icon glyph must be a paper knockout, got {glyph_fills}"
    )


def test_icon_dark_glyph_unchanged() -> None:
    """Dark icon keeps the v0.3.2 treatment: surface fill + signal-dim glyph."""
    svg = _svg("icon", "celadon", title="GH", glyph="github")
    assert re.search(r'<path d="[^"]+" fill="var\(--dna-signal-dim\)"', svg), (
        "dark icon glyph must stay --dna-signal-dim (byte-equal)"
    )


@pytest.mark.parametrize("variant", LIGHT_VARIANTS)
def test_strip_light_left_rail_is_ink(variant: str) -> None:
    """Light strip's 6px left rail is ink (manuscript margin), not accent —
    structure is ink on light, matching the badge + stats left rails."""
    svg = _svg("strip", variant, title="REPO", value="STARS:2.9k,BUILD:passing").replace("\n", " ")
    assert re.search(r'<rect width="6(?:\.0)?" height="52" fill="var\(--dna-ink-primary\)"', svg), (
        f"{variant}: strip left rail (6px) must be --dna-ink-primary"
    )


@pytest.mark.parametrize("variant", LIGHT_VARIANTS)
def test_strip_light_glyph_is_accent_on_dark_panel(variant: str) -> None:
    """The strip identity glyph sits on the DARK brand panel, so it carries the
    accent (glyph-inner) — accent-on-dark, the converse of the icon's
    ink-on-paper. Confirms the glyph rule is zone-aware, not a blanket ink."""
    svg = _svg("strip", variant, title="REPO", value="STARS:2.9k,BUILD:passing", glyph="github").replace("\n", " ")
    assert re.search(r'data-hw-zone="brand-glyph".*?fill="var\(--dna-glyph-inner', svg), (
        f"{variant}: strip glyph on the dark panel must use the accent (glyph-inner)"
    )


@pytest.mark.parametrize("variant", LIGHT_VARIANTS)
def test_marquee_light_cap_is_ink_not_paper(variant: str) -> None:
    """Light marquee bookend caps carry the genome INK hex (ink mass), not the
    paper surface — the weightless-cap fix. Compares the rendered cap fill to
    the SVG-root --dna-ink-primary / --dna-surface declarations."""
    svg = _svg("marquee-horizontal", variant, value="STARS:2.9k,FORKS:278,BUILD:passing").replace("\n", " ")
    ink = re.search(r"--dna-ink-primary:\s*(#[0-9A-Fa-f]{6})", svg)
    surface = re.search(r"--dna-surface:\s*(#[0-9A-Fa-f]{6})", svg)
    assert ink and surface, f"{variant}: missing ink/surface token declarations"
    cap = re.search(r'data-hw-zone="cap-left">\s*<rect[^>]*fill="(#[0-9A-Fa-f]{6})"', svg)
    assert cap, f"{variant}: marquee left cap rect not found"
    assert cap.group(1).upper() == ink.group(1).upper(), (
        f"{variant}: cap fill {cap.group(1)} must be ink {ink.group(1)} (not paper {surface.group(1)})"
    )


# ── v0.3.13 horizontal metric row + streak momentum tint ──


def _stats(variant: str) -> str:
    return compose(
        ComposeSpec(
            type="stats", genome_id="brutalist", variant=variant, stats_username="eli64s", connector_data=MOCK_STATS
        )
    ).svg


@pytest.mark.parametrize("variant", LIGHT_VARIANTS)
def test_stats_light_is_horizontal_row_300(variant: str) -> None:
    """Light stats card uses the 300-tall horizontal metric row: center-anchored
    columns (accent label over 27px ink value), distinct from the dark 2x2 grid."""
    svg = _stats(variant)
    assert 'viewBox="0 0 495 300"' in svg, f"{variant}: light card must be 495x300 (row layout)"
    assert re.search(r"-sl \{[^}]*?fill:\s*var\(--dna-signal\)", svg, re.S), f"{variant}: row labels must be accent"
    assert re.search(r"-sv \{[^}]*?font-size:\s*27px[^}]*?fill:\s*var\(--dna-ink-primary\)", svg, re.S), (
        f"{variant}: row values must be 27px ink"
    )
    assert svg.count('text-anchor="middle"') >= 8, f"{variant}: row metrics must be center-anchored"


def test_stats_light_row_column_centers_pulse() -> None:
    """The 4-metric row resolves to the reference column centers + dividers + 300 height."""
    from hyperweave.compose.stats.layout import compute_stats_card_height, compute_stats_layout
    from hyperweave.config.registry import get_paradigms

    ps = get_paradigms()["brutalist"].stats
    h = compute_stats_card_height(
        stats=ps,
        metric_count=4,
        activity_type="bars_52w",
        has_activity=True,
        has_heatmap=False,
        has_proportional_bar=True,
        substrate_kind="light",
    )
    layout = compute_stats_layout(
        stats=ps,
        card_width=495,
        card_height=h,
        username="x",
        bio_text="x",
        displays={"stars": "1", "commits": "1", "prs": "1", "issues": "1", "contrib": "1", "streak": "1"},
        metric_entries=[{"label": label, "value": "1"} for label in ("COMMITS", "ISSUES", "PRS", "STREAK")],
        activity_bars=[{"count": 1}],
        activity_peak=1,
        languages=[{"name": "Py", "pct": 100}],
        heatmap_grid=[],
        area_tiers=[],
        substrate_kind="light",
    )
    assert h == 300
    assert [s.value_x for s in layout.metric_slots] == [78.375, 191.125, 303.875, 416.625]
    assert layout.metric_divider_xs == [134.75, 247.5, 360.25]
    assert all(s.text_anchor == "middle" for s in layout.metric_slots)


@pytest.mark.parametrize("variant", LIGHT_VARIANTS)
def test_stats_light_streak_momentum_tint(variant: str) -> None:
    """A STREAK metric (>=7 days) earns a per-column accent momentum tint at 0.10
    opacity — decorative reinforcement behind the column (label+value still carry
    the meaning)."""
    svg = _stats(variant)
    assert re.search(r'data-hw-zone="momentum-tint"[^>]*fill="var\(--dna-signal\)"[^>]*opacity="0\.1', svg), (
        f"{variant}: STREAK column must carry the accent momentum tint"
    )


def test_stats_dark_stays_grid_no_row_no_tint() -> None:
    """Dark stats keep the 2x2 grid — no 300-tall row, no momentum tint."""
    svg = _stats("celadon")
    assert 'viewBox="0 0 495 300"' not in svg, "dark card must not adopt the 300-tall row layout"
    assert "momentum-tint" not in svg, "dark card must not emit the momentum tint"


@pytest.mark.parametrize("variant", LIGHT_VARIANTS)
def test_strip_light_has_ink_bookend(variant: str) -> None:
    """Light strips terminate in an ink bookend with an accent liveness/state
    square — closure the dark reclaim-trailing strip omits."""
    svg = _svg("strip", variant, title="REPO", value="STARS:2.9k,COMMITS:235,STREAK:33").replace("\n", " ")
    assert 'data-hw-zone="bookend"' in svg, f"{variant}: light strip must render the ink bookend terminus"


def test_badge_light_ground_panel_butts_at_left_panel() -> None:
    """The light badge GROUND panel starts at left_panel_width (no separator-zone
    gap); the 2px accent seam draws on top of the boundary."""
    svg = _svg("badge", "archive", title="PYPI", value="v0.3.0", glyph="python")
    left = re.search(r'<rect width="([\d.]+)" height="20" fill="var\(--dna-ink-primary\)"', svg)
    right = re.search(r'<rect x="([\d.]+)" width="[\d.]+" height="20" fill="var\(--dna-surface\)"', svg)
    assert left and right, "badge must render ink left + ground right panels"
    assert float(left.group(1)) == float(right.group(1)), (
        f"ground panel x ({right.group(1)}) must equal left panel width ({left.group(1)}) — no gap"
    )


def test_stats_light_activity_bars_fit_content_width() -> None:
    """Row activity bars fit within the content margin (x=22 .. card_width-22) so
    they align with the metric row + language bar, instead of overrunning at the
    dark card's fixed stride."""
    from hyperweave.compose.stats.layout import compute_stats_card_height, compute_stats_layout
    from hyperweave.config.registry import get_paradigms

    ps = get_paradigms()["brutalist"].stats
    h = compute_stats_card_height(
        stats=ps,
        metric_count=4,
        activity_type="bars_52w",
        has_activity=True,
        has_heatmap=False,
        has_proportional_bar=True,
        substrate_kind="light",
    )
    layout = compute_stats_layout(
        stats=ps,
        card_width=495,
        card_height=h,
        username="x",
        bio_text="x",
        displays={k: "1" for k in ("stars", "commits", "prs", "issues", "contrib", "streak")},
        metric_entries=[{"label": label, "value": "1"} for label in ("COMMITS", "ISSUES", "PRS", "STREAK")],
        activity_bars=[{"count": 1} for _ in range(52)],
        activity_peak=1,
        languages=[{"name": "Py", "pct": 100}],
        heatmap_grid=[],
        area_tiers=[],
        substrate_kind="light",
    )
    assert layout.activity_bars[0].x == 22.0, "first activity bar starts at the content left edge"
    right = max(b.x + b.w for b in layout.activity_bars)
    assert right <= 474.0, f"row activity bars must fit within the content margin (~473); got {right}"


def test_stats_light_header_square_and_baseline_aligned() -> None:
    """Row status square centers with the 40px-header username (y=16, lower than
    the dark 32px-header literal y=12), and the activity baseline ends at the
    content margin (473) instead of sticking out past the fitted bars."""
    from hyperweave.compose.stats.layout import compute_stats_card_height, compute_stats_layout
    from hyperweave.config.registry import get_paradigms

    ps = get_paradigms()["brutalist"].stats
    kw = dict(
        stats=ps,
        metric_count=4,
        activity_type="bars_52w",
        has_activity=True,
        has_heatmap=False,
        has_proportional_bar=True,
    )
    h = compute_stats_card_height(substrate_kind="light", **kw)  # type: ignore[arg-type]
    layout = compute_stats_layout(
        stats=ps,
        card_width=495,
        card_height=h,
        username="x",
        bio_text="x",
        displays={k: "1" for k in ("stars", "commits", "prs", "issues", "contrib", "streak")},
        metric_entries=[{"label": label, "value": "1"} for label in ("COMMITS", "ISSUES", "PRS", "STREAK")],
        activity_bars=[{"count": 1} for _ in range(52)],
        activity_peak=1,
        languages=[{"name": "Py", "pct": 100}],
        heatmap_grid=[],
        area_tiers=[],
        substrate_kind="light",
    )
    assert layout.rects["brutalist_status_dot"].y == 16.0, "row status square must center with the header text"
    assert layout.lines["activity_baseline"].x2 == 473.0, "activity baseline must end at the content margin"


def test_stats_light_language_bar_fills_content_width() -> None:
    """The row language bar fills the full content width (segments + a faint
    remainder) so it reads complete, like the dark card's panel track — instead
    of trailing off into empty cream."""
    svg = _stats("pulse")
    segs = re.findall(r'<rect x="([\d.]+)" y="[\d.]+" width="([\d.]+)" height="14', svg)
    assert segs, "row language segments must render"
    right_edge = max(float(x) + float(w) for x, w in segs)
    assert right_edge >= 470.0, f"language bar must fill to the content edge (~473); got {right_edge}"
