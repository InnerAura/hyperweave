"""The meter kit piece — a declared segment gauge riding a return chip.

Derived on the FROZEN layout (the choreography precedent): the strip's
geometry comes entirely from its chip's placed ``edge-chip`` annotation box,
so it rides none of the solve-time normalization channels. Constants live in
the ``loop:`` meter block of ``data/config/diagram-frame.yaml``, cited from
the three meter specimens (the lap counter, the budget drain, the
accumulator). The STATIC gauge draws on every face — plate, lead mark, base
segment row; the register's choreography supplies the fill layer.

The lead mark is register-semantic (the specimens' own tints): the lap
counter's rotate arc in muted ink, the budget's rotate arc in the
complement, the accumulator's trend line in the accent.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.chrome import glyph_slot_builder
from hyperweave.compose.diagram.records import DiagramLayout, MeterStrip
from hyperweave.compose.spatial_records import RectSpec
from hyperweave.core.diagram import resolved_edges
from hyperweave.core.matrix import GlyphTint

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hyperweave.core.diagram import DiagramSpec

_REGISTER_MARKS: dict[str, tuple[str, str]] = {
    # register -> (glyph kind, hue class). The lap counter and the budget
    # share the rotate arc (one turn of the counted thing); the accumulator
    # draws the trend. Tints are the specimens' own: muted ink for the
    # neutral count, the complement for the drain, the accent for the gain —
    # stroked via CSS class, never an attribute var() (the complement has no
    # root custom property; an attribute var() paints nothing).
    "laps": ("rotate-cw", "M"),
    "budget": ("rotate-cw", "C"),
    "accumulate": ("trending-up", "A"),
}


def _mcfg(engine: Mapping[str, Any], key: str, default: float) -> float:
    return float((engine.get("loop") or {}).get(key, default))


def apply_meters(
    layout: DiagramLayout,
    spec: DiagramSpec,
    *,
    register: str,
    engine: Mapping[str, Any],
    glyph_registry: Mapping[str, Any] | None,
) -> DiagramLayout:
    """Attach the static meter strips to a loop layout. No metered return,
    or a non-loop layout: byte-identical passthrough."""
    if not layout.layout_slug.startswith("loop"):
        return layout
    metered = {k for k, e in enumerate(resolved_edges(spec)) if e.meter}
    if not metered:
        return layout
    seg_h = _mcfg(engine, "meter_seg_h", 10.0)
    seg_rx = _mcfg(engine, "meter_seg_rx", 3.0)
    seg_gap = _mcfg(engine, "meter_seg_gap", 6.0)
    gap = _mcfg(engine, "meter_gap", 10.0)
    w_min = _mcfg(engine, "meter_seg_w_min", 14.0)
    w_max = _mcfg(engine, "meter_seg_w_max", 22.0)
    glyph_w = _mcfg(engine, "meter_glyph_w", 14.0)
    pad = _mcfg(engine, "meter_pad", 11.0)
    wrap = _mcfg(engine, "meter_wrap", 8.0)
    plate_rx = _mcfg(engine, "meter_plate_rx", 8.0)
    edges = resolved_edges(spec)
    strips: list[MeterStrip] = []
    for ann in layout.annotations:
        if ann.kind != "edge-chip" or ann.edge_index not in metered or ann.box is None:
            continue
        n = edges[ann.edge_index].meter
        chip = ann.box
        # The row spans the chip's own width (the row-spans-the-chip law:
        # the lap counter's 86-wide row under its 86.7 chip); segments size
        # by count at the cited gap, clamped to the corpus band.
        seg_w = max(w_min, min(w_max, (chip.w - (n - 1) * seg_gap) / n))
        row_w = n * seg_w + (n - 1) * seg_gap
        # Plate: mark + row at 14px pads (the accumulator's 222 = 14 + 18 +
        # 14 + 162 + 14, exact), seated 4 under the chip, 33 tall rx 11 —
        # derived as pads + row so a narrow chip keeps the same air.
        plate_w = pad + glyph_w + pad + row_w + pad
        # Chip bottom -> row top is meter_gap; the plate wraps the row at
        # meter_wrap above and below, seating its own top just under the
        # chip — the specimens' construction at the owner-ruled scale.
        row_y = chip.y + chip.h + gap
        plate_y = row_y - wrap
        plate_h = wrap + seg_h + wrap
        plate_x = chip.x + chip.w / 2 - plate_w / 2
        plate = RectSpec(x=plate_x, y=plate_y, w=plate_w, h=plate_h, rx=plate_rx)
        boxes = tuple(
            RectSpec(x=plate_x + pad + glyph_w + pad + i * (seg_w + seg_gap), y=row_y, w=seg_w, h=seg_h, rx=seg_rx)
            for i in range(n)
        )
        kind, hue = _REGISTER_MARKS.get(register, ("rotate-cw", "M"))
        art = glyph_slot_builder(kind, glyph_registry, GlyphTint.INK, size=glyph_w)(
            plate_x + pad + glyph_w / 2, row_y + seg_h / 2
        )
        strips.append(MeterStrip(edge_index=ann.edge_index, plate=plate, boxes=boxes, glyph=art, hue=hue))
    if not strips:
        return layout
    return replace(layout, meters=tuple(strips))
