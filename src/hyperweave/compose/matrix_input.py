"""Matrix input coercion — every input path normalizes into MatrixSpec here.

Mirrors ``coerce_chart_input``: the frame never sees a caller's domain
schema, only the universal table IR. Three input paths, in precedence
order:

1. **Caller-supplied IR** — ``spec.matrix`` (CLI ``--spec-file``, POST
   body, MCP ``matrix=`` dict). Passed through untouched.
2. **Adapter** — ``connector_data["matrix_adapter"]`` names a server-known
   generator. ``connector-registry`` builds the connector matrix from
   ``data/connector_registry.yaml`` (productionizes the v0.3.12 hand-built
   artifact; a registry edit updates the artifact).
3. **Data tokens** — ``spec.data_tokens`` becomes a simple two-column
   metric/value table.

No usable input raises :class:`MatrixInputError` — the engine never
fabricates a table (the no-fabricated-data doctrine; degrades to the
SMPTE error badge on image surfaces).

This module is the matrix frame's *domain seam*: connector/provider
knowledge is permitted here and in ``data/`` only — the inference, layout,
and template layers stay domain-blind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hyperweave.core.models import ComposeSpec

from hyperweave.core.matrix import (
    Align,
    CellKind,
    CellState,
    ColRole,
    MatrixCell,
    MatrixColumn,
    MatrixInputError,
    MatrixRow,
    MatrixSpec,
    RowHeight,
)

# Server-known preset names → the connector_data payload that produces
# them. Transports (CLI --preset, GET /v1/matrix/{preset}, MCP) resolve a
# preset through here so all three stay in lockstep (Invariant 9).
_MATRIX_PRESETS: dict[str, dict[str, Any]] = {
    "connectors": {"matrix_adapter": "connector-registry"},
}


def matrix_preset_names() -> tuple[str, ...]:
    """Preset names for discovery surfaces (hw_discover, /v1/frames)."""
    return tuple(sorted(_MATRIX_PRESETS))


def resolve_matrix_preset(name: str) -> dict[str, Any]:
    """Map a preset name to its ``connector_data`` payload.

    Raises :class:`MatrixInputError` for unknown names so image surfaces
    degrade to the error badge with a useful message.
    """
    try:
        return dict(_MATRIX_PRESETS[name])
    except KeyError:
        known = ", ".join(matrix_preset_names())
        raise MatrixInputError(f"unknown matrix preset {name!r} (known presets: {known})") from None


def coerce_matrix_input(connector_data: Mapping[str, object] | None, spec: ComposeSpec) -> MatrixSpec:
    """Normalize whichever input path the caller used into a MatrixSpec."""
    if spec.matrix is not None:
        return spec.matrix

    adapter = (connector_data or {}).get("matrix_adapter")
    if adapter is not None:
        if adapter == "connector-registry":
            from hyperweave.config.loader import load_connector_registry

            return build_connector_registry_matrix(load_connector_registry())
        raise MatrixInputError(f"unknown matrix adapter {adapter!r} (known adapters: connector-registry)")

    if spec.data_tokens:
        return build_tokens_matrix(spec.data_tokens)

    raise MatrixInputError(
        "matrix frame requires a table: pass spec.matrix (a MatrixSpec), a matrix preset, or data tokens"
    )


def build_connector_registry_matrix(registry: Sequence[Mapping[str, Any]]) -> MatrixSpec:
    """The generated connector matrix — glyph + chip + pill columns.

    The adapter is a "caller": it declares kinds explicitly (registry rows
    are documentation, not data to infer over). Rows grow to fit their
    metric chips (``row_height=CONTENT``); the full metric lists always
    live in the payload.
    """
    if not registry:
        raise MatrixInputError("connector registry is empty (data/connector_registry.yaml)")

    rows: list[MatrixRow] = []
    for entry in registry:
        auth = str(entry.get("auth", "no")).lower()
        if auth == "yes":
            auth_cell = MatrixCell(state=CellState.FULL, value="Yes")
        elif auth == "opt":
            auth_cell = MatrixCell(state=CellState.PARTIAL, value="Opt-in")
        else:
            auth_cell = MatrixCell(state=CellState.NONE)
        rows.append(
            MatrixRow(
                label=str(entry.get("name", entry.get("id", ""))),
                sublabel=str(entry.get("prefix", "")),
                glyph=str(entry.get("glyph", "")),
                cells=[
                    MatrixCell(chips=[str(m) for m in entry.get("metrics") or []]),
                    MatrixCell(state=CellState.ON if entry.get("live") else CellState.OFF),
                    auth_cell,
                ],
            )
        )

    live_count = sum(1 for entry in registry if entry.get("live"))
    return MatrixSpec(
        title="Data connectors",
        subtitle=f"{live_count} live connectors through the HyperWeave compositor",
        columns=[
            MatrixColumn(id="connector", label="CONNECTOR", role=ColRole.LABEL),
            MatrixColumn(id="metrics", label="METRICS", kind=CellKind.CHIP, align=Align.LEFT),
            MatrixColumn(id="live", label="LIVE", kind=CellKind.PILL, align=Align.CENTER),
            MatrixColumn(id="auth", label="AUTH", kind=CellKind.PILL, align=Align.CENTER),
        ],
        rows=rows,
        row_height=RowHeight.CONTENT,
        notes="full metric lists live in hw:payload",
    )


def build_tokens_matrix(tokens: Sequence[Any]) -> MatrixSpec:
    """Two-column metric/value table from resolved data tokens.

    Accepts ``kv`` and ``live`` tokens (``text`` tokens carry no label/value
    pair and are skipped). Live rows get their provider's registry glyph
    when one exists. Values prefer the connector's unformatted
    ``raw_value`` so numeric columns infer as NUMERIC.
    """
    from hyperweave.config.loader import load_connector_registry

    glyph_by_provider = {str(e.get("provider", "")): str(e.get("glyph", "")) for e in load_connector_registry()}

    rows: list[MatrixRow] = []
    providers: list[str] = []
    for token in tokens:
        kind = getattr(token, "kind", "")
        if kind not in ("kv", "live"):
            continue
        label = str(getattr(token, "label", "") or "")
        if not label:
            continue
        raw_value = getattr(token, "raw_value", None)
        value: bool | int | float | str = (
            raw_value if isinstance(raw_value, bool | int | float) else str(getattr(token, "value", "") or "")
        )
        provider = str(getattr(token, "provider", "") or "")
        if provider and provider not in providers:
            providers.append(provider)
        rows.append(
            MatrixRow(
                label=label,
                sublabel=str(getattr(token, "window", "") or ""),
                glyph=glyph_by_provider.get(provider, ""),
                cells=[MatrixCell(value=value)],
            )
        )

    if not rows:
        raise MatrixInputError("data tokens produced no matrix rows (text tokens are not tabular)")

    return MatrixSpec(
        title="Metrics",
        subtitle=" · ".join(providers),
        columns=[
            MatrixColumn(id="metric", label="METRIC", role=ColRole.LABEL),
            MatrixColumn(id="value", label="VALUE"),
        ],
        rows=rows,
    )
