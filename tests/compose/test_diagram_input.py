"""Diagram IR structural grammar: derivation, canonicalization, validators.

Count caps, orientation legality, and depth policy are YAML data enforced at
the input seam (compose/diagram/input.py) and are tested alongside coercion;
this module pins the config-blind structural rules in core/diagram.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from hyperweave.core.diagram import (
    DiagramSpec,
    EdgeKind,
    Topology,
    derive_edges,
    focal_slot,
    layout_slug,
    resolved_edges,
    tree_depth,
)


def nodes(*labels: str, **overrides: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"label": lb} for lb in labels]
    for idx, fields in overrides.get("at", {}).items():  # type: ignore[union-attr]
        out[idx].update(fields)
    return out


def ided(*labels: str) -> list[dict[str, Any]]:
    return [{"id": lb.lower(), "label": lb} for lb in labels]


class TestDerivedEdges:
    def test_pipeline_chains_in_reading_order(self) -> None:
        s = DiagramSpec(topology="pipeline", nodes=nodes("A", "B", "C", "D"))
        assert derive_edges(s) == ((0, 1), (1, 2), (2, 3))

    def test_fanout_stars_from_first(self) -> None:
        s = DiagramSpec(topology="fanout", nodes=nodes("hub", "a", "b", "c"))
        assert derive_edges(s) == ((0, 1), (0, 2), (0, 3))

    def test_convergence_meets_at_last(self) -> None:
        s = DiagramSpec(topology="convergence", nodes=nodes("a", "b", "c", "out"))
        assert derive_edges(s) == ((0, 3), (1, 3), (2, 3))

    def test_flywheel_cycles_the_ring(self) -> None:
        s = DiagramSpec(topology="flywheel", nodes=nodes("p1", "p2", "p3", "p4"))
        assert derive_edges(s) == ((0, 1), (1, 2), (2, 3), (3, 0))

    def test_flywheel_hero_is_axis_not_ring(self) -> None:
        s = DiagramSpec(
            topology="flywheel",
            nodes=nodes("p1", "p2", "axis", "p3", at={2: {"role": "hero"}}),
        )
        assert derive_edges(s) == ((0, 1), (1, 3), (3, 0))

    def test_stack_rises_bottom_to_top(self) -> None:
        s = DiagramSpec(topology="stack", nodes=nodes("result", "frame", "genome"))
        assert derive_edges(s) == ((1, 0), (2, 1))

    def test_tree_stars_depth_one(self) -> None:
        s = DiagramSpec(topology="tree", nodes=nodes("root", "a", "b"))
        assert derive_edges(s) == ((0, 1), (0, 2))

    def test_comparison_single_pair(self) -> None:
        s = DiagramSpec(topology="comparison", nodes=nodes("before", "after"))
        assert derive_edges(s) == ((0, 1),)

    def test_data_topologies_never_derive(self) -> None:
        s = DiagramSpec(
            topology="sequence",
            nodes=ided("A", "B"),
            edges=[{"source": "a", "target": "b", "label": "call()"}],
        )
        with pytest.raises(Exception, match="declared, never derived"):
            derive_edges(s)


class TestLayoutSlug:
    @pytest.mark.parametrize(
        ("topology", "orientation", "slug"),
        [
            ("pipeline", "horizontal", "pipeline"),
            ("fanout", "horizontal", "fanout-horizontal"),
            ("fanout", "bilateral", "fanout-bilateral"),
            ("fanout", "upward", "fanout-upward"),
            ("fanout", "radial", "fanout-radial"),
            ("tree", "horizontal", "tree"),
            ("tree", "radial", "tree-radial"),
        ],
    )
    def test_slug_set(self, topology: str, orientation: str, slug: str) -> None:
        kwargs: dict[str, Any] = {"topology": topology, "orientation": orientation, "nodes": nodes("a", "b", "c")}
        if topology == "tree" and orientation == "radial":
            kwargs["nodes"] = ided("Root", "A", "B")
            kwargs["edges"] = [
                {"source": "root", "target": "a"},
                {"source": "root", "target": "b"},
            ]
        assert layout_slug(DiagramSpec(**kwargs)) == slug

    def test_data_topology_slugs(self) -> None:
        sm = DiagramSpec(
            topology="state-machine",
            nodes=ided("Draft", "Done"),
            edges=[{"source": "draft", "target": "done", "label": "ship"}],
        )
        assert layout_slug(sm) == "state-machine"


class TestStructuralValidators:
    def test_duplicate_ids_rejected(self) -> None:
        with pytest.raises(ValueError, match="unique"):
            DiagramSpec(topology="pipeline", nodes=[{"id": "x", "label": "A"}, {"id": "x", "label": "B"}])

    def test_two_heroes_rejected(self) -> None:
        with pytest.raises(ValueError, match="at most one hero"):
            DiagramSpec(
                topology="pipeline",
                nodes=nodes("A", "B", "C", at={0: {"role": "hero"}, 2: {"role": "hero"}}),
            )

    @pytest.mark.parametrize(
        ("topology", "n", "slot"),
        [("fanout", 4, 0), ("convergence", 4, 3), ("tree", 3, 0), ("stack", 3, 0), ("comparison", 2, 1)],
    )
    def test_muted_forbidden_on_focal_slot(self, topology: str, n: int, slot: int) -> None:
        assert focal_slot(Topology(topology), n) == slot
        labels = [f"N{i}" for i in range(n)]
        with pytest.raises(ValueError, match="focal slot"):
            DiagramSpec(topology=topology, nodes=nodes(*labels, at={slot: {"role": "muted"}}))

    @pytest.mark.parametrize("topology", ["pipeline", "flywheel", "sequence", "dag", "state-machine"])
    def test_no_structural_focal_slot(self, topology: str) -> None:
        assert focal_slot(Topology(topology), 4) is None

    @pytest.mark.parametrize("topology", ["sequence", "dag", "state-machine"])
    def test_data_topologies_require_edges(self, topology: str) -> None:
        with pytest.raises(ValueError, match="edges are the content"):
            DiagramSpec(topology=topology, nodes=ided("A", "B"))

    def test_unknown_edge_ref_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown node id"):
            DiagramSpec(
                topology="dag",
                nodes=ided("A", "B"),
                edges=[{"source": "a", "target": "ghost"}],
            )

    def test_self_loop_rejected(self) -> None:
        with pytest.raises(ValueError, match="self-loop"):
            DiagramSpec(
                topology="state-machine",
                nodes=ided("A", "B"),
                edges=[{"source": "a", "target": "a"}],
            )

    def test_duplicate_directed_edge_rejected(self) -> None:
        with pytest.raises(ValueError, match="once per direction"):
            DiagramSpec(
                topology="dag",
                nodes=ided("A", "B"),
                edges=[{"source": "a", "target": "b"}, {"source": "a", "target": "b"}],
            )

    def test_reciprocal_pair_is_legal(self) -> None:
        s = DiagramSpec(
            topology="pipeline",
            nodes=ided("Client", "Hw", "Server"),
            edges=[
                {"source": "client", "target": "hw"},
                {"source": "hw", "target": "client"},
                {"source": "hw", "target": "server"},
                {"source": "server", "target": "hw"},
            ],
        )
        assert len(resolved_edges(s)) == 4

    def test_direction_both_collides_with_explicit_reciprocal(self) -> None:
        with pytest.raises(ValueError, match="once per direction"):
            DiagramSpec(
                topology="comparison",
                nodes=ided("A", "B"),
                edges=[
                    {"source": "a", "target": "b", "direction": "both"},
                    {"source": "b", "target": "a"},
                ],
            )

    def test_kind_outside_sequence_rejected(self) -> None:
        with pytest.raises(ValueError, match="sequence message semantics"):
            DiagramSpec(
                topology="dag",
                nodes=ided("A", "B"),
                edges=[{"source": "a", "target": "b", "kind": "call"}],
            )

    def test_closed_topology_cover_must_match_derived(self) -> None:
        with pytest.raises(ValueError, match="cover the derived"):
            DiagramSpec(
                topology="pipeline",
                nodes=ided("A", "B", "C"),
                edges=[{"source": "a", "target": "c"}],  # skips the chain
            )

    def test_closed_topology_direction_flip_passes(self) -> None:
        s = DiagramSpec(
            topology="fanout",
            nodes=ided("Hub", "L", "R"),
            edges=[
                {"source": "l", "target": "hub"},  # flipped: inward
                {"source": "hub", "target": "r"},
            ],
        )
        flows = [(e.source, e.target) for e in resolved_edges(s)]
        assert flows == [(1, 0), (0, 2)]

    def test_dag_cycle_names_state_machine(self) -> None:
        with pytest.raises(ValueError, match="state-machine"):
            DiagramSpec(
                topology="dag",
                nodes=ided("A", "B", "C"),
                edges=[
                    {"source": "a", "target": "b"},
                    {"source": "b", "target": "c"},
                    {"source": "c", "target": "a"},
                ],
            )

    def test_tree_root_with_parent_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"root .* cannot have a parent"):
            DiagramSpec(
                topology="tree",
                nodes=ided("Root", "A"),
                edges=[{"source": "a", "target": "root"}],
            )

    def test_tree_two_parents_rejected(self) -> None:
        with pytest.raises(ValueError, match="exactly one parent"):
            DiagramSpec(
                topology="tree",
                nodes=ided("Root", "A", "B"),
                edges=[
                    {"source": "root", "target": "a"},
                    {"source": "root", "target": "b"},
                    {"source": "a", "target": "b"},
                ],
            )


class TestResolvedEdges:
    def test_direction_both_expands_to_reciprocal_pair(self) -> None:
        s = DiagramSpec(
            topology="comparison",
            nodes=ided("A", "B"),
            edges=[{"source": "a", "target": "b", "direction": "both", "label": "sync"}],
        )
        edges = resolved_edges(s)
        assert [(e.source, e.target) for e in edges] == [(0, 1), (1, 0)]
        assert all(e.label == "sync" for e in edges)

    def test_inert_state_carries(self) -> None:
        s = DiagramSpec(
            topology="comparison",
            nodes=ided("A", "B"),
            edges=[{"source": "a", "target": "b", "state": "inert"}],
        )
        assert resolved_edges(s)[0].inert is True

    def test_sequence_order_is_edge_order(self) -> None:
        s = DiagramSpec(
            topology="sequence",
            nodes=ided("Agent", "Hw", "GitHub"),
            edges=[
                {"source": "agent", "target": "hw", "label": "compose()", "kind": "call"},
                {"source": "hw", "target": "agent", "label": "artifact", "kind": "return"},
                {"source": "agent", "target": "github", "label": "embed", "kind": "call"},
            ],
        )
        edges = resolved_edges(s)
        assert [(e.source, e.target, e.kind) for e in edges] == [
            (0, 1, EdgeKind.CALL),
            (1, 0, EdgeKind.RETURN),
            (0, 2, EdgeKind.CALL),
        ]


class TestTreeDepth:
    def test_star_is_depth_one(self) -> None:
        assert tree_depth(DiagramSpec(topology="tree", nodes=nodes("r", "a", "b"))) == 1

    def test_two_level_explicit(self) -> None:
        s = DiagramSpec(
            topology="tree",
            nodes=ided("Root", "A", "B", "A1", "A2"),
            edges=[
                {"source": "root", "target": "a"},
                {"source": "root", "target": "b"},
                {"source": "a", "target": "a1"},
                {"source": "a", "target": "a2"},
            ],
        )
        assert tree_depth(s) == 2
