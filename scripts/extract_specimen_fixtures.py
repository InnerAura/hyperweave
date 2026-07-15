"""Extract specimen-parity fixtures from the diagrams-v3 prototypes.

Parses each prototype SVG into a neutral piece census + geometry targets and
writes ``tests/fixtures/specimens/*.json`` (deterministic: sorted keys, no
timestamps). Twin prototypes additionally yield per-face chroma tokens.

Run: ``uv run python scripts/extract_specimen_fixtures.py``
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tests.compose.parity.laws import has_gather_trunk_chip, measure_chip_stub_min, measure_port_max  # noqa: E402
from tests.compose.parity.pieces import (  # noqa: E402
    back_edge_routes,
    caption_text,
    card_rects,
    census,
    chip_homes,
    content_bbox,
    convergence_outer_chord_deg,
    edge_dress,
    edge_label_seats,
    hero_figures,
    hero_stack,
    hub_seats,
    lane_mark_kinds,
    payload_edge_pairs,
    plate_anchors,
    ring_arc_spans,
)
from tests.compose.parity.svgfacts import css_tokens, parse_svg  # noqa: E402

# The two authored source sets: the kit PROTOTYPES (one per topology
# story) and the later REFERENCES (beam motion + the conformance faces).
PROTOTYPES = REPO / "v04" / "alpha" / "v04a6" / "diagrams-v3"
REFERENCES = REPO / "v04" / "alpha" / "v04a6" / "diagrams-v4"
OUT = REPO / "tests" / "fixtures" / "specimens"

# Ground-truth set: one specimen per topology narrative, keyed by its clean
# topology-story name. The value still points at the authored specimen file
# under v04/ (which never ships) — that path is the honest provenance pointer.
GEOMETRY_SPECIMENS: dict[str, Path] = {
    "rag-pipeline": PROTOTYPES / "pp-pipeline.svg",
    "hub": PROTOTYPES / "pp-verb-ontology.svg",
    "axial": PROTOTYPES / "pp-axial.svg",
    "artifact-roundtrip": PROTOTYPES / "pp-roundtrip.svg",
    "reverse-etl": PROTOTYPES / "pp-integration.svg",
    "convergence": PROTOTYPES / "pp-convergence.svg",
    "convergence-arrivals": PROTOTYPES / "pp-convergence-flow.svg",
    "flywheel-orbit": PROTOTYPES / "pp-flywheel-v2.svg",
    "flywheel-flow": PROTOTYPES / "pp-flywheel-flow.svg",
    "stack": PROTOTYPES / "pp-stack-v2.svg",
    "comparison": PROTOTYPES / "pp-comparison-v2.svg",
    "cicd-machine": PROTOTYPES / "pp-state-machine.svg",
    "order-lifecycle": PROTOTYPES / "pp-state-machine-alt1.svg",
    "agent-task-lifecycle": PROTOTYPES / "pp-state-machine-alt2.svg",
    "obi-engine": PROTOTYPES / "pp-swimlanes.svg",
    "model-router": PROTOTYPES / "pp-router-flow-v2.svg",
    "router-descent": PROTOTYPES / "pp-router-down-v2.svg",
    "gateway": PROTOTYPES / "pp-mcp-gateway-v4.svg",
    "verb-reads": PROTOTYPES / "pp-radial.svg",
    "cicd-gate": PROTOTYPES / "dag-seq-tree" / "pp-dag-cicd-v4.svg",
    "observability-converge": PROTOTYPES / "dag-seq-tree" / "pp-dag-observability-v4.svg",
    "frontier-serving": PROTOTYPES / "dag-seq-tree" / "pp-dag-serving-v2.svg",
    "scatter-gather": PROTOTYPES / "dag-seq-tree" / "pp-dag-scatter-v4.svg",
    "kernel-bottleneck": PROTOTYPES / "dag-seq-tree" / "pp-dep-mesh-v2.svg",
    "model-gateway-tiers": PROTOTYPES / "dag-seq-tree" / "pp-gateway-refined.svg",
    "service-dependencies": PROTOTYPES / "dag-seq-tree" / "pp-service-deps.svg",
    "agent-runtime": PROTOTYPES / "dag-seq-tree" / "pp-agent-runtime.svg",
    "auth-sequence": PROTOTYPES / "dag-seq-tree" / "pp-sequence.svg",
    "tree": PROTOTYPES / "dag-seq-tree" / "pp-tree.svg",
    "dep-audit": PROTOTYPES / "dag-seq-tree" / "pp-tree-v2.svg",
    "mindmap": PROTOTYPES / "dag-seq-tree" / "pp-tree-radial.svg",
    "dep-audit-radial": PROTOTYPES / "dag-seq-tree" / "pp-tree-radial-v2.svg",
    "gateway-balanced": PROTOTYPES / "dag-seq-tree" / "pp-gateway-balanced.svg",
    # The reference set (one generation past the kit prototypes): beam
    # motion plus the conformance faces (circles, ring, hub relook,
    # typographic panel). Same fixture-name ≡ preset-name law; specimen
    # filename abbreviations live only in these source paths.
    "frontier-handoff": REFERENCES / "diagram-frontier-handoff-pp-v2.svg",
    "parity-beam": REFERENCES / "diagram-parity-beam-pp.svg",
    "flywheel-circles": REFERENCES / "diagram-flywheel-circles-pp.svg",
    "agent-loop-ring": REFERENCES / "diagram-agent-loop-ring-pp.svg",
    "config-radial-circles": REFERENCES / "diagram-data-hub-circles-pp.svg",
    "frame-engine-hub": REFERENCES / "diagram-frame-engine-hub-pp-v2.svg",
    "hub-panel-orchestrator": REFERENCES / "hub-panel-02-orchestrator.svg",
}

TWIN_DIR = PROTOTYPES / "primer-diagrams-v3"
TWIN_VARIANTS = ("porcelain", "carbon", "dusk", "cream", "noir", "space", "anvil", "petrol")

_TWIN_KEYS = {
    "--hw-sig": "sig",
    "--hw-sigt": "sigt",
    "--hw-s0": "s0",
    "--hw-s1": "s1",
    "--hw-s2": "s2",
    "--hw-stroke": "stroke",
    "--hw-ink": "ink",
    "--hw-inkhi": "inkhi",
    "--hw-ink2": "ink2",
    "--hw-conn": "conn",
}


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def extract_geometry(name: str, path: Path) -> dict[str, object]:
    facts = parse_svg(path.read_text())
    # Topology ground truth the hand file already declares: the census
    # counted the wrong-target retry as green for months because nothing
    # read this field on either side.
    _spec = (facts.payload or {}).get("spec") or {}
    _back = _spec.get("back_edge")
    cards = card_rects(facts)
    heroes_rect = [r for r in cards if "hero" in r.cls]
    std = [r for r in cards if "hero" not in r.cls]
    stats: dict[str, object] = {}
    if _back:
        stats["back_edge"] = _back
    if std:
        stats["std_w_med"] = round(_median([r.w for r in std]), 2)
        stats["std_h_med"] = round(_median([r.h for r in std]), 2)
    # hero_w/hero_h read every anatomy (hero_figures): a circle hero's box
    # is its bounding square, so its diameter lands in these same two keys.
    # hero_area_ratio stays rect-vs-rect only — a circle hero has no "std
    # card" to ratio against (its siblings are std CIRCLES, a different
    # census), so the ratio law is legitimately n/a there, not populated.
    hero_figs = hero_figures(facts)
    if hero_figs:
        stats["hero_w"] = round(hero_figs[0].w, 2)
        stats["hero_h"] = round(hero_figs[0].h, 2)
        if heroes_rect and std:
            ratio = (heroes_rect[0].w * heroes_rect[0].h) / max(
                _median([r.w for r in std]) * _median([r.h for r in std]), 1.0
            )
            stats["hero_area_ratio"] = round(ratio, 3)
    bbox = content_bbox(facts)
    occupancy = None
    if bbox and facts.vb_w and facts.vb_h:
        occupancy = round(((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / (facts.vb_w * facts.vb_h), 3)
    stub_min = measure_chip_stub_min(facts)
    result: dict[str, object] = {
        "source": str(path.relative_to(REPO)),
        "viewbox": list(facts.viewbox),
        "width": facts.width,
        "height": facts.height,
        "aspect": round(facts.vb_w / facts.vb_h, 3) if facts.vb_h else None,
        "occupancy": occupancy,
        "cards": stats,
        "census": census(facts).as_dict(),
        # The specimen's own craft envelope: renders are held to it.
        "port_tolerance": round(measure_port_max(facts) + 0.5, 1),
        "chip_stub_min": round(stub_min, 1) if stub_min is not None else None,
    }
    # Plate bands: the four vertical anchors (zone baseline, content ink
    # top/bottom, caption baseline) plus the caption-to-edge pad — the chrome
    # constants were calibrated from one specimen family; these pins hold
    # every family to its own hand file's air.
    anchors = plate_anchors(facts)
    plate: dict[str, object] = {k: v for k, v in anchors.items() if v is not None}
    if anchors.get("caption_y") is not None and facts.vb_h:
        plate["caption_pad"] = round(facts.vb_h - float(anchors["caption_y"]), 2)  # type: ignore[arg-type]
    if plate:
        result["plate"] = plate
    # Caption sentence, verbatim (None pins ABSENCE — obi renders captionless).
    result["caption_text"] = caption_text(facts)
    # Full declared relation set (payload dialects: edges/transitions).
    edge_set = payload_edge_pairs(facts)
    if edge_set:
        result["edge_set"] = edge_set
    # Chip homes: in-card row vs on-wire, plus the worst on-wire float band.
    # A ratified census amendment that folds chips away (kernel-bottleneck's
    # objecthood fold, chips 1→0) outranks the raw count — the hand file
    # still draws its pill; the render lawfully carries none.
    _existing_amend = {}
    _existing_fixture = OUT / f"{name}.json"
    if _existing_fixture.exists():
        _existing_amend = json.loads(_existing_fixture.read_text()).get("census_amendments") or {}
    homes = chip_homes(facts)
    if homes and "chips" not in _existing_amend:
        result["chip_homes"] = homes
    # Hub satellite seats: polar seat of each satellite NAME about the hero.
    seats = hub_seats(facts)
    if seats:
        result["hub_seats"] = seats
    # Hero stack composition: the rows the crown contains, per hand file.
    stack = hero_stack(facts)
    if stack:
        result["hero_stack"] = stack
    # Ring arc spans: the sorted angular spans of the medallion arcs.
    arcs = ring_arc_spans(facts)
    if arcs:
        result["ring_arcs"] = arcs
    # Lanes category-by-MARK pin (obi-engine): per-card mark kind, position-
    # matched. Only specimens that carry marks opt in; every other fixture
    # omits the field and the parity law is n/a there.
    marks = lane_mark_kinds(facts)
    if any(marks):
        result["lane_marks"] = marks
    # Gather-trunk chip idiom (dag-scatter): only specimens that seat a chip on
    # a join trunk opt into the mouth-hug position law; every other fixture omits
    # the flag and the law is n/a there.
    if has_gather_trunk_chip(facts):
        result["gather_trunk_chip"] = True
    # Convergence approach-angle commitment (F1): the outer fan-in spoke's
    # chord to the shared gather knot. Convergence-topology only — a DAG's
    # departure knot (model-gateway-tiers' own mouth ring) is a different
    # idiom with no citation calibrated for this tolerance.
    if str(facts.root_attrs.get("data-hw-topology", "")) == "convergence":
        angle = convergence_outer_chord_deg(facts)
        if angle is not None:
            result["convergence_outer_angle_deg"] = round(angle, 1)
    # State-machine return edges (retry/throw/revise): exit side, chord bow,
    # clearance to third cards, arrival tangent angle, and (where a genuine
    # interior dip exists) the belly's x — only specimens carrying a curved,
    # non-self-loop connector opt in — every other fixture omits the key.
    routes = back_edge_routes(facts)
    if routes:
        result["back_edge_routes"] = routes
    dress = edge_dress(facts)
    if dress:
        result["edge_dress"] = dress
    label_seats = edge_label_seats(facts)
    if label_seats:
        result["edge_label_seats"] = label_seats
    # Beam recipe (the beam reference specimens): shared clock + the staged window
    # set — the structural pin law_beam grades; coordinate-free on purpose.
    if facts.beam_gradients:
        windows = sorted({w for g in facts.beam_gradients if (w := g.window()) is not None})
        result["beam"] = {
            "clock": facts.beam_gradients[0].dur,
            "windows": [list(w) for w in windows],
        }
    # HAND-AUTHORED annotations survive regeneration: census_amendments and
    # dims_superseded are owner-triaged supersession records (standing law #3),
    # written into the fixture after extraction — a re-run must never silently
    # clobber them (it did once; four boards went red).
    existing_path = OUT / f"{name}.json"
    if existing_path.exists():
        existing = json.loads(existing_path.read_text())
        if "census_amendments" in existing:
            result["census_amendments"] = existing["census_amendments"]
        if "plate_amendment" in existing:
            result["plate_amendment"] = existing["plate_amendment"]
        # hub_seats_superseded: same survival rule, for a satellite seat
        # angle/dist that no longer reproduces without un-verticalizing a
        # connector no specimen draws off-spine (see axial.py's solve_axial).
        if "hub_seats_superseded" in existing:
            result["hub_seats_superseded"] = existing["hub_seats_superseded"]
        # port_tolerance widens the ports law for terminal-ring presets (the
        # ring inflates the boundary the specimen's tolerance never knew) —
        # an owner-triaged amendment, same survival rule as the others.
        for key in ("port_tolerance", "port_tolerance_note"):
            if key in existing:
                result[key] = existing[key]
        prior_cards = existing.get("cards") or {}
        if "dims_superseded" in prior_cards and isinstance(result.get("cards"), dict):
            result["cards"]["dims_superseded"] = prior_cards["dims_superseded"]  # type: ignore[index]
    return result


def extract_twin(variant: str, path: Path) -> dict[str, object]:
    facts = parse_svg(path.read_text())
    base, dark = css_tokens(facts.style_text)

    def face(tokens: dict[str, str]) -> dict[str, str]:
        return {key: tokens[var] for var, key in _TWIN_KEYS.items() if var in tokens}

    return {
        "source": str(path.relative_to(REPO)),
        "variant": variant,
        "faces": {"light": face(base), "dark": face(dark)},
    }


# ── The diagram language law (primer_diagram_language.html) ─────────────────
# The total aesthetic law for primer diagrams: per variant x face, every slot
# token, text/shape class, filter primitive, marker, gradient and animation
# parameter. Extracted to tests/fixtures/primer_diagram_language.json — the committed
# fixture tests/compose/test_primer_diagram_language.py validates emitted CSS against
# (v04/ never ships, so tests read the fixture, not the html).

_LANGUAGE_HTML = Path("v04/alpha/v04a6/diagrams-v3/primer_diagram_language.html")


def _classes(svg: str) -> dict[str, dict[str, str]]:
    """Every ``.prefix-NAME { ... }`` rule, keyed by the short class name."""
    out: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"\.[a-z0-9]+-[a-z]+-([a-z0-9]+)(?:\s*,[^{]*)?\s*\{([^}]*)\}", svg):
        name, body = m.group(1), m.group(2)
        props = dict(
            (k.strip(), " ".join(v.split())) for k, v in (pair.split(":", 1) for pair in body.split(";") if ":" in pair)
        )
        out.setdefault(name, props)
    return out


def _filters(svg: str) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for m in re.finditer(r'<filter id="[^"]*-(lift|seat)"[^>]*>(.*?)</filter>', svg, re.S):
        prims = []
        for p in re.finditer(r"<fe([A-Za-z]+)([^/>]*)/?>", m.group(2)):
            attrs = dict(re.findall(r'([a-zA-Z-]+)="([^"]+)"', p.group(2)))
            prims.append({"prim": p.group(1), **attrs})
        out[m.group(1)] = prims
    return out


def _markers(svg: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for m in re.finditer(r'<marker id="[^"]*-([a-z]+)"([^>]*)>(.*?)</marker>', svg, re.S):
        attrs = dict(re.findall(r'([a-zA-Z-]+)="([^"]+)"', m.group(2)))
        path = re.search(r'd="([^"]+)"', m.group(3))
        out[m.group(1)] = {**attrs, "path": path.group(1) if path else ""}
    return out


def _gradients(svg: str) -> dict[str, list[tuple[str, str]]]:
    """cf/es/hf/hc gradient stops as (offset, color) — a stop may carry its
    color inline OR via a stop class (``.…-cf1 { stop-color: var(--hw-card-hi) }``),
    resolved here so the fixture is self-contained."""
    stop_cls = dict(re.findall(r"\.[a-z0-9]+-[a-z]+-([a-z]+\d)\s*\{\s*stop-color:\s*([^;}]+)", svg))
    out: dict[str, list[tuple[str, str]]] = {}
    for gid, gbody in re.findall(
        r'<linearGradient[^>]*id="[^"]*-(cf|es|hf|hc)"[^>]*>(.*?)</linearGradient>', svg, re.S
    ):
        stops: list[tuple[str, str]] = []
        for sm in re.finditer(r'<stop\s+offset="([^"]+)"([^>]*)>', gbody):
            attrs = sm.group(2)
            color = re.search(r'stop-color="([^"]+)"', attrs)
            cls = re.search(r'class="[^"]*-([a-z]+\d)"', attrs)
            op = re.search(r'stop-opacity="([^"]+)"', attrs)
            val = color.group(1) if color else stop_cls.get(cls.group(1) if cls else "", "")
            if op:
                val = f"{val} @{op.group(1)}"
            stops.append((sm.group(1), val.strip()))
        out[gid] = stops
    return out


def _anim(svg: str) -> dict[str, str]:
    out: dict[str, str] = {}
    kf = re.search(r"@keyframes [a-z0-9-]+m \{\s*to \{\s*stroke-dashoffset: ([-\d]+)", svg)
    if kf:
        out["march_offset"] = kf.group(1)
    dur = re.search(r"animation: [a-z0-9-]+m ([\d.]+s)", svg)
    if dur:
        out["march_dur"] = dur.group(1)
    part = re.search(r'<animateMotion dur="([\d.]+s)"', svg)
    if part:
        out["particle_dur"] = part.group(1)
    ramp = re.search(r'values="0;1;1;0"\s+keyTimes="([^"]+)"', svg)
    if ramp:
        out["particle_keytimes"] = ramp.group(1)
    return out


def _text_xy(chunk: str, cls_suffix: str) -> list[tuple[float, float]]:
    """Every ``<text x="..." y="..." ... class="{prefix}-{cls_suffix}">`` in
    ``chunk``, in document order. The x/y attribute pair may or may not wrap
    onto its own line (the html's line-wrapped prettifier is inconsistent),
    so the newline between them is optional. Both coordinates allow a
    leading sign — the language sheet's own genome cards never go negative,
    but the dag/state-machine hand files' local coordinate systems straddle
    y=0 (a standard row's text can land at e.g. y="-4.1")."""
    return [
        (float(x), float(y))
        for x, y in re.findall(
            rf'<text x="(-?[\d.]+)"\s*\n?\s*y="(-?[\d.]+)"[^>]*class="[a-z0-9-]+-{cls_suffix}"', chunk
        )
    ]


def _card_from_source(
    text: str, *, rect_pat: str, glyph_pat: str, name_cls: str, desc_cls: str, min_span: int = 400
) -> dict[str, object]:
    """The same slot-rhythm extraction as ``_slot_geometry``'s ``card()``/
    ``window()``, generalized to an arbitrary specimen SVG's raw text rather
    than the ``primer_diagram_language.html`` sheet — the dag/state-machine
    card rows cite their OWN hand file (dag-seq-tree/pp-gateway-balanced.svg,
    pp-state-machine-alt2.svg), never the language sheet, so this reads a
    standalone document instead of windowing within one big multi-genome
    page. ``rect_pat`` must capture x/y as groups 1/2."""
    m = re.search(rect_pat, text, re.S)
    if not m:
        raise ValueError(f"slot-geometry anchor not found: {rect_pat!r}")
    nxt = re.search(r'<rect class="[a-z0-9-]+-(?:card|hero)"', text[m.start() + min_span :])
    end = m.start() + min_span + nxt.start() if nxt else m.start() + 3500
    chunk = text[m.start() : end]
    rx, ry = float(m.group(1)), float(m.group(2))
    glyph = re.search(glyph_pat, chunk)
    assert glyph, glyph_pat
    gx, gy = float(glyph.group(1)), float(glyph.group(2))
    names = _text_xy(chunk, name_cls)
    descs = _text_xy(chunk, desc_cls)
    assert names, f"no .{name_cls} text found for {rect_pat!r}"
    name_x, name_y = names[0]
    out: dict[str, object] = {
        "glyph_inset": [round(gx - rx, 2), round(gy - ry, 2)],
        "text_lead": round(name_x - rx, 2),
        "name_baseline": round(name_y - ry, 2),
    }
    if descs:
        out["name_desc_gap"] = round(descs[0][1] - name_y, 2)
    if len(descs) > 1:
        out["desc_pitch"] = round(descs[1][1] - descs[0][1], 2)
    return out


def _dag_card_geometry() -> dict[str, object]:
    """dag-card: dag-seq-tree/pp-gateway-balanced.svg's own std card (the
    'requests' tile, 150x62 rx13, uniquely width-matched — the file's other
    std cards run 164/152) — the dag family's card+glyph label-row rhythm,
    cited on ``diagram.topologies.dag.node`` in primer.yaml."""
    path = PROTOTYPES / "dag-seq-tree" / "pp-gateway-balanced.svg"
    text = path.read_text()
    card = _card_from_source(
        text,
        # y runs negative in this specimen's local coordinate system (the
        # standard row cards straddle y=0) — every numeric capture allows a
        # leading sign.
        rect_pat=r'<rect class="gw-card" x="(-?[\d.]+)" y="(-?[\d.]+)" width="150\.0"',
        glyph_pat=r'<g class="gw-gi" transform="translate\((-?[\d.]+),(-?[\d.]+)\)">',
        name_cls="name",
        desc_cls="sub",
        # The true next-rect (the hero) sits 317 chars past this card's own
        # start — a tight span so the window never bleeds a sibling card's
        # text in (min_span=400, the language-sheet default, overshoots it).
        min_span=150,
    )
    card["source"] = str(path.relative_to(REPO))
    card["box"] = [150.0, 62.0]
    card["rx"] = 13
    return card


def _state_machine_card_geometry() -> dict[str, object]:
    """state-machine-card: pp-state-machine-alt2.svg's own std card (the
    'idle' tile, 120x62 rx13, uniquely width-matched — the file's other std
    cards run 140/150/122) — cross-validated identical (name baseline 27,
    name->desc gap 18) against pp-state-machine.svg's own 'QUEUED' card, so
    either hand file grades the same citation on
    ``diagram.topologies.state-machine.node``."""
    path = PROTOTYPES / "pp-state-machine-alt2.svg"
    text = path.read_text()
    card = _card_from_source(
        text,
        rect_pat=r'<rect class="a2-card" x="(-?[\d.]+)" y="(-?[\d.]+)" width="120"',
        glyph_pat=r'<g class="a2-gi" transform="translate\((-?[\d.]+),(-?[\d.]+)\)">',
        name_cls="name",
        desc_cls="sub",
        # The next card (all four std cards share this SAME "a2-sub" class,
        # unlike gateway-balanced's distinct hero suffix) sits 313 chars
        # past this card's own start — a tight span so the window never
        # picks up a sibling card's desc line as a phantom second desc.
        min_span=150,
    )
    card["source"] = str(path.relative_to(REPO))
    card["box"] = [120.0, 62.0]
    card["rx"] = 13
    return card


def _slot_geometry(t: str) -> dict[str, object]:
    """The card slot-rhythm law (JOB1 — glyph inset, text lead, name
    baseline, name->desc gap, desc pitch) for the sheet's two hero
    families and their satellite: geometry is genome/face-INVARIANT (every
    one of the sixteen faces renders the identical coordinates, only the
    paint differs), so this extracts ONCE from the first occurrence of each
    card rather than repeating per (genome, face) like ``extract_diagram_
    language``'s chromatic sections. A card's identity mark can be a WIDE
    inline glyph path (the brand logos run past 1500 chars) between its
    ``<rect>`` and its ``<text>`` runs, so each card is windowed generously
    (3500 chars) rather than assumed adjacent."""

    def window(pattern: str, min_span: int = 400) -> str:
        """From the anchor to the START of the next card/hero ``<rect>`` (or
        ``min_span`` chars, whichever is longer) — bounds a card to its OWN
        content so a following sibling's text never leaks in. A fixed span
        alone is unsafe both ways: too short truncates a card whose glyph is
        a long inline brand path (Claude's logo runs past 1500 chars before
        its own text starts), too long spills into the NEXT stacked
        satellite's name/desc (the fanout column's 118px pitch)."""
        m = re.search(pattern, t, re.S)
        if not m:
            raise ValueError(f"slot-geometry anchor not found: {pattern!r}")
        nxt = re.search(r'<rect class="[a-z0-9-]+-(?:card|hero)"', t[m.start() + min_span :])
        end = m.start() + min_span + nxt.start() if nxt else m.start() + 3500
        return t[m.start() : end]

    def card(w: str, rect_pat: str, glyph_pat: str, name_cls: str, desc_cls: str) -> dict[str, object]:
        rect = re.search(rect_pat, w)
        glyph = re.search(glyph_pat, w)
        assert rect and glyph, (rect_pat, glyph_pat)
        rx, ry = float(rect.group(1)), float(rect.group(2))
        gx, gy = float(glyph.group(1)), float(glyph.group(2))
        names = _text_xy(w, name_cls)
        descs = _text_xy(w, desc_cls)
        name_x, name_y = names[0]
        out: dict[str, object] = {
            "glyph_inset": [round(gx - rx, 2), round(gy - ry, 2)],
            "text_lead": round(name_x - rx, 2),
            "name_baseline": round(name_y - ry, 2),
        }
        if descs:
            out["name_desc_gap"] = round(descs[0][1] - name_y, 2)
        if len(descs) > 1:
            out["desc_pitch"] = round(descs[1][1] - descs[0][1], 2)
        return out

    fanout_hero_w = window(r'<rect class="[a-z0-9-]+-hero" x="[\d.]+" y="[\d.]+" width="206\.0"')
    fanout_hero = card(
        fanout_hero_w,
        r'x="([\d.]+)" y="([\d.]+)" width="206\.0"\s*\n?\s*height="104" rx="16"',
        r'<g class="[a-z0-9-]+-gia" transform="translate\(([\d.]+),([\d.]+)\)">',
        "hname",
        "hsub",
    )
    fanout_hero["box"] = [206.0, 104.0]
    fanout_hero["rx"] = 16
    fanout_hero["glyph_size"] = 24  # unscaled — the router hero keeps the standard mark, never the 32 nucleus glyph

    satellite_w = window(r'<rect class="[a-z0-9-]+-card" x="[\d.]+" y="[\d.]+" width="165\.0"')
    satellite = card(
        satellite_w,
        r'x="([\d.]+)" y="([\d.]+)" width="165\.0"\s*\n?\s*height="76" rx="13"',
        r'<g transform="translate\(([\d.]+),([\d.]+)\) scale\(1\.00000\)">',
        "name",
        "sub",
    )
    satellite["box"] = [165.0, 76.0]
    satellite["rx"] = 13
    satellite["glyph_size"] = 24

    axial_w = window(r'<rect class="[a-z0-9-]+-hero" x="[\d.]+" y="[\d.]+" width="232"')
    axial = card(
        axial_w,
        r'x="([\d.]+)" y="([\d.]+)" width="232"\s*\n?\s*height="112" rx="16"',
        r'<g transform="translate\(([\d.]+),([\d.]+)\) scale\(1\.3333\)">',
        "hname",
        "hsub",
    )
    axial["box"] = [232.0, 112.0]
    axial["rx"] = 16
    axial["glyph_size"] = 32  # scale(1.3333) on a 24-unit icon — the nucleus-only enlarged mark

    return {
        "source": str(_LANGUAGE_HTML),
        "fanout-hero": fanout_hero,
        "fanout-satellite": satellite,
        "axial-nucleus": axial,
    }


def extract_diagram_language() -> dict[str, object]:
    t = _LANGUAGE_HTML.read_text()
    h2s = [(m.start(), m.group(1)) for m in re.finditer(r"<h2[^>]*>([^<]+)</h2>", t)]
    law: dict[str, dict[str, dict[str, object]]] = {}
    for k, (pos, name) in enumerate(h2s):
        end = h2s[k + 1][0] if k + 1 < len(h2s) else len(t)
        for s in re.findall(r"(<svg.*?</svg>)", t[pos:end], re.S):
            did = re.search(r'data-hw-id="([^"]+)"', s)
            face = "dark" if "-dark" in (did.group(1) if did else "") else "light"
            entry = law.setdefault(name, {}).setdefault(face, {})
            entry.setdefault("vars", dict(re.findall(r"(--hw-[a-z-]+):\s*([^;]+);", s)))
            entry.setdefault("classes", {}).update(_classes(s))
            entry.setdefault("filters", {}).update(_filters(s))
            entry.setdefault("markers", {}).update(_markers(s))
            entry.setdefault("gradients", {}).update(_gradients(s))
            entry.setdefault("anim", {}).update(_anim(s))
    out: dict[str, object] = dict(law)
    slot_geometry = _slot_geometry(t)
    # dag-card/state-machine-card: their OWN hand files (dag-seq-tree/
    # pp-gateway-balanced.svg, pp-state-machine-alt2.svg), not the language
    # sheet — the sheet demonstrates only the fanout/axial families.
    slot_geometry["dag-card"] = _dag_card_geometry()
    slot_geometry["state-machine-card"] = _state_machine_card_geometry()
    out["slot_geometry"] = slot_geometry
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for name, path in sorted(GEOMETRY_SPECIMENS.items()):
        fixture = extract_geometry(name, path)
        out = OUT / f"{name}.json"
        out.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n")
        written.append(out.name)
    for variant in TWIN_VARIANTS:
        path = TWIN_DIR / f"verb-algebra-primer-{variant}.svg"
        fixture = extract_twin(variant, path)
        out = OUT / f"twin-{variant}.json"
        out.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n")
        written.append(out.name)
    print(f"wrote {len(written)} fixtures to {OUT.relative_to(REPO)}")


def _write_language_fixture() -> None:
    out = Path("tests/fixtures/primer_diagram_language.json")
    out.write_text(json.dumps(extract_diagram_language(), indent=1) + "\n")
    print(f"{out}: diagram language law re-extracted")


if __name__ == "__main__":
    main()
    _write_language_fixture()
