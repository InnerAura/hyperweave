"""GitHub connector."""

from __future__ import annotations

import asyncio
import math
import re
from typing import Any

from hyperweave.connectors.base import fetch_json, fetch_text
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


_STARGAZER_PAGE_SIZE = 30
_STARGAZER_ACCEPT_HEADER = "application/vnd.github.v3.star+json"


async def fetch_stargazer_history(
    owner: str,
    repo: str,
    sample_pages: int = 12,
) -> dict[str, Any]:
    """Fetch sampled star history for ``owner/repo`` as cumulative data points.

    Strategy:
      1. GET ``/repos/{owner}/{repo}`` → total ``stargazers_count``.
      2. Compute total pages (30 per page on the stargazers endpoint).
      3. Sample ``sample_pages`` evenly distributed page numbers across
         ``[1, total_pages]`` and fetch them concurrently with the
         ``application/vnd.github.v3.star+json`` ``Accept`` header so each
         element contains a ``starred_at`` timestamp.
      4. From each sampled page take the FIRST starred_at and use it as the
         time marker for the cumulative count at ``(page - 1) * 30``.
      5. Cache under ``github:{owner}/{repo}:stargazer-history``.

    Returns a dict with keys ``points`` (list of ``{date, count}``), ``current_stars``,
    ``repo``, ``ttl``. Raises ``ValueError`` on invalid identifier.
    """
    if not owner or not repo:
        raise ValueError("fetch_stargazer_history requires owner and repo")

    identifier = f"{owner}/{repo}"
    cache = get_cache()
    cache_key = f"{PROVIDER}:{identifier}:stargazer-history"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    # Step 1: total stars
    repo_url = f"https://api.github.com/repos/{identifier}"
    repo_data = await fetch_json(repo_url, provider=PROVIDER)
    total_stars = int(repo_data.get("stargazers_count", 0))
    if total_stars == 0:
        empty_result: dict[str, Any] = {
            "points": [],
            "current_stars": 0,
            "repo": identifier,
            "ttl": STARGAZER_HISTORY_TTL,
        }
        cache.set(cache_key, empty_result, STARGAZER_HISTORY_TTL)
        return empty_result

    # Step 2: compute total pages
    total_pages = max(1, math.ceil(total_stars / _STARGAZER_PAGE_SIZE))
    # Cap the sample count at the number of available pages.
    sample_count = min(sample_pages, total_pages)

    # Step 3: pick evenly distributed page numbers (always include first + last).
    if sample_count == 1:
        page_numbers: list[int] = [1]
    else:
        step = (total_pages - 1) / (sample_count - 1)
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

    # Always append the "now" point with the current total.
    if points:
        latest_date = max(p["date"] for p in points)
        points.append({"date": latest_date, "count": total_stars})
    points.sort(key=lambda p: p["date"])

    result: dict[str, Any] = {
        "points": points,
        "current_stars": total_stars,
        "repo": identifier,
        "ttl": STARGAZER_HISTORY_TTL,
    }
    cache.set(cache_key, result, STARGAZER_HISTORY_TTL)
    return result


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
