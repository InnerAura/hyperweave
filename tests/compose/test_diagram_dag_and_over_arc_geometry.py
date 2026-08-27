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
def test_conduit_chips_never_overlap(pairs: int, orientation: str) -> None:
    lay = _compose_layout(_duplex_spec(pairs, orientation=orientation, chips=True))
    chips = [a for a in lay.annotations if a.kind == "edge-chip" and a.box is not None]
    assert len(chips) == pairs * 2, "every declared chip rendered as a pill"
    for a, b in itertools.combinations(chips, 2):
        ox = min(a.box.x + a.box.w, b.box.x + b.box.w) - max(a.box.x, b.box.x)
        oy = min(a.box.y + a.box.h, b.box.y + b.box.h) - max(a.box.y, b.box.y)
        assert ox <= 0 or oy <= 0, (
            f"{orientation} {pairs}-pair: chips overlap by {ox:.1f}x{oy:.1f} — "
            f"{[t.text for t in a.lines]} and {[t.text for t in b.lines]}"
        )


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
def test_both_channels_of_a_conduit_keep_the_same_label_grammar(orientation: str) -> None:
    # One conduit cannot be half pill and half bare text.
    lay = _compose_layout(_duplex_spec(2, orientation=orientation, chips=True))
    kinds = [a.kind for a in lay.annotations if a.box is not None]
    assert set(kinds) == {"edge-chip"}, f"mixed label grammar on a conduit: {sorted(set(kinds))}"


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
def test_fanned_duplex_draws_the_familys_own_curve(orientation: str, chips: bool) -> None:
    """A fanned conduit is the family's S-curve, not a chord.

    Both channels must be cubics whose control points sit at the major
    midpoint, exactly like the plain edge beside them — a straight ``L``
    chord read as foreign geometry against its own siblings.
    """
    spec = _fanned_duplex_spec(orientation=orientation, chips=chips)
    lay = _compose_layout(spec)
    plain = lay.connectors[2].path_d
    assert "C" in plain, "precondition: the family draws its plain edges as cubics"
    for idx in (0, 1):
        d = lay.connectors[idx].path_d
        assert "C" in d and " L " not in d, f"conduit channel {idx} drew a chord, not the family's curve: {d}"


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
def test_fanned_duplex_channels_stay_parallel(orientation: str) -> None:
    """Shifting both endpoints of a cubic by one pitch translates the whole
    curve, so the two channels hold their separation end to end rather than
    pinching or splaying."""
    lay = _compose_layout(_fanned_duplex_spec(orientation=orientation, chips=True))
    a = _sample_any(lay.connectors[0].path_d)
    b = list(reversed(_sample_any(lay.connectors[1].path_d)))
    n = min(len(a), len(b))
    seps = [math.hypot(a[i][0] - b[i][0], a[i][1] - b[i][1]) for i in range(n)]
    assert max(seps) - min(seps) < 6.0, (
        f"{orientation}: conduit separation drifts {min(seps):.1f}..{max(seps):.1f}px along the run"
    )


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
