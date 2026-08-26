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

import itertools
import json
import re
from typing import Any

import pytest

from hyperweave.compose.diagram.input import (
    NormalizedInput,
    coerce_diagram_input,
    promote_cyclic_dag,
    reciprocal_pairs,
)
from hyperweave.compose.diagram.project import diagram_payload_json
from hyperweave.compose.diagram.records import RenderedMotion
from hyperweave.compose.engine import compose
from hyperweave.core.diagram import (
    DiagramEdge,
    DiagramInputError,
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


class TestPromotionNamesEveryCause:
    """The warning is the caller's whole account of why their dag became a
    state-machine, so it names every cause. Naming only the first cycle the
    DFS happened to reach let a caller unpick the pair they were shown and
    promote again on the pair they were not — and request/response pairs
    arrive in twos and threes on real architecture graphs."""

    def test_one_reciprocal_pair_is_named_as_a_pair(self) -> None:
        norm = promote_cyclic_dag(_dag([("a", "b"), ("b", "a")]))
        assert norm.warnings[0] == "cyclic dag promoted to state-machine (1 reciprocal pair: A <-> B)"

    def test_both_reciprocal_pairs_are_named(self) -> None:
        norm = promote_cyclic_dag(_dag([("a", "b"), ("b", "a"), ("b", "c"), ("c", "b")]))
        assert norm.warnings[0] == "cyclic dag promoted to state-machine (2 reciprocal pairs: A <-> B, B <-> C)"

    def test_multi_hop_cycle_still_reads_as_a_cycle(self) -> None:
        # A three-node loop is NOT a round trip between two nodes; stripping
        # the pairs leaves it standing, so it keeps the cycle phrasing.
        norm = promote_cyclic_dag(_dag([("a", "b"), ("b", "c"), ("c", "a")]))
        assert "reciprocal" not in norm.warnings[0]
        assert "cycle: A -> B -> C -> A" in norm.warnings[0]

    def test_a_self_loop_is_not_a_reciprocal_pair(self) -> None:
        # a -> a is one edge, not two opposed ones. It stays an ordinary
        # cycle — the distinction the duplex work downstream depends on.
        norm = promote_cyclic_dag(_dag([("a", "a"), ("a", "b")]))
        assert "reciprocal" not in norm.warnings[0]
        assert "cycle: A -> A" in norm.warnings[0]

    def test_pairs_and_a_multi_hop_cycle_are_reported_together(self) -> None:
        norm = promote_cyclic_dag(
            _dag([("a", "b"), ("b", "c"), ("c", "a"), ("a", "d"), ("d", "a")], labels=("A", "B", "C", "D"))
        )
        assert "cycle: A -> B -> C -> A" in norm.warnings[0]
        assert "1 reciprocal pair: A <-> D" in norm.warnings[0]

    def test_reciprocal_pairs_helper_ignores_one_way_edges(self) -> None:
        assert reciprocal_pairs({(0, 1), (1, 0), (1, 2)}) == [(0, 1)]

    def test_reciprocal_pairs_helper_excludes_self_loops(self) -> None:
        assert reciprocal_pairs({(0, 0), (1, 1)}) == []


class TestNoInputErrorMessage:
    def test_names_every_real_path(self) -> None:
        # Every reachable input path must be named — the message shouldn't
        # teach a shape that fails on the surface that shows it (the CLI
        # error was naming only ``spec.diagram``, which no CLI flag sets).
        with pytest.raises(DiagramInputError) as exc_info:
            coerce_diagram_input(None, ComposeSpec(type="diagram"))
        message = str(exc_info.value)
        assert "--spec-file" in message
        assert "spec.diagram" in message
        assert "diagram_preset" in message


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


_CYCLIC_DAG = {
    "topology": "dag",
    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
    "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}, {"source": "c", "target": "a"}],
}
_ACYCLIC_DAG = {
    "topology": "dag",
    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
    "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
}


# The architecture graph a caller actually sent: five components, two
# request/response pairs (engine<->parsers, engine<->models), captions longer
# than a state card's one-line budget, and a chip on every edge. It renders
# through the state-machine solver, so every state-machine defect it touches
# is a defect a dag caller sees.
_ARCHITECTURE_DAG = {
    "topology": "dag",
    "title": "readme-ai Architecture",
    "subtitle": "Directed execution graph",
    "node_style": "card+glyph",
    "nodes": [
        {"id": "cli", "label": "CLI Interface", "desc": "Commands & Configuration", "glyph": "terminal"},
        {"id": "parsers", "label": "Parsers & Extractors", "desc": "AST & Dependency Analysis", "glyph": "package"},
        {
            "id": "core",
            "label": "Pipeline Engine",
            "desc": "readme-ai async orchestrator",
            "glyph": "cpu",
            "role": "hero",
        },
        {"id": "models", "label": "Model Providers", "desc": "OpenAI / Gemini / Claude / Ollama", "glyph": "sparkles"},
        {"id": "generators", "label": "Markdown & Visuals", "desc": "HyperWeave SVGs & Docs", "glyph": "layers"},
    ],
    "edges": [
        {"source": "cli", "target": "core", "label": "invoke", "label_style": "chip"},
        {"source": "core", "target": "parsers", "label": "extract", "label_style": "chip"},
        {"source": "parsers", "target": "core", "label": "context", "label_style": "chip"},
        {"source": "core", "target": "models", "label": "synthesize", "label_style": "chip"},
        {"source": "models", "target": "core", "label": "responses", "label_style": "chip"},
        {"source": "core", "target": "generators", "label": "render", "label_style": "chip", "relation": "assert"},
    ],
}

_CHIP_RECT_RE = re.compile(
    r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"[^>]*class="hw-[0-9a-f]+-r?chipbg"'
)
_DESC_RE = re.compile(r'class="hw-[0-9a-f]+-[nmh]desc"[^>]*>([^<]*)</text>')


def _payload_from_svg(svg: str) -> dict[str, Any]:
    m = re.search(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>", svg, re.DOTALL)
    assert m, "hw:payload missing"
    return json.loads(m.group(1))  # type: ignore[no-any-return]


class TestPromotedArchitectureRender:
    """The promoted render, graded on what a reader can actually see.

    A promoted spec is still somebody's artifact — until the dag solver takes
    reciprocal pairs natively, this IS the output for every request/response
    architecture graph, so the state-machine defects it exposes are pinned
    here at the rendered-SVG level rather than at the solver beneath it."""

    def _svg(self) -> str:
        spec = ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=_ARCHITECTURE_DAG)
        svg = compose(spec).svg
        assert 'data-hw-topology="state-machine"' in svg, "precondition: this spec promotes"
        return svg

    def test_captions_grow_their_card_instead_of_ellipsizing(self) -> None:
        # Three of these five captions outrun a single line. Under the
        # inherited one-line budget each lost its tail to an ellipsis.
        descs = _DESC_RE.findall(self._svg())
        assert descs, "no node captions rendered"
        truncated = [d for d in descs if d.rstrip().endswith("…")]
        assert truncated == [], f"captions truncated: {truncated}"

    def test_every_caption_survives_whole(self) -> None:
        # Stronger than "no ellipsis": the wrapped runs must reassemble into
        # the authored caption, so a silent mid-word drop cannot pass either.
        rendered = " ".join(_DESC_RE.findall(self._svg())).replace("&amp;", "&")
        for node in _ARCHITECTURE_DAG["nodes"]:
            assert node["desc"] in rendered, f"caption lost: {node['desc']!r}"  # type: ignore[index]

    def test_converging_chips_do_not_overlap(self) -> None:
        # The forward chip to the generators and the back-edge chip from the
        # parsers both arrive at the hero. Both are pinned to their own wire,
        # so neither used to yield and one rendered buried under the other.
        chips = [tuple(float(v) for v in m) for m in _CHIP_RECT_RE.findall(self._svg())]
        assert len(chips) == 6, f"expected a chip per edge, got {len(chips)}"
        for (x1, y1, w1, h1), (x2, y2, w2, h2) in itertools.combinations(chips, 2):
            ox = min(x1 + w1, x2 + w2) - max(x1, x2)
            oy = min(y1 + h1, y2 + h2) - max(y1, y2)
            assert ox <= 0 or oy <= 0, (
                f"chips overlap by {ox:.2f}x{oy:.2f}: ({x1:.0f},{y1:.0f}) and ({x2:.0f},{y2:.0f})"
            )


class TestPayloadRenderedTopology:
    """rendered.topology bridges a promoted render back to structured data —
    a payload reader should never have to parse ``rendered.warnings`` prose
    to learn what actually rendered (spec.topology stays the caller's dag)."""

    def test_promoted_payload_gets_rendered_topology_key(self) -> None:
        norm = promote_cyclic_dag(_dag([("a", "b"), ("b", "c"), ("c", "a")]))
        payload = json.loads(
            diagram_payload_json(norm.payload_spec, _rendered(norm.warnings), rendered_topology=norm.spec.topology)
        )
        assert payload["spec"]["topology"] == "dag"
        assert payload["rendered"]["topology"] == "state-machine"

    def test_unpromoted_rendered_topology_omits_the_key(self) -> None:
        spec = _dag([("a", "b"), ("b", "c")])
        payload = json.loads(diagram_payload_json(spec, _rendered(), rendered_topology=spec.topology))
        assert "topology" not in payload["rendered"]

    def test_topology_key_absent_when_argument_not_passed(self) -> None:
        # Byte-stability: the pre-existing call shape (no rendered_topology
        # kwarg) reproduces the pre-existing payload exactly.
        payload = json.loads(diagram_payload_json(_dag([("a", "b"), ("b", "c")]), _rendered()))
        assert "topology" not in payload["rendered"]

    def test_cyclic_dag_through_the_real_engine(self) -> None:
        # Guard Law: compose through the real engine and parse the real SVG,
        # not just the projection helper in isolation.
        svg = compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=_CYCLIC_DAG)).svg
        assert 'data-hw-topology="state-machine"' in svg
        payload = _payload_from_svg(svg)
        assert payload["spec"]["topology"] == "dag"
        assert payload["rendered"]["topology"] == "state-machine"

    def test_acyclic_dag_through_the_real_engine_has_no_topology_key(self) -> None:
        svg = compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=_ACYCLIC_DAG)).svg
        payload = _payload_from_svg(svg)
        assert "topology" not in payload["rendered"]


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
