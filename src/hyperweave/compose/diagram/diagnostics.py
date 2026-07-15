"""§6 compiler diagnostics — the compiler that teaches (diagrams-v2).

Every rule is ADVISORY: {rule, measured, band, suggestion} on CLI stderr,
HTTP JSON, and MCP — never a refusal (refusals live at the input seam and
name their rule, e.g. cross-boundary-edge and nesting-depth's hard cap).
Measurements are pure functions of (spec, layout, genome, engine); bands
live in the ``diagnostics:`` engine block. A clean artifact reports
NOTHING — silence is the passing grade.

Rules: mass-ratio, canonical-slot, sector-balance, margin-band, contrast,
palette, nucleus-underweight, accent-unbound, unbundled-fan,
unresolved-glyph, relation-ambiguous, crossing-count, visual-channel-collision,
nesting-depth (advisory at the cap; >2 refuses at the seam),
nested-density, annotation-failure. cross-boundary-edge is seam-enforced
(a hard error carrying the rule name) — it never reaches this pass.
"""

from __future__ import annotations

import itertools
import math
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.paths import count_polyline_crossings, sample_path
from hyperweave.core.color import contrast_ratio
from hyperweave.core.diagnostics import Diagnostic

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hyperweave.compose.diagram.records import DiagramLayout
    from hyperweave.core.diagram import DiagramSpec


def _cfg(engine: Mapping[str, Any]) -> Mapping[str, Any]:
    return engine.get("diagnostics") or {}


def _band(table: Mapping[str, Any], key: str, default_key: str = "default") -> Any:
    return table.get(key, table.get(default_key))


def _is_axial(spec: DiagramSpec, layout: DiagramLayout) -> bool:
    """Mirror of hub._hub_policy: explicit wins; compass when any member
    speaks compass vocabulary; axial otherwise. Never inferred from shapes
    (an axial nucleus may legally render as a glyph circle)."""
    if layout.layout_slug != "hub":
        return False
    if spec.hub_policy:
        return spec.hub_policy == "axial"
    compassish = (
        any(n.anchor for n in spec.nodes)
        or any(e.zone or e.angle is not None for e in spec.edges)
        or bool(spec.distribution)
    )
    return not compassish


# ── individual rules ─────────────────────────────────────────────────────────


def _mass_ratio(spec: DiagramSpec, layout: DiagramLayout, engine: Mapping[str, Any]) -> Diagnostic | None:
    bands = _cfg(engine).get("mass_bands") or {}
    klass = "axial" if _is_axial(spec, layout) else layout.layout_slug
    lo, hi = _band(bands, klass) or (0.0, 1.0)
    canvas = float(layout.width * layout.height) or 1.0
    ink = sum(n.box.w * n.box.h for n in layout.nodes)
    ink += sum(c.length * 3.0 for c in layout.connectors)
    ink += sum(a.box.w * a.box.h for a in layout.annotations if a.box is not None)
    measured = ink / canvas
    if lo <= measured <= hi:
        return None
    direction = "sparse — the canvas is billing for void" if measured < lo else "dense — the eye has nowhere to rest"
    return Diagnostic(
        rule="mass-ratio",
        measured=f"{measured:.2f} ink fraction ({klass})",
        band=f"[{lo:.2f}, {hi:.2f}] (§11.5a, centered on specimen ink)",
        suggestion=f"{direction}; split the diagram or trim descs/annotations",
    )


def _canonical_slot(spec: DiagramSpec, layout: DiagramLayout) -> Diagnostic | None:
    if layout.layout_slug != "hub" or _is_axial(spec, layout):
        return None
    hubs = [n for n in layout.nodes if n.shape == "circle"]
    if not hubs:
        return None
    hx, hy = hubs[0].box.x + hubs[0].box.w / 2, hubs[0].box.y + hubs[0].box.h / 2
    worst = 0.0
    for n in layout.nodes:
        if n.shape == "circle":
            continue
        ang = math.degrees(math.atan2((n.box.y + n.box.h / 2) - hy, (n.box.x + n.box.w / 2) - hx)) % 360.0
        dev = min(ang % 22.5, 22.5 - (ang % 22.5))
        worst = max(worst, dev)
    if worst <= 0.75:
        return None
    return Diagnostic(
        rule="canonical-slot",
        measured=f"{worst:.1f}° off the 22.5° rose grid",
        band="<= 0.75° (quantized slots)",
        suggestion="drop explicit angles and let the rose quantize, or align angle to a half-step multiple",
    )


def _sector_balance(spec: DiagramSpec, layout: DiagramLayout, engine: Mapping[str, Any]) -> Diagnostic | None:
    if layout.layout_slug != "hub" or _is_axial(spec, layout):
        return None
    zones: dict[str, int] = {}
    for e in spec.edges:
        z = e.zone or {"in": "W", "out": "E", "read": "S", "edit": "N"}.get(e.role, "E")
        zones[z] = zones.get(z, 0) + 1
    if len(zones) < 2:
        return None
    spread = max(zones.values()) - min(zones.values())
    cap = int(_cfg(engine).get("sector_spread_max", 2))
    if spread <= cap:
        return None
    return Diagnostic(
        rule="sector-balance",
        measured=f"sector occupancy spread {spread} ({zones})",
        band=f"at most {cap}",
        suggestion="rebalance roles/zones across the rose, or switch hub_policy to axial",
    )


def _margin_band(layout: DiagramLayout, engine: Mapping[str, Any]) -> Diagnostic | None:
    if not layout.regions:
        return None
    left = min(r.x for r in layout.regions)
    right = layout.width - max(r.x + r.w for r in layout.regions)
    top = min(r.y for r in layout.regions)
    bottom = layout.height - max(r.y + r.h for r in layout.regions)
    worst = min(top, right, bottom, left)
    # §2 margins are symmetric WITHIN each axis by construction — vertical
    # (top==bottom) and horizontal (left==right) — but the two axes differ
    # on purpose (a portrait chassis breathes wider left/right than top/
    # bottom). Compare each axis to ITSELF, never across axes. The rule fires
    # only on the real failures: a NEGATIVE inset (a region pushed off-canvas)
    # or a within-axis imbalance (one edge overran while its opposite did not
    # = an annotation or embed grew past its band).
    cap = float(_cfg(engine).get("margin_spread_max", 12))
    # The bottom band carries the caption law's designed difference — per-
    # family chassis caption_pad runs 11-97px against the generic 24, above
    # OR below it. Read the STAMPED margin off the bottom region itself,
    # never a parallel constant: the plate chassis is the one owner.
    bottom_region = max(layout.regions, key=lambda r: r.y + r.h)
    top_region = min(layout.regions, key=lambda r: r.y)
    caption_extra = float(bottom_region.margin[2]) - float(top_region.margin[0])
    if worst >= -0.5 and abs(top - (bottom - caption_extra)) <= cap and abs(left - right) <= cap:
        return None
    reason = "off-canvas" if worst < -0.5 else "asymmetric — a band overran one edge"
    return Diagnostic(
        rule="margin-band",
        measured=f"insets NSEW {top:.0f}/{right:.0f}/{bottom:.0f}/{left:.0f} ({reason})",
        band="uniform, non-negative (§2 region stack)",
        suggestion="an annotation or embed outgrew its band; shorten it or let the caption carry it",
    )


def _contrast(genome: Mapping[str, Any]) -> Diagnostic | None:
    ink = str(genome.get("ink") or genome.get("ink_primary") or "")
    surface = str(genome.get("surface_0") or "")
    if not ink or not surface:
        return None
    ratio = contrast_ratio(ink, surface)
    if ratio >= 4.5:
        return None
    return Diagnostic(
        rule="contrast",
        measured=f"ink vs surface_0 = {ratio:.2f}:1",
        band=">= 4.5:1 (AA)",
        suggestion="re-derive the variant ink through the Surface Modes machinery (LAW 2)",
    )


def _palette(spec: DiagramSpec, palette_len: int) -> Diagnostic | None:
    cats = {n.category for n in spec.nodes if n.category}
    if len(cats) <= palette_len:
        return None
    return Diagnostic(
        rule="palette",
        measured=f"{len(cats)} categories over {palette_len} flow hues",
        band=f"at most {palette_len} distinct hues",
        suggestion="hues will repeat; merge categories or accept cycled assignment",
    )


def _nucleus_underweight(spec: DiagramSpec, layout: DiagramLayout, engine: Mapping[str, Any]) -> Diagnostic | None:
    if not _is_axial(spec, layout):
        return None
    heroes = [n for n in layout.nodes if n.role == "hero"]
    sats = [n for n in layout.nodes if n.role != "hero"]
    if not heroes or not sats:
        return None
    # The §11.4a prominence factor is a CARD-vs-card measure (264x100 vs
    # 220x64 in axial). A glyph-circle nucleus draws its weight from
    # centrality + the emanation ring, not raw area, so comparing πr² to a
    # rectangle satellite is a category error — skip it.
    if heroes[0].shape == "circle":
        return None
    factor = float((engine.get("axial") or {}).get("prominence_factor", 1.9))
    hero_a = heroes[0].box.w * heroes[0].box.h
    sat_a = max(n.box.w * n.box.h for n in sats)
    measured = hero_a / sat_a if sat_a else factor
    if measured >= factor - 0.05:
        return None
    return Diagnostic(
        rule="nucleus-underweight",
        measured=f"hero/satellite area ratio {measured:.2f}",
        band=f">= {factor:.2f} (§11.4a ledger factor)",
        suggestion="a satellite outgrew the nucleus (long desc or chips); trim it or move detail into an embed",
    )


def _accent_unbound(spec: DiagramSpec, layout: DiagramLayout) -> Diagnostic | None:
    # Semantic Chromatics binding: a declared accent renders on the node's
    # TITLE (default role) or the nucleus ring/glyph (hero). A MUTED node is
    # de-emphasised — its title stays neutral, so a declared accent there has
    # nowhere to live (unbound). The rule covers title binding, not just the
    # old stroke/dot mark.
    from hyperweave.core.diagram import NodeRole

    declared = [n for n in spec.nodes if n.accent is not None]
    if not declared:
        return None
    unbound = [n.id or n.label for n in declared if n.role is NodeRole.MUTED]
    if not unbound:
        return None
    return Diagnostic(
        rule="accent-unbound",
        measured=f"{len(unbound)} declared accents on muted nodes ({', '.join(unbound[:4])})",
        band="a declared accent binds a title or the nucleus — never a muted node",
        suggestion="drop the accent on the muted node, or raise its role so the accent has a title to live on",
    )


def _unbundled_fan(spec: DiagramSpec, layout: DiagramLayout) -> Diagnostic | None:
    if layout.layout_slug != "hub" or _is_axial(spec, layout):
        return None
    outs = [e for e in spec.edges if e.role == "out" and not e.zone and e.angle is None]
    if len(outs) < 3:
        return None
    return Diagnostic(
        rule="unbundled-fan",
        measured=f"{len(outs)} same-role out-spokes on the compass rose",
        band="fans of 3+ read as a bundle (§11.4c gather-fan)",
        suggestion="switch hub_policy to axial: destinations gather east on tangent curves",
    )


def _unresolved_glyph(spec: DiagramSpec, layout: DiagramLayout) -> Diagnostic | None:
    """A node declared an identity (``glyph`` or ``kind``) but no mark
    rendered — either the slug does not resolve, or the node's style has no
    glyph slot (the default ``card`` draws none). Silent identity loss is
    the icon-or-nothing law's failure mode; name it so the caller learns
    the slug list and the style requirement instead of guessing."""
    placed = {n.node_id: n for n in layout.nodes}
    misses = [
        n.id or n.label
        for n in spec.nodes
        if (n.glyph or n.kind) and (p := placed.get(n.id)) is not None and p.glyph is None and p.shape != "circle"
    ]
    if not misses:
        return None
    return Diagnostic(
        rule="unresolved-glyph",
        measured=f"{len(misses)} declared identity, no mark: {', '.join(misses[:4])}",
        band="every declared glyph/kind renders a mark, or none is declared",
        suggestion="set node_style/style to card+glyph, and check the slug (discover what='glyphs' lists glyph_kinds)",
    )


def _relation_ambiguous(spec: DiagramSpec) -> Diagnostic | None:
    from hyperweave.config.loader import load_idioms

    present = sorted({e.relation for e in spec.edges if e.relation})
    if len(present) < 2:
        return None
    lines = load_idioms().get("line") or {}
    pairs = []
    for a, b in itertools.combinations(present, 2):
        da, db = lines.get(a, {}).get("dress") or {}, lines.get(b, {}).get("dress") or {}
        channels = ("texture", "terminal", "motion", "route")
        if all(da.get(c) == db.get(c) for c in channels):
            pairs.append(f"{a}~{b}")
    if not pairs:
        return None
    return Diagnostic(
        rule="relation-ambiguous",
        measured=f"indistinguishable relations: {', '.join(pairs)}",
        band="co-present relations differ on >= 1 dress channel (§3)",
        suggestion="pick one relation per meaning, or restore distinct dress in the idiom registry",
    )


def _crossing_count(layout: DiagramLayout, engine: Mapping[str, Any]) -> Diagnostic | None:
    bands = _cfg(engine).get("crossing_bands") or {}
    cap = int(_band(bands, layout.layout_slug) or 0)
    polys = [(c.index, sample_path(c.path_d)) for c in layout.connectors]
    count = count_polyline_crossings(polys)
    if count <= cap:
        return None
    return Diagnostic(
        rule="crossing-count",
        measured=f"{count} wire crossings",
        band=f"at most {cap} for {layout.layout_slug}",
        suggestion="reorder declaration (ranks follow it), pin ranks, or route long hauls around",
    )


def _visual_channel_collision(layout: DiagramLayout) -> Diagnostic | None:
    recipes: dict[tuple[str, str], set[str]] = {}
    for c in layout.connectors:
        dash = c.static_dash or ("5 7" if c.track == "dash-march" else "")
        if not dash:
            continue
        kind = "dot" if " A " in f" {c.marker_d} " else ("arrow" if c.marker_d else "none")
        source = f"relation:{c.relation}" if c.relation else "kind/semantic"
        recipes.setdefault((dash, kind), set()).add(source)
    mixed = [k for k, sources in recipes.items() if len(sources) > 1]
    if not mixed:
        return None
    return Diagnostic(
        rule="visual-channel-collision",
        measured=f"{len(mixed)} stroke recipes shared across semantic channels {sorted(recipes[mixed[0]])}",
        band="one visual recipe per meaning channel",
        suggestion="declare relations on ALL meaning-bearing edges, or drop the colliding semantic dash",
    )


def _nesting_depth(spec: DiagramSpec) -> Diagnostic | None:
    depth = 0
    for n in spec.nodes:
        if n.embed is not None:
            depth = max(depth, 1)
            if any(inner.embed is not None for inner in n.embed.nodes):
                depth = 2
    if depth < 2:
        return None
    return Diagnostic(
        rule="nesting-depth",
        measured="depth 2 (the cap)",
        band="<= 2 (deeper refuses at the seam)",
        suggestion="a depth-2 composition is dense by construction; consider linking sibling artifacts instead",
    )


def _nested_density(spec: DiagramSpec, engine: Mapping[str, Any]) -> Diagnostic | None:
    cap = int(_cfg(engine).get("nested_density_max", 7))
    heavy = [
        (n.id or n.label, len(n.embed.nodes)) for n in spec.nodes if n.embed is not None and len(n.embed.nodes) > cap
    ]
    if not heavy:
        return None
    name, count = heavy[0]
    return Diagnostic(
        rule="nested-density",
        measured=f"container {name!r} embeds {count} nodes",
        band=f"at most {cap} nodes per embed",
        suggestion="an embed is a thumbnail — split the inner diagram or promote it to its own artifact",
    )


def _annotation_failure(layout: DiagramLayout) -> Diagnostic | None:
    warnings = tuple(getattr(layout.rendered, "warnings", ()) or ())
    hits = [w for w in warnings if "annotation" in w.lower()]
    if not hits:
        return None
    return Diagnostic(
        rule="annotation-failure",
        measured=f"{len(hits)} unresolved placements ({hits[0]})",
        band="every annotation places without residue",
        suggestion="shorten the annotation, move its anchor, or drop it — unresolved chrome ships as declared",
    )


def _over_arc_zone_collision(layout: DiagramLayout) -> Diagnostic | None:
    """The over-arc return (state-machine exit:top — agent-runtime's re-plan)
    bows above the loop row; a zone header sharing that airspace reads INTO the
    return. Advisory (the control-loop idiom, per-class diagnostic): move the
    header off the arc's airspace or lift the arc."""
    headers = [b.header for b in layout.lane_bands if b.header and "zone" in b.header.cls]
    if not headers:
        return None
    for c in layout.connectors:
        pts = sample_path(c.path_d)
        if len(pts) < 3:
            continue
        ends_y = (pts[0][1], pts[-1][1])
        apex_y = min(p[1] for p in pts)
        if apex_y > min(ends_y) - 20.0:  # not an over-arc (does not rise above its ends)
            continue
        lo_x, hi_x = min(p[0] for p in pts), max(p[0] for p in pts)
        for h in headers:
            if lo_x - 12.0 <= h.x <= hi_x + 12.0 and apex_y - 12.0 <= h.y <= min(ends_y):
                return Diagnostic(
                    rule="over-arc-zone-collision",
                    measured=f"return apex y={apex_y:.0f} crowds zone header {h.text!r} at ({h.x:.0f},{h.y:.0f})",
                    band=">= 12px clear between an exit:top return and a zone header",
                    suggestion="move the zone header off the return's airspace, or lift the arc (its band frames it)",
                )
    return None


def run_diagnostics(
    spec: DiagramSpec,
    layout: DiagramLayout,
    *,
    genome: Mapping[str, Any],
    engine: Mapping[str, Any],
    palette_len: int,
) -> tuple[Diagnostic, ...]:
    """Run every advisory rule; a clean artifact returns ()."""
    checks = (
        _over_arc_zone_collision(layout),
        _mass_ratio(spec, layout, engine),
        _canonical_slot(spec, layout),
        _sector_balance(spec, layout, engine),
        _margin_band(layout, engine),
        _contrast(genome),
        _palette(spec, palette_len),
        _nucleus_underweight(spec, layout, engine),
        _accent_unbound(spec, layout),
        _unbundled_fan(spec, layout),
        _unresolved_glyph(spec, layout),
        _relation_ambiguous(spec),
        _crossing_count(layout, engine),
        _visual_channel_collision(layout),
        _nesting_depth(spec),
        _nested_density(spec, engine),
        _annotation_failure(layout),
    )
    return tuple(d for d in checks if d is not None)
