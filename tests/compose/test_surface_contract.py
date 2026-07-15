"""Surface Modes contract gate — output-level invariants (plan §7.5).

Distinct from ``test_surface_modes.py`` (which unit-tests the projection math):
these tests compose REAL matrix artifacts and assert the emitted-SVG contract
holds — the matrix templates paint only through var()s, plate-vs-inlay differs in
exactly the three expected places, adaptive output scopes to ``#uid`` and two
adaptive artifacts don't clobber, and status hues never appear in a far @media
block. The diagram frame is the second Surface-Modes frame (WC-2b): its primer
partials are scanned for the same paint-through-var contract (with the documented
allowlist) and its backdrop guard + adaptive shadow rule are pinned below.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.matrix import MatrixCell, MatrixColumn, MatrixRow, MatrixSpec
from hyperweave.core.models import ComposeSpec

_TEMPLATES = Path(__file__).resolve().parents[2] / "src" / "hyperweave" / "templates"
_MATRIX_CONTENT = _TEMPLATES / "frames" / "matrix" / "primer-content.j2"
_MATRIX_DEFS = _TEMPLATES / "frames" / "matrix" / "primer-defs.j2"
_DIAGRAM_CONTENT = _TEMPLATES / "frames" / "diagram" / "primer-content.j2"
_DIAGRAM_DEFS = _TEMPLATES / "frames" / "diagram" / "primer-defs.j2"


def _spec_dict() -> dict[str, object]:
    return MatrixSpec(
        title="Contract",
        subtitle="surface modes",
        columns=[
            MatrixColumn(id="model", label="MODEL", role="label"),
            MatrixColumn(id="score", label="SCORE", role="data", kind="numeric"),
        ],
        rows=[
            MatrixRow(label="alpha", cells=[MatrixCell(value=91)]),
            MatrixRow(label="beta", cells=[MatrixCell(value=84)]),
        ],
    ).model_dump()


def _compose(**surface_kw: str) -> str:
    return compose(
        ComposeSpec(type="matrix", genome_id="primer", variant="porcelain", matrix=_spec_dict(), **surface_kw)
    ).svg


# ── (a) matrix template source scan: paint only through var() ──────────────

# The matrix primer partials paint entirely through var()s and context values —
# the allowlist of tolerated hardcoded chromatic literals is EMPTY by design.
# Semantic paints (the pass/fail pill capsule) and brand glyph gradients arrive
# as context values (semantic_palette.*, stop.color), not string literals, so
# they don't appear as raw #hex in the source. Any literal the scan below finds
# is a genuine adaptation break — a fill that can't flip under @media.

# Matches a fill=/stroke=/stop-color= with a hardcoded #hex or rgb(...) literal.
_LITERAL_PAINT = re.compile(r'(?:fill|stroke|stop-color)="(#[0-9A-Fa-f]{3,8}|rgba?\([^"]*\))"')


@pytest.mark.parametrize("template", [_MATRIX_CONTENT, _MATRIX_DEFS])
def test_matrix_templates_paint_through_vars(template: Path) -> None:
    """No hardcoded chromatic paint literal in the matrix primer partials.

    Every fill/stroke/stop-color references a ``var(--dna-*)`` or a pre-resolved
    context value (cell indicator paints arrive resolved on the placement). A raw
    #hex would not flip under @media — the adaptation would silently break.
    """
    src = template.read_text()
    literals = _LITERAL_PAINT.findall(src)
    assert not literals, f"{template.name} has hardcoded paint literals: {literals}"


def test_matrix_content_backdrop_is_guarded() -> None:
    """The single backdrop rect is wrapped in the bare-ground guard."""
    src = _MATRIX_CONTENT.read_text()
    assert "{% if surface_ground != 'bare' %}" in src
    # the card-bg backdrop fill sits inside that guard
    guard_idx = src.find("{% if surface_ground != 'bare' %}")
    endif_idx = src.find("{% endif %}", guard_idx)
    assert "-card-bg)" in src[guard_idx:endif_idx]


def test_matrix_defs_gradient_gated_on_adapt() -> None:
    """The panel_gradient_stops branch yields to var-stops under adaptive."""
    src = _MATRIX_DEFS.read_text()
    assert "{% if panel_gradient_stops and not surface_adapt %}" in src


# ── (a-diagram) diagram template source scan: paint only through var() ──────

# The diagram primer partials paint through var()s and pre-resolved context
# values too. The documented allowlist of tolerated NON-var paint is:
#   - diagram_flow classes (`stroke: {{ diagram_flow[i] }}`) — the genome-
#     invariant communication palette, a CSS declaration value, not an attr;
#   - `_genome_raw.shadow_color` — a flood-color ATTRIBUTE (var() can't resolve
#     in a presentation attr; the adaptive path overrides it via a scoped CSS
#     rule instead);
#   - glyph gradient stops (`stop-color="{{ stop.color }}"`).
# All of these are Jinja `{{ }}` expressions, never raw #hex, so the same
# raw-literal scan applies and the tolerated set is empty in the source.


@pytest.mark.parametrize("template", [_DIAGRAM_CONTENT, _DIAGRAM_DEFS])
def test_diagram_templates_paint_through_vars(template: Path) -> None:
    """No hardcoded chromatic paint literal in the diagram primer partials.

    Every fill/stroke/stop-color/flood-color references a ``var(--dna-*)`` or a
    pre-resolved context value (flow hues, plate overrides, glyph-gradient stops,
    the shadow-color attr). A raw #hex would not flip under @media.
    """
    src = template.read_text()
    literals = _LITERAL_PAINT.findall(src)
    assert not literals, f"{template.name} has hardcoded paint literals: {literals}"


def test_diagram_content_backdrop_is_guarded() -> None:
    """The diagram backdrop composes the bare-ground guard with the chrome axis.

    The substrate rect drops for an inlay ground OR bare chrome — two orthogonal
    axes on one element. Both conditions gate the single ``var(--dna-surface)``
    backdrop rect.
    """
    src = _DIAGRAM_CONTENT.read_text()
    assert "surface_ground != 'bare'" in src
    assert "diagram_chrome != 'bare'" in src
    # both conditions guard the same backdrop rect (one line, composed with `and`)
    assert "diagram_chrome != 'bare' and surface_ground != 'bare'" in src


def test_diagram_defs_adaptive_shadow_rule() -> None:
    """Under adaptive, a scoped CSS rule re-tints the feDropShadow flood-color.

    The diagram carries its OWN neutral shadow tint (``diagram_shadow_color``,
    distinct from the shared ``shadow_color`` other frames use). The literal
    flood-color presentation attrs stay (plate/raster path); the adaptive rule
    (CSS beats attrs, browser-only) flips the shadow via the dedicated
    ``--dna-diagram-shadow-color`` var that the far @media block re-declares.
    """
    src = _DIAGRAM_DEFS.read_text()
    # literal attrs preserved for the raster path (diagram's own neutral tint)
    assert 'flood-color="{{ _genome_raw.diagram_shadow_color }}"' in src
    # adaptive override scoped to the root id, on the dedicated diagram var
    assert "{% if surface_adapt %}#{{ uid }} feDropShadow { flood-color: var(--dna-diagram-shadow-color); }" in src


# ── (b) plate vs inlay diff = exactly {backdrop, css layer, root attrs} ─────


def test_plate_vs_inlay_differences_are_bounded() -> None:
    """Plate and inlay differ ONLY in the backdrop rect, the CSS genome layer,
    and the root adaptive attributes — nothing in the content geometry.

    Proven structurally: the inlay drops the backdrop rect, swaps the global
    ``svg, :root`` genome rule for a scoped ``#uid`` block + @media, adds the
    adaptive root attrs, and drops the inline style attr. The row/cell/header
    geometry (every ``<text>``/``<line>``/coordinate) is identical.
    """
    # primer DEFAULTS to twin now — the plate baseline must be explicit.
    plate = _compose(ground="opaque", palette="fixed")
    inlay = _compose(ground="bare", palette="adaptive")

    # backdrop: present in plate, absent in inlay
    assert "-card-bg)" in plate
    assert "-card-bg)" not in inlay  # bare drops the backdrop fill

    # css layer: plate has the global genome rule; inlay has the scoped one
    assert "svg, :root {" in plate
    assert "svg, :root {" not in inlay
    assert "{ color-scheme: light dark;" in inlay
    assert "{ color-scheme: light dark;" not in plate

    # root attrs: inlay carries the adaptive trio, plate none
    assert "data-hw-adapt=" in inlay
    assert "data-hw-adapt=" not in plate

    # OUTER CONTAINER BORDER: gone entirely on inlay (review overrule of the
    # plan's "hairline stays" — a framed dissolved artifact reads as a
    # translucent plate). Internal structure hairlines (column/row rules)
    # remain — the table skeleton is content, not the container.
    outer_border = 'fill="none" stroke="var(--dna-border)" stroke-width="1.2"'
    assert outer_border in plate
    assert outer_border not in inlay

    # content geometry parity: the row/header <text> content is identical. Strip
    # ids (uid differs by content digest) and compare the geometry-bearing lines.
    def _geometry_lines(svg: str) -> list[str]:
        # every <text>/<line>/<rect> that is NOT the backdrop, normalized of uid
        out: list[str] = []
        for line in svg.splitlines():
            s = line.strip()
            if s.startswith(("<text", "<line", "<circle")):
                out.append(re.sub(r"hw-[0-9a-f]{8}", "hw-UID", s))
        return out

    assert _geometry_lines(plate) == _geometry_lines(inlay)


# ── (c) id-scoping + two-artifact clobber invariant ────────────────────────


def test_adaptive_scopes_to_root_id() -> None:
    """Adaptive output: root id == the CSS #uid scope, one @media block, and no
    global svg,:root --dna rule survives."""
    svg = _compose(ground="opaque", palette="adaptive")
    root_id = re.search(r'\bid="(hw-[0-9a-f]+)"', svg)
    assert root_id is not None
    uid = root_id.group(1)
    # near block scoped to #uid
    assert f"#{uid} {{ color-scheme: light dark;" in svg
    # exactly one @media(prefers-color-scheme) far block, scoped to the same id
    media_blocks = re.findall(r"@media \(prefers-color-scheme: \w+\) \{ #(hw-[0-9a-f]+) \{", svg)
    assert media_blocks == [uid]
    # no leftover global genome rule
    assert "svg, :root {" not in svg
    # no root style= attribute (folded into the near block)
    assert not re.search(r'\bstyle="--dna', svg)


def test_two_adaptive_artifacts_disjoint_scopes() -> None:
    """Two adaptive artifacts on one page scope to distinct ids — no clobber.

    Same spec + variant twice would collide only if the scope selector were
    shared; the content-digest uid keeps them distinct (and here the two use
    different variants for good measure). Neither's @media selector matches the
    other's root id.
    """
    a = _compose(ground="opaque", palette="adaptive")
    b = compose(
        ComposeSpec(
            type="matrix",
            genome_id="primer",
            variant="cream",
            ground="opaque",
            palette="adaptive",
            matrix=_spec_dict(),
        )
    ).svg
    id_a = re.search(r'\bid="(hw-[0-9a-f]+)"', a).group(1)  # type: ignore[union-attr]
    id_b = re.search(r'\bid="(hw-[0-9a-f]+)"', b).group(1)  # type: ignore[union-attr]
    assert id_a != id_b
    # a's selectors never reference b's id and vice versa
    assert id_b not in a
    assert id_a not in b


# ── emitted-vars parity: the inline style= attr's vars all reach the near block ──


def _declared_vars(css_fragment: str) -> set[str]:
    """The set of ``--dna-*`` property names declared in a CSS fragment."""
    return set(re.findall(r"(--dna-[a-z0-9-]+)\s*:", css_fragment))


def _plate_inline_style_vars(plate_svg: str) -> set[str]:
    """The ``--dna-*`` vars a plate carries on its root ``style=`` attribute."""
    m = re.search(r'\sstyle="(--dna[^"]*)"', plate_svg)
    return _declared_vars(m.group(1)) if m else set()


def _adaptive_near_block(adaptive_svg: str) -> str:
    """The body of the ``#uid { color-scheme: light dark; … }`` near block."""
    m = re.search(r"#hw-[0-9a-f]+ \{ color-scheme: light dark;(.*?)\}", adaptive_svg, re.DOTALL)
    assert m is not None, "adaptive output has no #uid near block"
    return m.group(1)


def test_plate_inline_vars_all_appear_in_adaptive_near_block() -> None:
    """Every var the plate emits ONLY via the root ``style=`` attribute survives
    into the adaptive near block.

    Adaptive mode suppresses the inline ``style=`` attribute and folds its
    declarations into the ``#uid`` near block via ``variant_override_declarations``
    unioned with the core genome layer. This is the invariant that motivates that
    factoring existing at all: several vars (``--dna-label-text``, ``--dna-signal``,
    ``--dna-glyph-inner`` — the variant's identity hue) reach the matrix template
    ONLY through the inline attribute on a plate. If the union broke, those vars
    would vanish from the near face and the variant would render its NEAR scheme
    with the base genome's identity instead of the variant's — a silent, styling-
    only regression no other test in this file would catch (geometry parity and
    the far @media checks all still pass). Pin the union at the emitted-SVG level.
    """
    plate = _compose(ground="opaque", palette="fixed")  # porcelain, explicit plate
    inlay = _compose(ground="bare", palette="adaptive")

    inline_vars = _plate_inline_style_vars(plate)
    # Sanity: porcelain's inline attr carries the identity-hue vars this guards.
    assert {"--dna-label-text", "--dna-signal"} <= inline_vars

    near_vars = _declared_vars(_adaptive_near_block(inlay))
    missing = inline_vars - near_vars
    assert not missing, f"plate inline vars dropped from the adaptive near block: {sorted(missing)}"


def test_label_text_tracks_accent_on_both_near_and_far() -> None:
    """--dna-label-text carries the accent hue: on the near face it equals the
    near accent (--dna-signal); in the far @media block it re-declares to the same
    flipped value as --dna-signal (the twin prototype's label==signal rule, at the
    emitted-CSS level rather than the projection-math level).
    """
    inlay = _compose(ground="opaque", palette="adaptive")  # twin: has a far block

    def _var(fragment: str, name: str) -> str | None:
        m = re.search(rf"{re.escape(name)}\s*:\s*([^;]+);", fragment)
        return m.group(1).strip() if m else None

    near = _adaptive_near_block(inlay)
    media_start = inlay.find("@media (prefers-color-scheme")
    far = inlay[media_start : inlay.find("</style>", media_start)]

    # near: porcelain's label_text is authored equal to its accent.
    assert _var(near, "--dna-label-text") == _var(near, "--dna-signal")
    # far: both re-declare, and to the same flipped hue (identity stays unified).
    far_label, far_signal = _var(far, "--dna-label-text"), _var(far, "--dna-signal")
    assert far_label is not None and far_signal is not None
    assert far_label == far_signal


# ── (d) status never flips at the OUTPUT level ─────────────────────────────

# The status CSS var names that must NEVER appear in a far @media block. If any
# surfaced there, a scheme flip would recolor pass/warn/fail — the one thing that
# is semantic, not thematic.
_STATUS_VARS = (
    "--dna-status-passing-core",
    "--dna-status-warning-core",
    "--dna-status-failing-core",
    "--dna-badge-pass-core",
)


@pytest.mark.parametrize("variant", ["porcelain", "carbon", "space", "dusk", "petrol", "cream", "anvil", "noir"])
def test_status_vars_absent_from_far_media_block(variant: str) -> None:
    """No status var is re-declared in the adaptive far @media block, for any variant."""
    svg = compose(
        ComposeSpec(
            type="matrix",
            genome_id="primer",
            variant=variant,
            ground="opaque",
            palette="adaptive",
            matrix=_spec_dict(),
        )
    ).svg
    media_start = svg.find("@media (prefers-color-scheme")
    assert media_start != -1
    # isolate the far block body (up to the closing of the media query)
    far_block = svg[media_start : svg.find("</style>", media_start)]
    for status_var in _STATUS_VARS:
        assert status_var not in far_block, f"{variant}: {status_var} flipped in the far @media block"


def test_semantic_pill_hexes_identical_across_faces() -> None:
    """The semantic pill capsule renders the same hexes on a light face and a dark
    face (a twin's two baked faces share the semantic palette byte-for-byte)."""
    light = compose(
        ComposeSpec(
            type="matrix",
            genome_id="primer",
            variant="porcelain",
            ground="opaque",
            palette="adaptive",
            surface_face="light",
            matrix=_spec_dict(),
        )
    ).svg
    dark = compose(
        ComposeSpec(
            type="matrix",
            genome_id="primer",
            variant="porcelain",
            ground="opaque",
            palette="adaptive",
            surface_face="dark",
            matrix=_spec_dict(),
        )
    ).svg

    def _pill_stops(svg: str) -> list[str]:
        m = re.search(r'id="[^"]*-pill-yes"[^>]*>(.*?)</linearGradient>', svg, re.DOTALL)
        return re.findall(r'stop-color="(#[0-9A-Fa-f]+)"', m.group(1)) if m else []

    assert _pill_stops(light) == _pill_stops(dark)
    assert _pill_stops(light)  # non-empty (the pill gradient is present)
