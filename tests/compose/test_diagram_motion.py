"""Motion-grammar math pinned against the canon constants.

Every expected value below traces to a specimen in
v04/specimens/diagrams/diagram-topologies/ (hw-diagram-alpha3-canon.html
spatial-notes + gradient defs, hw-connector-additions.html).
"""

from __future__ import annotations

import pytest

from hyperweave.config.loader import load_diagram_config
from hyperweave.core.diagram import ResolvedEdge

CFG = load_diagram_config()
SEQ = CFG["sequence_replay"]
LADDER = CFG["fallback_ladder"]
TRACK_MAP = {"dash": "dash-march", "particle": "dash-march"}


def edge(source: int = 0, target: int = 1, **kw: object) -> ResolvedEdge:
    return ResolvedEdge(source=source, target=target, **kw)  # type: ignore[arg-type]


class TestSpeedLaw:
    """K1 — one speed of light: free-choreography particles travel at
    constant velocity (dur = clamp(L / v_target, dur_min, dur_max)); a
    particle on a marching track overtakes the texture by the floor
    multiple. Slot-locked clocks (sequence replay, beam relay) are
    SEMANTIC choreography and exempt."""

    def test_particle_velocity_band_and_overtake(self) -> None:
        from hyperweave.compose.diagram import compute_diagram_layout
        from hyperweave.compose.diagram.input import coerce_diagram_input, diagram_preset_names, resolve_diagram_preset
        from hyperweave.config.loader import load_diagram_config, load_glyphs, load_paradigms
        from hyperweave.core.matrix import GlyphTint
        from hyperweave.core.models import ComposeSpec

        cfg = load_paradigms()["primer"].diagram
        engine = load_diagram_config()
        registry = load_glyphs()
        phase = abs(float(engine["track"]["march_offset_to"])) / float(str(engine["track"]["march_dur"]).rstrip("s"))
        checked = 0
        for preset in sorted(diagram_preset_names()):
            # Particles are opt-in under the diagrams-v3 kit's dash default —
            # force particle motion so this sweep still exercises the K1
            # speed law broadly across the preset library.
            cs = ComposeSpec(
                type="diagram",
                genome_id="primer",
                diagram={**resolve_diagram_preset(preset), "edge_motion": "particle"},
            )
            # The production input seam (cyclic presets promote before solve).
            spec = coerce_diagram_input(cs.connector_data, cs).spec
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
                if p.connector_index < 0:
                    # The flywheel rim-orbit riders (flywheel-orbit)
                    # are a fixed-count, fixed-phi-duration ornament tracing
                    # the FULL closed rim, not a per-edge speed-law rider —
                    # connector_index is a sentinel (no single connector owns
                    # their length), so the K1 sweep excludes them.
                    continue
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


class TestEdgeMotionAcrossSubstrates:
    """Every closed-2x2 mode renders well-formed on a light AND a dark genome,
    and the payload records the requested mode — the override's surface proof."""

    @pytest.mark.parametrize("variant", ["porcelain", "noir"])
    @pytest.mark.parametrize("mode", ["dash", "particle"])
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


# ── Beam (the reference-specimen recipe) ─────────────────────────────────────


def test_beam_windows_reproduce_the_relay_specimen_exactly() -> None:
    """The sequential relay family at N=3 reproduces the frontier-handoff
    specimen's windows to the digit: .02-.28 / .34-.60 / .66-.92."""
    from hyperweave.compose.diagram import motion as mo
    from hyperweave.config.loader import load_diagram_config

    cfg = load_diagram_config()["beam"]
    assert mo.beam_windows(3, cfg, family="relay") == [(0.02, 0.28), (0.34, 0.6), (0.66, 0.92)]
    # N=1 is capped at relay_span_cap (.30, the wider of the two specimen
    # citations) rather than filling the whole clock — a lone stage still
    # gets the ~1.5s window both specimens converge on, not a 4.7s crawl.
    assert mo.beam_windows(1, cfg, family="relay") == [(0.02, 0.32)]


def test_beam_windows_reproduce_parity_branch_family() -> None:
    """The trunk-then-branches family is always exactly two stages —
    the parity specimen's .02-.30 / .32-.62."""
    from hyperweave.compose.diagram import motion as mo
    from hyperweave.config.loader import load_diagram_config

    cfg = load_diagram_config()["beam"]
    assert mo.beam_windows(2, cfg, family="branch") == [(0.02, 0.3), (0.32, 0.62)]


def test_beam_gradient_pair_shape() -> None:
    """One beam edge yields the (body, front) pair: shared animate record
    (one clock, staged 4-point keyTimes, spline + keySplines), pad spread,
    true-zero end stops, geometry baked at the edge start with the window
    vector pointing back — safe at identity transform when SMIL strips."""
    from hyperweave.compose.diagram import motion as mo
    from hyperweave.config.loader import load_diagram_config

    cfg = load_diagram_config()["beam"]
    body, front = mo.beam_gradient(0, 100.0, 50.0, 300.0, 50.0, stage=(0.02, 0.28), cfg=cfg)
    assert body.animate is front.animate  # byte-identical animate blocks
    assert body.animate.keytimes == "0;0.02;0.28;1"
    assert body.animate.calc_mode == "spline" and body.animate.keysplines
    assert body.animate.dur == "5.236s"
    # travel = run (200) + window (120); relative from '0 0'
    assert body.animate.values == "0 0;0 0;320 0;320 0"
    assert body.spread == "" and front.spread == ""
    assert body.stops[0].opacity == 0.0 and body.stops[-1].opacity == 0.0
    assert front.stops[0].opacity == 0.0 and front.stops[-1].opacity == 0.0
    # body window points BACK one window from the start; front a shorter span
    assert (body.x1, body.y1, body.x2, body.y2) == (100.0, 50.0, -20.0, 50.0)
    assert (front.x1, front.x2) == (100.0, 62.0)
    assert body.stops[1].color == "#60A5FA" and body.stops[-1].color == "#A78BFA"
    assert front.stops[1].color == "#2563EB"


def test_beam_dag_stages_by_rank_transition() -> None:
    """A dag beam fires per rank transition (the N-stage generalization of
    the parity trunk-then-branches law): edges leaving one rank share a
    window; windows are ordered and non-overlapping on one clock."""
    import re as _re2

    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    spec = {
        "title": "rank relay",
        "topology": "dag",
        "edge_motion": "beam",
        "nodes": [
            {"id": "a", "label": "alpha", "desc": "entry"},
            {"id": "b", "label": "beta", "desc": "mid"},
            {"id": "c", "label": "gamma", "desc": "mid"},
            {"id": "d", "label": "delta", "desc": "sink"},
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "a", "target": "c"},
            {"source": "b", "target": "d"},
            {"source": "c", "target": "d"},
        ],
    }
    svg = compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=spec)).svg
    keytimes = sorted({m.group(1) for m in _re2.finditer(r'keyTimes="([^"]+)"', svg)})
    # Two rank transitions (a→{b,c}, {b,c}→d) = two staged windows shared
    # pairwise across the four edges. N=2 is capped at relay_span_cap (.30)
    # rather than the raw by-count division (.42) — .02-.32 / .38-.68.
    assert keytimes == ["0;0.02;0.32;1", "0;0.38;0.68;1"], keytimes


def test_sequence_beam_falls_back_honestly() -> None:
    """Sequence owns its replay grammar: a requested beam ladders to particle
    with requested/rendered recorded honestly — and no gradientTransform
    reaches the document."""
    import json as _json2
    import re as _re3

    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    spec = {
        "title": "seq beam",
        "topology": "sequence",
        "edge_motion": "beam",
        "nodes": [{"id": "u", "label": "User"}, {"id": "a", "label": "API"}],
        "edges": [
            {"source": "u", "target": "a", "label": "call", "kind": "call"},
            {"source": "a", "target": "u", "label": "reply", "kind": "return"},
        ],
    }
    svg = compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=spec)).svg
    assert 'attributeName="gradientTransform"' not in svg
    m = _re3.search(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>", svg, _re3.DOTALL)
    assert m is not None
    rendered = _json2.loads(m.group(1))["rendered"]
    assert "beam" not in rendered["edge_motion"]
    assert rendered.get("fallback_applied") is True
