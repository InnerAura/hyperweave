"""The loop battery holds on every device shape — and actually bites.

The battery is an ENGINE-fault gate (it asserts the engine honored its own
contract), so the positive case is simply that every corpus shape composes;
the negative case feeds it a layout with a doctored pulse and expects the
typed ENGINE_INVARIANT fault to fire — a checker that cannot fail is not a
checker, and one that fails as a bare AssertionError is a traceback on every
surface.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from hyperweave.compose.diagram.battery import run_loop_battery
from hyperweave.compose.diagram.choreography import apply_choreography
from hyperweave.compose.diagram.input import coerce_diagram_input
from hyperweave.compose.diagram.records import KeyframeBlock
from hyperweave.config.loader import load_diagram_config
from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.core.models import ComposeSpec
from tests.compose.test_loop_choreography import flywheel, shuttle
from tests.compose.test_loop_ir import endless, hillclimb, nested, tap
from tests.compose.test_loop_solver import solve

ENGINE = load_diagram_config()


def choreographed(dspec: dict[str, Any]) -> Any:
    norm = coerce_diagram_input(
        None, ComposeSpec.model_validate({"type": "diagram", "genome_id": "primer", "diagram": dspec})
    )
    return apply_choreography(solve(dspec), norm.spec, register="turn", engine=ENGINE)


@pytest.mark.parametrize(
    "dspec",
    [hillclimb(), nested(), tap(), flywheel(), shuttle(), endless("Plan", "Act", "Review")],
)
def test_battery_holds_on_the_corpus_shapes(dspec: dict[str, Any]) -> None:
    run_loop_battery(choreographed(dspec))


def test_battery_is_a_noop_off_loop() -> None:
    lay = solve(hillclimb())
    run_loop_battery(replace(lay, layout_slug="dag"))


def test_battery_catches_a_mid_wire_pulse() -> None:
    lay = choreographed(hillclimb())
    plan = lay.choreography
    assert plan is not None
    # Doctor the first pulse's keyframes to stop mid-wire — full exit is the law.
    broken = list(plan.keyframes)
    victim = plan.pulses[0].anim_index
    broken[victim] = KeyframeBlock(
        prop="stroke-dashoffset",
        body="0% { stroke-dashoffset: 18; } 50% { stroke-dashoffset: -10; } 100% { stroke-dashoffset: 18; }",
    )
    doctored = replace(lay, choreography=replace(plan, keyframes=tuple(broken)))
    with pytest.raises(HwError, match="full exit") as exc:
        run_loop_battery(doctored)
    assert exc.value.code is HwErrorCode.ENGINE_INVARIANT
    assert exc.value.is_engine_fault
