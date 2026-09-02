"""Record what the engine draws today for the spatial probe corpus.

Probes live in ``tests/fixtures/spatial/probes/*.json``; the recorder composes
each through the surface named in the probe — the real CLI parser for matrix
and diagram specs, the engine for connector-fed frames, a unit call for
formatter checks — measures the result, and writes
``tests/fixtures/spatial/characterization.json``. The record is the present
state, dated; it is never an assertion that the state is lawful.

Regenerate deliberately: ``uv run python -m tests.compose.spatial.characterize``.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from hyperweave.cli import app
from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import coerce_diagram_input
from hyperweave.compose.engine import compose
from hyperweave.compose.matrix.infer import infer_matrix
from hyperweave.compose.matrix.layout import compute_matrix_layout
from hyperweave.config.loader import load_diagram_config, load_glyphs, load_matrix_config, load_paradigms
from hyperweave.core.matrix import MatrixSpec
from hyperweave.core.models import ComposeSpec
from hyperweave.core.paradigm import ParadigmMatrixConfig
from tests.compose.spatial import measure
from tests.conftest import FIXTURES_DIR

PROBES_DIR = FIXTURES_DIR / "spatial" / "probes"
RECORD_PATH = FIXTURES_DIR / "spatial" / "characterization.json"
SCHEMA = "spatial-characterization/1"


def load_probes() -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted(PROBES_DIR.glob("*.json"))]


def _cli_args(probe: dict[str, Any], spec_path: Path, out_svg: Path) -> list[str]:
    c = probe["compose"]
    args = ["compose", c["type"], "--spec-file", str(spec_path), "-g", c.get("genome_id", "primer")]
    if c.get("variant"):
        args += ["--variant", c["variant"]]
    return [*args, "--respond", "report", "-o", str(out_svg)]


def matrix_layout(c: dict[str, Any]) -> tuple[Any, Any, Any]:
    spec = infer_matrix(MatrixSpec(**c["matrix"]))
    cfg = load_paradigms()[c.get("genome_id", "primer")].matrix or ParadigmMatrixConfig()
    layout = compute_matrix_layout(spec, matrix=cfg, config=load_matrix_config(), glyph_registry=load_glyphs())
    return layout, spec, cfg


def diagram_layout(c: dict[str, Any]) -> tuple[Any, Any]:
    cs = ComposeSpec(type="diagram", genome_id=c.get("genome_id", "primer"), diagram=c["diagram"])
    spec = coerce_diagram_input(cs.connector_data, cs).spec
    cfg = load_paradigms()[c.get("genome_id", "primer")].diagram
    return compute_diagram_layout(spec, paradigm=cfg, engine=load_diagram_config(), palette_len=5), cfg


def _refusal(result: Any) -> dict[str, Any]:
    text = (result.stderr or result.stdout or "").strip().splitlines()
    return {"refused": True, "exit_code": result.exit_code, "message": text[-1][:160] if text else ""}


def run_cli_probe(probe: dict[str, Any], workdir: Path) -> dict[str, Any]:
    c = probe["compose"]
    inner = c[c["type"]]
    spec_path = workdir / f"{probe['id']}.json"
    out_svg = workdir / f"{probe['id']}.svg"
    spec_path.write_text(json.dumps(inner))
    result = CliRunner().invoke(app, _cli_args(probe, spec_path, out_svg))
    if result.exit_code != 0 or not out_svg.exists():
        return _refusal(result)
    report = json.loads(result.stdout)
    svg = out_svg.read_text()
    record: dict[str, Any] = {
        "refused": False,
        "exit_code": 0,
        "report_ok": report["ok"],
        "diagnostics": sorted({d.get("rule", "") for d in report.get("diagnostics", [])}),
        "warnings": len(report.get("warnings", [])),
        **measure.svg_summary(svg),
    }
    if c["type"] == "matrix":
        layout, spec, cfg = matrix_layout(c)
        record["layout"] = measure.matrix_summary(layout, spec, cfg)
    else:
        layout, cfg = diagram_layout(c)
        record["layout"] = measure.diagram_summary(layout)
        if layout.lane_bands:
            record["layout"]["lane_bands"] = measure.lane_band_overlaps(layout, cfg)
    return record


def run_engine_probe(probe: dict[str, Any]) -> dict[str, Any]:
    result = compose(ComposeSpec(**probe["compose"]))
    return {
        "refused": False,
        "width": result.width,
        "height": result.height,
        "warnings": len(result.warnings),
        "diagnostics": sorted({d.get("rule", "") for d in result.diagnostics}),
        **measure.svg_summary(result.svg),
    }


def run_sweep_probe(probe: dict[str, Any]) -> dict[str, Any]:
    widths: dict[str, Any] = {}
    for item in probe["sweep"]["items"]:
        try:
            result = compose(ComposeSpec(**{**probe["compose"], **item}))
        except ValueError as exc:
            widths[item["divider_variant"]] = f"refused: {exc}"[:120]
            continue
        widths[item["divider_variant"]] = result.width
    return {"refused": False, "widths": widths}


def run_receipt_probe(probe: dict[str, Any], workdir: Path) -> dict[str, Any]:
    c = probe["compose"]
    out_svg = workdir / f"{probe['id']}.svg"
    args = [
        "compose",
        "receipt",
        c["session"],
        "-g",
        c.get("genome_id", "primer"),
        "--respond",
        "report",
        "-o",
        str(out_svg),
    ]
    result = CliRunner().invoke(app, args)
    if result.exit_code != 0 or not out_svg.exists():
        return _refusal(result)
    stdout = result.stdout.strip()
    honored = stdout.startswith("{")
    record: dict[str, Any] = {"refused": False, "exit_code": 0, "report_honored": honored}
    if honored:
        record["report_ok"] = json.loads(stdout)["ok"]
    return {**record, **measure.svg_summary(out_svg.read_text())}


def run_unit_probe(probe: dict[str, Any]) -> dict[str, Any]:
    fn = getattr(measure, probe["unit"]["fn"])
    return {"refused": False, "result": fn(*probe["unit"]["args"])}


def run_probe(probe: dict[str, Any], workdir: Path) -> dict[str, Any]:
    surface = probe["surface"]
    if surface == "cli":
        return run_cli_probe(probe, workdir)
    if surface == "engine":
        return run_engine_probe(probe)
    if surface == "engine-sweep":
        return run_sweep_probe(probe)
    if surface == "cli-receipt":
        return run_receipt_probe(probe, workdir)
    if surface == "unit":
        return run_unit_probe(probe)
    raise ValueError(f"unknown probe surface {surface!r}")


def record_all(workdir: Path) -> dict[str, Any]:
    probes = {}
    for probe in load_probes():
        probes[probe["id"]] = {
            "defects": probe["defects"],
            "surface": probe["surface"],
            "measured": run_probe(probe, workdir),
        }
    return {
        "schema": SCHEMA,
        "recorded": dt.date.today().isoformat(),
        "note": (
            "Present-state measurements of the spatial probe corpus. Not a statement of lawfulness; "
            "each family repair flips its slice and re-records."
        ),
        "probes": probes,
    }


def main() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        record = record_all(Path(tmp))
    RECORD_PATH.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    print(f"recorded {len(record['probes'])} probes → {RECORD_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
