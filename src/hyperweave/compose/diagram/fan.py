"""S-curve family solvers: fanout (horizontal, bilateral, upward) and
convergence. Every curve is a midpoint S — control points at the chord
midpoint, verified exact against all specimen connectors. Heights grow
with the dest/input count; widths are the banner contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hyperweave.compose.diagram.chrome import (
    glyph_slot_builder,
    mark_w_for,
    place_card,
    place_circle,
    solve_card_w,
)
from hyperweave.compose.diagram.motion import lane_endpoints
from hyperweave.compose.diagram.paths import s_curve_h, s_curve_h_len, s_curve_v, s_curve_v_len
from hyperweave.compose.diagram.solver import finish_layout, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
from hyperweave.core.diagram import DiagramNode, NodeStyle

if TYPE_CHECKING:
    from collections.abc import Callable

    from hyperweave.compose.diagram.records import DiagramLayout, GlyphArt, NodePlacement


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


def _member_widths(ctx: SolverContext, nodes: list[DiagramNode]) -> list[float]:
    """G3 width policy from the chassis: free content-solves each member
    (slack never exceeds the symmetric pads); aligned shares the max."""
    ch = ctx.ch
    widths = [
        solve_card_w(
            n,
            ch.node,
            ctx.cfg,
            ctx.mono_triggers,
            min_w=ch.card_min_w,
            mark_w=mark_w_for(_style_of(ctx, n), n),
        )
        for n in nodes
    ]
    if ch.width_policy == "aligned":
        shared = max(widths)
        return [shared] * len(widths)
    return widths


def _pitch(ctx: SolverContext) -> float:
    p = ctx.ch.pitch
    if ctx.shrink:
        p *= float((ctx.engine.get("caps") or {}).get("shrink_factor", 0.85))
    return p


def _place(
    ctx: SolverContext, i: int, node: DiagramNode, *, x: float, y: float, hero: bool, w_override: float = 0.0
) -> NodePlacement:
    """Card or glyph-circle per the style cascade; (x, y) is the card's
    top-left — circle placement converts to the equivalent center."""
    ch = ctx.ch
    nch = ch.hero if hero else ch.node
    if _style_of(ctx, node) == NodeStyle.GLYPH_CIRCLE.value:
        r = ch.hero_circle_r if hero else ch.circle_r
        return place_circle(
            index=i,
            node=node,
            cx=x + nch.w / 2,
            cy=y + nch.h / 2,
            r=r,
            cfg=ctx.cfg,
            ch=ch,
            accent_index=ctx.node_accents[i],
            hub=hero,
            registry=ctx.glyph_registry,
            glyph_selection=ctx.glyph_selections[i],
        )
    return place_card(
        index=i,
        node=node,
        x=x,
        y=y,
        nch=nch,
        cfg=ctx.cfg,
        accent_index=ctx.node_accents[i],
        mono_triggers=ctx.mono_triggers,
        muted_dash=_muted_dash(ctx),
        w_override=w_override,
        glyph_builder=_card_art(ctx, i, node),
    )


def _edge_x(p: NodePlacement, *, toward_right: bool, fan_dy: float = 0.0) -> tuple[float, float]:
    """An edge's anchor on a node: card edge midpoint or circle rim; hubs
    fan their anchors vertically so multiple spokes don't stack."""
    if p.shape == "circle":
        inset = 2.0 if fan_dy else 0.0
        return (p.cx + (p.r - inset) if toward_right else p.cx - (p.r - inset), p.cy + fan_dy)
    b = p.box
    return (b.x + b.w if toward_right else b.x, b.y + b.h / 2 + fan_dy)


def _fan_offsets(k: int, step: float = 12.0) -> list[float]:
    return [(i - (k - 1) / 2) * step for i in range(k)]


def solve_fanout_horizontal(ctx: SolverContext) -> DiagramLayout:
    """Source left, dest column right: one-to-many reads left to right.
    The source centers on the dest column (rule over the specimen's
    hand-raised source)."""
    ch = ctx.ch
    spec = ctx.spec
    width = ch.width
    k = len(spec.nodes) - 1
    p = _pitch(ctx)
    dest_ws = _member_widths(ctx, list(spec.nodes[1:]))
    dest_x = width - ch.margin_x - max(dest_ws)
    content_top = ch.header_h
    column_h = (k - 1) * p + ch.node.h
    src_cy = content_top + column_h / 2
    # The footer band spans last-dest-bottom -> canvas edge (the specimen's
    # 78px already includes the breathing room — no separate bottom margin).
    height = int(content_top + column_h + ch.footer_h)
    nodes: list[NodePlacement] = [_place(ctx, 0, spec.nodes[0], x=ch.margin_x, y=src_cy - ch.hero.h / 2, hero=True)]
    for i, node in enumerate(spec.nodes[1:], start=1):
        nodes.append(_place(ctx, i, node, x=dest_x, y=content_top + (i - 1) * p, hero=False, w_override=dest_ws[i - 1]))
    geos: list[EdgeGeo] = []
    for j, edge in enumerate(ctx.edges):
        src, dst = nodes[edge.source], nodes[edge.target]
        rightward = dst.box.x > src.box.x
        sx, sy = _edge_x(src, toward_right=rightward)
        tx, ty = _edge_x(dst, toward_right=not rightward)
        x1, y1, x2, y2 = lane_endpoints(sx, sy, tx, ty, ctx.lanes[j], ctx.lane_offsets[j])
        geos.append(
            EdgeGeo(
                index=j,
                d=s_curve_h(x1, y1, x2, y2),
                sx=x1,
                sy=y1,
                tx=x2,
                ty=y2,
                length=s_curve_h_len(x1, y1, x2, y2),
            )
        )
    return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)


def solve_fanout_bilateral(ctx: SolverContext) -> DiagramLayout:
    """Source centered, dests split left/right (|L - R| <= 1, spec order
    fills left first). Both sides distribute over one shared vertical band
    so the composition stays symmetric about the source."""
    ch = ctx.ch
    spec = ctx.spec
    width = ch.width
    k = len(spec.nodes) - 1
    left_n = k // 2
    right_n = k - left_n
    p = _pitch(ctx)
    band = (max(left_n, right_n) - 1) * p
    src_cy = ch.header_h + (band + ch.node.h) / 2
    height = int(2 * src_cy)
    # The source occupies the hero CHASSIS slot structurally; its border
    # stays role-driven (place_* reads node.role).
    nodes: list[NodePlacement] = [
        _place(ctx, 0, spec.nodes[0], x=width / 2 - ch.hero.w / 2, y=src_cy - ch.hero.h / 2, hero=True)
    ]

    def side_cy(idx: int, count: int) -> float:
        if count == 1:
            return src_cy
        return src_cy - band / 2 + idx * (band / (count - 1))

    dest_ws = _member_widths(ctx, list(spec.nodes[1:]))
    left_ws = [w for w, i in zip(dest_ws, range(1, len(spec.nodes)), strict=True) if (i - 1) < left_n]
    facing_left = ch.margin_x + (max(left_ws) if left_ws else 0.0)
    sides: list[int] = []
    for i, node in enumerate(spec.nodes[1:], start=1):
        on_left = (i - 1) < left_n
        idx = (i - 1) if on_left else (i - 1 - left_n)
        cy = side_cy(idx, left_n if on_left else right_n)
        w = dest_ws[i - 1]
        x = facing_left - w if on_left else width - ch.margin_x - max(dest_ws)
        nodes.append(_place(ctx, i, node, x=x, y=cy - ch.node.h / 2, hero=False, w_override=w))
        sides.append(0 if on_left else 1)
    hub = nodes[0]
    left_fans = _fan_offsets(left_n)
    right_fans = _fan_offsets(right_n)
    left_seen = right_seen = 0
    geos: list[EdgeGeo] = []
    for j, edge in enumerate(ctx.edges):
        other_idx = edge.target if edge.source == 0 else edge.source
        on_left = sides[other_idx - 1] == 0
        if on_left:
            fan = left_fans[left_seen]
            left_seen += 1
        else:
            fan = right_fans[right_seen]
            right_seen += 1
        hub_pt = _edge_x(hub, toward_right=not on_left, fan_dy=fan)
        other = nodes[other_idx]
        other_pt = _edge_x(other, toward_right=on_left)
        if edge.source == 0:
            sx, sy, tx, ty = hub_pt[0], hub_pt[1], other_pt[0], other_pt[1]
        else:
            sx, sy, tx, ty = other_pt[0], other_pt[1], hub_pt[0], hub_pt[1]
        x1, y1, x2, y2 = lane_endpoints(sx, sy, tx, ty, ctx.lanes[j], ctx.lane_offsets[j])
        geos.append(
            EdgeGeo(
                index=j,
                d=s_curve_h(x1, y1, x2, y2),
                sx=x1,
                sy=y1,
                tx=x2,
                ty=y2,
                length=s_curve_h_len(x1, y1, x2, y2),
                flow_side=0 if on_left else 1,
            )
        )
    return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)


def solve_fanout_upward(ctx: SolverContext) -> DiagramLayout:
    """Headerless inverted pyramid: dest rows fill top-down (row_cap per
    row, remainder last), every row centered; the source sits beneath and
    particles rise. The compact embed of the family."""
    ch = ctx.ch
    spec = ctx.spec
    width = ch.width
    k = len(spec.nodes) - 1
    rows: list[int] = []
    remaining = k
    while remaining > 0:
        take = min(ch.row_cap, remaining)
        rows.append(take)
        remaining -= take
    # The REMAINDER row rides on top (G7): with the full row nearest the
    # source, curves to the far row rise through the full row's wide gaps
    # instead of crossing a centered box's corridor.
    rows.reverse()
    k_max = max(rows)
    dest_ws = _member_widths(ctx, list(spec.nodes[1:]))
    pitch_x = (width - 2 * ch.margin_x - max(dest_ws)) / (k_max - 1) if k_max > 1 else 0.0
    nodes: list[NodePlacement] = []
    positions: list[tuple[float, float]] = []  # dest centers (cx, bottom_y)
    y = ch.margin_top
    for row_count in rows:
        for i in range(row_count):
            cx = width / 2 + (i - (row_count - 1) / 2) * pitch_x
            positions.append((cx, y + ch.node.h))
        y += ch.node.h + ch.row_gap
    src_top = y - ch.row_gap + ch.src_gap
    height = int(src_top + ch.hero.h + ch.bottom_m)
    nodes.append(_place(ctx, 0, spec.nodes[0], x=width / 2 - ch.hero.w / 2, y=src_top, hero=True))
    for i, node in enumerate(spec.nodes[1:], start=1):
        cx, bottom = positions[i - 1]
        w = dest_ws[i - 1]
        nodes.append(_place(ctx, i, node, x=cx - w / 2, y=bottom - ch.node.h, hero=False, w_override=w))
    # Root each curve directly under its dest, clamped to the source's top
    # edge (G7): a centered start hugs the inner row boxes; a dest-aligned
    # root rises through the row gaps and bends only over the last span.
    half = ch.hero.w / 2 - 14.0
    geos: list[EdgeGeo] = []
    for j, edge in enumerate(ctx.edges):
        other = edge.target if edge.target != 0 else edge.source
        dest = nodes[other]
        dcx, dbottom = dest.box.x + dest.box.w / 2, dest.box.y + dest.box.h
        root_x = min(max(dcx, width / 2 - half), width / 2 + half)
        upward = edge.target != 0
        if upward:
            sx, sy, tx, ty = root_x, src_top, dcx, dbottom
        else:
            sx, sy, tx, ty = dcx, dbottom, root_x, src_top
        x1, y1, x2, y2 = lane_endpoints(sx, sy, tx, ty, ctx.lanes[j], ctx.lane_offsets[j])
        geos.append(
            EdgeGeo(
                index=j,
                d=s_curve_v(x1, y1, x2, y2),
                sx=x1,
                sy=y1,
                tx=x2,
                ty=y2,
                length=s_curve_v_len(x1, y1, x2, y2),
            )
        )
    return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)


def solve_convergence(ctx: SolverContext) -> DiagramLayout:
    """Inputs in a left column, the hero on the right, every curve meeting
    one point on the hero's facing edge — ingestion has a single mouth."""
    ch = ctx.ch
    spec = ctx.spec
    width = ch.width
    k = len(spec.nodes) - 1
    p = _pitch(ctx)
    content_top = ch.header_h
    column_h = (k - 1) * p + ch.node.h
    hero_cy = content_top + column_h / 2
    height = int(content_top + column_h + ch.bottom_m)
    in_ws = _member_widths(ctx, list(spec.nodes[:-1]))
    hero_w = solve_card_w(spec.nodes[-1], ch.hero, ctx.cfg, ctx.mono_triggers, hero=True, min_w=ch.card_min_w)
    nodes: list[NodePlacement] = []
    for i, node in enumerate(spec.nodes[:-1]):
        nodes.append(_place(ctx, i, node, x=ch.margin_x, y=content_top + i * p, hero=False, w_override=in_ws[i]))
    hero_i = len(spec.nodes) - 1
    nodes.append(
        _place(
            ctx,
            hero_i,
            spec.nodes[-1],
            x=width - ch.margin_x - hero_w,
            y=hero_cy - ch.hero.h / 2,
            hero=True,
            w_override=hero_w,
        )
    )
    hero = nodes[hero_i]
    geos: list[EdgeGeo] = []
    for j, edge in enumerate(ctx.edges):
        src = nodes[edge.source]
        sx, sy = _edge_x(src, toward_right=True)
        tx, ty = _edge_x(hero, toward_right=False)
        if edge.target != hero_i:  # a flipped pair (hero feeding back)
            sx, sy = _edge_x(hero, toward_right=False)
            tx, ty = _edge_x(nodes[edge.target], toward_right=True)
        x1, y1, x2, y2 = lane_endpoints(sx, sy, tx, ty, ctx.lanes[j], ctx.lane_offsets[j])
        geos.append(
            EdgeGeo(
                index=j,
                d=s_curve_h(x1, y1, x2, y2),
                sx=x1,
                sy=y1,
                tx=x2,
                ty=y2,
                length=s_curve_h_len(x1, y1, x2, y2),
            )
        )
    return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)


register_solvers(
    {
        "fanout-horizontal": solve_fanout_horizontal,
        "fanout-bilateral": solve_fanout_bilateral,
        "fanout-upward": solve_fanout_upward,
        "convergence": solve_convergence,
    }
)
