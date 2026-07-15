"""§12.2 --format ansi — the true spatial character-grid RENDER, golden-pinned.

The grid derives from the artifact's own machine layer — ``hw:payload``'s
embedded ``DiagramSpec``, re-solved through the IDENTICAL production pipeline
``compose/resolvers/diagram.py`` uses (never from pixels) — so the render is
deterministic by construction and the golden below is a literal.
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.errors import HwError
from hyperweave.core.models import ComposeSpec
from hyperweave.formats import FormatId, project

_PIPELINE_SPEC = {
    "topology": "pipeline",
    "title": "Ansi Golden",
    "nodes": [
        {"id": "a", "label": "extract"},
        {"id": "b", "label": "verify", "chips": ["hash", "schema"]},
        {"id": "c", "label": "publish"},
    ],
    "edges": [
        {"source": "a", "target": "b", "relation": "assert"},
        {"source": "b", "target": "c", "relation": "drift"},
    ],
}

_DAG_SPEC = {
    "topology": "dag",
    "title": "Fan Converge",
    "nodes": [
        {"id": "src", "label": "source"},
        {"id": "a", "label": "branch-a"},
        {"id": "b", "label": "branch-b"},
        {"id": "sink", "label": "sink"},
    ],
    "edges": [
        {"source": "src", "target": "a"},
        {"source": "src", "target": "b"},
        {"source": "a", "target": "sink"},
        {"source": "b", "target": "sink"},
    ],
}

_STATE_MACHINE_SPEC = {
    "topology": "state-machine",
    "title": "Job Lifecycle",
    "nodes": [
        {"id": "idle", "label": "idle"},
        {"id": "running", "label": "running"},
        {"id": "done", "label": "done"},
    ],
    "edges": [
        {"source": "idle", "target": "running", "label": "start"},
        {"source": "running", "target": "running", "label": "retry"},
        {"source": "running", "target": "done", "label": "finish"},
        {"source": "done", "target": "idle", "label": "reset"},
    ],
}

# dag/state-machine goldens re-pinned for the content-fit canvas (the
# chassis width became the scale reference, not a floor — the grids
# re-flowed one column narrower). Re-pinned again for the content-anchor
# envelope (card width minimum = glyph_inset_x + ink + pad_x; cards widen
# a few columns and the grids re-flow with them). Re-pinned again for the
# snug-width ruling (width citations are ceilings; cards solve to ink and
# the grids pack tighter).
_PIPELINE_GOLDEN = """\
┌─ content · pipeline · 3 nodes · 2 edges ────────────────────────────────────────────────┐
│ ╭─────────────────╮               ╭─────────────────╮               ╭─────────────────╮ │
│ │                 │               │  verify         │               │                 │ │
│ │                 │───────────────▶                 │┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄·                 │ │
│ │  extract        │               │   hash  schema  │               │  publish        │ │
│ ╰─────────────────╯               ╰─────────────────╯               ╰─────────────────╯ │
└─────────────────────────────────────────────────────────────────────────────────────────┘
┌─ footer ───┐
└────────────┘
"""

_DAG_GOLDEN = """\
┌─ content · dag · 4 nodes · 4 edges ────────────────────────────────────┐
│                               ╭──────────╮                             │
│                               │          │                             │
│                               ▶ branch-a │┄┄┄┄┄┄┄╮                     │
│                        ┄┄┄┄┄┄┄╰──────────╯       ┄┄┄┄┄╮                │
│ ╭─────────╮            ┆                              ┄┄┄┄┄┄┄╭───────╮ │
│ │         │       ┄┄┄┄┄╯                                     ▶       │ │
│ │  source │┄┄┄┄┄┄┄╮                                          ▶  sink │ │
│ ╰─────────╯       ┄┄┄┄┄╮      ╭──────────╮            ┄┄┄┄┄┄┄╰───────╯ │
│                        ┄┄┄┄┄┄┄│          │            ┆                │
│                               ▶          │┄┄┄┄┄┄┄┄┄┄┄┄╯                │
│                               │ branch-b │                             │
│                               ╰──────────╯                             │
└────────────────────────────────────────────────────────────────────────┘
┌─ footer ─────┐
└──────────────┘
"""

# Re-pinned (pill retirement + the drift-return and caption-pad laws):
# the state chain projects rx-13 glyph cards; returns ride the drift.
# Re-pinned: the SM back-edge construction moved to span-proportional
# pulls + geometry-driven arrivals (the specimen curve law), deepening
# the retry sweep — the projected grid shifts with the geometry.
# Re-pinned again: back-edges now dispatch by EXIT-SIDE ARCHETYPE
# (pp-state-machine-alt2.svg / pp-state-machine.svg) instead of one
# unconditional left-center exit — done->idle's reset has both ends on
# the SAME baseline row, so it now exits done's BOTTOM-CENTER into one
# shallow sweep (the alt2 revise law) instead of diving from the left
# edge; the grid is shorter because the sweep no longer needs the deep
# canvas a left-exit loop-around required. Re-pinned again for the
# exact-arrival construction (c2 placed from the specimen's own arrival
# angle, sole-return entry no longer offset ±14): the reset endpoint and
# the self-loop corner each moved one grid cell.
_STATE_MACHINE_GOLDEN = """\
┌─ content · state-machine · 3 nodes · 4 edges ──┐
│                          retry                 │
│                                                │
│                                                │
│ ╭──────╮        ╭──────────╮↺        ╭───────╮ │
│ │  i◀le│────────▶  running │┄┄┄┄┄┄┄┄┄▶┄┄done │ │
│ ╰──────╯        ╰──────────╯         ╰───────╯ │
│     ┆                      ┆                   │
│     ┆                      ┆                   │
│     ╰┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄                   │
└────────────────────────────────────────────────┘
┌─ footer ───────────┐
└────────────────────┘
"""


def _svg(diagram: dict) -> str:
    return compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=diagram)).svg


class TestAnsiProjection:
    def test_golden_pipeline(self) -> None:
        grid = project(_svg(_PIPELINE_SPEC), FormatId.ANSI).data.decode()
        assert grid == _PIPELINE_GOLDEN

    def test_golden_dag(self) -> None:
        """A fan-out + converge topology: staircase elbows plus arrival arrows."""
        grid = project(_svg(_DAG_SPEC), FormatId.ANSI).data.decode()
        assert grid == _DAG_GOLDEN

    def test_golden_state_machine(self) -> None:
        """A self-loop transition: the orbit glyph lands beside the revisited node."""
        grid = project(_svg(_STATE_MACHINE_SPEC), FormatId.ANSI).data.decode()
        assert grid == _STATE_MACHINE_GOLDEN

    def test_deterministic(self) -> None:
        a = project(_svg(_PIPELINE_SPEC), "ansi").data
        b = project(_svg(_PIPELINE_SPEC), "ansi").data
        assert a == b

    def test_structural_markers(self) -> None:
        inner = {
            "topology": "pipeline",
            "title": "i",
            "nodes": [{"id": "x", "label": "X"}, {"id": "y", "label": "Y"}, {"id": "z", "label": "Z"}],
        }
        spec = {
            "topology": "pipeline",
            "title": "T",
            "nodes": [
                {"id": "a", "label": "edge"},
                {"id": "b", "label": "mesh", "embed": inner},
                {"id": "c", "label": "sink"},
            ],
        }
        grid = project(_svg(spec), "ansi").data.decode()
        assert "mesh [⊞]" in grid  # containers carry the embed marker

    def test_direction_terminals(self) -> None:
        """assert -> an arrow chevron; drift -> a dot riding the dashed rail
        (the §3 line idioms' terminal dress, drawn onto the grid)."""
        grid = project(_svg(_PIPELINE_SPEC), "ansi").data.decode()
        assert "▶" in grid
        assert re.search(r"┄+·", grid) is not None

    def test_self_loop_glyph(self) -> None:
        grid = project(_svg(_STATE_MACHINE_SPEC), "ansi").data.decode()
        assert "↺" in grid

    def test_media_type_and_ext(self) -> None:
        p = project(_svg(_PIPELINE_SPEC), "ansi")
        assert p.media_type.startswith("text/plain")
        assert p.ext == "txt"

    def test_is_text_reaches_the_terminal(self) -> None:
        # The CLI delivers by Projection.is_text: ansi and svg are terminal
        # text; raster bytes are not (they blit or hint, never spill).
        from hyperweave.formats import Projection

        assert project(_svg(_PIPELINE_SPEC), "ansi").is_text
        assert project(_svg(_PIPELINE_SPEC), "svg").is_text
        assert not Projection(b"", "image/png", "png").is_text
        assert not Projection(b"", "image/webp", "webp").is_text

    def test_non_diagram_refuses(self) -> None:
        badge = compose(ComposeSpec(type="badge", genome_id="primer", variant="porcelain")).svg
        with pytest.raises(HwError):
            project(badge, "ansi")
