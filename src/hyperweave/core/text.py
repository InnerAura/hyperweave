"""Text width measurement backed by per-font LUTs.

Deterministic width estimation for the shipped supported ASCII glyph set,
using per-codepoint advance widths scaled linearly by font size.
Kerning ignored. Ligatures ignored. Non-ASCII codepoints fall back to the
font's declared ``fallback_width``. Unknown font families fall back to
Inter metrics with a one-shot warning log per family — never to
genome-specific multipliers.

Add a new font LUT by running::

    uv run python scripts/extract_font_metrics.py <slug>

which writes ``src/hyperweave/data/font-metrics/<slug>.json``. The
:class:`hyperweave.core.font_metrics.FontRegistry` picks it up on the
next process start (or after :func:`hyperweave.core.font_metrics.reset_registry`).
"""

from __future__ import annotations

from hyperweave.core.font_metrics import get_registry


def measure_text(
    text: str,
    *,
    font_family: str = "Inter",
    font_size: float = 11.0,
    font_weight: int = 400,
    letter_spacing_em: float = 0.0,
) -> float:
    """Estimate the rendered width of ``text`` in pixels.

    The text measurement pipeline:

    1. Resolve ``font_family`` to a :class:`FontMetrics` LUT via the
       :class:`FontRegistry` (falls back to Inter + one-shot warning on
       unknown families).
    2. For monospace fonts, width = ``len(text) * char_width_px``
       scaled linearly by ``font_size / baseline_size_px``.
       For proportional fonts, sum per-codepoint advance widths (tenths
       of pixels at ``baseline_size_px``), divide by 10, scale by size.
    3. Apply ``bold_expansion_factor`` when ``font_weight >= 700`` for
       non-monospace fonts (true monospace has no bold width change).
    4. Absorb letter-spacing: add ``max(0, len(text) - 1) *
       font_size * letter_spacing_em`` so callers don't repeat the
       arithmetic themselves.
    """
    metrics = get_registry().get(font_family)
    baseline = metrics.baseline_size_px

    if metrics.is_monospace:
        base_px = len(text) * metrics.char_width_px * (font_size / baseline)
    else:
        total_tenths = 0.0
        for ch in text:
            total_tenths += metrics.widths.get(ch, metrics.fallback_width)
        base_px = (total_tenths / 10.0) * (font_size / baseline)
        if font_weight >= 700:
            base_px *= metrics.bold_expansion_factor

    if text and letter_spacing_em:
        base_px += max(0, len(text) - 1) * font_size * letter_spacing_em

    return base_px
