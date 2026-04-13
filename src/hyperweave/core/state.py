"""State inference from label + value strings.

Maps a (label, value) pair to one of the ArtifactStatus member values. Called
by compose() to auto-populate spec.state when the caller left it at the
default "active", so that a live badge whose fetched value is "failing"
renders as failing without every route having to remember to call this.

Inference is deliberately conservative: it returns "active" whenever no rule
fires, which compose() treats as "caller did not override, leave alone".
"""

from __future__ import annotations


def infer_state(label: str, value: str) -> str:
    """Infer a semantic state from a (label, value) pair.

    Returns one of: passing, failing, warning, building, critical, active.
    "active" means "could not infer" — callers should treat it as unchanged.
    """
    label_lower = label.lower()
    value_lower = value.lower()

    if "pass" in value_lower or "success" in value_lower:
        return "passing"
    if "fail" in value_lower or "error" in value_lower:
        return "failing"
    if "warn" in value_lower:
        return "warning"
    if "build" in label_lower and "run" in value_lower:
        return "building"

    # Percentage-based threshold (e.g. "95%", "72.5%")
    if value.rstrip("%").replace(".", "").isdigit():
        try:
            num = float(value.rstrip("%"))
            if num >= 90:
                return "passing"
            if num >= 70:
                return "warning"
            return "critical"
        except ValueError:
            pass

    return "active"
