"""Tests for the ``receipt/1`` payload assembler and parser extensions.

Covers the data contract that the v3 receipt embeds (``hw:payload``) and the
resolver consumes:

* token identities (working = in + out; total = in+out+cache_read+cache_write)
* cost-by-model grouping, dominant selection, cost_pct, role attribution
* the ``/compact`` turn-count fix (compact-summary messages are not turns)
* active_min derivation (turn-duration when present, else min(stage, wall-clock))
* context-event modelling (resets at the right minutes, peak, window)
* payload discipline (compact, single-line, data-only — no display strings)
* field-name round-trip (specimen payload ↔ resolver-readable shape)

Fixtures:
  * ``session.jsonl``          — single-model Claude Code session, no resets
  * ``synthetic_session.jsonl``— /rename envelope + corrections (turn-count edges)
  * ``compact_session.jsonl``  — an ``isCompactSummary`` auto-compaction reset
  * ``codex_session.jsonl``    — Codex (real window + occupancy series)
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from hyperweave.telemetry.context import (
    CONTEXT_NOTE,
    DEFAULT_CONTEXT_WINDOW,
    build_context_summary,
    window_for_model,
)
from hyperweave.telemetry.contract import build_receipt_contract
from hyperweave.telemetry.models import (
    AgentSpan,
    CommandEvent,
    CommandResetKind,
    SessionTelemetry,
    SessionTotals,
    ToolCall,
    ToolClass,
    ToolOutcome,
    ToolSummary,
)
from hyperweave.telemetry.receipt_payload import build_receipt_payload
from tests.conftest import FIXTURES_DIR

if TYPE_CHECKING:
    from pathlib import Path

SESSION_FIXTURE = FIXTURES_DIR / "session.jsonl"
SYNTHETIC_FIXTURE = FIXTURES_DIR / "synthetic_session.jsonl"
COMPACT_FIXTURE = FIXTURES_DIR / "compact_session.jsonl"
CODEX_FIXTURE = FIXTURES_DIR / "codex_session.jsonl"

_BASE_TS = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Builders for hand-constructed telemetry (unit-level, no JSONL)              #
# --------------------------------------------------------------------------- #


def _call(
    name: str,
    model: str,
    *,
    tin: int = 0,
    tout: int = 0,
    cread: int = 0,
    ccreate: int = 0,
    tool_class: ToolClass = ToolClass.EXPLORE,
    outcome: ToolOutcome = ToolOutcome.SUCCESS,
    minute: int = 0,
) -> ToolCall:
    return ToolCall(
        tool_name=name,
        tool_id=f"{name}-{minute}-{model}",
        tool_class=tool_class,
        timestamp=_BASE_TS + timedelta(minutes=minute),
        tokens_input=tin,
        tokens_output=tout,
        cache_read_tokens=cread,
        cache_create_tokens=ccreate,
        outcome=outcome,
        model=model,
    )


def _telemetry(
    calls: list[ToolCall],
    *,
    model: str = "claude-opus-4-8",
    agents: list[AgentSpan] | None = None,
    command_events: list[CommandEvent] | None = None,
    context_window: int = 0,
    peak: int = 0,
    turn_duration_minutes: float | None = None,
    duration_minutes: float = 0.0,
    user_messages: int = 0,
) -> SessionTelemetry:
    summary: dict[str, ToolSummary] = {}
    totals = SessionTotals(
        total_calls=len(calls),
        total_user_messages=user_messages,
    )
    for c in calls:
        s = summary.setdefault(c.tool_name, ToolSummary(tool_name=c.tool_name, tool_class=c.tool_class))
        s.call_count += 1
        s.total_input_tokens += c.tokens_input
        s.total_output_tokens += c.tokens_output
        s.total_cache_read += c.cache_read_tokens
        s.total_cache_create += c.cache_create_tokens
        if c.outcome is ToolOutcome.ERROR:
            s.error_count += 1
        elif c.outcome is ToolOutcome.BLOCKED:
            s.blocked_count += 1
        else:
            s.success_count += 1
        totals.total_input_tokens += c.tokens_input
        totals.total_output_tokens += c.tokens_output
        totals.total_cache_read += c.cache_read_tokens
        totals.total_cache_create += c.cache_create_tokens
    return SessionTelemetry(
        session_id="unit-001",
        project_path="/repo",
        model=model,
        runtime="claude-code",
        timestamp=_BASE_TS,
        duration_minutes=duration_minutes,
        turn_duration_minutes=turn_duration_minutes,
        context_window=context_window,
        peak_context_tokens=peak,
        tool_calls=calls,
        agents=agents or [],
        command_events=command_events or [],
        tool_summary=summary,
        totals=totals,
    )


# --------------------------------------------------------------------------- #
# Token identities                                                            #
# --------------------------------------------------------------------------- #


class TestTokenIdentities:
    def test_working_equals_in_plus_out(self) -> None:
        t = _telemetry([_call("Read", "claude-opus-4-8", tin=100, tout=40, cread=900, ccreate=10)])
        p = build_receipt_payload(t)
        tok = p["tokens"]
        assert tok["working"] == tok["in"] + tok["out"]
        assert tok["working"] == 140

    def test_total_is_four_field_sum(self) -> None:
        t = _telemetry([_call("Read", "claude-opus-4-8", tin=100, tout=40, cread=900, ccreate=60)])
        tok = build_receipt_payload(t)["tokens"]
        assert tok["total"] == tok["in"] + tok["out"] + tok["cache_read"] + tok["cache_write"]
        assert tok["total"] == 1100

    def test_cache_write_maps_to_cache_create(self) -> None:
        t = _telemetry([_call("Edit", "claude-opus-4-8", ccreate=4390, cread=349000, tin=400800, tout=23930)])
        tok = build_receipt_payload(t)["tokens"]
        assert tok["cache_write"] == 4390
        assert tok["cache_read"] == 349000

    def test_specimen_working_identity(self) -> None:
        """The specimen's working = 157500 + 867300 = 1024800 (in + out)."""
        t = _telemetry([_call("X", "claude-opus-4-8", tin=157500, tout=867300)])
        assert build_receipt_payload(t)["tokens"]["working"] == 1024800


# --------------------------------------------------------------------------- #
# Cost-by-model grouping, dominant, cost_pct, role                            #
# --------------------------------------------------------------------------- #


class TestCostByModel:
    def test_single_model_is_full_cost_main_thread(self) -> None:
        t = _telemetry([_call("Edit", "claude-opus-4-8", tin=1000, tout=1000)])
        p = build_receipt_payload(t)
        assert len(p["models"]) == 1
        m = p["models"][0]
        assert m["role"] == "main thread"
        assert m["cost_pct"] == 100
        assert m["name"] == "opus-4.8"
        assert p["dominant"] == "opus-4.8"

    def test_multi_model_main_thread_switch_both_main(self) -> None:
        # Two models on the MAIN thread (mid-session model switch), neither tagged
        # is_subagent → BOTH read "main thread" (origin, not dominance — the v0.4
        # fix; previously the non-dominant one was mislabelled a subagent).
        calls = [
            _call("Edit", "claude-opus-4-8", tin=2_000_000, tout=2_000_000),
            _call("Read", "claude-sonnet-4-6", tin=100_000, tout=100_000),
        ]
        t = _telemetry(calls, model="claude-opus-4-8")
        p = build_receipt_payload(t)
        names = [m["name"] for m in p["models"]]
        assert names[0] == "opus-4.8"  # sorted by cost descending
        assert p["dominant"] == "opus-4.8"
        opus = next(m for m in p["models"] if m["name"] == "opus-4.8")
        sonnet = next(m for m in p["models"] if m["name"] == "sonnet-4.6")
        assert opus["role"] == "main thread"
        assert sonnet["role"] == "main thread"
        assert all(isinstance(m["cost_pct"], int) for m in p["models"])
        assert abs(sum(m["cost_pct"] for m in p["models"]) - 100) <= 1

    def test_role_counts_distinct_subagent_spans(self) -> None:
        """A subagent-only model (is_subagent calls) with N spans → 'N subagents'."""
        sub_call = _call("Read", "claude-haiku-4-5", tin=500_000, tout=500_000)
        sub_call.is_subagent = True  # folded from a sidechain, not the main thread
        calls = [_call("Edit", "claude-opus-4-8", tin=1_000_000, tout=1_000_000), sub_call]
        agents = [
            AgentSpan(agent_id="a1", model="claude-haiku-4-5"),
            AgentSpan(agent_id="a2", model="claude-haiku-4-5"),
        ]
        t = _telemetry(calls, model="claude-opus-4-8", agents=agents)
        p = build_receipt_payload(t)
        opus = next(m for m in p["models"] if m["name"] == "opus-4.8")
        haiku = next(m for m in p["models"] if m["name"] == "haiku-4.5")
        assert opus["role"] == "main thread"
        assert haiku["role"] == "2 subagents"  # by origin + span count, not dominance

    def test_dated_subagent_model_label_normalized(self) -> None:
        """A dated model id (a subagent's YYYYMMDD snapshot) reads like the undated
        main-thread ids — 'haiku-4.5', not 'haiku-4-5.20251001'."""
        sub_call = _call("Read", "claude-haiku-4-5-20251001", tin=100_000, tout=100_000)
        sub_call.is_subagent = True
        t = _telemetry(
            [_call("Edit", "claude-opus-4-8", tin=1_000_000, tout=1_000_000), sub_call],
            model="claude-opus-4-8",
            agents=[AgentSpan(agent_id="a1", model="claude-haiku-4-5-20251001")],
        )
        p = build_receipt_payload(t)
        assert any(m["name"] == "haiku-4.5" for m in p["models"])
        assert not any("20251001" in str(m["name"]) for m in p["models"])

    def test_cost_pct_is_percent_of_total_cost(self) -> None:
        # Equal-cost models → ~50/50.
        calls = [
            _call("A", "claude-opus-4-8", tin=1_000_000, tout=0),
            _call("B", "claude-opus-4-7", tin=1_000_000, tout=0),
        ]
        t = _telemetry(calls, model="claude-opus-4-8")
        p = build_receipt_payload(t)
        assert {m["cost_pct"] for m in p["models"]} == {50}

    def test_cost_usd_rounds_to_cents(self) -> None:
        t = _telemetry([_call("X", "claude-opus-4-8", tin=350_000, tout=0)])
        p = build_receipt_payload(t)
        # 350000 * 5/1e6 = 1.75 exactly; ensure 2-decimal rounding.
        assert p["cost_usd"] == 1.75
        assert p["models"][0]["cost_usd"] == 1.75


# --------------------------------------------------------------------------- #
# Turn count — the /compact fix                                               #
# --------------------------------------------------------------------------- #


class TestTurnCount:
    def test_compact_summary_not_counted_as_turn(self) -> None:
        """compact_session.jsonl has 2 human prose turns + 1 isCompactSummary.

        The summary message carries prose, not an envelope, so the pre-fix
        tally counted it. Turns must read 2, never 3.
        """
        p = build_receipt_contract(str(COMPACT_FIXTURE))
        assert p["turns"] == 2

    def test_turns_exclude_command_envelopes(self) -> None:
        """synthetic has a /rename envelope + stdout that are not turns."""
        p = build_receipt_contract(str(SYNTHETIC_FIXTURE))
        assert p["turns"] == 5

    def test_turns_do_not_include_assistant_messages(self) -> None:
        """turns counts human prose only — never assistant turns.

        session.jsonl has many assistant messages but 6 human prompts.
        """
        p = build_receipt_contract(str(SESSION_FIXTURE))
        assert p["turns"] == 6

    def test_token_totals_unaffected_by_turn_fix(self) -> None:
        """Excluding the compact summary from turns must not touch token sums."""
        p = build_receipt_contract(str(COMPACT_FIXTURE))
        tok = p["tokens"]
        # 50000+60000+12000+18000 input across 4 assistant turns.
        assert tok["in"] == 140000
        assert tok["working"] == tok["in"] + tok["out"]


# --------------------------------------------------------------------------- #
# active_min                                                                  #
# --------------------------------------------------------------------------- #


class TestActiveMinutes:
    def test_prefers_turn_duration_when_present(self) -> None:
        calls = [
            _call("A", "claude-opus-4-8", minute=0),
            _call("B", "claude-opus-4-8", minute=200),  # wall-clock 200m
        ]
        t = _telemetry(calls, turn_duration_minutes=42.0)
        # turn_duration (42) << wall-clock (200) → 42.
        assert build_receipt_payload(t)["active_min"] == 42

    def test_falls_back_to_min_stage_wall_clock(self) -> None:
        # No turn_duration, no stages → falls back to duration_minutes.
        t = _telemetry([_call("A", "claude-opus-4-8")], duration_minutes=17.0)
        assert build_receipt_payload(t)["active_min"] == 17

    def test_turn_duration_capped_at_wall_clock(self) -> None:
        calls = [_call("A", "claude-opus-4-8", minute=0), _call("B", "claude-opus-4-8", minute=10)]
        # Absurd turn_duration must not exceed wall-clock span when stages exist.
        t = _telemetry(calls, turn_duration_minutes=9999.0)
        from hyperweave.telemetry.stages import detect_stages

        t.stages = detect_stages(t.tool_calls)
        if t.stages:
            assert build_receipt_payload(t)["active_min"] <= 10


# --------------------------------------------------------------------------- #
# Session reconstruction (main + subagent sidechains)                         #
# --------------------------------------------------------------------------- #


class TestSessionStitching:
    def test_stitch_folds_subagent_sidechain(self, tmp_path: Path) -> None:
        """A Claude main session + a ``<stem>/subagents/agent-*.jsonl`` child:
        the child's cost/calls fold into the parent, but the occupancy curve +
        turns stay main-thread (subagents run in their own context window)."""
        main = tmp_path / "sess.jsonl"
        shutil.copy(SESSION_FIXTURE, main)
        before = build_receipt_contract(str(main))  # no subdir yet → no stitch

        subdir = tmp_path / "sess" / "subagents"
        subdir.mkdir(parents=True)
        shutil.copy(SESSION_FIXTURE, subdir / "agent-deadbeef00.jsonl")
        after = build_receipt_contract(str(main))  # now stitches the child

        # The child is an exact copy → calls double; cost grows (folded spend).
        assert before["calls"] > 0
        assert after["calls"] == 2 * before["calls"]
        assert after["cost_usd"] >= before["cost_usd"]
        # Occupancy curve is main-thread-only — NOT folded (subagents have their
        # own context window).
        assert after["context"]["peak_ctx"] == before["context"]["peak_ctx"]
        assert after["context"]["window"] == before["context"]["window"]
        assert after["context"]["events"] == before["context"]["events"]
        # Turns count main-thread prompts only — a subagent is not a user turn.
        assert after["turns"] == before["turns"]


# --------------------------------------------------------------------------- #
# Context-event modelling                                                     #
# --------------------------------------------------------------------------- #


class TestContextModelling:
    def test_window_for_model_default(self) -> None:
        # Real 200K-window models (and unknown ids / None) resolve to the default.
        assert window_for_model("claude-haiku-4-5") == DEFAULT_CONTEXT_WINDOW
        assert window_for_model("claude-sonnet-4-5") == DEFAULT_CONTEXT_WINDOW
        assert window_for_model("some-unknown-model") == DEFAULT_CONTEXT_WINDOW
        assert window_for_model(None) == DEFAULT_CONTEXT_WINDOW

    def test_window_for_model_extended(self) -> None:
        # Explicit 1M markers AND doc-sourced 1M-baseline models (opus 4.x, fable).
        assert window_for_model("claude-opus-4-8[1m]") == 1_000_000
        assert window_for_model("claude-opus-4-8-1m") == 1_000_000
        assert window_for_model("claude-opus-4-8") == 1_000_000
        assert window_for_model("claude-fable-5") == 1_000_000

    def test_summary_carries_verbatim_note(self) -> None:
        t = _telemetry([_call("A", "claude-opus-4-8")], context_window=200000, peak=50000)
        assert build_context_summary(t)["note"] == CONTEXT_NOTE

    def test_events_emit_min_cmd_to(self) -> None:
        ev = CommandEvent(
            kind=CommandResetKind.COMPACT,
            timestamp=_BASE_TS + timedelta(minutes=31),
            occupancy_before=196000,
            occupancy_after=38000,
        )
        t = _telemetry([_call("A", "claude-opus-4-8")], command_events=[ev], context_window=200000, peak=196000)
        ctx = build_context_summary(t)
        assert ctx["events"] == [{"min": 31, "cmd": "compact", "to": 38000}]

    def test_peak_clamped_to_window(self) -> None:
        # Modelled peak can momentarily exceed the nominal window.
        t = _telemetry([_call("A", "claude-opus-4-8")], context_window=200000, peak=210000)
        assert build_context_summary(t)["peak_ctx"] == 200000

    def test_window_falls_back_to_model_when_unset(self) -> None:
        # context_window unset (0) → fall back to the model's resolved window:
        # 1M for a 1M-baseline model, the 200K default for a 200K one.
        t = _telemetry([_call("A", "claude-opus-4-8")], model="claude-opus-4-8", context_window=0, peak=10000)
        assert build_context_summary(t)["window"] == 1_000_000
        t2 = _telemetry([_call("A", "claude-haiku-4-5")], model="claude-haiku-4-5", context_window=0, peak=10000)
        assert build_context_summary(t2)["window"] == DEFAULT_CONTEXT_WINDOW

    def test_span_min_covers_wall_clock_not_active(self) -> None:
        """span_min is the elapsed wall-clock span — it reaches a reset logged far
        past the active-work sum (a session resumed across days), so the burn
        curve's x-axis covers every event instead of crushing them on the rail."""
        ev = CommandEvent(
            kind=CommandResetKind.AUTO,
            timestamp=_BASE_TS + timedelta(minutes=8461),
            occupancy_before=999_000,
            occupancy_after=90_000,
        )
        t = _telemetry(
            [_call("A", "claude-opus-4-8")],
            command_events=[ev],
            context_window=1_000_000,
            peak=999_000,
            duration_minutes=648.0,  # active-work sum ≪ the 8461-min wall-clock span
        )
        ctx = build_context_summary(t)
        assert ctx["span_min"] >= 8461
        assert ctx["events"][0]["min"] == 8461

    def test_errors_are_main_thread_error_outcomes_only(self) -> None:
        """``errors`` (and ``context.error_min``) count main-thread ERROR outcomes
        only: BLOCKED is a permission/hook denial, not a failure; a subagent
        erroring in its own context is not an event on the main-thread timeline."""
        main_err = _call("Bash", "claude-opus-4-8")
        main_err.outcome = ToolOutcome.ERROR
        blocked = _call("Read", "claude-opus-4-8")
        blocked.outcome = ToolOutcome.BLOCKED
        sub_err = _call("Edit", "claude-haiku-4-5")
        sub_err.outcome = ToolOutcome.ERROR
        sub_err.is_subagent = True
        ok = _call("Write", "claude-opus-4-8")  # SUCCESS
        t = _telemetry([main_err, blocked, sub_err, ok], model="claude-opus-4-8")
        p = build_receipt_payload(t)
        # Only the one main-thread ERROR — not BLOCKED, not the subagent error.
        assert p["errors"] == 1
        assert len(p["context"]["error_min"]) == 1

    def test_error_count_reconciles_across_surfaces(self) -> None:
        """The three error surfaces count the identical set: the per-tool badges
        SUM to the header ``errors``, which equals the number of curve ticks
        (``context.error_min``). BLOCKED + subagent errors count on none of them."""
        calls = []
        for tool in ("Edit", "Edit", "Bash"):  # 3 genuine main-thread errors
            c = _call(tool, "claude-opus-4-8")
            c.outcome = ToolOutcome.ERROR
            calls.append(c)
        blk = _call("Read", "claude-opus-4-8")
        blk.outcome = ToolOutcome.BLOCKED  # a denial — not an error
        sub = _call("Edit", "claude-haiku-4-5")
        sub.outcome = ToolOutcome.ERROR
        sub.is_subagent = True  # subagent error — off the main-thread timeline
        calls += [blk, sub, _call("Write", "claude-opus-4-8")]
        t = _telemetry(calls, model="claude-opus-4-8")
        p = build_receipt_payload(t)
        badge_sum = sum(int(tool.get("err", 0)) for tool in p["tools"])
        assert p["errors"] == 3
        assert badge_sum == p["errors"]
        assert len(p["context"]["error_min"]) == p["errors"]

    def test_compact_fixture_detects_auto_reset_at_right_minute(self) -> None:
        """compact_session.jsonl: a lone isCompactSummary at 10:30 (start 10:00,
        no adjacent /compact command) → an AUTO reset at min 30."""
        p = build_receipt_contract(str(COMPACT_FIXTURE))
        events = p["context"]["events"]
        assert len(events) == 1
        assert events[0]["cmd"] == "auto"
        assert events[0]["min"] == 30
        # to = first post-reset turn occupancy: 12000+2000+24000 = 38000.
        assert events[0]["to"] == 38000

    def test_codex_reports_real_window(self) -> None:
        """Codex token_count events carry model_context_window — use it."""
        p = build_receipt_contract(str(CODEX_FIXTURE))
        assert p["context"]["window"] == 258400

    def test_codex_peak_is_per_turn_not_cumulative(self) -> None:
        """Codex occupancy reads ``last_token_usage`` (current-turn context), NOT
        ``total_token_usage`` (cumulative). The fixture's per-turn peak is 76799;
        the cumulative total reaches 349493 (> the 258400 window) — using it would
        clamp every codex curve to the ceiling and (monotonic) defeat reset
        detection."""
        p = build_receipt_contract(str(CODEX_FIXTURE))
        peak = p["context"]["peak_ctx"]
        assert peak == 76799, f"expected per-turn peak 76799, got {peak}"
        assert peak < p["context"]["window"]  # not pegged to the ceiling

    def test_no_resets_yields_empty_events(self) -> None:
        p = build_receipt_contract(str(SESSION_FIXTURE))
        assert p["context"]["events"] == []


# --------------------------------------------------------------------------- #
# Payload discipline — compact, single-line, data-only                        #
# --------------------------------------------------------------------------- #


class TestPayloadDiscipline:
    @pytest.fixture(scope="class")
    def payload(self) -> dict[str, object]:
        return build_receipt_contract(str(SESSION_FIXTURE))

    def test_carries_cost_basis_and_estimate(self, payload: dict[str, object]) -> None:
        assert payload["cost_basis"] == "public per-token rates"
        assert payload["estimate"] is True

    def test_serializes_compact_single_line(self, payload: dict[str, object]) -> None:
        compact = json.dumps(payload, separators=(",", ":"))
        assert "\n" not in compact
        # Compact separators: no ", " or ": " spacing leaks.
        assert ", " not in compact
        assert ": " not in compact

    def test_no_currency_symbols(self, payload: dict[str, object]) -> None:
        compact = json.dumps(payload, separators=(",", ":"))
        assert "$" not in compact

    def test_no_interpunct_or_percent_labels(self, payload: dict[str, object]) -> None:
        compact = json.dumps(payload, separators=(",", ":"))
        assert "·" not in compact  # interpunct ·
        assert "% " not in compact  # "73% spend" style labels
        assert "spend" not in compact

    def test_no_comma_grouped_numerals(self, payload: dict[str, object]) -> None:
        """Numbers are raw ints — no '262,400,000' thousands separators.

        Within the compact JSON, a comma only ever separates elements; a
        comma immediately flanked by digits would be a grouped numeral.
        """
        compact = json.dumps(payload, separators=(",", ":"))
        import re

        assert not re.search(r"\d,\d", compact), "grouped numeral leaked into payload"

    def test_cost_values_are_numbers_not_strings(self, payload: dict[str, object]) -> None:
        assert isinstance(payload["cost_usd"], int | float)
        for m in payload["models"]:
            assert isinstance(m["cost_usd"], int | float)
            assert isinstance(m["cost_pct"], int)


# --------------------------------------------------------------------------- #
# Sparse tools[] convention                                                   #
# --------------------------------------------------------------------------- #


class TestSparseTools:
    def test_token_bearing_tool_carries_tok_and_class(self) -> None:
        t = _telemetry([_call("Edit", "claude-opus-4-8", tin=1000, tout=200, tool_class=ToolClass.MUTATE)])
        tools = build_receipt_payload(t)["tools"]
        edit = next(x for x in tools if x["name"] == "Edit")
        assert edit["tok"] == 1200
        assert edit["class"] == "mutate"
        assert edit["calls"] == 1
        assert "err" not in edit  # no errors → no err key

    def test_tail_tool_omits_tok_and_class(self) -> None:
        """A zero-token tool carries only name + calls (the sparse tail)."""
        t = _telemetry([_call("TaskUpdate", "claude-opus-4-8", tool_class=ToolClass.COORDINATE)])
        tools = build_receipt_payload(t)["tools"]
        tu = next(x for x in tools if x["name"] == "TaskUpdate")
        assert tu == {"name": "TaskUpdate", "calls": 1}

    def test_err_emitted_only_when_nonzero(self) -> None:
        calls = [
            _call("ExitPlanMode", "claude-opus-4-8", outcome=ToolOutcome.ERROR),
            _call("ExitPlanMode", "claude-opus-4-8", outcome=ToolOutcome.SUCCESS),
        ]
        t = _telemetry(calls)
        tools = build_receipt_payload(t)["tools"]
        epm = next(x for x in tools if x["name"] == "ExitPlanMode")
        assert epm["err"] == 1
        assert "tok" not in epm  # zero tokens → no tok
        assert epm == {"name": "ExitPlanMode", "calls": 2, "err": 1}

    def test_tools_ordered_by_token_spend_descending(self) -> None:
        calls = [
            _call("Small", "claude-opus-4-8", tin=10),
            _call("Big", "claude-opus-4-8", tin=10000),
            _call("Mid", "claude-opus-4-8", tin=500),
        ]
        t = _telemetry(calls)
        names = [x["name"] for x in build_receipt_payload(t)["tools"]]
        assert names == ["Big", "Mid", "Small"]


# --------------------------------------------------------------------------- #
# Field-name round-trip (specimen ↔ resolver-readable)                        #
# --------------------------------------------------------------------------- #


class TestFieldNameRoundTrip:
    def test_payload_has_exactly_the_receipt1_top_level_keys(self) -> None:
        p = build_receipt_contract(str(SESSION_FIXTURE))
        assert set(p.keys()) == {
            "session",
            "model",
            "cost_usd",
            "dominant",
            "cost_basis",
            "estimate",
            "models",
            "tokens",
            "calls",
            "stages",
            "turns",
            "errors",
            "active_min",
            "context",
            "tools",
        }

    def test_tokens_block_uses_compact_names(self) -> None:
        tok = build_receipt_contract(str(SESSION_FIXTURE))["tokens"]
        assert set(tok.keys()) == {"total", "in", "out", "cache_read", "cache_write", "working"}

    def test_context_block_uses_compact_names(self) -> None:
        ctx = build_receipt_contract(str(SESSION_FIXTURE))["context"]
        assert set(ctx.keys()) == {"window", "peak_ctx", "span_min", "events", "error_min", "note"}

    def test_specimen_payload_parses_and_matches_our_shape(self) -> None:
        """Round-trip the specimen's embedded receipt/1 through json and assert
        our assembler produces the same field *names* (the contract surface).

        ComposeSpec.telemetry_data is opaque dict[str, object], so the names
        the specimen uses must equal the names our assembler emits — this is
        the agreement the resolver reads against.
        """
        specimen = {
            "session": "398ce70f",
            "model": "opus-4.7",
            "cost_usd": 175.01,
            "models": [{"name": "opus-4.7", "role": "main thread", "cost_usd": 128.00, "cost_pct": 73}],
            "dominant": "opus-4.7",
            "cost_basis": "public per-token rates",
            "estimate": True,
            "tokens": {
                "total": 262400000,
                "in": 157500,
                "out": 867300,
                "cache_read": 257600000,
                "cache_write": 3800000,
                "working": 1024800,
            },
            "calls": 562,
            "stages": 55,
            "turns": 31,
            "errors": 15,
            "active_min": 157,
            "context": {
                "window": 200000,
                "peak_ctx": 196000,
                "events": [{"min": 31, "cmd": "compact", "to": 38000}],
                "note": CONTEXT_NOTE,
            },
            "tools": [{"name": "Edit", "tok": 709300, "calls": 242, "err": 6, "class": "mutate"}],
        }
        ours = build_receipt_contract(str(SESSION_FIXTURE))
        # Top-level names agree.
        assert set(specimen.keys()) <= set(ours.keys()) | {"models"}
        assert set(specimen["tokens"].keys()) == set(ours["tokens"].keys())
        # span_min (elapsed wall-clock span) and error_min (real error minutes) are
        # our v0.4 extensions beyond the v3 specimen — the burn curve runs on them,
        # so the specimen's names are a subset of ours, with these two added.
        assert set(specimen["context"].keys()) <= set(ours["context"].keys())
        assert set(ours["context"].keys()) - set(specimen["context"].keys()) == {"span_min", "error_min"}
        # The specimen's tool entry uses the same sparse field vocabulary.
        sample_tool = specimen["tools"][0]
        assert set(sample_tool.keys()) <= {"name", "tok", "calls", "err", "class"}
        # working identity holds on the specimen numbers.
        assert specimen["tokens"]["working"] == specimen["tokens"]["in"] + specimen["tokens"]["out"]
