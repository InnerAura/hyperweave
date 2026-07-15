"""Far-face legibility sweep — every diagram kit piece, both faces, all 8 variants.

The adaptive twin's far face is a SPARSE ``@media (prefers-color-scheme)`` block
computed by ``flip_palette()`` (compose/surface_modes.py): contrast parity, not a
naive lightness mirror. A piece goes illegible on the far face when either (a)
its CSS var never appears in the flip set (a literal genome value, or a "held"
communication-palette field, baked once and never re-declared) or (b) an element
carries a SECOND class whose rule is declared LATER in the stylesheet and wins
the cascade, silently overriding a var that DOES flip with one that doesn't.

This sweep renders the ``cicd-gate`` bundled diagram spec (chips, an edge-chip,
a hero card + chips, gather-free but marker/wire-bearing) as a twin for every
primer variant, parses BOTH CSS layers out of the real output (a tiny cascade
model: compound-selector class rules in source order + ``var(--x[, fallback])``
resolution against the near ``#uid{}`` block and the far ``@media{}`` block),
and asserts the effective foreground/background PAIR an actual rendered element
would show clears the legibility floor on each face. Parsing the ACTUAL emitted
classes (not the static template source) is what catches a same-specificity
cascade override — one WAS found this way: an edge-chip's ``-tag`` (ink_muted,
which flips fine) loses to an accent-hijack class appended for edges/annotations/
node-labels that carry an explicit accent index, whose color is the diagram_flow
communication palette — HELD across faces by design, so it goes near-invisible
whenever the flip lands the chip's (flipping) background close to the flow
color's own (fixed) lightness.
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.engine import compose
from hyperweave.core.color import contrast_ratio
from hyperweave.core.models import ComposeSpec

_VARIANTS = ["porcelain", "cream", "dusk", "petrol", "noir", "carbon", "space", "anvil"]

_TEXT_FLOOR = 3.0
_FURNITURE_FLOOR = 1.5

_UID_RE = re.compile(r"#(hw-[0-9a-f]+)\s*\{\s*color-scheme: light dark;")
_MEDIA_RE = re.compile(r"@media \(prefers-color-scheme:\s*(\w+)\)\s*")
_VAR_DECL_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
_VAR_REF_RE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^)]+))?\)")
# Compound selectors of PLAIN class-only rules (`.a, .b, .c { ... }`) — every
# selector in this codebase's diagram defs is exactly this shape.
_RULE_RE = re.compile(r"((?:\.[\w-]+\s*,\s*)*\.[\w-]+)\s*\{([^}]*)\}")
_CLASS_ATTR_RE = re.compile(r'<(text|rect|circle|line|path)\b[^>]*\bclass="([^"]+)"[^>]*>(?:([^<]*)</\1>)?')


def _brace_block(text: str, search_from: int) -> tuple[int, int, str] | None:
    """Brace-match the block starting at the first ``{`` at/after ``search_from``."""
    brace = text.find("{", search_from)
    if brace == -1:
        return None
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return brace, i, text[brace + 1 : i]
    return None


def _parse_rules(css: str) -> list[tuple[str, dict[str, str]]]:
    """Every ``.class { prop: value; }`` rule, compound selectors exploded, in
    document order (needed so "last rule wins" cascade resolution is correct)."""
    rules: list[tuple[str, dict[str, str]]] = []
    for m in _RULE_RE.finditer(css):
        selector, body = m.group(1), m.group(2)
        classes = [c.strip().lstrip(".") for c in selector.split(",")]
        props: dict[str, str] = {}
        for decl in body.split(";"):
            decl = decl.strip()
            if ":" not in decl:
                continue
            k, v = decl.split(":", 1)
            props[k.strip()] = v.strip()
        for cls in classes:
            rules.append((cls, props))
    return rules


def _effective(rules: list[tuple[str, dict[str, str]]], classes: set[str], prop: str) -> str | None:
    """The LAST rule (source order) among an element's classes that sets `prop` —
    same-specificity CSS cascade (every selector here is a single class, 0-1-0)."""
    value = None
    for cls, props in rules:
        if cls in classes and prop in props:
            value = props[prop]
    return value


def _css_vars(css: str, uid: str) -> tuple[dict[str, str], dict[str, str]]:
    """(near_vars, far_vars) merged across every ``#uid{...}`` block found,
    inside or outside an ``@media (prefers-color-scheme)`` wrapper. far_vars is
    seeded from near_vars first — an unflipped var holds its near value."""
    media_spans: list[tuple[int, int]] = []
    for m in _MEDIA_RE.finditer(css):
        blk = _brace_block(css, m.end())
        if blk:
            media_spans.append((blk[0], blk[1]))

    def _in_media(pos: int) -> bool:
        return any(s <= pos <= e for s, e in media_spans)

    near: dict[str, str] = {}
    far: dict[str, str] = {}
    for m in re.finditer(rf"#{re.escape(uid)}\s*(?=\{{)", css):
        blk = _brace_block(css, m.end())
        if blk is None:
            continue
        _, _, body = blk
        decls = {mm.group(1): mm.group(2).strip() for mm in _VAR_DECL_RE.finditer(body)}
        if _in_media(m.start()):
            far.update(decls)
        else:
            near.update(decls)
    return near, {**near, **far}


def _resolve(value: str | None, near_vars: dict[str, str], far_vars: dict[str, str], face: str) -> str | None:
    """Resolve a raw CSS value (literal hex/rgba, or ``var(--x[, fallback])``)
    to the concrete color on the given face ("near" | "far")."""
    if value is None:
        return None
    m = _VAR_REF_RE.match(value.strip())
    if not m:
        return value.strip()
    name, fallback = m.group(1), m.group(2)
    table = far_vars if face == "far" else near_vars
    if name in table:
        return table[name].strip()
    return fallback.strip() if fallback else None


def _hex_only(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip()
    return v if re.fullmatch(r"#[0-9A-Fa-f]{6}", v) else None


class _Rendered:
    """A composed adaptive-twin diagram: uid, css rules, and near/far var tables."""

    def __init__(self, svg: str) -> None:
        self.svg = svg
        m = _UID_RE.search(svg)
        assert m, "no adaptive #uid{ color-scheme: ...} block found — compose wasn't adaptive"
        self.uid = m.group(1)
        # Two <style> tags exist in a composed diagram: the genome/accessibility
        # CSS bundle (carries the #uid{} near/far adaptive blocks) AND the
        # frame's own defs partial (embedded @font-face payloads immediately
        # followed by every diagram class rule). Both must be searched.
        style_blocks = re.findall(r"<style>(.*?)</style>", svg, re.S)
        assert style_blocks, "no <style> block in composed SVG"
        self.css = "\n".join(style_blocks)
        self.rules = _parse_rules(self.css)
        self.near_vars, self.far_vars = _css_vars(self.css, self.uid)

    def color(self, classes: set[str], prop: str, face: str) -> str | None:
        raw = _effective(self.rules, classes, prop)
        return _resolve(raw, self.near_vars, self.far_vars, face)

    def instances(self, marker_class: str) -> list[set[str]]:
        """Distinct class-sets of every rendered element carrying `marker_class`
        (deduped) — reading the ACTUAL emitted classes catches a cascade
        override (a second, later-declared class hijacking the color) that a
        static read of the template source would miss."""
        prefixed = f"{self.uid}-{marker_class}"
        seen: list[set[str]] = []
        for m in _CLASS_ATTR_RE.finditer(self.svg):
            classes = set(m.group(2).split())
            if prefixed in classes and classes not in seen:
                seen.append(classes)
        return seen


_CACHE: dict[str, _Rendered] = {}


def _render(variant: str) -> _Rendered:
    if variant not in _CACHE:
        bs = resolve_bundled_spec("diagram", "cicd-gate")
        spec = ComposeSpec(
            type="diagram", genome_id="primer", variant=variant, ground="opaque", palette="adaptive", diagram=bs.value
        )
        _CACHE[variant] = _Rendered(compose(spec).svg)
    return _CACHE[variant]


def _assert_pair(
    rendered: _Rendered,
    fg_classes: set[str],
    fg_prop: str,
    bg_classes: set[str],
    bg_prop: str,
    floor: float,
    face: str,
    label: str,
) -> None:
    fg = _hex_only(rendered.color(fg_classes, fg_prop, face))
    bg = _hex_only(rendered.color(bg_classes, bg_prop, face))
    if fg is None or bg is None:
        pytest.fail(f"{label} [{face}]: could not resolve a concrete color (fg={fg!r} bg={bg!r})")
    ratio = contrast_ratio(fg, bg)
    assert ratio >= floor, f"{label} [{face}]: {fg} vs {bg} = {ratio:.2f} < {floor} ({fg_classes} vs {bg_classes})"


# ── page ground + card fills (always single-rule, resolved once per variant) ──


def _page_ground(rendered: _Rendered, face: str) -> str | None:
    table = rendered.far_vars if face == "far" else rendered.near_vars
    return _hex_only(table.get("--dna-surface"))


# ── 1. chip text vs chip bg — the exact reported bug (edge-chip on cream) ────


@pytest.mark.parametrize("variant", _VARIANTS)
@pytest.mark.parametrize("face", ["near", "far"])
def test_chip_text_vs_chip_bg(variant: str, face: str) -> None:
    r = _render(variant)
    chip_bg_cls = {f"{r.uid}-chipbg"}
    for instance in r.instances("tag"):
        label = f"{variant} chip-text{sorted(instance)}"
        _assert_pair(r, instance, "fill", chip_bg_cls, "fill", _TEXT_FLOOR, face, label)


# ── 2. micro-label (edge label) vs page ground ───────────────────────────────


@pytest.mark.parametrize("variant", _VARIANTS)
@pytest.mark.parametrize("face", ["near", "far"])
def test_micro_label_vs_surface_0(variant: str, face: str) -> None:
    r = _render(variant)
    bg = _page_ground(r, face)
    for instance in r.instances("elbl"):
        fg = _hex_only(r.color(instance, "fill", face))
        if fg is None or bg is None:
            pytest.fail(f"{variant} micro-label [{face}]: unresolved color (fg={fg!r} bg={bg!r})")
        ratio = contrast_ratio(fg, bg)
        assert ratio >= _TEXT_FLOOR, f"{variant} micro-label [{face}]: {fg} vs {bg} = {ratio:.2f} < {_TEXT_FLOOR}"


# ── 3. annotation text vs page ground ────────────────────────────────────────


@pytest.mark.parametrize("variant", _VARIANTS)
@pytest.mark.parametrize("face", ["near", "far"])
def test_annotation_text_vs_surface_0(variant: str, face: str) -> None:
    r = _render(variant)
    bg = _page_ground(r, face)
    for instance in r.instances("ann"):
        fg = _hex_only(r.color(instance, "fill", face))
        if fg is None or bg is None:
            pytest.fail(f"{variant} annotation [{face}]: unresolved color (fg={fg!r} bg={bg!r})")
        ratio = contrast_ratio(fg, bg)
        assert ratio >= _TEXT_FLOOR, f"{variant} annotation [{face}]: {fg} vs {bg} = {ratio:.2f} < {_TEXT_FLOOR}"


# ── 4/5/6. node name / desc / hero-desc vs their card fill ───────────────────


@pytest.mark.parametrize("variant", _VARIANTS)
@pytest.mark.parametrize("face", ["near", "far"])
@pytest.mark.parametrize(
    ("marker", "label"),
    [("name", "name"), ("hname", "hero-name"), ("ndesc", "desc"), ("hdesc", "hero-sub")],
)
def test_node_text_vs_card_fill(variant: str, face: str, marker: str, label: str) -> None:
    r = _render(variant)
    card_classes = {f"{r.uid}-herobg"} if marker in ("hname", "hdesc") else {f"{r.uid}-cardbg"}
    instances = r.instances(marker)
    if not instances:
        pytest.skip(f"{variant}: no {marker} instances in cicd-gate")
    for instance in instances:
        piece_label = f"{variant} {label}{sorted(instance)}"
        _assert_pair(r, instance, "fill", card_classes, "fill", _TEXT_FLOOR, face, piece_label)


# ── furniture: gather ring / borders / muted wires vs ground (>=1.5) ────────


def _assert_furniture_vs_ground(r: _Rendered, marker: str, face: str, label: str) -> None:
    bg = _page_ground(r, face)
    instances = r.instances(marker)
    if not instances:
        pytest.skip(f"{label}: cicd-gate has no {marker} instances")
    for instance in instances:
        fg = _hex_only(r.color(instance, "stroke", face))
        if fg is None or bg is None:
            pytest.fail(f"{label} [{face}]: unresolved color (fg={fg!r} bg={bg!r})")
        ratio = contrast_ratio(fg, bg)
        assert ratio >= _FURNITURE_FLOOR, f"{label} [{face}]: {fg} vs {bg} = {ratio:.2f} < {_FURNITURE_FLOOR}"


@pytest.mark.parametrize("variant", _VARIANTS)
@pytest.mark.parametrize("face", ["near", "far"])
def test_gather_ring_vs_ground(variant: str, face: str) -> None:
    _assert_furniture_vs_ground(_render(variant), "gr", face, f"{variant} gather-ring")


@pytest.mark.parametrize("variant", _VARIANTS)
@pytest.mark.parametrize("face", ["near", "far"])
@pytest.mark.parametrize("marker", ["lead", "lanerule"])
def test_borders_vs_ground(variant: str, face: str, marker: str) -> None:
    _assert_furniture_vs_ground(_render(variant), marker, face, f"{variant} border({marker})")


@pytest.mark.parametrize("variant", _VARIANTS)
@pytest.mark.parametrize("face", ["near", "far"])
def test_muted_wires_vs_ground(variant: str, face: str) -> None:
    _assert_furniture_vs_ground(_render(variant), "connmuted", face, f"{variant} muted-wire")


# ── coverage guard: the sweep must actually be exercising instances, not
#    vacuously skipping every check (a preset change silently defanging it) ──


def test_sweep_exercises_chip_tags_and_they_are_neutral() -> None:
    """cicd-gate's 'release' edge-chip emits a ``-tag`` text run — the sweep
    must actually SEE it (non-vacuous), AND after the P5 chip contract that run
    is NEUTRAL: it never carries a second (accent/flow) class alongside ``-tag``.

    Pre-P5 the edge-chip tag was accent-hijacked (``-tag -flpN``, the flow hue
    HELD across faces → the espresso-chip-on-cream illegibility bug); the fix
    unbinds chip text from the accent class (primer-content.j2), so chip text
    now rides --dna-ink-muted and flips cleanly. Both halves matter: the first
    keeps the sweep honest, the second pins the fix."""
    r = _render("cream")
    tags = r.instances("tag")
    assert tags, "cicd-gate emits no -tag edge-chip run — chip sweep is vacuous"
    hijacked = [i for i in tags if len(i) > 1]
    assert not hijacked, f"chip -tag text still carries a second (accent) class: {hijacked}"


# ── 7. identity-mark GLYPH paint vs its backing ──────────────────────────────
#
# Glyphs don't carry a `class` — chrome.py/matrix/cells.py's glyph_mark_placement
# stamps paint straight onto the <g> as an inline fill/stroke attribute (a var()
# for ink, a literal hex for brand, a gradient url(#...) for full-color/gradient
# marks). None of the class-cascade machinery above sees them, so this sweep
# parses the glyph <g transform="translate(...) scale(...)"> tags directly (that
# exact transform shape is glyph_mark_placement's signature — nothing else in the
# diagram frame emits it) and resolves each paint value through the SAME near/far
# var tables the CSS cascade uses. Backing mirrors contrast.py's own surface
# split: a card/hero mark checks the card fill (--dna-surface-alt); a bare circle
# mark (kit anatomy: no independent plate) checks the page ground (--dna-surface)
# — found by walking back to the nearest preceding node-background element in
# document order. A gradient/multi-path full-color mark resolves to no concrete
# hex (by design — team directive: true brand colors never remap) and is skipped.

_GLYPH_PRESETS = ["frontier-serving", "flywheel-orbit"]

_GLYPH_GROUP_RE = re.compile(r'<g transform="translate\([^)]*\) scale\([^)]*\)"([^>]*)>')
_GLYPH_ATTR_RE = re.compile(r'\b(fill|stroke)="([^"]*)"')
_NODE_BG_RE = re.compile(r"<(rect|circle)\b[^>]*\bclass=\"([^\"]+)\"")


def _node_backgrounds(svg: str, uid: str) -> list[tuple[int, str]]:
    """``[(offset, shape)]`` for every NODE background element in document
    order. ``shape`` is ``"card"`` (cardbg/herobg — fills ``--dna-surface-alt``)
    or ``"circle"`` (circlebg/herocirclebg — ``fill: none``, a bare ring on the
    page ground) — the exact split ``contrast.py`` gates against."""
    out: list[tuple[int, str]] = []
    for m in _NODE_BG_RE.finditer(svg):
        classes = set(m.group(2).split())
        if f"{uid}-cardbg" in classes or f"{uid}-herobg" in classes:
            out.append((m.start(), "card"))
        elif f"{uid}-circlebg" in classes or f"{uid}-herocirclebg" in classes:
            out.append((m.start(), "circle"))
    return out


def _glyph_marks(svg: str, uid: str) -> list[tuple[dict[str, str], str]]:
    """``(paint_attrs, backing_shape)`` for every identity-mark glyph, in
    document order, backing resolved from the nearest PRECEDING node
    background (a glyph always renders just after its own node's plate)."""
    backgrounds = _node_backgrounds(svg, uid)
    marks: list[tuple[dict[str, str], str]] = []
    for m in _GLYPH_GROUP_RE.finditer(svg):
        shape = "card"
        for bg_offset, bg_shape in backgrounds:
            if bg_offset > m.start():
                break
            shape = bg_shape
        marks.append((dict(_GLYPH_ATTR_RE.findall(m.group(1))), shape))
    return marks


def _render_diagram_preset(preset: str, variant: str) -> _Rendered:
    key = f"{preset}:{variant}"
    if key not in _CACHE:
        bs = resolve_bundled_spec("diagram", preset)
        spec = ComposeSpec(
            type="diagram", genome_id="primer", variant=variant, ground="opaque", palette="adaptive", diagram=bs.value
        )
        _CACHE[key] = _Rendered(compose(spec).svg)
    return _CACHE[key]


@pytest.mark.parametrize("preset", _GLYPH_PRESETS)
@pytest.mark.parametrize("variant", _VARIANTS)
@pytest.mark.parametrize("face", ["near", "far"])
def test_glyph_paint_vs_backing(preset: str, variant: str, face: str) -> None:
    """Every identity-mark glyph's effective paint clears the legibility floor
    against its backing on BOTH faces. This is the reported bug: an achromatic
    brand mark (anthropic/openai's near-black wordmark) read fine on its own
    near face and stayed a literal hex — invisible once the twin's far card
    flipped dark. Fails on the pre-fix gate (near-face-only) for native-light
    variants' far face; green once the gate checks both faces (contrast.py's
    ``far_genome``)."""
    r = _render_diagram_preset(preset, variant)
    ground = _page_ground(r, face)
    card = _hex_only((r.far_vars if face == "far" else r.near_vars).get("--dna-surface-alt"))
    checked = 0
    for attrs, shape in _glyph_marks(r.svg, r.uid):
        backing = card if shape == "card" else ground
        for channel in ("fill", "stroke"):
            raw = attrs.get(channel)
            if not raw or raw == "none":
                continue
            fg = _hex_only(_resolve(raw, r.near_vars, r.far_vars, face))
            if fg is None:
                continue  # gradient url(#...) / multi-path full-color — out of scope by design
            if backing is None:
                pytest.fail(f"{preset}/{variant} glyph [{face}]: backing unresolved (shape={shape})")
            checked += 1
            ratio = contrast_ratio(fg, backing)
            assert ratio >= _TEXT_FLOOR, (
                f"{preset}/{variant} glyph {channel} [{face}]: {fg} vs {backing} = "
                f"{ratio:.2f} < {_TEXT_FLOOR} (raw={raw!r}, shape={shape})"
            )
    assert checked > 0, f"{preset}/{variant} [{face}]: no glyph paint checked — sweep is vacuous"
