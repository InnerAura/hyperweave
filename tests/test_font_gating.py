"""Per-frame font tree-shaking gate tests (Round 6 / Issue H).

The CSS module gate at compose/assembler.py:183-226 already gates bridge,
expression, status, motion, telemetry per frame type. v0.3.0 Round 6
extended this pattern with `_NEEDS_FONTS` to cover the @font-face base64
payloads that previously loaded for every frame regardless of whether
text rendered.

These tests pin the contract: icons + dividers must NOT embed fonts
(zero text content makes them inert payload), badges + charts + stats
MUST embed fonts (text is the carrier of meaning). The hw:css-modules
debug comment surfaces the gate decision per artifact for visual audit.
"""

from __future__ import annotations

import re

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec


def _extract_modules_comment(svg: str) -> str:
    """Pull the hw:css-modules debug comment value (or empty string if absent)."""
    match = re.search(r"/\* hw:css-modules: ([^*]+) \*/", svg)
    return match.group(1).strip() if match else ""


def test_icon_svg_excludes_fonts() -> None:
    """Icons emit zero <text> elements; @font-face payload must be suppressed.

    Pre-Round-6 the cellular icon defs partial inherited a {{ font_faces }}
    reference from cellular badge/chart/strip. Brutalist + chrome icon defs
    didn't have it; cellular did, embedding ~75KB of unused base64 fonts.
    The gate at context.py:160 + the template-level removal at
    icon/cellular-defs.j2:10 together drop automata icon size from 82KB to ~11KB.
    """
    for genome in ("automata", "chrome", "brutalist"):
        spec = ComposeSpec(type="icon", genome_id=genome, glyph="github")
        svg = compose(spec).svg
        assert "@font-face" not in svg, f"{genome} icon embeds @font-face"
        assert "data:font" not in svg, f"{genome} icon embeds base64 font payload"
        assert "fonts" not in _extract_modules_comment(svg), (
            f"{genome} icon hw:css-modules debug comment should not list 'fonts'"
        )


def test_automata_icon_under_size_ceiling() -> None:
    """Hard size ceiling pins the contract — if a future template change
    reintroduces font payload to icons, this fails before proofset regen.
    Pre-Round-6 was 82KB; post-gate is ~11KB. 15KB ceiling leaves headroom
    for legitimate growth (more rim_stops, glyph variations) without
    accidentally re-admitting fonts."""
    spec = ComposeSpec(type="icon", genome_id="automata", glyph="github")
    svg = compose(spec).svg
    assert len(svg.encode()) < 15_000, (
        f"automata icon SVG = {len(svg.encode())} bytes (>15KB ceiling); "
        "likely re-introduced base64 fonts via a template-level injection"
    )


def test_divider_excludes_fonts() -> None:
    """Divider variants don't embed @font-face — text is handled inline per
    variant (block, current, takeoff, void, zeropoint). The gate keeps
    them clean even though their templates don't currently reference
    {{ font_faces }} — defense-in-depth against future drift."""
    spec = ComposeSpec(type="divider", genome_id="brutalist")
    svg = compose(spec).svg
    assert "@font-face" not in svg
    assert "fonts" not in _extract_modules_comment(svg)


def test_badge_includes_fonts() -> None:
    """Badges render label + value text and must embed fonts. The gate's
    positive case — confirms _NEEDS_FONTS correctly admits text-bearing frames."""
    spec = ComposeSpec(type="badge", genome_id="automata", title="BUILD", value="passing", state="passing")
    svg = compose(spec).svg
    assert "@font-face" in svg, "badge must embed @font-face for label/value text"
    assert "fonts" in _extract_modules_comment(svg)


def test_chart_includes_fonts() -> None:
    """Charts render axis labels + hero value + footer text — fonts required."""
    spec = ComposeSpec(type="chart", genome_id="automata")
    svg = compose(spec).svg
    assert "@font-face" in svg
    assert "fonts" in _extract_modules_comment(svg)


def test_stats_includes_fonts() -> None:
    """Stat cards render header + hero + secondary text across multiple zones."""
    spec = ComposeSpec(type="stats", genome_id="automata")
    svg = compose(spec).svg
    assert "@font-face" in svg
    assert "fonts" in _extract_modules_comment(svg)
