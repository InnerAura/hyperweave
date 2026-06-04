"""v0.3.13 content-aware brutalist strip layout + camo-proof textLength bound.

The brutalist strip measures every text run in its RENDER font and sizes each
zone to content + a single shared pad (``strip_pad``): the identity panel grows
to the measured width (no ceiling), metric cells size to
``max(label, value) + 2*strip_pad``, and every text run carries
``textLength`` = its measured width — a no-op when the embedded font loads, and
a font-independent BOUND when GitHub camo's CSP blocks ``@font-face`` (the
README bleed). These pins guard the foundation: if ``measure_text`` drifts, or
a zone stops tracking content, the strip silently elongates or bleeds again.
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec
from hyperweave.core.text import measure_text

# Render-truth font configs (brutalist-defs.j2 .brand-text/.metric-label/.metric-value).
_BRAND = {"font_family": "Barlow Condensed", "font_size": 11, "font_weight": 900, "letter_spacing_em": 0.18}
_LABEL = {"font_family": "JetBrains Mono", "font_size": 7, "font_weight": 800, "letter_spacing_em": 0.25}
_VALUE = {"font_family": "Barlow Condensed", "font_size": 18, "font_weight": 900, "letter_spacing_em": -0.03}


def _strip(title: str, value: str, variant: str = "celadon") -> str:
    return compose(ComposeSpec(type="strip", genome_id="brutalist", title=title, value=value, variant=variant)).svg


def _viewbox_w(svg: str) -> int:
    m = re.search(r'viewBox="0 0 (\d+) 52"', svg)
    assert m, "no 52-tall viewBox"
    return int(m.group(1))


@pytest.mark.parametrize(
    "text,cfg,expected",
    [
        ("TRANSFORMERS-V2", _BRAND, 107.0),
        ("STARS", _LABEL, 28.0),
        ("2.9k", _VALUE, 28.0),
        ("passing", _VALUE, 50.0),
    ],
)
def test_strip_measurement_fixtures(text: str, cfg: dict, expected: float) -> None:  # type: ignore[type-arg]
    """measure_text returns the render-font advances the strip geometry is built
    on. Drift here invalidates every downstream zone width (the foundation gate).
    """
    got = measure_text(text, **cfg)
    assert abs(got - expected) <= 0.5, f"{text!r}: measure {got:.2f} != {expected}±0.5"


def test_strip_panel_grows_and_shrinks_with_identity() -> None:
    """Golden: a 1-char identity yields a strictly narrower strip than a 28-char
    one (identical metrics). The panel — and the total — track the measured
    identity width, with no ceiling clamp."""
    metrics = "STARS:2.9k,FORKS:278,BUILD:passing"
    short = _viewbox_w(_strip("X", metrics))
    long = _viewbox_w(_strip("TENSORFLOW-EXTENDED-PIPELINE", metrics))
    assert short < long, f"short-identity strip ({short}) must be narrower than long ({long})"


def test_strip_long_identity_textlength_is_natural_width() -> None:
    """A long identity grows the panel to fit; its textLength equals the natural
    measured width (Barlow Condensed) — never clamped to a smaller box."""
    title = "TENSORFLOW-EXTENDED-PIPELINE"
    svg = _strip(title, "STARS:2.9k,FORKS:278,BUILD:passing").replace("\n", " ")
    m = re.search(r'data-hw-zone="identity"[^>]*textLength="([\d.]+)"', svg)
    assert m, "long identity must emit textLength"
    natural = round(measure_text(title.upper(), **_BRAND), 1)
    assert abs(float(m.group(1)) - natural) < 0.2, f"textLength {m.group(1)} != natural {natural}"


def test_strip_metric_value_textlength_matches_measure() -> None:
    """Every metric VALUE carries textLength = its measured width — the camo
    bound that keeps a fallback font from bleeding past the cell divider."""
    svg = _strip("README-AI", "STARS:2.9k,FORKS:278,BUILD:passing").replace("\n", " ")
    runs = re.findall(r'class="[^"]*-metric-value"[^>]*?textLength="([\d.]+)"[^>]*>([^<]+)<', svg)
    assert len(runs) == 3, f"all 3 metric values must carry textLength, found {len(runs)}"
    for tl, text in runs:
        natural = round(measure_text(text, **_VALUE), 1)
        assert abs(float(tl) - natural) < 0.3, f"value {text!r} textLength {tl} != measured {natural}"


def test_strip_identical_metrics_have_equal_cells() -> None:
    """Two metrics with identical content render at identical cell widths — the
    shared pad (2*strip_pad) is applied uniformly, so the inter-cell stride is
    constant for equal content."""
    svg = _strip("REPO", "STARS:2.9k,FORKS:2.9k,ISSUES:2.9k").replace("\n", " ")
    xs = [
        int(x)
        for _i, x in sorted(
            (int(i), int(x)) for i, x in re.findall(r'data-hw-zone="metric-(\d)" transform="translate\((\d+),', svg)
        )
    ]
    assert len(xs) == 3
    strides = [xs[1] - xs[0], xs[2] - xs[1]]
    assert strides[0] == strides[1], f"equal-content cells must have a constant stride: {strides}"
