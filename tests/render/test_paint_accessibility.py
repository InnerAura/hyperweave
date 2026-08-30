"""Session-C emit-time gates: paint economy + accessibility structure.

Guard Law throughout — every gate reads the EMITTED artifact bytes, never the
config that produced them:

- role-aware contrast: muted connectors clear the 3:1 graphical floor against
  the ground they cross, on BOTH faces; the declared text pairs clear 4.5:1;
- filter-pixel budget: sum of (region-area multiple x primitives x consumers)
  per artifact stays under a cap cited from the measured corpus maximum
  (206.4 on lanes, 2026-08-30) — a region blowout or primitive pile-up fails;
- the material grain stays one octave (the second octave was sub-Nyquist
  aliasing at every delivery scale);
- aria-hidden decoupling: decorative geometry (wires, markers, halos, icon
  geometry) is hidden from the AOM, and no ``<text>`` ever sits inside a
  hidden subtree;
- the glyph pre-blend holds: no group-opacity marks, the icon token declared
  and consumed;
- multi-line node text stacks ship as one ``<text>`` of ``<tspan>`` rows.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

import pytest

from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_diagram_presets
from hyperweave.core.color import contrast_ratio
from hyperweave.core.models import ComposeSpec

_VARIANTS = ("porcelain", "noir", "cream", "petrol", "space", "anvil", "carbon", "dusk")
_FILTER_BUDGET_CAP = 250.0  # measured corpus max 206.4 (lanes, 2026-08-30) + headroom


def _compose(preset: str, **kw: object) -> str:
    return compose(
        ComposeSpec(type="diagram", genome_id="primer", diagram=dict(load_diagram_presets()[preset]), **kw)  # type: ignore[arg-type]
    ).svg


def _styles(svg: str) -> str:
    return "\n".join(re.findall(r"<style\b[^>]*>(.*?)</style>", svg, re.DOTALL))


def _dark_blocks(css: str) -> str:
    return "\n".join(re.findall(r"@media[^{]*prefers-color-scheme:\s*dark[^{]*\{((?:[^{}]|\{[^{}]*\})*)\}", css))


class TestRoleAwareContrast:
    @pytest.mark.parametrize("variant", _VARIANTS)
    def test_muted_connector_clears_3_to_1_on_both_faces(self, variant: str) -> None:
        svg = _compose("dag-gate", variant=variant, ground="opaque", palette="adaptive")
        css = _styles(svg)
        dark = _dark_blocks(css)
        near_conn = re.findall(r"-connmuted \{ stroke: (#[0-9A-Fa-f]{6})", css)
        near_ground = re.findall(r"--dna-surface:\s*(#[0-9A-Fa-f]{6})", css)
        assert near_conn and near_ground, f"{variant}: no measurable near connector pair"
        r = contrast_ratio(near_conn[0], near_ground[0])
        assert r >= 3.0, f"{variant}: near muted wire {near_conn[0]} on {near_ground[0]} = {r:.2f}:1"
        dark_conn = re.findall(r"-connmuted \{ stroke: (#[0-9A-Fa-f]{6})", dark)
        dark_ground = re.findall(r"--dna-surface:\s*(#[0-9A-Fa-f]{6})", dark)
        if dark_conn and dark_ground:  # material block present
            r = contrast_ratio(dark_conn[-1], dark_ground[0])
            assert r >= 3.0, f"{variant}: dark muted wire {dark_conn[-1]} on {dark_ground[0]} = {r:.2f}:1"

    @pytest.mark.parametrize("variant", _VARIANTS)
    def test_declared_text_pairs_clear_4_5_to_1(self, variant: str) -> None:
        # The near block's own declarations are the delivered text palette.
        svg = _compose("dag-gate", variant=variant, ground="opaque", palette="adaptive")
        css = _styles(svg)
        decls = dict(re.findall(r"(--dna-[\w-]+):\s*(#[0-9A-Fa-f]{6})", css.split("@media")[0]))
        surface = decls.get("--dna-surface")
        assert surface
        for token, floor in (("--dna-ink-primary", 4.5), ("--dna-ink-muted", 4.5)):
            value = decls.get(token)
            if value:
                r = contrast_ratio(value, surface)
                assert r >= floor, f"{variant}: {token} {value} on {surface} = {r:.2f}:1 < {floor}"


class TestFilterBudget:
    @pytest.mark.parametrize("preset", ("lanes", "loop-retry-budget", "dag-gate", "tree"))
    def test_filter_pixel_budget_under_cap(self, preset: str) -> None:
        for kw in ({}, {"ground": "opaque", "palette": "fixed"}, {"variant": "noir"}):
            svg = _compose(preset, **kw)
            total = 0.0
            for m in re.finditer(
                r'<filter id="([^"]+)"[^>]*x="(-?[\d.]+)%"[^>]*y="(-?[\d.]+)%"'
                r'[^>]*width="([\d.]+)%"[^>]*height="([\d.]+)%"[^>]*>(.*?)</filter>',
                svg,
                re.DOTALL,
            ):
                fid, _x, _y, w, h, body = m.groups()
                area = (float(w) / 100) * (float(h) / 100)
                primitives = len(re.findall(r"<fe[A-Z]", body))
                consumers = svg.count(f"url(#{fid})")
                total += area * primitives * consumers
            assert total <= _FILTER_BUDGET_CAP, f"{preset} {kw}: filter budget {total:.1f} > {_FILTER_BUDGET_CAP}"

    def test_grain_is_single_octave(self) -> None:
        svg = _compose("dag-gate", variant="noir")
        for octaves in re.findall(r'<feTurbulence[^>]*numOctaves="(\d+)"', svg):
            assert int(octaves) <= 1, "material grain regressed to multi-octave turbulence"


class TestAriaDecoupling:
    @pytest.mark.parametrize("preset", ("loop-retry-budget", "sequence", "lanes", "dag-gate"))
    def test_no_text_inside_hidden_subtrees(self, preset: str) -> None:
        root = ET.fromstring(_compose(preset))
        ns = "{http://www.w3.org/2000/svg}"

        def walk(el: ET.Element, hidden: bool) -> None:
            hidden = hidden or el.get("aria-hidden") == "true"
            if hidden and el.tag == f"{ns}text":
                raise AssertionError(f"{preset}: <text>{el.text!r} hidden from the AOM")
            for child in el:
                walk(child, hidden)

        walk(root, False)

    @pytest.mark.parametrize("preset", ("loop-retry-budget", "sequence", "dag-gate"))
    def test_connector_geometry_is_hidden(self, preset: str) -> None:
        root = ET.fromstring(_compose(preset))
        exposed: list[str] = []

        def walk(el: ET.Element, hidden: bool) -> None:
            hidden = hidden or el.get("aria-hidden") == "true"
            cls = el.get("class", "")
            if not hidden and re.search(r"-(?:branch|mk|trl|pu|halo|p)\b", cls):
                exposed.append(cls)
            for child in el:
                walk(child, hidden)

        walk(root, False)
        assert not exposed, f"{preset}: decorative wire geometry exposed to AT: {exposed[:4]}"


class TestGlyphPreBlend:
    def test_no_group_opacity_marks_remain(self) -> None:
        for preset in ("loop-retry-budget", "tree", "fanin"):
            svg = _compose(preset, ground="opaque", palette="fixed")
            assert 'opacity="0.9"' not in svg, f"{preset}: a mark still rides group opacity"

    def test_icon_token_declared_and_consumed_together(self) -> None:
        svg = _compose("tree", ground="opaque", palette="fixed")
        declared = "--dna-ink-icon:" in svg
        consumed = "var(--dna-ink-icon" in svg
        assert declared == consumed
        assert consumed, "tree's kind marks should ride the pre-blended icon token"

    def test_adaptive_far_block_repaints_the_icon_token(self) -> None:
        svg = _compose("tree")
        css = _styles(svg)
        near = re.findall(r"--dna-ink-icon:\s*(#[0-9A-Fa-f]{6})", css.split("@media")[0])
        far = re.findall(r"--dna-ink-icon:\s*(#[0-9A-Fa-f]{6})", _dark_blocks(css))
        assert near and far and near[0] != far[0], "icon token must flip with the face"


class TestTspanConsolidation:
    def test_multiline_desc_stacks_are_one_text_element(self) -> None:
        diagram = {
            "topology": "pipeline",
            "node_style": "card+label",
            "nodes": [
                {"label": "fetch", "desc": "1.2M docs\n14 sources"},
                {"label": "index", "desc": "1536 dims\n8k batch", "role": "hero"},
                {"label": "serve", "desc": "p50 42ms\np99 210ms"},
            ],
        }
        svg = compose(ComposeSpec(type="diagram", genome_id="primer", diagram=diagram)).svg
        body = re.sub(r"<style\b[^>]*>.*?</style>", "", svg, flags=re.DOTALL)
        stacks = re.findall(r"<text[^>]*class=\"[^\"]*-[nh]val[^\"]*\"[^>]*>(.*?)</text>", body, re.DOTALL)
        assert stacks, "no value stacks rendered"
        for stack in stacks:
            assert stack.count("<tspan") == 2, f"two desc lines should be two tspans in one text: {stack!r}"
