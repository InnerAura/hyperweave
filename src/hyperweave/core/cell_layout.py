"""Centralized text + cell-layout measurement.

Single source of truth for translating ``(label, value, font config)`` into
rendered pixel widths and resolved per-cell coordinates. Resolvers build
``TextSpec`` inputs, call ``compute_cell_layout``, and pass the resulting
``CellLayout`` straight to templates — templates render the coordinates
verbatim with zero arithmetic. The previous split (resolver measured cell
width without letter-spacing, template re-derived ``text_x`` from
``cell_w // 2``, paradigm YAML declared a font weight that nobody read
back during measurement) drifted whenever a paradigm changed any of those
parameters and produced symptoms like long labels bleeding past right
dividers and short values crowding into them. Centralizing measurement +
layout here makes adding a new paradigm a YAML-only edit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from hyperweave.core.text import measure_text


@dataclass(frozen=True, slots=True)
class TextSpec:
    """Every parameter that affects a text run's rendered pixel width."""

    text: str
    font_family: str
    font_size: float
    font_weight: int = 400
    letter_spacing_em: float = 0.0

    @property
    def rendered_width(self) -> float:
        return measure_text(
            self.text,
            font_family=self.font_family,
            font_size=self.font_size,
            font_weight=self.font_weight,
            letter_spacing_em=self.letter_spacing_em,
        )


@dataclass(frozen=True, slots=True)
class CellLayout:
    """Resolved geometry for one metric cell.

    Templates render: ``<g transform="translate(cell_x_running, 0)">``
    with text at ``x=label_x`` and ``text-anchor=text_anchor``. No
    further math required template-side.
    """

    cell_w: int
    label_x: float
    value_x: float
    text_anchor: str
    label_w: float
    value_w: float
    content_w: float


def compute_cell_layout(
    label: TextSpec,
    value: TextSpec,
    *,
    cell_pad: float,
    anchor: str,
    text_inset: float,
    min_cell_w: int = 0,
) -> CellLayout:
    """Resolve a metric cell's geometry from label + value specs.

    ``cell_w`` is ``ceil(max(label_w, value_w) + cell_pad)`` floored
    by ``min_cell_w``. ``label_x``/``value_x`` are coordinates inside
    the cell: at ``text_inset`` for ``anchor='start'``, at
    ``cell_w / 2`` for ``'middle'``, at ``cell_w - text_inset`` for
    ``'end'``.
    """
    label_w = label.rendered_width
    value_w = value.rendered_width
    content_w = max(label_w, value_w)
    cell_w = max(math.ceil(content_w + cell_pad), int(min_cell_w))
    if anchor == "start":
        text_x = float(text_inset)
    elif anchor == "end":
        text_x = float(cell_w - text_inset)
    else:
        text_x = cell_w / 2.0
    return CellLayout(
        cell_w=cell_w,
        label_x=text_x,
        value_x=text_x,
        text_anchor=anchor,
        label_w=label_w,
        value_w=value_w,
        content_w=content_w,
    )
