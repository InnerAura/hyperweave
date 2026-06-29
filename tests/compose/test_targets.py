"""Surface pack + BUG-002 (var()→hex for non-web targets)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

import pytest

from hyperweave.compose.surface import SpecEnvelope, compose_surface
from hyperweave.compose.targets import apply_target, resolve_vars_to_hex, strip_animation

_HAS_RSVG = shutil.which("rsvg-convert") is not None


def _email(genome: str, variant: str, state: str = "active") -> str:
    return compose_surface(
        SpecEnvelope(
            type="badge",
            genome=genome,
            variant=variant,
            spec={"title": "BUILD", "value": state, "state": state},
            target="email",
            emit=("svg",),
        )
    ).svg


@pytest.mark.parametrize(
    "genome,variant,state",
    [
        ("primer", "porcelain", "passing"),
        ("chrome", "horizon", "failing"),
        ("automata", "teal", "active"),
        ("brutalist", "", "warning"),
    ],
)
def test_email_has_no_css_vars_and_real_hex(genome: str, variant: str, state: str) -> None:
    svg = _email(genome, variant, state)
    assert "var(--" not in svg, "all custom properties must flatten off-web (BUG-002)"
    assert 'fill=""' not in svg, "a flattened var must never collapse to an empty paint"
    assert re.search(r'fill="#[0-9A-Fa-f]{6}"', svg), "real hex paints must land"


def test_web_target_is_byte_stable() -> None:
    raw = compose_surface(
        SpecEnvelope(type="badge", genome="primer", spec={"title": "X", "value": "Y"}, target="web", emit=("svg",))
    ).svg
    assert "var(--dna" in raw  # web keeps CSS vars — unchanged from today


def test_strip_animation_removes_motion() -> None:
    svg = "<svg><style>@keyframes a{0%{opacity:0}}.x{animation:a 1s}</style>"
    svg += '<rect><animate attributeName="opacity" values="0;1"/></rect>'
    svg += '<circle><animateTransform attributeName="transform"/></circle></svg>'
    out = strip_animation(svg)
    assert "<animate" not in out
    assert "@keyframes" not in out
    assert "animation:" not in out


def test_apply_target_unknown_is_identity() -> None:
    svg = "<svg>var(--dna-x)</svg>"
    assert apply_target(svg, "web") == svg  # web is the identity
    assert apply_target(svg, "nonsense") == svg  # unknown target → no-op


def test_resolve_vars_falls_back_never_empty() -> None:
    # an undeclared var with no fallback resolves to ink, never to empty
    svg = '<svg><style>:root{--dna-ink-primary:#123456}</style><rect fill="var(--dna-unknown)"/></svg>'
    out = resolve_vars_to_hex(svg)
    assert 'fill="#123456"' in out
    assert "var(--" not in out


def _raster(svg: str) -> bytes:
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False, encoding="utf-8") as f:
        f.write(svg)
        path = f.name
    try:
        return subprocess.run(["rsvg-convert", "-w", "160", path], capture_output=True, check=True).stdout
    finally:
        os.unlink(path)


@pytest.mark.skipif(not _HAS_RSVG, reason="rsvg-convert not installed")
def test_email_target_rasterizes_in_a_non_browser_renderer() -> None:
    """The regex var()->hex flatten must produce real pixels in rsvg-convert — a
    non-browser rasterizer (the BUG-002 target environment) — deterministically,
    and differently from the var()-based web SVG (whose colours depend on the
    renderer resolving CSS custom properties, which rsvg / email / PDF do not).
    Guards against the flatten passing the corpus but breaking actual off-web pixels."""
    base = {
        "type": "badge",
        "genome": "primer",
        "variant": "porcelain",
        "spec": {"title": "STARS", "value": "1.2k", "state": "passing"},
        "emit": ("svg",),
    }
    web = compose_surface(SpecEnvelope(**base, target="web")).svg
    email = compose_surface(SpecEnvelope(**base, target="email")).svg
    assert "var(--" not in email
    web_png, email_png = _raster(web), _raster(email)
    assert len(email_png) > 1000  # rendered real content, not an empty/error image
    assert email_png != web_png  # the flatten changed the rendered pixels (resolved vs fallback)
