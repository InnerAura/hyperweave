"""S-curve family solvers: fanout (horizontal, bilateral, upward) and
convergence. Every curve is a midpoint S — control points at the chord
midpoint, verified exact against all specimen connectors. Heights grow
with the dest/input count; widths are the banner contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from hyperweave.compose.diagram.anchors import side_anchor
from hyperweave.compose.diagram.chrome import place_node, style_of
from hyperweave.compose.diagram.motion import lane_endpoints
from hyperweave.compose.diagram.paths import s_curve_h, s_curve_h_len, s_curve_v, s_curve_v_len
from hyperweave.compose.diagram.sizing import (
    CHIP_STUB_MIN,
    chip_run_min,
    hero_height_floor,
    marker_reserved_stub,
    solve_node_box,
)
from hyperweave.compose.diagram.solver import finish_layout, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext, knot_collapse
from hyperweave.core.diagram import NodeRole, NodeStyle

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import DiagramLayout, NodePlacement
    from hyperweave.core.diagram import DiagramNode


def _member_widths(ctx: SolverContext, nodes: list[DiagramNode]) -> list[float]:
    """G3 width policy from the chassis: free content-solves each member
    (slack never exceeds the symmetric pads); aligned shares the max.
    Measurement is style- and role-derived (seam-conversion mismatch #6,
    FIXED): a glyph-circle member reserves its true diameter — spacing no
    longer assumes a full card slot around a small coin."""
    ch = ctx.ch
    widths = [solve_node_box(ctx, n, i)[0] for i, n in enumerate(nodes)]
    if ch.width_policy == "aligned":
        shared = max(widths)
        return [shared] * len(widths)
    return widths


def _member_boxes(ctx: SolverContext, nodes: list[DiagramNode]) -> tuple[list[float], list[float]]:
    """Content-solved widths AND heights for a member group (G3 extension).

    Free policy sizes each card; aligned shares the max width, then re-solves
    each height at that shared width and shares the max — so a row/column of
    cards stays rectangular even when one member's desc wraps taller.
    ``h == nch.h`` for content that already fits, so cards without a rich desc
    keep the chassis height and render byte-identically. Style/role-derived
    like ``_member_widths`` (mismatch #6, FIXED)."""
    ch = ctx.ch
    boxes = [solve_node_box(ctx, n, i) for i, n in enumerate(nodes)]
    widths = [w for w, _, _ in boxes]
    if ch.width_policy == "aligned":
        shared_w = max(widths)
        widths = [shared_w] * len(nodes)
        heights = [solve_node_box(ctx, n, i, min_w=shared_w)[1] for i, n in enumerate(nodes)]
        shared_h = max(heights)
        return widths, [shared_h] * len(nodes)
    return widths, [h for _, h, _ in boxes]


def _pitch(ctx: SolverContext) -> float:
    p = ctx.ch.pitch
    if ctx.shrink:
        p *= float((ctx.engine.get("caps") or {}).get("shrink_factor", 0.85))
    return p


def _place(
    ctx: SolverContext,
    i: int,
    node: DiagramNode,
    *,
    x: float,
    y: float,
    hero: bool | None = None,
    w_override: float = 0.0,
    h_override: float = 0.0,
) -> NodePlacement:
    """Card or glyph-circle per the style cascade; (x, y) is the card's
    top-left — circle placement converts to the equivalent center.
    ``h_override`` (0 = chassis height) carries the solved card height for
    content-sized cards; glyph-circles ignore it (their size is the radius —
    a member's aligned-policy width from ``_member_boxes``/``_member_widths``
    is likewise ignored for a circle member, matching the original split).
    Widths are SNUG (snug-width ruling): every card — crown included —
    content-solves; width citations bound growth as ceilings only."""
    ch = ctx.ch
    is_hero = (node.role is NodeRole.HERO) if hero is None else hero
    nch = ch.hero if is_hero else ch.node
    style = style_of(node, ctx.spec, ctx.ch)
    if style == NodeStyle.GLYPH_CIRCLE.value:
        r = ch.hero_circle_r if is_hero else ch.circle_r
        # Center within the caller's reserved slot (the solved 2r box when
        # the measurement fix is in play, else the chassis slot).
        slot_w = w_override or 2 * r
        slot_h = h_override or 2 * r
        return place_node(ctx, node, i, x + slot_w / 2, y + slot_h / 2, w=2 * r, h=2 * r, hero=is_hero)
    # Never-truncate, BOTH axes: an un-overridden card (the fan hub, the
    # convergence hero) content-solves its box through the one sizing seam —
    # a long name grows the width instead of ellipsizing (provider-fallback),
    # and a node carrying more pieces grows the height instead of dropping
    # them (convergence-arrivals' hero authored an in-card chip row that the
    # fixed 112 frame silently shed). Every card piece composes because the
    # box is solved for what the node CARRIES, never assumed from an
    # archetype it never cited.
    if w_override and h_override:
        w, h = w_override, h_override
    else:
        # Heights: a hero floors at an EXPLICIT chassis ``hero.h`` citation
        # (hero_height_floor reads ``hero_declared``) else content-solves
        # pure; a satellite keeps the chassis height floor. Widths are snug
        # for both (the snug-width ruling).
        h_floor = hero_height_floor(ch) if is_hero else nch.h
        sw, sh, _ = solve_node_box(ctx, node, i, h_floor=h_floor)
        w = w_override or sw
        h = h_override or max(sh, h_floor)
    # ``x=x, y=y`` exact (the caller's literal top-left) — ``cx``/``cy`` are
    # otherwise unused by the card path (place_node's escape hatch).
    return place_node(ctx, node, i, x + w / 2, y + h / 2, w=w, h=h, hero=is_hero, x=x, y=y)


def _hero_content_box(ctx: SolverContext, index: int, node: DiagramNode) -> tuple[float, float] | None:
    """The hero's TRUE content-solved (w, h) for a call site that positions
    it by CENTER or by an assumed chassis dimension (fanout-horizontal's
    crown, convergence's hero, bilateral's hub, upward/downward's source) —
    ``None`` only for a glyph-circle (it centers on its own radius; this box
    never applies to it). Marked and markless card heroes solve the SAME
    way now (a glyph row participates in content height exactly like a
    label row does); height floors at an explicit chassis citation
    (``hero_height_floor``), width is snug — never an uncited archetype
    dimension. A caller that assumed the chassis w/h for
    centering or offset math must use the returned box instead of
    ``ch.hero.w``/``.h`` (a markless hero landed 37px off the fan's true
    vertical center, and an assumed-width hub would mis-center
    horizontally, before every fan-family call site solved once, here, and
    reused the answer for both the offset math and the final placement).

    NOT ``force_card`` (unlike the old ``_hero_center_h``, which forced a
    card measurement to dodge a glyph-circle mismatch this function already
    handles via the style check above): ``force_card`` also suppresses
    ``solve_node_box``'s HEAD-anatomy dispatch, and a topology declaring
    ``node_anatomy: head`` (fanout-downward's portrait provider row) renders
    its hero through ``place_head``/``solve_head_box`` — measuring it as a
    plain card here disagreed with what actually paints, landing the desc
    rows outside the hero's own box (router-descent's two-line subtitle
    overflowed the crown once marked heroes stopped floor-hiding the gap)."""
    style = style_of(node, ctx.spec, ctx.ch)
    if style == NodeStyle.GLYPH_CIRCLE.value:
        return None
    ch = ctx.ch
    w, h, _ = solve_node_box(ctx, node, index, hero=True, h_floor=hero_height_floor(ch))
    return w, h


def _edge_anchor(p: NodePlacement, *, toward_right: bool, fan_dy: float = 0.0) -> tuple[float, float]:
    """An edge's anchor on a node's TRUE boundary via the shared shape-true
    primitive: card edge midpoint or circle rim, with a vertical fan offset
    re-projected onto the silhouette (retires the local rect/circle math and
    its 2px circle inset hack)."""
    center_y = p.cy if p.shape == "circle" else p.box.y + p.box.h / 2
    return side_anchor(p, side="right" if toward_right else "left", at=center_y + fan_dy)


def _fan_offsets(k: int, step: float = 12.0) -> list[float]:
    return [(i - (k - 1) / 2) * step for i in range(k)]


def _depart_trunk_len(ctx: SolverContext, slots: list[int], geos: list[EdgeGeo], *, vertical: bool = False) -> float:
    """Cargo-aware depart-trunk length. The trunk sizes to what it carries: a
    fan whose shared wire carries a route chip keeps the full ``depart_trunk``
    (chip_along + balanced stubs — the chip needs the run); a chipless fan
    departs FLUSH off the source's face (``depart_trunk_bare``, 0 by default —
    primer-fanout-refined.html: the spread's curves start exactly at the card
    mouth, no stub, no floating knot) so the burst reads as one continuous
    gesture instead of a dangling wire. The chip rides the shared trunk
    (``_edge_geo_by_index`` trunk_wins on the fanout family), so ANY fan edge
    declaring a label is trunk cargo — a subsumed TEXT label needs the float
    budget too (a 26px stub gave a trunk-riding label 33px and it ellipsized).

    ``full`` is a per-preset CITATION (router-descent's 66, the horizontal
    twins' own numbers) — the floor a hand specimen's OWN chip needed, not a
    guarantee for every story's label. The chip-run law (``chip_run_min``)
    grows the trunk past that citation when a different story's wider chip
    needs more room than the citation ever measured — a depart trunk is
    always arrowless (``marker="none"``; the spokes carry their own
    chevrons), so the bare ``CHIP_STUB_MIN`` stub is the whole floor, no
    marker reserve. The citation still wins outright whenever it already
    covers the chip, so every existing render stays byte-identical."""
    ch = ctx.ch
    full = float(ch.depart_trunk or 0)
    bare = float(ch.depart_trunk_bare or 0)
    cargo = [ctx.edges[geos[g].index] for g in slots if ctx.edges[geos[g].index].label]
    if not cargo:
        return bare
    return max(full, chip_run_min(cargo, ctx.cfg, stub=CHIP_STUB_MIN, vertical=vertical))


def _join_trunk_len(ctx: SolverContext, slots: list[int], geos: list[EdgeGeo]) -> float:
    """Spread-aware join-trunk floor. ``ch.join_trunk`` (100) is a per-preset
    CITATION off convergence-arrivals' own 4-input column — a flat pullback
    that undershoots badly on a THIN column: a low-arity gather (glyph-merge's
    2-in 'One glyph lookup') has little vertical spread to carry an angle with,
    so the same flat trunk leaves it reading near-flat and disconnected, the
    run not contracting with arity. Solve instead for the pullback that would
    reproduce the outer spoke's own chord angle off the 4-input hand files
    (pp-convergence.svg: half-spread 165 / run 440 = 0.375 — the more
    conservative of the two hand files' 0.375/0.531, chosen as the floor since
    no controlled multi-arity citation exists to pick between them; the DAG
    2-/3-source kv-cache joins move the SAME direction — steeper, not flatter,
    at lower member count — but their own run is confounded by unrelated
    per-preset rank-gap/canvas differences, so they inform direction only, not
    the constant). Floored at the citation (never shrinks the 4-in case — the
    citation already exceeds what this formula alone would ask for there) and
    capped at 19% of the natural run — pp-convergence-flow.svg is the only
    hand file that draws a real join trunk, and it spends 100 of its own
    524px run as bare wire (19.1%), matching this function's own "no hand
    file spends more than ~20%" rationale. The cap used to read 0.5 (half the
    run) — 2.6x that citation — so ``needed`` rode it to a 42-53% trunk on
    every convergence gather that doesn't cite convergence-arrivals' own
    tighter chassis (context-merge/flag-evaluation/gate-verdicts/glyph-merge
    all hit the old ceiling on their ordinary, uncited 2-4 input columns —
    the common case, not an edge case): near-identical specs rendered wildly
    different bare-wire runs because the SAFETY cap, not the content, was
    setting the trunk. ``natural_run`` and ``needed`` still carry content
    (member/hero widths shrink the former; arity/spread shrink or grow the
    latter) — this cap only stops either from spending more of the run as
    dead wire than the one specimen that actually draws a trunk ever does.
    ``chip_run_min`` (the caller) still grows the result past this cap
    afterward when the chip itself needs the room — convergence-arrivals'
    own render lands at 122.96px, chip-bound, unchanged by this cap either
    way."""
    ch = ctx.ch
    base = float(ch.join_trunk or 0)
    if not base or not slots:
        return base
    # Cargo rule, join side (the ``depart_trunk_bare`` mirror): a trunk
    # exists to carry its chip; a CHIPLESS join collapses to the bare length
    # (default 0 — flush at the mouth, the gather ring on the sink's face)
    # instead of dangling a bare arrowed wire before the sink.
    if not any(ctx.edges[geos[g].index].label for g in slots):
        return float(ch.join_trunk_bare or 0)
    mx, my = geos[slots[0]].tx, geos[slots[0]].ty
    natural_run = max((mx - geos[g].sx for g in slots), default=0.0)
    half_spread = max((abs(geos[g].sy - my) for g in slots), default=0.0)
    if natural_run <= 0 or half_spread <= 0:
        return base
    target_ratio = 0.375
    needed = natural_run - half_spread / target_ratio
    run_cap_fraction = 0.19  # pp-convergence-flow.svg: 100px trunk / 524px member-to-mouth run
    # The cap wraps OUTSIDE the citation floor, not inside it: on a thin
    # natural_run (0.19 * run < base) the growth clamp would otherwise pull
    # the result BELOW ch.join_trunk, contradicting "floored at the
    # citation" above for whichever future story lands there uncushioned by
    # chip_run_min's own max() (today only convergence-arrivals sits in that
    # corner, and its chip already carries it to 122.96 either way).
    return max(base, min(max(base, needed), run_cap_fraction * natural_run))


def _solve_fan_linear(ctx: SolverContext, *, direction: Literal["out", "in"]) -> DiagramLayout:
    """Shared S-curve linear-column machinery for the fan family's
    directional pair. direction="out" is fanout-horizontal: source LEFT,
    dest column RIGHT, the source is every edge's mouth (one-to-many reads
    left to right; the source centers on the dest column). direction="in" is
    convergence: inputs in a LEFT column, the hero RIGHT, the hero is every
    edge's mouth (every curve meets one point on the hero's facing edge —
    ingestion has a single mouth). Both directions read left-to-right and
    share the edge-anchor dispatch below (already general — it reads which
    node sits physically right of the other, so a "flipped pair" edge
    reverses correctly with no special case) and the knot_collapse gather-
    trunk piece, dressed depart (out) vs join (in). Member measurement, the
    bottom-margin chassis field, and the focal card's own box solve stay
    direction-specific — each is a hand-tuned fact of its own chassis
    (fanout-horizontal's ``footer_h`` and convergence's ``bottom_m`` are
    different numbers that were never meant to trade places)."""
    ch = ctx.ch
    spec = ctx.spec
    width = ch.width
    k = len(spec.nodes) - 1
    p = _pitch(ctx)
    content_top = ch.header_h
    placed: dict[int, NodePlacement] = {}
    if direction == "out":
        focal_i = 0
        member_idx = list(range(1, len(spec.nodes)))
        members = [spec.nodes[i] for i in member_idx]
        member_ws, member_hs = _member_boxes(ctx, members)
        member_h = max(member_hs)  # aligned column shares one card height
        # Grow the pitch by exactly the height a wrapped desc adds, so the
        # inter-card gap (p - nch.h) is preserved; byte-identical when the
        # desc fits (member_h == nch.h).
        pitch = p + max(0.0, member_h - ch.node.h)
        member_x = width - ch.margin_x - max(member_ws)
        column_h = (k - 1) * pitch + member_h
        focal_cy = content_top + column_h / 2
        # The footer band spans last-dest-bottom -> canvas edge (the
        # specimen's 78px already includes the breathing room — no separate
        # bottom margin).
        height = int(content_top + column_h + ch.footer_h)
        for slot, i in enumerate(member_idx):
            placed[i] = _place(
                ctx,
                i,
                spec.nodes[i],
                x=member_x,
                y=content_top + slot * pitch,
                w_override=member_ws[slot],
                h_override=member_hs[slot],
            )
        hero_box = _hero_content_box(ctx, focal_i, spec.nodes[focal_i])
        hero_h = hero_box[1] if hero_box is not None else None
        placed[focal_i] = _place(
            ctx,
            focal_i,
            spec.nodes[focal_i],
            x=ch.margin_x,
            y=focal_cy - (hero_h / 2 if hero_h is not None else ch.hero.h / 2),
            hero=True,
            h_override=hero_h if hero_h is not None else 0.0,
        )
    else:
        focal_i = len(spec.nodes) - 1
        member_idx = list(range(len(spec.nodes) - 1))
        members = [spec.nodes[i] for i in member_idx]
        member_ws = _member_widths(ctx, members)
        column_h = (k - 1) * p + ch.node.h
        focal_cy = content_top + column_h / 2
        height = int(content_top + column_h + ch.bottom_m)
        # Edge-run law: a cited ``focal_run`` derives the focal seat and the
        # canvas from the members' own widths + the hand file's face-to-face
        # run — positions follow the gap citation, never a fixed frame.
        run_cited = float(ch.focal_run or 0.0)
        for slot, i in enumerate(member_idx):
            placed[i] = _place(
                ctx,
                i,
                spec.nodes[i],
                x=ch.margin_x,
                y=content_top + slot * p,
                w_override=member_ws[slot],
            )
        # ``hero=True`` pinned (unconditional, not role-derived) — matches the
        # original's hardcoded ``hero=True``/``ch.hero``; the focal index is
        # convergence's structural focal slot, so this is byte-identical in
        # practice, but preserved as an explicit override, not auto-derive.
        # ``force_card=True``: measured via ``solve_card_w`` alone (never
        # checking style), so this stays a CARD measurement even for a
        # glyph-circle hero — ``_place``'s circle branch ignores it anyway
        # (uses the fixed hero chassis width for its center, not this content
        # width; only the positioning offset below reads it) — the same
        # measure/render split ``_member_widths``/``_member_boxes`` preserve.
        focal_w, _, _ = solve_node_box(
            ctx,
            spec.nodes[focal_i],
            focal_i,
            hero=True,
            force_card=True,
        )
        hero_box = _hero_content_box(ctx, focal_i, spec.nodes[focal_i])
        hero_h = hero_box[1] if hero_box is not None else None
        if run_cited:
            # Edge-run law: the focal seat derives from the members' faces +
            # the cited run; the canvas follows.
            focal_x = ch.margin_x + max(member_ws, default=0.0) + run_cited
            width = int(focal_x + focal_w + ch.margin_x)
        else:
            focal_x = width - ch.margin_x - focal_w
        placed[focal_i] = _place(
            ctx,
            focal_i,
            spec.nodes[focal_i],
            x=focal_x,
            y=focal_cy - (hero_h / 2 if hero_h is not None else ch.hero.h / 2),
            hero=True,
            w_override=focal_w,
            h_override=hero_h if hero_h is not None else 0.0,
        )
    nodes = [placed[i] for i in range(len(spec.nodes))]
    geos: list[EdgeGeo] = []
    for j, edge in enumerate(ctx.edges):
        src, dst = nodes[edge.source], nodes[edge.target]
        rightward = dst.box.x > src.box.x
        sx, sy = _edge_anchor(src, toward_right=rightward)
        tx, ty = _edge_anchor(dst, toward_right=not rightward)
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
    # The gather-fan trunk (knot_collapse): a focal node that AUTHORS
    # ``gather: true`` collapses >=2 mouth-sharing edges at a knot floated off
    # the mouth, one trunk carrying them the rest of the way. depart (out):
    # the fan leaves the source on ONE wire, dressed like its own spokes,
    # arrowless (the spokes carry the chevrons; router specimens). join (in):
    # arrivals meet the hero on ONE wire, assert-dressed and arrowed
    # (convergence-arrivals). join and dag's trunks already gated on
    # node.gather; depart now matches instead of firing unconditionally
    # whenever >=2 spokes exist.
    if ctx.spec.nodes[focal_i].gather:
        if direction == "out" and float(ch.depart_trunk or 0):
            slots = [g for g, geo in enumerate(geos) if ctx.edges[geo.index].source == focal_i]
            if len(slots) >= 2:
                rels = {ctx.edges[geos[g].index].relation or "" for g in slots}
                rel = rels.pop() if len(rels) == 1 else "assert"
                knot_collapse(
                    geos, slots, trunk_len=_depart_trunk_len(ctx, slots, geos), depart=True, relation=rel, marker="none"
                )
        elif direction == "in" and float(ch.join_trunk or 0):
            slots = [g for g, geo in enumerate(geos) if ctx.edges[geo.index].target == focal_i]
            if len(slots) >= 2:
                # ``ch.join_trunk`` is a per-preset CITATION (convergence-
                # arrivals' own compose chip) — the floor for that hand
                # specimen's chip, not a guarantee for every convergence
                # story's label. A join trunk always draws its terminal
                # arrow at the mouth (``knot_collapse``'s default marker),
                # so the chip-run law reserves the chevron's own draw
                # length beyond the bare stub — the DAG join's law
                # (``_join_chip_stub``), generalized here for the fan
                # family's own join. The citation still wins outright
                # whenever it already covers the chip (byte-identical).
                cargo = [ctx.edges[geos[g].index] for g in slots if ctx.edges[geos[g].index].label]
                trunk_len = _join_trunk_len(ctx, slots, geos)
                if cargo:
                    trunk_len = max(
                        trunk_len,
                        chip_run_min(cargo, ctx.cfg, stub=marker_reserved_stub(ctx.engine, CHIP_STUB_MIN)),
                    )
                knot_collapse(geos, slots, trunk_len=trunk_len)
                # A gather line carries its verb chip before the hero card
                # (convergence-arrivals' compose trunk), alongside any in-card
                # chips the hero declares. Convergence grounds the chip ON the
                # wire (lift=0) — the specimen seats it dead-center on the
                # trunk, unlike the DAG join's mouth-lift (there, crowded
                # arrivals push it clear). A FLUSH (chipless) join appended no
                # trunk geo — nothing to seat a chip on.
                if trunk_len:
                    from hyperweave.compose.diagram.graph import _seat_gather_chip

                    _seat_gather_chip(ctx, geos, slots, geos[-1], lift=0.0)
    return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)


def solve_fanout_horizontal(ctx: SolverContext) -> DiagramLayout:
    """Source left, dest column right: one-to-many reads left to right —
    the fan-linear family's direction=out (the source is every edge's
    mouth)."""
    return _solve_fan_linear(ctx, direction="out")


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
    dest_ws, dest_hs = _member_boxes(ctx, list(spec.nodes[1:]))
    dest_h = max(dest_hs)  # both sides distribute over one shared card height
    # Grow the band pitch by the height a wrapped desc adds (byte-identical
    # when dest_h == nch.h), so taller cards never overlap.
    pitch = p + max(0.0, dest_h - ch.node.h)
    band = (max(left_n, right_n) - 1) * pitch
    src_cy = ch.header_h + (band + dest_h) / 2
    height = int(2 * src_cy)
    left_ws = [w for w, i in zip(dest_ws, range(1, len(spec.nodes)), strict=True) if (i - 1) < left_n]
    facing_left = ch.margin_x + (max(left_ws) if left_ws else 0.0)
    facing_right = width - ch.margin_x - max(dest_ws)
    # The bilateral canon (alpha3 integration hub) is a DOUBLE mirror: the
    # medallion sits at the exact midpoint of the two column faces (110 and
    # 710 about the 410 hub — equal 300 throws) and its CIRCLE center rides
    # the seat band's center line. width/2 broke the first mirror whenever
    # the two columns' widths differed; centering the labeled BOX broke the
    # second (an under-label lifted the circle 20px off the seat line).
    hub_cx = (facing_left + facing_right) / 2
    hero_style = style_of(spec.nodes[0], spec, ch)
    if hero_style == NodeStyle.GLYPH_CIRCLE.value:
        r0 = ch.hero_circle_r
        nodes: list[NodePlacement] = [_place(ctx, 0, spec.nodes[0], x=hub_cx - r0, y=src_cy - r0, hero=True)]
    else:
        # The hub's own content-solved box (G3 dominance law: floored at an
        # explicit chassis citation or the dest columns' measured width,
        # never an uncited archetype) — ``hub_cx - ch.hero.w / 2`` assumed
        # the chassis width for centering; a hero solving NARROWER than
        # that (undeclared, dominance below the paradigm default) needs the
        # REAL width here or it renders off the hub's intended center axis.
        hero_box = _hero_content_box(ctx, 0, spec.nodes[0])
        hero_w, hero_h = hero_box if hero_box is not None else (ch.hero.w, ch.hero.h)
        nodes = [
            _place(
                ctx,
                0,
                spec.nodes[0],
                x=hub_cx - hero_w / 2,
                y=src_cy - hero_h / 2,
                hero=True,
                w_override=hero_w,
                h_override=hero_h,
            )
        ]

    def side_cy(idx: int, count: int) -> float:
        if count == 1:
            return src_cy
        return src_cy - band / 2 + idx * (band / (count - 1))

    sides: list[int] = []
    for i, node in enumerate(spec.nodes[1:], start=1):
        on_left = (i - 1) < left_n
        idx = (i - 1) if on_left else (i - 1 - left_n)
        cy = side_cy(idx, left_n if on_left else right_n)
        w = dest_ws[i - 1]
        x = facing_left - w if on_left else width - ch.margin_x - max(dest_ws)
        nodes.append(
            _place(
                ctx,
                i,
                node,
                x=x,
                y=cy - dest_hs[i - 1] / 2,
                hero=False,
                w_override=w,
                h_override=dest_hs[i - 1],
            )
        )
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
        hub_pt = _edge_anchor(hub, toward_right=not on_left, fan_dy=fan)
        other = nodes[other_idx]
        other_pt = _edge_anchor(other, toward_right=on_left)
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
    # The canvas reserves the chassis archetype height regardless of the
    # hero's actual content height (G3 dominance never shrinks the RESERVED
    # band, only the rendered box within it) — a shorter undeclared hero
    # reads as slightly more bottom air, never a clipped or shifted canvas.
    height = int(src_top + ch.hero.h + ch.bottom_m)
    hero_box = _hero_content_box(ctx, 0, spec.nodes[0])
    hero_w, hero_h = hero_box if hero_box is not None else (ch.hero.w, ch.hero.h)
    nodes.append(
        _place(
            ctx, 0, spec.nodes[0], x=width / 2 - hero_w / 2, y=src_top, hero=True, w_override=hero_w, h_override=hero_h
        )
    )
    for i, node in enumerate(spec.nodes[1:], start=1):
        cx, bottom = positions[i - 1]
        w = dest_ws[i - 1]
        nodes.append(_place(ctx, i, node, x=cx - w / 2, y=bottom - ch.node.h, w_override=w))
    # Root each curve directly under its dest, clamped to the source's top
    # edge (G7): a centered start hugs the inner row boxes; a dest-aligned
    # root rises through the row gaps and bends only over the last span.
    half = hero_w / 2 - 14.0
    src = nodes[0]
    geos: list[EdgeGeo] = []
    for j, edge in enumerate(ctx.edges):
        other = edge.target if edge.target != 0 else edge.source
        dest = nodes[other]
        dcx = dest.box.x + dest.box.w / 2
        root_x = min(max(dcx, width / 2 - half), width / 2 + half)
        # Shape-true attachments: the root lands on the source's top rim at
        # root_x, the far end on the dest's bottom rim at its center x.
        rx_a, root_y = side_anchor(src, side="top", at=root_x)
        dcx_a, dbottom = side_anchor(dest, side="bottom", at=dcx)
        upward = edge.target != 0
        if upward:
            sx, sy, tx, ty = rx_a, root_y, dcx_a, dbottom
        else:
            sx, sy, tx, ty = dcx_a, dbottom, rx_a, root_y
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
    one point on the hero's facing edge — ingestion has a single mouth. The
    fan-linear family's direction=in (the hero is every edge's mouth)."""
    return _solve_fan_linear(ctx, direction="in")


def solve_fanout_downward(ctx: SolverContext) -> DiagramLayout:
    """Source top-center, dest ROW at the bottom: one-to-many fanning DOWN — the
    vertical mirror of ``solve_fanout_horizontal``. A depart trunk drops from the
    source to a knot, then the fan spreads on vertical S-curves to the dest TOP
    edges (router-descent's model router routing to a provider row)."""
    ch = ctx.ch
    spec = ctx.spec
    width = ch.width
    k = len(spec.nodes) - 1
    dest_ws, dest_hs = _member_boxes(ctx, list(spec.nodes[1:]))
    dest_w = max(dest_ws)
    dest_h = max(dest_hs)
    pitch = _pitch(ctx) + max(0.0, dest_w - ch.node.w)
    row_w = (k - 1) * pitch + dest_w
    x0 = width / 2 - row_w / 2
    content_top = ch.margin_top
    height = int(ch.height or 740)
    dest_top = height - ch.footer_h - ch.bottom_m - dest_h
    hero_box = _hero_content_box(ctx, 0, spec.nodes[0])
    hero_w, hero_h = hero_box if hero_box is not None else (ch.hero.w, ch.hero.h)
    nodes: list[NodePlacement] = [
        _place(
            ctx,
            0,
            spec.nodes[0],
            x=width / 2 - hero_w / 2,
            y=content_top,
            hero=True,
            w_override=hero_w,
            h_override=hero_h,
        )
    ]
    x = x0
    for i, node in enumerate(spec.nodes[1:], start=1):
        w = dest_ws[i - 1]
        nodes.append(
            _place(
                ctx,
                i,
                node,
                x=x + (dest_w - w) / 2,
                y=dest_top,
                w_override=w,
                h_override=dest_hs[i - 1],
            )
        )
        x += pitch
    src = nodes[0]
    half = hero_w / 2 - 14.0
    geos: list[EdgeGeo] = []
    for j, edge in enumerate(ctx.edges):
        other = edge.target if edge.target != 0 else edge.source
        dest = nodes[other]
        dcx = dest.box.x + dest.box.w / 2
        # Root each curve under its dest, clamped to the source's bottom rim
        # (G7) so it rises through the fan region instead of hugging a neighbour.
        root_x = min(max(dcx, width / 2 - half), width / 2 + half)
        rx_a, root_y = side_anchor(src, side="bottom", at=root_x)
        dcx_a, dtop = side_anchor(dest, side="top", at=dcx)
        down = edge.target != 0
        sx, sy, tx, ty = (rx_a, root_y, dcx_a, dtop) if down else (dcx_a, dtop, rx_a, root_y)
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
    # The depart trunk (router-descent): the fan leaves the source on ONE wire
    # to a knot floated depart_trunk DOWN, then spreads — the arrowless departure
    # dress, the one-to-many mirror of the convergence join. Gated on the source
    # authoring ``gather: true`` (join and dag's trunks already gated this way;
    # depart now matches instead of firing unconditionally on >=2 spokes).
    if ctx.spec.nodes[0].gather and float(ch.depart_trunk or 0):
        slots = [g for g, geo in enumerate(geos) if ctx.edges[geo.index].source == 0]
        if len(slots) >= 2:
            rels = {ctx.edges[geos[g].index].relation or "" for g in slots}
            rel = rels.pop() if len(rels) == 1 else "assert"
            mouth = (src.box.x + src.box.w / 2, src.box.y + src.box.h)
            knot_collapse(
                geos,
                slots,
                trunk_len=_depart_trunk_len(ctx, slots, geos, vertical=True),
                depart=True,
                relation=rel,
                marker="none",
                vertical=True,
                mouth=mouth,
            )
    return finish_layout(ctx, width=width, height=height, nodes_paint=nodes, geos=geos)


register_solvers(
    {
        "fanout-horizontal": solve_fanout_horizontal,
        "fanout-bilateral": solve_fanout_bilateral,
        "fanout-upward": solve_fanout_upward,
        "fanout-downward": solve_fanout_downward,
        "convergence": solve_convergence,
    }
)
