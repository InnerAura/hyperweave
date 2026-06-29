"""frame_schema_for — map a payload schema id to its Pydantic frame model.

The model IS the spec schema, so re-validating a patched payload against it gives
typed safety for free: a patch that drops a required field or breaks arity fails
as SPEC_INVALID instead of producing a broken artifact. Frames whose payload is
a digest (chart/stats) or has no structural model return ``None`` — the caller
falls back to ComposeSpec construction for validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hyperweave.core.diagram import DiagramSpec
from hyperweave.core.matrix import MatrixSpec

if TYPE_CHECKING:
    from pydantic import BaseModel

_MODELS: dict[str, type[BaseModel]] = {
    "matrix/1": MatrixSpec,
    "diagram/1": DiagramSpec,
}


def frame_schema_for(schema: str) -> type[BaseModel] | None:
    """Return the Pydantic model for a payload schema id, or ``None``."""
    return _MODELS.get(schema)
