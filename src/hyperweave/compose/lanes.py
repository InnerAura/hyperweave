"""Policy lane enforcement -- validates compose context against regime constraints."""

from __future__ import annotations

import logging
from typing import Any

from hyperweave.core.enums import MotionId, Regime

logger = logging.getLogger(__name__)

# CIM-compliant animated properties
CIM_SAFE_PROPERTIES: frozenset[str] = frozenset(
    {
        "transform",
        "opacity",
        "filter",
        "mix-blend-mode",
        "clip-path",
    }
)

# Properties that may only use CSS transitions, not keyframe animations
CIM_TRANSITION_ONLY: frozenset[str] = frozenset(
    {
        "fill",
        "stroke",
    }
)

# Properties that must NEVER be animated
CIM_NEVER: frozenset[str] = frozenset(
    {
        "cx",
        "cy",
        "r",
        "d",
        "width",
        "height",
        "x",
        "y",
        "rx",
        "ry",
        "viewBox",
    }
)


def enforce(context: dict[str, Any], regime: Regime) -> dict[str, Any]:
    """Enforce policy lane constraints on the compose context."""
    if regime == Regime.UNGOVERNED:
        return context

    violations: list[str] = []

    # Check motion CIM compliance
    motion = context.get("motion", MotionId.STATIC)
    if motion != MotionId.STATIC:
        motion_violations = _check_motion_cim(motion)
        if motion_violations:
            if regime == Regime.NORMAL:
                # Downgrade to static
                logger.warning(
                    "Motion '%s' violates CIM in normal regime: %s. Falling back to static.",
                    motion,
                    motion_violations,
                )
                context["motion"] = MotionId.STATIC
                context["motion_css"] = ""
                violations.extend(motion_violations)
            elif regime == Regime.PERMISSIVE:
                # Warn but allow
                logger.info(
                    "Motion '%s' has CIM violations in permissive regime: %s",
                    motion,
                    motion_violations,
                )

    # Check contrast ratios (normal regime: WCAG AA ≥ 4.5:1)
    if regime == Regime.NORMAL:
        _check_contrast(context, violations)

    # Record violations in context for metadata
    if violations:
        context["lane_violations"] = violations
        context["lane_corrected"] = regime == Regime.NORMAL

    return context


def _check_motion_cim(motion_id: str) -> list[str]:
    try:
        from hyperweave.config.loader import get_loader

        loader = get_loader()
        motion_config = loader.motions.get(motion_id)
        if not motion_config:
            return []

        animated = set(motion_config.get("animated_properties", []))
        cim_compliant = motion_config.get("cim_compliant", True)

        if cim_compliant:
            return []

        violations: list[str] = []
        for prop in animated:
            if prop in CIM_NEVER:
                violations.append(f"Animated '{prop}' is NEVER allowed in CIM")
            elif prop not in CIM_SAFE_PROPERTIES and prop not in CIM_TRANSITION_ONLY:
                violations.append(f"Animated '{prop}' is not CIM-safe")

        return violations
    except (ImportError, Exception):
        return []


def _check_contrast(context: dict[str, Any], violations: list[str]) -> None:
    """WCAG AA contrast check against raw genome color pairs."""
    try:
        from hyperweave.core.color import contrast_ratio

        genome = context.get("_genome_raw", {})
        if not genome:
            return

        # Color pairs to check: (foreground_key, background_key, min_ratio, label)
        pairs = [
            ("ink", "surface_0", 4.5, "ink vs surface"),
            ("ink_secondary", "surface_0", 3.0, "ink_secondary vs surface"),
            ("accent", "surface_0", 3.0, "accent vs surface"),
            ("accent_signal", "surface_2", 3.0, "status-passing vs surface-deep"),
            ("accent_warning", "surface_2", 3.0, "status-warning vs surface-deep"),
            ("accent_error", "surface_2", 3.0, "status-failing vs surface-deep"),
        ]
        for fg_key, bg_key, threshold, label in pairs:
            fg = genome.get(fg_key, "")
            bg = genome.get(bg_key, "")
            if not fg or not bg or not fg.startswith("#") or not bg.startswith("#"):
                continue
            try:
                ratio = contrast_ratio(fg, bg)
                if ratio < threshold:
                    violations.append(f"WCAG: {label} contrast {ratio:.1f}:1 < {threshold}:1 ({fg} on {bg})")
            except (ValueError, TypeError):
                continue
    except ImportError:
        pass


def validate_regime(regime: str) -> str:
    """Validate and normalize regime string."""
    known = {Regime.NORMAL, Regime.PERMISSIVE, Regime.UNGOVERNED}
    if regime in known:
        return regime

    # Check for custom policy file
    try:
        from hyperweave.config.loader import get_loader

        loader = get_loader()
        if regime in loader.policies:
            return regime
    except (ImportError, Exception):
        pass

    logger.warning("Unknown regime '%s', falling back to 'normal'.", regime)
    return Regime.NORMAL
