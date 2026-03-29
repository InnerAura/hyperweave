"""GitHub connector."""

from __future__ import annotations

from typing import Any

from hyperweave.connectors.base import fetch_json
from hyperweave.connectors.cache import get_cache

PROVIDER = "github"
CACHE_TTL = 300

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
    """Fetch combined CI status via the Commit Status API.

    Works with any CI provider (GitHub Actions, Travis, CircleCI, etc.)
    by reading the combined status of the default branch HEAD.
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

    # Combined status for HEAD of default branch
    status_url = f"https://api.github.com/repos/{identifier}/commits/{default_branch}/status"
    status_data = await fetch_json(status_url, provider=PROVIDER)
    state = status_data.get("state", "unknown")  # success, pending, failure, error

    # Map GitHub states to display values
    display = {"success": "passing", "pending": "building", "failure": "failing", "error": "error"}
    value = display.get(state, state)

    result: dict[str, Any] = {
        "provider": PROVIDER,
        "identifier": identifier,
        "metric": "build",
        "value": value,
        "ttl": 120,  # shorter TTL for CI status
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
