"""Per-(frame, genome) font embedding gate tests.

The CSS module gate at compose/assembler.py:183-226 already gates bridge,
expression, status, motion, telemetry per frame type. The font embedding
gate is per-(frame, genome) via ``data/font-embedding.yaml`` so the brutalist badge
embeds JetBrains Mono only (saving ~28KB) even though the brutalist
genome declares Barlow Condensed for its stats/strip/chart frames.

These tests pin the contract: icons + dividers must NOT embed fonts
(zero text content makes them inert payload); badges + charts + stats
MUST embed fonts (text is the carrier of meaning); and within those
text-bearing frames, only the slugs the templates' CSS classes
actually reference get embedded. The ``hw:css-modules`` debug comment
surfaces the gate decision per artifact for visual audit.
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
    positive case — confirms text-bearing frames get @font-face payloads."""
    spec = ComposeSpec(type="badge", genome_id="automata", title="BUILD", value="passing", state="passing")
    svg = compose(spec).svg
    assert "@font-face" in svg, "badge must embed @font-face for label/value text"
    assert "fonts" in _extract_modules_comment(svg)


def _embedded_families(svg: str) -> set[str]:
    """Return the set of font-family names appearing in @font-face blocks."""
    blocks = re.findall(r"@font-face\s*\{[^}]*?font-family:\s*'([^']+)'", svg)
    return set(blocks)


def test_brutalist_badge_excludes_barlow() -> None:
    """Brutalist badge templates reference --dna-font-mono only (= JetBrains
    Mono). Barlow Condensed is declared in brutalist.json:fonts for the
    stats/strip/chart frames; the v0.3.7 genome-aware gate prevents it from
    shipping in the badge. Saves ~28KB raw / ~24KB gzip per brutalist badge.
    """
    for variant in ("celadon", "pulse"):
        spec = ComposeSpec(
            type="badge", genome_id="brutalist", variant=variant, title="BUILD", value="passing", state="passing"
        )
        svg = compose(spec).svg
        families = _embedded_families(svg)
        assert "Barlow Condensed" not in families, (
            f"brutalist {variant} badge embeds Barlow Condensed (unused) — gate misconfigured"
        )
        assert families == {"JetBrains Mono"}, (
            f"brutalist {variant} badge expected only JetBrains Mono, got {sorted(families)}"
        )


def test_automata_badge_excludes_jetbrains_mono() -> None:
    """Automata badge CSS classes reference Orbitron (label) + Chakra Petch
    (value). JetBrains Mono is declared in automata.json:fonts for the
    strip/stats/receipt frames; v0.3.7 genome-aware gate
    prevents it from shipping in the badge. Saves ~30KB raw per badge.
    """
    spec = ComposeSpec(type="badge", genome_id="automata", title="BUILD", value="passing", state="passing")
    svg = compose(spec).svg
    families = _embedded_families(svg)
    assert "JetBrains Mono" not in families, "automata badge embeds JetBrains Mono (unused) — gate misconfigured"
    assert families == {"Orbitron", "Chakra Petch"}, (
        f"automata badge expected Orbitron + Chakra Petch, got {sorted(families)}"
    )


def test_automata_chart_excludes_chakra_petch() -> None:
    """Automata chart cellular-defs.j2 binds Orbitron (header) + JetBrains
    Mono (axis labels). Chakra Petch is declared in automata.json:fonts
    for the badge/strip/stats frames but never bound to a chart CSS class;
    v0.3.7 genome-aware gate prevents it from shipping. Saves ~14KB raw.
    """
    spec = ComposeSpec(type="chart", genome_id="automata")
    svg = compose(spec).svg
    families = _embedded_families(svg)
    assert "Chakra Petch" not in families, "automata chart embeds Chakra Petch (unused) — gate misconfigured"


# Combined Layer 1 + Layer 2 byte ceilings live in tests/test_font_subsetting.py
# where they're parameterized across the full (genome, variant) matrix.


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
