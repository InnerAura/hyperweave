"""Generation event schema for Tier 1 metadata — a constructor with NO SINK.

:func:`emit_generation_event` builds and returns a :class:`GenerationEvent`;
nothing stores, logs, or transmits it, and compose discards the return value.
No telemetry is recorded anywhere by composing an artifact. The event exists
as the stable record shape a future opt-in sink would consume (persistence is
the telemetry batch's to design); until one lands, this module is schema, not
telemetry, and any claim that compose records telemetry is false.
"""

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
    """Create a GenerationEvent from a ComposeSpec and ComposeResult.

    Despite the name, nothing is emitted anywhere: the event is constructed
    and returned, and the one caller (``compose()``) discards it. This is the
    schema witness, not a telemetry write."""
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
