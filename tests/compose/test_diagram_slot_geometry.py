"""The card slot-rhythm law: glyph inset, text lead, name baseline,
name->desc gap, desc pitch — machine-extracted from
``primer_diagram_language.html`` into ``tests/fixtures/primer_diagram_
language.json``'s ``slot_geometry`` section (``scripts/extract_specimen_
fixtures.py``'s ``_slot_geometry``).

Two grading tiers, because a card's geometry splits into two families with
different portability:

- VERTICAL facts (name baseline, name->desc gap, desc pitch, and a card's
  solved HEIGHT) are pure function of font size + the citation-derived
  ``pad_y``/``label_desc_gap``/``desc_line_pitch`` this fix landed — no
  content-WIDTH measurement enters the formula at all, so engine and sheet
  agree to <1px. Graded at the brief's ±1.5px.
- WIDTH-coupled facts (glyph inset, text lead, solved card WIDTH) depend on
  ``place_card``'s bilateral centering, which depends on the MEASURED
  advance of this exact text run — a quantity the engine's font LUT and the
  hand specimen's rendering browser don't compute byte-identically. The
  axial nucleus ALSO carries a deliberate, pre-existing box-height/width
  inflation on top of content-solve (``axial.py``'s ``_hero_box`` "nucleus
  prominence": the crown grows toward ``factor x satellite_area``) —
  unrelated to this fix, graded with its own explicit band in that test.
  Both bands are still tight enough to fail loudly on an actual regression
  (a wrong pad constant moves these by 10s of px, not a handful).
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

_FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "primer_diagram_language.json").read_text())[
    "slot_geometry"
]

VERTICAL_TOL = 1.5
WIDTH_TOL = 6.0  # bilateral-centering + font-LUT slack (see module docstring); still catches a real regression


def _render(preset: str, overrides: dict[str, Any] | None = None) -> str:
    bs = resolve_bundled_spec("diagram", preset)
    value = copy.deepcopy(bs.value)
    if overrides:
        for node in value["nodes"]:
            if node.get("id") in overrides:
                node.update(overrides[node["id"]])
    spec = ComposeSpec(
        type="diagram", genome_id="primer", variant="porcelain", ground="opaque", palette="fixed", diagram=value
    )
    return compose(spec).svg


def _card_geometry(svg: str, *, rx: int, name_cls: str, desc_cls: str, after: int = 0) -> dict[str, float]:
    """The rendered box + derived slot metrics for the first card of corner
    radius ``rx`` at or after character offset ``after`` — mirrors
    ``scripts/extract_specimen_fixtures.py``'s ``_slot_geometry`` extraction
    so engine and sheet numbers are computed identically."""
    m = re.search(
        rf'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="{rx}\.0" class="', svg[after:]
    )
    assert m, f"no rx={rx} card rect found"
    bx, by, bw, bh = (float(g) for g in m.groups())
    tail = svg[after + m.end() : after + m.end() + 1400]
    gm = re.search(r'<g transform="translate\(([\d.]+),([\d.]+)\)', tail)
    names = re.findall(rf'<text x="([\d.]+)" y="([\d.]+)"[^>]*class="[a-z0-9-]+-{name_cls}"', tail)
    descs = re.findall(rf'<text x="([\d.]+)" y="([\d.]+)"[^>]*class="[a-z0-9-]+-{desc_cls}"', tail)
    assert names, f"no .{name_cls} text found for this card"
    nx, ny = float(names[0][0]), float(names[0][1])
    out = {
        "box_w": bw,
        "box_h": bh,
        "text_lead": nx - bx,
        "name_baseline": ny - by,
    }
    if gm:
        out["glyph_inset_x"] = float(gm.group(1)) - bx
        out["glyph_inset_y"] = float(gm.group(2)) - by
    if descs:
        out["name_desc_gap"] = float(descs[0][1]) - ny
    if len(descs) > 1:
        out["desc_pitch"] = float(descs[1][1]) - float(descs[0][1])
    return out


def _assert_close(label: str, got: dict[str, float], want: dict[str, Any], keys: list[str], tol: float) -> None:
    failures = []
    for key in keys:
        if key not in want:
            continue
        g = got.get(key)
        w = want[key]
        if g is None:
            failures.append(f"{key}: engine emitted nothing (sheet {w})")
            continue
        if abs(g - w) > tol:
            failures.append(f"{key}: engine={g:.2f} sheet={w:.2f} (Δ{abs(g - w):.2f} > ±{tol:g})")
    assert not failures, f"{label}:\n  " + "\n  ".join(failures)


# ── sheet-governed families ──────────────────────────────────────────────


def test_fanout_hero_matches_the_sheet() -> None:
    """model-router's hero carries the sheet's OWN content verbatim
    (name + 2 authored desc lines) — the router hero family, 206x104 rx16."""
    svg = _render("model-router")
    got = _card_geometry(svg, rx=16, name_cls="hname", desc_cls="hdesc")
    want = _FIXTURE["fanout-hero"]
    _assert_close(
        "fanout-hero (vertical)",
        got,
        want,
        ["name_baseline", "name_desc_gap", "desc_pitch", "glyph_inset_y"],
        VERTICAL_TOL,
    )
    _assert_close("fanout-hero (width-coupled)", got, want, ["text_lead", "glyph_inset_x"], WIDTH_TOL)
    assert abs(got["box_h"] - want["box"][1]) <= VERTICAL_TOL, (got["box_h"], want["box"])
    assert abs(got["box_w"] - want["box"][0]) <= WIDTH_TOL, (got["box_w"], want["box"])


def test_fanout_satellite_matches_the_sheet() -> None:
    """model-router's first provider door (Claude): name + 1 desc line, the
    uniform 165x76 rx13 satellite family."""
    svg = _render("model-router")
    # The satellite rect shares rx=13 with nothing else in this preset.
    got = _card_geometry(svg, rx=13, name_cls="name", desc_cls="ndesc")
    want = _FIXTURE["fanout-satellite"]
    _assert_close(
        "fanout-satellite (vertical)", got, want, ["name_baseline", "name_desc_gap", "glyph_inset_y"], VERTICAL_TOL
    )
    _assert_close("fanout-satellite (width-coupled)", got, want, ["text_lead", "glyph_inset_x"], WIDTH_TOL)
    assert abs(got["box_h"] - want["box"][1]) <= VERTICAL_TOL, (got["box_h"], want["box"])
    # Snug-width ruling 2026-07-14: the sheet's 165 uniform satellite is a
    # CEILING — the ring shares the widest door's own ink solve (154), never
    # the citation. Never wider than the sheet; uniformity still holds.
    assert got["box_w"] <= want["box"][0] + 0.6, (got["box_w"], want["box"])


def test_axial_nucleus_matches_its_hand_crown() -> None:
    """SUPERSEDED SUBJECT (crown re-cite ruling): the axial preset's crown
    now cites its OWN hand file (pp-axial: 264x100 rx16, one-line payload
    desc, name→desc gap 19) in the kit dress — the 232x112/+82 sheet
    nucleus belongs to the hand-maintained verb-algebra README asset and no
    longer dresses any preset, so the former grade-against-the-sheet
    comparison has no production carrier. What still grades tight here:
    the crown holds the citation box exactly (declared dims clamp
    prominence drift), the name→desc rhythm stays on the hand file's own
    19px gap, the kit anchor columns hold (glyph at +22, text at +60 for
    the 24 slot), and the one-line desc renders WHOLE — no wrap, no
    ellipsis (its sweep-caught overflow was the hero desc budget missing
    the text-column lead)."""
    svg = _render("axial")
    got = _card_geometry(svg, rx=16, name_cls="hname", desc_cls="hdesc")
    # Snug-width ruling 2026-07-14: the 264 hand crown is a CEILING; the
    # crown solves to its own one-line payload ink (234) at the cited 100 h.
    assert got["box_w"] == 234.0 and got["box_h"] == 100.0, (got["box_w"], got["box_h"])
    assert abs(got["name_desc_gap"] - 19.0) <= VERTICAL_TOL, got["name_desc_gap"]
    assert abs(got["glyph_inset_x"] - 22.0) <= 0.6, got["glyph_inset_x"]
    assert abs(got["text_lead"] - 60.0) <= 0.6, got["text_lead"]  # column inset: 22 anchor + 24 slot + 14 gap
    m = re.search(r'<text[^>]*class="[a-z0-9-]+-hdesc"[^>]*>([^<]*)</text>', svg)
    assert m and m.group(1) == "hw:payload · hwz/1 · sha", m.group(1) if m else "no hdesc"


def test_dag_card_matches_the_sheet() -> None:
    """gateway-balanced's own std card ('requests') — dag-seq-tree/
    pp-gateway-balanced.svg's own 150x62 rx13 tile, the dag family's node
    rhythm (pad_y 14.7 / label_desc_gap 7.6). Width is NOT graded:
    gateway-balanced's own ``card_min_w`` (158, its specimen's MEDIAN std
    width, cited at the preset level) floors every card at least 8px wider
    than this one specific 150-wide tile — an intentional per-preset choice
    unrelated to the vertical citation this test grades."""
    svg = _render("gateway-balanced")
    got = _card_geometry(svg, rx=13, name_cls="name", desc_cls="ndesc")
    want = _FIXTURE["dag-card"]
    _assert_close("dag-card (vertical)", got, want, ["name_baseline", "name_desc_gap", "glyph_inset_y"], VERTICAL_TOL)
    assert abs(got["box_h"] - want["box"][1]) <= VERTICAL_TOL, (got["box_h"], want["box"])


def test_state_machine_card_matches_the_sheet() -> None:
    """agent-task-lifecycle's own std card ('idle') — pp-state-machine-
    alt2.svg's own 120x62 rx13 tile, the state-machine family's node rhythm
    (pad_y 15.2 / label_desc_gap 6.6) — cross-validated identical (name
    baseline 27, name->desc gap 18) against pp-state-machine.svg's own
    'QUEUED' card, so either hand file grades the same citation. Width is
    not graded, same rationale as the dag-card test above."""
    svg = _render("agent-task-lifecycle")
    got = _card_geometry(svg, rx=13, name_cls="name", desc_cls="ndesc")
    want = _FIXTURE["state-machine-card"]
    _assert_close(
        "state-machine-card (vertical)", got, want, ["name_baseline", "name_desc_gap", "glyph_inset_y"], VERTICAL_TOL
    )
    assert abs(got["box_h"] - want["box"][1]) <= VERTICAL_TOL, (got["box_h"], want["box"])


# ── root-inheritance law ──────────────────────────────────────────────────
# Every DiagramNodeChassis's pad_y/label_desc_gap/desc_line_pitch/
# max_desc_lines (and every DiagramTopologyChassis's circle_r/hero_circle_r)
# resolves at PARADIGM LOAD (``ParadigmDiagramConfig._resolve_topology_
# rhythm``, a model_validator in core/paradigm.py) to the family's own
# citation if it has one, else the paradigm ROOT rhythm
# (``cfg.node``/``cfg.hero``/``cfg.circle_r``/``cfg.hero_circle_r``) — never
# a bare Pydantic class default. This is a structural guarantee, not a
# per-family opt-in: nothing in ``topologies`` can still be ``None`` by the
# time a solver reads it, so "families the sheet never demonstrates" is no
# longer a real state to test around — pipeline (the one family JOB1
# deliberately left uncited for ``label_desc_gap``) now inherits root
# exactly like every other uncited field on every other family.


def test_root_rhythm_is_the_sheets_own_law() -> None:
    """The paradigm root IS the sheet's own citation, not an invented
    number: node matches model-router's own satellite override (pad_y 22,
    label_desc_gap 7.5); hero matches fanout-horizontal's own router-hero
    citation (pad_y 25.5, label_desc_gap 8.5, desc_line_pitch 18); the
    circle radii match the bilateral canon (hw-diagram-alpha3-canon.html
    "Integration Hub v2": satellites r=30, hub r=44)."""
    from hyperweave.config.loader import load_paradigms

    cfg = load_paradigms()["primer"].diagram
    assert (cfg.node.pad_y, cfg.node.label_desc_gap) == (22.0, 7.5)
    assert (cfg.hero.pad_y, cfg.hero.label_desc_gap, cfg.hero.desc_line_pitch) == (25.5, 8.5, 18.0)
    assert (cfg.circle_r, cfg.hero_circle_r) == (30.0, 44.0)


def test_uncited_family_inherits_root_without_clipping() -> None:
    """A synthetic hero solved directly against the ``pipeline`` chassis —
    not a named preset, so a FUTURE preset-level override on any one
    pipeline story can't silently invalidate this: pipeline's own citation
    covers pad_y (16) and desc_line_pitch (19), but never label_desc_gap —
    it now resolves to the paradigm ROOT (8.5), never the retired bare
    paradigm-wide scalar (6.0) this fix kills. A two-line desc, long enough
    to push content-solve past the chassis's own 72 floor, proves the
    resolved value actually reaches the formula rather than the floor
    silently masking it (a short desc would content-solve under 72 either
    way, at 6.0 or 8.5 — no regression trap there)."""
    import pytest

    from hyperweave.compose.diagram.sizing import solve_card_box
    from hyperweave.config.loader import load_paradigms
    from hyperweave.core.diagram import DiagramNode

    cfg = load_paradigms()["primer"].diagram
    ch = cfg.topologies["pipeline"]
    pipeline_hero = ch.hero
    assert pipeline_hero.pad_y == 16.0  # pipeline's own citation, untouched by root
    assert pipeline_hero.label_desc_gap == cfg.hero.label_desc_gap == 8.5  # inherited from root

    # An explicit \n (the kit's own authoring convention for a 2-line hero
    # desc, e.g. stack's "artifact" node) rather than a long unbroken run:
    # _hero_ink_w measures a desc's WIDEST authored line pre-wrap, so a
    # single long run just grows the box wide enough to hold it on one
    # line instead of forcing a second — a different, unrelated mechanism
    # this test isn't the place to exercise.
    node = DiagramNode(label="Stage", desc="one two three four five\nsix seven eight nine ten")
    _w, h, lines = solve_card_box(node, pipeline_hero, ch, cfg, [], hero=True, min_w=pipeline_hero.w)
    assert len(lines) >= 2, "the desc must actually wrap to exercise desc_line_pitch/label_desc_gap"
    ar, dr = cfg.text_ascent_ratio, cfg.text_descent_ratio
    block = cfg.hero_name_voice.size * (ar + dr)
    block += (
        pipeline_hero.label_desc_gap
        + cfg.hero_desc_voice.size * (ar + dr)
        + (len(lines) - 1) * pipeline_hero.desc_line_pitch
    )
    want = block + 2 * pipeline_hero.pad_y
    assert h == pytest.approx(max(want, pipeline_hero.h))


def test_cited_family_is_never_overridden_by_root() -> None:
    """dag's own node citation (pad_y 14.7, label_desc_gap 7.6 — this
    family's own hand specimen genuinely differs from the sheet satellite)
    stays exactly what dag's own hand file measured: root only ever fills a
    gap, never clobbers a family's own number."""
    from hyperweave.config.loader import load_paradigms

    cfg = load_paradigms()["primer"].diagram
    dag_node = cfg.topologies["dag"].node
    assert (dag_node.pad_y, dag_node.label_desc_gap) == (14.7, 7.6)
    assert dag_node.pad_y != cfg.node.pad_y  # genuinely its own citation, not root's
