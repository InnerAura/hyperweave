"""The swimlane loop — the lane-membership minor allocator.

Its own module beside ``loop.py`` (split at the seam, never grown into it):
when a loop spec declares ``lanes``, minor position is assigned by LANE
MEMBERSHIP instead of seat kind. The corpus construction (the shuttle's
role lanes): full-width tinted bands in declared order, every station
centered in its lane; work moves ALONG the flow within a lane and crosses
between lanes at a fixed handoff column (source face + lane_hop, filleted
H-V-H); a cross-lane TERMINAL drops in place at its source's rank (the
at-rank exit law); and the return crosses back through the gutter adjacent
to its target's lane, riding the gutter's own midline, rising into the
target's near face — the guard chip seated on the channel run.

Constants live in the ``loop:`` block of ``data/config/diagram-frame.yaml``
(lane_* keys), cited from the swimlane specimen.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from hyperweave.compose.diagram.axis import AxisMap
from hyperweave.compose.diagram.chrome import place_node
from hyperweave.compose.diagram.loop import (
    _assign_seats,
    _chassis_cls,
    _chip_run_need,
    _face_point,
    _lcfg,
    _line,
    _partition_dress,
    _stand,
    _unit,
    classify_loop,
)
from hyperweave.compose.diagram.records import DiagramText, LaneBand, NodePlacement
from hyperweave.compose.diagram.route import orthogonal_d
from hyperweave.compose.diagram.sizing import centred_baseline, solve_node_box
from hyperweave.compose.diagram.solver import finish_layout
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
from hyperweave.compose.matrix.cells import measure_voice
from hyperweave.compose.spatial_records import RectSpec

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import DiagramLayout


def solve_loop_lanes(ctx: SolverContext) -> DiagramLayout:
    ax = AxisMap.for_slug(ctx.slug)
    ch = ctx.ch
    spec = ctx.spec
    sh = classify_loop(ctx.spec, ctx.edges)
    rank, seat = _assign_seats(ctx, sh)
    standoff = ch.connector_standoff if ch.connector_standoff is not None else 0.0
    lanes = [str(c) for c in spec.lanes]
    lane_of = {i: lanes.index(n.category) for i, n in enumerate(spec.nodes) if n.category in lanes}
    pad_y = _lcfg(ctx, "lane_pad_y", 38.0)
    pad_term = _lcfg(ctx, "lane_pad_terminal", 26.0)
    gutter = _lcfg(ctx, "lane_gutter", 44.0)
    lane_hop = _lcfg(ctx, "lane_hop", 76.0)
    lane_r = _lcfg(ctx, "lane_r", 18.0)
    reach = _lcfg(ctx, "lane_reach", 34.0)

    # A cross-lane TERMINAL drops in place at its source's rank — the
    # at-rank exit law, spoken vertically (the specimen's Shipped under its
    # own Approve?).
    for _k, e in [*sh.forward, *([sh.ret] if sh.ret is not None else [])]:
        if (
            spec.nodes[e.target].station == "terminal"
            and lane_of.get(e.source) is not None
            and lane_of.get(e.target) is not None
            and lane_of[e.source] != lane_of[e.target]
        ):
            rank[e.target] = rank[e.source]

    # ── Boxes (the loop's own box solve; scopes don't ride lanes) ────────
    boxes: dict[int, tuple[float, float]] = {}
    for i, node in enumerate(spec.nodes):
        w, h, _l = solve_node_box(ctx, node, i, chassis_class=_chassis_cls(node, seat.get(i, "")))
        boxes[i] = (w, h)

    # ── Rank majors (spine allocation, chip-run floors on in-lane runs) ──
    ranks = sorted({r for r in rank.values()})
    rank_extent: dict[int, float] = {}
    for i, (w, h) in boxes.items():
        rank_extent[rank[i]] = max(rank_extent.get(rank[i], 0.0), ax.box_major(w, h))
    gap = ch.gap
    gap_need: dict[int, float] = {}
    for _k, e in sh.forward:
        same_lane = lane_of.get(e.source) == lane_of.get(e.target)
        if same_lane and rank.get(e.target, 0) == rank.get(e.source, 0) + 1:
            need = _chip_run_need(ctx, e, vertical_run=ax.flow == "down")
            if need:
                gap_need[rank[e.source]] = max(gap_need.get(rank[e.source], 0.0), need)
    cursor = ch.header_h
    rank_center: dict[int, float] = {}
    for r in ranks:
        extent = rank_extent.get(r, 0.0)
        rank_center[r] = cursor + extent / 2
        cursor += extent + max(gap, gap_need.get(r, 0.0))
    content_major_end = cursor - max(gap, gap_need.get(ranks[-1], 0.0) if ranks else 0.0)

    # ── Lane bands: stacked in declared order, thickness from content ────
    lane_members: dict[int, list[int]] = {b: [] for b in range(len(lanes))}
    for i, b in lane_of.items():
        lane_members[b].append(i)
    band_span: list[tuple[float, float]] = []
    minor_cursor = 0.0
    for b in range(len(lanes)):
        members = lane_members[b]
        content = max((ax.box_minor(*boxes[i]) for i in members), default=ch.node.h)
        all_terminal = bool(members) and all(spec.nodes[i].station == "terminal" for i in members)
        pad = pad_term if all_terminal else pad_y
        # A diamond overhangs into the pad rather than growing the band —
        # the specimen's Approve? rides its 160 lane with 22px air.
        card_content = max(
            (ax.box_minor(*boxes[i]) for i in members if spec.nodes[i].station != "decision"),
            default=content,
        )
        thickness = card_content + 2 * pad
        band_span.append((minor_cursor, minor_cursor + thickness))
        minor_cursor += thickness + gutter
    minor: dict[int, float] = {i: (band_span[b][0] + band_span[b][1]) / 2 for i, b in lane_of.items()}

    # ── Place ────────────────────────────────────────────────────────────
    all_min = min(lo for lo, _hi in band_span)
    all_max = max(hi for _lo, hi in band_span)
    minor_off = -(all_min - ch.margin_x)
    span_minor = (all_max - all_min) + 2 * ch.margin_x
    span_major = content_major_end + ch.footer_h
    width, height = (int(span_minor), int(span_major)) if ax.flow == "down" else (int(span_major), int(span_minor))
    placed: dict[int, NodePlacement] = {}
    for i, node in enumerate(spec.nodes):
        w, h = boxes[i]
        cxy = ax.point(rank_center[rank[i]], minor[i] + minor_off)
        pl = place_node(ctx, node, i, cxy[0], cxy[1], w=w, h=h, chassis_class=_chassis_cls(node, seat.get(i, "")))
        placed[i] = _partition_dress(node, pl)

    # ── Bands (screen boxes; the eyebrow rides the band's head corner) ───
    major_lo = min(rank_center[rank[i]] - ax.box_major(*boxes[i]) / 2 for i in boxes) - reach
    major_hi = max(rank_center[rank[i]] + ax.box_major(*boxes[i]) / 2 for i in boxes) + reach
    bands: list[LaneBand] = []
    for b, name in enumerate(lanes):
        lo, hi = band_span[b]
        p0 = ax.point(major_lo, lo + minor_off)
        p1 = ax.point(major_hi, hi + minor_off)
        box = RectSpec(
            x=min(p0[0], p1[0]),
            y=min(p0[1], p1[1]),
            w=abs(p1[0] - p0[0]),
            h=abs(p1[1] - p0[1]),
            rx=16.0,
        )
        label = name.upper()
        # The title sits CENTRED in its plate on both axes. It used to inset 6
        # from a plate padded 24, which is 6 left against 18 right, and to seat
        # its baseline 2px under the plate's middle where half a 10.5px ascent
        # is 3.9 — so the run read pushed up and to the left of its own chip.
        # Both pads are now the one pad, and the baseline derives.
        voice = ctx.cfg.scope_header_voice
        pad = 12.0
        plate_w = measure_voice(label, voice) + 2 * pad
        header_box = RectSpec(x=box.x + 6.0, y=box.y + 6.0, w=plate_w, h=20.0, rx=6.0)
        header = DiagramText(
            x=header_box.x + pad,
            y=centred_baseline(header_box.y + header_box.h / 2, voice, ctx.cfg),
            text=label,
            cls="eyeb",
            anchor="start",
        )
        bands.append(LaneBand(box=box, header=header, ground="panel", header_box=header_box))

    # ── Edges ────────────────────────────────────────────────────────────
    # Handoff columns (the forward crossings' descents) — the channel chip
    # avoids them by seating on its longest clear run.
    crossings: list[float] = []
    for _k, e in sh.forward:
        s_lane, t_lane = lane_of.get(e.source), lane_of.get(e.target)
        if s_lane is not None and t_lane is not None and s_lane != t_lane and rank[e.source] != rank[e.target]:
            p0f = _face_point(ax, placed[e.source], major_dir=1)
            crossings.append((p0f[1] if ax.flow == "down" else p0f[0]) + lane_hop)
    geos: list[EdgeGeo] = []
    for k, e in enumerate(ctx.edges):
        src_pl, tgt_pl = placed[e.source], placed[e.target]
        s_lane, t_lane = lane_of.get(e.source), lane_of.get(e.target)
        chip = bool(e.label and e.label_style == "chip")
        if e.circuit == "return" and s_lane is not None and t_lane is not None and s_lane != t_lane:
            geos.append(
                _channel_geo(
                    ax,
                    k,
                    src_pl,
                    tgt_pl,
                    band_span,
                    minor_off,
                    s_lane,
                    t_lane,
                    lane_r,
                    standoff,
                    crossings,
                    chip=chip,
                )
            )
        elif s_lane == t_lane or s_lane is None or t_lane is None:
            p0 = _face_point(ax, src_pl, major_dir=1)
            p1 = _stand(_face_point(ax, tgt_pl, major_dir=-1), ax, standoff, major_dir=-1)
            lp = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2) if chip else None
            geos.append(replace_tangent(_line(k, p0, p1, label_pos=lp), p0, p1))
        elif rank[e.source] == rank[e.target]:
            # The in-place drop: a cross-lane terminal descends at its
            # source's own major (Shipped under Approve?).
            sign = 1 if minor[e.target] > minor[e.source] else -1
            p0 = _face_point(ax, src_pl, major_dir=0, minor_dir=sign)
            p1 = _stand(_face_point(ax, tgt_pl, major_dir=0, minor_dir=-sign), ax, standoff, minor_dir=-sign)
            lp = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2) if chip else None
            geos.append(replace_tangent(_line(k, p0, p1, label_pos=lp), p0, p1))
        else:
            # The handoff crossing: along the flow to the fixed column
            # (source face + lane_hop), filleted down/up through the
            # gutter, arriving the target's near face — H-V-H exactly as
            # the specimen draws it, the chip on the descent.
            p0 = _face_point(ax, src_pl, major_dir=1)
            p1 = _stand(_face_point(ax, tgt_pl, major_dir=-1), ax, standoff, major_dir=-1)
            hand_major = (p0[1] if ax.flow == "down" else p0[0]) + lane_hop
            if ax.flow == "down":
                d, length, poly, tangent = orthogonal_d(
                    p0[0], p0[1], p1[0], p1[1], mid=hand_major, first_axis="v", r=lane_r
                )
                lp = ((p0[0] + p1[0]) / 2, hand_major) if chip else None
            else:
                d, length, poly, tangent = orthogonal_d(
                    p0[0], p0[1], p1[0], p1[1], mid=hand_major, first_axis="h", r=lane_r
                )
                lp = (hand_major, (p0[1] + p1[1]) / 2) if chip else None
            geos.append(
                EdgeGeo(
                    index=k,
                    d=d,
                    sx=p0[0],
                    sy=p0[1],
                    tx=p1[0],
                    ty=p1[1],
                    length=length,
                    polyline=poly,
                    end_tangent=tangent,
                    label_pos=lp,
                    label_bare=lp is not None,
                )
            )
    nodes_paint = [placed[i] for i in sorted(placed)]
    return finish_layout(
        ctx,
        width=width,
        height=height,
        nodes_paint=nodes_paint,
        geos=geos,
        lane_bands=tuple(bands),
        flow=ax.flow,
    )


def replace_tangent(geo: EdgeGeo, p0: tuple[float, float], p1: tuple[float, float]) -> EdgeGeo:
    from dataclasses import replace

    return replace(geo, end_tangent=_unit(p0, p1))


def _channel_geo(
    ax: AxisMap,
    k: int,
    src_pl: NodePlacement,
    tgt_pl: NodePlacement,
    band_span: list[tuple[float, float]],
    minor_off: float,
    s_lane: int,
    t_lane: int,
    lane_r: float,
    standoff: float,
    crossings: list[float],
    *,
    chip: bool,
) -> EdgeGeo:
    """The return channel: the gutter adjacent to the TARGET's lane, ridden
    at its own midline — out of the source's sky face, along the channel,
    up into the target's near face (V-H-V). The guard chip seats on the
    channel's LONGEST CLEAR RUN between the forward crossings, so the two
    directions' guards never collide however tight the columns."""
    toward = -1 if t_lane < s_lane else 1
    if toward < 0:
        gutter_lo = band_span[t_lane][1]
        gutter_hi = band_span[t_lane + 1][0]
    else:
        gutter_lo = band_span[t_lane - 1][1]
        gutter_hi = band_span[t_lane][0]
    channel = (gutter_lo + gutter_hi) / 2 + minor_off
    p0 = _face_point(ax, src_pl, major_dir=0, minor_dir=toward)
    p1 = _stand(_face_point(ax, tgt_pl, major_dir=0, minor_dir=-toward), ax, standoff, minor_dir=-toward)
    run_lo, run_hi = sorted((p0[1], p1[1]) if ax.flow == "down" else (p0[0], p1[0]))
    marks = sorted([run_lo, *[c for c in crossings if run_lo < c < run_hi], run_hi])
    seat_major = max(itertools.pairwise(marks), key=lambda ab: ab[1] - ab[0], default=(run_lo, run_hi))
    seat = (seat_major[0] + seat_major[1]) / 2
    if ax.flow == "down":
        d, length, poly, tangent = orthogonal_d(p0[0], p0[1], p1[0], p1[1], mid=channel, first_axis="h", r=lane_r)
        lp = (channel, seat) if chip else None
    else:
        d, length, poly, tangent = orthogonal_d(p0[0], p0[1], p1[0], p1[1], mid=channel, first_axis="v", r=lane_r)
        lp = (seat, channel) if chip else None
    return EdgeGeo(
        index=k,
        d=d,
        sx=p0[0],
        sy=p0[1],
        tx=p1[0],
        ty=p1[1],
        length=length,
        polyline=poly,
        end_tangent=tangent,
        label_pos=lp,
        label_bare=lp is not None,
    )
