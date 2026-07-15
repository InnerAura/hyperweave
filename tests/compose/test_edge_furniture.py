"""Property tests for edge-furniture geometry.

Where ``test_specimen_parity`` pins each idiom against ONE hand-authored ground
truth, these pin the POLICIES across every GENERATED story
(``scripts/generate_diagram_galleries.py``): a chip on a curved edge rides its
true wire (not the chord), a fanout trunk sizes to its cargo, and no two
arrivals stack on one card edge. Specimen = one point; the policy = the whole
space (Specimen-Driven Development, standing law).
"""

from __future__ import annotations

import itertools
import math
import sys
from collections import defaultdict
from pathlib import Path

import pytest

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_paradigms
from hyperweave.core.models import ComposeSpec

from .parity.pieces import card_rects, chip_rects, edge_paths, gather_knots
from .parity.svgfacts import Facts, parse_svg

# The story specs live at the repo root (pytest only puts ``src`` on the path).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.generate_diagram_galleries import SECTIONS

# Bundled presets that exercise the arrival/cargo/curve policies but aren't
# topology stories (the dag fan-in family lives here, not in the readme).
_BUNDLED = (
    "scatter-gather",
    "service-dependencies",
    "dep-audit",
    "kernel-bottleneck",
    "model-gateway-tiers",
    "gateway-balanced",
    "convergence",
    "convergence-arrivals",
    "reverse-etl",
    "rag-pipeline",
    "artifact-roundtrip",
    "order-lifecycle",
)


def _all_stories() -> list[tuple[str, str, dict]]:
    out: list[tuple[str, str, dict]] = [(sid, topo, spec) for topo, stories in SECTIONS for sid, _desc, spec in stories]
    seen = {s[0] for s in out}
    for name in _BUNDLED:
        if name in seen:
            continue
        spec = dict(resolve_bundled_spec("diagram", name).value)
        out.append((name, str(spec.get("topology", "")), spec))
    return out


_STORIES = _all_stories()
_RENDER_CACHE: dict[str, Facts] = {}


def _facts(sid: str, spec: dict) -> Facts:
    if sid not in _RENDER_CACHE:
        cs = ComposeSpec(
            type="diagram", genome_id="primer", variant="porcelain", ground="opaque", palette="fixed", diagram=spec
        )
        _RENDER_CACHE[sid] = parse_svg(compose(cs).svg)
    return _RENDER_CACHE[sid]


# ── path sampling ────────────────────────────────────────────────────────────


def _sample_path(d: str, per_cubic: int = 24) -> list[tuple[float, float]]:
    """Absolute on-path points, sampling every cubic — the same coarse trace
    ``wiring.enrich_geos`` hands the annotate pass."""
    import re

    nums = [float(n) for n in re.findall(r"-?\d*\.?\d+(?:e[+-]?\d+)?", d)]
    letters = re.findall(r"[MLHVCSQTAZ]", d, re.I)
    pts: list[tuple[float, float]] = []
    vi = 0
    cur = (0.0, 0.0)
    for letter in letters:
        cmd = letter.upper()
        if cmd == "M" or cmd == "L":
            cur = (nums[vi], nums[vi + 1])
            pts.append(cur)
            vi += 2
        elif cmd == "H":
            cur = (nums[vi], cur[1])
            pts.append(cur)
            vi += 1
        elif cmd == "V":
            cur = (cur[0], nums[vi])
            pts.append(cur)
            vi += 1
        elif cmd == "C":
            c1 = (nums[vi], nums[vi + 1])
            c2 = (nums[vi + 2], nums[vi + 3])
            p3 = (nums[vi + 4], nums[vi + 5])
            for i in range(1, per_cubic + 1):
                t = i / per_cubic
                mt = 1 - t
                pts.append(
                    (
                        mt**3 * cur[0] + 3 * mt * mt * t * c1[0] + 3 * mt * t * t * c2[0] + t**3 * p3[0],
                        mt**3 * cur[1] + 3 * mt * mt * t * c1[1] + 3 * mt * t * t * c2[1] + t**3 * p3[1],
                    )
                )
            cur = p3
            vi += 6
        elif cmd == "Z":
            pass
    return pts


def _arc_midpoint(poly: list[tuple[float, float]]) -> tuple[float, float]:
    seglens = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in itertools.pairwise(poly)]
    half = sum(seglens) / 2
    acc = 0.0
    for (a, b), length in zip(itertools.pairwise(poly), seglens, strict=True):
        if length > 0 and acc + length >= half:
            t = (half - acc) / length
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        acc += length
    return poly[-1]


def _point_to_polyline(px: float, py: float, poly: list[tuple[float, float]]) -> float:
    best = math.inf
    for a, b in itertools.pairwise(poly):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / L2))
        cx, cy = a[0] + t * dx, a[1] + t * dy
        best = min(best, math.hypot(px - cx, py - cy))
    return best


def _edge_chips(facts: Facts) -> list:
    cards = card_rects(facts)
    return [
        ch
        for ch in chip_rects(facts)
        if not any(r.x - 2 <= ch.cx <= r.x + r.w + 2 and r.y - 2 <= ch.cy <= r.y + r.h + 2 for r in cards)
    ]


# ── Chips ride their true (curved) wire, not the chord ────────────────────────

CURVE_RIDE_EPS = 12.0
"""A chip riding a curved wire must sit within this of the true curve — the
roundtrip diff chip floated 125px off its under-arc at the chord midpoint."""


@pytest.mark.parametrize("sid,topo,spec", _STORIES, ids=[s[0] for s in _STORIES])
def test_chip_rides_curved_wire(sid: str, topo: str, spec: dict) -> None:
    """Every edge chip that sits at a curved edge's chord/arc midpoint (i.e. it
    RIDES that curve) lands within ε of the true curve, not its straight chord."""
    facts = _facts(sid, spec)
    curved = [_sample_path(p.d) for p in edge_paths(facts) if "C" in p.d.upper() and len(p.d) > 20]
    for ch in _edge_chips(facts):
        for poly in curved:
            if len(poly) < 2:
                continue
            chord_mid = ((poly[0][0] + poly[-1][0]) / 2, (poly[0][1] + poly[-1][1]) / 2)
            arc_mid = _arc_midpoint(poly)
            rides = (
                math.hypot(ch.cx - chord_mid[0], ch.cy - chord_mid[1]) < 15.0
                or math.hypot(ch.cx - arc_mid[0], ch.cy - arc_mid[1]) < 15.0
            )
            if rides:
                off = _point_to_polyline(ch.cx, ch.cy, poly)
                assert off < CURVE_RIDE_EPS, (
                    f"{sid}: edge chip at ({ch.cx:.0f},{ch.cy:.0f}) rides a curved wire but sits "
                    f"{off:.0f}px off it (>{CURVE_RIDE_EPS:g}) — chord-midpoint float, not on the curve"
                )


# ── Fanout depart-trunk sizes to its cargo ─────────────────────────────────────


def _hero_right_and_knot(facts: Facts) -> tuple[float, float, tuple[float, float]] | None:
    heroes = [r for r in card_rects(facts) if "hero" in r.cls]
    knots = gather_knots(facts)
    if not heroes or not knots:
        return None
    h = heroes[0]
    k = min((kr for kr, _ in knots), key=lambda kr: math.hypot(kr.cx - (h.x + h.w), kr.cy - (h.y + h.h / 2)))
    return h.x + h.w, h.y + h.h, (k.cx, k.cy)


_FANOUT_STORIES = [s for s in _STORIES if s[2].get("topology") == "fanout"]


@pytest.mark.parametrize("sid,topo,spec", _FANOUT_STORIES, ids=[s[0] for s in _FANOUT_STORIES])
def test_fanout_trunk_matches_cargo(sid: str, topo: str, spec: dict) -> None:
    """A fanout depart trunk carrying a route chip runs the full length; a
    chipless fan shrinks to the bare stub. Grades the discrimination directly:
    a chip trunk is measurably longer than a bare one of the same orientation."""
    orientation_early = spec.get("orientation", "horizontal")
    if orientation_early not in ("horizontal", "downward"):
        # Only the horizontal and downward fans OWN a depart trunk (the
        # specimen constants below exist for exactly those two); bilateral /
        # upward / radial fans leave the hero on bare spokes, and a glyph's
        # internal circles can false-positive the knot detector there.
        pytest.skip(f"{sid}: {orientation_early} fan has no depart trunk")
    facts = _facts(sid, spec)
    hk = _hero_right_and_knot(facts)
    if hk is None:
        pytest.skip(f"{sid}: no depart trunk (chipless short fan)")
    hero_right, hero_bottom, (kx, ky) = hk
    orientation = spec.get("orientation", "horizontal")
    trunk = abs(ky - hero_bottom) if orientation == "downward" else abs(kx - hero_right)
    # The cargo RULE is the pin; the lengths are the chassis' own facts
    # (depart_trunk specimen-cited, depart_trunk_bare the short-stub law) —
    # hardcoding 72/40 here made a lawful chassis change read as a failure.
    # Cargo = ANY trunk label (a chip needs its seat, a subsumed TEXT label
    # its float budget); only the truly unlabeled fan takes the short stub.
    has_cargo = any(e.get("label") for e in spec.get("edges", []))
    ch = load_paradigms()["primer"].diagram.topologies[
        "fanout-downward" if orientation == "downward" else "fanout-horizontal"
    ]
    want = float(ch.depart_trunk) if has_cargo else float(ch.depart_trunk_bare)
    assert abs(trunk - want) <= 3.0, (
        f"{sid}: {orientation} fanout trunk={trunk:.0f}px, expected {want:.0f} "
        f"({'cargo-bearing' if has_cargo else 'unlabeled'} cargo rule)"
    )


# ── Arrivals on a card edge stay ported apart ──────────────────────────────────

ARRIVAL_MIN_SEP = 12.0
# A deliberate flush convergence collapses its arrivals COINCIDENT onto one
# center mouth (the engine's _PORT_FLUSH tolerance); such a cluster is exempt
# like a gather knot. A 1-11px near-miss is still a spreading failure and fails.
_MOUTH_COINCIDENT = 3.0
_MOUTH_CENTER_TOL = 4.0
"""No two arrowhead tips within this of each other on one card edge (≈ arrowhead
width + margin) — dep-mesh seats 4 arrivals over 34px, ~11px apart."""
_FURNITURE = ("tree", "tree-radial", "flywheel", "mindmap", "radial", "hub")


def _card_side(px: float, py: float, r, tol: float = 6.0) -> str | None:
    for cond, side in (
        (abs(px - r.x) <= tol and r.y - tol <= py <= r.y + r.h + tol, "L"),
        (abs(px - (r.x + r.w)) <= tol and r.y - tol <= py <= r.y + r.h + tol, "R"),
        (abs(py - r.y) <= tol and r.x - tol <= px <= r.x + r.w + tol, "T"),
        (abs(py - (r.y + r.h)) <= tol and r.x - tol <= px <= r.x + r.w + tol, "B"),
    ):
        if cond:
            return side
    return None


@pytest.mark.parametrize("sid,topo,spec", _STORIES, ids=[s[0] for s in _STORIES])
def test_arrivals_stay_ported(sid: str, topo: str, spec: dict) -> None:
    """No two DISTINCT edges arrive within ε on the same card edge. A GATHER
    mouth is exempt — its converging edges collapse to a knot by design, so a
    cluster with a gather knot nearby is skipped."""
    if spec.get("topology") in _FURNITURE:
        pytest.skip(f"{sid}: furniture topology (position IS the relation)")
    facts = _facts(sid, spec)
    cards = card_rects(facts)
    knots = [(kr.cx, kr.cy) for kr, _ in gather_knots(facts)]
    arrivals: dict[tuple[int, str], list[tuple[float, float, str]]] = defaultdict(list)
    for p in edge_paths(facts):
        e = p.endpoints()
        if not e:
            continue
        px, py = e[-1]
        for ci, r in enumerate(cards):
            side = _card_side(px, py, r)
            if side:
                arrivals[(ci, side)].append((px, py, p.d[:26]))
                break
    for (ci, side), pts in arrivals.items():
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        if any(math.hypot(cx - kx, cy - ky) < 60 for kx, ky in knots):
            continue  # designed convergence to a gather mouth
        # Flush convergence (no gather ornament): a many-to-one collapse onto the
        # card's center mouth — service-dependencies auth/orders->postgres, the
        # tiers->cache/metrics sinks — lands its arrivals coincident there by
        # design. Exempt a cluster that collapses onto the center row; a partial
        # (1-11px) overlap is a spreading FAILURE and still fails below.
        r = cards[ci]
        spread = max((math.hypot(a[0] - b[0], a[1] - b[1]) for a in pts for b in pts), default=0.0)
        if spread <= _MOUTH_COINCIDENT and abs(cy - (r.y + r.h / 2)) <= _MOUTH_CENTER_TOL:
            continue  # designed convergence to the center mouth
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                if pts[i][2] == pts[j][2]:
                    continue
                sep = math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])
                assert sep >= ARRIVAL_MIN_SEP, (
                    f"{sid}: two arrivals {sep:.0f}px apart on card#{ci} edge {side} "
                    f"at ({pts[i][0]:.0f},{pts[i][1]:.0f}) — arrowheads overlap (<{ARRIVAL_MIN_SEP:g}px)"
                )
