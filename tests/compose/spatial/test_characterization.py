"""The spatial probe corpus reproduces its recorded present state, and the
generators produce specs the engine accepts.

Neither test blesses a measurement as lawful. A drift in a recorded number is
a real event: the family repair that moves a slice re-records it on purpose
(``python -m tests.compose.spatial.characterize``), and anything else that
moves one is a regression to look at.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from typer.testing import CliRunner

from hyperweave.cli import app
from tests.compose.spatial import characterize, generators

if TYPE_CHECKING:
    from pathlib import Path

RECORD = json.loads(characterize.RECORD_PATH.read_text())
PROBES = {p["id"]: p for p in characterize.load_probes()}
CASES = generators.all_cases()
TOLERANCE_PX = 0.15


def _close(a: Any, b: Any, path: str) -> list[str]:
    if isinstance(a, float) or isinstance(b, float):
        if (
            isinstance(a, bool)
            or isinstance(b, bool)
            or not isinstance(a, (int, float))
            or not isinstance(b, (int, float))
        ):
            return [f"{path}: {a!r} != {b!r}"]
        return [] if abs(float(a) - float(b)) <= TOLERANCE_PX else [f"{path}: {a} != {b}"]
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for key in sorted(set(a) | set(b)):
            out.extend(_close(a.get(key), b.get(key), f"{path}.{key}"))
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} != {len(b)}"]
        out = []
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            out.extend(_close(x, y, f"{path}[{i}]"))
        return out
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


def test_record_covers_every_probe() -> None:
    assert RECORD["schema"] == characterize.SCHEMA
    assert set(RECORD["probes"]) == set(PROBES)


@pytest.mark.parametrize("probe_id", sorted(PROBES))
def test_probe_reproduces_its_recorded_measurement(probe_id: str, tmp_path: Path) -> None:
    probe = PROBES[probe_id]
    measured = characterize.run_probe(probe, tmp_path)
    recorded = RECORD["probes"][probe_id]["measured"]
    if probe.get("expect_refusal"):
        assert measured["refused"], f"{probe_id} was expected to refuse today and composed instead"
    drift = _close(measured, recorded, probe_id)
    assert not drift, "measurement drifted from the characterization record:\n" + "\n".join(drift)


@pytest.mark.parametrize(("name", "kwargs"), CASES, ids=[name for name, _ in CASES])
def test_generated_spec_is_legal(name: str, kwargs: dict[str, Any]) -> None:
    """Every generated case solves inside the engine's caps — the solver, not
    just the input seam, is the judge (caps are enforced at solve time)."""
    if kwargs["type"] == "diagram":
        characterize.diagram_layout(kwargs)
    else:
        characterize.matrix_layout(kwargs)


_ONE_PER_FAMILY = {name.split("-")[0]: (name, kwargs) for name, kwargs in reversed(CASES)}


@pytest.mark.parametrize(
    ("name", "kwargs"), sorted(_ONE_PER_FAMILY.values()), ids=[n for n, _ in sorted(_ONE_PER_FAMILY.values())]
)
def test_generated_spec_composes_through_the_cli(name: str, kwargs: dict[str, Any], tmp_path: Path) -> None:
    inner = kwargs[kwargs["type"]]
    spec_path = tmp_path / f"{name}.json"
    spec_path.write_text(json.dumps(inner))
    out = tmp_path / f"{name}.svg"
    result = CliRunner().invoke(
        app,
        [
            "compose",
            kwargs["type"],
            "--spec-file",
            str(spec_path),
            "-g",
            "primer",
            "--respond",
            "report",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stderr or result.stdout
    assert json.loads(result.stdout)["ok"] is True
    assert out.exists()
