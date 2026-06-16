"""Conservative inference for matrix specs — structure only, never rhetoric.

Resolves the AUTO axes of a :class:`MatrixSpec` (cell kind, polarity,
alignment) from the data itself. The contract (architecture §5):

- Inference fills *structure*, which is data-derivable.
- It never invents *rhetoric*, which is editorial: ``hero_column``,
  ``headline``, ``summary_row``, and ``MatrixRow.emphasis`` are caller-only
  and pass through untouched.
- ``CellKind.BAR`` and ``CellKind.DOT`` are likewise never inferred — a
  shared magnitude axis and a tier-dot vocabulary are claims about the
  data, not properties of it. Ambiguous columns default to TEXT.

This module is domain-blind: it operates on the universal table IR only.
Domain adapters live in ``compose/matrix_input.py`` and ``data/``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

from hyperweave.core.matrix import (
    Align,
    CellKind,
    ColRole,
    MatrixCell,
    MatrixColumn,
    MatrixSpec,
    Polarity,
)

_WORD_RE = re.compile(r"[a-z0-9]+")

_BOOL_STRINGS = frozenset({"yes", "no", "true", "false"})

# Alignment defaults by resolved kind (AUTO alignment only).
_ALIGN_BY_KIND: dict[CellKind, Align] = {
    CellKind.TEXT: Align.LEFT,
    CellKind.NUMERIC: Align.RIGHT,
    CellKind.BAR: Align.RIGHT,
    CellKind.CHECK: Align.CENTER,
    CellKind.DOT: Align.CENTER,
    CellKind.PILL: Align.CENTER,
    CellKind.CHIP: Align.LEFT,
    CellKind.GLYPH: Align.CENTER,
}


def infer_matrix(spec: MatrixSpec, *, config: Mapping[str, Any] | None = None) -> MatrixSpec:
    """Resolve AUTO kind/polarity/alignment; return a new spec.

    ``config`` is the data/config/matrix-frame.yaml mapping (``polarity_keywords`` is the
    only key consumed); ``None`` loads it from the package data.
    ``RowHeight.AUTO`` is *not* resolved here — it needs solved column
    widths, so it resolves in the layout solver.
    """
    if config is None:
        from hyperweave.config.loader import load_matrix_config

        config = load_matrix_config()
    keywords = config.get("polarity_keywords") or {}

    data_index = 0
    columns: list[MatrixColumn] = []
    for column in spec.columns:
        if column.role is ColRole.LABEL:
            resolved = column
            if column.align is Align.AUTO:
                resolved = resolved.model_copy(update={"align": Align.LEFT})
            if column.kind is CellKind.AUTO:
                resolved = resolved.model_copy(update={"kind": CellKind.TEXT})
            columns.append(resolved)
            continue

        cells = [row.cells[data_index] for row in spec.rows]
        data_index += 1

        kind = column.kind if column.kind is not CellKind.AUTO else _infer_kind(cells)
        polarity = column.polarity
        if polarity is Polarity.NONE and kind in (CellKind.NUMERIC, CellKind.BAR):
            polarity = _infer_polarity(f"{column.label} {column.sublabel}", keywords)
        align = column.align
        if align is Align.AUTO:
            # A heat tile is a centered object: its header and fallback text
            # share the tile's axis. Plain numeric stays RIGHT.
            heat = kind is CellKind.NUMERIC and polarity is not Polarity.NONE
            align = Align.CENTER if heat else _ALIGN_BY_KIND[kind]
        # Spec-level default unit copies down to value-bearing columns so every
        # consumer (bar builder, axis, markdown) reads one field. Structure,
        # not rhetoric — the caller already declared the unit.
        unit = column.unit
        if not unit and spec.unit and kind in (CellKind.NUMERIC, CellKind.BAR):
            unit = spec.unit

        if (kind, polarity, align, unit) == (column.kind, column.polarity, column.align, column.unit):
            columns.append(column)
        else:
            columns.append(column.model_copy(update={"kind": kind, "polarity": polarity, "align": align, "unit": unit}))

    return spec.model_copy(update={"columns": columns})


def _infer_kind(cells: list[MatrixCell]) -> CellKind:
    """Ordered structural rules over a column's meaningful cells.

    Empty cells (no value, state, chips, or glyph) are ignored so scattered
    gaps don't flip a column to TEXT; an all-empty column is TEXT.
    """
    meaningful = [c for c in cells if _is_meaningful(c)]
    if not meaningful:
        return CellKind.TEXT
    if all(c.state is not None for c in meaningful):
        return CellKind.CHECK
    if any(c.chips for c in meaningful):
        return CellKind.CHIP
    if all(c.glyph for c in meaningful):
        return CellKind.GLYPH
    values = [c.value for c in meaningful if c.value is not None and c.value != ""]
    if values and all(_is_bool_like(v) for v in values):
        return CellKind.PILL
    if values and all(_is_numeric(v) for v in values):
        return CellKind.NUMERIC
    return CellKind.TEXT


def _is_meaningful(cell: MatrixCell) -> bool:
    return bool(cell.state is not None or cell.chips or cell.glyph or (cell.value is not None and cell.value != ""))


def _is_bool_like(value: bool | int | float | str) -> bool:
    if isinstance(value, bool):
        return True
    return isinstance(value, str) and value.strip().lower() in _BOOL_STRINGS


def _is_numeric(value: bool | int | float | str) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return True
    try:
        float(value.strip())
    except ValueError:
        return False
    return True


def _infer_polarity(header_text: str, keywords: Mapping[str, Any]) -> Polarity:
    """Tokenized keyword scan over the column header; ambiguity → NONE."""
    tokens = set(_WORD_RE.findall(header_text.lower()))
    lower_hit = bool(tokens & {str(k).lower() for k in keywords.get("lower") or []})
    higher_hit = bool(tokens & {str(k).lower() for k in keywords.get("higher") or []})
    if lower_hit and not higher_hit:
        return Polarity.LOWER
    if higher_hit and not lower_hit:
        return Polarity.HIGHER
    return Polarity.NONE
