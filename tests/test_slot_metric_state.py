"""Slot-driven metric-state extraction — Phase 3.

Verifies that ``zone="metric-state"`` slots carry a ``state`` field that
the cellular paradigm strip templates consume. Plain ``zone="metric"``
slots still work as before (no state field, backward-compatible).
"""

from __future__ import annotations

from hyperweave.compose.resolver import _parse_metrics
from hyperweave.core.models import ComposeSpec, SlotContent


def test_metric_slot_has_no_state() -> None:
    spec = ComposeSpec(
        type="strip",
        slots=[
            SlotContent(zone="metric", value="STARS:2.9k"),
            SlotContent(zone="metric", value="FORKS:278"),
        ],
    )
    metrics = _parse_metrics(spec)
    assert len(metrics) == 2
    for m in metrics:
        assert m["state"] == ""  # default empty, template branches on this


def test_metric_state_slot_carries_state_from_data() -> None:
    spec = ComposeSpec(
        type="strip",
        state="active",
        slots=[
            SlotContent(zone="metric", value="STARS:2.9k"),
            SlotContent(
                zone="metric-state",
                value="BUILD:passing",
                data={"state": "passing"},
            ),
        ],
    )
    metrics = _parse_metrics(spec)
    assert len(metrics) == 2
    assert metrics[0]["state"] == ""
    assert metrics[1]["state"] == "passing"
    assert metrics[1]["label"] == "BUILD"
    assert metrics[1]["value"] == "passing"


def test_metric_state_slot_falls_back_to_spec_state() -> None:
    """When slot.data lacks 'state', the parser uses spec.state as the fallback."""
    spec = ComposeSpec(
        type="strip",
        state="warning",
        slots=[
            SlotContent(zone="metric-state", value="BUILD:warning"),
        ],
    )
    metrics = _parse_metrics(spec)
    assert metrics[0]["state"] == "warning"


def test_comma_value_fallback_still_works() -> None:
    """Legacy spec.value 'LABEL:VAL,LABEL2:VAL2' path preserved."""
    spec = ComposeSpec(type="strip", value="STARS:100,FORKS:20")
    metrics = _parse_metrics(spec)
    assert len(metrics) == 2
    assert metrics[0] == {"label": "STARS", "value": "100", "delta": "", "delta_dir": "neutral", "state": ""}
