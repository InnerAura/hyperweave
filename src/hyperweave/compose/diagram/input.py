"""Diagram input seam: coercion, normalization, presets, auto-promotion.

Precedence mirrors the matrix seam: an explicit ``spec.diagram`` wins; a
server-known preset (``data/presets/diagram.yaml`` — content as data, zero
Python per preset) fills otherwise; no usable input raises. Normalization
resolves what is structure, never rhetoric: AUTO roles land on the
topology's focal slot, comparison's left card mutes, empty ids fill
``n{i}``, and ``direction: both`` expands to its reciprocal pair. The
solver guards on receiving a normalized spec.

Auto-promotion is the seam that lets a caller declare ``topology: dag`` for
a graph that turns out cyclic and still get a coherent artifact: a cyclic
DAG promotes to ``state-machine`` (which owns back-edges) with a warning.
The IR no longer hard-raises on the cycle — a frozen model can't re-dispatch
its own topology — so the decision lives HERE, where a fresh spec can be
constructed. ``coerce_diagram_input`` returns a :class:`NormalizedInput`
carrying the solved-ready spec plus any warnings for the caller's stderr.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hyperweave.config.loader import load_diagram_presets
from hyperweave.core.diagram import (
    DiagramEdge,
    DiagramInputError,
    DiagramNode,
    DiagramSpec,
    NodeRole,
    Topology,
    _find_cycle,
    focal_slot,
)

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec


@dataclass(frozen=True, slots=True)
class NormalizedInput:
    """The solved-ready spec plus the caller's payload spec and any warnings.

    ``spec`` is the RENDERED spec — post-normalization (AUTO roles resolved,
    ``direction: both`` expanded) and post-promotion (cyclic dag →
    state-machine). Solvers, layout slug, and ``data-hw-subvariant`` read it.

    ``payload_spec`` is the CALLER's spec (its declared topology, e.g. dag)
    with roles resolved against that topology — so the payload round-trips as
    the caller wrote it. For every non-promoted input the two are the same
    object's normalization, keeping payloads byte-identical.

    ``warnings`` are human-readable strings the caller surfaces (CLI stderr)
    — empty for the common case, so a clean input emits no
    ``rendered.warnings`` key and its payload stays byte-stable."""

    spec: DiagramSpec
    payload_spec: DiagramSpec
    warnings: tuple[str, ...] = ()


def diagram_preset_names() -> tuple[str, ...]:
    return tuple(sorted(load_diagram_presets()))


def resolve_diagram_preset(name: str) -> dict[str, Any]:
    """A preset's DiagramSpec dict, or a DiagramInputError naming the menu."""
    presets = load_diagram_presets()
    found = presets.get(name)
    if found is None:
        known = ", ".join(sorted(presets)) or "(none configured)"
        raise DiagramInputError(f"unknown diagram preset {name!r}; known presets: {known}")
    return dict(found)


def resolve_auto_roles(spec: DiagramSpec) -> DiagramSpec:
    """Normalize structure: AUTO roles, auto ids, ``direction: both``.

    AUTO resolves to HERO on the topology's structural focal slot and MUTED
    on comparison's left card and on a state-machine's fail states (the
    figure grammar's contrast tier: an AUTO node whose every outgoing edge
    returns to an EARLIER state is the off-happy-path dead end —
    cicd-machine renders it muted, never as a plain ground card);
    everything else resolves AUTO to DEFAULT — hero is caller rhetoric.
    Returns a new frozen spec; declared rhetoric passes through untouched.
    """
    focal = focal_slot(spec.topology, len(spec.nodes))
    index_of = {node.id: i for i, node in enumerate(spec.nodes) if node.id}
    sm_muted: set[int] = set()
    if spec.topology is Topology.STATE_MACHINE:
        for i, node in enumerate(spec.nodes):
            if node.role is not NodeRole.AUTO or not node.id:
                continue
            outgoing = [e for e in spec.edges if e.source == node.id and e.target != node.id]
            if outgoing and all(index_of.get(e.target, i) < i for e in outgoing):
                sm_muted.add(i)
    nodes: list[DiagramNode] = []
    for i, node in enumerate(spec.nodes):
        updates: dict[str, Any] = {}
        if not node.id:
            updates["id"] = f"n{i}"
        if node.role is NodeRole.AUTO:
            if focal is not None and i == focal:
                updates["role"] = NodeRole.HERO
            elif (spec.topology is Topology.COMPARISON and i == 0) or i in sm_muted:
                updates["role"] = NodeRole.MUTED
            else:
                updates["role"] = NodeRole.DEFAULT
        nodes.append(node.model_copy(update=updates) if updates else node)
    edges: list[DiagramEdge] = []
    for edge in spec.edges:
        if edge.direction == "both":
            single = edge.model_copy(update={"direction": ""})
            edges.append(single)
            edges.append(single.model_copy(update={"source": edge.target, "target": edge.source}))
        else:
            edges.append(edge)
    return spec.model_copy(update={"nodes": nodes, "edges": edges})


def promote_cyclic_dag(spec: DiagramSpec) -> NormalizedInput:
    """Promote a cyclic DAG to state-machine, or pass an acyclic spec through.

    The DAG solver is a longest-path layered layout — a back-edge has no
    rank. State-machine owns back-edges (the revise loop), so a caller who
    declared ``topology: dag`` for a graph that turns out cyclic gets a
    coherent artifact under the state-machine solver plus a warning naming
    the cycle. Non-dag specs and acyclic dags return unchanged (``spec`` and
    ``payload_spec`` identical, no warning → byte-identical payload). On
    promotion ``spec`` becomes the state-machine variant (what renders) while
    ``payload_spec`` keeps the caller's dag (what round-trips)."""
    if spec.topology is not Topology.DAG:
        return NormalizedInput(spec=spec, payload_spec=spec)
    index = {(n.id or f"n{i}"): i for i, n in enumerate(spec.nodes)}
    directed = {(index[e.source], index[e.target]) for e in spec.edges}
    cycle = _find_cycle(len(spec.nodes), directed)
    if not cycle:
        return NormalizedInput(spec=spec, payload_spec=spec)
    labels = " -> ".join(spec.nodes[i].label for i in cycle)
    promoted = spec.model_copy(update={"topology": Topology.STATE_MACHINE})
    return NormalizedInput(
        spec=promoted,
        payload_spec=spec,
        warnings=(f"cyclic dag promoted to state-machine (cycle: {labels})",),
    )


def coerce_diagram_input(connector_data: dict[str, Any] | None, spec: ComposeSpec) -> NormalizedInput:
    """Normalize whatever the transport carried into a solved-ready spec.

    Returns a :class:`NormalizedInput`: AUTO roles resolved, ``direction:
    both`` expanded, and a cyclic dag promoted to state-machine (with a
    warning). The warning — when present — flows to the caller's stderr and
    the payload's ``rendered.warnings``."""
    if spec.diagram is not None:
        return _finalize(spec.diagram)
    preset_name = str((connector_data or {}).get("diagram_preset") or "")
    if preset_name:
        return _finalize(DiagramSpec.model_validate(resolve_diagram_preset(preset_name)))
    raise DiagramInputError("diagram frame requires a topology: pass spec.diagram (a DiagramSpec) or a server preset")


def _finalize(raw: DiagramSpec) -> NormalizedInput:
    """Promote (cyclic dag → state-machine) then resolve roles on both specs.

    ``spec`` resolves roles against the RENDERED topology (state-machine when
    promoted, so the solver sees a self-consistent spec). ``payload_spec``
    resolves roles against the CALLER's declared topology (dag) so the
    payload round-trips as written. For non-promoted inputs the two are the
    same spec, so role resolution is identical and payloads stay
    byte-stable."""
    promoted = promote_cyclic_dag(raw)
    rendered_spec = resolve_auto_roles(promoted.spec)
    if promoted.payload_spec is promoted.spec:
        payload_spec = rendered_spec
    else:
        payload_spec = resolve_auto_roles(promoted.payload_spec)
    return NormalizedInput(spec=rendered_spec, payload_spec=payload_spec, warnings=promoted.warnings)
