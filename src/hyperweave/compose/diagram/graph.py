"""Layered-graph solvers: dag and state-machine.

The general-graph half of the family, kept simple and deterministic by
honest caps. DAG: longest-path rank assignment, fixed-sweep barycenter
crossing reduction (input-order tie-breaks — stable sorts only), rank-
channel S-curves, and skip edges routed through under-channels below the
content band. State machine rides the same machinery: back-edges (DFS,
edge order) lift out, the longest forward chain takes the pill baseline,
off-chain states drop beneath their predecessor, and back-edges return as
under-curves — the back-edge is the point.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from hyperweave.compose.diagram.chrome import glyph_slot_builder, mark_w_for, place_card, place_pill, solve_card_w
from hyperweave.compose.diagram.paths import fmt, line_d, line_len, s_curve_h, s_curve_h_len
from hyperweave.compose.diagram.solver import finish_layout, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
from hyperweave.compose.matrix.cells import measure_voice
from hyperweave.compose.spatial_records import LineSpec
from hyperweave.core.diagram import DiagramCapacityError, DiagramNode, NodeRole, NodeStyle, ResolvedEdge

if TYPE_CHECKING:
    from collections.abc import Callable

    from hyperweave.compose.diagram.records import DiagramLayout, GlyphArt, NodePlacement


def _node_style(ctx: SolverContext, node: DiagramNode) -> str:
    if node.style is not None:
        return node.style.value
    if ctx.spec.node_style is not None:
        return ctx.spec.node_style.value
    return ctx.ch.node_style or NodeStyle.CARD.value


def _card_art(ctx: SolverContext, i: int, node: DiagramNode) -> Callable[[float, float], GlyphArt | None] | None:
    """card+glyph anatomy: the identity mark takes the dot slot."""
    if _node_style(ctx, node) != NodeStyle.CARD_GLYPH.value or not node.glyph:
        return None
    return glyph_slot_builder(node.glyph, ctx.glyph_registry, ctx.glyph_selections[i])


def _longest_path_ranks(n: int, edges: list[ResolvedEdge]) -> list[int]:
    """rank[v] = longest edge-count path from any source — deterministic
    (acyclicity is validated in the IR; iterate to fixpoint, n passes max)."""
    rank = [0] * n
    for _ in range(n):
        changed = False
        for e in edges:
            if rank[e.target] < rank[e.source] + 1:
                rank[e.target] = rank[e.source] + 1
                changed = True
        if not changed:
            break
    return rank


def _barycenter_orders(n: int, edges: list[ResolvedEdge], rank: list[int], sweeps: int = 4) -> dict[int, list[int]]:
    """Per-rank vertical orders after fixed barycenter sweeps.

    Initial order is spec order; each down pass orders a rank by the mean
    position of predecessors, each up pass by successors. Stable sorts on
    rounded keys keep ties in current order — same input, same layout."""
    ranks = sorted(set(rank))
    orders: dict[int, list[int]] = {r: [i for i in range(n) if rank[i] == r] for r in ranks}
    preds: dict[int, list[int]] = {}
    succs: dict[int, list[int]] = {}
    for e in edges:
        preds.setdefault(e.target, []).append(e.source)
        succs.setdefault(e.source, []).append(e.target)

    def position(r: int) -> dict[int, int]:
        return {node: i for i, node in enumerate(orders[r])}

    def sweep(rank_seq: list[int], neighbors: dict[int, list[int]], neighbor_rank_of: int) -> None:
        for r in rank_seq:
            ref = r + neighbor_rank_of
            if ref not in orders:
                continue
            pos = position(ref)
            keyed = []
            for node in orders[r]:
                ns = [pos[p] for p in neighbors.get(node, []) if rank[p] == ref]
                keyed.append((round(sum(ns) / len(ns), 4) if ns else float(position(r)[node]), node))
            orders[r] = [node for _, node in sorted(keyed, key=lambda kv: kv[0])]

    for _ in range(sweeps):
        sweep(ranks[1:], preds, -1)  # down: order by predecessors above-left
        sweep(list(reversed(ranks[:-1])), succs, +1)  # up: order by successors
    return orders


def solve_dag(ctx: SolverContext) -> DiagramLayout:
    ch = ctx.ch
    spec = ctx.spec
    n = len(spec.nodes)
    edges = list(ctx.edges)
    caps = ctx.engine.get("caps") or {}
    rank = _longest_path_ranks(n, edges)
    n_ranks = max(rank) + 1
    if n_ranks > int(caps.get("dag_max_ranks", 4)):
        raise DiagramCapacityError(f"dag caps at {caps.get('dag_max_ranks', 4)} ranks (got {n_ranks}); split the graph")
    orders = _barycenter_orders(n, edges, rank)
    for r, members in orders.items():
        if len(members) > int(caps.get("dag_max_per_rank", 4)):
            raise DiagramCapacityError(
                f"dag caps at {caps.get('dag_max_per_rank', 4)} nodes per rank (rank {r} has {len(members)})"
            )
    skips = [e for e in edges if rank[e.target] - rank[e.source] >= 2]
    if len(skips) > int(caps.get("dag_max_skip_edges", 3)):
        raise DiagramCapacityError(
            f"dag caps at {caps.get('dag_max_skip_edges', 3)} rank-skipping edges (got {len(skips)})"
        )
    height = ch.height or 360
    mid = (ch.header_h + height - ch.footer_h) / 2
    usable = height - ch.header_h - ch.footer_h - ch.node.h + 10
    # Aligned ranks (G3): ONE content-solved width over all members keeps
    # the rank columns and gaps regular. The canvas then sizes to the rank
    # count (the chassis width is the floor, so three-rank graphs keep the
    # 760 banner) — a four-rank graph at the announced cap NEEDS the span;
    # squeezing it under 760 truncated every label to a single letter.
    card_w = max(
        solve_card_w(
            n, ch.node, ctx.cfg, ctx.mono_triggers, min_w=ch.card_min_w, mark_w=mark_w_for(_node_style(ctx, n), n)
        )
        for n in spec.nodes
    )
    width = int(max(ch.width, 2 * ch.margin_x + n_ranks * card_w + (n_ranks - 1) * ch.rank_gap))
    placed: dict[int, NodePlacement] = {}
    for r, members in orders.items():
        x = ch.margin_x + r * (card_w + ch.rank_gap)
        k = len(members)
        pitch = min(ch.rank_pitch_max, usable / (k - 1)) if k > 1 else 0.0
        for i, node_index in enumerate(members):
            cy = mid + (i - (k - 1) / 2) * pitch
            placed[node_index] = place_card(
                index=node_index,
                node=spec.nodes[node_index],
                x=x,
                y=cy - ch.node.h / 2,
                nch=ch.hero if spec.nodes[node_index].role is NodeRole.HERO else ch.node,
                cfg=ctx.cfg,
                accent_index=ctx.node_accents[node_index],
                mono_triggers=ctx.mono_triggers,
                muted_dash=str(ctx.engine["track"]["muted_dash"]),
                w_override=card_w,
                glyph_builder=_card_art(ctx, node_index, spec.nodes[node_index]),
            )
    in_degree: dict[int, int] = {}
    for e in edges:
        in_degree[e.target] = in_degree.get(e.target, 0) + 1
    # The under-channel must be where the edge ACTUALLY runs (G7): a single
    # cubic with controls at the channel never reaches it (~75% depth) and
    # grazes rank boxes. Three segments — dive, flat run ON the channel,
    # rise — keep clearance true; channels stack DOWNWARD and the canvas
    # grows to hold them.
    deepest_box = max((p.box.y + p.box.h for p in placed.values()), default=0.0)
    clearance = float(ctx.engine.get("min_clearance", 18))
    channel_base = max(height - ch.footer_h - ch.skip_drop, deepest_box + clearance + 4)
    geos: list[EdgeGeo] = []
    skip_seen = 0
    deepest_channel = 0.0
    for j, e in enumerate(edges):
        a, b = placed[e.source].box, placed[e.target].box
        scy, tcy = a.y + a.h / 2, b.y + b.h / 2
        if rank[e.target] - rank[e.source] >= 2:
            channel = channel_base + skip_seen * ch.skip_stack
            deepest_channel = max(deepest_channel, channel)
            skip_seen += 1
            land_y = tcy + (16.0 if in_degree.get(e.target, 0) > 1 else 0.0)
            sx, tx = a.x + a.w, b.x
            d = (
                f"M {fmt(sx)},{fmt(scy)} "
                f"C {fmt(sx + 34)},{fmt(scy)} {fmt(sx + 34)},{fmt(channel)} {fmt(sx + 68)},{fmt(channel)} "
                f"L {fmt(tx - 68)},{fmt(channel)} "
                f"C {fmt(tx - 34)},{fmt(channel)} {fmt(tx - 34)},{fmt(land_y)} {fmt(tx)},{fmt(land_y)}"
            )
            length = (tx - sx) + (channel - scy) + (channel - land_y)
            geos.append(EdgeGeo(index=j, d=d, sx=sx, sy=scy, tx=tx, ty=land_y, length=length))
            continue
        sx, tx = a.x + a.w, b.x
        geos.append(
            EdgeGeo(
                index=j,
                d=s_curve_h(sx, scy, tx, tcy),
                sx=sx,
                sy=scy,
                tx=tx,
                ty=tcy,
                length=s_curve_h_len(sx, scy, tx, tcy),
            )
        )
    if deepest_channel:
        height = max(height, int(deepest_channel + clearance + ch.footer_h))
    paint = [placed[i] for i in sorted(placed)]
    return finish_layout(ctx, width=width, height=height, nodes_paint=paint, geos=geos)


def _back_edges(n: int, edges: list[ResolvedEdge]) -> set[int]:
    """Edge positions that close a cycle — DFS in edge order (deterministic)."""
    adj: dict[int, list[tuple[int, int]]] = {}
    for j, e in enumerate(edges):
        adj.setdefault(e.source, []).append((j, e.target))
    color = [0] * n
    back: set[int] = set()

    def dfs(u: int) -> None:
        color[u] = 1
        for j, v in adj.get(u, []):
            if color[v] == 1:
                back.add(j)
            elif color[v] == 0:
                dfs(v)
        color[u] = 2

    for s in range(n):
        if color[s] == 0:
            dfs(s)
    return back


def solve_state_machine(ctx: SolverContext) -> DiagramLayout:
    ch = ctx.ch
    spec = ctx.spec
    n = len(spec.nodes)
    edges = list(ctx.edges)
    caps = ctx.engine.get("caps") or {}
    back = _back_edges(n, edges)
    if len(back) > int(caps.get("sm_max_back_edges", 2)):
        raise DiagramCapacityError(f"state-machine caps at {caps.get('sm_max_back_edges', 2)} back-edges")
    forward = [e for j, e in enumerate(edges) if j not in back]
    rank = _longest_path_ranks(n, forward)
    # The happy path: walk the longest forward chain (first-seen tie-break).
    succ_best: dict[int, int] = {}
    for e in forward:
        if rank[e.target] == rank[e.source] + 1 and e.source not in succ_best:
            succ_best[e.source] = e.target
    start = next((i for i in range(n) if rank[i] == 0), 0)
    baseline: list[int] = [start]
    while baseline[-1] in succ_best:
        baseline.append(succ_best[baseline[-1]])
    below = [i for i in range(n) if i not in baseline]
    if len(below) > int(caps.get("sm_max_below_baseline", 2)):
        raise DiagramCapacityError(
            f"state-machine caps at {caps.get('sm_max_below_baseline', 2)} off-baseline states (got {len(below)})"
        )
    width, height = ch.width, ch.height or 300
    cy = ch.header_h + ch.node.h
    placed: dict[int, NodePlacement] = {}
    x = ch.margin_x
    last_baseline = baseline[-1]
    for i in baseline:
        node = spec.nodes[i]
        tag = "TERMINAL" if (i == last_baseline and node.role is NodeRole.HERO) else ""
        nch = ch.hero if node.role is NodeRole.HERO else ch.node
        # Pills are the family's one content-solved width — compute it
        # first so the pill can START at the cursor (place_pill centers).
        w = max(
            nch.w,
            ch.pill_min_w,
            math.ceil((measure_voice(node.label, ctx.cfg.label_voice) + 2 * ch.pill_pad_x) / 10) * 10,
        )
        p = place_pill(
            index=i,
            node=node,
            cx=x + w / 2,
            cy=cy,
            nch=nch,
            ch=ch,
            cfg=ctx.cfg,
            accent_index=ctx.node_accents[i],
            tag=tag,
        )
        placed[i] = p
        x = p.box.x + p.box.w + ch.pill_gap
    if x - ch.pill_gap > width - ch.margin_x + 0.5:
        raise DiagramCapacityError(
            f"state-machine baseline overflows the {width}px banner; shorten labels or split the machine"
        )
    # Off-baseline states drop beneath their first forward predecessor.
    pred_of: dict[int, int] = {}
    for e in forward:
        if e.target in below and e.target not in pred_of:
            pred_of[e.target] = e.source
    for i in below:
        anchor = placed[pred_of.get(i, baseline[0])]
        acx = anchor.box.x + anchor.box.w / 2
        placed[i] = place_pill(
            index=i,
            node=spec.nodes[i],
            cx=acx,
            cy=cy + ch.drop_dy,
            nch=ch.node,
            ch=ch,
            cfg=ctx.cfg,
            accent_index=ctx.node_accents[i],
        )
    geos: list[EdgeGeo] = []
    for j, e in enumerate(edges):
        a, b = placed[e.source], placed[e.target]
        ab, bb = a.box, b.box
        if j in back:
            # The revise loop: an under-curve from the source's left edge
            # back into the target's underside — the structural feature
            # that separates this topology from a pipeline.
            sx, sy = ab.x, ab.y + ab.h / 2
            tcx = bb.x + bb.w / 2
            entry_y = bb.y + bb.h + 2
            d = (
                f"M {fmt(sx)},{fmt(sy)} C {fmt(sx - ch.loop_dx)},{fmt(sy + ch.loop_dy)} "
                f"{fmt(tcx)},{fmt(entry_y + 47)} {fmt(tcx)},{fmt(entry_y)}"
            )
            geos.append(
                EdgeGeo(
                    index=j,
                    d=d,
                    sx=sx,
                    sy=sy,
                    tx=tcx,
                    ty=entry_y,
                    length=line_len(sx, sy, tcx, entry_y) * 1.3,
                    label_pos=(sx - ch.loop_dx - 32.0, sy - 6.0),
                    label_max_w=96.0,
                    label_anchor="start",
                )
            )
        elif e.target in below or e.source in below:
            drop = e.target in below
            top = (ab.y + ab.h, bb.y) if drop else (bb.y + bb.h, ab.y)
            cxx = (bb.x + bb.w / 2) if drop else (ab.x + ab.w / 2)
            y1, y2 = top
            geos.append(
                EdgeGeo(
                    index=j,
                    d=line_d(cxx, y1, cxx, y2),
                    sx=cxx,
                    sy=y1,
                    tx=cxx,
                    ty=y2,
                    length=abs(y2 - y1),
                    label_pos=(cxx + 12.0, (y1 + y2) / 2 + 3.0),
                    label_max_w=96.0,
                    label_anchor="start",
                )
            )
        else:
            forwardward = bb.x > ab.x
            sx = ab.x + ab.w if forwardward else ab.x
            tx = bb.x if forwardward else bb.x + bb.w
            geos.append(
                EdgeGeo(
                    index=j,
                    d=line_d(sx, cy, tx, cy),
                    sx=sx,
                    sy=cy,
                    tx=tx,
                    ty=cy,
                    length=abs(tx - sx),
                    label_pos=((sx + tx) / 2, cy - 8.0),
                    label_max_w=abs(tx - sx) + 56.0,
                )
            )
    first = placed[baseline[0]].box
    initial_dot = (first.x - ch.stub_len - 4.0, cy)
    initial_stub = LineSpec(x1=first.x - ch.stub_len, y1=cy, x2=first.x, y2=cy)
    paint = [placed[i] for i in sorted(placed)]
    return finish_layout(
        ctx,
        width=width,
        height=height,
        nodes_paint=paint,
        geos=geos,
        initial_dot=initial_dot,
        initial_stub=initial_stub,
    )


register_solvers({"dag": solve_dag, "state-machine": solve_state_machine})
