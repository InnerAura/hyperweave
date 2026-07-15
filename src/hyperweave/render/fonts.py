"""Base64 font embedding for self-contained SVGs.

Reads WOFF2 base64 data from ``data/fonts/{slug}.b64`` and companion metadata
from ``{slug}.meta.json``, then assembles ``@font-face`` CSS declarations.
Genomes declare which fonts to embed via their ``fonts`` JSON field; the
per-(genome, frame) gate at ``data/config/font-embedding.yaml`` further narrows
the embedded set per artifact.

v0.3.7 added optional glyph subsetting: pass a ``char_set`` to
:func:`load_font_face_css` and each font's payload is reduced via
``fontTools.subset.Subsetter`` to contain only the codepoints actually
rendered. Cache is memory-only (``@lru_cache``) keyed by the sorted
character string so identical text inputs hit the same subset across
HTTP/CLI/MCP entry points.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from functools import lru_cache
from pathlib import Path

from fontTools.subset import Options, Subsetter  # type: ignore[import-untyped]
from fontTools.ttLib import TTFont  # type: ignore[import-untyped]

_FONTS_DIR = Path(__file__).resolve().parent.parent / "data" / "fonts"
_LOG = logging.getLogger(__name__)


@lru_cache(maxsize=16)
def _load_font(slug: str) -> tuple[str, str, str, str]:
    """Load a single font's base64 data and metadata. Returns (family, weight, style, b64)."""
    b64_path = _FONTS_DIR / f"{slug}.b64"
    meta_path = _FONTS_DIR / f"{slug}.meta.json"
    b64 = b64_path.read_text().strip()
    meta = json.loads(meta_path.read_text())
    return meta["family"], meta["weight"], meta.get("style", "normal"), b64


@lru_cache(maxsize=8)
def _load_font_bytes(slug: str) -> bytes:
    """Decode a font's base64 payload to raw WOFF2 bytes once per process.

    Subsetting runs against the raw bytes; this cache avoids paying the
    base64 decode cost on every subset call. The 5-font on-disk registry
    fits comfortably in the 8-entry LRU.
    """
    _family, _weight, _style, b64 = _load_font(slug)
    return base64.b64decode(b64)


@lru_cache(maxsize=128)
def _subset_b64(slug: str, char_set_str: str) -> str:
    """Subset ``slug`` to only the codepoints in ``char_set_str``, return base64 WOFF2.

    ``char_set_str`` is the deterministic ``"".join(sorted(char_set))`` —
    sort order is the cache-key canonicalization, so ``frozenset("AB")``
    and ``frozenset("BA")`` hit the same entry.

    On any fontTools failure (corrupt source, layout-feature panic) falls
    back to the full font and logs a warning. The fallback path is the
    pre-v0.3.7 behavior, so a degraded run still produces a correct
    self-contained artifact — only the size benefit is lost.

    Sizing: 128 entries x 5 fonts x ~25 distinct character-set fingerprints
    across observed badge/strip/chart/stats text covers steady-state with
    eviction headroom.
    """
    woff2 = _load_font_bytes(slug)
    try:
        font = TTFont(io.BytesIO(woff2))
        options = Options()
        options.flavor = "woff2"
        options.with_zopfli = False
        options.hinting = False
        options.desubroutinize = True
        options.layout_features = ["*"]
        options.name_IDs = ["*"]
        options.notdef_glyph = True
        options.notdef_outline = True
        subsetter = Subsetter(options=options)
        subsetter.populate(text=char_set_str)
        subsetter.subset(font)
        out = io.BytesIO()
        font.flavor = "woff2"
        font.save(out)
        return base64.b64encode(out.getvalue()).decode("ascii")
    except Exception as exc:
        _LOG.warning("font subset failed for %s (%d chars): %s; embedding full font", slug, len(char_set_str), exc)
        return base64.b64encode(woff2).decode("ascii")


_GOOGLE_FAMILIES = {
    "jetbrains-mono": "JetBrains+Mono:wght@400;700",
    "inter": "Inter:wght@400;500;700;800",
    "orbitron": "Orbitron:wght@400;700;900",
    "chakra-petch": "Chakra+Petch:wght@400;700",
    "barlow-condensed-700": "Barlow+Condensed:wght@700",
    "barlow-condensed-900": "Barlow+Condensed:wght@900",
}


def font_import_css(font_slugs: list[str]) -> str:
    """A Google Fonts ``@import`` for the given slugs (the ``cdn`` font-mode).

    Lighter than embedding when the surface can fetch fonts; breaks the
    self-contained guarantee, so it is opt-in.
    """
    families = [_GOOGLE_FAMILIES[s] for s in font_slugs if s in _GOOGLE_FAMILIES]
    if not families:
        return ""
    # The style block lives inside XML — a raw '&' is a malformed entity
    # (browsers forgive it; strict parsers like resvg refuse the document).
    query = "&amp;".join(f"family={fam}" for fam in families)
    return f"@import url('https://fonts.googleapis.com/css2?{query}&amp;display=swap');"


def load_font_face_css(font_slugs: list[str], char_set: frozenset[str] | None = None) -> str:
    """Return ``@font-face`` CSS for the given font slugs, with base64 data URIs.

    Each slug maps to a ``{slug}.b64`` + ``{slug}.meta.json`` pair in
    ``data/fonts/``. Unknown slugs are silently skipped.

    When ``char_set`` is provided each font's payload is subset via
    :func:`_subset_b64` to only the codepoints needed — typical reduction
    is 80-90% for badges where the rendered text is a few dozen glyphs out
    of the full Latin-Extended + Cyrillic + Greek source. ``char_set=None``
    embeds the full font (legacy callers and ``serve/app.py:_error_badge``).
    """
    char_set_str = "" if char_set is None else "".join(sorted(char_set))

    blocks: list[str] = []
    for slug in font_slugs:
        try:
            family, weight, style, full_b64 = _load_font(slug)
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            continue
        b64 = _subset_b64(slug, char_set_str) if char_set_str else full_b64
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
