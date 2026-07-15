"""Caller-annotation kind placement — the initial geometry of each overlay.

``annotate.py`` orchestrates the chrome pass and owns edge-label subsumption;
this module owns the PREFERRED geometry of the five caller kinds (callout,
aside, legend) plus the shared text-block measurement helpers both
modules use. Each ``place_*`` returns an ``AnnotationPlacement`` whose box and
runs are the annotation's wanted position — ``collide.py`` moves it off the
graph afterward.

Swappability: NO appearance value lives here as a literal. Every proportion a
genome re-skin might tune — box padding, line leading, callout lead, dot and
swatch radii, legend gaps, and the font ascent/descent ratios —
arrives in a :class:`ChromeStyle` built once from the engine ``annotate:``
block and the paradigm's text-metric ratios. Placement math consumes geometry
and semantic indices only; the records carry boxes, points, paths, and class
names, never hex or sizes. A primer re-skin therefore edits YAML + voices +
genome CSS, and this module stays byte-identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram.paths import diamond_d, line_stub_d, square_d
from hyperweave.compose.diagram.records import AnnotationPlacement, DiagramText, LegendEntry
from hyperweave.compose.diagram.sizing import voice_for
from hyperweave.compose.matrix.cells import measure_voice, wrap_text_lines
from hyperweave.compose.spatial_records import RectSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hyperweave.core.diagram_annotations import DiagramAnnotation
    from hyperweave.core.paradigm import MatrixVoice


@dataclass(frozen=True, slots=True)
class ChromeStyle:
    """The annotation chrome's tunable proportions — the re-skin surface.

    Built once per solve from the engine ``annotate:`` block (box/dot/swatch
    scalars) and the paradigm text-metric ratios (ascent/descent, shared with
    the card sizer). Every ``place_*`` reads from here so a genome re-skin
    changes annotation proportions in YAML, never in this module's math."""

    ascent: float
    descent: float
    line_pad: float
    box_pad_x: float
    box_pad_y: float
    callout_lead: float
    callout_max_w: float
    leader_gap: float
    standoff: float
    swatch_r: float
    legend_gap: float
    legend_row_h: float
    badge_pad_y: float
    legend_stub_len: float

    @classmethod
    def from_engine(cls, engine: Mapping[str, Any], cfg: Any) -> ChromeStyle:
        """Assemble from the ``annotate:`` block + ``connector.leader_gap`` +
        the paradigm's ``text_ascent_ratio``/``text_descent_ratio`` (the same
        metrics the card sizer measures with, so a shared re-skin stays
        coherent)."""
        a = engine.get("annotate") or {}
        conn = engine.get("connector") or {}
        return cls(
            ascent=float(cfg.text_ascent_ratio),
            descent=float(cfg.text_descent_ratio),
            line_pad=float(a.get("line_pad", 2.5)),
            box_pad_x=float(a.get("box_pad_x", 6)),
            box_pad_y=float(a.get("box_pad_y", 4)),
            callout_lead=float(a.get("callout_lead", 8)),
            callout_max_w=float(a.get("callout_max_w", 150)),
            leader_gap=float(conn.get("leader_gap", 10)),
            standoff=float(a.get("freetext_standoff", 16)),
            swatch_r=float(a.get("legend_swatch_r", 4)),
            legend_gap=float(a.get("legend_gap", 6)),
            legend_row_h=float(a.get("legend_row_h", 16)),
            badge_pad_y=float(a.get("badge_pad_y", 4)),
            legend_stub_len=float(a.get("legend_stub_len", 12)),
        )


def ascent_of(voice: MatrixVoice, style: ChromeStyle) -> float:
    """The ascent (baseline-to-top) of one line in ``voice`` — the offset from
    a text-block's top edge down to the first baseline."""
    return voice.size * style.ascent


def line_box_h(voice: MatrixVoice, style: ChromeStyle) -> float:
    """The height of one text line in ``voice`` (ascent + descent)."""
    return voice.size * (style.ascent + style.descent)


def block_h(n_lines: int, voice: MatrixVoice, style: ChromeStyle) -> float:
    """The height a wrapped block of ``n_lines`` occupies."""
    if n_lines <= 0:
        return 0.0
    return line_box_h(voice, style) + (n_lines - 1) * (voice.size + style.line_pad)


def text_w(lines: tuple[str, ...], voice: MatrixVoice) -> float:
    """The widest line's measured width."""
    return max((measure_voice(line, voice) for line in lines), default=0.0)


def wrap(text: str, max_w: float, voice: MatrixVoice, *, max_lines: int) -> tuple[str, ...]:
    return tuple(wrap_text_lines(text, max_w, voice, max_lines=max_lines))


def stack_runs(
    lines: tuple[str, ...],
    *,
    x: float,
    top_y: float,
    voice: MatrixVoice,
    cls: str,
    anchor: str,
    style: ChromeStyle,
) -> tuple[DiagramText, ...]:
    """Lay wrapped ``lines`` as text runs from ``top_y`` (the first baseline
    sits one ascent below ``top_y``), sharing ``x`` and ``anchor``."""
    ascent = voice.size * style.ascent
    pitch = voice.size + style.line_pad
    return tuple(
        DiagramText(x=x, y=top_y + ascent + k * pitch, text=line, cls=cls, anchor=anchor)
        for k, line in enumerate(lines)
    )


_SWATCH_PATH_BUILDERS = {"diamond": diamond_d, "square": square_d, "line": line_stub_d, "line-dashed": line_stub_d}
"""Non-circle swatch shapes with a precomputed drawn-geometry builder; disc/
ring stay a plain ``<circle>`` (see ``LegendEntry.swatch_path``). Shared by
row and column legend layout so the shape vocabulary never forks. line and
line-dashed share ONE builder (line_stub_d) — the dash is a template-side
stroke-dasharray on the identical ``d``, never a different geometry."""

_LINE_SHAPES = frozenset({"line", "line-dashed"})


def _swatch_extent(ann: DiagramAnnotation, style: ChromeStyle) -> float:
    """The swatch builder's sizing param: a RADIUS for every dot/mark shape,
    a HALF-LENGTH (``legend_stub_len``, dep-audit's own 12px citation) for
    the wire-stub shapes — same positional slot, shape-native meaning."""
    return style.legend_stub_len / 2 if ann.shape in _LINE_SHAPES else style.swatch_r


def place_legend(
    anns: list[DiagramAnnotation], region: RectSpec, cfg: Any, style: ChromeStyle, *, column: bool = False
) -> AnnotationPlacement:
    """Legend entries laid left-to-right in a region (row mode, the default),
    or stacked top-to-bottom as a right-anchored column (``column=True`` —
    the masthead corner key: dep-audit's cited hand file, tr2-leg, a 4-row
    status+relation key at x1002, y 94/116/138/160). Each entry = a swatch
    circle (accent slot) + its label in ``key`` voice. An accentless entry
    renders as a tracked-caps header (no swatch). Row mode's
    ``placement='right'`` hint right-aligns the whole row within the region;
    column mode is unconditionally right-anchored (the masthead idiom)."""
    if column:
        return _place_legend_column(anns, region, cfg, style)
    voice = voice_for(cfg, "key")
    gap = style.legend_gap

    def entry_w(ann: DiagramAnnotation) -> float:
        tw = measure_voice(ann.text, voice)
        accent = -1 if ann.accent is None else ann.accent
        has_swatch = accent >= 0 or bool(ann.shape) or bool(ann.health)
        return (2 * _swatch_extent(ann, style) + gap + tw + gap * 2) if has_swatch else (tw + gap * 2)

    entries: list[LegendEntry] = []
    x = region.x + style.box_pad_x
    if any(a.placement == "right" for a in anns):
        x = region.x + region.w - style.box_pad_x - sum(entry_w(a) for a in anns)
    row_left = x
    cy = region.y + region.h / 2
    ascent = voice.size * style.ascent
    for ann in anns:
        accent = -1 if ann.accent is None else ann.accent
        tw = measure_voice(ann.text, voice)
        # A swatch renders for an accent-bound entry (the pre-existing
        # colored-circle legend), a lanes morphology entry (ann.shape set,
        # obi-engine' category-by-SHAPE idiom — INK-toned, never hue, even
        # though it carries no accent slot), or a health-state entry
        # (ann.health set — the dep-audit vulnerable/outdated key, state-
        # palette colored, never a flow accent).
        if accent >= 0 or ann.shape or ann.health:
            ext = _swatch_extent(ann, style)
            sx = x + ext
            text = DiagramText(x=sx + ext + gap, y=cy + ascent / 2, text=ann.text, cls="key", anchor="start")
            # diamond/square/line(-dashed) precompute their drawn geometry;
            # disc/ring stay a plain circle (the template branches on shape,
            # ring drawing an open stroke; '' keeps the legacy accent-colored
            # circle, and a health swatch always draws a plain filled disc).
            swatch_path = _SWATCH_PATH_BUILDERS[ann.shape](sx, cy, ext) if ann.shape in _SWATCH_PATH_BUILDERS else ""
            entries.append(
                LegendEntry(
                    swatch_x=sx,
                    swatch_y=cy,
                    swatch_r=ext,
                    accent_index=accent,
                    text=text,
                    swatch_shape=ann.shape,
                    swatch_path=swatch_path,
                    health=ann.health,
                )
            )
            x = sx + ext + gap + tw + gap * 2
        else:
            text = DiagramText(x=x, y=cy + ascent / 2, text=ann.text, cls="key", anchor="start")
            entries.append(LegendEntry(swatch_x=0.0, swatch_y=0.0, swatch_r=0.0, accent_index=-1, text=text))
            x = x + tw + gap * 2
    box = RectSpec(x=row_left, y=cy - style.legend_row_h / 2, w=x - row_left, h=style.legend_row_h)
    return AnnotationPlacement(kind="legend", entries=tuple(entries), box=box, accent_index=-1)


def _place_legend_column(
    anns: list[DiagramAnnotation], region: RectSpec, cfg: Any, style: ChromeStyle
) -> AnnotationPlacement:
    """The masthead corner key: entries stack top-to-bottom instead of
    left-to-right — the compact key a status+relation legend earns once it
    outgrows a single row. Right-anchored by default (tr2-leg, dep-audit's
    cited hand file), or LEFT-anchored, flush under the kicker's own margin,
    when the group carries a ``placement: left`` hint (dep-audit-radial's
    cited hand file — its four-row key sits at the kicker's own x, not the
    opposite corner; a sibling composition earns the opposite side, not a
    universal rule).

    Row pitch is ``legend_row_h + legend_gap`` (16 + 6 == tr2-leg's measured
    22px row pitch) — the existing row-chrome scalars compose into the
    column rhythm; no new constant. Every row reserves the SAME swatch
    gutter, even an accentless one, so the text column reads as one aligned
    edge (tr2-leg's four rows all start their label at x1002, whatever their
    own swatch) rather than a ragged left edge where bare rows crowd the
    accented ones. The provisional box this returns is relocated verbatim by
    ``finish_layout``'s masthead placement (``shift_placement`` — a uniform
    translation), so only the RELATIVE row geometry here needs to be right;
    the final canvas position is stamped there."""
    voice = voice_for(cfg, "key")
    gap = style.legend_gap
    pitch = style.legend_row_h + gap
    ascent = voice.size * style.ascent
    has_swatch = any(a.accent is not None or a.shape or a.health for a in anns)
    # Every row's swatch CENTERS on the same x regardless of its own extent
    # (tr2-leg: the r=5 status dots and the half-len=6 wire stubs share one
    # cx=66) — the gutter (and every row's sx) sizes off the WIDEST swatch
    # so a mixed dot/stub key still reads as one aligned text edge.
    max_ext = max((_swatch_extent(a, style) for a in anns), default=style.swatch_r)
    gutter = (2 * max_ext + gap) if has_swatch else 0.0
    col_w = max((gutter + measure_voice(a.text, voice) for a in anns), default=0.0)
    anchor_left = any(a.placement == "left" for a in anns)
    left = region.x + style.box_pad_x if anchor_left else region.x + region.w - style.box_pad_x - col_w
    top = region.y + style.box_pad_y
    entries: list[LegendEntry] = []
    for i, ann in enumerate(anns):
        cy = top + i * pitch + style.legend_row_h / 2
        accent = -1 if ann.accent is None else ann.accent
        text = DiagramText(x=left + gutter, y=cy + ascent / 2, text=ann.text, cls="key", anchor="start")
        if accent >= 0 or ann.shape or ann.health:
            ext = _swatch_extent(ann, style)
            sx = left + max_ext
            swatch_path = _SWATCH_PATH_BUILDERS[ann.shape](sx, cy, ext) if ann.shape in _SWATCH_PATH_BUILDERS else ""
            entries.append(
                LegendEntry(
                    swatch_x=sx,
                    swatch_y=cy,
                    swatch_r=ext,
                    accent_index=accent,
                    text=text,
                    swatch_shape=ann.shape,
                    swatch_path=swatch_path,
                    health=ann.health,
                )
            )
        else:
            entries.append(LegendEntry(swatch_x=0.0, swatch_y=0.0, swatch_r=0.0, accent_index=-1, text=text))
    h = (len(anns) - 1) * pitch + style.legend_row_h if anns else 0.0
    box = RectSpec(x=left, y=top, w=col_w, h=h)
    anchor = "left" if anchor_left else ""
    return AnnotationPlacement(kind="legend", entries=tuple(entries), box=box, accent_index=-1, anchor=anchor)
