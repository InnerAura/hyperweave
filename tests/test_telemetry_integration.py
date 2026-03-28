"""Integration tests for the telemetry delivery pipeline.

Tests the full chain: transcript JSONL -> parser -> contract -> compose -> SVG.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_JSONL = Path("tests/fixtures/session.jsonl")


@pytest.fixture()
def fixture_transcript() -> Path:
    assert FIXTURE_JSONL.exists(), f"Fixture not found: {FIXTURE_JSONL}"
    return FIXTURE_JSONL


def test_contract_structure(fixture_transcript: Path) -> None:
    """Contract has all required top-level keys."""
    from hyperweave.telemetry.contract import build_contract

    contract = build_contract(str(fixture_transcript))

    assert "session" in contract
    assert "profile" in contract
    assert "tools" in contract
    assert "stages" in contract
    assert "corrections" in contract
    assert "agents" in contract

    # Session fields
    session = contract["session"]
    assert "id" in session
    assert "model" in session
    assert "duration_minutes" in session

    # Profile fields
    profile = contract["profile"]
    assert "total_input_tokens" in profile
    assert "total_output_tokens" in profile
    assert "total_cost" in profile
    assert profile["total_cost"] > 0

    # Tools is a dict keyed by tool name
    tools = contract["tools"]
    assert isinstance(tools, dict)
    assert len(tools) > 0
    for _name, data in tools.items():
        assert "count" in data
        assert "total_tokens" in data
        assert "tool_class" in data


def test_receipt_end_to_end(fixture_transcript: Path) -> None:
    """Full pipeline: transcript -> contract -> receipt SVG."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec
    from hyperweave.telemetry.contract import build_contract

    contract = build_contract(str(fixture_transcript))
    spec = ComposeSpec(type="receipt", telemetry_data=contract)
    result = compose(spec)

    assert "<svg" in result.svg
    assert result.width == 800
    assert result.height == 400

    # Hero stats are populated
    svg = result.svg.lower()
    assert "token" in svg or "tok" in svg
    assert "session" in svg

    # Treemap cells present
    assert 'data-hw-zone="treemap"' in result.svg

    # Rhythm bars present
    assert 'data-hw-zone="rhythm"' in result.svg


def test_rhythm_strip_end_to_end(fixture_transcript: Path) -> None:
    """Full pipeline: transcript -> contract -> rhythm strip SVG."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec
    from hyperweave.telemetry.contract import build_contract

    contract = build_contract(str(fixture_transcript))
    spec = ComposeSpec(type="rhythm-strip", telemetry_data=contract)
    result = compose(spec)

    assert "<svg" in result.svg
    assert result.width == 800
    assert result.height == 60

    # Stats present
    assert 'data-hw-zone="stats-left"' in result.svg
    assert 'data-hw-zone="velocity"' in result.svg
    assert 'data-hw-zone="loop-status"' in result.svg


def test_cli_session_parse(fixture_transcript: Path) -> None:
    """CLI session parse outputs valid JSON with expected structure."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["session", "parse", str(fixture_transcript)])

    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    data = json.loads(result.output)
    assert "session" in data
    assert "tools" in data
    assert "stages" in data


def test_cli_session_receipt(fixture_transcript: Path, tmp_path: Path) -> None:
    """CLI session receipt writes SVG to output path."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    out_path = tmp_path / "receipt.svg"
    runner = CliRunner()
    result = runner.invoke(app, ["session", "receipt", str(fixture_transcript), "-o", str(out_path)])

    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    assert out_path.exists()
    svg = out_path.read_text()
    assert "<svg" in svg


def test_cli_session_strip(fixture_transcript: Path) -> None:
    """CLI session strip outputs SVG to stdout."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["session", "strip", str(fixture_transcript)])

    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    assert "<svg" in result.output


def test_cli_stdin_hook_mode(fixture_transcript: Path, tmp_path: Path) -> None:
    """Simulate Claude Code hook: JSON on stdin with transcript_path."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    out_path = tmp_path / "hook-receipt.svg"
    hook_json = json.dumps(
        {
            "session_id": "test-hook",
            "transcript_path": str(fixture_transcript),
            "hook_event_name": "SessionEnd",
        }
    )
    runner = CliRunner()
    result = runner.invoke(app, ["session", "receipt", "-o", str(out_path)], input=hook_json)

    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    assert out_path.exists()
    svg = out_path.read_text()
    assert "<svg" in svg
