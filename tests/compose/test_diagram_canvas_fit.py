"""Canvas content-fit + constant display scale.

The chassis width is the SCALE REFERENCE, not a universal canvas floor: a
narrow diagram hugs its content (first card at margin_x, no phantom centering
slack) and renders proportionally narrower at the SAME physical card size —
``display_w / chassis width`` is a constant per topology. Fixed-frame
topologies (stack, comparison, the fan family, flywheel, tree-radial) keep
their floors via ``width_floor: true``.
"""

from __future__ import annotations

import math
from typing import Any

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import coerce_diagram_input
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


def _pipeline(n: int) -> dict[str, Any]:
    names = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta"]
    nodes = [{"id": f"n{i}", "label": names[i], "desc": "stage"} for i in range(n)]
    edges = [{"source": f"n{i}", "target": f"n{i + 1}"} for i in range(n - 1)]
    return {"title": f"{n} stages", "topology": "pipeline", "nodes": nodes, "edges": edges}


def test_narrow_pipeline_hugs_margin() -> None:
    """A 3-node pipeline's first card sits at margin_x — no phantom slack
    from a 1000px canvas floor (read-side sat at x=142.21 before)."""
    lay = _layout(_pipeline(3))
    first = min(n.box.x for n in lay.nodes)
    assert math.isclose(first, 40.0, abs_tol=0.5), f"first card at x={first:.2f}, expected margin_x=40"
    assert lay.width < 1000, f"canvas still floored: width={lay.width}"


def test_display_scale_constant_under_reference() -> None:
    """Two regimes: content UNDER the chassis reference renders at the
    CONSTANT scale display_w/chassis width (one physical card size at any
    node count — the 3-node pipeline drew ~40% larger cards under
    normalize-to-740); content PAST the reference keeps the old fit-to-pin
    (README columns clamp anything wider anyway)."""
    lay = _layout(_pipeline(3))
    assert lay.width < 1000, f"3-node content unexpectedly at/over the reference: {lay.width}"
    assert lay.display_w == round(lay.width * 740 / 1000), (
        f"display {lay.display_w} != constant-scale {round(lay.width * 740 / 1000)} at viewBox {lay.width}"
    )
    wide = _layout(_pipeline(6))
    assert wide.width > 1000, "6-node content unexpectedly under the reference"
    assert wide.display_w == 740, f"wide content must fit to the pin, got {wide.display_w}"


def test_stack_keeps_its_floor() -> None:
    """Stack is a declared fixed frame (width_floor) — a short layer column
    must not shrink-wrap into the portrait strip its specimen rejects."""
    spec = {
        "title": "layers",
        "topology": "stack",
        "nodes": [
            {"id": "app", "label": "app", "desc": "the crown", "role": "hero"},
            {"id": "api", "label": "api", "desc": "layer"},
            {"id": "db", "label": "db", "desc": "layer"},
        ],
        "edges": [{"source": "db", "target": "api"}, {"source": "api", "target": "app"}],
    }
    lay = _layout(spec)
    assert lay.width >= 900, f"stack lost its fixed frame: width={lay.width}"


def test_comparison_run_citation_holds() -> None:
    spec = {
        "title": "pair",
        "topology": "comparison",
        "nodes": [
            {"id": "before", "label": "before", "desc": "muted", "role": "muted"},
            {"id": "after", "label": "after", "desc": "hero", "role": "hero"},
        ],
        "edges": [{"source": "before", "target": "after"}],
    }
    lay = _layout(spec)
    # Edge-run law (2026-07-14, supersedes the fixed-frame floor): the frame
    # DERIVES from the panels + the hand pair's cited 220 face-to-face run.
    rects = sorted((n.box for n in lay.nodes), key=lambda b: b.x)
    run = rects[1].x - (rects[0].x + rects[0].w)
    assert abs(run - 220.0) <= 0.6, f"comparison run {run} left its citation"
    assert lay.width < 1180, f"comparison kept the retired fixed frame: width={lay.width}"


def test_hub_axial_content_fit() -> None:
    """The hub-family presets were once floor-bound at exactly 1000 (the
    suspiciously round number). Content-fit sizes them from the axial seat
    law — the verb-ontology hand file's W reach (throw 476) + E reach (412)
    — plus the satellites' own solved extents; the guard is that the canvas
    tracks that cited content, not any round floor. The two presets now
    diverge because their CROWNS cite different hand files (hub:
    pp-verb-ontology's 280x120; axial: pp-axial's 264x100) — the throws are
    unchanged, so each canvas is the shared 1080 envelope plus its own
    crown's own SNUG solve (snug-width ruling 2026-07-14: width citations
    are ceilings — the crowns and W/E satellites all solve to their ink,
    pulling both canvases in)."""
    for preset, want in (("hub", 1032), ("axial", 1072)):
        spec = dict(resolve_bundled_spec("diagram", preset).value)
        lay = _layout(spec)
        assert lay.width == want, f"{preset}: canvas left the cited seat reach (width={lay.width}, want {want})"
        assert lay.display_w == 740, f"{preset}: display cap moved ({lay.display_w})"


def test_dag_rank_locks_are_per_column() -> None:
    """Kit law: widths even only within stacked columns — a trivial rank must
    not inherit a distant rank's long labels (the service-dependencies
    specimen carries three column widths in one file)."""
    spec = {
        "title": "ranks",
        "topology": "dag",
        "nodes": [
            {"id": "in", "label": "x"},
            {"id": "mid", "label": "a much much longer stage label", "desc": "a long descriptive subtitle line"},
            {"id": "out", "label": "y"},
        ],
        "edges": [{"source": "in", "target": "mid"}, {"source": "mid", "target": "out"}],
    }
    lay = _layout(spec)
    widths = sorted(n.box.w for n in lay.nodes)
    assert widths[0] < widths[-1] - 40, f"trivial ranks inherited the long rank's width: {widths}"


def test_glyph_slot_is_the_kit_24() -> None:
    """The 24px glyph slot (kit sheet law): no standard node chassis may
    override it back down — the 16px era read tiny in the card gutter."""
    from hyperweave.config.loader import load_paradigms

    cfg = load_paradigms()["primer"].diagram
    for slug, ch in cfg.topologies.items():
        assert not (0 < ch.node.glyph_w < 24), f"{slug} shrinks the glyph slot to {ch.node.glyph_w}"
