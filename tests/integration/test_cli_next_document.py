"""The machine-readable compose document: `next` + `text` on stdout.

The verb hint used to be prose on stderr — the stream an agent is trained to
treat as noise — so a cold agent did archaeology instead of running the verbs.
The governing rule these tests pin: **stdout carries one machine-readable
document unless it is carrying the artifact.**

Guard Law throughout: every assertion goes through the real CLI parser, and the
printed commands are RUN, not just shape-checked. A suggestion that errors is
worse than no suggestion.
"""

from __future__ import annotations

import json
import re
import shlex
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from typer.testing import CliRunner

from hyperweave.cli import app

runner = CliRunner()

_SPEC = {
    "topology": "pipeline",
    "title": "A pipeline",
    "subtitle": "the caption line",
    "nodes": [{"id": "a", "label": "Fetch"}, {"id": "b", "label": "Parse"}, {"id": "c", "label": "Render"}],
    "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
}


def _compose(args: list[str]) -> str:
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return result.stdout


# ── one document per path ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param([], id="output-only"),
        pytest.param(["--respond", "envelope"], id="respond-envelope"),
        pytest.param(["--respond", "json"], id="respond-json"),
        pytest.param(["--respond", "envelope", "--faces", "--surface", "twin"], id="respond-and-faces-refused"),
    ],
)
def test_stdout_is_exactly_one_json_document(extra: list[str], tmp_path: Path) -> None:
    """json.loads over the WHOLE of stdout — catches a leaked second document
    and trailing noise in one assertion. --respond returns before the delivery
    tail, so `--respond … -o` must not print twice."""
    out = tmp_path / "a.svg"
    args = ["compose", "diagram", "--spec", json.dumps(_SPEC), "-g", "primer", "-o", str(out), *extra]
    result = runner.invoke(app, args)
    if "--faces" in extra:  # --faces and --respond refuse each other
        assert result.exit_code == 2
        assert "exclusive" in result.output
        return
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert isinstance(doc, dict)
    assert doc["next"]


def test_compose_without_output_streams_bytes_not_json() -> None:
    """No -o means stdout is carrying the artifact; a JSON document there would
    corrupt every pipe."""
    stdout = _compose(["compose", "diagram", "--spec", json.dumps(_SPEC), "-g", "primer"])
    assert stdout.startswith("<svg")
    with pytest.raises(json.JSONDecodeError):
        json.loads(stdout)


def test_the_stderr_verb_hint_survives_for_the_bytes_path() -> None:
    """The prose line is all a bytes-to-stdout compose can carry, so it stays."""
    result = runner.invoke(app, ["compose", "diagram", "--spec", json.dumps(_SPEC), "-g", "primer"])
    assert result.exit_code == 0, result.output
    assert "verbs over the seed" in result.output


# ── the document's contents ──────────────────────────────────────────────


def test_document_names_the_artifact_and_every_file_written(tmp_path: Path) -> None:
    out, md = tmp_path / "a.svg", tmp_path / "a.md"
    doc = json.loads(
        _compose(
            [
                "compose",
                "diagram",
                "--spec",
                json.dumps(_SPEC),
                "-g",
                "primer",
                "-o",
                str(out),
                "--markdown-out",
                str(md),
            ]
        )
    )
    assert doc["artifact"] and len(doc["artifact"]) == 12
    assert doc["wrote"] == [str(out), str(md)]


def test_diagram_document_names_what_title_feeds(tmp_path: Path) -> None:
    """The reported surprise: `title` is accepted, reaches <title>/<desc>/the
    payload/the markdown lead, and draws as the caption only when `subtitle` is
    empty. The document says so instead of leaving it to be discovered."""
    out = tmp_path / "a.svg"
    doc = json.loads(_compose(["compose", "diagram", "--spec", json.dumps(_SPEC), "-g", "primer", "-o", str(out)]))
    assert "<title>" in doc["text"]["title"]
    assert "caption" in doc["text"]["title"]
    assert "caption" in doc["text"]["subtitle"]
    # …and the claim is true of the artifact it just wrote.
    svg = out.read_text()
    assert "<title" in svg and "A pipeline</title>" in svg
    assert "the caption line" in svg


def test_a_frame_with_unremarkable_text_omits_the_block(tmp_path: Path) -> None:
    out = tmp_path / "b.svg"
    doc = json.loads(_compose(["compose", "badge", "BUILD", "passing", "-o", str(out)]))
    assert "text" not in doc


def test_faces_lists_both_files_and_a_resolving_handle(tmp_path: Path) -> None:
    out = tmp_path / "t.svg"
    doc = json.loads(
        _compose(
            [
                "compose",
                "diagram",
                "--spec",
                json.dumps(_SPEC),
                "-g",
                "primer",
                "--surface",
                "twin",
                "--faces",
                "-o",
                str(out),
            ]
        )
    )
    assert doc["wrote"] == [str(tmp_path / "t-light.svg"), str(tmp_path / "t-dark.svg")]
    assert doc["next"][0]["command"].endswith("t-light.svg --respond payload")


# ── --respond: siblings, never a nested key ──────────────────────────────


def test_respond_envelope_keeps_its_seed_byte_identical(tmp_path: Path) -> None:
    """`next`/`text` are TOP-LEVEL siblings of the wrapper's own keys. The
    envelope object is the content-addressed seed extract/verify read back, so
    absorbing a CLI hint would change what the artifact hashes to."""
    from hyperweave.compose.engine import compose
    from hyperweave.core.envelope import extract_envelope
    from hyperweave.core.models import ComposeSpec

    out = tmp_path / "a.svg"
    doc = json.loads(
        _compose(
            ["compose", "diagram", "--spec", json.dumps(_SPEC), "-g", "primer", "--respond", "envelope", "-o", str(out)]
        )
    )
    for hint in ("next", "text", "artifact", "wrote"):
        assert hint in doc, hint
        assert hint not in doc["envelope"], f"{hint} leaked into the seed"

    direct = extract_envelope(compose(ComposeSpec(type="diagram", genome_id="primer", diagram=_SPEC)).svg) or {}
    carried = dict(doc["envelope"])
    # The only legitimate difference between two composes of one spec is the
    # wall-clock stamp (the byte-parity convention in test_cli_compose_contract).
    stamps = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+00:00")

    def _normalize(env: dict[str, object]) -> str:
        return stamps.sub("TS", json.dumps(env, sort_keys=True))

    assert _normalize(carried) == _normalize(direct)


def test_respond_json_keeps_its_own_keys(tmp_path: Path) -> None:
    out = tmp_path / "a.svg"
    doc = json.loads(
        _compose(
            ["compose", "diagram", "--spec", json.dumps(_SPEC), "-g", "primer", "--respond", "json", "-o", str(out)]
        )
    )
    assert doc["svg"].startswith("<svg")
    assert doc["width"] > 0 and doc["height"] > 0
    assert doc["next"]


def test_respond_without_output_hands_back_a_usable_handle() -> None:
    """No file to point at, so the handle is the stored-artifact url the verbs
    already accept — never a fabricated filename."""
    doc = json.loads(
        _compose(["compose", "diagram", "--spec", json.dumps(_SPEC), "-g", "primer", "--respond", "envelope"])
    )
    assert doc["wrote"] == []
    assert doc["url"] and doc["url"] in doc["next"][0]["command"]


# ── the printed commands RUN ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("frame", "args"),
    [
        pytest.param("diagram", ["compose", "diagram", "--spec", json.dumps(_SPEC), "-g", "primer"], id="diagram"),
        pytest.param("matrix", ["compose", "matrix", "--spec-file", "connectors", "-g", "primer"], id="matrix"),
        pytest.param("badge", ["compose", "badge", "BUILD", "passing"], id="badge"),
    ],
)
def test_every_suggested_command_runs(
    frame: str, args: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Guard Law in full: run the literal printed sentence through the real
    parser. Advertising `transform` on a badge printed a command that exits 2.

    The suggestions carry RELATIVE output paths (``-o next.svg``) because that
    is what reads well in a terminal, so this runs from ``tmp_path``: without
    the chdir the transform suggestion minted ``next.svg`` into the repo root
    on every full-suite run."""
    monkeypatch.chdir(tmp_path)
    out = tmp_path / f"{frame}.svg"
    doc = json.loads(_compose([*args, "-o", str(out)]))
    assert doc["next"], "every frame advertises at least one verb"
    for entry in doc["next"]:
        argv = shlex.split(entry["command"])
        assert argv[0] == "hyperweave", entry["command"]
        result = runner.invoke(app, argv[1:], catch_exceptions=False)
        assert result.exit_code == 0, f"{entry['command']!r} exited {result.exit_code}: {result.output}"


def test_transform_is_advertised_only_where_it_is_accepted(tmp_path: Path) -> None:
    """Sourced from transform's own allowlist, so the two cannot drift."""
    from hyperweave.verbs.transform import transformable_frames

    diagram = json.loads(
        _compose(["compose", "diagram", "--spec", json.dumps(_SPEC), "-g", "primer", "-o", str(tmp_path / "d.svg")])
    )
    badge = json.loads(_compose(["compose", "badge", "BUILD", "passing", "-o", str(tmp_path / "b.svg")]))

    assert "diagram" in transformable_frames() and "badge" not in transformable_frames()
    assert "transform" in {entry["verb"] for entry in diagram["next"]}
    assert "transform" not in {entry["verb"] for entry in badge["next"]}


def test_the_query_example_resolves_a_real_field(tmp_path: Path) -> None:
    """A printed query must hit the deterministic field map, not fall through
    to the intent string dressed up as an answer."""
    out = tmp_path / "d.svg"
    doc = json.loads(_compose(["compose", "diagram", "--spec", json.dumps(_SPEC), "-g", "primer", "-o", str(out)]))
    query = next(entry for entry in doc["next"] if entry["verb"] == "query")
    result = runner.invoke(app, shlex.split(query["command"])[1:])
    assert result.exit_code == 0, result.output
    answer = json.loads(result.stdout)
    assert answer["field"] == "data.n"
    assert answer["answer"] == "3"
