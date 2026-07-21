"""payload_to_compose_spec — rebuild a ComposeSpec from an extracted seed.

Genome/variant are recovered from ``prov.genome`` (not the payload, which is
content-only). Matrix and diagram carry their full spec, so recompose is exact —
those are the document agent's mutation targets. Frames whose payload is a digest
(chart/stats) or lacks a lineage field are not yet transform-supported.
"""

from __future__ import annotations

import re
from typing import Any

from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.core.models import ComposeSpec

_FACE_RE = re.compile(r'data-hw-face="([^"]*)"')
_GROUND_RE = re.compile(r'data-hw-ground="([^"]*)"')


def _genome_variant(prov: dict[str, Any]) -> tuple[str, str]:
    genome, _, variant = str((prov or {}).get("genome", "")).partition(".")
    return genome or "primer", variant


def _surface_kwargs(spec_dict: dict[str, Any]) -> dict[str, str]:
    """The parent artifact's resolved surface, threaded back through recompose.

    Transform preserves presentation — a bare adaptive inlay must not silently
    re-render as the plate default. The payload's ``surface`` block (absent for
    plate, by serialization contract) maps onto the ComposeSpec format axes.
    """
    surface = spec_dict.get("surface")
    if not isinstance(surface, dict):
        return {}
    out: dict[str, str] = {}
    if surface.get("ground"):
        out["ground"] = str(surface["ground"])
    if surface.get("palette"):
        out["palette"] = str(surface["palette"])
    if surface.get("face"):
        out["surface_face"] = str(surface["face"])
    return out


def _surface_kwargs_from_parent(svg: str) -> dict[str, str]:
    """Read the parent's rendered presentation when the payload is silent.

    The payload's ``surface`` block is absent for plate by serialization
    contract — but absent is ambiguous between "explicit plate" and "genome
    default", so a twin-default genome (primer) would re-render an explicit
    plate parent's child adaptive. The artifact itself disambiguates: a face
    render stamps ``data-hw-face``, an adaptive render stamps ``data-hw-adapt``;
    NEITHER marker means the parent rendered plate — pin it explicitly. The pin
    is a no-op for plate-default genomes (``stamp_surface`` still recognizes
    plate, so child payloads stay surface-key-absent and ids byte-stable).
    Regex over the root attributes, matching the verb layer's extraction idiom.
    """
    face = _FACE_RE.search(svg)
    if face and face.group(1):
        return {"palette": "fixed", "surface_face": face.group(1)}
    if 'data-hw-adapt="adaptive"' in svg:
        ground = _GROUND_RE.search(svg)
        return {
            "ground": ground.group(1) if ground and ground.group(1) else "opaque",
            "palette": "adaptive",
        }
    return {"ground": "opaque", "palette": "fixed"}


def payload_to_compose_spec(
    schema: str, spec_dict: dict[str, Any], prov: dict[str, Any], *, parent_svg: str = ""
) -> ComposeSpec:
    """Map a patched payload back to a ComposeSpec for recomposition.

    The payload's ``surface`` block wins when present; when silent and the
    caller holds the parent SVG, presentation is read from the artifact itself.
    """
    genome, variant = _genome_variant(prov)
    surface = _surface_kwargs(spec_dict) or (_surface_kwargs_from_parent(parent_svg) if parent_svg else {})
    if schema == "matrix/1":
        return ComposeSpec(type="matrix", matrix=spec_dict, genome_id=genome, variant=variant, **surface)
    if schema == "diagram/1":
        return ComposeSpec(type="diagram", diagram=spec_dict, genome_id=genome, variant=variant, **surface)
    raise HwError(
        HwErrorCode.SPEC_INVALID,
        f"transform supports matrix and diagram artifacts; {schema!r} is not yet supported",
        fix="transform a matrix or diagram artifact (the document agent's mutation targets)",
    )
