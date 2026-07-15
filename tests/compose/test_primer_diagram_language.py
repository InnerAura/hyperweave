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


def test_dark_gradient_stops_match_law(emitted_dark: str) -> None:
    v = _DARK["vars"]
    cf = re.search(
        r'-cf"[^>]*>\s*<stop offset="0" stop-color="([^"]+)"/>\s*<stop offset="1" stop-color="([^"]+)"', emitted_dark
    )
    assert cf, "cf gradient missing"
    assert (cf.group(1), cf.group(2)) == (v["--hw-card-hi"].strip(), v["--hw-card-lo"].strip())


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
