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
import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.recenter import translate_path
from hyperweave.compose.diagram.sizing import CHIP_STUB_MIN
from hyperweave.compose.geometry.bounds import inflate, overlap_area, segment_crosses_box

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
        ob = inflate(o.box, text_margin) if (text_margin and o.kind == "label") else o.box
        total += overlap_area(box, ob)
    return total


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
    return any(segment_crosses_box(a, b, box) for a, b in segs)


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
    return any(segment_crosses_box(a, b, padded) for a, b in perimeter)


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
            # A drawn swatch (diamond/square/line stub) is a precomputed d
            # string — it must ride the same translation as the circle
            # swatches' cx/cy fields, or a displaced legend renders its
            # marks at the OLD seat while its text moves (the misaligned-key
            # defect: ring at the new row, diamond 8px below it).
            swatch_path=translate_path(e.swatch_path, dx, dy) if e.swatch_path else "",
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
    # An ARC's body bows far off its endpoint midline — mirroring across
    # that midline would drop the label INTO the content band the arc
    # exists to avoid (the breaker's probe label once landed inside the
    # state row this way). No mirror candidate; the label slides instead.
    ys = [pt[1] for pt in poly]
    end_hi, end_lo = max(poly[0][1], poly[-1][1]), min(poly[0][1], poly[-1][1])
    if max(max(ys) - end_hi, end_lo - min(ys)) > 20.0:
        return None
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
    poly: tuple[tuple[float, float], ...] = geo.polyline or ((geo.sx, geo.sy), (geo.tx, geo.ty))
    cur_cx = p.box.x + p.box.w / 2
    cur_cy = p.box.y + p.box.h / 2
    ys_ = [pt[1] for pt in poly]
    bow = max(max(ys_) - max(poly[0][1], poly[-1][1]), min(poly[0][1], poly[-1][1]) - min(ys_))
    if bow <= 20.0:
        # Straight-ish wires slide along the endpoint chord (byte-identical
        # to the original walk).
        start, end = poly[0], poly[-1]
        out_c: list[AnnotationPlacement] = []
        for f in slides:
            tx = start[0] + (end[0] - start[0]) * f
            ty = start[1] + (end[1] - start[1]) * f
            out_c.append(_shift_placement(p, tx - cur_cx, ty - cur_cy))
        return out_c
    # A BOWED geo (an over/under arc) slides along the POLYLINE: its chord
    # runs at the content band's own line, so chord-sliding dropped arc
    # labels onto the cards they float above. The box keeps its current
    # offset from its nearest polyline point and rides the curve.
    lens: list[float] = [0.0]
    for a, b in itertools.pairwise(poly):
        lens.append(lens[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = lens[-1] or 1.0

    def at(f: float) -> tuple[float, float]:
        target = f * total
        for i in range(1, len(lens)):
            if lens[i] >= target:
                seg = lens[i] - lens[i - 1] or 1.0
                t = (target - lens[i - 1]) / seg
                ax, ay = poly[i - 1]
                bx, by = poly[i]
                return (ax + (bx - ax) * t, ay + (by - ay) * t)
        return poly[-1]

    near = min(poly, key=lambda q: (q[0] - cur_cx) ** 2 + (q[1] - cur_cy) ** 2)
    off_x, off_y = cur_cx - near[0], cur_cy - near[1]
    out: list[AnnotationPlacement] = []
    for f in slides:
        tx, ty = at(f)
        out.append(_shift_placement(p, tx + off_x - cur_cx, ty + off_y - cur_cy))
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
    # TWO passes, and the second one is the whole point. Every candidate here
    # is a slide along the label's OWN wire, so on a diagonal run the wire
    # crosses the text box at every position on the ladder — including the
    # seat the label already occupies. Requiring ``not _wire_through_box`` in
    # a single pass therefore rejects the entire ladder and silently returns
    # the overlapping seat, which is how a label came to sit on the corner of
    # its own source card: the guard fired, found five clean candidates, and
    # threw all five away for a property its starting point also had.
    #
    # So: prefer a seat that clears the wire too, and if none exists, take one
    # that merely clears the CARD. A wire crossing its own label is a dress
    # problem; a label lying on a card is an unreadable one.
    # A slide keeps the lift vector it started with, which on a DIAGONAL run
    # points along the wire rather than off it — so every slid seat still has
    # the wire through it. Offer each candidate's mirror as well: same seat,
    # lift flipped to the other side of the thread. That is the tool that
    # actually clears a diagonal, and sliding alone never reaches it.
    fallback: AnnotationPlacement | None = None
    for cand in _slide_candidates(p, geo, slides):
        for trial in (cand, _mirror_label(cand, geo)):
            if (
                trial is None
                or trial.box is None
                or _total_overlap(trial.box, incident_obstacles) != 0.0
                or _total_overlap(trial.box, obstacles, text_margin=text_margin) != 0.0
            ):
                continue
            if not _wire_through_box(trial.box, geo):
                return trial
            if fallback is None:
                fallback = trial
    return fallback if fallback is not None else p


def _chip_slide_candidates(
    p: AnnotationPlacement, geo: EdgeGeo | None, slides: list[float]
) -> list[AnnotationPlacement]:
    """Seats along the chip's own DRAWN path, at the slide fractions, keeping
    ``CHIP_STUB_MIN`` of visible wire on each side.

    Always arc-length along the polyline, never the endpoint chord: on an
    HVH skip route the chord cuts the corner and leaves the wire entirely,
    which is the seat-offset law's whole subject. The stub floor is the same
    constant the solvers reserve their runs with, so a slide can never spend
    the clearance the run was widened to provide — a chip pushed up against
    its own arrowhead reads as a chip on the wrong edge."""
    if geo is None or p.box is None:
        return []
    poly = geo.polyline or ((geo.sx, geo.sy), (geo.tx, geo.ty))
    lens = [0.0]
    for a, b in itertools.pairwise(poly):
        lens.append(lens[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = lens[-1]
    if total <= 0.0:
        return []
    cur_cx, cur_cy = p.box.x + p.box.w / 2, p.box.y + p.box.h / 2
    # A FLOATED chip keeps its offset from the run. Sliding a chip by putting
    # its centre ON the polyline is right for a pill that rides its wire and
    # destroys one that was deliberately lifted clear of a bend — the slide
    # would hand it straight back the stroke the float exists to escape.
    near_x, near_y = cur_cx, cur_cy
    best = math.inf
    for a, b in itertools.pairwise(poly):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((cur_cx - a[0]) * dx + (cur_cy - a[1]) * dy) / L2))
        px, py = a[0] + t * dx, a[1] + t * dy
        d = math.hypot(cur_cx - px, cur_cy - py)
        if d < best:
            best, near_x, near_y = d, px, py
    off_x, off_y = cur_cx - near_x, cur_cy - near_y
    out: list[AnnotationPlacement] = []
    for f in slides:
        target = f * total
        for i, (a, b) in enumerate(itertools.pairwise(poly)):
            if lens[i + 1] < target and i + 2 < len(lens):
                continue
            seg = lens[i + 1] - lens[i]
            if seg <= 0.0:
                continue
            t = (target - lens[i]) / seg
            # How much of the run this pill actually occupies depends on the
            # direction the run leaves at: a 63x26 chip eats 63px of a
            # horizontal wire but only 26 of a vertical one. Taking the wider
            # side for both reserved 37px that a vertical run never spends,
            # and rejected the only seats it had. This is the rectangle's
            # support width along the local heading.
            ux, uy = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
            half = (abs(ux) * p.box.w + abs(uy) * p.box.h) / 2
            # A stub of visible wire each side, measured the way the battery
            # measures it: from the pill's edge to the end of the run.
            if target - half < CHIP_STUB_MIN or (total - target) - half < CHIP_STUB_MIN:
                break
            tx = a[0] + (b[0] - a[0]) * t + off_x
            ty = a[1] + (b[1] - a[1]) * t + off_y
            out.append(_shift_placement(p, tx - cur_cx, ty - cur_cy))
            break
    return out


def _resolve_chip(
    p: AnnotationPlacement,
    obstacles: list[Obstacle],
    *,
    geo: EdgeGeo | None,
    slides: list[float],
) -> tuple[AnnotationPlacement, bool]:
    """Arbitrate one edge-chip against the other ANNOTATIONS, and nothing else.

    A chip is an opaque pill that covers whatever it sits over — a wire, a
    card corner, a band. That is the seat law, not a defect, and it is why
    every non-annotation obstacle is filtered out here: re-seating a chip to
    dodge geometry it is entitled to cover moves seats the specimens pin.
    The one thing a pill must not cover is ANOTHER pill, because there is no
    reading order between two opaque plates — the lower one is simply gone.

    So: the preferred seat wins whenever no sibling annotation contests it,
    which is every chip in every artifact that already composed. Otherwise
    the chip slides along its own drawn path, inside the stub law. Mirror and
    push are the OFF-wire moves and stay barred.

    A chip that cannot find a clear seat anywhere on its run keeps its
    preferred one and reports ``False`` — the caller warns. Burial is then a
    stated defect on a crowded graph rather than a silent one, and the chip
    still reads against the edge it belongs to."""
    if p.box is None:
        return p, True
    siblings = [o for o in obstacles if o.kind == "label"]
    if not siblings or _total_overlap(p.box, siblings) == 0.0:
        return p, True
    for cand in _chip_slide_candidates(p, geo, slides):
        if cand.box is not None and _total_overlap(cand.box, siblings) == 0.0:
            return cand, True
    return p, False


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
    if p.box is None:
        return p, True
    # An edge-chip rides ON its wire by construction (the kit specimen sheet, piece 7: the
    # line runs through the chip's vertical center, even in / even out). It is
    # an OPAQUE pill that covers whatever it sits over — it must never be
    # mirrored or pushed OFF the wire to dodge a neighbor. That is the stage-4
    # rule the pass never learned — the ±16 perpendicular shove that lifted
    # reads/emits/direct-read off their lines.
    #
    # What the law fixes is the chip's OFFSET from the thread, not its position
    # ALONG it: the run midpoint is the preferred seat, not the only legal one.
    # So a chip arbitrates by sliding down its own wire, where the line still
    # runs through its vertical center and the pill still reads as that edge's.
    # Its acceptance test is the INVERSE of a floating label's: a chip REQUIRES
    # the wire through its box (that is the piece), where a callout requires
    # clear ground. Without this a converging pair — a forward chip and a
    # back-edge chip arriving at the same hero — both declared themselves
    # correct-by-construction and one rendered buried under the other, with no
    # warning, because the old exit reported every chip clean.
    if p.kind == "edge-chip":
        return _resolve_chip(p, obstacles, geo=geo, slides=slides)
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

    # PINNED BEFORE MOVABLE. A chip rides its own wire at the run midpoint —
    # that seat is the law, so the ladder cannot move it. A bare micro-label
    # can go anywhere clear. Walking them in edge order therefore lets a chip
    # land on a micro-label that was already placed, and neither one yields.
    # Placing every pinned chip first puts its plate in the obstacle set before
    # a single free label is laddered, so the label steps around it instead.
    # Among the chips, SHORTEST RUN FIRST. A chip can only slide along its own
    # wire, so the length of that wire is exactly how much choice it has: a
    # chip on a 100px run has one or two legal seats, one on a 365px run has
    # its pick. Seating them in edge order handed the ground to whichever chip
    # the caller happened to declare first and left the constrained one with
    # nowhere legal to go — the short forward run to the generators lost to a
    # long back-edge that had the whole graph to slide along. Serving the
    # least-free chip first lets the free one route around it, which is the
    # only ordering under which both can be right.
    def _run_len(k: int) -> float:
        if k >= len(labelled_indices):
            return 0.0
        geo = geo_of.get(labelled_indices[k])
        if geo is None:
            return 0.0
        poly = geo.polyline or ((geo.sx, geo.sy), (geo.tx, geo.ty))
        return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in itertools.pairwise(poly))

    def _rank(k: int) -> tuple[int, float]:
        is_chip = k < len(labelled_indices) and edges[labelled_indices[k]].label_style == "chip"
        return (0, _run_len(k)) if is_chip else (1, 0.0)

    order = sorted(range(len(labels)), key=_rank)
    placed_by_k: dict[int, AnnotationPlacement] = {}
    for k in order:
        p = labels[k]
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
        placed_by_k[k] = placed
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
    # Emit in the caller's original order — only the RESOLUTION order changed.
    out = [placed_by_k[k] for k in range(len(labels))]
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
