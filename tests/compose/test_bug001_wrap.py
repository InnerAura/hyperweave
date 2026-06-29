"""BUG-001: narrow-container text wraps to a second line before it ellipsizes.

A short edge span or a squeezed note column fits ~1.5 words, so a two-word
label like "Claude Code" must wrap to ['Claude', 'Code'] — never truncate to a
mid-word 'Claude C…'. The masthead title/subtitle are deliberately excluded:
they are measured at the full diagram width, never exhibit the bug, and a
two-line subtitle would collide with the body on the 56/66px header chassis.
"""

from __future__ import annotations

import re

from hyperweave.compose.diagram.wiring import wrap_text_lines
from hyperweave.compose.engine import compose
from hyperweave.compose.matrix.cells import _note_sub_fields
from hyperweave.core.models import ComposeSpec
from hyperweave.core.paradigm import MatrixVoice

_EDGE_VOICE = MatrixVoice(family="JetBrains Mono", size=9.5, weight=400)
_SUB_VOICE = MatrixVoice(family="Inter", size=9.0, weight=400)


def test_two_word_label_wraps_never_mid_word() -> None:
    # Narrow span: wraps on the word boundary, no ellipsis at all.
    assert wrap_text_lines("Claude Code", 45.0, _EDGE_VOICE, max_lines=2) == ["Claude", "Code"]
    # Wide span: one line, untouched.
    assert wrap_text_lines("Claude Code", 200.0, _EDGE_VOICE, max_lines=2) == ["Claude Code"]
    # The ellipsis only ever lands on the final permitted line — the first line
    # (a whole word that fits) is never clipped.
    wrapped = wrap_text_lines("Claude Code runtime agent here", 45.0, _EDGE_VOICE, max_lines=2)
    assert len(wrapped) == 2
    assert "…" not in wrapped[0]


def test_note_sub_fields_wraps_into_sub_lines() -> None:
    # A note wider than its column wraps into stacked sub_lines (BUG-001).
    fields = _note_sub_fields("Claude Code", x=10.0, y0=20.0, max_w=45.0, voice=_SUB_VOICE, anchor="start")
    assert "sub_lines" in fields and "sub_text" not in fields
    lines = fields["sub_lines"]
    assert [s.text for s in lines] == ["Claude", "Code"]
    # Stacked downward, monotonic baselines, shared x.
    assert lines[1].y > lines[0].y
    assert all(s.x == 10.0 for s in lines)


def test_note_sub_fields_single_line_uses_sub_text_slot() -> None:
    # A note that fits keeps the single sub_text slot — no behavior change.
    fields = _note_sub_fields("ok", x=10.0, y0=20.0, max_w=200.0, voice=_SUB_VOICE, anchor="start")
    assert fields["sub_text"] == "ok"
    assert "sub_lines" not in fields


def test_diagram_edge_label_wraps_instead_of_truncating() -> None:
    """End-to-end: an edge label that outruns its span emits multiple
    <text class=elbl> runs (wrapped on word boundaries), not one clipped run."""
    spec = {
        "title": "flow",
        "topology": "sequence",
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        "edges": [{"source": "a", "target": "b", "label": "Claude Code Agent Runtime Bridge Layer Service Handler"}],
    }
    svg = compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=spec)).svg
    elbl = re.findall(r'-elbl">([^<]*)</text>', svg)
    assert len(elbl) >= 2, elbl  # wrapped across lines, not crammed onto one
    assert "…" not in elbl[0], elbl  # the first line is a clean word break, never clipped
