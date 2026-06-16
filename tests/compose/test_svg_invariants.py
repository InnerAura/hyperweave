"""System-level SVG invariants — one artifact per frame type.

Artifacts are inert documents: CSS may animate them, but they never carry
executable content. The grep gate covers the templates; this test covers
the composed output, where context values could smuggle markup in.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.enums import FrameType
from hyperweave.core.matrix import MatrixSpec
from hyperweave.core.models import ComposeSpec

_FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"

_MINIMAL_TELEMETRY: dict[str, Any] = {"session": {}, "profile": {}, "tools": {}, "stages": []}

_CHART_POINTS = [
    {"date": "2025-01-01T00:00:00Z", "count": 100},
    {"date": "2025-04-01T00:00:00Z", "count": 320},
    {"date": "2025-07-01T00:00:00Z", "count": 680},
    {"date": "2025-10-01T00:00:00Z", "count": 1200},
]


def _matrix() -> MatrixSpec:
    return MatrixSpec.model_validate(json.loads((_FIXTURES / "matrix" / "check.json").read_text()))


def _spec(frame: FrameType) -> ComposeSpec:
    if frame is FrameType.BADGE:
        return ComposeSpec(type="badge", title="BUILD", value="passing")
    if frame is FrameType.STRIP:
        return ComposeSpec(type="strip", title="REPO", value="A:1")
    if frame is FrameType.ICON:
        return ComposeSpec(type="icon", glyph="github")
    if frame is FrameType.DIVIDER:
        return ComposeSpec(type="divider")
    if frame is FrameType.MARQUEE_HORIZONTAL:
        return ComposeSpec(type="marquee-horizontal", title="HW|TEST")
    if frame is FrameType.RECEIPT:
        return ComposeSpec(type="receipt", telemetry_data=_MINIMAL_TELEMETRY)
    if frame is FrameType.RHYTHM_STRIP:
        return ComposeSpec(type="rhythm-strip", telemetry_data=_MINIMAL_TELEMETRY)
    if frame is FrameType.STATS:
        return ComposeSpec(type="stats", genome_id="chrome")
    if frame is FrameType.CHART:
        return ComposeSpec(
            type="chart",
            chart_owner="eli64s",
            chart_repo="readme-ai",
            connector_data={"points": _CHART_POINTS, "current_stars": 2850, "repo": "eli64s/readme-ai"},
        )
    if frame is FrameType.MATRIX:
        return ComposeSpec(type="matrix", genome_id="primer", matrix=_matrix())
    if frame is FrameType.DIAGRAM:
        return ComposeSpec(
            type="diagram",
            genome_id="primer",
            diagram={
                "topology": "pipeline",
                "title": "Invariant probe",
                "nodes": [{"label": "A"}, {"label": "B", "role": "hero"}, {"label": "C"}],
            },
        )
    raise AssertionError(f"no minimal spec registered for frame type {frame!r} — add one")


@pytest.mark.parametrize("frame", list(FrameType))
def test_no_script_in_any_frame_output(frame: FrameType) -> None:
    """No ``<script>`` tags in any SVG output, across every frame type."""
    svg = compose(_spec(frame)).svg
    assert "<script" not in svg.lower()
