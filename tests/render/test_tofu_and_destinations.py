"""Session-D emit-time gates: glyph coverage (tofu) + the destination contract.

- **Tofu gate**: every codepoint an artifact renders in ``<text>``/``<tspan>``
  exists in the union cmap of its own embedded font subsets. A missing glyph
  renders as tofu or a system-fallback face today with nothing to catch it —
  this gate is also the prerequisite the measured per-frame baseline rebuild
  stands on (insurance enforced loudly instead of rented in bytes).
  One documented exemption: U+25AE (the brutalist marquee separator bar) is
  absent from EVERY shipped font — it has always rendered via system fallback
  and belongs as drawn geometry, not a glyph (routed forward in the session
  record).
- **Destination contract**: the five profile ids are pinned at definition,
  every width carries a dated basis, and the scale gates return the verdicts
  the profile's own numbers dictate — including the true fact that a
  design-width diagram fails the legibility floor at GitHub's mobile column.
- **Face bake**: ``project(face=...)`` commits one face of an adaptive
  artifact — scheme queries resolve, the root's claims follow the bytes, and
  the two faces genuinely differ.
"""

from __future__ import annotations

import base64
import io
import re
from xml.etree import ElementTree as ET

import pytest
from fontTools.ttLib import TTFont

from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_destination_profiles, load_diagram_presets
from hyperweave.core.errors import HwError
from hyperweave.core.models import ComposeSpec
from hyperweave.formats import project
from hyperweave.formats.destinations import min_scale, scale_gates

_NS = "{http://www.w3.org/2000/svg}"
_UNCOVERABLE = {0x25AE}  # marquee separator bar: absent from every shipped font

_TOFU_SPECS: tuple[tuple[str, ComposeSpec], ...] = (
    ("badge", ComposeSpec(type="badge", genome_id="brutalist", title="BUILD", value="passing")),
    ("strip", ComposeSpec(type="strip", genome_id="primer", title="repo", value="STARS:1")),
    ("marquee", ComposeSpec(type="marquee", genome_id="brutalist", title="HW|TEST")),
    (
        "chart",
        ComposeSpec(
            type="chart",
            genome_id="primer",
            connector_data={
                "points": [
                    {"date": "2025-01-01T00:00:00Z", "count": 100},
                    {"date": "2026-01-01T00:00:00Z", "count": 9400},
                ],
                "current_stars": 9400,
                "repo": "acme/widgets",
            },
        ),
    ),
)


def _rendered_codepoints(svg: str) -> set[int]:
    out: set[int] = set()
    for el in ET.fromstring(svg).iter():
        if el.tag in (f"{_NS}text", f"{_NS}tspan") and el.text:
            out.update(ord(c) for c in el.text)
    return {cp for cp in out if cp != 0x20 and cp != 0x0A}


def _embedded_cmap(svg: str) -> set[int]:
    cps: set[int] = set()
    for b64 in re.findall(r"base64,([A-Za-z0-9+/=]+)", svg):
        cps.update(TTFont(io.BytesIO(base64.b64decode(b64))).getBestCmap().keys())
    return cps


class TestTofuGate:
    @pytest.mark.parametrize(("label", "spec"), _TOFU_SPECS, ids=[label for label, _ in _TOFU_SPECS])
    def test_every_rendered_codepoint_is_in_the_embedded_subset(self, label: str, spec: ComposeSpec) -> None:
        svg = compose(spec).svg
        cmap = _embedded_cmap(svg)
        if not cmap:
            pytest.skip(f"{label}: no embedded fonts (system font mode)")
        missing = _rendered_codepoints(svg) - cmap - _UNCOVERABLE
        assert not missing, f"{label}: tofu — rendered but not in the subset: {[hex(cp) for cp in sorted(missing)]}"

    def test_the_full_preset_corpus_is_tofu_free(self) -> None:
        # The FULL corpus, not a sample — a 3-preset spot check missed five
        # presets whose chip, legend, and tint text rode fields the subsetter
        # never saw (review finding, 2026-08-30).
        failures: list[str] = []
        for preset, payload in sorted(load_diagram_presets().items()):
            svg = compose(
                ComposeSpec(type="diagram", genome_id="primer", ground="opaque", palette="fixed", diagram=dict(payload))
            ).svg
            cmap = _embedded_cmap(svg)
            assert cmap, f"{preset}: diagram must embed its fonts"
            missing = _rendered_codepoints(svg) - cmap - _UNCOVERABLE
            if missing:
                failures.append(f"{preset}: {[hex(cp) for cp in sorted(missing)]}")
        assert not failures, "tofu in the preset corpus:\n" + "\n".join(failures)


class TestDestinationContract:
    def test_the_five_profile_ids_are_pinned(self) -> None:
        assert set(load_destination_profiles()) == {
            "standalone",
            "github-readme",
            "landing-hero",
            "slides",
            "chat-raster",
        }

    def test_every_profile_states_a_dated_basis(self) -> None:
        for pid, profile in load_destination_profiles().items():
            basis = str(profile.get("basis") or "")
            assert basis, f"{pid}: width without a basis is a gate against a guess"
            assert re.search(r"20\d\d-\d\d-\d\d|law", basis), f"{pid}: basis carries no date: {basis!r}"

    def test_standalone_is_identity_scale(self) -> None:
        profile = load_destination_profiles()["standalone"]
        assert min_scale(profile, 1080.0) == 1.0

    def test_github_readme_range_and_worst_case_scale(self) -> None:
        profile = load_destination_profiles()["github-readme"]
        width = profile["render_width"]
        assert width["min"] == 254 and width["max"] == 838
        assert min_scale(profile, 1024.0) == 254 / 1024
        assert min_scale(profile, 200.0) == 1.0  # narrower than the column: natural size


class TestScaleGates:
    @pytest.fixture(scope="class")
    def loop_svg(self) -> str:
        return compose(
            ComposeSpec(
                type="diagram",
                genome_id="primer",
                ground="opaque",
                palette="fixed",
                diagram=dict(load_diagram_presets()["loop-retry-budget"]),
            )
        ).svg

    def test_standalone_passes_at_design_scale(self, loop_svg: str) -> None:
        assert scale_gates(loop_svg, load_destination_profiles()["standalone"]) == []

    def test_github_mobile_floor_fails_the_font_gate_honestly(self, loop_svg: str) -> None:
        # A design-width loop at GitHub's 254px mobile floor renders its body
        # text far below 9 CSS px. That verdict is the gate WORKING — the
        # instrument states the density fact; Stage 7's delivery shell decides
        # what a compose-for-destination does with it.
        failures = scale_gates(loop_svg, load_destination_profiles()["github-readme"])
        assert any(f.startswith("font floor:") for f in failures), failures

    def test_dither_grain_is_exempt_from_the_texture_floor(self) -> None:
        svg = compose(
            ComposeSpec(
                type="diagram",
                genome_id="primer",
                variant="noir",
                ground="opaque",
                palette="fixed",
                diagram=dict(load_diagram_presets()["dag-gate"]),
            )
        ).svg
        assert "feTurbulence" in svg, "noir material should carry the dither grain"
        failures = scale_gates(svg, load_destination_profiles()["standalone"])
        assert not any("texture floor" in f for f in failures), failures

    def test_caller_policy_without_a_width_defers(self, loop_svg: str) -> None:
        assert scale_gates(loop_svg, load_destination_profiles()["chat-raster"]) == []
        failures = scale_gates(loop_svg, load_destination_profiles()["chat-raster"], raster_width=200.0)
        assert any(f.startswith("font floor:") for f in failures), failures


class TestFaceBake:
    @pytest.fixture(scope="class")
    def adaptive_svg(self) -> str:
        return compose(
            ComposeSpec(type="diagram", genome_id="primer", diagram=dict(load_diagram_presets()["dag-gate"]))
        ).svg

    def test_both_faces_bake_parse_and_differ(self, adaptive_svg: str) -> None:
        outs = {}
        for face in ("light", "dark"):
            data = project(adaptive_svg, "svg-static", face=face).data
            text = data.decode() if isinstance(data, bytes) else data
            ET.fromstring(text)
            nocomment = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
            assert not re.search(r"@media[^{]*prefers-color-scheme\s*:", nocomment)
            assert f'data-hw-face="{face}"' in text
            assert 'data-hw-adapt="adaptive"' not in text
            assert "var(--" not in text
            outs[face] = text
        assert outs["light"] != outs["dark"]

    def test_faceless_flatten_still_refuses_adaptive(self, adaptive_svg: str) -> None:
        with pytest.raises(HwError):
            project(adaptive_svg, "svg-static")

    def test_unknown_face_refused(self, adaptive_svg: str) -> None:
        with pytest.raises(HwError):
            project(adaptive_svg, "svg-static", face="sepia")

    def test_reduced_motion_media_survives_the_bake(self, adaptive_svg: str) -> None:
        data = project(adaptive_svg, "svg-static", face="light").data
        text = data.decode() if isinstance(data, bytes) else data
        assert "prefers-reduced-motion" in text


class TestSecondReviewGuards:
    def test_face_stamp_survives_a_colliding_title(self) -> None:
        # User content containing the literal attribute text must not
        # suppress the root stamp — only the ROOT TAG is inspected.
        from hyperweave.formats.static import bake_face

        svg = (
            '<svg data-hw-adapt="adaptive" data-hw-chromatic="primer">'
            "<style>@media (prefers-color-scheme: dark) { svg { color: red; } }</style>"
            '<text>mentions data-hw-face="dark" in prose</text></svg>'
        )
        baked = bake_face(svg, "dark")
        root = baked[: baked.find(">") + 1]
        assert 'data-hw-face="dark"' in root

    def test_contrast_claim_matches_the_delivered_faces(self) -> None:
        # The metadata's measured minimum is measured over the palettes that
        # RENDER (both overlaid faces) — a 5.7:1 claim once sat over a
        # delivered 1.12:1 pair (review finding, 2026-08-30).
        import re as _re

        from hyperweave.core.color import contrast_ratio

        preset = dict(load_diagram_presets()["dag-gate"])
        for variant in ("noir", "porcelain", "carbon"):
            svg = compose(ComposeSpec(type="diagram", genome_id="primer", variant=variant, diagram=preset)).svg
            claim = float(_re.search(r'contrast-ratio="([\d.]+):1"', svg).group(1))
            css = "\n".join(_re.findall(r"<style\b[^>]*>(.*?)</style>", svg, _re.DOTALL))
            near = dict(_re.findall(r"(--dna-[\w-]+):\s*(#[0-9A-Fa-f]{6})", css.split("@media")[0]))
            darkcss = "\n".join(_re.findall(r"@media[^{]*dark[^{]*\{((?:[^{}]|\{[^{}]*\})*)\}", css))
            far = {**near, **dict(_re.findall(r"(--dna-[\w-]+):\s*(#[0-9A-Fa-f]{6})", darkcss))}
            measured = min(
                contrast_ratio(t[fg], t[bg])
                for t in (near, far)
                for fg, bg in (
                    ("--dna-ink-primary", "--dna-surface"),
                    ("--dna-ink-muted", "--dna-surface"),
                    ("--dna-ink-on-accent", "--dna-signal"),
                )
                if t.get(fg) and t.get(bg)
            )
            assert abs(claim - measured) <= 0.15, f"{variant}: claim {claim} vs delivered {measured:.2f}"
            assert measured >= 4.5, f"{variant}: delivered floor {measured:.2f}"

    def test_inert_edges_keep_the_composite_only_tier(self) -> None:
        import re as _re

        svg = compose(
            ComposeSpec(
                type="diagram",
                genome_id="primer",
                ground="opaque",
                palette="fixed",
                diagram={
                    "topology": "pipeline",
                    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                    "edges": [{"source": "a", "target": "b", "state": "inert"}],
                },
            )
        ).svg
        assert "@keyframes" not in svg
        assert _re.search(r'"performance":\s*"composite-only"', svg)
