"""Diagram annotation model: anchor arity, kind/shape rules, edge-ref grammar.

The annotation model (``core/diagram_annotations.py``) is a leaf validated in
isolation: exactly one anchor, kind/shape legality, placement bounds, and the
``parse_edge_ref`` grammar. Referential checks (the anchor names a declared
node/edge, the ordinal is in range) live on the spec validator — those are
pinned in ``tests/compose/test_diagram_promotion.py``.
"""

from __future__ import annotations

import pytest

from hyperweave.core.diagram_annotations import AnnotationKind, DiagramAnnotation, parse_edge_ref


class TestEdgeRefGrammar:
    def test_plain_pair_is_ordinal_one(self) -> None:
        assert parse_edge_ref("a->b") == ("a", "b", 1)

    def test_ordinal_suffix_parses(self) -> None:
        assert parse_edge_ref("plan->act#3") == ("plan", "act", 3)

    def test_whitespace_trimmed(self) -> None:
        assert parse_edge_ref(" a -> b ") == ("a", "b", 1)

    def test_missing_arrow_rejected(self) -> None:
        with pytest.raises(ValueError, match="src->dst"):
            parse_edge_ref("a b")

    def test_empty_endpoint_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            parse_edge_ref("->b")

    def test_zero_ordinal_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            parse_edge_ref("a->b#0")

    def test_non_numeric_ordinal_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            parse_edge_ref("a->b#x")


class TestAnchorArity:
    def test_exactly_one_anchor_required_none(self) -> None:
        with pytest.raises(ValueError, match="exactly one anchor"):
            DiagramAnnotation(text="note", kind=AnnotationKind.CALLOUT)

    def test_exactly_one_anchor_required_two(self) -> None:
        with pytest.raises(ValueError, match="exactly one anchor"):
            DiagramAnnotation(text="note", kind=AnnotationKind.CALLOUT, node="a", region="canvas")

    def test_node_anchor_ok(self) -> None:
        a = DiagramAnnotation(text="note", kind=AnnotationKind.CALLOUT, node="a")
        assert a.node == "a"

    def test_at_anchor_ok(self) -> None:
        a = DiagramAnnotation(text="note", kind=AnnotationKind.ASIDE, at=(0.5, 0.5))
        assert a.at == (0.5, 0.5)

    def test_at_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"0\.\.1"):
            DiagramAnnotation(text="note", kind=AnnotationKind.ASIDE, at=(1.5, 0.5))


class TestKindShapeRules:
    def test_badge_and_pin_are_deleted(self) -> None:
        # Objecthood law: frames confer objecthood — a framed pill attached
        # by proximity reads as a sibling object, not an annotation. Both
        # kinds are deleted; a spec declaring them must hear a refusal.
        for retired in ("badge", "pin"):
            with pytest.raises(ValueError):
                DiagramAnnotation(text="new", kind=retired, node="a")  # type: ignore[arg-type]

    def test_legend_requires_region_or_at(self) -> None:
        with pytest.raises(ValueError, match="legend"):
            DiagramAnnotation(text="key", kind=AnnotationKind.LEGEND, node="a")

    def test_legend_on_region_ok(self) -> None:
        a = DiagramAnnotation(text="key", kind=AnnotationKind.LEGEND, region="footer")
        assert a.region == "footer"

    def test_callout_accepts_any_anchor(self) -> None:
        for anchor in ({"node": "a"}, {"edge": "a->b"}, {"region": "canvas"}, {"at": (0.5, 0.5)}):
            a = DiagramAnnotation(text="c", kind=AnnotationKind.CALLOUT, **anchor)  # type: ignore[arg-type]
            assert a.kind is AnnotationKind.CALLOUT


class TestPlacement:
    def test_valid_placement_ok(self) -> None:
        a = DiagramAnnotation(text="n", kind=AnnotationKind.CALLOUT, node="a", placement="ne")
        assert a.placement == "ne"

    def test_unknown_placement_rejected(self) -> None:
        with pytest.raises(ValueError, match="placement"):
            DiagramAnnotation(text="n", kind=AnnotationKind.CALLOUT, node="a", placement="diagonal")

    def test_empty_placement_ok(self) -> None:
        a = DiagramAnnotation(text="n", kind=AnnotationKind.CALLOUT, node="a")
        assert a.placement == ""


class TestTextRequired:
    def test_empty_text_rejected(self) -> None:
        with pytest.raises(ValueError):
            DiagramAnnotation(text="", kind=AnnotationKind.CALLOUT, node="a")
