"""Row-order pinning — the id-level seam between transform and the dag solver.

``transform`` needs the parent's rendered order to pin the child's rows, but
geometry is never persisted for fresh artifacts: the solve is deterministic,
so a parent without ``layout`` pins re-derives exactly what it rendered from
its declaration alone (rank + barycenter are pure functions of nodes+edges —
no boxes, no canvas). A parent that IS a transform child carries its pins in
the payload, so chains read the rendered truth instead of re-deriving a
pre-pin order. Both paths meet here: ``spec_rank_orders`` speaks raw payload
spec dicts (the transform verb's world), ``resolve_layout_pins`` speaks the
validated DiagramSpec (the solver's world).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.layered import (
    barycenter_orders,
    longest_path_ranks,
    pinned_orders,
    split_self_loops,
)
from hyperweave.core.diagram import DiagramInputError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hyperweave.core.diagram import DiagramSpec


@dataclass(frozen=True, slots=True)
class _Ends:
    source: int
    target: int


def _node_ids(nodes: Sequence[Mapping[str, Any]]) -> list[str]:
    """Spec-dict node ids, empty ids filled with the ``n{i}`` convention
    (mirrors resolve_auto_roles, so pins written against a normalized payload
    always resolve)."""
    return [str(node.get("id") or f"n{i}") for i, node in enumerate(nodes)]


def spec_rank_orders(spec: Mapping[str, Any], prior: Sequence[Sequence[str]] | None = None) -> list[list[str]]:
    """Per-rank node ids in vertical order for a raw diagram spec dict.

    ``prior=None`` re-derives the declaration's own solve (what a fresh
    compose renders). With ``prior`` — a parent's rank_orders — survivors
    keep their pinned relative order and new nodes append at their rank's
    extent, which is exactly the order the pinned child solve will render.
    Ids named by ``prior`` that no longer exist simply drop (a removal patch
    is a legitimate ancestor)."""
    nodes = list(spec.get("nodes") or [])
    ids = _node_ids(nodes)
    index_of = {node_id: i for i, node_id in enumerate(ids)}
    edges: list[_Ends] = []
    for edge in spec.get("edges") or []:
        source, target = str(edge.get("source", "")), str(edge.get("target", ""))
        if source not in index_of or target not in index_of:
            raise DiagramInputError(f"edge {source!r}->{target!r} names a node absent from the spec")
        edges.append(_Ends(source=index_of[source], target=index_of[target]))
    fixed = {i: int(node["rank"]) for i, node in enumerate(nodes) if node.get("rank") is not None}
    _, non_self = split_self_loops(edges)
    flow = [edges[j] for j in non_self]
    rank = longest_path_ranks(len(nodes), flow, fixed)
    if prior is None:
        orders = barycenter_orders(len(nodes), flow, rank)
    else:
        runs = [[index_of[node_id] for node_id in run if node_id in index_of] for run in prior]
        orders = pinned_orders(len(nodes), rank, runs)
    return [[ids[i] for i in orders[r]] for r in sorted(orders)]


def child_rank_orders(parent_spec: Mapping[str, Any], child_spec: Mapping[str, Any]) -> list[list[str]]:
    """The child's pinned rank orders for a transform: parent order inherited
    (persisted pins when the parent is itself a child, else the parent's own
    deterministic re-solve), insertions at the extent."""
    persisted = (parent_spec.get("layout") or {}).get("rank_orders")
    prior: Sequence[Sequence[str]] = persisted if persisted else spec_rank_orders(parent_spec)
    return spec_rank_orders(child_spec, prior=prior)


def transform_note_facts(spec: DiagramSpec) -> dict[str, str] | None:
    """Slot values for the reasoning transform note, from the lineage record.

    None for an untransformed spec (no note renders). ``delta`` is a terse
    formulaic summary of the LAST patch; ``seat`` names where an inserted
    node landed in the pinned order (rank, row ordinal) — the one spatial
    fact the pins alone can state without re-solving geometry."""
    if not spec.lineage:
        return None
    patch_raw = (spec.lineage[-1] or {}).get("patch") or []
    patch = patch_raw if isinstance(patch_raw, list) else [patch_raw]
    added_nodes: list[str] = []
    added_edges = 0
    removed = 0
    other = 0
    for op in patch:
        if not isinstance(op, dict):
            continue
        kind, path = str(op.get("op", "")), str(op.get("path", ""))
        raw_value = op.get("value")
        value: dict[str, Any] = raw_value if isinstance(raw_value, dict) else {}
        if kind == "add" and path.startswith("/nodes"):
            added_nodes.append(str(value.get("id") or value.get("label") or "node"))
        elif kind == "add" and path.startswith("/edges"):
            added_edges += 1
        elif kind == "remove":
            removed += 1
        else:
            other += 1
    bits: list[str] = []
    if added_nodes:
        bits.append("+" + " +".join(added_nodes))
    if added_edges:
        bits.append(f"+{added_edges} edge{'s' if added_edges != 1 else ''}")
    if removed:
        bits.append(f"{removed} removal{'s' if removed != 1 else ''}")
    if other:
        bits.append(f"{other} field edit{'s' if other != 1 else ''}")
    delta = ", ".join(bits) if bits else "empty patch"
    seat = "none — structure-preserving edit"
    runs = spec.layout.rank_orders if spec.layout is not None else ()
    hit = next(
        (
            (node_id, r, i + 1, len(run))
            for r, run in enumerate(runs)
            for i, node_id in enumerate(run)
            if node_id in added_nodes
        ),
        None,
    )
    if hit is not None:
        seat = f"{hit[0]} at rank {hit[1]}, row {hit[2]}/{hit[3]}"
    return {"delta": delta, "seat": seat}


def resolve_layout_pins(spec: DiagramSpec) -> list[list[int]] | None:
    """``spec.layout`` as node-index runs for the solver, validated loud.

    None when the spec carries no pins (the fresh-compose default). A pin
    naming an unknown node, or naming one twice, is an authoring error — the
    figure it claims to preserve doesn't exist — so it raises rather than
    silently re-deriving."""
    if spec.layout is None or not spec.layout.rank_orders:
        return None
    index_of = {node.id: i for i, node in enumerate(spec.nodes) if node.id}
    seen: set[str] = set()
    runs: list[list[int]] = []
    for run in spec.layout.rank_orders:
        indices: list[int] = []
        for node_id in run:
            if node_id in seen:
                raise DiagramInputError(f"layout.rank_orders names node {node_id!r} twice; a node holds one row")
            if node_id not in index_of:
                raise DiagramInputError(f"layout.rank_orders names unknown node {node_id!r}; pins must name spec nodes")
            seen.add(node_id)
            indices.append(index_of[node_id])
        runs.append(indices)
    return runs
