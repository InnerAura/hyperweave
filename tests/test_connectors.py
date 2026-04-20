"""Tests for the connectors module.

Tests SSRF protection, circuit breaker state machine, response
parsing for all six providers, and the TTL cache.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from hyperweave.connectors.base import (
    ALLOWED_HOSTS,
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    ConnectorError,
    SSRFError,
    fetch,
    get_breaker,
    reset_breakers,
    validate_url,
)
from hyperweave.connectors.cache import ConnectorCache, get_cache

# =========================================================================
# SSRF Protection
# =========================================================================


class TestSSRFProtection:
    """Verify the SSRF allowlist rejects non-approved domains."""

    def test_allowed_hosts_are_accepted(self) -> None:
        for host in ALLOWED_HOSTS:
            url = f"https://{host}/some/path"
            assert validate_url(url) == url

    def test_private_ip_rejected(self) -> None:
        with pytest.raises(SSRFError, match="not in the SSRF allowlist"):
            validate_url("http://127.0.0.1/admin")

    def test_localhost_rejected(self) -> None:
        with pytest.raises(SSRFError, match="not in the SSRF allowlist"):
            validate_url("http://localhost:8080/secret")

    def test_internal_network_rejected(self) -> None:
        with pytest.raises(SSRFError, match="not in the SSRF allowlist"):
            validate_url("http://192.168.1.1/api")

    def test_unknown_host_rejected(self) -> None:
        with pytest.raises(SSRFError, match="not in the SSRF allowlist"):
            validate_url("https://evil.example.com/steal-data")

    def test_empty_url_rejected(self) -> None:
        with pytest.raises(SSRFError):
            validate_url("")

    def test_subdomain_not_allowed(self) -> None:
        """Subdomains of allowed hosts should NOT pass."""
        with pytest.raises(SSRFError):
            validate_url("https://evil.api.github.com/repos")

    def test_allowed_host_list_is_frozen(self) -> None:
        assert isinstance(ALLOWED_HOSTS, frozenset)


# =========================================================================
# Circuit Breaker
# =========================================================================


class TestCircuitBreaker:
    """Verify circuit breaker state transitions."""

    def test_starts_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.state is CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_stays_closed_under_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state is CircuitState.CLOSED

    def test_opens_at_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(5):
            cb.record_failure()
        assert cb.state is CircuitState.OPEN
        assert cb.allow_request() is False

    def test_half_open_after_recovery(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state is CircuitState.OPEN

        # Wait for recovery
        time.sleep(0.15)
        assert cb.state is CircuitState.HALF_OPEN
        assert cb.allow_request() is True

    def test_success_resets_to_closed(self) -> None:
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state is CircuitState.OPEN

        # Simulate half-open + success
        cb._state = CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state is CircuitState.CLOSED

    def test_success_resets_failure_count(self) -> None:
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(3):
            cb.record_failure()
        cb.record_success()
        # Should be reset -- 4 more failures needed to trip
        for _ in range(4):
            cb.record_failure()
        assert cb.state is CircuitState.CLOSED


# =========================================================================
# TTL Cache
# =========================================================================


class TestConnectorCache:
    """Verify the in-memory TTL cache."""

    def test_set_and_get(self) -> None:
        cache = ConnectorCache()
        cache.set("key", "value", ttl_seconds=60)
        assert cache.get("key") == "value"

    def test_miss_returns_none(self) -> None:
        cache = ConnectorCache()
        assert cache.get("nonexistent") is None

    def test_expired_entry_returns_none(self) -> None:
        cache = ConnectorCache()
        cache.set("key", "value", ttl_seconds=0)
        time.sleep(0.01)
        assert cache.get("key") is None

    def test_clear(self) -> None:
        cache = ConnectorCache()
        cache.set("a", 1, ttl_seconds=60)
        cache.set("b", 2, ttl_seconds=60)
        assert cache.size == 2
        cache.clear()
        assert cache.size == 0

    def test_provider_ttls(self) -> None:
        cache = ConnectorCache()
        assert cache.ttl_for_provider("github") == 300
        assert cache.ttl_for_provider("pypi") == 600
        assert cache.ttl_for_provider("arxiv") == 1800
        assert cache.ttl_for_provider("unknown") == 600  # default


# =========================================================================
# Base Fetch (mocked HTTP)
# =========================================================================


class TestFetch:
    """Verify the base fetch function with mocked HTTP."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()

    @pytest.mark.asyncio
    async def test_ssrf_rejection_in_fetch(self) -> None:
        with pytest.raises(SSRFError):
            await fetch("http://evil.com/api")

    @pytest.mark.asyncio
    async def test_circuit_open_raises(self) -> None:
        breaker = get_breaker("test-provider")
        for _ in range(5):
            breaker.record_failure()

        with pytest.raises(CircuitOpenError):
            await fetch(
                "https://api.github.com/repos/test",
                provider="test-provider",
            )

    @pytest.mark.asyncio
    async def test_successful_fetch(self) -> None:
        mock_response = httpx.Response(
            200,
            json={"stargazers_count": 1234},
            request=httpx.Request("GET", "https://api.github.com/repos/test/test"),
        )

        with patch("hyperweave.connectors.base.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.get.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = instance

            response = await fetch(
                "https://api.github.com/repos/test/test",
                provider="github",
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_failed_fetch_trips_breaker(self) -> None:
        with patch("hyperweave.connectors.base.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.get.side_effect = httpx.RequestError("connection refused")
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = instance

            breaker = get_breaker("fail-provider")
            assert breaker.state is CircuitState.CLOSED

            with pytest.raises(ConnectorError):
                await fetch(
                    "https://api.github.com/repos/test/test",
                    provider="fail-provider",
                )

            assert breaker._failure_count == 1


# =========================================================================
# GitHub Provider
# =========================================================================


class TestGitHubProvider:
    """Test GitHub connector response parsing."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    @pytest.mark.asyncio
    async def test_stars_metric(self) -> None:
        mock_data = {
            "stargazers_count": 2900,
            "forks_count": 278,
            "subscribers_count": 42,
            "open_issues_count": 15,
            "license": {"spdx_id": "MIT", "name": "MIT License"},
            "language": "Python",
        }

        with patch(
            "hyperweave.connectors.github.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors.github import fetch_metric

            result = await fetch_metric("eli64s/readme-ai", "stars")
            assert result["provider"] == "github"
            assert result["value"] == 2900
            assert result["metric"] == "stars"

    @pytest.mark.asyncio
    async def test_license_metric_extracts_spdx(self) -> None:
        mock_data = {
            "license": {"spdx_id": "MIT", "name": "MIT License"},
        }

        with patch(
            "hyperweave.connectors.github.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors.github import fetch_metric

            result = await fetch_metric("eli64s/readme-ai", "license")
            assert result["value"] == "MIT"

    @pytest.mark.asyncio
    async def test_invalid_metric_raises(self) -> None:
        with patch(
            "hyperweave.connectors.github.fetch_json",
            new_callable=AsyncMock,
            return_value={},
        ):
            from hyperweave.connectors.github import fetch_metric

            with pytest.raises(ValueError, match="Unknown GitHub metric"):
                await fetch_metric("eli64s/readme-ai", "nonexistent")

    @pytest.mark.asyncio
    async def test_invalid_identifier_raises(self) -> None:
        from hyperweave.connectors.github import fetch_metric

        with pytest.raises(ValueError, match="owner/repo"):
            await fetch_metric("invalid-no-slash", "stars")


# =========================================================================
# PyPI Provider
# =========================================================================


class TestPyPIProvider:
    """Test PyPI connector response parsing."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    @pytest.mark.asyncio
    async def test_version_metric(self) -> None:
        mock_data = {
            "info": {
                "version": "0.6.3",
                "license": "MIT",
                "requires_python": ">=3.9",
                "downloads": {"last_month": -1},
            }
        }

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors.rest import pypi_fetch_metric as fetch_metric

            result = await fetch_metric("readmeai", "version")
            assert result["value"] == "0.6.3"
            assert result["provider"] == "pypi"

    @pytest.mark.asyncio
    async def test_python_requires_metric(self) -> None:
        mock_data = {
            "info": {"requires_python": ">=3.9"},
        }

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors.rest import pypi_fetch_metric as fetch_metric

            result = await fetch_metric("readmeai", "python_requires")
            assert result["value"] == ">=3.9"


# =========================================================================
# npm Provider
# =========================================================================


class TestNpmProvider:
    """Test npm connector response parsing."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    @pytest.mark.asyncio
    async def test_version_metric(self) -> None:
        mock_data = {
            "dist-tags": {"latest": "4.18.2"},
            "license": "MIT",
        }

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors.rest import npm_fetch_metric as fetch_metric

            result = await fetch_metric("express", "version")
            assert result["value"] == "4.18.2"


# =========================================================================
# arXiv Provider
# =========================================================================


class TestArxivProvider:
    """Test arXiv connector XML parsing."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    SAMPLE_ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Attention Is All You Need</title>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <published>2023-01-02T00:00:00Z</published>
    <category term="cs.CL"/>
    <category term="cs.AI"/>
    <summary>We propose a new architecture...</summary>
  </entry>
</feed>"""

    @pytest.mark.asyncio
    async def test_title_metric(self) -> None:
        with patch(
            "hyperweave.connectors.arxiv.fetch_text",
            new_callable=AsyncMock,
            return_value=self.SAMPLE_ATOM_XML,
        ):
            from hyperweave.connectors.arxiv import fetch_metric

            result = await fetch_metric("2301.00774", "title")
            assert result["value"] == "Attention Is All You Need"

    @pytest.mark.asyncio
    async def test_authors_metric(self) -> None:
        with patch(
            "hyperweave.connectors.arxiv.fetch_text",
            new_callable=AsyncMock,
            return_value=self.SAMPLE_ATOM_XML,
        ):
            from hyperweave.connectors.arxiv import fetch_metric

            result = await fetch_metric("2301.00774", "authors")
            assert result["value"] == ["Ashish Vaswani", "Noam Shazeer"]

    @pytest.mark.asyncio
    async def test_categories_metric(self) -> None:
        with patch(
            "hyperweave.connectors.arxiv.fetch_text",
            new_callable=AsyncMock,
            return_value=self.SAMPLE_ATOM_XML,
        ):
            from hyperweave.connectors.arxiv import fetch_metric

            result = await fetch_metric("2301.00774", "categories")
            assert result["value"] == ["cs.CL", "cs.AI"]

    @pytest.mark.asyncio
    async def test_summary_metric(self) -> None:
        with patch(
            "hyperweave.connectors.arxiv.fetch_text",
            new_callable=AsyncMock,
            return_value=self.SAMPLE_ATOM_XML,
        ):
            from hyperweave.connectors.arxiv import fetch_metric

            result = await fetch_metric("2301.00774", "summary")
            assert result["value"] == "We propose a new architecture..."
            assert result["ttl"] == 1800

    @pytest.mark.asyncio
    async def test_published_metric(self) -> None:
        with patch(
            "hyperweave.connectors.arxiv.fetch_text",
            new_callable=AsyncMock,
            return_value=self.SAMPLE_ATOM_XML,
        ):
            from hyperweave.connectors.arxiv import fetch_metric

            result = await fetch_metric("2301.00774", "published")
            assert result["value"] == "2023-01-02T00:00:00Z"

    @pytest.mark.asyncio
    async def test_invalid_metric_raises(self) -> None:
        with patch(
            "hyperweave.connectors.arxiv.fetch_text",
            new_callable=AsyncMock,
            return_value=self.SAMPLE_ATOM_XML,
        ):
            from hyperweave.connectors.arxiv import fetch_metric

            with pytest.raises(ValueError, match="Unknown arXiv metric"):
                await fetch_metric("2301.00774", "nonexistent")


# =========================================================================
# HuggingFace Provider
# =========================================================================


class TestHuggingFaceProvider:
    """Test HuggingFace connector response parsing."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    @pytest.mark.asyncio
    async def test_downloads_metric(self) -> None:
        mock_data = {
            "downloads": 1_500_000,
            "likes": 3200,
            "tags": ["pytorch", "llama"],
            "pipeline_tag": "text-generation",
        }

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors.rest import hf_fetch_metric as fetch_metric

            result = await fetch_metric("meta-llama/Llama-2-7b", "downloads")
            assert result["value"] == 1_500_000

    @pytest.mark.asyncio
    async def test_tags_metric(self) -> None:
        mock_data = {"tags": ["pytorch", "llama"]}

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors.rest import hf_fetch_metric as fetch_metric

            result = await fetch_metric("meta-llama/Llama-2-7b", "tags")
            assert result["value"] == ["pytorch", "llama"]

    @pytest.mark.asyncio
    async def test_invalid_identifier_raises(self) -> None:
        from hyperweave.connectors.rest import hf_fetch_metric as fetch_metric

        with pytest.raises(ValueError, match="org/model"):
            await fetch_metric("no-slash", "downloads")


# =========================================================================
# Docker Provider
# =========================================================================


class TestDockerProvider:
    """Test Docker Hub connector response parsing."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    @pytest.mark.asyncio
    async def test_pull_count_metric(self) -> None:
        mock_data = {
            "pull_count": 50000,
            "star_count": 12,
            "last_updated": "2026-03-15T10:00:00Z",
        }

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors.rest import docker_fetch_metric as fetch_metric

            result = await fetch_metric("zeroxeli/readme-ai", "pull_count")
            assert result["value"] == 50000
            assert result["provider"] == "docker"

    @pytest.mark.asyncio
    async def test_star_count_metric(self) -> None:
        mock_data = {
            "pull_count": 50000,
            "star_count": 12,
            "last_updated": "2026-03-15T10:00:00Z",
        }

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors.rest import docker_fetch_metric as fetch_metric

            result = await fetch_metric("library/nginx", "star_count")
            assert result["value"] == 12

    @pytest.mark.asyncio
    async def test_last_updated_metric(self) -> None:
        mock_data = {
            "pull_count": 50000,
            "star_count": 12,
            "last_updated": "2026-03-15T10:00:00Z",
        }

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors.rest import docker_fetch_metric as fetch_metric

            result = await fetch_metric("library/nginx", "last_updated")
            assert result["value"] == "2026-03-15T10:00:00Z"

    @pytest.mark.asyncio
    async def test_invalid_identifier_raises(self) -> None:
        from hyperweave.connectors.rest import docker_fetch_metric as fetch_metric

        with pytest.raises(ValueError, match="namespace/repo"):
            await fetch_metric("no-slash", "pull_count")

    @pytest.mark.asyncio
    async def test_invalid_metric_raises(self) -> None:
        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value={},
        ):
            from hyperweave.connectors.rest import docker_fetch_metric as fetch_metric

            with pytest.raises(ValueError, match="Unknown Docker metric"):
                await fetch_metric("library/nginx", "nonexistent")


# =========================================================================
# HuggingFace: library_name metric
# =========================================================================


class TestHuggingFaceLibraryName:
    """Test HuggingFace library_name metric."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    @pytest.mark.asyncio
    async def test_library_name_metric(self) -> None:
        mock_data = {"library_name": "transformers"}

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors.rest import hf_fetch_metric as fetch_metric

            result = await fetch_metric("microsoft/DialoGPT-medium", "library_name")
            assert result["value"] == "transformers"
            assert result["provider"] == "huggingface"


# =========================================================================
# Unified Dispatcher
# =========================================================================


class TestUnifiedDispatcher:
    """Test the unified fetch_metric dispatcher in connectors/__init__.py."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    @pytest.mark.asyncio
    async def test_routes_to_github(self) -> None:
        mock_data = {
            "stargazers_count": 5000,
            "forks_count": 100,
            "subscribers_count": 20,
            "open_issues_count": 5,
            "license": None,
            "language": "Python",
        }

        with patch(
            "hyperweave.connectors.github.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors import fetch_metric

            result = await fetch_metric("github", "eli64s/readme-ai", "stars")
            assert result["provider"] == "github"
            assert result["value"] == 5000

    @pytest.mark.asyncio
    async def test_routes_to_pypi(self) -> None:
        mock_data = {"info": {"version": "1.0.0"}}

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors import fetch_metric

            result = await fetch_metric("pypi", "readmeai", "version")
            assert result["provider"] == "pypi"
            assert result["value"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_routes_to_npm(self) -> None:
        mock_data = {"dist-tags": {"latest": "5.0.0"}}

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors import fetch_metric

            result = await fetch_metric("npm", "express", "version")
            assert result["provider"] == "npm"
            assert result["value"] == "5.0.0"

    @pytest.mark.asyncio
    async def test_routes_to_arxiv(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Test Paper</title>
    <published>2023-10-01T00:00:00Z</published>
    <summary>Abstract text</summary>
  </entry>
</feed>"""

        with patch(
            "hyperweave.connectors.arxiv.fetch_text",
            new_callable=AsyncMock,
            return_value=xml,
        ):
            from hyperweave.connectors import fetch_metric

            result = await fetch_metric("arxiv", "2310.06825", "title")
            assert result["provider"] == "arxiv"
            assert result["value"] == "Test Paper"

    @pytest.mark.asyncio
    async def test_routes_to_huggingface(self) -> None:
        mock_data = {"downloads": 42000, "likes": 100}

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors import fetch_metric

            result = await fetch_metric("huggingface", "microsoft/DialoGPT-medium", "downloads")
            assert result["provider"] == "huggingface"
            assert result["value"] == 42000

    @pytest.mark.asyncio
    async def test_hf_alias(self) -> None:
        mock_data = {"downloads": 42000}

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors import fetch_metric

            result = await fetch_metric("hf", "microsoft/DialoGPT-medium", "downloads")
            assert result["provider"] == "huggingface"

    @pytest.mark.asyncio
    async def test_routes_to_docker(self) -> None:
        mock_data = {"pull_count": 99000, "star_count": 50, "last_updated": "2026-03-01T00:00:00Z"}

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors import fetch_metric

            result = await fetch_metric("docker", "library/nginx", "pull_count")
            assert result["provider"] == "docker"
            assert result["value"] == 99000

    @pytest.mark.asyncio
    async def test_unknown_provider_raises(self) -> None:
        from hyperweave.connectors import fetch_metric

        with pytest.raises(ValueError, match="Unknown provider"):
            await fetch_metric("gitlab", "foo/bar", "stars")

    @pytest.mark.asyncio
    async def test_case_insensitive_provider(self) -> None:
        mock_data = {"info": {"version": "2.0.0"}}

        with patch(
            "hyperweave.connectors.rest.fetch_json",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            from hyperweave.connectors import fetch_metric

            result = await fetch_metric("PyPI", "readmeai", "version")
            assert result["provider"] == "pypi"

    @pytest.mark.asyncio
    async def test_invalid_metric_propagates(self) -> None:
        with patch(
            "hyperweave.connectors.github.fetch_json",
            new_callable=AsyncMock,
            return_value={},
        ):
            from hyperweave.connectors import fetch_metric

            with pytest.raises(ValueError, match="Unknown GitHub metric"):
                await fetch_metric("github", "eli64s/readme-ai", "bogus_metric")


# =========================================================================
# GitHub Token Pool Rotation (§1.1)
# =========================================================================


class TestGitHubTokenPool:
    """Verify HW_GITHUB_TOKENS round-robin rotation and fallback chain.

    The pool is read by ``_get_github_token`` in ``connectors.base``; a
    module-level ``_token_index`` advances on each call so six calls across
    a 3-token pool return the pool twice in order.
    """

    def setup_method(self) -> None:
        from hyperweave.connectors import base

        base._token_index = 0

    def test_rotates_through_pool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HW_GITHUB_TOKENS", "tok_a,tok_b,tok_c")
        from hyperweave.connectors.base import _get_github_token

        assert [_get_github_token() for _ in range(6)] == [
            "tok_a",
            "tok_b",
            "tok_c",
            "tok_a",
            "tok_b",
            "tok_c",
        ]

    def test_strips_whitespace_and_empty_entries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HW_GITHUB_TOKENS", " tok_a , ,tok_b,")
        from hyperweave.connectors.base import _get_github_token

        assert _get_github_token() == "tok_a"
        assert _get_github_token() == "tok_b"

    def test_falls_back_to_single_github_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HW_GITHUB_TOKENS", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "tok_solo")
        from hyperweave.connectors.base import _get_github_token

        assert _get_github_token() == "tok_solo"

    def test_returns_none_when_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HW_GITHUB_TOKENS", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        from hyperweave.connectors.base import _get_github_token

        assert _get_github_token() is None


# =========================================================================
# Stargazer History Pagination (§1.4)
# =========================================================================


class TestStargazerPagination:
    """Verify the 400-page clamp and current-UTC now-point."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    @pytest.mark.asyncio
    async def test_mega_repo_uses_page_clamp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """357k-star repo → total_pages≈3570 but sampling clamps at 400."""
        captured_pages: list[int] = []

        async def fake_fetch_json(url: str, **_kw: Any) -> Any:
            if "/stargazers" in url:
                # Extract the page query parameter to assert the clamp
                page = int(url.split("page=")[-1])
                captured_pages.append(page)
                # Return an ancient starred_at so we can verify the now-point
                # isn't sourced from fetched timestamps.
                return [{"starred_at": "2015-01-01T00:00:00Z"}]
            # Repo metadata request
            return {"stargazers_count": 357_000}

        monkeypatch.setattr("hyperweave.connectors.github.fetch_json", fake_fetch_json)
        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("torvalds", "linux")

        # No page > 400 even though total_stars / 100 = 3570.
        assert captured_pages, "expected at least one stargazer fetch"
        assert max(captured_pages) <= 400

        # Now-point uses current UTC, not the 2015 mock date.
        assert result["points"], "expected at least one point"
        now_year = str(datetime.now(UTC).year)
        assert result["points"][-1]["date"].startswith(now_year)
        # Real star total preserved on the now-point.
        assert result["points"][-1]["count"] == 357_000

    @pytest.mark.asyncio
    async def test_small_repo_samples_full_range(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """500-star repo: total_pages=5, clamp doesn't truncate sampling."""
        captured_pages: list[int] = []

        async def fake_fetch_json(url: str, **_kw: Any) -> Any:
            if "/stargazers" in url:
                page = int(url.split("page=")[-1])
                captured_pages.append(page)
                return [{"starred_at": "2024-06-01T00:00:00Z"}]
            return {"stargazers_count": 500}

        monkeypatch.setattr("hyperweave.connectors.github.fetch_json", fake_fetch_json)
        from hyperweave.connectors.github import fetch_stargazer_history

        await fetch_stargazer_history("small", "repo")

        # All requested pages within the actual total-pages range (5).
        assert captured_pages, "expected at least one stargazer fetch"
        assert max(captured_pages) <= 5


# =========================================================================
# fetch_graphql (POST + Bearer + breaker + SSRF)
# =========================================================================


class TestFetchGraphQL:
    """Verify the GraphQL POST primitive mirrors fetch_json semantics."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        from hyperweave.connectors import base

        base._token_index = 0

    @staticmethod
    def _mock_client(response_json: Any, capture: dict[str, Any] | None = None) -> Any:
        """Build an AsyncMock that intercepts client.post and records the call."""
        mock_response = httpx.Response(
            200,
            json=response_json,
            request=httpx.Request("POST", "https://api.github.com/graphql"),
        )

        instance = AsyncMock()

        async def _capturing_post(url: str, **kwargs: Any) -> httpx.Response:
            if capture is not None:
                capture["url"] = url
                capture["headers"] = kwargs.get("headers", {})
                capture["json"] = kwargs.get("json", {})
            return mock_response

        instance.post = _capturing_post
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)
        return instance

    @pytest.mark.asyncio
    async def test_posts_query_and_variables_as_json_body(self) -> None:
        capture: dict[str, Any] = {}
        instance = self._mock_client({"data": {"ok": True}}, capture=capture)

        with patch("hyperweave.connectors.base.httpx.AsyncClient") as mock_client:
            mock_client.return_value = instance
            from hyperweave.connectors.base import fetch_graphql

            result = await fetch_graphql(
                query="query { viewer { login } }",
                variables={"owner": "eli64s"},
            )

        assert result == {"data": {"ok": True}}
        assert capture["url"] == "https://api.github.com/graphql"
        assert capture["json"] == {"query": "query { viewer { login } }", "variables": {"owner": "eli64s"}}
        assert capture["headers"]["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_sends_bearer_token_for_github(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HW_GITHUB_TOKENS", "ghp_test_token")
        capture: dict[str, Any] = {}
        instance = self._mock_client({"data": {}}, capture=capture)

        with patch("hyperweave.connectors.base.httpx.AsyncClient") as mock_client:
            mock_client.return_value = instance
            from hyperweave.connectors.base import fetch_graphql

            await fetch_graphql(query="{ viewer { login } }")

        assert capture["headers"]["Authorization"] == "Bearer ghp_test_token"

    @pytest.mark.asyncio
    async def test_omits_auth_without_token_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HW_GITHUB_TOKENS", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        capture: dict[str, Any] = {}
        instance = self._mock_client({"data": {}}, capture=capture)

        with patch("hyperweave.connectors.base.httpx.AsyncClient") as mock_client:
            mock_client.return_value = instance
            from hyperweave.connectors.base import fetch_graphql

            await fetch_graphql(query="{ viewer { login } }")

        assert "Authorization" not in capture["headers"]

    @pytest.mark.asyncio
    async def test_reuses_token_rotation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Pool rotation: two calls should use different tokens in order."""
        monkeypatch.setenv("HW_GITHUB_TOKENS", "tok_a,tok_b,tok_c")
        captures: list[dict[str, Any]] = [{}, {}]

        async def _run_call(idx: int) -> None:
            instance = self._mock_client({"data": {}}, capture=captures[idx])
            with patch("hyperweave.connectors.base.httpx.AsyncClient") as mock_client:
                mock_client.return_value = instance
                from hyperweave.connectors.base import fetch_graphql

                await fetch_graphql(query="{ viewer { login } }")

        await _run_call(0)
        await _run_call(1)

        assert captures[0]["headers"]["Authorization"] == "Bearer tok_a"
        assert captures[1]["headers"]["Authorization"] == "Bearer tok_b"

    @pytest.mark.asyncio
    async def test_http_failure_trips_breaker(self) -> None:
        instance = AsyncMock()
        instance.post = AsyncMock(side_effect=httpx.RequestError("connection refused"))
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)

        with patch("hyperweave.connectors.base.httpx.AsyncClient") as mock_client:
            mock_client.return_value = instance
            from hyperweave.connectors.base import fetch_graphql

            breaker = get_breaker("github")
            with pytest.raises(ConnectorError):
                await fetch_graphql(query="{ viewer { login } }")
            assert breaker._failure_count == 1

    @pytest.mark.asyncio
    async def test_rejects_non_allowlisted_host(self) -> None:
        from hyperweave.connectors.base import fetch_graphql

        with pytest.raises(SSRFError):
            await fetch_graphql(
                query="{ viewer { login } }",
                url="https://evil.example.com/graphql",
            )

    @pytest.mark.asyncio
    async def test_open_breaker_raises_without_posting(self) -> None:
        """When breaker is already OPEN, the call should fail fast with no HTTP attempt."""
        breaker = get_breaker("github")
        breaker._state = CircuitState.OPEN
        breaker._last_failure_time = time.monotonic()

        from hyperweave.connectors.base import fetch_graphql

        with pytest.raises(CircuitOpenError):
            await fetch_graphql(query="{ viewer { login } }")


# =========================================================================
# GraphQL Stargazer History (adaptive recent-window sampling)
# =========================================================================


class TestStargazerGraphQL:
    """Verify the GraphQL cursor-offset star-history pipeline + REST fallback.

    Post-v0.2.9: the primary GraphQL path samples N stargazer timestamps at
    evenly-distributed cursor offsets (bypassing REST's 400-page cap). The
    mock below decodes the ``after`` cursor to recover the target offset and
    returns the timestamp assigned to that offset by the fixture, matching
    production behavior where ``base64("cursor:<N-1>")`` fetches star #N.
    """

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()
        from hyperweave.connectors import base

        base._token_index = 0

    @staticmethod
    def _make_graphql_mock(
        timestamps_by_offset: dict[int, str],
        total_stars: int,
        captured: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Return a mock ``fetch_graphql`` that resolves cursor-offset queries.

        ``timestamps_by_offset`` maps 1-indexed stargazer offset → ISO timestamp.
        For each mock call the ``after`` cursor (or ``None`` for offset 1) is
        decoded to its offset; the matching timestamp is returned as a single
        edge. ``captured`` receives every incoming variables dict so tests
        can assert on the offset distribution.
        """
        import base64 as _b64

        def _offset_from_cursor(cursor: str | None) -> int:
            if cursor is None:
                return 1
            try:
                decoded = _b64.b64decode(cursor).decode()
            except Exception:  # pragma: no cover — malformed cursor would be a test bug
                return 1
            if decoded.startswith("cursor:"):
                try:
                    return int(decoded[len("cursor:") :]) + 1
                except ValueError:  # pragma: no cover
                    return 1
            return 1

        async def fake(query: str, variables: dict[str, Any], **_kw: Any) -> dict[str, Any]:
            if captured is not None:
                captured.append(dict(variables))
            offset = _offset_from_cursor(variables.get("cursor"))
            starred_at = timestamps_by_offset.get(offset)
            edges = [{"starredAt": starred_at}] if starred_at is not None else []
            return {
                "data": {
                    "repository": {
                        "stargazerCount": total_stars,
                        "stargazers": {"edges": edges},
                    }
                }
            }

        return fake

    # ── cursor construction (pure unit) ──

    def test_cursor_for_offset_encoding(self) -> None:
        from hyperweave.connectors.github import _cursor_for_offset

        assert _cursor_for_offset(1) is None
        assert _cursor_for_offset(0) is None  # defensive: also treated as "no cursor"
        # btoa("cursor:1") == "Y3Vyc29yOjE="
        assert _cursor_for_offset(2) == "Y3Vyc29yOjE="
        # btoa("cursor:99") == "Y3Vyc29yOjk5"
        assert _cursor_for_offset(100) == "Y3Vyc29yOjk5"

    # ── dispatcher routing (token → GraphQL; no token → REST) ──

    @pytest.mark.asyncio
    async def test_primary_path_with_token_uses_graphql_not_rest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HW_GITHUB_TOKENS", "ghp_test")
        rest_calls = {"n": 0}

        async def fail_rest(*args: Any, **kwargs: Any) -> Any:
            rest_calls["n"] += 1
            raise AssertionError("REST path should not be called when GraphQL succeeds")

        timestamps = {1: "2026-04-01T00:00:00Z", 2: "2026-04-02T00:00:00Z", 3: "2026-04-03T00:00:00Z"}
        monkeypatch.setattr(
            "hyperweave.connectors.github.fetch_graphql",
            self._make_graphql_mock(timestamps, total_stars=3),
        )
        monkeypatch.setattr("hyperweave.connectors.github.fetch_json", fail_rest)

        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("owner", "repo")

        assert rest_calls["n"] == 0
        assert result["current_stars"] == 3
        # 3 sampled stargazers (small repo, clamps sample_count to total) + now-point
        assert len(result["points"]) == 4

    @pytest.mark.asyncio
    async def test_no_token_skips_graphql_uses_rest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HW_GITHUB_TOKENS", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        graphql_calls = {"n": 0}

        async def fail_graphql(*args: Any, **kwargs: Any) -> Any:
            graphql_calls["n"] += 1
            raise AssertionError("GraphQL path should not be called without a token")

        async def fake_rest(url: str, **_kw: Any) -> Any:
            if "/stargazers" not in url:
                return {"stargazers_count": 50}
            return [{"starred_at": "2026-04-01T00:00:00Z"}]

        monkeypatch.setattr("hyperweave.connectors.github.fetch_graphql", fail_graphql)
        monkeypatch.setattr("hyperweave.connectors.github.fetch_json", fake_rest)

        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("owner", "repo")

        assert graphql_calls["n"] == 0
        assert result["current_stars"] == 50

    @pytest.mark.asyncio
    async def test_graphql_failure_falls_back_to_rest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HW_GITHUB_TOKENS", "ghp_test")

        async def failing_graphql(*args: Any, **kwargs: Any) -> Any:
            raise ConnectorError("simulated GraphQL failure")

        rest_called = {"n": 0}

        async def fake_rest(url: str, **_kw: Any) -> Any:
            rest_called["n"] += 1
            if "/stargazers" not in url:
                return {"stargazers_count": 42}
            return [{"starred_at": "2026-03-01T00:00:00Z"}]

        monkeypatch.setattr("hyperweave.connectors.github.fetch_graphql", failing_graphql)
        monkeypatch.setattr("hyperweave.connectors.github.fetch_json", fake_rest)

        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("owner", "repo")

        assert rest_called["n"] >= 1
        assert result["current_stars"] == 42

    # ── cursor-offset sampling correctness ──

    @pytest.mark.asyncio
    async def test_cursor_offset_samples_at_even_positions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """N=12 offsets across 10,000 stars fetches one point per offset.

        Verifies the offset distribution is even and each point's count
        matches its cursor offset (not a derived interpolation).
        """
        monkeypatch.setenv("HW_GITHUB_TOKENS", "ghp_test")
        # Synthesize timestamps for every possible offset — mock returns
        # whichever one the dispatcher asks for.
        timestamps = {i: f"2024-{((i - 1) % 12) + 1:02d}-15T00:00:00Z" for i in range(1, 10_001)}
        captured: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "hyperweave.connectors.github.fetch_graphql",
            self._make_graphql_mock(timestamps, total_stars=10_000, captured=captured),
        )

        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("owner", "repo", sample_pages=12)

        # 12 offset samples + 1 now-point = 13 total
        assert len(result["points"]) == 13
        # Last point is the now-point with the real total.
        assert result["points"][-1]["count"] == 10_000
        # Counts on the sampled points should span ~[1, 10000] — no flat cluster.
        sampled_counts = [p["count"] for p in result["points"][:-1]]
        assert min(sampled_counts) == 1  # offset 1 always included
        assert max(sampled_counts) == 10_000  # offset N always included

    @pytest.mark.asyncio
    async def test_mega_repo_samples_spread_across_full_lifetime(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """361K-star repo: 12 samples span stars #1 through #361K, not the recent 2K."""
        monkeypatch.setenv("HW_GITHUB_TOKENS", "ghp_test")
        # Fixture: star #1 is in Jan 2015; star #361,000 is in Dec 2026.
        # Spread evenly across 11 years (2015..2026 inclusive, 12 bucket-years).
        timestamps: dict[int, str] = {}
        for off in range(1, 361_001):
            year_frac = (off - 1) / (361_000 - 1)  # 0..1 inclusive
            year = 2015 + min(11, int(year_frac * 12))
            month = min(12, 1 + int(((off - 1) * 12 / 361_000) % 12))
            timestamps[off] = f"{year:04d}-{month:02d}-15T00:00:00Z"
        captured: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "hyperweave.connectors.github.fetch_graphql",
            self._make_graphql_mock(timestamps, total_stars=361_000, captured=captured),
        )

        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("openclaw", "openclaw", sample_pages=12)

        assert result["current_stars"] == 361_000
        sampled_years = [int(p["date"][:4]) for p in result["points"][:-1]]
        # Must cover the full lifetime — oldest point is in 2015, newest in 2026.
        assert min(sampled_years) == 2015
        assert max(sampled_years) == 2026
        # Not a flat cluster near total_stars: the 12 sampled counts should span
        # at least 90% of the repo's lifetime (1 → 361K).
        sampled_counts = [p["count"] for p in result["points"][:-1]]
        assert max(sampled_counts) - min(sampled_counts) >= 324_000  # 0.9 * 361K

    @pytest.mark.asyncio
    async def test_small_repo_clamps_sample_count_to_total_stars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """5-star repo with sample_pages=12 fetches only 5 points, not 12 duplicates."""
        monkeypatch.setenv("HW_GITHUB_TOKENS", "ghp_test")
        timestamps = {i: f"2026-04-{i:02d}T00:00:00Z" for i in range(1, 6)}
        captured: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "hyperweave.connectors.github.fetch_graphql",
            self._make_graphql_mock(timestamps, total_stars=5, captured=captured),
        )

        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("owner", "tiny-repo", sample_pages=12)

        # 5 stargazer points (one per star) + 1 now-point = 6 total
        assert len(result["points"]) == 6
        # Total GraphQL calls: 1 initial (for total_stars) + up to 4 additional
        # (offset 1 reuses the initial response). Capped well below sample_pages=12.
        assert len(captured) <= 5

    @pytest.mark.asyncio
    async def test_bounded_concurrency_limits_inflight_requests(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_GRAPHQL_CONCURRENCY caps parallel in-flight requests to avoid abuse-detection.

        Uses an awaitable barrier: if more than _GRAPHQL_CONCURRENCY requests
        enter simultaneously, the test fails.
        """
        monkeypatch.setenv("HW_GITHUB_TOKENS", "ghp_test")
        from hyperweave.connectors import github as gh_mod

        timestamps = {i: f"2024-{((i - 1) % 12) + 1:02d}-15T00:00:00Z" for i in range(1, 1001)}
        in_flight = {"count": 0, "peak": 0}

        async def throttle_observing_mock(query: str, variables: dict[str, Any], **_kw: Any) -> dict[str, Any]:
            in_flight["count"] += 1
            in_flight["peak"] = max(in_flight["peak"], in_flight["count"])
            await asyncio.sleep(0.02)  # simulate network latency so concurrency is observable
            in_flight["count"] -= 1
            offset = 1
            if variables.get("cursor"):
                import base64 as _b64

                decoded = _b64.b64decode(variables["cursor"]).decode()
                if decoded.startswith("cursor:"):
                    offset = int(decoded[len("cursor:") :]) + 1
            return {
                "data": {
                    "repository": {
                        "stargazerCount": 1000,
                        "stargazers": {"edges": [{"starredAt": timestamps[offset]}]},
                    }
                }
            }

        monkeypatch.setattr("hyperweave.connectors.github.fetch_graphql", throttle_observing_mock)

        from hyperweave.connectors.github import fetch_stargazer_history

        await fetch_stargazer_history("owner", "repo", sample_pages=12)

        # Never more than _GRAPHQL_CONCURRENCY in flight at once.
        assert in_flight["peak"] <= gh_mod._GRAPHQL_CONCURRENCY

    @pytest.mark.asyncio
    async def test_now_point_uses_current_utc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Even with ancient fixture timestamps, the terminal point is stamped "now"."""
        monkeypatch.setenv("HW_GITHUB_TOKENS", "ghp_test")
        timestamps = {1: "2020-01-01T00:00:00Z"}  # single ancient star
        monkeypatch.setattr(
            "hyperweave.connectors.github.fetch_graphql",
            self._make_graphql_mock(timestamps, total_stars=1),
        )

        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("owner", "repo")

        now_year = str(datetime.now(UTC).year)
        assert result["points"][-1]["date"].startswith(now_year)

    @pytest.mark.asyncio
    async def test_empty_repo_returns_empty_points(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Zero-star repo → no sampling attempted, empty points list."""
        monkeypatch.setenv("HW_GITHUB_TOKENS", "ghp_test")
        monkeypatch.setattr(
            "hyperweave.connectors.github.fetch_graphql",
            self._make_graphql_mock(timestamps_by_offset={}, total_stars=0),
        )

        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("owner", "brand-new-repo")

        assert result["points"] == []
        assert result["current_stars"] == 0
