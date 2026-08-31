"""Frozen fixture mode: HW_PROOFSET_FROZEN=1 makes the proofset cache read-only.

The proofset fixture (`tests/fixtures/proofset_data.json`) is rewritten on
every successful live fetch — which silently overwrites a locally modified
fixture whenever the gate runs. Frozen mode covers BOTH fetch helpers and the
writer: no fetcher is ever called, no byte of the fixture file changes.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

import pytest
from scripts.examples.harness import FIXTURE_PATH, fetch_or_cache, frozen_fixtures, save_fixtures
from scripts.examples.proofset import _fetch_snapshot_or_cache


@pytest.fixture()
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HW_PROOFSET_FROZEN", "1")
    assert frozen_fixtures()


class _Boom:
    """A fetcher that fails the test if the network path is ever taken."""

    called = False

    async def __call__(self) -> dict[str, Any]:
        type(self).called = True
        raise AssertionError("frozen mode must never call a fetcher")


def test_fetch_or_cache_reads_cache_without_fetching(frozen: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_fetch(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("frozen mode must never import/call fetch_metric")

    monkeypatch.setattr("hyperweave.connectors.fetch_metric", _no_fetch)
    fixtures = {"gh:acme/widgets.stars": {"value": 42, "fetched_at": 0.0}}
    value = asyncio.run(fetch_or_cache("gh", "acme/widgets", "stars", fixtures))
    assert value == 42
    with pytest.raises(RuntimeError, match="HW_PROOFSET_FROZEN"):
        asyncio.run(fetch_or_cache("gh", "acme/widgets", "forks", fixtures))


def test_snapshot_fetch_reads_cache_without_fetching(frozen: None) -> None:
    boom = _Boom()
    fixtures: dict[str, Any] = {"snap": {"value": {"a": 1}, "fetched_at": 0.0}}
    result = asyncio.run(_fetch_snapshot_or_cache(fixtures, "snap", "label", boom))
    assert result == {"a": 1}
    assert not _Boom.called
    assert fixtures["snap"]["value"] == {"a": 1}
    with pytest.raises(RuntimeError, match="HW_PROOFSET_FROZEN"):
        asyncio.run(_fetch_snapshot_or_cache(fixtures, "missing", "label", boom))
    assert not _Boom.called


def test_save_fixtures_refuses_writes_and_preserves_bytes(frozen: None) -> None:
    before = hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest() if FIXTURE_PATH.exists() else None
    save_fixtures({"poison": {"value": 1, "fetched_at": 0.0}})
    after = hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest() if FIXTURE_PATH.exists() else None
    assert before == after
