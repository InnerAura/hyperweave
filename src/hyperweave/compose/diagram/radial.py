"""Polar-family solvers: fanout-radial, flywheel, ring, and the multi-level
radial tree (per-subtree angular subdivision).

The radial fan's connectors are drawn from the HUB CENTER and the hub
paints last — the card masks the inner stubs so spokes appear to emanate
from its surface (paint order is data, never a template branch). Flywheel
arcs trim each card's angular half-width plus a clearance, reproducing the
specimen's 24-degree insets at any ring count; the ring adds the
text-aware trim (arcs also clear each stage's stacked annotation block).
"""

from __future__ import annotations

import math
import re
from dataclasses import replace
from typing import TYPE_CHECKING

from hyperweave.compose.diagram.anchors import boundary_anchor, rect_distance, trim_arc_angle
from hyperweave.compose.diagram.chrome import (
    apply_health_dot,
    place_node,
    style_of,
    voice_for,
)
from hyperweave.compose.diagram.motion import fmt_s, lane_endpoints
from hyperweave.compose.diagram.paths import arc_d, arc_len, fmt, line_len, point_on, ray_d
from hyperweave.compose.diagram.recenter import translate_path
from hyperweave.compose.diagram.records import ParticlePlacement
from hyperweave.compose.diagram.sizing import hero_height_floor, solve_node_box
from hyperweave.compose.diagram.solver import finish_layout, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
from hyperweave.compose.matrix.cells import measure_voice
from hyperweave.core.diagram import DiagramInputError, NodeRole, NodeStyle, resolved_edges

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import DiagramLayout, DiagramText, NodePlacement
    from hyperweave.core.diagram import DiagramNode


def _place_at_center(
    ctx: SolverContext,
    i: int,
    node: DiagramNode,
    cx: float,
    cy: float,
    *,
    hero: bool,
    nch_name: str = "",
    ring_center: tuple[float, float] | None = None,
    w_group: float = 0.0,
) -> NodePlacement:
    ch = ctx.ch
    # ``nch`` computed here (not via the seam's own ``chassis_class`` hint)
    # so ``hero`` always wins over ``nch_name`` exactly as the original
    # ternary orders it — passed as an explicit ``chassis=`` override, the
    # seam's highest-priority chassis source, so this call site's priority
    # can never drift from the shared function's own default ordering.
    nch = ch.hero if hero else (ch.node2 if nch_name == "node2" else ch.node)
    if style_of(node, ctx.spec, ctx.ch) == NodeStyle.GLYPH_CIRCLE.value:
        r = ch.hero_circle_r if hero else ch.circle_r
        return place_node(ctx, node, i, cx, cy, w=2 * r, h=2 * r, hero=hero, ring_center=ring_center)
    # A group-normalized width (``w_group``, from the aligned ring policy)
    # fixes every spoke card to the group max (a content-derived share) and
    # re-solves the height at that width; 0 = the card's own snug solve.
    # Snug-width ruling: no other floor — crowns and members alike solve to
    # their own content, with citations bounding growth as ceilings inside
    # the sizing seam (the HEAD-anatomy crown keeps its family frame there).
    min_w = w_group or 0.0
    w, h, _ = solve_node_box(
        ctx,
        node,
        i,
        hero=hero,
        chassis=nch,
        min_w=min_w,
        h_floor=hero_height_floor(ch) if hero else None,
    )
    if w_group:
        w = w_group
    # A spoke node centers on its solved box (width AND height), so a wrapped
    # desc grows the card symmetrically about the ring anchor. Byte-identical
    # when the desc fits (solved height == chassis h).
    placed = place_node(ctx, node, i, cx, cy, w=w, h=h, hero=hero, chassis=nch)
    return apply_health_dot(ctx, node, placed)


def _facing_anchor(ctx: SolverContext, p: NodePlacement, hub_cx: float, hub_cy: float) -> tuple[float, float]:
    """Where a spoke from the hub lands on the node: the ray crosses the
    node's actual shape boundary (rect, circle, or pill) + the uniform
    standoff — direction-true, so corner-angle cards get no dead gap."""
    standoff = float(ctx.engine["connector"].get("standoff", 0))
    return boundary_anchor(p, hub_cx, hub_cy, standoff)


def _hub_label_box(
    ctx: SolverContext, hub: NodePlacement, spoke_angles: list[float]
) -> tuple[NodePlacement, tuple[float, float, float, float] | None]:
    """The hub label sits in the angular gap between spokes nearest to
    straight-down (G4): measured box, bisector placement, pushed outward
    until it clears the hub circle. Returns the re-labeled hub and the
    label's clearance box (cx, cy, w, h) for spoke anchoring."""
    if hub.shape != "circle" or not hub.label.text:
        return hub, None
    # Already inside-stacked (K-radial-general): the label sits within the
    # circle; spokes start at the boundary, so no gap move / clearance box.
    if math.hypot(hub.label.x - hub.cx, hub.label.y - hub.cy) <= hub.r:
        return hub, None
    from hyperweave.compose.diagram.chrome import voice_for
    from hyperweave.compose.matrix.cells import measure_voice

    cfg = ctx.cfg
    clear = float(ctx.engine["connector"].get("hub_label_clear", 6))
    voice = voice_for(cfg, hub.label.cls)
    w = measure_voice(hub.label.text, voice)
    h = voice.size * (cfg.text_ascent_ratio + cfg.text_descent_ratio)
    angles = sorted(a % 360 for a in spoke_angles)
    if not angles:
        return hub, None
    # Gap bisectors; choose the one nearest straight-down (90 deg).
    best: tuple[tuple[float, float], float] | None = None
    for i, a in enumerate(angles):
        b = angles[(i + 1) % len(angles)]
        span = (b - a) % 360 or 360.0
        bis = (a + span / 2) % 360
        dev = abs((bis - 90 + 180) % 360 - 180)
        key = (round(dev, 4), round(bis, 4))
        if best is None or key < best[0]:
            best = (key, bis)
    assert best is not None  # angles is non-empty here
    bis = best[1]
    rad = math.radians(bis)
    radius = hub.r + clear + h / 2
    for _ in range(40):  # push out until the box clears the circle
        lcx = hub.cx + math.cos(rad) * radius
        lcy = hub.cy + math.sin(rad) * radius
        if rect_distance(lcx, lcy, w, h, 0.0, hub.cx, hub.cy) >= hub.r + clear:
            break
        radius += 2.0
    baseline = lcy + (cfg.text_ascent_ratio - cfg.text_descent_ratio) / 2 * voice.size
    dy = baseline - hub.label.y
    dx = lcx - hub.label.x
    hub = replace(
        hub,
        label=replace(hub.label, x=lcx, y=baseline),
        desc_lines=tuple(replace(d, x=d.x + dx, y=d.y + dy) for d in hub.desc_lines),
    )
    return hub, (lcx, lcy, w, h)


def _hub_clearance_anchor(
    hub: NodePlacement,
    label_box: tuple[float, float, float, float] | None,
    to_x: float,
    to_y: float,
    clear: float,
) -> tuple[float, float]:
    """Hub-side spoke endpoint: the ray from the hub center crosses the
    union of the hub circle and the label clearance box (G4) — spokes and
    the particles riding them keep clear of the label. Card hubs keep the
    masked center start (their label lives inside the card)."""
    if hub.shape != "circle":
        b = hub.box
        return (b.x + b.w / 2, b.y + b.h / 2)

    def sdf(x: float, y: float) -> float:
        d = math.hypot(x - hub.cx, y - hub.cy) - hub.r
        if label_box is not None:
            # Uniform ``clear`` padding with ROUND corners: distance to the
            # true ink box minus clear. Inflating the box by 2*clear kept
            # sharp corners, so a diagonal ray paid ~clear*sqrt(2) at the
            # corner — the display-voice hub name pushed that over-claim to
            # a 17px off-rim stop on spokes that never touch the ink.
            lcx, lcy, w, h = label_box
            d = min(d, rect_distance(lcx, lcy, w, h, 0.0, x, y) - clear)
        return d

    dist = math.hypot(to_x - hub.cx, to_y - hub.cy)
    if dist == 0:
        return (hub.cx, hub.cy)
    ux, uy = (to_x - hub.cx) / dist, (to_y - hub.cy) / dist
    # The union SDF is not monotone along the ray (exit the circle, enter
    # the box): find the LAST inside sample, then bisect that crossing.
    steps = 160
    last_inside = 0
    for i in range(steps + 1):
        t = dist * i / steps
        if sdf(hub.cx + ux * t, hub.cy + uy * t) < 0.0:
            last_inside = i
    lo, hi = dist * last_inside / steps, dist * min(last_inside + 1, steps) / steps
    for _ in range(28):
        mid = (lo + hi) / 2
        if sdf(hub.cx + ux * mid, hub.cy + uy * mid) < 0.0:
            lo = mid
        else:
            hi = mid
    travel = (lo + hi) / 2
    return (hub.cx + ux * travel, hub.cy + uy * travel)


def _ring_group_width(ctx: SolverContext, nodes: list[DiagramNode]) -> float:
    """Group-max card width across the ring's CARD dests under the aligned
    policy (glyph-circle dests carry no card width). 0 when the policy is free
    or every dest is a circle — then each card keeps its own solved width."""
    if ctx.ch.width_policy != "aligned":
        return 0.0
    # Role-derived (mismatch class FIXED): a declared hero dest measures
    # with the chassis its placement renders.
    widths = [
        solve_node_box(ctx, n, i)[0]
        for i, n in enumerate(nodes)
        if style_of(n, ctx.spec, ctx.ch) != NodeStyle.GLYPH_CIRCLE.value
    ]
    return max(widths) if widths else 0.0


def solve_fanout_radial(ctx: SolverContext) -> DiagramLayout:
    """Hub centered, dests on a ring at equal angles from the top; rays
    drawn under the hub. The ring grows past its base radius when the
    perimeter would crowd (K x (node width + ring_gap) / 2pi)."""
    ch = ctx.ch
    spec = ctx.spec
    k = len(spec.nodes) - 1
    # Aligned ring: every card dest takes the group-max width, so the ring is
    # uniform (0 = free policy / all circles → each keeps its solved width).
    dest_w = _ring_group_width(ctx, list(spec.nodes[1:]))
    card_unit = max(ch.node.w, dest_w)  # the packing width the ring must clear
    radius = max(ch.ring_r, k * (card_unit + ch.ring_gap) / (2 * math.pi))
    size = math.ceil(2 * (radius + card_unit / 2) + 16) if radius > ch.ring_r else ch.width
    c = size / 2
    dests: list[NodePlacement] = []
    spoke_angles: list[float] = []
    pitch = 360 / k
    # Seat assignment (diagram-data-hub-circles-pp.svg's own hw:spatial-notes:
    # "node centres R=252 at theta 90/162/18/234/306" for its 5 satellites in
    # payload order — the specimen's theta is the CCW-from-east / y-up
    # convention; this engine's ``point_on`` adds sin(deg) straight to a
    # y-DOWN svg coordinate, so engine-theta = -specimen-theta. Converted:
    # -90, -162, -18, -234(=126), -306(=54) — a NORTH-ANCHORED ALTERNATING
    # WALK off the first satellite (paradigms, already north under the old
    # sequential walk and unmoved here): pitch steps 0, -1, +1, -2, +2, ...
    # (alternate side, growing magnitude every 2 seats) rather than one
    # direction in seat order. Generalizes past k=5: the step sequence visits
    # every one of the k distinct pitch multiples exactly once for any k.
    for i, node in enumerate(spec.nodes[1:], start=1):
        pos = i - 1  # 0-indexed walk position
        if pos == 0:
            step = 0
        else:
            magnitude = (pos + 1) // 2
            step = -magnitude if pos % 2 == 1 else magnitude
        theta = -90 + step * pitch
        spoke_angles.append(theta)
        cx, cy = point_on(c, c, radius, theta)
        # Radial-outboard labels (K-radial-general): glyph-circle dests
        # label along the spoke away from the hub; a below-label would
        # point inward and the spoke would cross it. Card dests carry their
        # label inside the card — ring_center is inert for them.
        dests.append(_place_at_center(ctx, i, node, cx, cy, hero=False, ring_center=(c, c), w_group=dest_w))
    hub = _place_at_center(ctx, 0, spec.nodes[0], c, c, hero=True)
    hub, label_box = _hub_label_box(ctx, hub, spoke_angles)
    clear = float(ctx.engine["connector"].get("hub_label_clear", 6))
    geos: list[EdgeGeo] = []
    for j, edge in enumerate(ctx.edges):
        other = dests[(edge.target if edge.source == 0 else edge.source) - 1]
        ax, ay = _facing_anchor(ctx, other, c, c)
        hx, hy = _hub_clearance_anchor(hub, label_box, ax, ay, clear)
        if edge.source == 0:
            sx, sy, tx, ty = hx, hy, ax, ay
        else:
            sx, sy, tx, ty = ax, ay, hx, hy
        # Reciprocal spokes split into lanes like any other chord (G8b).
        sx, sy, tx, ty = lane_endpoints(sx, sy, tx, ty, ctx.lanes[j], ctx.lane_offsets[j])
        geos.append(
            EdgeGeo(index=j, d=ray_d(sx, sy, tx, ty), sx=sx, sy=sy, tx=tx, ty=ty, length=line_len(sx, sy, tx, ty))
        )
    # Paint order: dests first, hub LAST — the emanation mask.
    return finish_layout(ctx, width=size, height=size, nodes_paint=[*dests, hub], geos=geos)


def _solve_cyclic(ctx: SolverContext) -> DiagramLayout:
    """Shared ring-placement machinery for the cyclic pair. RING (slug
    "ring") is the semantic claim "every stage equal, no hero" — enforced
    here by raising. FLYWHEEL (slug "flywheel") is "a cyclic process with an
    OPTIONAL central axis". Hero-PRESENCE, not the requested word, drives the
    rest of the expression: label anchoring (outboard-radial when a center
    hero exists, below-stacked when the center is empty — below earns the
    empty centre as text room) and the arc-trim law. The two arc-trim laws
    were tuned against different specimens and are NOT interchangeable: with
    a hero, the simple silhouette-plus-clearance trim floats the arc past the
    node's own boundary (flywheel-orbit's card phases); with no hero, the
    newer centre-measured law takes max(node_angle + clear, silhouette trim)
    — clear is a floor, never added ON TOP of the silhouette trim (that
    double-counted and halved every span) — then walks each end past the
    endpoint's own stacked annotation block (ring's per-line text-aware
    trim). Flywheel's two pure-data-gated forms fold in unchanged: the FLOW
    full-circle collapse (every edge dressed drift+markerless) and the orbit
    rim-riders (``"particle" in ctx.motions``) — both gates already read the
    edges/motions, never the topology word, so they apply identically
    whichever slug reaches here."""
    ch = ctx.ch
    spec = ctx.spec
    if ctx.slug == "ring" and any(node.role is NodeRole.HERO for node in spec.nodes):
        raise DiagramInputError("ring holds every stage equal — no hero; a centred axis belongs to flywheel")
    size = ch.width
    c = size / 2
    ring = [i for i, node in enumerate(spec.nodes) if node.role is not NodeRole.HERO]
    k = len(ring)
    hero_i = next((i for i, node in enumerate(spec.nodes) if node.role is NodeRole.HERO), None)
    angle_of: dict[int, float] = {}
    placed: dict[int, NodePlacement] = {}
    for pos, i in enumerate(ring):
        theta = -90 + pos * 360 / k
        angle_of[i] = theta
        cx, cy = point_on(c, c, ch.ring_r, theta)
        # Radially outboard labels when a center hero claims the middle
        # (K-radial-label: the ring stroke runs through these node centers,
        # so a below-label collides at 3 and 9 o'clock); below-stacked labels
        # (ring_center=None) when the centre is empty — upper text falls
        # inward, toward the empty centre, which earns its keep as text room.
        placed[i] = _place_at_center(
            ctx, i, spec.nodes[i], cx, cy, hero=False, ring_center=(c, c) if hero_i is not None else None
        )
    if hero_i is not None:
        placed[hero_i] = _place_at_center(ctx, hero_i, spec.nodes[hero_i], c, c, hero=True)
    paint: list[NodePlacement] = [placed[i] for i in ring]
    if hero_i is not None:
        paint.append(placed[hero_i])
    standoff = float(ctx.engine["connector"].get("standoff", 0))
    # Per-line padded boxes of each node's OUTSIDE text (ring only — a
    # center hero's ring_center labels never stack below, so there is
    # nothing here for the arc trim to walk past).
    text_bb: dict[int, list[tuple[float, float, float, float]]] = (
        {i: _annotation_line_boxes(ctx, placed[i], pad=8.0) for i in placed} if hero_i is None else {}
    )

    def _inside(boxes: list[tuple[float, float, float, float]], ang: float) -> bool:
        px, py = point_on(c, c, ch.arc_r, ang)
        return any(b[0] <= px <= b[2] and b[1] <= py <= b[3] for b in boxes)

    geos: list[EdgeGeo] = []
    for j, edge in enumerate(ctx.edges):
        if hero_i is None:
            # ring's centre-measured arc_clear law (the hand file's arcs
            # start exactly ±13° off each medallion centre, emerging from
            # behind the circle): the silhouette trim survives only as a
            # FLOOR for a node too big for the clear.
            sil0 = trim_arc_angle(
                placed[edge.source],
                arc_cx=c,
                arc_cy=c,
                arc_r=ch.arc_r,
                node_angle_deg=angle_of[edge.source],
                direction=+1,
                standoff=standoff,
            )
            a0 = max(angle_of[edge.source] + ch.arc_clear_deg, sil0)
            sil1 = trim_arc_angle(
                placed[edge.target],
                arc_cx=c,
                arc_cy=c,
                arc_r=ch.arc_r,
                node_angle_deg=angle_of[edge.target],
                direction=-1,
                standoff=standoff,
            )
            a1 = min(angle_of[edge.target] - ch.arc_clear_deg, sil1)
            if a1 <= a0:
                a1 += 360 if angle_of[edge.target] <= angle_of[edge.source] else 0
            # Text-aware trim: walk each end past the endpoint node's
            # annotation block (1° steps, bounded well inside the arc span)
            # so the arc starts below the upper stage's text and its
            # arrowhead lands clear of the next stage's ink.
            guard = 0
            while _inside(text_bb[edge.source], a0) and a0 < a1 - 4 and guard < 120:
                a0 += 1.0
                guard += 1
            guard = 0
            while _inside(text_bb[edge.target], a1) and a1 > a0 + 4 and guard < 120:
                a1 -= 1.0
                guard += 1
        else:
            # flywheel's silhouette-plus-clearance trim: FLOAT the boundary
            # crossing by arc_clear_deg — the specimen's arcs deliberately do
            # not touch the cards (flywheel-orbit: boundary + 1.2deg of air
            # per end — the cycle reads as motion BETWEEN phases, not
            # plumbing into them).
            a0 = (
                trim_arc_angle(
                    placed[edge.source],
                    arc_cx=c,
                    arc_cy=c,
                    arc_r=ch.arc_r,
                    node_angle_deg=angle_of[edge.source],
                    direction=+1,
                    standoff=standoff,
                )
                + ch.arc_clear_deg
            )
            a1 = (
                trim_arc_angle(
                    placed[edge.target],
                    arc_cx=c,
                    arc_cy=c,
                    arc_r=ch.arc_r,
                    node_angle_deg=angle_of[edge.target],
                    direction=-1,
                    standoff=standoff,
                )
                - ch.arc_clear_deg
            )
            if a1 <= a0:
                a1 += 360 if angle_of[edge.target] <= angle_of[edge.source] else 0
        p0 = point_on(c, c, ch.arc_r, a0)
        p1 = point_on(c, c, ch.arc_r, a1)
        geos.append(
            EdgeGeo(
                index=j,
                d=arc_d(c, c, ch.arc_r, a0, a1),
                sx=p0[0],
                sy=p0[1],
                tx=p1[0],
                ty=p1[1],
                length=arc_len(ch.arc_r, a0, a1),
                arc=(c, c, ch.arc_r, a0, a1),
            )
        )
    # The FLOW form (flywheel-flow): when every ring edge dresses as a
    # markerless drift, there are no discrete turns — the rim is ONE
    # continuous current, a single closed circle behind the cards, not four
    # floated arcs. Form follows dress; no extra field.
    ring_edges = [ctx.edges[g.index] for g in geos]
    if geos and all(e.relation == "drift" and (e.marker or "") == "none" for e in ring_edges):
        top = point_on(c, c, ch.arc_r, -90)
        bottom = point_on(c, c, ch.arc_r, 90)
        full = (
            f"M {fmt(top[0])},{fmt(top[1])} "
            f"A {fmt(ch.arc_r)},{fmt(ch.arc_r)} 0 0 1 {fmt(bottom[0])},{fmt(bottom[1])} "
            f"A {fmt(ch.arc_r)},{fmt(ch.arc_r)} 0 0 1 {fmt(top[0])},{fmt(top[1])}"
        )
        geos = [
            EdgeGeo(
                index=geos[0].index,
                d=full,
                sx=top[0],
                sy=top[1],
                tx=top[0],
                ty=top[1],
                length=arc_len(ch.arc_r, 0, 360),
                arc=(c, c, ch.arc_r, -90, 270),
                marker_override="none",
            )
        ]
    # flywheel-orbit's signature ornament: a FIXED count of accent particles
    # ride the FULL closed rim as one continuous loop, independent of the
    # per-arc edges above (a rider must not restart at each ring card) — the
    # rim path shares the arcs' own radius (invisible-rider rule) and starts
    # at the top, matching the specimen. Gated on the artifact actually
    # requesting particle motion (flywheel-orbit); every other motion, or
    # none, leaves the rim ornament-free.
    extra_particles: tuple[ParticlePlacement, ...] = ()
    if "particle" in ctx.motions:
        orbit = ctx.engine["particle"]["orbit"]
        count = int(orbit["count"])
        top = point_on(c, c, ch.arc_r, -90)
        bottom = point_on(c, c, ch.arc_r, 90)
        rim_d = (
            f"M {fmt(top[0])},{fmt(top[1])} A {fmt(ch.arc_r)},{fmt(ch.arc_r)} 0 0 1 "
            f"{fmt(bottom[0])},{fmt(bottom[1])} A {fmt(ch.arc_r)},{fmt(ch.arc_r)} 0 0 1 {fmt(top[0])},{fmt(top[1])}"
        )
        dur = str(orbit["dur"])
        step = float(dur.rstrip("s")) / count
        accent = 0 if ctx.palette_len else -1
        extra_particles = tuple(
            ParticlePlacement(
                connector_index=-1,
                accent_index=accent,
                r=float(orbit["r"]),
                dur=dur,
                begin=fmt_s(-(i * step)),
                path_override=rim_d,
            )
            for i in range(count)
        )
    return finish_layout(ctx, width=size, height=size, nodes_paint=paint, geos=geos, extra_particles=extra_particles)


def solve_flywheel(ctx: SolverContext) -> DiagramLayout:
    """K phase nodes on a ring, arcs between consecutive phases trimmed by
    each node's angular half-width plus a clearance; an optional hero is
    the center axis, not a fifth step. Arc geometry rides EdgeGeo.arc so
    flow currents can subdivide past the sagitta threshold. The cyclic
    family's hero-bearing expression."""
    return _solve_cyclic(ctx)


def _shift_placement(p: NodePlacement, dx: float, dy: float) -> NodePlacement:
    """Translate a frozen placement (bbox crop, G6): box, circle geometry,
    text runs, dot, and the mark's transform string all move together."""
    from hyperweave.compose.spatial_records import RectSpec

    def sh_text(tx: DiagramText | None) -> DiagramText | None:
        return None if tx is None else replace(tx, x=tx.x + dx, y=tx.y + dy)

    glyph = p.glyph
    if glyph is not None and glyph.transform.startswith("translate("):
        m = re.match(r"translate\((-?[\d.]+),(-?[\d.]+)\)(.*)", glyph.transform)
        if m:
            new_t = f"translate({float(m.group(1)) + dx:.2f},{float(m.group(2)) + dy:.2f}){m.group(3)}"
            glyph = replace(glyph, transform=new_t, cx=glyph.cx + dx, cy=glyph.cy + dy)
    label = sh_text(p.label)
    assert label is not None
    return replace(
        p,
        box=RectSpec(x=p.box.x + dx, y=p.box.y + dy, w=p.box.w, h=p.box.h, rx=p.box.rx),
        label=label,
        desc_lines=tuple(sh_text(d) for d in p.desc_lines if d is not None),  # type: ignore[misc]
        dot=(p.dot[0] + dx, p.dot[1] + dy) if p.dot else None,
        dot_path=translate_path(p.dot_path, dx, dy),
        health_dot=(p.health_dot[0] + dx, p.health_dot[1] + dy) if p.health_dot else None,
        short=sh_text(p.short),
        tag=sh_text(p.tag),
        glyph=glyph,
        cx=p.cx + dx if p.shape == "circle" else p.cx,
        cy=p.cy + dy if p.shape == "circle" else p.cy,
    )


def solve_tree_radial(ctx: SolverContext) -> DiagramLayout:
    """The mindmap: root centered, ring radii scaled by OCCUPANCY, ring-1
    UNIFORM at 360/k1 starting straight up (both specimens: the mindmap's 4
    classes sit dead on the compass at 90 deg apart, dep-audit-radial's 6
    direct deps at 60 deg apart, EACH regardless of whether that sibling
    carries a transitive child) — a subtree's own packing NEED (G6) grows
    the RADIUS when it doesn't fit its uniform slice, it never claims a
    bigger slice off a plainer sibling. Below ring-1, a parent's own sector
    subdivides by leaf count (mindmap's 2-leaf classes fan +/-22 deg; a
    single child inherits the whole parent sector, landing on the parent's
    own bearing — dep-audit-radial's transitives). Ring radii shrink with
    sparse trees, and the canvas crops to the placed content's bbox + pad.
    Hierarchy arrives through the hybrid edge model (explicit parent edges,
    validated as a rooted tree)."""
    ch = ctx.ch
    spec = ctx.spec
    cfg = ctx.cfg
    edges = resolved_edges(spec)
    children: dict[int, list[int]] = {}
    for e in edges:
        children.setdefault(e.source, []).append(e.target)
    ring1 = children.get(0, [])
    caps = ctx.engine.get("caps") or {}
    if len(ring1) > int(caps.get("tree_radial_max_ring1", 7)):
        from hyperweave.core.diagram import DiagramCapacityError

        raise DiagramCapacityError(
            f"tree:radial caps at {caps.get('tree_radial_max_ring1', 7)} ring-1 children (got {len(ring1)})"
        )

    def leaves(i: int) -> int:
        kids = children.get(i, [])
        return 1 if not kids else sum(leaves(j) for j in kids)

    def ring_counts(i: int, depth: int, acc: dict[int, int]) -> None:
        if depth > 0:
            acc[depth] = acc.get(depth, 0) + 1
        for j in children.get(i, []):
            ring_counts(j, depth + 1, acc)

    # Occupancy-scaled radii (G6) with clearance-true extents (G7): needed
    # span per child sums each member's SOLVED box width + min_clearance at
    # its ring radius; scaling every radius by total/360 re-expands the
    # packing to the circle (span scales 1/r), so sparse trees pull their
    # rings IN instead of holding specimen radii. ``ch.r1``/``ch.r2`` (the
    # PRE-scale base, primer.yaml's tree-radial block) carry the mindmap +
    # dep-audit-radial specimen citations — see that block's own comment for
    # the two hw:spatial-notes R1/R2 pairs and why one base can't hit both
    # exactly.
    clearance = float(ctx.engine.get("min_clearance", 20))
    pitch_r = ch.r2 - ch.r1
    base_radius = {1: ch.r1, 2: ch.r2, 3: ch.r2 + pitch_r}

    def node_w(i: int, depth: int) -> float:
        # Role-derived (mismatch class FIXED); the depth-tier chassis class
        # is the one positional pick the solver still owns.
        chassis_class = "" if depth <= 1 else "node2"
        w, _, _ = solve_node_box(ctx, spec.nodes[i], i, chassis_class=chassis_class)
        return w

    def ring_members(i: int, depth: int, acc: dict[int, list[int]]) -> None:
        if depth > 0:
            acc.setdefault(depth, []).append(i)
        for j in children.get(i, []):
            ring_members(j, depth + 1, acc)

    def needed_deg(child: int, radii: dict[int, float]) -> float:
        acc: dict[int, list[int]] = {}
        ring_members(child, 1, acc)
        return max(
            sum(math.degrees((node_w(i, d) + clearance) / radii[min(d, 3)]) for i in members)
            for d, members in acc.items()
        )

    total = sum(needed_deg(kid, base_radius) for kid in ring1)
    scale = min(1.6, max(0.72, total / 360.0))
    radius_of = {d: r * scale for d, r in base_radius.items()}
    # Hub clearance floor (G7): ring-1 centers stay a hub-half + card-half
    # + clearance out, whatever occupancy did.
    hub_is_circle = style_of(spec.nodes[0], ctx.spec, ctx.ch) == NodeStyle.GLYPH_CIRCLE.value
    if hub_is_circle:
        hub_w = 2 * ch.hero_circle_r
    else:
        # Snug-width ruling: the hub solves to its own content; chassis
        # archetypes only bound growth as ceilings inside the sizing seam.
        hub_w, _, _ = solve_node_box(ctx, spec.nodes[0], 0)
    max_w1 = max((node_w(i, 1) for i in ring1), default=ch.node.w)
    radius_of[1] = max(radius_of[1], hub_w / 2 + max_w1 / 2 + clearance)
    # Ring-pitch floor: adjacent rings keep a card height + breathing room
    # apart, whatever the occupancy scale did.
    min_pitch = ch.node.h + 2 * clearance
    for d in (2, 3):
        if radius_of[d] - radius_of[d - 1] < min_pitch:
            radius_of[d] = radius_of[d - 1] + min_pitch
    max_depth = 1
    for kid in ring1:
        acc: dict[int, int] = {}
        ring_counts(kid, 1, acc)
        max_depth = max(max_depth, *acc.keys())
    c = float(base_radius[min(max_depth, 3)] * 2 + ch.node.w + 16)  # provisional center; bbox crop resizes
    placed: dict[int, NodePlacement] = {}

    def place_subtree(node_index: int, depth: int, sector_start: float, sector_span: float) -> None:
        mid = sector_start + sector_span / 2
        if depth > 0:
            cx, cy = point_on(c, c, radius_of[min(depth, 3)], mid)
            placed[node_index] = _place_at_center(
                ctx,
                node_index,
                spec.nodes[node_index],
                cx,
                cy,
                hero=False,
                nch_name="node2" if depth >= 2 else "",
                ring_center=(c, c),  # radial-outboard for any glyph-circle leaf (cards label inside)
            )
        kids = children.get(node_index, [])
        if not kids:
            return
        total_leaves = sum(leaves(k) for k in kids)
        cursor = sector_start
        for kid in kids:
            span = sector_span * leaves(kid) / total_leaves
            place_subtree(kid, depth + 1, cursor, span)
            cursor += span

    def min_box_clearance() -> float:
        boxes = [p.box for p in placed.values()] + [hub.box]
        worst = float("inf")
        for i, a in enumerate(boxes):
            for b in boxes[i + 1 :]:
                gx = max(a.x - (b.x + b.w), b.x - (a.x + a.w), 0.0)
                gy = max(a.y - (b.y + b.h), b.y - (a.y + a.h), 0.0)
                if gx == 0.0 and gy == 0.0:
                    return 0.0
                worst = min(worst, math.hypot(gx, gy))
        return worst

    # Ring-1 sector: UNIFORM (both specimens split 360 evenly across their
    # direct children — 4x90deg, 6x60deg — with no wider slice for a sibling
    # that happens to carry a transitive child). A lopsided subtree instead
    # grows the RADIUS below (relaxation), never claims more arc than its
    # equal-born siblings. ``place_subtree`` seats a node at its SECTOR's
    # midpoint (so a parent's own inherited sector still centers its
    # children below), so ring-1's own first sector starts a HALF-pitch
    # before due north — its midpoint then lands exactly on -90, matching
    # both specimens' first-declared child (mindmap's "diagram", dep-audit-
    # radial's "react") sitting dead straight up, not half a pitch off it.
    k1 = len(ring1)
    uniform_span = 360.0 / k1 if k1 else 0.0
    # Relaxation (G7): packing is need-based but cross-ring adjacency can
    # still kiss; scale the rings out in bounded deterministic steps until
    # every box pair clears min_clearance.
    for _ in range(8):
        placed.clear()
        cursor = -90.0 - uniform_span / 2.0
        for kid in ring1:
            place_subtree(kid, 1, cursor, uniform_span)
            cursor += uniform_span
        hub = _place_at_center(ctx, 0, spec.nodes[0], c, c, hero=True)
        if min_box_clearance() >= clearance:
            break
        radius_of = {d: r * 1.12 for d, r in radius_of.items()}

    # ── bbox crop (G6): the canvas is the content, not the ring formula ──
    from hyperweave.compose.matrix.cells import measure_voice

    def extents(p: NodePlacement) -> tuple[float, float, float, float]:
        x0, y0 = p.box.x, p.box.y
        x1, y1 = p.box.x + p.box.w, p.box.y + p.box.h
        for run in (p.label, *p.desc_lines):
            if run is None or not run.text:
                continue
            w = measure_voice(run.text, voice_for(cfg, run.cls))
            asc = cfg.text_ascent_ratio * voice_for(cfg, run.cls).size
            dsc = cfg.text_descent_ratio * voice_for(cfg, run.cls).size
            rx0 = run.x - (w / 2 if run.anchor == "middle" else 0.0)
            x0, x1 = min(x0, rx0), max(x1, rx0 + w)
            y0, y1 = min(y0, run.y - asc), max(y1, run.y + dsc)
        return x0, y0, x1, y1

    all_p = [*placed.values(), hub]
    bx0 = min(extents(p)[0] for p in all_p)
    by0 = min(extents(p)[1] for p in all_p)
    bx1 = max(extents(p)[2] for p in all_p)
    by1 = max(extents(p)[3] for p in all_p)
    pad = 24.0
    top_pad = 56.0 if spec.title else pad
    dx, dy = pad - bx0, top_pad - by0
    placed = {i: _shift_placement(p, dx, dy) for i, p in placed.items()}
    hub = _shift_placement(hub, dx, dy)
    c_x, c_y = c + dx, c + dy
    size_w = math.ceil(bx1 - bx0 + 2 * pad)
    size_h = math.ceil(by1 - by0 + top_pad + pad)

    ring1_angles = [
        math.degrees(
            math.atan2(placed[i].box.y + placed[i].box.h / 2 - c_y, placed[i].box.x + placed[i].box.w / 2 - c_x)
        )
        for i in ring1
    ]
    hub, label_box = _hub_label_box(ctx, hub, ring1_angles)
    clear = float(ctx.engine["connector"].get("hub_label_clear", 6))
    standoff = float(ctx.engine["connector"].get("standoff", 0))
    geos: list[EdgeGeo] = []
    for j, e in enumerate(edges):
        if e.source == 0:
            target = placed[e.target]
            ax, ay = boundary_anchor(target, c_x, c_y, standoff)
            hx, hy = _hub_clearance_anchor(hub, label_box, ax, ay, clear)
            geos.append(
                EdgeGeo(index=j, d=ray_d(hx, hy, ax, ay), sx=hx, sy=hy, tx=ax, ty=ay, length=line_len(hx, hy, ax, ay))
            )
        else:
            pnode, cnode = placed[e.source], placed[e.target]
            pcx, pcy = pnode.box.x + pnode.box.w / 2, pnode.box.y + pnode.box.h / 2
            ax, ay = boundary_anchor(cnode, pcx, pcy, standoff)
            bx, by = boundary_anchor(pnode, ax, ay, standoff)
            bx, by, ax, ay = lane_endpoints(bx, by, ax, ay, ctx.lanes[j], ctx.lane_offsets[j])
            geos.append(
                EdgeGeo(index=j, d=ray_d(bx, by, ax, ay), sx=bx, sy=by, tx=ax, ty=ay, length=line_len(bx, by, ax, ay))
            )
    paint = [placed[i] for i in sorted(placed)] + [hub]
    # The cropped canvas still honours the page scale law: floor it at the
    # chassis width so the display pin downscales (never magnifies) type.
    size_w = max(size_w, int(ch.width))
    return finish_layout(ctx, width=size_w, height=size_h, nodes_paint=paint, geos=geos)


def _annotation_line_boxes(ctx: SolverContext, p: NodePlacement, pad: float) -> list[tuple[float, float, float, float]]:
    """Per-LINE padded boxes of a placed node's OUTSIDE text — the obstruction
    a ring arc must clear beyond the node silhouette. Per line, never the
    stack union: the union rectangle claims the empty ragged corners beside
    short runs and over-trimmed ring arcs to a 12.1° mean span where the
    hand file holds 34° on four arcs and walks text on only two ends
    (+13.2° exactly where the arc strikes an actual run)."""
    boxes: list[tuple[float, float, float, float]] = []
    for t in (p.label, *p.desc_lines):
        if t is None or not t.text:
            continue
        voice = voice_for(ctx.cfg, t.cls)
        w = measure_voice(t.text, voice)
        x0 = t.x - (w / 2 if t.anchor == "middle" else (w if t.anchor == "end" else 0.0))
        boxes.append(
            (
                x0 - pad,
                t.y - voice.size * ctx.cfg.text_ascent_ratio - pad,
                x0 + w + pad,
                t.y + voice.size * ctx.cfg.text_descent_ratio + pad,
            )
        )
    return boxes


def solve_ring(ctx: SolverContext) -> DiagramLayout:
    """RING (the agent-loop-ring specimen): K equal medallions at even pitch
    from the top on one ring, EMPTY centre — no hero, every stage equal.
    Congruent arcs trim each node's angular half-width plus the clearance,
    then extend past the endpoint node's stacked annotation block (the
    specimen starts its side arcs beneath the upper text, so the arrowhead
    emerges under the ink, never through it). Annotations stack BELOW every
    node — one rule, K identical applications; upper text falls inside the
    ring toward the empty centre, which earns its keep as text room. The
    cyclic family's hero-less expression (raises if a hero is declared)."""
    return _solve_cyclic(ctx)


register_solvers(
    {
        "fanout-radial": solve_fanout_radial,
        "flywheel": solve_flywheel,
        "ring": solve_ring,
        "tree-radial": solve_tree_radial,
    }
)
