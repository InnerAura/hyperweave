"""The authored grouping device — what `regions:` may draw, and when it may not.

A region binds member nodes and draws one box around them. Two regions in one
artifact therefore have to agree about space, and there are exactly three ways
that ends:

CONTAIN — one region's members are a SUBSET of the other's. The outer grows to
hold the inner with the family's nest air on every side. Containment is
DECLARED, read off membership; it is never inferred from where the two boxes
happened to land.

NEIGHBOUR — the member hulls are separable ALONG THE FLOW (one region's members
all sit at earlier ranks than the other's). Two boxes in a row, and the gap
between them has to hold both their pads — a reservation the rank-gridded
solvers make before placement (``flow_gap_reservation``).

NEITHER — the hulls overlap along the flow while the memberships are disjoint.
No pair of rectangles draws that, so nothing is drawn: both regions are
suppressed and the caller is told which members interleave.

The suppression is the load-bearing part. The alternative — draw both boxes and
attach a warning — puts a false picture on the page with a true sentence beside
it, and a reader who does not read the sentence sees a containment nobody
declared. An absent box is honest: ungrouped nodes, plus a note saying why. It
also keeps the compositor and the render sweep from contradicting each other —
a partial overlap is red in the sweep and cannot be produced here.

WHY THIS IS NOT ``regions.py``: that module is the artifact's own region tree
(masthead / content / footer, ``RegionBox``, ``stack_regions``), and
``DiagramLayout.regions`` already means it. This module is the AUTHORED device
the ``regions:`` spec key names. Two meanings of one word, kept in two files.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.axis import DOWN, RIGHT, AxisMap
from hyperweave.compose.diagram.records import DiagramText, LaneBand
from hyperweave.compose.diagram.sizing import CHIP_H, CHIP_PAD_X, voice_for
from hyperweave.compose.matrix.cells import measure_voice
from hyperweave.compose.spatial_records import RectSpec

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
    from hyperweave.core.diagram import DiagramRegion, DiagramSpec


@dataclass(frozen=True, slots=True)
class RegionPads:
    """A region's breathing room, in SCREEN terms — which is how all three hand
    specimens measure it.

    The pads do not transpose with the flow: ``side`` is the x pad on both
    edges and ``top``/``bottom`` are the y pads, whichever way the graph runs,
    because the label always seats in the TOP pad. Only the y-trailing
    CONSTANT is flow-dependent (a vertical band's members spread across the
    flow, so it cites its own 38 where the horizontal cites 12).

    ``along_flow`` is the one place the frame is needed: two regions in a row
    meet on the flow axis, so the reservation asks for that pair specifically."""

    side: float
    top: float
    bottom: float

    def along_flow(self, flow: str) -> tuple[float, float]:
        """``(pad before the first member, pad after the last)`` along the flow.

        Flowing down that is the y pair; flowing right the members run along x
        and both along-flow pads are the same ``side`` value."""
        return (self.top, self.bottom) if flow == "down" else (self.side, self.side)


@dataclass(frozen=True, slots=True)
class RegionHull:
    """One region's members' bounding box, before any pad is added."""

    index: int
    """Position in ``spec.regions`` — the region's identity through the pass."""
    label: str
    major_lo: float
    major_hi: float
    minor_lo: float
    minor_hi: float
    members: frozenset[str]
    """Ids of the members that were actually placed."""


@dataclass(frozen=True, slots=True)
class RegionPlan:
    """The verdict: which regions draw, which nest in which, and what to say
    about the ones that cannot."""

    parent_of: Mapping[int, int]
    """Region index -> the index of the region that CONTAINS it (declared by
    membership subset). Absent for a region nothing contains."""
    suppressed: frozenset[int]
    """Region indices that draw nothing — every region in an unresolvable
    pair. A region not in a pair still draws, so one bad pair never costs a
    third region its box."""
    notes: tuple[str, ...]
    """One human-readable note per unresolvable pair, naming both regions and
    the members that put them there. Rides ``rendered.warnings`` and the
    ``region-overlap`` diagnostic."""


def region_over_arc(reg: DiagramRegion, spec: DiagramSpec) -> bool:
    """Does this region frame an over-arc return? (agent-runtime's AGENT
    RUNTIME control loop — an ``exit: top`` back-edge between two members.)

    Pure in the spec, so the pad it selects is known before placement — which
    is what lets ``flow_gap_reservation`` price a region's pads while the cards
    are still being laid out."""
    if reg.kind != "band":
        return False
    members = set(reg.members)
    return any(e.exit == "top" and e.source in members and e.target in members for e in spec.edges)


def region_pads(
    reg: DiagramRegion,
    *,
    over_arc: bool,
    flow: str,
    on_edge: bool,
    rb: Mapping[str, Any],
    coordinated: bool = False,
) -> RegionPads:
    """Pads DERIVED from what the region frames, cited to ``diagram-frame.yaml``.

    SYMMETRY LAW (all three hand specimens, one rule): a region's two pads on an
    axis are EQUAL, and the only asymmetry allowed is a label seated inside one
    of them — which then equals that label's own measured seating.

      gateway-balanced  h band   side 18/18  flow 26/12  seated strip
      mapreduce band    v band   side 42/42  flow 50/38  seated pill
      mapreduce enclos. v encl   side 65/65  flow 25/25  straddles

    The base pad is the TRAILING one (nothing is seated there); the leading pad
    is ``max(base, seating)``. Writing it this way is what stops a bottom-
    cramped band: the trailing pad had been left at the horizontal citation
    while the leading one grew to hold a chip, so the row sank toward the lower
    border."""
    if reg.kind == "band":
        if over_arc:
            return RegionPads(
                side=float(rb.get("band_over_arc_side_pad", 22)),
                top=float(rb.get("band_over_arc_top_pad", 65)),
                bottom=float(rb.get("band_over_arc_bottom_pad", 13)),
            )
        return _band_pads(flow=flow, rb=rb)
    # ONE BOX RULE, and its precondition: both kinds must seat the label the
    # same way. True flowing down, and true of a coordinating group; false
    # flowing right, where the band seats a header strip inside its leading pad
    # and the enclosure straddles its rim seating nothing.
    if on_edge and (flow == "down" or coordinated):
        return _band_pads(flow=flow, rb=rb)
    # An enclosure label STRADDLES its leading border — its plate is centred ON
    # the hairline, so it seats nothing inside and both pads stay the base. The
    # cited 28 trailing pad is the STRIP grammar's seating (pp-state-machine-
    # alt2's RECOVERY box, "28px bottom (the label strip)"); a family that
    # seats nothing there stays at base.
    base = float(rb.get("enclosure_top_pad", 22))
    return RegionPads(
        side=float(rb.get("enclosure_side_pad", 20)),
        top=base,
        bottom=base if on_edge else float(rb.get("enclosure_bottom_pad", 28)),
    )


def _band_pads(*, flow: str, rb: Mapping[str, Any]) -> RegionPads:
    """The plain band's pads — the ``bottom`` base plus a ``top`` that grew to
    hold whatever the family seats there.

    PER-AXIS CITATION: gateway-balanced's 12 is a band whose members stack
    ALONG the flow; a vertical dag band's members spread ACROSS it and its own
    specimen reads 38. Only the base is cited per axis — the leading pad still
    derives from the seating it holds."""
    bottom = float(rb.get("band_flow_pad_down", 38) if flow == "down" else rb.get("band_bottom_pad", 12))
    seating = (
        float(rb.get("band_label_inset", 12)) + CHIP_H + float(rb.get("band_label_gap", 18))
        if flow == "down"
        else float(rb.get("band_top_pad", 26))  # gateway-balanced's header strip
    )
    return RegionPads(side=float(rb.get("band_side_pad", 18)), top=max(bottom, seating), bottom=bottom)


def coordinated_regions(spec: DiagramSpec, boxes: Mapping[str, RectSpec], *, air: float) -> frozenset[int]:
    """Region indices whose labels must read as ONE row.

    Two regions coordinate when they frame the same row of cards — measured as
    their members' TOP edges landing within the family's own air of each other.
    Flowing right that is two regions side by side on one rank row; flowing
    down it is a nest, and never two stacked siblings, whose member tops are a
    whole run apart.

    Measured on the MEMBER hulls, never on the padded rims, because the pads
    are what this answer decides: asking the rims would make the leading pad a
    function of itself."""
    tops: dict[int, float] = {}
    for i, reg in enumerate(spec.regions):
        seated = [boxes[m] for m in reg.members if m in boxes]
        if seated:
            tops[i] = min(b.y for b in seated)
    return frozenset(i for i, t in tops.items() if any(j != i and abs(t - u) <= air for j, u in tops.items()))


def hull_of(boxes: Iterable[RectSpec]) -> tuple[float, float, float, float]:
    """The screen bounding box of some placed cards, ``(x0, y0, x1, y1)``.

    Every grouping box in the engine starts here, whether its membership was
    authored (``regions:``) or derived by a solver (the unrolled ladder's
    gather arms). Sharing the primitive rather than the caller is what keeps a
    future hull rule — hidden cards, a rotated frame — from reaching one and
    silently skipping the other. Pads are the CALLER's: they are cited to
    different specimens and priced differently."""
    bs = list(boxes)
    return (
        min(b.x for b in bs),
        min(b.y for b in bs),
        max(b.x + b.w for b in bs),
        max(b.y + b.h for b in bs),
    )


def region_hulls(spec: DiagramSpec, boxes: Mapping[str, RectSpec], *, flow: str) -> list[RegionHull]:
    """Each authored region's placed-member bounding box, in flow-frame terms.

    Regions whose members are all unplaced drop out — an authored region over
    nodes the solver never seated has nothing to bound."""
    out: list[RegionHull] = []
    for i, reg in enumerate(spec.regions):
        seated = {m: boxes[m] for m in reg.members if m in boxes}
        if not seated:
            continue
        x0, y0, x1, y1 = hull_of(seated.values())
        major = (y0, y1) if flow == "down" else (x0, x1)
        minor = (x0, x1) if flow == "down" else (y0, y1)
        out.append(
            RegionHull(
                index=i,
                label=reg.label,
                major_lo=major[0],
                major_hi=major[1],
                minor_lo=minor[0],
                minor_hi=minor[1],
                members=frozenset(seated),
            )
        )
    return out


def _member_major(b: RectSpec, flow: str) -> tuple[float, float]:
    return (b.y, b.y + b.h) if flow == "down" else (b.x, b.x + b.w)


def _interleavers(inner: RegionHull, outer: RegionHull, boxes: Mapping[str, RectSpec], *, flow: str) -> tuple[str, ...]:
    """Members of ``inner`` whose along-flow extent falls inside ``outer``'s.

    These are the nodes the author has to move (or re-assign) to make the two
    regions drawable, so naming them is the whole value of the note — "these
    two regions overlap" is not actionable; "`query` sits inside INDEX TIME" is."""
    hits = []
    for m in sorted(inner.members):
        lo, hi = _member_major(boxes[m], flow)
        if lo < outer.major_hi and hi > outer.major_lo:
            hits.append(m)
    return tuple(hits)


def plan_regions(
    spec: DiagramSpec,
    boxes: Mapping[str, RectSpec],
    *,
    flow: str,
    slug: str,
) -> RegionPlan:
    """Classify every region pair: contain, neighbour, or draw neither.

    Runs on PLACED boxes, so it is the same verdict whether the caller is a
    solver building bands or the diagnostics pass re-reading a finished layout
    — one implementation, two readers, no drift."""
    hulls = region_hulls(spec, boxes, flow=flow)
    parent_of: dict[int, int] = {}
    suppressed: set[int] = set()
    notes: list[str] = []
    for a, b in _pairs(hulls):
        # CONTAINMENT IS DECLARED. Membership decides which region is the outer
        # one; geometry never does. (The retired law read containment off
        # rectangle INTERSECTION with an area tie-break, which force-nested two
        # regions whose members were disjoint — see the round record in
        # v04/backlog/v04/diagrams/kit-questions-and-deprecated-kit-pieces.md.)
        if a.members < b.members:
            parent_of[a.index] = b.index
            continue
        if b.members < a.members:
            parent_of[b.index] = a.index
            continue
        if a.major_hi <= b.major_lo or b.major_hi <= a.major_lo:
            continue  # NEIGHBOUR — separable along the flow; the gap holds the pads
        # NEITHER. Both regions lose their box; the note names the members that
        # put them here, in both directions (a region can be broken by one
        # foreign node sitting in its span, and by its own node sitting in the
        # other's).
        suppressed.add(a.index)
        suppressed.add(b.index)
        causes = []
        for inner, outer in ((a, b), (b, a)):
            named = _interleavers(inner, outer, boxes, flow=flow)
            if named:
                causes.append(f"{', '.join(repr(m) for m in named)} within {outer.label!r}")
        cause = "; ".join(causes) if causes else f"{slug} reserves no gap between these regions"
        notes.append(
            f"regions {a.label!r} and {b.label!r} overlap along the flow without one containing "
            f"the other, so neither is drawn ({cause})"
        )
    return RegionPlan(parent_of=parent_of, suppressed=frozenset(suppressed), notes=tuple(notes))


def _pairs(hulls: Sequence[RegionHull]) -> list[tuple[RegionHull, RegionHull]]:
    return [(hulls[i], hulls[j]) for i in range(len(hulls)) for j in range(i + 1, len(hulls))]


def flow_gap_reservation(
    spec: DiagramSpec,
    rank_of: Mapping[str, int],
    *,
    flow: str,
    rb: Mapping[str, Any],
) -> dict[int, float]:
    """Rank -> the gap its boundary must hold so two NEIGHBOUR regions clear.

    Where one region's last member sits at rank ``r-1`` and another's first at
    ``r``, the boundary between them carries both pads plus the family's air:

        need = trail(earlier) + lead(later) + region_nest_air

    Every term is known before placement — kind, over-arc, flow and the config
    block — which is why this can price a gap the cards have not been laid into
    yet. Without it the two pads simply overlap: the vertical rag's band trails
    38 into an enclosure that leads 56, against a 74px rank gap, and the two
    boxes cross by 20px with every member cleanly separated.

    The air is ``region_nest_air`` rather than a second constant: one region's
    distance from another is one idea, whether it sits inside or beside."""
    air = float(rb.get("region_nest_air", 12))
    spans: list[tuple[int, int, float, float]] = []
    for reg in spec.regions:
        ranks = [rank_of[m] for m in reg.members if m in rank_of]
        if not ranks:
            continue
        pads = region_pads(
            reg, over_arc=region_over_arc(reg, spec), flow=flow, on_edge=reg.label_style != "strip", rb=rb
        )
        lead, trail = pads.along_flow(flow)
        spans.append((min(ranks), max(ranks), lead, trail))
    need: dict[int, float] = {}
    for _lo_a, hi_a, _lead_a, trail_a in spans:
        for lo_b, _hi_b, lead_b, _trail_b in spans:
            # ADJACENT ranks only. With a rank sitting between the two regions,
            # that rank's own cards and both its gaps already separate them —
            # reserving here would price air twice.
            if lo_b != hi_a + 1:
                continue
            need[lo_b] = max(need.get(lo_b, 0.0), trail_a + lead_b + air)
    return need


_REGION_RX = 18.0
"""Corner radius every region box draws at. A corner-seated label plate starts
where the region's STRAIGHT edge starts — inside the radius, its own rounded
corner sits on the region's and the pair reads as two overlapping ovals. The
specimen agrees: its band is rx16 at x=60 and its chip starts at x=76."""


def _label_plate(ctx: SolverContext, label: DiagramText, *, anchor: str) -> RectSpec:
    """The opaque chip behind a region label that sits ON its own boundary.

    Measured from the label's own run at the region voice, padded to the chip
    chassis — the same pill vocabulary every on-wire chip uses, so a label
    riding a hairline reads as furniture rather than as text struck through."""
    # Measure in the voice the text ACTUALLY renders in. ``voice_for`` is the
    # one class -> voice map (sizing.VOICE_CLASSES); reaching past it for a
    # hardcoded voice is how a plate ends up sized for 10/400 text while the
    # label draws at 12.5/700 and overflows its own pill by 16px.
    voice = voice_for(ctx.cfg, label.cls)
    w = measure_voice(label.text, voice) + 2 * CHIP_PAD_X
    x = label.x - w / 2 if anchor == "middle" else label.x - CHIP_PAD_X
    # The plate is back-computed from the baseline, so its centre is the
    # baseline MINUS half the ascent — the same one term the other two plate
    # sites derive. A hardcoded 4.0 stood here, solved for a voice this label
    # no longer renders in once the region voice was ruled.
    return RectSpec(
        x=x, y=label.y - CHIP_H / 2 - voice.size * float(ctx.cfg.text_ascent_ratio) / 2, w=w, h=CHIP_H, rx=6.0
    )


def reseat_region_labels(
    ctx: SolverContext,
    bands: tuple[LaneBand, ...],
    geos: list[EdgeGeo],
    cards: Sequence[RectSpec],
    axis: AxisMap,
) -> tuple[LaneBand, ...]:
    """Slide a region label along its own edge until it stops competing.

    Region labels were the ONE annotation class placed by pure formula: a
    corner offset computed before any wire existed, never checked against
    anything. Every other label on the artifact goes through the collision
    ladder. That asymmetry is the whole defect — the corner was chosen to dodge
    the CENTRE thread, and the leftmost branch of a fan then ran straight
    through the word.

    No formula can be safe here, and the specimen shows why rather than
    contradicting it: its pill ends 8px before the first card's arrival thread
    because that file's side pad and its hand-set pill width happen to leave
    the gap. The engine's pill is 22px wider for the same words, so the same
    formula lands 42px inside the thread. What the specimen encodes is the
    RELATION — label clear of the threads — not the offset that achieved it.

    So: keep the cited seat as the preferred one, then slide ALONG the region's
    leading edge (the family's grammar; the edge never changes) to the first
    position clear of every wire and card. Sliding, not pushing — the label
    belongs on that edge."""
    if not bands:
        return bands
    # CARDS, plus the SEATED PLATES of sibling regions. Wires are not an
    # obstacle for this label: its plate is opaque and paints ABOVE the
    # connectors — occlusion is the plate's whole purpose ("the hairline runs
    # behind the plate rather than through the word"), and a wire is the same
    # problem as a border. Cards paint above the plate in turn, so they ARE
    # obstacles — and so is another region's plate: two plates share no
    # reading order, and when one region's members bracket the other's the
    # two leading corners coincide and the inner label rendered buried under
    # the outer one (rag-index-and-query's INDEX TIME under QUERY TIME).
    # Bands resolve in declaration order, each against the plates already
    # seated, so the arbitration is the same anchored near/far ladder.
    seated: list[RectSpec] = []

    def _hits(bx: RectSpec) -> bool:
        return any(
            bx.x < c.x + c.w and bx.x + bx.w > c.x and bx.y < c.y + c.h and bx.y + bx.h > c.y for c in (*cards, *seated)
        )

    out: list[LaneBand] = []
    for lb in bands:
        hb = lb.header_box
        if hb is None:
            out.append(lb)
            continue
        if not _hits(hb):
            seated.append(hb)
            out.append(lb)
            continue
        # ANCHORED seats only. A region label names its region, so it has to
        # read as attached to it — the near corner of the leading edge (the
        # specimen's own seating), or failing that the FAR corner of the same
        # edge. Both are anchors. An earlier cut slid in half-plate steps to
        # the first clear position and produced a label floating mid-edge
        # between two cards, which is clear of everything and means nothing:
        # "avoid collisions" was the wrong objective. If neither corner is
        # free the cited seat stays — a label in the right place slightly
        # crowded beats a label nowhere.
        near = hb.x if axis.flow == "down" else hb.y
        far = (
            lb.box.x + lb.box.w - hb.w - (near - lb.box.x)
            if axis.flow == "down"
            else lb.box.y + lb.box.h - hb.h - (near - lb.box.y)
        )
        best: RectSpec | None = None
        for seat in (near, far):
            cand = replace(hb, x=seat) if axis.flow == "down" else replace(hb, y=seat)
            if not _hits(cand):
                best = cand
                break
        if best is None:
            seated.append(hb)
            out.append(lb)
            continue
        seated.append(best)
        dx, dy = best.x - hb.x, best.y - hb.y
        out.append(replace(lb, header_box=best, header=replace(lb.header, x=lb.header.x + dx, y=lb.header.y + dy)))
    return tuple(out)


def placement_axis(slug: str, boxes: Mapping[str, RectSpec]) -> AxisMap:
    """The axis a figure reads in: the table where it speaks, the placement
    where it does not.

    Neither source is sufficient alone. ``AxisMap.for_slug`` knows only
    dag-vertical, loop and loop-horizontal and hands every other slug the
    identity — a claim about ROUTING, not about where cards landed, which calls
    a stack right-flowing when its cards run down the page. Measuring alone is
    worse: a dag two ranks wide and four members tall spreads further down than
    across and would be read as flowing down, which it does not.

    So the table wins wherever it has an entry, and measurement covers the rest.
    This is the answer for the shared seam, which serves families with no flow
    at all; a solver that flows knows its own axis and passes that instead.
    """
    if AxisMap.maps(slug) or len(boxes) < 2:
        return AxisMap.for_slug(slug)
    xs = [b.x + b.w / 2 for b in boxes.values()]
    ys = [b.y + b.h / 2 for b in boxes.values()]
    return DOWN if (max(ys) - min(ys)) > (max(xs) - min(xs)) else RIGHT


def boxes_by_id(spec: DiagramSpec, placed: Mapping[int, Any]) -> dict[str, RectSpec]:
    """Placed cards keyed by node id — the shape every consumer of this module
    wants, from a solver's index-keyed placement map."""
    order = {n.id: k for k, n in enumerate(spec.nodes) if n.id}
    return {nid: placed[k].box for nid, k in order.items() if k in placed}


def build_region_bands(
    ctx: SolverContext, boxes: Mapping[str, RectSpec], axis: AxisMap
) -> tuple[tuple[LaneBand, ...], tuple[str, ...]]:
    """Authored compound regions → chrome bands, on EVERY topology.

    ``boxes`` is the placed cards by node id — the one thing every solver has
    in the same shape, which is what lets this run once at the shared exit
    seam instead of per family.

    ``axis`` is REQUIRED. It defaulted to ``AxisMap.for_slug`` and two of the
    three call sites took that default silently; the table has no entry for
    ``dag`` or ``state-machine``, so they were riding its RIGHT fallback and
    would have reverted alone the day either gained a transposed cell. A solver
    that flows knows its own axis and passes it; the generic seam, which serves
    families that do not flow at all, measures one.

    Returns the bands plus any NOTES about regions that could not be drawn —
    the caller passes those to ``finish_layout`` so they reach the payload's
    ``rendered.warnings`` and the ``region-overlap`` diagnostic. A region the
    pass suppresses must never leave the artifact silently ungrouped.

    Pads are DERIVED from what a region frames, not authored, and cited to
    ``diagram-frame.yaml``'s ``region_band`` block (each pad traces to a
    hand specimen's own compound-region rect vs. its member cards'); the
    derivation itself lives in ``grouping.region_pads``, which prices them
    before placement too. Two region kinds:

    ENCLOSURE (agent-task-lifecycle's RECOVERY): a DASHED, UNFILLED box around
    the members, uppercase label centred in the bottom strip. Fill and dash are
    what separate the two kinds — ``kind`` is a material, not a size.

    BAND (``kind: band``) is a FILLED panel:

    - A band enclosing an over-arc return (agent-runtime's AGENT RUNTIME
      control loop — an ``exit: top`` back-edge between two members) reserves
      65px above the row so the re-plan bow clears the frame; the tall top pad
      lifts the panel off the row centre and it censuses as its own card. The
      label tags the top-left corner.
    - A band with no over-arc (gateway-balanced's MODEL POOL) is a snug
      header strip with a centred column label. The near-symmetric pads leave
      it concentric with its middle member, so the census coalesces it as
      that member's shell — one shell_mark, not an extra card.
    """
    if not ctx.spec.regions:
        return (), ()
    spec = ctx.spec
    rb = ctx.engine.get("region_band") or {}
    # The label treatment is the REGION's, not the family's. It used to be a
    # config list naming two slugs, so the same declaration got a plate on a dag
    # and bare text everywhere else — and once regions drew on every topology
    # that accident made bare text the majority default. Both treatments are now
    # available everywhere and the plate is the default.
    # CONTAINMENT IS DECLARED, and a pair that resolves to neither containment
    # nor neighbourhood draws NOTHING. Both verdicts live in grouping.py so the
    # solver and the region-overlap diagnostic read one implementation.
    plan = plan_regions(spec, boxes, flow=axis.flow, slug=ctx.slug)
    nest = float(rb.get("region_nest_air", 12))
    coordinated = coordinated_regions(spec, boxes, air=nest)
    bands: list[LaneBand] = []
    rects: list[dict[str, Any]] = []
    for i, reg in enumerate(spec.regions):
        if i in plan.suppressed:
            continue
        member_boxes = [boxes[m] for m in reg.members if m in boxes]
        if not member_boxes:
            continue
        over_arc = region_over_arc(reg, spec)
        on_edge = reg.label_style != "strip"
        pads = region_pads(reg, over_arc=over_arc, flow=axis.flow, on_edge=on_edge, rb=rb, coordinated=i in coordinated)
        rects.append(
            {
                "index": i,
                "reg": reg,
                "over_arc": over_arc,
                "x0": min(mb.x for mb in member_boxes) - pads.side,
                "x1": max(mb.x + mb.w for mb in member_boxes) + pads.side,
                "y0": min(mb.y for mb in member_boxes) - pads.top,
                "y1": max(mb.y + mb.h for mb in member_boxes) + pads.bottom,
            }
        )
    # Growth only, outer over inner, iterated to a fixed point so a declared
    # chain (A in B in C) settles however it was written.
    by_index = {int(r["index"]): r for r in rects}
    for _ in range(max(len(rects), 1)):
        grew = False
        for child_i, parent_i in plan.parent_of.items():
            inner, outer = by_index.get(child_i), by_index.get(parent_i)
            if inner is None or outer is None:
                continue
            want = {
                "x0": inner["x0"] - nest,
                "y0": inner["y0"] - nest,
                "x1": inner["x1"] + nest,
                "y1": inner["y1"] + nest,
            }
            if (
                outer["x0"] > want["x0"]
                or outer["y0"] > want["y0"]
                or outer["x1"] < want["x1"]
                or outer["y1"] < want["y1"]
            ):
                outer["x0"] = min(outer["x0"], want["x0"])
                outer["y0"] = min(outer["y0"], want["y0"])
                outer["x1"] = max(outer["x1"], want["x1"])
                outer["y1"] = max(outer["y1"], want["y1"])
                grew = True
        if not grew:
            break
    # Stacked siblings share a column: the UNION of their cross-flow extents,
    # since their differing widths are an accident of which member happened to
    # be widest. Union, not max — equal widths centred differently would only
    # move the ragged edge. A nest is excluded; its inner stays inset.
    _tied = [
        r for r in rects if int(r["index"]) not in plan.parent_of and int(r["index"]) not in plan.parent_of.values()
    ]
    if len(_tied) > 1:
        lo_k, hi_k = ("x0", "x1") if axis.flow == "down" else ("y0", "y1")
        lo = min(float(r[lo_k]) for r in _tied)
        hi = max(float(r[hi_k]) for r in _tied)
        for r in _tied:
            r[lo_k], r[hi_k] = lo, hi

    # THE FINAL CHECK. Classification decides what to RESERVE; this decides what
    # DRAWS. A neighbour pair on a family that reserves no gap between regions
    # still lands with its pads crossed, and a drawn partial overlap is exactly
    # what the render sweep calls red — so it takes the same absent-box outcome
    # the interleaved pair takes, named rather than shipped.
    rects, late_notes = _drop_crossed_regions(rects, nest, ctx.slug)

    # NESTED-LABEL COORDINATION (owner, 2026-08-27). Nested regions' labels
    # must know what is above and beside them, or each grammar lands its own
    # word a near-miss apart: flowing down the outer's corner plate sat one
    # nest-air higher than the inner's and the stagger read accidental;
    # flowing right the inner band spoke bare centred text next to the
    # outer's straddle plate — two label materials on one nest. So: an OUTER
    # region's corner plate drops to its FIRST inner's own label row (one
    # shared row, the plate arbitration then separates them horizontally),
    # and a NESTED inner band takes the corner-plate grammar whatever the
    # axis, so both labels wear the same material.
    def _contains_rect(o: dict[str, Any], i: dict[str, Any]) -> bool:
        return bool(
            o is not i and o["x0"] <= i["x0"] and o["y0"] <= i["y0"] and o["x1"] >= i["x1"] and o["y1"] >= i["y1"]
        )

    for r in rects:
        inners = [i for i in rects if _contains_rect(r, i)]
        r["inner_y0"] = min((float(i["y0"]) for i in inners), default=None)
        outers = [o for o in rects if _contains_rect(o, r)]
        r["nested"] = bool(outers)
        r["outer_y0"] = min((float(o["y0"]) for o in outers), default=None)
    # Regions that read together share a label row: the topmost rim among
    # them. Membership comes from ``coordinated_regions``.
    for r in rects:
        r["coord_y0"] = (
            min(float(o["y0"]) for o in rects if int(o["index"]) in coordinated)
            if int(r["index"]) in coordinated and len(rects) > 1
            else None
        )
    for r in rects:
        reg = r["reg"]
        on_edge = reg.label_style != "strip"
        over_arc = bool(r["over_arc"])
        x0, x1, y0, y1 = float(r["x0"]), float(r["x1"]), float(r["y0"]), float(r["y1"])
        row_y0 = float(r["inner_y0"]) if axis.flow == "down" and r["inner_y0"] is not None else y0
        if r["coord_y0"] is not None and axis.flow == "right" and not over_arc:
            # One treatment for the whole group: the band's header strip,
            # seated inside the shared leading pad. Not the straddling plate —
            # a plate seats nothing, and the pad-symmetry law then forbids the
            # asymmetric box the group shares. The material follows the pad.
            label = DiagramText(
                x=(x0 + x1) / 2, y=float(r["coord_y0"]) + 16.0, text=reg.label.upper(), cls="rcnt", anchor="middle"
            )
            header_box = None
            ground = "panel" if reg.kind == "band" else "enclosure"
        elif reg.kind == "band":
            # Label seating is AXIS-DEPENDENT, and it is not cosmetic: flowing
            # down, the rank's own centre wire descends through the band's top
            # centre — exactly where a centred label would sit — so the label
            # and the arrival chevron collide. The vertical specimen seats its
            # chip in the top-LEFT corner instead (band 60,284 -> chip 76,296:
            # 16 in, 12 down), which is the same corner grammar the over-arc
            # band already uses. Flowing right the centre wire enters the
            # band's left face, the top centre is clear, and the centred label
            # is the specimen's own reading.
            corner_label = over_arc or axis.flow == "down"
            if corner_label:
                inset = float(rb.get("band_label_inset", 12))
                # The inset is the PLATE's, not the baseline's: `_label_plate`
                # back-computes its box as `baseline - CHIP_H/2 - 4`, so
                # insetting the BASELINE by 12 landed the plate flush ON the
                # border at inset 0. The specimen seats its pill 12px inside
                # (region 284, pill 296..316), so solve for the baseline that
                # puts the PLATE where the law says.
                label = DiagramText(
                    x=x0 + _REGION_RX + CHIP_PAD_X,
                    y=row_y0 + inset + CHIP_H / 2 + 4.0,
                    text=reg.label.upper(),
                    cls="rcnt",
                )
                header_box = _label_plate(ctx, label, anchor="start") if on_edge else None
            else:
                label = DiagramText(x=(x0 + x1) / 2, y=y0 + 16.0, text=reg.label.upper(), cls="rcnt", anchor="middle")
                header_box = None
            ground = "panel"
        else:
            if not on_edge:
                # The STRIP grammar (agent-task-lifecycle's RECOVERY): the label
                # sits inside the box along its trailing edge with no plate.
                # state-machine cites this; dag cites the on-edge chip below.
                # Two specimens, two families, both right about their own.
                label = DiagramText(x=(x0 + x1) / 2, y=y1 - 10.0, text=reg.label.upper(), cls="rcnt", anchor="middle")
                header_box = None
            elif axis.flow == "down":
                # INSIDE the leading pad, at the corner — identical to the
                # band. Straddling is right flowing RIGHT, where edges arrive
                # on the left face and the top edge is free; flowing DOWN the
                # leading edge is exactly where every arrowhead lands, and a
                # straddling plate sat 1px off the nearest one. Which edge is
                # free is an axis fact, not a region-kind fact.
                inset = float(rb.get("band_label_inset", 12))
                label = DiagramText(
                    x=x0 + _REGION_RX + CHIP_PAD_X,
                    y=row_y0 + inset + CHIP_H / 2 + 4.0,
                    text=reg.label.upper(),
                    cls="rcnt",
                )
                header_box = _label_plate(ctx, label, anchor="start")
            else:
                # Straddle the LEADING edge, centred — the dag-mapreduce
                # enclosure's own seating (a 144x20 chip whose centre sits on
                # the region's top edge at y=66, so the hairline runs behind
                # the plate rather than through the word). The plate is what
                # makes an on-boundary label legible at all; without it the
                # border strikes the text. A region that COORDINATES never
                # reaches here — it took the group's shared header strip above.
                label = DiagramText(x=(x0 + x1) / 2, y=y0 + 4.0, text=reg.label.upper(), cls="rcnt", anchor="middle")
                header_box = _label_plate(ctx, label, anchor="middle")
            ground = "enclosure"
        bands.append(
            LaneBand(
                box=RectSpec(x=x0, y=y0, w=x1 - x0, h=y1 - y0, rx=_REGION_RX),
                header=label,
                ground=ground,
                header_box=header_box,
                outline=reg.kind != "band",
                region_id=reg.label,
            )
        )
    return tuple(bands), plan.notes + late_notes


def _drop_crossed_regions(
    rects: list[dict[str, Any]], nest: float, slug: str
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """Suppress any pair of region rects that CROSSES — intersects without one
    containing the other.

    The verdict pass upstream decides what to reserve; this decides what draws,
    and it grades the rectangles that actually came out. It exists for the case
    the verdict cannot price: two regions the spec declares as neighbours, on a
    family with no gap reservation between regions, whose pads meet anyway. The
    verdict says "drawable", the geometry says otherwise, and the geometry is
    the thing on the page.

    Dropping both is the same outcome an interleaved pair takes, for the same
    reason: two crossed boxes assert a containment nobody declared, and it is
    what the render sweep calls red. An absent box plus a named note is honest,
    and it keeps the compositor from emitting what the gate forbids."""

    def crossed(a: dict[str, Any], b: dict[str, Any]) -> bool:
        if not (a["x0"] < b["x1"] and a["x1"] > b["x0"] and a["y0"] < b["y1"] and a["y1"] > b["y0"]):
            return False
        return not (_holds(a, b, nest) or _holds(b, a, nest))

    doomed: set[int] = set()
    notes: list[str] = []
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if not crossed(rects[i], rects[j]):
                continue
            doomed.add(i)
            doomed.add(j)
            notes.append(
                f"regions {rects[i]['reg'].label!r} and {rects[j]['reg'].label!r} sit side by side but their "
                f"frames cross, so neither is drawn ({slug} reserves no gap between regions here)"
            )
    return [r for k, r in enumerate(rects) if k not in doomed], tuple(notes)


def _holds(outer: dict[str, Any], inner: dict[str, Any], nest: float) -> bool:
    """Does ``outer`` contain ``inner`` with the family's air on every side?"""
    return bool(
        float(outer["x0"]) <= float(inner["x0"]) - nest + _NEST_SLACK
        and float(outer["y0"]) <= float(inner["y0"]) - nest + _NEST_SLACK
        and float(outer["x1"]) >= float(inner["x1"]) + nest - _NEST_SLACK
        and float(outer["y1"]) >= float(inner["y1"]) + nest - _NEST_SLACK
    )


_NEST_SLACK = 0.5
"""Float-comparison slack on the nest-air containment test. The growth pass
sets each edge to exactly ``inner ± nest``, so an exact ``>=`` compares two
values that travelled through different float sums; half a pixel is below the
0.1px the renderer rounds to and cannot mask a real crossing."""
