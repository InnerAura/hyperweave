"""Lanes solver: a swimlane banner — category bands with a gutter bus.

Nodes carry a ``category``; each distinct category becomes a vertical BAND
(first-appearance order), its nodes stacked top-aligned in rows. Bands sit
side by side separated by a gutter. An edge routes by lane distance: same band
is a short vertical; adjacent bands cross the gutter (straight when the rows
line up, else an exit-leg → gutter-center bus → entry-leg); a LONG HAUL
(``|Δlane| ≥ 2`` or ``route: around``) drops to a perimeter channel below all
bands and runs there (channels stack, the canvas grows) so it never cuts
through a band interior. ``route: bus`` on a non-adjacent pair is illegal.

Naming note: the solver's category bands are ``bands`` here, NOT ``lanes`` —
``SolverContext.lanes`` already means reciprocal-pair lanes. Everything
visual-adjacent (band widths, gutter, row pitch, header/count voices, channel
spacing) comes from the chassis + voices; this module holds spatial policy.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from hyperweave.compose.diagram.annotate import Region
from hyperweave.compose.diagram.chrome import place_node
from hyperweave.compose.diagram.paths import diamond_d, fmt, square_d
from hyperweave.compose.diagram.records import DiagramText, LaneBand
from hyperweave.compose.diagram.sizing import ink_gap, solve_node_box, voice_for
from hyperweave.compose.diagram.solver import finish_layout, register_solvers
from hyperweave.compose.diagram.wiring import EdgeGeo, SolverContext
from hyperweave.compose.spatial_records import LineSpec, RectSpec
from hyperweave.core.diagram import DiagramCapacityError, DiagramInputError, DiagramNode
from hyperweave.core.diagram_annotations import AnnotationKind, DiagramAnnotation

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from hyperweave.compose.diagram.records import DiagramLayout, NodePlacement


_AROUND_LAND_STUB = 14.0
"""obi-engine: the perimeter bypass lands 14px past its entry-gutter rise
(608 - 594) — a rail-join stub, never a run to the card mouth."""


def _morphology_marks(spec_nodes: list[DiagramNode]) -> tuple[str, ...]:
    """Per-node mark token (obi-engine' category-by-MARK idiom, never hue):
    a node's ``morphology`` archetype resolves to a mark token (shape + tone
    — 'disc' | 'diamond' | 'square' | 'ring' | 'disc-muted') via the idiom
    registry's ``archetypes`` map. An unlisted archetype (or a node declaring
    only ``category``) falls back to the ordered ``shapes`` cycle, indexed by
    first-appearance order — one mark per band, all ink-toned, zero extra
    authoring burden. A preset opts into finer within-band distinction by
    declaring ``morphology`` per node (obi-engine's Callers band: surface
    disc vs store diamond)."""
    from hyperweave.config.loader import load_idioms

    idioms = load_idioms().get("morphology") or {}
    archetypes = {str(k): str(v) for k, v in (idioms.get("archetypes") or {}).items()}
    cycle = [str(s) for s in (idioms.get("shapes") or ["disc"])] or ["disc"]
    order: list[str] = []
    marks: list[str] = []
    for node in spec_nodes:
        key = node.morphology or node.category
        if key in archetypes:
            marks.append(archetypes[key])
            continue
        if key not in order:
            order.append(key)
        marks.append(cycle[order.index(key) % len(cycle)])
    return tuple(marks)


def _bullet_lead(ctx: SolverContext) -> float:
    """The label-row advance the leading category mark reserves: mark
    diameter + the optical ink gap (obi-engine ~14px — the small bullet
    slot, never the 24px identity-glyph slot)."""
    return 2 * ctx.ch.morph_mark_r + ink_gap(ctx.ch.node)


def _mark_geometry(shape: str, cx: float, cy: float, r: float) -> str:
    """Precomputed drawn-geometry ``d`` for a non-circle mark shape ('' for
    disc/ring, which stamp as a plain ``<circle>``, the ring open-stroked)."""
    if shape == "diamond":
        return diamond_d(cx, cy, r)
    if shape == "square":
        return square_d(cx, cy, r)
    return ""


def _stamp_morphology_mark(
    p: NodePlacement, shape: str, r: float, lead: float, label_size: float, accent: bool
) -> NodePlacement:
    """Place a node's category mark LEADING the label row (obi-engine: the
    mark sits left of the title, marks column-aligning down each lane; the
    label indents past it via place_card's ``bullet_lead``). The mark centers
    on the label's optical middle — baseline minus ~0.35 of the voice size
    (the x-height center the specimen marks ride)."""
    cx = p.label.x - lead + r
    cy = p.label.y - 0.35 * label_size
    return replace(
        p, dot=(cx, cy), dot_r=r, dot_shape=shape, dot_path=_mark_geometry(shape, cx, cy, r), card_accent=accent
    )


def _bands_of(spec_nodes: list[DiagramNode], declared: tuple[str, ...] = ()) -> tuple[list[str], dict[int, int]]:
    """Category → band index. DECLARED order wins when the spec names its
    lanes (a declared-but-unpopulated entry renders as an EMPTY lane — the
    empty-lane knob); otherwise first-appearance order. Returns the ordered
    category list and a node-index → band-index map."""
    if declared:
        order = list(declared)
    else:
        order = []
        for node in spec_nodes:
            if node.category not in order:
                order.append(node.category)
    band_of = {i: order.index(node.category) for i, node in enumerate(spec_nodes)}
    return order, band_of


def solve_lanes(ctx: SolverContext) -> DiagramLayout:
    ch = ctx.ch
    spec = ctx.spec
    caps = ctx.engine.get("caps") or {}
    categories, band_of = _bands_of(list(spec.nodes), spec.lanes)
    if len(categories) > int(caps.get("lanes_max_lanes", 5)):
        raise DiagramCapacityError(
            f"lanes caps at {caps.get('lanes_max_lanes', 5)} category bands (got {len(categories)})"
        )
    # Rows within each band, spec order (top-aligned). A declared-but-empty
    # lane keeps an entry with no rows. Per-band row cap.
    rows: dict[int, list[int]] = {b: [] for b in range(len(categories))}
    for i in range(len(spec.nodes)):
        rows[band_of[i]].append(i)
    for b, members in rows.items():
        if len(members) > int(caps.get("lanes_max_rows", 6)):
            raise DiagramCapacityError(
                f"lanes caps at {caps.get('lanes_max_rows', 6)} rows per band ({categories[b]} has {len(members)})"
            )
    # Category-grouped accents come from solver.py:assign_accents (same
    # category → same slot); ctx.node_accents already carries them.
    cat_accents = {i: ctx.node_accents[i] for i in range(len(spec.nodes))}

    # Content-solved band width: the max card width in the band, clamped to
    # [lane_w_min, lane_w_max]. Shared row height across ALL bands (one grid).
    band_w: dict[int, float] = {}
    row_h = ch.node.h
    box_of: dict[int, tuple[float, float]] = {}
    for i, node in enumerate(spec.nodes):
        # ``hero=False`` is pinned, not role-derived (preserved verbatim —
        # see the seam-conversion report): lanes has no focal slot, so an
        # explicit caller ``role: hero`` on a lane node still measures
        # against the plain node chassis here while place_card's OWN
        # role_of() independently renders it with hero text/voice — a
        # latent chassis/text mismatch this conversion does not fix.
        bw, bh, _ = solve_node_box(ctx, node, i, force_card=True, bullet_lead=_bullet_lead(ctx))
        box_of[i] = (bw, bh)
        row_h = max(row_h, bh)
    for b, members in rows.items():
        # An empty (declared, unpopulated) lane takes the width floor.
        want = max((box_of[m][0] for m in members), default=ch.lane_w_min)
        band_w[b] = max(ch.lane_w_min, min(ch.lane_w_max, want))

    # Band geometry: header strip on top, rows beneath at row_pitch (grown to
    # hold the shared row height). Bands laid left→right separated by gutter.
    pitch = max(ch.row_pitch, row_h + (ch.row_pitch - ch.node.h))
    max_rows = max(max((len(m) for m in rows.values()), default=1), 1)
    band_top = ch.header_h
    header_h = ch.lane_header_h
    rows_top = band_top + header_h
    band_h = header_h + max_rows * pitch
    band_x: dict[int, float] = {}
    x = ch.margin_x
    for b in range(len(categories)):
        band_x[b] = x
        x += band_w[b] + ch.gutter_w
    content_right = x - ch.gutter_w
    width = int(max(ch.width, content_right + ch.margin_x))

    # Place cards: top-aligned rows, each band a vertical aligned column —
    # members share one content-left edge by construction (the bulleted
    # anatomy left-aligns at the chassis pad).
    placed: dict[int, NodePlacement] = {}
    for b, members in rows.items():
        for r, m in enumerate(members):
            bw = band_w[b]
            cx = band_x[b] + bw / 2
            cy = rows_top + r * pitch + row_h / 2
            placed[m] = _place_card(ctx, m, spec.nodes[m], cx, cy, bw, row_h, cat_accents[m])

    # Category-by-MARK marks (obi-engine' morphology idiom, never hue): a
    # small mark per card whose shape+tone names its archetype. The mark KIND
    # (idiom-registry archetype map) and ink/muted TONE are the category
    # channel; the accent slot never colours it. The mark LEADS the label row
    # (obi-engine) — place_card reserved the ``bullet_lead`` for it.
    morph_shapes = _morphology_marks(list(spec.nodes))
    label_size = ctx.cfg.label_voice.size
    # The singular convergence hubs (node.hub) carry the ONE accent: signal
    # card border + signal mark ring at normal card size (obi-engine
    # sl-cardH/sl-mkH on obix + model-router).
    placed = {
        i: _stamp_morphology_mark(p, morph_shapes[i], ch.morph_mark_r, _bullet_lead(ctx), label_size, spec.nodes[i].hub)
        for i, p in placed.items()
    }

    # LaneBand furniture: full-height band rect + uppercased header + count.
    bands = _lane_bands(ctx, categories, rows, band_x, band_w, band_top, band_h, cat_accents)

    # Route edges. Long hauls drop to a perimeter channel below all bands.
    band_bottom = band_top + band_h
    channel_gap = ch.channel_gap
    channel_stack = ch.channel_stack
    geos, deepest_channel = _route_edges(
        ctx, placed, band_of, band_x, band_w, band_bottom, channel_gap, channel_stack, caps
    )
    height = int(band_bottom + ch.footer_h)
    if deepest_channel:
        height = max(height, int(deepest_channel + channel_gap + ch.footer_h))

    regions = {
        f"lane:{categories[b]}": Region(x=bands[b].box.x, y=bands[b].box.y, w=bands[b].box.w, h=bands[b].box.h)
        for b in range(len(categories))
    }
    auto_legend = _auto_category_legend(ctx, list(spec.nodes), morph_shapes)
    paint = [placed[i] for i in range(len(spec.nodes))]
    return finish_layout(
        ctx,
        width=width,
        height=height,
        nodes_paint=paint,
        geos=geos,
        lane_bands=tuple(bands),
        extra_regions=regions,
        auto_annotations=auto_legend,
    )


def _auto_category_legend(
    ctx: SolverContext, spec_nodes: list[DiagramNode], morph_shapes: tuple[str, ...]
) -> tuple[DiagramAnnotation, ...]:
    """A category legend, one entry per DISTINCT morphology archetype (obi-
    lanes: surface/engine/store/external) — never hue, so a reader maps a
    mark's SHAPE to its archetype. Falls back to one entry per band when no
    node declares ``morphology`` (the zero-authoring default: every node's
    archetype IS its band). Its home is the ``legend_home`` knob:
    'masthead' coalesces top-right in the header band, inline with the title
    row (the obi-engine placement); 'footer' takes the footer band, where the
    footer-growth pass reserves it. Either way it never floats over the
    graph mid-canvas. A caller-declared legend suppresses the auto one (the
    caller owns the chrome then)."""
    if any(a.kind is AnnotationKind.LEGEND for a in ctx.spec.annotations):
        return ()
    home = "header" if str(ctx.ch.legend_home or "masthead") == "masthead" else "footer"
    placement = "right" if home == "header" else ""
    order: list[str] = []
    shape_of: dict[str, str] = {}
    for node, shape in zip(spec_nodes, morph_shapes, strict=True):
        key = node.morphology or node.category
        if key not in order:
            order.append(key)
            shape_of[key] = shape
    return tuple(
        DiagramAnnotation(text=key, kind=AnnotationKind.LEGEND, region=home, shape=shape_of[key], placement=placement)
        for key in order
    )


def _place_card(
    ctx: SolverContext,
    i: int,
    node: DiagramNode,
    cx: float,
    cy: float,
    bw: float,
    row_h: float,
    accent: int,
) -> NodePlacement:
    # ``accent`` is always ``ctx.node_accents[i]`` (lanes' category-grouped
    # accent map is a verbatim copy — see ``cat_accents`` at the call site);
    # ``place_node`` derives it the same way, so the param is unused here.
    del accent
    # ``hero=False`` pinned — see the matching note on the box-solving loop
    # above; place_card's own role_of() still renders hero text/voice for an
    # explicit ``role: hero`` lane node, inside this plain-chassis box.
    # Bulleted-card anatomy (obi-engine): content LEFT-aligns so the
    # category marks column-align down each lane; the label indents past the
    # mark's reserved lead, the desc stays flush at content-left.
    return place_node(
        ctx,
        node,
        i,
        cx,
        cy,
        w=bw,
        h=row_h,
        force_card=True,
        bullet_lead=_bullet_lead(ctx),
        left_align=True,
    )


def _lane_bands(
    ctx: SolverContext,
    categories: list[str],
    rows: dict[int, list[int]],
    band_x: dict[int, float],
    band_w: dict[int, float],
    band_top: float,
    band_h: float,
    cat_accents: dict[int, int],
) -> list[LaneBand]:
    """One LaneBand per category: the full-height band rect, an uppercased
    header in the `lane` voice, and a member-count badge in the `cnt` voice."""
    cfg = ctx.cfg
    ch = ctx.ch
    lane_voice = voice_for(cfg, "lane")
    cnt_voice = voice_for(cfg, "cnt")
    pad = ch.lane_pad
    ground = str(ch.lane_ground or "panel")
    rows_top = band_top + ch.lane_header_h
    if ground == "typographic":
        # Typographic ground (the obi-engine specimen): the lane dissolves into a typographic region — an
        # uppercase header, a right-aligned count on the SAME baseline, and
        # one hairline rule spanning exactly the card column. Grouping is
        # carried by alignment and proximity, never a box. The baseline
        # derives from the rule position: rule sits lane_rule_to_row above
        # the first card row; the baseline lane_rule_dy above the rule.
        rule_y = rows_top - ch.lane_rule_to_row
        header_y = rule_y - ch.lane_rule_dy
        count_y = header_y
        header_x_pad, count_x_pad = 0.0, 0.0
    else:
        # Panel ground: baselines center in the header STRIP (chassis-driven;
        # a taller strip in another genome re-centers with zero code).
        strip_mid = band_top + ch.lane_header_h / 2
        header_y = strip_mid + lane_voice.size * float(cfg.text_ascent_ratio) / 2
        count_y = strip_mid + cnt_voice.size * float(cfg.text_ascent_ratio) / 2
        header_x_pad, count_x_pad = pad, pad
    bands: list[LaneBand] = []
    for b, cat in enumerate(categories):
        members = rows[b]
        accent = cat_accents[members[0]] if members else -1
        box = RectSpec(x=band_x[b], y=band_top, w=band_w[b], h=band_h, rx=ch.node.rx)
        header = DiagramText(
            x=band_x[b] + header_x_pad,
            y=header_y,
            text=cat.upper(),
            cls="lane",
        )
        count = DiagramText(
            x=band_x[b] + band_w[b] - count_x_pad,
            y=count_y,
            text=str(len(members)),
            cls="cnt",
            anchor="end",
        )
        rule = (
            LineSpec(x1=band_x[b], y1=rule_y, x2=band_x[b] + band_w[b], y2=rule_y) if ground == "typographic" else None
        )
        bands.append(LaneBand(box=box, header=header, count=count, accent_index=accent, ground=ground, rule=rule))
    return bands


def _route_edges(
    ctx: SolverContext,
    placed: dict[int, NodePlacement],
    band_of: dict[int, int],
    band_x: dict[int, float],
    band_w: dict[int, float],
    band_bottom: float,
    channel_gap: float,
    channel_stack: float,
    caps: Mapping[str, Any],
) -> tuple[list[EdgeGeo], float]:
    """Route every edge by lane distance. Returns (geos, deepest_channel)."""
    geos: list[EdgeGeo] = []
    long_haul_seen = 0
    deepest_channel = 0.0
    gutter_seen: dict[float, int] = {}
    channel_base = band_bottom + channel_gap
    for j, e in enumerate(ctx.edges):
        sb, tb = band_of[e.source], band_of[e.target]
        delta = abs(tb - sb)
        route = e.route
        if route == "bus" and delta >= 2:
            raise DiagramInputError(
                f"edge {e.source}->{e.target} sets route='bus' across {delta} bands; "
                f"bus routing is adjacent-only (use route='around' for the perimeter channel)"
            )
        long_haul = delta >= 2 or route == "around"
        if long_haul:
            if long_haul_seen >= int(caps.get("lanes_max_long_haul", 3)):
                raise DiagramCapacityError(
                    f"lanes caps at {caps.get('lanes_max_long_haul', 3)} long-haul edges (perimeter channel)"
                )
            channel = channel_base + long_haul_seen * channel_stack
            deepest_channel = max(deepest_channel, channel)
            # Vertical legs run in the GUTTERS, never at a card's center x — a
            # centered drop cuts straight through the source's band-mates below
            # it (the min_clearance law binds wire-to-card everywhere). The
            # exit gutter sits on the travel side of the source band, the
            # entry gutter on the side of the target band facing the source;
            # stacked channels stagger their gutter x so coincident verticals
            # never overlap.
            n_bands = len(band_x)
            direction = 1 if tb > sb else -1 if tb < sb else (1 if sb + 1 < n_bands else -1)
            stagger = long_haul_seen * 6.0
            exit_gx = _gutter_center(sb, sb + direction, band_x, band_w) + stagger
            enter_gx = _gutter_center(tb, tb - direction, band_x, band_w) + stagger if tb != sb else exit_gx
            long_haul_seen += 1
            bypass_dash = str(ctx.engine["connector"]["dash"])
            geos.append(
                _perimeter_geo(
                    j, placed[e.source], placed[e.target], channel, exit_gx, enter_gx, direction, bypass_dash
                )
            )
        elif sb == tb:
            geos.append(_same_band_geo(j, placed[e.source], placed[e.target]))
        else:
            gutter_x = _gutter_center(sb, tb, band_x, band_w)
            if str(ctx.ch.bus_bundling or "shared-rail") == "per-edge":
                # Per-edge bundling: each edge takes its own offset rail so
                # individual routes stay traceable; shared-rail (default)
                # keeps ONE rail x per gutter — coincident verticals merge
                # into a single drawn rail (the obi-engine bus).
                key = round(gutter_x, 1)
                ordinal = gutter_seen.get(key, 0)
                gutter_seen[key] = ordinal + 1
                gutter_x += ordinal * 6.0
            geos.append(_gutter_geo(j, placed[e.source], placed[e.target], gutter_x))
    # Fan-in rule: edges that ENTER the same target from the same rail
    # merge arrowless — one arrow marks the entry, never a stack of
    # coincident chevrons (the obi-engine specimen: "fan-in merges arrowless into the bus").
    # A perimeter bypass lands on its own rail-join stub PAST the entry
    # gutter — a distinct landing, so it keeps its terminal (obi census
    # pins 12 arrows including it). Same-row crowding between a bypass
    # stub and a direct mouth is an AUTHORING concern (per-edge marker
    # overrides), never an engine suppression.
    seen_entries: set[tuple[float, float]] = set()
    for k, geo in enumerate(geos):
        entry = (round(geo.tx, 1), round(geo.ty, 1))
        if entry in seen_entries:
            geos[k] = replace(geo, marker_override="none")
        else:
            seen_entries.add(entry)
    return geos, deepest_channel


def _gutter_center(sb: int, tb: int, band_x: dict[int, float], band_w: dict[int, float]) -> float:
    """The x of the gutter between two adjacent bands (right edge of the left
    band + half the gutter to the left edge of the right band)."""
    left, right = (sb, tb) if sb < tb else (tb, sb)
    left_edge = band_x[left] + band_w[left]
    right_edge = band_x[right]
    return (left_edge + right_edge) / 2


def _same_band_geo(j: int, a: NodePlacement, b: NodePlacement) -> EdgeGeo:
    """Same band: a short vertical between the two rows (bottom of the upper
    box to the top of the lower box, shared center x)."""
    ab, bb = a.box, b.box
    cx = ab.x + ab.w / 2
    if bb.y >= ab.y:
        sy, ty = ab.y + ab.h, bb.y
    else:
        sy, ty = ab.y, bb.y + bb.h
    d = f"M {fmt(cx)},{fmt(sy)} L {fmt(cx)},{fmt(ty)}"
    return EdgeGeo(
        index=j,
        d=d,
        sx=cx,
        sy=sy,
        tx=cx,
        ty=ty,
        length=abs(ty - sy),
        polyline=((cx, sy), (cx, ty)),
        end_tangent=(0.0, 1.0 if ty >= sy else -1.0),
    )


def _gutter_geo(j: int, a: NodePlacement, b: NodePlacement, gutter_x: float) -> EdgeGeo:
    """Adjacent bands: exit the source's facing edge, run to the gutter center,
    drop/rise to the target row, enter the target's facing edge. Straight
    across when the rows already line up. Exact manhattan length with a small
    per-corner arc correction."""
    ab, bb = a.box, b.box
    forward = bb.x > ab.x
    sx = ab.x + ab.w if forward else ab.x
    tx = bb.x if forward else bb.x + bb.w
    scy = ab.y + ab.h / 2
    tcy = bb.y + bb.h / 2
    if abs(scy - tcy) < 0.5:  # rows line up — straight across the gutter
        d = f"M {fmt(sx)},{fmt(scy)} L {fmt(tx)},{fmt(tcy)}"
        return EdgeGeo(
            index=j,
            d=d,
            sx=sx,
            sy=scy,
            tx=tx,
            ty=tcy,
            length=abs(tx - sx),
            polyline=((sx, scy), (tx, tcy)),
            end_tangent=(1.0 if tx >= sx else -1.0, 0.0),
        )
    d = f"M {fmt(sx)},{fmt(scy)} L {fmt(gutter_x)},{fmt(scy)} L {fmt(gutter_x)},{fmt(tcy)} L {fmt(tx)},{fmt(tcy)}"
    length = abs(gutter_x - sx) + abs(tcy - scy) + abs(tx - gutter_x)
    poly = ((sx, scy), (gutter_x, scy), (gutter_x, tcy), (tx, tcy))
    return EdgeGeo(
        index=j,
        d=d,
        sx=sx,
        sy=scy,
        tx=tx,
        ty=tcy,
        length=length,
        polyline=poly,
        end_tangent=(1.0 if tx >= gutter_x else -1.0, 0.0),
    )


def _perimeter_geo(
    j: int,
    a: NodePlacement,
    b: NodePlacement,
    channel: float,
    exit_gx: float,
    enter_gx: float,
    direction: int,
    dash: str,
) -> EdgeGeo:
    """Long haul: exit the source's travel-side edge at its own row, drop to
    the perimeter channel in the gutter, run below every band, rise in the
    gutter facing the target, and enter its side edge. Vertical legs live in
    gutters ONLY — a center-x drop would cut through the source's band-mates
    below it (never cuts a band interior, and never shaves a card). The
    bypass carries THE reserved dash (D5: dash is semantic within lanes) and
    its label rides the channel run itself (D7), not a fallback midpoint."""
    ab, bb = a.box, b.box
    scy = ab.y + ab.h / 2
    tcy = bb.y + bb.h / 2
    sx = ab.x + ab.w if direction > 0 else ab.x
    # The bypass HANDS OFF at the rail join, not the card: it rounds the
    # entry-gutter corner and stops on a short stub, its arrow marking the
    # join — the rail's own exit leg covers the last run to the mouth
    # (obi-engine: the perimeter wire lands 608, the card mouth is 669).
    # A distinct landing also keeps it clear of the D6 coincident-chevron
    # merge at the mouth.
    tx = enter_gx + direction * _AROUND_LAND_STUB
    d = (
        f"M {fmt(sx)},{fmt(scy)} L {fmt(exit_gx)},{fmt(scy)} L {fmt(exit_gx)},{fmt(channel)} "
        f"L {fmt(enter_gx)},{fmt(channel)} L {fmt(enter_gx)},{fmt(tcy)} L {fmt(tx)},{fmt(tcy)}"
    )
    length = abs(exit_gx - sx) + (channel - scy) + abs(enter_gx - exit_gx) + (channel - tcy) + abs(tx - enter_gx)
    poly = ((sx, scy), (exit_gx, scy), (exit_gx, channel), (enter_gx, channel), (enter_gx, tcy), (tx, tcy))
    return EdgeGeo(
        index=j,
        d=d,
        sx=sx,
        sy=scy,
        tx=tx,
        ty=tcy,
        length=length,
        semantic_dash=dash,
        label_pos=((exit_gx + enter_gx) / 2, channel - 7.0),
        label_max_w=max(24.0, abs(enter_gx - exit_gx) - 16.0),
        polyline=poly,
        end_tangent=(1.0 if direction > 0 else -1.0, 0.0),
    )


register_solvers({"lanes": solve_lanes})
