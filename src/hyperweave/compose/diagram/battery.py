"""Layout self-consistency batteries — hard laws on a SOLVED layout.

The corpus's time-domain QA, enrolled as pipeline law (cycle-expression-map:
"a motion checker in the pipeline — park-invisible, full-exit, occlusion
ratio, minimum visible runs as hard asserts"). Runs inside the resolver
AFTER layout + choreography. A failure here means the engine broke its own
geometric or motion contract on an input that was otherwise legal — it
raises a typed ``HwError`` with code ``ENGINE_INVARIANT`` (an engine fault,
500-class, CLI exit 70), never ``DiagramInputError`` (the caller asked for
something lawful and the engine failed while building it) and never a bare
``AssertionError`` (which escapes every surface as a traceback and vanishes
under ``python -O``).

The one exception is the chip-air battery, which classifies by the owner's
reseat-then-classify ruling: a colliding pill pair is first RESEATED along
its own run; success composes with a ``chip-air`` advisory diagnostic
recording the near miss, and only a pair no lawful seat can separate becomes
an author-repairable ``SPEC_INVALID`` naming both chips and the measured gap.

Checks:
* endpoint standoffs — every connector arrival lands 0-3.5px off its
  target's boundary (the corpus asserts 0.5-3.5; 0 covers flush merges);
* guard-chip occlusion — a chip straddling its wire covers at most 1/3 of
  the run and leaves a visible run each side (>=30px on the long rail legs,
  relaxed pro-rata on runs shorter than 3 chips);
* geometric seating — a chip's center sits ON its wire (never a floating
  path-parameter guess);
* park-invisible / full-exit — every choreographed pulse rests entirely
  before its path (+dash) and exits entirely past it (-length).
"""

from __future__ import annotations

import dataclasses
import itertools
import math
import re
from typing import TYPE_CHECKING

from hyperweave.compose.geometry.bounds import inflate, segment_crosses_box
from hyperweave.compose.geometry.paths import flatten_points
from hyperweave.core.diagnostics import Diagnostic
from hyperweave.core.errors import HwError, HwErrorCode

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from hyperweave.compose.diagram.records import AnnotationPlacement, DiagramLayout, NodePlacement
    from hyperweave.compose.spatial_records import RectSpec

_SEAT_SAMPLES = 16
"""Bezier samples per segment for seat and run measurements — the even coverage
the chip ladder needs, reproduced through the one path parser. A judgement
that needs a bound flattens adaptively instead (``flatten_points(d)``)."""


def _fault(message: str) -> HwError:
    """A typed engine fault — the battery's own measurement is the evidence."""
    return HwError(
        HwErrorCode.ENGINE_INVARIANT,
        message,
        fix="this is an engine fault, not a spec problem — report it with the spec that produced it",
    )


def _law(condition: bool, message: str) -> None:
    """Hard law: raise a typed engine fault when ``condition`` fails."""
    if not condition:
        raise _fault(message)


CHIP_OCCLUSION_MAX = 1 / 3
CHIP_VISIBLE_RUN_MIN = 30.0
_CONDUIT_ENDPOINT_TOL = 48.0
"""How far apart a conduit's two channels may face each other and still be
recognised as one round trip: the lane gap plus the pill air it reserves."""
_RIDING_SEAT_TOL = 8.0
"""How near a stroke a pill's centre must sit to count as RIDING it.

Calibrated from the corpus, not chosen: of 81 bundled chips, 78 sit 0.0-2.2px
off the wire they ride and the state-machine back-arc pair (sm-terminal's
throw/retry) sits at 7.5 on its lens, while every genuinely floated seat this
wave introduces lands 22px or further out. 8.0 separates the two populations
with room on both sides. A tighter 1.0 called most of the corpus floated —
riding is a seat, not a sub-pixel coincidence."""
_CONDUIT_ENDPOINT_SLACK = 1.0
"""How far inside its own card a departure may sit before it is a defect —
a rounding hair, not a trim."""
_CONDUIT_STUB_MIN = 18.4
"""Visible wire each side of a conduit chip — the same floor a chip reserves
anywhere else (sizing.CHIP_STUB_MIN), restated here so the battery grades the
RENDER without importing the solver's sizing seam."""
"""The enrolled loop law (cycle-expression-map, corrected from 40 against
the v4 corpus): a straddling chip leaves at least this much bare wire each
side."""
STANDOFF_MAX = 3.5


def run_loop_battery(layout: DiagramLayout) -> None:
    """No-op off the loop family; hard-asserts on it."""
    if not layout.layout_slug.startswith("loop"):
        return
    _check_standoffs(layout)
    _check_chip_seating(layout)
    _check_chip_foreign_wires(layout)
    _check_pulses(layout)
    _check_meter_seating(layout)


def _box_distance(x: float, y: float, box: RectSpec) -> float:
    dx = max(box.x - x, x - (box.x + box.w), 0.0)
    dy = max(box.y - y, y - (box.y + box.h), 0.0)
    return math.hypot(dx, dy)


def _check_meter_seating(layout: DiagramLayout) -> None:
    """The meter kit piece seats clear: its plate stays inside the canvas
    and never overlaps a node card (it may — deliberately — sit on its own
    rail run, exactly as its chip does), and every segment stays inside the
    plate."""
    for m in layout.meters:
        p = m.plate
        _law(
            p.x >= 0 and p.y >= 0 and p.x + p.w <= layout.width and p.y + p.h <= layout.height,
            f"meter plate leaves the canvas: ({p.x},{p.y}) {p.w}x{p.h} on {layout.width}x{layout.height}",
        )
        for n in layout.nodes:
            b = n.box
            overlap_x = min(p.x + p.w, b.x + b.w) - max(p.x, b.x)
            overlap_y = min(p.y + p.h, b.y + b.h) - max(p.y, b.y)
            _law(
                overlap_x <= 0 or overlap_y <= 0,
                f"meter plate overlaps node {n.node_id!r}: plate ({p.x},{p.y}) {p.w}x{p.h} vs box ({b.x},{b.y})",
            )
        for sb in m.boxes:
            _law(
                sb.x >= p.x - 0.5
                and sb.y >= p.y - 0.5
                and sb.x + sb.w <= p.x + p.w + 0.5
                and sb.y + sb.h <= p.y + p.h + 0.5,
                "meter segment escapes its plate",
            )


def _check_standoffs(layout: DiagramLayout) -> None:
    by_index = {n.index: n for n in layout.nodes}
    polylines = [(c.index, flatten_points(c.path_d, curve_samples=_SEAT_SAMPLES)) for c in layout.connectors]
    for c in layout.connectors:
        target = by_index.get(c.target_index)
        if target is None:
            continue  # scope arrivals anchor on the enclosure band
        pts = flatten_points(c.path_d, curve_samples=_SEAT_SAMPLES)
        if not pts:
            continue
        x, y = pts[-1]
        d = _box_distance(x, y, target.box)
        if d > STANDOFF_MAX:
            # A gather-bus ARM lawfully ends on the JUNCTION — its arrival
            # completes through the stem, so its endpoint sits ON another
            # connector's run instead of the target's face.
            on_a_wire = any(
                other_i != c.index
                and len(other) >= 2
                and min(_segment_distance(x, y, other[i], other[i + 1]) for i in range(len(other) - 1)) <= 1.0
                for other_i, other in polylines
            )
            if on_a_wire:
                continue
        _law(
            d <= STANDOFF_MAX,
            f"loop battery: connector {c.index} arrives {d:.2f}px off its target "
            f"(the family standoff law holds arrivals within {STANDOFF_MAX}px)",
        )


def _check_chip_seating(layout: DiagramLayout) -> None:
    conn = {c.index: c for c in layout.connectors}
    for a in layout.annotations:
        if a.kind != "edge-chip" or a.edge_index < 0 or a.box is None:
            continue
        c = conn.get(a.edge_index)
        if c is None:
            continue
        cx, cy = a.box.x + a.box.w / 2, a.box.y + a.box.h / 2
        # Geometric seating: the chip's center lies ON its wire (measured
        # against the SAMPLED path — the curve, never its control polygon).
        pts = flatten_points(c.path_d, curve_samples=_SEAT_SAMPLES)
        best_i = min(range(len(pts) - 1), key=lambda i: _segment_distance(cx, cy, pts[i], pts[i + 1]))
        seat_error = _segment_distance(cx, cy, pts[best_i], pts[best_i + 1])
        _law(
            seat_error <= 8.0,
            f"loop battery: guard chip for edge {a.edge_index} floats {seat_error:.1f}px off its wire "
            "(chips seat at named geometry, never a path parameter)",
        )
        # Occlusion: the chip's span ALONG the run (the box's projection on
        # the local wire direction — a 26-tall chip on a vertical run spends
        # 26, not its width) leaves visible wire each side.
        ax_, ay_ = pts[best_i]
        bx_, by_ = pts[best_i + 1]
        seg = math.hypot(bx_ - ax_, by_ - ay_) or 1.0
        ux, uy = (bx_ - ax_) / seg, (by_ - ay_) / seg
        span = abs(a.box.w * ux) + abs(a.box.h * uy)
        # The RUN the law grades: a curve reads whole (the corpus's fork
        # chips measure against their full 155px sweeps); an orthogonal
        # route reads its seat LEG (the rail chip owns the entry run, never
        # the whole rail).
        run = c.length if "C" in c.path_d.upper() else _colinear_run(pts, best_i)
        if run > 0:
            ratio = span / run
            visible = (run - span) / 2
            cited = layout.chip_visible_run
            if cited:
                # The spec's own density citation (the caps-lift pattern):
                # the run holds the chip plus 2x the CITED visible run —
                # the ratio term is the citation's to waive, and the
                # default law stands everywhere uncited.
                _law(
                    visible >= cited - 0.5,
                    f"loop battery: guard chip for edge {a.edge_index} leaves {visible:.1f}px visible "
                    f"each side against its spec's own {cited:.0f}px citation",
                )
            else:
                _law(
                    ratio <= CHIP_OCCLUSION_MAX and visible >= CHIP_VISIBLE_RUN_MIN - 0.5,
                    f"loop battery: guard chip for edge {a.edge_index} occludes {ratio:.0%} of its "
                    f"{run:.0f}px run with {visible:.1f}px visible each side "
                    f"(the enrolled law: <=1/3 occlusion with >={CHIP_VISIBLE_RUN_MIN:.0f}px visible per side)",
                )


def _colinear_run(pts: list[tuple[float, float]], i: int, tol_deg: float = 10.0) -> float:
    """The chip's own RUN: the chain of near-colinear segments around its
    seat. On an orthogonal rail this is exactly the seat leg (a 90° corner
    breaks the chain); on a sampled curve the gentle per-segment turn chains
    the whole sweep — matching how the corpus reads occlusion per run."""
    import math as _m

    def _unit(j: int) -> tuple[float, float]:
        dx, dy = pts[j + 1][0] - pts[j][0], pts[j + 1][1] - pts[j][1]
        n = _m.hypot(dx, dy) or 1.0
        return dx / n, dy / n

    def _seg_len(j: int) -> float:
        return _m.hypot(pts[j + 1][0] - pts[j][0], pts[j + 1][1] - pts[j][1])

    cos_tol = _m.cos(_m.radians(tol_deg))
    total = _seg_len(i)
    ux, uy = _unit(i)
    j = i - 1
    while j >= 0:
        vx, vy = _unit(j)
        if ux * vx + uy * vy < cos_tol:
            break
        total += _seg_len(j)
        j -= 1
    j = i + 1
    while j < len(pts) - 1:
        vx, vy = _unit(j)
        if ux * vx + uy * vy < cos_tol:
            break
        total += _seg_len(j)
        j += 1
    return total


def _segment_distance(px: float, py: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    qx, qy = ax + t * dx, ay + t * dy
    return math.hypot(px - qx, py - qy)


def _check_chip_foreign_wires(layout: DiagramLayout) -> None:
    """A chip straddles ITS OWN wire and no other: its box (plus a hair of
    air) never crosses a foreign connector's run — the flywheel's compounding
    chip once reached back over the spine's Distribute -> Capture wire, and
    nothing said so until a human looked."""
    own_by_index = {c.index: flatten_points(c.path_d, curve_samples=_SEAT_SAMPLES) for c in layout.connectors}
    for a in layout.annotations:
        if a.kind != "edge-chip" or a.box is None:
            continue
        b = a.box
        chip_box = inflate(b, 2.0)
        own = own_by_index.get(a.edge_index, [])
        own_in_box = any(segment_crosses_box(own[i], own[i + 1], chip_box) for i in range(len(own) - 1))
        for c in layout.connectors:
            if c.index == a.edge_index:
                continue
            pts = flatten_points(c.path_d, curve_samples=_SEAT_SAMPLES)
            for i in range(len(pts) - 1):
                if segment_crosses_box(pts[i], pts[i + 1], chip_box):
                    if own_in_box:
                        # The declared crossing: where a chip's OWN wire and
                        # the foreign one cross inside the chip, the chip
                        # covers the intersection deliberately (the swimlane
                        # specimen's handoff guard sits exactly on the one
                        # crossing — "routing around it would cost more than
                        # it buys", its own tradeoff record verbatim).
                        continue
                    raise _fault(
                        f"loop battery: guard chip for edge {a.edge_index} overlaps connector "
                        f"{c.index}'s wire — a chip straddles its own wire and no other"
                    )


def _check_pulses(layout: DiagramLayout) -> None:
    plan = layout.choreography
    if plan is None:
        return
    lengths = {c.index: c.length for c in layout.connectors}
    # The overlays ride the route trimmed at the arrowhead's base — the
    # trail's own park offset IS the effective run the head must fully exit.
    runs = {tr.connector_index: tr.rest_offset for tr in plan.trails}
    for tr in plan.trails:
        body = plan.keyframes[tr.anim_index].body
        offsets = [float(v) for v in re.findall(r"stroke-dashoffset:(-?[\d.]+)", body)]
        _law(
            bool(offsets) and abs(max(offsets) - tr.rest_offset) < 0.6 and tr.rest_offset > 0,
            f"loop battery: trail on connector {tr.connector_index} never parks invisible",
        )
        _law(min(offsets) >= -0.01, f"loop battery: trail on connector {tr.connector_index} overshoots its own wire")
        _law(
            abs(offsets[-1] - tr.rest_offset) < 0.6,
            f"loop battery: trail on connector {tr.connector_index} ends lit — the route clears at the wrap",
        )
    for p in plan.pulses:
        body = plan.keyframes[p.anim_index].body
        offsets = [float(v) for v in re.findall(r"stroke-dashoffset: ?(-?[\d.]+)", body)]
        _law(
            bool(offsets) and max(offsets) == p.rest_offset > 0,
            f"loop battery: pulse on connector {p.connector_index} never parks invisible",
        )
        run = runs.get(p.connector_index, lengths[p.connector_index])
        _law(
            min(offsets) <= -run + 0.01,
            f"loop battery: pulse on connector {p.connector_index} stops mid-wire "
            f"(sweeps to {min(offsets)} on a {run:.0f}px run — full exit is the law)",
        )


_RESEAT_ROUNDS = 4
"""How many colliding pairs one figure may reseat before the density itself is
the finding — each round separates the worst pair, so exhausting the budget
means the author's label density outruns the runs available to carry it."""


def _pill_gap(a: RectSpec, b: RectSpec) -> float:
    gap_x = max(a.x - (b.x + b.w), b.x - (a.x + a.w))
    gap_y = max(a.y - (b.y + b.h), b.y - (a.y + a.h))
    return max(gap_x, gap_y)


def _boxes_overlap(a: RectSpec, b: RectSpec) -> bool:
    return min(a.x + a.w, b.x + b.w) > max(a.x, b.x) and min(a.y + a.h, b.y + b.h) > max(a.y, b.y)


def _worst_fused_pair(
    chips: list[AnnotationPlacement], air: float
) -> tuple[AnnotationPlacement, AnnotationPlacement, float] | None:
    worst: tuple[AnnotationPlacement, AnnotationPlacement, float] | None = None
    for a, b in itertools.combinations(chips, 2):
        if a.box is None or b.box is None:
            continue
        gap = _pill_gap(a.box, b.box)
        if gap < air - 0.5 and (worst is None or gap < worst[2]):
            worst = (a, b, gap)
    return worst


def _seat_visible_run(pts: list[tuple[float, float]], box: RectSpec) -> float:
    """The tighter visible stub either side of a pill's seat on its own leg."""
    if len(pts) < 2:
        return 0.0
    cx, cy = box.x + box.w / 2, box.y + box.h / 2
    best_i = min(range(len(pts) - 1), key=lambda i: _segment_distance(cx, cy, pts[i], pts[i + 1]))
    near, far = _leg_stubs(pts, best_i, box)
    return min(near, far)


def _translate_annotation(a: AnnotationPlacement, dx: float, dy: float) -> AnnotationPlacement:
    box = a.box
    if box is None:
        return a
    moved = dataclasses.replace(box, x=box.x + dx, y=box.y + dy)
    lines = tuple(dataclasses.replace(t, x=t.x + dx, y=t.y + dy) for t in a.lines)
    return dataclasses.replace(a, box=moved, lines=lines)


def _reseat_candidates(
    layout: DiagramLayout, chips: list[AnnotationPlacement], moving: AnnotationPlacement, air: float
) -> list[tuple[float, float, float]]:
    """Lawful alternate seats for one pill along its OWN connector, nearest
    first: air to every other pill holds, the pill stays on the canvas and off
    the node cards, and its visible-stub read never gets worse than the seat
    it left. Riding its own wire is true by construction (candidates are the
    wire's own sampled points)."""
    if moving.box is None or moving.edge_index < 0:
        return []
    conn = next((c for c in layout.connectors if c.index == moving.edge_index), None)
    if conn is None:
        return []
    pts = _densify_path(flatten_points(conn.path_d, curve_samples=_SEAT_SAMPLES), samples=96)
    if len(pts) < 2:
        return []
    box = moving.box
    cx, cy = box.x + box.w / 2, box.y + box.h / 2
    floor_visible = min(CHIP_VISIBLE_RUN_MIN, max(_seat_visible_run(pts, box), 0.0))
    others = [c for c in chips if c is not moving and c.box is not None]
    node_boxes = [n.box for n in layout.nodes]
    margin = max(1, len(pts) // 8)  # keep off the departure and arrowhead zones
    scored: list[tuple[float, float, float]] = []
    for x, y in pts[margin : len(pts) - margin]:
        dx, dy = x - cx, y - cy
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            continue
        nb = dataclasses.replace(box, x=box.x + dx, y=box.y + dy)
        if nb.x < 0 or nb.y < 0 or nb.x + nb.w > layout.width or nb.y + nb.h > layout.height:
            continue
        if any(o.box is not None and _pill_gap(nb, o.box) < air - 0.5 for o in others):
            continue
        if any(_boxes_overlap(nb, b) for b in node_boxes):
            continue
        if _seat_visible_run(pts, nb) < floor_visible - 0.5:
            continue
        scored.append((dist, dx, dy))
    scored.sort()
    return [(dx, dy, dist) for dist, dx, dy in scored]


def run_chip_air_battery(
    layout: DiagramLayout, engine: Mapping[str, Any] | None = None
) -> tuple[DiagramLayout, tuple[Diagnostic, ...]]:
    """No two pills fuse — FAMILY-WIDE, on every topology.

    Deliberately not a trigger for anything and not scoped to the shape that
    prompted it: two plates closer than the air floor read as one plate
    whatever seated them, so this grades the outcome rather than any
    particular cause, and it will catch fusion on shapes the seat laws do not
    yet describe. Kept separate from the duplex dialogue seats for the same
    reason — a seat rule that also policed its own result could only ever
    check the cases it already knew about.

    Classification is the owner's reseat-then-classify ruling (2026-08-30):

    1. a colliding pair is RESEATED along its own run — success composes,
       with a ``chip-air`` advisory diagnostic recording the near miss;
    2. a pair no lawful seat can separate is the author's density, not the
       engine's geometry — ``SPEC_INVALID`` naming both chips and the
       measured gap;
    3. every other battery law stays a typed engine fault
       (``ENGINE_INVARIANT``), because those grade geometry the caller
       cannot lawfully influence.

    Returns the (possibly reseated) layout plus the advisory diagnostics.
    """
    air = 6.0
    if engine is not None:
        air = float((engine.get("connector") or {}).get("chip_pill_air", 6))
    chips = [a for a in layout.annotations if a.kind == "edge-chip" and a.box is not None]
    _check_no_wire_through_pill(layout, chips)
    diags: list[Diagnostic] = []
    for _ in range(_RESEAT_ROUNDS):
        pair = _worst_fused_pair(chips, air)
        if pair is None:
            break
        a, b, gap = pair
        moved: tuple[AnnotationPlacement, AnnotationPlacement, float] | None = None
        for cand in (a, b):
            idx = next(i for i, c in enumerate(chips) if c is cand)
            for dx, dy, dist in _reseat_candidates(layout, chips, cand, air):
                replacement = _translate_annotation(cand, dx, dy)
                tentative_chips = [replacement if c is cand else c for c in chips]
                tentative = dataclasses.replace(
                    layout,
                    annotations=tuple(replacement if ann is cand else ann for ann in layout.annotations),
                )
                # A candidate is lawful only if the WHOLE geometry stays
                # lawful after the move — the seat checks above are local,
                # but a reseated pill can land on a foreign wire or break a
                # loop/duplex law the earlier batteries already cleared.
                try:
                    _check_no_wire_through_pill(tentative, tentative_chips)
                    run_loop_battery(tentative)
                    run_duplex_battery(tentative)
                except HwError:
                    continue
                chips[idx] = replacement
                layout = tentative
                moved = (cand, replacement, dist)
                break
            if moved is not None:
                break
        if moved is None:
            break
        at = " ".join(t.text for t in a.lines)
        bt = " ".join(t.text for t in b.lines)
        diags.append(
            Diagnostic(
                rule="chip-air",
                measured=f"pills {at!r} and {bt!r} sat {gap:.1f}px apart; one reseated {moved[2]:.0f}px along its run",
                band=f">={air:g}px air",
                suggestion="the reseat held the law — shorten a label if the new seat reads far from its wire",
            )
        )
    pair = _worst_fused_pair(chips, air)
    if pair is not None:
        a, b, gap = pair
        at = " ".join(t.text for t in a.lines)
        bt = " ".join(t.text for t in b.lines)
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            f"chip battery: pills {at!r} and {bt!r} sit {gap:.1f}px apart (law >={air:g}px) and no lawful "
            f"reseat separates them — two plates that close read as one",
            fix="shorten or drop one of the two labels, or thin the chip density around this run",
        )
    return layout, tuple(diags)


def run_duplex_battery(layout: DiagramLayout) -> None:
    """Hard asserts on a solved layout's DUPLEX CONDUITS — the dag family's
    request/response pairs.

    A conduit is recovered from geometry rather than from solver bookkeeping:
    two connectors whose endpoints are each other's, reversed, are the two
    channels of one round trip. That keeps the check honest about what
    rendered — a conduit that lost its pairing somewhere between the solver
    and the emitter simply stops being found, and its chips are then graded
    by the ordinary laws instead of silently exempted.
    """
    if not layout.layout_slug.startswith("dag"):
        return
    _check_duplex_conduits(layout)
    _check_conduit_endpoints(layout)
    _check_conduit_face_planarity(layout)
    _check_channel_chip_stubs(layout)
    _check_slot_corner_zone(layout)


def _conduit_pairs(layout: DiagramLayout) -> list[tuple[int, int]]:
    """Index pairs of connectors that run the same corridor in opposite
    directions — endpoints swapped within the lane gap that separates them."""
    ends: dict[int, tuple[tuple[float, float], tuple[float, float]]] = {}
    for c in layout.connectors:
        pts = flatten_points(c.path_d, curve_samples=_SEAT_SAMPLES)
        if len(pts) >= 2:
            ends[c.index] = (pts[0], pts[-1])
    out: list[tuple[int, int]] = []
    seen: set[int] = set()
    for i, (si, ti) in ends.items():
        if i in seen:
            continue
        for k, (sk, tk) in ends.items():
            if k <= i or k in seen:
                continue
            # Reversed within a generous tolerance: the two channels are
            # offset by the lane gap, so their endpoints never coincide
            # exactly — they face each other across it.
            if math.hypot(si[0] - tk[0], si[1] - tk[1]) < _CONDUIT_ENDPOINT_TOL and (
                math.hypot(ti[0] - sk[0], ti[1] - sk[1]) < _CONDUIT_ENDPOINT_TOL
            ):
                out.append((i, k))
                seen.add(i)
                seen.add(k)
                break
    return out


def _check_duplex_conduits(layout: DiagramLayout) -> None:
    """A conduit wears NO chip pill — the bracket law.

    A pill on one lane of a duplex occludes the partner lane by
    construction (the pill's across-run extent exceeds the lane gap), so
    the chip home does not exist on a conduit any more than on a bent wire;
    a conduit's labels render as the bare micro-label bracket. Graded on
    the drawn result so a pill that leaks back through ANY seam is refused
    whatever seated it. This replaced the pill-overlap and conduit-stub
    checks, both vacuous once no pill may exist here; the leg-stub law
    lives on in ``_check_channel_chip_stubs`` for the single-edge pills
    that still ride channel legs.
    """
    chips = {a.edge_index for a in layout.annotations if a.kind == "edge-chip" and a.box is not None}
    for i, k in _conduit_pairs(layout):
        for idx in (i, k):
            if idx in chips:
                raise _fault(
                    f"duplex battery: conduit channel {idx} wears a chip pill — a pill on one lane "
                    f"occludes the partner lane, so a conduit's labels are the bare bracket, never chips"
                )


def _check_channel_chip_stubs(layout: DiagramLayout) -> None:
    """A pill riding an ORTHOGONAL route shows visible wire both sides of
    its own LEG.

    Scoped to chips whose connector draws the detour grammar — straight
    legs joined by Q fillets, no cubic — because that is where a chord
    figure lies about the run: the seat leg is what carries the pill, and
    a leg sized to the riser centre instead of the fillet start starves a
    stub the reservation promised. Rank S-curves and gather trunks grade
    under their own laws; a floated pill has no leg to grade.
    """
    for a in layout.annotations:
        if a.kind != "edge-chip" or a.box is None or a.edge_index < 0:
            continue
        conn = next((c for c in layout.connectors if c.index == a.edge_index), None)
        if conn is None or "C" in conn.path_d or "Q" not in conn.path_d:
            continue
        pts = flatten_points(conn.path_d, curve_samples=_SEAT_SAMPLES)
        if len(pts) < 2:
            continue
        cx, cy = a.box.x + a.box.w / 2, a.box.y + a.box.h / 2
        best_i = min(range(len(pts) - 1), key=lambda s: _segment_distance(cx, cy, pts[s], pts[s + 1]))
        if _segment_distance(cx, cy, pts[best_i], pts[best_i + 1]) > _RIDING_SEAT_TOL:
            continue
        near, far = _leg_stubs(pts, best_i, a.box)
        visible = min(near, far)
        if visible < _CONDUIT_STUB_MIN - 0.5:
            raise _fault(
                f"chip battery: the pill on channel-routed edge {a.edge_index} leaves {visible:.1f}px of "
                f"visible wire on its short side (law >={_CONDUIT_STUB_MIN:g}px) — a pill with no thread "
                f"reads as a label floating between two cards, not as that leg's"
            )


def _leg_stubs(pts: list[tuple[float, float]], i: int, box: RectSpec) -> tuple[float, float]:
    """Visible wire each side of a pill on ITS OWN LEG.

    The leg is the chain of near-colinear segments around the seat — a 90°
    corner ends it — and each stub is the distance from the pill's along-run
    edge to that end of the chain. The figure this replaces measured the
    connector's endpoint-to-endpoint chord, which on an L-shaped channel is
    a diagonal no wire follows, and it was symmetric, which on a staggered
    dialogue seat reports the average of a tight stub and a generous one
    instead of the tight one the law is about.
    """

    def _unit(j: int) -> tuple[float, float]:
        dx, dy = pts[j + 1][0] - pts[j][0], pts[j + 1][1] - pts[j][1]
        n = math.hypot(dx, dy) or 1.0
        return dx / n, dy / n

    cos_tol = math.cos(math.radians(10.0))
    ux, uy = _unit(i)
    lo, hi = i, i
    while lo > 0 and _unit(lo - 1)[0] * ux + _unit(lo - 1)[1] * uy >= cos_tol:
        lo -= 1
    while hi < len(pts) - 2 and _unit(hi + 1)[0] * ux + _unit(hi + 1)[1] * uy >= cos_tol:
        hi += 1
    a, b = pts[lo], pts[hi + 1]
    cx, cy = box.x + box.w / 2, box.y + box.h / 2
    span = abs(box.w * ux) + abs(box.h * uy)
    return math.hypot(cx - a[0], cy - a[1]) - span / 2, math.hypot(cx - b[0], cy - b[1]) - span / 2


def _check_conduit_endpoints(layout: DiagramLayout) -> None:
    """Each conduit channel meets its OWN cards, computed from its OWN
    direction.

    A conduit is two edges pointing opposite ways, and it is the one place in
    the family where it is easy to hand a channel its partner's numbers. The
    symptom is silent and symmetric: offsetting a finished pair of endpoints
    perpendicular to their shared chord is only parallel to a card face when
    that chord is axis-aligned, so on a FANNED pair the outbound departed
    8.3px inside the hero and the return's arrowhead stopped 8.3px outside
    it, floating — both wrong, in mirror image, with the pair still looking
    tidy because they were wrong by the same amount.

    So both ends are graded, per channel: a departure originates ON its
    source's boundary (never under it, where the card paints over the wire's
    first pixels), and an arrival stands off by no more than the family's
    ``STANDOFF_MAX``.
    """
    by_index = {n.index: n for n in layout.nodes}
    for i, k in _conduit_pairs(layout):
        for idx in (i, k):
            conn = next((c for c in layout.connectors if c.index == idx), None)
            if conn is None:
                continue
            pts = flatten_points(conn.path_d, curve_samples=_SEAT_SAMPLES)
            if len(pts) < 2:
                continue
            source = by_index.get(conn.source_index)
            target = by_index.get(conn.target_index)
            if source is not None:
                sx, sy = pts[0]
                inset = _inset_depth(sx, sy, source)
                if inset > _CONDUIT_ENDPOINT_SLACK:
                    raise _fault(
                        f"duplex battery: conduit channel {idx} departs {inset:.1f}px INSIDE its source card — "
                        f"the card paints over the wire's own first pixels"
                    )
            if target is not None:
                tx, ty = pts[-1]
                d = _box_distance(tx, ty, target.box)
                if d > STANDOFF_MAX:
                    raise _fault(
                        f"duplex battery: conduit channel {idx} stops {d:.1f}px short of its target "
                        f"(law <={STANDOFF_MAX:g}px) — its arrowhead floats free of the card"
                    )


def _inset_depth(x: float, y: float, node: NodePlacement) -> float:
    """How far a point lies inside the node's TRUE boundary (0 when on it or
    outside).

    Measured against the shape, not its bounding box. A card has rounded
    corners, and ``side_anchor`` bisects to the real boundary — so a
    departure seated near a corner is legitimately several px inside the BBOX
    while sitting exactly on the card. Grading it against the box called that
    a defect and would have pushed a correct anchor off its own face.
    """
    from hyperweave.compose.diagram.anchors import boundary_distance

    return max(0.0, -boundary_distance(node, x, y))


def _check_conduit_face_planarity(layout: DiagramLayout) -> None:
    """No two runs meeting a conduit-bearing face cross each other.

    Destination-monotonic port ordering exists to make this true: wires whose
    ports are ordered by their far endpoint cannot cross, because the ordering
    at the face IS the ordering in the field. Grading the drawn result rather
    than the ordering is the point — the ordering can be perfectly applied and
    still produce crossings if the slots are squeezed until neighbouring pairs
    interleave, which is exactly how this first shipped.

    Scoped to faces that carry a conduit, matching where the ordering law
    applies. A pure fan-out keeps the centre mouth and separates by curvature,
    and crossings there are a different question.
    """
    conduit_nodes: set[int] = set()
    for i, k in _conduit_pairs(layout):
        for idx in (i, k):
            conn = next((c for c in layout.connectors if c.index == idx), None)
            if conn is not None:
                conduit_nodes.add(conn.source_index)
                conduit_nodes.add(conn.target_index)
    if not conduit_nodes:
        return
    for node_i in sorted(conduit_nodes):
        runs = [
            (c.index, flatten_points(c.path_d, curve_samples=_SEAT_SAMPLES))
            for c in layout.connectors
            if node_i in (c.source_index, c.target_index) and c.source_index != c.target_index
        ]
        for (ia, pa), (ib, pb) in itertools.combinations(runs, 2):
            hit = _first_crossing(pa, pb)
            if hit is not None:
                raise _fault(
                    f"duplex battery: runs {ia} and {ib} meeting node {node_i} cross at "
                    f"({hit[0]:.1f},{hit[1]:.1f}) — ports ordered by destination cannot cross, so "
                    f"either the ordering did not apply or the slots were squeezed until "
                    f"neighbouring pairs interleaved"
                )


def _first_crossing(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Where two sampled polylines properly cross, if they do. Shared
    endpoints and grazes do not count — only a true sign change on both
    segments, which is what a reader sees as one wire passing through
    another."""

    def cross(o: tuple[float, float], p: tuple[float, float], q: tuple[float, float]) -> float:
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    for p0, p1 in itertools.pairwise(a):
        for q0, q1 in itertools.pairwise(b):
            d1, d2 = cross(q0, q1, p0), cross(q0, q1, p1)
            d3, d4 = cross(p0, p1, q0), cross(p0, p1, q1)
            if (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0):
                return ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
    return None


_SLOT_CORNER_AIR = 3.0
"""Air a slot keeps beyond its face's corner radius — the wire-separation
motion floor, restated here so the battery grades the render without
importing the engine config. A wire anchored inside the corner arc departs
from curved boundary and reads as leaking out of the card's shoulder."""


def _check_slot_corner_zone(layout: DiagramLayout) -> None:
    """No slot sits in its face's CORNER ZONE.

    Every conduit channel and orthogonal channel route anchors on a flat
    stretch of its card's face: its endpoint keeps at least the corner
    radius plus the wire air from both ends of the face it meets. Scoped to
    the slot machinery's own endpoints — a fan's curvature ports grade
    under the attachment law, not this one. The gate exists to catch the
    NEXT crowding: a face short enough to squeeze its slots into the
    corners has outgrown its band, and that must refuse rather than ship a
    wire out of a card's shoulder.
    """
    pair_idx = {i for pr in _conduit_pairs(layout) for i in pr}
    by_index = {n.index: n for n in layout.nodes}
    for c in layout.connectors:
        ortho = "Q" in c.path_d and "C" not in c.path_d
        if c.index not in pair_idx and not ortho:
            continue
        pts = flatten_points(c.path_d, curve_samples=_SEAT_SAMPLES)
        if len(pts) < 2:
            continue
        for pt, node_idx in ((pts[0], c.source_index), (pts[-1], c.target_index)):
            n = by_index.get(node_idx)
            if n is None:
                continue
            b = n.box
            rx = float(getattr(b, "rx", 0.0) or 0.0)
            x, y = pt
            d_left, d_right = abs(x - b.x), abs(x - (b.x + b.w))
            d_top, d_bot = abs(y - b.y), abs(y - (b.y + b.h))
            dmin = min(d_left, d_right, d_top, d_bot)
            if dmin > 6.0:
                continue  # not anchored on this card's boundary (a knot-collapsed trunk end)
            if min(d_left, d_right) <= min(d_top, d_bot):
                end_d = min(y - b.y, (b.y + b.h) - y)
            else:
                end_d = min(x - b.x, (b.x + b.w) - x)
            floor = rx + _SLOT_CORNER_AIR
            if end_d + 0.5 < floor:
                raise _fault(
                    f"slot battery: connector {c.index} anchors {end_d:.1f}px from the end of its face on "
                    f"node {node_idx} (law >= rx {rx:g} + {_SLOT_CORNER_AIR:g}px air) — a slot in the corner "
                    f"zone departs from curved boundary"
                )


def _check_no_wire_through_pill(layout: DiagramLayout, chips: list[Any]) -> None:
    """A FLOATED pill contains no wire at all.

    A pill has two lawful homes. It RIDES a run — its stroke through the
    pill's centre, legible against the fill — or it FLOATS clear of a bend it
    cannot sit level on. Riding is the only home where a wire belongs inside
    the plate, and a floated pill that still catches a stroke has neither:
    it reads as a label somebody dropped on the wiring.

    Scoped to FLOATED pills on purpose. The existing foreign-wire check
    already grades riding pills (with the swimlane specimen's declared
    crossing exempted); what nothing graded was the floated seat, which is
    how a render shipped with a wire crossing a pill's full diagonal and
    every gate stayed green.

    "Riding" is measured against ANY connector, not the pill's own edge
    index: a gather/join chip rides the shared TRUNK, which carries a
    different index than the edge that authored the label (dag-gate's
    `release`, dag-join's `unify`). Keying the test to the authored index
    called those trunk-ridden pills floated and their own trunk foreign.
    """
    if not chips:
        return
    paths = {c.index: _densify_path(flatten_points(c.path_d, curve_samples=_SEAT_SAMPLES)) for c in layout.connectors}
    for chip in chips:
        b = chip.box
        if b is None:
            continue
        cx, cy = b.x + b.w / 2, b.y + b.h / 2
        rides = any(any(math.hypot(cx - x, cy - y) <= _RIDING_SEAT_TOL for x, y in pts) for pts in paths.values())
        if rides:
            continue
        for idx, pts in paths.items():
            inside = sum(1 for x, y in pts if b.x <= x <= b.x + b.w and b.y <= y <= b.y + b.h)
            if inside:
                text = " ".join(t.text for t in chip.lines)
                which = "its own" if idx == chip.edge_index else f"connector {idx}'s"
                raise _fault(
                    f"chip battery: {which} wire runs through the FLOATED pill {text!r} "
                    f"({inside} sampled points inside the plate) — a floated pill is the seat for a "
                    f"run it cannot sit on, so nothing may cross it; only a RIDING pill carries a wire"
                )


def _densify_path(pts: list[tuple[float, float]], samples: int = 240) -> list[tuple[float, float]]:
    """Resample a polyline at even arc-length steps, so a long straight leg
    cannot slip through the test between two distant vertices."""
    if len(pts) < 2:
        return pts
    lens = [0.0]
    for a, b in itertools.pairwise(pts):
        lens.append(lens[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = lens[-1]
    if total <= 0:
        return pts
    out: list[tuple[float, float]] = []
    for i in range(samples + 1):
        target = total * i / samples
        for k, (a, b) in enumerate(itertools.pairwise(pts)):
            if lens[k + 1] >= target or k + 2 == len(lens):
                seg = lens[k + 1] - lens[k]
                f = 0.0 if seg <= 0 else (target - lens[k]) / seg
                out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
                break
    return out
