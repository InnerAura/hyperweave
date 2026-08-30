"""Destination scale gates — legibility and texture floors at delivery scale.

An SVG has no intrinsic size; the same artifact is crisp at its design width
and illegible squeezed into a phone column. These gates evaluate an artifact
AGAINST a destination profile (``data/config/destinations.yaml``) at the
profile's worst-case (minimum) scale:

- **font floor**: every rendered font-size x scale ≥ 9 CSS px — below that no
  display renders readable body text;
- **texture floor**: every *visible-texture* turbulence keeps a wavelength of
  ≥ 2 device px (``1/baseFrequency x scale x dpr``) — finer than that the
  noise averages out and the artifact pays full filter cost for grey mush.
  Sub-perceptual DITHER is exempt by its measured amplitude: the diagram
  grain's alpha row is 0.08 (≈ ±1 LSB on the ramp — the anti-banding ruling),
  and a pass whose alpha multiplier is ≤ :data:`DITHER_ALPHA_CEILING` is
  dither by construction, not texture, so a visibility floor does not apply.

A failing verdict is a true fact about density at that destination, never a
corpus wall — ``standalone`` carries the identity policy and is the default
compose target. Every failure string shows its terms.
"""

from __future__ import annotations

import re
from typing import Any

FONT_FLOOR_CSS_PX = 9.0
TEXTURE_FLOOR_DEVICE_PX = 2.0
DITHER_ALPHA_CEILING = 0.1

_VIEWBOX = re.compile(r'viewBox="0 0 ([0-9.]+) [0-9.]+"')
_FONT_ATTR = re.compile(r'font-size="([0-9.]+)"')
_FONT_CSS = re.compile(r"font-size:\s*([0-9.]+)px")
_TURBULENCE = re.compile(r'<feTurbulence[^>]*baseFrequency="([0-9.]+)"[^>]*/>(.*?)</filter>', re.DOTALL)
_ALPHA_ROW = re.compile(r"0 0 0 ([0-9.]+) 0")


def min_scale(profile: dict[str, Any], viewbox_w: float, *, raster_width: float | None = None) -> float | None:
    """The worst-case render scale for ``profile``, or None when the profile
    cannot state one (caller policy without a supplied raster width)."""
    policy = str(profile.get("scale_policy") or "identity")
    if policy == "identity":
        return 1.0
    if policy == "caller":
        return min(1.0, raster_width / viewbox_w) if raster_width and viewbox_w else None
    width = profile.get("render_width") or {}
    floor = float(width.get("min") or 0.0)
    if not floor or not viewbox_w:
        return None
    # An embedding column wider than the artifact renders it at natural size
    # (max-width semantics) — scale never exceeds 1.
    return min(1.0, floor / viewbox_w)


def scale_gates(svg: str, profile: dict[str, Any], *, raster_width: float | None = None) -> list[str]:
    """Gate ``svg`` against ``profile`` at its minimum scale. Empty = passes."""
    m = _VIEWBOX.search(svg)
    if m is None:
        return ["no viewBox — render scale is undefined"]
    scale = min_scale(profile, float(m.group(1)), raster_width=raster_width)
    if scale is None:
        return []  # the profile defers scale to the caller and none was supplied

    failures: list[str] = []
    sizes = [float(v) for v in _FONT_ATTR.findall(svg)] + [float(v) for v in _FONT_CSS.findall(svg)]
    if sizes:
        smallest = min(sizes)
        rendered = smallest * scale
        if rendered < FONT_FLOOR_CSS_PX:
            failures.append(
                f"font floor: {smallest:g}px x scale {scale:.3f} = {rendered:.1f} CSS px < {FONT_FLOOR_CSS_PX:g}"
            )

    dpr = float(profile.get("dpr") or 1)
    for freq, tail in _TURBULENCE.findall(svg):
        alpha = max((float(a) for a in _ALPHA_ROW.findall(tail)), default=1.0)
        if alpha <= DITHER_ALPHA_CEILING:
            continue  # sub-perceptual dither, exempt (see module docstring)
        wavelength = (1.0 / float(freq)) * scale * dpr
        if wavelength < TEXTURE_FLOOR_DEVICE_PX:
            failures.append(
                f"texture floor: 1/{freq} x scale {scale:.3f} x dpr {dpr:g} = "
                f"{wavelength:.2f} device px < {TEXTURE_FLOOR_DEVICE_PX:g}"
            )
    return failures
