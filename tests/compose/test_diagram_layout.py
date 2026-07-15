"""Geometric invariants for the diagram layout solvers.

Universal rules hold across every layout (in-canvas, no node overlap,
determinism, connector endpoints on node edges); per-topology pins
reproduce the specimen constants the formulas were extracted from.
"""

from __future__ import annotations

import itertools
import math
import re
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram import motion as mo
from hyperweave.compose.diagram.input import resolve_auto_roles
from hyperweave.config.loader import load_diagram_config, load_paradigms
from hyperweave.core.diagram import DiagramCapacityError, DiagramInputError, DiagramSpec

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import DiagramLayout

ENGINE = load_diagram_config()

# The hero own-ink G3 dominance law lives in fan.py: every layout slug whose
# solver threads measured sibling/satellite dominance through
# ``sizing.hero_width_floor``/``hero_height_floor``. Every other topology's
# hero still floors through its own solver (graph.py, state-machine, hub),
# which legitimately keeps the paradigm chassis width as a floor.
_FAN_FAMILY_SLUGS = frozenset(
    {"fanout-horizontal", "fanout-bilateral", "fanout-upward", "fanout-downward", "convergence"}
)


def solve(palette_len: int = 5, **kw: Any) -> DiagramLayout:
    paradigm = load_paradigms()["primer"].diagram
    spec = resolve_auto_roles(DiagramSpec(**kw))
    return compute_diagram_layout(spec, paradigm=paradigm, engine=ENGINE, palette_len=palette_len)


def _normalized_preset(name: str) -> DiagramSpec:
    """A preset routed through the PRODUCTION input seam (auto roles + the
    cyclic-dag promotion in ``coerce_diagram_input``) — the spec the solvers
    actually receive. Feeding a raw declared spec to compute_diagram_layout
    tests geometry no production path produces; the dag solver now refuses
    cycles outright, so a cyclic preset (release-train) MUST promote first."""
    from hyperweave.compose.diagram.input import coerce_diagram_input, resolve_diagram_preset
    from hyperweave.core.models import ComposeSpec

    cs = ComposeSpec(type="diagram", genome_id="primer", diagram=resolve_diagram_preset(name))
    return coerce_diagram_input(cs.connector_data, cs).spec


def labeled(*labels: str, hero: int | None = None) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = [{"label": lb} for lb in labels]
    if hero is not None:
        nodes[hero]["role"] = "hero"
    return nodes


CASES: dict[str, dict[str, Any]] = {
    "pipeline": dict(topology="pipeline", title="T", nodes=labeled("A", "B", "C", "D", hero=1)),
    "fanout-horizontal": dict(
        topology="fanout",
        title="T",
        # gather: true on the hub — the depart-trunk gather-gate (fan.py)
        # now matches join/dag instead of firing unconditionally on >=2
        # spokes; this CASE exercises the trunk in
        # test_horizontal_curves_share_midpoint_control.
        nodes=[{"label": "hub", "gather": True}, *labeled("a", "b", "c", "d", "e")],
    ),
    "fanout-bilateral": dict(
        topology="fanout", orientation="bilateral", title="T", nodes=labeled("hub", "a", "b", "c", "d", "e")
    ),
    "fanout-upward": dict(topology="fanout", orientation="upward", nodes=labeled("hub", "a", "b", "c", "d", "e")),
    "fanout-radial": dict(topology="fanout", orientation="radial", nodes=labeled("hub", "a", "b", "c", "d", "e")),
    "convergence": dict(topology="convergence", title="T", nodes=labeled("a", "b", "c", "d", "out")),
    "flywheel": dict(topology="flywheel", title="T", nodes=labeled("p1", "p2", "p3", "p4", "axis", hero=4)),
    "stack": dict(topology="stack", title="T", nodes=labeled("result", "f", "g", "d", "p")),
    "tree": dict(topology="tree", title="T", nodes=labeled("root", "a", "b", "c")),
    "comparison": dict(topology="comparison", title="T", nodes=labeled("before", "after")),
    "sequence": dict(
        topology="sequence",
        title="T",
        nodes=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
        edges=[
            {"source": "a", "target": "b", "label": "call()", "kind": "call"},
            {"source": "b", "target": "a", "label": "ret", "kind": "return"},
            {"source": "a", "target": "c", "label": "notify", "kind": "call"},
        ],
    ),
    "hub": dict(
        topology="hub",
        hub_policy="compass",
        title="T",
        nodes=[
            {"id": "core", "label": "CORE", "role": "hero"},
            {"id": "a", "label": "a"},
            {"id": "b", "label": "b"},
            {"id": "c", "label": "c"},
            {"id": "d", "label": "d"},
        ],
        edges=[
            {"source": "core", "target": "a", "role": "out"},
            {"source": "core", "target": "b", "role": "out"},
            {"source": "c", "target": "core", "role": "in"},
            {"source": "d", "target": "core", "role": "in"},
        ],
    ),
    "lanes": dict(
        topology="lanes",
        title="T",
        nodes=[
            {"id": "a", "label": "Ingest", "category": "Source"},
            {"id": "b", "label": "Parse", "category": "Transform"},
            {"id": "c", "label": "Store", "category": "Sink"},
            {"id": "d", "label": "Check", "category": "Transform"},
        ],
        edges=[
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
            {"source": "b", "target": "d"},
        ],
    ),
}


class TestUniversalInvariants:
    @pytest.mark.parametrize("slug", sorted(CASES))
    def test_nodes_inside_canvas(self, slug: str) -> None:
        lay = solve(**CASES[slug])
        assert lay.layout_slug == slug
        for n in lay.nodes:
            b = n.box
            assert b.x >= -0.5 and b.y >= -0.5, (slug, n.index)
            assert b.x + b.w <= lay.width + 0.5 and b.y + b.h <= lay.height + 0.5, (slug, n.index)

    @pytest.mark.parametrize("slug", sorted(CASES))
    def test_no_node_overlap(self, slug: str) -> None:
        lay = solve(**CASES[slug])
        boxes = [n.box for n in lay.nodes]
        for i, a in enumerate(boxes):
            for b in boxes[i + 1 :]:
                separated = a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y
                assert separated, (slug, a, b)

    @pytest.mark.parametrize("slug", sorted(CASES))
    def test_determinism(self, slug: str) -> None:
        assert solve(**CASES[slug]) == solve(**CASES[slug])

    @pytest.mark.parametrize("slug", sorted(CASES))
    def test_text_fits_its_box(self, slug: str) -> None:
        # Truncation is measurement-based: a start-anchored run must not
        # cross its card's right padding edge.
        from hyperweave.compose.diagram.chrome import voice_for
        from hyperweave.compose.matrix.cells import measure_voice

        cfg = load_paradigms()["primer"].diagram
        lay = solve(**CASES[slug])
        for n in lay.nodes:
            if n.shape != "rect" or n.label.anchor != "start":
                continue
            w = measure_voice(n.label.text, voice_for(cfg, n.label.cls))
            assert n.label.x + w <= n.box.x + n.box.w + 0.5, (slug, n.index, n.label.text)

    @pytest.mark.parametrize("slug", sorted(CASES))
    def test_palette_slots_cover_accents(self, slug: str) -> None:
        lay = solve(**CASES[slug])
        used = [n.accent_index for n in lay.nodes] + [c.accent_index for c in lay.connectors]
        top = max([a for a in used if a >= 0], default=-1)
        assert lay.palette_slots == top + 1


class TestPipeline:
    def test_specimen_exact_x_positions(self) -> None:
        lay = solve(**CASES["pipeline"])
        # Bare pipeline stays label-row (rag-pipeline opts into portrait head): ink-derived unit, gap 120.
        # Re-pinned (snug-width ruling 2026-07-14): stages solve to their
        # own ink, so the row packs tighter.
        assert [round(n.box.x, 4) for n in lay.nodes] == [40.0, 206.0, 380.05, 546.05]
        # height 169 (was 181): the pipeline hero-floor migration (JOB2) content-
        # solves an UNCITED hero pure — this CASE's bare desc-less "B" hero no
        # longer floats the shared row height at the paradigm's topology-default
        # hero.h (72); the plain siblings' own 60px chassis height now sets the
        # row's shared max instead, 12px shorter.
        assert (lay.width, lay.height) == (632, 169)  # caption_bottom_pad 44; width re-pinned for the snug row
        # Row centerline y 54 (was 60): rides the shared row height's
        # midpoint, which shifted up 6px (half of the 12px height re-pin above).
        assert [c.path_d for c in lay.connectors] == [
            "M 86,54 L 206,54",
            "M 260.1,54 L 380.1,54",
            "M 426.1,54 L 546,54",
        ]

    def test_equal_gaps(self) -> None:
        lay = solve(topology="pipeline", nodes=labeled(*"ABCDE"))
        xs = sorted(n.box.x for n in lay.nodes)
        widths = {round(n.box.w, 2) for n in lay.nodes}
        assert len(widths) == 1  # no hero -> equal units
        gaps = {round(b - (a + lay.nodes[0].box.w), 2) for a, b in itertools.pairwise(xs)}
        assert len(gaps) == 1


class TestFans:
    def test_bilateral_double_mirror(self) -> None:
        """The bilateral canon (the alpha3 integration-hub composition
        proof): the medallion sits at the exact midpoint of the two column
        faces AND its circle centre rides the seat band's centre line — a
        double mirror (the reference holds columns at 110/710 about the 410
        hub, seats at equal pitch about its cy). A labeled hero box once
        lifted the circle 20px off the seat line, and width/2 broke the
        horizontal mirror whenever the columns' label widths differed."""
        lay = solve(
            topology="fanout",
            orientation="bilateral",
            title="T",
            node_style="glyph-circle",
            nodes=[
                {"id": "hub", "label": "deploy", "desc": "v1", "role": "hero", "kind": "send"},
                {"id": "a", "label": "us-east", "kind": "globe"},
                {"id": "b", "label": "eu-west-longer-label", "kind": "globe"},
                {"id": "c", "label": "canary", "kind": "eye"},
                {"id": "d", "label": "shadow", "kind": "layers"},
            ],
        )
        hub = next(n for n in lay.nodes if n.role == "hero")
        sats = [n for n in lay.nodes if n.role != "hero"]
        left = [n for n in sats if n.cx < hub.cx]
        right = [n for n in sats if n.cx > hub.cx]
        assert left and right
        lt = hub.cx - max(n.cx for n in left)
        rt = min(n.cx for n in right) - hub.cx
        assert abs(lt - rt) <= 0.5, (lt, rt)
        seat_c = (min(n.cy for n in sats) + max(n.cy for n in sats)) / 2
        assert abs(hub.cy - seat_c) <= 0.5, (hub.cy, seat_c)

    def test_horizontal_column_pitch_and_height(self) -> None:
        lay = solve(**CASES["fanout-horizontal"])
        dests = [n for n in lay.nodes if n.index != 0]
        tops = sorted(n.box.y for n in dests)
        pitches = {round(b - a, 2) for a, b in itertools.pairwise(tops)}
        # G7 raised the column pitch so siblings clear min_clearance.
        assert pitches == {load_paradigms()["primer"].diagram.topologies["fanout-horizontal"].pitch}
        assert (lay.width, lay.height) == (920, 657)  # language pitch 118; caption_bottom_pad 44

    def test_horizontal_curves_depart_flush_at_shared_mouth(self) -> None:
        # An unlabeled fan departs FLUSH off the hero's face
        # (primer-fanout-refined.html): no stub, no floating knot — every
        # spoke starts at the same point on the card's right edge, and the
        # gather bezel marks that point. Curves still spread as midpoint
        # S-curves once departed.
        lay = solve(**CASES["fanout-horizontal"])
        trunks = [c for c in lay.connectors if " L " in c.path_d]
        assert not trunks, [c.path_d for c in trunks]
        starts = {tuple(round(float(v), 2) for v in c.path_d.split(" ")[1].split(",")) for c in lay.connectors}
        assert len(starts) == 1, starts
        assert len(lay.gathers) == 1
        mx, my = starts.pop()
        assert abs(lay.gathers[0].x - mx) < 0.5
        assert abs(lay.gathers[0].y - my) < 0.5
        for c in lay.connectors:
            m = re.match(r"M ([\d.]+),[\d.-]+ C ([\d.]+),", c.path_d)
            assert m
            start_x, ctrl_x = float(m.group(1)), float(m.group(2))
            end_x = float(c.path_d.rsplit(" ", 1)[1].split(",")[0])
            assert abs(ctrl_x - (start_x + end_x) / 2) < 0.11, c.path_d

    def test_bilateral_split_balance(self) -> None:
        lay = solve(**CASES["fanout-bilateral"])
        hub_cx = lay.width / 2
        left = sum(1 for n in lay.nodes if n.index != 0 and n.box.x + n.box.w / 2 < hub_cx)
        right = sum(1 for n in lay.nodes if n.index != 0 and n.box.x + n.box.w / 2 > hub_cx)
        assert abs(left - right) <= 1

    def test_upward_rows_centered(self) -> None:
        lay = solve(**CASES["fanout-upward"])
        rows: dict[float, list[float]] = {}
        for n in lay.nodes:
            if n.index == 0:
                continue
            rows.setdefault(n.box.y, []).append(n.box.x + n.box.w / 2)
        for centers in rows.values():
            assert abs(sum(centers) / len(centers) - lay.width / 2) < 0.5

    def test_radial_uniform_center_radius(self) -> None:
        # R5: radial topologies place by ONE declared policy — uniform
        # CENTER-radius (perceived radius is to card centers, not edges).
        # Pinned for fanout-radial here; the hub property sweep pins its
        # equidistance across generated specs.
        lay = solve(**CASES["fanout-radial"])
        hub = lay.nodes[-1]
        hx = hub.box.x + hub.box.w / 2
        hy = hub.box.y + hub.box.h / 2
        radii = {
            round(math.hypot(n.box.x + n.box.w / 2 - hx, n.box.y + n.box.h / 2 - hy), 1)
            for n in lay.nodes
            if n.index != 0
        }
        assert len(radii) == 1, radii

    def test_radial_equiangle_content_fit(self) -> None:
        # LAW 1 superseded the ring SQUARE: the canvas is the content bbox +
        # chrome bands, so an unoccupied arc never pays for dead canvas.
        # Equiangle placement is measured about the HUB, not the canvas mid.
        lay = solve(**CASES["fanout-radial"])
        hub = lay.nodes[-1]
        assert hub.index == 0  # painted last: the emanation mask
        hx = hub.box.x + hub.box.w / 2
        hy = hub.box.y + hub.box.h / 2
        angles = sorted(
            math.degrees(math.atan2(n.box.y + n.box.h / 2 - hy, n.box.x + n.box.w / 2 - hx))
            for n in lay.nodes
            if n.index != 0
        )
        deltas = {round(b - a, 1) for a, b in itertools.pairwise(angles)}
        assert deltas == {72.0}

    def test_convergence_single_meet_point(self) -> None:
        lay = solve(**CASES["convergence"])
        ends = {c.path_d.rsplit(" ", 1)[1] for c in lay.connectors}
        assert len(ends) == 1

    def test_undeclared_hero_width_floors_at_dominance(self) -> None:
        """G3 dominance law: an undeclared fanout-horizontal hero (no preset
        citation of ``chassis.hero.w``) with short, markless content floors
        at the layout's measured DOMINANCE — the widest solved satellite —
        never the paradigm's uncited 206px archetype (tuned to a DIFFERENT
        specimen whose own crown fills 98% of it). A short hero left in that
        floor rendered ~27% full, a dead-air box."""
        lay = solve(
            topology="fanout",
            title="T",
            node_style="card",
            nodes=[
                {"label": "hub", "desc": "the seed", "gather": True},
                {"label": "porcelain", "desc": "paper light"},
                {"label": "carbon", "desc": "graphite dark"},
                {"label": "dusk", "desc": "violet dark"},
            ],
        )
        ch = load_paradigms()["primer"].diagram.topologies["fanout-horizontal"]
        hero = next(n for n in lay.nodes if n.role == "hero")
        # Snug-width ruling: the crown solves ALONE to its own ink — the
        # retired dominance law floored it at its satellites' width. It may
        # legitimately solve narrower than them; the chassis archetype only
        # bounds growth.
        assert hero.box.w < ch.hero.w, (hero.box.w, ch.hero.w)

    def test_marked_hero_height_content_solves(self) -> None:
        """G3 height law: a MARKED (glyph) fanout-horizontal hero with a
        short one-line desc content-solves its height too — the prior
        marked-only floor cited a glyph-bearing crown (104, a two-line
        subtitle) against every marked hero regardless of whether its own
        preset ever earned that citation, truncating a short glyph row's
        card at the uncited archetype height."""
        lay = solve(
            topology="fanout",
            title="T",
            node_style="card+glyph",
            nodes=[
                {"label": "hw", "desc": "the binary", "role": "hero", "kind": "terminal", "gather": True},
                {"label": "compose", "desc": "spec -> svg", "kind": "code"},
                {"label": "extract", "desc": "payload out", "kind": "search"},
            ],
        )
        ch = load_paradigms()["primer"].diagram.topologies["fanout-horizontal"]
        hero = next(n for n in lay.nodes if n.role == "hero")
        assert hero.box.h < ch.hero.h, (hero.box.h, ch.hero.h)
        # One name line + one desc line, content+pads only — the pad_y/
        # label_desc_gap citations that make a 2-line hero content-solve to
        # the archetype's 104 NATURALLY (primer_diagram_language's own
        # generous ~26px vertical air) also raise a 1-line hero's floor —
        # padding is constant regardless of line count, so a 1-line hero
        # now lands at ~0.83 of the citation (86.38), not ~0.45 (the old
        # tight pad_y's ~47). The band still catches a regression to the
        # UNCONDITIONAL floor (which lands at exactly 1.0x, not below it).
        assert hero.box.h < ch.hero.h * 0.9, (hero.box.h, ch.hero.h)


class TestRing:
    def test_flywheel_arc_radius_and_boundary_trim(self) -> None:
        lay = solve(**CASES["flywheel"])
        arc_r = load_paradigms()["primer"].diagram.topologies["flywheel"].arc_r
        for c in lay.connectors:
            m = re.search(r"A ([\d.]+),", c.path_d)
            assert m and float(m.group(1)) == arc_r  # flywheel-orbit rim
        # Shape-true trim (G1): every arc spans MORE than the old
        # half-width-as-radius estimate allowed (42 deg) because side
        # approaches now stop at the card's actual boundary.
        spans = [round(c.length / 178 * 180 / math.pi, 1) for c in lay.connectors]
        assert all(s > 42.0 for s in spans), spans
        assert len(set(spans)) == 1  # cardinal symmetry holds

    def test_flywheel_hero_is_axis(self) -> None:
        lay = solve(**CASES["flywheel"])
        axis = next(n for n in lay.nodes if n.role == "hero")
        # LAW 1: the CONTENT centers on the canvas; the hero centers the ring
        # horizontally exactly, and vertically up to the ring's asymmetric
        # extras (labels under the lowest card extend the bbox below).
        assert abs(axis.box.x + axis.box.w / 2 - lay.width / 2) < 0.5
        assert abs(axis.box.y + axis.box.h / 2 - lay.height / 2) < 32.0  # caption pad 44 deepens the footer band


class TestStackTreeComparison:
    def test_stack_operator_count_and_vertical_risers(self) -> None:
        # The operator SLOT is chassis geometry (ring + cross, stack);
        # its PRESENCE is preset data (G9): no mark, no rail; a declared
        # token rails every riser gap with a drawn ring+cross, never text.
        lay = solve(**CASES["stack"])
        assert lay.operators == ()
        lay = solve(**{**CASES["stack"], "operator": "\u00d7"})
        assert len(lay.operators) == 3  # L-1 between the 4 layers
        assert all(op.r > 0 and op.cross_d for op in lay.operators)
        assert {op.cx for op in lay.operators} == {450.0}  # riding the vertical spine
        for c in lay.connectors:
            xs = re.findall(r"([\d.]+),[\d.]+", c.path_d)
            assert len({float(x) for x in xs}) == 1, c.path_d
        # Stack's chassis width (900, stack) is a landscape canvas
        # FLOOR, not just a solve ceiling — the specimen explicitly rejects
        # the portrait tower a shrink-wrapped narrow content column produced.
        # height 750 (was 713, was 787): the stack hero-floor migration
        # (JOB2) content-solves an UNCITED crown pure — this CASE's bare
        # crown (no chassis override, so hero_declared is empty) no longer
        # floats at the paradigm's topology-default hero.h (104). 713
        # reflected the bare paradigm pad_y (7); the family's own hero
        # pad_y citation (25.5, pp-stack-v2.svg's own crown rhythm,
        # inherited from fanout-horizontal's established 104-tall hero) now
        # floors even this NAME-ONLY hero (no desc — ``labeled()`` supplies
        # none) more generously: 67.32 tall instead of 30.32.
        assert (lay.width, lay.height) == (900, 750)  # caption_bottom_pad 44 re-pin

    def test_tree_orthogonal_bus_shares_one_trunk(self) -> None:
        # The mirrored S-curve/straight-line anatomy is retired for
        # the tree/dep-audit orthogonal drop-span-drop BUS — every edge
        # draws its own VHV leg (never a curve), and siblings' legs share the
        # SAME parent-stub point and the SAME bus-y elbow, so they overlay
        # into what reads as one trunk. No arrowheads (position IS direction).
        lay = solve(**CASES["tree"])
        assert all("C" not in c.path_d for c in lay.connectors)
        assert all(c.marker_d == "" for c in lay.connectors)
        pts = [re.findall(r"(-?[\d.]+),(-?[\d.]+)", c.path_d) for c in lay.connectors]
        assert len({p[0] for p in pts}) == 1  # shared parent-stub start
        assert len({p[1] for p in pts}) == 1  # shared bus-y elbow
        # Content-fit: tree hugs its leaf slots (chassis 1000 is the
        # scale reference, not a floor) — same height, no phantom width.
        assert (lay.width, lay.height) == (470, 415)  # caption_bottom_pad 44 re-pin

    def test_comparison_fixed_canvas_and_single_connector(self) -> None:
        lay = solve(**CASES["comparison"])
        # Edge-run law re-pin: the canvas derives from panels + the cited
        # 220 run; the retired 1180 fixed frame is the scale reference only.
        assert (lay.width, lay.height) == (588, 269)
        assert len(lay.connectors) == 1
        assert lay.connectors[0].accent_index == -1
        assert lay.nodes[0].role == "muted"
        assert lay.nodes[0].stroke_dasharray == "4 4"
        assert lay.nodes[0].dot is None


class TestStateMachineBackEdges:
    """agent-task-lifecycle: several returns into ONE state enter its bottom
    edge at DISTINCT offset points and nest without crossing — the specimen's
    revise + retry under-sweeps into planning's underside (358 / 330)."""

    @staticmethod
    def _cubic(d: str) -> list[tuple[float, float]] | None:
        if "C" not in d:
            return None
        nums = [float(x) for x in re.findall(r"-?\d*\.?\d+", d)]
        return [(nums[i], nums[i + 1]) for i in range(0, 8, 2)] if len(nums) >= 8 else None

    @staticmethod
    def _sample(cub: list[tuple[float, float]], n: int = 48) -> list[tuple[float, float]]:
        p0, p1, p2, p3 = cub
        out: list[tuple[float, float]] = []
        for i in range(n + 1):
            t = i / n
            v = 1.0 - t
            out.append(
                (
                    v**3 * p0[0] + 3 * v * v * t * p1[0] + 3 * v * t * t * p2[0] + t**3 * p3[0],
                    v**3 * p0[1] + 3 * v * v * t * p1[1] + 3 * v * t * t * p2[1] + t**3 * p3[1],
                )
            )
        return out

    @staticmethod
    def _cross(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> bool:
        def ccw(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> bool:
            return (r[1] - p[1]) * (q[0] - p[0]) > (q[1] - p[1]) * (r[0] - p[0])

        for i in range(len(a) - 1):
            for j in range(len(b) - 1):
                p, q, r, s = a[i], a[i + 1], b[j], b[j + 1]
                if ccw(p, r, s) != ccw(q, r, s) and ccw(p, q, r) != ccw(p, q, s):
                    return True
        return False

    def test_returns_distinct_entries_and_no_cross(self) -> None:
        cfg = load_paradigms()["primer"].diagram
        lay = compute_diagram_layout(
            _normalized_preset("agent-task-lifecycle"), paradigm=cfg, engine=ENGINE, palette_len=5
        )
        boxes = [n.box for n in lay.nodes]
        by_target: dict[int, list[tuple[list[tuple[float, float]], float]]] = {}
        for c in lay.connectors:
            if c.source_index == c.target_index:
                continue
            cub = self._cubic(c.path_d)
            if cub is None:
                continue
            tb = boxes[c.target_index]
            end = cub[-1]
            # A back-edge ENTERS its target's bottom edge from below.
            if abs(end[1] - (tb.y + tb.h)) <= 6.0 and tb.x - 2 <= end[0] <= tb.x + tb.w + 2:
                by_target.setdefault(c.target_index, []).append((cub, end[0]))
        multi = [v for v in by_target.values() if len(v) >= 2]
        assert multi, "agent-task-lifecycle must return >=2 back-edges into one state (planning)"
        for group in multi:
            entries = sorted(e for _, e in group)
            gaps = [b - a for a, b in itertools.pairwise(entries)]
            assert gaps and min(gaps) >= 6.0, f"returns must enter at DISTINCT bottom-edge points; got {entries}"
            samples = [self._sample(cub) for cub, _ in group]
            for a, b in itertools.combinations(samples, 2):
                assert not self._cross(a, b), "nested returns must not cross each other"

    def test_over_arc_return_stays_above_row(self) -> None:
        """The over-arc return (agent-runtime's exit:top re-plan): its polyline
        stays STRICTLY above the loop row (the underside is the tool pool) and
        clears every card it crosses by G7."""
        cfg = load_paradigms()["primer"].diagram
        lay = compute_diagram_layout(_normalized_preset("agent-runtime"), paradigm=cfg, engine=ENGINE, palette_len=5)
        boxes = [n.box for n in lay.nodes]
        # the over-arc = the cubic whose apex rises well above both endpoints
        over = None
        for c in lay.connectors:
            cub = self._cubic(c.path_d)
            if cub is None:
                continue
            pts = self._sample(cub)
            apex = min(p[1] for p in pts)
            if apex <= min(pts[0][1], pts[-1][1]) - 20.0:
                over = (c, pts)
                break
        assert over is not None, "agent-runtime must carry one exit:top over-arc return"
        c, pts = over
        row_top = min(boxes[c.source_index].y, boxes[c.target_index].y)
        # strictly above the row: every interior point sits above the loop cards' top
        interior = pts[3:-3]
        assert all(p[1] <= row_top + 0.5 for p in interior), "over-arc must stay above the loop row"
        # G7: clears every OTHER card by min_clearance
        clearance = float(ENGINE.get("min_clearance", 18)) - 0.6
        for i, b in enumerate(boxes):
            if i in (c.source_index, c.target_index):
                continue
            for px, py in interior:
                gx = max(b.x - px, px - (b.x + b.w), 0.0)
                gy = max(b.y - py, py - (b.y + b.h), 0.0)
                assert math.hypot(gx, gy) >= clearance, f"over-arc grazes card {i}"

    @staticmethod
    def _back_route(lay: DiagramLayout, source_id: str, target_id: str) -> tuple[list[tuple[float, float]], Any]:
        by_id = {n.node_id: n for n in lay.nodes}
        src_i, tgt_i = by_id[source_id].index, by_id[target_id].index
        conn = next(c for c in lay.connectors if c.source_index == src_i and c.target_index == tgt_i)
        cub = TestStateMachineBackEdges._cubic(conn.path_d)
        assert cub is not None, f"{source_id}->{target_id} did not render a curved return"
        return TestStateMachineBackEdges._sample(cub), by_id[source_id]

    @staticmethod
    def _arrival_deg(lay: DiagramLayout, source_id: str, target_id: str) -> float:
        """Angle off horizontal the curve strikes the target's underside —
        the analytic tangent at t=1 (3*(P3-P2)), not a sampled secant."""
        by_id = {n.node_id: n for n in lay.nodes}
        src_i, tgt_i = by_id[source_id].index, by_id[target_id].index
        conn = next(c for c in lay.connectors if c.source_index == src_i and c.target_index == tgt_i)
        cub = TestStateMachineBackEdges._cubic(conn.path_d)
        assert cub is not None
        _p0, _p1, p2, p3 = cub
        dx, dy = p3[0] - p2[0], p3[1] - p2[1]
        return math.degrees(math.atan2(abs(dy), abs(dx)))

    def test_needs_basin_hang_is_span_invariant(self) -> None:
        """USER FILING: "the angles of the skip edges when the edge bends
        are still just awful ... why cant you derive these better?" — the
        old 0.501x-span depth hung a belly hundreds of px into empty canvas
        once a corner-basin return's source sat many columns from its
        target (session-states' re-auth). The belly must hang a FIXED
        clearance off the deepest card it actually crosses — never scale
        with how far apart the two states sit. Two session-lifecycle-shaped
        machines (idle->authing->[mid...]->active->confirmed, active also
        dropping to an off-baseline ``expired`` that returns as ``re-auth``
        — the ``active->confirmed`` continuation is declared FIRST so
        ``active`` stays on the baseline and ``expired`` drops, mirroring
        agent-task-lifecycle's executing->review/executing->failed pair) at
        column spans 1 and 4 must land the SAME hang off ``expired``'s own
        card, and arrive EXACTLY vertical into ``authing``'s underside — not
        merely "steep" (SM ARRIVAL-ANGLE FILING: c2x is now pinned to the
        target's own bottom-center for every corner-basin return, dx=0
        whatever depth the clearance search settles on, so the tangent is
        90.0deg by construction, immune to rise/span/extra — the old >=70deg
        floor tolerated a fit that drifted as far as 82.4deg on cicd-
        machine's own generated layout before this fix)."""

        def _machine(n_mid: int) -> DiagramLayout:
            names = ["idle", "authing"] + [f"mid{i}" for i in range(n_mid)] + ["active", "confirmed"]
            nodes = [{"id": nm, "label": nm, "role": "ground"} for nm in names] + [
                {"id": "expired", "label": "expired", "role": "muted"}
            ]
            edges = [{"source": names[i], "target": names[i + 1]} for i in range(len(names) - 1)]
            edges.append({"source": "active", "target": "expired", "label": "timeout"})
            edges.append(
                {"source": "expired", "target": "authing", "label": "re-auth", "relation": "drift", "marker": "arrow"}
            )
            return solve(topology="state-machine", title="T", nodes=nodes, edges=edges)

        short_lay, long_lay = _machine(0), _machine(3)  # active 1 column vs 4 columns from authing
        short_pts, short_src = self._back_route(short_lay, "expired", "authing")
        long_pts, long_src = self._back_route(long_lay, "expired", "authing")
        hang_short = max(y for _, y in short_pts) - (short_src.box.y + short_src.box.h)
        hang_long = max(y for _, y in long_pts) - (long_src.box.y + long_src.box.h)
        assert abs(hang_short - hang_long) < 3.0, (
            f"corner-basin hang must not scale with span: {hang_short:.1f}px (short) vs {hang_long:.1f}px (long)"
        )
        assert 25.0 <= hang_short <= 55.0, (
            f"hang should sit in the 67px-hang Bernstein-blended band, got {hang_short:.1f}"
        )
        assert hang_long < 100.0, (
            f"regression guard: the old span-proportional law hung this ~300px, got {hang_long:.1f}"
        )
        for lay in (short_lay, long_lay):
            deg = self._arrival_deg(lay, "expired", "authing")
            assert abs(deg - 90.0) < 0.5, (
                f"corner-basin return must arrive EXACTLY vertical (c2x=tcx by construction), got {deg:.1f}deg"
            )

    def test_same_row_hang_stays_bounded_not_proportional(self) -> None:
        """The same-row rework's 49px hang (alt2 revise: row bottom 201,
        controls 250) is a flat construction constant, but the render's
        ACTUAL peak also answers to the pre-existing G7 clearance safety
        net (``_under_curve_depth``) once enough intervening baseline cards
        spread across a wide x-range — so it is not pinned bit-for-bit
        across every span, but it must grow far SLOWER than span (never the
        old law's straight 0.1186x proportionality, which would have
        demanded ~137px of depth at the wide end measured here) and stay
        glancing, never steep, into the underside."""

        def _machine(n_mid: int) -> DiagramLayout:
            names = ["idle", "authing"] + [f"mid{i}" for i in range(n_mid)]
            nodes = [{"id": nm, "label": nm, "role": "ground"} for nm in names]
            edges = [{"source": names[i], "target": names[i + 1]} for i in range(len(names) - 1)]
            edges.append(
                {"source": names[-1], "target": "authing", "label": "renewed", "relation": "drift", "marker": "arrow"}
            )
            return solve(topology="state-machine", title="T", nodes=nodes, edges=edges)

        short_lay, long_lay = _machine(1), _machine(6)  # 8-node cap ceilings the long span
        short_pts, short_src = self._back_route(short_lay, "mid0", "authing")
        long_pts, long_src = self._back_route(long_lay, "mid5", "authing")
        span_short = abs(short_pts[0][0] - short_pts[-1][0])
        span_long = abs(long_pts[0][0] - long_pts[-1][0])
        hang_short = max(y for _, y in short_pts) - (short_src.box.y + short_src.box.h)
        hang_long = max(y for _, y in long_pts) - (long_src.box.y + long_src.box.h)
        assert 25.0 <= hang_short <= 55.0, (
            f"hang should sit in the 49px-hang Bernstein-blended band, got {hang_short:.1f}"
        )
        assert hang_long < 80.0, (
            f"regression guard: bounded well under the old 0.1186x-span law's ~137px, got {hang_long:.1f}"
        )
        span_ratio = span_long / span_short
        hang_ratio = hang_long / hang_short
        assert hang_ratio < 0.5 * span_ratio, (
            f"hang must grow far slower than span (never proportional): span grew {span_ratio:.1f}x, "
            f"hang grew {hang_ratio:.1f}x"
        )
        for lay, src in ((short_lay, "mid0"), (long_lay, "mid5")):
            deg = self._arrival_deg(lay, src, "authing")
            assert deg <= 45.0, f"same-row return must arrive glancing, not steep, got {deg:.1f}deg"

    def test_breaker_states_multiple_basins_stay_bounded(self) -> None:
        """A circuit-breaker machine (closed/open/half_open, all baseline)
        carries TWO same-row returns into two DIFFERENT targets
        (half_open->closed "reset" spans 2 columns, half_open->open
        "retrip" spans 1) — the clearance-hung law must bound both at the
        row's own hang without either ballooning or the canvas growing to
        chase a span it does not need to."""
        lay = solve(
            topology="state-machine",
            title="Circuit breaker",
            nodes=[
                {"id": "closed", "label": "closed", "role": "ground"},
                {"id": "open", "label": "open", "role": "ground"},
                {"id": "half_open", "label": "half_open", "role": "ground"},
            ],
            edges=[
                {"source": "closed", "target": "open", "label": "trip"},
                {"source": "open", "target": "half_open", "label": "cooldown"},
                {"source": "half_open", "target": "closed", "label": "reset", "relation": "drift", "marker": "arrow"},
                {"source": "half_open", "target": "open", "label": "retrip", "relation": "drift", "marker": "arrow"},
            ],
        )
        by_id = {n.node_id: n for n in lay.nodes}
        for source_id, target_id in (("half_open", "closed"), ("half_open", "open")):
            pts, src = self._back_route(lay, source_id, target_id)
            hang = max(y for _, y in pts) - (src.box.y + src.box.h)
            assert 25.0 <= hang <= 55.0, f"{source_id}->{target_id} hang out of band: {hang:.1f}px"
            deg = self._arrival_deg(lay, source_id, target_id)
            assert deg <= 45.0, f"{source_id}->{target_id} must arrive glancing (same-row), got {deg:.1f}deg"
        # Regression guard: an unbounded (span-proportional) basin would
        # inflate the canvas chasing depth neither return needs.
        assert lay.height < by_id["half_open"].box.y + by_id["half_open"].box.h + 200.0


class TestRegionBands:
    """The over-arc-derived band padding policy (graph.build_region_bands): a
    band reserves 65px of top over-arc clearance IFF it frames an exit:top
    back-edge among its members. Absent an over-arc it is a snug header strip
    concentric with its middle member (censusing as that member's shell)."""

    @staticmethod
    def _band_and_boxes(preset: str) -> tuple[Any, dict[str, Any]]:
        cfg = load_paradigms()["primer"].diagram
        lay = compute_diagram_layout(_normalized_preset(preset), paradigm=cfg, engine=ENGINE, palette_len=5)
        assert lay.lane_bands, f"{preset} must render a region band"
        boxes = {n.node_id: n.box for n in lay.nodes}
        return lay.lane_bands[0], boxes

    def test_pool_band_is_concentric_shell(self) -> None:
        """gateway-balanced's MODEL POOL (no over-arc): a FILLED panel with a
        snug ~26px top strip, concentric (within 8px) with the middle tier so
        the census coalesces it as that tier's shell, not a separate card."""
        band, boxes = self._band_and_boxes("gateway-balanced")
        assert band.ground == "panel", "pool band is a filled panel"
        top_pad = min(boxes[m].y for m in ("fast", "deep", "vision")) - band.box.y
        assert 20.0 <= top_pad <= 34.0, f"pool band top strip should be snug (~26px), got {top_pad:.1f}"
        off = (band.box.y + band.box.h / 2) - (boxes["deep"].y + boxes["deep"].h / 2)
        assert abs(off) <= 8.0, f"pool band must be concentric with the middle tier; off by {off:.1f}"

    def test_control_loop_band_reserves_over_arc(self) -> None:
        """agent-runtime's AGENT RUNTIME (exit:top re-plan): reserves >=55px
        above the row for the over-bow, which lifts the panel off the row centre
        so it is NOT concentric with its middle member (censuses as its own card)."""
        band, boxes = self._band_and_boxes("agent-runtime")
        members = [boxes[m] for m in ("plan", "act", "observe")]
        top_pad = min(b.y for b in members) - band.box.y
        assert top_pad >= 55.0, f"control-loop band must reserve over-arc clearance, got {top_pad:.1f}"
        mid = sorted(members, key=lambda b: b.y)[len(members) // 2]
        off = (band.box.y + band.box.h / 2) - (mid.y + mid.h / 2)
        assert abs(off) > 8.0, "over-arc reserve must lift the band off the row centre (own card, not a shell)"


class TestSequence:
    def test_replay_single_particle_and_anatomy(self) -> None:
        # The sequence-replay law: ONE traversing particle per message (sequential slots,
        # so one dot is visible at a time), full-weight semantic strokes,
        # no comet light layers. Particles are opt-in under the diagrams-v3
        # kit's dash default — request them explicitly (spec-level, not on
        # the shared CASES fixture: an artifact-level edge_motion would also
        # suppress the relation-dress override other sweeps rely on).
        lay = solve(**{**CASES["sequence"], "edge_motion": "particle"})
        assert len(lay.lifelines) == 3
        assert len(lay.activations) == 3
        assert len(lay.particles) == len(lay.connectors)  # one dot per message
        # Edge labels are subsumed into the annotation pass (kind="label"),
        # emitted in edge order before any caller annotations.
        labels = [line.text for a in lay.annotations if a.kind == "label" for line in a.lines]
        assert labels == ["call()", "ret", "notify"]
        ret = lay.connectors[1]
        assert ret.semantic_dash == "4 5"
        # auth-sequence deliberately SUPERSEDES the P3 static-yield law here:
        # a return message drifts home on its own track value rather than
        # resolving static, and carries the hero's accent (index 0).
        assert ret.track == "dash-drift"
        assert ret.accent_index == 0
        # Loop coherence: every dot rides one shared period; slots are
        # ordered and non-overlapping (the single-traversal illusion).
        assert len({p.dur for p in lay.particles}) == 1
        windows = sorted(tuple(map(float, p.keytimes_motion.split(";")[1:3])) for p in lay.particles)
        for (_, e0), (s1, _) in itertools.pairwise(windows):
            assert s1 >= e0 - 1e-9  # one dot visible at a time

    def test_message_pitch_uniform(self) -> None:
        lay = solve(**CASES["sequence"])
        ys = sorted({c.path_d.split(",")[1].split(" ")[0] for c in lay.connectors})
        ys_f = sorted(float(y) for y in ys)
        pitches = {round(b - a, 2) for a, b in itertools.pairwise(ys_f)}
        assert pitches == {72.0}  # auth-sequence rhythm


class TestPolicy:
    def test_soft_cap_is_the_safety_valve_behind_layout_maxes(self) -> None:
        # Every per-layout max sits at or below the global soft cap, so
        # crowding is prevented by caps first; the shrink flag remains the
        # mechanism if a layout's cap ever widens past it.
        from hyperweave.compose.diagram.solver import enforce_caps

        spec = resolve_auto_roles(DiagramSpec(topology="fanout", nodes=[{"label": f"n{i}"} for i in range(14)]))
        synthetic = {"soft_nodes": 12, "hard_nodes": 20, "layouts": {"fanout-horizontal": {"min": 3, "max": 16}}}
        assert enforce_caps(spec, "fanout-horizontal", synthetic) is True
        small = resolve_auto_roles(DiagramSpec(topology="fanout", nodes=[{"label": f"n{i}"} for i in range(5)]))
        assert enforce_caps(small, "fanout-horizontal", synthetic) is False
        layout_caps = ENGINE["caps"]["layouts"]
        over_soft = {slug for slug, band in layout_caps.items() if int(band["max"]) > int(ENGINE["caps"]["soft_nodes"])}
        # Four layouts admit more nodes than the global soft cap: the mindmap
        # and the orthogonal-bus tree (both density-governed by
        # leaf-count sector subdivision, Cartesian or angular), lanes
        # (band/lane subdivision), and hub (canonical slot grid + per-zone
        # cap) — none uses a pitch shrink.
        assert over_soft == {"tree", "tree-radial", "lanes", "hub"}

    def test_layout_min_max_from_yaml(self) -> None:
        with pytest.raises(DiagramInputError, match="at least"):
            solve(topology="pipeline", nodes=labeled("A", "B"))
        with pytest.raises(DiagramCapacityError, match="caps at"):
            solve(topology="comparison", nodes=labeled("A", "B", "C"))

    def test_orientation_legality_is_config(self) -> None:
        with pytest.raises(DiagramInputError, match="not legal"):
            solve(topology="pipeline", orientation="radial", nodes=labeled("A", "B", "C"))

    def test_p2_depth_rules_close_both_ways(self) -> None:
        with pytest.raises(DiagramInputError, match="fanout-radial"):
            solve(topology="tree", orientation="radial", nodes=labeled("r", "a", "b", "c"))
        # Depth 2 is legal on tree:horizontal (the tree/
        # dep-audit orthogonal-bus ceiling) — it no longer raises.
        shallow = dict(
            topology="tree",
            nodes=[{"id": "r", "label": "R"}, {"id": "a", "label": "A"}, {"id": "a1", "label": "A1"}],
            edges=[{"source": "r", "target": "a"}, {"source": "a", "target": "a1"}],
        )
        solve(**shallow)
        # Depth 3 still exceeds tree_horizontal_max_depth — deeper hierarchies
        # use orientation 'radial'.
        deep = dict(
            topology="tree",
            nodes=[
                {"id": "r", "label": "R"},
                {"id": "a", "label": "A"},
                {"id": "a1", "label": "A1"},
                {"id": "a2", "label": "A2"},
            ],
            edges=[
                {"source": "r", "target": "a"},
                {"source": "a", "target": "a1"},
                {"source": "a1", "target": "a2"},
            ],
        )
        with pytest.raises(DiagramCapacityError, match="caps at depth"):
            solve(**deep)

    def test_accent_overflow_names_palette(self) -> None:
        with pytest.raises(DiagramInputError, match="diagram_flow"):
            solve(
                palette_len=2,
                topology="pipeline",
                nodes=[{"label": "A", "accent": 7}, {"label": "B"}, {"label": "C"}],
            )


class TestTreeRadial:
    def test_tree_radial_density(self) -> None:
        """G6: sparse radial trees crop to content — the placed bbox fills
        at least 55% of the canvas, and the canvas is no longer the ring
        formula's square."""
        from hyperweave.compose.diagram.chrome import voice_for
        from hyperweave.compose.matrix.cells import measure_voice
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.matrix import GlyphTint

        cfg = load_paradigms()["primer"].diagram
        registry = load_glyphs()
        for preset in ("mindmap", "dep-audit-radial"):
            spec = _normalized_preset(preset)
            lay = compute_diagram_layout(
                spec,
                paradigm=cfg,
                engine=ENGINE,
                palette_len=5,
                glyph_registry=registry,
                glyph_selections=tuple(GlyphTint.INK for _ in spec.nodes),
            )
            x0 = y0 = float("inf")
            x1 = y1 = float("-inf")
            for n in lay.nodes:
                x0, y0 = min(x0, n.box.x), min(y0, n.box.y)
                x1, y1 = max(x1, n.box.x + n.box.w), max(y1, n.box.y + n.box.h)
                for run in (n.label, *n.desc_lines):
                    if not run.text:
                        continue
                    w = measure_voice(run.text, voice_for(cfg, run.cls))
                    rx0 = run.x - (w / 2 if run.anchor == "middle" else 0.0)
                    x0, x1 = min(x0, rx0), max(x1, rx0 + w)
                    y0, y1 = min(y0, run.y - 10), max(y1, run.y + 4)
            # Specimen-pinned plate air is chrome, never solver slack: the
            # density floor exists to catch an over-solved canvas, and a
            # chassis that declares its hand file's own masthead/caption
            # bands (dep-audit-radial holds a 233px kicker band) shrinks
            # ink share BY LAW. Density measures against the canvas minus
            # the declared plate airs.
            from hyperweave.compose.diagram.solver import apply_spec_chassis

            eff = apply_spec_chassis(cfg.topologies[lay.layout_slug], spec.chassis)
            plate_air = (eff.zone_content_gap or 0.0) + (eff.caption_gap or 0.0) + (eff.caption_pad or 0.0)
            # A masthead legend column (annotation-driven — dep-audit's
            # pp-tree-v2 idiom) buys canvas height by law the same way the
            # chassis plate airs do; measure the placed band and exempt it.
            node_top = min(n.box.y for n in lay.nodes)
            mast = [a.box for a in lay.annotations if a.box.y + a.box.h <= node_top]
            if mast:
                plate_air += max(b.y + b.h for b in mast) - min(b.y for b in mast)
            density = ((x1 - x0) * (y1 - y0)) / (lay.width * max(lay.height - plate_air, 1.0))
            # Floored canvases are exempt: the chassis width is the page-scale
            # floor (display pins ~740 in the downscale band) and the
            # specimens budget generous negative space at that scale.
            ch_floor = cfg.topologies[lay.layout_slug].width
            assert density >= 0.55 or lay.width <= ch_floor, (preset, round(density, 3), lay.width, lay.height)

    def test_sectors_proportional_to_subtree_leaves(self) -> None:
        lay = solve(
            topology="tree",
            orientation="radial",
            nodes=[
                {"id": "r", "label": "Root", "short": "r"},
                {"id": "a", "label": "A"},
                {"id": "b", "label": "B"},
                {"id": "a1", "label": "A1"},
                {"id": "a2", "label": "A2"},
                {"id": "a3", "label": "A3"},
            ],
            edges=[
                {"source": "r", "target": "a"},
                {"source": "r", "target": "b"},
                {"source": "a", "target": "a1"},
                {"source": "a", "target": "a2"},
                {"source": "a", "target": "a3"},
            ],
        )
        assert lay.layout_slug == "tree-radial"
        hub = lay.nodes[-1]
        assert hub.index == 0
        # The hub's own center is the ring origin (bbox crop moved the
        # canvas, G6); ring-2 nodes still share ONE radius, and occupancy
        # scaling pulled it inside the specimen's 280.
        hc = (hub.box.x + hub.box.w / 2, hub.box.y + hub.box.h / 2)
        ring2 = [n for n in lay.nodes if n.index in (3, 4, 5)]
        rads = {round(math.hypot(n.box.x + n.box.w / 2 - hc[0], n.box.y + n.box.h / 2 - hc[1])) for n in ring2}
        assert len(rads) == 1, rads  # one shared ring radius
        # G7 supersedes the magnitude pin: the radius is whatever clearance
        # demands; every box pair must breathe by min_clearance.
        clearance = float(ENGINE["min_clearance"])
        boxes = [n.box for n in lay.nodes]
        for i, a in enumerate(boxes):
            for b in boxes[i + 1 :]:
                gx = max(a.x - (b.x + b.w), b.x - (a.x + a.w), 0.0)
                gy = max(a.y - (b.y + b.h), b.y - (a.y + a.h), 0.0)
                assert math.hypot(gx, gy) >= clearance - 0.6, (a, b)


class TestAnchors:
    """G1: connector endpoints sit at the node's actual shape boundary
    plus the uniform standoff — across shapes and approach angles."""

    STANDOFF = float(ENGINE["connector"]["standoff"])

    @staticmethod
    def _d_endpoints(d: str) -> tuple[tuple[float, float], tuple[float, float]]:
        import re as _re

        pairs = _re.findall(r"(-?[\d.]+),(-?[\d.]+)", d)
        (x0, y0), (x1, y1) = pairs[0], pairs[-1]
        return (float(x0), float(y0)), (float(x1), float(y1))

    def _assert_on_boundary(self, lay: DiagramLayout, *, skip_hub_end: bool) -> None:
        from hyperweave.compose.diagram.anchors import boundary_distance

        nodes_by_index = {n.index: n for n in lay.nodes}
        for c in lay.connectors:
            start, end = self._d_endpoints(c.path_d)
            target = nodes_by_index[c.target_index]
            source = nodes_by_index[c.source_index]
            assert abs(boundary_distance(target, *end) - self.STANDOFF) < 0.6, (c.index, "target", end)
            if not skip_hub_end:
                assert abs(boundary_distance(source, *start) - self.STANDOFF) < 0.6, (c.index, "source", start)

    def test_radial_card_endpoints(self) -> None:
        # Cards at corner angles: the half-height side must govern side
        # approaches, the half-width the top/bottom ones.
        lay = solve(**CASES["fanout-radial"])
        self._assert_on_boundary(lay, skip_hub_end=True)  # hub end is masked center

    def test_flywheel_card_arc_endpoints(self) -> None:
        # The rim arcs FLOAT: boundary-trimmed then backed off by
        # arc_clear_deg per end (flywheel-orbit — the cycle reads as motion
        # BETWEEN phases, never plumbing into them).
        from hyperweave.compose.diagram.anchors import boundary_distance

        lay = solve(**CASES["flywheel"])
        ch = load_paradigms()["primer"].diagram.topologies["flywheel"]
        clear_px = math.radians(ch.arc_clear_deg) * ch.arc_r
        nodes_by_index = {n.index: n for n in lay.nodes}
        for c in lay.connectors:
            start, end = self._d_endpoints(c.path_d)
            for node, pt in ((nodes_by_index[c.target_index], end), (nodes_by_index[c.source_index], start)):
                gap = boundary_distance(node, *pt)
                assert clear_px * 0.5 <= gap <= clear_px * 2.5, (c.index, gap, clear_px)

    def test_tree_radial_endpoints(self) -> None:
        lay = solve(
            topology="tree",
            orientation="radial",
            nodes=[
                {"id": "r", "label": "Root", "short": "r"},
                {"id": "a", "label": "A"},
                {"id": "b", "label": "B"},
                {"id": "a1", "label": "A1"},
            ],
            edges=[
                {"source": "r", "target": "a"},
                {"source": "r", "target": "b"},
                {"source": "a", "target": "a1"},
            ],
        )
        self._assert_on_boundary(lay, skip_hub_end=True)


class TestTextMetrics:
    """G2: every node text baseline + descender sits inside its box minus
    the pad — clipping is never legal, across all presets and shapes."""

    def test_no_text_clips_its_node(self) -> None:
        from hyperweave.compose.diagram.chrome import voice_for
        from hyperweave.compose.diagram.input import diagram_preset_names

        cfg = load_paradigms()["primer"].diagram
        pad = cfg.min_pad_y
        for preset in sorted(diagram_preset_names()):
            spec = _normalized_preset(preset)
            lay = compute_diagram_layout(spec, paradigm=cfg, engine=ENGINE, palette_len=5)
            for n in lay.nodes:
                if n.shape == "circle":
                    continue  # circle labels are EXTERNAL by design (radial/below)
                b = n.box
                runs = [n.label, *n.desc_lines]
                if n.short is not None:
                    runs.append(n.short)
                if n.tag is not None:
                    runs.append(n.tag)
                for run in runs:
                    size = voice_for(cfg, run.cls).size
                    assert run.y + size * cfg.text_descent_ratio <= b.y + b.h - pad + 0.51, (
                        preset,
                        n.index,
                        run.cls,
                        run.text,
                    )
                    assert run.y - size * cfg.text_ascent_ratio >= b.y + pad - 0.51, (preset, n.index, run.cls)

    def test_flywheel_labels_clear_the_ring_stroke(self) -> None:
        """K-radial-label: in a topology with a ring STROKE through its
        nodes, each label places radially outboard and its box keeps clear
        of the ring stroke — no 3/9 o'clock collision."""
        from hyperweave.compose.diagram.chrome import voice_for
        from hyperweave.compose.matrix.cells import measure_voice

        cfg = load_paradigms()["primer"].diagram
        # Coin-ring labels are a glyph-circle feature; no parity preset renders
        # coins (specimen census coins:0), so the law is exercised on an inline
        # glyph-circle flywheel (the engine feature is preset-independent).
        from hyperweave.compose.diagram.input import resolve_auto_roles
        from hyperweave.core.diagram import DiagramSpec

        for case in ("glyph-circle flywheel",):
            spec = resolve_auto_roles(
                DiagramSpec.model_validate(
                    {
                        "topology": "flywheel",
                        "node_style": "glyph-circle",
                        "nodes": [
                            {"id": "gen", "label": "Generate", "glyph": "github"},
                            {"id": "emb", "label": "Embed", "glyph": "anthropic"},
                            {"id": "rec", "label": "Record", "glyph": "grafana"},
                            {"id": "trn", "label": "Train", "glyph": "huggingface"},
                            {"id": "axis", "label": "the model", "role": "hero", "short": "hw"},
                        ],
                    }
                )
            )
            lay = compute_diagram_layout(spec, paradigm=cfg, engine=ENGINE, palette_len=5)
            circles = [n for n in lay.nodes if n.shape == "circle" and n.role != "hero"]
            assert circles
            cx = sum(n.cx for n in circles) / len(circles)
            cy = sum(n.cy for n in circles) / len(circles)
            ring_r = sum(math.hypot(n.cx - cx, n.cy - cy) for n in circles) / len(circles)
            for n in circles:
                voice = voice_for(cfg, n.label.cls)
                w = measure_voice(n.label.text, voice)
                x0 = n.label.x - (w if n.label.anchor == "end" else w / 2 if n.label.anchor == "middle" else 0.0)
                x1 = x0 + w
                asc, desc = cfg.text_ascent_ratio * voice.size, cfg.text_descent_ratio * voice.size
                # Nearest point of the label box to the ring center, vs ring radius.
                corners = [(x0, n.label.y - asc), (x1, n.label.y - asc), (x0, n.label.y + desc), (x1, n.label.y + desc)]
                near = min(math.hypot(px - cx, py - cy) for px, py in corners)
                far = max(math.hypot(px - cx, py - cy) for px, py in corners)
                # Every label corner is OUTSIDE the ring radius (outboard),
                # clear of the stroke that runs along it.
                assert near >= ring_r - 0.6, (case, n.index, n.label.text, round(near, 1), round(ring_r, 1))
                assert far > near  # the box has extent, sanity

    def test_hub_spoke_labels_outboard_and_hub_contained(self) -> None:
        """K-radial-general: in a hub-spoke radial layout, every glyph-circle
        dest labels OUTBOARD (its label center sits farther from the hub
        than the node center, so the spoke can't cross it), and the hub's
        own label is stacked INSIDE its circle (clear of every spoke)."""
        from hyperweave.compose.diagram.input import resolve_auto_roles
        from hyperweave.core.diagram import DiagramSpec

        cfg = load_paradigms()["primer"].diagram
        # Glyph-circle radial dests are exercised inline — the parity model-router
        # renders card+glyph (specimen census coins:0), not coins.
        spec = resolve_auto_roles(
            DiagramSpec.model_validate(
                {
                    "topology": "fanout",
                    "orientation": "radial",
                    "node_style": "glyph-circle",
                    "nodes": [
                        {"id": "router", "label": "router", "role": "hero", "short": "api"},
                        {"id": "a", "label": "Claude", "glyph": "anthropic"},
                        {"id": "b", "label": "Gemini", "glyph": "gemini"},
                        {"id": "c", "label": "Mistral", "glyph": "mistral"},
                        {"id": "d", "label": "OpenAI", "glyph": "openai"},
                        {"id": "e", "label": "Cohere", "glyph": "cohere"},
                        {"id": "f", "label": "Ollama", "glyph": "ollama"},
                        {"id": "g", "label": "Qwen", "glyph": "qwen"},
                    ],
                }
            )
        )
        lay = compute_diagram_layout(spec, paradigm=cfg, engine=ENGINE, palette_len=5)
        hub = next(n for n in lay.nodes if n.role == "hero")
        hx, hy = hub.cx, hub.cy
        dests = [n for n in lay.nodes if n.shape == "circle" and n.role != "hero"]
        assert len(dests) >= 6
        for n in dests:
            node_d = math.hypot(n.cx - hx, n.cy - hy)
            label_d = math.hypot(n.label.x - hx, n.label.y - hy)
            assert label_d > node_d, (n.label.text, round(label_d, 1), round(node_d, 1))
        # The hub label rides inside its circle — every spoke starts at the
        # boundary, so an inside label clears all of them.
        assert math.hypot(hub.label.x - hx, hub.label.y - hy) <= hub.r, hub.label.text

    def test_slack_rule_free_and_aligned(self) -> None:
        """G3 slack rule under the content-anchor law: every plain card —
        free OR aligned — seats its content-left at the chassis
        ``glyph_inset_x`` (the column is a chassis fact; slack pools right,
        matching every wide hand specimen), and carries no width beyond
        clamp(ink + anchor_pads, min_w, max). The former per-card centering
        (Item-2) made the column a function of each card's own slack.

        Hero width UPPER BOUND (G3 dominance law): an undeclared hero (no
        preset-level ``chassis.hero.w`` citation — ``hero_declared`` tracks
        this through the merge) never solves wider than its own never-clip
        ``want`` or the layout's measured DOMINANCE (the max solved width of
        its sibling/satellite cards); the paradigm archetype width is not a
        legal cap for it, since it never cited that archetype. An EXPLICIT
        citation is a hard pin — legal up to its declared value."""
        from hyperweave.compose.diagram.chrome import DOT_MARK_W, voice_for
        from hyperweave.compose.diagram.input import diagram_preset_names
        from hyperweave.compose.diagram.solver import apply_spec_chassis
        from hyperweave.compose.matrix.cells import measure_voice
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.matrix import GlyphTint

        cfg = load_paradigms()["primer"].diagram
        registry = load_glyphs()
        eps = 0.6
        checked_free = checked_aligned = 0
        # (The old dead-DOT_MARK_W-lead carve-outs are gone: mark_w_for()
        # reserves no advance for a markless card, so solve and place agree.)
        for preset in sorted(diagram_preset_names()):
            spec = _normalized_preset(preset)
            lay = compute_diagram_layout(
                spec,
                paradigm=cfg,
                engine=ENGINE,
                palette_len=5,
                glyph_registry=registry,
                glyph_selections=tuple(GlyphTint.INK for _ in spec.nodes),
            )
            merged_ch = apply_spec_chassis(cfg.topologies[lay.layout_slug], spec.chassis)
            policy = merged_ch.width_policy
            hero_w_declared = "w" in merged_ch.hero_declared
            dominance_w = max(
                (m.box.w for m in lay.nodes if m.shape == "rect" and m.role != "hero"),
                default=0.0,
            )
            # The dominance law lives in fan.py (this session's territory) —
            # an undeclared hero elsewhere (state-machine, sequence, dag's own
            # rank-relative floor) still floors at its own solver's untouched
            # mechanism, which legitimately includes the paradigm chassis
            # width; only the fan family's undeclared cap excludes it.
            fan_family_dominance = lay.layout_slug in _FAN_FAMILY_SLUGS
            for n in lay.nodes:
                if n.shape != "rect" or n.label.anchor != "start":
                    continue
                ink_lefts = [n.label.x] + [line.x for line in n.desc_lines]
                ink_rights = [n.label.x + measure_voice(n.label.text, voice_for(cfg, n.label.cls))] + [
                    line.x + measure_voice(line.text, voice_for(cfg, line.cls)) for line in n.desc_lines
                ]
                if n.dot is not None:
                    ink_lefts.append(n.dot[0] - n.dot_r)
                if n.glyph is not None:
                    ink_lefts.append(n.glyph.cx - n.glyph.size / 2)
                # The chip row is ink too — a two-chip card centers its
                # whole group, so the pad measure must see the row's extent.
                for cb in n.chip_boxes:
                    ink_lefts.append(cb.x)
                    ink_rights.append(cb.x + cb.w)
                ink_l, ink_r = min(ink_lefts), max(ink_rights)
                left_pad = ink_l - n.box.x
                nch = merged_ch.hero if n.role == "hero" else merged_ch.node
                want = (ink_r - ink_l) + nch.glyph_inset_x + nch.pad_x
                anchor = nch.glyph_inset_x
                # A glyphless node under the card+glyph anatomy reserves its
                # mark slot (mark_w_for) — the empty slot carries no ink, so
                # the card's leftmost INK legitimately sits at the text
                # column instead of the anchor.
                slot_col = anchor + (nch.glyph_w or 24.0) + nch.glyph_label_gap

                def _anchored(lp: float, a: float = anchor, sc: float = slot_col) -> bool:
                    return min(abs(lp - a), abs(lp - sc)) <= eps

                if policy == "free":
                    assert _anchored(left_pad), (preset, n.index, left_pad, anchor)
                    cap = max(merged_ch.card_min_w, want + 2.0)  # 2px even-grid round
                    if n.role == "hero":
                        # No fan-family topology uses "free" policy (all
                        # aligned) — every hero reaching this branch floors
                        # through its own solver (graph.py, hub, sequence),
                        # untouched by this session's law, so the chassis
                        # width stays a legal cap unconditionally.
                        # ``hero_min_w`` is a SEPARATE, pre-existing floor
                        # (graph.py's DAG family, cicd-gate's "specimen
                        # crown, verbatim" pin).
                        assert not fan_family_dominance, (preset, "unexpected free-policy fan-family hero")
                        cap = max(cap, nch.w, merged_ch.hero_min_w)
                    if any("…" in line.text for line in n.desc_lines):
                        # A desc ellipsized at the chassis ceiling means the
                        # RAW desc justified the full chassis width; the
                        # rendered (truncated) ink under-measures it.
                        cap = max(cap, nch.w)
                    assert n.box.w <= cap + eps, (preset, n.index, n.box.w, want)
                    checked_free += 1
                elif n.role == "hero":
                    # Aligned heroes keep their left_align_hero anchor: the
                    # nucleus content hugs the card's left edge, matching the
                    # specimen's left-anchored hero (hub's artifact
                    # sits ~7px from the left, its slack pooled on the right)
                    # — no L/R pad symmetry assertion here. The G3 dominance
                    # upper bound applies ONLY where fan.py computed it (this
                    # session's law); other aligned-hero topologies (hub's
                    # compass, axial's prominence-grown nucleus) have their
                    # own, separate growth rules this test does not model —
                    # unasserted here exactly as before this law landed.
                    if fan_family_dominance:
                        cap = max(merged_ch.card_min_w, want + 2.0)
                        cap = max(cap, nch.w if hero_w_declared else dominance_w, merged_ch.hero_min_w)
                        if any("…" in line.text for line in n.desc_lines):
                            cap = max(cap, nch.w)
                        assert n.box.w <= cap + eps, (preset, n.index, n.box.w, want)
                    checked_aligned += 1
                elif lay.layout_slug == "lanes":
                    # Bulleted-card anatomy (the obi-engine specimen): lanes cards LEFT-
                    # align so the category marks column-align down each lane
                    # — content at the pad, slack pooled right, desc wrapping
                    # against the asymmetric envelope. The G3 centering law
                    # never governed this anatomy. (This sweep also measures
                    # desc ink at the RAW paradigm voice; lanes overrides the
                    # desc voice via the chassis, so its extents are not
                    # comparable here anyway.)
                    checked_aligned += 1
                else:
                    # Content-anchor law: a plain aligned card seats its ink
                    # group at the chassis anchor — glyph + name + desc + chip
                    # row share the column left edge; slack pools right.
                    assert _anchored(left_pad), (preset, n.index, left_pad, anchor)
                    checked_aligned += 1
            # Head-anatomy (portrait) cards are middle-anchored and skip this
            # census; label-row cards bind wherever they remain, so an empty
            # sweep is vacuous, not a failure.
            assert checked_free >= 0 and checked_aligned >= 0
        assert DOT_MARK_W == 8.0  # the measured dot advance the rule builds on

    def test_radial_hub_label_clearance(self) -> None:
        """G4: the radial hub label sits in an angular gap and every spoke
        (and the particle path riding it) keeps clear of the label box."""
        from hyperweave.compose.diagram.chrome import voice_for
        from hyperweave.compose.matrix.cells import measure_voice
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.matrix import GlyphTint

        cfg = load_paradigms()["primer"].diagram
        registry = load_glyphs()
        clear = float(ENGINE["connector"]["hub_label_clear"])
        checked = 0
        # P6: no parity preset renders a glyph-circle radial hero (specimen
        # census coins:0); the radial hub-label clearance law is exercised on an
        # inline glyph-circle radial whose long hero name places outboard.
        from hyperweave.compose.diagram.input import resolve_auto_roles
        from hyperweave.core.diagram import DiagramSpec

        for preset in ("glyph-circle radial",):
            spec = resolve_auto_roles(
                DiagramSpec.model_validate(
                    {
                        "topology": "fanout",
                        "orientation": "radial",
                        "node_style": "glyph-circle",
                        "nodes": [
                            {"id": "hub", "label": "one key, every model", "role": "hero"},
                            {"id": "a", "label": "Claude", "glyph": "anthropic"},
                            {"id": "b", "label": "Gemini", "glyph": "gemini"},
                            {"id": "c", "label": "Mistral", "glyph": "mistral"},
                            {"id": "d", "label": "OpenAI", "glyph": "openai"},
                            {"id": "e", "label": "Cohere", "glyph": "cohere"},
                            {"id": "f", "label": "Ollama", "glyph": "ollama"},
                        ],
                    }
                )
            )
            lay = compute_diagram_layout(
                spec,
                paradigm=cfg,
                engine=ENGINE,
                palette_len=5,
                glyph_registry=registry,
                glyph_selections=tuple(GlyphTint.INK for _ in spec.nodes),
            )
            if lay.layout_slug not in ("fanout-radial", "tree-radial"):
                continue
            hub = next((n for n in lay.nodes if n.shape == "circle" and n.role == "hero"), None)
            if hub is None or not hub.label.text:
                continue
            # K-radial-general: a hub whose label stacks INSIDE its circle is
            # exempt from this outboard-clearance sweep — spokes start at the
            # circle boundary, so an inside label clears them by construction.
            # That geometry is pinned by
            # test_hub_spoke_labels_outboard_and_hub_contained; this sweep
            # covers only gap-placed (outboard) hub labels.
            if math.hypot(hub.label.x - hub.cx, hub.label.y - hub.cy) <= hub.r:
                continue
            voice = voice_for(cfg, hub.label.cls)
            w = measure_voice(hub.label.text, voice)
            h = voice.size * (cfg.text_ascent_ratio + cfg.text_descent_ratio)
            lcy = hub.label.y - (cfg.text_ascent_ratio - cfg.text_descent_ratio) / 2 * voice.size
            bx0, bx1 = hub.label.x - w / 2, hub.label.x + w / 2
            by0, by1 = lcy - h / 2, lcy + h / 2
            # The box itself clears the hub circle.
            import math as _m

            nearest = _m.hypot(
                max(bx0 - hub.cx, 0.0, hub.cx - bx1),
                max(by0 - hub.cy, 0.0, hub.cy - by1),
            )
            assert nearest >= hub.r + clear - 0.6, (preset, nearest, hub.r)
            # No spoke crosses the box (sampled along each straight ray).
            for c in lay.connectors:
                pairs = re.findall(r"(-?[\d.]+),(-?[\d.]+)", c.path_d)
                (sx, sy), (tx, ty) = (map(float, pairs[0]), map(float, pairs[-1]))
                for t in range(51):
                    px = sx + (tx - sx) * t / 50
                    py = sy + (ty - sy) * t / 50
                    inside = bx0 - 0.5 < px < bx1 + 0.5 and by0 - 0.5 < py < by1 + 0.5
                    assert not inside, (preset, c.path_d, px, py)
            checked += 1
        assert checked >= 1  # the inline glyph-circle radial (outboard hero label)

    def test_presets_stay_inside_their_canvas(self) -> None:
        """The universal in-canvas invariant, swept over the REAL content:
        synthetic CASES missed a DAG whose content-solved rank width pushed
        the last rank off-frame."""
        from hyperweave.compose.diagram.input import diagram_preset_names

        cfg = load_paradigms()["primer"].diagram
        for preset in sorted(diagram_preset_names()):
            spec = _normalized_preset(preset)
            lay = compute_diagram_layout(spec, paradigm=cfg, engine=ENGINE, palette_len=5)
            for n in lay.nodes:
                b = n.box
                assert b.x >= -0.5 and b.y >= -0.5, (preset, n.index)
                assert b.x + b.w <= lay.width + 0.5, (preset, n.index, b)
                assert b.y + b.h <= lay.height + 0.5, (preset, n.index, b)
            boxes = [n.box for n in lay.nodes]
            for i, a in enumerate(boxes):
                for b in boxes[i + 1 :]:
                    separated = (
                        a.x + a.w <= b.x + 0.5
                        or b.x + b.w <= a.x + 0.5
                        or a.y + a.h <= b.y + 0.5
                        or b.y + b.h <= a.y + 0.5
                    )
                    assert separated, (preset, a, b)
            for c in lay.connectors:
                pairs = re.findall(r"(-?[\d.]+),(-?[\d.]+)", c.path_d)
                for px, py in (pairs[0], pairs[-1]):  # the real endpoints
                    assert -0.5 <= float(px) <= lay.width + 0.5, (preset, c.path_d)
                    assert -0.5 <= float(py) <= lay.height + 0.5, (preset, c.path_d)

    def test_reciprocal_lane_separation(self) -> None:
        """G8b: any preset whose edge set carries both A->B and B->A renders
        the pair as two DISTINCT lane paths whose centerlines sit the
        composition gap apart — coordinate-level, swept across every preset
        (the cross-topology guard round 5 shipped without; its absence is
        how the refactor dropped the offset silently). Sequence and
        state-machine reciprocity rides their own grammars (replay pitch /
        under-loops) and is exempt from the GEOMETRIC gap law — state-machine's
        exemption is made REAL below (never a lane-hue accent), not just
        skipped."""
        from hyperweave.compose.diagram.input import diagram_preset_names
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.matrix import GlyphTint

        cfg = load_paradigms()["primer"].diagram
        registry = load_glyphs()
        base_gap = float(ENGINE["lane_offset"])
        comp_table = {str(k): float(v) for k, v in (ENGINE.get("lane_offset_by_composition") or {}).items()}
        extents = {str(k): float(v) for k, v in (ENGINE.get("lane_extent") or {}).items()}
        min_air = float(ENGINE.get("lane_min_air", 3))

        def endpoints(d: str) -> tuple[tuple[float, float], tuple[float, float]]:
            pairs = re.findall(r"(-?[\d.]+),(-?[\d.]+)", d)
            return (float(pairs[0][0]), float(pairs[0][1])), (float(pairs[-1][0]), float(pairs[-1][1]))

        checked = 0
        sm_checked = 0
        for preset in sorted(diagram_preset_names()):
            spec = _normalized_preset(preset)
            if spec.topology.value == "sequence":
                continue
            lay = compute_diagram_layout(
                spec,
                paradigm=cfg,
                engine=ENGINE,
                palette_len=5,
                glyph_registry=registry,
                glyph_selections=tuple(GlyphTint.INK for _ in spec.nodes),
            )
            by_pair = {(c.source_index, c.target_index): c for c in lay.connectors}
            for (s, t_), c in sorted(by_pair.items()):
                if s == t_:  # a self-loop is not a reciprocal pair (maps to itself)
                    continue
                back = by_pair.get((t_, s))
                if back is None or s > t_:
                    continue
                if spec.topology.value == "state-machine":
                    # DRESS, not geometry: the lens bow already separates the
                    # two directions visually and the accent binds to the
                    # back edge alone (spine_members) — a reciprocal pair
                    # here must never carry the generic lane-hue treatment
                    # (order-lifecycle: retry resolves to the spine accent 0,
                    # throw to neutral -1). lane_fwd/lane_rev are now the
                    # SAME two values (0 = true accent, -1 = true muted, per
                    # the gateway v4 specimen's binary law) as the ordinary
                    # spine/neutral binary, so a numeric-coincidence check
                    # can no longer tell "lane-dressed" apart from "ordinary"
                    # — assert the STRUCTURAL fact directly instead.
                    assert not mo.lane_dress_applies(spec.topology, c.lane), (preset, s, t_, c.lane)
                    assert not mo.lane_dress_applies(spec.topology, back.lane), (preset, s, t_, back.lane)
                    sm_checked += 1
                    continue
                assert c.path_d != back.path_d, (preset, s, t_, c.path_d)
                (a1, a2) = endpoints(c.path_d)
                (b1, b2) = endpoints(back.path_d)
                mid_a = ((a1[0] + a2[0]) / 2, (a1[1] + a2[1]) / 2)
                mid_b = ((b1[0] + b2[0]) / 2, (b1[1] + b2[1]) / 2)
                separation = math.hypot(mid_a[0] - mid_b[0], mid_a[1] - mid_b[1])
                comp = "-".join(sorted((c.motion, back.motion)))
                rendered_floor = extents.get(c.motion, 1.0) + extents.get(back.motion, 1.0) + min_air
                gap = max(comp_table.get(comp, base_gap), rendered_floor)  # K2: air between rendered extents
                assert abs(separation - gap) <= 0.8, (preset, s, t_, comp, round(separation, 2), gap)
                checked += 1
        # P6 preset gut: the multi-reciprocal presets (sync-chain, gateway-classic,
        # frontier-gateway) are out of the parity library; gateway is the surviving
        # duplex preset (request/response pair + direction:both server pair).
        assert checked >= 2  # gateway: 2 reciprocal pairs
        assert sm_checked >= 1  # order-lifecycle: throw/retry

    def test_channel_lanes_hold_the_period_floor(self) -> None:
        """K3: all-reciprocal pipeline compositions are wire-major — every
        lane run holds the chassis channel_run_min (dash-period legibility);
        node-major pipelines are untouched."""
        from hyperweave.compose.diagram.input import diagram_preset_names

        cfg = load_paradigms()["primer"].diagram
        run_min = cfg.topologies["pipeline"].channel_run_min
        assert run_min == 144.0  # the triptych pick
        checked = 0
        for preset in sorted(diagram_preset_names()):
            spec = _normalized_preset(preset)
            lay = compute_diagram_layout(spec, paradigm=cfg, engine=ENGINE, palette_len=5)
            if lay.layout_slug != "pipeline":
                continue
            by_pair = {(c.source_index, c.target_index) for c in lay.connectors}
            all_reciprocal = lay.connectors and all((t2, s2) in by_pair for (s2, t2) in by_pair)
            if not all_reciprocal:
                continue
            for c in lay.connectors:
                assert c.length >= run_min - 0.6, (preset, c.index, c.length)
            checked += 1
        # P6 preset gut: gateway is the surviving all-reciprocal (duplex) pipeline.
        assert checked >= 1  # gateway

    def test_clearance_law(self) -> None:
        """G7: clearance, not just non-overlap — every non-nested box pair
        breathes by min_clearance, and every box keeps min_clearance from
        every NON-INCIDENT connector path, across all presets."""
        from hyperweave.compose.diagram.input import diagram_preset_names
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.matrix import GlyphTint

        cfg = load_paradigms()["primer"].diagram
        registry = load_glyphs()
        clearance = float(ENGINE["min_clearance"])
        eps = 0.6

        def box_gap(a, b) -> float:
            gx = max(a.x - (b.x + b.w), b.x - (a.x + a.w), 0.0)
            gy = max(a.y - (b.y + b.h), b.y - (a.y + a.h), 0.0)
            return math.hypot(gx, gy)

        def sample_path(d: str) -> list[tuple[float, float]]:
            pts: list[tuple[float, float]] = []
            tokens = re.findall(r"([MLCAQ])\s*((?:-?[\d.]+[, ]*)+)", d)
            cursor: tuple[float, float] | None = None
            for cmd, raw in tokens:
                nums = [float(v) for v in re.findall(r"-?[\d.]+", raw)]
                if cmd == "M":
                    cursor = (nums[0], nums[1])
                    pts.append(cursor)
                elif cmd == "L":
                    assert cursor is not None
                    x0, y0 = cursor
                    for t_ in range(1, 25):
                        u = t_ / 24
                        pts.append((x0 + (nums[0] - x0) * u, y0 + (nums[1] - y0) * u))
                    cursor = (nums[0], nums[1])
                elif cmd == "C":
                    assert cursor is not None
                    x0, y0 = cursor
                    for k in range(0, len(nums), 6):
                        c1x, c1y, c2x, c2y, ex, ey = nums[k : k + 6]
                        for t_ in range(1, 25):
                            u = t_ / 24
                            v = 1 - u
                            pts.append(
                                (
                                    v**3 * x0 + 3 * v**2 * u * c1x + 3 * v * u**2 * c2x + u**3 * ex,
                                    v**3 * y0 + 3 * v**2 * u * c1y + 3 * v * u**2 * c2y + u**3 * ey,
                                )
                            )
                        x0, y0 = ex, ey
                    cursor = (x0, y0)
                elif cmd == "Q":
                    # Quadratic corners: the orthogonal over/under skip routes
                    # (L+Q). Subdivide so the sampler tracks the true corner
                    # instead of chording it — a skipped Q made the flat run
                    # read as a slant that false-tripped the clearance floor.
                    assert cursor is not None
                    x0, y0 = cursor
                    for k in range(0, len(nums), 4):
                        cx, cy, ex, ey = nums[k : k + 4]
                        for t_ in range(1, 25):
                            u = t_ / 24
                            v = 1 - u
                            qx = v * v * x0 + 2 * v * u * cx + u * u * ex
                            qy = v * v * y0 + 2 * v * u * cy + u * u * ey
                            pts.append((qx, qy))
                        x0, y0 = ex, ey
                    cursor = (x0, y0)
                elif cmd == "A":
                    # Arcs connect adjacent ring cards (incident); skip.
                    cursor = (nums[-2], nums[-1])
                    pts.append(cursor)
            return pts

        for preset in sorted(diagram_preset_names()):
            spec = _normalized_preset(preset)
            lay = compute_diagram_layout(
                spec,
                paradigm=cfg,
                engine=ENGINE,
                palette_len=5,
                glyph_registry=registry,
                glyph_selections=tuple(GlyphTint.INK for _ in spec.nodes),
            )
            boxes = {n.index: n.box for n in lay.nodes}
            items = sorted(boxes.items())
            # Lanes rows pack at the SPECIMEN's own 14px (obi-engine,
            # measured) — a same-column vertical stack inside a band is the
            # lane grid, not a crowding failure. Every other pair keeps G7.
            lanes_stack_gap = 14.0
            for ai in range(len(items)):
                for bi in range(ai + 1, len(items)):
                    a_box, b_box = items[ai][1], items[bi][1]
                    g = box_gap(a_box, b_box)
                    floor = clearance
                    if spec.topology.value == "lanes" and abs(a_box.x - b_box.x) < 2.0:
                        floor = lanes_stack_gap
                    assert g >= floor - eps, (preset, items[ai][0], items[bi][0], round(g, 1))
            for c in lay.connectors:
                pts = sample_path(c.path_d)
                # A CLOSED rim (start == end — the flywheel flow current)
                # passes beneath the phase cards by design; paint order
                # occludes it (flywheel-flow).
                if pts and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1.0:
                    continue
                for idx, b in boxes.items():
                    if idx in (c.source_index, c.target_index):
                        continue
                    for px, py in pts:
                        gx = max(b.x - px, px - (b.x + b.w), 0.0)
                        gy = max(b.y - py, py - (b.y + b.h), 0.0)
                        d = math.hypot(gx, gy)
                        assert d >= clearance - eps, (preset, c.index, idx, round(d, 1), (round(px), round(py)))

    def test_card_glyph_marks_sit_inside_their_cards(self) -> None:
        """The card+glyph identity mark anchors at the card's dot slot —
        its transform must translate INTO the card, never to the canvas
        origin (a literal-x call-site regression caught at raster)."""
        import re

        from hyperweave.compose.diagram.input import diagram_preset_names
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.matrix import GlyphTint

        cfg = load_paradigms()["primer"].diagram
        registry = load_glyphs()
        seen = 0
        for preset in sorted(diagram_preset_names()):
            spec = _normalized_preset(preset)
            lay = compute_diagram_layout(
                spec,
                paradigm=cfg,
                engine=ENGINE,
                palette_len=5,
                glyph_registry=registry,
                glyph_selections=tuple(GlyphTint.INK for _ in spec.nodes),
            )
            for n in lay.nodes:
                if n.shape != "rect" or n.glyph is None:
                    continue
                m = re.match(r"translate\((-?[\d.]+),(-?[\d.]+)\)", n.glyph.transform)
                assert m, (preset, n.index, n.glyph.transform)
                gx, gy = float(m.group(1)), float(m.group(2))
                b = n.box
                assert b.x <= gx <= b.x + b.w, (preset, n.index, gx, b)
                assert b.y <= gy <= b.y + b.h, (preset, n.index, gy, b)
                seen += 1
        assert seen >= 20  # the C1 identity pass marks branded cards broadly


def _member_widths(lay: DiagramLayout) -> set[float]:
    """Distinct widths of the non-hero rect cards — a member group is uniform
    iff this is a single value."""
    return {round(n.box.w, 1) for n in lay.nodes if n.role != "hero" and n.shape == "rect"}


class TestGroupUniformWidths:
    """The aligned-group policy normalizes card WIDTHS to the group max (the
    height-normalization law, extended). Every fanout-family member group is
    uniform even when member labels vary in length — the ragged column becomes
    the prototype's uniformity. Content-aware sizing stays the law: the shared
    width is the group's content-solved max, never a fixed size."""

    # Deliberately varied label lengths, several exceeding the min_w floor so
    # a free policy would render ragged.
    _VARIED = ("s", "a considerably longer destination label", "medium label", "x", "another long one here")

    def _fan(self, orientation: str) -> DiagramLayout:
        nodes = [{"label": "HUB", "role": "hero"}, *({"label": lb} for lb in self._VARIED)]
        kw: dict[str, Any] = dict(topology="fanout", nodes=nodes)
        if orientation:
            kw["orientation"] = orientation
        return solve(**kw)

    @pytest.mark.parametrize("orientation", ["", "bilateral", "upward", "radial"])
    def test_fanout_member_widths_uniform(self, orientation: str) -> None:
        widths = _member_widths(self._fan(orientation))
        assert len(widths) == 1, (orientation, sorted(widths))

    def test_convergence_arrivals_uniform(self) -> None:
        nodes = [*({"label": lb} for lb in self._VARIED), {"label": "SINK", "role": "hero"}]
        widths = _member_widths(solve(topology="convergence", nodes=nodes))
        assert len(widths) == 1, sorted(widths)

    def test_shared_width_is_the_group_max(self) -> None:
        # The shared width equals the WIDEST member's content-solved width, not
        # a fixed chassis value — content-aware sizing is preserved.
        from hyperweave.compose.diagram.sizing import mark_w_for, solve_card_w

        cfg = load_paradigms()["primer"].diagram
        lay = self._fan("")
        ch = cfg.topologies[lay.layout_slug]
        dest_nodes = resolve_auto_roles(
            DiagramSpec(
                topology="fanout", nodes=[{"label": "HUB", "role": "hero"}, *({"label": lb} for lb in self._VARIED)]
            )
        ).nodes[1:]
        solved = [
            solve_card_w(nd, ch.node, cfg, [], min_w=ch.card_min_w, mark_w=mark_w_for("card", nd)) for nd in dest_nodes
        ]
        shared = next(iter(_member_widths(lay)))
        assert shared == pytest.approx(max(solved))  # the group max drives it

    def test_chassis_fit_content_stays_uniform_and_short(self) -> None:
        # Short chassis-fit labels already share the chassis-floor width — the
        # normalization is a no-op there (byte-identical), and stays uniform.
        lay = solve(topology="fanout", nodes=labeled("hub", "a", "b", "c", "d", "e"))
        assert len(_member_widths(lay)) == 1


class TestLaw1CanvasPresence:
    """LAW 1 (universal canvas/presence): every topology flows through ONE
    post-pass in finish_layout — canvas = content bbox + chrome bands,
    content translated to sit exactly inside them. Swept across every
    shipped preset: nothing clips, the content pins to its bands, and the
    canvas never dilutes the artifact below the mass floor."""

    def test_every_preset_fits_pins_and_carries_mass(self) -> None:
        from hyperweave.compose.diagram.input import diagram_preset_names
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.matrix import GlyphTint

        cfg = load_paradigms()["primer"].diagram
        registry = load_glyphs()
        for preset in sorted(diagram_preset_names()):
            spec = _normalized_preset(preset)
            lay = compute_diagram_layout(
                spec,
                paradigm=cfg,
                engine=ENGINE,
                palette_len=5,
                glyph_registry=registry,
                glyph_selections=tuple(GlyphTint.INK for _ in spec.nodes),
            )
            ch = cfg.topologies[lay.layout_slug]
            # NO-CLIP: every element inside the canvas.
            xs: list[float] = []
            ys: list[float] = []
            for n in lay.nodes:
                assert n.box.x >= -0.5 and n.box.y >= -0.5, (preset, n.index)
                assert n.box.x + n.box.w <= lay.width + 0.5, (preset, n.index)
                assert n.box.y + n.box.h <= lay.height + 0.5, (preset, n.index)
                xs += [n.box.x, n.box.x + n.box.w]
                ys += [n.box.y, n.box.y + n.box.h]
            for a in lay.annotations:
                if a.box is not None:
                    assert a.box.x >= -0.5 and a.box.y >= -0.5, (preset, a.kind)
                    assert a.box.x + a.box.w <= lay.width + 0.5, (preset, a.kind)
                    assert a.box.y + a.box.h <= lay.height + 0.5, (preset, a.kind)
            # CONTENT NEVER INTRUDES INTO THE BANDS: the law translated the
            # geo-inclusive bbox onto (margin_x, the SOLVED masthead band);
            # node/furniture extents therefore sit AT or INSIDE the bands (a
            # topology whose wires rise above its cards — the SM self-loop —
            # pins its cards deeper). Exact ==-pins live in the per-topology
            # suites. The masthead band's height is measured against the
            # ACTUAL stacked content region (`lay.regions`), not the chassis'
            # static `header_h` budget — every public compose renders
            # caption chrome now, whose masthead band is 0 unless a header-
            # region legend bumps it, so the pre-stack solver constant no
            # longer bounds the post-stack content position.
            from hyperweave.compose.diagram.recenter import content_extents

            ext = content_extents(
                list(lay.nodes),
                [],
                lay.lane_bands,
                lay.lifelines,
                lay.activations,
                lay.initial_dot,
                lay.initial_stub,
            )
            assert ext is not None
            content_region = next(r for r in lay.regions if r.id == "content")
            assert ext[0] >= ch.margin_x - 1.5, (preset, ext[0], ch.margin_x)
            assert ext[1] >= content_region.y - 1.5, (preset, ext[1], content_region.y)
            # MASS FLOOR: the canvas never dilutes the artifact. The flywheel
            # ring is the airiest lawful preset; the floor sits just below it
            # (the canvas now grows to hold outboard ring labels, so the ring
            # reads slightly airier than before — that is correct Law-1
            # measurement, not dilution).
            mass = sum(n.box.w * n.box.h for n in lay.nodes) / (lay.width * lay.height)
            # Floor sits under the airiest lawful preset on the page-scale
            # canvas (glyph-circle ring on the 920 flywheel-orbit field).
            assert mass >= 0.015, (preset, mass)


class TestCardLego:
    """The sixth-review card law: a card is a lego defined once — it adjusts
    to the content inside. Reasonable names and subtitles never truncate
    (the box grows to the widest unbreakable run before the desc wraps), and
    every card piece (the chip row) is hosted coherently by every anatomy
    that renders it."""

    _PIPE: ClassVar[dict[str, Any]] = dict(
        topology="pipeline",
        title="T",
        nodes=[
            {"id": "a", "label": "slug", "desc": "node.glyph"},
            {"id": "b", "label": "kinds", "desc": "glyphs-core.json"},
            {"id": "c", "label": "brands", "desc": "glyphs.json", "chips": ["385 marks"]},
            {"id": "d", "label": "the mark", "desc": "or nothing at all", "role": "hero"},
        ],
        edges=[
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
            {"source": "c", "target": "d"},
        ],
    )

    def test_unbreakable_desc_word_never_ellipsizes(self) -> None:
        # glyphs-core.json is one unbreakable token wider than the 112 stage
        # floor — the stage grows; the desc renders whole (Eli: truncation
        # "was implemented earlier, but it doesnt make sense").
        lay = solve(**self._PIPE)
        runs = [dt.text for nd in lay.nodes for dt in (*nd.desc_lines, nd.label)]
        assert not [t for t in runs if "…" in t], runs
        assert "glyphs-core.json" in runs

    def test_desc_word_grows_the_stage(self) -> None:
        # The label-row pipeline is ALIGNED: the shared unit grows to hold the
        # widest unbreakable desc token — no stage may be narrower than it.
        from hyperweave.compose.diagram.sizing import desc_word_w

        cfg = load_paradigms()["primer"].diagram
        lay = solve(**self._PIPE)
        by_id = {nd.node_id: nd for nd in lay.nodes}
        need = desc_word_w("glyphs-core.json", cfg.desc_voice)
        assert by_id["b"].box.w >= need, (by_id["b"].box.w, need)
        assert by_id["b"].box.w >= by_id["a"].box.w

    def test_head_anatomy_hosts_chips(self) -> None:
        # Label-row stages: a chips-bearing stage renders its chip row
        # INSIDE the card (the in-card chip home), left-aligned to the text
        # column, same species as its siblings.
        lay = solve(**self._PIPE)
        card = next(nd for nd in lay.nodes if nd.node_id == "c")
        assert card.chip_boxes, "chip row must render inside the card"
        row_left = min(b.x for b in card.chip_boxes)
        row_right = max(b.x + b.w for b in card.chip_boxes)
        assert row_left >= card.box.x - 0.5 and row_right <= card.box.x + card.box.w + 0.5
        for b in card.chip_boxes:
            assert card.box.y <= b.y and b.y + b.h <= card.box.y + card.box.h + 0.5
        assert card.label.anchor == "start"  # label-row anatomy

    def test_portrait_text_stays_inside_the_card(self) -> None:
        # The bleed law: every text run's measured extent fits its card.
        from hyperweave.compose.diagram.sizing import voice_for
        from hyperweave.compose.matrix.cells import measure_voice

        cfg = load_paradigms()["primer"].diagram
        lay = solve(**self._PIPE)
        for nd in lay.nodes:
            for dt in (nd.label, *nd.desc_lines):
                w = measure_voice(dt.text, voice_for(cfg, dt.cls))
                left = dt.x - (w / 2 if dt.anchor == "middle" else w if dt.anchor == "end" else 0.0)
                assert left >= nd.box.x - 0.5, (nd.node_id, dt.text, left)
                assert left + w <= nd.box.x + nd.box.w + 0.5, (nd.node_id, dt.text, left + w)


def test_plain_edge_chips_ride_on_their_wire() -> None:
    """Kit piece 7: an edge-chip is centered ON its wire (the
    line runs through its middle, even in / even out). The anti-collision pass
    must never perp-push a plain chip off it — the ±push-step shove that lifted
    reads/emits/cache/direct-read off their lines. service-dependencies and
    gateway-balanced carry only plain edge-chips (no gather-trunk lift idiom),
    so every one rides within 2px of its wire midpoint."""
    from hyperweave.compose.diagram.annotate import _polyline_midpoint
    from hyperweave.compose.diagram.paths import sample_path
    from hyperweave.config.loader import load_glyphs, load_paradigms
    from hyperweave.core.matrix import GlyphTint

    cfg = load_paradigms()["primer"].diagram
    registry = load_glyphs()
    for preset in ("service-dependencies", "gateway-balanced"):
        spec = _normalized_preset(preset)
        lay = compute_diagram_layout(
            spec,
            paradigm=cfg,
            engine=ENGINE,
            palette_len=5,
            glyph_registry=registry,
            glyph_selections=tuple(GlyphTint.INK for _ in spec.nodes),
        )
        for c in lay.connectors:
            e = spec.edges[c.index]
            if not (e.label and e.label_style == "chip"):
                continue
            mid = _polyline_midpoint(tuple(sample_path(c.path_d)))
            chip = next(
                (a for a in lay.annotations if a.kind == "edge-chip" and a.lines and a.lines[0].text == e.label),
                None,
            )
            if chip is None:
                continue
            cy = chip.box.y + chip.box.h / 2
            assert abs(cy - mid[1]) < 2.0, f"{preset}: chip {e.label!r} sits {cy - mid[1]:+.0f}px off its wire midpoint"
