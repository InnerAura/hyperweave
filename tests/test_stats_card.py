"""Integration tests for the stats card frame (Session 2A+2B Phase 5).

Covers:
- Compose with mock connector_data in both paradigms (brutalist + chrome)
- Structural differentiation (Principle 26)
- Graceful degradation with connector_data=None
- fetch_user_stats parallel aggregation with all sub-fetches mocked
- CLI and HTTP route integration is covered separately in test_serve.py / test_cli.py
"""

from __future__ import annotations

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

MOCK_STATS = {
    "username": "eli64s",
    "bio": "Building HyperWeave",
    "stars_total": 12847,
    "commits_total": 1203,
    "prs_total": 89,
    "issues_total": 47,
    "contrib_total": 234,
    "streak_days": 47,
    "top_language": "Python",
    "repo_count": 63,
    "language_breakdown": [
        {"name": "Python", "pct": 68.5, "count": 43},
        {"name": "TypeScript", "pct": 18.1, "count": 11},
        {"name": "Rust", "pct": 9.5, "count": 6},
        {"name": "Go", "pct": 3.9, "count": 2},
    ],
    "heatmap_grid": [],
}


def _spec(genome: str) -> ComposeSpec:
    return ComposeSpec(
        type="stats",
        genome_id=genome,
        stats_username="eli64s",
        connector_data=MOCK_STATS,
    )


# ── End-to-end compose ─────────────────────────────────────────────────


def test_stats_compose_brutalist_emerald_renders() -> None:
    result = compose(_spec("brutalist-emerald"))
    assert result.width == 495
    assert result.height == 280
    assert 'data-hw-frame="stats"' in result.svg
    # Hero number formatted compactly (12847 → "12.8K")
    assert "12.8K" in result.svg
    # Horizontal metric row labels present
    assert "COMMITS" in result.svg
    assert "PRS" in result.svg
    assert "ISSUES" in result.svg
    assert "STREAK" in result.svg


def test_stats_compose_chrome_horizon_renders_material_stack() -> None:
    result = compose(_spec("chrome-horizon"))
    svg = result.svg
    assert result.width == 495
    assert result.height == 260
    # Chrome paradigm uses material stack with envelope gradient and bevel filter.
    assert "linearGradient" in svg
    # Metrics displayed with text-anchor="middle" (centered columns).
    assert 'text-anchor="middle"' in svg


def test_stats_paradigms_are_structurally_different() -> None:
    """Principle 26: brutalist-emerald and chrome-horizon stats must render
    with materially different primitive counts, not just different colors."""
    br = compose(_spec("brutalist-emerald")).svg
    ch = compose(_spec("chrome-horizon")).svg
    # Brutalist uses heavy stroke-width rules; chrome uses gradient envelopes.
    assert 'stroke-width="2.5"' in br
    assert 'stroke-width="2.5"' not in ch
    # Chrome uses material stack with bevel filter; brutalist uses grain.
    assert "linearGradient" in ch
    assert "feTurbulence" in br


def test_stats_graceful_degradation_without_data() -> None:
    spec = ComposeSpec(type="stats", genome_id="brutalist-emerald", stats_username="eli64s", connector_data=None)
    result = compose(spec)
    assert 'data-hw-status="stale"' in result.svg
    # Still renders — no exception, no empty SVG.
    assert len(result.svg) > 1000


def test_stats_contains_real_data_values() -> None:
    """Real values from connector data must appear in the rendered SVG.

    Proves the PRD requirement: ship with real values, NOT em-dash placeholders.
    """
    result = compose(_spec("brutalist-emerald"))
    # Template shows COMMITS, PRS, ISSUES, STREAK from mock connector data.
    assert "1,203" in result.svg  # commits_display
    assert "47d" in result.svg  # streak_display


def test_stats_compose_with_minimal_connector_data() -> None:
    """Partial connector data (only username + stars) still renders OK."""
    spec = ComposeSpec(
        type="stats",
        genome_id="brutalist-emerald",
        stats_username="anon",
        connector_data={"username": "anon", "stars_total": 12},
    )
    result = compose(spec)
    assert 'data-hw-frame="stats"' in result.svg


def test_stats_chrome_zero_stars_does_not_synthesize_placeholder() -> None:
    """Zero-star user → embedded chart must not fabricate the old 1200-star series.

    Regression guard: the previous `int(stars_total or 1200)` pattern silently
    defaulted to a 1200-star synthetic curve whenever stars_total was falsy.
    After the fix, zero stars yields an empty embedded chart — truthfully.
    """
    spec = ComposeSpec(
        type="stats",
        genome_id="chrome-horizon",
        stats_username="newbie",
        connector_data={
            "username": "newbie",
            "stars_total": 0,
            "commits_total": 5,
            "prs_total": 0,
            "issues_total": 0,
        },
    )
    svg = compose(spec).svg
    # No placeholder leakage in the embedded chart.
    assert "1200" not in svg
    assert "1,200" not in svg
    # Compose still completes successfully with data-hw-frame marker.
    assert 'data-hw-frame="stats"' in svg


# ── fetch_user_stats parallel aggregation ─────────────────────────────


@pytest.mark.asyncio
async def test_fetch_user_stats_aggregates_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    """All sub-fetches run in parallel and combine into one dict."""
    from hyperweave.connectors import cache as cache_module
    from hyperweave.connectors import github as github_module

    cache_module.get_cache().clear()

    async def fake_fetch_json(url: str, provider: str = "", headers: dict[str, str] | None = None) -> object:
        if url.endswith("/users/eli64s"):
            return {"avatar_url": "https://example/avatar", "bio": "builder", "public_repos": 63, "followers": 420}
        if "/users/eli64s/repos" in url:
            return [
                {"stargazers_count": 5000, "language": "Python"},
                {"stargazers_count": 3200, "language": "Python"},
                {"stargazers_count": 2100, "language": "TypeScript"},
                {"stargazers_count": 1500, "language": "Rust"},
                {"stargazers_count": 1047, "language": "Python"},
            ]
        if "search/commits" in url:
            return {"total_count": 1203}
        if "search/issues" in url and "type:pr" in url:
            return {"total_count": 89}
        if "search/issues" in url and "type:issue" in url:
            return {"total_count": 47}
        return None

    contrib_html = (
        "<tool-tip>5 contributions on Monday, April 7, 2025</tool-tip>"
        '<td class="ContributionCalendar-day" data-date="2025-04-07" data-level="2">&nbsp;</td>'
    )

    async def fake_fetch_text(url: str, provider: str = "", headers: dict[str, str] | None = None) -> str:
        return contrib_html

    monkeypatch.setattr(github_module, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(github_module, "fetch_text", fake_fetch_text)

    result = await github_module.fetch_user_stats("eli64s")

    assert result["username"] == "eli64s"
    assert result["stars_total"] == 5000 + 3200 + 2100 + 1500 + 1047  # 12847
    assert result["commits_total"] == 1203
    assert result["prs_total"] == 89
    assert result["issues_total"] == 47
    assert result["repo_count"] == 63
    assert result["followers"] == 420
    assert result["top_language"] == "Python"
    # Contribution scraper ran → at least one cell parsed.
    assert result["contrib_total"] == 5
    assert result["streak_days"] == 1


@pytest.mark.asyncio
async def test_fetch_user_stats_partial_failure_keeps_other_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Individual sub-fetch exceptions don't blow up the whole result."""
    from hyperweave.connectors import cache as cache_module
    from hyperweave.connectors import github as github_module

    cache_module.get_cache().clear()

    async def partial_fetch_json(url: str, provider: str = "", headers: dict[str, str] | None = None) -> object:
        if url.endswith("/users/eli64s"):
            return {"public_repos": 10, "followers": 5}
        raise RuntimeError("search api 503")

    async def empty_fetch_text(url: str, provider: str = "", headers: dict[str, str] | None = None) -> str:
        return ""

    monkeypatch.setattr(github_module, "fetch_json", partial_fetch_json)
    monkeypatch.setattr(github_module, "fetch_text", empty_fetch_text)

    result = await github_module.fetch_user_stats("eli64s")
    assert result["repo_count"] == 10
    assert result["followers"] == 5
    # Failed sub-fetches produced zeros, not exceptions.
    assert result["commits_total"] == 0
    assert result["prs_total"] == 0
    assert result["issues_total"] == 0
    assert result["stars_total"] == 0


@pytest.mark.asyncio
async def test_fetch_user_stats_rejects_bad_username() -> None:
    from hyperweave.connectors.github import fetch_user_stats

    with pytest.raises(ValueError):
        await fetch_user_stats("../etc/passwd")
