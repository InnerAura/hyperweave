"""Diagram layout orchestration: caps, accents, motion wiring, dispatch.

Per-topology placement lives in linear/fan/radial/sequence/graph; this
module owns everything uniform across them — capacity/legality policy
(YAML), flow-palette index assignment, and ``wire_motion``, which turns a
solver's edge geometries into connector/particle/gradient placements under
the closed motion grammar. Solvers never see hex (accent INDICES only) and
templates never see arithmetic.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping
from dataclasses import replace as _dc_replace
from typing import Any

from hyperweave.compose.diagram import motion as mo
from hyperweave.compose.diagram.anchors import boundary_distance
from hyperweave.compose.diagram.annotate import Region as AnnRegion
from hyperweave.compose.diagram.annotate import build_annotations
from hyperweave.compose.diagram.chrome import measure_caption, voice_for
from hyperweave.compose.diagram.layered import back_edges, split_self_loops
from hyperweave.compose.diagram.recenter import content_extents, shift_content, translate_path
from hyperweave.compose.diagram.records import (
    AnnotationPlacement,
    DiagramHeader,
    DiagramLayout,
    DiagramText,
    GatherPoint,
    LaneBand,
    NodePlacement,
    OperatorMark,
    ParticlePlacement,
    RenderedMotion,
)
from hyperweave.compose.diagram.regions import MeasuredRegion, stack_regions
from hyperweave.compose.diagram.sizing import effective_diagram_cfg
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext, enrich_geos, wire_motion
from hyperweave.compose.matrix.cells import measure_voice
from hyperweave.compose.spatial_records import RectSpec
from hyperweave.core.diagram import (
    DiagramCapacityError,
    DiagramInputError,
    DiagramSpec,
    EdgeKind,
    NodeRole,
    Orientation,
    ResolvedEdge,
    Topology,
    layout_slug,
    resolved_edges,
    tree_depth,
)
from hyperweave.core.matrix import GlyphTint
from hyperweave.core.paradigm import DiagramTopologyChassis, ParadigmDiagramConfig


def enforce_caps(spec: DiagramSpec, slug: str, caps: Mapping[str, Any]) -> bool:
    """Hard caps raise; per-layout min/max raise; soft cap returns the
    shrink flag (the named gap/pitch tightens by shrink_factor)."""
    n = len(spec.nodes)
    if n > int(caps.get("hard_nodes", 20)):
        raise DiagramCapacityError(f"{n} nodes exceeds the hard cap {caps.get('hard_nodes', 20)}; split the diagram")
    band = (caps.get("layouts") or {}).get(slug) or {}
    lo, hi = int(band.get("min", 2)), int(band.get("max", 20))
    if n < lo:
        raise DiagramInputError(f"{slug} needs at least {lo} nodes (got {n})")
    if n > hi:
        raise DiagramCapacityError(f"{slug} caps at {hi} nodes (got {n}); split the diagram")
    if spec.topology is Topology.SEQUENCE and len(spec.edges) > int(caps.get("sequence_max_messages", 8)):
        raise DiagramCapacityError(
            f"sequence caps at {caps.get('sequence_max_messages', 8)} messages (got {len(spec.edges)})"
        )
    return n > int(caps.get("soft_nodes", 12))


def check_routing_overridable(spec: DiagramSpec, slug: str, engine: Mapping[str, Any]) -> None:
    """Explicit connector routing/exit is legal only on the topologies the
    engine lists in ``routing_overridable``. Elsewhere a fixed-geometry
    topology owns its connector shape, so honouring the override would be a
    lie — raise instead of silently dropping it, naming the slug and the set.
    Keyed on the resolved slug's TOPOLOGY (fanout-radial and fanout-horizontal
    share the fanout ban)."""
    overridable = {str(s) for s in (engine.get("routing_overridable") or [])}
    topo = spec.topology.value
    if topo in overridable:
        return
    for e in spec.edges:
        if e.routing or e.exit or e.entry:
            field, value = ("routing", e.routing) if e.routing else ("exit", e.exit) if e.exit else ("entry", e.entry)
            raise DiagramInputError(
                f"edge {e.source!r}->{e.target!r} sets {field}={value!r}, but connector "
                f"{field} overrides are legal only on {sorted(overridable)} "
                f"(topology is {topo})"
            )


def check_orientation(spec: DiagramSpec, engine: Mapping[str, Any]) -> None:
    """topology x orientation legality is config data; the depth ceilings are
    per-orientation caps (P2): radial trees need depth >= 2 (a depth-1 radial
    tree IS fanout-radial), horizontal trees cap at ``tree_horizontal_max_depth``
    (the taxonomy/dependency-audit orthogonal-bus ceiling — specimen-driven,
    CLAUDE.md Rule 1: no depth beyond what tree/dep-audit validate)."""
    legality: Mapping[str, list[str]] = engine.get("orientation_legality") or {}
    legal = legality.get(spec.topology.value, ["horizontal"])
    if spec.orientation.value not in legal:
        raise DiagramInputError(
            f"orientation {spec.orientation.value!r} is not legal for {spec.topology.value} (legal: {legal})"
        )
    if spec.topology is Topology.TREE:
        depth = tree_depth(spec)
        caps = engine.get("caps") or {}
        if spec.orientation is Orientation.RADIAL:
            if depth < 2:
                raise DiagramInputError(
                    "tree:radial requires depth >= 2 — a depth-1 radial tree IS fanout-radial "
                    "(use topology 'fanout' with orientation 'radial')"
                )
            if depth > int(caps.get("tree_radial_max_depth", 3)):
                raise DiagramCapacityError(f"tree:radial caps at depth {caps.get('tree_radial_max_depth', 3)}")
        else:
            max_h = int(caps.get("tree_horizontal_max_depth", 2))
            if depth > max_h:
                raise DiagramCapacityError(
                    f"tree:horizontal caps at depth {max_h} (got {depth}) — a deeper hierarchy uses "
                    "orientation 'radial' (tree: radial)"
                )


def _longest_directed_path(edges: list[Any], through: str | None = None) -> list[str]:
    """The longest simple forward path over the edge set (ids). If ``through``
    is given, prefer the longest path that passes through that node. Cycles
    are broken by visited-set; ties by first-appearance (deterministic)."""
    adj: dict[str, list[str]] = {}
    nodes: list[str] = []
    for e in edges:
        if e.source == e.target:
            continue
        adj.setdefault(e.source, []).append(e.target)
        for nid in (e.source, e.target):
            if nid not in nodes:
                nodes.append(nid)
    best: list[str] = []

    def walk(node: str, seen: frozenset[str], acc: list[str]) -> None:
        nonlocal best
        if len(acc) > len(best) and (through is None or through in acc):
            best = list(acc)
        for nxt in adj.get(node, []):
            if nxt not in seen:
                walk(nxt, seen | {nxt}, [*acc, nxt])

    for start in nodes:
        walk(start, frozenset({start}), [start])
    return best


def spine_members(spec: DiagramSpec) -> tuple[frozenset[int], frozenset[int]]:
    """Semantic Chromatics: the nodes and edges that carry the ONE accent.

    Hue encodes MEMBERSHIP of ONE main sequence — never identity, never every
    node. Returns ``(accent_node_indices, spine_edge_indices)``. The accent
    binds to the spine's EDGES (the flow the reader traces first), the HERO
    (nucleus), and the spine's SINK nodes (its terminals) — the destinations.
    Intermediate spine nodes stay neutral, so a five-node path is one blue
    line + a blue endpoint, not five blue titles.

    The agent declares WHICH relation is the spine (``spec.spine``); absent
    that, the engine infers ONE directed path:

    * hero WITH out-edges → the hero's out-fan (the prototype's destinations).
    * hero as a sink → the longest path INTO it.
    * no hero → the longest directed path overall.
    * nothing inferable (< 2 nodes on any path) → EMPTY; the
      ``spine-uninferable`` diagnostic asks the agent to declare a spine.

    Lanes are excluded — category membership is their own accent axis."""
    ids = [n.id for n in spec.nodes]
    idx_of = {nid: i for i, nid in enumerate(ids) if nid}
    edges = list(spec.edges)
    hero_i = next((i for i, n in enumerate(spec.nodes) if n.role is NodeRole.HERO), None)

    if spec.spine:
        spine_ids = set(spec.spine)
        if spec.topology is Topology.STATE_MACHINE:
            # Direction-aware for state machines: a 2-member spine over a
            # reciprocal pair (order-lifecycle's failed<->running) must bind
            # the accent to the BACK edge alone (the specimen's retry,
            # sm-acc) — "both endpoints in spine_ids" cannot distinguish
            # throw from retry, only direction can. Mirrors
            # solve_state_machine's own back-edge partition exactly
            # (self-loops excluded first, then back_edges() DFS over the
            # rest) so the accent and the solver's own routing never disagree.
            # ``edges`` here is spec-level (string source/target, matched
            # against ``hero_id``/``spine_ids`` throughout this function);
            # back_edges()/split_self_loops() need the index-based form, so
            # this branch resolves its OWN copy rather than reinterpreting
            # string ids as integers.
            resolved = resolved_edges(spec)
            non_self = split_self_loops(list(resolved))[1]
            flow_edges = [resolved[j] for j in non_self]
            back_idx = frozenset(non_self[j] for j in back_edges(len(spec.nodes), flow_edges))
            e_idx = frozenset(j for j in back_idx if edges[j].source in spine_ids and edges[j].target in spine_ids)
        else:
            e_idx = frozenset(j for j, e in enumerate(edges) if e.source in spine_ids and e.target in spine_ids)
    elif spec.topology is Topology.TREE:
        # A tree's root -> child fan is HIERARCHY, not a traced sequence —
        # auto-inferring "hero WITH out-edges -> the hero's out-fan" (the
        # generic default below) would accent EVERY root edge in blue on
        # any tree whose root carries the focal role (every tree, always).
        # No spine without an explicit ``spec.spine`` declaration.
        e_idx = frozenset()
    elif hero_i is not None:
        hero_id = ids[hero_i]
        roled = any(e.role for e in edges)
        out = [j for j, e in enumerate(edges) if e.source == hero_id and (e.role == "out" or not roled)]
        if out:
            e_idx = frozenset(out)  # the hero's out-fan is the spine
        else:
            # Hero as a sink: the accent is THE arriving edge — the kit's
            # release-edge figure (one privileged hop into the hero). With
            # several arrivals there is no single privileged hop; the hero
            # ring and riders carry the emphasis, the wires stay neutral.
            arriving = [j for j, e in enumerate(edges) if e.target == hero_id]
            e_idx = frozenset(arriving) if len(arriving) == 1 else frozenset()
    else:
        path = _longest_directed_path(edges)
        if len(path) < 2:
            return frozenset(), frozenset()
        seq = set(itertools.pairwise(path))
        e_idx = frozenset(j for j, e in enumerate(edges) if (e.source, e.target) in seq)

    # Accent NODES = the hero + the spine's SINKS (endpoints with no outgoing
    # spine edge). Intermediate spine nodes stay neutral — never all nodes.
    has_out = {edges[j].source for j in e_idx}
    spine_nodes = {edges[j].source for j in e_idx} | {edges[j].target for j in e_idx}
    sinks = {nid for nid in spine_nodes if nid not in has_out}
    accent_ids = sinks | ({ids[hero_i]} if hero_i is not None else set())
    return frozenset(idx_of[nid] for nid in accent_ids if nid in idx_of), e_idx


def assign_accents(spec: DiagramSpec, palette_len: int) -> tuple[int, ...]:
    """Semantic Chromatics node binding: ONE accent (index 0), carried only
    by the spine members; everything else neutral (-1). Hue is DERIVED from
    declared meaning (spine/role), never painted per element — so a cold
    agent declaring only structure gets the bound gestalt automatically and
    no diagram can emit a hue that contradicts meaning.

    An explicit ``node.accent`` still overrides (validated against the
    palette). Lanes keep their category axis (membership by band)."""
    if spec.topology is Topology.LANES:
        return _lanes_accents(spec, palette_len)
    accent_nodes, _ = spine_members(spec)
    if spec.topology is not Topology.HUB:
        # Kit binding: sink TITLES carry the accent only in the hub/axial
        # accent-zone (hub's DESTINATIONS). Everywhere else hue
        # lives on the spine EDGES + the hero — provider titles stay ink even
        # under an accent fan (the router/serving prototypes' explicit rule).
        heroes = frozenset(i for i, n in enumerate(spec.nodes) if n.role is NodeRole.HERO)
        accent_nodes = accent_nodes & heroes
    out: list[int] = []
    for i, node in enumerate(spec.nodes):
        if node.accent is not None:
            if node.accent >= palette_len:
                raise DiagramInputError(
                    f"node accent {node.accent} is outside the genome diagram_flow palette (len {palette_len})"
                )
            out.append(node.accent)
            continue
        out.append(0 if (i in accent_nodes and palette_len) else -1)
    return tuple(out)


def _lanes_accents(spec: DiagramSpec, palette_len: int) -> tuple[int, ...]:
    """Category → flow-palette slot (first-appearance order); every node in a
    category shares its slot. Explicit ``node.accent`` overrides per node."""
    order: list[str] = []
    for node in spec.nodes:
        if node.category not in order:
            order.append(node.category)
    slot_of = {cat: (i % palette_len if palette_len else -1) for i, cat in enumerate(order)}
    out: list[int] = []
    for node in spec.nodes:
        if node.accent is not None:
            if node.accent >= palette_len:
                raise DiagramInputError(
                    f"node accent {node.accent} is outside the genome diagram_flow palette (len {palette_len})"
                )
            out.append(node.accent)
            continue
        out.append(slot_of[node.category])
    return tuple(out)


def connector_accents(
    spec: DiagramSpec,
    edges: tuple[ResolvedEdge, ...],
    node_accents: tuple[int, ...],
    lanes: tuple[int, ...] = (),
    lane_hues: Mapping[str, Any] | None = None,
) -> tuple[int, ...]:
    """Semantic Chromatics edge binding: an edge carries the accent iff it is
    a SPINE edge (the main sequence the reader traces first) — the
    destination fan in the prototype's binding — everything else neutral
    (-1). Hue is a function of declared membership, never the endpoint's
    incidental color, so the compose edge INTO the accented nucleus stays
    grey while the publish fan OUT of it carries blue. Reciprocal pairs (G8)
    keep their per-direction lane hues (a conversation is its own axis) —
    EXCEPT state-machine, whose reciprocal pairs (order-lifecycle's
    throw/retry) ride their own return grammar instead: the lens bow's
    geometry already separates the two directions visually, and the accent
    binds to the back edge alone (see ``spine_members``), so painting a
    SECOND axis of meaning (lane hue) over the same pair would contradict
    it. ``mo.lane_dress_applies`` is the shared gate (also consumed by
    ``wiring.wire_motion``'s march dasharray and ``annotate``'s label hue,
    so hue/texture/label never disagree about which edges are lane-dressed);
    ``detect_lanes`` still computes a lane for every reciprocal pair (a pure
    structural fact motion.py owns) whether or not this gate paints it."""
    if spec.topology is Topology.LANES:
        # Lanes WIRES stay neutral (the kit's swimlanes: category lives on
        # the node marks, bands, and legend — colored rails would re-encode
        # the same axis twice and rainbow the gutter).
        return tuple(-1 for _ in edges)
    if spec.topology is Topology.SEQUENCE:
        # auth-sequence's binding: every RETURN message carries the accent
        # (the hero's own hue), calls stay neutral — independent of the
        # generic spine inference, which has no notion of "every return in
        # this trace" as a single relation.
        return tuple(0 if e.kind is EdgeKind.RETURN else -1 for e in edges)
    fwd = int((lane_hues or {}).get("forward", 0))
    rev = int((lane_hues or {}).get("reverse", -1))
    _, spine_edges = spine_members(spec)
    edge_out: list[int] = []
    for j, _e in enumerate(edges):
        if lanes and mo.lane_dress_applies(spec.topology, lanes[j]):
            edge_out.append(fwd if lanes[j] < 0 else rev)
            continue
        edge_out.append(0 if j in spine_edges else -1)
    return tuple(edge_out)


def shift_placement(p: Any, dx: float, dy: float) -> Any:
    """Region translation for an annotation placement — uniform move that
    PRESERVES the leader (unlike collide's collision-move, which drops it
    because only its box end moves; here anchor and box move together)."""
    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return p
    box = _dc_replace(p.box, x=p.box.x + dx, y=p.box.y + dy) if p.box is not None else None
    lines = tuple(_dc_replace(t2, x=t2.x + dx, y=t2.y + dy) for t2 in p.lines)
    dot = (p.dot[0] + dx, p.dot[1] + dy) if p.dot is not None else None
    entries = tuple(
        _dc_replace(
            e,
            swatch_x=e.swatch_x + dx,
            swatch_y=e.swatch_y + dy,
            swatch_path=translate_path(e.swatch_path, dx, dy),
            text=_dc_replace(e.text, x=e.text.x + dx, y=e.text.y + dy),
        )
        for e in p.entries
    )
    return _dc_replace(p, box=box, lines=lines, dot=dot, entries=entries, leader=translate_path(p.leader, dx, dy))


def shift_text(t: DiagramText | None, dx: float, dy: float) -> DiagramText | None:
    """Translate one chrome text run (region-local -> canvas)."""
    if t is None:
        return None
    from dataclasses import replace as _replace

    return _replace(t, x=t.x + dx, y=t.y + dy)


def _reanchor_zone_headers(
    lane_bands: tuple[LaneBand, ...], count: int, *, margin_x: float, canvas_w: float
) -> tuple[LaneBand, ...]:
    """Pin the zone-header band(s) — the LAST ``count`` entries the zone-header
    law appended to ``lane_bands`` — to the chassis margin, independent of the
    content region's own centering offset.

    The header is unioned into content LOCALLY (so it grows the content
    band's height and rides the same origin shifts as the nodes it titles),
    but ``stack_regions`` center-aligns the content region within the canvas
    (Law 1) whenever some OTHER region (a width_floor chassis, or a wide
    caption/footer) makes the canvas wider than content — and a header riding
    inside content then drifts with that centering offset instead of reading
    at the fixed chrome margin the specimen anchors it to (dep-audit's
    tr2-zone measured at the tree chassis' own margin_x, whatever x the tree's
    own bbox happened to center at). Both zone slots are affected identically
    — the ink (start-anchored, left) band pins to ``margin_x``; the accent
    (end-anchored, right) band, when a spec declares a second zone, pins to
    ``canvas_w - margin_x``. A one-zone spec (``count == 1``) only ever built
    the ink band, so the accent branch is a no-op."""
    if count <= 0 or not lane_bands:
        return lane_bands
    fixed = list(lane_bands)
    head_i = len(fixed) - count
    ink = fixed[head_i]
    fixed[head_i] = _dc_replace(ink, box=_dc_replace(ink.box, x=margin_x), header=_dc_replace(ink.header, x=margin_x))
    if count > 1:
        target = canvas_w - margin_x
        accent = fixed[head_i + 1]
        fixed[head_i + 1] = _dc_replace(
            accent, box=_dc_replace(accent.box, x=target), header=_dc_replace(accent.header, x=target)
        )
    return tuple(fixed)


def _expand_for_labels(
    ext: tuple[float, float, float, float] | None,
    nodes: list[NodePlacement],
    cfg: ParadigmDiagramConfig,
) -> tuple[float, float, float, float] | None:
    """Union each node's LABEL and DESC-LINE extents into the content bbox.
    Most runs sit inside the box (a no-op), but radial-outboard text spills
    past it; measuring here is the single place the canvas learns to hold
    every run whatever the topology placed it. Desc lines were once omitted —
    a ring's bottom-node desc overlapped the caption by a measured 4.78px."""
    if ext is None:
        return None
    x0, y0, x1, y1 = ext
    for n in nodes:
        for lbl in (n.label, *n.desc_lines):
            if lbl is None or not lbl.text:
                continue
            w = measure_voice(lbl.text, voice_for(cfg, lbl.cls))
            if lbl.anchor == "middle":
                lx0, lx1 = lbl.x - w / 2, lbl.x + w / 2
            elif lbl.anchor == "end":
                lx0, lx1 = lbl.x - w, lbl.x
            else:
                lx0, lx1 = lbl.x, lbl.x + w
            x0, x1 = min(x0, lx0), max(x1, lx1)
            y0, y1 = min(y0, lbl.y - 12.0), max(y1, lbl.y + 4.0)
    return (x0, y0, x1, y1)


def _gather_clip_rect_d(x: float, y: float, w: float, h: float, rx: float) -> str:
    """One clockwise rect (or rounded-rect) subpath, corners cut by ``rx`` —
    SVG treats a zero-radius arc as a straight line, so ``rx=0`` degrades to
    square corners with the same builder. Reused for both the gather clip's
    canvas-frame subpath (always ``rx=0``) and a card owner's own rounded
    figure."""
    if rx <= 0.0:
        return f"M {x:g},{y:g} H {x + w:g} V {y + h:g} H {x:g} Z"
    return (
        f"M {x + rx:g},{y:g} H {x + w - rx:g} A {rx:g},{rx:g} 0 0 1 {x + w:g},{y + rx:g} "
        f"V {y + h - rx:g} A {rx:g},{rx:g} 0 0 1 {x + w - rx:g},{y + h:g} "
        f"H {x + rx:g} A {rx:g},{rx:g} 0 0 1 {x:g},{y + h - rx:g} "
        f"V {y + rx:g} A {rx:g},{rx:g} 0 0 1 {x + rx:g},{y:g} Z"
    )


def _gather_clip_circle_d(cx: float, cy: float, r: float) -> str:
    """One clockwise two-arc circle subpath (top to bottom and back) — the
    same full-circle-via-two-semicircles recipe the flywheel rim-orbit path
    already uses below, for the SAME reason: <path> has no circle primitive."""
    return f"M {cx:g},{cy - r:g} A {r:g},{r:g} 0 0 1 {cx:g},{cy + r:g} A {r:g},{r:g} 0 0 1 {cx:g},{cy - r:g}"


def finish_layout(
    ctx: SolverContext,
    *,
    width: int,
    height: int,
    nodes_paint: list[NodePlacement],
    geos: list[EdgeGeo],
    operators: tuple[OperatorMark, ...] = (),
    lifelines: tuple[Any, ...] = (),
    activations: tuple[Any, ...] = (),
    legend: DiagramText | None = None,
    initial_dot: tuple[float, float] | None = None,
    initial_stub: Any = None,
    header_width: float = 0.0,
    lane_bands: tuple[Any, ...] = (),
    extra_regions: Mapping[str, Any] | None = None,
    auto_annotations: tuple[Any, ...] = (),
    extra_particles: tuple[ParticlePlacement, ...] = (),
) -> DiagramLayout:
    """Shared assembly: chrome + motion wiring + annotation pass + the record.

    The annotate chrome pass runs AFTER ``wire_motion`` (so connectors are
    collision obstacles) and BEFORE ``build_footer`` (so a footer-region
    legend/aside can grow the canvas first — ``extra_h`` re-anchors the footer
    below the reserved band). ``lane_bands``/``extra_regions`` are the lanes+hub
    solver seams: bands become collision obstacles, ``zone:*``/``lane:*``
    regions become annotation anchor frames. ``auto_annotations`` are
    solver-synthesized annotations (lanes' category legend); empty for every
    other solver, so this path is byte-identical for them. ``extra_particles``
    is the flywheel rim-orbit seam: riders outside the uniform edge->particle
    wiring (not tied 1:1 to a connector) — empty for every other solver."""
    # Enrich once: derive polyline + arrival tangent for the S-curve/line/arc
    # families so marker resolution and the annotate/collide pass read one
    # obstacle + direction contract, whatever built each geo.
    geos = enrich_geos(geos)
    # §2 REGION TREE (LAW 1 as composition): normalize the CONTENT to its own
    # local origin, wire + annotate in content coordinates, measure the
    # chrome regions, and let the stack compose the artifact — chrome bands
    # sit OUTSIDE the measured content, the canvas is the union plus
    # per-side margins, and no fixed y exists anywhere in chrome.
    m = float(ctx.ch.margin_x)
    # Vertical margin is INDEPENDENT of the horizontal one. A portrait
    # chassis (stack, request-descent) widens margin_x for left/right
    # breathing, but the region stack must not bleed that into the top /
    # inter-region / bottom gaps — that is the "obnoxious empty space above
    # and below" defect. Vertical rhythm stays a consistent 24 (or the
    # chassis' explicit margin_y) so a tall diagram reads as tight vertically
    # as a wide one.
    _margin_y = getattr(ctx.ch, "margin_y", None)
    mv = float(_margin_y) if _margin_y else min(m, 24.0)
    ext = content_extents(
        nodes_paint, geos, tuple(lane_bands), tuple(lifelines), tuple(activations), initial_dot, initial_stub
    )
    # Radial/ring topologies place node labels OUTBOARD of the box (flywheel,
    # radial hub); content_extents bboxes only boxes, so a cardinal label
    # spills past the canvas and clips (Law 1). Measure every node label and
    # union its extent so the canvas grows to hold the text.
    ext = _expand_for_labels(ext, nodes_paint, ctx.cfg)
    # THE zone-header law (single implementation — axial's corner pair and
    # stack's band pair fold in here; their texts are preset data now, per
    # Invariant 5): the first zone reads ink at the content's left edge, the
    # second reads accent right-anchored at its right edge, both one
    # ``zone_header_gap`` above the content top MEASURED AFTER label
    # expansion — the retired node-box-minus-40 landed 4px off a flywheel's
    # outboard label. Gap cited to the verb-algebra hand file (header
    # baseline to card top = 48).
    n_zone_bands = 0
    if ctx.spec.zones and ext is not None:
        # Chassis-declared zone air wins (per-family masthead air, cited to
        # that family's hand file); the engine constant is the axial-sheet
        # default the round-3 plate trace proved single-family.
        _zgap = (
            float(ctx.ch.zone_content_gap)
            if ctx.ch.zone_content_gap
            else float((ctx.engine.get("annotate") or {}).get("zone_header_gap", 48.0))
        )
        zx0, zx1 = ext[0], ext[2]
        zy = ext[1] - _zgap
        zone_bands = [
            LaneBand(
                box=RectSpec(x=zx0, y=zy, w=1.0, h=1.0),
                header=DiagramText(x=zx0, y=zy, text=ctx.spec.zones[0].upper(), cls="zoneh"),
                ground="typographic",
            )
        ]
        if len(ctx.spec.zones) > 1:
            zone_bands.append(
                LaneBand(
                    box=RectSpec(x=zx1, y=zy, w=1.0, h=1.0),
                    header=DiagramText(x=zx1, y=zy, text=ctx.spec.zones[1].upper(), cls="zoneha", anchor="end"),
                    ground="typographic",
                )
            )
        n_zone_bands = len(zone_bands)
        lane_bands = tuple(lane_bands) + tuple(zone_bands)
        ext = (ext[0], zy - 14.0, ext[2], ext[3])
    dx0, dy0 = (-ext[0], -ext[1]) if ext else (0.0, 0.0)
    (nodes_paint, geos, lane_bands, lifelines, activations, operators, legend, initial_dot, initial_stub) = (
        shift_content(
            nodes=nodes_paint,
            geos=geos,
            lane_bands=tuple(lane_bands),
            lifelines=tuple(lifelines),
            activations=tuple(activations),
            operators=tuple(operators),
            legend=legend,
            initial_dot=initial_dot,
            initial_stub=initial_stub,
            dx=dx0,
            dy=dy0,
        )
    )
    content_w = (ext[2] - ext[0]) if ext else 0.0
    content_h = (ext[3] - ext[1]) if ext else 0.0
    shifted_extras = {k: AnnRegion(x=r.x + dx0, y=r.y + dy0, w=r.w, h=r.h) for k, r in (extra_regions or {}).items()}
    # Annotate in CONTENT-LOCAL coordinates: canvas = the content frame;
    # header/footer are zero-height stubs at the content edges (legends
    # aimed there place provisionally and are RELOCATED into their stacked
    # chrome rows below).
    frames = {
        "canvas": AnnRegion(x=0.0, y=0.0, w=content_w, h=content_h),
        "header": AnnRegion(x=0.0, y=0.0, w=content_w, h=0.0),
        "footer": AnnRegion(x=0.0, y=content_h, w=content_w, h=0.0),
    }
    annotations, _extra_h, chrome_notes = build_annotations(
        ctx,
        geos,
        nodes_paint,
        width=float(content_w),
        height=float(content_h),
        lane_bands=tuple(lane_bands),
        extra_regions=shifted_extras or None,
        auto_annotations=tuple(auto_annotations),
        frames=frames,
    )
    chrome_legends = [a for a in annotations if a.kind == "legend" and a.region in ("header", "footer")]
    content_anns = [a for a in annotations if a not in chrome_legends]
    # Content region = content bbox UNION its annotations, renormalized so
    # nothing precedes the region origin (a label lifted above the top wire
    # grows the region upward instead of clipping).
    min_x = min([0.0] + [a.box.x for a in content_anns if a.box is not None])
    min_y = min([0.0] + [a.box.y for a in content_anns if a.box is not None])
    max_x = max([content_w] + [a.box.x + a.box.w for a in content_anns if a.box is not None])
    max_y = max([content_h] + [a.box.y + a.box.h for a in content_anns if a.box is not None])
    if min_x < 0 or min_y < 0:
        (nodes_paint, geos, lane_bands, lifelines, activations, operators, legend, initial_dot, initial_stub) = (
            shift_content(
                nodes=nodes_paint,
                geos=geos,
                lane_bands=tuple(lane_bands),
                lifelines=tuple(lifelines),
                activations=tuple(activations),
                operators=tuple(operators),
                legend=legend,
                initial_dot=initial_dot,
                initial_stub=initial_stub,
                dx=-min_x,
                dy=-min_y,
            )
        )
        content_anns = [shift_placement(a, -min_x, -min_y) for a in content_anns]
    content_w = max_x - min_x
    content_h = max_y - min_y
    # Chrome regions measured in their own local coordinates. Public composes
    # always land here with ctx.chrome == "caption" (the only public rendering
    # mode — no masthead, ever); "bare" is internal-only, set solely by the
    # sec 12.1 recursive embed seam (compose/resolvers/diagram.py).
    bare = ctx.chrome == "bare"
    header_rec, mast_w, mast_h = DiagramHeader(), 0.0, 0.0
    if ctx.chrome in ("bare", "plain"):
        # "plain" keeps the plate and drops only the caption line — the
        # lanes hand sheet is captionless while every other chrome stands.
        foot_text, foot_w, foot_h = None, 0.0, 0.0
    else:
        foot_text, foot_w, foot_h = measure_caption(ctx.spec, ctx.cfg)
    caption_h = foot_h
    legend_row_h = 16.0
    head_legends = [a for a in chrome_legends if a.region == "header"]
    foot_legends = [a for a in chrome_legends if a.region == "footer"]
    stacked_footer = foot_text is not None and bool(foot_legends)
    # head_legends deliberately DO NOT inflate mast_h/mast_w: the "masthead"
    # stack_regions band sits ABOVE content, so reserving stacking height for
    # it pushes content — and the zone header riding inside it — down by the
    # legend's own height (measured: an 82px 4-row column pushed dep-audit's
    # kicker from y38 to y144, out of the top-left corner every other
    # topology holds). A header-region legend instead rides the masthead
    # CORNER key idiom (the specimen's tr2-leg): it shares the zone header's
    # own row rather than reserving a row of its own — positioned below,
    # once content lands, from the zone header's own final y (see the
    # zone_header_y anchor after the region stack resolves).
    if foot_legends:
        # A footer carrying BOTH the caption sentence AND a legend row is a
        # STACK, not a shared band: max()-ing the two heights let both texts
        # gravitate to the same vertical center — dep-audit's caption and
        # legend baselines landed 3.51px apart (near-total overlap). Sum the
        # rows plus one legend_gap of air (the existing swatch-to-label/
        # inter-entry gap, reused here as the inter-row gap — no new
        # constant): legend on top, caption keeping its existing
        # bottom-pinned baseline (caption_pad/caption_bottom_pad already
        # calibrate THAT distance). A captionless chrome (bare/plain) keeps
        # the bare legend_row_h band, unchanged.
        row_gap = float((ctx.engine.get("annotate") or {}).get("legend_gap", 6))
        foot_h = (caption_h + row_gap + legend_row_h) if stacked_footer else legend_row_h
    # A footer-region annotation that overflows its band grows the band —
    # ``build_annotations`` computed this all along; the value was captured
    # and dropped, so a tall footer legend clipped past the canvas edge.
    foot_h = max(foot_h, _extra_h)
    legend_w = max([0.0] + [a.box.w for a in chrome_legends if a.box is not None])
    # The chassis width is a CANVAS FLOOR only where the chassis declares
    # ``width_floor`` (fixed/near-fixed specimen frames: stack, comparison,
    # the fan family, flywheel, tree-radial). Everywhere else the canvas hugs
    # content + margins and the chassis width serves purely as the SCALE
    # REFERENCE below — a 3-node pipeline stops centering inside a 1000px
    # phantom frame (the content-fit law).
    stack_min_w = float(ctx.ch.width) if (ctx.ch.width and ctx.ch.width_floor) else 0.0
    # A caption-band annotation above a rendered footer caption needs more
    # air than the generic inter-region margin — both are text bands, and at
    # mv≈24 they read as two stacked captions (the publish-path symptom). The
    # gap is a chassis constant; margins meet as max(), so raising the
    # content's bottom margin is the whole mechanism.
    _band_kinds = ("callout", "aside", "pin")
    _has_band_ann = any(a.kind in _band_kinds for a in content_anns)
    _ann_gap = float((ctx.engine.get("annotate") or {}).get("annotation_footer_gap", 40.0))
    content_bot_mv = _ann_gap if (_has_band_ann and foot_h > 0) else mv
    if ctx.ch.caption_gap:
        # Chassis-declared caption air (per-family, calibrated against the
        # family hand file's content-to-caption band) replaces the generic
        # inter-region margin — the plate trace measured every render's
        # caption band at 53-63% of its specimen's.
        content_bot_mv = float(ctx.ch.caption_gap)
    stacked = stack_regions(
        [
            MeasuredRegion(
                id="masthead",
                w=max(mast_w, mast_w + (legend_w + 24.0 if head_legends else 0.0)),
                h=mast_h,
                margin=(mv, m, mv, m),
            ),
            MeasuredRegion(id="content", w=content_w, h=content_h, margin=(mv, m, content_bot_mv, m), align="center"),
            MeasuredRegion(
                id="footer",
                w=max(foot_w, legend_w if foot_legends else 0.0),
                h=foot_h,
                # Caption air below: chassis-declared per family (the v3
                # prototype sheets pad 24-36; the v4 reference sheets 44),
                # falling back to the engine constant.
                margin=(
                    mv,
                    m,
                    float(ctx.ch.caption_pad)
                    if ctx.ch.caption_pad
                    else float((ctx.engine.get("annotate") or {}).get("caption_bottom_pad", mv)),
                    m,
                ),
                # The caption sentence centers (axial); the only other
                # footer occupant is a footer-region legend, which centers
                # alongside it now that the left-aligned brand footer line
                # (card chrome) is retired.
                align="center",
            ),
        ],
        min_width=stack_min_w,
    )
    width, height = stacked.width, stacked.height
    cdx, cdy = stacked.offsets.get("content", (m, m))
    (nodes_paint, geos, lane_bands, lifelines, activations, operators, legend, initial_dot, initial_stub) = (
        shift_content(
            nodes=nodes_paint,
            geos=geos,
            lane_bands=tuple(lane_bands),
            lifelines=tuple(lifelines),
            activations=tuple(activations),
            operators=tuple(operators),
            legend=legend,
            initial_dot=initial_dot,
            initial_stub=initial_stub,
            dx=cdx,
            dy=cdy,
        )
    )
    content_anns = [shift_placement(a, cdx, cdy) for a in content_anns]
    zone_header_y: float | None = None
    if n_zone_bands:
        # The content region just absorbed ``cdx`` — its OWN centering offset
        # inside the (possibly wider) canvas. The zone header rode along with
        # it (drifting off the chrome margin whenever content is narrower
        # than the canvas); pin it back now that the canvas width is final.
        lane_bands = _reanchor_zone_headers(lane_bands, n_zone_bands, margin_x=m, canvas_w=float(width))
        # Final canvas y of the ink zone band — the masthead corner key's
        # only anchor (below): a header-region legend shares this row rather
        # than reserving one of its own.
        zone_header_y = lane_bands[len(lane_bands) - n_zone_bands].header.y
    # Wire motion LAST — connectors/particles/gradients read the FINAL geo
    # coordinates (wiring earlier would freeze pre-stack paths).
    connectors, particles = wire_motion(ctx, geos)
    # Solver-supplied riders (the flywheel rim orbit) were built in PRE-shift
    # coordinates and the content moves through up to three shifts. Rebuild
    # each raw orbit path from the FINAL arc geometry instead — the geos'
    # ``arc`` tuples carry the shifted ring center, so the rider is
    # concentric with the arcs by construction.
    if extra_particles:
        ring = next((g.arc for g in geos if g.arc is not None), None)
        if ring is not None:
            from dataclasses import replace as _replace_pp

            rcx, rcy, rr = ring[0], ring[1], ring[2]
            rim = (
                f"M {rcx:g},{rcy - rr:g} A {rr:g},{rr:g} 0 0 1 {rcx:g},{rcy + rr:g} "
                f"A {rr:g},{rr:g} 0 0 1 {rcx:g},{rcy - rr:g}"
            )
            extra_particles = tuple(
                _replace_pp(pp, path_override=rim) if pp.path_override else pp for pp in extra_particles
            )
    particles = particles + extra_particles
    # Accent titles are the hub/axial accent-zone binding ONLY (verb-
    # algebra's DESTINATIONS): flag them here so lanes' category slots and
    # any other accent-indexed node keep ink titles.
    if ctx.spec.topology is Topology.HUB:
        nodes_paint = [
            _dc_replace(n, label_accent=True) if (n.accent_index >= 0 and n.role == "default") else n
            for n in nodes_paint
        ]
    # Gather-fan ornament: mark a STRUCTURAL one-to-many junction —
    # >=2 live edges leaving the focal node from one shared point (the
    # router trunk, the axial gather) — and its many-to-one mirror: >=2
    # edges LANDING on a convergence focal from one shared point (the
    # specimen law puts the knot at the sink too). Incidental fan-outs
    # elsewhere (a dag rank fanning) stay unmarked, matching the kit's
    # restraint.
    gathers: tuple[GatherPoint, ...] = ()
    if ctx.spec.topology in (Topology.FANOUT, Topology.HUB, Topology.CONVERGENCE, Topology.DAG):
        # The gather families: fan trunks, convergence mouths, the dag
        # AND-join. Orthogonal-bus topologies (tree) share stub points by
        # construction and never knot them (tree draws bare elbows).
        # Fan/hub/convergence knot intrinsically — the topology IS the
        # aggregation. A dag mouth knots only when a node at that point
        # AUTHORS ``gather: true``: a plain fan-in (bottleneck, shared
        # dependency) is the same geometry with per-edge meaning.
        dag_hinted = ctx.spec.topology is Topology.DAG
        shared: dict[tuple[float, float], list[tuple[int, bool]]] = {}
        for g in geos:
            e = ctx.edges[g.index]
            if e.inert or e.source == e.target:
                continue
            shared.setdefault((round(g.sx, 1), round(g.sy, 1)), []).append((e.source, False))
            shared.setdefault((round(g.tx, 1), round(g.ty, 1)), []).append((e.target, True))
        # A depart mouth WITH a trunk marks the gather by the STUB, never the
        # knot (frontier-serving's hub); a trunk-less depart keeps the knot
        # (model-gateway-tiers). Depart trunks are the marker-suppressed
        # synthetics — their far end is the spokes' shared departure.
        # BOTH trunk ends suppress: the far end is the spokes' shared
        # departure, and the NEAR end (the hub mouth) became a shared point
        # once fan exits collapsed to the language's center mouth — a skip edge
        # leaving the same center must not read as a second gather.
        depart_ends = {
            end
            for g in geos
            if g.relation_override and g.marker_override == "none"
            for end in ((round(g.tx, 1), round(g.ty, 1)), (round(g.sx, 1), round(g.sy, 1)))
        }
        ring_r = float((ctx.engine.get("connector") or {}).get("gather_ring_r", 5))
        points: list[GatherPoint] = []
        for (x, y), contribs in sorted(shared.items()):
            owners = [o for o, _ in contribs]
            if len(owners) < 2:
                continue
            if dag_hinted and not any(ctx.spec.nodes[o].gather for o in owners):
                continue
            if dag_hinted and (x, y) in depart_ends:
                continue
            # A JOIN point (every contribution ARRIVES — no owner reaches it as
            # an edge source) whose chassis chose a flush, trunk-less join
            # (join_trunk: 0 — model-gateway-tiers, gateway-balanced) marks the
            # AND-join by coincident overlap alone: pp-gateway-refined.svg and
            # pp-gateway-balanced.svg draw no ring at kv-cache — each member
            # keeps its own arrowhead, and the identical endpoint + identical
            # flat arrival tangent (every s_curve_h control shares its
            # endpoint's y) reads as one. A nonzero join_trunk (the default,
            # 44.0) keeps drawing the ring — frontier-serving/scatter-gather/
            # convergence-arrivals mark their knot explicitly and are unaffected.
            if dag_hinted and all(is_target for _, is_target in contribs) and not ctx.ch.join_trunk:
                continue
            owner = owners[0]
            # Occlusion is geometric law, not paint order (refined-fanout:
            # v04/alpha/v04a6/primer-diagrams/primer-fanout-refined.html —
            # bezel at the mouth, the node occludes the inward half). A seat
            # ON a node's boundary (within one ring radius of it) clips to
            # the boundary's outside via the node's OWN figure — an opaque
            # card painted over the inward half anyway (byte-stable), but a
            # bare-ring circle or containerless text satellite has nothing
            # to hide behind it. A mid-air trunk knot (no boundary within
            # reach) gets no clip and draws the full ring, as before.
            owner_p = next((n for n in nodes_paint if n.index == owner), None)
            clip_shape = ""
            clip_path_d = ""
            if owner_p is not None and abs(boundary_distance(owner_p, x, y)) < ring_r:
                if owner_p.shape == "circle":
                    # Clip to the PAINTED circle, not just its path radius: a
                    # stroke straddles the boundary (half in, half out), so a
                    # clip at bare r leaves the outer half-stroke to
                    # overpaint luck — measured as a ~17deg AA-fragile ring on
                    # the sharpest gather seats. +half the node's own
                    # stroke_width is the honest compensation (no magic
                    # constant): the SAME width chrome.py's place_circle
                    # painted the figure with.
                    clip_shape = "circle"
                    fig_d = _gather_clip_circle_d(owner_p.cx, owner_p.cy, owner_p.r + owner_p.stroke_width / 2.0)
                else:
                    clip_shape = "rect"
                    fig_d = _gather_clip_rect_d(
                        owner_p.box.x, owner_p.box.y, owner_p.box.w, owner_p.box.h, owner_p.box.rx
                    )
                # SVG unions sibling <clipPath> children — it never
                # subtracts — so the inverse (occlude-the-node) clip must be
                # ONE path, two evenodd subpaths: the canvas frame first,
                # then the owner's own figure. A point inside both crosses
                # an even number of subpath boundaries and clips OUT,
                # excluding exactly the figure's interior; a point inside
                # only the frame crosses once (odd) and stays visible.
                frame_d = _gather_clip_rect_d(0.0, 0.0, float(width), float(height), 0.0)
                clip_path_d = f"{frame_d} {fig_d}"
            points.append(
                GatherPoint(
                    x=x,
                    y=y,
                    clip_shape=clip_shape,
                    clip_path_d=clip_path_d,
                )
            )
        gathers = tuple(points)
    # Masthead texts (title/subtitle, when a chassis populates them) land at
    # their stacked offset; header legends right-anchor on the zone header's
    # OWN row (below) UNLESS the legend carries an explicit left anchor hint
    # (dep-audit-radial's cited hand file: its corner key sits flush under
    # the kicker, the opposite corner from dep-audit's plain sibling — see
    # AnnotationPlacement.anchor); footer legends left-align in the footer
    # row.
    placed_legends: list[AnnotationPlacement] = []
    if not bare:
        hdx, hdy = stacked.offsets.get("masthead", (m, m))
        header_rec = DiagramHeader(
            title=shift_text(header_rec.title, hdx, hdy),
            subtitle=shift_text(header_rec.subtitle, hdx, hdy),
            title_lines=tuple(t2 for t2 in (shift_text(tl, hdx, hdy) for tl in header_rec.title_lines) if t2),
        )
        for a in head_legends:
            if a.box is None:
                placed_legends.append(a)
                continue
            target_x = m if a.anchor == "left" else width - m - a.box.w
            # The masthead corner key (tr2-leg): top-anchored to the SAME 14px
            # of air the zone-header law itself clears above its own text (the
            # content-top adjustment two shifts back), so the key's top lines
            # up with the content band's own top edge — sharing the zone
            # header's row instead of a dedicated band stacked above it (see
            # the head_legends/mast_h comment above). No declared zone (no
            # row to share, e.g. the lanes auto legend's row-mode home) falls
            # back to centering within the top MARGIN band (mv, the same
            # vertical rhythm every other chrome gap in this function reads)
            # — never ``m`` (the HORIZONTAL margin; that mismatch is what
            # dropped a fallback-anchored row below the lane bands' own top).
            #
            # A LEFT-anchored key shares the kicker's own CORNER (not its
            # opposite corner the row-sharing math above assumes), so sharing
            # the row would overlap the kicker's own ink instead of merely
            # sitting on its other side — pp-tree-radial-v2.svg's own tr2-leg
            # stacks BELOW its kicker instead (kicker baseline y52, first key
            # row's top y80: a 28px drop, not a 14px rise). Both hand files
            # cite the SAME zone-header anchor point; only the sign and
            # magnitude of the offset differ by which side of the kicker the
            # key sits on.
            if zone_header_y is None:
                target_y = max(0.0, (mv - a.box.h) / 2.0)
            elif a.anchor == "left":
                target_y = zone_header_y + 28.0
            else:
                target_y = zone_header_y - 14.0
            placed_legends.append(shift_placement(a, target_x - a.box.x, target_y - a.box.y))
        fdx, fdy = stacked.offsets.get("footer", (m, height - m))
        # A stacked footer keeps the caption's baseline pinned to the band's
        # OWN bottom (the canvas-edge distance caption_pad/caption_bottom_pad
        # already calibrate) and seats the legend row in the air the stack
        # opened above it — never both centered on the same shared band.
        cap_dy = (fdy + (foot_h - caption_h)) if stacked_footer else fdy
        foot_text = shift_text(foot_text, fdx, cap_dy)
        legend_band_h = legend_row_h if stacked_footer else foot_h
        for a in foot_legends:
            if a.box is None:
                placed_legends.append(a)
                continue
            placed_legends.append(
                shift_placement(a, fdx - a.box.x, fdy + max(0.0, (legend_band_h - a.box.h) / 2.0) - a.box.y)
            )
    annotations = tuple(content_anns) + tuple(placed_legends)
    # The payload reports what was DRAWN: wiring's post-dress connector values
    # (D5 solid-wire, relation dress, accent-wire stillness all applied), never
    # a re-derivation — the artifact's self-description cannot lie.
    motion_by_index = {c.index: c.motion for c in connectors}
    track_by_index = {c.index: c.track for c in connectors}
    rendered_tracks = tuple(track_by_index.get(i, "static") for i in range(len(ctx.motions)))
    tint_by_index = {n.index: (n.glyph.tint if n.glyph else "") for n in nodes_paint}
    rendered = RenderedMotion(
        edge_motion=tuple(motion_by_index.get(i, m) for i, m in enumerate(ctx.motions)),
        track=rendered_tracks,
        glyph_tint=tuple(tint_by_index.get(i, "") for i in range(len(ctx.spec.nodes))),
        performance=mo.performance_tier(
            [motion_by_index.get(i, m) for i, m in enumerate(ctx.motions)], [e.inert for e in ctx.edges]
        ),
        fallback_applied=ctx.fallback_applied,
        warnings=ctx.warnings + chrome_notes,
    )
    ch = ctx.ch
    # Display scale is a CONSTANT per resolved chassis (the content-fit law): the chassis
    # width is the SCALE REFERENCE, so content NARROWER than it renders
    # proportionally narrower — cards hold ONE physical size across node
    # counts instead of a sparse canvas normalizing up to the display pin
    # (a 3-node pipeline drew ~40% larger cards than a 6-node one). Content
    # WIDER than the reference keeps the prior fit-to-pin (README columns
    # clamp anything past ~740, which would undo the size guarantee anyway),
    # so wide renders are byte-identical to the old law. Chrome never enters
    # the reference: scale is the same in every chrome mode (Law 1 — chrome
    # wraps content, it never resizes it). A chassis pinning BOTH display
    # dims is a fixed banner: honour it. A chassis without its own display_w
    # takes the engine default rather than rendering 1:1.
    display_target = float(ch.display_w or ctx.engine.get("display_w_default", 740))
    reference_w = float(ch.width) if ch.width else float(width)
    if ch.display_w and ch.display_h:
        disp_w, disp_h = int(ch.display_w), int(ch.display_h)
    elif width > 0:
        scale = display_target / max(reference_w, float(width))
        disp_w, disp_h = round(width * scale), round(height * scale)
    else:
        disp_w, disp_h = int(width), int(height)
    return DiagramLayout(
        width=width,
        height=height,
        display_w=disp_w,
        display_h=disp_h,
        layout_slug=ctx.slug,
        aspect=ch.aspect,
        header=header_rec,
        nodes=tuple(nodes_paint),
        connectors=connectors,
        particles=particles,
        operators=operators,
        lifelines=tuple(lifelines),
        activations=tuple(activations),
        annotations=annotations,
        lane_bands=tuple(lane_bands),
        gathers=gathers,
        legend=legend,
        initial_dot=initial_dot,
        initial_stub=initial_stub,
        footer=foot_text,
        regions=stacked.regions,
        palette_slots=(max([a for a in ctx.node_accents + ctx.edge_accents if a >= 0], default=-1) + 1),
        # A STILL diagram stays still: the entrance fade fires only when the
        # figure carries live motion (comparison: "a comparison is a
        # still claim" — motion: none end to end).
        entrance=(
            ctx.cfg.entrance
            if (
                particles or gathers or any(c.track in ("dash-march", "dash-drift") and not c.inert for c in connectors)
            )
            else "none"
        ),
        rendered=rendered,
    )


def apply_spec_chassis(ch: DiagramTopologyChassis, overrides: Mapping[str, Any]) -> DiagramTopologyChassis:
    """Merge a spec's shallow chassis overrides (design dims, never
    coordinates) onto the topology chassis: node/hero/node2 sub-dicts merge
    field-wise; scalar fields replace.

    A ``hero`` sub-dict's own keys accumulate onto ``hero_declared`` — the
    explicitness carrier the hero sizing law reads (``sizing.hero_width_floor``
    / ``hero_height_floor``): this is the ONE seam where a PRESET's citation
    is distinguishable from the paradigm's own default (which also always
    constructs ``hero.w``/``.h``, so ``model_fields_set`` alone can't tell
    them apart post-merge)."""
    if not overrides:
        return ch
    update: dict[str, Any] = {}
    for key, value in overrides.items():
        if key in ("node", "hero", "node2") and isinstance(value, Mapping):
            # Re-VALIDATE the merged sub-chassis (model_copy(update=...)
            # skips pydantic coercion, so a preset's YAML ints leaked into
            # float fields raw — rx 16 rendered "16" where the paradigm's
            # own 16 rendered "16.0", splitting byte formats by which seam a
            # value arrived through).
            base = getattr(ch, key)
            update[key] = type(base).model_validate({**base.model_dump(), **dict(value)})
            if key == "hero":
                update["hero_declared"] = ch.hero_declared | frozenset(value.keys())
        else:
            update[key] = value
    return ch.model_copy(update=update)


def effective_render_cfg(spec: DiagramSpec, paradigm: ParadigmDiagramConfig) -> ParadigmDiagramConfig:
    """The voice config the solver measured with, for RENDER-side consumers
    (the resolver's CSS emission): same slug → chassis → voice-override
    derivation as ``compute_diagram_layout``, so emitted font sizes can
    never drift from the measured geometry."""
    slug = layout_slug(spec)
    ch = paradigm.topologies.get(slug) or DiagramTopologyChassis()
    ch = apply_spec_chassis(ch, spec.chassis)
    return effective_diagram_cfg(paradigm, ch)


SolverFn = Callable[[SolverContext], DiagramLayout]


def compute_diagram_layout(
    spec: DiagramSpec,
    *,
    paradigm: ParadigmDiagramConfig,
    engine: Mapping[str, Any],
    palette_len: int,
    composite_only: bool = False,
    chrome: str = "caption",
    glyph_registry: Mapping[str, Any] | None = None,
    glyph_selections: tuple[GlyphTint, ...] = (),
    warnings: tuple[str, ...] = (),
) -> DiagramLayout:
    """Deterministic solve: same spec, same chassis, same bytes.

    ``spec`` must be post-normalization (AUTO roles resolved,
    ``direction: both`` expanded — the input seam's job). ``warnings`` carry
    input-seam notes (cyclic-dag promotion) through to the rendered record."""
    _ensure_solvers_registered()  # dispatch is order-independent (see registered_slugs)
    if any(n.role is NodeRole.AUTO for n in spec.nodes):
        raise DiagramInputError("spec reached the solver with AUTO roles; normalize via the input seam first")
    slug = layout_slug(spec)
    caps = engine.get("caps") or {}
    check_orientation(spec, engine)
    check_routing_overridable(spec, slug, engine)
    shrink = enforce_caps(spec, slug, caps)
    edges = resolved_edges(spec)
    node_accents = assign_accents(spec, palette_len)
    lanes_t = tuple(mo.detect_lanes(edges, float(engine.get("lane_offset", 4))))
    motions, fallback = mo.resolve_edge_motions(
        edges,
        spec_motion=spec.edge_motion,
        default=paradigm.edge_motion_default,
        allowlist=paradigm.edge_motion_allowlist,
        composite_only=composite_only,
        ladder={str(k): str(v) for k, v in (engine.get("fallback_ladder") or {}).items()},
        # Sequence owns its own replay grammar — a requested beam falls back
        # through the ladder with honest requested/rendered bookkeeping.
        stage_exempt=slug in {str(s) for s in ((engine.get("beam") or {}).get("stage_exempt_topologies") or [])},
    )
    ch = paradigm.topologies.get(slug) or DiagramTopologyChassis()
    ch = apply_spec_chassis(ch, spec.chassis)
    # Chassis voice overrides land HERE, once: every downstream measurement
    # (sizing/wrap) and placement (chrome) reads ctx.cfg, and the resolver
    # emits CSS from the same helper (effective_render_cfg) — one seam, no
    # measure/render drift.
    paradigm = effective_diagram_cfg(paradigm, ch)
    if chrome == "bare":
        # Bare chrome (F1): collapse the masthead/footer bands to pads and
        # let the canvas height + display ratio re-derive — the artifact
        # crops to content over transparent paper.
        bare = engine.get("chrome_bare") or {}
        top = min(ch.header_h, float(bare.get("top_pad", 24)))
        bottom = min(ch.footer_h, float(bare.get("bottom_pad", 20)))
        new_h = int(ch.height - (ch.header_h - top) - (ch.footer_h - bottom)) if ch.height else 0
        ch = ch.model_copy(update={"header_h": top, "footer_h": bottom, "height": max(new_h, 0), "display_h": 0})
    ctx = SolverContext(
        spec=spec,
        slug=slug,
        ch=ch,
        cfg=paradigm,
        engine=engine,
        edges=edges,
        node_accents=node_accents,
        edge_accents=connector_accents(spec, edges, node_accents, lanes_t, engine.get("lane_hues") or {}),
        motions=tuple(motions),
        lanes=lanes_t,
        lane_offsets=mo.lane_offsets(edges, lanes_t, tuple(motions), engine),
        shrink=shrink,
        palette_len=palette_len,
        composite_only=composite_only,
        fallback_applied=fallback,
        chrome=chrome,
        mono_triggers=[str(t) for t in engine.get("mono_triggers") or []],
        glyph_registry=glyph_registry,
        glyph_selections=glyph_selections or tuple(GlyphTint.INK for _ in spec.nodes),
        warnings=warnings,
    )
    solver = _SOLVERS.get(slug)
    if solver is None:
        # hub/lanes are declared topologies whose solvers land in a later
        # slice — until then a clear error beats the KeyError a raw dict
        # lookup would raise. The registered set is the requestable menu.
        raise DiagramInputError(
            f"no layout solver registered for topology {slug!r}; registered: {', '.join(registered_slugs())}"
        )
    return solver(ctx)


def register_solvers(solvers: Mapping[str, SolverFn]) -> None:
    """Topology modules register their slugs at import (the matrix
    kind->builder dispatch precedent — never a template branch)."""
    _SOLVERS.update(solvers)


# The solver modules that populate _SOLVERS at import. Listed here so the
# registry accessor can GUARANTEE they are loaded regardless of what imported
# first — the full set is process-order-independent. (Kept in sync with
# compose/diagram/__init__.py, which imports the same set for eager
# registration; either entry point yields the complete registry.)
_SOLVER_MODULES = (
    "fan",
    "graph",
    "hub",
    "lanes",
    "linear",
    "radial",
    "sequence",
)
_SOLVERS_LOADED = False


def _ensure_solvers_registered() -> None:
    """Import every solver module once, so ``_SOLVERS`` is fully populated for
    any caller — the registry is process-global and its population must not
    depend on import order (a test hitting ``registered_slugs()`` before the
    package ``__init__`` ran would otherwise see a short set). Lazy (not a
    top-level import) because the solver modules import back from this one."""
    global _SOLVERS_LOADED
    if _SOLVERS_LOADED:
        return
    import importlib

    for name in _SOLVER_MODULES:
        importlib.import_module(f"hyperweave.compose.diagram.{name}")
    _SOLVERS_LOADED = True


def registered_slugs() -> list[str]:
    """Every layout slug with a registered solver — the requestable set.

    These are the concrete ``layout_slug`` / payload ``subvariant`` values
    (``fanout-radial``, ``tree-radial``, ``dag`` …), the flattened result of
    topology x orientation. Discovery and the URL grammar emit this list so a
    caller never has to combine the axes by hand. The accessor guarantees the
    solver modules are imported, so the full set is returned whatever imported
    first (order-independent)."""
    _ensure_solvers_registered()
    return sorted(_SOLVERS)


_SOLVERS: dict[str, SolverFn] = {}
