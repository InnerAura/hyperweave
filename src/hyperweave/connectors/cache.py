"""Simple in-memory TTL cache for connector responses."""

from __future__ import annotations

import time
from typing import Any

PROVIDER_TTLS: dict[str, int] = {
    "github": 300,
    "pypi": 600,
    "npm": 600,
    "arxiv": 1800,
    "huggingface": 600,
    "docker": 600,
}

DEFAULT_TTL: int = 600


class ConnectorCache:
    """Thread-safe in-memory TTL cache."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        """Return cached value for *key*, or None if missing/expired."""
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if time.monotonic() > expiry:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Store *value* under *key* with a TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_TTL
        self._store[key] = (value, time.monotonic() + ttl)

    def clear(self) -> None:
        """Remove all entries."""
        self._store.clear()

    @property
    def size(self) -> int:
        """Number of entries (including potentially expired ones)."""
        return len(self._store)

    def ttl_for_provider(self, provider: str) -> int:
        """Return the configured TTL for *provider*."""
        return PROVIDER_TTLS.get(provider, DEFAULT_TTL)


# Module-level singleton
_cache = ConnectorCache()


def get_cache() -> ConnectorCache:
    """Return the module-level cache singleton."""
    return _cache
