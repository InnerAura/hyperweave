"""Layered-graph algorithms + dag/state-machine self-loop integration.

layered.py is the pure combinatorial layer beneath graph.py: ordinal ranking
(with caller pins + compression), barycenter ordering, cycle detection, and the
self-loop partition. These pins hold the algorithm contracts, then exercise the
integration through compose: rank overrides move columns, self-loops draw as
their own arc on the chosen side, and a self-loop is NOT counted as a back-edge
(the bug the partition fixes — a v->v edge re-enters its own grey DFS node).
"""

from __future__ import annotations

import pytest

from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import resolve_auto_roles
from hyperweave.compose.diagram.layered import (
    back_edges,
    check_rank_contradiction,
    longest_path_ranks,
    split_self_loops,
)
from hyperweave.config.loader import load_diagram_config, load_paradigms
from hyperweave.core.diagram import DiagramCapacityError, DiagramInputError, DiagramSpec, ResolvedEdge

ENGINE = load_diagram_config()


def solve(**kw: object) -> object:
    paradigm = load_paradigms()["primer"].diagram
    spec = resolve_auto_roles(DiagramSpec.model_validate(kw))
    return compute_diagram_layout(spec, paradigm=paradigm, engine=ENGINE, palette_len=5)


def solve_promoted(**kw: object) -> object:
    """Solve after the cyclic-dag promotion the input seam applies — a cyclic
    ``topology: dag`` becomes state-machine before layout (what the real
    compose path does via ``coerce_diagram_input``)."""
    from hyperweave.compose.diagram.input import promote_cyclic_dag

    paradigm = load_paradigms()["primer"].diagram
    raw = resolve_auto_roles(DiagramSpec.model_validate(kw))
    normalized = promote_cyclic_dag(raw)
    return compute_diagram_layout(normalized.spec, paradigm=paradigm, engine=ENGINE, palette_len=5)


def _edges(*pairs: tuple[int, int]) -> list[ResolvedEdge]:
    return [ResolvedEdge(source=a, target=b) for a, b in pairs]


def _label_texts(lay: object) -> list[str]:
    """Rendered edge-label text — subsumed into annotations by the annotate
    pass (a self-loop's label rides ``geo.label_pos`` into a label
    annotation, not the connector)."""
    return [t.text for a in lay.annotations for t in a.lines]  # type: ignore[attr-defined]


class TestLongestPathRanks:
    def test_chain_ranks_are_consecutive(self) -> None:
        # 0->1->2->3: a straight chain ranks 0,1,2,3.
        rank = longest_path_ranks(4, _edges((0, 1), (1, 2), (2, 3)))
        assert rank == [0, 1, 2, 3]

    def test_longest_path_wins(self) -> None:
        # 0->1->2 and 0->2: node 2 takes the LONGER path (rank 2, not 1).
        rank = longest_path_ranks(3, _edges((0, 1), (1, 2), (0, 2)))
        assert rank == [0, 1, 2]

    def test_fixed_pin_seeds_and_holds(self) -> None:
        # Pin node 2 forward to rank 2 (its derived rank would be 1 via 0->2).
        rank = longest_path_ranks(3, _edges((0, 1), (0, 2)), fixed={2: 2})
        assert rank[0] == 0
        assert rank[1] == 1
        assert rank[2] == 2  # the pin held

    def test_compression_closes_gaps(self) -> None:
        # A pin at rank 9 with nothing between must compress to consecutive
        # ordinals — rank is a column position, not a measured depth.
        rank = longest_path_ranks(3, _edges((0, 1), (0, 2)), fixed={2: 9})
        assert sorted(set(rank)) == [0, 1, 2]  # 3 columns, not 10
        assert rank[2] == 2  # still the last column

    def test_self_loop_free_input_assumed(self) -> None:
        # longest_path_ranks must be given self-loop-free edges (the solver
        # partitions first); a chain of two ranks two nodes.
        rank = longest_path_ranks(2, _edges((0, 1)))
        assert rank == [0, 1]


class TestRankContradiction:
    def test_forward_pins_pass(self) -> None:
        rank = [0, 1, 2]
        check_rank_contradiction(_edges((0, 1), (1, 2)), rank, fixed={2: 2})  # no raise

    def test_backward_pin_raises_naming_edge(self) -> None:
        # Pin makes edge 1->2 point backward (rank[1]=2 >= rank[2]=1).
        rank = [0, 2, 1]
        with pytest.raises(DiagramInputError, match=r"1->2"):
            check_rank_contradiction(_edges((0, 1), (1, 2)), rank, fixed={1: 2, 2: 1})

    def test_unpinned_edges_never_contradict(self) -> None:
        # With no pins, the check is a no-op (relaxation guarantees forward).
        rank = [0, 1, 2]
        check_rank_contradiction(_edges((0, 1), (1, 2)), rank, fixed={})


class TestSplitSelfLoops:
    def test_partitions_indices(self) -> None:
        edges = _edges((0, 1), (1, 1), (1, 2), (2, 2))
        loops, non_self = split_self_loops(edges)
        assert loops == [1, 3]
        assert non_self == [0, 2]

    def test_no_self_loops_leaves_all(self) -> None:
        edges = _edges((0, 1), (1, 2))
        loops, non_self = split_self_loops(edges)
        assert loops == []
        assert non_self == [0, 1]


class TestBackEdges:
    def test_detects_the_cycle_closer(self) -> None:
        # 0->1->2->0: the 2->0 edge (index 2) closes the cycle.
        assert back_edges(3, _edges((0, 1), (1, 2), (2, 0))) == {2}

    def test_self_loop_would_falsely_register(self) -> None:
        # A v->v edge re-enters its own grey node — WITHOUT the partition it
        # registers as a back-edge. This pins the exact bug split_self_loops
        # exists to prevent: on the raw list the self-loop IS flagged.
        assert back_edges(3, _edges((0, 1), (1, 1), (1, 2))) == {1}
        # After the partition, the non-self sublist has no false back-edge.
        edges = _edges((0, 1), (1, 1), (1, 2))
        _loops, non_self = split_self_loops(edges)
        flow = [edges[j] for j in non_self]
        assert back_edges(3, flow) == set()


class TestDagRankOverride:
    def test_forward_pin_moves_the_column(self) -> None:
        # a->b, a->c; pin c to rank 2. c should land in a third column (its
        # derived rank is 1, same as b).
        lay = solve(
            topology="dag",
            nodes=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C", "rank": 2}],
            edges=[{"source": "a", "target": "b"}, {"source": "a", "target": "c"}],
        )
        xs = {n.node_id: round(n.box.x, 1) for n in lay.nodes}  # type: ignore[attr-defined]
        assert xs["a"] < xs["b"] < xs["c"]  # three distinct columns, c last

    def test_contradicting_pin_raises_through_compose(self) -> None:
        # Pin a downstream node behind its predecessor → DiagramInputError.
        with pytest.raises(DiagramInputError, match="rank override contradicts"):
            solve(
                topology="dag",
                nodes=[
                    {"id": "a", "label": "A", "rank": 5},
                    {"id": "b", "label": "B", "rank": 2},
                    {"id": "c", "label": "C"},
                ],
                edges=[{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
            )

    def test_huge_pin_compresses_columns(self) -> None:
        lay = solve(
            topology="dag",
            nodes=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C", "rank": 9}],
            edges=[{"source": "a", "target": "b"}, {"source": "a", "target": "c"}],
        )
        ncols = len({round(n.box.x, 1) for n in lay.nodes})  # type: ignore[attr-defined]
        assert ncols == 3  # not 10 — ordinal compression


class TestSelfLoopIntegration:
    def test_dag_self_loop_draws_its_own_arc(self) -> None:
        lay = solve(
            topology="dag",
            nodes=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
            edges=[
                {"source": "a", "target": "b"},
                {"source": "b", "target": "b", "label": "retry"},
                {"source": "b", "target": "c"},
            ],
        )
        conns = lay.connectors  # type: ignore[attr-defined]
        assert len(conns) == 3
        loop = conns[1]
        assert " C " in loop.path_d  # a cubic arc, not a degenerate line
        assert loop.marker_d == ""  # self-loops are exempt from the D5 arrow default
        # The label rides the loop's anchor through the subsumption pipeline
        # into a label annotation (post-#4: connectors no longer carry labels).
        assert "retry" in _label_texts(lay)

    def test_dag_self_loop_anchors_on_top_side(self) -> None:
        # Default DAG loop side is top: both mouth points sit ABOVE the node
        # center (the arc bows out of the content band).
        lay = solve(
            topology="dag",
            nodes=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
            edges=[
                {"source": "a", "target": "b"},
                {"source": "b", "target": "b"},
                {"source": "b", "target": "c"},
            ],
        )
        node_b = next(n for n in lay.nodes if n.node_id == "b")  # type: ignore[attr-defined]
        loop = lay.connectors[1]  # type: ignore[attr-defined]
        # The first cubic control point (bow direction) is above the node top.
        first_y = float(loop.path_d.split("C")[1].split()[1].split(",")[1])
        assert first_y < node_b.box.y  # bows upward, above the card top

    def test_sm_self_loop_is_not_a_back_edge(self) -> None:
        # Three self-loops would blow sm_max_back_edges IF miscounted; here two
        # self-loops + a real back-edge all coexist under their separate caps
        # (sm_max_self_loops=2, sm_max_back_edges=2). Before the partition the
        # self-loops ate the back-edge budget.
        lay = solve(
            topology="state-machine",
            nodes=[{"id": "s", "label": "S"}, {"id": "r", "label": "R"}, {"id": "d", "label": "D"}],
            edges=[
                {"source": "s", "target": "r"},
                {"source": "r", "target": "r", "label": "tool_call"},
                {"source": "r", "target": "d"},
                {"source": "d", "target": "s"},  # a genuine back-edge
            ],
        )
        # All four connectors placed; the self-loop carries its label (subsumed
        # into an annotation), and it drew a cubic arc.
        conns = lay.connectors  # type: ignore[attr-defined]
        assert len(conns) == 4
        assert "tool_call" in _label_texts(lay)
        assert " C " in conns[1].path_d

    def test_sm_self_loop_cap_enforced(self) -> None:
        # Three distinct self-loops exceeds sm_max_self_loops (2).
        with pytest.raises(DiagramCapacityError, match="self-loop"):
            solve(
                topology="state-machine",
                nodes=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
                edges=[
                    {"source": "a", "target": "b"},
                    {"source": "b", "target": "c"},
                    {"source": "a", "target": "a"},
                    {"source": "b", "target": "b"},
                    {"source": "c", "target": "c"},
                ],
            )


class TestFsmShapedPromotion:
    def test_cyclic_dag_promotes_and_renders_self_loop(self) -> None:
        # An agent lifecycle declared as a DAG but carrying a self-loop
        # (tool_call revise) AND a cycle: it promotes to state-machine and the
        # self-loop renders as its arc — the FSM-shaped case end-to-end.
        lay = solve_promoted(
            topology="dag",
            title="Agent",
            nodes=[
                {"id": "idle", "label": "IDLE"},
                {"id": "run", "label": "RUN"},
                {"id": "done", "label": "DONE"},
            ],
            edges=[
                {"source": "idle", "target": "run"},
                {"source": "run", "target": "run", "label": "tool_call"},
                {"source": "run", "target": "done"},
                {"source": "done", "target": "idle"},  # cycle → promotes to SM
            ],
        )
        assert lay.layout_slug == "state-machine"  # type: ignore[attr-defined]
        # The self-loop survived promotion: a cubic arc among the connectors
        # and its label subsumed into an annotation.
        assert any(" C " in c.path_d for c in lay.connectors)  # type: ignore[attr-defined]
        assert "tool_call" in _label_texts(lay)
