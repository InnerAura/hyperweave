"""The dag flow axis — identity, transpose, and the chirality it forces.

``RIGHT`` must be the identity in every accessor: the whole byte-parity
guarantee for the horizontal cell rests on it. ``DOWN`` must be the transpose
``(x, y) -> (y, x)`` — not a rotation — and its side names must be the
REFLECTION of RIGHT's, which is the one detail a call site could plausibly get
backwards and never notice until a skip edge renders.
"""

from __future__ import annotations

import pytest

from hyperweave.compose.diagram.axis import DOWN, RIGHT, AxisMap

_SAMPLES = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (13.5, -7.25), (880.0, 262.0)]


@pytest.mark.parametrize(("a", "b"), _SAMPLES)
def test_right_is_the_identity(a: float, b: float) -> None:
    """Every RIGHT accessor returns its argument untouched — ranks are x,
    members are y, box extents are w/h. Byte parity depends on this."""
    assert RIGHT.point(a, b) == (a, b)
    assert RIGHT.major_of(a, b) == a
    assert RIGHT.minor_of(a, b) == b
    assert RIGHT.box_major(a, b) == a
    assert RIGHT.box_minor(a, b) == b


@pytest.mark.parametrize(("a", "b"), _SAMPLES)
def test_down_is_the_transpose(a: float, b: float) -> None:
    """DOWN swaps the pair — and swapping twice is the identity, which is
    what makes it a reflection rather than a rotation (a quarter turn applied
    twice is a half turn, not the identity)."""
    assert DOWN.point(a, b) == (b, a)
    assert DOWN.major_of(a, b) == b
    assert DOWN.minor_of(a, b) == a
    assert DOWN.box_major(a, b) == b
    assert DOWN.box_minor(a, b) == a
    x, y = DOWN.point(a, b)
    assert DOWN.point(x, y) == (a, b)


def test_down_preserves_flow_and_reading_order() -> None:
    """The property that forced the transpose over either rotation: rank 1
    lands FURTHER DOWN than rank 0, and a rank's first member lands LEFT of
    its second. A clockwise turn keeps the flow but reverses reading order;
    a counter-clockwise turn keeps reading order but flows upward."""
    rank0 = DOWN.point(100.0, 200.0)
    rank1 = DOWN.point(350.0, 200.0)
    assert rank1[1] > rank0[1], "ranks must advance downward"
    assert rank1[0] == rank0[0], "advancing a rank must not move the cross axis"

    member0 = DOWN.point(350.0, 200.0)
    member1 = DOWN.point(350.0, 440.0)
    assert member1[0] > member0[0], "the first member must sit left of the second"
    assert member1[1] == member0[1], "members of one rank share a major coordinate"


def test_side_names_are_the_reflection_not_a_choice() -> None:
    """Chirality: the transpose maps right/left -> bottom/top and
    top/bottom -> left/right. Pinning BOTH channel sides is the point — a
    call site that hardcodes 'top' for the over-channel is invisible until
    the first skip edge draws on the wrong side."""
    assert (RIGHT.exit_side, RIGHT.entry_side) == ("right", "left")
    assert (DOWN.exit_side, DOWN.entry_side) == ("bottom", "top")

    assert (RIGHT.channel_near, RIGHT.channel_far) == ("top", "bottom")
    assert (DOWN.channel_near, DOWN.channel_far) == ("left", "right")

    # The four side names are distinct within a map — an over-channel and an
    # under-channel that resolved to the same side would stack silently.
    for axis in (RIGHT, DOWN):
        sides = {axis.exit_side, axis.entry_side, axis.channel_near, axis.channel_far}
        assert len(sides) == 4, f"{axis.flow}: side names collide"


def test_side_transposes_authored_words_and_agrees_with_the_fields() -> None:
    """Authored ``exit``/``entry`` words are FLOW-FRAME words: ``exit: top``
    means "leave by the near channel" whichever way the graph runs. They have
    to transpose with everything else or a declared detour stops being
    recognised as one and falls through to the default route.

    The pin that matters is AGREEMENT: ``side()`` is derived from the four side
    fields, so a future edit to one of them cannot leave a second table saying
    something else."""
    assert (DOWN.side("right"), DOWN.side("left")) == ("bottom", "top")
    assert (DOWN.side("top"), DOWN.side("bottom")) == ("left", "right")

    for axis in (RIGHT, DOWN):
        assert axis.side(RIGHT.exit_side) == axis.exit_side
        assert axis.side(RIGHT.entry_side) == axis.entry_side
        assert axis.side(RIGHT.channel_near) == axis.channel_near
        assert axis.side(RIGHT.channel_far) == axis.channel_far
        # A side word is its own image under RIGHT, and applying DOWN's map
        # twice returns it — the reflection property, at the level of names.
        for word in ("right", "left", "top", "bottom"):
            assert RIGHT.side(word) == word
            assert DOWN.side(DOWN.side(word)) == word


@pytest.mark.parametrize("word", ["", "middle", "RIGHT", " top"])
def test_side_passes_unknown_words_through(word: str) -> None:
    """Pass-through is part of the rule, not an exception to it. The
    derivation — "the field whose RIGHT value is this name" — has nothing to
    say about the empty default that every unrouted edge carries, so a reader
    implementing only the four-way table would leave ``side("")`` undefined."""
    assert RIGHT.side(word) == word
    assert DOWN.side(word) == word


def test_for_slug_covers_both_cells_and_defaults_to_identity() -> None:
    """Only ``dag-vertical`` transposes; every other slug — including any
    solver that never learned the axis — takes the identity."""
    assert AxisMap.for_slug("dag") is RIGHT
    assert AxisMap.for_slug("dag-vertical") is DOWN
    for slug in ("pipeline", "pipeline-vertical", "fanout-upward", "state-machine", ""):
        assert AxisMap.for_slug(slug) is RIGHT, f"{slug!r} must not transpose"
