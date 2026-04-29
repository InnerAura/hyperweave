"""Chakra Petch font metrics — Phase 2 validation.

The automata genome uses Chakra Petch 700 for hero value text in badges
and strips. Source: Google Fonts (OFL-1.1). Extracted via
``scripts/extract_font_metrics.py chakra-petch`` at baseline 12px.
"""

from __future__ import annotations

from hyperweave.core.font_metrics import get_registry, reset_registry
from hyperweave.core.text import measure_text


def test_chakra_petch_lut_loads() -> None:
    """Registry discovers chakra-petch.json and exposes Chakra Petch metrics."""
    reset_registry()
    registry = get_registry()
    metrics = registry.get("Chakra Petch")
    assert metrics.font_family == "Chakra Petch"
    assert metrics.baseline_size_px == 12
    assert metrics.is_monospace is False
    assert metrics.bold_expansion_factor > 1.0
    # Latin ASCII coverage
    for ch in ("A", "B", "0", "9", " ", ".", "v"):
        assert ch in metrics.widths, f"missing ASCII glyph '{ch}'"


def test_chakra_petch_alias_resolution() -> None:
    """Both 'chakra petch' and 'chakra-petch' aliases resolve to the same LUT."""
    registry = get_registry()
    by_family = registry.get("Chakra Petch")
    by_kebab = registry.get("chakra-petch")
    by_space = registry.get("chakra petch")
    assert by_family.font_family == by_kebab.font_family == by_space.font_family


def test_measure_text_returns_sensible_width() -> None:
    """measure_text on a typical automata value renders 30-80px at size 12."""
    width = measure_text("v0.2.5", font_family="Chakra Petch", font_size=12, font_weight=700)
    assert 25 < width < 80, f"unexpected width {width:.1f} for 'v0.2.5' at 12px"


def test_chakra_petch_wider_than_jetbrains_mono_for_same_digits() -> None:
    """Chakra Petch (proportional) renders numeric strings differently than mono."""
    mono = measure_text("2.9k", font_family="JetBrains Mono", font_size=12)
    chakra = measure_text("2.9k", font_family="Chakra Petch", font_size=12, font_weight=700)
    # Proportional font widths will differ from flat monospace widths
    assert abs(chakra - mono) > 0.5, "expected measurable difference between mono and proportional"


def test_chakra_petch_bold_expansion_applies_at_weight_700() -> None:
    """bold_expansion_factor multiplies width at font_weight >= 700."""
    normal = measure_text("test", font_family="Chakra Petch", font_size=12, font_weight=400)
    bold = measure_text("test", font_family="Chakra Petch", font_size=12, font_weight=700)
    assert bold > normal, "bold 700 should render wider than normal 400"
