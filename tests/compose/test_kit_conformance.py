"""Kit-only conformance harness — the permanent gate against pre-kit visuals.

Five leak classes let old visuals ship past review: stale preset content,
undeleted legacy mechanisms (plate-swap fills, masthead-band chrome),
un-extracted per-topology anatomy, under-fed shared functions (truncation),
and stale parallel state. This suite pins the FIXED world: it sweeps every
bundled diagram preset (``hyperweave.compose.diagram.input.diagram_preset_names``)
through the full production compose path and asserts the emitted SVG speaks
ONLY kit vocabulary — never preset content itself, always an engine
invariant, so a preset-authoring pass can't trip the harness by rewriting
copy.

Two composes per preset: PLATE (``ground=opaque``, ``palette=fixed``,
``variant=porcelain`` — the flagship, light-native default) covers ten
structural invariants. ONE extra ADAPTIVE TWIN compose (a fixed glyph-rich
preset, ``frontier-serving``) covers the eleventh: adaptive honesty (the
near/far face contract at the emitted-CSS level).

``data/presets/diagram.yaml`` may be under concurrent edit by a parallel
preset-authoring pass while this suite runs; ``load_diagram_presets`` is
``@lru_cache``d, so the FIRST successful read in this process freezes a
stable snapshot for the rest of the run regardless of later edits on disk —
``_with_retry`` only needs to cover that first read (and any other call
racing ahead of it).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.diagram.chrome import VOICE_CLASSES
from hyperweave.compose.diagram.input import diagram_preset_names
from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_diagram_config, load_idioms, load_paradigms
from hyperweave.core.color import relative_luminance
from hyperweave.core.models import ComposeSpec

_TEMPLATES = Path(__file__).resolve().parents[2] / "src" / "hyperweave" / "templates"
_DIAGRAM_DEFS = _TEMPLATES / "frames" / "diagram" / "primer-defs.j2"

_VARIANT = "porcelain"  # flagship, light-native default — the PLATE/porcelain compose
_ADAPTIVE_PRESET = "frontier-serving"  # fixed glyph-rich preset (also used by test_far_face_legibility)


def _with_retry[T](build: Callable[[], T], *, attempts: int = 8, delay: float = 0.25) -> T:
    """Retry ``build`` across a brief window.

    ``data/presets/diagram.yaml`` may be mid-write by a parallel agent when
    this module first touches it; a half-written YAML document raises a
    parse error (or, mid-rename, an unknown-preset error) that clears on the
    next attempt. Once one call succeeds, ``load_diagram_presets``'s
    ``@lru_cache`` freezes the result for the rest of the process.
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return build()
        except Exception as exc:  # transient YAML/parse hiccup while a preset file is mid-write, retried below
            last = exc
            if attempt < attempts - 1:
                time.sleep(delay)
    assert last is not None
    raise last


def _stable_preset_names() -> tuple[str, ...]:
    return _with_retry(diagram_preset_names)


_PRESET_NAMES = _stable_preset_names()


@dataclass(frozen=True, slots=True)
class _Rendered:
    """A PLATE compose of one bundled preset: the emitted SVG, its uid, the
    merged CSS text (a diagram artifact emits two ``<style>`` tags — the
    genome adaptive-CSS bundle and the frame's own defs partial — both are
    searched), and the preset's declared topology (for the lanes exemption)."""

    svg: str
    uid: str
    css: str
    topology: str


_CACHE: dict[str, _Rendered] = {}


def _render(name: str) -> _Rendered:
    if name in _CACHE:
        return _CACHE[name]

    def _build() -> _Rendered:
        bs = resolve_bundled_spec("diagram", name)
        spec = ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant=_VARIANT,
            ground="opaque",
            palette="fixed",
            diagram=bs.value,
        )
        svg = compose(spec).svg
        uid_m = re.search(r'class="(hw-[0-9a-f]+)-', svg)
        assert uid_m, f"{name}: composed SVG carries no uid-prefixed class"
        css = "\n".join(re.findall(r"<style>(.*?)</style>", svg, re.S))
        return _Rendered(svg=svg, uid=uid_m.group(1), css=css, topology=str(bs.value.get("topology") or ""))

    rendered = _with_retry(_build)
    _CACHE[name] = rendered
    return rendered


# ── derived, config-sourced vocabulary (never hardcoded content) ───────────


def _allowed_dash_literals() -> frozenset[str]:
    """Every dasharray literal the kit is allowed to emit, derived from
    ``diagram-frame.yaml`` (connector/track/lane constants) and
    ``registries/idioms.yaml`` (``dress_textures``), plus the ONE dasharray
    that is a template literal rather than a config knob: the sequence
    lifeline dash (``-life``/``-lifeh`` in primer-defs.j2) — read straight
    from the template source so a chassis edit can't silently drift this set."""
    cfg = load_diagram_config()
    connector = cfg["connector"]
    track = cfg["track"]
    values: set[str] = {
        str(connector["dash"]),
        str(track["march_dash"]),
        str(track["return_dash"]),
        str(track["muted_dash"]),
    }
    if "return_drift_dash" in track:
        values.add(str(track["return_drift_dash"]))
    if "legend_dash" in track:
        values.add(str(track["legend_dash"]))
    if cfg.get("lane_dash"):
        # Reciprocal-lane march override (gateway v4 specimen's longer dash;
        # see ``mo.lane_dress_applies`` / ``ConnectorPlacement.march_dash``).
        values.add(str(cfg["lane_dash"]))
    idioms = load_idioms()
    for texture in (idioms.get("dress_textures") or {}).values():
        if texture:
            values.add(str(texture))
    defs_src = _DIAGRAM_DEFS.read_text()
    life_m = re.search(r"-life \{[^}]*stroke-dasharray:\s*([^;]+);", defs_src)
    assert life_m, "could not locate the sequence lifeline dasharray in primer-defs.j2"
    values.add(life_m.group(1).strip())
    return frozenset(" ".join(v.split()) for v in values)


def _allowed_voice_sizes() -> frozenset[float]:
    """Every legal font-size, resolved from the primer paradigm's
    ``ParadigmDiagramConfig`` via the VOICE_CLASSES registry (chrome.py /
    resolvers/diagram.py's own coupling point) — never a hardcoded list."""
    diagram_cfg = load_paradigms()["primer"].diagram
    return frozenset(float(getattr(diagram_cfg, attr).size) for _, attr in VOICE_CLASSES)


def _reciprocal_accent_pair() -> frozenset[str]:
    """The forward/reverse duo a declared reciprocal edge pair (a
    manually-authored pair, or a ``direction: both`` auto-expansion) is
    documented to use together (diagram-frame.yaml ``lane_hues``) — the one
    exception to the one-accent law: a bidirectional "conversation" reads
    forward as accent, reverse as muted, every link of a chain sharing the
    same duo (never a per-edge rainbow of distinct accents). Only a
    non-negative slot emits a numeric ``-fl{i}`` class in the first place
    (``_accent_wire_classes`` excludes ``-fls``/``-connmuted`` by
    construction, same as the template's own ``>= 0`` branch) — the muted
    slot (-1, the gateway v4 specimen's response lane) contributes none,
    so the "duo" collapses to one class under the current binary law."""
    lane_hues = load_diagram_config()["lane_hues"]
    return frozenset(f"fl{i}" for i in (int(lane_hues["forward"]), int(lane_hues["reverse"])) if i >= 0)


# ── shared parsing helpers ──────────────────────────────────────────────────


def _brace_block(text: str, search_from: int) -> str | None:
    """Brace-matched body of the block starting at the first ``{`` at/after
    ``search_from`` (handles nested braces, e.g. ``@keyframes x { from { ... } }``)."""
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
                return text[brace + 1 : i]
    return None


_DASH_ATTR_RE = re.compile(r'stroke-dasharray="([^"]+)"')
_DASH_CSS_RE = re.compile(r"stroke-dasharray:\s*([^;}\"]+);")
_KEYFRAMES_START_RE = re.compile(r"@keyframes\s+([\w-]+)\s*(?=\{)")
_CIM_LEGAL_KEYFRAME_PROPS = frozenset({"transform", "opacity", "filter", "stroke-dashoffset", "stop-color"})
_NAME_TEXT_RE = re.compile(r'<text[^>]*\bclass="hw-[0-9a-f]+-(name|hname|mname)"[^>]*>([^<]*)</text>')
_TEXT_CLASS_RE = re.compile(r'<text[^>]*class="(hw-[0-9a-f]+)-([a-z]+)')
_STYLE_FILL_RE = re.compile(r'<(?:rect|circle)\b[^>]*\bstyle="[^"]*fill:')
_ELLIPSIS = "…"


def _accent_wire_classes(svg: str, uid: str) -> set[str]:
    """Distinct accent-indexed wire classes (``-fl{i}``, i numeric) used on
    ``-branch`` connector paths — the spine class (``-fls``) and neutral
    classes (``-connmuted``/``-tube``) are excluded by construction (they
    don't match the numeric-index pattern)."""
    out: set[str] = set()
    for m in re.finditer(rf'<path[^>]*\bclass="({re.escape(uid)}-branch[^"]*)"', svg):
        for tok in m.group(1).split():
            idx_m = re.fullmatch(rf"{re.escape(uid)}-fl(\d+)", tok)
            if idx_m:
                out.add(f"fl{idx_m.group(1)}")
    return out


# ── 1. NO masthead ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", _PRESET_NAMES)
def test_no_masthead(name: str) -> None:
    """The masthead-band mechanism (measure_masthead's title_lines, the
    ``<g data-hw-region="masthead">`` template branch) is retired: solver.py
    only ever measures it for a canvas-width reference, never populates the
    rendered header. Both structural signatures must stay absent — the
    region marker AND the ``-title`` voice class (masthead-exclusive; no
    other chrome uses it)."""
    r = _render(name)
    assert 'data-hw-region="masthead"' not in r.svg, f"{name}: masthead region rendered"
    assert f'class="{r.uid}-title"' not in r.svg, f"{name}: -title voice class rendered (masthead-only class)"


# ── 2. NO plate-swap ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", _PRESET_NAMES)
def test_no_plate_swap(name: str) -> None:
    """The retired ``plate_fill`` channel painted node backgrounds via an
    inline ``style="fill:..."`` attribute on the rect/circle element; card
    fills now flow ONLY through the -cardbg/-herobg/-circlebg/-herocirclebg
    classes."""
    r = _render(name)
    assert not _STYLE_FILL_RE.search(r.svg), (
        f'{name}: inline style="fill: on a rect/circle — retired plate_fill channel'
    )
    for cls in ("cardbg", "herobg", "circlebg", "herocirclebg"):
        pattern = re.compile(rf'<(?:rect|circle)\b[^>]*\bclass="{re.escape(r.uid)}-{cls}"[^>]*\bstyle=')
        assert not pattern.search(r.svg), f"{name}: .{r.uid}-{cls} element carries an inline style attr"


# ── 3. Kit dash grammar ──────────────────────────────────────────────────────


@pytest.mark.parametrize("name", _PRESET_NAMES)
def test_kit_dash_grammar(name: str) -> None:
    r = _render(name)
    allowed = _allowed_dash_literals()
    found = {" ".join(v.split()) for v in _DASH_ATTR_RE.findall(r.svg)}
    found |= {" ".join(v.split()) for v in _DASH_CSS_RE.findall(r.css)}
    rogue = found - allowed
    assert not rogue, f"{name}: dasharray literal(s) {sorted(rogue)} outside the kit set {sorted(allowed)}"


# ── 4. Kit terminals ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", _PRESET_NAMES)
def test_kit_terminals(name: str) -> None:
    """Every ``-mk`` marker path is a drawn, CLOSED chevron (``arrow_d`` —
    ``d`` ends with ``Z``) or the dot disc (``marker_path(kind="dot")`` — an
    arc-pair path, no ``Z``); no SVG ``<marker>`` element ever appears —
    diagrams draw their own terminals."""
    r = _render(name)
    assert "<marker" not in r.svg, f"{name}: <marker> element present — drawn chevrons/dots only"
    mk_re = re.compile(rf'<path d="([^"]+)" class="{re.escape(r.uid)}-mk[^"]*"')
    paths = mk_re.findall(r.svg)
    for d in paths:
        is_chevron = d.rstrip().endswith("Z")
        is_dot = d.count(" A ") >= 2
        assert is_chevron or is_dot, f"{name}: -mk path is neither a closed chevron nor a dot disc: {d!r}"


# ── 5. Typography ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", _PRESET_NAMES)
def test_typography_matches_voice_registry(name: str) -> None:
    r = _render(name)
    allowed = _allowed_voice_sizes()
    sizes = {float(v) for v in re.findall(r"font-size:\s*([\d.]+)px", r.css)}
    rogue = sizes - allowed
    assert not rogue, f"{name}: rogue font-size(s) {sorted(rogue)} outside the VOICE_CLASSES registry {sorted(allowed)}"


# ── 6. One-accent law ────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", _PRESET_NAMES)
def test_one_accent_law(name: str) -> None:
    """Non-lanes presets: the distinct accent-indexed wire classes on
    connectors number at most one (the spine), OR exactly the documented
    reciprocal forward/reverse duo (a bidirectional 'conversation' — the one
    config-declared exception; every link of a chain shares the same duo,
    never a per-edge rainbow). Lanes presets: wires stay fully neutral —
    zero accent classes."""
    r = _render(name)
    accents = _accent_wire_classes(r.svg, r.uid)
    if r.topology == "lanes":
        assert not accents, f"{name}: lanes wires must stay neutral, found accent classes {sorted(accents)}"
        return
    allowed_pair = _reciprocal_accent_pair()
    assert len(accents) <= 1 or accents == set(allowed_pair), (
        f"{name}: one-accent law violated — distinct accent wire classes {sorted(accents)} "
        f"(only the reciprocal duo {sorted(allowed_pair)} is exempt)"
    )


# ── 7. Motion legality ───────────────────────────────────────────────────────


@pytest.mark.parametrize("name", _PRESET_NAMES)
def test_motion_legality(name: str) -> None:
    """Every ``@keyframes`` block animates only CIM-legal channels
    (transform/opacity/filter, plus the diagram kit's stroke-dashoffset and
    stop-color-safe channels) — never a geometric attribute (cx/cy/r/d/
    width/height/x/y). ``prefers-reduced-motion`` is present whenever any
    animation exists."""
    r = _render(name)
    any_animation = False
    for m in _KEYFRAMES_START_RE.finditer(r.svg):
        any_animation = True
        body = _brace_block(r.svg, m.end())
        assert body is not None, f"{name}: unterminated @keyframes {m.group(1)}"
        props = set(re.findall(r"([a-zA-Z-]+)\s*:\s*[^;{}]+;", body))
        illegal = props - _CIM_LEGAL_KEYFRAME_PROPS
        assert not illegal, f"{name}: @keyframes {m.group(1)} animates non-CIM channel(s) {sorted(illegal)}"
    if any_animation:
        assert "@media (prefers-reduced-motion: reduce)" in r.svg, (
            f"{name}: animation present with no reduced-motion guard"
        )


# ── 8. Adaptive honesty (the one twin compose) ──────────────────────────────


def test_adaptive_honesty_frontier_serving() -> None:
    """The one adaptive-twin compose in this suite (frontier-serving, a
    fixed glyph-rich dag preset): the base ``#uid`` scope is the LIGHT face
    (porcelain is light-native — near luminance both exceeds the far
    luminance and clears an absolute light floor), and a spot-check of
    surface/ink/signal confirms each is actually RE-DECLARED in the far
    ``@media`` block (never silently held) and actually FLIPS (never a
    no-op copy of the near value)."""

    def _build() -> str:
        bs = resolve_bundled_spec("diagram", _ADAPTIVE_PRESET)
        spec = ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant=_VARIANT,
            ground="opaque",
            palette="adaptive",
            diagram=bs.value,
        )
        return compose(spec).svg

    svg = _with_retry(_build)

    uid_m = re.search(r'\bid="(hw-[0-9a-f]+)"', svg)
    assert uid_m, "adaptive twin carries no scoped root id"
    uid = uid_m.group(1)

    near_m = re.search(rf"#{re.escape(uid)} \{{ color-scheme: light dark;(.*?)\}}", svg, re.DOTALL)
    assert near_m, "no #uid near block found"
    near = near_m.group(1)

    # The FIRST @media(prefers-color-scheme) block is the main genome-bundle
    # far face (surface/ink/signal/etc, emitted in its own <style> tag before
    # the frame's defs partial); diagram-specific per-var far overrides
    # (--dna-flow-0, --dna-diagram-conn-muted) live in a LATER, separate
    # <style> tag and are out of scope for this spot-check.
    media_start = svg.find("@media (prefers-color-scheme")
    assert media_start != -1, "adaptive twin carries no far @media block"
    far = svg[media_start : svg.find("</style>", media_start)]

    def _var(fragment: str, name: str) -> str | None:
        m = re.search(rf"{re.escape(name)}\s*:\s*([^;]+);", fragment)
        return m.group(1).strip() if m else None

    near_surface = _var(near, "--dna-surface")
    far_surface = _var(far, "--dna-surface")
    assert near_surface is not None and far_surface is not None, "surface var missing on a face"
    assert relative_luminance(near_surface) > relative_luminance(far_surface), (
        f"base scope should be the LIGHT face: near={near_surface} far={far_surface}"
    )
    assert relative_luminance(near_surface) > 0.5, f"base scope {near_surface} does not read as the light face"

    for role_var in ("--dna-surface", "--dna-ink-primary", "--dna-signal"):
        near_v = _var(near, role_var)
        far_v = _var(far, role_var)
        assert far_v is not None, f"{role_var}: not re-declared in the far block — held, never flips"
        assert far_v != near_v, f"{role_var}: far block copies the near value ({near_v}) — no actual flip"


# ── 9. No truncated IDENTITY ─────────────────────────────────────────────────


@pytest.mark.parametrize("name", _PRESET_NAMES)
def test_no_truncated_identity(name: str) -> None:
    """A node's own identity text (-name/-hname/-mname) never ends in an
    ellipsis — sizing.py's promise is that names never truncate (descs wrap,
    chips cap); this pins that promise at the rendered-output level across
    every bundled preset, catching any preset/layout combination where the
    upstream width reservation falls short."""
    r = _render(name)
    for cls, content in _NAME_TEXT_RE.findall(r.svg):
        assert not content.rstrip().endswith(_ELLIPSIS), f"{name}: -{cls} run truncated: {content!r}"


# ── 10. Every uid-prefixed text class carries a paint rule (LAW 2, generalized) ──


@pytest.mark.parametrize("name", _PRESET_NAMES)
def test_every_text_class_carries_paint_rule(name: str) -> None:
    """LAW 2, generalized from a 4-preset pin to the full kit sweep: a voice
    class with no fill/stroke rule inherits SVG default BLACK — invisible on
    a dark ground. Every distinct (uid, class) pair emitted on a ``<text>``
    element must have its own CSS rule declaring ``fill`` or ``stroke``."""
    r = _render(name)
    classes = {(m.group(1), m.group(2)) for m in _TEXT_CLASS_RE.finditer(r.svg)}
    assert classes, f"{name}: no text-class runs found — sweep is vacuous for this preset"
    for uid, cls in sorted(classes):
        pattern = re.compile(r"\." + re.escape(f"{uid}-{cls}") + r"\b[^}]*")
        rules = " ".join(m.group(0) for m in pattern.finditer(r.css))
        assert "fill" in rules or "stroke" in rules, (
            f"{name}: .{uid}-{cls} has no fill/stroke rule — invisible text risk"
        )


# ── coverage guard ───────────────────────────────────────────────────────────


def test_preset_sweep_is_nonempty() -> None:
    """A collapsed or partially-loaded preset store would silently vacuous
    every parametrized test above rather than failing loud."""
    assert len(_PRESET_NAMES) >= 30, f"only {len(_PRESET_NAMES)} bundled diagram presets found — sweep may be broken"
