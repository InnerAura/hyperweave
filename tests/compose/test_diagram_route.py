"""Connector grammar (route.py) + content-sized cards + ornament-free defaults.

route.py is the routing layer above paths.py: exit points on node boundaries,
routed paths (straight | curved | orthogonal), self-loop cubics, and DRAWN
chevron arrowheads (never <marker> elements). These pins hold the two
quantities the later passes consume — an exact length and a unit end tangent —
and prove the ornament-free doctrine: no shipped preset draws a marker.

Card pins hold the content-sized card box (G3 extension): a wrapped desc grows
the box height, aligned groups share the max, and the w_max/h_max ceilings
clamp. The byte-determinism proof (existing snapshots) shows h_override=0 kept
every preset unchanged; these pins prove the growth path itself.
"""

from __future__ import annotations

import math

import pytest

from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import (
    diagram_preset_names,
    resolve_auto_roles,
    resolve_diagram_preset,
)
from hyperweave.compose.diagram.records import DiagramText, NodePlacement
from hyperweave.compose.diagram.route import (
    arrow_d,
    exit_point,
    marker_path,
    orthogonal_d,
    resolve_marker,
    route_path,
    self_loop,
)
from hyperweave.compose.diagram.sizing import label_desc_gap_for, solve_card_box
from hyperweave.compose.spatial_records import RectSpec
from hyperweave.config.loader import load_diagram_config, load_paradigms
from hyperweave.core.diagram import DiagramInputError, DiagramNode, DiagramSpec

ENGINE = load_diagram_config()
Vec = tuple[float, float]


def _rect(x: float, y: float, w: float, h: float) -> NodePlacement:
    """A minimal rect placement — only the geometry route.py reads."""
    return NodePlacement(
        index=0,
        node_id="n",
        shape="rect",
        box=RectSpec(x=x, y=y, w=w, h=h),
        role="default",
        stroke_width=1.0,
        stroke_dasharray="",
        accent_index=-1,
        label=DiagramText(x=x, y=y, text="n", cls="name"),
    )


def _circle(cx: float, cy: float, r: float) -> NodePlacement:
    return NodePlacement(
        index=0,
        node_id="n",
        shape="circle",
        box=RectSpec(x=cx - r, y=cy - r, w=2 * r, h=2 * r, rx=r),
        role="default",
        stroke_width=1.0,
        stroke_dasharray="",
        accent_index=-1,
        label=DiagramText(x=cx, y=cy, text="n", cls="clbl"),
        cx=cx,
        cy=cy,
        r=r,
    )


def _dist(a: Vec, b: Vec) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _first_point(d: str) -> Vec:
    _, rest = d.split("M", 1)
    x, y = rest.strip().split(" ", 1)[0].split(",")
    return (float(x), float(y))


def _last_point(d: str) -> Vec:
    x, y = d.replace(",", " ").split()[-2:]
    return (float(x), float(y))


class TestExitPoint:
    def test_rect_side_midpoints(self) -> None:
        p = _rect(100.0, 200.0, 60.0, 40.0)  # center (130, 220)
        assert exit_point(p, "right") == (160.0, 220.0)
        assert exit_point(p, "left") == (100.0, 220.0)
        assert exit_point(p, "top") == (130.0, 200.0)
        assert exit_point(p, "bottom") == (130.0, 240.0)

    def test_standoff_backs_off_along_normal(self) -> None:
        p = _rect(0.0, 0.0, 40.0, 40.0)  # center (20, 20)
        assert exit_point(p, "right", standoff=8.0) == (48.0, 20.0)
        assert exit_point(p, "top", standoff=5.0) == (20.0, -5.0)

    def test_circle_compass_point_on_rim(self) -> None:
        p = _circle(50.0, 50.0, 10.0)
        rx, ry = exit_point(p, "right")
        assert rx == pytest.approx(60.0)
        assert ry == pytest.approx(50.0)


class TestOrthogonalLength:
    def test_exact_length_no_rounding(self) -> None:
        # r=0 drops every corner to a sharp join, so the length is the raw
        # leg sum: |mid - sx| + |ty - sy| + |tx - mid| for HVH.
        sx, sy, tx, ty = 0.0, 0.0, 200.0, 80.0
        mid = 100.0
        _d, length, _poly, _tan = orthogonal_d(sx, sy, tx, ty, mid=mid, first_axis="h", r=0.0)
        expected = abs(mid - sx) + abs(ty - sy) + abs(tx - mid)
        assert length == pytest.approx(expected)

    def test_rounded_corner_shortens_by_correction(self) -> None:
        # Each drawn corner replaces 2r of leg with a quarter-arc (pi/2)*r,
        # so length = raw - 2*(2r) + 2*((pi/2)*r) for two rounded corners.
        sx, sy, tx, ty = 0.0, 0.0, 200.0, 80.0
        mid = 100.0
        r = 10.0
        _d, length, _poly, _tan = orthogonal_d(sx, sy, tx, ty, mid=mid, first_axis="h", r=r)
        raw = abs(mid - sx) + abs(ty - sy) + abs(tx - mid)
        correction = 2 * ((math.pi / 2) * r - 2 * r)  # two corners
        assert length == pytest.approx(raw + correction)

    def test_short_leg_caps_the_corner_radius(self) -> None:
        # A middle (vertical) leg of 4px caps each adjacent corner's radius at
        # leg/2 = 2 (not the requested 10), so the length correction is taken
        # at r=2 for both corners — the degenerate-safe path, not a full-radius
        # arc that would overshoot the leg.
        sx, sy, tx, ty = 0.0, 0.0, 200.0, 4.0
        mid = 100.0
        _d, length, _poly, _tan = orthogonal_d(sx, sy, tx, ty, mid=mid, first_axis="h", r=10.0)
        raw = abs(mid - sx) + abs(ty - sy) + abs(tx - mid)
        capped_r = 2.0  # min(10, leg/2) for the 4px middle leg
        correction = 2 * ((math.pi / 2) * capped_r - 2 * capped_r)
        assert length == pytest.approx(raw + correction)

    def test_zero_length_leg_drops_the_corner(self) -> None:
        # A straight run (mid == sx so the first horizontal leg is 0) leaves
        # nothing to round: the corner drops and the polyline stays clean.
        sx, sy, tx, ty = 0.0, 0.0, 0.0, 100.0
        _d, length, poly, tan = orthogonal_d(sx, sy, tx, ty, mid=0.0, first_axis="h", r=10.0)
        assert length == pytest.approx(100.0)  # a pure vertical drop
        assert poly[0] == pytest.approx((sx, sy))
        assert poly[-1] == pytest.approx((tx, ty))
        assert math.hypot(*tan) == pytest.approx(1.0)

    def test_last_leg_end_tangent(self) -> None:
        # HVH into a target to the right of mid arrives travelling +x.
        _d, _len, _poly, tan = orthogonal_d(0.0, 0.0, 200.0, 80.0, mid=100.0, first_axis="h")
        assert tan == (1.0, 0.0)
        # target left of mid arrives travelling -x.
        _d, _len, _poly, tan = orthogonal_d(200.0, 0.0, 0.0, 80.0, mid=100.0, first_axis="h")
        assert tan == (-1.0, 0.0)
        # VHV arrives vertically.
        _d, _len, _poly, tan = orthogonal_d(0.0, 0.0, 80.0, 200.0, mid=100.0, first_axis="v")
        assert tan == (0.0, 1.0)


class TestPolylineEndpoints:
    @pytest.mark.parametrize(
        ("style", "kw"),
        [
            ("straight", {}),
            ("curved", {"axis": "h"}),
            ("curved", {"axis": "v"}),
            ("orthogonal", {"first_axis": "h"}),
            ("orthogonal", {"first_axis": "v"}),
        ],
    )
    def test_polyline_starts_and_ends_at_path_endpoints(self, style: str, kw: dict[str, object]) -> None:
        sx, sy, tx, ty = 10.0, 20.0, 210.0, 120.0
        d, _len, poly, _tan = route_path(sx, sy, tx, ty, style=style, **kw)  # type: ignore[arg-type]
        assert poly[0] == pytest.approx((sx, sy))
        assert poly[-1] == pytest.approx((tx, ty))
        # The polyline endpoints agree with the drawn path's endpoints too.
        assert _first_point(d) == pytest.approx((sx, sy))
        assert _last_point(d) == pytest.approx((tx, ty))

    def test_unknown_style_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown route style"):
            route_path(0.0, 0.0, 1.0, 1.0, style="zigzag")


class TestSelfLoop:
    def test_rect_anchors_on_chosen_side(self) -> None:
        # Two boundary points, mouth apart, centred on the top-side midpoint.
        p = _rect(0.0, 0.0, 100.0, 40.0)  # center (50, 20), top edge y=0
        d, length, apex, label_anchor, _end_tangent = self_loop(p, "top", mouth=24.0, reach=40.0)
        a = _first_point(d)
        b = _last_point(d)
        assert a[1] == pytest.approx(0.0)  # both mouth points on the top edge
        assert b[1] == pytest.approx(0.0)
        assert _dist(a, b) == pytest.approx(24.0)  # mouth spacing
        assert length > 0.0
        assert label_anchor[0] > apex[0]  # label sits outboard of the apex

    def test_apex_bows_outward(self) -> None:
        # The apex sits beyond the side (above a top side => smaller y) by
        # roughly the reach, not back inside the node.
        p = _rect(0.0, 0.0, 100.0, 40.0)  # top edge y=0, interior y>0
        _d, _len, apex, _lbl, _tan = self_loop(p, "top", mouth=24.0, reach=40.0)
        assert apex[1] < 0.0  # outboard of the top edge

    def test_end_tangent_is_unit(self) -> None:
        p = _rect(0.0, 0.0, 100.0, 40.0)
        _d, _len, _apex, _lbl, end_tangent = self_loop(p, "top")
        assert math.hypot(*end_tangent) == pytest.approx(1.0)

    def test_circle_mouth_points_on_rim(self) -> None:
        p = _circle(50.0, 50.0, 20.0)
        d, _len, _apex, _lbl, tan = self_loop(p, "right", mouth=16.0, reach=30.0)
        a = _first_point(d)
        b = _last_point(d)
        assert _dist((50.0, 50.0), a) == pytest.approx(20.0, abs=0.5)  # on the rim
        assert _dist((50.0, 50.0), b) == pytest.approx(20.0, abs=0.5)
        assert math.hypot(*tan) == pytest.approx(1.0)


class TestChevron:
    def test_tip_is_path_end(self) -> None:
        tip = (100.0, 50.0)
        u = (1.0, 0.0)
        d = arrow_d(tip, u, size=11.0, half=0.45)
        # Path is "M leg1 L tip L leg2 Z" — a closed, filled triangle; the
        # tip is the middle vertex and the trailing "Z" close isn't a point.
        pts = [tuple(map(float, p.split(","))) for p in d.replace("M", "").replace("L", "").replace("Z", "").split()]
        assert pts[1] == pytest.approx(tip)

    def test_legs_point_backward_along_end_tangent(self) -> None:
        # Both legs sit BEHIND the tip along -u: (leg - tip) . u < 0.
        tip = (100.0, 50.0)
        u = (1.0, 0.0)
        d = arrow_d(tip, u)
        pts = [tuple(map(float, p.split(","))) for p in d.replace("M", "").replace("L", "").replace("Z", "").split()]
        l1, _tip, l2 = pts
        for leg in (l1, l2):
            back = (leg[0] - tip[0], leg[1] - tip[1])
            assert back[0] * u[0] + back[1] * u[1] < 0.0

    def test_diagonal_tangent_legs_straddle_axis(self) -> None:
        # A diagonal arrival still puts the tip at the end and the legs
        # backward along the tangent (dot-product sign holds for any u).
        tip = (60.0, 60.0)
        u = (math.sqrt(0.5), math.sqrt(0.5))
        d = arrow_d(tip, u)
        pts = [tuple(map(float, p.split(","))) for p in d.replace("M", "").replace("L", "").replace("Z", "").split()]
        l1, _tip, l2 = pts
        for leg in (l1, l2):
            back = (leg[0] - tip[0], leg[1] - tip[1])
            assert back[0] * u[0] + back[1] * u[1] < 0.0


class TestMarkerResolution:
    def test_edge_over_spec_over_device(self) -> None:
        # Per-edge override wins.
        assert resolve_marker("arrow", "none", "motion") == "arrow"
        # Explicit none at the edge beats a genome arrowhead device.
        assert resolve_marker("none", "arrow", "arrowhead") == ""
        # Artifact default when the edge is silent.
        assert resolve_marker("", "arrow", "motion") == "arrow"
        # Genome arrowhead device only when both are silent.
        assert resolve_marker("", "", "arrowhead") == "arrow"
        # The shipped 'motion' device yields no marker.
        assert resolve_marker("", "", "motion") == ""

    def test_marker_path_needs_a_tangent(self) -> None:
        assert marker_path((10.0, 10.0), None, size=11.0, half=0.45) == ""
        drawn = marker_path((10.0, 10.0), (1.0, 0.0), size=11.0, half=0.45)
        assert drawn.startswith("M ")


class TestOrnamentFreeDefaults:
    def test_preset_markers_follow_the_per_topology_defaults(self) -> None:
        # The wire-defaults grammar: topologies in the engine wire_defaults table
        # (sequence, dag, state-machine, lanes, flywheel) draw terminal
        # arrows by default (obi-engine/flywheel-orbit both read solid
        # rails + drawn chevrons); every other topology stays markerless
        # unless an edge/spec opts in. Self-loops never take the default (a
        # loop's direction is unambiguous). Asserted across every shipped preset.
        # Tree also carries a wire_defaults entry (wire: solid,
        # the tree/dep-audit static hairline bus) but declares NO
        # terminal — a hierarchy's direction is position, never an arrowhead
        # (wiring.py's tree_exempt suppresses one regardless) — so it stays
        # OUT of the arrow-drawing subset even though it has a wire entry.
        from hyperweave.compose.diagram.input import coerce_diagram_input
        from hyperweave.core.models import ComposeSpec

        paradigm = load_paradigms()["primer"].diagram
        wire_defaults = ENGINE.get("wire_defaults") or {}
        flow_slugs = set(wire_defaults.keys())
        assert flow_slugs == {
            "hub",
            "sequence",
            "dag",
            "state-machine",
            "lanes",
            "flywheel",
            "tree",
            "ring",
        }  # the confirmed wire-defaults set
        arrow_slugs = {slug for slug, cfg in wire_defaults.items() if cfg.get("terminal")}
        assert arrow_slugs == {"sequence", "dag", "state-machine", "lanes", "flywheel", "ring", "hub"}
        offenders: list[tuple[str, str, int]] = []
        for name in sorted(diagram_preset_names()):
            # The production input seam (cyclic presets promote before solve).
            cs = ComposeSpec(type="diagram", genome_id="primer", diagram=resolve_diagram_preset(name))
            spec = coerce_diagram_input(cs.connector_data, cs).spec
            lay = compute_diagram_layout(spec, paradigm=paradigm, engine=ENGINE, palette_len=5)
            arrows_expected = lay.layout_slug in arrow_slugs
            for c in lay.connectors:
                edge = spec.edges[c.index] if c.index < len(spec.edges) else None
                is_loop = edge is not None and edge.source == edge.target
                # A relation-dressed wire's terminal is semantics (§3),
                # never ornament — the axial per-role defaults draw them. An
                # explicit per-edge `marker` is caller intent, not a leaking
                # topology default — the stack riser (stack) opts a
                # single edge into an arrowhead this way.
                explicit_marker = edge is not None and bool(edge.marker)
                if bool(c.marker_d) and (not arrows_expected or is_loop) and not c.relation and not explicit_marker:
                    offenders.append((name, "unexpected-arrow", c.index))
        assert offenders == []


class TestRoutingOverridable:
    def _spec(self, routing: str = "", exit_side: str = "") -> dict[str, object]:
        edge: dict[str, object] = {"source": "a", "target": "b"}
        if routing:
            edge["routing"] = routing
        if exit_side:
            edge["exit"] = exit_side
        return dict(
            topology="dag",
            nodes=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
            edges=[edge, {"source": "b", "target": "c"}],
        )

    def _solve(self, spec_kw: dict[str, object]) -> None:
        paradigm = load_paradigms()["primer"].diagram
        spec = resolve_auto_roles(DiagramSpec.model_validate(spec_kw))
        compute_diagram_layout(spec, paradigm=paradigm, engine=ENGINE, palette_len=5)

    def test_dag_accepts_routing_override(self) -> None:
        # dag is in routing_overridable — an explicit routing is honoured.
        self._solve(self._spec(routing="orthogonal"))

    def test_pipeline_accepts_routing_override(self) -> None:
        # pipeline is IN the routable set (its chain can bus or elbow), so an
        # explicit routing is honoured — the closed-topology pair set is fully
        # declared with the override on the first edge.
        kw = dict(
            topology="pipeline",
            nodes=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
            edges=[
                {"source": "a", "target": "b", "routing": "orthogonal"},
                {"source": "b", "target": "c"},
            ],
        )
        self._solve(kw)

    def test_fanout_rejects_routing_override(self) -> None:
        # fanout owns its connector shape (a fixed fan); an override would be a
        # lie, so it raises naming the field and the set. The derived pair set
        # (hub->each spoke) is declared with the illegal routing on one edge.
        kw = dict(
            topology="fanout",
            nodes=[{"id": "h", "label": "H"}, {"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            edges=[
                {"source": "h", "target": "a", "routing": "orthogonal"},
                {"source": "h", "target": "b"},
            ],
        )
        with pytest.raises(DiagramInputError, match="routing"):
            self._solve(kw)

    def test_fanout_rejects_exit_override(self) -> None:
        # fanout's derived pair set is hub->each spoke; both are declared and
        # one carries the illegal exit override.
        kw = dict(
            topology="fanout",
            nodes=[{"id": "h", "label": "H"}, {"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            edges=[
                {"source": "h", "target": "a", "exit": "top"},
                {"source": "h", "target": "b"},
            ],
        )
        with pytest.raises(DiagramInputError, match="exit"):
            self._solve(kw)


class TestContentSizedCards:
    def _cfg_ch(self, slug: str) -> tuple[object, object]:
        paradigm = load_paradigms()["primer"].diagram
        return paradigm, paradigm.topologies[slug]

    def test_short_desc_keeps_chassis_height(self) -> None:
        # A one-word desc that fits leaves the box at the chassis height —
        # the byte-identical floor (h == nch.h).
        cfg, ch = self._cfg_ch("pipeline")
        node = DiagramNode(label="A", desc="ok")
        _w, h, _lines = solve_card_box(node, ch.node, ch, cfg, [], min_w=ch.node.w)
        assert h == pytest.approx(ch.node.h)

    def test_four_line_desc_grows_box(self) -> None:
        # A rich desc on a card topology (max_desc_lines=4, h_max set) grows
        # the box to at least the measured block + 2*min_pad_y, capped at h_max.
        cfg, ch = self._cfg_ch("pipeline")
        long_desc = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen"
        node = DiagramNode(label="Stage", desc=long_desc)
        _w, h, lines = solve_card_box(node, ch.node, ch, cfg, [], min_w=ch.node.w)
        assert len(lines) >= 2  # the desc actually wrapped
        assert h >= ch.node.h  # and the box holds it (the portrait floor may already)
        assert h <= ch.h_max + 0.001  # clamped at the ceiling
        # The grown height fits the measured text block plus symmetric pad.
        # label_desc_gap_for (not the bare cfg.label_desc_gap scalar): pipeline's
        # own node never cited a label_desc_gap override, so it now inherits the
        # paradigm ROOT rhythm (7.5) rather than the bare paradigm-wide default
        # (6.0) — the same resolver solve_card_box itself calls.
        ar, dr = cfg.text_ascent_ratio, cfg.text_descent_ratio
        label_block = cfg.label_voice.size * (ar + dr)
        desc_block = cfg.desc_voice.size * (ar + dr) + (len(lines) - 1) * ch.node.desc_line_pitch
        pad_y = cfg.min_pad_y if ch.node.pad_y is None else ch.node.pad_y
        want = label_block + label_desc_gap_for(ch.node, cfg) + desc_block + 2 * pad_y
        assert h == pytest.approx(min(max(want, ch.node.h), ch.h_max))  # chassis h is the floor

    def test_w_max_stretches_to_hold_the_name_whole(self) -> None:
        # G3 kit: the width ceiling now stretches to hold the [mark·gap·name]
        # identity row WHOLE — w_max is a design target, never a wall a name
        # clips against. A long label grows the card past w_max rather than
        # truncate; the grown width is the row's own measured span (mark +
        # gap + label + 2*pad), rounded up to the even grid.
        from hyperweave.compose.diagram.sizing import DOT_MARK_W, anchor_pads, mark_lead
        from hyperweave.compose.matrix.cells import measure_voice

        cfg, ch = self._cfg_ch("hub")
        assert ch.w_max > 0.0
        node = DiagramNode(label="A very long node label that would overflow any card")
        w, _h, _lines = solve_card_box(node, ch.node, ch, cfg, [], min_w=ch.card_min_w)
        row_w = mark_lead(DOT_MARK_W, ch.node) + measure_voice(node.label, cfg.label_voice) + anchor_pads(ch.node)
        assert w == pytest.approx(math.ceil(row_w / 2) * 2)
        assert w > ch.w_max  # grew past the target ceiling to hold the name whole

    def test_aligned_group_shares_max_height(self) -> None:
        # A pipeline row: one card with a tall desc, others short. The shared
        # baseline puts every placed card at the same (grown) height.
        paradigm = load_paradigms()["primer"].diagram
        long_desc = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron"
        spec = resolve_auto_roles(
            DiagramSpec.model_validate(
                dict(
                    topology="pipeline",
                    nodes=[
                        {"label": "A", "desc": long_desc},
                        {"label": "B", "desc": "short"},
                        {"label": "C"},
                    ],
                )
            )
        )
        lay = compute_diagram_layout(spec, paradigm=paradigm, engine=ENGINE, palette_len=5)
        heights = {round(n.box.h, 3) for n in lay.nodes}
        assert len(heights) == 1  # every card shares one height
        assert heights.pop() >= paradigm.topologies["pipeline"].node.h  # and it holds it

    def test_dag_ranks_share_solved_box(self) -> None:
        # The DAG solver's max-over-members box solve (one content-solved box
        # across every rank member, so columns/gaps stay regular): a rich desc
        # on one node grows the shared card height for the whole graph. This is
        # the aligned-rank path that reuses the node iterate — a regression pin
        # for the box-solve loop.
        paradigm = load_paradigms()["primer"].diagram
        long_desc = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi"
        spec = resolve_auto_roles(
            DiagramSpec.model_validate(
                dict(
                    topology="dag",
                    nodes=[
                        {"id": "a", "label": "A", "desc": long_desc},
                        {"id": "b", "label": "B"},
                        {"id": "c", "label": "C"},
                    ],
                    edges=[{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
                )
            )
        )
        lay = compute_diagram_layout(spec, paradigm=paradigm, engine=ENGINE, palette_len=5)
        assert lay.layout_slug == "dag"
        heights = {round(n.box.h, 3) for n in lay.nodes}
        # Per-node boxes (dag specimens): the desc card grows its OWN height while
        # siblings keep the chassis floor.
        assert max(heights) > paradigm.topologies["dag"].node.h  # grew for the desc
        assert min(heights) >= paradigm.topologies["dag"].node.h
