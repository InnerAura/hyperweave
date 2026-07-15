"""Integration tests for the telemetry delivery pipeline.

Tests the full chain: transcript JSONL -> parser -> contract / receipt payload
-> compose -> SVG. The primer receipt (8 variants) replaced the
earlier pre-genome treemap/rhythm artifact; these tests assert the
end-to-end CLI + hook behavior and the receipt zone structure. The receipt/1 payload
assembler + section-layout extremes are unit-tested in
``tests/telemetry/test_receipt_payload.py`` and ``tests/compose/test_receipt_primer.py``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from tests.conftest import FIXTURES_DIR

if TYPE_CHECKING:
    from pathlib import Path

FIXTURE_JSONL = FIXTURES_DIR / "session.jsonl"


@pytest.fixture()
def fixture_transcript() -> Path:
    assert FIXTURE_JSONL.exists(), f"Fixture not found: {FIXTURE_JSONL}"
    return FIXTURE_JSONL


def test_contract_structure(fixture_transcript: Path) -> None:
    """The legacy ``build_contract`` shape (kept for non-receipt consumers)."""
    from hyperweave.telemetry.contract import build_contract

    contract = build_contract(str(fixture_transcript))

    assert "session" in contract
    assert "profile" in contract
    assert "tools" in contract
    assert "stages" in contract
    assert "user_events" in contract
    assert "agents" in contract

    session = contract["session"]
    assert "id" in session
    assert "model" in session
    assert "duration_minutes" in session

    profile = contract["profile"]
    assert "total_input_tokens" in profile
    assert "total_output_tokens" in profile
    assert "total_cost" in profile
    assert profile["total_cost"] > 0

    tools = contract["tools"]
    assert isinstance(tools, dict)
    assert len(tools) > 0
    for _name, data in tools.items():
        assert "count" in data
        assert "total_tokens" in data
        assert "tool_class" in data


def test_receipt_end_to_end(fixture_transcript: Path) -> None:
    """Full pipeline: transcript -> receipt/1 payload -> receipt SVG."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec
    from hyperweave.telemetry.contract import build_receipt_contract

    payload = build_receipt_contract(str(fixture_transcript))
    spec = ComposeSpec(type="receipt", telemetry_data=payload)
    result = compose(spec)

    assert "<svg" in result.svg
    assert result.width == 800
    # Height is content-aware (the cursor stacks present zones); a full session
    # reaches the specimen's 578, a sparse one is shorter.
    assert 300 <= result.height <= 578

    # The receipt zones are present (the treemap/rhythm artifact is retired).
    for zone in ("identity", "hero", "metrics", "tool-spend", "cost-by-model", "footer"):
        assert f'data-hw-zone="{zone}"' in result.svg, f"missing zone {zone}"
    assert 'data-hw-field="burn-curve"' in result.svg


def test_receipt_defaults_to_primer_genome(fixture_transcript: Path) -> None:
    """No --genome → the receipt renders the primer genome (porcelain flagship)."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec
    from hyperweave.telemetry.contract import build_receipt_contract

    payload = build_receipt_contract(str(fixture_transcript))
    svg = compose(ComposeSpec(type="receipt", telemetry_data=payload)).svg
    assert 'data-hw-genome="primer"' in svg


def test_receipt_embeds_payload_and_envelope(fixture_transcript: Path) -> None:
    """The artifact carries the receipt/1 payload + an hwz/1 envelope id."""
    import hashlib

    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec
    from hyperweave.telemetry.contract import build_receipt_contract

    payload = build_receipt_contract(str(fixture_transcript))
    svg = compose(ComposeSpec(type="receipt", telemetry_data=payload)).svg
    assert 'schema="receipt/1"' in svg
    # Envelope id is sha256 over the compact payload bytes the resolver emits.
    compact = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(compact.encode("utf-8")).hexdigest()
    assert f"sha256:{digest}" in svg


def test_cli_session_receipt(fixture_transcript: Path, tmp_path: Path) -> None:
    """CLI session receipt writes a receipt SVG to the output path."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    out_path = tmp_path / "receipt.svg"
    runner = CliRunner()
    result = runner.invoke(app, ["session", "receipt", str(fixture_transcript), "-o", str(out_path)])

    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    assert out_path.exists()
    svg = out_path.read_text()
    assert "<svg" in svg
    assert 'data-hw-frame="receipt"' in svg


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


def test_compose_receipt_from_transcript_paths(fixture_transcript: Path, tmp_path: Path) -> None:
    """The canonical receipt surface: ``compose receipt x.jsonl``, ``compose x.jsonl``
    (extension-inferred), and ``compose -`` (stdin hook JSON) all render a receipt."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    runner = CliRunner()

    # 1) explicit frame + transcript path
    a = tmp_path / "a.svg"
    r = runner.invoke(app, ["compose", "receipt", str(fixture_transcript), "-o", str(a)])
    assert r.exit_code == 0, r.output
    assert 'data-hw-frame="receipt"' in a.read_text()

    # 2) a .jsonl path alone infers the receipt frame
    b = tmp_path / "b.svg"
    r = runner.invoke(app, ["compose", str(fixture_transcript), "-o", str(b)])
    assert r.exit_code == 0, r.output
    assert 'data-hw-frame="receipt"' in b.read_text()

    # 3) `compose -` reads transcript_path from hook JSON on stdin
    c = tmp_path / "c.svg"
    hook = json.dumps({"transcript_path": str(fixture_transcript), "hook_event_name": "SessionEnd"})
    r = runner.invoke(app, ["compose", "-", "-o", str(c)], input=hook)
    assert r.exit_code == 0, r.output
    assert 'data-hw-frame="receipt"' in c.read_text()


# ── Hook-mode silent-no-op behavior ──────────────────────────────────────


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
