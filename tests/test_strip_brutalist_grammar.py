"""Brutalist strip grammar (v0.3.2 Phase C).

When a paradigm declares `owns_strip: true` in its YAML config, the parent
strip.svg.j2 wraps its shared zone pipeline (icon-box, glyph, identity,
metric cells, status indicator) in `{% if not paradigm_owns_strip %}` and
the paradigm content partial assumes full responsibility for body composition.

This test pins the contract on three axes:
1. Brutalist strips render the brutalist strip grammar (brand panel +
   ACCENT-VOID-ACCENT triple divider + ornament + bookend + Barlow Condensed
   metric numerals).
2. Other paradigms (chrome, cellular) leave `paradigm_owns_strip` False and
   continue rendering through the shared zone pipeline — no brand panel rect,
   no brutalist strip CSS classes, no bookend ornament.
3. Brutalist strip canvas width is forced to 560 (strip_width override)
   regardless of identity/metric content width — the bookend ornament at
   x=520 always has consistent space.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

if TYPE_CHECKING:
    import pytest


def _render(genome: str, variant: str | None = None) -> str:
    spec = ComposeSpec(
        type="strip",
        genome_id=genome,
        title="HYPERWEAVE",
        value="STARS:2898,FORKS:283,ISSUES:64",
        variant=variant or "",
    )
    return compose(spec).svg


def test_brutalist_brand_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brutalist celadon strip renders the brand panel rect at x=6 width=156."""
    body = _render("brutalist", "celadon")
    assert re.search(
        r'<rect\s+x="6"\s+y="0"\s+width="156"\s+height="52"\s+fill="var\(--dna-brand-panel-fill\)"',
        body,
    ), "brutalist strip must render brand panel rect at x=6 width=156"


def test_brutalist_triple_divider(monkeypatch: pytest.MonkeyPatch) -> None:
    """ACCENT-VOID-ACCENT triple divider at x=162 (3px+2px+3px)."""
    body = _render("brutalist", "celadon")
    assert re.search(r'<rect\s+x="162"\s+y="0"\s+width="3"', body), "missing left accent bar of triple divider"
    assert re.search(r'<rect\s+x="165"\s+y="0"\s+width="2"', body), "missing center void of triple divider"
    assert re.search(r'<rect\s+x="167"\s+y="0"\s+width="3"', body), "missing right accent bar of triple divider"


def test_brutalist_ornament_and_bookend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Identity ornament at (22,19) 14x14 + bookend at translate(520,26)."""
    body = _render("brutalist", "celadon")
    assert re.search(
        r'<rect\s+x="22"\s+y="19"\s+width="14"\s+height="14"',
        body,
    ), "brutalist strip must render identity ornament at (22,19) size 14"
    assert "translate(520,26)" in body, "brutalist strip must render bookend at x=520, y=strip_h/2=26"


def test_brutalist_canvas_width(monkeypatch: pytest.MonkeyPatch) -> None:
    """strip_width=560 overrides the adaptive width calculation."""
    body = _render("brutalist", "celadon")
    assert re.search(r'viewBox="0\s+0\s+560\s+52"', body), "brutalist strip canvas must be 560x52"


def test_brutalist_typography_classes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Metric cells use the unprefixed strip-grammar CSS classes."""
    body = _render("brutalist", "celadon")
    assert "brand-text" in body, "brutalist strip must use brand-text class on identity"
    assert "metric-label" in body, "brutalist strip must use metric-label class on metric labels"
    assert "metric-value" in body, "brutalist strip must use metric-value class on metric values"


def test_brutalist_light_substrate_inversion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Light variant uses url(#panel) gradient + INK-SEAM-INK (dark+gold+dark)."""
    body = _render("brutalist", "pulse")
    assert "url(#hw-" in body and "-panel)" in body, "brutalist light strip must reference panel gradient"
    # Verify INK-SEAM-INK polarity: outer bars use ink-primary, center uses seam-color
    assert re.search(
        r'<rect\s+x="162"\s+y="0"\s+width="3"\s+height="52"\s+fill="var\(--dna-ink-primary\)"',
        body,
    ), "light variant triple divider outer must use --dna-ink-primary"
    assert re.search(
        r'<rect\s+x="165"\s+y="0"\s+width="2"\s+height="52"\s+fill="var\(--dna-seam-color\)"',
        body,
    ), "light variant triple divider center must use --dna-seam-color"


def test_chrome_strip_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chrome paradigm leaves owns_strip at default False — no brutalist artifacts."""
    spec = ComposeSpec(
        type="strip",
        genome_id="chrome",
        title="HYPERWEAVE",
        value="STARS:2898,FORKS:283",
        variant="",  # horizon flagship
    )
    body = compose(spec).svg
    assert "dna-brand-panel-fill" not in body, "chrome strip must NOT carry brand-panel CSS var (no brutalist grammar)"
    # CSS class match for the brutalist-strip-grammar identity class. Pattern
    # matches `class="..."` references, not the `--dna-brand-text` CSS var
    # which chrome's own genome legitimately defines.
    assert not re.search(r'class="hw-[0-9a-f]+-brand-text"', body), (
        "chrome strip must NOT use the brutalist strip grammar `.brand-text` class"
    )
    # Chrome strip uses chrome-specific identity/metric classes from chrome-defs.j2 —
    # presence of metric cell zones confirms parent pipeline ran.
    assert 'data-hw-zone="metric-' in body, "chrome strip must render metric cells via parent zone pipeline"
