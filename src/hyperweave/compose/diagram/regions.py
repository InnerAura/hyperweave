"""§2 REGION TREE — LAW 1 as composition (diagrams-v2).

The artifact is a one-level region tree: ``masthead`` (title, subtitle,
optional satellite legend), ``content`` (the solved topology), ``footer``
(attribution line). Each region measures its OWN content; the parent stacks
regions vertically, places chrome bands OUTSIDE the content bbox, sets the
canvas to the union plus per-side margins, and centers the whole
composition. No fixed y exists anywhere in chrome — every baseline derives
from stacking, so a taller title block pushes content down instead of
overlapping it, and an empty masthead costs zero band.

This is exactly LAW 1 — canvas hugs content, everything centers, chrome
never overlaps — built as the degenerate (one-level) case of a recursive
engine. §12.1's nested topologies are the relaxation ("a region may contain
a topology solver"), landing on this same structure: an inner solve's
finished canvas becomes a container node's content box.

The region tree is PUBLIC anatomy (§10.1a): the template wraps each region
in ``<g data-hw-region>`` and the payload carries the region map (id, bbox,
margin, strategy), so agents reason over nested structure instead of flat
coordinates and ``extract``/``query`` answer region-addressable questions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import DiagramText

# Per-side margins are (N, E, S, W) — reading order of a compass clock.
Margins = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class RegionBox:
    """One placed region of the artifact's public anatomy."""

    id: str
    x: float
    y: float
    w: float
    h: float
    margin: Margins
    strategy: str = "block"
    children: tuple[RegionBox, ...] = ()

    def as_payload(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "id": self.id,
            "bbox": [round(self.x, 1), round(self.y, 1), round(self.w, 1), round(self.h, 1)],
            "margin": [round(m, 1) for m in self.margin],
            "strategy": self.strategy,
        }
        if self.children:
            entry["children"] = [c.as_payload() for c in self.children]
        return entry


@dataclass(slots=True)
class MeasuredRegion:
    """A region's content measured in its own local coordinates, before the
    parent stacks it. ``w``/``h`` are the content extents; ``margin`` is the
    breathing room the parent must grant on each side."""

    id: str
    w: float
    h: float
    margin: Margins
    align: str = "left"  # left | center — horizontal placement in the stack
    texts: list[DiagramText] = field(default_factory=list)
    satellites: list[MeasuredRegion] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class StackedLayout:
    """The parent's verdict: canvas size plus each region's placement."""

    width: int
    height: int
    regions: tuple[RegionBox, ...]
    offsets: dict[str, tuple[float, float]]
    """Region id → (dx, dy) translation from region-local to canvas coords."""


def stack_regions(regions: list[MeasuredRegion], *, min_width: float = 0.0) -> StackedLayout:
    """Stack regions vertically and center the composition (§2).

    The canvas width is the widest region's content plus its E+W margins
    (floored by ``min_width``); every region then places at its own alignment
    within that width. Heights accumulate: each region's top is the previous
    region's bottom plus the meeting margins (the LARGER of the two wins —
    margins are breathing room, not additive gaps). An empty region (zero
    content) contributes nothing: no band, no margin — chrome costs exactly
    what it renders.
    """
    live = [r for r in regions if r.w > 0 and r.h > 0]
    if not live:
        side = max(min_width, 0.0)
        return StackedLayout(width=round(side), height=0, regions=(), offsets={})

    width = max(max(r.w + r.margin[1] + r.margin[3] for r in live), min_width)

    placed: list[RegionBox] = []
    offsets: dict[str, tuple[float, float]] = {}
    y = 0.0
    prev_bottom_margin = 0.0
    for i, r in enumerate(live):
        top_gap = r.margin[0] if i == 0 else max(prev_bottom_margin, r.margin[0])
        y += top_gap
        x = (width - r.w) / 2.0 if r.align == "center" else r.margin[3]
        placed.append(RegionBox(id=r.id, x=x, y=y, w=r.w, h=r.h, margin=r.margin, strategy="block"))
        offsets[r.id] = (x, y)
        y += r.h
        prev_bottom_margin = r.margin[2]
    height = y + prev_bottom_margin

    return StackedLayout(
        width=round(width),
        height=round(height),
        regions=tuple(placed),
        offsets=offsets,
    )
