"""hw:reasoning describes the face the artifact actually renders.

The reported defect: an adaptive primer diagram explained white cards on light
paper while the reader, in dark mode, was looking at the dark plate. The file
contradicted itself. Reasoning used to key off the variant's NATIVE substrate;
it now keys off what the artifact renders as, which is also what `data-hw-mode`
reports — so the two can be asserted against each other.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from hyperweave.compose.engine import compose
from hyperweave.compose.reasoning import load_reasoning
from hyperweave.core.models import ComposeSpec

_DIAGRAM = {
    "topology": "pipeline",
    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
    "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
}


def _reasoning(svg: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for field in ("intent", "approach", "tradeoffs"):
        match = re.search(rf"<hw:{field}>(.*?)</hw:{field}>", svg, re.S)
        out[field] = " ".join((match.group(1) if match else "").split())
    return out


def _mode(svg: str) -> str:
    match = re.search(r'data-hw-mode="([^"]+)"', svg)
    assert match, "every artifact reports the face it rendered"
    return match.group(1)


def _diagram(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {"type": "diagram", "genome_id": "primer", "variant": "porcelain", "diagram": _DIAGRAM}
    return compose(ComposeSpec(**{**kwargs, **overrides})).svg


# ── the reported defect ──────────────────────────────────────────────────


def test_an_adaptive_artifact_does_not_describe_one_face_only() -> None:
    """The repro: `--surface inlay` on porcelain renders light-base + dark
    @media, and used to carry porcelain's light-paper prose verbatim."""
    svg = _diagram(ground="bare", palette="adaptive")
    assert _mode(svg) == "adaptive"
    reasoning = _reasoning(svg)
    assert "BOTH faces" in reasoning["intent"]
    assert "prefers-color-scheme" in reasoning["intent"]


def test_a_baked_dark_face_stops_describing_light_paper() -> None:
    """`--variant porcelain --face dark` keeps substrate_kind='light', which is
    why the old key picked the light block for a dark render."""
    svg = _diagram(palette="fixed", surface_face="dark")
    assert _mode(svg) == "dark"
    assert "light paper" not in _reasoning(svg)["intent"]


@pytest.mark.parametrize(
    ("overrides", "expected_mode"),
    [
        pytest.param({"ground": "bare", "palette": "adaptive"}, "adaptive", id="inlay"),
        pytest.param({"ground": "opaque", "palette": "adaptive"}, "adaptive", id="twin"),
        pytest.param({"palette": "fixed", "surface_face": "dark"}, "dark", id="face-dark"),
        pytest.param({"palette": "fixed", "surface_face": "light"}, "light", id="face-light"),
        pytest.param({"ground": "opaque", "palette": "fixed"}, "light", id="plate-porcelain"),
        pytest.param({"variant": "noir", "ground": "opaque", "palette": "fixed"}, "dark", id="plate-noir"),
    ],
)
def test_reasoning_matches_the_face_the_artifact_reports(overrides: dict[str, Any], expected_mode: str) -> None:
    """One assertion across every surface: the prose and `data-hw-mode` agree.
    A file whose own explanation contradicts what you look at is the bug."""
    svg = _diagram(**overrides)
    assert _mode(svg) == expected_mode
    expected = load_reasoning("primer", "diagram", expected_mode)
    assert expected is not None, f"primer/diagram must author a {expected_mode} block"
    assert _reasoning(svg)["intent"] == " ".join(expected.intent.split())


def test_the_three_faces_are_genuinely_different_prose() -> None:
    """A fallback that silently reused one block would satisfy the check above
    while leaving the defect in place."""
    intents = {
        face: _reasoning(_diagram(**overrides))["intent"]
        for face, overrides in (
            ("adaptive", {"ground": "bare", "palette": "adaptive"}),
            ("dark", {"palette": "fixed", "surface_face": "dark"}),
            ("light", {"palette": "fixed", "surface_face": "light"}),
        )
    }
    assert len(set(intents.values())) == 3, intents


# ── the matrix frame, the other adaptive-capable frame ───────────────────


def test_the_matrix_frame_also_speaks_for_its_rendered_face() -> None:
    from hyperweave.compose.bundled_specs import resolve_bundled_spec

    connectors = resolve_bundled_spec("matrix", "connectors").value
    svg = compose(
        ComposeSpec(
            type="matrix",
            genome_id="primer",
            variant="porcelain",
            connector_data=connectors,
            ground="bare",
            palette="adaptive",
        )
    ).svg
    assert _mode(svg) == "adaptive"
    assert "BOTH faces" in _reasoning(svg)["intent"]


# ── the quality bar the strings are held to ──────────────────────────────


@pytest.mark.parametrize("frame", ["diagram", "matrix"])
def test_the_new_adaptive_blocks_clear_the_reasoning_bar(frame: str) -> None:
    """Every reasoning string carries a spatial measurement, a geometric
    decision, and an explicit tradeoff — strings teach the spatial model."""
    fields = load_reasoning("primer", frame, "adaptive")
    assert fields is not None
    assert re.search(r"\d", fields.approach), "approach cites no measurement"
    assert len(fields.tradeoffs.split()) > 20, "tradeoffs is not an explicit tradeoff"
    for text in (fields.intent, fields.approach, fields.tradeoffs):
        assert text.strip() and not text.strip().endswith(":")


def test_a_plate_render_keeps_the_reasoning_it_always_had() -> None:
    """The fix is scoped to faces that disagreed; a fixed plate on a light
    variant resolved to the light block before and must still."""
    svg = _diagram(ground="opaque", palette="fixed")
    light = load_reasoning("primer", "diagram", "light")
    assert light is not None
    assert _reasoning(svg)["intent"] == " ".join(light.intent.split())
