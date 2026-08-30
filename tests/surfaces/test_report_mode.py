"""``respond=report`` — one bounded answer, identical on every surface.

The recorded session ran compose + validate + verify as separate commands and
printed a whole SVG into context (116,626 characters, 22.6% of all shell
output). The report is the transactional replacement: what composed, where it
lives, the compiler's advisories, the integrity verdict, the proof when asked
— never the SVG inline, under the 10 KB output budget.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from typer.testing import CliRunner

from hyperweave.surfaces.registry import CallContext, dispatch
from hyperweave.surfaces.report import REPORT_SCHEMA

runner = CliRunner()

_DIAGRAM = {
    "topology": "pipeline",
    "title": "Report probe",
    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
    "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
}
_PAYLOAD = {"type": "diagram", "genome": "primer", "spec": dict(_DIAGRAM), "respond": "report"}


def _registry_report() -> dict[str, Any]:
    return asyncio.run(dispatch("compose", dict(_PAYLOAD), CallContext(surface="test", base_url="")))


class TestReportShape:
    def test_bounded_never_the_svg(self) -> None:
        report = _registry_report()
        assert report["schema"] == REPORT_SCHEMA
        assert report["ok"] is True
        text = json.dumps(report)
        assert "<svg" not in text
        assert len(text) < 10_000, "the report honors the output budget"

    def test_verdict_fields_are_separate(self) -> None:
        report = _registry_report()
        assert set(report) == {"schema", "ok", "artifact", "integrity", "diagnostics", "warnings", "proof", "next"}
        assert report["integrity"] == {"hash_valid": True, "well_formed": True}
        assert report["proof"] is None  # honest null — nothing faked when unrequested
        assert report["artifact"]["envelope_id"].startswith("sha256:")

    def test_identity_fields_stay_reserved(self) -> None:
        # spec_id / render_id / artifact_hash are the identity model's to mint;
        # today's envelope id must never ship under those names.
        report = _registry_report()
        for reserved in ("spec_id", "render_id", "artifact_hash"):
            assert reserved not in json.dumps(report)

    def test_unknown_respond_refuses(self) -> None:
        import pytest

        from hyperweave.core.errors import HwError

        with pytest.raises(HwError, match="respond"):
            asyncio.run(
                dispatch("compose", {**_PAYLOAD, "respond": "receipt"}, CallContext(surface="test", base_url=""))
            )


class TestReportParityAcrossSurfaces:
    def test_http_mcp_cli_return_the_same_document(self, tmp_path: Any) -> None:
        from fastapi.testclient import TestClient

        from hyperweave.cli import app as cli_app
        from hyperweave.mcp import server as mcp_server
        from hyperweave.serve.app import app as serve_app

        registry = _registry_report()

        resp = TestClient(serve_app).post(
            "/v1/compose", json={"type": "diagram", "genome": "primer", "diagram": dict(_DIAGRAM), "respond": "report"}
        )
        assert resp.status_code == 200, resp.text
        http_doc = resp.json()

        mcp_doc = asyncio.run(
            mcp_server.hw_compose(type="diagram", genome="primer", diagram=dict(_DIAGRAM), respond="report")
        )
        assert isinstance(mcp_doc, dict)

        spec_file = tmp_path / "d.json"
        spec_file.write_text(json.dumps(_DIAGRAM))
        result = runner.invoke(cli_app, ["compose", "diagram", "--spec-file", str(spec_file), "--respond", "report"])
        assert result.exit_code == 0, result.output
        cli_doc = json.loads(result.stdout[result.stdout.index("{") :])

        for name, doc in (("http", http_doc), ("mcp", mcp_doc), ("cli", cli_doc)):
            assert doc["schema"] == REPORT_SCHEMA, name
            assert set(doc) == set(registry), name
            assert doc["artifact"]["envelope_id"] == registry["artifact"]["envelope_id"], name

    def test_cli_report_with_proof_embeds_the_record(self, tmp_path: Any) -> None:
        from hyperweave.cli import app as cli_app

        spec_file = tmp_path / "d.json"
        spec_file.write_text(json.dumps(_DIAGRAM))
        out = tmp_path / "d.svg"
        result = runner.invoke(
            cli_app,
            [
                "compose",
                "diagram",
                "--spec-file",
                str(spec_file),
                "-o",
                str(out),
                "--ground",
                "opaque",
                "--palette",
                "fixed",
                "--proof",
                "--respond",
                "report",
            ],
        )
        assert result.exit_code == 0, result.output
        doc = json.loads(result.stdout[result.stdout.index("{") :])
        assert doc["proof"] is not None and doc["proof"]["schema"] == "proof/1"
        assert (tmp_path / "d.proof.json").exists()
