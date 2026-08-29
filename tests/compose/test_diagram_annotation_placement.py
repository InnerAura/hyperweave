"""Property tests: caller free-text annotations clear content and never truncate.

Run across the GENERATED topology stories — the same specs
``python -m scripts.examples.diagrams`` composes into the proofset — so the
placement policy is graded on real, composed diagrams, not toy inputs. For
EVERY callout / aside / pin / badge in every story the engine must:

  (a) keep the annotation box inside the final canvas,
  (b) never overlap a card rect (cards paint OVER annotations — any overlap
      clips the text behind the card),
  (c) never cross a connector wire (sampled from the bezier path), and
  (d) render every authored word — no ellipsis, no dropped tail.

An ``at``-anchored aside is honored positionally: its block centres on the
authored horizontal fraction, the canvas growing outward rather than the note
being shoved into the diagram. These are the six-bug regressions as invariants:
compose-pipeline / publish-path / verb-roundtrip (callout on the wire row or
under a card), glyph-ladder (aside dragged up), format-ladder (detached pin),
spec-boundary (callout straddling a hub spoke).
"""

from __future__ import annotations

import itertools
import math
import pathlib
import re
from typing import Any

import pytest

from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import coerce_diagram_input
from hyperweave.config.loader import load_diagram_config, load_glyphs, load_paradigms
from hyperweave.core.models import ComposeSpec
from hyperweave.core.paradigm import ParadigmDiagramConfig

_REPO = pathlib.Path(__file__).resolve().parents[2]


def _load_stories() -> list[tuple[str, str, dict[str, Any]]]:
    """The PIPELINE/FANOUT/HUB story lists, from the generator module.

    Loaded by file path until the generators became a package; a plain import
    now, so a move cannot leave this pointing at a path that does not exist.
    """
    from scripts.examples import diagrams

    return [*diagrams.PIPELINE, *diagrams.FANOUT, *diagrams.HUB]


_STORIES = _load_stories()
_CALLER_KINDS = ("callout", "aside", "pin", "badge")
_ELLIPSIS = "…"


def _layout(spec_dict: dict[str, Any]) -> Any:
    """Solve a diagram story to its layout record (no SVG), primer/porcelain —
    the same chassis the proofset renders under."""
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


def _flatten(d: str) -> list[tuple[float, float]]:
    """Sample a connector 'd' into a polyline (M/L exact, C at 10 steps)."""
    toks = re.findall(r"[MLC]|-?[0-9.]+", d)
    pts: list[tuple[float, float]] = []
    cur = (0.0, 0.0)
    i = 0
    while i < len(toks):
        c = toks[i]
        if c in ("M", "L"):
            cur = (float(toks[i + 1]), float(toks[i + 2]))
            pts.append(cur)
            i += 3
        elif c == "C":
            x1, y1, x2, y2, x3, y3 = (float(toks[i + j]) for j in range(1, 7))
            p0 = cur
            for s in range(1, 11):
                u = s / 10
                mx = (1 - u) ** 3 * p0[0] + 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u * u * x2 + u**3 * x3
                my = (1 - u) ** 3 * p0[1] + 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u * u * y2 + u**3 * y3
                pts.append((mx, my))
            cur = (x3, y3)
            i += 7
        else:
            i += 1
    return pts


def _overlap(a: Any, b: Any) -> float:
    ix = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    iy = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    return ix * iy if ix > 0 and iy > 0 else 0.0


def _seg_in_box(p: tuple[float, float], q: tuple[float, float], box: Any) -> bool:
    for s in range(0, 7):
        u = s / 6
        x = p[0] + (q[0] - p[0]) * u
        y = p[1] + (q[1] - p[1]) * u
        if box.x <= x <= box.x + box.w and box.y <= y <= box.y + box.h:
            return True
    return False


def _caller_anns(layout: Any) -> list[Any]:
    return [a for a in layout.annotations if a.kind in _CALLER_KINDS and a.box is not None]


# ── The invariants, parametrized over every story ────────────────────────────

_IDS = [s[0] for s in _STORIES]


@pytest.mark.parametrize(("slug", "source", "spec"), _STORIES, ids=_IDS)
def test_annotation_box_within_canvas(slug: str, source: str, spec: dict[str, Any]) -> None:
    """Every caller annotation box lies inside the final (grown) canvas."""
    lay = _layout(spec)
    for a in _caller_anns(lay):
        b = a.box
        assert b.x >= -0.5 and b.y >= -0.5, f"{slug}: {a.kind} box starts off-canvas at ({b.x:.1f},{b.y:.1f})"
        assert b.x + b.w <= lay.width + 0.5, f"{slug}: {a.kind} box right {b.x + b.w:.1f} > width {lay.width}"
        assert b.y + b.h <= lay.height + 0.5, f"{slug}: {a.kind} box bottom {b.y + b.h:.1f} > height {lay.height}"


@pytest.mark.parametrize(("slug", "source", "spec"), _STORIES, ids=_IDS)
def test_no_annotation_card_overlap(slug: str, source: str, spec: dict[str, Any]) -> None:
    """No caller annotation box overlaps a card — cards paint over the
    annotation layer, so any overlap is clipped text (bugs 1/2/3/4)."""
    lay = _layout(spec)
    cards = [n.box for n in lay.nodes]
    for a in _caller_anns(lay):
        hits = [(i, _overlap(a.box, c)) for i, c in enumerate(cards) if _overlap(a.box, c) > 0.5]
        text = " ".join(t.text for t in a.lines)
        assert not hits, f"{slug}: {a.kind} {text!r} overlaps card(s) {hits}"


@pytest.mark.parametrize(("slug", "source", "spec"), _STORIES, ids=_IDS)
def test_no_annotation_wire_overlap(slug: str, source: str, spec: dict[str, Any]) -> None:
    """No caller annotation box crosses a connector wire (the hub-spoke
    straddle). Edge labels/chips ride wires by design and are not caller kinds,
    so they are out of scope here."""
    lay = _layout(spec)
    polys = [_flatten(c.path_d) for c in lay.connectors]
    for a in _caller_anns(lay):
        for poly in polys:
            crossing = [k for k in range(len(poly) - 1) if _seg_in_box(poly[k], poly[k + 1], a.box)]
            if crossing:
                text = " ".join(t.text for t in a.lines)
                pytest.fail(f"{slug}: {a.kind} {text!r} box {a.box} crosses a wire at {poly[crossing[0]]}")


@pytest.mark.parametrize(("slug", "source", "spec"), _STORIES, ids=_IDS)
def test_annotation_text_complete(slug: str, source: str, spec: dict[str, Any]) -> None:
    """Every authored callout/aside/pin word renders — no ellipsis, nothing
    dropped (an earlier regression lost 'compute' to the collide re-wrap ladder)."""
    lay = _layout(spec)
    rendered = " ".join(t.text for a in lay.annotations for t in a.lines)
    assert _ELLIPSIS not in rendered, f"{slug}: an annotation ellipsized: {rendered!r}"
    for ann in spec.get("annotations", []):
        if ann.get("kind", "callout") not in ("callout", "aside", "micro-label"):
            continue
        for word in str(ann["text"]).split():
            assert word in rendered, f"{slug}: authored word {word!r} missing from rendered {rendered!r}"


@pytest.mark.parametrize(("slug", "source", "spec"), _STORIES, ids=_IDS)
def test_at_anchored_aside_honored(slug: str, source: str, spec: dict[str, Any]) -> None:
    """An ``at``-anchored aside centres on the authored horizontal fraction —
    honored positionally even when the canvas grows to clear it (the
    aside was dragged 67px up into the diagram instead)."""
    at_asides = [a for a in spec.get("annotations", []) if a.get("kind") == "aside" and a.get("at")]
    if not at_asides:
        pytest.skip("no at-anchored aside in this story")
    lay = _layout(spec)
    placed = [a for a in lay.annotations if a.kind == "aside" and a.box is not None]
    assert placed, f"{slug}: at-anchored aside did not place"
    for authored, p in zip(at_asides, placed, strict=False):
        fx = float(authored["at"][0])
        center_x = p.box.x + p.box.w / 2
        want_x = fx * lay.width
        assert math.isclose(center_x, want_x, abs_tol=6.0), (
            f"{slug}: aside centre-x {center_x:.1f} not near authored {fx}*{lay.width}={want_x:.1f}"
        )


def test_gather_note_clears_grounded_chip() -> None:
    """A gather trunk's plain-labeled note seats tight BELOW the grounded
    chip's own box (convergence, lift=0) at the trunk x — the seat law
    decides the position, never the collide ladder. Before the fix the note's
    preferred seat landed inside the chip pill and the ladder flung it ~90px
    into blank space (the convergence-arrivals 'one seed' float)."""
    spec = {
        "title": "gather note clearance",
        "topology": "fanin",
        "nodes": [
            {"id": "a", "label": "alpha", "desc": "input"},
            {"id": "b", "label": "beta", "desc": "input"},
            {"id": "c", "label": "gamma", "desc": "input"},
            {"id": "d", "label": "delta", "desc": "input"},
            {"id": "sink", "label": "the sink", "desc": "one mouth", "role": "hero", "gather": True},
        ],
        "edges": [
            {"source": "a", "target": "sink", "relation": "drift", "label": "compose", "label_style": "chip"},
            {"source": "b", "target": "sink", "relation": "drift", "label": "one seed"},
            {"source": "c", "target": "sink", "relation": "drift"},
            {"source": "d", "target": "sink", "relation": "drift"},
        ],
    }
    lay = _layout(spec)
    chips = [a for a in lay.annotations if a.kind == "edge-chip"]
    notes = [a for a in lay.annotations if a.kind == "label" and "seed" in " ".join(t.text for t in a.lines)]
    assert len(chips) == 1, f"expected one gather chip, got {len(chips)}"
    assert len(notes) == 1, f"expected one gather note, got {len(notes)}"
    chip, note = chips[0], notes[0]
    assert _overlap(chip.box, note.box) == 0.0, f"note box {note.box} overlaps chip box {chip.box}"
    gap = note.box.y - (chip.box.y + chip.box.h)
    assert 0.0 < gap <= 16.0, f"note hangs {gap:.1f}px under the chip — expected a tight standoff, not a fling"
    chip_cx = chip.box.x + chip.box.w / 2
    note_cx = note.box.x + note.box.w / 2
    assert abs(note_cx - chip_cx) <= 1.0, f"note centre {note_cx:.1f} left the trunk x (chip centre {chip_cx:.1f})"


def _story_spec(slug: str) -> dict[str, Any]:
    hits = [s for s in _STORIES if s[0] == slug]
    assert hits, f"story {slug!r} not in the gallery lists"
    return hits[0][2]


def test_node_anchored_callout_centers_under_anchor() -> None:
    """compose-pipeline: the callout anchored to `solve` centres under the
    solve card itself — not the content bbox's middle, which the wider hero
    at the row's end pulls ~14px right of the anchor."""
    lay = _layout(_story_spec("compose-pipeline"))
    callout = next(a for a in lay.annotations if a.kind == "callout")
    solve = next(n for n in lay.nodes if n.node_id == "solve")
    want = solve.box.x + solve.box.w / 2
    got = callout.box.x + callout.box.w / 2
    assert math.isclose(got, want, abs_tol=2.0), f"callout centre {got:.1f} vs anchor centre {want:.1f}"


def test_at_anchored_fractions_order_and_mirror() -> None:
    """Two asides at 0.25/0.75 place mirrored about the canvas centre, in
    authored order — the fraction carries real horizontal information (the
    old band centring collapsed every fraction onto one x)."""
    spec = {
        "title": "fractions",
        "topology": "pipeline",
        "nodes": [
            {"id": "a", "label": "alpha", "desc": "one"},
            {"id": "b", "label": "beta", "desc": "two"},
            {"id": "c", "label": "gamma", "desc": "three"},
            {"id": "d", "label": "delta", "desc": "four"},
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
            {"source": "c", "target": "d"},
        ],
        "annotations": [
            {"text": "left note", "kind": "aside", "at": [0.25, 0.9]},
            {"text": "right note", "kind": "aside", "at": [0.75, 0.9]},
        ],
    }
    lay = _layout(spec)
    asides = [a for a in lay.annotations if a.kind == "aside"]
    assert len(asides) == 2
    left, right = sorted(asides, key=lambda a: a.box.x)
    assert any("left" in t.text for t in left.lines), "authored order not preserved"
    lc = left.box.x + left.box.w / 2
    rc = right.box.x + right.box.w / 2
    assert rc - lc > 40.0, f"fractions collapsed: centres {lc:.1f} / {rc:.1f}"
    mid = lay.width / 2
    assert math.isclose(mid - lc, rc - mid, abs_tol=8.0), (
        f"not mirrored about centre {mid:.1f}: left {lc:.1f}, right {rc:.1f}"
    )


def test_annotation_runs_use_annotation_voice() -> None:
    """Every caption-band annotation renders in the `ann` voice — never the
    footer caption's `cap` voice (the two-stacked-captions symptom)."""
    for slug, _src, spec in _STORIES:
        if not spec.get("annotations"):
            continue
        lay = _layout(spec)
        for a in lay.annotations:
            if a.kind in ("callout", "aside"):
                classes = [t.cls for t in a.lines]
                assert all(c == "ann" for c in classes), f"{slug}: {a.kind} renders as {classes}"


def test_annotation_footer_gap_min() -> None:
    """publish-path: the footer caption sits at least annotation_footer_gap
    below the callout block — two text bands never read as one stack."""
    lay = _layout(_story_spec("publish-path"))
    callout = next(a for a in lay.annotations if a.kind == "callout")
    assert lay.footer is not None, "publish-path story lost its footer caption"
    gap = lay.footer.y - (callout.box.y + callout.box.h)
    assert gap >= 39.5, f"footer baseline only {gap:.1f}px under the callout block"


# ── Edge-label ownership ────────────────────────────────────────────────────
#
# A micro-label is attributed by PROXIMITY — there is no leader line to a bare
# run, so the wire it sits nearest is the wire a reader reads it against. The
# placement passes had no notion of this: the perpendicular lift always chose
# "above", and the collide ladder's bar is zero OVERLAP. On a fan, "above"
# points out of the diagram for the edge curving up and straight INTO the fan
# for the edge curving down, so a lower edge's label was lifted toward its
# siblings, cleared of overlap by the ladder, and left sitting almost exactly
# between two wires. Not-overlapping and attributable are different properties,
# and only the first one was ever checked.


def _label_anns(layout: Any) -> list[Any]:
    """Subsumed edge micro-labels — bare text beside a wire. Chips are exempt
    by construction: a pill rides ON its run, so its own distance is ~0 and
    ownership is never in question."""
    return [a for a in layout.annotations if a.kind == "label" and a.box is not None]


def _duplex_labels(spec_dict: dict[str, Any]) -> set[str]:
    """Labels belonging to a reciprocal pair, which the law exempts.

    A request/response pair is DRAWN as two wires side by side and its labels
    belong in the channel between them — nearness to the partner wire is the
    vocabulary there, not a failure to attribute. Exempt from day one rather
    than after the fact: the dag solver takes reciprocal pairs natively next,
    and a law that fought the duplex grammar would be self-inflicted."""
    edges = spec_dict.get("edges") or []
    pairs = {
        (e.get("source"), e.get("target"))
        for e in edges
        if any(o.get("source") == e.get("target") and o.get("target") == e.get("source") for o in edges)
    }
    return {str(e.get("label")) for e in edges if (e.get("source"), e.get("target")) in pairs and e.get("label")}


def _wire_distance(px: float, py: float, poly: list[tuple[float, float]]) -> float:
    best = math.inf
    for a, b in itertools.pairwise(poly):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
        best = min(best, math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy)))
    return best


@pytest.mark.parametrize(
    ("slug", "source", "spec"), [(s[0], s[1], s[2]) for s in _STORIES], ids=[s[0] for s in _STORIES]
)
def test_edge_label_reads_against_its_own_wire(slug: str, source: str, spec: dict[str, Any]) -> None:
    """Every bare edge label sits decisively nearer ONE wire than any other.

    Graded at the FINAL seat — after the lift and after the collide ladder —
    because that is the only position a reader ever sees, and because it
    catches a regression from either lift path rather than just the
    perpendicular fallback. The ratio floor is calibrated from this corpus:
    healthy labels sit at 2.3x and above, the borderline band is 1.34-1.44x,
    and the failure that motivated the law measured 1.01x.
    """
    from hyperweave.compose.diagram.annotate import OWNERSHIP_MIN_RATIO

    lay = _layout(spec)
    polys = [_flatten(c.path_d) for c in lay.connectors]
    polys = [p for p in polys if len(p) >= 2]
    if len(polys) < 2:
        pytest.skip("single-wire diagram — nothing to confuse a label with")
    exempt = _duplex_labels(spec)
    for ann in _label_anns(lay):
        text = " ".join(t.text for t in ann.lines)
        if text in exempt:
            continue
        cx, cy = ann.box.x + ann.box.w / 2, ann.box.y + ann.box.h / 2
        ds = sorted(_wire_distance(cx, cy, p) for p in polys)
        if ds[0] <= 1e-9:
            continue  # sitting ON its wire: unambiguous
        ratio = ds[1] / ds[0]
        assert ratio >= OWNERSHIP_MIN_RATIO, (
            f"{slug}: label {text!r} sits {ds[0]:.1f}px from one wire and {ds[1]:.1f}px from the next "
            f"({ratio:.2f}x, law >={OWNERSHIP_MIN_RATIO}x) — a reader cannot tell which edge it labels"
        )


_FAN_SPEC: dict[str, Any] = {
    "topology": "dag",
    "title": "readme-ai Architecture",
    "node_style": "card+glyph",
    "nodes": [
        {"id": "cli", "label": "CLI Interface", "desc": "Commands & Configuration", "glyph": "terminal"},
        {"id": "parsers", "label": "Parsers & Extractors", "desc": "AST & Dependency Analysis", "glyph": "package"},
        {
            "id": "core",
            "label": "Pipeline Engine",
            "desc": "readme-ai async orchestrator",
            "glyph": "cpu",
            "role": "hero",
        },
        {"id": "models", "label": "Model Providers", "desc": "OpenAI / Gemini / Claude / Ollama", "glyph": "sparkles"},
        {"id": "generators", "label": "Markdown & Visuals", "desc": "HyperWeave SVGs & Docs", "glyph": "layers"},
    ],
    "edges": [
        {"source": "cli", "target": "core", "label": "invoke", "label_style": "chip"},
        {"source": "core", "target": "parsers", "label": "extract", "label_style": "chip"},
        {"source": "core", "target": "models", "label": "synthesize", "label_style": "chip"},
        {"source": "core", "target": "generators", "label": "render", "label_style": "chip", "relation": "assert"},
    ],
}


def _seat_of(lay: Any, text: str) -> tuple[float, float]:
    hits = [a for a in lay.annotations if a.box is not None and " ".join(t.text for t in a.lines) == text]
    assert len(hits) == 1, f"expected one {text!r} annotation, found {len(hits)}"
    return (hits[0].box.x + hits[0].box.w / 2, hits[0].box.y + hits[0].box.h / 2)


def _ratio_of(lay: Any, text: str) -> float:
    cx, cy = _seat_of(lay, text)
    polys = [p for p in (_flatten(c.path_d) for c in lay.connectors) if len(p) >= 2]
    ds = sorted(_wire_distance(cx, cy, p) for p in polys)
    return math.inf if ds[0] <= 1e-9 else ds[1] / ds[0]


class TestFanLabelOwnership:
    """The fan that motivated the ownership law.

    Three edges leave one hero: one curves up, one runs straight, one curves
    down. The up and down edges both bend past ``_chip_bend_max``, so both
    lose their pill (correct — a chip has no home on bending wire) and fall to
    the perpendicular lift. Under the old unconditional "above", the DOWN
    edge's label was lifted into the fan toward its siblings.
    """

    def test_downward_edge_label_is_attributable(self) -> None:
        # Measured 1.01x before the clear-side lift: 35.92px from its own wire
        # and 36.46px from the neighbouring one — it won ownership by 0.54px.
        lay = _layout(_FAN_SPEC)
        assert _ratio_of(lay, "render") >= 1.5

    def test_upward_edge_label_keeps_its_default_seat(self) -> None:
        # Hysteresis: a label whose default (above) seat already reads clear
        # must not be moved by the clear-side check. This is the
        # byte-stability half of the rule — a side chosen by bare comparison
        # would trade seats between near-identical renders for no legibility
        # gain.
        #
        # Graded as "the seat does not move when foreign geometry is hidden"
        # rather than against a pinned coordinate: the bent-chip amendment
        # made this fan's curved edges keep floated PILLS, so the micro-label
        # this once pinned by hand is no longer the shape under test, and a
        # literal (770.1, 99.2) would only ever pin whichever label happened
        # to survive.
        import hyperweave.compose.diagram.annotate as _annotate

        lay = _layout(_FAN_SPEC)
        bare = [a for a in lay.annotations if a.kind == "label" and a.box is not None]
        if not bare:
            pytest.skip("this fan carries no bare micro-label to grade")
        seats = {" ".join(t.text for t in a.lines): (a.box.x, a.box.y) for a in bare}
        real = _annotate._foreign_wires
        _annotate._foreign_wires = lambda ctx, geos, j: []
        try:
            plain = _layout(_FAN_SPEC)
        finally:
            _annotate._foreign_wires = real
        for a in plain.annotations:
            if a.kind != "label" or a.box is None:
                continue
            text = " ".join(t.text for t in a.lines)
            if text in seats:
                assert seats[text] == pytest.approx((a.box.x, a.box.y), abs=0.5), (
                    f"{text!r} moved although its default seat already read clear"
                )

    def test_every_declared_chip_keeps_its_pill(self) -> None:
        # AMENDED: this once asserted only the two STRAIGHT edges kept pills,
        # because a bent rank-step chip was demoted to a micro-label. A bent
        # chip now takes the floated seat instead, so the face carries ONE
        # label grammar — every declared chip renders as a pill, and the bent
        # ones float clear of their stroke rather than riding it.
        lay = _layout(_FAN_SPEC)
        chips = {" ".join(t.text for t in a.lines) for a in lay.annotations if a.kind == "edge-chip"}
        declared = {str(e["label"]) for e in _FAN_SPEC["edges"] if e.get("label_style") == "chip"}
        assert chips == declared


def test_duplex_labels_are_exempt_from_the_ownership_law() -> None:
    """A reciprocal pair's labels belong BETWEEN its two wires.

    ``pipeline-row`` draws client⇄hw as `request →` over `← response`; both
    sit at 1.34x, under the floor, and both are correct. The exemption is
    keyed off the spec's own reciprocal edges, so it holds for any duplex the
    dag solver draws rather than for these two strings.
    """
    from hyperweave.compose.bundled_specs import resolve_bundled_spec

    spec = dict(resolve_bundled_spec("diagram", "pipeline-row").value)
    exempt = _duplex_labels(spec)
    assert exempt == {"request →", "← response"}
    lay = _layout(spec)
    # Precondition: they really are under the floor — otherwise this test
    # would pass for the wrong reason if the seats ever drifted apart.
    assert _ratio_of(lay, "request →") < 1.5


def test_two_labels_on_one_run_take_the_bracket_on_any_topology() -> None:
    """Two labelled edges DRAWN ON THE SAME RUN never both wear a pill.

    A chip's seat is the run midpoint and the ladder may not move it, so a
    shared run pins two plates to one point and they fuse by construction.
    The slide ladder cannot rescue it either: separating these two pills
    needs ~141px where the whole slack on their 253px run is 32. So the pair
    drops the pill and brackets the run instead — one label above, one below.

    Graded on `hub`, which has no duplex machinery of its own: the law lives
    in the shared annotation pass, not in a solver, so it holds wherever the
    geometry happens rather than only where a solver was taught about it.
    """
    spec = {
        "topology": "hub",
        "title": "t",
        "nodes": [
            {"id": "h", "label": "Orchestrator", "role": "hero"},
            {"id": "a", "label": "Providers"},
            {"id": "b", "label": "Parsers"},
            {"id": "c", "label": "Docs"},
            {"id": "d", "label": "Runtime"},
            {"id": "e", "label": "Config"},
            {"id": "f", "label": "Scanner"},
            {"id": "g", "label": "Badges"},
        ],
        "edges": [
            {"source": "h", "target": "a", "label": "prompt payload", "label_style": "chip"},
            {"source": "a", "target": "h", "label": "structured summary", "label_style": "chip"},
            *[
                {"source": "h", "target": n, "label": f"to {n}", "label_style": "chip"}
                for n in ("b", "c", "d", "e", "f", "g")
            ],
        ],
    }
    from hyperweave.compose.engine import compose

    svg = compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="opaque",
            palette="fixed",
            diagram=spec,
        )
    ).svg
    body = svg.split("</defs>")[-1]
    seats = {
        m.group(2): float(m.group(1))
        for m in re.finditer(r'<text[^>]*y="([\d.]+)"[^>]*>(prompt payload|structured summary)</text>', body)
    }
    assert set(seats) == {"prompt payload", "structured summary"}, f"a shared-run label was dropped: {seats}"
    # One line of the 10px edge-label voice plus air — these are bare runs,
    # not plates, so the floor is the ink they actually occupy.
    assert abs(seats["prompt payload"] - seats["structured summary"]) > 12.0, f"the pair still shares a row: {seats}"
    # Neither wears a pill — a plate on one lane occludes the other.
    assert "prompt payload" not in re.findall(r'-tag">([^<]+)<', body)
