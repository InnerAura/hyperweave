"""Integration tests for the chart frame (Session 2A+2B Phase 4).

Covers end-to-end compose() with mock connector data for both paradigms,
graceful degradation with missing data, and the fetch_stargazer_history
sampling helper with fetch_json mocked.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

MOCK_POINTS = [
    {"date": "2025-01-01T00:00:00Z", "count": 100},
    {"date": "2025-04-01T00:00:00Z", "count": 320},
    {"date": "2025-07-01T00:00:00Z", "count": 680},
    {"date": "2025-10-01T00:00:00Z", "count": 1200},
    {"date": "2026-01-01T00:00:00Z", "count": 2100},
    {"date": "2026-04-01T00:00:00Z", "count": 2850},
]


def _make_chart_spec(genome: str) -> ComposeSpec:
    return ComposeSpec(
        type="chart",
        genome_id=genome,
        chart_owner="eli64s",
        chart_repo="readme-ai",
        connector_data={
            "points": MOCK_POINTS,
            "current_stars": 2850,
            "repo": "eli64s/readme-ai",
        },
    )


# ── End-to-end compose for chart frame ─────────────────────────────────


def test_chart_compose_brutalist_emerald_full() -> None:
    result = compose(_make_chart_spec("brutalist-emerald"))
    svg = result.svg
    assert result.width == 900
    assert result.height == 500
    assert 'data-hw-frame="chart"' in svg
    # brutalist-emerald declares paradigms.chart = "brutalist"
    assert "<polyline" in svg
    assert 'stroke-linejoin="miter"' in svg
    assert "<rect" in svg  # square markers


def test_chart_compose_chrome_horizon_full() -> None:
    result = compose(_make_chart_spec("chrome-horizon"))
    svg = result.svg
    assert 'data-hw-frame="chart"' in svg
    # chrome-horizon declares paradigms.chart = "chrome"
    # → bezier <path> instead of polyline
    assert "<path" in svg
    # Diamond markers via rotate(45)
    assert "rotate(45" in svg


def test_chart_graceful_degradation_without_data() -> None:
    """Missing connector_data → placeholder series + data-hw-status=stale."""
    spec = ComposeSpec(
        type="chart",
        genome_id="brutalist-emerald",
        chart_owner="eli64s",
        chart_repo="readme-ai",
        connector_data=None,
    )
    result = compose(spec)
    assert 'data-hw-status="stale"' in result.svg
    # Placeholder still produces a chart (not an empty SVG).
    assert "<polyline" in result.svg


def test_chart_structural_differentiation_proves_not_color_swap() -> None:
    """brutalist-emerald and chrome-horizon produce materially different SVGs.

    Enforces Principle 26: paradigm dispatch must produce structural differences,
    not just color swaps. We compare element counts — the two paradigms use
    different primitives (polyline vs path, rect vs rotated-rect markers).
    """
    br = compose(_make_chart_spec("brutalist-emerald")).svg
    ch = compose(_make_chart_spec("chrome-horizon")).svg

    # brutalist uses <polyline>, chrome uses <path> for the line.
    assert br.count("<polyline") > ch.count("<polyline")
    assert ch.count("<path") > br.count("<path")
    # chrome's diamonds include rotate(45); brutalist's squares do not.
    assert "rotate(45" in ch
    assert "rotate(45" not in br


# ── fetch_stargazer_history sampling ───────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_stargazer_history_samples_pages() -> None:
    """The sampler should:
    1. Query /repos/{owner}/{repo} for total stars.
    2. Concurrently fetch N evenly-spaced pages with the star Accept header.
    3. Return cumulative (date, count) points sorted chronologically.
    """
    from hyperweave.connectors.cache import get_cache
    from hyperweave.connectors.github import fetch_stargazer_history

    # Clear cache so we actually hit the mock.
    get_cache().clear()

    # Mock JSON responses: repo metadata + stargazer page data.
    async def fake_fetch_json(url, provider="generic", headers=None):  # type: ignore[no-untyped-def]
        if url.endswith("/repos/eli64s/readme-ai"):
            return {"stargazers_count": 120}
        # stargazers page URL ends with ?page=N
        if "page=" in url:
            page = int(url.split("page=")[-1])
            # Return a single starred_at record per page, date = 2025-01-{page:02d}
            return [{"starred_at": f"2025-01-{page:02d}T00:00:00Z"}]
        return {}

    with patch("hyperweave.connectors.github.fetch_json", side_effect=fake_fetch_json):
        result = await fetch_stargazer_history("eli64s", "readme-ai", sample_pages=4)

    assert result["current_stars"] == 120
    assert result["repo"] == "eli64s/readme-ai"
    # We asked for 4 samples; with 120 stars @ 30/page = 4 pages total,
    # the sampler picks all 4, and we also append a synthetic "now" point,
    # so we expect at least 4 points (may include the trailing duplicate date).
    assert len(result["points"]) >= 4
    # All points are sorted chronologically.
    dates = [p["date"] for p in result["points"]]
    assert dates == sorted(dates)


@pytest.mark.asyncio
async def test_fetch_stargazer_history_handles_zero_stars() -> None:
    """Repo with zero stars → empty points list, no API calls beyond the metadata fetch."""
    from hyperweave.connectors.cache import get_cache
    from hyperweave.connectors.github import fetch_stargazer_history

    get_cache().clear()

    async def fake_fetch_json(url, provider="generic", headers=None):  # type: ignore[no-untyped-def]
        return {"stargazers_count": 0}

    with patch("hyperweave.connectors.github.fetch_json", side_effect=fake_fetch_json):
        result = await fetch_stargazer_history("someone", "empty-repo")

    assert result["points"] == []
    assert result["current_stars"] == 0


@pytest.mark.asyncio
async def test_fetch_stargazer_history_requires_valid_identifier() -> None:
    from hyperweave.connectors.github import fetch_stargazer_history

    with pytest.raises(ValueError):
        await fetch_stargazer_history("", "repo")
    with pytest.raises(ValueError):
        await fetch_stargazer_history("owner", "")
