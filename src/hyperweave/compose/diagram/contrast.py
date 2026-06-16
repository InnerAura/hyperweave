"""Backing-aware glyph contrast gate (G5 v3).

Runs RESOLVER-side, after hue substitution — the solver stays genome-blind;
this pass knows the genome's actual surface hexes.

Plate tokens are a SET-LEVEL invariant: the glyph-circle class of a layout
is treated uniformly — plateless together, or on ONE shared plate — never a
per-node checkerboard. The remedy ladder per node class per paper:

0. PLATELESS — if every gated mark reads directly on the paper
   (``surface_0``), the circles drop their fill and the marks sit on the
   paper, full color intact. "Reads" = the WCAG ratio clears the threshold
   OR the mark is chromatically distinct (RGB distance) with a small
   luminance floor — a solid saturated mark (HF yellow on dusk) reads
   through hue long before it clears 3:1.
1. UNIFORM PLATE — when the paper swallows any mark, the WHOLE class takes
   the genome plate (light or dark) that carries the set best. Ink-mode
   marks and mono shorts riding a swapped plate take the plate's
   counter-ink (the sibling plate's fill) so "ink contrasts by
   construction" stays true on the plate.
2. DEGRADE — marks that still fail on the shared plate degrade toward ink
   (brand, then ink). Brand colors are never altered.

Cards have no plate construct: their marks check against the card surface
and degrade tint directly. Per-node outcomes are recorded in the payload's
``rendered.glyph_backing`` so requested vs rendered never silently
diverges.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from hyperweave.core.color import contrast_ratio
from hyperweave.core.matrix import GlyphTint

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hyperweave.compose.diagram.records import DiagramLayout, GlyphArt, NodePlacement

_DEGRADE: tuple[GlyphTint, ...] = (GlyphTint.BRAND, GlyphTint.INK)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_distance(a: str, b: str) -> float:
    import math

    (r1, g1, b1), (r2, g2, b2) = _rgb(a), _rgb(b)
    return math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)


def _expand(hex_color: str) -> str:
    """#abc -> #aabbcc (color_paths masters use both forms)."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return f"#{h}"


def _mark_hexes(art: GlyphArt, registry: Mapping[str, Any]) -> list[str]:
    """Every literal hex the mark paints with (gradient stops, color_paths
    fills, the brand fill). Ink marks paint with a CSS var — exempt."""
    hexes: list[str] = []
    if art.gradient:
        entry = registry.get(art.glyph_id) or {}
        for stop in (entry.get("gradient") or {}).get("stops", []):
            color = str(stop.get("color", ""))
            if color.startswith("#"):
                hexes.append(_expand(color))
    for p in art.paths:
        fill = str(getattr(p, "fill", "") or "")
        if fill.startswith("#"):
            hexes.append(_expand(fill))
    if art.fill.startswith("#"):
        hexes.append(_expand(art.fill))
    return hexes


def _reads_on(hexes: list[str], surface: str, cfg: Mapping[str, Any]) -> bool:
    """A mark reads when its BEST color clears the surface: the WCAG ratio
    at the threshold, or chromatic distinctness with a luminance floor."""
    threshold = float(cfg.get("threshold", 3.0))
    chroma_floor = float(cfg.get("chroma_floor", 120))
    chroma_lum_floor = float(cfg.get("chroma_lum_floor", 1.2))
    for h in hexes:
        ratio = contrast_ratio(h, surface)
        if ratio >= threshold:
            return True
        if _rgb_distance(h, surface) >= chroma_floor and ratio >= chroma_lum_floor:
            return True
    return False


def apply_glyph_contrast(
    layout: DiagramLayout,
    *,
    genome: dict[str, Any],
    registry: Mapping[str, Any],
    engine: Mapping[str, Any],
    rebuild: Any,
) -> DiagramLayout:
    """Gate the layout's identity marks per the v3 ladder; returns the
    layout with the class treatment applied and per-node outcomes on
    ``rendered.glyph_backing``. ``rebuild`` is
    ``(glyph_id, tint, cx, cy, size) -> GlyphArt | None``."""
    cfg = engine.get("glyph_contrast") or {}
    paper = str(genome.get("surface_0", "#FFFFFF"))
    card = str(genome.get("surface_1", "#FFFFFF"))
    plates = genome.get("diagram_plates") or {}
    plate_fill = {"plate-light": str(plates.get("light", "#FFFFFF")), "plate-dark": str(plates.get("dark", "#141414"))}
    counter_ink = {"plate-light": plate_fill["plate-dark"], "plate-dark": plate_fill["plate-light"]}

    outcomes: dict[int, str] = {}
    nodes = list(layout.nodes)

    def degrade(n: NodePlacement, art: GlyphArt, surface: str, ink_fill: str) -> NodePlacement:
        """Brand, then ink (ink fill overridable for plated classes)."""
        for mode in _DEGRADE:
            candidate = rebuild(art.glyph_id, mode, art.cx, art.cy, art.size)
            if candidate is None:
                continue
            if candidate.tint == "ink":
                if ink_fill:
                    candidate = replace(candidate, fill=ink_fill)
                outcomes[n.index] = "tint-ink"
                return replace(n, glyph=candidate)
            if _reads_on(_mark_hexes(candidate, registry), surface, cfg):
                outcomes[n.index] = f"tint-{candidate.tint}"
                return replace(n, glyph=candidate)
        return n

    # ── The glyph-circle class: one uniform treatment (v2 cohesion law) ──
    circle_ix = [i for i, n in enumerate(nodes) if n.shape == "circle"]

    def gated_art(i: int) -> GlyphArt:
        art = nodes[i].glyph
        assert art is not None  # membership in `gated` guarantees it
        return art

    gated = [i for i in circle_ix if (a := nodes[i].glyph) is not None and a.tint != "ink" and _mark_hexes(a, registry)]
    if not gated:
        # No color marks under the gate: the class keeps its canon coins.
        for i in circle_ix:
            art0 = nodes[i].glyph
            if art0 is not None and art0.tint == "ink":
                outcomes[nodes[i].index] = "exempt-ink"
    elif circle_ix:
        if all(_reads_on(_mark_hexes(gated_art(i), registry), paper, cfg) for i in gated):
            # Step 0: plateless — marks sit on the paper, full color intact.
            for i in circle_ix:
                nodes[i] = replace(nodes[i], plate_fill="none")
                art1 = nodes[i].glyph
                if art1 is not None:
                    outcomes[nodes[i].index] = "exempt-ink" if art1.tint == "ink" else "plateless"
        else:
            # Step 1: ONE plate for the whole class — scored by the worst
            # gated mark's best color (set-min lum ratio).
            def plate_score(token: str) -> float:
                surface = plate_fill[token]
                return min(
                    (max(contrast_ratio(h, surface) for h in _mark_hexes(gated_art(i), registry)) for i in gated),
                    default=21.0,
                )

            token = max(("plate-light", "plate-dark"), key=plate_score)
            surface = plate_fill[token]
            ink_fill = counter_ink[token]
            for i in circle_ix:
                n = nodes[i]
                n = replace(n, plate_fill=surface, plate_ink=ink_fill)
                art = n.glyph
                if art is not None:
                    if art.tint == "ink":
                        n = replace(n, glyph=replace(art, fill=ink_fill))
                        outcomes[n.index] = token
                    elif _reads_on(_mark_hexes(art, registry), surface, cfg):
                        outcomes[n.index] = token
                    else:
                        n = degrade(n, art, surface, ink_fill)
                nodes[i] = n

    # ── Cards: no plate construct — check the card surface, degrade tint ─
    for i, n in enumerate(nodes):
        if n.shape == "circle" or n.glyph is None:
            continue
        if n.glyph.tint == "ink":
            outcomes[n.index] = "exempt-ink"
            continue
        hexes = _mark_hexes(n.glyph, registry)
        if not hexes or _reads_on(hexes, card, cfg):
            outcomes[n.index] = "default"
            continue
        nodes[i] = degrade(n, n.glyph, card, "")

    n_nodes = len(layout.rendered.glyph_tint)
    tint_by_index = dict(zip(range(n_nodes), layout.rendered.glyph_tint, strict=False))
    for n in nodes:
        if n.glyph is not None:
            tint_by_index[n.index] = n.glyph.tint
    rendered = replace(
        layout.rendered,
        glyph_backing=tuple(outcomes.get(i, "") for i in range(n_nodes)),
        glyph_tint=tuple(tint_by_index.get(i, "") for i in range(n_nodes)),
    )
    return replace(layout, nodes=tuple(nodes), rendered=rendered)
