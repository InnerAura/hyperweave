"""Acceptance: the hub / lanes / promotion bundled specs render end-to-end.

These three bundled specs are the mechanism recreations of the hub,
obi, and agent-lifecycle specimens (zone roles, perimeter long-haul, cyclic-dag
promotion + self-loop — NOT their chrome). This suite composes each through the
FULL engine (the path a caller hits: bundled spec → ComposeSpec → compose) and
pins that the mechanism survives to the rendered artifact. The reviewable SVGs
live in ``v04/alpha/v04a6/acceptance/`` (regenerate with ``ACCEPTANCE_WRITE=1``).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

_ACCEPTANCE_DIR = Path(__file__).resolve().parents[2] / "v04" / "alpha" / "v04a6" / "acceptance"
_SPECS = ("hub", "obi-engine", "agent-task-lifecycle")


def _compose(name: str) -> object:
    bs = resolve_bundled_spec("diagram", name)
    spec = ComposeSpec(type="diagram", genome_id="primer", **{bs.field: bs.value})
    return compose(spec)


@pytest.mark.parametrize("name", _SPECS)
def test_renders_valid_svg(name: str) -> None:
    res = _compose(name)
    assert res.svg.lstrip().startswith("<svg") or "<svg" in res.svg[:400]  # type: ignore[attr-defined]
    assert res.svg.rstrip().endswith("</svg>")  # type: ignore[attr-defined]
    # No script — the inert-document invariant (mirrors test_svg_invariants).
    assert "<script" not in res.svg  # type: ignore[attr-defined]


def test_hub_carries_the_focal_and_spokes() -> None:
    # The hub axial cross (hub partition): the artifact
    # nucleus + transform (edit/N) + the collapsed read chip-card + the
    # destination fan all render (layout structure pinned in
    # test_diagram_hub_lanes; here it's the rendered SVG).
    svg = _compose("hub").svg  # type: ignore[attr-defined]
    assert "the artifact" in svg
    # transform north, the read family as chips, destinations east.
    for member in ("transform", "documents", "surfaces", "extract", "verify", "diff", "query"):
        assert member in svg, member


def test_lanes_bands_render() -> None:
    # The obi lanes: the five category band headers render (uppercased).
    svg = _compose("obi-engine").svg  # type: ignore[attr-defined]
    for band in ("CALLERS", "REGISTRY", "TOOLS", "MODEL ROUTING", "PROVIDERS"):
        assert band in svg, band


def test_agent_lifecycle_promotes_with_self_loop() -> None:
    # Declared topology:dag, but the replan cycle promotes it to state-machine
    # and the tool_call self-loop renders — the promotion mechanism end-to-end.
    # No parity preset declares a cyclic dag (the parity set is acyclic dags +
    # native state machines), so the promotion mechanism is exercised inline.
    cyclic_dag = {
        "topology": "dag",
        "title": "Agent lifecycle",
        "nodes": [
            {"id": "plan", "label": "plan"},
            {"id": "act", "label": "act"},
            {"id": "observe", "label": "observe"},
            {"id": "done", "label": "done", "role": "hero"},
        ],
        "edges": [
            {"source": "plan", "target": "act", "label": "dispatch"},
            {"source": "act", "target": "act", "label": "tool_call"},
            {"source": "act", "target": "observe"},
            {"source": "observe", "target": "plan", "label": "replan"},
            {"source": "observe", "target": "done"},
        ],
    }
    res = compose(ComposeSpec(type="diagram", genome_id="primer", diagram=cyclic_dag))
    assert any("promoted to state-machine" in w for w in res.warnings)  # type: ignore[attr-defined]
    # The rendered artifact is the state-machine subvariant and the self-loop's
    # label survived subsumption into the drawn document.
    assert "state-machine" in res.svg  # type: ignore[attr-defined]
    assert "tool_call" in res.svg  # type: ignore[attr-defined]


def test_write_reviewable_svgs() -> None:
    """Not an assertion — regenerates the reviewable acceptance SVGs when
    ``ACCEPTANCE_WRITE=1``. Kept in the suite so the artifacts never drift from
    the specs; the reviewed copies are committed under acceptance/."""
    if os.environ.get("ACCEPTANCE_WRITE") != "1":
        pytest.skip("set ACCEPTANCE_WRITE=1 to regenerate acceptance SVGs")
    _ACCEPTANCE_DIR.mkdir(parents=True, exist_ok=True)
    for name in _SPECS:
        res = _compose(name)
        (_ACCEPTANCE_DIR / f"{name}.svg").write_text(res.svg)  # type: ignore[attr-defined]
