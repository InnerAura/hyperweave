"""Inter font metrics validation."""

from __future__ import annotations

from hyperweave.core.font_metrics import get_registry, reset_registry
from hyperweave.core.text import measure_text, measure_text_ink_width, measure_text_trailing_bearing


def test_inter_lut_has_bearings_and_weight_maps() -> None:
    """Inter is the registry fallback, so it must have real ink metrics."""
    reset_registry()
    metrics = get_registry().get("Inter")
    assert metrics.font_family == "Inter"
    assert metrics.baseline_size_px == 11
    assert metrics.is_monospace is False
    assert metrics.bearings
    assert sorted(metrics.widths_by_weight) == ["400", "700", "800", "900"]
    assert sorted(metrics.bearings_by_weight) == ["400", "700", "800", "900"]


def test_inter_ink_width_does_not_fall_back_to_advance_width() -> None:
    """Inter ink-width correction uses extracted bearings."""
    text = "HyperWeave"
    advance = measure_text(text, font_family="Inter", font_size=13, font_weight=700)
    ink = measure_text_ink_width(text, font_family="Inter", font_size=13, font_weight=700)
    trailing = measure_text_trailing_bearing(text, font_family="Inter", font_size=13, font_weight=700)

    assert ink < advance
    assert trailing > 0
