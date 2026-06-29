"""The composition layer (L2) — DocumentSpec and its deterministic render.

The AI authors a DocumentSpec (which blocks, what order, which frames, the prose
between) — a PLAN, never markup. ``render(doc, target)`` projects it
deterministically (no AI in the loop) to SVG / Markdown / JSON today, with HTML
reserved as the v0.5 seam. DocumentSpec IS the payload, so the verbs
(extract/transform/diff) generalize from single artifacts to composed documents
without changing shape.
"""

from __future__ import annotations

from hyperweave.compose.document.models import (
    ArtifactBlock,
    Block,
    BlockKind,
    CaptionBlock,
    DocumentSpec,
    FlowBlock,
    HeadingBlock,
    ProseBlock,
    RenderTarget,
)
from hyperweave.compose.document.render import DocumentResult, render

__all__ = [
    "ArtifactBlock",
    "Block",
    "BlockKind",
    "CaptionBlock",
    "DocumentResult",
    "DocumentSpec",
    "FlowBlock",
    "HeadingBlock",
    "ProseBlock",
    "RenderTarget",
    "render",
]
