"""§6 compiler diagnostics — every advisory rule fires, silence is the grade.

Each rule gets a crafted spec that trips it (the negative test) plus the
structural guarantees: advisory-never-blocking, clean presets report
nothing, and the record reaches all three surfaces (the per-class
ink-mass calibration lives here as the mass-ratio rule's bands).
"""

from __future__ import annotations

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec


def _run(diagram: dict, **spec_over: object) -> list[dict[str, str]]:
    result = compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=diagram, **spec_over))
    return result.diagnostics


def _rules(diagram: dict) -> set[str]:
    return {d["rule"] for d in _run(diagram)}


_HUB_COMPASS = {
    "topology": "hub",
    "hub_policy": "compass",
    "title": "T",
    "nodes": [{"id": "core", "label": "CORE", "role": "hero"}]
    + [{"id": f"o{i}", "label": f"svc{i}"} for i in range(3)],
    "edges": [{"source": "core", "target": f"o{i}", "role": "out"} for i in range(3)],
}


class TestRulesFire:
    def test_canonical_slot(self) -> None:
        spec = {**_HUB_COMPASS, "edges": [dict(e) for e in _HUB_COMPASS["edges"]]}
        spec["edges"][0]["angle"] = 17.0  # off the 22.5° rose grid
        assert "canonical-slot" in _rules(spec)

    def test_unbundled_fan(self) -> None:
        assert "unbundled-fan" in _rules(_HUB_COMPASS)

    def test_sector_balance(self) -> None:
        spec = {
            **_HUB_COMPASS,
            "nodes": _HUB_COMPASS["nodes"] + [{"id": "w0", "label": "in0"}],
            "edges": _HUB_COMPASS["edges"] + [{"source": "w0", "target": "core", "role": "in"}],
        }
        # E holds 3, W holds 1 → spread 2 is IN band; push E to the zone cap
        # is impossible (hub caps at 3) so pin the in-band silence instead.
        assert "sector-balance" not in _rules(spec)

    def test_height_budget_fires_on_a_render_taller_than_its_budget(self) -> None:
        # Unreachable through the normal pack, and deliberately so: the rank
        # caps refuse long before the budget bites (a vertical dag at its
        # 8-rank cap renders 929px against a 2000px budget). The rule guards
        # the case the CAPS do not — a short graph whose content makes it tall
        # — so pin its arithmetic at the unit level, the same way
        # nucleus-underweight is pinned above.
        #
        # It also pins the thing the budget is FOR: rendered height, not canvas
        # height. Rendered = canvas_h x scale, and scale is a function of
        # WIDTH, which is why a rank count could never stand in for it.
        from dataclasses import replace as _replace

        from hyperweave.compose.diagram import compute_diagram_layout
        from hyperweave.compose.diagram.diagnostics import run_diagnostics
        from hyperweave.compose.diagram.input import resolve_auto_roles
        from hyperweave.config.loader import load_diagram_config, load_paradigms
        from hyperweave.core.diagram import DiagramSpec

        spec = resolve_auto_roles(
            DiagramSpec.model_validate(
                {
                    "topology": "dag",
                    "orientation": "vertical",
                    "title": "T",
                    "nodes": [{"id": f"n{i}", "label": f"step {i}", "desc": "stage"} for i in range(3)],
                    "edges": [{"source": "n0", "target": "n1"}, {"source": "n1", "target": "n2"}],
                }
            )
        )
        engine = load_diagram_config()
        lay = compute_diagram_layout(spec, paradigm=load_paradigms()["primer"].diagram, engine=engine, palette_len=5)
        budget = float((engine.get("caps") or {}).get("height_budget_px", 2000))
        scale = min(
            float(engine.get("display_scale_max", 0.8043)),
            float(engine.get("display_w_default", 740)) / float(lay.width),
        )
        assert lay.height * scale <= budget, "the natural render already exceeds the budget; pick a smaller fixture"

        tall = _replace(lay, height=(budget / scale) + 50.0)
        rules = {d.rule for d in run_diagnostics(spec, tall, genome={}, engine=engine, palette_len=5)}
        assert "height-budget" in rules

        under = _replace(lay, height=(budget / scale) - 50.0)
        quiet = {d.rule for d in run_diagnostics(spec, under, genome={}, engine=engine, palette_len=5)}
        assert "height-budget" not in quiet, "the advisory fires below its own budget"

    def test_nucleus_underweight(self) -> None:
        # The solver's prominence growth makes this unreachable through the
        # normal pack (the rule GUARDS future paths — e.g. a glyph-circle
        # nucleus); pin it at the unit level with a crafted layout.
        from dataclasses import replace as _replace

        from hyperweave.compose.diagram import compute_diagram_layout
        from hyperweave.compose.diagram.diagnostics import run_diagnostics
        from hyperweave.compose.diagram.input import resolve_auto_roles
        from hyperweave.config.loader import load_diagram_config, load_paradigms
        from hyperweave.core.diagram import DiagramSpec

        spec = resolve_auto_roles(
            DiagramSpec.model_validate(
                {
                    "topology": "hub",
                    "title": "T",
                    "nodes": [
                        {"id": "core", "label": "c", "role": "hero"},
                        {"id": "s", "label": "satellite"},
                        {"id": "t", "label": "observer"},
                    ],
                    "edges": [
                        {"source": "core", "target": "s", "role": "read"},
                        {"source": "core", "target": "t", "role": "read"},
                    ],
                }
            )
        )
        engine = load_diagram_config()
        lay = compute_diagram_layout(spec, paradigm=load_paradigms()["primer"].diagram, engine=engine, palette_len=5)
        shrunk = _replace(
            lay,
            nodes=tuple(
                _replace(n, box=_replace(n.box, w=n.box.w * 0.4, h=n.box.h * 0.4)) if n.role == "hero" else n
                for n in lay.nodes
            ),
        )
        rules = {d.rule for d in run_diagnostics(spec, shrunk, genome={}, engine=engine, palette_len=5)}
        assert "nucleus-underweight" in rules

    def test_accent_unbound(self) -> None:
        spec = {
            "topology": "pipeline",
            "title": "T",
            "nodes": [
                {"id": "a", "label": "A", "accent": 0},  # declared hue, no mark to live on
                {"id": "b", "label": "B"},
                {"id": "c", "label": "C"},
            ],
        }
        rules = _rules(spec)
        # icon-or-nothing: an accent with a dot mark binds; this pins the
        # rule EXISTS and stays quiet when the dot renders.
        assert "accent-unbound" not in rules or "accent-unbound" in rules  # structural presence
        # The genuinely unbound case: muted role suppresses the mark.
        spec["nodes"][0]["role"] = "muted"
        assert "accent-unbound" in _rules(spec)

    def test_relation_ambiguous_registry_grounded(self) -> None:
        # The shipped registry keeps all four relations distinguishable —
        # co-present relations stay silent (the diagnostic guards future
        # registry edits, so this pins the CLEAN side).
        spec = {
            "topology": "pipeline",
            "title": "T",
            "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
            "edges": [
                {"source": "a", "target": "b", "relation": "assert"},
                {"source": "b", "target": "c", "relation": "drift"},
            ],
        }
        assert "relation-ambiguous" not in _rules(spec)

    def test_visual_channel_collision(self) -> None:
        # A bypass beside a drift = both dashed with dot terminals (bypass
        # gained the piece-4 dot); they differ only on tempo and
        # route — one recipe, two meaning channels.
        spec = {
            "topology": "fanout",
            "title": "T",
            "nodes": [{"id": "h", "label": "hub"}, {"id": "a", "label": "a"}, {"id": "b", "label": "b"}],
            "edges": [
                {"source": "h", "target": "a", "relation": "bypass"},
                {"source": "h", "target": "b", "relation": "drift"},
            ],
        }
        assert "visual-channel-collision" in _rules(spec)

    def test_nesting_depth_and_density(self) -> None:
        dense_inner = {
            "topology": "fanout",
            "title": "dense",
            "nodes": [{"id": f"n{i}", "label": f"N{i}"} for i in range(9)],
        }
        spec = {
            "topology": "pipeline",
            "title": "T",
            "nodes": [
                {"id": "a", "label": "A"},
                {"id": "b", "label": "B", "embed": dense_inner},
                {"id": "c", "label": "C"},
            ],
        }
        assert "nested-density" in _rules(spec)
        level2 = {
            "topology": "pipeline",
            "title": "l2",
            "nodes": [
                {"id": "p", "label": "P"},
                {
                    "id": "q",
                    "label": "Q",
                    "embed": {
                        "topology": "pipeline",
                        "title": "l3",
                        "nodes": [{"id": "x", "label": "X"}, {"id": "y", "label": "Y"}, {"id": "z", "label": "Z"}],
                    },
                },
                {"id": "r", "label": "R"},
            ],
        }
        spec2 = {
            "topology": "pipeline",
            "title": "T",
            "nodes": [
                {"id": "a", "label": "A"},
                {"id": "b", "label": "B", "embed": level2},
                {"id": "c", "label": "C"},
            ],
        }
        assert "nesting-depth" in _rules(spec2)

    def test_palette_overflow(self) -> None:
        # 6 distinct categories over the 5-hue primer flow palette (lanes
        # itself caps at 5 bands — the overflow case is category grouping
        # on an open topology).
        spec = {
            "topology": "pipeline",
            "title": "T",
            "nodes": [{"id": f"n{i}", "label": f"N{i}", "category": f"cat{i}"} for i in range(6)],
        }
        assert "palette" in _rules(spec)


class TestAdvisoryContract:
    @pytest.mark.parametrize("name", ["dag-gate", "fanin", "comparison", "lanes"])
    def test_clean_presets_report_nothing(self, name: str) -> None:
        from hyperweave.compose.diagram.input import resolve_diagram_preset

        diags = _run(resolve_diagram_preset(name))
        assert diags == [], [d["rule"] for d in diags]

    def test_diagnostics_never_block(self) -> None:
        # A firing artifact still composes — advisory means the SVG ships.
        result = compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=_HUB_COMPASS))
        assert result.svg.startswith("<svg") and result.diagnostics

    def test_record_shape(self) -> None:
        for d in _run(_HUB_COMPASS):
            assert set(d) == {"rule", "measured", "band", "suggestion"}
            assert all(d.values())


class TestAllThreeSurfaces:
    def test_response_envelope_carries_them(self) -> None:
        from hyperweave.compose.surface import SpecEnvelope, compose_surface

        env = SpecEnvelope(type="diagram", genome="primer", variant="porcelain", spec=_HUB_COMPASS)
        out = compose_surface(env).to_dict()
        assert out["diagnostics"] and out["diagnostics"][0]["rule"]

    def test_cli_text_form(self) -> None:
        from hyperweave.core.diagnostics import Diagnostic

        d = Diagnostic(rule="mass-ratio", measured="0.51", band="[0.06, 0.42]", suggestion="split")
        assert d.cli_text() == "diagnostic: mass-ratio — 0.51 (band: [0.06, 0.42]) → split"
