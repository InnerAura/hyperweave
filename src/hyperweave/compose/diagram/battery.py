"""Loop self-consistency battery — hard asserts on a SOLVED loop layout.

The corpus's time-domain QA, enrolled as pipeline law (cycle-expression-map:
"a motion checker in the pipeline — park-invisible, full-exit, occlusion
ratio, minimum visible runs as hard asserts"). Runs inside the resolver for
loop slugs only, AFTER layout + choreography. A failure here means the
engine broke its own geometric or motion contract on an input that was
otherwise legal — it raises ``AssertionError`` (an engine fault, 500-class),
never ``DiagramInputError`` (the caller asked for something lawful and the
engine failed while building it).

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

import itertools
import math
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from hyperweave.compose.diagram.records import DiagramLayout, NodePlacement
    from hyperweave.compose.spatial_records import RectSpec

_NUM = r"-?\d+(?:\.\d+)?"

CHIP_OCCLUSION_MAX = 1 / 3
CHIP_VISIBLE_RUN_MIN = 30.0
_CONDUIT_ENDPOINT_TOL = 48.0
"""How far apart a conduit's two channels may face each other and still be
recognised as one round trip: the lane gap plus the pill air it reserves."""
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


def _path_points(d: str) -> list[tuple[float, float]]:
    """A sampled polyline along the path: L runs keep their endpoints, C
    segments sample the actual bezier (a control-polygon read once measured
    a correctly-seated fork chip 12px 'off its wire'), and rail arcs pass as
    chords (no chip ever seats on a corner)."""
    out: list[tuple[float, float]] = []
    cursor: tuple[float, float] | None = None
    for cmd, args in re.findall(r"([MLCQA])\s*((?:[-\d.,\s]|(?<=e)-)+)", d):
        nums = [float(v) for v in re.findall(_NUM, args)]
        if cmd == "M" and len(nums) >= 2:
            cursor = (nums[0], nums[1])
            out.append(cursor)
        elif cmd == "L":
            for i in range(0, len(nums) - 1, 2):
                cursor = (nums[i], nums[i + 1])
                out.append(cursor)
        elif cmd == "C" and cursor is not None and len(nums) >= 6:
            x0, y0 = cursor
            c1x, c1y, c2x, c2y, x1, y1 = nums[:6]
            for step in range(1, 17):
                t = step / 16.0
                v = 1.0 - t
                out.append(
                    (
                        v**3 * x0 + 3 * v**2 * t * c1x + 3 * v * t**2 * c2x + t**3 * x1,
                        v**3 * y0 + 3 * v**2 * t * c1y + 3 * v * t**2 * c2y + t**3 * y1,
                    )
                )
            cursor = (x1, y1)
        elif cmd == "Q" and cursor is not None and len(nums) >= 4:
            x0, y0 = cursor
            cx_, cy_, x1, y1 = nums[:4]
            for step in range(1, 9):
                t = step / 8.0
                v = 1.0 - t
                out.append((v**2 * x0 + 2 * v * t * cx_ + t**2 * x1, v**2 * y0 + 2 * v * t * cy_ + t**2 * y1))
            cursor = (x1, y1)
        elif cmd == "A" and len(nums) >= 7:
            cursor = (nums[-2], nums[-1])
            out.append(cursor)
    return out


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
        assert p.x >= 0 and p.y >= 0 and p.x + p.w <= layout.width and p.y + p.h <= layout.height, (
            f"meter plate leaves the canvas: ({p.x},{p.y}) {p.w}x{p.h} on {layout.width}x{layout.height}"
        )
        for n in layout.nodes:
            b = n.box
            overlap_x = min(p.x + p.w, b.x + b.w) - max(p.x, b.x)
            overlap_y = min(p.y + p.h, b.y + b.h) - max(p.y, b.y)
            assert overlap_x <= 0 or overlap_y <= 0, (
                f"meter plate overlaps node {n.node_id!r}: plate ({p.x},{p.y}) {p.w}x{p.h} vs box ({b.x},{b.y})"
            )
        for sb in m.boxes:
            assert (
                sb.x >= p.x - 0.5
                and sb.y >= p.y - 0.5
                and sb.x + sb.w <= p.x + p.w + 0.5
                and sb.y + sb.h <= p.y + p.h + 0.5
            ), "meter segment escapes its plate"


def _check_standoffs(layout: DiagramLayout) -> None:
    by_index = {n.index: n for n in layout.nodes}
    polylines = [(c.index, _path_points(c.path_d)) for c in layout.connectors]
    for c in layout.connectors:
        target = by_index.get(c.target_index)
        if target is None:
            continue  # scope arrivals anchor on the enclosure band
        pts = _path_points(c.path_d)
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
        assert d <= STANDOFF_MAX, (
            f"loop battery: connector {c.index} arrives {d:.2f}px off its target "
            f"(the family standoff law holds arrivals within {STANDOFF_MAX}px)"
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
        pts = _path_points(c.path_d)
        best_i = min(range(len(pts) - 1), key=lambda i: _segment_distance(cx, cy, pts[i], pts[i + 1]))
        seat_error = _segment_distance(cx, cy, pts[best_i], pts[best_i + 1])
        assert seat_error <= 8.0, (
            f"loop battery: guard chip for edge {a.edge_index} floats {seat_error:.1f}px off its wire "
            "(chips seat at named geometry, never a path parameter)"
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
                assert visible >= cited - 0.5, (
                    f"loop battery: guard chip for edge {a.edge_index} leaves {visible:.1f}px visible "
                    f"each side against its spec's own {cited:.0f}px citation"
                )
            else:
                assert ratio <= CHIP_OCCLUSION_MAX and visible >= CHIP_VISIBLE_RUN_MIN - 0.5, (
                    f"loop battery: guard chip for edge {a.edge_index} occludes {ratio:.0%} of its "
                    f"{run:.0f}px run with {visible:.1f}px visible each side "
                    f"(the enrolled law: <=1/3 occlusion with >={CHIP_VISIBLE_RUN_MIN:.0f}px visible per side)"
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
    own_by_index = {c.index: _path_points(c.path_d) for c in layout.connectors}
    for a in layout.annotations:
        if a.kind != "edge-chip" or a.box is None:
            continue
        b = a.box
        x0, y0, x1, y1 = b.x - 2, b.y - 2, b.x + b.w + 2, b.y + b.h + 2
        own = own_by_index.get(a.edge_index, [])
        own_in_box = any(_segment_crosses_box(own[i], own[i + 1], x0, y0, x1, y1) for i in range(len(own) - 1))
        for c in layout.connectors:
            if c.index == a.edge_index:
                continue
            pts = _path_points(c.path_d)
            for i in range(len(pts) - 1):
                if _segment_crosses_box(pts[i], pts[i + 1], x0, y0, x1, y1):
                    if own_in_box:
                        # The declared crossing: where a chip's OWN wire and
                        # the foreign one cross inside the chip, the chip
                        # covers the intersection deliberately (the swimlane
                        # specimen's handoff guard sits exactly on the one
                        # crossing — "routing around it would cost more than
                        # it buys", its own tradeoff record verbatim).
                        continue
                    raise AssertionError(
                        f"loop battery: guard chip for edge {a.edge_index} overlaps connector "
                        f"{c.index}'s wire — a chip straddles its own wire and no other"
                    )


def _segment_crosses_box(
    a: tuple[float, float], b: tuple[float, float], x0: float, y0: float, x1: float, y1: float
) -> bool:
    """Liang-Barsky style clip test: does segment a-b intersect the box?"""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, ax - x0), (dx, x1 - ax), (-dy, ay - y0), (dy, y1 - ay)):
        if p == 0:
            if q < 0:
                return False
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return False
    return True


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
        assert offsets and abs(max(offsets) - tr.rest_offset) < 0.6 and tr.rest_offset > 0, (
            f"loop battery: trail on connector {tr.connector_index} never parks invisible"
        )
        assert min(offsets) >= -0.01, f"loop battery: trail on connector {tr.connector_index} overshoots its own wire"
        assert abs(offsets[-1] - tr.rest_offset) < 0.6, (
            f"loop battery: trail on connector {tr.connector_index} ends lit — the route clears at the wrap"
        )
    for p in plan.pulses:
        body = plan.keyframes[p.anim_index].body
        offsets = [float(v) for v in re.findall(r"stroke-dashoffset: ?(-?[\d.]+)", body)]
        assert offsets and max(offsets) == p.rest_offset > 0, (
            f"loop battery: pulse on connector {p.connector_index} never parks invisible"
        )
        run = runs.get(p.connector_index, lengths[p.connector_index])
        assert min(offsets) <= -run + 0.01, (
            f"loop battery: pulse on connector {p.connector_index} stops mid-wire "
            f"(sweeps to {min(offsets)} on a {run:.0f}px run — full exit is the law)"
        )


def run_chip_air_battery(layout: DiagramLayout, engine: Mapping[str, Any] | None = None) -> None:
    """No two pills fuse — FAMILY-WIDE, on every topology.

    Deliberately not a trigger for anything and not scoped to the shape that
    prompted it: two plates closer than the air floor read as one plate
    whatever seated them, so this grades the outcome rather than any
    particular cause, and it will catch fusion on shapes the seat laws do not
    yet describe. Kept separate from the duplex dialogue seats for the same
    reason — a seat rule that also policed its own result could only ever
    check the cases it already knew about.
    """
    air = 6.0
    if engine is not None:
        air = float((engine.get("connector") or {}).get("chip_pill_air", 6))
    chips = [a for a in layout.annotations if a.kind == "edge-chip" and a.box is not None]
    for a, b in itertools.combinations(chips, 2):
        if a.box is None or b.box is None:
            continue
        gap_x = max(a.box.x - (b.box.x + b.box.w), b.box.x - (a.box.x + a.box.w))
        gap_y = max(a.box.y - (b.box.y + b.box.h), b.box.y - (a.box.y + a.box.h))
        gap = max(gap_x, gap_y)
        if gap < air - 0.5:
            at = " ".join(t.text for t in a.lines)
            bt = " ".join(t.text for t in b.lines)
            raise AssertionError(
                f"chip battery: pills {at!r} and {bt!r} sit {gap:.1f}px apart (law >={air:g}px) — "
                f"two plates that close read as one"
            )


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


def _conduit_pairs(layout: DiagramLayout) -> list[tuple[int, int]]:
    """Index pairs of connectors that run the same corridor in opposite
    directions — endpoints swapped within the lane gap that separates them."""
    ends: dict[int, tuple[tuple[float, float], tuple[float, float]]] = {}
    for c in layout.connectors:
        pts = _path_points(c.path_d)
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
    """Two chips on one conduit never overlap, and each keeps visible wire.

    A pill may only slide along its OWN run, and a conduit's two runs are the
    same length in the same corridor — so if the channels are too close the
    pills stack and neither can escape. The separation has to be right at the
    geometry, which is what this grades.
    """
    chips = {a.edge_index: a for a in layout.annotations if a.kind == "edge-chip" and a.box is not None}
    for i, k in _conduit_pairs(layout):
        a, b = chips.get(i), chips.get(k)
        if a is None or b is None or a.box is None or b.box is None:
            continue
        ox = min(a.box.x + a.box.w, b.box.x + b.box.w) - max(a.box.x, b.box.x)
        oy = min(a.box.y + a.box.h, b.box.y + b.box.h) - max(a.box.y, b.box.y)
        if ox > 0 and oy > 0:
            raise AssertionError(
                f"duplex battery: the two chips on the conduit between edges {i} and {k} overlap by "
                f"{ox:.1f}x{oy:.1f}px — a chip can only slide along its own run, and both runs are "
                f"the same length here, so neither can clear the other"
            )
    for i, k in _conduit_pairs(layout):
        for idx in (i, k):
            chip = chips.get(idx)
            conn = next((c for c in layout.connectors if c.index == idx), None)
            if chip is None or chip.box is None or conn is None:
                continue
            pts = _path_points(conn.path_d)
            if len(pts) < 2:
                continue
            ux, uy = pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]
            run = math.hypot(ux, uy)
            if run <= 0:
                continue
            ux, uy = ux / run, uy / run
            span = abs(chip.box.w * ux) + abs(chip.box.h * uy)
            visible = (run - span) / 2
            if visible < _CONDUIT_STUB_MIN - 0.5:
                raise AssertionError(
                    f"duplex battery: the chip on conduit channel {idx} leaves {visible:.1f}px of visible "
                    f"wire each side (law >={_CONDUIT_STUB_MIN:g}px) — a pill with no thread reads as a "
                    f"label floating between two cards, not as that channel's"
                )


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
            pts = _path_points(conn.path_d)
            if len(pts) < 2:
                continue
            source = by_index.get(conn.source_index)
            target = by_index.get(conn.target_index)
            if source is not None:
                sx, sy = pts[0]
                inset = _inset_depth(sx, sy, source)
                if inset > _CONDUIT_ENDPOINT_SLACK:
                    raise AssertionError(
                        f"duplex battery: conduit channel {idx} departs {inset:.1f}px INSIDE its source card — "
                        f"the card paints over the wire's own first pixels"
                    )
            if target is not None:
                tx, ty = pts[-1]
                d = _box_distance(tx, ty, target.box)
                if d > STANDOFF_MAX:
                    raise AssertionError(
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
            (c.index, _path_points(c.path_d))
            for c in layout.connectors
            if node_i in (c.source_index, c.target_index) and c.source_index != c.target_index
        ]
        for (ia, pa), (ib, pb) in itertools.combinations(runs, 2):
            hit = _first_crossing(pa, pb)
            if hit is not None:
                raise AssertionError(
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
