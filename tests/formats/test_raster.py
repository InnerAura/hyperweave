"""Raster projection — the font-bridge pixel canary + 501 degradation.

The load-bearing test is the font canary: resvg ignores embedded base64 woff2
``@font-face`` (proven empirically), so the raster
path decodes ``data/fonts/*.b64`` woff2 → TTF and feeds resvg via ``font_dirs``.
The canary asserts the label region contains ink — i.e. text actually rendered,
not a fontless blank. When the ``[raster]`` extra is absent, png/webp degrade to
a 501 FORMAT_UNAVAILABLE with an install hint.
"""

from __future__ import annotations

import io

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.core.models import ComposeSpec
from hyperweave.formats import FormatId, project, raster_available
from hyperweave.formats import raster as raster_mod

_HAS_RASTER = raster_available()


def _badge_svg() -> str:
    return compose(
        ComposeSpec(type="badge", genome_id="primer", variant="porcelain", title="STARS", value="1234", state="passing")
    ).svg


@pytest.mark.skipif(not _HAS_RASTER, reason="raster extra not installed")
def test_png_font_canary_text_region_has_ink() -> None:
    """The value/label text renders — the label region is not blank.

    Rasterize the artifact, then rasterize the SAME artifact with the embedded
    @font-face stripped AND the font bridge disabled (no font_dirs). If the font
    bridge works, the two differ in the text region; if resvg were silently
    ignoring our fonts, they would be identical (the empirical failure mode).
    """
    import resvg_py
    from PIL import Image, ImageChops

    from hyperweave.formats.static import resolve_vars_to_hex, strip_animation

    svg = _badge_svg()
    static = strip_animation(resolve_vars_to_hex(svg))

    # Bridged render (the real path).
    bridged_png = project(svg, FormatId.PNG).data
    bridged = Image.open(io.BytesIO(bridged_png)).convert("RGB")

    # Fontless baseline: strip @font-face and supply no font dir at all.
    import re

    no_font = re.sub(r"@font-face\s*\{[^}]*\}", "", static)
    fontless_raw = resvg_py.svg_to_bytes(svg_string=no_font, skip_system_fonts=True, width=bridged.width)
    fontless = Image.open(io.BytesIO(bytes(fontless_raw))).convert("RGB")

    diff = ImageChops.difference(bridged, fontless)
    bbox = diff.getbbox()
    assert bbox is not None, "text did not render — the font bridge is not feeding resvg"


@pytest.mark.skipif(not _HAS_RASTER, reason="raster extra not installed")
def test_png_is_valid_and_scaled() -> None:
    """png is a valid PNG rendered at intrinsic x HW_RASTER_SCALE (default 2)."""
    png = project(_badge_svg(), FormatId.PNG).data
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    from PIL import Image

    img = Image.open(io.BytesIO(png))
    # primer badge is ~121px wide; at 2x the raster is well over 200px.
    assert img.width >= 200


@pytest.mark.skipif(not _HAS_RASTER, reason="raster extra not installed")
def test_png_width_cap_overrides_scale() -> None:
    """A max_width cap clamps the raster below the scaled intrinsic width."""
    from PIL import Image

    png = project(_badge_svg(), FormatId.PNG, max_width=100).data
    assert Image.open(io.BytesIO(png)).width <= 100


@pytest.mark.skipif(not _HAS_RASTER, reason="raster extra not installed")
def test_webp_is_valid_riff() -> None:
    data = project(_badge_svg(), FormatId.WEBP).data
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def test_gif_is_format_unavailable() -> None:
    """gif always raises FORMAT_UNAVAILABLE (501) with a fix — no SVG-input path."""
    with pytest.raises(HwError) as exc:
        project(_badge_svg(), FormatId.GIF)
    assert exc.value.code is HwErrorCode.FORMAT_UNAVAILABLE
    assert exc.value.http_status == 501
    assert "png" in exc.value.fix


def test_raster_unavailable_degrades_to_501(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the raster extra absent, png/webp raise 501 with an install hint."""
    monkeypatch.setattr(raster_mod, "available", lambda: False)
    with pytest.raises(HwError) as exc:
        project(_badge_svg(), FormatId.PNG)
    assert exc.value.code is HwErrorCode.FORMAT_UNAVAILABLE
    assert exc.value.http_status == 501
    assert "hyperweave[raster]" in exc.value.fix


# ── Terminal inlay: the bare face rasterizes with alpha ─────────────────────


@pytest.mark.skipif(not _HAS_RASTER, reason="raster extra not installed")
def test_bare_face_png_preserves_alpha() -> None:
    """The terminal-inlay face (ground=bare + fixed palette + explicit face)
    rasterizes with TRANSPARENT ground — corner alpha 0, no implicit plate
    fill — so a kitty-protocol blit composites the inks directly over the
    terminal background."""
    import io

    from PIL import Image

    from hyperweave.compose.diagram.input import resolve_diagram_preset
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    svg = compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="bare",
            palette="fixed",
            surface_face="dark",
            diagram=resolve_diagram_preset("hub"),
        )
    ).svg
    assert "data-hw-adapt" not in svg  # a face is FIXED, never adaptive
    assert 'data-hw-face="dark"' in svg
    png = project(svg, FormatId.PNG, is_face=True).data
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    w, h = img.size
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        assert img.getpixel(corner)[3] == 0, corner
    # And the artifact actually painted ink somewhere (not a blank sheet).
    assert any(img.getpixel((w // 2, h // 2))), "center pixel empty"


def test_adaptive_flatten_guard_hints_the_face_route() -> None:
    """An adaptive artifact still refuses every flattening format — the fix
    text now names the --face escape (the theme-committed bare face)."""
    from hyperweave.compose.diagram.input import resolve_diagram_preset
    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    svg = compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="bare",
            palette="adaptive",
            diagram=resolve_diagram_preset("hub"),
        )
    ).svg
    with pytest.raises(HwError) as exc:
        project(svg, FormatId.SVG_STATIC)
    assert "--face" in exc.value.fix
