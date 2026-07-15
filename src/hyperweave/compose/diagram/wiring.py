"""Kinetic wiring: edge geometries -> connector/particle/gradient placements.

The uniform half of the solve. Topology solvers compute WHERE an edge runs
(``EdgeGeo``); this module decides HOW it moves under the closed grammar —
track resolution (P3 semantic yield), ant delays, particle riders (with the
sequence replay clock). Hues stay symbolic (@flow{i} / @signal /
@signal2) — the resolver substitutes genome hex; solvers never see it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram import motion as mo
from hyperweave.compose.diagram.paths import (
    chord_unit,
    end_tangent_of,
    line_d,
    point_on,
    s_curve_h,
    s_curve_h_len,
    s_curve_v,
    s_curve_v_len,
    sample_path,
)
from hyperweave.compose.diagram.records import (
    BeamGradient,
    ConnectorPlacement,
    ParticlePlacement,
)
from hyperweave.compose.diagram.route import marker_path, resolve_marker

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
    label_bare: bool = False
    """``label_pos`` is a bare geometric point ON the wire (no presentation
    bias) — annotate.py's ``subsume_edge_labels`` is the sole reader: a chip
    centers its box on it unconditionally, a micro-label calls
    ``_solver_label_lift`` to clear the stroke. False (default) means
    ``label_pos`` is already the final point and renders verbatim — every
    self-loop (route.py's own outboard anchor), lens bow (already seats at
    its curve's own belly), and sequence message (its own -7 baseline
    convention) stays on this path unchanged."""
    track_override: str = ""
    """'static' forces the track regardless of motion — sequence message
    strokes are kind semantics (solid call / dashed return), never a march."""
    flow_side: int = 0
    """Begin-stagger side for hub currents (bilateral: left 0 / right 1)."""
    polyline: tuple[tuple[float, float], ...] = ()
    """Coarse point list tracing the path (exact endpoints), populated by the
    solver. The annotate/collide pass (a later slice) consumes it as an
    obstacle; empty falls back to the straight (sx,sy)->(tx,ty) chord."""
    end_tangent: tuple[float, float] | None = None
    """Unit direction the connector arrives travelling — the arrowhead's aim
    and the label-lift normal. None lets marker resolution skip a degenerate
    edge (the chord unit is the fallback where a solver leaves it unset)."""
    marker_override: str = ""
    """Geometry-level terminal override: 'none' suppresses the arrowhead on
    this geo regardless of edge/spec/topology defaults — a shared-rail JOIN
    merges arrowless (the lanes fan-in rule); the rail's single exit leg
    keeps the arrow."""
    relation_default: str = ""
    """Solver-assigned relation when the edge declares none — axial's
    partition speaks the idiom vocabulary (in→assert, read→drift,
    destinations→assert-with-accent); an explicit edge.relation wins."""
    relation_override: str = ""
    """A solver-built synthetic segment (the gather trunk) dresses ITSELF —
    the override beats the host edge's declared relation."""
    accent_wire: bool = False
    """Role-bound accent stroke (§11.4b): the wire itself carries the accent
    class even under the muted default — the destination fan's dress."""
    stage_key: int = -1
    """Beam relay stage group: edges sharing a key fire their beam
    window together — DAG stamps the source rank (rank-transition staging,
    the N-stage generalization of the parity specimen's trunk-then-branches).
    -1 = ungrouped; ungrouped beams stage sequentially by declaration."""
    synthetic_trunk: bool = False
    """``knot_collapse`` built this geo (the gather/depart trunk) — the
    STRUCTURAL trunk marker, independent of relation dress (an undressed fan
    leaves relation_override empty). Beam staging keys the trunk-then-
    branches family on it."""


def knot_collapse(
    geos: list[EdgeGeo],
    slots: list[int],
    *,
    trunk_len: float,
    depart: bool = False,
    relation: str = "assert",
    marker: str = "arrow",
    mouth: tuple[float, float] | None = None,
    vertical: bool = False,
) -> tuple[float, float]:
    """The gather-fan piece: >=2 geos sharing a mouth collapse at a knot
    floated ``trunk_len`` from it, and ONE synthetic trunk carries the mouth
    wire. Join (default): members re-end at the knot with their terminals
    suppressed — the knot is their terminus — and the trunk runs knot->mouth
    (dag specimens, convergence-arrivals: assert-dressed, arrowed). Depart: members
    re-START at the knot keeping their own terminals, the trunk runs
    mouth->knot dressed like its fan (router specimens: the drift trunk is
    arrowless — the spokes carry the chevrons). The trunk borrows a member's
    edge index, so it dresses itself via the overrides. ``mouth`` overrides
    the shared point when members don't already share one (a dag hub's
    fan-spread exits collapse to the hub's center mouth, frontier-serving)."""
    from dataclasses import replace as _replace

    if depart and vertical:
        # The DOWNWARD depart (router-descent): the trunk drops the knot
        # trunk_len BELOW the mouth and the spokes fan on vertical S-curves —
        # the vertical mirror of the horizontal depart, so the route chip rides
        # the straight vertical trunk instead of falling to a micro-label.
        mx, my = mouth if mouth else (geos[slots[0]].sx, geos[slots[0]].sy)
        ky = my + trunk_len
        flush = not trunk_len
        for gi in slots:
            old_g = geos[gi]
            geos[gi] = _replace(
                old_g,
                d=s_curve_v(mx, ky, old_g.tx, old_g.ty),
                sx=mx,
                sy=ky,
                length=s_curve_v_len(mx, ky, old_g.tx, old_g.ty),
                # A flush depart has no trunk geo for wire_motion's beam
                # staging to key on (the early return below never appends
                # one) — the spokes stamp their OWN shared group instead, so
                # a beam fires the doors as one window, not N sequential
                # stages burning a clock on a stub that no longer exists.
                stage_key=0 if flush else old_g.stage_key,
            )
        if flush:
            return (mx, my)
        trunk_d = line_d(mx, my, mx, ky)
        tsx, tsy, ttx, tty = mx, my, mx, ky
        knot = (mx, ky)
    elif depart:
        mx, my = mouth if mouth else (geos[slots[0]].sx, geos[slots[0]].sy)
        kx = mx + trunk_len
        flush = not trunk_len
        for gi in slots:
            old_g = geos[gi]
            geos[gi] = _replace(
                old_g,
                d=s_curve_h(kx, my, old_g.tx, old_g.ty),
                sx=kx,
                sy=my,
                length=s_curve_h_len(kx, my, old_g.tx, old_g.ty),
                stage_key=0 if flush else old_g.stage_key,
            )
        if flush:
            # Trunk-less depart (model-gateway-tiers): the exits collapse AT
            # the mouth and the knot alone marks the gather — no stub.
            return (mx, my)
        trunk_d = line_d(mx, my, kx, my)
        tsx, tsy, ttx, tty = mx, my, kx, my
        knot = (kx, my)
    else:
        mx, my = geos[slots[0]].tx, geos[slots[0]].ty
        kx = mx - trunk_len
        flush = not trunk_len
        for gi in slots:
            old_g = geos[gi]
            geos[gi] = _replace(
                old_g,
                d=s_curve_h(old_g.sx, old_g.sy, kx, my),
                tx=kx,
                ty=my,
                length=s_curve_h_len(old_g.sx, old_g.sy, kx, my),
                marker_override="none",
            )
        if flush:
            # Chipless FLUSH join (the depart mirror): members run all the
            # way to the mouth, the gather ring alone marks the AND-join —
            # seated ON the sink's face, half occluded by the card — and no
            # bare arrowed trunk dangles before the sink.
            return (mx, my)
        trunk_d = line_d(kx, my, mx, my)
        tsx, tsy, ttx, tty = kx, my, mx, my
        knot = (kx, my)
    geos.append(
        EdgeGeo(
            index=geos[slots[0]].index,
            d=trunk_d,
            sx=tsx,
            sy=tsy,
            tx=ttx,
            ty=tty,
            length=trunk_len,
            relation_override=relation,
            marker_override=marker,
            synthetic_trunk=True,
        )
    )
    return knot


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
    chrome: str = "caption"
    """caption | bare (F1). caption (the only public rendering mode) renders
    ONE caption sentence at the base, no masthead. bare drops the caption and
    the substrate too — internal-only, set solely by the sec 12.1 recursive
    embed seam. Presentational, excluded from the envelope digest."""
    mono_triggers: list[str] = field(default_factory=list)
    glyph_registry: Mapping[str, Any] | None = None
    glyph_selections: tuple[GlyphTint, ...] = ()
    """Per-node tint SELECTION (per-slot > artifact > genome per-frame
    default); the rendered mode lands on each placement's GlyphArt."""
    warnings: tuple[str, ...] = ()
    """Normalization warnings from the input seam (cyclic-dag promotion);
    passed through to RenderedMotion.warnings, surfaced only when non-empty."""


def _per_layout(table: Mapping[str, Any], slug: str) -> Any:
    return table.get(slug, table.get("default"))


_ARC_POLY_SAMPLES = 8


def _geo_polyline_tangent(geo: EdgeGeo) -> tuple[tuple[tuple[float, float], ...], tuple[float, float]]:
    """Derive a coarse polyline (exact endpoints) and the unit arrival tangent
    for a geo the solver left unenriched. An arc samples along its sweep and
    takes the analytic tangent at the end angle; a curved path samples its
    cubic; everything else is treated as the straight chord. The polyline's
    consumer is the collision pass — a light sampling suffices."""
    if geo.arc is not None:
        cx, cy, r, a0, a1 = geo.arc
        pts = tuple(point_on(cx, cy, r, a0 + (a1 - a0) * i / _ARC_POLY_SAMPLES) for i in range(_ARC_POLY_SAMPLES + 1))
        end_rad = math.radians(a1)
        # A point (cos θ, sin θ) advancing in +θ moves along (-sin θ, cos θ);
        # arc_d sweeps in increasing angle, so that is the arrival direction.
        sign = 1.0 if a1 >= a0 else -1.0
        tangent = (-math.sin(end_rad) * sign, math.cos(end_rad) * sign)
        return pts, tangent
    return ((geo.sx, geo.sy), (geo.tx, geo.ty)), chord_unit(geo.sx, geo.sy, geo.tx, geo.ty)


def enrich_geos(geos: list[EdgeGeo]) -> list[EdgeGeo]:
    """Populate ``polyline`` + ``end_tangent`` on any geo a solver left unset.

    Solvers that build exact geometry (route.py's orthogonal/self-loop paths)
    supply their own; the S-curve/line/arc families get theirs derived here so
    the annotate/collide pass (a later slice) and marker resolution have one
    obstacle + arrival-direction contract to read, whatever built the geo."""
    out: list[EdgeGeo] = []
    for geo in geos:
        # A CURVED path carrying at most its endpoint chord is unsampled: a
        # skip channel, under-curve, or self-loop dips far outside that
        # chord, and both the annotate obstacle set and the content-extents
        # union must see the true trace (bugs d + e — the data-mesh
        # perimeter channel ran straight through the footer text because
        # extents only saw the chord).
        curved = ("C" in geo.d or "Q" in geo.d) and geo.arc is None
        unsampled = curved and len(geo.polyline) <= 2
        if geo.polyline and not unsampled:
            out.append(geo)
            continue
        if unsampled or (curved and geo.end_tangent is not None):
            # The unsampled branch must ALSO settle the tangent — returning
            # early with it unset dropped these geos to the secant at
            # arrival time (the dag skips' 6-9° chevron twists).
            out.append(replace(geo, polyline=sample_path(geo.d), end_tangent=geo.end_tangent or end_tangent_of(geo.d)))
            continue
        if geo.end_tangent is not None:
            out.append(replace(geo, polyline=((geo.sx, geo.sy), (geo.tx, geo.ty))))
            continue
        poly, tangent = _geo_polyline_tangent(geo)
        # A builder that supplied no tangent gets the FINAL SEGMENT's
        # analytic derivative, never the polyline secant (which read the
        # dag skips 6-9° off and an over-arc chevron 37.7° off); the secant
        # survives only for paths the parser cannot differentiate.
        out.append(replace(geo, polyline=poly, end_tangent=end_tangent_of(geo.d) or tangent))
    return out


def _arrival_tangent(geo: EdgeGeo) -> tuple[float, float]:
    """The unit direction the connector ARRIVES at its target. A solver's
    ``end_tangent`` is exact where supplied (every curve builder pins its
    final control to the arrival axis or computes the analytic derivative),
    so it wins outright — the retired polyline-first rule read a coarse
    8-sample secant instead, tilting every curved arrowhead by ~25% of the
    chord's off-axis component (7-14 degrees on ordinary S-curves). The
    polyline secant survives only as the fallback for geos with no tangent
    hint, then the chord."""
    if geo.end_tangent:
        return geo.end_tangent
    poly = geo.polyline
    if poly and len(poly) >= 2:
        tx, ty = poly[-1]
        for px, py in reversed(poly[:-1]):
            dx, dy = tx - px, ty - py
            d = math.hypot(dx, dy)
            if d > 1e-6:
                return (dx / d, dy / d)
    return chord_unit(geo.sx, geo.sy, geo.tx, geo.ty)


def wire_motion(
    ctx: SolverContext, geos: list[EdgeGeo]
) -> tuple[tuple[ConnectorPlacement, ...], tuple[ParticlePlacement, ...]]:
    """Uniform kinetic wiring: each edge geometry gets its concrete motion's
    layers — ants delays, particle riders, and the beam's gradient-window
    pair on the shared relay clock (the reference-specimen recipe; the
    flow tube grammar stays retired)."""
    engine = ctx.engine
    track_cfg = engine["track"]
    particle_cfg = engine["particle"]
    track_map = {str(k): str(v) for k, v in ctx.cfg.track_default_by_motion.items()}
    ant_step = float(_per_layout(engine["connector"]["ant_stagger"], ctx.slug) or 0)
    # Marker resolution is genome-blind here (the artifact default + the
    # genome device); the per-edge override rides each ResolvedEdge. Marker
    # geometry sizes from the connector keys — a drawn chevron, never a
    # <marker>. No shipped genome declares an arrowhead device, so the common
    # path leaves marker_d empty and the output is byte-identical.
    conn_cfg = engine["connector"]
    marker_size = float(conn_cfg.get("marker_size", 11))
    marker_half = float(conn_cfg.get("marker_half", 0.45))
    # Reciprocal-lane march dasharray (gateway v4 specimen: a longer dash
    # than the shared ants texture) — read once, applied per-connector below
    # wherever mo.lane_dress_applies gates the same edge into its lane hue.
    lane_dash_cfg = str(engine.get("lane_dash", ""))
    # D5 per-topology static-wire grammar: flow topologies read solid rails +
    # terminal arrows from engine wire_defaults; unlisted stay dashed and
    # markerless. Spec-level `wire`/`marker` chrome knobs override the table.
    wire_default = dict((engine.get("wire_defaults") or {}).get(ctx.slug) or {})
    wire = ctx.spec.wire or str(wire_default.get("wire", ""))
    spec_marker = ctx.spec.marker or str(wire_default.get("terminal", ""))
    device = ctx.cfg.direction_device
    # §3 relation dress: a line idiom names MEANING and binds default dress
    # (texture + terminal + motion) from the registry — explicit per-edge
    # fields override channels; the vocabulary is universal chrome, consumed
    # identically by every topology.
    from hyperweave.config.loader import load_idioms

    idioms = load_idioms()
    relation_dress: dict[str, dict[str, str]] = {
        k: dict(v.get("dress") or {}) for k, v in (idioms.get("line") or {}).items()
    }
    dress_textures: dict[str, str] = {str(k): str(v) for k, v in (idioms.get("dress_textures") or {}).items()}

    connectors: list[ConnectorPlacement] = []
    particles: list[ParticlePlacement] = []

    def _effective(geo: EdgeGeo) -> tuple[str, bool]:
        """Post-dress motion for one geo + whether the accent-wire stillness
        applies — computed ONCE so the choreography orders (beam/flow/replay)
        and the per-edge wiring below read the SAME motion. Building order
        lists from the pre-dress table would let a dress-promoted rider (a
        flow relation over a dash default) crash the replay indexer."""
        edge = ctx.edges[geo.index]
        m2 = ctx.motions[geo.index]
        explicit2 = edge.edge_motion is not None or ctx.spec.edge_motion is not None
        rel2 = geo.relation_override or edge.relation or geo.relation_default
        if rel2 and not explicit2:
            dm = str(relation_dress.get(rel2, {}).get("motion", "none"))
            m2 = "dash" if dm == "none" else dm
        still = geo.accent_wire and not (explicit2 and m2 == "dash")
        if still:
            m2 = "dash"
        return m2, still

    effective = {geo.index: _effective(geo) for geo in geos}
    particle_seen = 0
    ant_seen = 0

    # Beam relay staging: every beam edge gets a stage window on ONE
    # shared clock. Grouping is structural, never by topology name (the one
    # exception is the bilateral choreography below, which reads a
    # topology-specific SIDE, not a topology name comparison): a knot trunk
    # present (relation_override — only knot_collapse sets it) → the 2-stage
    # trunk-then-branches family (parity-beam); a bilateral fan (west/east
    # split, EdgeGeo.flow_side) → the 2-stage bilateral family — west
    # converges as one wave, a beat at the hub, east emerges as the next;
    # geos carrying a stage_key (DAG stamps source rank; a flush fan's
    # trunk-less spokes share one key too) → one window per stage in order
    # (the N-stage generalization of the same law); otherwise singleton
    # stages by declaration index (frontier-handoff).
    beam_pos = [gi for gi, g in enumerate(geos) if effective[g.index][0] == "beam" and not ctx.edges[g.index].inert]
    beam_stage: dict[int, tuple[float, float]] = {}
    if beam_pos:
        bcfg = engine.get("beam") or {}
        trunk_set = {gi for gi in beam_pos if geos[gi].synthetic_trunk}
        if trunk_set:
            wins = mo.beam_windows(2, bcfg, family="branch")
            for gi in beam_pos:
                beam_stage[gi] = wins[0] if gi in trunk_set else wins[1]
        elif ctx.slug == "fanout-bilateral":
            wins = mo.beam_windows(2, bcfg, family="bilateral")
            for gi in beam_pos:
                beam_stage[gi] = wins[geos[gi].flow_side]
        elif any(geos[gi].stage_key >= 0 for gi in beam_pos):
            order = sorted({geos[gi].stage_key for gi in beam_pos})
            slot_of = {k: i for i, k in enumerate(order)}
            wins = mo.beam_windows(len(order), bcfg, family="relay")
            for gi in beam_pos:
                beam_stage[gi] = wins[slot_of[geos[gi].stage_key]]
        else:
            wins = mo.beam_windows(len(beam_pos), bcfg, family="relay")
            for win_i, gi in enumerate(sorted(beam_pos, key=lambda p: geos[p].index)):
                beam_stage[gi] = wins[win_i]

    for gi, geo in enumerate(geos):
        edge = ctx.edges[geo.index]
        m, accent_still = effective[geo.index]
        # Explicit motion (per-edge field, spec field, or the CLI/HTTP override
        # that writes into the spec) outranks every DEFAULT dress below — the
        # D5 solid-wire table, a relation's dress motion, the accent-wire
        # stillness. Defaults describe the unrequested case only.
        explicit_motion = edge.edge_motion is not None or ctx.spec.edge_motion is not None
        track = geo.track_override or mo.resolve_track(m, track_map=track_map, semantic_dash=geo.semantic_dash)
        # Solid-wire law: the marching dashed rail becomes a static solid
        # hairline; dash survives ONLY as semantics (a return stroke, the
        # lanes bypass, a muted role) — reserved-for-meaning, never texture.
        # Flywheel is exempt from the explicit_motion override (the flywheel
        # specimen): the rim's own arcs never carry motion texture — an explicit
        # 'particle' request routes entirely to the rim-orbit ornament above,
        # so the rail itself stays the same static solid rail regardless.
        wire_exempt = not explicit_motion or ctx.slug == "flywheel"
        if wire == "solid" and track == "dash-march" and not geo.semantic_dash and wire_exempt:
            track = "static"
        inert = edge.inert
        # A drawn end-marker at the connector's target, aimed by the arrival
        # tangent (the chord unit when a solver leaves the geo's tangent
        # unset). Empty unless this edge/spec/topology/genome asks for an
        # arrow; a geo-level 'none' (shared-rail join) suppresses it last.
        # Relation dress (per edge): terminal + texture from the registry
        # when the edge declares a relation; explicit fields override.
        rel = geo.relation_override or edge.relation or geo.relation_default
        # Tree/tree-radial limbs are FURNITURE — position IS the relation, so
        # an UNDRESSED limb never marches by default (tree/mindmap
        # are static). A declared relation still dresses and marches (versioned specimens
        # dep-audits drift), and an explicit edge_motion keeps the last word.
        if ctx.slug in ("tree", "tree-radial") and not rel and not explicit_motion:
            track = "static"
        dress = relation_dress.get(rel or "", {})
        dress_terminal = str(dress.get("terminal", ""))
        dress_texture = dress_textures.get(str(dress.get("texture", "")), "")
        # Self-loops are exempt from the DEFAULTS (a loop's direction is
        # unambiguous; a chevron at the mouth is ornament) — an explicit
        # per-edge marker still wins. Tree/tree-radial are exempt the same
        # way: a hierarchy fan reads its direction from POSITION (root above
        # or centre-out), never a chevron (tree/mindmap) — a
        # relation's dress terminal (e.g. assert's arrow) would otherwise
        # leak onto every root edge on any tree using dependency relations.
        loop_exempt = edge.source == edge.target and not edge.marker
        tree_exempt = ctx.slug in ("tree", "tree-radial") and not edge.marker
        marker = (
            ""
            if loop_exempt or tree_exempt
            else resolve_marker(geo.marker_override or edge.marker, dress_terminal or spec_marker, device)
        )
        # The arrowhead aims along the line's TRUE arrival — the last real
        # segment of the drawn polyline (enrich populated it for every geo),
        # so a chevron follows a bending bezier / S-curve / elbow / arc
        # instead of a solver's approximate end_tangent. Straight lines fall
        # back to the chord (last segment == chord). This is the single place
        # marker orientation is decided, so every topology reads identically.
        marker_tangent = _arrival_tangent(geo)
        marker_d = (
            marker_path((geo.tx, geo.ty), marker_tangent, size=marker_size, half=marker_half, kind=marker)
            if marker in ("arrow", "dot")
            else ""
        )
        if rel:
            # Relation dress owns the full channel set: texture wins the
            # rail and motion names the rider (none = still — no particles
            # ride a static relation). An explicit per-edge edge_motion
            # keeps the last word, per the registry's override contract.
            # ``m`` is already the post-dress motion (the pre-pass above).
            dress_motion = str(dress.get("motion", "none"))
            # A dashed dress TEXTURE is a marching rail (drift, bypass, flow
            # all march in the specimens) — the RELATION owns the rail even
            # under an explicit edge_motion, which only names the rider
            # (particle) or requests a rail itself (dash). The RESOLVED
            # relation (authored or a solver's relation_default) outranks a
            # solver's semantic dash: every hand state-machine file marches
            # its returns whether or not the story spelled the relation out
            # (pp-state-machine's back edge: dasharray 2 7 + march), and the
            # lanes perimeter route dashes as bypass semantics while a
            # declared drift marches it anyway (obi-engine pins->utilities).
            if dress_texture and (rel or not geo.semantic_dash):
                track = "dash-march"
            elif not explicit_motion:
                if dress_motion == "none":
                    track = "static"
                else:
                    track = mo.resolve_track(m, track_map=track_map, semantic_dash=geo.semantic_dash)
            static_dash = dress_texture if (inert or track == "static") else ""
        elif inert or track == "static":
            if wire == "solid":
                static_dash = geo.semantic_dash  # solid rails; dash is semantic-only
            else:
                static_dash = geo.semantic_dash or ("" if geo.track_override else str(engine["connector"]["dash"]))
        else:
            static_dash = ""
        if accent_still:
            # invisible-riders (§11, P11): particles/beams never ride accent
            # strokes — a role-bound accent rail is a still, solid assertion.
            # An explicit dash request keeps its marching rail (the rail IS
            # the stroke, not a rider); riders always fall still. ``m`` was
            # already forced to dash by the pre-pass.
            track = "static"
            static_dash = ""
        # Edge labels are no longer wired here: the annotate chrome pass
        # (compose/diagram/annotate.py) subsumes every edge's label into a
        # ``kind="label"`` AnnotationPlacement AFTER wiring, so labels render on
        # ALL topologies (not just sequence/state-machine) and route through the
        # anti-collision ladder. The subsumption reproduces this block's former
        # math byte-for-byte where a solver supplied ``geo.label_pos``.
        ant_delay = ""
        if not inert and track == "dash-march" and m in ("dash", "particle"):
            ant_delay = mo.stagger_begin(ant_seen, ant_step)
            ant_seen += 1
        # A synthetic trunk (relation_override: the geo dresses itself) never
        # takes a rider — particles ride the AUTHORED relations; the mouth
        # wire is furniture (convergence-arrivals: four riders, one per spoke,
        # none on the trunk).
        if not inert and m == "particle" and not geo.relation_override:
            if ctx.slug == "sequence":
                # Single traversing particle (the sequence-replay specimen): ONE persistent dot
                # hops message-to-message in replay order. Each message owns
                # a non-overlapping slot on one DERIVED clock (speed law +
                # gap beats + rest beat), so exactly one dot is visible at a
                # time — a single object travelling the trace at lawful
                # velocity. The semantic call/return strokes stay at full
                # weight beneath it (solid call, dashed return).
                seq_cfg = engine["sequence_replay"]
                replay_idx = [
                    g2.index for g2 in geos if effective[g2.index][0] == "particle" and not ctx.edges[g2.index].inert
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
            elif ctx.slug == "flywheel":
                # flywheel-orbit: particle motion on flywheel routes ENTIRELY
                # to the rim-orbit ornament (radial.py's solve_flywheel ->
                # finish_layout's extra_particles) — a fixed accent-particle
                # count riding the full closed rim, never a per-arc rider
                # that would restart at each ring card. No per-edge
                # ParticlePlacement here; the arc itself stays a plain rail.
                pass
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
        beam_paint: tuple[BeamGradient, ...] = ()
        if not inert and m == "beam":
            beam_paint = mo.beam_gradient(
                len(connectors),
                geo.sx,
                geo.sy,
                geo.tx,
                geo.ty,
                stage=beam_stage.get(gi, (0.02, 0.92)),
                cfg=engine.get("beam") or {},
            )
        lane_dressed = (
            not inert and track == "dash-march" and mo.lane_dress_applies(ctx.spec.topology, ctx.lanes[geo.index])
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
                march_dash=lane_dash_cfg if lane_dressed else "",
                marker_d=marker_d,
                length=geo.length,
                lane=ctx.lanes[geo.index],
                inert=inert,
                accent_wire=geo.accent_wire,
                relation=rel,
                beam=beam_paint,
            )
        )
    _ = track_cfg
    return tuple(connectors), tuple(particles)
