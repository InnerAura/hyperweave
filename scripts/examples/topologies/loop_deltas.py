"""Measured delta lists: the loop expression corpus vs the engine's current output.

For each hand specimen under ``v04/v040/v044/loop/**-specimens*/`` this
harness authors the nearest-LEGAL engine spec (only vocabulary the solver
accepts today), renders it exactly as the parity board does (primer /
porcelain / fixed), measures both sides with the same extractors the fixture
pipeline uses, and emits a field-by-field delta record. Everything an
expression needs that the IR cannot yet say (a lap meter, swimlanes, a scope
placement, a ring form) is recorded as a structural-absence delta with its
specimen citation — never invented as an IR field. A spec the engine refuses
records the refusal verbatim; that refusal IS the measurement.

The corpus panels are bare plates (no masthead, no caption): plate/caption
deltas against the engine's chrome are expected framing, not defects, and
are pre-classed ``chrome`` so triage can skim past them.

Outputs (gitignored; this script is the deliverable — everything lands
under the diagrams exhibit's own renders/ tree):
  outputs/diagrams/renders/topologies/loop/expressions/measure/{slug}.specimen.json
  outputs/diagrams/renders/topologies/loop/expressions/measure/{slug}.render.json
  outputs/diagrams/renders/topologies/loop/expressions/deltas/{slug}.delta.json
  outputs/diagrams/renders/topologies/loop/expressions/{slug}.svg
plus the side-by-side board index in the triage-packet directory.

Run: ``uv run python -m scripts.examples.topologies.loop_deltas``
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from hyperweave.compose.engine import compose  # noqa: E402
from scripts.examples.render import gallery_spec  # noqa: E402
from scripts.extract_specimen_fixtures import extract_geometry  # noqa: E402

CORPUS = REPO / "v04" / "v040" / "v044" / "loop"
OUT = REPO / "outputs" / "diagrams" / "renders" / "topologies" / "loop" / "expressions"
PACKET = CORPUS / "docs" / "expression-wave-triage"

# ── The four instance stories, each rooted in a shipped anchor preset ────────


def _nested_spec() -> dict[str, Any]:
    return {
        "topology": "loop",
        "node_style": "card+glyph",
        "title": "Plan, delegate, integrate",
        "nodes": [
            {"id": "plan", "label": "Plan the task", "desc": "break it down"},
            {"id": "scope", "label": "Tool loop · inner", "station": "scope"},
            {
                "id": "i1",
                "label": "Decide",
                "desc": "next move",
                "enclosure": "scope",
                "kind": "git-branch",
            },
            {
                "id": "i2",
                "label": "Call",
                "desc": "mcp · code",
                "enclosure": "scope",
                "kind": "zap",
            },
            {
                "id": "i3",
                "label": "Read",
                "desc": "observe",
                "enclosure": "scope",
                "kind": "eye",
            },
            {
                "id": "integ",
                "label": "Integrate results",
                "desc": "update the plan",
            },
            {"id": "dq", "label": "Done?", "station": "decision"},
            {
                "id": "term",
                "label": "Done",
                "desc": "report it",
                "station": "terminal",
                "partition": "advance",
            },
        ],
        "edges": [
            {
                "from": "plan",
                "to": "scope",
                "label": "delegate",
                "label_style": "chip",
            },
            {"from": "i1", "to": "i2"},
            {"from": "i2", "to": "i3"},
            {
                "from": "i3",
                "to": "i1",
                "label": "next call",
                "label_style": "chip",
                "circuit": "return",
            },
            {
                "from": "scope",
                "to": "integ",
                "label": "answer found",
                "label_style": "chip",
            },
            {"from": "integ", "to": "dq"},
            {
                "from": "dq",
                "to": "term",
                "label": "yes",
                "label_style": "chip",
            },
            {
                "from": "dq",
                "to": "plan",
                "label": "no · go again",
                "label_style": "chip",
                "circuit": "return",
            },
        ],
    }


def _retry_spec(*, budget_chips: bool = False) -> dict[str, Any]:
    yes = "yes · budget left" if budget_chips else "yes"
    no = "no · budget out" if budget_chips else "no"
    return {
        "topology": "loop",
        "node_style": "card+glyph",
        "title": "Retry with backoff",
        "nodes": [
            {
                "id": "call",
                "label": "Call the tool",
                "desc": "attempt n",
                "kind": "zap",
            },
            {"id": "succ", "label": "Succeeded?", "station": "decision"},
            {
                "id": "done",
                "label": "Done",
                "desc": "return the result",
                "station": "terminal",
                "partition": "advance",
            },
            {"id": "retry", "label": "Retry?", "station": "decision"},
            {
                "id": "back",
                "label": "Back off",
                "desc": "wait 2^n + jitter",
                "kind": "clock",
            },
            {
                "id": "fail",
                "label": "Failed",
                "desc": "surface the error",
                "station": "terminal",
                "partition": "exhausted",
            },
        ],
        "edges": [
            {"from": "call", "to": "succ"},
            {
                "from": "succ",
                "to": "done",
                "label": "yes",
                "label_style": "chip",
            },
            {
                "from": "succ",
                "to": "retry",
                "label": "no",
                "label_style": "chip",
            },
            {
                "from": "retry",
                "to": "back",
                "label": yes,
                "label_style": "chip",
            },
            {
                "from": "retry",
                "to": "fail",
                "label": no,
                "label_style": "chip",
            },
            {
                "from": "back",
                "to": "call",
                "label": "attempt n+1",
                "label_style": "chip",
                "circuit": "return",
            },
        ],
    }


def _retry_unrolled_spec() -> dict[str, Any]:
    # The honest unrolled structure: a finite attempt ladder with convergent
    # success exits and no return edge. If the solver refuses it, the refusal
    # is the measurement.
    return {
        "topology": "loop",
        "node_style": "card+glyph",
        "title": "Retry, unrolled",
        "nodes": [
            {
                "id": "a1",
                "label": "Attempt 1",
                "desc": "call the tool",
                "kind": "zap",
            },
            {
                "id": "a2",
                "label": "Attempt 2",
                "desc": "call the tool",
                "kind": "zap",
            },
            {
                "id": "a3",
                "label": "Attempt 3",
                "desc": "call the tool",
                "kind": "zap",
            },
            {
                "id": "done",
                "label": "Done",
                "desc": "return the result",
                "station": "terminal",
                "partition": "advance",
            },
            {
                "id": "fail",
                "label": "Failed",
                "desc": "surface the error",
                "station": "terminal",
                "partition": "exhausted",
            },
        ],
        "edges": [
            {
                "from": "a1",
                "to": "a2",
                "label": "fail · wait 1s",
                "label_style": "chip",
            },
            {
                "from": "a2",
                "to": "a3",
                "label": "fail · wait 2s",
                "label_style": "chip",
            },
            {"from": "a1", "to": "done"},
            {
                "from": "a2",
                "to": "done",
                "label": "succeeded",
                "label_style": "chip",
            },
            {"from": "a3", "to": "done"},
            {
                "from": "a3",
                "to": "fail",
                "label": "budget out",
                "label_style": "chip",
            },
        ],
    }


def _flywheel_spec(*, descs: bool = True, chip: str = "compounds · each turn") -> dict[str, Any]:
    def node(nid: str, label: str, desc: str, kind: str) -> dict[str, Any]:
        d: dict[str, Any] = {"id": nid, "label": label, "kind": kind}
        if descs:
            d["desc"] = desc
        return d

    return {
        "topology": "loop",
        "node_style": "card+glyph",
        "title": "The data flywheel",
        "motion_register": "turn",
        "nodes": [
            node("gen", "Generate", "agents create", "zap"),
            node("dist", "Distribute", "ship anywhere", "upload"),
            node("cap", "Capture", "corpus grows", "database"),
            node("imp", "Improve", "model learns", "refresh-cw"),
        ],
        "edges": [
            {"from": "gen", "to": "dist"},
            {"from": "dist", "to": "cap"},
            {"from": "cap", "to": "imp"},
            {
                "from": "imp",
                "to": "gen",
                "label": chip,
                "label_style": "chip",
                "circuit": "return",
                "accumulates": True,
            },
        ],
    }


def _shuttle_spec(*, handoff_chip: bool = False) -> dict[str, Any]:
    fwd: dict[str, Any] = {"from": "draft", "to": "review"}
    if handoff_chip:
        fwd.update({"label": "hands over", "label_style": "chip"})
    return {
        "topology": "loop",
        "node_style": "card+glyph",
        "title": "Revise and resubmit",
        "nodes": [
            {
                "id": "draft",
                "label": "Draft",
                "desc": "agent writes v(n)",
                "kind": "file-code",
            },
            {
                "id": "review",
                "label": "Review",
                "desc": "human reads the diff",
                "kind": "eye",
            },
            {"id": "appr", "label": "Approve?", "station": "decision"},
            {
                "id": "ship",
                "label": "Shipped",
                "desc": "merged to main",
                "station": "terminal",
                "partition": "advance",
            },
        ],
        "edges": [
            fwd,
            {"from": "review", "to": "appr"},
            {
                "from": "appr",
                "to": "ship",
                "label": "approved",
                "label_style": "chip",
            },
            {
                "from": "appr",
                "to": "draft",
                "label": "changes requested",
                "label_style": "chip",
                "circuit": "return",
            },
        ],
    }


def _with(spec: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {**spec, **kw}


# ── Candidates: slug, claim, specimen path, structural absences, spec ────────
# An absence entry is (what the specimen draws that the IR cannot say,
# specimen citation, engine seam). The delta file carries them verbatim.

_CANDIDATES: list[tuple[str, str, str, list[tuple[str, str, str]], dict[str, Any]]] = [
    (
        "nested-inline",
        "Inline scope on the spine — the shipped placement, new generation of the anchor.",
        "nested/nested-specimens/diagram-loop-nested-inline-turn.svg",
        [],
        _with(_nested_spec(), motion_register="turn"),
    ),
    (
        "nested-aside",
        "Scope seated beside the spine, top-right; the outer ranks run past it.",
        "nested/nested-specimens/diagram-loop-nested-aside-turn.svg",
        [
            (
                "aside scope placement (off-spine seat)",
                "Scope 640x210 at (486,51); outer ranks y=156/391/689",
                "compose/diagram/loop.py:_assign_seats scope fall-through (spine-only today)",
            )
        ],
        _with(_nested_spec(), motion_register="turn"),
    ),
    (
        "nested-laps",
        "Inline scope with a lap counter: the meter grows and resets with the outer turn.",
        "nested/nested-specimens/diagram-loop-nested-inline-laps.svg",
        [
            (
                "laps register + lap counter meter",
                "scenarios: outer turn 1: 3 inner laps -> go again; outer turn 2: 1 inner lap -> ship",
                "compose/diagram/choreography.py:_CHOREOGRAPHERS + a node-attached meter piece",
            )
        ],
        _with(_nested_spec(), motion_register="turn"),
    ),
    (
        "nested-lateral",
        "Horizontal outer loop; the inner circuit runs the counter-axis as a column.",
        "nested/nested-specimens/diagram-loop-nested-lateral-turn.svg",
        [],
        _with(
            _nested_spec(),
            motion_register="turn",
            orientation="horizontal",
            # The hand cell honestly carries 8 nodes; the spec lifts its OWN
            # ceiling (never the family default).
            caps={"max_nodes": 8},
        ),
    ),
    (
        "retry-axial",
        "The rolled retry, new generation: descs on every station, Done/Failed pills.",
        "retry/retry-specimens/diagram-loop-retry-axial-turn.svg",
        [],
        _with(_retry_spec(), motion_register="turn"),
    ),
    (
        "retry-lateral",
        "The rolled retry transposed: success rank exits upward, under-rail return.",
        "retry/retry-specimens/diagram-loop-retry-lateral-turn.svg",
        [],
        _with(_retry_spec(), motion_register="turn", orientation="horizontal"),
    ),
    (
        "retry-budget",
        "The rolled retry with the budget spoken: a drain meter on the rail.",
        "retry/retry-specimens/diagram-loop-retry-axial-budget.svg",
        [
            (
                "budget register + rail drain meter",
                "Meter: 3 segments of 26x13 on the rail beside the attempt chip",
                "compose/diagram/choreography.py:_CHOREOGRAPHERS + a rail-attached meter piece",
            )
        ],
        _with(_retry_spec(budget_chips=True), motion_register="turn"),
    ),
    (
        "retry-unrolled",
        "The loop unrolled: a finite budget ladder with a convergent success bus.",
        "retry/retry-specimens/diagram-loop-retry-unrolled-turn.svg",
        # The gather bus landed (loop.py:_bus_geo — arms, bus_r fillets, one marked
        # stem), so this cell has no structural absence left. What remains is a spatial
        # limit, not a missing piece: the shipped preset clears the chip-occlusion law
        # only on a cited `chip_visible_run` waiver.
        [],
        _retry_unrolled_spec(),
    ),
    (
        "flywheel-vertical",
        "The flywheel spoken as turn choreography, vertical — new generation of the anchor.",
        "runloop/runloop-specimens-v2/diagram-loop-flywheel-axial-vertical-turn.svg",
        [],
        _flywheel_spec(),
    ),
    (
        "flywheel-horizontal",
        "The flywheel transposed: horizontal spine, underslung rail.",
        "runloop/runloop-specimens-v2/diagram-loop-flywheel-axial-horizontal-turn.svg",
        [],
        _with(_flywheel_spec(), orientation="horizontal"),
    ),
    (
        "flywheel-accumulate",
        "The flywheel with the gain spoken: accumulator readouts grow and hold.",
        "runloop/runloop-specimens-v2/diagram-loop-flywheel-axial-vertical-accumulate.svg",
        [
            (
                "accumulate register + accumulator readouts",
                'accumulates: ["corpus size", "model quality"]; period 11.51s over 3 turns',
                "compose/diagram/choreography.py:_CHOREOGRAPHERS + accumulator meter pieces",
            )
        ],
        _flywheel_spec(),
    ),
    (
        "flywheel-ring",
        "The flywheel as a ring: four stations at compass points, tangent-port arcs.",
        "runloop/runloop-specimens-v2/diagram-loop-flywheel-ring-turn.svg",
        [
            (
                "ring form (radial orientation, tangent ports, equal arcs)",
                "Ring radius 236 at (358,316); arcs 59.91deg / 235.2px each, equal by construction; "
                "laws L-CHIP(polar), L-ARC-EQUAL",
                "family-boundary ruling: loop slug cells vs cycle territory (radial.py owns cycle-orbit/ring)",
            )
        ],
        _flywheel_spec(),
    ),
    (
        "flywheel-square",
        "The flywheel as an orthogonal ring: side-midpoint stations, filleted legs.",
        "runloop/runloop-specimens-v2/diagram-loop-flywheel-square-turn.svg",
        [
            (
                "square form (orthogonal ring, equal filleted legs)",
                "Square half-extent 236 at (358,316); each leg 331.6px through one 18 fillet, equal by construction",
                "family-boundary ruling: loop slug cells vs cycle territory",
            )
        ],
        _flywheel_spec(),
    ),
    (
        "flywheel-strip",
        "The flywheel compressed to a badge-grade strip: a pill row over an under-rail.",
        "runloop/runloop-specimens-v2/diagram-loop-flywheel-strip-turn.svg",
        [
            (
                "strip density (pill row, under-rail, badge grade)",
                "Single row y=62, four pills 46 tall sized to their own ink, under-rail y=143",
                "density axis on the loop chassis (recurs on shuttle-strip: cross-instance form)",
            )
        ],
        _with(
            _flywheel_spec(descs=False, chip="compounds"),
            orientation="horizontal",
        ),
    ),
    (
        "shuttle-lateral",
        "The shuttle, new generation: three cards with descs, guard chips at equal runs.",
        "shuttle/shuttle-specimens/diagram-loop-shuttle-lateral-turn.svg",
        [],
        _with(_shuttle_spec(), motion_register="turn", orientation="horizontal"),
    ),
    (
        "shuttle-vertical",
        "The shuttle transposed to a vertical spine — the transpose law's own test.",
        "shuttle/shuttle-specimens/diagram-loop-shuttle-vertical-turn.svg",
        [],
        _with(_shuttle_spec(), motion_register="turn"),
    ),
    (
        "shuttle-swimlane",
        "The shuttle across role lanes: work moves right in a lane, crosses down between.",
        "shuttle/shuttle-specimens/diagram-loop-shuttle-swimlane-turn.svg",
        [
            (
                "role swimlanes with gutter-seated chips and a fixed handoff column",
                "Lanes x=40 w=1000: agent/human/merged, gutters 44; forward handoff column x=424, return channel y=238",
                "a lane-membership minor-allocator (lane_bands plumbing exists; the spatial model does not)",
            )
        ],
        _with(
            _shuttle_spec(handoff_chip=True),
            motion_register="turn",
            orientation="horizontal",
        ),
    ),
    (
        "shuttle-strip",
        "The shuttle compressed to a badge-grade strip: four pills, yes/changes chips.",
        "shuttle/shuttle-specimens/diagram-loop-shuttle-strip-turn.svg",
        [
            (
                "strip density (pill row, under-rail, badge grade)",
                "Single row y=62, four pills 46 tall sized to their own text on a 66 gap, under-rail y=143",
                "density axis on the loop chassis (recurs on flywheel-strip: cross-instance form)",
            )
        ],
        _with(_shuttle_spec(), motion_register="turn", orientation="horizontal"),
    ),
]


# ── Measurement ──────────────────────────────────────────────────────────────


def _payload(svg: str) -> dict[str, Any]:
    m = re.search(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]>", svg, re.S)
    if not m:
        return {}
    try:
        loaded = json.loads(m.group(1))
    except ValueError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _spatial_notes(svg: str) -> str:
    m = re.search(r"<hw:spatial-notes>([^<]*)</hw:spatial-notes>", svg)
    return m.group(1).strip() if m else ""


def _flatten(prefix: str, value: Any, out: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}" if prefix else str(k), v, out)
    elif isinstance(value, int | float | str | bool) or value is None:
        out[prefix] = value


_SKIP_DIMS = ("source", "beam.", "edge_set.", "lane_marks")

# Bare corpus panels vs the engine's masthead/caption chrome: framing, not defects.
_CHROME_DIMS = (
    "plate.",
    "caption",
    "viewbox",
    "aspect",
    "width",
    "height",
    "occupancy",
)

# The corpus generation writes a compressed class dialect (-s subs, -h
# choreography halos, animated dashed wires) the anchor-calibrated census and
# chip readers miscount: halos read as cards, subs go unseen, animated wires
# read as drift, pulse paths inflate the port envelope. The payload audit
# block is the specimen's own measurement channel for chips. Teaching the
# readers this dialect is enrollment work — until then these dims measure the
# reader, not the engine.
_READER_GAP_DIMS = (
    "census.cards",
    "census.desc_lines",
    "census.drift_edges",
    "census.solid_edges",
    "census.chips",
    "census.animated",
    "census.glyph_marks",
    "census.arrow_terminals",
    "census.hero_cards",
    "census.hero_rx",
    "census.micro_labels",
    "chip_homes.",
    "chip_stub_min",
    "port_tolerance",
)


def _delta_rows(spec_stats: dict[str, Any], rend_stats: dict[str, Any]) -> list[dict[str, Any]]:
    flat_s: dict[str, Any] = {}
    flat_r: dict[str, Any] = {}
    _flatten("", spec_stats, flat_s)
    _flatten("", rend_stats, flat_r)
    rows: list[dict[str, Any]] = []
    for dim in sorted(set(flat_s) | set(flat_r)):
        if any(dim.startswith(sk) or sk in dim for sk in _SKIP_DIMS):
            continue
        sv, rv = flat_s.get(dim), flat_r.get(dim)
        if sv == rv:
            continue
        row: dict[str, Any] = {"dim": dim, "specimen": sv, "render": rv}
        if dim.startswith(_CHROME_DIMS):
            row["class"] = "chrome"
        elif dim.startswith(_READER_GAP_DIMS):
            row["class"] = "reader-gap"
        elif isinstance(sv, int | float) and isinstance(rv, int | float) and not isinstance(sv, bool):
            row["delta"] = round(rv - sv, 2)
            tol = 0.10 * max(abs(sv), 1.0) if any(t in dim for t in ("_w", "_h", "hero")) else 6.0
            row["class"] = "free-confirm" if abs(rv - sv) <= tol else "triage"
        else:
            row["class"] = "triage"
        rows.append(row)
    return rows


def main() -> None:
    for sub in ("measure", "deltas"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    (PACKET / "boards").mkdir(parents=True, exist_ok=True)
    board_lines = [
        "# Loop expression corpus — specimen | render board",
        "",
        "Nearest-legal engine render beside each hand specimen. Raw measurements and",
        "delta records live under `outputs/diagrams/renders/topologies/loop/expressions/` (regenerate with",
        "`uv run python -m scripts.examples.topologies.loop_deltas`).",
        "",
        # HTML rows with equal-width image cells — markdown tables render each
        # SVG at natural size, so a wide specimen dwarfs its render.
        '<table><tr><th>cell</th><th width="40%">specimen</th>'
        '<th width="40%">engine render (nearest-legal)</th><th>absences</th></tr>',
    ]
    summary: list[str] = []
    for slug, claim, rel, absences, spec in _CANDIDATES:
        source = CORPUS / rel
        svg_text = source.read_text()
        spec_stats = extract_geometry(f"zz-{slug}", source)
        spec_record = {
            "claim": claim,
            "spatial_notes": _spatial_notes(svg_text),
            "payload": _payload(svg_text),
            "stats": spec_stats,
        }
        (OUT / "measure" / f"{slug}.specimen.json").write_text(json.dumps(spec_record, indent=2, sort_keys=True) + "\n")

        refusal: str | None = None
        rend_stats: dict[str, Any] = {}
        render_path = OUT / f"{slug}.svg"
        try:
            svg = compose(
                gallery_spec(
                    type="diagram",
                    genome_id="primer",
                    variant="porcelain",
                    ground="opaque",
                    palette="fixed",
                    diagram=spec,
                )
            ).svg
        except Exception as exc:  # a refusal is a measurement, not a crash
            refusal = f"{type(exc).__name__}: {exc}"
        else:
            render_path.write_text(svg)
            shutil.copyfile(render_path, PACKET / "boards" / f"{slug}.render.svg")
            rend_stats = extract_geometry(f"zz-{slug}-render", render_path)
        (OUT / "measure" / f"{slug}.render.json").write_text(
            json.dumps(
                {"refusal": refusal, "stats": rend_stats},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        delta = {
            "slug": slug,
            "claim": claim,
            "source": str(source.relative_to(REPO)),
            "identity": {
                k: spec_record["payload"].get(k)
                for k in ("instance", "expression", "orientation", "register")
                if isinstance(spec_record["payload"], dict) and k in spec_record["payload"]
            },
            "authored_spec": spec,
            "refusal": refusal,
            "structural_absences": [
                {
                    "absent": what,
                    "cite": cite,
                    "seam": seam,
                    "class": "structural-absence",
                }
                for what, cite, seam in absences
            ],
            "rows": _delta_rows(spec_stats, rend_stats) if refusal is None else [],
        }
        (OUT / "deltas" / f"{slug}.delta.json").write_text(json.dumps(delta, indent=2, sort_keys=True) + "\n")

        webp = "../../imgs/" + rel.replace(".svg", ".webp")
        render_cell = (
            f'<img src="boards/{slug}.render.svg" width="100%">'
            if refusal is None
            else f"REFUSED: <code>{refusal}</code>"
        )
        board_lines.append(
            f"<tr><td><b>{slug}</b> — {claim}</td>"
            f'<td><img src="{webp}" width="100%"></td>'
            f"<td>{render_cell}</td><td>{len(absences)}</td></tr>"
        )
        n_triage = sum(1 for r in delta["rows"] if r.get("class") == "triage")
        summary.append(
            f"{slug}: "
            + (
                f"REFUSED ({refusal})"
                if refusal
                else f"{n_triage} triage rows, {len(delta['rows'])} total, {len(absences)} absences"
            )
        )
    board_lines.append("</table>")
    (PACKET / "board.md").write_text("\n".join(board_lines) + "\n")
    print(f"measured {len(_CANDIDATES)} cells → {OUT.relative_to(REPO)} + {PACKET.relative_to(REPO)}/board.md")
    for line in summary:
        print(f"  {line}")


if __name__ == "__main__":
    main()
