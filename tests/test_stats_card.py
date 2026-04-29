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


async def _force_rest_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``fetch_graphql`` fail so the REST fallback path runs.

    The GraphQL primary path was added to eliminate the search-API silent-
    zero bug; tests that exercise the REST aggregator pin GraphQL to
    failure so the fallback is exercised deterministically.
    """
    from hyperweave.connectors import github as github_module
    from hyperweave.connectors.base import ConnectorError

    async def failing_graphql(*_args: object, **_kwargs: object) -> object:
        raise ConnectorError("graphql disabled in test")

    monkeypatch.setattr(github_module, "fetch_graphql", failing_graphql)


@pytest.mark.asyncio
async def test_fetch_user_stats_aggregates_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    """All sub-fetches run in parallel and combine into one dict (REST path)."""
    from hyperweave.connectors import cache as cache_module
    from hyperweave.connectors import github as github_module

    cache_module.get_cache().clear()
    await _force_rest_path(monkeypatch)

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
    # Fully successful aggregate → no stale fields.
    assert result["_stale_fields"] == []


@pytest.mark.asyncio
async def test_fetch_user_stats_partial_failure_marks_fields_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    """Search-API failures surface as ``None`` + ``_stale_fields``, not silent zeros.

    This is the regression guard for v0.2.10's silent-zero bug: a 403 from
    the search API was caught by a blanket ``except Exception`` and coerced
    to ``0`` via ``_total_count(None)``. The fix makes failed sub-fetches
    return the ``_FETCH_FAILED`` sentinel, which propagates through to
    ``commits_total = None`` plus ``"commits_total" in _stale_fields``.
    """
    from hyperweave.connectors import cache as cache_module
    from hyperweave.connectors import github as github_module
    from hyperweave.connectors.base import ConnectorError

    cache_module.get_cache().clear()
    await _force_rest_path(monkeypatch)

    async def partial_fetch_json(url: str, provider: str = "", headers: dict[str, str] | None = None) -> object:
        if url.endswith("/users/eli64s"):
            return {"public_repos": 10, "followers": 5}
        # Real ``fetch_json`` raises ``ConnectorError`` on HTTP 403/429/5xx.
        # Programming errors (RuntimeError) would propagate uncaught — the
        # closure narrowly catches typed connector failures only.
        raise ConnectorError("search api 403 (rate limit)")

    async def empty_fetch_text(url: str, provider: str = "", headers: dict[str, str] | None = None) -> str:
        return ""

    monkeypatch.setattr(github_module, "fetch_json", partial_fetch_json)
    monkeypatch.setattr(github_module, "fetch_text", empty_fetch_text)

    result = await github_module.fetch_user_stats("eli64s")

    # User fetch succeeded → identity fields live.
    assert result["repo_count"] == 10
    assert result["followers"] == 5

    # Failed sub-fetches surface as None, not 0.
    assert result["commits_total"] is None
    assert result["prs_total"] is None
    assert result["issues_total"] is None
    assert result["stars_total"] is None

    # Each failure recorded in _stale_fields for resolver consumption.
    stale = set(result["_stale_fields"])
    assert "commits_total" in stale
    assert "prs_total" in stale
    assert "issues_total" in stale
    assert "stars_total" in stale


@pytest.mark.asyncio
async def test_fetch_user_stats_caches_short_ttl_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failed aggregate caches for 30s, not 1 hour — transient outages self-heal fast."""
    from hyperweave.connectors import cache as cache_module
    from hyperweave.connectors import github as github_module
    from hyperweave.connectors.base import ConnectorError

    cache = cache_module.get_cache()
    cache.clear()
    await _force_rest_path(monkeypatch)

    async def all_fail(*_args: object, **_kwargs: object) -> object:
        raise ConnectorError("everything is on fire")

    monkeypatch.setattr(github_module, "fetch_json", all_fail)
    monkeypatch.setattr(github_module, "fetch_text", all_fail)

    captured: dict[str, int] = {}
    real_set = cache.set

    def spy_set(key: str, value: object, ttl: int) -> None:
        if key.endswith(":profile-stats"):
            captured["ttl"] = ttl
        real_set(key, value, ttl)

    monkeypatch.setattr(cache, "set", spy_set)

    result = await github_module.fetch_user_stats("eli64s")
    assert result["_stale_fields"]  # at least one field went stale
    assert captured.get("ttl") == github_module.FAILURE_CACHE_TTL


@pytest.mark.asyncio
async def test_fetch_user_stats_caches_long_ttl_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fully successful aggregate caches for the full 1-hour USER_STATS_TTL."""
    from hyperweave.connectors import cache as cache_module
    from hyperweave.connectors import github as github_module

    cache = cache_module.get_cache()
    cache.clear()
    await _force_rest_path(monkeypatch)

    async def fake_fetch_json(url: str, provider: str = "", headers: dict[str, str] | None = None) -> object:
        if url.endswith("/users/eli64s"):
            return {"public_repos": 1, "followers": 1}
        if "/repos?" in url:
            return [{"stargazers_count": 1, "language": "Python"}]
        if "search/" in url:
            return {"total_count": 1}
        return None

    async def fake_fetch_text(url: str, provider: str = "", headers: dict[str, str] | None = None) -> str:
        return (
            "<tool-tip>1 contribution on Monday</tool-tip>"
            '<td class="ContributionCalendar-day" data-date="2025-04-07" data-level="1">&nbsp;</td>'
        )

    monkeypatch.setattr(github_module, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(github_module, "fetch_text", fake_fetch_text)

    captured: dict[str, int] = {}
    real_set = cache.set

    def spy_set(key: str, value: object, ttl: int) -> None:
        if key.endswith(":profile-stats"):
            captured["ttl"] = ttl
        real_set(key, value, ttl)

    monkeypatch.setattr(cache, "set", spy_set)

    result = await github_module.fetch_user_stats("eli64s")
    assert result["_stale_fields"] == []
    assert captured.get("ttl") == github_module.USER_STATS_TTL


@pytest.mark.asyncio
async def test_fetch_user_stats_graphql_primary_path_skips_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    """When GraphQL succeeds, the REST sub-fetches don't run at all."""
    from hyperweave.connectors import cache as cache_module
    from hyperweave.connectors import github as github_module

    cache_module.get_cache().clear()

    rest_calls: list[str] = []

    async def graphql_success(query: str, variables: dict[str, object] | None = None, **_: object) -> dict[str, object]:
        return {
            "data": {
                "user": {
                    "avatarUrl": "https://example/avatar",
                    "bio": "builder",
                    "followers": {"totalCount": 420},
                    "repositories": {
                        "totalCount": 63,
                        "nodes": [
                            {"stargazerCount": 12847, "primaryLanguage": {"name": "Python"}},
                        ],
                    },
                    "contributionsCollection": {
                        "totalCommitContributions": 1203,
                        "totalPullRequestContributions": 89,
                        "totalIssueContributions": 47,
                        "contributionCalendar": {
                            "totalContributions": 234,
                            "weeks": [
                                {"contributionDays": [{"contributionCount": 5, "date": "2025-04-07"}]},
                            ],
                        },
                    },
                }
            }
        }

    async def rest_should_not_run(url: str, **_: object) -> object:
        rest_calls.append(url)
        return None

    monkeypatch.setattr(github_module, "fetch_graphql", graphql_success)
    monkeypatch.setattr(github_module, "fetch_json", rest_should_not_run)
    monkeypatch.setattr(github_module, "fetch_text", rest_should_not_run)

    result = await github_module.fetch_user_stats("eli64s")
    assert result["commits_total"] == 1203
    assert result["prs_total"] == 89
    assert result["issues_total"] == 47
    assert result["stars_total"] == 12847
    assert result["_stale_fields"] == []
    # Crucially: no REST calls were made — GraphQL replaced 5 round-trips with 1.
    assert rest_calls == []


@pytest.mark.asyncio
async def test_fetch_user_stats_graphql_falls_back_to_rest_when_user_null(monkeypatch: pytest.MonkeyPatch) -> None:
    """``data.user`` null → silent transition to REST aggregator, no exception."""
    from hyperweave.connectors import cache as cache_module
    from hyperweave.connectors import github as github_module

    cache_module.get_cache().clear()

    rest_calls: list[str] = []

    async def graphql_null_user(*_: object, **__: object) -> dict[str, object]:
        return {"data": {"user": None}, "errors": [{"message": "scope missing"}]}

    async def fake_fetch_json(url: str, provider: str = "", headers: dict[str, str] | None = None) -> object:
        rest_calls.append(url)
        if url.endswith("/users/eli64s"):
            return {"public_repos": 7, "followers": 3}
        if "search/" in url:
            return {"total_count": 42}
        if "/repos?" in url:
            return []
        return None

    async def fake_fetch_text(url: str, **_: object) -> str:
        return ""

    monkeypatch.setattr(github_module, "fetch_graphql", graphql_null_user)
    monkeypatch.setattr(github_module, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(github_module, "fetch_text", fake_fetch_text)

    result = await github_module.fetch_user_stats("eli64s")
    # REST fallback DID run (this is the whole point of the test).
    assert any("/users/eli64s" in u for u in rest_calls)
    # And the REST-derived values landed in the result.
    assert result["repo_count"] == 7
    assert result["commits_total"] == 42


@pytest.mark.asyncio
async def test_fetch_user_stats_rejects_bad_username() -> None:
    from hyperweave.connectors.github import fetch_user_stats

    with pytest.raises(ValueError):
        await fetch_user_stats("../etc/passwd")


@pytest.mark.asyncio
async def test_fetch_user_stats_propagates_programming_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``ValueError`` (programming error) must propagate, not be swallowed.

    The sentinel pattern only catches ``ConnectorError`` and ``CircuitOpenError``
    — narrow, recoverable upstream failures. Bugs (KeyError, ValueError, type
    errors) should crash loudly so they get fixed instead of silently masking
    behind ``_FETCH_FAILED``.
    """
    from hyperweave.connectors import cache as cache_module
    from hyperweave.connectors import github as github_module

    cache_module.get_cache().clear()
    await _force_rest_path(monkeypatch)

    async def buggy_fetch(*_: object, **__: object) -> object:
        raise ValueError("downstream parser bug")

    async def fake_fetch_text(*_: object, **__: object) -> str:
        return ""

    monkeypatch.setattr(github_module, "fetch_json", buggy_fetch)
    monkeypatch.setattr(github_module, "fetch_text", fake_fetch_text)

    with pytest.raises(ValueError, match="downstream parser bug"):
        await github_module.fetch_user_stats("eli64s")


def test_circuit_breaker_search_does_not_affect_core() -> None:
    """A tripped search breaker leaves the core breaker untouched.

    Splits the formerly shared ``provider="github"`` breaker into three
    domains so a 403-storm on the search API doesn't cascade into badge
    or chart endpoints.
    """
    from hyperweave.connectors.base import CircuitState, get_breaker, reset_breakers

    reset_breakers()
    search_breaker = get_breaker("github-search")
    core_breaker = get_breaker("github-core")
    graphql_breaker = get_breaker("github-graphql")

    # Trip the search breaker with the configured failure threshold.
    for _ in range(search_breaker.failure_threshold):
        search_breaker.record_failure()

    assert search_breaker.state is CircuitState.OPEN
    assert not search_breaker.allow_request()

    # Core and GraphQL breakers are unaffected — distinct provider names
    # produce distinct breaker instances in the registry.
    assert core_breaker.state is CircuitState.CLOSED
    assert core_breaker.allow_request()
    assert graphql_breaker.state is CircuitState.CLOSED
    assert graphql_breaker.allow_request()

    reset_breakers()


def test_resolve_stats_renders_dash_for_stale_field() -> None:
    """Stale fields render as ``—`` (em dash) and the artifact is marked stale.

    Distinguishes failure (``—``, ``data-hw-status="stale"``) from real zero
    (``0`` glyph, no stale marker). The whole point of the silent-zero fix.
    """
    spec = ComposeSpec(
        type="stats",
        genome_id="brutalist-emerald",
        stats_username="eli64s",
        connector_data={
            "username": "eli64s",
            "stars_total": 12847,
            "commits_total": None,
            "prs_total": None,
            "issues_total": None,
            "contrib_total": 234,
            "streak_days": 47,
            "_stale_fields": ["commits_total", "issues_total", "prs_total"],
        },
    )
    result = compose(spec)
    svg = result.svg
    # Stale marker present.
    assert 'data-hw-status="stale"' in svg
    # Live values render normally.
    assert "12.8K" in svg
    assert "47d" in svg
    # Stale fields render as em dash, not as "0".
    assert "—" in svg


def test_resolve_stats_real_zero_renders_zero_not_dash() -> None:
    """A genuine zero (no _stale_fields) renders as ``0``, not ``—``.

    The contract guard: failure-zero must look different from real-zero.
    A new account with no commits should display ``0``, distinguishing it
    from a rate-limited fetch that couldn't determine the value.
    """
    spec = ComposeSpec(
        type="stats",
        genome_id="brutalist-emerald",
        stats_username="newbie",
        connector_data={
            "username": "newbie",
            "stars_total": 0,
            "commits_total": 0,
            "prs_total": 0,
            "issues_total": 0,
            "contrib_total": 0,
            "streak_days": 0,
            "_stale_fields": [],
        },
    )
    result = compose(spec)
    svg = result.svg
    # No stale marker — this is real-zero, not failure-zero.
    assert 'data-hw-status="stale"' not in svg
    # Real zero renders as a digit, not as the em-dash placeholder.
    assert ">0<" in svg or ">0 <" in svg or "0d" in svg
