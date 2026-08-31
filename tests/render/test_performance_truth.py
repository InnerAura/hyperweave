"""The performance/cim claims must equal the rendered document's truth.

The drift guard behind ``data/config/performance.yaml``: every case composes
through the real engine, extracts the animated property names actually present
in the final document (``render.css_finish.rendered_animated_properties``),
derives the honest tier from the compositor law, and asserts the artifact's
own ``performance=`` / ``cim-compliant=`` claims agree. Change a template's
animation and this matrix fails until the table (and therefore the claim)
follows — the claim can never be static again.
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_performance_config
from hyperweave.core.enums import FrameType
from hyperweave.core.models import ComposeSpec
from hyperweave.render.css_finish import rendered_animated_properties

# The svg-invariants builders already enroll every frame x genome x
# opposite-substrate variant with valid offline IR — reuse them so the truth
# matrix and the hostile-label sweep can never cover different corpora. (The
# hostile labels are irrelevant here: text never animates.)
from tests.compose.test_svg_invariants import _genome_cases, _hostile_spec

_PERFORMANCE_ATTR = re.compile(r'performance="([^"]*)"')
_CIM_ATTR = re.compile(r'cim-compliant="([^"]*)"')


def _claimed_tier(svg: str) -> str:
    match = _PERFORMANCE_ATTR.search(svg)
    assert match, "artifact emits no performance claim"
    return match.group(1)


def _honest_tier(svg: str) -> str:
    compositor = set(load_performance_config()["compositor_properties"])
    return "paint-ok" if rendered_animated_properties(svg) - compositor else "composite-only"


def _assert_claims_match(svg: str, where: str) -> None:
    claimed = _claimed_tier(svg)
    honest = _honest_tier(svg)
    animated = sorted(rendered_animated_properties(svg))
    assert claimed == honest, f"{where}: claims {claimed} but renders {honest} (animates {animated})"
    cim = _CIM_ATTR.search(svg)
    if cim:
        assert (cim.group(1) == "true") == (claimed == "composite-only"), (
            f"{where}: cim-compliant={cim.group(1)!r} disagrees with tier {claimed!r}"
        )


def _matrix_cases() -> list[tuple[str, str, str]]:
    return [(frame.value, genome, variant) for frame in FrameType for genome, variant in _genome_cases(frame.value)]


def _case_spec(frame: str, genome: str, variant: str) -> ComposeSpec:
    """The invariant-sweep builder, extended for the two frames it skips
    (icon and divider take no user text, so the hostile sweep has no case)."""
    if frame in ("icon", "divider"):
        kwargs: dict[str, str] = {"variant": variant} if variant else {}
        return ComposeSpec(type=frame, genome_id=genome, **kwargs)
    return _hostile_spec(frame, genome, variant)


@pytest.mark.parametrize(("frame", "genome", "variant"), _matrix_cases())
def test_claimed_tier_matches_rendered_animation(frame: str, genome: str, variant: str) -> None:
    """Every frame x genome x substrate-variant branch tells the truth."""
    svg = compose(_case_spec(frame, genome, variant)).svg
    _assert_claims_match(svg, f"{frame}/{genome}/{variant or 'default'}")


_DIVIDER_CASES = [
    ("block", "primer"),
    ("current", "primer"),
    ("takeoff", "primer"),
    ("void", "primer"),
    ("zeropoint", "primer"),
    ("band", "chrome"),
    ("seam", "brutalist"),
    ("sigil", "brutalist"),
    ("aura", "primer"),
]


@pytest.mark.parametrize(("slug", "genome"), _DIVIDER_CASES)
def test_divider_variant_tiers_match_reality(slug: str, genome: str) -> None:
    """Every divider template branch — editorial generics and genome-themed
    slugs — claims what it renders (divider dispatches by variant, not
    paradigm, so it carries its own tier_key)."""
    svg = compose(ComposeSpec(type="divider", genome_id=genome, divider_variant=slug)).svg
    _assert_claims_match(svg, f"divider/{slug}/{genome}")


_BORDER_MOTIONS = ["chromatic-pulse", "corner-trace", "dual-orbit", "entanglement", "rimrun"]


@pytest.mark.parametrize("frame", ["badge", "strip", "icon"])
@pytest.mark.parametrize("motion", _BORDER_MOTIONS)
def test_border_motion_tiers_match_reality(frame: str, motion: str) -> None:
    """Request-selected border motions animate Paint-stage properties (their
    motions/*.yaml declare so) — the claim must follow. regime=permissive so
    the NORMAL-lane downgrade (routed to the lanes overhaul) can't mask the
    claim under test."""
    svg = compose(
        ComposeSpec(type=frame, genome_id="brutalist", title="X", value="1", motion=motion, regime="permissive")
    ).svg
    _assert_claims_match(svg, f"{frame}/brutalist/motion={motion}")


def test_baked_animation_table_has_no_orphans() -> None:
    """Every performance.yaml key resolves to a live dispatch target: a
    paradigm YAML for frame.paradigm keys, a template or editorial variant for
    divider keys. A key naming a retired branch fails loud."""
    import pathlib

    import hyperweave

    data = pathlib.Path(hyperweave.__file__).parent / "data"
    editorial = {"block", "current", "takeoff", "void", "zeropoint", "dissolve"}
    frames = {f.value for f in FrameType}
    for key in load_performance_config()["baked_animations"]:
        frame, _, slug = key.partition(".")
        assert frame in frames, f"{key}: unknown frame {frame!r}"
        if frame == "divider":
            template = data.parent / "templates" / "frames" / "divider" / f"{slug}.svg.j2"
            assert slug in editorial or template.exists(), f"{key}: no divider branch behind {slug!r}"
        else:
            assert (data / "paradigms" / f"{slug}.yaml").exists(), f"{key}: no paradigm YAML for {slug!r}"


def test_cli_written_chart_claims_paint_ok(tmp_path: object) -> None:
    """The artifact a CLI user actually receives carries the derived claim."""
    import json as _json
    from pathlib import Path

    from typer.testing import CliRunner

    from hyperweave.cli import app

    out = Path(str(tmp_path)) / "b.svg"
    result = CliRunner().invoke(app, ["compose", "badge", "X", "1", "-g", "chrome", "-o", str(out)])
    assert result.exit_code == 0, result.output
    svg = out.read_text()
    assert 'performance="paint-ok"' in svg, _json.dumps(sorted(rendered_animated_properties(svg)))
    _assert_claims_match(svg, "cli/badge/chrome")
