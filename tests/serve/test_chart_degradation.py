"""Chart route degradation under a broken upstream — the guard law's surface:
the real HTTP route, wall-clock behavior, the rendered overlay text."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from hyperweave.serve.app import app


@pytest.mark.asyncio
async def test_chart_render_returns_inside_the_deadline_under_a_hanging_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hanging socket cannot hold a chart render open: the wall-clock
    deadline cancels the fan-out in-flight and the route answers 200 with the
    truthful overlay, well inside the deadline."""
    monkeypatch.setattr("hyperweave.connectors.github._RENDER_DEADLINE_S", 0.3)

    hang = asyncio.Event()  # never set — the upstream never answers

    async def _never_answers(*args: object, **kwargs: object) -> None:
        await hang.wait()

    instance = AsyncMock()
    instance.get = _never_answers
    with patch("hyperweave.connectors.base.get_client", return_value=instance):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            start = time.monotonic()
            response = await client.get("/v1/chart/stars/acme/hanging-upstream-probe/primer.static")
            elapsed = time.monotonic() - start

    assert response.status_code == 200
    # Generous CI margin: the bound guards against the ~45s multi-attempt hang
    # class, not compose speed — a cold runner's first compose (font subsetting,
    # template env build) can take seconds on its own.
    assert elapsed < 10.0, f"render held open {elapsed:.1f}s under a hanging upstream"
    assert "DATA UNAVAILABLE" in response.text
