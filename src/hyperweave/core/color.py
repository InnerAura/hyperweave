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
