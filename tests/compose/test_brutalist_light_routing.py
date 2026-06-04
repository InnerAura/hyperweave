"""v0.3.13 brutalist light-variant color routing + strip glyph/parity pins.

The 6 brutalist light scholars route color by THREE roles (not two):
  INK    (--dna-ink-primary / --dna-bg)  structure, values, label pills
  GROUND (--dna-surface)                 backgrounds, knockouts
  ACCENT (--dna-signal)                  data-viz, labels-on-cream, spots

These pins lock the light-routing revision: activity bars + chart data line + strip
metric labels are ACCENT; hero/activity labels are ink pills; the strip
identity defaults to the HyperWeave sigil and emits a camo-bound textLength on
every genome; chrome strip cells size to content (not the legacy 106 floor).
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

LIGHT_VARIANTS = ["archive", "signal", "pulse", "depth", "afterimage", "primer"]

MOCK_STATS = {
    "username": "eli64s",
    "stars_total": 12847,
    "commits_total": 1203,
    "prs_total": 89,
    "issues_total": 47,
    "streak_days": 47,
    "top_language": "Python",
    "language_breakdown": [{"name": "Python", "pct": 68.5}, {"name": "TypeScript", "pct": 18.1}],
    "heatmap_grid": [{"date": f"2025-01-{(i % 28) + 1:02d}", "count": (i % 12) + 1} for i in range(364)],
}

MOCK_CHART = {
    "current_stars": 2962,
    "identity": "myorg/myrepo",
    "series_points": [{"date": f"2024-{(i // 5) % 12 + 1:02d}-15", "count": 100 + i * 40} for i in range(20)],
}


def _strip(genome: str, variant: str = "", *, title: str = "repo", value: str = "STARS:2.9k", glyph: str = "") -> str:
    return compose(
        ComposeSpec(type="strip", genome_id=genome, variant=variant, title=title, value=value, glyph=glyph)
    ).svg


def _stats(variant: str) -> str:
    return compose(
        ComposeSpec(
            type="stats", genome_id="brutalist", variant=variant, stats_username="eli64s", connector_data=MOCK_STATS
        )
    ).svg


def _chart(variant: str) -> str:
    return compose(
        ComposeSpec(
            type="chart",
            genome_id="brutalist",
            variant=variant,
            chart_owner="myorg",
            chart_repo="myrepo",
            connector_data=MOCK_CHART,
        )
    ).svg


# ── Strip metric labels: accent on light, label-text on dark ──


@pytest.mark.parametrize("variant", LIGHT_VARIANTS)
def test_strip_light_metric_label_is_accent(variant: str) -> None:
    """Light strip metric LABELS carry --dna-signal (accent-as-label); values stay ink."""
    svg = _strip("brutalist", variant, value="STARS:2.9k,FORKS:278")
    m = re.search(r"-metric-label \{[^}]*?fill:\s*([^;]+);", svg, re.S)
    assert m and m.group(1).strip() == "var(--dna-signal)", (
        f"{variant}: strip metric-label must be --dna-signal, got {m.group(1) if m else None}"
    )


def test_strip_dark_metric_label_is_label_text() -> None:
    """Dark strip metric labels stay --dna-label-text (celadon byte-equality preserved)."""
    svg = _strip("brutalist", "celadon", value="STARS:2.9k,FORKS:278")
    m = re.search(r"-metric-label \{[^}]*?fill:\s*([^;]+);", svg, re.S)
    assert m and m.group(1).strip() == "var(--dna-label-text)"


# ── Strip default glyph chain ──


@pytest.mark.parametrize("genome", ["brutalist", "chrome", "automata"])
def test_strip_defaults_to_hyperweave_sigil(genome: str) -> None:
    """No explicit glyph + no provider → the HyperWeave sigil fills the identity zone."""
    svg = _strip(genome, value="STARS:2.9k")
    assert "M12 0 C15 3 21 9 24 12" in svg, f"{genome}: glyphless strip must default to the HyperWeave sigil"


@pytest.mark.parametrize("genome", ["brutalist", "chrome", "automata"])
def test_strip_glyph_none_suppresses(genome: str) -> None:
    """``--glyph none`` suppresses the glyph entirely (no sigil, no glyph zone)."""
    svg = _strip(genome, value="STARS:2.9k", glyph="none")
    assert "M12 0 C15 3 21 9 24 12" not in svg, f"{genome}: --glyph none must not render the sigil"
    assert 'data-hw-zone="brand-glyph"' not in svg and 'data-hw-zone="glyph"' not in svg, (
        f"{genome}: --glyph none must render no glyph zone"
    )


def test_strip_explicit_glyph_overrides_default() -> None:
    """An explicit ``--glyph`` wins over the sigil default."""
    svg = _strip("brutalist", value="STARS:2.9k", glyph="github")
    assert "M12 0 C15 3 21 9 24 12" not in svg, "explicit glyph must override the sigil default"


# ── Strip identity textLength parity (camo bound) across genomes ──


@pytest.mark.parametrize("genome", ["brutalist", "chrome", "automata"])
def test_strip_identity_textlength_present(genome: str) -> None:
    """Every genome's strip identity carries textLength — the camo overflow bound."""
    svg = _strip(genome, title="Significant-Gravitas/AutoGPT", value="STARS:184k,FORKS:46k,ISSUES:428,PRS:42")
    identity_chunk = svg.split('data-hw-zone="identity"')[1][:300]
    assert "textLength=" in identity_chunk and "lengthAdjust" in identity_chunk, (
        f"{genome}: strip identity must emit camo-bound textLength"
    )


def test_chrome_strip_cells_size_to_content() -> None:
    """Chrome's long-namespace 4-metric strip sizes closer to content
    (cell_min_width 88, not the legacy 106 floor): viewBox width stays clearly
    under the old 745px inflation while keeping Orbitron's breathing room."""
    svg = _strip("chrome", title="Significant-Gravitas/AutoGPT", value="STARS:184k,FORKS:46k,ISSUES:428,PRS:42")
    w = float(re.search(r'viewBox="0 0 ([\d.]+)', svg).group(1))
    assert w < 700, f"chrome long-namespace strip should size toward content (<700px, was 745 at 106), got {w}"


# ── Stats hero + activity ink pills (light) ──


@pytest.mark.parametrize("variant", LIGHT_VARIANTS)
def test_stats_light_hero_label_is_ink_pill(variant: str) -> None:
    """Light stats hero label = cream (.hl=brand-text) text inside an ink-primary
    rect; the ACTIVITY band label gets the same treatment (two measured pills at
    x=19). v0.3.13 4-role: the knockout cream is --dna-brand-text, not the ground
    --dna-surface."""
    svg = _stats(variant)
    assert re.search(r"-hl \{[^}]*?fill:\s*var\(--dna-brand-text\)", svg, re.S), (
        f"{variant}: hero label text must be --dna-brand-text (cream knockout on the ink pill)"
    )
    pills = re.findall(r'<rect x="19[^>]*?fill="var\(--dna-ink-primary\)"', svg, re.S)
    assert len(pills) >= 2, f"{variant}: expected hero + activity ink pills (x=19), found {len(pills)}"


# ── Chart data line = accent on light ──


@pytest.mark.parametrize("variant", LIGHT_VARIANTS)
def test_chart_light_data_line_is_accent(variant: str) -> None:
    """Light chart routes --dna-chart-main to --dna-signal (the data polyline is accent),
    matching the stats activity bars so the two frames read as one family."""
    svg = _chart(variant)
    assert re.search(r"--dna-chart-main:\s*var\(--dna-signal\)", svg), (
        f"{variant}: chart data line (--dna-chart-main) must route to --dna-signal"
    )
