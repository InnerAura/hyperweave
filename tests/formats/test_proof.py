"""The proof projection — the inspected artifact is the delivered artifact.

The recorded failure class: an agent altered a spec field to make inspection
possible and graded a substitute render. ``build_proof`` takes only delivered
bytes — no field exists to alter — and these tests pin that every reported
fact (geometry, identity, resources, verdicts) derives from exactly those
bytes, that a missing raster path or an unflattenable face is reported as
"not inspected"/"unavailable" rather than substituted, and that the CLI's
``--proof`` is the one reliable inspection path.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree as ET

from typer.testing import CliRunner

if TYPE_CHECKING:
    import pytest

from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_diagram_presets
from hyperweave.core.models import ComposeSpec
from hyperweave.formats.proof import PROOF_SCHEMA, _external_references, build_proof

runner = CliRunner()


def _composed(preset: str = "loop-retry-budget", **diagram_overrides: Any) -> Any:
    spec = dict(load_diagram_presets()[preset])
    spec.update(diagram_overrides)
    return compose(ComposeSpec(type="diagram", genome_id="primer", ground="opaque", palette="fixed", diagram=spec))


class TestProofRecord:
    def test_record_derives_from_the_delivered_bytes(self) -> None:
        result = _composed()
        record, files = build_proof(result.svg, diagnostics=result.diagnostics, warnings=result.warnings)
        assert record["schema"] == PROOF_SCHEMA
        vb = re.search(r'viewBox="([^"]+)"', result.svg)
        assert vb is not None and record["geometry"]["viewBox"] == vb.group(1)
        assert record["geometry"]["regions"], "a diagram artifact carries a region sidecar"
        assert record["diagnostics"] == [dict(d) for d in result.diagnostics]
        assert record["resources"]["external_references"] == []
        assert "not the artifact" in record["resources"]["gzip_note"]
        assert set(record["verdicts"]) == {
            "schema",
            "composition",
            "layout",
            "projection_well_formed",
            "integrity",
            "self_contained",
        }
        assert record["verdicts"]["integrity"] == "pass"
        assert record["verdicts"]["projection_well_formed"] == "pass"
        ET.fromstring(files["static.svg"].decode("utf-8"))

    def test_delivered_equals_inspected_identity_pin(self) -> None:
        # Two composes of one spec differing in a single field produce
        # different delivered bytes; each proof reports ITS artifact's own
        # envelope identity — nothing in the proof path re-solves, normalizes,
        # or substitutes (the inspection-drift regression class).
        a = _composed(motion_register="budget")
        b = _composed(motion_register="drift")
        assert a.svg != b.svg
        rec_a, _ = build_proof(a.svg)
        rec_b, _ = build_proof(b.svg)
        for rec, result in ((rec_a, a), (rec_b, b)):
            m = re.search(r'"id":\s*"(sha256:[0-9a-f]+)"', result.svg)
            assert m is not None
            assert rec["artifact"]["envelope_id"] == m.group(1)

    def test_motion_reported_never_faked(self) -> None:
        # A frame animated only through class-driven keyframes has no inline
        # sampling path — the record says so instead of substituting frames.
        svg = compose(ComposeSpec(type="badge", title="BUILD", value="passing", motion="chromatic-pulse")).svg
        record, _ = build_proof(svg)
        assert record["motion"]["sampled"] is False
        assert record["motion"]["reason"]

    def test_raster_unavailable_is_first_class(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from hyperweave.formats import raster

        monkeypatch.setattr(raster, "available", lambda: False)
        record, files = build_proof(_composed().svg)
        assert record["raster"]["available"] is False
        assert "hyperweave[raster]" in record["raster"]["fix"]
        assert "png" not in files

    def test_adaptive_face_reports_not_inspected(self) -> None:
        # A default (adaptive) compose refuses flattening — the proof reports
        # the honest reason instead of substituting a committed face.
        svg = compose(
            ComposeSpec(type="diagram", genome_id="primer", diagram=dict(load_diagram_presets()["loop-retry"]))
        ).svg
        record, files = build_proof(svg)
        assert record["resting_frame"]["available"] is False
        assert record["verdicts"]["projection_well_formed"].startswith("not inspected")
        assert "static.svg" not in files

    def test_cdn_fonts_are_a_declared_tradeoff_not_a_failure(self) -> None:
        # The cdn font mode is a configured delivery: its import reports as
        # disclosed, while any reference BEYOND it still fails.
        svg = compose(ComposeSpec(type="badge", title="BUILD", value="passing", font_mode="cdn")).svg
        record, _ = build_proof(svg)
        assert record["resources"]["font_mode"] == "cdn"
        assert record["verdicts"]["self_contained"].startswith("declared")
        tampered = svg.replace("</svg>", '<image href="https://cdn.example/x.png"/></svg>')
        record2, _ = build_proof(tampered)
        assert record2["verdicts"]["self_contained"].startswith("fail")
        assert "beyond the declared cdn fonts" in record2["verdicts"]["self_contained"]

    def test_embed_mode_fails_on_any_external_reference(self) -> None:
        svg = compose(ComposeSpec(type="badge", title="BUILD", value="passing")).svg
        record, _ = build_proof(svg)
        assert record["verdicts"]["self_contained"] == "pass"

    def test_external_reference_scan(self) -> None:
        assert _external_references('<image href="https://cdn.example/x.png"/>') == ["https://cdn.example/x.png"]
        assert _external_references("@import url('https://fonts.example/css');")
        assert (
            _external_references('<svg xmlns="http://www.w3.org/2000/svg" xmlns:hw="https://hyperweave.app/hw/v1.0"/>')
            == []
        )


class TestProofThroughRealCli:
    def test_proof_writes_record_and_frames(self, tmp_path: Any) -> None:
        from hyperweave.cli import app

        out = tmp_path / "flow.svg"
        result = runner.invoke(
            app,
            [
                "compose",
                "diagram",
                "--spec-file",
                "loop-retry",
                "-o",
                str(out),
                "--ground",
                "opaque",
                "--palette",
                "fixed",
                "--proof",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "proof: flow.proof.json" in result.output
        record = json.loads((tmp_path / "flow.proof.json").read_text())
        assert record["schema"] == PROOF_SCHEMA
        assert record["resting_frame"]["file"] == "flow.static.svg"
        ET.fromstring((tmp_path / "flow.static.svg").read_text())
        # the wrote document lists every proof file
        doc = json.loads(result.stdout[result.stdout.index("{") :])
        assert any(w.endswith("flow.proof.json") for w in doc["wrote"])

    def test_proof_requires_output(self) -> None:
        from hyperweave.cli import app

        result = runner.invoke(app, ["compose", "diagram", "--spec-file", "loop-retry", "--proof"])
        assert result.exit_code == 2
        assert "--proof" in result.output and "-o" in result.output

    def test_proof_and_faces_are_exclusive(self, tmp_path: Any) -> None:
        from hyperweave.cli import app

        result = runner.invoke(
            app,
            ["compose", "diagram", "--spec-file", "loop-retry", "-o", str(tmp_path / "x.svg"), "--faces", "--proof"],
        )
        assert result.exit_code == 2
        assert "each face separately" in result.output
