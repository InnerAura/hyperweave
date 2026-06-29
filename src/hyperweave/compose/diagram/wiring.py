"""Kinetic wiring: edge geometries -> connector/particle/gradient placements.

The uniform half of the solve. Topology solvers compute WHERE an edge runs
(``EdgeGeo``); this module decides HOW it moves under the closed grammar —
track resolution (P3 semantic yield), ant delays, particle riders (with the
sequence replay clock), beam comets (relay slots / volley / arrivals), and
flow currents (streaming / circulation / hub current, arc-subdivided past
the sagitta threshold). Hues stay symbolic (@flow{i} / @signal /
@signal2) — the resolver substitutes genome hex; solvers never see it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram import motion as mo
from hyperweave.compose.diagram.paths import arc_d, point_on, subdivide_arc
from hyperweave.compose.diagram.records import (
    ConnectorPlacement,
    DiagramText,
    GradientSpec,
    LightLayer,
    ParticlePlacement,
)
from hyperweave.compose.matrix.cells import wrap_text_lines

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hyperweave.core.diagram import DiagramSpec, ResolvedEdge
    from hyperweave.core.matrix import GlyphTint
    from hyperweave.core.paradigm import DiagramTopologyChassis, ParadigmDiagramConfig


@dataclass(frozen=True, slots=True)
class EdgeGeo:
    """One edge's geometry as a solver hands it to ``wire_motion``."""

    index: int
    """Logical resolved-edge index (payload order); arc segments share it."""
    d: str
    sx: float
    sy: float
    tx: float
    ty: float
    length: float
    semantic_dash: str = ""
    """Long back/skip edges travel on the slower per-layout duration."""
    arc: tuple[float, float, float, float, float] | None = None
    """(cx, cy, r, a0_deg, a1_deg) when the path is a circular arc — flow
    subdivides deep arcs into chord-aligned segments."""
    label_pos: tuple[float, float] | None = None
    label_max_w: float = 0.0
    """Label truncation width; 0 falls back to the edge span. Short SM
    transitions let their labels overhang the gap (the canon places them
    above the pills, not inside the connector)."""
    label_anchor: str = "middle"
    track_override: str = ""
    """'static' forces the track regardless of motion — sequence message
    strokes are kind semantics (solid call / dashed return), never a march."""
    flow_side: int = 0
    """Begin-stagger side for hub currents (bilateral: left 0 / right 1)."""


@dataclass(frozen=True, slots=True)
class SolverContext:
    spec: DiagramSpec
    slug: str
    ch: DiagramTopologyChassis
    cfg: ParadigmDiagramConfig
    engine: Mapping[str, Any]
    edges: tuple[ResolvedEdge, ...]
    node_accents: tuple[int, ...]
    edge_accents: tuple[int, ...]
    motions: tuple[str, ...]
    lanes: tuple[int, ...]
    shrink: bool
    palette_len: int
    composite_only: bool
    fallback_applied: bool
    lane_offsets: tuple[float, ...] = ()
    """Per-edge reciprocal-lane offsets (G8): composition-aware gaps."""
    chrome: str = "card"
    """card | bare (F1): bare drops the masthead/footer and the substrate
    — presentational only, excluded from the envelope digest."""
    mono_triggers: list[str] = field(default_factory=list)
    glyph_registry: Mapping[str, Any] | None = None
    glyph_selections: tuple[GlyphTint, ...] = ()
    """Per-node tint SELECTION (per-slot > artifact > genome per-frame
    default); the rendered mode lands on each placement's GlyphArt."""


def _per_layout(table: Mapping[str, Any], slug: str) -> Any:
    return table.get(slug, table.get("default"))


def wire_motion(
    ctx: SolverContext, geos: list[EdgeGeo]
) -> tuple[tuple[ConnectorPlacement, ...], tuple[ParticlePlacement, ...], tuple[GradientSpec, ...]]:
    """Uniform kinetic wiring: each edge geometry gets its concrete motion's
    layers — ants delays, particle riders, beam comet gradients (relay
    slots / volley / arrivals), or flow currents (streaming / circulation /
    hub current, arc-subdivided past the sagitta threshold)."""
    engine = ctx.engine
    track_cfg = engine["track"]
    particle_cfg = engine["particle"]
    beam_cfg = engine["beam"]
    flow_cfg = engine["flow"]
    track_map = {str(k): str(v) for k, v in ctx.cfg.track_default_by_motion.items()}
    ant_step = float(_per_layout(engine["connector"]["ant_stagger"], ctx.slug) or 0)
    renders_labels = bool((engine.get("renders_edge_labels") or {}).get(ctx.slug, False))

    connectors: list[ConnectorPlacement] = []
    particles: list[ParticlePlacement] = []
    gradients: list[GradientSpec] = []

    beam_order = [g.index for g in geos if ctx.motions[g.index] == "beam" and not ctx.edges[g.index].inert]
    beam_choreo = mo.choreography_for(ctx.slug, "beam", engine["choreography"]) if beam_order else ""
    relay = mo.relay_slots(len(beam_order), beam_cfg["relay"]) if beam_choreo == "relay" else []
    flow_order = [g.index for g in geos if ctx.motions[g.index] == "flow" and not ctx.edges[g.index].inert]
    flow_choreo = mo.choreography_for(ctx.slug, "flow", engine["choreography"]) if flow_order else ""
    flow_dur_s = float(str(flow_cfg["dur"]).rstrip("s"))
    particle_seen = 0
    ant_seen = 0

    for geo in geos:
        edge = ctx.edges[geo.index]
        m = ctx.motions[geo.index]
        track = geo.track_override or mo.resolve_track(m, track_map=track_map, semantic_dash=geo.semantic_dash)
        inert = edge.inert
        if inert or track == "static":
            if m in ("beam", "flow") and not inert:
                static_dash = ""  # the faint tube under the light is solid
            else:
                static_dash = geo.semantic_dash or ("" if geo.track_override else str(engine["connector"]["dash"]))
        else:
            static_dash = ""
        # Edge labels wrap to two lines before ellipsizing (BUG-001): a short
        # edge span fits ~1.5 words, so a two-word label like "Claude Code"
        # would otherwise truncate mid-word. The stack centers vertically on
        # the label anchor — the edge has no container, so growth is free.
        label_lines: tuple[DiagramText, ...] = ()
        if renders_labels and edge.label and geo.label_pos is not None:
            max_w = geo.label_max_w or max(24.0, geo.length - 16.0)
            voice = ctx.cfg.edge_label_voice
            wrapped = wrap_text_lines(edge.label, max_w, voice, max_lines=2)
            lx, ly = geo.label_pos
            pitch = voice.size + 2.5
            n = len(wrapped)
            label_lines = tuple(
                DiagramText(
                    x=lx,
                    y=ly + (k - (n - 1) / 2.0) * pitch,
                    text=line,
                    cls="elbl",
                    anchor=geo.label_anchor,
                )
                for k, line in enumerate(wrapped)
            )
        layers: tuple[LightLayer, ...] = ()
        ant_delay = ""
        if not inert and track == "dash-march" and m in ("dash", "particle"):
            ant_delay = mo.stagger_begin(ant_seen, ant_step)
            ant_seen += 1
        if not inert and m == "particle":
            if ctx.slug == "sequence":
                # Single traversing particle (K-seq-v2): ONE persistent dot
                # hops message-to-message in replay order. Each message owns
                # a non-overlapping slot on one DERIVED clock (speed law +
                # gap beats + rest beat), so exactly one dot is visible at a
                # time — a single object travelling the trace at lawful
                # velocity. The semantic call/return strokes stay at full
                # weight beneath it (solid call, dashed return).
                seq_cfg = engine["sequence_replay"]
                replay_idx = [
                    g2.index for g2 in geos if ctx.motions[g2.index] == "particle" and not ctx.edges[g2.index].inert
                ]
                spans = [g2.length for g2 in geos if g2.index in set(replay_idx)]
                clock_s, slots = mo.replay_clock(
                    spans,
                    v_target=ctx.cfg.motion_v_target,
                    dur_min=ctx.cfg.motion_dur_min,
                    dur_max=ctx.cfg.motion_dur_max,
                    seq_cfg=seq_cfg,
                )
                slot = slots[replay_idx.index(geo.index)]
                fade = min(0.02, (slot[1] - slot[0]) * 0.15)
                kp, kt, ov, okt = mo.replay_particle_params(slot, fade)
                particles.append(
                    ParticlePlacement(
                        connector_index=len(connectors),
                        accent_index=ctx.edge_accents[geo.index],
                        r=float(particle_cfg["r"]),
                        dur=f"{clock_s:g}s",
                        opacity_values=ov,
                        opacity_keytimes=okt,
                        keypoints=kp,
                        keytimes_motion=kt,
                        calc_mode="linear",
                    )
                )
                particle_seen += 1
            else:
                # Constant velocity (K1): transit time follows path length;
                # departure staggers below stay untouched. On a marching
                # track the overtake cap keeps the particle visibly faster
                # than the texture's phase speed.
                dur_s = min(max(geo.length / ctx.cfg.motion_v_target, ctx.cfg.motion_dur_min), ctx.cfg.motion_dur_max)
                if track == "dash-march":
                    phase = abs(float(engine["track"]["march_offset_to"])) / float(
                        str(engine["track"]["march_dur"]).rstrip("s")
                    )
                    dur_s = min(dur_s, geo.length / (ctx.cfg.track_overtake_floor * phase))
                dur = f"{dur_s:.3f}s"
                step = float(_per_layout(particle_cfg["stagger"], ctx.slug) or 0)
                ramp = _per_layout(particle_cfg["opacity"], ctx.slug)
                particles.append(
                    ParticlePlacement(
                        connector_index=len(connectors),
                        accent_index=ctx.edge_accents[geo.index],
                        r=float(particle_cfg["r"]),
                        dur=dur,
                        begin=mo.stagger_begin(particle_seen, step),
                        opacity_values=str(ramp["values"]),
                        opacity_keytimes=str(ramp["keytimes"]),
                    )
                )
                particle_seen += 1
        if not inert and m == "beam":
            pos = beam_order.index(geo.index)
            hue_slot = ctx.edge_accents[geo.index]
            beam_travel: float | None = None
            if beam_choreo != "relay":
                clock_cfg = beam_cfg["arrivals"] if beam_choreo == "arrivals" else beam_cfg["volley"]
                clock_s = float(str(clock_cfg["dur"]).rstrip("s"))
                transit = min(max(geo.length / ctx.cfg.motion_v_target, ctx.cfg.motion_dur_min), ctx.cfg.motion_dur_max)
                beam_travel = round(min(max(transit / clock_s, 0.15), 0.9), 4)
            body, fil = mo.beam_gradients(
                id_base=f"g{len(connectors)}",
                x1=geo.sx,
                y1=geo.sy,
                x2=geo.tx,
                y2=geo.ty,
                length=geo.length,
                hue=f"@flow{hue_slot}" if hue_slot >= 0 else "@signal",
                hue2="@signal2" if beam_choreo == "relay" else None,
                choreo=beam_choreo,
                slot=relay[pos] if beam_choreo == "relay" else None,
                begin=mo.stagger_begin(pos, float(beam_cfg[beam_choreo]["stagger"])) if beam_choreo != "relay" else "",
                beam_cfg=beam_cfg,
                travel_end=beam_travel,
            )
            gradients.extend([body, fil])
            layers = (
                LightLayer(
                    kind="halo",
                    gradient_ref=body.id_suffix,
                    width=float(beam_cfg["halo_width"]),
                    opacity=float(beam_cfg["halo_opacity"]),
                    blur=True,
                ),
                LightLayer(kind="core", gradient_ref=body.id_suffix, width=float(beam_cfg["core_width"])),
                LightLayer(kind="filament", gradient_ref=fil.id_suffix, width=float(beam_cfg["filament_width"])),
            )
        if not inert and m == "flow":
            pos = flow_order.index(geo.index)
            if flow_choreo == "circulation":
                begin = mo.stagger_begin(pos, flow_dur_s / 4)
            elif flow_choreo == "streaming":
                begin = mo.stagger_begin(pos, float(flow_cfg["streaming_stagger"]))
            else:
                begin = mo.stagger_begin(pos, float(flow_cfg["hub_stagger"]))
                if geo.flow_side:
                    side = float(flow_cfg["hub_side_offset"])
                    begin = mo.fmt_s((0.0 if not begin else float(begin.rstrip("s"))) + side)
            hue_slot = ctx.edge_accents[geo.index]
            hue = f"@flow{hue_slot}" if hue_slot >= 0 else "@signal"
            if flow_choreo in ("circulation", "streaming"):
                hue = "@signal"  # one momentum / one stream — a single system hue
            if geo.arc is not None:
                cx, cy, r, a0, a1 = geo.arc
                segments = subdivide_arc(
                    a0, a1, r, float(flow_cfg["sagitta_threshold"]), int(flow_cfg["max_subdivisions"])
                )
                cum = 0.0
                for si, (s0, s1) in enumerate(segments):
                    p0, p1 = point_on(cx, cy, r, s0), point_on(cx, cy, r, s1)
                    seg_len = geo.length / len(segments)
                    g = mo.flow_gradient(
                        id_base=f"g{len(connectors)}s{si}",
                        x1=p0[0],
                        y1=p0[1],
                        x2=p1[0],
                        y2=p1[1],
                        length=seg_len,
                        hue=hue,
                        begin=begin if si == 0 else "",
                        flow_cfg=flow_cfg,
                        phase_px=cum,
                    )
                    gradients.append(g)
                    seg_layers = (
                        LightLayer(
                            kind="halo",
                            gradient_ref=g.id_suffix,
                            width=float(flow_cfg["halo_width"]),
                            opacity=float(flow_cfg["halo_opacity"]),
                            blur=True,
                        ),
                        LightLayer(kind="core", gradient_ref=g.id_suffix, width=float(flow_cfg["core_width"])),
                    )
                    connectors.append(
                        ConnectorPlacement(
                            index=geo.index,
                            path_d=arc_d(cx, cy, r, s0, s1),
                            source_index=edge.source,
                            target_index=edge.target,
                            accent_index=ctx.edge_accents[geo.index],
                            motion=m,
                            track=track,
                            semantic_dash=geo.semantic_dash,
                            static_dash="",
                            label_lines=label_lines if si == 0 else (),
                            light_layers=seg_layers,
                            length=seg_len,
                            lane=ctx.lanes[geo.index],
                            inert=inert,
                        )
                    )
                    cum += seg_len
                continue
            g = mo.flow_gradient(
                id_base=f"g{len(connectors)}",
                x1=geo.sx,
                y1=geo.sy,
                x2=geo.tx,
                y2=geo.ty,
                length=geo.length,
                hue=hue,
                begin=begin,
                flow_cfg=flow_cfg,
            )
            gradients.append(g)
            layers = (
                LightLayer(
                    kind="halo",
                    gradient_ref=g.id_suffix,
                    width=float(flow_cfg["halo_width"]),
                    opacity=float(flow_cfg["halo_opacity"]),
                    blur=True,
                ),
                LightLayer(kind="core", gradient_ref=g.id_suffix, width=float(flow_cfg["core_width"])),
            )
        connectors.append(
            ConnectorPlacement(
                index=geo.index,
                path_d=geo.d,
                source_index=edge.source,
                target_index=edge.target,
                accent_index=ctx.edge_accents[geo.index],
                motion=m,
                track="static" if inert else track,
                ant_delay="" if inert else ant_delay,
                semantic_dash=geo.semantic_dash,
                static_dash=static_dash if (inert or track == "static") else "",
                label_lines=label_lines,
                light_layers=() if inert else layers,
                length=geo.length,
                lane=ctx.lanes[geo.index],
                inert=inert,
            )
        )
    _ = track_cfg
    return tuple(connectors), tuple(particles), tuple(gradients)
