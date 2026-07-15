"""Strip layout invariance pins (v0.3.9 additive layout).

Three behaviors locked here:

1. **Height invariance under metric-count variation.** Both brutalist and
   chrome strip canvases must stay 52px tall regardless of metric count.
   Width grows with content (additive slot assembly); height does not.
   Pre-v0.3.9, my first-pass redistribution stretched cells to fill a
   pinned canvas, producing 350px cells for n=1 with text floating in
   the center. The additive layout sizes each cell to its content + pad,
   leaving no dead space inside cells or between cells and the bookend.

2. **Cell positions follow additive assembly.** Cell n+1's x-coordinate
   equals cell n's x plus cell n's content-width. No reshuffling, no
   redistribution. v0.3.13: brutalist cells size to content (max(label,value)
   measured + 2*strip_pad) with a small cell_min_width floor (44) — short
   metrics no longer inflate to the retired 100px stride. Chrome keeps its
   own cell_min_width.

3. **State-indicator gating on per-metric STATEFUL_TITLES presence.**
   Data-only strips (STARS, FORKS, ISSUES, PRS, DOWNLOADS, VERSION)
   render without the ``<g data-hw-zone="status">`` element. Strips
   containing at least one state-bearing title (BUILD, CI, COVERAGE,
   STATUS, HEALTH, etc.) render the indicator. Per-metric inference
   rolls up via ``compose/layout.py:decide_strip_mode``.
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec
from hyperweave.core.text import measure_text

# Brutalist strip identity renders in Barlow Condensed 11/900/0.18em
# (brutalist-defs.j2 `.brand-text`). Measurement helper mirrors render truth.
_BRAND = {"font_family": "Barlow Condensed", "font_size": 11, "font_weight": 900, "letter_spacing_em": 0.18}

_VIEWBOX_RE = re.compile(r'viewBox="0 0 (\d+) (\d+)"')
_CELL_POS_RE = re.compile(r'data-hw-zone="metric-(\d+)" transform="translate\((\d+),')
_GLYPH_RE = re.compile(
    r'data-hw-zone="glyph" transform="translate\(([\d.]+),([\d.]+)\)">\s*'
    r'<svg x="-?[\d.]+"\s+y="-?[\d.]+"\s+width="([\d.]+)"\s+height="([\d.]+)"',
    re.S,
)
_IDENTITY_X_RE = re.compile(r'<text data-hw-zone="identity" x="([\d.]+)"')


def _render_strip(genome: str, metrics: list[str]) -> str:
    spec = ComposeSpec(
        type="strip",
        genome_id=genome,
        title="eli64s/readme-ai",
        value=",".join(metrics),
    )
    return compose(spec).svg


def _viewbox(svg: str) -> tuple[int, int]:
    m = _VIEWBOX_RE.search(svg)
    assert m, f"no viewBox found in:\n{svg[:300]}"
    return int(m.group(1)), int(m.group(2))


def _has_status_indicator(svg: str) -> bool:
    return '<g data-hw-zone="status"' in svg


METRIC_POOL = ["STARS:2.9k", "FORKS:278", "ISSUES:14", "PRS:7"]


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_brutalist_height_invariant(n: int) -> None:
    """Brutalist strip height MUST stay 52px at any metric count.

    Width adapts to content (additive); height does not.
    """
    svg = _render_strip("brutalist", METRIC_POOL[:n])
    _, height = _viewbox(svg)
    assert height == 52, f"brutalist n={n}: height drifted from 52"


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_chrome_height_invariant(n: int) -> None:
    """Chrome strip height MUST stay 52px at any metric count.

    Width adapts to content; height does not.
    """
    svg = _render_strip("chrome", METRIC_POOL[:n])
    _, height = _viewbox(svg)
    assert height == 52, f"chrome n={n}: height drifted from 52"


def test_brutalist_width_grows_with_metric_count() -> None:
    """Brutalist canvas WIDTH grows monotonically as metrics are added.

    Pre-v0.3.9 additive rewrite: cells were stretched to fill a pinned
    560 canvas, producing identical widths for any n (and elongated
    cells for low n). Post-rewrite: each cell adds its content-width,
    so n=1 < n=2 < n=3 < n=4.
    """
    widths = [_viewbox(_render_strip("brutalist", METRIC_POOL[:n]))[0] for n in (1, 2, 3, 4)]
    assert widths == sorted(widths) and len(set(widths)) == 4, (
        f"brutalist widths {widths} should grow strictly monotonically with n"
    )


def test_chrome_width_grows_with_metric_count() -> None:
    """Chrome canvas WIDTH grows monotonically as metrics are added."""
    widths = [_viewbox(_render_strip("chrome", METRIC_POOL[:n]))[0] for n in (1, 2, 3, 4)]
    assert widths == sorted(widths) and len(set(widths)) == 4, (
        f"chrome widths {widths} should grow strictly monotonically with n"
    )


def test_brutalist_cells_size_to_content() -> None:
    """v0.3.13: brutalist metric cells size to their OWN content
    (max(label, value) measured + 2*strip_pad), not a fixed stride. Each cell
    advances by the prior cell's measured width, so cells with different content
    render at different widths. Pre-v0.3.13 every cell was floored to
    cell_min_width=100, inflating short metrics with dead space (the bug).
    """
    # Asymmetric metrics: a wide cell (DOWNLOADS/1.2M) and narrow ones (PRS/7).
    svg = _render_strip("brutalist", ["DOWNLOADS:1.2M", "PRS:7", "ISSUES:14"])
    xs = [int(x) for _i, x in sorted((int(i), int(x)) for i, x in _CELL_POS_RE.findall(svg))]
    assert len(xs) == 3, f"expected 3 metric cells, got {xs}"
    widths = [xs[1] - xs[0], xs[2] - xs[1]]
    # Content-aware: the DOWNLOADS cell (wide label) is strictly wider than the
    # PRS cell (narrow). Equal widths would mean the old fixed-stride floor.
    assert widths[0] > widths[1], f"DOWNLOADS cell must exceed PRS cell (content-sized): widths={widths}"
    # No cell is inflated to the retired 100px floor for these short metrics.
    assert all(w < 100 for w in widths), f"cells should not hit the old 100px floor: {widths}"


@pytest.mark.parametrize(
    "metrics,expected,case",
    [
        (["STARS:373k", "FORKS:12k", "ISSUES:234"], False, "data-only (3)"),
        (["STARS:2.9k", "FORKS:278", "ISSUES:14", "PRS:7"], False, "data-only (4)"),
        (["VERSION:v0.3.9", "DOWNLOADS:1.2M"], False, "data-only (version + downloads)"),
        (["BUILD:passing", "STARS:2.9k"], True, "state + data"),
        (["BUILD:failing"], True, "state-only"),
        (["COVERAGE:94"], True, "coverage-only"),
    ],
)
def test_brutalist_state_indicator_gates_on_stateful_titles(metrics: list[str], expected: bool, case: str) -> None:
    """Brutalist state indicator renders ONLY when at least one metric
    title is in ``data/config/badge-modes.yaml`` (STATEFUL_TITLES set).

    Per-metric inference via ``compose/layout.py:decide_strip_mode``;
    no per-strip "force-indicator" override. Data-only strips (high-
    star repos like openclaw 373k, n8n 189k) must render without the
    indicator — the indicator is exclusively for state metrics
    (build/ci/coverage/health), not for data magnitude.
    """
    svg = _render_strip("brutalist", metrics)
    assert _has_status_indicator(svg) is expected, f"brutalist {case}: indicator presence != {expected}"


@pytest.mark.parametrize(
    "metrics,expected,case",
    [
        (["STARS:373k", "FORKS:12k", "ISSUES:234"], False, "data-only"),
        (["BUILD:passing", "STARS:2.9k"], True, "state + data"),
    ],
)
def test_chrome_state_indicator_gates_on_stateful_titles(metrics: list[str], expected: bool, case: str) -> None:
    """Chrome strip honors the same state-indicator gate as brutalist.

    The gate lives in ``compose/resolver.py:resolve_strip`` and
    ``compose/layout.py:decide_strip_mode`` — paradigm-agnostic.
    """
    svg = _render_strip("chrome", metrics)
    assert _has_status_indicator(svg) is expected, f"chrome {case}: indicator presence != {expected}"


# ─────────────────────────────────────────────────────────────────────
# Identity overflow shrink-to-fit + chrome min-width
# ─────────────────────────────────────────────────────────────────────

_IDENTITY_TEXTLENGTH_RE = re.compile(r'data-hw-zone="identity"[^>]*textLength="([\d.]+)"')


def test_brutalist_long_identity_emits_natural_textlength() -> None:
    """v0.3.13: a long identity emits textLength = its NATURAL measured width
    (Barlow Condensed render font) and the panel GROWS to fit — no squish into
    a smaller box. textLength is a no-op when the embedded font loads and a
    font-independent bound when it can't (camo blocks @font-face), so
    "SIGNIFICANT-GRAVITAS/AUTOGPT" is bounded to its true width, never bled or
    stretched. (Replaces the v0.3.2 shrink-to-fit-into-156-ceiling behavior.)
    """
    title = "SIGNIFICANT-GRAVITAS/AUTOGPT"
    spec = ComposeSpec(
        type="strip",
        genome_id="brutalist",
        title=title,
        value="STARS:184k,FORKS:46k,ISSUES:428,PRS:42",
    )
    svg = compose(spec).svg
    m = _IDENTITY_TEXTLENGTH_RE.search(svg)
    assert m is not None, "brutalist identity MUST emit a measured textLength bound"
    natural = round(measure_text(title.upper(), **_BRAND), 1)
    assert abs(float(m.group(1)) - natural) < 0.2, (
        f"identity textLength={m.group(1)} must equal the NATURAL measured width "
        f"{natural} (panel grows to fit — no squish)."
    )
    assert 'lengthAdjust="spacingAndGlyphs"' in svg, (
        "lengthAdjust='spacingAndGlyphs' MUST accompany textLength for cross-renderer consistency."
    )


def test_brutalist_short_identity_emits_natural_textlength() -> None:
    """v0.3.13: short identities ALSO emit textLength = their natural measured
    width — the camo font-independent bound. This inverts the pre-v0.3.13 rule
    (no textLength for short identities): a textLength equal to the natural
    width is a no-op when the font loads (zero distortion) and prevents
    fallback-font bleed in the README, where camo's CSP blocks the embedded
    @font-face."""
    title = "hyperweave"
    spec = ComposeSpec(type="strip", genome_id="brutalist", title=title, value="STARS:15")
    svg = compose(spec).svg
    m = _IDENTITY_TEXTLENGTH_RE.search(svg)
    assert m is not None, "v0.3.13: every brutalist identity emits a measured textLength bound"
    natural = round(measure_text(title.upper(), **_BRAND), 1)
    assert abs(float(m.group(1)) - natural) < 0.2, (
        f"short identity textLength={m.group(1)} must equal natural width {natural} (no distortion)"
    )


def test_chrome_strip_glyph_identity_gap_is_rendered_from_zone_geometry() -> None:
    """Chrome glyph and identity text render with the computed 9px gap."""
    spec = ComposeSpec(
        type="strip",
        genome_id="chrome",
        title="eli64s/readme-ai",
        value="STARS:2.9k,FORKS:278",
        glyph="github",
    )
    svg = compose(spec).svg
    glyph = _GLYPH_RE.search(svg)
    identity = _IDENTITY_X_RE.search(svg)
    assert glyph is not None
    assert identity is not None
    glyph_cx = float(glyph.group(1))
    glyph_w = float(glyph.group(3))
    identity_x = float(identity.group(1))
    assert identity_x == glyph_cx + glyph_w / 2 + 9


@pytest.mark.parametrize("n", [1, 2, 3])
def test_chrome_strip_clamps_to_min_width(n: int) -> None:
    """chrome.yaml declares ``strip_min_width: 320`` so 1-metric
    chrome strips don't aspect-warp in README columns. The clamp applies to
    the natural width when below 320; wider strips pass through unchanged."""
    svg = _render_strip("chrome", METRIC_POOL[:n])
    width, _ = _viewbox(svg)
    assert width >= 320, f"chrome n={n}: width={width} below strip_min_width=320"


def test_brutalist_strip_unaffected_by_chrome_min_width() -> None:
    """The strip_min_width clamp is paradigm-scoped (chrome.yaml only).
    Brutalist strips compute their own minimum via the owns_strip bookend
    grammar — they should not adopt chrome's 320 floor."""
    svg = _render_strip("brutalist", METRIC_POOL[:1])
    width, _ = _viewbox(svg)
    # Brutalist 1-metric natural width: brand_divider_x 170 + cell_min_width 100
    # + bookend_gap 16 + bookend_pad_right 40 = ~326. Independent of chrome's clamp.
    # Test only confirms brutalist isn't being force-clamped to 320 by a stray
    # paradigm cross-leak.
    assert width != 320, (
        f"brutalist width={width} suspiciously matches chrome strip_min_width "
        "— possible paradigm config cross-contamination"
    )
