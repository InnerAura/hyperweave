"""CSS assembler -- builds the optimal CSS bundle for each artifact type."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from hyperweave.core.enums import FrameType, MotionId

if TYPE_CHECKING:
    from hyperweave.core.models import ResolvedArtifact

# Frame types that use badge/strip state machine + status indicator animations
_STATEFUL_FRAMES: frozenset[str] = frozenset({FrameType.BADGE, FrameType.STRIP})

# Frame types that use bridge hw-* class mappings
_BRIDGE_FRAMES: frozenset[str] = frozenset({FrameType.BADGE, FrameType.STRIP, FrameType.BANNER, FrameType.ICON})

# Telemetry frame types — need tool-class + extra ink variables
_TELEMETRY_FRAMES: frozenset[str] = frozenset({FrameType.RECEIPT, FrameType.RHYTHM_STRIP, FrameType.MASTER_CARD})

# Marquee frame types — need frame_fill, status colors, ink tiers
_MARQUEE_FRAMES: frozenset[str] = frozenset({
    FrameType.MARQUEE_HORIZONTAL, FrameType.MARQUEE_VERTICAL, FrameType.MARQUEE_COUNTER,
})


def assemble_css(resolved: ResolvedArtifact, frame_type: str = "") -> dict[str, str]:
    """Assemble frame-aware CSS for an artifact.

    Only includes CSS layers that the specific frame type actually uses:
    - genome DNA variables → ALL frames
    - bridge classes → badge, strip, banner, icon
    - expression layer → badge, strip (full); banner (typography only)
    - status animations → badge, strip only
    - accessibility → ALL frames
    - motion CSS → only when motion != static
    """
    genome = resolved.genome
    if not frame_type:
        frame_type = resolved.frame_template.replace("frames/", "").replace(".svg.j2", "")
    motion_id = resolved.motion

    css: dict[str, str] = {
        "genome": genome_to_css(genome, frame_type),
        "accessibility": _load_css_file("accessibility.css"),
    }

    # Bridge classes — only for frames that use hw-* semantic classes
    if frame_type in _BRIDGE_FRAMES:
        css["bridge"] = _load_css_file("bridge.css")
    else:
        css["bridge"] = ""

    # Expression layer — badge/strip get full; others get nothing
    # (badge state machine, living value thresholds, typography classes)
    if frame_type in _STATEFUL_FRAMES:
        css["expression"] = _load_css_file("expression.css")
    else:
        css["expression"] = ""

    # Status indicator animations — only badge/strip have .hw-logic-bit
    if frame_type in _STATEFUL_FRAMES:
        css["status"] = _load_css_file("status.css")
    else:
        css["status"] = ""

    # Telemetry utility classes — only for telemetry frames
    if frame_type in _TELEMETRY_FRAMES:
        css["telemetry"] = _load_css_file("telemetry.css")
    else:
        css["telemetry"] = ""

    # Motion CSS — only when a motion is active
    css["motion"] = _load_motion_css(motion_id) if motion_id != MotionId.STATIC else ""

    return css


def genome_to_css(genome: dict[str, Any], frame_type: str = "") -> str:
    """Convert genome JSON fields to CSS custom properties.

    Frame-aware: badge/strip-only variables are excluded from other frame types.
    """
    # Core variables — ALL frames need these
    mapping: list[tuple[str, str]] = [
        # Surfaces
        ("surface_0", "--dna-surface"),
        ("surface_1", "--dna-surface-alt"),
        ("surface_2", "--dna-surface-deep"),
        # Inks
        ("ink", "--dna-ink-primary"),
        ("ink_secondary", "--dna-ink-muted"),
        ("ink_on_accent", "--dna-ink-on-accent"),
        ("ink_bright", "--dna-ink-bright"),
        ("ink_sub", "--dna-ink-sub"),
        # Signals
        ("accent", "--dna-signal"),
        ("accent_complement", "--dna-signal-dim"),
        # Borders
        ("stroke", "--dna-border"),
        ("border_tint", "--dna-border-tint"),
        # Shadow / Glow
        ("shadow_color", "--dna-shadow-color"),
        ("shadow_opacity", "--dna-shadow-opacity"),
        ("glow", "--dna-glow"),
        # Geometry
        ("corner", "--dna-corner"),
        # Rhythm
        ("rhythm_base", "--dna-rhythm-base"),
        # Extended palette (used by templates)
        ("bg", "--dna-bg"),
        ("bg_alt", "--dna-bg-alt"),
        ("brand_text", "--dna-brand-text"),
    ]

    # Badge/strip-specific variables
    if frame_type in _STATEFUL_FRAMES:
        mapping.extend(
            [
                ("accent_signal", "--dna-status-passing-core"),
                ("accent_warning", "--dna-status-warning-core"),
                ("accent_error", "--dna-status-failing-core"),
                ("rhythm_slow", "--dna-rhythm-slow"),
                ("rhythm_fast", "--dna-rhythm-fast"),
                ("density", "--dna-density"),
                ("metric_text", "--dna-metric-text"),
                ("label_text", "--dna-label-text"),
                ("glyph_inner", "--dna-glyph-inner"),
                ("seam_gap", "--dna-seam-gap"),
                ("badge_value_text", "--dna-badge-value-text"),
                ("badge_pass_sep", "--dna-badge-pass-sep"),
                ("badge_pass_core", "--dna-badge-pass-core"),
                ("badge_warn_color", "--dna-badge-warn-color"),
                ("material_specular", "--dna-material-specular"),
                ("material_roughness", "--dna-material-roughness"),
            ]
        )
    elif frame_type in ("banner",):
        # Banner needs status colors for the indicator + rhythm
        mapping.extend(
            [
                ("accent_signal", "--dna-status-passing-core"),
                ("rhythm_slow", "--dna-rhythm-slow"),
                ("metric_text", "--dna-metric-text"),
                ("label_text", "--dna-label-text"),
            ]
        )
    elif frame_type in _MARQUEE_FRAMES:
        # Marquees need frame fill, status colors (vertical feed), ink tiers
        mapping.extend(
            [
                ("frame_fill", "--dna-frame-fill"),
                ("accent_signal", "--dna-status-passing-core"),
                ("accent_warning", "--dna-status-warning-core"),
                ("accent_error", "--dna-status-failing-core"),
                ("ink_secondary", "--dna-ink-secondary"),
                ("ink_on_accent", "--dna-ink-on-accent"),
                ("label_text", "--dna-label-text"),
            ]
        )
    elif frame_type in _TELEMETRY_FRAMES:
        # Telemetry frames need tool-class colors, status colors, and extra ink tiers
        mapping.extend(
            [
                ("accent_signal", "--dna-status-passing-core"),
                ("accent_warning", "--dna-status-warning-core"),
                ("accent_error", "--dna-status-failing-core"),
                ("ink_sub", "--dna-ink-tertiary"),
                ("label_text", "--dna-ink-ghost"),
                ("border_tint", "--dna-border-div"),
                ("tool_explore", "--dna-tool-explore"),
                ("tool_execute", "--dna-tool-execute"),
                ("tool_mutate", "--dna-tool-mutate"),
                ("tool_coordinate", "--dna-tool-coordinate"),
                ("tool_reflect", "--dna-tool-reflect"),
            ]
        )

    font_mapping: list[tuple[str, str]] = [
        ("font_display", "--dna-font-display"),
        ("font_mono", "--dna-font-mono"),
    ]

    lines = ["svg, :root {"]

    for field, prop in mapping:
        val = genome.get(field)
        if val:  # skip empty/None — lets CSS var() fallbacks activate
            lines.append(f"  {prop}: {val};")

    for field, prop in font_mapping:
        val = genome.get(field)
        if val:  # skip empty — lets CSS var() fallbacks activate
            lines.append(f"  {prop}: {val};")

    if "sep" not in genome and "stroke" in genome:
        lines.append(f"  --dna-sep: {genome['stroke']};")

    if "status_delta_positive" not in genome:
        lines.append("  --dna-status-delta-positive: #22C55E;")
    if "status_delta_negative" not in genome:
        lines.append("  --dna-status-delta-negative: #DC2626;")

    lines.append("}")

    # Light mode overrides
    light = genome.get("light_mode")
    if light and isinstance(light, dict):
        lm_map: list[tuple[str, str]] = [
            ("surface", "--dna-surface"),
            ("surface", "--dna-surface-top"),
            ("surface_alt", "--dna-surface-alt"),
            ("surface_deep", "--dna-surface-deep"),
            ("surface", "--dna-bg"),
            ("surface_alt", "--dna-bg-alt"),
            ("ink", "--dna-ink"),
            ("ink", "--dna-ink-primary"),
            ("ink", "--dna-ink-dark"),
            ("ink_muted", "--dna-ink-muted"),
            ("ink_muted", "--dna-ink-sub"),
            ("ink_ghost", "--dna-ink-ghost"),
            ("border", "--dna-border"),
            ("border", "--dna-border-div"),
            ("sep", "--dna-sep"),
        ]
        lines.append("@media (prefers-color-scheme: light) {")
        lines.append("  svg {")
        for field, prop in lm_map:
            val = light.get(field)
            if val is not None:
                lines.append(f"    {prop}: {val};")
        lines.append("  }")
        lines.append("}")

    return "\n".join(lines)


def _load_css_file(filename: str) -> str:
    css_path = _css_dir() / filename
    if css_path.exists():
        return css_path.read_text()
    return f"/* {filename} not found */"


def _load_motion_css(motion_id: str) -> str:
    try:
        from hyperweave.render.motion import get_motion_css

        compatible: list[str] = []
        return get_motion_css(motion_id, compatible)
    except (ImportError, Exception):
        return ""


def _css_dir() -> Path:
    try:
        from hyperweave.config.settings import get_settings

        return get_settings().data_dir / "css"
    except (ImportError, Exception):
        return Path(__file__).parent.parent / "data" / "css"
