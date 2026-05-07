"""Real-fixture sweeps that catch unmapped tools before they ship.

Pre-v0.2.23, the silent ``TOOL_CLASS_MAP.get(name, ToolClass.EXPLORE)``
fallback masked 11+ tools that Claude Code actually emits (Agent,
ToolSearch, ScheduleWakeup, Cron*, EnterWorktree, ExitWorktree, mcp__*).
Stage classification cascaded from those silent defaults — every Agent
dispatch was scored as "explore," every Cron op as "explore," etc.

These tests sweep the existing real-data fixtures, parse them, and
assert no ``unknown_tool`` warnings fire. Add a tool to
``data/telemetry/runtimes/<runtime>.yaml`` to silence a new failure.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hyperweave.telemetry.contract import build_contract

if TYPE_CHECKING:
    import pytest


def test_claude_session_fixture_has_no_unknown_tools(caplog: pytest.LogCaptureFixture) -> None:
    """Sweep the bundled Claude session fixture — every tool name must be mapped."""
    with caplog.at_level(logging.WARNING):
        build_contract("tests/fixtures/session.jsonl")
    unknowns = [r for r in caplog.records if "unknown_tool" in r.message]
    assert not unknowns, f"unmapped tools in tests/fixtures/session.jsonl: {[r.message for r in unknowns]}"
