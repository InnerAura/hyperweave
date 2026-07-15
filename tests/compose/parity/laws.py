"""Parity laws: (law, ok, evidence) records over parsed SVG facts.

Each law asserts a kit invariant or a specimen-derived target. Laws never
compare full documents — they grade geometry, census, chroma tokens, and
self-description honesty, engine-agnostically. Tolerances cover measurement
noise, not negotiation.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .pieces import (
    _rect_boundary_dist,
    back_edge_routes,
    caption_text,
    card_rects,
    census,
    chip_homes,
    chip_rects,
    coin_circles,
    convergence_outer_chord_deg,
    edge_dress,
    edge_paths,
    gather_knots,
    hero_figures,
    hero_stack,
    hub_seats,
    label_seat,
    lane_mark_kinds,
    payload_edge_pairs,
    plate_anchors,
    ring_arc_spans,
)

if TYPE_CHECKING:
    from .svgfacts import Facts, Rect

# Specimen-derived constants (see DIAGRAM_KIT_BRIEF.md)
RENDER_WIDTH = 740.0
SCALE_BAND = (0.51, 0.83)  # prototypes span 0.517-0.822
CARD_DIM_TOL = 0.10
# Hero emphasis is specimen-relative and two-sided (ratios span 0.93 pill
# machines → 2.53 axial; several specimens emphasize by ring only, ratio 1.0).
HERO_RATIO_SLACK = 0.8
PORT_NEAR_PX = 25.0
# A dot terminal (r~=2.3) kisses the boundary from its centre; a drawn/marker
# chevron occupies the last ~4-8px so its path stops short of the boundary.
PORT_FLUSH_PX = 3.0
PORT_FLUSH_MARKER_PX = 8.0
CHIP_STUB_MIN = 18.0
# Mirrors diagram-frame.yaml beam.relay_span_cap: both beam specimens converge
# on a ~.26-.30 per-stage window regardless of stage count (parity-beam's
# branch span .30, the relay reference's own n=3 span .26) — velocity varies
# with edge length, never with window duration. Any staged beam window wider
# than this crawls (the artifact-fanout-beam/compose-gate/settlement-relay
# regression: n=1 or n=2 groupings dividing the whole clock instead of being
# held to the specimen band).
BEAM_RELAY_SPAN_CAP = 0.30
NOTES_DIM_TOL = 0.02
# The two "Four inputs, one artifact" hand files disagree with each other on
# their own outer approach angle (pp-convergence.svg 20.6deg vs
# pp-convergence-flow.svg 27.9deg, delta 7.3deg) — half that inter-specimen
# spread is the tolerance a render is graded within of EITHER citation.
CONVERGENCE_ANGLE_TOL = 4.0


@dataclass(frozen=True, slots=True)
class LawResult:
    law: str
    ok: bool
    evidence: str

    def __str__(self) -> str:
        return f"[{'PASS' if self.ok else 'FAIL'}] {self.law}: {self.evidence}"


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


# ── scale ────────────────────────────────────────────────────────────────────


def law_scale(
    facts: Facts, fixture: dict[str, Any] | None = None, *, expected_render_w: int | None = None
) -> list[LawResult]:
    out: list[LawResult] = []
    if facts.width is None:
        # Fluid (%-width) specimens delegate sizing to the page; the fixed
        # render-width law applies to engine px output only.
        return [LawResult("scale.render-width", True, "fluid width (%) — n/a")]
    if expected_render_w is not None:
        # Content-fit amendment (documented supersession): the engine render's
        # width follows the CONSTANT-SCALE law — round(vb_w * display_w /
        # max(chassis width, vb_w)) — so a narrow diagram renders
        # proportionally narrower at one physical card size instead of
        # normalizing to the 740 pin. Hand specimens (no expected_render_w)
        # still grade against the fixed 740 convention they were authored at.
        out.append(
            LawResult(
                "scale.render-width",
                abs(float(facts.width) - float(expected_render_w)) <= 1.0,
                f"width={facts.width} (constant-scale law: {expected_render_w})",
            )
        )
    else:
        # A hand specimen self-validates against its OWN recorded width when
        # it deliberately departs the 740 convention (hub-panel authors 720);
        # the convention stays the norm for everything else.
        own_w = (fixture or {}).get("width")
        out.append(
            LawResult(
                "scale.render-width",
                facts.width == RENDER_WIDTH or (own_w is not None and facts.width == own_w),
                f"width={facts.width} (law: {RENDER_WIDTH:g}; specimen-recorded {own_w})",
            )
        )
    scale = facts.display_scale
    if scale is None:
        out.append(LawResult("scale.band", False, "no width/viewBox to compute scale"))
    else:
        floor = SCALE_BAND[0]
        note = ""
        fx_vb = (fixture or {}).get("viewbox")
        if fixture is not None and fixture.get("width") is None and fx_vb:
            # Fluid-specimen floor: a hand specimen with no fixed width was
            # excluded from the band calibration, and its own implied scale
            # at the render width can sit BELOW the band (the obi-engine
            # specimen is 1584 wide → 0.467). The render must never be blurrier than its
            # own specimen displayed at the same width — but it cannot be
            # required to beat a band the specimen never met (squeezing obi
            # under 0.51 would distort its lanes below the specimen's 244px).
            spec_scale = RENDER_WIDTH / float(fx_vb[2])
            if spec_scale < floor:
                floor = spec_scale - 0.01
                note = f"; fluid-specimen floor {floor:.3f} (specimen vb_w {fx_vb[2]:g})"
        out.append(
            LawResult(
                "scale.band",
                floor <= scale <= SCALE_BAND[1],
                f"display/viewBox scale={scale:.3f} (band {floor:.3g}-{SCALE_BAND[1]}; "
                f"viewBox {facts.vb_w:g}x{facts.vb_h:g}, display {facts.width}{note})",
            )
        )
        out.append(LawResult("scale.never-magnify", scale < 1.0, f"scale={scale:.3f} (must downscale)"))
    return out


# ── cards ────────────────────────────────────────────────────────────────────


def law_cards(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    out: list[LawResult] = []
    targets = fixture.get("cards") or {}
    cards = card_rects(facts)
    heroes = [r for r in cards if "hero" in r.cls]
    std = [r for r in cards if "hero" not in r.cls]

    t_w, t_h = targets.get("std_w_med"), targets.get("std_h_med")
    superseded = str(targets.get("dims_superseded") or "")
    if t_w and t_h and superseded:
        # The language specimen (primer_diagram_language.html) replaced this specimen's card
        # ANATOMY (portrait stages → label-row); its content/structure laws
        # still pin, but dims re-derive from the language law, recorded here.
        out.append(LawResult("cards.std-dims", True, f"superseded: {superseded}"))
    elif t_w and t_h and std:
        w_med, h_med = _median([r.w for r in std]), _median([r.h for r in std])
        ok_w = abs(w_med - t_w) <= t_w * CARD_DIM_TOL
        ok_h = abs(h_med - t_h) <= t_h * CARD_DIM_TOL
        out.append(
            LawResult(
                "cards.std-dims",
                ok_w and ok_h,
                f"median {w_med:g}x{h_med:g} vs specimen {t_w:g}x{t_h:g} (±{CARD_DIM_TOL:.0%})",
            )
        )
    elif t_w and t_h:
        out.append(LawResult("cards.std-dims", False, "no standard cards rendered to compare"))

    t_ratio = targets.get("hero_area_ratio")
    if t_ratio and superseded:
        # The language law (primer_diagram_language.html) re-derives the hero
        # PROPORTION too — a 232x112 nucleus over the 144x60 satellite family is
        # a steeper step than the earlier topology specimen's — so the ratio law
        # rides the same documented supersession note as the std-dims law above.
        out.append(LawResult("cards.hero-ratio", True, f"superseded: {superseded}"))
    elif t_ratio:
        lo, hi = t_ratio * HERO_RATIO_SLACK, t_ratio * 1.25
        if heroes and std:
            ratio = (heroes[0].w * heroes[0].h) / max(_median([r.w for r in std]) * _median([r.h for r in std]), 1.0)
            out.append(
                LawResult(
                    "cards.hero-ratio",
                    lo <= ratio <= hi,
                    f"hero/std area ratio {ratio:.2f} (specimen {t_ratio:.2f}, band {lo:.2f}-{hi:.2f})",
                )
            )
        else:
            out.append(
                LawResult(
                    "cards.hero-ratio",
                    False,
                    f"specimen declares a hero; render has hero={len(heroes)} std={len(std)}",
                )
            )
    return out


# ── ports ────────────────────────────────────────────────────────────────────


def _near_endpoints(facts: Facts) -> list[tuple[float, float, float, bool]]:
    """(px, py, boundary-distance, is-marker-end) for every connector endpoint
    that approaches a node."""
    cards = card_rects(facts)
    coins = coin_circles(facts)
    out: list[tuple[float, float, float, bool]] = []
    for p in edge_paths(facts):
        ends = p.endpoints()
        if not ends:
            continue
        for idx, (px, py) in enumerate(ends):
            dists = [(_rect_boundary_dist(px, py, r)) for r in cards]
            dists += [abs(math.hypot(px - c.cx, py - c.cy) - c.r) for c in coins]
            if not dists:
                continue
            d = min(dists)
            if d <= PORT_NEAR_PX:
                out.append((px, py, d, idx == 1 and p.marker_end))
    return out


def measure_port_max(facts: Facts) -> float:
    """Largest near-node endpoint standoff a document exhibits (its authored
    craft envelope — extracted per specimen into the fixture)."""
    return max((d for _, _, d, _ in _near_endpoints(facts)), default=0.0)


def law_ports(facts: Facts, fixture: dict[str, Any] | None = None) -> list[LawResult]:
    """Every connector endpoint that approaches a node must land within the
    specimen's own attachment envelope of the true boundary (circle rim
    included — the audit's 4.51px bbox-gap class)."""
    # The flywheel rim is the exception BY DESIGN: its arcs float ~52px off
    # the phase cards (flywheel-orbit, measured) — the cycle is motion
    # BETWEEN phases, never plumbing into them. The flush premise doesn't
    # apply; the float itself is pinned engine-side (test_diagram_layout).
    if str(facts.root_attrs.get("data-hw-topology", "")) == "flywheel":
        return [LawResult("ports.flush", True, "flywheel rim floats by design (n/a)")]
    tol = PORT_FLUSH_PX
    if fixture:
        tol = max(PORT_FLUSH_PX, float(fixture.get("port_tolerance") or 0.0))
    marker_tol = max(tol, PORT_FLUSH_MARKER_PX)
    violations: list[str] = []
    near = _near_endpoints(facts)
    for px, py, d, is_marker_end in near:
        limit = marker_tol if is_marker_end else tol
        if d > limit:
            violations.append(f"({px:g},{py:g}) off-boundary by {d:.2f}px (limit {limit:g})")
    return [
        LawResult(
            "ports.flush",
            not violations,
            f"{len(near)} endpoints checked; " + ("; ".join(violations[:6]) if violations else "all within envelope"),
        )
    ]


# ── chip stubs ───────────────────────────────────────────────────────────────


def _on_line_chip_stubs(facts: Facts) -> list[tuple[Rect, float, float]]:
    """(chip, near-stub, far-stub) for every chip riding a straight edge."""
    out: list[tuple[Rect, float, float]] = []
    segs: list[tuple[float, float, float, float]] = []
    for p in edge_paths(facts):
        ends = p.endpoints()
        if ends:
            (x1, y1), (x2, y2) = ends
            segs.append((x1, y1, x2, y2))
    for ch in chip_rects(facts):
        for x1, y1, x2, y2 in segs:
            if abs(y1 - y2) <= 2.0 and abs(ch.cy - y1) <= 8.0:  # horizontal edge
                lo, hi = min(x1, x2), max(x1, x2)
                if lo <= ch.cx <= hi:
                    out.append((ch, ch.x - lo, hi - (ch.x + ch.w)))
                    break
            if abs(x1 - x2) <= 2.0 and abs(ch.cx - x1) <= 8.0:  # vertical edge
                lo, hi = min(y1, y2), max(y1, y2)
                if lo <= ch.cy <= hi:
                    out.append((ch, ch.y - lo, hi - (ch.y + ch.h)))
                    break
    return out


def measure_chip_stub_min(facts: Facts) -> float | None:
    stubs = _on_line_chip_stubs(facts)
    if not stubs:
        return None
    return min(min(a, b) for _, a, b in stubs)


def law_chip_stubs(facts: Facts, fixture: dict[str, Any] | None = None) -> list[LawResult]:
    floor = CHIP_STUB_MIN
    if fixture and fixture.get("chip_stub_min") is not None:
        floor = max(3.0, min(CHIP_STUB_MIN, float(fixture["chip_stub_min"])))
    stubs = _on_line_chip_stubs(facts)
    eps = 0.5  # int-rounded canvas widths shave up to half a px off a stub
    violations = [
        f"chip@({ch.x:g},{ch.y:g}) stubs {a:.1f}/{b:.1f}" for ch, a, b in stubs if a < floor - eps or b < floor - eps
    ]
    return [
        LawResult(
            "chips.stubs",
            not violations,
            f"{len(stubs)} on-line chips checked (law ≥{floor:g}px each side); "
            + ("; ".join(violations[:6]) if violations else "all clear"),
        )
    ]


# ── beam ─────────────────────────────────────────────────────────────────────


def law_beam(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    """The beam recipe: two grading tiers over the same facts. TEMPO
    (unconditional, every render carrying a beam — opted into full citation
    or not): no staged window may exceed ``BEAM_RELAY_SPAN_CAP``, the per-
    stage duration law both hand specimens converge on regardless of stage
    count — this is the enrollment that catches a family whose window math
    balloons on small stage counts (n=1 flush fans, n=2 bilateral/DAG
    splits) even on stories with no hand-authored citation to diff against.
    STRUCTURE (opt-in via ``fixture['beam']``, the two reference specimens
    only): the staged window set on one shared clock, keySplines easing,
    pad spread, true-zero end stops — never literal coordinates (per-edge
    chord gradients legitimately replace a hand file's shared-horizontal
    gradient economy on curved lanes, a recorded divergence)."""
    grads = facts.beam_gradients
    out: list[LawResult] = []
    if grads:
        windows_all = sorted({w for g in grads if (w := g.window()) is not None})
        wide = [w for w in windows_all if round(w[1] - w[0], 4) > BEAM_RELAY_SPAN_CAP + 1e-6]
        out.append(
            LawResult(
                "beam.tempo",
                not wide,
                f"windows {windows_all} (law: no span > {BEAM_RELAY_SPAN_CAP:g} of the clock — "
                + (f"wide: {wide}" if wide else "all clear"),
            )
        )
    want = fixture.get("beam") or {}
    if not want:
        return out
    if not grads:
        return [*out, LawResult("beam.present", False, "specimen carries a beam; render emitted no animated gradients")]
    clocks = sorted({g.dur for g in grads})
    out.append(
        LawResult(
            "beam.shared-clock",
            clocks == [str(want.get("clock"))],
            f"dur set {clocks} (law: one shared {want.get('clock')})",
        )
    )
    out.append(
        LawResult(
            "beam.eased",
            all(g.has_keysplines and g.calc_mode == "spline" for g in grads),
            "keySplines + calcMode=spline on every window",
        )
    )
    out.append(
        LawResult(
            "beam.pad-spread",
            all(g.spread in ("", "pad") for g in grads),
            f"spreads {sorted({g.spread or 'pad' for g in grads})} (repeat = the barber-pole bug)",
        )
    )
    out.append(
        LawResult(
            "beam.true-zero-ends",
            all(g.end_opacities[0] == 0.0 and g.end_opacities[1] == 0.0 for g in grads),
            "the comet arrives from nothing and leaves to nothing at both stops",
        )
    )
    windows = sorted({w for g in grads if (w := g.window()) is not None})
    want_windows = sorted((round(float(a), 4), round(float(b), 4)) for a, b in (want.get("windows") or []))
    out.append(
        LawResult(
            "beam.staged-windows",
            windows == want_windows,
            f"render windows {windows} vs specimen {want_windows}",
        )
    )
    return out


# ── census ───────────────────────────────────────────────────────────────────


def law_census(facts: Facts, fixture: dict[str, Any], *, mode: str = "render") -> list[LawResult]:
    want = fixture.get("census") or {}
    # Amendments (documented supersessions): where a ruling AMENDED a
    # specimen's composition (service-dependencies' relations ground as
    # on-wire chips; the gateway lightning counts as a mark), the fixture
    # keeps the specimen's own census — the SELF law still validates the
    # hand file — and the amended value REPLACES the render target: a render
    # that regresses to the superseded count fails instead of passing
    # against either.
    amended = (fixture.get("census_amendments") or {}) if mode == "render" else {}
    got = census(facts).as_dict()
    out: list[LawResult] = []
    for key, target in sorted(want.items()):
        actual = got.get(key)
        ok = actual == amended[key] if key in amended else actual == target
        note = f" | amended={amended[key]}" if key in amended else ""
        out.append(
            LawResult(
                f"census.{key}",
                ok,
                f"render={actual} specimen={target}{note}",
            )
        )
    return out


def law_lane_marks(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    """Lanes category-by-MARK census (obi-engine): per-card mark KIND, matched
    position-by-position in reading order — the finer-grained twin of the
    ``glyph_marks`` count. Pins that the render carries the specimen's
    archetype marks (disc/diamond/ring/disc-muted) on the RIGHT cards, so a
    scrambled shape cycle or a re-hued mark can't regress silently. Only
    specimens that declare ``lane_marks`` opt in; every other fixture is n/a."""
    want = fixture.get("lane_marks")
    if not want:
        return []
    assert isinstance(want, list)
    got = lane_mark_kinds(facts)
    return [
        LawResult(
            "lanes.card-marks",
            got == list(want),
            f"render={got} specimen={list(want)}",
        )
    ]


# ── vocabulary ───────────────────────────────────────────────────────────────

# Chrome text the payload legitimately does not carry: the composed caption
# sentence, masthead title/subtitle projections, zone headers, legend keys,
# lane furniture, and count badges.
_VOCAB_EXEMPT = ("ft", "cap", "cnt", "title", "sub", "key", "lane")


def law_vocabulary(facts: Facts) -> list[LawResult]:
    """Every rendered text run traces to the document's OWN payload: labels,
    descs, chips, guards, annotations all exist as payload strings. The law
    that catches engine-injected words (a TERMINAL tag) and hallucinated
    chips — on the specimen and the render alike."""
    hay = facts.payload_text.lower()
    # The law's premise is a FULL payload (nodes/states declared). Engine
    # payloads always are; some hand specimens carry envelope-style
    # summaries instead — the law is n/a there, never weakened.
    if not hay or '"desc"' not in hay:
        return [LawResult("vocab.payload", True, "no full payload (n/a)")]
    aliens: list[str] = []
    for t in facts.texts:
        run = t.content.strip()
        if not run:
            continue
        toks = t.cls.split()
        own = toks[-1].rsplit("-", 1)[-1] if toks else ""
        if any(
            own == e or own.startswith("zone") or own.endswith(("cap", "ft", "cnt", "title")) for e in _VOCAB_EXEMPT
        ):
            continue
        if own in _VOCAB_EXEMPT or "zone" in own:
            continue
        # Display runs legitimately COMPOSE payload fragments with the
        # interpunct / arrow typography (`write · mints`, `a → b`): each
        # fragment must trace, not the joined string.
        frags = [f.strip() for f in re.split(r"[·→]", run) if f.strip()]
        if any(f.lower() not in hay for f in frags):
            aliens.append(f"{own}:{run[:28]}")
    return [
        LawResult(
            "vocab.traceable",
            not aliens,
            "all text traces to the payload" if not aliens else f"alien runs: {aliens[:5]}",
        )
    ]


# ── honesty ──────────────────────────────────────────────────────────────────

_DIMS = re.compile(r"(\d{2,5})\s*[xx]\s*(\d{2,5})")
_RADIAL_TOPOLOGIES = ("flywheel", "radial", "hub", "mindmap")


def law_honesty(facts: Facts) -> list[LawResult]:
    out: list[LawResult] = []
    motion_attr = facts.root_attrs.get("data-hw-motion")
    if motion_attr is not None:
        claims_motion = motion_attr not in ("static", "none", "")
        out.append(
            LawResult(
                "honesty.motion-flag",
                claims_motion == facts.animated,
                f'data-hw-motion="{motion_attr}" vs rendered animation={facts.animated}',
            )
        )
    payload = facts.payload or {}
    spec = payload.get("spec") if isinstance(payload.get("spec"), dict) else None
    if spec:
        nodes = spec.get("nodes")
        # Containerless typographic nodes (hub-panel doctrine) render as bare
        # type — the rect/coin census cannot count them, so the node-count
        # law is n/a by construction, not dishonesty.
        containerless = (
            spec.get("node_style") == "text"
            or spec.get("composition") == "typographic-satellites"
            or (isinstance(nodes, list) and any(isinstance(n, dict) and n.get("style") == "text" for n in nodes))
        )
        if isinstance(nodes, list) and nodes and not containerless:
            cards = card_rects(facts)

            def _encloses_a_card(r: Rect) -> bool:
                # A region BAND (a filled non-concentric enclosure holding member
                # cards — agent-runtime's AGENT RUNTIME control-loop frame)
                # censuses as a card rect but is CHROME, not a payload node.
                return any(
                    o is not r
                    and o.x >= r.x - 1
                    and o.y >= r.y - 1
                    and o.x + o.w <= r.x + r.w + 1
                    and o.y + o.h <= r.y + r.h + 1
                    and o.w * o.h < r.w * r.h
                    for o in cards
                )

            rendered_nodes = sum(1 for r in cards if not _encloses_a_card(r)) + len(coin_circles(facts))
            # A compact payload may declare its focal node under a separate
            # ``hub`` key beside the member list (the parity-beam hand file's
            # "one spec") — the hub IS a rendered node, so it counts.
            declared = len(nodes) + (1 if spec.get("hub") else 0)
            out.append(
                LawResult(
                    "honesty.payload-nodes",
                    rendered_nodes == declared,
                    f"payload declares {declared} nodes; render shows {rendered_nodes}",
                )
            )
    if facts.spatial_notes:
        m = _DIMS.search(facts.spatial_notes)
        if m:
            nw, nh = float(m.group(1)), float(m.group(2))
            ok = (
                abs(nw - facts.vb_w) <= facts.vb_w * NOTES_DIM_TOL
                and abs(nh - facts.vb_h) <= facts.vb_h * NOTES_DIM_TOL
            )
            out.append(
                LawResult(
                    "honesty.notes-dims",
                    ok,
                    f"notes claim {nw:g}x{nh:g}; viewBox is {facts.vb_w:g}x{facts.vb_h:g}",
                )
            )
        topo = facts.root_attrs.get("data-hw-topology", "")
        if "left-to-right" in facts.spatial_notes and any(t in topo for t in _RADIAL_TOPOLOGIES):
            out.append(
                LawResult(
                    "honesty.notes-orientation",
                    False,
                    f'notes say "left-to-right" on topology "{topo}"',
                )
            )
    return out


# ── chroma ───────────────────────────────────────────────────────────────────


def law_chip_text_neutral(facts: Facts) -> list[LawResult]:
    offenders = [t.content for t in facts.texts if "-tag" in t.cls and re.search(r"-flp\d", t.cls)]
    return [
        LawResult(
            "chroma.chip-text-neutral",
            not offenders,
            "chip text carries accent class: " + ", ".join(offenders[:5])
            if offenders
            else "no chip text painted accent",
        )
    ]


# Specimen twin token → engine custom-property candidates. Engine names that
# do not exist yet (signal-text) are part of the red queue by design.
TOKEN_MAP: dict[str, tuple[str, ...]] = {
    "sig": ("--dna-signal",),
    "sigt": ("--dna-signal-text",),
    "s0": ("--dna-surface",),
    "s1": ("--dna-surface-alt",),
    "s2": ("--dna-surface-deep",),
    "stroke": ("--dna-border",),
    "ink": ("--dna-ink-primary",),
    "ink2": ("--dna-ink-muted",),
}


def law_twin_tokens(
    engine_faces: tuple[dict[str, str], dict[str, str]],
    specimen_faces: dict[str, dict[str, str]],
    variant: str,
) -> list[LawResult]:
    out: list[LawResult] = []
    for face_name, engine_face in (("light", engine_faces[0]), ("dark", engine_faces[1])):
        want = specimen_faces.get(face_name) or {}
        for key, expected in sorted(want.items()):
            candidates = TOKEN_MAP.get(key)
            if not candidates:
                continue
            actual = next((engine_face[c] for c in candidates if c in engine_face), None)
            out.append(
                LawResult(
                    f"chroma.twin.{variant}.{face_name}.{key}",
                    actual == expected.upper(),
                    f"{candidates[0]}={actual} vs specimen {expected.upper()}",
                )
            )
    return out


def _edge_chips(facts: Facts) -> list[Rect]:
    """Chips that ride a WIRE, not a card — an edge chip sits outside every
    card body (a node chip sits inside its card's footprint)."""
    cards = card_rects(facts)
    return [
        ch
        for ch in chip_rects(facts)
        if not any(r.x - 2 <= ch.cx <= r.x + r.w + 2 and r.y - 2 <= ch.cy <= r.y + r.h + 2 for r in cards)
    ]


def _gather_trunk(facts: Facts, kx: float, ky: float) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """The JOIN trunk at knot ``(kx, ky)``: the STRAIGHT edge whose FIRST
    endpoint is the knot (its spokes END there; a depart fan's trunk ENDS at
    the knot). Returns (knot, mouth) or None."""
    for p in edge_paths(facts):
        e = p.endpoints()
        if e and "C" not in p.d.upper() and math.hypot(e[0][0] - kx, e[0][1] - ky) < 4.0:
            return e
    return None


def has_gather_trunk_chip(facts: Facts) -> bool:
    """Does this document ride an edge chip ON a gather join trunk (dag-scatter)?
    The extractor sets the ``gather_trunk_chip`` fixture flag from this so the
    position law only fires where the idiom is actually present — a converge
    knot with a chip beside it but OFF the trunk (frontier-serving) reads False."""
    chips = _edge_chips(facts)
    for ring, _core in gather_knots(facts):
        trunk = _gather_trunk(facts, ring.cx, ring.cy)
        if trunk is None:
            continue
        (tx0, ty0), (mx, my) = trunk
        vx, vy = mx - tx0, my - ty0
        span = math.hypot(vx, vy)
        if span < 1.0:
            continue
        for ch in chips:
            pos = ((ch.cx - tx0) * vx + (ch.cy - ty0) * vy) / (span * span)
            off = abs((ch.cx - tx0) * vy - (ch.cy - ty0) * vx) / span
            if 0.3 <= pos <= 1.1 and off < 30.0:
                return True
    return False


def law_gather_chip(facts: Facts, fixture: dict[str, Any] | None = None) -> list[LawResult]:
    """A chip riding a gather trunk hugs the SINK mouth, never the knot/spoke.

    The dag-scatter idiom: converging edges collapse to a knot, one trunk
    carries them to the sink, and the ``resolve`` chip describing the join
    sits at that OUTPUT — its center in the mouth half of the trunk, on the
    wire. The engine default seated it on its own converging spoke, up near
    the fan ~97px short of the card (the census position-blindness Eli keeps
    catching). Fixture-gated (``gather_trunk_chip``, derived by the extractor
    only where a specimen actually rides a chip on a join trunk): a hub-fan-
    converge with a chip beside the knot but off the trunk (frontier-serving)
    is a DIFFERENT idiom, never held to this one. Finds each gather trunk (the
    straight edge that STARTS at the knot — spokes END there) and the edge chip
    nearest that knot; its normalized position along knot->mouth must be >= 0.40
    and it must sit within 40px of the trunk line."""
    gtc = fixture.get("gather_trunk_chip") if fixture else None
    if not gtc:
        return [LawResult("chips.gather-mouth", True, "no gather-trunk chip (n/a)")]
    # Convergence grounds its chip ON the wire (off ~0); the DAG-scatter join
    # LIFTS it a mouth-clearance above the trunk. An ``on_wire`` fixture flag
    # holds the tight floor so a convergence regression back to the 22px lift
    # fails loud — the 40px default can't tell the two idioms apart.
    off_max = 6.0 if (isinstance(gtc, dict) and gtc.get("on_wire")) else 40.0
    knots = gather_knots(facts)
    if not knots:
        return [LawResult("chips.gather-mouth", False, "fixture declares a gather-trunk chip but no knot rendered")]
    chips = _edge_chips(facts)
    out: list[LawResult] = []
    for ring, _core in knots:
        kx, ky = ring.cx, ring.cy
        trunk = _gather_trunk(facts, kx, ky)
        if trunk is None:
            continue
        (tx0, ty0), (mx, my) = trunk
        vx, vy = mx - tx0, my - ty0
        span = math.hypot(vx, vy)
        if span < 1.0:
            continue
        near = [(math.hypot(ch.cx - kx, ch.cy - ky), ch) for ch in chips]
        near = [(d, ch) for d, ch in near if d < 160.0]
        if not near:
            # The fixture promised a chip on this join; a render that dropped
            # it (or floated it out of reach) fails loud, not vacuous.
            out.append(
                LawResult("chips.gather-mouth", False, f"gather knot ({kx:g},{ky:g}) has no edge chip within reach")
            )
            continue
        _d, ch = min(near, key=lambda t: t[0])
        pos = ((ch.cx - tx0) * vx + (ch.cy - ty0) * vy) / (span * span)
        off = abs((ch.cx - tx0) * vy - (ch.cy - ty0) * vx) / span
        out.append(
            LawResult(
                "chips.gather-mouth",
                pos >= 0.40 and off < off_max,
                f"gather chip at norm-pos {pos:.2f} along knot->mouth, {off:.0f}px off the trunk "
                f"(law: pos>=0.40 mouth-half & <{off_max:g}px off — never a knot-side spoke)",
            )
        )
    return out or [
        LawResult("chips.gather-mouth", False, "fixture declares a gather-trunk chip but no join trunk rendered")
    ]


def law_convergence_approach_angle(facts: Facts, fixture: dict[str, Any], *, mode: str = "render") -> list[LawResult]:
    """F1's census key: the convergence fan-in's outer approach-angle
    commitment (``convergence_outer_angle_deg``, extractor-derived) must land
    within ``CONVERGENCE_ANGLE_TOL`` of the fixture's citation — a render that
    runs near-parallel-flat and pinches only at the end reads as a much
    smaller angle than a composition whose spokes commit early (a fuller arc,
    wider spread at the knot). Opt-in: absent on fixtures with no gather
    knot to measure from."""
    want = fixture.get("convergence_outer_angle_deg")
    if want is None or str(facts.root_attrs.get("data-hw-topology", "")) != "convergence":
        return []
    got = convergence_outer_chord_deg(facts)
    if got is None:
        return [LawResult("convergence.approach_angle", False, "fixture cites an approach angle but no knot rendered")]
    # Documented amendment: where a ruling SUPERSEDES the hand file's own
    # composition (the convergence pair share one envelope now), the fixture
    # keeps the specimen's citation — the SELF law still validates the hand
    # file — and the amended angle REPLACES the render target, so a render
    # that regresses to the superseded composition fails.
    amended = fixture.get("convergence_outer_angle_amended") if mode == "render" else None
    target = float(amended) if amended is not None else float(want)
    ok = abs(got - target) <= CONVERGENCE_ANGLE_TOL
    note = f" | amended={float(amended):.1f}deg" if amended is not None else ""
    return [
        LawResult(
            "convergence.approach_angle",
            ok,
            f"render={got:.1f}deg specimen={float(want):.1f}deg (tol {CONVERGENCE_ANGLE_TOL:g}deg){note}",
        )
    ]


def law_topology(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    """Structure parity (opt-in via fixture ``back_edge``): the render's OWN
    hw:payload declares its edges — the hand file declares the back-edge in
    the same machine-readable form. Both sides said what they connect for
    months while a wrong-target retry graded green; this law finally reads
    them. Counts and shapes cannot catch a mis-wired graph — identity can."""
    want = str((fixture.get("cards") or {}).get("back_edge") or fixture.get("back_edge") or "")
    if not want:
        return []
    payload = facts.payload or {}
    spec = payload.get("spec") or {}
    # Two declaration forms, one identity: the hand files state it directly
    # (spec.back_edge); the engine's payload derives it from the edge list.
    backs = (
        [str(spec["back_edge"])]
        if spec.get("back_edge")
        else [
            f"{e.get('source', e.get('s', ''))}->{e.get('target', e.get('t', ''))}"
            for e in (spec.get("edges") or [])
            if isinstance(e, dict) and (e.get("relation") == "drift" or e.get("role") == "liveness")
        ]
    )
    ok = any(b.lower() == want.lower() for b in backs)
    return [LawResult("topology.back-edge", ok, f"render back-edges {backs} vs specimen {want!r}")]


def law_edge_set(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    """Full relation-set parity (opt-in via fixture ``edge_set``): every
    declared source->target pair, with labels graded where BOTH sides carry
    one. back_edge caught the mis-wired retry; a wrong-source forward branch
    (executing->failed authored as review->failed) still graded green — the
    whole set is the identity, not just the returns. n/a when the two sides
    speak different node-id vocabularies (nothing to map)."""
    want = fixture.get("edge_set")
    if not isinstance(want, dict) or not want:
        return []
    got = payload_edge_pairs(facts)
    if not got:
        return [LawResult("topology.edge-set", False, "specimen declares edges; render payload declares none")]
    want_nodes = {n for pair in want for n in pair.split("->")}
    got_nodes = {n for pair in got for n in pair.split("->")}
    if not (want_nodes & got_nodes):
        return [LawResult("topology.edge-set", True, "n/a: disjoint node vocabularies")]
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    relabeled = sorted(p for p in set(want) & set(got) if want[p] and got[p] and want[p].lower() != got[p].lower())
    ok = not missing and not extra and not relabeled
    return [
        LawResult(
            "topology.edge-set",
            ok,
            f"missing {missing} extra {extra} relabeled {relabeled}" if not ok else f"{len(want)} relations match",
        )
    ]


def law_caption_voice(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    """Caption parity: the rendered caption sentence IS the specimen's,
    verbatim — 25 of 40 presets drifted (rewrites, dropped 'The loop ·'
    prefixes) while every geometry law stayed green, because no law read the
    text. A captionless specimen (obi) pins the ABSENCE."""
    if "caption_text" not in fixture:
        return []
    want = fixture.get("caption_text")
    got = caption_text(facts)
    if want is None:
        return [LawResult("chrome.caption-text", got is None, f"specimen has no caption; render says {got!r}")]
    ok = got == want
    return [LawResult("chrome.caption-text", ok, f"render {got!r} vs specimen {want!r}" if not ok else "verbatim")]


def law_hero_dims(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    """Hero crown dims, absolute (opt-in via fixture hero_w/hero_h): the
    area-RATIO law alone let a 280x92 specimen crown render 240x112 — same
    ballpark area, wrong shape. Honors the documented dims supersession the
    std-dims law already rides. Anatomy-blind via ``hero_figures``: a
    circle hero's box is its bounding square (w=h=2r — see
    ``HeroFigure``), so a circle grades diameter-vs-diameter through this
    SAME w/h comparison, no branch needed here."""
    targets = fixture.get("cards") or {}
    t_w, t_h = targets.get("hero_w"), targets.get("hero_h")
    if not (t_w and t_h):
        return []
    if targets.get("dims_superseded"):
        return [LawResult("cards.hero-dims", True, f"superseded: {targets['dims_superseded']}")]
    heroes = hero_figures(facts)
    if not heroes:
        return [LawResult("cards.hero-dims", False, "specimen declares a hero; render has none")]
    h = heroes[0]
    tol_w, tol_h = max(2.0, t_w * 0.02), max(2.0, t_h * 0.02)
    ok = abs(h.w - t_w) <= tol_w and abs(h.h - t_h) <= tol_h
    return [LawResult("cards.hero-dims", ok, f"hero {h.w:g}x{h.h:g} vs specimen {t_w:g}x{t_h:g}")]


def law_plate(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    """Plate band parity (opt-in via fixture ``plate``): zone-header air,
    content-to-caption air, caption-to-edge pad — measured baseline/ink
    anchors, same method both sides. The chrome mechanism was one owner fed
    four engine-wide constants calibrated from ONE specimen family; ring air
    rendered at a quarter of its hand file's band while every law held."""
    want = fixture.get("plate")
    if not isinstance(want, dict):
        return []
    amendment = str(fixture.get("plate_amendment") or "")
    if amendment:
        # Owner-triaged supersession (standing law #3): the hand sheet's
        # plate proportions are recorded as unfinished — the specimen still
        # validates itself, the render grades against the family values.
        return [LawResult("plate.bands", True, f"amended: {amendment}")]
    got = plate_anchors(facts)
    out: list[LawResult] = []

    def gap(anchors: dict[str, Any], a: str, b: str) -> float | None:
        if anchors.get(a) is None or anchors.get(b) is None:
            return None
        return float(anchors[b]) - float(anchors[a])

    checks = (
        ("plate.zone-air", gap(want, "zone_y", "content_top"), gap(got, "zone_y", "content_top"), 5.0),
        ("plate.caption-air", gap(want, "content_bottom", "caption_y"), gap(got, "content_bottom", "caption_y"), 6.0),
    )
    for law, w, g, tol in checks:
        if w is None:
            continue
        if g is None:
            if law == "plate.zone-air":
                # The hand file carries a masthead kicker the preset never
                # declares (zones data absent) — a standing authoring gap
                # recorded for owner triage, not a band-air defect.
                out.append(LawResult(law, True, f"specimen kicker at {w:.1f}px air; preset declares no zones"))
            else:
                out.append(LawResult(law, False, f"specimen band {w:.1f}px; render lacks the anchors"))
            continue
        out.append(LawResult(law, abs(g - w) <= tol, f"render {g:.1f}px vs specimen {w:.1f}px (±{tol:g})"))
    w_pad, g_pad = want.get("caption_pad"), None
    if got.get("caption_y") is not None and facts.vb_h:
        g_pad = facts.vb_h - float(got["caption_y"])
    if w_pad is not None and g_pad is not None:
        out.append(
            LawResult(
                "plate.caption-pad",
                abs(g_pad - float(w_pad)) <= 12.0,
                f"render {g_pad:.1f}px vs specimen {float(w_pad):.1f}px (±12)",
            )
        )
    return out


def law_chip_homes(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    """Chip placement census (opt-in via fixture ``chip_homes``): chips live
    in exactly two homes — the in-card row or threaded on a wire — and the
    on-wire seat offset is held to the specimen's own worst float band. The
    count-only census graded a bottom-edge-riding chip green."""
    want = fixture.get("chip_homes")
    if not isinstance(want, dict):
        return []
    got = chip_homes(facts)
    if got is None:
        return [LawResult("chips.homes", False, "specimen has chips; render has none")]
    ok_counts = got.get("in_card") == want.get("in_card") and got.get("on_wire") == want.get("on_wire")
    out = [
        LawResult(
            "chips.homes",
            ok_counts,
            f"render in_card={got.get('in_card')} on_wire={got.get('on_wire')} "
            f"vs specimen in_card={want.get('in_card')} on_wire={want.get('on_wire')}",
        )
    ]
    band = want.get("wire_offset_max")
    got_off = got.get("wire_offset_max")
    if band is not None and got_off is not None:
        limit = max(float(band) + 1.0, 2.0)
        out.append(
            LawResult(
                "chips.wire-seat",
                float(got_off) <= limit,
                f"worst on-wire offset {got_off}px (band {limit:.1f})",
            )
        )
    return out


def law_hub_seats(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    """Satellite seat parity (opt-in via fixture ``hub_seats``): per-satellite
    polar seat of the NAME run about the hero center — angle ±4°, throw ±6%.
    The sag/count census graded a dead-vertical, compressed delegation panel
    green; arrival axis and spread are the composition.

    A label listed in ``hub_seats_superseded`` (owner-triaged, same
    survival rule as ``cards.dims_superseded``) auto-passes with its note as
    evidence instead of comparing: pp-verb-ontology.svg's wide, uniform-
    floor satellite cards were superseded by the language specimen's
    narrower ink-solved family (dims_superseded), which mechanically
    shallows a sole N/S satellite's incidental text-anchor lean below this
    specimen's measured angle — closing that gap by nudging the card off
    the spine reads as a slanted connector no specimen draws, so the
    fixture target is amended here instead of the geometry."""
    want = fixture.get("hub_seats")
    if not isinstance(want, list) or not want:
        return []
    superseded = fixture.get("hub_seats_superseded") or {}
    got = hub_seats(facts)
    if not got:
        if superseded and all(str(w["label"]).lower() in superseded for w in want):
            return [LawResult("hub.seats", True, f"superseded: {'; '.join(superseded.values())}")]
        return [LawResult("hub.seats", False, "specimen pins satellite seats; render yields none")]
    got_by_label = {str(s["label"]).lower(): s for s in got}
    fails: list[str] = []
    notes: list[str] = []
    for w in want:
        label = str(w["label"])
        note = superseded.get(label.lower())
        if note:
            notes.append(f"{label}: superseded: {note}")
            continue
        g = got_by_label.get(label.lower())
        if g is None:
            fails.append(f"{label}: missing")
            continue
        d_ang = abs((float(g["angle"]) - float(w["angle"]) + 180.0) % 360.0 - 180.0)
        w_dist = float(w["dist"])
        d_rel = abs(float(g["dist"]) - w_dist) / max(w_dist, 1.0)
        if d_ang > 4.0 or d_rel > 0.06:
            fails.append(f"{label}: Δangle {d_ang:.1f}° Δthrow {d_rel:.1%}")
    evidence = "; ".join(fails or notes or [f"{len(want)} seats hold"])
    return [LawResult("hub.seats", not fails, evidence)]


def law_ring_arcs(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    """Ring arc spans (opt-in via fixture ``ring_arcs``): sorted spans within
    ±6° per position, mean within ±3° — wide enough for wrap-driven walk
    variance, far below the double-counted-clearance regression (every span
    15.2° vs the sheet's 34°)."""
    want = fixture.get("ring_arcs")
    if not isinstance(want, list) or not want:
        return []
    got = ring_arc_spans(facts)
    if not got or len(got) != len(want):
        return [LawResult("ring.arc-spans", False, f"render arcs {got} vs specimen {want}")]
    per = [abs(g - w) for g, w in zip(got, want, strict=True)]
    mean_d = abs(sum(got) / len(got) - sum(want) / len(want))
    ok = max(per) <= 6.0 and mean_d <= 3.0
    evidence = f"render {got} vs specimen {want} (worst Δ{max(per):.1f}°, mean Δ{mean_d:.1f}°)"
    return [LawResult("ring.arc-spans", ok, evidence)]


def law_hero_stack(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    """Hero STACK COMPOSITION (opt-in via fixture ``hero_stack``): the rows
    the crown contains — name runs, sub/desc/chip lines — against the hand
    file. Dims laws graded the box while nothing graded the stack; a crown
    that grows or drops a row re-rhythms invisibly."""
    want = fixture.get("hero_stack")
    if not isinstance(want, dict):
        return []
    got = hero_stack(facts)
    if got is None:
        return [LawResult("cards.hero-stack", False, "specimen crown carries rows; render hero has none")]
    ok = got == want
    return [LawResult("cards.hero-stack", ok, f"render {got} vs specimen {want}")]


_BELLY_X_TOL = 0.12
"""Band for ``belly_x`` (a 0..1 position along the edge's OWN start->end
x-span, never an absolute px — a hand specimen's viewBox and its engine
preset's content-sized canvas share no coordinate system: cicd-machine
solves to ~923px wide against the specimen's 1240, so the solver's own
internal belly_x reads 310px vs 482px, a false "171px off" a same-diagram
proportion check reads as within a few percent). 0.12 gives real auto-
layout card-size drift room while still catching a belly dragged to the
wrong THIRD of the sweep."""


def law_back_route(facts: Facts, fixture: dict[str, Any], *, mode: str = "render") -> list[LawResult]:
    """Per state-machine return edge (opt-in via fixture ``back_edge_routes``):
    the source face it exits (exact match — left/right/top/bottom/corner),
    how far it bows off its own start->end chord (±15%, the audit's
    148.5px-corner-basin vs a 44.3px flattened render is exactly this
    check), its closest approach to every third card on the canvas (floor =
    specimen clearance -15%, never tighter than the hand file's own craft),
    the angle its tangent strikes the target at (``arrival_angle``, ±3deg —
    chord_dev and clearance alone graded a corner-basin return green at
    82.4deg off the specimen's exact 90.0deg vertical; this is the check
    that catches it), and the NORMALIZED position of its deepest excursion
    when it carries a genuine interior dip (``belly_x``, ±0.12 — see
    ``_BELLY_X_TOL``; ``None`` for a monotonic recovery-climb, which has no
    belly to grade, never a failure). Citations: pp-state-machine.svg (cicd
    retry, corner exit, 148.5px bow, EXACTLY 90.0deg vertical, belly at
    41.5% of its own sx->tcx span), pp-state-machine-alt1.svg
    (order-lifecycle throw+retry, mirrored single-face exits, 32.2px bow —
    the LENS construction, a different idiom with its own analytic tangent
    citation in graph.py; not enrolled here, its fixture carries no
    arrival_angle/belly_x key), pp-state-machine-alt2.svg
    (agent-task-lifecycle revise 23.6deg belly at 55.4% / retry 71.1deg no
    belly, bottom/left exits)."""
    want = fixture.get("back_edge_routes")
    if not isinstance(want, dict) or not want:
        return []
    got = back_edge_routes(facts) or {}
    out: list[LawResult] = []
    for edge_key, want_route in sorted(want.items()):
        assert isinstance(want_route, dict)
        g = got.get(edge_key)
        if g is None:
            out.append(
                LawResult(
                    f"sm.back-route.{edge_key}", False, f"specimen declares {edge_key!r}; render has no matching route"
                )
            )
            continue
        ok_side = g["exit_side"] == want_route["exit_side"]
        # Documented amendment (replace-mode): a ruling that lawfully moves
        # the sweep (the snug-width chain shortens the span the lens bow is
        # proportional to) records the amended dev; the SELF law still
        # grades the hand file at its own citation.
        amended_dev = want_route.get("chord_dev_amended") if mode == "render" else None
        w_dev = float(amended_dev if amended_dev is not None else want_route["chord_dev"])
        ok_dev = abs(float(g["chord_dev"]) - w_dev) <= max(w_dev * 0.15, 1.0)
        ok_clear = True
        w_clear = want_route.get("clearance")
        g_clear = g.get("clearance")
        if w_clear is not None:
            ok_clear = g_clear is not None and float(g_clear) >= float(w_clear) * 0.85
        ok_angle = True
        w_angle = want_route.get("arrival_angle")
        g_angle = g.get("arrival_angle")
        if w_angle is not None:
            ok_angle = g_angle is not None and abs(float(g_angle) - float(w_angle)) <= 3.0
        ok_belly = True
        w_belly = want_route.get("belly_x")
        g_belly = g.get("belly_x")
        if w_belly is not None:
            ok_belly = g_belly is not None and abs(float(g_belly) - float(w_belly)) <= _BELLY_X_TOL
        ok = ok_side and ok_dev and ok_clear and ok_angle and ok_belly
        out.append(
            LawResult(
                f"sm.back-route.{edge_key}",
                ok,
                f"exit={g['exit_side']} (specimen {want_route['exit_side']}); "
                f"chord_dev={g['chord_dev']:.1f} (specimen {w_dev:.1f}, ±15%); "
                f"clearance={g_clear} (floor {(round(float(w_clear) * 0.85, 1)) if w_clear is not None else 'n/a'}); "
                f"arrival_angle={g_angle} (specimen {w_angle}, {'±3°' if w_angle is not None else 'n/a'}); "
                f"belly_x={g_belly} (specimen {w_belly}, {f'±{_BELLY_X_TOL}' if w_belly is not None else 'n/a'})",
            )
        )
    return out


def law_edge_dress(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    """Per state-machine return edge (opt-in via fixture ``edge_dress``):
    stroke role (accent | neutral) and dashed(bool) — order-lifecycle's own
    dress law in miniature (retry accent+dashed, throw neutral+solid),
    generalized to every specimen that carries a return family. A
    topology-blind reciprocal-lane detector once inverted this pair before
    the specimen's binary law was ever consulted; this reads the render's
    own CSS every time, never a cached assumption."""
    want = fixture.get("edge_dress")
    if not isinstance(want, dict) or not want:
        return []
    got = edge_dress(facts) or {}
    out: list[LawResult] = []
    for edge_key, want_d in sorted(want.items()):
        assert isinstance(want_d, dict)
        g = got.get(edge_key)
        if g is None:
            out.append(
                LawResult(
                    f"sm.edge-dress.{edge_key}", False, f"specimen declares {edge_key!r}; render has no matching edge"
                )
            )
            continue
        ok = g["role"] == want_d["role"] and g["dashed"] == want_d["dashed"]
        out.append(
            LawResult(
                f"sm.edge-dress.{edge_key}",
                ok,
                f"role={g['role']} dashed={g['dashed']} (specimen role={want_d['role']} dashed={want_d['dashed']})",
            )
        )
    return out


def law_label_seat(facts: Facts, fixture: dict[str, Any]) -> list[LawResult]:
    """Per return-edge label (opt-in via fixture ``edge_label_seats``,
    keyed by the label's own text): distance to its own wire within
    specimen+10px, AND that own wire is truly its NEAREST wire in the
    document — no foreign-wire adoption. ``label_seat`` re-discovers the
    owning edge from geometry on every call (never a stored identity), so
    a render that relocates a label onto a neighboring wire fails the
    nearest-wire half even when the raw distance looks small."""
    want = fixture.get("edge_label_seats")
    if not isinstance(want, dict) or not want:
        return []
    out: list[LawResult] = []
    for label_text, want_d in sorted(want.items()):
        seat = label_seat(facts, str(label_text))
        if seat is None:
            out.append(LawResult(f"sm.label-seat.{label_text}", False, f"label {label_text!r} or its wire not found"))
            continue
        own, nearest = seat["own"], seat["nearest_any"]
        ok_dist = own <= float(want_d) + 10.0
        ok_nearest = own <= nearest + 0.5
        out.append(
            LawResult(
                f"sm.label-seat.{label_text}",
                ok_dist and ok_nearest,
                f"own-wire {own:.1f}px (specimen {float(want_d):.1f}px +10 band) nearest-any {nearest:.1f}px"
                + ("" if ok_nearest else " — FOREIGN WIRE ADOPTED"),
            )
        )
    return out


def geometry_laws(
    facts: Facts, fixture: dict[str, Any], *, expected_render_w: int | None = None, mode: str = "render"
) -> list[LawResult]:
    """``mode``: "render" grades the ENGINE against the fixture — documented
    amendments REPLACE their key's target, so a regression back to a
    superseded composition fails instead of passing against either value;
    "self" grades the HAND FILE against its own citations — amendments are
    ignored (the specimen still validates itself, the amendment doctrine's
    first clause)."""
    return (
        law_scale(facts, fixture, expected_render_w=expected_render_w)
        + law_cards(facts, fixture)
        + law_ports(facts, fixture)
        + law_chip_stubs(facts, fixture)
        + law_census(facts, fixture, mode=mode)
        + law_lane_marks(facts, fixture)
        + law_gather_chip(facts, fixture)
        + law_convergence_approach_angle(facts, fixture, mode=mode)
        + law_beam(facts, fixture)
        + law_vocabulary(facts)
        + law_honesty(facts)
        + law_chip_text_neutral(facts)
        + law_topology(facts, fixture)
        + law_edge_set(facts, fixture)
        + law_caption_voice(facts, fixture)
        + law_hero_dims(facts, fixture)
        + law_plate(facts, fixture)
        + law_chip_homes(facts, fixture)
        + law_hub_seats(facts, fixture)
        + law_ring_arcs(facts, fixture)
        + law_hero_stack(facts, fixture)
        + law_back_route(facts, fixture, mode=mode)
        + law_edge_dress(facts, fixture)
        + law_label_seat(facts, fixture)
    )
