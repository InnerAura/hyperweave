"""hw:chromatic-surface — the artifact's own account of what a theme may repaint.

The gap this closes: an agent handed a composed SVG had no way to know which
paint answers to a `--dna-*` override, so it overrode everything and watched a
third of the picture refuse to move. The manifest states it up front.

Two claims carry the weight, and both are gated here rather than trusted:
the chassis token list is exactly the artifact's own declarations, and no
render puts colour in an attribute the `sinks` list does not name.
"""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree

import pytest

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_chromatic_surface
from hyperweave.core.models import ComposeSpec

# An attribute whose VALUE is a literal colour. Deliberately keyed on the value,
# not the name: stroke-width and color-interpolation-filters are not paint.
_COLOR_ATTR = re.compile(r'\b([a-zA-Z-]+)="(#[0-9A-Fa-f]{3,8}|rgba?\([^)]*\))"')
_DECLARED = re.compile(r"(--dna-[a-z0-9-]+)\s*:")
_ZONE = re.compile(r"<hw:zone\b([^>]*)/>")
_ATTR = re.compile(r'([a-z-]+)="([^"]*)"')

# A preset with brand marks, so the brand zone has something to report.
_BRANDED = resolve_bundled_spec("diagram", "fanout-bilateral").value

_DIAGRAM = {
    "topology": "pipeline",
    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
    "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
}


def _declared_tokens(svg: str) -> set[str]:
    """The artifact's own `--dna-*` declarations, read with the manifest block
    removed so the assertion can never be satisfied by the claim itself."""
    body = re.sub(r"<hw:chromatic-surface\b.*?</hw:chromatic-surface>", "", svg, flags=re.S)
    return set(_DECLARED.findall(body))


def _zones(svg: str) -> dict[str, dict[str, str]]:
    """The manifest's zone rows, keyed by id."""
    block = re.search(r"<hw:chromatic-surface\b.*?</hw:chromatic-surface>", svg, re.S)
    assert block, "every tier-3 artifact declares its chromatic surface"
    return {dict(_ATTR.findall(attrs))["id"]: dict(_ATTR.findall(attrs)) for attrs in _ZONE.findall(block.group(0))}


def _sweep_specs() -> list[dict[str, Any]]:
    """Frames x genomes x variants x surface modes — the axes a manifest claim
    has to survive, not one happy-path render."""
    specs: list[dict[str, Any]] = []
    for genome, variants in (("primer", ("porcelain", "noir", "cream", "petrol")), ("brutalist", ("celadon", "pulse"))):
        for variant in variants:
            for frame in ("badge", "strip", "icon", "divider", "marquee", "stats", "chart"):
                specs.append(
                    {"type": frame, "genome_id": genome, "variant": variant, "title": "BUILD", "value": "passing"}
                )
    connectors = resolve_bundled_spec("matrix", "connectors").value
    for variant in ("porcelain", "noir"):
        for ground, palette in (("", ""), ("opaque", "fixed"), ("bare", "adaptive"), ("opaque", "adaptive")):
            base = {"genome_id": "primer", "variant": variant, "ground": ground, "palette": palette}
            specs.append({**base, "type": "diagram", "diagram": _DIAGRAM})
            specs.append({**base, "type": "matrix", "connector_data": connectors})
    specs.append({"type": "diagram", "genome_id": "primer", "diagram": _BRANDED})
    specs.append({"type": "receipt", "genome_id": "primer"})
    return specs


def _rendered_sweep() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for kwargs in _sweep_specs():
        label = f"{kwargs['type']}/{kwargs.get('genome_id')}/{kwargs.get('variant', '-')}"
        try:
            out.append((label, compose(ComposeSpec(**kwargs)).svg))
        except Exception:  # an unsupported combination is not this suite's subject
            continue
    assert len(out) > 40, "the sweep must actually cover the axes it claims"
    return out


# ── the anti-drift gate ──────────────────────────────────────────────────


def test_no_render_hides_colour_in_an_unnamed_attribute() -> None:
    """The claim `sinks` makes is that grepping those four attributes yields
    every literal paint in the file. A template that starts writing colour into
    a fifth attribute breaks that promise silently — so it breaks here first."""
    sinks = set(load_chromatic_surface()["sinks"])
    offenders: dict[str, set[str]] = {}
    for label, svg in _rendered_sweep():
        for attr, _value in _COLOR_ATTR.findall(svg):
            if attr not in sinks:
                offenders.setdefault(attr, set()).add(label)
    assert not offenders, (
        f"literal colour in attributes the manifest does not name: "
        f"{ {a: sorted(v)[:3] for a, v in offenders.items()} } — add them to "
        f"data/config/chromatic-surface.yaml:sinks"
    )


def test_every_named_sink_is_one_the_engine_actually_uses() -> None:
    """The other direction: a sink listed but never emitted is a stale claim
    that sends an agent grepping for nothing."""
    sinks = set(load_chromatic_surface()["sinks"])
    seen: set[str] = set()
    for _label, svg in _rendered_sweep():
        seen.update(attr for attr, _v in _COLOR_ATTR.findall(svg))
    assert sinks <= seen, f"sinks names attributes no render emits: {sorted(sinks - seen)}"


# ── the chassis zone is a measurement, not a list to maintain ────────────


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"type": "diagram", "genome_id": "primer", "diagram": _DIAGRAM}, id="diagram"),
        pytest.param({"type": "badge", "genome_id": "brutalist", "title": "BUILD", "value": "passing"}, id="badge"),
        pytest.param({"type": "strip", "genome_id": "primer", "title": "repo", "value": "STARS:1"}, id="strip"),
    ],
)
def test_chassis_tokens_equal_the_artifacts_own_declarations(kwargs: dict[str, Any]) -> None:
    """Set equality both ways — a token claimed but not declared is a lie, and
    a token declared but not claimed is a gap the agent pays for."""
    svg = compose(ComposeSpec(**kwargs)).svg
    chassis = _zones(svg)["chassis"]
    claimed = set(chassis["tokens"].split())
    assert claimed == _declared_tokens(svg)
    assert int(chassis["count"]) == len(claimed)


def test_chassis_equals_the_declarations_across_every_swept_render() -> None:
    """The same set equality over frames x genomes x variants x surfaces. This
    is the gate on `frame_tokens`: a defs template that starts declaring a new
    custom property fails here until the config names it."""
    mismatches: dict[str, dict[str, list[str]]] = {}
    for label, svg in _rendered_sweep():
        claimed = set(_zones(svg)["chassis"]["tokens"].split())
        declared = _declared_tokens(svg)
        if claimed != declared:
            mismatches[label] = {
                "claimed_not_declared": sorted(claimed - declared),
                "declared_not_claimed": sorted(declared - claimed),
            }
    assert not mismatches, f"chassis zone disagrees with the artifact's own stylesheet: {mismatches}"


def test_chassis_tracks_the_adaptive_swap() -> None:
    """The adaptive surface rewrites the whole genome CSS layer after the
    context is built. Measuring before that would report the plate's tokens."""
    adaptive = compose(
        ComposeSpec(type="diagram", genome_id="primer", diagram=_DIAGRAM, ground="bare", palette="adaptive")
    ).svg
    chassis = _zones(adaptive)["chassis"]
    assert set(chassis["tokens"].split()) == _declared_tokens(adaptive)


# ── the fixed zones ──────────────────────────────────────────────────────


def test_material_zone_names_its_sinks_and_says_why() -> None:
    svg = compose(ComposeSpec(type="diagram", genome_id="primer", diagram=_DIAGRAM)).svg
    material = _zones(svg)["material"]
    assert material["capability"] == "fixed"
    assert set(material["sinks"].split()) == set(load_chromatic_surface()["sinks"])
    assert "var()" in material["reason"]


def test_brand_zone_lists_the_marks_and_is_absent_without_them() -> None:
    with_brands = compose(ComposeSpec(type="diagram", genome_id="primer", diagram=_BRANDED)).svg
    brand = _zones(with_brands)["brand"]
    assert brand["capability"] == "fixed"
    assert brand["glyphs"].split()
    assert int(brand["count"]) == len(brand["glyphs"].split())

    plain = compose(ComposeSpec(type="diagram", genome_id="primer", diagram=_DIAGRAM)).svg
    assert "brand" not in _zones(plain), "an artifact with no brand marks must not claim any"


def test_chassis_is_the_only_writable_zone() -> None:
    svg = compose(ComposeSpec(type="diagram", genome_id="primer", diagram=_BRANDED)).svg
    zones = _zones(svg)
    writable = {name for name, zone in zones.items() if zone["capability"] == "chromatic-override"}
    assert writable == {"chassis"}


# ── it does not break the artifact ───────────────────────────────────────


def test_the_manifest_keeps_the_document_well_formed() -> None:
    """Invariant 14 — the zone attributes carry prose and token lists."""
    for _label, svg in _rendered_sweep():
        ElementTree.fromstring(svg)  # our own output, not untrusted input


def test_the_manifest_does_not_change_artifact_identity() -> None:
    """The envelope id is sha256(payload); the manifest sits outside the
    payload, so a re-render of the same spec keeps the same id."""
    from hyperweave.core.envelope import extract_envelope

    spec = ComposeSpec(type="diagram", genome_id="primer", diagram=_DIAGRAM)
    first = extract_envelope(compose(spec).svg) or {}
    second = extract_envelope(compose(spec).svg) or {}
    assert first["id"] == second["id"]
    assert "chromatic" not in str(first).lower()
