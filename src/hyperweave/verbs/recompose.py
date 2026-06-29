"""payload_to_compose_spec — rebuild a ComposeSpec from an extracted seed.

Genome/variant are recovered from ``prov.genome`` (not the payload, which is
content-only). Matrix and diagram carry their full spec, so recompose is exact —
those are the document agent's mutation targets. Frames whose payload is a digest
(chart/stats) or lacks a lineage field are not yet transform-supported.
"""

from __future__ import annotations

from typing import Any

from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.core.models import ComposeSpec


def _genome_variant(prov: dict[str, Any]) -> tuple[str, str]:
    genome, _, variant = str((prov or {}).get("genome", "")).partition(".")
    return genome or "primer", variant


def payload_to_compose_spec(schema: str, spec_dict: dict[str, Any], prov: dict[str, Any]) -> ComposeSpec:
    """Map a patched payload back to a ComposeSpec for recomposition."""
    genome, variant = _genome_variant(prov)
    if schema == "matrix/1":
        return ComposeSpec(type="matrix", matrix=spec_dict, genome_id=genome, variant=variant)
    if schema == "diagram/1":
        return ComposeSpec(type="diagram", diagram=spec_dict, genome_id=genome, variant=variant)
    raise HwError(
        HwErrorCode.SPEC_INVALID,
        f"transform supports matrix and diagram artifacts; {schema!r} is not yet supported",
        fix="transform a matrix or diagram artifact (the document agent's mutation targets)",
    )
