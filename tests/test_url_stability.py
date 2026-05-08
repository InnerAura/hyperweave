"""URL byte-stability tests — backward-compat guards for embedded URLs.

The HyperWeave testing stack has three layers, each with one job:

1. **Assertion tests** (``test_badge_layout.py``, ``test_badge_mode.py``)
   answer "is the output correct?" via geometric math and DOM structure
   checks. They catch *what changed and whether it's right*.
2. **The proofset script** (``scripts/generate_proofset.py``) renders 129+
   artifacts to ``outputs/`` for visual inspection. It catches *whether
   it looks right* via the human eye.
3. **This file** answers ONE question: did we accidentally break an
   embedded URL someone depends on? The cases here are URLs known to be
   referenced in the wild (Muhamed-abdelmoneim's
   ``/v1/divider/band/chrome.static`` cited 12+ times in his GitHub
   README). They MUST stay byte-equal across releases.

Why no observational snapshots? Snapshot tests can only flag "something
changed" — they can't tell you *what* or *whether the change is correct*.
Observational snapshots create review tax (every intentional change
forces a snapshot regen) without offering correctness guarantees the
assertion tests don't already provide. Keep this list tight: protective
contracts only.

First run on a clean checkout auto-bootstraps: any missing snapshot is
written from the current rendering and the test xfails with a "captured
new snapshot" message. Re-running asserts against the captured baseline.

Volatile pattern normalization: ``hw-[0-9a-f]{6,}`` UUID fragments and
ISO 8601 timestamps are scrubbed before comparison so the same artifact
rendered twice compares equal even though its embedded IDs differ.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from hyperweave.serve.app import app

SNAPSHOT_DIR = Path(__file__).parent / "snapshots" / "url_stability"

# Short UUID fragments embedded in element IDs/classes (e.g., hw-ebd30b0c-title).
_HW_UID_RE = re.compile(r"hw-[0-9a-f]{6,}")
# Full UUID v4 inside data-hw-id, data-hw-contract, hw:artifact id (no hw- prefix).
_FULL_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
# ISO 8601 timestamps that may appear in metadata (created/created_at).
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
# Package version strings — `__version__` is dynamically computed from git
# tags by hatch-vcs/setuptools-scm, so the same code produces "0.2.20"
# locally (no tag) and "0.2.25" in CI (tagged release). Normalize all
# semver-like version strings in metadata so backward-compat snapshots
# track artifact STRUCTURE, not the version that happened to render them.
_VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9a-zA-Z.\-]+)?")


def _normalize(svg: str) -> str:
    """Scrub volatile fragments so the same artifact rendered twice compares equal."""
    svg = _HW_UID_RE.sub("hw-UID", svg)
    svg = _FULL_UUID_RE.sub("UUID", svg)
    svg = _TS_RE.sub("TIMESTAMP", svg)
    svg = _VERSION_RE.sub("VERSION", svg)
    return svg


# Protective-only. Each case: (snapshot_filename, url_path).
# These URLs MUST remain byte-equal across releases.
#
# - divider_band_chrome_static: Muhamed-abdelmoneim's embedded URL,
#   referenced 12+ times in his GitHub README. Load-bearing.
# - icon_github_chrome_static: bare-genome icon URL; anchors a frame
#   category that doesn't load expression.css and shouldn't drift on
#   any badge or strip work.
PROTECTIVE_CASES: list[tuple[str, str]] = [
    ("divider_band_chrome_static.svg", "/v1/divider/band/chrome.static"),
    ("icon_github_chrome_static.svg", "/v1/icon/github/chrome.static"),
]


@pytest.fixture()
async def client() -> Any:
    """Async test client wrapping the FastAPI app via ASGI transport."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _fetch_normalized(client: AsyncClient, url: str) -> str:
    resp = await client.get(url)
    assert resp.status_code == 200, f"GET {url} -> {resp.status_code}: {resp.text[:300]}"
    return _normalize(resp.text)


async def _assert_or_capture(client: AsyncClient, snapshot_name: str, url: str, *, kind: str) -> None:
    """Compare against snapshot, or auto-capture on first run.

    On first run the snapshot file doesn't exist yet — write it and xfail
    with a clear message so the run isn't silently green. Subsequent runs
    assert byte-equality after normalization.
    """
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / snapshot_name
    actual = await _fetch_normalized(client, url)

    if not path.exists():
        path.write_text(actual, encoding="utf-8")
        pytest.xfail(f"Captured new {kind} snapshot at {path.name}; re-run to assert.")

    expected = path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"\n{kind.upper()} URL {url} drifted from {snapshot_name}.\n"
        f"If this drift is intentional (v0.2.25 bugfix), document the diff in\n"
        f"docs/decisions/v0225-snapshot-changes.md and regenerate the snapshot.\n"
        f"If unintentional (regression), restore byte-equality before merging.\n"
    )


@pytest.mark.parametrize("name,url", PROTECTIVE_CASES, ids=[c[0] for c in PROTECTIVE_CASES])
async def test_protective_url_byte_stable(client: AsyncClient, name: str, url: str) -> None:
    """Protective URLs must render byte-equal across releases."""
    await _assert_or_capture(client, name, url, kind="protective")
