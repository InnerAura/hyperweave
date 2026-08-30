"""The pinned font-feature contract — measured, never inherited.

``layout_features = ["*"]`` retained every OpenType stylistic set and
alternate: measured 30,968 dead bytes on Inter's 68-character baseline subset
alone (-56%), and 41% of a full artifact's gzipped weight. The fix is an
EXPLICIT pinned list — never fontTools' default (unbounded across versions: a
future release could silently move every artifact's bytes and metrics), never
``[]`` (drops kern, which moves rendered advances off the metrics LUT the
solver measured with).

Width and glyph identity are contracts, not hopes: the pinned subset must keep
byte-identical outlines and advances for every baseline character, and must
retain the shaping tables (GPOS kerning, GSUB ligatures) wherever the
full-feature subset had them.
"""

from __future__ import annotations

import io

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

from hyperweave.render import fonts as hw_fonts

PINNED = ["kern", "liga", "calt", "clig", "mark", "mkmk", "ccmp", "locl"]
_CHARS = "".join(sorted(set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .:/-·")))


def _subset(slug: str, features: list[str]) -> TTFont:
    font = TTFont(io.BytesIO(hw_fonts._load_font_bytes(slug)))
    options = Options()
    options.flavor = None  # keep tables inspectable
    options.hinting = False
    options.desubroutinize = True
    options.layout_features = features
    options.notdef_glyph = True
    options.notdef_outline = True
    subsetter = Subsetter(options=options)
    subsetter.populate(text=_CHARS)
    subsetter.subset(font)
    return font


class TestPinnedFeatureList:
    def test_the_shipped_subsetter_uses_the_pinned_list(self) -> None:
        # The production path must never regress to ["*"] or to the unbounded
        # fontTools default — the list is pinned in one place, asserted here.
        import inspect

        source = inspect.getsource(hw_fonts._subset_b64)
        assert 'layout_features = ["*"]' not in source
        assert "kern" in source and "mkmk" in source

    def test_width_contract_advances_identical(self) -> None:
        # hmtx advances for every baseline character are byte-equal between
        # the full-feature subset and the pinned subset — the metrics LUT the
        # solver measured with stays true.
        for slug in ("inter", "jetbrains-mono"):
            full, pinned = _subset(slug, ["*"]), _subset(slug, PINNED)
            cmap_f, cmap_p = full.getBestCmap(), pinned.getBestCmap()
            for ch in _CHARS:
                cp = ord(ch)
                assert (cp in cmap_f) == (cp in cmap_p), f"{slug}: coverage differs at {ch!r}"
                if cp in cmap_f:
                    assert full["hmtx"][cmap_f[cp]] == pinned["hmtx"][cmap_p[cp]], f"{slug}: advance moved for {ch!r}"

    def test_glyph_outlines_identical(self) -> None:
        for slug in ("inter", "jetbrains-mono"):
            full, pinned = _subset(slug, ["*"]), _subset(slug, PINNED)
            cmap_f, cmap_p = full.getBestCmap(), pinned.getBestCmap()
            glyf_f, glyf_p = full["glyf"], pinned["glyf"]
            for ch in _CHARS:
                cp = ord(ch)
                if cp in cmap_f:
                    # Resolved coordinates, not compiled bytes: a composite
                    # glyph stores component INDICES, which legitimately
                    # differ between two subsets of different sizes.
                    coords_f = glyf_f[cmap_f[cp]].getCoordinates(glyf_f)
                    coords_p = glyf_p[cmap_p[cp]].getCoordinates(glyf_p)
                    assert coords_f == coords_p, f"{slug}: outline changed for {ch!r}"

    def test_shaping_tables_survive(self) -> None:
        # Kerning (GPOS) and ligatures (GSUB) must not be casualties of the
        # trim — [] would strip them, and that is the failure the pin forbids.
        for slug in ("inter", "jetbrains-mono"):
            full, pinned = _subset(slug, ["*"]), _subset(slug, PINNED)
            for table in ("GPOS", "GSUB"):
                assert (table in full) == (table in pinned), f"{slug}: {table} dropped by the pinned list"

    def test_pinned_subset_is_materially_smaller(self) -> None:
        def _bytes(font: TTFont) -> int:
            out = io.BytesIO()
            font.save(out)
            return len(out.getvalue())

        full, pinned = _bytes(_subset("inter", ["*"])), _bytes(_subset("inter", PINNED))
        assert pinned < full * 0.7, f"expected >30% savings on Inter, got {full} -> {pinned}"
