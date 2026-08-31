"""Frame-generic performance-tier derivation.

The diagram pattern (``compose/diagram/motion.py::performance_tier``)
generalized to every frame: the tier DERIVES from the properties the RENDERED
artifact animates — sourced from data (the motions registry's
``animated_properties`` plus ``data/config/performance.yaml``'s
``baked_animations`` table), never asserted. ``compose/context.py`` calls
:func:`derive_performance_tier` where a hardcoded ``composite-only`` claim
used to live; the diagram resolver keeps its own richer per-connector
derivation and overrides through ``frame_context``.
"""

from __future__ import annotations


def animated_properties_for(motion_id: str, tier_key: str) -> frozenset[str]:
    """Union of the motion registry's ``animated_properties`` for
    ``motion_id`` (``static`` contributes none) and the template-baked
    ``baked_animations[tier_key]`` list."""
    from hyperweave.config.loader import get_loader, load_performance_config

    motion = get_loader().motions.get(motion_id) or {}
    baked = (load_performance_config().get("baked_animations") or {}).get(tier_key) or []
    return frozenset(str(p) for p in (motion.get("animated_properties") or [])) | frozenset(str(p) for p in baked)


def derive_performance_tier(motion_id: str, tier_key: str) -> str:
    """``paint-ok`` when any animated property falls outside the compositor
    law (``performance.yaml`` ``compositor_properties``), else
    ``composite-only``."""
    from hyperweave.config.loader import load_performance_config

    compositor = frozenset(str(p) for p in (load_performance_config().get("compositor_properties") or []))
    return (
        "paint-ok"
        if any(prop not in compositor for prop in animated_properties_for(motion_id, tier_key))
        else "composite-only"
    )
