"""Primer genome regression coverage."""

from __future__ import annotations

from hyperweave.compose.assembler import fonts_for_frame
from hyperweave.compose.engine import compose
from hyperweave.compose.resolver import resolve
from hyperweave.config.registry import get_genome_specs, get_paradigms
from hyperweave.core.enums import FrameType
from hyperweave.core.models import ComposeSpec
from hyperweave.core.text import measure_text

MOCK_STATS = {
    "username": "eli64s",
    "bio": "Python / 20 repos / AI + Art + Meta",
    "stars_total": 2957,
    "commits_total": 222,
    "prs_total": 2,
    "issues_total": 0,
    "streak_days": 26,
    "top_language": "Python",
    "repo_count": 20,
    "heatmap_grid": [{"date": f"2026-01-{(index % 28) + 1:02d}", "count": (index % 12) + 1} for index in range(52)],
}

MOCK_CHART = {
    "points": [
        {"date": "2025-01-01T00:00:00Z", "count": 100},
        {"date": "2025-04-01T00:00:00Z", "count": 320},
        {"date": "2025-07-01T00:00:00Z", "count": 680},
        {"date": "2025-10-01T00:00:00Z", "count": 1200},
        {"date": "2026-01-01T00:00:00Z", "count": 5200},
        {"date": "2026-04-01T00:00:00Z", "count": 9400},
    ],
    "current_stars": 9400,
    "repo": "eli64s/readme-ai",
}


def test_primer_dispatches_stats_and_chart_to_primer_paradigm() -> None:
    """Primer stats/chart are first-class paradigms, not brutalist delegates."""
    primer = get_genome_specs()["primer"]
    assert primer.paradigms["stats"] == "primer"
    assert primer.paradigms["chart"] == "primer"

    paradigms = get_paradigms()
    assert paradigms["primer"].stats.metric_layout_mode == "primer_editorial"
    assert primer.structural["fill_density"] == "bezier-smooth"

    stats = resolve(ComposeSpec(type="stats", genome_id="primer", connector_data=MOCK_STATS))
    chart = resolve(ComposeSpec(type="chart", genome_id="primer", connector_data=MOCK_CHART))
    assert stats.frame_context["paradigm"] == "primer"
    assert chart.frame_context["paradigm"] == "primer"


def test_primer_font_gate_uses_inter_for_stats_and_chart() -> None:
    """Primer text-bearing proof frames embed Inter + JetBrains Mono only."""
    assert fonts_for_frame(FrameType.STATS, "primer") == frozenset({"inter", "jetbrains-mono"})
    assert fonts_for_frame(FrameType.CHART, "primer") == frozenset({"inter", "jetbrains-mono"})
    assert fonts_for_frame(FrameType.MARQUEE, "primer") == frozenset({"inter", "jetbrains-mono"})

    width = measure_text("deployed", font_family="Inter", font_size=9, font_weight=700, letter_spacing_em=0.06)
    assert 42 <= width <= 47


def test_primer_strip_width_is_content_adaptive() -> None:
    """Primer strip width adapts to metric count via the shared compute_strip_zones
    engine: a 2-metric strip is narrower than a 4-metric one. Regression guard for
    the prior ``strip_min_width: 540`` + ``stretch_cells_to_min_width`` config that
    clamped EVERY primer strip to the full 4-metric width regardless of how many
    metrics it carried (defeating the adaptive layout every other genome uses)."""

    def strip(value: str):
        return compose(
            ComposeSpec(
                type="strip",
                genome_id="primer",
                variant="porcelain",
                title="ELI64S",
                value=value,
                state="passing",
            )
        )

    two = strip("STARS:12.4k,FORKS:1.2k")
    four = strip("COMMITS:222,PRS:2,ISSUES:0,STREAK:26d")
    assert two.width < four.width, f"2-metric ({two.width}) must be narrower than 4-metric ({four.width})"
    assert two.width != 540 and four.width != 540, "width must be content-derived, not the old fixed 540 clamp"
    # Full-bleed 46px card — no canvas inset: an embedded artifact
    # has no page for a shadow to fade into, so the card spans the viewBox.
    assert four.height == 46
    assert 'data-hw-frame="strip"' in four.svg
    assert "COMMITS" in four.svg
    assert "STREAK" in four.svg


def test_primer_stats_card_uses_editorial_layout() -> None:
    """Primer stats render the Inter editorial card, not the brutalist plate."""
    result = compose(
        ComposeSpec(
            type="stats",
            genome_id="primer",
            variant="porcelain",
            stats_username="eli64s",
            connector_data=MOCK_STATS,
            state="passing",
        )
    )
    assert result.width == 480
    assert result.height == 210
    assert "-card-bg" in result.svg
    assert "-hero-value" in result.svg
    assert "Barlow Condensed" not in result.svg
    assert "2,957" in result.svg
    assert "COMMITS" in result.svg


def test_primer_stats_height_is_content_adaptive() -> None:
    """Primer stats height adapts to the data zones present via compute_stats_card_height:
    hero-only (130) < hero+metrics (172) < activity/heatmap card (210). Regression guard
    against the data-blind fixed-height failure mode — the strip's ``== 540`` bug one frame
    over — which the ``height == 210`` assertion above would not catch on its own."""

    def card_height(data: dict[str, object]) -> int:
        return compose(
            ComposeSpec(
                type="stats",
                genome_id="primer",
                variant="porcelain",
                stats_username="eli64s",
                connector_data=data,
                state="passing",
            )
        ).height

    hero_only = card_height({"username": "eli64s", "stars_total": 2957})
    hero_metrics = card_height({"username": "eli64s", "stars_total": 2957, "commits_total": 222, "prs_total": 2})
    with_heatmap = card_height(
        {
            "username": "eli64s",
            "stars_total": 2957,
            "commits_total": 222,
            "prs_total": 2,
            "heatmap_grid": [{"date": f"2026-01-{(i % 28) + 1:02d}", "count": (i % 12) + 1} for i in range(52)],
        }
    )
    assert hero_only < hero_metrics < with_heatmap, (
        f"stats height must grow with data zones, got {hero_only}/{hero_metrics}/{with_heatmap}"
    )
    assert (hero_only, hero_metrics, with_heatmap) == (130, 172, 210)


def test_primer_chart_uses_smooth_area_chart() -> None:
    """Primer chart renders a path, gradient fill, and circle endpoint marker."""
    result = compose(
        ComposeSpec(
            type="chart",
            genome_id="primer",
            variant="porcelain",
            chart_owner="eli64s",
            chart_repo="readme-ai",
            connector_data=MOCK_CHART,
            state="passing",
        )
    )
    assert result.width == 1100
    assert result.height == 660
    assert "-area-fade" in result.svg
    assert "hw-chart-area-smooth" in result.svg
    assert "<path" in result.svg
    assert "<polyline" not in result.svg
    assert 'class="hw-chart-endpoint"' in result.svg
    assert "9,400" in result.svg
