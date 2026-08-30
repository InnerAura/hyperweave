"""The agent-cost budgets, pinned through the real CLI.

The recorded baseline for one supplied-facts diagram was 38 shell commands and
44 activity blocks, with one composed SVG printed into context (116,626
characters — 22.6% of the session's shell output). The budgets from the agent
contract: supplied-facts ≤ 8 tool operations and ≤ 10 KB of command output;
existing-artifact transform ≤ 6 and ≤ 10 KB.

These are regression pins against the scripted canonical flows, not published
performance claims and not a benchmark — one machine, deterministic inputs.
A failure here means the contract regressed: a flow started needing more
commands, or a command started printing more than an agent should ever pay
to read.
"""

from __future__ import annotations

import json
from typing import Any

from typer.testing import CliRunner

runner = CliRunner()

_SPEC = {
    "topology": "pipeline",
    "title": "Budget probe",
    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
    "edges": [{"source": "a", "target": "b", "label": "ship"}, {"source": "b", "target": "c"}],
}

SUPPLIED_FACTS_MAX_OPS = 8
TRANSFORM_MAX_OPS = 6
OUTPUT_BUDGET_BYTES = 10_000


def _run(args: list[str]) -> str:
    from hyperweave.cli import app

    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return result.output


class TestSuppliedFactsFlow:
    def test_two_commands_inside_the_budget(self, tmp_path: Any) -> None:
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(_SPEC))
        out = tmp_path / "flow.svg"
        commands = [
            ["discover", "--agent", "--topology", "pipeline"],
            [
                "compose",
                "diagram",
                "--spec-file",
                str(spec_file),
                "-o",
                str(out),
                "--ground",
                "opaque",
                "--palette",
                "fixed",
                "--proof",
                "--respond",
                "report",
            ],
        ]
        assert len(commands) <= SUPPLIED_FACTS_MAX_OPS
        total = sum(len(_run(cmd)) for cmd in commands)
        assert total <= OUTPUT_BUDGET_BYTES, f"flow printed {total} bytes against the {OUTPUT_BUDGET_BYTES} budget"
        assert out.exists() and (tmp_path / "flow.proof.json").exists()

    def test_no_command_prints_the_svg(self, tmp_path: Any) -> None:
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(_SPEC))
        output = _run(
            [
                "compose",
                "diagram",
                "--spec-file",
                str(spec_file),
                "-o",
                str(tmp_path / "x.svg"),
                "--respond",
                "report",
            ]
        )
        assert "<svg" not in output


class TestTransformFlow:
    def test_one_command_inside_the_budget(self, tmp_path: Any) -> None:
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(_SPEC))
        src = tmp_path / "src.svg"
        _run(["compose", "diagram", "--spec-file", str(spec_file), "-o", str(src)])

        commands = [
            [
                "transform",
                str(src),
                "--patch-json",
                '[{"op": "replace", "path": "/edges/0/label", "value": "deploy"}]',
                "--intent",
                "rename the ship edge",
            ]
        ]
        assert len(commands) <= TRANSFORM_MAX_OPS
        total = sum(len(_run(cmd)) for cmd in commands)
        assert total <= OUTPUT_BUDGET_BYTES, f"transform printed {total} bytes against the {OUTPUT_BUDGET_BYTES} budget"
