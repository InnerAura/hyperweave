"""Provider snapshot adapter tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from hyperweave.compose.schema import coerce_chart_input, coerce_stats_input
from hyperweave.connectors.cache import get_cache
from hyperweave.connectors.snapshots import (
    fetch_arxiv_snapshot,
    fetch_hf_snapshot,
    fetch_pypi_snapshot,
    merge_stats_sources,
)
from hyperweave.core.models import ComposeSpec


@pytest.fixture(autouse=True)
def _clear_connector_cache() -> None:
    get_cache().clear()


@pytest.mark.asyncio
async def test_fetch_hf_snapshot_returns_stats_input_compatible_data() -> None:
    payload = {
        "id": "zai-org/GLM-5.1",
        "author": "zai-org",
        "downloads": 175311,
        "likes": 1686,
        "pipeline_tag": "text-generation",
        "library_name": "transformers",
        "siblings": [{"rfilename": "config.json"}, {"rfilename": "model.safetensors"}],
        "spaces": [{"id": "zai-org/demo"}],
    }

    with patch("hyperweave.connectors.snapshots.fetch_json", new_callable=AsyncMock, return_value=payload):
        snapshot = await fetch_hf_snapshot("zai-org/GLM-5.1")

    coerced = coerce_stats_input(snapshot, ComposeSpec(type="stats"))
    assert coerced.provider == "huggingface"
    assert coerced.hero.label == "DOWNLOADS/MO"
    assert coerced.metrics[0].label == "LIKES"
    assert coerced.metrics[1].label == "FILES"


@pytest.mark.asyncio
async def test_fetch_pypi_snapshot_returns_sparkline_and_chart_series() -> None:
    async def fake_fetch_json(url: str, *, provider: str = "generic", **_kwargs: Any) -> dict[str, Any]:
        if "pypi.org" in url:
            return {"info": {"version": "0.21.0", "requires_python": "<3.15,>=3.10"}}
        if "recent" in url:
            return {"data": {"last_month": 6131880, "last_day": 149654}}
        return {
            "data": [
                {"category": "without_mirrors", "date": f"2026-05-{day:02d}", "downloads": 100000 + day}
                for day in range(1, 32)
            ]
        }

    with patch("hyperweave.connectors.snapshots.fetch_json", side_effect=fake_fetch_json):
        snapshot = await fetch_pypi_snapshot("vllm")

    stats = coerce_stats_input(snapshot, ComposeSpec(type="stats"))
    chart = coerce_chart_input(snapshot, ComposeSpec(type="chart"))
    assert stats.hero.label == "DOWNLOADS/MO"
    assert stats.metrics[1].value == "3.10-3.14"
    assert stats.activity is not None
    assert stats.activity.type == "sparkline_30d"
    assert stats.activity.peak_label == "100.0K"
    assert len(chart.series_points) == 31
    assert chart.status == "fresh"


@pytest.mark.asyncio
async def test_fetch_arxiv_snapshot_returns_paper_metadata_without_citations() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>GLM-5: from Vibe Coding to Agentic Engineering</title>
    <summary>summary</summary>
    <published>2026-02-17T17:50:56Z</published>
    <category term="cs.LG"/>
    <category term="cs.CL"/>
    <author><name>Aohan Zeng</name></author>
    <author><name>Xin Lv</name></author>
  </entry>
</feed>"""

    with patch("hyperweave.connectors.snapshots.fetch_text", new_callable=AsyncMock, return_value=xml):
        snapshot = await fetch_arxiv_snapshot("2602.15763")

    coerced = coerce_stats_input(snapshot, ComposeSpec(type="stats"))
    assert coerced.provider == "arxiv"
    assert coerced.hero.label == "PAPER"
    assert "citation" not in str(snapshot).lower()
    assert coerced.metrics[0].label == "AUTHORS"


def test_merge_stats_sources_preserves_first_hero_and_concatenates_metrics() -> None:
    merged = merge_stats_sources(
        {
            "provider": "github",
            "identity": "GLM-5",
            "hero": {"label": "STARS", "value": "123", "raw_value": 123},
            "metrics": [{"label": "FORKS", "value": "4", "raw_value": 4}],
        },
        {
            "provider": "huggingface",
            "identity": "zai-org/GLM-5.1",
            "hero": {"label": "DOWNLOADS", "value": "175.3K", "raw_value": 175311},
            "metrics": [{"label": "LIKES", "value": "1.7K", "raw_value": 1686}],
        },
    )

    coerced = coerce_stats_input(merged, ComposeSpec(type="stats"))
    assert coerced.hero.label == "STARS"
    assert [metric.label for metric in coerced.metrics] == ["FORKS", "HF DL", "LIKES"]
    assert coerced.provider == "github+huggingface"
