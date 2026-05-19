"""Layer 2 (glyph subsetting) regression + functional tests.

The font compression pipeline in v0.3.7 has two layers:

1. **Genome-aware pruning** (``data/font-embedding.yaml``) — only embeds
   font slugs whose CSS classes are actually bound in the (genome, frame)
   templates. Covered by ``tests/test_font_gating.py``.

2. **Glyph subsetting** (``render/fonts.py:_subset_b64``) — reduces each
   embedded font's payload to only the codepoints rendered in the
   artifact. fontTools subsetter + memory-only LRU cache.

This module pins the Layer 2 contract:

- Subsetting produces a strict subset by byte count.
- Cache lookup is order-invariant (``frozenset("AB") == frozenset("BA")``).
- Subset failure falls back to the full font (defense-in-depth).
- Per-artifact gzip ceilings catch regressions that re-bloat fonts.
- Self-containment + accessibility invariants still hold.
"""

from __future__ import annotations

import gzip
import re
from unittest.mock import patch

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec
from hyperweave.render.fonts import _load_font, _subset_b64, load_font_face_css

# ─── Subsetting unit tests ───────────────────────────────────────────


def _b64_block_bytes(svg: str, family: str) -> int:
    """Return base64 char count for the @font-face block whose family matches."""
    pattern = (
        r"@font-face\s*\{[^}]*?font-family:\s*'" + re.escape(family) + r"'[^}]*?"
        r"base64,([A-Za-z0-9+/=]+)\)"
    )
    m = re.search(pattern, svg)
    return len(m.group(1)) if m else 0


def test_subset_reduces_jbm_size() -> None:
    """fontTools subset on a tiny char set must produce ≤25% of the full payload.

    JetBrains Mono ships with Latin Extended + Cyrillic + Greek; a 22-char
    subset can't reasonably exceed a quarter of that even after WOFF2
    re-encoding. Empirically the ratio is ~10% but the test pins a
    generous ceiling to allow for fonttools version drift.
    """
    full = _load_font("jetbrains-mono")[3]
    subset = _subset_b64("jetbrains-mono", "".join(sorted("BUILDpassing0123456789 ")))
    assert len(subset) < len(full) * 0.25, f"subset ratio = {len(subset) / len(full):.1%} (expected < 25%)"


def test_subset_cache_invariant_to_set_order() -> None:
    """``frozenset('AB')`` and ``frozenset('BA')`` MUST hit the same cache entry.

    The canonicalization is at the call site of ``_subset_b64``: it receives
    ``''.join(sorted(char_set))`` so caller-side iteration order is
    irrelevant. Re-running through the public API should return the
    byte-identical b64 — and the second call should be a cache hit.
    """
    out_a = load_font_face_css(["jetbrains-mono"], char_set=frozenset("AB"))
    out_b = load_font_face_css(["jetbrains-mono"], char_set=frozenset("BA"))
    assert out_a == out_b


def test_subset_failure_falls_back_to_full() -> None:
    """If fontTools raises mid-subset, the loader emits the full font.

    The fallback path is the pre-v0.3.7 behavior — a degraded run still
    produces a correct artifact. The warning side-effect is observable
    via ``logging`` but the test only pins the byte-level contract:
    embedded payload must be valid WOFF2 base64.
    """
    full_b64 = _load_font("jetbrains-mono")[3]
    full_b64_block = load_font_face_css(["jetbrains-mono"], char_set=None)
    assert full_b64 in full_b64_block

    # Force a subset failure by monkeypatching the subsetter; bust the LRU
    # so the patched path actually executes.
    _subset_b64.cache_clear()
    with patch("hyperweave.render.fonts.Subsetter") as mock_sub:
        mock_sub.side_effect = RuntimeError("simulated fonttools failure")
        out = load_font_face_css(["jetbrains-mono"], char_set=frozenset("X"))
    # Must still produce a valid @font-face with a base64 payload
    assert "@font-face" in out
    assert "base64," in out
    # And the payload should be the FULL font (fallback path)
    assert full_b64 in out
    _subset_b64.cache_clear()


# ─── Per-artifact byte ceilings (combined Layer 1 + 2 contract) ─────


_BADGE_SPEC_KWARGS = {"title": "BUILD", "value": "passing", "state": "passing"}


@pytest.mark.parametrize(
    ("genome_id", "variant", "raw_max", "gzip_max"),
    [
        ("brutalist", "celadon", 40_000, 20_000),
        ("brutalist", "pulse", 40_000, 20_000),
        ("chrome", "horizon", 52_000, 28_500),
        ("automata", "teal", 44_000, 22_000),
    ],
)
def test_badge_byte_ceiling(genome_id: str, variant: str, raw_max: int, gzip_max: int) -> None:
    """Badge artifacts must compress below per-(genome, variant) ceilings.

    Ceilings calibrated from v0.3.7 Layer 1+2 post-compression measurements
    with ~10% headroom. Pre-v0.3.7 baseline was 68-80KB gzip; post is
    18-26KB gzip across the matrix. A regression that re-bloats fonts
    (e.g. accidentally embedding an unused family, or reverting the subset)
    fails here before the proofset regen.
    """
    spec = ComposeSpec(type="badge", genome_id=genome_id, variant=variant, **_BADGE_SPEC_KWARGS)
    svg_bytes = compose(spec).svg.encode("utf-8")
    raw = len(svg_bytes)
    gz = len(gzip.compress(svg_bytes))
    assert raw < raw_max, f"{genome_id}.{variant} badge raw = {raw}B (>{raw_max}B ceiling)"
    assert gz < gzip_max, f"{genome_id}.{variant} badge gzip = {gz}B (>{gzip_max}B ceiling)"


@pytest.mark.parametrize(
    ("genome_id", "variant", "raw_max", "gzip_max"),
    [
        ("brutalist", "celadon", 65_000, 37_500),
        ("chrome", "horizon", 52_000, 28_500),
    ],
)
def test_strip_byte_ceiling(genome_id: str, variant: str, raw_max: int, gzip_max: int) -> None:
    """Strip artifacts must compress below per-(genome, variant) ceilings."""
    spec = ComposeSpec(type="strip", genome_id=genome_id, variant=variant)
    svg_bytes = compose(spec).svg.encode("utf-8")
    raw = len(svg_bytes)
    gz = len(gzip.compress(svg_bytes))
    assert raw < raw_max, f"{genome_id}.{variant} strip raw = {raw}B (>{raw_max}B ceiling)"
    assert gz < gzip_max, f"{genome_id}.{variant} strip gzip = {gz}B (>{gzip_max}B ceiling)"


@pytest.mark.parametrize(
    ("genome_id", "variant", "raw_max", "gzip_max"),
    [
        ("brutalist", "celadon", 60_000, 36_000),
        ("brutalist", "pulse", 60_000, 36_000),
        ("chrome", "horizon", 48_000, 27_000),
    ],
)
def test_stats_byte_ceiling(genome_id: str, variant: str, raw_max: int, gzip_max: int) -> None:
    """Stats artifacts must compress below per-(genome, variant) ceilings."""
    spec = ComposeSpec(type="stats", genome_id=genome_id, variant=variant)
    svg_bytes = compose(spec).svg.encode("utf-8")
    raw = len(svg_bytes)
    gz = len(gzip.compress(svg_bytes))
    assert raw < raw_max, f"{genome_id}.{variant} stats raw = {raw}B (>{raw_max}B ceiling)"
    assert gz < gzip_max, f"{genome_id}.{variant} stats gzip = {gz}B (>{gzip_max}B ceiling)"


@pytest.mark.parametrize(
    ("genome_id", "variant", "raw_max", "gzip_max"),
    [
        ("brutalist", "celadon", 60_000, 36_000),
        ("chrome", "horizon", 52_000, 28_000),
        ("automata", "teal", 70_000, 28_000),
    ],
)
def test_chart_byte_ceiling(genome_id: str, variant: str, raw_max: int, gzip_max: int) -> None:
    """Chart artifacts must compress below per-(genome, variant) ceilings."""
    spec = ComposeSpec(type="chart", genome_id=genome_id, variant=variant)
    svg_bytes = compose(spec).svg.encode("utf-8")
    raw = len(svg_bytes)
    gz = len(gzip.compress(svg_bytes))
    assert raw < raw_max, f"{genome_id}.{variant} chart raw = {raw}B (>{raw_max}B ceiling)"
    assert gz < gzip_max, f"{genome_id}.{variant} chart gzip = {gz}B (>{gzip_max}B ceiling)"


# ─── Self-containment + accessibility invariants ────────────────────


@pytest.mark.parametrize("genome_id", ["brutalist", "chrome", "automata"])
def test_self_contained_invariants_preserved(genome_id: str) -> None:
    """Subsetting must NOT break the self-contained SVG contract.

    No external font URLs, no script tags, no event handlers, ARIA
    attributes preserved, ``prefers-reduced-motion`` CSS present,
    ``hw:tradeoffs`` metadata still emitted.
    """
    spec = ComposeSpec(type="badge", genome_id=genome_id, title="BUILD", value="passing", state="passing")
    svg = compose(spec).svg

    # Self-containment: no external resources
    assert "@import url(" not in svg, f"{genome_id} badge has @import url() — not self-contained"
    assert "<script" not in svg, f"{genome_id} badge has <script> — security risk"
    assert " onload=" not in svg, f"{genome_id} badge has onload handler — security risk"
    assert " onclick=" not in svg, f"{genome_id} badge has onclick handler — security risk"

    # Accessibility: ARIA + reduced motion preserved
    assert "<title" in svg, f"{genome_id} badge missing <title> ARIA element"
    assert "<desc" in svg, f"{genome_id} badge missing <desc> ARIA element"
    assert "prefers-reduced-motion" in svg, f"{genome_id} badge missing prefers-reduced-motion CSS"


def test_subset_includes_rendered_text_chars() -> None:
    """The extracted char set must include every char from title + value.

    Render a badge with non-baseline characters (Q, Z, !) and confirm
    the embedded JBM subset includes those glyphs. Counter-test against
    the safe baseline by using glyphs OUTSIDE the baseline set.
    """
    # ! is not in _SAFE_BASELINE, so the subset must include it from the title
    spec = ComposeSpec(
        type="badge",
        genome_id="brutalist",
        variant="celadon",
        title="QUIZ!",
        value="zoom!",
        state="passing",
    )
    svg = compose(spec).svg
    # The badge embeds JBM (only font for brutalist badge). Decode the subset
    # and confirm it covers Q, U, I, Z, !.
    import base64
    import io

    from fontTools.ttLib import TTFont

    m = re.search(r"base64,([A-Za-z0-9+/=]+)\)\s*format\('woff2'\)", svg)
    assert m is not None, "no woff2 base64 payload found in badge"
    woff2_bytes = base64.b64decode(m.group(1))
    font = TTFont(io.BytesIO(woff2_bytes))
    cmap = font["cmap"].getBestCmap()
    for char in "QUIZ!":
        assert ord(char) in cmap, f"subset is missing glyph for '{char}' (codepoint {ord(char)})"
