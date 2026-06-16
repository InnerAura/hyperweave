"""Motion-grammar math pinned against the alpha.3 canon constants.

Every expected value below traces to a specimen in
v04/specimens/diagrams/diagram-topologies/ (hw-diagram-alpha3-canon.html
spatial-notes + gradient defs, hw-connector-additions.html).
"""

from __future__ import annotations

import itertools

import pytest

from hyperweave.compose.diagram.motion import (
    beam_gradients,
    beam_window,
    choreography_for,
    detect_lanes,
    flow_gradient,
    flow_period,
    lane_endpoints,
    performance_tier,
    relay_slots,
    replay_clock,
    resolve_edge_motions,
    resolve_track,
)
from hyperweave.compose.diagram.paths import sagitta, subdivide_arc
from hyperweave.config.loader import load_diagram_config
from hyperweave.core.diagram import DiagramInputError, EdgeMotion, ResolvedEdge

CFG = load_diagram_config()
BEAM = CFG["beam"]
FLOW = CFG["flow"]
SEQ = CFG["sequence_replay"]
LADDER = CFG["fallback_ladder"]
TRACK_MAP = {"dash": "dash-march", "particle": "dash-march", "beam": "static", "flow": "static"}


def edge(source: int = 0, target: int = 1, **kw: object) -> ResolvedEdge:
    return ResolvedEdge(source=source, target=target, **kw)  # type: ignore[arg-type]


class TestClamps:
    def test_beam_window_short_edge_canon(self) -> None:
        # Relay on 142px pipeline edges: clamp(.55x142)=78.1 -> 80 (canon W=80).
        assert beam_window(142, BEAM) == 80

    def test_beam_window_caps_on_long_fans(self) -> None:
        assert beam_window(430, BEAM) == 130

    def test_beam_window_floor(self) -> None:
        assert beam_window(60, BEAM) == 50  # clamped to 48, rounded to 10

    def test_flow_period_canon_streaming(self) -> None:
        # clamp(0.6x142, 80, 170) = 85, rounded to 90 (canon caption).
        assert flow_period(142, FLOW) == 90

    def test_flow_period_caps(self) -> None:
        assert flow_period(540, FLOW) == 170


class TestRelayClock:
    def test_three_edge_relay_reproduces_canon_slots(self) -> None:
        # Canon pipeline relay: .02-.28 / .34-.60 / .66-.92, rest to 1.
        assert relay_slots(3, BEAM["relay"]) == [(0.02, 0.28), (0.34, 0.6), (0.66, 0.92)]

    def test_relay_slots_general_n(self) -> None:
        slots = relay_slots(4, BEAM["relay"])
        assert slots[0][0] == 0.02
        assert all(round(b - a, 4) == round(slots[0][1] - slots[0][0], 4) for a, b in slots)
        assert slots[-1][1] < 1.0 - float(BEAM["relay"]["cycle_rest"]) + 1e-9


class TestReplayClock:
    """K-seq: each message is an independent comet event whose transit obeys
    the K1 speed law; the shared clock is DERIVED so order semantics hold
    while the clock stretches to fit the speed of light."""

    V, DMIN, DMAX = 144.0, 2.618, 4.236

    def _clock(self, spans: list[float]) -> tuple[float, list[tuple[float, float]]]:
        return replay_clock(spans, v_target=self.V, dur_min=self.DMIN, dur_max=self.DMAX, seq_cfg=SEQ)

    def test_clock_is_derived_from_beats_and_transits(self) -> None:
        spans = [247.0, 247.0, 700.0]
        total, _slots = self._clock(spans)
        transits = [min(max(s / self.V, self.DMIN), self.DMAX) for s in spans]
        lead, gap, rest = float(SEQ["lead_beat"]), float(SEQ["gap_beat"]), float(SEQ["rest_beat"])
        assert total == pytest.approx(lead + sum(transits) + gap * (len(spans) - 1) + rest)

    def test_each_transit_obeys_the_speed_law(self) -> None:
        # Short span clamps to dur_min (slower than v_target); a long span
        # clamps to dur_max; mid spans hit v_target exactly.
        spans = [60.0, 480.0, 900.0]  # 60/144<min -> min; 480/144 -> 3.333; 900/144>max -> max
        total, slots = self._clock(spans)
        for span, (s, e) in zip(spans, slots, strict=True):
            transit = (e - s) * total
            expected = min(max(span / self.V, self.DMIN), self.DMAX)
            assert transit == pytest.approx(expected, abs=0.02)
            if transit < self.DMAX - 0.01:  # only dur_max-clamped tails legally exceed v_target
                assert span / transit <= self.V + 1.0  # never above the speed of light otherwise
        # The mid span hits v_target exactly.
        mid_transit = (slots[1][1] - slots[1][0]) * total
        assert spans[1] / mid_transit == pytest.approx(self.V, abs=1.0)

    def test_slots_replay_in_order_without_overlap(self) -> None:
        _, slots = self._clock([247.0, 300.0, 247.0, 500.0])
        starts = [s for s, _ in slots]
        assert starts == sorted(starts)  # ordered top-to-bottom
        for (_, e0), (s1, _) in itertools.pairwise(slots):
            assert s1 >= e0 - 1e-9  # gap beat between events; no overlap

    def test_rest_beat_precedes_the_loop(self) -> None:
        # The last event ends before t=1 by at least the rest fraction.
        total, slots = self._clock([247.0, 247.0])
        assert slots[-1][1] < 1.0
        assert (1.0 - slots[-1][1]) * total >= float(SEQ["rest_beat"]) - 0.01


class TestMotionResolution:
    def test_default_and_overrides(self) -> None:
        edges = [edge(), edge(1, 2, edge_motion=EdgeMotion.BEAM)]
        motions, fb = resolve_edge_motions(
            edges,
            spec_motion=None,
            default="particle",
            allowlist=["dash", "particle", "beam", "flow"],
            composite_only=False,
            ladder=LADDER,
        )
        assert motions == ["particle", "beam"]
        assert fb is False

    def test_spec_override_between_edge_and_default(self) -> None:
        motions, _ = resolve_edge_motions(
            [edge(), edge(1, 2, edge_motion=EdgeMotion.DASH)],
            spec_motion=EdgeMotion.FLOW,
            default="particle",
            allowlist=["dash", "particle", "beam", "flow"],
            composite_only=False,
            ladder=LADDER,
        )
        assert motions == ["flow", "dash"]

    def test_allowlist_violation_raises(self) -> None:
        with pytest.raises(DiagramInputError, match="allowlist"):
            resolve_edge_motions(
                [edge(edge_motion=EdgeMotion.BEAM)],
                spec_motion=None,
                default="dash",
                allowlist=["dash"],
                composite_only=False,
                ladder=LADDER,
            )

    def test_fallback_ladder_under_composite_only(self) -> None:
        motions, fb = resolve_edge_motions(
            [edge(edge_motion=EdgeMotion.BEAM), edge(1, 2, edge_motion=EdgeMotion.FLOW)],
            spec_motion=None,
            default="particle",
            allowlist=["dash", "particle", "beam", "flow"],
            composite_only=True,
            ladder=LADDER,
        )
        assert motions == ["particle", "dash"]
        assert fb is True


class TestTrackChannel:
    def test_composite_values_ride_the_march(self) -> None:
        assert resolve_track("particle", track_map=TRACK_MAP, semantic_dash="") == "dash-march"
        assert resolve_track("dash", track_map=TRACK_MAP, semantic_dash="") == "dash-march"

    def test_paint_values_ride_a_static_tube(self) -> None:
        assert resolve_track("beam", track_map=TRACK_MAP, semantic_dash="") == "static"
        assert resolve_track("flow", track_map=TRACK_MAP, semantic_dash="") == "static"

    def test_p3_semantic_dash_wins(self) -> None:
        # A sequence return edge carries a meaning-bearing dasharray: the
        # march never overwrites semantics.
        assert resolve_track("particle", track_map=TRACK_MAP, semantic_dash="4 5") == "static"


class TestPerformanceTier:
    def test_paint_ok_iff_animated_paint_renders(self) -> None:
        assert performance_tier(["particle", "beam"], [False, False]) == "paint-ok"
        assert performance_tier(["particle", "dash"], [False, False]) == "composite-only"

    def test_inert_beam_does_not_claim_paint(self) -> None:
        assert performance_tier(["beam"], [True]) == "composite-only"


class TestLanes:
    def test_reciprocal_pair_takes_opposite_lanes(self) -> None:
        edges = [edge(0, 1), edge(1, 0), edge(1, 2), edge(2, 1)]
        assert detect_lanes(edges, 4.0) == [-1, 1, -1, 1]

    def test_singles_stay_centered(self) -> None:
        assert detect_lanes([edge(0, 1), edge(1, 2)], 4.0) == [0, 0]

    def test_lane_endpoints_offset_perpendicular(self) -> None:
        # The REAL pair has REVERSED chords (the old pin gave both lanes the
        # same chord and missed the cancellation): one canonical axis, the
        # lane sign picks sides, each lane gap/2 from the centerline.
        fwd = lane_endpoints(0, 100, 50, 100, -1, 4.0)
        rev = lane_endpoints(50, 100, 0, 100, 1, 4.0)
        assert fwd == (0, 98, 50, 98)
        assert rev == (50, 102, 0, 102)
        assert abs(fwd[1] - rev[1]) == 4.0  # centerline separation == gap


class TestArcSubdivision:
    def test_flywheel_quarter_arcs_stay_whole(self) -> None:
        # Canon: ~42-degree arcs at r=178 sit under the threshold (~12px).
        assert sagitta(178, 42) < 16
        assert subdivide_arc(-66, -24, 178, 16, 6) == [(-66, -24)]

    def test_deep_arcs_subdivide_within_threshold(self) -> None:
        segments = subdivide_arc(-90, -18, 178, 16, 6)  # K=3 flywheel span
        assert len(segments) == 2
        for a0, a1 in segments:
            assert sagitta(178, abs(a1 - a0)) <= 16


class TestBeamGradients:
    def test_relay_translate_reproduces_canon_values(self) -> None:
        # Canon pipeline relay edge 104->246 (length 142, W=80):
        # values "24 0;24 0;246 0;246 0", keyTimes 0;.02;.28;1.
        body, filament = beam_gradients(
            id_base="c0",
            x1=104,
            y1=140,
            x2=246,
            y2=140,
            length=142,
            hue="#1D4ED8",
            hue2="#1E40A0",
            choreo="relay",
            slot=(0.02, 0.28),
            begin="",
            beam_cfg=BEAM,
        )
        assert body.animate is not None
        assert body.animate.values == "24 140;24 140;246 140;246 140"
        assert body.animate.keytimes == "0;0.02;0.28;1"
        assert body.animate.calc_mode == "spline"
        assert filament.animate is not None
        assert filament.animate.values == body.animate.values

    def test_volley_starts_one_window_before_the_edge(self) -> None:
        body, _ = beam_gradients(
            id_base="c1",
            x1=138,
            y1=183,
            x2=560,
            y2=183,
            length=430,
            hue="#7C3AED",
            hue2=None,
            choreo="volley",
            slot=None,
            begin="0.55s",
            beam_cfg=BEAM,
        )
        assert body.animate is not None
        assert body.animate.values.startswith("8 183;")  # 138 - W(130)
        assert body.animate.begin == "0.55s"
        # Ramp duty: single hue end to end.
        assert len({s.color for s in body.stops}) == 1

    def test_identity_duty_is_two_hue(self) -> None:
        body, _ = beam_gradients(
            id_base="c2",
            x1=0,
            y1=0,
            x2=142,
            y2=0,
            length=142,
            hue="#1D4ED8",
            hue2="#1E40A0",
            choreo="relay",
            slot=(0.02, 0.28),
            begin="",
            beam_cfg=BEAM,
        )
        assert {s.color for s in body.stops} == {"#1D4ED8", "#1E40A0"}


class TestFlowGradient:
    def test_streaming_period_translate_canon(self) -> None:
        # Canon pipeline streaming: period 90, values "0 0;90 0", 2.6s.
        g = flow_gradient(
            id_base="c0", x1=104, y1=140, x2=246, y2=140, length=142, hue="#1D4ED8", begin="", flow_cfg=FLOW
        )
        assert g.animate is not None
        assert g.animate.values == "0 0;90 0"
        assert g.spread == "repeat"
        assert g.animate.dur == "2.6s"

    def test_arc_segments_phase_offset_keeps_current_continuous(self) -> None:
        g = flow_gradient(
            id_base="c1",
            x1=0,
            y1=0,
            x2=100,
            y2=0,
            length=110,
            hue="#1D4ED8",
            begin="",
            flow_cfg=FLOW,
            phase_px=45.0,
        )
        assert g.animate is not None
        assert g.animate.begin.startswith("-")  # negative begin = phase shift


class TestChoreography:
    @pytest.mark.parametrize(
        ("layout", "motion", "mode"),
        [
            ("pipeline", "beam", "relay"),
            ("stack", "beam", "relay"),
            ("fanout-horizontal", "beam", "volley"),
            ("convergence", "beam", "arrivals"),
            ("flywheel", "flow", "circulation"),
            ("pipeline", "flow", "streaming"),
            ("dag", "flow", "current"),
            ("state-machine", "beam", "volley"),
        ],
    )
    def test_layout_motion_modes(self, layout: str, motion: str, mode: str) -> None:
        assert choreography_for(layout, motion, CFG["choreography"]) == mode


class TestSpeedLaw:
    """K1 — one speed of light: free-choreography particles travel at
    constant velocity (dur = clamp(L / v_target, dur_min, dur_max)); a
    particle on a marching track overtakes the texture by the floor
    multiple. Slot-locked clocks (sequence replay, beam relay) are
    SEMANTIC choreography and exempt."""

    def test_particle_velocity_band_and_overtake(self) -> None:
        from hyperweave.compose.diagram import compute_diagram_layout
        from hyperweave.compose.diagram.input import diagram_preset_names, resolve_auto_roles, resolve_diagram_preset
        from hyperweave.config.loader import load_diagram_config, load_glyphs, load_paradigms
        from hyperweave.core.diagram import DiagramSpec
        from hyperweave.core.matrix import GlyphTint

        cfg = load_paradigms()["primer"].diagram
        engine = load_diagram_config()
        registry = load_glyphs()
        phase = abs(float(engine["track"]["march_offset_to"])) / float(str(engine["track"]["march_dur"]).rstrip("s"))
        checked = 0
        for preset in sorted(diagram_preset_names()):
            spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset(preset)))
            if spec.topology.value == "sequence":
                continue  # replay slots are the semantic clock
            lay = compute_diagram_layout(
                spec,
                paradigm=cfg,
                engine=engine,
                palette_len=5,
                glyph_registry=registry,
                glyph_selections=tuple(GlyphTint.INK for _ in spec.nodes),
            )
            for p in lay.particles:
                c = lay.connectors[p.connector_index]
                dur = float(p.dur.rstrip("s"))
                expected = min(max(c.length / cfg.motion_v_target, cfg.motion_dur_min), cfg.motion_dur_max)
                if c.track == "dash-march":
                    expected = min(expected, c.length / (cfg.track_overtake_floor * phase))
                    assert c.length / dur >= cfg.track_overtake_floor * phase - 0.2, (preset, c.index)
                assert abs(dur - expected) <= 0.01, (preset, c.index, dur, expected)
                if dur < cfg.motion_dur_max - 0.01:  # dur_max-clamped tails legally exceed v_target
                    assert c.length / dur <= cfg.motion_v_target + 1.0, (preset, c.index)
                checked += 1
        assert checked >= 20

    def test_volley_beams_share_transit_velocity(self) -> None:
        from hyperweave.compose.diagram import compute_diagram_layout
        from hyperweave.compose.diagram.input import resolve_auto_roles, resolve_diagram_preset
        from hyperweave.config.loader import load_diagram_config, load_glyphs, load_paradigms
        from hyperweave.core.diagram import DiagramSpec
        from hyperweave.core.matrix import GlyphTint

        cfg = load_paradigms()["primer"].diagram
        engine = load_diagram_config()
        spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_diagram_preset("fanout-volley")))
        lay = compute_diagram_layout(
            spec,
            paradigm=cfg,
            engine=engine,
            palette_len=5,
            glyph_registry=load_glyphs(),
            glyph_selections=tuple(GlyphTint.INK for _ in spec.nodes),
        )
        clock = float(str(engine["beam"]["volley"]["dur"]).rstrip("s"))
        speeds = []
        by_suffix = {g.id_suffix: g for g in lay.gradients}
        for c in lay.connectors:
            body = next(
                (g for ref in c.light_layers for g in [by_suffix[ref.gradient_ref]] if ref.kind == "halo"), None
            )
            if body is None or body.animate is None:
                continue
            travel_end = float(body.animate.keytimes.split(";")[1])
            speeds.append(c.length / (travel_end * clock))
        assert len(speeds) >= 5
        # All comets within a tight band around the shared velocity.
        assert max(speeds) - min(speeds) <= 0.25 * max(speeds), speeds


class TestEdgeMotionAcrossSubstrates:
    """Every closed-2x2 mode renders well-formed on a light AND a dark genome,
    and the payload records the requested mode — the override's surface proof."""

    @pytest.mark.parametrize("variant", ["porcelain", "noir"])
    @pytest.mark.parametrize("mode", ["dash", "particle", "beam", "flow"])
    def test_mode_renders_on_light_and_dark(self, mode: str, variant: str) -> None:
        import json as _json
        import re as _re
        import xml.etree.ElementTree as ET

        from hyperweave.compose.engine import compose
        from hyperweave.core.models import ComposeSpec

        spec = {
            "topology": "pipeline",
            "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
            "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
            "edge_motion": mode,
        }
        svg = compose(ComposeSpec(type="diagram", genome_id="primer", variant=variant, diagram=spec)).svg
        ET.fromstring(svg)  # well-formed on this substrate
        m = _re.search(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>", svg, _re.DOTALL)
        assert m, "hw:payload missing"
        assert mode in _json.loads(m.group(1))["rendered"]["edge_motion"]


def test_entrance_rejects_unknown_value() -> None:
    """ParadigmDiagramConfig.entrance is validated at load — a typo or an
    unlanded value (draw-on) raises instead of silently no-opping."""
    from pydantic import ValidationError

    from hyperweave.core.paradigm import ParadigmDiagramConfig

    assert ParadigmDiagramConfig(entrance="fade").entrance == "fade"
    assert ParadigmDiagramConfig(entrance="none").entrance == "none"
    with pytest.raises(ValidationError):
        ParadigmDiagramConfig(entrance="draw-on")
