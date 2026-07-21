"""Diagram CLI surface: --spec-file (path or bundled-spec name), --markdown-out."""

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


def test_bundled_spec_name_flywheel(tmp_path: Path) -> None:
    """A bare --spec-file name resolves against the bundled-spec store."""
    out_svg = tmp_path / "flywheel.svg"
    result = runner.invoke(
        app,
        ["compose", "diagram", "--spec-file", "flywheel-orbit", "-g", "primer", "-o", str(out_svg)],
    )
    assert result.exit_code == 0, result.output
    assert 'data-hw-subvariant="flywheel"' in out_svg.read_text()


def test_unknown_bundled_spec_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["compose", "diagram", "--spec-file", "no-such", "-g", "primer", "-o", str(tmp_path / "x.svg")],
    )
    assert result.exit_code == 2
    assert "unknown diagram spec" in result.output


def test_retired_preset_flag_exits_2(tmp_path: Path) -> None:
    """--preset is retired for one release with a migration message."""
    result = runner.invoke(app, ["compose", "diagram", "--preset", "pipeline", "-g", "primer"])
    assert result.exit_code == 2
    assert "--preset was removed" in result.output


def test_invalid_spec_file_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    result = runner.invoke(
        app,
        ["compose", "diagram", "--spec-file", str(bad), "-g", "primer", "-o", str(tmp_path / "x.svg")],
    )
    assert result.exit_code == 2


def test_performance_composite_only_same_grammar(tmp_path: Path) -> None:
    """--performance composite-only renders the same kit grammar (dash |
    particle is compositor-only by construction) — CLI parity with
    ?performance= and the POST/MCP fields."""
    import json
    import re

    out = tmp_path / "relay.svg"
    result = runner.invoke(
        app,
        [
            "compose",
            "diagram",
            "--spec-file",
            "rag-pipeline",
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
    assert payload["rendered"]["performance"] == "composite-only"
    assert set(payload["rendered"]["edge_motion"]) <= {"dash", "particle"}


def test_diagram_renders_caption_not_masthead(tmp_path: Path) -> None:
    """`--chrome` is retired — every CLI diagram compose renders kit chrome
    (caption): no masthead band, no brand-footer line."""
    out = tmp_path / "caption.svg"
    result = runner.invoke(
        app,
        ["compose", "diagram", "--spec-file", "rag-pipeline", "-g", "primer", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    svg = out.read_text()
    assert "INNERAURA LABS" not in svg
    assert 'data-hw-region="masthead"' not in svg


def test_chrome_flag_removed(tmp_path: Path) -> None:
    out = tmp_path / "rejected.svg"
    result = runner.invoke(
        app,
        ["compose", "diagram", "--spec-file", "rag-pipeline", "-g", "primer", "--chrome", "bare", "-o", str(out)],
    )
    assert result.exit_code != 0
    assert "--chrome" in result.output or "no such option" in result.output.lower()


def test_edge_motion_override(tmp_path: Path) -> None:
    """--edge-motion overrides the preset's motion (parity with HTTP ?edge_motion=)."""
    import json
    import re

    out = tmp_path / "ov.svg"
    result = runner.invoke(
        app,
        [
            "compose",
            "diagram",
            "--spec-file",
            "rag-pipeline",
            "-g",
            "primer",
            "--edge-motion",
            "dash",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    m = re.search(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>", out.read_text(), re.DOTALL)
    assert m, "hw:payload missing"
    assert "dash" in json.loads(m.group(1))["rendered"]["edge_motion"]


def test_edge_motion_invalid_exits_2() -> None:
    result = runner.invoke(
        app,
        ["compose", "diagram", "--spec-file", "rag-pipeline", "-g", "primer", "--edge-motion", "zoom"],
    )
    assert result.exit_code == 2
    assert "must be one of" in result.output


def test_hub_incidence_error_names_the_recompose_path() -> None:
    """A hub spec with a satellite-to-satellite edge fails with the exit named:
    the printed message carries the actual rule text (not an error count) and
    points at the free-graph recompose."""
    import json

    spec = json.dumps(
        {
            "type": "diagram",
            "genome": "primer",
            "spec": {
                "topology": "hub",
                "title": "Probe",
                "nodes": [
                    {"id": "gw", "label": "Gateway"},
                    {"id": "billing", "label": "Billing"},
                    {"id": "pg", "label": "Postgres"},
                ],
                "edges": [
                    {"source": "gw", "target": "billing"},
                    {"source": "billing", "target": "pg"},
                ],
            },
        }
    )
    result = runner.invoke(app, ["validate", "--spec", spec])
    assert result.exit_code == 1
    combined = result.output + result.stderr
    assert "not incident to the hub node" in combined
    assert "recompose with topology dag or lanes" in combined
