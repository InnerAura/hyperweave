"""Frozen spatial records for the matrix frame — the template seam.

``MatrixLayout`` mirrors ``ChartLayout``/``StatsLayout``: a frozen record of
fully-resolved primitives. Templates do pure substitution over these fields
and contain zero arithmetic (guard-tested).

``CellPlacement`` is THE SEAM between the solver and the cell partials:
one flat record dispatched by ``kind`` — every concrete kind maps 1:1 to
``frames/matrix/cells/{kind}.j2``, and each partial consumes only the
fields its kind populates. Paint fields (``text_fill``, ``tone``,
``glyph_fill``) arrive pre-resolved as either ``var(--dna-*)`` references
(chassis) or semantic literals from data/matrix.yaml (genome-invariant
indicators); empty string defers to the partial's chassis default class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hyperweave.compose.spatial_records import LineSpec, RectSpec, TextSpec


@dataclass(frozen=True, slots=True)
class ChipPlacement:
    """One packed chip (or the ``+N`` overflow chip) inside a chip cell."""

    rect: RectSpec
    text: str
    text_x: float
    text_y: float
    overflow: bool = False


@dataclass(frozen=True, slots=True)
class GlyphPath:
    """One path of a glyph mark; empty ``fill`` inherits the group fill."""

    d: str
    fill: str = ""


@dataclass(frozen=True, slots=True)
class CellPlacement:
    """One placed cell. ``kind`` is always a concrete slug, never ``auto``.

    ``row`` is the row index; ``-1`` marks masthead legend usage and
    ``len(rows)`` marks summary-row cells. ``cls`` names a type voice
    defined in the paradigm defs (``{{ uid }}-{{ cell.cls }}``).
    """

    kind: str
    row: int
    col: int
    box: RectSpec
    emphasis: bool = False
    note: str = ""
    # -- text run (text / numeric value / pill text / bar value / labels) --
    text: str = ""
    text_x: float = 0.0
    text_y: float = 0.0
    text_anchor: str = "middle"
    cls: str = ""
    text_fill: str = ""
    text_length: float = 0.0
    text_lines: tuple[TextSpec, ...] = ()
    """Wrapped text runs (multiline overflow). When present, the cell
    renders these instead of the single ``text`` run — wrapping is the
    default for text content that outruns its column; the ellipsis is the
    last resort on the final permitted line."""
    # -- second line (row sublabel / bar unit / summary qualifier) --
    sub_text: str = ""
    sub_x: float = 0.0
    sub_y: float = 0.0
    sub_cls: str = ""
    sub_fill: str = ""
    # -- indicator paint --
    tone: str = ""
    tone_opacity: float = 1.0
    # -- check --
    mark_d: str = ""
    mark_state: str = ""
    stroke_width: float = 0.0
    # -- dot --
    dot_cx: float = 0.0
    dot_cy: float = 0.0
    dot_r: float = 0.0
    dot_filled: bool = False
    dot_stroke_w: float = 0.0
    # -- bar --
    track: RectSpec | None = None
    bar_fill: RectSpec | None = None
    # -- pill --
    pill: RectSpec | None = None
    pill_gradient: bool = False
    # -- numeric heat --
    heat_tile: RectSpec | None = None
    heat_track: RectSpec | None = None
    heat_underline: RectSpec | None = None
    # -- chip --
    chips: tuple[ChipPlacement, ...] = ()
    chip_fill_opacity: float = 0.0
    # -- glyph --
    glyph_paths: tuple[GlyphPath, ...] = ()
    glyph_transform: str = ""
    glyph_fill: str = ""
    glyph_opacity: float = 1.0
    glyph_gradient: str = ""
    glyph_fill_rule: str = ""
    """Registry fill-rule (e.g. 'evenodd'), stamped on the mark group —
    inherited by every path; the evenodd marks break without it."""
    """Registry id whose brand gradient fills this mark. Non-empty routes the
    group fill to ``url(#{uid}-gg-{glyph_gradient})``; the defs emit one
    linearGradient per gradient id used (Gemini's four-stop spark)."""


@dataclass(frozen=True, slots=True)
class ColHeader:
    """One column header: label line, optional sublabel line."""

    label: TextSpec
    sublabel: TextSpec | None = None
    accent: bool = False


@dataclass(frozen=True, slots=True)
class SectionBand:
    """Row-group band: faint wash + bold section label."""

    band: RectSpec
    label: TextSpec
    band_opacity: float = 0.024


@dataclass(frozen=True, slots=True)
class HeaderBlock:
    """Masthead: title, descriptor, rule, scan rail, optional headline chip
    and indicator legend (legend marks are CellPlacements with row == -1).

    Every field is optional: a spec with no title/subtitle/headline
    collapses the masthead entirely (the zone releases its space)."""

    title: TextSpec | None
    subtitle: TextSpec | None
    rule: LineSpec | None
    scan: RectSpec | None = None
    headline_chip: RectSpec | None = None
    headline_value: TextSpec | None = None
    headline_label: TextSpec | None = None
    key_marks: tuple[CellPlacement, ...] = ()
    key_texts: tuple[TextSpec, ...] = ()
    key_rects: tuple[RectSpec, ...] = ()
    """Legend mark rects (the tier-span key's mini reach bar) — rendered
    in the genome signal at the span wash opacity."""


@dataclass(frozen=True, slots=True)
class TierSpan:
    """One tier-reach span: a vertical bar from the table's top to the
    column's last included row, closed by a terminal dot. The chain
    projection — spans replace the dot grid when inclusion sets are
    totally ordered."""

    bar: RectSpec
    dot_cx: float
    dot_cy: float
    dot_r: float


@dataclass(frozen=True, slots=True)
class AxisSpec:
    """Bar-scale axis: vertical gridlines + tick labels + axis caption."""

    grid_lines: tuple[LineSpec, ...] = ()
    tick_labels: tuple[TextSpec, ...] = ()
    caption: TextSpec | None = None


@dataclass(frozen=True, slots=True)
class SummaryBlock:
    """Summary band chrome; summary CELLS live in ``MatrixLayout.cells``
    with ``row == len(rows)``."""

    rule: LineSpec
    label: TextSpec | None = None


@dataclass(frozen=True, slots=True)
class FooterBlock:
    """Footer: accent seam, optional notes line, brand mark."""

    seam: LineSpec
    notes: TextSpec | None = None
    brand: TextSpec | None = None


@dataclass(frozen=True, slots=True)
class MatrixLayout:
    """Fully-resolved matrix geometry; the template substitutes, never computes."""

    width: int
    height: int
    col_x: tuple[float, ...]
    col_w: tuple[float, ...]
    row_y: tuple[float, ...]
    row_h: tuple[float, ...]
    header: HeaderBlock
    colheaders: tuple[ColHeader, ...] = ()
    section_bands: tuple[SectionBand, ...] = ()
    cells: tuple[CellPlacement, ...] = ()
    hero_band: RectSpec | None = None
    hero_cap: RectSpec | None = None
    hero_band_opacity: float = 0.055
    extent_bars: tuple[RectSpec, ...] = ()
    axis: AxisSpec | None = None
    summary: SummaryBlock | None = None
    guides: tuple[LineSpec, ...] = ()
    guide_opacity: float = 0.06
    row_stripes: tuple[RectSpec, ...] = ()
    stripe_opacity: float = 0.024
    title_voice_size: float = 33.0
    """Active title size — steps down on compact frames so the masthead
    stays proportionate to the table. The defs voice block emits this."""
    tier_spans: tuple[TierSpan, ...] = ()
    """Chain projection: per-column reach bars + terminal dots replacing
    the dot grid (empty for non-chain matrices)."""
    tier_span_opacity: float = 0.28
    footer: FooterBlock | None = None
    rects: dict[str, RectSpec] = field(default_factory=dict)
    lines: dict[str, LineSpec] = field(default_factory=dict)
    texts: dict[str, TextSpec] = field(default_factory=dict)
