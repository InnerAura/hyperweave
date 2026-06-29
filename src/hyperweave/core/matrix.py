"""Matrix frame IR — the universal table the matrix frame renders.

``MatrixSpec`` is the schema decoupler for structured comparisons: the frame
never sees a caller's domain schema, only this IR. Adapters (raw JSON via
CLI/POST/MCP, the connector-registry preset, data tokens) all normalize INTO
it; every projection (SVG layout, ``hw:payload``, the GFM markdown shadow,
the hwz/1 envelope) reads FROM it. The visual is one projection of the IR,
never the source of truth.

Inference policy (enforced in ``compose/matrix_infer.py``): structure is
data-derivable and may be inferred (cell kind, polarity, alignment);
rhetoric is editorial and is caller-only (``hero_column``, ``headline``,
``summary_row``, ``MatrixRow.emphasis``). ``CellKind.BAR`` and
``CellKind.DOT`` are likewise caller-only — a magnitude axis and a
tier-dot vocabulary are claims about the data, not properties of it.

This module is a leaf: it imports only ``core.base`` so that
``core/models.py`` can nest ``MatrixSpec`` on ``ComposeSpec``.
"""

from __future__ import annotations

import itertools
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from hyperweave.core.base import FrozenModel


class CellKind(StrEnum):
    """Cell renderer a column dispatches to — the open registry seam.

    Each non-AUTO kind maps 1:1 to a template partial at
    ``frames/matrix/cells/{kind}.j2``. AUTO resolves at inference time and
    never reaches a layout or template.
    """

    AUTO = "auto"
    TEXT = "text"
    CHECK = "check"
    DOT = "dot"
    BAR = "bar"
    PILL = "pill"
    NUMERIC = "numeric"
    CHIP = "chip"
    GLYPH = "glyph"


class Polarity(StrEnum):
    """Direction of "better" for numeric columns — drives heat tinting."""

    HIGHER = "higher"
    LOWER = "lower"
    NONE = "none"


class Align(StrEnum):
    """Column text alignment; AUTO resolves by role/kind at inference."""

    AUTO = "auto"
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class ColRole(StrEnum):
    """Structural role of a column within the table."""

    LABEL = "label"
    DATA = "data"
    SUMMARY = "summary"


class CellState(StrEnum):
    """Tri-valence check / binary indicator states (check, dot, pill)."""

    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"
    ON = "on"
    OFF = "off"


class RowHeight(StrEnum):
    """Row-height policy, resolved in the layout solver.

    Chip columns ALWAYS grow rows to fit their packed chips — wrapping
    chips force CONTENT regardless of the declared policy, and the ``+N``
    overflow appears only past the per-cell row cap (extreme lists).
    UNIFORM therefore governs chip-less tables; AUTO resolves to UNIFORM
    when nothing wraps."""

    UNIFORM = "uniform"
    CONTENT = "content"
    AUTO = "auto"


class GlyphTint(StrEnum):
    """Glyph fill contract for glyph cells.

    ``ink`` binds the mark to the genome ink (monochrome marks invert
    correctly between paper and near-black substrates). ``brand`` keeps the
    mark's own scalar fill — color logos render identically on both
    substrates. ``full`` selects the multicolor master (``color_paths``)
    when the registry carries one. Selection degrades, never errors:
    full → gradient → brand → ink. For an identity column where the brand
    IS the row, recognisability outranks the monochrome doctrine; ``ink``
    stays the default.
    """

    INK = "ink"
    BRAND = "brand"
    FULL = "full"


class MatrixInputError(ValueError):
    """No usable matrix input (no spec, no adapter, no tokens) or an input
    that cannot be normalized. Maps to HTTP 422 / the SMPTE error badge."""


class MatrixCapacityError(MatrixInputError):
    """Matrix exceeds the hard caps (rows/columns). The adapter must
    paginate; compose never silently truncates a table."""


class Headline(FrozenModel):
    """Masthead chip — present only when the value is load-bearing.

    Caller-only rhetoric (the 219x rule): never inferred from data.
    """

    value: str = Field(description="The headline figure (e.g. '16x')")
    label: str = Field(default="", description="Qualifier text beside the figure")


class MatrixColumn(FrozenModel):
    """One column: a header, a role, and the cell renderer it dispatches to."""

    id: str = Field(description="Stable column identifier (hero_column references this)")
    label: str = Field(description="Header text")
    sublabel: str = Field(default="", description="Second header line: price, '↑ higher', units")
    kind: CellKind = Field(
        default=CellKind.AUTO,
        description="Cell renderer; AUTO infers from data (BAR and DOT are caller-only)",
    )
    align: Align = Field(default=Align.AUTO, description="AUTO: label→left, numeric→right, indicators→center")
    polarity: Polarity = Field(
        default=Polarity.NONE,
        description="Heat direction for numeric columns; NONE = no heat (header keywords may infer)",
    )
    width: float | None = Field(default=None, description="Fixed column width in px; None = solved from content")
    role: ColRole = Field(default=ColRole.DATA, description="label, data, or summary")
    glyph_tint: GlyphTint = Field(default=GlyphTint.INK, description="Glyph fill contract for glyph cells")
    unit: str = Field(
        default="",
        description="Value unit rendered beside bar/numeric values (e.g. 'tok', 'ms'); overrides spec.unit",
    )


class MatrixCell(FrozenModel):
    """One cell. Exactly one value channel is meaningful per the column's kind."""

    value: bool | int | float | str | None = Field(
        default=None, description="text / numeric / pill-value / bar magnitude"
    )
    state: CellState | None = Field(default=None, description="check / dot / binary pill state")
    chips: list[str] = Field(default_factory=list, description="chip cells: packed token list")
    glyph: str = Field(
        default="",
        description=(
            "Glyph registry id (data/registries/glyphs.json) for glyph cells. Registry ids only in v0.4.0-alpha.2."
        ),
    )
    note: str = Field(default="", description="Tooltip / aria / markdown-cell detail (never rendered in the SVG)")


class MatrixRow(FrozenModel):
    """One row: identity (label/sublabel/glyph) plus one cell per non-label column."""

    label: str = Field(description="Row label (the label-zone primary line)")
    sublabel: str = Field(default="", description="Alias, source, descriptor (label-zone second line)")
    glyph: str = Field(default="", description="Row identity glyph registry id (connectors-style rows)")
    cells: list[MatrixCell] = Field(description="One cell per non-LABEL column, in column order")
    section: str = Field(default="", description="Group header this row falls under (must be in spec.sections)")
    emphasis: bool = Field(default=False, description="Accent-lit row. Caller-only rhetoric; never inferred")


class MatrixSpec(FrozenModel):
    """The universal table IR — request input, ``hw:payload`` body, markdown
    shadow source, and envelope source, all at once."""

    title: str = Field(description="Masthead title")
    subtitle: str = Field(default="", description="Masthead descriptor line")
    columns: list[MatrixColumn] = Field(min_length=1, description="Ordered columns (label column optional)")
    rows: list[MatrixRow] = Field(min_length=1, description="Ordered rows")
    sections: list[str] = Field(default_factory=list, description="Ordered group headers")
    hero_column: str | None = Field(
        default=None, description="Highlighted column id (winner band). Caller-only; never inferred"
    )
    summary_row: list[MatrixCell] | None = Field(
        default=None, description="Score / USE-FOR row (one cell per non-LABEL column). Caller-only"
    )
    summary_label: str = Field(default="", description="Summary row label (e.g. 'SCORE', 'USE FOR')")
    headline: Headline | None = Field(default=None, description="Masthead chip. Caller-only; never inferred")
    row_height: RowHeight = Field(
        default=RowHeight.AUTO,
        description=(
            "uniform, content, or auto. Wrapping chip columns always force "
            "content (rows grow to fit; +N only past the row cap)"
        ),
    )
    row_glyph_tint: GlyphTint = Field(
        default=GlyphTint.INK,
        description=(
            "Fill contract for row-identity glyphs (MatrixRow.glyph). ink (default) "
            "binds genome ink; brand keeps each mark's own fills/gradient — for "
            "identity rows where the brand IS the row, recognisability outranks the "
            "monochrome doctrine (architecture §6)"
        ),
    )
    axis_max: float | None = Field(
        default=None,
        description="Bar-scale axis maximum. Default when unset = max of that column's values",
    )
    unit: str = Field(default="", description="Default value unit for bar/numeric columns")
    notes: str = Field(default="", description="Footer legend text")
    lineage: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Append-only edit history written by `transform` — each entry "
            "{parent_id, op, patch, ts}. Empty by default and excluded from the "
            "payload dump, so untransformed artifacts stay byte-identical; once "
            "populated it rides inside the hashed payload (tamper-evident)."
        ),
    )

    @model_validator(mode="after")
    def _validate_shape(self) -> MatrixSpec:
        """Structural integrity: arity, id uniqueness, reference validity."""
        ids = [c.id for c in self.columns]
        if len(set(ids)) != len(ids):
            raise ValueError(f"matrix column ids must be unique, got {ids}")
        data_cols = [c for c in self.columns if c.role is not ColRole.LABEL]
        if not data_cols:
            raise ValueError("matrix needs at least one non-label column")
        for i, row in enumerate(self.rows):
            if len(row.cells) != len(data_cols):
                raise ValueError(
                    f"row {i} ({row.label!r}) has {len(row.cells)} cells; "
                    f"expected {len(data_cols)} (one per non-label column)"
                )
        if self.hero_column is not None and self.hero_column not in ids:
            raise ValueError(f"hero_column {self.hero_column!r} is not a column id (have {ids})")
        if self.sections:
            unknown = sorted({r.section for r in self.rows} - set(self.sections) - {""})
            if unknown:
                raise ValueError(f"row sections {unknown} not declared in spec.sections {self.sections}")
        if self.summary_row is not None and len(self.summary_row) != len(data_cols):
            raise ValueError(
                f"summary_row has {len(self.summary_row)} cells; expected {len(data_cols)} (one per non-label column)"
            )
        return self


def is_chain(spec: MatrixSpec) -> bool:
    """Whether the dot columns form a progressive-inclusion chain.

    True when every data column is a DOT column (two or more), no cell
    carries a partial state, and the columns' inclusion sets are totally
    ordered by the subset relation. Chains render as the tier-span
    projection (reach bars with terminal dots — 3 spans instead of 27
    marks); everything else keeps the tier-dot grid. Pure IR structure —
    safe for projection selection at compose time.
    """
    data_cols = [c for c in spec.columns if c.role is not ColRole.LABEL]
    if len(data_cols) < 2 or any(c.kind is not CellKind.DOT for c in data_cols):
        return False
    included: list[set[int]] = []
    for j in range(len(data_cols)):
        rows: set[int] = set()
        for i, row in enumerate(spec.rows):
            state = row.cells[j].state
            if state is CellState.PARTIAL:
                return False
            if state in (CellState.FULL, CellState.ON):
                rows.add(i)
        included.append(rows)
    ordered = sorted(included, key=len)
    return all(a <= b for a, b in itertools.pairwise(ordered))
