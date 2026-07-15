"""Raster projection — png/webp from a static SVG, behind the ``[raster]`` extra.

All heavy imports (``resvg_py``, ``PIL``, ``fontTools``) are lazy so a core
install never loads them; :func:`available` reports whether the extra is present.

**Font bridge (empirically required).** resvg ignores embedded base64 woff2
``@font-face`` data-URIs — text does not render from them. So the bundled woff2
fonts (``data/fonts/*.b64``) are decoded to plain TTF in a process-lifetime temp
dir once and handed to resvg via ``font_dirs``; resvg matches them by family
name. Without this, the raster is a fontless, textless render.

**png = rasterize the svg-static projection**, not the live var()-based SVG:
resvg does not resolve CSS custom properties, so the caller flattens vars→hex
first (the var-flatten law). webp is converted from that png via Pillow.
"""

from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# Rasterize at intrinsic size x this factor unless a width cap overrides it, so
# a 148x22 badge is legible rather than a 148px-tall thumbnail. Env-tunable.
_DEFAULT_SCALE = 2

_FONTS_DIR = Path(__file__).resolve().parent.parent / "data" / "fonts"
# Process-lifetime dir holding the decoded TTFs; built lazily on first raster.
_font_dir: str | None = None


def available() -> bool:
    """True when the ``[raster]`` extra is importable (resvg-py + Pillow)."""
    import importlib.util

    return importlib.util.find_spec("resvg_py") is not None and importlib.util.find_spec("PIL") is not None


def _raster_scale() -> int:
    """Intrinsic-size multiplier for the raster (``HW_RASTER_SCALE``, default 2)."""
    raw = os.environ.get("HW_RASTER_SCALE", "")
    if raw:
        try:
            val = int(raw)
        except ValueError:
            return _DEFAULT_SCALE
        if val >= 1:
            return val
    return _DEFAULT_SCALE


def _ensure_font_dir() -> str:
    """Decode the bundled woff2 fonts to TTF in a shared temp dir (once).

    resvg reads TTF/OTF from ``font_dirs`` and matches by family name; it cannot
    read the artifact's embedded base64 woff2. fontTools + brotli (both core
    deps) decode each ``{slug}.b64`` woff2 and re-save it flavor-less (plain
    sfnt/TTF). The dir persists for the process lifetime and is reused across
    every raster call.
    """
    global _font_dir
    if _font_dir is not None and Path(_font_dir).is_dir():
        return _font_dir

    import io

    from fontTools.ttLib import TTFont  # type: ignore[import-untyped]

    dest = tempfile.mkdtemp(prefix="hw-raster-fonts-")
    for b64_path in sorted(_FONTS_DIR.glob("*.b64")):
        try:
            woff2 = base64.b64decode(b64_path.read_text(encoding="utf-8").strip())
            font = TTFont(io.BytesIO(woff2))
            font.flavor = None  # woff2 → plain sfnt so resvg can read it
            font.save(str(Path(dest) / f"{b64_path.stem}.ttf"))
        except Exception:
            continue
    _font_dir = dest
    return dest


def _intrinsic_dims(svg: str) -> tuple[int, int]:
    """Read ``width``/``height`` px from the SVG root (fallback via viewBox)."""
    import re

    w = re.search(r'\bwidth="(\d+(?:\.\d+)?)"', svg)
    h = re.search(r'\bheight="(\d+(?:\.\d+)?)"', svg)
    if w and h:
        return round(float(w.group(1))), round(float(h.group(1)))
    vb = re.search(r'viewBox="[\d.\s]*?(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)"', svg)
    if vb:
        return round(float(vb.group(1))), round(float(vb.group(2)))
    return 0, 0


def to_png(static_svg: str, *, max_width: int | None = None) -> bytes:
    """Rasterize an already-flattened (svg-static) SVG to PNG bytes.

    Renders at intrinsic width x ``HW_RASTER_SCALE``; a ``max_width`` cap
    overrides the scale when the scaled width would exceed it. The caller is
    responsible for passing the static (var-flattened) projection — resvg does
    not resolve ``var(--dna-*)``.
    """
    import resvg_py

    font_dir = _ensure_font_dir()
    iw, _ih = _intrinsic_dims(static_svg)
    scale = _raster_scale()
    target_w = iw * scale if iw else 0
    if max_width is not None and (target_w == 0 or target_w > max_width):
        target_w = max_width

    kwargs: dict[str, object] = {"svg_string": static_svg, "font_dirs": [font_dir]}
    if target_w:
        kwargs["width"] = target_w
    raw = resvg_py.svg_to_bytes(**kwargs)  # type: ignore[arg-type]
    return bytes(raw)


def to_webp(static_svg: str, *, max_width: int | None = None) -> bytes:
    """Rasterize to PNG, then convert to WebP via Pillow (lossless, method 6)."""
    import io

    from PIL import Image

    png = to_png(static_svg, max_width=max_width)
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    out = io.BytesIO()
    img.save(out, format="WEBP", lossless=True, method=6)
    return out.getvalue()


# format id → raster function. png/webp only; gif has no SVG-input path today
# (see the census: takumi is JSX/HTML-input, not arbitrary SVG).
_RASTERIZERS: dict[str, Callable[..., bytes]] = {
    "png": to_png,
    "webp": to_webp,
}


def rasterize(static_svg: str, fmt: str, *, max_width: int | None = None) -> bytes:
    """Rasterize ``static_svg`` to ``fmt`` (png|webp). Unknown fmt → KeyError."""
    return _RASTERIZERS[fmt](static_svg, max_width=max_width)
