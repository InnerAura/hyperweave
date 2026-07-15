"""Containment + text-survival laws — each pinned (§5 + §12.4, diagrams-v2).

a  per-surface no-clip: nothing renders outside the canvas on ANY preset.
b  markers ride the terminus, aimed by the arrival tangent (the kafka
   "scissors" read was small-size legibility of the true brand mark —
   registry path verified against the official geometry; census note).
c  margins are uniform NSEW — pinned on all four sides via the region stack.
d  wires never cross chrome bands: the data-mesh perimeter channel ran
   through the footer text because extents saw only endpoint chords.
e  curved wires carry their TRUE trace (sampled polylines) — obstacle set
   and extents read the same geometry (shared root with d).
f  per-class ink-mass bands are the mass-ratio diagnostic's calibration
   (§11.5a) — pinned in test_diagram_diagnostics.py with the §6 rules.
g  gallery cells embed exactly one artifact (the ghost-stack sweep lives in
   scripts/generate_surface_matrix.py; pinned here against fixtures).
h  the caption sentence (request-descent's subtitle) never ellipsizes —
   including under --font-mode system; the title survives in accessibility
   metadata even though caption chrome never renders a masthead.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import pytest

from hyperweave.compose.diagram.input import diagram_preset_names, resolve_diagram_preset
from hyperweave.compose.diagram.paths import sample_path
from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec
from tests.compose.test_diagram_layout import _normalized_preset, solve

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))


def _preset_layout(name: str):
    spec = _normalized_preset(name)
    return solve(**spec.model_dump(exclude_defaults=True))


class TestBugANoClip:
    @pytest.mark.parametrize("name", sorted(diagram_preset_names()))
    def test_everything_inside_the_canvas(self, name: str) -> None:
        lay = _preset_layout(name)
        w, h = lay.width, lay.height
        for n in lay.nodes:
            b = n.box
            assert b.x >= -0.5 and b.y >= -0.5 and b.x + b.w <= w + 0.5 and b.y + b.h <= h + 0.5, (name, n.index)
        for c in lay.connectors:
            for px, py in sample_path(c.path_d):
                assert -0.5 <= px <= w + 0.5 and -0.5 <= py <= h + 0.5, (name, c.index, px, py)
        for a in lay.annotations:
            if a.box is not None:
                assert a.box.x >= -0.5 and a.box.y >= -0.5, (name, a.kind)
                assert a.box.x + a.box.w <= w + 0.5 and a.box.y + a.box.h <= h + 0.5, (name, a.kind)


class TestBugBMarkerOnTerminus:
    @pytest.mark.parametrize("name", sorted(diagram_preset_names()))
    def test_marker_touches_the_path_end(self, name: str) -> None:
        # A drawn terminal (chevron tip or dot disc) sits ON the terminus:
        # its geometry starts within one marker-size of where the wire ends.
        lay = _preset_layout(name)
        for c in lay.connectors:
            if not c.marker_d:
                continue
            pts = sample_path(c.path_d)
            mpts = sample_path(c.marker_d)
            if not pts or not mpts:
                continue
            ex, ey = pts[-1]
            near = min(math.hypot(px - ex, py - ey) for px, py in mpts)
            assert near <= 12.0, (name, c.index, near)


class TestBugCMarginsNSEW:
    @pytest.mark.parametrize("name", ["rag-pipeline", "cicd-gate", "hub", "obi-engine"])
    def test_region_stack_breathes_on_all_four_sides(self, name: str) -> None:
        lay = _preset_layout(name)
        m = 24.0  # margin_x on the primer diagram chassis (uniform NSEW, §2)
        regions = {r.id: r for r in lay.regions}
        first = min(lay.regions, key=lambda r: r.y)
        last = max(lay.regions, key=lambda r: r.y + r.h)
        assert first.y >= m - 0.5, name  # N
        # S floor: the bottom region's own stamped margin — the plate law
        # pins per-family caption pads to the hand sheets (cicd-gate 23,
        # tighter than the generic 24), so the uniform floor yields to the
        # chassis-declared one where the chassis speaks.
        s_floor = min(m, float(last.margin[2]))
        assert lay.height - (last.y + last.h) >= s_floor - 0.5, name  # S
        for r in regions.values():
            assert r.x >= m - 0.5, (name, r.id)  # W
            assert lay.width - (r.x + r.w) >= m - 0.5, (name, r.id)  # E


class TestBugDEWireTruth:
    def test_channels_never_cross_chrome_bands(self) -> None:
        # A dag whose bypass channel dips BELOW the ranks (service-dependencies'
        # web->postgres direct read): the footer must stack BELOW the channel.
        lay = _preset_layout("service-dependencies")
        footer = next(r for r in lay.regions if r.id == "footer")
        max_wire_y = max(py for c in lay.connectors for _, py in sample_path(c.path_d))
        assert footer.y >= max_wire_y - 0.5

    @pytest.mark.parametrize("name", sorted(diagram_preset_names()))
    def test_wires_stay_inside_the_content_region(self, name: str) -> None:
        # e: sampled traces (not chords) bound every wire into the content
        # region — a dip outside it would collide with stacked chrome.
        lay = _preset_layout(name)
        content = next(r for r in lay.regions if r.id == "content")
        for c in lay.connectors:
            for px, py in sample_path(c.path_d):
                assert content.y - 0.5 <= py <= content.y + content.h + 0.5, (name, c.index, py)
                assert content.x - 0.5 <= px <= content.x + content.w + 0.5, (name, c.index, px)


class TestBugGGallerySweep:
    def test_one_artifact_per_cell(self) -> None:
        from generate_surface_matrix import _sweep_gallery_cells

        one = (
            '<figure><div class="hosts">'
            '<div class="host host-light"><img src="a.svg" alt=""></div>'
            '<div class="host host-dark"><img src="a.svg" alt=""></div>'
            "</div></figure>"
        )
        _sweep_gallery_cells(one)  # one artifact over two grounds — legal
        two = one.replace('host-dark"><img src="a.svg"', 'host-dark"><img src="b.svg"')
        with pytest.raises(AssertionError):
            _sweep_gallery_cells(two)  # two artifacts in one cell — the ghost-stack
        doubled = one.replace(
            '<div class="host host-dark"><img src="a.svg" alt=""></div>',
            '<div class="host host-dark"><img src="a.svg" alt=""><img src="a.svg" alt=""></div>',
        )
        with pytest.raises(AssertionError):
            _sweep_gallery_cells(doubled)


class TestBugHWrapBeforeTruncate:
    def _compose(self, preset: str, font_mode: str) -> str:
        return compose(
            ComposeSpec(
                type="diagram",
                genome_id="primer",
                variant="porcelain",
                font_mode=font_mode,
                diagram=resolve_diagram_preset(preset),
            )
        ).svg

    @pytest.mark.parametrize("font_mode", ["embed", "system"])
    def test_caption_never_ellipsizes_title_survives_in_metadata(self, font_mode: str) -> None:
        # The subject moved off obi-engine when its hand sheet's captionless
        # chrome was ratified (chrome: plain) — the ellipsis contract now
        # exercises the longest restored caption sentence instead.
        svg = self._compose("observability-converge", font_mode)
        # Caption chrome never renders a masthead group — the title still
        # ships whole via the SVG accessibility <title>, never truncated.
        assert 'data-hw-region="masthead"' not in svg
        title_body = svg.split("<title", 1)[-1].split("</title>", 1)[0]
        assert "<title" in svg and "Observability signals DAG" in title_body
        # The caption sentence (subtitle wins over title) renders whole in
        # the footer region — no ellipsis anywhere in chrome text (content
        # descs may ellipsize by their own truncation contract; chrome must
        # not).
        footer = svg.split('data-hw-region="footer"', 1)[-1].split("</g>", 1)[0]
        assert "unified in one dashboard" in footer
        assert "…" not in footer

    @pytest.mark.parametrize("font_mode", ["embed", "system"])
    def test_plain_chrome_renders_no_caption(self, font_mode: str) -> None:
        # obi-engine's hand sheet is captionless; chrome: plain keeps the
        # full plate and drops only the caption line — the subtitle still
        # ships in the accessibility metadata, never as chrome ink.
        svg = self._compose("obi-engine", font_mode)
        title_body = svg.split("<title", 1)[-1].split("</title>", 1)[0]
        assert "one engine under every surface" in title_body
        assert not re.search(r'class="[^"]*-cap"', svg)
