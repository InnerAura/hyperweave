"""Tests for the connectors module.

Tests SSRF protection, circuit breaker state machine, response
parsing for all six providers, and the TTL cache.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

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
        assert cache.ttl_for_provider("crates") == 600
        assert cache.ttl_for_provider("scorecard") == 21600
        assert cache.ttl_for_provider("dora") == 3600
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

        instance = AsyncMock()
        instance.get = AsyncMock(return_value=mock_response)

        with patch("hyperweave.connectors.base.get_client", return_value=instance):
            response = await fetch(
                "https://api.github.com/repos/test/test",
                provider="github",
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_failed_fetch_trips_breaker(self) -> None:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=httpx.RequestError("connection refused"))

        with patch("hyperweave.connectors.base.get_client", return_value=instance):
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

    def test_format_relative_time_buckets(self) -> None:
        from hyperweave.connectors.github import _format_relative_time

        now = datetime.now(UTC)
        # Deltas sit safely mid-bucket so sub-second drift can't cross a boundary.
        assert _format_relative_time((now - timedelta(seconds=20)).isoformat()) == "JUST NOW"
        assert _format_relative_time((now - timedelta(hours=3, minutes=20)).isoformat()) == "3H AGO"
        assert _format_relative_time((now - timedelta(days=2, hours=5)).isoformat()) == "2D AGO"
        assert _format_relative_time((now - timedelta(days=400)).isoformat()) == "1Y AGO"
        assert _format_relative_time("not-a-timestamp") == "unknown"

    @pytest.mark.asyncio
    async def test_last_push_metric_formats_relative(self) -> None:
        recent = (datetime.now(UTC) - timedelta(hours=5, minutes=20)).isoformat().replace("+00:00", "Z")
        with patch(
            "hyperweave.connectors.github.fetch_json",
            new_callable=AsyncMock,
            return_value={"pushed_at": recent},
        ):
            from hyperweave.connectors.github import fetch_metric

            result = await fetch_metric("eli64s/readme-ai", "last_push")
            assert result["metric"] == "last_push"
            assert result["value"] == "5H AGO"

    @pytest.mark.asyncio
    async def test_contributors_count_from_link_header(self) -> None:
        # The contributors API has no count field; the count is the rel="last"
        # page index in the Link header (per_page=1 makes page == contributor count).
        response = MagicMock()
        response.headers = {
            "Link": (
                '<https://api.github.com/repositories/1/contributors?per_page=1&page=2>; rel="next", '
                '<https://api.github.com/repositories/1/contributors?per_page=1&page=6>; rel="last"'
            )
        }
        with patch(
            "hyperweave.connectors.github.fetch",
            new_callable=AsyncMock,
            return_value=response,
        ):
            from hyperweave.connectors.github import fetch_metric

            result = await fetch_metric("eli64s/readme-ai", "contributors")
            assert result["metric"] == "contributors"
            assert result["value"] == 6

    @pytest.mark.asyncio
    async def test_contributors_count_fallback_when_no_link(self) -> None:
        # <=1 contributor → no Link header → fall back to body length.
        response = MagicMock()
        response.headers = {}
        response.json.return_value = [{"login": "solo"}]
        with patch(
            "hyperweave.connectors.github.fetch",
            new_callable=AsyncMock,
            return_value=response,
        ):
            from hyperweave.connectors.github import fetch_metric

            result = await fetch_metric("eli64s/readme-ai", "contributors")
            assert result["value"] == 1

    @pytest.mark.asyncio
    async def test_pull_requests_count_from_search_api(self) -> None:
        # open_issues_count conflates issues + PRs, so PRs come from the Search
        # API's total_count via the dedicated github-search breaker.
        with patch(
            "hyperweave.connectors.github.fetch_json",
            new_callable=AsyncMock,
            return_value={"total_count": 25, "items": []},
        ):
            from hyperweave.connectors.github import fetch_metric

            result = await fetch_metric("eli64s/readme-ai", "pull_requests")
            assert result["metric"] == "pull_requests"
            assert result["value"] == 25


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

    @pytest.mark.asyncio
    async def test_downloads_metric_primary_pepy_total(self) -> None:
        # v0.3.12: downloads is sourced from pepy.tech v2 (total_downloads),
        # keyless and burst-tolerant. pypi.org's JSON never carried counts and
        # pypistats.org rate-limits (429), so pepy is primary.
        captured_urls: list[str] = []

        async def fake_fetch_json(url: str, **_kwargs: Any) -> Any:
            captured_urls.append(url)
            return {"id": "readmeai", "total_downloads": 234567, "versions": []}

        with patch("hyperweave.connectors.rest.fetch_json", side_effect=fake_fetch_json):
            from hyperweave.connectors.rest import pypi_fetch_metric as fetch_metric

            result = await fetch_metric("readmeai", "downloads")

        assert result["value"] == 234567
        assert result["provider"] == "pypi"
        assert captured_urls == ["https://pepy.tech/api/v2/projects/readmeai"]

    @pytest.mark.asyncio
    async def test_downloads_falls_back_to_pypistats_when_pepy_fails(self) -> None:
        # When pepy is unavailable (429/network), fall back to pypistats
        # last-month so downloads never silently returns --.
        from hyperweave.connectors.base import ConnectorError

        captured_urls: list[str] = []

        async def fake_fetch_json(url: str, **_kwargs: Any) -> Any:
            captured_urls.append(url)
            if "pepy.tech" in url:
                raise ConnectorError("pepy down (429)")
            return {"data": {"last_day": 1, "last_week": 7, "last_month": 234567}, "type": "recent_downloads"}

        with patch("hyperweave.connectors.rest.fetch_json", side_effect=fake_fetch_json):
            from hyperweave.connectors.rest import pypi_fetch_metric as fetch_metric

            result = await fetch_metric("readmeai", "downloads")

        assert result["value"] == 234567
        assert "pepy.tech" in captured_urls[0]
        assert "pypistats.org" in captured_urls[1]

    @pytest.mark.asyncio
    async def test_downloads_zero_when_both_sources_empty(self) -> None:
        # pepy returns no total + pypistats empty → coerce to 0, not None/-1.
        from hyperweave.connectors.base import ConnectorError

        async def fake_fetch_json(url: str, **_kwargs: Any) -> Any:
            if "pepy.tech" in url:
                raise ConnectorError("pepy down")
            return {"data": {}, "package": "ghost", "type": "recent_downloads"}

        with patch("hyperweave.connectors.rest.fetch_json", side_effect=fake_fetch_json):
            from hyperweave.connectors.rest import pypi_fetch_metric as fetch_metric

            result = await fetch_metric("ghost", "downloads")
            assert result["value"] == 0


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
    def _reset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_breakers()
        get_cache().clear()

        # v0.2.16-fix3: fetch_stargazer_history now does a GraphQL second-source
        # cross-check on stargazerCount. These tests mock /repos via fetch_json
        # but not fetch_graphql, so the GraphQL call would either hit real HTTP
        # (test pollution) or raise (test pass for the wrong reason). Mock
        # fetch_graphql to a payload that returns 0 → cross-check helper
        # treats 0 as "couldn't verify" and skips the cross-check, preserving
        # the original test behavior of trusting the REST stargazers_count.
        async def _stub_graphql(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {"data": {"repository": None}}

        monkeypatch.setattr("hyperweave.connectors.github.fetch_graphql", _stub_graphql)

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
        """Build an AsyncMock that intercepts client.post and records the call.

        Returned mock is patched in via ``patch("hyperweave.connectors.base.get_client",
        return_value=instance)`` since fetch_graphql now uses the module singleton
        client rather than ``async with httpx.AsyncClient(...)``.
        """
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
        return instance

    @pytest.mark.asyncio
    async def test_posts_query_and_variables_as_json_body(self) -> None:
        capture: dict[str, Any] = {}
        instance = self._mock_client({"data": {"ok": True}}, capture=capture)

        with patch("hyperweave.connectors.base.get_client", return_value=instance):
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

        with patch("hyperweave.connectors.base.get_client", return_value=instance):
            from hyperweave.connectors.base import fetch_graphql

            await fetch_graphql(query="{ viewer { login } }")

        assert capture["headers"]["Authorization"] == "Bearer ghp_test_token"

    @pytest.mark.asyncio
    async def test_omits_auth_without_token_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HW_GITHUB_TOKENS", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        capture: dict[str, Any] = {}
        instance = self._mock_client({"data": {}}, capture=capture)

        with patch("hyperweave.connectors.base.get_client", return_value=instance):
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
            with patch("hyperweave.connectors.base.get_client", return_value=instance):
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

        with patch("hyperweave.connectors.base.get_client", return_value=instance):
            from hyperweave.connectors.base import fetch_graphql

            # Three breaker domains exist post-v0.2.11 (core / search / graphql);
            # GraphQL traffic isolates from search-API rate-limit storms.
            breaker = get_breaker("github-graphql")
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
        breaker = get_breaker("github-graphql")
        breaker._state = CircuitState.OPEN
        breaker._last_failure_time = time.monotonic()

        from hyperweave.connectors.base import fetch_graphql

        with pytest.raises(CircuitOpenError):
            await fetch_graphql(query="{ viewer { login } }")


# =========================================================================
# Stargazer History REST sampling — detailed coverage
# =========================================================================


class TestStargazerRESTSampling:
    """Exercises the REST-only stargazer path end-to-end.

    v0.2.10 removed an earlier GraphQL cursor-offset sampler that was based
    on a false assumption about GitHub's cursor format (they're opaque
    ``cursor:v2:<MessagePack>`` pointers, not ``cursor:<N>``). Tests here
    pin the REST behavior — even evenly-distributed sample pages, now-point
    stamping with current UTC, clamp at 400 pages for mega-repos, and
    single-page granularity for tiny repos.
    """

    @pytest.fixture(autouse=True)
    def _reset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_breakers()
        get_cache().clear()
        from hyperweave.connectors import base

        base._token_index = 0

        # See TestStargazerPagination._reset: stub GraphQL cross-check.
        async def _stub_graphql(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {"data": {"repository": None}}

        monkeypatch.setattr("hyperweave.connectors.github.fetch_graphql", _stub_graphql)

    @pytest.mark.asyncio
    async def test_cursor_offset_helper_is_removed(self) -> None:
        """The broken ``_cursor_for_offset`` helper must not exist.

        Regression gate for v0.2.10: re-introducing a ``cursor:<N-1>`` offset
        helper would resurrect the broken sampler. Real GitHub cursors are
        ``cursor:v2:<MessagePack>`` blobs — constructed ``cursor:N-1`` blobs
        were either rejected with ``INVALID_CURSOR_ARGUMENTS`` or silently
        returned a recent stargazer, collapsing the chart into a flat line.
        """
        from hyperweave.connectors import github as gh_mod

        assert not hasattr(gh_mod, "_cursor_for_offset")
        assert not hasattr(gh_mod, "_fetch_stargazer_history_graphql")
        assert not hasattr(gh_mod, "_CURSOR_OFFSET_QUERY")
        assert not hasattr(gh_mod, "_GRAPHQL_CONCURRENCY")

    @pytest.mark.asyncio
    async def test_sample_pages_evenly_distributed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Medium repo: 12 sample points are spread evenly across all pages.

        For a 2,900-star repo (29 pages), the 12-sample distribution should
        land on pages [1, 3, 6, 8, 11, 13, 16, 18, 21, 23, 26, 29] — each
        step of roughly (29-1)/11 ≈ 2.55, rounded.
        """
        captured_pages: list[int] = []

        async def fake_fetch_json(url: str, **_kw: Any) -> Any:
            if "/stargazers" in url:
                page = int(url.split("page=")[-1])
                captured_pages.append(page)
                # Return a timestamp so the point is emitted (starred_at
                # proportional to page so the sampled curve climbs).
                year = 2023 + (page // 12)
                month = 1 + (page % 12)
                return [{"starred_at": f"{year:04d}-{month:02d}-01T00:00:00Z"}]
            return {"stargazers_count": 2900}

        monkeypatch.setattr("hyperweave.connectors.github.fetch_json", fake_fetch_json)
        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("owner", "medium-repo", sample_pages=12)

        # 12 sample points + 1 now-point appended at the end.
        assert len(result["points"]) == 13
        # First sample is page 1, last sample is page 29 (total pages).
        assert min(captured_pages) == 1
        assert max(captured_pages) == 29
        # Counts climb monotonically (page N → count (N-1)*100 + 1, except
        # page 1 which is clamped to 1).
        counts = [p["count"] for p in result["points"]]
        assert counts[0] == 1
        assert counts[-1] == 2900  # now-point uses real total
        # All intermediate counts monotonically non-decreasing.
        assert all(counts[i] <= counts[i + 1] for i in range(len(counts) - 1))

    @pytest.mark.asyncio
    async def test_no_token_still_uses_rest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """REST is the only path — it runs regardless of token presence."""
        monkeypatch.delenv("HW_GITHUB_TOKENS", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        async def fake_rest(url: str, **_kw: Any) -> Any:
            if "/stargazers" not in url:
                return {"stargazers_count": 50}
            return [{"starred_at": "2026-04-01T00:00:00Z"}]

        monkeypatch.setattr("hyperweave.connectors.github.fetch_json", fake_rest)

        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("owner", "repo")

        assert result["current_stars"] == 50
        assert len(result["points"]) >= 1

    @pytest.mark.asyncio
    async def test_now_point_uses_current_utc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Even with ancient stargazer timestamps, the terminal point is stamped "now".

        Uses a 500-star repo so the multi-page branch runs — the single-page
        branch (≤100 stars) is a separate code path that emits each
        stargazer's own timestamp and appends no now-point.
        """

        async def fake_fetch_json(url: str, **_kw: Any) -> Any:
            if "/stargazers" in url:
                return [{"starred_at": "2020-01-01T00:00:00Z"}]
            return {"stargazers_count": 500}

        monkeypatch.setattr("hyperweave.connectors.github.fetch_json", fake_fetch_json)

        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("owner", "repo")

        now_year = str(datetime.now(UTC).year)
        assert result["points"][-1]["date"].startswith(now_year)
        # Real total preserved on the now-point.
        assert result["points"][-1]["count"] == 500

    @pytest.mark.asyncio
    async def test_empty_repo_returns_empty_points(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Zero-star repo → no sampling attempted, empty points list."""

        async def fake_fetch_json(url: str, **_kw: Any) -> Any:
            if "/stargazers" in url:
                return []  # won't be reached; caller bails on stargazers_count=0
            return {"stargazers_count": 0}

        monkeypatch.setattr("hyperweave.connectors.github.fetch_json", fake_fetch_json)

        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("owner", "brand-new-repo")

        assert result["points"] == []
        assert result["current_stars"] == 0

    @pytest.mark.asyncio
    async def test_single_page_repo_uses_per_star_timestamps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """<= 100-star repo: emit each stargazer's own timestamp, not page-first only."""
        fixture_page = [{"starred_at": f"2024-0{i}-01T00:00:00Z"} for i in range(1, 8)]

        async def fake_fetch_json(url: str, **_kw: Any) -> Any:
            if "/stargazers" in url:
                return fixture_page
            return {"stargazers_count": 7}

        monkeypatch.setattr("hyperweave.connectors.github.fetch_json", fake_fetch_json)

        from hyperweave.connectors.github import fetch_stargazer_history

        result = await fetch_stargazer_history("owner", "tiny-repo")

        # 7 stargazer points, each with its own timestamp and count 1..7.
        # No now-point appended on the single-page path (REST single_page branch).
        assert len(result["points"]) == 7
        assert [p["count"] for p in result["points"]] == [1, 2, 3, 4, 5, 6, 7]


# =========================================================================
# crates.io Provider (v0.3.12)
# =========================================================================


class TestCratesProvider:
    """crates.io connector — verified live against ``serde``."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    MOCK_DATA: ClassVar[dict[str, Any]] = {
        "crate": {
            "max_stable_version": "1.0.228",
            "newest_version": "1.0.228",
            "downloads": 1036804419,
            "recent_downloads": 195396284,
        },
        "versions": [{"num": "1.0.228", "license": "MIT OR Apache-2.0"}],
    }

    @pytest.mark.asyncio
    async def test_version_metric(self) -> None:
        with patch("hyperweave.connectors.rest.fetch_json", new_callable=AsyncMock, return_value=self.MOCK_DATA):
            from hyperweave.connectors.rest import crates_fetch_metric

            result = await crates_fetch_metric("serde", "version")
            assert result["value"] == "1.0.228"
            assert result["provider"] == "crates"

    @pytest.mark.asyncio
    async def test_downloads_and_recent(self) -> None:
        with patch("hyperweave.connectors.rest.fetch_json", new_callable=AsyncMock, return_value=self.MOCK_DATA):
            from hyperweave.connectors.rest import crates_fetch_metric

            assert (await crates_fetch_metric("serde", "downloads"))["value"] == 1036804419
            get_cache().clear()
            assert (await crates_fetch_metric("serde", "recent_downloads"))["value"] == 195396284

    @pytest.mark.asyncio
    async def test_license_from_versions(self) -> None:
        with patch("hyperweave.connectors.rest.fetch_json", new_callable=AsyncMock, return_value=self.MOCK_DATA):
            from hyperweave.connectors.rest import crates_fetch_metric

            assert (await crates_fetch_metric("serde", "license"))["value"] == "MIT OR Apache-2.0"

    @pytest.mark.asyncio
    async def test_version_falls_back_to_newest(self) -> None:
        # Pre-1.0 / pre-release-only crates have no max_stable_version.
        data = {"crate": {"newest_version": "0.1.0-alpha"}, "versions": []}
        with patch("hyperweave.connectors.rest.fetch_json", new_callable=AsyncMock, return_value=data):
            from hyperweave.connectors.rest import crates_fetch_metric

            assert (await crates_fetch_metric("preview", "version"))["value"] == "0.1.0-alpha"

    @pytest.mark.asyncio
    async def test_empty_versions_license_unknown(self) -> None:
        data = {"crate": {"max_stable_version": "1.0.0"}, "versions": []}
        with patch("hyperweave.connectors.rest.fetch_json", new_callable=AsyncMock, return_value=data):
            from hyperweave.connectors.rest import crates_fetch_metric

            assert (await crates_fetch_metric("ghost", "license"))["value"] == "Unknown"

    @pytest.mark.asyncio
    async def test_unknown_metric_raises(self) -> None:
        with patch("hyperweave.connectors.rest.fetch_json", new_callable=AsyncMock, return_value=self.MOCK_DATA):
            from hyperweave.connectors.rest import crates_fetch_metric

            with pytest.raises(ValueError, match="Unknown crates metric"):
                await crates_fetch_metric("serde", "nonexistent")

    @pytest.mark.asyncio
    async def test_user_agent_header_sent(self) -> None:
        # crates.io 403s requests without a descriptive UA — assert we send one.
        captured: dict[str, Any] = {}

        async def fake_fetch_json(url: str, **kwargs: Any) -> Any:
            captured["headers"] = kwargs.get("headers", {})
            return self.MOCK_DATA

        with patch("hyperweave.connectors.rest.fetch_json", side_effect=fake_fetch_json):
            from hyperweave.connectors.rest import crates_fetch_metric

            await crates_fetch_metric("serde", "version")

        assert "HyperWeave/" in captured["headers"].get("User-Agent", "")


# =========================================================================
# OpenSSF Scorecard Provider (v0.3.12)
# =========================================================================


class TestScorecardProvider:
    """OpenSSF Scorecard — verified live against ``tokio-rs/tokio``."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    MOCK_PAYLOAD: ClassVar[dict[str, Any]] = {
        "date": "2026-05-25",
        "repo": {"name": "github.com/tokio-rs/tokio"},
        "score": 6.9,
        "checks": [
            {"name": "Maintained", "score": 10},
            {"name": "Code-Review", "score": 10},
            {"name": "Token-Permissions", "score": 0},
            {"name": "Branch-Protection", "score": -1},
        ],
    }

    @pytest.mark.asyncio
    async def test_aggregate_score(self) -> None:
        with patch(
            "hyperweave.connectors.scorecard.fetch_json", new_callable=AsyncMock, return_value=self.MOCK_PAYLOAD
        ):
            from hyperweave.connectors.scorecard import fetch_metric

            result = await fetch_metric("tokio-rs/tokio", "score")
            assert result["value"] == 6.9
            assert result["provider"] == "scorecard"

    @pytest.mark.asyncio
    async def test_named_check_resolves(self) -> None:
        with patch(
            "hyperweave.connectors.scorecard.fetch_json", new_callable=AsyncMock, return_value=self.MOCK_PAYLOAD
        ):
            from hyperweave.connectors.scorecard import fetch_metric

            assert (await fetch_metric("tokio-rs/tokio", "code_review"))["value"] == 10

    @pytest.mark.asyncio
    async def test_negative_one_is_na(self) -> None:
        # Branch-Protection=-1 means "did not run" → must surface as n/a,
        # never a negative gauge value.
        with patch(
            "hyperweave.connectors.scorecard.fetch_json", new_callable=AsyncMock, return_value=self.MOCK_PAYLOAD
        ):
            from hyperweave.connectors.scorecard import fetch_metric

            assert (await fetch_metric("tokio-rs/tokio", "branch_protection"))["value"] == "n/a"

    @pytest.mark.asyncio
    async def test_real_zero_is_preserved(self) -> None:
        # Token-Permissions=0 is a real (worst) score, NOT n/a.
        with patch(
            "hyperweave.connectors.scorecard.fetch_json", new_callable=AsyncMock, return_value=self.MOCK_PAYLOAD
        ):
            from hyperweave.connectors.scorecard import fetch_metric

            assert (await fetch_metric("tokio-rs/tokio", "token_permissions"))["value"] == 0

    @pytest.mark.asyncio
    async def test_absent_check_is_na(self) -> None:
        # vulnerabilities is not in tokio's variable-length checks[] → n/a, not 0.
        with patch(
            "hyperweave.connectors.scorecard.fetch_json", new_callable=AsyncMock, return_value=self.MOCK_PAYLOAD
        ):
            from hyperweave.connectors.scorecard import fetch_metric

            assert (await fetch_metric("tokio-rs/tokio", "vulnerabilities"))["value"] == "n/a"

    @pytest.mark.asyncio
    async def test_fetch_once_single_api_call(self) -> None:
        # Two metric tokens for one repo must share a single upstream call.
        mock = AsyncMock(return_value=self.MOCK_PAYLOAD)
        with patch("hyperweave.connectors.scorecard.fetch_json", mock):
            from hyperweave.connectors.scorecard import fetch_metric

            await fetch_metric("tokio-rs/tokio", "score")
            await fetch_metric("tokio-rs/tokio", "maintained")
            assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_invalid_identifier_raises(self) -> None:
        from hyperweave.connectors.scorecard import fetch_metric

        with pytest.raises(ValueError, match="owner/repo"):
            await fetch_metric("no-slash", "score")

    @pytest.mark.asyncio
    async def test_unknown_metric_raises(self) -> None:
        with patch(
            "hyperweave.connectors.scorecard.fetch_json", new_callable=AsyncMock, return_value=self.MOCK_PAYLOAD
        ):
            from hyperweave.connectors.scorecard import fetch_metric

            with pytest.raises(ValueError, match="Unknown Scorecard metric"):
                await fetch_metric("tokio-rs/tokio", "bogus")


# =========================================================================
# GitHub Actions DORA Provider (v0.3.12)
# =========================================================================


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class TestDoraProvider:
    """DORA computed metrics over a 30-day window."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    @pytest.mark.asyncio
    async def test_deployments_path_computes_metrics(self, monkeypatch: pytest.MonkeyPatch) -> None:
        now = datetime.now(UTC)
        deployments = [
            {
                "id": 3,
                "sha": "sha3",
                "created_at": _iso(now - timedelta(days=1)),
                "updated_at": _iso(now - timedelta(days=1)),
            },
            {
                "id": 2,
                "sha": "sha2",
                "created_at": _iso(now - timedelta(days=2)),
                "updated_at": _iso(now - timedelta(days=2)),
            },
            {
                "id": 1,
                "sha": "sha1",
                "created_at": _iso(now - timedelta(days=3)),
                "updated_at": _iso(now - timedelta(days=3)),
            },
        ]
        statuses = {
            3: [{"state": "success", "created_at": _iso(now - timedelta(days=1))}],
            2: [{"state": "failure", "created_at": _iso(now - timedelta(days=2))}],
            1: [{"state": "success", "created_at": _iso(now - timedelta(days=3))}],
        }
        commits = {
            "sha3": {"commit": {"author": {"date": _iso(now - timedelta(days=1, hours=2))}}},
            "sha2": {"commit": {"author": {"date": _iso(now - timedelta(days=2, hours=4))}}},
            "sha1": {"commit": {"author": {"date": _iso(now - timedelta(days=3, hours=6))}}},
        }

        async def fake(url: str, **_kw: Any) -> Any:
            if "/deployments?" in url:
                return deployments
            if "/statuses" in url:
                dep_id = int(url.split("/deployments/")[1].split("/statuses")[0])
                return statuses[dep_id]
            if "/commits/" in url:
                return commits[url.rsplit("/", 1)[1]]
            return {}

        monkeypatch.setattr("hyperweave.connectors.dora.fetch_json", fake)
        from hyperweave.connectors.dora import fetch_metric

        # cfr = 1 failure / 3 total = 33.3%
        assert (await fetch_metric("o/r", "change_failure_rate"))["value"] == pytest.approx(33.3)
        # deploy_frequency = 2 successes / 30 days
        assert (await fetch_metric("o/r", "deploy_frequency"))["value"] == pytest.approx(round(2 / 30, 3))
        # lead_time = median([2h, 4h, 6h]) = 4.0
        assert (await fetch_metric("o/r", "lead_time"))["value"] == pytest.approx(4.0)
        # mttr: failure (day2) → next success (day1) = 24h
        assert (await fetch_metric("o/r", "mttr"))["value"] == pytest.approx(24.0)

    @pytest.mark.asyncio
    async def test_fetch_once_shares_aggregate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        now = datetime.now(UTC)
        deployments = [
            {
                "id": 1,
                "sha": "s1",
                "created_at": _iso(now - timedelta(days=1)),
                "updated_at": _iso(now - timedelta(days=1)),
            }
        ]
        calls: list[str] = []

        async def fake(url: str, **_kw: Any) -> Any:
            calls.append(url)
            if "/deployments?" in url:
                return deployments
            if "/statuses" in url:
                return [{"state": "success", "created_at": _iso(now - timedelta(days=1))}]
            if "/commits/" in url:
                return {"commit": {"author": {"date": _iso(now - timedelta(days=1, hours=1))}}}
            return {}

        monkeypatch.setattr("hyperweave.connectors.dora.fetch_json", fake)
        from hyperweave.connectors.dora import fetch_metric

        await fetch_metric("o/r", "deploy_frequency")
        first_round = len(calls)
        await fetch_metric("o/r", "mttr")
        # Second metric reads the cached aggregate — no new upstream calls.
        assert len(calls) == first_round

    @pytest.mark.asyncio
    async def test_actions_fallback_when_no_deployments(self, monkeypatch: pytest.MonkeyPatch) -> None:
        now = datetime.now(UTC)
        runs = {
            "workflow_runs": [
                {
                    "status": "completed",
                    "conclusion": "success",
                    "updated_at": _iso(now - timedelta(days=1)),
                    "head_sha": "a",
                    "head_commit": {"timestamp": _iso(now - timedelta(days=1, hours=3))},
                },
                {
                    "status": "completed",
                    "conclusion": "failure",
                    "updated_at": _iso(now - timedelta(days=2)),
                    "head_sha": "b",
                    "head_commit": {"timestamp": _iso(now - timedelta(days=2, hours=1))},
                },
            ]
        }

        async def fake(url: str, **_kw: Any) -> Any:
            if "/deployments?" in url:
                return []  # forces the Actions fallback
            if url.endswith("/repos/o/r") or "/repos/o/r?" in url:
                return {"default_branch": "main"}
            if "/actions/runs" in url:
                return runs
            return {"default_branch": "main"}

        monkeypatch.setattr("hyperweave.connectors.dora.fetch_json", fake)
        from hyperweave.connectors.dora import fetch_metric

        # cfr = 1 failure / 2 total = 50%
        assert (await fetch_metric("o/r", "change_failure_rate"))["value"] == pytest.approx(50.0)
        # lead_time = median([3h, 1h]) = 2.0 (head_commit.timestamp is inline)
        assert (await fetch_metric("o/r", "lead_time"))["value"] == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_zero_deploys_edge_case(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake(url: str, **_kw: Any) -> Any:
            if "/deployments?" in url:
                return []
            if "/actions/runs" in url:
                return {"workflow_runs": []}
            return {"default_branch": "main"}

        monkeypatch.setattr("hyperweave.connectors.dora.fetch_json", fake)
        from hyperweave.connectors.dora import fetch_metric

        assert (await fetch_metric("o/r", "deploy_frequency"))["value"] == 0.0
        assert (await fetch_metric("o/r", "lead_time"))["value"] == "n/a"
        assert (await fetch_metric("o/r", "mttr"))["value"] == "n/a"

    @pytest.mark.asyncio
    async def test_invalid_identifier_raises(self) -> None:
        from hyperweave.connectors.dora import fetch_metric

        with pytest.raises(ValueError, match="owner/repo"):
            await fetch_metric("no-slash", "deploy_frequency")

    @pytest.mark.asyncio
    async def test_unknown_metric_raises(self) -> None:
        from hyperweave.connectors.dora import fetch_metric

        with pytest.raises(ValueError, match="Unknown DORA metric"):
            await fetch_metric("o/r", "bogus")


# =========================================================================
# HuggingFace + arXiv extended fields (v0.3.12 — audit-surfaced)
# =========================================================================


class TestHuggingFaceExtendedFields:
    """v0.3.12 HF fields — verified live against ``mistralai/Mistral-7B-v0.1``."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    MOCK_DATA: ClassVar[dict[str, Any]] = {
        "lastModified": "2025-07-24T16:44:02.000Z",
        "gated": False,
        "cardData": {"license": "apache-2.0"},
        "tags": ["license:apache-2.0", "pytorch"],
    }

    @pytest.mark.asyncio
    async def test_last_modified_casing(self) -> None:
        with patch("hyperweave.connectors.rest.fetch_json", new_callable=AsyncMock, return_value=self.MOCK_DATA):
            from hyperweave.connectors.rest import hf_fetch_metric

            assert (await hf_fetch_metric("org/model", "last_modified"))["value"] == "2025-07-24T16:44:02.000Z"

    @pytest.mark.asyncio
    async def test_gated_bool_stringifies_lowercase(self) -> None:
        with patch("hyperweave.connectors.rest.fetch_json", new_callable=AsyncMock, return_value=self.MOCK_DATA):
            from hyperweave.connectors.rest import hf_fetch_metric

            assert (await hf_fetch_metric("org/model", "gated"))["value"] == "false"

    @pytest.mark.asyncio
    async def test_gated_access_mode_string(self) -> None:
        data = {"gated": "manual"}
        with patch("hyperweave.connectors.rest.fetch_json", new_callable=AsyncMock, return_value=data):
            from hyperweave.connectors.rest import hf_fetch_metric

            assert (await hf_fetch_metric("org/model", "gated"))["value"] == "manual"

    @pytest.mark.asyncio
    async def test_license_from_card_data(self) -> None:
        # License is NOT top-level — it lives in cardData.license.
        with patch("hyperweave.connectors.rest.fetch_json", new_callable=AsyncMock, return_value=self.MOCK_DATA):
            from hyperweave.connectors.rest import hf_fetch_metric

            assert (await hf_fetch_metric("org/model", "license"))["value"] == "apache-2.0"

    @pytest.mark.asyncio
    async def test_license_falls_back_to_tag(self) -> None:
        data = {"tags": ["license:mit", "pytorch"]}
        with patch("hyperweave.connectors.rest.fetch_json", new_callable=AsyncMock, return_value=data):
            from hyperweave.connectors.rest import hf_fetch_metric

            assert (await hf_fetch_metric("org/model", "license"))["value"] == "mit"


class TestArxivExtendedFields:
    """v0.3.12 arXiv fields — verified live against ``2310.06825``."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    XML_WITHOUT_OPTIONAL = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <title>Mistral 7B</title>
    <published>2023-10-10T17:54:58Z</published>
    <updated>2023-10-11T09:00:00Z</updated>
    <summary>Abstract.</summary>
  </entry>
</feed>"""

    XML_WITH_OPTIONAL = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <title>Published Paper</title>
    <published>2020-01-01T00:00:00Z</published>
    <updated>2021-06-01T00:00:00Z</updated>
    <arxiv:journal_ref>Nature 583, 2020</arxiv:journal_ref>
    <arxiv:doi>10.1000/xyz123</arxiv:doi>
    <summary>Abstract.</summary>
  </entry>
</feed>"""

    @pytest.mark.asyncio
    async def test_updated_metric(self) -> None:
        with patch(
            "hyperweave.connectors.arxiv.fetch_text", new_callable=AsyncMock, return_value=self.XML_WITHOUT_OPTIONAL
        ):
            from hyperweave.connectors.arxiv import fetch_metric

            assert (await fetch_metric("2310.06825", "updated"))["value"] == "2023-10-11T09:00:00Z"

    @pytest.mark.asyncio
    async def test_absent_journal_ref_is_na(self) -> None:
        # journal_ref / doi are frequently absent — must render n/a, never crash.
        with patch(
            "hyperweave.connectors.arxiv.fetch_text", new_callable=AsyncMock, return_value=self.XML_WITHOUT_OPTIONAL
        ):
            from hyperweave.connectors.arxiv import fetch_metric

            assert (await fetch_metric("2310.06825", "journal_ref"))["value"] == "n/a"
            get_cache().clear()
            assert (await fetch_metric("2310.06825", "doi"))["value"] == "n/a"

    @pytest.mark.asyncio
    async def test_present_journal_ref_and_doi(self) -> None:
        with patch(
            "hyperweave.connectors.arxiv.fetch_text", new_callable=AsyncMock, return_value=self.XML_WITH_OPTIONAL
        ):
            from hyperweave.connectors.arxiv import fetch_metric

            assert (await fetch_metric("2020.00001", "journal_ref"))["value"] == "Nature 583, 2020"
            get_cache().clear()
            assert (await fetch_metric("2020.00001", "doi"))["value"] == "10.1000/xyz123"


# =========================================================================
# Unified dispatcher — v0.3.12 providers
# =========================================================================


class TestDispatcherCursorPointerPins:
    """Route the three new providers + the cargo alias through the dispatcher."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_breakers()
        get_cache().clear()

    @pytest.mark.asyncio
    async def test_routes_to_crates(self) -> None:
        data = {"crate": {"max_stable_version": "1.0.0", "downloads": 5}, "versions": [{"license": "MIT"}]}
        with patch("hyperweave.connectors.rest.fetch_json", new_callable=AsyncMock, return_value=data):
            from hyperweave.connectors import fetch_metric

            result = await fetch_metric("crates", "serde", "version")
            assert result["provider"] == "crates"
            assert result["value"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_routes_to_scorecard(self) -> None:
        payload = {"score": 7.5, "checks": []}
        with patch("hyperweave.connectors.scorecard.fetch_json", new_callable=AsyncMock, return_value=payload):
            from hyperweave.connectors import fetch_metric

            result = await fetch_metric("scorecard", "tokio-rs/tokio", "score")
            assert result["provider"] == "scorecard"
            assert result["value"] == 7.5

    @pytest.mark.asyncio
    async def test_routes_to_dora(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake(url: str, **_kw: Any) -> Any:
            if "/deployments?" in url:
                return []
            if "/actions/runs" in url:
                return {"workflow_runs": []}
            return {"default_branch": "main"}

        monkeypatch.setattr("hyperweave.connectors.dora.fetch_json", fake)
        from hyperweave.connectors import fetch_metric

        result = await fetch_metric("dora", "o/r", "deploy_frequency")
        assert result["provider"] == "dora"
        assert result["value"] == 0.0
