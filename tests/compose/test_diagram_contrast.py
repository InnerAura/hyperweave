"""The backing-aware glyph contrast gate.

Neither node shape carries a plate: a card's mark checks against the card
surface; a circle carries no independent backing and sits bare on the paper,
checking directly against it. The ladder for both: (0) the mark reads
directly on its surface — full color, unchanged — (1) tint degradation
toward ink (brand, then ink), decided per node. Ink is exempt; brand colors
are never altered; per-node outcomes ship in the payload's rendered block.
"""

from __future__ import annotations

import json
import re

from hyperweave.compose.diagram.input import diagram_preset_names, resolve_diagram_preset
from hyperweave.compose.engine import compose
from hyperweave.core.color import contrast_ratio
from hyperweave.core.models import ComposeSpec

_PAYLOAD_RE = re.compile(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>", re.DOTALL)


def rendered_of(svg: str) -> dict:
    m = _PAYLOAD_RE.search(svg)
    assert m, "hw:payload missing"
    return json.loads(m.group(1))["rendered"]


def compose_preset(name: str, variant: str, **overrides: object) -> str:
    payload = dict(resolve_diagram_preset(name), **overrides)
    spec = ComposeSpec(type="diagram", genome_id="primer", variant=variant, diagram=payload)
    return compose(spec).svg


def compose_inline(payload: dict, variant: str) -> str:
    spec = ComposeSpec(type="diagram", genome_id="primer", variant=variant, diagram=payload)
    return compose(spec).svg


# The glyph-contrast gate is a glyph-circle (coin) feature; the P6 parity library
# renders zero coins (every specimen census is coins:0), so the gate is exercised
# on inline glyph-circle specs — recreations of the deleted coin presets.
_MODEL_ROUTER_COINS = {
    "topology": "fanout",
    "orientation": "radial",
    "node_style": "glyph-circle",
    "glyph_tint": "full",
    "nodes": [
        {"label": "router", "short": "api", "role": "hero"},
        {"label": "OpenAI", "glyph": "openai"},
        {"label": "Anthropic", "glyph": "anthropic"},
        {"label": "Gemini", "glyph": "gemini"},
        {"label": "Mistral", "glyph": "mistral"},
        {"label": "DeepSeek", "glyph": "deepseek"},
        {"label": "Qwen", "glyph": "qwen"},
        {"label": "Ollama", "glyph": "ollama"},
        {"label": "HF", "glyph": "huggingface"},
    ],
}
_FRONTIER_RELAY_COINS = {
    "topology": "pipeline",
    "node_style": "glyph-circle",
    "glyph_tint": "full",
    "nodes": [
        {"label": "GPT", "glyph": "openai"},
        {"label": "Claude", "glyph": "anthropic", "role": "hero", "glyph_tint": "ink"},
        {"label": "Gemini", "glyph": "gemini"},
        {"label": "Ollama", "glyph": "ollama"},
    ],
}
_PIPELINE_RELAY_COINS = {
    "topology": "pipeline",
    "node_style": "glyph-circle",
    "nodes": [
        {"label": "agent", "glyph": "claude"},
        {"label": "hw compose", "short": "hw", "role": "hero"},
        {"label": "artifact", "glyph": "hyperweave"},
        {"label": "surface", "glyph": "github"},
    ],
}
_MARKLESS = {
    "topology": "pipeline",
    "nodes": [
        {"id": "a", "label": "queued"},
        {"id": "b", "label": "running", "role": "hero"},
        {"id": "c", "label": "done"},
    ],
}


def circle_fill_rules(svg: str) -> set[str]:
    """The CSS ``fill`` declared for every node-circle background class
    present in the document (``circlebg``/``herocirclebg``/``cardbg``/
    ``herobg``) — circles never carry an inline style override anymore, so
    the class rule IS the treatment."""
    fills = set()
    for cls in ("circlebg", "herocirclebg"):
        for m in re.finditer(r"-" + cls + r" \{ ([^}]*)\}", svg):
            decl = m.group(1)
            fm = re.search(r"fill:\s*([^;]+);", decl)
            fills.add(fm.group(1).strip() if fm else "")
    return fills


class TestBareCircles:
    def test_circles_never_carry_an_inline_fill(self) -> None:
        """No node circle ever gets a ``style="fill:...` override — the mark
        either reads full-color on the bare paper or degrades in place;
        there is no backing plate to swap onto."""
        svg = compose_inline(_MODEL_ROUTER_COINS, "noir")
        for m in re.finditer(r"<circle[^>]*class=\"[^\"]*(?:circlebg|herocirclebg)[^\"]*\"[^>]*>", svg):
            assert "style=" not in m.group(0), m.group(0)

    def test_circlebg_classes_are_fill_none(self) -> None:
        """The circle background classes are bare rings — fill: none — on
        every variant; only the stroke (border vs signal) differs."""
        for variant in ("porcelain", "noir", "dusk", "space"):
            svg = compose_inline(_MODEL_ROUTER_COINS, variant)
            assert circle_fill_rules(svg) == {"none"}, (variant, circle_fill_rules(svg))

    def test_one_key_full_color_reads_on_dusk_paper(self) -> None:
        # HF's yellow reads on dusk's paper (through chroma) — full color,
        # unchanged, no plate involved.
        svg = compose_inline(_MODEL_ROUTER_COINS, "dusk")
        rendered = rendered_of(svg)
        assert rendered["glyph_backing"][8] == "plateless"  # HF, full color intact
        assert rendered["glyph_tint"][8] == "full"

    def test_frontier_handoff_degrades_per_node_on_noir(self) -> None:
        # GPT/Ollama black fails noir's near-black paper and degrades toward
        # ink INDIVIDUALLY — no shared plate, no class-wide swap. Gemini's
        # multicolor gradient reads fine on its own (plateless); the hero
        # opts into ink explicitly and is exempt from the gate entirely.
        svg = compose_inline(_FRONTIER_RELAY_COINS, "noir")
        rendered = rendered_of(svg)
        backing = rendered["glyph_backing"]
        assert backing[0] == "tint-ink"  # GPT
        assert backing[1] == "exempt-ink"  # Claude, the ink hero
        assert backing[2] == "plateless"  # Gemini, reads on noir unaided
        assert backing[3] == "tint-ink"  # Ollama
        assert rendered["glyph_tint"][1] == "ink"

    def test_ink_only_classes_render_bare_with_no_remedy(self) -> None:
        # No gated marks -> no remedy: pipeline-relay's ink coins stay
        # bare-ring (the gate is a contrast remedy, not a restyle).
        svg = compose_inline(_PIPELINE_RELAY_COINS, "porcelain")
        rendered = rendered_of(svg)
        assert circle_fill_rules(svg) <= {"none"}
        assert all(b in ("", "exempt-ink") for b in rendered["glyph_backing"])


class TestLadder:
    def test_chroma_relief_is_paper_specific(self) -> None:
        # Yellow reads on dusk's warm pink through hue, not luminance; on
        # noir's near-black it reads through luminance outright.
        assert contrast_ratio("#FFD21E", "#F6ECF0") < 3.0  # fails plain WCAG on dusk
        assert contrast_ratio("#FFD21E", "#0A0A0A") > 3.0
        # Black on noir paper fails BOTH ratio and chroma -> degrade.
        assert contrast_ratio("#000000", "#0A0A0A") < 1.2

    def test_threshold_and_relief_are_engine_config(self) -> None:
        from hyperweave.config.loader import load_diagram_config

        cfg = load_diagram_config()["glyph_contrast"]
        assert float(cfg["threshold"]) == 3.0
        assert float(cfg["chroma_floor"]) == 120
        assert float(cfg["chroma_lum_floor"]) == 1.2

    def test_no_marks_means_empty_outcomes(self) -> None:
        svg = compose_inline(_MARKLESS, "porcelain")
        rendered = rendered_of(svg)
        assert all(b == "" for b in rendered["glyph_backing"])

    def test_outcome_vocabulary(self) -> None:
        for preset, variant in (
            ("model-router", "dusk"),
            ("reverse-etl", "noir"),
            ("rag-pipeline", "space"),
            ("service-dependencies", "cream"),
        ):
            rendered = rendered_of(compose_preset(preset, variant))
            for outcome in rendered["glyph_backing"]:
                assert outcome in ("", "default", "exempt-ink", "plateless") or (outcome.startswith("tint-")), outcome

    def test_every_diagram_preset_renders_clean_on_every_variant(self) -> None:
        """Property test standing in for the old class-cohesion law: with no
        plate to keep consistent across a class, the only invariant left is
        that every preset composes without error on every paper."""
        for variant in ("porcelain", "noir", "dusk", "space"):
            for preset in sorted(diagram_preset_names()):
                compose_preset(preset, variant)  # raises on failure


class TestLaw2FillCoverage:
    def test_every_text_class_carries_a_fill_rule(self) -> None:
        """LAW 2 structural pin: a voice class with no fill rule inherits SVG
        default BLACK — invisible on dark grounds (the carbon black-on-black
        annotation defect). Render annotation-heavy + lanes + sequence
        artifacts and assert every emitted <text class> has a fill rule in
        the same document."""
        import re

        from hyperweave.compose.diagram.input import resolve_diagram_preset
        from hyperweave.compose.engine import compose
        from hyperweave.core.models import ComposeSpec

        for preset in ("hub", "obi-engine", "auth-sequence", "dep-audit"):
            svg = compose(
                ComposeSpec(
                    type="diagram", genome_id="primer", variant="carbon", diagram=resolve_diagram_preset(preset)
                )
            ).svg
            classes = set()
            for m in re.finditer(r'<text[^>]*class="(hw-[0-9a-f]+)-([a-z]+)', svg):
                classes.add((m.group(1), m.group(2)))
            assert classes, preset
            for uid, cls in sorted(classes):
                pat = re.compile(r"\." + re.escape(f"{uid}-{cls}") + r"\b[^}]*")
                rules = " ".join(m.group(0) for m in pat.finditer(svg))
                assert "fill" in rules, (preset, cls, "no fill rule — inherits black")


class TestLaw3PaletteDerivation:
    def test_undeclared_specs_render_single_accent_hue(self) -> None:
        """LAW 3: with no declared roles/categories/explicit accents, every
        particle and dot rides the VARIANT ACCENT — one hue, tonal with the
        muted wire. Porcelain never again renders green+orange particles
        that exist nowhere in its palette."""
        import json
        import pathlib
        import re

        from hyperweave.compose.diagram.input import resolve_diagram_preset
        from hyperweave.compose.engine import compose
        from hyperweave.core.models import ComposeSpec

        genome = json.loads(pathlib.Path("src/hyperweave/data/genomes/primer.json").read_text())
        for preset in ("rag-pipeline", "reverse-etl", "tree", "convergence"):
            spec_d = resolve_diagram_preset(preset)
            svg = compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=spec_d)).svg
            # Every flow class the artifact declares binds the accent hex —
            # no universal-constant hues.
            flow_hexes = set(re.findall(r"-fl(?:p)?\d+ \{ (?:stroke|fill): (#[0-9A-Fa-f]{6})", svg))
            accent = genome["variant_overrides"]["porcelain"].get("accent", genome.get("accent"))
            assert flow_hexes <= {accent}, (preset, flow_hexes, accent)

    def test_declared_roles_earn_the_flow_palette(self) -> None:
        """Hub edge roles / lanes categories are DECLARED semantics — the
        multi-hue flow palette engages for them (per-variant genome data)."""
        import re

        from hyperweave.compose.diagram.input import resolve_diagram_preset
        from hyperweave.compose.engine import compose
        from hyperweave.core.models import ComposeSpec

        svg = compose(
            ComposeSpec(
                type="diagram", genome_id="primer", variant="porcelain", diagram=resolve_diagram_preset("obi-engine")
            )
        ).svg
        flow_classes = set(re.findall(r"-fl(\d+) \{", svg))
        assert len(flow_classes) >= 3, flow_classes  # categorical hues engaged
