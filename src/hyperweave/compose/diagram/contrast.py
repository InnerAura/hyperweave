"""Backing-aware glyph contrast gate.

Runs RESOLVER-side, after hue substitution — the solver stays genome-blind;
this pass knows the genome's actual surface hexes.

Neither shape carries a plate: a card's mark checks against the card surface
(``surface_1``); a circle carries no independent backing and sits bare on the
paper (``surface_0``), so it checks directly against that. The remedy ladder
is the same for both, keyed only by which surface the shape reads against:

0. DEFAULT / PLATELESS — the mark reads directly on its surface (the WCAG
   ratio clears the threshold, or the mark is chromatically distinct — a
   solid saturated color reads through hue long before it clears 3:1, e.g.
   HF yellow on a dusk paper) — full color, unchanged.
1. DEGRADE — a mark that fails its surface degrades toward ink (brand, then
   ink), evaluated per node. Brand colors are never altered.

Ink-tint marks are exempt (ink is designed to read on every surface the
genome ships — it paints with ``var(--dna-ink-primary)``, which the twin's
far ``@media`` block re-declares for free). Per-node outcomes are recorded in
the payload's ``rendered.glyph_backing`` so requested vs rendered never
silently diverges.

TWIN AWARENESS: a brand/full/gradient mark paints with a LITERAL hex or a
fixed SVG gradient — neither re-inks when an adaptive twin's far face flips
(unlike ink, there is no var to ride). Checking only the near surface passes
an achromatic brand mark that happens to read fine on its OWN face (e.g. an
anthropic/openai near-black wordmark on a light near card) while it goes
invisible on the twin's far face, whose card flips dark. ``far_genome``
(optional; the sparse ``flip_palette()`` dict, ``surface_0``/``surface_1``
only needed) extends every readability check to require BOTH faces clear the
threshold — empty/absent for a plate render, so the gate's plate behavior is
byte-identical to before.
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
    far_genome: Mapping[str, Any] | None = None,
) -> DiagramLayout:
    """Gate every node's identity mark against the surface(s) it actually sits
    on (bare paper for a circle, the card fill for a card/pill); returns the
    layout with degraded marks applied and per-node outcomes on
    ``rendered.glyph_backing``. ``rebuild`` is
    ``(glyph_id, tint, cx, cy, size) -> GlyphArt | None``. ``far_genome``
    (sparse ``flip_palette()`` output) adds the twin's far surface to every
    check — a mark must clear the threshold on BOTH faces or it degrades."""
    cfg = engine.get("glyph_contrast") or {}
    paper = str(genome.get("surface_0", "#FFFFFF"))
    card = str(genome.get("surface_1", "#FFFFFF"))
    far_paper = str((far_genome or {}).get("surface_0") or "")
    far_card = str((far_genome or {}).get("surface_1") or "")

    outcomes: dict[int, str] = {}
    nodes = list(layout.nodes)

    def reads(hexes: list[str], surfaces: list[str]) -> bool:
        return all(_reads_on(hexes, surface, cfg) for surface in surfaces)

    def degrade(n: NodePlacement, art: GlyphArt, surfaces: list[str]) -> NodePlacement:
        """Brand, then ink — the only remedy past a failing full-color mark."""
        for mode in _DEGRADE:
            candidate = rebuild(art.glyph_id, mode, art.cx, art.cy, art.size)
            if candidate is None:
                continue
            if candidate.tint == "ink":
                outcomes[n.index] = "tint-ink"
                return replace(n, glyph=candidate)
            if reads(_mark_hexes(candidate, registry), surfaces):
                outcomes[n.index] = f"tint-{candidate.tint}"
                return replace(n, glyph=candidate)
        return n

    for i, n in enumerate(nodes):
        if n.glyph is None:
            continue
        # A circle carries no plate (kit anatomy: a bare ring on the paper);
        # a card/pill checks against its own surface fill. The far surface
        # (twin only) rides alongside — both must clear, or the mark degrades.
        is_circle = n.shape == "circle"
        surface = paper if is_circle else card
        far_surface = far_paper if is_circle else far_card
        surfaces = [surface, far_surface] if far_surface else [surface]
        if n.glyph.tint == "ink":
            outcomes[n.index] = "exempt-ink"
            continue
        hexes = _mark_hexes(n.glyph, registry)
        if not hexes or reads(hexes, surfaces):
            outcomes[n.index] = "plateless" if is_circle else "default"
            continue
        nodes[i] = degrade(n, n.glyph, surfaces)

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
