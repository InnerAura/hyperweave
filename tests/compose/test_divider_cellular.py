"""dissolve divider variant — Phase 9 rendering validation.

The divider is the one automata artifact that sacrifices motion for
renderer independence (feedback_static_rendering_renderer_independence).
It carries ZERO CSS animation, baked composited colors, and per-rect
opacity for the dissolve effect — so it renders identically in GitHub
Camo proxy, VS Code preview, Finder Quick Look, and any static renderer.
"""

from __future__ import annotations

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec


def _compose_divider(*, variant: str = "teal", pair: str = "violet") -> str:
    """Default to the legacy teal+violet bifamily for paired-divider tests."""
    spec = ComposeSpec(
        type="divider",
        genome_id="automata",
        divider_variant="dissolve",
        variant=variant,
        pair=pair,
    )
    return compose(spec).svg


def test_dissolve_viewbox_is_800_by_28() -> None:
    result = compose(ComposeSpec(type="divider", genome_id="automata", divider_variant="dissolve"))
    assert result.width == 800
    assert result.height == 28


def test_dissolve_renders_variant_bifamily_bridge_palette() -> None:
    """Paired ?variant=teal&pair=violet emits a 4-color bridge synthesized
    from each tone's cellular_cells[0:2]. Pre-v0.3.0-grammar this came from
    a hand-curated variant_pairs[violet-teal].bridge dict; post-grammar the
    same shape is derived from variant_tones at request time."""
    svg = _compose_divider()
    # Teal bridge terminal — from variant_tones.teal.cellular_cells[0:2]
    assert "#1E849A" in svg
    assert "#104052" in svg
    # Violet bridge terminal — from variant_tones.violet.cellular_cells[0:2]
    assert "#6B3B8A" in svg
    assert "#331A4A" in svg


def test_dissolve_has_no_cellular_pulse_classes() -> None:
    """Static-baked divider deliberately omits the cellular pulse classes.

    Baseline expression.css emits animations for state indicators, but the
    divider content itself uses NO cz*/cb*/si* classes and NO <animate>
    elements. The dissolve effect comes from per-rect opacity attributes."""
    svg = _compose_divider()
    for cls in ("cz1", "cz2", "cz3", "cz4", "cb1", "cb2", "si1", "si2"):
        assert f'class="{cls}"' not in svg
    assert "<animate " not in svg
    assert "<animateTransform" not in svg


def test_dissolve_uses_per_rect_opacity_cascade() -> None:
    """Dissolve = per-rect opacity, not CSS opacity animation."""
    svg = _compose_divider()
    # Scatter rects have opacity attributes ranging from 0.2 to 0.85
    assert 'opacity="0.85"' in svg
    assert 'opacity="0.7"' in svg
    assert 'opacity="0.55"' in svg
    assert 'opacity="0.2"' in svg


def test_dissolve_terminals_are_full_opacity() -> None:
    """Corner terminals are 4x2 solid cell blocks at full opacity."""
    svg = _compose_divider()
    # Left terminal cells land at x=0, x=12, x=24, x=36 — no opacity attr → 1.0
    # Synthesized bridge primary_main / primary_alt = teal cellular_cells[0:2].
    assert 'x="0" y="2" width="12" height="12" fill="#1E849A"' in svg
    assert 'x="12" y="2" width="12" height="12" fill="#104052"' in svg


def test_dissolve_existing_variants_still_work() -> None:
    """Regression: adding dissolve didn't break the other 5 variants."""
    for variant in ("block", "current", "takeoff", "void", "zeropoint"):
        spec = ComposeSpec(type="divider", genome_id="brutalist", divider_variant=variant)
        result = compose(spec)
        assert result.width > 0
        assert result.height > 0
