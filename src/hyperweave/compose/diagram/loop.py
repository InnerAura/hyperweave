"""Loop family solver: the procedural directed loop (core/diagram.py
Topology.LOOP) — process stations on one spine, exclusive decision rhombi
with guard chips, terminal exits, external taps, one-level named scopes, and
the return rail closing the circuit.

One solver serves both cells through the AxisMap (the dag/dag-vertical
precedent): ``loop`` (the family default) flows DOWN — the axial spine with
its margin rail; ``loop-horizontal`` flows RIGHT — the lateral row with the
same rail construction landing as the underslung return (the far channel IS
the underside once the axis transposes; chirality is derived, never chosen).
Everything below is written in MAJOR/MINOR terms and mapped to screen at
placement — boxes never rotate.

Seat dispatch is STRUCTURAL (devices are content, never flags):

* a decision's return exit departs for the rail directly;
* a process exit whose only outgoing edge is the outer return (the rail
  feeder — cycle-retry's Back off) seats LATERALLY at the decision's rank on
  the rail side;
* a terminal exit beside a live continuation seats laterally on the advance
  side (cycle-retry's Done at Succeeded?'s own rank — "exits leave at their
  decision's rank"); beside a return exit it continues down the spine
  (turn/cycle-turn's Stop? -> Done);
* two plain process exits are the deviation pair (Improved? -> revert/keep):
  both seat at the next rank, offset each side of the spine, and their merge
  converges on the following station's near face — one drawn arrival.

Chromatic compile (the anchor's ``chromatic_compile`` law, genome tokens
only): a decision exit toward an advance-partition node rides the accent;
toward a discard/exhausted node or a further decision it rides the
complement (wire-grade); everything else stays the quiet conn. Deliberation
ink lives in the decision question text (``qname``) — never the frame.

Geometry constants: routing numbers in ``data/config/diagram-frame.yaml``'s
``loop:`` block, card/diamond dimensions on the topology chassis
(``data/paradigms/primer.yaml`` topologies.loop / loop-horizontal) — every
non-obvious number cites its specimen in v04/v040/v044/loop/.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from hyperweave.compose.diagram.axis import AxisMap
from hyperweave.compose.diagram.chrome import place_node
from hyperweave.compose.diagram.paths import cubic_len, fmt, line_d, line_len
from hyperweave.compose.diagram.records import DiagramText, LaneBand, NodePlacement
from hyperweave.compose.diagram.route import orthogonal_d
from hyperweave.compose.diagram.sizing import CHIP_H, family_carries_marks, solve_chip_box, solve_node_box
from hyperweave.compose.diagram.solver import finish_layout, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
from hyperweave.compose.matrix.cells import measure_voice
from hyperweave.compose.spatial_records import RectSpec
from hyperweave.core.diagram import DiagramInputError

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import DiagramLayout
    from hyperweave.core.diagram import DiagramNode, DiagramSpec, ResolvedEdge

# Deviation-pair minor offset is halves-sum: the deviation card's near edge
# aligns with the spine card's far edge (turn/cycle-turn: spine cards 210
# wide at x 295..505, deviation cards 170 wide at 125..295 / 505..675 — the
# columns tile exactly; the rank difference supplies the air).
CHIP_VISIBLE_RUN = 30.0
"""Bare-wire minimum each side of a straddling chip (the enrolled occlusion
law: <=1/3 occlusion with >=30px visible run per side)."""

_FORK_PULL = 0.6
"""Quarter-pipe fork: control 1 sits this fraction of the minor run from the
vertex (turn/cycle-turn's Improved? forks: M 300,396 C 246,396 … — 54 of 90)."""

_MERGE_DEPART = 0.727
"""Merge S-curve: control 1 rides this fraction of the major travel past the
dev card's exit face (the anchor's M 210,576 C 210,640 … — 64 of 88)."""

_MERGE_ARRIVE = 0.614
"""Merge S-curve: control 2 backs this fraction of the major travel off the
arrival apex (… 400,610 400,664 — 54 of 88); depart + arrive > 1, so the
controls cross the midpoint and the curve sweeps instead of kinking."""


@dataclass
class _Shape:
    """The loop's classified structure — one derivation, every pass reads it."""

    entry: int
    ret: tuple[int, ResolvedEdge] | None
    forward: list[tuple[int, ResolvedEdge]] = field(default_factory=list)
    taps: list[tuple[int, ResolvedEdge]] = field(default_factory=list)
    inner: dict[int, list[tuple[int, ResolvedEdge]]] = field(default_factory=dict)
    inner_ret: dict[int, tuple[int, ResolvedEdge]] = field(default_factory=dict)
    members: dict[int, list[int]] = field(default_factory=dict)
    member_scope: dict[int, int] = field(default_factory=dict)
    gather: tuple[int, list[tuple[int, ResolvedEdge]]] | None = None
    """The unrolled ladder's gather bus: (the gather terminal, its arm
    edges). ``ret`` is None exactly when this is set — the budget IS the
    unrolling, and the bus replaces the rail."""


def classify_loop(spec: DiagramSpec, edges: tuple[ResolvedEdge, ...]) -> _Shape:
    """The loop's structural classification — shared by the solver and the
    choreography compiler so the two can never disagree about which edge is
    the rail, which are taps, and which live inside a scope."""
    idx = {(n.id or f"n{i}"): i for i, n in enumerate(spec.nodes)}
    member_scope = {i: idx[n.enclosure] for i, n in enumerate(spec.nodes) if n.enclosure}
    members: dict[int, list[int]] = {}
    for m, s in member_scope.items():
        members.setdefault(s, []).append(m)
    ret: tuple[int, ResolvedEdge] | None = None
    shape_forward: list[tuple[int, ResolvedEdge]] = []
    taps: list[tuple[int, ResolvedEdge]] = []
    inner: dict[int, list[tuple[int, ResolvedEdge]]] = {s: [] for s in members}
    inner_ret: dict[int, tuple[int, ResolvedEdge]] = {}
    for k, e in enumerate(edges):
        scope = member_scope.get(e.source)
        if scope is not None and member_scope.get(e.target) == scope:
            if e.circuit == "return":
                inner_ret[scope] = (k, e)
            else:
                inner[scope].append((k, e))
            continue
        if e.circuit == "return":
            ret = (k, e)
        elif e.circuit in ("tap-in", "tap-out"):
            taps.append((k, e))
        else:
            shape_forward.append((k, e))
    gather: tuple[int, list[tuple[int, ResolvedEdge]]] | None = None
    if ret is None:
        # The unrolled ladder (IR-validated): the gather terminal is the
        # advance terminal two or more plain stations converge on; its arm
        # edges leave the forward walk — they are the bus, not the spine.
        by_target: dict[int, list[tuple[int, ResolvedEdge]]] = {}
        for kk, ee in shape_forward:
            tgt_n = spec.nodes[ee.target]
            if tgt_n.station == "terminal" and tgt_n.partition == "advance" and spec.nodes[ee.source].station == "":
                by_target.setdefault(ee.target, []).append((kk, ee))
        g_target = next((t for t, es in by_target.items() if len(es) >= 2), None)
        assert g_target is not None, "IR validation guarantees the gather signature on a zero-return loop"
        gather = (g_target, by_target[g_target])
        gset = {kk for kk, _ in by_target[g_target]}
        shape_forward = [(kk, ee) for kk, ee in shape_forward if kk not in gset]
        chained = {ee.target for _, ee in shape_forward}
        entry = next(
            i
            for i, n in enumerate(spec.nodes)
            if n.station == "" and not n.enclosure and i not in chained and i not in member_scope
        )
    else:
        entry = ret[1].target
    sh = _Shape(entry=entry, ret=ret, forward=shape_forward, taps=taps, inner=inner, inner_ret=inner_ret)
    sh.gather = gather
    sh.members = members
    sh.member_scope = member_scope
    return sh


def _station(node: DiagramNode) -> str:
    return node.station


def _is_rail_feeder(i: int, sh: _Shape) -> bool:
    """A process station whose ONLY outgoing edge is the outer return —
    cycle-retry's Back off, the node that hands the circuit to the rail."""
    outs = [e for _, e in sh.forward if e.source == i]
    return not outs and sh.ret is not None and sh.ret[1].source == i


# Seat kinds: where a node sits relative to the spine at its rank.
_SPINE, _DEV_NEAR, _DEV_FAR, _LAT_ADV, _LAT_RAIL, _EXT = "spine", "dev-", "dev+", "lat-adv", "lat-rail", "ext"
_GATHER = "gather"
"""The gather terminal's seat: across the flow from the ladder, over the
bus junction (the unrolled specimen's Done, sky-side of the attempts)."""


def _chassis_cls(node: DiagramNode, seat_kind: str) -> str:
    """The loop's node-class dispatch: terminals/externals ride the ``node2``
    class (the anchor's 220 sinks), the deviation pair its own ``dev`` class
    (the 170 twins), everything else the primary ``node`` class."""
    if _station(node) in ("terminal", "external"):
        return "node2"
    if seat_kind in (_DEV_NEAR, _DEV_FAR):
        return "dev"
    return ""


def _assign_seats(ctx: SolverContext, sh: _Shape) -> tuple[dict[int, int], dict[int, str]]:
    """Rank + seat per outer node, walked from the entry (the return edge's
    target). Structural dispatch only — see the module docstring."""
    spec = ctx.spec
    rank: dict[int, int] = {sh.entry: 0}
    seat: dict[int, str] = {sh.entry: _SPINE}
    out_of: dict[int, list[ResolvedEdge]] = {}
    into: dict[int, int] = {}
    for _, e in sh.forward:
        out_of.setdefault(e.source, []).append(e)
        into[e.target] = into.get(e.target, 0) + 1

    def _seat(i: int, r: int, s: str) -> None:
        if i in rank:
            rank[i] = max(rank[i], r)
            return
        rank[i], seat[i] = r, s

    frontier = [sh.entry]
    visited: set[int] = set()
    while frontier:
        i = frontier.pop(0)
        if i in visited or i not in rank:
            continue
        visited.add(i)
        r = rank[i]
        exits = out_of.get(i, [])
        node = spec.nodes[i]
        if _station(node) == "decision" and len(exits) == 2:
            a, b = exits
            has_return_exit = sh.ret is not None and sh.ret[1].source == i
            targets = [(e, spec.nodes[e.target]) for e in (a, b)]
            if all(_station(t) == "" and not _is_rail_feeder(e.target, sh) for e, t in targets):
                # Deviation pair — both descend, offset each side; the far
                # (advance) seat goes to the advance-partition target.
                first, second = targets
                far = first if first[1].partition == "advance" else second
                near = second if far is first else first
                _seat(far[0].target, r + 1, _DEV_FAR)
                _seat(near[0].target, r + 1, _DEV_NEAR)
                frontier += [far[0].target, near[0].target]
            else:
                for e, tnode in targets:
                    if _is_rail_feeder(e.target, sh):
                        _seat(e.target, r, _LAT_RAIL)
                    elif _station(tnode) == "terminal" and tnode.partition != "exhausted" and not has_return_exit:
                        # An advance terminal exits at its decision's rank
                        # (cycle-retry's Done); the bottom belongs to
                        # exhaustion — an exhausted terminal falls through
                        # the spine (the two-terminal placement rule).
                        _seat(e.target, r, _LAT_ADV)
                    else:
                        _seat(e.target, r + 1, _SPINE)
                    frontier.append(e.target)
        else:
            for e in exits:
                # A merge target ranks below its DEEPEST source; max() in
                # _seat handles re-visits.
                _seat(e.target, r + 1, _SPINE)
                frontier.append(e.target)
    for k, e in sh.taps:
        ext = e.source if e.circuit == "tap-in" else e.target
        partner = e.target if e.circuit == "tap-in" else e.source
        _ = k
        if partner in rank:
            _seat(ext, rank[partner], _EXT)
    if sh.gather is not None:
        # The gather terminal seats over the bus junction: the middle
        # source's rank (the unrolled specimen's Done centers over its
        # middle attempt), across the flow on the sky side.
        g, sources = sh.gather
        src_ranks = sorted(rank[ee.source] for _, ee in sources if ee.source in rank)
        if src_ranks:
            _seat(g, src_ranks[len(src_ranks) // 2], _GATHER)
    return rank, seat


def _lcfg(ctx: SolverContext, key: str, default: float) -> float:
    return float((ctx.engine.get("loop") or {}).get(key, default))


def _run_floor(span: float, cvr: float = 0.0) -> float:
    """The loop's own occlusion law (cycle-expression-map, the 40->30
    correction): <=1/3 occlusion AND >=30px of bare wire EACH side — the
    anchor's stop->done run measures 85 around its 26-tall chip, both
    constraints at their edge. +4 covers the endpoint standoff the drawn
    run loses to its target face. A spec-level density CITATION (``cvr``,
    the chassis chip_visible_run — the unrolled ladder's audited 22px)
    replaces the law for its own cell: run = span + 2 x the citation,
    exactly the specimen's 118.2 + 44 = 162.2 construction."""
    if cvr:
        return span + 2 * cvr + 4.0
    return max(span + 2 * CHIP_VISIBLE_RUN, 3 * span) + 4.0


def _chip_run_need(ctx: SolverContext, e: ResolvedEdge, *, vertical_run: bool) -> float:
    """The run a straddling guard chip needs: its span ALONG the run plus a
    visible stub each side — "the solver sized the run" is an owner-level
    contract (annotate seats a label_pos chip unconditionally), so every
    chip-bearing straight run floors here before geometry exists. A WIDE
    chip on a run across its long axis triples the run; the hand shuttle
    instead re-routes such an exit over an elbow so the chip straddles the
    cross leg — the tighter expression, a later routing refinement."""
    if not (e.label and e.label_style == "chip"):
        return 0.0
    cw, _ch = solve_chip_box(e.label, ctx.cfg)
    span = CHIP_H if vertical_run else cw
    return _run_floor(span, ctx.ch.chip_visible_run)


def solve_loop(ctx: SolverContext) -> DiagramLayout:
    if ctx.spec.lanes:
        # The swimlane loop: minor position by LANE MEMBERSHIP, its own
        # allocator module (split at the seam, never grown in here).
        from hyperweave.compose.diagram.loop_lanes import solve_loop_lanes

        return solve_loop_lanes(ctx)
    ax = AxisMap.for_slug(ctx.slug)
    ch = ctx.ch
    spec = ctx.spec
    sh = classify_loop(ctx.spec, ctx.edges)
    rank, seat = _assign_seats(ctx, sh)
    # A branch that SKIPS past an intervening spine station has no lawful
    # route this release — it would draw straight through the card (caught
    # by the wire-crosses-card sweep before this wall existed). Refuse with
    # the remedy rather than degrade.
    for _k, e in sh.forward:
        if (
            seat.get(e.source) == _SPINE
            and seat.get(e.target) == _SPINE
            and rank.get(e.target, 0) - rank.get(e.source, 0) >= 2
            and any(
                rank.get(i) is not None and rank[e.source] < rank[i] < rank[e.target] and seat.get(i) == _SPINE
                for i in range(len(spec.nodes))
            )
        ):
            src_id = spec.nodes[e.source].id or f"n{e.source}"
            tgt_id = spec.nodes[e.target].id or f"n{e.target}"
            raise DiagramInputError(
                f"edge '{src_id}'->'{tgt_id}' skips past a station on the spine — no route form "
                f"carries a skip this release; partition the intervening station aside (a deviation "
                f"pair) or route through it"
            )
    standoff = ch.connector_standoff if ch.connector_standoff is not None else 0.0
    rail_r = _lcfg(ctx, "rail_r", 10.0)
    rank_hop = _lcfg(ctx, "rank_hop", 66.0)
    rail_clear = _lcfg(ctx, "rail_clearance", 27.0)

    # ── Boxes (screen dims; text never rotates) ─────────────────────────
    boxes: dict[int, tuple[float, float]] = {}
    scope_layouts: dict[int, _ScopeLayout] = {}
    for i, node in enumerate(spec.nodes):
        if i in sh.member_scope:
            continue  # solved inside their scope below
        if _station(node) == "scope":
            sl = _solve_scope(ctx, ax, sh, i)
            scope_layouts[i] = sl
            boxes[i] = (sl.w, sl.h)
        else:
            w, h, _l = solve_node_box(ctx, node, i, chassis_class=_chassis_cls(node, seat.get(i, "")))
            boxes[i] = (w, h)
    fam_col: set[int] = set()  # members of marked families (the column law)
    if ch.width_policy == "aligned":
        # Each SEAT FAMILY shares one solved width (the corpus columns: all
        # spine stations 210, the deviation pair 170, terminals 220) —
        # re-solved at the family max so heights stay content-true.
        groups: dict[str, list[int]] = {}
        for i, node in enumerate(spec.nodes):
            if i in sh.member_scope or i not in boxes or _station(node) in ("decision", "scope"):
                continue
            key = "node2" if _station(node) in ("terminal", "external") else seat.get(i, _SPINE)
            if key in (_DEV_NEAR, _DEV_FAR):
                key = "dev"  # the pair is one aligned family (170-wide twins in the anchor)
            groups.setdefault(key, []).append(i)
        for key, members_g in groups.items():
            if len(members_g) < 2:
                continue
            cls2 = key if key in ("node2", "dev") else ""
            fam = family_carries_marks(ctx, [spec.nodes[i] for i in members_g])
            if fam:
                # Mixed-family column law: markless members re-measure at
                # the family's glyph column BEFORE the max, so the shared
                # width already holds their column-indented text.
                fam_col.update(members_g)
                for i in members_g:
                    boxes[i] = solve_node_box(ctx, spec.nodes[i], i, chassis_class=cls2, family_marked=True)[:2]
            shared = max(ax.box_minor(*boxes[i]) for i in members_g)
            for i in members_g:
                w, h, _l = solve_node_box(ctx, spec.nodes[i], i, chassis_class=cls2, min_w=shared, family_marked=fam)
                boxes[i] = (w, h)

    # ── Rail side / advance side ────────────────────────────────────────
    # far = the ADVANCE side (the zones' law); the rail defaults far
    # (turn/cycle-turn's right rail) unless a lateral advance terminal
    # occupies it (cycle-retry's Done), which pushes the rail near.
    has_lat_adv = any(s == _LAT_ADV for s in seat.values())
    rail_far = {"": not has_lat_adv, "near": False, "far": True}[ch.rail_side]

    # ── Rank majors ─────────────────────────────────────────────────────
    ranks = sorted({r for r in rank.values()})
    rank_extent: dict[int, float] = {}
    for i, (w, h) in boxes.items():
        if seat.get(i) == _EXT:
            continue
        r = rank[i]
        rank_extent[r] = max(rank_extent.get(r, 0.0), ax.box_major(w, h))
    gap = ch.gap
    vertical_major = ax.flow == "down"
    # A chip-bearing straight spine run must hold its chip plus visible
    # stubs each side (the chip-run law) — the gap into that rank floors.
    gap_need: dict[int, float] = {}
    lat_hop: dict[int, float] = {}
    for _k, e in sh.forward:
        if seat.get(e.target) in (_LAT_ADV, _LAT_RAIL):
            lat_hop[e.target] = max(rank_hop, _chip_run_need(ctx, e, vertical_run=not vertical_major))
        elif (
            seat.get(e.source) == _SPINE
            and seat.get(e.target) == _SPINE
            and rank.get(e.target, 0) == rank.get(e.source, 0) + 1
        ):
            need = _chip_run_need(ctx, e, vertical_run=vertical_major)
            if need:
                gap_need[rank[e.source]] = max(gap_need.get(rank[e.source], 0.0), need)
    # A chip-HOLDER decision breathes at the corpus's own air on BOTH sides
    # (turn/cycle-turn-choreography: dev bottom 576 -> Stop? apex 665 = 89 in,
    # Stop? bottom 835 -> Done top 922 = 87 out, against the 48-56 plain
    # hops) — the guard rows inside the rhombus earn the rank that extra
    # clearance, and the merge S-curves get the vertical room their
    # tangential arrival needs.
    holder_air = _lcfg(ctx, "holder_air", 88.0)
    for i, node in enumerate(spec.nodes):
        if _station(node) == "decision" and node.chips and i in rank and seat.get(i) == _SPINE:
            gap_need[rank[i] - 1] = max(gap_need.get(rank[i] - 1, 0.0), holder_air)
            gap_need[rank[i]] = max(gap_need.get(rank[i], 0.0), holder_air)
    if sh.ret is not None:
        ret_e = sh.ret[1]
        if ret_e.label and ret_e.label_style == "chip" and ret_e.source in rank and ret_e.target in rank:
            # The rail's LONG leg carries the return chip mid-run: its
            # straight run is the major span between the two port centers
            # minus both corner turns — floor it like any chip-bearing run
            # (a two-station loop is where this binds; taller loops clear
            # it from their own extents).
            r_lo, r_hi = sorted((rank[ret_e.source], rank[ret_e.target]))
            if r_hi > r_lo:
                span = CHIP_H if vertical_major else solve_chip_box(ret_e.label, ctx.cfg)[0]
                need = _run_floor(span, ctx.ch.chip_visible_run) + 2.0 * rail_r
                legs = [rank_extent.get(r, 0.0) for r in range(r_lo, r_hi + 1)]
                gaps = [max(gap, gap_need.get(r, 0.0)) for r in range(r_lo, r_hi)]
                have = legs[0] / 2 + legs[-1] / 2 + sum(legs[1:-1]) + sum(gaps)
                if have < need:
                    gap_need[r_lo] = max(gap_need.get(r_lo, 0.0), gaps[0] + (need - have))
    cursor = ch.header_h
    rank_center: dict[int, float] = {}
    for r in ranks:
        extent = rank_extent.get(r, 0.0)
        rank_center[r] = cursor + extent / 2
        cursor += extent + max(gap, gap_need.get(r, 0.0))
    content_major_end = cursor - max(gap, gap_need.get(ranks[-1], 0.0) if ranks else 0.0)

    # ── Minor seats ─────────────────────────────────────────────────────
    def _minor_half(i: int) -> float:
        w, h = boxes[i]
        return ax.box_minor(w, h) / 2

    # The deviation pair tiles against the spine CARDS (turn/cycle-turn:
    # dev near edge = spine card far edge); a diamond's grown width never
    # pushes the pair out — the rank difference supplies the air.
    spine_half = max(
        (_minor_half(i) for i, s in seat.items() if s == _SPINE and spec.nodes[i].station == ""),
        default=ch.node.w / 2,
    )
    far_sign = 1.0
    near_sign = -1.0
    minor: dict[int, float] = {}
    for i, s in seat.items():
        if s == _SPINE:
            minor[i] = 0.0
        elif s in (_DEV_NEAR, _DEV_FAR):
            sign = far_sign if s == _DEV_FAR else near_sign
            minor[i] = sign * (spine_half + _minor_half(i))
        elif s == _GATHER:
            # The gather terminal rides the sky side of the ladder: card
            # face -> bus_gap to the bus line -> bus_stem to its own face
            # (the unrolled specimen: attempts top 234, bus 176, Done
            # bottom 100 — 58 + 76 exactly).
            minor[i] = near_sign * (
                spine_half + _lcfg(ctx, "bus_gap", 58.0) + _lcfg(ctx, "bus_stem", 76.0) + _minor_half(i)
            )
        elif s in (_LAT_ADV, _LAT_RAIL):
            src_half = _decision_half_minor(ctx, ax, boxes, rank, i)
            sign = (far_sign if rail_far else near_sign) if s == _LAT_RAIL else far_sign
            if s == _LAT_ADV and not rail_far:
                sign = far_sign
            minor[i] = sign * (src_half + lat_hop.get(i, rank_hop) + _minor_half(i))
    # A chip-bearing FORK holds its guard like every straight run: the
    # curve's own arc length floors at the chip-run law, and the pair bumps
    # outward TOGETHER (the corpus pair is symmetric about the spine — the
    # hand file's 170 modules give its forks ~145px of arc for the 40px
    # chips; a snugger pair must buy that run back with offset).
    fork_bump = 0.0
    for _k, e in sh.forward:
        if spec.nodes[e.source].station != "decision" or seat.get(e.target) not in (_DEV_NEAR, _DEV_FAR):
            continue
        if not (e.label and e.label_style == "chip"):
            continue
        cw, _ch2 = solve_chip_box(e.label, ctx.cfg)
        src_half = ax.box_minor(*boxes[e.source]) / 2
        d_major = (
            rank_center[rank[e.target]] - ax.box_major(*boxes[e.target]) / 2 - standoff - rank_center[rank[e.source]]
        )
        d_minor = abs(minor[e.target]) - src_half
        bump = 0.0
        for _ in range(8):
            dm = d_minor + bump
            # The chip seats at t=0.5; its span along the run is its BOX
            # projected on the curve's own mid tangent (the battery's exact
            # read) — B'(0.5) ∝ P3 + P2 - P1 - P0 for this quarter-pipe.
            # The box never rotates, so its WIDTH pairs with the screen-x
            # tangent component: the minor term on the vertical cell, the
            # major term on the horizontal one.
            tmn, tmj = dm * (2.0 - _FORK_PULL), 1.5 * d_major
            tn = (tmn * tmn + tmj * tmj) ** 0.5 or 1.0
            if ax.flow == "down":
                span = cw * abs(tmn / tn) + CHIP_H * abs(tmj / tn)
            else:
                span = cw * abs(tmj / tn) + CHIP_H * abs(tmn / tn)
            ln = cubic_len(0.0, 0.0, _FORK_PULL * dm, 0.0, dm, d_major / 2, dm, d_major)
            # +2 margin: the battery reads a SAMPLED polyline whose local
            # segment can sit a hair steeper than the exact mid tangent; the
            # arc also grows sublinearly with the offset, so the deficit is
            # doubled each pass instead of chased 1:1.
            if ln >= _run_floor(span, ctx.ch.chip_visible_run) + 2.0:
                break
            bump += 2.0 * (_run_floor(span, ctx.ch.chip_visible_run) + 2.0 - ln)
        fork_bump = max(fork_bump, bump)
    if fork_bump:
        for i, s in seat.items():
            if s in (_DEV_NEAR, _DEV_FAR):
                minor[i] += fork_bump if minor[i] > 0 else -fork_bump
    # Externals seat at the world margin on the side opposite the rail
    # (tap/cycle-tap-v3's world-margin zone); a tap run floors at its own
    # chip's need like every other chip-bearing straight run.
    ext_sign = near_sign if rail_far else far_sign
    non_ext = [i for i in minor if seat.get(i) != _EXT]
    edge_min = min((minor[i] - _minor_half(i) for i in non_ext), default=-spine_half)
    edge_max = max((minor[i] + _minor_half(i) for i in non_ext), default=spine_half)
    ext_need: dict[int, float] = {}
    for _k, e in sh.taps:
        ext_i = e.source if e.circuit == "tap-in" else e.target
        ext_need[ext_i] = max(ext_need.get(ext_i, 0.0), _chip_run_need(ctx, e, vertical_run=ax.flow != "down"))
    # One world-margin COLUMN: every external shares the widest tap run,
    # so their inner faces align down the margin (tap/cycle-tap-v3's own
    # zone — two externals, one column).
    ext_gap = max([rank_hop, *ext_need.values()]) if ext_need else rank_hop
    for i, s in seat.items():
        if s == _EXT:
            base = (edge_min - ext_gap - _minor_half(i)) if ext_sign < 0 else (edge_max + ext_gap + _minor_half(i))
            minor[i] = base
    # Rail minor: clear of everything on its side — and far enough out that
    # the rail's MID run (where every return chip seats) stands the chip off
    # content by its half plus the bare clearance.
    all_min = min((minor[i] - _minor_half(i) for i in minor), default=-spine_half)
    all_max = max((minor[i] + _minor_half(i) for i in minor), default=spine_half)
    mid_chip_half = 0.0
    rail_hang = 0.0
    if sh.ret is not None:
        ret_edge = sh.ret[1]
        if ret_edge.label and ret_edge.label_style == "chip":
            # Every return chip rides the rail's own MID run with equal
            # visible runs both sides (the expression corpus seats each
            # return claim at the loop's visual center — retry "attempt
            # n+1", nested "no · go again", the flywheel's compounding chip
            # with its measured equal runs) — the rail stands off content
            # by the chip's half plus the bare clearance, so the chip never
            # reaches back over the spine's wires.
            cw, _chh = solve_chip_box(ret_edge.label, ctx.cfg)
            mid_chip_half = (cw if ax.flow == "down" else CHIP_H) / 2
            if ret_edge.meter:
                if ax.flow == "down":
                    # The gauge's plate outreaches its chip on the vertical
                    # rail (pads + the lead mark, each side) — the rail
                    # stands off content for the whole piece.
                    mid_chip_half += _lcfg(ctx, "meter_rail_reach", 26.0)
                else:
                    # On the horizontal rail the gauge HANGS OUTWARD below
                    # the chip — the canvas reserves the hang past the rail
                    # line instead of wasting it as inward air (the hang
                    # once overlapped the caption band).
                    rail_hang = _lcfg(ctx, "meter_rail_hang", 43.0)
        rail_m = all_max + rail_clear + mid_chip_half if rail_far else all_min - rail_clear - mid_chip_half
        rail_edge = rail_m + rail_hang if rail_far else rail_m - rail_hang
    else:
        # The unrolled ladder has no rail — the bus lives inside the
        # content extents, so the phantom rail adds nothing.
        rail_m = all_max if rail_far else all_min
        rail_edge = rail_m

    # ── Canvas + origin ─────────────────────────────────────────────────
    minor_lo = min(all_min, rail_edge) - ch.margin_x
    minor_hi = max(all_max, rail_edge) + ch.margin_x
    minor_off = -minor_lo
    span_minor = minor_hi - minor_lo
    span_major = content_major_end + ch.footer_h
    if ax.flow == "down":
        width, height = int(span_minor), int(span_major)
    else:
        width, height = int(span_major), int(span_minor)

    def _pt(major: float, m: float) -> tuple[float, float]:
        return ax.point(major, m + minor_off)

    # ── Place nodes ─────────────────────────────────────────────────────
    placed: dict[int, NodePlacement] = {}
    bands: list[LaneBand] = []
    for i, node in enumerate(spec.nodes):
        if i in sh.member_scope:
            continue
        w, h = boxes[i]
        cxy = _pt(rank_center[rank[i]], minor[i])
        if _station(node) == "scope":
            sl = scope_layouts[i]
            band, inner_placed = _place_scope(ctx, sh, i, sl, cxy)
            bands.append(band)
            for m_i, pl in inner_placed.items():
                placed[m_i] = pl
            # The scope itself paints as its enclosure band — no card; its
            # box is remembered for port math via a synthetic placement kept
            # OUT of nodes_paint.
            placed[i] = _scope_anchor_placement(i, node, cxy, w, h)
        else:
            cls2 = _chassis_cls(node, seat.get(i, ""))
            pl = place_node(ctx, node, i, cxy[0], cxy[1], w=w, h=h, chassis_class=cls2, family_marked=i in fam_col)
            placed[i] = _partition_dress(node, pl)
    if sh.gather is not None:
        bands.append(_ladder_band(ctx, sh, placed))
    # ── Edges ───────────────────────────────────────────────────────────
    rail_screen = rail_m + minor_off
    geos = _build_geos(
        ctx, ax, sh, rank, seat, minor, rank_center, placed, scope_layouts, standoff, rail_screen, rail_r
    )
    scope_ids = set(scope_layouts)
    nodes_paint = [placed[i] for i in sorted(placed) if i not in scope_ids]
    return finish_layout(
        ctx,
        width=width,
        height=height,
        nodes_paint=nodes_paint,
        geos=geos,
        lane_bands=tuple(bands),
    )


def _decision_half_minor(
    ctx: SolverContext,
    ax: AxisMap,
    boxes: dict[int, tuple[float, float]],
    rank: dict[int, int],
    lateral_i: int,
) -> float:
    """The minor half-extent of the decision a lateral seat hangs off —
    found by rank (the lateral shares its decision's rank by construction)."""
    r = rank[lateral_i]
    halves = [
        ax.box_minor(*boxes[j]) / 2
        for j, rj in rank.items()
        if rj == r and j != lateral_i and j in boxes and ctx.spec.nodes[j].station == "decision"
    ]
    return max(halves, default=ax.box_minor(*boxes[lateral_i]) / 2)


def _partition_dress(node: DiagramNode, pl: NodePlacement) -> NodePlacement:
    """Partition hue on names AND identity marks (the anchor's law): advance
    names ride the accent (``dname``) with a signal-tone mark (the stair-up
    ``cyt1-gA``), discard/exhausted names recede to the muted name voice with
    a wire-grade complement mark (the undo-arc ``cyt1-gC``) — every wrapped
    name line dresses with the first (both keep lines render ``dname``).
    Wire hue is the edge pass's job, never repeated here. Only a stroke-drawn
    ink mark takes the partition tone — a brand/full/hue mark keeps its own
    color, the same precedence every other promotion in the kit obeys."""
    if node.partition not in ("advance", "discard", "exhausted"):
        return pl
    cls = "dname" if node.partition == "advance" else "mname"
    # A TERMINAL wears its partition as a permanent finish (the corpus's
    # -term / -flat classes): advance = the signal wash with a signal-edge
    # rim, exhausted/discard = the flat page tone — the chromatic gestalt
    # that lets an observer read the outcome before reading a word.
    dress = ""
    if node.station == "terminal":
        dress = "termadvbg" if node.partition == "advance" else "termflatbg"
    dressed = replace(
        pl,
        label=replace(pl.label, cls=cls),
        label_lines=tuple(replace(t, cls=cls) for t in pl.label_lines),
        card_dress=dress,
    )
    g = pl.glyph
    if g is not None and g.stroke_w and g.tint == "ink" and not g.gradient:
        dressed = replace(
            dressed, glyph=replace(g, signal=node.partition == "advance", comp=node.partition != "advance")
        )
    return dressed


# ── Scope (the nested cell) ─────────────────────────────────────────────


@dataclass
class _ScopeLayout:
    """A solved scope in LOCAL coordinates (its own center at 0,0)."""

    w: float
    h: float
    member_boxes: dict[int, tuple[float, float, float, float]]  # i -> (cx, cy, w, h) local screen
    rail_local: float  # mini-rail's local screen offset from center along the INNER rail axis
    label: str


def _scope_family_marked(ctx: SolverContext, members: list[int]) -> bool:
    """The scope circuit's mixed-family fact (the column law) — one
    derivation shared by the solve and place halves, so the two can never
    disagree about where the inner family's text column sits."""
    return (
        ctx.ch.width_policy == "aligned"
        and len(members) >= 2
        and family_carries_marks(ctx, [ctx.spec.nodes[m] for m in members])
    )


def _solve_scope(ctx: SolverContext, ax: AxisMap, sh: _Shape, scope_i: int) -> _ScopeLayout:
    """Inner circuit solves FIRST, in local screen coordinates: members in a
    row ACROSS the outer flow (orthogonal orientation decoupling —
    cycle-nested's inner circuit runs laterally against the outer vertical),
    a mini-rail beneath them carrying the inner return, the enclosure box
    wrapping row + rail + the label band."""
    spec = ctx.spec
    members = sorted(sh.members[scope_i], key=lambda m: _inner_order(sh, scope_i).index(m))
    pad_side = _lcfg(ctx, "scope_pad_side", 16.0)
    pad_top = _lcfg(ctx, "scope_pad_top", 56.0)
    rail_gap = _lcfg(ctx, "scope_rail_gap", 46.0)
    pad_bottom = _lcfg(ctx, "scope_pad_bottom", 50.0)
    member_gap = _lcfg(ctx, "scope_member_gap", 70.0)
    inner_ret = sh.inner_ret.get(scope_i)
    if inner_ret is not None and inner_ret[1].meter:
        # The inner return carries a meter: the enclosure grows below the
        # mini-rail so the gauge seats inside the band (the lap-counter
        # scope stands 258 tall against the plain inline scope's 210).
        pad_bottom += _lcfg(ctx, "scope_meter_extra", 48.0)
    fam = _scope_family_marked(ctx, members)
    dims = {m: solve_node_box(ctx, spec.nodes[m], m, chassis_class="node2", family_marked=fam)[:2] for m in members}
    if ctx.ch.width_policy == "aligned" and len(dims) >= 2:
        # The inner circuit is one aligned family like the outer seat
        # families: the corpus draws its members at a single shared width
        # (the nested hand files' 3 x 144 columns) — re-solved at the
        # family max so heights stay content-true.
        shared = max(ax.box_minor(w, h) for (w, h) in dims.values())
        dims = {
            m: solve_node_box(ctx, spec.nodes[m], m, chassis_class="node2", min_w=shared, family_marked=fam)[:2]
            for m in members
        }
    # The inner row runs along the outer MINOR axis; in screen terms that is
    # horizontal for the vertical loop and vertical for the horizontal one.
    row_axis_w = [ax.box_minor(w, h) for (w, h) in dims.values()]
    row_len = sum(row_axis_w) + member_gap * (len(members) - 1)
    inner_ret = sh.inner_ret.get(scope_i)
    if inner_ret is not None and len(members) > 1:
        # The mini-rail is a chip-bearing run like any other: it floors at
        # its own chip's need (a two-member circuit once seated a wide
        # guard on a rail shorter than the occlusion law allows), and the
        # member gap absorbs the slack.
        # The graded run is the rail's colinear leg between its corners —
        # roughly the END members' center-to-center span — so the row must
        # hold the chip's need PLUS the end members' half-widths.
        need = _chip_run_need(ctx, inner_ret[1], vertical_run=ax.flow != "down")
        # ... plus the corners' radii and endpoint standoffs the drawn leg
        # loses at both ends.
        need += (row_axis_w[0] + row_axis_w[-1]) / 2 + 24.0
        if need > row_len:
            member_gap += (need - row_len) / (len(members) - 1)
            row_len = need
    row_thick = max(ax.box_major(w, h) for (w, h) in dims.values())
    inner_w = row_len + 2 * pad_side
    inner_h = pad_top + row_thick + rail_gap + pad_bottom
    member_boxes: dict[int, tuple[float, float, float, float]] = {}
    cursor = -row_len / 2
    row_center_major = -inner_h / 2 + pad_top + row_thick / 2
    for m in members:
        w, h = dims[m]
        extent = ax.box_minor(w, h)
        c_minor = cursor + extent / 2
        cx, cy = ax.point(row_center_major, c_minor)
        member_boxes[m] = (cx, cy, w, h)
        cursor += extent + member_gap
    rail_local = row_center_major + row_thick / 2 + rail_gap
    label = spec.nodes[scope_i].label
    if ax.flow == "down":
        return _ScopeLayout(w=inner_w, h=inner_h, member_boxes=member_boxes, rail_local=rail_local, label=label)
    return _ScopeLayout(w=inner_h, h=inner_w, member_boxes=member_boxes, rail_local=rail_local, label=label)


def _inner_order(sh: _Shape, scope_i: int) -> list[int]:
    """Members in circuit order, from the inner return's target."""
    k_ret = sh.inner_ret[scope_i]
    start = k_ret[1].target
    nxt = {e.source: e.target for _, e in sh.inner[scope_i]}
    order = [start]
    while order[-1] in nxt and nxt[order[-1]] not in order:
        order.append(nxt[order[-1]])
    for m in sh.members[scope_i]:
        if m not in order:
            order.append(m)
    return order


def _scope_anchor_placement(i: int, node: DiagramNode, cxy: tuple[float, float], w: float, h: float) -> NodePlacement:
    """A geometry-only anchor for port math (never painted): the scope IS
    the node for outer port purposes."""
    return NodePlacement(
        index=i,
        node_id=node.id or f"n{i}",
        shape="rect",
        box=RectSpec(x=cxy[0] - w / 2, y=cxy[1] - h / 2, w=w, h=h, rx=16.0),
        role="default",
        stroke_width=0.0,
        stroke_dasharray="",
        accent_index=-1,
        label=DiagramText(x=cxy[0], y=cxy[1], text="", cls="rlabel"),
    )


def _ladder_band(ctx: SolverContext, sh: _Shape, placed: dict[int, NodePlacement]) -> LaneBand:
    """The unrolled ladder's budget enclosure (the unrolled specimen: the
    region pads the attempts 26 across the flow and 34 along it, rx 18 —
    the terminals stay OUTSIDE). Its legend is the chip piece, centered in
    the widest clear run of the sky rim between the gather arms' crossings,
    its text derived from the ladder's own length."""
    assert sh.gather is not None
    g, arms = sh.gather
    sources = [e.source for _, e in arms]
    boxes = [placed[i].box for i in sources]
    pad_x = _lcfg(ctx, "unrolled_pad_across", 26.0)
    pad_y = _lcfg(ctx, "unrolled_pad_along", 34.0)
    x0 = min(b.x for b in boxes) - pad_x
    x1 = max(b.x + b.w for b in boxes) + pad_x
    y0 = min(b.y for b in boxes) - pad_y
    y1 = max(b.y + b.h for b in boxes) + pad_y
    box = RectSpec(x=x0, y=y0, w=x1 - x0, h=y1 - y0, rx=18.0)
    # The legend always rides a HORIZONTAL rim (its text is horizontal).
    # On the lateral ladder that is the sky rim facing the gather — the
    # arms pierce it at each source's center and the plate seats in the
    # widest clear run. On the vertical ladder the arms pierce a SIDE rim
    # instead, so the top rim is clear and the plate centers there (the
    # bottom rim carries the exhaust exit).
    g_box = placed[g].box
    gather_vertical = abs(g_box.y + g_box.h / 2 - (y0 + y1) / 2) > abs(g_box.x + g_box.w / 2 - (x0 + x1) / 2)
    if gather_vertical:
        rim_y = y0 if g_box.y + g_box.h / 2 < (y0 + y1) / 2 else y1
        crossings = sorted(b.x + b.w / 2 for b in boxes)
    else:
        rim_y = y0
        crossings = []
    label = str((ctx.engine.get("loop") or {}).get("unrolled_legend", "RETRY BUDGET · MAX {n}")).format(n=len(sources))
    plate_h = 22.0
    plate_w = measure_voice(label, ctx.cfg.scope_header_voice) + 28.0
    edges_x = [x0, *crossings, x1]
    runs = [(edges_x[i], edges_x[i + 1]) for i in range(len(edges_x) - 1)]
    lo, hi = max(runs, key=lambda r: r[1] - r[0])
    plate_cx = min(max((lo + hi) / 2, x0 + plate_w / 2), x1 - plate_w / 2)
    plate_x = plate_cx - plate_w / 2
    header_box = RectSpec(x=plate_x, y=rim_y - plate_h / 2, w=plate_w, h=plate_h, rx=plate_h / 2)
    header = DiagramText(x=plate_x + 14.0, y=rim_y + 4.2, text=label, cls="eyeb", anchor="start")
    scope_dash = str((ctx.engine.get("loop") or {}).get("scope_dash", "8 7"))
    return LaneBand(box=box, header=header, ground="enclosure", header_box=header_box, dash=scope_dash)


def _place_scope(
    ctx: SolverContext,
    sh: _Shape,
    scope_i: int,
    sl: _ScopeLayout,
    cxy: tuple[float, float],
) -> tuple[LaneBand, dict[int, NodePlacement]]:
    """Translate the locally-solved scope to its spine seat: the dashed
    enclosure band with its legend plate straddling the top border
    (cycle-nested's region grammar), members placed as ordinary cards."""
    cx, cy = cxy
    box = RectSpec(x=cx - sl.w / 2, y=cy - sl.h / 2, w=sl.w, h=sl.h, rx=18.0)
    label = sl.label.upper()
    # The legend is THE chip piece: a capsule plate (h 22, rx h/2, 14px text
    # pads) in the eyebrow voice, centered ON the rim line. On the vertical
    # cell the entry wire pierces the top rim at the spine, so the plate
    # seats on the left clear run (the inline scope specimen: inset 73 from
    # the region's left edge); an unpierced rim centers it (aside/lateral).
    plate_h = 22.0
    plate_w = measure_voice(label, ctx.cfg.scope_header_voice) + 28.0
    ax = AxisMap.for_slug(ctx.slug)
    if ax.flow == "down":
        inset = float((ctx.engine.get("loop") or {}).get("scope_header_inset", 73.0))
        plate_x = box.x + inset
    else:
        plate_x = cx - plate_w / 2
    header_box = RectSpec(x=plate_x, y=box.y - plate_h / 2, w=plate_w, h=plate_h, rx=plate_h / 2)
    header = DiagramText(x=plate_x + 14.0, y=box.y + 4.2, text=label, cls="eyeb", anchor="start")
    # The expression corpus's enclosure stroke — a config knob so the kit
    # dash grammar can enumerate it.
    scope_dash = str((ctx.engine.get("loop") or {}).get("scope_dash", "8 7"))
    band = LaneBand(box=box, header=header, ground="enclosure", header_box=header_box, dash=scope_dash)
    placed: dict[int, NodePlacement] = {}
    fam = _scope_family_marked(ctx, list(sl.member_boxes))
    for m, (lx, ly, w, h) in sl.member_boxes.items():
        pl = place_node(ctx, ctx.spec.nodes[m], m, cx + lx, cy + ly, w=w, h=h, chassis_class="node2", family_marked=fam)
        placed[m] = pl
    return band, placed


# ── Edge geometry ───────────────────────────────────────────────────────


def _face_point(ax: AxisMap, pl: NodePlacement, *, major_dir: int, minor_dir: int = 0) -> tuple[float, float]:
    """A box-face midpoint in screen coords: ``major_dir`` -1/+1 = the
    near/far face along the flow; ``minor_dir`` -1/+1 = the near/far face
    across it (0 = centered)."""
    b = pl.box
    cx, cy = b.x + b.w / 2, b.y + b.h / 2
    if major_dir:
        if ax.flow == "down":
            return cx, b.y if major_dir < 0 else b.y + b.h
        return (b.x if major_dir < 0 else b.x + b.w), cy
    if ax.flow == "down":
        return (b.x if minor_dir < 0 else b.x + b.w), cy
    return cx, (b.y if minor_dir < 0 else b.y + b.h)


def _cubic(
    k: int,
    p0: tuple[float, float],
    c1: tuple[float, float],
    c2: tuple[float, float],
    p1: tuple[float, float],
    *,
    label_pos: tuple[float, float] | None = None,
    end_tangent: tuple[float, float] | None = None,
) -> EdgeGeo:
    d = f"M {fmt(p0[0])},{fmt(p0[1])} C {fmt(c1[0])},{fmt(c1[1])} {fmt(c2[0])},{fmt(c2[1])} {fmt(p1[0])},{fmt(p1[1])}"
    length = cubic_len(p0[0], p0[1], c1[0], c1[1], c2[0], c2[1], p1[0], p1[1])
    return EdgeGeo(
        index=k,
        d=d,
        sx=p0[0],
        sy=p0[1],
        tx=p1[0],
        ty=p1[1],
        length=length,
        label_pos=label_pos,
        label_bare=label_pos is not None,
        end_tangent=end_tangent,
    )


def _casteljau_mid(
    p0: tuple[float, float], c1: tuple[float, float], c2: tuple[float, float], p1: tuple[float, float]
) -> tuple[float, float]:
    """De Casteljau t=0.5 — where a curve's guard chip seats (the anchor's
    own 'no'/'yes' chips measure within ~1.5px of exactly this point)."""

    def mid(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    q0, q1, q2 = mid(p0, c1), mid(c1, c2), mid(c2, p1)
    r0, r1 = mid(q0, q1), mid(q1, q2)
    return mid(r0, r1)


def _edge_hue(ctx: SolverContext, e: ResolvedEdge) -> tuple[bool, bool]:
    """(accent, complement) for a decision exit — the chromatic compile."""
    src = ctx.spec.nodes[e.source]
    tgt = ctx.spec.nodes[e.target]
    if src.station != "decision":
        return False, False
    if tgt.partition == "advance":
        return True, False
    if tgt.partition in ("discard", "exhausted") or tgt.station == "decision":
        return False, True
    return False, False


def _build_geos(
    ctx: SolverContext,
    ax: AxisMap,
    sh: _Shape,
    rank: dict[int, int],
    seat: dict[int, str],
    minor: dict[int, float],
    rank_center: dict[int, float],
    placed: dict[int, NodePlacement],
    scope_layouts: dict[int, _ScopeLayout],
    standoff: float,
    rail_screen: float,
    rail_r: float,
) -> list[EdgeGeo]:
    geos: list[EdgeGeo] = []
    spec = ctx.spec
    _ = rank_center

    def chip_pos(e: ResolvedEdge) -> bool:
        return bool(e.label and e.label_style == "chip")

    for k, e in enumerate(ctx.edges):
        scope = sh.member_scope.get(e.source)
        if scope is not None and sh.member_scope.get(e.target) == scope:
            geos.append(_inner_geo(ctx, ax, sh, scope, k, e, placed, scope_layouts[scope]))
            continue
        accent, comp = _edge_hue(ctx, e)
        src_pl, tgt_pl = placed[e.source], placed[e.target]
        s_seat, t_seat = seat[e.source], seat[e.target]
        s_node = spec.nodes[e.source]
        if e.circuit == "return":
            geos.append(_rail_geo(ctx, ax, k, e, src_pl, tgt_pl, seat, rail_screen, rail_r, standoff, chip=chip_pos(e)))
        elif e.circuit in ("tap-in", "tap-out"):
            geos.append(_tap_geo(ax, k, e, src_pl, tgt_pl, standoff, chip=chip_pos(e)))
        elif t_seat == _GATHER and sh.gather is not None:
            stem_src = next(
                (ee.source for _, ee in sh.gather[1] if rank.get(ee.source) == rank.get(e.target)),
                sh.gather[1][-1][1].source,
            )
            geos.append(_bus_geo(ctx, ax, k, e, src_pl, tgt_pl, standoff, stem=e.source == stem_src, chip=chip_pos(e)))
        elif s_node.station == "decision" and t_seat in (_DEV_NEAR, _DEV_FAR):
            # Quarter-pipe fork: departs the vertex across the flow, arrives
            # the deviation card's near face along it.
            sign = 1 if minor[e.target] > minor[e.source] else -1
            p0 = _face_point(ax, src_pl, major_dir=0, minor_dir=sign)
            p1 = _face_point(ax, tgt_pl, major_dir=-1)
            p1 = _stand(p1, ax, standoff, major_dir=-1)
            dm = (p1[0] - p0[0]) if ax.flow == "down" else (p1[1] - p0[1])
            if ax.flow == "down":
                c1 = (p0[0] + _FORK_PULL * dm, p0[1])
                c2 = (p1[0], (p0[1] + p1[1]) / 2)
                tangent = (0.0, 1.0)
            else:
                c1 = (p0[0], p0[1] + _FORK_PULL * dm)
                c2 = ((p0[0] + p1[0]) / 2, p1[1])
                tangent = (1.0, 0.0)
            lp = _casteljau_mid(p0, c1, c2, p1) if chip_pos(e) else None
            geo = _cubic(k, p0, c1, c2, p1, label_pos=lp, end_tangent=tangent)
            geos.append(replace(geo, accent_wire=accent, comp_wire=comp))
        elif s_seat in (_DEV_NEAR, _DEV_FAR) and t_seat == _SPINE:
            # Merge: an S-curve along the flow converging on the target's
            # near face CENTER — both pair members share one drawn arrival.
            # Specimen pulls, not midpoints: the anchor's merge (M 210,576
            # C 210,640 400,610 400,664) departs the dev card VERTICALLY for
            # 0.73 of the travel and arrives the apex vertically from 0.61 —
            # the controls overshoot the midpoint, so the curve hugs the flow
            # at both ends and crosses in one organic sweep instead of a V.
            p0 = _face_point(ax, src_pl, major_dir=1)
            p1 = _stand(_face_point(ax, tgt_pl, major_dir=-1), ax, standoff, major_dir=-1)
            if ax.flow == "down":
                dmaj = p1[1] - p0[1]
                c1 = (p0[0], p0[1] + _MERGE_DEPART * dmaj)
                c2 = (p1[0], p1[1] - _MERGE_ARRIVE * dmaj)
                tangent = (0.0, 1.0)
            else:
                dmaj = p1[0] - p0[0]
                c1 = (p0[0] + _MERGE_DEPART * dmaj, p0[1])
                c2 = (p1[0] - _MERGE_ARRIVE * dmaj, p1[1])
                tangent = (1.0, 0.0)
            geos.append(_cubic(k, p0, c1, c2, p1, end_tangent=tangent))
        elif t_seat in (_LAT_ADV, _LAT_RAIL):
            # At-rank lateral hop: a short straight run across the flow.
            sign = 1 if minor[e.target] > minor[e.source] else -1
            p0 = _face_point(ax, src_pl, major_dir=0, minor_dir=sign)
            p1 = _stand(_face_point(ax, tgt_pl, major_dir=0, minor_dir=-sign), ax, standoff, minor_dir=-sign)
            lp = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2) if chip_pos(e) else None
            geos.append(
                replace(
                    _line(k, p0, p1, label_pos=lp),
                    accent_wire=accent,
                    comp_wire=comp,
                    end_tangent=_unit(p0, p1),
                )
            )
        else:
            # Spine continuation (process/decision/scope -> next rank).
            p0 = _face_point(ax, src_pl, major_dir=1)
            p1 = _stand(_face_point(ax, tgt_pl, major_dir=-1), ax, standoff, major_dir=-1)
            lp = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2) if chip_pos(e) else None
            geos.append(
                replace(
                    _line(k, p0, p1, label_pos=lp),
                    accent_wire=accent,
                    comp_wire=comp,
                    end_tangent=_unit(p0, p1),
                )
            )
    return geos


def _unit(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = (dx * dx + dy * dy) ** 0.5 or 1.0
    return dx / n, dy / n


def _stand(
    p: tuple[float, float], ax: AxisMap, standoff: float, *, major_dir: int = 0, minor_dir: int = 0
) -> tuple[float, float]:
    """Back the arrival point off the target face by the family standoff
    (the corpus-enrolled 2px — endpoints asserted 0.5-3.5px off the card).
    ``major_dir``/``minor_dir`` name WHICH face of the target the arrival
    lands on (the same convention ``_face_point`` reads); the point retreats
    outward along that face's own normal — coordinate += dir * standoff."""
    if not standoff:
        return p
    if major_dir:
        return (p[0], p[1] + major_dir * standoff) if ax.flow == "down" else (p[0] + major_dir * standoff, p[1])
    if minor_dir:
        return (p[0] + minor_dir * standoff, p[1]) if ax.flow == "down" else (p[0], p[1] + minor_dir * standoff)
    return p


def _line(
    k: int, p0: tuple[float, float], p1: tuple[float, float], *, label_pos: tuple[float, float] | None = None
) -> EdgeGeo:
    return EdgeGeo(
        index=k,
        d=line_d(p0[0], p0[1], p1[0], p1[1]),
        sx=p0[0],
        sy=p0[1],
        tx=p1[0],
        ty=p1[1],
        length=line_len(p0[0], p0[1], p1[0], p1[1]),
        label_pos=label_pos,
        label_bare=label_pos is not None,
    )


def _bus_geo(
    ctx: SolverContext,
    ax: AxisMap,
    k: int,
    e: ResolvedEdge,
    src_pl: NodePlacement,
    tgt_pl: NodePlacement,
    standoff: float,
    *,
    stem: bool,
    chip: bool,
) -> EdgeGeo:
    """The gather bus — the unrolled ladder's named merge piece, sibling of
    the gather knot. Each source raises an arm from its sky face, fillets
    (bus_r) onto the shared bus line bus_gap off the cards, and runs to the
    junction under the gather terminal; the junction-aligned arm carries
    the single marked STEM into the terminal — one drawn arrival, exactly
    the specimen's construction (arms bare, the arrowhead on the stem)."""
    _ = e
    bus_r = _lcfg(ctx, "bus_r", 18.0)
    bus_gap = _lcfg(ctx, "bus_gap", 58.0)
    down = ax.flow == "down"
    g_box = tgt_pl.box
    g_min_c = (g_box.x + g_box.w / 2) if down else (g_box.y + g_box.h / 2)
    s_min_c = (src_pl.box.x + src_pl.box.w / 2) if down else (src_pl.box.y + src_pl.box.h / 2)
    sign = -1 if g_min_c < s_min_c else 1
    p0 = _face_point(ax, src_pl, major_dir=0, minor_dir=sign)
    p0_maj, p0_min = (p0[1], p0[0]) if down else (p0[0], p0[1])
    j_maj = (g_box.y + g_box.h / 2) if down else (g_box.x + g_box.w / 2)
    bus_min = p0_min + sign * bus_gap

    def pt(maj: float, mn: float) -> tuple[float, float]:
        return (mn, maj) if down else (maj, mn)

    if stem:
        # Straight through the bus into the terminal's near face.
        p1 = _stand(_face_point(ax, tgt_pl, major_dir=0, minor_dir=-sign), ax, standoff, minor_dir=-sign)
        p1_min = p1[0] if down else p1[1]
        lp = pt(j_maj, (bus_min + p1_min) / 2) if chip else None
        geo = _line(k, p0, p1, label_pos=lp)
        return replace(geo, end_tangent=_unit(p0, p1))
    r = min(bus_r, bus_gap - 1.0, max(1.0, abs(j_maj - p0_maj) - 1.0))
    mdir = 1.0 if j_maj > p0_maj else -1.0
    a = pt(p0_maj, bus_min - sign * r)
    ctrl = pt(p0_maj, bus_min)
    b = pt(p0_maj + mdir * r, bus_min)
    j = pt(j_maj, bus_min)
    d = (
        f"M {fmt(p0[0])},{fmt(p0[1])} L {fmt(a[0])},{fmt(a[1])} "
        f"Q {fmt(ctrl[0])},{fmt(ctrl[1])} {fmt(b[0])},{fmt(b[1])} L {fmt(j[0])},{fmt(j[1])}"
    )
    length = line_len(p0[0], p0[1], a[0], a[1]) + 1.5708 * r + line_len(b[0], b[1], j[0], j[1])
    lp = pt((p0_maj + mdir * r + j_maj) / 2, bus_min) if chip else None
    return EdgeGeo(
        index=k,
        d=d,
        sx=p0[0],
        sy=p0[1],
        tx=j[0],
        ty=j[1],
        length=length,
        polyline=(p0, a, b, j),
        end_tangent=(0.0, mdir) if down else (mdir, 0.0),
        label_pos=lp,
        label_bare=lp is not None,
        marker_override="none",
    )


def _rail_geo(
    ctx: SolverContext,
    ax: AxisMap,
    k: int,
    e: ResolvedEdge,
    src_pl: NodePlacement,
    tgt_pl: NodePlacement,
    seat: dict[int, str],
    rail_screen: float,
    rail_r: float,
    standoff: float,
    *,
    chip: bool,
) -> EdgeGeo:
    """The margin rail — the one lawful long route (HVH orthogonal at the
    fixed rail offset, two rounded corners). The guard/annotation chip seats
    at the rail's own MID run with equal visible runs both sides (the
    expression corpus's seating law — every return claim reads at the
    loop's visual center)."""
    src_minor_c = src_pl.box.x + src_pl.box.w / 2 if ax.flow == "down" else src_pl.box.y + src_pl.box.h / 2
    rail_side = 1 if rail_screen > src_minor_c else -1
    p0 = _face_point(ax, src_pl, major_dir=0, minor_dir=rail_side)
    p1 = _stand(_face_point(ax, tgt_pl, major_dir=0, minor_dir=rail_side), ax, standoff, minor_dir=rail_side)
    _ = ctx
    if ax.flow == "down":
        d, length, poly, tangent = orthogonal_d(p0[0], p0[1], p1[0], p1[1], mid=rail_screen, first_axis="h", r=rail_r)
        entry_leg_mid = ((rail_screen + p1[0]) / 2, p1[1])
        rail_run_mid = (rail_screen, (p0[1] + p1[1]) / 2)
    else:
        d, length, poly, tangent = orthogonal_d(p0[0], p0[1], p1[0], p1[1], mid=rail_screen, first_axis="v", r=rail_r)
        entry_leg_mid = (p1[0], (rail_screen + p1[1]) / 2)
        rail_run_mid = ((p0[0] + p1[0]) / 2, rail_screen)
    _ = entry_leg_mid
    lp = rail_run_mid if (chip or e.accumulates) else None
    _ = seat
    return EdgeGeo(
        index=k,
        d=d,
        sx=p0[0],
        sy=p0[1],
        tx=p1[0],
        ty=p1[1],
        length=length,
        polyline=poly,
        end_tangent=tangent,
        label_pos=lp,
        label_bare=lp is not None,
    )


def _tap_geo(
    ax: AxisMap,
    k: int,
    e: ResolvedEdge,
    src_pl: NodePlacement,
    tgt_pl: NodePlacement,
    standoff: float,
    *,
    chip: bool,
) -> EdgeGeo:
    """Tap edges run straight across the flow between the external's inner
    face and its partner's outer face. tap-in is the interrupting one-shot
    (complement, solid); tap-out is standing dress (conn dash-drift, never
    choreographed) — the register carve-out rides ``relation_default``."""
    scx = src_pl.box.x + src_pl.box.w / 2
    tcx = tgt_pl.box.x + tgt_pl.box.w / 2
    scy = src_pl.box.y + src_pl.box.h / 2
    tcy = tgt_pl.box.y + tgt_pl.box.h / 2
    if ax.flow == "down":
        sign = 1 if tcx > scx else -1
        p0 = _face_point(ax, src_pl, major_dir=0, minor_dir=sign)
        p1 = _stand(_face_point(ax, tgt_pl, major_dir=0, minor_dir=-sign), ax, standoff, minor_dir=-sign)
    else:
        sign = 1 if tcy > scy else -1
        p0 = _face_point(ax, src_pl, major_dir=0, minor_dir=sign)
        p1 = _stand(_face_point(ax, tgt_pl, major_dir=0, minor_dir=-sign), ax, standoff, minor_dir=-sign)
    lp = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2) if chip else None
    geo = _line(k, p0, p1, label_pos=lp)
    if e.circuit == "tap-out":
        return replace(geo, relation_default="drift", end_tangent=_unit(p0, p1))
    return replace(geo, comp_wire=True, end_tangent=_unit(p0, p1))


def _inner_geo(
    ctx: SolverContext,
    ax: AxisMap,
    sh: _Shape,
    scope_i: int,
    k: int,
    e: ResolvedEdge,
    placed: dict[int, NodePlacement],
    sl: _ScopeLayout,
) -> EdgeGeo:
    """Scope-internal wiring: straight runs between row neighbours; the
    inner return takes the mini-rail beneath the row (the same rail law at
    scope scale). Global edge indices are preserved — motion wiring indexes
    every geo by its resolved position."""
    src_pl, tgt_pl = placed[e.source], placed[e.target]
    scope_pl = placed[scope_i]
    _ = ctx
    if e.circuit == "return":
        rail = (
            scope_pl.box.y + scope_pl.box.h / 2 + sl.rail_local
            if ax.flow == "down"
            else scope_pl.box.x + scope_pl.box.w / 2 + sl.rail_local
        )
        p0 = _face_point(ax, src_pl, major_dir=1)
        p1 = _face_point(ax, tgt_pl, major_dir=1)
        first = "v" if ax.flow == "down" else "h"
        d, length, poly, tangent = orthogonal_d(p0[0], p0[1], p1[0], p1[1], mid=rail, first_axis=first, r=8.0)
        lp = ((p0[0] + p1[0]) / 2, rail) if ax.flow == "down" else (rail, (p0[1] + p1[1]) / 2)
        return EdgeGeo(
            index=k,
            d=d,
            sx=p0[0],
            sy=p0[1],
            tx=p1[0],
            ty=p1[1],
            length=length,
            polyline=poly,
            end_tangent=tangent,
            label_pos=lp if e.label else None,
            label_bare=bool(e.label),
        )
    sign = 1 if (tgt_pl.box.x > src_pl.box.x if ax.flow == "down" else tgt_pl.box.y > src_pl.box.y) else -1
    p0 = _face_point(ax, src_pl, major_dir=0, minor_dir=sign)
    p1 = _face_point(ax, tgt_pl, major_dir=0, minor_dir=-sign)
    geo = _line(k, p0, p1)
    return replace(geo, end_tangent=_unit(p0, p1))


register_solvers({"loop": solve_loop, "loop-horizontal": solve_loop})
