"""extract / verify / diff / query — the read half."""

from __future__ import annotations

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.errors import HwError
from hyperweave.core.models import ComposeSpec
from hyperweave.verbs import diff, extract, query, transform, verify

_MATRIX = {
    "title": "Cost",
    "columns": [{"id": "m", "label": "MODEL"}, {"id": "c", "label": "COST", "kind": "numeric"}],
    "rows": [
        {"label": "Qwen", "cells": [{"value": "Qwen"}, {"value": "0.12"}]},
        {"label": "GPT", "cells": [{"value": "GPT"}, {"value": "2.50"}]},
    ],
}


def _matrix() -> str:
    return compose(ComposeSpec(type="matrix", genome_id="primer", matrix=_MATRIX)).svg


def test_extract_three_depths() -> None:
    svg = _matrix()
    assert extract(svg, respond="envelope").envelope["k"] == "matrix"
    assert extract(svg, respond="payload").payload["title"] == "Cost"
    assert extract(svg, respond="markdown").markdown.startswith("**Cost**")


def test_extract_payload_is_lossless_replant() -> None:
    svg = _matrix()
    payload = extract(svg, respond="payload").payload
    # replant → byte-identical payload id
    re_svg = compose(ComposeSpec(type="matrix", genome_id="primer", matrix=payload)).svg
    assert verify(re_svg).computed_id == verify(svg).computed_id


def test_verify_detects_match_and_mismatch() -> None:
    svg = _matrix()
    assert verify(svg).hash_valid is True
    tampered = svg.replace("Qwen", "Qwxn", 1)  # changes payload + rendered, id no longer matches
    assert verify(tampered).hash_valid is False


def test_verify_reports_well_formed_container() -> None:
    assert verify(_matrix()).well_formed is True


def test_verify_flags_non_well_formed_xml_independent_of_hash_match() -> None:
    """A bare ``&`` in root character data breaks the container, never the seed.

    The corruption sits outside the metadata CDATA, so the hash proof stays
    intact — the two checks must report independently.
    """
    svg = _matrix()
    corrupted = svg.replace("</svg>", "&</svg>", 1)
    result = verify(corrupted)
    assert result.well_formed is False
    assert result.hash_valid is True


def test_query_envelope_fields() -> None:
    svg = _matrix()
    assert query(svg, "how many rows?").answer == "2"
    assert query(svg, "how many rows?").field == "data.rows_total"
    assert query(svg, "what genome?").answer.startswith("primer")
    assert query(svg, "what frame type?").answer == "matrix"
    assert query(svg, "blah blah unanswerable").confidence == "inferred"


def test_diff_reports_cell_flip_excludes_lineage() -> None:
    svg = _matrix()
    r = transform(svg, [{"op": "replace", "path": "/rows/1/cells/1/value", "value": "9.99"}], ts="t")
    d = diff(svg, r.svg)
    assert d.same is False
    assert any(c.get("row") == "GPT" and c.get("to") == {"value": "9.99"} for c in d.changed)
    # the transform added lineage to r.svg — it must NOT surface as a content change
    assert not any("lineage" in str(c) for c in d.changed)


def test_diff_identical_is_same() -> None:
    svg = _matrix()
    assert diff(svg, svg).same is True


def test_diff_different_frame_types_rejected() -> None:
    matrix = _matrix()
    diagram = compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            diagram={
                "topology": "pipeline",
                "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
            },
        )
    ).svg
    with pytest.raises(HwError):
        diff(matrix, diagram)


def test_verify_cli_exit_codes_discriminate_the_failure() -> None:
    """Guard law, real CLI: 1 = seed hash mismatch, 3 = intact hash but a
    container that will not parse — scripts can gate on the difference."""
    from typer.testing import CliRunner

    from hyperweave.cli import app

    runner = CliRunner()
    svg = _matrix()

    assert runner.invoke(app, ["verify", svg]).exit_code == 0

    tampered = svg.replace("Qwen", "Qwxn", 1)
    assert runner.invoke(app, ["verify", tampered]).exit_code == 1

    corrupted = svg.replace("</svg>", "&</svg>", 1)
    run = runner.invoke(app, ["verify", corrupted])
    assert run.exit_code == 3
    assert "not well-formed" in run.stderr
