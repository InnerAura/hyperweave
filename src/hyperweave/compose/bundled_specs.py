"""The single bundled-spec store — one resolver for CLI and HTTP.

The content ``--preset`` flag is retired: ``--spec-file`` accepts a bare
name that resolves against bundled specs, and the HTTP GET
``/v1/{matrix,diagram}/{name}/…`` URL-grammar routes read the SAME store, so the
two surfaces cannot drift. This module is that store — a thin dispatcher over the
per-frame preset loaders (``data/presets/{matrix,diagram}.yaml``, content-as-data,
zero Python per entry). Every existing preset name keeps working everywhere.

Matrix and diagram resolve to different shapes: a matrix preset is a
``connector_data`` payload (an adapter name the builder expands); a diagram preset
is a complete ``DiagramSpec`` dict. :class:`BundledSpec` carries which, so a
caller folds it into the right ComposeSpec field without re-branching on frame
type. New frame families (hub/lanes/agent-lifecycle land as diagram bundled
specs) need only a YAML entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hyperweave.core.errors import HwError, HwErrorCode

# Frame types that have a bundled-spec store today. A frame outside this set has
# no server-known specs — the resolver says so loudly rather than 404-ing bare.
_BUNDLED_FRAMES = {"matrix", "diagram"}


@dataclass(frozen=True, slots=True)
class BundledSpec:
    """A resolved bundled spec plus which ComposeSpec field it fills.

    ``field`` is ``"connector_data"`` (matrix presets — an adapter payload) or
    ``"diagram"`` (diagram presets — the topology IR). ``value`` is the dict to
    place under that field on the compose input.
    """

    field: str
    value: dict[str, Any]


def bundled_spec_names(frame_type: str) -> tuple[str, ...]:
    """The bundled-spec names for a frame type (discovery surfaces read this)."""
    from hyperweave.config.loader import load_diagram_presets, load_matrix_presets

    if frame_type == "matrix":
        return tuple(sorted(load_matrix_presets()))
    if frame_type == "diagram":
        return tuple(sorted(load_diagram_presets()))
    return ()


def resolve_bundled_spec(frame_type: str, name: str) -> BundledSpec:
    """Resolve a bundled spec name for a frame type from the single store.

    Raises ``PRESET_UNKNOWN`` for an unknown name (naming the menu) and
    ``TYPE_UNKNOWN`` for a frame type with no store — the same closed error
    contract every surface renders.
    """
    from hyperweave.config.loader import load_diagram_presets, load_matrix_presets

    if frame_type not in _BUNDLED_FRAMES:
        raise HwError(
            HwErrorCode.TYPE_UNKNOWN,
            f"frame type {frame_type!r} has no bundled specs",
            fix=f"bundled specs exist for: {sorted(_BUNDLED_FRAMES)}",
        )

    store = load_matrix_presets() if frame_type == "matrix" else load_diagram_presets()
    found = store.get(name)
    if found is None:
        known = ", ".join(sorted(store)) or "(none configured)"
        raise HwError(
            HwErrorCode.PRESET_UNKNOWN,
            f"unknown {frame_type} spec {name!r}",
            fix=f"known {frame_type} specs: {known}",
        )
    field = "connector_data" if frame_type == "matrix" else "diagram"
    return BundledSpec(field=field, value=dict(found))
