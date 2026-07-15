"""Hub solver: a focal node with spokes on canonical compass slots.

The hub is slot 0, centered on a square canvas; every other node is a spoke
placed in a compass SECTOR (N, NE, E, …). A spoke's sector resolves by a fixed
precedence — an explicit ``angle`` beats a node ``anchor`` beats an edge
``zone`` beats the role default (``role_zones[role]``) beats the direction
default (a spoke the hub points AT goes E, one pointing IN goes W).

Within a sector, angles are QUANTIZED — authored diagrams snap to canonical
slots, never free optimized angles. The rose is a global grid of half-step
slots (22.5° on the standard 8-way table); a single member takes its sector's
cardinal axis exactly; multiples take symmetric uniform-pitch arrangements
about it (45° steps preferred, 22.5° when neighbors crowd), so balanced
opposite sectors mirror across the hub by construction and within-sector
neighbor gaps are equal by construction. Slots past the sector border are
admissible only into EMPTY neighbor sectors, never more than one sector step
(east stays recognizably east). Contention resolves to the next canonical
arrangement, then to the nearest free slots, then raises — never to a nudge
(``distribution`` policies converge under quantization; explicit ``angle``
remains the caller's escape hatch). The ring radius is then the smallest
that clears the tightest adjacent pair globally. Spokes draw from the hub
boundary to each member boundary via ``route.route_path`` and the hub paints
LAST, so the card masks the inner stubs (the radial emanation precedent from
``radial.py``).

Everything visual-adjacent — sector centers, ring floor, card geometry —
comes from the ``hub`` config block and the chassis; this module holds
spatial policy only.
"""

from __future__ import annotations

import itertools
import math
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.anchors import boundary_anchor
from hyperweave.compose.diagram.annotate import Region
from hyperweave.compose.diagram.axial import solve_axial
from hyperweave.compose.diagram.chrome import measure_text_block, place_node, style_of
from hyperweave.compose.diagram.motion import lane_endpoints
from hyperweave.compose.diagram.paths import fmt, point_on, sample_path
from hyperweave.compose.diagram.route import route_path
from hyperweave.compose.diagram.sizing import hero_height_floor, solve_node_box
from hyperweave.compose.diagram.solver import finish_layout, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
from hyperweave.compose.matrix.cells import wrap_text_lines
from hyperweave.core.diagram import DiagramCapacityError, DiagramNode, NodeStyle

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hyperweave.compose.diagram.records import DiagramLayout, NodePlacement

_ZONES = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _hub_cfg(ctx: SolverContext) -> Mapping[str, Any]:
    return ctx.engine.get("hub") or {}


def _spoke_role(ctx: SolverContext, member: int) -> str:
    """The spoke's role from the first incident hub edge: a member the hub
    points AT is 'out', one pointing at the hub is 'in', 'read' if declared.
    Empty when no edge role is set (falls to the direction default)."""
    for e in ctx.edges:
        if e.source == 0 and e.target == member:
            return e.role or "out"
        if e.target == 0 and e.source == member:
            return e.role or "in"
    return ""


def _resolve_zone(ctx: SolverContext, member: int, node: DiagramNode, hub_cfg: Mapping[str, Any]) -> str:
    """Sector precedence (spec §5.2): edge angle wins (handled at placement,
    not here), then node.anchor, then edge.zone, then role_zones[role], then
    the direction default (in->W, out->E, read->role_zones.read)."""
    if node.anchor:
        return node.anchor
    role_zones = hub_cfg.get("role_zones") or {}
    for e in ctx.edges:
        incident = (e.source == 0 and e.target == member) or (e.target == 0 and e.source == member)
        if incident and e.zone:
            return str(e.zone)
    role = _spoke_role(ctx, member)
    if role and role in role_zones:
        return str(role_zones[role])
    return "E" if role == "out" else "W" if role == "in" else "E"


def _explicit_angle(ctx: SolverContext, member: int) -> float | None:
    """An edge's explicit ``angle`` overrides sector placement entirely."""
    for e in ctx.edges:
        if ((e.source == 0 and e.target == member) or (e.target == 0 and e.source == member)) and e.angle is not None:
            return float(e.angle)
    return None


def _arrangements(k: int, q: float, pair_splay: float | None = None) -> list[tuple[float, ...]]:
    """Preference-ordered candidate arrangements for k members about a sector
    cardinal: uniform-pitch runs on the q-grid, so within-sector neighbor
    gaps are equal BY CONSTRUCTION. Symmetric about the cardinal first (the
    mirror property), the authored wide pitch (45° steps) before the dense
    one (22.5°), center-shifted runs last (contention escapes that keep the
    equal-gap law). Even member counts need an even pitch multiple to stay
    on the grid. Every slot stays within ±3q — the one-step borrow cap.

    A PAIR packs at the measured splay first (frame-engine-hub seats its S
    pair at ±27.5° about the cardinal — card centers 62.5°/117.5° — tighter
    than any grid slot; ±q spread the pair across the whole sector and the
    fan read as exaggerated); grid runs stay as contention escapes."""
    if k == 1:
        return [(0.0,)]
    out: list[tuple[float, ...]] = []
    if k == 2 and pair_splay:
        out.append((-float(pair_splay), float(pair_splay)))
    pitches = (4 * q, 2 * q) if k % 2 == 0 else (2 * q, q)
    for shift in (0.0, -q, q, -2 * q, 2 * q):
        for pitch in pitches:
            offs = tuple(shift + (i - (k - 1) / 2.0) * pitch for i in range(k))
            if max(abs(o) for o in offs) <= 3 * q + 1e-9 and offs not in out:
                out.append(offs)
    return out


def _quantized_angles(
    by_zone: Mapping[str, list[int]],
    zone_centers: Mapping[str, Any],
    taken: Mapping[int, float],
    pair_splay: float | None = None,
) -> dict[int, float]:
    """Canonical-slot placement (the quantization law). A slot may be claimed
    once, globally; slots past the sector border (|off| > q) are admissible
    only when the neighbor on that side is unoccupied. Contention resolves
    to the next canonical arrangement, then to the nearest free slots
    walking outward from the cardinal, then raises — never a free angle.
    Explicit-angle members pre-claim their exact angle so a sector never
    lands a slot on top of one."""
    order = [z for z in _ZONES if z in zone_centers]
    idx = {z: i for i, z in enumerate(order)}
    q = _sector_step(order, zone_centers) / 2.0
    occupied = set(by_zone)
    registry: set[float] = {round(a % 360.0, 4) for a in taken.values()}

    def slot_open(zone: str, off: float) -> bool:
        if round((float(zone_centers.get(zone, 0.0)) + off) % 360.0, 4) in registry:
            return False
        if abs(off) > q + 1e-9:
            side = 1 if off > 0 else -1
            neighbor = order[(idx[zone] + side) % len(order)]
            if neighbor in occupied:
                return False
        return True

    out: dict[int, float] = {}
    # Denser sectors claim slots first (they need the spill room); the
    # compass index breaks ties — deterministic for a given spec.
    for zone in sorted(by_zone, key=lambda z: (-len(by_zone[z]), idx[z])):
        occupants = by_zone[zone]
        center = float(zone_centers.get(zone, 0.0))
        chosen = next(
            (offs for offs in _arrangements(len(occupants), q, pair_splay) if all(slot_open(zone, o) for o in offs)),
            None,
        )
        if chosen is None:
            free = [
                off
                for step_i in range(4)
                for off in ((0.0,) if step_i == 0 else (-step_i * q, step_i * q))
                if slot_open(zone, off)
            ]
            if len(free) >= len(occupants):
                chosen = tuple(sorted(free[: len(occupants)]))
        if chosen is None:
            raise DiagramCapacityError(f"hub sector {zone} has no free canonical slots for {len(occupants)} spokes")
        # Members take slots in projected-axis order along the arc (the
        # crossing-minimized rule — declaration order on a pure hub), for
        # every policy: quantization supersedes fractional distribution.
        ranked = sorted(occupants, key=_projected_axis)
        for m, off in zip(ranked, sorted(chosen), strict=True):
            registry.add(round((center + off) % 360.0, 4))
            out[m] = center + off
    return out


def _hub_policy(ctx: SolverContext) -> str:
    """§1.2 policy resolution: explicit ``hub_policy`` > compass when any
    member speaks compass vocabulary (zone / angle / anchor / distribution)
    > axial. The semantic cross is the DEFAULT for role-driven hubs — the
    compass rose is the opt-in generalist."""
    if ctx.spec.hub_policy:
        return ctx.spec.hub_policy
    compassish = (
        any(n.anchor for n in ctx.spec.nodes)
        or any(e.zone or e.angle is not None for e in ctx.edges)
        or bool(ctx.spec.distribution)
    )
    return "compass" if compassish else "axial"


def solve_hub(ctx: SolverContext) -> DiagramLayout:
    if _hub_policy(ctx) == "axial":
        return solve_axial(ctx)
    ch = ctx.ch
    spec = ctx.spec
    caps = ctx.engine.get("caps") or {}
    hub_cfg = _hub_cfg(ctx)
    zone_centers: Mapping[str, Any] = hub_cfg.get("zone_centers") or {}

    members = list(range(1, len(spec.nodes)))
    # Group members by resolved sector (explicit-angle members ride solo).
    by_zone: dict[str, list[int]] = {}
    angle_members: dict[int, float] = {}
    for m in members:
        ang = _explicit_angle(ctx, m)
        if ang is not None:
            angle_members[m] = ang
            continue
        by_zone.setdefault(_resolve_zone(ctx, m, spec.nodes[m], hub_cfg), []).append(m)
    for zone, occupants in by_zone.items():
        if len(occupants) > int(caps.get("hub_max_per_zone", 3)):
            raise DiagramCapacityError(
                f"hub caps at {caps.get('hub_max_per_zone', 3)} spokes per zone ({zone} has {len(occupants)})"
            )

    # Content-solved member box: ONE box across all spokes keeps the ring
    # regular (the aligned precedent; reuses the #3 card-box solver).
    card_w, card_h = _member_box(ctx)
    hub_w, hub_h, hub_node = _hub_box(ctx, member_w=card_w)
    # Member ANGLES are radius-independent (canonical slots), so quantize them
    # first; each member's radius then solves the CLEARANCE law per spoke.
    member_angle = _quantized_angles(
        by_zone, zone_centers, angle_members, pair_splay=float(hub_cfg.get("pair_splay") or 0.0) or None
    )
    for m, theta in angle_members.items():
        member_angle[m] = theta
    # Per-spoke radius — the hub-edge clearance law. The specimens hold the
    # hub-rect-to-satellite-rect air near-uniform along every axis
    # (hub 167-220px, verb-reads 230px); a single center-radius
    # ring collapsed E/W air to ~44px beside a 280-wide hub while N/S kept
    # ~170 (the massive-hub/short-arrows read). Radius = the hub rect's
    # support along the spoke + hub_clearance + the card's support, floored
    # at the chassis ring base; the neighbor-pair chord law (G7 breathing
    # room on the rect-diagonal bound) then raises the SMALLER of a crowding
    # pair — radii only grow, so the pass converges.
    clearance = float(ctx.engine.get("min_clearance", 18))
    base_r = {
        m: max(
            float(ch.ring_r_hub),
            _support(hub_w, hub_h, th) + float(ch.hub_clearance) + _support(card_w, card_h, th),
        )
        for m, th in member_angle.items()
    }
    radius = dict(base_r)

    def _pair_gap(ra: float, th_a: float, rb: float, th_b: float) -> float:
        # Exact axis-aligned silhouette air between two ring boxes at their
        # polar seats: the larger per-axis clearance (every ring member
        # shares ONE box, so the half-width sums are just card_w/card_h).
        # The old rect-diagonal chord bound (hypot(w,h)+24+clearance of
        # CHORD, everywhere) demanded separation the specimens never spend —
        # frame-engine's E/W spokes rode 9.6px past the hand file's kissing
        # radius while its own E-SE pair holds 82.8px of true y-air.
        ax_ = ra * math.cos(math.radians(th_a))
        ay_ = ra * math.sin(math.radians(th_a))
        bx_ = rb * math.cos(math.radians(th_b))
        by_ = rb * math.sin(math.radians(th_b))
        return max(abs(ax_ - bx_) - card_w, abs(ay_ - by_) - card_h)

    def _clear_radius(th_a: float, rj: float, th_j: float) -> float:
        # Minimal radius along ray th_a holding ``clearance`` of axis air
        # against the fixed neighbor at (rj, th_j): the cheaper of the two
        # per-axis outward escapes (an axis the ray barely moves along
        # cannot provide the escape).
        jx = rj * math.cos(math.radians(th_j))
        jy = rj * math.sin(math.radians(th_j))
        ca = math.cos(math.radians(th_a))
        sa = math.sin(math.radians(th_a))
        cands = []
        if abs(ca) > 1e-9:
            cands.append((jx + math.copysign(card_w + clearance, ca)) / ca)
        if abs(sa) > 1e-9:
            cands.append((jy + math.copysign(card_h + clearance, sa)) / sa)
        good = [t for t in cands if t >= 0.0]
        return min(good) if good else 0.0

    ordered = sorted(member_angle, key=lambda m: member_angle[m] % 360.0)
    if len(ordered) >= 2:
        for _ in range(4 * len(ordered)):
            raised = False
            for a, b in itertools.pairwise([*ordered, ordered[0]]):
                ra, rb = radius[a], radius[b]
                if _pair_gap(ra, member_angle[a], rb, member_angle[b]) >= clearance - 1e-6:
                    continue
                lo, hi = (a, b) if ra <= rb else (b, a)
                t = _clear_radius(member_angle[lo], radius[hi], member_angle[hi])
                if t > radius[lo] + 1e-6:
                    radius[lo] = t
                    raised = True
            if not raised:
                break
        # Relaxation — the no-slack fixed point: a spoke raised against a
        # neighbor a LATER pass pushed further out is stranded above every
        # constraint (spread-5 measured one 150px over base, nothing
        # binding). Settle each spoke to the max of its clearance base and
        # its still-binding pair requirements; sequential in-place sweeps
        # preserve feasibility and terminate at the cap.
        for _ in range(4):
            changed = False
            for m in ordered:
                req = base_r[m]
                for j in ordered:
                    if j == m:
                        continue
                    if _pair_gap(req, member_angle[m], radius[j], member_angle[j]) >= clearance - 1e-6:
                        continue
                    req = max(req, _clear_radius(member_angle[m], radius[j], member_angle[j]))
                if abs(req - radius[m]) > 1e-6:
                    radius[m] = req
                    changed = True
            if not changed:
                break
    # Canvas fits the CONTENT, never the theoretical ring square (R3, the
    # content-fit law): bbox the occupied extents in ring coordinates —
    # cards at their slots, the hub disc, its under-label — then pad with
    # the chrome bands. A sparse compass (three sectors of eight) previously
    # billed the artifact for a full centered square, leaving a dead
    # quadrant of pure void wherever the rose was unoccupied.
    ext_x: list[float] = [-hub_w / 2.0, hub_w / 2.0]
    ext_y: list[float] = [-hub_h / 2.0, hub_h / 2.0 + 26.0]  # the hub's under-label line
    for m, theta in member_angle.items():
        mx, my = point_on(0.0, 0.0, radius[m], theta)
        ext_x += [mx - card_w / 2.0, mx + card_w / 2.0]
        ext_y += [my - card_h / 2.0, my + card_h / 2.0]
    min_x, max_x = min(ext_x), max(ext_x)
    min_y, max_y = min(ext_y), max(ext_y)
    cx = ch.margin_x - min_x
    cy = ch.header_h - min_y
    width = math.ceil(cx + max_x + ch.margin_x)
    height = math.ceil(cy + max_y + ch.footer_h)
    # Ring members share one content column BY CONSTRUCTION (the chassis
    # content-anchor law seats every card's group at ``glyph_inset_x``).
    placed: dict[int, NodePlacement] = {}
    for m, theta in member_angle.items():
        px, py = point_on(cx, cy, radius[m], theta)
        placed[m] = _place_member(ctx, m, spec.nodes[m], px, py, card_w, card_h)

    hub = _place_hub(ctx, hub_node, cx, cy, hub_w, hub_h)
    standoff = float(ctx.engine["connector"].get("standoff", 0))
    geos = _hub_spokes(ctx, hub, placed, cx, cy, standoff)
    # Regions: one anchor frame per occupied sector (zone:N..NW) at the
    # sector's mid-ring point (its own clearance-law radius) — the annotate
    # pass hangs zone callouts here.
    regions = {
        f"zone:{zone}": _zone_region(
            cx,
            cy,
            max(
                float(ch.ring_r_hub),
                _support(hub_w, hub_h, float(zone_centers.get(zone, 0.0)))
                + float(ch.hub_clearance)
                + _support(card_w, card_h, float(zone_centers.get(zone, 0.0))),
            ),
            float(zone_centers.get(zone, 0.0)),
            card_w,
            card_h,
        )
        for zone in by_zone
    }
    # Paint order: spokes' cards first, hub LAST (the emanation mask).
    paint = [placed[m] for m in members] + [hub]
    return finish_layout(ctx, width=width, height=height, nodes_paint=paint, geos=geos, extra_regions=regions)


def _support(bw: float, bh: float, theta_deg: float) -> float:
    """Distance from an axis-aligned rect's center to its boundary along
    ``theta_deg`` — the rect support the clearance law measures edge-to-edge
    against (a point-radius ring treats a 280-wide hub as a point and eats
    the E/W air)."""
    c = abs(math.cos(math.radians(theta_deg)))
    s = abs(math.sin(math.radians(theta_deg)))
    cands = []
    if c > 1e-9:
        cands.append((bw / 2.0) / c)
    if s > 1e-9:
        cands.append((bh / 2.0) / s)
    return min(cands)


def _member_box(ctx: SolverContext) -> tuple[float, float]:
    """Shared content-solved (w, h) across every spoke card — the max box, so
    the ring stays regular. A pill spoke's content-solved width folds into
    the same max (one sizing seam for solve and placement), so the
    ring sizes for whatever anatomy the widest member resolves to. Ring
    members are never hero (``hero=False`` pinned): the seam's own default
    chassis/radius picks (``ch.node``/``ch.circle_r``) already match the
    original's hardcoded values at ``hero=False``, so one call covers every
    style without an external branch. The width floor is the chassis ring
    base (``ch.node.w`` — the specimens never render a shrink-wrapped ring
    card: verb-reads 200, hub 210-220), not the bare
    ``card_min_w``."""
    ch = ctx.ch
    w = 0.0
    h = ch.node.h
    for m in range(1, len(ctx.spec.nodes)):
        if style_of(ctx.spec.nodes[m], ctx.spec, ctx.ch) == NodeStyle.TEXT.value:
            # A typographic satellite's box is its own measured type block —
            # no card floor (containers earn their existence, hub-panel).
            bw, bh, _lines = measure_text_block(ctx.cfg, ctx.spec.nodes[m])
        else:
            bw, bh, _ = solve_node_box(ctx, ctx.spec.nodes[m], m)
        w = max(w, bw)
        h = max(h, bh)
    return w, h


def _hub_box(ctx: SolverContext, *, member_w: float) -> tuple[float, float, DiagramNode]:
    """The compass center's own (w, h) footprint for the canvas bbox: a
    circle's diameter (the STRUCTURAL default — the emanation mask the ring
    spokes paint against), or a content-solved card/pill when the center
    declares an explicit style. Mirrors ``_member_box``'s per-style branch
    so the canvas fits whatever anatomy the center resolves to, not the
    circle radius the ring math assumed before node.style was honored here.
    ``circle_r=ch.hero_circle_r_hub`` is the hub-specific radius field (a
    DIFFERENT constant than the ring members' ``ch.circle_r``).

    The card nucleus is a LEGO: width floors at an EXPLICIT ``hero.w``
    citation, else the ring's member width (dominance is a step over the
    family, never the fixed 280 frame — half-empty nucleus); height floors
    at an EXPLICIT ``hero.h`` citation, else solves PURE from the content
    rows over the chassis ``pad_y`` band, never at the ring member's OWN
    height (verb-reads' two-row hub is 92, the hub specimen's three-row is
    120; one archetype ``h`` can't serve both, and neither is the ring
    card's business) — the same ``hero_declared`` law ``fan.py`` reads."""
    ch = ctx.ch
    node = ctx.spec.nodes[0]
    w, h, _ = solve_node_box(
        ctx,
        node,
        0,
        circle_r=ch.hero_circle_r_hub,
        default_style=NodeStyle.GLYPH_CIRCLE.value,
        h_floor=hero_height_floor(ch),
    )
    # Compass hero aspect discipline (the frame-engine-hub hand hero measures
    # 163.5x120 -> w/h = 1.36): a wide-short nucleus collapses the rect
    # support off-axis, pushing cardinal spokes far past diagonal ones (a
    # 270x87 unpinned hero spread sibling radii 38%; the specimen chassis
    # holds 12%). Past the cap the desc wraps into a squarer crown instead
    # of widening — the name row still never truncates (ceiling stretches).
    aspect_max = float((ctx.engine.get("hub") or {}).get("hero_aspect_max", 1.36))
    # A preset that PINS its hero chassis is specimen law (hub-panel's
    # 232x136 crown) — the clamp only disciplines unpinned content heroes.
    hero_pinned = bool(((ctx.spec.chassis or {}).get("hero") or {}).get("w"))
    if not hero_pinned and node.desc and "\n" not in node.desc and h > 0 and w / h > aspect_max:
        target_w = max(float(ch.card_min_w), math.ceil(math.sqrt(w * h * aspect_max) / 2) * 2)
        if target_w < w:
            # The hero's never-clip rule keeps its UNWRAPPED text column whole,
            # so a narrower chassis alone can't shrink it — wrap the desc at
            # the target budget first (authored-breaks law: the solve honors
            # explicit \n), then re-solve against the wrapped column. The
            # REWRITTEN node returns with the box: placement must wrap the
            # same text the box was sized for (discarding it re-wrapped the
            # original single line into a box solved for two — the hero text
            # hugged the left pad and blew 31px past the right one).
            budget = target_w - 2 * (ch.hero.pad_x or 32.0)
            lines = wrap_text_lines(node.desc, budget, ctx.cfg.hero_desc_voice, max_lines=ch.hero.max_desc_lines or 2)
            if len(lines) > 1:
                node = node.model_copy(update={"desc": "\n".join(lines)})
                w, h, _ = solve_node_box(
                    ctx,
                    node,
                    0,
                    circle_r=ch.hero_circle_r_hub,
                    default_style=NodeStyle.GLYPH_CIRCLE.value,
                    chassis=ch.hero.model_copy(update={"w": target_w}),
                    h_floor=hero_height_floor(ch),
                )
    return w, h, node


def _sector_step(order: list[str], zone_centers: Mapping[str, Any]) -> float:
    """Uniform angular step between adjacent compass sectors (the table is a
    regular 8-way rose → 45°). Derived from the table, not hardcoded."""
    if len(order) < 2:
        return 45.0
    a = float(zone_centers[order[0]])
    b = float(zone_centers[order[1]])
    return abs((b - a + 180) % 360 - 180) or 45.0


def _projected_axis(member: int) -> float:
    """The tie-break coordinate for crossing-minimized ordering. A pure hub has
    no external anchor to project onto (every spoke's other end is the center),
    so the caller's declaration order IS the axis — members fan in the order
    they were written, monotone by construction. Returned as the member's spec
    index so the sort is deterministic and stable."""
    return float(member)


def _place_member(
    ctx: SolverContext,
    i: int,
    node: DiagramNode,
    cx: float,
    cy: float,
    card_w: float,
    card_h: float,
) -> NodePlacement:
    # Ring members are never hero. A glyph-circle member ignores the shared
    # ``card_w``/``card_h`` aligned box entirely (its own chassis radius,
    # ``ch.circle_r`` — matching ``_member_box``'s hero=False default), so
    # its own diameter is fed instead of the caller's card box.
    if style_of(node, ctx.spec, ctx.ch) == NodeStyle.GLYPH_CIRCLE.value:
        d = 2 * ctx.ch.circle_r
        return place_node(ctx, node, i, cx, cy, w=d, h=d)
    return place_node(ctx, node, i, cx, cy, w=card_w, h=card_h)


def _place_hub(ctx: SolverContext, node: DiagramNode, cx: float, cy: float, w: float, h: float) -> NodePlacement:
    """Compass hub center: glyph-circle is the STRUCTURAL default (the
    emanation mask the ring spokes paint against, matching radial.py's polar
    hubs) — an explicit ``node.style`` (card, card+glyph, pill) wins, the
    same cascade every other topology honors. ``w``/``h`` come from
    ``_hub_box`` (a circle's diameter, or the resolved card/pill's own box),
    already correct for whichever style resolves — one seam call covers all
    three (``hero=True`` pinned, matching ``_hub_box``; ``hub=True`` only
    matters for the circle dispatch)."""
    return place_node(ctx, node, 0, cx, cy, w=w, h=h, hub=True, default_style=NodeStyle.GLYPH_CIRCLE.value)


def _hub_spokes(
    ctx: SolverContext, hub: NodePlacement, placed: Mapping[int, NodePlacement], cx: float, cy: float, standoff: float
) -> list[EdgeGeo]:
    """One spoke per edge: hub boundary -> member boundary via route_path
    (straight default, curved when the edge asks). Reciprocal pairs split
    into lanes like any chord."""
    geos: list[EdgeGeo] = []
    for j, edge in enumerate(ctx.edges):
        member = edge.target if edge.source == 0 else edge.source
        other = placed[member]
        mx, my = boundary_anchor(other, cx, cy, standoff)
        member_style = style_of(ctx.spec.nodes[member], ctx.spec, ctx.ch)
        if (
            member_style == NodeStyle.TEXT.value
            and hub.shape == "rect"
            and edge.routing == "curved"
            and edge.source == 0
        ):
            # Corner-exit quadrants (hub-panel-02-orchestrator): the spoke
            # leaves the hub CARD CORNER facing the block's quadrant and
            # sweeps one shallow quadratic to the block's near boundary. The
            # hand file drew these by eye; the engine derives the same sag —
            # a standoff lift-off plus a bowed control point, both measured
            # off the four (mirror-identical) hand curves. Standoff: the
            # launch point sits 10.7% of the way from the corner toward the
            # target (17.2px along a 161.2px corner->target span), softening
            # the sharp-vertex launch that swept overwide against the
            # specimen; re-based on the resulting draw chord (corner->target
            # minus the standoff) that is 12.0% of its length — 17.2px on
            # the hand curves' own 144.0px chord. Bow: the control point
            # sits at that draw chord's midpoint, pushed 13.5% of the chord
            # perpendicular, away from the hub (measured 19.4px bow on the
            # same 144.0px chord — 2026-07-13 recalibration, superseding the
            # un-stood-off 14%-bow-only construction).
            hb = hub.box
            qx0 = hb.x if mx < cx else hb.x + hb.w
            qy0 = hb.y if my < cy else hb.y + hb.h
            mx, my = boundary_anchor(other, qx0, qy0, standoff)
            corner_x, corner_y = mx - qx0, my - qy0
            sx, sy = qx0 + 0.107 * corner_x, qy0 + 0.107 * corner_y
            chord_x, chord_y = mx - sx, my - sy
            clen = math.hypot(chord_x, chord_y) or 1.0
            # Bow-side selection reads the CORNER's fixed side of the hub
            # center (qx0 vs cx — a solid half-box-width margin, ~116px
            # here), never the chord's own relation to the hub center: a
            # seat angle aimed through its own corner (hub-panel's
            # ±30°/±150° spokes) puts the corner/center/target within a
            # degree of collinear, so the old chord-midpoint dot-product
            # test flipped sign on measurement noise far smaller than
            # hub_seats()'s own passing tolerance (0.5° off collinear
            # rendered vs the hand file's 7.2° — every one of the four
            # spokes' arrival tangents landed mirrored, chevrons arriving
            # near-flat instead of the hand file's steep dagger angle). The
            # hand file's own four corners bow with the horizontal
            # component always OUTWARD (same side as the corner) — bilateral
            # by construction (TL/BR share one sign, TR/BL the other).
            px, py = -chord_y / clen, chord_x / clen
            if (px >= 0) != (qx0 >= cx):
                px, py = -px, -py
            qcx = (sx + mx) / 2 + px * 0.135 * clen
            qcy = (sy + my) / 2 + py * 0.135 * clen
            d = f"M {fmt(sx)},{fmt(sy)} Q {fmt(qcx)},{fmt(qcy)} {fmt(mx)},{fmt(my)}"
            tlen = math.hypot(mx - qcx, my - qcy) or 1.0
            geos.append(
                EdgeGeo(
                    index=j,
                    d=d,
                    sx=sx,
                    sy=sy,
                    tx=mx,
                    ty=my,
                    length=clen * 1.05,
                    polyline=sample_path(d),
                    end_tangent=((mx - qcx) / tlen, (my - qcy) / tlen),
                )
            )
            continue
        hx, hy = boundary_anchor(hub, mx, my, standoff)
        if edge.source == 0:
            sx, sy, tx, ty = hx, hy, mx, my
        else:
            sx, sy, tx, ty = mx, my, hx, hy
        sx, sy, tx, ty = lane_endpoints(sx, sy, tx, ty, ctx.lanes[j], ctx.lane_offsets[j])
        style = "curved" if edge.routing == "curved" else "straight"
        d, length, poly, tangent = route_path(sx, sy, tx, ty, style=style)
        geos.append(
            EdgeGeo(index=j, d=d, sx=sx, sy=sy, tx=tx, ty=ty, length=length, polyline=poly, end_tangent=tangent)
        )
    return geos


def _zone_region(cx: float, cy: float, ring_r: float, center_deg: float, card_w: float, card_h: float) -> Region:
    """A region frame at a sector's mid-ring point — the annotate pass anchors
    a zone:N..NW callout inside it (Region.point(0.5,0.5) is the sector center).
    Sized to the shared member box."""
    zx, zy = point_on(cx, cy, ring_r, center_deg)
    return Region(x=zx - card_w / 2, y=zy - card_h / 2, w=card_w, h=card_h)


register_solvers({"hub": solve_hub})
