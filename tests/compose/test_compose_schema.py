"""Normalized connector schema tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hyperweave.compose.schema import (
    ChartInput,
    MetricSlot,
    coerce_chart_input,
    coerce_stats_input,
    coerce_strip_input,
)
from hyperweave.connectors.data_tokens import ResolvedToken
from hyperweave.core.models import ComposeSpec


def test_coerce_stats_input_handles_github_full_payload() -> None:
    spec = ComposeSpec(type="stats", stats_username="eli64s")
    result = coerce_stats_input(
        {
            "username": "eli64s",
            "stars_total": 12847,
            "commits_total": 1203,
            "prs_total": 89,
            "issues_total": 47,
            "contrib_total": 234,
            "streak_days": 47,
            "top_language": "Python",
            "repo_count": 63,
            "language_breakdown": [{"name": "Python", "pct": 68.5}],
            "heatmap_grid": [{"date": "2026-01-01", "count": 3, "level": 2} for _ in range(14)],
            "extra_provider_field": "ignored",
        },
        spec,
    )

    assert result.identity == "eli64s"
    assert result.hero.value == "12.8K"
    assert result.identity_subtitle == "Python / 63 repos"
    assert result.metrics[0].label == "COMMITS"
    assert result.activity is not None
    assert result.proportional_bar[0].label == "Python"


def test_coerce_stats_input_handles_minimal_payload_and_unknown_fields() -> None:
    spec = ComposeSpec(type="stats", stats_username="anon")
    result = coerce_stats_input({"stars_total": 12, "unknown": {"nested": "ignored"}}, spec)

    assert result.identity == "anon"
    assert result.hero.value == "12"
    assert result.metrics == []
    assert result.activity is None


def test_coerce_stats_input_promotes_data_tokens_to_hero_and_metrics() -> None:
    spec = ComposeSpec(
        type="stats",
        stats_username="GLM-5",
        data_tokens=[
            ResolvedToken(
                kind="live",
                label="STARS",
                value="123",
                ttl=300,
                provider="github",
                identifier="zai-org/GLM-5",
                metric="stars",
                raw_value=123,
            ),
            ResolvedToken(
                kind="live",
                label="DOWNLOADS",
                value="175311",
                ttl=300,
                provider="huggingface",
                identifier="zai-org/GLM-5.1",
                metric="downloads",
                raw_value=175311,
            ),
        ],
    )

    result = coerce_stats_input(None, spec)

    assert result.identity == "GLM-5"
    assert result.hero.label == "GH STARS"
    assert result.hero.value == "123"
    assert result.metrics[0].label == "HF DL"
    assert result.metrics[0].value == "175.3K"
    assert result.provider == "github+huggingface"


def test_coerce_stats_input_appends_data_tokens_to_legacy_payload_and_truncates() -> None:
    spec = ComposeSpec(
        type="stats",
        stats_username="eli64s",
        data_tokens=[
            ResolvedToken(kind="live", label="DOWNLOADS", value="10", ttl=300, provider="pypi", metric="downloads"),
            ResolvedToken(kind="live", label="DOWNLOADS", value="20", ttl=300, provider="npm", metric="downloads"),
        ],
    )

    result = coerce_stats_input(
        {
            "username": "eli64s",
            "stars_total": 100,
            "commits_total": 1,
            "prs_total": 2,
            "issues_total": 3,
            "contrib_total": 4,
            "streak_days": 5,
        },
        spec,
    )

    assert result.hero.label == "STARS"
    assert [metric.label for metric in result.metrics] == ["COMMITS", "PRS", "ISSUES", "CONTRIB", "STREAK", "PYPI DL"]


def test_coerce_chart_input_resolves_star_and_series_aliases() -> None:
    spec = ComposeSpec(type="chart", chart_owner="inneraura", chart_repo="hyperweave")

    current = coerce_chart_input({"current_stars": 2850, "points": [{"date": "2026-01-01", "count": 2850}]}, spec)
    legacy = coerce_chart_input({"stars_total": 2850, "star_history": [{"date": "2026-01-01", "count": 2850}]}, spec)

    assert current.hero.value == "2,850"
    assert legacy.hero.value == "2,850"
    assert current.series_points[0].count == legacy.series_points[0].count


def test_coerce_chart_input_accepts_generic_download_series() -> None:
    spec = ComposeSpec(type="chart")
    result = coerce_chart_input(
        {
            "provider": "pypi",
            "identity": "vllm",
            "hero": {"label": "DOWNLOADS/MO", "value": "6.1M", "raw_value": 6131880},
            "series_label": "DOWNLOADS",
            "series_points": [{"date": "2026-05-23", "count": 149654}],
        },
        spec,
    )

    assert result.identity == "vllm"
    assert result.hero.label == "DOWNLOADS/MO"
    assert result.series_label == "DOWNLOADS"
    assert result.status == "fresh"


def test_coerce_strip_input_resolves_repo_subtitle_aliases() -> None:
    spec = ComposeSpec(type="strip", title="hyperweave", value="STARS:2.9K,FORKS:278")

    repo_slug = coerce_strip_input({"repo_slug": "inneraura/hyperweave"}, spec)
    repo = coerce_strip_input({"repo": "inneraura/hyperweave"}, spec)

    assert repo_slug.identity_subtitle == "inneraura/hyperweave"
    assert repo.identity_subtitle == "inneraura/hyperweave"
    assert repo.metrics[0].label == "STARS"


def test_normalized_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ChartInput(hero=MetricSlot(label="STARS", value="1"), identity="repo", unexpected=True)
