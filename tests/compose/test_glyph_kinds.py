"""Core glyph set + the node ``kind`` resolution ladder (§4, diagrams-v2).

The brand registry answers ``glyph`` (company marks, fills); the CORE set
(``glyphs-core.json``, Lucide-derived 24px/2px stroke geometry, see NOTICE)
answers ``kind`` (database, server, ...). The identity-slot ladder is
brand -> kind -> nothing — an unknown slug renders NO mark, never an empty
group (icon-or-nothing law).
"""

from __future__ import annotations

import json
from pathlib import Path

from hyperweave.compose.diagram.chrome import node_glyph_id
from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_glyphs
from hyperweave.core.diagram import DiagramNode
from hyperweave.core.models import ComposeSpec

_ROOT = Path(__file__).resolve().parent.parent.parent
_CORE = _ROOT / "src" / "hyperweave" / "data" / "registries" / "glyphs-core.json"


class TestCoreRegistryShape:
    def test_core_set_size_and_geometry(self) -> None:
        # The confirmed band: 50-115 marks, every one 24px viewBox / 2px
        # stroke. Ceiling raised 100→115 for the prototype glyph audit's
        # nine specimen-cited additions (check, waves, hash, triangle,
        # files, frame, dna, blend, columns-2 — each drawn by a hand file a
        # preset recreates); the band still catches an unreviewed dump.
        core = json.loads(_CORE.read_text())
        assert 50 <= len(core) <= 115
        for name, entry in core.items():
            assert entry["viewBox"] == "0 0 24 24", name
            assert entry["stroke"] == 2, name
            assert entry["paths"] and all(d for d in entry["paths"]), name

    def test_merge_keeps_both_claims(self) -> None:
        # Brands shadow bare generic words; the kind: namespace keeps the
        # generic mark reachable — each channel resolves its own claim.
        g = load_glyphs()
        assert "stroke" not in g["shield"]  # bare = the brand fill
        assert g["kind:shield"]["stroke"] == 2  # namespaced = the core mark
        assert g["database"]["stroke"] == 2  # unshadowed core keeps its bare name

    def test_notice_attribution(self) -> None:
        notice = (_ROOT / "NOTICE").read_text()
        assert "Lucide" in notice and "ISC" in notice
        assert "glyphs-core.json" in notice


class TestKindLadder:
    def test_brand_beats_kind(self) -> None:
        g = load_glyphs()
        node = DiagramNode(id="a", label="a", glyph="anthropic", kind="database")
        assert node_glyph_id(node, g) == "anthropic"

    def test_kind_resolves_core(self) -> None:
        # The kind channel resolves through its namespace UNIFORMLY — the
        # rendered glyph id says which channel claimed the mark.
        g = load_glyphs()
        assert node_glyph_id(DiagramNode(id="a", label="a", kind="database"), g) == "kind:database"
        # A brand-shadowed generic word still reaches the generic mark.
        assert node_glyph_id(DiagramNode(id="a", label="a", kind="shield"), g) == "kind:shield"

    def test_unknown_glyph_falls_to_kind(self) -> None:
        g = load_glyphs()
        node = DiagramNode(id="a", label="a", glyph="no-such-brand", kind="server")
        assert node_glyph_id(node, g) == "kind:server"

    def test_nothing_resolves_nothing(self) -> None:
        g = load_glyphs()
        assert node_glyph_id(DiagramNode(id="a", label="a", kind="no-such-kind"), g) == ""
        assert node_glyph_id(DiagramNode(id="a", label="a"), g) == ""


class TestStrokeChannel:
    def test_kind_marks_render_as_strokes(self) -> None:
        svg = compose(
            ComposeSpec(
                type="diagram",
                genome_id="primer",
                variant="porcelain",
                diagram={
                    "topology": "pipeline",
                    "title": "T",
                    "node_style": "card+glyph",
                    "nodes": [
                        {"id": "a", "label": "ingest", "kind": "database"},
                        {"id": "b", "label": "api", "kind": "server"},
                        {"id": "c", "label": "ghost", "kind": "no-such-kind"},
                    ],
                },
            )
        ).svg
        # Two resolved kinds -> two stroke groups (round caps/joins, fill none);
        # the unknown kind renders NOTHING (icon-or-nothing).
        assert svg.count('stroke-linecap="round" stroke-linejoin="round"') == 2
        assert svg.count("<g ") == svg.count("</g>")


class TestDiscoverySurfaces:
    def test_idioms_selector(self) -> None:
        from hyperweave.surfaces.discover import discover

        idi = discover("idioms")["idioms"]
        assert set(idi["line"]) == {"assert", "drift", "flow", "bypass"}
        assert "chip" in idi["box"] and "edge-chip" in idi["box"]
        assert idi["class_native"]["axial-cross"]["class"] == "hub"

    def test_glyph_kinds_listed(self) -> None:
        from hyperweave.surfaces.discover import discover

        d = discover("glyphs")
        assert len(d["glyph_kinds"]) == len(json.loads(_CORE.read_text()))
        assert "database" in d["glyph_kinds"] and "shield" in d["glyph_kinds"]
        assert not any(k.startswith("kind:") for k in d["glyphs"])

    def test_llms_full_carries_idiom_tier(self) -> None:
        from hyperweave.surfaces.discover import render_llms_full_txt

        full = render_llms_full_txt()
        assert "## Idiom tier" in full
        assert "relation `drift`" in full
        assert "axial-cross" in full
