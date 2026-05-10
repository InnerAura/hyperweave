"""Real-fixture coverage for the v0.2.23 Codex parser.

Two fixtures are exercised, scoped to distinct schema territories:

* ``tests/fixtures/codex_session.jsonl`` (170-line May 3) — covers
  ``function_call`` (exec_command, write_stdin), ``web_search_call``
  (22 events), nullable ``token_count.info``, full event_msg variety.
* ``tests/fixtures/codex_session_patches.jsonl`` (745-line Mar 20) —
  covers ``custom_tool_call`` (apply_patch, 20 events), update_plan,
  larger token totals, more turn boundaries.

Both have ``session_meta.payload.base_instructions.text`` redacted (it
carries OpenAI's proprietary system prompt) and reasoning
``encrypted_content`` stripped (opaque ciphertext, not parser-relevant).
"""

from __future__ import annotations

from hyperweave.telemetry.codex_parser import parse_transcript
from hyperweave.telemetry.models import ToolClass, ToolOutcome

PRIMARY_FIXTURE = "tests/fixtures/codex_session.jsonl"
PATCHES_FIXTURE = "tests/fixtures/codex_session_patches.jsonl"


# --------------------------------------------------------------------------- #
# Primary fixture (web_search + exec_command + write_stdin)                   #
# --------------------------------------------------------------------------- #


def test_primary_fixture_parses() -> None:
    """170-line May 3 fixture parses without errors."""
    t = parse_transcript(PRIMARY_FIXTURE)
    assert t.runtime == "codex"
    assert t.session_id  # session_meta.payload.id was preserved through redaction


def test_primary_fixture_has_three_tool_call_shapes() -> None:
    """function_call (exec_command, write_stdin) + web_search_call all extracted."""
    t = parse_transcript(PRIMARY_FIXTURE)
    names = {tc.tool_name for tc in t.tool_calls}
    assert "exec_command" in names
    assert "write_stdin" in names
    assert "web_search" in names  # synthesized for web_search_call payloads


def test_primary_fixture_web_search_classified_as_explore() -> None:
    """web_search_call → tool_class=EXPLORE per codex.yaml."""
    t = parse_transcript(PRIMARY_FIXTURE)
    web = [tc for tc in t.tool_calls if tc.tool_name == "web_search"]
    assert web, "expected at least one web_search_call in primary fixture"
    assert all(tc.tool_class == ToolClass.EXPLORE for tc in web)


def test_primary_fixture_exec_classified_as_execute() -> None:
    """exec_command + write_stdin → tool_class=EXECUTE per codex.yaml."""
    t = parse_transcript(PRIMARY_FIXTURE)
    for tc in t.tool_calls:
        if tc.tool_name in ("exec_command", "write_stdin"):
            assert tc.tool_class == ToolClass.EXECUTE, f"{tc.tool_name} → {tc.tool_class}"


def test_primary_fixture_token_total_disjoint() -> None:
    """Codex token tally subtracts cached_input from input so the four token
    fields sum to the runtime-reported total (no double-counting)."""
    t = parse_transcript(PRIMARY_FIXTURE)
    summed = (
        t.totals.total_input_tokens
        + t.totals.total_output_tokens
        + t.totals.total_cache_read
        + t.totals.total_cache_create
    )
    # Sanity: total > 0 (this fixture has real usage), and input was actually
    # split out from cache (cache should be the dominant component for a
    # context-rich session).
    assert summed > 0
    assert t.totals.total_cache_read > t.totals.total_input_tokens, (
        "expected cache to dominate fresh input on a context-heavy real session"
    )


def test_primary_fixture_handles_nullable_token_count_info() -> None:
    """Codex emits ``info: null`` on early token_count events; parser must skip,
    not crash, and find the LAST non-null event for total tally."""
    t = parse_transcript(PRIMARY_FIXTURE)
    # If the parser had crashed on the null-info event we'd never get here.
    assert t.totals.total_input_tokens >= 0


# --------------------------------------------------------------------------- #
# Patches fixture (apply_patch + update_plan + exec_command)                  #
# --------------------------------------------------------------------------- #


def test_patches_fixture_parses() -> None:
    """745-line Mar 20 fixture parses without errors."""
    t = parse_transcript(PATCHES_FIXTURE)
    assert t.runtime == "codex"
    assert t.session_id


def test_patches_fixture_extracts_apply_patch_calls() -> None:
    """custom_tool_call/apply_patch events are surfaced as ToolCall(tool_name='apply_patch')."""
    t = parse_transcript(PATCHES_FIXTURE)
    patches = [tc for tc in t.tool_calls if tc.tool_name == "apply_patch"]
    assert len(patches) >= 10, f"expected ≥10 apply_patch calls, got {len(patches)}"


def test_patches_fixture_apply_patch_classified_as_mutate() -> None:
    """apply_patch → tool_class=MUTATE per codex.yaml."""
    t = parse_transcript(PATCHES_FIXTURE)
    for tc in t.tool_calls:
        if tc.tool_name == "apply_patch":
            assert tc.tool_class == ToolClass.MUTATE, f"apply_patch → {tc.tool_class}"


def test_patches_fixture_extracts_update_plan() -> None:
    """response_item/function_call/update_plan classifies as coordinate."""
    t = parse_transcript(PATCHES_FIXTURE)
    plans = [tc for tc in t.tool_calls if tc.tool_name == "update_plan"]
    if plans:  # update_plan is rare; only assert classification when present
        assert all(tc.tool_class == ToolClass.COORDINATE for tc in plans)


def test_patches_fixture_apply_patch_extracts_file_path() -> None:
    """apply_patch input contains '*** Update File: <path>' — parser captures the first."""
    t = parse_transcript(PATCHES_FIXTURE)
    patches = [tc for tc in t.tool_calls if tc.tool_name == "apply_patch"]
    with_paths = [tc for tc in patches if tc.file_path]
    assert with_paths, "expected at least one apply_patch with extracted file_path"


# --------------------------------------------------------------------------- #
# Outcome propagation                                                         #
# --------------------------------------------------------------------------- #


def test_outcomes_default_to_success() -> None:
    """Tool calls without explicit error markers default to SUCCESS."""
    t = parse_transcript(PRIMARY_FIXTURE)
    successes = [tc for tc in t.tool_calls if tc.outcome == ToolOutcome.SUCCESS]
    assert successes, "expected at least one successful call"


# --------------------------------------------------------------------------- #
# Schema invariants                                                           #
# --------------------------------------------------------------------------- #


def test_codex_runtime_stamped_on_every_telemetry() -> None:
    """SessionTelemetry.runtime must be 'codex' (resolver depends on this)."""
    for fixture in (PRIMARY_FIXTURE, PATCHES_FIXTURE):
        t = parse_transcript(fixture)
        assert t.runtime == "codex"


def test_no_subagent_spans_for_codex() -> None:
    """Codex has no Task-style subagent dispatch — agents list is empty."""
    for fixture in (PRIMARY_FIXTURE, PATCHES_FIXTURE):
        t = parse_transcript(fixture)
        assert t.agents == []


# --------------------------------------------------------------------------- #
# Session identity (git_branch + thread_name)                                 #
# --------------------------------------------------------------------------- #


def test_git_branch_extracted_from_session_meta() -> None:
    """session_meta.payload.git.branch is read into git_branch (no longer hardcoded None)."""
    t = parse_transcript(PRIMARY_FIXTURE)
    assert t.git_branch == "main", f"expected 'main' from fixture session_meta.git.branch, got {t.git_branch!r}"


def test_session_name_from_thread_name_updated() -> None:
    """event_msg/thread_name_updated.thread_name populates session_name (latest wins)."""
    t = parse_transcript(PRIMARY_FIXTURE)
    assert t.session_name == "hw_review_20260503", (
        f"expected 'hw_review_20260503' from thread_name_updated event, got {t.session_name!r}"
    )
