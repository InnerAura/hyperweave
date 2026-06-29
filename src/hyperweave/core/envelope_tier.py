"""Envelope metadata tiering — how deep an envelope a frame emits.

The schema is always a valid ``hwz/1`` envelope regardless of tier; only the
DEPTH of the ``data`` digest varies. Lightweight frames (badge, divider, icon,
strip, marquee) carry a MINIMAL envelope — identity, provenance, and a compact
content digest. Structural frames (chart, stats, matrix, diagram, receipt) carry
a FULL envelope with salience-ranked frame data.

The map is data, not code (data/config/envelope-tiers.yaml, Invariant 5). A
caller may force a tier with an explicit override; otherwise the frame type
decides. An unknown frame falls back to MINIMAL — a forgotten frame still emits
a valid envelope, just a shallow one.
"""

from __future__ import annotations

from enum import StrEnum

from hyperweave.config.loader import load_envelope_tiers


class EnvelopeTier(StrEnum):
    """Envelope data depth. Schema is invariant; only ``data`` richness scales."""

    MINIMAL = "minimal"
    FULL = "full"


def resolve_tier(frame_type: str, override: str = "") -> EnvelopeTier:
    """Resolve the envelope tier for ``frame_type``.

    ``override`` (a ``--metadata-tier``-style flag value) wins when it names a
    valid tier; otherwise the per-frame map decides, defaulting to MINIMAL for
    frames the map doesn't list.
    """
    if override:
        try:
            return EnvelopeTier(override)
        except ValueError:
            pass
    tiers = load_envelope_tiers()
    return EnvelopeTier(tiers.get(frame_type, EnvelopeTier.MINIMAL.value))
