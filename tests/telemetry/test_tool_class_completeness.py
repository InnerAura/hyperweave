"""Real-fixture sweeps that catch silent registry fallbacks before they ship.

Pre-v0.2.23, the silent ``TOOL_CLASS_MAP.get(name, ToolClass.EXPLORE)``
fallback masked 11+ tools that Claude Code actually emits (Agent,
ToolSearch, ScheduleWakeup, Cron*, EnterWorktree, ExitWorktree, mcp__*).
Stage classification cascaded from those silent defaults — every Agent
dispatch was scored as "explore," every Cron op as "explore," etc.

These tests sweep the existing real-data fixtures, parse them, and
assert no ``unknown_tool`` warnings fire. Add a tool to
``data/telemetry/runtimes/<runtime>.yaml`` to silence a new failure.

The sweep covers EVERY runtime, and each runtime is pinned at more than
one transcript vintage. Claude was swept from v0.2.23 while Codex went
unenrolled, so when Codex renamed its shell to ``exec`` the whole class
silently re-entered the EXPLORE fallback this file exists to prevent —
736 of 744 calls across a month of transcripts. A guard that watches one
axis of a two-axis surface reports green on a broken half.
"""

from __future__ import annotations

import logging

import pytest

from hyperweave.telemetry.contract import build_contract
from tests.conftest import FIXTURES_DIR

_SESSION_FIXTURE = str(FIXTURES_DIR / "session.jsonl")
# Codex is pinned at two vintages: the 2026-05 shape (prose on
# `event_msg/user_message`, shell named `exec_command`) and the current one
# (prose on `response_item/message`, shell named `exec`). Both must parse —
# the parser picks the channel per transcript, it does not migrate.
_CODEX_LEGACY_FIXTURE = str(FIXTURES_DIR / "codex_session.jsonl")
_CODEX_FIXTURE = str(FIXTURES_DIR / "codex_session_v2.jsonl")

_ALL_FIXTURES = (_SESSION_FIXTURE, _CODEX_LEGACY_FIXTURE, _CODEX_FIXTURE)


@pytest.mark.parametrize("fixture", _ALL_FIXTURES)
def test_fixture_has_no_unknown_tools(fixture: str, caplog: pytest.LogCaptureFixture) -> None:
    """Sweep every bundled transcript — each runtime, each vintage, all tools mapped."""
    with caplog.at_level(logging.WARNING):
        build_contract(fixture)
    unknowns = [r for r in caplog.records if "unknown_tool" in r.message]
    assert not unknowns, f"unmapped tools in {fixture}: {[r.message for r in unknowns]}"


@pytest.mark.parametrize("fixture", _ALL_FIXTURES)
def test_fixture_reports_human_turns(fixture: str) -> None:
    """Every vintage must yield human turns.

    Turn counting is channel-sensitive: read the wrong one and the receipt
    reports ``turns: 0`` while the transcript holds a full session. That is
    what shipped for Codex — the parser watched a channel Codex had stopped
    emitting, and nothing failed because nothing asserted a floor.
    """
    contract = build_contract(fixture)
    assert contract["user_events"], f"no user events parsed from {fixture}"
    assert contract["profile"]["turns"] > 0, f"zero turns from {fixture}"


@pytest.mark.parametrize("fixture", _ALL_FIXTURES)
def test_fixture_models_are_priced(fixture: str, caplog: pytest.LogCaptureFixture) -> None:
    """Every model a fixture names must have its own rate, not the default.

    Same silent-fallback shape as ``unknown_tool``, one layer over: an unpriced
    model still renders a receipt, it just bills at a guess. Add the model to
    ``data/telemetry/model-pricing.yaml`` to silence a new failure.
    """
    with caplog.at_level(logging.WARNING):
        build_contract(fixture)
    unknowns = [r for r in caplog.records if "unknown_model" in r.message]
    assert not unknowns, f"unpriced models in {fixture}: {[r.message for r in unknowns]}"


def test_codex_agents_preamble_is_not_a_turn() -> None:
    """Codex injects the repo's AGENTS.md as a ``role: user`` message.

    It is machine-authored context, not a human turn. It also arrives FIRST,
    and the first user prompt is the receipt's filename slug source — so
    letting it through both inflates the turn count and names the artifact
    after the instruction file.
    """
    contract = build_contract(_CODEX_FIXTURE)
    first = contract["user_events"][0]["preview"]
    assert "AGENTS.md instructions" not in first
    assert "<INSTRUCTIONS>" not in first
    assert first.startswith("AUDIT ONLY:")
