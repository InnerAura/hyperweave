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


def compose_fixture(name: str, *, variant: str = "porcelain", **diagram_overrides: Any) -> str:
    spec = ComposeSpec(
        type="diagram", genome_id="primer", variant=variant, diagram={**load_fixture(name), **diagram_overrides}
    )
    return compose(spec).svg


class TestByteDeterminism:
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
        # The payload stays CHROME-INVARIANT (the envelope digest is artifact
        # identity; chrome sits outside it) — the §2 region map rides its own
        # hw:regions sidecar instead.
        assert set(body) == {"spec", "rendered"}
        regions_m = re.search(r"<hw:regions[^>]*><!\[CDATA\[(.*?)\]\]></hw:regions>", svg, re.DOTALL)
        assert regions_m, "hw:regions sidecar missing"
        region_ids = [r["id"] for r in json.loads(regions_m.group(1))]
        assert "content" in region_ids
        spec = DiagramSpec.model_validate(body["spec"])
        assert spec.topology.value == "sequence"
        rendered = body["rendered"]
        assert rendered["performance"] in ("composite-only", "paint-ok")
        assert len(rendered["edge_motion"]) == len(spec.edges)
        assert len(rendered["track"]) == len(spec.edges)
        assert rendered["fallback_applied"] is False
        # Calls stay static (kind semantics own the sequence stroke); returns
        # deliberately supersede the P3 static-yield law and drift home on
        # their own track value instead.
        assert set(rendered["track"]) == {"static", "dash-drift"}

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
        # Particles are opt-in (the genome default edge motion is dash, not
        # particle, under the diagrams-v3 kit) — request them explicitly.
        svg = compose_fixture("pipeline", edge_motion="particle")
        assert re.search(r'<circle class="hw-[0-9a-f]{8}-p[^"]*"[^>]*opacity="0"', svg)

    def test_reduced_motion_block_present(self) -> None:
        svg = compose_fixture("pipeline")
        assert "prefers-reduced-motion" in svg
        assert "display: none" in svg

    def test_non_adaptive_diagram_classes(self) -> None:
        # The palette layer's id-scoped var swap (#uid { --dna-... }) is the
        # ONLY adaptive machinery (primer defaults to twin now); the diagram
        # TEMPLATES must add no adaptive block of their own — no uid-prefixed
        # CLASS selector may appear inside any prefers-color-scheme body.
        svg = compose_fixture("pipeline")
        uid = re.search(r'id="(hw-[0-9a-f]{8})-lift"', svg).group(1)  # type: ignore[union-attr]
        for m in re.finditer(r"@media[^{]*prefers-color-scheme[^{]*\{", svg):
            depth, i = 1, m.end()
            while depth and i < len(svg):
                depth += {"{": 1, "}": -1}.get(svg[i], 0)
                i += 1
            assert f".{uid}-" not in svg[m.end() : i]

    def test_sequence_uses_single_traversing_particle(self) -> None:
        # The sequence-replay law: ONE persistent dot hops message-to-message in replay
        # order — a single particle (keyPoints hold/travel/hold per slot),
        # not per-message gradient comets. No animateTransform for sequence.
        # Particles are opt-in under the diagrams-v3 kit's dash default.
        svg = compose_fixture("sequence", edge_motion="particle")
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
        # return = accent dash-drift (not faded to the motion tube) — its
        # dasharray rides the -retdrift CSS class, not an inline attribute,
        # so the animation applies uniformly. The fixture alternates call /
        # return.
        svg = compose_fixture("sequence")
        conns = re.findall(r'<path id="[^"]*-c\d+"[^>]*/>', svg)
        drifting = ["-retdrift" in c for c in conns]
        assert drifting == [False, True, False, True]  # call, return, call, return
        assert "-tube" not in "".join(conns)  # calls keep their hue, never the faint tube

    def test_sequence_particles_share_one_loop_period(self) -> None:
        # Loop coherence: every message dot rides ONE common period (sum of
        # slots + gaps + rest) so the trace replays in unison. Particles are
        # opt-in under the diagrams-v3 kit's dash default.
        svg = compose_fixture("sequence", edge_motion="particle")
        durs = set(re.findall(r'<animateMotion[^>]*dur="([^"]*)"', svg))
        assert len(durs) == 1, durs


class TestChromatic:
    @pytest.mark.parametrize("variant", ["noir", "carbon", "space", "anvil", "porcelain", "cream", "dusk", "petrol"])
    def test_all_eight_variants_render(self, variant: str) -> None:
        svg = compose_fixture("pipeline", variant=variant)
        assert 'data-hw-type="diagram"' in svg

    def test_per_variant_flow_palette_binds(self) -> None:
        # LAW 3 + the anti-leak regression: the flow palette is DERIVED per
        # variant from its accent (compose/diagram/palette.py), so each
        # variant's spine reads in its OWN hue. Porcelain's cobalt must NOT
        # bleed onto a warm variant — the cobalt-on-cream bug where a copied
        # diagram_flow array smeared one variant's blue across every light
        # variant. Proven on a categorical spec so the flow palette engages.
        from hyperweave.compose.diagram.input import resolve_diagram_preset
        from hyperweave.config.loader import load_genomes

        genome = load_genomes()["primer"]
        d = resolve_diagram_preset("obi-engine")
        porc_accent = genome.variant_overrides["porcelain"]["accent"]  # cobalt #1D4ED8
        cream_accent = genome.variant_overrides["cream"]["accent"]  # warm brown #2C2014
        light = compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=d)).svg
        cream = compose(ComposeSpec(type="diagram", genome_id="primer", variant="cream", diagram=d)).svg
        # Each variant's spine accent (flow slot 0) is its OWN accent.
        assert porc_accent in light
        assert cream_accent in cream
        # No leak: porcelain's cobalt never appears anywhere on the cream render.
        assert porc_accent not in cream

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
        # Particles are opt-in under the diagrams-v3 kit's dash default.
        svg = compose_fixture("fanout-radial", edge_motion="particle")
        last_particle = max(m.start() for m in re.finditer(r'class="hw-[0-9a-f]{8}-p ', svg))
        # The hub is the only hero node — it must paint after every
        # particle so the spokes emanate from under its card.
        hub_node = max(m.start() for m in re.finditer(r'<(?:circle|rect) [^>]*-herobg"', svg))
        assert hub_node > last_particle

    def test_stack_operators_render(self) -> None:
        # The operator is drawn geometry (a quiet ring + cross, stack),
        # never a floating multiply-sign character — three marks between the 4 layers.
        svg = compose_fixture("stack")
        assert svg.count('r="11.0"') == 3
        assert svg.count('-cardbg"/><path d="M ') == 3

    def test_state_machine_furniture(self) -> None:
        svg = compose_fixture("state-machine")
        # Terminal chrome renders ONLY for an authored ``terminal: true``
        # (the agent-task-lifecycle double-ring law) — the implicit TERMINAL
        # text tag died with the retired pill anatomy, and this fixture
        # authors no terminal.
        assert '-term"' not in svg
        assert "-idot" in svg and "-stub" in svg
        assert "review ✓" in svg

    def test_sequence_furniture(self) -> None:
        # auth-sequence anatomy: the fixture's one hero ("hw") gets the accent
        # lifeline/activation (2 of 3 lifelines stay the plain neutral
        # class); returns drift on their own track; the left-margin time
        # axis and the top-right call/return mini-legend both render.
        svg = compose_fixture("sequence")
        assert svg.count('-life"') == 2
        assert "-lifeh" in svg
        assert "-retdrift" in svg
        assert "-taxis" in svg and ">time</text>" in svg
        assert ">call</text>" in svg and ">return</text>" in svg

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


class TestReasoningMetadata:
    def test_tier3_tradeoffs_present(self) -> None:
        svg = compose_fixture("pipeline")
        m = re.search(r"<hw:tradeoffs>(.*?)</hw:tradeoffs>", svg, re.DOTALL)
        assert m and len(m.group(1).strip()) > 20


class TestSolverRegistryOrderIndependence:
    """The solver registry is process-global and populated at solver-module
    import. Its accessor must GUARANTEE that population — a caller hitting
    ``registered_slugs()`` before the package ``__init__`` imported the solvers
    (an unlucky pytest-randomly ordering) must still see the full set, or the
    slug-count gates flake."""

    def test_registered_slugs_full_from_bare_solver_import(self) -> None:
        # A FRESH interpreter imports ONLY solver.py (never the package
        # __init__ that eagerly imports the solvers) and asks for the slugs.
        # This reproduces the flake condition; the accessor self-imports the
        # solver modules, so the count is the full 18 regardless of order.
        import subprocess
        import sys

        code = (
            "from hyperweave.compose.diagram.solver import registered_slugs\n"
            "s = registered_slugs()\n"
            "assert len(s) == 18, f'expected 18, got {len(s)}: {sorted(s)}'\n"
            "assert {'hub', 'lanes'} <= set(s), sorted(s)\n"
            "print('ok')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "ok"

    def test_registered_slugs_idempotent(self) -> None:
        from hyperweave.compose.diagram.solver import registered_slugs

        assert registered_slugs() == registered_slugs()
        assert len(registered_slugs()) == 18


class TestConnectorPalette:
    """The connector-palette knob (chrome): MUTED static/dash wires are the
    default; 'colored' opts back into the five-hue flow palette."""

    def test_default_omits_knob_from_payload(self) -> None:
        """connector_palette='' is excluded from the payload (byte-safe round-trip)."""
        svg = compose_fixture("dag")
        m = _PAYLOAD_RE.search(svg)
        assert m
        spec = json.loads(m.group(1))["spec"]
        assert "connector_palette" not in spec  # exclude_defaults keeps old payloads identical

    def test_default_is_muted(self) -> None:
        """The DEFAULT (no knob) quiets static/dash wires — colored is opt-in
        chrome, not the baseline (the wire-rainbow review decision)."""
        svg = compose_fixture("dag")
        assert "-connmuted {" in svg
        assert "#A9B4C6" in svg  # porcelain's muted wire tone

    def test_colored_opts_back_into_hue(self) -> None:
        """connector_palette='colored' restores the genome flow palette."""
        d = {**load_fixture("dag"), "connector_palette": "colored"}
        svg = compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=d)).svg
        assert "-connmuted {" not in svg

    def _muted_svg(self) -> str:
        d = {**load_fixture("dag"), "connector_palette": "muted"}
        return compose(ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", diagram=d)).svg

    def test_muted_rides_the_payload_and_round_trips(self) -> None:
        """A muted request persists in the payload and re-validates as the knob."""
        m = _PAYLOAD_RE.search(self._muted_svg())
        assert m
        spec = DiagramSpec.model_validate(json.loads(m.group(1))["spec"])
        assert spec.connector_palette == "muted"

    def test_muted_emits_the_neutral_class(self) -> None:
        """Muted wires reference the neutral connector class in the artifact."""
        svg = self._muted_svg()
        assert "-connmuted {" in svg  # the neutral class is declared
        assert "#A9B4C6" in svg  # porcelain's muted wire tone

    def test_muted_absent_no_warning(self) -> None:
        """A plain muted request (no beam/flow) emits no warning."""
        result = compose(
            ComposeSpec(
                type="diagram",
                genome_id="primer",
                variant="porcelain",
                diagram={**load_fixture("dag"), "connector_palette": "muted"},
            )
        )
        assert result.warnings == []


def test_dark_face_circle_boundary_is_visible() -> None:
    """diagram_dark.border is the plateless boundary stroke: a glyph-circle
    node's outline once rode edge_faint (a 7%-alpha bevel stop) and vanished
    on noir. The override block must map --dna-border to the 28% boundary."""
    import json as _json
    import re as _re
    from importlib import resources

    from hyperweave.core.models import ComposeSpec

    genome = _json.loads(resources.files("hyperweave.data.genomes").joinpath("primer.json").read_text())
    noir = genome["variant_overrides"]["noir"]["diagram_dark"]
    spec = {
        "title": "relay",
        "topology": "pipeline",
        "node_style": "glyph-circle",
        "nodes": [
            {"id": "a", "label": "monitor", "kind": "activity"},
            {"id": "b", "label": "oncall", "kind": "users"},
            {"id": "c", "label": "lead", "kind": "shield"},
        ],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
    }
    svg = compose(
        ComposeSpec(
            type="diagram", genome_id="primer", variant="noir", surface_face="dark", ground="opaque", diagram=spec
        )
    ).svg
    m = _re.search(r"--dna-border: (rgba\([^)]+\))", svg)
    assert m, "dark override block missing --dna-border"
    assert m.group(1) == noir["border"], m.group(1)
    assert noir["edge_faint"] != m.group(1), "boundary must not ride the bevel stop"
