"""Diagram projections — payload, envelope digest, markdown shadow, desc.

The diagram is a polyglot container: the SVG is one projection of the
``DiagramSpec`` IR, never its source. The payload pairs the spec with the
RENDERED record (per-edge motion post-ladder, per-edge track, per-node
glyph tint, the performance tier) so requested vs rendered never silently
diverges — and, P4, the envelope id is therefore ARTIFACT identity: the
same spec under a different edge_motion hashes differently, exactly as a
different genome or variant already does. No test may assert cross-motion
id stability.

The envelope digest is pattern + n + semantic content only: orientation,
node_style, glyph, edge_motion, entrance, and track are presentational and
never reach it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from hyperweave.core.diagram import DiagramSpec, EdgeKind, NodeRole, layout_slug, resolved_edges
from hyperweave.core.envelope import cdata_safe_json

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import RenderedMotion

PAYLOAD_SCHEMA = "diagram/1"

ENVELOPE_NODE_CAP = 12
ENVELOPE_EDGE_CAP = 16


def diagram_payload_json(spec: DiagramSpec, rendered: RenderedMotion) -> str:
    """Canonical, lossless, CDATA-safe payload text.

    ``{"spec": ..., "rendered": ...}`` — the spec keeps the caller's
    requested motions intact (round-trip source: re-render ``spec`` under
    the same constraint and you reproduce the artifact); ``rendered``
    records what actually drew."""
    body = {
        "spec": spec.model_dump(mode="json", exclude_defaults=True),
        "rendered": {
            "edge_motion": list(rendered.edge_motion),
            "track": list(rendered.track),
            "glyph_tint": list(rendered.glyph_tint),
            "glyph_backing": list(rendered.glyph_backing),
            "performance": rendered.performance,
            "fallback_applied": rendered.fallback_applied,
        },
    }
    text = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    return cdata_safe_json(text)


def derive_subvariant(spec: DiagramSpec) -> str:
    """``data-hw-subvariant`` = the concrete layout slug (14 values)."""
    return layout_slug(spec)


def _edge_lines(spec: DiagramSpec) -> list[str]:
    lines: list[str] = []
    for e in resolved_edges(spec):
        arrow = f"{spec.nodes[e.source].label} → {spec.nodes[e.target].label}"
        if e.label:
            arrow += f" ({e.label})" if e.kind is EdgeKind.NONE else f" ({e.label}, {e.kind.value})"
        elif e.kind is not EdgeKind.NONE:
            arrow += f" ({e.kind.value})"
        lines.append(arrow)
    return lines


def diagram_envelope_data(spec: DiagramSpec) -> dict[str, Any]:
    """The hwz/1 ``data`` digest: pattern + n + semantic content.

    A topology's meaning is its pattern — the typed compaction the PRD
    asked for — plus enough content (hero, node labels, edge lines) for a
    receiving agent to act without the SVG. Presentational fields never
    reach this digest."""
    data: dict[str, Any] = {
        "pattern": spec.topology.value,
        "n": len(spec.nodes),
    }
    hero = next((n for n in spec.nodes if n.role is NodeRole.HERO), None)
    if hero is not None:
        data["hero"] = hero.label
    nodes = {n.label: n.desc for n in spec.nodes[:ENVELOPE_NODE_CAP]}
    data["nodes"] = nodes
    if len(spec.nodes) > ENVELOPE_NODE_CAP:
        data["nodes_total"] = len(spec.nodes)
    edges = _edge_lines(spec)
    data["edges"] = edges[:ENVELOPE_EDGE_CAP]
    if len(edges) > ENVELOPE_EDGE_CAP:
        data["edges_total"] = len(edges)
    return data


def to_markdown(spec: DiagramSpec) -> str:
    """The minimal text shadow: title, topology, nodes, edge lines."""
    lines: list[str] = []
    if spec.title:
        head = f"**{spec.title}**"
        if spec.subtitle:
            head += f" — {spec.subtitle}"
        lines.append(head)
        lines.append("")
    topo = spec.topology.value
    if layout_slug(spec) != topo:
        topo += f" ({spec.orientation.value})"
    lines.append(f"Topology: {topo}")
    lines.append("")
    for n in spec.nodes:
        item = f"- **{n.label}**"
        if n.desc:
            item += f" — {n.desc}"
        if n.role is NodeRole.HERO:
            item += " *(hero)*"
        elif n.role is NodeRole.MUTED:
            item += " *(muted)*"
        if n.note:
            item += f" — {n.note}"
        lines.append(item)
    lines.append("")
    lines.extend(_edge_lines(spec))
    return "\n".join(lines).strip() + "\n"


def diagram_desc(spec: DiagramSpec, *, subvariant: str) -> str:
    """The generated aria description."""
    edges = _edge_lines(spec)
    shown = "; ".join(edges[:6]) + ("; …" if len(edges) > 6 else "")
    parts = [
        f"{spec.title or spec.topology.value}: {subvariant} diagram,",
        f"{len(spec.nodes)} nodes, {len(edges)} edges.",
    ]
    if spec.subtitle:
        parts.append(f"{spec.subtitle}.")
    parts.append(f"Flow: {shown}.")
    parts.append("Full data in hw:payload.")
    return " ".join(parts)
