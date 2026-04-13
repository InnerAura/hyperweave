"""Base64 font embedding for self-contained SVGs.

Reads WOFF2 base64 data from ``data/fonts/{slug}.b64`` and companion metadata
from ``{slug}.meta.json``, then assembles ``@font-face`` CSS declarations.
Genomes declare which fonts to embed via their ``fonts`` JSON field.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_FONTS_DIR = Path(__file__).resolve().parent.parent / "data" / "fonts"


@lru_cache(maxsize=16)
def _load_font(slug: str) -> tuple[str, str, str, str]:
    """Load a single font's base64 data and metadata. Returns (family, weight, style, b64)."""
    b64_path = _FONTS_DIR / f"{slug}.b64"
    meta_path = _FONTS_DIR / f"{slug}.meta.json"
    b64 = b64_path.read_text().strip()
    meta = json.loads(meta_path.read_text())
    return meta["family"], meta["weight"], meta.get("style", "normal"), b64


def load_font_face_css(font_slugs: list[str]) -> str:
    """Return ``@font-face`` CSS for the given font slugs, with base64 data URIs.

    Each slug maps to a ``{slug}.b64`` + ``{slug}.meta.json`` pair in
    ``data/fonts/``. Unknown slugs are silently skipped.
    """
    blocks: list[str] = []
    for slug in font_slugs:
        try:
            family, weight, style, b64 = _load_font(slug)
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            continue
        blocks.append(
            f"@font-face {{\n"
            f"  font-family: '{family}';\n"
            f"  font-style: {style};\n"
            f"  font-weight: {weight};\n"
            f"  font-display: swap;\n"
            f"  src: url(data:font/woff2;base64,{b64}) format('woff2');\n"
            f"}}"
        )
    return "\n".join(blocks)
