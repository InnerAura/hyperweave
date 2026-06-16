"""Diagram CLI surface: --spec-file, --preset, --markdown-out."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from typer.testing import CliRunner

from hyperweave.cli import app
from tests.conftest import FIXTURES_DIR

runner = CliRunner()


def test_spec_file_with_markdown_sidecar(tmp_path: Path) -> None:
    spec_file = tmp_path / "flow.json"
    spec_file.write_text((FIXTURES_DIR / "diagram" / "pipeline.json").read_text())
    out_svg = tmp_path / "flow.svg"
    out_md = tmp_path / "flow.md"
    result = runner.invoke(
        app,
        [
            "compose",
            "diagram",
            "--spec-file",
            str(spec_file),
            "-g",
            "primer",
            "--variant",
            "porcelain",
            "-o",
            str(out_svg),
            "--markdown-out",
            str(out_md),
        ],
    )
    assert result.exit_code == 0, result.output
    assert 'data-hw-type="diagram"' in out_svg.read_text()
    assert out_md.read_text().startswith("**One Compositor")


def test_preset_flywheel(tmp_path: Path) -> None:
    out_svg = tmp_path / "flywheel.svg"
    result = runner.invoke(
        app,
        ["compose", "diagram", "--preset", "flywheel", "-g", "primer", "-o", str(out_svg)],
    )
    assert result.exit_code == 0, result.output
    assert 'data-hw-subvariant="flywheel"' in out_svg.read_text()


def test_unknown_preset_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["compose", "diagram", "--preset", "no-such", "-g", "primer", "-o", str(tmp_path / "x.svg")],
    )
    assert result.exit_code == 2
    assert "known presets" in result.output


def test_invalid_spec_file_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    result = runner.invoke(
        app,
        ["compose", "diagram", "--spec-file", str(bad), "-g", "primer", "-o", str(tmp_path / "x.svg")],
    )
    assert result.exit_code == 2


def test_performance_composite_only_ladders(tmp_path: Path) -> None:
    """--performance composite-only: beam ladders to particle, recorded in
    the payload (CLI parity with ?performance= and the POST/MCP fields)."""
    import json
    import re

    out = tmp_path / "relay.svg"
    result = runner.invoke(
        app,
        [
            "compose",
            "diagram",
            "--preset",
            "pipeline-relay",
            "-g",
            "primer",
            "--performance",
            "composite-only",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    svg = out.read_text()
    m = re.search(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>", svg, re.DOTALL)
    assert m, "hw:payload missing"
    payload = json.loads(m.group(1))
    assert payload["rendered"]["fallback_applied"] is True
    assert set(payload["rendered"]["edge_motion"]) == {"particle"}


def test_chrome_bare_flag(tmp_path: Path) -> None:
    out = tmp_path / "bare.svg"
    result = runner.invoke(
        app,
        ["compose", "diagram", "--preset", "pipeline", "-g", "primer", "--chrome", "bare", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    svg = out.read_text()
    assert "INNERAURA LABS" not in svg
    assert 'fill="var(--dna-surface)"' not in svg


def test_edge_motion_override(tmp_path: Path) -> None:
    """--edge-motion overrides the preset's motion (parity with HTTP ?edge_motion=)."""
    import json
    import re

    out = tmp_path / "ov.svg"
    result = runner.invoke(
        app,
        ["compose", "diagram", "--preset", "pipeline", "-g", "primer", "--edge-motion", "beam", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    m = re.search(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>", out.read_text(), re.DOTALL)
    assert m, "hw:payload missing"
    assert "beam" in json.loads(m.group(1))["rendered"]["edge_motion"]


def test_edge_motion_invalid_exits_2() -> None:
    result = runner.invoke(
        app,
        ["compose", "diagram", "--preset", "pipeline", "-g", "primer", "--edge-motion", "zoom"],
    )
    assert result.exit_code == 2
    assert "must be one of" in result.output
