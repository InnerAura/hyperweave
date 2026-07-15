"""§12.1 nested topology composition — depth-2 sweeps (diagrams-v2).

A ``node.embed`` composes recursively as a FULL bare-chrome artifact of the
same genome/variant (the laws recurse by construction) and scales into its
container's content box as a child ``<svg>``. Outer edges target containers
only; depth caps at 2; a container never inflates its text siblings.
"""

from __future__ import annotations

import re

import pydantic
import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

_INNER = {
    "topology": "hub",
    "title": "inner ring",
    "nodes": [
        {"id": "core", "label": "core", "role": "hero"},
        {"id": "a", "label": "auth"},
        {"id": "b", "label": "billing"},
    ],
    "edges": [
        {"source": "core", "target": "a", "role": "out"},
        {"source": "core", "target": "b", "role": "out"},
    ],
}


def _outer(embed: dict | None = None, **over: object) -> dict:
    spec = {
        "topology": "pipeline",
        "title": "Nested",
        "nodes": [
            {"id": "in", "label": "ingress", "desc": "edge"},
            {"id": "svc", "label": "services", "desc": "the inner mesh", "embed": embed or _INNER},
            {"id": "out", "label": "egress", "desc": "sink"},
        ],
    }
    spec.update(over)
    return spec


def _compose(diagram: dict) -> str:
    return compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=diagram)).svg


class TestNestingComposition:
    def test_container_holds_a_complete_inner_artifact(self) -> None:
        svg = _compose(_outer())
        assert svg.count('data-hw-embed="1"') == 1
        # The inner document travels whole: its metadata block rides inside
        # (two hw:payload blocks in one document — laws recurse) and the
        # wrapper names the inner artifact's content address.
        assert svg.count("<hw:payload") == 2
        assert 'data-hw-embed-id="diagram-' in svg
        # The nested viewport scales via width/height vs viewBox.
        m = re.search(r'<svg x="[0-9.]+" y="[0-9.]+" width="([0-9.]+)" height="[0-9.]+" viewBox="0 0 ([0-9.]+)', svg)
        assert m is not None
        assert float(m.group(1)) <= 360.0 + 0.5  # the embed.max_w knob

    def test_inner_font_payload_strips(self) -> None:
        # The outer document provides the faces; the inner's @font-face
        # blocks would be pure byte duplication.
        svg = _compose(_outer())
        head, _, embedded = svg.partition('data-hw-embed="1"')
        assert "@font-face" in head
        assert "@font-face" not in embedded

    def test_siblings_never_inflate(self) -> None:
        svg = _compose(_outer())
        heights = [float(h) for h in re.findall(r'class="[^"]*-cardbg"[^>]*?height="([0-9.]+)"', svg)] or [
            float(h) for h in re.findall(r'height="([0-9.]+)"[^>]*class="[^"]*-cardbg"', svg)
        ]
        assert heights, "card rects not found"
        assert max(heights) > 150  # the container grew for its canvas
        assert min(heights) < 100  # text siblings stayed compact
        # Width too (the sibling-inflation regression): a container's canvas
        # is never a unit/column vote — plain siblings keep ink-derived
        # widths instead of inheriting the nested artifact's bulk (the 384px
        # platform once made both its 150px siblings render at 326.8).
        widths = [float(w) for w in re.findall(r'class="[^"]*-cardbg"[^>]*?width="([0-9.]+)"', svg)] or [
            float(w) for w in re.findall(r'width="([0-9.]+)"[^>]*class="[^"]*-cardbg"', svg)
        ]
        assert widths and min(widths) < 220, f"plain siblings inflated: {sorted(widths)}"

    def test_inner_artifact_rides_the_outer_face(self) -> None:
        """The nested compose inherits variant AND surface face — a dark
        outer story once embedded a light-faced inner hub (white cards
        floating in the dark container)."""
        import json as _json
        from importlib import resources

        genome = _json.loads(resources.files("hyperweave.data.genomes").joinpath("primer.json").read_text())
        noir_dark = genome["variant_overrides"]["noir"]["diagram_dark"]
        cs = ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="noir",
            surface_face="dark",
            ground="opaque",
            diagram=_outer(),
        )
        svg = compose(cs).svg
        m = re.search(r'<svg[^>]*data-hw-embed="1"[^>]*>(.*?)</svg>', svg, re.S)
        assert m, "embedded artifact not found"
        inner = m.group(1)
        assert noir_dark["card_hi"] in inner, "inner artifact did not inherit the noir dark face"

    def test_depth_two_renders_depth_three_refuses(self) -> None:
        level2 = {
            "topology": "pipeline",
            "title": "level2",
            "nodes": [
                {"id": "p", "label": "P"},
                {"id": "q", "label": "Q", "embed": _INNER},
                {"id": "r", "label": "R"},
            ],
        }
        svg = _compose(_outer(embed=level2))
        assert svg.count('data-hw-embed="1"') == 2  # container inside a container
        level3_inner = {
            "topology": "pipeline",
            "title": "l3",
            "nodes": [
                {"id": "s", "label": "S", "embed": _INNER},
                {"id": "t", "label": "T"},
                {"id": "u", "label": "U"},
            ],
        }
        level2_deep = dict(level2)
        level2_deep["nodes"] = [
            {"id": "p", "label": "P"},
            {"id": "q", "label": "Q", "embed": level3_inner},
            {"id": "r", "label": "R"},
        ]
        with pytest.raises(pydantic.ValidationError, match="nesting-depth"):
            ComposeSpec(type="diagram", genome_id="primer", diagram=_outer(embed=level2_deep))

    def test_cross_boundary_edge_refuses_with_the_rule_name(self) -> None:
        spec = _outer()
        spec["edges"] = [{"source": "in", "target": "core"}]  # 'core' lives inside the embed
        with pytest.raises(pydantic.ValidationError, match="cross-boundary-edge"):
            ComposeSpec(type="diagram", genome_id="primer", diagram=spec)

    def test_payload_keeps_embed_drops_internal_dims(self) -> None:
        from hyperweave.verbs.extract import extract

        svg = _compose(_outer())
        payload = extract(svg, respond="payload").payload
        svc = next(n for n in payload["spec"]["nodes"] if n["id"] == "svc")
        assert svc["embed"]["title"] == "inner ring"  # the inner spec IS content
        assert "embed_dims" not in svc  # resolver-internal, never serialized

    def test_determinism(self) -> None:
        a = _compose(_outer())
        b = _compose(_outer())
        ida = re.search(r'data-hw-id="([^"]+)"', a)
        idb = re.search(r'data-hw-id="([^"]+)"', b)
        assert ida is not None and idb is not None and ida.group(1) == idb.group(1)
