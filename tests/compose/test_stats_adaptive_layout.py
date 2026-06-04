"""Adaptive stats zone layout tests."""

from __future__ import annotations

import re
from itertools import pairwise

from hyperweave.compose.engine import compose
from hyperweave.compose.stats_layout import compute_stats_card_height, compute_stats_layout
from hyperweave.config.registry import get_paradigms
from hyperweave.core.models import ComposeSpec


def test_stats_full_zone_payload_cascades_without_overlap() -> None:
    heatmap = [{"date": f"2026-01-{(idx % 28) + 1:02d}", "count": (idx % 8) + 1} for idx in range(364)]
    payload = {
        "username": "eli64s",
        "stars_total": 12847,
        "commits_total": 1203,
        "prs_total": 89,
        "issues_total": 47,
        "contrib_total": 234,
        "streak_days": 47,
        "language_breakdown": [{"name": "Python", "pct": 70.0}],
        "heatmap_grid": heatmap,
    }

    brutalist = compose(ComposeSpec(type="stats", genome_id="brutalist", connector_data=payload))
    assert brutalist.height == 280
    chrome = compose(ComposeSpec(type="stats", genome_id="chrome", connector_data=payload))
    assert chrome.height == 260

    stats = get_paradigms()["chrome"].stats
    layout = compute_stats_layout(
        stats=stats,
        card_width=495,
        card_height=chrome.height,
        username="eli64s",
        bio_text="",
        displays={"stars": "12.8K", "commits": "1,203", "prs": "89", "issues": "47", "contrib": "234", "streak": "47d"},
        metric_entries=[
            {"label": "COMMITS", "value": "1,203"},
            {"label": "PRS", "value": "89"},
            {"label": "ISSUES", "value": "47"},
            {"label": "STREAK", "value": "47d"},
        ],
        activity_bars=[{"week": idx, "count": idx + 1} for idx in range(52)],
        activity_peak=52,
        activity_type="bars_52w",
        languages=[],
        heatmap_grid=heatmap,
        area_tiers=[],
        has_activity=True,
        has_heatmap=True,
        has_proportional_bar=True,
    )
    assert layout.texts["chrome_hero_value"].y == 98.0
    assert layout.texts["chrome_activity_label"].y == 181.0
    assert layout.lines["chrome_footer_rule"].y1 == 232.0
    assert [(slot.label_y, slot.value_y) for slot in layout.metric_slots] == [(135.0, 158.0)] * 4

    brutalist_stats = get_paradigms()["brutalist"].stats
    brutalist_layout = compute_stats_layout(
        stats=brutalist_stats,
        card_width=495,
        card_height=brutalist.height,
        username="eli64s",
        bio_text="",
        displays={"stars": "12.8K", "commits": "1,203", "prs": "89", "issues": "47", "contrib": "234", "streak": "47d"},
        metric_entries=[
            {"label": "COMMITS", "value": "1,203"},
            {"label": "PRS", "value": "89"},
            {"label": "ISSUES", "value": "47"},
            {"label": "STREAK", "value": "47d"},
        ],
        activity_bars=[{"week": idx, "count": idx + 1} for idx in range(52)],
        activity_peak=52,
        activity_type="bars_52w",
        languages=[{"name": "Python", "pct": 70.0}],
        heatmap_grid=heatmap,
        area_tiers=[],
        has_activity=True,
        has_heatmap=True,
        has_proportional_bar=True,
    )
    assert [(slot.value_y, slot.label_y) for slot in brutalist_layout.metric_slots] == [
        (154.0, 154.0),
        (190.0, 190.0),
        (154.0, 154.0),
        (190.0, 190.0),
    ]


def test_stats_minimal_hero_and_three_metrics_keeps_reference_spacing() -> None:
    result = compose(
        ComposeSpec(
            type="stats",
            genome_id="chrome",
            connector_data={
                "username": "mini",
                "stars_total": 12,
                "metrics": [
                    {"label": "COMMITS", "value": "20", "raw_value": 20},
                    {"label": "PRS", "value": "4", "raw_value": 4},
                    {"label": "ISSUES", "value": "1", "raw_value": 1},
                ],
            },
        )
    )

    assert result.height == 198
    assert "COMMITS" in result.svg


def test_brutalist_three_metric_layout_uses_strip_style_cells() -> None:
    stats = get_paradigms()["brutalist"].stats
    height = compute_stats_card_height(
        stats=stats,
        metric_count=3,
        activity_type="",
        has_activity=False,
        has_heatmap=False,
        has_proportional_bar=False,
    )
    layout = compute_stats_layout(
        stats=stats,
        card_width=495,
        card_height=height,
        username="vllm",
        bio_text="PyPI package",
        displays={"stars": "6.1M", "commits": "—", "prs": "—", "issues": "—", "contrib": "—", "streak": "—"},
        metric_entries=[
            {"label": "VERSION", "value": "0.21.0"},
            {"label": "PYTHON", "value": "<3.15,>=3.10"},
            {"label": "DAILY", "value": "149.7K"},
        ],
        activity_bars=[],
        activity_peak=0,
        languages=[],
        heatmap_grid=[],
        area_tiers=[],
    )

    assert height == 192
    assert layout.metric_divider_xs == [169.0, 332.0]
    slot_positions = [
        (slot.label_x, slot.label_y, slot.value_x, slot.value_y, slot.text_anchor) for slot in layout.metric_slots
    ]
    assert slot_positions == [
        (24.0, 148.0, 155.0, 154.0, "end"),
        (187.0, 148.0, 318.0, 154.0, "end"),
        (350.0, 148.0, 481.0, 154.0, "end"),
    ]
    assert layout.metric_slots[1].value_text_length > 0


def test_chrome_three_metric_layout_uses_full_width_dynamic_columns() -> None:
    stats = get_paradigms()["chrome"].stats
    height = compute_stats_card_height(
        stats=stats,
        metric_count=3,
        activity_type="",
        has_activity=False,
        has_heatmap=False,
        has_proportional_bar=False,
    )
    layout = compute_stats_layout(
        stats=stats,
        card_width=495,
        card_height=height,
        username="zai-org/GLM-5.1",
        bio_text="",
        displays={"stars": "165.9K", "commits": "—", "prs": "—", "issues": "—", "contrib": "—", "streak": "—"},
        metric_entries=[
            {"label": "LIKES", "value": "1,686"},
            {"label": "FILES", "value": "300"},
            {"label": "SPACES", "value": "66"},
        ],
        activity_bars=[],
        activity_peak=0,
        languages=[],
        heatmap_grid=[],
        area_tiers=[],
    )

    assert [slot.value_x for slot in layout.metric_slots] == [97.167, 247.5, 397.833]
    assert layout.metric_divider_xs == [172.333, 322.667]


def test_chrome_six_metric_layout_wraps_to_two_rows() -> None:
    stats = get_paradigms()["chrome"].stats
    metric_entries = [{"label": f"M{idx}", "value": str(idx)} for idx in range(1, 7)]
    height = compute_stats_card_height(
        stats=stats,
        metric_count=len(metric_entries),
        activity_type="",
        has_activity=False,
        has_heatmap=False,
        has_proportional_bar=False,
    )
    layout = compute_stats_layout(
        stats=stats,
        card_width=495,
        card_height=height,
        username="GLM-5.1",
        bio_text="",
        displays={"stars": "175.3K", "commits": "—", "prs": "—", "issues": "—", "contrib": "—", "streak": "—"},
        metric_entries=metric_entries,
        activity_bars=[],
        activity_peak=0,
        languages=[],
        heatmap_grid=[],
        area_tiers=[],
    )

    assert height == 234
    assert [slot.label_y for slot in layout.metric_slots] == [135.0, 135.0, 135.0, 171.0, 171.0, 171.0]
    assert [slot.value_y for slot in layout.metric_slots] == [158.0, 158.0, 158.0, 194.0, 194.0, 194.0]
    assert layout.zones["footer"].y == 206.0


def test_stats_sparkline_activity_renders_without_heatmap_zone() -> None:
    result = compose(
        ComposeSpec(
            type="stats",
            genome_id="chrome",
            connector_data={
                "username": "spark",
                "stars_total": 12,
                "metrics": [{"label": "COMMITS", "value": "20", "raw_value": 20}],
                "activity": {"type": "sparkline_30d", "points": [0.1, 0.6, 0.2, 0.9], "peak_label": "90 PEAK"},
            },
        )
    )

    assert 'data-hw-zone="activity-sparkline"' in result.svg
    assert 'data-hw-zone="heatmap"' not in result.svg
    assert "PEAK · 90<" in result.svg


def test_cellular_stats_without_heatmap_omits_blank_cell_row() -> None:
    result = compose(
        ComposeSpec(
            type="stats",
            genome_id="automata",
            connector_data={
                "username": "compact",
                "stars_total": 12,
                "commits_total": 8,
                "prs_total": 2,
                "issues_total": 1,
                "streak_days": 5,
                "heatmap_grid": [],
            },
        )
    )

    assert result.height < 150
    assert 'data-hw-zone="heatmap"' not in result.svg
    assert 'width="11.08" height="11.08"' not in result.svg


def test_cellular_preserves_temporal_metric_as_fifth_slot() -> None:
    result = compose(
        ComposeSpec(
            type="stats",
            genome_id="automata",
            connector_data={
                "username": "temporal",
                "stars_total": 99,
                "metrics": [
                    {"label": "COMMITS", "value": "1", "raw_value": 1},
                    {"label": "PRS", "value": "2", "raw_value": 2},
                    {"label": "ISSUES", "value": "3", "raw_value": 3},
                    {"label": "CONTRIB", "value": "4", "raw_value": 4},
                    {"label": "STREAK", "value": "9d", "raw_value": 9},
                ],
            },
        )
    )

    labels = re.findall(r'class="[^"]+-mlb">([^<]+)</text>', result.svg)
    assert labels[:5] == ["STARS", "COMMITS", "PRS", "ISSUES", "STREAK"]
    assert "CONTRIB" not in labels[:5]


def test_cellular_preserves_non_github_temporal_metric_when_truncating() -> None:
    result = compose(
        ComposeSpec(
            type="stats",
            genome_id="automata",
            connector_data={
                "provider": "pypi",
                "identity": "temporal-package",
                "hero": {"label": "DOWNLOADS", "value": "10K"},
                "metrics": [
                    {"label": "VERSION", "value": "1.0.0"},
                    {"label": "PYTHON", "value": "3.10-3.14"},
                    {"label": "LICENSE", "value": "MIT"},
                    {"label": "FILES", "value": "92"},
                    {"label": "UPDATED", "value": "May 2026"},
                ],
            },
        )
    )

    labels = re.findall(r'class="[^"]+-mlb">([^<]+)</text>', result.svg)
    assert labels[:5] == ["DOWNLOADS", "VERSION", "PYTHON", "LICENSE", "UPDATED"]
    assert "FILES" not in labels[:5]


def test_cellular_subtitle_truncates_without_textlength_compression() -> None:
    result = compose(
        ComposeSpec(
            type="stats",
            genome_id="automata",
            connector_data={
                "username": "arxiv-paper",
                "hero_label": "PAPER",
                "hero_value": "2602.15763",
                "identity_subtitle": "GLM-5: From Vibe Coding to Agentic Engineering with a very long subtitle",
                "bio": "2602.15763 · GLM-5-Team and a long author consortium",
                "metrics": [
                    {"label": "AUTHORS", "value": "186"},
                    {"label": "CATEGORIES", "value": "cs.LG, cs.CL"},
                ],
            },
        )
    )

    match = re.search(r'<text[^>]*class="[^"]+-bio"[^>]*>(.*?)</text>', result.svg)
    assert match is not None
    assert "..." in match.group(1)
    assert "textLength" not in match.group(0)
    assert "lengthAdjust" not in match.group(0)
    assert "HYPERWEAVE" in result.svg


def test_cellular_stats_with_long_schema_order_metrics_does_not_overflow() -> None:
    result = compose(
        ComposeSpec(
            type="stats",
            genome_id="automata",
            connector_data={
                "provider": "arxiv",
                "identity": "GLM-5-Team et al.",
                "hero": {"label": "PAPER", "value": "2602.15763"},
                "metrics": [
                    {"label": "AUTHORS", "value": "186", "raw_value": 186},
                    {"label": "CATEGORIES", "value": "cs.LG, cs.CL"},
                    {"label": "PUBLISHED", "value": "Feb 2026"},
                ],
            },
        )
    )

    assert "PUBLISHED" not in result.svg
    assert re.search(r'class="[^"]+-mvg"[^>]*>—</text>', result.svg) is None


def test_arxiv_automata_identity_truncates_instead_of_textlength_compression() -> None:
    result = compose(
        ComposeSpec(
            type="stats",
            genome_id="automata",
            connector_data={
                "provider": "arxiv",
                "identity": "GLM-5: from Vibe Coding to Agentic Engineering and Beyond",
                "identity_subtitle": "2602.15763",
                "hero": {"label": "PAPER", "value": "2602.15763"},
                "metrics": [
                    {"label": "AUTHORS", "value": "186", "raw_value": 186},
                    {"label": "CATEGORIES", "value": "cs.LG, cs.CL"},
                ],
            },
        )
    )

    username = re.search(r'<text[^>]*class="[^"]+-username"[^>]*>([^<]+)</text>', result.svg)
    assert username is not None
    assert "..." in username.group(1)
    assert "textLength" not in username.group(0)


def test_stats_zone_y_positions_cascade() -> None:
    stats = get_paradigms()["chrome"].stats
    height = compute_stats_card_height(
        stats=stats,
        metric_count=3,
        activity_type="sparkline_30d",
        has_activity=True,
        has_heatmap=False,
        has_proportional_bar=False,
    )
    layout = compute_stats_layout(
        stats=stats,
        card_width=495,
        card_height=height,
        username="spark",
        bio_text="",
        displays={"stars": "12", "commits": "20", "prs": "4", "issues": "1", "contrib": "—", "streak": "—"},
        metric_entries=[
            {"label": "COMMITS", "value": "20"},
            {"label": "PRS", "value": "4"},
            {"label": "ISSUES", "value": "1"},
        ],
        activity_bars=[{"week": 0, "count": 1}],
        activity_peak=1,
        activity_type="sparkline_30d",
        languages=[],
        heatmap_grid=[],
        area_tiers=[],
        has_activity=True,
        has_heatmap=False,
        has_proportional_bar=False,
    )

    ordered = [layout.zones[name] for name in ("header", "hero", "metrics", "activity", "footer")]
    assert all(next_zone.y >= zone.end_y for zone, next_zone in pairwise(ordered))
