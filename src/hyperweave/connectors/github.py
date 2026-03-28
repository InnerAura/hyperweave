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


async def fetch_metric(identifier: str, metric: str) -> dict[str, Any]:
    """Fetch a single metric from GitHub."""
    cache = get_cache()
    cache_key = f"{PROVIDER}:{identifier}:{metric}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    if "/" not in identifier:
        raise ValueError(f"GitHub identifier must be 'owner/repo', got {identifier!r}")

    url = f"https://api.github.com/repos/{identifier}"
    data = await fetch_json(url, provider=PROVIDER)

    api_key = _METRIC_MAP.get(metric)
    if api_key is None:
        raise ValueError(f"Unknown GitHub metric {metric!r}. Available: {sorted(_METRIC_MAP)}")

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
