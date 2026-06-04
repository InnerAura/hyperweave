"""Configurable badge state-indicator shape (square / circle / diamond).

The indicator shape is a cascade: request (?state_glyph_shape=) > genome/variant
state_glyph_shape > paradigm badge.indicator_shape > substrate default (light →
circle, dark → square). All four badge paradigms dispatch their indicator through
the shared ``indicators/<shape>-indicator.j2`` partials, so any shape renders in
any paradigm.

Byte-equality of the DEFAULT path (existing variants render identically) is pinned
by test_badge_brutalist_dark / test_badge_cellular and the pre/post raw-diff gate;
this file pins the BEHAVIOR: shapes flip on override, degrade on garbage, and the
root attribute mirrors what painted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hyperweave.compose.engine import compose
from hyperweave.compose.validate_paradigms import validate_genome_variants
from hyperweave.config.loader import load_genomes
from hyperweave.core.models import ComposeSpec
from hyperweave.core.schema import INDICATOR_SHAPES, GenomeSpec

_INDICATORS_DIR = Path(__file__).resolve().parent.parent.parent / "src/hyperweave/templates/frames/badge/indicators"


def _badge(**kw: object) -> str:
    base: dict[str, object] = {
        "type": "badge",
        "title": "BUILD",
        "value": "passing",
        "state": "passing",
        "glyph": "github",
    }
    base.update(kw)
    return compose(ComposeSpec(**base)).svg  # type: ignore[arg-type]


def _status_zone(svg: str) -> str:
    """The status-indicator <g> block (or '' when no indicator paints)."""
    marker = 'data-hw-zone="status"'
    if marker not in svg:
        return ""
    return svg.split(marker, 1)[1].split("</g>", 1)[0]


def _rendered_shape(svg: str) -> str:
    zone = _status_zone(svg)
    if "<circle" in zone:
        return "circle"
    if "rotate(45)" in zone:
        return "diamond"
    if "<rect" in zone:
        return "square"
    return "none"


# --------------------------------------------------------------------------- #
# Defaults — each paradigm keeps its canonical shape (byte-equality contract)  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "genome,variant,shape",
    [
        ("brutalist", "celadon", "square"),  # dark substrate
        ("brutalist", "archive", "circle"),  # light substrate
        ("chrome", "horizon", "diamond"),
        ("automata", "teal", "square"),
    ],
)
def test_default_shape_per_paradigm(genome: str, variant: str, shape: str) -> None:
    svg = _badge(genome_id=genome, variant=variant)
    assert _rendered_shape(svg) == shape
    assert f'data-hw-state-shape="{shape}"' in svg


# --------------------------------------------------------------------------- #
# Request override — the interchange, across every paradigm                    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "genome,variant,requested",
    [
        ("brutalist", "celadon", "circle"),  # dark → circle
        ("brutalist", "archive", "square"),  # light → square
        ("chrome", "horizon", "square"),  # diamond → square
        ("automata", "teal", "diamond"),  # square → diamond
    ],
)
def test_request_override_flips_shape(genome: str, variant: str, requested: str) -> None:
    svg = _badge(genome_id=genome, variant=variant, state_glyph_shape=requested)
    assert _rendered_shape(svg) == requested
    assert f'data-hw-state-shape="{requested}"' in svg


def test_request_override_normalizes_case() -> None:
    svg = _badge(genome_id="chrome", variant="horizon", state_glyph_shape="Circle")
    assert _rendered_shape(svg) == "circle"


def test_unknown_request_shape_degrades_to_default() -> None:
    """Untrusted request input: garbage defers to the paradigm default, no raise."""
    svg = _badge(genome_id="chrome", variant="horizon", state_glyph_shape="hexagon")
    assert _rendered_shape(svg) == "diamond"
    assert ComposeSpec(type="badge", state_glyph_shape="hexagon").state_glyph_shape == ""


# --------------------------------------------------------------------------- #
# Stateless badges carry neither indicator nor shape attribute                 #
# --------------------------------------------------------------------------- #


def test_stateless_badge_has_no_indicator_or_shape_attr() -> None:
    svg = _badge(genome_id="brutalist", variant="celadon", title="PYPI", value="v1.2.3", state="active")
    assert _status_zone(svg) == ""
    assert "data-hw-state-shape=" not in svg


# --------------------------------------------------------------------------- #
# Config-side validation is strict (developer error fails loud at load)        #
# --------------------------------------------------------------------------- #


def test_genomespec_rejects_invalid_shape() -> None:
    with pytest.raises(ValidationError, match="state_glyph_shape"):
        GenomeSpec(id="x", name="x", state_glyph_shape="hexagon")


def test_variant_override_invalid_shape_rejected_at_load() -> None:
    """A typo'd shape in variant_overrides fails validate_genome_variants."""
    brutalist = load_genomes()["brutalist"]
    raw = brutalist.model_dump()
    overrides = dict(raw["variant_overrides"])
    target = next(iter(overrides))  # any whitelisted variant
    overrides[target] = {**overrides[target], "state_glyph_shape": "hexagon"}
    raw["variant_overrides"] = overrides
    bad = GenomeSpec(**raw)
    with pytest.raises(ValueError, match="state_glyph_shape"):
        validate_genome_variants(bad)


def test_all_indicator_partials_exist() -> None:
    """Every canonical shape has a partial behind its include slug."""
    for shape in INDICATOR_SHAPES:
        assert (_INDICATORS_DIR / f"{shape}-indicator.j2").is_file()
