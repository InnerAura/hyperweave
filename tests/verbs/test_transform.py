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


_DAG = {
    "topology": "dag",
    "title": "Grown figure",
    "subtitle": "A gateway fans to services, each grounding on its store",
    "nodes": [
        {"id": "web", "label": "web"},
        {"id": "gw", "label": "gateway", "role": "hero"},
        {"id": "auth", "label": "Auth"},
        {"id": "orders", "label": "Orders"},
        {"id": "pg", "label": "Postgres"},
        {"id": "kafka", "label": "Kafka"},
    ],
    "edges": [
        {"source": "web", "target": "gw"},
        {"source": "gw", "target": "auth"},
        {"source": "gw", "target": "orders"},
        {"source": "auth", "target": "pg", "label": "reads", "label_style": "chip"},
        {"source": "orders", "target": "kafka", "label": "emits", "label_style": "chip"},
    ],
}

_GROW = [
    {"op": "add", "path": "/nodes/-", "value": {"id": "billing", "label": "Billing"}},
    {"op": "add", "path": "/edges/-", "value": {"source": "gw", "target": "billing"}},
    {
        "op": "add",
        "path": "/edges/-",
        "value": {"source": "billing", "target": "pg", "label": "writes", "label_style": "chip"},
    },
]


def _dag_svg() -> str:
    return compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=_DAG)).svg


def _label_rows(svg: str, names: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for name in names:
        m = re.search(rf'<text x="[0-9.]+" y="([0-9.]+)"[^>]*>{re.escape(name)}</text>', svg)
        assert m is not None, f"label {name!r} missing from render"
        out[name] = float(m.group(1))
    return out


def test_diagram_transform_preserves_caption() -> None:
    """The child renders the same caption band the parent composed — the
    subtitle is spec content and the footer region is kit chrome; neither is
    transform's to drop."""
    svg0 = _dag_svg()
    assert 'data-hw-region="footer"' in svg0
    res = transform(svg0, _GROW, ts=_FIXED_TS)
    assert 'data-hw-region="footer"' in res.svg
    assert "A gateway fans to services, each grounding on its store" in res.svg


def test_diagram_transform_pins_survivor_rows() -> None:
    """The figure survives the edit: every survivor keeps its row, the
    insertion seats at its rank's extent, and the pins ride the hashed
    payload for the next hop."""
    svg0 = _dag_svg()
    names = ["Auth", "Orders", "Postgres", "Kafka"]
    before = _label_rows(svg0, names)
    res = transform(svg0, _GROW, ts=_FIXED_TS)
    after = _label_rows(res.svg, [*names, "Billing"])
    for name in names:
        assert abs(after[name] - before[name]) < 0.5, f"{name} moved: {before[name]} -> {after[name]}"
    assert after["Billing"] > after["Orders"], "insertion interleaved into the authored run"
    emb = extract_embedded(res.svg)
    assert emb.payload["spec"]["layout"]["rank_orders"] == [
        ["web"],
        ["gw"],
        ["auth", "orders", "billing"],
        ["pg", "kafka"],
    ]
    # the first labeled vote holds the store even after the second arrives
    assert abs(after["Postgres"] - after["Auth"]) < 0.5


def test_diagram_transform_chain_keeps_the_figure() -> None:
    """Transform of a transform: the grandchild reads the child's persisted
    pins (never a cold re-solve of the patched spec), so survivor rows hold
    across hops and lineage chains hop to hop."""
    svg0 = _dag_svg()
    r1 = transform(svg0, _GROW, ts=_FIXED_TS)
    rows1 = _label_rows(r1.svg, ["Auth", "Orders", "Billing", "Postgres", "Kafka"])
    r2 = transform(
        r1.svg,
        [
            {"op": "add", "path": "/nodes/-", "value": {"id": "audit", "label": "Audit"}},
            {"op": "add", "path": "/edges/-", "value": {"source": "gw", "target": "audit"}},
        ],
        ts=_FIXED_TS,
    )
    rows2 = _label_rows(r2.svg, ["Auth", "Orders", "Billing", "Audit", "Postgres", "Kafka"])
    for name in ("Auth", "Orders", "Billing", "Postgres", "Kafka"):
        assert abs(rows2[name] - rows1[name]) < 0.5, f"{name} moved on the second hop"
    assert rows2["Audit"] > rows2["Billing"], "second insertion left the extent"
    assert len(r2.lineage) == 2
    assert r2.lineage[1]["parent_id"] == r1.new_id


def test_diagram_insert_then_remove_returns_the_figure() -> None:
    """Adding a node and then removing it (edges first, then the node)
    returns every original row — pins drop the vanished id and the figure
    closes back over the edit."""
    svg0 = _dag_svg()
    names = ["Auth", "Orders", "Postgres", "Kafka"]
    before = _label_rows(svg0, names)
    r1 = transform(svg0, _GROW, ts=_FIXED_TS)
    r2 = transform(
        r1.svg,
        [
            {"op": "remove", "path": "/edges/6"},
            {"op": "remove", "path": "/edges/5"},
            {"op": "remove", "path": "/nodes/6"},
        ],
        ts=_FIXED_TS,
    )
    after = _label_rows(r2.svg, names)
    for name in names:
        assert abs(after[name] - before[name]) < 0.5, f"{name} did not return: {before[name]} -> {after[name]}"


def test_diagram_transform_reasoning_carries_the_delta() -> None:
    """Parent and child stop being byte-identical in hw:reasoning: the child
    appends the transform note with its insertion seat filled in."""
    svg0 = _dag_svg()
    res = transform(svg0, _GROW, ts=_FIXED_TS)
    parent_tr = re.search(r"<hw:tradeoffs>(.*?)</hw:tradeoffs>", svg0, re.DOTALL)
    child_tr = re.search(r"<hw:tradeoffs>(.*?)</hw:tradeoffs>", res.svg, re.DOTALL)
    assert parent_tr and child_tr
    assert child_tr.group(1) != parent_tr.group(1)
    assert "billing at rank 2, row 3/3" in child_tr.group(1)


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


def test_transform_preserves_explicit_plate_on_twin_default_genome() -> None:
    """The regression: primer defaults to twin, so an explicit plate parent's
    child must not spring back to adaptive after a transform (the payload is
    surface-silent for plate — presentation is read from the artifact)."""
    svg0 = compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="opaque",
            palette="fixed",
            diagram=_DIAGRAM,
        )
    ).svg
    assert 'data-hw-adapt="adaptive"' not in svg0
    res = transform(svg0, [{"op": "replace", "path": "/title", "value": "Flow 2"}], ts=_FIXED_TS)
    assert 'data-hw-adapt="adaptive"' not in res.svg

    # The original symptom: projecting the child to a flattening format failed
    # with "adaptive-palette artifact cannot be flattened".
    from hyperweave.formats import project

    project(res.svg, "svg-static")

    # Plate stays payload-silent — child ids byte-stable with fresh plates.
    surface = extract_embedded(res.svg).payload["spec"].get("surface")
    assert surface is None


def test_transform_preserves_genome_default_twin() -> None:
    """A genome-defaulted twin parent (no explicit surface at all) stays twin
    through transform — explicit derivation, not the accidental correctness of
    the genome default re-firing."""
    svg0 = compose(ComposeSpec(type="diagram", genome_id="primer", diagram=_DIAGRAM)).svg
    assert 'data-hw-adapt="adaptive"' in svg0
    res = transform(svg0, [{"op": "replace", "path": "/title", "value": "Flow 2"}], ts=_FIXED_TS)
    assert 'data-hw-adapt="adaptive"' in res.svg


def test_transform_preserves_committed_face() -> None:
    """A face-committed parent's child re-renders the same baked face."""
    svg0 = compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="opaque",
            palette="fixed",
            surface_face="dark",
            diagram=_DIAGRAM,
        )
    ).svg
    assert 'data-hw-face="dark"' in svg0
    res = transform(svg0, [{"op": "replace", "path": "/title", "value": "Flow 2"}], ts=_FIXED_TS)
    assert 'data-hw-face="dark"' in res.svg
