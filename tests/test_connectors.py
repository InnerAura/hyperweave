"""Tests for the connectors module.

Tests SSRF protection, circuit breaker state machine, response
parsing for all six providers, and the TTL cache.
"""

from __future__ import annotations

import time
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
