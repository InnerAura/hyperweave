"""Connector base: SSRF protection, circuit breaker, HTTP fetching."""

from __future__ import annotations

import contextlib
import os
import time
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

import httpx

from hyperweave import __version__

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
        # PyPI's JSON API stopped exposing download counts in 2016, so the
        # downloads metric routes through pypistats.org (the source the
        # official `pypistats` CLI uses). Listed separately so version /
        # license stay on pypi.org and a pypistats outage doesn't trip
        # the breaker that fronts pypi.org.
        "pypistats.org",
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

# Three breaker-isolated provider names. The literal ``"github"`` is no longer
# accepted (kept off the list intentionally) — bare references are caught by
# the grep gate in CLAUDE.md. See connectors/github.py for the full rationale.
_GITHUB_PROVIDERS: frozenset[str] = frozenset({"github-core", "github-search", "github-graphql"})

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


# Singleton AsyncClient — replaces the per-request httpx.AsyncClient construction
# that was paying a fresh TCP+TLS handshake (~150-300ms) on every upstream call.
# With HTTP/2 multiplexing, the marquee fan-out (5 tokens / 3 providers) reuses
# already-established connections to api.github.com / pypi.org / pypistats.org /
# hub.docker.com instead of opening 5 fresh ones in parallel.
#
# Lifecycle:
#   - FastAPI: opened in lifespan startup (warmup compose primes the pool),
#     closed in lifespan shutdown via close_client().
#   - CLI: opened lazily on first asyncio.run(fetch_metric(...)) call, reaped
#     at process exit (each CLI invocation is a fresh process).
#   - Tests: tests/conftest.py autouse fixture calls close_client() after every
#     test so each test gets a fresh client bound to its own event loop
#     (pytest-asyncio asyncio_mode='auto' creates a new loop per test).
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """Return the singleton AsyncClient, creating it lazily if needed.

    Re-creates if the previous client was closed (test fixtures do this between
    tests to rebind the client to each test's event loop). Same code path
    serves FastAPI (lifespan-opened), CLI (lazy-opened), and tests (autouse-
    fixture-recreated).
    """
    global _client
    if _client is None or _client.is_closed:
        timeout = httpx.Timeout(
            connect=CONNECT_TIMEOUT,
            read=TOTAL_TIMEOUT,
            write=TOTAL_TIMEOUT,
            pool=TOTAL_TIMEOUT,
        )
        _client = httpx.AsyncClient(
            http2=True,
            timeout=timeout,
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=40,
                keepalive_expiry=30.0,
            ),
        )
    return _client


async def close_client() -> None:
    """Close the singleton AsyncClient and reset the module-level reference.

    Called by FastAPI lifespan shutdown so the client cleanly releases its
    connections, and by tests/conftest.py autouse fixture between tests so
    the next test gets a fresh client on its own event loop.

    Cross-loop tolerance: if a sync test ran ``asyncio.run(fetch_metric(...))``
    internally, the client was bound to that nested loop -- which is closed
    by the time pytest-asyncio runs this fixture's teardown on a different
    loop. ``aclose()`` would then raise ``RuntimeError: Event loop is closed``.
    Catch and drop the reference; the OS reaps the sockets at process exit
    and the next ``get_client()`` call rebinds to a live loop.
    """
    global _client
    if _client is not None and not _client.is_closed:
        # Client may be bound to a different (now-closed) event loop -- e.g.
        # a sync test that ran asyncio.run() internally. Suppress and drop
        # the reference; OS reaps the sockets at process exit.
        with contextlib.suppress(RuntimeError):
            await _client.aclose()
    _client = None


def pin_github_token() -> str | None:
    """Grab one GitHub token NOW for use across multiple correlated requests.

    Token rotation via :func:`_get_github_token` advances the global index on
    every call, so successive HTTP requests within a single logical operation
    (e.g. ``/repos`` + N ``/stargazers?page=X``) land on different tokens and
    can pick up data inconsistencies if any one token's response disagrees
    (different cache age, different scope, or any per-token GitHub edge state).
    Pin one token at the start of the operation, pass it explicitly to every
    sub-call via ``fetch(..., auth_token=pinned)``, and the entire operation
    sees a consistent view. Token rotation then happens BETWEEN logical
    operations, not within them — which is the intent.

    Returns ``None`` when ``HW_GITHUB_TOKENS`` is unset (caller should fall
    back to whatever rate-limit-free behavior the unauth path provides).
    """
    return _get_github_token()


async def fetch(
    url: str,
    *,
    provider: str = "generic",
    headers: dict[str, str] | None = None,
    auth_token: str | None = None,
) -> httpx.Response:
    """Fetch *url* with SSRF validation, circuit breaker, and timeouts.

    ``auth_token`` (optional): when provided AND ``provider`` is a GitHub
    provider, use this exact token for the Authorization header instead of
    rotating via :func:`_get_github_token`. Lets callers pin one token across
    a multi-request logical operation — see :func:`pin_github_token` for the
    rationale and :func:`hyperweave.connectors.github.fetch_stargazer_history`
    for the canonical use site.
    """
    validate_url(url)

    breaker = get_breaker(provider)
    if not breaker.allow_request():
        raise CircuitOpenError(
            f"Circuit breaker open for provider {provider!r}. Retry after {breaker.recovery_timeout}s."
        )

    merged_headers: dict[str, str] = {
        "User-Agent": f"HyperWeave/{__version__} (https://hyperweave.app)",
        "Accept": "application/json",
    }
    if headers:
        merged_headers.update(headers)

    # GitHub token injection. Provider name is also the breaker key, so we
    # split into three failure domains (core REST / search REST / GraphQL)
    # to keep search-API rate limit 403s from tripping badge or chart
    # endpoints. See connectors/github.py for the rename rationale.
    # Pinned token (caller-provided) wins over rotation so multi-request
    # logical operations see a consistent token view.
    if provider in _GITHUB_PROVIDERS:
        token = auth_token if auth_token is not None else _get_github_token()
        if token:
            merged_headers["Authorization"] = f"Bearer {token}"

    try:
        client = get_client()
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
    auth_token: str | None = None,
) -> Any:
    """Fetch *url* and return parsed JSON.

    See :func:`fetch` for the ``auth_token`` parameter — same semantics.
    """
    response = await fetch(url, provider=provider, headers=headers, auth_token=auth_token)
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


# GraphQL POST

_GITHUB_GRAPHQL_URL: str = "https://api.github.com/graphql"


async def fetch_graphql(
    query: str,
    variables: dict[str, Any] | None = None,
    *,
    provider: str = "github-graphql",
    url: str = _GITHUB_GRAPHQL_URL,
    auth_token: str | None = None,
) -> dict[str, Any]:
    """POST a GraphQL query and return the parsed JSON response.

    Mirrors :func:`fetch_json`'s contract (SSRF validation, per-provider
    circuit breaker, timeouts, GitHub Bearer-token injection) but speaks
    POST with a JSON body. The single GraphQL endpoint for GitHub is
    baked into the default URL so callers don't have to remember it.

    GraphQL always returns HTTP 200 with a ``data`` field and an optional
    ``errors`` list — HTTP-level failures trip the breaker, but query-level
    errors (invalid field, missing perms) come through as response body
    and are the caller's responsibility to inspect.

    See :func:`fetch` for the ``auth_token`` parameter — same semantics.
    """
    validate_url(url)

    breaker = get_breaker(provider)
    if not breaker.allow_request():
        raise CircuitOpenError(
            f"Circuit breaker open for provider {provider!r}. Retry after {breaker.recovery_timeout}s."
        )

    merged_headers: dict[str, str] = {
        "User-Agent": f"HyperWeave/{__version__} (https://hyperweave.app)",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if provider in _GITHUB_PROVIDERS:
        token = auth_token if auth_token is not None else _get_github_token()
        if token:
            merged_headers["Authorization"] = f"Bearer {token}"

    body: dict[str, Any] = {"query": query, "variables": variables or {}}

    try:
        client = get_client()
        response = await client.post(url, headers=merged_headers, json=body)
        response.raise_for_status()
        breaker.record_success()
        data: dict[str, Any] = response.json()
        return data
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        breaker.record_failure()
        raise ConnectorError(f"GraphQL fetch failed for {provider!r}: {exc}") from exc
