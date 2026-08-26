"""Which screen axis carries rank flow — the dag family's expression axis.

A layered graph is solved in MAJOR/MINOR terms: ranks advance along the major
axis, a rank's members spread along the minor. ``RIGHT`` is the identity map
(``dag``, byte-for-byte what shipped before this module existed); ``DOWN``
transposes it (``dag-vertical``). ``layered.py`` needs no part of this — it is
already axis-free, emitting ordinal ranks and per-rank orders with zero
geometry. Only placement and routing read an ``AxisMap``.

Boxes never rotate. Text stays horizontal, so a card is measured and drawn in
screen coordinates whichever way the graph flows; the map moves POSITIONS and
SIDE NAMES, never glyph geometry. That is why an axis-parameterized placement
works where transposing the finished canvas would not.

DOWN is the transpose ``(x, y) -> (y, x)``, and the choice is forced. Of the
three candidate maps, only the transpose preserves both properties that matter:

===================  ====================  =========================
map                  flow direction        member reading order
===================  ====================  =========================
transpose (y, x)     right -> down    OK   first member -> left  OK
clockwise (-y, x)    right -> down    OK   first member -> RIGHT  X
counter-cw (y, -x)   right -> UP       X   first member -> left  OK
===================  ====================  =========================

**Chirality is the price.** A transpose is a reflection across the diagonal,
not a rotation, so handedness MIRRORS: anything with a bow, a bulge, or a
near/far side flips sense. ``channel_near``/``channel_far`` are therefore
DERIVED here (``top``/``bottom`` reflect to ``left``/``right``), never chosen at
a call site, and every arc-sweep sign and control-point offset must route
through this map rather than through a literal. A hardcoded side name is
invisible until the first skip edge renders, and then it reads backwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal


@dataclass(frozen=True, slots=True)
class AxisMap:
    """A major/minor <-> screen mapping plus the side names it implies."""

    flow: Literal["right", "down"]
    exit_side: str
    """Face an edge LEAVES its source by (with the flow)."""
    entry_side: str
    """Face an edge ENTERS its target by (against the flow)."""
    channel_near: str
    """Side the over-channel runs on — the reflection of horizontal's ``top``."""
    channel_far: str
    """Side the under-channel runs on — the reflection of horizontal's ``bottom``."""

    def point(self, major: float, minor: float) -> tuple[float, float]:
        """Major/minor -> screen ``(x, y)``. Identity for RIGHT."""
        return (major, minor) if self.flow == "right" else (minor, major)

    def major_of(self, x: float, y: float) -> float:
        """The along-flow component of a screen point."""
        return x if self.flow == "right" else y

    def minor_of(self, x: float, y: float) -> float:
        """The across-flow component of a screen point."""
        return y if self.flow == "right" else x

    def box_major(self, w: float, h: float) -> float:
        """A box's extent ALONG the flow — width when flowing right."""
        return w if self.flow == "right" else h

    def box_minor(self, w: float, h: float) -> float:
        """A box's extent ACROSS the flow — height when flowing right."""
        return h if self.flow == "right" else w

    def side(self, name: str) -> str:
        """A horizontal-frame side word, read in THIS axis's screen frame.

        Authored ``exit``/``entry`` words are chosen in the flow frame, not the
        screen one: ``exit: top`` means "leave by the near channel" and
        ``entry: left`` means "arrive by the face the flow points at". Those
        readings are what the words meant when they were written, and they have
        to survive the transpose exactly as ``channel_near`` does — otherwise a
        declared detour stops being recognised as one and falls through to the
        default route, out to the far side and back across the whole diagram.

        DERIVED from the side fields above rather than a second table, so the
        two cannot drift: the answer is the field whose RIGHT value is ``name``.
        A word that names no field — including the empty default — **passes
        through unchanged**; that clause is part of the rule, not an exception
        to it, since the derivation alone has nothing to say about ``""``.
        """
        return {
            RIGHT.exit_side: self.exit_side,
            RIGHT.entry_side: self.entry_side,
            RIGHT.channel_near: self.channel_near,
            RIGHT.channel_far: self.channel_far,
        }.get(name, name)

    @classmethod
    def for_slug(cls, slug: str) -> AxisMap:
        """The map a layout slug solves in. Unknown slugs take RIGHT — the
        identity — so a solver that never learned the axis is unchanged.
        Loop's BARE slug is its vertical cell (the family default), so it
        maps DOWN where every other bare slug is the identity."""
        return _SLUG_AXES.get(slug, RIGHT)


RIGHT: Final = AxisMap(
    flow="right",
    exit_side="right",
    entry_side="left",
    channel_near="top",
    channel_far="bottom",
)
"""Ranks advance +x, members spread +y. The identity map."""

DOWN: Final = AxisMap(
    flow="down",
    exit_side="bottom",
    entry_side="top",
    channel_near="left",
    channel_far="right",
)
"""Ranks advance +y, members spread +x. Sides are the transpose of RIGHT's:
``right``/``left`` reflect to ``bottom``/``top``, and ``top``/``bottom``
reflect to ``left``/``right`` — see the chirality note in the module docstring."""

_SLUG_AXES: Final[dict[str, AxisMap]] = {
    "dag-vertical": DOWN,
    "loop": DOWN,
    "loop-horizontal": RIGHT,
}
