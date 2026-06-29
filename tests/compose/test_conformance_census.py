"""Conformance census — the envelope-floor tag gate (alpha.5, Layer 0).

Every frame must emit a valid, re-ingestible ``hwz/1`` envelope. This census is
the proof the floor holds:

    frame x {payload_present, envelope_present, markdown_present, aria_present,
             hash_valid, prov_valid, triad_valid}

It is also the training-corpus integrity check — every artifact entering the
spatial-model training set passes here. No alpha.5 tag without this green.

The triad check is frame-aware: ``data-hw-status`` (health/severity) and
``data-hw-regime`` (policy lane) are universal; ``data-hw-state`` (lifecycle:
live/static) is the third axis. The three draw from disjoint vocabularies, so
when all three are present they are genuinely distinct — never a faked
three-different-strings collapse. A frame that honestly carries only two would
still pass (the third is asserted only when present).
"""

from __future__ import annotations

import json
import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.envelope import PROV_KEYS, envelope_id, validate_envelope
from hyperweave.core.models import ComposeSpec

from .test_chart_frame import MOCK_POINTS
from .test_receipt_primer import SPECIMEN_PAYLOAD
from .test_stats_card import MOCK_STATS

_PAYLOAD = re.compile(
    r'<hw:payload[^>]*\bschema="([^"]+)"[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>',
    re.DOTALL,
)
_ENVELOPE = re.compile(r"<hw:envelope[^>]*><!\[CDATA\[(.*?)\]\]></hw:envelope>", re.DOTALL)

_HEALTH_VOCAB = {"active", "passing", "building", "warning", "critical", "failing", "offline", "loop"}
_REGIME_VOCAB = {"normal", "permissive", "ungoverned"}
_LIFECYCLE_VOCAB = {"bound", "static"}

_MATRIX = {
    "title": "Cost by model",
    "columns": [{"id": "model", "label": "MODEL"}, {"id": "cost", "label": "COST", "kind": "numeric"}],
    "rows": [
        {"label": "Qwen", "cells": [{"value": "Qwen"}, {"value": "0.12"}]},
        {"label": "GPT-5", "cells": [{"value": "GPT-5"}, {"value": "2.50"}]},
    ],
}
_DIAGRAM = {
    "topology": "pipeline",
    "title": "Compose flow",
    "nodes": [{"id": "src", "label": "Source"}, {"id": "xform", "label": "Transform"}, {"id": "sink", "label": "Sink"}],
    "edges": [{"source": "src", "target": "xform"}, {"source": "xform", "target": "sink"}],
}


def _attr(svg: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]*)"', svg)
    return m.group(1) if m else None


def _spec(frame: str) -> ComposeSpec:
    specs = {
        "badge": ComposeSpec(type="badge", genome_id="primer", title="STARS", value="1.2k"),
        "strip": ComposeSpec(type="strip", genome_id="primer", title="readme-ai", value="STARS:2.9k,FORKS:278"),
        "icon": ComposeSpec(type="icon", genome_id="chrome", glyph="github"),
        "divider": ComposeSpec(type="divider", genome_id="automata", divider_variant="dissolve"),
        "marquee": ComposeSpec(type="marquee", genome_id="primer", title="ALPHA | BETA | GAMMA"),
        "chart": ComposeSpec(
            type="chart",
            genome_id="primer",
            chart_owner="eli64s",
            chart_repo="readme-ai",
            connector_data={"points": MOCK_POINTS, "current_stars": 2850, "repo": "eli64s/readme-ai"},
        ),
        "stats": ComposeSpec(type="stats", genome_id="brutalist", stats_username="eli64s", connector_data=MOCK_STATS),
        "matrix": ComposeSpec(type="matrix", genome_id="primer", matrix=_MATRIX),
        "diagram": ComposeSpec(type="diagram", genome_id="primer", diagram=_DIAGRAM),
        "receipt": ComposeSpec(
            type="receipt", genome_id="primer", variant="porcelain", telemetry_data=SPECIMEN_PAYLOAD
        ),
    }
    return specs[frame]


FRAMES = ["badge", "strip", "icon", "divider", "marquee", "chart", "stats", "matrix", "diagram", "receipt"]


@pytest.mark.parametrize("frame", FRAMES)
def test_conformance_census(frame: str) -> None:
    result = compose(_spec(frame))
    svg = result.svg

    # payload_present
    pm = _PAYLOAD.search(svg)
    assert pm, f"{frame}: hw:payload absent"
    schema, payload_json = pm.group(1), pm.group(2)
    assert schema, f"{frame}: payload schema empty"

    # envelope_present
    em = _ENVELOPE.search(svg)
    assert em, f"{frame}: hw:envelope absent"
    env = json.loads(em.group(1))

    # prov_valid — schema gate + exact prov key set + non-empty genome
    validate_envelope(env)
    assert set(env["prov"]) == set(PROV_KEYS), f"{frame}: prov keys {sorted(env['prov'])}"
    assert env["prov"]["genome"], f"{frame}: prov.genome empty"

    # hash_valid — recomputable from the embedded payload alone
    assert env["id"] == envelope_id(payload_json), f"{frame}: id != sha256(payload)"

    # markdown_present — the text-shadow projection the document agent leads with
    assert result.markdown.strip(), f"{frame}: markdown shadow empty"

    # aria_present
    for needle in ('role="img"', "<title ", "<desc ", "aria-labelledby="):
        assert needle in svg, f"{frame}: missing {needle}"

    # triad_valid — three distinct, non-colliding channels
    status = _attr(svg, "data-hw-status")
    regime = _attr(svg, "data-hw-regime")
    state = _attr(svg, "data-hw-state")
    assert status in _HEALTH_VOCAB, f"{frame}: data-hw-status={status!r} not health vocab"
    assert regime in _REGIME_VOCAB, f"{frame}: data-hw-regime={regime!r} not policy vocab"
    if state is not None:
        assert state in _LIFECYCLE_VOCAB, f"{frame}: data-hw-state={state!r} not lifecycle vocab"
        # disjoint vocabularies → all three values genuinely distinct (never collapsed)
        assert len({state, status, regime}) == 3, f"{frame}: triad collapsed {state}/{status}/{regime}"
