"""The kit explainer — a specimen plate in HTML.

The genre is the kit sheet, not a table of contents: every piece is DRAWN at
true size from live engine constants and live genome hexes; the combinatorics
are shown with real renders (the same story bent through orientations, node
faces, and sizes); the laws sit next to the geometry they govern.

Two disciplines, both load-bearing:

* LIVE VALUES — every number and hex is imported from the engine/genome at
  build time. A hand-copied "+17" in documentation is the same bug class the
  consolidation pass deleted.
* REAL EXHIBITS — every full diagram is composed by the engine at build time;
  piece samples are drawn from the same constants the engine renders with
  (chip pads, chevron geometry via route.arrow_d, dash clocks, chassis dims).

Output: outputs/diagrams/kit-explainer.html (outputs/ is gitignored — this
generator is the committed deliverable).
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from importlib import resources  # noqa: E402

from hyperweave.compose.bundled_specs import resolve_bundled_spec  # noqa: E402
from hyperweave.compose.diagram.route import arrow_d  # noqa: E402
from hyperweave.compose.diagram.sizing import (  # noqa: E402
    CHIP_GAP,
    CHIP_H,
    CHIP_PAD_X,
    CHIP_RX,
    DOT_MARK_W,
    GLYPH_MARK_W,
    HERO_GLYPH_MARK_W,
)
from hyperweave.compose.diagram.solver import registered_slugs  # noqa: E402
from hyperweave.compose.engine import compose  # noqa: E402
from hyperweave.config.loader import load_diagram_config, load_paradigms  # noqa: E402
from hyperweave.core.diagram import Topology  # noqa: E402
from hyperweave.core.models import ComposeSpec  # noqa: E402

OUT = REPO / "outputs" / "diagrams"

GENOME = json.loads(resources.files("hyperweave.data.genomes").joinpath("primer.json").read_text())
PO = GENOME["variant_overrides"]["porcelain"]
CARD = PO["surface_1"]
STROKE = PO["stroke"]
INK = PO["ink"]
DIM = PO["ink_secondary"]
ACCENT = PO["accent"]
CONN = GENOME.get("diagram_conn_muted", PO["diagram_conn_muted"])
CHIPBG = PO["surface_0"]

ENGINE = load_diagram_config()
ANN = ENGINE.get("annotate") or {}
CN = ENGINE.get("connector") or {}
BEAM = ENGINE.get("beam") or {}
HUBCFG = ENGINE.get("hub") or {}
CAPS = ENGINE.get("caps") or {}
LEGAL = ENGINE.get("orientation_legality") or {}
PRIMER = load_paradigms()["primer"].diagram
NCH = PRIMER.topologies["pipeline"].node
PAD_X = NCH.pad_x
INK_GAP = NCH.label_gap - DOT_MARK_W / 2
TEXT_X = PAD_X + GLYPH_MARK_W + INK_GAP
MARKER = float(CN.get("marker_size", 8))
DASH = str(CN.get("dash", "2 7"))
DRIFT = str(CN.get("ants_dur", "7s"))


def _render(spec: str | dict, *, variant: str = "porcelain", face: str = "light", motion: str = "static") -> str:
    d = resolve_bundled_spec("diagram", spec).value if isinstance(spec, str) else spec
    return compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant=variant,
            ground="bare" if face == "light" else "opaque",
            palette="fixed",
            surface_face=face,
            motion=motion,
            diagram=d,
        )
    ).svg


# ── drawn piece samples (live constants + live hexes; kit-sheet discipline) ──


def _chev(tx: float, ty: float, ux: float, uy: float, fill: str = CONN) -> str:
    return f'<path d="{arrow_d((tx, ty), (ux, uy), size=MARKER + 3, half=0.45)}" fill="{fill}"/>'


def _svg(w: float, h: float, body: str) -> str:
    return (
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'style="overflow:visible" xmlns="http://www.w3.org/2000/svg">{body}</svg>'
    )


def _glyph_stub(x: float, y: float, size: float, stroke: str = INK) -> str:
    """A document-ish ink glyph drawn AT the live slot size."""
    s = size / 24.0
    return (
        f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{stroke}" '
        f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        f'<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/></g>'
    )


def px_card(*, hero: bool = False) -> str:
    w, h = (232, 112) if hero else (58 + 96 + 14, 60)
    mark = HERO_GLYPH_MARK_W if hero else GLYPH_MARK_W
    gx = PAD_X
    tx = TEXT_X if not hero else PAD_X + mark + INK_GAP
    name_y, sub_y = (40, 64) if hero else (25, 44)
    stroke = ACCENT if hero else STROKE
    name_font = "700 17px Inter" if hero else "600 15px Inter"
    return _svg(
        w + 8,
        h + 8,
        f'<rect x="4" y="4" width="{w}" height="{h}" rx="{16 if hero else 13}" fill="{CARD}" '
        f'stroke="{stroke}" stroke-width="{1.5 if hero else 1}"/>'
        + _glyph_stub(4 + gx, 4 + (h - mark) / 2 if hero else 4 + 18, mark, ACCENT if hero else INK)
        + f'<text x="{4 + tx}" y="{4 + name_y}" style="font:{name_font}" fill="{INK}">'
        + ("the crown" if hero else "node name")
        + "</text>"
        + f'<text x="{4 + tx}" y="{4 + sub_y}" style="font:400 11px JetBrains Mono" fill="{ACCENT if hero else DIM}">'
        + ("privileged sub" if hero else "mono subtitle")
        + "</text>"
        + (
            f'<text x="{4 + tx}" y="{4 + 83}" style="font:400 11px JetBrains Mono" fill="{ACCENT}">second line</text>'
            if hero
            else ""
        ),
    )


def px_circle() -> str:
    r = 44
    return _svg(
        2 * r + 8,
        2 * r + 56,
        f'<circle cx="{r + 4}" cy="{r + 4}" r="{r}" fill="{CARD}" stroke="{STROKE}"/>'
        + _glyph_stub(r + 4 - 12, r + 4 - 12, 24)
        + f'<text x="{r + 4}" y="{2 * r + 26}" text-anchor="middle" style="font:600 15px Inter" fill="{INK}">'
        "1. Stage</text>"
        + f'<text x="{r + 4}" y="{2 * r + 44}" text-anchor="middle" style="font:400 11px JetBrains Mono" fill="{DIM}">'
        "name Inter · desc mono</text>",
    )


def px_text_block() -> str:
    return _svg(
        200,
        66,
        f'<text x="4" y="18" style="font:600 15px Inter" fill="{INK}">researcher</text>'
        f'<text x="4" y="38" style="font:400 11px JetBrains Mono" fill="{DIM}">gathers sources, extracts</text>'
        f'<text x="4" y="54" style="font:400 11px JetBrains Mono" fill="{DIM}">claims, returns cited notes</text>',
    )


def px_chip_row() -> str:
    xs, parts = 4.0, []
    for label, wpx in (("extract", 66), ("verify", 60), ("diff", 46)):
        parts.append(
            f'<rect x="{xs}" y="4" width="{wpx}" height="{CHIP_H}" rx="{CHIP_RX}" fill="{CHIPBG}" stroke="{STROKE}"/>'
        )
        parts.append(
            f'<text x="{xs + CHIP_PAD_X}" y="{4 + 17}" style="font:400 11px JetBrains Mono" fill="{DIM}">{label}</text>'
        )
        xs += wpx + CHIP_GAP
    return _svg(xs, CHIP_H + 8, "".join(parts))


def px_edge_chip() -> str:
    w, cw = 320, 82
    cx = (w - cw) / 2
    return _svg(
        w,
        40,
        f'<line x1="4" y1="20" x2="{w - 4}" y2="20" stroke="{CONN}" stroke-width="1.5"/>'
        f'<rect x="{cx}" y="{20 - CHIP_H / 2}" width="{cw}" height="{CHIP_H}" rx="{CHIP_RX}" '
        f'fill="{CHIPBG}" stroke="{STROKE}"/>'
        f'<text x="{cx + CHIP_PAD_X}" y="{20 + 4.5}" style="font:400 11px JetBrains Mono" fill="{DIM}">compose</text>',
    )


def px_micro_label() -> str:
    return _svg(
        220,
        44,
        f'<line x1="4" y1="30" x2="216" y2="30" stroke="{CONN}" stroke-width="1.5"/>'
        + _chev(216, 30, 1, 0)
        + f'<text x="110" y="16" text-anchor="middle" style="font:400 10px JetBrains Mono;letter-spacing:.08em" '
        f'fill="{DIM}">verb</text>',
    )


def px_edge(kind: str) -> str:
    y, w = 16, 240
    if kind == "solid":
        body = f'<line x1="4" y1="{y}" x2="{w - 10}" y2="{y}" stroke="{CONN}" stroke-width="1.5"/>' + _chev(
            w - 4, y, 1, 0
        )
    elif kind == "drift":
        body = (
            f'<line x1="4" y1="{y}" x2="{w - 8}" y2="{y}" stroke="{CONN}" stroke-width="1.5" '
            f'stroke-dasharray="{DASH}" stroke-linecap="round">'
            f'<animate attributeName="stroke-dashoffset" to="-108" dur="{DRIFT}" repeatCount="indefinite"/></line>'
            f'<circle cx="{w - 4}" cy="{y}" r="2.3" fill="{CONN}"/>'
        )
    elif kind == "accent":
        body = f'<line x1="4" y1="{y}" x2="{w - 10}" y2="{y}" stroke="{ACCENT}" stroke-width="1.5"/>' + _chev(
            w - 4, y, 1, 0, ACCENT
        )
    elif kind == "skip":
        body = (
            f'<path d="M 4,{y + 10} C 60,{y - 14} {w - 60},{y - 14} {w - 8},{y + 8}" fill="none" '
            f'stroke="{CONN}" stroke-width="1.5" stroke-dasharray="{DASH}" stroke-linecap="round">'
            f'<animate attributeName="stroke-dashoffset" to="-108" dur="9s" repeatCount="indefinite"/></path>'
            f'<circle cx="{w - 6}" cy="{y + 9}" r="2.3" fill="{CONN}"/>'
        )
    elif kind == "particle":
        body = (
            f'<line x1="4" y1="{y}" x2="{w - 4}" y2="{y}" stroke="{CONN}" stroke-width="1.5"/>'
            f'<circle r="3" fill="{ACCENT}" opacity="0"><animateMotion dur="3.2s" repeatCount="indefinite" '
            f'path="M 4,{y} L {w - 4},{y}"/>'
            f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.14;.82;1" '
            f'dur="3.2s" repeatCount="indefinite"/></circle>'
        )
    else:  # beam — glass conduit + gradient window pair, the real recipe colors
        ba, bb = str(BEAM.get("color_a", "#60A5FA")), str(BEAM.get("color_b", "#A78BFA"))
        body = (
            f'<line x1="4" y1="{y}" x2="{w - 4}" y2="{y}" stroke="{INK}" stroke-width="6" opacity="0.07"/>'
            f'<line x1="4" y1="{y}" x2="{w - 4}" y2="{y}" stroke="{CONN}" stroke-width="1.5" opacity="0.26"/>'
            f'<linearGradient id="kxb" gradientUnits="userSpaceOnUse" x1="4" y1="{y}" x2="124" y2="{y}">'
            f'<stop offset="0" stop-color="{ba}" stop-opacity="0"/>'
            f'<stop offset="0.5" stop-color="{ba}" stop-opacity="1"/>'
            f'<stop offset="1" stop-color="{bb}" stop-opacity="0"/>'
            f'<animateTransform attributeName="gradientTransform" type="translate" values="0 0;{w} 0;0 0" '
            f'dur="{BEAM.get("dur", 5.236)}s" repeatCount="indefinite"/></linearGradient>'
            f'<line x1="4" y1="{y}" x2="{w - 4}" y2="{y}" stroke="url(#kxb)" stroke-width="2"/>'
        )
    return _svg(w, 32, body)


def px_knot() -> str:
    return _svg(
        220,
        90,
        f'<path d="M 20,45 C 100,45 100,18 200,18" fill="none" stroke="{ACCENT}" stroke-width="1.5"/>'
        f'<path d="M 20,45 C 100,45 100,72 200,72" fill="none" stroke="{ACCENT}" stroke-width="1.5"/>'
        + _chev(206, 18, 1, 0, ACCENT)
        + _chev(206, 72, 1, 0, ACCENT)
        + f'<circle cx="20" cy="45" r="5" fill="none" stroke="{CONN}"/>'
        f'<circle cx="20" cy="45" r="2.5" fill="{ACCENT}"/>',
    )


def px_region() -> str:
    return _svg(
        250,
        104,
        f'<rect x="4" y="4" width="242" height="96" rx="16" fill="none" stroke="{CONN}" '
        f'stroke-width="1.25" stroke-dasharray="4 4"/>'
        f'<text x="20" y="26" style="font:400 10px JetBrains Mono;letter-spacing:.08em" fill="{DIM}">RECOVERY</text>'
        f'<rect x="20" y="40" width="88" height="28" rx="8" fill="{CHIPBG}" stroke="{STROKE}"/>'
        f'<rect x="124" y="40" width="88" height="28" rx="8" fill="{CHIPBG}" stroke="{STROKE}"/>',
    )


def px_zone_pair() -> str:
    return _svg(
        340,
        30,
        f'<text x="4" y="20" style="font:700 12.5px Inter;letter-spacing:.18em" fill="{INK}">OPERATIONS</text>'
        f'<text x="336" y="20" text-anchor="end" style="font:700 12.5px Inter;letter-spacing:.18em" '
        f'fill="{ACCENT}">DESTINATIONS</text>',
    )


def px_caption() -> str:
    return _svg(
        360,
        26,
        f'<text x="180" y="17" text-anchor="middle" style="font:400 14px Inter" fill="{DIM}">'
        f"one sentence, bottom-center · {ANN.get('caption_bottom_pad')}px of air below</text>",
    )


def px_annotation() -> str:
    return _svg(
        320,
        26,
        f'<text x="160" y="17" text-anchor="middle" style="font:400 12px JetBrains Mono;letter-spacing:.04em" '
        f'fill="{DIM}">an anchored aside — subordinate by ink, above the cards</text>',
    )


PIECE_SAMPLES: list[tuple[str, str, str]] = [
    ("card", "w = text column + name/desc ink + pads · glyph slot at +{gx:g} · text at +{tx:g}", "CARD"),
    ("hero", "the crown — hero voices, bilateral centering; floors at its family, never a fixed frame", "HERO"),
    ("glyph-circle", "a bare ring on the paper (no plate) — name Inter above mono desc, stacked below", "CIRCLE"),
    ("text block", "containers earn their existence — the type IS the node; ink name over mono descs", "TEXT"),
    (
        "chip row",
        "in-card pills: h {ch:g} · rx {crx:g} · pads {cp:g} · gap {cg:g} — parts attach by containment",
        "CHIPROW",
    ),
    ("edge-chip", "threaded ON its wire, even t = (run − w)/2 each side; slides to a clear seat", "EDGECHIP"),  # noqa: RUF001
    ("micro-label", "bare tracked text floated clear of its run — never boxed", "MICRO"),
    ("solid edge", "assert — {cw:g}px stroke, drawn chevron at the exact arrival tangent", "SOL"),
    ("drift edge", "observe — dash {dash} on the {drift} clock, terminal dot", "DRIFT"),
    ("accent edge", "the ONE privileged relationship — accent solid, spend rarely", "ACC"),
    ("skip edge", "the long jump — 9s clock; its chip seats at the channel midpoint", "SKIP"),
    ("particle", "an accent rider — flow emphasis on a quiet wire", "PART"),
    ("beam", "the gradient-window comet ({dur}s shared clock) over a glass conduit — fixed identity", "BEAMS"),
    ("gather knot", "ring + accent core where a fan bundles; lanes end short of the card edge", "KNOT"),
    ("region", "a dashed enclosure binding a sub-whole — a compound made visible", "REGION"),
    ("zone header", "the corner pair: first zone ink left, second accent right, one law places both", "ZONES"),
    ("caption", "the one-sentence footer", "CAP"),
    ("annotation", "callout / aside / legend — subordinate by ink, painted above the cards", "ANNOT"),
]


def _sample(tag: str) -> str:
    return {
        "CARD": px_card(),
        "HERO": px_card(hero=True),
        "CIRCLE": px_circle(),
        "TEXT": px_text_block(),
        "CHIPROW": px_chip_row(),
        "EDGECHIP": px_edge_chip(),
        "MICRO": px_micro_label(),
        "SOL": px_edge("solid"),
        "DRIFT": px_edge("drift"),
        "ACC": px_edge("accent"),
        "SKIP": px_edge("skip"),
        "PART": px_edge("particle"),
        "BEAMS": px_edge("beam"),
        "KNOT": px_knot(),
        "REGION": px_region(),
        "ZONES": px_zone_pair(),
        "CAP": px_caption(),
        "ANNOT": px_annotation(),
    }[tag]


# ── the bend proof: one story through orientations / faces / sizes ──────────

BEND_FAN: dict[str, Any] = {
    "title": "One seed, many doors",
    "topology": "fanout",
    "node_style": "card+glyph",
    "nodes": [
        {"id": "seed", "label": "seed", "desc": "aesthetic dna", "role": "hero", "kind": "droplet"},
        {"id": "badge", "label": "badge", "desc": "112×20", "kind": "box"},  # noqa: RUF001
        {"id": "chart", "label": "chart", "desc": "axis · series", "kind": "activity"},
        {"id": "diagram", "label": "diagram", "desc": "the kit", "kind": "boxes"},
    ],
    "edges": [
        {"source": "seed", "target": "badge"},
        {"source": "seed", "target": "chart"},
        {"source": "seed", "target": "diagram"},
    ],
}


def _bend(orientation: str, *, circles: bool = False) -> dict:
    d = json.loads(json.dumps(BEND_FAN))
    d["orientation"] = orientation
    if circles:
        d["node_style"] = "glyph-circle"
    return d


def _pipe(n: int) -> dict:
    names = ["spec", "resolve", "layout", "annotate", "render", "digest", "ship"]
    return {
        "title": f"{n} stages",
        "topology": "pipeline",
        "node_style": "card+glyph",
        "nodes": [{"id": f"s{i}", "label": names[i], "desc": "stage", "kind": "box"} for i in range(n)],
        "edges": [{"source": f"s{i}", "target": f"s{i + 1}"} for i in range(n - 1)],
    }


TOPOLOGY_EXHIBITS: list[tuple[str, str, str]] = [
    ("pipeline", "rag-pipeline", "stages on one rail; chips ride the runs"),
    ("fanout", "model-router", "one source, many doors — trunk, knot, locked column"),
    ("fanout · beam", "parity-beam", "the relay recipe: trunk first, doors together"),
    ("hub · compass", "frame-engine-hub", "uniform tiles at compass seats, kissing spokes"),
    ("hub · panel", "hub-panel-orchestrator", "corner-exit quadratics to containerless type"),
    ("ring", "agent-loop-ring", "equal stages, empty centre"),
    ("flywheel · circles", "flywheel-circles", "medallions ON the ring, axis crown"),
    ("convergence", "convergence-arrivals", "many inputs, one mouth"),
    ("stack", "stack", "layers composed upward"),
    ("comparison", "comparison", "muted BEFORE, hero AFTER"),
    ("dag", "frontier-serving", "ranked flow with skips"),
    ("tree", "tree", "hierarchy on a bus"),
    ("state-machine", "agent-task-lifecycle", "the glyph-card chain; returns ride the drift"),
    ("sequence", "auth-sequence", "lifelines, activations, the call/return key"),
    ("lanes", "obi-engine", "category bands, morphology marks, the bus rail"),
]


def build() -> None:
    css = f"""
    body{{font:15px/1.55 'Inter',system-ui,sans-serif;color:{INK};background:#FFFFFF;
      margin:0 auto;padding:56px 48px 96px;max-width:1120px}}
    h1{{font:700 28px 'Inter';color:{INK};margin:0 0 6px}}
    h2{{font:700 13px 'Inter';letter-spacing:.18em;color:{INK};margin:64px 0 14px;text-transform:uppercase}}
    .cap{{font:400 13.5px 'Inter';color:{DIM};margin:4px 0 0;max-width:76ch}}
    .law{{font:400 12px 'JetBrains Mono',ui-monospace,monospace;color:{DIM};letter-spacing:.02em;
      border-left:2px solid {STROKE};padding:8px 14px;margin:14px 0;white-space:pre-wrap}}
    .pieces{{display:grid;grid-template-columns:1fr 1fr;gap:14px 28px}}
    .piece{{border:1px solid {STROKE};border-radius:16px;padding:16px 18px;display:flex;
      flex-direction:column;gap:8px;background:#FFFFFF}}
    .piece .hd{{display:flex;align-items:baseline;gap:10px}}
    .piece b{{font:600 14px 'Inter';color:{INK}}}
    .piece .sample{{min-height:56px;display:flex;align-items:center;overflow-x:auto}}
    .piece .note{{font:400 12px 'Inter';color:{DIM}}}
    .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}}
    .grid3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;align-items:start}}
    .exhibit{{border:1px solid {STROKE};border-radius:16px;padding:14px;overflow-x:auto;background:#FFF}}
    .exhibit svg{{max-width:100%;height:auto;display:block;margin:0 auto}}
    .exhibit .t{{font:600 12px 'Inter';color:{DIM};margin:0 0 8px;letter-spacing:.06em;text-transform:uppercase}}
    pre.spec{{font:400 11.5px 'JetBrains Mono';background:{CHIPBG};border:1px solid {STROKE};
      border-radius:12px;padding:14px;overflow-x:auto;margin:0}}
    table{{border-collapse:collapse;font:400 12.5px 'JetBrains Mono';width:100%}}
    td,th{{border-bottom:1px solid {CHIPBG};padding:6px 14px 6px 0;text-align:left;color:{INK}}}
    th{{font:600 11px 'Inter';letter-spacing:.14em;color:{DIM};text-transform:uppercase}}
    """
    p: list[str] = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>The HyperWeave diagram kit — explainer plate</title>"
        f"<style>{css}</style></head><body>",
        "<h1>The HyperWeave diagram kit</h1>",
        "<p class='cap'>A fixed alphabet, not a blank canvas — you declare the semantics, the engine owns the "
        "craft. Every piece below is drawn from the engine's live constants and the primer genome's live "
        "hexes; every full diagram is a real render composed at build time.</p>",
    ]

    # 00 — the pieces, DRAWN
    p.append("<h2>00 · the pieces</h2>")
    p.append(
        "<p class='cap'>The closed alphabet. Each sample is drawn at true size with the same numbers the "
        "engine renders with.</p><div class='pieces'>"
    )
    fmt = {
        "gx": PAD_X,
        "tx": TEXT_X,
        "ch": CHIP_H,
        "crx": CHIP_RX,
        "cp": CHIP_PAD_X,
        "cg": CHIP_GAP,
        "cw": float(CN.get("width", 1.5)),
        "dash": DASH,
        "drift": DRIFT,
        "dur": BEAM.get("dur", 5.236),
    }
    for i, (name, note, tag) in enumerate(PIECE_SAMPLES, start=1):
        p.append(
            f"<div class='piece'><div class='hd'><b>{i:02d} · {name}</b></div>"
            f"<div class='sample'>{_sample(tag)}</div>"
            f"<div class='note'>{html.escape(note.format(**fmt))}</div></div>"
        )
    p.append("</div>")

    # 01 — slots in a node (anatomy with dashed slot overlay, live offsets)
    p.append("<h2>01 · the slots in a card</h2>")
    w, h = 58 + 96 + 14, 60
    p.append(
        "<div class='grid2'><div class='exhibit'>"
        + _svg(
            w + 260,
            h + 30,
            f'<rect x="4" y="12" width="{w}" height="{h}" rx="13" fill="{CARD}" stroke="{STROKE}"/>'
            + _glyph_stub(4 + PAD_X, 12 + 18, GLYPH_MARK_W)
            + f'<text x="{4 + TEXT_X}" y="{12 + 25}" style="font:600 15px Inter" fill="{INK}">node name</text>'
            + f'<text x="{4 + TEXT_X}" y="{12 + 44}" style="font:400 11px JetBrains Mono" '
            f'fill="{DIM}">mono subtitle</text>'
            + f'<rect x="{4 + PAD_X - 2}" y="{12 + 16}" width="{GLYPH_MARK_W + 4}" height="{GLYPH_MARK_W + 4}" '
            f'fill="none" stroke="{CONN}" stroke-dasharray="4 4"/>'
            + f'<path d="M {4 + TEXT_X},{12 + 25} L {w + 40},{12 + 25} M {4 + TEXT_X},{12 + 44} L {w + 40},{12 + 44}" '
            f'stroke="{CONN}" stroke-dasharray="4 4"/>'
            + f'<text x="{w + 48}" y="{12 + 12}" style="font:400 10px JetBrains Mono" '
            f'fill="{DIM}">glyph slot {GLYPH_MARK_W:g} @ +{PAD_X:g}</text>'
            + f'<text x="{w + 48}" y="{12 + 29}" style="font:400 10px JetBrains Mono" '
            f'fill="{DIM}">name baseline +25 · text @ +{TEXT_X:g}</text>'
            + f'<text x="{w + 48}" y="{12 + 48}" style="font:400 10px JetBrains Mono" '
            f'fill="{DIM}">sub baseline +44 · pitch 19</text>',
        )
        + "</div><div class='law'>"
        + html.escape(
            f"w = {TEXT_X:g} + max(name ink, desc ink) + pads · snap 4 — cards size to their own ink\n"
            f"widths lock only within a stacked column, to the COLUMN's widest content\n"
            f"hero mark {HERO_GLYPH_MARK_W:g} · the crown floors at its family's widest column\n"
            f"(a declared hero_min_w is specimen law) · compass hero aspect cap {HUBCFG.get('hero_aspect_max')}\n"
            f"chips measure the voice they render in — always"
        )
        + "</div></div>"
    )

    # 02 — the bend proof: one story, four orientations + circle face
    p.append("<h2>02 · one story, many shapes</h2>")
    p.append(
        "<p class='cap'>The SAME spec — three doors off one seed — bent through orientations and node faces. "
        "Topology is semantics; orientation and face are presentation. This is the lego claim, rendered.</p>"
    )
    p.append("<div class='grid2'>")
    for label, spec in (
        ("horizontal · cards", _bend("horizontal")),
        ("downward · cards", _bend("downward")),
        ("bilateral · circles", _bend("bilateral", circles=True)),
        ("radial · circles", _bend("radial", circles=True)),
    ):
        p.append(f"<div class='exhibit'><p class='t'>{label}</p>{_render(spec)}</div>")
    p.append("</div>")
    p.append("<div class='grid2'>")
    for label, spec in (
        ("pipeline · 3 stages", _pipe(3)),
        ("pipeline · 6 stages — same card size, wider canvas", _pipe(6)),
    ):
        p.append(f"<div class='exhibit'><p class='t'>{label}</p>{_render(spec)}</div>")
    p.append("</div>")

    # 03 — how the spatial engine composes
    p.append("<h2>03 · how the engine composes</h2>")
    p.append(
        "<div class='law'>"
        + html.escape(
            "place    boxes from measured ink on the 4px grid; column locks; crowns step over their family\n"
            "route    straight when aligned, C-curves with controls at mid, channels for skips — end\n"
            "         tangents pinned to the arrival axis (the chevron reads the SOLVER's exact tangent)\n"
            "label    chips thread ON their runs (slide clear of crossing wires); micro-labels float clear\n"
            "collide  floaters nudge around nodes/wires; pinned pieces never move off-run\n"
            "chrome   ONE law seats zone headers "
            + f"{ANN.get('zone_header_gap')}px above the content top and the caption with "
            + f"{ANN.get('caption_bottom_pad')}px of air\n"
            "render   svg + hw:payload + hwz/1 digest — the visual is one projection of the IR"
        )
        + "</div>"
    )
    p.append(
        "<p class='cap'>Declare semantics, the engine owns the craft — the spec is the only authored artifact:</p>"
    )
    p.append("<div class='grid2'>")
    p.append(f"<pre class='spec'>{html.escape(json.dumps(_bend('horizontal'), indent=2))}</pre>")
    p.append(f"<div class='exhibit'>{_render(_bend('horizontal'))}</div>")
    p.append("</div>")

    # 04 — chassis coverage (the "most codebases" answer, live caps)
    p.append("<h2>04 · chassis coverage</h2>")
    lay_caps = CAPS.get("layouts") or {}
    p.append("<table><tr><th>topology</th><th>orientations</th><th>node counts</th><th>faces</th></tr>")
    face_note = {
        "pipeline": "cards · circles",
        "fanout": "cards · circles",
        "hub": "cards · circles · text",
        "ring": "circles",
        "flywheel": "cards · circles",
        "state-machine": "glyph cards",
        "sequence": "heads",
        "lanes": "bulleted cards",
    }
    # The topology rows come from the LIVE schema; the slugs each row expands
    # to come from the LIVE solver registry, not the caps config — a word
    # added to (or merged out of) _SOLVER_MODULES changes this grid on regen,
    # and a slug with a cap entry but no registered solver (or vice versa)
    # can no longer drift silently out of the plate.
    _topos = [t.value for t in Topology]
    _registered = set(registered_slugs())
    for topo in _topos:
        slugs = sorted(s for s in _registered if s == topo or s.startswith(topo + "-"))
        rng = (
            " · ".join(
                f"{s.split('-', 1)[-1] if '-' in s else 'base'} "
                f"{lay_caps.get(s, {}).get('min', '?')}–{lay_caps.get(s, {}).get('max', '?')}"  # noqa: RUF001
                for s in slugs
            )
            or "—"
        )
        ors = " ".join(LEGAL.get(topo, ["—"]))
        p.append(f"<tr><td>{topo}</td><td>{ors}</td><td>{rng}</td><td>{face_note.get(topo, 'cards')}</td></tr>")
    p.append("</table>")
    p.append(
        f"<p class='cap'>Hard cap {CAPS.get('hard_nodes')} nodes per artifact — compose never crowds a "
        "topology; a bigger system splits into multiple diagrams (nesting embeds one inside another). The "
        f"claim: most codebase structures reduce to these {len(_topos)} patterns — flows (pipeline, fanout, "
        "convergence, dag), cycles (ring, flywheel, state-machine), structure (stack, tree, hub, lanes, "
        "comparison), and time (sequence).</p>"
    )

    # 05+ — one real render per topology
    for i, (label, preset, blurb) in enumerate(TOPOLOGY_EXHIBITS, start=5):
        p.append(f"<h2>{i:02d} · {html.escape(label)}</h2>")
        p.append(f"<p class='cap'>{html.escape(blurb)} · preset <code>{preset}</code></p>")
        if preset == "parity-beam":
            p.append("<div class='grid2'>")
            p.append(f"<div class='exhibit'>{_render(preset, variant='noir', face='dark', motion='animated')}</div>")
            p.append(f"<div class='exhibit'>{_render(preset)}</div>")
            p.append("</div><p class='cap'>noir animated beside the porcelain static twin</p>")
        else:
            p.append(f"<div class='exhibit'>{_render(preset)}</div>")

    p.append(
        "<p class='cap' style='margin-top:56px'>The kit · pieces are spent, not drawn — what doesn't "
        "communicate is cut.</p></body></html>"
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "kit-explainer.html").write_text("".join(p))
    print(
        f"kit-explainer.html — {len(PIECE_SAMPLES)} drawn pieces, 6 bend renders, "
        f"{len(TOPOLOGY_EXHIBITS)} topology exhibits, live values"
    )


if __name__ == "__main__":
    build()
