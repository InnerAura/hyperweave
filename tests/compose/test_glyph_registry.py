"""Glyph registry contract — data gate + tint selection/degradation.

The registry (data/glyphs.json) is config; these tests pin its shape so a
bad rebuild fails loud at CI instead of rendering broken marks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import hyperweave
from hyperweave.compose.matrix.cells import glyph_mark_placement, resolve_glyph_mode
from hyperweave.compose.spatial_records import RectSpec
from hyperweave.core.matrix import GlyphTint

# The BRAND file itself — this suite gates the data file's shape. The
# runtime loader merges it with the core set (glyphs-core.json) and adds
# kind: namespace entries; that merged view has its own pins in
# test_glyph_kinds.py.
GLYPHS = json.loads((Path(hyperweave.__file__).parent / "data" / "registries" / "glyphs.json").read_text())

_FIELD_ORDER = ["path", "viewBox", "brand_color", "category", "mono", "gradient", "fill_rule", "color_paths"]
_GEOMETRIC = {
    "circle",
    "diamond",
    "hexagon",
    "shield",
    "shieldcheck",
    "star",
    "triangle",
    "braces",
    "textlines",
}
_EVENODD = {"azure", "langfuse", "msteams", "playwright", "vscode", "zoom"}


class TestRegistryShape:
    def test_size_sort_and_uniqueness(self) -> None:
        assert len(GLYPHS) >= 189
        keys = list(GLYPHS)
        assert keys == sorted(keys)
        assert len(keys) == len(set(keys))

    def test_field_order_and_required_fields(self) -> None:
        for key, entry in GLYPHS.items():
            fields = list(entry)
            assert fields == [f for f in _FIELD_ORDER if f in entry], key
            assert entry.get("path"), key
            assert entry.get("viewBox"), key
            assert entry.get("category"), key

    def test_brand_color_null_only_on_geometric_and_sigil(self) -> None:
        # hyperweave carries its own brand color (the hero
        # mark renders signal blue under glyph_tint: brand/full, matching the
        # primer-diagrams-v3 prototypes, instead of degrading to plain ink).
        nulls = {k for k, v in GLYPHS.items() if v.get("brand_color") is None}
        assert nulls == _GEOMETRIC

    def test_fill_rule_entries(self) -> None:
        assert {k for k, v in GLYPHS.items() if "fill_rule" in v} == _EVENODD
        assert all(GLYPHS[k]["fill_rule"] == "evenodd" for k in _EVENODD)

    def test_mono_declarations(self) -> None:
        """A1: `mono: true` = the OFFICIAL brand mark is single-color, by
        design forever — exclusive with full-capability, exactly the audited
        class-(b) set; the remainder is the named class-(c) debt inventory
        (docs/decisions/glyph-registry-full-audit.md)."""
        monos = {k for k, v in GLYPHS.items() if "mono" in v}
        assert all(GLYPHS[k]["mono"] is True for k in monos)
        full = {k for k, v in GLYPHS.items() if "color_paths" in v or "gradient" in v}
        assert not monos & full, monos & full
        assert len(monos) == 125  # elasticsearch promoted from wave-3 debt: single-color mark, no gradient/color_paths
        assert len(full) == 38
        assert len(set(GLYPHS) - monos - full) == 29  # the named wave-3 debt

    def test_color_paths_shape(self) -> None:
        masters = {k: v["color_paths"] for k, v in GLYPHS.items() if "color_paths" in v}
        assert len(masters) >= 28
        for key, master in masters.items():
            assert master.get("viewBox"), key
            paths = master.get("paths")
            assert isinstance(paths, list) and paths, key
            for p in paths:
                assert p.get("d") and p.get("fill"), key

    def test_gradient_entries_have_stops(self) -> None:
        for key, entry in GLYPHS.items():
            if "gradient" in entry:
                assert entry["gradient"].get("stops"), key


class TestTintSelection:
    """full -> gradient -> brand -> ink degradation, never an error."""

    def test_full_uses_color_master_when_present(self) -> None:
        key = next(k for k, v in GLYPHS.items() if "color_paths" in v)
        assert resolve_glyph_mode(GLYPHS[key], GlyphTint.FULL) == "full"

    def test_full_degrades_without_master(self) -> None:
        entry = GLYPHS["openai"]
        assert "color_paths" not in entry
        assert resolve_glyph_mode(entry, GlyphTint.FULL) in ("gradient", "brand")

    def test_brand_never_picks_the_color_master(self) -> None:
        key = next(k for k, v in GLYPHS.items() if "color_paths" in v and "gradient" not in v)
        assert resolve_glyph_mode(GLYPHS[key], GlyphTint.BRAND) == "brand"

    def test_gradient_outranks_brand(self) -> None:
        assert resolve_glyph_mode(GLYPHS["gemini"], GlyphTint.BRAND) == "gradient"

    def test_ink_is_ink_and_the_null_brand_fallback(self) -> None:
        assert resolve_glyph_mode(GLYPHS["github"], GlyphTint.INK) == "ink"
        # "circle" is one of the geometric entries with no brand identity —
        # brand_color stays null by design, so BRAND degrades to ink.
        assert resolve_glyph_mode(GLYPHS["circle"], GlyphTint.BRAND) == "ink"
        # hyperweave now carries its own brand color: BRAND
        # resolves to the mark itself instead of degrading.
        assert resolve_glyph_mode(GLYPHS["hyperweave"], GlyphTint.BRAND) == "brand"

    @pytest.mark.parametrize("tint", list(GlyphTint))
    def test_every_entry_renders_under_every_tint(self, tint: GlyphTint) -> None:
        """The compositor never crashes on any entry under any selection."""
        for key, entry in GLYPHS.items():
            placement = glyph_mark_placement(
                entry,
                glyph_id=key,
                kind_row=0,
                col=0,
                box=RectSpec(0, 0, 24, 24),
                cx=12.0,
                cy=12.0,
                size=18.0,
                tint=tint,
            )
            assert placement.glyph_paths, key
            assert all(p.d for p in placement.glyph_paths), key
            if key in _EVENODD:
                assert placement.glyph_fill_rule == "evenodd", key

    def test_full_mode_uses_the_color_master_viewbox(self) -> None:
        key = next(k for k, v in GLYPHS.items() if "color_paths" in v and v["color_paths"]["viewBox"] != v["viewBox"])
        entry = GLYPHS[key]
        full = glyph_mark_placement(
            entry,
            glyph_id=key,
            kind_row=0,
            col=0,
            box=RectSpec(0, 0, 24, 24),
            cx=12,
            cy=12,
            size=18,
            tint=GlyphTint.FULL,
        )
        ink = glyph_mark_placement(
            entry,
            glyph_id=key,
            kind_row=0,
            col=0,
            box=RectSpec(0, 0, 24, 24),
            cx=12,
            cy=12,
            size=18,
            tint=GlyphTint.INK,
        )
        assert full.glyph_transform != ink.glyph_transform  # different coordinate spaces
        assert len(full.glyph_paths) == len(entry["color_paths"]["paths"])
        assert all(p.fill for p in full.glyph_paths)
