"""Post-layout annotation chrome pass — the overlay layer on a solved topology.

The solver places nodes and routes edges; THIS pass places everything the
solver does not own: the edge labels (subsumed here so every topology renders
them, not just sequence/state-machine), plus caller-declared callouts,
asides, and legends. It runs inside ``finish_layout`` after
``wire_motion`` (the connectors exist as collision obstacles) and before
``build_footer`` (a footer-region legend/aside can grow the canvas first).

Responsibilities split three ways: this module owns the region table, edge-
label subsumption, and orchestration; ``chrome_kinds.py`` owns each caller
kind's preferred geometry; ``collide.py`` moves a placement off the graph when
its preferred spot overlaps something. The edge-label migration guarantee
lives here — a subsumed label reproduces the retired wiring block's math
byte-for-byte where the solver supplied a ``label_pos``, so its preferred
position equals what rendered before subsumption, and collision is a no-op for
the labels that never collided.

Regions (canvas / header / footer + solver-registered ``zone:*`` / ``lane:*``)
are the coordinate frames a region-anchored annotation resolves against. The
region table's ``extra_regions`` parameter is the extension seam hub/lanes call
into (empty today) — an unknown region name raises ``DiagramInputError`` naming
the registered set, never a silent miss.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram import chrome_kinds as ck
from hyperweave.compose.diagram import motion as mo
from hyperweave.compose.diagram import place
from hyperweave.compose.diagram.collide import (
    Obstacle,
    _band_border_crossed,
    _wire_through_box,
    resolve_generic,
    resolve_labels,
)
from hyperweave.compose.diagram.records import AnnotationPlacement, DiagramText, LaneBand
from hyperweave.compose.diagram.sizing import CHIP_RX, solve_chip_box, voice_for
from hyperweave.compose.matrix.cells import measure_voice
from hyperweave.compose.spatial_records import RectSpec
from hyperweave.core.diagram import DiagramInputError
from hyperweave.core.diagram_annotations import AnnotationKind, parse_edge_ref

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hyperweave.compose.diagram.records import LaneBand, NodePlacement
    from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
    from hyperweave.core.diagram import ResolvedEdge
    from hyperweave.core.diagram_annotations import DiagramAnnotation

_CLEAR_SCAN_PAD = 2.0
"""Sampling headroom for the floated-seat clearance scan (see
``_lift_clear_of_run``): the scan tests points, the law grades the drawn
stroke, so the box is padded by more than the sample spacing."""

_GRID = 4.0
"""Footer-growth rounds up to this pixel grid so the footer re-anchors clean."""


@dataclass(frozen=True, slots=True)
class Region:
    """A rectangular coordinate frame an annotation can anchor within."""

    x: float
    y: float
    w: float
    h: float

    def point(self, fx: float, fy: float) -> tuple[float, float]:
        """Map (fx, fy) fractions to an absolute point inside the region."""
        return (self.x + fx * self.w, self.y + fy * self.h)

    def rect(self) -> RectSpec:
        """The region as a plain rect (chrome_kinds consumes rects)."""
        return RectSpec(x=self.x, y=self.y, w=self.w, h=self.h)


# ── Edge-label subsumption ───────────────────────────────────────────────────


def _edge_geo_by_index(
    geos: list[EdgeGeo], *, trunk_wins: bool = False, edges: tuple[Any, ...] = ()
) -> dict[int, EdgeGeo]:
    """First geo per logical edge index (arc-subdivided flows share an index;
    the first segment carries the label, as the wiring block put it on
    ``si == 0``). With ``trunk_wins`` (the fanout family), the depart trunk
    claims its own index AND every chip-labeled edge's index: the fan's chip
    rides the shared wire no matter which spoke authored it (stack-deps'
    core chip was authored on the pydantic spoke — it rode the curve
    mid-fan, and because the chip's own-wire exclusion keyed the SPOKE, the
    trunk pushed its own chip 59px off the wire). A dag hub's 72px depart
    stub is too short for a chip and its specimen keeps chips on the spokes,
    so dag leaves the default; the JOIN trunk (terminal 'arrow') never
    steals — converging edges keep their labels."""
    out: dict[int, EdgeGeo] = {}
    trunk: EdgeGeo | None = None
    for geo in geos:
        if trunk_wins and geo.relation_override and geo.marker_override == "none":
            out[geo.index] = geo
            trunk = geo
        else:
            out.setdefault(geo.index, geo)
    if trunk is not None:
        for j, edge in enumerate(edges):
            if getattr(edge, "label_style", "") == "chip" and j in out:
                out[j] = trunk
    return out


def _polyline_midpoint(poly: tuple[tuple[float, float], ...]) -> tuple[float, float]:
    """The point at HALF the polyline's arc length — the true midpoint of the
    DRAWN path, not its (sx,sy)->(tx,ty) chord. A curved bypass/skip/self-loop
    dips far off its chord, so a rider anchored at the chord midpoint floats in
    blank space (the roundtrip diff chip sat 125px off its under-arc). Straight
    wires are unaffected: their arc-length midpoint IS the chord midpoint."""
    if len(poly) < 2:
        return poly[0] if poly else (0.0, 0.0)
    seglens = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in itertools.pairwise(poly)]
    half = sum(seglens) / 2
    acc = 0.0
    for (a, b), length in zip(itertools.pairwise(poly), seglens, strict=True):
        if length > 0 and acc + length >= half:
            t = (half - acc) / length
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        acc += length
    return poly[-1]


def _channel_midpoint(poly: tuple[tuple[float, float], ...]) -> tuple[float, float]:
    """The midpoint of the polyline's dominant axis-aligned leg — the flat
    CHANNEL of an HVH/VHV skip route. The kit seats an edge-chip with even
    thread both sides of the run the eye reads, and on a channel route that
    run is the flat leg: the arc-length midpoint bakes the two (generally
    unequal) risers into the seat and drifts the chip off the channel's
    centre by half their difference (the service-dependencies 'direct read'
    chip sat 63px left of its channel mid). A leg qualifies as the channel
    when it is purely horizontal or vertical AND carries at least half the
    total arc length — a straight 2-point chord resolves identically to the
    arc-length midpoint, and a curved bypass/self-loop (all short sampled
    segments, no dominant leg) falls through to ``_polyline_midpoint``
    unchanged."""
    if len(poly) < 3:
        return _polyline_midpoint(poly)
    legs = [(math.hypot(b[0] - a[0], b[1] - a[1]), a, b) for a, b in itertools.pairwise(poly)]
    total = sum(leg[0] for leg in legs)
    channel = max(
        (leg for leg in legs if abs(leg[1][0] - leg[2][0]) < 0.5 or abs(leg[1][1] - leg[2][1]) < 0.5),
        key=lambda leg: leg[0],
        default=None,
    )
    if channel is not None and total > 0 and channel[0] >= 0.5 * total:
        _, a, b = channel
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return _polyline_midpoint(poly)


def _channel_leg(poly: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """The chip's seat RUN: the dominant axis-aligned leg when one exists
    (same qualification as ``_channel_midpoint``), else the straight chord of
    a 2-point wire. A curved run returns None — its chip never slides."""
    if len(poly) == 2:
        return poly[0], poly[1]
    legs = [(math.hypot(b[0] - a[0], b[1] - a[1]), a, b) for a, b in itertools.pairwise(poly)]
    total = sum(leg[0] for leg in legs)
    channel = max(
        (leg for leg in legs if abs(leg[1][0] - leg[2][0]) < 0.5 or abs(leg[1][1] - leg[2][1]) < 0.5),
        key=lambda leg: leg[0],
        default=None,
    )
    if channel is not None and total > 0 and channel[0] >= 0.5 * total:
        return channel[1], channel[2]
    return None


def _leg_at_point(
    poly: tuple[tuple[float, float], ...], point: tuple[float, float]
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """The individual polyline leg containing ``point`` (the chip's chosen
    seat), returned ONLY when that leg is axis-aligned — the clear-seat
    ladder's fallback when ``_channel_leg`` finds no GLOBALLY dominant leg.
    A flat middle run bracketed by two long S-curve risers (gateway-balanced's
    telemetry skip: a 322px flat leg between two bezier risers whose
    piecewise-linear SAMPLING overstates their true length) can miss
    ``_channel_leg``'s >=50%-of-total-sampled-arc-length bar by a hair even
    though the flat leg is, by a wide margin, the single longest individual
    leg and visually IS the channel the chip already sits on. This never
    widens which chips slide at all: a point landing on a genuinely curved
    sub-segment (every leg non-axis-aligned) still returns None, same as a
    ``_channel_leg`` miss today — it only recovers the near-miss case where
    the chip's OWN seat leg is unambiguously flat."""
    eps = 0.5
    for a, b in itertools.pairwise(poly):
        if not (abs(a[0] - b[0]) < eps or abs(a[1] - b[1]) < eps):
            continue
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        if x0 - eps <= point[0] <= x1 + eps and y0 - eps <= point[1] <= y1 + eps:
            return a, b
    return None


def _midpoint_and_tangent(
    poly: tuple[tuple[float, float], ...],
) -> tuple[float, float, float, float]:
    """The arc-length midpoint AND the LOCAL segment direction there. A rider
    lifts perpendicular to the wire's direction AT the label, not the edge's end
    tangent — a skip's flat channel run (or an over-the-top run) is horizontal
    even though the edge descends into its sink, so the end-tangent lift floated
    the chip off that flat run."""
    if len(poly) < 2:
        p = poly[0] if poly else (0.0, 0.0)
        return (p[0], p[1], 0.0, 0.0)
    seglens = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in itertools.pairwise(poly)]
    half = sum(seglens) / 2
    acc = 0.0
    for (a, b), length in zip(itertools.pairwise(poly), seglens, strict=True):
        if length > 0 and acc + length >= half:
            t = (half - acc) / length
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), b[0] - a[0], b[1] - a[1])
        acc += length
    a, b = poly[-2], poly[-1]
    return (poly[-1][0], poly[-1][1], b[0] - a[0], b[1] - a[1])


OWNERSHIP_MIN_RATIO = 1.5
"""How much nearer its OWN wire a bare micro-label must sit than the nearest
foreign one, for a reader to be able to tell which edge it labels.

Calibrated from the bundled corpus, not chosen: the labels that read cleanly
sit at 2.3x and above, the two ``pipeline-row`` duplex labels and
``sm-recursive``'s ``error`` sit at 1.34-1.44x, and the readme-ai fan's
``render`` — the label nobody could attribute — sits at 1.01x. 1.5 is the gap
between the borderline band and the healthy one. A DUPLEX label is exempt: a
paired request/response label belongs BETWEEN its pair by design, so
proximity to the partner wire is the vocabulary, not a defect."""


def _point_wire_distance(px: float, py: float, poly: tuple[tuple[float, float], ...]) -> float:
    """Shortest distance from a point to a sampled polyline."""
    best = math.inf
    for a, b in itertools.pairwise(poly):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
        best = min(best, math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy)))
    return best


def _ownership_ratio(
    seat: tuple[float, float],
    own: tuple[tuple[float, float], ...],
    foreign: list[tuple[tuple[float, float], ...]],
) -> float:
    """How decisively a seat reads as belonging to ``own`` — the nearest
    foreign wire's distance over its own. Above 1 it is nearer its own wire;
    the ratio says by how much, which is the part a reader actually uses."""
    d_own = _point_wire_distance(seat[0], seat[1], own)
    if d_own <= 1e-9:
        return math.inf
    d_foreign = min((_point_wire_distance(seat[0], seat[1], f) for f in foreign), default=math.inf)
    return d_foreign / d_own


def _densify(run: tuple[tuple[float, float], ...], step: float = 3.0) -> tuple[tuple[float, float], ...]:
    """Resample a polyline at even spacing, so an emptiness test cannot miss
    a long straight leg lying between two far-apart vertices."""
    if len(run) < 2:
        return run
    out: list[tuple[float, float]] = [run[0]]
    for a, b in itertools.pairwise(run):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(seg / step))
        for k in range(1, n + 1):
            f = k / n
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return tuple(out)


def _lift_clear_of_run(
    poly: tuple[tuple[float, float], ...],
    seat: tuple[float, float],
    box_w: float,
    box_h: float,
    clear: float,
    *,
    lane: int = 0,
    steep: bool = False,
    others: list[tuple[tuple[float, float], ...]] | None = None,
) -> tuple[float, float]:
    """Float a pill off a bend to the NEAREST seat no wire reaches.

    A fixed perpendicular lift is only right on a straight wire: over the
    width of its own pill a curve climbs, so a pill lifted by
    ``half_pill + clear`` at the seat point still catches its own stroke near
    the box's ends. And a seat that clears its own bend can still land on a
    neighbour's run — a pill with somebody else's wire through it reads
    exactly as broken as one with its own.

    So the distance is SEARCHED, not derived: step outward from the minimum
    the specimen band allows and stop at the first offset where the box is
    empty of every wire. Searching beats solving here because "clear of all
    runs" is not a single extreme to compute — taking the extreme of every
    wire crossing the pill's span at once stacks unrelated geometry and
    pushes the pill off the canvas (measured: y=10 on a 175px graph).

    A run of offsets that never clears returns the minimum, which keeps the
    pill on its own edge and lets the battery report the collision rather
    than hiding it in a silent drift.
    """
    if len(poly) < 2:
        return seat
    direction = _lift_direction(poly, seat, lane=lane, steep=steep)
    along_i, across_i = (1, 0) if steep else (0, 1)
    half_along = (box_h if steep else box_w) / 2
    half_across = (box_w if steep else box_h) / 2
    # Densified: a coarse polyline puts long straight legs between distant
    # vertices, and an emptiness test that samples only vertices lets a whole
    # leg pass through the box unseen.
    runs = [_densify(r) for r in (poly, *(others or ()))]

    def box_is_clear(centre_across: float) -> bool:
        # Padded by the sampling step: the scan reads points, the law reads
        # the continuous stroke, and a wire may dip into the box between two
        # samples. The pad is what makes "clear" mean clear.
        pad = _CLEAR_SCAN_PAD
        lo, hi = centre_across - half_across - pad, centre_across + half_across + pad
        a_lo, a_hi = seat[along_i] - half_along - pad, seat[along_i] + half_along + pad
        for run in runs:
            for p in run:
                if a_lo <= p[along_i] <= a_hi and lo <= p[across_i] <= hi:
                    return False
        return True

    minimum = half_across + clear
    step = max(1.0, clear / 4)
    offset = minimum
    limit = minimum + 8 * (box_h if steep else box_w)
    while offset <= limit:
        candidate = seat[across_i] + direction * offset
        if box_is_clear(candidate):
            return (candidate, seat[1]) if steep else (seat[0], candidate)
        offset += step
    fallback = seat[across_i] + direction * minimum
    return (fallback, seat[1]) if steep else (seat[0], fallback)


def _lift_direction(
    poly: tuple[tuple[float, float], ...], seat: tuple[float, float], *, lane: int, steep: bool
) -> float:
    """Which way a floated pill leaves its run: +1 or -1 along the minor axis.

    A DUPLEX channel floats OUTWARD OF ITS PAIR — away from the partner wire,
    in the direction its own lane sign already put it. The corridor between
    two channels is one lane gap wide and can never hold a pill, so a rule
    that can point inward lands the pill on its partner.

    A lone bent edge has no partner, so it takes the OUTSIDE of its bend: a
    pill lifted into the concave side moves toward whatever the bend is
    bending around.
    """
    if lane != 0:
        return 1.0 if lane > 0 else -1.0
    best_i, best_d = 0, math.inf
    for i, (a, b) in enumerate(itertools.pairwise(poly)):
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        d = math.hypot(seat[0] - mx, seat[1] - my)
        if d < best_d:
            best_i, best_d = i, d
    prev_i = max(best_i - 1, 0)
    next_i = min(best_i + 1, len(poly) - 2)
    p0, p1 = poly[prev_i], poly[prev_i + 1]
    q0, q1 = poly[next_i], poly[next_i + 1]
    turn = (p1[0] - p0[0]) * (q1[1] - q0[1]) - (p1[1] - p0[1]) * (q1[0] - q0[0])
    a, b = poly[best_i], poly[best_i + 1]
    ux, uy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(ux, uy)
    if n == 0:
        return -1.0
    nx, ny = -uy / n, ux / n
    if turn > 0:
        nx, ny = -nx, -ny
    comp = nx if steep else ny
    return 1.0 if comp >= 0 else -1.0


def _lift_off_run(
    poly: tuple[tuple[float, float], ...],
    seat: tuple[float, float],
    lift: float,
    *,
    lane: int = 0,
    steep: bool = False,
) -> tuple[float, float]:
    """Push a pill off its own run, clear of the stroke.

    A DUPLEX channel (``lane`` non-zero) floats OUTWARD OF ITS PAIR: away
    from the partner wire, along the minor axis, in the direction its own
    lane sign already put it. The corridor between two channels is one lane
    gap wide — it can never hold a pill — so any rule that can point inward
    lands the pill on its partner's wire, which is what shipped.

    A lone bent edge has no partner to avoid, so it takes the OUTSIDE of the
    bend: a pill lifted into the concave side moves toward whatever the bend
    is bending around. The local turn decides, so it reads the same on a rise
    and a fall."""
    if len(poly) < 2 or lift <= 0:
        return seat
    if lane != 0:
        sign = 1.0 if lane > 0 else -1.0
        return (seat[0] + sign * lift, seat[1]) if steep else (seat[0], seat[1] + sign * lift)
    best_i, best_d = 0, math.inf
    for i, (a, b) in enumerate(itertools.pairwise(poly)):
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        d = math.hypot(seat[0] - mx, seat[1] - my)
        if d < best_d:
            best_i, best_d = i, d
    a, b = poly[best_i], poly[best_i + 1]
    ux, uy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(ux, uy)
    if n == 0:
        return seat
    ux, uy = ux / n, uy / n
    nx, ny = -uy, ux
    # Turn sign from the neighbouring segments: the outside of the bend is
    # away from where the run is curving.
    prev_i = max(best_i - 1, 0)
    next_i = min(best_i + 1, len(poly) - 2)
    p0, p1 = poly[prev_i], poly[prev_i + 1]
    q0, q1 = poly[next_i], poly[next_i + 1]
    turn = (p1[0] - p0[0]) * (q1[1] - q0[1]) - (p1[1] - p0[1]) * (q1[0] - q0[0])
    if turn > 0:
        nx, ny = -nx, -ny
    return (seat[0] + nx * lift, seat[1] + ny * lift)


def is_duplex_edge(edges: Sequence[ResolvedEdge], j: int) -> bool:
    """Whether edge ``j`` is one half of a reciprocal pair — the same u->v
    with v->u that promotes a cyclic dag.

    A duplex label is exempt from the ownership law: a request/response pair
    is DRAWN as two wires side by side, and its two labels belong in the
    channel between them. Proximity to the partner wire is the vocabulary
    there, not a failure to attribute — which matters more than it looks,
    because the dag work now takes reciprocal pairs natively and renders them
    as one dual-channel conduit. A law that fought that grammar would be
    fighting the feature that is arriving next."""
    if not (0 <= j < len(edges)):
        return False
    e = edges[j]
    return any(o.source == e.target and o.target == e.source for k, o in enumerate(edges) if k != j)


def _foreign_wires(ctx: SolverContext, geos: list[EdgeGeo], j: int) -> list[tuple[tuple[float, float], ...]]:
    """Every OTHER edge's drawn polyline — the competition a label has to be
    told apart from. A duplex edge gets an empty list, which turns the
    ownership check off for it entirely (see ``is_duplex_edge``)."""
    if is_duplex_edge(ctx.edges, j):
        return []
    own = geos[j] if 0 <= j < len(geos) else None
    out: list[tuple[tuple[float, float], ...]] = []
    for k, g in enumerate(geos):
        if g is None or k == j or (own is not None and g.index == own.index):
            continue
        out.append(g.polyline or ((g.sx, g.sy), (g.tx, g.ty)))
    return out


def _coincident_label_runs(
    edges: Sequence[ResolvedEdge], geo_of: Mapping[int, EdgeGeo], tol: float = 1.0
) -> dict[int, tuple[int, int]]:
    """Labelled edges that are DRAWN ON THE SAME RUN, grouped and sided.

    A chip's seat is the run midpoint and the ladder may not move it, so two
    labelled edges sharing one run pin two pills to one point and fuse by
    construction — the arithmetic is not close: separating a 121 and a 150
    wide pill needs 141px where the slide ladder's whole slack on a 253px run
    is 32. No amount of nudging resolves it, which is why this is decided
    here rather than left to the collide pass.

    Keyed on the GEOMETRY, not on reciprocity. A request/response pair is the
    common cause but not the condition: sequence draws each message on its
    own arrow and a state machine on its own back-arc, so neither coincides
    and neither is touched, while two parallel edges that are not a pair at
    all still fuse and still need this. Only runs the solver left unseated
    are considered — a ``label_pos`` means the solver already chose.

    Returns ``{edge index: (side, rank)}``: sides alternate so the first
    declared rides above its run and its partner below, and rank pushes any
    third-and-beyond member further out rather than back onto a taken seat.
    """
    groups: list[list[int]] = []
    for j, e in enumerate(edges):
        g = geo_of.get(j)
        if not e.label or g is None or g.label_pos is not None:
            continue
        ends = ((g.sx, g.sy), (g.tx, g.ty))
        for grp in groups:
            h = geo_of[grp[0]]
            other = ((h.sx, h.sy), (h.tx, h.ty))
            fwd = math.dist(ends[0], other[0]) <= tol and math.dist(ends[1], other[1]) <= tol
            rev = math.dist(ends[0], other[1]) <= tol and math.dist(ends[1], other[0]) <= tol
            if fwd or rev:
                grp.append(j)
                break
        else:
            groups.append([j])
    sided: dict[int, tuple[int, int]] = {}
    for grp in groups:
        if len(grp) < 2:
            continue
        for rank, j in enumerate(grp):
            sided[j] = (1 if rank % 2 == 0 else -1, rank // 2)
    return sided


def _perp_lift(
    geo: EdgeGeo,
    lift: float,
    half_w: float = 0.0,
    half_h: float = 0.0,
    foreign: list[tuple[tuple[float, float], ...]] | None = None,
    side: int = 0,
) -> tuple[float, float]:
    """A label anchor lifted along the wire's local perpendicular for a geo
    the solver left unlabelled — the arc-length midpoint pushed off the wire,
    by default toward the smaller-y side so labels ride above it. The lift
    covers the label BOX's support extent along the normal (|nx|·half_w +
    |ny|·half_h) plus the configured margin: a fixed lift cleared horizontal
    wires but left a middle-anchored run straddling vertical and diagonal
    spokes — and a label's OWN wire is excluded from collision by design, so
    the preferred position itself must clear it. Deterministic: the
    perpendicular is fixed by the end tangent, reproducible run to run.

    ABOVE is the standing default, and it stays the answer for every wire
    with room on that side. It is abandoned only when it produces a seat the
    reader cannot attribute: on a FAN, "above" points out of the diagram for
    the edge that curves up and straight INTO the fan for the edge that
    curves down, so the lower edge's label was being lifted toward its
    siblings — the readme-ai `render` label was born at 0.70x, nearer the
    `synthesize` wire than its own, before any collision pass ran. The
    collide ladder then cleared the OVERLAP and left the ambiguity, because
    not-overlapping and attributable are different properties.

    The flip is deliberately hysteretic, not a bare "pick the roomier side":
    the default has to be AMBIGUOUS (below ``OWNERSHIP_MIN_RATIO``) and the
    mirror has to actually FIX it. Two seats within a hair of each other
    therefore never trade places between near-identical renders, which is
    what would churn goldens for no legibility gain. Both candidates come out
    of the same ``off`` formula, so the mirror keeps the standoff law rather
    than trading clearance for attribution."""
    poly = geo.polyline or ((geo.sx, geo.sy), (geo.tx, geo.ty))
    mx, my, ux, uy = _midpoint_and_tangent(poly)
    if ux == 0.0 and uy == 0.0:  # degenerate local segment — fall back to the end tangent
        ux, uy = geo.end_tangent or (geo.tx - geo.sx, geo.ty - geo.sy)
    d = math.hypot(ux, uy)
    if d == 0:
        return (mx, my - lift - half_h)
    nx, ny = -uy / d, ux / d
    if ny > 0:
        nx, ny = -nx, -ny
    off = lift + abs(nx) * half_w + abs(ny) * half_h
    seat = (mx + nx * off, my + ny * off)
    if side:
        # A run shared by two labels: the side is assigned, not chosen. The
        # ownership test below cannot decide it — both labels name the SAME
        # wire, so every ratio is 1.0 and the hysteresis has nothing to weigh.
        return seat if side > 0 else (mx - nx * off, my - ny * off)
    if not foreign:
        return seat
    if _ownership_ratio(seat, poly, foreign) >= OWNERSHIP_MIN_RATIO:
        return seat
    mirrored = (mx - nx * off, my - ny * off)
    if _ownership_ratio(mirrored, poly, foreign) >= OWNERSHIP_MIN_RATIO:
        return mirrored
    return seat


def _solver_label_lift(geo: EdgeGeo, point: tuple[float, float], lift: float, anchor: str) -> tuple[float, float]:
    """The ONE place a solver-anchored micro-label's presentation offset is
    applied — the convention this collapses: every graph.py label_pos site
    (SM plain-forward, back-edge belly, over-arc peak, baseline<->drop
    midpoint) hands back the bare point ON the wire, geometric and unbiased;
    this is where it clears the stroke. Chips never call this (a chip centers
    its box ON the bare point — no lift at all).

    A middle-anchored label lifts perpendicular to the edge's OWN chord
    (source->target, i.e. ``geo.sx,sy``->``geo.tx,ty``) at ``point``,
    continuing whichever side of the chord ``point`` already sits on: a level
    chain edge has no chord deviation (the point IS the chord) and defaults to
    the kit's reading direction, above; an under-sweep's belly or an over-arc's
    peak already deviates off its chord, so the label continues past it, into
    the same open space the curve's own bow already claimed. This is what the
    old per-branch constants (plain-forward -8, back-edge +20, over-arc -6)
    were each hand-tuning per shape; one signed perpendicular now covers all
    three. A start-anchored label (the baseline<->drop family) reads rightward
    from the point, so it clears the wire sideways instead of vertically."""
    px, py = point
    if anchor == "start":
        return (px + lift, py)
    sx, sy, tx, ty = geo.sx, geo.sy, geo.tx, geo.ty
    dx, dy = tx - sx, ty - sy
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return (px, py - lift)
    below = abs(dx) >= 1e-6 and py > (sy + (px - sx) * (dy / dx)) + 0.25
    nx, ny = -dy / d, dx / d
    if below == (ny < 0):
        nx, ny = -nx, -ny
    return (px + nx * lift, py + ny * lift)


def subsume_edge_labels(
    ctx: SolverContext, geos: list[EdgeGeo], style: ck.ChromeStyle, lane_bands: tuple[LaneBand, ...] = ()
) -> list[AnnotationPlacement]:
    """Turn every resolved edge's label into a ``kind="label"`` placement.

    Where the solver supplied ``geo.label_pos`` (sequence, state-machine, and
    any self-loop the graph solvers add) the anchor, wrap width, pitch, and
    vertical centring reproduce the retired wiring block's math byte-for-byte —
    so the migrated label's PREFERRED position equals what rendered before, and
    the parity pins hold. A chip-styled edge treats ``label_pos`` as its box
    CENTER verbatim (no lift); a plain micro-label lifts off it via
    ``_solver_label_lift`` (the single presentation-offset owner — solvers
    emit bare on-wire geometry, never a baseline bias). The pitch reads
    ``style.line_pad`` (YAML default 2.5 == the retired ``voice.size + 2.5``),
    so even the parity constant is a re-skin surface. Every other topology
    gets the polyline-midpoint fallback lifted along the local perpendicular
    by the connector ``label_lift``, anchored 'middle' — the labels that were
    reaching payload-only now render.

    ``lane_bands`` are the solver's authored region bands (gateway-balanced's
    MODEL POOL, agent-runtime's AGENT RUNTIME) — visible-outline obstacles for
    the chip clear-seat ladder below (``_band_border_crossed``), never a
    static obstacle for the generic label ladder (``resolve_labels`` already
    owns that pass via ``_static_obstacles``)."""
    conn = ctx.engine["connector"]
    label_lift = float(conn.get("label_lift", 8))
    sm_label_lift = float(conn.get("sm_label_lift", 8))
    voice = ctx.cfg.edge_label_voice
    pitch = voice.size + style.line_pad
    geo_of = _edge_geo_by_index(geos, trunk_wins=ctx.slug.startswith("fanout"), edges=ctx.edges)
    # Band OUTLINES the chip clear-seat ladder must slide clear of — the
    # filled interior is not an obstacle (a chip fully inside/outside a band
    # is fine); only "panel"/"enclosure" grounds draw a visible rect at all
    # ("typographic" zone headers have no line to cross).
    band_boxes = [lb.box for lb in lane_bands if lb.ground in ("panel", "enclosure")]
    band_clear = float((ctx.engine.get("region_band") or {}).get("band_chip_clearance", 20))
    out: list[AnnotationPlacement] = []
    # Two labels drawn on one run cannot both wear a pill at its midpoint;
    # they take the bracket instead — one above the run, one below.
    shared_run = _coincident_label_runs(ctx.edges, geo_of)
    for j, edge in enumerate(ctx.edges):
        if not edge.label:
            continue
        geo = geo_of.get(j)
        if geo is None:
            continue
        if edge.label_style == "chip" and not geo.label_micro and j not in shared_run:
            # ``label_micro`` is the solver's structural override — a conduit
            # channel has no chip home (a pill on one lane occludes the
            # partner lane), so its authored chip renders as the bare bracket
            # micro-label the solver seated in ``label_pos``. Falls through
            # to the micro-label path below, exactly like a balance-starved
            # chip always has.
            #
            # A solver-supplied label_pos wins: the geo already decided the
            # on-wire anchor (a gather-trunk chip mouth-hugging its sink), so
            # honor it verbatim and skip the length balance below — the solver
            # sized the run to seat the chip where it placed it. This is now
            # an OWNER-LEVEL guarantee, not a per-family habit: every gather/
            # join/depart trunk builder (graph.py's DAG, fan.py's fanout/
            # convergence) floors its trunk_len through sizing.chip_run_min
            # before calling knot_collapse, so "the solver sized the run" is
            # true everywhere a label_pos gets set, not just where someone
            # remembered to check. The gallery sweep's chip-stub pin re-
            # verifies the rendered geometry against the same law as a
            # regression backstop (never silently starve).
            if geo.label_pos is not None:
                accent = ctx.edge_accents[j] if j < len(ctx.edge_accents) else -1
                out.append(
                    _chip_placement(
                        edge.label, geo.label_pos[0], geo.label_pos[1], ctx.cfg, accent, style, edge_index=j
                    )
                )
                continue
            # Balance rule (cicd-machine hw:approach): a chip must show
            # visible wire BOTH sides; a run too short to balance one floats
            # the label as a micro-label instead of cramming the pill.
            chip_w, chip_h = solve_chip_box(edge.label, ctx.cfg)
            # The along-edge extent is the pill's WIDTH on a horizontal wire but
            # its HEIGHT on a vertical one (a depart trunk drops vertically — the
            # route pill rides ACROSS it, so its height is what the run must hold).
            steep = abs(geo.ty - geo.sy) > abs(geo.tx - geo.sx)
            chip_along = chip_h if steep else chip_w
            stub_min = float(conn.get("chip_stub_min", 18))
            if geo.length * 0.5 >= chip_along / 2 + stub_min:
                # Edge-chip: a single-run pill riding ON a STRAIGHT wire at
                # its midpoint (never lifted — the pill ground makes riding
                # legible). On a CURVED run the specimens float the pill
                # 7-13px clear of the bending stroke (frontier-serving
                # cache/telemetry, the SM back-arcs) — pill corners over a
                # bending line read rough. Emitted at this edge's slot so the
                # collide pass keeps its label↔edge pairing.
                poly = geo.polyline or ((geo.sx, geo.sy), (geo.tx, geo.ty))
                pmx, pmy = _channel_midpoint(poly)
                # A pill the SOLVER judged unable to sit level takes the
                # FLOATED seat (owner amendment): lifted clear of the bending
                # stroke rather than riding it, or demoted to bare text.
                #
                # The solver owns that judgement because the drawn path
                # cannot be re-read for it. Endpoint offset calls an authored
                # elbow bent while its chip rides a dead-straight gutter leg;
                # local straightness calls an S-curve flat, because an S IS
                # straight at the inflection a centred seat lands on. Only
                # the solver's own test carries the exclusions that make the
                # answer right (elbow, gather trunk, rank step).
                if geo.float_label:
                    # EDGE clearance, not centre: the specimen band is
                    # stroke-to-pill-EDGE, so the centre sits a further
                    # half-pill out or the wire runs through its own plate.
                    # A DUPLEX pill floats OUTWARD of its pair — the corridor
                    # between two channels is one lane gap wide and can never
                    # hold a pill.
                    lane = ctx.lanes[j] if j < len(ctx.lanes) else 0
                    pmx, pmy = _lift_clear_of_run(
                        poly,
                        (pmx, pmy),
                        chip_w,
                        chip_h,
                        float(conn.get("chip_curve_clear", 10)),
                        lane=lane,
                        steep=steep,
                        others=[(g.polyline or ((g.sx, g.sy), (g.tx, g.ty))) for g in geos if g.index != geo.index],
                    )
                # The specimen grounds the pill ON the wire — the line runs
                # through the pill center, legible against its fill. This holds on
                # straight runs, channel-routed skips (seated at the CHANNEL's own
                # midpoint, even thread both sides), and over-the-top runs alike;
                # the old end-tangent perp-lift floated skip chips off their flat run.
                cx, cy = pmx, pmy
                # Clear-seat law (an EXPLICIT amendment of the kit sheet's
                # absolute "pinned to the run midpoint · stage 4 never nudges
                # it"): seated at the midpoint; when a FOREIGN wire crosses
                # the pill, the chip slides along its OWN run to the nearest
                # clear seat — it never leaves the wire, and stage 4 still
                # never moves it off-run. The prototype wording predates the
                # crossing evidence (a monorepo skip ran straight through a
                # rank chip); the amendment is recorded on the kit-sheet
                # fixture and in diagram-frame.yaml's annotate block. A region
                # band's OUTLINE fouls the same ladder (gateway-balanced's
                # telemetry chip straddling the MODEL POOL band's bottom
                # hairline) — the filled interior never does; band_clear
                # holds the specimen's own 20px clearance, not a bare touch.
                # ``_leg_at_point`` recovers the near-miss case where
                # ``_channel_leg`` finds no globally-dominant leg (this
                # exact telemetry skip: a 322px flat leg between two long
                # bezier risers, 49.2% of the sampled total) but the chip's
                # own seat point already sits on an unambiguous flat run.
                leg = _channel_leg(poly) or _leg_at_point(poly, (cx, cy))
                if leg is not None:
                    (ax0, ay0), (ax1, ay1) = leg
                    leg_len = math.hypot(ax1 - ax0, ay1 - ay0)
                    if leg_len > 1e-6:
                        ux, uy = (ax1 - ax0) / leg_len, (ay1 - ay0) / leg_len
                        bw2, bh2 = solve_chip_box(edge.label, ctx.cfg)
                        slack = leg_len / 2 - (bw2 if abs(ux) >= abs(uy) else bh2) / 2 - stub_min

                        def _foul(px: float, py: float, _bw: float = bw2, _bh: float = bh2, _j: int = j) -> bool:
                            b2 = RectSpec(x=px - _bw / 2, y=py - _bh / 2, w=_bw, h=_bh)
                            return any(
                                q != _j and _wire_through_box(b2, g2) for q, g2 in enumerate(geos) if g2 is not None
                            ) or any(_band_border_crossed(b2, bb, clear=band_clear) for bb in band_boxes)

                        if slack > 0 and _foul(cx, cy):
                            for step in range(8, int(slack) + 1, 8):
                                if not _foul(cx + ux * step, cy + uy * step):
                                    cx, cy = cx + ux * step, cy + uy * step
                                    break
                                if not _foul(cx - ux * step, cy - uy * step):
                                    cx, cy = cx - ux * step, cy - uy * step
                                    break
                accent = ctx.edge_accents[j] if j < len(ctx.edge_accents) else -1
                out.append(_chip_placement(edge.label, cx, cy, ctx.cfg, accent, style, edge_index=j))
                continue
        # A micro-label floats ABOVE its wire (kit): its wrap allowance is the
        # edge run plus a small overhang, not a hard inset — a one-word label
        # on a short flush edge must not pre-ellipsize; the collide ladder
        # resolves any true overlap the overhang creates.
        max_w = geo.label_max_w or max(24.0, geo.length + 8.0)
        wrapped = ck.wrap(edge.label, max_w, voice, max_lines=2)
        n = len(wrapped)
        label_cls = "elbl"
        if geo.label_pos is not None:
            anchor = geo.label_anchor  # solver-anchored: exact reproduction
            # geo.label_bare marks a bare on-wire point (the four SM branches
            # this convention covers): lift it clear of the stroke here, the
            # single owner. Everything else (self-loops, lens bows, sequence
            # messages) already carries its OWN final point and renders
            # verbatim, unchanged.
            lx, ly = _solver_label_lift(geo, geo.label_pos, sm_label_lift, anchor) if geo.label_bare else geo.label_pos
            # Solver-anchored labels take the topology's declared class:
            # sequence messages are native text (msg), SM transitions stay
            # tracked micro-labels (elbl) — chassis data, not a code branch.
            label_cls = ctx.ch.edge_label_cls or "elbl"
        else:
            # Fallback: midpoint + perpendicular lift sized to the measured
            # label box, so the run clears its own wire at ANY wire angle.
            anchor = "middle"
            half_w = ck.text_w(tuple(wrapped), voice) / 2
            half_h = ck.block_h(n, voice, style) / 2
            _side, _rank = shared_run.get(j, (0, 0))
            lx, ly = _perp_lift(
                geo,
                label_lift + _rank * (pitch + label_lift),
                half_w,
                half_h,
                _foreign_wires(ctx, geos, j),
                side=_side,
            )
        lines = tuple(
            DiagramText(x=lx, y=ly + (k - (n - 1) / 2.0) * pitch, text=line, cls=label_cls, anchor=anchor)
            for k, line in enumerate(wrapped)
        )
        accent = ctx.edge_accents[j] if j < len(ctx.edge_accents) else -1
        # Lane dress (gateway v4 specimen): a bare label subsumed from a
        # mo.lane_dress_applies edge binds its hue to its lane's dress (the
        # request/response text) — every other micro-label stays neutral ink
        # regardless of accent_index, same as an edge-chip's P5 contract.
        lane_dressed = j < len(ctx.lanes) and mo.lane_dress_applies(ctx.spec.topology, ctx.lanes[j])
        out.append(_label_placement(lines, voice, accent, style, lane_dressed))
    return out


def _label_placement(
    lines: tuple[DiagramText, ...], voice: Any, accent: int, style: ck.ChromeStyle, lane_dressed: bool = False
) -> AnnotationPlacement:
    """Wrap subsumed label runs into a placement whose ``box`` bounds the runs
    (so collision has an obstacle) but which renders as bare text — no leader,
    no backing rect, exactly as before subsumption."""
    if not lines:
        return AnnotationPlacement(kind="label")
    texts = tuple(dt.text for dt in lines)
    w = ck.text_w(texts, voice)
    anchor = lines[0].anchor
    x0 = lines[0].x
    if anchor == "middle":
        left = x0 - w / 2
    elif anchor == "end":
        left = x0 - w
    else:
        left = x0
    top = lines[0].y - ck.ascent_of(voice, style)
    box = RectSpec(x=left, y=top, w=w, h=ck.block_h(len(lines), voice, style))
    return AnnotationPlacement(
        kind="label", lines=lines, box=box, accent_index=-1 if accent < 0 else accent, lane_dress=lane_dressed
    )


def _chip_placement(
    text: str, cx: float, cy: float, cfg: Any, accent: int, style: ck.ChromeStyle, edge_index: int = -1
) -> AnnotationPlacement:
    """The edge-chip: the SAME pill as a node chip (hub draws
    both at w=text+2*pad, h=26, rx=8 — a rounded rect, never a full pill),
    centered on the wire midpoint and dressed in the chip ground (surface tint
    + hairline) rather than the badge accent pill."""
    bw, bh = solve_chip_box(text, cfg)
    box = RectSpec(x=cx - bw / 2, y=cy - bh / 2, w=bw, h=bh, rx=CHIP_RX)
    baseline = cy + cfg.tag_voice.size * cfg.text_ascent_ratio / 2
    run = DiagramText(x=cx, y=baseline, text=text, cls="tag", anchor="middle")
    return AnnotationPlacement(
        kind="edge-chip", lines=(run,), box=box, accent_index=-1 if accent < 0 else accent, edge_index=edge_index
    )


# ── Anchor resolution ────────────────────────────────────────────────────────


def _anchor_box(
    ann: DiagramAnnotation,
    nodes: list[NodePlacement],
    geo_of: dict[int, EdgeGeo],
    regions: dict[str, Region],
    edges: tuple[Any, ...],
) -> tuple[float, float, RectSpec | None]:
    """Resolve an annotation's anchor to a point plus (for node/edge anchors)
    the anchor's bounding box. Region/at anchors return a point and no box.
    Raises on an unresolved region name — the seam contract."""
    if ann.node:
        b = _node_by_id(nodes, ann.node).box
        return (b.x + b.w / 2, b.y + b.h / 2, b)
    if ann.edge:
        geo = _edge_geo_for(ann.edge, nodes, geo_of, edges)
        poly = geo.polyline or ((geo.sx, geo.sy), (geo.tx, geo.ty))
        return ((poly[0][0] + poly[-1][0]) / 2, (poly[0][1] + poly[-1][1]) / 2, None)
    if ann.region:
        region = regions.get(ann.region)
        if region is None:
            raise DiagramInputError(
                f"annotation {ann.text!r} anchors to unknown region {ann.region!r}; "
                f"registered regions: {sorted(regions)}"
            )
        return (*region.point(0.5, 0.5), None)
    if ann.at is not None:
        return (*regions["canvas"].point(ann.at[0], ann.at[1]), None)
    raise DiagramInputError(f"annotation {ann.text!r} has no resolvable anchor")


# ── Orchestration ────────────────────────────────────────────────────────────


def build_annotations(
    ctx: SolverContext,
    geos: list[EdgeGeo],
    nodes: list[NodePlacement],
    *,
    width: float,
    height: float,
    lane_bands: tuple[LaneBand, ...] = (),
    extra_regions: dict[str, Region] | None = None,
    auto_annotations: tuple[DiagramAnnotation, ...] = (),
    frames: dict[str, Region],
) -> tuple[tuple[AnnotationPlacement, ...], float, tuple[str, ...]]:
    """The chrome pass. Returns the placed annotations (labels first, then the
    caller kinds placed in clear zones, then legends) plus ``extra_h`` — the
    footer-region band a legend forces the footer to re-anchor below.

    Order is load-bearing for parity: the subsumed edge LABELS resolve against
    the STATIC obstacles only (``resolve_labels``), so a solver-anchored label
    that never collided keeps its byte-exact position. The placed labels then
    JOIN the obstacle set, and each caller free-text kind (callout / aside)
    is positioned by ``place.py`` in the first zone clearing every card, wire,
    label, and prior annotation — the canvas grows (``finish_layout``'s
    content-union) when no zone is clear, never truncating, never on content.

    ``extra_regions`` is the solver-registered region seam (``zone:*`` for hub,
    ``lane:*`` for lanes). ``auto_annotations`` are solver-synthesized
    annotations (lanes' category legend) appended after the caller's.
    ``frames`` is required: sec 2's region engine is the ONLY supplier of
    coordinate frames, and they are CONTENT-LOCAL."""
    engine = ctx.engine
    style = ck.ChromeStyle.from_engine(engine, ctx.cfg)
    regions = dict(frames)
    if extra_regions:
        regions.update(extra_regions)
    geo_of = _edge_geo_by_index(geos, trunk_wins=ctx.slug.startswith("fanout"), edges=ctx.edges)

    # 1. Subsumed edge labels (the migration guarantee path).
    labels = subsume_edge_labels(ctx, geos, style, lane_bands)

    # 2. Cap the CALLER annotations (auto-legends are furniture).
    anns = [*ctx.spec.annotations, *auto_annotations]
    cap = int((engine.get("caps") or {}).get("annotations_max", 8))
    if len(ctx.spec.annotations) > cap:
        raise DiagramInputError(f"diagram declares {len(ctx.spec.annotations)} annotations; the cap is {cap}")

    canvas_rect = regions["canvas"].rect()

    # 3. Labels FIRST, against the static obstacles only (parity), then joining
    # the working obstacle set every caller kind must clear.
    static_obstacles = _static_obstacles(nodes, geos, lane_bands, engine, ctx.cfg)
    placed_labels, working, _ = resolve_labels(
        labels=labels, obstacles=static_obstacles, geo_of=geo_of, edges=ctx.edges, engine=engine
    )

    # 4. Caller kinds placed deliberately (obstacle-aware, greedy). A legend
    # groups by region into one row; every other kind lands in a clear zone and
    # JOINS the obstacle set so a later annotation avoids it.
    legend_by_region: dict[str, list[DiagramAnnotation]] = {}
    caller: list[AnnotationPlacement] = []
    for ann in anns:
        if ann.kind is AnnotationKind.LEGEND:
            legend_by_region.setdefault(ann.region or "canvas", []).append(ann)
            continue
        p = _place_caller(ann, nodes, geo_of, regions, canvas_rect, working, ctx, style)
        caller.append(p)
        if p.box is not None:
            working.append(Obstacle(box=p.box, kind="furniture", ref=-1))

    chrome_notes: list[str] = []
    # 5. Legends: region-packed rows, then nudged off any residual overlap.
    # A header-anchored legend is the masthead corner KEY (tr2-leg): it
    # stacks as a column, never a row. But ``region: header`` alone isn't a
    # reliable orientation signal — the lanes solver's AUTO category legend
    # (obi-engine) ALSO anchors to region="header" (its ``legend_home``
    # knob), and its own specimen law is a single right-aligned ROW inline
    # with the title, never a column. No field in DiagramAnnotation marks
    # provenance (solver-synthesized vs caller-authored — the two are
    # actually mutually exclusive by construction, see
    # lanes._auto_category_legend), so the corner-key idiom is scoped by the
    # ORIENTATION hint instead: the auto legend always sets
    # ``placement="right"`` (its pre-existing "compact right-aligned row"
    # request); an authored corner-key legend (dep-audit) never does. A
    # caller wanting the plain right-aligned row in the header gets it by
    # setting the same hint explicitly. Within column mode, a caller can
    # separately flip which CORNER the key hugs — ``placement="left"``
    # anchors it under the kicker's own margin instead of the opposite
    # corner (dep-audit-radial's cited hand file; see
    # ``ck._place_legend_column``) — never a "right" value, which this gate
    # already reserves for the row-mode opt-in above.
    legends: list[AnnotationPlacement] = []
    for region_key, group in legend_by_region.items():
        region = regions.get(region_key)
        if region is None:
            raise DiagramInputError(
                f"legend annotation anchors to unknown region {region_key!r}; registered regions: {sorted(regions)}"
            )
        column = region_key == "header" and not any(a.placement == "right" for a in group)
        placed = ck.place_legend(group, region.rect(), ctx.cfg, style, column=column)
        legends.append(replace(placed, region=region_key))
    placed_legends, _ = resolve_generic(placements=legends, obstacles=working, engine=engine)
    # Chrome law: a legend seats at its DECLARED corner (paradigm default
    # right-anchored column; ``placement: left`` the cited per-preset flip).
    # Collision displacement is lawful but never silent — a nudge off the
    # declared seat is logged as a compile note on the rendered record.
    for declared, resolved in zip(legends, placed_legends, strict=True):
        if declared.box is None or resolved.box is None:
            continue
        dx = resolved.box.x - declared.box.x
        dy = resolved.box.y - declared.box.y
        if abs(dx) > 0.5 or abs(dy) > 0.5:
            chrome_notes.append(f"legend displaced ({dx:+.0f},{dy:+.0f})px off its declared corner to clear content")

    # 6. Footer-region growth (a footer-band legend); callout/aside overflow is
    # handled by finish_layout's content-union growth, not here.
    extra_h = _footer_growth(placed_legends, regions["footer"])
    return (tuple(placed_labels) + tuple(caller) + tuple(placed_legends)), extra_h, tuple(chrome_notes)


def _place_caller(
    ann: DiagramAnnotation,
    nodes: list[NodePlacement],
    geo_of: dict[int, EdgeGeo],
    regions: dict[str, Region],
    canvas: RectSpec,
    obstacles: list[Obstacle],
    ctx: SolverContext,
    style: ck.ChromeStyle,
) -> AnnotationPlacement:
    """Place one caller free-text annotation deliberately (obstacle-aware).

    A GRAPH-anchored callout/aside picks a clear zone around its node/edge
    (an edge anchor becomes a zero-size rect at the wire midpoint); a
    POINT-anchored callout/aside (region/at) centres on the point and grows the
    canvas outward when it lands on content; a
    micro-label floats bare at its anchor. A near-seated aside carries no
    leader (see the ASIDE branch below for the growth-mode amendment)."""
    ax, ay, anchor_box = _anchor_box(ann, nodes, geo_of, regions, ctx.edges)
    graph_anchored = bool(ann.node or ann.edge)
    anchor_rect = anchor_box if anchor_box is not None else RectSpec(x=ax, y=ay, w=0.0, h=0.0)
    anchor_node = _node_by_id(nodes, ann.node) if ann.node else None
    anchor_ref = anchor_node.index if anchor_node is not None else -1
    if ann.kind is AnnotationKind.CALLOUT:
        # A graph-anchored callout reads its tie by adjacency (no leader); a
        # point-anchored one has no card, so it keeps a leader to the point.
        if graph_anchored:
            p = place.place_callout(ann, anchor_rect, canvas, obstacles, ctx.cfg, style, anchor_ref=anchor_ref)
        else:
            p = place.place_callout_at_point(ann, ax, ay, canvas, obstacles, ctx.cfg, style)
        return replace(p, kind="callout")
    if ann.kind is AnnotationKind.ASIDE:
        # A margin note: a graph-anchored aside seats NEAR its anchor (the
        # caption-band home is the CALLOUT's; parking a node's margin note
        # in the band read as disconnected float); a point/region aside
        # centres on the point.
        if graph_anchored:
            # 'Near its anchor' must mean near the whole FIGURE, not just the
            # node's geometry box: a glyph-circle's outboard label+desc stack
            # draws outside its box, so a below-seat computed from the box
            # alone lands ON that text (hw_discover). Only the node case
            # needs this — an edge anchor's rect is already a zero-size point.
            aside_anchor = anchor_rect
            if anchor_node is not None:
                aside_anchor = _node_text_box(anchor_node, ctx.cfg)
            p = place.place_aside_near(ann, aside_anchor, canvas, obstacles, ctx.cfg, style, anchor_ref=anchor_ref)
        else:
            p = place.place_aside_point(ann, ax, ay, canvas, obstacles, ctx.cfg, style)
        # AMENDMENT: a near-seated aside carries no leader (the adjacency IS
        # the tie); place_aside_near's growth fallback draws one once the
        # note lands far enough that adjacency reads as lost (the
        # seed-lights-everything float otherwise had zero visual tie to its
        # anchor) — that leader must survive here, not be blanked.
        return replace(p, kind="aside")
    # MICRO_LABEL: bare tracked text floated at the anchor (a declared edge-
    # label-shaped figure), boxed only for the collide pass. Wrapped with the
    # no-truncation wrapper — a declared label never ellipsizes either.
    voice_ml = ctx.cfg.edge_label_voice
    wrapped_ml = place.wrap_full(ann.text, 160.0, voice_ml)
    pitch_ml = voice_ml.size + style.line_pad
    n_ml = len(wrapped_ml)
    runs_ml = tuple(
        DiagramText(x=ax, y=ay + (k - (n_ml - 1) / 2.0) * pitch_ml, text=line, cls="elbl", anchor="middle")
        for k, line in enumerate(wrapped_ml)
    )
    return _label_placement(runs_ml, voice_ml, -1, style)


def _footer_growth(footer_boxed: list[AnnotationPlacement], footer_region: Region) -> float:
    """Extra canvas height a footer-region annotation forces: how far its box
    extends below the footer band's top, rounded up to the pixel grid."""
    grow = 0.0
    for p in footer_boxed:
        if p.box is not None and p.box.y + p.box.h > footer_region.y:
            grow = max(grow, (p.box.y + p.box.h) - footer_region.y)
    return math.ceil(grow / _GRID) * _GRID if grow > 0 else 0.0


def _node_text_box(n: NodePlacement, cfg: Any) -> RectSpec:
    """``n.box`` unioned with any LABEL/DESC-LINE run that falls outside it,
    and the terminal ring (``term_box``) when the node carries one.

    A card/head anatomy keeps every run inside its own box (chrome's
    metric-centered text block asserts this before it ever lays a line), so
    the union is a no-op there. A glyph-circle's outboard label+desc stack
    (chrome.place_circle: ``ly = cy + r + gap`` and the desc further out) and
    a containerless TEXT node's block both draw outside their geometry box —
    invisible to a collision map keyed on ``box`` alone (hw_discover's 'one
    tool call' desc sat directly under an aside seated 'below the anchor
    box', because the anchor obstacle was the CIRCLE alone). Same
    ±ascent/descent convention as radial.py's ``_annotation_line_boxes``
    (the ring arc-clear trim measures the same outboard runs for the same
    reason) — reimplemented here rather than imported, since the two
    consumers need different shapes (a per-line box list there, one union
    rect here). The terminal ring is the SAME invisibility class as the
    glyph-circle's outboard text: a state-machine final's ring floats 6px
    outside its card on every side (graph.py), so an obstacle keyed on
    ``box`` alone let an annotation nest inside the ring's own hairline."""
    x0, y0 = n.box.x, n.box.y
    x1, y1 = n.box.x + n.box.w, n.box.y + n.box.h
    if n.term_box is not None:
        tb = n.term_box
        x0, x1 = min(x0, tb.x), max(x1, tb.x + tb.w)
        y0, y1 = min(y0, tb.y), max(y1, tb.y + tb.h)
    ar, dr = cfg.text_ascent_ratio, cfg.text_descent_ratio
    for t in (n.label, *n.desc_lines):
        if t is None or not t.text:
            continue
        voice = voice_for(cfg, t.cls)
        w = measure_voice(t.text, voice)
        if t.anchor == "middle":
            tx0, tx1 = t.x - w / 2, t.x + w / 2
        elif t.anchor == "end":
            tx0, tx1 = t.x - w, t.x
        else:
            tx0, tx1 = t.x, t.x + w
        ty0, ty1 = t.y - voice.size * ar, t.y + voice.size * dr
        x0, x1 = min(x0, tx0), max(x1, tx1)
        y0, y1 = min(y0, ty0), max(y1, ty1)
    if x0 == n.box.x and y0 == n.box.y and x1 == n.box.x + n.box.w and y1 == n.box.y + n.box.h:
        return n.box
    return RectSpec(x=x0, y=y0, w=x1 - x0, h=y1 - y0)


def _static_obstacles(
    nodes: list[NodePlacement],
    geos: list[EdgeGeo],
    lane_bands: tuple[LaneBand, ...],
    engine: Mapping[str, Any],
    cfg: Any,
) -> list[Obstacle]:
    """Every fixed thing an annotation must avoid, tagged with its source so a
    subsumed label can exclude its OWN incident nodes and wire: node boxes —
    unioned with any outboard text first (``_node_text_box``) — inflated by
    half the minimum clearance, connector polylines (tagged by logical edge
    index) expanded to thin per-segment rects, and lane band strips
    (furniture)."""
    clear = float(engine.get("min_clearance", 18)) / 2
    half_w = float(engine["connector"].get("stroke_width", 1.5)) + 2.0
    obstacles: list[Obstacle] = []
    for n in nodes:
        b = _node_text_box(n, cfg)
        obstacles.append(
            Obstacle(
                box=RectSpec(x=b.x - clear, y=b.y - clear, w=b.w + 2 * clear, h=b.h + 2 * clear),
                kind="node",
                ref=n.index,
            )
        )
    for geo in geos:
        poly = geo.polyline or ((geo.sx, geo.sy), (geo.tx, geo.ty))
        for (x0, y0), (x1, y1) in itertools.pairwise(poly):
            lo_x, hi_x = min(x0, x1), max(x0, x1)
            lo_y, hi_y = min(y0, y1), max(y0, y1)
            obstacles.append(
                Obstacle(
                    box=RectSpec(
                        x=lo_x - half_w, y=lo_y - half_w, w=(hi_x - lo_x) + 2 * half_w, h=(hi_y - lo_y) + 2 * half_w
                    ),
                    kind="edge",
                    ref=geo.index,
                )
            )
    for band in lane_bands:
        obstacles.append(Obstacle(box=band.box, kind="furniture", ref=-1))
    return obstacles


def _node_by_id(nodes: list[NodePlacement], node_id: str) -> NodePlacement:
    for n in nodes:
        if n.node_id == node_id:
            return n
    raise DiagramInputError(f"annotation anchors to node {node_id!r} not found in the solved layout")


def _edge_geo_for(
    edge_ref: str, nodes: list[NodePlacement], geo_of: dict[int, EdgeGeo], edges: tuple[Any, ...]
) -> EdgeGeo:
    """Resolve an edge anchor ref to its geo. The ordinal selects the k-th
    parallel occurrence of the directed pair; the resolved-edge order (source/
    target node indices) selects the geo, and geos key on that same logical
    index, so the k-th matching edge is exact. The referential check in
    ``core/diagram.py`` already proved the ordinal is in range."""
    src, dst, ordinal = parse_edge_ref(edge_ref)
    index = {n.node_id: n.index for n in nodes}
    if src not in index or dst not in index:
        raise DiagramInputError(f"annotation edge anchor {edge_ref!r} names an unplaced node")
    s, t = index[src], index[dst]
    matches = [j for j, e in enumerate(edges) if e.source == s and e.target == t and j in geo_of]
    if not matches:
        raise DiagramInputError(f"annotation edge anchor {edge_ref!r} did not resolve to a placed edge")
    return geo_of[matches[min(ordinal - 1, len(matches) - 1)]]
