"""svg-static projection — the var-flatten law (var()→hex for non-browser rasterizers).

Migrated from tests/compose/test_targets.py when the destination `--target`
machinery was replaced by the `formats` package. The passes are unchanged
(resolve_vars_to_hex / strip_animation / clamp_width); the flatten assertions
and the byte-stability check (now an svg-identity check) are preserved.
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec
from hyperweave.formats import FormatId, project
from hyperweave.formats.static import clamp_width, resolve_vars_to_hex, run_passes, strip_animation


def _static(genome: str, variant: str, state: str = "active") -> str:
    spec = ComposeSpec(type="badge", genome_id=genome, variant=variant, title="BUILD", value=state, state=state)
    return project(compose(spec).svg, FormatId.SVG_STATIC).data.decode("utf-8")


@pytest.mark.parametrize(
    "genome,variant,state",
    [
        ("primer", "porcelain", "passing"),
        ("chrome", "horizon", "failing"),
        ("automata", "teal", "active"),
        ("brutalist", "", "warning"),
    ],
)
def test_static_has_no_css_vars_and_real_hex(genome: str, variant: str, state: str) -> None:
    svg = _static(genome, variant, state)
    assert "var(--" not in svg, "all custom properties must flatten in svg-static"
    assert 'fill=""' not in svg, "a flattened var must never collapse to an empty paint"
    assert re.search(r'fill="#[0-9A-Fa-f]{6}"', svg), "real hex paints must land"


def test_svg_format_is_identity() -> None:
    """The `svg` format keeps CSS vars — byte-identical to the composed artifact."""
    svg = compose(ComposeSpec(type="badge", genome_id="primer", title="X", value="Y")).svg
    projected = project(svg, FormatId.SVG).data.decode("utf-8")
    assert projected == svg
    assert "var(--dna" in projected  # web keeps CSS vars — unchanged from today


def test_strip_animation_removes_motion() -> None:
    svg = "<svg><style>@keyframes a{0%{opacity:0}}.x{animation:a 1s}</style>"
    svg += '<rect><animate attributeName="opacity" values="0;1"/></rect>'
    svg += '<circle><animateTransform attributeName="transform"/></circle></svg>'
    out = strip_animation(svg)
    assert "<animate" not in out
    assert "@keyframes" not in out
    assert "animation:" not in out


def test_run_passes_empty_is_identity() -> None:
    svg = "<svg>var(--dna-x)</svg>"
    assert run_passes(svg, []) == svg  # no passes → no-op


def test_resolve_vars_falls_back_never_empty() -> None:
    # an undeclared var with no fallback resolves to ink, never to empty
    svg = '<svg><style>:root{--dna-ink-primary:#123456}</style><rect fill="var(--dna-unknown)"/></svg>'
    out = resolve_vars_to_hex(svg)
    assert 'fill="#123456"' in out
    assert "var(--" not in out


def test_clamp_width_caps_only_over_max() -> None:
    assert 'width="800"' in clamp_width('<svg width="1200" viewBox="0 0 1200 40">', 800)
    assert 'width="400"' in clamp_width('<svg width="400" viewBox="0 0 400 40">', 800)


def test_static_rasterizes_in_resvg_and_differs_from_live() -> None:
    """The var()→hex flatten produces real pixels in resvg — a non-browser
    rasterizer (the flatten law's target environment) — deterministically, and the
    static projection differs from the live var()-based SVG. Guards against the
    flatten passing the corpus but breaking actual off-browser pixels."""
    from hyperweave.formats import raster

    if not raster.available():
        pytest.skip("raster extra not installed")

    base = dict(type="badge", genome_id="primer", variant="porcelain", title="STARS", value="1.2k", state="passing")
    live_svg = compose(ComposeSpec(**base)).svg  # type: ignore[arg-type]
    static_svg = project(live_svg, FormatId.SVG_STATIC).data.decode("utf-8")
    assert "var(--" not in static_svg

    png = project(live_svg, FormatId.PNG).data
    assert len(png) > 1000  # rendered real content, not an empty/error image
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # valid PNG signature
