"""GitHub connector."""

from __future__ import annotations

import asyncio
import logging
import math
import re
from datetime import UTC, datetime
from typing import Any

from hyperweave.connectors.base import (
    CircuitOpenError,
    ConnectorError,
    fetch_graphql,
    fetch_json,
    fetch_text,
    pin_github_token,
)
from hyperweave.connectors.cache import get_cache

_LOGGER = logging.getLogger(__name__)

# Three breaker domains for github traffic. Splitting the formerly shared
# ``provider="github"`` keeps a search-API quota 403 from tripping the
# circuit breaker for badge/strip/chart endpoints (which use core REST).
# The bearer token is injected for all three by ``connectors/base.fetch``.
_PROVIDER_CORE = "github-core"
_PROVIDER_SEARCH = "github-search"
_PROVIDER_GRAPHQL = "github-graphql"

# Cache namespace for all github cache keys. Cache identity is keyed by
# resource URL, not by breaker domain — distinct breakers shouldn't fork
# the cache layout.
_CACHE_NS = "github"

CACHE_TTL = 300

# Longer TTL for stargazer history + user stats — append-only data that changes slowly.
STARGAZER_HISTORY_TTL = 3600
USER_STATS_TTL = 3600

# Short TTL for results that contain failure evidence (any sub-fetch
# returned ``_FETCH_FAILED``). 30s vs 3600s for success means a transient
# rate-limit burst self-heals in seconds, not in an hour.
FAILURE_CACHE_TTL = 30

# Sentinel returned by sub-fetch helpers to mark "fetch failed, do NOT
# coerce to a zero". Identity-checked (``payload is _FETCH_FAILED``) rather
# than equality so it cannot be confused with a legitimate empty value.
_FETCH_FAILED: Any = object()

# Username sanitization per GitHub's own rules (letters, digits, hyphens; 1-39 chars).
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,38}$")

# Mapping from user-facing metric names to API response keys
_METRIC_MAP: dict[str, str] = {
    "stars": "stargazers_count",
    "forks": "forks_count",
    "watchers": "subscribers_count",
    "issues": "open_issues_count",
    "license": "license",
    "language": "language",
}


async def _fetch_build_status(identifier: str) -> dict[str, Any]:
    """Fetch CI status from both the Checks API and Status API.

    GitHub Actions reports via the Checks API, while older CI systems
    (Travis, CircleCI) use the Status API. We query both and pick the
    most informative signal.
    """
    cache = get_cache()
    cache_key = f"{_CACHE_NS}:{identifier}:build"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    # Get default branch
    repo_url = f"https://api.github.com/repos/{identifier}"
    repo_data = await fetch_json(repo_url, provider=_PROVIDER_CORE)
    default_branch = repo_data.get("default_branch", "main")

    # 1. Check Runs API (GitHub Actions, modern CI)
    checks_url = f"https://api.github.com/repos/{identifier}/commits/{default_branch}/check-runs"
    checks_data = await fetch_json(checks_url, provider=_PROVIDER_CORE)
    check_runs: list[dict[str, Any]] = checks_data.get("check_runs", [])

    value = "unknown"
    if check_runs:
        # Aggregate: any failure → failing, all success → passing, else building
        conclusions = [r.get("conclusion") for r in check_runs]
        statuses = [r.get("status") for r in check_runs]
        if "failure" in conclusions or "timed_out" in conclusions:
            value = "failing"
        elif "cancelled" in conclusions:
            value = "cancelled"
        elif all(c == "success" for c in conclusions if c is not None) and all(s == "completed" for s in statuses):
            value = "passing"
        elif any(s in ("queued", "in_progress") for s in statuses):
            value = "building"
        else:
            value = "failing"
    else:
        # 2. Fallback: legacy Status API (Travis, etc.)
        status_url = f"https://api.github.com/repos/{identifier}/commits/{default_branch}/status"
        status_data = await fetch_json(status_url, provider=_PROVIDER_CORE)
        state = status_data.get("state", "unknown")
        total = status_data.get("total_count", 0)
        if total == 0:
            value = "unknown"
        else:
            display = {"success": "passing", "pending": "building", "failure": "failing", "error": "error"}
            value = display.get(state, state)

    result: dict[str, Any] = {
        "provider": _CACHE_NS,
        "identifier": identifier,
        "metric": "build",
        "value": value,
        "ttl": 120,
    }
    cache.set(cache_key, result, 120)
    return result


async def fetch_metric(identifier: str, metric: str) -> dict[str, Any]:
    """Fetch a single metric from GitHub."""
    if "/" not in identifier:
        raise ValueError(f"GitHub identifier must be 'owner/repo', got {identifier!r}")

    # Build status uses a separate API endpoint
    if metric == "build":
        return await _fetch_build_status(identifier)

    cache = get_cache()
    cache_key = f"{_CACHE_NS}:{identifier}:{metric}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    url = f"https://api.github.com/repos/{identifier}"
    data = await fetch_json(url, provider=_PROVIDER_CORE)

    api_key = _METRIC_MAP.get(metric)
    if api_key is None:
        raise ValueError(f"Unknown GitHub metric {metric!r}. Available: {sorted([*_METRIC_MAP, 'build'])}")

    raw_value = data.get(api_key)

    # License is nested
    if metric == "license" and isinstance(raw_value, dict):
        raw_value = raw_value.get("spdx_id", raw_value.get("name", "Unknown"))

    result: dict[str, Any] = {
        "provider": _CACHE_NS,
        "identifier": identifier,
        "metric": metric,
        "value": raw_value,
        "ttl": CACHE_TTL,
    }
    cache.set(cache_key, result, CACHE_TTL)
    return result


# ── Session 2A+2B: star history sampling ───────────────────────────────────


_STARGAZER_PAGE_SIZE = 100
# GitHub hard-caps deep pagination on /stargazers at ~400 pages.
# With per_page=100 that gives ~40k stargazer visibility per repo; we still
# report the real total_stars in the "now" point, we just can't sample past
# this wall. For mega-repos (100k+ stars) we therefore sample within a fixed
# window and mark the final point with the current timestamp.
#
# v0.2.10 removed an earlier GraphQL cursor-offset sampler (v0.2.8/v0.2.9)
# that was based on a false assumption: GitHub's stargazer cursor decodes to
# ``cursor:v2:<MessagePack binary>`` — not ``cursor:<N>`` as documented in
# the removed code. Constructed ``cursor:<N-1>`` anchors were rejected by
# GitHub with ``INVALID_CURSOR_ARGUMENTS``, or (worse) silently returned a
# recent stargazer for a handful of offsets, so mega-repo charts collapsed
# into flat lines. The unit tests mocked the cursor decoder to match the
# broken assumption, so they passed green. REST sampling is now the only
# path — it is bounded at 40K but produces honest, evenly-spaced samples
# (star-history.com is bounded by the same cap and uses the same strategy).
_STARGAZER_PAGE_CAP = 400
_STARGAZER_ACCEPT_HEADER = "application/vnd.github.v3.star+json"


async def fetch_stargazer_history(
    owner: str,
    repo: str,
    sample_pages: int = 12,
) -> dict[str, Any]:
    """Fetch sampled star history for ``owner/repo`` as cumulative data points.

    Samples evenly across pages ``[1, min(total_pages, 400)]`` via REST and
    stamps the now-point with the current UTC timestamp. Bounded by GitHub's
    400-page deep-pagination cap: produces a truthful but limited view of
    mega-repos (first ~40K stars + real now-point). Caches successful results
    under ``github:{owner}/{repo}:stargazer-history``.

    Returns a dict with keys ``points`` (list of ``{date, count}``),
    ``current_stars``, ``repo``, ``ttl``. Raises ``ValueError`` on invalid
    identifier.
    """
    if not owner or not repo:
        raise ValueError("fetch_stargazer_history requires owner and repo")

    identifier = f"{owner}/{repo}"
    cache = get_cache()
    cache_key = f"{_CACHE_NS}:{identifier}:stargazer-history"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    result = await _fetch_stargazer_history_rest(owner, repo, sample_pages)
    cache.set(cache_key, result, STARGAZER_HISTORY_TTL)
    return result


_STARGAZER_COUNT_GRAPHQL_QUERY = """
query($owner: String!, $repo: String!) {
  repository(owner: $owner, name: $repo) {
    stargazerCount
  }
}
"""


async def _fetch_stargazer_count_graphql(
    owner: str,
    repo: str,
    auth_token: str | None,
) -> int:
    """Fetch ``stargazerCount`` for a repo via GraphQL — second source for
    cross-validation against the REST ``/repos`` ``stargazers_count`` field.

    Returns 0 on any failure (breaker open, network error, malformed payload,
    repo not found, missing scope). The caller treats 0 as "couldn't verify"
    and proceeds with REST data only — failure to cross-check should never
    *block* the chart, only *warn* when both sources disagree.
    """
    try:
        payload = await fetch_graphql(
            _STARGAZER_COUNT_GRAPHQL_QUERY,
            variables={"owner": owner, "repo": repo},
            provider=_PROVIDER_GRAPHQL,
            auth_token=auth_token,
        )
    except (ConnectorError, CircuitOpenError) as exc:
        _LOGGER.warning(
            "stargazerCount cross-check fetch failed: %s — proceeding with REST only",
            exc,
        )
        return 0
    repo_node = (payload.get("data") or {}).get("repository") if isinstance(payload, dict) else None
    if not isinstance(repo_node, dict):
        return 0
    try:
        return int(repo_node.get("stargazerCount") or 0)
    except (TypeError, ValueError):
        return 0


async def _fetch_stargazer_history_rest(
    owner: str,
    repo: str,
    sample_pages: int = 12,
) -> dict[str, Any]:
    """REST-based stargazer sampling implementation.

    Samples evenly across pages ``[1, min(total_pages, 400)]`` and stamps the
    now-point with the current UTC timestamp. Works unauth at 60 req/hr but
    caps at ~40k stars on mega-repos (GitHub's deep-pagination wall).

    v0.2.16-fix3: token-pinned across all sub-requests so /repos and every
    /stargazers?page=N call see a consistent view (pre-fix, token rotation
    within a single fetch could land different sub-calls on different tokens
    and pick up GitHub edge-cache disagreements). Also cross-checks
    total_stars against a second source (GraphQL repository.stargazerCount);
    if the two disagree by >2x, returns ``{points: [], current_stars: <max>}``
    so the chart resolver renders the verified hero number with HISTORY
    UNAVAILABLE in the chart body — never a wrong curve.
    """
    identifier = f"{owner}/{repo}"

    # Pin one token for the entire operation so /repos and every /stargazers
    # sub-call see a consistent view. Token rotation happens BETWEEN logical
    # operations (e.g. between fetch_stargazer_history and fetch_user_stats),
    # not within them.
    pinned_token = pin_github_token()

    # Step 1: total stars (REST source)
    repo_url = f"https://api.github.com/repos/{identifier}"
    repo_data = await fetch_json(repo_url, provider=_PROVIDER_CORE, auth_token=pinned_token)
    total_stars = int(repo_data.get("stargazers_count", 0))
    if total_stars == 0:
        return {
            "points": [],
            "current_stars": 0,
            "repo": identifier,
            "ttl": STARGAZER_HISTORY_TTL,
        }

    # Step 1b: cross-check total_stars against a second source (GraphQL).
    # GitHub's REST and GraphQL endpoints are served by different infrastructure
    # with different cache layers — if BOTH report the same number, we have
    # high confidence; if they disagree by >2x we trust neither curve and
    # return an empty-state chart with the verified hero number.
    cross_check_stars = await _fetch_stargazer_count_graphql(owner, repo, pinned_token)
    if cross_check_stars > 0:
        ratio = max(total_stars, cross_check_stars) / max(min(total_stars, cross_check_stars), 1)
        if ratio > 2.0:
            _LOGGER.warning(
                "stargazer_count cross-check disagreement: REST=%d GraphQL=%d (%.1fx). "
                "Returning empty-state chart with verified hero (max of the two) — never a wrong curve.",
                total_stars,
                cross_check_stars,
                ratio,
            )
            return {
                "points": [],
                "current_stars": max(total_stars, cross_check_stars),
                "repo": identifier,
                "ttl": STARGAZER_HISTORY_TTL,
            }
        # Sources agree within 2x — trust the GraphQL number (more reliable
        # for total counts) and proceed with REST sampling for history.
        total_stars = cross_check_stars

    # Step 2: compute total pages (clamped at GitHub's deep-pagination cap)
    total_pages = max(1, math.ceil(total_stars / _STARGAZER_PAGE_SIZE))
    effective_pages = min(total_pages, _STARGAZER_PAGE_CAP)

    # Single-page case: repo has ≤ 100 stars. The "first starred_at of the page"
    # sampling trick would otherwise collapse to a single aggregated point plus
    # a duplicate-date "now" point, producing a zero time-range polyline. Use
    # each stargazer's own timestamp instead — the whole page fits in one call.
    if total_pages == 1:
        single_page_url = f"https://api.github.com/repos/{identifier}/stargazers?per_page={_STARGAZER_PAGE_SIZE}&page=1"
        page_payload = await fetch_json(
            single_page_url,
            provider=_PROVIDER_CORE,
            headers={"Accept": _STARGAZER_ACCEPT_HEADER},
            auth_token=pinned_token,
        )
        single_page_points: list[dict[str, Any]] = []
        if isinstance(page_payload, list):
            for idx, entry in enumerate(page_payload):
                if isinstance(entry, dict) and entry.get("starred_at"):
                    single_page_points.append({"date": entry["starred_at"], "count": idx + 1})
        return {
            "points": single_page_points,
            "current_stars": total_stars,
            "repo": identifier,
            "ttl": STARGAZER_HISTORY_TTL,
        }

    # Cap the sample count at the number of reachable pages.
    sample_count = min(sample_pages, effective_pages)

    # Step 3: pick evenly distributed page numbers (always include first + last).
    if sample_count == 1:
        page_numbers: list[int] = [1]
    else:
        step = (effective_pages - 1) / (sample_count - 1)
        page_numbers = sorted({max(1, round(1 + step * i)) for i in range(sample_count)})

    async def _fetch_page(page: int) -> tuple[int, list[dict[str, Any]]]:
        url = f"https://api.github.com/repos/{identifier}/stargazers?per_page={_STARGAZER_PAGE_SIZE}&page={page}"
        data = await fetch_json(
            url,
            provider=_PROVIDER_CORE,
            headers={"Accept": _STARGAZER_ACCEPT_HEADER},
            auth_token=pinned_token,
        )
        if not isinstance(data, list):
            return page, []
        return page, data

    # Step 4: concurrent fetch
    results = await asyncio.gather(*[_fetch_page(p) for p in page_numbers], return_exceptions=True)

    points: list[dict[str, Any]] = []
    for item in results:
        if isinstance(item, BaseException):
            continue
        page, payload = item
        if not payload:
            continue
        first = payload[0]
        starred_at = first.get("starred_at") if isinstance(first, dict) else None
        if not starred_at:
            continue
        cumulative = (page - 1) * _STARGAZER_PAGE_SIZE
        if cumulative == 0:
            cumulative = 1  # first starred timestamp → at least 1 star
        points.append({"date": starred_at, "count": cumulative})

    # Append an honest "now" point: real current star total at real current
    # timestamp. For mega-repos where sampling is capped at page 400, the
    # deepest reachable starred_at may be years old — using that as the
    # terminal timestamp produced polylines that ended in the past. The count
    # is still the real stargazers_count; only the timestamp becomes "now".
    if points:
        points.append({"date": datetime.now(UTC).isoformat(), "count": total_stars})
    points.sort(key=lambda p: p["date"])

    return {
        "points": points,
        "current_stars": total_stars,
        "repo": identifier,
        "ttl": STARGAZER_HISTORY_TTL,
    }


# ── Session 2A+2B: contribution calendar scraping ──────────────────────────


# Regex to extract contribution cells from github.com/users/{u}/contributions HTML.
# Attributes may appear in any order on the <td>, so we match the full tag and
# use named groups to extract data-date and data-level from anywhere within it.
_CELL_RE = re.compile(
    r'<td(?=[^>]*\bclass="[^"]*ContributionCalendar-day[^"]*")'
    r'(?=[^>]*\bdata-date="(?P<date>\d{4}-\d{2}-\d{2})")'
    r'(?=[^>]*\bdata-level="(?P<level>\d+)")'
    r"[^>]*>",
    re.IGNORECASE,
)

# Tooltip count extraction. GitHub emits a ``<tool-tip>`` element right before
# each ``<td>`` with text like ``"12 contributions on Friday, April 11, 2025"``
# or ``"No contributions on ..."``. GitHub's tooltip uses a MONTH-NAME date
# format, not ISO, so we do NOT try to extract the date from the tooltip —
# instead we pair tooltips and cells positionally in document order.
_COUNT_TOOLTIP_RE = re.compile(
    r"<tool-tip[^>]*>\s*(?P<count>\d+|No)\s+contributions?",
    re.IGNORECASE,
)


# Lower-bound contribution counts inferred from GitHub's 0-4 intensity levels.
# Used only when the tooltip element is missing from the HTML response.
_LEVEL_ESTIMATE: dict[int, int] = {
    0: 0,
    1: 1,
    2: 4,
    3: 10,
    4: 20,
}


def _level_from_count(count: int) -> int:
    """Inverse of ``_LEVEL_ESTIMATE`` — bucket a contribution count into 0-4.

    Used by the GraphQL path where the API gives us an exact count but the
    heatmap template still wants a 0-4 ``level`` for cell color binning.
    Thresholds match the lower bounds of ``_LEVEL_ESTIMATE`` so a round-trip
    (count → level → estimated count) preserves the bucket.
    """
    if count <= 0:
        return 0
    if count < 4:
        return 1
    if count < 10:
        return 2
    if count < 20:
        return 3
    return 4


def _compute_streak(heatmap_grid: list[dict[str, Any]]) -> int:
    """Count consecutive non-zero days from the tail of the heatmap.

    The most recent day (index 0 from the tail) is allowed to be zero as
    a grace day — GitHub renders today's empty cell before the user has
    committed today, and a morning stats check shouldn't report a false
    0-day streak. Any zero day AFTER the first one still breaks the streak.
    """
    streak = 0
    for i, cell in enumerate(reversed(heatmap_grid)):
        count = int(cell.get("count", 0) or 0)
        if count > 0:
            streak += 1
        elif i == 0:
            continue
        else:
            break
    return streak


def _classify_failure(status_code: int | None) -> str:
    """Categorize an HTTP failure for log dashboards.

    Distinguishes rate-limit (the dominant cause of v0.2.10's silent-zero
    bug) from auth, validation, and transient network errors so an alert
    pipeline can react differently to each.
    """
    if status_code in (403, 429):
        return "rate_limit"
    if status_code == 401:
        return "auth"
    if status_code == 422:
        return "validation"
    if status_code is None:
        return "transient"
    return "unknown"


def _extract_status_code(exc: BaseException) -> int | None:
    """Walk the exception chain to find an HTTP status code if present."""
    current: BaseException | None = exc
    while current is not None:
        response = getattr(current, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
        current = current.__cause__
    return None


def parse_contribution_html(html: str) -> dict[str, Any]:
    """Parse a GitHub contribution calendar HTML response.

    Returns a dict with keys ``contrib_total``, ``streak_days``, and
    ``heatmap_grid`` (a list of ``{date, count, level}`` entries sorted
    chronologically). Missing/unparseable inputs return zeros with an
    empty heatmap — never raises on malformed markup.

    This is a public helper (tested in isolation) so the contract is stable
    even if ``_fetch_contribution_data`` changes how the HTML is fetched.

    Strategy: extract tooltip counts and td cells as two parallel lists in
    document order, then zip them. GitHub always emits one tooltip per cell,
    so positional alignment is reliable. Cells without a matching tooltip
    (e.g. malformed partial markup) fall back to the ``_LEVEL_ESTIMATE`` map.
    """
    # Ordered list of exact counts from tooltips.
    tooltip_counts: list[int] = []
    for match in _COUNT_TOOLTIP_RE.finditer(html):
        raw_count = match.group("count")
        count = 0 if raw_count.lower() == "no" else int(raw_count)
        tooltip_counts.append(count)

    cells: list[dict[str, Any]] = []
    for idx, match in enumerate(_CELL_RE.finditer(html)):
        date = match.group("date")
        level = int(match.group("level"))
        # Prefer positional tooltip count; fall back to level-estimate.
        count = tooltip_counts[idx] if idx < len(tooltip_counts) else _LEVEL_ESTIMATE.get(level, 0)
        cells.append({"date": date, "count": count, "level": level})

    # Chronological sort (GitHub returns oldest-first already, but make it explicit).
    cells.sort(key=lambda c: c["date"])

    contrib_total = sum(c["count"] for c in cells)

    return {
        "contrib_total": contrib_total,
        "streak_days": _compute_streak(cells),
        "heatmap_grid": cells,
    }


async def _fetch_contribution_data(username: str) -> Any:
    """Scrape GitHub's public contribution calendar for ``username``.

    Uses ``github.com/users/{username}/contributions`` (HTML page), which is
    public and unauthenticated. The username is strictly validated against
    GitHub's own allowed character set before interpolation to eliminate
    path-injection risk.

    Returns the same shape as :func:`parse_contribution_html` on success,
    or the ``_FETCH_FAILED`` sentinel on typed connector failures
    (``ConnectorError`` / ``CircuitOpenError``). Programming errors
    (``ValueError``, ``RuntimeError``, etc.) propagate uncaught — the
    silent-zero anti-pattern would mask real bugs as transient outages.
    """
    if not _USERNAME_RE.match(username or ""):
        raise ValueError(f"Invalid GitHub username: {username!r}")

    cache = get_cache()
    cache_key = f"{_CACHE_NS}:{username}:contributions"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"https://github.com/users/{username}/contributions"
    try:
        html = await fetch_text(url, provider=_PROVIDER_CORE, headers={"Accept": "text/html"})
    except (ConnectorError, CircuitOpenError) as exc:
        # Sentinel propagation: signal failure upstream rather than caching
        # a zero-filled success-shaped dict. Caller decides whether to mark
        # contrib_total / streak_days as stale and what TTL to use.
        _LOGGER.warning(
            "github contribution scrape failed",
            extra={
                "url": url,
                "provider": _PROVIDER_CORE,
                "error_class": type(exc).__name__,
                "error": str(exc),
            },
        )
        return _FETCH_FAILED

    parsed = parse_contribution_html(html)
    cache.set(cache_key, parsed, USER_STATS_TTL)
    return parsed


# ── Session 2A+2B: aggregated user stats (stats card connector data) ──────


# GraphQL query — single round-trip alternative to the 5 REST sub-fetches.
# Eliminates the ``search/*`` dependency that produced v0.2.10's silent-zero
# bug: the ``contributionsCollection`` aggregate fields are not subject to
# the per-resource secondary rate limit that 403s the search API at burst.
_USER_STATS_QUERY = """
query($login: String!) {
  user(login: $login) {
    avatarUrl
    bio
    followers { totalCount }
    repositories(
      first: 100
      ownerAffiliations: OWNER
      orderBy: {field: STARGAZERS, direction: DESC}
    ) {
      totalCount
      nodes {
        stargazerCount
        primaryLanguage { name }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { contributionCount, date }
        }
      }
    }
  }
}
"""


async def _fetch_user_stats_graphql(username: str) -> Any:
    """GraphQL primary path — returns the unified stats dict or ``_FETCH_FAILED``.

    Returns ``_FETCH_FAILED`` (sentinel) when the GraphQL endpoint is
    unreachable, the breaker is open, the response is malformed, or
    ``data.user`` is null. The caller falls back to the REST aggregator.
    """
    try:
        payload = await fetch_graphql(
            _USER_STATS_QUERY,
            variables={"login": username},
            provider=_PROVIDER_GRAPHQL,
        )
    except (ConnectorError, CircuitOpenError) as exc:
        _LOGGER.warning(
            "github graphql user stats failed",
            extra={
                "username": username,
                "provider": _PROVIDER_GRAPHQL,
                "error_class": type(exc).__name__,
                "status_code": _extract_status_code(exc),
                "classification": _classify_failure(_extract_status_code(exc)),
                "error": str(exc),
            },
        )
        return _FETCH_FAILED

    user = (payload.get("data") or {}).get("user") if isinstance(payload, dict) else None
    if not isinstance(user, dict):
        # Either ``data.user`` is null (login mismatch, missing scope) or the
        # response carries query-level errors. Both fall back to REST.
        _LOGGER.warning(
            "github graphql user stats: malformed payload",
            extra={
                "username": username,
                "errors": payload.get("errors") if isinstance(payload, dict) else None,
            },
        )
        return _FETCH_FAILED

    stale_fields: set[str] = set()

    repos_node = user.get("repositories")
    cc = user.get("contributionsCollection")
    calendar = (cc or {}).get("contributionCalendar") if isinstance(cc, dict) else None
    repo_nodes = (repos_node or {}).get("nodes") if isinstance(repos_node, dict) else None

    # Stars + language breakdown — degrade to stale if the repos sub-tree
    # is missing entirely. Empty list (no repos) is a real zero, not stale.
    stars_total: int | None = 0
    language_counts: dict[str, int] = {}
    if not isinstance(repo_nodes, list):
        stars_total = None
        stale_fields.add("stars_total")
    else:
        running = 0
        for r in repo_nodes:
            if not isinstance(r, dict):
                continue
            running += int(r.get("stargazerCount", 0) or 0)
            primary_lang = r.get("primaryLanguage")
            if isinstance(primary_lang, dict):
                name = primary_lang.get("name")
                if name:
                    language_counts[str(name)] = language_counts.get(str(name), 0) + 1
        stars_total = running

    top_language = ""
    language_breakdown: list[dict[str, Any]] = []
    if language_counts:
        total_langs = sum(language_counts.values())
        sorted_langs = sorted(language_counts.items(), key=lambda kv: kv[1], reverse=True)
        top_language = sorted_langs[0][0]
        language_breakdown = [
            {"name": name, "pct": round(100 * count / total_langs, 1), "count": count}
            for name, count in sorted_langs[:6]
        ]

    # Flatten weeks → date-sorted heatmap_grid in the same shape the REST
    # path produces. ``level`` is bucketed from the exact count so existing
    # heatmap templates render identically regardless of source.
    heatmap_grid: list[dict[str, Any]] = []
    weeks = calendar.get("weeks") if isinstance(calendar, dict) else None
    if isinstance(weeks, list):
        for week in weeks:
            if not isinstance(week, dict):
                continue
            for day in week.get("contributionDays") or []:
                if not isinstance(day, dict):
                    continue
                count = int(day.get("contributionCount", 0) or 0)
                heatmap_grid.append(
                    {"date": str(day.get("date", "")), "count": count, "level": _level_from_count(count)}
                )
        heatmap_grid.sort(key=lambda c: c["date"])

    def _gql_int_or_stale(obj: Any, key: str, field: str) -> int | None:
        if not isinstance(obj, dict):
            stale_fields.add(field)
            return None
        val = obj.get(key)
        if val is None:
            stale_fields.add(field)
            return None
        return int(val or 0)

    commits_total = _gql_int_or_stale(cc, "totalCommitContributions", "commits_total")
    prs_total = _gql_int_or_stale(cc, "totalPullRequestContributions", "prs_total")
    issues_total = _gql_int_or_stale(cc, "totalIssueContributions", "issues_total")
    contrib_total = _gql_int_or_stale(calendar, "totalContributions", "contrib_total")

    streak_days: int | None
    if "contrib_total" in stale_fields:
        streak_days = None
        stale_fields.add("streak_days")
    else:
        streak_days = _compute_streak(heatmap_grid)

    followers_obj = user.get("followers")
    followers_count: int | None
    if isinstance(followers_obj, dict) and followers_obj.get("totalCount") is not None:
        followers_count = int(followers_obj.get("totalCount") or 0)
    else:
        followers_count = None
        stale_fields.add("followers")

    repo_count: int | None
    if isinstance(repos_node, dict) and repos_node.get("totalCount") is not None:
        repo_count = int(repos_node.get("totalCount") or 0)
    else:
        repo_count = None
        stale_fields.add("repo_count")

    return {
        "username": username,
        "avatar_url": str(user.get("avatarUrl") or ""),
        "bio": str(user.get("bio") or ""),
        "stars_total": stars_total,
        "commits_total": commits_total,
        "prs_total": prs_total,
        "issues_total": issues_total,
        "contrib_total": contrib_total,
        "streak_days": streak_days,
        "top_language": top_language,
        "language_breakdown": language_breakdown,
        "repo_count": repo_count,
        "followers": followers_count,
        "heatmap_grid": heatmap_grid,
        "_stale_fields": sorted(stale_fields),
        "ttl": USER_STATS_TTL,
    }


async def _fetch_user_stats_rest(username: str) -> dict[str, Any]:
    """REST fallback — six concurrent sub-fetches with sentinel propagation.

    Each failed sub-fetch is recorded in ``_stale_fields`` (a sorted list
    of field names) and the corresponding output value is ``None``. The
    resolver detects ``_stale_fields`` and renders ``—`` for those fields
    rather than misrepresenting failure as a real ``0``.
    """

    async def _safe_fetch_json(url: str, provider: str) -> Any:
        try:
            return await fetch_json(url, provider=provider)
        except (ConnectorError, CircuitOpenError) as exc:
            status = _extract_status_code(exc)
            _LOGGER.warning(
                "github rest sub-fetch failed",
                extra={
                    "url": url,
                    "provider": provider,
                    "error_class": type(exc).__name__,
                    "status_code": status,
                    "classification": _classify_failure(status),
                    "error": str(exc),
                },
            )
            return _FETCH_FAILED

    user_url = f"https://api.github.com/users/{username}"
    repos_url = f"https://api.github.com/users/{username}/repos?sort=stars&per_page=100&type=owner"
    commits_url = f"https://api.github.com/search/commits?q=author:{username}&per_page=1"
    prs_url = f"https://api.github.com/search/issues?q=author:{username}+type:pr&per_page=1"
    issues_url = f"https://api.github.com/search/issues?q=author:{username}+type:issue&per_page=1"

    user_data, repos_data, commits_data, prs_data, issues_data, contrib_data = await asyncio.gather(
        _safe_fetch_json(user_url, _PROVIDER_CORE),
        _safe_fetch_json(repos_url, _PROVIDER_CORE),
        _safe_fetch_json(commits_url, _PROVIDER_SEARCH),
        _safe_fetch_json(prs_url, _PROVIDER_SEARCH),
        _safe_fetch_json(issues_url, _PROVIDER_SEARCH),
        _fetch_contribution_data(username),
    )

    stale_fields: set[str] = set()

    avatar_url = ""
    bio = ""
    repo_count: int | None = 0
    followers: int | None = 0
    if user_data is _FETCH_FAILED:
        repo_count = None
        followers = None
        stale_fields.update({"repo_count", "followers"})
    elif isinstance(user_data, dict):
        avatar_url = str(user_data.get("avatar_url", ""))
        bio = str(user_data.get("bio") or "")
        repo_count = int(user_data.get("public_repos", 0) or 0)
        followers = int(user_data.get("followers", 0) or 0)

    stars_total: int | None = 0
    language_counts: dict[str, int] = {}
    if repos_data is _FETCH_FAILED:
        stars_total = None
        stale_fields.add("stars_total")
    elif isinstance(repos_data, list):
        running = 0
        for r in repos_data:
            if not isinstance(r, dict):
                continue
            running += int(r.get("stargazers_count", 0) or 0)
            lang = r.get("language")
            if lang:
                language_counts[str(lang)] = language_counts.get(str(lang), 0) + 1
        stars_total = running

    top_language = ""
    language_breakdown: list[dict[str, Any]] = []
    if language_counts:
        total_langs = sum(language_counts.values())
        sorted_langs = sorted(language_counts.items(), key=lambda kv: kv[1], reverse=True)
        top_language = sorted_langs[0][0]
        language_breakdown = [
            {"name": name, "pct": round(100 * count / total_langs, 1), "count": count}
            for name, count in sorted_langs[:6]
        ]

    def _total_count_or_stale(payload: Any, field: str) -> int | None:
        if payload is _FETCH_FAILED:
            stale_fields.add(field)
            return None
        if isinstance(payload, dict):
            return int(payload.get("total_count", 0) or 0)
        return 0

    commits_total = _total_count_or_stale(commits_data, "commits_total")
    prs_total = _total_count_or_stale(prs_data, "prs_total")
    issues_total = _total_count_or_stale(issues_data, "issues_total")

    contrib_total: int | None
    streak_days: int | None
    heatmap_grid: list[dict[str, Any]]
    if contrib_data is _FETCH_FAILED:
        contrib_total = None
        streak_days = None
        heatmap_grid = []
        stale_fields.update({"contrib_total", "streak_days"})
    elif isinstance(contrib_data, dict):
        contrib_total = int(contrib_data.get("contrib_total", 0) or 0)
        streak_days = int(contrib_data.get("streak_days", 0) or 0)
        hg = contrib_data.get("heatmap_grid", [])
        heatmap_grid = list(hg) if isinstance(hg, list) else []
    else:
        contrib_total = 0
        streak_days = 0
        heatmap_grid = []

    return {
        "username": username,
        "avatar_url": avatar_url,
        "bio": bio,
        "stars_total": stars_total,
        "commits_total": commits_total,
        "prs_total": prs_total,
        "issues_total": issues_total,
        "contrib_total": contrib_total,
        "streak_days": streak_days,
        "top_language": top_language,
        "language_breakdown": language_breakdown,
        "repo_count": repo_count,
        "followers": followers,
        "heatmap_grid": heatmap_grid,
        "_stale_fields": sorted(stale_fields),
        "ttl": USER_STATS_TTL,
    }


async def fetch_user_stats(username: str) -> dict[str, Any]:
    """Fetch everything a stats card needs for ``username``.

    Two-tier strategy:

    1. **GraphQL primary** (``_fetch_user_stats_graphql``) — single
       round-trip via ``api.github.com/graphql``. Replaces the 5 REST
       sub-fetches with one query that uses first-class
       ``contributionsCollection`` aggregates instead of search-API
       counts. Eliminates the per-resource secondary rate limit that
       produced v0.2.10's silent-zero bug.

    2. **REST fallback** (``_fetch_user_stats_rest``) — runs
       automatically when GraphQL fails for any reason (no token,
       network error, breaker open, malformed response, ``data.user``
       null). Six concurrent sub-fetches with sentinel propagation
       so search-API rate-limit 403s surface as ``_stale_fields``
       rather than silent zeros.

    The result shape is identical for both paths. ``_stale_fields``
    enumerates fields that failed (empty list when fully successful);
    the resolver renders ``—`` for stale fields and the cache layer
    uses ``FAILURE_CACHE_TTL`` (30s) instead of ``USER_STATS_TTL``
    (3600s) so transient failures self-heal in seconds, not an hour.
    """
    if not _USERNAME_RE.match(username or ""):
        raise ValueError(f"Invalid GitHub username: {username!r}")

    cache = get_cache()
    cache_key = f"{_CACHE_NS}:{username}:profile-stats"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    primary = await _fetch_user_stats_graphql(username)
    if primary is _FETCH_FAILED:
        result = await _fetch_user_stats_rest(username)
    else:
        result = primary

    ttl = FAILURE_CACHE_TTL if result.get("_stale_fields") else USER_STATS_TTL
    cache.set(cache_key, result, ttl)
    return result
