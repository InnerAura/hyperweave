"""Session-3 surface truth: intent reaches every surface, diff sees edges,
validate speaks JSON, the two-node floor holds, and every metadata claim
carries a referent.

The intent parity test proves the SAME lineage intent lands through CLI, HTTP,
and MCP — the registry model, the handler that used to drop it, the CLI flag,
and the handwritten MCP wrapper are four separate seams and any one of them
silently losing the field is exactly the recorded defect.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from typer.testing import CliRunner

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec
from hyperweave.verbs import diff, transform

runner = CliRunner()

_PATCH = [{"op": "replace", "path": "/nodes/0/label", "value": "Gateway"}]
_INTENT = "rename the entry node for the ops audience"


def _diagram_svg() -> str:
    return compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            ground="opaque",
            palette="fixed",
            diagram={
                "topology": "pipeline",
                "title": "Flow",
                "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
                "edges": [
                    {"source": "a", "target": "b", "label": "ship"},
                    {"source": "b", "target": "c"},
                ],
            },
        )
    ).svg


def _lineage_intents(result: dict[str, Any]) -> list[str]:
    return [e.get("intent", "") for e in result.get("lineage", [])]


class TestIntentParity:
    def test_cli_http_mcp_carry_the_same_intent(self, tmp_path: Any) -> None:
        svg = _diagram_svg()
        src = tmp_path / "a.svg"
        src.write_text(svg)

        # CLI — the real parser, the real flag.
        from hyperweave.cli import app

        result = runner.invoke(
            app,
            ["transform", str(src), "--patch-json", json.dumps(_PATCH), "--intent", _INTENT],
        )
        assert result.exit_code == 0, result.output
        cli_env = json.loads(result.stdout[result.stdout.index("{") :])

        # HTTP — the factory-mounted POST route.
        from fastapi.testclient import TestClient

        from hyperweave.serve.app import app as serve_app

        resp = TestClient(serve_app).post("/v1/transform", json={"source": svg, "mutations": _PATCH, "intent": _INTENT})
        assert resp.status_code == 200, resp.text
        http_env = resp.json()

        # MCP — the handwritten wrapper that used to drop the field.
        import asyncio

        from hyperweave.mcp import server as mcp_server

        mcp_out = asyncio.run(mcp_server.hw_transform(svg, _PATCH, intent=_INTENT))
        assert isinstance(mcp_out, dict)
        mcp_env = mcp_out

        for name, env in (("cli", cli_env), ("http", http_env), ("mcp", mcp_env)):
            assert _INTENT in _lineage_intents(env), f"{name} surface dropped the intent"


class TestDiffSeesEdges:
    def test_edge_label_change_is_reported_not_same(self) -> None:
        # The live reproduction: an edge-label-only change used to collapse
        # into {"same": true}.
        svg_a = _diagram_svg()
        r = transform(svg_a, [{"op": "replace", "path": "/edges/0/label", "value": "deploy"}], ts="t")
        d = diff(svg_a, r.svg)
        assert d.same is False
        assert any(c.get("edge") == "a->b" and c.get("field") == "label" and c.get("to") == "deploy" for c in d.changed)

    def test_repeated_pair_keeps_identity_by_declaration_index(self) -> None:
        from hyperweave.verbs.diff import _diff_diagram

        a = {"edges": [{"source": "x", "target": "y", "label": "req"}, {"source": "x", "target": "y", "label": "ack"}]}
        b = {"edges": [{"source": "x", "target": "y", "label": "req"}, {"source": "x", "target": "y", "label": "nak"}]}
        _added, _removed, changed = _diff_diagram(a, b)
        assert any(c.get("edge") == "x->y#1" and c.get("field") == "label" for c in changed)

    def test_identical_diagrams_stay_same(self) -> None:
        svg = _diagram_svg()
        assert diff(svg, svg).same is True


class TestValidateJson:
    def test_json_flag_emits_the_report_dict(self) -> None:
        from hyperweave.cli import app

        result = runner.invoke(app, ["validate", "loop-retry", "--json"])
        assert result.exit_code == 0
        report = json.loads(result.stdout)
        assert report["valid"] is True and report["type"] == "diagram"

    def test_json_flag_on_invalid_carries_the_envelope(self, tmp_path: Any) -> None:
        from hyperweave.cli import app

        bad = tmp_path / "bad.json"
        bad.write_text('{"topology": "pipeline", "nodes": [], "edges": []}')
        result = runner.invoke(app, ["validate", str(bad), "--json"])
        assert result.exit_code == 1
        report = json.loads(result.stdout)
        assert report["valid"] is False and report["error"]["code"]


class TestTwoNodeFloor:
    @pytest.mark.parametrize("topology", ["pipeline", "pipeline-vertical"])
    def test_two_node_relation_composes(self, topology: str) -> None:
        # Boundary pin: the census's six refused two-node sites stay legal —
        # the floor must not drift back to 3.
        spec = {
            "topology": "pipeline",
            "orientation": "vertical" if topology.endswith("vertical") else "horizontal",
            "title": "Two",
            "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "edges": [{"source": "a", "target": "b"}],
        }
        svg = compose(ComposeSpec(type="diagram", genome_id="primer", diagram=spec)).svg
        assert "<svg" in svg


class TestClaimReferents:
    def test_dash_diagram_declares_paint_ok_and_not_cim(self) -> None:
        svg = _diagram_svg()  # default edge motion is dash — stroke-dashoffset
        assert 'performance="paint-ok"' in svg
        assert 'cim-compliant="false"' in svg
        assert re.search(r"<hw:constraints-applied>(?:(?!cim-compliant).)*</hw:constraints-applied>", svg, re.DOTALL)

    def test_badge_stays_composite_only_phi_and_cim(self) -> None:
        svg = compose(ComposeSpec(type="badge", title="BUILD", value="passing")).svg
        assert 'performance="composite-only"' in svg
        assert 'cim-compliant="true"' in svg
        assert 'timing="phi"' in svg

    def test_animated_diagram_names_its_register_not_phi(self) -> None:
        svg = _diagram_svg()
        m = re.search(r'timing="([^"]+)"', svg)
        assert m is not None
        assert m.group(1) != "phi", "an animated diagram runs the replay clock, never the phi ladder"

    def test_lifecycle_frozen_never_collides_with_motion_vocabulary(self) -> None:
        svg = compose(ComposeSpec(type="badge", title="BUILD", value="passing")).svg
        assert 'data-hw-state="frozen"' in svg
        assert 'data-hw-state="static"' not in svg

    def test_contrast_claim_names_its_worst_pair(self) -> None:
        svg = compose(ComposeSpec(type="badge", title="BUILD", value="passing")).svg
        m = re.search(r'contrast-ratio="([0-9.]+):1" contrast-worst-pair="([^"]+)"', svg)
        assert m is not None
        assert m.group(2) in {"ink/surface", "ink-secondary/surface", "ink-on-accent/accent"}
