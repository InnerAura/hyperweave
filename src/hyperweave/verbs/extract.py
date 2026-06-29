"""extract — pull the seed at a chosen depth.

``payload`` = the full lossless seed (replant → byte-identical artifact); what
``transform``/``diff`` consume. ``envelope`` = the compact hwz/1 digest (the
~200-token actionable read); what ``query``/``verify`` use. ``markdown`` = the
text-shadow projection. ``hw_compress`` is the kept alias for envelope depth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hyperweave.verbs.parse import EmbeddedArtifact, extract_embedded, load_artifact


@dataclass(frozen=True)
class ExtractResult:
    respond: str
    schema: str
    envelope: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    markdown: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"respond": self.respond, "schema": self.schema}
        if self.envelope is not None:
            out["envelope"] = self.envelope
        if self.payload is not None:
            out["payload"] = self.payload
        if self.markdown:
            out["markdown"] = self.markdown
        return out


def _markdown_from(emb: EmbeddedArtifact) -> str:
    """Re-derive the text shadow from the seed (the SVG never embeds it)."""
    if emb.schema == "matrix/1":
        from hyperweave.compose.matrix.project import to_markdown as matrix_to_markdown
        from hyperweave.core.matrix import MatrixSpec

        return matrix_to_markdown(MatrixSpec.model_validate(emb.payload))
    if emb.schema == "diagram/1":
        from hyperweave.compose.diagram.project import to_markdown as diagram_to_markdown
        from hyperweave.core.diagram import DiagramSpec

        return diagram_to_markdown(DiagramSpec.model_validate(emb.payload.get("spec", {})))
    return _simple_markdown(emb.schema, emb.payload)


def _simple_markdown(schema: str, payload: dict[str, Any]) -> str:
    """Best-effort shadow for a content frame: title (bold) + scalar values."""
    kind = schema.split("/")[0]
    title = str(
        payload.get("title") or payload.get("username") or payload.get("glyph") or payload.get("variant") or kind
    )
    scalars = " · ".join(
        f"{k}: {v}" for k, v in payload.items() if k not in ("title", "lineage") and not isinstance(v, list | dict)
    )
    head = f"**{title}**" if title else ""
    return " — ".join(p for p in (head, scalars) if p) or kind


def extract(source: str, *, respond: str = "envelope") -> ExtractResult:
    """Pull the seed at ``respond`` depth: envelope | payload | markdown."""
    emb = extract_embedded(load_artifact(source))
    if respond == "payload":
        return ExtractResult(respond="payload", schema=emb.schema, payload=emb.payload)
    if respond == "markdown":
        return ExtractResult(respond="markdown", schema=emb.schema, markdown=_markdown_from(emb))
    return ExtractResult(respond="envelope", schema=emb.schema, envelope=emb.envelope)
