"""Artifact parsing — pull the embedded seed (payload + envelope) from an SVG.

The seed is the lossless ``hw:payload``; because rendering is deterministic it
regenerates the artifact. Extraction is byte-exact (regex over the CDATA, never
an XML parse) so ``envelope_id(payload_json)`` recomputes the id.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from hyperweave.core.envelope import extract_envelope, extract_payload
from hyperweave.core.errors import HwError, HwErrorCode


@dataclass(frozen=True)
class EmbeddedArtifact:
    """The seed extracted from an artifact."""

    payload_json: str
    payload: dict[str, Any]
    envelope: dict[str, Any]
    schema: str


def load_artifact(source: str) -> str:
    """Resolve an artifact SVG from a raw SVG string, a ``/v1/a/{digest}`` url, or a digest/id.

    URL/id forms resolve against the per-process content cache (the LRU). A cold
    cache raises ENVELOPE_CORRUPT — the caller passes the SVG or recomposes.
    """
    if "<svg" in source[:1024]:
        return source
    from hyperweave.compose.artifact_store import get_artifact

    svg = get_artifact(source.rsplit("/", 1)[-1])
    if svg is None:
        raise HwError(
            HwErrorCode.ENVELOPE_CORRUPT,
            f"cannot resolve artifact from {source[:80]!r}",
            fix="pass the SVG string, or a /v1/a/{digest} url whose render is still cached this process",
        )
    return svg


def extract_embedded(svg: str) -> EmbeddedArtifact:
    """Extract the seed (payload + envelope) from an artifact SVG."""
    pair = extract_payload(svg)
    if pair is None:
        raise HwError(HwErrorCode.SPEC_INVALID, "artifact carries no hw:payload (nothing to extract)")
    schema, payload_json = pair
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise HwError(HwErrorCode.ENVELOPE_CORRUPT, f"hw:payload is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HwError(HwErrorCode.ENVELOPE_CORRUPT, "hw:payload must be a JSON object")
    return EmbeddedArtifact(
        payload_json=payload_json, payload=payload, envelope=extract_envelope(svg) or {}, schema=schema
    )
