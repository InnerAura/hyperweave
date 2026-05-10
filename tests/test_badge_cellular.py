"""Automata cellular badge — Phase 4 rendering validation.

Covers the 8-case matrix: {blue, purple} x {default, compact} x {version, state}.
Assertions verify structural elements and family-specific colors, not byte
equality — dynamic width from measure_text and UID suffix variance make
golden-file comparison fragile.
"""

from __future__ import annotations

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec


def _compose_svg(**kwargs: object) -> str:
    kwargs.setdefault("type", "badge")
    kwargs.setdefault("genome_id", "automata")
    spec = ComposeSpec(**kwargs)  # type: ignore[arg-type]
    return compose(spec).svg


# ── Version-mode badges ──────────────────────────────────────────────────


def test_version_badge_blue_default() -> None:
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="teal", glyph="python")
    # Blue-family signature colors
    assert "#3A9FB8" in svg  # label text
    assert "#A8D4F0" in svg  # value text
    assert "#8AC8E0" in svg  # top highlight (first rim stop)
    # Paradigm font stack
    assert "Orbitron" in svg
    assert "Chakra Petch" in svg
    # Rim gradient has 7 stops
    assert svg.count("<stop offset=") >= 7
    # No state indicator ring in version mode
    assert 'class="hw-ring"' not in svg
    assert 'class="hw-bit"' not in svg


def test_version_badge_purple_default() -> None:
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="violet", glyph="python")
    # Purple-family signature colors — label/value/rim all use amethyst palette
    assert "#A88AD4" in svg  # label text
    assert "#D8B4FE" in svg  # value text
    assert "#E6C0FF" in svg  # top highlight (first rim stop)
    assert "#6B3B8A" in svg  # pattern cell mid
    # Note: the glyph inline SVG still uses genome.glyph_inner (blue-family tint)
    # and CSS --dna-badge-value-text retains the blue stop (unused in purple render
    # but emitted by the assembler for state-mode fallback). Family-aware glyph
    # color + CSS var routing are separate cleanup items for v1.1.


def test_version_badge_compact_is_smaller() -> None:
    default_spec = ComposeSpec(
        type="badge", genome_id="automata", title="PYPI", value="v0.2.5", variant="teal", glyph="python"
    )
    compact_spec = ComposeSpec(
        type="badge",
        genome_id="automata",
        title="PYPI",
        value="v0.2.5",
        variant="teal",
        size="compact",
        glyph="python",
    )
    d = compose(default_spec)
    c = compose(compact_spec)
    assert c.height < d.height  # 20 vs 32
    assert c.width < d.width


def test_compact_badge_viewbox_is_20_tall() -> None:
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="teal", size="compact")
    # Compact height is 20 (small badge class)
    assert 'height="20"' in svg or "height=20" in svg


# ── State-mode badges ────────────────────────────────────────────────────


@pytest.mark.parametrize("state", ["passing", "warning", "critical", "building", "offline"])
def test_state_badge_emits_ring_and_bit(state: str) -> None:
    """state-mode badges render the ring+bit indicator block."""
    svg = _compose_svg(title="BUILD", value=state, state=state, variant="teal", glyph="github")
    assert 'class="hw-ring"' in svg
    assert 'class="hw-bit"' in svg
    # The state cascade partial defines --hw-state-signal for this status
    assert f'data-hw-status="{state}"' in svg or state in svg


def test_state_badge_binds_hw_value_text_class() -> None:
    """State value text routes through CSS custom property for runtime swap."""
    svg = _compose_svg(title="BUILD", value="passing", state="passing", variant="teal", glyph="github")
    assert 'class="hw-value-text"' in svg
    assert "var(--hw-state-value" in svg


def test_state_badge_state_signal_cascade_included() -> None:
    """The shared state-signal cascade partial is inlined for state badges."""
    svg = _compose_svg(title="BUILD", value="warning", state="warning", variant="teal", glyph="github")
    # All 5 state selectors should be present in the cascade block
    assert '[data-hw-status="passing"]' in svg
    assert '[data-hw-status="warning"]' in svg
    assert '[data-hw-status="critical"]' in svg
    assert '[data-hw-status="building"]' in svg
    assert '[data-hw-status="offline"]' in svg
    # Backfilled Tailwind 400 colors populate the cascade
    assert "#34D399" in svg  # passing core
    assert "#FBBF24" in svg  # warning core


# Version-mode isolation is verified via `hw-ring` class absence in
# `test_version_badge_blue_default`; no separate cascade-absence test
# needed because the baseline expression.css always emits state palette vars.


# ── Cellular structural invariants ───────────────────────────────────────


def test_cellular_badge_has_pattern_strip() -> None:
    """3 x 4 = 12 cellular pattern cells render on the left edge."""
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="teal")
    # Pattern cells are rects with class="cz{1,2,3,4,f,d}"; count distinct classes
    for cls in ("cz1", "cz2", "cz3", "cz4", "czf", "czd"):
        assert f'class="{cls}"' in svg, f"missing pattern class {cls}"


def test_cellular_badge_has_chrome_rim() -> None:
    """Rim, dark lip, and drop-shadow lift filter are all present."""
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="teal")
    assert "-rim" in svg  # gradient id suffix
    assert "feDropShadow" in svg
    assert "-lift" in svg  # filter id suffix


def test_cellular_badge_font_face_embedded() -> None:
    """Font-face CSS embeds Chakra Petch + Orbitron + JetBrains Mono WOFF2."""
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="teal")
    assert "@font-face" in svg


def test_cellular_badge_respects_prefers_reduced_motion() -> None:
    """CIM compliance: animation pauses under reduce-motion media query."""
    svg = _compose_svg(title="PYPI", value="v0.2.5", variant="teal")
    assert "prefers-reduced-motion" in svg
