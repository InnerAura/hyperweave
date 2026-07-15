"""Edge-chip seating on multi-leg routes: even thread on the CHANNEL.

The kit law seats an on-wire chip with even thread both sides of the run the
eye reads. On an HVH/VHV skip route that run is the flat channel leg — the
arc-length midpoint of the whole drawn path bakes the two (generally unequal)
risers into the seat and drifts the chip off the channel's centre by half
their difference. These tests pin the channel seat on both skip exits, prove
the seat law bites (channel mid ≠ arc mid on unequal risers), and guard the
curved-run fallback (no dominant leg → arc-length midpoint, unchanged).
"""

from __future__ import annotations

import itertools
import math
from typing import Any

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.annotate import _channel_midpoint, _polyline_midpoint
from hyperweave.compose.diagram.input import coerce_diagram_input
from hyperweave.compose.diagram.paths import sample_path
from hyperweave.config.loader import load_diagram_config, load_glyphs, load_paradigms
from hyperweave.core.models import ComposeSpec
from hyperweave.core.paradigm import ParadigmDiagramConfig


def _layout(spec_dict: dict[str, Any]) -> Any:
    cs = ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", ground="bare", diagram=spec_dict)
    normalized = coerce_diagram_input(cs.connector_data, cs)
    pmap = load_paradigms()
    pspec = pmap.get("primer")
    cfg = pspec.diagram if pspec is not None and hasattr(pspec, "diagram") else ParadigmDiagramConfig()
    return compute_diagram_layout(
        normalized.spec,
        paradigm=cfg,
        engine=load_diagram_config(),
        palette_len=6,
        glyph_registry=load_glyphs(),
    )


def _chip(lay: Any, text: str) -> Any:
    hits = [a for a in lay.annotations if a.kind == "edge-chip" and any(t.text == text for t in a.lines)]
    assert len(hits) == 1, f"expected one {text!r} edge-chip, found {len(hits)}"
    return hits[0]


def _chip_center(chip: Any) -> tuple[float, float]:
    return (chip.box.x + chip.box.w / 2, chip.box.y + chip.box.h / 2)


def _connector_through(lay: Any, cx: float, cy: float) -> tuple[tuple[float, float], ...]:
    """The sampled polyline of the connector whose drawn path passes through
    (cx, cy) — the chip's own wire (chips ground ON their run)."""
    best: tuple[float, tuple[tuple[float, float], ...]] | None = None
    for c in lay.connectors:
        poly = sample_path(c.path_d)
        d = min(_point_segment_distance(cx, cy, a, b) for a, b in itertools.pairwise(poly))
        if best is None or d < best[0]:
            best = (d, poly)
    assert best is not None and best[0] < 2.0, f"no connector runs through ({cx:.1f},{cy:.1f})"
    return best[1]


def _point_segment_distance(px: float, py: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _preset(name: str) -> dict[str, Any]:
    return dict(resolve_bundled_spec("diagram", name).value)


def test_service_dependencies_skip_chip_centers_on_channel() -> None:
    """The 'direct read' chip (exit:top skip, risers 137 vs 11) seats at the
    flat channel's own midpoint — not the whole-path arc midpoint 63px left."""
    lay = _layout(_preset("service-dependencies"))
    chip = _chip(lay, "direct read")
    cx, cy = _chip_center(chip)
    poly = _connector_through(lay, cx, cy)
    ch_x, ch_y = _channel_midpoint(poly)
    assert math.isclose(cx, ch_x, abs_tol=0.5), f"chip x {cx:.1f} != channel mid {ch_x:.1f}"
    assert math.isclose(cy, ch_y, abs_tol=0.5), f"chip y {cy:.1f} != channel y {ch_y:.1f}"
    # The seat law must BITE here: the arc-length midpoint sits well off the
    # channel mid on this route's unequal risers.
    arc_x, _ = _polyline_midpoint(poly)
    assert abs(arc_x - ch_x) > 5.0, "risers unexpectedly equal — this fixture no longer exercises the law"


def test_exit_bottom_skip_chip_centers_on_channel() -> None:
    """The frontier-serving 'telemetry' chip rides an exit:bottom skip — the
    same channel law from the mirrored exit."""
    lay = _layout(_preset("frontier-serving"))
    chip = _chip(lay, "telemetry")
    cx, cy = _chip_center(chip)
    poly = _connector_through(lay, cx, cy)
    ch_x, ch_y = _channel_midpoint(poly)
    assert math.isclose(cx, ch_x, abs_tol=0.5), f"chip x {cx:.1f} != channel mid {ch_x:.1f}"
    assert math.isclose(cy, ch_y, abs_tol=0.5), f"chip y {cy:.1f} != channel y {ch_y:.1f}"


def test_unequal_riser_property() -> None:
    """Synthetic exit:top skip with deliberately unequal riser depths: the
    chip's x equals the channel leg's midpoint x, for every seat the solver
    produces (the property, not one pinned coordinate)."""
    spec = {
        "title": "riser property",
        "topology": "dag",
        "nodes": [
            {"id": "a", "label": "alpha", "desc": "entry point with a much taller card body"},
            {"id": "b", "label": "beta", "desc": "mid"},
            {"id": "c", "label": "gamma", "desc": "mid"},
            {"id": "d", "label": "delta", "desc": "sink"},
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
            {"source": "c", "target": "d"},
            {"source": "a", "target": "d", "label": "shortcut", "label_style": "chip", "exit": "top"},
        ],
    }
    lay = _layout(spec)
    chip = _chip(lay, "shortcut")
    cx, cy = _chip_center(chip)
    poly = _connector_through(lay, cx, cy)
    ch_x, ch_y = _channel_midpoint(poly)
    assert math.isclose(cx, ch_x, abs_tol=0.5)
    assert math.isclose(cy, ch_y, abs_tol=0.5)


def test_curved_chip_keeps_arc_midpoint() -> None:
    """A chip on a C-curved run (no dominant axis-aligned leg) keeps the
    arc-length midpoint seat — the fallback is byte-stable for curves."""
    spec = {
        "title": "curved run",
        "topology": "dag",
        "nodes": [
            {"id": "a", "label": "alpha", "desc": "src"},
            {"id": "b", "label": "beta", "desc": "row peer"},
            {"id": "c", "label": "gamma", "desc": "offset sink"},
            {"id": "d", "label": "delta", "desc": "offset sink"},
        ],
        "edges": [
            {"source": "a", "target": "c", "label": "sweep", "label_style": "chip"},
            {"source": "a", "target": "d"},
            {"source": "b", "target": "d"},
        ],
    }
    lay = _layout(spec)
    chip = _chip(lay, "sweep")
    cx, cy = _chip_center(chip)
    poly = _connector_through(lay, cx, cy)
    arc_x, arc_y = _polyline_midpoint(poly)
    ch_x, ch_y = _channel_midpoint(poly)
    assert math.isclose(ch_x, arc_x, abs_tol=0.01) and math.isclose(ch_y, arc_y, abs_tol=0.01), (
        "curved run unexpectedly resolved a dominant channel leg"
    )
    assert math.isclose(cx, arc_x, abs_tol=0.5)
    assert math.isclose(cy, arc_y, abs_tol=0.5)


def test_chip_slides_to_a_clear_seat_when_a_foreign_wire_crosses() -> None:
    """The amended seat law: seated at the run midpoint; a FOREIGN wire
    crossing the pill slides the chip along its OWN run to the nearest clear
    seat (never off the wire). The monorepo build graph's skip once ran
    straight through a rank chip."""
    import itertools

    from hyperweave.compose.diagram.paths import sample_path

    spec = {
        "title": "crossing",
        "topology": "dag",
        "nodes": [
            {"id": "a", "label": "alpha"},
            {"id": "b", "label": "beta"},
            {"id": "c", "label": "gamma"},
            {"id": "d", "label": "delta"},
        ],
        "edges": [
            {"source": "a", "target": "b", "label": "carry", "label_style": "chip"},
            {"source": "b", "target": "c"},
            {"source": "c", "target": "d"},
            {"source": "a", "target": "d", "exit": "bottom"},
        ],
    }
    lay = _layout(spec)
    chips = [a for a in lay.annotations if a.kind == "edge-chip"]
    assert chips, "chip did not render"
    box = chips[0].box
    fouls = 0
    for c in lay.connectors[1:]:
        for (x1, y1), (x2, y2) in itertools.pairwise(sample_path(c.path_d)):
            if (
                min(x1, x2) < box.x + box.w
                and max(x1, x2) > box.x
                and min(y1, y2) < box.y + box.h
                and max(y1, y2) > box.y
            ):
                fouls += 1
                break
    assert fouls == 0, f"a foreign wire still crosses the chip box at ({box.x:.0f},{box.y:.0f})"


def test_chip_measures_the_voice_it_renders() -> None:
    """Criterion 2 (voice single-sourcing): every pill flows through
    solve_chip_box — width is its text measured in the SAME voice the run
    renders in (cls='tag' ≡ tag_voice), plus the fixed pads. The retired
    badge path measured tag_voice while painting the sub voice (41.93px of
    phantom side padding)."""
    from hyperweave.compose.diagram.sizing import CHIP_PAD_X
    from hyperweave.compose.matrix.cells import measure_voice
    from hyperweave.config.loader import load_paradigms

    cfg = load_paradigms()["primer"].diagram
    spec = {
        "title": "voice",
        "topology": "pipeline",
        "nodes": [
            {"id": "a", "label": "alpha"},
            {"id": "b", "label": "beta"},
            {"id": "c", "label": "gamma"},
        ],
        "edges": [
            {"source": "a", "target": "b", "label": "direct read", "label_style": "chip"},
            {"source": "b", "target": "c"},
        ],
    }
    lay = _layout(spec)
    chips = [a for a in lay.annotations if a.kind == "edge-chip"]
    assert chips and chips[0].lines
    run = chips[0].lines[0]
    assert run.cls == "tag"
    expected = measure_voice(run.text, cfg.tag_voice) + 2 * CHIP_PAD_X
    assert abs(chips[0].box.w - expected) < 0.01, (chips[0].box.w, expected)
