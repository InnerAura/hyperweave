"""Diagram/matrix spec-surface parity: one spec shape works across `compose`
and `validate`, on both the CLI's file and inline-JSON grammars, and a missing/
unsupported input fails with a clean one-line error rather than a traceback.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from typer.testing import CliRunner

from hyperweave.cli import app
from hyperweave.compose.diagram.input import diagram_preset_names

runner = CliRunner()

MINIMAL_DIAGRAM_SPEC = {
    "topology": "pipeline",
    "nodes": [{"id": "a", "label": "Fetch"}, {"id": "b", "label": "Parse"}, {"id": "c", "label": "Render"}],
    "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
}


def _no_traceback(output: str) -> bool:
    return "Traceback (most recent call last)" not in output


def test_diagram_compose_with_no_genome_flag_defaults_to_primer(tmp_path: Path) -> None:
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(MINIMAL_DIAGRAM_SPEC))
    out_svg = tmp_path / "out.svg"
    result = runner.invoke(app, ["compose", "diagram", "--spec-file", str(spec_file), "-o", str(out_svg)])
    assert result.exit_code == 0, result.output
    assert _no_traceback(result.output)
    assert 'data-hw-genome="primer"' in out_svg.read_text()


def test_diagram_compose_with_non_diagram_genome_fails_cleanly(tmp_path: Path) -> None:
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(MINIMAL_DIAGRAM_SPEC))
    result = runner.invoke(app, ["compose", "diagram", "--spec-file", str(spec_file), "-g", "brutalist"])
    assert result.exit_code == 2
    assert _no_traceback(result.output)
    assert "diagram frame is not supported by genome 'brutalist'" in result.output
    assert "fix:" in result.output
    assert "primer" in result.output


def test_bare_ir_and_envelope_both_validate_and_compose(tmp_path: Path) -> None:
    bare_file = tmp_path / "bare.json"
    bare_file.write_text(json.dumps(MINIMAL_DIAGRAM_SPEC))
    enveloped_file = tmp_path / "enveloped.json"
    enveloped_file.write_text(json.dumps({"type": "diagram", "genome": "primer", "spec": MINIMAL_DIAGRAM_SPEC}))

    for spec_file in (bare_file, enveloped_file):
        validate_result = runner.invoke(app, ["validate", str(spec_file)])
        assert validate_result.exit_code == 0, validate_result.output
        assert _no_traceback(validate_result.output)

        compose_result = runner.invoke(
            app,
            ["compose", "diagram", "--spec-file", str(spec_file), "-o", str(tmp_path / f"{spec_file.stem}.svg")],
        )
        assert compose_result.exit_code == 0, compose_result.output
        assert _no_traceback(compose_result.output)


def test_validate_bundled_preset_name_exits_zero() -> None:
    preset_name = diagram_preset_names()[0]
    result = runner.invoke(app, ["validate", preset_name])
    assert result.exit_code == 0, result.output
    assert _no_traceback(result.output)


def test_validate_nonexistent_path_fails_cleanly_not_a_traceback() -> None:
    result = runner.invoke(app, ["validate", "/nonexistent/path.json"])
    assert result.exit_code == 2
    assert _no_traceback(result.output)
    assert "/nonexistent/path.json" in result.output


def test_inline_spec_composes_and_spec_file_flag_validates(tmp_path: Path) -> None:
    inline_result = runner.invoke(
        app,
        ["compose", "diagram", "--spec", json.dumps(MINIMAL_DIAGRAM_SPEC), "-o", str(tmp_path / "inline.svg")],
    )
    assert inline_result.exit_code == 0, inline_result.output
    assert _no_traceback(inline_result.output)

    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(MINIMAL_DIAGRAM_SPEC))
    validate_result = runner.invoke(app, ["validate", "--spec-file", str(spec_file)])
    assert validate_result.exit_code == 0, validate_result.output
    assert _no_traceback(validate_result.output)


def test_mismatched_envelope_type_in_compose_errors_cleanly(tmp_path: Path) -> None:
    envelope_file = tmp_path / "mismatched.json"
    envelope_file.write_text(json.dumps({"type": "matrix", "genome": "primer", "spec": {"whatever": True}}))
    result = runner.invoke(app, ["compose", "diagram", "--spec-file", str(envelope_file)])
    assert result.exit_code == 2
    assert _no_traceback(result.output)
    assert "matrix" in result.output
    assert "diagram" in result.output


TWO_NODE_PIPELINE = {
    "topology": "pipeline",
    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
    "edges": [{"source": "a", "target": "b"}],
}


def test_two_node_pipeline_fails_validate_and_compose_with_the_same_error(tmp_path: Path) -> None:
    """The invariant: a file that validates always composes — so a file that
    can't compose (topology min-node band) must fail validate too, and both
    surfaces speak the same refusal sentence."""
    spec_file = tmp_path / "two.json"
    spec_file.write_text(json.dumps(TWO_NODE_PIPELINE))

    v = runner.invoke(app, ["validate", str(spec_file)])
    assert v.exit_code == 1
    assert "pipeline needs at least 3 nodes (got 2)" in v.output

    c = runner.invoke(app, ["compose", "diagram", "--spec-file", str(spec_file)])
    assert c.exit_code == 2
    assert _no_traceback(c.output)
    assert "pipeline needs at least 3 nodes (got 2)" in c.output


def test_mid_solve_capacity_refusal_caught_by_validate_and_compose() -> None:
    """The dag rank cap fires deep in the graph solve — past any curated
    pre-check list. validate runs the real pipeline, so it refuses exactly
    what compose refuses, with the solver's own sentence on both surfaces."""
    chain = {
        "topology": "dag",
        "nodes": [{"id": f"s{i}", "label": f"S{i}"} for i in range(6)],
        "edges": [{"source": f"s{i}", "target": f"s{i + 1}"} for i in range(5)],
    }
    v = runner.invoke(app, ["validate", "--spec", json.dumps(chain)])
    assert v.exit_code == 1
    assert "dag caps at" in v.output

    c = runner.invoke(app, ["compose", "diagram", "--spec", json.dumps(chain)])
    assert c.exit_code == 2
    assert _no_traceback(c.output)
    assert "dag caps at" in c.output


def test_unknown_genome_fails_cleanly_naming_the_known_genomes(tmp_path: Path) -> None:
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(MINIMAL_DIAGRAM_SPEC))
    result = runner.invoke(app, ["compose", "diagram", "--spec-file", str(spec_file), "-g", "nope"])
    assert result.exit_code == 2
    assert _no_traceback(result.output)
    assert "unknown genome 'nope'" in result.output
    assert "known genomes:" in result.output


def test_unknown_variant_fails_cleanly_naming_the_known_variants(tmp_path: Path) -> None:
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(MINIMAL_DIAGRAM_SPEC))
    result = runner.invoke(
        app, ["compose", "diagram", "--spec-file", str(spec_file), "-g", "primer", "--variant", "nope"]
    )
    assert result.exit_code == 2
    assert _no_traceback(result.output)
    assert "variant 'nope'" in result.output
    assert "known variants:" in result.output


@pytest.mark.parametrize(
    ("frame", "needle"),
    [("diagram", "diagram frame requires a topology"), ("matrix", "matrix frame requires a table")],
)
def test_no_input_compose_fails_cleanly_citing_working_commands(frame: str, needle: str) -> None:
    result = runner.invoke(app, ["compose", frame])
    assert result.exit_code == 2
    assert _no_traceback(result.output)
    assert needle in result.output
    assert "--spec-file" in result.output


@pytest.mark.asyncio
async def test_genome_default_parity_across_cli_http_mcp(tmp_path: Path) -> None:
    """The frame-aware genome default is ONE seam: a genome-less diagram
    compose lands on primer on all three surfaces, and a genome-less badge
    stays brutalist on all three. A default living in an adapter is how the
    surfaces drift apart (the brutalist-override bug this pins)."""
    from httpx import ASGITransport, AsyncClient

    from hyperweave.mcp.server import hw_compose
    from hyperweave.serve.app import app as http_app

    # CLI
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(MINIMAL_DIAGRAM_SPEC))
    out_diagram, out_badge = tmp_path / "d.svg", tmp_path / "b.svg"
    r = runner.invoke(app, ["compose", "diagram", "--spec-file", str(spec_file), "-o", str(out_diagram)])
    assert r.exit_code == 0, r.output
    assert 'data-hw-genome="primer"' in out_diagram.read_text()
    r = runner.invoke(app, ["compose", "badge", "T", "V", "-o", str(out_badge)])
    assert r.exit_code == 0, r.output
    assert 'data-hw-genome="brutalist"' in out_badge.read_text()

    # HTTP
    async with AsyncClient(transport=ASGITransport(app=http_app), base_url="http://hw") as client:
        resp = await client.post("/v1/compose", json={"type": "diagram", "diagram": MINIMAL_DIAGRAM_SPEC})
        assert resp.status_code == 200 and "x-hw-error-code" not in resp.headers
        assert 'data-hw-genome="primer"' in resp.text
        resp = await client.post("/v1/compose", json={"type": "badge", "title": "T", "value": "V"})
        assert resp.status_code == 200 and "x-hw-error-code" not in resp.headers
        assert 'data-hw-genome="brutalist"' in resp.text

    # MCP
    mcp_diagram = await hw_compose(type="diagram", diagram=MINIMAL_DIAGRAM_SPEC)
    assert isinstance(mcp_diagram, dict) and mcp_diagram["genome"] == "primer"
    mcp_badge = await hw_compose(type="badge", title="T", value="V")
    assert isinstance(mcp_badge, dict) and mcp_badge["genome"] == "brutalist"
