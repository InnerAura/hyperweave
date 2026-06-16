"""Diagram input seam: coercion, normalization, presets.

Precedence mirrors the matrix seam: an explicit ``spec.diagram`` wins; a
server-known preset (``data/presets/diagram.yaml`` — content as data, zero
Python per preset) fills otherwise; no usable input raises. Normalization
resolves what is structure, never rhetoric: AUTO roles land on the
topology's focal slot, comparison's left card mutes, empty ids fill
``n{i}``, and ``direction: both`` expands to its reciprocal pair. The
solver guards on receiving a normalized spec.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hyperweave.config.loader import load_diagram_presets
from hyperweave.core.diagram import (
    DiagramEdge,
    DiagramInputError,
    DiagramNode,
    DiagramSpec,
    NodeRole,
    Topology,
    focal_slot,
)

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec


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
    on comparison's left card; topologies without a focal slot (pipeline,
    flywheel, sequence, dag, state-machine) resolve AUTO to DEFAULT — their
    hero is caller rhetoric. Returns a new frozen spec; rhetoric the caller
    declared passes through untouched.
    """
    focal = focal_slot(spec.topology, len(spec.nodes))
    nodes: list[DiagramNode] = []
    for i, node in enumerate(spec.nodes):
        updates: dict[str, Any] = {}
        if not node.id:
            updates["id"] = f"n{i}"
        if node.role is NodeRole.AUTO:
            if focal is not None and i == focal:
                updates["role"] = NodeRole.HERO
            elif spec.topology is Topology.COMPARISON and i == 0:
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


def coerce_diagram_input(connector_data: dict[str, Any] | None, spec: ComposeSpec) -> DiagramSpec:
    """Normalize whatever the transport carried into a solved-ready spec."""
    if spec.diagram is not None:
        return resolve_auto_roles(spec.diagram)
    preset_name = str((connector_data or {}).get("diagram_preset") or "")
    if preset_name:
        return resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset(preset_name)))
    raise DiagramInputError("diagram frame requires a topology: pass spec.diagram (a DiagramSpec) or a server preset")
