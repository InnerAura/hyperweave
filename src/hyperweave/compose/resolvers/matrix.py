"""Matrix frame resolver — coerce → infer → cap → solve → project.

Mirrors ``resolvers/chart.py``: returns ``{"width", "height", "template",
"context"}`` and never touches SVG. The frame_context it emits is the seam
the matrix templates consume:

- ``matrix_layout`` — frozen :class:`MatrixLayout`; ``.cells`` is the flat
  ``CellPlacement`` list the chassis dispatches through
  ``frames/matrix/cells/{kind}.j2``.
- ``matrix_cfg`` — the :class:`ParadigmMatrixConfig` (type voices, scan
  timing) the defs CSS substitutes from.
- ``payload_json`` / ``payload_schema`` — the lossless ``hw:payload``
  body (canonical + CDATA-safe).
- ``matrix_envelope_data`` / ``matrix_intent`` — inputs for the hwz/1
  envelope, which ``_ctx_matrix`` assembles where ``created_at`` exists
  (so ``prov.ts == hw:created`` with no second clock read).
- ``markdown_shadow`` — the GFM projection, lifted onto
  ``ComposeResult.markdown`` by the engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hyperweave.compose.matrix_infer import infer_matrix
from hyperweave.compose.matrix_input import coerce_matrix_input
from hyperweave.compose.matrix_layout import compute_matrix_layout
from hyperweave.compose.matrix_project import (
    PAYLOAD_SCHEMA,
    derive_subvariant,
    matrix_desc,
    matrix_envelope_data,
    matrix_payload_json,
    to_markdown,
)
from hyperweave.config.loader import load_glyphs, load_matrix_config
from hyperweave.core.matrix import CellKind, GlyphTint
from hyperweave.core.paradigm import ParadigmMatrixConfig

if TYPE_CHECKING:
    from hyperweave.compose.matrix_records import MatrixLayout
    from hyperweave.core.matrix import MatrixSpec
    from hyperweave.core.models import ComposeSpec


def resolve_matrix(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    paradigm_spec: Any = None,
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve a matrix artifact into template + frame context."""
    paradigms_map = genome.get("paradigms") or {}
    if "matrix" not in paradigms_map:
        raise ValueError(
            f"matrix frame is not supported by genome '{genome.get('id', spec.genome_id)}' (no paradigms.matrix entry)"
        )

    cfg: ParadigmMatrixConfig = (
        paradigm_spec.matrix
        if paradigm_spec is not None and hasattr(paradigm_spec, "matrix")
        else ParadigmMatrixConfig()
    )
    mconf = load_matrix_config()
    glyphs = load_glyphs()
    table = infer_matrix(coerce_matrix_input(spec.connector_data, spec), config=mconf)
    table = _apply_glyph_tint(table, spec, genome)
    layout = compute_matrix_layout(table, matrix=cfg, config=mconf, glyph_registry=glyphs)
    subvariant = derive_subvariant(table)
    payload_json = matrix_payload_json(table)

    context: dict[str, Any] = {
        "matrix_layout": layout,
        "matrix_cfg": cfg,
        "matrix_title": table.title,
        "matrix_subtitle": table.subtitle,
        "matrix_notes": table.notes,
        "matrix_subvariant": subvariant,
        "semantic_palette": dict(mconf.get("semantic_palette") or {}),
        "matrix_voices": _voice_params(cfg, title_size=layout.title_voice_size),
        # The scan rect is centered on the rail and sweeps ±46% of the card
        # width — out past both edges and back (the specimen's travel; the
        # card clip crops the overshoot). Transform-only, CIM.
        "matrix_scan_travel": round(0.46 * layout.width, 1),
        "matrix_glyph_gradients": _used_glyph_gradients(layout, glyphs),
        "payload_json": payload_json,
        "payload_schema": PAYLOAD_SCHEMA,
        "matrix_envelope_data": matrix_envelope_data(table, subvariant=subvariant),
        "matrix_intent": spec.intent or f"structured comparison: {table.title}",
        "markdown_shadow": to_markdown(table),
        "title_text": table.title,
        "desc_text": matrix_desc(table, subvariant=subvariant),
        "data_hw_subvariant": subvariant,
        "matrix_text_surface": _text_surface(layout),
    }
    return {
        "width": layout.width,
        "height": layout.height,
        "template": "frames/matrix.svg.j2",
        "context": context,
    }


def _apply_glyph_tint(table: MatrixSpec, spec: ComposeSpec, genome: dict[str, Any]) -> MatrixSpec:
    """Resolve the glyph tint selection into the table IR.

    Precedence per slot: an explicit IR declaration (``row_glyph_tint`` /
    a glyph column's ``glyph_tint``) > the caller's ``ComposeSpec.glyph_tint``
    (``?glyph_tint=``) > the genome's per-frame default > ink. Resolving
    INTO the spec means the embedded ``hw:payload`` records the tint that
    actually rendered.
    """
    selected = spec.glyph_tint or str((genome.get("glyph_tint") or {}).get("matrix", ""))
    if not selected:
        return table
    tint = GlyphTint(selected)
    updates: dict[str, Any] = {}
    if "row_glyph_tint" not in table.model_fields_set:
        updates["row_glyph_tint"] = tint
    columns = list(table.columns)
    changed = False
    for i, column in enumerate(columns):
        if column.kind is CellKind.GLYPH and "glyph_tint" not in column.model_fields_set:
            columns[i] = column.model_copy(update={"glyph_tint": tint})
            changed = True
    if changed:
        updates["columns"] = columns
    return table.model_copy(update=updates) if updates else table


def _voice_params(cfg: ParadigmMatrixConfig, *, title_size: float) -> list[dict[str, Any]]:
    """Type-voice CSS parameters for the defs ``<style>`` block.

    The same family/size/weight tuples the solver measured with — keeping
    measurement and rendering coupled (``title_size`` carries the layout's
    active title voice, which steps down on compact frames). Stacks bind
    the genome font roles so variants restate the voices through
    ``--dna-font-*``.
    """

    def stack(family: str) -> str:
        if family == "Inter":
            return "var(--dna-font-display, 'Inter', system-ui, sans-serif)"
        return "var(--dna-font-mono, 'JetBrains Mono', ui-monospace, monospace)"

    named = (
        ("title", cfg.title_voice.model_copy(update={"size": title_size})),
        ("desc", cfg.desc_voice),
        ("colhead", cfg.colhead_voice),
        ("colheadsub", cfg.colhead_sub_voice),
        ("rowlabel", cfg.row_label_voice),
        ("rowlabelsub", cfg.row_label_sub_voice),
        ("rowsub", cfg.row_sub_voice),
        ("cell", cfg.cell_voice),
        ("cellstrong", cfg.cell_strong_voice),
        ("section", cfg.section_voice),
        ("axis", cfg.axis_voice),
        ("chip", cfg.chip_voice),
        ("pillv", cfg.pill_voice),
        ("foot", cfg.foot_voice),
        ("headline", cfg.headline_voice),
        ("sumval", cfg.summary_value_voice),
        ("sumvalhero", cfg.summary_hero_voice),
        ("sumqual", cfg.summary_qual_voice),
        ("sumtext", cfg.summary_text_voice),
    )
    return [
        {"name": name, "stack": stack(v.family), "size": v.size, "weight": v.weight, "tracking": v.tracking_em}
        for name, v in named
    ]


def _used_glyph_gradients(layout: MatrixLayout, glyphs: dict[str, Any]) -> list[dict[str, Any]]:
    """Gradient definitions for every brand-gradient mark the layout placed.

    The defs template emits one ``linearGradient`` per entry as
    ``#{uid}-gg-{id}`` — id-scoped per artifact so multiple embeds on one
    page never collide.
    """
    ids: list[str] = []
    for cell in layout.cells:
        if cell.glyph_gradient and cell.glyph_gradient not in ids:
            ids.append(cell.glyph_gradient)
    gradients: list[dict[str, Any]] = []
    for glyph_id in ids:
        gradient = (glyphs.get(glyph_id) or {}).get("gradient")
        if isinstance(gradient, dict):
            gradients.append({"id": glyph_id, **gradient})
    return gradients


def _text_surface(layout: MatrixLayout) -> list[str]:
    """Every string the SVG renders — feeds the font subsetter."""
    strings: list[str] = []
    for key in ("masthead_title", "masthead_desc"):
        text_spec = layout.texts.get(key)
        if text_spec is not None:
            strings.append(text_spec.text)
    for header in layout.colheaders:
        strings.append(header.label.text)
        if header.sublabel is not None:
            strings.append(header.sublabel.text)
    for band in layout.section_bands:
        strings.append(band.label.text)
    for cell in layout.cells:
        if cell.text:
            strings.append(cell.text)
        if cell.sub_text:
            strings.append(cell.sub_text)
        for chip in cell.chips:
            strings.append(chip.text)
    if layout.axis is not None:
        strings.extend(tick.text for tick in layout.axis.tick_labels)
        if layout.axis.caption is not None:
            strings.append(layout.axis.caption.text)
    if layout.summary is not None and layout.summary.label is not None:
        strings.append(layout.summary.label.text)
    head = layout.header
    if head.headline_value is not None:
        strings.append(head.headline_value.text)
    if head.headline_label is not None:
        strings.append(head.headline_label.text)
    strings.extend(t.text for t in head.key_texts)
    footer = layout.footer
    if footer is not None:
        if footer.notes is not None:
            strings.append(footer.notes.text)
        if footer.brand is not None:
            strings.append(footer.brand.text)
    return [s for s in strings if s]
