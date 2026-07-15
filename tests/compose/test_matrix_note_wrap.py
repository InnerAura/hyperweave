"""The note-wrap law: narrow-container text wraps to a second line before it ellipsizes.

A short edge span or a squeezed note column fits ~1.5 words, so a two-word
label like "Claude Code" must wrap to ['Claude', 'Code'] — never truncate to a
mid-word 'Claude C…'. The masthead title/subtitle are deliberately excluded:
they are measured at the full diagram width, never exhibit the bug, and a
two-line subtitle would collide with the body on the 56/66px header chassis.
"""

from __future__ import annotations

import re

from hyperweave.compose.engine import compose
from hyperweave.compose.matrix.cells import _note_sub_fields, wrap_text_lines
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
    # A note wider than its column wraps into stacked sub_lines.
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
    elbl = re.findall(r'-(?:elbl|msg)">([^<]*)</text>', svg)
    assert len(elbl) >= 2, elbl  # wrapped across lines, not crammed onto one
    assert "…" not in elbl[0], elbl  # the first line is a clean word break, never clipped


# ── Authored paragraphs never drop ───────────────────────────────────────────


def test_multi_paragraph_never_drops_a_paragraph() -> None:
    """A max_lines cap narrower than the authored paragraph count used to
    silently discard whole paragraphs past the cap (the per-paragraph loop's
    naive ``if len(out) >= max_lines: break``) — boxes grow to hold what the
    author wrote, so the effective budget floors at the paragraph count:
    every paragraph gets at least one line, none vanish without a trace."""
    voice = MatrixVoice(family="Inter", size=11, weight=400)
    assert wrap_text_lines("First para.\nSecond para.\nThird para.", 500.0, voice, max_lines=1) == [
        "First para.",
        "Second para.",
        "Third para.",
    ]
    # An early paragraph long enough to fully consume the OLD budget on its
    # own (before the floor existed, this ate every remaining line) still
    # leaves its sibling at least one line.
    long_first = " ".join(["word"] * 20) + ".\nSecond para."
    wrapped = wrap_text_lines(long_first, 60.0, voice, max_lines=2)
    assert wrapped[-1].startswith("Second") or wrapped[-1].startswith("S…"), wrapped
    # A genuinely long SINGLE paragraph still respects max_lines as a WRAP
    # cap (never grows past it) — the floor only protects AUTHORED breaks.
    long_one_line = " ".join(["word"] * 20)
    assert len(wrap_text_lines(long_one_line, 60.0, voice, max_lines=2)) == 2


def test_fanout_upward_hero_desc_keeps_both_paragraphs() -> None:
    """primer.yaml's fanout-upward hero now declares ``max_desc_lines: 2``
    (sibling parity with fanout-downward/convergence/tree/hub, which all
    declare it) — a two-paragraph hero desc renders both paragraphs, not
    just the first. Regression coverage for the compound bug: the chassis
    default (``max_desc_lines`` floors at 1 when undeclared) combined with
    ``wrap_text_lines`` silently dropping any paragraph past the line cap."""
    spec = {
        "title": "Sources",
        "topology": "fanout",
        "orientation": "upward",
        "nodes": [
            {"label": "Hub", "role": "hero", "desc": "first paragraph\nsecond paragraph"},
            {"label": "A"},
            {"label": "B"},
        ],
    }
    svg = compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=spec)).svg
    assert "first paragraph" in svg
    assert "second paragraph" in svg
