"""Straight-family solvers: pipeline, stack, comparison, tree (banner).

Constants come from the topology chassis (specimen-extracted); formulas
generalize the hand-crafted specimens to any in-cap N. Rule over handcraft:
where a specimen's hand placement deviates a few px from the closed form
(band centering, riser insets), the form wins — presets stay within
tolerance of their specimens.
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
from hyperweave.compose.diagram.paths import line_d, line_len, s_curve_v, s_curve_v_len
from hyperweave.compose.diagram.records import DiagramLayout, DiagramText, GlyphArt, NodePlacement
from hyperweave.compose.diagram.solver import finish_layout, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
from hyperweave.core.diagram import DiagramNode, NodeRole, NodeStyle

if TYPE_CHECKING:
    from collections.abc import Callable


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


def _gap(ctx: SolverContext, base: float) -> float:
    if not ctx.shrink:
        return base
    return base * float((ctx.engine.get("caps") or {}).get("shrink_factor", 0.85))


def _band_center(ctx: SolverContext, height: float) -> float:
    ch = ctx.ch
    return ch.header_h + (height - ch.header_h - ch.footer_h) / 2


def solve_pipeline(ctx: SolverContext) -> DiagramLayout:
    """N stage cards on one baseline, equal gaps; the hero takes
    hero_ratio x the solved unit width. Glyph-circle style spreads circle
    centers evenly instead (the canon relay anatomy)."""
    ch = ctx.ch
    spec = ctx.spec
    n = len(spec.nodes)
    width, height = ch.width, ch.height or 216
    gap = _gap(ctx, ch.gap)
    cy = _band_center(ctx, height)
    circle_mode = all(_style_of(ctx, node) == NodeStyle.GLYPH_CIRCLE.value for node in spec.nodes)
    nodes: list[NodePlacement] = []
    geos: list[EdgeGeo] = []
    if circle_mode:
        r, hr = ch.circle_r, ch.hero_circle_r
        span = width - 2 * ch.margin_x - 2 * r
        for i, node in enumerate(spec.nodes):
            cx = ch.margin_x + r + (span * i / (n - 1) if n > 1 else span / 2)
            rad = hr if node.role is NodeRole.HERO else r
            nodes.append(
                place_circle(
                    index=i,
                    node=node,
                    cx=cx,
                    cy=cy,
                    r=rad,
                    cfg=ctx.cfg,
                    ch=ch,
                    accent_index=ctx.node_accents[i],
                    hub=node.role is NodeRole.HERO,
                    registry=ctx.glyph_registry,
                    glyph_selection=ctx.glyph_selections[i],
                )
            )
        for k, edge in enumerate(ctx.edges):
            a, b = nodes[edge.source], nodes[edge.target]
            sx = a.cx + a.r if b.cx > a.cx else a.cx - a.r
            tx = b.cx - b.r if b.cx > a.cx else b.cx + b.r
            x1, y1, x2, y2 = lane_endpoints(sx, cy, tx, cy, ctx.lanes[k], ctx.lane_offsets[k])
            geos.append(
                EdgeGeo(index=k, d=line_d(x1, y1, x2, y2), sx=x1, sy=y1, tx=x2, ty=y2, length=line_len(x1, y1, x2, y2))
            )
        return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)
    hero_idx = next((i for i, node in enumerate(spec.nodes) if node.role is NodeRole.HERO), None)
    # Wire-major (K3): an ALL-RECIPROCAL composition makes the channel the
    # subject — cards shrink to content, every run holds the dash-period
    # floor, and the canvas slack (or growth) goes to the wire.
    wire_major = ch.channel_run_min > 0 and len(ctx.lanes) > 0 and all(lane != 0 for lane in ctx.lanes)
    if wire_major:
        widths = [
            solve_card_w(
                node,
                ch.hero if i == hero_idx else ch.node,
                ctx.cfg,
                ctx.mono_triggers,
                hero=i == hero_idx,
                min_w=ch.card_min_w,
                mark_w=mark_w_for(_style_of(ctx, node), node),
            )
            for i, node in enumerate(spec.nodes)
        ]
        run = max(ch.channel_run_min, (width - 2 * ch.margin_x - sum(widths)) / (n - 1))
        width = int(max(width, 2 * ch.margin_x + sum(widths) + (n - 1) * run))
        x = ch.margin_x
        y = cy - ch.node.h / 2
        for i, node in enumerate(spec.nodes):
            nch = ch.hero if i == hero_idx else ch.node
            nodes.append(
                place_card(
                    index=i,
                    node=node,
                    x=x,
                    y=y,
                    nch=nch,
                    cfg=ctx.cfg,
                    accent_index=ctx.node_accents[i],
                    mono_triggers=ctx.mono_triggers,
                    muted_dash=_muted_dash(ctx),
                    glyph_builder=_card_art(ctx, i, node),
                    w_override=widths[i],
                )
            )
            x += widths[i] + run
        for k, edge in enumerate(ctx.edges):
            ab, bb = nodes[edge.source].box, nodes[edge.target].box
            forward = bb.x > ab.x
            sx = ab.x + ab.w if forward else ab.x
            tx = bb.x if forward else bb.x + bb.w
            x1, y1, x2, y2 = lane_endpoints(sx, cy, tx, cy, ctx.lanes[k], ctx.lane_offsets[k])
            geos.append(
                EdgeGeo(index=k, d=line_d(x1, y1, x2, y2), sx=x1, sy=y1, tx=x2, ty=y2, length=line_len(x1, y1, x2, y2))
            )
        return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)
    avail = width - 2 * ch.margin_x - (n - 1) * gap
    unit = avail / ((n - 1) + ch.hero_ratio) if hero_idx is not None else avail / n
    unit = max(unit, ch.card_min_w)
    x = ch.margin_x
    y = cy - ch.node.h / 2
    for i, node in enumerate(spec.nodes):
        w = unit * ch.hero_ratio if i == hero_idx else unit
        nch = ch.hero if i == hero_idx else ch.node
        nodes.append(
            place_card(
                index=i,
                node=node,
                x=x,
                y=y,
                nch=nch,
                cfg=ctx.cfg,
                accent_index=ctx.node_accents[i],
                mono_triggers=ctx.mono_triggers,
                muted_dash=_muted_dash(ctx),
                glyph_builder=_card_art(ctx, i, node),
                w_override=w,
            )
        )
        x += w + gap
    for k, edge in enumerate(ctx.edges):
        ab, bb = nodes[edge.source].box, nodes[edge.target].box
        forward = bb.x > ab.x
        sx = ab.x + ab.w if forward else ab.x
        tx = bb.x if forward else bb.x + bb.w
        x1, y1, x2, y2 = lane_endpoints(sx, cy, tx, cy, ctx.lanes[k], ctx.lane_offsets[k])
        geos.append(
            EdgeGeo(index=k, d=line_d(x1, y1, x2, y2), sx=x1, sy=y1, tx=x2, ty=y2, length=line_len(x1, y1, x2, y2))
        )
    return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)


def solve_stack(ctx: SolverContext) -> DiagramLayout:
    """Portrait composition: the result on top, layers beneath, x operators
    in the layer gaps; risers climb bottom to top (the derived edges)."""
    ch = ctx.ch
    spec = ctx.spec
    width = ch.width
    gap = _gap(ctx, ch.gap)
    cx = width / 2
    nodes: list[NodePlacement] = []
    hero_nch = ch.hero if spec.nodes[0].role is NodeRole.HERO else ch.node
    hero_w = solve_card_w(
        spec.nodes[0],
        hero_nch,
        ctx.cfg,
        ctx.mono_triggers,
        hero=spec.nodes[0].role is NodeRole.HERO,
        min_w=ch.card_min_w,
    )
    layer_w = max(
        solve_card_w(
            n, ch.node, ctx.cfg, ctx.mono_triggers, min_w=ch.card_min_w, mark_w=mark_w_for(_style_of(ctx, n), n)
        )
        for n in spec.nodes[1:]
    )
    top_y = ch.header_h
    nodes.append(
        place_card(
            index=0,
            node=spec.nodes[0],
            x=cx - hero_w / 2,
            y=top_y,
            nch=hero_nch,
            cfg=ctx.cfg,
            accent_index=ctx.node_accents[0],
            mono_triggers=ctx.mono_triggers,
            muted_dash=_muted_dash(ctx),
            w_override=hero_w,
            glyph_builder=_card_art(ctx, 0, spec.nodes[0]),
        )
    )
    y = top_y + hero_nch.h + ch.src_gap
    for i, node in enumerate(spec.nodes[1:], start=1):
        nodes.append(
            place_card(
                index=i,
                node=node,
                x=cx - layer_w / 2,
                y=y,
                nch=ch.node,
                cfg=ctx.cfg,
                accent_index=ctx.node_accents[i],
                mono_triggers=ctx.mono_triggers,
                muted_dash=_muted_dash(ctx),
                w_override=layer_w,
                glyph_builder=_card_art(ctx, i, node),
            )
        )
        y += ch.node.h + gap
    height = int(y - gap + ch.footer_h)
    geos: list[EdgeGeo] = []
    for k, edge in enumerate(ctx.edges):
        a, b = nodes[edge.source].box, nodes[edge.target].box  # a below, b above (rising)
        y1, y2 = a.y, b.y + b.h
        x1, py1, x2, py2 = lane_endpoints(cx, y1, cx, y2, ctx.lanes[k], ctx.lane_offsets[k])
        geos.append(EdgeGeo(index=k, d=line_d(x1, py1, x2, py2), sx=x1, sy=py1, tx=x2, ty=py2, length=abs(y2 - y1)))
    # The operator SLOT is chassis geometry; its content is preset data
    # (G9) — no token, no rail.
    operators = (
        tuple(
            DiagramText(
                x=cx + ch.op_dx,
                y=(nodes[i].box.y + nodes[i].box.h + nodes[i + 1].box.y) / 2 + ch.op_dy,
                text=spec.operator,
                cls="op",
            )
            for i in range(1, len(nodes) - 1)
        )
        if spec.operator
        else ()
    )
    return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos, operators=operators)


def solve_comparison(ctx: SolverContext) -> DiagramLayout:
    """The before/after pair: muted left, hero right, one connector whose
    single particle carries the upgrade narrative."""
    ch = ctx.ch
    spec = ctx.spec
    width, height = ch.width, ch.height or 240
    cy = _band_center(ctx, height)
    left, right = spec.nodes[0], spec.nodes[1]
    pair_w = max(
        solve_card_w(
            left,
            ch.node,
            ctx.cfg,
            ctx.mono_triggers,
            min_w=ch.card_min_w,
            mark_w=mark_w_for(_style_of(ctx, left), left),
        ),
        solve_card_w(
            right,
            ch.hero,
            ctx.cfg,
            ctx.mono_triggers,
            hero=right.role is NodeRole.HERO,
            min_w=ch.card_min_w,
            mark_w=mark_w_for(_style_of(ctx, right), right),
        ),
    )
    nodes = [
        place_card(
            index=0,
            node=left,
            x=ch.margin_x,
            y=cy - ch.node.h / 2,
            nch=ch.node,
            cfg=ctx.cfg,
            accent_index=ctx.node_accents[0],
            mono_triggers=ctx.mono_triggers,
            muted_dash=_muted_dash(ctx),
            w_override=pair_w,
            glyph_builder=_card_art(ctx, 0, left),
        ),
        place_card(
            index=1,
            node=right,
            x=width - ch.margin_x - pair_w,
            y=cy - ch.hero.h / 2,
            nch=ch.hero if right.role is NodeRole.HERO else ch.node,
            cfg=ctx.cfg,
            accent_index=ctx.node_accents[1],
            mono_triggers=ctx.mono_triggers,
            muted_dash=_muted_dash(ctx),
            w_override=pair_w,
            glyph_builder=_card_art(ctx, 1, right),
        ),
    ]
    geos: list[EdgeGeo] = []
    for k, edge in enumerate(ctx.edges):
        a, b = nodes[edge.source].box, nodes[edge.target].box
        forward = b.x > a.x
        sx = a.x + a.w if forward else a.x
        tx = b.x if forward else b.x + b.w
        x1, y1, x2, y2 = lane_endpoints(sx, cy, tx, cy, ctx.lanes[k], ctx.lane_offsets[k])
        geos.append(
            EdgeGeo(index=k, d=line_d(x1, y1, x2, y2), sx=x1, sy=y1, tx=x2, ty=y2, length=line_len(x1, y1, x2, y2))
        )
    return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)


def solve_tree(ctx: SolverContext) -> DiagramLayout:
    """Banner star (depth 1): root top-center, leaves share a baseline;
    the center leaf takes a straight drop, outer leaves mirrored verticals.
    Leaf width solves the canvas — the one width-adaptive banner."""
    ch = ctx.ch
    spec = ctx.spec
    k = len(spec.nodes) - 1
    gap = _gap(ctx, ch.gap)
    leaf_w = (ch.width - 2 * ch.margin_x - (k - 1) * gap) / k
    leaf_w = max(ch.leaf_min_w, min(ch.leaf_max_w, leaf_w))
    width = int(2 * ch.margin_x + k * leaf_w + (k - 1) * gap)
    height = ch.height or 320
    root_nch = ch.hero if spec.nodes[0].role is NodeRole.HERO else ch.node
    root_cx = width / 2
    root_y = ch.header_h
    leaf_y = ch.pitch  # the leaves' shared top edge (specimen 200)
    nodes = [
        place_card(
            index=0,
            node=spec.nodes[0],
            x=root_cx - root_nch.w / 2,
            y=root_y,
            nch=root_nch,
            cfg=ctx.cfg,
            accent_index=ctx.node_accents[0],
            mono_triggers=ctx.mono_triggers,
            muted_dash=_muted_dash(ctx),
            glyph_builder=_card_art(ctx, 0, spec.nodes[0]),
        )
    ]
    for i, node in enumerate(spec.nodes[1:], start=1):
        x = ch.margin_x + (i - 1) * (leaf_w + gap)
        nodes.append(
            place_card(
                index=i,
                node=node,
                x=x,
                y=leaf_y,
                nch=ch.node,
                cfg=ctx.cfg,
                accent_index=ctx.node_accents[i],
                mono_triggers=ctx.mono_triggers,
                muted_dash=_muted_dash(ctx),
                glyph_builder=_card_art(ctx, i, node),
                w_override=leaf_w,
            )
        )
    root_bottom = root_y + root_nch.h
    geos: list[EdgeGeo] = []
    for j, edge in enumerate(ctx.edges):
        leaf = nodes[edge.target].box
        lcx = leaf.x + leaf.w / 2
        if abs(lcx - root_cx) < 1.0:
            d = line_d(root_cx, root_bottom, lcx, leaf.y)
            length = leaf.y - root_bottom
        else:
            d = s_curve_v(root_cx, root_bottom, lcx, leaf.y)
            length = s_curve_v_len(root_cx, root_bottom, lcx, leaf.y)
        geos.append(EdgeGeo(index=j, d=d, sx=root_cx, sy=root_bottom, tx=lcx, ty=leaf.y, length=length))
    return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)


register_solvers(
    {
        "pipeline": solve_pipeline,
        "stack": solve_stack,
        "comparison": solve_comparison,
        "tree": solve_tree,
    }
)
