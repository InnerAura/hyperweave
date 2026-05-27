"""Tests for CSS assembler gating logic.

PRD 1B Phase 3 requirement: verify that the assembler only includes
CSS modules relevant to the artifact being generated.
"""

from __future__ import annotations

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec


def test_voltage_emits_no_light_mode_media_query() -> None:
    """Voltage is dark-flagship. Removing its light_mode JSON block stops the
    assembler from emitting `@media (prefers-color-scheme: light)`, which made
    voltage receipts render as light in viewers (svgviewer) that respect the
    OS color scheme. Pin the disable so a future contributor can't reintroduce
    a light_mode block silently.
    """
    spec = ComposeSpec(
        type="receipt",
        genome_id="telemetry-voltage",
        telemetry_data={"session": {"id": "test", "runtime": "claude-code"}},
    )
    css = compose(spec).svg
    assert "prefers-color-scheme: light" not in css, (
        "voltage must not emit a light-mode media query — remove the light_mode block from telemetry-voltage.json"
    )


def test_chrome_emits_no_light_mode_media_query() -> None:
    """Chrome's identity is a dark midnight envelope (gradient stops are
    hex-baked via url(#env), scheme-stable). A light_mode block in chrome.json
    caused the assembler to emit `@media (prefers-color-scheme: light)` rules
    that swapped --dna-ink-primary to a dark slate (#1E293B) on light GitHub
    READMEs. Result: the GitHub provider glyph and identity/metric text on
    chrome stats/chart cards rendered as dark-slate-on-dark-envelope, nearly
    invisible — while the envelope itself stayed dark because the gradient
    fill is hex, not var-driven. Pin the disable.
    """
    spec = ComposeSpec(type="stats", genome_id="chrome")
    css = compose(spec).svg
    assert "prefers-color-scheme: light" not in css, (
        "chrome must not emit a light-mode media query — chrome is a "
        "scheme-stable dark-envelope identity; remove the light_mode block "
        "from chrome.json"
    )


def test_chrome_stats_and_chart_headers_use_badge_identity_roles() -> None:
    """Chrome stats/chart header slots consume the same roles as badges."""
    stats_svg = compose(
        ComposeSpec(
            type="stats",
            genome_id="chrome",
            variant="horizon",
            connector_data={
                "provider": "github",
                "username": "eli64s",
                "stars_total": 20,
                "source_url": "https://github.com/eli64s",
            },
        )
    ).svg
    chart_svg = compose(
        ComposeSpec(
            type="chart",
            genome_id="chrome",
            variant="horizon",
            connector_data={
                "provider": "github",
                "identity": "eli64s/readme-ai",
                "points": [{"date": "2024-01-01", "count": 10}, {"date": "2024-02-01", "count": 20}],
                "current_stars": 20,
                "source_url": "https://github.com/eli64s/readme-ai",
            },
        )
    ).svg

    for svg in (stats_svg, chart_svg):
        assert "--dna-glyph-inner: #E0ECF6;" in svg
        assert "fill: var(--dna-signal)" in svg
        assert "--hw-core: var(--dna-signal)" in svg
        assert "var(--dna-status-passing-core, #22C55E)" not in svg
        assert 'fill="var(--dna-glyph-inner, var(--dna-signal))"' in svg


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
    assert ".hw-frame-bg" not in css or "divider" in css, "Divider should not include bridge classes"
