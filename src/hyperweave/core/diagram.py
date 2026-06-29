"""Diagram frame IR — the universal topology graph the diagram frame renders.

``DiagramSpec`` is the schema decoupler for explanatory instruments: the frame
never sees a caller's domain schema, only this IR. Adapters (raw JSON via
CLI/POST/MCP, server-known presets) normalize INTO it; every projection (SVG
layout, ``hw:payload``, the markdown shadow, the hwz/1 envelope) reads FROM
it. The visual is one projection of the IR, never the source of truth.

Edge doctrine (hybrid): for the closed topologies the node ORDER is the
structure and :func:`derive_edges` is canonical — explicit ``edges`` are
optional presentational/direction overlays that must cover the derived pair
set as undirected pairs, at most once per direction (reciprocal pairs render
as parallel lanes). Tree is the hybrid exception: its explicit edges express
HIERARCHY (the depth >= 2 case) and validate as a rooted tree instead of
against the derived star. Sequence, dag, and state-machine are data
topologies: their edges ARE the content and are required. ``resolved_edges``
canonicalizes both forms into index-based records so solvers and projections
never branch on which form the caller used.

Inference policy (matrix doctrine): structure is data-derivable and may be
normalized (AUTO roles, ``direction: both`` expansion — both in the input
seam); rhetoric is caller-only (``role: hero`` outside focal slots, ``accent``
overrides, ``node_style``). Count caps, orientation legality, and depth
policy are YAML data enforced at the input seam — this module stays
config-blind.

This module is a leaf: it imports only ``core.base`` and ``core.matrix``
(for the shared ``GlyphTint`` contract) so ``core/models.py`` can nest
``DiagramSpec`` on ``ComposeSpec``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from hyperweave.core.base import FrozenModel
from hyperweave.core.matrix import GlyphTint  # noqa: TC001 (Pydantic needs at runtime)


class Topology(StrEnum):
    """Named layout pattern — the semantic unit of a diagram.

    A topology's meaning is its pattern: the hwz/1 envelope compacts a
    diagram to ``{"pattern": <topology>, "n": <nodes>}`` plus content.
    """

    PIPELINE = "pipeline"
    FANOUT = "fanout"
    CONVERGENCE = "convergence"
    FLYWHEEL = "flywheel"
    STACK = "stack"
    TREE = "tree"
    COMPARISON = "comparison"
    SEQUENCE = "sequence"
    DAG = "dag"
    STATE_MACHINE = "state-machine"


class Orientation(StrEnum):
    """Second presentational axis. Legality per topology is config data
    (``data/config/diagram-frame.yaml: orientation_legality``), enforced at the input seam."""

    HORIZONTAL = "horizontal"
    BILATERAL = "bilateral"
    UPWARD = "upward"
    RADIAL = "radial"


class NodeRole(StrEnum):
    """Card treatment. AUTO resolves at the input seam and never reaches a
    layout: focal slot -> HERO, comparison left -> MUTED, else DEFAULT."""

    AUTO = "auto"
    DEFAULT = "default"
    HERO = "hero"  # accent-bordered focal card
    MUTED = "muted"  # comparison-left grammar: gray dashed border, muted text, no dot


class NodeStyle(StrEnum):
    """Node identity anatomy — caller-chosen, never inferred. Frame default
    comes from the paradigm chassis (per topology); per-node overrides win."""

    CARD = "card"
    GLYPH_CIRCLE = "glyph-circle"
    CARD_GLYPH = "card+glyph"


class EdgeMotion(StrEnum):
    """The closed connector-motion vocabulary — a 2x2, not a list.

    {composite-only, paint-ok} x {discrete, continuous}: particle | dash |
    beam | flow. New aesthetics are parameters owned by the genome's kinetic
    channel, never new values. Fallback ladder under a composite-only
    constraint: beam -> particle, flow -> dash.
    """

    DASH = "dash"
    PARTICLE = "particle"
    BEAM = "beam"
    FLOW = "flow"


class EdgeKind(StrEnum):
    """Sequence message semantics: solid stroke = call, dashed = return.
    Meaning-bearing dasharray — the track channel yields to it (P3)."""

    NONE = ""
    CALL = "call"
    RETURN = "return"


class DiagramInputError(ValueError):
    """No usable diagram input, or an input that cannot be normalized.
    Maps to HTTP 422 / the SMPTE error badge."""


class DiagramCapacityError(DiagramInputError):
    """Diagram exceeds the hard caps (nodes/ranks/loops). Split the diagram;
    compose never crowds a topology."""


class DiagramNode(FrozenModel):
    """One node: identity text plus caller-chosen presentation."""

    id: str = Field(default="", description="Stable node id (edges reference this; empty auto-fills 'n{i}')")
    label: str = Field(description="Card name line")
    desc: str = Field(default="", description="Mono caption line; wraps to chassis max_desc_lines then truncates")
    role: NodeRole = Field(default=NodeRole.AUTO, description="auto resolves: focal->hero, comparison-left->muted")
    accent: int | None = Field(
        default=None, ge=0, description="Explicit flow-palette index (caller-only; None = cycle assignment)"
    )
    glyph: str = Field(default="", description="Glyph registry id (data/registries/glyphs.json) for the identity slot")
    glyph_tint: GlyphTint | None = Field(
        default=None,
        description="Per-slot tint override (ink | brand | full); None defers to spec then genome per-frame default",
    )
    style: NodeStyle | None = Field(
        default=None, description="Per-node anatomy override; None defers to spec then chassis default"
    )
    short: str = Field(default="", description="Mono text inside a glyph-circle when no glyph is set (e.g. 'hw')")
    note: str = Field(default="", description="Payload/markdown-only detail; never rendered in the SVG")


class DiagramEdge(FrozenModel):
    """One directed edge. For the closed topologies this is an optional
    overlay on the derived structure; for sequence/dag/state-machine it IS
    the content (ordered for sequence)."""

    source: str = Field(description="Source node id")
    target: str = Field(description="Target node id")
    label: str = Field(
        default="",
        description=(
            "Edge label. Rendered only where the topology's chassis declares "
            "renders_edge_labels (sequence, state-machine); elsewhere it "
            "reaches payload/markdown only"
        ),
    )
    kind: EdgeKind = Field(default=EdgeKind.NONE, description="Sequence message semantics (call | return)")
    edge_motion: EdgeMotion | None = Field(
        default=None, description="Per-edge motion override; None defers to spec then genome default"
    )
    state: Literal["", "inert"] = Field(
        default="", description="inert kills motion on this edge (semantic, frame-invariant)"
    )
    direction: Literal["", "both"] = Field(
        default="",
        description="'both' is sugar: expands to the reciprocal pair at the input seam (parallel lanes)",
    )


class DiagramSpec(FrozenModel):
    """The universal diagram IR — request input, ``hw:payload`` body,
    markdown shadow source, and envelope source, all at once."""

    title: str = Field(default="", description="Header title; empty (with empty subtitle) collapses the header")
    subtitle: str = Field(default="", description="Header descriptor line")
    topology: Topology = Field(description="Named layout pattern")
    orientation: Orientation = Field(
        default=Orientation.HORIZONTAL,
        description="Presentational axis; legality per topology is config data",
    )
    nodes: list[DiagramNode] = Field(min_length=2, description="Ordered nodes — ORDER IS STRUCTURE (closed topologies)")
    edges: list[DiagramEdge] = Field(
        default_factory=list,
        description=(
            "Explicit edges. Required for sequence/dag/state-machine (and "
            "multi-level trees); optional overlay on the closed topologies"
        ),
    )
    edge_motion: EdgeMotion | None = Field(
        default=None, description="Artifact-level motion override; None defers to the genome default"
    )
    node_style: NodeStyle | None = Field(
        default=None, description="Artifact-level anatomy override; None defers to the chassis default"
    )
    glyph_tint: GlyphTint | None = Field(
        default=None,
        description="Artifact-level tint override; None defers to the genome per-frame default",
    )
    notes: str = Field(default="", description="Footer slug; empty renders the topology name uppercased")
    lineage: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Append-only edit history written by `transform` — each entry "
            "{parent_id, op, patch, ts}. Empty by default and excluded from the "
            "payload dump, so untransformed artifacts stay byte-identical; once "
            "populated it rides inside the hashed payload (tamper-evident)."
        ),
    )
    operator: str = Field(
        default="",
        max_length=4,
        description=(
            "Stack riser-rail annotation (G9): a short mono token stamped at "
            "each riser midpoint — the Composited Upward specimen's x. The "
            "SLOT is chassis geometry; the content is preset data. Empty "
            "renders no rail."
        ),
    )

    @model_validator(mode="after")
    def _validate_shape(self) -> DiagramSpec:
        """Structural grammar only — caps/legality/depth policy live in YAML."""
        declared = [n.id for n in self.nodes if n.id]
        if len(set(declared)) != len(declared):
            raise ValueError(f"diagram node ids must be unique, got {declared}")
        heroes = [i for i, n in enumerate(self.nodes) if n.role is NodeRole.HERO]
        if len(heroes) > 1:
            raise ValueError(f"at most one hero node (got nodes {heroes})")
        focal = focal_slot(self.topology, len(self.nodes))
        for i, n in enumerate(self.nodes):
            if n.role is NodeRole.MUTED and focal is not None and i == focal:
                raise ValueError(f"node {i} ({n.label!r}) is the {self.topology.value} focal slot and cannot be muted")
        if self.edges:
            self._validate_edges(declared)
        elif self.topology in _EDGES_REQUIRED:
            raise ValueError(f"{self.topology.value} is a data topology: edges are the content and are required")
        return self

    def _validate_edges(self, declared: list[str]) -> None:
        ids = set(declared)
        seen: set[tuple[str, str]] = set()
        for e in self.edges:
            for ref in (e.source, e.target):
                if ref not in ids:
                    raise ValueError(f"edge references unknown node id {ref!r} (declared: {sorted(ids)})")
            if e.source == e.target:
                raise ValueError(f"self-loop {e.source!r}->{e.source!r} is not representable (split the state)")
            pairs = [(e.source, e.target)] if e.direction != "both" else [(e.source, e.target), (e.target, e.source)]
            for p in pairs:
                # Sequence messages are ordered EVENTS, not connectors — the
                # same directed pair repeats legitimately (call, later call).
                if p in seen and self.topology is not Topology.SEQUENCE:
                    raise ValueError(f"duplicate directed edge {p[0]!r}->{p[1]!r} (once per direction)")
                seen.add(p)
            if e.kind is not EdgeKind.NONE and self.topology is not Topology.SEQUENCE:
                raise ValueError("edge kind (call/return) is sequence message semantics only")
        index = {nid: i for i, nid in enumerate(declared)}
        directed = {(index[a], index[b]) for a, b in seen}
        if self.topology in _CLOSED_TOPOLOGIES and self.topology is not Topology.TREE:
            derived = {frozenset(p) for p in derive_edges(self)}
            explicit = {frozenset(p) for p in directed}
            if explicit != derived:
                raise ValueError(
                    f"explicit edges on a closed topology must cover the derived "
                    f"{self.topology.value} pair set exactly (as undirected pairs); "
                    f"got {sorted(tuple(sorted(p)) for p in explicit)}, "
                    f"expected {sorted(tuple(sorted(p)) for p in derived)}"
                )
        if self.topology is Topology.DAG:
            cycle = _find_cycle(len(self.nodes), directed)
            if cycle:
                labels = " -> ".join(self.nodes[i].label for i in cycle)
                raise ValueError(
                    f"dag edges contain a cycle ({labels}); use topology 'state-machine' for cyclic graphs"
                )
        if self.topology is Topology.TREE:
            _validate_tree_shape(len(self.nodes), directed)
        if self.topology is Topology.SEQUENCE:
            # Every node participating in messages must be a declared lifeline;
            # already guaranteed by the id check. Order is the given edge order.
            pass


# ── Structural constants ────────────────────────────────────────────────────

_CLOSED_TOPOLOGIES = frozenset(
    {
        Topology.PIPELINE,
        Topology.FANOUT,
        Topology.CONVERGENCE,
        Topology.FLYWHEEL,
        Topology.STACK,
        Topology.TREE,
        Topology.COMPARISON,
    }
)

_EDGES_REQUIRED = frozenset({Topology.SEQUENCE, Topology.DAG, Topology.STATE_MACHINE})


def focal_slot(topology: Topology, n: int) -> int | None:
    """The structural focal index AUTO resolves to HERO, or None.

    Pipeline, flywheel, sequence, dag, and state-machine have no structural
    focal slot — their hero is caller rhetoric.
    """
    if topology is Topology.FANOUT or topology is Topology.TREE or topology is Topology.STACK:
        return 0
    if topology is Topology.CONVERGENCE:
        return n - 1
    if topology is Topology.COMPARISON:
        return 1
    return None


def layout_slug(spec: DiagramSpec) -> str:
    """The concrete layout algorithm slug — also ``data-hw-subvariant``.

    14 values: the closed seven (fanout expanded by orientation, tree by
    radial), plus sequence, dag, and state-machine.
    """
    if spec.topology is Topology.FANOUT:
        return f"fanout-{spec.orientation.value}"
    if spec.topology is Topology.TREE and spec.orientation is Orientation.RADIAL:
        return "tree-radial"
    return spec.topology.value


def derive_edges(spec: DiagramSpec) -> tuple[tuple[int, int], ...]:
    """Canonical derived structure for the closed topologies (index pairs).

    pipeline: reading-order chain. fanout: nodes[0] -> each. convergence:
    each -> nodes[-1]. flywheel: ring cycle over non-hero nodes (a hero is
    the center axis, lifted out of the ring). stack: rising (nodes[0] is the
    top result; particles climb bottom -> top). tree: nodes[0] -> each
    (depth-1 star; multi-level trees declare explicit edges). comparison:
    the single before -> after pair.
    """
    n = len(spec.nodes)
    t = spec.topology
    if t is Topology.PIPELINE:
        return tuple((i, i + 1) for i in range(n - 1))
    if t is Topology.FANOUT:
        return tuple((0, j) for j in range(1, n))
    if t is Topology.CONVERGENCE:
        return tuple((j, n - 1) for j in range(n - 1))
    if t is Topology.FLYWHEEL:
        ring = [i for i, node in enumerate(spec.nodes) if node.role is not NodeRole.HERO]
        k = len(ring)
        return tuple((ring[i], ring[(i + 1) % k]) for i in range(k))
    if t is Topology.STACK:
        return tuple((i + 1, i) for i in range(n - 1))
    if t is Topology.TREE:
        return tuple((0, j) for j in range(1, n))
    if t is Topology.COMPARISON:
        return ((0, 1),)
    raise DiagramInputError(f"{t.value} is a data topology: edges are declared, never derived")


@dataclass(frozen=True, slots=True)
class ResolvedEdge:
    """Canonical directed edge — the single form solvers and projections
    consume, whether the caller declared edges or the topology derived them."""

    source: int
    target: int
    label: str = ""
    kind: EdgeKind = EdgeKind.NONE
    edge_motion: EdgeMotion | None = None
    inert: bool = False


def resolved_edges(spec: DiagramSpec) -> tuple[ResolvedEdge, ...]:
    """Canonicalize the spec's edges to index-based records.

    Explicit edges win (they carry labels, kinds, per-edge motion, and
    direction flips); ``direction: both`` expands to the reciprocal pair
    here so downstream code only ever sees directed singles. Closed
    topologies without explicit edges get the derived structure.
    """
    if not spec.edges:
        return tuple(ResolvedEdge(source=a, target=b) for a, b in derive_edges(spec))
    index = {n.id: i for i, n in enumerate(spec.nodes) if n.id}
    out: list[ResolvedEdge] = []
    for e in spec.edges:
        base = ResolvedEdge(
            source=index[e.source],
            target=index[e.target],
            label=e.label,
            kind=e.kind,
            edge_motion=e.edge_motion,
            inert=e.state == "inert",
        )
        out.append(base)
        if e.direction == "both":
            out.append(
                ResolvedEdge(
                    source=base.target,
                    target=base.source,
                    label=e.label,
                    kind=e.kind,
                    edge_motion=e.edge_motion,
                    inert=base.inert,
                )
            )
    return tuple(out)


def tree_depth(spec: DiagramSpec) -> int:
    """Depth of a tree spec: 1 for the derived star, else the longest
    root-to-leaf edge count over the explicit parent edges."""
    if spec.topology is not Topology.TREE:
        raise DiagramInputError("tree_depth is only defined for tree specs")
    if not spec.edges:
        return 1
    children: dict[int, list[int]] = {}
    for e in resolved_edges(spec):
        children.setdefault(e.source, []).append(e.target)

    def walk(i: int) -> int:
        kids = children.get(i, [])
        return 1 + max((walk(k) for k in kids), default=0)

    return walk(0) - 1


def _find_cycle(n: int, directed: set[tuple[int, int]]) -> list[int]:
    """Return one cycle as a node-index path (empty when acyclic)."""
    adj: dict[int, list[int]] = {}
    for a, b in sorted(directed):
        adj.setdefault(a, []).append(b)
    color = [0] * n  # 0 white, 1 gray, 2 black
    stack: list[int] = []

    def dfs(u: int) -> list[int]:
        color[u] = 1
        stack.append(u)
        for v in adj.get(u, []):
            if color[v] == 1:
                return [*stack[stack.index(v) :], v]
            if color[v] == 0:
                found = dfs(v)
                if found:
                    return found
        color[u] = 2
        stack.pop()
        return []

    for s in range(n):
        if color[s] == 0:
            found = dfs(s)
            if found:
                return found
    return []


def _validate_tree_shape(n: int, directed: set[tuple[int, int]]) -> None:
    """Explicit tree edges must form a tree rooted at nodes[0]: every
    non-root has exactly one parent, the root has none, all reachable."""
    parents: dict[int, list[int]] = {}
    for a, b in directed:
        parents.setdefault(b, []).append(a)
    if 0 in parents:
        raise ValueError("tree root (nodes[0]) cannot have a parent edge")
    for i in range(1, n):
        got = parents.get(i, [])
        if len(got) != 1:
            raise ValueError(f"tree node {i} must have exactly one parent edge (got {len(got)})")
    # Connectivity: walk from the root; every node must be reachable.
    children: dict[int, list[int]] = {}
    for a, b in directed:
        children.setdefault(a, []).append(b)
    seen = {0}
    frontier = [0]
    while frontier:
        u = frontier.pop()
        for v in children.get(u, []):
            if v in seen:
                raise ValueError("tree edges contain a cycle")
            seen.add(v)
            frontier.append(v)
    if len(seen) != n:
        missing = sorted(set(range(n)) - seen)
        raise ValueError(f"tree nodes {missing} are not reachable from the root")
