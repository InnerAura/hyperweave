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
as parallel lanes). A ``relation: bypass`` edge (L4 — exception/privileged
path, artifact-roundtrip's transform -> artifact' loop) is the one declared
exception: it may ADD a pair beyond the derived set instead of covering one,
since its whole point is a privileged path the plain structure doesn't have.
Tree is the hybrid exception: its explicit edges express HIERARCHY (the
depth >= 2 case) and validate as a rooted tree instead of against the
derived star. Sequence, dag, and state-machine are data topologies: their
edges ARE the content and are required. ``resolved_edges`` canonicalizes
both forms into index-based records so solvers and projections never branch
on which form the caller used.

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

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from hyperweave.core.base import FrozenModel
from hyperweave.core.diagram_annotations import (
    DiagramAnnotation,
    parse_edge_ref,
)
from hyperweave.core.matrix import GlyphTint  # noqa: TC001 (Pydantic needs at runtime)
from hyperweave.core.surface_spec import SurfaceSpec  # noqa: TC001 (Pydantic needs at runtime)


class Topology(StrEnum):
    """Named layout FAMILY — the semantic unit of a diagram (the family x
    expression consolidation, owner ruling 2026-08-20: fourteen flat words
    folded into families whose expressions ride the ``orientation`` axis).

    A topology's meaning is its pattern: the hwz/1 envelope compacts a
    diagram to ``{"pattern": <topology>, "n": <nodes>}`` plus content.

    The fan family carries its direction in the word itself (``fanout`` /
    ``fanin`` — one solver, one chassis family, opposite mouths). The
    retired flat words teach their new spelling at the input seam
    (``RETIRED_TOPOLOGIES``): ``convergence`` → ``fanin``; ``stack`` →
    ``pipeline`` + ``orientation: vertical``; ``flywheel`` → ``cycle`` +
    ``orientation: orbit``; ``ring`` → ``cycle`` + ``orientation: ring``.
    """

    PIPELINE = "pipeline"
    """Linear family: horizontal chain (rows or portrait heads), or the
    vertical operator stack via ``orientation: vertical``."""
    FANOUT = "fanout"
    CYCLE = "cycle"
    """The loop family: ``orientation: orbit`` — phases around a hero axis
    (the accumulator loop) — or ``orientation: ring`` — the equal-stage
    loop, N medallions at even pitch on one ring, EMPTY centre, no hero,
    circulation carried by congruent arc arrows."""
    FANIN = "fanin"
    """The fan family's inward direction: inputs fan into one mouth — the
    same fan-linear solver as ``fanout``, direction reversed."""
    TREE = "tree"
    COMPARISON = "comparison"
    SEQUENCE = "sequence"
    DAG = "dag"
    STATE_MACHINE = "state-machine"
    HUB = "hub"
    LANES = "lanes"


RETIRED_TOPOLOGIES: dict[str, str] = {
    "convergence": "topology: fanin — the fan family's inward direction (same solver, opposite mouth)",
    "stack": "topology: pipeline with orientation: vertical — the linear family's operator stack",
    "flywheel": "topology: cycle with orientation: orbit — the loop family's hero-axis accumulator",
    "ring": "topology: cycle with orientation: ring — the loop family's equal-stage empty-centre loop",
}
"""Hard-retired flat topology words → the family x expression spelling that
replaced each (the 2026-08-20 consolidation). Read by the input seam so the
refusal TEACHES the new spelling — an error-text record, never live
compatibility state (the rename-ledger preservation law)."""


class Orientation(StrEnum):
    """The EXPRESSION axis: which cell of its family a spec asks for.
    Legality per topology is config data (``data/config/diagram-frame.yaml:
    orientation_legality``), enforced at the input seam."""

    HORIZONTAL = "horizontal"
    BILATERAL = "bilateral"
    UPWARD = "upward"
    DOWNWARD = "downward"
    RADIAL = "radial"
    VERTICAL = "vertical"
    """Pipeline: the operator stack (bottom-to-top layers, the retired
    ``stack`` word's cell)."""
    ORBIT = "orbit"
    """Cycle: phases around a hero axis (the retired ``flywheel`` word)."""
    RING = "ring"
    """Cycle: the equal-stage empty-centre loop (the retired ``ring`` word)."""


class NodeRole(StrEnum):
    """Card treatment. AUTO resolves at the input seam and never reaches a
    layout: focal slot -> HERO, comparison left -> MUTED, else DEFAULT."""

    AUTO = "auto"
    DEFAULT = "default"
    HERO = "hero"  # accent-bordered focal card
    MUTED = "muted"  # contrast grammar: gray dashed border, muted text, no dot
    GROUND = "ground"  # figure grammar: the declared backdrop tier (renders as
    # the neutral ink card — declaring it fixes the node's tier so an auto
    # policy can never promote it, and the payload names the intent)


class NodeHealth(StrEnum):
    """Dependency-audit health channel: a card-corner status dot, ORTHOGONAL
    to identity accent (pp-tree-radial-v2.svg's own hw:chromatic: "node
    HEALTH on a separate status channel ... Identity accent and health
    status stay orthogonal"). OK renders no dot — attention lands only on
    the packages that need it. State-palette colors (never genome
    identity); VULNERABLE also pulses (status-pulse, critical only)."""

    OK = "ok"
    OUTDATED = "outdated"  # amber dot
    VULNERABLE = "vulnerable"  # red dot, pulsing


class NodeStyle(StrEnum):
    """Node identity anatomy — caller-chosen, never inferred. Rectangular
    card anatomies are topology-orthogonal; a topology whose connector math
    requires a plate may constrain non-card silhouettes. Frame defaults come
    from the paradigm chassis and per-node overrides win."""

    CARD = "card"
    GLYPH_CIRCLE = "glyph-circle"
    CARD_GLYPH = "card+glyph"
    CARD_LABEL = "card+label"
    """A card whose identity is TYPOGRAPHIC, not a mark: a small tracked mono
    label over a stack of display values (the bilateral-wings specimen's
    ``CPU / 14-core CPU / 10 performance cores``) — the inverse of the default
    card's display name over mono desc. A ``glyph``/``kind`` still resolves,
    but as a CORNER ANNOTATION in the card's top-right: it never opens a left
    identity column and never indents a value line (that would make it
    card+glyph again), and an unresolved mark costs nothing (icon-or-nothing
    stays total). The hero register stacks the same two slots as an identity
    ROW (mark + mono id) over a centered display block — the crown."""
    TEXT = "text"
    """A containerless typographic block (hub-panel-02-orchestrator):
    containers earn their existence — a satellite carrying enough text to be
    its own shape drops the box entirely; the type IS the node. Name +
    authored desc lines, start-anchored; the block's bbox still anchors
    connectors and collision."""


class EdgeMotion(StrEnum):
    """Kit motion dress for a wire: the marching dash, a particle rider, or the
    beam — a gradient-window comet that animates ONLY the gradient's coordinates
    (animateTransform on gradientTransform, transform-class CIM; geometry never
    moves). The beam declares performance="paint-ok" and degrades to particle on
    composite-only surfaces via the fallback ladder. Its identity is a fixed
    blue/purple, held across every variant (not genome-derived)."""

    DASH = "dash"
    PARTICLE = "particle"
    BEAM = "beam"


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
    health: NodeHealth = Field(
        default=NodeHealth.OK,
        description=(
            "Dependency-audit health channel ('ok' | 'outdated' | 'vulnerable') — a card-corner "
            "status dot, state-palette colored, orthogonal to identity accent. 'ok' renders no dot."
        ),
    )
    glyph: str = Field(default="", description="Glyph registry id (data/registries/glyphs.json) for the identity slot")
    kind: str = Field(
        default="",
        description=(
            "Semantic kind slug (database, queue, server, ...) resolving a CORE glyph "
            "(data/registries/glyphs-core.json) when no brand glyph resolves. The identity-slot "
            "ladder is brand -> kind -> nothing (icon-or-nothing law)."
        ),
    )
    glyph_tint: GlyphTint | None = Field(
        default=None,
        description="Per-slot tint override (ink | brand | full); None defers to spec then genome per-frame default",
    )
    style: NodeStyle | None = Field(
        default=None, description="Per-node anatomy override; None defers to spec then chassis default"
    )
    short: str = Field(default="", description="Mono text inside a glyph-circle when no glyph is set (e.g. 'hw')")
    note: str = Field(default="", description="Payload/markdown-only detail; never rendered in the SVG")
    category: str = Field(
        default="", description="Lanes band assignment — every lanes node declares one; illegal off-lanes"
    )
    morphology: str = Field(
        default="",
        description=(
            "Lanes category-by-SHAPE archetype slug (obi-engine: filled disc / open ring / diamond / "
            "square, never hue or icon) — resolves to a mark shape via the idiom registry's ordered shape "
            "cycle, first-appearance order. Empty defers to the node's lane ``category`` (one shape per "
            "band); a preset opts into finer within-band distinction by declaring it per node. Lanes-only."
        ),
    )
    rank: int | None = Field(
        default=None, ge=0, description="DAG rank override (ordinal); contradiction with edges raises. Dag-only"
    )
    hub: bool = Field(
        default=False,
        description=(
            "Lanes convergence-hub accent (the obi-engine specimen: obix + model-router carry the ONE "
            "accent — a signal-stroked card border and mark ring at NORMAL card size; "
            "role: hero is wrong here, it enlarges the voice). Lanes-only."
        ),
    )
    terminal: bool = Field(
        default=False,
        description=(
            "Terminal double-ring aspect (agent-task-lifecycle's done): a hairline "
            "accent ring floats 6px outside the card — the machine's final state. "
            "An aspect (a mark), never a second card. State-machine only."
        ),
    )
    gather: bool = Field(
        default=False,
        description=(
            "This node AGGREGATES its fan: >=2 converging or departing edges collapse to ONE "
            "mouth — the knot + trunk on dag (the AND-join), the launch mouth on the upward "
            "fan, the arrival mouth on the bilateral hub, the boundary point on the axial "
            "hub. Authored meaning, one vocabulary system-wide — a plain fan (bottleneck, "
            "shared dependency, port row) lands per-edge; geometry cannot tell the two apart."
        ),
    )
    anchor: str = Field(
        default="",
        description=(
            "Hub compass escape hatch (N|NE|E|SE|S|SW|W|NW) for a non-hero hub node; "
            "legal only on hub. Prefer role/zone — anchor is the last resort"
        ),
    )
    chips: tuple[str, ...] = Field(
        default=(),
        description=(
            "Chip-row: inline pills rendered inside the card beneath the desc (the hub read-card's "
            "extract/verify/diff/query row). Chrome vocabulary — legal on every topology."
        ),
    )
    embed_dims: tuple[float, float] | None = Field(
        default=None,
        exclude=True,
        description=(
            "INTERNAL (resolver-stamped, never serialized): the embedded inner artifact's "
            "DISPLAY dimensions after the embed.max_w scale — the card solver reserves this "
            "box; the template stamps the nested svg into it."
        ),
    )
    embed: DiagramSpec | None = Field(
        default=None,
        description=(
            "§12.1 nested composition: a full inner DiagramSpec composed chrome:bare into this "
            "container's content box. The inner artifact is a complete lawful artifact (laws "
            "recurse); OUTER edges target the container only — referencing an inner id is the "
            "cross-boundary-edge error. Depth caps at 2 (a container's containers hold no embeds)."
        ),
    )


class DiagramEdge(FrozenModel):
    """One directed edge. For the closed topologies this is an optional
    overlay on the derived structure; for sequence/dag/state-machine it IS
    the content (ordered for sequence)."""

    source: str = Field(description="Source node id (also accepts 'from' as an input alias)")
    target: str = Field(description="Target node id (also accepts 'to' as an input alias)")
    label: str = Field(
        default="",
        description=(
            "Edge label. Rendered on every topology by the annotation chrome "
            "pass (subsumed into a placement, anti-collision applied); also "
            "reaches the payload and markdown shadow"
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
    role: Literal["", "in", "out", "read", "edit"] = Field(
        default="", description="Hub spoke role; maps to a default zone (in→W, out→E, read→S). Hub-only"
    )
    zone: Literal["", "N", "NE", "E", "SE", "S", "SW", "W", "NW"] = Field(
        default="", description="Hub spoke sector override (compass token). Hub-only; excludes angle"
    )
    angle: float | None = Field(
        default=None, description="Hub spoke exact angle in degrees (0=E, 90=S). Hub-only; excludes zone"
    )
    route: Literal["", "bus", "around"] = Field(
        default="",
        description="Lanes routing: bus (gutter-adjacent) | around (perimeter long-haul). Lanes-only",
    )
    exit: Literal["", "top", "bottom", "left", "right"] = Field(
        default="", description="Explicit connector exit side (routing_overridable topologies only)"
    )
    entry: Literal["", "top", "bottom", "left", "right"] = Field(
        default="",
        description=(
            "Explicit connector entry side on the TARGET (routing_overridable topologies only). "
            "Independent of exit — a skip edge may leave one face and land on a different one "
            "(model-gateway's telemetry exits south/enters south; gateway-balanced's exits "
            "south/enters west)."
        ),
    )
    routing: Literal["", "straight", "orthogonal", "curved"] = Field(
        default="", description="Explicit connector routing style (routing_overridable topologies only)"
    )
    label_style: Literal["", "chip"] = Field(
        default="",
        description=(
            "Edge label dress: '' renders bare text beside the wire; 'chip' renders the "
            "Edge-chip — a pill riding ON the wire at its midpoint (idiom registry box tier)."
        ),
    )
    relation: Literal["", "assert", "drift", "flow", "bypass"] = Field(
        default="",
        description=(
            "Line IDIOM (sec 3): what this edge MEANS — assert (causes/writes), drift (passive/read), "
            "flow (data in motion), bypass (privileged exception path). Binds the registry's default "
            "dress (texture + terminal + motion + route); explicit per-edge fields override channels. "
            "Distinct key from edge_motion — relation:flow names meaning, edge-motion:flow names dress."
        ),
    )
    marker: Literal["", "none", "arrow", "dot"] = Field(
        default="", description="Per-edge end marker; overrides spec.marker then genome direction_device"
    )
    pieces: tuple[int, ...] = Field(
        default=(),
        description="kit piece ids this edge composes (grammar-inventory 1-8): "
        "payload vocabulary — echoed into hw:payload so an agent reads the "
        "declared grammar; dress derives from relation/kind, not from this",
    )

    @model_validator(mode="before")
    @classmethod
    def _canonicalize_endpoint_aliases(cls, data: object) -> object:
        """``from``/``to`` are accepted input aliases for ``source``/``target``
        — every LLM's Mermaid-shaped prior writes edges this way. Canonicalize
        here so the canonical names stay ``source``/``target`` everywhere
        downstream (payloads, docs, Field descriptions); a caller declaring
        both an alias and the canonical name with conflicting values is a
        caller error, not a silent pick."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "from" in data:
            frm = data.pop("from")
            if "source" in data and data["source"] != frm:
                raise ValueError(f"edge sets both 'from'={frm!r} and 'source'={data['source']!r} with different values")
            data["source"] = frm
        if "to" in data:
            to = data.pop("to")
            if "target" in data and data["target"] != to:
                raise ValueError(f"edge sets both 'to'={to!r} and 'target'={data['target']!r} with different values")
            data["target"] = to
        return data


class DiagramRegion(FrozenModel):
    """An authored compound made visible: a region binding member nodes,
    labeled in uppercase. The common-region Gestalt piece — grouping, never a
    hue. Two treatments: ``enclosure`` is a concentric hairline box with a
    bottom-strip label (agent-task-lifecycle's RECOVERY); ``band`` is a FILLED
    panel with a small top-left count-voice label that also reserves the
    over-arc space above the row (agent-runtime's AGENT RUNTIME control-loop
    frame, gateway-balanced's MODEL POOL)."""

    label: str = Field(min_length=1, description="Region name (renders uppercase, letter-spaced)")
    members: list[str] = Field(min_length=1, description="Node ids the enclosure binds")
    kind: Literal["enclosure", "band"] = Field(
        default="enclosure",
        description="enclosure = concentric hairline + bottom label; band = filled panel + top-left cnt label",
    )


class DiagramLayoutPins(FrozenModel):
    """Authored row-order pins — figure continuity across edits.

    A reader keeps a mental map of a diagram between renders; a fresh
    crossing-minimum solve does not. ``transform`` writes the parent's
    rendered order here so survivors keep their rows and insertions seat at
    their rank's extent, never interleaved into the authored run. The dag
    solver consumes it in place of the barycenter sweep; every other
    topology ignores it (their placement has no rank grid to pin)."""

    rank_orders: tuple[tuple[str, ...], ...] = Field(
        default=(),
        description=(
            "Per-rank node ids in vertical order, leftmost rank first. Pins "
            "carry ORDER only — a patched graph may shift a node's column, so "
            "ranks re-derive at solve time and pinned ids keep their relative "
            "order within whatever rank they land in. Ids must name spec "
            "nodes; a node absent here appends after the pinned run."
        ),
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
    node_anatomy: Literal["", "head", "row"] = Field(
        default="",
        description="card LAYOUT override: 'head' = stacked portrait column, "
        "'row' = the label-row card — overrides the topology chassis default "
        "(rag-pipeline opts into 'head' on the label-row pipeline chassis; "
        "artifact-roundtrip/gateway keep 'row')",
    )
    regions: tuple[DiagramRegion, ...] = Field(
        default=(), description="Authored compound enclosures (state-machine: the recovery region idiom)"
    )
    zones: tuple[str, ...] = Field(
        default=(),
        max_length=2,
        description=(
            "Zone headers — the small-caps tracked labels naming the composition's "
            "structural sides (specimens' -zone runs). One renders top-left of the "
            "content; a second renders top-right (source/destination split). Authored, "
            "never inferred."
        ),
    )
    partition_chroma: Literal["", "zone"] = Field(
        default="",
        description=(
            "Partition-pair chromatics: 'zone' compiles the accent PAIR from the declared "
            "binary zone partition — every member of zone 0 takes the ink tone, every member "
            "of zone 1 takes the signal tone, across its label, its corner mark and its wire. "
            "ONE hue per group, never per node (the group-membership law gaining a two-group "
            "clause); spends one figure against figure_budget. Requires exactly two zones — "
            "declaring it with fewer raises rather than silently no-opping. Empty (default) "
            "leaves hue to the spine binding alone."
        ),
    )
    chassis: dict[str, Any] = Field(
        default_factory=dict,
        description="shallow chassis overrides for THIS spec (design dims, "
        "never coordinates): node/hero/node2 sub-dicts plus scalar fields "
        "(card_min_w, hero_min_w, gap, pitch...). Merged onto the topology "
        "chassis at solve time; the parity presets use it where prototypes "
        "of one topology disagree on card proportions.",
    )
    figure_budget: int = Field(
        default=3,
        ge=1,
        le=5,
        description="figure grammar: how many emphasized figures the reader "
        "should count (~3 — hero + privileged edge + contrast). Recorded in "
        "the payload; the accent binder already spends at most one accent "
        "role, so today this is a declared intent the harness can audit.",
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
    connector_palette: Literal["", "muted", "colored"] = Field(
        default="",
        description=(
            "Connector-hue knob. '' (default) and 'muted' draw static/dash wires "
            "in the genome's quiet neutral (diagram_conn_muted); 'colored' opts "
            "back into the genome's colored flow palette. beam/flow edges keep the "
            "colored flow under muted (their identity is the hue) — an explicit "
            "'muted' request keeps every kit motion quiet (the hue-carrying "
            "colored; the default stays silent. Additive; excluded from the "
            "payload by default (exclude_defaults)."
        ),
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
    layout: DiagramLayoutPins | None = Field(
        default=None,
        description=(
            "Row-order pins written by `transform` (see DiagramLayoutPins). "
            "None — the default, dropped from the payload dump — leaves "
            "ordering to the solver, so fresh artifacts stay byte-identical; "
            "once populated it rides inside the hashed payload like lineage."
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
    annotations: list[DiagramAnnotation] = Field(
        default_factory=list,
        description="Caller-declared overlay chrome (callouts, legends, badges, pins); each anchors to one target",
    )
    marker: Literal["", "none", "arrow", "dot"] = Field(
        default="",
        description=(
            "Artifact-default terminal marker (the D5 'terminal' chrome knob); per-edge marker wins, "
            "then this, then the relation dress, then the per-topology default (engine wire_defaults), "
            "then genome direction_device. 'dot' is the drift relation's terminal (on-terminus)."
        ),
    )
    chrome: Literal["", "caption", "plain"] = Field(
        default="",
        description=(
            "The composition's own chrome mode: 'plain' keeps the full plate but drops the caption "
            "line (the lanes hand sheet renders captionless); 'caption' is the kit default. Empty "
            "defers to the compose-level chrome (which alone may say 'bare' — embed plumbing, never "
            "a composition fact)."
        ),
    )
    wire: Literal["", "solid", "dashed"] = Field(
        default="",
        description=(
            "Static-wire grammar (the D5 chrome knob): 'solid' renders hairline rails (dash stays "
            "reserved for semantic edges — returns, bypasses, muted roles); 'dashed' keeps the dashed "
            "track. Empty defers to the per-topology default: flow topologies (lanes, sequence, dag, "
            "state-machine) read solid + terminal arrows; radial topologies stay dashed markerless."
        ),
    )
    hero_ring: Literal["", "quiet"] = Field(
        default="",
        description=(
            "role:hero ring dress (2026-07-13 ruling, v04/decisions/diagram-law-enrollment-audit.md): "
            "empty (default) rings the hero card/circle in the genome accent (stroke var(--dna-signal), "
            "the pp corpus's own hero dress); 'quiet' opts back into the flat family border for a spec "
            "whose OWN specimen shows a neutral hero — the opt-out is data honoring its source, not a "
            "taste knob. The ring spends one figure against figure_budget like any other emphasized figure."
        ),
    )
    lanes: tuple[str, ...] = Field(
        default=(),
        description=(
            "Lanes topology: DECLARED category order. When set, band order follows this list (not node "
            "first-appearance), every node category must be a member, and an unpopulated entry renders "
            "as an EMPTY lane (the empty-lane knob). Empty tuple defers to first-appearance order."
        ),
    )
    hub_policy: Literal["", "compass", "axial"] = Field(
        default="",
        description=(
            "Hub placement policy (§1.2): 'compass' fans spokes into radial sectors on canonical "
            "slots; 'axial' places the hero on a spine with roles mapped to axes (edit/N, read/S, "
            "compose-in/W) and the destination family curving into the E half-plane via a gather. "
            "Empty defers: axial when the spec carries half-plane semantics (edge roles), compass "
            "for pure radial fans."
        ),
    )
    spine: tuple[str, ...] = Field(
        default=(),
        description=(
            "Semantic Chromatics (the color analogue to CIM): the ORDERED node ids of the main "
            "sequence the reader should trace first. The engine binds ONE accent to the spine — its "
            "edges, its members' titles, and the nucleus role — and holds everything else neutral, so "
            "hue encodes MEMBERSHIP not identity. Empty = the engine infers the spine from the "
            "partition (the hero's primary out-family, else the longest main sequence). The agent picks "
            "WHAT matters (this relation); the engine derives WHAT color. Raw per-element hue is never "
            "an input — significance is expressed by role/spine, color is always derived."
        ),
    )
    axial: dict[str, float] | None = Field(
        default=None,
        description=(
            "Per-spec axial-cross geometry overrides (prominence_factor, hero_aspect, satellite_min_w/h, "
            "fan_pitch/reach, axis_gap, ...) merged over data/config/diagram-frame.yaml:axial. The axial "
            "family shares one frame config, but sibling specimens tune the nucleus prominence and "
            "satellite width — axial's 1.6x prominence / 236-wide satellites vs hub's "
            "2.4x / ~220. Config remains data; this is a per-artifact tuning of it, not new geometry."
        ),
    )
    caps: dict[str, int] | None = Field(
        default=None,
        description=(
            "Per-spec capacity-cap overrides (e.g. sm_max_below_baseline for a wide tool pool) merged "
            "over data/config/diagram-frame.yaml:caps. Caps stay data; a specimen with an honestly wider "
            "rank lifts its OWN cap without loosening the frame default for every diagram."
        ),
    )
    distribution: Literal["", "even", "golden", "balanced", "crossing-minimized"] = Field(
        default="",
        description=(
            "Hub spoke distribution policy; accepted for schema stability, but placement quantizes to "
            "canonical compass slots under every policy (crossing-minimized member ordering preserved)"
        ),
    )
    surface: SurfaceSpec | None = Field(
        default=None,
        description=(
            "Surface mode (plate/inlay/twin) this projection renders on. Additive "
            "and None by default, so `exclude_defaults` keeps pre-existing payloads "
            "byte-identical; a non-plate surface serializes into the payload and "
            "gives plate/inlay/twin (and each twin face) distinct content addresses."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _refuse_retired_topologies(cls, data: object) -> object:
        """A retired flat topology word refuses TEACHING its family x
        expression spelling (``RETIRED_TOPOLOGIES``) — the consolidation's
        hard break, never an alias that silently lifts."""
        if isinstance(data, dict):
            raw = data.get("topology")
            if isinstance(raw, str) and raw in RETIRED_TOPOLOGIES:
                raise ValueError(f"topology {raw!r} was consolidated into its family — use {RETIRED_TOPOLOGIES[raw]}")
        return data

    @model_validator(mode="before")
    @classmethod
    def _autofill_node_ids(cls, data: object) -> object:
        """Empty/missing node ids fill ``n{i}`` (index-positional) before the
        after-validator runs, so a spec with id-less nodes and edges
        referencing ``n0``/``n1`` (the promised auto-id contract on
        ``DiagramNode.id``) validates instead of failing with an
        unknown-node-reference error. Matches ``resolve_auto_roles``' exact
        scheme (compose/diagram/input.py) — that normalization pass becomes a
        harmless no-op once ids are already filled here. Declared ids pass
        through untouched; a declared id that collides with an autofill
        target is caught downstream by ``_validate_shape``'s duplicate-id
        check, same as two declared ids colliding with each other."""
        if not isinstance(data, dict):
            return data
        nodes = data.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            return data
        new_nodes: list[Any] = []
        changed = False
        for i, node in enumerate(nodes):
            if isinstance(node, dict):
                if not node.get("id"):
                    node = {**node, "id": f"n{i}"}
                    changed = True
            elif isinstance(node, DiagramNode) and not node.id:
                node = node.model_copy(update={"id": f"n{i}"})
                changed = True
            new_nodes.append(node)
        if not changed:
            return data
        return {**data, "nodes": new_nodes}

    @model_validator(mode="after")
    def _validate_shape(self) -> DiagramSpec:
        """Structural grammar only — caps/legality/depth policy live in YAML."""
        declared = [n.id for n in self.nodes if n.id]
        if len(set(declared)) != len(declared):
            raise ValueError(f"diagram node ids must be unique, got {declared}")
        heroes = [i for i, n in enumerate(self.nodes) if n.role is NodeRole.HERO]
        if len(heroes) > 1:
            raise ValueError(f"at most one hero node (got nodes {heroes})")
        focal = focal_slot(self.topology, len(self.nodes), self.orientation)
        for i, n in enumerate(self.nodes):
            if n.role is NodeRole.MUTED and focal is not None and i == focal:
                raise ValueError(
                    f"node {i} ({n.label!r}) is the {self.topology.value}'s focus "
                    "(the first node declared) and cannot be muted"
                )
        if self.edges:
            self._validate_edges(declared)
        elif self.topology in _EDGES_REQUIRED:
            raise ValueError(f"{self.topology.value} is a data topology: edges are the content and are required")
        for n in self.nodes:
            style = n.style.value if n.style is not None else (self.node_style.value if self.node_style else "")
            if style != NodeStyle.CARD_LABEL.value:
                continue
            # card+label's slots are the label kicker and the value stack —
            # it hosts no chip row and no nested artifact. Silently dropping
            # authored content is the unsafe outcome; say so instead.
            if n.chips:
                raise ValueError(
                    f"node {n.id or n.label!r} declares chips on a card+label, which has no chip row "
                    "(its slots are the label and the value stack) — put the chip text in the value "
                    "stack, or use style: card"
                )
            if n.embed is not None:
                raise ValueError(
                    f"node {n.id or n.label!r} embeds an artifact in a card+label, which reserves no "
                    "embed box — use style: card for a container node"
                )
        if self.partition_chroma:
            if len(self.zones) != 2:
                raise ValueError(
                    f"partition_chroma: {self.partition_chroma!r} compiles hue from a BINARY zone "
                    f"partition, but this spec declares {len(self.zones)} zone(s) — declare both "
                    "zone headers (the two groups the hue names) or drop partition_chroma"
                )
            if layout_slug(self) not in _PARTITIONED_LAYOUTS:
                raise ValueError(
                    f"partition_chroma is legal on {sorted(_PARTITIONED_LAYOUTS)} — the layouts that "
                    f"SEAT their members in two structural groups; {layout_slug(self)!r} has no such "
                    "split, so a hue compiled from it would name nothing the reader can see"
                )
            self._validate_partition_seats()
        self._validate_rank_field()
        self._validate_embeds()
        self._validate_hub_structure(declared)
        self._validate_lanes_structure()
        self._validate_annotations(declared)
        return self

    def _validate_partition_seats(self) -> None:
        """A hub compiles a partition hue only when its SEATS actually split
        east/west. The bilateral fan's split is structural — its solver seats
        two columns — but a compass hub seats wherever the author points it: a
        N/E/S/W cross has no two sides, and painting half of it would assert a
        grouping the geometry never draws. So the seat declarations must agree
        with the declaration-order halves the hue compiles from."""
        if self.topology is not Topology.HUB:
            return
        groups = partition_groups(self)
        sides: dict[int, set[str]] = {0: set(), 1: set()}
        for i, node in enumerate(self.nodes):
            if groups[i] < 0:
                continue
            side = _seat_side(self, i, node)
            if side == "":
                raise ValueError(
                    f"partition_chroma on a hub needs every member's SEAT declared so the two groups "
                    f"can be checked against the geometry — node {node.id or node.label!r} declares "
                    "none (give it an edge angle/zone or a node anchor)"
                )
            sides[groups[i]].add(side)
        if sides[0] & sides[1] or any(len(s) != 1 for s in sides.values()):
            raise ValueError(
                f"partition_chroma compiles hue from the two declaration-order halves, but this hub's "
                f"seats do not split that way (first half seats {sorted(sides[0])}, second "
                f"{sorted(sides[1])}) — reorder the nodes so each group sits on one side, or drop "
                "partition_chroma"
            )

    def _validate_embeds(self) -> None:
        """§12.1 depth policy: an artifact may hold containers (depth 1)
        whose inner artifacts may hold containers (depth 2); a depth-2
        inner node holding an embed refuses — split the diagram instead.
        Inner specs self-validate recursively by construction (they ARE
        DiagramSpecs), so the laws recurse for free."""
        for n in self.nodes:
            if n.embed is None:
                continue
            for inner in n.embed.nodes:
                if inner.embed is None:
                    continue
                for deepest in inner.embed.nodes:
                    if deepest.embed is not None:
                        raise ValueError(
                            f"nesting-depth: container {n.id or n.label!r} exceeds depth 2 "
                            f"(node {deepest.id or deepest.label!r} still embeds) — split the diagram"
                        )

    def _validate_edges(self, declared: list[str]) -> None:
        ids = set(declared)
        inner_ids = {inner.id for n in self.nodes if n.embed is not None for inner in n.embed.nodes if inner.id}
        seen: set[tuple[str, str]] = set()
        for e in self.edges:
            for ref in (e.source, e.target):
                if ref not in ids:
                    if ref in inner_ids:
                        # §12.1 cross-boundary-edge: an embedded artifact is a
                        # sealed unit — outer edges target its CONTAINER.
                        raise ValueError(
                            f"cross-boundary-edge: {ref!r} lives inside an embedded diagram — "
                            "edges target containers only (address the container node's id)"
                        )
                    raise ValueError(f"edge references unknown node id {ref!r} (declared: {sorted(ids)})")
            if e.source == e.target:
                # Self-loops are the state/step revisiting itself — legal on
                # the data topologies (state-machine, dag, hub, lanes,
                # sequence) where an edge is content. On the closed
                # topologies the node ORDER is the structure and a self-loop
                # has no derived-pair meaning, so it stays illegal there. A
                # bidirectional self-loop is nonsense in either case.
                if self.topology not in _EDGES_REQUIRED:
                    raise ValueError(
                        f"self-loop {e.source!r}->{e.source!r} is not representable on "
                        f"{self.topology.value} (split the node, or use a data topology)"
                    )
                if e.direction == "both":
                    raise ValueError(f"self-loop {e.source!r}->{e.source!r} cannot be bidirectional")
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
            # A bypass relation (L4 — exception/privileged path, artifact-roundtrip's
            # transform -> artifact' loop) may ADD one pair beyond the closed
            # topology's derived structure — node order still owns the plain
            # chain (every derived pair must still be present), the bypass is
            # the one declared exception allowed to ride on top of it. A
            # bypass dressing an ORDINARY derived pair (the common case: style
            # one existing edge as an exception) is unaffected either way.
            bypass_pairs = {frozenset((index[e.source], index[e.target])) for e in self.edges if e.relation == "bypass"}
            missing = derived - explicit
            extra = (explicit - derived) - bypass_pairs
            if missing or extra:
                raise ValueError(
                    f"explicit edges on a closed topology must cover the derived "
                    f"{self.topology.value} pair set exactly (as undirected pairs, a "
                    f"bypass-relation edge may add one exception); got "
                    f"{sorted(tuple(sorted(p)) for p in explicit)}, "
                    f"expected {sorted(tuple(sorted(p)) for p in derived)}"
                )
        # NOTE: the DAG cycle check is NOT a hard-raise here. A frozen model
        # cannot re-dispatch itself to a different topology, and a cyclic DAG
        # is the auto-promotion trigger (compose/diagram/input.py:
        # promote_cyclic_dag → state-machine + warning). The solver keeps a
        # defensive cyclic re-check. ``_find_cycle`` stays exported for both.
        if self.topology is Topology.TREE:
            _validate_tree_shape(len(self.nodes), directed)
        if self.topology is Topology.SEQUENCE:
            # Every node participating in messages must be a declared lifeline;
            # already guaranteed by the id check. Order is the given edge order.
            pass

    def _validate_rank_field(self) -> None:
        """``node.rank`` (the DAG rank override) is legal on dag only."""
        if self.topology is Topology.DAG:
            return
        for i, n in enumerate(self.nodes):
            if n.rank is not None:
                raise ValueError(
                    f"node {i} ({n.label!r}) sets rank={n.rank}, but rank overrides are dag-only "
                    f"(topology is {self.topology.value})"
                )

    def _validate_hub_structure(self, declared: list[str]) -> None:
        """Hub incidence + spoke-key exclusivity; off-hub role/zone/angle illegal.

        On hub, node 0 is the focal hub and every edge is incident to it.
        Per-edge at most one of {zone, angle}; ``role``/``zone``/``angle`` are
        hub-only; ``node.anchor`` is legal only on a hub NON-hero node.
        """
        if self.topology is not Topology.HUB:
            # role/zone/angle and node.anchor are hub grammar; reject off-hub.
            for e in self.edges:
                if e.role or e.zone or e.angle is not None:
                    raise ValueError(
                        f"edge {e.source!r}->{e.target!r} sets a hub spoke key (role/zone/angle) "
                        f"but topology is {self.topology.value} (hub-only)"
                    )
            for i, n in enumerate(self.nodes):
                if n.anchor:
                    raise ValueError(
                        f"node {i} ({n.label!r}) sets anchor={n.anchor!r}, but the compass anchor is hub-only "
                        f"(topology is {self.topology.value})"
                    )
            return
        hub_id = self.nodes[0].id or "n0"
        index = {(nid or f"n{i}"): i for i, nid in enumerate(n.id for n in self.nodes)}
        for e in self.edges:
            if hub_id not in (e.source, e.target):
                raise ValueError(
                    f"hub edge {e.source!r}->{e.target!r} is not incident to the hub node {hub_id!r} "
                    "(the hub is the first node declared) — a satellite-to-satellite relation needs "
                    "a free-graph topology: recompose with topology dag or lanes"
                )
            if e.zone and e.angle is not None:
                raise ValueError(
                    f"hub edge {e.source!r}->{e.target!r} sets both zone and angle (at most one spoke override)"
                )
        for i, n in enumerate(self.nodes):
            if n.anchor and index.get(n.id or f"n{i}") == 0:
                raise ValueError(f"the hub node ({n.label!r}) cannot carry a compass anchor (it is the center)")

    def _validate_lanes_structure(self) -> None:
        """Lanes: every node declares a category; ``route``, declared
        ``lanes``, and node ``morphology`` are lanes-only; declared lanes
        must cover node categories."""
        if self.topology is not Topology.LANES:
            for e in self.edges:
                if e.route:
                    raise ValueError(
                        f"edge {e.source!r}->{e.target!r} sets route={e.route!r}, but lane routing is lanes-only "
                        f"(topology is {self.topology.value})"
                    )
            if self.lanes:
                raise ValueError(
                    f"'lanes' declares category order, which is lanes-only (topology is {self.topology.value})"
                )
            for i, n in enumerate(self.nodes):
                if n.morphology:
                    raise ValueError(
                        f"node {i} ({n.label!r}) sets morphology={n.morphology!r}, but the category-by-shape axis "
                        f"is lanes-only (topology is {self.topology.value})"
                    )
            return
        for i, n in enumerate(self.nodes):
            if not n.category:
                raise ValueError(f"lanes node {i} ({n.label!r}) must declare a non-empty category")
        if self.lanes:
            if len(set(self.lanes)) != len(self.lanes):
                raise ValueError("declared 'lanes' contains a duplicate category")
            declared_lanes = set(self.lanes)
            for i, n in enumerate(self.nodes):
                if n.category not in declared_lanes:
                    raise ValueError(
                        f"lanes node {i} ({n.label!r}) has category {n.category!r} not in the declared "
                        f"'lanes' order {list(self.lanes)}"
                    )

    def _validate_annotations(self, declared: list[str]) -> None:
        """Referential checks for annotation anchors (arity/kind live on the
        annotation model). A node ref must be a declared id; an edge ref must
        parse, both endpoints must be declared, and its ordinal must not
        exceed the occurrence count of that directed pair. Region/at anchors
        pass structurally — region names resolve at solve time."""
        if not self.annotations:
            return
        ids = set(declared)
        pair_counts: dict[tuple[str, str], int] = {}
        for e in self.edges:
            pair_counts[e.source, e.target] = pair_counts.get((e.source, e.target), 0) + 1
        for ann in self.annotations:
            if ann.node:
                if ann.node not in ids:
                    raise ValueError(
                        f"annotation {ann.text!r} anchors to unknown node id {ann.node!r} (declared: {sorted(ids)})"
                    )
            elif ann.edge:
                try:
                    src, dst, ordinal = parse_edge_ref(ann.edge)
                except ValueError as exc:
                    raise ValueError(f"annotation {ann.text!r} has a bad edge anchor: {exc}") from exc
                for ref in (src, dst):
                    if ref not in ids:
                        raise ValueError(f"annotation {ann.text!r} edge anchor references unknown node id {ref!r}")
                occurrences = pair_counts.get((src, dst), 0)
                if occurrences == 0:
                    raise ValueError(
                        f"annotation {ann.text!r} anchors to edge {src!r}->{dst!r}, which is not a declared edge"
                    )
                if ordinal > occurrences:
                    raise ValueError(
                        f"annotation {ann.text!r} edge ordinal #{ordinal} exceeds the "
                        f"{occurrences} occurrence(s) of {src!r}->{dst!r}"
                    )


# ── Structural constants ────────────────────────────────────────────────────

_CLOSED_TOPOLOGIES = frozenset(
    {
        Topology.PIPELINE,
        Topology.FANOUT,
        Topology.FANIN,
        # Both cycle expressions derive the loop; declared edges must cover
        # the derived structure the same way (the gap once let a ring spec
        # declare a partial cycle unvalidated).
        Topology.CYCLE,
        Topology.TREE,
        Topology.COMPARISON,
    }
)

_EDGES_REQUIRED = frozenset({Topology.SEQUENCE, Topology.DAG, Topology.STATE_MACHINE, Topology.HUB, Topology.LANES})

_PARTITIONED_LAYOUTS = frozenset({"fanout-bilateral", "hub"})
"""Layouts that CAN seat members in two structural groups, so a hue compiled
from the partition names something the reader can already see. The bilateral
fan splits its destinations left/right about the source unconditionally; a hub
splits only when its seats say so, which ``_validate_partition_seats`` checks
per spec (a N/E/S/W compass cross has no two sides). Every other layout seats
one undivided family, and painting half of it would assert a grouping the
geometry does not draw. Widening this set is a per-layout ruling with its own
specimen, never a default."""

_EAST_SEATS = frozenset({"E", "NE", "SE"})
_WEST_SEATS = frozenset({"W", "NW", "SW"})


def _seat_side(spec: DiagramSpec, index: int, node: DiagramNode) -> str:
    """Which SIDE a hub member is seated on — 'east', 'west', or '' when the
    declaration does not commit to one (a bare N/S cardinal, or no seat at
    all). Reads the same precedence the compass solver does: an explicit edge
    angle wins, then a node anchor, then an edge zone token."""
    incident = [e for e in spec.edges if node.id in (e.source, e.target)]
    # Precedence is the compass solver's, in ITS order: an explicit angle
    # wins outright, then the node anchor, then an edge zone. An angle that
    # commits to NEITHER side (a due-N/S seat, cos == 0) is a decided answer
    # of "no side" — it must NOT fall through to an anchor, or a spec seated
    # north/south passes as an east/west partition on a stale anchor.
    for edge in incident:
        if edge.angle is not None:
            cos = math.cos(math.radians(edge.angle))
            return "east" if cos > 1e-6 else "west" if cos < -1e-6 else ""
    if node.anchor in _EAST_SEATS:
        return "east"
    if node.anchor in _WEST_SEATS:
        return "west"
    if node.anchor:
        return ""  # a declared N/S anchor is likewise a decided "no side"
    for edge in incident:
        if edge.zone in _EAST_SEATS:
            return "east"
        if edge.zone in _WEST_SEATS:
            return "west"
    return ""


def focal_slot(topology: Topology, n: int, orientation: Orientation = Orientation.HORIZONTAL) -> int | None:
    """The structural focal index AUTO resolves to HERO, or None.

    A horizontal pipeline, the cycle family, sequence, dag, state-machine,
    and lanes have no structural focal slot — their hero is caller
    rhetoric. Hub has one: the center node (slot 0); the vertical pipeline
    (the operator stack) crowns its top result (slot 0); fanin's mouth is
    the last node.
    """
    if (
        topology is Topology.FANOUT
        or topology is Topology.TREE
        or topology is Topology.HUB
        or (topology is Topology.PIPELINE and orientation is Orientation.VERTICAL)
    ):
        return 0
    if topology is Topology.FANIN:
        return n - 1
    if topology is Topology.COMPARISON:
        return 1
    return None


def layout_slug(spec: DiagramSpec) -> str:
    """The concrete layout algorithm slug — also ``data-hw-subvariant``.

    Family word alone where the family has one cell; ``family-expression``
    where the ``orientation`` axis selects one (fanout's five, pipeline's
    vertical stack, cycle's orbit/ring, tree's radial).
    """
    if spec.topology is Topology.FANOUT:
        return f"fanout-{spec.orientation.value}"
    if spec.topology is Topology.CYCLE:
        return f"cycle-{spec.orientation.value}"
    if spec.topology is Topology.PIPELINE and spec.orientation is Orientation.VERTICAL:
        return "pipeline-vertical"
    if spec.topology is Topology.TREE and spec.orientation is Orientation.RADIAL:
        return "tree-radial"
    return spec.topology.value


def partition_groups(spec: DiagramSpec) -> tuple[int, ...]:
    """Binary-partition membership per node index: ``0`` for the first zone's
    group, ``1`` for the second's, ``-1`` for a node in neither (the focal
    source — it is what the partition divides, never a member of it). All
    ``-1`` when the spec declares no ``partition_chroma``.

    Membership is DECLARATION ORDER, which is the identical fact the bilateral
    fan solver seats on (``fan.py``: ``left_n = k // 2``, spec order fills left
    first), so hue and geometry can never disagree about which side a node is
    on. One derivation, read by the node binder, the edge binder, and the
    label pass alike — a group decides once and three channels follow."""
    if not spec.partition_chroma:
        return tuple(-1 for _ in spec.nodes)
    members = len(spec.nodes) - 1
    first = members // 2
    return tuple(-1 if i == 0 else (0 if (i - 1) < first else 1) for i in range(len(spec.nodes)))


def derive_edges(spec: DiagramSpec) -> tuple[tuple[int, int], ...]:
    """Canonical derived structure for the closed topologies (index pairs).

    pipeline: reading-order chain — or RISING when vertical (the operator
    stack: nodes[0] is the top result; particles climb bottom -> top).
    fanout: nodes[0] -> each. fanin: each -> nodes[-1]. cycle: the loop —
    orbit cycles the non-hero ring (a hero is the center axis, lifted out
    of the ring); ring cycles every node. tree: nodes[0] -> each (depth-1
    star; multi-level trees declare explicit edges). comparison: the single
    before -> after pair.
    """
    n = len(spec.nodes)
    t = spec.topology
    if t is Topology.PIPELINE:
        if spec.orientation is Orientation.VERTICAL:
            return tuple((i + 1, i) for i in range(n - 1))
        return tuple((i, i + 1) for i in range(n - 1))
    if t is Topology.FANOUT:
        return tuple((0, j) for j in range(1, n))
    if t is Topology.FANIN:
        return tuple((j, n - 1) for j in range(n - 1))
    if t is Topology.CYCLE:
        if spec.orientation is Orientation.RING:
            return tuple((i, (i + 1) % n) for i in range(n))
        ring = [i for i, node in enumerate(spec.nodes) if node.role is not NodeRole.HERO]
        k = len(ring)
        return tuple((ring[i], ring[(i + 1) % k]) for i in range(k))
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
    marker: str = ""
    """Per-edge end marker ('' | none | arrow); the connector grammar resolves
    it against the spec default and the genome direction_device."""
    exit: str = ""
    """Explicit connector exit side ('' | top | bottom | left | right);
    honoured only on routing_overridable topologies (enforced at the seam)."""
    entry: str = ""
    """Explicit connector entry side on the TARGET ('' | top | bottom | left |
    right); independent of ``exit``, same routing_overridable gate."""
    routing: str = ""
    """Explicit routing style ('' | straight | orthogonal | curved); same
    routing_overridable gate as ``exit``."""
    role: str = ""
    """Hub spoke role ('' | in | out | read) — the hub solver's sector default
    when no zone/anchor/angle overrides it."""
    zone: str = ""
    """Hub compass sector override ('' | N..NW); loses to an explicit angle."""
    angle: float | None = None
    """Hub explicit spoke angle (degrees, 0=E clockwise); overrides the sector."""
    route: str = ""
    """Lanes routing ('' | bus | around); 'around' forces the perimeter
    channel, 'bus' is adjacent-only."""
    relation: str = ""
    label_style: str = ""
    """Line idiom ('' | assert | drift | flow | bypass) — binds the registry's
    default dress; explicit per-edge fields override channels (sec 3)."""


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
            marker=e.marker,
            exit=e.exit,
            entry=e.entry,
            routing=e.routing,
            role=e.role,
            zone=e.zone,
            angle=e.angle,
            route=e.route,
            relation=e.relation,
            label_style=e.label_style,
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
                    marker=e.marker,
                    exit=e.exit,
                    entry=e.entry,
                    routing=e.routing,
                    role=e.role,
                    zone=e.zone,
                    relation=e.relation,
                    label_style=e.label_style,
                    angle=e.angle,
                    route=e.route,
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
