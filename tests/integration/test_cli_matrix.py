"""Matrix CLI surface: --spec-file (path or bundled-spec name), --markdown-out."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from typer.testing import CliRunner

from hyperweave.cli import app
from tests.conftest import FIXTURES_DIR

runner = CliRunner()


def test_spec_file_with_markdown_sidecar(tmp_path: Path) -> None:
    spec_file = tmp_path / "table.json"
    spec_file.write_text((FIXTURES_DIR / "matrix" / "check.json").read_text())
    out_svg = tmp_path / "matrix.svg"
    out_md = tmp_path / "matrix.md"
    result = runner.invoke(
        app,
        [
            "compose",
            "matrix",
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
    assert 'data-hw-subvariant="check"' in out_svg.read_text()
    assert out_md.read_text().startswith("**Format comparison**")


def test_bundled_spec_name_connectors(tmp_path: Path) -> None:
    """A bare --spec-file name resolves against the bundled-spec store."""
    out_svg = tmp_path / "connectors.svg"
    result = runner.invoke(app, ["compose", "matrix", "--spec-file", "connectors", "-g", "primer", "-o", str(out_svg)])
    assert result.exit_code == 0, result.output
    assert 'data-hw-subvariant="registry"' in out_svg.read_text()


def test_unknown_bundled_spec_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["compose", "matrix", "--spec-file", "nope", "-g", "primer"])
    assert result.exit_code == 2
    assert "unknown matrix spec" in result.output


def test_retired_preset_flag_exits_2(tmp_path: Path) -> None:
    """--preset is retired for one release with a migration message."""
    result = runner.invoke(app, ["compose", "matrix", "--preset", "connectors", "-g", "primer"])
    assert result.exit_code == 2
    assert "--preset was removed" in result.output


def test_invalid_spec_file_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    result = runner.invoke(app, ["compose", "matrix", "--spec-file", str(bad), "-g", "primer"])
    assert result.exit_code == 2
    assert "not valid JSON" in result.output


def test_data_tokens_simple_table(tmp_path: Path) -> None:
    out_svg = tmp_path / "tokens.svg"
    result = runner.invoke(
        app,
        ["compose", "matrix", "--data", "kv:PHASE=alpha,kv:GATE=green", "-g", "primer", "-o", str(out_svg)],
    )
    assert result.exit_code == 0, result.output
    svg = out_svg.read_text()
    assert "PHASE" in svg and "alpha" in svg


def test_fixture_spec_round_trips_from_payload(tmp_path: Path) -> None:
    """The CLI artifact's embedded payload re-validates as a MatrixSpec."""
    import re

    from hyperweave.core.matrix import MatrixSpec

    spec_file = tmp_path / "t.json"
    spec_file.write_text((FIXTURES_DIR / "matrix" / "readcost.json").read_text())
    out_svg = tmp_path / "m.svg"
    args = ["compose", "matrix", "--spec-file", str(spec_file), "-g", "primer", "-o", str(out_svg)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    payload = re.search(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]>", out_svg.read_text(), re.S)
    assert payload is not None
    assert MatrixSpec.model_validate(json.loads(payload.group(1))).title == "Agent read cost"
