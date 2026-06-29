"""DocumentSpec — the composition IR. An ordered list of blocks; two families:
ARTIFACT blocks (a real frame rendered by L1) and COMPOSITION blocks
(document-level primitives the doc agent arranges). Order is part of the
composition. One genome per document (coherence)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import Field

from hyperweave.core.base import FrozenModel
from hyperweave.core.models import ComposeSpec  # noqa: TC001  (Pydantic resolves this at runtime)


class RenderTarget(StrEnum):
    """A render target over the plan — same data, same blocks, deterministic."""

    SVG = "svg"
    MARKDOWN = "markdown"
    JSON = "json"
    HTML = "html"  # reserved v0.5 seam — render(doc, "html") raises NotImplementedError


class BlockKind(StrEnum):
    ARTIFACT = "artifact"  # a real frame (any L1 frame)
    FLOW = "flow"  # unambiguously the diagram frame embedded
    HEADING = "heading"
    PROSE = "prose"
    CAPTION = "caption"


class ArtifactBlock(FrozenModel):
    kind: Literal[BlockKind.ARTIFACT] = BlockKind.ARTIFACT
    frame: ComposeSpec
    caption: str = ""


class FlowBlock(FrozenModel):
    kind: Literal[BlockKind.FLOW] = BlockKind.FLOW
    diagram: dict[str, Any]
    caption: str = ""


class HeadingBlock(FrozenModel):
    kind: Literal[BlockKind.HEADING] = BlockKind.HEADING
    text: str
    level: int = Field(default=1, ge=1, le=3)


class ProseBlock(FrozenModel):
    kind: Literal[BlockKind.PROSE] = BlockKind.PROSE
    text: str


class CaptionBlock(FrozenModel):
    kind: Literal[BlockKind.CAPTION] = BlockKind.CAPTION
    text: str


Block = Annotated[
    ArtifactBlock | FlowBlock | HeadingBlock | ProseBlock | CaptionBlock,
    Field(discriminator="kind"),
]


class DocumentSpec(FrozenModel):
    """The universal, source- and target-agnostic plan — a document's spec."""

    title: str
    blocks: list[Block] = Field(min_length=1)
    genome: str = "primer"
    variant: str = ""
    mode: Literal["standalone", "embedded"] = "standalone"
    intent: str = ""
