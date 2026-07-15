"""transform — the write half."""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.errors import HwError
from hyperweave.core.models import ComposeSpec
from hyperweave.verbs import transform, verify
from hyperweave.verbs.parse import extract_embedded

_FIXED_TS = "2026-06-22T00:00:00Z"

_MATRIX = {
    "title": "Cost by model",
    "columns": [{"id": "m", "label": "MODEL"}, {"id": "c", "label": "COST", "kind": "numeric"}],
    "rows": [
        {"label": "Qwen", "cells": [{"value": "Qwen"}, {"value": "0.12"}]},
        {"label": "GPT-5", "cells": [{"value": "GPT-5"}, {"value": "2.50"}]},
    ],
}
_DIAGRAM = {
    "topology": "pipeline",
    "title": "Flow",
    "nodes": [{"id": "a", "label": "Source"}, {"id": "b", "label": "Mid"}, {"id": "c", "label": "Sink"}],
    "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
}


def _matrix_svg() -> str:
    return compose(ComposeSpec(type="matrix", genome_id="primer", variant="porcelain", matrix=_MATRIX)).svg


def _tamper_payload(svg: str) -> str:
    """Surgically change one char inside the hw:payload CDATA, leaving the envelope id stale."""
    m = re.search(r"(<hw:payload[^>]*><!\[CDATA\[)(.*?)(\]\]></hw:payload>)", svg, re.DOTALL)
    assert m is not None
    body = m.group(2).replace("Qwen", "Qwxn", 1)
    return svg[: m.start()] + m.group(1) + body + m.group(3) + svg[m.end() :]


def test_round_trip_matrix_cell_edit() -> None:
    svg0 = _matrix_svg()
    assert verify(svg0).hash_valid

    r = transform(svg0, [{"op": "replace", "path": "/rows/1/cells/1/value", "value": "9.99"}], ts=_FIXED_TS)

    # new artifact self-verifies, differs from parent, carries the edit
    assert r.new_id != r.parent_id
    assert verify(r.svg).hash_valid
    emb = extract_embedded(r.svg)
    assert "9.99" in emb.payload_json
    # lineage chains to the source and records the patch
    assert len(r.lineage) == 1
    assert r.lineage[0]["parent_id"] == r.parent_id
    assert r.lineage[0]["op"] == "transform"
    assert r.lineage[0]["patch"][0]["path"] == "/rows/1/cells/1/value"
    assert "lineage" in emb.payload


def test_transform_is_deterministic_with_fixed_ts() -> None:
    svg0 = _matrix_svg()
    patch = [{"op": "replace", "path": "/title", "value": "Updated"}]
    a = transform(svg0, patch, ts=_FIXED_TS)
    b = transform(svg0, patch, ts=_FIXED_TS)
    assert a.new_id == b.new_id


def test_lineage_accumulates_across_two_transforms() -> None:
    svg0 = _matrix_svg()
    r1 = transform(svg0, [{"op": "replace", "path": "/title", "value": "v2"}], ts=_FIXED_TS)
    r2 = transform(r1.svg, [{"op": "replace", "path": "/subtitle", "value": "more"}], ts=_FIXED_TS)
    assert len(r2.lineage) == 2
    assert r2.lineage[1]["parent_id"] == r1.new_id  # chains parent → child


def test_diagram_patches_spec_not_rendered() -> None:
    svg0 = compose(ComposeSpec(type="diagram", genome_id="primer", diagram=_DIAGRAM)).svg
    r = transform(svg0, [{"op": "replace", "path": "/title", "value": "Renamed"}], ts=_FIXED_TS)
    emb = extract_embedded(r.svg)
    assert emb.payload["spec"]["title"] == "Renamed"
    assert "rendered" in emb.payload  # rendered block regenerated, still present
    assert verify(r.svg).hash_valid


def test_spec_invalid_patch_fails_cleanly() -> None:
    svg0 = _matrix_svg()
    with pytest.raises(HwError) as exc:
        transform(svg0, [{"op": "add", "path": "/nodes/-", "value": {"label": "X"}}], ts=_FIXED_TS)
    assert exc.value.code.value == "SPEC_INVALID"


def test_envelope_corrupt_blocks_mutation() -> None:
    svg0 = _matrix_svg()
    tampered = _tamper_payload(svg0)
    with pytest.raises(HwError) as exc:
        transform(tampered, [{"op": "replace", "path": "/title", "value": "Z"}], ts=_FIXED_TS)
    assert exc.value.code.value == "ENVELOPE_CORRUPT"


def test_unsupported_frame_rejected() -> None:
    badge = compose(ComposeSpec(type="badge", genome_id="primer", title="X", value="Y")).svg
    with pytest.raises(HwError) as exc:
        transform(badge, [{"op": "replace", "path": "/value", "value": "Z"}], ts=_FIXED_TS)
    assert exc.value.code.value == "SPEC_INVALID"


def test_transform_preserves_surface() -> None:
    """A bare adaptive inlay source must not re-render as the plate default —
    transform changes content, never presentation."""
    svg0 = compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="bare",
            palette="adaptive",
            diagram=_DIAGRAM,
        )
    ).svg
    assert 'data-hw-surface="inlay"' in svg0
    res = transform(svg0, [{"op": "replace", "path": "/title", "value": "Flow 2"}], ts=_FIXED_TS)
    assert 'data-hw-surface="inlay"' in res.svg
    assert 'data-hw-ground="bare"' in res.svg
    surface = extract_embedded(res.svg).payload["spec"].get("surface") or {}
    assert surface == {"ground": "bare", "palette": "adaptive"}
