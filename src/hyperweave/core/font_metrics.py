"""Per-font character-width LUTs for deterministic text measurement.

    Contract
    --------
    Deterministic width estimation for the shipped supported ASCII glyph set,
    using per-codepoint advance widths scaled linearly by font size.
    Kerning ignored. Ligatures ignored. Non-ASCII codepoints fall back to the
    font's declared ``fallback_width``. Unknown font families fall back to
    Inter metrics with a one-shot warning log per family — never to
    genome-specific multipliers.

LUT JSON files live at ``src/hyperweave/data/font-metrics/{slug}.json``
and are loaded by :func:`hyperweave.config.loader.load_font_metrics`.
Regenerate them by running ``uv run python scripts/extract_font_metrics.py``.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

from hyperweave.core.models import FrozenModel

_logger = logging.getLogger(__name__)

# Module-level memo of font families we've already warned about, to
# keep the warning one-shot per family per process.
_WARNED_UNKNOWN: set[str] = set()


class FontMetrics(FrozenModel):
    """Per-font character-width lookup table.

    One instance per font family, loaded from a JSON file under
    ``data/font-metrics/``. Monospace fonts skip the ``widths`` dict
    and use ``char_width_px`` for all glyphs. Non-monospace fonts use
    the ``widths`` dict (tenths of pixels at ``baseline_size_px``) and
    fall through to ``fallback_width`` for unlisted codepoints.
    """

    font_family: str
    baseline_size_px: float
    units: str = "tenths_of_pixels"
    bold_expansion_factor: float = 1.07
    fallback_width: float = 60.0
    is_monospace: bool = False
    char_width_px: float = 0.0
    aliases: list[str] = Field(default_factory=list)
    widths: dict[str, int] = Field(default_factory=dict)


class FontRegistry:
    """Indexed map of ``FontMetrics`` with alias resolution and Inter fallback.

    Constructed once at startup from ``ConfigLoader.font_metrics``. Callers
    look up a font by its canonical family name or any declared alias; an
    unknown family returns the Inter LUT and logs a one-shot warning.
    """

    def __init__(self, metrics_by_slug: dict[str, dict[str, Any]]) -> None:
        self._by_family: dict[str, FontMetrics] = {}
        for raw in metrics_by_slug.values():
            fm = FontMetrics(**raw)
            self._by_family[fm.font_family.lower()] = fm
            for alias in fm.aliases:
                self._by_family[alias.lower()] = fm
        self._fallback: FontMetrics | None = self._by_family.get("inter")

    def get(self, font_family: str) -> FontMetrics:
        """Resolve ``font_family`` to a ``FontMetrics``, falling back to Inter.

        Accepts either a bare family name ("Orbitron") or a CSS font-family
        string ("'Orbitron','Space Grotesk',sans-serif") — only the first
        comma-separated component is considered, quotes stripped.
        """
        key = font_family.split(",")[0].strip().strip("'\"").lower()
        metrics = self._by_family.get(key)
        if metrics is not None:
            return metrics
        if key not in _WARNED_UNKNOWN:
            _WARNED_UNKNOWN.add(key)
            _logger.warning(
                "Unknown font family '%s' — falling back to Inter metrics. "
                "Extract a LUT via scripts/extract_font_metrics.py to remove this warning.",
                key,
            )
        if self._fallback is None:
            raise RuntimeError(
                "FontRegistry has no Inter fallback — "
                "data/font-metrics/inter.json must exist and load before measure_text is called."
            )
        return self._fallback


_registry: FontRegistry | None = None


def get_registry() -> FontRegistry:
    """Return the process-wide FontRegistry, constructing it on first access."""
    global _registry
    if _registry is None:
        from hyperweave.config.registry import get_font_metrics

        _registry = FontRegistry(get_font_metrics())
    return _registry


def reset_registry() -> None:
    """Reset the registry + unknown-font warning cache. For tests."""
    global _registry
    _registry = None
    _WARNED_UNKNOWN.clear()
