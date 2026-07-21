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
from dataclasses import replace
from typing import TYPE_CHECKING

from hyperweave.compose.diagram.anchors import boundary_anchor, side_anchor
from hyperweave.compose.diagram.chrome import place_node, style_of
from hyperweave.compose.diagram.layered import (
    back_edges,
    barycenter_orders,
    check_rank_contradiction,
    longest_path_ranks,
    pinned_orders,
    split_self_loops,
)
from hyperweave.compose.diagram.paths import bisect_clearance_depth, fmt, line_d, line_len, s_curve_h, s_curve_h_len
from hyperweave.compose.diagram.pinning import resolve_layout_pins
from hyperweave.compose.diagram.records import DiagramText, LaneBand
from hyperweave.compose.diagram.route import self_loop
from hyperweave.compose.diagram.sizing import (
    CHIP_H,
    CHIP_STUB_MIN,
    chip_run_min,
    hero_height_floor,
    marker_reserved_stub,
    solve_node_box,
)
from hyperweave.compose.diagram.solver import finish_layout, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext, knot_collapse
from hyperweave.compose.spatial_records import LineSpec, RectSpec
from hyperweave.core.diagram import DiagramCapacityError, DiagramInputError, DiagramNode, NodeRole, NodeStyle

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

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
    *,
    pitch_max: float = 16.0,
    skip_edges: frozenset[int] = frozenset(),
) -> tuple[dict[int, float], dict[int, float]]:
    """Spread the y where edges leave a shared source (fan-out) and land on a
    shared target (fan-in), so a bundle reads as distinct wires, not one
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
        b = placed[idx].box
        return b.y + b.h / 2

    exit_y: dict[int, float] = {}
    entry_y: dict[int, float] = {}

    def _assign(
        groups: dict[int, list[int]], node_of: dict[int, int], other_of: dict[int, int], out: dict[int, float]
    ) -> None:
        for node_i, members in groups.items():
            if len(members) < 2:
                continue
            box = placed[node_i].box
            cy = box.y + box.h / 2
            # Flush convergence: if any member's OTHER endpoint already sits on
            # this node's center row, its natural chord is straight — spreading
            # the group would bend that straight arrival into an S-curve. Collapse
            # to the one center mouth instead (service-dependencies auth->postgres,
            # gateway-balanced tiers->cache); a genuinely offset fan still spreads.
            if any(abs(_center(other_of[j]) - cy) <= _PORT_FLUSH for j in members):
                continue
            members.sort(key=lambda j: _center(other_of[j]))
            span = max(0.0, box.h - 20.0)
            pitch = min(pitch_max, span / (len(members) - 1)) if len(members) > 1 else 0.0
            for r, j in enumerate(members):
                out[j] = cy + (r - (len(members) - 1) / 2.0) * pitch

    src_of = {j: e.source for j, e in enumerate(edges)}
    tgt_of = {j: e.target for j, e in enumerate(edges)}
    _assign(out_groups, src_of, tgt_of, exit_y)
    _assign(in_groups, tgt_of, src_of, entry_y)
    return exit_y, entry_y


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
    d, length, _apex, label_anchor, end_tangent = self_loop(
        p,
        side,
        mouth=float(conn.get("loop_mouth", 24)),
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
        label_pos=label_anchor,
        label_max_w=float(conn.get("loop_label_max_w", 96)),
        label_anchor="start",
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
    ctx: SolverContext, i: int, node: DiagramNode, cx: float, cy: float, w: float, h: float
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
    return place_node(ctx, node, i, cx, cy, w=w, h=h)


def build_region_bands(ctx: SolverContext, placed: dict[int, NodePlacement]) -> tuple[LaneBand, ...]:
    """Authored compound regions → chrome bands, shared by dag and state-machine.

    Pads are DERIVED from what a region frames, not authored, and cited to
    ``diagram-frame.yaml``'s ``region_band`` block (each pad traces to a
    hand specimen's own compound-region rect vs. its member cards'). Two
    region kinds:

    ENCLOSURE (agent-task-lifecycle's RECOVERY): a hairline box around the
    members, uppercase label centred in the bottom strip.

    BAND (``kind: band``) is a FILLED panel:

    - A band enclosing an over-arc return (agent-runtime's AGENT RUNTIME
      control loop — an ``exit: top`` back-edge between two members) reserves
      65px above the row so the re-plan bow clears the frame; the tall top pad
      lifts the panel off the row centre and it censuses as its own card. The
      label tags the top-left corner.
    - A band with no over-arc (gateway-balanced's MODEL POOL) is a snug
      header strip with a centred column label. The near-symmetric pads leave
      it concentric with its middle member, so the census coalesces it as
      that member's shell — one shell_mark, not an extra card.
    """
    if not ctx.spec.regions:
        return ()
    spec = ctx.spec
    id_of = {n.id: k for k, n in enumerate(spec.nodes)}
    rb = ctx.engine.get("region_band") or {}
    bands: list[LaneBand] = []
    for reg in spec.regions:
        member_boxes = [placed[id_of[m]].box for m in reg.members if m in id_of and id_of[m] in placed]
        if not member_boxes:
            continue
        if reg.kind == "band":
            over_arc = any(e.exit == "top" and e.source in reg.members and e.target in reg.members for e in spec.edges)
            if over_arc:
                side_pad = float(rb.get("band_over_arc_side_pad", 22))
                top_pad = float(rb.get("band_over_arc_top_pad", 65))
                bot_pad = float(rb.get("band_over_arc_bottom_pad", 13))
            else:
                side_pad = float(rb.get("band_side_pad", 18))
                top_pad = float(rb.get("band_top_pad", 26))
                bot_pad = float(rb.get("band_bottom_pad", 12))
            x0 = min(mb.x for mb in member_boxes) - side_pad
            x1 = max(mb.x + mb.w for mb in member_boxes) + side_pad
            y0 = min(mb.y for mb in member_boxes) - top_pad
            y1 = max(mb.y + mb.h for mb in member_boxes) + bot_pad
            if over_arc:
                label = DiagramText(x=x0 + 14.0, y=y0 + 17.0, text=reg.label.upper(), cls="rcnt")
            else:
                label = DiagramText(x=(x0 + x1) / 2, y=y0 + 16.0, text=reg.label.upper(), cls="rcnt", anchor="middle")
            ground = "panel"
        else:
            side_pad = float(rb.get("enclosure_side_pad", 20))
            top_pad = float(rb.get("enclosure_top_pad", 22))
            bot_pad = float(rb.get("enclosure_bottom_pad", 28))
            x0 = min(mb.x for mb in member_boxes) - side_pad
            x1 = max(mb.x + mb.w for mb in member_boxes) + side_pad
            y0 = min(mb.y for mb in member_boxes) - top_pad
            y1 = max(mb.y + mb.h for mb in member_boxes) + bot_pad
            label = DiagramText(x=(x0 + x1) / 2, y=y1 - 10.0, text=reg.label.upper(), cls="rlabel", anchor="middle")
            ground = "enclosure"
        bands.append(LaneBand(box=RectSpec(x=x0, y=y0, w=x1 - x0, h=y1 - y0, rx=18.0), header=label, ground=ground))
    return tuple(bands)


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
    chip_cx = (trunk.sx + mx) / 2
    # DAG joins float the chip a mouth-lift above the trunk (arrivals crowd the
    # knot, so the verb clears them); convergence grounds it ON the wire
    # (lift=0) — its own specimen (convergence-arrivals) seats the compose chip
    # dead-center on the trunk, nothing arriving to collide.
    dy = (CHIP_H / 2 + _GATHER_STANDOFF) if lift is None else lift
    geos[chip_slot] = replace(geos[chip_slot], label_pos=(chip_cx, my - dy), label_anchor="middle")
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
    note_base = max(my, (my - dy) + CHIP_H / 2)
    for r, s in enumerate(note_slots):
        note_y = note_base + _GATHER_STANDOFF + note_voice.size + r * (note_voice.size + _GATHER_STANDOFF)
        geos[s] = replace(geos[s], label_pos=(chip_cx, note_y), label_anchor="middle")


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
    mx, my = mouth
    kx, _ = knot
    geos[chip_slot] = replace(geos[chip_slot], label_pos=((mx + kx) / 2, my), label_anchor="middle")


def _lane_rows(
    grid_members: list[int],
    provisional: Mapping[int, float],
    pitch: float,
    edges: Sequence[ResolvedEdge],
    rank: list[int],
    placed: Mapping[int, NodePlacement],
    spec_nodes: Sequence[DiagramNode],
) -> dict[int, float]:
    """Row-aligned cy per grid member — lanes over independent centering.

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
    already-aligned figure."""
    targets: dict[int, float] = {}
    designated: dict[int, int] = {}
    for m in grid_members:
        inbound = [
            e for e in edges if e.target == m and e.source != m and rank[m] - rank[e.source] == 1 and e.source in placed
        ]
        if not inbound:
            continue
        src_cy = {e.source: placed[e.source].box.y + placed[e.source].box.h / 2 for e in inbound}
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
            targets[m] = placed[source].box.y + placed[source].box.h / 2
    rows: dict[int, float] = {}
    running = -math.inf
    for m in grid_members:
        cy = targets.get(m, provisional[m])
        if running > -math.inf and pitch > 0:
            cy = max(cy, running + pitch)
        rows[m] = cy
        running = cy
    return rows


def solve_dag(ctx: SolverContext) -> DiagramLayout:
    ch = ctx.ch
    spec = ctx.spec
    n = len(spec.nodes)
    edges = list(ctx.edges)
    caps = {**(ctx.engine.get("caps") or {}), **(ctx.spec.caps or {})}
    # Self-loops carry no rank/crossing info (a v->v edge would push its own
    # rank up forever) — partition them out, rank + order on the remainder,
    # and route them as their own arc below.
    loop_idx, non_self = split_self_loops(edges)
    if len(loop_idx) > int(caps.get("sm_max_self_loops", 2)):
        raise DiagramCapacityError(f"dag caps at {caps.get('sm_max_self_loops', 2)} self-loops (got {len(loop_idx)})")
    flow_edges = [edges[j] for j in non_self]
    # Defensive re-check (the promotion seam's backstop): a cycle among
    # distinct nodes has no rank — production paths promote it to
    # state-machine in coerce_diagram_input before the solver runs; a direct
    # caller that skipped the seam must hear a refusal, not receive
    # rank-relaxed garbage geometry.
    if back_edges(n, flow_edges):
        raise DiagramInputError(
            "dag declares a cycle among its edges; cyclic dags promote to state-machine at the input "
            "seam (coerce_diagram_input) — route through it, or declare topology: state-machine"
        )
    fixed = _rank_overrides(list(spec.nodes))
    rank = longest_path_ranks(n, flow_edges, fixed)
    check_rank_contradiction(flow_edges, rank, fixed)
    n_ranks = max(rank) + 1
    if n_ranks > int(caps.get("dag_max_ranks", 4)):
        raise DiagramCapacityError(f"dag caps at {caps.get('dag_max_ranks', 4)} ranks (got {n_ranks}); split the graph")
    # Authored row-order pins (a transform child's inherited figure) outrank
    # the barycenter's fresh crossing minimum — order continuity IS the law;
    # a fresh compose without pins keeps the sweep byte-identical.
    pins = resolve_layout_pins(spec)
    orders = pinned_orders(n, rank, pins) if pins is not None else barycenter_orders(n, flow_edges, rank)
    for r, members in orders.items():
        if len(members) > int(caps.get("dag_max_per_rank", 4)):
            raise DiagramCapacityError(
                f"dag caps at {caps.get('dag_max_per_rank', 4)} nodes per rank (rank {r} has {len(members)})"
            )
    skips = [e for e in flow_edges if rank[e.target] - rank[e.source] >= 2]
    if len(skips) > int(caps.get("dag_max_skip_edges", 3)):
        raise DiagramCapacityError(
            f"dag caps at {caps.get('dag_max_skip_edges', 3)} rank-skipping edges (got {len(skips)})"
        )
    # Per-node boxes in per-rank columns (dag specimens): every card solves its
    # OWN box (a rank's crown enlarges through its content while its
    # siblings stay small — the uniform max-box sized every std card to the
    # hero and collapsed the hero/std ratio to 1.0); each rank column takes
    # its widest member, and members center within their column.
    boxes: dict[int, tuple[float, float]] = {}
    for i, node in enumerate(spec.nodes):
        style = style_of(node, ctx.spec, ch)
        if style == NodeStyle.GLYPH_CIRCLE.value:
            # Role-derived (mismatch #5, FIXED): the reserved slot measures
            # with the same chassis/radius the placement renders.
            w, h, _ = solve_node_box(ctx, node, i)
        else:
            w, h, _ = solve_node_box(ctx, node, i)
        boxes[i] = (w, h)
    # Aligned rank columns (kit law: widths even only within stacked columns —
    # the service-dependencies specimen carries three column widths in one
    # file): each rank's std cards share that COLUMN's widest content-driven
    # box, never the whole graph's (a trivial rank must not inherit a distant
    # rank's long labels). Heights re-solve at the shared width so wrapped
    # descs stay in-card. Containers are excluded — a nested canvas is not a
    # column vote.
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
        col_w = max(boxes[i][0] for i in col_ids)
        for i in col_ids:
            _w2, h2, _ = solve_node_box(ctx, spec.nodes[i], i, min_w=col_w)
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
        w, h, _ = solve_node_box(ctx, node, i, h_floor=hero_height_floor(ch))
        boxes[i] = (w, h)
    rank_w = {r: max(boxes[i][0] for i in members) for r, members in orders.items()}
    # Rank channels must hold their edge-chips + stubs (the chip-run law).
    # Rank channels must hold the chips that RIDE them — a rank-skipping
    # edge's chip rides its own under/over channel run instead, so it never
    # votes here (the gateway hand file's telemetry chip is 78 wide on a
    # 455px channel run; letting it inflate the 92px rank runs stretched
    # every rank gap ~30px past the citation).
    rank_channel_edges = [e for e in edges if e.source != e.target and rank[e.target] - rank[e.source] < 2]
    rank_gap = max(ch.rank_gap, chip_run_min(rank_channel_edges, ctx.cfg, stub=CHIP_STUB_MIN))
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
        trunk = max(depart_base, chip_run_min(outgoing, ctx.cfg, stub=_GATHER_STANDOFF))
        if trunk:
            gather_trunk[rank[sidx] + 1] = max(gather_trunk.get(rank[sidx] + 1, 0.0), trunk)
    span = sum(rank_w.values()) + (n_ranks - 1) * rank_gap + sum(gather_trunk.values())
    # Content-fit law: the chassis width spreads rank gaps only where the chassis
    # declares a fixed frame — otherwise a sparse dag hugs its own span
    # (canvas + scale follow in finish_layout).
    width = int(max(ch.width if ch.width_floor else 0, 2 * ch.margin_x + span))

    # Balance law (primer_diagram_language, router pitch 118 on h60):
    # rank pitch = card height + row_gap (gap ≈ card height), floored at the
    # chassis pitch — and the CANVAS grows to hold the tallest rank. The old
    # fixed-height clamp compressed a 4-member rank to ~10px gaps (the
    # squished-fan read).
    def _rank_pitch(members: list[int]) -> float:
        max_h_r = max(boxes[i][1] for i in members)
        return max(ch.rank_pitch_max, max_h_r + ch.row_gap)

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
        return all(rank[t] - rank[e.source] >= 2 and e.exit == "bottom" and e.entry == "left" for e in inbound)

    lane_members = frozenset(t for t in range(n) if _is_lane_member(t))

    def _grid(members: list[int]) -> list[int]:
        return [m for m in members if m not in lane_members]

    needed_h = max(
        (
            (len(_grid(members)) - 1) * _rank_pitch(_grid(members)) + max(boxes[i][1] for i in _grid(members))
            for members in orders.values()
            if _grid(members)
        ),
        default=ch.node.h,
    )
    # An exit:top skip runs an over-the-content channel (the specimen routes a
    # long cross-rank skip OVER the cards, chip on the top run); reserve a top
    # band so the cards clear it, mirroring the below-canvas skip channel.
    _has_top_skip = any(e.exit == "top" and rank[e.target] - rank[e.source] >= 2 for e in edges)
    top_reserve = max(ch.skip_drop, 60.0) if _has_top_skip else 0.0
    height = max(ch.height or 360, int(ch.header_h + top_reserve + ch.footer_h + needed_h))
    mid = (ch.header_h + top_reserve + height - ch.footer_h) / 2
    placed: dict[int, NodePlacement] = {}
    x_cursor = ch.margin_x
    # The extra canvas past the natural span splits evenly into the gaps so
    # a chassis-floored banner still reads centered.
    slack = max(0.0, width - 2 * ch.margin_x - span)
    eff_gap = rank_gap + (slack / (n_ranks - 1) if n_ranks > 1 else 0.0)
    if n_ranks == 1:
        x_cursor += slack / 2
    lane_cx: dict[int, float] = {}
    clearance = float(ctx.engine.get("min_clearance", 18))
    for idx, r in enumerate(sorted(orders)):
        # The gap INTO this rank; a gather-join rank takes its trunk ADDITIVELY
        # over the shared eff_gap so the convergence fan mirrors the departure.
        if idx > 0:
            x_cursor += eff_gap + gather_trunk.get(r, 0.0)
        members = orders[r]
        grid_members = _grid(members)
        k = len(grid_members)
        col_w = rank_w[r]
        pitch = _rank_pitch(grid_members) if k > 1 else 0.0
        provisional = {m: mid + (i - (k - 1) / 2) * pitch for i, m in enumerate(grid_members)}
        rows = _lane_rows(
            grid_members,
            provisional,
            _rank_pitch(grid_members) if grid_members else 0.0,
            edges,
            rank,
            placed,
            spec.nodes,
        )
        for node_index in grid_members:
            w, h = boxes[node_index]
            placed[node_index] = _place_dag_node(
                ctx, node_index, spec.nodes[node_index], x_cursor + col_w / 2, rows[node_index], w, h
            )
        for node_index in members:
            if node_index in lane_members:
                # Seated after the channel solves — remember the column only.
                lane_cx[node_index] = x_cursor + col_w / 2
        x_cursor += col_w
    # A monotone snap chain can push a conflict loser past the pre-solve rank
    # extent; grow the canvas exactly as the lane-member seat does rather than
    # letting a row ride the footer.
    if placed:
        deepest_grid = max(p.box.y + p.box.h for p in placed.values())
        height = max(height, int(deepest_grid + clearance + ch.footer_h))
    in_degree: dict[int, int] = {}
    for e in edges:
        in_degree[e.target] = in_degree.get(e.target, 0) + 1
    # Region bands (gateway-balanced's MODEL POOL) built NOW, ahead of their
    # one other consumer (finish_layout's lane_bands, below) — the under-
    # channel below needs each band's own bottom edge (a band's pad extends
    # PAST its deepest member card, so a channel cleared only against
    # deepest_box still crosses the band's own hairline: the gateway-balanced
    # telemetry defect).
    bands = build_region_bands(ctx, placed)
    # The under-channel must be where the edge ACTUALLY runs (G7): a single
    # cubic with controls at the channel never reaches it (~75% depth) and
    # grazes rank boxes. Three segments — dive, flat run ON the channel,
    # rise — keep clearance true; channels stack DOWNWARD and the canvas
    # grows to hold them.
    deepest_box = max((p.box.y + p.box.h for p in placed.values()), default=0.0)
    # A band's OUTLINE is a chip-seat obstacle too (annotate.py's
    # band_chip_clearance) — the under-channel a chip rides must clear the
    # band by the same specimen-cited margin PLUS the chip's own half-height
    # (CHIP_H/2), so a chip centered on the channel (never pushed off its
    # wire — kit piece 7) inherits the full clearance, not just the wire.
    deepest_band = max(
        (b.box.y + b.box.h for b in bands if b.ground in ("panel", "enclosure")),
        default=0.0,
    )
    band_clearance = float((ctx.engine.get("region_band") or {}).get("band_chip_clearance", 20)) + CHIP_H / 2
    channel_base = max(height - ch.footer_h - ch.skip_drop, deepest_box + clearance + 4, deepest_band + band_clearance)
    # Seat the lane members now the channel is solved: each takes the channel
    # its own inbound edge will run at (replicating the edge loop's
    # skip_seen ordering below — every non-top skip consumes one slot), so
    # its west face sits exactly at the flat run's height (the hand file's
    # one-corner telemetry entry) and the canvas grows to hold it.
    if lane_members:
        lane_channel: dict[int, float] = {}
        seen = 0
        for e in edges:
            if e.source == e.target or rank[e.target] - rank[e.source] < 2 or e.exit == "top":
                continue
            if e.target in lane_members and e.target not in lane_channel:
                lane_channel[e.target] = channel_base + seen * ch.skip_stack
            seen += 1
        for node_index in lane_members:
            w, h = boxes[node_index]
            cy = lane_channel.get(node_index, channel_base)
            placed[node_index] = _place_dag_node(ctx, node_index, spec.nodes[node_index], lane_cx[node_index], cy, w, h)
            height = max(height, int(cy + h / 2 + clearance + ch.footer_h))
    # Top channel for exit:top skips: above the shallowest card by a clear margin
    # (chip half-height + clearance) so the on-wire pill clears the card row.
    shallowest_box = min((p.box.y for p in placed.values()), default=mid)
    # Fan separation: edges sharing a source (fan-out) or a target (fan-in)
    # must not all leave/land on the SAME edge-center point — that reads as
    # a bundle of overlapping cables. Spread their exit/entry y across the
    # node's edge, ordered by the OTHER endpoint's y so the curves stay
    # untangled (top target = top exit). ``fan_exit_y`` / ``fan_entry_y``
    # return the spread coordinate for edge j.
    # Skip edges (rank diff >= 2) run in the under-channel, not a shared port —
    # exclude them from the arrival spread so a plain fan-in keeps its true pitch.
    skip_idx = frozenset(j for j, e in enumerate(edges) if rank[e.target] - rank[e.source] >= 2)
    _, fan_entry_y = _fan_spread(edges, placed, skip_edges=skip_idx)  # exits collapse to the center mouth
    plateau_min_dy = float((ctx.engine.get("connector") or {}).get("plateau_min_dy", 40))
    # Shared-east-face port stagger: a node that HOSTS an authored elbow entry
    # while also SOURCING a plain east exit would fuse both wires at center-y
    # (~18px shared cable + stacked arrowheads). Part them: exit half a stagger
    # above center, elbow landing half below. Scoped to exactly this collision —
    # the fan attachment law (exits collapse to the center mouth) is untouched
    # for every node not in the set, and an empty set is byte-identical output.
    _elbow_entry_targets = {e.target for e in edges if e.exit == "bottom" and e.entry == "right"}
    _plain_exit_sources = {
        e.source
        for j, e in enumerate(edges)
        if e.source != e.target and j not in skip_idx and not (e.exit == "bottom" and e.entry == "right")
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
        a, b = pa.box, pb.box
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
        exit_at = a.y + a.h / 2 - (ch.port_stagger / 2 if e.source in stagger_faces else 0.0)
        sx, scy = side_anchor(pa, side="right", at=exit_at)
        entry_at = b.y + b.h / 2 if ctx.spec.nodes[e.target].gather else fan_entry_y.get(j, b.y + b.h / 2)
        tx, tcy = side_anchor(pb, side="left", at=entry_at)
        if rank[e.target] - rank[e.source] >= 2:
            if e.exit == "top":
                # Over-the-top skip: leave the source's top, run an orthogonal
                # channel above the content band, descend to the target's top —
                # the specimen's cross-rank "direct read" route, its chip riding
                # the top run. Crisp L+Q corners (service-dependencies), never a wide
                # cubic sweep: a straight riser, a small over_arc_r quarter turn
                # into the channel, the flat run, a turn down, the drop.
                arc_r = ch.over_arc_r
                top_channel = shallowest_box - ch.over_arc_clear - skip_top_seen * ch.skip_stack
                skip_top_seen += 1
                sx_t, sy_t = pa.box.x + pa.box.w / 2, pa.box.y
                tx_t, ty_t = pb.box.x + pb.box.w / 2, pb.box.y
                sgn = 1.0 if tx_t >= sx_t else -1.0
                d = (
                    f"M {fmt(sx_t)},{fmt(sy_t)} "
                    f"L {fmt(sx_t)},{fmt(top_channel + arc_r)} "
                    f"Q {fmt(sx_t)},{fmt(top_channel)} {fmt(sx_t + sgn * arc_r)},{fmt(top_channel)} "
                    f"L {fmt(tx_t - sgn * arc_r)},{fmt(top_channel)} "
                    f"Q {fmt(tx_t)},{fmt(top_channel)} {fmt(tx_t)},{fmt(top_channel + arc_r)} "
                    f"L {fmt(tx_t)},{fmt(ty_t)}"
                )
                length = (sy_t - top_channel) + abs(tx_t - sx_t) + (ty_t - top_channel)
                geos.append(EdgeGeo(index=j, d=d, sx=sx_t, sy=sy_t, tx=tx_t, ty=ty_t, length=length))
                continue
            if e.exit == "bottom":
                sx_b, sy_b = pa.box.x + pa.box.w / 2, pa.box.y + pa.box.h
                if e.entry == "left":
                    # Bottom-exit, WEST-entry (gateway-balanced telemetry):
                    # dive from the source's bottom, one L+Q corner from
                    # vertical to horizontal at the channel depth, then a
                    # flat run straight into the target's west face —
                    # pp-gateway-balanced.svg's own telemetry: M 427,31 L
                    # 427,149 Q 427,156 434,156 L 889,156 (the channel sits
                    # AT the target's own entry height, so one corner
                    # suffices). Where the channel sits BELOW the target's
                    # own entry height (channel > tcy — a shallower target
                    # that doesn't reach the deep-content clearance line),
                    # the flat run at ``channel`` would pass under the face
                    # and never arrive: a second and third corner carry it
                    # back UP to ``tcy`` before a final flat entry, the two
                    # corners' own radius shrinking to fit whenever the rise
                    # itself is tighter than the standard ``arc_r``.
                    arc_r = ch.over_arc_r
                    channel = max(channel_base + skip_seen * ch.skip_stack, tcy)
                    deepest_channel = max(deepest_channel, channel)
                    skip_seen += 1
                    sgn = 1.0 if tx >= sx_b else -1.0
                    rise = channel - tcy
                    if rise <= 0.05:
                        d = (
                            f"M {fmt(sx_b)},{fmt(sy_b)} "
                            f"L {fmt(sx_b)},{fmt(channel - arc_r)} "
                            f"Q {fmt(sx_b)},{fmt(channel)} {fmt(sx_b + sgn * arc_r)},{fmt(channel)} "
                            f"L {fmt(tx)},{fmt(channel)}"
                        )
                        length = (channel - arc_r - sy_b) + abs(tx - sx_b)
                        label_pos = ((sx_b + sgn * arc_r + tx) / 2, channel)
                        polyline: tuple[tuple[float, float], ...] = ((sx_b, sy_b), (sx_b, channel), (tx, channel))
                    else:
                        rise_r = min(arc_r, rise / 2)
                        end_stub = max(rise_r, 12.0)
                        rise_x = tx - sgn * (rise_r + end_stub)
                        d = (
                            f"M {fmt(sx_b)},{fmt(sy_b)} "
                            f"L {fmt(sx_b)},{fmt(channel - arc_r)} "
                            f"Q {fmt(sx_b)},{fmt(channel)} {fmt(sx_b + sgn * arc_r)},{fmt(channel)} "
                            f"L {fmt(rise_x - sgn * rise_r)},{fmt(channel)} "
                            f"Q {fmt(rise_x)},{fmt(channel)} {fmt(rise_x)},{fmt(channel - rise_r)} "
                            f"L {fmt(rise_x)},{fmt(tcy + rise_r)} "
                            f"Q {fmt(rise_x)},{fmt(tcy)} {fmt(rise_x + sgn * rise_r)},{fmt(tcy)} "
                            f"L {fmt(tx)},{fmt(tcy)}"
                        )
                        length = (channel - arc_r - sy_b) + abs(tx - sx_b) + rise
                        label_pos = ((sx_b + sgn * arc_r + rise_x - sgn * rise_r) / 2, channel)
                        polyline = ((sx_b, sy_b), (sx_b, channel), (rise_x, channel), (rise_x, tcy), (tx, tcy))
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
                tx_b, ty_b = pb.box.x + pb.box.w / 2, pb.box.y + pb.box.h
                sgn = 1.0 if tx_b >= sx_b else -1.0
                drop_r = min(ch.over_arc_r, (channel - sy_b) / 2, abs(tx_b - sx_b) / 2)
                rise_r = min(ch.over_arc_r, (channel - ty_b) / 2, abs(tx_b - sx_b) / 2)
                d = (
                    f"M {fmt(sx_b)},{fmt(sy_b)} "
                    f"L {fmt(sx_b)},{fmt(channel - drop_r)} "
                    f"Q {fmt(sx_b)},{fmt(channel)} {fmt(sx_b + sgn * drop_r)},{fmt(channel)} "
                    f"L {fmt(tx_b - sgn * rise_r)},{fmt(channel)} "
                    f"Q {fmt(tx_b)},{fmt(channel)} {fmt(tx_b)},{fmt(channel - rise_r)} "
                    f"L {fmt(tx_b)},{fmt(ty_b)}"
                )
                length = (channel - sy_b) + abs(tx_b - sx_b) + (channel - ty_b)
                # The chip seats mid-run on the flat channel leg (the gateway
                # hand file centers its telemetry chip on the run); without a
                # solver seat the balance rule falls back to the straight
                # chord, which an under-route never touches.
                label_pos = ((sx_b + sgn * drop_r + tx_b - sgn * rise_r) / 2, channel)
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
                        polyline=((sx_b, sy_b), (sx_b, channel), (tx_b, channel), (tx_b, ty_b)),
                        end_tangent=(0.0, -1.0),
                    )
                )
                continue
            # Default under-route (source RIGHT face -> target LEFT face):
            # the same orthogonal detour law as the bottom-face family above —
            # straight legs, fixed ``ch.over_arc_r`` fillets — here as five
            # legs (exit stub, dive, channel run, rise, entry stub). The
            # retired construction swept the whole dive and the whole rise as
            # corner-consuming cubics with uncited 34/68 rail offsets. Stub
            # length mirrors the bottom-left branch's ``max(rise_r, 12)`` end
            # stub plus the fillet's own radius, so a full-radius corner
            # always fits the stub leg.
            channel = channel_base + skip_seen * ch.skip_stack
            deepest_channel = max(deepest_channel, channel)
            skip_seen += 1
            land_y = tcy
            arc_r = ch.over_arc_r
            stub = max(arc_r, 12.0) + arc_r
            down_x = sx + stub
            rise_x = tx - stub
            run_w = rise_x - down_x
            r1 = min(arc_r, stub / 2, (channel - scy) / 2)
            r2 = min(arc_r, (channel - scy) / 2, run_w / 2)
            r3 = min(arc_r, run_w / 2, (channel - land_y) / 2)
            r4 = min(arc_r, (channel - land_y) / 2, stub / 2)
            d = (
                f"M {fmt(sx)},{fmt(scy)} "
                f"L {fmt(down_x - r1)},{fmt(scy)} "
                f"Q {fmt(down_x)},{fmt(scy)} {fmt(down_x)},{fmt(scy + r1)} "
                f"L {fmt(down_x)},{fmt(channel - r2)} "
                f"Q {fmt(down_x)},{fmt(channel)} {fmt(down_x + r2)},{fmt(channel)} "
                f"L {fmt(rise_x - r3)},{fmt(channel)} "
                f"Q {fmt(rise_x)},{fmt(channel)} {fmt(rise_x)},{fmt(channel - r3)} "
                f"L {fmt(rise_x)},{fmt(land_y + r4)} "
                f"Q {fmt(rise_x)},{fmt(land_y)} {fmt(rise_x + r4)},{fmt(land_y)} "
                f"L {fmt(tx)},{fmt(land_y)}"
            )
            length = (tx - sx) + (channel - scy) + (channel - land_y)
            geos.append(
                EdgeGeo(
                    index=j,
                    d=d,
                    sx=sx,
                    sy=scy,
                    tx=tx,
                    ty=land_y,
                    length=length,
                    label_pos=((down_x + r2 + rise_x - r3) / 2, channel),
                    label_bare=True,
                    polyline=(
                        (sx, scy),
                        (down_x, scy),
                        (down_x, channel),
                        (rise_x, channel),
                        (rise_x, land_y),
                        (tx, land_y),
                    ),
                    end_tangent=(1.0, 0.0),
                )
            )
            continue
        plain_by_target.setdefault(e.target, []).append(len(geos))
        plain_by_source.setdefault(e.source, []).append(len(geos))
        if e.exit == "bottom" and e.entry == "right":
            # Authored under-elbow — the direct-read's mirror: exit the
            # source's south face, ride the bottom band east PAST the target
            # column, climb the east gutter, land through the target's east
            # face. Zero lane crossings by construction (the band runs under
            # the content, the climb outside the column); a chip seats on the
            # flat bottom run like every channel chip. Same orthogonal detour
            # family and fixed fillets as the skip routes. Authored data
            # only — no solver policy picks this route for an edge.
            sx_b, sy_b = pa.box.x + pa.box.w / 2, pa.box.y + pa.box.h
            channel = channel_base + skip_seen * ch.skip_stack
            deepest_channel = max(deepest_channel, channel)
            skip_seen += 1
            arc_r = ch.over_arc_r
            elbow_at = b.y + b.h / 2 + (ch.port_stagger / 2 if e.target in stagger_faces else 0.0)
            tx_e, tcy_e = side_anchor(pb, side="right", at=elbow_at)
            # Span-aware corridor (ruling 2026-07-16): the climb clears every
            # box it passes — the rightmost obstacle in its own span plus
            # clearance, never just the target's face — so a later rank east
            # of the entry face wraps the route instead of being cut. Region
            # bands count as obstacles (their outline is furniture a wire
            # must clear like a card).
            corridor_pad = clearance + arc_r
            climb_top = min(tcy_e, channel)
            rise_x = pb.box.x + pb.box.w + corridor_pad
            corridor_blockers = [p.box for p in placed.values()] + [band.box for band in bands]
            moved = True
            while moved:
                moved = False
                for blocker in corridor_blockers:
                    in_span = blocker.y < channel and blocker.y + blocker.h > climb_top
                    if in_span and blocker.x - clearance < rise_x < blocker.x + blocker.w + corridor_pad:
                        rise_x = blocker.x + blocker.w + corridor_pad
                        moved = True
            r1 = min(arc_r, (channel - sy_b) / 2)
            r2 = min(arc_r, (channel - tcy_e) / 2, (rise_x - tx_e) / 2)
            d = (
                f"M {fmt(sx_b)},{fmt(sy_b)} "
                f"L {fmt(sx_b)},{fmt(channel - r1)} "
                f"Q {fmt(sx_b)},{fmt(channel)} {fmt(sx_b + r1)},{fmt(channel)} "
                f"L {fmt(rise_x - r2)},{fmt(channel)} "
                f"Q {fmt(rise_x)},{fmt(channel)} {fmt(rise_x)},{fmt(channel - r2)} "
                f"L {fmt(rise_x)},{fmt(tcy_e + r2)} "
                f"Q {fmt(rise_x)},{fmt(tcy_e)} {fmt(rise_x - r2)},{fmt(tcy_e)} "
                f"L {fmt(tx_e)},{fmt(tcy_e)}"
            )
            geos.append(
                EdgeGeo(
                    index=j,
                    d=d,
                    sx=sx_b,
                    sy=sy_b,
                    tx=tx_e,
                    ty=tcy_e,
                    length=(channel - sy_b) + (rise_x - sx_b) + (channel - tcy_e) + (rise_x - tx_e),
                    label_pos=(round((sx_b + r1 + rise_x - r2) / 2, 2), round(channel, 2)),
                    label_bare=True,
                    polyline=((sx_b, sy_b), (sx_b, channel), (rise_x, channel), (rise_x, tcy_e), (tx_e, tcy_e)),
                    end_tangent=(-1.0, 0.0),
                )
            )
            continue
        is_chip = bool(e.label) and e.label_style == "chip"
        gathered = ctx.spec.nodes[e.target].gather or ctx.spec.nodes[e.source].gather
        # +3: the pill's PAINTED edge sits ~1.4px outside its ink box each
        # side, and the plateau is the one run built at exactly chip_run_min
        # — without the reserve the measured stub reads 17.0 against the
        # 18.4/face citation (same family as marker_reserved_stub: painted
        # extent eats a bare stub's visible thread).
        flat_min = chip_run_min([e], ctx.cfg, stub=CHIP_STUB_MIN) + 3.0 if is_chip else 0.0
        if is_chip and not gathered and abs(tcy - scy) > plateau_min_dy and (tx - sx) - flat_min >= 36.0:
            # A chip on a plain S-curve seats at the arc-length midpoint —
            # the steepest point of the S once the rows diverge, where the
            # stroke parts the pill diagonally. Chip edges that must bend
            # therefore ride a PLATEAU: bow in, flat run at the chip's own
            # run minimum (the ≥18px visible-wire stub law each side — the
            # parity board holds every on-line chip to it), bow out — the
            # remaining room splits
            # between dive and rise in proportion to their climbs, so a tall
            # rise reads as a swoop instead of a wall. Still the relational
            # bow family (two cubics), never the detour's L+Q corners. The
            # rail seats in the gap band adjacent to the SOURCE row toward
            # the target — the billing transform's writes chip rides below
            # the cache row — collapsing to the natural S mid for a
            # single-row bend. The rise still finishes min_clearance before
            # the target column face and lands through a flat approach (the
            # first construction grazed the cards stacked above the port).
            # Gather ends keep their trunk seats.
            src_grid = _grid(orders[rank[e.source]])
            half_gap = (_rank_pitch(src_grid) if src_grid else ch.rank_pitch_max) / 2
            rail = scy + math.copysign(min(half_gap, abs(tcy - scy) / 2), tcy - scy)
            approach = min(clearance + 2.0, (tx - sx - flat_min) / 4)
            rem = (tx - sx) - flat_min - approach
            dy_dive, dy_rise = abs(rail - scy), abs(tcy - rail)
            dive_dx = max(12.0, rem * dy_dive / max(dy_dive + dy_rise, 1.0))
            px0 = sx + dive_dx
            px1 = px0 + flat_min
            px2 = tx - approach
            mx1, mx2 = (sx + px0) / 2, (px1 + px2) / 2
            d = (
                f"M {fmt(sx)},{fmt(scy)} "
                f"C {fmt(mx1)},{fmt(scy)} {fmt(mx1)},{fmt(rail)} {fmt(px0)},{fmt(rail)} "
                f"L {fmt(px1)},{fmt(rail)} "
                f"C {fmt(mx2)},{fmt(rail)} {fmt(mx2)},{fmt(tcy)} {fmt(px2)},{fmt(tcy)} "
                f"L {fmt(tx)},{fmt(tcy)}"
            )
            geos.append(
                EdgeGeo(
                    index=j,
                    d=d,
                    sx=sx,
                    sy=scy,
                    tx=tx,
                    ty=tcy,
                    length=s_curve_h_len(sx, scy, px0, rail) + flat_min + s_curve_h_len(px1, rail, px2, tcy) + approach,
                    label_pos=(round((px0 + px1) / 2, 2), round(rail, 2)),
                    label_bare=True,
                    end_tangent=(1.0, 0.0),
                )
            )
            continue
        geos.append(
            EdgeGeo(
                index=j,
                d=s_curve_h(sx, scy, tx, tcy),
                sx=sx,
                sy=scy,
                tx=tx,
                ty=tcy,
                length=s_curve_h_len(sx, scy, tx, tcy),
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
                knot_collapse(geos, slots, trunk_len=float(ch.join_trunk_bare or 0))
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
            knot_collapse(geos, slots, trunk_len=max(base_trunk, chip_run))
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
        mouth = side_anchor(pb, side="right", at=pb.box.y + pb.box.h / 2)
        # Grow the depart stub to seat the fan's verb chip (frontier-serving
        # 'route') — the mouth-side mirror of the join's chip_run_min. A chipless
        # depart keeps the base stub (0 on the dag chassis: knot-only, no stub).
        chip_run = chip_run_min([ctx.edges[geos[s].index] for s in slots], ctx.cfg, stub=_GATHER_STANDOFF)
        trunk_len = max(depart_len, chip_run)
        knot_collapse(geos, slots, trunk_len=trunk_len, depart=True, marker="none", mouth=mouth)
        _seat_depart_chip(ctx, geos, slots, mouth, (mouth[0] + trunk_len, mouth[1]))
    if deepest_channel:
        height = max(height, int(deepest_channel + clearance + ch.footer_h))
    # Beam relay staging: a dag beam fires per RANK TRANSITION — the
    # N-stage generalization of the parity specimen's trunk-then-branches
    # (edges leaving one rank share a window). Stamp the source rank as the
    # stage key; wire_motion groups by it only when beams are present.
    geos = [replace(g, stage_key=rank[ctx.edges[g.index].source]) for g in geos]
    paint = [placed[i] for i in sorted(placed)]
    return finish_layout(ctx, width=width, height=height, nodes_paint=paint, geos=geos, lane_bands=bands)


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
    return finish_layout(
        ctx,
        width=width,
        height=height,
        nodes_paint=paint,
        geos=geos,
        lane_bands=build_region_bands(ctx, placed),
        initial_dot=initial_dot,
        initial_stub=initial_stub,
    )


register_solvers({"dag": solve_dag, "state-machine": solve_state_machine})
