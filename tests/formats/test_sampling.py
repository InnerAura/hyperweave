"""Choreography sampling — a turn loop is reviewed as turn, at the phi beats.

Frames bake the artifact's OWN channel values at beats of its own cycle:
states the animation actually passes through, never a substitute artifact.
Everything unsampleable is disclosed, not faked.
"""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_diagram_presets
from hyperweave.core.models import ComposeSpec
from hyperweave.formats.sampling import PHI_BEATS, _value_at, sample_choreography


def _loop_svg() -> str:
    return compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            ground="opaque",
            palette="fixed",
            diagram=dict(load_diagram_presets()["loop-retry-budget"]),
        )
    ).svg


class TestSampleChoreography:
    def test_loop_samples_four_parsing_frames(self) -> None:
        svg = _loop_svg()
        sampled = sample_choreography(svg)
        assert sampled is not None
        record, frames = sampled
        assert record["sampled"] is True
        assert record["beats"] == [f"{b * record['cycle_s']:.2f}s" for b in PHI_BEATS]
        assert record["cycle_s"] > 0
        assert "easing functions are not simulated" in record["interpolation"]
        assert len(frames) == len(PHI_BEATS)
        for name, data in frames.items():
            text = data.decode("utf-8")
            ET.fromstring(text)  # every frame obeys the projection postcondition
            assert not re.search(r"animation(?:-[a-z]+)*\s*:", text.split("<style")[0])
            assert "var(--" not in text
            assert name.startswith("beat-")

    def test_frames_differ_across_beats(self) -> None:
        # The beats land at different points of the cycle, so the baked channel
        # values differ — identical frames would mean sampling faked a state.
        sampled = sample_choreography(_loop_svg())
        assert sampled is not None
        _record, frames = sampled
        assert len({data for data in frames.values()}) > 1

    def test_no_inline_channels_returns_none(self) -> None:
        svg = compose(ComposeSpec(type="badge", title="BUILD", value="passing", motion="chromatic-pulse")).svg
        assert sample_choreography(svg) is None

    def test_interpolation_is_linear_between_stops(self) -> None:
        stops: list[tuple[float, dict[str, float]]] = [(0.0, {"opacity": 0.0}), (50.0, {"opacity": 1.0})]
        assert _value_at(stops, "opacity", 25.0) == 0.5
        assert _value_at(stops, "opacity", 80.0) == 1.0  # holds past the last stop
        assert _value_at(stops, "opacity", 0.0) == 0.0


class TestProofMotionIntegration:
    def test_proof_of_a_loop_carries_sampled_frames(self) -> None:
        from hyperweave.formats.proof import build_proof

        record, files = build_proof(_loop_svg())
        assert record["motion"]["sampled"] is True
        beat_files = [k for k in files if k.startswith("beat-")]
        assert len(beat_files) == len(PHI_BEATS)

    def test_unsampleable_motion_stays_disclosed(self) -> None:
        from hyperweave.formats.proof import build_proof

        svg = compose(ComposeSpec(type="badge", title="BUILD", value="passing", motion="chromatic-pulse")).svg
        record, files = build_proof(svg)
        assert record["motion"]["sampled"] is False
        assert "resting frame" in record["motion"]["reason"]
        assert not [k for k in files if k.startswith("beat-")]


class TestDoctorReadiness:
    def test_doctor_reports_compositor_before_composing(self) -> None:
        from typer.testing import CliRunner

        from hyperweave.cli import app

        result = CliRunner().invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "Compositor:" in result.output
        assert "raster (png/webp)" in result.output
        assert "genomes:" in result.output
        assert "--proof" in result.output

    def test_doctor_output_precedes_runtimes(self) -> None:
        from typer.testing import CliRunner

        from hyperweave.cli import app

        out: Any = CliRunner().invoke(app, ["doctor"]).output
        assert out.index("Compositor:") < out.index("Runtimes:")
