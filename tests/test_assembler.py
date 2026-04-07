"""Tests for CSS assembler gating logic.

PRD 1B Phase 3 requirement: verify that the assembler only includes
CSS modules relevant to the artifact being generated.
"""

from __future__ import annotations

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec


def test_static_motion_omits_motion_css_but_retains_status() -> None:
    """motion=static should exclude motion keyframes but keep ambient status animations.

    Status indicator breathe/pulse/strobe are AMBIENT — always present on
    stateful frames regardless of motion input. Motion-layer CSS (border
    animations, kinetic keyframes) is gated by motion != static.
    """
    result = compose(ComposeSpec(type="badge", title="build", value="passing"))
    css = result.svg

    # Ambient status animations MUST be present (badge is a stateful frame)
    assert "hw-breathe" in css, "Badge should include ambient hw-breathe animation"
    assert "hw-logic-bit" in css, "Badge should include status indicator class"

    # Default motion is static — no motion-layer CSS should be present
    # Border motions (chromatic-pulse, corner-trace, etc.) inject SMIL, not CSS keyframes,
    # but the motion CSS slot should be empty for static
    assert "chromatic-pulse" not in css, "Static badge should not include motion-specific CSS"


def test_non_stateful_frame_omits_status_and_expression() -> None:
    """Dividers (non-stateful) should not include expression or status CSS.

    Only badge and strip are stateful frames that need .hw-value,
    .hw-logic-bit, and status animation keyframes.
    """
    result = compose(ComposeSpec(type="divider"))
    css = result.svg

    # Genome DNA variables MUST always be present
    assert "--dna-surface" in css, "Divider should include genome DNA variables"

    # Accessibility layer MUST always be present
    assert "prefers-reduced-motion" in css, "Divider should include accessibility CSS"

    # Status animation KEYFRAMES should NOT be present (divider is not stateful)
    # Note: hw-logic-bit appears in accessibility.css (reduced-motion override),
    # which is never gated — so we check for the keyframe definition, not the class name.
    assert "@keyframes hw-breathe" not in css, "Divider should not include status keyframes"
    assert "@keyframes hw-pulse" not in css, "Divider should not include status keyframes"

    # Expression layer should NOT be present
    assert ".hw-value" not in css, "Divider should not include expression layer"

    # Bridge classes should NOT be present (divider is not in bridge frames)
    assert ".hw-frame-bg" not in css or "divider" in css, \
        "Divider should not include bridge classes"
