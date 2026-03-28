"""Generation event capture for Tier 1 metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class GenerationEvent:
    """Tier 1 generation event emitted for every compose() call."""

    timestamp: str
    artifact_type: str
    genome_id: str
    profile_id: str
    motion: str
    regime: str
    metadata_tier: int
    width: int
    height: int


def emit_generation_event(
    spec: Any,
    result: Any,
) -> GenerationEvent:
    """Create a GenerationEvent from a ComposeSpec and ComposeResult."""
    now = datetime.now(tz=UTC).isoformat()

    return GenerationEvent(
        timestamp=now,
        artifact_type=getattr(spec, "type", "unknown"),
        genome_id=getattr(spec, "genome_id", ""),
        profile_id=getattr(spec, "profile_id", ""),
        motion=getattr(spec, "motion", "static"),
        regime=getattr(spec, "regime", "normal"),
        metadata_tier=getattr(spec, "metadata_tier", 3),
        width=getattr(result, "width", 0),
        height=getattr(result, "height", 0),
    )
