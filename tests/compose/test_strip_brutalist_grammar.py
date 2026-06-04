"""Brutalist strip grammar (v0.3.2 Phase C, updated v0.3.9 additive).

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
3. Brutalist strip canvas WIDTH adapts to metric content AND identity
   content (v0.3.13 content-aware retune): the brand panel GROWS to fit the
   measured identity (no ceiling); triple_divider_x and brand_divider_x follow
   the panel right edge; cells size to content (max(label,value)+2*strip_pad,
   small cell_min_width=44 floor — no fixed 100px stride). A glyphless strip
   defaults to the HyperWeave sigil in the identity zone; a STATELESS strip
   (v0.3.13, dark) renders no decorative bookend and ends at cells_end +
   strip_pad (16). HEIGHT stays pinned at 52. For the 3-metric STATELESS
   reference render (title=HYPERWEAVE, Barlow Condensed 73.6px): brand_panel_w
   =134, triple_divider_x=140, brand_divider_x=148, cells end at 338, canvas
   340x52 (last cell + stateless trailing 2). (Measured in Barlow Condensed —
   the `.brand-text` render font.)
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
    """Brutalist celadon strip brand panel GROWS to fit identity content.

    For title='HYPERWEAVE' (73.6px in Barlow Condensed): brand_panel_w =
    ceil(identity_left_inset 44 + 73.6 + strip_pad 16) = 134. The panel has no
    ceiling (v0.3.13) — it grows for longer identities and shrinks for shorter,
    always sized to the measured render-font width.
    """
    body = _render("brutalist", "celadon")
    assert re.search(
        r'<rect\s+x="6"\s+y="0"\s+width="134"\s+height="52"\s+fill="var\(--dna-brand-panel-fill\)"',
        body,
    ), "brutalist HYPERWEAVE strip must render content-driven brand panel at x=6 width=134"


def test_brutalist_triple_divider(monkeypatch: pytest.MonkeyPatch) -> None:
    """ACCENT-VOID-ACCENT triple divider follows the content-driven brand panel
    right edge (x=140 for HYPERWEAVE: brand_panel_x 6 + brand_panel_w 134).
    Width 3px + 2px + 3px = 8px total triple-divider span.
    """
    body = _render("brutalist", "celadon")
    assert re.search(r'<rect\s+x="140"\s+y="0"\s+width="3"', body), "missing left accent bar of triple divider"
    assert re.search(r'<rect\s+x="143"\s+y="0"\s+width="2"', body), "missing center void of triple divider"
    assert re.search(r'<rect\s+x="145"\s+y="0"\s+width="3"', body), "missing right accent bar of triple divider"


def test_brutalist_default_glyph_and_stateless_terminus(monkeypatch: pytest.MonkeyPatch) -> None:
    """v0.3.13: a glyphless brutalist strip defaults to the HyperWeave
    sigil in the identity zone (not a fallback ornament square), and a
    STATELESS strip (STARS/FORKS/ISSUES — none allowlisted) renders NO
    right-side terminus: the operational-status slot is empty, so the strip
    ends at the last cell + pad rather than a decorative bookend square.
    """
    body = _render("brutalist", "celadon")
    # Glyphless → HyperWeave sigil fills the identity zone.
    assert 'data-hw-zone="brand-glyph"' in body, "glyphless strip must default to the HyperWeave sigil"
    assert "M12 0 C15 3 21 9 24 12" in body, "default identity glyph must be the HyperWeave sigil path"
    # No retired fallback ornament square at the old (22,19) identity slot.
    assert not re.search(r'<rect\s+x="22"\s+y="19"\s+width="14"\s+height="14"', body), (
        "default-sigil strip must NOT render the retired identity ornament square"
    )
    # Stateless → no decorative bookend AND no status indicator.
    assert "translate(354,26)" not in body, "stateless strip must NOT render a decorative bookend"
    assert 'data-hw-zone="status"' not in body, "stateless strip must NOT render a status indicator"


def test_brutalist_canvas_height_invariant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip height pinned at 52 regardless of metric count (additive layout)."""
    body = _render("brutalist", "celadon")
    assert re.search(r'viewBox="0\s+0\s+\d+\s+52"', body), "brutalist strip canvas height must stay 52"


def test_brutalist_canvas_width_additive(monkeypatch: pytest.MonkeyPatch) -> None:
    """3-metric STATELESS brutalist strip is 340 wide (v0.3.13, dark default).

    Width = brand_divider_x 148 + content cells (64+60+66=190) + stateless
    trailing 2 = 340. The stateless strip ends a thin stroke clearance past the
    last cell (no decorative ornament), so the last value's right margin mirrors
    its left — the cell's own pad supplies the margin, not a full strip_pad of
    trailing. HEIGHT stays 52.
    """
    body = _render("brutalist", "celadon")
    assert re.search(r'viewBox="0\s+0\s+340\s+52"', body), (
        "brutalist 3-metric stateless strip canvas must be 340x52 (symmetric trailing)"
    )


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
    # Verify INK-SEAM-INK polarity: outer bars use ink-primary, center uses seam-color.
    # Triple divider x follows content-driven brand panel (HYPERWEAVE → x=140).
    assert re.search(
        r'<rect\s+x="140"\s+y="0"\s+width="3"\s+height="52"\s+fill="var\(--dna-ink-primary\)"',
        body,
    ), "light variant triple divider outer must use --dna-ink-primary"
    assert re.search(
        r'<rect\s+x="143"\s+y="0"\s+width="2"\s+height="52"\s+fill="var\(--dna-seam-color\)"',
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
