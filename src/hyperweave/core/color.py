"""Color math utilities -- ONE canonical copy."""

from __future__ import annotations


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
    l_, m_, s_ = lc ** (1 / 3), mc ** (1 / 3), sc ** (1 / 3)
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
    return tuple(max(0, min(255, round(_linear_to_srgb(v) * 255))) for v in (lr, lg, lb))  # type: ignore[return-value]
