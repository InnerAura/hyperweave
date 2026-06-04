"""REST-based connectors (PyPI, npm, HuggingFace, Docker Hub, crates.io)."""

from __future__ import annotations

from typing import Any

from hyperweave import __version__
from hyperweave.connectors.base import (
    CircuitOpenError,
    ConnectorError,
    fetch_json,
)
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


async def _pypi_downloads(identifier: str) -> int:
    """Resolve a pypi package's download count.

    PRIMARY: pepy.tech v2 (``/api/v2/projects/{pkg}`` → ``total_downloads``),
    keyless and purpose-built for download badges. pypi.org's JSON API never
    populated download counts, and pypistats.org rate-limits (429) under the
    proofset's burst — so pepy is primary and pypistats last-month is the
    fallback. ``provider="pepy"`` gives pepy its own circuit breaker.

    NOTE: pepy's ``total_downloads`` is an ALL-TIME total; the pypistats
    fallback is LAST-MONTH. The value's period is therefore unlabeled — a
    download window subtitle is a tracked follow-up (it needs a layout slot).
    """
    try:
        pepy = await fetch_json(f"https://pepy.tech/api/v2/projects/{identifier}", provider="pepy")
        total = pepy.get("total_downloads")
        if isinstance(total, int | float) and not isinstance(total, bool):
            return int(total)
    except (ConnectorError, CircuitOpenError):
        pass
    # Fallback: pypistats last-month (the source pre-v0.3.12 used).
    stats = await fetch_json(
        f"https://pypistats.org/api/packages/{identifier}/recent",
        provider="pypistats",
    )
    bucket: dict[str, Any] = stats.get("data", {})
    return int(bucket.get("last_month", 0))


async def _pypi_extract(identifier: str, metric: str) -> Any:
    # pypi.org/pypi/{pkg}/json hasn't carried download counts since 2016 —
    # ``info.downloads.last_month`` returns -1 for every package. The
    # downloads metric is routed through pypistats.org, the same source
    # the official ``pypistats`` CLI uses. Provider name "pypistats"
    # gives it its own circuit-breaker so a pypistats outage cannot trip
    # the version/license/python_requires path that still hits pypi.org.
    if metric == "downloads":
        return await _pypi_downloads(identifier)

    data = await fetch_json(f"https://pypi.org/pypi/{identifier}/json", provider="pypi")
    info: dict[str, Any] = data.get("info", {})
    extractors: dict[str, Any] = {
        "version": info.get("version"),
        "license": info.get("license", "Unknown"),
        "python_requires": info.get("requires_python", "Unknown"),
    }
    if metric not in extractors:
        available = [*extractors, "downloads"]
        raise ValueError(f"Unknown PyPI metric {metric!r}. Available: {', '.join(available)}")
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
        # npm download stats live on a separate api.npmjs.org subdomain;
        # registry.npmjs.org/-/downloads/* returns 404 for all packages
        # (verified 2026-05-20). Scoped paths (@scope/name) work unencoded
        # on the api host.
        dl = await fetch_json(
            f"https://api.npmjs.org/downloads/point/last-week/{identifier}",
            provider="npm",
        )
        return dl.get("downloads", 0)
    raise ValueError(f"Unknown npm metric {metric!r}. Available: version, downloads, license")


async def npm_fetch_metric(identifier: str, metric: str) -> dict[str, Any]:
    """Fetch a metric from npm."""
    return await _fetch_cached("npm", identifier, metric, 600, _npm_extract)


# -- HuggingFace -----------------------------------------------------------


def _hf_license(data: dict[str, Any]) -> str:
    """Resolve a model's license.

    The license is NOT a top-level field — it lives in ``cardData.license``
    (verified live on ``mistralai/Mistral-7B-v0.1``). When the model card omits
    it, fall back to a ``license:<id>`` entry in ``tags``. ``"Unknown"`` if
    neither source carries it.
    """
    card = data.get("cardData")
    if isinstance(card, dict):
        card_license = card.get("license")
        if card_license:
            return str(card_license)
    for tag in data.get("tags", []):
        if isinstance(tag, str) and tag.startswith("license:"):
            return tag.split(":", 1)[1]
    return "Unknown"


def _hf_gated(data: dict[str, Any]) -> str:
    """Stringify ``gated``: bool ``false`` OR string ``"auto"``/``"manual"``.

    Booleans render lowercase (``"false"``/``"true"``) so the badge reads
    cleanly; the access-mode strings pass through unchanged.
    """
    raw = data.get("gated")
    if isinstance(raw, bool):
        return "true" if raw else "false"
    return str(raw) if raw is not None else "false"


async def _hf_extract(identifier: str, metric: str) -> Any:
    _require_slash(identifier, "HuggingFace")
    data = await fetch_json(f"https://huggingface.co/api/models/{identifier}", provider="huggingface")
    extractors: dict[str, Any] = {
        "downloads": data.get("downloads", 0),
        "likes": data.get("likes", 0),
        "tags": data.get("tags", []),
        "pipeline_tag": data.get("pipeline_tag", "unknown"),
        "library_name": data.get("library_name", "unknown"),
        # v0.3.12 audit-surfaced fields (casing verified live):
        "last_modified": data.get("lastModified", "unknown"),
        "gated": _hf_gated(data),
        "license": _hf_license(data),
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


# -- crates.io -------------------------------------------------------------


async def _crates_extract(identifier: str, metric: str) -> Any:
    # crates.io rejects requests without a descriptive User-Agent (returns
    # 403). fetch_json merges caller headers over its defaults, so this UA
    # overrides the generic one for the crates host only.
    headers = {"User-Agent": f"HyperWeave/{__version__} (https://github.com/InnerAura/hyperweave)"}
    data = await fetch_json(
        f"https://crates.io/api/v1/crates/{identifier}",
        provider="crates",
        headers=headers,
    )
    crate: dict[str, Any] = data.get("crate", {})
    if metric == "version":
        # Prefer the highest stable release; pre-1.0 / pre-release-only crates
        # have no max_stable_version, so fall back to newest_version.
        return crate.get("max_stable_version") or crate.get("newest_version") or "unknown"
    if metric == "downloads":
        return int(crate.get("downloads", 0) or 0)
    if metric == "recent_downloads":
        return int(crate.get("recent_downloads", 0) or 0)
    if metric == "license":
        versions = data.get("versions", [])
        if versions and isinstance(versions[0], dict):
            return versions[0].get("license") or "Unknown"
        return "Unknown"
    raise ValueError(f"Unknown crates metric {metric!r}. Available: version, downloads, recent_downloads, license")


async def crates_fetch_metric(identifier: str, metric: str) -> dict[str, Any]:
    """Fetch a metric from crates.io."""
    return await _fetch_cached("crates", identifier, metric, 600, _crates_extract)
