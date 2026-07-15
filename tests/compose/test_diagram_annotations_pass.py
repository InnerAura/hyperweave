"""Annotation chrome pass — edge-label subsumption, placement, anti-collision.

Two guarantees anchor these tests. First, MIGRATION PARITY: the edge labels
sequence and state-machine used to wire in ``wiring.py`` must render at the
SAME ``(x, y, text, anchor)`` after subsumption — the pins below were captured
from the pre-subsumption output, so a coordinate drift is a visual regression.
Second, COLLISION CORRECTNESS: genuinely overlapping annotations separate
deterministically (byte-identical across runs), an authored label never
false-collides with its own edge, and an unresolvable overlap warns rather
than crashing or dropping.
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.annotate import base_regions
from hyperweave.compose.diagram.input import coerce_diagram_input, resolve_auto_roles
from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_diagram_config, load_glyphs, load_paradigms
from hyperweave.core.diagram import DiagramInputError, DiagramSpec
from hyperweave.core.models import ComposeSpec
from hyperweave.core.paradigm import ParadigmDiagramConfig


def _layout(spec_dict: dict) -> object:
    """Solve a diagram to its layout record (no SVG) under the primer chassis."""
    cs = ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=spec_dict)
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


def _labels(layout: object) -> list[tuple[float, float, str, str]]:
    """Every subsumed edge-label run as (x, y, text, anchor)."""
    out: list[tuple[float, float, str, str]] = []
    for a in layout.annotations:  # type: ignore[attr-defined]
        if a.kind != "label":
            continue
        for line in a.lines:
            out.append((round(line.x, 2), round(line.y, 2), line.text, line.anchor))
    return out


# ── Migration parity pins (captured pre-subsumption from wiring.py output) ────

_SEQ_SPEC = {
    "title": "Auth Flow",
    "topology": "sequence",
    "nodes": [{"id": "u", "label": "User"}, {"id": "a", "label": "API"}, {"id": "d", "label": "DB"}],
    "edges": [
        {"source": "u", "target": "a", "label": "login", "kind": "call"},
        {"source": "a", "target": "d", "label": "query user", "kind": "call"},
        {"source": "d", "target": "a", "label": "row", "kind": "return"},
        {"source": "a", "target": "u", "label": "token", "kind": "return"},
    ],
}
# Re-captured after the auth-sequence anatomy rebuild (compact head cards,
# margin_x/lifeline_gap retuned) — the SUBSUMPTION parity these pins guard
# (label_pos -> annotation, byte-identical) is unchanged relative to the wires.
# Re-captured again for caption chrome (the masthead band no longer reserves
# space above content — every label shifted up by the retired band's height).
# Re-pinned (content-fit): the canvas floor released, shifting ALL
# labels uniformly -119.5px x (verified pure translation, y unchanged).
_SEQ_PINS = [
    (214.0, 115.0, "login", "middle"),
    (447.0, 187.0, "query user", "middle"),
    (447.0, 259.0, "row", "middle"),
    (214.0, 331.0, "token", "middle"),
]

_SM_SPEC = {
    "title": "Order FSM",
    "topology": "state-machine",
    "nodes": [
        {"id": "new", "label": "New"},
        {"id": "paid", "label": "Paid"},
        {"id": "ship", "label": "Shipped"},
        {"id": "done", "label": "Done", "role": "hero"},
        {"id": "cancel", "label": "Cancelled"},
    ],
    "edges": [
        {"source": "new", "target": "paid", "label": "pay"},
        {"source": "paid", "target": "ship", "label": "fulfill"},
        {"source": "ship", "target": "done", "label": "deliver"},
        {"source": "paid", "target": "cancel", "label": "refund request"},
        {"source": "cancel", "target": "new", "label": "reopen"},
    ],
}
# Re-pinned: the SM initial pseudo-state is authored-only now (chassis
# stub_len default 0), so an undeclared machine starts 11.5px further left.
# Re-pinned again (content-fit): the canvas floor released, shifting
# ALL labels uniformly -57px x (verified pure translation, y unchanged).
_SM_PINS = [
    # Re-pinned (pill retirement): the state chain renders the specimen's
    # rx-13 glyph cards — content-solved card widths shift the label anchors.
    # Re-pinned again (bare-label face-clearance law): chip_run_min folded
    # non-chip labels into the chain-gap floor (own ink + 10.9px/face each
    # side, cited to pp-state-machine-alt2.svg) — this spec's own "refund
    # request" is the widest label in the chain, so its floor now sets
    # chain_gap uniformly wider, shifting every forward-chain label right by
    # a cumulative multiple of the same per-gap growth (a bare label used to
    # carry ZERO weight in this floor at all).
    # Re-pinned (snug-width ruling 2026-07-14): the chain cards solve to
    # their own ink, packing the whole baseline tighter — every label and
    # the under-sweep belly ride the new chain positions.
    (166.1, 55.0, "pay", "middle"),
    (348.3, 55.0, "fulfill", "middle"),
    (560.5, 55.0, "deliver", "middle"),
    # Re-pinned (label_pos convention collapse): graph.py's drop branch now
    # hands back the bare wire midpoint (290,148); annotate.py's single
    # presentation-offset owner (_solver_label_lift) applies a uniform
    # +lift/+0 nudge for start-anchored labels, replacing the branch's own
    # hand-tuned +12/+3 — same midpoint, a smaller, uniform clearance.
    # Re-pinned again (bare-label face-clearance law, see above): the same
    # chain-gap growth shifts this drop's anchor too.
    (265.2, 148.0, "refund request", "start"),
    # Re-pinned (belly-label law): the back-edge label rides the sweep's own
    # deepest point, anchor middle — the retired source-relative offset
    # landed up to 105px off the ink.
    # Re-pinned again (construction law + label_pos convention collapse):
    # the under-sweep's C1 pull is now span-proportional (~48%, was a fixed
    # ~110px) and its arrival angle follows the climb (rise) instead of a
    # forced 90deg (see graph.py's back branch) — the belly itself moves;
    # annotate.py's _solver_label_lift then clears the bare belly point by
    # sm_label_lift (8px) along the wire's own chord-relative perpendicular,
    # replacing the branch's hand-tuned "+20 below the belly".
    # Re-pinned again (default archetype depth recalibration): "reopen"
    # (cancel->new) is a short, steep off-baseline return — the same
    # DEFAULT archetype as agent-task-lifecycle's retry — and its
    # loop_dy/18.57 bases (graph.py's back branch) were recalibrated off
    # pp-state-machine-alt2.svg's retry deviation (32.9px; the old
    # loop_dy=24/47.0 rendered that specimen edge 30% over the law's +-15%
    # band). The shared constant shift moves this belly too.
    # Re-pinned again (bare-label face-clearance law, see above): the wider
    # chain also widens the whole baseline span the drop's under-sweep bows
    # beneath, moving its belly.
    # Re-pinned again (clearance-hung depth law): "reopen" (cancel->new) is
    # this spec's own needs_basin case (col_span=1, alone on new's underside
    # — same basin gate as ci1's retry) — the branch's depth base is no
    # longer 0.501x the source/target span (a single-point fit that hung an
    # unbounded belly on a wider graph); both controls now hang off one
    # belly_y = (deepest bottom edge the sweep crosses, cancel's own card
    # included) + a fixed 67px, cited to pp-state-machine.svg's retry
    # (graph.py's back branch). cancel's bottom (264) + 67 moves the belly
    # to 331, and the label rides it.
    # Re-pinned again (SM arrival-angle fix): corner-basin's c2x is now
    # pinned to the target's own bottom-center (dx=0) instead of a
    # rise-fit offset — ci1's own construction, EXACTLY reproduced instead
    # of approximated (the fit drifted this archetype's arrival as far as
    # 82.4deg off vertical on cicd-machine's own generated layout; "reopen"
    # is the same needs_basin archetype). c2's x moved onto tcx, shifting
    # the sweep's deepest point (hence the belly the label rides) by <1px.
    (134.82, 306.79, "reopen", "middle"),
]


def test_sequence_label_parity() -> None:
    """Sequence message labels render at the exact pre-subsumption coordinates
    (forward migration guarantee — no visual regression)."""
    assert _labels(_layout(_SEQ_SPEC)) == _SEQ_PINS


def test_state_machine_label_parity() -> None:
    """State-machine transition labels (forward, back-edge, drop) all render at
    the exact pre-subsumption coordinates — the three label_pos anchor cases."""
    assert _labels(_layout(_SM_SPEC)) == _SM_PINS


def test_label_parity_holds_through_svg() -> None:
    """End-to-end: the composed SVG carries the migrated labels in order —
    sequence messages render as the msg voice (chassis edge_label_cls: the
    specimen's native message text), same runs, same order."""
    svg = compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=_SEQ_SPEC)).svg
    runs = re.findall(r'-(?:elbl|msg)">([^<]*)</text>', svg)
    assert runs == ["login", "query user", "row", "token"]


# ── Every-topology labels (previously gated off) ─────────────────────────────


def test_edge_label_renders_on_pipeline() -> None:
    """An edge label on pipeline — a topology whose labels used to reach
    payload-only — now renders through the annotation pass."""
    spec = {
        "title": "Build",
        "topology": "pipeline",
        "nodes": [{"id": "a", "label": "Source"}, {"id": "b", "label": "Build"}, {"id": "c", "label": "Ship"}],
        "edges": [
            {"source": "a", "target": "b", "label": "commit"},
            {"source": "b", "target": "c", "label": "release"},
        ],
    }
    labels = [t for *_xy, t, _anchor in _labels(_layout(spec))]
    assert "commit" in labels and "release" in labels


def test_edge_label_renders_on_fanout() -> None:
    """Fanout labels (formerly payload-only) render via subsumption."""
    spec = {
        "title": "Dispatch",
        "topology": "fanout",
        "nodes": [
            {"id": "hub", "label": "Router"},
            {"id": "a", "label": "Worker A"},
            {"id": "b", "label": "Worker B"},
        ],
        "edges": [
            {"source": "hub", "target": "a", "label": "route"},
            {"source": "hub", "target": "b", "label": "route"},
        ],
    }
    labels = [t for *_xy, t, _anchor in _labels(_layout(spec))]
    assert labels.count("route") == 2


# ── Anti-collision ───────────────────────────────────────────────────────────


def _overlap(a: object, b: object) -> float:
    ix = max(0.0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))  # type: ignore[attr-defined]
    iy = max(0.0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))  # type: ignore[attr-defined]
    return ix * iy


_SM_COLLIDE_SPEC = {
    "title": "FSM",
    "topology": "state-machine",
    "nodes": [
        {"id": "idle", "label": "Idle"},
        {"id": "run", "label": "Running"},
        {"id": "err", "label": "Error"},
        {"id": "warn", "label": "Warning"},
    ],
    "edges": [
        {"source": "idle", "target": "run", "label": "start"},
        {"source": "run", "target": "err", "label": "fatal exception occurred"},
        {"source": "run", "target": "warn", "label": "recoverable issue detected"},
    ],
}


def test_sm_two_drop_labels_disjoint() -> None:
    """Two off-baseline states dropping from the same predecessor put their
    labels at the same x — collision must separate the boxes (the mirrored-side
    /slide ladder). All label boxes end pairwise disjoint."""
    layout = _layout(_SM_COLLIDE_SPEC)
    boxes = [a.box for a in layout.annotations if a.kind == "label" and a.box is not None]  # type: ignore[attr-defined]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            assert _overlap(boxes[i], boxes[j]) == 0.0, f"labels {i},{j} overlap"


# ── Label-vs-label minimum margin ────────────────────────────────────────────


def test_label_vs_label_keeps_minimum_margin_not_just_zero_overlap() -> None:
    """A bare zero-overlap check let two resolved labels sit a hairline
    apart (the revise/error crowd) — the resolve ladder now holds LABEL-vs-
    LABEL candidates to a minimum margin (half min_clearance, the same
    budget node/edge obstacles already carry), so a candidate merely 2px
    clear of a neighboring label is rejected; the ladder keeps searching
    until it finds one that clears the margin."""
    from hyperweave.compose.diagram.collide import Obstacle, _resolve_one
    from hyperweave.compose.diagram.records import AnnotationPlacement, DiagramText
    from hyperweave.compose.spatial_records import RectSpec

    # Label A already placed, 30px wide, at x=[100,130].
    neighbor = Obstacle(box=RectSpec(x=100.0, y=50.0, w=30.0, h=10.0), kind="label", ref=-1)
    # Label B's preferred box sits just 2px clear of A (x=[132,162]) — zero
    # overlap, but inside the margin.
    box = RectSpec(x=132.0, y=50.0, w=30.0, h=10.0)
    lines = (DiagramText(x=132.0, y=57.0, text="b", cls="elbl", anchor="start"),)
    p = AnnotationPlacement(kind="label", lines=lines, box=box)
    resolved, ok = _resolve_one(p, [neighbor], geo=None, slides=[], push_step=4.0, push_max=28.0, text_margin=9.0)
    assert ok
    assert resolved.box is not None
    gap = resolved.box.x - (neighbor.box.x + neighbor.box.w)
    assert gap >= 9.0 - 1e-6, gap


def test_clear_own_incident_slides_a_label_off_its_own_node() -> None:
    """The incident-node exclusion (a label never collision-avoids its OWN
    endpoints, by design — the authored position beside its own edge is
    never a false collision) can hide a REAL overlap: a ladder candidate
    chosen to dodge a FOREIGN obstacle can still land on the label's own
    node, since that node was never in the set the main ladder checked. The
    residual guard slides further along the SAME wire until the seat clears
    its own node too."""
    from hyperweave.compose.diagram.collide import Obstacle, _clear_own_incident
    from hyperweave.compose.diagram.records import AnnotationPlacement, DiagramText
    from hyperweave.compose.diagram.wiring import EdgeGeo
    from hyperweave.compose.spatial_records import RectSpec

    # A bowed wire (a back-edge under-sweep, not a straight chord): sliding
    # to an intermediate fraction lands off the ACTUAL polyline (inside the
    # bow), the way a real curved return's slide candidates do — a straight
    # 2-point wire would re-center each slide candidate exactly ON the line,
    # which _wire_through_box correctly rejects every time (not this guard's
    # concern; that class of edge falls through to the push ladder instead).
    geo = EdgeGeo(
        index=0,
        d="M 0,100 C 75,200 225,200 300,100",
        sx=0.0,
        sy=100.0,
        tx=300.0,
        ty=100.0,
        length=340.0,
        polyline=((0.0, 100.0), (150.0, 200.0), (300.0, 100.0)),
    )
    # The label's own incident node sits near the wire's start.
    own_node = Obstacle(box=RectSpec(x=0.0, y=85.0, w=50.0, h=30.0), kind="node", ref=0)
    # The label's current (ladder-chosen) box sits ON its own node.
    box = RectSpec(x=10.0, y=95.0, w=20.0, h=10.0)
    lines = (DiagramText(x=10.0, y=102.0, text="x", cls="elbl", anchor="start"),)
    p = AnnotationPlacement(kind="label", lines=lines, box=box)
    result = _clear_own_incident(
        p, obstacles=[], incident_obstacles=[own_node], geo=geo, slides=[0.5, 0.7, 0.9], text_margin=0.0
    )
    assert result.box is not None
    assert (result.box.x, result.box.y) != (box.x, box.y)
    ox0, oy0 = own_node.box.x, own_node.box.y
    ox1, oy1 = ox0 + own_node.box.w, oy0 + own_node.box.h
    rx0, ry0, rx1, ry1 = result.box.x, result.box.y, result.box.x + result.box.w, result.box.y + result.box.h
    assert rx1 <= ox0 or rx0 >= ox1 or ry1 <= oy0 or ry0 >= oy1, "still overlaps its own node"


def test_collision_is_deterministic() -> None:
    """No randomness: the placed annotation geometry is byte-identical across
    two independent solves of the colliding spec."""
    a = _layout(_SM_COLLIDE_SPEC)
    b = _layout(_SM_COLLIDE_SPEC)
    ann_a = [(p.kind, p.box, tuple((t.x, t.y, t.text, t.anchor) for t in p.lines)) for p in a.annotations]  # type: ignore[attr-defined]
    ann_b = [(p.kind, p.box, tuple((t.x, t.y, t.text, t.anchor) for t in p.lines)) for p in b.annotations]  # type: ignore[attr-defined]
    assert ann_a == ann_b


def test_annotations_never_overlap_node_text() -> None:
    """A callout placed near a node must not overlap the node's own box after
    collision (the node box is a clearance-inflated obstacle)."""
    spec = {
        "title": "P",
        "topology": "pipeline",
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
        "annotations": [{"text": "an important note here", "kind": "callout", "node": "b", "placement": "below"}],
    }
    layout = _layout(spec)
    callout = next(p for p in layout.annotations if p.kind == "callout")  # type: ignore[attr-defined]
    for node in layout.nodes:  # type: ignore[attr-defined]
        assert _overlap(callout.box, node.box) == 0.0


# ── Callout leader ───────────────────────────────────────────────────────────


def test_callout_leader_reaches_anchor() -> None:
    """Slot grammar (primer_diagram_language): a point-anchored callout seats in the CAPTION BAND —
    below all content, centred on its authored x-fraction, in the ANNOTATION
    voice (distinct from the footer caption's), leaderless (the three text
    homes are wire-side micro-label / in-card chip / caption band; free-zone
    parking and its leaders are retired)."""
    spec = {
        "title": "P",
        "topology": "pipeline",
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
        "annotations": [{"text": "margin annotation", "kind": "callout", "at": [0.5, 0.05]}],
    }
    layout = _layout(spec)
    callout = next(p for p in layout.annotations if p.kind == "callout")  # type: ignore[attr-defined]
    assert not callout.leader
    assert all(t_.cls == "ann" and t_.anchor == "middle" for t_ in callout.lines)
    content_bottom = max(n.box.y + n.box.h for n in layout.nodes)  # type: ignore[attr-defined]
    assert callout.box is not None and callout.box.y >= content_bottom
    ccx = callout.box.x + callout.box.w / 2
    span = [n.box.x for n in layout.nodes] + [n.box.x + n.box.w for n in layout.nodes]  # type: ignore[attr-defined]
    assert abs(ccx - (min(span) + max(span)) / 2) <= 2.0


def test_footer_legend_grows_canvas() -> None:
    """A footer-region legend reserves a band: the canvas grows and the footer
    re-anchors below the reserved space. No title/subtitle, so the baseline
    footer starts genuinely empty (caption chrome renders nothing without
    one) — isolating the legend's own growth from the caption sentence's."""
    base_spec = {
        "topology": "pipeline",
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
    }
    without = _layout(base_spec)
    footer_legend = [{"text": "live", "kind": "legend", "region": "footer", "accent": 0}]
    with_legend = _layout({**base_spec, "annotations": footer_legend})
    assert with_legend.height > without.height  # type: ignore[attr-defined]
    # The legend lives in the FOOTER region, below every content item (the
    # region stack replaced the 4px-grid growth mechanism).
    leg = next(a for a in with_legend.annotations if a.kind == "legend")  # type: ignore[attr-defined]
    content_bottom = max(n.box.y + n.box.h for n in with_legend.nodes)  # type: ignore[attr-defined]
    assert leg.box is not None and leg.box.y >= content_bottom
    assert leg.box.y + leg.box.h <= with_legend.height  # type: ignore[attr-defined]  # no-clip
    # No title/subtitle in this fixture, so there is no caption sentence —
    # the reserved footer band holds the legend alone.
    assert with_legend.footer is None  # type: ignore[attr-defined]


def test_legend_swatches_bind_accents() -> None:
    """Accent-carrying legend entries emit swatch circles bound to the flow
    palette slot; the SVG references the -flp{i} accent class."""
    spec = {
        "title": "P",
        "topology": "pipeline",
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
        "annotations": [
            {"text": "prod", "kind": "legend", "region": "footer", "accent": 0},
            {"text": "stage", "kind": "legend", "region": "footer", "accent": 1},
        ],
    }
    svg = compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=spec)).svg
    assert re.search(r'-flp0"', svg) and re.search(r'-flp1"', svg)
    assert "prod" in svg and "stage" in svg


# ── Validation: unknown region, annotations cap ──────────────────────────────


def test_unknown_region_raises() -> None:
    """A region anchor naming a region no solver registered raises a clear
    DiagramInputError listing the registered regions."""
    spec = DiagramSpec.model_validate(
        {
            "title": "P",
            "topology": "pipeline",
            "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
            "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
            "annotations": [{"text": "x", "kind": "aside", "region": "zone:N"}],
        }
    )
    normalized = resolve_auto_roles(spec)
    pmap = load_paradigms()
    with pytest.raises(DiagramInputError, match="unknown region"):
        compute_diagram_layout(
            normalized,
            paradigm=pmap["primer"].diagram,
            engine=load_diagram_config(),
            palette_len=6,
            glyph_registry=load_glyphs(),
        )


def test_annotations_cap_raises() -> None:
    """More annotations than the YAML cap raises."""
    anns = [{"text": f"n{i}", "kind": "callout", "node": "a"} for i in range(9)]
    spec = DiagramSpec.model_validate(
        {
            "title": "P",
            "topology": "pipeline",
            "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
            "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
            "annotations": anns,
        }
    )
    normalized = resolve_auto_roles(spec)
    pmap = load_paradigms()
    with pytest.raises(DiagramInputError, match="annotations"):
        compute_diagram_layout(
            normalized,
            paradigm=pmap["primer"].diagram,
            engine=load_diagram_config(),
            palette_len=6,
            glyph_registry=load_glyphs(),
        )


# ── Regions ──────────────────────────────────────────────────────────────────


def test_base_regions_partition_canvas() -> None:
    """The three base regions tile the height: header + canvas + footer bands
    are contiguous and non-overlapping."""
    ch = load_paradigms()["primer"].diagram.topologies["pipeline"]
    regions = base_regions(760.0, 216.0, ch)
    header, canvas, footer = regions["header"], regions["canvas"], regions["footer"]
    assert header.y == 0.0
    assert abs((header.y + header.h) - canvas.y) < 1e-9
    assert abs((canvas.y + canvas.h) - footer.y) < 1e-9


def test_placeless_annotation_pass_is_noop_for_labelless_topology() -> None:
    """A topology with no edge labels and no caller annotations produces an
    empty annotation tuple and zero footer growth (byte-stability)."""
    spec = {
        "title": "Compare",
        "topology": "comparison",
        "nodes": [{"id": "a", "label": "Before"}, {"id": "b", "label": "After"}],
    }
    layout = _layout(spec)
    assert layout.annotations == ()  # type: ignore[attr-defined]


def test_labelless_pipeline_does_not_grow() -> None:
    """A pipeline with no edge labels and no caller annotations leaves the
    canvas height at the chassis default (the annotate pass adds no growth)."""
    spec = {
        "title": "P",
        "topology": "pipeline",
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
    }
    layout = _layout(spec)
    assert layout.annotations == ()  # type: ignore[attr-defined]
    assert layout.height == 169  # type: ignore[attr-defined]  # h60 cards; caption_bottom_pad 44


# ── Fallback label vs its own wire (the COMPILE-on-spoke defect) ──────────────


def _segment_hits_rect(sx: float, sy: float, tx: float, ty: float, box: object) -> bool:
    """Whether the segment (sx,sy)→(tx,ty) intersects the axis-aligned rect —
    endpoint containment or a crossing of any rect edge. Exact for straight
    wires (hub spokes), no bbox over-approximation on diagonals."""
    x0, y0, x1, y1 = box.x, box.y, box.x + box.w, box.y + box.h

    def inside(px: float, py: float) -> bool:
        return x0 <= px <= x1 and y0 <= py <= y1

    if inside(sx, sy) or inside(tx, ty):
        return True

    def cross(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

    def seg_seg(ax: float, ay: float, bx: float, by: float, cx: float, cy: float, dx: float, dy: float) -> bool:
        d1 = cross(cx, cy, dx, dy, ax, ay)
        d2 = cross(cx, cy, dx, dy, bx, by)
        d3 = cross(ax, ay, bx, by, cx, cy)
        d4 = cross(ax, ay, bx, by, dx, dy)
        return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))

    edges = [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]
    return any(seg_seg(sx, sy, tx, ty, ex0, ey0, ex1, ey1) for ex0, ey0, ex1, ey1 in edges)


def test_fallback_label_clears_its_own_wire_at_any_angle() -> None:
    """A subsumed edge label placed by the perpendicular-lift FALLBACK must not
    straddle its own wire — a label's own wire is excluded from collision by
    design, so the preferred position itself has to clear it. Pre-fix, a fixed
    8px lift cleared horizontal wires only: on a hub's vertical south spoke
    (and the diagonals) the middle-anchored run sat ON the dashed wire (the
    COMPILE defect from the render review). Vertical, diagonal, and horizontal
    spokes all pin here."""
    spec = {
        "title": "Hub",
        "topology": "hub",
        "hub_policy": "compass",
        "nodes": [
            {"id": "core", "label": "CORE", "role": "hero"},
            {"id": "s", "label": "South"},
            {"id": "ne", "label": "NorthEast"},
            {"id": "e", "label": "East"},
        ],
        "edges": [
            {"source": "core", "target": "s", "zone": "S", "label": "COMPILE"},
            {"source": "core", "target": "ne", "zone": "NE", "label": "TRANSFORM"},
            {"source": "core", "target": "e", "zone": "E", "label": "EXTRACT"},
        ],
    }
    layout = _layout(spec)
    labels = [a for a in layout.annotations if a.kind == "label"]  # type: ignore[attr-defined]
    assert len(labels) == 3
    texts = {line.text for a in labels for line in a.lines}
    assert texts == {"COMPILE", "TRANSFORM", "EXTRACT"}
    for a in labels:
        assert a.box is not None
        # Every wire in the layout must stay clear of every label box — own
        # wire included (the fallback lift sizes itself to the label box).
        for c in layout.connectors:  # type: ignore[attr-defined]
            m = re.match(r"M ([\d.-]+),([\d.-]+) L ([\d.-]+),([\d.-]+)", c.path_d)
            if m is None:
                continue
            sx, sy, tx, ty = (float(g) for g in m.groups())
            assert not _segment_hits_rect(sx, sy, tx, ty, a.box), (
                " ".join(line.text for line in a.lines),
                c.path_d,
            )
