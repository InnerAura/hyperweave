"""Diagram annotation IR — the caller's overlay layer on a solved topology.

An annotation is chrome the SOLVER does not own: a callout with a leader, a
legend of accent swatches, a badge pill on a node, a pin dot at a canvas
point. It anchors to exactly one target — a node id, an edge (by the
``src->dst`` grammar, optionally ``#k`` for the k-th parallel occurrence), a
solver-registered region name, or a raw canvas point in 0..1 fractions — and
declares a placement hint the anti-collision pass may override.

This module is a leaf: it imports only ``core.base`` so ``core/diagram.py``
can nest annotations on ``DiagramSpec`` without a cycle. Referential checks
(the anchor names a declared id, the ordinal is in range) live on the spec
validator where the node/edge tables exist; here the model enforces only
what is self-contained — anchor arity and kind/shape legality.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from hyperweave.core.base import FrozenModel


class AnnotationKind(StrEnum):
    """Annotation anatomy — caller-chosen, drives the placement record.

    callout: boxed text with a leader line to its anchor. legend: a column
    of accent-swatch + label rows (region/canvas anchored). aside: boxed
    text, no leader (a margin note). The retired badge/pin kinds are deleted
    under the objecthood law: frames confer objecthood — annotations
    subordinate by ink; parts attach by containment (chip row) or threading
    (edge-chip), never a framed pill by proximity.
    """

    CALLOUT = "callout"
    LEGEND = "legend"
    ASIDE = "aside"
    MICRO_LABEL = "micro-label"  # bare tracked text floated at its anchor —
    # the kit's piece 8 as a first-class declarable figure (cicd-machine:
    # transitions ride floated micro-labels, never boxed callouts)


def parse_edge_ref(ref: str) -> tuple[str, str, int]:
    """Parse an edge anchor ``"src->dst"`` or ``"src->dst#k"``.

    Returns ``(source, target, ordinal)`` where ordinal is 1-based (the k-th
    parallel edge from source to target; 1 when no ``#k`` suffix). Raises
    ``ValueError`` on a malformed reference — the spec validator turns that
    into a referential error naming the annotation.
    """
    body = ref
    ordinal = 1
    if "#" in ref:
        body, _, tail = ref.partition("#")
        if not tail.isdigit() or int(tail) < 1:
            raise ValueError(f"edge ref ordinal must be a positive integer, got {ref!r}")
        ordinal = int(tail)
    if "->" not in body:
        raise ValueError(f"edge ref must be 'src->dst' (optionally '#k'), got {ref!r}")
    source, _, target = body.partition("->")
    source, target = source.strip(), target.strip()
    if not source or not target:
        raise ValueError(f"edge ref needs a non-empty source and target, got {ref!r}")
    return source, target, ordinal


class DiagramAnnotation(FrozenModel):
    """One caller-declared overlay on the solved topology.

    Exactly ONE anchor is set (``node`` | ``edge`` | ``region`` | ``at``);
    the model validator enforces that arity. Placement is a hint — the
    anti-collision pass may move the annotation to keep it off the graph.
    """

    text: str = Field(min_length=1, description="Annotation content (a single run; callouts/asides wrap)")
    kind: AnnotationKind = Field(default=AnnotationKind.CALLOUT, description="Annotation anatomy")
    node: str = Field(default="", description="Anchor: a declared node id")
    edge: str = Field(
        default="",
        description="Anchor: an edge as 'src->dst' or 'src->dst#k' (k-th parallel occurrence, 1-based)",
    )
    region: str = Field(default="", description="Anchor: a solver-registered region name (canvas, header, zone:N, …)")
    at: tuple[float, float] | None = Field(
        default=None, description="Anchor: a raw canvas point in (fx, fy) fractions, each 0..1"
    )
    placement: str = Field(
        default="",
        description="Placement hint: '' | above | below | left | right | ne | nw | se | sw (collision may override)",
    )
    accent: int | None = Field(
        default=None, ge=0, description="Flow-palette index for the annotation's chrome; None = chassis default"
    )
    shape: str = Field(
        default="",
        description=(
            "Legend swatch mark shape ('' | disc | ring | diamond | square | line | line-dashed) — disc.."
            "square are the lanes category-by-SHAPE idiom (obi-engine); line/line-dashed draw a short wire "
            "stub instead of a dot (dep-audit's edge-type key: solid stub = direct dep, dashed = "
            "transitive), riding the same neutral connector stroke every wire uses. Meaningful on "
            "kind=legend only. '' resolves to the plain accent circle."
        ),
    )
    health: str = Field(
        default="",
        description=(
            "Legend swatch STATE color ('' | outdated | vulnerable) — mirrors DiagramNode.health's "
            "vocabulary so a legend dot rides the identical state-palette class as the card dots it "
            "explains (never the flow-palette accent). Meaningful on kind=legend only; set health XOR "
            "accent, never both — health wins if both are set."
        ),
    )

    @model_validator(mode="after")
    def _validate_anchor(self) -> DiagramAnnotation:
        """Exactly one anchor set; kind/shape legality; placement/at bounds."""
        anchors = [bool(self.node), bool(self.edge), bool(self.region), self.at is not None]
        set_count = sum(anchors)
        if set_count != 1:
            raise ValueError(
                f"annotation {self.text!r} must set exactly one anchor (node | edge | region | at); got {set_count}"
            )
        if self.at is not None:
            for coord in self.at:
                if not (0.0 <= coord <= 1.0):
                    raise ValueError(f"annotation 'at' fractions must be within 0..1, got {self.at}")
        if self.placement and self.placement not in _PLACEMENTS:
            raise ValueError(f"annotation placement {self.placement!r} not in {sorted(_PLACEMENTS)}")
        # Kind/shape rules: a legend is a block that anchors to a region or
        # a canvas point; callout and aside accept any anchor.
        if self.kind is AnnotationKind.LEGEND and not (self.region or self.at is not None):
            raise ValueError("legend annotation must anchor to a region or a canvas point (got node/edge)")
        return self


_PLACEMENTS = frozenset({"above", "below", "left", "right", "ne", "nw", "se", "sw"})
