"""Loop family IR grammar: station vocabulary, the circuit, taps, scopes.

Devices are structural — retry is a loop with two decisions, a tap is a loop
with tap edges, nesting is a scope node — so these tests pin the grammar that
makes each device declarable and every off-loop leak reject legibly. Count
caps and orientation legality stay YAML data (tested with the solver);
default-vertical is the one input-seam rule pinned here.
"""

from __future__ import annotations

from typing import Any

import pytest

from hyperweave.compose.diagram.input import _finalize
from hyperweave.core.diagram import (
    DiagramSpec,
    Orientation,
    derive_edges,
    layout_slug,
    resolved_edges,
)


def endless(*labels: str) -> dict[str, Any]:
    return {"topology": "loop", "nodes": [{"label": lb} for lb in labels]}


def hillclimb() -> dict[str, Any]:
    """The anchor's shape: two decisions, a deviation pair, one terminal,
    one return (turn/cycle-turn.svg)."""
    return {
        "topology": "loop",
        "nodes": [
            {"id": "change", "label": "Make one change"},
            {"id": "measure", "label": "Measure against the target"},
            {"id": "improved", "label": "Improved?", "station": "decision"},
            {"id": "revert", "label": "Revert to last best", "partition": "discard"},
            {"id": "keep", "label": "Keep as new best", "partition": "advance"},
            {
                "id": "stop",
                "label": "Stop?",
                "station": "decision",
                "chips": ["target hit", "no gains", "out of ideas"],
            },
            {"id": "done", "label": "Done. Report it.", "station": "terminal", "partition": "advance"},
        ],
        "edges": [
            {"from": "change", "to": "measure"},
            {"from": "measure", "to": "improved"},
            {"from": "improved", "to": "revert", "label": "no", "label_style": "chip"},
            {"from": "improved", "to": "keep", "label": "yes", "label_style": "chip"},
            {"from": "revert", "to": "stop"},
            {"from": "keep", "to": "stop"},
            {"from": "stop", "to": "done", "label": "yes", "label_style": "chip"},
            {"from": "stop", "to": "change", "label": "no · keep going", "label_style": "chip", "circuit": "return"},
        ],
    }


def nested() -> dict[str, Any]:
    """cycle-nested.svg's shape: an outer circuit whose middle station is a
    scope holding a complete inner circuit."""
    return {
        "topology": "loop",
        "nodes": [
            {"id": "plan", "label": "Plan the task"},
            {"id": "scope", "label": "Tool loop", "station": "scope"},
            {"id": "i1", "label": "Decide", "enclosure": "scope"},
            {"id": "i2", "label": "Call", "enclosure": "scope"},
            {"id": "i3", "label": "Read", "enclosure": "scope"},
            {"id": "integ", "label": "Integrate results"},
            {"id": "dq", "label": "Done?", "station": "decision"},
            {"id": "term", "label": "Done. Report it.", "station": "terminal", "partition": "advance"},
        ],
        "edges": [
            {"from": "plan", "to": "scope", "label": "delegate"},
            {"from": "i1", "to": "i2"},
            {"from": "i2", "to": "i3"},
            {"from": "i3", "to": "i1", "circuit": "return", "label": "next call"},
            {"from": "scope", "to": "integ", "label": "answer found"},
            {"from": "integ", "to": "dq"},
            {"from": "dq", "to": "term", "label": "yes", "label_style": "chip"},
            {"from": "dq", "to": "plan", "label": "no · go again", "label_style": "chip", "circuit": "return"},
        ],
    }


def tap() -> dict[str, Any]:
    """cycle-tap-v3.svg's shape: the endless runloop with two externals."""
    return {
        "topology": "loop",
        "nodes": [
            {"id": "hero", "label": "Decide the next step", "role": "hero"},
            {"id": "call", "label": "Call the tool"},
            {"id": "read", "label": "Read the result"},
            {"id": "human", "label": "Human", "station": "external"},
            {"id": "tele", "label": "Telemetry", "station": "external"},
        ],
        "edges": [
            {"from": "hero", "to": "call"},
            {"from": "call", "to": "read"},
            {"from": "read", "to": "hero", "circuit": "return", "label": "next turn"},
            {"from": "human", "to": "hero", "circuit": "tap-in", "label": "interrupt"},
            {"from": "read", "to": "tele", "circuit": "tap-out", "label": "metrics"},
        ],
    }


class TestLoopDerivation:
    def test_endless_derives_chain_plus_return(self) -> None:
        s = DiagramSpec.model_validate(endless("Decide", "Call", "Read"))
        assert derive_edges(s) == ((0, 1), (1, 2), (2, 0))

    def test_derived_closing_pair_is_marked_return(self) -> None:
        s = DiagramSpec.model_validate(endless("Decide", "Call", "Read"))
        circuits = [(e.source, e.target, e.circuit) for e in resolved_edges(s)]
        assert circuits == [(0, 1, ""), (1, 2, ""), (2, 0, "return")]

    def test_declared_circuit_and_accumulates_resolve(self) -> None:
        s = DiagramSpec.model_validate(
            {
                "topology": "loop",
                "nodes": [{"id": "a", "label": "Generate"}, {"id": "b", "label": "Capture"}],
                "edges": [
                    {"from": "a", "to": "b"},
                    {"from": "b", "to": "a", "circuit": "return", "accumulates": True},
                ],
            }
        )
        back = resolved_edges(s)[1]
        assert back.circuit == "return"
        assert back.accumulates is True

    def test_devices_never_derive(self) -> None:
        s = DiagramSpec.model_validate(hillclimb())
        stripped = s.model_copy(update={"edges": []})
        with pytest.raises(Exception, match=r"edges content|declare them"):
            derive_edges(stripped)


class TestLoopSlugAndOrientation:
    def test_vertical_is_the_bare_slug(self) -> None:
        s = DiagramSpec.model_validate({**endless("A", "B", "C"), "orientation": "vertical"})
        assert layout_slug(s) == "loop"

    def test_horizontal_slug(self) -> None:
        s = DiagramSpec.model_validate({**endless("A", "B", "C"), "orientation": "horizontal"})
        assert layout_slug(s) == "loop-horizontal"

    def test_input_seam_defaults_loop_to_vertical(self) -> None:
        got = _finalize(DiagramSpec.model_validate(endless("A", "B", "C")))
        assert got.spec.orientation is Orientation.VERTICAL
        assert got.payload_spec.orientation is Orientation.VERTICAL

    def test_input_seam_honors_explicit_horizontal(self) -> None:
        got = _finalize(DiagramSpec.model_validate({**endless("A", "B", "C"), "orientation": "horizontal"}))
        assert got.spec.orientation is Orientation.HORIZONTAL

    def test_seam_leaves_other_families_alone(self) -> None:
        got = _finalize(DiagramSpec.model_validate({"topology": "pipeline", "nodes": [{"label": "A"}, {"label": "B"}]}))
        assert got.spec.orientation is Orientation.HORIZONTAL


class TestLoopStructure:
    def test_hillclimb_shape_validates(self) -> None:
        DiagramSpec.model_validate(hillclimb())

    def test_nested_shape_validates(self) -> None:
        DiagramSpec.model_validate(nested())

    def test_tap_shape_validates(self) -> None:
        DiagramSpec.model_validate(tap())

    def test_devices_without_edges_reject(self) -> None:
        with pytest.raises(ValueError, match="edges content"):
            DiagramSpec.model_validate(
                {"topology": "loop", "nodes": [{"label": "A", "station": "decision"}, {"label": "B"}]}
            )

    def test_exactly_one_outer_return(self) -> None:
        with pytest.raises(ValueError, match="exactly one outer"):
            DiagramSpec.model_validate(
                {
                    "topology": "loop",
                    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                    "edges": [
                        {"from": "a", "to": "b", "circuit": "return"},
                        {"from": "b", "to": "a", "circuit": "return"},
                    ],
                }
            )

    def test_missing_return_rejects(self) -> None:
        with pytest.raises(ValueError, match="exactly one outer"):
            DiagramSpec.model_validate(
                {
                    "topology": "loop",
                    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                    "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}],
                }
            )

    def test_external_requires_tap_circuit(self) -> None:
        spec = tap()
        spec["edges"][3] = {"from": "human", "to": "hero"}  # tap-in stripped of its circuit role
        with pytest.raises(ValueError, match="tap edges only"):
            DiagramSpec.model_validate(spec)

    def test_tap_in_direction_enforced(self) -> None:
        spec = tap()
        spec["edges"][3] = {"from": "hero", "to": "human", "circuit": "tap-in"}
        with pytest.raises(ValueError, match="tap-in"):
            DiagramSpec.model_validate(spec)

    def test_terminal_is_a_sink(self) -> None:
        spec = hillclimb()
        spec["edges"].append({"from": "done", "to": "change"})
        with pytest.raises(ValueError, match="sink"):
            DiagramSpec.model_validate(spec)

    def test_decision_spends_exactly_two_exits(self) -> None:
        with pytest.raises(ValueError, match="exactly two"):
            DiagramSpec.model_validate(
                {
                    "topology": "loop",
                    "nodes": [{"id": "a", "label": "A"}, {"id": "d", "label": "D?", "station": "decision"}],
                    "edges": [{"from": "a", "to": "d"}, {"from": "d", "to": "a", "circuit": "return"}],
                }
            )

    def test_accumulates_only_on_the_return(self) -> None:
        with pytest.raises(ValueError, match="circuit: return"):
            DiagramSpec.model_validate(
                {
                    "topology": "loop",
                    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                    "edges": [
                        {"from": "a", "to": "b", "accumulates": True},
                        {"from": "b", "to": "a", "circuit": "return"},
                    ],
                }
            )

    def test_circuit_edge_cannot_be_bidirectional(self) -> None:
        with pytest.raises(ValueError, match="bidirectional"):
            DiagramSpec.model_validate(
                {
                    "topology": "loop",
                    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                    "edges": [{"from": "b", "to": "a", "circuit": "return", "direction": "both"}],
                }
            )

    def test_unreachable_station_rejects(self) -> None:
        spec = hillclimb()
        spec["nodes"].append({"id": "orphan", "label": "Orphan"})
        # Give the orphan an edge so the id checks pass but the circuit never
        # reaches it from the entry.
        spec["edges"].append({"from": "orphan", "to": "measure"})
        with pytest.raises(ValueError, match="not reachable"):
            DiagramSpec.model_validate(spec)


class TestScopeGrammar:
    def test_scope_boundary_never_crossed(self) -> None:
        spec = nested()
        spec["edges"][0] = {"from": "plan", "to": "i1", "label": "delegate"}
        with pytest.raises(ValueError, match="scope boundary"):
            DiagramSpec.model_validate(spec)

    def test_scope_members_are_plain_stations(self) -> None:
        spec = nested()
        spec["nodes"][2] = {"id": "i1", "label": "Decide?", "enclosure": "scope", "station": "decision"}
        with pytest.raises(ValueError, match=r"guard-less|plain"):
            DiagramSpec.model_validate(spec)

    def test_enclosure_must_name_a_scope(self) -> None:
        spec = nested()
        spec["nodes"][2] = {"id": "i1", "label": "Decide", "enclosure": "plan"}
        with pytest.raises(ValueError, match="station: scope"):
            DiagramSpec.model_validate(spec)

    def test_scope_inner_circuit_closes_once(self) -> None:
        spec = nested()
        spec["edges"][3] = {"from": "i3", "to": "i1", "label": "next call"}  # return role dropped
        with pytest.raises(ValueError, match="inner return"):
            DiagramSpec.model_validate(spec)

    def test_scope_needs_two_members(self) -> None:
        spec = nested()
        for node in spec["nodes"]:
            if node["id"] in ("i2", "i3"):
                node.pop("enclosure")
        with pytest.raises(ValueError, match=r"at least two members|member"):
            DiagramSpec.model_validate(spec)


class TestOffLoopRejections:
    def test_station_off_loop(self) -> None:
        with pytest.raises(ValueError, match="loop-only"):
            DiagramSpec.model_validate(
                {
                    "topology": "dag",
                    "nodes": [{"id": "a", "label": "A", "station": "decision"}, {"id": "b", "label": "B"}],
                    "edges": [{"from": "a", "to": "b"}],
                }
            )

    def test_partition_off_loop(self) -> None:
        with pytest.raises(ValueError, match="loop-only"):
            DiagramSpec.model_validate(
                {"topology": "pipeline", "nodes": [{"label": "A", "partition": "advance"}, {"label": "B"}]}
            )

    def test_circuit_off_loop(self) -> None:
        with pytest.raises(ValueError, match="loop-only"):
            DiagramSpec.model_validate(
                {
                    "topology": "dag",
                    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                    "edges": [{"from": "a", "to": "b", "circuit": "return"}],
                }
            )


class TestPayloadStability:
    def test_defaults_stay_out_of_the_dump(self) -> None:
        s = DiagramSpec.model_validate(endless("A", "B", "C"))
        dump = s.model_dump(exclude_defaults=True, mode="json")
        assert "motion_register" not in dump
        assert all("station" not in n and "partition" not in n and "enclosure" not in n for n in dump["nodes"])

    def test_loop_vocabulary_round_trips(self) -> None:
        s = DiagramSpec.model_validate(hillclimb())
        dump = s.model_dump(exclude_defaults=True, mode="json")
        again = DiagramSpec.model_validate(dump)
        assert again == s

    def test_motion_register_serializes_when_set(self) -> None:
        s = DiagramSpec.model_validate({**endless("A", "B", "C"), "motion_register": "turn"})
        assert s.model_dump(exclude_defaults=True, mode="json")["motion_register"] == "turn"
