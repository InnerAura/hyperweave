"""The primer diagram language, validated attribute-by-attribute.

``primer_diagram_language.html`` is the total aesthetic + spatial law for
primer diagrams — every voice, material, wire class, filter primitive,
marker, knot and timing parameter. Its machine extraction lives at
``tests/fixtures/primer_diagram_language.json`` (re-extract via
``scripts/extract_specimen_fixtures.py``; the html itself never ships).

These tests compose the axial language diagram on the porcelain light face
and compare the EMITTED defs/CSS against the law, so an engine drift in any
"tiny detail" — a stroke width, a dash rhythm, a flood opacity — fails here
instead of waiting for a human review round.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_diagram_config
from hyperweave.core.models import ComposeSpec

_PORCELAIN = json.loads((Path(__file__).parents[1] / "fixtures" / "primer_diagram_language.json").read_text())[
    "porcelain"
]
_LAW = _PORCELAIN["light"]
_DARK = _PORCELAIN["dark"]

# language class -> engine class (primer-defs.j2 vocabulary)
CLASS_MAP = {
    "name": "name",
    "hname": "hname",
    "sub": "ndesc",
    "hsub": "hdesc",
    "ml": "elbl",
    "cap": "cap",
    "chipt": "tag",
    "card": "cardbg",
    "hero": "herobg",
    "chip": "chipbg",
}
_FONT = re.compile(r"(\d+) ([\d.]+)px '([^']+)'")

# Hero-ring ruling (2026-07-13, v04/decisions/diagram-law-enrollment-audit.md):
# role:hero now rings in the genome accent by default (stroke var(--dna-signal)
# on herobg/herocirclebg); hero_ring:quiet is the spec-level opt-out back to the
# flat family border. primer_diagram_language.json is a byte-for-byte machine
# extraction of the html sheet as authored BEFORE this ruling, so its "hero"
# class still records the flat border it superseded — the fixture stays an
# accurate transcription of that source and is not edited. Laws never weaken
# silently: this is the documented amendment, scoped to exactly the one
# property the ruling changed (hero.stroke); hero.fill and every other
# class/property in CLASS_MAP still grades against the sheet unchanged.
_HERO_RING_AMENDMENT = {("hero", "stroke")}


@pytest.fixture(scope="module")
def emitted() -> tuple[dict[str, dict[str, str]], dict[str, str], str]:
    spec = resolve_bundled_spec("diagram", "hub").value
    svg = compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="bare",
            palette="fixed",
            surface_face="light",
            diagram=spec,
        )
    ).svg
    classes: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"\.hw-[0-9a-f]+-([a-z0-9]+)(?:\s*,[^{]*)?\s*\{([^}]*)\}", svg):
        props = dict(
            (k.strip(), " ".join(v.split()))
            for k, v in (pair.split(":", 1) for pair in m.group(2).split(";") if ":" in pair)
        )
        prev = classes.setdefault(m.group(1), {})
        for k, v in props.items():
            prev.setdefault(k, v)
    root = {m.group(1): m.group(2).strip() for m in re.finditer(r"(--dna-[a-z0-9-]+):\s*([^;]+);", svg)}
    return classes, root, svg


def _resolve(value: str, root: dict[str, str]) -> str:
    m = re.match(r"var\((--[a-z0-9-]+)(?:,\s*([^)]+))?\)", value or "")
    if not m:
        return (value or "").upper()
    return (root.get(m.group(1), m.group(2) or value)).strip().upper()


def _law_color(value: str) -> str:
    m = re.match(r"var\((--hw-[a-z-]+)\)", value or "")
    if m:
        return _LAW["vars"].get(m.group(1), value).strip().upper()
    return (value or "").upper()


@pytest.mark.parametrize(("language_cls", "engc"), sorted(CLASS_MAP.items()))
def test_class_matches_law(language_cls: str, engc: str, emitted: tuple[dict, dict, str]) -> None:
    classes, root, _svg = emitted
    lc, ec = _LAW["classes"].get(language_cls, {}), classes.get(engc, {})
    assert ec, f"engine emits no .{engc} for language class {language_cls}"
    fails: list[str] = []
    lf = _FONT.search(lc.get("font", ""))
    if lf:
        ef = _FONT.search(ec.get("font", "")) if ec.get("font") else None
        size = ef.group(2) if ef else ec.get("font-size", "").replace("px", "")
        weight = ef.group(1) if ef else ec.get("font-weight", "")
        fam = ef.group(3) if ef else (re.search(r"'([^']+)'", ec.get("font-family", "")) or [None, ""])[1]
        if float(size or 0) != float(lf.group(2)):
            fails.append(f"font-size {size} vs {lf.group(2)}")
        if (weight or "") != lf.group(1):
            fails.append(f"font-weight {weight} vs {lf.group(1)}")
        if fam and fam != lf.group(3):
            fails.append(f"font-family {fam} vs {lf.group(3)}")

    def _num(v: str) -> str:
        s = v.strip()
        if re.match(r"^\.?\d*\.?\d+(em|px)?$", s):
            bare = s.rstrip("empx")
            return f"{float('0' + bare) if bare.startswith('.') else float(bare):g}"
        return s

    for prop in ("letter-spacing", "stroke-width", "stroke-dasharray", "stroke-linecap"):
        lv, ev = lc.get(prop, ""), ec.get(prop, "")
        if lv and ev and _num(lv) != _num(ev):
            fails.append(f"{prop} {ev!r} vs {lv!r}")
    for prop in ("fill", "stroke"):
        if (language_cls, prop) in _HERO_RING_AMENDMENT:
            continue
        lv, ev = lc.get(prop, ""), ec.get(prop, "")
        if lv and ev and not lv.startswith("Canvas") and _law_color(lv) != _resolve(ev, root):
            fails.append(f"{prop} {_resolve(ev, root)} vs {_law_color(lv)}")
    assert not fails, f"{language_cls}->{engc}: " + "; ".join(fails)


def test_lift_filter_matches_law(emitted: tuple[dict, dict, str]) -> None:
    _c, _r, svg = emitted
    got = sorted(
        re.findall(
            r'<feDropShadow dx="([\d.]+)" dy="([\d.]+)" stdDeviation="([\d.]+)"[^>]*flood-opacity="([\d.]+)"', svg
        )
    )
    want = sorted((p["dx"], p["dy"], p["stdDeviation"], p["flood-opacity"]) for p in _LAW["filters"].get("lift", []))
    if want:
        assert got == want, f"lift primitives {got} vs law {want}"


def test_marker_matches_law(emitted: tuple[dict, dict, str]) -> None:
    _c, _r, svg = emitted
    lm = _LAW["markers"].get("ac") or _LAW["markers"].get("aa") or {}
    em = re.search(r'<marker[^>]*refX="([\d.]+)"[^>]*markerWidth="([\d.]+)"', svg)
    if lm and em:
        assert (em.group(1), em.group(2)) == (lm.get("refX"), lm.get("markerWidth")), (
            f"marker refX/width {em.groups()} vs law ({lm.get('refX')}, {lm.get('markerWidth')})"
        )


def test_march_timing_matches_law(emitted: tuple[dict, dict, str]) -> None:
    _c, _r, svg = emitted
    off = re.search(r"stroke-dashoffset:\s*(-\d+)", svg)
    if off and _LAW["anim"].get("march_offset"):
        assert off.group(1) == _LAW["anim"]["march_offset"], (
            f"march offset {off.group(1)} vs law {_LAW['anim']['march_offset']}"
        )


# ── dark face: the language's plate physics ──────────────────────────────────────────


@pytest.fixture(scope="module")
def emitted_dark() -> str:
    spec = resolve_bundled_spec("diagram", "hub").value
    return compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="opaque",
            palette="fixed",
            surface_face="dark",
            diagram=spec,
        )
    ).svg


def test_dark_cards_ride_plate_physics(emitted_dark: str) -> None:
    # Cards + heroes fill the cf gradient, stroke the es rim, sit on the seat.
    dark_rule = re.findall(r"\.hw-[0-9a-f]+-cardbg[^{]*\{[^}]*url\(#hw-[0-9a-f]+-cf\)[^}]*\}", emitted_dark)
    assert dark_rule, "dark cards must fill the cf gradient"
    assert "url(#" in dark_rule[0] and "-es)" in dark_rule[0], "dark cards must stroke the es rim"
    assert re.search(r"-cardbg[^}]*url\(#hw-[0-9a-f]+-seat\)", emitted_dark), "dark cards must sit on the seat"


# Card-ramp ruling (2026-07-15, owner triage after the banding report): the
# sheet's card_hi/card_lo pair spans only ~4/255 per channel — below display
# quantization resolution, so every renderer posterizes the face into flat
# bands with a mid-card seam (measured on the sheet AND the engine render).
# The ruling widens each variant's pair symmetrically around its own midpoint
# to >=10/255 max-channel delta, hue direction preserved — the top-lit intent
# the sheet AUTHORED, at a delta the medium can actually render. The fixture
# stays a byte-accurate transcription of the sheet as authored (same rule as
# the hero-ring amendment above); the engine grades against the genome's
# amended pair, and the delta law below pins the ramp for every variant.
def test_dark_gradient_stops_match_law(emitted_dark: str) -> None:
    v = _DARK["vars"]
    cf = re.search(
        r'-cf"[^>]*>\s*<stop offset="0" stop-color="([^"]+)"/>\s*'
        r'<stop offset="([\d.]+)" stop-color="([^"]+)"/>\s*<stop offset="1" stop-color="([^"]+)"',
        emitted_dark,
    )
    assert cf, "cf gradient missing its 3-stop eased ramp"
    genome_dark = _genome_diagram_dark("porcelain")
    assert (cf.group(1), cf.group(4)) == (genome_dark["card_hi"], genome_dark["card_lo"])
    # The eased mid stop is DERIVED, never authored: hi mixed toward lo by the
    # chassis fraction at the chassis offset (the strip-plate recipe).
    material = load_diagram_config().get("material") or {}
    assert cf.group(2) == str(material.get("ramp_mid_offset", "0.4"))
    mix_t = float(material.get("ramp_mid_mix", 0.58))
    hi_rgb, lo_rgb = _rgb(genome_dark["card_hi"]), _rgb(genome_dark["card_lo"])
    want_mid = "#{:02X}{:02X}{:02X}".format(*(round(a + (b - a) * mix_t) for a, b in zip(hi_rgb, lo_rgb, strict=True)))
    assert cf.group(3) == want_mid, f"card_mid {cf.group(3)} vs derived {want_mid}"
    # The amended pair keeps the sheet's hue direction: per-channel deltas
    # scale uniformly from the sheet pair, so sign and ratio survive.
    sheet_hi, sheet_lo = _rgb(v["--hw-card-hi"].strip()), _rgb(v["--hw-card-lo"].strip())
    hi, lo = _rgb(genome_dark["card_hi"]), _rgb(genome_dark["card_lo"])
    sheet_deltas = [a - b for a, b in zip(sheet_hi, sheet_lo, strict=True)]
    amended_deltas = [a - b for a, b in zip(hi, lo, strict=True)]
    for sheet_d, d in zip(sheet_deltas, amended_deltas, strict=True):
        assert (sheet_d > 0) == (d > 0) or (sheet_d == 0 and abs(d) <= 1), "hue direction diverged from the sheet"


def _rgb(hexstr: str) -> tuple[int, int, int]:
    h = hexstr.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _lum(c: tuple[int, int, int]) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _genome_diagram_dark(variant: str) -> dict[str, str]:
    genome_path = Path(__file__).parents[2] / "src" / "hyperweave" / "data" / "genomes" / "primer.json"
    payload = json.loads(genome_path.read_text())
    block = payload["variant_overrides"][variant]["diagram_dark"]
    assert isinstance(block, dict)
    return {k: str(val) for k, val in block.items()}


@pytest.mark.parametrize("variant", ["porcelain", "noir", "carbon", "space", "anvil", "cream", "dusk", "petrol"])
def test_card_ramp_renders_continuous(variant: str) -> None:
    """The card-ramp law: every variant's cf pair spans >=10/255 on its widest
    channel (below that, displays posterize the face into a banded two-tone)
    and the luminance ladder holds — ground < card_lo < card_hi < chip."""
    d = _genome_diagram_dark(variant)
    hi, lo = _rgb(d["card_hi"]), _rgb(d["card_lo"])
    assert max(abs(a - b) for a, b in zip(hi, lo, strict=True)) >= 10, (
        f"{variant}: cf ramp below quantization threshold"
    )
    assert _lum(_rgb(d["ground"])) < _lum(lo) < _lum(hi) < _lum(_rgb(d["chip"])), f"{variant}: ladder order broken"


def test_dark_seat_matches_law(emitted_dark: str) -> None:
    want = _DARK["filters"]["seat"][0]
    got = re.search(
        r'-seat"[^>]*>\s*<feDropShadow dx="(\d+)" dy="(\d+)" stdDeviation="(\d+)"[^>]*flood-opacity="([\d.]+)"',
        emitted_dark,
    )
    assert got, "seat filter missing"
    assert got.groups() == (want["dx"], want["dy"], want["stdDeviation"], want["flood-opacity"])


def test_dark_ink_family_matches_law(emitted_dark: str) -> None:
    v = _DARK["vars"]
    assert f"--dna-ink-primary: {v['--hw-ink'].strip()}" in emitted_dark
    assert f"--dna-signal: {v['--hw-accent'].strip()}" in emitted_dark
    hname = re.findall(r"\.hw-[0-9a-f]+-hname \{ fill: ([^;}]+)", emitted_dark)
    assert v["--hw-ink-hero"].strip() in [h.strip() for h in hname], hname


# ── surface invariance: one look through every door ──────────────────────────
#
# The rendered look is a pure function of (spec, genome, variant, scheme) —
# surface mode and delivery adapter choose packaging, never appearance. The
# material law fires on every render whose scheme includes the dark face:
# the baked dark face, a fixed dark-substrate variant, and the dark @media
# branch of an adaptive render (normalized ordering: the base scope is always
# the light face, the media query always dark). These tests enroll every
# surface preset and substrate in that law, so a render path that silently
# drops the material — the flat-README regression — fails here.

_HUB_SPEC = resolve_bundled_spec("diagram", "hub").value
_UID_NORM = re.compile(r"hw-[0-9a-f]{8}")
_DARK_WRAPPER = "@media (prefers-color-scheme: dark) {"

_SURFACES = {
    "plate": ("opaque", "fixed"),
    "inlay": ("bare", "adaptive"),
    "twin": ("opaque", "adaptive"),
}


def _compose_surface_svg(variant: str, ground: str, palette: str, face: str = "") -> str:
    return compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant=variant,
            ground=ground,
            palette=palette,
            surface_face=face,
            diagram=_HUB_SPEC,
        )
    ).svg


def _material_block(svg: str) -> list[str]:
    """The dark material override block as uid-normalized lines: from the
    ``#UID { --dna-signal:`` rule to the block's end (the wrapper's lone ``}``
    on an adaptive render, ``</style>`` on a committed one). Empty when the
    render carries no material."""
    out: list[str] = []
    taking = False
    for ln in _UID_NORM.sub("UID", svg).splitlines():
        if not taking and ln.startswith("#UID { --dna-signal:"):
            taking = True
        if taking:
            if ln.strip() in ("}", "</style>"):
                break
            if ln.strip():
                out.append(ln)
    return out


def _material_scope(svg: str) -> str:
    """``none`` (no material block), ``committed`` (declared bare, wins the
    cascade on the render's one scheme) or ``dark-branch`` (inside the dark
    @media wrapper of an adaptive render)."""
    lines = _UID_NORM.sub("UID", svg).splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("#UID { --dna-signal:"):
            prev = next((p for p in reversed(lines[:i]) if p.strip()), "")
            return "dark-branch" if prev.strip() == _DARK_WRAPPER else "committed"
    return "none"


@pytest.mark.parametrize(("variant", "substrate"), [("porcelain", "light"), ("noir", "dark")])
@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_material_presence_matrix(variant: str, substrate: str, surface: str) -> None:
    """Every surface preset resolves the material by SCHEME, never delivery:
    adaptive surfaces carry it in the dark branch, a fixed surface carries it
    exactly when the variant's substrate is dark. The SEAT is ground-keyed on
    top of that: a shadow casts ink outside the card, so it fires only on a
    plate the artifact OWNS — a bare ground rides the lift+grain chain
    instead (no drop shadows on unowned grounds)."""
    ground, palette = _SURFACES[surface]
    svg = _compose_surface_svg(variant, ground, palette)
    scope = _material_scope(svg)
    has_defs = '-cf"' in svg
    has_material = palette == "adaptive" or substrate == "dark"
    if palette == "adaptive":
        assert scope == "dark-branch", f"{surface}/{variant}: material must ride the dark @media branch"
        assert has_defs, f"{surface}/{variant}: cf/es defs missing"
    elif substrate == "dark":
        assert scope == "committed", f"{surface}/{variant}: fixed dark substrate must commit the material"
        assert has_defs, f"{surface}/{variant}: cf/es defs missing"
    else:
        assert scope == "none" and not has_defs, f"{surface}/{variant}: light committed render must stay paper-flat"
    if has_material and ground == "opaque":
        assert '-seat"' in svg and "-seat)" in svg, f"{surface}/{variant}: owned plate must seat its cards"
        assert "feTurbulence" in svg, f"{surface}/{variant}: seat chain missing its grain pass"
    elif has_material:
        assert '-liftg"' in svg and "-liftg)" in svg, f"{surface}/{variant}: bare material must ride lift+grain"
        assert '-seat"' not in svg and "-seat)" not in svg, f"{surface}/{variant}: seat shadow on an unowned ground"
        assert "feTurbulence" in svg, f"{surface}/{variant}: liftg chain missing its grain pass"
    else:
        assert '-seat"' not in svg and "-seat)" not in svg and '-liftg"' not in svg, (
            f"{surface}/{variant}: material filters on a light committed render"
        )
        assert "feTurbulence" not in svg, f"{surface}/{variant}: grain on the light face"


@pytest.mark.parametrize("variant", ["porcelain", "noir"])
@pytest.mark.parametrize("surface", ["inlay", "twin"])
def test_adaptive_dark_branch_equals_baked_dark_face(variant: str, surface: str) -> None:
    """The invariance property itself: the dark branch an adaptive render
    ships is rule-for-rule the baked dark face OF THE SAME GROUND — same
    material, same family, through every door. (The seat is ground-keyed, so
    the baked reference must own or not own its plate exactly as the surface
    under test does.)"""
    ground, palette = _SURFACES[surface]
    adaptive_block = _material_block(_compose_surface_svg(variant, ground, palette))
    baked_block = _material_block(_compose_surface_svg(variant, ground, "fixed", face="dark"))
    assert adaptive_block, f"{surface}/{variant}: adaptive render carries no material block"
    assert adaptive_block == baked_block, f"{surface}/{variant}: dark branch diverges from the baked dark face"


def test_fixed_dark_plate_equals_baked_dark_face() -> None:
    """A fixed-palette dark-substrate plate has no adaptivity excuse — it
    commits the same material block the baked dark face (same ground) bakes."""
    plate_block = _material_block(_compose_surface_svg("noir", "opaque", "fixed"))
    baked_block = _material_block(_compose_surface_svg("noir", "opaque", "fixed", face="dark"))
    assert plate_block, "noir plate carries no material block"
    assert plate_block == baked_block, "noir plate material diverges from the baked dark face"


@pytest.mark.parametrize("variant", ["porcelain", "noir"])
def test_adaptive_light_base_stays_flat_paper(variant: str) -> None:
    """The adaptive base scope is the light face law: flat var-driven card
    fills, the material urls referenced nowhere outside the dark branch."""
    svg = _UID_NORM.sub("UID", _compose_surface_svg(variant, "bare", "adaptive"))
    assert ".UID-cardbg { fill: var(--dna-surface-alt); stroke: var(--dna-border); }" in svg
    assert svg.count("url(#UID-cf)") == 1, "cf gradient must be referenced exactly once — inside the dark branch"


def test_baked_light_face_carries_no_material() -> None:
    svg = _compose_surface_svg("porcelain", "bare", "fixed", face="light")
    assert '-cf"' not in svg and '-seat"' not in svg
    assert _material_scope(svg) == "none"
