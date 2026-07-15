"""Straight-family solvers: pipeline, stack, comparison, tree (banner).

Constants come from the topology chassis (specimen-extracted); formulas
generalize the hand-crafted specimens to any in-cap N. Rule over handcraft:
where a specimen's hand placement deviates a few px from the closed form
(band centering, riser insets), the form wins — presets stay within
tolerance of their specimens.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from hyperweave.compose.diagram.chrome import apply_health_dot, place_node, style_of
from hyperweave.compose.diagram.motion import lane_endpoints
from hyperweave.compose.diagram.paths import (
    bisect_clearance_depth,
    cubic_len,
    fmt,
    line_d,
    line_len,
)
from hyperweave.compose.diagram.records import (
    DiagramLayout,
    NodePlacement,
    OperatorMark,
)
from hyperweave.compose.diagram.route import orthogonal_d
from hyperweave.compose.diagram.sizing import (
    CHIP_STUB_MIN,
    chip_run_min,
    hero_height_floor,
    node_anatomy_of,
    solve_node_box,
)
from hyperweave.compose.diagram.solver import finish_layout, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
from hyperweave.compose.matrix.cells import measure_voice
from hyperweave.core.diagram import DiagramNode, NodeRole, NodeStyle

if TYPE_CHECKING:
    from hyperweave.compose.spatial_records import RectSpec
    from hyperweave.core.diagram import ResolvedEdge


def _gap(ctx: SolverContext, base: float) -> float:
    if not ctx.shrink:
        return base
    return base * float((ctx.engine.get("caps") or {}).get("shrink_factor", 0.85))


def _chip_run_min(ctx: SolverContext, *, vertical: bool = False) -> float:
    """Chip-run floor for this solver's edges (``sizing.chip_run_min`` at the
    generic ``CHIP_STUB_MIN`` floor — this family's runs carry no marker at
    the chip's own local terminus, so the bare stub is the whole law)."""
    return chip_run_min(ctx.edges, ctx.cfg, stub=CHIP_STUB_MIN, vertical=vertical)


def _band_center(ctx: SolverContext, height: float) -> float:
    ch = ctx.ch
    return ch.header_h + (height - ch.header_h - ch.footer_h) / 2


def _pipeline_box(ctx: SolverContext, node: DiagramNode, i: int, *, min_w: float = 0.0) -> tuple[float, float]:
    """A pipeline stage's natural (w, h) — the seam's own hero/chassis/style
    dispatch (``i == hero_idx`` matches ``node.role is NodeRole.HERO`` for
    every pipeline stage, so the seam's role-derived hero is byte-identical
    to the caller's former ``i == hero_idx`` ternary). Glyph-circle stays the
    all-or-nothing ``circle_mode`` special case above this function — not
    dispatched here.

    Width solves snug (the snug-width ruling): the
    pipeline's own width comes from a proportional content-unit shared with
    every stage (below), never a dominance-over-siblings floor — passing
    a dominance floor would be a no-op here
    anyway (undeclared, it resolves to the same ``nch.w`` this already
    reads). Height DOES need the ``hero_declared`` law explicitly: omitting
    ``h_floor`` let an UNCITED hero float on the paradigm's topology-default
    height (``h_floor=None`` -> ``nch.h`` inside ``solve_card_box``) —
    every uncited pipeline hero inherited a floor it never earned."""
    is_hero = node.role is NodeRole.HERO
    h_floor = hero_height_floor(ctx.ch) if is_hero else ctx.ch.node.h
    w, h, _ = solve_node_box(ctx, node, i, min_w=min_w, h_floor=h_floor)
    return w, h


def _place_pipeline(
    ctx: SolverContext, i: int, node: DiagramNode, x: float, cy: float, w: float, h: float
) -> NodePlacement:
    """Dispatch a pipeline stage to its resolved anatomy at baseline center
    ``cy``: a pill centers on (x + w/2, cy); a card/card+glyph keeps the
    existing top-left ``x`` EXACTLY (the ``x=`` escape hatch — ``cx - w/2``
    would round differently than the original's stored ``x`` in some cases,
    a real byte-identity break the seam-conversion harness caught)."""
    return place_node(ctx, node, i, x + w / 2, cy, w=w, h=h, x=x)


def _pipeline_skip_geo(
    ctx: SolverContext, k: int, ab: RectSpec, bb: RectSpec, all_boxes: list[RectSpec], *, over: bool
) -> EdgeGeo:
    """A pipeline edge that SKIPS past its neighbors — a soft symmetric sweep
    from the source's face to the target's face that clears every card between.

    A BACKWARD return dips UNDER (artifact-roundtrip's transform -> artifact'
    loop); a FORWARD bypass bows OVER (http-request's 304 cache path jumping the
    engine) so the two directions never share a channel and a straight run never
    spears the card it skips. The bow rides the SAME face on both ends (both
    undersides / both tops), a flat-bottom (or flat-top) cubic — unlike the
    state-machine back-edge's asymmetric hook. Its level starts ``return_depth``
    past the crossed cards' near edge and bisect-extends (G7, shared with
    ``graph.py``'s back-edge) until it clears every crossed card."""
    ch = ctx.ch
    if over:
        sx, sy = ab.x + ab.w / 2, ab.y
        tx, ty = bb.x + bb.w / 2, bb.y - 2.0
    else:
        sx, sy = ab.x + ab.w / 2, ab.y + ab.h
        tx, ty = bb.x + bb.w / 2, bb.y + bb.h + 2.0
    # Controls pull INTO the span (toward the crossed cards) whichever way the
    # skip runs, so the sweep stays symmetric — the inset sign follows the run.
    run_dir = 1.0 if tx >= sx else -1.0
    c1x, c2x = sx + ch.return_inset * run_dir, tx - ch.return_inset * run_dir
    lo_x, hi_x = min(c1x, sx, tx, c2x), max(c1x, sx, tx, c2x)
    crossed = [box for box in all_boxes if box is not ab and box is not bb and box.x < hi_x and box.x + box.w > lo_x]
    if over:
        base = min((box.y for box in crossed), default=min(sy, ty)) - ch.return_depth
    else:
        base = max((box.y + box.h for box in crossed), default=max(sy, ty)) + ch.return_depth
    clearance = float(ctx.engine.get("min_clearance", 18))

    def points(extra: float) -> list[tuple[float, float]]:
        lvl = base - extra if over else base + extra
        pts: list[tuple[float, float]] = []
        for t_i in range(1, 48):
            t = t_i / 48.0
            v = 1.0 - t
            pts.append(
                (
                    v**3 * sx + 3 * v**2 * t * c1x + 3 * v * t**2 * c2x + t**3 * tx,
                    v**3 * sy + 3 * v**2 * t * lvl + 3 * v * t**2 * lvl + t**3 * ty,
                )
            )
        return pts

    extra, _reach = bisect_clearance_depth(points, crossed, clearance)
    lvl = base - extra if over else base + extra
    d = f"M {fmt(sx)},{fmt(sy)} C {fmt(c1x)},{fmt(lvl)} {fmt(c2x)},{fmt(lvl)} {fmt(tx)},{fmt(ty)}"
    length = cubic_len(sx, sy, c1x, lvl, c2x, lvl, tx, ty)
    return EdgeGeo(index=k, d=d, sx=sx, sy=sy, tx=tx, ty=ty, length=length)


def _pipeline_edge_geo(
    ctx: SolverContext, k: int, edge: ResolvedEdge, nodes: list[NodePlacement], cy: float
) -> EdgeGeo:
    """One pipeline edge: the ordinary straight run between adjacent stages
    (forward, or a reciprocal pair's backward lane — ``ctx.lanes`` nonzero),
    or — a return that SKIPS backward past its neighbors — the under-sweep
    above. Only a genuine skip (node-index distance >= 2) with no reciprocal
    partner triggers the sweep; a lone reversed-adjacent edge stays a line."""
    ab, bb = nodes[edge.source].box, nodes[edge.target].box
    forward = bb.x > ab.x
    # A skip past a neighbor (index distance >= 2, no reciprocal lane) sweeps
    # AROUND the cards between instead of spearing them: a backward return dips
    # under, a forward bypass bows over — so a cache path never overlaps the
    # main-flow arrival on the target's mouth (http-request's 304).
    is_skip = ctx.lanes[k] == 0 and abs(edge.source - edge.target) >= 2
    if is_skip:
        return _pipeline_skip_geo(ctx, k, ab, bb, [n.box for n in nodes], over=forward)
    sx = ab.x + ab.w if forward else ab.x
    tx = bb.x if forward else bb.x + bb.w
    x1, y1, x2, y2 = lane_endpoints(sx, cy, tx, cy, ctx.lanes[k], ctx.lane_offsets[k])
    return EdgeGeo(index=k, d=line_d(x1, y1, x2, y2), sx=x1, sy=y1, tx=x2, ty=y2, length=line_len(x1, y1, x2, y2))


def solve_pipeline(ctx: SolverContext) -> DiagramLayout:
    """N stages on one baseline, equal gaps; the hero takes hero_ratio x the
    solved unit width. Glyph-circle style spreads circle centers evenly
    instead when EVERY node is glyph-circle (the canon relay anatomy, an
    all-or-nothing switch); a pill or card+glyph style is a per-node choice
    within the ordinary card baseline (``_place_pipeline`` dispatches)."""
    ch = ctx.ch
    spec = ctx.spec
    n = len(spec.nodes)
    width, height = ch.width, ch.height or 216
    gap = _gap(ctx, ch.gap)
    # A forward micro-label floats ABOVE its run with a +8 overhang allowance
    # (annotate.py) — the run itself must already be at least as wide as the
    # label, or it pre-wraps regardless of the overhang (artifact-roundtrip's
    # "publish --target"). A chip label rides ON the wire, so its run must
    # hold the chip PLUS a visible stub each side (_chip_run_min).
    label_gap_min = max(
        (
            measure_voice(e.label, ctx.cfg.edge_label_voice) - 8.0
            for e in ctx.edges
            if e.label and e.label_style != "chip"
        ),
        default=0.0,
    )
    gap = max(gap, label_gap_min, _chip_run_min(ctx))
    cy = _band_center(ctx, height)
    circle_mode = all(style_of(node, ctx.spec, ctx.ch) == NodeStyle.GLYPH_CIRCLE.value for node in spec.nodes)
    nodes: list[NodePlacement] = []
    geos: list[EdgeGeo] = []
    if circle_mode:
        r = ch.circle_r
        span = width - 2 * ch.margin_x - 2 * r
        for i, node in enumerate(spec.nodes):
            cx = ch.margin_x + r + (span * i / (n - 1) if n > 1 else span / 2)
            # ``solve_node_box`` picks the same hero/default radius the
            # original ``rad = hr if node.role is NodeRole.HERO else r``
            # ternary did; ``place_node``'s ``hub`` default (``is_hero`` when
            # unset) likewise matches the original's explicit
            # ``hub=node.role is NodeRole.HERO``.
            w, h, _ = solve_node_box(ctx, node, i)
            nodes.append(place_node(ctx, node, i, cx, cy, w=w, h=h))
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
    # floor, and the canvas slack (or growth) goes to the wire. The stacked
    # HEAD anatomy takes the same content-width placement (rag-pipeline:
    # portrait stages at their own widths, four equal specimen runs) — the
    # proportional split below is the landscape-card law only.
    wire_major = ch.channel_run_min > 0 and len(ctx.lanes) > 0 and all(lane != 0 for lane in ctx.lanes)
    if wire_major or node_anatomy_of(ctx.spec, ch) == "head":
        boxes = [_pipeline_box(ctx, node, i) for i, node in enumerate(spec.nodes)]
        widths = [w for w, _ in boxes]
        # One baseline: TEXT cards share a height; a CONTAINER (sec 12.1
        # embed) keeps its own solved box, centered on the row midline —
        # its bulk must never inflate its siblings.
        text_hs = [h for (_, h), node in zip(boxes, spec.nodes, strict=True) if node.embed is None]
        shared_h = max(text_hs) if text_hs else ch.node.h
        heights = [h if node.embed is not None else shared_h for (_, h), node in zip(boxes, spec.nodes, strict=True)]
        run_floor = ch.channel_run_min if wire_major else _gap(ctx, ch.gap)
        run = max(run_floor, _chip_run_min(ctx), (width - 2 * ch.margin_x - sum(widths)) / (n - 1))
        width = int(max(width, 2 * ch.margin_x + sum(widths) + (n - 1) * run))
        x = ch.margin_x
        for i, node in enumerate(spec.nodes):
            nodes.append(_place_pipeline(ctx, i, node, x, cy, widths[i], heights[i]))
            x += widths[i] + run
        for k, edge in enumerate(ctx.edges):
            geos.append(_pipeline_edge_geo(ctx, k, edge, nodes, cy))
        return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)
    # Cards size to their CONTENT. Solve each card's content width, back out the
    # unit it implies (the hero divides by its ratio), take the max (aligned
    # columns, like fan.py), and DERIVE the canvas from it — the content-sizing
    # the dag/state-machine use. The old model divided a fixed chassis width by
    # N, stretching a short/narrow pipeline's cards to fill a canvas sized for a
    # bigger diagram; the canvas is a derived quantity now, not a floor.
    content_ws = [_pipeline_box(ctx, node, i)[0] for i, node in enumerate(spec.nodes)]
    divisor = ((n - 1) + ch.hero_ratio) if hero_idx is not None else float(n)
    # A container's inner canvas is never a unit vote — its slot grows past
    # the unit at the growth guard below; letting it vote inflated every
    # sibling to the nested artifact's width (hero-ratio-divided: the 384px
    # platform container made both its 150px siblings render at 326.8).
    content_unit = max(
        (cw / ch.hero_ratio if i == hero_idx else cw for i, cw in enumerate(content_ws) if spec.nodes[i].embed is None),
        default=float(ch.card_min_w),
    )
    # Cards size to their CONTENT (the content-max aggregate, mirroring fan.py's
    # aligned columns), and the canvas is DERIVED from that unit — NOT a fixed
    # chassis width divided by N, which stretched a short/narrow pipeline's cards
    # to fill a canvas sized for a bigger diagram (the over-wide bug: read-side's
    # 3 cards padded ~76px each). Snug-width ruling 2026-07-14: ``card_min_w``
    # no longer floors the unit — the pin inflated every stage past its ink
    # (roundtrip's 228 over a 194 content unit, the last standing pin-floor);
    # the row unit is the widest stage's own solve.
    unit = content_unit
    width = int(2 * ch.margin_x + (n - 1) * gap + unit * divisor)
    # Widths come from the proportional split (now content-cleared above), but
    # each card's HEIGHT solves against its own width; the baseline shares the
    # max so a wrapped desc grows the row together. Byte-identical when descs fit.
    widths = [unit * ch.hero_ratio if i == hero_idx else unit for i in range(n)]
    # A container (sec 12.1) must HOLD its inner canvas: its slot grows past
    # the proportional unit rather than squeezing the embed.
    widths = [
        max(w, node.embed_dims[0] + 2 * ch.node.pad_x) if node.embed_dims else w
        for w, node in zip(widths, spec.nodes, strict=True)
    ]
    solved_hs = [_pipeline_box(ctx, node, i, min_w=widths[i])[1] for i, node in enumerate(spec.nodes)]
    text_hs2 = [h for h, node in zip(solved_hs, spec.nodes, strict=True) if node.embed is None]
    shared_h2 = max(text_hs2) if text_hs2 else ch.node.h
    heights2 = [h if node.embed is not None else shared_h2 for h, node in zip(solved_hs, spec.nodes, strict=True)]
    x = ch.margin_x
    for i, node in enumerate(spec.nodes):
        w = widths[i]
        nodes.append(_place_pipeline(ctx, i, node, x, cy, w, heights2[i]))
        x += w + gap
    for k, edge in enumerate(ctx.edges):
        geos.append(_pipeline_edge_geo(ctx, k, edge, nodes, cy))
    return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)


def _operator_mark(cx: float, cy: float, r: float, cross: float) -> OperatorMark:
    """A quiet ring + cross (stack): the ring rides the card surface,
    the cross the muted-connector tone — drawn geometry, never a floating
    character glyph."""
    d = (
        f"M {fmt(cx - cross)},{fmt(cy - cross)} L {fmt(cx + cross)},{fmt(cy + cross)} "
        f"M {fmt(cx + cross)},{fmt(cy - cross)} L {fmt(cx - cross)},{fmt(cy + cross)}"
    )
    return OperatorMark(cx=cx, cy=cy, r=r, cross_d=d)


def solve_stack(ctx: SolverContext) -> DiagramLayout:
    """Landscape composition (stack): the hero crown top-center,
    content-sized layers in a column beneath it, gray ring+cross operators
    between consecutive layers; the one accent riser (the derived edge into
    the hero, always a sink) climbs from the topmost layer into the crown."""
    ch = ctx.ch
    spec = ctx.spec
    width = ch.width
    gap = _gap(ctx, ch.gap)
    cx = width / 2
    nodes: list[NodePlacement] = []
    # Layers role-derive like every other card (seam-conversion mismatch #3,
    # FIXED: a declared ``role: hero`` on a layer now measures with the same
    # hero chassis/voice place_card renders it with — box and text agree).
    layer_boxes = [solve_node_box(ctx, n, i) for i, n in enumerate(spec.nodes[1:], start=1)]
    layer_w = max(w for w, _, _ in layer_boxes)
    # The crown floors at an EXPLICIT hero.w/.h citation, else the layer
    # column's dominance (width) and pure content-solve (height) — the
    # hero_declared law fan.py/hub.py/graph.py already read (the prior
    # unconditional floor let an uncited crown inherit the topology's
    # default hero.h regardless of whether ITS OWN preset earned it).
    hero_w, hero_h, _ = solve_node_box(
        ctx,
        spec.nodes[0],
        0,
        h_floor=hero_height_floor(ch),
    )
    # Aligned column shares one height across TEXT layers; a container
    # layer (sec 12.1) keeps its own solved box.
    text_layer_hs = [h for (_, h, _), node in zip(layer_boxes, spec.nodes[1:], strict=True) if node.embed is None]
    layer_h = max(text_layer_hs) if text_layer_hs else ch.node.h
    top_y = ch.header_h
    # ``y=top_y`` exact (the original's literal top, never center-derived).
    nodes.append(place_node(ctx, spec.nodes[0], 0, cx, top_y + hero_h / 2, w=hero_w, h=hero_h, y=top_y))
    # The riser between crown and top layer must hold its compose chip plus
    # visible stubs (the vertical chip-run law).
    y = top_y + hero_h + max(ch.src_gap, _chip_run_min(ctx, vertical=True))
    for i, node in enumerate(spec.nodes[1:], start=1):
        own_h = layer_boxes[i - 1][1] if node.embed is not None else layer_h
        nodes.append(place_node(ctx, node, i, cx, y + own_h / 2, w=layer_w, h=own_h, y=y))
        y += own_h + gap
    height = int(y - gap + ch.footer_h)
    geos: list[EdgeGeo] = []
    for k, edge in enumerate(ctx.edges):
        a, b = nodes[edge.source].box, nodes[edge.target].box  # a below, b above (rising)
        y1, y2 = a.y, b.y + b.h
        x1, py1, x2, py2 = lane_endpoints(cx, y1, cx, y2, ctx.lanes[k], ctx.lane_offsets[k])
        geos.append(EdgeGeo(index=k, d=line_d(x1, py1, x2, py2), sx=x1, sy=py1, tx=x2, ty=py2, length=abs(y2 - y1)))
    # The operator SLOT is chassis geometry (ring radius + cross span); its
    # PRESENCE is preset data (G9) — spec.operator gates both the ring+cross
    # marks between consecutive layers AND the LAYERS/COMPOSITE zone headers
    # (the multiply ladder and the zone labels are the same "this is a
    # composition formula" claim; a plain chain like request-descent carries
    # neither).
    operators = (
        tuple(
            _operator_mark(cx, (nodes[i].box.y + nodes[i].box.h + nodes[i + 1].box.y) / 2, ch.op_r, ch.op_cross)
            for i in range(1, len(nodes) - 1)
        )
        if spec.operator
        else ()
    )
    lane_bands = ()  # stack band headers ride the solver zone law (preset zones data)
    return finish_layout(
        ctx, width=width, height=height, nodes_paint=nodes, geos=geos, operators=operators, lane_bands=lane_bands
    )


def solve_comparison(ctx: SolverContext) -> DiagramLayout:
    """The before/after pair: muted left, hero right, one connector whose
    single particle carries the upgrade narrative."""
    ch = ctx.ch
    spec = ctx.spec
    width, height = ch.width, ch.height or 240
    cy = _band_center(ctx, height)
    left, right = spec.nodes[0], spec.nodes[1]
    # Left is pinned to the plain node chassis (never hero) — comparison-left
    # grammar (the muted before never wears the crown).
    left_box = solve_node_box(ctx, left, 0, hero=False)
    # Right's box now role-derives its chassis exactly like its placement does
    # (seam-conversion mismatch #4, FIXED: measure and render use one chassis).
    # G3 dominance law: an undeclared hero floors at its sibling's ALREADY-
    # solved width/height (left_box, computed above) — never an uncited
    # chassis archetype (twin-faces' "baked face" content-solved to a
    # fraction of the paradigm's 380x160 before the muted sibling's own
    # width was ever consulted). An explicit preset citation of chassis.hero
    # still wins outright for HEIGHT (hero_height_floor reads
    # ch.hero_declared).
    right_box = solve_node_box(
        ctx,
        right,
        1,
        h_floor=hero_height_floor(ch),
    )
    # The pair shares a box (G3 aligned): one width, one height, so before/after
    # read as siblings even when one desc wraps taller. Byte-identical when the
    # descs fit (solved height == the left/hero chassis h they replaced).
    pair_w = max(left_box[0], right_box[0])
    pair_h = max(left_box[1], right_box[1])
    # Edge-run law (2026-07-14): the citation is the FACE-TO-FACE run, not
    # positions — the hand pair (380 panels at x=100/700) runs 220 between
    # faces, which the chassis constants derive exactly below. The canvas
    # DERIVES from cards + run; the retired fixed frame held the old
    # positions while snug cards shrank, stretching the run +55%.
    design_gap = ch.width - 2 * ch.margin_x - 2 * max(ch.node.w, ch.hero.w)
    run = max(48.0, design_gap, _chip_run_min(ctx))
    width = math.ceil(2 * ch.margin_x + 2 * pair_w + run)
    # The pair shares ONE content-left inset (comparison: muted glyph
    # and hero glyph sit the same distance inside their cards) — the group
    # includes BOTH members now that heroes are start-anchored group content.
    nodes = [
        # Left pinned non-hero (matches the box solve above); ``x=ch.margin_x``
        # exact (the original's literal left edge, never center-derived).
        place_node(
            ctx,
            left,
            0,
            ch.margin_x + pair_w / 2,
            cy,
            w=pair_w,
            h=pair_h,
            hero=False,
            x=ch.margin_x,
        ),
        # Right's PLACEMENT chassis is role-derived (``ch.hero if role is
        # HERO else ch.node`` in the original) — genuinely different from
        # the pinned-hero BOX solve above; auto-derive matches it exactly,
        # so no override here. ``x=`` pinned exact (literal right edge).
        place_node(
            ctx,
            right,
            1,
            width - ch.margin_x - pair_w / 2,
            cy,
            w=pair_w,
            h=pair_h,
            x=width - ch.margin_x - pair_w,
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


def _tree_children(ctx: SolverContext) -> dict[int, list[int]]:
    """Parent -> ordered children (spec/edge declaration order — ORDER IS
    STRUCTURE): the derived depth-1 star or the explicit multi-level edges,
    already canonicalized to ``ctx.edges`` by ``resolved_edges``."""
    children: dict[int, list[int]] = {i: [] for i in range(len(ctx.spec.nodes))}
    for e in ctx.edges:
        children[e.source].append(e.target)
    return children


def _tree_leaves(children: dict[int, list[int]], i: int) -> int:
    """Leaf count of the subtree rooted at ``i`` (1 for a childless node) —
    the proportional-sector weight (tree-radial's ``leaves()``, Cartesian)."""
    kids = children[i]
    return 1 if not kids else sum(_tree_leaves(children, k) for k in kids)


def _tree_depths(children: dict[int, list[int]]) -> tuple[dict[int, int], dict[int, list[int]]]:
    """DFS from the root: per-node depth, and per-depth member order. DFS
    (not BFS) so a depth bucket lists each parent's children together,
    left to right, whatever depth a branch happens to terminate at (a
    dependency tree's leaf can sit shallower than its sibling's)."""
    depth_of: dict[int, int] = {0: 0}
    by_depth: dict[int, list[int]] = {0: [0]}

    def visit(i: int) -> None:
        for c in children[i]:
            depth_of[c] = depth_of[i] + 1
            by_depth.setdefault(depth_of[c], []).append(c)
            visit(c)

    visit(0)
    return depth_of, by_depth


def solve_tree(ctx: SolverContext) -> DiagramLayout:
    """Depth-weighted hierarchy (tree/dep-audit): root top-center; each
    level's members split their parent's horizontal span proportional to
    subtree leaf-count (tree-radial's sector allocation, Cartesian instead of
    angular) — a childless node renders at its own allotted midpoint,
    whatever depth it terminates at, so an irregular tree (a dependency's
    direct dep with no transitive child) never collides with a deeper
    sibling. Root -> children is the depth-1 derived star (any topology's
    common case); explicit edges declare depth 2, the taxonomy/dependency-
    audit ceiling (specimen-driven — CLAUDE.md Rule 1: no unvalidated depth).
    Every edge draws an orthogonal drop-span-drop BUS (root/parent stub down,
    span across, stub down to the child) with sharp elbows — a hierarchy
    reads its direction from vertical position, never an arrowhead."""
    ch = ctx.ch
    spec = ctx.spec
    n = len(spec.nodes)
    children = _tree_children(ctx)
    depth_of, by_depth = _tree_depths(children)
    max_depth = max(depth_of.values())
    gap = _gap(ctx, ch.gap)
    margin = ch.margin_x

    # Per-row uniform card box (aligned width policy): the DEEPEST row uses
    # the smaller node2 floor, every shallower row uses node — content still
    # grows a card past its floor (dep-audit's transitive deps carry a
    # version desc and land at their direct-dep parents' height regardless of
    # the smaller floor; tree's desc-less leaves stay small).
    def _row_chassis_class(d: int) -> str:
        return "node2" if d == max_depth else ""

    row_w: dict[int, float] = {}
    row_h: dict[int, float] = {}
    for d in range(1, max_depth + 1):
        # Row members role-derive (mismatch #3, FIXED); ``chassis_class`` is
        # the one genuinely POSITIONAL chassis hint (depth-tier) a solver
        # still owns — a declared hero in a row measures hero, renders hero.
        boxes = [solve_node_box(ctx, spec.nodes[i], i, chassis_class=_row_chassis_class(d)) for i in by_depth[d]]
        row_w[d] = max(w for w, _, _ in boxes)
        row_h[d] = max(h for _, h, _ in boxes)

    # Canvas width: total leaf-slot count x a per-slot floor (the widest
    # row's solved width, leaf-bounds clamped) — the one width-adaptive
    # dimension, same law the depth-1 star always used, generalized to
    # however many leaf slots the tree's shape needs (a leaf slot is a
    # childless node's OWN allotment, whatever depth it sits at).
    total_leaves = _tree_leaves(children, 0)
    slot_w = max([*row_w.values()], default=ch.card_min_w)
    slot_w = max(ch.leaf_min_w, min(ch.leaf_max_w, slot_w))
    # Content-fit law: the chassis width spreads the root span only where the chassis
    # declares a fixed frame — otherwise a narrow tree hugs its leaf slots.
    width = int(max(ch.width if ch.width_floor else 0, 2 * margin + total_leaves * slot_w + (total_leaves - 1) * gap))

    # Root is role-derived hero — matches solve_node_box's own default. An
    # EXPLICIT hero.w/.h citation is a hard floor; undeclared, the root
    # floors at its immediate children's row width (dominance, row_w[1] —
    # the tree's closest analog to a fan/hub's ring siblings) and
    # content-solves height PURE — the hero_declared law fan.py/hub.py/
    # graph.py/stack already read. A non-hero root (role-derived False)
    # keeps the plain chassis floor, both params unused by that branch.
    is_root_hero = spec.nodes[0].role is NodeRole.HERO
    root_nch = ch.hero if is_root_hero else ch.node
    root_y = ch.header_h
    _root_w, root_h, _ = solve_node_box(
        ctx,
        spec.nodes[0],
        0,
        h_floor=hero_height_floor(ch) if is_root_hero else root_nch.h,
    )

    row_top: dict[int, float] = {}
    cursor = root_y + root_h
    for d in range(1, max_depth + 1):
        cursor += ch.row_gap
        row_top[d] = cursor
        cursor += row_h[d]
    height = int(cursor + ch.footer_h)

    placed: list[NodePlacement | None] = [None] * n

    def place_subtree(i: int, depth: int, x0: float, span: float) -> None:
        mid = x0 + span / 2
        if depth > 0:
            w, h = row_w[depth], row_h[depth]
            # ``y=row_top[depth]`` exact (the original's literal row top,
            # never center-derived) — ``x`` needs no escape: ``mid - w/2`` is
            # the SAME expression the original used to compute its own ``x``.
            placed[i] = apply_health_dot(
                ctx,
                spec.nodes[i],
                place_node(
                    ctx,
                    spec.nodes[i],
                    i,
                    mid,
                    row_top[depth] + h / 2,
                    w=w,
                    h=h,
                    chassis_class=_row_chassis_class(depth),
                    y=row_top[depth],
                ),
            )
        kids = children[i]
        if not kids:
            return
        total = sum(_tree_leaves(children, k) for k in kids)
        x = x0
        for kid in kids:
            kid_span = span * _tree_leaves(children, kid) / total
            place_subtree(kid, depth + 1, x, kid_span)
            x += kid_span

    place_subtree(0, 0, margin, width - 2 * margin)
    # No w_override in the original — the root's WIDTH is always the
    # chassis width (root_nch.w), never the content-solved ``_root_w``
    # (discarded above); only the HEIGHT is content-solved. Preserved
    # verbatim: ``place_node`` gets ``w=root_nch.w`` directly, not the
    # solve's own return value.
    # ``y=root_y`` exact (literal top); ``x`` needs no escape (``width/2 -
    # root_nch.w/2`` is the same expression the original used).
    placed[0] = apply_health_dot(
        ctx,
        spec.nodes[0],
        place_node(ctx, spec.nodes[0], 0, width / 2, root_y + root_h / 2, w=root_nch.w, h=root_h, y=root_y),
    )
    nodes: list[NodePlacement] = [p for p in placed if p is not None]
    assert len(nodes) == n, "every tree node must be placed exactly once"

    # Bus y per depth transition: the midpoint between the parent row's
    # bottom and the child row's top (tree/dep-audit: 238 == mid(168,
    # 308); 497 == mid(412,582)) — one shared trunk per level, emergent from
    # each edge independently drawing its own VHV leg through the SAME
    # midpoint (coincident stubs/spans overlay into what reads as one bus).
    bus_y: dict[int, float] = {}
    prev_bottom = root_y + root_h
    for d in range(1, max_depth + 1):
        bus_y[d] = (prev_bottom + row_top[d]) / 2
        prev_bottom = row_top[d] + row_h[d]

    geos: list[EdgeGeo] = []
    for j, edge in enumerate(ctx.edges):
        pb, cb = nodes[edge.source].box, nodes[edge.target].box
        sx, sy = pb.x + pb.w / 2, pb.y + pb.h
        tx, ty = cb.x + cb.w / 2, cb.y
        d_path, length, poly, tangent = orthogonal_d(
            sx, sy, tx, ty, mid=bus_y[depth_of[edge.target]], first_axis="v", r=0.0
        )
        geos.append(
            EdgeGeo(index=j, d=d_path, sx=sx, sy=sy, tx=tx, ty=ty, length=length, polyline=poly, end_tangent=tangent)
        )
    return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)


register_solvers(
    {
        "pipeline": solve_pipeline,
        "stack": solve_stack,
        "comparison": solve_comparison,
        "tree": solve_tree,
    }
)
