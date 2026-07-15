"""Layered-graph algorithms: ranking, ordering, cycle + self-loop partition.

The pure combinatorial layer beneath the dag/state-machine solvers in
``graph.py`` — indices in, structure out, zero geometry. Ranks are ORDINAL
(0, 1, 2 …): a rank number is a column position, not a distance, so after
seeding and relaxation the occupied ranks are compressed to consecutive
integers. Self-loops (source == target) are partitioned out FIRST: they are
neither ranked (they'd add a phantom +1 to their own node) nor counted as
cycle-closing back-edges (``back_edges`` keys on a cross-color hit and a
same-node edge trivially re-enters its own grey node — a false cycle). They
render as their own arc via ``route.self_loop``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hyperweave.core.diagram import ResolvedEdge


def split_self_loops(edges: list[ResolvedEdge]) -> tuple[list[int], list[int]]:
    """Partition edge positions into (self-loop indices, non-self indices).

    A self-loop (``source == target``) is a node revisiting itself; it carries
    no rank or crossing information and would corrupt both — so every ranking,
    ordering, and back-edge pass runs on the non-self remainder, and the loop
    indices route separately. BOTH lists index the ORIGINAL edge list, so the
    caller keeps geo/motion alignment and can rebuild the non-self sublist as
    ``[edges[j] for j in non_self]``."""
    self_loops = [j for j, e in enumerate(edges) if e.source == e.target]
    non_self = [j for j, e in enumerate(edges) if e.source != e.target]
    return self_loops, non_self


def longest_path_ranks(n: int, edges: list[ResolvedEdge], fixed: Mapping[int, int] | None = None) -> list[int]:
    """Ordinal rank per node: the longest edge-count path from any source,
    seeded by caller pins and compressed to consecutive integers.

    ``fixed`` pins a node to a starting rank (``DiagramNode.rank`` — dag rank
    override); an unpinned node seeds at 0. Relaxation raises a target to
    ``source + 1`` whenever that is higher, EXCEPT it never moves a pinned
    target (its rank is authored). Acyclicity is validated upstream; iterate to
    a fixpoint (``n`` passes max). After relaxation the occupied ranks are
    remapped to 0..k-1 so gaps left by pins or sparse graphs don't open empty
    columns — rank is a position, not a measured depth. Self-loops must be
    excluded before this (see ``split_self_loops``): a ``v->v`` edge would try
    to push ``rank[v] >= rank[v] + 1`` forever."""
    fixed = fixed or {}
    rank = [fixed.get(i, 0) for i in range(n)]
    for _ in range(n):
        changed = False
        for e in edges:
            if e.target in fixed:
                continue  # a pinned target keeps its authored rank
            if rank[e.target] < rank[e.source] + 1:
                rank[e.target] = rank[e.source] + 1
                changed = True
        if not changed:
            break
    # Compress to consecutive ordinals: an authored pin at rank 5 with no
    # ranks 1-4 occupied must not open four empty columns.
    occupied = sorted(set(rank))
    remap = {r: i for i, r in enumerate(occupied)}
    return [remap[r] for r in rank]


def check_rank_contradiction(edges: list[ResolvedEdge], rank: list[int], fixed: Mapping[int, int]) -> None:
    """A pinned edge must still point forward: if the caller authored ranks
    such that an edge ``a -> b`` ends with ``rank[a] >= rank[b]``, the pins
    contradict the flow — raise naming the edge (no silent reorder). Only
    edges touching a pin can contradict (unpinned targets relax forward by
    construction), so the check is scoped to those."""
    from hyperweave.core.diagram import DiagramInputError

    for e in edges:
        if (e.source in fixed or e.target in fixed) and rank[e.source] >= rank[e.target]:
            raise DiagramInputError(
                f"rank override contradicts edge {e.source}->{e.target}: "
                f"source lands at rank {rank[e.source]} but target at {rank[e.target]} "
                f"(a forward edge needs source rank < target rank)"
            )


def barycenter_orders(n: int, edges: list[ResolvedEdge], rank: list[int], sweeps: int = 4) -> dict[int, list[int]]:
    """Per-rank vertical orders after fixed barycenter sweeps.

    Initial order is spec order; each down pass orders a rank by the mean
    position of predecessors, each up pass by successors. Stable sorts on
    rounded keys keep ties in current order — same input, same layout."""
    ranks = sorted(set(rank))
    orders: dict[int, list[int]] = {r: [i for i in range(n) if rank[i] == r] for r in ranks}
    preds: dict[int, list[int]] = {}
    succs: dict[int, list[int]] = {}
    for e in edges:
        preds.setdefault(e.target, []).append(e.source)
        succs.setdefault(e.source, []).append(e.target)

    def position(r: int) -> dict[int, int]:
        return {node: i for i, node in enumerate(orders[r])}

    def sweep(rank_seq: list[int], neighbors: dict[int, list[int]], neighbor_rank_of: int) -> None:
        for r in rank_seq:
            ref = r + neighbor_rank_of
            if ref not in orders:
                continue
            pos = position(ref)
            keyed = []
            for node in orders[r]:
                ns = [pos[p] for p in neighbors.get(node, []) if rank[p] == ref]
                keyed.append((round(sum(ns) / len(ns), 4) if ns else float(position(r)[node]), node))
            orders[r] = [node for _, node in sorted(keyed, key=lambda kv: kv[0])]

    for _ in range(sweeps):
        sweep(ranks[1:], preds, -1)  # down: order by predecessors above-left
        sweep(list(reversed(ranks[:-1])), succs, +1)  # up: order by successors
    return orders


def back_edges(n: int, edges: list[ResolvedEdge]) -> set[int]:
    """Edge positions that close a cycle — DFS in edge order (deterministic).

    Positions index the passed ``edges`` list. Self-loops must be excluded
    first (``split_self_loops``): a ``v->v`` edge re-enters its own grey node
    and would register as a false back-edge, so the revise-loop budget must
    never see one. When called on a non-self sublist, the caller remaps the
    returned positions to original edge indices for geo alignment."""
    adj: dict[int, list[tuple[int, int]]] = {}
    for j, e in enumerate(edges):
        adj.setdefault(e.source, []).append((j, e.target))
    color = [0] * n
    back: set[int] = set()

    def dfs(u: int) -> None:
        color[u] = 1
        for j, v in adj.get(u, []):
            if color[v] == 1:
                back.add(j)
            elif color[v] == 0:
                dfs(v)
        color[u] = 2

    for s in range(n):
        if color[s] == 0:
            dfs(s)
    return back
