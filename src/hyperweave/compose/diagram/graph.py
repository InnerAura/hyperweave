"""Layered-graph solvers: dag and state-machine.

The general-graph half of the family, kept simple and deterministic by
honest caps. DAG: longest-path rank assignment, fixed-sweep barycenter
crossing reduction (input-order tie-breaks — stable sorts only), rank-
channel S-curves, and skip edges routed through under-channels below the
content band. State machine rides the same machinery: back-edges (DFS,
edge order) lift out, the longest forward chain takes the pill baseline,
off-chain states drop beneath their predecessor, and back-edges return as
under-curves — the back-edge is the point.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from hyperweave.compose.diagram.anchors import boundary_anchor, port_row, side_anchor
from hyperweave.compose.diagram.axis import RIGHT, AxisMap
from hyperweave.compose.diagram.chrome import place_node, style_of
from hyperweave.compose.diagram.grouping import (
    boxes_by_id,
    build_region_bands,
    flow_gap_reservation,
    reseat_region_labels,
)
from hyperweave.compose.diagram.layered import (
    back_edges,
    barycenter_orders,
    check_rank_contradiction,
    duplex_return_indices,
    longest_path_ranks,
    pinned_orders,
    split_self_loops,
)
from hyperweave.compose.diagram.paths import (
    bisect_clearance_depth,
    fmt,
    line_d,
    line_len,
    s_curve_h,
    s_curve_h_len,
    s_curve_v,
    s_curve_v_len,
)
from hyperweave.compose.diagram.pinning import resolve_layout_pins
from hyperweave.compose.diagram.route import self_loop
from hyperweave.compose.diagram.sizing import (
    CHIP_H,
    CHIP_PAD_X,
    CHIP_STUB_MIN,
    chip_run_min,
    family_carries_marks,
    hero_height_floor,
    marker_reserved_stub,
    solve_chip_box,
    solve_node_box,
)
from hyperweave.compose.diagram.solver import finish_layout, layout_cap, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext, knot_collapse
from hyperweave.compose.geometry.text import measure_voice
from hyperweave.compose.spatial_records import LineSpec, RectSpec
from hyperweave.core.diagram import DiagramCapacityError, DiagramInputError, DiagramNode, NodeRole, NodeStyle

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from hyperweave.compose.diagram.records import DiagramLayout, NodePlacement
    from hyperweave.core.diagram import ResolvedEdge
    from hyperweave.core.paradigm import DiagramNodeChassis


def _rank_overrides(spec_nodes: list[DiagramNode]) -> dict[int, int]:
    """The caller's authored rank pins (``DiagramNode.rank``), keyed by node
    index — the fixed seeding for ``longest_path_ranks``. Empty for the common
    graph where ranks derive purely from edges."""
    return {i: node.rank for i, node in enumerate(spec_nodes) if node.rank is not None}


def _fan_spread(
    edges: tuple[ResolvedEdge, ...] | list[ResolvedEdge],
    placed: dict[int, NodePlacement],
    axis: AxisMap,
    *,
    pitch_max: float = 16.0,
    skip_edges: frozenset[int] = frozenset(),
) -> tuple[dict[int, float], dict[int, float]]:
    """Spread the MINOR coordinate where edges leave a shared source (fan-out)
    and land on a shared target (fan-in), so a bundle reads as distinct wires,
    not one
    overlapping cable. Within each group the edges order by the OTHER
    endpoint's center y — the topmost destination gets the topmost exit — so
    the fan stays untangled. The spread band is clamped to the node's inner
    height; a lone edge is absent from the maps and falls back to the center.
    Self-loops (source==target) are excluded — they own their own arc.
    ``skip_edges`` (rank-skip indices) are excluded too: they route through the
    under-channel, not a shared port, so folding them into a spread group would
    inflate its pitch and displace the plain arrivals."""
    from collections import defaultdict

    out_groups: dict[int, list[int]] = defaultdict(list)
    in_groups: dict[int, list[int]] = defaultdict(list)
    for j, e in enumerate(edges):
        if e.source == e.target or j in skip_edges:
            continue
        out_groups[e.source].append(j)
        in_groups[e.target].append(j)

    def _center(idx: int) -> float:
        return _minor_center(axis, placed[idx])

    exit_y: dict[int, float] = {}
    entry_y: dict[int, float] = {}

    def _assign(
        groups: dict[int, list[int]], node_of: dict[int, int], other_of: dict[int, int], out: dict[int, float]
    ) -> None:
        for node_i, members in groups.items():
            if len(members) < 2:
                continue
            box = placed[node_i].box
            cy = _minor_center(axis, placed[node_i])
            # Flush convergence: if any member's OTHER endpoint already sits on
            # this node's center row, its natural chord is straight — spreading
            # the group would bend that straight arrival into an S-curve. Collapse
            # to the one center mouth instead (service-dependencies auth->postgres,
            # gateway-balanced tiers->cache); a genuinely offset fan still spreads.
            if any(abs(_center(other_of[j]) - cy) <= _PORT_FLUSH for j in members):
                continue
            members.sort(key=lambda j: _center(other_of[j]))
            # The shared row mechanism (anchors.port_row): dag seats keep a
            # 10px face inset each side; the pitch cap is this family's own.
            offs = port_row(len(members), pitch=pitch_max, face_len=axis.box_minor(box.w, box.h), inset=10.0)
            for r, j in enumerate(members):
                out[j] = cy + offs[r]

    src_of = {j: e.source for j, e in enumerate(edges)}
    tgt_of = {j: e.target for j, e in enumerate(edges)}
    _assign(out_groups, src_of, tgt_of, exit_y)
    _assign(in_groups, tgt_of, src_of, entry_y)
    return exit_y, entry_y


def _conduit_lane_gaps(ctx: SolverContext, axis: AxisMap, edges: Sequence[ResolvedEdge]) -> list[float]:
    """Per-edge across-channel gap: the conduit floor where there is one."""
    return [
        max(
            ctx.lane_offsets[j] if j < len(ctx.lane_offsets) else 0.0,
            _conduit_chip_gap(ctx, axis, j),
        )
        for j in range(len(edges))
    ]


def _face_neighbour_edges(edges: Sequence[ResolvedEdge], members: Sequence[int], node_i: int) -> dict[int, list[int]]:
    """The face's edge indices grouped by which NEIGHBOUR they run to — one
    slot per key, a pair's two channels under the same key."""
    out: dict[int, list[int]] = {}
    for j in members:
        e = edges[j]
        other = e.target if e.source == node_i else e.source
        out.setdefault(other, []).append(j)
    return out


def _slot_extents(
    ctx: SolverContext,
    axis: AxisMap,
    edges: Sequence[ResolvedEdge],
    idxs: Sequence[int],
    lanes: Sequence[int],
    gaps: Sequence[float],
) -> tuple[float, float]:
    """What one slot occupies ACROSS the flow, each side of its centre.

    A conduit slot carries two lanes half a gap out, and the BRACKET label
    outboard of each: on a flow-leg bracket that is the lift plus the type's
    ascent above the outbound lane and the below offset plus the descent
    under the return lane; flowing down the labels sit beside the lanes, so
    the outboard cost is the lift plus the measured line. A single-edge
    slot carries its pill's half-extent across the run, a bare-labelled one
    half its text block, an unlabelled wire only its stroke. Slot spacing
    and the face band price these — the flat pill constant this replaces
    let a bracket label sit on the neighbouring conduit's wire (measured:
    the label laddered 120px off its seat fleeing it).
    """
    conn = ctx.engine.get("connector") or {}
    g = max((gaps[j] for j in idxs if j < len(gaps)), default=0.0)
    voice = ctx.cfg.edge_label_voice
    horiz = axis.flow == "right"
    ascent = float(voice.size) * ctx.cfg.text_ascent_ratio
    descent = float(voice.size) * ctx.cfg.text_descent_ratio
    lane_members = [j for j in idxs if j < len(lanes) and lanes[j] != 0]
    if lane_members:
        lift = float(conn.get("sm_label_lift", 8))
        if horiz:
            above_off, below_off = _bracket_offsets(lift, float(voice.size), ctx.cfg.text_ascent_ratio)
            return g / 2 + above_off + ascent, g / 2 + below_off + descent
        req = next((j for j in lane_members if lanes[j] < 0), lane_members[0])
        resp = next((j for j in lane_members if lanes[j] > 0), lane_members[-1])
        w_req = measure_voice(edges[req].label, voice) if edges[req].label else 0.0
        w_resp = measure_voice(edges[resp].label, voice) if edges[resp].label else 0.0
        return g / 2 + lift + w_req, g / 2 + lift + w_resp
    labelled = [j for j in idxs if edges[j].label]
    chips = [j for j in labelled if edges[j].label_style == "chip"]
    if chips:
        half = max((CHIP_H if horiz else solve_chip_box(edges[j].label, ctx.cfg)[0]) for j in chips) / 2
        return half, half
    if labelled:
        block = (ascent + descent) / 2 if horiz else max(measure_voice(edges[j].label, voice) for j in labelled) / 2
        return block, block
    return 1.0, 1.0


def _slot_stack(
    ctx: SolverContext,
    axis: AxisMap,
    edges: Sequence[ResolvedEdge],
    ordered_idxs: Sequence[Sequence[int]],
    lanes: Sequence[int],
    gaps: Sequence[float],
    pitch_max: float,
) -> tuple[list[float], list[float], float]:
    """Cumulative positions for an ORDERED row of slots: each adjacency is
    spaced by its two occupants' extents plus the collide gate's air,
    floored at the family port pitch. Returns the positions, each slot's
    lane gap, and the face band the stack needs (span plus the end lanes'
    half-gaps plus the row insets) — one construction shared by the
    reservation and the placement, so the two can never price the same
    slots differently."""
    air = _slot_stack_air(ctx)
    exts = [_slot_extents(ctx, axis, edges, idxs, lanes, gaps) for idxs in ordered_idxs]
    pos: list[float] = [0.0]
    for r in range(1, len(ordered_idxs)):
        pos.append(pos[-1] + max(pitch_max, exts[r - 1][1] + air + exts[r][0]))
    gs = [max((gaps[j] for j in idxs if j < len(gaps)), default=0.0) for idxs in ordered_idxs]
    band = pos[-1] + gs[0] / 2 + gs[-1] / 2 + 20.0
    return pos, gs, band


def _conduit_port_band(
    ctx: SolverContext,
    axis: AxisMap,
    edges: Sequence[ResolvedEdge],
    lanes: Sequence[int],
    gaps: Sequence[float],
    rank: Sequence[int],
    *,
    pitch_max: float = 16.0,
) -> dict[int, float]:
    """Minor band a conduit-bearing flow face needs to seat its own port.

    Under PERIMETER ROUTING the flow face carries at most the flush traffic
    — one same-row pair, since two neighbours cannot share the hub's row —
    so the band prices exactly ONE conduit slot: the widest pair's own
    extents (lanes plus bracket labels) with the row insets. This is what
    returns the hub to the standard card class; the multi-slot stack the
    perimeter superseded priced every off-row track's bracket onto this one
    face and grew the hero past twice its neighbours.
    """
    faces = _incident_by_face(edges, rank)
    out: dict[int, float] = {}
    for (node_i, _face), members in faces.items():
        if not any(j < len(lanes) and lanes[j] != 0 for j in members):
            continue
        by_other = _face_neighbour_edges(edges, members, node_i)
        widest = 0.0
        for idxs in by_other.values():
            if not any(j < len(lanes) and lanes[j] != 0 for j in idxs):
                continue
            above, below_e = _slot_extents(ctx, axis, edges, idxs, lanes, gaps)
            widest = max(widest, above + below_e)
        if widest:
            out[node_i] = max(out.get(node_i, 0.0), widest + 20.0)
    return out


def _incident_by_face(edges: Sequence[ResolvedEdge], rank: Sequence[int]) -> dict[tuple[int, str], list[int]]:
    """Edge indices grouped by the FACE they meet on each node.

    A face is decided by rank, not by travel direction: everything running
    between a node and a DOWNSTREAM neighbour — outbound or the conduit's
    return — shares the corridor on the flow-forward face, and everything to
    an upstream neighbour shares the other. Grouping per node instead put a
    node's upstream wires in the same port row as its downstream ones, which
    reserved a band for ports that were never on that face and pushed the
    real ones off their slots.
    """
    from collections import defaultdict

    out: dict[tuple[int, str], list[int]] = defaultdict(list)
    for j, e in enumerate(edges):
        if e.source == e.target:
            continue
        for node_i, other in ((e.source, e.target), (e.target, e.source)):
            if node_i >= len(rank) or other >= len(rank):
                continue
            face = "exit" if rank[other] > rank[node_i] else "entry"
            out[(node_i, face)].append(j)
    return out


def _conduit_face_slots(
    ctx: SolverContext,
    edges: tuple[ResolvedEdge, ...] | list[ResolvedEdge],
    centers: Mapping[int, float],
    face_len: Mapping[int, float],
    axis: AxisMap,
    lanes: Sequence[int],
    gaps: Sequence[float],
    rank: Sequence[int],
    routed: Mapping[int, _ChannelRoute],
    *,
    pitch_max: float = 16.0,
) -> tuple[dict[tuple[int, int], float], dict[int, float]]:
    """DESTINATION-MONOTONIC PORT ORDERING for faces carrying a conduit.

    The family's attachment law says a fan LEAVES its source at the edge
    centre and separates by curvature. That holds while every wire on the
    face travels the same way: two outbound curves to different rows diverge
    at once, so one mouth reads fine. It stops holding the moment a wire
    ARRIVES on that face going the other way. A return cannot be separated
    from an unrelated outbound by curvature — it has to reach a point on the
    face, and if that point is the shared centre it cuts across whatever
    leaves there.

    So a conduit-bearing face switches to SLOTS: one per neighbour, ordered
    by that neighbour's own minor, top destination to top slot. A pair shares
    its neighbour's slot and takes the lane gap inside it; plain edges on the
    same face are enrolled in the same ordering, because a plain edge holding
    the centre mouth crosses the conduits around it. Ordering by destination
    is what makes the result planar: wires that do not cross in the ordering
    cannot cross in the drawing.

    Returns the slot centres AND the minor band each face needs, so a face
    too short to seat its own ports can be grown by the residual rather than
    silently clamping its slots until neighbouring pairs interleave.

    Positions come in as bare ``centers``/``face_len`` mappings rather than
    placements so the SAME ordering can run before the boxes are seated: the
    rank-gap reservation has to decide which edges route through the channel
    from the rows alone, and a second, slightly different ordering there
    would let the reservation and the route disagree about the same edge.
    """
    slots: dict[tuple[int, int], float] = {}
    band: dict[int, float] = {}
    for (node_i, _face), members in _incident_by_face(edges, rank).items():
        if node_i not in centers:
            continue
        if not any(j < len(lanes) and lanes[j] != 0 for j in members):
            continue  # no conduit on this face — the centre mouth still rules
        by_other = _face_neighbour_edges(edges, members, node_i)
        # A perimeter-routed neighbour left this face entirely — its track
        # uses the hub's minor face — so it neither takes a slot nor prices
        # the stack.
        others = {o for o, idxs in by_other.items() if not all(j in routed for j in idxs)}
        if len(others) < 2:
            continue  # one neighbour, one slot: the centre already is it
        cy = centers[node_i]
        ordered = sorted(others, key=lambda k: centers[k])
        # Slots stack by their own EXTENTS — a conduit slot spends its lane
        # gap plus its bracket labels, a pill slot its pill, a bare wire its
        # stroke — with the air the collide gate will actually measure
        # between neighbours (its label text margin, floored at the plate
        # air), and the whole thing floored at the family's port pitch so
        # wires read apart. A uniform pitch here must price every adjacency
        # at the worst one; the stack gives each pair what its occupants
        # need. Pricing the air below the gate's margin is how a lawful
        # seat still gets laddered 100px off its bracket.
        pos, gs, _band = _slot_stack(ctx, axis, edges, [by_other[o] for o in ordered], lanes, gaps, pitch_max)
        # The face itself only has to seat the LANES (the labels hang out in
        # the gap): outermost lane half-gaps inside the inset. What centres
        # on the face is the full lane EXTENT — first lane to last lane —
        # not the slot span: centring the span pushes the heavier end's lane
        # past the inset whenever the end gaps differ (measured: a hub's top
        # lane departing 6px under the face's own corner radius). A face
        # still too short scales the whole stack rather than interleaving
        # pairs — and the band returned below is what grows it instead.
        ext_top = pos[0] - gs[0] / 2
        ext_bot = pos[-1] + gs[-1] / 2
        extent = ext_bot - ext_top
        usable = face_len[node_i] - 2 * 10.0
        scale = 1.0 if extent <= 0 else min(1.0, max(usable, 0.0) / extent)
        mid = (ext_top + ext_bot) / 2
        offs = [(p - mid) * scale for p in pos]
        # SNAP: the stack's one free parameter is its translation, and a
        # straight lane is worth more than centring (the lane law's own
        # priority). Spend it on the slot that lands nearest its neighbour's
        # row, so a same-row neighbour stays flush instead of inheriting a
        # few px of stack asymmetry as a jog every reader can see.
        deltas = [centers[o] - (cy + offs[r]) for r, o in enumerate(ordered) if o in centers]
        snap = min(deltas, key=abs, default=0.0)
        if abs(snap) > pitch_max:
            snap = 0.0
        for r, other in enumerate(ordered):
            slots[(node_i, other)] = cy + offs[r] + snap
        band[node_i] = max(band.get(node_i, 0.0), _band)
    return slots, band


def _slot_stack_air(ctx: SolverContext) -> float:
    """Air between adjacent slots' occupants — the same margin the collide
    ladder measures label neighbours with (``min_clearance / 2``), floored
    at the plate air, so a seat the stack blesses is a seat the gate will
    not move."""
    conn = ctx.engine.get("connector") or {}
    return max(float(conn.get("chip_pill_air", 6)), float(ctx.engine.get("min_clearance", 18)) / 2.0)


@dataclass(frozen=True)
class _ChannelRoute:
    """One routed edge's share of the channel plan (see ``_channel_plan``)."""

    hub: int
    """The conduit-bearing hub whose MINOR face this track uses."""
    side: float
    """Which minor face: -1 the near channel side, +1 the far."""
    slot_off: float
    """The slot's MAJOR offset from the hub's major centre along that face."""


@dataclass(frozen=True)
class _ChannelPlan:
    """PERIMETER ROUTING (owner ruling, superseding "all conduits share the
    flow face"): on a conduit-bearing hub, an off-row track leaves by the
    MINOR face nearest its partner's side — a riser out of the top or bottom
    face, one turn, a flow leg into the partner's own flow face. A pair is
    still the locked dual-lane bus (both channels through shared elbows, the
    lane gap held throughout); a plain off-row edge takes a single lane. The
    flow face then carries only the flush traffic — at most one same-row
    pair — which is what returns the hub to the standard card class instead
    of growing it to seat every track's bracket on one face.

    The round the perimeter superseded routed every off-row track out of the
    flow face through riser columns in the rank gap; it fixed the braid but
    priced the hub's face for all of them at once, and the owner's hero-size
    verdict retired it. A neighbour too shallow to clear the hub's own minor
    face (off-row past flush, yet within the face's half plus a fillet) has
    no perimeter to reach and keeps the family curve.

    The plan is decided ONCE, from the same rows the rank-gap reservation
    reads, and reused verbatim when the routes are drawn — deciding it twice
    from slightly different numbers is how a reservation and a route come to
    disagree about the same edge.
    """

    routed: dict[int, _ChannelRoute]
    perim_band: dict[int, float]
    """Per-hub MAJOR floor: what each minor face's slot stack occupies along
    the flow, so a narrow hub grows to seat its own perimeter ports."""


def _channel_col_sep(occ_a: float, occ_b: float, lane_air: float, pitch_max: float) -> float:
    """Centre-to-centre separation between two adjacent perimeter slots: the
    two riser bands' half-widths (a bus occupies its lane gap, a single wire
    none) plus the motion air, floored at the family's own port pitch so
    parallel risers read apart the way ports on a face do."""
    return max(pitch_max, (occ_a + occ_b) / 2 + lane_air)


def _channel_plan(
    ctx: SolverContext,
    axis: AxisMap,
    edges: tuple[ResolvedEdge, ...] | list[ResolvedEdge],
    lanes: Sequence[int],
    gaps: Sequence[float],
    rank: Sequence[int],
    centers: Mapping[int, float],
    boxes: Mapping[int, tuple[float, float]],
    *,
    pitch_max: float = 16.0,
) -> _ChannelPlan:
    """Classify each conduit-hub track and seat its perimeter slot.

    Per neighbour of a conduit-bearing hub face: a flush partner
    (``_PORT_FLUSH``) keeps the flow face and the straight grammar; a
    partner past the hub's own minor half-face (plus a fillet, so the riser
    exists at all) takes the PERIMETER — the hub's near or far minor face,
    whichever its row is on. The shallow between-band keeps the family
    curve: it is off-row, but there is no perimeter face between the hub's
    edge and a row the face itself spans. Skips keep the skip machinery and
    authored routing means it, exactly as everywhere else in this solver.

    Slot order per (hub, side) is what makes the perimeter planar: tracks
    turn at their partner's row, so the partner with the MORE EXTREME row
    must turn before its flow leg would cross a nearer partner's riser —
    the extreme slot sits at the end of the face AWAY from the legs' travel
    (flow-backward for downstream partners, flow-forward for upstream).
    """
    lane_air = float(ctx.engine.get("lane_min_air") or 3)
    arc_r = float(ctx.ch.over_arc_r)
    routed: dict[int, _ChannelRoute] = {}
    perim_band: dict[int, float] = {}
    claimed: set[int] = set()
    groups = _incident_by_face(edges, rank)
    for face_kind in ("exit", "entry"):
        for (node_i, face), members in groups.items():
            if face != face_kind or node_i not in centers or node_i not in boxes:
                continue
            if not any(j < len(lanes) and lanes[j] != 0 for j in members):
                continue
            others = {(edges[j].target if edges[j].source == node_i else edges[j].source) for j in members}
            if len(others) < 2:
                continue
            cy = centers[node_i]
            hub_half = axis.box_minor(*boxes[node_i]) / 2
            by_other: dict[int, list[int]] = {}
            for j in members:
                e = edges[j]
                if j in claimed or e.exit or e.entry or abs(rank[e.target] - rank[e.source]) != 1:
                    continue
                other = e.target if e.source == node_i else e.source
                by_other.setdefault(other, []).append(j)
            tracks: list[tuple[int, list[int], float]] = []
            for other, idxs in sorted(by_other.items()):
                delta = centers.get(other, cy) - cy
                if abs(delta) <= max(_PORT_FLUSH, 0.0) or abs(delta) <= hub_half + 2 * arc_r:
                    continue
                tracks.append((other, idxs, delta))
            if not tracks:
                continue
            legs_dir = 1.0 if face_kind == "exit" else -1.0
            for side in (-1.0, 1.0):
                side_tracks = [t for t in tracks if (1.0 if t[2] > 0 else -1.0) == side]
                side_tracks.sort(key=lambda t: (-abs(t[2]), t[0]))
                occs = [max((gaps[j] for j in idxs if j < len(gaps)), default=0.0) for _o, idxs, _d in side_tracks]
                pos = [0.0]
                for r in range(1, len(side_tracks)):
                    pos.append(pos[-1] + _channel_col_sep(occs[r - 1], occs[r], lane_air, pitch_max))
                span = pos[-1]
                for r, (_other, idxs, _delta) in enumerate(side_tracks):
                    # Extreme track at the end away from the legs' travel;
                    # the stack centres on the hub's major middle.
                    off = (pos[r] - span / 2) * legs_dir
                    for j in idxs:
                        routed[j] = _ChannelRoute(hub=node_i, side=side, slot_off=off)
                        claimed.add(j)
                band = span + occs[0] / 2 + occs[-1] / 2 + 2 * 10.0
                perim_band[node_i] = max(perim_band.get(node_i, 0.0), band)
    return _ChannelPlan(routed=routed, perim_band=perim_band)


def _resolve_perimeter_slots(
    ctx: SolverContext,
    axis: AxisMap,
    edges: tuple[ResolvedEdge, ...] | list[ResolvedEdge],
    placed: dict[int, NodePlacement],
    plan: _ChannelPlan,
    blockers: Sequence[RectSpec],
    clearance: float,
    furniture: Callable[..., tuple[RectSpec, ...]],
) -> dict[tuple[int, float, float], float]:
    """Absolute slot major per planned perimeter slot.

    A slot starts at the plan's offset from its hub's major centre, then its
    riser clears every card and band standing in its own span through
    ``_corridor_major`` — the one corridor law every detour branch runs.
    Slots resolve in stack order and a displaced slot pushes the next one
    ahead by the separation the plan priced, so displacement can never
    reorder what the ordering made planar.
    """
    arc_r = float(ctx.ch.over_arc_r)
    lane_air = float(ctx.engine.get("lane_min_air") or 3)
    gaps = _conduit_lane_gaps(ctx, axis, edges)
    by_group: dict[tuple[int, float], dict[float, list[int]]] = {}
    for j, route in plan.routed.items():
        by_group.setdefault((route.hub, route.side), {}).setdefault(route.slot_off, []).append(j)
    out: dict[tuple[int, float, float], float] = {}
    for (hub, side), slots_of in sorted(by_group.items()):
        if hub not in placed:
            continue
        ph = placed[hub]
        hub_mid = _major_center(axis, ph)
        face_minor = _minor_near(axis, ph) if side < 0 else _minor_far(axis, ph)
        prev_x: float | None = None
        prev_occ = 0.0
        for slot_off in sorted(slots_of):
            idxs = slots_of[slot_off]
            occ = max((gaps[j] for j in idxs if j < len(gaps)), default=0.0)
            rows: list[float] = [face_minor]
            skip_boxes: list[RectSpec] = [ph.box]
            for j in idxs:
                e = edges[j]
                other = e.target if e.source == hub else e.source
                if other in placed:
                    rows.append(_minor_center(axis, placed[other]))
                    skip_boxes.append(placed[other].box)
            lo, hi = min(rows), max(rows)
            x = _corridor_major(
                axis,
                blockers,
                major=hub_mid + slot_off,
                minor_lo=lo,
                minor_hi=hi,
                sgn=1.0,
                pad=clearance + arc_r,
                clearance=clearance,
                skip=furniture(*skip_boxes),
            )
            if prev_x is not None:
                sep = _channel_col_sep(prev_occ, occ, lane_air, 16.0)
                x = max(x, prev_x + sep)
            out[(hub, side, slot_off)] = x
            prev_x, prev_occ = x, occ
    return out


def _channel_route_geo(
    ctx: SolverContext,
    axis: AxisMap,
    j: int,
    e: ResolvedEdge,
    rank: Sequence[int],
    route: _ChannelRoute,
    placed: Mapping[int, NodePlacement],
    slot_x: Mapping[tuple[int, float, float], float],
) -> EdgeGeo:
    """One perimeter track: a riser out of the hub's MINOR face at its slot,
    one turn at the partner's row, a flow leg into the partner's own flow
    face — the orthogonal detour family's construction (straight legs, a
    fixed ``over_arc_r`` fillet shrinking only when a leg is shorter than
    the diameter), leaving the hub's flow face to the flush traffic.

    A pair's two channels are this same route displaced half the lane gap
    each way along BOTH axes — the riser along the flow, the leg across
    it — so they turn at the same elbow and hold the gap end to end: one
    conduit with two lanes, never two free wires.

    The label home is the LONGEST flat leg — the flow leg: a riding chip
    seats at its midpoint, a pair's bracket wraps it. Emitted as a solver
    ``label_pos`` so the annotate pass honours the seat.
    """
    hub = route.hub
    far = e.target if e.source == hub else e.source
    p_hub, p_far = placed[hub], placed[far]
    lane = ctx.lanes[j] if j < len(ctx.lanes) else 0
    gap = max(ctx.lane_offsets[j] if j < len(ctx.lane_offsets) else 0.0, _conduit_chip_gap(ctx, axis, j))
    h = lane * gap / 2
    hub_face = axis.channel_near if route.side < 0 else axis.channel_far
    hub_at = slot_x[(hub, route.side, route.slot_off)] + h
    far_face = axis.entry_side if rank[far] > rank[hub] else axis.exit_side
    far_at = _minor_center(axis, p_far) + h
    hub_pt = side_anchor(p_hub, side=hub_face, at=hub_at)
    far_pt = side_anchor(p_far, side=far_face, at=far_at)
    hm, hn = axis.major_of(*hub_pt), axis.minor_of(*hub_pt)
    fm, fn = axis.major_of(*far_pt), axis.minor_of(*far_pt)
    arc_r = float(ctx.ch.over_arc_r)
    dirn = 1.0 if fn >= hn else -1.0
    sgn = 1.0 if fm >= hm else -1.0
    r1 = min(arc_r, abs(fn - hn) / 2, abs(fm - hm) / 2)
    if e.source == hub:
        d = (
            f"M {_pt(axis, hm, hn)} "
            f"L {_pt(axis, hm, fn - dirn * r1)} "
            f"Q {_pt(axis, hm, fn)} {_pt(axis, hm + sgn * r1, fn)} "
            f"L {_pt(axis, fm, fn)}"
        )
        sx, sy = hub_pt
        tx, ty = far_pt
        polyline = (hub_pt, axis.point(hm, fn), far_pt)
        end_tangent = axis.point(sgn, 0.0)
    else:
        d = (
            f"M {_pt(axis, fm, fn)} "
            f"L {_pt(axis, hm + sgn * r1, fn)} "
            f"Q {_pt(axis, hm, fn)} {_pt(axis, hm, fn - dirn * r1)} "
            f"L {_pt(axis, hm, hn)}"
        )
        sx, sy = far_pt
        tx, ty = hub_pt
        polyline = (far_pt, axis.point(hm, fn), hub_pt)
        end_tangent = axis.point(0.0, -dirn)
    return EdgeGeo(
        index=j,
        d=d,
        sx=sx,
        sy=sy,
        tx=tx,
        ty=ty,
        length=abs(fn - hn) + abs(fm - hm),
        label_pos=axis.point((hm + sgn * r1 + fm) / 2, fn),
        label_bare=True,
        polyline=polyline,
        end_tangent=end_tangent,
    )


def _bracket_offsets(lift: float, size: float, ascent_ratio: float) -> tuple[float, float]:
    """Baseline offsets for a horizontal bracket label pair: the baseline
    already sits under its ink, so a label ABOVE the wire clears it by the
    lift alone, while one BELOW must also spend the ink's ascent (the same
    ``text_ascent_ratio`` every block measurement in sizing shares) before
    its clearance begins — the asymmetry is type metrics, not taste, and it
    gives both sides the same visible air."""
    return lift, lift + ascent_ratio * size


def _bracket_clear_of_hub(
    ctx: SolverContext,
    axis: AxisMap,
    bracket: float,
    forward: bool,
    hub: NodePlacement | None,
    f_maj: float,
    pair: tuple[ResolvedEdge, ResolvedEdge],
) -> float:
    """Slide the bracket point along the flow until BOTH labels clear the hub.

    The bracket is a PAIR seat — its whole meaning is that request and response
    share one along-run coordinate — so the two labels can only move together.
    The annotation collision ladder cannot do that: it resolves each label
    independently, and when only one of them fouls something it slides that one
    and silently breaks the pair.

    Only the hub can foul it, and structurally: the seat is the midpoint of the
    caller-side leg, and the return lane is the inboard one, so the shorter the
    leg the nearer the response label sits to the hub's own card. Below a
    certain leg length the midpoint lands inside the card's clearance. So the
    solver — which knows which card is the hub, the one fact the ladder would
    have to rediscover — prices that here and hands down a seat already clear.

    The clearance is the ladder's own (``min_clearance`` halved, the inflation
    ``_static_obstacles`` applies to every node box), so the two passes agree by
    construction instead of by a tuned constant. If the leg cannot hold a clear
    seat the cited midpoint stays: a bracket in the right place slightly
    crowded beats a bracket nowhere, the same ruling region labels take."""
    if hub is None:
        return bracket
    voice = ctx.cfg.edge_label_voice
    half_w = max(measure_voice(e.label, voice) if e.label else 0.0 for e in pair) / 2
    clear = float(ctx.engine.get("min_clearance", 18)) / 2
    lo_h, hi_h = (hub.box.y, hub.box.y + hub.box.h) if axis.flow == "down" else (hub.box.x, hub.box.x + hub.box.w)
    if forward:
        want = hi_h + clear + half_w
        return bracket if bracket >= want or want > f_maj - half_w else want
    want = lo_h - clear - half_w
    return bracket if bracket <= want or want < f_maj + half_w else want


def _bracket_conduit_labels(
    ctx: SolverContext,
    axis: AxisMap,
    edges: tuple[ResolvedEdge, ...] | list[ResolvedEdge],
    geos: list[EdgeGeo],
    plan: _ChannelPlan,
    placed: Mapping[int, NodePlacement],
) -> list[EdgeGeo]:
    """CONDUIT LABEL BRACKET (owner law; specimen and verdict in the round
    record): a duplex conduit never wears chip pills — a pill on one lane
    occludes the partner lane by construction, so the chip home does not
    exist on a conduit any more than on a bent wire. Its labels render as
    ONE bare micro-label pair per conduit: the request seated outboard of
    the outbound lane, the response outboard of the return lane, both
    anchor-middle at the SAME along-run coordinate on the pair's LONGEST
    flat leg — the flow leg of a perimeter track, the whole run of a
    straight pair. The arrowheads keep direction; the labels carry only
    the verbs, and the dialogue reads from position — question over the
    outbound, answer under the return.

    Seats are FINAL points (``label_bare=False``): the solver owns the
    bracket because only it knows which leg is the hub's and which lane is
    which — neither is recoverable from the drawn path.
    """
    conn = ctx.engine["connector"]
    lift = float(conn.get("sm_label_lift", 8))
    voice = ctx.cfg.edge_label_voice
    arc_r = float(ctx.ch.over_arc_r)
    above, below = _bracket_offsets(lift, float(voice.size), ctx.cfg.text_ascent_ratio)
    out = list(geos)
    done: set[int] = set()

    def _flow_leg(g: EdgeGeo, jj: int) -> tuple[tuple[float, float], tuple[float, float]]:
        """(far endpoint, hub endpoint) of a perimeter track — the flow leg
        runs between the far endpoint and the elbow."""
        hub = plan.routed[jj].hub
        if edges[jj].source == hub:
            return (g.tx, g.ty), (g.sx, g.sy)
        return (g.sx, g.sy), (g.tx, g.ty)

    for j in range(len(edges)):
        if j in done or not (j < len(ctx.lanes) and ctx.lanes[j] != 0):
            continue
        partner = _duplex_partner(edges, j)
        if partner is None:
            continue
        req, resp = (j, partner) if ctx.lanes[j] < 0 else (partner, j)
        done.update((j, partner))
        gi_req = next((i for i, g in enumerate(out) if g.index == req), None)
        gi_resp = next((i for i, g in enumerate(out) if g.index == resp), None)
        if gi_req is None or gi_resp is None:
            continue
        g_req, g_resp = out[gi_req], out[gi_resp]
        # The bracket's along-run seat: the midpoint of the request's FLOW
        # leg on a perimeter track (the leg ends where the elbow's fillet
        # begins), the midpoint of the shared run on a straight pair. Each
        # label's lane is its own channel's flow-leg row.
        if req in plan.routed and len(g_req.polyline) >= 3 and resp in plan.routed:
            req_far, req_hub = _flow_leg(g_req, req)
            resp_far, _resp_hub = _flow_leg(g_resp, resp)
            corner = g_req.polyline[1]
            c_maj, f_maj = axis.major_of(*corner), axis.major_of(*req_far)
            riser_ext = abs(axis.minor_of(*corner) - axis.minor_of(*req_hub))
            r1 = min(arc_r, riser_ext / 2, abs(f_maj - c_maj) / 2)
            sgn_cf = 1.0 if f_maj >= c_maj else -1.0
            bracket = (c_maj + sgn_cf * r1 + f_maj) / 2
            bracket = _bracket_clear_of_hub(
                ctx, axis, bracket, f_maj >= c_maj, placed.get(plan.routed[req].hub), f_maj, (edges[req], edges[resp])
            )
            req_minor = axis.minor_of(*req_far)
            resp_minor = axis.minor_of(*resp_far)
        else:
            bracket = (axis.major_of(g_req.sx, g_req.sy) + axis.major_of(g_req.tx, g_req.ty)) / 2
            req_minor = axis.minor_of(g_req.sx, g_req.sy)
            resp_minor = axis.minor_of(g_resp.tx, g_resp.ty)
        s_pair = 1.0 if resp_minor >= req_minor else -1.0
        if axis.flow == "right":
            req_seat = axis.point(bracket, req_minor - s_pair * above)
            resp_seat = axis.point(bracket, resp_minor + s_pair * below)
        else:
            # Flowing down the lanes are vertical and the labels sit BESIDE
            # them: the outboard support is the lift plus half the measured
            # line, and the baseline drops a third of the type size so the
            # ink centres on the bracket point.
            base = bracket + 0.35 * float(voice.size)
            req_w = measure_voice(edges[req].label, voice) if edges[req].label else 0.0
            resp_w = measure_voice(edges[resp].label, voice) if edges[resp].label else 0.0
            req_seat = axis.point(base, req_minor - s_pair * (lift + req_w / 2))
            resp_seat = axis.point(base, resp_minor + s_pair * (lift + resp_w / 2))
        if edges[req].label:
            out[gi_req] = replace(g_req, label_pos=req_seat, label_bare=False, label_anchor="middle", label_micro=True)
        if edges[resp].label:
            out[gi_resp] = replace(
                g_resp, label_pos=resp_seat, label_bare=False, label_anchor="middle", label_micro=True
            )
    return out


def _self_loop_geo(ctx: SolverContext, j: int, e: ResolvedEdge, p: NodePlacement, *, default_side: str) -> EdgeGeo:
    """A revise-in-place arc on node ``p`` via ``route.self_loop`` — the
    same connector grammar the hub/lanes solvers will reuse. Side is the
    edge's ``exit`` override, else ``default_side`` (top for baseline pills /
    rank cards so the loop bows out of the content band; a below-baseline node
    passes bottom). ``route.self_loop`` returns the arc, its length, the apex,
    the outboard label anchor, and the unit arrival tangent; the label rides
    ``label_pos`` (anchor 'start') so it flows through the label pipeline
    unchanged before and after the edge-label subsumption. ``end_tangent`` is
    set so ``enrich_geos`` leaves this geo untouched (route.py owns its
    geometry)."""
    side = e.exit or default_side
    conn = ctx.engine["connector"]
    standoff = float(conn.get("standoff", 0))
    # A chipped loop must be WIDE enough to show its own chip: the arc runs
    # flat through the apex, so the mouth is the run the pill seats on. At the
    # bare 24px mouth a 55px pill swallows the whole arc and the loop reads as
    # a detached tag. Same run law as a trunk chip (chip + a stub each side).
    mouth = float(conn.get("loop_mouth", 24))
    if e.label_style == "chip":
        mouth = max(mouth, chip_run_min([e], ctx.cfg, stub=CHIP_STUB_MIN))
    d, length, apex, label_anchor, end_tangent = self_loop(
        p,
        side,
        mouth=mouth,
        reach=float(conn.get("loop_reach", 46)),
        pinch=float(conn.get("loop_pinch", 18)),
        standoff=standoff,
    )
    # The geo's endpoints are the arc's TRUE mouth points — the explicit
    # marker lands on the re-entry (agent-task-lifecycle's arrowed tool-call
    # loop) and the census pairs the chevron to the arc. The label rides
    # ``label_pos`` (outboard of the apex) as before.
    mx0, my0 = (float(v) for v in d.split(" ", 2)[1].split(","))
    mx1, my1 = (float(v) for v in d.rsplit(" ", 1)[1].split(","))
    # A CHIP rides its wire at the run midpoint — the same law every other
    # channel chip obeys — so on a loop it seats at the APEX, centred. The
    # outboard anchor exists for a bare micro-label, which must sit beside the
    # stroke rather than cover it; an opaque pill parked outboard reads as a
    # detached tag floating near the arc instead of a label on it.
    is_chip = e.label_style == "chip"
    seat = apex if is_chip else label_anchor
    seat_anchor = "middle" if is_chip else "start"
    return EdgeGeo(
        index=j,
        # Returns ride the drift dash (specimen law: every state-machine
        # hand file draws its revise/self arcs as conn drift, chain solid).
        # relation_default (not relation_override) so an authored relation
        # on the edge still wins outright. drift's own dress terminal is a
        # dot (§3), but every hand specimen that authors relation: drift on
        # a return/self-loop pairs it with an explicit marker: arrow — the
        # dash comes from drift, the chevron stays. marker_override
        # reproduces that pairing for the UNAUTHORED case only (empty when
        # the edge already declares its own marker, so authored intent
        # still wins the resolve_marker precedence).
        semantic_dash=str(ctx.engine["connector"].get("dash", "2 7")),
        relation_default="drift",
        marker_override="" if e.marker else "arrow",
        d=d,
        sx=mx0,
        sy=my0,
        tx=mx1,
        ty=my1,
        length=length,
        end_tangent=end_tangent,
        label_pos=seat,
        label_max_w=float(conn.get("loop_label_max_w", 96)),
        label_anchor=seat_anchor,
    )


def _under_curve_depth(
    sx: float,
    sy: float,
    tcx: float,
    entry_y: float,
    c1x: float,
    c2x: float,
    base_c1y: float,
    base_c2y: float,
    crossed: list[RectSpec],
    clearance: float,
) -> tuple[float, float, float]:
    """(extra_depth, deepest_y, belly_x) for a back-edge under-curve: bisect the two
    deep control ys DOWN until the flattened cubic clears every crossed pill
    by ``clearance`` (G7 binds under-runs too). ``c2x`` is the caller's own
    span/depth-fit control-point x (``solve_state_machine``'s back branch) —
    distinct from the endpoint ``tcx`` so the curve's arrival angle can vary;
    the search flattens control2's Y only, matching whatever X the caller
    already solved. The search itself is ``bisect_clearance_depth`` (shared
    with ``linear.py``'s pipeline return, which keeps its own symmetric
    flat-bottom points builder)."""

    def points(extra: float) -> list[tuple[float, float]]:
        c1y, c2y = base_c1y + extra, base_c2y + extra
        pts: list[tuple[float, float]] = []
        for t_i in range(1, 48):
            t = t_i / 48.0
            v = 1.0 - t
            pts.append(
                (
                    v**3 * sx + 3 * v**2 * t * c1x + 3 * v * t**2 * c2x + t**3 * tcx,
                    v**3 * sy + 3 * v**2 * t * c1y + 3 * v * t**2 * c2y + t**3 * entry_y,
                )
            )
        return pts

    extra, deepest = bisect_clearance_depth(points, crossed, clearance)
    pts = points(extra)
    belly_x = max(pts, key=lambda pq: pq[1])[0]
    return extra, deepest, belly_x


def _over_arc_peak(
    sx: float,
    sy: float,
    tcx: float,
    entry_y: float,
    base_peak: float,
    crossed: list[RectSpec],
    clearance: float,
) -> float:
    """The over-arc return's actual peak Y: bisect the extra RISE up from
    ``base_peak`` until the flattened cubic clears every crossed card (+ the
    row's own label headroom, folded into ``clearance`` by the caller) by
    ``clearance`` — the over-arc's mirror of ``_under_curve_depth``'s downward
    search, sharing its ``bisect_clearance_depth`` engine (direction-agnostic:
    a clamped point-to-rect distance, so "deeper" reads as "higher" here
    without any change to the search itself). Both controls sit directly
    above their own endpoint (vertical departure/arrival, symmetric by
    construction, never pulled sideways like the under-curve's span-
    proportional pull) — an over-arc crosses ABOVE unrelated content, so the
    only unknown is how HIGH the peak must rise, never where it bends."""

    def points(extra: float) -> list[tuple[float, float]]:
        py = base_peak - extra
        pts: list[tuple[float, float]] = []
        for t_i in range(1, 48):
            t = t_i / 48.0
            v = 1.0 - t
            pts.append(
                (
                    v**3 * sx + 3 * v**2 * t * sx + 3 * v * t**2 * tcx + t**3 * tcx,
                    v**3 * sy + 3 * v**2 * t * py + 3 * v * t**2 * py + t**3 * entry_y,
                )
            )
        return pts

    extra, _deepest = bisect_clearance_depth(points, crossed, clearance)
    return base_peak - extra


def _place_dag_node(
    ctx: SolverContext,
    i: int,
    node: DiagramNode,
    cx: float,
    cy: float,
    w: float,
    h: float,
    *,
    family_marked: bool = False,
) -> NodePlacement:
    """Dispatch a rank card to its resolved anatomy, centered at (cx, cy):
    card/card+glyph is the family default; glyph-circle (fixed chassis
    radius) or pill (its own content-solved box) render through the shared
    chrome placements, still keyed to the rank's uniform reserved slot.
    Glyph-circle NEVER scales for a hero (``circle_r=ch.circle_r`` pinned,
    never ``hero_circle_r``) and never inside-stacks (``hub=False`` pinned)
    — preserved verbatim, matching ``solve_dag``'s own box-solving loop.
    Pill/card chassis is role-derived (``ch.hero if role is HERO else
    ch.node``) via the seam's own default — matches the caller's ternary."""
    style = style_of(node, ctx.spec, ctx.ch)
    if style == NodeStyle.GLYPH_CIRCLE.value:
        # Role-derived radius (mismatch #5, FIXED): a hero coin scales to the
        # hero chassis radius in BOTH the box solve and the placement.
        r = ctx.ch.hero_circle_r if node.role is NodeRole.HERO else ctx.ch.circle_r
        return place_node(ctx, node, i, cx, cy, w=2 * r, h=2 * r, hub=False)
    return place_node(ctx, node, i, cx, cy, w=w, h=h, family_marked=family_marked)


def _sibling_chip_major(
    ctx: SolverContext,
    axis: AxisMap,
    edges: list[ResolvedEdge],
    skip_idx: frozenset[int],
    source: int,
    placed: dict[int, NodePlacement],
    s_major: float,
) -> float | None:
    """Where a chipped sibling's pill sits ALONG the flow, or None.

    A chip on a plain adjacent-rank edge seats at that edge's run midpoint. A
    sibling skip leaving the same face should turn THERE — the pill then reads
    as the junction rather than as something the skip clipped on its way past.
    Only straight siblings qualify: on a bending run the pill is not on the
    departure axis, so aligning to it would pull the turn off the wire."""
    best: float | None = None
    # A gather HUB relocates its verb chip onto the synthetic depart TRUNK, so
    # the pill does not sit on any declared edge at all — looking only at
    # sibling edges misses it and the skip turns above the chip instead of
    # beside it. The trunk seat is deterministic (mouth + trunk_len/2 along the
    # flow), so compute it here rather than waiting for the seating pass that
    # runs after routing.
    src_node = ctx.spec.nodes[source]
    if src_node.gather and source in placed:
        out_edges = [e for j, e in enumerate(edges) if e.source == source and e.target != source and j not in skip_idx]
        if len(out_edges) >= 2 and any(e.label for e in out_edges):
            ch = ctx.ch
            trunk_len = max(
                float(ch.depart_trunk or 0),
                chip_run_min(out_edges, ctx.cfg, stub=_GATHER_STANDOFF),
            )
            mouth = side_anchor(placed[source], side=axis.exit_side, at=_minor_center(axis, placed[source]))
            return axis.major_of(*mouth) + trunk_len / 2
    for j, sib in enumerate(edges):
        if j in skip_idx or sib.source != source or sib.source == sib.target:
            continue
        if not (sib.label and sib.label_style == "chip"):
            continue
        if sib.source not in placed or sib.target not in placed:
            continue
        a, b = placed[sib.source], placed[sib.target]
        if abs(_minor_center(axis, a) - _minor_center(axis, b)) > _PORT_FLUSH:
            continue  # a bending sibling's pill is off the departure axis
        # The chip seats at the midpoint of the DRAWN run — face to face, not
        # centre to centre. Averaging box centres is off by half the height
        # difference whenever the two cards are not the same size.
        exit_major = axis.major_of(a.box.x + a.box.w, a.box.y + a.box.h)
        entry_major = axis.major_of(b.box.x, b.box.y)
        mid = (exit_major + entry_major) / 2
        if mid > s_major and (best is None or mid < best):
            best = mid
    return best


_PORT_FLUSH = 3.0
"""Row-alignment tolerance (px): an arrival whose source center sits within this
of the target center is treated as flush (a straight chord), so ``_fan_spread``
leaves it — and its group — on the center mouth instead of bending it."""
_GATHER_STANDOFF = 9.0
"""Gather-trunk chip standoff (dag-scatter specimen). The resolve chip on the
85px trunk seats 67px wide with a 9px stub each side — its mouth-side edge sits
9px off the sink card, reading centered but mouth-hugging. Also the gap between
the trunk wire and the chip above / note below it."""


def _join_chip_stub(ctx: SolverContext) -> float:
    """Per-side stub for a JOIN gather trunk's ``chip_run_min`` call: the join
    branch of ``knot_collapse`` always terminates in a drawn arrowhead (its
    ``marker`` defaults to ``"arrow"``, never overridden by ``solve_dag``'s
    join call), so the mouth-side stub must clear the chevron's own draw
    length beyond the bare ``_GATHER_STANDOFF`` visible-thread floor —
    frontier-serving's 'cache' seated on the bare 9px standoff left ~1px
    between the pill and an 8px chevron (``marker_size``), the arrowhead
    drawing into the chip. The chip seats at the trunk's true midpoint
    (``_seat_gather_chip``), so both sides take the marker-inclusive stub —
    the knot side gains slack rather than the law growing an asymmetric seat.
    Thin wrapper over the owner-level law (``sizing.marker_reserved_stub``) —
    every marker-terminated trunk site shares this one mechanism now, DAG's
    dag-scatter citation included."""
    return marker_reserved_stub(ctx.engine, _GATHER_STANDOFF)


def _seat_gather_chip(
    ctx: SolverContext, geos: list[EdgeGeo], slots: list[int], trunk: EdgeGeo, *, lift: float | None = None
) -> None:
    """Relocate a gather's chip + note to the trunk MOUTH (dag-scatter idiom).

    A join collapses its arrivals to a knot and one trunk carries them to the
    sink; the DESCRIPTION of what the gather produces (scatter: ``resolve`` /
    ``one response``) belongs at that output, not scattered up the spokes. The
    default seats the chip on its own spoke — for scatter that lands it near
    the fan knot, ~97px short of the card. Here the chip mouth-hugs (right
    edge ``_GATHER_STANDOFF`` off the card, lifted just above the wire) and each
    note stacks below the wire, centered under the chip. Positions are written
    as ``label_pos`` on the converging spoke geos: ``_edge_geo_by_index`` keeps
    join labels on the spokes (dag), the annotate label branch honors a
    ``label_pos`` verbatim, and the chip branch honors it once supplied."""

    axis = AxisMap.for_slug(ctx.slug)
    mx, my = trunk.tx, trunk.ty  # the join trunk runs knot -> mouth
    chip_slot = next((s for s in slots if ctx.edges[geos[s].index].label_style == "chip"), None)
    if chip_slot is None:
        return
    # The chip seats at the trunk's RUN MIDPOINT (specimen law, unanimous:
    # every specimen chip sits at frac 0.48-0.56 of its drawn run). On the
    # dag-scatter 84px trunk — chip + 2x9 stubs — midpoint and mouth-hugging
    # coincide; anchoring mouth-minus-9 on a LONGER trunk drifted the chip to
    # frac 0.62-0.71 with a 34px stub one side and 9px the other — the
    # asymmetric seat that reads as a random placement.
    # The midpoint runs ALONG the trunk and the lift runs ACROSS it. Flowing
    # right those are x and y; flowing down they swap, and taking them as x/y
    # regardless seats a vertical join's chip on the sink's own face instead of
    # mid-trunk (the trunk's x-midpoint is constant when the trunk is vertical).
    trunk_s_major = axis.major_of(trunk.sx, trunk.sy)
    mouth_major, mouth_minor = axis.major_of(mx, my), axis.minor_of(mx, my)
    chip_major = (trunk_s_major + mouth_major) / 2
    # DAG joins float the chip a mouth-lift above the trunk (arrivals crowd the
    # knot, so the verb clears them); convergence grounds it ON the wire
    # (lift=0) — its own specimen (convergence-arrivals) seats the compose chip
    # dead-center on the trunk, nothing arriving to collide.
    dy = (CHIP_H / 2 + _GATHER_STANDOFF) if lift is None else lift
    if axis.flow == "down":
        # The mouth-lift clears arrivals that crowd the knot by moving the chip
        # PERPENDICULAR to the trunk. On a horizontal trunk that is upward, off
        # a busy junction but still reading as "on the line". Transposed it
        # becomes a sideways shove: the pill leaves a vertical trunk entirely
        # and reads as a detached tag with the note stranded beside it. The
        # deeper law wins — a chip rides its wire — and a vertical trunk does
        # not need the lift anyway: its arrivals converge AT the knot, half a
        # trunk-length from the chip's own centred seat.
        dy = 0.0
    geos[chip_slot] = replace(
        geos[chip_slot], label_pos=axis.point(chip_major, mouth_minor - dy), label_anchor="middle"
    )
    note_voice = ctx.cfg.edge_label_voice
    note_slots = [
        s
        for s in slots
        if s != chip_slot and ctx.edges[geos[s].index].label and ctx.edges[geos[s].index].label_style != "chip"
    ]
    # Notes clear the CHIP'S OWN BOX, not just the wire: a grounded chip
    # (lift=0, convergence) hangs CHIP_H/2 below the trunk at the same x, so a
    # wire-relative seat lands the first note inside the pill and the collide
    # ladder flings it into blank space. Stacking below max(wire, chip bottom)
    # keeps the lifted DAG case byte-identical (its chip bottom sits above the
    # wire).
    # Notes stack clear of the chip's own PLATE, and the plate's extent across
    # the trunk is its height only when the trunk runs horizontally. On a
    # vertical trunk the across-extent is the pill's WIDTH, so clearing by
    # CHIP_H/2 leaves the first note sitting inside the pill.
    chip_w = measure_voice(ctx.edges[geos[chip_slot].index].label, ctx.cfg.edge_label_voice) + 2 * CHIP_PAD_X
    chip_across = axis.box_minor(chip_w, CHIP_H)
    note_base = max(mouth_minor, (mouth_minor - dy) + chip_across / 2)
    for r, s in enumerate(note_slots):
        note_y = note_base + _GATHER_STANDOFF + note_voice.size + r * (note_voice.size + _GATHER_STANDOFF)
        # A middle-anchored note straddles its clearance point. That is fine
        # when the stack runs DOWN from a horizontal trunk (the offset is
        # vertical, so width never re-enters), but on a vertical trunk the
        # offset is horizontal and half the note swings back over the plate.
        # Left-align it at the clearance point instead.
        geos[s] = replace(
            geos[s],
            label_pos=axis.point(chip_major, note_y),
            label_anchor="start" if axis.flow == "down" else "middle",
        )


def _seat_depart_chip(
    ctx: SolverContext, geos: list[EdgeGeo], slots: list[int], mouth: tuple[float, float], knot: tuple[float, float]
) -> None:
    """Seat a depart-hub's verb chip ON its trunk (frontier-serving ``route``).

    A gather HUB leaves on one solid stub to a knot, then fans; the verb NAMING
    the fan (route) belongs on that stub, centered, grounded ON the wire — the
    mouth-side mirror of ``_seat_gather_chip``, minus the join's mouth-lift (a
    depart chip rides the trunk, not floated above it, because nothing arrives
    there to collide). The chip is authored on one spoke; ``knot_collapse``
    re-rooted every spoke at the knot, so without this the chip falls to the
    generic pass and lands on that spoke's bend instead of the trunk."""
    chip_slot = next((s for s in slots if ctx.edges[geos[s].index].label_style == "chip"), None)
    if chip_slot is None:
        return
    axis = AxisMap.for_slug(ctx.slug)
    # Same transposition as the join seat: the midpoint runs ALONG the trunk and
    # the constant runs ACROSS it. Taking them as x/y regardless seats a
    # vertical depart chip off in space beside the fan (the parity sweep caught
    # it at 37px from any wire, with no stub at all).
    mx, my = mouth
    kx, ky = knot
    mouth_major, mouth_minor = axis.major_of(mx, my), axis.minor_of(mx, my)
    knot_major = axis.major_of(kx, ky)
    geos[chip_slot] = replace(
        geos[chip_slot],
        label_pos=axis.point((mouth_major + knot_major) / 2, mouth_minor),
        label_anchor="middle",
    )


def _curve_len(axis: AxisMap, maj1: float, min1: float, maj2: float, min2: float) -> float:
    """Arc length of a plain S-curve given in MAJOR/MINOR terms."""
    x1, y1 = axis.point(maj1, min1)
    x2, y2 = axis.point(maj2, min2)
    return (s_curve_h_len if axis.flow == "right" else s_curve_v_len)(x1, y1, x2, y2)


def _minor_center(axis: AxisMap, p: NodePlacement) -> float:
    """A placed box's center ACROSS the flow — the coordinate a lane aligns
    on. Flowing right that is cy; flowing down it is cx."""
    return axis.minor_of(p.box.x + p.box.w / 2, p.box.y + p.box.h / 2)


def _major_center(axis: AxisMap, p: NodePlacement) -> float:
    """A placed box's center ALONG the flow — cx flowing right, cy flowing down."""
    return axis.major_of(p.box.x + p.box.w / 2, p.box.y + p.box.h / 2)


def _minor_near(axis: AxisMap, p: NodePlacement) -> float:
    """The box face on the NEAR side across the flow (where the over-channel
    lives): its top edge flowing right, its left edge flowing down."""
    return axis.minor_of(p.box.x, p.box.y)


def _minor_far(axis: AxisMap, p: NodePlacement) -> float:
    """The box face on the FAR side across the flow (where the under-channel
    lives): its bottom edge flowing right, its right edge flowing down."""
    return axis.minor_of(p.box.x + p.box.w, p.box.y + p.box.h)


def _leg_blockers(
    axis: AxisMap,
    boxes: Sequence[RectSpec],
    *,
    major: float,
    minor_lo: float,
    minor_hi: float,
    sgn: float = 1.0,
    pad: float = 0.0,
    clearance: float = 0.0,
    skip: Sequence[RectSpec] = (),
) -> list[RectSpec]:
    """Boxes a MINOR-running leg at ``major`` would pass through on its way
    between ``minor_lo`` and ``minor_hi``.

    The span test is the shipped span-aware corridor's (ruling 2026-07-16): a
    box counts when its own minor extent OVERLAPS the leg's, not merely when
    it sits beyond the target's face.

    Pads default to ZERO because DETECTION and DISPLACEMENT are different
    questions. "Does this wire run through that card" is bare geometry, and it
    is the same question the gallery's wire-crosses-card sweep asks — trigger
    and guard have to agree, or a route detours around something it was never
    going to touch. Only ``_corridor_major`` passes pads, and asymmetrically,
    because it pushes one way: full ``pad`` on the side it moves to, bare
    ``clearance`` on the side it leaves."""
    lo_pad, hi_pad = (clearance, pad) if sgn > 0 else (pad, clearance)
    out: list[RectSpec] = []
    for b in boxes:
        if any(b is s for s in skip):
            continue
        if not (axis.minor_of(b.x, b.y) < minor_hi and axis.minor_of(b.x + b.w, b.y + b.h) > minor_lo):
            continue
        if axis.major_of(b.x, b.y) - lo_pad < major < axis.major_of(b.x + b.w, b.y + b.h) + hi_pad:
            out.append(b)
    return out


def _run_blocked(
    axis: AxisMap,
    boxes: Sequence[RectSpec],
    *,
    minor: float,
    major_lo: float,
    major_hi: float,
    skip: Sequence[RectSpec] = (),
) -> bool:
    """Does a MAJOR-running leg at ``minor`` cross a box between ``major_lo``
    and ``major_hi``? The transpose of ``_leg_blockers`` — same bare-geometry
    question, along the flow instead of across it."""
    return any(
        axis.major_of(b.x, b.y) < major_hi
        and axis.major_of(b.x + b.w, b.y + b.h) > major_lo
        and axis.minor_of(b.x, b.y) < minor < axis.minor_of(b.x + b.w, b.y + b.h)
        for b in boxes
        if not any(b is s for s in skip)
    )


def _corridor_major(
    axis: AxisMap,
    boxes: Sequence[RectSpec],
    *,
    major: float,
    minor_lo: float,
    minor_hi: float,
    sgn: float,
    pad: float,
    clearance: float,
    skip: Sequence[RectSpec] = (),
) -> float:
    """Push a MINOR-running leg's major coordinate along ``sgn`` until it
    clears every box in its own minor span — the span-aware corridor, lifted
    out of the authored elbow so every detour branch runs the one law.

    A detour's TRAVEL leg has always been cleared (``over_arc_clear`` above the
    shallowest card, the channel below the deepest); its ENTRY leg never was,
    so a route could ride a clear channel and then descend straight through a
    same-rank sibling to reach the card behind it. Cards paint after edges, so
    the wire vanishes into the box and the defect reads as clean."""
    moved = True
    while moved:
        moved = False
        for b in _leg_blockers(
            axis,
            boxes,
            major=major,
            minor_lo=minor_lo,
            minor_hi=minor_hi,
            sgn=sgn,
            pad=pad,
            clearance=clearance,
            skip=skip,
        ):
            major = (axis.major_of(b.x + b.w, b.y + b.h) + pad) if sgn > 0 else (axis.major_of(b.x, b.y) - pad)
            moved = True
    return major


def _pt(axis: AxisMap, major: float, minor: float) -> str:
    """One path coordinate, written in major/minor and emitted in screen space.

    Every skip-channel and over-arc route below is built this way so its
    geometry transposes with the flow axis. RIGHT is the identity map and the
    same ``fmt`` runs on both components, so the horizontal cell's path strings
    are byte-for-byte what they were before the axis existed."""
    x, y = axis.point(major, minor)
    return f"{fmt(x)},{fmt(y)}"


def _lane_rows(
    grid_members: list[int],
    provisional: Mapping[int, float],
    pitch: float,
    edges: Sequence[ResolvedEdge],
    rank: list[int],
    minor_of: Mapping[int, float],
    spec_nodes: Sequence[DiagramNode],
) -> dict[int, float]:
    """Lane-aligned MINOR coordinate per grid member — lanes over independent
    centering. "Row" is the across-flow position: cy flowing right, cx
    flowing down.

    The centering formula seats every rank around the shared canvas mid, so
    adjacent ranks row-align only when their counts happen to match; one
    insertion knocks every cross-rank edge into an S (the service-dependencies
    billing transform: 4 services vs 3 stores put the store rank a half-pitch
    off the grid and zero edges ran straight). The lane law instead reads the
    rows already placed one rank left:

    - a single-source node snaps to its source's row (the reads/emits/cache
      lanes);
    - a multi-source node centers on the MIDPOINT of its sources' rows,
      unless one inbound is chip-labeled — then it snaps to the labeled
      source's row, first label by declaration order when several carry
      chips (Postgres rides Auth's row for the reads lane even after writes
      arrives);
    - a gather node always takes the midpoint — its trunk chip is furniture
      on the knot, not a lane vote (gateway-balanced's cache centers on the
      tier fan, dead on the middle tier's row);
    - a source designated by MORE than one member of the rank snaps nobody —
      a fan distributes around its mouth (the four services keep the grid;
      snapping them all to the gateway's row would stack the fan);
    - skip edges (rank diff >= 2) ride channels, not lanes, so they never
      vote.

    Snapped rows then pass a monotone min-pitch chain in rank order, so an
    authored order never inverts and boxes never overlap; a conflict loser
    shifts down one pitch instead of stealing the row. Balanced 1:1 ranks
    reproduce their provisional rows exactly — the pass is a no-op on every
    already-aligned figure.

    The cascade looks lopsided where a rank cannot seat its snaps — two
    174-wide stores wanting rows 83px apart pin the first and shove the second
    135px past its own midpoint — and distributing that conflict around the
    rank's centre instead was measured as the alternative. It is not better:
    on cache-aside-mesh the two seatings give the SAME total cross-axis bow
    (378.6) and the same worst edge (152.6), and centring buys a 26px
    reduction on one edge by breaking a lane that was dead straight. The
    binding constraint is the pitch, not the seating, so the cascade stays and
    keeps the straight lane it earns."""
    targets: dict[int, float] = {}
    designated: dict[int, int] = {}
    for m in grid_members:
        inbound = [
            e
            for e in edges
            if e.target == m and e.source != m and rank[m] - rank[e.source] == 1 and e.source in minor_of
        ]
        if not inbound:
            continue
        src_cy = {e.source: minor_of[e.source] for e in inbound}
        if spec_nodes[m].gather:
            targets[m] = (min(src_cy.values()) + max(src_cy.values())) / 2
            continue
        if len(src_cy) == 1:
            designated[m] = inbound[0].source
            continue
        chips = [e for e in inbound if e.label and e.label_style == "chip"]
        if chips:
            designated[m] = chips[0].source
        else:
            targets[m] = (min(src_cy.values()) + max(src_cy.values())) / 2
    claims: dict[int, int] = {}
    for source in designated.values():
        claims[source] = claims.get(source, 0) + 1
    for m, source in designated.items():
        if claims[source] == 1:
            targets[m] = minor_of[source]
    rows: dict[int, float] = {}
    running = -math.inf
    for m in grid_members:
        cy = targets.get(m, provisional[m])
        if running > -math.inf and pitch > 0:
            cy = max(cy, running + pitch)
        rows[m] = cy
        running = cy
    return rows


def _duplex_conduit_geo(
    ctx: SolverContext,
    axis: AxisMap,
    j: int,
    e: ResolvedEdge,
    pa: NodePlacement,
    pb: NodePlacement,
    rank: Sequence[int],
    slots: Mapping[tuple[int, int], float],
) -> EdgeGeo:
    """One channel of a SAME-ROW local duplex — the family's OWN edge,
    lane-shifted.

    AMENDED SCOPE (owner composition ruling): only the flush pair reaches
    this. It draws the same S-curve every adjacent-rank edge draws, twice, a
    lane pitch apart — which for a same-row pair degenerates to two parallel
    straight runs. The fanned case this construction used to cover (two
    parallel curves, by translating both endpoints of the cubic) was
    falsified by eye: a free curve separates a fan by curvature, and a face
    carrying traffic both ways cannot be read that way — an off-row pair now
    takes the orthogonal channel route (``_channel_route_geo``) instead.

    The one thing the return does differently is which faces it uses: routed
    like an ordinary edge it would exit the flow-forward face and cross the
    whole diagram to get home, which is what put the readme-ai return wires
    through the hero card. So it mirrors both (``entry_side`` to leave,
    ``exit_side`` to arrive) and covers its partner's run backwards.

    The lane pitch is spent along the MINOR axis, through each anchor's own
    ``at``, never as a free perpendicular translation of the finished
    endpoints. A perpendicular offset is only parallel to the card face when
    the chord is axis-aligned; on the fanned pair its chord normal carried an
    8.3px component straight through the hero's right face, so the outbound
    departed 8.3px INSIDE the card and the return's arrowhead stopped 8.3px
    outside it, floating. Re-resolving the boundary crossing at a shifted
    ``at`` keeps every endpoint ON its own card, whatever the chord does.

    Dress follows for free: ``lane_dress_applies`` is already true for dag, so
    the outbound channel reads accent and the return reads muted — the
    conversation grammar the gateway specimen uses.
    """
    outbound = rank[e.target] > rank[e.source]
    leave = axis.exit_side if outbound else axis.entry_side
    arrive = axis.entry_side if outbound else axis.exit_side
    gap = ctx.lane_offsets[j] if j < len(ctx.lane_offsets) else 0.0
    gap = max(gap, _conduit_chip_gap(ctx, axis, j))
    shift = ctx.lanes[j] * gap / 2
    a_slot = slots.get((e.source, e.target), _minor_center(axis, pa))
    b_slot = slots.get((e.target, e.source), _minor_center(axis, pb))
    sx, sy = side_anchor(pa, side=leave, at=a_slot + shift)
    tx, ty = side_anchor(pb, side=arrive, at=b_slot + shift)
    curve = s_curve_h if axis.flow == "right" else s_curve_v
    curve_len = s_curve_h_len if axis.flow == "right" else s_curve_v_len
    return EdgeGeo(index=j, d=curve(sx, sy, tx, ty), sx=sx, sy=sy, tx=tx, ty=ty, length=curve_len(sx, sy, tx, ty))


def _conduit_chip_gap(ctx: SolverContext, axis: AxisMap, j: int) -> float:
    """Across-channel separation a conduit needs — its LAWFUL FLOOR.

    With the dialogue seats at 0.25/0.75 the two pills are half a run apart
    and clear each other ALONG the wire, so this no longer has to hold two
    stacked plates apart (it used to reserve ``half_pill_h * 2 + air``, 32px,
    which is what made three slots need a 116px face). What remains is not a
    bare motion constant either: a channel passing a seated pill is a FOREIGN
    wire to it, and a foreign wire must clear the pill BODY rather than
    graze its stroke. So the floor is written from its terms —

        max(motion_lane_air, half_pill_h + chip_foreign_wire_clearance)

    — and a hand-picked small lane (the +/-3.5 that looks tidy) threads the
    partner wire under the pill, which the foreign-wire battery reports.
    """
    partner = _duplex_partner(ctx.edges, j)
    if partner is None:
        return 0.0
    conn = ctx.engine.get("connector") or {}
    motion_lane_air = float(ctx.engine.get("lane_min_air") or 3)
    foreign_clear = float(conn.get("chip_foreign_wire_clearance", 2))
    half_pill_h = 0.0
    for k in (j, partner):
        edge = ctx.edges[k]
        if edge.label and edge.label_style == "chip":
            w, h = solve_chip_box(edge.label, ctx.cfg)
            # The pill's half-extent ACROSS the run: its height on a run the
            # flow follows, its width on one crossing the flow.
            half_pill_h = max(half_pill_h, (h if axis.flow == "right" else w) / 2)
    if half_pill_h <= 0.0:
        return motion_lane_air
    headroom = float(conn.get("lane_rounding_headroom", 0.5))
    return max(motion_lane_air, half_pill_h + foreign_clear + headroom)


def _bare_twin(e: ResolvedEdge) -> ResolvedEdge:
    """The edge as its label will actually render on a conduit: a bare
    micro-label, whatever style was authored. A conduit never wears a pill
    (the bracket law), so every run/leg floor for its labels must price the
    ink, not the plate — feeding the authored chip style here books ~50px of
    pill-and-stub run for a 10px-tall line of text."""
    return replace(e, label_style="") if e.label_style else e


def _duplex_partner(edges: Sequence[ResolvedEdge], j: int) -> int | None:
    """The index of edge ``j``'s reciprocal, if it has one."""
    e = edges[j]
    for k, o in enumerate(edges):
        if k != j and o.source == e.target and o.target == e.source:
            return k
    return None


def solve_dag(ctx: SolverContext) -> DiagramLayout:
    ch = ctx.ch
    spec = ctx.spec
    n = len(spec.nodes)
    edges = list(ctx.edges)
    caps = {**(ctx.engine.get("caps") or {}), **(ctx.spec.caps or {})}
    axis = AxisMap.for_slug(ctx.slug)
    vertical_flow = axis.flow == "down"  # knot/trunk geometry floats along the flow
    # Authored routing words are FLOW-FRAME words (AxisMap.side): `exit: top`
    # names the near channel and `entry: left` the flow-facing face, whichever
    # way the graph runs. Transposed once, here, so every predicate below
    # compares screen sides against screen sides. RIGHT is the identity, so the
    # horizontal cell never sees this line.
    if axis is not RIGHT:
        edges = [replace(e, exit=axis.side(e.exit), entry=axis.side(e.entry)) for e in edges]
    # Self-loops carry no rank/crossing info (a v->v edge would push its own
    # rank up forever) — partition them out, rank + order on the remainder,
    # and route them as their own arc below.
    loop_idx, non_self = split_self_loops(edges)
    max_self_loops = layout_cap(caps, ctx.slug, "max_self_loops", 2)
    if len(loop_idx) > max_self_loops:
        raise DiagramCapacityError(f"{ctx.slug} caps at {max_self_loops} self-loops (got {len(loop_idx)})")
    # A LOCAL DUPLEX (u->v with v->u) is a round trip between two adjacent
    # nodes, not feedback: the FIRST-DECLARED direction defines the rank step
    # and its reciprocal carries no rank information at all — ranking on both
    # would demand v after u and u after v at once. Partitioned out here for
    # exactly the reason self-loops are, one line up. The return edge is not
    # dropped: it keeps its geometry and rides the paired lane offset below,
    # so the pair draws as one dual-channel conduit. ``detect_lanes`` assigns
    # -1 to the first-declared direction and +1 to its reciprocal, so keeping
    # the first-declared as the ranking edge puts the outbound channel and the
    # rank step on the same edge — the two passes cannot disagree about which
    # way the conduit flows.
    duplex_return = duplex_return_indices(edges, non_self)
    flow_edges = [edges[j] for j in non_self if j not in duplex_return]
    # Defensive re-check (the promotion seam's backstop): a cycle among
    # distinct nodes that ISN'T a local duplex has no rank — production paths
    # promote it to state-machine in coerce_diagram_input before the solver
    # runs; a direct caller that skipped the seam must hear a refusal, not
    # receive rank-relaxed garbage geometry.
    if back_edges(n, flow_edges):
        raise DiagramInputError(
            "dag declares a cycle among its edges; cyclic dags promote to state-machine at the input "
            "seam (coerce_diagram_input) — route through it, or declare topology: state-machine"
        )
    fixed = _rank_overrides(list(spec.nodes))
    rank = longest_path_ranks(n, flow_edges, fixed)
    check_rank_contradiction(flow_edges, rank, fixed)
    n_ranks = max(rank) + 1
    max_ranks = layout_cap(caps, ctx.slug, "max_ranks", 5)
    if n_ranks > max_ranks:
        raise DiagramCapacityError(f"{ctx.slug} caps at {max_ranks} ranks (got {n_ranks}); split the graph")
    # Authored row-order pins (a transform child's inherited figure) outrank
    # the barycenter's fresh crossing minimum — order continuity IS the law;
    # a fresh compose without pins keeps the sweep byte-identical.
    pins = resolve_layout_pins(spec)
    orders = pinned_orders(n, rank, pins) if pins is not None else barycenter_orders(n, flow_edges, rank)
    max_per_rank = layout_cap(caps, ctx.slug, "max_per_rank", 4)
    for r, members in orders.items():
        if len(members) > max_per_rank:
            raise DiagramCapacityError(
                f"{ctx.slug} caps at {max_per_rank} nodes per rank (rank {r} has {len(members)})"
            )
    skips = [e for e in flow_edges if rank[e.target] - rank[e.source] >= 2]
    max_skip_edges = layout_cap(caps, ctx.slug, "max_skip_edges", 3)
    if len(skips) > max_skip_edges:
        raise DiagramCapacityError(f"{ctx.slug} caps at {max_skip_edges} rank-skipping edges (got {len(skips)})")
    # Per-node boxes in per-rank columns (dag specimens): every card solves its
    # OWN box (a rank's crown enlarges through its content while its
    # siblings stay small — the uniform max-box sized every std card to the
    # hero and collapsed the hero/std ratio to 1.0); each rank column takes
    # its widest member, and members center within their column.
    # A FACE MUST BE LONG ENOUGH TO SEAT ITS OWN PORTS. Destination-monotonic
    # ordering is planar only while each neighbour's slot holds the conduit it
    # carries; squeezed onto a short face the slots interleave and the
    # ordering buys nothing. So the band each conduit-bearing face needs is
    # computed here and folded into that node's height FLOOR — content still
    # wins wherever it is taller, and with the dialogue seats at 0.25/0.75 the
    # lane gap is its own small floor, so the residual is a few px rather than
    # the 50+ the stacked-pill gap used to demand.
    _lane_gaps = _conduit_lane_gaps(ctx, axis, edges)
    port_band = _conduit_port_band(ctx, axis, edges, ctx.lanes, _lane_gaps, rank)
    boxes: dict[int, tuple[float, float]] = {}
    for i, node in enumerate(spec.nodes):
        style = style_of(node, ctx.spec, ch)
        if style == NodeStyle.GLYPH_CIRCLE.value:
            # Role-derived (mismatch #5, FIXED): the reserved slot measures
            # with the same chassis/radius the placement renders.
            w, h, _ = solve_node_box(ctx, node, i)
        else:
            w, h, _ = solve_node_box(ctx, node, i, h_floor=port_band.get(i))
        boxes[i] = (w, h)
    # Aligned rank columns (kit law: widths even only within stacked columns —
    # the service-dependencies specimen carries three column widths in one
    # file): each rank's std cards share that COLUMN's widest content-driven
    # box, never the whole graph's (a trivial rank must not inherit a distant
    # rank's long labels). Heights re-solve at the shared width so wrapped
    # descs stay in-card. Containers are excluded — a nested canvas is not a
    # column vote.
    fam_col: set[int] = set()  # members of marked rank columns (the column law)
    for members in orders.values():
        col_ids = [
            i
            for i in members
            if spec.nodes[i].role is not NodeRole.HERO
            and spec.nodes[i].embed is None
            and style_of(spec.nodes[i], ctx.spec, ch) != NodeStyle.GLYPH_CIRCLE.value
        ]
        if not col_ids:
            continue
        fam = len(col_ids) >= 2 and family_carries_marks(ctx, [spec.nodes[i] for i in col_ids])
        if fam:
            # Mixed-family column law: markless members re-measure at the
            # column's glyph lead BEFORE the max, so the shared width
            # already holds their column-indented text.
            fam_col.update(col_ids)
            for i in col_ids:
                boxes[i] = solve_node_box(ctx, spec.nodes[i], i, family_marked=True)[:2]
        col_w = max(boxes[i][0] for i in col_ids)
        for i in col_ids:
            _w2, h2, _ = solve_node_box(ctx, spec.nodes[i], i, min_w=col_w, family_marked=fam)
            boxes[i] = (col_w, h2)
    # The crown solves SNUG (snug-width ruling): its own content + the
    # anchor envelope; ``hero.w``/``hero_min_w`` citations only bound growth
    # as ceilings. Heights: an EXPLICIT ``hero.h`` citation (``hero_declared``
    # — cicd-gate pins its specimen's 210-wide deploy) is a hard floor;
    # undeclared, the hero floors at the family's widest column (width
    # dominance) and content-solves PURE on height — never the std chassis
    # height (a "fulfill / ship it" crown no longer ships half empty, and an
    # uncited crown no longer inherits a dimension that was never its own).
    for i, node in enumerate(spec.nodes):
        if node.role is not NodeRole.HERO:
            continue
        if style_of(node, ctx.spec, ch) == NodeStyle.GLYPH_CIRCLE.value or node.embed:
            continue
        # Compose, never replace: the crown keeps its own content floor and
        # also has to seat its ports.
        _floor = max(hero_height_floor(ch), port_band.get(i, 0.0))
        w, h, _ = solve_node_box(ctx, node, i, h_floor=_floor)
        boxes[i] = (w, h)
    # From here the solve is in MAJOR/MINOR terms: ranks advance along the
    # major axis, a rank's members spread along the minor. RIGHT is the
    # identity map, so every expression below reduces to exactly what the
    # horizontal cell computed before the axis existed — byte parity depends
    # on that, which is why these are renames and accessor swaps only, never
    # reassociated arithmetic.
    rank_ext = {r: max(axis.box_major(*boxes[i]) for i in members) for r, members in orders.items()}
    ranks_sorted = sorted(orders)

    # Gather-join trunks are ADDITIVE room (primer_diagram_language): a rank whose
    # gather node collects >=2 converging edges seats its knot+trunk in space BEYOND
    # the rank gap, so the convergence fan opens at the same span as the preceding
    # fan-out. Carving the trunk out of a uniform gap (the old model) left the
    # convergence curve half the departure's horizontal room — the pinched lens.
    base_trunk = float(ch.join_trunk or 0)
    gather_trunk: dict[int, float] = {}
    if base_trunk:
        for t, node in enumerate(spec.nodes):
            if not node.gather:
                continue
            incoming = [e for e in edges if e.target == t and e.source != t and rank[t] - rank[e.source] < 2]
            if len(incoming) < 2:
                continue
            # Cargo rule: a chipless join collapses FLUSH (join_trunk_bare,
            # default 0) — reserve additive rank room only for the trunk the
            # join will actually draw.
            if not any(e.label for e in incoming):
                trunk = float(ch.join_trunk_bare or 0)
            else:
                # Reserve what the join will draw: a grounded (<4 spoke)
                # join floors its stub at the on-line law — mirror of the
                # knot_collapse sizing below, or the knot crowds the gap.
                reserve_stub = _join_chip_stub(ctx) if len(incoming) >= 4 else max(_join_chip_stub(ctx), CHIP_STUB_MIN)
                trunk = max(base_trunk, chip_run_min(incoming, ctx.cfg, stub=reserve_stub))
            if trunk:
                gather_trunk[rank[t]] = max(gather_trunk.get(rank[t], 0.0), trunk)
    # Mirror for DEPART sources (frontier-serving's hub): a gather node that FANS
    # OUT to >=2 next-rank targets seats its depart trunk ADDITIVELY too, so the
    # fan-OUT opens at the same span as the following convergence. The join loop
    # above defended only one side, leaving a gather HUB's fan-out pinched (the
    # lens, recurring on a DAG): its trunk got carved out of a normal gap (~76px
    # left, steep) while the join got additive room (~150px left, gentle). Room
    # lands on the gap INTO the source's next rank (same key the join writes) and
    # matches the trunk the depart call site carves: max(depart_trunk, chip_run).
    depart_base = float(ch.depart_trunk or 0)
    for sidx, node in enumerate(spec.nodes):
        if not node.gather:
            continue
        outgoing = [e for e in edges if e.source == sidx and e.target != sidx and rank[e.target] - rank[sidx] == 1]
        if len(outgoing) < 2:
            continue
        # Cargo rule, same as the join loop above: a chipless depart draws
        # NO stub (flush at the mouth), so it reserves no additive room —
        # only a trunk that will actually carry a chip earns rank space.
        if not any(e.label for e in outgoing):
            trunk = float(ch.depart_trunk_bare or 0)
        else:
            trunk = max(depart_base, chip_run_min(outgoing, ctx.cfg, stub=_GATHER_STANDOFF))
        if trunk:
            gather_trunk[rank[sidx] + 1] = max(gather_trunk.get(rank[sidx] + 1, 0.0), trunk)

    # Balance law (primer_diagram_language, router pitch 118 on h60):
    # rank pitch = card height + row_gap (gap ≈ card height), floored at the
    # chassis pitch — and the CANVAS grows to hold the tallest rank. The old
    # fixed-height clamp compressed a 4-member rank to ~10px gaps (the
    # squished-fan read).

    # ONE pitch for the whole figure, not one per rank. The cross-axis extent
    # a pitch is built from is the card's HEIGHT flowing right and its WIDTH
    # flowing down — and those two behave completely differently. The card
    # anatomy fixes height, so flowing right every rank computes the same
    # pitch and the ranks land on a shared grid for free; width follows the
    # label text, so flowing down every rank computes its OWN pitch and
    # nothing lines up with anything. Measured: request-to-pod solves rank
    # pitches 178 and 170, putting a probe 4px off the pod it feeds — enough
    # to lose a straight run to the flush test; cache-aside-mesh solves 166
    # and 218, so a sink's own feeders never sit on its column and the
    # convergence that reads as one mouth flowing right reads as two spread
    # arrivals flowing down.
    #
    # The grid is the point of a layered graph, so the pitch is a property of
    # the FIGURE. Taking the max keeps every rank's own boxes clear.
    def _grid_pitch() -> float:
        """Only ranks that actually SPACE members set the grid. A one-member
        rank never uses its pitch to position anything, so letting it into the
        max lets a tall hero dictate the spread of a fan it does not belong
        to — frontier-serving's crown pushed its three providers from 118 to
        146 apart and grew the canvas 65px to hold air nobody asked for."""
        return max(
            (
                max(ch.rank_pitch_max, max(axis.box_minor(*boxes[i]) for i in ms) + ch.row_gap)
                for ms in (_grid(m) for m in orders.values())
                if len(ms) > 1
            ),
            default=float(ch.rank_pitch_max),
        )

    def _rank_pitch(members: list[int]) -> float:
        return _grid_pitch()

    # Out-of-band LANE members (the gateway hand file's metrics): a sink
    # whose EVERY inbound edge is a bottom-exit, west-entry under-channel
    # route (and that feeds nothing downstream) belongs to the telemetry
    # lane, not the rank grid — the hand file seats metrics' center ON the
    # channel (its west face at the flat run's own height, one corner, no
    # rise), while kv-cache alone holds the spine. Lane members keep their
    # rank COLUMN (x) but take their y from the channel after it solves.
    def _is_lane_member(t: int) -> bool:
        inbound = [e for e in edges if e.target == t and e.source != t]
        if not inbound or any(e.source == t for e in edges):
            return False
        return all(
            rank[t] - rank[e.source] >= 2 and e.exit == axis.channel_far and e.entry == axis.entry_side for e in inbound
        )

    lane_members = frozenset(t for t in range(n) if _is_lane_member(t))

    def _grid(members: list[int]) -> list[int]:
        return [m for m in members if m not in lane_members]

    # Flow-axis gap. Flowing right it is the flat chassis constant: the cards
    # are WIDE along the flow, so a fixed gap reads proportionate. Flowing down
    # the cards are SHORT along the flow, and a flat gap that suits a wide fan
    # leaves a straight chain swimming in dead air — the same 166 that a 3-wide
    # fan needs to bow through is 2.5x the card between two stacked boxes.
    #
    # So the vertical chassis derives it from the CROSS-AXIS SPREAD the edges
    # into a rank must actually cover, which is what the travel was ever paying
    # for. Both ends are cited: the ratio reproduces the bare specimen exactly
    # (its outer worker sits 240 off the centre thread and its travel is 166 —
    # 166/240 = 0.6917), and the floor is pipeline-vertical's own straight-stack
    # gap (74), the repo's only cited vertical run with nothing to bow around.
    spread_ratio = float(getattr(ch, "rank_gap_spread_ratio", 0.0) or 0.0)
    gap_floor = float(getattr(ch, "rank_gap_min", 0.0) or 0.0)

    def _rows_relative() -> dict[int, float]:
        """Every rank's rows, solved about a zero mid.

        Rows have to come BEFORE gaps, because a gap is sized for the bows
        that cross it and a bow's cross travel is only known once the rows are
        snapped. Nothing here reads a major coordinate — ``_lane_rows`` only
        ever asks where the previous rank sat ACROSS the flow — so the two can
        be separated. Solving about zero rather than ``minor_mid`` is safe for
        the same reason it is useful: a gap is sized from DIFFERENCES, and a
        shared origin cancels out of every one of them."""
        rows: dict[int, float] = {}
        for r in ranks_sorted:
            gm = _grid(orders[r])
            if not gm:
                continue
            k = len(gm)
            p = _rank_pitch(gm) if k > 1 else 0.0
            prov = {m: (i - (k - 1) / 2) * p for i, m in enumerate(gm)}
            rows.update(_lane_rows(gm, prov, p, edges, rank, rows, spec.nodes))
        return rows

    def _cross_travel(rows: Mapping[int, float], prev_r: int, r: int) -> float:
        """The widest bow that crosses this gap — MEASURED over the edges that
        actually cross it, not inferred from the two ranks' half-spans.

        The half-span sum assumes both ranks centre on the same axis, and a
        lane snap is precisely the thing that breaks that: a one-member rank
        pulled onto its source's column contributes a half-span of ZERO while
        its own outbound edge still has to reach the far member of the next
        rank. request-to-pod sized a gap for 89px of spread and then drew a bow
        across 178 — the same quantity, measured two different ways, and the
        gap was built on the wrong one.

        Only edges that actually BOW count. An authored elbow crosses the same
        two ranks but routes orthogonally — out the far face, along the outside
        gutter, back in through the target's side — on tight fixed-radius
        fillets that consume no rank gap whatever. Measuring its cross
        DISPLACEMENT as if it were a bow is the same category error one level
        up: dag-mesh-billing's `writes` runs 552px across, and sizing the gap
        for it opened 720px of dead air between two rank rows that only ever
        needed 184."""
        return max(
            (
                abs(rows[e.target] - rows[e.source])
                for e in edges
                if e.source != e.target
                and rank[e.source] == prev_r
                and rank[e.target] == r
                and e.source in rows
                and e.target in rows
                and not (e.exit == axis.channel_far and e.entry == axis.exit_side)
            ),
            default=0.0,
        )

    # Rank channels must hold their edge-chips + stubs (the chip-run law).
    # Rank channels must hold the chips that RIDE them — a rank-skipping
    # edge's chip rides its own under/over channel run instead, so it never
    # votes here (the gateway hand file's telemetry chip is 78 wide on a
    # 455px channel run; letting it inflate the 92px rank runs stretched
    # every rank gap ~30px past the citation).
    #
    # ...and only the chips that will actually be DRAWN. A chip whose edge
    # bends past `chip_bend_max_dy` hands its label off the wire and becomes a
    # micro-label, so reserving a pill-width run for it books space nothing
    # occupies: order-event-dlq held 219px gaps for a `dead letter` pill it no
    # longer draws — 69px of dead width per gap, and a gap:card ratio of 1.37
    # against the horizontal specimen's 0.90. Rows are already solved above
    # (they never depended on gaps), so the same bend test the edge loop runs
    # is available here.
    _bend_max = float((ctx.engine.get("connector") or {}).get("chip_bend_max_dy", 40))
    _rows_for_gap = _rows_relative()
    _rank_channel_idx = [j for j, e in enumerate(edges) if e.source != e.target and rank[e.target] - rank[e.source] < 2]
    rank_chip_stub = float((ctx.engine.get("region_band") or {}).get("rank_chip_stub", CHIP_STUB_MIN))

    def _lane_at(j: int) -> int:
        return ctx.lanes[j] if j < len(ctx.lanes) else 0

    # A pill rides ACROSS a descending run, so what the gap must hold is its
    # HEIGHT flowing down and its WIDTH flowing right — the same split the
    # annotate pass makes when it decides whether a chip fits at all.
    _down = axis.flow == "down"
    # THE PERIMETER PLAN is decided here, from the same rows the gap
    # reservation reads, and reused verbatim when the routes draw.
    _plan = _channel_plan(ctx, axis, edges, ctx.lanes, _lane_gaps, rank, _rows_for_gap, boxes)
    # A hub whose minor face carries a perimeter slot stack grows ALONG the
    # flow to seat it — the slot-stack law rotated a quarter turn, feeding
    # the same sizing seam. Rows are untouched: the bump moves only the
    # major extent, and rows never read one.
    for _i, _need in sorted(_plan.perim_band.items()):
        _w0, _h0 = boxes[_i]
        if axis.box_major(_w0, _h0) + 0.5 >= _need:
            continue
        if _down:
            _w2, _h2, _ = solve_node_box(ctx, spec.nodes[_i], _i, h_floor=_need)
        else:
            _w2, _h2, _ = solve_node_box(ctx, spec.nodes[_i], _i, min_w=_need, h_floor=port_band.get(_i))
        boxes[_i] = (max(_w0, _w2), max(_h0, _h2))
        rank_ext[rank[_i]] = max(axis.box_major(*boxes[m]) for m in orders[rank[_i]])

    # A channel-routed plain edge's pill rides its own flow leg, priced by
    # the plan — leaving it in the centred full-gap reservation would book
    # the whole gap for a pill that only ever occupies one leg of it.
    # An unrouted (same-row) CONDUIT votes here too, as its labels will
    # actually render: the bare bracket at the run midpoint, so the run must
    # hold the wider label's ink plus the bare-label face clearances — the
    # bare twin of the centred chip figure, through the same function.
    # The same bend verdict the edge loop reaches, available here because the
    # relative rows never depended on gaps: a chip past the bend threshold
    # takes the FLOATED seat downstream, and a floated pill's run need is not
    # a riding pill's (below).
    def _floats_at_reservation(j: int) -> bool:
        e = edges[j]
        return (
            bool(e.label)
            and e.label_style == "chip"
            and e.source != e.target
            and e.source in _rows_for_gap
            and e.target in _rows_for_gap
            and not (ctx.spec.nodes[e.target].gather or ctx.spec.nodes[e.source].gather)
            and not (e.exit == axis.channel_far and e.entry == axis.exit_side)
            and abs(_rows_for_gap[e.target] - _rows_for_gap[e.source]) > _bend_max
        )

    _plain_idx = [j for j in _rank_channel_idx if j not in _plan.routed]

    # ``rank_chip_stub`` (60) is the RIDING-chip citation — a centred 60px
    # pill on a 180px rank channel showing 60px of thread each side — and it
    # is a HORIZONTAL one. Two populations never earn it:
    #   - flowing down, the pill's along-run extent is 26, and booking 60px
    #     of wire beside it is most of why a chipped vertical chain gapped
    #     at 146 where the stack family sits near 63;
    #   - a FLOATED pill hovers clear of the stroke, so the whole thread
    #     stays visible whatever the stubs — its run need is the pill plus
    #     the minimum-anywhere clearance (booking the riding citation for
    #     it is how order-event-dlq's `dead letter` re-opened uniform 219px
    #     gaps against the family's 150 floor).
    # Both take ``chip_stub_min``; the horizontal riding chip keeps its own
    # citation.
    def _chip_floor_into(r: int | None) -> float:
        """The chip-run floor for the gap INTO rank ``r`` — priced by the chips
        that actually cross THAT gap. ``None`` prices the whole graph, for the
        one fallback that has no rank in hand.

        EVERY GAP IS PRICED BY WHAT CROSSES IT. This was a single figure-wide
        maximum, so one chipped edge opened every rank gap to the width its
        pill needed: grid-horizontal-asymmetric carries exactly one chipped
        adjacent-rank edge (`fail`, into rank 3) and drew all FOUR of its gaps
        at 168.4 against a 74 floor — 283px of dead width across three gaps
        that carry no pill at all.

        The rank-gap derivation beside this one already works this way — the
        cross-travel spread is "MEASURED over the edges that actually cross it,
        not inferred". The chip floor simply never got the same treatment."""
        idx = [j for j in _plain_idx if r is None or rank[edges[j].target] == r]
        riding = [_bare_twin(edges[j]) if _lane_at(j) != 0 else edges[j] for j in idx if not _floats_at_reservation(j)]
        floating = [edges[j] for j in idx if _floats_at_reservation(j)]
        return max(
            chip_run_min(riding, ctx.cfg, stub=(CHIP_STUB_MIN if _down else rank_chip_stub), vertical=_down),
            chip_run_min(floating, ctx.cfg, stub=CHIP_STUB_MIN, vertical=_down),
        )

    rank_gap = max(ch.rank_gap, _chip_floor_into(None))
    gap_into: dict[int, float] = {}
    _rows = _rows_for_gap if spread_ratio else {}
    for idx, r in enumerate(ranks_sorted):
        if idx == 0:
            continue
        if spread_ratio:
            spread = _cross_travel(_rows, ranks_sorted[idx - 1], r)
            # The RESERVATION — the chip-run floor — participates
            # unconditionally: a cited floor must never sit under the run a
            # pill needs. ``ch.rank_gap``
            # does NOT: on a chassis that cites a spread derivation, the
            # flat gap is "retained as the fan-case reference; the
            # derivation governs" (its own comment), and letting it back in
            # through this max pinned every vertical gap at the horizontal
            # 166 — a straight vertical chain swimming in exactly the dead
            # air the derivation exists to remove, measured 166 against its
            # own cited 74 floor.
            gap_into[r] = max(gap_floor, spread_ratio * spread, _chip_floor_into(r))
        else:
            gap_into[r] = max(ch.rank_gap, _chip_floor_into(r))
    # TWO REGIONS IN A ROW need a boundary wide enough for both their pads: the
    # earlier one's trailing pad, the later one's leading pad, and the family's
    # air. Priced here, before placement, because a region's pads are a
    # function of its kind and the flow — never of where its cards land.
    #
    # Without it the pads simply cross: rag-index-and-query flowing down trails
    # its band by 38 into an enclosure that leads by 56, against a 74px rank
    # gap, so the two frames overlap 20px with every member cleanly separated.
    # That is not an author's error and must not be diagnosed as one — it is a
    # gap the solver never opened.
    for r, need in flow_gap_reservation(
        ctx.spec,
        {n.id: rank[i] for i, n in enumerate(ctx.spec.nodes) if n.id},
        flow=axis.flow,
        rb=ctx.engine.get("region_band") or {},
    ).items():
        if r in gap_into:
            gap_into[r] = max(gap_into[r], need)
    span = sum(rank_ext.values()) + sum(gap_into.values()) + sum(gather_trunk.values())

    minor_needed = max(
        (
            (len(_grid(members)) - 1) * _rank_pitch(_grid(members))
            + max(axis.box_minor(*boxes[i]) for i in _grid(members))
            for members in orders.values()
            if _grid(members)
        ),
        default=axis.box_minor(ch.node.w, ch.node.h),
    )
    # An exit:top skip runs an over-the-content channel (the specimen routes a
    # long cross-rank skip OVER the cards, chip on the top run); reserve a top
    # band so the cards clear it, mirroring the below-canvas skip channel.
    _has_top_skip = any(e.exit == axis.channel_near and rank[e.target] - rank[e.source] >= 2 for e in edges)
    top_reserve = max(ch.skip_drop, 60.0) if _has_top_skip else 0.0
    # Chrome is the ONE thing that does not transpose: the masthead band and
    # the caption sit at the top and bottom of the SCREEN whichever way the
    # graph flows, so they always consume the VERTICAL axis. Flowing right
    # that is the minor axis (the branch below is the horizontal cell's
    # original arithmetic, preserved term for term); flowing down it is the
    # major axis, so the rank run starts below the header while the members'
    # spread takes the plain side margins instead.
    #
    # Content-fit law, either way: the chassis dimension floors the canvas
    # only where the chassis declares a fixed frame — otherwise a sparse dag
    # hugs its own span (canvas + scale follow in finish_layout).
    chrome_reserve = ch.header_h + top_reserve + ch.footer_h
    if axis.flow == "right":
        major_total = int(max(ch.width if ch.width_floor else 0, 2 * ch.margin_x + span))
        minor_total = max(ch.height or 360, int(chrome_reserve + minor_needed))
        minor_mid = (ch.header_h + top_reserve + minor_total - ch.footer_h) / 2
        major_origin = float(ch.margin_x)
    else:
        major_total = max(ch.height or 360, int(chrome_reserve + span))
        minor_total = int(max(ch.width if ch.width_floor else 0, 2 * ch.margin_x + minor_needed))
        minor_mid = minor_total / 2
        major_origin = float(ch.header_h + top_reserve)
    # What sits outside the content on the FAR minor side — the caption band
    # flowing right, a plain side margin flowing down. The channels clear it.
    minor_far_chrome = float(ch.footer_h if axis.flow == "right" else ch.margin_x)
    width, height = (int(v) for v in axis.point(major_total, minor_total))
    placed: dict[int, NodePlacement] = {}
    major_cursor = major_origin
    # The extra canvas past the natural span splits evenly into the gaps so
    # a chassis-floored banner still reads centered.
    slack = max(0.0, major_total - 2 * ch.margin_x - span)
    slack_each = slack / (n_ranks - 1) if n_ranks > 1 else 0.0
    if n_ranks == 1:
        major_cursor += slack / 2
    lane_cx: dict[int, float] = {}
    clearance = float(ctx.engine.get("min_clearance", 18))
    for idx, r in enumerate(sorted(orders)):
        # The gap INTO this rank; a gather-join rank takes its trunk ADDITIVELY
        # over the shared eff_gap so the convergence fan mirrors the departure.
        if idx > 0:
            major_cursor += gap_into.get(r, rank_gap) + slack_each + gather_trunk.get(r, 0.0)
        members = orders[r]
        grid_members = _grid(members)
        k = len(grid_members)
        col_ext = rank_ext[r]
        pitch = _rank_pitch(grid_members) if k > 1 else 0.0
        provisional = {m: minor_mid + (i - (k - 1) / 2) * pitch for i, m in enumerate(grid_members)}
        rows = _lane_rows(
            grid_members,
            provisional,
            _rank_pitch(grid_members) if grid_members else 0.0,
            edges,
            rank,
            {i: _minor_center(axis, p) for i, p in placed.items()},
            spec.nodes,
        )
        for node_index in grid_members:
            w, h = boxes[node_index]
            cx, cy = axis.point(major_cursor + col_ext / 2, rows[node_index])
            placed[node_index] = _place_dag_node(
                ctx, node_index, spec.nodes[node_index], cx, cy, w, h, family_marked=node_index in fam_col
            )
        for node_index in members:
            if node_index in lane_members:
                # Seated after the channel solves — remember the rank position only.
                lane_cx[node_index] = major_cursor + col_ext / 2
        major_cursor += col_ext
    # A monotone snap chain can push a conflict loser past the pre-solve rank
    # extent; grow the canvas exactly as the lane-member seat does rather than
    # letting a row ride the footer.
    if placed:
        deepest_grid = max(_minor_far(axis, p) for p in placed.values())
        minor_total = max(minor_total, int(deepest_grid + clearance + minor_far_chrome))
    in_degree: dict[int, int] = {}
    for e in edges:
        in_degree[e.target] = in_degree.get(e.target, 0) + 1
    # Region bands (gateway-balanced's MODEL POOL) built NOW, ahead of their
    # one other consumer (finish_layout's lane_bands, below) — the under-
    # channel below needs each band's own bottom edge (a band's pad extends
    # PAST its deepest member card, so a channel cleared only against
    # deepest_box still crosses the band's own hairline: the gateway-balanced
    # telemetry defect).
    bands, region_notes = build_region_bands(ctx, boxes_by_id(ctx.spec, placed), axis)
    # The under-channel must be where the edge ACTUALLY runs (G7): a single
    # cubic with controls at the channel never reaches it (~75% depth) and
    # grazes rank boxes. Three segments — dive, flat run ON the channel,
    # rise — keep clearance true; channels stack DOWNWARD and the canvas
    # grows to hold them.
    deepest_box = max((_minor_far(axis, p) for p in placed.values()), default=0.0)
    # A band's OUTLINE is a chip-seat obstacle too (annotate.py's
    # band_chip_clearance) — the under-channel a chip rides must clear the
    # band by the same specimen-cited margin PLUS the chip's own half-height
    # (CHIP_H/2), so a chip centered on the channel (never pushed off its
    # wire — kit piece 7) inherits the full clearance, not just the wire.
    deepest_band = max(
        (axis.minor_of(b.box.x + b.box.w, b.box.y + b.box.h) for b in bands if b.ground in ("panel", "enclosure")),
        default=0.0,
    )
    band_clearance = float((ctx.engine.get("region_band") or {}).get("band_chip_clearance", 20)) + CHIP_H / 2

    # A chip riding the channel needs the channel itself clear by the chip's
    # own half-extent ACROSS it — which is the pill's HEIGHT on a horizontal
    # channel but its WIDTH on a vertical one. The bare +4 covers a 13px half
    # height and nothing like a 42px half width, so a vertical channel chip
    # clipped whatever card sat nearest the far side.
    # ``near=None`` is every skip chip — the shipped far-channel set, kept
    # whole. Scoping it to far-only would be tighter (a chip rides one channel,
    # never both) but the far channel's depth is not this fix's business and
    # narrowing it moves horizontal artifacts for an unrelated reason. The near
    # channel, which had no reservation at all, asks for its own set.
    def _chip_across(near: bool | None) -> float:
        return max(
            (
                axis.box_minor(chip_run_min([e], ctx.cfg, stub=0.0), CHIP_H)
                for e in edges
                if e.source != e.target
                and rank[e.target] - rank[e.source] >= 2
                and e.label
                and e.label_style == "chip"
                and (near is None or (e.exit == axis.channel_near) is near)
            ),
            default=0.0,
        )

    skip_chip_across = _chip_across(near=None)
    channel_base = max(
        minor_total - minor_far_chrome - ch.skip_drop,
        deepest_box + clearance + max(4.0, skip_chip_across / 2),
        deepest_band + band_clearance,
    )
    # The NEAR channel needs the same reservation and never had one: a flat
    # ``over_arc_clear`` clears a pill lying along the channel and nothing like
    # one standing across it. Same terms as the far channel's — half the chip's
    # across-extent plus its bare +4 floor — and inert flowing right, where the
    # across-extent is CHIP_H (26): max(18, 13 + 4) is 18 exactly.
    near_clear = max(ch.over_arc_clear, _chip_across(near=True) / 2 + 4.0)
    # Seat the lane members now the channel is solved: each takes the channel
    # its own inbound edge will run at (replicating the edge loop's
    # skip_seen ordering below — every non-top skip consumes one slot), so
    # its west face sits exactly at the flat run's height (the hand file's
    # one-corner telemetry entry) and the canvas grows to hold it.
    if lane_members:
        lane_channel: dict[int, float] = {}
        seen = 0
        for e in edges:
            if e.source == e.target or rank[e.target] - rank[e.source] < 2 or e.exit == axis.channel_near:
                continue
            if e.target in lane_members and e.target not in lane_channel:
                lane_channel[e.target] = channel_base + seen * ch.skip_stack
            seen += 1
        for node_index in lane_members:
            w, h = boxes[node_index]
            seat_minor = lane_channel.get(node_index, channel_base)
            cx, cy = axis.point(lane_cx[node_index], seat_minor)
            placed[node_index] = _place_dag_node(
                ctx, node_index, spec.nodes[node_index], cx, cy, w, h, family_marked=node_index in fam_col
            )
            minor_total = max(minor_total, int(seat_minor + axis.box_minor(w, h) / 2 + clearance + minor_far_chrome))
    # Top channel for exit:top skips: above the shallowest card by a clear margin
    # (chip half-height + clearance) so the on-wire pill clears the card row.
    shallowest_box = min((_minor_near(axis, p) for p in placed.values()), default=minor_mid)
    # Fan separation: edges sharing a source (fan-out) or a target (fan-in)
    # must not all leave/land on the SAME edge-center point — that reads as
    # a bundle of overlapping cables. Spread their exit/entry y across the
    # node's edge, ordered by the OTHER endpoint's y so the curves stay
    # untangled (top target = top exit). ``fan_exit_y`` / ``fan_entry_y``
    # return the spread coordinate for edge j.
    # Every card and every band outline, hoisted once: a wire must clear a
    # band's hairline exactly as it clears a card. Placement is final here —
    # the lane members took their channel seats above — so one list serves
    # every detour branch's corridor scan.
    corridor_blockers = [p.box for p in placed.values()] + [band.box for band in bands]
    corridor_pad = clearance + ch.over_arc_r
    _chip_bend_max = float((ctx.engine.get("connector") or {}).get("chip_bend_max_dy", 40))
    # A chip rides STRAIGHT wire — the kit's own law — and the way to honour
    # that on a bending edge is NOT to bend the edge further. The retired
    # construction was a PLATEAU: bow in, flat run for the pill, bow out. It
    # manufactured straightness by adding two shoulders, so a chipped edge and
    # its unchipped sibling left the same face on visibly different shapes —
    # order-event-dlq's kafka fans to reserve and dlq at the same 59px offset
    # and only the labelled one stepped. It fired on ONE edge in the whole
    # corpus, and no hand specimen draws it: every specimen chip
    # (pp-service-deps' `reads`, `direct read`) sits centred on wire that was
    # already straight.
    #
    # So the LABEL steps off the wire instead, which is the shipped THREE
    # HOMES rule — micro-label beside its wire, chip inside its card, caption
    # band at the bottom. A chip that cannot sit on straight wire has no home
    # on that wire. Decided here, on the placed rows, and written onto the ctx
    # because the label style is read downstream by the annotation pass.
    _bent = {
        j
        for j, e in enumerate(edges)
        if e.label
        and e.label_style == "chip"
        and e.source != e.target
        and e.source in placed
        and e.target in placed
        and abs(rank[e.target] - rank[e.source]) == 1
        and not (ctx.spec.nodes[e.target].gather or ctx.spec.nodes[e.source].gather)
        # An authored elbow does not bow between those rows — it goes AROUND,
        # and its chip rides the flat gutter run. Reading its row offset as a
        # bend is the same category error one axis over, and it stripped
        # dag-mesh-billing's `writes` pill off a dead-straight leg.
        and not (e.exit == axis.channel_far and e.entry == axis.exit_side)
        # A duplex channel is judged like any other, and a channel-routed
        # edge is subtracted from the result below: its legs are straight
        # under the seat by construction, so a row offset there is travel a
        # riser already absorbed, not a bend. What remains bent here is the
        # S-curve population on faces without conduits.
        #
        # Both halves of a pair reach this test, because a return is a rank
        # step DOWN and the ``== 1`` check above would only ever see the
        # outbound — one conduit cannot wear two label grammars.
        and (rank[e.target] - rank[e.source] == 1 or (j < len(ctx.lanes) and ctx.lanes[j] != 0))
        and abs(_minor_center(axis, placed[e.target]) - _minor_center(axis, placed[e.source])) > _chip_bend_max
    }
    # AMENDMENT (owner, 2026-08-26, at render review). A bent rank-step chip
    # is no longer DEMOTED to a micro-label; it takes the FLOATED pill seat
    # instead — the pill lifted clear of the bending stroke, which is the
    # frontier-serving cache/telemetry idiom this module's own annotate
    # comment already cites (and the SM back-arcs use). The three-homes rule
    # above is not wrong about a pill's corners over a bending line; it was
    # wrong that the only remaining home was off-wire text. One conduit face
    # should not mix two label grammars when the specimens offer a home for
    # both. The collision case that originally motivated demotion is now
    # guarded from both ends — the collide ladder seats the pill clear, and
    # the planarity gate refuses a render where the wires themselves cross.
    #
    # ``_bent`` is kept: the annotate pass recomputes the same bend test from
    # the geo to decide WHICH chips float, and the rank-gap reservation below
    # now counts them, because a floated pill occupies run where a demoted
    # label did not.
    # A channel-routed edge never floats: its legs are straight under the
    # seat by construction, so its pill RIDES — which is the ruling's §4.
    # The floated seat stays law for genuinely bent single edges on faces
    # without conduits.
    _float_labels = {j for j in _bent if j not in _plan.routed}

    def _own_furniture(*boxes: RectSpec) -> tuple[RectSpec, ...]:
        """The boxes given, plus every enclosure CONTAINING any of them. A
        region is an obstacle for a wire passing by and furniture for one whose
        own endpoints live inside it — rag-index-and-query's query and retrieve
        are both members of the `query time` enclosure, so the straight line
        between them crosses nothing, and treating that enclosure as a wall
        sent the wire down to the channel and back for no reason."""
        out = list(boxes)
        for b in corridor_blockers:
            if any(b is x for x in boxes):
                continue
            if any(b.x <= t.x and b.y <= t.y and b.x + b.w >= t.x + t.w and b.y + b.h >= t.y + t.h for t in boxes):
                out.append(b)
        return tuple(out)

    def _entry_skips(pb: NodePlacement) -> tuple[RectSpec, ...]:
        """What an entry leg is allowed to touch on its way in: the target's
        own box, plus any enclosure CONTAINING it. A band is an obstacle for a
        wire passing by and furniture for one terminating inside it — a leg
        that must enter a band to reach a card seated in it is not crossing
        anything, and detouring it around its own enclosure is the failure a
        flat containment test makes."""
        tb = pb.box
        return (
            tb,
            *(
                b
                for b in corridor_blockers
                if b is not tb and b.x <= tb.x and b.y <= tb.y and b.x + b.w >= tb.x + tb.w and b.y + b.h >= tb.y + tb.h
            ),
        )

    # A skip takes the channel because its DIRECT run would cross the ranks it
    # skips over. Rank distance is a topological stand-in for that geometric
    # question, and where the two disagree the stand-in loses: a probe sitting
    # in the same row as the pod two ranks along, with an empty corridor
    # between them, was sent out of its own face, down, across the floor and
    # back up to re-enter from the side — a detour around nothing.
    #
    # So an aligned skip whose straight run is clear draws the straight run.
    # Scoped tight: no authored routing (an author who names a face means it),
    # rows flush within the cited ``_PORT_FLUSH``, and the run measured
    # against every card and band rather than assumed.
    straight_skips = frozenset(
        j
        for j, e in enumerate(edges)
        if rank[e.target] - rank[e.source] >= 2
        and e.source != e.target
        and not (e.exit or e.entry)
        and abs(_minor_center(axis, placed[e.source]) - _minor_center(axis, placed[e.target])) <= _PORT_FLUSH
        and not _run_blocked(
            axis,
            corridor_blockers,
            minor=_minor_center(axis, placed[e.source]),
            major_lo=_major_center(axis, placed[e.source]),
            major_hi=_major_center(axis, placed[e.target]),
            skip=_own_furniture(placed[e.source].box, placed[e.target].box),
        )
    )

    def _direct_elbow(j: int, e: ResolvedEdge) -> float | None:
        """Major coordinate to turn at, if this skip can reach its target on
        its OWN row instead of diving to the channel.

        Same argument as ``straight_skips`` one step further out. The channel
        exists to get UNDER the ranks a skip bypasses; where the source's own
        row is already clear across the span there is nothing to get under, and
        diving is a detour around nothing. rag-index-and-query's query->retrieve
        left its face, dropped 94px to the deep channel, ran the full 706px
        width down there and climbed 205px back — while the straight line at
        its own row was empty the whole way.

        Returns the target's major centre (the one turn), or None to dive. The
        route stays ORTHOGONAL either way: a skip is a detour and reads as one.
        """
        pa, pb = placed[e.source], placed[e.target]
        s_min = _minor_center(axis, pa)
        t_maj = _major_center(axis, pb)
        near, far = _minor_near(axis, pb), _minor_far(axis, pb)
        face = far if s_min > _minor_center(axis, pb) else near
        if _run_blocked(
            axis,
            corridor_blockers,
            minor=s_min,
            major_lo=_major_center(axis, pa),
            major_hi=t_maj,
            skip=_own_furniture(pa.box, pb.box),
        ):
            return None
        lo, hi = (face, s_min) if face < s_min else (s_min, face)
        if _leg_blockers(
            axis, corridor_blockers, major=t_maj, minor_lo=lo, minor_hi=hi, skip=_own_furniture(pa.box, pb.box)
        ):
            return None
        return t_maj

    def _interior_corridor(e: ResolvedEdge) -> float | None:
        """The clearest free band BETWEEN the source's row and the target's,
        or None to dive to the deep channel.

        The last step of the same argument ``straight_skips`` and
        ``_direct_elbow`` make. Those two ask whether the SOURCE'S OWN row is
        clear; when it is not, the engine's only remaining answer was the deep
        channel — below every card in the figure — so a two-rank hop between
        neighbouring rows left the content band, ran the full width underneath
        and climbed back. A layered dag separates its rows by ``row_gap``, and
        those interior bands are the same free space the deep channel is; the
        engine simply had no name for them.

        Scoped the same way as its two siblings: unauthored routing only, the
        band measured against every card and region rather than assumed, and
        both legs onto it checked. The band must also be wide enough for what
        the wire carries — a chip riding the flat run needs its own height plus
        clearance, not just the wire's.

        Only bands BETWEEN the two rows qualify. Outside that span the wire
        would be travelling away from its own target to find a shortcut, which
        is the detour the deep channel already honestly is."""
        pa, pb = placed[e.source], placed[e.target]
        s_min, t_min = _minor_center(axis, pa), _minor_center(axis, pb)
        lo_maj, hi_maj = sorted((_major_center(axis, pa), _major_center(axis, pb)))
        own = _own_furniture(pa.box, pb.box)
        spans = [
            (axis.minor_of(b.x, b.y), axis.minor_of(b.x + b.w, b.y + b.h))
            for b in corridor_blockers
            if not any(b is x for x in own)
            and axis.major_of(b.x, b.y) < hi_maj
            and axis.major_of(b.x + b.w, b.y + b.h) > lo_maj
        ]
        merged: list[list[float]] = []
        for lo, hi in sorted(spans):
            if merged and lo <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        chipped = bool(e.label and e.label_style == "chip")
        need = max(2 * clearance, CHIP_H + clearance if chipped else 0.0)
        band_lo, band_hi = sorted((s_min, t_min))
        best, best_cost = None, float("inf")
        for i in range(len(merged) - 1):
            gap_lo, gap_hi = merged[i][1], merged[i + 1][0]
            mid = (gap_lo + gap_hi) / 2
            if gap_hi - gap_lo < need or not band_lo <= mid <= band_hi:
                continue
            cost = abs(mid - s_min) + abs(mid - t_min)
            if cost < best_cost:
                best, best_cost = mid, cost
        if best is None:
            return None
        for pl, minor in ((pa, s_min), (pb, t_min)):
            lo, hi = sorted((minor, best))
            if _leg_blockers(
                axis,
                corridor_blockers,
                major=_major_center(axis, pl),
                minor_lo=lo,
                minor_hi=hi,
                skip=_own_furniture(pa.box, pb.box),
            ):
                return None
        return best

    direct_elbows: dict[int, float] = {}
    corridor_runs: dict[int, float] = {}
    for j, e in enumerate(edges):
        if (
            j in straight_skips
            or rank[e.target] - rank[e.source] < 2
            or e.source == e.target
            or (e.exit or e.entry)  # an author who names a face means it
        ):
            continue
        turn = _direct_elbow(j, e)
        if turn is not None:
            direct_elbows[j] = turn
            continue
        corridor = _interior_corridor(e)
        if corridor is not None:
            corridor_runs[j] = corridor
    # Skip edges (rank diff >= 2) run in the under-channel, not a shared port —
    # exclude them from the arrival spread so a plain fan-in keeps its true pitch.
    skip_idx = frozenset(
        j for j, e in enumerate(edges) if rank[e.target] - rank[e.source] >= 2 and j not in straight_skips
    )
    _, fan_entry_y = _fan_spread(edges, placed, axis, skip_edges=skip_idx)  # exits collapse to the center mouth
    conduit_slots, _ = _conduit_face_slots(
        ctx,
        edges,
        {i: _minor_center(axis, p) for i, p in placed.items()},
        {i: axis.box_minor(p.box.w, p.box.h) for i, p in placed.items()},
        axis,
        ctx.lanes,
        _lane_gaps,
        rank,
        _plan.routed,
    )
    # Perimeter slots, resolved to absolute majors: the plan's offsets grow
    # from the hub's major centre, and each riser then clears every card and
    # band in its own span through the one corridor law — sequentially per
    # (hub, side), so a displaced slot can never leap its neighbour and undo
    # the ordering that made the perimeter planar.
    perimeter_x = _resolve_perimeter_slots(
        ctx, axis, edges, placed, _plan, corridor_blockers, clearance, _own_furniture
    )

    # Shared-east-face port stagger: a node that HOSTS an authored elbow entry
    # while also SOURCING a plain east exit would fuse both wires at center-y
    # (~18px shared cable + stacked arrowheads). Part them: exit half a stagger
    # above center, elbow landing half below. Scoped to exactly this collision —
    # the fan attachment law (exits collapse to the center mouth) is untouched
    # for every node not in the set, and an empty set is byte-identical output.
    def _is_authored_elbow(e: ResolvedEdge) -> bool:
        # Leaves by the far channel and re-enters by the face an edge normally
        # EXITS from — the elbow that would otherwise fuse with a plain exit.
        return e.exit == axis.channel_far and e.entry == axis.exit_side

    _elbow_entry_targets = {e.target for e in edges if _is_authored_elbow(e)}
    _plain_exit_sources = {
        e.source
        for j, e in enumerate(edges)
        if e.source != e.target and j not in skip_idx and not _is_authored_elbow(e)
    }
    stagger_faces = _elbow_entry_targets & _plain_exit_sources
    geos: list[EdgeGeo] = []
    plain_by_target: dict[int, list[int]] = {}
    plain_by_source: dict[int, list[int]] = {}
    skip_seen = 0
    skip_top_seen = 0
    deepest_channel = 0.0
    for j, e in enumerate(edges):
        if e.source == e.target:
            # A rank card revisiting itself: the loop bows UP out of the
            # content band (top default; edge.exit overrides).
            geos.append(_self_loop_geo(ctx, j, e, placed[e.source], default_side="top"))
            continue
        pa, pb = placed[e.source], placed[e.target]
        if j in _plan.routed:
            # PERIMETER ROUTING (owner ruling): an off-row track on a
            # conduit-bearing hub leaves by the minor face nearest its
            # partner's side — a fanned pair as a locked dual-lane bus, a
            # plain off-row edge as a single lane — so the flow face keeps
            # only the flush traffic. Same-row edges fall through to their
            # straight grammar below.
            geos.append(_channel_route_geo(ctx, axis, j, e, rank, _plan.routed[j], placed, perimeter_x))
            continue
        if j < len(ctx.lanes) and ctx.lanes[j] != 0:
            # A same-row LOCAL DUPLEX draws as one dual-channel conduit in
            # the corridor between its two cards — both halves adjacent-rank
            # by construction, so neither needs the skip/elbow machinery
            # below. (An off-row pair took the channel route above.)
            geos.append(_duplex_conduit_geo(ctx, axis, j, e, pa, pb, rank, conduit_slots))
            continue
        # Fan-spread both ends into distinct ports so a bundle reads as separate
        # wires, not one overlapping cable. A GATHER target is the exception:
        # its arrivals COLLAPSE to one center mouth where the knot+trunk marks
        # the AND-join (the trunk owns the arrival, so slots[0]'s mouth must
        # stay centered for knot_collapse). Every OTHER shared target (a mesh
        # dependency, a bottleneck) distributes arrivals along its edge — the
        # dep-mesh specimen seats 4 arrivals over 34px so 2+ arrowheads never
        # stack on one point. Anchored on the node's TRUE boundary.
        # Attachment law (primer_diagram_language): a
        # fan LEAVES its source at the edge CENTER — one mouth, separation by
        # curvature, monotone S-curves that cannot cross (the port-spread
        # exits criss-crossed model-gateway's tier curves). Shared non-gather
        # TARGETS keep the dep-mesh arrival spread (that specimen seats 4
        # arrivals over 34px so arrowheads never stack).
        a_minor, b_minor = _minor_center(axis, pa), _minor_center(axis, pb)
        # A plain edge on a conduit-bearing face joins the destination
        # ordering too: holding the centre mouth there cuts across the
        # conduits seated around it.
        a_minor = conduit_slots.get((e.source, e.target), a_minor)
        b_minor = conduit_slots.get((e.target, e.source), b_minor)
        exit_at = a_minor - (ch.port_stagger / 2 if e.source in stagger_faces else 0.0)
        sx, scy = side_anchor(pa, side=axis.exit_side, at=exit_at)
        entry_at = b_minor if ctx.spec.nodes[e.target].gather else fan_entry_y.get(j, b_minor)
        tx, tcy = side_anchor(pb, side=axis.entry_side, at=entry_at)
        if rank[e.target] - rank[e.source] >= 2 and j not in straight_skips:
            if j in direct_elbows:
                # The skip reaches its target on its own row: run the row to
                # the target's column, one fillet, in through the face the
                # wire arrives at. Orthogonal like every detour — the channel
                # is the FALLBACK for a blocked row, not the default.
                turn = direct_elbows[j]
                s_major, s_minor = axis.major_of(sx, scy), axis.minor_of(sx, scy)
                t_center = _minor_center(axis, pb)
                face = _minor_far(axis, pb) if s_minor > t_center else _minor_near(axis, pb)
                sgn = 1.0 if turn >= s_major else -1.0
                dirn = 1.0 if face >= s_minor else -1.0
                elbow_r = min(ch.over_arc_r, abs(turn - s_major) / 2, abs(face - s_minor) / 2)
                d = (
                    f"M {_pt(axis, s_major, s_minor)} "
                    f"L {_pt(axis, turn - sgn * elbow_r, s_minor)} "
                    f"Q {_pt(axis, turn, s_minor)} {_pt(axis, turn, s_minor + dirn * elbow_r)} "
                    f"L {_pt(axis, turn, face)}"
                )
                sx_d, sy_d = axis.point(s_major, s_minor)
                tx_d, ty_d = axis.point(turn, face)
                geos.append(
                    EdgeGeo(
                        index=j,
                        d=d,
                        sx=sx_d,
                        sy=sy_d,
                        tx=tx_d,
                        ty=ty_d,
                        length=abs(turn - s_major) + abs(face - s_minor),
                        label_pos=axis.point((s_major + turn - sgn * elbow_r) / 2, s_minor),
                        label_bare=True,
                        polyline=(axis.point(s_major, s_minor), axis.point(turn, s_minor), axis.point(turn, face)),
                        end_tangent=axis.point(0.0, dirn),
                    )
                )
                continue
            if j in corridor_runs:
                # INTERIOR CORRIDOR: the same two-turn detour the deep channel
                # draws, run in a free band BETWEEN the two rows instead of
                # under the whole figure. Both faces are chosen by which way
                # the band lies, so the construction serves a corridor above
                # the source as readily as one below it.
                run = corridor_runs[j]
                s_major, s_min = _major_center(axis, pa), _minor_center(axis, pa)
                t_major, t_min = _major_center(axis, pb), _minor_center(axis, pb)
                d_s = 1.0 if run >= s_min else -1.0
                d_t = 1.0 if t_min >= run else -1.0
                s_face = _minor_far(axis, pa) if d_s > 0 else _minor_near(axis, pa)
                t_face = _minor_near(axis, pb) if d_t > 0 else _minor_far(axis, pb)
                sgn = 1.0 if t_major >= s_major else -1.0
                r_s = min(ch.over_arc_r, abs(run - s_face) / 2, abs(t_major - s_major) / 2)
                r_t = min(ch.over_arc_r, abs(t_face - run) / 2, abs(t_major - s_major) / 2)
                d = (
                    f"M {_pt(axis, s_major, s_face)} "
                    f"L {_pt(axis, s_major, run - d_s * r_s)} "
                    f"Q {_pt(axis, s_major, run)} {_pt(axis, s_major + sgn * r_s, run)} "
                    f"L {_pt(axis, t_major - sgn * r_t, run)} "
                    f"Q {_pt(axis, t_major, run)} {_pt(axis, t_major, run + d_t * r_t)} "
                    f"L {_pt(axis, t_major, t_face)}"
                )
                sx_c, sy_c = axis.point(s_major, s_face)
                tx_c, ty_c = axis.point(t_major, t_face)
                geos.append(
                    EdgeGeo(
                        index=j,
                        d=d,
                        sx=sx_c,
                        sy=sy_c,
                        tx=tx_c,
                        ty=ty_c,
                        length=abs(run - s_face) + abs(t_major - s_major) + abs(t_face - run),
                        # The chip rides the FLAT run, the only leg long enough
                        # to seat one — same home the deep channel gives it.
                        label_pos=axis.point((s_major + sgn * r_s + t_major - sgn * r_t) / 2, run),
                        label_bare=True,
                        polyline=(
                            axis.point(s_major, s_face),
                            axis.point(s_major, run),
                            axis.point(t_major, run),
                            axis.point(t_major, t_face),
                        ),
                        end_tangent=axis.point(0.0, d_t),
                    )
                )
                continue
            if e.exit == axis.channel_near:
                # Over-the-near-side skip: leave the source's near face, run an
                # orthogonal channel outside the content band, and come back in
                # at the target's near face — the specimen's cross-rank "direct
                # read" route, its chip riding the channel leg. Crisp L+Q
                # corners (service-dependencies), never a wide cubic sweep: a
                # straight departure, a small over_arc_r quarter turn into the
                # channel, the flat run, a turn back, the return.
                arc_r = ch.over_arc_r
                near_channel = shallowest_box - near_clear - skip_top_seen * ch.skip_stack
                skip_top_seen += 1
                s_major, s_minor = _major_center(axis, pa), _minor_near(axis, pa)
                t_major, t_minor = _major_center(axis, pb), _minor_near(axis, pb)
                sgn = 1.0 if t_major >= s_major else -1.0
                # The return leg descends the target's OWN major column, so a
                # same-rank sibling nearer the channel sits squarely in its
                # path (service-dependencies' Redis over Postgres: both centre
                # on one column, and 66px of wire ran inside the card, hidden
                # only because cards paint after edges). Where that happens the
                # route takes the elbow's corridor instead — carry on past the
                # target, descend outside the column, and come back in through
                # the major face on the side the corridor ran. Unblocked routes
                # keep the straight return exactly.
                if _leg_blockers(
                    axis,
                    corridor_blockers,
                    major=t_major,
                    minor_lo=near_channel,
                    minor_hi=t_minor,
                    skip=_entry_skips(pb),
                ):
                    t_center = _minor_center(axis, pb)
                    face_major = t_major + sgn * axis.box_major(pb.box.w, pb.box.h) / 2
                    turn = _corridor_major(
                        axis,
                        corridor_blockers,
                        major=face_major + sgn * corridor_pad,
                        minor_lo=near_channel,
                        minor_hi=t_center,
                        sgn=sgn,
                        pad=corridor_pad,
                        clearance=clearance,
                    )
                    r_in = min(arc_r, abs(turn - face_major) / 2, (t_center - near_channel) / 2)
                    d = (
                        f"M {_pt(axis, s_major, s_minor)} "
                        f"L {_pt(axis, s_major, near_channel + arc_r)} "
                        f"Q {_pt(axis, s_major, near_channel)} {_pt(axis, s_major + sgn * arc_r, near_channel)} "
                        f"L {_pt(axis, turn - sgn * r_in, near_channel)} "
                        f"Q {_pt(axis, turn, near_channel)} {_pt(axis, turn, near_channel + r_in)} "
                        f"L {_pt(axis, turn, t_center - r_in)} "
                        f"Q {_pt(axis, turn, t_center)} {_pt(axis, turn - sgn * r_in, t_center)} "
                        f"L {_pt(axis, face_major, t_center)}"
                    )
                    length = (
                        (s_minor - near_channel)
                        + abs(turn - s_major)
                        + (t_center - near_channel)
                        + abs(turn - face_major)
                    )
                    sx_t, sy_t = axis.point(s_major, s_minor)
                    tx_t, ty_t = axis.point(face_major, t_center)
                    geos.append(
                        EdgeGeo(
                            index=j,
                            d=d,
                            sx=sx_t,
                            sy=sy_t,
                            tx=tx_t,
                            ty=ty_t,
                            length=length,
                            end_tangent=axis.point(-sgn, 0.0),
                        )
                    )
                    continue
                d = (
                    f"M {_pt(axis, s_major, s_minor)} "
                    f"L {_pt(axis, s_major, near_channel + arc_r)} "
                    f"Q {_pt(axis, s_major, near_channel)} {_pt(axis, s_major + sgn * arc_r, near_channel)} "
                    f"L {_pt(axis, t_major - sgn * arc_r, near_channel)} "
                    f"Q {_pt(axis, t_major, near_channel)} {_pt(axis, t_major, near_channel + arc_r)} "
                    f"L {_pt(axis, t_major, t_minor)}"
                )
                length = (s_minor - near_channel) + abs(t_major - s_major) + (t_minor - near_channel)
                sx_t, sy_t = axis.point(s_major, s_minor)
                tx_t, ty_t = axis.point(t_major, t_minor)
                geos.append(EdgeGeo(index=j, d=d, sx=sx_t, sy=sy_t, tx=tx_t, ty=ty_t, length=length))
                continue
            # An UNAUTHORED skip takes the bottom-face family too (owner
            # ruling, 2026-08-27): a detour's whole job is to get under the
            # ranks it bypasses, and the far-face route does it in TWO turns —
            # out the far face, along the channel, up into the target's far
            # face — where the old flow-face default spent FOUR turns plus a
            # stub-jog off the face it left by. The flow-face five-leg route
            # remains only for the authored entry-without-exit combination,
            # where the author named the arrival face and means it.
            if e.exit == axis.channel_far or not (e.exit or e.entry):
                s_major, s_far = _major_center(axis, pa), _minor_far(axis, pa)
                sx_b, sy_b = axis.point(s_major, s_far)
                t_major, t_minor = axis.major_of(tx, tcy), axis.minor_of(tx, tcy)
                if e.entry == axis.entry_side:
                    # Bottom-exit, WEST-entry (gateway-balanced telemetry):
                    # dive from the source's bottom, one L+Q corner from
                    # vertical to horizontal at the channel depth, then a
                    # flat run straight into the target's west face —
                    # pp-gateway-balanced.svg's own telemetry: M 427,31 L
                    # 427,149 Q 427,156 434,156 L 889,156 (the channel sits
                    # AT the target's own entry height, so one corner
                    # suffices). Where the channel sits BELOW the target's
                    # own entry height (channel > t_minor — a shallower target
                    # that doesn't reach the deep-content clearance line),
                    # the flat run at ``channel`` would pass under the face
                    # and never arrive: a second and third corner carry it
                    # back UP to ``t_minor`` before a final flat entry, the two
                    # corners' own radius shrinking to fit whenever the rise
                    # itself is tighter than the standard ``arc_r``.
                    #
                    # The floor is ``t_minor``, NOT ``tcy``. A channel lives in
                    # MINOR space; ``tcy`` is a screen y, which is the minor
                    # coordinate flowing right and the MAJOR one flowing down.
                    # Reading it raw is invisible horizontally (the two are the
                    # same number) and flowing down it floors the channel
                    # against a rank position — so the lane member parked ON
                    # the channel and the edge solved a different one, and the
                    # route turned back inward to reach a sink already waiting
                    # for it.
                    arc_r = ch.over_arc_r
                    channel = max(channel_base + skip_seen * ch.skip_stack, t_minor)
                    deepest_channel = max(deepest_channel, channel)
                    skip_seen += 1
                    sgn = 1.0 if t_major >= s_major else -1.0
                    rise = channel - t_minor
                    if rise <= 0.05:
                        d = (
                            f"M {_pt(axis, s_major, s_far)} "
                            f"L {_pt(axis, s_major, channel - arc_r)} "
                            f"Q {_pt(axis, s_major, channel)} {_pt(axis, s_major + sgn * arc_r, channel)} "
                            f"L {_pt(axis, t_major, channel)}"
                        )
                        length = (channel - arc_r - s_far) + abs(t_major - s_major)
                        label_pos = axis.point((s_major + sgn * arc_r + t_major) / 2, channel)
                        polyline: tuple[tuple[float, float], ...] = (
                            axis.point(s_major, s_far),
                            axis.point(s_major, channel),
                            axis.point(t_major, channel),
                        )
                    else:
                        rise_r = min(arc_r, rise / 2)
                        end_stub = max(rise_r, 12.0)
                        rise_x = t_major - sgn * (rise_r + end_stub)
                        d = (
                            f"M {_pt(axis, s_major, s_far)} "
                            f"L {_pt(axis, s_major, channel - arc_r)} "
                            f"Q {_pt(axis, s_major, channel)} {_pt(axis, s_major + sgn * arc_r, channel)} "
                            f"L {_pt(axis, rise_x - sgn * rise_r, channel)} "
                            f"Q {_pt(axis, rise_x, channel)} {_pt(axis, rise_x, channel - rise_r)} "
                            f"L {_pt(axis, rise_x, t_minor + rise_r)} "
                            f"Q {_pt(axis, rise_x, t_minor)} {_pt(axis, rise_x + sgn * rise_r, t_minor)} "
                            f"L {_pt(axis, t_major, t_minor)}"
                        )
                        length = (channel - arc_r - s_far) + abs(t_major - s_major) + rise
                        label_pos = axis.point((s_major + sgn * arc_r + rise_x - sgn * rise_r) / 2, channel)
                        polyline = (
                            axis.point(s_major, s_far),
                            axis.point(s_major, channel),
                            axis.point(rise_x, channel),
                            axis.point(rise_x, t_minor),
                            axis.point(t_major, t_minor),
                        )
                    # The chip seats on the FLAT channel leg — without a
                    # solver seat the balance rule falls back to the
                    # straight chord, which the L-shaped route never touches.
                    geos.append(
                        EdgeGeo(
                            index=j,
                            d=d,
                            sx=sx_b,
                            sy=sy_b,
                            tx=tx,
                            ty=tcy,
                            length=length,
                            label_pos=label_pos,
                            label_bare=True,
                            polyline=polyline,
                        )
                    )
                    continue
                # Below-canvas skip on the BOTTOM faces (the model-gateway and
                # frontier-serving telemetry routes): leave the source's
                # bottom, run the deep channel, rise into the target's bottom.
                # Detour law: edge geometry is per-edge-class — relational
                # edges own the bow family; a detour route is ORTHOGONAL:
                # straight legs joined by tight fixed-radius quarter-turn
                # fillets (``ch.over_arc_r``), never a corner-consuming cubic
                # (the retired construction swept the ENTIRE drop as one
                # bezier and read as a relational curve). The gateway hand
                # file's own telemetry pins the family: M 457,31 L 457,150
                # Q 457,157 464,157 L 1154,157 Q 1161,157 1161,150 L 1161,78 —
                # drop leg, r=7 fillet, flat run, r=7 fillet, rise leg. The
                # fillet is a fixed px value, never a fraction of run length;
                # legs shorter than the diameter shrink their own corner
                # (the orthogonal_d discipline).
                channel = channel_base + skip_seen * ch.skip_stack
                deepest_channel = max(deepest_channel, channel)
                skip_seen += 1
                t_major_f, t_far = _major_center(axis, pb), _minor_far(axis, pb)
                tx_b, ty_b = axis.point(t_major_f, t_far)
                sgn = 1.0 if t_major_f >= s_major else -1.0
                # BOTH legs off the channel run down a card's own major column,
                # and each can be standing behind a same-rank sibling — the
                # drop behind one deeper than the source, the rise behind one
                # deeper than the target. They displace independently through
                # the one corridor: a route can need neither, either, or both.
                s_center = _minor_center(axis, pa)
                drop_major, drop_from = s_major, s_far
                if _leg_blockers(
                    axis, corridor_blockers, major=s_major, minor_lo=s_far, minor_hi=channel, skip=_entry_skips(pa)
                ):
                    # Leave by the flow face and dive clear of the column —
                    # the default under-route's own opening, which exists for
                    # exactly this reason.
                    #
                    # STAGGER OFF THE MOUTH. That flow face is where the plain
                    # edges leave too, and they leave at its CENTRE by the
                    # attachment law (one mouth, separation by curvature). A
                    # displaced drop leaving the same centre put two wires on
                    # one point — monorepo-build-graph drew typecheck's two
                    # departures from (552.1, 259.9) and unit's from
                    # (552.1, 382.9), which is the fused cable ``port_stagger``
                    # exists to prevent, one pairing over from the elbow-vs-exit
                    # case it already covers.
                    #
                    # The mouth does not move — it is cited — so the skip takes
                    # the whole step, toward the channel it is about to dive to,
                    # so its first movement is already separation. Clamped
                    # inside the face: on a short card the step must not walk
                    # the departure off its own edge.
                    drop_from = s_center
                    if e.source in _plain_exit_sources:
                        half_face = axis.box_minor(pa.box.w, pa.box.h) / 2 - clearance / 2
                        step = min(float(ch.port_stagger), max(0.0, half_face))
                        drop_from = s_center + (step if channel >= s_center else -step)
                    drop_major = _corridor_major(
                        axis,
                        corridor_blockers,
                        major=_major_center(axis, pa) + sgn * axis.box_major(pa.box.w, pa.box.h) / 2 + corridor_pad,
                        minor_lo=s_center,
                        minor_hi=channel,
                        sgn=sgn,
                        pad=corridor_pad,
                        clearance=clearance,
                    )
                rise_major, land = t_major_f, t_far
                if _leg_blockers(
                    axis, corridor_blockers, major=t_major_f, minor_lo=t_far, minor_hi=channel, skip=_entry_skips(pb)
                ):
                    land = _minor_center(axis, pb)
                    rise_major = _corridor_major(
                        axis,
                        corridor_blockers,
                        major=t_major_f + sgn * axis.box_major(pb.box.w, pb.box.h) / 2 + sgn * corridor_pad,
                        minor_lo=land,
                        minor_hi=channel,
                        sgn=sgn,
                        pad=corridor_pad,
                        clearance=clearance,
                    )
                run = abs(rise_major - drop_major)
                drop_r = min(ch.over_arc_r, (channel - drop_from) / 2, run / 2)
                rise_r = min(ch.over_arc_r, (channel - land) / 2, run / 2)
                # A DISPLACED DROP leaves the source's FLOW face and runs out
                # to its own corridor column before diving. That opening leg
                # has to start ON the card, and it was starting on the corridor
                # column instead — so the wire drew a 7px backwards stub into
                # its own fillet and appeared to begin 25px out in clear space,
                # unattached to anything. The geo's recorded endpoint (``sx_b``
                # below) was right all along; only the drawn path disagreed,
                # which is why nothing downstream caught it.
                s_face_major = _major_center(axis, pa) + sgn * axis.box_major(pa.box.w, pa.box.h) / 2
                # The opening leg runs at the DEPARTURE's own minor, not the
                # card centre: once the drop staggers off the mouth those are
                # different numbers, and reading the centre here bent the leg
                # into a diagonal — an orthogonal family's legs are straight or
                # they are not that family. Identical while the two agree, so
                # an unstaggered drop is byte-for-byte unchanged.
                head = (
                    ""
                    if drop_from == s_far
                    else f"L {_pt(axis, drop_major - sgn * drop_r, drop_from)} "
                    f"Q {_pt(axis, drop_major, drop_from)} {_pt(axis, drop_major, drop_from + drop_r)} "
                )
                # A displaced rise lands on the target's MAJOR face at its
                # centre, so the wire turns in from the side it came around;
                # an undisplaced one keeps the cited straight climb into the
                # far face.
                tail = (
                    f"L {_pt(axis, rise_major, land)}"
                    if land == t_far
                    else f"L {_pt(axis, rise_major, land + rise_r)} "
                    f"Q {_pt(axis, rise_major, land)} {_pt(axis, rise_major - sgn * rise_r, land)} "
                    f"L {_pt(axis, t_major_f + sgn * axis.box_major(pb.box.w, pb.box.h) / 2, land)}"
                )
                d = (
                    f"M {_pt(axis, s_face_major if head else s_major, drop_from)} "
                    f"{head}"
                    f"L {_pt(axis, drop_major, channel - drop_r)} "
                    f"Q {_pt(axis, drop_major, channel)} {_pt(axis, drop_major + sgn * drop_r, channel)} "
                    f"L {_pt(axis, rise_major - sgn * rise_r, channel)} "
                    f"Q {_pt(axis, rise_major, channel)} {_pt(axis, rise_major, channel - rise_r)} "
                    f"{tail}"
                )
                if head:
                    sx_b, sy_b = axis.point(s_face_major, drop_from)
                if land != t_far:
                    tx_b, ty_b = axis.point(t_major_f + sgn * axis.box_major(pb.box.w, pb.box.h) / 2, land)
                length = (channel - drop_from) + run + (channel - land)
                # The chip seats mid-run on the flat channel leg (the gateway
                # hand file centers its telemetry chip on the run); without a
                # solver seat the balance rule falls back to the straight
                # chord, which an under-route never touches.
                label_pos = axis.point((drop_major + sgn * drop_r + rise_major - sgn * rise_r) / 2, channel)
                geos.append(
                    EdgeGeo(
                        index=j,
                        d=d,
                        sx=sx_b,
                        sy=sy_b,
                        tx=tx_b,
                        ty=ty_b,
                        length=length,
                        label_pos=label_pos,
                        label_bare=True,
                        polyline=(
                            axis.point(drop_major if head else s_major, drop_from),
                            axis.point(drop_major, channel),
                            axis.point(rise_major, channel),
                            axis.point(rise_major, land),
                            *(((tx_b, ty_b),) if land != t_far else ()),
                        ),
                        end_tangent=axis.point(0.0, -1.0) if land == t_far else axis.point(-sgn, 0.0),
                    )
                )
                continue
            # Flow-face under-route (source RIGHT face -> target LEFT face):
            # the same orthogonal detour law as the bottom-face family above —
            # straight legs, fixed ``ch.over_arc_r`` fillets — here as five
            # legs (exit stub, dive, channel run, rise, entry stub). The
            # retired construction swept the whole dive and the whole rise as
            # corner-consuming cubics with uncited 34/68 rail offsets. Stub
            # length mirrors the bottom-left branch's ``max(rise_r, 12)`` end
            # stub plus the fillet's own radius, so a full-radius corner
            # always fits the stub leg.
            #
            # No longer the default (owner ruling, 2026-08-27): an unauthored
            # skip takes the two-turn bottom-face route above. This branch
            # now serves only the skip that AUTHORS its entry face without an
            # exit — the arrival face was named, so the route honours it.
            channel = channel_base + skip_seen * ch.skip_stack
            deepest_channel = max(deepest_channel, channel)
            skip_seen += 1
            s_major, s_minor = axis.major_of(sx, scy), axis.minor_of(sx, scy)
            t_major, t_minor = axis.major_of(tx, tcy), axis.minor_of(tx, tcy)
            land_y = t_minor
            arc_r = ch.over_arc_r
            stub = max(arc_r, 12.0) + arc_r
            # Chip-junction alignment: when a SIBLING edge off the same face
            # carries a chip on a straight run, the skip's first turn lands a
            # few px shy of that pill and reads as leaking out of its corner.
            # Align the turn to the chip's own centre instead, so the pill
            # becomes the junction the two paths part at — one continuing along
            # the thread, one leaving its side. Falls back to the plain stub
            # when there is no chip to align to, so unchipped routes are
            # byte-identical.
            align = _sibling_chip_major(ctx, axis, edges, skip_idx, e.source, placed, s_major)
            down_x = align if align is not None else s_major + stub
            # This branch already climbs OUTSIDE the target's column (one stub
            # short of it) and lands through a major-running entry leg, so it
            # only needs the corridor when something stands in that climb —
            # a rank between the channel and the entry face. Pushed backwards
            # (-sgn) so the climb stays on the approach side of the target.
            rise_x = t_major - stub
            if _leg_blockers(
                axis, corridor_blockers, major=rise_x, minor_lo=land_y, minor_hi=channel, skip=_entry_skips(pb)
            ):
                rise_x = _corridor_major(
                    axis,
                    corridor_blockers,
                    major=rise_x,
                    minor_lo=land_y,
                    minor_hi=channel,
                    sgn=-1.0,
                    pad=corridor_pad,
                    clearance=clearance,
                    skip=_entry_skips(pb),
                )
            run_w = rise_x - down_x
            r1 = min(arc_r, stub / 2, (channel - s_minor) / 2)
            r2 = min(arc_r, (channel - s_minor) / 2, run_w / 2)
            r3 = min(arc_r, run_w / 2, (channel - land_y) / 2)
            r4 = min(arc_r, (channel - land_y) / 2, stub / 2)
            d = (
                f"M {_pt(axis, s_major, s_minor)} "
                f"L {_pt(axis, down_x - r1, s_minor)} "
                f"Q {_pt(axis, down_x, s_minor)} {_pt(axis, down_x, s_minor + r1)} "
                f"L {_pt(axis, down_x, channel - r2)} "
                f"Q {_pt(axis, down_x, channel)} {_pt(axis, down_x + r2, channel)} "
                f"L {_pt(axis, rise_x - r3, channel)} "
                f"Q {_pt(axis, rise_x, channel)} {_pt(axis, rise_x, channel - r3)} "
                f"L {_pt(axis, rise_x, land_y + r4)} "
                f"Q {_pt(axis, rise_x, land_y)} {_pt(axis, rise_x + r4, land_y)} "
                f"L {_pt(axis, t_major, land_y)}"
            )
            length = (t_major - s_major) + (channel - s_minor) + (channel - land_y)
            geos.append(
                EdgeGeo(
                    index=j,
                    d=d,
                    sx=sx,
                    sy=scy,
                    tx=tx,
                    ty=tcy,
                    length=length,
                    label_pos=axis.point((down_x + r2 + rise_x - r3) / 2, channel),
                    label_bare=True,
                    polyline=(
                        axis.point(s_major, s_minor),
                        axis.point(down_x, s_minor),
                        axis.point(down_x, channel),
                        axis.point(rise_x, channel),
                        axis.point(rise_x, land_y),
                        axis.point(t_major, land_y),
                    ),
                    end_tangent=axis.point(1.0, 0.0),
                )
            )
            continue
        plain_by_target.setdefault(e.target, []).append(len(geos))
        plain_by_source.setdefault(e.source, []).append(len(geos))
        if _is_authored_elbow(e):
            # Authored under-elbow — the direct-read's mirror: exit the
            # source's south face, ride the bottom band east PAST the target
            # column, climb the east gutter, land through the target's east
            # face. Zero lane crossings by construction (the band runs under
            # the content, the climb outside the column); a chip seats on the
            # flat bottom run like every channel chip. Same orthogonal detour
            # family and fixed fillets as the skip routes. Authored data
            # only — no solver policy picks this route for an edge.
            s_major, s_far = _major_center(axis, pa), _minor_far(axis, pa)
            sx_b, sy_b = axis.point(s_major, s_far)
            channel = channel_base + skip_seen * ch.skip_stack
            deepest_channel = max(deepest_channel, channel)
            skip_seen += 1
            arc_r = ch.over_arc_r
            elbow_at = b_minor + (ch.port_stagger / 2 if e.target in stagger_faces else 0.0)
            tx_e, tcy_e = side_anchor(pb, side=axis.exit_side, at=elbow_at)
            # Span-aware corridor (ruling 2026-07-16): the climb clears every
            # box it passes — the rightmost obstacle in its own span plus
            # clearance, never just the target's face — so a later rank east
            # of the entry face wraps the route instead of being cut. Region
            # bands count as obstacles (their outline is furniture a wire
            # must clear like a card). ``_corridor_major`` is this loop; every
            # other detour branch now runs it on its own entry leg.
            e_major, e_minor = axis.major_of(tx_e, tcy_e), axis.minor_of(tx_e, tcy_e)
            climb_top = min(e_minor, channel)
            rise_x = _corridor_major(
                axis,
                corridor_blockers,
                major=_major_center(axis, pb) + axis.box_major(pb.box.w, pb.box.h) / 2 + corridor_pad,
                minor_lo=climb_top,
                minor_hi=channel,
                sgn=1.0,
                pad=corridor_pad,
                clearance=clearance,
            )
            r1 = min(arc_r, (channel - s_far) / 2)
            r2 = min(arc_r, (channel - e_minor) / 2, (rise_x - e_major) / 2)
            d = (
                f"M {_pt(axis, s_major, s_far)} "
                f"L {_pt(axis, s_major, channel - r1)} "
                f"Q {_pt(axis, s_major, channel)} {_pt(axis, s_major + r1, channel)} "
                f"L {_pt(axis, rise_x - r2, channel)} "
                f"Q {_pt(axis, rise_x, channel)} {_pt(axis, rise_x, channel - r2)} "
                f"L {_pt(axis, rise_x, e_minor + r2)} "
                f"Q {_pt(axis, rise_x, e_minor)} {_pt(axis, rise_x - r2, e_minor)} "
                f"L {_pt(axis, e_major, e_minor)}"
            )
            geos.append(
                EdgeGeo(
                    index=j,
                    d=d,
                    sx=sx_b,
                    sy=sy_b,
                    tx=tx_e,
                    ty=tcy_e,
                    length=(channel - s_far) + (rise_x - s_major) + (channel - e_minor) + (rise_x - e_major),
                    label_pos=(
                        round(axis.point((s_major + r1 + rise_x - r2) / 2, channel)[0], 2),
                        round(axis.point((s_major + r1 + rise_x - r2) / 2, channel)[1], 2),
                    ),
                    label_bare=True,
                    polyline=(
                        axis.point(s_major, s_far),
                        axis.point(s_major, channel),
                        axis.point(rise_x, channel),
                        axis.point(rise_x, e_minor),
                        axis.point(e_major, e_minor),
                    ),
                    end_tangent=axis.point(-1.0, 0.0),
                )
            )
            continue
        # A chip rides STRAIGHT wire — the kit's own law — and the way to
        # honour it on a bending edge is NOT to bend the edge further. The
        # retired construction here was a PLATEAU: bow in, flat run for the
        # pill, bow out. It manufactured straightness by adding two shoulders,
        # so a chipped edge and its unchipped sibling left the same face on
        # visibly different shapes — order-event-dlq's kafka fans to reserve
        # and dlq at the same 59px offset, and only the labelled one stepped.
        # It fired on ONE edge in the whole corpus and no hand specimen draws
        # it: every specimen chip (pp-service-deps' `reads`, `direct read`)
        # sits centred on wire that was already straight.
        #
        # So the label steps off the wire instead, which is the shipped THREE
        # HOMES rule — micro-label beside its wire, chip inside its card,
        # caption band at the bottom. A chip that cannot sit on straight wire
        # has no home on that wire.

        # The plain S-curve: both control points at the MAJOR midpoint, so the
        # wire leaves its source and meets its target ALONG the flow — the
        # attachment law. Flowing right that is s_curve_h (controls at the x
        # midpoint, horizontal tangents); flowing down it is s_curve_v, which
        # is the vertical specimens' own construction
        # (``M 440,148 C 440,241 200,241 200,334``).
        curve = s_curve_h if axis.flow == "right" else s_curve_v
        curve_len = s_curve_h_len if axis.flow == "right" else s_curve_v_len
        geos.append(
            EdgeGeo(
                index=j,
                d=curve(sx, scy, tx, tcy),
                sx=sx,
                sy=scy,
                tx=tx,
                ty=tcy,
                length=curve_len(sx, scy, tx, tcy),
            )
        )
    # The AND-join (dag specimens): >=2 plain edges converging on a node that
    # AUTHORS ``gather: true`` meet at a knot floated join_trunk px before
    # the sink, and ONE solid trunk (arrowed) carries them home. Converging
    # curves drop their own terminals — the knot is their terminus. The hint
    # is required: a plain fan-in (bottleneck, shared dependency) is the same
    # geometry with per-edge meaning, so it lands per-edge.
    base_trunk = float(ch.join_trunk or 0)
    if base_trunk:
        for target, slots in plain_by_target.items():
            if len(slots) < 2 or not ctx.spec.nodes[target].gather:
                continue
            # Cargo rule (dag-scatter + the ``depart_trunk_bare`` mirror): a
            # trunk exists to carry its chip — a chip lengthens it to seat
            # (chip_w + 2*standoff, standoff marker-inclusive —
            # _join_chip_stub) and the chip mouth-hugs on the seated run; a
            # CHIPLESS join collapses to ``join_trunk_bare`` (default 0 —
            # flush at the mouth, the gather ring on the sink's face) instead
            # of dangling a bare arrowed wire before the sink.
            if not any(ctx.edges[geos[s].index].label for s in slots):
                knot_collapse(geos, slots, trunk_len=float(ch.join_trunk_bare or 0), vertical=vertical_flow)
                continue
            # The mouth-lift exists because ARRIVALS CROWD the knot (its own
            # citation): dag-scatter's 4-spoke join lifts its chip 22 above
            # the trunk. Every smaller join grounds — a trunk chip seats ON
            # its wire like every other channel chip (ruling 2026-07-16:
            # frontier-serving's cache chip grounded when its join grew to
            # three spokes; the wire parts the pill, no float). A GROUNDED
            # pill answers the on-line stub law (18.4/face), so its trunk
            # floors there; the lifted scatter keeps its own cited sizing.
            lifted = len(slots) >= 4
            join_stub = _join_chip_stub(ctx) if lifted else max(_join_chip_stub(ctx), CHIP_STUB_MIN)
            chip_run = chip_run_min([ctx.edges[geos[s].index] for s in slots], ctx.cfg, stub=join_stub)
            knot_collapse(geos, slots, trunk_len=max(base_trunk, chip_run), vertical=vertical_flow)
            _seat_gather_chip(ctx, geos, slots, geos[-1], lift=None if lifted else 0.0)
    # The depart mirror (frontier-serving): a HUB that authors ``gather:
    # true`` leaves on one solid arrowless stub to a knot at its center
    # mouth, then fans — the spread exits collapse to that mouth. The stub
    # is assert-dressed furniture (the spokes keep their own dress/arrows).
    depart_len = float(ch.depart_trunk or 0)
    for source, slots in plain_by_source.items():
        if len(slots) < 2 or not ctx.spec.nodes[source].gather:
            continue
        pb = placed[source]
        # The depart mouth is the face the fan LEAVES by, on the cross-axis
        # centre — east/cy flowing right, south/cx flowing down. Hardcoding the
        # east face put a vertical hub's knot (and the verb chip seated on its
        # trunk) out the card's side, straddling its own corner.
        mouth = side_anchor(pb, side=axis.exit_side, at=_minor_center(axis, pb))
        out_edges = [ctx.edges[geos[s].index] for s in slots]
        if not any(e.label for e in out_edges):
            # Cargo rule (the join's own law, mirrored — a trunk exists to
            # carry its chip): a CHIPLESS depart collapses FLUSH at the
            # mouth — the knot seats ON the face and the spread leaves it
            # directly, no bare stub dangling before the fan.
            bare_len = float(ch.depart_trunk_bare or 0)
            knot_collapse(
                geos, slots, trunk_len=bare_len, depart=True, marker="none", mouth=mouth, vertical=vertical_flow
            )
            continue
        # Grow the depart stub to seat the fan's verb chip (frontier-serving
        # 'route') — the mouth-side mirror of the join's chip_run_min.
        chip_run = chip_run_min(out_edges, ctx.cfg, stub=_GATHER_STANDOFF)
        trunk_len = max(depart_len, chip_run)
        knot_collapse(geos, slots, trunk_len=trunk_len, depart=True, marker="none", mouth=mouth, vertical=vertical_flow)
        # The knot floats trunk_len ALONG THE FLOW from the mouth — +x flowing
        # right, +y flowing down. Adding it to x regardless put the vertical
        # knot beside the mouth instead of below it, which collapsed the chip
        # onto the trunk's start with no stub before it.
        knot_pt = axis.point(axis.major_of(*mouth) + trunk_len, axis.minor_of(*mouth))
        _seat_depart_chip(ctx, geos, slots, mouth, knot_pt)
    if deepest_channel:
        minor_total = max(minor_total, int(deepest_channel + clearance + minor_far_chrome))
    # Re-derive the screen canvas: the channel and lane passes above grow the
    # MINOR axis, which is the height flowing right and the width flowing down.
    width, height = (int(v) for v in axis.point(major_total, minor_total))
    # Beam relay staging: a dag beam fires per RANK TRANSITION — the
    # N-stage generalization of the parity specimen's trunk-then-branches
    # (edges leaving one rank share a window). Stamp the source rank as the
    # stage key; wire_motion groups by it only when beams are present.
    geos = [replace(g, stage_key=rank[ctx.edges[g.index].source]) for g in geos]
    # The bend verdict travels with the geo: annotate seats the pill, the
    # solver decides whether it can sit level.
    if _float_labels:
        geos = [replace(g, float_label=True) if g.index in _float_labels else g for g in geos]
    # Conduit labels take the bracket — final seats, chip style overridden.
    geos = _bracket_conduit_labels(ctx, axis, edges, geos, _plan, placed)
    paint = [placed[i] for i in sorted(placed)]
    bands = reseat_region_labels(ctx, bands, geos, [p.box for p in placed.values()], axis)
    return finish_layout(
        ctx,
        width=width,
        height=height,
        nodes_paint=paint,
        geos=geos,
        lane_bands=bands,
        region_notes=region_notes,
        flow=axis.flow,
    )


def _sm_box(ctx: SolverContext, node: DiagramNode, nch: DiagramNodeChassis, i: int) -> tuple[float, float]:
    """The (w, h) a state-machine node's resolved anatomy solves to: pill
    (content-solved width, chassis height — the family default), card/
    card+glyph (``solve_card_box``), or glyph-circle (chassis diameter).
    ``nch`` (chassis) and hero-ness are independent here, exactly as the
    original kept them: the baseline loop's caller passes a role-conditional
    ``nch`` (matching auto-derive), but the off-baseline drop loop always
    passes ``ch.node`` regardless of role — ``chassis=nch`` preserves
    whichever the caller chose while hero still derives from the node's own
    role (a hero-role off-baseline drop would measure card/pill against
    ``ch.node`` while place_card's own role_of() still renders hero text —
    preserved verbatim, not fixed)."""
    ch = ctx.ch
    style = style_of(node, ctx.spec, ch)
    if style == NodeStyle.GLYPH_CIRCLE.value:
        w, h, _ = solve_node_box(ctx, node, i, circle_r=ch.circle_r)
        return w, h
    # The hero solves with ITS voice (17px name) — sizing it with the regular
    # voice under-reserved the name row (the truncated-hero bug, SM path).
    w, h, _ = solve_node_box(ctx, node, i, chassis=nch)
    return w, h


def _place_sm(
    ctx: SolverContext,
    i: int,
    node: DiagramNode,
    cx: float,
    cy: float,
    nch: DiagramNodeChassis,
    w: float,
    h: float,
    *,
    tag: str = "",
) -> NodePlacement:
    """Dispatch a state-machine node to its resolved anatomy, centered at
    (cx, cy) like every other topology's placement helper. Pill is the
    chassis default (a state is a condition, not a component — the family's
    one content-solved width); an explicit card/card+glyph or glyph-circle
    style renders through the shared chrome placements instead. ``tag`` (the
    TERMINAL chip under the chain's last hero) is pill-only chrome — a card
    or circle terminal renders without it. Glyph-circle never inside-stacks
    (``hub=False`` pinned, matching the original's omitted ``hub`` kwarg)."""
    style = style_of(node, ctx.spec, ctx.ch)
    if style == NodeStyle.GLYPH_CIRCLE.value:
        return place_node(ctx, node, i, cx, cy, w=w, h=h, hub=False)
    return place_node(ctx, node, i, cx, cy, w=w, h=h, chassis=nch, tag=tag)


def solve_state_machine(ctx: SolverContext) -> DiagramLayout:
    ch = ctx.ch
    spec = ctx.spec
    n = len(spec.nodes)
    edges = list(ctx.edges)
    caps = {**(ctx.engine.get("caps") or {}), **(ctx.spec.caps or {})}
    # A self-loop is the state revising itself in place — NOT a back-edge (the
    # DFS would falsely flag a v->v re-entry as a cycle). Partition first; the
    # back-edge machinery and rank chain run on the non-self remainder.
    loop_idx, non_self = split_self_loops(edges)
    if len(loop_idx) > int(caps.get("sm_max_self_loops", 2)):
        raise DiagramCapacityError(
            f"state-machine caps at {caps.get('sm_max_self_loops', 2)} self-loops (got {len(loop_idx)})"
        )
    flow_edges = [edges[j] for j in non_self]
    # back_edges returns positions into flow_edges; remap to original indices.
    back_local = back_edges(n, flow_edges)
    back = {non_self[j] for j in back_local}
    if len(back) > int(caps.get("sm_max_back_edges", 2)):
        raise DiagramCapacityError(f"state-machine caps at {caps.get('sm_max_back_edges', 2)} back-edges")
    forward = [flow_edges[j] for j in range(len(flow_edges)) if j not in back_local]
    rank = longest_path_ranks(n, forward)
    # The happy path: walk the longest forward chain (first-seen tie-break).
    succ_best: dict[int, int] = {}
    for e in forward:
        if rank[e.target] == rank[e.source] + 1 and e.source not in succ_best:
            succ_best[e.source] = e.target
    start = next((i for i in range(n) if rank[i] == 0), 0)
    baseline: list[int] = [start]
    while baseline[-1] in succ_best:
        baseline.append(succ_best[baseline[-1]])
    below = [i for i in range(n) if i not in baseline]
    if len(below) > int(caps.get("sm_max_below_baseline", 2)):
        raise DiagramCapacityError(
            f"state-machine caps at {caps.get('sm_max_below_baseline', 2)} off-baseline states (got {len(below)})"
        )
    height = ch.height or 300  # width is content-solved from the baseline below
    cy = ch.header_h + ch.node.h
    placed: dict[int, NodePlacement] = {}
    x = ch.margin_x
    last_baseline = baseline[-1]
    # Chip-run reconciliation (the same law the dag rank channels apply): a
    # run carrying an edge-chip must hold the chip plus a visible stub each
    # side — the chain gap grows to the widest chip's need, never the chip
    # squeezed onto a short run.
    chain_gap = max(ch.chain_gap, chip_run_min(list(ctx.edges), ctx.cfg, stub=CHIP_STUB_MIN))
    for i in baseline:
        node = spec.nodes[i]
        tag = "TERMINAL" if (i == last_baseline and node.role is NodeRole.HERO) else ""
        nch = ch.hero if node.role is NodeRole.HERO else ch.node
        # Content-solved box first so the node can START at the cursor
        # (every placement below centers on cx, cy).
        w, h = _sm_box(ctx, node, nch, i)
        p = _place_sm(ctx, i, node, x + w / 2, cy, nch, w, h, tag=tag)
        placed[i] = p
        x = p.box.x + p.box.w + chain_gap
    # The banner grows to fit the baseline (chassis width is the floor) — the same
    # content-sizing the dag path uses two functions up. A 5-6 state machine renders
    # at its natural span instead of truncating; the state count is already bounded
    # by the topology node cap (<=7), so the span stays reasonable.
    width = int(max(ch.width, x - chain_gap + ch.margin_x))
    # Off-baseline states drop beneath their first forward predecessor.
    pred_of: dict[int, int] = {}
    for e in forward:
        if e.target in below and e.target not in pred_of:
            pred_of[e.target] = e.source
    # Siblings sharing one predecessor spread symmetrically about its center
    # (one child sits exactly beneath it; two straddle it) — anchoring each
    # at the bare center stacked them on the SAME point.
    below_set = set(below)
    by_anchor: dict[int, list[int]] = {}
    for i in below:
        by_anchor.setdefault(pred_of.get(i, baseline[0]), []).append(i)

    # Depth-aware drops: a node anchored to ANOTHER off-baseline node hangs a
    # row below IT — the flat one-row drop landed a chained drop on the same
    # row as its own anchor (the Observe/Response overlap). Forward edges are
    # acyclic, so anchor groups process in depth order and every anchor is
    # placed before its dependents read it.
    def _drop_depth(i: int) -> int:
        d, cur, seen = 1, pred_of.get(i), {i}
        while cur is not None and cur in below_set and cur not in seen:
            seen.add(cur)
            d += 1
            cur = pred_of.get(cur)
        return d

    def _sm_nch(i: int) -> DiagramNodeChassis:
        # Role-derived for drops too (mismatch class FIXED): a hero-role
        # off-baseline state measures and renders with one chassis.
        return ch.hero if spec.nodes[i].role is NodeRole.HERO else ch.node

    for anchor_i in sorted(by_anchor, key=lambda a: 0 if a not in below_set else _drop_depth(a)):
        members = by_anchor[anchor_i]
        anchor = placed[anchor_i]
        acx = anchor.box.x + anchor.box.w / 2
        boxes = [_sm_box(ctx, spec.nodes[i], _sm_nch(i), i) for i in members]
        pitch = max(w for w, _h in boxes) + ch.drop_gap
        x0 = acx - pitch * (len(members) - 1) / 2
        for k, i in enumerate(members):
            w, h = boxes[k]
            placed[i] = _place_sm(
                ctx, i, spec.nodes[i], x0 + k * pitch, cy + _drop_depth(i) * ch.drop_dy, _sm_nch(i), w, h
            )
    # Terminal double-ring aspect (agent-task-lifecycle's done): a hairline
    # accent rect floating 6px outside the final card — a mark, not a card.
    # Computed HERE, before any arrival resolves (every anchors.py boundary
    # call below reads ``term_box`` when present): the ring is the state's
    # TRUE outer face — an arrival that resolved against the plain box first
    # would land 6px short of it (USER RULING, superseding the hand
    # specimen's own overshoot: pp-state-machine-alt2.svg's done ring draws
    # 6px past the card, but its own arrivals still tip at the PLAIN face —
    # an authoring inconsistency, not a law; arrivals now stop at the ring's
    # outer face, and labels clear the ring in turn).
    for i, node in enumerate(spec.nodes):
        if node.terminal and i in placed:
            tb = placed[i].box
            placed[i] = replace(
                placed[i],
                term_box=RectSpec(x=tb.x - 6.0, y=tb.y - 6.0, w=tb.w + 12.0, h=tb.h + 12.0, rx=tb.rx + 5.0),
            )
    # Nested back-edge returns (agent-task-lifecycle): several returns into ONE
    # target enter its bottom edge at DISTINCT offset points and never cross —
    # the wider-spanning return nests UNDER the shorter one. Order the returns by
    # source cx (so a return from the right enters right-of-centre, matching the
    # specimen's 358 vs 330 on planning's 140px underside) and rank them by span
    # (widest sinks deepest). One entry point + one depth per back-edge.
    back_entry: dict[int, tuple[float, float]] = {}
    _back_by_target: dict[int, list[int]] = {}
    for _j in back:
        _back_by_target.setdefault(edges[_j].target, []).append(_j)
    for _tgt, _js in _back_by_target.items():
        _tb = placed[_tgt].box
        _tcx = _tb.x + _tb.w / 2
        # Outermost (deepest) return = the one whose source sits LOWEST — an
        # off-baseline source (failed, already dropped below the chain) is
        # already deep, so its return naturally bows deeper than a same-row
        # return's shallow dip; horizontal distance from centre breaks ties
        # among sources at the same height. It enters the underside farthest
        # from centre on the side AWAY from its source and bows deepest, so
        # every shallower return nests INSIDE it and no two cross (specimen:
        # retry from the recovery region — failed at y351, off-baseline —
        # enters left/deep; revise from review — on-baseline, y139 — enters
        # right/shallow, even though review sits horizontally FARTHER from
        # planning than failed does: depth, not span, decides nesting order).
        _outer_first = sorted(
            _js,
            key=lambda j: (
                placed[edges[j].source].box.y,
                abs(placed[edges[j].source].box.x + placed[edges[j].source].box.w / 2 - _tcx),
            ),
            reverse=True,
        )
        _k = len(_outer_first)
        _half = min(14.0, _tb.w * 0.18)  # specimen: two entries 28px apart on planning's 140px underside
        for _rank, _j in enumerate(_outer_first):
            _sb = placed[edges[_j].source].box
            _src_dir = 1.0 if (_sb.x + _sb.w / 2) >= _tcx else -1.0
            # outer +1 .. inner -1, but a SOLE return (k==1) has no sibling to
            # separate from — ci1's own retry is the only edge into queued and
            # enters dead-center (275,181, queued cx=275 exactly); the old
            # unconditional 1.0 gave it the same +14px "outer" bias a 2-way
            # split's outer member gets, pulling the seat off-center for
            # nothing (and, compounded with the arrival-angle fix above, was
            # part of why the rendered retry read off-vertical).
            _signed = 0.0 if _k == 1 else 1.0 - 2.0 * _rank / (_k - 1)
            back_entry[_j] = (-_src_dir * _half * _signed, float(_k - 1 - _rank))
    geos: list[EdgeGeo] = []
    # LENS pairs (the order-lifecycle specimen): when a dropped state and its
    # anchor exchange BOTH directions and the drop sits directly beneath it,
    # the pair renders as a bowed lens — forward bows right, return bows
    # left, chips at the bellies — never a straight drop plus a cross-canvas
    # under-sweep. Detection: back-edge source hangs below, its target IS the
    # anchor it dropped from, and the drop is centered under it.
    lens_back: dict[int, tuple[int, int]] = {}
    lens_fwd: dict[int, tuple[int, int]] = {}
    for j, e in enumerate(edges):
        if j in back and e.source in below and pred_of.get(e.source) == e.target:
            low_p, top_p = placed.get(e.source), placed.get(e.target)
            if low_p is None or top_p is None:
                continue
            if abs((low_p.box.x + low_p.box.w / 2) - (top_p.box.x + top_p.box.w / 2)) < 1.0:
                lens_back[j] = (e.source, e.target)
                for k, f in enumerate(edges):
                    if f.source == e.target and f.target == e.source:
                        lens_fwd[k] = (e.target, e.source)
    for j, e in enumerate(edges):
        if e.source == e.target:
            # The state revising itself: a self-loop arc. A baseline pill loops
            # UP (out of the baseline row); an off-baseline pill loops DOWN
            # (away from the baseline above it). edge.exit overrides either.
            default_side = "bottom" if e.source in below_set else "top"
            geos.append(_self_loop_geo(ctx, j, e, placed[e.source], default_side=default_side))
            continue
        a, b = placed[e.source], placed[e.target]
        ab, bb = a.box, b.box
        if j in back and e.exit == "top":
            # THE OVER-ARC RETURN (agent-runtime's re-plan): the row's
            # underside is occupied (the tool pool), so an authored ``exit:
            # top`` bows the return ABOVE the row instead of under it — leaves
            # the source's top edge, peaks above the row, enters the target's
            # top. Vertical departure/arrival (both controls sit directly
            # above their own endpoint) keeps the bow symmetric —
            # ``_over_arc_peak`` bisects the RISE (mirroring
            # ``_under_curve_depth``'s downward search, same G7 discipline as
            # the back branch) until the flattened cubic clears every crossed
            # card by ``min_clearance``: a fixed 60px rise cleared agent-
            # runtime's evenly-spaced row by luck, never by construction, and
            # dove into a shorter span or a taller intervening card. The
            # composer owns the trigger (it knows the underside is taken);
            # this mirrors the under-curve, never a new routing convention.
            sx, sy = side_anchor(a, side="top", at=ab.x + ab.w / 2)
            tcx, entry_y = side_anchor(b, side="top", at=bb.x + bb.w / 2)
            lo_x, hi_x = min(sx, tcx), max(sx, tcx)
            crossed = [
                p.box
                for q, p in placed.items()
                if q not in (e.source, e.target) and p.box.x < hi_x and p.box.x + p.box.w > lo_x
            ]
            # A forward chain label rides ``sm_label_lift`` off its wire at
            # the row's own edge-label voice — folding its rendered height
            # into the clearance floor means the search below clears "the
            # tallest card ... and its labels" without a fragile cross-edge
            # lookup (a later-declared edge's label position isn't solved
            # yet here; every forward chain label sits at the row's own cy,
            # this floor bounds the worst case honestly).
            clearance = (
                float(ctx.engine.get("min_clearance", 18))
                + float(ctx.engine["connector"].get("sm_label_lift", 8))
                + ctx.cfg.edge_label_voice.size
            )
            peak = _over_arc_peak(sx, sy, tcx, entry_y, min(sy, entry_y) - 60.0, crossed, clearance)
            d = f"M {fmt(sx)},{fmt(sy)} C {fmt(sx)},{fmt(peak)} {fmt(tcx)},{fmt(peak)} {fmt(tcx)},{fmt(entry_y)}"
            # Analytic end tangent (the cubic's own derivative at t=1,
            # normalize(endpoint - c2)) — matches the back branch's own
            # pattern; c2=(tcx, peak) sits directly above the target by
            # construction, so the arrival reads perfectly vertical (never
            # the polyline-secant fallback, which read this class of curve
            # up to 37 degrees off — end_tangent_of's own citation).
            c2x, c2y = tcx, peak
            dtx, dty = tcx - c2x, entry_y - c2y
            tlen = math.hypot(dtx, dty)
            end_tangent = (dtx / tlen, dty / tlen) if tlen > 1e-9 else (0.0, -1.0)
            geos.append(
                EdgeGeo(
                    index=j,
                    d=d,
                    sx=sx,
                    sy=sy,
                    tx=tcx,
                    ty=entry_y,
                    length=line_len(sx, sy, tcx, entry_y) * 1.3,
                    end_tangent=end_tangent,
                    # Bare peak point (label_pos convention: annotate.py's
                    # subsume_edge_labels owns the presentation lift for
                    # every solver-anchored micro-label — see its docstring).
                    label_pos=((sx + tcx) / 2, peak),
                    label_max_w=96.0,
                    label_anchor="middle",
                    label_bare=True,
                    semantic_dash=str(ctx.engine["connector"].get("dash", "2 7")),
                )
            )
            continue
        if j in lens_back:
            # The LEFT bow of the lens (alt1's retry): exits the drop's top
            # at cx-inset, bows outward by depth, enters the anchor's bottom
            # at cx-inset — controls at 25%/75% of the run (the specimen's
            # own bezier: 575/545 ports, 618/502 controls, 360/440 on a
            # 320-480 run). Constants scale off the card like the arc-port
            # pattern: inset = min(15, w*0.18), depth = w*0.25 (171-wide cards give
            # the hand file's 15/43 exactly). The chip label seats at the
            # belly — the curve's own outward control x at the run midpoint.
            low_i, top_i = lens_back[j]
            lp, tp = placed[low_i], placed[top_i]
            cxm = lp.box.x + lp.box.w / 2
            inset = min(15.0, lp.box.w * 0.18)
            depth = lp.box.w * 0.25
            y0 = lp.box.y  # drop top
            y1 = tp.box.y + tp.box.h  # anchor bottom
            run = y0 - y1
            bx = cxm - inset - depth
            c2y_back = y1 + 0.25 * run
            d = (
                f"M {fmt(cxm - inset)},{fmt(y0)} C {fmt(bx)},{fmt(y1 + 0.75 * run)} "
                f"{fmt(bx)},{fmt(c2y_back)} {fmt(cxm - inset)},{fmt(y1)}"
            )
            # Analytic end tangent (the cubic's own derivative at t=1,
            # normalize(endpoint - c2) — the same pattern the back branch
            # below uses): a fixed (0,-1) reads pure-vertical, but the bow's
            # own c2 sits ``depth`` off the endpoint's x, so the TRUE arrival
            # is diagonal — pp-state-machine-alt1.svg's native marker-end
            # (orient="auto") draws retry's chevron on exactly that diagonal,
            # never straight up. The fixed guess mis-rotated the drawn
            # chevron by the full angle between "diagonal" and "vertical"
            # (62.2deg on order-lifecycle's own card geometry).
            dtx_back, dty_back = (cxm - inset) - bx, y1 - c2y_back
            tlen_back = math.hypot(dtx_back, dty_back)
            end_tangent_back = (dtx_back / tlen_back, dty_back / tlen_back) if tlen_back > 1e-9 else (0.0, -1.0)
            geos.append(
                EdgeGeo(
                    index=j,
                    d=d,
                    sx=cxm - inset,
                    sy=y0,
                    tx=cxm - inset,
                    ty=y1,
                    length=run * 1.15,
                    end_tangent=end_tangent_back,
                    label_pos=(bx, y1 + 0.5 * run),
                    label_max_w=96.0,
                    label_anchor="middle",
                    semantic_dash=str(ctx.engine["connector"].get("dash", "2 7")),
                )
            )
            continue
        if j in back:
            # The revise loop: an under-curve back into the target's
            # underside — the structural feature that separates this
            # topology from a pipeline. EXIT SIDE is one of three specimen-
            # measured archetypes (pp-state-machine-alt2.svg's revise/retry,
            # pp-state-machine.svg's retry) chosen by the source/target's
            # own geometry, never authored: SAME-ROW exits bottom-center
            # into a shallow sweep; a LOOP-AROUND spanning >=2 baseline
            # columns (or a 1-column short return with no nesting bonus —
            # see ``needs_basin`` below) hugs the source's bottom corner on
            # the travel side into a wide basin; otherwise (a short local
            # return from an off-baseline source already close to its
            # target, AND sharing its target's underside with another
            # return) the source's left-center, unchanged. The deep controls
            # then bisect DOWN until the flattened curve clears every
            # crossed pill by min_clearance (G7 binds under-runs too), and
            # the banner grows to hold whatever depth the law demanded.
            entry_off, nest_rank = back_entry.get(j, (0.0, 0.0))
            same_row = abs((ab.y + ab.h / 2) - (bb.y + bb.h / 2)) < 1.0
            # "Columns crossed": the source's baseline anchor (itself, if it
            # is already on the chain; its drop predecessor otherwise) vs
            # the target, counted by their position in the forward chain —
            # pp-state-machine's retry (failed, anchored under test) is 2
            # hops from queued (crossing build); alt2's retry (failed,
            # anchored under executing) is 1 hop from planning (adjacent,
            # nothing between) and stays the short-return default.
            anchor_src = pred_of.get(e.source, e.source)
            col_span = 0
            if not same_row and anchor_src in baseline and e.target in baseline:
                col_span = abs(baseline.index(anchor_src) - baseline.index(e.target))
            # needs_basin: a 1-column return ALSO takes the loop-around when
            # it has no nesting bonus to lean on (nest_rank==0 — alone on its
            # target's underside, not sharing it with a sibling return). The
            # short-return default's own two depth constants (loop_dy / 18.57
            # below) were fit on alt2's retry MEASURING ITS RENDERED CURVE,
            # which is nested under revise (both return to planning) and so
            # carries a +24px nest bonus the fit unknowingly baked in
            # (session-lifecycle's re-auth: expired anchored under active,
            # one hop from authing, ALONE on authing's underside — same
            # col_span==1 as alt2's retry, zero nest — rendered a 22.3deg
            # near-flat arrival off the bare constants, the same angle a
            # same-row sweep produces, not the short-return's own steep
            # signature). Loop-around's depth is span-proportional (0.501x,
            # never nest-dependent), so an un-nested short return takes that
            # self-scaling basin instead of leaning on a bonus it doesn't have.
            needs_basin = col_span >= 2 or (col_span == 1 and nest_rank == 0)
            if same_row:
                sx, sy = side_anchor(a, side="bottom", at=ab.x + ab.w / 2)
            elif needs_basin:
                target_left = (bb.x + bb.w / 2) < (ab.x + ab.w / 2)
                corner_x = ab.x if target_left else ab.x + ab.w
                sx, sy = boundary_anchor(a, corner_x, ab.y + ab.h, 0.0)
            else:
                sx, sy = side_anchor(a, side="left", at=ab.y + ab.h / 2)
            tcx, entry_anchor_y = side_anchor(b, side="bottom", at=bb.x + bb.w / 2 + entry_off)
            entry_y = entry_anchor_y + 2
            # A nested return sinks its belly one depth-step further than the one
            # inside it, so the returns read as concentric under-sweeps rather
            # than a single tangle (specimen: the retry from the recovery region
            # bows below the revise from review).
            nest = nest_rank * 24.0
            span = sx - tcx
            sign = 1.0 if span >= 0 else -1.0
            # C1 pull (specimen law): the sweep pulls out ~48% of its span
            # before diving, never a fixed chassis offset — measured across
            # the three hand back-edges (pp-state-machine-alt2.svg revise
            # 41%, retry 55%; pp-state-machine.svg (ci1) retry 48%); one
            # span-proportional constant reproduces all three within ~30px.
            c1x = sx - sign * 0.48 * abs(span)
            # C2/arrival rule (construction, not fit): each archetype's
            # arrival tangent is a SPECIMEN-EXACT angle off horizontal, cited
            # from the hand file's own raw bezier (direction P3-P2), and c2x
            # is now DERIVED from that angle instead of a continuous fit
            # against "rise" (source exit y minus target entry y). A rise-fit
            # reproduced the three hand numbers to within ~3px ON THEIR OWN
            # geometry (alt2 revise rise=0 offset=112px 23.6deg, alt2 retry
            # rise=179 offset=28px 71.1deg, ci1 retry rise=226 offset=0px
            # 90.0deg) but rise is layout-sensitive: cicd-machine's own
            # generated card layout measures rise=165.6 against the hand
            # file's 226 for the SAME edge, swinging the old fit's offset
            # from ~2px to 31px and the rendered arrival from the specimen's
            # exact 90.0deg to 82.4deg — the census dev-band laws never
            # caught it because nothing graded the angle itself (USER
            # FILING: "this keeps getting ignored — actually trace and
            # calculate").
            #   corner-basin (needs_basin, ci1 retry): 90.0deg exactly — c2
            #     sits DIRECTLY BELOW the seat (dx=0) whatever depth the
            #     clearance search below settles on; immune to rise BY
            #     CONSTRUCTION, never approximated toward it.
            #   recovery-climb (else, alt2 retry): 71.1deg — derived from
            #     THIS branch's own pre-clearance depth target
            #     (``recovery_base_c2y`` below, reused verbatim once the
            #     depth branch runs), so a clearance-driven deepening only
            #     ever makes the arrival STEEPER than 71.1, never flatter.
            #   same-row (alt2 revise): 23.6deg — rise~=0 here by
            #     definition (both ends share the baseline row), where the
            #     retired rise-fit already lands within ~1px of the
            #     specimen's own 112px offset (22.9deg rendered vs 23.6deg
            #     specimen) — left as the same fit rather than threading an
            #     angle target through belly_y's crossed-cards dependency
            #     for a sub-degree gain.
            rise = abs(sy - entry_y)
            recovery_base_c2y = entry_y + 18.57 + nest  # this branch's own depth target, cited again below
            if needs_basin:
                c2x = tcx
            elif not same_row:
                dy_recovery = abs(entry_y - recovery_base_c2y)
                c2x = tcx + sign * (dy_recovery / math.tan(math.radians(71.1)))
            else:
                c2_offset = max(0.0, 112.5 - 0.49 * rise)
                c2x = tcx + sign * c2_offset
            lo_x, hi_x = min(c1x, c2x, sx, tcx), max(c1x, c2x, sx, tcx)
            crossed = [
                p.box
                for q, p in placed.items()
                if q not in (e.source, e.target) and p.box.x < hi_x and p.box.x + p.box.w > lo_x
            ]
            clearance = float(ctx.engine.get("min_clearance", 18))
            # Depth base: CLEARANCE-HUNG, superseding a span-proportional fit
            # that generalized wrong (USER RULING: a wide same-target span on
            # a generated graph hung a belly hundreds of px deep in empty
            # canvas, chasing a span that had nothing to do with what the
            # sweep actually had to clear). same-row and corner-basin now
            # share ONE construction: both controls sink to the SAME belly_y
            # — a flat-bottomed basin, never a slope — set from what the
            # sweep must clear, not how far apart its endpoints sit:
            #   belly_y = (deepest bottom edge among the crossed cards, the
            #              source card, and the target card) + a fixed hang.
            # Two hangs, cited on their own hand file (c1x — the pull — is
            # unchanged here; the arrival-angle law above already consumed
            # this branch's own depth target once, for the recovery-climb
            # case, via ``recovery_base_c2y``):
            #   same-row (alt2 revise): row bottom 201 + 49 = controls at
            #     250 — pp-state-machine-alt2.svg's own revise draws BOTH
            #     controls at y=250 exactly; belly deviation 36.8px, arrival
            #     23.6deg both fall out of this construction, not fit to it.
            #   corner-basin (ci1 retry): failed's bottom 411 + 67 = belly
            #     478 — pp-state-machine.svg's own spatial-notes places the
            #     retry label "near the belly" at y=478; chord_dev ~=148.5px,
            #     arrival ~=90deg both fall out of this construction too.
            # "Crosses" is column-blind otherwise: agent-task-lifecycle's
            # revise (review->planning, same-row) x-overlaps the OFF-BASELINE
            # failed card (it hangs under executing, which sits between the
            # two) even though failed is nowhere near the shallow row sweep —
            # a raw crossed-rect max chased failed's bottom into a 462px
            # belly for a curve that should barely leave the row. A rect only
            # counts if it starts ABOVE the deeper of the two endpoints' own
            # bottoms (``deep_floor``): failed's top sits well BELOW that
            # floor (it begins where the row has already ended), so it is not
            # something the sweep ducks under; build/test in ci1's retry
            # start well above failed's own corner-basin floor, so they still
            # count there.
            # The short-return default (below) is a steep CLIMB, not a sag —
            # alt2's retry never dips below its own source, so there is no
            # belly to hang and it keeps its own asymmetric loop_dy/18.57 fit
            # (``ch.loop_dy`` in primer.yaml), unchanged, still landing on
            # pp-state-machine-alt2.svg's retry, 32.9px.
            if same_row or needs_basin:
                hang = 49.0 if same_row else 67.0
                deep_floor = max(ab.y + ab.h, bb.y + bb.h)
                crossed_bottom = max([deep_floor, *(r.y + r.h for r in crossed if r.y < deep_floor)])
                belly_y = crossed_bottom + hang
                base_c1y, base_c2y = belly_y + nest, belly_y + nest
            else:
                base_c1y, base_c2y = sy + ch.loop_dy + nest, entry_y + 18.57 + nest
            extra, deepest, belly_x = _under_curve_depth(
                sx, sy, tcx, entry_y, c1x, c2x, base_c1y, base_c2y, crossed, clearance
            )
            height = max(height, math.ceil(deepest + clearance + ch.footer_h))
            c1y = base_c1y + extra
            c2y = base_c2y + extra
            d = f"M {fmt(sx)},{fmt(sy)} C {fmt(c1x)},{fmt(c1y)} {fmt(c2x)},{fmt(c2y)} {fmt(tcx)},{fmt(entry_y)}"
            # Analytic end tangent (the cubic's own derivative at t=1,
            # normalize(endpoint - c2)) — required now that c2x varies from
            # tcx; without it wiring's arrival tangent falls back to a
            # polyline secant and mis-rotates the chevron by up to ~17deg.
            dtx, dty = tcx - c2x, entry_y - c2y
            tlen = math.hypot(dtx, dty)
            end_tangent = (dtx / tlen, dty / tlen) if tlen > 1e-9 else (0.0, -1.0)
            # Label anchor: an archetype that genuinely dips (same-row,
            # corner-basin) seats its label at the curve's own deepest
            # excursion — both hand files draw "near the belly". A
            # recovery-climb has no dip BY CITATION (alt2's retry never
            # falls below its own source): ``deepest`` there is just
            # whichever sampled point happens to have the largest y, a
            # near-endpoint artifact carrying no meaning, not a "middle of
            # the sweep" — its label rides the curve's own parameter
            # midpoint instead, B(0.5) = (P0+3*P1+3*P2+P3)/8, "half-way
            # through the climb" regardless of depth.
            if deepest > max(sy, entry_y) + 2.0:
                label_x, label_y = belly_x, deepest
            else:
                label_x = (sx + 3 * c1x + 3 * c2x + tcx) / 8.0
                label_y = (sy + 3 * c1y + 3 * c2y + entry_y) / 8.0
            geos.append(
                EdgeGeo(
                    index=j,
                    d=d,
                    sx=sx,
                    sy=sy,
                    tx=tcx,
                    ty=entry_y,
                    length=line_len(sx, sy, tcx, entry_y) * 1.3,
                    end_tangent=end_tangent,
                    # label_pos is the bare point ON the curve — annotate.py's
                    # subsume_edge_labels is the single owner of the
                    # presentation lift that clears a micro-label off the
                    # stroke (the convention collapse: the solver emits
                    # geometry, the annotate layer decides chip-vs-micro-label
                    # dress).
                    label_pos=(label_x, label_y),
                    label_max_w=96.0,
                    label_anchor="middle",
                    label_bare=True,
                    semantic_dash=str(ctx.engine["connector"].get("dash", "2 7")),
                    # Returns ride the drift dash (specimen law: every
                    # state-machine hand file draws its revise/self arcs as
                    # conn drift, chain solid) — relation_default (not
                    # relation_override) so an authored relation on the edge
                    # still wins outright. drift's own dress terminal is a
                    # dot (§3), but every hand specimen that authors
                    # relation: drift on a back-edge pairs it with an
                    # explicit marker: arrow — the dash comes from drift, the
                    # chevron stays. marker_override reproduces that pairing
                    # for the UNAUTHORED case only (empty when the edge
                    # already declares its own marker).
                    relation_default="drift",
                    marker_override="" if e.marker else "arrow",
                )
            )
        elif j in lens_fwd:
            # The RIGHT bow of the lens (alt1's throw) — mirror of the left.
            top_i, low_i = lens_fwd[j]
            tp, lp = placed[top_i], placed[low_i]
            cxm = lp.box.x + lp.box.w / 2
            inset = min(15.0, lp.box.w * 0.18)
            depth = lp.box.w * 0.25
            y0 = tp.box.y + tp.box.h
            y1 = lp.box.y
            run = y1 - y0
            bx = cxm + inset + depth
            c2y_fwd = y0 + 0.75 * run
            d = (
                f"M {fmt(cxm + inset)},{fmt(y0)} C {fmt(bx)},{fmt(y0 + 0.25 * run)} "
                f"{fmt(bx)},{fmt(c2y_fwd)} {fmt(cxm + inset)},{fmt(y1)}"
            )
            # Analytic end tangent (mirrors the left bow's own fix above): a
            # fixed (0,1) reads pure-vertical, but this bow's own c2 sits
            # ``depth`` off the endpoint's x too — pp-state-machine-alt1.svg's
            # native marker-end draws throw's chevron on the same diagonal
            # family as retry's, never straight down.
            dtx_fwd, dty_fwd = (cxm + inset) - bx, y1 - c2y_fwd
            tlen_fwd = math.hypot(dtx_fwd, dty_fwd)
            end_tangent_fwd = (dtx_fwd / tlen_fwd, dty_fwd / tlen_fwd) if tlen_fwd > 1e-9 else (0.0, 1.0)
            geos.append(
                EdgeGeo(
                    index=j,
                    d=d,
                    sx=cxm + inset,
                    sy=y0,
                    tx=cxm + inset,
                    ty=y1,
                    length=run * 1.15,
                    end_tangent=end_tangent_fwd,
                    label_pos=(bx, y0 + 0.5 * run),
                    label_max_w=96.0,
                    label_anchor="middle",
                )
            )
        elif e.target in below or e.source in below:
            drop = e.target in below
            top_node = a if drop else b  # the on-baseline anchor
            low_node = b if drop else a  # the off-baseline drop
            lcx = low_node.box.x + low_node.box.w / 2
            # Fan off the anchor's bottom EDGE: the anchor-side endpoint clamps to
            # the anchor's span so it stays flush, then the wire angles to the
            # below-node's top. A tool pool wider than its anchor (agent-
            # runtime: three tools off Act) fans; it never floats a vertical stub
            # past the anchor's side. A drop already under its anchor is
            # byte-identical (clamp is a no-op, the wire stays vertical).
            axx = min(max(lcx, top_node.box.x + 8.0), top_node.box.x + top_node.box.w - 8.0)
            _, ty0 = side_anchor(top_node, side="bottom", at=axx)
            _, ly0 = side_anchor(low_node, side="top", at=lcx)
            sxx, syy, txx, tyy = (axx, ty0, lcx, ly0) if drop else (lcx, ly0, axx, ty0)
            geos.append(
                EdgeGeo(
                    index=j,
                    d=line_d(sxx, syy, txx, tyy),
                    sx=sxx,
                    sy=syy,
                    tx=txx,
                    ty=tyy,
                    length=line_len(sxx, syy, txx, tyy),
                    # Bare wire midpoint (label_pos convention: annotate.py's
                    # subsume_edge_labels owns the presentation clearance for
                    # every solver-anchored micro-label — see its docstring).
                    label_pos=((sxx + txx) / 2, (syy + tyy) / 2),
                    label_max_w=96.0,
                    label_anchor="start",
                    label_bare=True,
                )
            )
        else:
            forwardward = bb.x > ab.x
            sx, sy_a = side_anchor(a, side="right" if forwardward else "left", at=cy)
            tx, ty_b = side_anchor(b, side="left" if forwardward else "right", at=cy)
            geos.append(
                EdgeGeo(
                    index=j,
                    d=line_d(sx, sy_a, tx, ty_b),
                    sx=sx,
                    sy=sy_a,
                    tx=tx,
                    ty=ty_b,
                    length=abs(tx - sx),
                    # Bare wire midpoint, ON the chain's cy (label_pos
                    # convention: annotate.py's subsume_edge_labels owns the
                    # presentation lift for every solver-anchored
                    # micro-label — see its docstring).
                    label_pos=((sx + tx) / 2, cy),
                    label_max_w=abs(tx - sx) + 56.0,
                    label_bare=True,
                )
            )
    # The initial pseudo-state is AUTHORED (chassis stub_len > 0): cicd-
    # lifecycle draws none; the alt specimens declare 26.5 / 16 px stubs.
    initial_dot = None
    initial_stub = None
    if float(ch.stub_len or 0) > 0:
        first = placed[baseline[0]].box
        initial_dot = (first.x - ch.stub_len - 4.0, cy)
        initial_stub = LineSpec(x1=first.x - ch.stub_len, y1=cy, x2=first.x, y2=cy)
    paint = [placed[i] for i in sorted(placed)]
    # RIGHT by construction, not by table: every state seats on the one
    # baseline ``cy`` and advances in x, so this solver has no transposed cell.
    sm_bands, sm_region_notes = build_region_bands(ctx, boxes_by_id(ctx.spec, placed), RIGHT)
    return finish_layout(
        ctx,
        width=width,
        height=height,
        nodes_paint=paint,
        geos=geos,
        lane_bands=sm_bands,
        region_notes=sm_region_notes,
        initial_dot=initial_dot,
        initial_stub=initial_stub,
        flow="right",
    )


# One solver, two cells: the flow axis is a parameter (AxisMap.for_slug),
# not a second implementation.
register_solvers({"dag": solve_dag, "dag-vertical": solve_dag, "state-machine": solve_state_machine})
