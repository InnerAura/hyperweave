"""Tests for hyperweave.connectors; subdir-local fixtures go here (root conftest inherited)."""

import pytest


@pytest.fixture(autouse=True)
def recorded_retry_waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Retry waits are recorded, never slept — tests assert timing intent
    without wall-clock cost (the retry layer's `_sleep` seam exists for this)."""
    waits: list[float] = []

    async def _record(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("hyperweave.connectors.base._sleep", _record)
    return waits
