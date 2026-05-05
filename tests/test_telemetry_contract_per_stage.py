"""Tests for the v0.2.21 contract patches.

Two new fields landed in :func:`hyperweave.telemetry.contract._assemble`:

* Per-stage ``tokens`` — total token count summed from each stage's
  ``ToolCall`` records (input + output + cache_read + cache_create).
  Drives variable-height bars in :func:`compose.bar_chart.layout_bar_chart`.
* Per-stage ``errors`` — count of tool calls with ``BLOCKED`` or ``ERROR``
  outcome in the stage. Drives error-tick markers above bars.
* Session-level ``runtime`` — identifier ("claude-code") that the receipt
  resolver's skin precedence chain reads to auto-select the matching
  ``telemetry-{runtime}`` genome JSON.

These three fields are additive: they don't change existing behavior
for any rhythm-strip / receipt code paths that don't read them, but
they unblock skin auto-detection (Phase D) and variable-height bars
(Phase B template rewrite + bar_chart wiring).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hyperweave.telemetry.contract import build_contract

SESSION_FIXTURE = Path(__file__).parent / "fixtures" / "session.jsonl"


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return build_contract(str(SESSION_FIXTURE))


# --------------------------------------------------------------------------- #
# Session-level runtime field                                                 #
# --------------------------------------------------------------------------- #


def test_session_carries_runtime_field(contract: dict[str, Any]) -> None:
    """Skin precedence chain reads session.runtime to pick the genome.

    The Claude Code parser is the only path through ``contract.py`` —
    every transcript it emits is tagged ``runtime: "claude-code"``.
    """
    assert contract["session"]["runtime"] == "claude-code"


def test_runtime_is_present_alongside_existing_session_fields(contract: dict[str, Any]) -> None:
    """Verify the new field doesn't displace existing session metadata."""
    session = contract["session"]
    for key in ("id", "start", "end", "duration_minutes", "model", "git_branch", "project_path", "runtime"):
        assert key in session, f"missing session key: {key}"


# --------------------------------------------------------------------------- #
# Per-stage tokens                                                            #
# --------------------------------------------------------------------------- #


def test_each_stage_carries_tokens(contract: dict[str, Any]) -> None:
    stages = contract["stages"]
    assert stages, "fixture should produce at least one stage"
    for s in stages:
        assert "tokens" in s
        assert isinstance(s["tokens"], int)
        assert s["tokens"] >= 0


def test_per_stage_token_sum_matches_session_total(contract: dict[str, Any]) -> None:
    """Sum of per-stage tokens should reconcile to the profile-level totals.

    Stages partition the session's tool-call timeline, so summing the
    per-stage `tokens` fields must equal the sum of input + output +
    cache_read + cache_create for every tool call.
    """
    stage_token_sum = sum(s["tokens"] for s in contract["stages"])
    profile = contract["profile"]
    expected = (
        profile["total_input_tokens"]
        + profile["total_output_tokens"]
        + profile["total_cache_read_tokens"]
        + profile["total_cache_creation_tokens"]
    )
    # Allow exact equality — tool calls are partitioned across stages
    # by the detector so the sums must match.
    assert stage_token_sum == expected


# --------------------------------------------------------------------------- #
# Per-stage errors                                                            #
# --------------------------------------------------------------------------- #


def test_each_stage_carries_errors(contract: dict[str, Any]) -> None:
    stages = contract["stages"]
    for s in stages:
        assert "errors" in s
        assert isinstance(s["errors"], int)
        assert s["errors"] >= 0


def test_per_stage_errors_reconcile_to_tool_summary(contract: dict[str, Any]) -> None:
    """Sum of per-stage errors should match the tool-summary blocked+error totals.

    Each tool call is in exactly one stage; each stage's `errors` field
    counts BLOCKED + ERROR outcomes; the tool summary aggregates the same
    outcomes across all calls. The two views must reconcile.
    """
    stage_error_sum = sum(s["errors"] for s in contract["stages"])
    tool_failure_sum = sum(t["blocked"] + t["errors"] for t in contract["tools"].values())
    assert stage_error_sum == tool_failure_sum


# --------------------------------------------------------------------------- #
# Backwards compatibility                                                     #
# --------------------------------------------------------------------------- #


def test_existing_stage_fields_still_present(contract: dict[str, Any]) -> None:
    """Phase C patches are additive: existing fields must remain intact
    so resolve_rhythm_strip and the master-card resolver keep working."""
    for s in contract["stages"]:
        for key in ("label", "dominant_class", "start", "end", "tools", "boundary_score"):
            assert key in s, f"missing pre-existing stage key: {key}"


def test_existing_session_fields_still_present(contract: dict[str, Any]) -> None:
    """Existing receipt resolver fields must remain intact."""
    for key in ("id", "start", "end", "duration_minutes", "model", "git_branch", "project_path"):
        assert key in contract["session"], f"missing pre-existing session key: {key}"
