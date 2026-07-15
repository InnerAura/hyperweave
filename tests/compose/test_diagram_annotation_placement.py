"""Property tests: caller free-text annotations clear content and never truncate.

Run across the GENERATED topology stories — the same specs
``scripts/generate_diagram_galleries.py`` composes into the proofset — so the
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

import importlib.util
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
    """Import the PIPELINE/FANOUT/HUB story lists straight from the generator
    file (imported by path — the script is not a package)."""
    path = _REPO / "scripts" / "generate_diagram_galleries.py"
    spec = importlib.util.spec_from_file_location("_gen_galleries", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [*mod.PIPELINE, *mod.FANOUT, *mod.HUB]


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
        "topology": "convergence",
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
