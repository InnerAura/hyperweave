"""Shields.io-grade text width measurement."""

from __future__ import annotations

# Monospace character width at 11px (SF Mono / JetBrains Mono average).
_MONO_CHAR_WIDTH_11PX: float = 6.6

# Width table for Inter Regular at 11px, in tenths-of-pixels.
# Derived from font metrics extraction. Missing characters use the
# fallback width. This set covers ASCII printable + common symbols.
_INTER_11_WIDTHS: dict[str, int] = {
    " ": 29,
    "!": 30,
    '"': 41,
    "#": 67,
    "$": 58,
    "%": 76,
    "&": 72,
    "'": 23,
    "(": 33,
    ")": 33,
    "*": 49,
    "+": 58,
    ",": 26,
    "-": 38,
    ".": 27,
    "/": 38,
    "0": 62,
    "1": 47,
    "2": 56,
    "3": 57,
    "4": 62,
    "5": 58,
    "6": 60,
    "7": 55,
    "8": 61,
    "9": 60,
    ":": 26,
    ";": 26,
    "<": 58,
    "=": 58,
    ">": 58,
    "?": 49,
    "@": 92,
    "A": 67,
    "B": 65,
    "C": 66,
    "D": 71,
    "E": 58,
    "F": 55,
    "G": 71,
    "H": 72,
    "I": 27,
    "J": 46,
    "K": 64,
    "L": 55,
    "M": 85,
    "N": 72,
    "O": 74,
    "P": 62,
    "Q": 74,
    "R": 64,
    "S": 57,
    "T": 58,
    "U": 71,
    "V": 63,
    "W": 92,
    "X": 62,
    "Y": 59,
    "Z": 59,
    "[": 32,
    "\\": 38,
    "]": 32,
    "^": 55,
    "_": 48,
    "`": 38,
    "a": 57,
    "b": 61,
    "c": 51,
    "d": 61,
    "e": 57,
    "f": 35,
    "g": 61,
    "h": 60,
    "i": 26,
    "j": 26,
    "k": 56,
    "l": 26,
    "m": 91,
    "n": 60,
    "o": 60,
    "p": 61,
    "q": 61,
    "r": 38,
    "s": 49,
    "t": 38,
    "u": 60,
    "v": 53,
    "w": 79,
    "x": 53,
    "y": 53,
    "z": 49,
    "{": 36,
    "|": 27,
    "}": 36,
    "~": 58,
}

# Fallback width for characters not in the LUT (tenths of pixels)
_FALLBACK_WIDTH: int = 60

# Bold expansion factor (Inter Bold is roughly 7% wider than Regular)
_BOLD_FACTOR: float = 1.07

# Font size scaling (LUT is calibrated at 11px)
_LUT_FONT_SIZE: float = 11.0


def measure_text(
    text: str,
    font_family: str = "Inter",  # reserved for future font LUTs
    font_size: float = 11.0,
    bold: bool = False,
    monospace: bool = False,
) -> float:
    """Measure the rendered width of text in pixels.

    For monospace fonts, uses a fixed character width (bold does not
    change width in a true monospace face).
    """
    if monospace:
        return len(text) * _MONO_CHAR_WIDTH_11PX * (font_size / _LUT_FONT_SIZE)

    total_tenths = 0
    for ch in text:
        total_tenths += _INTER_11_WIDTHS.get(ch, _FALLBACK_WIDTH)

    width = total_tenths / 10.0

    # Scale for font size
    if font_size != _LUT_FONT_SIZE:
        width *= font_size / _LUT_FONT_SIZE

    # Apply bold expansion
    if bold:
        width *= _BOLD_FACTOR

    return width
