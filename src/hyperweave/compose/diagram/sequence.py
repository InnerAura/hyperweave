"""Sequence solver: lifelines, activation bars, ordered messages.

The agent-era diagram — closed-form because lifelines are columns and
messages are ordered rows. Order rides one shared replay clock (wired in
``wire_motion``); direction and call/return ride the stroke (solid = call,
dashed = return — a meaning-bearing dasharray the track yields to, P3).
No arrowheads, per the family's ornament-free doctrine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hyperweave.compose.diagram.chrome import glyph_slot_builder, mark_w_for, place_card, solve_card_w
from hyperweave.compose.diagram.paths import line_d
from hyperweave.compose.diagram.records import DiagramLayout, DiagramText, GlyphArt, NodePlacement
from hyperweave.compose.diagram.solver import finish_layout, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
from hyperweave.compose.spatial_records import LineSpec, RectSpec
from hyperweave.core.diagram import DiagramNode, EdgeKind, NodeRole, NodeStyle

if TYPE_CHECKING:
    from collections.abc import Callable


def _card_art(ctx: SolverContext, i: int, node: DiagramNode) -> Callable[[float, float], GlyphArt | None] | None:
    """card+glyph anatomy: the identity mark takes the dot slot."""
    if _seq_style(ctx, node) != NodeStyle.CARD_GLYPH.value or not node.glyph:
        return None
    return glyph_slot_builder(node.glyph, ctx.glyph_registry, ctx.glyph_selections[i])


def _seq_style(ctx: SolverContext, node: DiagramNode) -> str:
    if node.style is not None:
        return node.style.value
    if ctx.spec.node_style is not None:
        return ctx.spec.node_style.value
    return ctx.ch.node_style or NodeStyle.CARD.value


def solve_sequence(ctx: SolverContext) -> DiagramLayout:
    ch = ctx.ch
    spec = ctx.spec
    k = len(spec.nodes)
    width = int(2 * ch.margin_x + k * ch.node.w + (k - 1) * ch.lifeline_gap)
    lifeline_x = [ch.margin_x + ch.node.w / 2 + i * (ch.node.w + ch.lifeline_gap) for i in range(k)]
    headers_y = ch.header_h
    lifelines_top = headers_y + ch.node.h
    # Header row cohesion (G3 aligned policy): one content-solved width
    # over the lifeline headers; the centered group splits the slack.
    header_w = max(
        solve_card_w(
            node,
            ch.hero if node.role is NodeRole.HERO else ch.node,
            ctx.cfg,
            ctx.mono_triggers,
            hero=node.role is NodeRole.HERO,
            min_w=ch.card_min_w,
            mark_w=mark_w_for(_seq_style(ctx, node), node),
        )
        for node in spec.nodes
    )
    nodes: list[NodePlacement] = []
    for i, node in enumerate(spec.nodes):
        nch = ch.hero if node.role is NodeRole.HERO else ch.node
        nodes.append(
            place_card(
                index=i,
                node=node,
                x=lifeline_x[i] - header_w / 2,
                y=headers_y,
                nch=nch,
                cfg=ctx.cfg,
                accent_index=ctx.node_accents[i],
                mono_triggers=ctx.mono_triggers,
                muted_dash=str(ctx.engine["track"]["muted_dash"]),
                w_override=header_w,
                glyph_builder=_card_art(ctx, i, node),
            )
        )
    msg_ys = [lifelines_top + ch.first_msg_dy + i * ch.msg_pitch for i in range(len(ctx.edges))]
    lifeline_bottom = (msg_ys[-1] if msg_ys else lifelines_top) + ch.first_msg_dy
    height = int(lifeline_bottom + ch.footer_h)
    lifelines = tuple(LineSpec(x1=x, y1=lifelines_top, x2=x, y2=lifeline_bottom) for x in lifeline_x)
    # Activation bars: a lifeline is busy from its first message touch to
    # its last (uniform pads — the rule, not the specimen's hand-tuning).
    touch: dict[int, list[float]] = {}
    for e, y in zip(ctx.edges, msg_ys, strict=True):
        touch.setdefault(e.source, []).append(y)
        touch.setdefault(e.target, []).append(y)
    activations = tuple(
        RectSpec(
            x=lifeline_x[i] - ch.act_w / 2,
            y=min(ys) - ch.act_pad_top,
            w=ch.act_w,
            h=(max(ys) + ch.act_pad_bottom) - (min(ys) - ch.act_pad_top),
            rx=2.0,
        )
        for i, ys in sorted(touch.items())
    )
    return_dash = str(ctx.engine["track"]["return_dash"])
    geos: list[EdgeGeo] = []
    for j, (edge, y) in enumerate(zip(ctx.edges, msg_ys, strict=True)):
        sx = lifeline_x[edge.source]
        tx = lifeline_x[edge.target]
        rightward = tx > sx
        sx += ch.act_w / 2 if rightward else -ch.act_w / 2
        tx += -ch.act_w / 2 if rightward else ch.act_w / 2
        geos.append(
            EdgeGeo(
                index=j,
                d=line_d(sx, y, tx, y),
                sx=sx,
                sy=y,
                tx=tx,
                ty=y,
                length=abs(tx - sx),
                semantic_dash=return_dash if edge.kind is EdgeKind.RETURN else "",
                track_override="static",
                label_pos=((sx + tx) / 2, y - 7.0),
            )
        )
    legend = None
    if any(e.kind is EdgeKind.RETURN for e in ctx.edges):
        legend = DiagramText(
            x=ch.margin_x,
            y=height - ch.legend_dy,
            text="SOLID = CALL · DASHED = RETURN · ORDER = REPLAY CLOCK",
            cls="key",
        )
    return finish_layout(
        ctx,
        width=width,
        height=height,
        nodes_paint=nodes,
        geos=geos,
        lifelines=lifelines,
        activations=activations,
        legend=legend,
        header_width=float(width),
    )


register_solvers({"sequence": solve_sequence})
