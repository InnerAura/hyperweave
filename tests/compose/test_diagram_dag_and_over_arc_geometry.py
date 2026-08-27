"""DAG gather-chip clearance and state-machine over-arc geometry.

Two related graph-family fixes: a DAG join-gather trunk that carries a chip
and terminates in a drawn arrowhead (every ``solve_dag`` join defaults
``marker="arrow"``) now reserves the chevron's own draw length beyond the
chip's visible-thread stub, so the pill and the chevron never overlap
(frontier-serving's 'cache'); and the state-machine's reciprocal over-arc
(``exit: top``) now bisects its rise until it clears every card between its
endpoints by ``min_clearance`` plus a row-label headroom floor, instead of a
fixed 60px offset that only happened to clear agent-runtime's evenly-spaced
row by luck.
"""

from __future__ import annotations

import itertools
import math
import re
from typing import Any

import pytest

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import coerce_diagram_input, resolve_auto_roles
from hyperweave.config.loader import load_diagram_config, load_glyphs, load_paradigms
from hyperweave.core.diagram import DiagramSpec
from hyperweave.core.models import ComposeSpec
from hyperweave.core.paradigm import ParadigmDiagramConfig

ENGINE = load_diagram_config()
_pspec = load_paradigms()["primer"]
PARADIGM: ParadigmDiagramConfig = _pspec.diagram if _pspec is not None else ParadigmDiagramConfig()
GLYPHS = load_glyphs()


def _layout(**kw: Any) -> Any:
    spec = resolve_auto_roles(DiagramSpec(**kw))
    return compute_diagram_layout(spec, paradigm=PARADIGM, engine=ENGINE, palette_len=6)


def _preset_layout(name: str) -> Any:
    spec_dict = dict(resolve_bundled_spec("diagram", name).value)
    cs = ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", ground="bare", diagram=spec_dict)
    normalized = coerce_diagram_input(cs.connector_data, cs)
    return compute_diagram_layout(
        normalized.spec, paradigm=PARADIGM, engine=ENGINE, palette_len=6, glyph_registry=GLYPHS
    )


# ── Defect 3: DAG join-gather chip run budget (marker clearance) ────────────


def test_frontier_serving_cache_chip_clears_the_chevron() -> None:
    """frontier-serving's 'cache' chip (anthropic+openai -> kv-cache join)
    shows >=8px of visible wire on EACH side, and the chevron drawn at the
    trunk's arrowed mouth end never overlaps the pill."""
    lay = _preset_layout("dag-providers")
    chip = next(a for a in lay.annotations if a.kind == "edge-chip" and any(t.text == "cache" for t in a.lines))
    sink = next(n for n in lay.nodes if n.node_id == "cache")
    mouth_x = sink.box.x
    trunk = next(
        c
        for c in lay.connectors
        if " L " in c.path_d and abs(float(c.path_d.rsplit(" ", 1)[1].split(",")[0]) - mouth_x) < 1.0
    )
    assert trunk.marker_d, "the join trunk terminates in a drawn arrowhead"
    knot_x = float(trunk.path_d.split(" ")[1].split(",")[0])
    marker_size = float((ENGINE.get("connector") or {}).get("marker_size", 8))
    left_thread = chip.box.x - knot_x
    right_thread = (mouth_x - (chip.box.x + chip.box.w)) - marker_size
    assert left_thread >= 8.0, left_thread
    assert right_thread >= 8.0, right_thread


def test_dag_scatter_chip_still_centers_on_the_trunk() -> None:
    """dag-scatter's 'resolve' chip (>=3 arrivals, mouth-lifted) keeps
    seating at the trunk's true midpoint — the marker-clearance fix widens
    the run symmetrically, it never re-derives the seat law."""
    lay = _preset_layout("scatter-gather")
    chip = next(a for a in lay.annotations if a.kind == "edge-chip" and any(t.text == "resolve" for t in a.lines))
    sink = next(n for n in lay.nodes if n.node_id == "aggregator")
    mouth_x = sink.box.x
    trunk = next(
        c
        for c in lay.connectors
        if " L " in c.path_d and abs(float(c.path_d.rsplit(" ", 1)[1].split(",")[0]) - mouth_x) < 1.0
    )
    knot_x = float(trunk.path_d.split(" ")[1].split(",")[0])
    chip_cx = chip.box.x + chip.box.w / 2
    run_mid = (knot_x + mouth_x) / 2
    assert abs(chip_cx - run_mid) < 1.0, (chip_cx, run_mid)


# ── Defect 5: reciprocal over-arc clears cards + labels, on-tangent chevron ──

_BREAKER_STATES = dict(
    topology="state-machine",
    title="A breaker trips",
    nodes=[{"id": "closed", "label": "closed"}, {"id": "open", "label": "open"}, {"id": "half", "label": "half-open"}],
    edges=[
        {"source": "closed", "target": "open", "label": "failures spike"},
        {"source": "open", "target": "half", "label": "cooldown"},
        {"source": "half", "target": "closed", "label": "probe succeeds", "exit": "top"},
        {"source": "half", "target": "open", "label": "probe fails", "exit": "top"},
    ],
)


def test_over_arc_clears_every_intervening_card() -> None:
    """closed<->open<->half-open: the half->closed over-arc spans OVER the
    'open' card — its swept path clears open's top by >=12px, not diving
    into it (the fixed 60px rise cleared agent-runtime's row by luck, never
    by construction)."""
    lay = _layout(**_BREAKER_STATES)
    over = next(c for c in lay.connectors if c.source_index == 2 and c.target_index == 0)  # half -> closed
    span = _sample_cubic(over.path_d)
    open_box = next(n for n in lay.nodes if n.node_id == "open").box
    worst = min(
        py_dist for px, py in span if open_box.x <= px <= open_box.x + open_box.w for py_dist in [open_box.y - py]
    )
    assert worst >= 12.0, worst


def test_over_arc_chevron_is_on_tangent() -> None:
    """The chevron drawn at an over-arc's arrival reads the curve's own
    analytic derivative, not a polyline-secant approximation — perfectly
    vertical here since both controls sit directly above their endpoint
    (symmetric departure/arrival), within 1 degree."""
    lay = _layout(**_BREAKER_STATES)
    for c in lay.connectors:
        if c.source_index in (1, 2) and c.target_index in (0, 1) and c.source_index != c.target_index and c.marker_d:
            nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", c.marker_d)]
            if len(nums) != 6:
                continue
            l1x, l1y, tipx, tipy, l2x, l2y = nums
            backx, backy = (l1x + l2x) / 2, (l1y + l2y) / 2
            dx, dy = tipx - backx, tipy - backy
            angle_off_vertical = math.degrees(math.atan2(abs(dx), dy))
            assert angle_off_vertical < 1.0, (c.path_d, c.marker_d, angle_off_vertical)


def test_over_arc_label_sits_above_the_peak() -> None:
    """Every over-arc's label renders above its own peak point (legible
    above the bow, never inside a card or on the wire)."""
    lay = _layout(**_BREAKER_STATES)
    for text in ("probe succeeds", "probe fails"):
        label = next(a for a in lay.annotations if a.kind == "label" and any(t.text == text for t in a.lines))
        row_top = min(n.box.y for n in lay.nodes)
        assert label.box.y + label.box.h < row_top, (text, label.box, row_top)


def test_agent_runtime_over_arc_still_clears_act() -> None:
    """The one production over-arc consumer (agent-runtime's re-plan) keeps
    clearing its intervening 'Act' card — the bisection fix only RAISES the
    peak when the fixed offset falls short, never lowers it."""
    lay = _preset_layout("sm-loop")
    over = next(
        c
        for c in lay.connectors
        if c.source_index == next(i for i, n in enumerate(lay.nodes) if n.node_id == "observe")
        and c.target_index == next(i for i, n in enumerate(lay.nodes) if n.node_id == "plan")
    )
    span = _sample_cubic(over.path_d)
    act_box = next(n for n in lay.nodes if n.node_id == "act").box
    worst = min(py_dist for px, py in span if act_box.x <= px <= act_box.x + act_box.w for py_dist in [act_box.y - py])
    assert worst >= 12.0, worst


def _sample_cubic(d: str, steps: int = 48) -> list[tuple[float, float]]:
    nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", d)]
    sx, sy, c1x, c1y, c2x, c2y, ex, ey = nums
    pts: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        v = 1.0 - t
        pts.append(
            (
                v**3 * sx + 3 * v**2 * t * c1x + 3 * v * t**2 * c2x + t**3 * ex,
                v**3 * sy + 3 * v**2 * t * c1y + 3 * v * t**2 * c2y + t**3 * ey,
            )
        )
    return pts


# ── Duplex conduits: generated 1..3-pair dags, both orientations ────────────
#
# A local duplex (u->v with v->u) keeps its dag ranks and draws as one
# dual-channel conduit. These are property tests over GENERATED graphs rather
# than a fixture, because the failure that motivated the work — two pills
# stacked in a stroke-width channel, neither able to slide clear — only
# appears once both channels carry chips, and which orientation exposes it
# flips with the pill's aspect: a pair separates vertically on a horizontal
# conduit and horizontally on a vertical one.


def _duplex_spec(pairs: int, *, orientation: str, chips: bool) -> dict[str, Any]:
    """A chain of ``pairs + 1`` nodes where each consecutive step is a round
    trip: a -> b -> c with b -> a and c -> b, and so on."""
    # The dag family needs three nodes minimum, so a single pair gets a plain
    # forward tail — which also puts an ordinary edge beside a conduit, the
    # mix every real architecture graph actually has.
    n_nodes = max(pairs + 1, 3)
    labels = [chr(ord("A") + i) for i in range(n_nodes)]
    nodes = [{"id": lb.lower(), "label": f"Node {lb}"} for lb in labels]
    edges: list[dict[str, Any]] = []
    for i in range(pairs):
        s, t = labels[i].lower(), labels[i + 1].lower()
        out: dict[str, Any] = {"source": s, "target": t, "label": f"req{i}"}
        back: dict[str, Any] = {"source": t, "target": s, "label": f"res{i}"}
        if chips:
            out["label_style"] = "chip"
            back["label_style"] = "chip"
        edges += [out, back]
    for i in range(pairs, n_nodes - 1):
        edges.append({"source": labels[i].lower(), "target": labels[i + 1].lower()})
    return {
        "topology": "dag",
        "orientation": orientation,
        "node_style": "card",
        "nodes": nodes,
        "edges": edges,
    }


def _compose_layout(spec_dict: dict[str, Any]) -> Any:
    cs = ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", ground="bare", diagram=spec_dict)
    normalized = coerce_diagram_input(cs.connector_data, cs)
    assert normalized.spec.topology.value == "dag", "a local duplex must never promote"
    return compute_diagram_layout(
        normalized.spec, paradigm=PARADIGM, engine=ENGINE, palette_len=6, glyph_registry=GLYPHS
    )


@pytest.mark.parametrize("pairs", [1, 2, 3])
@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
@pytest.mark.parametrize("chips", [False, True])
def test_duplex_dag_solves_without_promoting(pairs: int, orientation: str, chips: bool) -> None:
    spec = _duplex_spec(pairs, orientation=orientation, chips=chips)
    lay = _compose_layout(spec)
    assert lay.layout_slug in ("dag", "dag-vertical")
    assert len(lay.connectors) == len(spec["edges"]), "every declared edge kept its wire"


@pytest.mark.parametrize("pairs", [1, 2, 3])
@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
def test_every_conduit_returns_along_its_own_corridor(pairs: int, orientation: str) -> None:
    """Each pair's two channels run between the same two faces, reversed.

    Routed as an ordinary edge the return leaves by the flow-forward face and
    has to cross the whole diagram to get home — which is what drove the
    readme-ai return wires through the hero card.
    """
    spec = _duplex_spec(pairs, orientation=orientation, chips=True)
    lay = _compose_layout(spec)
    for i in range(pairs):
        out_pts = _sample_any(lay.connectors[i * 2].path_d)
        back_pts = _sample_any(lay.connectors[i * 2 + 1].path_d)
        # The gap between the two channels bounds how far the endpoints can
        # face each other; nothing else should separate them.
        assert math.hypot(out_pts[0][0] - back_pts[-1][0], out_pts[0][1] - back_pts[-1][1]) < 60.0
        assert math.hypot(out_pts[-1][0] - back_pts[0][0], out_pts[-1][1] - back_pts[0][1]) < 60.0


@pytest.mark.parametrize("pairs", [1, 2, 3])
@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
def test_conduit_wears_no_pills_and_labels_never_overlap(pairs: int, orientation: str) -> None:
    """A conduit never wears chip pills — its labels are the bare BRACKET.

    SUPERSEDED (owner bracket ruling): this test used to assert the
    OPPOSITE — ``len(chips) == pairs * 2``, every authored chip rendered as
    a pill on its channel. The owner's verdict on that render ("still
    crowded on the chips") and the pp-mcp-gateway specimen retired it: a
    pill on one lane occludes the partner lane by construction, so the
    authored chip style takes a structural override and each conduit
    renders one bare label pair instead. The no-overlap half of the old law
    carries over to the labels.
    """
    lay = _compose_layout(_duplex_spec(pairs, orientation=orientation, chips=True))
    chips = [a for a in lay.annotations if a.kind == "edge-chip" and a.box is not None]
    assert chips == [], f"{orientation} {pairs}-pair: a conduit wears a pill"
    labels = [a for a in lay.annotations if a.kind == "label" and a.box is not None]
    assert len(labels) == pairs * 2, "every declared conduit label rendered as bare bracket text"
    for a, b in itertools.combinations(labels, 2):
        ox = min(a.box.x + a.box.w, b.box.x + b.box.w) - max(a.box.x, b.box.x)
        oy = min(a.box.y + a.box.h, b.box.y + b.box.h) - max(a.box.y, b.box.y)
        assert ox <= 0 or oy <= 0, (
            f"{orientation} {pairs}-pair: labels overlap by {ox:.1f}x{oy:.1f} — "
            f"{[t.text for t in a.lines]} and {[t.text for t in b.lines]}"
        )


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
def test_both_channels_of_a_conduit_keep_the_same_label_grammar(orientation: str) -> None:
    # One conduit cannot be half pill and half bare text. (Since the
    # bracket ruling the one grammar is BARE — the pill half of the old
    # assertion lives on inverted in the no-pills law above.)
    lay = _compose_layout(_duplex_spec(2, orientation=orientation, chips=True))
    kinds = [a.kind for a in lay.annotations if a.box is not None]
    assert set(kinds) == {"label"}, f"mixed label grammar on a conduit: {sorted(set(kinds))}"


def _sample_any(d: str) -> list[tuple[float, float]]:
    from hyperweave.compose.diagram.paths import sample_path

    return list(sample_path(d))


def _fanned_duplex_spec(*, orientation: str, chips: bool) -> dict[str, Any]:
    """A duplex whose partner sits OFF-ROW: the hub also feeds a second
    target, so the pair fans instead of running level.

    This is the shape that escaped. A same-row pair's chord is axis-aligned,
    which hides two things at once — a straight chord looks identical to the
    family's own degenerate S-curve, and a perpendicular lane offset happens
    to run parallel to the card face. Tilt the chord and both come apart.
    """
    out: dict[str, Any] = {"source": "hub", "target": "up", "label": "req"}
    back: dict[str, Any] = {"source": "up", "target": "hub", "label": "res"}
    if chips:
        out["label_style"] = "chip"
        back["label_style"] = "chip"
    return {
        "topology": "dag",
        "orientation": orientation,
        "node_style": "card",
        "nodes": [
            {"id": "hub", "label": "Hub Node"},
            {"id": "up", "label": "Upper Node"},
            {"id": "down", "label": "Lower Node"},
        ],
        "edges": [out, back, {"source": "hub", "target": "down", "label": "other"}],
    }


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
@pytest.mark.parametrize("chips", [False, True])
def test_fanned_duplex_routes_as_an_orthogonal_bus(orientation: str, chips: bool) -> None:
    """One grammar per face: every off-row edge on a conduit-bearing face
    takes the orthogonal channel route — the pair as a dual-lane bus, the
    plain edge beside it as a single-lane channel.

    SUPERSEDED (owner composition ruling): this test used to pin the
    OPPOSITE — ``"C" in d and " L " not in d``, the family's own S-curve for
    a fanned conduit. The owner falsified that by eye ("not coherent with
    5+ edges all stacked and bent on top of one another"): a free curve
    separates a fan by curvature, which only reads while every wire on the
    face travels the same way, and a conduit face carries traffic both
    ways. The routes are now straight legs joined by fixed-radius fillets,
    same as every other detour in the family.
    """
    spec = _fanned_duplex_spec(orientation=orientation, chips=chips)
    lay = _compose_layout(spec)
    for idx in (0, 1, 2):
        d = lay.connectors[idx].path_d
        assert "C" not in d and " L " in d and "Q " in d, (
            f"channel {idx} is not an orthogonal route (legs + fillets): {d}"
        )


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
def test_fanned_duplex_bus_holds_the_lane_gap(orientation: str) -> None:
    """The pair is a LOCKED bus: both channels turn at the same elbows and
    hold the lane gap throughout — never two free wires.

    Graded from the drawn geometry against the gap's own terms
    (``max(motion_lane_air, half_pill_h + foreign_clearance + headroom)``):
    the channels never pinch below the corner floor, and the straight legs —
    where the pills and the partner wire actually meet — hold the gap
    itself. At a shared elbow the inner lane's corner legitimately nears the
    outer lane's by ``(gap - fillet_r) * sqrt(2)``, which is the only place
    the separation may dip under the gap.
    """
    lay = _compose_layout(_fanned_duplex_spec(orientation=orientation, chips=True))
    conn_cfg = ENGINE.get("connector") or {}
    lane_air = float(ENGINE.get("lane_min_air") or 3)
    clear = float(conn_cfg.get("chip_foreign_wire_clearance", 2))
    headroom = float(conn_cfg.get("lane_rounding_headroom", 0.5))
    # The gap's pill term measures the AUTHORED labels' pill boxes — the
    # bracket renders them as bare text, but the pair keeps its separation
    # floor (the bracket ruling left the lane gap untouched). Across-run
    # extent is the pill's height on a flow leg flowing right, its width
    # flowing down.
    from hyperweave.compose.diagram.sizing import solve_chip_box

    pills = [
        solve_chip_box(str(e["label"]), PARADIGM)
        for e in _fanned_duplex_spec(orientation=orientation, chips=True)["edges"][:2]
    ]
    across = max((h if orientation == "horizontal" else w) for w, h in pills)
    gap = max(lane_air, across / 2 + clear + headroom)
    arc_r = 7.0  # the chassis over_arc_r every detour fillet cites
    a = _sample_any(lay.connectors[0].path_d)
    b = _sample_any(lay.connectors[1].path_d)
    b_segs = list(itertools.pairwise(b))
    seps = [min(_dist_to_seg(ax, ay, p, q) for p, q in b_segs) for ax, ay in a]
    corner_floor = min(gap, (gap - arc_r) * math.sqrt(2.0))
    assert min(seps) >= corner_floor - 0.6, (
        f"{orientation}: the two channels pinch to {min(seps):.1f}px (corner floor {corner_floor:.1f})"
    )
    # Locked means the closest approach IS the lane gap: two channels that
    # never come within it are two free wires that happen to agree, not one
    # conduit — and two parallel offset polylines meet exactly at the gap
    # along their shared legs.
    assert min(seps) <= gap + 1.0, (
        f"{orientation}: the channels never close to the lane gap (nearest {min(seps):.1f} vs {gap:.1f}) — "
        f"a bus is one conduit with two lanes, not two free wires"
    )


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
def test_fanned_duplex_labels_bracket_the_bus(orientation: str) -> None:
    """The conduit's labels are one BRACKET: bare text, request outboard of
    the outbound lane, response outboard of the return lane, both at the
    same along-run coordinate on the caller-side legs — the dialogue reads
    from position, question over the outbound, answer under the return.

    SUPERSEDED (owner bracket ruling): this test used to pin pills riding
    each channel's source-side leg ("Pills all ride", the round-6 §4). The
    owner's verdict retired the pill grammar for conduits; the caller-side
    reading carries over — both labels sit nearer the CALLER (the request's
    source) than the callee.
    """
    lay = _compose_layout(_fanned_duplex_spec(orientation=orientation, chips=True))
    boxes = {n.index: n.box for n in lay.nodes}
    labels = {}
    for a in lay.annotations:
        if a.kind == "label" and a.box is not None:
            labels[" ".join(t.text for t in a.lines)] = a
    assert set(labels) >= {"req", "res"}, f"bracket labels missing: {sorted(labels)}"
    req, res = labels["req"], labels["res"]
    assert req.box is not None and res.box is not None
    # Same along-run coordinate: x flowing right, y flowing down.
    if orientation == "horizontal":
        assert abs((req.box.x + req.box.w / 2) - (res.box.x + res.box.w / 2)) <= 1.0
    else:
        assert abs((req.box.y + req.box.h / 2) - (res.box.y + res.box.h / 2)) <= 1.0
    # The bracket wraps the bus: the two labels sit on OPPOSITE sides of
    # both lanes, outboard, never in the corridor between them.
    req_pts = _sample_any(lay.connectors[0].path_d)
    res_pts = _sample_any(lay.connectors[1].path_d)
    for name, a in (("req", req), ("res", res)):
        assert a.box is not None
        cx, cy = a.box.x + a.box.w / 2, a.box.y + a.box.h / 2
        own = 0 if name == "req" else 1
        d_own = min(_dist_to_seg(cx, cy, p, q) for p, q in itertools.pairwise((req_pts, res_pts)[own]))
        d_other = min(_dist_to_seg(cx, cy, p, q) for p, q in itertools.pairwise((req_pts, res_pts)[1 - own]))
        assert d_own < d_other, f"{name} sits nearer its partner's lane than its own"
        assert d_own > 2.0, f"{name} lies on its own wire — a bracket label sits beside its lane, never on it"
        # Caller-side: nearer the request's source card than the callee's.
        caller = boxes[lay.connectors[0].source_index]
        callee = boxes[lay.connectors[0].target_index]
        assert _box_gap((cx, cy), caller) < _box_gap((cx, cy), callee), (
            f"{name} sits nearer the callee than the caller — the bracket seats on the caller-side legs"
        )


def _dist_to_seg(px: float, py: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    denom = dx * dx + dy * dy
    if denom == 0:
        return math.hypot(px - a[0], py - a[1])
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / denom))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
@pytest.mark.parametrize("chips", [False, True])
def test_fanned_duplex_endpoints_meet_their_own_cards(orientation: str, chips: bool) -> None:
    """Each channel departs ON its source face and arrives at its target.

    A perpendicular offset of finished endpoints is parallel to a card face
    only when the chord is axis-aligned; tilted, it drove the outbound 8.3px
    inside the hero and left the return's arrowhead 8.3px outside it.
    """
    spec = _fanned_duplex_spec(orientation=orientation, chips=chips)
    lay = _compose_layout(spec)
    boxes = {n.index: n.box for n in lay.nodes}
    for idx in (0, 1):
        conn = lay.connectors[idx]
        pts = _sample_any(conn.path_d)
        src, tgt = boxes[conn.source_index], boxes[conn.target_index]
        assert _inside_depth(pts[0], src) <= 1.0, (
            f"{orientation} channel {idx} departs {_inside_depth(pts[0], src):.1f}px inside its source card"
        )
        assert _box_gap(pts[-1], tgt) <= 3.5, (
            f"{orientation} channel {idx} stops {_box_gap(pts[-1], tgt):.1f}px short of its target"
        )


def _inside_depth(p: tuple[float, float], box: Any) -> float:
    x, y = p
    if not (box.x <= x <= box.x + box.w and box.y <= y <= box.y + box.h):
        return 0.0
    return min(x - box.x, box.x + box.w - x, y - box.y, box.y + box.h - y)


def _box_gap(p: tuple[float, float], box: Any) -> float:
    x, y = p
    dx = max(box.x - x, 0.0, x - (box.x + box.w))
    dy = max(box.y - y, 0.0, y - (box.y + box.h))
    return math.hypot(dx, dy)
