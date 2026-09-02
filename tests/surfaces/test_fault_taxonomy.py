"""Fault taxonomy — an engine fault is never a caller refusal, on any surface.

Three battery cases pinned per the reseat-then-classify ruling (2026-08-30):
reseat succeeds → compose + a ``chip-air`` advisory; a pair no lawful seat
separates → ``SPEC_INVALID`` naming both chips and the measured gap; any other
post-solve invariant → typed ``ENGINE_INVARIANT``, 500-class, CLI exit 70 with
an ``engine fault:`` prefix and never a traceback.

The CLI cases drive the REAL parser and app (Guard Law) — the printed sentence
and the exit code are the contract, not the function beneath them.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from typer.testing import CliRunner

from hyperweave.compose.diagram.battery import _fault, run_chip_air_battery
from hyperweave.config.loader import load_diagram_config
from hyperweave.core.errors import HwError, HwErrorCode
from tests.compose.test_loop_ir import hillclimb
from tests.compose.test_loop_solver import solve

ENGINE = load_diagram_config()
runner = CliRunner()


AIRY_ENGINE = {"connector": {"chip_pill_air": 90.0}}
"""The doctored tests run under a 90px air law: hillclimb cannot produce two
LAWFULLY SEATED chips within 6px (measured best on-wire approach is 87px), and
an off-wire teleport would break the loop chip-seat law the battery's pipeline
position guarantees green on entry. Raising the config-driven air floor fuses
a lawful pair instead — every other law holds, exactly the production shape."""


def _fused_layout() -> Any:
    """A real solved layout doctored so two chips sit fused under AIRY_ENGINE.

    One chip slides ALONG ITS OWN WIRE to its closest lawful approach to a
    sibling (87px) — realistic density, loop/duplex laws green on entry."""
    import math

    lay = solve(hillclimb())
    chips = [a for a in lay.annotations if a.kind == "edge-chip" and a.box is not None]
    assert len(chips) >= 4, "harness premise: hillclimb carries guard chips"
    mover, target = chips[1], chips[3]
    assert mover.box is not None and target.box is not None
    from hyperweave.compose.diagram.battery import _densify_path, _pill_gap, _translate_annotation
    from hyperweave.compose.geometry.paths import flatten_points

    conn = next(c for c in lay.connectors if c.index == mover.edge_index)
    pts = _densify_path(flatten_points(conn.path_d, curve_samples=16), samples=96)
    bx, by = mover.box.x + mover.box.w / 2, mover.box.y + mover.box.h / 2

    def gap_at(p: tuple[float, float]) -> float:
        import dataclasses

        nb = dataclasses.replace(mover.box, x=p[0] - mover.box.w / 2, y=p[1] - mover.box.h / 2)
        return _pill_gap(nb, target.box)

    tx, ty = min(pts[12:-12], key=gap_at)
    moved = _translate_annotation(mover, tx - bx, ty - by)
    annotations = tuple(moved if ann is mover else ann for ann in lay.annotations)
    doctored = replace(lay, annotations=annotations)
    assert math.isfinite(gap_at((tx, ty))) and gap_at((tx, ty)) < 90.0
    return doctored


class TestChipAirReseatThenClassify:
    def test_reseat_succeeds_with_advisory(self) -> None:
        doctored = _fused_layout()
        reseated, diags = run_chip_air_battery(doctored, AIRY_ENGINE)
        assert len(diags) >= 1
        assert diags[0].rule == "chip-air"
        assert "px apart" in diags[0].measured and "reseated" in diags[0].measured
        # The result satisfies its own law: a second run finds nothing.
        again, more = run_chip_air_battery(reseated, AIRY_ENGINE)
        assert more == ()
        assert again.annotations == reseated.annotations

    def test_reseat_leaves_the_whole_geometry_lawful(self) -> None:
        # A candidate seat is legal only if EVERY law still holds after the
        # move — the review found a reseated pill could land on a foreign
        # wire or break a loop/duplex law the earlier batteries had cleared.
        from hyperweave.compose.diagram.battery import (
            _check_no_wire_through_pill,
            run_duplex_battery,
            run_loop_battery,
        )

        reseated, diags = run_chip_air_battery(_fused_layout(), AIRY_ENGINE)
        assert diags, "harness premise: the fused pair reseats"
        chips = [a for a in reseated.annotations if a.kind == "edge-chip" and a.box is not None]
        _check_no_wire_through_pill(reseated, chips)
        run_loop_battery(reseated)
        run_duplex_battery(reseated)

    def test_unsatisfiable_density_is_spec_invalid_naming_both_chips(self) -> None:
        # Shrinking the canvas denies every candidate seat: the density is the
        # author's to repair, so the outcome is a refusal, never a fault.
        doctored = replace(_fused_layout(), width=1.0, height=1.0)
        with pytest.raises(HwError) as exc:
            run_chip_air_battery(doctored, AIRY_ENGINE)
        assert exc.value.code is HwErrorCode.SPEC_INVALID
        assert not exc.value.is_engine_fault
        assert "px apart" in exc.value.message
        assert exc.value.fix  # author-repairable: a fix line exists

    def test_clean_layout_is_untouched(self) -> None:
        lay = solve(hillclimb())
        out, diags = run_chip_air_battery(lay, ENGINE)
        assert diags == ()
        assert out.annotations == lay.annotations

    def test_status_split(self) -> None:
        assert HwError(HwErrorCode.ENGINE_INVARIANT, "x").http_status == 500
        assert HwError(HwErrorCode.PROJECTION_INVALID, "x").http_status == 500
        assert HwError(HwErrorCode.SPEC_INVALID, "x").http_status == 400
        assert not HwError(HwErrorCode.SPEC_INVALID, "x").is_engine_fault


class TestFaultThroughRealCli:
    def test_engine_fault_exits_70_with_prefix_and_no_traceback(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        import hyperweave.compose.diagram.battery as battery
        from hyperweave.cli import app

        def boom(layout: Any) -> None:
            raise _fault("loop battery: probe invariant failed on a lawful input")

        monkeypatch.setattr(battery, "run_loop_battery", boom)
        out = tmp_path / "out.svg"
        result = runner.invoke(app, ["compose", "diagram", "--spec-file", "loop-retry", "-o", str(out)])
        assert result.exit_code == 70
        assert "engine fault:" in result.output
        assert "probe invariant" in result.output
        assert "Traceback" not in result.output
        assert not out.exists(), "an engine fault never writes a file"

    def test_projection_fault_exits_70_not_2(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        # A projection failure AFTER a successful compose is ours, not the
        # caller's — the generic catch used to print Error: and exit 2.
        import hyperweave.formats.static as static_mod
        from hyperweave.cli import app

        def boom(svg: str, passes: Any) -> Any:
            raise HwError(HwErrorCode.PROJECTION_INVALID, "static projection failed its postcondition (seeded)")

        monkeypatch.setattr(static_mod, "run_passes_counted", boom)
        out = tmp_path / "out.svg"
        result = runner.invoke(
            app, ["compose", "diagram", "--spec-file", "loop-retry", "--format", "svg-static", "-o", str(out)]
        )
        assert result.exit_code == 70
        assert "engine fault:" in result.output
        assert "Traceback" not in result.output

    def test_proof_refuses_non_live_formats(self, tmp_path: Any) -> None:
        # proof/1 law: delivered-equals-inspected. A proof of the live SVG
        # beside an ANSI grid would describe bytes the caller never received.
        from hyperweave.cli import app

        out = tmp_path / "out.txt"
        result = runner.invoke(
            app, ["compose", "diagram", "--spec-file", "loop-retry", "--format", "ansi", "-o", str(out), "--proof"]
        )
        assert result.exit_code == 2
        assert "--format svg only" in result.output

    def test_caller_refusal_keeps_exit_2_without_fault_prefix(self, tmp_path: Any) -> None:
        spec = tmp_path / "seq5.json"
        spec.write_text(
            '{"topology": "sequence", "title": "T", '
            '"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}, '
            '{"id": "d", "label": "D"}, {"id": "e", "label": "E"}], '
            '"edges": [{"source": "a", "target": "b"}]}'
        )
        from hyperweave.cli import app

        result = runner.invoke(app, ["compose", "diagram", "--spec-file", str(spec), "-o", str(tmp_path / "o.svg")])
        assert result.exit_code == 2
        assert "sequence caps at 4 nodes" in result.output
        assert "engine fault:" not in result.output

    def test_chip_air_refusal_names_both_pills_through_cli(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        import hyperweave.compose.diagram.battery as battery
        from hyperweave.cli import app

        def refuse(layout: Any, engine: Any = None) -> Any:
            raise HwError(
                HwErrorCode.SPEC_INVALID,
                "chip battery: pills 'retry' and 'give up' sit 2.1px apart (law >=6px) and no lawful "
                "reseat separates them — two plates that close read as one",
                fix="shorten or drop one of the two labels, or thin the chip density around this run",
            )

        monkeypatch.setattr(battery, "run_chip_air_battery", refuse)
        result = runner.invoke(app, ["compose", "diagram", "--spec-file", "loop-retry", "-o", str(tmp_path / "o.svg")])
        assert result.exit_code == 2
        assert "'retry' and 'give up'" in result.output and "2.1px apart" in result.output
        assert "engine fault:" not in result.output

    def test_validate_returns_structured_record_on_bare_assert(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A residual bare assert anywhere in the solve crosses the validate
        # boundary as a typed record — the recorded traceback never recurs.
        import hyperweave.compose.diagram.battery as battery
        from hyperweave.cli import app

        def bare(layout: Any) -> None:
            raise AssertionError("probe: residual bare assert")

        monkeypatch.setattr(battery, "run_loop_battery", bare)
        result = runner.invoke(app, ["validate", "loop-retry"])
        assert result.exit_code == 70
        assert "INVALID [ENGINE_INVARIANT]" in result.output
        assert "probe: residual bare assert" in result.output
        assert "Traceback" not in result.output
