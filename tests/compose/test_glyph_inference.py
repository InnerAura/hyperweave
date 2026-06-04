"""Provider-aware glyph inference tests."""

from __future__ import annotations

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec


def test_stats_glyph_uses_dominant_provider_with_hero_tie_break() -> None:
    svg = compose(
        ComposeSpec(
            type="stats",
            genome_id="chrome",
            connector_data={
                "provider": "huggingface+arxiv",
                "identity": "zai-org/GLM-5.1",
                "hero": {"label": "DOWNLOADS/MO", "value": "165.9K", "provider": "huggingface"},
                "metrics": [
                    {"label": "LIKES", "value": "1,688", "provider": "huggingface"},
                    {"label": "FILES", "value": "300", "provider": "huggingface"},
                    {"label": "SPACES", "value": "66", "provider": "huggingface"},
                    {"label": "ARXIV", "value": "2602.15763", "provider": "arxiv"},
                    {"label": "AUTHORS", "value": "186", "provider": "arxiv"},
                    {"label": "CATEGORIES", "value": "cs.LG, cs.CL", "provider": "arxiv"},
                ],
                "source_url": "https://huggingface.co/zai-org/GLM-5.1",
            },
        )
    ).svg

    assert 'data-hw-glyph="huggingface"' in svg
    assert 'data-hw-glyph="github"' not in svg


def test_explicit_glyph_override_wins_over_provider_inference() -> None:
    svg = compose(
        ComposeSpec(
            type="stats",
            genome_id="chrome",
            glyph="arxiv",
            connector_data={
                "provider": "huggingface",
                "identity": "zai-org/GLM-5.1",
                "hero": {"label": "DOWNLOADS/MO", "value": "165.9K"},
                "metrics": [{"label": "LIKES", "value": "1,688"}],
            },
        )
    ).svg

    assert 'data-hw-glyph="arxiv"' in svg


def test_unknown_provider_and_identity_do_not_default_to_github() -> None:
    svg = compose(
        ComposeSpec(
            type="stats",
            genome_id="chrome",
            connector_data={
                "identity": "unknown-subject",
                "hero": {"label": "SCORE", "value": "42"},
                "metrics": [{"label": "COUNT", "value": "7"}],
            },
        )
    ).svg

    assert "data-hw-glyph=" not in svg


def test_chart_glyph_infers_provider_from_connector_data() -> None:
    svg = compose(
        ComposeSpec(
            type="chart",
            genome_id="chrome",
            connector_data={
                "provider": "pypi",
                "identity": "vllm",
                "hero": {"label": "DOWNLOADS/MO", "value": "6.1M"},
                "series_label": "DOWNLOADS",
                "series_points": [{"date": "2026-05-01", "count": 1000}],
                "source_url": "https://pypi.org/project/vllm/",
            },
        )
    ).svg

    assert 'data-hw-glyph="pypi"' in svg
