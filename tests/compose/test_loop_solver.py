"""Loop solver geometry guards.

The corpus-enrolled composition rules, asserted on the SOLVED layout: 2px
endpoint standoffs, the rail as the one long route (two rounded corners,
clear of content), rhombus-true diamonds whose holders grow for their chips,
scope containment, the family's own chromatic compile, and transpose
equivalence — the same spec must keep its structure on either flow.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest

from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import coerce_diagram_input
from hyperweave.config.loader import load_diagram_config, load_paradigms
from hyperweave.core.models import ComposeSpec

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import DiagramLayout, NodePlacement
from tests.compose.test_loop_ir import endless, hillclimb, nested, tap

NUM = r"-?\d+(?:\.\d+)?"


def solve(dspec: dict[str, Any]) -> DiagramLayout:
    normalized = coerce_diagram_input(
        None, ComposeSpec.model_validate({"type": "diagram", "genome_id": "primer", "diagram": dspec})
    )
    paradigm = load_paradigms()["primer"].diagram
    engine = load_diagram_config()
    return compute_diagram_layout(normalized.spec, paradigm=paradigm, engine=engine, palette_len=6)


def node_by_id(lay: DiagramLayout, node_id: str) -> NodePlacement:
    for n in lay.nodes:
        if n.node_id == node_id:
            return n
    raise AssertionError(f"no placement for {node_id!r}")


def path_end(d: str) -> tuple[float, float]:
    pairs = re.findall(rf"({NUM}),({NUM})", d)
    x, y = pairs[-1]
    return float(x), float(y)


def box_distance(x: float, y: float, n: NodePlacement) -> float:
    b = n.box
    dx = max(b.x - x, x - (b.x + b.w), 0.0)
    dy = max(b.y - y, y - (b.y + b.h), 0.0)
    return (dx * dx + dy * dy) ** 0.5


class TestStandoffs:
    @pytest.mark.parametrize("dspec", [hillclimb(), nested(), tap(), endless("Plan", "Act", "Review")])
    def test_arrivals_stand_off_their_target(self, dspec: dict[str, Any]) -> None:
        lay = solve(dspec)
        by_index = {n.index: n for n in lay.nodes}
        for c in lay.connectors:
            target = by_index.get(c.target_index)
            if target is None:
                continue  # the scope anchors paint as bands, not cards
            x, y = path_end(c.path_d)
            d = box_distance(x, y, target)
            assert 0.0 <= d <= 3.5, (
                f"connector {c.index} arrives {d:.2f}px off its target "
                f"(the corpus asserts endpoints 0.5-3.5px off the boundary)"
            )


class TestRail:
    def test_return_is_the_one_long_route(self) -> None:
        lay = solve(hillclimb())
        lengths = sorted(c.length for c in lay.connectors)
        ret = max(lay.connectors, key=lambda c: c.length)
        # The rail dominates every other run (turn/cycle-turn: 1041 vs <=225).
        assert ret.length > 2.5 * lengths[-2]
        # Two rounded corners: orthogonal_d draws each as one arc command.
        assert ret.path_d.count("A ") == 2

    def test_rail_clears_content(self) -> None:
        lay = solve(hillclimb())
        ret = max(lay.connectors, key=lambda c: c.length)
        xs = [float(m) for m in re.findall(rf"({NUM}),{NUM}", ret.path_d)]
        rail_x = max(xs)
        content_right = max(n.box.x + n.box.w for n in lay.nodes)
        # The rail's vertical run sits beyond every card (cycle-nested: 27px
        # clear); the entry leg necessarily crosses back in.
        assert rail_x >= content_right


class TestDiamond:
    def test_decisions_render_rhombus_true(self) -> None:
        lay = solve(hillclimb())
        improved = node_by_id(lay, "improved")
        assert improved.shape == "diamond"
        pts = [(float(x), float(y)) for x, y in re.findall(rf"({NUM}),({NUM})", improved.shape_d)]
        assert len(pts) == 4
        b = improved.box
        cx, cy = b.x + b.w / 2, b.y + b.h / 2
        # N/E/S/W vertices at the circumscribing box's edge midpoints (the
        # path rides fmt's coordinate quantization; the box keeps full
        # floats — 0.06px covers the rounding, never a real seat error).
        assert pts[0] == pytest.approx((cx, b.y), abs=0.06)
        assert pts[1] == pytest.approx((b.x + b.w, cy), abs=0.06)
        assert pts[2] == pytest.approx((cx, b.y + b.h), abs=0.06)
        assert pts[3] == pytest.approx((b.x, cy), abs=0.06)

    def test_holder_grows_for_its_chips(self) -> None:
        lay = solve(hillclimb())
        plain = node_by_id(lay, "improved")
        holder = node_by_id(lay, "stop")
        assert holder.box.h > plain.box.h
        assert holder.box.w > plain.box.w
        assert len(holder.chip_boxes) == 3
        # Rhombus-true seating: every chip corner satisfies the diamond
        # inequality (|dx|/hw + |dy|/hh <= 1), never just the bounding box.
        hw, hh = holder.box.w / 2, holder.box.h / 2
        cx, cy = holder.box.x + hw, holder.box.y + hh
        for cb in holder.chip_boxes:
            for corner in ((cb.x, cb.y), (cb.x + cb.w, cb.y), (cb.x, cb.y + cb.h), (cb.x + cb.w, cb.y + cb.h)):
                k = abs(corner[0] - cx) / hw + abs(corner[1] - cy) / hh
                assert k <= 1.0 + 1e-6, f"chip corner {corner} escapes the rhombus (k={k:.3f})"

    def test_four_chip_holder_packs_two_full_rows(self) -> None:
        # Past two greedy rows the holder re-packs into exactly two full
        # rows, widest chips shallow, spending width on full rows.
        dspec = hillclimb()
        stop = next(n for n in dspec["nodes"] if n["id"] == "stop")
        stop["chips"] = ["target hit", "no gains", "out of ideas", "budget spent"]
        lay = solve(dspec)
        holder = node_by_id(lay, "stop")
        assert len(holder.chip_boxes) == 4
        row_tops = sorted({round(cb.y, 1) for cb in holder.chip_boxes})
        assert len(row_tops) == 2
        by_row = [[cb for cb in holder.chip_boxes if round(cb.y, 1) == y] for y in row_tops]
        assert [len(r) for r in by_row] == [2, 2]
        assert sum(cb.w for cb in by_row[0]) >= sum(cb.w for cb in by_row[1])
        # AMENDED (owner aspect ruling, 2026-08-30): the height-class law
        # ("gains chips without gaining a row -> same height") is superseded
        # by aspect invariance — w/h stays the chassis ratio, so a wider row
        # propagates into height and 2+2 no longer shares 2+1's class. The
        # holder still solves TALLER-or-equal, never shorter, than the 2+1
        # form, and the aspect pin below is the new law.
        three_chip = node_by_id(solve(hillclimb()), "stop")
        assert holder.box.h >= three_chip.box.h
        assert abs(holder.box.w / holder.box.h - three_chip.box.w / three_chip.box.h) < 0.01
        hw, hh = holder.box.w / 2, holder.box.h / 2
        assert abs(hw / hh - 100 / 52) < 0.01  # the chassis aspect, both specimens sit on it
        cx, cy = holder.box.x + hw, holder.box.y + hh
        for cb in holder.chip_boxes:
            for corner in ((cb.x, cb.y), (cb.x + cb.w, cb.y), (cb.x, cb.y + cb.h), (cb.x + cb.w, cb.y + cb.h)):
                k = abs(corner[0] - cx) / hw + abs(corner[1] - cy) / hh
                assert k <= 1.0 + 1e-6, f"chip corner {corner} escapes the rhombus (k={k:.3f})"

    def test_question_rides_the_deliberation_voice(self) -> None:
        lay = solve(hillclimb())
        assert node_by_id(lay, "improved").label.cls == "qname"


class TestSkipBranchWall:
    def test_skip_branch_refuses_with_the_remedy(self) -> None:
        """A decision branch that skips past a spine station refuses with
        the printed remedy — before this wall it drew through the card."""
        dspec = {
            "topology": "loop",
            "nodes": [
                {"id": "a", "label": "Run"},
                {"id": "q", "label": "Green?", "station": "decision"},
                {"id": "fix", "label": "Patch"},
                {"id": "stop", "label": "Done?", "station": "decision"},
                {"id": "out", "label": "Out.", "station": "terminal", "partition": "advance"},
            ],
            "edges": [
                {"from": "a", "to": "q"},
                {"from": "q", "to": "fix", "label": "no", "label_style": "chip"},
                {"from": "q", "to": "stop", "label": "yes", "label_style": "chip"},
                {"from": "fix", "to": "stop"},
                {"from": "stop", "to": "out", "label": "yes", "label_style": "chip"},
                {"from": "stop", "to": "a", "label": "no", "label_style": "chip", "circuit": "return"},
            ],
        }
        from hyperweave.core.diagram import DiagramInputError

        with pytest.raises(DiagramInputError, match="skips past a station on the spine"):
            solve(dspec)


class TestMixedFamilyColumn:
    """Mixed-family column law: a width-aligned family that draws at least
    one identity mark seats EVERY member's text at the family's glyph
    column — a markless member reserves the mark advance art-free instead
    of pad-anchoring and pooling the shared width's slack on its right (the
    failover terminal read). All-markless families keep the pad anchor (the
    markless refinement); content stays free — any mark mix is legal."""

    @staticmethod
    def solve_with_marks(dspec: dict[str, Any]) -> DiagramLayout:
        # The registry-carrying solve: mark placement (and therefore the
        # column each sibling actually renders at) needs the glyph registry
        # the module helper deliberately omits.
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.matrix import GlyphTint

        normalized = coerce_diagram_input(
            None, ComposeSpec.model_validate({"type": "diagram", "genome_id": "primer", "diagram": dspec})
        )
        return compute_diagram_layout(
            normalized.spec,
            paradigm=load_paradigms()["primer"].diagram,
            engine=load_diagram_config(),
            palette_len=6,
            glyph_registry=load_glyphs(),
            glyph_selections=tuple(GlyphTint.INK for _ in normalized.spec.nodes),
        )

    def _tap_spec(self, *, mark_tele: bool) -> dict[str, Any]:
        # The loop-tap shape: the externals pair {human, tele} is one node2
        # family; marking only tele makes it a MIXED family. Marks need the
        # card+glyph anatomy, declared spec-level like every loop exhibit.
        dspec = tap()
        dspec["node_style"] = "card+glyph"
        for n in dspec["nodes"]:
            if n["id"] == "tele" and mark_tele:
                n["kind"] = "activity"
        return dspec

    def test_markless_member_joins_the_marked_family_column(self) -> None:
        lay = self.solve_with_marks(self._tap_spec(mark_tele=True))
        tele, human = node_by_id(lay, "tele"), node_by_id(lay, "human")
        assert tele.glyph is not None
        assert human.glyph is None
        tele_lead = tele.label.x - tele.box.x
        human_lead = human.label.x - human.box.x
        assert tele_lead == pytest.approx(human_lead, abs=0.01), (
            f"markless external anchors at {human_lead:.1f} while its glyphed sibling's column sits at {tele_lead:.1f}"
        )

    def test_all_markless_family_keeps_the_pad_anchor(self) -> None:
        lay = self.solve_with_marks(self._tap_spec(mark_tele=False))
        marked = self.solve_with_marks(self._tap_spec(mark_tele=True))
        pad_lead = node_by_id(lay, "human").label.x - node_by_id(lay, "human").box.x
        col_lead = node_by_id(marked, "human").label.x - node_by_id(marked, "human").box.x
        assert pad_lead < col_lead, "an all-markless family must keep the tighter pad anchor"


class TestChromaticCompile:
    def test_partition_hues(self) -> None:
        lay = solve(hillclimb())
        accents = [c for c in lay.connectors if c.accent_wire]
        comps = [c for c in lay.connectors if c.comp_wire]
        # improved->keep and stop->done ride the accent; improved->revert the
        # complement; everything else stays quiet conn.
        assert len(accents) == 2
        assert len(comps) == 1
        assert all(c.accent_index == -1 for c in lay.connectors), "loop bypasses the spine inference"

    def test_partition_names(self) -> None:
        lay = solve(hillclimb())
        assert node_by_id(lay, "done").label.cls == "dname"
        assert node_by_id(lay, "revert").label.cls == "mname"

    def test_tap_dress(self) -> None:
        lay = solve(tap())
        by_index = {n.index: n for n in lay.nodes}
        comp = [c for c in lay.connectors if c.comp_wire]
        assert len(comp) == 1  # the interrupting tap-in
        assert by_index[comp[0].source_index].node_id == "human"


class TestScope:
    def test_enclosure_band_holds_its_members(self) -> None:
        lay = solve(nested())
        assert len(lay.lane_bands) == 1
        band = lay.lane_bands[0]
        assert band.ground == "enclosure"
        assert band.dash == "8 7"  # the expression corpus's enclosure stroke
        assert band.header_box is not None
        inner_ids = {"i1", "i2", "i3"}
        for n in lay.nodes:
            if n.node_id in inner_ids:
                assert band.box.x <= n.box.x and n.box.x + n.box.w <= band.box.x + band.box.w
                assert band.box.y <= n.box.y and n.box.y + n.box.h <= band.box.y + band.box.h

    def test_scope_paints_no_card(self) -> None:
        lay = solve(nested())
        assert all(n.node_id != "scope" for n in lay.nodes)


class TestTransposeEquivalence:
    def test_structure_survives_the_flip(self) -> None:
        v = solve(hillclimb())
        h = solve({**hillclimb(), "orientation": "horizontal"})
        assert v.layout_slug == "loop"
        assert h.layout_slug == "loop-horizontal"

        def flow_order(lay: DiagramLayout, major: str) -> list[str]:
            key = (lambda n: n.box.y) if major == "y" else (lambda n: n.box.x)
            return [n.node_id for n in sorted(lay.nodes, key=key)]

        # The rank walk is orientation-invariant: the same stations advance
        # in the same order along whichever axis carries the flow.
        assert flow_order(v, "y") == flow_order(h, "x")

    def test_default_orientation_is_vertical(self) -> None:
        lay = solve(endless("Plan", "Act", "Review"))
        assert lay.layout_slug == "loop"
        assert lay.height > lay.width
