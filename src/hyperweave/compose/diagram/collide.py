"""Deterministic anti-collision for subsumed edge labels and legends.

Given the preferred boxes and the static obstacles (node boxes, connector
polylines, lane-band strips), this module nudges each label/legend onto the
first candidate position that overlaps nothing. It is pure geometry — no
randomness, no meaning — so the same input yields byte-identical output (the
determinism pin). A box that exhausts its ladder keeps its preferred position
and appends a warning — never a crash, never a silent drop, and never an
ellipsis: annotations do not truncate to fit (the wrap already sized every
line; ``place.py`` grows the canvas rather than shrinking the text).

The candidate ladder per box: the preferred position, then the mirrored side
(for an edge label: the opposite perpendicular side plus a start↔end anchor
flip — THE fix for two transition labels colliding above a state machine),
then slides along the underlying polyline at the YAML ``candidate_slides``
fractions, then outward pushes in ``push_step`` increments up to ``push_max``.
Labels resolve FIRST, against the static obstacles only (``resolve_labels``);
the caller free-text kinds are positioned in a clear zone by ``place.py`` and
join the obstacle set before the region-packed legends settle
(``resolve_generic``) — so the whole pass is total-order stable.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hyperweave.compose.diagram.records import AnnotationPlacement, DiagramText
    from hyperweave.compose.diagram.wiring import EdgeGeo
    from hyperweave.compose.spatial_records import RectSpec
    from hyperweave.core.diagram import ResolvedEdge


@dataclass(frozen=True, slots=True)
class Obstacle:
    """A rectangular no-go region tagged with the graph element it came from.

    ``kind`` is 'node' | 'edge' | 'furniture'; ``ref`` is the node index (node
    obstacles) or logical edge index (edge-polyline obstacles), -1 for
    furniture. The tag lets a subsumed edge label EXCLUDE its own incident
    nodes and its own wire — a label authored to sit beside its edge must not
    collide-avoid the very edge and endpoints it labels, only foreign
    geometry and other annotations (which is what keeps the parity pins)."""

    box: RectSpec
    kind: str = "furniture"
    ref: int = -1


def _rect_overlap(a: RectSpec, b: RectSpec) -> float:
    """The intersection AREA of two rects (0 = disjoint or edge-touching)."""
    ix = max(0.0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    iy = max(0.0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    return ix * iy


def _inflate(box: RectSpec, margin: float) -> RectSpec:
    return replace(box, x=box.x - margin, y=box.y - margin, w=box.w + 2 * margin, h=box.h + 2 * margin)


def _total_overlap(box: RectSpec, obstacles: list[Obstacle], *, text_margin: float = 0.0) -> float:
    """Total intersection area against every obstacle. ``text_margin``
    inflates the check against LABEL-kind obstacles only (a placed label
    joining the working set — see ``resolve_labels``): node/edge/furniture
    obstacles already carry their own clearance pad where it matters
    (``annotate.py``'s ``_static_obstacles`` inflates node boxes by half
    ``min_clearance``), so inflating them again here would double-count and
    risk moving byte-pinned placements that were never the crowding
    problem. A bare zero-overlap check let two micro-labels crowd to a
    hairline gap (the ``revise``/``error`` reads); this is the minimum-
    margin fix, scoped to the ONE obstacle kind it's meant for."""
    total = 0.0
    for o in obstacles:
        ob = _inflate(o.box, text_margin) if (text_margin and o.kind == "label") else o.box
        total += _rect_overlap(box, ob)
    return total


def _seg_rect_cross(x1: float, y1: float, x2: float, y2: float, box: RectSpec) -> bool:
    """Does the segment (x1,y1)->(x2,y2) intersect the box's interior?
    Liang-Barsky slab clip against the AABB."""
    rx0, ry0, rx1, ry1 = box.x, box.y, box.x + box.w, box.y + box.h
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - rx0), (dx, rx1 - x1), (-dy, y1 - ry0), (dy, ry1 - y1)):
        if p == 0.0:
            if q < 0.0:
                return False
        else:
            t = q / p
            if p < 0.0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    return t0 <= t1


def _wire_through_box(box: RectSpec, geo: EdgeGeo | None) -> bool:
    """Does the label's OWN wire pass through the box interior? The own-wire
    exclusion is correct for the perp-lifted anchor (beside its wire) and for a
    chip grounded ON its wire — both short-circuit before the ladder. But it
    must not let a RELOCATING push land a micro-label across the very line it
    labels: a label nudged to dodge foreign furniture could cross its own wire
    (model-gateway telemetry). Only ladder candidates reach here, so a True is
    always an illegitimate crossing, never the legitimate anchor/chip seat."""
    if geo is None:
        return False
    poly = geo.polyline or ((geo.sx, geo.sy), (geo.tx, geo.ty))
    segs = itertools.pairwise(poly)
    return any(_seg_rect_cross(x1, y1, x2, y2, box) for (x1, y1), (x2, y2) in segs)


def _band_border_crossed(box: RectSpec, band: RectSpec, clear: float = 0.0) -> bool:
    """Does ``box`` sit within ``clear`` px of ``band``'s OUTLINE (its four
    perimeter segments, never the filled interior — a chip fully inside or
    fully outside a region band is fine; straddling the hairline border is
    the defect: gateway-balanced's telemetry chip crossing the MODEL POOL
    band's bottom edge). ``box`` is padded by ``clear`` before the segment
    test so the clear-seat ladder stops at a real gap, not a bare touch —
    the specimen's own telemetry chip sits 20px clear of the boundary
    (region_band.band_chip_clearance), not merely off it."""
    x0, y0, x1, y1 = box.x - clear, box.y - clear, box.x + box.w + clear, box.y + box.h + clear
    padded = replace(box, x=x0, y=y0, w=x1 - x0, h=y1 - y0)
    bx0, by0, bx1, by1 = band.x, band.y, band.x + band.w, band.y + band.h
    perimeter = (
        ((bx0, by0), (bx1, by0)),  # top
        ((bx1, by0), (bx1, by1)),  # right
        ((bx1, by1), (bx0, by1)),  # bottom
        ((bx0, by1), (bx0, by0)),  # left
    )
    return any(_seg_rect_cross(x1s, y1s, x2s, y2s, padded) for (x1s, y1s), (x2s, y2s) in perimeter)


def _translate(box: RectSpec, dx: float, dy: float) -> RectSpec:
    return replace(box, x=box.x + dx, y=box.y + dy)


def _shift_placement(p: AnnotationPlacement, dx: float, dy: float) -> AnnotationPlacement:
    """Move a whole placement — its box, text runs, dot, and legend entries —
    by (dx, dy). Pure translation keeps every sub-part coherent. A callout's
    leader is DROPPED on a move: its box-side endpoint would shift while the
    anchor endpoint stays pinned to the graph, so the annotate pass's clean
    hairline no longer holds; a moved callout reads by proximity (a short push
    rarely needed the leader). The common case — a callout placed clean on its
    first try — keeps its leader untouched."""
    box = _translate(p.box, dx, dy) if p.box is not None else None
    lines = tuple(replace(t, x=t.x + dx, y=t.y + dy) for t in p.lines)
    dot = (p.dot[0] + dx, p.dot[1] + dy) if p.dot is not None else None
    entries = tuple(
        replace(
            e,
            swatch_x=e.swatch_x + dx,
            swatch_y=e.swatch_y + dy,
            text=replace(e.text, x=e.text.x + dx, y=e.text.y + dy),
        )
        for e in p.entries
    )
    return replace(p, box=box, lines=lines, dot=dot, leader="", entries=entries)


def _mirror_label(p: AnnotationPlacement, geo: EdgeGeo | None) -> AnnotationPlacement | None:
    """Flip an edge label to the opposite side of its wire and swap the
    horizontal anchor — the collision fix for two labels stacked above a state
    machine. Mirrors the box across the wire's midline: for a middle-anchored
    label above a horizontal wire, drop it below; for a start-anchored label,
    flip to end on the other side. Returns None when there is no geo to mirror
    across (the label keeps sliding instead)."""
    if geo is None or not p.lines:
        return None
    # Mirror vertically across the wire midpoint y for horizontal-ish wires,
    # horizontally for vertical-ish wires — chosen by the geo's dominant axis.
    poly = geo.polyline or ((geo.sx, geo.sy), (geo.tx, geo.ty))
    dx = abs(poly[-1][0] - poly[0][0])
    dy = abs(poly[-1][1] - poly[0][1])
    if dx >= dy:
        # Horizontal wire: reflect the box's y across the wire's midline y.
        wire_y = (geo.sy + geo.ty) / 2
        if p.box is None:
            return None
        new_top = 2 * wire_y - (p.box.y + p.box.h)
        shift_y = new_top - p.box.y
        return _shift_placement(p, 0.0, shift_y)
    # Vertical wire: reflect x across the wire midline and flip the anchor.
    wire_x = (geo.sx + geo.tx) / 2
    if p.box is None:
        return None
    new_left = 2 * wire_x - (p.box.x + p.box.w)
    shift_x = new_left - p.box.x
    flipped = _shift_placement(p, shift_x, 0.0)
    lines = tuple(_flip_anchor(t, wire_x) for t in flipped.lines)
    return replace(flipped, lines=lines)


def _flip_anchor(t: DiagramText, axis_x: float) -> DiagramText:
    """Swap start↔end anchor and reflect the run's x across ``axis_x`` so the
    text reads on the mirrored side without re-measuring."""
    if t.anchor == "start":
        return replace(t, anchor="end", x=2 * axis_x - t.x)
    if t.anchor == "end":
        return replace(t, anchor="start", x=2 * axis_x - t.x)
    return replace(t, x=2 * axis_x - t.x)


def _slide_candidates(
    p: AnnotationPlacement,
    geo: EdgeGeo | None,
    slides: list[float],
) -> list[AnnotationPlacement]:
    """Slide the box to fractional positions along the underlying polyline. The
    box keeps its shape and its offset from the wire; only the along-wire
    position changes. Falls back to no candidates when there is no geo."""
    if geo is None or p.box is None:
        return []
    poly = geo.polyline or ((geo.sx, geo.sy), (geo.tx, geo.ty))
    start, end = poly[0], poly[-1]
    # Current along-wire position of the box center (fraction 0.5 was the
    # midpoint anchor). We translate to each requested fraction.
    cur_cx = p.box.x + p.box.w / 2
    cur_cy = p.box.y + p.box.h / 2
    out: list[AnnotationPlacement] = []
    for f in slides:
        tx = start[0] + (end[0] - start[0]) * f
        ty = start[1] + (end[1] - start[1]) * f
        # Keep the perpendicular offset the box already has by moving only along
        # the wire direction: project the delta onto the wire axis.
        out.append(_shift_placement(p, tx - cur_cx, ty - cur_cy))
    return out


def _push_candidates(
    p: AnnotationPlacement,
    push_step: float,
    push_max: float,
) -> list[AnnotationPlacement]:
    """Outward nudges in the four cardinal directions, growing by push_step up
    to push_max — the last resort before re-wrap. Up first (labels prefer to
    rise), then down, left, right, at each magnitude."""
    out: list[AnnotationPlacement] = []
    steps = int(push_max // push_step)
    for k in range(1, steps + 1):
        mag = k * push_step
        for dx, dy in ((0.0, -mag), (0.0, mag), (-mag, 0.0), (mag, 0.0)):
            out.append(_shift_placement(p, dx, dy))
    return out


def _clear_own_incident(
    p: AnnotationPlacement,
    obstacles: list[Obstacle],
    incident_obstacles: list[Obstacle],
    geo: EdgeGeo | None,
    slides: list[float],
    text_margin: float,
) -> AnnotationPlacement:
    """The incident-node exclusion in ``resolve_labels`` below (a label never
    collision-avoids its OWN endpoints — the authored position beside its
    own edge is never a false collision, by design) hides a REAL overlap
    from ``_resolve_one``'s main ladder: a candidate chosen to dodge a
    FOREIGN obstacle can still land on the label's own incident node, since
    that node was never in the set the ladder checked. Slide further along
    the SAME wire (the ladder's own tool, never a push off it) until the
    seat clears its own node too, without reopening a foreign collision the
    main ladder already resolved (the residual check against ``obstacles``,
    margin included)."""
    if p.box is None or not incident_obstacles or geo is None:
        return p
    if _total_overlap(p.box, incident_obstacles) == 0.0:
        return p
    for cand in _slide_candidates(p, geo, slides):
        if (
            cand.box is not None
            and _total_overlap(cand.box, incident_obstacles) == 0.0
            and _total_overlap(cand.box, obstacles, text_margin=text_margin) == 0.0
            and not _wire_through_box(cand.box, geo)
        ):
            return cand
    return p


def _resolve_one(
    p: AnnotationPlacement,
    obstacles: list[Obstacle],
    *,
    geo: EdgeGeo | None,
    slides: list[float],
    push_step: float,
    push_max: float,
    text_margin: float = 0.0,
    incident_obstacles: list[Obstacle] | None = None,
) -> tuple[AnnotationPlacement, bool]:
    """Walk the candidate ladder; return the first zero-overlap placement and
    whether it was placed clean. The ladder order IS the tie-break. There is no
    ellipsis rung — a run that cannot be placed keeps its wrapped text and its
    preferred box (the caller warns); annotations never truncate to fit."""
    # An edge-chip rides ON its wire by construction (the kit specimen sheet, piece 7: the
    # line runs through the chip's vertical center, even in / even out). It is
    # an OPAQUE pill that covers whatever it sits over — it must never be
    # mirrored, slid, or pushed off the wire to dodge a neighbor. The ladder is
    # for FLOATING labels (callouts, micro-labels, legends) that need clear
    # ground; a chip's seat is correct-by-construction, so it exits here. This
    # is the stage-4 rule the pass never learned — the ±16 perpendicular shove
    # that lifted reads/emits/direct-read off their lines.
    if p.box is None or p.kind == "edge-chip":
        return p, True
    # The text-text margin only governs LABEL-vs-LABEL proximity (see
    # _total_overlap) — a callout/aside/legend keeps the plain zero-overlap
    # bar against everything, unchanged.
    margin = text_margin if p.kind == "label" else 0.0
    incident = incident_obstacles or []
    if _total_overlap(p.box, obstacles, text_margin=margin) == 0.0:
        return _clear_own_incident(p, obstacles, incident, geo, slides, margin), True
    ladder: list[AnnotationPlacement] = []
    mirrored = _mirror_label(p, geo)
    if mirrored is not None:
        ladder.append(mirrored)
    ladder.extend(_slide_candidates(p, geo, slides))
    ladder.extend(_push_candidates(p, push_step, push_max))
    for cand in ladder:
        if (
            cand.box is not None
            and _total_overlap(cand.box, obstacles, text_margin=margin) == 0.0
            and not _wire_through_box(cand.box, geo)
        ):
            return _clear_own_incident(cand, obstacles, incident, geo, slides, margin), True
    return p, False


def _ladder_params(engine: Mapping[str, Any]) -> tuple[list[float], float, float, float]:
    """The resolve ladder's tunables, plus the label-vs-label minimum margin:
    HALF ``min_clearance`` — the SAME clearance budget ``annotate.py``'s
    node/edge obstacles already carry (``_static_obstacles``:
    ``clear = min_clearance / 2``), applied now to label-vs-label proximity
    too. No hand SM specimen actually crowds two labels this tight (their
    discipline keeps labels apart by placement, not a numeric floor) — the
    margin exists for what the ladder produces when it lacks that
    discipline, so it borrows the kit's one already-established 'breathing
    room' constant rather than inventing a new one."""
    cfg = engine.get("annotate") or {}
    slides = [float(f) for f in cfg.get("candidate_slides", [0.5, 0.38, 0.62, 0.26, 0.74])]
    text_margin = float(engine.get("min_clearance", 18)) / 2.0
    return slides, float(cfg.get("push_step", 4)), float(cfg.get("push_max", 28)), text_margin


def resolve_labels(
    *,
    labels: list[AnnotationPlacement],
    obstacles: list[Obstacle],
    geo_of: dict[int, EdgeGeo],
    edges: tuple[ResolvedEdge, ...],
    engine: Mapping[str, Any],
    warnings: tuple[str, ...] = (),
) -> tuple[list[AnnotationPlacement], list[Obstacle], list[str]]:
    """Resolve the subsumed edge labels FIRST, against the STATIC obstacles only
    (cards, wires, bands) — never against caller annotations, which are placed
    afterward. A label carries its geo (for mirror/slide) and its incident
    node/edge indices, so it EXCLUDES its own endpoints + wire: the authored
    position beside its edge is never a false collision, which is what keeps the
    parity pins byte-identical. Returns the placed labels, the obstacle set
    grown by each label's box, and any overlap warnings — the grown set is what
    the caller-kind placement then avoids."""
    slides, push_step, push_max, text_margin = _ladder_params(engine)
    working = list(obstacles)
    out: list[AnnotationPlacement] = []
    warns = list(warnings)
    labelled_indices = [j for j, e in enumerate(edges) if e.label and j in geo_of]
    for k, p in enumerate(labels):
        edge_index = labelled_indices[k] if k < len(labelled_indices) else -1
        geo = geo_of.get(edge_index) if edge_index >= 0 else None
        incident = _incident_refs(edge_index, edges)
        # Own-wire exclusion keys the GEO the label actually rides: a fan
        # chip authored on a spoke rides the shared depart TRUNK, whose
        # obstacle carries the trunk's own index — excluding only the
        # authored index let the trunk push its own chip off the wire.
        own_edge = geo.index if geo is not None else edge_index
        seen = [o for o in working if not _is_incident(o, incident, own_edge)]
        # The excluded NODE geometry isn't dropped, just deferred: a ladder
        # candidate chosen to dodge a FOREIGN obstacle can still land on the
        # label's own node (_clear_own_incident, inside _resolve_one) — the
        # residual guard that exclusion needs. NODE only, not the own-wire
        # segments _is_incident also excludes: a solver-anchored label rides
        # its own wire by construction (lifted a bare sm_label_lift/label_lift
        # off it), so it ALWAYS sits near those segments — checking them here
        # would fire on every well-placed label, not just a genuine node
        # collision, and fling it off its own belly.
        incident_obs = [o for o in working if _is_incident(o, incident, own_edge) and o.kind == "node"]
        placed, ok = _resolve_one(
            p,
            seen,
            geo=geo,
            slides=slides,
            push_step=push_step,
            push_max=push_max,
            text_margin=text_margin,
            incident_obstacles=incident_obs,
        )
        out.append(placed)
        if placed.box is not None:
            # kind="label" (not "furniture"): a LATER label's own text-text
            # margin check (_total_overlap) only inflates against this kind
            # — a lane band or another caller kind never gets the extra
            # margin, only a sibling label does. _is_incident still falls
            # through to False for it (only "node"/"edge" are checked), so
            # the own-incident exclusion above is unaffected.
            working.append(Obstacle(box=placed.box, kind="label", ref=-1))
        if not ok:
            warns.append(_overlap_warning(p))
    return out, working, warns


def resolve_generic(
    *,
    placements: list[AnnotationPlacement],
    obstacles: list[Obstacle],
    engine: Mapping[str, Any],
    warnings: tuple[str, ...] = (),
) -> tuple[list[AnnotationPlacement], list[str]]:
    """Nudge geo-less placements (region-packed legends) off any overlap with a
    push-only ladder — no mirror, no slide, no ellipsis. Each placed box joins
    the obstacle set for the ones after it. Caller free-text kinds do NOT come
    here: ``place.py`` positions them in a clear zone up front. No
    ``text_margin`` here: a legend is never ``kind="label"``, so
    ``_resolve_one`` would no-op it anyway — the margin is label-vs-label
    only."""
    _, push_step, push_max, _text_margin = _ladder_params(engine)
    working = list(obstacles)
    out: list[AnnotationPlacement] = []
    warns = list(warnings)
    for p in placements:
        placed, ok = _resolve_one(p, working, geo=None, slides=[], push_step=push_step, push_max=push_max)
        out.append(placed)
        if placed.box is not None:
            working.append(Obstacle(box=placed.box, kind="furniture", ref=-1))
        if not ok:
            warns.append(_overlap_warning(p))
    return out, warns


def _incident_refs(edge_index: int, edges: tuple[ResolvedEdge, ...]) -> tuple[int, int]:
    """The (source, target) node indices of a label's own edge — the two node
    boxes it is allowed to sit against."""
    if 0 <= edge_index < len(edges):
        e = edges[edge_index]
        return (e.source, e.target)
    return (-1, -1)


def _is_incident(obstacle: Obstacle, incident_nodes: tuple[int, int], own_edge: int) -> bool:
    """Whether an obstacle is a label's OWN incident geometry: its source or
    target node box, or its own connector polyline."""
    if obstacle.kind == "node":
        return obstacle.ref in incident_nodes
    if obstacle.kind == "edge":
        return obstacle.ref == own_edge
    return False


def _overlap_warning(p: AnnotationPlacement) -> str:
    text = " ".join(t.text for t in p.lines) or p.kind
    return f"annotation overlap unresolved: {text}"
