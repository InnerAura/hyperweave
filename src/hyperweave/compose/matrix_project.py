"""Matrix projections — payload, envelope digest, markdown shadow, desc.

The matrix is a polyglot container: the SVG is one projection of the
``MatrixSpec`` IR, never its source. This module emits the others:

- ``matrix_payload_json`` — the lossless ``hw:payload`` body
  (``schema="matrix/1"``); canonical AND CDATA-safe by construction.
- ``matrix_envelope_data`` — the matrix digest nested under the hwz/1
  envelope's ``data`` key (the envelope itself is assembled by the shared
  frame-agnostic emitter in ``core/envelope.py``).
- ``to_markdown`` — the GFM table shadow (the artifact's terminal/text
  representation).
- ``matrix_desc`` — the generated aria ``<desc>``.
- ``derive_subvariant`` — the ``data-hw-subvariant`` slug.

All functions consume the POST-inference spec (concrete column kinds).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from hyperweave.compose.matrix_cells import format_value_with_unit
from hyperweave.core.envelope import cdata_safe_json
from hyperweave.core.matrix import CellKind, CellState, ColRole, MatrixCell, MatrixSpec, Polarity, is_chain

if TYPE_CHECKING:
    from hyperweave.core.matrix import MatrixColumn, MatrixRow

PAYLOAD_SCHEMA = "matrix/1"

ENVELOPE_ROW_CAP = 16

# Sub-variant precedence: the most structurally distinctive kind wins.
# Dot resolves dynamically: tier-span when the inclusion sets chain
# (reach bars), tier-dot for the grid — category first, projection second.
_SUBVARIANT_PRECEDENCE: tuple[tuple[CellKind, str], ...] = (
    (CellKind.CHIP, "registry"),
    (CellKind.CHECK, "check"),
    (CellKind.DOT, "tier-dot"),
    (CellKind.BAR, "bar-scale"),
    (CellKind.NUMERIC, "numeric-heat"),
    (CellKind.PILL, "pill-tags"),
)

_MD_CHECK = {
    CellState.FULL: "✓",
    CellState.ON: "✓",
    CellState.PARTIAL: "~",
    CellState.NONE: "✗",
    CellState.OFF: "✗",
}
_MD_DOT = {
    CellState.FULL: "●",
    CellState.ON: "●",
    CellState.PARTIAL: "●",
    CellState.NONE: "○",
    CellState.OFF: "○",
}


def matrix_payload_json(spec: MatrixSpec) -> str:
    """Canonical, lossless, CDATA-safe payload text.

    ``exclude_defaults`` keeps it compact while staying lossless (defaults
    reconstruct on ``model_validate``). Any literal ``]]>`` inside string
    content is rewritten to the parse-equivalent ``]]\\u003e`` escape —
    ``]]>`` can only occur inside a JSON string literal, so the rewrite
    never changes the parsed value. The canonical text is therefore safe
    to embed inside ``<![CDATA[...]]>`` verbatim, which is what makes the
    envelope id recomputable from the embedded bytes.
    """
    text = json.dumps(spec.model_dump(mode="json", exclude_defaults=True), separators=(",", ":"), ensure_ascii=False)
    return cdata_safe_json(text)


def derive_subvariant(spec: MatrixSpec) -> str:
    """``data-hw-subvariant`` slug from the dominant data-column kind."""
    kinds = {c.kind for c in spec.columns if c.role is not ColRole.LABEL}
    for kind, slug in _SUBVARIANT_PRECEDENCE:
        if kind in kinds:
            if kind is CellKind.DOT and is_chain(spec):
                return "tier-span"
            return slug
    return "table"


def matrix_envelope_data(spec: MatrixSpec, *, subvariant: str) -> dict[str, Any]:
    """The matrix digest for the envelope's ``data`` key.

    Row primaries are capped at :data:`ENVELOPE_ROW_CAP`; ``rows_total``
    is always present so a capped list is self-describing.
    """
    data_cols = [c for c in spec.columns if c.role is not ColRole.LABEL]
    rows: dict[str, str] = {}
    for row in spec.rows[:ENVELOPE_ROW_CAP]:
        rows[row.label] = _primary_value(row)
    digest: dict[str, Any] = {
        "subvariant": subvariant,
        "cols": [c.id for c in data_cols],
        "rows": rows,
        "rows_total": len(spec.rows),
    }
    polarity = {c.id: c.polarity.value for c in data_cols if c.polarity is not Polarity.NONE}
    if polarity:
        digest["polarity"] = polarity
    if spec.hero_column:
        digest["hero"] = spec.hero_column
    if spec.headline is not None:
        digest["headline"] = f"{spec.headline.value} {spec.headline.label}".strip()
    return digest


def _primary_value(row: MatrixRow) -> str:
    """One-string digest of a row: its first meaningful data cell."""
    for cell in row.cells:
        if cell.state is not None:
            return cell.state.value
        if cell.chips:
            return f"{len(cell.chips)} items"
        if cell.value is not None and cell.value != "":
            return _md_value(cell.value)
        if cell.glyph:
            return cell.glyph
    return ""


def to_markdown(spec: MatrixSpec) -> str:
    """Deterministic GFM table shadow of the spec.

    Cell glyph mapping per the architecture: check → ``✓ / ~ / ✗``;
    dot → ``● / ○``; binary pill → ``Yes / —``; chip → comma-joined FULL
    list (overflow is a rendering concern, not a data one); bar →
    ``value unit``; glyph → the registry id. Sections become bold
    separator rows; the summary row closes the table.
    """
    data_cols = [c for c in spec.columns if c.role is not ColRole.LABEL]
    label_header = next((c.label for c in spec.columns if c.role is ColRole.LABEL), "")

    lines: list[str] = [f"**{spec.title}**" + (f" — {spec.subtitle}" if spec.subtitle else ""), ""]
    header = [label_header or " "] + [_md_header(c) for c in data_cols]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(_md_align(c) for c in [None, *data_cols]) + "|")

    current_section = ""
    for row in spec.rows:
        if spec.sections and row.section != current_section:
            current_section = row.section
            lines.append("| " + " | ".join([f"**{current_section}**"] + [" "] * len(data_cols)) + " |")
        label = row.label + (f" ({row.sublabel})" if row.sublabel else "")
        cells = [_md_cell(cell, col) for cell, col in zip(row.cells, data_cols, strict=True)]
        lines.append("| " + " | ".join([label, *cells]) + " |")

    if spec.summary_row is not None:
        label = f"**{spec.summary_label}**" if spec.summary_label else "**—**"
        cells = [_md_value(c.value) + (f" ({c.note})" if c.note else "") for c in spec.summary_row]
        lines.append("| " + " | ".join([label, *cells]) + " |")

    if spec.notes:
        lines.extend(["", f"*{spec.notes}*"])
    return "\n".join(lines) + "\n"


def _md_header(column: MatrixColumn) -> str:
    return column.label + (f" ({column.sublabel})" if column.sublabel else "")


def _md_align(column: MatrixColumn | None) -> str:
    if column is None:
        return ":---"
    align = column.align.value
    if align == "right":
        return "---:"
    if align == "center":
        return ":---:"
    return ":---"


def _md_value(value: bool | int | float | str | None) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "—"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{int(value):,}" if value.is_integer() else f"{value:g}"
    return value


def _md_cell(cell: MatrixCell, column: MatrixColumn) -> str:
    kind = column.kind
    if kind is CellKind.CHECK:
        return _MD_CHECK.get(cell.state or CellState.NONE, "✗")
    if kind is CellKind.DOT:
        return _MD_DOT.get(cell.state or CellState.OFF, "○")
    if kind is CellKind.PILL:
        if cell.state is not None:
            affirmative = cell.state in (CellState.FULL, CellState.ON)
            partial = cell.state is CellState.PARTIAL
            base = _md_value(cell.value) if cell.value not in (None, "") else ("Yes" if affirmative else "—")
            return base if (affirmative or cell.value not in (None, "")) else ("Opt-in" if partial else "—")
        return _md_value(cell.value)
    if kind is CellKind.CHIP:
        return ", ".join(cell.chips) if cell.chips else "—"
    if kind in (CellKind.BAR, CellKind.NUMERIC):
        text = _md_value(cell.value)
        return format_value_with_unit(text, column.unit) if text != "—" else "—"
    if kind is CellKind.GLYPH:
        return cell.glyph or "—"
    return _md_value(cell.value)


def matrix_desc(spec: MatrixSpec, *, subvariant: str) -> str:
    """Generated aria description from the IR."""
    data_cols = [c.label for c in spec.columns if c.role is not ColRole.LABEL]
    head = f"{spec.title}: {subvariant} matrix, {len(spec.rows)} rows by {len(data_cols)} columns"
    cols = ", ".join(data_cols)
    tail = f" Columns: {cols}." if cols else ""
    subtitle = f" {spec.subtitle}." if spec.subtitle else ""
    return f"{head}.{subtitle}{tail} Full data in hw:payload."
