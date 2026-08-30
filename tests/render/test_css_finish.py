"""The emit-time CSS gates + the finishing pass's behavior contract.

Session-A measurement: a committed artifact declared 76% dead classes; an
adaptive artifact declared every token 4x across 6 dark media blocks. The
finishing pass (``render/css_finish.py``) closes both. These gates hold the
EMITTED artifact to the claim — extraction here is independent regex over the
shipped bytes, never the finisher's own internals (Guard Law).
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_diagram_presets
from hyperweave.core.models import ComposeSpec
from hyperweave.render.css_finish import finish_css

MOCK_CHART = {
    "points": [
        {"date": "2025-01-01T00:00:00Z", "count": 100},
        {"date": "2025-07-01T00:00:00Z", "count": 680},
        {"date": "2026-01-01T00:00:00Z", "count": 5200},
        {"date": "2026-04-01T00:00:00Z", "count": 9400},
    ],
    "current_stars": 9400,
    "repo": "acme/widgets",
}


def _corpus() -> list[tuple[str, str]]:
    presets = load_diagram_presets()
    named: list[tuple[str, ComposeSpec]] = [
        ("badge-adaptive", ComposeSpec(type="badge", genome_id="brutalist", title="BUILD", value="passing")),
        ("badge-chrome", ComposeSpec(type="badge", genome_id="chrome", title="PULLS", value="135.9M")),
        ("marquee", ComposeSpec(type="marquee", genome_id="brutalist", title="HW|TEST")),
        ("chart", ComposeSpec(type="chart", genome_id="primer", connector_data=MOCK_CHART)),
        (
            "diagram-adaptive",
            ComposeSpec(type="diagram", genome_id="primer", diagram=dict(load_diagram_presets()["loop-retry-budget"])),
        ),
        (
            "diagram-fixed",
            ComposeSpec(
                type="diagram", genome_id="primer", ground="opaque", palette="fixed", diagram=dict(presets["dag-gate"])
            ),
        ),
    ]
    return [(name, compose(spec).svg) for name, spec in named]


@pytest.fixture(scope="module")
def corpus() -> list[tuple[str, str]]:
    return _corpus()


def _style_bodies(svg: str) -> list[str]:
    return re.findall(r"<style\b[^>]*>(.*?)</style>", svg, re.DOTALL)


def _without_styles(svg: str) -> str:
    return re.sub(r"<style\b[^>]*>.*?</style>", "", svg, flags=re.DOTALL)


_KEYFRAMES_BLOCK = re.compile(r"@(?:-webkit-)?keyframes\s+([\w-]+)\s*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}")


def _selector_preludes(css: str) -> list[str]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    css = _KEYFRAMES_BLOCK.sub("}", css)
    css = re.sub(r"@media[^{]*\{", "}", css)
    css = re.sub(r"@font-face\s*\{[^{}]*\}", "}", css)
    return [m.group(1).strip() for m in re.finditer(r"(?:^|\})\s*([^{}@]+)\{", css)]


class TestEmitTimeGates:
    def test_every_emitted_class_appears_in_the_body(self, corpus: list[tuple[str, str]]) -> None:
        for name, svg in corpus:
            body = _without_styles(svg)
            present: set[str] = set()
            for value in re.findall(r'class="([^"]*)"', body):
                present.update(value.split())
            for css in _style_bodies(svg):
                for prelude in _selector_preludes(css):
                    for cls in re.findall(r"\.([A-Za-z_][\w-]*)", prelude):
                        assert cls in present, f"{name}: emitted class .{cls} matches nothing in the body"

    def test_declared_tokens_are_consumed_tokens(self, corpus: list[tuple[str, str]]) -> None:
        # Every custom property an artifact declares is read somewhere in that
        # artifact — via var(), or offered as an override point by its own
        # hw:chromatic-surface contract. --hw-* is exempt: the state cascade
        # reads those by name at flatten time.
        for name, svg in corpus:
            consumed = set(re.findall(r"var\(\s*(--[\w-]+)", svg))
            for block in re.findall(r"<hw:chromatic-surface\b.*?(?:/>|</hw:chromatic-surface>)", svg, re.DOTALL):
                consumed.update(re.findall(r"--[\w-]+", block))
            declared = {
                prop
                for css in _style_bodies(svg)
                for prop in re.findall(r"(--[\w-]+)\s*:", css)
                if not prop.startswith("--hw-")
            }
            dead = declared - consumed
            assert not dead, f"{name}: declared but never consumed: {sorted(dead)}"

    def test_at_most_one_dark_block_per_stylesheet(self, corpus: list[tuple[str, str]]) -> None:
        for name, svg in corpus:
            for css in _style_bodies(svg):
                dark = re.findall(r"@media[^{]*prefers-color-scheme\s*:\s*dark", css)
                assert len(dark) <= 1, f"{name}: {len(dark)} dark media blocks in one stylesheet"

    def test_every_keyframes_is_referenced(self, corpus: list[tuple[str, str]]) -> None:
        for name, svg in corpus:
            all_css = "\n".join(_style_bodies(svg))
            declared = set(_KEYFRAMES_BLOCK.findall(all_css))
            referenced = set(re.findall(r"animation(?:-name)?\s*:\s*([\w-]+)", svg))
            orphans = declared - referenced
            assert not orphans, f"{name}: keyframes never animated: {sorted(orphans)}"

    def test_no_duplicate_property_in_the_adaptive_near_block(self, corpus: list[tuple[str, str]]) -> None:
        # The near block used to be a raw union of the genome layer and the
        # variant fan-out — the same token declared twice. Now: once.
        for name, svg in corpus:
            for m in re.finditer(r"#hw-[0-9a-f]{8}\s*\{([^{}]*)\}", "\n".join(_style_bodies(svg))):
                props = re.findall(r"(--[\w-]+)\s*:", m.group(1))
                dupes = {p for p in props if props.count(p) > 1}
                assert not dupes, f"{name}: property declared twice in one block: {sorted(dupes)}"

    def test_finishing_is_idempotent(self, corpus: list[tuple[str, str]]) -> None:
        for name, svg in corpus:
            assert finish_css(svg) == svg, f"{name}: a second finishing pass still found work"


_SHELL = (
    '<svg xmlns="http://www.w3.org/2000/svg" role="img"><style>{css}</style>'
    '<rect class="kept panel" id="root"/><text class="label" style="{inline}">x</text></svg>'
)


def _mini(css: str, inline: str = "") -> str:
    return finish_css(_SHELL.format(css=css, inline=inline))


class TestFinishingBehavior:
    def test_unused_class_rule_dropped_used_kept(self) -> None:
        out = _mini(".kept { fill: red; } .ghost { fill: blue; }")
        assert ".kept" in out and ".ghost" not in out

    def test_any_absent_class_token_kills_the_selector(self) -> None:
        # `.ghost .label` cannot match this document even though .label exists.
        out = _mini(".ghost .label { fill: red; } .kept .label { fill: blue; }")
        assert ".ghost .label" not in out and ".kept .label" in out

    def test_functional_pseudo_class_is_conservatively_kept(self) -> None:
        # :not(.ghost) matches precisely BECAUSE ghost is absent — never shake it.
        out = _mini("text:not(.ghost) { fill: red; }")
        assert ":not(.ghost)" in out

    def test_element_root_and_attribute_selectors_survive(self) -> None:
        css = ":root { --a: 1; } text { fill: var(--a); } [data-face] { opacity: 1; } * { stroke: none; }"
        out = _mini(css)
        for fragment in (":root", "text {", "[data-face]", "* {"):
            assert fragment in out

    def test_keyframes_kept_when_referenced_by_kept_rule(self) -> None:
        out = _mini("@keyframes spin { to { transform: rotate(1turn); } } .kept { animation: spin 2.618s linear; }")
        assert "@keyframes spin" in out

    def test_keyframes_kept_when_referenced_only_inline(self) -> None:
        out = _mini("@keyframes drift { to { opacity: 0; } }", inline="animation: drift 4.236s ease-out")
        assert "@keyframes drift" in out

    def test_keyframes_dropped_when_sole_referencing_rule_dropped(self) -> None:
        out = _mini("@keyframes gone { to { opacity: 0; } } .ghost { animation: gone 1s; }")
        assert "@keyframes gone" not in out and ".ghost" not in out

    def test_unconsumed_custom_property_dropped(self) -> None:
        out = _mini(".kept { --dead-token: #fff; fill: red; }")
        assert "--dead-token" not in out and "fill: red" in out

    def test_hw_prefixed_property_protected(self) -> None:
        out = _mini(".kept { --hw-state-build: 1; }")
        assert "--hw-state-build" in out

    def test_chromatic_surface_listing_counts_as_consumption(self) -> None:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg"><style>.kept { --dna-offered: #123; }</style>'
            '<metadata><hw:chromatic-surface xmlns:hw="https://hyperweave.app/hw/v1.0">'
            "--dna-offered</hw:chromatic-surface></metadata>"
            '<rect class="kept"/></svg>'
        )
        assert "--dna-offered" in finish_css(svg)

    def test_dark_blocks_consolidate_into_the_last(self) -> None:
        css = (
            "@media (prefers-color-scheme: dark) { .kept { fill: black; } }"
            ".kept { fill: white; }"
            "@media (prefers-color-scheme: dark) { .panel { stroke: gray; } }"
        )
        out = _mini(css)
        assert len(re.findall(r"prefers-color-scheme", out)) == 1
        merged = re.search(r"@media[^{]*dark[^{]*\{(.*)\}", _style_bodies(out)[0], re.DOTALL)
        assert merged is not None
        assert "fill: black" in merged.group(1) and "stroke: gray" in merged.group(1)
        # Base rule order preserved: the light .kept rule precedes the block.
        assert out.find("fill: white") < out.find("fill: black")

    def test_font_face_and_reduced_motion_survive_verbatim(self) -> None:
        css = (
            '@font-face { font-family: "Inter"; src: url(data:font/woff2;base64,AAAA); }'
            "@media (prefers-reduced-motion: reduce) { .ghost { animation: none !important; } }"
        )
        out = _mini(css)
        assert "@font-face" in out
        # Inside media the same shake applies — .ghost is gone, the block empties away.
        assert "prefers-reduced-motion" not in out

    def test_bytes_outside_style_untouched(self) -> None:
        svg = _SHELL.format(css=".ghost { fill: red; }", inline="")
        assert _without_styles(finish_css(svg)) == _without_styles(svg)
