"""G5 v3 — the backing-aware glyph contrast gate.

Plate tokens are a SET-LEVEL invariant: a layout's glyph-circle class is
plateless together or on one shared plate — never a per-node checkerboard.
The ladder: (0) plateless when every gated mark reads on the paper (WCAG
ratio or chromatic distinctness), (1) one uniform class plate, (2) tint
degradation toward ink. Ink is exempt; brand colors are never altered;
per-node outcomes ship in the payload's rendered block.
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


def circle_fills(svg: str) -> set[str]:
    """The style-fill treatment of every node circle (the coin class)."""
    fills = set()
    for m in re.finditer(r'<circle[^>]*class="[^"]*(?:cardbg|herobg)[^"]*"[^>]*>', svg):
        s = re.search(r'style="fill:([^"]+)"', m.group(0))
        fills.add(s.group(1) if s else "default")
    return fills


class TestSetCohesion:
    def test_one_key_goes_plateless_on_dusk(self) -> None:
        # Step 0 proof: every One Key mark reads on dusk's paper (HF's
        # yellow through chroma) — the whole coin set drops its fill; the
        # round-2 lone dark coin and an ink downgrade are both wrong here.
        svg = compose_preset("model-router", "dusk")
        rendered = rendered_of(svg)
        assert rendered["glyph_backing"][8] == "plateless"  # HF, full color intact
        # R1 — full means full: HF carries a color_paths master now; the
        # old assertion blessed the silhouette degradation and was the bug.
        assert rendered["glyph_tint"][8] == "full"
        assert circle_fills(svg) == {"none"}  # the entire class, uniformly

    def test_frontier_handoff_uniform_plate_on_noir(self) -> None:
        # Step 1 proof: GPT/Ollama black fails noir's paper -> ONE light
        # plate set-wide; Gemini rides it; the ink hero takes counter-ink.
        svg = compose_preset("frontier-relay", "noir")
        rendered = rendered_of(svg)
        backing = rendered["glyph_backing"]
        assert backing[0] == backing[2] == backing[3] == "plate-light"
        assert backing[1] == "plate-light"  # the ink hero rides the class plate
        assert rendered["glyph_tint"][1] == "ink"
        assert circle_fills(svg) == {"#FFFFFF"}  # uniform — no checkerboard
        assert 'fill="#141414"' in svg  # the hero mark's counter-ink on the light plate

    def test_class_treatment_never_varies_within_a_layout(self) -> None:
        """The cohesion law as a property: across every preset on every
        paper, the coin class carries at most ONE fill treatment."""
        for variant in ("porcelain", "noir", "dusk", "space"):
            for preset in sorted(diagram_preset_names()):
                svg = compose_preset(preset, variant)
                assert len(circle_fills(svg)) <= 1, (preset, variant, circle_fills(svg))

    def test_ink_only_classes_keep_their_canon_coins(self) -> None:
        # No gated marks -> no remedy: pipeline-relay's ink coins stay
        # chassis-filled (the gate is a contrast remedy, not a restyle).
        svg = compose_preset("pipeline-relay", "porcelain")
        rendered = rendered_of(svg)
        assert circle_fills(svg) == {"default"}
        assert all(b in ("", "exempt-ink") for b in rendered["glyph_backing"])


class TestLadder:
    def test_chroma_relief_is_paper_specific(self) -> None:
        # Yellow reads on dusk's warm pink through hue, not luminance; on
        # noir's near-black it reads through luminance outright.
        assert contrast_ratio("#FFD21E", "#F6ECF0") < 3.0  # fails plain WCAG on dusk
        assert contrast_ratio("#FFD21E", "#0A0A0A") > 3.0
        # Black on noir paper fails BOTH ratio and chroma -> plates.
        assert contrast_ratio("#000000", "#0A0A0A") < 1.2

    def test_threshold_and_relief_are_engine_config(self) -> None:
        from hyperweave.config.loader import load_diagram_config

        cfg = load_diagram_config()["glyph_contrast"]
        assert float(cfg["threshold"]) == 3.0
        assert float(cfg["chroma_floor"]) == 120
        assert float(cfg["chroma_lum_floor"]) == 1.2

    def test_no_marks_means_empty_outcomes(self) -> None:
        svg = compose_preset("order-lifecycle", "porcelain")
        rendered = rendered_of(svg)
        assert all(b == "" for b in rendered["glyph_backing"])

    def test_outcome_vocabulary(self) -> None:
        for preset, variant in (
            ("model-router", "dusk"),
            ("frontier-relay", "noir"),
            ("rag-pipeline", "space"),
            ("inference-serving", "cream"),
        ):
            rendered = rendered_of(compose_preset(preset, variant))
            for outcome in rendered["glyph_backing"]:
                assert outcome in ("", "default", "exempt-ink", "plateless", "plate-light", "plate-dark") or (
                    outcome.startswith("tint-")
                ), outcome
