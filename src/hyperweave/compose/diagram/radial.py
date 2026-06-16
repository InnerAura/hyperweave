"""Polar-family solvers: fanout-radial, flywheel, and the multi-level
radial tree (per-subtree angular subdivision).

The radial fan's connectors are drawn from the HUB CENTER and the hub
paints last — the card masks the inner stubs so spokes appear to emanate
from its surface (paint order is data, never a template branch). Flywheel
arcs trim each card's angular half-width plus a clearance, reproducing the
specimen's 24-degree insets at any ring count.
"""

from __future__ import annotations

import math
import re
from dataclasses import replace
from typing import TYPE_CHECKING

from hyperweave.compose.diagram.anchors import boundary_anchor, rect_distance, trim_arc_angle
from hyperweave.compose.diagram.chrome import (
    glyph_slot_builder,
    mark_w_for,
    place_card,
    place_circle,
    solve_card_w,
    voice_for,
)
from hyperweave.compose.diagram.motion import lane_endpoints
from hyperweave.compose.diagram.paths import arc_d, arc_len, line_len, point_on, ray_d
from hyperweave.compose.diagram.solver import finish_layout, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
from hyperweave.core.diagram import DiagramNode, NodeRole, NodeStyle, resolved_edges

if TYPE_CHECKING:
    from collections.abc import Callable

    from hyperweave.compose.diagram.records import DiagramLayout, DiagramText, GlyphArt, NodePlacement


def _style_of(ctx: SolverContext, node: DiagramNode) -> str:
    if node.style is not None:
        return node.style.value
    if ctx.spec.node_style is not None:
        return ctx.spec.node_style.value
    return ctx.ch.node_style or NodeStyle.CARD.value


def _muted_dash(ctx: SolverContext) -> str:
    return str(ctx.engine["track"]["muted_dash"])


def _card_art(ctx: SolverContext, i: int, node: DiagramNode) -> Callable[[float, float], GlyphArt | None] | None:
    """card+glyph anatomy: the identity mark takes the dot slot."""
    if _style_of(ctx, node) != NodeStyle.CARD_GLYPH.value or not node.glyph:
        return None
    return glyph_slot_builder(node.glyph, ctx.glyph_registry, ctx.glyph_selections[i])


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
) -> NodePlacement:
    ch = ctx.ch
    nch = ch.hero if hero else (ch.node2 if nch_name == "node2" else ch.node)
    if _style_of(ctx, node) == NodeStyle.GLYPH_CIRCLE.value:
        r = ch.hero_circle_r if hero else ch.circle_r
        return place_circle(
            index=i,
            node=node,
            cx=cx,
            cy=cy,
            r=r,
            cfg=ctx.cfg,
            ch=ch,
            accent_index=ctx.node_accents[i],
            hub=hero,
            registry=ctx.glyph_registry,
            glyph_selection=ctx.glyph_selections[i],
            ring_center=ring_center,
        )
    w = solve_card_w(
        node,
        nch,
        ctx.cfg,
        ctx.mono_triggers,
        hero=hero,
        min_w=ch.card_min_w,
        mark_w=mark_w_for(_style_of(ctx, node), node),
    )
    x0, y0 = cx - w / 2, cy - nch.h / 2
    return place_card(
        index=i,
        node=node,
        x=x0,
        y=y0,
        nch=nch,
        cfg=ctx.cfg,
        accent_index=ctx.node_accents[i],
        mono_triggers=ctx.mono_triggers,
        muted_dash=_muted_dash(ctx),
        w_override=w,
        glyph_builder=_card_art(ctx, i, node),
    )


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
            lcx, lcy, w, h = label_box
            d = min(d, rect_distance(lcx, lcy, w + 2 * clear, h + 2 * clear, 0.0, x, y))
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


def solve_fanout_radial(ctx: SolverContext) -> DiagramLayout:
    """Hub centered, dests on a ring at equal angles from the top; rays
    drawn under the hub. The ring grows past its base radius when the
    perimeter would crowd (K x (node width + ring_gap) / 2pi)."""
    ch = ctx.ch
    spec = ctx.spec
    k = len(spec.nodes) - 1
    radius = max(ch.ring_r, k * (ch.node.w + ch.ring_gap) / (2 * math.pi))
    size = math.ceil(2 * (radius + ch.node.w / 2) + 16) if radius > ch.ring_r else ch.width
    c = size / 2
    dests: list[NodePlacement] = []
    spoke_angles: list[float] = []
    for i, node in enumerate(spec.nodes[1:], start=1):
        theta = -90 + (i - 1) * 360 / k
        spoke_angles.append(theta)
        cx, cy = point_on(c, c, radius, theta)
        # Radial-outboard labels (K-radial-general): glyph-circle dests
        # label along the spoke away from the hub; a below-label would
        # point inward and the spoke would cross it. Card dests carry their
        # label inside the card — ring_center is inert for them.
        dests.append(_place_at_center(ctx, i, node, cx, cy, hero=False, ring_center=(c, c)))
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


def solve_flywheel(ctx: SolverContext) -> DiagramLayout:
    """K phase nodes on a ring, arcs between consecutive phases trimmed by
    each node's angular half-width plus a clearance; an optional hero is
    the center axis, not a fifth step. Arc geometry rides EdgeGeo.arc so
    flow currents can subdivide past the sagitta threshold."""
    ch = ctx.ch
    spec = ctx.spec
    size = ch.width
    c = size / 2
    ring = [i for i, node in enumerate(spec.nodes) if node.role is not NodeRole.HERO]
    k = len(ring)
    angle_of: dict[int, float] = {}
    placed: dict[int, NodePlacement] = {}
    for pos, i in enumerate(ring):
        theta = -90 + pos * 360 / k
        angle_of[i] = theta
        cx, cy = point_on(c, c, ch.ring_r, theta)
        # Labels place RADIALLY outboard (K-radial-label): the ring stroke
        # runs through these node centers, so a below-label collides at 3
        # and 9 o'clock — the spoke direction from the ring center keeps it
        # in open air.
        placed[i] = _place_at_center(ctx, i, spec.nodes[i], cx, cy, hero=False, ring_center=(c, c))
    hero_node = next((i for i, node in enumerate(spec.nodes) if node.role is NodeRole.HERO), None)
    paint: list[NodePlacement] = [placed[i] for i in ring]
    if hero_node is not None:
        paint.append(_place_at_center(ctx, hero_node, spec.nodes[hero_node], c, c, hero=True))
    standoff = float(ctx.engine["connector"].get("standoff", 0))
    geos: list[EdgeGeo] = []
    for j, edge in enumerate(ctx.edges):
        # Trim each arc end at the actual node boundary (shape-true): a
        # half-height side approach stops where the card stops, not at a
        # half-width-as-radius estimate.
        a0 = trim_arc_angle(
            placed[edge.source],
            arc_cx=c,
            arc_cy=c,
            arc_r=ch.arc_r,
            node_angle_deg=angle_of[edge.source],
            direction=+1,
            standoff=standoff + ch.arc_clear_deg * 0,
        )
        a1 = trim_arc_angle(
            placed[edge.target],
            arc_cx=c,
            arc_cy=c,
            arc_r=ch.arc_r,
            node_angle_deg=angle_of[edge.target],
            direction=-1,
            standoff=standoff,
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
    return finish_layout(ctx, width=size, height=size, nodes_paint=paint, geos=geos)


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
        short=sh_text(p.short),
        tag=sh_text(p.tag),
        glyph=glyph,
        cx=p.cx + dx if p.shape == "circle" else p.cx,
        cy=p.cy + dy if p.shape == "circle" else p.cy,
    )


def solve_tree_radial(ctx: SolverContext) -> DiagramLayout:
    """The mindmap: root centered, ring radii scaled by OCCUPANCY and child
    sectors sized by packing NEED (G6) — angular entitlement floors the
    minimum chord separation instead of distributing the full circle, ring
    radii shrink with sparse trees, and the canvas crops to the placed
    content's bbox + pad. Hierarchy arrives through the hybrid edge model
    (explicit parent edges, validated as a rooted tree)."""
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
    # rings IN instead of holding specimen radii.
    clearance = float(ctx.engine.get("min_clearance", 20))
    pitch_r = ch.r2 - ch.r1
    base_radius = {1: ch.r1, 2: ch.r2, 3: ch.r2 + pitch_r}

    def node_w(i: int, depth: int) -> float:
        nch = ch.node if depth <= 1 else ch.node2
        return solve_card_w(
            spec.nodes[i],
            nch,
            ctx.cfg,
            ctx.mono_triggers,
            min_w=ch.card_min_w,
            mark_w=mark_w_for(_style_of(ctx, spec.nodes[i]), spec.nodes[i]),
        )

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
    hub_is_circle = _style_of(ctx, spec.nodes[0]) == NodeStyle.GLYPH_CIRCLE.value
    hub_w = 2 * ch.hero_circle_r if hub_is_circle else node_w(0, 0)
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

    # Relaxation (G7): packing is need-based but cross-ring adjacency can
    # still kiss; scale the rings out in bounded deterministic steps until
    # every box pair clears min_clearance.
    for _ in range(8):
        placed.clear()
        spans = {kid: needed_deg(kid, radius_of) for kid in ring1}
        span_total = sum(spans.values())
        norm = 360.0 / span_total if span_total > 0 else 1.0
        cursor = -90.0
        for kid in ring1:
            span = spans[kid] * norm
            place_subtree(kid, 1, cursor, span)
            cursor += span
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
    # The chassis display_w was tuned for the specimen square; a cropped
    # canvas renders 1:1 (display never downscales type, G6).
    from dataclasses import replace as _dc_replace

    ctx = _dc_replace(ctx, ch=ch.model_copy(update={"display_w": 0, "display_h": 0}))
    return finish_layout(ctx, width=size_w, height=size_h, nodes_paint=paint, geos=geos)


register_solvers(
    {
        "fanout-radial": solve_fanout_radial,
        "flywheel": solve_flywheel,
        "tree-radial": solve_tree_radial,
    }
)
