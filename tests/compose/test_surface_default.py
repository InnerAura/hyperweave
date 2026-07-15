"""Genome-preferred default surface — primer defaults to twin.

The genome's ``default_surface`` fills the surface resolution ONLY when the
caller supplied nothing at all (an explicit plate writes "opaque"/"fixed" and
stays plate), and only on surface-mode frames — a primer badge stays plate
silently. A flattening --format on a DEFAULTED adaptive artifact commits to
the plate instead of failing; an EXPLICIT adaptive request still fails loud.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

from hyperweave.cli import app
from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

runner = CliRunner()

_DIAGRAM = {
    "topology": "pipeline",
    "title": "Default Surface",
    "nodes": [{"id": "a", "label": "in"}, {"id": "b", "label": "mid"}, {"id": "c", "label": "out"}],
}


def _svg(**overrides: object) -> str:
    return compose(
        ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=_DIAGRAM, **overrides)
    ).svg


class TestGenomeDefaultSurface:
    def test_bare_primer_diagram_defaults_to_twin(self) -> None:
        svg = _svg()
        assert 'data-hw-adapt="adaptive"' in svg
        assert 'data-hw-surface="twin"' in svg
        assert "prefers-color-scheme" in svg

    def test_explicit_plate_stays_plate(self) -> None:
        svg = _svg(ground="opaque", palette="fixed")
        assert "data-hw-adapt" not in svg

    def test_explicit_inlay_wins_over_the_default(self) -> None:
        svg = _svg(ground="bare", palette="adaptive")
        assert 'data-hw-surface="inlay"' in svg

    def test_primer_badge_stays_plate_silently(self) -> None:
        svg = compose(ComposeSpec(type="badge", genome_id="primer", variant="porcelain")).svg
        assert "data-hw-adapt" not in svg

    def test_genome_without_preference_stays_plate(self) -> None:
        from hyperweave.compose.resolver import _genome_default_surface

        assert _genome_default_surface({}, "diagram") is None
        assert _genome_default_surface({"default_surface": "plate"}, "diagram") is None
        # The preference is frame-gated: a non-surface-mode frame ignores it.
        assert _genome_default_surface({"default_surface": "twin"}, "badge") is None


class TestDefaultedAdaptiveFlattening:
    def test_svg_static_commits_the_defaulted_twin_to_plate(self, tmp_path: Path) -> None:
        out = tmp_path / "flat.svg"
        result = runner.invoke(
            app,
            [
                "compose",
                "diagram",
                "--spec-file",
                "rag-pipeline",
                "-g",
                "primer",
                "--format",
                "svg-static",
                "-o",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        flat = out.read_text()
        assert "var(--dna" not in flat
        assert "data-hw-adapt" not in flat

    def test_explicit_twin_plus_static_fails_loud(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "compose",
                "diagram",
                "--spec-file",
                "rag-pipeline",
                "-g",
                "primer",
                "--surface",
                "twin",
                "--format",
                "svg-static",
                "-o",
                str(tmp_path / "x.svg"),
            ],
        )
        assert result.exit_code != 0
