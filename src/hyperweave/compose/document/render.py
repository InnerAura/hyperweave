"""render(doc, target) — deterministic projection of a DocumentSpec. NO AI.

SVG (standalone/embedded) and Markdown ship today; JSON returns the payload +
envelope; HTML is the reserved v0.5 seam (raises NotImplementedError). Each
target is a pure function of the plan — byte-stable, cacheable, diffable. The
AI decides (which blocks, order, prose); the renderer draws.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from hyperweave import __version__
from hyperweave.compose.document.models import (
    ArtifactBlock,
    CaptionBlock,
    DocumentSpec,
    FlowBlock,
    HeadingBlock,
    ProseBlock,
    RenderTarget,
)
from hyperweave.compose.document.payload import document_envelope, document_payload_json
from hyperweave.compose.engine import compose
from hyperweave.core.contract import SELF_INSTRUCT
from hyperweave.core.envelope import ENVELOPE_VERSION, cdata_safe_json, envelope_json
from hyperweave.core.models import ComposeSpec

_PAD = 28
_GAP = 22
_TEXT_W = 660
_LINE = 22
_HEAD_SIZE = {1: 24, 2: 18, 3: 14}


@dataclass(frozen=True)
class DocumentResult:
    target: str
    svg: str = ""
    markdown: str = ""
    payload: dict[str, Any] | None = None
    envelope: dict[str, Any] | None = None
    width: int = 0
    height: int = 0


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _namespace_ids(inner: str, salt: str) -> str:
    """Prefix ids / url(#) / href=#... so identical embedded children never collide."""
    inner = re.sub(r'id="([^"]+)"', rf'id="{salt}-\1"', inner)
    inner = re.sub(r"url\(#([^)]+)\)", rf"url(#{salt}-\1)", inner)
    return re.sub(r'href="#([^"]+)"', rf'href="#{salt}-\1"', inner)


def _embed_child(child_svg: str, salt: str) -> tuple[str, int, int]:
    """Strip the child <svg> wrapper + its <metadata>, namespace ids, size it."""
    wm = re.search(r'\bwidth="([\d.]+)"', child_svg)
    hm = re.search(r'\bheight="([\d.]+)"', child_svg)
    w = int(float(wm.group(1))) if wm else 0
    h = int(float(hm.group(1))) if hm else 0
    open_end = child_svg.index(">", child_svg.index("<svg")) + 1
    inner = child_svg[open_end : child_svg.rindex("</svg>")]
    inner = re.sub(r"<metadata>.*?</metadata>", "", inner, flags=re.DOTALL)
    return _namespace_ids(inner, salt), w, h


def _wrap(text: str, width_px: int) -> list[str]:
    max_chars = max(8, width_px // 8)
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words, cur = paragraph.split(), ""
        for word in words:
            if cur and len(cur) + 1 + len(word) > max_chars:
                lines.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        lines.append(cur)
    return lines or [""]


def _child_spec(block: ArtifactBlock | FlowBlock, doc: DocumentSpec) -> ComposeSpec:
    if isinstance(block, FlowBlock):
        return ComposeSpec(type="diagram", diagram=block.diagram, genome_id=doc.genome, variant=doc.variant)
    return block.frame.model_copy(update={"genome_id": doc.genome, "variant": doc.variant})


def _render_svg(doc: DocumentSpec) -> tuple[str, int, int]:
    fragments: list[tuple[int, int, str]] = []
    y = _PAD
    content_w = _TEXT_W
    embedded = doc.mode == "embedded"

    for i, block in enumerate(doc.blocks):
        if isinstance(block, ArtifactBlock | FlowBlock):
            child = compose(_child_spec(block, doc)).svg
            inner, w, h = _embed_child(child, f"b{i}")
            content_w = max(content_w, w)
            fragments.append((y, w, f'<g data-hw-block="{i}" transform="translate(__CX{w}__,{y})">{inner}</g>'))
            y += h + _GAP
            if block.caption:
                for line in _wrap(block.caption, content_w):
                    fragments.append((y, 0, f'<text x="{_PAD}" y="{y}" class="hw-doc-cap">{_xml(line)}</text>'))
                    y += _LINE
                y += _GAP - _LINE
        elif isinstance(block, HeadingBlock):
            size = _HEAD_SIZE.get(block.level, 16)
            y += size
            fragments.append(
                (y, 0, f'<text x="{_PAD}" y="{y}" class="hw-doc-h" font-size="{size}">{_xml(block.text)}</text>')
            )
            y += _GAP
        elif isinstance(block, ProseBlock | CaptionBlock):
            cls = "hw-doc-cap" if isinstance(block, CaptionBlock) else "hw-doc-p"
            for line in _wrap(block.text, _TEXT_W):
                y += _LINE
                fragments.append((y, 0, f'<text x="{_PAD}" y="{y}" class="{cls}">{_xml(line)}</text>'))
            y += _GAP

    doc_w = content_w + 2 * _PAD
    doc_h = y + _PAD
    # resolve centered-x placeholders now that doc_w is known
    body = "\n".join(frag.replace(f"__CX{w}__", str((doc_w - w) // 2)) for (_, w, frag) in fragments)
    return _wrap_document_svg(doc, body, doc_w, doc_h, embedded=embedded)


def _wrap_document_svg(doc: DocumentSpec, body: str, w: int, h: int, *, embedded: bool) -> tuple[str, int, int]:
    created = datetime.now(UTC).isoformat()
    payload_json = document_payload_json(doc)
    envelope = document_envelope(doc, payload_json, version=__version__, created=created)
    bg = "" if embedded else f'<rect width="{w}" height="{h}" fill="var(--dna-surface, #0b0e14)"/>'
    style = (
        "<style>"
        ".hw-doc-h{font-family:var(--dna-font-display,Inter,system-ui,sans-serif);font-weight:700;fill:var(--dna-ink-primary,#e8eef7)}"
        ".hw-doc-p{font-family:var(--dna-font-display,Inter,system-ui,sans-serif);font-size:14px;fill:var(--dna-ink-secondary,#aebbcc)}"
        ".hw-doc-cap{font-family:var(--dna-font-mono,ui-monospace,monospace);font-size:11px;fill:var(--dna-ink-muted,#7f8ea3)}"
        "</style>"
    )
    meta = (
        f'<metadata><hw:payload xmlns:hw="https://hyperweave.app/hw/v1.0" schema="document/1" '
        f'media-type="application/json"><![CDATA[{payload_json}]]></hw:payload>'
        f'<hw:envelope xmlns:hw="https://hyperweave.app/hw/v1.0" format="{ENVELOPE_VERSION}" '
        f'media-type="application/json"><![CDATA[{cdata_safe_json(envelope_json(envelope))}]]></hw:envelope></metadata>'
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:hw="https://hyperweave.app/hw/v1.0" '
        f'role="img" aria-labelledby="hwd-title" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'data-hw-type="document" data-hw-genome="{doc.genome}" data-hw-mode="{doc.mode}">'
        f'<title id="hwd-title">{_xml(doc.title)}</title>'
        f"<!-- {SELF_INSTRUCT} -->"
        f"{meta}{style}{bg}{body}</svg>"
    )
    return svg, w, h


def _render_markdown(doc: DocumentSpec) -> str:
    parts: list[str] = [f"# {doc.title}"] if doc.title else []
    for block in doc.blocks:
        if isinstance(block, HeadingBlock):
            parts.append(f"{'#' * (block.level + 1)} {block.text}")
        elif isinstance(block, ProseBlock):
            parts.append(block.text)
        elif isinstance(block, CaptionBlock):
            parts.append(f"_{block.text}_")
        elif isinstance(block, ArtifactBlock | FlowBlock):
            md = compose(_child_spec(block, doc)).markdown
            if md:
                parts.append(md)
            if block.caption:
                parts.append(f"_{block.caption}_")
    return "\n\n".join(p for p in parts if p)


def render(doc: DocumentSpec, target: RenderTarget | str = RenderTarget.SVG) -> DocumentResult:
    """Project a DocumentSpec to a render target, deterministically."""
    target = RenderTarget(target)
    if target is RenderTarget.HTML:
        raise NotImplementedError("html render_target is the v0.5 seam — not implemented")
    if target is RenderTarget.MARKDOWN:
        return DocumentResult(target="markdown", markdown=_render_markdown(doc))
    if target is RenderTarget.JSON:
        payload_json = document_payload_json(doc)
        created = datetime.now(UTC).isoformat()
        import json

        return DocumentResult(
            target="json",
            payload=json.loads(payload_json),
            envelope=document_envelope(doc, payload_json, version=__version__, created=created),
        )
    svg, w, h = _render_svg(doc)
    return DocumentResult(target="svg", svg=svg, width=w, height=h)
