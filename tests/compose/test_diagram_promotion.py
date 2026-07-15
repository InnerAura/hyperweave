"""Cyclic-dag promotion, hub/lanes validators, rank overrides, byte-stability.

The promotion seam (``compose/diagram/input.py``) turns a caller's cyclic
``dag`` into a ``state-machine`` render while keeping the caller's spec in the
payload — so a re-render reproduces exactly what was declared. These pins
cover: the promotion mechanics + warning labels; the payload keeping the
declared topology; the ``rendered.warnings`` key appearing ONLY under
promotion (byte-stability); the hub/lanes structural validators; and dag
``rank`` overrides staying dag-only.
"""

from __future__ import annotations

import json

import pytest

from hyperweave.compose.diagram.input import (
    NormalizedInput,
    coerce_diagram_input,
    promote_cyclic_dag,
)
from hyperweave.compose.diagram.project import diagram_payload_json
from hyperweave.compose.diagram.records import RenderedMotion
from hyperweave.core.diagram import (
    DiagramEdge,
    DiagramNode,
    DiagramSpec,
    Topology,
)
from hyperweave.core.models import ComposeSpec


def _dag(edges: list[tuple[str, str]], *, labels: tuple[str, ...] = ("A", "B", "C")) -> DiagramSpec:
    return DiagramSpec(
        topology=Topology.DAG,
        nodes=[DiagramNode(id=lb.lower(), label=lb) for lb in labels],
        edges=[DiagramEdge(source=s, target=t) for s, t in edges],
    )


def _rendered(warnings: tuple[str, ...] = ()) -> RenderedMotion:
    return RenderedMotion(
        edge_motion=(),
        track=(),
        glyph_tint=(),
        performance="composite-only",
        fallback_applied=False,
        warnings=warnings,
    )


class TestPromotion:
    def test_cyclic_dag_promotes_to_state_machine(self) -> None:
        norm = promote_cyclic_dag(_dag([("a", "b"), ("b", "c"), ("c", "a")]))
        assert norm.spec.topology is Topology.STATE_MACHINE
        assert norm.payload_spec.topology is Topology.DAG
        assert len(norm.warnings) == 1

    def test_warning_names_the_cycle_with_real_labels(self) -> None:
        norm = promote_cyclic_dag(_dag([("a", "b"), ("b", "c"), ("c", "a")]))
        assert norm.warnings[0] == "cyclic dag promoted to state-machine (cycle: A -> B -> C -> A)"

    def test_acyclic_dag_is_not_promoted(self) -> None:
        norm = promote_cyclic_dag(_dag([("a", "b"), ("b", "c")]))
        assert norm.spec.topology is Topology.DAG
        assert norm.payload_spec is norm.spec
        assert norm.warnings == ()

    def test_non_dag_passes_through(self) -> None:
        spec = DiagramSpec(topology=Topology.PIPELINE, nodes=[DiagramNode(label="A"), DiagramNode(label="B")])
        norm = promote_cyclic_dag(spec)
        assert norm.spec is spec
        assert norm.warnings == ()

    def test_coerce_returns_normalized_input_with_warning(self) -> None:
        spec = ComposeSpec(type="diagram", diagram=_dag([("a", "b"), ("b", "c"), ("c", "a")]))
        norm = coerce_diagram_input(spec.connector_data, spec)
        assert isinstance(norm, NormalizedInput)
        assert norm.spec.topology is Topology.STATE_MACHINE
        assert norm.warnings and "state-machine" in norm.warnings[0]

    def test_coerce_acyclic_has_no_warnings(self) -> None:
        spec = ComposeSpec(type="diagram", diagram=_dag([("a", "b"), ("b", "c")]))
        norm = coerce_diagram_input(spec.connector_data, spec)
        assert norm.warnings == ()


class TestPayloadWarnings:
    def test_promoted_payload_keeps_declared_dag_topology(self) -> None:
        norm = promote_cyclic_dag(_dag([("a", "b"), ("b", "c"), ("c", "a")]))
        payload = json.loads(diagram_payload_json(norm.payload_spec, _rendered(norm.warnings)))
        assert payload["spec"]["topology"] == "dag"

    def test_promoted_payload_carries_rendered_warnings(self) -> None:
        norm = promote_cyclic_dag(_dag([("a", "b"), ("b", "c"), ("c", "a")]))
        payload = json.loads(diagram_payload_json(norm.payload_spec, _rendered(norm.warnings)))
        assert payload["rendered"]["warnings"] == list(norm.warnings)

    def test_clean_payload_omits_warnings_key(self) -> None:
        # Byte-stability: a diagram with no warnings emits no rendered.warnings
        # key, so its payload matches the pre-promotion schema exactly.
        payload = json.loads(diagram_payload_json(_dag([("a", "b"), ("b", "c")]), _rendered()))
        assert "warnings" not in payload["rendered"]


class TestByteDeterminism:
    def test_additive_fields_excluded_from_default_dump(self) -> None:
        # The new IR fields all default clean, so exclude_defaults keeps a
        # pre-existing diagram/1 payload byte-identical.
        spec = DiagramSpec(
            topology=Topology.PIPELINE,
            nodes=[DiagramNode(label="A"), DiagramNode(label="B"), DiagramNode(label="C")],
        )
        dump = spec.model_dump(mode="json", exclude_defaults=True)
        assert set(dump) == {"topology", "nodes"}
        for key in ("marker", "distribution", "annotations", "surface"):
            assert key not in dump
        for key in ("category", "rank", "anchor"):
            assert key not in dump["nodes"][0]

    def test_edge_additive_fields_excluded(self) -> None:
        edge = DiagramEdge(source="a", target="b")
        dump = edge.model_dump(mode="json", exclude_defaults=True)
        assert set(dump) == {"source", "target"}


class TestHubValidators:
    def _hub(self, edges: list[dict[str, str]], nodes: tuple[str, ...] = ("Hub", "A", "B")) -> DiagramSpec:
        return DiagramSpec(
            topology=Topology.HUB,
            nodes=[DiagramNode(id=lb.lower(), label=lb) for lb in nodes],
            edges=[DiagramEdge(**e) for e in edges],  # type: ignore[arg-type]
        )

    def test_hub_all_edges_incident_ok(self) -> None:
        s = self._hub([{"source": "hub", "target": "a"}, {"source": "b", "target": "hub"}])
        assert s.topology is Topology.HUB

    def test_hub_non_incident_edge_rejected(self) -> None:
        with pytest.raises(ValueError, match="incident to the hub"):
            self._hub([{"source": "hub", "target": "a"}, {"source": "a", "target": "b"}])

    def test_hub_zone_and_angle_exclusive(self) -> None:
        with pytest.raises(ValueError, match="both zone and angle"):
            self._hub([{"source": "hub", "target": "a", "zone": "N", "angle": 45.0}])  # type: ignore[dict-item]

    def test_role_illegal_off_hub(self) -> None:
        with pytest.raises(ValueError, match="hub-only"):
            DiagramSpec(
                topology=Topology.DAG,
                nodes=[DiagramNode(id="a", label="A"), DiagramNode(id="b", label="B"), DiagramNode(id="c", label="C")],
                edges=[DiagramEdge(source="a", target="b", role="out"), DiagramEdge(source="b", target="c")],
            )

    def test_hub_node_anchor_on_center_rejected(self) -> None:
        with pytest.raises(ValueError, match="cannot carry a compass anchor"):
            DiagramSpec(
                topology=Topology.HUB,
                nodes=[DiagramNode(id="hub", label="Hub", anchor="N"), DiagramNode(id="a", label="A")],
                edges=[DiagramEdge(source="hub", target="a")],
            )

    def test_node_anchor_illegal_off_hub(self) -> None:
        with pytest.raises(ValueError, match="hub-only"):
            DiagramSpec(
                topology=Topology.PIPELINE,
                nodes=[DiagramNode(label="A", anchor="N"), DiagramNode(label="B")],
            )


class TestLanesValidators:
    def test_lanes_categories_present_ok(self) -> None:
        s = DiagramSpec(
            topology=Topology.LANES,
            nodes=[DiagramNode(id="a", label="A", category="in"), DiagramNode(id="b", label="B", category="out")],
            edges=[DiagramEdge(source="a", target="b")],
        )
        assert s.topology is Topology.LANES

    def test_lanes_missing_category_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty category"):
            DiagramSpec(
                topology=Topology.LANES,
                nodes=[DiagramNode(id="a", label="A", category="in"), DiagramNode(id="b", label="B")],
                edges=[DiagramEdge(source="a", target="b")],
            )

    def test_route_illegal_off_lanes(self) -> None:
        with pytest.raises(ValueError, match="lanes-only"):
            DiagramSpec(
                topology=Topology.PIPELINE,
                nodes=[DiagramNode(id="a", label="A"), DiagramNode(id="b", label="B"), DiagramNode(id="c", label="C")],
                edges=[DiagramEdge(source="a", target="b", route="bus"), DiagramEdge(source="b", target="c")],
            )


class TestRankOverride:
    def test_rank_legal_on_dag(self) -> None:
        s = DiagramSpec(
            topology=Topology.DAG,
            nodes=[
                DiagramNode(id="a", label="A", rank=0),
                DiagramNode(id="b", label="B", rank=1),
                DiagramNode(id="c", label="C", rank=2),
            ],
            edges=[DiagramEdge(source="a", target="b"), DiagramEdge(source="b", target="c")],
        )
        assert [n.rank for n in s.nodes] == [0, 1, 2]

    def test_rank_illegal_off_dag(self) -> None:
        with pytest.raises(ValueError, match="dag-only"):
            DiagramSpec(
                topology=Topology.PIPELINE,
                nodes=[DiagramNode(label="A", rank=1), DiagramNode(label="B"), DiagramNode(label="C")],
            )


class TestAnnotationReferential:
    def test_node_ref_must_be_declared(self) -> None:
        with pytest.raises(ValueError, match="unknown node id"):
            DiagramSpec(
                topology=Topology.PIPELINE,
                nodes=[DiagramNode(id="a", label="A"), DiagramNode(id="b", label="B"), DiagramNode(id="c", label="C")],
                annotations=[{"text": "note", "kind": "callout", "node": "z"}],  # type: ignore[list-item]
            )

    def test_edge_ordinal_within_occurrence_count(self) -> None:
        s = DiagramSpec(
            topology=Topology.SEQUENCE,
            nodes=[DiagramNode(id="a", label="A"), DiagramNode(id="b", label="B")],
            edges=[DiagramEdge(source="a", target="b", label="1"), DiagramEdge(source="a", target="b", label="2")],
            annotations=[{"text": "x", "kind": "callout", "edge": "a->b#2"}],  # type: ignore[list-item]
        )
        assert len(s.annotations) == 1

    def test_edge_ordinal_over_count_rejected(self) -> None:
        with pytest.raises(ValueError, match="exceeds"):
            DiagramSpec(
                topology=Topology.SEQUENCE,
                nodes=[DiagramNode(id="a", label="A"), DiagramNode(id="b", label="B")],
                edges=[DiagramEdge(source="a", target="b")],
                annotations=[{"text": "x", "kind": "callout", "edge": "a->b#2"}],  # type: ignore[list-item]
            )

    def test_edge_ref_to_undeclared_edge_rejected(self) -> None:
        with pytest.raises(ValueError, match="not a declared edge"):
            DiagramSpec(
                topology=Topology.SEQUENCE,
                nodes=[DiagramNode(id="a", label="A"), DiagramNode(id="b", label="B")],
                edges=[DiagramEdge(source="a", target="b")],
                annotations=[{"text": "x", "kind": "callout", "edge": "b->a"}],  # type: ignore[list-item]
            )

    def test_region_anchor_passes_structurally(self) -> None:
        s = DiagramSpec(
            topology=Topology.PIPELINE,
            nodes=[DiagramNode(id="a", label="A"), DiagramNode(id="b", label="B"), DiagramNode(id="c", label="C")],
            annotations=[{"text": "key", "kind": "legend", "region": "footer"}],  # type: ignore[list-item]
        )
        assert s.annotations[0].region == "footer"
