"""Unit tests for the Antigravity parser module."""

from __future__ import annotations

from hyperweave.telemetry.antigravity_parser import parse_transcript
from hyperweave.telemetry.models import ToolClass, ToolOutcome
from tests.conftest import FIXTURES_DIR

PRIMARY_FIXTURE = str(FIXTURES_DIR / "antigravity_session.jsonl")


def test_antigravity_fixture_parses() -> None:
    """The synthetic Antigravity session fixture parses without errors."""
    t = parse_transcript(PRIMARY_FIXTURE)
    assert t.runtime == "antigravity"
    assert t.session_id == "antigravity-session"
    assert t.project_path == "/Users/martha/Documents/Repositories/hyperweave"
    assert t.git_branch == "main"
    assert t.model == "Gemini 3.5 Flash"


def test_tool_calls_extracted_and_classified() -> None:
    """All tool calls are extracted and classified into correct ToolClasses."""
    t = parse_transcript(PRIMARY_FIXTURE)
    assert len(t.tool_calls) == 3

    # Order of tool calls in the fixture: view_file, run_command, invoke_subagent
    tc0, tc1, tc2 = t.tool_calls

    assert tc0.tool_name == "view_file"
    assert tc0.tool_class == ToolClass.EXPLORE
    assert tc0.file_path == "/Users/martha/Documents/Repositories/hyperweave/antigravity_setup_guide.md"
    assert tc0.command is None

    assert tc1.tool_name == "run_command"
    assert tc1.tool_class == ToolClass.EXECUTE
    assert tc1.command == "git status"
    assert tc1.file_path is None

    assert tc2.tool_name == "invoke_subagent"
    assert tc2.tool_class == ToolClass.COORDINATE
    assert tc2.file_path is None
    assert tc2.command is None


def test_outcome_propagation() -> None:
    """Outcomes (success, error) are successfully matched and propagated."""
    t = parse_transcript(PRIMARY_FIXTURE)
    tc0, tc1, tc2 = t.tool_calls

    # view_file has DONE status -> SUCCESS
    assert tc0.outcome == ToolOutcome.SUCCESS

    # run_command has ERROR status -> ERROR
    assert tc1.outcome == ToolOutcome.ERROR

    # invoke_subagent has DONE status -> SUCCESS
    assert tc2.outcome == ToolOutcome.SUCCESS


def test_token_distribution() -> None:
    """Token estimations are successfully parsed and distributed across tool calls."""
    t = parse_transcript(PRIMARY_FIXTURE)
    assert t.totals.total_calls == 3
    assert t.totals.total_input_tokens > 0
    assert t.totals.total_output_tokens > 0

    summed_input = sum(tc.tokens_input for tc in t.tool_calls)
    summed_output = sum(tc.tokens_output for tc in t.tool_calls)

    assert summed_input <= t.totals.total_input_tokens
    assert summed_output <= t.totals.total_output_tokens
    # Proportional distribution should be close to the total
    assert abs(summed_input - t.totals.total_input_tokens) < 10
    assert abs(summed_output - t.totals.total_output_tokens) < 10


def test_files_accessed() -> None:
    """Files accessed list gathers unique path inputs."""
    t = parse_transcript(PRIMARY_FIXTURE)
    assert len(t.files_accessed) == 1
    assert t.files_accessed[0] == "/Users/martha/Documents/Repositories/hyperweave/antigravity_setup_guide.md"


def test_agent_span_detection() -> None:
    """Agent span is successfully detected from invoke_subagent calls."""
    t = parse_transcript(PRIMARY_FIXTURE)
    assert len(t.agents) == 1
    agent = t.agents[0]
    assert agent.agent_type == "general-purpose"
    assert agent.start_time is not None
