"""The closed edge-motion grammar's math — pure functions over config.

Three kinetic pieces: dash march and particle riders (composite-only) plus
the BEAM — a gradient-window comet pair on one shared relay clock
(paint-ok; the recipe generalizes the frontier-handoff and parity-beam
reference specimens). The beam animates
gradient COORDINATES only (animateTransform on gradientTransform —
transform-class CIM); geometry never moves. The flow tube grammar stays
retired. All constants arrive from ``data/config/diagram-frame.yaml`` —
this module owns formulas, not numbers.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.paths import chord_unit, fmt
from hyperweave.core.diagram import DiagramInputError, EdgeMotion, ResolvedEdge, Topology

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def fmt_s(v: float) -> str:
    """Seconds attribute value: trimmed, 's'-suffixed."""
    return f"{round(v, 4):g}s"


def _round10(v: float) -> float:
    return math.floor(v / 10 + 0.5) * 10


def resolve_edge_motions(
    edges: Sequence[ResolvedEdge],
    *,
    spec_motion: EdgeMotion | None,
    default: str,
    allowlist: Sequence[str],
    composite_only: bool,
    ladder: Mapping[str, str],
    stage_exempt: bool = False,
) -> tuple[list[str], bool]:
    """Concrete per-edge motion: edge override -> spec override -> genome
    default, allowlist-validated, then the fallback ladder under a
    composite-only constraint. ``stage_exempt`` routes ladder-listed motions
    through the same fallback for topologies that own their own replay
    grammar (sequence: its single traversing particle IS the clock — a beam
    would fight it), keeping the payload's requested/rendered record honest
    instead of silently diverging inside wire_motion. Returns (per-edge
    values, fallback_applied)."""
    allowed = set(allowlist)
    out: list[str] = []
    fallback = False
    for e in edges:
        requested = (
            (e.edge_motion.value if e.edge_motion else None) or (spec_motion.value if spec_motion else None) or default
        )
        if requested not in allowed:
            raise DiagramInputError(f"edge_motion {requested!r} is outside the genome allowlist {sorted(allowed)}")
        rendered = requested
        if (composite_only or stage_exempt) and requested in ladder:
            rendered = ladder[requested]
            fallback = True
        out.append(rendered)
    return out, fallback


def resolve_track(motion: str, *, track_map: Mapping[str, str], semantic_dash: str) -> str:
    """The track channel: which line the motion rides. P3 — a meaning-
    bearing dasharray (sequence return, SM styling) wins; the march never
    overwrites semantics."""
    if semantic_dash:
        return "static"
    return track_map.get(motion, "static")


def performance_tier(motions: Sequence[str], inert: Sequence[bool]) -> str:
    """The beam animates PAINT (a gradient window over a static tube), so an
    artifact carrying a rendered beam declares performance="paint-ok". The other
    kinetic pieces (dash march, particle riders) animate transform/dashoffset
    only — a beam-free artifact stays composite-only."""
    del inert
    return "paint-ok" if any(m == EdgeMotion.BEAM.value for m in motions) else "composite-only"


def replay_clock(
    spans: Sequence[float],
    *,
    v_target: float,
    dur_min: float,
    dur_max: float,
    seq_cfg: Mapping[str, Any],
) -> tuple[float, list[tuple[float, float]]]:
    """Sequence ordered replay under the speed law: each message is
    an independent EVENT whose transit obeys clamp(span / v_target,
    dur_min, dur_max); the shared clock is DERIVED — lead beat + Σ slots +
    gap beats between events + a rest beat before the loop. Order
    semantics untouched; the clock stretches to fit the speed of light."""
    lead = float(seq_cfg["lead_beat"])
    gap = float(seq_cfg["gap_beat"])
    rest = float(seq_cfg["rest_beat"])
    transits = [min(max(s / v_target, dur_min), dur_max) for s in spans]
    total = lead + sum(transits) + gap * max(len(spans) - 1, 0) + rest
    out: list[tuple[float, float]] = []
    cursor = lead
    for transit in transits:
        out.append((round(cursor / total, 4), round((cursor + transit) / total, 4)))
        cursor += transit + gap
    return total, out


def replay_particle_params(slot: tuple[float, float], fade: float) -> tuple[str, str, str, str]:
    """(keyPoints, keyTimes, opacity values, opacity keyTimes) for ONE
    persistent replay particle's slot (the sequence-replay specimen): the dot holds at the
    message's start, travels its slot at lawful velocity, then holds
    invisible for the rest of the cycle. Sequential non-overlapping slots
    mean exactly one dot is visible at a time — a single particle hopping
    message-to-message down the trace, in replay order."""
    s, e = slot
    keypoints = "0;0;1;1"
    keytimes = f"0;{round(s, 4):g};{round(e, 4):g};1"
    op_values = "0;0;.9;.9;0;0"
    op_keytimes = f"0;{round(s, 4):g};{round(min(s + fade, e), 4):g};{round(max(e - fade, s), 4):g};{round(e, 4):g};1"
    return keypoints, keytimes, op_values, op_keytimes


def stagger_begin(i: int, step: float) -> str:
    """Independent phi-staggered begins (volley/arrivals/particles/ants)."""
    return "" if i == 0 or step == 0 else fmt_s(i * step)


def detect_lanes(edges: Sequence[ResolvedEdge], lane_offset: float) -> list[int]:
    """Reciprocal-pair lanes: a derived pair may appear once per direction;
    the first-declared direction takes the -1 lane, its reciprocal +1,
    singles 0. The offset itself is applied to endpoints by the solver
    (perpendicular, +/- lane_offset).

    Topology-blind by design: this is a pure structural fact about the edge
    set, computed the same way whatever solver runs. State-machine's
    reciprocal pairs (order-lifecycle's throw/retry) ride their own return
    grammar instead of the generic lane-hue channel — that exemption is
    consumed at ``lane_dress_applies``, the semantic-chromatics owner
    deciding which topologies PAINT the lane, not detected here."""
    lanes = [0] * len(edges)
    seen: dict[tuple[int, int], int] = {}
    for i, e in enumerate(edges):
        back = seen.get((e.target, e.source))
        if back is not None:
            lanes[back] = -1
            lanes[i] = 1
        seen[(e.source, e.target)] = i
    return lanes


def lane_dress_applies(topology: Topology, lane: int) -> bool:
    """True where a reciprocal-lane edge paints ITS OWN lane dress — hue
    (``solver.connector_accents``), march dasharray (``wiring.wire_motion``),
    and label hue (``annotate.subsume_edge_labels``) all gate on this ONE
    predicate so the three channels of "lane dress" can never drift apart.

    Lanes topology paints category on the node marks, never the wire
    (a colored rail would re-encode the same axis twice); sequence's
    reciprocal-looking call/return pairs read their own kind grammar
    (solid call, dashed return) independent of lane parity; state-machine's
    reciprocal pairs (order-lifecycle's throw/retry) ride the back-edge
    accent instead — the lens bow's geometry already separates the two
    directions, so a second axis of meaning over the same pair would
    contradict it (see ``connector_accents``). Every other topology's
    reciprocal pair (the gateway specimen's request/response) is a
    CONVERSATION: forward reads accent, reverse reads muted."""
    return lane != 0 and topology not in (Topology.LANES, Topology.SEQUENCE, Topology.STATE_MACHINE)


def lane_offsets(
    edges: Sequence[ResolvedEdge],
    lanes: tuple[int, ...],
    motions: tuple[str, ...],
    engine: Mapping[str, Any],
) -> tuple[float, ...]:
    """Per-edge lane offset (G8): singles take the base; reciprocal pairs
    take the gap their motion COMPOSITION needs — dash-dash pairs have no
    motion asymmetry separating the lanes, so they carry more air
    (lane_offset_by_composition, sorted pair key)."""
    base = float(engine.get("lane_offset", 4))
    table = {str(k): float(v) for k, v in (engine.get("lane_offset_by_composition") or {}).items()}
    extents = {str(k): float(v) for k, v in (engine.get("lane_extent") or {}).items()}
    min_air = float(engine.get("lane_min_air", 3))
    partner: dict[int, int] = {}
    seen: dict[tuple[int, int], int] = {}
    for j, e in enumerate(edges):
        back = seen.get((e.target, e.source))
        if back is not None:
            partner[j], partner[back] = back, j
        seen[(e.source, e.target)] = j
    out: list[float] = []
    for j in range(len(edges)):
        if lanes[j] == 0 or j not in partner:
            out.append(base)
            continue
        a, b = motions[j], motions[partner[j]]
        comp = "-".join(sorted((a, b)))
        # K2: the gap is air between RENDERED extents — glow counts.
        rendered_floor = extents.get(a, 1.0) + extents.get(b, 1.0) + min_air
        out.append(max(table.get(comp, base), rendered_floor))
    return tuple(out)


def lane_endpoints(
    x1: float, y1: float, x2: float, y2: float, lane: int, gap: float
) -> tuple[float, float, float, float]:
    """Reciprocal lanes sit ±gap/2 perpendicular to the SHARED centerline
    (G8b). The perpendicular comes from a CANONICAL chord orientation
    (endpoint-sorted), never the edge's own travel direction: the pair's
    chords are reversed copies, so multiplying the lane sign by each edge's
    own perpendicular cancels against the reversal and renders the lanes
    COINCIDENT — the candy-stripe regression. One shared axis + the lane
    sign picks sides; motion still travels each path's own direction."""
    if lane == 0:
        return x1, y1, x2, y2
    cx1, cy1, cx2, cy2 = (x1, y1, x2, y2) if (x1, y1) <= (x2, y2) else (x2, y2, x1, y1)
    ux, uy = chord_unit(cx1, cy1, cx2, cy2)
    nx, ny = -uy, ux
    d = lane * gap / 2
    return x1 + nx * d, y1 + ny * d, x2 + nx * d, y2 + ny * d


def _translate_values(sx: float, sy: float, ux: float, uy: float, distances: Sequence[float]) -> str:
    """Absolute 'dx dy' translate keyframes along the chord."""
    return ";".join(f"{fmt(sx + ux * d)} {fmt(sy + uy * d)}" for d in distances)


def beam_windows(n: int, cfg: Mapping[str, Any], *, family: str) -> list[tuple[float, float]]:
    """Stage windows on the shared beam relay clock.

    ``family='relay'`` (the frontier-handoff specimen): a lead beat, ``n``
    equal spans separated by gap beats, and a rest beat before the loop —
    ``span = (1 - lead - (n-1)*gap - rest) / n``, capped per below. n=3
    reproduces the specimen's .02-.28 / .34-.60 / .66-.92 exactly.
    ``max(span, gap)`` is a defensive floor the topology caps never reach.
    ``family='branch'`` (the parity-beam specimen):
    exactly two stages — the trunk fires, then every branch shares one
    simultaneous window (.02-.30 / .32-.62): simultaneity IS the parity
    argument. ``family='bilateral'``: the fan-out mirror of ``branch`` for a
    topology with no trunk to lead — two EQUAL simultaneous stages (west
    converges as one wave, a beat at the hub, east emerges as the next),
    keyed by ``EdgeGeo.flow_side`` rather than stage order. No bilateral
    beam specimen exists to cite its own span, so it's derived from
    ``relay``'s own n=2 shape (same lead/gap/rest law, dedicated so it never
    degenerates to the n=1 near-full sweep when one side happens to hold
    every beam-lit edge — relay's generic by-count path would collapse to
    ``len(order)==1`` there, which is tuned for a genuinely solo relay leg,
    not a two-sided wave).

    ``relay``/``bilateral`` divide the WHOLE clock across n stages
    (``span = (1 - lead - (n-1)*gap - rest) / n``), which only reproduces
    the specimen band at n=3 (its citation, span .26): at n=1 (a flush
    single-group fan — artifact-fanout-beam's chipless depart, no trunk
    stub to key a second stage on) or n=2 (bilateral's own west/east split;
    a 2-rank DAG transition — settlement-relay) the raw division balloons
    to span .42-.90, a comet crawling 2.2-4.7s across one window instead of
    the ~1.5s both specimens converge on regardless of stage count (branch
    .28-.30, relay-n=3 .26). ``relay_span_cap`` (.30, the wider of the two
    citations) is the per-stage window LAW; ``min(computed, cap)`` lets it
    bind only where the by-count division would exceed what either
    specimen ever licensed, leaving n=3 (and any n whose computed span
    already undercuts the cap) byte-identical."""
    if family == "branch":
        r = cfg.get("relay_branch") or {}
        t0 = float(r.get("trunk_lead", 0.02))
        ts = float(r.get("trunk_span", 0.28))
        bg = float(r.get("branch_gap", 0.02))
        bs = float(r.get("branch_span", 0.30))
        return [(round(t0, 4), round(t0 + ts, 4)), (round(t0 + ts + bg, 4), round(t0 + ts + bg + bs, 4))]
    cap = float(cfg.get("relay_span_cap", 0.30))
    if family == "bilateral":
        r = cfg.get("relay_bilateral") or {}
        lead = float(r.get("lead", 0.02))
        gap = float(r.get("gap", 0.06))
        rest = float(r.get("rest", 0.08))
        span = max(min((1.0 - lead - gap - rest) / 2, cap), gap)
        west = (round(lead, 4), round(lead + span, 4))
        east = (round(lead + span + gap, 4), round(lead + span + gap + span, 4))
        return [west, east]
    r = cfg.get("relay") or {}
    lead = float(r.get("lead", 0.02))
    gap = float(r.get("gap", 0.06))
    rest = float(r.get("rest", 0.08))
    n = max(n, 1)
    span = max(min((1.0 - lead - (n - 1) * gap - rest) / n, cap), gap)
    out: list[tuple[float, float]] = []
    for i in range(n):
        s = lead + i * (span + gap)
        out.append((round(s, 4), round(s + span, 4)))
    return out


def beam_gradient(
    index: int,
    sx: float,
    sy: float,
    tx: float,
    ty: float,
    *,
    stage: tuple[float, float],
    cfg: Mapping[str, Any],
) -> tuple[BeamGradient, BeamGradient]:
    """The specimen beam pair (the frontier-handoff and parity-beam
    references): a BODY window (blue head → purple tail,
    true-zero ends) and a narrower accent-deep COMET FRONT, sharing ONE
    GradientAnimate — both translate one full run + window along the chord
    inside this edge's ``stage`` of the shared relay clock (hold → eased
    sweep → hold; calcMode spline). The gradient geometry BAKES the edge
    start (x1,y1 = the source point, the vector pointing back one window)
    and the animation translates RELATIVE from '0 0' — bit-identical to the
    hand files when animated, and safe at identity transform when SMIL is
    stripped (svg-static, rasterizers): the window rests entirely behind the
    start point, so a static face shows the bare glass conduit, never a
    frozen half-comet. No spreadMethod (pad) + true-zero end stops keep the
    sweep a single comet, not a barber-pole. Identity fixed blue/purple
    across every variant (beam-relay.md), never genome-derived."""
    from hyperweave.compose.diagram.records import BeamGradient, GradientAnimate, GradientStop

    ux, uy = chord_unit(sx, sy, tx, ty)
    w = float(cfg.get("window", 120))
    front_span = float(cfg.get("front_span", 38))
    travel = math.hypot(tx - sx, ty - sy) + w
    s, e = stage
    animate = GradientAnimate(
        values=_translate_values(0.0, 0.0, ux, uy, [0.0, 0.0, travel, travel]),
        keytimes=f"0;{round(s, 4):g};{round(e, 4):g};1",
        keysplines=str(cfg.get("keysplines", "0 0 1 1;0.42 0 0.58 1;0 0 1 1")),
        dur=fmt_s(float(cfg.get("dur", 5.236))),
        calc_mode="spline",
    )
    color_a = str(cfg.get("color_a", "#60A5FA"))
    color_b = str(cfg.get("color_b", "#A78BFA"))
    front_a = str(cfg.get("front_a", "#2563EB"))
    front_b = str(cfg.get("front_b", "#93C5FD"))
    body = BeamGradient(
        id_suffix=f"beam{index}body",
        x1=round(sx, 3),
        y1=round(sy, 3),
        x2=round(sx - ux * w, 3),
        y2=round(sy - uy * w, 3),
        # The reference stops verbatim: a 4% transparent nose, solid blue head,
        # purple body at .85, fading to TRUE zero at the tail.
        stops=(
            GradientStop(offset=0.0, color=color_a, opacity=0.0),
            GradientStop(offset=0.04, color=color_a, opacity=1.0),
            GradientStop(offset=0.09, color=color_a, opacity=1.0),
            GradientStop(offset=0.35, color=color_b, opacity=0.85),
            GradientStop(offset=1.0, color=color_b, opacity=0.0),
        ),
        animate=animate,
        spread="",
    )
    front = BeamGradient(
        id_suffix=f"beam{index}front",
        x1=round(sx, 3),
        y1=round(sy, 3),
        x2=round(sx - ux * front_span, 3),
        y2=round(sy - uy * front_span, 3),
        stops=(
            GradientStop(offset=0.0, color=front_a, opacity=0.0),
            GradientStop(offset=0.12, color=front_a, opacity=0.95),
            GradientStop(offset=1.0, color=front_b, opacity=0.0),
        ),
        animate=animate,
        spread="",
    )
    return body, front


if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import BeamGradient
