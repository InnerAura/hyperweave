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
    if frame_key == "receipt":
        # Every user-space string in the telemetry contract: session/model ids,
        # model names + roles, tool names, and context-event commands all come
        # straight from harness transcripts the user does not control.
        return ComposeSpec(
            type="receipt",
            telemetry_data={
                "session": _HOSTILE,
                "model": _HOSTILE,
                "cost_usd": 100.05,
                "dominant": _HOSTILE,
                "cost_basis": _HOSTILE,
                "estimate": True,
                "models": [
                    {"name": _HOSTILE, "role": _HOSTILE, "cost_usd": 100.00, "cost_pct": 99},
                    {"name": f"{_HOSTILE}2", "role": _HOSTILE, "cost_usd": 0.05, "cost_pct": 1},
                ],
                "tokens": {
                    "total": 1000000,
                    "in": 1000,
                    "out": 2000,
                    "cache_read": 500000,
                    "cache_write": 10000,
                    "working": 3000,
                },
                "calls": 10,
                "stages": 3,
                "turns": 2,
                "errors": 1,
                "active_min": 30,
                "context": {
                    "window": 200000,
                    "peak_ctx": 100000,
                    "events": [{"min": 5, "cmd": _HOSTILE, "to": 30000}],
                    "note": _HOSTILE,
                },
                "tools": [
                    {"name": _HOSTILE, "tok": 5000, "calls": 4, "err": 1, "class": "mutate"},
                    {"name": f"{_HOSTILE}2", "calls": 3},
                ],
            },
            **kwargs,
        )
    if frame_key == "stats":
        # Username, bio, top language, and language names all arrive from the
        # connector response — third-party text, not ours.
        return ComposeSpec(
            type="stats",
            connector_data={
                "username": _HOSTILE,
                "bio": _HOSTILE,
                "stars_total": 12847,
                "commits_total": 1203,
                "prs_total": 89,
                "issues_total": 47,
                "contrib_total": 234,
                "streak_days": 47,
                "top_language": _HOSTILE,
                "repo_count": 63,
                "language_breakdown": [
                    {"name": _HOSTILE, "pct": 68.5, "count": 43},
                    {"name": f"{_HOSTILE}2", "pct": 18.1, "count": 11},
                ],
                "heatmap_grid": [{"date": f"2025-01-{(i % 28) + 1:02d}", "count": (i % 12) + 1} for i in range(364)],
            },
            **kwargs,
        )
    raise AssertionError(f"no hostile spec registered for {frame_key!r}")


def _hostile_cases() -> list[tuple[str, str, str]]:
    cases: list[tuple[str, str, str]] = []
    for frame_key in ("badge", "strip", "marquee", "chart", "matrix", "diagram", "receipt", "stats"):
        for gid, variant in _genome_cases(frame_key):
            cases.append((frame_key, gid, variant))
    return cases


@pytest.mark.parametrize(("frame_key", "genome_id", "variant"), _hostile_cases())
def test_frames_emit_well_formed_xml_with_hostile_labels(frame_key: str, genome_id: str, variant: str) -> None:
    """Invariant 14: raw ``& < > \" '`` in user text never breaks the XML container."""
    svg = compose(_hostile_spec(frame_key, genome_id, variant)).svg
    ET.fromstring(svg)


# Engine-generated text can smuggle markup too: a model cost share that rounds
# to zero renders as "<1%", whose bare "<" is a StartTag to any XML parser.
_SUB_PERCENT_TELEMETRY: dict[str, Any] = {
    "session": "abc12345",
    "model": "opus-4.7",
    "cost_usd": 100.05,
    "models": [
        {"name": "opus-4.7", "role": "main thread", "cost_usd": 100.00, "cost_pct": 99},
        {"name": "haiku-4.5", "role": "subagent", "cost_usd": 0.05, "cost_pct": 0},
    ],
    "tokens": {"total": 1000000, "in": 1000, "out": 2000},
    "calls": 10,
}


def test_receipt_sub_percent_model_share_stays_well_formed() -> None:
    """The "<1%" cost share reaches the artifact as an entity, never a raw ``<``."""
    svg = compose(ComposeSpec(type="receipt", genome_id="primer", telemetry_data=_SUB_PERCENT_TELEMETRY)).svg
    assert "&lt;1%" in svg
    ET.fromstring(svg)
