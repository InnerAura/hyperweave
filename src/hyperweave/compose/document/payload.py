"""document/1 payload + envelope — DocumentSpec IS the payload.

``hw:payload`` serializes the DocumentSpec; ``extract`` reads it; every render
target consumes it. Because it is structural JSON, transform/diff generalize to
documents unchanged. ``frames[]`` in the envelope is the block list compacted —
a composed document's envelope is the first-class message type.
"""

from __future__ import annotations

import json
from typing import Any

from hyperweave.compose.document.models import ArtifactBlock, Block, DocumentSpec, FlowBlock
from hyperweave.core.envelope import build_envelope, cdata_safe_json


def document_payload_json(doc: DocumentSpec) -> str:
    """The lossless document/1 seed — replant (render) → identical document."""
    body = doc.model_dump(mode="json", exclude_defaults=True)
    return cdata_safe_json(json.dumps(body, separators=(",", ":"), ensure_ascii=False))


def _block_label(block: Block) -> str:
    if isinstance(block, ArtifactBlock):
        return block.caption or str(block.frame.type)
    if isinstance(block, FlowBlock):
        return block.caption or str(block.diagram.get("title", "flow"))
    return getattr(block, "text", "")[:48]


def document_envelope(doc: DocumentSpec, payload_json: str, *, version: str, created: str) -> dict[str, Any]:
    """Assemble the hwz/1 envelope for a composed document (kind ``visual-doc``)."""
    frames = [{"t": b.kind.value, "l": _block_label(b)} for b in doc.blocks][:20]
    data: dict[str, Any] = {
        "blocks": len(doc.blocks),
        "kinds": sorted({b.kind.value for b in doc.blocks}),
    }
    genome_label = f"{doc.genome}.{doc.variant}" if doc.variant else doc.genome
    return build_envelope(
        kind="visual-doc",
        title=doc.title,
        intent=doc.intent,
        data=data,
        frames=frames,
        payload_json=payload_json,
        genome_label=genome_label,
        version=version,
        created=created,
    )
