"""Threshold-based state resolution for data-bound badges."""

from __future__ import annotations

from dataclasses import dataclass

# Default threshold rules keyed by threshold_id.
# Each rule: list of (min_value, state) checked top-down.
# First match wins. The last entry should have min_value=None (catchall).

_COVERAGE_RULES: list[tuple[float | None, str]] = [
    (90.0, "passing"),
    (70.0, "warning"),
    (None, "critical"),
]

_UPTIME_RULES: list[tuple[float | None, str]] = [
    (99.9, "passing"),
    (99.0, "warning"),
    (None, "critical"),
]

_GENERIC_RULES: list[tuple[float | None, str]] = [
    (80.0, "passing"),
    (50.0, "warning"),
    (None, "critical"),
]

THRESHOLD_REGISTRY: dict[str, list[tuple[float | None, str]]] = {
    "coverage": _COVERAGE_RULES,
    "uptime": _UPTIME_RULES,
    "generic": _GENERIC_RULES,
}


@dataclass(frozen=True)
class ThresholdResult:
    """Result of threshold evaluation."""

    state: str
    numeric_value: float
    threshold_id: str


def resolve_threshold_state(value: str, threshold_id: str) -> str:
    """Resolve a numeric value to a semantic state using threshold rules."""
    # Strip common suffixes
    cleaned = value.strip().rstrip("%").strip()
    try:
        numeric = float(cleaned)
    except ValueError:
        msg = f"Cannot parse '{value}' as a numeric threshold value"
        raise ValueError(msg) from None

    rules = THRESHOLD_REGISTRY.get(threshold_id)
    if rules is None:
        msg = f"Unknown threshold_id: '{threshold_id}'. Available: {list(THRESHOLD_REGISTRY.keys())}"
        raise KeyError(msg)

    for min_val, state in rules:
        if min_val is None or numeric >= min_val:
            return state

    # Should be unreachable due to None catchall, but just in case
    return "critical"
