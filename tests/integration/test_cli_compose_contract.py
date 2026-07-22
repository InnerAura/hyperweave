"""CLI compose output contract — characterization net for the spec-construction seam.

Baseline: the post-topology-error-surfacing tree (NOT the alpha.7 tag) — the
shared exception-mapping helper these tests protect carries that message fix,
so a bisect landing here should read these assertions against that baseline.

The pinned invariant: however the CLI builds its ComposeSpec, the default
stdout/file output stays byte-identical to a direct engine compose of the same
spec (identical inputs → identical files is a product guarantee, so byte
equality is the honest characterization).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from typer.testing import CliRunner

from hyperweave.cli import app
from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

runner = CliRunner()

# The only legitimate byte difference between two composes of the same spec is
# wall-clock metadata (hw:created, the RDF dc:date, and their JSON echoes) —
# normalize every ISO-8601 stamp; everything else must match exactly.
_STAMPS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+00:00")


def _normalize(svg: str) -> str:
    return _STAMPS.sub("TS", svg)


def _cli_svg(args: list[str]) -> str:
    result = runner.invoke(app, args)
    assert result.exit_code == 0, f"compose exit {result.exit_code}: {result.output}"
    return result.stdout


def test_cli_compose_badge_stdout_matches_direct_engine_compose() -> None:
    cli_svg = _cli_svg(["compose", "badge", "BUILD", "passing"])
    direct = compose(ComposeSpec(type="badge", genome_id="brutalist", title="BUILD", value="passing")).svg
    assert _normalize(cli_svg) == _normalize(direct)


def test_cli_compose_strip_stdout_matches_direct_engine_compose() -> None:
    cli_svg = _cli_svg(["compose", "strip", "REPO", "STARS:42"])
    direct = compose(ComposeSpec(type="strip", genome_id="brutalist", title="REPO", value="STARS:42")).svg
    assert _normalize(cli_svg) == _normalize(direct)


def test_cli_compose_diagram_preset_matches_direct_engine_compose() -> None:
    bundled = resolve_bundled_spec("diagram", "rag-pipeline")
    cli_svg = _cli_svg(["compose", "diagram", "-g", "primer", "--spec-file", "rag-pipeline"])
    direct = compose(ComposeSpec(type="diagram", genome_id="primer", diagram=bundled.value)).svg
    assert _normalize(cli_svg) == _normalize(direct)


def test_cli_compose_png_writes_the_projected_bytes(tmp_path: Path) -> None:
    import pytest

    pytest.importorskip("resvg_py")
    from hyperweave.formats import project

    out = tmp_path / "b.png"
    result = runner.invoke(app, ["compose", "badge", "BUILD", "passing", "--format", "png", "-o", str(out)])
    assert result.exit_code == 0, result.output
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"

    direct = compose(ComposeSpec(type="badge", genome_id="brutalist", title="BUILD", value="passing")).svg
    assert data == project(direct, "png").data  # png rasterizes the static projection (created stamp excluded)


def test_cli_compose_faces_pair_matches_direct_face_bakes(tmp_path: Path) -> None:
    from hyperweave.core.surface_spec import expand_surface_preset

    bundled = resolve_bundled_spec("diagram", "rag-pipeline")
    twin = expand_surface_preset("twin", "", "")
    out = tmp_path / "d.svg"
    result = runner.invoke(
        app,
        [
            "compose",
            "diagram",
            "-g",
            "primer",
            "--spec-file",
            "rag-pipeline",
            "--surface",
            "twin",
            "--faces",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output

    base = ComposeSpec(
        type="diagram",
        genome_id="primer",
        diagram=bundled.value,
        ground=twin.ground.value,
        palette=twin.palette.value,
    )
    for face in ("light", "dark"):
        written = (tmp_path / f"d-{face}.svg").read_text()
        direct = compose(base.model_copy(update={"palette": "fixed", "surface_face": face})).svg
        assert _normalize(written) == _normalize(direct), f"--faces {face} drifted from the direct face bake"


def test_cli_compose_rejects_malformed_diagram_spec_with_clean_error(tmp_path: Path) -> None:
    """A structurally invalid spec exits 2 with the rule text — never a traceback."""
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "topology": "hub",
                "title": "Probe",
                "nodes": [
                    {"id": "gw", "label": "Gateway"},
                    {"id": "b", "label": "Billing"},
                    {"id": "p", "label": "Postgres"},
                ],
                "edges": [{"source": "gw", "target": "b"}, {"source": "b", "target": "p"}],
            }
        )
    )
    result = runner.invoke(app, ["compose", "diagram", "-g", "primer", "--spec-file", str(bad)])
    assert result.exit_code == 2, f"expected clean exit 2, got {result.exit_code}: {result.output}"
    combined = result.output + (result.stderr or "")
    assert "Traceback" not in combined
    assert "not incident to the hub node" in combined


def test_cli_compose_respond_envelope_names_the_exits_and_keeps_stdout_clean() -> None:
    """Without -o the envelope's url is a dead handle once the process exits —
    the resolve hint rides stderr; stdout stays one clean JSON document."""
    result = runner.invoke(app, ["compose", "badge", "BUILD", "passing", "--respond", "envelope"])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["envelope"]["id"]
    assert doc["url"].startswith("/v1/a/")
    assert "hyperweave serve" in result.stderr
    assert "-o" in result.stderr


def test_cli_compose_respond_envelope_with_out_writes_the_svg(tmp_path: Path) -> None:
    out = tmp_path / "b.svg"
    result = runner.invoke(app, ["compose", "badge", "BUILD", "passing", "--respond", "envelope", "-o", str(out)])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    written = out.read_text()
    assert "<svg" in written
    from hyperweave.core.envelope import extract_envelope

    envelope = extract_envelope(written)
    assert envelope is not None and envelope["id"] == doc["envelope"]["id"]
    assert "hyperweave serve" not in result.stderr  # the exit exists; no hint needed


def test_cli_compose_respond_json_carries_svg_and_markdown_inline() -> None:
    result = runner.invoke(app, ["compose", "badge", "BUILD", "passing", "--respond", "json"])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["svg"].startswith("<svg")
    assert doc["width"] > 0 and doc["height"] > 0
    assert "markdown" in doc


def test_compose_prints_verb_pointer_on_stderr_without_polluting_stdout() -> None:
    """Every compose advertises its artifact id + verbs on stderr; stdout
    stays exactly the artifact bytes."""
    result = runner.invoke(app, ["compose", "badge", "BUILD", "passing"])
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("<svg")
    assert "verbs over the seed" in result.stderr
    assert "extract" in result.stderr and "transform" in result.stderr
    from hyperweave.core.envelope import extract_envelope

    envelope = extract_envelope(result.stdout)
    assert envelope is not None
    assert envelope["id"].removeprefix("sha256:")[:12] in result.stderr


def test_cli_compose_faces_and_respond_are_exclusive(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "compose",
            "diagram",
            "-g",
            "primer",
            "--spec-file",
            "rag-pipeline",
            "--surface",
            "twin",
            "--faces",
            "-o",
            str(tmp_path / "d.svg"),
            "--respond",
            "envelope",
        ],
    )
    assert result.exit_code == 2
    assert "exclusive" in (result.stderr or result.output)
