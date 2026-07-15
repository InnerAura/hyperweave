"""Surface-matrix per-cell invariants — the CI gate half of the proof matrix.

The pure-Python companion to ``scripts/generate_surface_matrix.py``: it composes
the matrix-frame surface cross-product in memory and asserts the per-cell
invariants that must hold without a browser — far-palette AA, status-invariance,
digest distinctness, and twin-face/@media hex agreement. The browser pass
(``raster_verify.py --scheme both``) is manual/nightly and covered separately.

Scope is the matrix frame (its templates honor the surface context today); the
diagram frame joins when its templates land (WC-2b-ii) — add it to ``_FRAMES``
here and to the generator's ``_FRAMES`` together.
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.compose.surface_modes import flip_palette, reground
from hyperweave.config.loader import get_loader, load_surface_modes
from hyperweave.core.color import contrast_ratio
from hyperweave.core.envelope import extract_envelope
from hyperweave.core.models import ComposeSpec

_VARIANTS = ("noir", "carbon", "space", "anvil", "porcelain", "cream", "dusk", "petrol")

# Frames whose templates honor surface_ground/surface_adapt today — the two
# Surface-Modes frames. Kept in lockstep with the generator's _FRAMES.
_FRAMES = ("matrix", "diagram")

# Status vars are semantic, never thematic — none may be redeclared in a far
# @media block (a scheme flip must not recolor pass/warn/fail).
_STATUS_VARS = (
    "--dna-status-passing-core",
    "--dna-status-warning-core",
    "--dna-status-failing-core",
    "--dna-badge-pass-core",
)


def _ir(frame: str) -> dict[str, object]:
    # Mirror the generator's representative IR per frame (matrix table / diagram DAG).
    if frame == "diagram":
        return {
            "title": "Surface Modes",
            "subtitle": "primer proof",
            "topology": "dag",
            "nodes": [
                {"id": "in", "label": "Ingest", "desc": "source"},
                {"id": "proc", "label": "Process", "role": "hero"},
                {"id": "out", "label": "Deliver", "desc": "sink"},
            ],
            "edges": [
                {"source": "in", "target": "proc"},
                {"source": "proc", "target": "out"},
            ],
        }
    return {
        "title": "Surface Modes",
        "subtitle": "primer proof",
        "columns": [
            {"id": "model", "label": "MODEL", "role": "label"},
            {"id": "score", "label": "SCORE", "role": "data", "kind": "numeric"},
            {"id": "pass", "label": "PASS", "role": "data", "kind": "check"},
        ],
        "rows": [
            {"label": "alpha", "cells": [{"value": 91}, {"value": True}]},
            {"label": "beta", "cells": [{"value": 84}, {"value": True}]},
            {"label": "gamma", "cells": [{"value": 62}, {"value": False}]},
        ],
    }


def _variant_palette(variant: str) -> dict[str, object]:
    genome = get_loader().genomes["primer"]
    override = genome["variant_overrides"][variant]
    return {**genome, **override, "_variant": variant}


def _compose(frame: str, variant: str, ground: str, palette: str, face: str = "") -> str:
    return compose(
        ComposeSpec(
            type=frame,
            genome_id="primer",
            variant=variant,
            ground=ground,
            palette=palette,
            surface_face=face,
            **{frame: _ir(frame)},
        )
    ).svg


def _digest(svg: str) -> str:
    env = extract_envelope(svg)
    return str(env.get("id", "")) if env else ""


def _far_media_block(svg: str) -> str:
    m = re.search(r"@media \(prefers-color-scheme: \w+\) \{ #hw-[0-9a-f]+ \{(.*?)\} \}", svg, re.DOTALL)
    assert m is not None, "adaptive artifact has no far @media block"
    return m.group(1)


def _near_block(svg: str) -> str:
    m = re.search(r"#hw-[0-9a-f]+ \{ color-scheme: light dark;(.*?)\}", svg, re.DOTALL)
    assert m is not None, "adaptive artifact has no near/base block"
    return m.group(1)


def _declared(css_fragment: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"(--dna-[a-z0-9-]+):\s*([^;]+);", css_fragment)}


# ── far-palette AA (both directions, all variants) ─────────────────────────


@pytest.mark.parametrize("variant", _VARIANTS)
def test_far_palette_ink_and_accent_clear_aa(variant: str) -> None:
    """On the flipped face, the ink and accent stay legible against the far ground.

    The projection's whole contract is that the far face is a real, legible scheme
    — not a naive mirror. Compute the far palette the same way the resolver does
    (flip_palette over the merged variant mapping) and assert ink/accent clear the
    AA floor against the re-grounded background.
    """
    cfg = load_surface_modes()
    mapping = _variant_palette(variant)
    far = flip_palette(mapping, cfg)
    substrate = str(mapping.get("substrate_kind") or "light")
    direction = "dark" if substrate == "light" else "light"
    far_ground = reground(str(mapping["surface_0"]), direction, cfg, tier="surface_0")

    assert contrast_ratio(far["ink"], far_ground) >= cfg.aa_floor, f"{variant}: far ink fails AA"
    if "accent" in far:
        assert contrast_ratio(far["accent"], far_ground) >= cfg.aa_floor, f"{variant}: far accent fails AA"


# ── status never flips (output level, all variants, inlay + twin) ──────────


@pytest.mark.parametrize("frame", _FRAMES)
@pytest.mark.parametrize("variant", _VARIANTS)
def test_status_vars_absent_from_far_block(frame: str, variant: str) -> None:
    for ground, palette in (("bare", "adaptive"), ("opaque", "adaptive")):  # inlay, twin
        far = _far_media_block(_compose(frame, variant, ground, palette))
        for status_var in _STATUS_VARS:
            assert status_var not in far, f"{variant} {ground}/{palette}: {status_var} flipped"


# ── digest distinctness (5 surfaces per variant) ───────────────────────────


@pytest.mark.parametrize("frame", _FRAMES)
@pytest.mark.parametrize("variant", _VARIANTS)
def test_five_surface_addresses_distinct(frame: str, variant: str) -> None:
    digests = {
        _digest(_compose(frame, variant, "opaque", "fixed")),  # plate
        _digest(_compose(frame, variant, "bare", "adaptive")),  # inlay
        _digest(_compose(frame, variant, "opaque", "adaptive")),  # twin
        _digest(_compose(frame, variant, "opaque", "fixed", "light")),  # light face
        _digest(_compose(frame, variant, "opaque", "fixed", "dark")),  # dark face
    }
    digests.discard("")
    assert len(digests) == 5, f"{variant}: expected 5 distinct surface addresses, got {len(digests)}"


# ── twin-face resolved hexes == the twin's @media declared values ──────────


def _face_effective_vars(face_svg: str) -> dict[str, str]:
    """The vars that ACTUALLY paint a baked face: the inline style= attr wins over
    the svg,:root rule (inline style beats a stylesheet), so union with the inline
    attr taking precedence — the value the browser actually uses."""
    root = re.search(r"svg, :root \{(.*?)\}", face_svg, re.DOTALL)
    effective = _declared(root.group(1)) if root else {}
    style = re.search(r'\sstyle="(--dna[^"]*)"', face_svg)
    if style:
        effective.update(_declared(style.group(1)))  # inline overrides the rule
    return effective


@pytest.mark.parametrize("frame", _FRAMES)
@pytest.mark.parametrize("variant", _VARIANTS)
def test_dark_face_hexes_match_twin_far_block(frame: str, variant: str) -> None:
    """The baked dark face and the twin's far @media block are the SAME flip.

    Both derive from flip_palette, so the dark face's EFFECTIVE vars (inline attr
    over svg,:root) must equal the twin's far-block declarations for every var the
    far block carries. This is the guarantee that ``surface=twin`` (one adaptive
    SVG) and ``--faces`` (two baked plates) render the identical dark scheme — the
    <picture> pair can't disagree with the inline @media.

    Regression guard for the face-bake fix: the flip must reach BOTH the top-level
    genome (svg,:root) AND variant_overrides[variant] (the inline style= attr,
    which wins over the stylesheet). Flipping only the top level left a baked face
    rendering the variant's NEAR values for every override field.
    """
    twin_far = _declared(_far_media_block(_compose(frame, variant, "opaque", "adaptive")))
    face_vars = _face_effective_vars(_compose(frame, variant, "opaque", "fixed", "dark"))

    assert twin_far, f"{variant}: twin far block declared nothing"
    for var, value in twin_far.items():
        assert face_vars.get(var) == value, (
            f"{variant}: {var} — twin @media says {value!r}, dark face effective says {face_vars.get(var)!r}"
        )


# ── NORMALIZED ORDERING: the twin's base (near) scope == the light face,      ─
# every variant including the dark-native ones (mirrors the test above, base  ─
# scope instead of the @media block). Pins the face-conformance ─
# fix: the hand-authored primer.noir/.carbon/.space/.anvil twin prototypes    ─
# all put light tokens in the base scope (renderers without prefers-color-    ─
# scheme support fall back there) and their OWN native dark tokens behind     ─
# @media(dark) — never the reverse.                                          ─


@pytest.mark.parametrize("frame", _FRAMES)
@pytest.mark.parametrize("variant", _VARIANTS)
def test_light_face_hexes_match_twin_near_block(frame: str, variant: str) -> None:
    """The baked light face and the twin's near (base) block are the SAME face,
    for every variant. Mirrors test_dark_face_hexes_match_twin_far_block for
    the base/near scope — before the fix this failed for the four dark-native
    variants, whose near block held their own native (dark) tokens instead."""
    twin_near = _declared(_near_block(_compose(frame, variant, "opaque", "adaptive")))
    face_vars = _face_effective_vars(_compose(frame, variant, "opaque", "fixed", "light"))

    assert twin_near, f"{variant}: twin near block declared nothing"
    for var, value in twin_near.items():
        assert face_vars.get(var) == value, (
            f"{variant}: {var} — twin near says {value!r}, light face effective says {face_vars.get(var)!r}"
        )


def test_twin_base_scope_is_light_face_for_dark_native_variant() -> None:
    """noir's twin base (near, no-media-query) scope carries the LIGHT face,
    not noir's own near-black tokens — those land behind @media(dark) instead.

    P5 chroma contract: a diagram twin sources BOTH faces from the variant's
    hand-authored ``diagram_faces`` (verbatim from verb-algebra-primer-*.svg),
    so the base scope equals the authored LIGHT face and the @media block the
    authored DARK face — which DIVERGE from the genome's plate variant palette
    (the authored twin surface/ink/accent are diagram-tuned). This pins the
    base=light / @media=dark ordering against the authored source of truth."""
    genome = get_loader().genomes["primer"]
    noir_faces = genome["variant_overrides"]["noir"]["diagram_faces"]
    porcelain_faces = genome["variant_overrides"]["porcelain"]["diagram_faces"]

    noir_svg = _compose("diagram", "noir", "opaque", "adaptive")
    noir_near = _declared(_near_block(noir_svg))
    noir_far = _declared(_far_media_block(noir_svg))
    assert noir_near["--dna-surface"] == noir_faces["light"]["surface_0"]
    assert noir_far["--dna-surface"] == noir_faces["dark"]["surface_0"]
    assert noir_far["--dna-ink-primary"] == noir_faces["dark"]["ink"]
    assert noir_far["--dna-signal"] == noir_faces["dark"]["accent"]

    porcelain_svg = _compose("diagram", "porcelain", "opaque", "adaptive")
    porcelain_near = _declared(_near_block(porcelain_svg))
    assert porcelain_near["--dna-surface"] == porcelain_faces["light"]["surface_0"]


# ── absolute --face semantics: the request names the SCHEME, not a relative
#    flip — `--face dark` on a dark-native variant is pass-through (its own
#    native tokens), matching what `--face light` does on a light-native one.


@pytest.mark.parametrize("variant", ["noir", "carbon", "space", "anvil"])
def test_dark_native_face_dark_is_native_passthrough(variant: str) -> None:
    """--face dark on a dark-native variant now yields its OWN native tokens.

    Pre-fix relative semantics inverted this: dark-native + --face=dark used
    to compute the FLIPPED (light) palette instead of passing the native one
    through untouched.
    """
    plate = _compose("matrix", variant, "opaque", "fixed")
    dark_face = _compose("matrix", variant, "opaque", "fixed", "dark")
    assert _face_effective_vars(plate) == _face_effective_vars(dark_face)


@pytest.mark.parametrize("variant", ["noir", "carbon", "space", "anvil"])
def test_dark_native_face_light_is_the_computed_flip(variant: str) -> None:
    """--face light on a dark-native variant computes the flip (unlike --face
    dark, which is pass-through) — the two faces must actually differ."""
    dark_face = _compose("matrix", variant, "opaque", "fixed", "dark")
    light_face = _compose("matrix", variant, "opaque", "fixed", "light")
    assert _face_effective_vars(dark_face) != _face_effective_vars(light_face)


@pytest.mark.parametrize("variant", ["porcelain", "cream", "dusk", "petrol"])
def test_light_native_face_light_is_native_passthrough(variant: str) -> None:
    """--face light on a light-native variant is still pass-through — this
    path is UNCHANGED by the fix, pinned here for symmetry."""
    plate = _compose("matrix", variant, "opaque", "fixed")
    light_face = _compose("matrix", variant, "opaque", "fixed", "light")
    assert _face_effective_vars(plate) == _face_effective_vars(light_face)


# ── LAW 2: NEAR-face role contrast, every variant (annotation chrome rides
# the same ink roles as frame content — no separate ink paths) ──────────────


@pytest.mark.parametrize("variant", _VARIANTS)
def test_near_palette_text_and_accent_clear_floors(variant: str) -> None:
    """Text roles (ink, ink_secondary) clear 4.5:1 against BOTH grounds the
    diagram paints them on (surface_0 backdrop, surface_1 card fill); the
    accent clears the 3:1 graphical floor. Annotation chrome (ann/lane/cnt
    classes) rides ink/ink_secondary, so this sweep IS its guarantee."""
    cfg = load_surface_modes()
    mapping = _variant_palette(variant)
    for ground_key in ("surface_0", "surface_1"):
        ground = str(mapping[ground_key])
        for role in ("ink", "ink_secondary"):
            got = contrast_ratio(str(mapping[role]), ground)
            assert got >= cfg.aa_floor, f"{variant}: {role} vs {ground_key} = {got:.2f}"
        accent = contrast_ratio(str(mapping["accent"]), ground)
        assert accent >= 3.0, f"{variant}: accent vs {ground_key} = {accent:.2f}"
