"""Data connectors for live metric fetching."""

from __future__ import annotations

from typing import Any

from hyperweave.connectors import arxiv, github
from hyperweave.connectors.base import (
    CircuitBreaker,
    CircuitState,
    ConnectorError,
    SSRFError,
    fetch,
    validate_url,
)
from hyperweave.connectors.cache import ConnectorCache
from hyperweave.connectors.rest import (
    docker_fetch_metric,
    hf_fetch_metric,
    npm_fetch_metric,
    pypi_fetch_metric,
)

_CONNECTORS: dict[str, Any] = {
    "github": github.fetch_metric,
    "pypi": pypi_fetch_metric,
    "npm": npm_fetch_metric,
    "arxiv": arxiv.fetch_metric,
    "huggingface": hf_fetch_metric,
    "hf": hf_fetch_metric,
    "docker": docker_fetch_metric,
}


async def fetch_metric(
    provider: str,
    identifier: str,
    metric: str,
) -> dict[str, Any]:
    """Unified metric fetch -- routes to provider-specific connector."""
    connector_fn = _CONNECTORS.get(provider.lower())
    if connector_fn is None:
        raise ValueError(f"Unknown provider {provider!r}. Available: {sorted(set(_CONNECTORS) - {'hf'})}")
    result: dict[str, Any] = await connector_fn(identifier, metric)
    return result


__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "ConnectorCache",
    "ConnectorError",
    "SSRFError",
    "fetch",
    "fetch_metric",
    "validate_url",
]
