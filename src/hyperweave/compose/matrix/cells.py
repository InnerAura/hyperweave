"""Per-kind cell placement builders for the matrix frame.

Each builder turns ``(MatrixCell, box)`` into a fully-resolved
:class:`CellPlacement` using ``measure_text`` and the cell geometry from
``data/config/matrix-frame.yaml``. Everything a template partial emits is precomputed
here — paths as absolute coordinate strings, paints as ``var(--dna-*)``
references or semantic literals, text already truncated and anchored.

Cross-cell statistics (column min/max for heat, axis maxima, solved
widths) are the solver's job (``matrix_layout``); this module sees one
cell at a time plus the pre-normalized ``heat_t`` / ``axis_frac`` the
solver derived. Domain-blind by contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from hyperweave.compose.matrix.records import CellPlacement, ChipPlacement, GlyphPath
from hyperweave.compose.spatial_records import RectSpec, TextSpec
from hyperweave.core.color import is_achromatic, oklch_to_rgb, rgb_to_oklch
from hyperweave.core.matrix import Align, CellKind, CellState, GlyphTint, MatrixCell, MatrixColumn
from hyperweave.core.text import measure_text

# Surface luminance at or above this reads as a LIGHT substrate (dark ink);
# below it reads as DARK (light ink). The 8 primer variants split cleanly —
# light surfaces sit at ~0.86-0.94, dark at <0.01.
_LIGHT_SURFACE_MIN = 0.5

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from hyperweave.core.paradigm import MatrixVoice, ParadigmMatrixConfig

_ELLIPSIS = "…"


def measure_voice(text: str, voice: MatrixVoice) -> float:
    """Measure ``text`` in a named matrix type voice."""
    return measure_text(
        text,
        font_family=voice.family,
        font_size=voice.size,
        font_weight=voice.weight,
        letter_spacing_em=voice.tracking_em,
    )


def truncate_to_width(text: str, max_w: float, voice: MatrixVoice) -> str:
    """Longest prefix of ``text`` that fits ``max_w``, ellipsized.

    Measurement-based (per-font LUTs), so the ellipsis lands where the ink
    actually runs out. The untruncated string stays in the payload by
    construction — truncation only affects the rendered run.
    """
    if not text or max_w <= 0 or measure_voice(text, voice) <= max_w:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = text[:mid].rstrip() + _ELLIPSIS
        if measure_voice(candidate, voice) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    if lo == 0:
        return _ELLIPSIS
    return text[:lo].rstrip() + _ELLIPSIS


def display_value(value: bool | int | float | str | None) -> str:
    """Canonical display string for a cell value."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{int(value):,}" if value.is_integer() else f"{value:g}"
    return value


def is_numeric_value(value: bool | int | float | str | None) -> bool:
    """Whether a summary value is a score (numbers, numeric strings) or a
    phrase. Scores take the large summary voices; phrases take the quiet
    summary text voice — the tiers-specimen split."""
    if isinstance(value, bool) or value is None or value == "":
        return False
    if isinstance(value, int | float):
        return True
    try:
        float(str(value).replace(",", ""))
    except ValueError:
        return False
    return True


def wrap_text_lines(text: str, max_w: float, voice: MatrixVoice, *, max_lines: int) -> list[str]:
    """Greedy word wrap into at most ``max_lines`` runs.

    Wrapping is the default overflow behavior for text cells — the
    ellipsis appears only on the final permitted line, when content
    genuinely exceeds the cap (or a single word outruns the column).
    """
    if not text:
        return []
    if max_lines <= 1 or measure_voice(text, voice) <= max_w:
        return [truncate_to_width(text, max_w, voice)]
    words = text.split(" ")
    lines: list[str] = []
    i = 0
    while i < len(words):
        if len(lines) == max_lines - 1:
            lines.append(truncate_to_width(" ".join(words[i:]), max_w, voice))
            return lines
        current = words[i]
        i += 1
        while i < len(words) and measure_voice(current + " " + words[i], voice) <= max_w:
            current = current + " " + words[i]
            i += 1
        lines.append(truncate_to_width(current, max_w, voice))
    return lines


def text_lines_needed(text: str, max_w: float, voice: MatrixVoice, *, max_lines: int) -> int:
    """Line count :func:`wrap_text_lines` will produce — keeps the
    row-height pre-pass and the cell builder coupled."""
    return max(1, len(wrap_text_lines(text, max_w, voice, max_lines=max_lines)))


def _heat_rgb(t: float, palette: Mapping[str, Any]) -> tuple[float, float, float]:
    bad = palette.get("heat_bad", [220, 38, 38])
    mid = palette.get("heat_mid", [120, 130, 138])
    good = palette.get("heat_good", [38, 145, 127])
    t = min(1.0, max(0.0, t))
    if t >= 0.5:
        a, b, u = mid, good, (t - 0.5) * 2.0
    else:
        a, b, u = bad, mid, t * 2.0
    r, g, bl = (a[i] + (b[i] - a[i]) * u for i in range(3))
    return r, g, bl


def heat_color(t: float, palette: Mapping[str, Any]) -> str:
    """Diverging ramp color for normalized ``t`` (1 = good pole).

    Piecewise-linear in sRGB: bad rose (the check_none family,
    polarity-inverted — one semantic system reversed) → cool neutral mid →
    good teal. The tile renders this as a low-opacity wash.
    """
    r, g, bl = _heat_rgb(t, palette)
    return f"rgb({round(r)},{round(g)},{round(bl)})"


def heat_text_color(t: float, palette: Mapping[str, Any], *, surface_lum: float = 1.0) -> str:
    """Value ink for a heat cell — surface-conditional, hue preserved.

    The NUMBER carries the semantic color; the tile behind it is a gentle
    wash. On a LIGHT substrate the hue is darkened for AA contrast (the
    grandfathered sRGB multiply, kept byte-stable). On a DARK substrate that
    same dark ink would vanish, so the SAME hue is re-inked in OKLCH: lightness
    lifted toward the light pole, chroma scaled by the same factor so it stays
    legible rather than neon. One derivation, opposite poles by surface.
    """
    darken = float(palette.get("heat_text_darken", 0.62))
    r, g, bl = _heat_rgb(t, palette)
    if surface_lum >= _LIGHT_SURFACE_MIN:
        return f"rgb({round(r * darken)},{round(g * darken)},{round(bl * darken)})"
    lift = float(palette.get("heat_text_dark_lift", 0.16))
    lightness, chroma, hue = rgb_to_oklch(r, g, bl)
    nr, ng, nb = oklch_to_rgb(lightness + lift, chroma * darken, hue)
    return f"rgb({nr},{ng},{nb})"


_PREFIX_UNITS = frozenset({"$", "€", "£", "¥"})


def format_value_with_unit(text: str, unit: str) -> str:
    """Attach a unit to a rendered value: currency symbols prefix
    (``$10``), word units suffix with a space (``250 ms``)."""
    if not text or not unit:
        return text
    if unit in _PREFIX_UNITS:
        return f"{unit}{text}"
    return f"{text} {unit}"


def content_width(
    kind: CellKind,
    cells: Sequence[MatrixCell],
    column: MatrixColumn,
    *,
    cfg: ParadigmMatrixConfig,
    geometry: Mapping[str, Any],
) -> float:
    """Natural column width for content-sized kinds (pre-clamp).

    BAR and CHIP are flexible — they absorb leftover width in the solver —
    so their content width is just the kind floor.
    """
    geo = geometry.get(kind.value) or {}
    pad = cfg.cell_pad_x * 2
    floor = float(geo.get("min_col", 64))
    if kind in (CellKind.BAR, CellKind.CHIP):
        return floor
    if kind in (CellKind.CHECK, CellKind.DOT):
        return floor
    if kind is CellKind.GLYPH:
        return max(floor, float(geo.get("size", 22)) + pad)
    if kind is CellKind.PILL:
        widest = max(
            (measure_voice(_pill_text(c), cfg.pill_voice) for c in cells),
            default=0.0,
        )
        return max(floor, widest + 2 * float(geo.get("pad_x", 11)) + pad)
    if kind is CellKind.NUMERIC and column.polarity.value != "none":
        return max(floor, float(geo.get("tile_w", 96)) + pad)
    if kind is CellKind.NUMERIC:
        # Plain (polarity-less) numeric renders right-aligned text — the
        # tile floor doesn't apply; use the text floor so wide tables
        # (8 plain-numeric columns) stay feasible.
        floor = float((geometry.get("text") or {}).get("min_col", 64))
    widest = max((measure_voice(display_value(c.value), cfg.cell_voice) for c in cells), default=0.0)
    return max(floor, widest + pad)


def chip_line_width(chips: Sequence[str], *, cfg: ParadigmMatrixConfig, geometry: Mapping[str, Any]) -> float:
    """Width of all chips packed on one line (no overflow)."""
    geo = geometry.get("chip") or {}
    pad_x = float(geo.get("pad_x", 8))
    gap = float(geo.get("gap", 6))
    widths = [measure_voice(c, cfg.chip_voice) + 2 * pad_x for c in chips]
    return sum(widths) + gap * max(0, len(widths) - 1)


def chip_rows_needed(
    chips: Sequence[str], avail_w: float, *, cfg: ParadigmMatrixConfig, geometry: Mapping[str, Any]
) -> int:
    """Rows a greedy line-pack needs at ``avail_w`` (≥1)."""
    geo = geometry.get("chip") or {}
    pad_x = float(geo.get("pad_x", 8))
    gap = float(geo.get("gap", 6))
    rows, cursor = 1, 0.0
    for chip in chips:
        w = measure_voice(chip, cfg.chip_voice) + 2 * pad_x
        step = w if cursor == 0 else gap + w
        if cursor > 0 and cursor + step > avail_w:
            rows += 1
            cursor = w
        else:
            cursor += step
    return rows


def build_cell(
    *,
    kind: CellKind,
    cell: MatrixCell,
    column: MatrixColumn,
    box: RectSpec,
    row: int,
    col: int,
    cfg: ParadigmMatrixConfig,
    geometry: Mapping[str, Any],
    palette: Mapping[str, Any],
    emphasis: bool = False,
    heat_t: float | None = None,
    axis_frac: float | None = None,
    glyph_entry: Mapping[str, Any] | None = None,
    value_zone_w: float = 0.0,
    content_mode: bool = False,
    surface_lum: float = 1.0,
) -> CellPlacement:
    """Dispatch to the kind builder; ``kind`` must be concrete (never AUTO)."""
    builders: dict[CellKind, Callable[..., CellPlacement]] = {
        CellKind.TEXT: _text,
        CellKind.CHECK: _check,
        CellKind.DOT: _dot,
        CellKind.BAR: _bar,
        CellKind.PILL: _pill,
        CellKind.NUMERIC: _numeric,
        CellKind.CHIP: _chip,
        CellKind.GLYPH: _glyph,
    }
    return builders[kind](
        cell=cell,
        column=column,
        box=box,
        row=row,
        col=col,
        cfg=cfg,
        geometry=geometry,
        palette=palette,
        emphasis=emphasis,
        heat_t=heat_t,
        axis_frac=axis_frac,
        glyph_entry=glyph_entry,
        value_zone_w=value_zone_w,
        content_mode=content_mode,
        surface_lum=surface_lum,
    )


def _anchor_x(box: RectSpec, align: Align, pad: float) -> tuple[float, str]:
    if align is Align.LEFT:
        return box.x + pad, "start"
    if align is Align.RIGHT:
        return box.x + box.w - pad, "end"
    return box.x + box.w / 2, "middle"


def _baseline(cy: float, voice: MatrixVoice) -> float:
    """Approximate optical baseline for vertically-centered text."""
    return cy + voice.size * 0.35


def _text(
    *,
    cell: MatrixCell,
    column: MatrixColumn,
    box: RectSpec,
    row: int,
    col: int,
    cfg: ParadigmMatrixConfig,
    geometry: Mapping[str, Any],
    palette: Mapping[str, Any],
    emphasis: bool,
    **_kw: Any,
) -> CellPlacement:
    voice = cfg.cell_strong_voice if emphasis else cfg.cell_voice
    cls = "cellstrong" if emphasis else "cell"
    x, anchor = _anchor_x(box, column.align, cfg.cell_pad_x)
    cy = box.y + box.h / 2
    text_geo = geometry.get("text") or {}
    lines = wrap_text_lines(
        display_value(cell.value),
        box.w - 2 * cfg.cell_pad_x,
        voice,
        max_lines=int(text_geo.get("max_lines", 3)),
    )
    if len(lines) > 1:
        # Overflow wraps by default — the row grew in content mode, so the
        # stack centers in its taller box. An optional note becomes one
        # quiet extra line under the stack.
        pitch = float(text_geo.get("line_pitch", 16))
        n = len(lines)
        text_lines = tuple(
            TextSpec(x=x, y=_baseline(cy + (k - (n - 1) / 2) * pitch, voice), anchor=anchor, text=line)
            for k, line in enumerate(lines)
        )
        placement = CellPlacement(
            kind="text",
            row=row,
            col=col,
            box=box,
            emphasis=emphasis,
            note=cell.note,
            text_anchor=anchor,
            cls=cls,
            text_lines=text_lines,
        )
        if cell.note and row >= 0:
            placement = _with(
                placement,
                sub_text=truncate_to_width(cell.note, box.w - 2 * cfg.cell_pad_x, cfg.row_sub_voice),
                sub_x=x,
                sub_y=_baseline(cy + (n - 1) / 2 * pitch + cfg.row_sub_voice.size + 4.0, cfg.row_sub_voice),
                sub_cls="rowsub",
            )
        return placement
    placement = CellPlacement(
        kind="text",
        row=row,
        col=col,
        box=box,
        emphasis=emphasis,
        note=cell.note,
        text=lines[0] if lines else "",
        text_x=x,
        text_y=_baseline(cy, voice),
        text_anchor=anchor,
        cls=cls,
    )
    if cell.note and row >= 0:
        sub_voice = cfg.row_sub_voice
        placement = _with(
            placement,
            text_y=_baseline(cy - sub_voice.size * 0.7, voice),
            sub_text=truncate_to_width(cell.note, box.w - 2 * cfg.cell_pad_x, sub_voice),
            sub_x=x,
            sub_y=_baseline(cy + voice.size * 0.62, sub_voice),
            sub_cls="rowsub",
        )
    return placement


def _check(
    *,
    cell: MatrixCell,
    box: RectSpec,
    row: int,
    col: int,
    cfg: ParadigmMatrixConfig,
    geometry: Mapping[str, Any],
    palette: Mapping[str, Any],
    emphasis: bool,
    **_kw: Any,
) -> CellPlacement:
    geo = geometry.get("check") or {}
    cx, cy = box.x + box.w / 2, box.y + box.h / 2
    state = cell.state or CellState.NONE
    if state in (CellState.FULL, CellState.ON):
        mark_d = f"M{cx - 4.55:.2f},{cy + 0.6:.2f} {geo.get('check', 'l3,3.2 l6.1,-7.3')}"
        tone = str(palette.get("check_full", ""))
    elif state is CellState.PARTIAL:
        mark_d = f"M{cx - 4.2:.2f},{cy:.2f} {geo.get('dash', 'h8.4')}"
        tone = str(palette.get("check_partial", ""))
    else:
        arm = float(geo.get("cross_arm", 7.4))
        half = arm / 2
        mark_d = f"M{cx - half:.2f},{cy - half:.2f} l{arm},{arm} M{cx + half:.2f},{cy - half:.2f} l-{arm},{arm}"
        tone = str(palette.get("check_none", ""))
    return CellPlacement(
        kind="check",
        row=row,
        col=col,
        box=box,
        emphasis=emphasis,
        note=cell.note,
        mark_d=mark_d,
        mark_state=state.value,
        tone=tone,
        stroke_width=float(geo.get("stroke_width", 2)),
    )


def _dot(
    *,
    cell: MatrixCell,
    box: RectSpec,
    row: int,
    col: int,
    cfg: ParadigmMatrixConfig,
    geometry: Mapping[str, Any],
    palette: Mapping[str, Any],
    emphasis: bool,
    **_kw: Any,
) -> CellPlacement:
    geo = geometry.get("dot") or {}
    state = cell.state or CellState.OFF
    filled = state in (CellState.FULL, CellState.ON, CellState.PARTIAL)
    return CellPlacement(
        kind="dot",
        row=row,
        col=col,
        box=box,
        emphasis=emphasis,
        note=cell.note,
        dot_cx=box.x + box.w / 2,
        dot_cy=box.y + box.h / 2,
        dot_r=float(geo.get("filled_r", 4.4)) if filled else float(geo.get("hollow_r", 4.1)),
        dot_filled=filled,
        dot_stroke_w=float(geo.get("hollow_stroke", 1.2)),
        tone="var(--dna-signal)" if filled else "var(--dna-ink-muted)",
        tone_opacity=0.45 if state is CellState.PARTIAL else 1.0,
        mark_state=state.value,
    )


def _bar(
    *,
    cell: MatrixCell,
    column: MatrixColumn,
    box: RectSpec,
    row: int,
    col: int,
    cfg: ParadigmMatrixConfig,
    geometry: Mapping[str, Any],
    palette: Mapping[str, Any],
    emphasis: bool,
    axis_frac: float | None,
    value_zone_w: float,
    **_kw: Any,
) -> CellPlacement:
    geo = geometry.get("bar") or {}
    pad = cfg.cell_pad_x
    cy = box.y + box.h / 2
    track_h = float(geo.get("track_h", 10))
    radius = float(geo.get("radius", 5))
    value_text = display_value(cell.value)
    if not value_text:
        x, anchor = _anchor_x(box, Align.RIGHT, pad)
        return CellPlacement(
            kind="bar",
            row=row,
            col=col,
            box=box,
            emphasis=emphasis,
            note=cell.note,
            text="—",
            text_x=x,
            text_y=_baseline(cy, cfg.cell_voice),
            text_anchor=anchor,
            cls="cell",
        )
    gap = 10.0
    track_w = max(0.0, box.w - 2 * pad - value_zone_w - gap)
    track = RectSpec(box.x + pad, cy - track_h / 2, track_w, track_h, radius)
    fill_w = max(float(geo.get("min_bar_px", 14)), (axis_frac or 0.0) * track_w)
    unit = column.unit
    if unit in _PREFIX_UNITS:
        # Currency symbols fold into the value run ("$10"); word units keep
        # the small trailing sub-run ("3,420 tok").
        value_text = format_value_with_unit(value_text, unit)
        unit = ""
    right = box.x + box.w - pad
    unit_w = measure_voice(unit, cfg.axis_voice) + 4 if unit else 0.0
    return CellPlacement(
        kind="bar",
        row=row,
        col=col,
        box=box,
        emphasis=emphasis,
        note=cell.note,
        track=track,
        bar_fill=RectSpec(track.x, track.y, min(fill_w, track_w), track_h, radius),
        tone="var(--dna-signal)",
        text=value_text,
        text_x=right - unit_w,
        text_y=_baseline(cy, cfg.cell_strong_voice),
        text_anchor="end",
        cls="cellstrong",
        sub_text=unit,
        sub_x=right,
        sub_y=_baseline(cy, cfg.axis_voice),
        sub_cls="axis",
    )


def _pill_text(cell: MatrixCell) -> str:
    if cell.state in (CellState.FULL, CellState.ON):
        return display_value(cell.value) or "Yes"
    if cell.state is CellState.PARTIAL:
        return display_value(cell.value) or "Opt-in"
    if cell.state in (CellState.NONE, CellState.OFF):
        return ""
    if isinstance(cell.value, bool):
        return "Yes" if cell.value else ""
    return display_value(cell.value)


def _pill(
    *,
    cell: MatrixCell,
    box: RectSpec,
    row: int,
    col: int,
    cfg: ParadigmMatrixConfig,
    geometry: Mapping[str, Any],
    palette: Mapping[str, Any],
    emphasis: bool,
    **_kw: Any,
) -> CellPlacement:
    geo = geometry.get("pill") or {}
    cx, cy = box.x + box.w / 2, box.y + box.h / 2
    text = _pill_text(cell)
    if not text:
        return CellPlacement(
            kind="pill",
            row=row,
            col=col,
            box=box,
            emphasis=emphasis,
            note=cell.note,
            text="—",
            text_x=cx,
            text_y=_baseline(cy, cfg.cell_voice),
            text_anchor="middle",
            cls="cell",
            mark_state=(cell.state.value if cell.state else ""),
        )
    h = float(geo.get("height", 20))
    rx = float(geo.get("radius", 10))
    pad_x = float(geo.get("pad_x", 11))
    w = measure_voice(text, cfg.pill_voice) + 2 * pad_x
    pill_rect = RectSpec(cx - w / 2, cy - h / 2, w, h, rx)
    affirmative = cell.state in (CellState.FULL, CellState.ON) or cell.value is True
    opt_in = cell.state is CellState.PARTIAL
    return CellPlacement(
        kind="pill",
        row=row,
        col=col,
        box=box,
        emphasis=emphasis,
        note=cell.note,
        pill=pill_rect,
        pill_gradient=affirmative,
        tone="" if affirmative else "var(--dna-surface-deep)",
        text=text,
        text_x=cx,
        text_y=_baseline(cy, cfg.pill_voice),
        text_anchor="middle",
        cls="pillv",
        text_fill=(
            str(palette.get("pill_yes_text", "#FFFFFF"))
            if affirmative
            else str(palette.get("pill_opt_text", ""))
            if opt_in
            else ""
        ),
        mark_state=(cell.state.value if cell.state else ""),
    )


def _numeric(
    *,
    cell: MatrixCell,
    column: MatrixColumn,
    box: RectSpec,
    row: int,
    col: int,
    cfg: ParadigmMatrixConfig,
    geometry: Mapping[str, Any],
    palette: Mapping[str, Any],
    emphasis: bool,
    heat_t: float | None,
    axis_frac: float | None,
    surface_lum: float = 1.0,
    **_kw: Any,
) -> CellPlacement:
    geo = geometry.get("numeric") or {}
    value_text = format_value_with_unit(display_value(cell.value), column.unit)
    cy = box.y + box.h / 2
    if heat_t is None or not value_text:
        x, anchor = _anchor_x(box, column.align, cfg.cell_pad_x)
        return CellPlacement(
            kind="numeric",
            row=row,
            col=col,
            box=box,
            emphasis=emphasis,
            note=cell.note,
            text=value_text or "—",
            text_x=x,
            text_y=_baseline(cy, cfg.cell_strong_voice),
            text_anchor=anchor,
            cls="cellstrong",
        )
    # The tile is a color FIELD the number sits in, not a capsule around
    # the text: it fills the column width minus padding as a gentle wash
    # (heat_tile_opacity). The VALUE carries the semantic hue; the thin
    # underline gauges within-range magnitude over a faint neutral track —
    # "fixed band · underline = gauged magnitude".
    tile_w = box.w - 2 * cfg.cell_pad_x
    tile_h = float(geo.get("tile_h", 30))
    cx = box.x + box.w / 2
    tile = RectSpec(cx - tile_w / 2, cy - tile_h / 2, tile_w, tile_h, float(geo.get("tile_radius", 6)))
    fill = heat_color(heat_t, palette)
    inset = float(geo.get("underline_inset", 8))
    ul_h = float(geo.get("underline_h", 1.5))
    ul_track_w = tile_w - 2 * inset
    ul_y = tile.y + tile_h - inset / 2 - ul_h
    return CellPlacement(
        kind="numeric",
        row=row,
        col=col,
        box=box,
        emphasis=emphasis,
        note=cell.note,
        heat_tile=tile,
        heat_track=RectSpec(tile.x + inset, ul_y, ul_track_w, ul_h, ul_h / 2),
        heat_underline=RectSpec(tile.x + inset, ul_y, max(0.0, (axis_frac or 0.0) * ul_track_w), ul_h, ul_h / 2),
        tone=fill,
        tone_opacity=(
            float(palette.get("heat_tile_opacity_dark", 0.18))
            if surface_lum < _LIGHT_SURFACE_MIN
            else float(palette.get("heat_tile_opacity", 0.13))
        ),
        text=value_text,
        text_x=cx,
        text_y=_baseline(cy - 1.5, cfg.cell_strong_voice),
        text_anchor="middle",
        cls="cellstrong",
        text_fill=heat_text_color(heat_t, palette, surface_lum=surface_lum),
    )


def _chip(
    *,
    cell: MatrixCell,
    box: RectSpec,
    row: int,
    col: int,
    cfg: ParadigmMatrixConfig,
    geometry: Mapping[str, Any],
    palette: Mapping[str, Any],
    emphasis: bool,
    content_mode: bool,
    **_kw: Any,
) -> CellPlacement:
    geo = geometry.get("chip") or {}
    pad_x = float(geo.get("pad_x", 8))
    gap = float(geo.get("gap", 6))
    h = float(geo.get("height", 17))
    rx = float(geo.get("radius", 5.5))
    pitch = float(geo.get("row_pitch", 24))
    max_rows = int(geo.get("max_chip_rows", 4)) if content_mode else 1
    avail = box.w - 2 * cfg.cell_pad_x
    x0 = box.x + cfg.cell_pad_x

    widths = [measure_voice(c, cfg.chip_voice) + 2 * pad_x for c in cell.chips]
    placed: list[tuple[int, float, float, str]] = []  # (line, x, w, text)
    line, cursor = 0, 0.0
    hidden_from = len(cell.chips)
    for i, w in enumerate(widths):
        step = w if cursor == 0 else gap + w
        if cursor > 0 and cursor + step > avail:
            if line + 1 >= max_rows:
                hidden_from = i
                break
            line, cursor, step = line + 1, 0.0, w
        placed.append((line, cursor if cursor == 0 else cursor + gap, w, cell.chips[i]))
        cursor = (cursor + step) if cursor > 0 else w

    hidden = len(cell.chips) - hidden_from
    if hidden > 0:
        overflow_text = f"+{hidden}"
        ow = measure_voice(overflow_text, cfg.chip_voice) + 2 * pad_x
        # Pop trailing chips on the last line until the overflow chip fits.
        while placed and placed[-1][0] == line and placed[-1][1] + placed[-1][2] + gap + ow > avail:
            hidden += 1
            overflow_text = f"+{hidden}"
            ow = measure_voice(overflow_text, cfg.chip_voice) + 2 * pad_x
            placed.pop()
        ox = (placed[-1][1] + placed[-1][2] + gap) if placed and placed[-1][0] == line else 0.0
        placed.append((line, ox, ow, overflow_text))

    n_lines = (placed[-1][0] + 1) if placed else 1
    block_h = (n_lines - 1) * pitch + h
    top = box.y + (box.h - block_h) / 2
    chips: list[ChipPlacement] = []
    for idx, (ln, x, w, text) in enumerate(placed):
        rect = RectSpec(x0 + x, top + ln * pitch, w, h, rx)
        chips.append(
            ChipPlacement(
                rect=rect,
                text=text,
                text_x=rect.x + rect.w / 2,
                text_y=_baseline(rect.y + h / 2, cfg.chip_voice),
                overflow=hidden > 0 and idx == len(placed) - 1,
            )
        )
    return CellPlacement(
        kind="chip",
        row=row,
        col=col,
        box=box,
        emphasis=emphasis,
        note=cell.note,
        chips=tuple(chips),
        chip_fill_opacity=float(geo.get("fill_opacity", 0.045)),
    )


def _glyph(
    *,
    cell: MatrixCell,
    column: MatrixColumn,
    box: RectSpec,
    row: int,
    col: int,
    cfg: ParadigmMatrixConfig,
    geometry: Mapping[str, Any],
    palette: Mapping[str, Any],
    emphasis: bool,
    glyph_entry: Mapping[str, Any] | None,
    **_kw: Any,
) -> CellPlacement:
    geo = geometry.get("glyph") or {}
    size = float(geo.get("size", 22))
    cx, cy = box.x + box.w / 2, box.y + box.h / 2
    return glyph_mark_placement(
        glyph_entry,
        glyph_id=cell.glyph,
        kind_row=row,
        col=col,
        box=box,
        cx=cx,
        cy=cy,
        size=size,
        tint=column.glyph_tint,
        emphasis=emphasis,
        note=cell.note,
        ink_adaptive_mono=True,
    )


def glyph_mark_placement(
    glyph_entry: Mapping[str, Any] | None,
    *,
    glyph_id: str,
    kind_row: int,
    col: int,
    box: RectSpec,
    cx: float,
    cy: float,
    size: float,
    tint: GlyphTint,
    emphasis: bool = False,
    note: str = "",
    ink_adaptive_mono: bool = False,
) -> CellPlacement:
    """Shared glyph mark builder (data cells and row-identity marks).

    ``ink_adaptive_mono`` (matrix opt-in) re-routes an achromatic brand mark
    to the genome ink so it adapts across substrates. The diagram frame leaves
    it off — its set-cohesion plate system handles dark-substrate contrast for
    the same marks, so changing their fill here would fight that gate.

    ``tint`` is the SELECTION (ink | brand | full); rendering then DEGRADES
    through what the registry entry actually carries, never erroring:
    full → multicolor ``color_paths`` master (its OWN viewBox/coordinate
    space) → ``gradient`` (routed through ``glyph_gradient`` so the defs
    emit one linearGradient per id used) → scalar ``brand_color`` →
    genome ink. Mono renders use the top-level viewBox; a registry
    ``fill_rule`` is stamped on the group (the evenodd marks break
    without it).
    """
    entry = glyph_entry or {}
    mode = resolve_glyph_mode(entry, tint)

    color_master = entry.get("color_paths") if mode == "full" else None
    if isinstance(color_master, Mapping):
        viewbox_src = str(color_master.get("viewBox", "0 0 24 24"))
        raw_paths = color_master.get("paths") or []
        paths = tuple(GlyphPath(d=str(p.get("d", "")), fill=str(p.get("fill", ""))) for p in raw_paths)
        group_fill, opacity, glyph_gradient = "", 1.0, ""
    else:
        viewbox_src = str(entry.get("viewBox", "0 0 24 24"))
        d = str(entry.get("path", ""))
        paths = (GlyphPath(d=d),) if d else ()
        if mode == "gradient":
            group_fill, opacity, glyph_gradient = "", 1.0, glyph_id
        elif mode == "brand":
            brand = str(entry.get("brand_color") or "")
            # A monochrome brand mark (black/white wordmark — anthropic, openai,
            # mcp) baked to its literal brand black vanishes on a dark substrate.
            # Re-route it to the genome ink so it adapts: dark-on-light,
            # light-on-dark. Chromatic marks keep their fixed brand fill.
            if ink_adaptive_mono and is_achromatic(brand):
                group_fill, opacity, glyph_gradient = "var(--dna-ink-primary)", 1.0, ""
            else:
                group_fill, opacity, glyph_gradient = brand, 1.0, ""
        else:
            group_fill, opacity, glyph_gradient = "var(--dna-ink-primary)", 0.9, ""

    parts = viewbox_src.split()
    if len(parts) == 4:
        min_x, min_y, vb_w, vb_h = (float(v) for v in parts)
    else:
        min_x = min_y = 0.0
        vb_w = vb_h = 24.0
    side = max(vb_w, vb_h)
    scale = size / side if side else 1.0
    # Center the viewBox content in the size x size box (non-square and
    # offset-origin viewBoxes both land centered).
    tx = cx - size / 2 - (min_x - (side - vb_w) / 2) * scale
    ty = cy - size / 2 - (min_y - (side - vb_h) / 2) * scale
    transform = f"translate({tx:.2f},{ty:.2f}) scale({scale:.4f})"

    return CellPlacement(
        kind="glyph",
        row=kind_row,
        col=col,
        box=box,
        emphasis=emphasis,
        note=note,
        glyph_paths=paths,
        glyph_transform=transform,
        glyph_fill=group_fill,
        glyph_opacity=opacity,
        glyph_gradient=glyph_gradient,
        glyph_fill_rule=str(entry.get("fill_rule", "") or ""),
    )


def resolve_glyph_mode(entry: Mapping[str, Any], tint: GlyphTint) -> str:
    """Degrade the tint selection through what the entry carries.

    ``full → gradient → brand → ink`` — silent degradation, never an
    error. The resolved mode is what actually renders (and what the
    matrix payload records via its resolved tint fields).
    """
    if tint is GlyphTint.INK:
        return "ink"
    if tint is GlyphTint.FULL:
        master = entry.get("color_paths")
        if isinstance(master, Mapping) and master.get("paths"):
            return "full"
    if isinstance(entry.get("gradient"), Mapping):
        return "gradient"
    if entry.get("brand_color"):
        return "brand"
    return "ink"


def _with(placement: CellPlacement, **updates: Any) -> CellPlacement:
    return replace(placement, **updates)
