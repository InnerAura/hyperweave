"""Brutalist stats card variant guardrails — activity histogram fill.

Regression coverage for the v0.3.3 brutalist-light activity-bar fix.

The 52-week activity bars in the brutalist stats card MUST use:
  - ``var(--dna-signal-dim)`` for the 6 light scholar variants (archive,
    signal, pulse, depth, afterimage, primer). The light template was
    authored to flip polarity against dark — substituting the panel-top
    accent (mapped from each variant's ``accent_complement`` JSON field)
    for the dark accent. A v0.3.2 regression hardcoded ``var(--dna-ink-primary)``
    which resolves to the deep near-black ink hex (e.g. #2A1215 on pulse),
    making the histogram read as dark-gray smudges on cream paper instead
    of the warm/cool dark accent intended by the prototype.

  - ``var(--dna-signal)`` for the 6 dark substrate variants (celadon, carbon,
    alloy, temper, pigment, ember). This guards the dark side from drifting
    into the light-only fix.

The activity histogram is rendered inside a ``<g fill="var(--dna-...)">``
parent so per-bar ``<rect>`` elements inherit the fill — the test asserts
the parent group's fill attribute references the correct CSS var.
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

# Mock connector data covering all the stats-card fields. Includes a 52-week
# heatmap so ``activity_bars`` is non-empty and the histogram group renders.
MOCK_STATS = {
    "username": "eli64s",
    "bio": "Building HyperWeave",
    "stars_total": 12847,
    "commits_total": 1203,
    "prs_total": 89,
    "issues_total": 47,
    "contrib_total": 234,
    "streak_days": 47,
    "top_language": "Python",
    "repo_count": 63,
    "language_breakdown": [
        {"name": "Python", "pct": 68.5, "count": 43},
        {"name": "TypeScript", "pct": 18.1, "count": 11},
    ],
    # 52 weeks of 7 days = 364 cells with monotonically rising counts so
    # the resolver's _build_activity_bars aggregator produces non-zero
    # weekly totals and the loop body actually emits <rect> elements.
    "heatmap_grid": [{"date": f"2025-01-{(i % 28) + 1:02d}", "count": (i % 12) + 1} for i in range(364)],
}


LIGHT_VARIANTS = ("archive", "signal", "pulse", "depth", "afterimage", "primer")
DARK_VARIANTS = ("celadon", "carbon", "alloy", "temper", "pigment", "ember")

# Regex matches the activity histogram group's opening tag. Anchors on
# the shape-rendering attribute that uniquely identifies the bars group
# in both the dark and light brutalist templates (chrome doesn't use
# crispEdges for its area chart, so this won't collide).
_ACTIVITY_GROUP_RE = re.compile(r'<g\s+fill="(var\(--dna-[a-z-]+\))"\s+shape-rendering="crispEdges">')


def _compose_stats(variant: str) -> str:
    spec = ComposeSpec(
        type="stats",
        genome_id="brutalist",
        variant=variant,
        stats_username="eli64s",
        connector_data=MOCK_STATS,
    )
    return compose(spec).svg


def _activity_group_fill(svg: str) -> str:
    match = _ACTIVITY_GROUP_RE.search(svg)
    assert match is not None, "activity histogram group not found in rendered SVG — template structure changed"
    return match.group(1)


@pytest.mark.parametrize("variant", LIGHT_VARIANTS)
def test_brutalist_light_variant_activity_bars_use_signal_dim(variant: str) -> None:
    """Each of the 6 light scholar variants must fill the 52-week activity
    histogram with ``var(--dna-signal-dim)`` so per-variant accent_complement
    (oxblood / tobacco / navy / forest / ultraviolet / zinc) reaches the bars.
    """
    svg = _compose_stats(variant)
    fill = _activity_group_fill(svg)
    assert fill == "var(--dna-signal-dim)", (
        f"brutalist-light variant {variant!r}: activity bars filled with {fill}, "
        "expected var(--dna-signal-dim) — the assembler-mapped accent_complement stop "
        "that matches each light DNA's prototype activity-bar fill"
    )


@pytest.mark.parametrize("variant", LIGHT_VARIANTS)
def test_brutalist_light_variant_activity_bars_not_ink_primary(variant: str) -> None:
    """Direct regression guard against the v0.3.2 bug: the activity histogram
    parent group must not use ``var(--dna-ink-primary)`` on any light variant.
    """
    svg = _compose_stats(variant)
    fill = _activity_group_fill(svg)
    assert fill != "var(--dna-ink-primary)", (
        f"brutalist-light variant {variant!r}: activity bars regressed to "
        "var(--dna-ink-primary) — the v0.3.2 bug that made bars read as "
        "dark-gray smudges on cream paper instead of warm/cool dark accent"
    )


@pytest.mark.parametrize("variant", DARK_VARIANTS)
def test_brutalist_dark_variant_activity_bars_use_signal(variant: str) -> None:
    """Each of the 6 dark substrate variants must fill the activity histogram
    with ``var(--dna-signal)``. Guards the dark side against the light-only
    fix drifting across the substrate boundary.
    """
    svg = _compose_stats(variant)
    fill = _activity_group_fill(svg)
    assert fill == "var(--dna-signal)", (
        f"brutalist-dark variant {variant!r}: activity bars filled with {fill}, "
        "expected var(--dna-signal) — dark variants put the accent ON the bars, "
        "light variants put accent_complement on them"
    )
