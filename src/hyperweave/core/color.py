"""Color math utilities -- ONE canonical copy."""

from __future__ import annotations

import re


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a hex color string to an (R, G, B) tuple."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        msg = f"Expected 6-character hex string, got '{hex_color}'"
        raise ValueError(msg)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB values to a hex color string."""
    return f"#{r:02X}{g:02X}{b:02X}"


def mix_hex(a: str, b: str, t: float) -> str:
    """``a`` mixed toward ``b`` by ``t`` in sRGB, rounded once per channel.

    The pre-blend primitive: ``mix_hex(ink, ground, 1 - alpha)`` is the exact
    composited color of ``ink`` drawn at ``alpha`` over an opaque ``ground``.
    """
    ar, ag, ab = hex_to_rgb(a)
    br, bg, bb = hex_to_rgb(b)
    return rgb_to_hex(round(ar + (br - ar) * t), round(ag + (bg - ag) * t), round(ab + (bb - ab) * t))


def hex_to_rgb_triplet(hex_color: str) -> str:
    """Convert a hex color to an ``"r,g,b"`` string for rgba() embedding.

    Returns an empty string for missing/malformed input so callers can gate
    on truthiness instead of catching.
    """
    try:
        r, g, b = hex_to_rgb(hex_color)
    except ValueError:
        return ""
    return f"{r},{g},{b}"


def relative_luminance(hex_color: str) -> float:
    """Compute WCAG 2.1 relative luminance of a hex color."""
    r, g, b = hex_to_rgb(hex_color)

    def _linearize(channel: int) -> float:
        s = channel / 255.0
        if s <= 0.04045:
            return s / 12.92
        return float(((s + 0.055) / 1.055) ** 2.4)

    r_lin = _linearize(r)
    g_lin = _linearize(g)
    b_lin = _linearize(b)

    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def contrast_ratio(hex1: str, hex2: str) -> float:
    """Compute WCAG contrast ratio between two hex colors."""
    l1 = relative_luminance(hex1)
    l2 = relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def is_wcag_aa(hex1: str, hex2: str) -> bool:
    """Check if two colors meet WCAG AA contrast requirement."""
    return contrast_ratio(hex1, hex2) >= 4.5


def is_achromatic(hex_color: str, *, max_spread: int = 30) -> bool:
    """True when a hex color carries no meaningful hue (black/white/gray).

    Spread = max channel - min channel in sRGB. Brand marks whose color is
    essentially achromatic (anthropic #191919, openai/mcp #000000) read as
    monochrome and must adapt to the genome ink; chromatic marks (blues,
    oranges, gradients — spread well over 150) keep their fixed brand fill.
    """
    try:
        r, g, b = hex_to_rgb(hex_color)
    except ValueError:
        return False
    return (max(r, g, b) - min(r, g, b)) <= max_spread


def _srgb_to_linear(c: float) -> float:
    c = max(0.0, min(1.0, c))
    return c / 12.92 if c <= 0.04045 else float(((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c: float) -> float:
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else float(1.055 * c ** (1 / 2.4) - 0.055)


def rgb_to_oklch(r: float, g: float, b: float) -> tuple[float, float, float]:
    """Convert sRGB (0-255) to OKLCH (lightness, chroma, hue-degrees).

    OKLCH is perceptually uniform, so lightness can be shifted toward a
    contrast pole without the hue drifting — the right space for re-inking a
    semantic hue onto a light vs dark substrate.
    """
    import math

    lr, lg, lb = (_srgb_to_linear(v / 255.0) for v in (r, g, b))
    lc = 0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb
    mc = 0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb
    sc = 0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb
    l_, m_, s_ = float(lc ** (1 / 3)), float(mc ** (1 / 3)), float(sc ** (1 / 3))
    lightness = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return lightness, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360.0


def oklch_to_rgb(lightness: float, chroma: float, hue_deg: float) -> tuple[int, int, int]:
    """Convert OKLCH back to sRGB (0-255), gamut-clamped per channel."""
    import math

    h = math.radians(hue_deg)
    a, bb = chroma * math.cos(h), chroma * math.sin(h)
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * bb) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * bb) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * bb) ** 3
    lr = 4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    lg = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    lb = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_
    r, g, b = (max(0, min(255, round(_linear_to_srgb(v) * 255))) for v in (lr, lg, lb))
    return r, g, b


def adjust_oklch(hex_color: str, *, dl: float = 0.0, dc: float = 1.0, dh: float = 0.0) -> str:
    """Shift a hex color in OKLCH and return the re-encoded hex.

    ``dl`` is ADDED to lightness (clamped 0..1), ``dc`` MULTIPLIES chroma
    (clamped >=0), ``dh`` is ADDED to hue in degrees (wrapped). OKLCH is
    perceptually uniform, so hue holds while lightness/chroma move — the
    right space for deriving an in-family tint from one accent without the
    hue drifting. Gamut-clamped per channel on return.
    """
    lightness, chroma, hue = rgb_to_oklch(*hex_to_rgb(hex_color))
    r, g, b = oklch_to_rgb(
        max(0.0, min(1.0, lightness + dl)),
        max(0.0, chroma * dc),
        (hue + dh) % 360.0,
    )
    return rgb_to_hex(r, g, b)


_CSS_RGB_RE = re.compile(r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([0-9.]+)\s*)?\)$")


def parse_css_rgb(value: str) -> tuple[int, int, int, float] | None:
    """``rgb()``/``rgba()`` to ``(r, g, b, alpha)``, or None when unparseable.

    Channels outside 0-255 and alpha outside 0-1 return None — an out-of-gamut
    declaration is not a color anything can render.
    """
    match = _CSS_RGB_RE.match(value.strip())
    if not match:
        return None
    r, g, b = (int(match.group(i)) for i in (1, 2, 3))
    if any(channel > 255 for channel in (r, g, b)):
        return None
    alpha = 1.0 if match.group(4) is None else float(match.group(4))
    if not 0.0 <= alpha <= 1.0:
        return None
    return r, g, b, alpha


def flatten_to_hex(value: str, backdrop: str) -> str | None:
    """Resolve a declared color to the opaque hex a reader actually sees.

    Hex passes through; ``rgb()``/``rgba()`` composites over ``backdrop``
    (source-over, the compositing every renderer performs). Returns None when
    the value is not a color at all — callers must fail closed rather than
    treat an unresolvable color as absent, which is how a translucent surface
    used to skip its WCAG pair entirely.
    """
    text = value.strip()
    if len(text.lstrip("#")) == 6 and text.startswith("#"):
        try:
            hex_to_rgb(text)
        except ValueError:
            return None
        return text.upper()
    parsed = parse_css_rgb(text)
    if parsed is None:
        return None
    r, g, b, alpha = parsed
    if alpha >= 1.0:
        return rgb_to_hex(r, g, b)
    try:
        br, bg, bb = hex_to_rgb(backdrop)
    except ValueError:
        return None
    return rgb_to_hex(*(round(c * alpha + bc * (1.0 - alpha)) for c, bc in ((r, br), (g, bg), (b, bb))))
