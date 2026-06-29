"""BUG-005 — Codex shell error classification (command-aware exit-code table).

The parser used a substring heuristic that never matched Codex's failure encoding
(`Process exited with code N`), so every receipt reported errors=0. The fix is a
command-aware exit-code table: exit-1 from a predicate tool (grep/rg/test/diff) is
a normal "no match" SUCCESS; the same code elsewhere is a real ERROR; control-kills
are INTERRUPTED; a backgrounded process is NO_VERDICT.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hyperweave.telemetry.codex_parser import _classify_exit, parse_transcript
from hyperweave.telemetry.models import ToolOutcome as O


def _exit_output(code: int) -> str:
    return f"Chunk ID: ab12\nWall time: 0.10 seconds\nProcess exited with code {code}\nOutput:\n(...)"


def _transcript(tmp_path: Path, calls: list[tuple[str, str, str]]) -> Path:
    """Build a minimal Codex transcript from (call_id, command, output) triples."""
    lines: list[str] = []
    for cid, cmd, out in calls:
        lines.append(
            json.dumps(
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": json.dumps({"cmd": cmd}),
                        "call_id": cid,
                    },
                }
            )
        )
        lines.append(
            json.dumps(
                {
                    "timestamp": "2026-01-01T00:00:01Z",
                    "type": "response_item",
                    "payload": {"type": "function_call_output", "call_id": cid, "output": out},
                }
            )
        )
    path = tmp_path / "codex.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "code,command,expected",
    [
        (0, "rg foo", O.SUCCESS),
        (1, "rg foo", O.SUCCESS),  # predicate no-match
        (1, "cd repo && grep -q x f", O.SUCCESS),  # cd-wrapped predicate
        (1, 'bash -lc "test -f x"', O.SUCCESS),  # bash-wrapped predicate
        (1, "python build.py", O.ERROR),  # generic exit-1
        (2, "rg foo", O.ERROR),  # rg exit-2 is a REAL error (the trap)
        (101, "cargo build", O.ERROR),  # rust panic
        (130, "sleep 9", O.INTERRUPTED),  # SIGINT
        (137, "x", O.INTERRUPTED),  # OOM kill
        (139, "seg", O.ERROR),  # SIGSEGV crash, NOT interrupted
    ],
)
def test_classification_table(code: int, command: str, expected: O) -> None:
    assert _classify_exit(code, command) is expected


def test_synthetic_transcript_outcomes(tmp_path: Path) -> None:
    path = _transcript(
        tmp_path,
        [
            ("c1", "rg foo", _exit_output(1) + "\n0 matches"),  # predicate → SUCCESS
            ("c2", "python build.py", _exit_output(1)),  # generic → ERROR
            ("c3", "sleep 99", _exit_output(130)),  # SIGINT → INTERRUPTED
            ("c4", "npm run dev", "Command: npm run dev\nProcess running with session ID 12345\n"),  # → NO_VERDICT
        ],
    )
    by_id = {tc.tool_id: tc.outcome for tc in parse_transcript(path).tool_calls}
    assert by_id["c1"] is O.SUCCESS
    assert by_id["c2"] is O.ERROR
    assert by_id["c3"] is O.INTERRUPTED
    assert by_id["c4"] is O.NO_VERDICT


def test_real_fixture_reports_nonzero_errors() -> None:
    # The whole point of the bug: this fixture always parsed to errors=0.
    fixture = Path(__file__).parent.parent / "fixtures" / "codex_session.jsonl"
    errors = [tc for tc in parse_transcript(fixture).tool_calls if tc.outcome is O.ERROR]
    assert errors, "exit-1/exit-2 shell calls must classify as ERROR (BUG-005)"
