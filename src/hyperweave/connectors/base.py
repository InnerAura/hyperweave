"""Connector base: SSRF protection, circuit breaker, HTTP fetching."""

from __future__ import annotations

import os
import time
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

import httpx

# SSRF Protection

ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "api.github.com",
        # Session 2A+2B: contribution calendar HTML scraping (precedent:
        # github-readme-streak-stats, ghchart.rshah.org, github-profile-summary-cards
        # — all public OSS tools with thousands of stars scrape the same page).
        # Username path segments are regex-sanitized in the scraper before
        # interpolation; no arbitrary path injection is possible.
        "github.com",
        "pypi.org",
        "registry.npmjs.org",
        "export.arxiv.org",
        "huggingface.co",
        "hub.docker.com",
    }
)


class SSRFError(Exception):
    """Raised when a request targets a non-allowlisted domain."""


class ConnectorError(Exception):
    """Raised when a connector fetch fails."""


class CircuitOpenError(ConnectorError):
    """Raised when the circuit breaker is open."""


def validate_url(url: str) -> str:
    """Validate that *url* targets an allowlisted host."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host not in ALLOWED_HOSTS:
        raise SSRFError(f"Host {host!r} is not in the SSRF allowlist. Allowed: {sorted(ALLOWED_HOSTS)}")
    return url


# Circuit Breaker


class CircuitState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class CircuitBreaker:
    """Per-provider circuit breaker."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count: int = 0
        self._state: CircuitState = CircuitState.CLOSED
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        """Current state, with automatic open -> half-open transition."""
        if self._state is CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def record_success(self) -> None:
        """Record a successful call -- resets the breaker."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed call -- may trip the breaker."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN

    def allow_request(self) -> bool:
        """Return True if a request is allowed through."""
        current = self.state
        if current is CircuitState.CLOSED:
            return True
        return current is CircuitState.HALF_OPEN


# GitHub Token Rotation

_token_index: int = 0


def _get_github_token() -> str | None:
    global _token_index
    tokens_env = os.environ.get("HW_GITHUB_TOKENS", "")
    if tokens_env:
        tokens = [t.strip() for t in tokens_env.split(",") if t.strip()]
        if tokens:
            token = tokens[_token_index % len(tokens)]
            _token_index += 1
            return token
    return os.environ.get("GITHUB_TOKEN")


# Shared Circuit Breakers (one per provider)

_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(provider: str) -> CircuitBreaker:
    """Return the circuit breaker for *provider*, creating if needed."""
    if provider not in _breakers:
        _breakers[provider] = CircuitBreaker()
    return _breakers[provider]


def reset_breakers() -> None:
    """Reset all circuit breakers. For testing."""
    _breakers.clear()


# Base HTTP Fetch

CONNECT_TIMEOUT: float = 10.0
TOTAL_TIMEOUT: float = 15.0


async def fetch(
    url: str,
    *,
    provider: str = "generic",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Fetch *url* with SSRF validation, circuit breaker, and timeouts."""
    validate_url(url)

    breaker = get_breaker(provider)
    if not breaker.allow_request():
        raise CircuitOpenError(
            f"Circuit breaker open for provider {provider!r}. Retry after {breaker.recovery_timeout}s."
        )

    merged_headers: dict[str, str] = {
        "User-Agent": "HyperWeave/0.1.0 (https://hyperweave.app)",
        "Accept": "application/json",
    }
    if headers:
        merged_headers.update(headers)

    # GitHub token injection
    if provider == "github":
        token = _get_github_token()
        if token:
            merged_headers["Authorization"] = f"Bearer {token}"

    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT,
        read=TOTAL_TIMEOUT,
        write=TOTAL_TIMEOUT,
        pool=TOTAL_TIMEOUT,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=merged_headers)
            response.raise_for_status()
            breaker.record_success()
            return response
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        breaker.record_failure()
        raise ConnectorError(f"Fetch failed for {provider!r}: {exc}") from exc


async def fetch_json(
    url: str,
    *,
    provider: str = "generic",
    headers: dict[str, str] | None = None,
) -> Any:
    """Fetch *url* and return parsed JSON."""
    response = await fetch(url, provider=provider, headers=headers)
    return response.json()


async def fetch_text(
    url: str,
    *,
    provider: str = "generic",
    headers: dict[str, str] | None = None,
) -> str:
    """Fetch *url* and return raw text."""
    merged = {"Accept": "text/html"}
    if headers:
        merged.update(headers)
    response = await fetch(url, provider=provider, headers=merged)
    return response.text
