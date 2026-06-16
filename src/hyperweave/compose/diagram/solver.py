"""Diagram layout orchestration: caps, accents, motion wiring, dispatch.

Per-topology placement lives in linear/fan/radial/sequence/graph; this
module owns everything uniform across them — capacity/legality policy
(YAML), flow-palette index assignment, and ``wire_motion``, which turns a
solver's edge geometries into connector/particle/gradient placements under
the closed motion grammar. Solvers never see hex (accent INDICES only) and
templates never see arithmetic.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from hyperweave.compose.diagram import motion as mo
from hyperweave.compose.diagram.chrome import build_footer, build_header
from hyperweave.compose.diagram.records import (
    DiagramHeader,
    DiagramLayout,
    DiagramText,
    NodePlacement,
    RenderedMotion,
)
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext, wire_motion
from hyperweave.core.diagram import (
    DiagramCapacityError,
    DiagramInputError,
    DiagramSpec,
    NodeRole,
    Orientation,
    ResolvedEdge,
    Topology,
    layout_slug,
    resolved_edges,
    tree_depth,
)
from hyperweave.core.matrix import GlyphTint
from hyperweave.core.paradigm import DiagramTopologyChassis, ParadigmDiagramConfig


def enforce_caps(spec: DiagramSpec, slug: str, caps: Mapping[str, Any]) -> bool:
    """Hard caps raise; per-layout min/max raise; soft cap returns the
    shrink flag (the named gap/pitch tightens by shrink_factor)."""
    n = len(spec.nodes)
    if n > int(caps.get("hard_nodes", 20)):
        raise DiagramCapacityError(f"{n} nodes exceeds the hard cap {caps.get('hard_nodes', 20)}; split the diagram")
    band = (caps.get("layouts") or {}).get(slug) or {}
    lo, hi = int(band.get("min", 2)), int(band.get("max", 20))
    if n < lo:
        raise DiagramInputError(f"{slug} needs at least {lo} nodes (got {n})")
    if n > hi:
        raise DiagramCapacityError(f"{slug} caps at {hi} nodes (got {n}); split the diagram")
    if spec.topology is Topology.SEQUENCE and len(spec.edges) > int(caps.get("sequence_max_messages", 8)):
        raise DiagramCapacityError(
            f"sequence caps at {caps.get('sequence_max_messages', 8)} messages (got {len(spec.edges)})"
        )
    return n > int(caps.get("soft_nodes", 12))


def check_orientation(spec: DiagramSpec, engine: Mapping[str, Any]) -> None:
    """topology x orientation legality is config data; the depth rules close
    both ways (P2): radial trees need depth >= 2, horizontal trees depth 1."""
    legality: Mapping[str, list[str]] = engine.get("orientation_legality") or {}
    legal = legality.get(spec.topology.value, ["horizontal"])
    if spec.orientation.value not in legal:
        raise DiagramInputError(
            f"orientation {spec.orientation.value!r} is not legal for {spec.topology.value} (legal: {legal})"
        )
    if spec.topology is Topology.TREE:
        depth = tree_depth(spec)
        caps = engine.get("caps") or {}
        if spec.orientation is Orientation.RADIAL:
            if depth < 2:
                raise DiagramInputError(
                    "tree:radial requires depth >= 2 — a depth-1 radial tree IS fanout-radial "
                    "(use topology 'fanout' with orientation 'radial')"
                )
            if depth > int(caps.get("tree_radial_max_depth", 3)):
                raise DiagramCapacityError(f"tree:radial caps at depth {caps.get('tree_radial_max_depth', 3)}")
        elif depth > 1:
            raise DiagramInputError(
                "tree:horizontal renders depth 1 only — multi-level trees use orientation 'radial' (tree: radial)"
            )


def assign_accents(spec: DiagramSpec, palette_len: int) -> tuple[int, ...]:
    """Flow-palette slots: non-hero, non-muted nodes cycle the palette by
    non-hero order; explicit ``node.accent`` overrides (validated against
    the genome palette length); hero and muted carry none."""
    out: list[int] = []
    k = 0
    for node in spec.nodes:
        if node.accent is not None:
            if node.accent >= palette_len:
                raise DiagramInputError(
                    f"node accent {node.accent} is outside the genome diagram_flow palette (len {palette_len})"
                )
            out.append(node.accent)
            k += 1
            continue
        if node.role in (NodeRole.HERO, NodeRole.MUTED):
            out.append(-1)
            continue
        out.append(k % palette_len if palette_len else -1)
        k += 1
    return tuple(out)


def connector_accents(
    spec: DiagramSpec,
    edges: tuple[ResolvedEdge, ...],
    node_accents: tuple[int, ...],
    lanes: tuple[int, ...] = (),
    lane_hues: Mapping[str, Any] | None = None,
) -> tuple[int, ...]:
    """Edge hue = its characteristic endpoint: the target unless the target
    is the hero (then the source) — except flywheel and stack, whose
    arcs/risers leave their card (source). Both endpoints accentless
    (comparison) falls to the chassis accent (-1). Reciprocal pairs (G8)
    override the endpoint rule with PER-DIRECTION hues — pair data from
    the engine's lane_hues, identical across every link of a chain, so a
    conversation never renders as a doubled line."""
    source_led = spec.topology in (Topology.FLYWHEEL, Topology.STACK)
    fwd = int((lane_hues or {}).get("forward", 3))
    rev = int((lane_hues or {}).get("reverse", 1))
    out: list[int] = []
    for j, e in enumerate(edges):
        if lanes and lanes[j] != 0:
            out.append(fwd if lanes[j] < 0 else rev)
            continue
        if source_led:
            out.append(node_accents[e.source])
            continue
        t = node_accents[e.target]
        out.append(t if t >= 0 else node_accents[e.source])
    return tuple(out)


def finish_layout(
    ctx: SolverContext,
    *,
    width: int,
    height: int,
    nodes_paint: list[NodePlacement],
    geos: list[EdgeGeo],
    operators: tuple[DiagramText, ...] = (),
    lifelines: tuple[Any, ...] = (),
    activations: tuple[Any, ...] = (),
    legend: DiagramText | None = None,
    initial_dot: tuple[float, float] | None = None,
    initial_stub: Any = None,
    header_width: float = 0.0,
) -> DiagramLayout:
    """Shared assembly: chrome + motion wiring + the rendered record."""
    connectors, particles, gradients = wire_motion(ctx, geos)
    track_map = {str(k): str(v) for k, v in ctx.cfg.track_default_by_motion.items()}
    semantic_by_index = {g.index: g.semantic_dash for g in geos}
    override_by_index = {g.index: g.track_override for g in geos}
    rendered_tracks = tuple(
        override_by_index.get(i) or mo.resolve_track(m, track_map=track_map, semantic_dash=semantic_by_index.get(i, ""))
        for i, m in enumerate(ctx.motions)
    )
    tint_by_index = {n.index: (n.glyph.tint if n.glyph else "") for n in nodes_paint}
    rendered = RenderedMotion(
        edge_motion=ctx.motions,
        track=rendered_tracks,
        glyph_tint=tuple(tint_by_index.get(i, "") for i in range(len(ctx.spec.nodes))),
        performance=mo.performance_tier(list(ctx.motions), [e.inert for e in ctx.edges]),
        fallback_applied=ctx.fallback_applied,
    )
    ch = ctx.ch
    return DiagramLayout(
        width=width,
        height=height,
        display_w=ch.display_w or width,
        display_h=ch.display_h or (round((ch.display_w / width) * height) if ch.display_w else height),
        layout_slug=ctx.slug,
        aspect=ch.aspect,
        header=build_header(ctx.spec, ch, ctx.cfg, header_width or width) if ctx.chrome != "bare" else DiagramHeader(),
        nodes=tuple(nodes_paint),
        connectors=connectors,
        particles=particles,
        gradients=gradients,
        operators=operators,
        lifelines=tuple(lifelines),
        activations=tuple(activations),
        legend=legend,
        initial_dot=initial_dot,
        initial_stub=initial_stub,
        footer=build_footer(ctx.spec, ctx.slug, ch, ctx.cfg, height) if ctx.chrome != "bare" else None,
        palette_slots=(max([a for a in ctx.node_accents + ctx.edge_accents if a >= 0], default=-1) + 1),
        entrance=ctx.cfg.entrance,
        rendered=rendered,
    )


SolverFn = Callable[[SolverContext], DiagramLayout]


def compute_diagram_layout(
    spec: DiagramSpec,
    *,
    paradigm: ParadigmDiagramConfig,
    engine: Mapping[str, Any],
    palette_len: int,
    composite_only: bool = False,
    chrome: str = "card",
    glyph_registry: Mapping[str, Any] | None = None,
    glyph_selections: tuple[GlyphTint, ...] = (),
) -> DiagramLayout:
    """Deterministic solve: same spec, same chassis, same bytes.

    ``spec`` must be post-normalization (AUTO roles resolved,
    ``direction: both`` expanded — the input seam's job)."""
    if any(n.role is NodeRole.AUTO for n in spec.nodes):
        raise DiagramInputError("spec reached the solver with AUTO roles; normalize via the input seam first")
    slug = layout_slug(spec)
    caps = engine.get("caps") or {}
    check_orientation(spec, engine)
    shrink = enforce_caps(spec, slug, caps)
    edges = resolved_edges(spec)
    node_accents = assign_accents(spec, palette_len)
    lanes_t = tuple(mo.detect_lanes(edges, float(engine.get("lane_offset", 4))))
    motions, fallback = mo.resolve_edge_motions(
        edges,
        spec_motion=spec.edge_motion,
        default=paradigm.edge_motion_default,
        allowlist=paradigm.edge_motion_allowlist,
        composite_only=composite_only,
        ladder={str(k): str(v) for k, v in (engine.get("fallback_ladder") or {}).items()},
    )
    ch = paradigm.topologies.get(slug) or DiagramTopologyChassis()
    if chrome == "bare":
        # Bare chrome (F1): collapse the masthead/footer bands to pads and
        # let the canvas height + display ratio re-derive — the artifact
        # crops to content over transparent paper.
        bare = engine.get("chrome_bare") or {}
        top = min(ch.header_h, float(bare.get("top_pad", 24)))
        bottom = min(ch.footer_h, float(bare.get("bottom_pad", 20)))
        new_h = int(ch.height - (ch.header_h - top) - (ch.footer_h - bottom)) if ch.height else 0
        ch = ch.model_copy(update={"header_h": top, "footer_h": bottom, "height": max(new_h, 0), "display_h": 0})
    ctx = SolverContext(
        spec=spec,
        slug=slug,
        ch=ch,
        cfg=paradigm,
        engine=engine,
        edges=edges,
        node_accents=node_accents,
        edge_accents=connector_accents(spec, edges, node_accents, lanes_t, engine.get("lane_hues") or {}),
        motions=tuple(motions),
        lanes=lanes_t,
        lane_offsets=mo.lane_offsets(edges, lanes_t, tuple(motions), engine),
        shrink=shrink,
        palette_len=palette_len,
        composite_only=composite_only,
        fallback_applied=fallback,
        chrome=chrome,
        mono_triggers=[str(t) for t in engine.get("mono_triggers") or []],
        glyph_registry=glyph_registry,
        glyph_selections=glyph_selections or tuple(GlyphTint.INK for _ in spec.nodes),
    )
    solver = _SOLVERS.get(slug)
    if solver is None:
        raise DiagramInputError(f"no layout solver registered for {slug!r}")
    return solver(ctx)


def register_solvers(solvers: Mapping[str, SolverFn]) -> None:
    """Topology modules register their slugs at import (the matrix
    kind->builder dispatch precedent — never a template branch)."""
    _SOLVERS.update(solvers)


def registered_slugs() -> list[str]:
    """Every layout slug with a registered solver — the requestable set.

    These are the concrete ``layout_slug`` / payload ``subvariant`` values
    (``fanout-radial``, ``tree-radial``, ``dag`` …), the flattened result of
    topology x orientation. Discovery and the URL grammar emit this list so a
    caller never has to combine the axes by hand. Importing the package
    registers all of them.
    """
    return sorted(_SOLVERS)


_SOLVERS: dict[str, SolverFn] = {}
