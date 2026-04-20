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
    """Missing connector_data → truthful empty state, NOT a fabricated polyline.

    After the bug-fix pass, the resolver no longer substitutes a placeholder
    1200-star series for failed upstream fetches. Instead it renders a
    "DATA UNAVAILABLE" overlay and still emits data-hw-status="stale".
    """
    spec = ComposeSpec(
        type="chart",
        genome_id="brutalist-emerald",
        chart_owner="eli64s",
        chart_repo="readme-ai",
        connector_data=None,
    )
    result = compose(spec)
    assert 'data-hw-status="stale"' in result.svg
    # No fabricated polyline and no leak of the old placeholder numbers.
    assert "<polyline" not in result.svg
    assert "1200" not in result.svg and "1,200" not in result.svg
    # Overlay communicates the truthful unavailable state.
    assert "DATA UNAVAILABLE" in result.svg


def test_chart_zero_stars_renders_empty_state() -> None:
    """A repo with 0 real stars must render an empty state — no 1200 leak, no fake polyline."""
    spec = ComposeSpec(
        type="chart",
        genome_id="brutalist-emerald",
        chart_owner="jiahongc",
        chart_repo="march-madness-prediction-market",
        connector_data={
            "points": [],
            "current_stars": 0,
            "repo": "jiahongc/march-madness-prediction-market",
        },
    )
    svg = compose(spec).svg
    assert 'data-hw-status="empty"' in svg
    assert "NEW REPO" in svg
    # No placeholder leakage.
    assert "1200" not in svg and "1,200" not in svg
    # No fabricated polyline.
    assert "<polyline" not in svg
    # Hero shows 0 stars truthfully (not a comma-formatted 1,200).
    assert ">0</text>" in svg


def test_chart_six_stars_renders_real_polyline_with_derived_labels() -> None:
    """A repo with 6 real stars must render a real polyline + derived axis labels.

    Covers bug 2 (low-star empty plot) at the compose level: the stargazer
    timestamps yield distinct x-coordinates, and the derived Y ticks show
    [0, 2, 4, 6] — never the hardcoded "3K".
    """
    points = [{"date": f"2025-{m:02d}-01T00:00:00Z", "count": i + 1} for i, m in enumerate((1, 3, 5, 7, 9, 11))]
    spec = ComposeSpec(
        type="chart",
        genome_id="brutalist-emerald",
        chart_owner="jiahongc",
        chart_repo="cc-companion",
        connector_data={
            "points": points,
            "current_stars": 6,
            "repo": "jiahongc/cc-companion",
        },
    )
    svg = compose(spec).svg
    # Real polyline rendered.
    assert "<polyline" in svg
    # Derived Y-axis: 0/2/4/6 ticks — NOT 3K.
    assert ">3K<" not in svg
    assert ">0</text>" in svg
    assert ">2</text>" in svg
    assert ">4</text>" in svg
    assert ">6</text>" in svg
    # Derived X-axis: year numbers only, no EARLY/MID/LATE bucket words.
    assert "2025" in svg
    assert "EARLY" not in svg
    assert "MID" not in svg
    assert "LATE" not in svg


@pytest.mark.asyncio
async def test_fetch_stargazer_history_single_page_uses_per_stargazer_timestamps() -> None:
    """Low-star repos (total_pages == 1) emit one point per stargazer entry.

    Bug 2 fix: the previous logic took only the first starred_at per page and
    appended a duplicate "now" point, collapsing the polyline's time range to
    zero. This test verifies that each stargazer's real timestamp is used and
    every point has a distinct date.
    """
    from hyperweave.connectors.cache import get_cache
    from hyperweave.connectors.github import fetch_stargazer_history

    get_cache().clear()

    async def fake_fetch_json(url, provider="generic", headers=None):  # type: ignore[no-untyped-def]
        if url.endswith("/repos/jiahongc/cc-companion"):
            return {"stargazers_count": 6}
        if "page=1" in url:
            return [{"starred_at": f"2025-0{m}-01T00:00:00Z"} for m in range(1, 7)]
        return {}

    with patch("hyperweave.connectors.github.fetch_json", side_effect=fake_fetch_json):
        result = await fetch_stargazer_history("jiahongc", "cc-companion")

    assert result["current_stars"] == 6
    assert len(result["points"]) == 6
    # All points have distinct timestamps (bug 2 fix).
    dates = [p["date"] for p in result["points"]]
    assert len(set(dates)) == 6
    # Cumulative counts are 1..6.
    assert [p["count"] for p in result["points"]] == [1, 2, 3, 4, 5, 6]


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
    # Use 400 stars so 400/100=4 pages are available for a 4-sample request.
    async def fake_fetch_json(url, provider="generic", headers=None):  # type: ignore[no-untyped-def]
        if url.endswith("/repos/eli64s/readme-ai"):
            return {"stargazers_count": 400}
        # stargazers page URL ends with ?page=N
        if "page=" in url:
            page = int(url.split("page=")[-1])
            # Return a single starred_at record per page, date = 2025-01-{page:02d}
            return [{"starred_at": f"2025-01-{page:02d}T00:00:00Z"}]
        return {}

    with patch("hyperweave.connectors.github.fetch_json", side_effect=fake_fetch_json):
        result = await fetch_stargazer_history("eli64s", "readme-ai", sample_pages=4)

    assert result["current_stars"] == 400
    assert result["repo"] == "eli64s/readme-ai"
    # 400 stars @ 100/page = 4 pages total. sample_pages=4 picks all 4;
    # plus a synthetic "now" point at the current timestamp → ≥ 4 points.
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
