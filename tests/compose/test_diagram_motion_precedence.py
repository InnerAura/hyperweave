"""Explicit edge-motion outranks default dress — and the payload never lies.

Pins for the diagram close-out fixes:

1. An EXPLICIT dash request (the spec field — which the CLI/HTTP overrides
   write into — or a per-edge field) survives the solid-wire table, a
   relation's dress motion, and the accent-wire stillness. Defaults describe
   only the unrequested case.
2. With no request, the solid-wire grammar still renders solid rails on the
   wire-solid topologies (sequence / state-machine / lanes / flywheel) —
   the quiet default holds. dag reads arrowed terminals only (its rails
   still march by default); hub is not in the solid-wire table at all.
3. ``rendered.track`` / ``rendered.edge_motion`` report wiring's post-dress
   connector values, so the artifact's self-description always matches what
   was drawn.
4. A glyph-circle node resolves its mark through the SAME identity ladder as
   cards (brand ``glyph`` -> semantic ``kind`` -> nothing) — a kind-only node
   never renders an empty circle.
"""

from __future__ import annotations

import pytest

from hyperweave.compose.diagram.input import diagram_preset_names
from tests.compose.test_diagram_layout import _normalized_preset, solve

# The kit wire law: sequence, state-machine, lanes, and flywheel read
# wire:solid+arrow. The "unrequested stays solid" pin needs edges that carry
# NO declared relation/motion. Every parity preset now dresses its edges
# (flywheel-flow's ring declares drift per flywheel-flow), so the pin
# rides a synthetic undressed flywheel instead of a preset.
_WIRE_SOLID_SPECS = {
    "flywheel-plain": {
        "topology": "flywheel",
        "title": "plain wheel",
        "nodes": [
            {"id": "a", "label": "A"},
            {"id": "b", "label": "B"},
            {"id": "c", "label": "C"},
            {"id": "d", "label": "D"},
        ],
    }
}

# Every non-sequence family marches under an EXPLICIT dash request (wiring.py
# precedence: an explicit motion survives the solid-wire downgrade, a
# relation's dress motion, and the accent-wire stillness). Sequence
# (auth-sequence) is excluded: its solver pins track_override static on the
# message strokes, so an explicit dash request can never march there.
_EXPLICIT_DASH_MARCH_PRESETS = ["service-dependencies", "hub", "cicd-machine", "obi-engine"]


def _preset_layout(name: str, **overrides: object):
    spec = _normalized_preset(name)
    return solve(**{**spec.model_dump(exclude_defaults=True), **overrides})


class TestExplicitMotionPrecedence:
    @pytest.mark.parametrize("name", _EXPLICIT_DASH_MARCH_PRESETS)
    def test_explicit_dash_marches_on_wire_solid_topologies(self, name: str) -> None:
        lay = _preset_layout(name, edge_motion="dash")
        marching = [c for c in lay.connectors if c.track == "dash-march"]
        assert marching, name

    @pytest.mark.parametrize("name", sorted(_WIRE_SOLID_SPECS))
    def test_unrequested_default_stays_solid(self, name: str) -> None:
        lay = solve(**_WIRE_SOLID_SPECS[name])
        assert all(c.track != "dash-march" for c in lay.connectors), name

    @pytest.mark.parametrize("name", ["service-dependencies"])
    def test_dag_marches_by_default(self, name: str) -> None:
        # Kit posture: dag (service-dependencies) is not in the wire-solid set
        # (only its terminal arrow is defaulted), so its rails march WITHOUT
        # an explicit request. Lanes joined the wire-solid set (obi-engine)
        # and is covered by test_unrequested_default_stays_solid instead.
        lay = _preset_layout(name)
        assert any(c.track == "dash-march" for c in lay.connectors), name

    def test_hub_relation_dress_governs_march_by_default(self) -> None:
        # A hub partitions its edges by axis role into relations (§3):
        # in/edit/out -> assert (still, solid), read -> drift (marches).
        # Unrequested, each relation's OWN dress motion governs. Built inline:
        # the parity hub preset carries explicit particle riders on its in +
        # read spokes (the hub specimen's 2 riders), which override
        # the default dress this pin measures.
        lay = solve(
            topology="hub",
            hub_policy="axial",
            spine=["artifact", "documents", "surfaces"],
            nodes=[
                {"id": "artifact", "label": "the artifact", "role": "hero", "glyph": "hyperweave"},
                {"id": "spec", "label": "the spec", "kind": "file-text"},
                {"id": "transform", "label": "transform", "kind": "git-branch"},
                {"id": "read", "label": "read", "kind": "eye"},
                {"id": "documents", "label": "documents", "kind": "layers"},
                {"id": "surfaces", "label": "surfaces", "kind": "layout-grid"},
            ],
            edges=[
                {"source": "spec", "target": "artifact", "role": "in"},
                {"source": "artifact", "target": "transform", "role": "edit"},
                {"source": "artifact", "target": "read", "role": "read"},
                {"source": "artifact", "target": "documents", "role": "out"},
                {"source": "artifact", "target": "surfaces", "role": "out"},
            ],
        )
        by_relation: dict[str, set[str]] = {}
        for c in lay.connectors:
            by_relation.setdefault(c.relation, set()).add(c.track)
        assert by_relation.get("assert") == {"static"}
        assert by_relation.get("drift") == {"dash-march"}


class TestRenderedHonesty:
    @pytest.mark.parametrize("name", sorted(diagram_preset_names()))
    def test_payload_reports_the_drawn_track_and_motion(self, name: str) -> None:
        lay = _preset_layout(name)
        by_index = {c.index: c for c in lay.connectors}
        for i, (track, motion) in enumerate(zip(lay.rendered.track, lay.rendered.edge_motion, strict=True)):
            conn = by_index.get(i)
            if conn is None:
                continue
            assert track == conn.track, (name, i)
            assert motion == conn.motion, (name, i)

    @pytest.mark.parametrize("name", sorted(_WIRE_SOLID_SPECS))
    def test_payload_honesty_under_explicit_dash(self, name: str) -> None:
        lay = solve(**{**_WIRE_SOLID_SPECS[name], "edge_motion": "dash"})
        by_index = {c.index: c for c in lay.connectors}
        for i, track in enumerate(lay.rendered.track):
            conn = by_index.get(i)
            if conn is not None:
                assert track == conn.track, (name, i)


class TestGlyphCircleIdentityLadder:
    def test_kind_only_nodes_carry_marks(self) -> None:
        # P6: every parity preset renders cards (specimen census coins:0), so
        # glyph-circle is exercised inline. Five kind-only nodes (including the
        # hero) must each resolve a mark through the identity ladder.
        from hyperweave.compose.diagram.input import resolve_auto_roles
        from hyperweave.compose.diagram.solver import compute_diagram_layout
        from hyperweave.config.loader import load_glyphs, load_paradigms
        from hyperweave.core.diagram import DiagramSpec
        from tests.compose.test_diagram_layout import ENGINE

        spec = resolve_auto_roles(
            DiagramSpec.model_validate(
                {
                    "topology": "flywheel",
                    "node_style": "glyph-circle",
                    "nodes": [
                        {"id": "gen", "label": "Generate", "kind": "zap"},
                        {"id": "dist", "label": "Distribute", "kind": "external-link"},
                        {"id": "cap", "label": "Capture", "kind": "database"},
                        {"id": "imp", "label": "Improve", "kind": "refresh-cw"},
                        {"id": "fw", "label": "the flywheel", "role": "hero", "kind": "repeat"},
                    ],
                }
            )
        )
        lay = compute_diagram_layout(
            spec,
            paradigm=load_paradigms()["primer"].diagram,
            engine=ENGINE,
            palette_len=5,
            glyph_registry=load_glyphs(),
        )
        circles = [n for n in lay.nodes if n.shape == "circle"]
        assert circles
        assert all(n.glyph is not None for n in circles), [n.node_id for n in circles if n.glyph is None]
