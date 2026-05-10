"""Tests for the telemetry module.

Tests Pydantic models, YAML config loading, 5-pass JSONL parser,
3-signal stage detection, dual-signal correction classification,
cost calculation, data contract building, generation event capture,
and the architectural invariant that telemetry/ never imports
render/ or compose/.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from hyperweave.telemetry.capture import GenerationEvent, emit_generation_event
from hyperweave.telemetry.contract import build_contract
from hyperweave.telemetry.corrections import classify_user_events
from hyperweave.telemetry.cost import calculate_session_cost, calculate_turn_cost
from hyperweave.telemetry.models import (
    STAGE_LABEL_MAP,
    ConfidenceLevel,
    SessionTelemetry,
    StageLabel,
    ToolCall,
    ToolClass,
    ToolOutcome,
    UserEvent,
    UserEventCategory,
)
from hyperweave.telemetry.parser import parse_transcript
from hyperweave.telemetry.runtimes import classify_tool, get_runtime
from hyperweave.telemetry.stages import detect_stages

_CC_REGISTRY = get_runtime("claude-code")

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SESSION_FIXTURE = FIXTURES_DIR / "session.jsonl"


# =========================================================================
# YAML Config Loading
# =========================================================================


class TestYAMLConfigLoading:
    """Verify that config maps are loaded from YAML, not hardcoded.

    Tool-class classification moved to the per-runtime registries in
    v0.2.23 — see ``tests/test_runtime_registries.py`` for tool table
    and detection-rule coverage. This class now only covers stage-label
    config (still in ``data/telemetry/stage-labels.yaml``).
    """

    def test_stage_label_map_loaded(self) -> None:
        assert len(STAGE_LABEL_MAP) > 0
        assert STAGE_LABEL_MAP[ToolClass.EXPLORE] == StageLabel.RECONNAISSANCE
        assert STAGE_LABEL_MAP[ToolClass.MUTATE] == StageLabel.IMPLEMENTATION
        assert STAGE_LABEL_MAP[ToolClass.EXECUTE] == StageLabel.VALIDATION

    def test_stage_label_map_values_are_enums(self) -> None:
        for cls, label in STAGE_LABEL_MAP.items():
            assert isinstance(cls, ToolClass)
            assert isinstance(label, StageLabel)


# =========================================================================
# Pydantic Models
# =========================================================================


class TestModels:
    """Verify Pydantic model constraints."""

    def test_tool_call_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            ToolCall(
                tool_name="Read",
                tool_id="x",
                tool_class=ToolClass.EXPLORE,
                timestamp=datetime.now(),
                bogus_field="nope",  # type: ignore[call-arg]
            )

    def test_tool_call_file_path(self) -> None:
        tc = ToolCall(
            tool_name="Read",
            tool_id="x",
            tool_class=ToolClass.EXPLORE,
            timestamp=datetime.now(),
            file_path="/src/main.py",
        )
        assert tc.file_path == "/src/main.py"

    def test_tool_call_defaults(self) -> None:
        tc = ToolCall(
            tool_name="Bash",
            tool_id="y",
            tool_class=ToolClass.EXECUTE,
            timestamp=datetime.now(),
        )
        assert tc.outcome == ToolOutcome.SUCCESS
        assert tc.tokens_input == 0
        assert tc.file_path is None
        assert tc.command is None


# =========================================================================
# Transcript Parser (5-pass)
# =========================================================================


class TestTranscriptParser:
    """Verify 5-pass JSONL transcript parsing."""

    @pytest.fixture(scope="class")
    def telemetry(self) -> SessionTelemetry:
        return parse_transcript(SESSION_FIXTURE)

    def test_returns_session_telemetry(self, telemetry: SessionTelemetry) -> None:
        assert isinstance(telemetry, SessionTelemetry)

    def test_extracts_session_id(self, telemetry: SessionTelemetry) -> None:
        assert telemetry.session_id == "session-001"

    def test_extracts_project_path(self, telemetry: SessionTelemetry) -> None:
        assert telemetry.project_path == "/project"

    def test_extracts_git_branch(self, telemetry: SessionTelemetry) -> None:
        assert telemetry.git_branch == "main"

    def test_extracts_model(self, telemetry: SessionTelemetry) -> None:
        assert telemetry.model == "claude-opus-4-6"

    def test_extracts_tool_calls(self, telemetry: SessionTelemetry) -> None:
        assert len(telemetry.tool_calls) > 0
        tool_names = {tc.tool_name for tc in telemetry.tool_calls}
        assert "Bash" in tool_names
        assert "Write" in tool_names
        assert "Read" in tool_names

    def test_extracts_file_paths(self, telemetry: SessionTelemetry) -> None:
        assert len(telemetry.files_accessed) > 0
        assert "pyproject.toml" in telemetry.files_accessed

    def test_file_path_on_tool_calls(self, telemetry: SessionTelemetry) -> None:
        write_calls = [tc for tc in telemetry.tool_calls if tc.tool_name == "Write"]
        has_file_path = any(tc.file_path is not None for tc in write_calls)
        assert has_file_path

    def test_command_on_bash_calls(self, telemetry: SessionTelemetry) -> None:
        bash_calls = [tc for tc in telemetry.tool_calls if tc.tool_name == "Bash"]
        has_command = any(tc.command is not None for tc in bash_calls)
        assert has_command

    def test_extracts_usage(self, telemetry: SessionTelemetry) -> None:
        assert telemetry.totals.total_input_tokens > 0
        assert telemetry.totals.total_output_tokens > 0

    def test_extracts_timestamps(self, telemetry: SessionTelemetry) -> None:
        assert telemetry.timestamp.year == 2026

    def test_extracts_user_events(self, telemetry: SessionTelemetry) -> None:
        assert len(telemetry.user_events) > 0
        for event in telemetry.user_events:
            assert isinstance(event, UserEvent)
            assert len(event.message_preview) > 0

    def test_tool_outcome_error_detected(self, telemetry: SessionTelemetry) -> None:
        """The fixture has tool-014 with is_error=true tool_result."""
        tc_014 = [tc for tc in telemetry.tool_calls if tc.tool_id == "tool-014"]
        assert len(tc_014) == 1
        assert tc_014[0].outcome == ToolOutcome.ERROR

    def test_tool_outcome_success_default(self, telemetry: SessionTelemetry) -> None:
        tc_003 = [tc for tc in telemetry.tool_calls if tc.tool_id == "tool-003"]
        assert len(tc_003) == 1
        assert tc_003[0].outcome == ToolOutcome.SUCCESS

    def test_duration_from_turn_duration(self, telemetry: SessionTelemetry) -> None:
        """system.turn_duration entry provides 2730000ms = 45.5 min."""
        assert telemetry.duration_minutes == 45.5

    def test_tool_summary(self, telemetry: SessionTelemetry) -> None:
        assert "Write" in telemetry.tool_summary
        assert telemetry.tool_summary["Write"].call_count > 0
        assert telemetry.tool_summary["Write"].tool_class == ToolClass.MUTATE

    def test_stages_empty_before_detection(self, telemetry: SessionTelemetry) -> None:
        # parse_transcript leaves stages empty; detect_stages fills them
        assert telemetry.stages == []

    def test_file_not_found_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_transcript("/nonexistent/path.jsonl")

    def test_per_call_token_division(self, telemetry: SessionTelemetry) -> None:
        """Turns with 2 tool calls divide tokens evenly."""
        # tool-002 and tool-003 are in the same turn (4100 input tokens)
        tc_002 = next(tc for tc in telemetry.tool_calls if tc.tool_id == "tool-002")
        tc_003 = next(tc for tc in telemetry.tool_calls if tc.tool_id == "tool-003")
        assert tc_002.tokens_input == 2050
        assert tc_003.tokens_input == 2050


# =========================================================================
# Stage Detector (3-signal)
# =========================================================================


class TestStageDetector:
    """Verify 3-signal weighted stage detection."""

    def _make_call(
        self,
        name: str,
        ts: datetime,
        tool_class: ToolClass | None = None,
    ) -> ToolCall:
        return ToolCall(
            tool_name=name,
            tool_id=f"id-{name}-{ts.second}",
            tool_class=tool_class or classify_tool(_CC_REGISTRY, name),
            timestamp=ts,
        )

    def test_empty_input(self) -> None:
        assert detect_stages([]) == []

    def test_single_call(self) -> None:
        tc = self._make_call("Read", datetime(2026, 1, 1, 10, 0, 0))
        stages = detect_stages([tc])
        assert len(stages) == 1
        assert stages[0].label == StageLabel.RECONNAISSANCE
        assert stages[0].call_count == 1

    def test_detects_class_shift(self) -> None:
        """6 Reads then a temporal gap then 6 Writes should detect a boundary.

        Tool class shift alone (0.4) < threshold (0.6). Adding a temporal
        gap (0.3) at the boundary pushes the combined score over 0.6.
        """
        from datetime import timedelta

        base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        calls = []
        for i in range(6):
            calls.append(
                self._make_call(
                    "Read",
                    base + timedelta(seconds=i),
                )
            )
        # Large temporal gap before the class shift
        gap = base + timedelta(seconds=60)
        for i in range(6):
            calls.append(
                self._make_call(
                    "Write",
                    gap + timedelta(seconds=i),
                )
            )
        stages = detect_stages(calls)
        assert len(stages) >= 2
        labels = [s.label for s in stages]
        assert StageLabel.RECONNAISSANCE in labels
        assert StageLabel.IMPLEMENTATION in labels

    def test_all_calls_assigned(self) -> None:
        """Every tool call appears in exactly one stage."""
        base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        calls = [self._make_call("Read", base.replace(second=i)) for i in range(10)]
        stages = detect_stages(calls)
        total_in_stages = sum(s.call_count for s in stages)
        assert total_in_stages == len(calls)

    def test_from_fixture(self) -> None:
        telemetry = parse_transcript(SESSION_FIXTURE)
        stages = detect_stages(telemetry.tool_calls)
        assert len(stages) >= 1
        for stage in stages:
            assert 0.0 <= stage.boundary_score <= 1.0


# =========================================================================
# Correction Detector (dual-signal)
# =========================================================================


class TestCorrectionDetector:
    """Verify dual-signal user message classification."""

    def _make_event(self, text: str, ts: datetime | None = None) -> UserEvent:
        return UserEvent(
            category=UserEventCategory.CONTINUATION,
            message_preview=text[:80],
            timestamp=ts or datetime(2026, 1, 1, 10, 5, 0),
            confidence=ConfidenceLevel.LOW,
        )

    def test_lexical_correction(self) -> None:
        event = self._make_event("No, that's wrong. Revert the change.")
        result = classify_user_events([event], [])
        assert result[0].category == UserEventCategory.CORRECTION
        assert result[0].confidence == ConfidenceLevel.MEDIUM

    def test_lexical_redirection(self) -> None:
        event = self._make_event("Let's switch to a different approach")
        result = classify_user_events([event], [])
        assert result[0].category == UserEventCategory.REDIRECTION

    def test_lexical_elaboration(self) -> None:
        event = self._make_event("Also, add error handling for edge cases")
        result = classify_user_events([event], [])
        assert result[0].category == UserEventCategory.ELABORATION

    def test_continuation_default(self) -> None:
        event = self._make_event("Looks good, proceed with implementation")
        result = classify_user_events([event], [])
        assert result[0].category == UserEventCategory.CONTINUATION
        assert result[0].confidence == ConfidenceLevel.HIGH

    def test_empty_events(self) -> None:
        assert classify_user_events([], []) == []


# =========================================================================
# Cost Calculator
# =========================================================================


class TestCostCalculator:
    """Verify token cost calculation with known inputs."""

    def test_zero_tokens_zero_cost(self) -> None:
        usage: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
        assert calculate_turn_cost(usage, "claude-opus-4-6") == 0.0

    def test_known_opus_cost(self) -> None:
        usage: dict[str, int] = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_creation_input_tokens": 200,
            "cache_read_input_tokens": 1000,
        }
        cost = calculate_turn_cost(usage, "claude-opus-4-6")
        # Opus 4.6: $5/M input + $25/M output + 1.25x cache write + 0.1x cache read
        assert abs(cost - 0.01925) < 1e-9

    def test_session_cost_sums_turns(self) -> None:
        turns: list[dict[str, Any]] = [
            {
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "model": "claude-opus-4-6",
            },
            {
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "model": "claude-opus-4-6",
            },
        ]
        single = calculate_turn_cost(turns[0]["usage"], "claude-opus-4-6")
        total = calculate_session_cost(turns)
        assert abs(total - 2 * single) < 1e-9

    def test_cache_creation_multiplier(self) -> None:
        usage: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 1_000_000,
            "cache_read_input_tokens": 0,
        }
        cost = calculate_turn_cost(usage, "claude-opus-4-6")
        expected = 1.25 * 5.0  # Opus 4.6: $5/M input * 1.25x cache write
        assert abs(cost - expected) < 1e-9

    def test_cache_read_multiplier(self) -> None:
        usage: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 1_000_000,
        }
        cost = calculate_turn_cost(usage, "claude-opus-4-6")
        expected = 0.1 * 5.0  # Opus 4.6: $5/M input * 0.1x cache read
        assert abs(cost - expected) < 1e-9

    def test_unknown_model_uses_default_rates(self) -> None:
        usage: dict[str, int] = {
            "input_tokens": 1_000_000,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
        cost = calculate_turn_cost(usage, "unknown-model-xyz")
        assert abs(cost - 5.0) < 1e-9  # Default rates: $5/M input (Opus 4.6)


# =========================================================================
# Contract Builder
# =========================================================================


class TestContractBuilder:
    """Verify the data contract structure."""

    @pytest.fixture(scope="class")
    def contract(self) -> dict[str, Any]:
        return build_contract(str(SESSION_FIXTURE))

    def test_has_session_key(self, contract: dict[str, Any]) -> None:
        session = contract["session"]
        assert session["id"] == "session-001"
        assert session["model"] == "claude-opus-4-6"
        assert session["git_branch"] == "main"
        assert session["duration_minutes"] > 0

    def test_has_profile_key(self, contract: dict[str, Any]) -> None:
        profile = contract["profile"]
        assert profile["total_input_tokens"] > 0
        assert profile["total_output_tokens"] > 0
        assert profile["total_cost"] > 0
        assert profile["turns"] > 0
        assert "opus" in profile["model"]

    def test_has_tools_key(self, contract: dict[str, Any]) -> None:
        tools = contract["tools"]
        assert isinstance(tools, dict)
        assert len(tools) > 0

    def test_tool_entries_have_fields(self, contract: dict[str, Any]) -> None:
        for name, data in contract["tools"].items():
            assert "count" in data, f"Tool {name!r} missing 'count'"
            assert "total_tokens" in data, f"Tool {name!r} missing 'total_tokens'"
            assert "tool_class" in data, f"Tool {name!r} missing 'tool_class'"

    def test_has_files_accessed(self, contract: dict[str, Any]) -> None:
        assert isinstance(contract["files_accessed"], list)
        assert len(contract["files_accessed"]) > 0

    def test_has_stages(self, contract: dict[str, Any]) -> None:
        stages = contract["stages"]
        assert isinstance(stages, list)
        assert len(stages) > 0
        for stage in stages:
            assert "label" in stage
            assert "dominant_class" in stage
            assert "boundary_score" in stage

    def test_has_user_events(self, contract: dict[str, Any]) -> None:
        assert "user_events" in contract
        assert isinstance(contract["user_events"], list)

    def test_has_agents(self, contract: dict[str, Any]) -> None:
        assert "agents" in contract
        assert isinstance(contract["agents"], list)

    def test_total_cost_positive(self, contract: dict[str, Any]) -> None:
        assert contract["profile"]["total_cost"] > 0


# =========================================================================
# Generation Event Capture
# =========================================================================


class TestGenerationEvent:
    """Verify generation event capture."""

    def test_emit_event_from_spec_and_result(self) -> None:
        from hyperweave.core.models import ComposeResult, ComposeSpec

        spec = ComposeSpec(
            type="badge",
            genome_id="brutalist",
            motion="bars",
            regime="normal",
            metadata_tier=3,
        )
        result = ComposeResult(
            svg="<svg></svg>",
            width=200,
            height=22,
        )

        event = emit_generation_event(spec, result)
        assert isinstance(event, GenerationEvent)
        assert event.artifact_type == "badge"
        assert event.genome_id == "brutalist"
        assert event.motion == "bars"
        assert event.width == 200
        assert event.height == 22
        assert event.timestamp

    def test_event_is_frozen(self) -> None:
        event = GenerationEvent(
            timestamp="2026-03-18T10:00:00Z",
            artifact_type="badge",
            genome_id="test",
            profile_id="brutalist",
            motion="static",
            regime="normal",
            metadata_tier=3,
            width=200,
            height=22,
        )
        with pytest.raises(AttributeError):
            event.width = 999  # type: ignore[misc]


# =========================================================================
# ARCHITECTURAL INVARIANT: telemetry/ never imports render/ or compose/
# =========================================================================


class TestArchitecturalInvariant:
    """Verify that the telemetry module has ZERO imports from render/ or compose/."""

    TELEMETRY_DIR = Path(__file__).parent.parent / "src" / "hyperweave" / "telemetry"

    def _get_imports(self, filepath: Path) -> list[str]:
        source = filepath.read_text()
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        return imports

    def test_no_render_imports(self) -> None:
        for py_file in self.TELEMETRY_DIR.glob("*.py"):
            imports = self._get_imports(py_file)
            for imp in imports:
                assert "render" not in imp, f"INVARIANT VIOLATION: {py_file.name} imports {imp!r}"

    def test_no_compose_imports(self) -> None:
        for py_file in self.TELEMETRY_DIR.glob("*.py"):
            imports = self._get_imports(py_file)
            for imp in imports:
                assert "compose" not in imp, f"INVARIANT VIOLATION: {py_file.name} imports {imp!r}"

    def test_telemetry_files_exist(self) -> None:
        expected = {
            "__init__.py",
            "models.py",
            "parser.py",
            "stages.py",
            "corrections.py",
            "contract.py",
            "cost.py",
            "capture.py",
        }
        actual = {f.name for f in self.TELEMETRY_DIR.glob("*.py")}
        assert expected.issubset(actual), f"Missing: {expected - actual}"

    def test_no_fstring_svg(self) -> None:
        """grep for f-string SVG in telemetry/ -- zero hits."""
        for py_file in self.TELEMETRY_DIR.glob("*.py"):
            source = py_file.read_text()
            assert 'f"<svg' not in source, f"f-string SVG in {py_file.name}"
            assert "f'<svg" not in source, f"f-string SVG in {py_file.name}"


# =========================================================================
# Telemetry Quality Pass: turn counting + customTitle extraction
# =========================================================================
#
# Synthetic fixture (`tests/fixtures/synthetic_session.jsonl`) covers the
# four leak/drop/overcount paths in one file:
#   - 5 prose prompts (3 continuation, 1 correction, 1 elaboration)
#   - 1 `<command-name>...</command-name>` slash command (filter regression)
#   - 1 `<local-command-stdout>...</local-command-stdout>` echo (envelope leak)
#   - 2 `tool_result` user records (count regression)
#   - 3 `custom-title` records exercising rename history (latest wins)


SYNTHETIC_FIXTURE = FIXTURES_DIR / "synthetic_session.jsonl"


class TestEnvelopeFilter:
    """Bug A: parser must filter ALL XML envelope wrappers, not just command-name."""

    def test_local_command_stdout_excluded_from_user_events(self) -> None:
        tel = parse_transcript(SYNTHETIC_FIXTURE)
        previews = [e.message_preview for e in tel.user_events]
        for p in previews:
            assert not p.startswith("<local-command-stdout>"), (
                f"local-command-stdout envelope leaked into user_events: {p!r}"
            )

    def test_command_name_envelope_excluded(self) -> None:
        tel = parse_transcript(SYNTHETIC_FIXTURE)
        previews = [e.message_preview for e in tel.user_events]
        for p in previews:
            assert not p.startswith("<command-name>"), f"command-name envelope leaked: {p!r}"

    def test_only_prose_prompts_become_user_events(self) -> None:
        """5 prose prompts in fixture; envelopes and tool_results all excluded."""
        tel = parse_transcript(SYNTHETIC_FIXTURE)
        assert len(tel.user_events) == 5, (
            f"expected 5 prose user events, got {len(tel.user_events)}: {[e.message_preview for e in tel.user_events]}"
        )


class TestContractPreservesAllEvents:
    """Bug B: the contract must NOT drop continuation events."""

    def test_contract_user_events_includes_continuations(self) -> None:
        c = build_contract(str(SYNTHETIC_FIXTURE))
        assert len(c["user_events"]) == 5, (
            f"contract dropped continuation events: got {len(c['user_events'])}, expected 5"
        )

    def test_contract_user_events_categories(self) -> None:
        """3 continuation + 1 correction + 1 elaboration after classification."""
        c = build_contract(str(SYNTHETIC_FIXTURE))
        cats = [e["category"] for e in c["user_events"]]
        assert cats.count("continuation") == 3, f"continuation count: {cats}"
        assert cats.count("correction") == 1, f"correction count: {cats}"
        assert cats.count("elaboration") == 1, f"elaboration count: {cats}"


class TestTotalUserMessages:
    """Bug D: total_user_messages must count only filtered prose, not raw user records."""

    def test_total_user_messages_excludes_tool_results_and_envelopes(self) -> None:
        tel = parse_transcript(SYNTHETIC_FIXTURE)
        assert tel.totals.total_user_messages == 5, (
            f"total_user_messages overcounts: got {tel.totals.total_user_messages}, expected 5 "
            f"(2 tool_results + 1 command-name + 1 local-command-stdout must NOT count)"
        )


class TestSessionNameExtraction:
    """Workstream 2: parser must surface latest customTitle as session_name."""

    def test_session_name_uses_latest_custom_title(self) -> None:
        """Fixture has 3 `custom-title` records: latest is 'third-session-title'."""
        tel = parse_transcript(SYNTHETIC_FIXTURE)
        assert tel.session_name == "third-session-title", f"expected latest customTitle, got {tel.session_name!r}"

    def test_session_name_default_empty_when_no_custom_title(self) -> None:
        """Existing session.jsonl fixture has no custom-title records."""
        tel = parse_transcript(SESSION_FIXTURE)
        assert tel.session_name == "", f"expected empty session_name, got {tel.session_name!r}"
