"""System-level SVG invariants — one artifact per frame type.

Artifacts are inert documents: CSS may animate them, but they never carry
executable content. The grep gate covers the templates; this test covers
the composed output, where context values could smuggle markup in.
"""

from __future__ import annotations

import json
import pathlib
import xml.etree.ElementTree as ET
from typing import Any

import pytest

import hyperweave
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
    if frame is FrameType.MARQUEE:
        return ComposeSpec(type="marquee", title="HW|TEST")
    if frame is FrameType.RECEIPT:
        return ComposeSpec(type="receipt", telemetry_data=_MINIMAL_TELEMETRY)
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


@pytest.mark.parametrize("frame", list(FrameType))
def test_every_frame_output_is_well_formed_xml(frame: FrameType) -> None:
    """Every composed artifact parses as XML, even with clean labels."""
    ET.fromstring(compose(_spec(frame)).svg)


# ── Hostile-label sweep: raw user text must never break the container ──
# One case per frame x genome x substrate face: each genome's default variant
# plus its first opposite-substrate variant, derived from the genome JSONs at
# collection time so new genomes/variants enroll themselves.

_HOSTILE = "A & B <C> \"D\" 'E'"


def _genome_cases(frame_key: str) -> list[tuple[str, str]]:
    genome_dir = pathlib.Path(hyperweave.__file__).parent / "data" / "genomes"
    cases: list[tuple[str, str]] = []
    for path in sorted(genome_dir.glob("*.json")):
        raw = json.loads(path.read_text())
        if not (raw.get("paradigms") or {}).get(frame_key):
            continue
        gid = path.stem
        cases.append((gid, ""))
        native = raw.get("substrate_kind") or raw.get("category", "dark")
        for vname in sorted(raw.get("variant_overrides") or {}):
            override = raw["variant_overrides"][vname]
            if (override.get("substrate_kind") or native) != native:
                cases.append((gid, vname))
                break
    return cases


def _hostile_spec(frame_key: str, genome_id: str, variant: str) -> ComposeSpec:
    kwargs: dict[str, Any] = {"genome_id": genome_id}
    if variant:
        kwargs["variant"] = variant
    if frame_key == "badge":
        # slots + numeric_value ride the badge case: ComposeSpec is the
        # declared boundary, so library-only fields enroll in the sweep too.
        return ComposeSpec(
            type="badge",
            title=_HOSTILE,
            value=_HOSTILE,
            numeric_value=_HOSTILE,
            slots=[{"zone": _HOSTILE, "value": _HOSTILE, "data": {"k": _HOSTILE}}],
            **kwargs,
        )
    if frame_key == "strip":
        return ComposeSpec(type="strip", title=_HOSTILE, value=f"{_HOSTILE}:{_HOSTILE}", **kwargs)
    if frame_key == "marquee":
        return ComposeSpec(type="marquee", title=f"{_HOSTILE}|{_HOSTILE}", **kwargs)
    if frame_key == "chart":
        return ComposeSpec(
            type="chart",
            chart_owner="acme",
            chart_repo=_HOSTILE,
            connector_data={"points": _CHART_POINTS, "current_stars": 2850, "repo": _HOSTILE},
            **kwargs,
        )
    if frame_key == "matrix":
        return ComposeSpec(
            type="matrix",
            matrix={
                "title": _HOSTILE,
                "columns": [{"id": "m", "label": _HOSTILE}, {"id": "c", "label": "COST", "kind": "numeric"}],
                "rows": [{"label": _HOSTILE, "cells": [{"value": _HOSTILE}, {"value": "0.12"}]}],
            },
            **kwargs,
        )
    if frame_key == "diagram":
        return ComposeSpec(
            type="diagram",
            diagram={
                "topology": "pipeline",
                "title": _HOSTILE,
                "subtitle": _HOSTILE,
                "nodes": [{"label": _HOSTILE}, {"label": _HOSTILE, "role": "hero"}, {"label": "C"}],
            },
            **kwargs,
        )
    raise AssertionError(f"no hostile spec registered for {frame_key!r}")


def _hostile_cases() -> list[tuple[str, str, str]]:
    cases: list[tuple[str, str, str]] = []
    for frame_key in ("badge", "strip", "marquee", "chart", "matrix", "diagram"):
        for gid, variant in _genome_cases(frame_key):
            cases.append((frame_key, gid, variant))
    return cases


@pytest.mark.parametrize(("frame_key", "genome_id", "variant"), _hostile_cases())
def test_frames_emit_well_formed_xml_with_hostile_labels(frame_key: str, genome_id: str, variant: str) -> None:
    """Invariant 14: raw ``& < > \" '`` in user text never breaks the XML container."""
    svg = compose(_hostile_spec(frame_key, genome_id, variant)).svg
    ET.fromstring(svg)
