"""Motion registry -- loading, compatibility check, CSS generation."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

from hyperweave.core.enums import (
    BorderMotionId,
    MotionId,
    Regime,
)

# Loading (cached)


@functools.lru_cache(maxsize=4)
def _load_motions_cached(motions_dir: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    path = Path(motions_dir)

    if not path.exists():
        return result

    # Scan root + border/ subdirs (kinetic/ removed in v0.2.14 with banner)
    for yaml_file in sorted(path.glob("*.yaml")):
        with yaml_file.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data and "id" in data:
                result[data["id"]] = data

    sub = path / "border"
    if sub.is_dir():
        for yaml_file in sorted(sub.glob("*.yaml")):
            with yaml_file.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "id" in data:
                    result[data["id"]] = data

    return result


def load_motions(motions_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all motion configs from a directory."""
    return _load_motions_cached(str(motions_dir))


def get_motions_dir() -> Path:
    """Locate the motions data directory."""
    try:
        from hyperweave.config.settings import get_settings

        return get_settings().data_dir / "motions"
    except (ImportError, Exception):
        return Path(__file__).resolve().parent.parent / "data" / "motions"


# CSS retrieval


def get_motion_css(motion_id: str, genome_compatible: list[str]) -> str:
    """Get CSS keyframes + class rule for a motion primitive."""
    if motion_id == MotionId.STATIC:
        return ""

    try:
        motions = load_motions(get_motions_dir())
    except Exception:
        return ""

    config = motions.get(motion_id)
    if not config:
        return ""

    css: str = config.get("css", "")
    return css


# Validation


def validate_motion(
    motion_id: str,
    genome_compatible: list[str],
    regime: str = "normal",
) -> str:
    """Validate a motion is compatible with the genome and return a valid ID."""
    if motion_id == MotionId.STATIC:
        return MotionId.STATIC

    # Ungoverned allows everything
    if regime == Regime.UNGOVERNED:
        return motion_id

    # Check genome compatibility
    if genome_compatible and motion_id not in genome_compatible:
        return MotionId.STATIC

    return motion_id


def validate_motion_compat(
    motion_id: str,
    frame_type: str,
    regime: str = "normal",
) -> tuple[bool, str]:
    """Validate that a motion is compatible with a frame type."""
    if motion_id == MotionId.STATIC:
        return True, ""

    try:
        motions = load_motions(get_motions_dir())
    except Exception:
        if regime == Regime.UNGOVERNED:
            return True, "ungoverned: registry unavailable"
        return False, "motion registry unavailable"

    motion = motions.get(motion_id)
    if motion is None:
        if regime == Regime.UNGOVERNED:
            return True, "ungoverned: unknown motion allowed"
        return False, f"unknown motion: {motion_id}"

    applies_to = motion.get("applies_to") or motion.get("frames", [])
    if not applies_to:
        # No restriction -- applies to all frames
        return True, ""

    if frame_type in applies_to:
        return True, ""

    if regime in (Regime.PERMISSIVE, Regime.UNGOVERNED):
        return True, f"{regime}: {motion_id} not listed for {frame_type}"

    return (
        False,
        f"motion '{motion_id}' not compatible with frame '{frame_type}'. Allowed: {applies_to}",
    )


# CIM compliance


def is_cim_compliant(motion_id: str) -> bool:
    """Check if a motion uses only compositor-friendly properties."""
    if motion_id == MotionId.STATIC:
        return True
    try:
        motions = load_motions(get_motions_dir())
    except Exception:
        return False
    motion = motions.get(motion_id)
    return bool(motion.get("cim_compliant", False)) if motion else False


# Motion info


def get_motion_info(motion_id: str) -> dict[str, Any]:
    """Get metadata about a motion primitive."""
    try:
        motions = load_motions(get_motions_dir())
    except Exception:
        return {"id": motion_id, "name": motion_id, "cim_compliant": True}

    return motions.get(
        motion_id,
        {"id": motion_id, "name": motion_id, "cim_compliant": True},
    )


# Context builder for template injection


def build_motion_context(
    motion_id: str,
    frame_type: str,
    regime: str = "normal",
) -> dict[str, Any]:
    """Build template context entries for a motion."""
    valid, reason = validate_motion_compat(motion_id, frame_type, regime)
    resolved = motion_id if valid else "static"
    info = get_motion_info(resolved)

    return {
        "motion_id": resolved,
        "motion_css": get_motion_css(resolved, []),
        "motion_valid": valid,
        "motion_reason": reason,
        "motion_class": f"hw-motion-{resolved}" if resolved != MotionId.STATIC else "",
        "motion_category": info.get("category", "none"),
        "motion_cim_compliant": is_cim_compliant(resolved),
    }


# Introspection


def list_motions() -> list[dict[str, Any]]:
    """Return a summary list of all registered motions."""
    try:
        motions = load_motions(get_motions_dir())
    except Exception:
        return []
    return sorted(
        [
            {
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "category": m.get("category", "none"),
                "cim_compliant": m.get("cim_compliant", False),
                "applies_to": m.get("applies_to", m.get("frames", [])),
            }
            for m in motions.values()
        ],
        key=lambda m: m["id"],
    )


# ═══════════════════════════════════════════════════════════════════
# Border Motion Overlay — 5 SMIL motions for badge / strip / icon
# All SVG is produced by Jinja2 templates in templates/motions/border/.
# Python computes numeric layout values; templates produce SVG markup.
# ═══════════════════════════════════════════════════════════════════

_BORDER_TEMPLATES: frozenset[str] = frozenset(BorderMotionId)


def _render_motion_template(template_path: str, context: dict[str, Any]) -> str:
    """Render a motion template fragment and return the SVG string."""
    from hyperweave.render.templates import render_template

    return render_template(template_path, context)


def build_border_overlay(
    motion_id: str,
    uid: str,
    w: int,
    h: int,
    rx: float = 3.33,
    *,
    lp_w: int = 0,
    right_x: int = 0,
    seam_positions: list[int] | None = None,
) -> tuple[str, str]:
    """Build (defs_svg, overlay_svg) for a border SMIL motion.

    Renders the Jinja2 template for the given motion_id, passing computed
    numeric layout values as context.  The template sets ``defs`` and
    ``overlay`` Jinja2 variables which we extract from the rendered output.

    For rimrun, ``lp_w`` and ``right_x`` specify the badge panel
    geometry so runners trace seams rather than the outer perimeter.
    ``seam_positions`` provides all vertical divider x-coordinates for
    multi-seam strips so rimrun can zigzag through every metric divider.
    """
    if motion_id not in _BORDER_TEMPLATES:
        return "", ""

    # Compute layout values used across multiple border motions
    # Rounded-rect perimeter: subtract 8*rx for corner straights, add 2*pi*rx for arcs
    import math

    perim = int(2 * (w + h) - 8 * rx + 2 * math.pi * rx)
    context: dict[str, Any] = {
        "uid": uid,
        "w": w,
        "h": h,
        "rx": rx,
        "perim": perim,
        "lp_w": lp_w or (w // 2),
        "right_x": right_x or (w // 2 + 5),
        "seam_positions": seam_positions or [],
    }

    # Motion-specific computed values
    if motion_id == "corner-trace":
        vis = int(perim * 0.2)
        context.update(vis=vis, gap=perim - vis)

    elif motion_id == "dual-orbit":
        vis = int(perim * 0.15)
        context.update(vis=vis, gap=perim - vis, half=perim // 2)

    elif motion_id == "entanglement":
        seg = max(int(perim * 0.125), 4)
        half = perim // 2
        quarter = perim // 4
        context.update(
            dash=f"{seg} {seg} {seg} {seg}",
            half=half,
            quarter=quarter,
        )

    # The template uses {% set defs %} and {% set overlay %} blocks.
    # Since Jinja2 set-blocks are local to the template and don't appear
    # in render output, we use a marker-based extraction instead.
    # Re-render with explicit output of defs and overlay.
    return _extract_border_parts(motion_id, context)


def _extract_border_parts(
    motion_id: str,
    context: dict[str, Any],
) -> tuple[str, str]:
    """Render border template with defs/overlay extraction wrapper."""
    from hyperweave.render.templates import create_jinja_env

    env = create_jinja_env()
    # Load the motion template source and wrap it to output defs + overlay
    tpl_path = f"motions/border/{motion_id}.svg.j2"
    source = env.loader.get_source(env, tpl_path)[0]  # type: ignore[union-attr]

    # Build a wrapper template that includes the motion template and
    # outputs the defs/overlay set-blocks separated by a marker.
    marker = "<!-- __HW_BORDER_SPLIT__ -->"
    wrapper_source = source + f"\n{{{{ defs }}}}{marker}{{{{ overlay }}}}"
    wrapper = env.from_string(wrapper_source)
    rendered = wrapper.render(**context)

    parts = rendered.split(marker)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", rendered.strip()
