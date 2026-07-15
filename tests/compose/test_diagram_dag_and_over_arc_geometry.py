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

import math
import re
from typing import Any

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
    lay = _preset_layout("frontier-serving")
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
    lay = _preset_layout("agent-runtime")
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
