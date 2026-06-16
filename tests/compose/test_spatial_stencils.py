"""Spatial-layout stencil contracts for frame templates."""

from __future__ import annotations

import re
from pathlib import Path

from hyperweave.compose.chart.layout import compute_chart_layout
from hyperweave.compose.engine import compose
from hyperweave.compose.stats.layout import compute_stats_card_height, compute_stats_layout
from hyperweave.config.registry import get_paradigms, reset_registry
from hyperweave.core.models import ComposeSpec

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_ROOT = ROOT / "src/hyperweave/templates"
GEOMETRY_STENCIL_DENYLIST: set[Path] = set()
JINJA_EXPR_ARITHMETIC = re.compile(
    r"\{\{(?:(?!\}\}).)*(?:"
    r"\b[a-zA-Z_][\w.]*\s*[-+*/]\s*(?:\d|[a-zA-Z_])|"
    r"\d+(?:\.\d+)?\s*[-+*/]\s*[a-zA-Z_]"
    r")(?:(?!\}\}).)*\}\}"
)
JINJA_SET_ARITHMETIC = re.compile(
    r"\{%\s*set\s+[^%]*(?:"
    r"\b[a-zA-Z_][\w.]*\s*[-+*/]\s*(?:\d|[a-zA-Z_])|"
    r"\d+(?:\.\d+)?\s*[-+*/]\s*[a-zA-Z_]"
    r")(?:(?!%\}).)*%\}"
)
HEX_LITERAL = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}\b")
QUOTED_STRING = re.compile(r"""(?P<quote>['"])(?:\\.|(?!\1).)*\1""")
GEOMETRY_NUMERIC_ATTR = re.compile(r'(?<!-)\b(?:x|y|x1|x2|y1|y2|width|height|rx|r|cx|cy)="-?(?:\d+(?:\.\d+)?|\.\d+)?"')


def _template_files() -> list[Path]:
    files = [*TEMPLATE_ROOT.rglob("*.j2"), *TEMPLATE_ROOT.rglob("*.svg")]
    return sorted({path for path in files if path.is_file()})


def _line_without_quoted_strings(line: str) -> str:
    return QUOTED_STRING.sub('""', line)


def test_templates_do_not_compute_coordinates_in_jinja() -> None:
    """Templates consume named geometry; they do not derive coordinates."""
    offenders: list[str] = []
    for path in _template_files():
        text = path.read_text()
        for lineno, line in enumerate(text.splitlines(), start=1):
            expression_line = _line_without_quoted_strings(line)
            if JINJA_EXPR_ARITHMETIC.search(expression_line) or JINJA_SET_ARITHMETIC.search(expression_line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "Jinja coordinate arithmetic found:\n" + "\n".join(offenders)


def test_templates_do_not_embed_hex_color_literals() -> None:
    """Color literals come from genome/config/resolver context, not templates."""
    offenders: list[str] = []
    for path in _template_files():
        text = path.read_text()
        for lineno, line in enumerate(text.splitlines(), start=1):
            if HEX_LITERAL.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "Template hex literals found:\n" + "\n".join(offenders)


def test_core_frame_content_does_not_embed_geometry_literals() -> None:
    """Stencil geometry comes from layout objects or structured records."""
    offenders: list[str] = []
    for path in _template_files():
        if path in GEOMETRY_STENCIL_DENYLIST:
            continue
        text = path.read_text()
        for lineno, line in enumerate(text.splitlines(), start=1):
            scan_line = re.sub(r'\b[xy][12]="(?:0|1)"', "", line) if "<linearGradient" in line else line
            if GEOMETRY_NUMERIC_ATTR.search(scan_line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "Hardcoded core-frame geometry attributes found:\n" + "\n".join(offenders)


def test_chrome_stats_template_pins_material_geometry_to_stats_layout() -> None:
    """Rendered chrome stats frame follows StatsLayout when config changes."""
    reset_registry()
    stats = get_paradigms()["chrome"].stats
    metric_entries = [
        {"label": "COMMITS", "value": "1,203"},
        {"label": "PRS", "value": "89"},
        {"label": "ISSUES", "value": "47"},
        {"label": "STREAK", "value": "47d"},
    ]
    card_height = compute_stats_card_height(
        stats=stats,
        metric_count=len(metric_entries),
        has_activity=False,
        has_heatmap=False,
        has_proportional_bar=False,
    )
    layout = compute_stats_layout(
        stats=stats,
        card_width=495,
        card_height=card_height,
        username="eli64s",
        bio_text="",
        displays={"stars": "12.8K", "commits": "1,203", "prs": "89", "issues": "47", "contrib": "234", "streak": "47d"},
        metric_entries=metric_entries,
        activity_bars=[],
        activity_peak=0,
        languages=[],
        heatmap_grid=[],
        area_tiers=[],
    )
    svg = compose(
        ComposeSpec(
            type="stats",
            genome_id="chrome",
            stats_username="eli64s",
            connector_data={
                "username": "eli64s",
                "stars_total": 12847,
                "commits_total": 1203,
                "prs_total": 89,
                "issues_total": 47,
                "contrib_total": 234,
                "streak_days": 47,
                "language_breakdown": [],
                "heatmap_grid": [],
            },
        )
    ).svg

    assert f'width="{layout.chrome_outer_rect.w}" height="{layout.chrome_outer_rect.h}"' in svg
    assert f'x2="{layout.chrome_hero_rule.x2}" y2="{layout.chrome_hero_rule.y2}"' in svg
    assert f'x2="{layout.chrome_footer_rule.x2}" y2="{layout.chrome_footer_rule.y2}"' in svg


def test_cellular_stats_pins_layout_to_template() -> None:
    """Rendered cellular stats frame follows StatsLayout."""
    reset_registry()
    stats = get_paradigms()["cellular"].stats
    metric_entries = [
        {"label": "COMMITS", "value": "1,203"},
        {"label": "PRS", "value": "89"},
        {"label": "ISSUES", "value": "47"},
        {"label": "CONTRIB", "value": "234"},
        {"label": "STREAK", "value": "47d"},
    ]
    card_height = compute_stats_card_height(
        stats=stats,
        metric_count=len(metric_entries),
        has_activity=False,
        has_heatmap=False,
        has_proportional_bar=False,
    )
    layout = compute_stats_layout(
        stats=stats,
        card_width=stats.card_width,
        card_height=card_height,
        username="karpathy",
        bio_text="Python / 39 repos",
        displays={"stars": "12.8K", "commits": "1,203", "prs": "89", "issues": "47", "contrib": "234", "streak": "47d"},
        metric_entries=metric_entries,
        activity_bars=[],
        activity_peak=0,
        languages=[],
        heatmap_grid=[],
        area_tiers=[],
    )
    svg = compose(
        ComposeSpec(
            type="stats",
            genome_id="automata",
            stats_username="karpathy",
            connector_data={
                "username": "karpathy",
                "bio": "Python / 39 repos",
                "stars_total": 12847,
                "commits_total": 1203,
                "prs_total": 89,
                "issues_total": 47,
                "contrib_total": 234,
                "streak_days": 47,
                "language_breakdown": [],
                "heatmap_grid": [],
            },
        )
    ).svg

    assert 'width="530"' in svg
    assert f'width="{layout.cellular_outer_rect.w}" height="{layout.cellular_outer_rect.h}"' in svg
    assert f'x2="{layout.lines["cellular_header_rule"].x2}" y2="{layout.lines["cellular_header_rule"].y2}"' in svg


def test_chrome_chart_template_pins_header_collision_and_rules_to_chart_layout() -> None:
    """Rendered chrome chart follows ChartLayout for header and rules."""
    reset_registry()
    repo = "averylongownername/a-very-long-repository-name-that-needs-clamping-for-the-header-slot"
    chart = get_paradigms()["chrome"].chart
    layout = compute_chart_layout(
        chart=chart,
        repo=repo,
        header_label="A-VERY-LONG-REPOSITORY-NAME-THAT-NEEDS-CLAMPING-FOR-THE-HEADER-SLOT · GITHUB",
    )
    assert layout.header_identity_text_length > 0

    svg = compose(
        ComposeSpec(
            type="chart",
            genome_id="chrome",
            chart_owner="averylongownername",
            chart_repo="a-very-long-repository-name-that-needs-clamping-for-the-header-slot",
            connector_data={
                "repo": repo,
                "current_stars": 2850,
                "points": [
                    {"date": "2025-01-01T00:00:00Z", "count": 100},
                    {"date": "2025-06-01T00:00:00Z", "count": 1200},
                    {"date": "2026-01-01T00:00:00Z", "count": 2850},
                ],
            },
        )
    ).svg

    assert f'textLength="{layout.header_identity_text_length}"' in svg
    assert f'x2="{layout.chrome_header_rule.x2}" y2="{layout.chrome_header_rule.y2}"' in svg
    assert f'x2="{layout.chrome_footer_rule.x2}" y2="{layout.chrome_footer_rule.y2}"' in svg
    assert re.search(r">\s*004\s*<", svg) is None


def test_brutalist_chart_pins_layout_to_template() -> None:
    """Rendered brutalist chart frame follows ChartLayout."""
    reset_registry()
    repo = "eli64s/readme-ai"
    chart = get_paradigms()["brutalist"].chart
    layout = compute_chart_layout(chart=chart, repo=repo, header_label="README-AI · GITHUB")
    svg = compose(
        ComposeSpec(
            type="chart",
            genome_id="brutalist",
            chart_owner="eli64s",
            chart_repo="readme-ai",
            connector_data={
                "repo": repo,
                "current_stars": 2850,
                "points": [
                    {"date": "2025-01-01T00:00:00Z", "count": 100},
                    {"date": "2025-06-01T00:00:00Z", "count": 1200},
                    {"date": "2026-01-01T00:00:00Z", "count": 2850},
                ],
            },
        )
    ).svg

    assert 'width="900"' in svg
    assert f'width="{layout.brutalist_dark_grain_rect.w}" height="{layout.brutalist_dark_grain_rect.h}"' in svg
    assert f'x2="{layout.lines["brutalist_header_rule"].x2}" y2="{layout.lines["brutalist_header_rule"].y2}"' in svg
