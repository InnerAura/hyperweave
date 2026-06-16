"""Geometric invariants for the diagram layout solvers.

Universal rules hold across every layout (in-canvas, no node overlap,
determinism, connector endpoints on node edges); per-topology pins
reproduce the specimen constants the formulas were extracted from.
"""

from __future__ import annotations

import itertools
import math
import re
from typing import TYPE_CHECKING, Any

import pytest

from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import resolve_auto_roles
from hyperweave.config.loader import load_diagram_config, load_paradigms
from hyperweave.core.diagram import DiagramCapacityError, DiagramInputError, DiagramSpec

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import DiagramLayout

ENGINE = load_diagram_config()


def solve(palette_len: int = 5, **kw: Any) -> DiagramLayout:
    paradigm = load_paradigms()["primer"].diagram
    spec = resolve_auto_roles(DiagramSpec(**kw))
    return compute_diagram_layout(spec, paradigm=paradigm, engine=ENGINE, palette_len=palette_len)


def labeled(*labels: str, hero: int | None = None) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = [{"label": lb} for lb in labels]
    if hero is not None:
        nodes[hero]["role"] = "hero"
    return nodes


CASES: dict[str, dict[str, Any]] = {
    "pipeline": dict(topology="pipeline", title="T", nodes=labeled("A", "B", "C", "D", hero=1)),
    "fanout-horizontal": dict(topology="fanout", title="T", nodes=labeled("hub", "a", "b", "c", "d", "e")),
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
        assert [n.box.x for n in lay.nodes] == [24.0, 244.0, 492.0, 712.0]
        assert (lay.width, lay.height) == (896, 216)
        assert [c.path_d for c in lay.connectors] == [
            "M 184,126 L 244,126",
            "M 432,126 L 492,126",
            "M 652,126 L 712,126",
        ]

    def test_equal_gaps(self) -> None:
        lay = solve(topology="pipeline", nodes=labeled(*"ABCDE"))
        xs = sorted(n.box.x for n in lay.nodes)
        widths = {round(n.box.w, 2) for n in lay.nodes}
        assert len(widths) == 1  # no hero -> equal units
        gaps = {round(b - (a + lay.nodes[0].box.w), 2) for a, b in itertools.pairwise(xs)}
        assert len(gaps) == 1


class TestFans:
    def test_horizontal_column_pitch_and_height(self) -> None:
        lay = solve(**CASES["fanout-horizontal"])
        dests = [n for n in lay.nodes if n.index != 0]
        tops = sorted(n.box.y for n in dests)
        pitches = {round(b - a, 2) for a, b in itertools.pairwise(tops)}
        # G7 raised the column pitch so siblings clear min_clearance.
        assert pitches == {load_paradigms()["primer"].diagram.topologies["fanout-horizontal"].pitch}
        assert (lay.width, lay.height) == (760, 520)  # height follows the G7 pitch

    def test_horizontal_curves_share_midpoint_control(self) -> None:
        lay = solve(**CASES["fanout-horizontal"])
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

    def test_radial_equiangle_and_square(self) -> None:
        lay = solve(**CASES["fanout-radial"])
        assert lay.width == lay.height
        c = lay.width / 2
        hub = lay.nodes[-1]
        assert hub.index == 0  # painted last: the emanation mask
        angles = sorted(
            math.degrees(math.atan2(n.box.y + n.box.h / 2 - c, n.box.x + n.box.w / 2 - c))
            for n in lay.nodes
            if n.index != 0
        )
        deltas = {round(b - a, 1) for a, b in itertools.pairwise(angles)}
        assert deltas == {72.0}

    def test_convergence_single_meet_point(self) -> None:
        lay = solve(**CASES["convergence"])
        ends = {c.path_d.rsplit(" ", 1)[1] for c in lay.connectors}
        assert len(ends) == 1


class TestRing:
    def test_flywheel_arc_radius_and_boundary_trim(self) -> None:
        lay = solve(**CASES["flywheel"])
        for c in lay.connectors:
            m = re.search(r"A ([\d.]+),", c.path_d)
            assert m and float(m.group(1)) == 178.0
        # Shape-true trim (G1): every arc spans MORE than the old
        # half-width-as-radius estimate allowed (42 deg) because side
        # approaches now stop at the card's actual boundary.
        spans = [round(c.length / 178 * 180 / math.pi, 1) for c in lay.connectors]
        assert all(s > 42.0 for s in spans), spans
        assert len(set(spans)) == 1  # cardinal symmetry holds

    def test_flywheel_hero_is_axis(self) -> None:
        lay = solve(**CASES["flywheel"])
        axis = next(n for n in lay.nodes if n.role == "hero")
        assert abs(axis.box.x + axis.box.w / 2 - lay.width / 2) < 0.5
        assert abs(axis.box.y + axis.box.h / 2 - lay.height / 2) < 0.5


class TestStackTreeComparison:
    def test_stack_operator_count_and_vertical_risers(self) -> None:
        # The operator SLOT is chassis geometry; its CONTENT is preset data
        # (G9): no token, no rail; a declared token rails every riser gap.
        lay = solve(**CASES["stack"])
        assert lay.operators == ()
        lay = solve(**{**CASES["stack"], "operator": "\u00d7"})
        assert len(lay.operators) == 3  # L-1 between the 4 layers
        assert {op.text for op in lay.operators} == {"\u00d7"}  # U+00D7 IS the rendered token
        for c in lay.connectors:
            xs = re.findall(r"([\d.]+),[\d.]+", c.path_d)
            assert len({float(x) for x in xs}) == 1, c.path_d

    def test_tree_center_leaf_straight_outer_curved(self) -> None:
        lay = solve(**CASES["tree"])
        kinds = sorted(("L" in c.path_d, c.index) for c in lay.connectors)
        assert sum(1 for straight, _ in kinds if straight) == 1
        assert (lay.width, lay.height) == (720, 320)

    def test_comparison_fixed_canvas_and_single_connector(self) -> None:
        lay = solve(**CASES["comparison"])
        assert (lay.width, lay.height) == (720, 240)
        assert len(lay.connectors) == 1
        assert lay.connectors[0].accent_index == -1
        assert lay.nodes[0].role == "muted"
        assert lay.nodes[0].stroke_dasharray == "4 4"
        assert lay.nodes[0].dot is None


class TestSequence:
    def test_replay_single_particle_and_anatomy(self) -> None:
        # K-seq-v2: ONE traversing particle per message (sequential slots,
        # so one dot is visible at a time), full-weight semantic strokes,
        # no comet light layers.
        lay = solve(**CASES["sequence"])
        assert len(lay.lifelines) == 3
        assert len(lay.activations) == 3
        assert len(lay.particles) == len(lay.connectors)  # one dot per message
        assert all(not c.light_layers for c in lay.connectors)  # strokes stay full-weight
        labels = [c.label.text for c in lay.connectors if c.label]
        assert labels == ["call()", "ret", "notify"]
        ret = lay.connectors[1]
        assert ret.semantic_dash == "4 5"
        assert ret.track == "static"  # P3: the return dash wins over the march
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
        assert pitches == {56.0}


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
        # Only the mindmap admits more nodes than the global soft cap — its
        # density is governed by sector subdivision, not a pitch shrink.
        assert over_soft == {"tree-radial"}

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
        deep = dict(
            topology="tree",
            nodes=[{"id": "r", "label": "R"}, {"id": "a", "label": "A"}, {"id": "a1", "label": "A1"}],
            edges=[{"source": "r", "target": "a"}, {"source": "a", "target": "a1"}],
        )
        with pytest.raises(DiagramInputError, match="tree: radial"):
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
        from hyperweave.compose.diagram.input import resolve_auto_roles, resolve_diagram_preset
        from hyperweave.compose.matrix.cells import measure_voice
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.diagram import DiagramSpec
        from hyperweave.core.matrix import GlyphTint

        cfg = load_paradigms()["primer"].diagram
        registry = load_glyphs()
        for preset in ("mindmap", "frontier-mindmap"):
            spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset(preset)))
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
            density = ((x1 - x0) * (y1 - y0)) / (lay.width * lay.height)
            assert density >= 0.55, (preset, round(density, 3), lay.width, lay.height)

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
        lay = solve(**CASES["flywheel"])
        self._assert_on_boundary(lay, skip_hub_end=False)

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
        from hyperweave.compose.diagram.input import diagram_preset_names, resolve_auto_roles, resolve_diagram_preset
        from hyperweave.core.diagram import DiagramSpec

        cfg = load_paradigms()["primer"].diagram
        pad = cfg.min_pad_y
        for preset in sorted(diagram_preset_names()):
            spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset(preset)))
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
        for case in ("flywheel", "event-flywheel"):
            if case == "flywheel":
                lay = solve(**CASES["flywheel"])
            else:
                from hyperweave.compose.diagram.input import resolve_auto_roles, resolve_diagram_preset
                from hyperweave.core.diagram import DiagramSpec

                spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset("event-flywheel")))
                lay = compute_diagram_layout(spec, paradigm=cfg, engine=ENGINE, palette_len=5)
            circles = [n for n in lay.nodes if n.shape == "circle" and n.role != "hero"]
            if not circles:
                continue
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
        from hyperweave.compose.diagram.input import resolve_auto_roles, resolve_diagram_preset
        from hyperweave.core.diagram import DiagramSpec

        cfg = load_paradigms()["primer"].diagram
        spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset("model-router")))
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
        """G3 slack rule. Every start-anchored card centers its measured
        content group (|left pad - right pad| <= eps); free-policy cards
        additionally carry no width beyond clamp(ink + 2·pad, min_w, max)."""
        from hyperweave.compose.diagram.chrome import DOT_MARK_W, voice_for
        from hyperweave.compose.diagram.input import diagram_preset_names, resolve_auto_roles, resolve_diagram_preset
        from hyperweave.compose.matrix.cells import measure_voice
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.diagram import DiagramSpec
        from hyperweave.core.matrix import GlyphTint

        cfg = load_paradigms()["primer"].diagram
        registry = load_glyphs()
        eps = 0.6
        checked_free = checked_aligned = 0
        for preset in sorted(diagram_preset_names()):
            spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset(preset)))
            lay = compute_diagram_layout(
                spec,
                paradigm=cfg,
                engine=ENGINE,
                palette_len=5,
                glyph_registry=registry,
                glyph_selections=tuple(GlyphTint.INK for _ in spec.nodes),
            )
            policy = cfg.topologies[lay.layout_slug].width_policy
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
                ink_l, ink_r = min(ink_lefts), max(ink_rights)
                left_pad = ink_l - n.box.x
                right_pad = n.box.x + n.box.w - ink_r
                assert abs(left_pad - right_pad) <= eps, (preset, n.index, left_pad, right_pad)
                if policy == "free":
                    nch = cfg.topologies[lay.layout_slug].node
                    want = (ink_r - ink_l) + 2 * nch.pad_x
                    cap = max(cfg.topologies[lay.layout_slug].card_min_w, want + 2.0)  # 2px even-grid round
                    assert n.box.w <= cap + eps, (preset, n.index, n.box.w, want)
                    checked_free += 1
                else:
                    checked_aligned += 1
        assert checked_free >= 20 and checked_aligned >= 20
        assert DOT_MARK_W == 8.0  # the measured dot advance the rule builds on

    def test_radial_hub_label_clearance(self) -> None:
        """G4: the radial hub label sits in an angular gap and every spoke
        (and the particle path riding it) keeps clear of the label box."""
        from hyperweave.compose.diagram.chrome import voice_for
        from hyperweave.compose.diagram.input import diagram_preset_names, resolve_auto_roles, resolve_diagram_preset
        from hyperweave.compose.matrix.cells import measure_voice
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.diagram import DiagramSpec
        from hyperweave.core.matrix import GlyphTint

        cfg = load_paradigms()["primer"].diagram
        registry = load_glyphs()
        clear = float(ENGINE["connector"]["hub_label_clear"])
        checked = 0
        for preset in sorted(diagram_preset_names()):
            spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset(preset)))
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
        assert checked >= 2  # fanout-radial + mindmap (outboard glyph / wide-name hubs)

    def test_presets_stay_inside_their_canvas(self) -> None:
        """The universal in-canvas invariant, swept over the REAL content:
        synthetic CASES missed a DAG whose content-solved rank width pushed
        the last rank off-frame."""
        from hyperweave.compose.diagram.input import diagram_preset_names, resolve_auto_roles, resolve_diagram_preset
        from hyperweave.core.diagram import DiagramSpec

        cfg = load_paradigms()["primer"].diagram
        for preset in sorted(diagram_preset_names()):
            spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset(preset)))
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
        under-loops) and is exempt."""
        from hyperweave.compose.diagram.input import diagram_preset_names, resolve_auto_roles, resolve_diagram_preset
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.diagram import DiagramSpec
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
        for preset in sorted(diagram_preset_names()):
            spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset(preset)))
            if spec.topology.value in ("sequence", "state-machine"):
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
                back = by_pair.get((t_, s))
                if back is None or s > t_:
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
        assert checked >= 6  # sync-chain x3, gateway x2(+classic), frontier-gateway x2

    def test_channel_lanes_hold_the_period_floor(self) -> None:
        """K3: all-reciprocal pipeline compositions are wire-major — every
        lane run holds the chassis channel_run_min (dash-period legibility);
        node-major pipelines are untouched."""
        from hyperweave.compose.diagram.input import diagram_preset_names, resolve_auto_roles, resolve_diagram_preset
        from hyperweave.core.diagram import DiagramSpec

        cfg = load_paradigms()["primer"].diagram
        run_min = cfg.topologies["pipeline"].channel_run_min
        assert run_min == 144.0  # the triptych pick
        checked = 0
        for preset in sorted(diagram_preset_names()):
            spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset(preset)))
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
        assert checked >= 3  # gateway, gateway-classic, sync-chain

    def test_clearance_law(self) -> None:
        """G7: clearance, not just non-overlap — every non-nested box pair
        breathes by min_clearance, and every box keeps min_clearance from
        every NON-INCIDENT connector path, across all presets."""
        from hyperweave.compose.diagram.input import diagram_preset_names, resolve_auto_roles, resolve_diagram_preset
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.diagram import DiagramSpec
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
            tokens = re.findall(r"([MLCA])\s*((?:-?[\d.]+[, ]*)+)", d)
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
                elif cmd == "A":
                    # Arcs connect adjacent ring cards (incident); skip.
                    cursor = (nums[-2], nums[-1])
                    pts.append(cursor)
            return pts

        for preset in sorted(diagram_preset_names()):
            spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset(preset)))
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
            for ai in range(len(items)):
                for bi in range(ai + 1, len(items)):
                    g = box_gap(items[ai][1], items[bi][1])
                    assert g >= clearance - eps, (preset, items[ai][0], items[bi][0], round(g, 1))
            for c in lay.connectors:
                pts = sample_path(c.path_d)
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

        from hyperweave.compose.diagram.input import diagram_preset_names, resolve_auto_roles, resolve_diagram_preset
        from hyperweave.config.loader import load_glyphs
        from hyperweave.core.diagram import DiagramSpec
        from hyperweave.core.matrix import GlyphTint

        cfg = load_paradigms()["primer"].diagram
        registry = load_glyphs()
        seen = 0
        for preset in sorted(diagram_preset_names()):
            spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset(preset)))
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
