"""Matrix layout solver — measured columns, stacked rows, frozen output.

``compute_matrix_layout`` is the only entry point: it takes a
POST-inference :class:`MatrixSpec` (every column kind concrete) and emits a
fully-resolved :class:`MatrixLayout`. All cross-cell statistics live here —
column width solving, row-height policy, heat normalization, axis maxima —
while per-cell geometry is delegated to ``matrix_cells``.

Width adapts to content: the paradigm ``width`` is a CEILING (900, the
porcelain specimens' size) and ``min_width`` the floor — the solved frame
is ``clamp(label + natural columns + margins, floor, ceiling)``, with bar
matrices pinned to the ceiling and the masthead text flooring the width so
titles never clip. Height is content-solved, mirroring the stats card.
Capacity is enforced up front: past the soft caps the type/pitch tightens
one step; past the hard caps :class:`MatrixCapacityError` is raised —
compose never silently truncates a table.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from hyperweave.compose.matrix_cells import (
    build_cell,
    chip_line_width,
    chip_rows_needed,
    content_width,
    display_value,
    format_value_with_unit,
    glyph_mark_placement,
    is_numeric_value,
    measure_voice,
    text_lines_needed,
    truncate_to_width,
)
from hyperweave.compose.matrix_records import (
    AxisSpec,
    CellPlacement,
    ColHeader,
    FooterBlock,
    HeaderBlock,
    MatrixLayout,
    SectionBand,
    SummaryBlock,
    TierSpan,
)
from hyperweave.compose.spatial_records import LineSpec, RectSpec, TextSpec
from hyperweave.core.matrix import (
    Align,
    CellKind,
    CellState,
    ColRole,
    GlyphTint,
    MatrixCapacityError,
    MatrixCell,
    MatrixColumn,
    MatrixInputError,
    MatrixRow,
    MatrixSpec,
    Polarity,
    RowHeight,
    is_chain,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hyperweave.core.paradigm import MatrixVoice, ParadigmMatrixConfig

_FLEX_KINDS = (CellKind.BAR, CellKind.CHIP)


def enforce_caps(spec: MatrixSpec, caps: Mapping[str, Any]) -> bool:
    """Hard caps raise; soft caps return True (apply the shrink step)."""
    n_rows = len(spec.rows)
    n_cols = sum(1 for c in spec.columns if c.role is not ColRole.LABEL)
    hard_rows = int(caps.get("hard_rows", 30))
    hard_cols = int(caps.get("hard_cols", 12))
    if n_rows > hard_rows or n_cols > hard_cols:
        raise MatrixCapacityError(
            f"matrix exceeds the hard cap ({n_rows}x{n_cols} vs {hard_rows}x{hard_cols} rows x data columns); "
            "paginate the adapter"
        )
    return n_rows > int(caps.get("soft_rows", 16)) or n_cols > int(caps.get("soft_cols", 8))


def compute_matrix_layout(
    spec: MatrixSpec,
    *,
    matrix: ParadigmMatrixConfig,
    config: Mapping[str, Any],
    glyph_registry: Mapping[str, Any],
) -> MatrixLayout:
    """Solve the full matrix geometry. ``spec`` must be post-inference."""
    cfg = matrix
    geometry: Mapping[str, Any] = config.get("cell_geometry") or {}
    palette: Mapping[str, Any] = config.get("semantic_palette") or {}
    shrink = enforce_caps(spec, config.get("caps") or {})

    data_cols: list[MatrixColumn] = [c for c in spec.columns if c.role is not ColRole.LABEL]
    for column in data_cols:
        if column.kind is CellKind.AUTO:
            raise MatrixInputError(f"column {column.id!r} reached the layout solver with kind=auto (run inference)")
    cells_by_col: list[list[MatrixCell]] = [[row.cells[j] for row in spec.rows] for j in range(len(data_cols))]

    ceiling = cfg.width
    margin = cfg.margin_x
    ceiling_avail = ceiling - 2 * margin

    # ── Label column ────────────────────────────────────────────────────
    glyph_size = float((geometry.get("glyph") or {}).get("size", 22))
    has_row_glyph = any(row.glyph for row in spec.rows)
    glyph_indent = (glyph_size + 10.0) if has_row_glyph else 0.0
    # Section members indent under their header (the tiers-prototype
    # hierarchy: header on the band, grouped fields stepped in below it).
    section_indent = cfg.section_indent if spec.sections else 0.0
    label_header = next((c.label for c in spec.columns if c.role is ColRole.LABEL), "")
    # Sectioned rows are sub-fields and speak the quieter label voice
    # (tiers specimen: mono 600/11 under the section header) — flat rows
    # keep the primary row-title voice. Width measures with the same
    # voice the cells render with.
    label_voice = cfg.row_label_sub_voice if spec.sections else cfg.row_label_voice
    label_text_w = max(
        [measure_voice(row.label, label_voice) for row in spec.rows]
        + [measure_voice(row.sublabel, cfg.row_sub_voice) for row in spec.rows]
        + [measure_voice(label_header, cfg.colhead_voice)]
    )
    label_w = min(
        max(glyph_indent + section_indent + label_text_w + 2 * cfg.cell_pad_x, cfg.label_col_min),
        ceiling_avail * cfg.label_col_max_ratio,
    )

    # ── Natural column widths (one source for sizing AND solving) ───────
    # Per column: max(header, data content, SUMMARY content) — the summary
    # row occupies the same columns, so "agent corpora" under a 9px dot
    # column widens the column, never crams.
    hero_j = _hero_index(spec, data_cols)
    naturals, floors = _natural_widths(spec, data_cols, cells_by_col, hero_j=hero_j, cfg=cfg, geometry=geometry)

    # ── Adaptive frame width ─────────────────────────────────────────────
    # The frame fits its content: cfg.width is a CEILING, not a constant.
    # A bar matrix pins to the ceiling (the shared magnitude axis wants
    # room); everything else solves to label + natural column widths,
    # floored by min_width and by the masthead text so titles never clip.
    has_bar = any(c.kind is CellKind.BAR for c in data_cols)
    has_subtitle = bool(spec.subtitle)
    has_masthead = bool(spec.title or spec.subtitle or spec.headline is not None)
    chain = is_chain(spec)
    masthead_right_w = _masthead_right_width(spec, data_cols, cfg=cfg, chain=chain) if has_masthead else 0.0
    has_legend = has_masthead and spec.headline is None and masthead_right_w > 0.0
    title_voice = cfg.title_voice
    title_w = measure_voice(spec.title.upper(), title_voice) if spec.title else 0.0
    subtitle_w = measure_voice(spec.subtitle, cfg.desc_voice) if spec.subtitle else 0.0

    # The legend rides the subtitle's descriptor line whenever the shared
    # band can exist at all — identity left, key right, one masthead band
    # (the specimen gestalt; the masthead floor widens the frame to fit).
    # Only a pair that cannot share even at the ceiling drops the legend
    # to its own line below the subtitle.
    inline_need = 2 * margin + subtitle_w + masthead_right_w + 24.0
    legend_inline = has_legend and has_subtitle and inline_need <= ceiling
    legend_line = has_legend and not legend_inline

    def _masthead_floor(t_w: float) -> float:
        """Masthead width floor for the resolved line composition.

        The headline chip always shares the TITLE line; an inline legend
        shares the subtitle's descriptor line; a legend on its own line
        floors at its own occupancy.
        """
        if not has_masthead:
            return 0.0
        line1 = t_w + (masthead_right_w + 24.0 if spec.headline is not None else 0.0)
        line2 = subtitle_w + (masthead_right_w + 24.0 if legend_inline else 0.0)
        own = masthead_right_w if legend_line else 0.0
        return 2 * margin + max(line1, line2, own)

    if has_bar:
        width = ceiling
    else:
        sizing_total = 0.0
        for j, column in enumerate(data_cols):
            if column.kind is CellKind.CHIP and column.width is None:
                # For the width DECISION a chip column asks for its longest
                # one-line packing (clamped by the ceiling downstream).
                one_line = max(
                    (chip_line_width(cell.chips, cfg=cfg, geometry=geometry) for cell in cells_by_col[j]),
                    default=0.0,
                )
                sizing_total += max(one_line + 2 * cfg.cell_pad_x, naturals[j])
            else:
                sizing_total += naturals[j]
        content_w = 2 * margin + label_w + sizing_total
        # The footer line is shared: notes left, brand right.
        footer_w = 0.0
        if spec.notes:
            footer_w = (
                2 * margin
                + measure_voice(spec.notes, cfg.foot_voice)
                + measure_voice("hyperweave", cfg.foot_voice) * 1.25
                + 24.0
            )
        # ceil, not round: rounding DOWN would under-fund the solver by up
        # to half a pixel, shaving column floors the naturals already paid
        # for (summary runs would measure past their solved column).
        masthead_w = _masthead_floor(title_w)
        width = min(math.ceil(max(content_w, masthead_w, footer_w, float(cfg.min_width))), ceiling)
        if width < cfg.compact_below:
            # Compact frame: the title voice steps down so the masthead
            # stays proportionate to the table. The width re-solves with
            # the smaller title floor (shrink-only — the decision never
            # flips back; the legend keeps its resolved line).
            title_voice = title_voice.model_copy(update={"size": cfg.title_compact_size})
            title_w = measure_voice(spec.title.upper(), title_voice) if spec.title else 0.0
            masthead_w = _masthead_floor(title_w)
            width = min(math.ceil(max(content_w, masthead_w, footer_w, float(cfg.min_width))), ceiling)
    avail = width - 2 * margin

    # ── Data column widths ─────────────────────────────────────────────
    col_w = _solve_column_widths(data_cols, naturals=naturals, floors=floors, rest=avail - label_w)
    col_x: list[float] = []
    cursor = margin + label_w
    for w in col_w:
        col_x.append(cursor)
        cursor += w

    # ── Row heights ─────────────────────────────────────────────────────
    # Sectioned rows are dense sub-fields and take the compact pitch (the
    # tiers specimen's 34px rhythm); flat rows keep the primary pitch.
    pitch = cfg.row_pitch_compact if (shrink or spec.sections) else cfg.row_pitch
    chip_geo = geometry.get("chip") or {}
    chip_pitch = float(chip_geo.get("row_pitch", 24))
    text_geo = geometry.get("text") or {}
    text_pitch = float(text_geo.get("line_pitch", 16))
    text_max_lines = int(text_geo.get("max_lines", 3))

    def _text_overflow_lines(row: MatrixRow, j: int) -> int:
        voice = cfg.cell_strong_voice if row.emphasis else cfg.cell_voice
        return text_lines_needed(
            display_value(row.cells[j].value), col_w[j] - 2 * cfg.cell_pad_x, voice, max_lines=text_max_lines
        )

    mode = spec.row_height
    chip_wraps = any(
        column.kind is CellKind.CHIP
        and any(
            chip_line_width(cell.chips, cfg=cfg, geometry=geometry) > col_w[j] - 2 * cfg.cell_pad_x
            for cell in cells_by_col[j]
        )
        for j, column in enumerate(data_cols)
    )
    text_wraps = any(
        column.kind is CellKind.TEXT and any(_text_overflow_lines(row, j) > 1 for row in spec.rows)
        for j, column in enumerate(data_cols)
    )
    if chip_wraps or text_wraps:
        # Chip and text columns ALWAYS grow rows to fit — packed lists and
        # wrapped runs are the standard rendering; truncation/overflow caps
        # are for the extreme case (past max_chip_rows / max_lines). A
        # declared UNIFORM never strangles content to one line.
        mode = RowHeight.CONTENT
    elif mode is RowHeight.AUTO:
        mode = RowHeight.UNIFORM
    content_mode = mode is RowHeight.CONTENT

    row_h: list[float] = []
    for row in spec.rows:
        if not content_mode:
            row_h.append(pitch)
            continue
        h = cfg.content_row_base
        for j, column in enumerate(data_cols):
            if column.kind is CellKind.CHIP:
                lines = chip_rows_needed(row.cells[j].chips, col_w[j] - 2 * cfg.cell_pad_x, cfg=cfg, geometry=geometry)
                h = max(h, (lines - 1) * chip_pitch + float(chip_geo.get("height", 17)) + 24.0)
            elif column.kind is CellKind.TEXT:
                lines = _text_overflow_lines(row, j)
                extra = cfg.row_sub_voice.size + 6.0 if (lines > 1 and row.cells[j].note) else 0.0
                h = max(h, (lines - 1) * text_pitch + cfg.row_pitch + extra)
        row_h.append(h)

    # ── Vertical stacking (section bands interleaved) ───────────────────
    # Sublabels add a second header line; grow the colheader block so the
    # label line clears the hero cap tab instead of colliding with it.
    has_sublabels = any(c.sublabel for c in data_cols)
    colheader_h = cfg.colheader_h + (cfg.colhead_sub_voice.size + 4.0 if has_sublabels else 0.0)
    # An empty masthead collapses: no title/subtitle/headline → the zone
    # releases its space and the rail/scan/legend are suppressed. Empty
    # slots never reserve geometry (the stats-card slot-removal principle).
    # The masthead is a tight text stack at desc_line_h pitch: title,
    # subtitle, legend — each line present only when occupied, the rail 16
    # below the last baseline. A missing subtitle releases its line (the
    # legend inherits the slot when it needs one); a legend line below the
    # subtitle grows the zone by exactly one line pitch.
    masthead_h = cfg.masthead_h if has_masthead else cfg.masthead_collapsed_h
    if has_masthead and not has_subtitle and not legend_line:
        masthead_h -= cfg.desc_line_h
    if legend_line and has_subtitle:
        masthead_h += cfg.desc_line_h
    # The descriptor baseline hangs one line pitch under the title's.
    legend_baseline = 54.0 + cfg.desc_line_h  # the descriptor line (shared or inherited)
    if legend_line and has_subtitle:
        legend_baseline += cfg.desc_line_h  # one line below the subtitle's baseline
    rows_top = masthead_h + colheader_h
    section_bands: list[SectionBand] = []
    row_y: list[float] = []
    y = rows_top
    current_section = ""
    for i, row in enumerate(spec.rows):
        if spec.sections and row.section != current_section:
            current_section = row.section
            # Section bands are the one card-wide wash (specimen: x=8 to
            # width-8, flush square) — every hairline rule stays within
            # the content margins.
            band = RectSpec(8.0, y, width - 16.0, cfg.section_band_h)
            section_bands.append(
                SectionBand(
                    band=band,
                    label=TextSpec(
                        x=margin,
                        y=band.y + band.h / 2 + cfg.section_voice.size * 0.37,
                        anchor="start",
                        text=current_section,
                    ),
                    band_opacity=cfg.section_band_opacity,
                )
            )
            y += cfg.section_band_h
        row_y.append(y)
        y += row_h[i]
    rows_bottom = y

    summary_top = rows_bottom
    if spec.summary_row is not None:
        y += cfg.summary_h
    axis_top = y
    if has_bar:
        y += cfg.axis_h
    footer_top = y
    height = round(y + cfg.footer_h)

    # ── Column statistics (heat / axis fractions) ───────────────────────
    heat_t, axis_frac, value_zones = _column_statistics(spec, data_cols, cells_by_col, cfg=cfg)

    # ── Cells ────────────────────────────────────────────────────────────
    cells: list[CellPlacement] = []
    for i, row in enumerate(spec.rows):
        box = RectSpec(margin, row_y[i], label_w, row_h[i])
        cells.extend(
            _label_cells(
                row,
                i,
                box,
                glyph_tint=spec.row_glyph_tint,
                cfg=cfg,
                glyph_indent=glyph_indent,
                section_indent=section_indent if row.section else 0.0,
                glyph_size=glyph_size,
                glyph_registry=glyph_registry,
                label_voice=label_voice,
                label_cls="rowlabelsub" if spec.sections else "rowlabel",
            )
        )
        if chain:
            # Chain projection: per-column tier spans replace the dot grid
            # (built below) — no per-cell marks.
            continue
        for j, column in enumerate(data_cols):
            cell = row.cells[j]
            cells.append(
                build_cell(
                    kind=column.kind,
                    cell=cell,
                    column=column,
                    box=RectSpec(col_x[j], row_y[i], col_w[j], row_h[i]),
                    row=i,
                    col=j,
                    cfg=cfg,
                    geometry=geometry,
                    palette=palette,
                    emphasis=row.emphasis,
                    heat_t=heat_t.get((i, j)),
                    axis_frac=axis_frac.get((i, j)),
                    glyph_entry=_glyph_entry(cell.glyph, glyph_registry) if column.kind is CellKind.GLYPH else None,
                    value_zone_w=value_zones.get(j, 0.0),
                    content_mode=content_mode,
                )
            )

    # ── Summary row ──────────────────────────────────────────────────────
    # The score band is the table's coda and reads bigger than the body:
    # large mono values with their qualifiers tucked below, the hero
    # column's pair carried in the genome accent (the original's gestalt).
    summary: SummaryBlock | None = None
    if spec.summary_row is not None:
        rule_y = summary_top + 0.5
        value_y = summary_top + 28.0
        qual_y = value_y + 16.0
        summary = SummaryBlock(
            rule=LineSpec(margin, rule_y, margin + avail, rule_y),
            label=TextSpec(
                x=margin + cfg.cell_pad_x,
                y=value_y,
                anchor="start",
                text=spec.summary_label,
            )
            if spec.summary_label
            else None,
        )
        for j, s_cell in enumerate(spec.summary_row):
            hero = j == hero_j
            cx = col_x[j] + col_w[j] / 2
            # Scores read big; phrases read quiet (the tiers USE-FOR row's
            # m6/9 against the check score band's 14.5/16.5).
            cls = ("sumvalhero" if hero else "sumval") if is_numeric_value(s_cell.value) else "sumtext"
            cells.append(
                CellPlacement(
                    kind="text",
                    row=len(spec.rows),
                    col=j,
                    box=RectSpec(col_x[j], summary_top, col_w[j], cfg.summary_h),
                    emphasis=hero,
                    text=display_value(s_cell.value),
                    text_x=cx,
                    text_y=value_y,
                    text_anchor="middle",
                    cls=cls,
                    text_fill="var(--dna-signal)" if hero else "",
                    sub_text=s_cell.note,
                    sub_x=cx,
                    sub_y=qual_y,
                    sub_cls="sumqual",
                    sub_fill="var(--dna-signal)" if hero else "",
                )
            )

    # ── Chassis blocks ───────────────────────────────────────────────────
    header = _header_block(
        spec,
        cfg=cfg,
        geometry=geometry,
        palette=palette,
        data_cols=data_cols,
        has_masthead=has_masthead,
        width=width,
        masthead_h=masthead_h,
        legend_baseline=legend_baseline,
        chain=chain,
    )
    colheaders = _colheaders(
        spec,
        data_cols,
        col_x=col_x,
        col_w=col_w,
        label_header=label_header,
        cfg=cfg,
        margin=margin,
        base_y=rows_top - 12.0,
    )

    hero_band = hero_cap = None
    if hero_j is not None:
        lane_top = masthead_h + 6.0
        lane_bottom = rows_bottom
        if spec.summary_row is not None:
            # The lane runs THROUGH the score band — the hero column's
            # verdict sits inside its highlighted region instead of
            # floating below it (the g3 specimen: 9px past the last
            # summary baseline).
            lane_bottom = summary_top + 28.0 + (16.0 if spec.summary_row[hero_j].note else 0.0) + 9.0
        hero_band = RectSpec(col_x[hero_j] + 2.0, lane_top, col_w[hero_j] - 4.0, lane_bottom - lane_top, 10.0)
        tab_w = col_w[hero_j] * cfg.hero_tab_ratio
        hero_cap = RectSpec(
            col_x[hero_j] + (col_w[hero_j] - tab_w) / 2, lane_top, tab_w, cfg.hero_tab_h, cfg.hero_tab_h / 2
        )

    extent_bars = [
        RectSpec(
            col_x[j] + col_w[j] / 2 - 1.25,
            rows_top + 4.0,
            2.5,
            _last_filled_y(spec, j, row_y, row_h) - rows_top - 4.0,
            1.25,
        )
        for j, column in enumerate(data_cols)
        if not chain and column.kind is CellKind.DOT and _last_filled_y(spec, j, row_y, row_h) > rows_top + 4.0
    ]

    # Chain projection: one reach bar per tier from the table's top to its
    # last included row, closed by a terminal dot (the span IS the extent;
    # no per-cell marks, no separate extent bars).
    tier_spans: list[TierSpan] = []
    if chain:
        dot_geo = geometry.get("dot") or {}
        span_w = float(dot_geo.get("span_w", 7))
        for j in range(len(data_cols)):
            last_y = _last_filled_y(spec, j, row_y, row_h)
            if last_y == float("-inf"):
                continue
            cx = col_x[j] + col_w[j] / 2
            top = rows_top + 4.0
            tier_spans.append(
                TierSpan(
                    bar=RectSpec(cx - span_w / 2, top, span_w, last_y - top, span_w / 2),
                    dot_cx=cx,
                    dot_cy=last_y,
                    dot_r=float(dot_geo.get("terminal_r", 4.6)),
                )
            )

    axis = (
        _axis_block(
            spec, data_cols, cells_by_col, col_x=col_x, col_w=col_w, rows_top=rows_top, axis_top=axis_top, cfg=cfg
        )
        if has_bar
        else None
    )

    guides = (
        tuple(LineSpec(col_x[j], rows_top + 2.0, col_x[j], rows_bottom - 2.0) for j in range(1, len(data_cols)))
        if len(data_cols) >= 2 and not has_bar
        else ()
    )

    # Zebra stripes share the card-wide wash treatment with section bands
    # (specimen: x=8 to width-8, square corners).
    row_stripes = (
        tuple(RectSpec(8.0, row_y[i], width - 16.0, row_h[i]) for i in range(1, len(spec.rows), 2))
        if not content_mode and not spec.sections and hero_j is None and len(spec.rows) >= 5
        else ()
    )

    # Footer order per the porcelain specimens: the cobalt seam closes the
    # table FIRST, then the notes/brand line sits below it.
    seam_y = footer_top + 6.0
    footer_text_y = seam_y + 19.0
    footer = FooterBlock(
        seam=LineSpec(margin, seam_y, margin + avail, seam_y),
        notes=TextSpec(x=margin, y=footer_text_y, anchor="start", text=spec.notes) if spec.notes else None,
        brand=TextSpec(x=margin + avail, y=footer_text_y, anchor="end", text="hyperweave"),
    )

    colheader_rule_y = rows_top - 0.5
    texts_map: dict[str, TextSpec] = {}
    if header.title is not None:
        texts_map["masthead_title"] = header.title
    if header.subtitle is not None:
        texts_map["masthead_desc"] = header.subtitle
    lines_map: dict[str, LineSpec] = {
        "colheader_rule": LineSpec(margin, colheader_rule_y, margin + avail, colheader_rule_y),
    }
    if header.rule is not None:
        lines_map["masthead_rule"] = header.rule
    rects_map: dict[str, RectSpec] = {
        "outer": RectSpec(0.6, 0.6, width - 1.2, height - 1.2, cfg.card_radius),
    }
    if header.scan is not None:
        rects_map["scan"] = header.scan
    return MatrixLayout(
        width=width,
        height=height,
        col_x=tuple(col_x),
        col_w=tuple(col_w),
        row_y=tuple(row_y),
        row_h=tuple(row_h),
        header=header,
        colheaders=tuple(colheaders),
        section_bands=tuple(section_bands),
        cells=tuple(cells),
        hero_band=hero_band,
        hero_cap=hero_cap,
        hero_band_opacity=cfg.hero_lane_opacity,
        extent_bars=tuple(extent_bars),
        axis=axis,
        summary=summary,
        guides=guides,
        guide_opacity=cfg.guide_opacity,
        row_stripes=row_stripes,
        stripe_opacity=cfg.stripe_opacity,
        title_voice_size=title_voice.size,
        tier_spans=tuple(tier_spans),
        tier_span_opacity=float((geometry.get("dot") or {}).get("span_opacity", 0.28)),
        footer=footer,
        rects=rects_map,
        lines=lines_map,
        texts=texts_map,
    )


def _natural_widths(
    spec: MatrixSpec,
    data_cols: Sequence[MatrixColumn],
    cells_by_col: Sequence[Sequence[MatrixCell]],
    *,
    hero_j: int | None,
    cfg: ParadigmMatrixConfig,
    geometry: Mapping[str, Any],
) -> tuple[list[float], list[float]]:
    """Natural width + floor per column — the ONE source both the adaptive
    width decision and the column solver consume.

    Per column: ``max(header, data content, summary content)``, clamped to
    ``[kind floor, max_col]`` for content-sized kinds. The summary row
    occupies the same columns as the data, so its values and qualifiers
    widen structurally-narrow columns (a dot column holding "agent
    corpora" in its score band) instead of cramming.
    """
    naturals: list[float] = []
    floors: list[float] = []
    for j, column in enumerate(data_cols):
        floor = _kind_floor(column, geometry)
        header_w = (
            max(
                measure_voice(column.label, cfg.colhead_voice),
                measure_voice(column.sublabel, cfg.colhead_sub_voice),
            )
            + 2 * cfg.cell_pad_x
        )
        summary_w = 0.0
        if spec.summary_row is not None:
            s_cell = spec.summary_row[j]
            if not is_numeric_value(s_cell.value):
                voice = cfg.summary_text_voice
            elif j == hero_j:
                voice = cfg.summary_hero_voice
            else:
                voice = cfg.summary_value_voice
            summary_w = measure_voice(display_value(s_cell.value), voice)
            if s_cell.note:
                summary_w = max(summary_w, measure_voice(s_cell.note, cfg.summary_qual_voice))
            summary_w += 2 * cfg.cell_pad_x
        if column.width is not None:
            w = float(column.width)
        elif column.kind in _FLEX_KINDS:
            # Flexible kinds absorb the remainder; their natural is the
            # kind floor raised by any summary occupancy.
            w = max(floor, summary_w)
        else:
            w = max(
                content_width(column.kind, cells_by_col[j], column, cfg=cfg, geometry=geometry),
                header_w,
                summary_w,
            )
            w = min(max(w, floor), cfg.max_col)
        naturals.append(w)
        floors.append(min(floor, w))
    return naturals, floors


def _solve_column_widths(
    data_cols: Sequence[MatrixColumn],
    *,
    naturals: Sequence[float],
    floors: Sequence[float],
    rest: float,
) -> list[float]:
    """Distribute ``rest`` across the columns so that Σ == ``rest`` exactly.

    Flexible kinds (bar, chip) absorb the remainder. With no flexible
    column, leftover distributes toward equal column widths (the
    check-specimen look); deficits shrink columns proportionally down to
    their floors.
    """
    n = len(data_cols)
    flex = [j for j, c in enumerate(data_cols) if c.kind in _FLEX_KINDS and c.width is None]
    widths = list(naturals)
    if flex:
        fixed_sum = sum(widths[j] for j in range(n) if j not in flex)
        share = (rest - fixed_sum) / len(flex)
        for j in flex:
            widths[j] = max(widths[j], share)
    else:
        total = sum(widths)
        if total < rest:
            # Grow toward equal widths: raise narrow columns first.
            target = rest / n
            grow = [j for j in range(n) if widths[j] < target and data_cols[j].width is None]
            if grow:
                extra = rest - total
                room = sum(target - widths[j] for j in grow)
                for j in grow:
                    widths[j] += extra * ((target - widths[j]) / room) if room else 0.0

    # Normalize a deficit: spend slack above the kind floors proportionally;
    # if the floors themselves don't fit, feasibility beats legibility —
    # scale every column to the same fraction of its floor. Both paths keep
    # every width strictly positive (a negative width would march columns
    # backward over the label zone).
    total = sum(widths)
    if total > rest:
        slack = [widths[j] - floors[j] for j in range(n)]
        slack_sum = sum(slack)
        over = total - rest
        if slack_sum >= over and slack_sum > 0:
            for j in range(n):
                widths[j] -= over * (slack[j] / slack_sum)
        else:
            floor_sum = sum(floors)
            scale = rest / floor_sum if floor_sum > 0 else 0.0
            widths = [floors[j] * scale for j in range(n)]
    # Pin Σ == rest exactly: absorb float residue in the widest column,
    # never letting it dip below half its solved width.
    residue = rest - sum(widths)
    if widths:
        widest = max(range(n), key=lambda j: widths[j])
        widths[widest] = max(widths[widest] / 2, widths[widest] + residue)
    return widths


def _kind_floor(column: MatrixColumn, geometry: Mapping[str, Any]) -> float:
    """Width floor for a column, polarity-aware for numeric.

    The numeric ``min_col`` (110) is sized for the fixed heat TILE; a
    polarity-less numeric column renders plain right-aligned text and only
    needs the text floor — using the tile floor there makes an 8-column
    plain-numeric table infeasible at 900 wide.
    """
    if column.kind is CellKind.NUMERIC and column.polarity is Polarity.NONE:
        geo = geometry.get("text") or {}
        return float(geo.get("min_col", 64))
    geo = geometry.get(column.kind.value) or {}
    return float(geo.get("min_col", 64))


def _column_statistics(
    spec: MatrixSpec,
    data_cols: Sequence[MatrixColumn],
    cells_by_col: Sequence[Sequence[MatrixCell]],
    *,
    cfg: ParadigmMatrixConfig,
) -> tuple[dict[tuple[int, int], float], dict[tuple[int, int], float], dict[int, float]]:
    """Per-cell heat ``t`` and axis fractions; per-column bar value zones."""
    heat_t: dict[tuple[int, int], float] = {}
    axis_frac: dict[tuple[int, int], float] = {}
    value_zones: dict[int, float] = {}
    for j, column in enumerate(data_cols):
        if column.kind not in (CellKind.NUMERIC, CellKind.BAR):
            continue
        numbers: dict[int, float] = {}
        for i, cell in enumerate(cells_by_col[j]):
            v = cell.value
            if isinstance(v, bool) or v is None or v == "":
                continue
            try:
                numbers[i] = float(v)
            except (TypeError, ValueError):
                continue
        if not numbers:
            continue
        vmax = max(numbers.values())
        vmin = min(numbers.values())
        if column.kind is CellKind.BAR:
            # Bars gauge ABSOLUTE magnitude against the shared axis.
            axis_max = spec.axis_max if spec.axis_max else (vmax if vmax > 0 else 1.0)
            for i, v in numbers.items():
                axis_frac[(i, j)] = min(1.0, max(0.0, v / axis_max)) if axis_max else 0.0
        else:
            # Heat underlines gauge WITHIN-RANGE magnitude so differences
            # read: the column max runs nearly full, the min keeps a stub
            # (a 96.2 is almost full, an 84.1 noticeably shorter).
            for i, v in numbers.items():
                t_range = 1.0 if vmax == vmin else (v - vmin) / (vmax - vmin)
                axis_frac[(i, j)] = 0.12 + 0.88 * t_range
        if column.kind is CellKind.NUMERIC and column.polarity is not Polarity.NONE:
            for i, v in numbers.items():
                t = 0.5 if vmax == vmin else (v - vmin) / (vmax - vmin)
                heat_t[(i, j)] = (1.0 - t) if column.polarity is Polarity.LOWER else t
        if column.kind is CellKind.BAR:
            unit = column.unit
            prefix_unit = unit in ("$", "€", "£", "¥")
            value_zones[j] = max(
                measure_voice(
                    format_value_with_unit(display_value(cells_by_col[j][i].value), unit)
                    if prefix_unit
                    else display_value(cells_by_col[j][i].value),
                    cfg.cell_strong_voice,
                )
                + (measure_voice(unit, cfg.axis_voice) + 4.0 if unit and not prefix_unit else 0.0)
                for i in numbers
            )
    return heat_t, axis_frac, value_zones


def _label_cells(
    row: MatrixRow,
    i: int,
    box: RectSpec,
    *,
    cfg: ParadigmMatrixConfig,
    glyph_tint: GlyphTint,
    glyph_indent: float,
    section_indent: float,
    glyph_size: float,
    glyph_registry: Mapping[str, Any],
    label_voice: MatrixVoice,
    label_cls: str,
) -> list[CellPlacement]:
    """Row identity: optional glyph mark + label (+ sublabel) stack.

    ``section_indent`` steps section-member rows in under their header band
    (the tiers-prototype hierarchy); rows outside sections pass 0.
    ``label_voice``/``label_cls`` carry the caller's register: primary
    row titles for flat tables, the quiet sub-field voice under sections.
    """
    placements: list[CellPlacement] = []
    text_x = box.x + cfg.cell_pad_x + glyph_indent + section_indent
    cy = box.y + box.h / 2
    max_w = box.w - 2 * cfg.cell_pad_x - glyph_indent - section_indent
    if row.glyph:
        entry = _glyph_entry(row.glyph, glyph_registry)
        glyph_x = box.x + cfg.cell_pad_x + section_indent
        placements.append(
            glyph_mark_placement(
                entry,
                glyph_id=row.glyph,
                kind_row=i,
                col=-1,
                box=RectSpec(glyph_x, cy - glyph_size / 2, glyph_size, glyph_size),
                cx=glyph_x + glyph_size / 2,
                cy=cy,
                size=glyph_size,
                tint=glyph_tint,
            )
        )
    if row.sublabel:
        placements.append(
            CellPlacement(
                kind="text",
                row=i,
                col=-1,
                box=box,
                emphasis=row.emphasis,
                text=truncate_to_width(row.label, max_w, label_voice),
                text_x=text_x,
                text_y=cy - 1.0,
                text_anchor="start",
                cls=label_cls,
                sub_text=truncate_to_width(row.sublabel, max_w, cfg.row_sub_voice),
                sub_x=text_x,
                sub_y=cy + cfg.row_sub_voice.size + 1.0,
                sub_cls="rowsub",
            )
        )
    else:
        placements.append(
            CellPlacement(
                kind="text",
                row=i,
                col=-1,
                box=box,
                emphasis=row.emphasis,
                text=truncate_to_width(row.label, max_w, label_voice),
                text_x=text_x,
                text_y=cy + label_voice.size * 0.35,
                text_anchor="start",
                cls=label_cls,
            )
        )
    return placements


def _glyph_entry(glyph_id: str, glyph_registry: Mapping[str, Any]) -> Mapping[str, Any]:
    entry = glyph_registry.get(glyph_id)
    if not isinstance(entry, Mapping):
        raise MatrixInputError(
            f"unknown glyph id {glyph_id!r} — matrix glyph cells accept data/glyphs.json registry ids only"
        )
    return entry


def _hero_index(spec: MatrixSpec, data_cols: Sequence[MatrixColumn]) -> int | None:
    if spec.hero_column is None:
        return None
    for j, column in enumerate(data_cols):
        if column.id == spec.hero_column:
            return j
    return None


def _last_filled_y(spec: MatrixSpec, j: int, row_y: Sequence[float], row_h: Sequence[float]) -> float:
    last = -1
    for i, row in enumerate(spec.rows):
        state = row.cells[j].state
        if state in (CellState.FULL, CellState.ON, CellState.PARTIAL):
            last = i
    if last < 0:
        return float("-inf")
    return row_y[last] + row_h[last] / 2


def _masthead_right_width(
    spec: MatrixSpec, data_cols: Sequence[MatrixColumn], *, cfg: ParadigmMatrixConfig, chain: bool
) -> float:
    """Width the descriptor line's right occupant needs (headline chip or
    indicator legend), mirroring the builders' own spacing math."""
    if spec.headline is not None:
        value_w = measure_voice(spec.headline.value, cfg.headline_voice)
        label_w = measure_voice(spec.headline.label, cfg.desc_voice) if spec.headline.label else 0.0
        return value_w + label_w + (10.0 if spec.headline.label else 0.0) + 24.0
    kinds = {c.kind for c in data_cols}
    labels: tuple[str, ...]
    if chain:
        labels = ("tier reach",)
    elif CellKind.CHECK in kinds:
        labels = ("full", "partial", "none")
    elif CellKind.DOT in kinds:
        labels = ("included", "omitted")
    else:
        return 0.0
    # Per legend entry the builder consumes label width + 34px of mark/gap.
    return sum(measure_voice(label, cfg.desc_voice) + 34.0 for label in labels)


def _header_block(
    spec: MatrixSpec,
    *,
    cfg: ParadigmMatrixConfig,
    geometry: Mapping[str, Any],
    palette: Mapping[str, Any],
    data_cols: Sequence[MatrixColumn],
    has_masthead: bool,
    width: int,
    masthead_h: float,
    legend_baseline: float,
    chain: bool,
) -> HeaderBlock:
    margin = cfg.margin_x
    avail = width - 2 * margin
    if not has_masthead:
        # Collapsed masthead: the table simply starts. No rail, no scan,
        # no legend — the colheader rule provides the top edge.
        return HeaderBlock(title=None, subtitle=None, rule=None, scan=None)
    # Title and subtitle keep their lines; the rule and scan rail ride the
    # masthead's bottom edge (which a released subtitle pulls up and a
    # legend line pushes down).
    rule_y = masthead_h + 0.5
    title = TextSpec(x=margin, y=54.0, anchor="start", text=spec.title.upper()) if spec.title else None
    subtitle = (
        TextSpec(x=margin, y=54.0 + cfg.desc_line_h, anchor="start", text=spec.subtitle) if spec.subtitle else None
    )
    # The scan rect sits centered on the rail and sweeps ±46% of the card
    # width (the specimen's out-to-the-edges-and-back travel).
    scan = RectSpec((width - cfg.scan_w) / 2, masthead_h - cfg.scan_h / 2, cfg.scan_w, cfg.scan_h, cfg.scan_h / 2)

    headline_chip = headline_value = headline_label = None
    key_marks: list[CellPlacement] = []
    key_texts: list[TextSpec] = []
    key_rects: list[RectSpec] = []
    right = margin + avail
    if spec.headline is not None:
        value_w = measure_voice(spec.headline.value, cfg.headline_voice)
        label_w = measure_voice(spec.headline.label, cfg.desc_voice) if spec.headline.label else 0.0
        chip_w = value_w + label_w + (10.0 if spec.headline.label else 0.0) + 24.0
        chip_h = 18.0
        chip_y = 41.0
        headline_chip = RectSpec(right - chip_w, chip_y, chip_w, chip_h, chip_h / 2)
        baseline = chip_y + chip_h / 2 + cfg.headline_voice.size * 0.35
        headline_value = TextSpec(x=right - chip_w + 12.0, y=baseline, anchor="start", text=spec.headline.value)
        if spec.headline.label:
            headline_label = TextSpec(x=right - 12.0, y=baseline, anchor="end", text=spec.headline.label)
    elif chain:
        key_marks, key_texts, key_rects = _tier_reach_key(
            cfg=cfg, geometry=geometry, right=right, baseline_y=legend_baseline
        )
    else:
        key_marks, key_texts = _indicator_legend(
            spec, data_cols, cfg=cfg, geometry=geometry, palette=palette, right=right, baseline_y=legend_baseline
        )

    return HeaderBlock(
        title=title,
        subtitle=subtitle,
        rule=LineSpec(margin, rule_y, margin + avail, rule_y),
        scan=scan,
        headline_chip=headline_chip,
        headline_value=headline_value,
        headline_label=headline_label,
        key_marks=tuple(key_marks),
        key_texts=tuple(key_texts),
        key_rects=tuple(key_rects),
    )


def _tier_reach_key(
    *, cfg: ParadigmMatrixConfig, geometry: Mapping[str, Any], right: float, baseline_y: float
) -> tuple[list[CellPlacement], list[TextSpec], list[RectSpec]]:
    """The chain projection's one-entry key: a mini reach bar with its
    terminal dot beside the words "tier reach" (the g1 specimen mark)."""
    dot_geo = geometry.get("dot") or {}
    bar_w = float(dot_geo.get("key_bar_w", 14.0))
    bar_h = float(dot_geo.get("key_bar_h", 4.8))
    dot_r = float(dot_geo.get("key_dot_r", 3.8))
    label = "tier reach"
    x = right - measure_voice(label, cfg.desc_voice)
    texts = [TextSpec(x=x, y=baseline_y, anchor="start", text=label)]
    cy = baseline_y - 4.0
    dot_cx = x - 8.8
    marks = [
        CellPlacement(
            kind="dot",
            row=-1,
            col=-1,
            box=RectSpec(dot_cx - dot_r, cy - dot_r, 2 * dot_r, 2 * dot_r),
            dot_cx=dot_cx,
            dot_cy=cy,
            dot_r=dot_r,
            dot_filled=True,
            tone="var(--dna-signal)",
            mark_state="on",
        )
    ]
    rects = [RectSpec(dot_cx - 3.2 - bar_w, cy - bar_h / 2, bar_w, bar_h, bar_h / 2)]
    return marks, texts, rects


def _indicator_legend(
    spec: MatrixSpec,
    data_cols: Sequence[MatrixColumn],
    *,
    cfg: ParadigmMatrixConfig,
    geometry: Mapping[str, Any],
    palette: Mapping[str, Any],
    right: float,
    baseline_y: float,
) -> tuple[list[CellPlacement], list[TextSpec]]:
    """Masthead key for check/dot vocabularies, right-aligned at the
    caller's baseline (shared descriptor line, or a reflowed key row).
    Built from the same cell builders the table uses — one mark
    vocabulary, drawn once."""
    kinds = {c.kind for c in data_cols}
    if CellKind.CHECK in kinds:
        entries: list[tuple[CellState, str]] = [
            (CellState.FULL, "full"),
            (CellState.PARTIAL, "partial"),
            (CellState.NONE, "none"),
        ]
        kind = CellKind.CHECK
    elif CellKind.DOT in kinds:
        entries = [(CellState.FULL, "included"), (CellState.OFF, "omitted")]
        kind = CellKind.DOT
    else:
        return [], []

    marks: list[CellPlacement] = []
    texts: list[TextSpec] = []
    x = right
    column = MatrixColumn(id="_legend", label="")
    for state, label in reversed(entries):
        label_w = measure_voice(label, cfg.desc_voice)
        x -= label_w
        texts.append(TextSpec(x=x, y=baseline_y, anchor="start", text=label))
        x -= 16.0
        marks.append(
            build_cell(
                kind=kind,
                cell=MatrixCell(state=state),
                column=column,
                box=RectSpec(x - 6.0, baseline_y - 9.0, 12.0, 12.0),
                row=-1,
                col=-1,
                cfg=cfg,
                geometry=geometry,
                palette=palette,
            )
        )
        x -= 18.0
    return marks, texts


def _colheaders(
    spec: MatrixSpec,
    data_cols: Sequence[MatrixColumn],
    *,
    col_x: Sequence[float],
    col_w: Sequence[float],
    label_header: str,
    cfg: ParadigmMatrixConfig,
    margin: float,
    base_y: float,
) -> list[ColHeader]:
    headers: list[ColHeader] = []
    if label_header:
        headers.append(
            ColHeader(label=TextSpec(x=margin + cfg.cell_pad_x, y=base_y, anchor="start", text=label_header))
        )
    hero = spec.hero_column
    for j, column in enumerate(data_cols):
        cx = col_x[j] + col_w[j] / 2
        if column.align is Align.LEFT:
            x, anchor = col_x[j] + cfg.cell_pad_x, "start"
        elif column.align is Align.RIGHT:
            x, anchor = col_x[j] + col_w[j] - cfg.cell_pad_x, "end"
        else:
            x, anchor = cx, "middle"
        label_y = base_y - (cfg.colhead_sub_voice.size + 2.0 if column.sublabel else 0.0)
        headers.append(
            ColHeader(
                label=TextSpec(x=x, y=label_y, anchor=anchor, text=column.label),
                sublabel=TextSpec(x=x, y=base_y, anchor=anchor, text=column.sublabel) if column.sublabel else None,
                accent=(hero is not None and column.id == hero),
            )
        )
    return headers


def _axis_block(
    spec: MatrixSpec,
    data_cols: Sequence[MatrixColumn],
    cells_by_col: Sequence[Sequence[MatrixCell]],
    *,
    col_x: Sequence[float],
    col_w: Sequence[float],
    rows_top: float,
    axis_top: float,
    cfg: ParadigmMatrixConfig,
) -> AxisSpec | None:
    """Gridlines + tick labels for the first bar column's shared axis."""
    j = next((k for k, c in enumerate(data_cols) if c.kind is CellKind.BAR), None)
    if j is None:
        return None
    values: list[float] = []
    for cell in cells_by_col[j]:
        if isinstance(cell.value, bool) or cell.value is None or cell.value == "":
            continue
        try:
            values.append(float(cell.value))
        except (TypeError, ValueError):
            continue
    axis_max = spec.axis_max if spec.axis_max else (max(values) if values else 0.0)
    if axis_max <= 0:
        return None
    # Track origin mirrors the bar builder: column left + pad; width minus
    # the value zone is unknowable here, so gridlines span the track start
    # to the column's 2/3 point per tick fraction over axis_max.
    step = _nice_step(axis_max / 3.0)
    x0 = col_x[j] + cfg.cell_pad_x
    track_w = col_w[j] - 2 * cfg.cell_pad_x
    grid: list[LineSpec] = []
    ticks: list[TextSpec] = []
    tick_y = axis_top + cfg.axis_voice.size + 6.0
    v = 0.0
    while v <= axis_max + 1e-9:
        x = x0 + (v / axis_max) * track_w * 0.78
        grid.append(LineSpec(x, rows_top + 2.0, x, axis_top))
        ticks.append(TextSpec(x=x, y=tick_y, anchor="middle", text=_fmt_tick(v)))
        v += step
    caption = (
        TextSpec(
            x=col_x[j] + col_w[j] - cfg.cell_pad_x,
            y=tick_y,
            anchor="end",
            text=data_cols[j].unit,
        )
        if data_cols[j].unit
        else None
    )
    return AxisSpec(grid_lines=tuple(grid), tick_labels=tuple(ticks), caption=caption)


def _nice_step(raw: float) -> float:
    """Largest 1/2/2.5/5 x 10^k step that is <= ``raw``.

    Rounding DOWN yields more ticks (3-4 for a /3 target), matching the
    readcost specimen's 0/1k/2k/3k rhythm for an axis max around 3.4k.
    """
    if raw <= 0:
        return 1.0
    mag = 10.0 ** math.floor(math.log10(raw))
    step = mag
    for mult in (2.0, 2.5, 5.0, 10.0):
        if mult * mag <= raw:
            step = mult * mag
    return step


def _fmt_tick(v: float) -> str:
    if v >= 1000:
        scaled = v / 1000.0
        return f"{scaled:g}k"
    return f"{v:g}"
