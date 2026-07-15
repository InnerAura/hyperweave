"""Embed-snippet builder — hosted URLs to markdown/html embed code.

INTERNAL seam for the document layer, exposed on no CLI/HTTP/MCP surface. Compose
already returns the hosted ``url``; this turns one (or a light/dark pair) into
copy-pasteable embed code. The ``urls`` list is the twin-``<picture>`` seam: pass
one URL for a plain embed, two (dark first, light second) for a scheme-adaptive
``<picture>`` pair — exactly what Surface Modes' twin faces produce.
"""

from __future__ import annotations

import html
from typing import TypedDict


class EmbedSnippets(TypedDict):
    """Markdown + HTML embed code for one artifact (or a light/dark pair)."""

    markdown: str
    html: str


def embed_snippets(urls: list[str], title: str = "", w: int = 0, h: int = 0) -> EmbedSnippets:
    """Build markdown + HTML embed snippets for one URL or a twin pair.

    ``urls`` — one URL for a plain image; two (dark, light) for a scheme-adaptive
    ``<picture>``. ``title`` becomes the alt text. ``w``/``h`` set explicit HTML
    dimensions when nonzero (markdown carries no size, by design). Raises on an
    empty list — there is nothing to embed.
    """
    if not urls:
        raise ValueError("embed_snippets requires at least one url")

    alt = html.escape(title, quote=True)
    dims = "".join(f' {k}="{v}"' for k, v in (("width", w), ("height", h)) if v)

    if len(urls) == 1:
        md = f"![{title}]({urls[0]})"
        html_out = f'<img src="{html.escape(urls[0], quote=True)}" alt="{alt}"{dims}>'
        return EmbedSnippets(markdown=md, html=html_out)

    # Twin pair: dark first (the brand default), light via prefers-color-scheme.
    dark, light = html.escape(urls[0], quote=True), html.escape(urls[1], quote=True)
    md = (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: light)" srcset="{urls[1]}">\n'
        f'  <img src="{urls[0]}" alt="{title}">\n'
        "</picture>"
    )
    html_out = (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="{dark}">\n'
        f'  <source media="(prefers-color-scheme: light)" srcset="{light}">\n'
        f'  <img src="{dark}" alt="{alt}"{dims}>\n'
        "</picture>"
    )
    return EmbedSnippets(markdown=md, html=html_out)
