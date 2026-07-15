"""Axial hub policy (§1.2, grammar-inventory/axial) — the semantic cross.

PARTITION: the plane splits into half-planes by ROLE — the hero sits on the
spine crossing; ``edit``-family satellites take the N axis, ``read`` the S
axis, ``in`` (compose) the W axis, and the ``out``/destination family fans
into the E half-plane from a gather point on the hero's east edge. Meaning
selects position before any label is parsed; PACK then solves pure geometry
inside each half-plane (axis offsets, fan pitch, tangent curves).

PACK follows the confirmed riders:

* Tangent beziers — control points derive from the spatial-notes rule
  (|dx| or |dy| ~= 0.5 of the leg at the tangent point); no free fitting.
* Gather-fan (§11.4c) — destinations bundle to an explicit gather point on
  the nucleus east boundary (hub measured: gather AT the boundary; the
  ``gather_dx`` knob floats it for genomes that want a visible stub).
* Nucleus prominence (§11.4a) — the hero's box grows to the class factor
  measured from the specimen (264x100 hero vs 220x64 satellites ~= 1.9);
  a ledger number in the ``axial:`` engine block, never a guess.
* Per-role dress (P5) — the solver assigns relation DEFAULTS from the idiom
  registry vocabulary (in→assert, edit→assert, read→drift, destinations→
  assert on an accent-bound stroke); an explicit ``edge.relation`` wins.
  Particles never ride accent strokes (the ``invisible-riders`` rule —
  enforced in wiring, declared here via ``accent_wire``).

Role→axis is data-shaped but closed (the semantic cross is the class);
slot assignment is role-priority then declaration order (§11.5b) — never
input-dict order. Everything metric — axis gaps, fan reach/pitch, the
prominence factor — reads from the ``axial:`` engine block.
"""

from __future__ import annotations

import itertools
import math
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.annotate import Region
from hyperweave.compose.diagram.chrome import place_node, style_of
from hyperweave.compose.diagram.motion import lane_endpoints
from hyperweave.compose.diagram.paths import fmt
from hyperweave.compose.diagram.route import route_path
from hyperweave.compose.diagram.sizing import solve_node_box
from hyperweave.compose.diagram.solver import finish_layout
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
from hyperweave.core.diagram import DiagramCapacityError, NodeStyle

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hyperweave.compose.diagram.records import DiagramLayout, LaneBand, NodePlacement
    from hyperweave.core.diagram import DiagramNode

# Role → axis assignment, in PRIORITY order (§11.5b: role-priority, then
# declaration order). Axes are the semantic half-planes of the cross.
_AXIS_OF: dict[str, str] = {
    "edit": "N",  # asserting operations above the spine
    "out": "E",  # the destination fan half-plane
    "in": "W",  # compose enters from the west
    "read": "S",  # observations below
}

# Per-axis relation defaults (P5) — idiom-registry vocabulary, consumed by
# wiring via EdgeGeo.relation_default. The E fan additionally binds the
# accent to the stroke itself (§11.4b role-bound accent).
_RELATION_OF_AXIS: dict[str, str] = {"N": "assert", "E": "assert", "W": "assert", "S": "drift"}


def spoke_role(ctx: SolverContext, member: int) -> str:
    """The member's semantic role from its first hub-incident edge."""
    for e in ctx.edges:
        if e.source == 0 and e.target == member:
            return e.role or "out"
        if e.target == 0 and e.source == member:
            return e.role or "in"
    return "out"


def partition_axial(ctx: SolverContext) -> dict[str, list[int]]:
    """PARTITION: members → half-planes by role. Deterministic — role
    priority (edit, out, in, read) then declaration order."""
    by_axis: dict[str, list[int]] = {axis: [] for axis in ("N", "E", "W", "S")}
    for m in range(1, len(ctx.spec.nodes)):
        by_axis[_AXIS_OF.get(spoke_role(ctx, m), "E")].append(m)
    return by_axis


def tangent_bezier(
    sx: float, sy: float, tx: float, ty: float, *, horizontal_exit: bool
) -> tuple[str, float, tuple[tuple[float, float], ...]]:
    """A tangent bezier per the spatial-notes rule: the curve leaves and
    arrives axis-tangent, with each control point placed at ~=0.5 of the leg
    along the tangent axis. Returns (d, approx_length, sampled polyline) —
    the polyline feeds the annotate obstacle set (curves are obstacles too,
    the bug-e contract)."""
    if horizontal_exit:
        c1x, c1y = sx + (tx - sx) * 0.5, sy
        c2x, c2y = tx - (tx - sx) * 0.5, ty
    else:
        c1x, c1y = sx, sy + (ty - sy) * 0.5
        c2x, c2y = tx, ty - (ty - sy) * 0.5
    d = f"M {fmt(sx)},{fmt(sy)} C {fmt(c1x)},{fmt(c1y)} {fmt(c2x)},{fmt(c2y)} {fmt(tx)},{fmt(ty)}"
    samples: list[tuple[float, float]] = []
    for k in range(9):
        t = k / 8.0
        u = 1.0 - t
        px = u * u * u * sx + 3 * u * u * t * c1x + 3 * u * t * t * c2x + t * t * t * tx
        py = u * u * u * sy + 3 * u * u * t * c1y + 3 * u * t * t * c2y + t * t * t * ty
        samples.append((px, py))
    length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in itertools.pairwise(samples))
    return d, length, tuple(samples)


def _axial_cfg(ctx: SolverContext) -> Mapping[str, Any]:
    """The frame axial config, with any per-spec override (spec.axial) merged
    on top — sibling axial diagrams tune prominence / satellite width without
    forking the shared frame config."""
    base: dict[str, Any] = dict(ctx.engine.get("axial") or {})
    if ctx.spec.axial:
        base.update(ctx.spec.axial)
    return base


def _axis_boxes(ctx: SolverContext, by_axis: dict[str, list[int]]) -> dict[str, tuple[float, float]]:
    """Per-AXIS content-solved (w, h): each half-plane's cards share ONE box so
    a column reads aligned, but a chip-heavy card on one axis is NOT forced onto
    the others — hub's read card is 340 wide while spec/transform
    stay ~210. Returns ``{axis: (w, h)}``; an empty axis gets the node floor."""
    ch = ctx.ch
    cfg = _axial_cfg(ctx)
    # Snug-width ruling: satellites content-solve; the retired
    # satellite_min_w floor inflated every S-rank card (extract carried
    # +54px of pin slack right of its anchored text). Heights keep the
    # family floor.
    floor_h = float(cfg.get("satellite_min_h", ch.node.h))
    # The cross gives its satellites a WIDER ceiling than the compass ring
    # (the read chip-card seats four chips at ~340); scope it to the axial
    # solve so a compass hub's cards keep the tighter shared w_max. Only the
    # CARD path reads it (``topo_chassis``) — pill/circle members ignore
    # topology chassis entirely, so the override is harmless there.
    ch_axial = ch.model_copy(update={"w_max": float(cfg.get("satellite_max_w", ch.w_max or ch.node.w))})
    out: dict[str, tuple[float, float]] = {}
    for axis in ("N", "E", "W", "S"):
        w, h = 0.0, floor_h
        for m in by_axis.get(axis, ()):
            # Satellites are never hero — pinned, matching the original's
            # role-blind ``ch.node``/``ch.circle_r`` picks (hero=False is
            # also the seam's own default here, since no caller passes it).
            bw, bh, _ = solve_node_box(ctx, ctx.spec.nodes[m], m, hero=False, topo_chassis=ch_axial)
            w = max(w, bw)
            h = max(h, bh)
        out[axis] = (w, h)
    return out


def _hero_box(ctx: SolverContext, sat_w: float, sat_h: float, factor: float) -> tuple[float, float]:
    """Nucleus box under the snug-width ruling: the crown solves to its OWN
    content; ``hero.w``/``hero.h`` citations bound growth as ceilings /
    height floors inside the sizing seam. The retired "prominence" formula
    grew the crown toward ``factor x satellite_area`` — a non-content
    inflator that left the verb-algebra crowns with up to 87px of dead band
    right of their anchored text. ``sat_w``/``sat_h``/``factor`` are kept in
    the signature for the engine-config seam but no longer move geometry."""
    del sat_w, sat_h, factor
    cw, chh, _ = solve_node_box(ctx, ctx.spec.nodes[0], 0, hero=True)
    return cw, chh


def _place(
    ctx: SolverContext,
    i: int,
    node: DiagramNode,
    cx: float,
    cy: float,
    w: float,
    h: float,
    *,
    force_card: bool = False,
) -> NodePlacement:
    # The NUCLEUS is ALWAYS force_card=True, DELIBERATELY, regardless of its
    # resolved style: its box IS the geometry the gather point and every axis
    # endpoint (N/S/W legs, the E fan's tangent beziers) are solved against
    # in ``_axial_edges`` — a glyph-circle or pill nucleus would draw a small
    # disc/capsule while the connectors were solved against a rectangular
    # prominence box, floating every arrival off the shape (the
    # arrows-float-in-space defect). This is a hard geometry constraint, not
    # a style preference — do not remove force_card from the nucleus call
    # site. Satellites (force_card=False) keep their full declared anatomy,
    # and — like every other topology's ring/rank members — are NEVER hero
    # regardless of role (pinned, matching the original's role-blind
    # ``ch.node``/``ch.circle_r`` for the satellite branches below).
    style = style_of(node, ctx.spec, ctx.ch)
    if not force_card and style == NodeStyle.GLYPH_CIRCLE.value:
        d = 2 * ctx.ch.circle_r
        return place_node(ctx, node, i, cx, cy, w=d, h=d, hero=False)
    # The nucleus uses the HERO chassis (its own pads + max_desc_lines=2, so
    # the subtitle can wrap to two lines) and an UNCONDITIONAL glyph — a
    # declared glyph rides it as a card+glyph mark even when the spec asked
    # for glyph-circle. Satellites use the plain node chassis (hero=False).
    return place_node(
        ctx,
        node,
        i,
        cx,
        cy,
        w=w,
        h=h,
        hero=force_card,
        force_card=force_card,
        glyph_unconditional=force_card,
    )


def solve_axial(ctx: SolverContext) -> DiagramLayout:
    """PACK for the axial policy: hero on the spine crossing, N/S columns at
    axis_gap and the W column at its own w_axis_gap from the hero boundary,
    the E destination fan on tangent beziers from the gather point. Every
    N/S/W satellite CENTERS on the spine — the hub specimen's own N/S
    connectors are dead-vertical L commands (``M 620,350 L 620,184``,
    ``M 620,470 L 620,634``) with the card centered under each endpoint, so
    no axis solves an off-spine offset for a single satellite (a genuinely
    off-spine multi-member rank, e.g. verb-reads' S row, is the documented
    exception — see ``s_rank_tilt_dx``). All coordinates start hero-centered
    at (0,0) and shift to canvas space once extents are known."""
    ch = ctx.ch
    spec = ctx.spec
    caps = ctx.engine.get("caps") or {}
    cfg = _axial_cfg(ctx)
    axis_gap = float(cfg.get("axis_gap", 96))
    # W's own reach: the hub specimen's W throw (measured to the rendered
    # NAME TEXT, hub_seats' own reference point) does not close on the
    # shared N/S axis_gap once satellites content-solve to the family's
    # narrower ink-bound boxes (a bare axis_gap floors W ~100px short). W's
    # reach is a straight-line extension along its own connector axis, so
    # widening it never bends anything — unlike N/S, where the connector
    # runs perpendicular to any x-nudge (see the note on hub_seats' own
    # hub_seats_superseded fixture amendment for why N/S stay un-nudged).
    # Falls back to axis_gap when unset, so a sibling axial spec that never
    # tunes it renders byte-identically.
    w_axis_gap = float(cfg.get("w_axis_gap", axis_gap))
    fan_reach = float(cfg.get("fan_reach", 112))
    fan_pitch = float(cfg.get("fan_pitch", 120))
    gather_dx = float(cfg.get("gather_dx", 0))
    factor = float(cfg.get("prominence_factor", 1.9))
    max_fan = int(cfg.get("max_fan", 8))
    # A sole N/S satellite's card centers ON the spine (x=0) — no x-nudge:
    # the hub specimen's own N/S connectors are dead-vertical L commands
    # (``M 620,350 L 620,184``, ``M 620,470 L 620,634``), which only holds if
    # the card sits directly under the hero edge. The specimen's measured
    # off-axis NAME-TEXT lean (hub_seats' own reference point) comes entirely
    # from the satellite's icon+left-aligned text sitting left of card-center
    # — real, but shallower at the engine's narrower ink-bound cards than the
    # specimen's now-superseded wide-floor cards produced (see hub.json's
    # ``hub_seats_superseded``). A card-position nudge previously closed that
    # gap here, but it necessarily un-verticals the connector along with it
    # (the endpoint IS the card's own edge) — do not reintroduce one; amend
    # the fixture target instead, the same way the card-dims law already
    # amends past this specimen's own superseded card family.
    # Per-axis satellite cap: the compass default is 3, but the axial cross can
    # seat a wider read/write ROW on an axis (verb-reads's four read verbs share
    # the S rank) — a per-spec override lifts it without touching the compass.
    per_axis = int(cfg.get("max_per_axis", caps.get("hub_max_per_zone", 3)))

    by_axis = partition_axial(ctx)
    for axis in ("N", "W", "S"):
        if len(by_axis[axis]) > per_axis:
            raise DiagramCapacityError(
                f"axial caps at {per_axis} satellites per axis ({axis} has {len(by_axis[axis])})"
            )
    if len(by_axis["E"]) > max_fan:
        raise DiagramCapacityError(f"axial destination fan caps at {max_fan} (E has {len(by_axis['E'])})")

    axis_box = _axis_boxes(ctx, by_axis)
    axis_of_member = {m: a for a, ms in by_axis.items() for m in ms}
    box_of = {m: axis_box[axis_of_member[m]] for m in axis_of_member}
    # Prominence ref: the largest REGULAR (chip-free) axis box — a chip-card is
    # a content outlier the nucleus must not be scaled against (else the read
    # card's 340 width would inflate the hero past the specimen ledger).
    reg = [axis_box[a] for a in by_axis if by_axis[a] and all(not spec.nodes[m].chips for m in by_axis[a])]
    ref_w, ref_h = max(reg or list(axis_box.values()), key=lambda wh: wh[0] * wh[1])
    hero_w, hero_h = _hero_box(ctx, ref_w, ref_h, factor)

    # Hero-centered satellite centers per half-plane, using each AXIS's own box
    # so the wide read card sits below without pushing N/W/E outward. N/S
    # multiples spread ACROSS the spine in a single rank; W and the E fan are
    # columns centered on the spine.
    w_n, h_n = axis_box["N"]
    w_s, h_s = axis_box["S"]
    w_w, h_w = axis_box["W"]
    w_e, h_e = axis_box["E"]
    centers: dict[int, tuple[float, float]] = {}
    kn = len(by_axis["N"])
    for k, m in enumerate(by_axis["N"]):
        centers[m] = ((k - (kn - 1) / 2.0) * (w_n + 24.0), -(hero_h / 2 + axis_gap + h_n / 2))
    ks = len(by_axis["S"])
    # A multi-member S rank (verb-reads' four-wide read row) is a DIFFERENT
    # composition from a sole-satellite S — a wide rank reads balanced only
    # at its own reach and pitch, not axis_gap's sole-satellite one, and its
    # connectors already curve (ns_rank in _axial_edges), so a rank-wide lean
    # never un-verticals a straight spoke the way a sole satellite's would.
    # s_rank_tilt_dx is that rank's own lean: a wide rank's per-member
    # label/icon widths vary enough that no single member's incidental
    # text-offset represents the whole row, so the row leans as a unit.
    # Defaults to 0.0 and is a no-op for ks == 1 (the (k-(ks-1)/2) term is 0
    # regardless of pitch/tilt when there is only one member).
    s_rank_gap = float(cfg.get("s_rank_axis_gap", axis_gap))
    # Angle-family construction (edge-run law, polar case): the hand file
    # cites the fan's SPREAD-TO-DROP ratio, never absolute seats — pitch
    # derives from the cited face-to-face gap (``s_rank_spread_ratio`` x
    # ``s_rank_axis_gap``), so any card-width change re-derives the same
    # even fan about the port. The retired absolute pitch/tilt pins were
    # fitted to one render's card widths and left the fan lopsided the
    # moment those widths changed (the snug-width wave's near-horizontal
    # leftmost spoke). Legacy absolute pins still read for specs that
    # declare them.
    ratio = float(cfg.get("s_rank_spread_ratio", 0.0))
    s_rank_pitch = ratio * s_rank_gap if ratio else float(cfg.get("s_rank_pitch", w_s + 24.0))
    s_rank_tilt = float(cfg.get("s_rank_tilt_dx", 0.0)) if ks > 1 else 0.0
    for k, m in enumerate(by_axis["S"]):
        centers[m] = (
            (k - (ks - 1) / 2.0) * s_rank_pitch + s_rank_tilt,
            (hero_h / 2 + s_rank_gap + h_s / 2),
        )
    kw = len(by_axis["W"])
    for k, m in enumerate(by_axis["W"]):
        centers[m] = (-(hero_w / 2 + w_axis_gap + w_w / 2), (k - (kw - 1) / 2.0) * (h_w + 24.0))
    ke = len(by_axis["E"])
    e_pitch = max(h_e + 24.0, fan_pitch)
    for k, m in enumerate(by_axis["E"]):
        centers[m] = (hero_w / 2 + fan_reach + w_e / 2, (k - (ke - 1) / 2.0) * e_pitch)

    # Canvas fits the content (R3): bbox all boxes, then chrome bands.
    ext_x = [-hero_w / 2, hero_w / 2]
    ext_y = [-hero_h / 2, hero_h / 2]
    for m, (x, y) in centers.items():
        bw, bh = box_of[m]
        ext_x += [x - bw / 2, x + bw / 2]
        ext_y += [y - bh / 2, y + bh / 2]
    min_x, max_x = min(ext_x), max(ext_x)
    min_y, max_y = min(ext_y), max(ext_y)
    cx = ch.margin_x - min_x
    cy = ch.header_h - min_y
    width = math.ceil(cx + max_x + ch.margin_x)
    height = math.ceil(cy + max_y + ch.footer_h)

    placed: dict[int, NodePlacement] = {
        m: _place(ctx, m, spec.nodes[m], cx + x, cy + y, box_of[m][0], box_of[m][1]) for m, (x, y) in centers.items()
    }
    hero = _place(ctx, 0, spec.nodes[0], cx, cy, hero_w, hero_h, force_card=True)

    geos = _axial_edges(ctx, axis_of_member, by_axis, centers, cx, cy, hero_w, hero_h, box_of, gather_dx)

    # Regions: one frame per occupied half-plane (zone:N|E|S|W) — caller
    # annotations keep the compass vocabulary.
    regions: dict[str, Region] = {}
    for axis, ms in by_axis.items():
        if not ms:
            continue
        aw, ah = axis_box[axis]
        xs = [centers[m][0] for m in ms]
        ys = [centers[m][1] for m in ms]
        regions[f"zone:{axis}"] = Region(
            x=cx + min(xs) - aw / 2,
            y=cy + min(ys) - ah / 2,
            w=(max(xs) - min(xs)) + aw,
            h=(max(ys) - min(ys)) + ah,
        )

    # P9 zone headers: 'corners' stamps each occupied half-plane's role
    # family at the zone corner (header-only typographic bands — the S1
    # lane-header furniture generalized). Default none; the caption chrome
    # mode carries the split in prose instead.
    # Corner group headers ride the solver's ONE zone-header law now —
    # the preset carries the words (Invariant 5); nothing is authored here.
    bands: tuple[LaneBand, ...] = ()

    # Paint order: satellites first, nucleus LAST (the emanation mask).
    paint = [placed[m] for m in sorted(placed)] + [hero]
    return finish_layout(
        ctx,
        width=width,
        height=height,
        nodes_paint=paint,
        geos=geos,
        extra_regions=regions,
        lane_bands=bands,
    )


def _axial_edges(
    ctx: SolverContext,
    axis_of_member: Mapping[int, str],
    by_axis: Mapping[str, list[int]],
    centers: Mapping[int, tuple[float, float]],
    cx: float,
    cy: float,
    hero_w: float,
    hero_h: float,
    box_of: Mapping[int, tuple[float, float]],
    gather_dx: float,
) -> list[EdgeGeo]:
    """One geo per edge, dressed by axis. N/S/W run straight on their axis;
    a MULTI-member off-spine N/S rank or W column curves tangent into the
    hero's edge instead (verb-reads' 4-wide S rank, pp-radial's read row —
    kn/ks or kw > 1). A SOLE N/S satellite is always spine-centered, so its
    edge is always the straight branch too — the hub specimen's own
    transform/read spokes run dead straight (``M 620,350 L 620,184``,
    ``M 620,470 L 620,634``, zero x-delta); the specimen's measured
    NAME-TEXT lean (``hub_seats()``'s reference point) comes from the card's
    own icon+text layout, never from shifting the card off the spine. The E
    fan leaves the gather point on tangent beziers. Every geo carries its
    axis relation default and the fan binds the accent to the stroke. Each
    satellite edge touches its OWN box (per-axis sizing)."""
    geos: list[EdgeGeo] = []
    gx, gy = cx + hero_w / 2 + gather_dx, cy
    ns_rank = {axis: len(by_axis.get(axis, ())) > 1 for axis in ("N", "S")}
    for j, edge in enumerate(ctx.edges):
        member = edge.target if edge.source == 0 else edge.source
        axis = axis_of_member.get(member, "E")
        mx, my = centers[member]
        mx, my = cx + mx, cy + my
        mw, mh = box_of[member]
        relation = _RELATION_OF_AXIS[axis]
        if axis == "E":
            # hero east boundary -> gather -> tangent bezier into the
            # destination's west edge. Terminal arrives axis-tangent (P8).
            tx, ty = mx - mw / 2, my
            bez_d, bez_len, poly = tangent_bezier(gx, gy, tx, ty, horizontal_exit=True)
            hx, hy = cx + hero_w / 2, cy
            if gather_dx > 0:
                d = f"M {fmt(hx)},{fmt(hy)} L{bez_d[1:]}"
                length = gather_dx + bez_len
                poly = ((hx, hy), *poly)
            else:
                d, length = bez_d, bez_len
            geos.append(
                EdgeGeo(
                    index=j,
                    d=d,
                    sx=hx,
                    sy=hy,
                    tx=tx,
                    ty=ty,
                    length=length,
                    polyline=poly,
                    end_tangent=(1.0, 0.0),
                    relation_default=relation,
                    # The destination fan binds the accent to a SOLID rail by
                    # default (hub); an edge that EXPLICITLY drifts
                    # releases it (axial's all-drift cross — every spoke is a
                    # dotted rail, no solid accent).
                    accent_wire=edge.relation != "drift",
                )
            )
            continue
        if axis == "N":
            hx, hy = cx, cy - hero_h / 2
            ex, ey = mx, my + mh / 2
        elif axis == "S":
            hx, hy = cx, cy + hero_h / 2
            ex, ey = mx, my - mh / 2
        else:  # W
            hx, hy = cx - hero_w / 2, cy
            ex, ey = mx + mw / 2, my
        if edge.source == 0:
            sx, sy, tx, ty = hx, hy, ex, ey
        else:
            sx, sy, tx, ty = ex, ey, hx, hy
        sx, sy, tx, ty = lane_endpoints(sx, sy, tx, ty, ctx.lanes[j], ctx.lane_offsets[j])
        if axis == "W" and abs(sy - ty) > 0.5:
            # Off-spine W satellite: tangent curve into the hero west edge.
            d, length, poly = tangent_bezier(sx, sy, tx, ty, horizontal_exit=True)
            tangent = (1.0, 0.0) if tx > sx else (-1.0, 0.0)
        elif axis in ("N", "S") and ns_rank[axis] and abs(sx - tx) > 0.5:
            # Off-spine RANK member only (kn/ks > 1): tangent curve, vertical
            # exit/arrival. A sole satellite never qualifies (ns_rank gates
            # it out, and it never carries an off-spine x anyway) — it draws
            # the dead-straight branch below.
            d, length, poly = tangent_bezier(sx, sy, tx, ty, horizontal_exit=False)
            tangent = (0.0, 1.0) if ty > sy else (0.0, -1.0)
        else:
            d, length, poly, tangent = route_path(sx, sy, tx, ty, style="straight")
        geos.append(
            EdgeGeo(
                index=j,
                d=d,
                sx=sx,
                sy=sy,
                tx=tx,
                ty=ty,
                length=length,
                polyline=poly,
                end_tangent=tangent,
                relation_default=relation,
            )
        )
    return geos
