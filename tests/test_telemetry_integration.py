"""Integration tests for the telemetry delivery pipeline.

Tests the full chain: transcript JSONL -> parser -> contract -> compose -> SVG.
"""

from __future__ import annotations

import json
import re
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
    assert result.height == 500

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


# ── Treemap layout regression tests ──

# Stress-test telemetry with real-world long tool names from Claude Code.
_STRESS_TELEMETRY: dict[str, object] = {
    "session": {
        "duration_m": 30,
        "total_cost": 50.0,
        "total_tokens": 10_000_000,
        "total_input": 100_000,
        "total_output": 200_000,
        "cache_read": 5_000_000,
        "cache_create": 1_000_000,
        "calls": 80,
        "model": "claude-opus-4-6",
    },
    "tools": {
        "Write": {"total_tokens": 500_000, "count": 20, "tool_class": "mutate", "blocked": 0, "errors": 3},
        "TaskCreate": {"total_tokens": 200_000, "count": 12, "tool_class": "coordinate", "blocked": 2, "errors": 0},
        "NotebookEdit": {"total_tokens": 150_000, "count": 8, "tool_class": "mutate", "blocked": 0, "errors": 0},
        "AskUserQuestion": {"total_tokens": 100_000, "count": 6, "tool_class": "coordinate"},
        "ToolSearch": {"total_tokens": 50_000, "count": 5, "tool_class": "explore"},
        "WebSearch": {"total_tokens": 40_000, "count": 4, "tool_class": "explore"},
        "EnterPlanMode": {"total_tokens": 30_000, "count": 3, "tool_class": "coordinate"},
        "EnterWorktree": {"total_tokens": 20_000, "count": 2, "tool_class": "execute"},
        "ServerSentEvents": {"total_tokens": 15_000, "count": 2, "tool_class": "explore"},
    },
    "stages": [
        {"name": "impl", "label": "IMPL", "pct": 60, "tool_class": "mutate"},
        {"name": "recon", "label": "RECON", "pct": 40, "tool_class": "explore"},
    ],
    "corrections": [],
    "agents": [],
}


def test_receipt_treemap_clippath_present() -> None:
    """Every treemap cell has a clipPath preventing inter-cell text overflow."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(type="receipt", telemetry_data=_STRESS_TELEMETRY)
    svg = compose(spec).svg

    # Each cell group must have a <clipPath> definition and a <g clip-path=...> wrapper
    clip_defs = set(re.findall(r'<clipPath id="([^"]+)">', svg))
    clip_refs = set(re.findall(r'clip-path="url\(#([^"]+)\)"', svg))

    assert len(clip_defs) >= 5, f"Expected >=5 clipPaths, got {len(clip_defs)}"
    assert clip_refs <= clip_defs, f"Dangling clip-path refs: {clip_refs - clip_defs}"


def test_receipt_treemap_clippath_dimensions_match_cell() -> None:
    """Each clipPath rect matches its parent cell's dimensions."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(type="receipt", telemetry_data=_STRESS_TELEMETRY)
    svg = compose(spec).svg

    # Extract pairs: clipPath rect dimensions vs sibling background rect dimensions
    cell_pattern = re.compile(
        r"<clipPath[^>]*>\s*<rect width=\"(\d+)\" height=\"(\d+)\"/>\s*</clipPath>\s*"
        r"<rect width=\"(\d+)\" height=\"(\d+)\"",
    )
    for m in cell_pattern.finditer(svg):
        clip_w, clip_h, bg_w, bg_h = m.groups()
        assert clip_w == bg_w, f"clipPath width {clip_w} != cell width {bg_w}"
        assert clip_h == bg_h, f"clipPath height {clip_h} != cell height {bg_h}"


def test_receipt_tier2_vertical_stacking() -> None:
    """Tier-2 treemap cells stack name above meta (distinct y values)."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(type="receipt", telemetry_data=_STRESS_TELEMETRY)
    svg = compose(spec).svg

    # Tier-2 cells: cell-name at font-size=9, cell-meta at font-size=8
    # inside a cell with height=32 (tier-2 specific).
    tier2_cells = re.findall(
        r'<clipPath[^>]*>\s*<rect width="\d+" height="32"/>\s*</clipPath>'
        r'.*?<text class="m cell-name"[^>]*y="(\d+)"[^>]*>([^<]+)</text>\s*'
        r'<text class="m cell-meta"[^>]*y="(\d+)"',
        svg,
        re.DOTALL,
    )
    assert len(tier2_cells) >= 2, f"Expected >=2 tier-2 cells, got {len(tier2_cells)}"
    for name_y, name, meta_y in tier2_cells:
        assert name_y != meta_y, (
            f"Tier-2 cell '{name}' has name_y={name_y} == meta_y={meta_y} — text collision (stacking regression)"
        )


def test_receipt_treemap_error_annotations() -> None:
    """Cells with blocked/errored calls show ✗N; clean cells do not."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(type="receipt", telemetry_data=_STRESS_TELEMETRY)
    svg = compose(spec).svg

    # Derive expected error count from the fixture itself
    tools = _STRESS_TELEMETRY["tools"]
    assert isinstance(tools, dict)
    expected_errors = {
        name: data["blocked"] + data["errors"]
        for name, data in tools.items()
        if isinstance(data, dict) and data.get("blocked", 0) + data.get("errors", 0) > 0
    }

    # Extract all cell-error annotations
    error_annotations = re.findall(r'class="m cell-error"[^>]*>✗(\d+)</text>', svg)

    # Every tool with errors must have a matching annotation
    for name, count in expected_errors.items():
        assert str(count) in error_annotations, f"Expected ✗{count} for {name}, got annotations: {error_annotations}"

    # No extra annotations beyond what the fixture defines
    assert len(error_annotations) == len(expected_errors), (
        f"Expected {len(expected_errors)} error annotations, got {len(error_annotations)}: {error_annotations}"
    )

    # Error annotations must be inside clip-path groups (not outside)
    for m in re.finditer(r'<g clip-path="[^"]*">(.*?)</g>', svg, re.DOTALL):
        clip_content = m.group(1)
        if "cell-error" in clip_content:
            assert 'text-anchor="end"' in clip_content, "Error text must be right-aligned"


# ── SessionEnd hook: graceful no-op for non-conversational sessions ──
# Claude Code fires SessionEnd for non-conversational actions (e.g.
# `claude update`, `claude config`) with non-TTY stdin but no valid JSONL
# transcript. `hyperweave session receipt` must silently exit 0 instead of
# surfacing "Error: no transcript found" to the user's terminal.
#
# typer's CliRunner provides non-TTY stdin by default, so no monkeypatching
# of sys.stdin.isatty() is needed to simulate hook mode. The TTY/interactive
# error branch is intentionally uncovered here — CliRunner's stdin redirection
# makes it impractical to test, and that path is pre-existing behavior.


def test_hook_mode_silent_on_empty_stdin() -> None:
    """`claude update` scenario: SessionEnd with empty stdin → graceful no-op."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["session", "receipt"], input="")

    assert result.exit_code == 0, (
        f"Hook-mode empty stdin must exit 0 gracefully. exit={result.exit_code}, output={result.output!r}"
    )


def test_hook_mode_silent_on_invalid_json() -> None:
    """Malformed stdin JSON must not crash the hook."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["session", "receipt"], input="not{valid}json")

    assert result.exit_code == 0, (
        f"Invalid JSON on stdin must not fail the hook. exit={result.exit_code}, output={result.output!r}"
    )


def test_hook_mode_silent_when_transcript_path_absent_from_payload() -> None:
    """Valid JSON without transcript_path key → graceful no-op."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    runner = CliRunner()
    payload = json.dumps({"hook_event_name": "SessionEnd"})
    result = runner.invoke(app, ["session", "receipt"], input=payload)

    assert result.exit_code == 0, (
        f"Missing transcript_path key must not fail the hook. exit={result.exit_code}, output={result.output!r}"
    )


def test_hook_mode_silent_when_transcript_path_does_not_exist(tmp_path: Path) -> None:
    """Hook references a path that no longer exists → graceful no-op."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    ghost = tmp_path / "never-existed.jsonl"
    runner = CliRunner()
    payload = json.dumps({"transcript_path": str(ghost)})
    result = runner.invoke(app, ["session", "receipt"], input=payload)

    assert result.exit_code == 0, (
        f"Nonexistent transcript path must not fail the hook. exit={result.exit_code}, output={result.output!r}"
    )
