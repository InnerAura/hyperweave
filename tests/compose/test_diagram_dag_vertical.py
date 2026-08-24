"""Class-level guards for the dag flow axis.

Every defect this family produced had the same shape — an extent measured on
the wrong axis, or a constant cited from a specimen whose own content happened
to equal it — and every one was found by looking at a render. Single-graph pins
would repeat that, so these guards ask corpus-wide questions instead:

* no wire runs through a card, on either flow;
* a sink seated ON a channel and the edge that runs to it agree;
* one coordinate carries one drawn terminal;
* a gap reserves chip-run width only for the chips it actually draws;
* and the whole thing is exercised at an aspect ratio where an axis confusion
  cannot hide as a plausible-looking error.

"Corpus-wide" means the whole corpus. Fixtured on bundled presets alone these
guards reached 9 of the 19 dag stories, and the 10 they missed were the skip and
detour family the flow axis was built for — so the fixture is the union, and
membership is decided by the topology the engine RESOLVES (``_dag_corpus``).

Two siblings live in the gallery sweep rather than here — ``edge-label-on-card``
and ``detour-around-nothing`` — because both read placement decisions the sweep
already has in hand across every render in the tree, not just the dag family.
"""

from __future__ import annotations

import copy
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from hyperweave.cli import app
from hyperweave.compose.bundled_specs import bundled_spec_names, resolve_bundled_spec
from hyperweave.compose.diagram.input import coerce_diagram_input
from hyperweave.compose.engine import compose
from hyperweave.core.diagram import Topology
from hyperweave.core.models import ComposeSpec

NUM = r"-?\d+(?:\.\d+)?"

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _dag_corpus() -> dict[str, dict[str, Any]]:
    """Every dag story a reader can see, on both flows — not just the bundled half.

    The bundled presets are 9 of the 19; the other 10 are gallery stories, and
    they are the skip-and-detour family this whole flow-axis wave is about:
    order-event-dlq, cache-aside-mesh, monorepo-build-graph, rag-index-and-query.
    Fixtured on the bundled names alone, these guards would measure none of the
    graphs whose defects opened the work — the same failure as naming three
    graphs, one import away."""
    from scripts.examples.diagrams import SECTIONS

    candidates: dict[str, dict[str, Any]] = {
        name: dict(resolve_bundled_spec("diagram", name).value or {}) for name in bundled_spec_names("diagram")
    }
    for _section, stories in SECTIONS:
        for name, _caption, story in stories:
            candidates.setdefault(name, dict(story))
    # The topology the ENGINE resolves, never the one the spec declares: a dag
    # carrying a cycle promotes to state-machine at the input seam, and a
    # state-machine is horizontal-only. session-lifecycle declares `dag`, files
    # under the gallery's dag section, and is refused vertical — correctly. A
    # flow-axis guard asks about specs that actually solve as dags.
    return {
        name: spec
        for name, spec in candidates.items()
        if coerce_diagram_input(None, ComposeSpec(type="diagram", diagram=spec)).spec.topology is Topology.DAG
    }


DAG_CORPUS = _dag_corpus()
DAG_PRESETS = tuple(sorted(DAG_CORPUS))
FLOWS = ("horizontal", "vertical")


def _svg(spec: dict[str, Any]) -> str:
    return compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="bare",
            palette="fixed",
            surface_face="light",
            diagram=spec,
        )
    ).svg


def _preset_spec(name: str, flow: str) -> dict[str, Any]:
    spec = copy.deepcopy(DAG_CORPUS[name])
    if flow == "vertical":
        spec["orientation"] = "vertical"
    return spec


def _preset_svg(name: str, flow: str) -> str:
    return _svg(_preset_spec(name, flow))


def _body(svg: str) -> str:
    return svg[svg.rfind("</style>") :]


def _rects(body: str, suffix: str) -> list[tuple[float, float, float, float]]:
    """(x0, y0, x1, y1) for every rect whose id ends in one of ``suffix``."""
    return [
        (float(a), float(b), float(a) + float(c), float(b) + float(d))
        for a, b, c, d in re.findall(
            rf'<rect x="({NUM})" y="({NUM})" width="({NUM})" height="({NUM})"[^>]*-(?:{suffix})"', body
        )
    ]


def _cubic(p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float]):
    for i in range(25):
        t = i / 24
        u = 1 - t
        yield (
            u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
        )


def _legs(d: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Every drawn leg. Cubics FLATTEN — a curve bowing through a card is a
    crossing the straight-leg reading cannot see, so the guard must not
    inherit that blind spot."""
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    cur: tuple[float, float] | None = None
    for cmd, blob in re.findall(rf"([MLQC])((?:\s*{NUM}[ ,]{NUM})+)", d):
        pts = [(float(a), float(b)) for a, b in re.findall(rf"({NUM})[ ,]({NUM})", blob)]
        if cmd == "M":
            cur = pts[-1]
        elif cmd == "L":
            for q in pts:
                if cur is not None:
                    out.append((cur, q))
                cur = q
        elif cmd == "Q":  # a 7px fillet joins two legs already measured
            cur = pts[-1]
        elif cmd == "C" and cur is not None:
            flat = list(_cubic(cur, pts[0], pts[1], pts[2]))
            out += list(itertools.pairwise(flat))
            cur = pts[2]
    return out


def _wires(body: str) -> list[str]:
    return [
        m.group(1)
        for m in re.finditer(r'<path\b[^>]*\bd="(M[^"]+)"[^>]*class="([^"]*)"', body)
        if "-branch" in m.group(2)
    ]


def _depth_inside(a: tuple[float, float], b: tuple[float, float], box: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = box
    ox = min(max(a[0], b[0]), x1) - max(min(a[0], b[0]), x0)
    oy = min(max(a[1], b[1]), y1) - max(min(a[1], b[1]), y0)
    return min(ox, oy) if ox > 0 and oy > 0 else 0.0


# ── G1 · no wire runs through a card ────────────────────────────────────────


@pytest.mark.parametrize("preset", DAG_PRESETS)
@pytest.mark.parametrize("flow", FLOWS)
def test_no_wire_runs_through_a_card(preset: str, flow: str) -> None:
    """A detour's TRAVEL leg was always cleared; its ENTRY leg never was, so a
    route could ride a clear channel and then descend straight through a
    same-rank sibling to reach the card behind it — 66px of wire inside a card
    on the horizontal cell, invisible only because cards paint after edges.

    Legs that terminate on a card are arrivals, not crossings, and are exempt.
    """
    body = _body(_preset_svg(preset, flow))
    cards = _rects(body, "cardbg|herobg")
    for d in _wires(body):
        legs = _legs(d)
        if not legs:
            continue
        ends = (legs[0][0], legs[-1][1])
        for a, b in legs:
            for box in cards:
                if any(box[0] - 2 <= e[0] <= box[2] + 2 and box[1] - 2 <= e[1] <= box[3] + 2 for e in ends):
                    continue
                depth = _depth_inside(a, b, box)
                assert depth <= 2.0, f"{preset}/{flow}: wire runs {depth:.0f}px inside card {box} (leg {a}->{b})"


# ── G2 · a sink seated ON a channel and its edge agree ──────────────────────


@pytest.mark.parametrize("preset", DAG_PRESETS)
@pytest.mark.parametrize("flow", FLOWS)
def test_channel_seated_sinks_take_a_straight_arrival(preset: str, flow: str) -> None:
    """A lane member leaves the rank grid and parks ON the channel its own
    inbound edge runs at, so that edge arrives straight — one corner, no turn
    back inward.

    The defect this catches is arithmetic, not taste: a channel lives in MINOR
    space, and flooring it against a screen ``y`` reads as the minor coordinate
    flowing right and the MAJOR one flowing down. The sink parked in one place
    and the edge solved another. Corpus-wide rather than pinned to the two
    graphs that showed it, because nothing declares which graphs have lane
    members — that falls out of the data.
    """
    body = _body(_preset_svg(preset, flow))
    cards = _rects(body, "cardbg|herobg")

    # A channel runs along the MINOR axis, which is the one the flow does not
    # advance along: y flowing right, x flowing down. Reading it the other way
    # round is the very bug this guard exists to catch, so it is spelled out
    # here rather than inferred from the picture.
    def minor(p: tuple[float, float]) -> float:
        return p[0] if flow == "vertical" else p[1]

    for d in _wires(body):
        if "C " in d:  # relational bows are not channel routes
            continue
        legs = [leg for leg in _legs(d) if leg[0] != leg[1]]
        if len(legs) < 2:
            continue
        end = legs[-1][1]
        for box in cards:
            x0, y0, x1, y1 = box
            if not (x0 - 2 <= end[0] <= x1 + 2 and y0 - 2 <= end[1] <= y1 + 2):
                continue
            seat = minor(((x0 + x1) / 2, (y0 + y1) / 2))
            # Seated ON the channel: the route's TRAVEL leg — its longest, the
            # one that is the channel — holds a constant minor equal to the
            # sink's own. That is what a lane member IS: it left the rank grid
            # to park on the wire. Keyed to the travel leg and not to "some
            # leg", because a detour's final entry stub always lands on the
            # target's face centre and so always shares a coordinate with it.
            travel = max(legs, key=lambda leg: abs(leg[0][0] - leg[1][0]) + abs(leg[0][1] - leg[1][1]))
            if not (abs(minor(travel[0]) - minor(travel[1])) < 0.5 and abs(minor(travel[0]) - seat) < 1.5):
                continue
            assert d.count("Q ") == 1, (
                f"{preset}/{flow}: the sink is parked ON the channel, so the arrival is one corner — "
                f"got {d.count('Q ')} in {d}"
            )


# ── G4 · one point, one terminal ────────────────────────────────────────────


@pytest.mark.parametrize("preset", DAG_PRESETS)
@pytest.mark.parametrize("flow", FLOWS)
def test_one_point_draws_one_terminal(preset: str, flow: str) -> None:
    """A flush convergence collapses its arrivals onto one seat — that is the
    seating law. Stamping the chevron once per arrival at that one coordinate
    is N marks with no distinguishable extent, and it darkens under any
    non-opaque dress. Terminals differing in dress each keep their own mark,
    so this only ever catches true duplicates."""
    body = _body(_preset_svg(preset, flow))
    seen: dict[tuple[str, str], int] = {}
    for m in re.finditer(r'<path\b[^>]*\bd="(M[^"]+)"[^>]*class="([^"]*)"', body):
        if "-mk" not in m.group(2):
            continue
        key = (m.group(1), m.group(2))
        seen[key] = seen.get(key, 0) + 1
    dupes = {k: v for k, v in seen.items() if v > 1}
    assert not dupes, f"{preset}/{flow}: {len(dupes)} coincident terminal(s) stamped twice"


# ── G3 · the aspect-ratio stress case ───────────────────────────────────────


def _tall_chain() -> dict[str, Any]:
    """Five ranks, one member each — the narrowest legal vertical dag.

    It solves to **313 x 735, 2.35:1**, and the terms are worth writing down
    because the obvious arithmetic gives a different answer. A 5-rank canvas
    reads `header + 4*pitch + card + footer`, and the specimen's pitch is 250,
    which would put this at 1204 tall. It does not, and should not: the
    vertical flow gap derives from the CROSS-AXIS SPREAD its edges must bow
    through, and a one-member rank has no spread at all, so every gap here
    takes the floor (74) instead. A straight chain swimming in dead air is the
    defect that ratio was cited against — reaching 1204 would mean the gap had
    stopped deriving.

    2.35:1 against the specimen's 1.15:1 is double the separation, which is all
    this fixture needs: far enough that a transposed extent lands outside the
    canvas instead of looking merely odd. The fixture is a chain rather than a
    taller stack for the same reason it is 735 and not 1204: height bought by
    adding ranks would be height the gap law is not producing, and the stress
    this guard applies has to be the engine's own arithmetic."""
    ids = ("ingest", "parse", "score", "route", "emit")
    return {
        "topology": "dag",
        "orientation": "vertical",
        "title": "Tall chain",
        "subtitle": "five ranks, one member each",
        "nodes": [{"id": i, "label": i, "desc": "step"} for i in ids],
        "edges": [{"source": a, "target": b} for a, b in itertools.pairwise(ids)],
    }


def test_extreme_aspect_ratio_keeps_the_axes_apart() -> None:
    """At the specimen's near-square canvas the major and minor extents are
    close enough that an axis confusion renders as a plausible-looking error
    somebody has to eyeball. Force them 3:1 apart and the same bug becomes a
    blowout: ranks that advance across instead of down, or members that spread
    down instead of across, land outside the canvas immediately."""
    body = _body(_svg(_tall_chain()))
    cards = _rects(body, "cardbg|herobg")
    assert len(cards) == 5, cards

    vb = re.search(rf'viewBox="0 0 ({NUM}) ({NUM})"', _svg(_tall_chain()))
    assert vb is not None
    w, h = float(vb.group(1)), float(vb.group(2))
    assert h / w > 2.0, f"the stress fixture must stay far from square: {w}x{h}"

    centres = sorted(((y0 + y1) / 2, (x0 + x1) / 2) for x0, y0, x1, y1 in cards)
    ys = [c[0] for c in centres]
    xs = [c[1] for c in centres]
    assert ys == sorted(ys) and len(set(round(y) for y in ys)) == 5, "five ranks must advance DOWN, one per row"
    assert max(xs) - min(xs) < 1.0, "a one-member rank centres on the minor axis; the chain must not drift across"
    for x0, y0, x1, y1 in cards:
        assert x0 >= 0 and x1 <= w and y0 >= 0 and y1 <= h, f"card {(x0, y0, x1, y1)} escapes the {w}x{h} canvas"


def test_the_rank_cap_refuses_through_the_real_cli() -> None:
    """Guard Law: the cap is exercised where a caller meets it — the real
    parser, the real exit code, the literal sentence — not only through
    ``compute_diagram_layout``. Nine ranks is one past ``max_ranks: 8``."""
    ids = ("a", "b", "c", "d", "e", "f", "g", "h", "i")
    spec = {
        "topology": "dag",
        "orientation": "vertical",
        "title": "Too deep",
        "nodes": [{"id": i, "label": i} for i in ids],
        "edges": [{"source": p, "target": q} for p, q in itertools.pairwise(ids)],
    }
    res = CliRunner().invoke(app, ["compose", "diagram", "--spec", json.dumps(spec)])
    assert res.exit_code != 0, res.output
    assert "Traceback" not in res.output, res.output
    assert "rank" in res.output.lower(), res.output


# ── G5 · no chip reservation without a chip ─────────────────────────────────


def _plated_labels(body: str) -> list[str]:
    """The label texts that render inside a chip plate — a DRAWN pill.

    A chip plate is a ``-chipbg`` rect immediately followed by its ``-tag``
    text, so the plated set reads straight off the markup. A declared chip
    missing from it was demoted to a micro-label beside the wire."""
    return [m.group(1).strip() for m in re.finditer(r'<rect\b[^>]*-chipbg"/>\s*<text\b[^>]*>([^<]*)</text>', body)]


def _demoted_chips(spec: dict[str, Any], body: str) -> list[int]:
    """Indices of edges that DECLARE a chip and do not draw one."""
    plated = _plated_labels(body)
    out: list[int] = []
    for i, edge in enumerate(spec.get("edges", [])):
        label = (edge.get("label") or "").strip()
        if edge.get("label_style") != "chip" or not label:
            continue
        # Chip text can be truncated to fit its plate, so match on a prefix
        # rather than equality — a truncated pill is still a drawn pill.
        hit = next((p for p in plated if p == label or (p and label.startswith(p.rstrip("\u2026")))), None)
        if hit is None:
            out.append(i)
        else:
            plated.remove(hit)
    return out


@pytest.mark.parametrize("preset", DAG_PRESETS)
@pytest.mark.parametrize("flow", FLOWS)
def test_a_gap_reserves_run_only_for_chips_it_draws(preset: str, flow: str) -> None:
    """A rank gap widens so a chip can ride the run between two cards. A chip
    whose edge bends past ``chip_bend_max_dy`` never rides it — the label hands
    off the wire and renders as a micro-label — so a gap sized for its pill
    books width that nothing occupies. order-event-dlq held 219px gaps for a
    `dead letter` pill it does not draw: 277px of dead canvas and a gap:card
    ratio of 1.37 against the horizontal specimen's 0.90.

    **The control is per-chip, not all-or-nothing.** Baring EVERY chip is only
    a comparable control on a graph where every chip was demoted anyway; the
    first cut did that and skipped 24 of 38 cells, which is to say it skipped
    every graph with a surviving pill — the majority, and the interesting half.
    So the control bares exactly the chips this render DEMOTED, read back off
    the markup. Those contribute nothing to the page, so removing them must
    change nothing about the canvas. It names no demotion rule, so a future one
    is covered too, and it never skips."""
    spec = _preset_spec(preset, flow)
    declared = _svg(spec)
    demoted = _demoted_chips(spec, _body(declared))
    if not demoted:
        return  # nothing was demoted here; there is no phantom reservation to make

    control_spec = copy.deepcopy(spec)
    for i in demoted:
        control_spec["edges"][i].pop("label_style", None)
    control = _svg(control_spec)

    box = re.compile(r'viewBox="0 0 (' + NUM + r") (" + NUM + r')"')
    got, want = box.search(declared), box.search(control)
    assert got is not None and want is not None
    names = ", ".join(repr(spec["edges"][i].get("label")) for i in demoted)
    assert got.group(0) == want.group(0), (
        f"{preset}/{flow}: {got.group(1)}x{got.group(2)} declared vs {want.group(1)}x{want.group(2)} with "
        f"the demoted chip(s) {names} bared — the gap reserved run for a pill it does not draw"
    )
    assert _plated_labels(_body(control)) == _plated_labels(_body(declared)), (
        f"{preset}/{flow}: baring the demoted chip(s) {names} changed which pills are drawn; the control is not one"
    )
