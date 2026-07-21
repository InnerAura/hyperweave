"""Shared-east-face port stagger — the calibration fixture for ``port_stagger``.

The collision: a node hosting an authored under-elbow ENTRY on its east face
while SOURCING a plain east exit fused both wires at center-y (~18px shared
cable, stacked arrowheads). The stagger parts them: exit half a step above
center, elbow landing half below. Everything without the collision keeps
face-center anchors byte-identically — the specimen-parity suite is the
negative control (no bundled preset exhibits the collision).
"""

from __future__ import annotations

import re

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

_PROBE = {
    "topology": "dag",
    "title": "Stagger probe",
    "nodes": [
        {"id": "a", "label": "Alpha"},
        {"id": "c", "label": "Gamma"},
        {"id": "b", "label": "Beta"},
        {"id": "x", "label": "Exit"},
    ],
    "edges": [
        {"source": "a", "target": "b"},
        {"source": "b", "target": "x"},
        {"source": "c", "target": "b", "exit": "bottom", "entry": "right"},
    ],
}


def _wire_ys_at_shared_face(svg: str) -> tuple[float, float]:
    """(plain-exit start y, elbow landing y) at the shared east face x."""
    paths = re.findall(r'<path[^>]* d="(M[^"]+)"', svg)
    exit_start = None
    elbow_land = None
    for d in paths:
        start = re.match(r"M (\d+(?:\.\d+)?),(\d+(?:\.\d+)?) C", d)
        if start and exit_start is None and float(start.group(1)) > 300:
            exit_start = (float(start.group(1)), float(start.group(2)))
        landing = re.search(r"L (\d+(?:\.\d+)?),(\d+(?:\.\d+)?)$", d)
        if landing and "Q" in d and d.startswith("M "):
            elbow_land = (float(landing.group(1)), float(landing.group(2)))
    assert exit_start is not None, "no plain east exit found"
    assert elbow_land is not None, "no elbow landing found"
    assert exit_start[0] == elbow_land[0], "the two wires must touch the same face x"
    return exit_start[1], elbow_land[1]


def test_shared_face_parts_exit_and_elbow_by_the_stagger() -> None:
    from hyperweave.core.paradigm import _diagram_topology_defaults

    svg = compose(ComposeSpec(type="diagram", genome_id="primer", ground="opaque", palette="fixed", diagram=_PROBE)).svg
    exit_y, elbow_y = _wire_ys_at_shared_face(svg)
    stagger = _diagram_topology_defaults()["dag"].port_stagger
    assert elbow_y - exit_y == stagger, f"expected {stagger}px separation, got {elbow_y - exit_y}"


def test_elbow_without_colliding_exit_keeps_center_landing() -> None:
    """Scope discipline: an elbow entering a node with NO east exit lands at
    face center exactly as before — the stagger fires only on the collision."""
    no_collision = {
        "topology": "dag",
        "title": "No collision",
        "nodes": [
            {"id": "a", "label": "Alpha"},
            {"id": "c", "label": "Gamma"},
            {"id": "b", "label": "Beta"},
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "c", "target": "b", "exit": "bottom", "entry": "right"},
        ],
    }
    svg = compose(
        ComposeSpec(type="diagram", genome_id="primer", ground="opaque", palette="fixed", diagram=no_collision)
    ).svg
    landing = None
    for d in re.findall(r'<path[^>]* d="(M[^"]+)"', svg):
        m = re.search(r"L (\d+(?:\.\d+)?),(\d+(?:\.\d+)?)$", d)
        if m and "Q" in d:
            landing = (float(m.group(1)), float(m.group(2)))
    assert landing is not None, "no elbow landing found"
    # The landed face belongs to the card whose east edge (x + w) is the
    # landing x — its center-y must equal the landing y exactly.
    centers = [
        (float(m.group(1)) + float(m.group(3)), float(m.group(2)) + float(m.group(4)) / 2)
        for m in re.finditer(
            r'<rect x="(\d+(?:\.\d+)?)" y="(\d+(?:\.\d+)?)" width="(\d+(?:\.\d+)?)" height="(\d+(?:\.\d+)?)"', svg
        )
    ]
    face_centers = [cy for east_x, cy in centers if abs(east_x - landing[0]) < 0.01]
    assert face_centers, f"no card east face at landing x {landing[0]}"
    assert any(abs(landing[1] - cy) < 0.01 for cy in face_centers), (
        f"elbow should land at face center; landing {landing[1]}, centers {face_centers}"
    )
