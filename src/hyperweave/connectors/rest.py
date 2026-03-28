"""REST-based connectors (PyPI, npm, HuggingFace, Docker Hub)."""

from __future__ import annotations

from typing import Any

from hyperweave.connectors.base import fetch_json
from hyperweave.connectors.cache import get_cache


async def _fetch_cached(
    provider: str,
    identifier: str,
    metric: str,
    ttl: int,
    extractor: Any,
) -> dict[str, Any]:
    cache = get_cache()
    key = f"{provider}:{identifier}:{metric}"
    cached = cache.get(key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    value = await extractor(identifier, metric)
    result: dict[str, Any] = {
        "provider": provider,
        "identifier": identifier,
        "metric": metric,
        "value": value,
        "ttl": ttl,
    }
    cache.set(key, result, ttl)
    return result


_SLASH_ERRORS: dict[str, str] = {
    "HuggingFace": "HuggingFace identifier must be 'org/model'",
    "Docker": "Docker identifier must be 'namespace/repo'",
    "GitHub": "GitHub identifier must be 'owner/repo'",
}


def _require_slash(identifier: str, label: str) -> None:
    if "/" not in identifier:
        msg = _SLASH_ERRORS.get(label, f"{label} identifier must contain '/'")
        raise ValueError(f"{msg}, got {identifier!r}")


# -- PyPI ------------------------------------------------------------------


async def _pypi_extract(identifier: str, metric: str) -> Any:
    data = await fetch_json(f"https://pypi.org/pypi/{identifier}/json", provider="pypi")
    info: dict[str, Any] = data.get("info", {})
    extractors: dict[str, Any] = {
        "version": info.get("version"),
        "downloads": info.get("downloads", {}).get("last_month", -1),
        "license": info.get("license", "Unknown"),
        "python_requires": info.get("requires_python", "Unknown"),
    }
    if metric not in extractors:
        raise ValueError(f"Unknown PyPI metric {metric!r}. Available: {', '.join(extractors)}")
    return extractors[metric]


async def pypi_fetch_metric(identifier: str, metric: str) -> dict[str, Any]:
    """Fetch a metric from PyPI."""
    return await _fetch_cached("pypi", identifier, metric, 600, _pypi_extract)


# -- npm -------------------------------------------------------------------


async def _npm_extract(identifier: str, metric: str) -> Any:
    data = await fetch_json(f"https://registry.npmjs.org/{identifier}", provider="npm")
    if metric == "version":
        return data.get("dist-tags", {}).get("latest", "unknown")
    if metric == "license":
        v = data.get("license")
        if v is None:
            latest = data.get("dist-tags", {}).get("latest", "")
            v = data.get("versions", {}).get(latest, {}).get("license", "Unknown")
        return v
    if metric == "downloads":
        dl = await fetch_json(
            f"https://registry.npmjs.org/-/downloads/point/last-week/{identifier}",
            provider="npm",
        )
        return dl.get("downloads", 0)
    raise ValueError(f"Unknown npm metric {metric!r}. Available: version, downloads, license")


async def npm_fetch_metric(identifier: str, metric: str) -> dict[str, Any]:
    """Fetch a metric from npm."""
    return await _fetch_cached("npm", identifier, metric, 600, _npm_extract)


# -- HuggingFace -----------------------------------------------------------


async def _hf_extract(identifier: str, metric: str) -> Any:
    _require_slash(identifier, "HuggingFace")
    data = await fetch_json(f"https://huggingface.co/api/models/{identifier}", provider="huggingface")
    extractors: dict[str, Any] = {
        "downloads": data.get("downloads", 0),
        "likes": data.get("likes", 0),
        "tags": data.get("tags", []),
        "pipeline_tag": data.get("pipeline_tag", "unknown"),
        "library_name": data.get("library_name", "unknown"),
    }
    if metric not in extractors:
        raise ValueError(f"Unknown HuggingFace metric {metric!r}. Available: {', '.join(extractors)}")
    return extractors[metric]


async def hf_fetch_metric(identifier: str, metric: str) -> dict[str, Any]:
    """Fetch a metric from HuggingFace."""
    return await _fetch_cached("huggingface", identifier, metric, 600, _hf_extract)


# -- Docker Hub ------------------------------------------------------------


async def _docker_extract(identifier: str, metric: str) -> Any:
    _require_slash(identifier, "Docker")
    data = await fetch_json(f"https://hub.docker.com/v2/repositories/{identifier}", provider="docker")
    extractors: dict[str, Any] = {
        "pull_count": data.get("pull_count", 0),
        "star_count": data.get("star_count", 0),
        "last_updated": data.get("last_updated", "unknown"),
    }
    if metric not in extractors:
        raise ValueError(f"Unknown Docker metric {metric!r}. Available: {', '.join(extractors)}")
    return extractors[metric]


async def docker_fetch_metric(identifier: str, metric: str) -> dict[str, Any]:
    """Fetch a metric from Docker Hub."""
    return await _fetch_cached("docker", identifier, metric, 600, _docker_extract)
