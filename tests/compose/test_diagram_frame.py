"""End-to-end diagram frame gates: determinism, projections, motion anatomy,
chromatic binding, draw order, the rendered record (F1), and P4's documented
reading — the envelope id is ARTIFACT identity, so no test here may assert
cross-motion id stability.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from hyperweave.compose.diagram.input import diagram_preset_names, resolve_diagram_preset
from hyperweave.compose.engine import compose
from hyperweave.core.diagram import DiagramSpec
from hyperweave.core.envelope import envelope_id, validate_envelope
from hyperweave.core.models import ComposeSpec

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "diagram"
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_PAYLOAD_RE = re.compile(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>", re.DOTALL)
_ENVELOPE_RE = re.compile(r"<hw:envelope[^>]*><!\[CDATA\[(.*?)\]\]></hw:envelope>", re.DOTALL)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
        return datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / f"{name}.json").read_text())


def compose_fixture(name: str, *, variant: str = "porcelain", **kw: Any) -> str:
    spec = ComposeSpec(type="diagram", genome_id="primer", variant=variant, diagram=load_fixture(name), **kw)
    return compose(spec).svg


class TestByteDeterminism:
    def test_identical_bytes_with_pinned_clock(self) -> None:
        spec = ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=load_fixture("pipeline"))
        with patch("hyperweave.compose.context.datetime", _FrozenDatetime):
            assert compose(spec).svg == compose(spec).svg

    def test_no_random_tokens(self) -> None:
        assert not _UUID_RE.search(compose_fixture("pipeline"))

    def test_uid_stable_across_runs_distinct_across_specs(self) -> None:
        def uid(svg: str) -> str:
            m = re.search(r'id="(hw-[0-9a-f]{8})-lift"', svg)
            assert m
            return m.group(1)

        a1, a2 = uid(compose_fixture("pipeline")), uid(compose_fixture("pipeline"))
        b = uid(compose_fixture("pipeline", variant="noir"))
        c = uid(compose_fixture("convergence"))
        assert a1 == a2
        assert len({a1, b, c}) == 3


class TestEmbeddedProjections:
    def test_payload_round_trips_with_rendered_record(self) -> None:
        svg = compose_fixture("sequence")
        m = _PAYLOAD_RE.search(svg)
        assert m, "hw:payload missing"
        body = json.loads(m.group(1))
        assert set(body) == {"spec", "rendered"}
        spec = DiagramSpec.model_validate(body["spec"])
        assert spec.topology.value == "sequence"
        rendered = body["rendered"]
        assert rendered["performance"] in ("composite-only", "paint-ok")
        assert len(rendered["edge_motion"]) == len(spec.edges)
        assert len(rendered["track"]) == len(spec.edges)
        assert rendered["fallback_applied"] is False
        # P3 made the return messages static; calls are static too (kind
        # semantics own the sequence stroke).
        assert set(rendered["track"]) == {"static"}

    def test_envelope_validates_and_agrees_with_payload(self) -> None:
        svg = compose_fixture("fanout-radial")
        payload = _PAYLOAD_RE.search(svg)
        env_match = _ENVELOPE_RE.search(svg)
        assert payload and env_match
        envelope = json.loads(env_match.group(1))
        validate_envelope(envelope)
        assert envelope["k"] == "diagram"
        assert envelope["id"] == envelope_id(payload.group(1))
        assert "ttok" not in envelope
        data = envelope["data"]
        assert data["pattern"] == "fanout"
        assert data["n"] == 6
        # Presentational fields never reach the digest.
        for forbidden in ("orientation", "node_style", "glyph", "edge_motion", "entrance", "track"):
            assert forbidden not in data, forbidden

    def test_markdown_on_result_never_in_svg(self) -> None:
        spec = ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=load_fixture("pipeline"))
        result = compose(spec)
        assert result.markdown.startswith("**One Compositor")
        assert "Agent → Compositor" in result.markdown
        # The aria <desc> legitimately narrates flow lines; the markdown's
        # bullet formatting must never leak into the SVG.
        assert "- **Agent**" not in result.svg


class TestTopologyDispatch:
    @pytest.mark.parametrize("preset", sorted(diagram_preset_names()))
    def test_every_preset_composes_with_subvariant(self, preset: str) -> None:
        payload = resolve_diagram_preset(preset)
        spec = ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=payload)
        svg = compose(spec).svg
        assert 'data-hw-type="diagram"' in svg
        assert "data-hw-subvariant=" in svg
        assert "data-hw-topology=" in svg


class TestMotionAnatomy:
    def test_keyframes_and_classes_are_uid_prefixed(self) -> None:
        svg = compose_fixture("pipeline")
        m = re.search(r"@keyframes (hw-[0-9a-f]{8})-f", svg)
        assert m, "marching keyframes missing or unprefixed"

    def test_every_mpath_target_exists(self) -> None:
        svg = compose_fixture("convergence")
        for ref in re.findall(r'<mpath href="#([^"]+)"', svg):
            assert f'id="{ref}"' in svg, ref

    def test_particles_carry_base_opacity_zero(self) -> None:
        svg = compose_fixture("pipeline")
        assert re.search(r'<circle class="hw-[0-9a-f]{8}-p[^"]*"[^>]*opacity="0"', svg)

    def test_reduced_motion_block_present(self) -> None:
        svg = compose_fixture("pipeline")
        assert "prefers-reduced-motion" in svg
        assert "display: none" in svg

    def test_non_adaptive_diagram_classes(self) -> None:
        # The shared assembler stylesheet carries the platform's adaptive
        # var swap (every primer frame does); the diagram TEMPLATES must
        # add no adaptive block of their own — no uid-prefixed class may
        # appear inside any prefers-color-scheme body.
        svg = compose_fixture("pipeline")
        uid = re.search(r'id="(hw-[0-9a-f]{8})-lift"', svg).group(1)  # type: ignore[union-attr]
        for m in re.finditer(r"@media[^{]*prefers-color-scheme[^{]*\{", svg):
            depth, i = 1, m.end()
            while depth and i < len(svg):
                depth += {"{": 1, "}": -1}.get(svg[i], 0)
                i += 1
            assert uid not in svg[m.end() : i]

    def test_beam_animates_gradient_transform_only(self) -> None:
        svg = compose_fixture(
            "pipeline",
        )
        relay = compose(
            ComposeSpec(
                type="diagram",
                genome_id="primer",
                variant="porcelain",
                diagram={**load_fixture("pipeline"), "edge_motion": "beam"},
            )
        ).svg
        assert 'attributeName="gradientTransform"' in relay
        assert 'performance="paint-ok"' in relay
        # Geometry attributes never animate.
        for attr in ("cx", "cy", "r", "d", "x", "y", "width", "height"):
            assert f'attributeName="{attr}"' not in relay
        assert 'performance="composite-only"' in svg

    def test_sequence_uses_single_traversing_particle(self) -> None:
        # K-seq-v2: ONE persistent dot hops message-to-message in replay
        # order — a single particle (keyPoints hold/travel/hold per slot),
        # not per-message gradient comets. No animateTransform for sequence.
        svg = compose_fixture("sequence")
        assert 'attributeName="gradientTransform"' not in svg  # no comets
        assert 'keyPoints="0;0;1;1"' in svg  # the single-particle hold/travel pattern
        assert 'calcMode="linear"' in svg
        # One particle circle per message connector.
        connectors = re.findall(r'<path id="[^"]*-c\d+"', svg)
        motions = re.findall(r"<animateMotion", svg)
        assert len(connectors) >= 4
        assert len(motions) == len(connectors)
        # Geometry never animates — the dot rides a path via animateMotion.
        for attr in ("cx", "cy", "r", "d", "x", "y", "width", "height"):
            assert f'attributeName="{attr}"' not in svg

    def test_sequence_preserves_full_weight_call_return_strokes(self) -> None:
        # The messages stay at FULL weight beneath the dot: call = solid,
        # return = dashed (not faded to the motion tube). The fixture
        # alternates call / return.
        svg = compose_fixture("sequence")
        conns = re.findall(r'<path id="[^"]*-c\d+"[^>]*/>', svg)
        dashed = ["4 5" in c for c in conns]
        assert dashed == [False, True, False, True]  # call, return, call, return
        assert "-tube" not in "".join(conns)  # calls keep their hue, never the faint tube

    def test_sequence_particles_share_one_loop_period(self) -> None:
        # Loop coherence: every message dot rides ONE common period (sum of
        # slots + gaps + rest) so the trace replays in unison.
        svg = compose_fixture("sequence")
        durs = set(re.findall(r'<animateMotion[^>]*dur="([^"]*)"', svg))
        assert len(durs) == 1, durs


class TestChromatic:
    @pytest.mark.parametrize("variant", ["noir", "carbon", "space", "anvil", "porcelain", "cream", "dusk", "petrol"])
    def test_all_eight_variants_render(self, variant: str) -> None:
        svg = compose_fixture("pipeline", variant=variant)
        assert 'data-hw-type="diagram"' in svg

    def test_per_variant_flow_palette_binds(self) -> None:
        from hyperweave.config.loader import load_genomes

        genome = load_genomes()["primer"]
        light = compose_fixture("pipeline", variant="porcelain")
        dark = compose_fixture("pipeline", variant="noir")
        assert genome.variant_overrides["porcelain"]["diagram_flow"][0] in light
        assert genome.variant_overrides["noir"]["diagram_flow"][0] in dark

    def test_no_hex_literals_in_diagram_templates(self) -> None:
        template_dir = Path(__file__).parents[2] / "src" / "hyperweave" / "templates" / "frames" / "diagram"
        offenders: list[str] = []
        for path in template_dir.rglob("*.j2"):
            for i, line in enumerate(path.read_text().splitlines(), 1):
                for m in re.finditer(r"#[0-9a-fA-F]{6}\b", line):
                    offenders.append(f"{path.name}:{i}: {m.group(0)}")
        assert not offenders, offenders

    def test_unsupported_genome_raises(self) -> None:
        spec = ComposeSpec(type="diagram", genome_id="brutalist", diagram=load_fixture("pipeline"))
        with pytest.raises(ValueError, match="diagram frame is not supported"):
            compose(spec)


class TestDrawOrderAndFurniture:
    def test_radial_hub_paints_after_particles(self) -> None:
        svg = compose_fixture("fanout-radial")
        last_particle = max(m.start() for m in re.finditer(r'class="hw-[0-9a-f]{8}-p ', svg))
        # The hub is the only hero node — it must paint after every
        # particle so the spokes emanate from under its card.
        hub_node = max(m.start() for m in re.finditer(r'<(?:circle|rect) [^>]*-herobg"', svg))
        assert hub_node > last_particle

    def test_stack_operators_render(self) -> None:
        svg = compose_fixture("stack")
        assert svg.count(">×</text>") == 3  # noqa: RUF001 — the stack operator IS U+00D7

    def test_state_machine_furniture(self) -> None:
        svg = compose_fixture("state-machine")
        assert "TERMINAL" in svg
        assert "-idot" in svg and "-stub" in svg
        assert "review ✓" in svg

    def test_sequence_furniture(self) -> None:
        svg = compose_fixture("sequence")
        assert svg.count('-life"') == 3
        assert "SOLID = CALL" in svg

    def test_gateway_lanes_offset(self) -> None:
        svg = compose(
            ComposeSpec(
                type="diagram",
                genome_id="primer",
                variant="porcelain",
                diagram=resolve_diagram_preset("gateway"),
            )
        ).svg
        # Two reciprocal lanes per pair: four connector paths.
        assert len(re.findall(r'id="hw-[0-9a-f]{8}-c\d+"', svg)) == 4


class TestFallbackRecording:
    def test_requested_vs_rendered_never_silently_diverges(self) -> None:
        # The ladder is exercised at the wiring level (composite_only is a
        # resolver-level constraint seam); the payload records what drew.
        from hyperweave.compose.diagram import compute_diagram_layout
        from hyperweave.compose.diagram.input import resolve_auto_roles
        from hyperweave.config.loader import load_diagram_config, load_paradigms

        spec = resolve_auto_roles(DiagramSpec.model_validate({**load_fixture("pipeline"), "edge_motion": "beam"}))
        lay = compute_diagram_layout(
            spec,
            paradigm=load_paradigms()["primer"].diagram,
            engine=load_diagram_config(),
            palette_len=5,
            composite_only=True,
        )
        assert set(lay.rendered.edge_motion) == {"particle"}
        assert lay.rendered.fallback_applied is True
        assert lay.rendered.performance == "composite-only"


class TestReasoningMetadata:
    def test_tier3_tradeoffs_present(self) -> None:
        svg = compose_fixture("pipeline")
        m = re.search(r"<hw:tradeoffs>(.*?)</hw:tradeoffs>", svg, re.DOTALL)
        assert m and len(m.group(1).strip()) > 20
