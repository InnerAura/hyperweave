"""Sequence solver: participant heads, lifelines, activation bars, ordered
messages — the auth-sequence anatomy.

The agent-era diagram — closed-form because lifelines are columns and
messages are ordered rows. Order rides one shared replay clock (wired in
``wire_motion``); direction and call/return ride the stroke (solid = call,
accent dash-drift = return — a meaning-bearing dasharray the track yields
to, P3 — EXCEPT for sequence returns, which deliberately supersede that
yield: the kit's responses drift home rather than sitting static). Terminal
arrows are the topology's D5 wire default (solid rails + drawn chevrons);
there is no ornament-free doctrine here — auth-sequence draws them.

Sequence-only chrome (the hero lifeline/activation tint, the left-margin
time axis, the top-right call/return mini-legend) is attached AFTER
``finish_layout`` returns, in ``_attach_sequence_furniture``: all three read
FINAL canvas coordinates, so building them post-solve avoids threading
sequence-only furniture through the universal region/recentering pipeline
every other topology also runs.
"""

from __future__ import annotations

import math
from dataclasses import replace

from hyperweave.compose.diagram.chrome import place_node, voice_for
from hyperweave.compose.diagram.paths import line_d
from hyperweave.compose.diagram.records import (
    DiagramLayout,
    DiagramText,
    NodePlacement,
    TimeAxis,
    WireLegendEntry,
)
from hyperweave.compose.diagram.route import marker_path
from hyperweave.compose.diagram.sizing import HEAD_GLYPH_SIZE, HEAD_PAD_X
from hyperweave.compose.diagram.solver import finish_layout, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
from hyperweave.compose.matrix.cells import measure_voice
from hyperweave.compose.spatial_records import LineSpec, RectSpec
from hyperweave.core.diagram import EdgeKind, NodeRole

# Call/return mini-legend geometry (chrome vocabulary — auth-sequence's top-
# right stubs): a 16px wire sample + its terminal, 8px gap, then the label.
_WIRE_LEGEND_STUB_W = 16.0
_WIRE_LEGEND_GAP = 8.0
_WIRE_LEGEND_ROW_PITCH = 20.0
# Time-axis furniture: a short vertical arrow centered on the trace's
# vertical midpoint, sitting inside the left margin gutter (never touching
# the first lifeline's card, which pins to the margin edge itself).
_TIME_AXIS_LEN = 40.0
_TIME_AXIS_X_FRAC = 0.32
_TIME_AXIS_LABEL_GAP = 8.0


def solve_sequence(ctx: SolverContext) -> DiagramLayout:
    ch = ctx.ch
    spec = ctx.spec
    k = len(spec.nodes)
    headers_y = ch.header_h
    hero_idx = next((i for i, node in enumerate(spec.nodes) if node.role is NodeRole.HERO), -1)
    # Solve every head's width FIRST, then derive lifeline positions from the
    # cumulative head widths: a long participant name widens its own COLUMN,
    # not just its head rect (the head-grow fix was incomplete — head_w never
    # reached the lifeline grid or the canvas, so a wide head overlapped its
    # neighbour or clipped the right margin). All-chassis-width heads
    # reproduce the old uniform grid exactly.
    head_ws: list[float] = []
    for node in spec.nodes:
        nch = ch.hero if node.role is NodeRole.HERO else ch.node
        voice = voice_for(ctx.cfg, "hname" if node.role is NodeRole.HERO else "name")
        head_ws.append(max(nch.w, math.ceil((measure_voice(node.label, voice) + 2 * HEAD_PAD_X) / 2) * 2))
    lifeline_x: list[float] = []
    for i in range(k):
        if i == 0:
            lifeline_x.append(ch.margin_x + head_ws[0] / 2)
        else:
            lifeline_x.append(lifeline_x[i - 1] + head_ws[i - 1] / 2 + ch.lifeline_gap + head_ws[i] / 2)
    width = math.ceil(lifeline_x[-1] + head_ws[-1] / 2 + ch.margin_x) if k else math.ceil(2 * ch.margin_x)
    nodes: list[NodePlacement] = []
    for i, node in enumerate(spec.nodes):
        # ``nch`` is role-derived (matches the seam's own default, so hero
        # need not be overridden); ``y=headers_y`` is the original's literal
        # top (never center-derived), so it takes the exact-position hatch.
        # A participant HEAD always carries its resolved glyph (brand or
        # kind) unconditionally — the compact stacked anatomy IS the
        # sequence default, never a caller-selected ``node_style``.
        nch = ch.hero if node.role is NodeRole.HERO else ch.node
        head_w = head_ws[i]
        nodes.append(
            place_node(
                ctx,
                node,
                i,
                lifeline_x[i],
                headers_y + nch.h / 2,
                w=head_w,
                h=nch.h,
                rx=nch.rx,
                anatomy="head",
                glyph_unconditional=True,
                glyph_size=HEAD_GLYPH_SIZE,
                y=headers_y,
                x=lifeline_x[i] - head_w / 2,
            )
        )
    # Heads share one row: lifelines drop from the taller of the two card
    # classes (both 64px in the chassis; the max guards a future re-skin
    # that diverges the hero's height).
    lifelines_top = headers_y + max(ch.node.h, ch.hero.h)
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
    sorted_touch = sorted(touch.items())
    activations = tuple(
        RectSpec(
            x=lifeline_x[i] - ch.act_w / 2,
            y=min(ys) - ch.act_pad_top,
            w=ch.act_w,
            h=(max(ys) + ch.act_pad_bottom) - (min(ys) - ch.act_pad_top),
            rx=2.0,
        )
        for i, ys in sorted_touch
    )
    hero_activation_index = next((pos for pos, (i, _ys) in enumerate(sorted_touch) if i == hero_idx), -1)
    return_dash = str(ctx.engine["track"]["return_dash"])
    geos: list[EdgeGeo] = []
    for j, (edge, y) in enumerate(zip(ctx.edges, msg_ys, strict=True)):
        sx = lifeline_x[edge.source]
        tx = lifeline_x[edge.target]
        rightward = tx > sx
        sx += ch.act_w / 2 if rightward else -ch.act_w / 2
        tx += -ch.act_w / 2 if rightward else ch.act_w / 2
        is_return = edge.kind is EdgeKind.RETURN
        geos.append(
            EdgeGeo(
                index=j,
                d=line_d(sx, y, tx, y),
                sx=sx,
                sy=y,
                tx=tx,
                ty=y,
                length=abs(tx - sx),
                semantic_dash=return_dash if is_return else "",
                # P3 override (auth-sequence): a return message drifts home
                # instead of resolving static — its own track value, never
                # the generic marching-ants texture.
                track_override="dash-drift" if is_return else "static",
                label_pos=((sx + tx) / 2, y - 7.0),
            )
        )
    layout = finish_layout(
        ctx,
        width=width,
        height=height,
        nodes_paint=nodes,
        geos=geos,
        lifelines=lifelines,
        activations=activations,
    )
    return _attach_sequence_furniture(
        layout, ctx, hero_lifeline_index=hero_idx, hero_activation_index=hero_activation_index
    )


def _attach_sequence_furniture(
    layout: DiagramLayout, ctx: SolverContext, *, hero_lifeline_index: int, hero_activation_index: int
) -> DiagramLayout:
    """Sequence-only chrome, built AFTER the shared solve so it reads FINAL
    canvas coordinates: the hero lifeline/activation flags (pure metadata —
    the template owns the styling), the left-margin time axis, and the
    top-right call/return mini-legend (masthead furniture; suppressed under
    bare chrome, matching every other masthead-anchored element). The legend
    can widen the canvas (``_build_wire_legend``'s second return value) — a
    RIGHT-side-only grow, never routed back through ``finish_layout``'s own
    region-stack: that stack CENTERS content, so a floor passed through it
    would waste half of any added width re-centering the lifelines instead
    of clearing the head column (measured: growing by exactly the legend's
    own need left it still short by half the growth)."""
    time_axis = _build_time_axis(layout, ctx) if layout.lifelines else None
    wire_legend, width = _build_wire_legend(layout, ctx) if ctx.chrome != "bare" else ((), layout.width)
    return replace(
        layout,
        width=width,
        hero_lifeline_index=hero_lifeline_index,
        hero_activation_index=hero_activation_index,
        time_axis=time_axis,
        wire_legend=wire_legend,
    )


def _build_time_axis(layout: DiagramLayout, ctx: SolverContext) -> TimeAxis:
    first = layout.lifelines[0]
    mid_y = (first.y1 + first.y2) / 2
    y0, y1 = mid_y - _TIME_AXIS_LEN / 2, mid_y + _TIME_AXIS_LEN / 2
    x = ctx.ch.margin_x * _TIME_AXIS_X_FRAC
    conn = ctx.engine["connector"]
    marker_d = marker_path(
        (x, y1), (0.0, 1.0), size=float(conn.get("marker_size", 8)), half=float(conn.get("marker_half", 0.45))
    )
    voice = voice_for(ctx.cfg, "key")
    label = DiagramText(
        x=x + _TIME_AXIS_LABEL_GAP,
        y=mid_y + voice.size * ctx.cfg.text_ascent_ratio / 2,
        text="time",
        cls="key",
    )
    return TimeAxis(stub_d=line_d(x, y0, x, y1), marker_d=marker_d, label=label)


def _build_wire_legend(layout: DiagramLayout, ctx: SolverContext) -> tuple[tuple[WireLegendEntry, ...], int]:
    """The call/return mini-legend, plus the canvas width it needs.

    Right-aligns on the canvas edge — UNLESS the rightmost participant head
    reaches far enough right that a plain right-alignment would crowd or
    overlap it (a narrow trace, or a long last-participant name): the legend
    then clears the head by ``legend_clearance`` instead, and the canvas
    grows to hold it (the fixed ``layout.width - m - block_w`` stamp
    collided with the rightmost card on two-lifeline traces, and even on
    auth-sequence itself once measured against the ACTUAL solved head box
    rather than assumed clear). Read the actual head positions from
    ``layout.nodes`` (final, post-solve coordinates) rather than re-deriving
    them — this runs after ``finish_layout``, which may have shifted every
    node from where ``solve_sequence`` first placed them."""
    if not any(e.kind is EdgeKind.RETURN for e in ctx.edges):
        return (), layout.width
    conn = ctx.engine["connector"]
    marker_size, marker_half = float(conn.get("marker_size", 8)), float(conn.get("marker_half", 0.45))
    voice = voice_for(ctx.cfg, "key")
    ar = ctx.cfg.text_ascent_ratio
    m = ctx.ch.margin_x
    mv = min(m, 24.0)
    specs = (("call", False), ("return", True))
    label_w = max(measure_voice(text, voice) for text, _accent in specs)
    block_w = _WIRE_LEGEND_STUB_W + _WIRE_LEGEND_GAP + label_w
    rightmost_head = max((n.box.x + n.box.w for n in layout.nodes), default=0.0)
    clearance = float((ctx.engine.get("sequence") or {}).get("legend_clearance", 40))
    left_x = max(layout.width - m - block_w, rightmost_head + clearance)
    width = max(layout.width, math.ceil(left_x + block_w + m))
    top_y = mv + 4.0
    rows: list[WireLegendEntry] = []
    for i, (text, accent) in enumerate(specs):
        stub_y = top_y + i * _WIRE_LEGEND_ROW_PITCH + _WIRE_LEGEND_ROW_PITCH / 2
        stub_x1 = left_x + _WIRE_LEGEND_STUB_W
        marker_d = marker_path((stub_x1, stub_y), (1.0, 0.0), size=marker_size, half=marker_half)
        label = DiagramText(x=stub_x1 + _WIRE_LEGEND_GAP, y=stub_y + voice.size * ar / 2, text=text, cls="key")
        rows.append(
            WireLegendEntry(
                stub_d=line_d(left_x, stub_y, stub_x1, stub_y),
                marker_d=marker_d,
                accent=accent,
                drift=accent,
                label=label,
            )
        )
    return tuple(rows), width


register_solvers({"sequence": solve_sequence})
