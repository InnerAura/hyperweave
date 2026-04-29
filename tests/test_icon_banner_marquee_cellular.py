"""Automata cellular icon + banner — Phase 6/7 rendering validation.

Marquee cellular paradigm currently aliases brutalist due to marquee's
envelope_stops-based dispatch (separate from paradigm interpolation).
This is tracked as a follow-up; cellular tspan alternation is a v1.1 item.
"""

from __future__ import annotations

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

# ── Cellular icon ────────────────────────────────────────────────────────


@pytest.mark.parametrize("family", ["blue", "purple"])
def test_cellular_icon_renders_family_palette(family: str) -> None:
    spec = ComposeSpec(type="icon", genome_id="automata", glyph="github", family=family)
    svg = compose(spec).svg
    if family == "blue":
        assert "#1E849A" in svg
        assert "#104052" in svg
    else:
        assert "#6B3B8A" in svg
        assert "#331A4A" in svg


def test_cellular_icon_has_4x4_cell_grid() -> None:
    spec = ComposeSpec(type="icon", genome_id="automata", glyph="github", family="blue")
    svg = compose(spec).svg
    # 16 cells = 4 rows x 4 cols at 16px pitch
    assert svg.count('width="16" height="16"') >= 16


def test_cellular_icon_uses_pulse_classes() -> None:
    spec = ComposeSpec(type="icon", genome_id="automata", glyph="github", family="blue")
    svg = compose(spec).svg
    for cls in ("si1", "si2", "si3", "sid"):
        assert f'class="{cls}"' in svg


def test_cellular_icon_is_64x64() -> None:
    spec = ComposeSpec(type="icon", genome_id="automata", glyph="github", family="blue")
    result = compose(spec)
    assert result.width == 64
    assert result.height == 64


# ── Cellular banner ──────────────────────────────────────────────────────


def test_cellular_banner_renders_bifamily_flanks() -> None:
    spec = ComposeSpec(
        type="banner",
        genome_id="automata",
        title="AUTOMATA",
        value="Living Artifacts",
        family="bifamily",
        variant="compact",
    )
    svg = compose(spec).svg
    # Both flank palettes should render
    assert "#1E849A" in svg
    assert "#6B3B8A" in svg


def test_cellular_banner_has_pulse_classes() -> None:
    spec = ComposeSpec(
        type="banner",
        genome_id="automata",
        title="AUTOMATA",
        value="Living Artifacts",
        family="bifamily",
        variant="compact",
    )
    svg = compose(spec).svg
    for cls in ("cb1", "cb2", "cb3", "cb4"):
        assert f'class="{cls}"' in svg


def test_cellular_banner_hero_uses_orbitron() -> None:
    spec = ComposeSpec(
        type="banner",
        genome_id="automata",
        title="AUTOMATA",
        value="Living Artifacts",
        family="bifamily",
        variant="compact",
    )
    svg = compose(spec).svg
    assert "'Orbitron'" in svg


def test_cellular_banner_respects_compact_variant() -> None:
    compact_spec = ComposeSpec(
        type="banner",
        genome_id="automata",
        title="AUTOMATA",
        value="Living Artifacts",
        family="bifamily",
        variant="compact",
    )
    full_spec = ComposeSpec(
        type="banner",
        genome_id="automata",
        title="AUTOMATA",
        value="Living Artifacts",
        family="bifamily",
        variant="default",
    )
    r_compact = compose(compact_spec)
    r_full = compose(full_spec)
    # Cellular banner canvas is specimen-locked to 800x220 for BOTH variants
    # (per paradigm config; spec cellular-automata-hero-banner-v2.svg is 800x220).
    assert r_compact.width == 800
    assert r_compact.height == 220
    assert r_full.width == 800
    assert r_full.height == 220
