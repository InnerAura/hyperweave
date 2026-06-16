"""The closed edge-motion grammar's math — pure functions over config.

The vocabulary is a 2x2 ({composite-only, paint-ok} x {discrete,
continuous} = particle | dash | beam | flow); everything here is a
PARAMETER of those four values, never a fifth. Beam and flow animate
gradient COORDINATES (animateTransform on gradientTransform —
transform-class CIM); geometry never moves. All constants arrive from
``data/config/diagram-frame.yaml`` — this module owns formulas, not numbers.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.paths import chord_unit, fmt
from hyperweave.compose.diagram.records import GradientAnimate, GradientSpec, GradientStop
from hyperweave.core.diagram import DiagramInputError, EdgeMotion, ResolvedEdge

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
) -> tuple[list[str], bool]:
    """Concrete per-edge motion: edge override -> spec override -> genome
    default, allowlist-validated, then the fallback ladder under a
    composite-only constraint. Returns (per-edge values, fallback_applied)
    — requested vs rendered never silently diverges (the caller records
    both in the payload)."""
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
        if composite_only and requested in ladder:
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
    """paint-ok iff any rendered edge runs an animated-paint value."""
    for m, dead in zip(motions, inert, strict=True):
        if not dead and m in ("beam", "flow"):
            return "paint-ok"
    return "composite-only"


def beam_window(length: float, beam_cfg: Mapping[str, Any]) -> float:
    """W = round10(clamp(ratio x length, min, max)) — 142px edges get the
    canon's 80, ~430px fan edges cap at 130."""
    w = float(beam_cfg["window_ratio"]) * length
    w = max(float(beam_cfg["window_min"]), min(float(beam_cfg["window_max"]), w))
    return _round10(w)


def flow_period(length: float, flow_cfg: Mapping[str, Any]) -> float:
    """P = round10(clamp(ratio x length, min, max)); the translate moves
    exactly one period per cycle so the current is seamless."""
    p = float(flow_cfg["period_ratio"]) * length
    p = max(float(flow_cfg["period_min"]), min(float(flow_cfg["period_max"]), p))
    return _round10(p)


def relay_slots(n: int, relay_cfg: Mapping[str, Any]) -> list[tuple[float, float]]:
    """Slot-locked relay on one phi clock: travel windows separated by
    hop_gap (the node 'processing'), cycle_rest before the next payload."""
    lead = float(relay_cfg["lead"])
    gap = float(relay_cfg["hop_gap"])
    rest = float(relay_cfg["cycle_rest"])
    travel = (1.0 - lead - rest - (n - 1) * gap) / n
    travel = math.floor(travel * 100) / 100
    out: list[tuple[float, float]] = []
    for i in range(n):
        start = round(lead + i * (travel + gap), 4)
        out.append((start, round(start + travel, 4)))
    return out


def replay_clock(
    spans: Sequence[float],
    *,
    v_target: float,
    dur_min: float,
    dur_max: float,
    seq_cfg: Mapping[str, Any],
) -> tuple[float, list[tuple[float, float]]]:
    """Sequence ordered replay under the speed law (K-seq): each message is
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
    persistent replay particle's slot (K-seq-v2): the dot holds at the
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
    (perpendicular, +/- lane_offset)."""
    lanes = [0] * len(edges)
    seen: dict[tuple[int, int], int] = {}
    for i, e in enumerate(edges):
        back = seen.get((e.target, e.source))
        if back is not None:
            lanes[back] = -1
            lanes[i] = 1
        seen[(e.source, e.target)] = i
    return lanes


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


def beam_gradients(
    *,
    id_base: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    length: float,
    hue: str,
    hue2: str | None,
    choreo: str,
    slot: tuple[float, float] | None,
    begin: str,
    beam_cfg: Mapping[str, Any],
    travel_end: float | None = None,
    clock: float | None = None,
) -> tuple[GradientSpec, GradientSpec]:
    """The comet: a body gradient (pad-guarded tip -> head -> signal body ->
    ember tail) plus the near-white head filament, both translated along the
    chord. Identity shots are two-hue (hue -> hue2); ramp edges single-hue.
    The gradient axis points BACKWARD along travel so the head leads."""
    w = beam_window(length, beam_cfg)
    ux, uy = chord_unit(x1, y1, x2, y2)
    stops_cfg = beam_cfg["stops"]
    tail_op = float(stops_cfg["tail_opacity_identity"] if hue2 else stops_cfg["tail_opacity_ramp"])
    tail_hue = hue2 or hue
    body_stops = (
        GradientStop(offset=float(stops_cfg["tip"]), color=hue, opacity=0.0),
        GradientStop(offset=float(stops_cfg["head"]), color=hue),
        GradientStop(offset=float(stops_cfg["body"]), color=hue),
        GradientStop(offset=float(stops_cfg["tail"]), color=tail_hue, opacity=tail_op),
        GradientStop(offset=1.0, color=tail_hue, opacity=0.0),
    )
    if choreo == "relay":
        if slot is None:
            raise ValueError("relay choreography requires a slot")
        relay = beam_cfg["relay"]
        s, e = slot
        distances = [-w, -w, length, length]
        keytimes = f"0;{s:g};{e:g};1"
        keysplines = f"0 0 1 1;{relay['travel_spline']};0 0 1 1"
        dur = f"{clock:g}s" if clock is not None else str(relay["dur"])
        anim_begin = ""
    else:
        mode = beam_cfg["arrivals"] if choreo == "arrivals" else beam_cfg["volley"]
        distances = [-w, length, length]
        # One speed of light (K1): the caller passes a per-edge travel
        # fraction (transit time / shared clock) so comets cross every
        # chord at the same velocity; departures stay phi-staggered.
        end = float(mode["travel_end"]) if travel_end is None else travel_end
        keytimes = f"0;{end:g};1"
        keysplines = f"{mode['travel_spline']};0 0 1 1"
        dur = str(mode["dur"])
        anim_begin = begin
    animate = GradientAnimate(
        values=_translate_values(x1, y1, ux, uy, distances),
        keytimes=keytimes,
        keysplines=keysplines,
        dur=dur,
        begin=anim_begin,
        calc_mode="spline",
    )
    body = GradientSpec(
        id_suffix=f"{id_base}b",
        x1=ux * w,
        y1=uy * w,
        x2=0.0,
        y2=0.0,
        stops=body_stops,
        animate=animate,
    )
    fil_w = round(float(beam_cfg["filament_ratio"]) * w / 2) * 2
    fil_stops = (
        GradientStop(offset=0.0, color=str(beam_cfg["filament_head"]), opacity=0.0),
        GradientStop(
            offset=0.12,
            color=str(beam_cfg["filament_head"]),
            opacity=float(beam_cfg["filament_head_opacity"]),
        ),
        GradientStop(offset=1.0, color=str(beam_cfg["filament_tail"]), opacity=0.0),
    )
    filament = GradientSpec(
        id_suffix=f"{id_base}f",
        x1=ux * w,
        y1=uy * w,
        x2=ux * (w - fil_w),
        y2=uy * (w - fil_w),
        stops=fil_stops,
        animate=animate,
    )
    return body, filament


def flow_gradient(
    *,
    id_base: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    length: float,
    hue: str,
    begin: str,
    flow_cfg: Mapping[str, Any],
    phase_px: float = 0.0,
) -> GradientSpec:
    """The laminar current: a repeating soft pulse translated exactly one
    period per cycle. Arc segments pass their cumulative length as
    ``phase_px`` so the current reads continuous across a subdivision."""
    p = flow_period(length, flow_cfg)
    ux, uy = chord_unit(x1, y1, x2, y2)
    phase = ""
    if phase_px:
        frac = (phase_px % p) / p
        dur_s = float(str(flow_cfg["dur"]).rstrip("s"))
        offset = round(frac * dur_s, 4)
        phase = fmt_s(-offset) if offset else ""
    stops = (
        GradientStop(offset=0.0, color=hue, opacity=0.0),
        GradientStop(offset=float(flow_cfg["pulse_peak"]), color=hue, opacity=float(flow_cfg["pulse_opacity"])),
        GradientStop(offset=1.0, color=hue, opacity=0.0),
    )
    animate = GradientAnimate(
        values=f"0 0;{fmt(ux * p)} {fmt(uy * p)}",
        dur=str(flow_cfg["dur"]),
        begin=begin or phase,
    )
    return GradientSpec(
        id_suffix=f"{id_base}l",
        x1=0.0,
        y1=0.0,
        x2=ux * p,
        y2=uy * p,
        stops=stops,
        spread="repeat",
        animate=animate,
    )


def choreography_for(layout_slug: str, motion: str, choreo_cfg: Mapping[str, Any]) -> str:
    """Which timing mode a (layout, motion) pair runs."""
    table = choreo_cfg.get(motion) or {}
    return str(table.get(layout_slug, table.get("default", "volley" if motion == "beam" else "current")))
