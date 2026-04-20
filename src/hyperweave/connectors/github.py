"""GitHub connector."""

from __future__ import annotations

import asyncio
import base64
import math
import re
from datetime import UTC, datetime
from typing import Any

from hyperweave.connectors.base import (
    CircuitOpenError,
    ConnectorError,
    _get_github_token,
    fetch_graphql,
    fetch_json,
    fetch_text,
)
from hyperweave.connectors.cache import get_cache

PROVIDER = "github"
CACHE_TTL = 300

# Longer TTL for stargazer history + user stats — append-only data that changes slowly.
STARGAZER_HISTORY_TTL = 3600
USER_STATS_TTL = 3600

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
    cache_key = f"{PROVIDER}:{identifier}:build"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    # Get default branch
    repo_url = f"https://api.github.com/repos/{identifier}"
    repo_data = await fetch_json(repo_url, provider=PROVIDER)
    default_branch = repo_data.get("default_branch", "main")

    # 1. Check Runs API (GitHub Actions, modern CI)
    checks_url = f"https://api.github.com/repos/{identifier}/commits/{default_branch}/check-runs"
    checks_data = await fetch_json(checks_url, provider=PROVIDER)
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
        status_data = await fetch_json(status_url, provider=PROVIDER)
        state = status_data.get("state", "unknown")
        total = status_data.get("total_count", 0)
        if total == 0:
            value = "unknown"
        else:
            display = {"success": "passing", "pending": "building", "failure": "failing", "error": "error"}
            value = display.get(state, state)

    result: dict[str, Any] = {
        "provider": PROVIDER,
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
    cache_key = f"{PROVIDER}:{identifier}:{metric}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    url = f"https://api.github.com/repos/{identifier}"
    data = await fetch_json(url, provider=PROVIDER)

    api_key = _METRIC_MAP.get(metric)
    if api_key is None:
        raise ValueError(f"Unknown GitHub metric {metric!r}. Available: {sorted([*_METRIC_MAP, 'build'])}")

    raw_value = data.get(api_key)

    # License is nested
    if metric == "license" and isinstance(raw_value, dict):
        raw_value = raw_value.get("spdx_id", raw_value.get("name", "Unknown"))

    result: dict[str, Any] = {
        "provider": PROVIDER,
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
_STARGAZER_PAGE_CAP = 400
_STARGAZER_ACCEPT_HEADER = "application/vnd.github.v3.star+json"

# GraphQL cursor-offset sampling constants.
#
# GitHub's GraphQL cursors decode to the literal text ``cursor:<N>`` where
# N is a 0-indexed offset into the stargazer list. By Base64-encoding
# ``cursor:<N-1>`` we can construct an ``after:`` anchor that lets ``first: 1``
# return exactly the Nth stargazer. This bypasses GitHub's 400-page REST cap
# and lets us sample any offset in a 500K-star repo cheaply.
#
# 12 offsets * 1 node per call = 12 GraphQL points per cold fetch.
# ``asyncio.Semaphore(_GRAPHQL_CONCURRENCY)`` caps fan-out so bursty
# same-token parallelism doesn't trigger GitHub's per-minute abuse detection.
_DEFAULT_SAMPLE_COUNT = 12
_GRAPHQL_CONCURRENCY = 4

_CURSOR_OFFSET_QUERY = """
query StargazerAtOffset($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    stargazerCount
    stargazers(first: 1, after: $cursor) {
      edges { starredAt }
    }
  }
}
"""


def _cursor_for_offset(offset: int) -> str | None:
    """Return the Base64-encoded cursor for a 1-indexed stargazer position.

    GitHub's GraphQL cursors decode to ``cursor:<N>`` where N is 0-indexed.
    Constructing them lets us sample any offset within a repo's stargazer
    list, bypassing both the REST 400-page cap and the cost of walking
    every page via cursor pagination.

    Returns None for ``offset <= 1`` (no cursor needed — this IS the first
    entry; passing ``after: None`` to GraphQL starts from the beginning).
    """
    if offset <= 1:
        return None
    return base64.b64encode(f"cursor:{offset - 1}".encode()).decode()


async def fetch_stargazer_history(
    owner: str,
    repo: str,
    sample_pages: int = 12,
) -> dict[str, Any]:
    """Fetch sampled star history for ``owner/repo`` as cumulative data points.

    Public dispatcher. Prefers GraphQL when a token is available (unlocks the
    recent-growth window on mega-repos beyond GitHub's 400-page REST cap);
    falls back to REST sampling on GraphQL failure or missing token. Caches
    successful results under ``github:{owner}/{repo}:stargazer-history``.

    Returns a dict with keys ``points`` (list of ``{date, count}``),
    ``current_stars``, ``repo``, ``ttl``. Raises ``ValueError`` on invalid
    identifier.
    """
    if not owner or not repo:
        raise ValueError("fetch_stargazer_history requires owner and repo")

    identifier = f"{owner}/{repo}"
    cache = get_cache()
    cache_key = f"{PROVIDER}:{identifier}:stargazer-history"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    result: dict[str, Any] | None = None

    # Primary path: GraphQL cursor-offset sampling (requires auth). Constructs
    # cursors for N evenly-distributed stargazer offsets across [1, total_stars]
    # and fetches one stargazer per offset. Bypasses GitHub's 400-page REST cap,
    # so a 361K-star repo gets 12 real points across its full lifetime instead
    # of a hockey-stick or flat line.
    if _get_github_token():
        try:
            result = await _fetch_stargazer_history_graphql(owner, repo, sample_pages)
        except (ConnectorError, CircuitOpenError):
            result = None  # fall through to REST

    if result is None:
        # Fallback path: REST sampling. Works unauth at 60 req/hr but caps at
        # ~40k stars on mega-repos (GitHub's deep-pagination wall).
        result = await _fetch_stargazer_history_rest(owner, repo, sample_pages)

    cache.set(cache_key, result, STARGAZER_HISTORY_TTL)
    return result


async def _fetch_stargazer_history_graphql(
    owner: str,
    repo: str,
    sample_count: int = _DEFAULT_SAMPLE_COUNT,
) -> dict[str, Any]:
    """Sample N stargazer timestamps at evenly-distributed cursor offsets.

    Strategy: given a repo's ``total_stars``, fetch one stargazer at each of
    N evenly-spaced offsets across ``[1, total_stars]``. Each offset maps to
    a constructed cursor (``base64("cursor:<N-1>")``); GraphQL returns that
    stargazer's ``starred_at``. Pair with the known offset to form a
    ``{date, count}`` point. Appends a now-point at ``total_stars``.

    Works for any repo size — 30 stars, 2938 stars, 361k stars — because
    cursor-offset sampling is not subject to GitHub's 400-page REST cap.

    Concurrency is bounded at ``_GRAPHQL_CONCURRENCY`` to avoid tripping
    per-minute abuse-detection heuristics on bursty parallel fan-out.
    """
    identifier = f"{owner}/{repo}"

    # First query: learn total_stars and pick up the first stargazer's
    # timestamp in the same round-trip (offset 1 uses no cursor anyway).
    first_response = await fetch_graphql(
        _CURSOR_OFFSET_QUERY,
        {"owner": owner, "repo": repo, "cursor": None},
        provider=PROVIDER,
    )
    repo_data = (first_response.get("data") or {}).get("repository")
    if not repo_data:
        return _empty_stargazer_result(identifier)

    total_stars = int(repo_data.get("stargazerCount", 0))
    if total_stars == 0:
        return _empty_stargazer_result(identifier)

    first_edges = (repo_data.get("stargazers") or {}).get("edges") or []
    first_starred_at: str | None = None
    if first_edges and isinstance(first_edges[0], dict):
        first_starred_at = first_edges[0].get("starredAt")

    # Clamp sample count to total_stars — small repos get every star sampled
    # (no point requesting 12 offsets from a 5-star repo).
    effective_samples = min(sample_count, total_stars)

    # Compute evenly-distributed offsets across the full stargazer list.
    # Always includes position 1 (oldest) and position total_stars (newest).
    if effective_samples <= 1:
        offsets = [1]
    else:
        step = (total_stars - 1) / (effective_samples - 1)
        offsets = sorted({max(1, round(1 + step * i)) for i in range(effective_samples)})

    # Bounded concurrent fan-out: semaphore throttles to _GRAPHQL_CONCURRENCY
    # in-flight requests at a time. For 12 offsets at concurrency 4, that's
    # 3 waves of ≤4 calls each → ~1s cold-fetch latency.
    sem = asyncio.Semaphore(_GRAPHQL_CONCURRENCY)

    async def _fetch_one(offset: int) -> tuple[int, str | None]:
        # Offset 1 is already in hand from the total_stars lookup.
        if offset == 1 and first_starred_at is not None:
            return offset, first_starred_at
        cursor = _cursor_for_offset(offset)
        async with sem:
            resp = await fetch_graphql(
                _CURSOR_OFFSET_QUERY,
                {"owner": owner, "repo": repo, "cursor": cursor},
                provider=PROVIDER,
            )
        edges_data = (((resp.get("data") or {}).get("repository") or {}).get("stargazers") or {}).get("edges") or []
        starred_at: str | None = None
        if edges_data and isinstance(edges_data[0], dict):
            starred_at = edges_data[0].get("starredAt")
        return offset, starred_at

    results = await asyncio.gather(
        *[_fetch_one(off) for off in offsets],
        return_exceptions=True,
    )

    points: list[dict[str, Any]] = []
    for item in results:
        if isinstance(item, BaseException):
            continue
        offset, starred_at = item
        if starred_at is None:
            continue
        points.append({"date": starred_at, "count": offset})

    # Append the honest now-point: current timestamp at the real total count.
    if points:
        points.append({"date": datetime.now(UTC).isoformat(), "count": total_stars})
    points.sort(key=lambda p: p["date"])

    return {
        "points": points,
        "current_stars": total_stars,
        "repo": identifier,
        "ttl": STARGAZER_HISTORY_TTL,
    }


def _empty_stargazer_result(identifier: str) -> dict[str, Any]:
    """Shared empty-state shape for zero-star or missing-repo cases."""
    return {
        "points": [],
        "current_stars": 0,
        "repo": identifier,
        "ttl": STARGAZER_HISTORY_TTL,
    }


async def _fetch_stargazer_history_rest(
    owner: str,
    repo: str,
    sample_pages: int = 12,
) -> dict[str, Any]:
    """REST-based stargazer sampling — the v0.2.7 behavior preserved as fallback.

    Used when no ``HW_GITHUB_TOKENS`` is set or when the GraphQL path fails.
    Samples evenly across pages ``[1, min(total_pages, 400)]`` and stamps the
    now-point with the current UTC timestamp. Bounded by GitHub's 400-page
    deep-pagination cap: produces a truthful but limited view of mega-repos.
    """
    identifier = f"{owner}/{repo}"

    # Step 1: total stars
    repo_url = f"https://api.github.com/repos/{identifier}"
    repo_data = await fetch_json(repo_url, provider=PROVIDER)
    total_stars = int(repo_data.get("stargazers_count", 0))
    if total_stars == 0:
        return {
            "points": [],
            "current_stars": 0,
            "repo": identifier,
            "ttl": STARGAZER_HISTORY_TTL,
        }

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
            provider=PROVIDER,
            headers={"Accept": _STARGAZER_ACCEPT_HEADER},
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
        data = await fetch_json(url, provider=PROVIDER, headers={"Accept": _STARGAZER_ACCEPT_HEADER})
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

    # Streak: walk backwards from the latest cell, counting consecutive
    # non-zero days. The most recent cell (today) is allowed to be zero
    # as a grace day — GitHub renders today's empty cell before the user
    # has committed today, and we don't want a morning stats check to
    # report a false 0d streak for an otherwise active contributor.
    # Any zero day AFTER the first one still breaks the streak.
    streak = 0
    for i, cell in enumerate(reversed(cells)):
        if cell["count"] > 0:
            streak += 1
        elif i == 0:
            continue
        else:
            break

    return {
        "contrib_total": contrib_total,
        "streak_days": streak,
        "heatmap_grid": cells,
    }


# Lower-bound contribution counts inferred from GitHub's 0-4 intensity levels.
# Used only when the tooltip element is missing from the HTML response.
_LEVEL_ESTIMATE: dict[int, int] = {
    0: 0,
    1: 1,
    2: 4,
    3: 10,
    4: 20,
}


async def _fetch_contribution_data(username: str) -> dict[str, Any]:
    """Scrape GitHub's public contribution calendar for ``username``.

    Uses ``github.com/users/{username}/contributions`` (HTML page), which is
    public and unauthenticated. The username is strictly validated against
    GitHub's own allowed character set before interpolation to eliminate
    path-injection risk.

    Returns the same shape as :func:`parse_contribution_html`. On fetch
    failure, returns zeros with an empty heatmap_grid so the stats card
    degrades gracefully without raising.
    """
    if not _USERNAME_RE.match(username or ""):
        raise ValueError(f"Invalid GitHub username: {username!r}")

    cache = get_cache()
    cache_key = f"{PROVIDER}:{username}:contributions"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    url = f"https://github.com/users/{username}/contributions"
    try:
        html = await fetch_text(url, provider=PROVIDER, headers={"Accept": "text/html"})
    except Exception:
        empty = {"contrib_total": 0, "streak_days": 0, "heatmap_grid": []}
        cache.set(cache_key, empty, 300)  # short TTL — retry sooner
        return empty

    parsed = parse_contribution_html(html)
    cache.set(cache_key, parsed, USER_STATS_TTL)
    return parsed


# ── Session 2A+2B: aggregated user stats (stats card connector data) ──────


async def fetch_user_stats(username: str) -> dict[str, Any]:
    """Fetch everything a stats card needs for ``username``, in parallel.

    Concurrent sub-fetches:
      - ``api.github.com/users/{u}`` → avatar, bio, public_repos, followers
      - ``api.github.com/users/{u}/repos?sort=stars`` → language breakdown, total stars
      - ``api.github.com/search/commits?q=author:{u}`` → commits total_count
      - ``api.github.com/search/issues?q=author:{u}+type:pr`` → PRs total
      - ``api.github.com/search/issues?q=author:{u}+type:issue`` → issues total
      - ``github.com/users/{u}/contributions`` (HTML) → contrib total, streak, heatmap

    Any individual sub-fetch may fail; partial data is returned with zero
    placeholders so the stats card still renders. Only when ALL sub-fetches
    fail does the result look "stale" — the caller signals that via
    ``data-hw-status="stale"`` based on inspection.

    Result keys: ``username``, ``avatar_url``, ``bio``, ``stars_total``,
    ``commits_total``, ``prs_total``, ``issues_total``, ``contrib_total``,
    ``streak_days``, ``top_language``, ``language_breakdown``, ``repo_count``,
    ``followers``, ``heatmap_grid``.
    """
    if not _USERNAME_RE.match(username or ""):
        raise ValueError(f"Invalid GitHub username: {username!r}")

    cache = get_cache()
    cache_key = f"{PROVIDER}:{username}:profile-stats"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    async def _safe_fetch_json(url: str) -> Any:
        try:
            return await fetch_json(url, provider=PROVIDER)
        except Exception:
            return None

    async def _safe_contributions() -> dict[str, Any]:
        try:
            return await _fetch_contribution_data(username)
        except Exception:
            return {"contrib_total": 0, "streak_days": 0, "heatmap_grid": []}

    user_url = f"https://api.github.com/users/{username}"
    repos_url = f"https://api.github.com/users/{username}/repos?sort=stars&per_page=100&type=owner"
    commits_url = f"https://api.github.com/search/commits?q=author:{username}&per_page=1"
    prs_url = f"https://api.github.com/search/issues?q=author:{username}+type:pr&per_page=1"
    issues_url = f"https://api.github.com/search/issues?q=author:{username}+type:issue&per_page=1"

    user_data, repos_data, commits_data, prs_data, issues_data, contrib_data = await asyncio.gather(
        _safe_fetch_json(user_url),
        _safe_fetch_json(repos_url),
        _safe_fetch_json(commits_url),
        _safe_fetch_json(prs_url),
        _safe_fetch_json(issues_url),
        _safe_contributions(),
    )

    # Identity + bio
    avatar_url = ""
    bio = ""
    repo_count = 0
    followers = 0
    if isinstance(user_data, dict):
        avatar_url = str(user_data.get("avatar_url", ""))
        bio = str(user_data.get("bio") or "")
        repo_count = int(user_data.get("public_repos", 0) or 0)
        followers = int(user_data.get("followers", 0) or 0)

    # Stars total + language breakdown (aggregate owner repos only)
    stars_total = 0
    language_counts: dict[str, int] = {}
    if isinstance(repos_data, list):
        for r in repos_data:
            if not isinstance(r, dict):
                continue
            stars_total += int(r.get("stargazers_count", 0) or 0)
            lang = r.get("language")
            if lang:
                language_counts[str(lang)] = language_counts.get(str(lang), 0) + 1

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

    def _total_count(payload: Any) -> int:
        if isinstance(payload, dict):
            return int(payload.get("total_count", 0) or 0)
        return 0

    commits_total = _total_count(commits_data)
    prs_total = _total_count(prs_data)
    issues_total = _total_count(issues_data)

    contrib_total = int(contrib_data.get("contrib_total", 0) or 0)
    streak_days = int(contrib_data.get("streak_days", 0) or 0)
    heatmap_grid = contrib_data.get("heatmap_grid", [])

    result: dict[str, Any] = {
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
        "ttl": USER_STATS_TTL,
    }
    cache.set(cache_key, result, USER_STATS_TTL)
    return result
