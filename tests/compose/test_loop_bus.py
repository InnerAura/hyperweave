"""The gather bus — the unrolled ladder's merge piece, at every seam.

The corpus's construction (retry's unrolled specimen): a finite attempt
ladder on the spine, each attempt raising a bare arm that fillets onto the
shared bus line and runs to the junction under the gather terminal; the
junction-aligned arm carries the single marked stem — one drawn arrival.
The unrolled form is the loop contract's ONE exception to the return law:
two or more stations converging on one advance terminal.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from pydantic import ValidationError

from hyperweave.compose.diagram.choreography import _derive_acts
from hyperweave.compose.diagram.loop import classify_loop
from hyperweave.compose.engine import compose
from hyperweave.core.diagram import DiagramSpec, resolved_edges
from hyperweave.core.models import ComposeSpec
from tests.compose.parity.pieces import gather_buses
from tests.compose.parity.svgfacts import parse_svg
from tests.compose.test_loop_solver import solve


def unrolled(n: int = 3) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {"id": f"a{i + 1}", "label": f"Attempt {i + 1}", "desc": "call the tool"} for i in range(n)
    ]
    nodes += [
        {"id": "done", "label": "Done", "desc": "return the result", "station": "terminal", "partition": "advance"},
        {"id": "fail", "label": "Failed", "desc": "surface the error", "station": "terminal", "partition": "exhausted"},
    ]
    edges: list[dict[str, Any]] = [
        {"from": f"a{i + 1}", "to": f"a{i + 2}", "label": f"fail · wait {i + 1}s", "label_style": "chip"}
        for i in range(n - 1)
    ]
    edges += [{"from": f"a{i + 1}", "to": "done"} for i in range(n)]
    edges[-2]["label"] = "succeeded"
    edges[-2]["label_style"] = "chip"
    edges.append({"from": f"a{n}", "to": "fail", "label": "budget out", "label_style": "chip"})
    return {
        "topology": "loop",
        "orientation": "horizontal",
        "title": "Retry, unrolled",
        "nodes": nodes,
        "edges": edges,
    }


def test_unrolled_ladder_is_the_one_lawful_zero_return_loop() -> None:
    """The gather signature admits the unrolled form; a plain no-return
    pair still hears the rail refusal."""
    solve(unrolled())  # composes without a return edge
    with pytest.raises(ValidationError, match="the rail is the one lawful long route"):
        DiagramSpec.model_validate(
            {
                "topology": "loop",
                "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                "edges": [{"from": "a", "to": "b"}],
            }
        )


def test_gather_terminal_seats_over_the_middle_attempt() -> None:
    """The junction centers under the gather terminal, which seats at the
    middle source's rank on the sky side (the specimen's Done over its
    middle attempt)."""
    lay = solve(unrolled())
    by_id = {n.node_id: n for n in lay.nodes}
    done, a2 = by_id["done"], by_id["a2"]
    assert abs((done.box.x + done.box.w / 2) - (a2.box.x + a2.box.w / 2)) < 1.0
    assert done.box.y + done.box.h < a2.box.y, "the gather terminal rides the sky side"


def test_bus_arms_are_bare_and_the_stem_carries_the_arrival() -> None:
    """Arms end ON the bus line short of the terminal (their markers
    suppressed); exactly one stem arrives — the composed artifact draws
    four arrowheads (three spine runs + the stem), never six."""
    lay = solve(unrolled())
    spec = DiagramSpec.model_validate(unrolled())
    edges = resolved_edges(spec)
    by_id = {n.node_id: n for n in lay.nodes}
    done, a2 = by_id["done"], by_id["a2"]
    stem_x = a2.box.x + a2.box.w / 2
    for c in lay.connectors:
        if c.index >= len(edges) or edges[c.index].target != "done" or not c.polyline:
            continue
        ex, ey = c.polyline[-1]
        if abs(ex - stem_x) < 1.0 and ey < done.box.y + done.box.h + 4:
            continue  # the stem's own arrival
        assert ey > done.box.y + done.box.h, "a bare arm ends on the bus line, short of the terminal"
    from tests.compose.parity.pieces import census

    svg = compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="opaque",
            palette="fixed",
            diagram=unrolled(),
        )
    ).svg
    assert census(parse_svg(svg)).arrow_terminals == 4, "three spine runs + the stem — the arms stay bare"


def test_unrolled_acts_are_the_scenarios_verbatim() -> None:
    """n success acts (attempt k rises its arm) plus the exhaust — the
    specimen's own audit scenario list."""
    spec = DiagramSpec.model_validate(unrolled(3))
    edges = resolved_edges(spec)
    sh = classify_loop(spec, edges)
    acts = _derive_acts(spec, edges, sh)
    assert len(acts) == 4
    assert [a.outcome for a in acts] == ["terminal"] * 4
    # The exhaust walks the whole ladder.
    assert len(acts[-1].edges) == 3


def test_unrolled_composes_with_the_bus_census_species() -> None:
    """Full pipeline: the battery holds (arms lawfully end on the junction)
    and the render carries exactly one gather-bus junction — the piece's
    own census species, read the same on hand and engine dialects."""
    svg = compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="opaque",
            palette="fixed",
            diagram={**unrolled(), "motion_register": "turn"},
        )
    ).svg
    assert gather_buses(parse_svg(svg)) == 1
    assert re.search(r"-ch0", svg), "the turn register performs the scenarios"
