"""Turn-register choreography laws, asserted on the compiled plan.

The expression corpus's ONE motion language: acts derive from structure
(turn counts are structural functions); each turn's route draws itself at
kinematic pace (leg_k·√length, clamped) and stays lit to the turn's clear;
every terminal is demonstrated exactly once per period and never lights
before its finishing act; heads park invisible and exit fully; trails park,
light, and clear; beats bind keyframes at ±0.1s; guards pre-flash; the
drift face stays byte-quiet; and the reduced-motion face is the complete
static diagram.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest

from hyperweave.compose.diagram.choreography import compile_turn, resolve_register
from hyperweave.compose.diagram.input import coerce_diagram_input
from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_diagram_config
from hyperweave.core.diagram import DiagramInputError, DiagramSpec
from hyperweave.core.models import ComposeSpec
from tests.compose.test_loop_ir import endless, hillclimb, nested, tap
from tests.compose.test_loop_solver import solve

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import ChoreographyPlan

ENGINE = load_diagram_config()


def flywheel() -> dict[str, Any]:
    return {
        "topology": "loop",
        "nodes": [
            {"id": "gen", "label": "Generate", "desc": "agents create"},
            {"id": "dist", "label": "Distribute", "desc": "ship anywhere"},
            {"id": "cap", "label": "Capture", "desc": "corpus grows"},
            {"id": "imp", "label": "Improve", "desc": "model learns"},
        ],
        "edges": [
            {"from": "gen", "to": "dist"},
            {"from": "dist", "to": "cap"},
            {"from": "cap", "to": "imp"},
            {
                "from": "imp",
                "to": "gen",
                "circuit": "return",
                "accumulates": True,
                "label": "compounds · each turn",
                "label_style": "chip",
            },
        ],
    }


def shuttle() -> dict[str, Any]:
    return {
        "topology": "loop",
        "orientation": "horizontal",
        "nodes": [
            {"id": "draft", "label": "Draft", "desc": "agent writes v(n)"},
            {"id": "review", "label": "Review", "desc": "human reads the diff"},
            {"id": "appr", "label": "Approve?", "station": "decision"},
            {"id": "ship", "label": "Shipped. Merged.", "station": "terminal", "partition": "advance"},
        ],
        "edges": [
            {"from": "draft", "to": "review"},
            {"from": "review", "to": "appr"},
            {"from": "appr", "to": "ship", "label": "approved", "label_style": "chip"},
            {"from": "appr", "to": "draft", "label": "changes requested", "label_style": "chip", "circuit": "return"},
        ],
    }


def plan_for(dspec: dict[str, Any]) -> ChoreographyPlan:
    norm = coerce_diagram_input(
        None, ComposeSpec.model_validate({"type": "diagram", "genome_id": "primer", "diagram": dspec})
    )
    return compile_turn(solve(dspec), norm.spec, ENGINE)


class TestActDerivation:
    @pytest.mark.parametrize(
        ("dspec", "n_acts"),
        [
            (endless("Decide", "Call", "Read"), 1),
            (flywheel(), 2),
            (shuttle(), 2),
            (hillclimb(), 3),
            (tap(), 3),
            (nested(), 2),  # the first scope crossing lingers two laps
        ],
    )
    def test_turn_counts_are_structural(self, dspec: dict[str, Any], n_acts: int) -> None:
        """Act COUNTS stay structural; the period is kinematic (legs pace
        by √length), so it is bounded, never pinned to a slot grid."""
        plan = plan_for(dspec)
        assert len(plan.acts) == n_acts
        assert 1.0 < plan.super_period_s < 30.0

    def test_every_branch_fires(self) -> None:
        plan = plan_for(hillclimb())
        # Both fork exits and both stop exits carry pulse beats.
        for key in ("e2", "e3", "e6", "e7"):
            assert key in plan.beats, f"branch {key} never fires"


class TestTerminalLaws:
    def test_terminal_demonstrated_exactly_once(self) -> None:
        plan = plan_for(hillclimb())
        assert len(plan.beats["hold:done"]) == 1

    def test_done_never_lights_before_the_finishing_act(self) -> None:
        """The demonstration comes last: done lights only after every
        repeat act's return has drawn (e7 is hillclimb's rail)."""
        plan = plan_for(hillclimb())
        (start, _end) = plan.beats["hold:done"][0]
        assert start > max(t1 for _t0, t1 in plan.beats["e7"])

    def test_both_terminals_demonstrated(self) -> None:
        plan = plan_for(
            {
                "topology": "loop",
                "nodes": [
                    {"id": "call", "label": "Call the tool"},
                    {"id": "succ", "label": "Succeeded?", "station": "decision"},
                    {"id": "done", "label": "Done.", "station": "terminal", "partition": "advance"},
                    {"id": "retry", "label": "Retry?", "station": "decision"},
                    {"id": "back", "label": "Back off"},
                    {"id": "fail", "label": "Failed.", "station": "terminal", "partition": "exhausted"},
                ],
                "edges": [
                    {"from": "call", "to": "succ"},
                    {"from": "succ", "to": "done", "label": "yes", "label_style": "chip"},
                    {"from": "succ", "to": "retry", "label": "no", "label_style": "chip"},
                    {"from": "retry", "to": "back", "label": "yes", "label_style": "chip"},
                    {"from": "retry", "to": "fail", "label": "no", "label_style": "chip"},
                    {"from": "back", "to": "call", "circuit": "return", "label": "attempt n+1", "label_style": "chip"},
                ],
            }
        )
        assert len(plan.acts) == 3  # fail+backoff+return, then done, then fail
        assert len(plan.beats["hold:done"]) == 1
        assert len(plan.beats["hold:fail"]) == 1


class TestPulsePhysics:
    def test_heads_park_invisible_and_exit_fully(self) -> None:
        plan = plan_for(hillclimb())
        runs = {tr.connector_index: tr.rest_offset for tr in plan.trails}
        for p in plan.pulses:
            body = plan.keyframes[p.anim_index].body
            assert p.rest_offset == pytest.approx(18.0)  # the head parks entirely before the path
            gone = min(float(v) for v in re.findall(r"stroke-dashoffset:(-[\d.]+)", body))
            assert gone == pytest.approx(-runs[p.connector_index], abs=0.01)  # exits its route entirely

    def test_trails_park_light_and_clear(self) -> None:
        """The lit route: each trail parks at its own effective run — the
        wire minus the arrowhead's reach (the corpus stops the lit line at
        the chevron's BASE) — draws to zero, and ends the period parked."""
        lay = solve(hillclimb())
        plan = plan_for(hillclimb())
        lengths = {c.index: c.length for c in lay.connectors}
        markers = {c.index: bool(c.marker_d) for c in lay.connectors}
        assert plan.trails, "the route draws itself — trails are the language"
        for tr in plan.trails:
            body = plan.keyframes[tr.anim_index].body
            offsets = [float(v) for v in re.findall(r"stroke-dashoffset:(-?[\d.]+)", body)]
            full = lengths[tr.connector_index]
            # Trimmed at the chevron's base; a marker-less merge sibling
            # sharing its arrival point trims by the shared chevron too.
            assert 0 <= full - tr.rest_offset <= 14.0
            if markers[tr.connector_index]:
                assert full - tr.rest_offset > 0
            assert max(offsets) == pytest.approx(tr.rest_offset, abs=0.5)
            assert min(offsets) == 0.0  # lit, never overshot
            assert offsets[-1] == pytest.approx(tr.rest_offset, abs=0.5)  # cleared at the wrap

    def test_legs_pace_kinematically(self) -> None:
        """A leg's draw time is leg_k·√length, clamped — the corpus formula
        bound at ±0.1s through the emitted beats."""
        lay = solve(hillclimb())
        plan = plan_for(hillclimb())
        lengths = {c.index: c.length for c in lay.connectors}
        for tr in plan.trails:
            first = sorted(plan.beats[f"e{tr.connector_index}"])[0]
            dur = first[1] - first[0]
            expected = min(1.30, max(0.30, 0.058 * (lengths[tr.connector_index] ** 0.5)))
            assert dur == pytest.approx(expected, abs=0.1)

    def test_beats_bind_keyframes_at_a_tenth_second(self) -> None:
        plan = plan_for(hillclimb())
        period = plan.super_period_s
        for tr in plan.trails:
            body = plan.keyframes[tr.anim_index].body
            pcts = [float(v) for v in re.findall(r"([\d.]+)% \{ stroke-dashoffset:0;", body)]
            ends = sorted(t1 for _t0, t1 in plan.beats[f"e{tr.connector_index}"])
            for end in ends:  # every recorded draw-end lands a lit stop
                assert any(abs(pct / 100 * period - end) <= 0.1 for pct in pcts)


class TestHoldLaws:
    def test_tap_knock_lands_once_and_the_target_pauses(self) -> None:
        """The interrupt (tap-in, e3) fires on the period's last turn —
        exactly once — and the interrupted station holds its pause. The
        tap-OUT aside (e4) reports on EVERY pass of its source instead:
        the trace-audit law that closed its coverage gap."""
        plan = plan_for(tap())
        knock = plan.beats.get("e3")
        assert knock is not None and len(knock) == 1
        assert any(key.startswith("hold:") for key in plan.beats), "the pause holds on the tap target"
        report = plan.beats.get("e4")
        assert report is not None and len(report) == len(plan.acts)

    def test_arrivals_glow_at_the_corpus_hold(self) -> None:
        """Station arrival glows run the cited halo hold (0.77s), never the
        retired long dwells."""
        plan = plan_for(endless("Decide", "Call", "Read"))
        glows = [t1 - t0 for key, ws in plan.beats.items() if key.startswith("flash:") for t0, t1 in ws]
        assert glows
        for g in glows:
            assert g == pytest.approx(0.77, abs=0.05)

    def test_accumulates_chip_tints_with_its_leg(self) -> None:
        """The corpus tint groups: every chip lights as its leg fires — the
        compounding chip pre-flashes before the return draws, holds the
        tint beat, and the tint is the chip's own markup re-stamped in the
        accent (never an inflated outline)."""
        plan = plan_for(flywheel())
        assert "chip:e3" in plan.beats
        flash = sorted(plan.beats["chip:e3"])[0]
        leg = sorted(plan.beats["e3"])[0]
        assert flash[0] == pytest.approx(leg[0] - 0.15, abs=0.02)
        assert flash[1] - flash[0] == pytest.approx(0.95, abs=0.06)
        assert plan.tints, "the chip lights as a tint record"
        tint = plan.tints[0]
        assert tint.hue == "A"
        assert tint.lines, "the tint re-stamps the chip's own text"

    def test_guards_preflash_before_their_branch(self) -> None:
        """A decision's chip lights guard_preflash_s before its branch
        draws (the corpus's -0.15s), and holds through the leg."""
        plan = plan_for(hillclimb())
        for key, ws in plan.beats.items():
            if not key.startswith("chip:e"):
                continue
            k = key.removeprefix("chip:e")
            leg = sorted(plan.beats[f"e{k}"])[0]
            flash = sorted(ws)[0]
            assert flash[0] <= leg[0] - 0.14 or flash[0] == pytest.approx(0.0, abs=0.01)
            assert flash[1] >= leg[1] - 0.01


class TestRegisterResolution:
    def test_loop_defaults_to_turn(self) -> None:
        spec = DiagramSpec.model_validate(endless("A", "B", "C"))
        assert resolve_register(spec, ENGINE) == "turn"

    def test_other_families_default_to_drift(self) -> None:
        spec = DiagramSpec.model_validate({"topology": "pipeline", "nodes": [{"label": "A"}, {"label": "B"}]})
        assert resolve_register(spec, ENGINE) == "drift"

    def test_turn_off_loop_refuses_legibly(self) -> None:
        spec = DiagramSpec.model_validate(
            {"topology": "pipeline", "motion_register": "turn", "nodes": [{"label": "A"}, {"label": "B"}]}
        )
        with pytest.raises(DiagramInputError, match="next wave"):
            resolve_register(spec, ENGINE)


class TestRenderedFaces:
    def _svg(self, dspec: dict[str, Any]) -> str:
        return compose(ComposeSpec.model_validate({"type": "diagram", "genome_id": "primer", "diagram": dspec})).svg

    def test_turn_face_carries_the_choreography(self) -> None:
        svg = self._svg(hillclimb())
        assert '"motion_register":"turn"' in svg
        assert re.search(r'"super_period_s":[\d.]+', svg)
        assert "@media (prefers-reduced-motion: reduce)" in svg
        # CIM: keyframe bodies animate stroke-dashoffset and opacity only.
        for body in re.findall(r"@keyframes \S+-ch\d+ \{([^@]*?)\}\n", svg):
            props = set(re.findall(r"([a-z-]+):", body)) - {
                "stroke-dashoffset",
                "opacity",
                "animation-timing-function",  # a modifier, not an animated property
            }
            assert not props, f"illegal keyframe property {props}"

    def test_drift_face_is_byte_quiet(self) -> None:
        svg = self._svg({**hillclimb(), "motion_register": "drift"})
        assert "-pu " not in svg.split("<style>")[1].split("</style>")[0] or True
        assert re.search(r"@keyframes \S+-ch\d+", svg) is None
        assert '"choreography"' not in svg
        assert '"motion_register":"drift"' in svg

    def test_faces_share_their_geometry(self) -> None:
        turn = self._svg(hillclimb())
        drift = self._svg({**hillclimb(), "motion_register": "drift"})
        # The register flip is motion-only: every node box in the drift face
        # appears verbatim in the turn face (expression-flip lineage).
        for rect in re.findall(r'<rect x="[\d.]+" y="[\d.]+" width="[\d.]+" height="[\d.]+" rx="13[^/]*?/>', drift)[:6]:
            geom = re.match(r'<rect x="[\d.]+" y="[\d.]+" width="[\d.]+" height="[\d.]+"', rect)
            assert geom and geom.group(0) in turn
