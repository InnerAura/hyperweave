"""Choreography compiler — the artifact-scoped motion-register axis.

A register performs the diagram's semantic claim IN TIME over geometry it
never touches (the corpus isolates the axis with expression-flip lineage).
The compiler runs AFTER the layout solve, reads only the frozen records
(final coordinates, exact connector lengths), and returns a new layout via
``dataclasses.replace`` — so it is topology-generic and register-generic by
construction: the ``enumerate`` register (tree/hub, the next wave) lands as
one more entry in ``_CHOREOGRAPHERS``.

The ``turn`` register speaks the expression corpus's ONE choreography
language (the second-generation specimens are the law; the first-generation
anchors' rhythmic grammar is retired):

* **The route draws itself and stays lit.** Each turn's trail sweeps on in
  the accent (stroke-dashoffset length -> 0), HOLDS, and clears at the turn
  boundary — a loop takes exactly one branch per pass, and the lit route is
  the pass's record. A three-layer comet head rides the drawing tip (bright
  core, two staggered washes); the arrowhead pops in the leg's hue when it
  completes and hides at the clear; every chip lights as a tint — its own
  markup re-stamped in the branch hue.
* **Kinematic pacing.** A leg's duration is ``leg_k * sqrt(length)``,
  clamped — long rails sweep with weight, short hops snap. An inner
  circuit's later laps replay on the comet head ALONE at the same pace —
  a trail draws once per turn and stays lit, never redraws.
* **One easing envelope per turn.** The first leg eases in, middle legs run
  linear, the closing rail eases out — rest to cruise, cruise, cruise to
  rest.
* **Short dwells, one dark beat.** Arrivals dwell ``dwell_s`` (decisions
  deliberate at ``dwell_decision_s``); the turn clears after ``clear_hold_s``
  and the next begins after ``turn_beat_s`` of dark; the period ends on a
  breathing rest.
* **Guards pre-flash.** A decision's chip lights ``guard_preflash_s`` before
  its branch fires; station halos are short arrival glows; a demonstrated
  terminal's halo holds ``terminal_hold_s`` into the dark beat — the
  completion read — and a terminal-ending period rests longer.

Constants live in ``data/config/diagram-frame.yaml``'s ``choreography.turn``
block, cited from the corpus motion records; this module owns the formulas —
Python computes, templates stamp.

CIM: stroke-dashoffset + opacity only; zero geometry animation. The static
face (reduced motion) is the corpus's own resting state: the route rests
FULLY LIT with its arrowheads shown, heads/halos/tints vanish — the
argument never degrades.
"""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.loop import classify_loop
from hyperweave.compose.diagram.records import (
    ChipTint,
    ChoreographyPlan,
    DiagramLayout,
    HaloFlash,
    KeyframeBlock,
    MeterFill,
    PulseOverlay,
)
from hyperweave.compose.spatial_records import RectSpec
from hyperweave.core.diagram import DiagramInputError, Topology, resolved_edges

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from hyperweave.core.diagram import DiagramSpec, ResolvedEdge

# The one easing envelope's letters (the corpus keyframes, verbatim).
_EASE_IN = "cubic-bezier(.55,0,1,1)"
_EASE_OUT = "cubic-bezier(0,0,.42,1)"
_POP = "cubic-bezier(.16,.9,.3,1)"
_FADE = "cubic-bezier(.5,0,.75,.4)"


def resolve_register(spec: DiagramSpec, engine: Mapping[str, Any]) -> str:
    """The artifact's register: the declared ``motion_register``, else the
    family default (``choreography.family_defaults`` — loop maps to turn per
    the corpus's owner gate), else the universal quiet face, drift."""
    cfg = engine.get("choreography") or {}
    defaults = cfg.get("family_defaults") or {}
    register = spec.motion_register or str(defaults.get(spec.topology.value, "drift"))
    if register != "drift" and spec.topology.value not in _REGISTER_TOPOLOGIES.get(register, ()):
        raise DiagramInputError(
            f"motion_register '{register}' ships on the "
            f"{' / '.join(_REGISTER_TOPOLOGIES.get(register, ()))} family this release; "
            f"{spec.topology.value} renders the drift face (the enumerate register is the next wave)"
        )
    return register


def apply_choreography(
    layout: DiagramLayout, spec: DiagramSpec, *, register: str, engine: Mapping[str, Any]
) -> DiagramLayout:
    """Compile the register onto the frozen layout. ``drift`` is the plain
    face — the layout passes through untouched except for the honest
    ``rendered.motion_register`` record."""
    rendered = replace(layout.rendered, motion_register=register)
    if register == "drift":
        return replace(layout, rendered=rendered)
    plan = _CHOREOGRAPHERS[register](layout, spec, engine)
    return replace(layout, choreography=plan, rendered=rendered)


# ── The turn register ───────────────────────────────────────────────────


@dataclass
class _Act:
    """One demonstrated outcome: the ordered outer edges of one turn, its
    outcome kind, and whether its first scope crossing lingers for extra
    laps (cycle-nested's own asymmetry)."""

    edges: list[int]
    outcome: str  # repeat | terminal
    branches: frozenset[tuple[int, int]]
    terminal: int | None = None
    slots: int = 1
    crosses_scope: bool = False


@dataclass
class _Timeline:
    """Firing windows per element, accumulated act by act (seconds)."""

    trails: dict[int, list[tuple[float, float, float, str]]] = field(default_factory=dict)
    """edge k -> [(draw_start, draw_end, clear, easing)] — the lit route."""
    halos: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    """station/scope key -> [(pop, hold_end)] — arrival glows."""
    halo_hues: dict[str, str] = field(default_factory=dict)
    """station key -> the arriving leg's hue letter; unset keys fall back
    to the partition read at emission."""
    heads: dict[int, list[tuple[float, float, str]]] = field(default_factory=dict)
    """edge k -> [(t0, t1, easing)] — EXTRA comet-head sweeps over a trail
    that is already lit (an inner circuit's later laps): the trail never
    redraws within a turn, only the head runs the route again."""
    chips: dict[int, list[tuple[float, float]]] = field(default_factory=dict)
    """edge k -> [(flash_start, hold_end)] — chips lighting with their leg."""
    chip_hues: dict[int, str] = field(default_factory=dict)
    """edge k -> tint hue letter (A / C / W — the branch's own ink)."""
    meter_marks: dict[int, list[tuple[float, float]]] = field(default_factory=dict)
    """RETURN edge k -> [(draw_start, draw_end)] — the meters' beats."""

    def trail(self, k: int, t0: float, t1: float, clear: float, ease: str) -> None:
        self.trails.setdefault(k, []).append((t0, t1, clear, ease))

    def head(self, k: int, t0: float, t1: float, ease: str = "linear") -> None:
        self.heads.setdefault(k, []).append((t0, t1, ease))

    def halo(self, key: str, t0: float, hold_end: float, hue: str = "") -> None:
        self.halos.setdefault(key, []).append((t0, hold_end))
        if hue:
            self.halo_hues[key] = hue

    def chip(self, k: int, t0: float, hold_end: float, hue: str = "A") -> None:
        self.chips.setdefault(k, []).append((t0, hold_end))
        self.chip_hues[k] = hue

    def meter_mark(self, k: int, t0: float, t1: float) -> None:
        self.meter_marks.setdefault(k, []).append((t0, t1))


def _tcfg(engine: Mapping[str, Any], key: str, default: float) -> float:
    return float(((engine.get("choreography") or {}).get("turn") or {}).get(key, default))


def _leg_s(engine: Mapping[str, Any], length: float) -> float:
    """Kinematic leg duration: ``leg_k * sqrt(length)``, clamped — the
    corpus's own formula, verbatim (0.058 * sqrt(66.4) = the measured
    0.473s spine hop; the 969px rail rides the 1.30 clamp)."""
    k = _tcfg(engine, "leg_k", 0.058)
    lo = _tcfg(engine, "leg_min_s", 0.30)
    hi = _tcfg(engine, "leg_max_s", 1.30)
    return min(hi, max(lo, k * math.sqrt(max(length, 1.0))))


def _turn_timeline(
    layout: DiagramLayout, spec: DiagramSpec, engine: Mapping[str, Any], register: str = "turn"
) -> tuple[_Timeline, list[_Act], list[tuple[float, float, str]], float, tuple[ResolvedEdge, ...], Any]:
    """The turn walk, shared by every register that rides its clock: the
    timeline, the acts, their (start, clear, outcome) windows, and the
    period. Legs pace kinematically off the FROZEN connector lengths. A
    METERED register expands the leading repeat act so the period tells
    the gauge's WHOLE story (the corpus meters): budget-n runs n draining
    turns before the resolution; the accumulator compounds — turn j banks
    j segments, so k turns where 1+2+..+k covers n."""
    edges = resolved_edges(spec)
    sh = classify_loop(spec, edges)
    acts = _derive_acts(spec, edges, sh)
    meter_n = next((e.meter for e in edges if e.meter and e.circuit == "return"), 0)
    if meter_n and register in ("budget", "accumulate"):
        i_rep = next((i for i, a in enumerate(acts) if a.outcome == "repeat"), None)
        if i_rep is not None:
            if register == "budget":
                k = int(meter_n)
            else:
                k = 1
                while k * (k + 1) // 2 < int(meter_n):
                    k += 1
            # The gauge's turns REPLACE the structural repeats entirely
            # (the accumulator specimen runs exactly its three banking
            # turns); the resolving acts follow unchanged.
            non_repeat = [a for a in acts if a.outcome != "repeat"]
            acts = [*([acts[i_rep]] * k), *non_repeat]
    lengths = {c.index: c.length for c in layout.connectors}
    wires = {c.index: ("C" if c.comp_wire else ("A" if c.accent_wire else "N")) for c in layout.connectors}
    # The gather bus's STEM answers every success: an arm ends at the
    # junction, and the stem (the one straight arm — the others fillet)
    # carries the arrival home (the unrolled specimen fires its stem in
    # each act, one dwell after the arm lands).
    stem_k: int | None = None
    arm_ks: set[int] = set()
    if sh.gather is not None:
        arm_ks = {k for k, _ in sh.gather[1]}
        paths = {c.index: c.path_d for c in layout.connectors}
        stem_k = next((k for k in sorted(arm_ks) if "Q" not in paths.get(k, "")), None)
    beat = _tcfg(engine, "turn_beat_s", 0.30)
    rest = _tcfg(engine, "period_rest_s", 1.40)
    tl = _Timeline()
    windows: list[tuple[float, float, str]] = []
    t = 0.0
    for act in acts:
        tap_turn = (
            act is acts[-1]
            and not any(n.station == "decision" for n in spec.nodes)
            and sh.ret is not None
            and any(e.circuit == "tap-in" for _, e in sh.taps)
        )
        clear = _walk_act(
            tl, act, spec, edges, sh, engine, lengths, wires, t0=t, tap_turn=tap_turn, arm_ks=arm_ks, stem_k=stem_k
        )
        for k, spans in tl.trails.items():
            tl.trails[k] = [(s, e, clear if c < 0 else c, z) for s, e, c, z in spans]
        windows.append((t, clear, act.outcome))
        t = clear + beat
    if acts and acts[-1].outcome == "terminal":
        # A terminal-ending period breathes longer: its held halo (1.77s)
        # runs into the rest — the corpus terminal specimens both rest 2.40
        # against the endless flywheel's 1.40.
        rest += _tcfg(engine, "terminal_rest_extra_s", 1.0)
    period = round(t - beat + rest, 3)
    return tl, acts, windows, period, edges, sh


def compile_turn(layout: DiagramLayout, spec: DiagramSpec, engine: Mapping[str, Any]) -> ChoreographyPlan:
    tl, acts, _windows, period, edges, sh = _turn_timeline(layout, spec, engine)
    return _emit(layout, spec, edges, sh, engine, tl, acts, period)


def _compile_metered(
    layout: DiagramLayout, spec: DiagramSpec, engine: Mapping[str, Any], *, register: str
) -> ChoreographyPlan:
    """A meter register: the turn timeline verbatim, plus the fill layer
    performing the declared gauge in the register's own arrow of time."""
    tl, acts, windows, period, edges, sh = _turn_timeline(layout, spec, engine, register)
    plan = _emit(layout, spec, edges, sh, engine, tl, acts, period)
    fills, kfs = _fill_layer(layout, engine, tl, windows, period, register, start_anim=len(plan.keyframes))
    return replace(plan, register=register, meter_fills=tuple(fills), keyframes=plan.keyframes + tuple(kfs))


def compile_laps(layout: DiagramLayout, spec: DiagramSpec, engine: Mapping[str, Any]) -> ChoreographyPlan:
    """Grows and resets with the outer turn (the lap-counter ruling)."""
    return _compile_metered(layout, spec, engine, register="laps")


def compile_budget(layout: DiagramLayout, spec: DiagramSpec, engine: Mapping[str, Any]) -> ChoreographyPlan:
    """Drains and refills (retry's budget: a spent attempt darkens its
    segment right-to-left; the fresh run refills)."""
    return _compile_metered(layout, spec, engine, register="budget")


def compile_accumulate(layout: DiagramLayout, spec: DiagramSpec, engine: Mapping[str, Any]) -> ChoreographyPlan:
    """Grows and holds (the accumulator: each turn banks its share; the
    gauge releases only on the period bar)."""
    return _compile_metered(layout, spec, engine, register="accumulate")


def _fill_layer(
    layout: DiagramLayout,
    engine: Mapping[str, Any],
    tl: _Timeline,
    windows: list[tuple[float, float, str]],
    period: float,
    register: str,
    *,
    start_anim: int,
) -> tuple[list[MeterFill], list[KeyframeBlock]]:
    """One keyframe block per segment, keyed to the timeline's own meter
    marks (exact lap/turn draw windows) — Python computes, templates stamp."""
    ramp = _tcfg(engine, "pop_s", 0.034)
    rcfg = (engine.get("choreography") or {}).get(register) or {}
    fills: list[MeterFill] = []
    kfs: list[KeyframeBlock] = []
    for strip in layout.meters:
        marks = sorted(tl.meter_marks.get(strip.edge_index, ()))
        n = len(strip.boxes)
        lit: list[list[tuple[float, float]]] = [[] for _ in range(n)]
        rest = 0.0
        if register == "laps":
            # Marks are inner-lap draws; each act's laps grow the gauge and
            # the act's clear resets it.
            for a0, a1, _outcome in windows:
                act_marks = [m for m in marks if a0 <= m[1] <= a1]
                for j, m in enumerate(act_marks[:n]):
                    lit[j].append((m[1], a1))
        elif register == "budget":
            # Full at rest; a repeat act SPENDS one segment right-to-left
            # the moment its return departs (the spend decided); the first
            # non-repeat act refills the gauge at its start.
            rest = 1.0
            floor = float(rcfg.get("drain_floor", 0.12))
            spent = 0
            drains: list[float] = []
            refill_t: float | None = None
            for a0, a1, outcome in windows:
                if outcome == "repeat" and spent < n:
                    m = next((mm for mm in marks if a0 <= mm[1] <= a1), (a1, a1))
                    drains.append(m[0])
                    spent += 1
                elif refill_t is None and drains:
                    refill_t = a0
            end = refill_t if refill_t is not None else period
            for i, t_spend in enumerate(drains):
                seg = n - 1 - i
                lit[seg].append((t_spend, end))
            fills_ops = (1.0, floor)
            for seg in range(n):
                anim = start_anim + len(kfs)
                kfs.append(KeyframeBlock(prop="opacity", body=_drain_body(lit[seg], period, ramp, *fills_ops)))
                fills.append(MeterFill(box=strip.boxes[seg], anim_index=anim, rest_opacity=rest))
            continue
        else:  # accumulate
            # The compounding bank (the accumulator specimen): turn j banks
            # j segments, a beat apart — 1, then 2, then 3 — and the gauge
            # holds, clearing just before the wrap.
            stagger = 0.16
            hold_end = max(0.0, period - 0.35)
            seg = 0
            for j, m in enumerate(marks, 1):
                for b in range(j):
                    if seg < n:
                        lit[seg].append((min(m[1] + b * stagger, hold_end - 0.1), hold_end))
                        seg += 1
            while seg < n:  # a remainder banks on the last turn
                lit[seg].append((marks[-1][1] if marks else 0.0, hold_end))
                seg += 1
        peak = float(rcfg.get("fill_opacity", 1.0))
        for seg in range(n):
            anim = start_anim + len(kfs)
            kfs.append(KeyframeBlock(prop="opacity", body=_fill_body(lit[seg], period, ramp, peak)))
            fills.append(MeterFill(box=strip.boxes[seg], anim_index=anim, rest_opacity=rest))
    return fills, kfs


def _fill_body(windows: list[tuple[float, float]], period: float, ramp: float, peak: float) -> str:
    """Lit windows -> opacity stops: dark, ramp up at start, hold, release
    at end (a window ending on the period bar releases there)."""
    stops = ["0% { opacity: 0; }"]
    for t0, t1 in sorted(windows):
        p0, p_up = _pct(t0, period), _pct(t0 + ramp, period)
        p1 = _pct(t1, period)
        if p0 > 0:
            stops.append(f"{_fmt_pct(p0)}% {{ opacity: 0; }}")
        stops.append(f"{_fmt_pct(p_up)}% {{ opacity: {peak}; }}")
        stops.append(f"{_fmt_pct(min(p1, 99.99))}% {{ opacity: {peak}; }}")
        if p1 < 99.5:
            stops.append(f"{_fmt_pct(min(p1 + _pct(ramp, period), 99.99))}% {{ opacity: 0; }}")
    stops.append("100% { opacity: 0; }")
    return " ".join(stops)


def _drain_body(windows: list[tuple[float, float]], period: float, ramp: float, full: float, floor: float) -> str:
    """Budget's inverse fill: full, step DOWN to the floor at each drain
    window's start, back to full at its end (the refill)."""
    stops = [f"0% {{ opacity: {full}; }}"]
    for t0, t1 in sorted(windows):
        p0, p_dn = _pct(t0, period), _pct(t0 + ramp, period)
        p1, p_up = _pct(t1, period), _pct(t1 + ramp, period)
        if p0 > 0:
            stops.append(f"{_fmt_pct(p0)}% {{ opacity: {full}; }}")
        stops.append(f"{_fmt_pct(p_dn)}% {{ opacity: {floor}; }}")
        stops.append(f"{_fmt_pct(min(p1, 99.99))}% {{ opacity: {floor}; }}")
        if p1 < 99.5:
            stops.append(f"{_fmt_pct(min(p_up, 99.99))}% {{ opacity: {full}; }}")
    stops.append(f"100% {{ opacity: {full}; }}")
    return " ".join(stops)


_REGISTER_TOPOLOGIES: dict[str, tuple[str, ...]] = {
    "turn": (Topology.LOOP.value,),
    "laps": (Topology.LOOP.value,),
    "budget": (Topology.LOOP.value,),
    "accumulate": (Topology.LOOP.value,),
}
_CHOREOGRAPHERS: dict[str, Callable[[DiagramLayout, DiagramSpec, Mapping[str, Any]], ChoreographyPlan]] = {
    "turn": compile_turn,
    "laps": compile_laps,
    "budget": compile_budget,
    "accumulate": compile_accumulate,
}


def _derive_acts(spec: DiagramSpec, edges: tuple[ResolvedEdge, ...], sh: Any) -> list[_Act]:
    """Act derivation from structure — turn counts are structural functions:
    endless = 1 act · +accumulator = 2 · +tap = 3 · bounded = the minimal
    branch-covering path set, repeats first then terminals ascending by
    decision depth, every terminal demonstrated once. The unrolled ladder's
    acts are its scenarios verbatim (succeeds on attempt 1..n, then the
    exhaust)."""
    out_of: dict[int, list[tuple[int, ResolvedEdge]]] = {}
    for k, e in sh.forward:
        out_of.setdefault(e.source, []).append((k, e))
    decisions = {i for i, n in enumerate(spec.nodes) if n.station == "decision"}
    scope_ids = set(sh.members)
    if sh.ret is None and sh.gather is not None:
        g, sources = sh.gather
        chain = {e.source: (k, e) for k, e in sh.forward}
        arm_of = {e.source: (k, e) for k, e in sources}
        order: list[int] = []
        i = sh.entry
        guard = 0
        while guard < 64 and i in arm_of:
            guard += 1
            order.append(i)
            nxt = chain.get(i)
            if nxt is None:
                break
            i = nxt[1].target
        acts: list[_Act] = []
        for idx, src in enumerate(order):
            taken = [chain[order[j]][0] for j in range(idx)]
            acts.append(_Act(edges=[*taken, arm_of[src][0]], outcome="terminal", branches=frozenset(), terminal=g))
        exhaust = [chain[s][0] for s in order if s in chain]
        if exhaust:
            last_target = edges[exhaust[-1]].target
            if spec.nodes[last_target].station == "terminal":
                acts.append(_Act(edges=exhaust, outcome="terminal", branches=frozenset(), terminal=last_target))
        return acts
    if not decisions:
        path = _endless_path(sh, out_of)
        crosses = any(edges[k].target in scope_ids for k in path[:-1])
        n_acts = 1
        if any(e.accumulates for _, e in [sh.ret]):
            n_acts = 2
        if any(e.circuit == "tap-in" for _, e in sh.taps):
            n_acts = 3
        return [
            _Act(edges=list(path), outcome="repeat", branches=frozenset(), crosses_scope=crosses) for _ in range(n_acts)
        ]
    candidates = _enumerate_paths(spec, sh, out_of)
    repeats = [c for c in candidates if c.outcome == "repeat"]
    terminals = [c for c in candidates if c.outcome == "terminal"]
    # Repeats lead the film, and within each group the ADVANCE route leads —
    # the improving turn keeps, the finishing turn improves-then-stops (the
    # corpus's own act order); terminals ascend by decision depth.
    repeats.sort(key=lambda c: (_discard_branches(spec, edges, c), len(c.branches)))
    terminals.sort(key=lambda c: (len(c.branches), _discard_branches(spec, edges, c)))
    selected: list[_Act] = []
    covered: set[tuple[int, int]] = set()
    terms_seen: set[int] = set()
    for cand in [*repeats, *terminals]:
        fresh = cand.branches - covered
        first_term = cand.terminal is not None and cand.terminal not in terms_seen
        if fresh or first_term:
            selected.append(cand)
            covered |= cand.branches
            if cand.terminal is not None:
                terms_seen.add(cand.terminal)
    seen_scope = False
    for act in selected:
        act.crosses_scope = any(edges[k].target in scope_ids for k in act.edges)
        if act.crosses_scope and not seen_scope:
            # The first demonstration of a scope lingers: its inner loop
            # spins two laps where later crossings pass with one
            # (cycle-nested's own turn structure).
            act.slots = 2
            seen_scope = True
    return selected


def _discard_branches(spec: DiagramSpec, edges: tuple[ResolvedEdge, ...], act: _Act) -> int:
    """How many of this path's steps land on discard/exhausted ground — the
    advance route counts zero and leads its group."""
    return sum(1 for k in act.edges if spec.nodes[edges[k].target].partition in ("discard", "exhausted"))


def _endless_path(sh: Any, out_of: dict[int, list[tuple[int, ResolvedEdge]]]) -> list[int]:
    path: list[int] = []
    i = sh.entry
    guard = 0
    while guard < 64:
        guard += 1
        outs = out_of.get(i, [])
        if not outs:
            break
        k, e = outs[0]
        path.append(k)
        i = e.target
    path.append(sh.ret[0])
    return path


def _enumerate_paths(spec: DiagramSpec, sh: Any, out_of: dict[int, list[tuple[int, ResolvedEdge]]]) -> list[_Act]:
    """Every root-to-outcome path over the decision tree of one turn."""
    ret_k, ret_e = sh.ret
    results: list[_Act] = []

    def walk(i: int, taken: list[int], branches: set[tuple[int, int]], guard: int) -> None:
        if guard > 64:
            return
        node = spec.nodes[i]
        if node.station == "terminal":
            results.append(_Act(edges=list(taken), outcome="terminal", branches=frozenset(branches), terminal=i))
            return
        if ret_e.source == i and node.station == "decision":
            # The return exit is one of this decision's branches.
            results.append(_Act(edges=[*taken, ret_k], outcome="repeat", branches=frozenset({*branches, (i, ret_k)})))
        outs = out_of.get(i, [])
        if not outs and ret_e.source == i:
            results.append(_Act(edges=[*taken, ret_k], outcome="repeat", branches=frozenset(branches)))
            return
        for k, e in outs:
            b = {*branches, (i, k)} if node.station == "decision" else branches
            walk(e.target, [*taken, k], b, guard + 1)

    walk(sh.entry, [], set(), 0)
    return results


def _nid(spec: DiagramSpec, i: int) -> str:
    return spec.nodes[i].id or f"n{i}"


def _walk_act(
    tl: _Timeline,
    act: _Act,
    spec: DiagramSpec,
    edges: tuple[ResolvedEdge, ...],
    sh: Any,
    engine: Mapping[str, Any],
    lengths: Mapping[int, float],
    wires: Mapping[int, str],
    *,
    t0: float,
    tap_turn: bool = False,
    arm_ks: set[int] | None = None,
    stem_k: int | None = None,
) -> float:
    """One turn: the route draws leg by leg at kinematic pace, dwelling at
    arrivals, and returns the turn's CLEAR time (trail windows are patched
    with it by the caller). The easing envelope spans the turn: first leg
    in, middles linear, the last leg out."""
    dwell = _tcfg(engine, "dwell_s", 0.10)
    dwell_dec = _tcfg(engine, "dwell_decision_s", 0.10)
    preflash = _tcfg(engine, "guard_preflash_s", 0.15)
    clear_hold = _tcfg(engine, "clear_hold_s", 0.10)
    halo_hold = _tcfg(engine, "halo_hold_s", 0.77)
    terminal_hold = _tcfg(engine, "terminal_hold_s", 1.77)
    tint_hold = _tcfg(engine, "tint_hold_s", 0.95)
    knock = _tcfg(engine, "tap_knock_s", 0.60)
    decisions = {i for i, n in enumerate(spec.nodes) if n.station == "decision"}
    scope_ids = set(sh.members)
    # The unrolled ladder's rungs ARE its deliberation: the fail-and-wait
    # chips between attempts tint in the deliberation ink, exactly like a
    # decision's quiet branch (the unrolled specimen's decide-hued chips).
    ladder = {e2.source for _, e2 in sh.gather[1]} if sh.gather is not None else set()
    t = t0
    drawn: set[int] = set()
    if tap_turn:
        # The interrupted turn (once per period, arranged by the caller as
        # the last endless act): the knock lands while the loop rests, the
        # target holds, and the route then answers.
        tap_k, tap_e = next((k, e) for k, e in sh.taps if e.circuit == "tap-in")
        tl.trail(tap_k, t, t + knock, -1.0, _EASE_IN)
        if tap_e.label:
            tl.chip(tap_k, max(t0, t - preflash), t + knock)
        tl.halo(f"hold:{_nid(spec, tap_e.target)}", t + knock, t + knock + halo_hold)
        t += knock + dwell
    n_edges = len(act.edges)
    for pos, k in enumerate(act.edges):
        e = edges[k]
        ease = _EASE_IN if pos == 0 else (_EASE_OUT if pos == n_edges - 1 else "linear")
        dur = _leg_s(engine, lengths.get(k, 100.0))
        if e.label and e.label_style == "chip":
            # Every chip lights with its leg (the corpus tint groups): a
            # guard holds through its branch, any other chip holds the
            # tint beat. Hue is the branch's own ink — complement stays
            # complement, a decision's quiet branch takes the deliberation
            # ink, everything else lights in the accent.
            # A RETURN chip is the loop's own continue — it tints advance
            # even when it leaves a decision (nsi's "no · go again" tints
            # advance from the Done? diamond); only forward branches take
            # the deliberation ink.
            deliberate = (
                (e.source in decisions or (e.source in ladder and e.target in ladder))
                and wires.get(k) != "A"
                and e.circuit != "return"
            )
            to_discard = spec.nodes[e.target].partition in ("discard", "exhausted")
            hue = "C" if (wires.get(k) == "C" or to_discard) else ("W" if deliberate else "A")
            start = max(t0, t - preflash)
            end = t + dur if e.source in decisions else min(t + dur, start + tint_hold)
            tl.chip(k, start, end, hue=hue)
        tl.trail(k, t, t + dur, -1.0, ease)
        drawn.add(k)
        if e.circuit == "return":
            tl.meter_mark(k, t, t + dur)
        t += dur
        if arm_ks and k in arm_ks and stem_k is not None and k != stem_k:
            # A filleted arm dead-ends at the junction — the stem draws the
            # last leg home so every success visibly reaches the terminal.
            t += dwell
            stem_dur = _leg_s(engine, lengths.get(stem_k, 100.0))
            tl.trail(stem_k, t, t + stem_dur, -1.0, "linear")
            t += stem_dur
        tgt = e.target
        node = spec.nodes[tgt]
        key = _nid(spec, tgt)
        # The branch's ink follows its destination: a leg into a discard/
        # exhausted partition carries the complement even when its wire is
        # muted (the corpus's discard-hued fail halo and arrowhead).
        leg_hue = "C" if (wires.get(k) == "C" or spec.nodes[e.target].partition in ("discard", "exhausted")) else "A"

        if tgt in scope_ids:
            # The lingering first crossing spins the gauge's own count of
            # laps when the inner return carries a meter (the laps specimen
            # fills one segment per lap, all three in the demonstrated
            # turn); an unmetered scope keeps the corpus's two.
            inner_ret_e = sh.inner_ret.get(tgt)
            meter_laps = int(inner_ret_e[1].meter) if inner_ret_e is not None and inner_ret_e[1].meter else 0
            laps = (meter_laps or 2) if act.slots > 1 else 1
            # One dwell after the entry arrival before the inner circuit
            # spins (the corpus paces the boundary like any station);
            # _scope_laps already dwells after its last leg, so the exit
            # leg follows at exactly one dwell — never two.
            lap_time = _scope_laps(tl, sh, tgt, edges, engine, lengths, wires, t + dwell, laps, drawn)
            tl.halo(f"scope:{key}", t, t + dwell + lap_time)
            t += dwell + lap_time
        elif node.station == "terminal":
            # The completion read: the terminal's halo holds well past its
            # own turn's clear — the corpus terminals glow 1.77s into the
            # dark beat so the outcome lands before the loop restarts.
            tl.halo(f"hold:{key}", t, t + terminal_hold, hue=leg_hue)
            t += dwell
        elif node.station == "decision":
            # A decision announces its arrival like every other station:
            # its rhombus outline lights in the deliberation hue for the
            # standard glow, keeping the whole route's rhythm uniform. The
            # guard chips and the question ink carry the rest of the
            # deliberation.
            tl.halo(f"flash:{key}", t, t + halo_hold, hue="W")
            t += dwell_dec
        else:
            # Arrival halos ride the arriving leg's hue — the corpus draws
            # every route in the accent and halos match it, not the
            # station's partition.
            tl.halo(f"flash:{key}", t, t + halo_hold, hue=leg_hue)
            t += dwell
        # A tap-out reports the aside as the route passes its source: the
        # leg draws concurrently with the dwell in the muted aside tone,
        # its external target glowing quietly. Without this the tap-out
        # edge never performs at all (the trace audit's coverage gap).
        for tap_k, tap_e in sh.taps:
            if tap_e.circuit == "tap-out" and tap_e.source == tgt and tap_k not in drawn:
                out_dur = _leg_s(engine, lengths.get(tap_k, 100.0))
                tl.trail(tap_k, t, t + out_dur, -1.0, "linear")
                drawn.add(tap_k)
                if tap_e.label and tap_e.label_style == "chip":
                    tl.chip(tap_k, max(t0, t - preflash), min(t + out_dur, t + tint_hold))
                tl.halo(f"flash:{_nid(spec, tap_e.target)}", t + out_dur, t + out_dur + halo_hold, hue="N")
    return t + clear_hold


def _scope_laps(
    tl: _Timeline,
    sh: Any,
    scope_i: int,
    edges: tuple[ResolvedEdge, ...],
    engine: Mapping[str, Any],
    lengths: Mapping[int, float],
    wires: Mapping[int, str],
    t0: float,
    laps: int,
    drawn: set[int],
) -> float:
    """The inner circuit spins its laps while the outer pulse rests at the
    boundary. A trail draws ONCE and stays lit — later laps run on the
    comet head alone, at the same kinematic pace, over the lit route (the
    nested specimens' own replay mechanism; a trail that re-drew would
    visibly retract backwards between laps). Inner chips light on their
    first draw like any other chip."""
    dwell = _tcfg(engine, "dwell_s", 0.10)
    preflash = _tcfg(engine, "guard_preflash_s", 0.15)
    tint_hold = _tcfg(engine, "tint_hold_s", 0.95)
    inner = [k for k, _ in sh.inner.get(scope_i, [])]
    inner_ret = sh.inner_ret.get(scope_i)
    t = t0

    def _leg(k: int, lap: int) -> None:
        nonlocal t
        dur = _leg_s(engine, lengths.get(k, 100.0))
        e = edges[k]
        if lap == 0 and e.label and e.label_style == "chip":
            hue = "C" if wires.get(k) == "C" else "A"
            start = max(t0, t - preflash)
            tl.chip(k, start, min(t + dur, start + tint_hold), hue=hue)
        if lap == 0 and k not in drawn:
            tl.trail(k, t, t + dur, -1.0, "linear")
            drawn.add(k)
        else:
            tl.head(k, t, t + dur)
        if e.circuit == "return":
            tl.meter_mark(k, t, t + dur)
        t += dur + dwell

    for lap in range(laps):
        for k in inner:
            _leg(k, lap)
        if inner_ret is not None:
            _leg(inner_ret[0], lap)
    return t - t0


# ── Emission ────────────────────────────────────────────────────────────


def _pct(t: float, period: float) -> float:
    return round(max(0.0, min(100.0, t / period * 100.0)), 3)


def _fmt_pct(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s or "0"


def _fmt_num(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s or "0"


def _stop(p: float, decl: str, tf: str = "") -> str:
    tail = f" animation-timing-function:{tf};" if tf else ""
    return f"{_fmt_pct(p)}% {{ {decl};{tail} }}"


def _marker_trim(marker_d: str, path_d: str) -> float:
    """How far the drawn arrowhead reaches back along the route from the
    path's end. The corpus stops the lit route at the chevron's BASE and
    draws the head beyond it (fwv: the wire ends at 176.4, the chevron
    spans 176.4->187) — an overlay riding the full path would fringe its
    washes around the arrowhead and touch the card face."""
    pts = [(float(x), float(y)) for x, y in re.findall(r"(-?\d+\.?\d*),(-?\d+\.?\d*)", marker_d)]
    pairs = re.findall(r"(-?\d+\.?\d*),(-?\d+\.?\d*)", path_d)
    if not pts or len(pairs) < 2:
        return 0.0
    x1, y1 = float(pairs[-1][0]), float(pairs[-1][1])
    x0, y0 = float(pairs[-2][0]), float(pairs[-2][1])
    seg = math.hypot(x1 - x0, y1 - y0) or 1.0
    ux, uy = (x1 - x0) / seg, (y1 - y0) / seg
    # Reach = the marker's extent back along the arrival tangent.
    return max(0.0, max((x1 - px) * ux + (y1 - py) * uy for px, py in pts))


def _trim_route(path_d: str, trim: float) -> str:
    """The route minus its arrowhead. A straight close pulls the endpoint
    back along its own segment; a curved close (C/Q) is SPLIT by arc
    length — the chord shortcut fails exactly where merges arrive, because
    an S-curve's final chord can be shorter than the trim (the untrimmed
    trail then runs through the chevron: the crevice-arrow defect)."""
    if trim <= 0:
        return path_d
    cmd_m = None
    for m in re.finditer(r"[LCQ](?=[^LCQAZ]*$)", path_d):
        cmd_m = m
    ms = list(re.finditer(r"(-?\d+\.?\d*),(-?\d+\.?\d*)", path_d))
    if cmd_m is None or len(ms) < 2:
        return path_d
    cmd = cmd_m.group(0)
    pts = [(float(a), float(b)) for a, b in (mm.groups() for mm in ms)]
    if cmd == "L":
        x0, y0 = pts[-2]
        x1, y1 = pts[-1]
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg <= trim + 1.0:
            return path_d
        ux, uy = (x1 - x0) / seg, (y1 - y0) / seg
        m = ms[-1]
        tip = f"{_fmt_num(round(x1 - ux * trim, 2))},{_fmt_num(round(y1 - uy * trim, 2))}"
        return f"{path_d[: m.start()]}{tip}{path_d[m.end() :]}"
    n_ctrl = 3 if cmd == "C" else 2
    if len(pts) < n_ctrl + 1:
        return path_d
    p = [pts[-(n_ctrl + 1)], *pts[-n_ctrl:]]

    def _at(t: float) -> tuple[float, float]:
        q = list(p)
        while len(q) > 1:
            q = [((1 - t) * a[0] + t * b[0], (1 - t) * a[1] + t * b[1]) for a, b in itertools.pairwise(q)]
        return q[0]

    samples = [_at(i / 48) for i in range(49)]
    arcs = [0.0]
    for a, b in itertools.pairwise(samples):
        arcs.append(arcs[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    if arcs[-1] <= trim + 1.0:
        return path_d
    target = arcs[-1] - trim
    i = next(j for j, d in enumerate(arcs) if d >= target)
    t_cut = (i - 1 + (target - arcs[i - 1]) / max(arcs[i] - arcs[i - 1], 1e-6)) / 48
    # de Casteljau: keep [0, t_cut] — control points from the split ladder.
    ladder = [list(p)]
    while len(ladder[-1]) > 1:
        q = ladder[-1]
        ladder.append(
            [((1 - t_cut) * a[0] + t_cut * b[0], (1 - t_cut) * a[1] + t_cut * b[1]) for a, b in itertools.pairwise(q)]
        )
    new_pts = [rung[0] for rung in ladder[1:]]
    body = " ".join(f"{_fmt_num(round(x, 2))},{_fmt_num(round(y, 2))}" for x, y in new_pts)
    return f"{path_d[: cmd_m.end()]} {body}"


def _trail_body(windows: list[tuple[float, float, float, str]], length: float, period: float) -> str:
    """The lit route: park at ``length``, DRAW to 0 with the leg's own
    easing, hold lit, step back to park at the turn's clear — the corpus's
    trail keyframes verbatim. ONE draw per clear: a second window inside
    the same turn is a replay the head layer carries — a trail stop pair
    here would animate the offset back to park, visibly retracting the lit
    route backwards."""
    park = f"stroke-dashoffset:{_fmt_num(length)}"
    lit = "stroke-dashoffset:0"
    stops = [_stop(0.0, park, "linear")]
    deduped: list[tuple[float, float, float, str]] = []
    clears_seen: set[float] = set()
    for w in sorted(windows):
        if w[2] not in clears_seen:
            clears_seen.add(w[2])
            deduped.append(w)
    for t0, t1, clear, ease in deduped:
        stops.append(_stop(_pct(t0, period), park, ease))
        stops.append(_stop(_pct(t1, period), lit, "linear"))
        p_clear = min(_pct(clear, period), 99.9)
        stops.append(_stop(p_clear, lit, "step-end"))
        stops.append(_stop(min(p_clear + 0.05, 99.95), park, "linear"))
    stops.append(f"100% {{ {park}; }}")
    return " ".join(stops)


def _head_body(windows: list[tuple[float, float, float, str]], head: float, length: float, period: float) -> str:
    """The soft head riding the drawing tip: parked before the path, swept
    fully past it on the leg's own easing, snapped home."""
    park = f"stroke-dashoffset:{_fmt_num(head)}"
    gone = f"stroke-dashoffset:{_fmt_num(-length)}"
    stops = [_stop(0.0, park, "linear")]
    for t0, t1, _clear, ease in sorted(windows):
        stops.append(_stop(_pct(t0, period), park, ease))
        p1 = min(_pct(t1, period), 99.9)
        stops.append(_stop(p1, gone, "step-end"))
        stops.append(_stop(min(p1 + 0.05, 99.95), park, "linear"))
    stops.append(f"100% {{ {park}; }}")
    return " ".join(stops)


def _marker_body(windows: list[tuple[float, float, float, str]], period: float, pop: float) -> str:
    """The arrowhead pops as its leg completes, rides the lit route, and
    hides at the clear."""
    stops = [_stop(0.0, "opacity:0", "linear")]
    for _t0, t1, clear, _ease in sorted(windows):
        p1 = _pct(t1, period)
        stops.append(_stop(max(0.0, p1 - _pct(pop, period)), "opacity:0", "linear"))
        stops.append(_stop(p1, "opacity:1", "linear"))
        p_clear = min(_pct(clear, period), 99.9)
        stops.append(_stop(p_clear, "opacity:1", "step-end"))
        stops.append(_stop(min(p_clear + 0.05, 99.95), "opacity:0", "linear"))
    stops.append("100% { opacity:0; }")
    return " ".join(stops)


def _glow_body(windows: list[tuple[float, float]], period: float, pop: float, fade: float, peak: float) -> str:
    """Arrival glow: eased pop, hold, eased fade — the corpus's halo letters."""
    stops = [_stop(0.0, "opacity:0", "linear")]
    for t0, hold_end in sorted(windows):
        stops.append(_stop(_pct(t0, period), "opacity:0", _POP))
        stops.append(_stop(_pct(t0 + pop, period), f"opacity:{peak}", "linear"))
        p_hold = min(_pct(hold_end, period), 99.8)
        stops.append(_stop(p_hold, f"opacity:{peak}", _FADE))
        stops.append(_stop(min(_pct(hold_end + fade, period), 99.9), "opacity:0", "linear"))
    stops.append("100% { opacity:0; }")
    return " ".join(stops)


def _emit(
    layout: DiagramLayout,
    spec: DiagramSpec,
    edges: tuple[ResolvedEdge, ...],
    sh: Any,
    engine: Mapping[str, Any],
    tl: _Timeline,
    acts: list[_Act],
    period: float,
) -> ChoreographyPlan:
    head = _tcfg(engine, "pulse_head", 18.0)
    pop = _tcfg(engine, "pop_s", 0.034)
    fade = _tcfg(engine, "fade_s", 0.088)
    halo_inflate = _tcfg(engine, "halo_inflate", 0.0)
    halo_op = _tcfg(engine, "halo_opacity", 1.0)
    layers_raw = ((engine.get("choreography") or {}).get("turn") or {}).get("pulse_layers") or [
        [3.6, 1.0, 0.0],
        [5.4, 0.30, 0.058],
        [7.5, 0.13, 0.115],
    ]
    pulse_layers = tuple((float(w), float(o), float(d)) for w, o, d in layers_raw)
    conn_by_index = {c.index: c for c in layout.connectors}
    node_by_id = {n.node_id: n for n in layout.nodes}
    chip_by_edge = {a.edge_index: a for a in layout.annotations if a.kind == "edge-chip" and a.edge_index >= 0}
    keyframes: list[KeyframeBlock] = []
    trails: list[PulseOverlay] = []
    pulses: list[PulseOverlay] = []
    halos: list[HaloFlash] = []
    tints: list[ChipTint] = []
    marker_fades: dict[int, int] = {}
    marker_hues: dict[int, str] = {}
    beats: dict[str, tuple[tuple[float, float], ...]] = {}

    def _hue_of_edge(k: int) -> str:
        # The route draws in the accent — the lit line IS the pass — except
        # a complement-graded branch (wire-grade hue) and the tap-out aside,
        # which reports in the muted tone, never the route's own ink.
        if k < len(edges) and edges[k].circuit == "tap-out":
            return "N"
        if k < len(edges) and spec.nodes[edges[k].target].partition in ("discard", "exhausted"):
            return "C"
        c = conn_by_index.get(k)
        return "C" if (c is not None and c.comp_wire) else "A"

    # The overlays stop at the arrowhead's BASE (the corpus law): the route
    # they ride is the path minus the chevron's reach, so the washes never
    # fringe around the arrow or touch the card face. A merge sibling that
    # SHARES its arrival point with a marker-ed leg (the converging S-curves
    # draw ONE chevron between them) trims by the shared chevron's reach —
    # its own marker_d is empty, but its trail would otherwise run straight
    # through the shared arrowhead.
    trims: dict[int, float] = {}
    marked_ends: list[tuple[float, float, float]] = []
    for conn in layout.connectors:
        if conn.marker_d:
            t_reach = _marker_trim(conn.marker_d, conn.path_d)
            trims[conn.index] = t_reach
            pe = re.findall(r"(-?\d+\.?\d*),(-?\d+\.?\d*)", conn.path_d)
            if pe:
                marked_ends.append((float(pe[-1][0]), float(pe[-1][1]), t_reach))
    for conn in layout.connectors:
        if conn.index in trims:
            continue
        pe = re.findall(r"(-?\d+\.?\d*),(-?\d+\.?\d*)", conn.path_d)
        if pe:
            x, y = float(pe[-1][0]), float(pe[-1][1])
            trims[conn.index] = next((t for ex, ey, t in marked_ends if abs(ex - x) < 1.5 and abs(ey - y) < 1.5), 0.0)
    for k, windows in sorted(tl.trails.items()):
        c = conn_by_index.get(k)
        if c is None:
            continue
        trim = trims.get(k, 0.0)
        route_d = _trim_route(c.path_d, trim) if trim else c.path_d
        run = max(round(c.length - trim, 2), 1.0)
        anim = len(keyframes)
        keyframes.append(KeyframeBlock(prop="stroke-dashoffset", body=_trail_body(windows, run, period)))
        trails.append(
            PulseOverlay(
                connector_index=k,
                hue=_hue_of_edge(k),
                dasharray=_fmt_num(run),
                rest_offset=run,
                anim_index=anim,
                route_d=route_d,
            )
        )
        # The comet head runs every sweep: each trail-draw window plus any
        # head-only replays (an inner circuit's later laps).
        head_windows = sorted(windows + [(h0, h1, 0.0, hz) for h0, h1, hz in tl.heads.get(k, [])])
        anim = len(keyframes)
        keyframes.append(KeyframeBlock(prop="stroke-dashoffset", body=_head_body(head_windows, head, run, period)))
        pulses.append(
            PulseOverlay(
                connector_index=k,
                hue=_hue_of_edge(k),
                dasharray=f"{_fmt_num(head)} {_fmt_num(run + head)}",
                rest_offset=head,
                anim_index=anim,
                route_d=route_d,
            )
        )
        if c.marker_d:
            anim = len(keyframes)
            keyframes.append(KeyframeBlock(prop="opacity", body=_marker_body(windows, period, pop)))
            marker_fades[k] = anim
            marker_hues[k] = _hue_of_edge(k)
        beats[f"e{k}"] = tuple((round(t0, 2), round(t1, 2)) for t0, t1, _c, _z in sorted(windows))
    scope_bands = {b.header.text: b for b in layout.lane_bands}
    for key, gwindows in sorted(tl.halos.items()):
        kind, _, ident = key.partition(":")
        anim = len(keyframes)
        body = _glow_body(gwindows, period, pop, fade, halo_op)
        halo: HaloFlash | None = None
        if kind == "scope":
            band = next(iter(scope_bands.values()), None)
            if band is not None:
                b = band.box
                halo = HaloFlash(
                    shape="rect",
                    hue="A",
                    anim_index=anim,
                    box=RectSpec(
                        x=b.x - halo_inflate,
                        y=b.y - halo_inflate,
                        w=b.w + 2 * halo_inflate,
                        h=b.h + 2 * halo_inflate,
                        rx=b.rx + halo_inflate,
                    ),
                )
        else:
            n = node_by_id.get(ident)
            if n is not None and n.shape == "diamond":
                # The decision's halo is its own rhombus, each vertex pushed
                # ``halo_diamond_inflate`` out so the ring sits clear of the
                # border, in the deliberation hue.
                b = n.box
                di = _tcfg(engine, "halo_diamond_inflate", 3.0)
                dcx, dcy = b.x + b.w / 2, b.y + b.h / 2
                d = (
                    f"M {_fmt_num(round(dcx, 2))},{_fmt_num(round(b.y - di, 2))}"
                    f" L {_fmt_num(round(b.x + b.w + di, 2))},{_fmt_num(round(dcy, 2))}"
                    f" L {_fmt_num(round(dcx, 2))},{_fmt_num(round(b.y + b.h + di, 2))}"
                    f" L {_fmt_num(round(b.x - di, 2))},{_fmt_num(round(dcy, 2))} Z"
                )
                halo = HaloFlash(shape="path", hue=tl.halo_hues.get(key) or "W", anim_index=anim, d=d)
            elif n is not None:
                b = n.box
                # The arriving leg's hue when the walk recorded one (the
                # corpus law); the partition read covers the rest.
                hue = tl.halo_hues.get(key, "")
                if not hue:
                    hue = "A" if (kind == "hold" or spec.nodes[n.index].partition == "advance") else "N"
                    if spec.nodes[n.index].partition in ("discard", "exhausted"):
                        hue = "C"
                halo = HaloFlash(
                    shape="rect",
                    hue=hue,
                    anim_index=anim,
                    box=RectSpec(
                        x=b.x - halo_inflate,
                        y=b.y - halo_inflate,
                        w=b.w + 2 * halo_inflate,
                        h=b.h + 2 * halo_inflate,
                        rx=b.rx + halo_inflate,
                    ),
                )
        if halo is None:
            continue
        keyframes.append(KeyframeBlock(prop="opacity", body=body))
        halos.append(halo)
        beats[key] = tuple((round(t0, 2), round(t1, 2)) for t0, t1 in sorted(gwindows))
    for k, cwindows in sorted(tl.chips.items()):
        ann = chip_by_edge.get(k)
        if ann is None or ann.box is None:
            continue
        # The corpus tint groups: the chip's own markup re-stamped in the
        # branch hue — never an inflated outline around it.
        anim = len(keyframes)
        keyframes.append(KeyframeBlock(prop="opacity", body=_glow_body(cwindows, period, pop, fade, 1.0)))
        tints.append(ChipTint(box=ann.box, lines=tuple(ann.lines), hue=tl.chip_hues.get(k, "A"), anim_index=anim))
        beats[f"chip:e{k}"] = tuple((round(t0, 2), round(t1, 2)) for t0, t1 in sorted(cwindows))
    _ = (edges, sh)
    act_names = [f"{a.outcome} ({a.slots} slot{'s' if a.slots > 1 else ''})" for a in acts]
    return ChoreographyPlan(
        register="turn",
        super_period_s=period,
        acts=tuple(act_names),
        legs_s={
            "k": _tcfg(engine, "leg_k", 0.058),
            "min": _tcfg(engine, "leg_min_s", 0.30),
            "max": _tcfg(engine, "leg_max_s", 1.30),
        },
        beats=beats,
        pulses=tuple(pulses),
        halos=tuple(halos),
        keyframes=tuple(keyframes),
        halo_stroke=_tcfg(engine, "halo_stroke", 2.0),
        trails=tuple(trails),
        marker_fades=marker_fades,
        marker_hues=marker_hues,
        trail_stroke=_tcfg(engine, "trail_stroke", 2.6),
        pulse_layers=pulse_layers,
        tints=tuple(tints),
    )
