"""Tests for the state inference chokepoint in compose().

BUG-003 regression tests: verify that state inference runs once at compose()
entry and covers every call site (CLI, HTTP, MCP, kit) without per-route
wiring. Observable signal is ``ComposeResult.metadata.state``.
"""

from __future__ import annotations

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec


def _metadata_state(title: str, value: str, state: str = "active") -> str:
    """Compose a minimal badge and return the state recorded in metadata.

    Metadata reflects the *post-inference* spec.state, so it proves the
    chokepoint fired (or didn't, when it shouldn't).
    """
    spec = ComposeSpec(
        type="badge",
        genome_id="brutalist-emerald",
        title=title,
        value=value,
        state=state,
    )
    result = compose(spec)
    assert result.metadata is not None
    return str(result.metadata.state)


def test_compose_infers_failing_from_value() -> None:
    assert _metadata_state("build", "failing") == "failing"


def test_compose_infers_passing_from_value() -> None:
    assert _metadata_state("build", "passing") == "passing"


def test_compose_infers_warning_from_value() -> None:
    assert _metadata_state("lint", "warning") == "warning"


def test_compose_infers_building_from_combined_signal() -> None:
    assert _metadata_state("build", "running") == "building"


def test_compose_infers_from_percentage_high() -> None:
    assert _metadata_state("coverage", "95%") == "passing"


def test_compose_infers_from_percentage_mid() -> None:
    assert _metadata_state("coverage", "75%") == "warning"


def test_compose_infers_from_percentage_low() -> None:
    assert _metadata_state("coverage", "50%") == "critical"


def test_compose_respects_explicit_state() -> None:
    """Explicit overrides must survive the chokepoint untouched."""
    # value="failing" would normally infer "failing", but the caller set
    # state="passing" explicitly -- that must win.
    assert _metadata_state("build", "failing", state="passing") == "passing"


def test_compose_respects_explicit_warning_over_inferred_passing() -> None:
    """Percentage >= 90 would infer passing; explicit warning survives."""
    assert _metadata_state("coverage", "95%", state="warning") == "warning"


def test_compose_empty_value_no_inference() -> None:
    """No value -> nothing to infer from; state stays at the default."""
    assert _metadata_state("build", "") == "active"


def test_compose_unrecognizable_value_no_inference() -> None:
    """Value with no rule match leaves state at default."""
    assert _metadata_state("version", "v1.2.3") == "active"
