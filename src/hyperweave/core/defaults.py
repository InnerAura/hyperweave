"""The single home of the default-genome policy.

Grep-gated in CLAUDE.md: a default-genome literal (a signature/field default
or a ``dict.get`` fallback naming a genome) appears exactly once in the tree —
here. Every surface and both verbs resolve an unset genome through this
function; a copy living in an adapter is how validate and compose drifted
apart in the first v0.4.1 cut.

Lives in core (not compose/) so ``ComposeSpec``'s own field default can use it
without inverting the core → compose layering.
"""

from __future__ import annotations


def default_genome(frame_type: str = "") -> str:
    """The genome an unset ``genome`` resolves to — primer, for every frame.

    ``frame_type`` is accepted (and ignored) so call sites read naturally and
    the zero-arg form works as a pydantic ``default_factory``.
    """
    return "primer"
