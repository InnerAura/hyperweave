"""The meter kit piece and its three registers, asserted at every seam.

The corpus's meter laws: one gauge grammar (plate + lead mark + segment row
spanning the chip's own width, seated beneath the chip) with three arrows of
time — laps grows and resets with the outer turn, budget drains and refills,
accumulate grows and holds. The drift face keeps the static gauge with zero
keyframes; geometry is register-invariant (one spec, register flipped); and
the gauge refuses without its structural anchor.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from pydantic import ValidationError

from hyperweave.compose.diagram.meter import apply_meters
from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_diagram_config
from hyperweave.core.models import ComposeSpec
from tests.compose.test_loop_choreography import flywheel
from tests.compose.test_loop_ir import hillclimb, nested
from tests.compose.test_loop_solver import solve

ENGINE = load_diagram_config()


def metered_flywheel(register: str = "accumulate", n: int = 6) -> dict[str, Any]:
    spec = flywheel()
    spec["motion_register"] = register
    spec["edges"][-1]["meter"] = n
    return spec


def metered_retry(register: str = "budget") -> dict[str, Any]:
    return {
        "topology": "loop",
        "motion_register": register,
        "nodes": [
            {"id": "call", "label": "Call the tool", "desc": "attempt n"},
            {"id": "succ", "label": "Succeeded?", "station": "decision"},
            {"id": "done", "label": "Done", "station": "terminal", "partition": "advance"},
            {"id": "retry", "label": "Retry?", "station": "decision"},
            {"id": "back", "label": "Back off", "desc": "wait 2^n + jitter"},
            {"id": "fail", "label": "Failed", "station": "terminal", "partition": "exhausted"},
        ],
        "edges": [
            {"from": "call", "to": "succ"},
            {"from": "succ", "to": "done", "label": "yes", "label_style": "chip"},
            {"from": "succ", "to": "retry", "label": "no", "label_style": "chip"},
            {"from": "retry", "to": "back", "label": "yes · budget left", "label_style": "chip"},
            {"from": "retry", "to": "fail", "label": "no · budget out", "label_style": "chip"},
            {
                "from": "back",
                "to": "call",
                "label": "attempt n+1",
                "label_style": "chip",
                "circuit": "return",
                "meter": 3,
            },
        ],
    }


def metered_nested() -> dict[str, Any]:
    spec = nested()
    spec["motion_register"] = "laps"
    for e in spec["edges"]:
        if e.get("circuit") == "return" and e["from"].startswith("i"):
            e["meter"] = 3
            e["label_style"] = "chip"  # the gauge seats beneath the inner chip
    return spec


def _svg(spec: dict[str, Any]) -> str:
    return compose(
        ComposeSpec(
            type="diagram", genome_id="primer", variant="porcelain", ground="opaque", palette="fixed", diagram=spec
        )
    ).svg


def _metered_layout(spec: dict[str, Any], register: str) -> Any:
    lay = solve(spec)
    from hyperweave.compose.diagram.input import resolve_auto_roles
    from hyperweave.core.diagram import DiagramSpec

    dspec = resolve_auto_roles(DiagramSpec.model_validate(spec))
    return apply_meters(lay, dspec, register=register, engine=ENGINE, glyph_registry=None)


def test_meter_strip_geometry_spans_its_chip() -> None:
    """The gauge grammar at the owner-ruled scale (~0.78 of the meter
    specimens): the segment row spans the chip's own width, seated
    meter_gap below the chip; the meter_wrap plate wraps mark + row;
    every segment stays inside the plate."""
    lay = _metered_layout(metered_retry(), "budget")
    assert len(lay.meters) == 1
    m = lay.meters[0]
    chip = next(a.box for a in lay.annotations if a.kind == "edge-chip" and a.edge_index == m.edge_index)
    assert chip is not None
    assert len(m.boxes) == 3
    row_left = min(b.x for b in m.boxes)
    row_right = max(b.x + b.w for b in m.boxes)
    assert m.boxes[0].y == pytest.approx(chip.y + chip.h + 12.0)
    assert m.plate.h == pytest.approx(26.0)
    assert m.plate.rx == pytest.approx(8.0)
    assert m.plate.y == pytest.approx(chip.y + chip.h + 4.0)
    for sb in m.boxes:
        assert sb.h == pytest.approx(10.0)
        assert sb.rx == pytest.approx(3.0)
        assert sb.x >= m.plate.x and sb.x + sb.w <= m.plate.x + m.plate.w
    # The row spans the chip's width within the clamp band.
    assert row_right - row_left == pytest.approx(chip.w, abs=22.0)
    # Center law: the piece centers on its chip.
    assert (m.plate.x + m.plate.w / 2) == pytest.approx(chip.x + chip.w / 2, abs=0.5)


def test_meter_registers_fill_their_gauges() -> None:
    """Each register fills every segment on its own clock; the budget's
    fills rest FULL (a drained gauge's honest reduced-motion state), the
    counter's and the accumulator's rest empty."""
    for spec, register, n in (
        (metered_flywheel(), "accumulate", 6),
        (metered_retry(), "budget", 3),
        (metered_nested(), "laps", 3),
    ):
        svg = _svg(spec)
        fills = re.findall(r'opacity="([\d.]+)" class="[a-z0-9-]+-mfill"', svg)
        assert len(fills) == n, f"{register}: {len(fills)} fills"
        rest = {float(v) for v in fills}
        assert rest == ({1.0} if register == "budget" else {0.0}), f"{register} rest {rest}"
        assert len(re.findall(r"-mseg\"", svg)) == n
        assert svg.count('-mplate"') >= 1


def test_meter_static_on_drift_zero_keyframes() -> None:
    """The drift face keeps the static gauge: base row and plate drawn, no
    fill layer, no choreography keyframes."""
    spec = metered_flywheel()
    spec["motion_register"] = "drift"
    svg = _svg(spec)
    assert re.search(r"-mseg\"", svg)
    assert re.search(r"-mplate\"", svg)
    assert '-mfill"' not in svg  # no fill ELEMENTS (the class rule alone is inert)
    assert "-ch0" not in svg


def test_meter_geometry_is_register_invariant() -> None:
    """One spec, register flipped: node boxes and connector paths are
    byte-identical between the drift face and the accumulate performance —
    the meter is content, the register only performs it."""
    plain = metered_flywheel()
    plain["motion_register"] = "drift"
    lay_a = solve(metered_flywheel())
    lay_d = solve(plain)
    assert [(n.box.x, n.box.y, n.box.w, n.box.h) for n in lay_a.nodes] == [
        (n.box.x, n.box.y, n.box.w, n.box.h) for n in lay_d.nodes
    ]
    assert [c.path_d for c in lay_a.connectors] == [c.path_d for c in lay_d.connectors]


def test_meter_refuses_off_the_return() -> None:
    spec = metered_retry()
    spec["edges"][1]["meter"] = 2  # a forward edge
    del spec["edges"][-1]["meter"]
    with pytest.raises(ValidationError, match=r"the meter rides\s+a 'circuit: return' edge"):
        _svg(spec)


def test_meter_refuses_without_its_chip() -> None:
    spec = metered_flywheel()
    del spec["edges"][-1]["label"]
    del spec["edges"][-1]["label_style"]
    with pytest.raises(ValidationError, match="without a chip"):
        _svg(spec)


def test_meter_caps_at_eight_segments() -> None:
    with pytest.raises(ValidationError, match="meter caps at 8 segments"):
        _svg(metered_flywheel(n=9))


def test_laps_refuses_without_a_scope() -> None:
    spec = hillclimb()
    spec["motion_register"] = "laps"
    with pytest.raises(ValidationError, match="no inner circuit to count"):
        _svg(spec)


def test_budget_refuses_without_a_decision() -> None:
    spec = flywheel()
    spec["motion_register"] = "budget"
    with pytest.raises(ValidationError, match="nothing spends the budget"):
        _svg(spec)


def test_accumulate_refuses_without_the_gain() -> None:
    spec = flywheel()
    spec["motion_register"] = "accumulate"
    spec["edges"][-1]["accumulates"] = False
    with pytest.raises(ValidationError, match=r"the return declares no\s+'accumulates: true'"):
        _svg(spec)
