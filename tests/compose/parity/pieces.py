"""Geometric piece census over parsed SVG facts.

Detection is geometry-first (dimensions, dashes, concentricity, motion) with
narrow class *hints* only where two vocabularies draw the same piece with
different mechanisms (specimens use ``marker-end``; the engine draws chevron
paths with a ``-mk`` class). The same detector runs on hand-authored
specimens and engine renders so a census diff means a piece diff, not a
vocabulary diff.
"""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .svgfacts import _ARITY, _CMD, _NUM

if TYPE_CHECKING:
    from .svgfacts import Circle, Facts, PathEl, Rect, TextEl

# Piece-geometry windows (from the kit specimen sheet and the engine chassis):
# chips are 26-tall rx8 pills; cards are >=36-tall rx>=10 boxes (pill nodes
# reach rx=h/2); gather knots are r5 ring + r2.5 core; terminal dots r2.3.
_CHIP_H = (22.0, 30.0)
_CHIP_RX = (5.0, 11.0)
_CARD_MIN_W = 60.0
_CARD_MIN_H = 36.0
_CARD_MIN_RX = 10.0
_COIN_MIN_R = 16.0
_KNOT_RING_R = (4.0, 6.5)
_KNOT_CORE_R = (1.6, 3.4)
_DOT_R = (1.8, 2.8)
_EDGE_MIN_SPAN = 28.0

# Decor/glyph strokes that must never census as connectors: specimen glyph
# families (gi/gia/gf/gm/mgi/hgi/hg ink strokes) and drawn terminals.
_GLYPH_DECOR_HINTS = ("-light", "-gi", "-gia", "-gf", "-gm", "-mgi", "-hgi", "-hg")
# -ml/-elbl are the engine floats; -reqt/-respt are the specimen's reciprocal-
# lane request/response direction labels (gateway) — the same floating
# lane-label PIECE the engine renders as -elbl, so the census must count both
# (a vocabulary difference, never a piece difference).
_MICRO_LABEL_HINTS = ("-ml", "-elbl", "-reqt", "-respt")
_ARROW_PATH_HINTS = ("-mk",)  # engine draws terminals as filled paths
# Chrome furniture drawn with edge vocabulary: the sequence time-axis is an
# arrowed stub on both sides (specimen ``seq-taxis`` marker-end, engine
# ``-taxis``/``-taxism`` drawn chevron) — never a relation.
_FURNITURE_HINTS = ("taxis",)


@dataclass(slots=True)
class Census:
    cards: int = 0
    card_rx: float = 0.0
    hero_rx: float = 0.0
    zone_headers: int = 0
    glyph_marks: int = 0
    desc_lines: int = 0
    shell_marks: int = 0
    hero_cards: int = 0
    muted_cards: int = 0
    coins: int = 0
    chips: int = 0
    gather_knots: int = 0
    terminal_dots: int = 0
    arrow_terminals: int = 0
    solid_edges: int = 0
    drift_edges: int = 0
    particles: int = 0
    micro_labels: int = 0
    animated: bool = False

    def as_dict(self) -> dict[str, float | int | bool]:
        return {
            "cards": self.cards,
            "card_rx": self.card_rx,
            "hero_rx": self.hero_rx,
            "zone_headers": self.zone_headers,
            "glyph_marks": self.glyph_marks,
            "desc_lines": self.desc_lines,
            "shell_marks": self.shell_marks,
            "hero_cards": self.hero_cards,
            "muted_cards": self.muted_cards,
            "coins": self.coins,
            "chips": self.chips,
            "gather_knots": self.gather_knots,
            "terminal_dots": self.terminal_dots,
            "arrow_terminals": self.arrow_terminals,
            "solid_edges": self.solid_edges,
            "drift_edges": self.drift_edges,
            "particles": self.particles,
            "micro_labels": self.micro_labels,
            "animated": self.animated,
        }


def _span(p: PathEl) -> float:
    ends = p.endpoints()
    if ends is None:
        return 0.0
    (x1, y1), (x2, y2) = ends
    return max(abs(x2 - x1), abs(y2 - y1))


def is_plate(r: Rect, facts: Facts) -> bool:
    return r.w >= facts.vb_w * 0.9 and r.h >= facts.vb_h * 0.9


def is_chip(r: Rect) -> bool:
    return _CHIP_H[0] <= r.h <= _CHIP_H[1] and _CHIP_RX[0] <= r.rx <= _CHIP_RX[1] and r.w <= 170


def is_card(r: Rect, facts: Facts) -> bool:
    return (
        r.w >= _CARD_MIN_W and r.h >= _CARD_MIN_H and r.rx >= _CARD_MIN_RX and not is_plate(r, facts) and not is_chip(r)
    )


def _contains_concentric(outer: Rect, inner: Rect, tol: float = 8.0) -> bool:
    """``inner`` sits fully inside ``outer`` with (near-)shared center — the
    double-rect card signature (outer glow/ring + inner body), never a
    region panel holding offset members."""
    if inner.w >= outer.w or inner.h >= outer.h:
        return False
    if not (
        inner.x >= outer.x - 0.5
        and inner.y >= outer.y - 0.5
        and inner.x + inner.w <= outer.x + outer.w + 0.5
        and inner.y + inner.h <= outer.y + outer.h + 0.5
    ):
        return False
    dcx = (inner.x + inner.w / 2) - (outer.x + outer.w / 2)
    dcy = (inner.y + inner.h / 2) - (outer.y + outer.h / 2)
    return abs(dcx) <= tol and abs(dcy) <= tol


def shell_rects(facts: Facts) -> list[Rect]:
    """Concentric outer shells the card census coalesces away — the terminal
    double-ring and the compound enclosure (rx >= 17 in both vocabularies;
    cards stop at 16)."""
    cards = [r for r in facts.rects if is_card(r, facts)]
    shells: list[Rect] = []
    for i, outer in enumerate(cards):
        inside = [j for j in range(len(cards)) if j != i and _contains_concentric(outer, cards[j])]
        if len(inside) == 1 and outer.rx >= 17.0:
            shells.append(outer)
    return shells


def card_rects(facts: Facts) -> list[Rect]:
    """Card bodies. A card drawn as a concentric DOUBLE (outer glow/ring +
    inner body — agent-task-lifecycle's hero and failed cards, the engine's
    hero ring) censuses ONCE, as its body: the ornament is the same piece.
    Containment must be concentric and single — a comparison panel holding
    several offset cards is a region, not a double."""
    cards = [r for r in facts.rects if is_card(r, facts)]
    drop: set[int] = set()
    for i, outer in enumerate(cards):
        inside = [j for j in range(len(cards)) if j != i and _contains_concentric(outer, cards[j])]
        if len(inside) == 1:
            drop.add(i)  # keep the body, drop the ornament shell
    return [r for i, r in enumerate(cards) if i not in drop]


def chip_rects(facts: Facts) -> list[Rect]:
    return [r for r in facts.rects if is_chip(r)]


def coin_circles(facts: Facts) -> list[Circle]:
    return [c for c in facts.circles if c.r >= _COIN_MIN_R and not c.has_motion]


def edge_paths(facts: Facts) -> list[PathEl]:
    """Connector-like paths: classed, long enough to be a relation, not a
    decor overlay or a drawn terminal."""
    out: list[PathEl] = []
    for p in facts.paths:
        if not p.own_cls:
            continue  # glyph strokes inside classed <g> groups
        if any(h in p.own_cls for h in _GLYPH_DECOR_HINTS + _ARROW_PATH_HINTS + _FURNITURE_HINTS):
            continue
        if _span(p) < _EDGE_MIN_SPAN:
            continue
        out.append(p)
    return out


def _terminates_edge(p: PathEl, edge_ends: list[tuple[float, float]], tol: float = 14.0) -> bool:
    """A drawn terminal counts only when it sits at a qualifying edge's end —
    the symmetric twin of the specimen side, where ``marker-end`` counts only
    on paths that census as edges. A chevron on a legend sample stub or a
    furniture axis pairs to nothing and drops on both sides."""
    ends = p.endpoints()
    if ends is None:
        return False
    return any(abs(px - x) <= tol and abs(py - y) <= tol for px, py in ends for x, y in edge_ends)


def gather_knots(facts: Facts) -> list[tuple[Circle, Circle]]:
    rings = [c for c in facts.circles if _KNOT_RING_R[0] <= c.r <= _KNOT_RING_R[1]]
    cores = [c for c in facts.circles if _KNOT_CORE_R[0] <= c.r <= _KNOT_CORE_R[1] and not c.has_motion]
    knots: list[tuple[Circle, Circle]] = []
    for ring in rings:
        for core in cores:
            if abs(ring.cx - core.cx) <= 1.5 and abs(ring.cy - core.cy) <= 1.5:
                knots.append((ring, core))
                break
    return knots


def convergence_outer_chord_deg(facts: Facts) -> float | None:
    """The convergence fan-in's OUTERMOST spoke's approach-angle commitment
    (F1's census key): the chord/secant from a spoke's far (source) endpoint
    to the shared gather knot/mouth, in degrees off horizontal. Every
    s_curve_h control shares its endpoint's y, so the literal Bezier tangent
    is always flat (0deg) at both ends by construction — 'angle' here is the
    overall run, the reader's actual visual read of commitment
    (pp-gateway-refined.svg's own citation: 'Fan angle ~33deg,
    write-convergence ~18deg; both arrive horizontal' measures the SAME
    secant this function computes). None when no gather knot is present to
    measure from (a bare, ungathered fan-in has no shared mouth point)."""
    knots = gather_knots(facts)
    if not knots:
        return None
    ring, _core = knots[0]
    kx, ky = ring.cx, ring.cy
    best: float | None = None
    for p in edge_paths(facts):
        ends = p.endpoints()
        if ends is None:
            continue
        (x1, y1), (x2, y2) = ends
        d1, d2 = math.hypot(x1 - kx, y1 - ky), math.hypot(x2 - kx, y2 - ky)
        near, far = (d1, (x2, y2)) if d1 < d2 else (d2, (x1, y1))
        if near > 3.0:
            continue  # neither end touches the knot; not a fan-in spoke
        sx, sy = far
        run, rise = abs(kx - sx), abs(ky - sy)
        if run < 1.0:
            continue
        ang = math.degrees(math.atan2(rise, run))
        best = ang if best is None else max(best, ang)
    return best


# Lanes morphology marks (obi-engine): one small leading mark per card whose
# SHAPE + TONE names the archetype — never hue. Both vocabularies draw the same
# piece: specimen ``-mk``/``-mkr``/``-mkH``/``-mkx``, engine ``-idot``/``-mkr``/
# ``-mkx``. The KIND is the piece; the class family is the vocabulary. A hub's
# accent ring (``-mkH``) still reads as a ring SHAPE here — the accent TONE is a
# separate axis, pinned/reported apart from the category-by-shape census.
_MARK_R = (2.0, 6.0)
_MARK_PATH_SPAN = 12.0


def _mark_kind(cls: str, *, is_path: bool) -> str:
    toks = cls.split()
    tok = toks[-1].rsplit("-", 1)[-1].lower() if toks else ""
    if tok in ("mkr", "mkh"):
        return "ring"
    if tok == "mkx":
        return "disc-muted"
    if tok in ("idot", "mk"):
        return "diamond" if is_path else "disc"
    return ""


def lane_mark_kinds(facts: Facts) -> list[str]:
    """Per-card morphology mark kind, cards in reading order (band x, then row
    y). Each card's mark is the small mark-classed circle/path inside its box
    ('' when a card carries none). Position-robust: a leading-left or a
    corner mark both census by the SAME card, so the pin survives the mark's
    placement moving without a fixture edit."""
    kinds: list[str] = []
    for card in sorted(card_rects(facts), key=lambda r: (round(r.x), round(r.y))):
        kind = ""
        for circ in facts.circles:
            if circ.has_motion or not (_MARK_R[0] <= circ.r <= _MARK_R[1]):
                continue
            if card.x <= circ.cx <= card.x + card.w and card.y <= circ.cy <= card.y + card.h:
                kind = _mark_kind(circ.cls, is_path=False)
                if kind:
                    break
        if not kind:
            for p in facts.paths:
                ends = p.endpoints()
                if ends is None or _span(p) > _MARK_PATH_SPAN:
                    continue
                px, py = ends[0]
                if card.x <= px <= card.x + card.w and card.y <= py <= card.y + card.h:
                    kind = _mark_kind(p.own_cls or p.cls, is_path=True)
                    if kind:
                        break
        kinds.append(kind)
    return kinds


def _is_card_desc_cls(cls: str) -> bool:
    """A node-desc sub-line voice, both vocabularies: engine -ndesc/-mdesc/
    -hdesc, specimen -*desc/-*sub/-ns lane cards. The caller CARD-SCOPES this,
    which excludes the masthead subtitle and footer caption — they share the
    -sub/-cap voice but sit outside every card (document chrome, not a card
    desc)."""
    for tok in cls.split():
        suf = tok.rsplit("-", 1)[-1]
        if suf.endswith(("desc", "sub")) or suf == "ns":
            return True
    return False


def census(facts: Facts) -> Census:
    c = Census()
    # Structural-connector families: tree/tree-radial limbs are positional
    # furniture — position IS the relation (tree draws per-stub paths,
    # the mindmap draws grouped dendrograms; granularities differ) — and the
    # flywheel ring is ONE decorative orbit drawn at arbitrary arc
    # granularity (flywheel-orbit-*: the cycle is the piece, not its segments).
    # The edge-dress census does not track either family, on either side.
    topo = str(facts.root_attrs.get("data-hw-topology", ""))
    furniture_family = topo.startswith("tree") or topo == "flywheel"
    knots = gather_knots(facts)
    knot_members = {id(k[0]) for k in knots} | {id(k[1]) for k in knots}
    edges = edge_paths(facts)
    edge_ends: list[tuple[float, float]] = []
    for p in edges:
        ends = p.endpoints()
        if ends:
            edge_ends.extend(ends)

    for r in card_rects(facts):  # double-rects coalesced to their bodies
        c.cards += 1
        if "hero" in r.cls:
            c.hero_cards += 1
        if r.dashed:
            c.muted_cards += 1
    c.chips = len(chip_rects(facts))

    c.coins = len(coin_circles(facts))
    c.gather_knots = len(knots)

    marker_arrows = 0 if furniture_family else sum(1 for p in edges if p.marker_end)
    drawn_terminals = (
        []
        if furniture_family
        else [
            p for p in facts.paths if any(h in p.own_cls for h in _ARROW_PATH_HINTS) and _terminates_edge(p, edge_ends)
        ]
    )
    drawn_arrows = sum(1 for p in drawn_terminals if "L" in p.d.upper())
    drawn_dots = len(drawn_terminals) - drawn_arrows
    for circ in facts.circles:
        if circ.has_motion:
            c.particles += 1
            continue
        if id(circ) in knot_members:
            continue
        if _DOT_R[0] <= circ.r <= _DOT_R[1]:
            near_end = any(abs(circ.cx - x) <= 3.0 and abs(circ.cy - y) <= 3.0 for x, y in edge_ends)
            if near_end:
                c.terminal_dots += 1
    c.terminal_dots += drawn_dots

    # A drawn terminal is a filled -mk path: a polygon (has line segments) is
    # the chevron; an arc-only path is the terminal DOT (the engine draws
    # piece 2's dot as a tiny full-circle arc path).
    c.arrow_terminals = marker_arrows + drawn_arrows

    if not furniture_family:
        for p in edges:
            if p.dashed and p.animated:
                c.drift_edges += 1
            elif not p.dashed:
                c.solid_edges += 1

    # Micro-labels: the engine's -ml/-elbl floats, plus the specimen
    # vocabulary's FLOATING chip-voice runs (service-dependencies classes its bare
    # edge labels ``chipt``) — a chipt INSIDE a chip rect is chip text, not a
    # label, so containment disambiguates the two roles.
    chips_boxes = chip_rects(facts)

    def _in_chip(tx: float, ty: float) -> bool:
        return any(cb.x <= tx <= cb.x + cb.w and cb.y - 2 <= ty <= cb.y + cb.h + 2 for cb in chips_boxes)

    c.micro_labels = sum(
        1
        for t in facts.texts
        if t.content and (any(h in t.cls for h in _MICRO_LABEL_HINTS) or ("chipt" in t.cls and not _in_chip(t.x, t.y)))
    )
    # MATERIAL census — what the cards are made of, not just how many:
    # the rx family (a pill is rx=h/2, a glyph card is 12-16), the identity
    # marks, the desc sub-lines, and the shell aspects (double-ring +
    # enclosure). These are what "looks like the specimen" means.
    bodies = card_rects(facts)
    if bodies:
        rxs = sorted(r.rx for r in bodies)
        c.card_rx = rxs[len(rxs) // 2]
        hero_rxs = sorted(r.rx for r in bodies if "hero" in r.cls)
        if hero_rxs:
            c.hero_rx = hero_rxs[len(hero_rxs) // 2]
    c.glyph_marks = sum(1 for g in facts.glyph_groups if "-in" not in g.own_cls)
    # Desc coverage: DISTINCT cards carrying >=1 node-desc sub-line — a WRAP-
    # robust count (a desc wrapping to two lines is ONE covered card, matching a
    # single-line specimen desc). Card-scoping excludes the masthead subtitle and
    # footer caption (document chrome sharing the -sub/-cap voice but sitting
    # outside every card), fixing the old run-count that conflated them with card
    # descs AND missed the specimen's lane-card voice (-ns).
    c.desc_lines = sum(
        1
        for card in bodies
        if any(
            t.content
            and _is_card_desc_cls(t.cls)
            and card.x - 1 <= t.x <= card.x + card.w + 1
            and card.y - 3 <= t.y <= card.y + card.h + 5
            for t in facts.texts
        )
    )
    c.shell_marks = len(shell_rects(facts))
    # Zone headers: the small-caps tracked labels naming structural sides —
    # class family "zone" in both vocabularies (specimen -zone runs, engine
    # zoneh/zoneha).
    c.zone_headers = sum(1 for t in facts.texts if "zone" in t.cls and t.content)
    c.animated = facts.animated
    return c


def content_bbox(facts: Facts) -> tuple[float, float, float, float] | None:
    """Extent of node-level content (cards + coins): the occupancy basis."""
    xs: list[float] = []
    ys: list[float] = []
    for r in card_rects(facts):
        xs.extend((r.x, r.x + r.w))
        ys.extend((r.y, r.y + r.h))
    for circ in coin_circles(facts):
        xs.extend((circ.cx - circ.r, circ.cx + circ.r))
        ys.extend((circ.cy - circ.r, circ.cy + circ.r))
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


# ── plate anchors ────────────────────────────────────────────────────────────

# Chrome text never counts as content ink: zone headers (the hand files'
# "kicker"), the caption sentence, legend rows (they ride the chrome bands
# and FOLLOW the caption — counting them as content couples the caption gap
# to itself and the tree calibration never converges), and footer/brand
# lines. Everything else with a baseline is content (names, descs, chips,
# micro-labels, outboard ring labels).
_CHROME_TEXT_TOKENS = ("zone", "kick", "cap", "leg", "-key", "-ft", "brand")


def _is_chrome_text(t: TextEl) -> bool:
    cls = t.cls.lower()
    return any(tok in cls for tok in _CHROME_TEXT_TOKENS)


def _sampled_points(d: str, per_curve: int = 24) -> list[tuple[float, float]]:
    """On-curve samples for distance checks — ``_path_points`` collects only
    command endpoints (a lens bow yields two points; a chip at its belly
    would measure the full sag as 'distance to wire'). Subdivides C/Q
    segments; every other command falls back to its endpoint."""
    pts: list[tuple[float, float]] = []
    cx = cy = 0.0
    start = (0.0, 0.0)
    for m in _CMD.finditer(d):
        letter = m.group(1)
        cmd = letter.upper()
        rel = letter.islower()
        nums = [float(n) for n in _NUM.findall(m.group(2))]
        arity = _ARITY[cmd]
        if cmd == "Z":
            cx, cy = start
            pts.append((cx, cy))
            continue
        if arity == 0 or len(nums) < arity:
            continue
        for i in range(0, len(nums) - arity + 1, arity):
            seg = nums[i : i + arity]
            if cmd == "H":
                cx = cx + seg[0] if rel else seg[0]
                pts.append((cx, cy))
                continue
            if cmd == "V":
                cy = cy + seg[0] if rel else seg[0]
                pts.append((cx, cy))
                continue
            if cmd == "C" and len(seg) == 6:
                p0 = (cx, cy)
                if rel:
                    p1 = (cx + seg[0], cy + seg[1])
                    p2 = (cx + seg[2], cy + seg[3])
                    p3 = (cx + seg[4], cy + seg[5])
                else:
                    p1 = (seg[0], seg[1])
                    p2 = (seg[2], seg[3])
                    p3 = (seg[4], seg[5])
                for k in range(1, per_curve + 1):
                    t = k / per_curve
                    mt = 1 - t
                    pts.append(
                        (
                            mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0],
                            mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1],
                        )
                    )
                cx, cy = p3
                continue
            if cmd == "Q" and len(seg) == 4:
                p0 = (cx, cy)
                if rel:
                    p1 = (cx + seg[0], cy + seg[1])
                    p2 = (cx + seg[2], cy + seg[3])
                else:
                    p1 = (seg[0], seg[1])
                    p2 = (seg[2], seg[3])
                for k in range(1, per_curve + 1):
                    t = k / per_curve
                    mt = 1 - t
                    pts.append(
                        (
                            mt**2 * p0[0] + 2 * mt * t * p1[0] + t**2 * p2[0],
                            mt**2 * p0[1] + 2 * mt * t * p1[1] + t**2 * p2[1],
                        )
                    )
                cx, cy = p2
                continue
            if cmd == "A" and len(seg) == 7:
                # Endpoint → center parameterization (SVG F.6.5), sampled —
                # an unsampled arc leaves a two-point jump whose secant is a
                # garbage tangent (the sweep read self-loop chevrons 8° off
                # while the render was exact).
                rx_, ry_, rot, laf, swf = abs(seg[0]), abs(seg[1]), math.radians(seg[2]), seg[3], seg[4]
                ex = cx + seg[5] if rel else seg[5]
                ey = cy + seg[6] if rel else seg[6]
                if rx_ < 1e-9 or ry_ < 1e-9 or (abs(ex - cx) < 1e-9 and abs(ey - cy) < 1e-9):
                    cx, cy = ex, ey
                    pts.append((cx, cy))
                    continue
                cosr, sinr = math.cos(rot), math.sin(rot)
                dx2, dy2 = (cx - ex) / 2.0, (cy - ey) / 2.0
                x1p = cosr * dx2 + sinr * dy2
                y1p = -sinr * dx2 + cosr * dy2
                lam = (x1p / rx_) ** 2 + (y1p / ry_) ** 2
                if lam > 1.0:
                    s = math.sqrt(lam)
                    rx_, ry_ = rx_ * s, ry_ * s
                num = rx_**2 * ry_**2 - rx_**2 * y1p**2 - ry_**2 * x1p**2
                den = rx_**2 * y1p**2 + ry_**2 * x1p**2
                co = math.sqrt(max(num / den, 0.0)) * (-1.0 if laf == swf else 1.0)
                cxp, cyp = co * rx_ * y1p / ry_, -co * ry_ * x1p / rx_
                arc_cx = cosr * cxp - sinr * cyp + (cx + ex) / 2.0
                arc_cy = sinr * cxp + cosr * cyp + (cy + ey) / 2.0
                th1 = math.atan2((y1p - cyp) / ry_, (x1p - cxp) / rx_)
                th2 = math.atan2((-y1p - cyp) / ry_, (-x1p - cxp) / rx_)
                dth = th2 - th1
                if swf == 0 and dth > 0:
                    dth -= 2 * math.pi
                elif swf == 1 and dth < 0:
                    dth += 2 * math.pi
                for k in range(1, per_curve + 1):
                    th = th1 + dth * k / per_curve
                    pts.append(
                        (
                            arc_cx + rx_ * math.cos(th) * cosr - ry_ * math.sin(th) * sinr,
                            arc_cy + rx_ * math.cos(th) * sinr + ry_ * math.sin(th) * cosr,
                        )
                    )
                cx, cy = ex, ey
                continue
            x, y = seg[-2], seg[-1]
            cx = cx + x if rel else x
            cy = cy + y if rel else y
            if cmd == "M" and i == 0:
                start = (cx, cy)
            pts.append((cx, cy))
    return pts


def plate_anchors(facts: Facts) -> dict[str, float | None]:
    """The four vertical anchors the plate law grades: zone-header baseline,
    content ink top/bottom, caption baseline. Content ink = cards + coins +
    chips + connector runs + non-chrome text baselines (text extent modeled
    as baseline -12/+4 — the same convention the engine's label-expansion
    pass uses, so specimen and render measure identically)."""
    ys: list[float] = []
    for r in card_rects(facts):
        ys.extend((r.y, r.y + r.h))
    for circ in coin_circles(facts):
        ys.extend((circ.cy - circ.r, circ.cy + circ.r))
    for r in chip_rects(facts):
        ys.extend((r.y, r.y + r.h))
    for p in edge_paths(facts):
        ys.extend(py for _, py in _sampled_points(p.d))
    for t in facts.texts:
        if not _is_chrome_text(t):
            ys.extend((t.y - 12.0, t.y + 4.0))
    zone_ys = [t.y for t in facts.texts if "zone" in t.cls.lower() or "kick" in t.cls.lower()]
    cap_ys = [t.y for t in facts.texts if "cap" in t.cls.lower()]
    content_top = round(min(ys), 2) if ys else None
    # A zone-ish run BELOW the content top is a section label inside the
    # composition (the gateway sheets' mid-canvas tiers), never the plate
    # masthead — only an above-content kicker anchors the zone-air band.
    zone_y = None
    if zone_ys and content_top is not None and min(zone_ys) < content_top:
        zone_y = round(min(zone_ys), 2)
    return {
        "zone_y": zone_y,
        "content_top": content_top,
        "content_bottom": round(max(ys), 2) if ys else None,
        "caption_y": round(max(cap_ys), 2) if cap_ys else None,
    }


def caption_text(facts: Facts) -> str | None:
    """The caption sentence (bottommost cap-classed run), whitespace-normal."""
    caps = [t for t in facts.texts if "cap" in t.cls.lower()]
    if not caps:
        return None
    return " ".join(max(caps, key=lambda t: t.y).content.split())


def chip_homes(facts: Facts) -> dict[str, float | int] | None:
    """Chip placement census: every chip lives in one of its two legal homes
    — inside a card (the chip row) or threaded on a wire. Counts per home
    plus the worst on-wire seat offset (chip center to the nearest sampled
    connector point; curved runs legitimately float — the specimen's own
    worst offset IS the band renders are held to)."""
    chips = chip_rects(facts)
    if not chips:
        return None
    cards = card_rects(facts)
    wires = [_sampled_points(p.d) for p in edge_paths(facts)]
    in_card = 0
    offsets: list[float] = []
    for chip in chips:
        ccx, ccy = chip.x + chip.w / 2, chip.y + chip.h / 2
        if any(r.x - 0.5 <= ccx <= r.x + r.w + 0.5 and r.y - 0.5 <= ccy <= r.y + r.h + 0.5 for r in cards):
            in_card += 1
            continue
        best = None
        for pts in wires:
            # Point-to-SEGMENT over consecutive samples — a straight run
            # yields two points, and a chip threaded mid-run measures half
            # the span to its nearest ENDPOINT (alt1's start chip read
            # 99.4px while sitting dead on its wire).
            for (ax, ay), (bx, by) in itertools.pairwise(pts):
                vx, vy = bx - ax, by - ay
                l2 = vx * vx + vy * vy
                if l2 <= 1e-12:
                    d = math.hypot(ccx - ax, ccy - ay)
                else:
                    t = max(0.0, min(1.0, ((ccx - ax) * vx + (ccy - ay) * vy) / l2))
                    d = math.hypot(ccx - (ax + t * vx), ccy - (ay + t * vy))
                if best is None or d < best:
                    best = d
        if best is not None:
            offsets.append(best)
    out: dict[str, float | int] = {"in_card": in_card, "on_wire": len(chips) - in_card}
    if offsets:
        out["wire_offset_max"] = round(max(offsets), 2)
    return out


def _rect_boundary_dist(px: float, py: float, r: Rect) -> float:
    """Distance to the ROUNDED-rect boundary (rx-aware SDF): pills and card
    corners recede from the square bbox, and the engine anchors on the true
    silhouette - a square-corner law flagged correct pill-cap attachments
    as several px "inside". Shared by the port-flush law (laws.py) and the
    circle-hero outboard stack below — one boundary metric, both shapes."""
    rx = min(r.rx, r.w / 2, r.h / 2)
    cx, cy = r.x + r.w / 2, r.y + r.h / 2
    qx, qy = abs(px - cx) - (r.w / 2 - rx), abs(py - cy) - (r.h / 2 - rx)
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
    inside = min(max(qx, qy), 0.0)
    return abs(outside + inside - rx)


def _circle_boundary_dist(px: float, py: float, c: Circle) -> float:
    """Distance to a circle's rim — the circle twin of ``_rect_boundary_dist``."""
    return abs(math.hypot(px - c.cx, py - c.cy) - c.r)


@dataclass(frozen=True, slots=True)
class HeroFigure:
    """A hero-anatomy figure normalized across the two node vocabularies —
    card rect and glyph-circle (the hub topology's own default anatomy: the
    engine draws it ``herocirclebg`` in ``primer-content.j2``'s ``bg_cls``
    dispatch, e.g. diagram-data-hub-circles-pp.svg's ``dhc-hero``,
    diagram-flywheel-circles-pp.svg's ``fwc-hero``,
    diagram-frontier-handoff-pp-v2.svg's ``fh2-hero``). For a circle, the
    box is its bounding square (x=cx-r, y=cy-r, w=h=2r) — so a dims law
    written against ``w``/``h`` grades diameter-vs-diameter through the
    SAME comparison it already runs for a card hero, no anatomy branch
    needed at the call site."""

    x: float
    y: float
    w: float
    h: float
    is_circle: bool

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def hero_figures(facts: Facts) -> list[HeroFigure]:
    """Every hero-classed figure in the document, card body first then
    circle — the convention every caller already relies on by taking
    ``[0]``. A hero circle is identified by the SAME class predicate as a
    hero card (``hero`` or ``hub`` substring): the engine's own background
    class is literally ``…-herocirclebg``, and every hand circle-hero
    specimen carries a plain ``*-hero`` class. ``coin_circles`` already
    holds every circle r>=16 (siblings and hero alike), so no separate
    hero-radius floor is needed."""
    out = [
        HeroFigure(x=r.x, y=r.y, w=r.w, h=r.h, is_circle=False)
        for r in card_rects(facts)
        if "hero" in r.cls.lower() or "hub" in r.cls.lower()
    ]
    out += [
        HeroFigure(x=c.cx - c.r, y=c.cy - c.r, w=2 * c.r, h=2 * c.r, is_circle=True)
        for c in coin_circles(facts)
        if "hero" in c.cls.lower() or "hub" in c.cls.lower()
    ]
    return out


def _is_hero_name_cls(cls: str) -> bool:
    """A hero crown's own name row, matched across dialects that never
    reconciled: the engine's ``hname`` (chrome.py's card-hero path sets
    ``name_cls = "hname" if role == "hero" else "name"``) and every hand
    file that follows suit, PLUS the bare ``-name``/``-dname`` suffix a
    hero box may carry instead — pp-dep-mesh-v2.svg's hero draws its "core"
    label in the specimen's own ``msh-dname`` class, never reconciled with
    the ``.msh-hname`` rule its stylesheet also defines but never applies.
    Geometric containment (the caller's ``inside()``) already scopes the
    search to THIS hero's own box, so any name-voice row found there is
    unambiguously its own — the suffix only needs to rule OUT a sub/desc
    line, not identify the owner."""
    return any(tok.rsplit("-", 1)[-1].endswith("name") for tok in cls.split())


# Empirically calibrated against every corpus specimen carrying >=3 payload
# nodes and a hero (see hub_seats' docstring for the full survey): the true
# polar-hub cluster (config-radial-circles, frame-engine-hub, hub-panel-
# orchestrator, pp-verb-ontology, verb-reads) spans 181-283° of arc at a
# 1.07-1.73x radius ratio; every directional composition (convergence x2,
# parity-beam, axial, cicd-machine, and frontier-handoff's line-of-three
# false-positive risk) fails one or both floors — frontier-handoff is the
# tight one, passing the span floor at 162.5° and excluded on ratio alone
# (1.95x). The ceiling sits at 1.90, not the corpus's own 1.73x max: the
# "hub" preset's engine render (pp-verb-ontology's ink-solved satellite
# family, narrower than this specimen's own now-superseded wide-floor
# cards — see hub.json's dims_superseded) measured 1.82x once its N/S
# satellites stopped carrying a card-position nudge that used to inflate
# their throw (see axial.py's solve_axial), and 1.89x once its crown took
# the hand file's own 280x120 citation (the wider crown pushes the W throw
# +25 while N/S tighten ~9; the seats themselves stay inside the ±6% law
# band) — still 0.06x clear of frontier-handoff's 1.95x false-positive.
_HUB_ANGULAR_SPAN_MIN = 150.0
_HUB_RADIUS_RATIO_MAX = 1.90


def hub_seats(facts: Facts) -> list[dict[str, float | str]] | None:
    """Satellite seat geometry for hub compositions: per non-hero node, the
    polar seat of its NAME run relative to the hero's center — the census
    that grades arrival axis and spread (a render that compresses the throw
    or verticalizes the seats fails here, whatever its sag looks like).

    Entry is geometry-first, not a topology-string allowlist: the engine's
    radial-fan dialect for config-radial-circles declares ``topology:
    "fanout"`` with ``orientation: "radial"`` — no "hub" substring
    anywhere — while the hand specimen's own payload says "radial-hub", and
    pp-verb-ontology.svg (the hub fixture) declares "axial". A topology
    string can never keep up with every dialect a preset invents, so this
    measures the candidate seats it already computes instead: a genuine
    polar hub surrounds its hero across a wide arc at a roughly consistent
    radius (a ring); a directional fan-in/pipeline/state-machine's
    "satellites" approach from one narrow wedge instead. See
    ``_HUB_ANGULAR_SPAN_MIN``/``_HUB_RADIUS_RATIO_MAX`` for the measured
    corpus bands these floors sit between."""
    spec = (facts.payload or {}).get("spec") if isinstance(facts.payload, dict) else None
    if not isinstance(spec, dict):
        return None
    # Three payload dialects declare the same composition: engine specs
    # (node dicts, role=hero), hp2 (node dicts with id/quadrant, hero under
    # a ``hub`` dict), fe2 (bare node-id strings, hero as a ``hub`` string).
    raw_nodes = spec.get("nodes") or []
    labels: list[str] = []
    for n in raw_nodes:
        if isinstance(n, dict):
            labels.append(str(n.get("label") or n.get("id") or ""))
        else:
            labels.append(str(n))
    if len(labels) < 3:
        return None
    hub_field = spec.get("hub")
    hub_id = str(hub_field.get("id") if isinstance(hub_field, dict) else (hub_field or ""))
    hero_labels = {hub_id.lower()} if hub_id else set()
    for n in raw_nodes:
        if isinstance(n, dict) and n.get("role") == "hero":
            hero_labels.add(str(n.get("label") or n.get("id") or "").lower())
    heroes = hero_figures(facts)
    if not heroes:
        return None
    hcx, hcy = heroes[0].cx, heroes[0].cy
    seats: list[dict[str, float | str]] = []
    for label in labels:
        if not label or label.lower() in hero_labels:
            continue
        runs = [t for t in facts.texts if t.content.lower() == label.lower() and "name" in t.cls.lower()]
        if not runs:
            continue
        t = runs[0]
        seats.append(
            {
                "label": label,
                "angle": round(math.degrees(math.atan2(t.y - hcy, t.x - hcx)), 1),
                "dist": round(math.hypot(t.x - hcx, t.y - hcy), 1),
            }
        )
    if len(seats) < 3:
        return None
    dists = [float(s["dist"]) for s in seats]
    angles = sorted(float(s["angle"]) for s in seats)
    n_seats = len(angles)
    gaps = [(angles[(i + 1) % n_seats] - angles[i]) % 360.0 for i in range(n_seats)]
    span = 360.0 - max(gaps)
    ratio = max(dists) / max(min(dists), 1.0)
    if span < _HUB_ANGULAR_SPAN_MIN or ratio > _HUB_RADIUS_RATIO_MAX:
        return None  # a directional fan/convergence/pipeline, not a polar hub
    return seats


_RING_ARC_RE = re.compile(
    r"M\s*([\d.-]+)[, ]([\d.-]+)\s*A\s*([\d.]+)[, ]([\d.]+)"
    r"\s+([\d.]+)\s+([01])[, ]?([01])[, ]?\s*([\d.-]+)[, ]([\d.-]+)"
)


def ring_arc_spans(facts: Facts) -> list[float] | None:
    """Sorted angular spans of a ring's connector arcs (A-commands riding
    the dominant ring radius about the medallion centroid). The double-
    counted clearance bug rendered every span at 15.2° while the hand file
    holds 34° — spans are the composition, so they census."""
    big = [c for c in facts.circles if c.r >= 30]
    if len(big) < 3:
        return None
    cx = sum(c.cx for c in big) / len(big)
    cy = sum(c.cy for c in big) / len(big)
    ring_r = sum(math.hypot(c.cx - cx, c.cy - cy) for c in big) / len(big)
    if ring_r < 60:
        return None
    spans: list[float] = []
    for p in facts.paths:
        m = _RING_ARC_RE.search(p.d)
        if not m:
            continue
        x0, y0, rx, _ry, _rot, _laf, sw, x1, y1 = map(float, m.groups())
        if abs(rx - ring_r) > 6.0:
            continue
        a0 = math.degrees(math.atan2(y0 - cy, x0 - cx))
        a1 = math.degrees(math.atan2(y1 - cy, x1 - cx))
        span = (a1 - a0) % 360.0 if sw == 1 else (a0 - a1) % 360.0
        spans.append(round(span, 1))
    return sorted(spans) or None


def hero_stack(facts: Facts) -> dict[str, int] | None:
    """The hero crown's STACK COMPOSITION — which text rows belong to the
    hero (name runs, desc/sub lines). Dims laws graded the box while
    nothing graded what the stack CONTAINS; a hero that grows or drops a
    row re-rhythms the whole crown invisibly. Glyph presence is not
    measurable from Facts (glyph groups carry no coordinates) — rows only.

    A CARD hero holds its stack INSIDE the box (bbox containment), matched
    by name/sub class family — see ``_is_hero_name_cls``.

    A CIRCLE hero holds its stack OUTBOARD instead: "a circle holds a
    glyph well and a word badly" (diagram-data-hub-circles-pp.svg's own
    hw:tradeoffs) so every circle-hero specimen measured
    (diagram-data-hub-circles-pp.svg, diagram-flywheel-circles-pp.svg,
    diagram-frontier-handoff-pp-v2.svg) parks the name/sub runs beyond the
    rim instead. Two of those three don't even carry a distinct hero-name
    class — frontier-handoff's hero shares the plain ``fh2-name`` voice
    with its three siblings, and the engine draws every circle label
    generic (``clbl``/``name``/``ndesc``) regardless of hero-ness — so
    class family cannot own the assignment here. Geometry does instead:
    a text run belongs to the hero when the hero is its NEAREST node
    figure by boundary distance (rect SDF or circle rim, among every card
    and circle in the document), chip/chrome text excluded. Ordering the
    owned runs by that same distance reproduces the authored stack order
    in all three specimens (name nearest the rim, sub(s) further out) —
    the row closest to the silhouette is the name, the rest are subs."""
    heroes = hero_figures(facts)
    if not heroes:
        return None
    h = heroes[0]

    if not h.is_circle:

        def inside(t: TextEl) -> bool:
            return h.x <= t.x <= h.x + h.w and h.y <= t.y <= h.y + h.h

        cls_l = [t.cls.lower() for t in facts.texts if inside(t)]
        names = sum(1 for c in cls_l if _is_hero_name_cls(c))
        # One piece, two vocabularies: in-card chip text is the specimens'
        # ``-chipt`` and the engine's ``-tag`` (the tag voice) — count both.
        # ``_is_card_desc_cls`` covers the generic ``-sub``/``-desc``
        # families a hero shares with its non-hero siblings (kernel-
        # bottleneck's hero draws its sub row in ``msh-sub``, never a
        # hero-specific class) alongside the explicit ``hdesc``/``hsub``.
        subs = sum(1 for c in cls_l if _is_card_desc_cls(c) or "chipt" in c or "-tag" in c)
        if not names and not subs:
            return None
        return {"name_rows": names, "sub_rows": subs}

    # Circle hero: nearest-owner assignment among every node figure.
    hero_circles = [c for c in coin_circles(facts) if "hero" in c.cls.lower() or "hub" in c.cls.lower()]
    if not hero_circles:
        return None
    hc = hero_circles[0]
    cards = card_rects(facts)
    siblings = [c for c in coin_circles(facts) if c is not hc]
    rows: list[tuple[float, TextEl]] = []
    for t in facts.texts:
        if not t.content or _is_chrome_text(t):
            continue
        if any(h_ in t.cls.lower() for h_ in ("chipt", "-tag", "-ml", "-elbl")):
            continue  # chip pills and floating wire labels are a different census
        d_hero = _circle_boundary_dist(t.x, t.y, hc)
        d_other = min(
            [_rect_boundary_dist(t.x, t.y, r) for r in cards] + [_circle_boundary_dist(t.x, t.y, c) for c in siblings],
            default=math.inf,
        )
        if d_hero <= d_other:
            rows.append((d_hero, t))
    if not rows:
        return None
    rows.sort(key=lambda pair: pair[0])
    return {"name_rows": 1, "sub_rows": len(rows) - 1}


def payload_edge_pairs(facts: Facts) -> dict[str, str] | None:
    """The declared relation set from the artifact's own payload: source->
    target keys with their label (or "" when unlabeled). Reads both payload
    dialects — engine/spec ``edges`` (source/target/label) and the SM hand
    dialect ``transitions`` (from/to/guard). None when nothing declares."""
    spec = (facts.payload or {}).get("spec") if isinstance(facts.payload, dict) else None
    if not isinstance(spec, dict):
        return None
    raw = spec.get("edges") or spec.get("transitions") or []
    pairs: dict[str, str] = {}
    for e in raw:
        if not isinstance(e, dict):
            continue
        s = e.get("source") or e.get("from")
        t = e.get("target") or e.get("to")
        if not s or not t:
            continue
        label = e.get("label") or e.get("guard") or ""
        pairs[f"{s}->{t}"] = str(label)
    return pairs or None


# ── state-machine back edges ─────────────────────────────────────────────────
#
# Discovery is geometry-first, not payload-first: pp-state-machine-alt1.svg's
# hw:payload carries only a bare ``back_edge`` string (no per-transition
# list), so a role/kind field cannot be the trigger. Every SM specimen
# measured (pp-state-machine.svg, pp-state-machine-alt1.svg,
# pp-state-machine-alt2.svg) draws its forward chain as straight M/L runs
# and every return (retry, throw, revise, the executing self-loop) as a
# bezier bow — curvature is the dialect-free signal both a hand file and an
# engine render share regardless of what their payloads say. A self-loop
# (both ends nearest the SAME node figure) is excluded: agent-task-
# lifecycle's ``executing->executing`` tool-call loop is curved too, but
# the task list names only the routes BETWEEN two states.

_ACCENT_EDGE_SUFFIXES = ("acc", "fls")
_NEUTRAL_EDGE_SUFFIXES = ("sol", "conn", "connmuted")
# The corner-vs-single-face split: pp-state-machine.svg's retry edge leaves
# the failed card's bottom-left corner at (629,407) — left face 4.0px, bottom
# face 4.0px, an exact tie. The smallest true single-face gap measured
# anywhere in the SM corpus is 31px (pp-state-machine-alt2.svg's retry: top
# 0px vs left 31px) — 10px sits well above the corner tie and well below
# every single-face gap.
_CORNER_BAND_PX = 10.0


def _rect_face_dists(px: float, py: float, r: Rect) -> dict[str, float]:
    """Point-to-FACE-SEGMENT distance for each of a rect's four sides — the
    basis for exit-side classification (which face a path's endpoint left
    from), never the corner-blind point-to-infinite-line distance."""
    x0, y0, x1, y1 = r.x, r.y, r.x + r.w, r.y + r.h

    def seg(ax: float, ay: float, bx: float, by: float) -> float:
        vx, vy = bx - ax, by - ay
        l2 = vx * vx + vy * vy
        t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / l2)) if l2 > 1e-9 else 0.0
        return math.hypot(px - (ax + t * vx), py - (ay + t * vy))

    return {
        "left": seg(x0, y0, x0, y1),
        "right": seg(x1, y0, x1, y1),
        "top": seg(x0, y0, x1, y0),
        "bottom": seg(x0, y1, x1, y1),
    }


def _exit_side(px: float, py: float, r: Rect) -> str:
    ordered = sorted(_rect_face_dists(px, py, r).items(), key=lambda kv: kv[1])
    (face0, d0), (_face1, d1) = ordered[0], ordered[1]
    return "corner" if d1 - d0 <= _CORNER_BAND_PX else face0


def _chord_deviation(pts: list[tuple[float, float]], p0: tuple[float, float], p1: tuple[float, float]) -> float:
    """Max perpendicular distance from any sampled point to the straight
    chord p0->p1 — how far the route bows off the direct line."""
    vx, vy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(vx, vy)
    if length < 1e-9:
        return 0.0
    return max(abs((x - p0[0]) * vy - (y - p0[1]) * vx) / length for x, y in pts)


def _cubic_control_points(
    d: str,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]] | None:
    """(P0, P1, P2, P3) for a single ``M sx,sy C c1x,c1y c2x,c2y ex,ey`` path
    — the state-machine return convention both the hand specimens and
    ``graph.py``'s back-edge branch emit (one M + one C, 8 numbers total).
    The same positional 8-number parse ``test_diagram_layout.py``'s own
    ``_cubic`` uses, so the fixture extractor and the engine property tests
    grade the identical geometry through one method, never two."""
    if "C" not in d.upper():
        return None
    nums = [float(x) for x in _NUM.findall(d)]
    if len(nums) < 8:
        return None
    return (nums[0], nums[1]), (nums[2], nums[3]), (nums[4], nums[5]), (nums[6], nums[7])


def _arrival_angle(d: str) -> float | None:
    """Angle off HORIZONTAL (0=flat, 90=vertical) the curve strikes its
    endpoint — the analytic tangent at t=1, direction (P3-P2), matching
    ``test_diagram_layout.py``'s own ``_arrival_deg``
    (``atan2(abs(dy), abs(dx))``) so a hand specimen and an engine render
    grade through the identical formula. A back-edge's own P2 sits BELOW
    (same or greater y) its endpoint in every specimen measured, so this
    reduces to the tangent's steepness, never its left/right sense —
    exactly what the construction law (corner-basin=vertical, recovery-
    climb=~71°, same-row=~24°) is stated in terms of."""
    cub = _cubic_control_points(d)
    if cub is None:
        return None
    _p0, _p1, p2, p3 = cub
    dx, dy = p3[0] - p2[0], p3[1] - p2[1]
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    return round(math.degrees(math.atan2(abs(dy), abs(dx))), 1)


def _belly_x(pts: list[tuple[float, float]], x0: float, y0: float, x1: float, y1: float) -> float | None:
    """Normalized position (0=source exit, 1=target entry) of the x at the
    curve's deepest (max-y) sampled point, along its OWN start->end x-span —
    the same landmark ``graph.py``'s ``_under_curve_depth`` computes as
    ``belly_x`` (``max(pts, key=lambda pq: pq[1])[0]``), but expressed
    scale-invariantly: a hand specimen (1240 viewBox) and its engine preset
    (content-sized to its own, much smaller, canvas — cicd-machine solves to
    ~923px) never share an absolute coordinate system, so the raw px the
    solver uses internally for label seating cannot double as a cross-scale
    fixture value (measured miss: specimen 482px vs render 310px on
    entirely different canvases, a false "171px off" that a same-diagram
    proportion check reads as within a few percent). Only a GENUINE
    interior belly earns a value: a monotonic climb (the recovery-climb
    archetype, e.g. alt2's retry) has its "deepest" point AT an endpoint,
    not a true dip — the null there is the signal that this archetype's
    construction has no belly to hang a label or a caption-clearance check
    off, not a measurement failure."""
    deepest = max(pts, key=lambda pq: pq[1])
    if deepest[1] <= max(y0, y1) + 2.0:
        return None
    span = x1 - x0
    if abs(span) < 1e-6:
        return None
    return round((deepest[0] - x0) / span, 3)


def _is_curved(p: PathEl) -> bool:
    return "C" in p.d.upper() or "A" in p.d.upper()


def _return_edges(facts: Facts) -> list[PathEl]:
    """Non-self-loop curved connectors — the state-machine return family
    (back/down edges). Topology-gated: "curved connector between two
    different cards" is common well outside state machines (router/DAG
    presets curve around obstacles too — an early cut of this discovery
    with no gate populated 24 unrelated fixtures), so this only fires on
    ``data-hw-topology="state-machine"``, the value both every hand SM
    specimen and its engine preset declare. Rect-scoped: every state in
    the three SM specimens is a card, never a circle, so face-based
    exit-side has a real silhouette to grade against — a circle-state SM
    would need its own hand specimen before this discovery earns a circle
    branch (standing law: no idiom ships ungrounded in a specimen)."""
    if str(facts.root_attrs.get("data-hw-topology", "")) != "state-machine":
        return []
    cards = card_rects(facts)
    if not cards:
        return []
    out: list[PathEl] = []
    for p in edge_paths(facts):
        if not _is_curved(p):
            continue
        ends = p.endpoints()
        if not ends:
            continue
        (x0, y0), (x1, y1) = ends
        src = min(cards, key=lambda r: _rect_boundary_dist(x0, y0, r))
        tgt = min(cards, key=lambda r: _rect_boundary_dist(x1, y1, r))
        if src is tgt:
            continue  # a self-loop is not a route between two states
        out.append(p)
    return out


def _figure_name(facts: Facts, r: Rect) -> str:
    """The name-voice text seated inside a card — reuses
    ``_is_hero_name_cls``'s suffix family (name/hname/mname/dname all
    qualify) since a return edge's endpoint state is as often muted
    (``mname``) as it is a hero."""
    pad = 6.0
    for t in facts.texts:
        inside = r.x - pad <= t.x <= r.x + r.w + pad and r.y - pad <= t.y <= r.y + r.h + pad
        if t.content and inside and _is_hero_name_cls(t.cls.lower()):
            return t.content.strip()
    return ""


def back_edge_routes(facts: Facts) -> dict[str, dict[str, object]] | None:
    """Per return edge (key ``"source->target"``, names from the seated
    card text — the payload id vocabulary can't be relied on, see the
    module note): the source face the route LEAVES from (``exit_side``),
    how far it bows off the direct chord (``chord_dev``), its closest
    approach to every OTHER card on the canvas (``clearance``, ``None``
    when no third card exists to clear), the angle its tangent strikes the
    target at (``arrival_angle``, degrees off horizontal — see
    ``_arrival_angle``), and the x of its deepest excursion when it carries
    a genuine interior dip (``belly_x``, ``None`` for a monotonic
    recovery-climb — see ``_belly_x``). chord_dev and clearance alone
    passed the census dev bands while arrival angle and belly position
    still read wrong (a corner-basin return landing at 82° instead of
    exactly vertical, its belly dragged off-center) — bow depth and
    tangent direction are independent measurements; a route can bow the
    right AMOUNT while pointing the wrong way."""
    returns = _return_edges(facts)
    if not returns:
        return None
    cards = card_rects(facts)
    out: dict[str, dict[str, object]] = {}
    for p in returns:
        ends = p.endpoints()
        if not ends:
            continue
        (x0, y0), (x1, y1) = ends
        src = min(cards, key=lambda r: _rect_boundary_dist(x0, y0, r))
        tgt = min(cards, key=lambda r: _rect_boundary_dist(x1, y1, r))
        src_name, tgt_name = _figure_name(facts, src).lower(), _figure_name(facts, tgt).lower()
        if not src_name or not tgt_name:
            continue
        pts = _sampled_points(p.d)
        others = [r for r in cards if r is not src and r is not tgt]
        clearance = min((_rect_boundary_dist(x, y, r) for r in others for x, y in pts), default=None)
        out[f"{src_name}->{tgt_name}"] = {
            "exit_side": _exit_side(x0, y0, src),
            "chord_dev": round(_chord_deviation(pts, (x0, y0), (x1, y1)), 1),
            "clearance": round(clearance, 1) if clearance is not None else None,
            "arrival_angle": _arrival_angle(p.d),
            "belly_x": _belly_x(pts, x0, y0, x1, y1),
        }
    return out or None


def _edge_role(p: PathEl) -> str:
    """accent | neutral, resolved from the edge's OWN class family — the
    codebase's established role-by-suffix idiom (``law_chip_text_neutral``'s
    ``-flp\\d`` pattern is the same trick). Specimens paint their
    privileged path with an ``*-acc`` class, always the same hex
    (pp-state-machine.svg's ``ci1-acc``, pp-state-machine-alt1.svg's
    ``sm-acc``, pp-state-machine-alt2.svg's ``a2-acc``, all ``#2563EB``);
    the engine's flow palette draws the same role ``-fl0``.. or its no-index
    fallback ``-fls`` (primer-defs.j2: ``.{{uid}}-fls { stroke:
    var(--dna-signal); }``, the same accent token). Neutral is the
    muted-connector family both sides share: specimens' ``-sol``/``-conn``,
    the engine's ``-connmuted`` — and the kit's own documented default, so
    an edge matching neither family still reads neutral rather than
    raising."""
    for tok in p.own_cls.split():
        suf = tok.rsplit("-", 1)[-1]
        if suf in _ACCENT_EDGE_SUFFIXES or re.fullmatch(r"fl\d+", suf):
            return "accent"
    for tok in p.own_cls.split():
        suf = tok.rsplit("-", 1)[-1]
        if suf in _NEUTRAL_EDGE_SUFFIXES:
            return "neutral"
    return "neutral"


def edge_dress(facts: Facts) -> dict[str, dict[str, object]] | None:
    """Per return edge: its stroke ROLE (accent | neutral) and whether it
    is dashed — ``PathEl.dashed`` already resolves both the inline
    ``stroke-dasharray`` attribute and the CSS class family, so no
    reparsing is needed here."""
    returns = _return_edges(facts)
    if not returns:
        return None
    cards = card_rects(facts)
    out: dict[str, dict[str, object]] = {}
    for p in returns:
        ends = p.endpoints()
        if not ends:
            continue
        (x0, y0), (x1, y1) = ends
        src = min(cards, key=lambda r: _rect_boundary_dist(x0, y0, r))
        tgt = min(cards, key=lambda r: _rect_boundary_dist(x1, y1, r))
        src_name, tgt_name = _figure_name(facts, src).lower(), _figure_name(facts, tgt).lower()
        if not src_name or not tgt_name:
            continue
        out[f"{src_name}->{tgt_name}"] = {"role": _edge_role(p), "dashed": p.dashed}
    return out or None


# A label riding a return edge is drawn one of two ways across the corpus:
# a bare micro-label run (pp-state-machine.svg, pp-state-machine-alt2.svg,
# the engine's ``-ml``/``-elbl``) or a chip pill (pp-state-machine-alt1.svg's
# ``sm-chipt``, ridden by EVERY one of its transitions, forward and back
# alike) — the same floating-annotation piece, two vocabularies, exactly
# the ``_MICRO_LABEL_HINTS`` doctrine this module already applies elsewhere.
_EDGE_LABEL_HINTS = (*_MICRO_LABEL_HINTS, "chipt")


def _edge_label_candidates(facts: Facts) -> list[TextEl]:
    cards = card_rects(facts)

    def _in_a_card(t: TextEl) -> bool:
        return any(r.x - 2 <= t.x <= r.x + r.w + 2 and r.y - 2 <= t.y <= r.y + r.h + 2 for r in cards)

    return [
        t
        for t in facts.texts
        if t.content
        and not _is_chrome_text(t)
        and any(h in t.cls.lower() for h in _EDGE_LABEL_HINTS)
        and not _in_a_card(t)  # a chip tag INSIDE a card is a chip, not an edge label
    ]


def _dist_to_wire(t: TextEl, p: PathEl) -> float:
    pts = _sampled_points(p.d)
    return min((math.hypot(t.x - x, t.y - y) for x, y in pts), default=math.inf)


def label_seat(facts: Facts, label_text: str) -> dict[str, float] | None:
    """For a label matched by CONTENT (case-insensitive, e.g. ``"retry"``):
    its distance to its OWN return-edge wire (nearest among the curved,
    non-self-loop return family — ``_return_edges``) vs. its distance to
    the nearest wire in the WHOLE document (every connector, not just
    returns). The two must coincide — a label closer to a foreign wire
    than to its own has adopted the wrong route. Re-discovers "own wire"
    fresh from geometry on every call rather than trusting a stored
    identity, so the SAME function grades a hand specimen and an engine
    render — a routing bug that relocates the label is caught structurally,
    not by comparing against a cached association."""
    matches = [t for t in facts.texts if t.content.strip().lower() == label_text.lower()]
    if not matches:
        return None
    t = matches[0]
    returns = _return_edges(facts)
    all_edges = edge_paths(facts)
    if not returns or not all_edges:
        return None
    d_own = min((_dist_to_wire(t, p) for p in returns), default=math.inf)
    d_any = min((_dist_to_wire(t, p) for p in all_edges), default=math.inf)
    if d_own == math.inf or d_any == math.inf:
        return None
    return {"own": round(d_own, 2), "nearest_any": round(d_any, 2)}


def edge_label_seats(facts: Facts) -> dict[str, float] | None:
    """Every return edge's label, matched to its wire by proximity
    (``_edge_label_candidates`` narrows to the floating-annotation classes
    so a card's own name/desc text is never mistaken for an edge label),
    reduced to the ``label_seat`` fixture value: distance to its own wire."""
    returns = _return_edges(facts)
    if not returns:
        return None
    candidates = _edge_label_candidates(facts)
    if not candidates:
        return None
    out: dict[str, float] = {}
    for p in returns:
        pts = _sampled_points(p.d)
        if not pts:
            continue
        best: TextEl | None = None
        best_d = math.inf
        for t in candidates:
            d = min(math.hypot(t.x - x, t.y - y) for x, y in pts)
            if d < best_d:
                best_d, best = d, t
        if best is None:
            continue
        seat = label_seat(facts, best.content)
        if seat is not None:
            out[best.content.strip().lower()] = seat["own"]
    return out or None
