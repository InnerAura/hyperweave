"""Diagram/matrix spec-surface parity: one spec shape works across `compose`
and `validate`, on both the CLI's file and inline-JSON grammars, and a missing/
unsupported input fails with a clean one-line error rather than a traceback.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

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


def test_unpinned_variant_refusal_is_identical_on_validate_and_compose(tmp_path: Path) -> None:
    """The celadon repro: a brutalist-only variant with the genome unset must
    get the SAME verdict from both verbs (refused against primer, the shared
    default) — and pinning brutalist must flip both to acceptance."""
    unpinned = '{"type":"badge","variant":"celadon","spec":{"title":"S","value":"1"}}'
    v = runner.invoke(app, ["validate", "--spec", unpinned])
    assert v.exit_code == 1
    assert "unknown variant 'celadon' for genome 'primer'" in v.output

    c = runner.invoke(app, ["compose", "badge", "S", "1", "--variant", "celadon"])
    assert c.exit_code == 2
    assert _no_traceback(c.output)
    assert "unknown variant 'celadon' for genome 'primer'" in c.output

    pinned = '{"type":"badge","genome":"brutalist","variant":"celadon","spec":{"title":"S","value":"1"}}'
    v2 = runner.invoke(app, ["validate", "--spec", pinned])
    assert v2.exit_code == 0, v2.output
    c2_args = ["compose", "badge", "S", "1", "-g", "brutalist", "--variant", "celadon", "-o", str(tmp_path / "c.svg")]
    c2 = runner.invoke(app, c2_args)
    assert c2.exit_code == 0, c2.output


def test_receipt_on_non_receipt_genome_validates_and_composes_on_primer() -> None:
    """The receipt repro: a receipt on brutalist canonicalizes to primer (the
    resolver's designed fallback) on BOTH verbs — never a false rejection."""
    from hyperweave.compose.engine import compose as engine_compose
    from hyperweave.core.models import ComposeSpec

    v = runner.invoke(app, ["validate", "--spec", '{"type":"receipt","genome":"brutalist","spec":{}}'])
    assert v.exit_code == 0, v.output
    assert "valid: receipt (primer)" in v.output

    result = engine_compose(
        ComposeSpec(
            type="receipt",
            genome_id="brutalist",
            telemetry_data={"session": {"id": "x"}, "tools": [], "cost_usd": 0, "tokens": {"total": 1}},
        )
    )
    assert 'data-hw-genome="primer"' in result.svg


def test_dotted_genome_is_one_grammar_on_both_verbs(tmp_path: Path) -> None:
    """The primer.porcelain repro: the dotted spelling validates AND composes
    (it was compose-CLI-only sugar; the seam owns it on every surface now)."""
    dotted_env = json.dumps({"type": "diagram", "genome": "primer.porcelain", "spec": MINIMAL_DIAGRAM_SPEC})
    v = runner.invoke(app, ["validate", "--spec", dotted_env])
    assert v.exit_code == 0, v.output
    assert "valid: diagram (primer)" in v.output

    dotted_args = ["compose", "diagram", "--spec", json.dumps(MINIMAL_DIAGRAM_SPEC)]
    c = runner.invoke(app, [*dotted_args, "-g", "primer.porcelain", "-o", str(tmp_path / "d.svg")])
    assert c.exit_code == 0, c.output

    from hyperweave.compose.surface import SpecEnvelope, validate_surface

    report = validate_surface(SpecEnvelope(type="diagram", genome="primer.porcelain", spec=MINIMAL_DIAGRAM_SPEC))
    assert report["valid"] is True and report["genome"] == "primer"


def test_spec_file_beside_directory_of_same_name_resolves_the_bundled_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stack/ repro: bundled names double as common directory names — a
    directory is never spec input, so both verbs fall through to the bundled
    store with a note instead of an IsADirectoryError traceback."""
    (tmp_path / "stack").mkdir()
    monkeypatch.chdir(tmp_path)

    c = runner.invoke(app, ["compose", "diagram", "--spec-file", "stack", "-o", str(tmp_path / "s.svg")])
    assert c.exit_code == 0, c.output
    assert _no_traceback(c.output)
    assert "is a directory here" in c.output

    v = runner.invoke(app, ["validate", "stack"])
    assert v.exit_code == 0, v.output
    assert _no_traceback(v.output)


def test_local_file_shadowing_a_bundled_name_is_loud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pipeline-row").write_text(json.dumps(MINIMAL_DIAGRAM_SPEC))
    monkeypatch.chdir(tmp_path)
    c = runner.invoke(app, ["compose", "diagram", "--spec-file", "pipeline-row", "-o", str(tmp_path / "g.svg")])
    assert c.exit_code == 0, c.output
    assert "shadows the bundled spec" in c.output


def test_compose_missing_path_fails_cleanly_not_a_preset_dump(tmp_path: Path) -> None:
    result = runner.invoke(app, ["compose", "diagram", "--spec-file", str(tmp_path / "nope.json")])
    assert result.exit_code == 2
    assert _no_traceback(result.output)
    assert "not found" in result.output
    assert "known diagram specs" not in result.output  # a path typo never gets the preset menu


def test_envelope_missing_spec_gets_the_same_diagnosis_on_both_verbs() -> None:
    c = runner.invoke(app, ["compose", "diagram", "--spec", '{"type":"diagram"}'])
    v = runner.invoke(app, ["validate", "--spec", '{"type":"diagram"}'])
    assert c.exit_code == 2 and v.exit_code == 2
    needle = "has no 'spec' object"
    assert needle in c.output and needle in v.output


MINIMAL_MATRIX_SPEC = {
    "title": "Cost",
    "columns": [{"id": "m", "label": "MODEL"}, {"id": "c", "label": "COST", "kind": "numeric"}],
    "rows": [{"label": "Qwen", "cells": [{"value": "Qwen"}, {"value": "0.12"}]}],
}


def test_matrix_bare_ir_and_envelope_both_validate_and_compose(tmp_path: Path) -> None:
    """Matrix coverage on the spec-shape surface — the diagram twin exists;
    the matrix frame must not ride along untested."""
    bare_file = tmp_path / "bare.json"
    bare_file.write_text(json.dumps(MINIMAL_MATRIX_SPEC))
    enveloped_file = tmp_path / "enveloped.json"
    enveloped_file.write_text(json.dumps({"type": "matrix", "spec": MINIMAL_MATRIX_SPEC}))

    for spec_file in (bare_file, enveloped_file):
        v = runner.invoke(app, ["validate", str(spec_file)])
        assert v.exit_code == 0, v.output
        c = runner.invoke(
            app, ["compose", "matrix", "--spec-file", str(spec_file), "-o", str(tmp_path / f"{spec_file.stem}.svg")]
        )
        assert c.exit_code == 0, c.output
        assert _no_traceback(c.output)


def test_envelope_genome_and_variant_precedence_regression(tmp_path: Path) -> None:
    """Envelope-carried genome/variant apply ONLY when the flag is unset; an
    explicit flag always wins. Probed with refusals so precedence is
    observable through exit codes on the real CLI."""
    env_file = tmp_path / "env.json"
    env_file.write_text(json.dumps({"type": "diagram", "genome": "brutalist", "spec": MINIMAL_DIAGRAM_SPEC}))

    # Envelope genome applies when the flag is unset → brutalist can't diagram.
    r = runner.invoke(app, ["compose", "diagram", "--spec-file", str(env_file)])
    assert r.exit_code == 2
    assert "diagram frame is not supported by genome 'brutalist'" in r.output
    # An explicit -g wins over the envelope's genome.
    r = runner.invoke(
        app, ["compose", "diagram", "--spec-file", str(env_file), "-g", "primer", "-o", str(tmp_path / "o.svg")]
    )
    assert r.exit_code == 0, r.output

    bad_variant = tmp_path / "envv.json"
    bad_variant.write_text(json.dumps({"type": "diagram", "variant": "nope", "spec": MINIMAL_DIAGRAM_SPEC}))
    # Envelope variant applies when the flag is unset → refused.
    r = runner.invoke(app, ["compose", "diagram", "--spec-file", str(bad_variant)])
    assert r.exit_code == 2
    assert "unknown variant 'nope'" in r.output
    # An explicit --variant wins over the envelope's bad variant.
    override_args = ["compose", "diagram", "--spec-file", str(bad_variant), "--variant", "porcelain"]
    r = runner.invoke(app, [*override_args, "-o", str(tmp_path / "o2.svg")])
    assert r.exit_code == 0, r.output


# The cross-product parity sweep trims two axes deliberately: chrome/automata
# behave identically to brutalist for every seam gate (same non-IR paradigm
# set), and chart/stats need live connector data their seam behavior doesn't
# depend on — badge covers their class.
_SWEEP_FRAMES: dict[str, dict[str, Any]] = {
    "badge": {"title": "T", "value": "V"},
    "strip": {"title": "T", "value": "A:1"},
    "icon": {"glyph": "github"},
    "divider": {"divider_variant": "zeropoint"},
    "marquee": {"title": "A | B"},
    "matrix": MINIMAL_MATRIX_SPEC,
    "diagram": MINIMAL_DIAGRAM_SPEC,
    "receipt": {"telemetry_data": {"session": {"id": "x"}, "tools": [], "cost_usd": 0, "tokens": {"total": 1}}},
}
_SWEEP_GENOMES = ["", "primer", "brutalist", "raw", "primer.porcelain"]


@pytest.mark.parametrize("genome", _SWEEP_GENOMES)
@pytest.mark.parametrize("frame", sorted(_SWEEP_FRAMES))
def test_validate_verdict_equals_compose_outcome(frame: str, genome: str) -> None:
    """The drift-killer: for every (frame x genome spelling — omitted, plain,
    dotted, non-capable) validate's verdict must equal compose's outcome.
    This is the property the first v0.4.1 cut violated three separate ways."""
    from hyperweave.compose.surface import SpecEnvelope, compose_surface, validate_surface
    from hyperweave.core.errors import HwError

    env = SpecEnvelope(type=frame, genome=genome, spec=_SWEEP_FRAMES[frame])
    report = validate_surface(env)
    try:
        compose_surface(env)
        composed = True
    except HwError:
        composed = False
    assert report["valid"] == composed, (
        f"validate says {report['valid']} but compose {'succeeded' if composed else 'refused'} "
        f"for frame={frame!r} genome={genome!r}: {report.get('error')}"
    )


@pytest.mark.asyncio
async def test_genome_default_parity_across_cli_http_mcp(tmp_path: Path) -> None:
    """The genome default is ONE seam: a genome-less compose lands on primer
    for EVERY frame on all three surfaces, and an explicit pin still wins.
    A default living in an adapter is how the surfaces drift apart (the
    brutalist-override bug this pins)."""
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
    assert 'data-hw-genome="primer"' in out_badge.read_text()
    r = runner.invoke(app, ["compose", "badge", "T", "V", "-g", "brutalist", "-o", str(out_badge)])
    assert r.exit_code == 0, r.output
    assert 'data-hw-genome="brutalist"' in out_badge.read_text()

    # HTTP
    async with AsyncClient(transport=ASGITransport(app=http_app), base_url="http://hw") as client:
        resp = await client.post("/v1/compose", json={"type": "diagram", "diagram": MINIMAL_DIAGRAM_SPEC})
        assert resp.status_code == 200 and "x-hw-error-code" not in resp.headers
        assert 'data-hw-genome="primer"' in resp.text
        resp = await client.post("/v1/compose", json={"type": "badge", "title": "T", "value": "V"})
        assert resp.status_code == 200 and "x-hw-error-code" not in resp.headers
        assert 'data-hw-genome="primer"' in resp.text
        pinned_body = {"type": "badge", "genome": "brutalist", "title": "T", "value": "V"}
        resp = await client.post("/v1/compose", json=pinned_body)
        assert 'data-hw-genome="brutalist"' in resp.text

    # MCP
    mcp_diagram = await hw_compose(type="diagram", diagram=MINIMAL_DIAGRAM_SPEC)
    assert isinstance(mcp_diagram, dict) and mcp_diagram["genome"] == "primer"
    mcp_badge = await hw_compose(type="badge", title="T", value="V")
    assert isinstance(mcp_badge, dict) and mcp_badge["genome"] == "primer"
    mcp_pinned = await hw_compose(type="badge", genome="brutalist", title="T", value="V")
    assert isinstance(mcp_pinned, dict) and mcp_pinned["genome"] == "brutalist"


# ── stdin as a spec source ────────────────────────────────────────────────
# Heredoc-to-stdin is the canonical agent invocation. Every assertion here
# goes through the real parser and reads the sentence a caller actually gets;
# the pre-fix CLI stat'd the path before opening it, so a fifo answered
# is_file() with False and `/dev/stdin` came back "not found" on turn one.

_STDIN_SPEC = json.dumps(MINIMAL_DIAGRAM_SPEC)


@pytest.mark.parametrize("handle", ["-", "/dev/stdin", "/dev/fd/0"])
def test_compose_reads_the_spec_from_stdin(handle: str, tmp_path: Path) -> None:
    out = tmp_path / f"{handle.strip('/-').replace('/', '_')}.svg"
    result = runner.invoke(app, ["compose", "diagram", "--spec-file", handle, "-o", str(out)], input=_STDIN_SPEC)
    assert result.exit_code == 0, result.output
    assert _no_traceback(result.output)
    assert 'data-hw-type="diagram"' in out.read_text()


@pytest.mark.parametrize("handle", ["-", "/dev/stdin"])
def test_validate_reads_the_spec_from_stdin(handle: str) -> None:
    result = runner.invoke(app, ["validate", handle], input=_STDIN_SPEC)
    assert result.exit_code == 0, result.output
    assert "valid: diagram" in result.output


def test_compose_reads_a_process_substitution_path(tmp_path: Path) -> None:
    """`<(jq …)` expands to a /dev/fd/N fifo — readable, but is_file() is False.
    The gate is readability, not regular-file-ness."""
    import os
    import threading

    fifo = tmp_path / "spec.fifo"
    os.mkfifo(fifo)

    def _feed() -> None:
        with fifo.open("w") as fh:
            fh.write(_STDIN_SPEC)

    writer = threading.Thread(target=_feed, daemon=True)
    writer.start()
    out = tmp_path / "fifo.svg"
    result = runner.invoke(app, ["compose", "diagram", "--spec-file", str(fifo), "-o", str(out)])
    writer.join(timeout=5)
    assert result.exit_code == 0, result.output
    assert 'data-hw-type="diagram"' in out.read_text()


@pytest.mark.parametrize(
    ("piped", "needle"),
    [
        ("", "no spec on stdin"),
        ("   \n", "no spec on stdin"),
        ("not json", "stdin is not valid JSON"),
        ("[]", "stdin must contain a JSON object"),
    ],
)
def test_stdin_refusals_print_a_clean_sentence(piped: str, needle: str) -> None:
    result = runner.invoke(app, ["compose", "diagram", "--spec-file", "-"], input=piped)
    assert result.exit_code == 2
    assert _no_traceback(result.output)
    assert needle in result.output


def test_empty_stdin_refusal_names_the_fix() -> None:
    result = runner.invoke(app, ["compose", "diagram", "--spec-file", "-"], input="")
    assert "fix:" in result.output
    assert "--spec-file -" in result.output


def test_interactive_stdin_refuses_instead_of_hanging(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A terminal never sends EOF, so an interactive stdin must refuse at once
    rather than parking the caller's turn on a read that never returns.

    This is the one stdin case CliRunner cannot stage — its replacement stdin
    always reports isatty() False — so the guard drives the helper directly and
    still asserts the sentence a caller reads, plus the exit code.
    """
    import click

    from hyperweave import cli

    class _Tty:
        @staticmethod
        def isatty() -> bool:
            return True

        @staticmethod
        def read() -> str:  # pragma: no cover - reached only if the guard fails
            raise AssertionError("read() on an interactive stdin would block")

    monkeypatch.setattr(cli.sys, "stdin", _Tty())
    with pytest.raises(click.exceptions.Exit) as exc:
        cli._read_stdin_spec()
    assert exc.value.exit_code == 2
    printed = capsys.readouterr().err
    assert "no spec on stdin" in printed
    assert "fix:" in printed


def test_stdin_handling_leaves_preset_dispatch_alone() -> None:
    """The stdin branch matches three literal names and returns before any
    stat, so the bundled-spec menu and the missing-path error keep their text."""
    unknown = runner.invoke(app, ["compose", "diagram", "--spec-file", "no-such"])
    assert unknown.exit_code == 2
    assert "unknown diagram spec 'no-such'" in unknown.output
    assert "known diagram specs:" in unknown.output

    missing = runner.invoke(app, ["compose", "diagram", "--spec-file", "./nope.json"])
    assert missing.exit_code == 2
    assert "not found" in missing.output

    named = runner.invoke(app, ["validate", diagram_preset_names()[0]])
    assert named.exit_code == 0, named.output
