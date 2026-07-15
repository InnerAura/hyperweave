"""Specimen-parity harness: the engine must recreate the diagrams-v3 prototypes.

Ground truth: fixtures extracted from ``v04/alpha/v04a6/diagrams-v3/**`` by
``scripts/extract_specimen_fixtures.py``. Laws live in ``parity/laws.py`` as
engine-agnostic (law, tolerance, evidence) records.

Two test families:
- SELF laws: every specimen satisfies the laws when graded directly — this
  pins the graders themselves (a failure here is a detector bug, never an
  engine bug).
- PARITY laws: the engine render of each prototype-mapped preset satisfies
  the same laws against the specimen's fixture. Red entries are the
  parity work queue; never weaken a law to pass one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.diagram.input import coerce_diagram_input
from hyperweave.compose.diagram.solver import apply_spec_chassis
from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_diagram_config, load_paradigms
from hyperweave.core.diagram import layout_slug
from hyperweave.core.models import ComposeSpec
from hyperweave.core.paradigm import DiagramTopologyChassis

from .parity.laws import geometry_laws, law_twin_tokens
from .parity.svgfacts import Facts, PathEl, css_tokens, parse_svg

_REPO = Path(__file__).resolve().parents[2]
_FIXTURES = _REPO / "tests" / "fixtures" / "specimens"

# Every diagrams-v3 specimen is recreated by ONE preset that shares its name:
# fixture name ≡ preset name (the board is 1:1). So there is no map and no gap
# mechanism — the fixture stem IS the preset id, and each fixture's ``source:``
# field is the only place the authored specimen filename appears. Importers and
# both parity families read this one tuple.
PARITY_NAMES: tuple[str, ...] = tuple(
    sorted(pth.stem for pth in _FIXTURES.glob("*.json") if not pth.stem.startswith("twin-"))
)

TWIN_VARIANTS = ("porcelain", "carbon", "dusk", "cream", "noir", "space", "anvil", "petrol")
_TWIN_PRESET = "frontier-serving"  # glyph-rich; same choice as the kit harness


def _fixture(name: str) -> dict[str, object]:
    path = _FIXTURES / f"{name}.json"
    if not path.exists():
        pytest.fail(f"fixture {path.name} missing — run scripts/extract_specimen_fixtures.py")
    loaded = json.loads(path.read_text())
    assert isinstance(loaded, dict)
    return loaded


_RENDER_CACHE: dict[tuple[str, str, str], str] = {}


def _render(preset: str, *, variant: str = "porcelain", palette: str = "fixed") -> str:
    key = (preset, variant, palette)
    if key not in _RENDER_CACHE:
        bs = resolve_bundled_spec("diagram", preset)
        spec = ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant=variant,
            ground="opaque",
            palette=palette,
            diagram=bs.value,
        )
        _RENDER_CACHE[key] = compose(spec).svg
    return _RENDER_CACHE[key]


@pytest.mark.parametrize("name", PARITY_NAMES)
def test_specimen_satisfies_own_laws(name: str) -> None:
    """Grader validation: the hand-authored ground truth passes its own laws."""
    fixture = _fixture(name)
    source = _REPO / str(fixture["source"])
    if not source.exists():
        pytest.skip(f"hand specimen not present in this checkout: {fixture['source']}")
    facts = parse_svg(source.read_text())
    failures = [r for r in geometry_laws(facts, fixture, mode="self") if not r.ok]
    assert not failures, f"{name} (SPECIMEN — grader bug, not engine bug):\n" + "\n".join(str(f) for f in failures)


def _expected_render_w(preset: str, vb_w: float) -> int | None:
    """The constant-scale law's expected render width (content-fit amendment),
    derived from the preset's own resolved chassis — the independent source
    the render must agree with: round(vb_w * display_w / max(chassis width,
    vb_w)); a chassis pinning both display dims is a fixed banner."""
    bs = resolve_bundled_spec("diagram", preset)
    cs = ComposeSpec(
        type="diagram", genome_id="primer", variant="porcelain", ground="opaque", palette="fixed", diagram=bs.value
    )
    normalized = coerce_diagram_input(cs.connector_data, cs)
    pspec = load_paradigms().get("primer")
    if pspec is None or not hasattr(pspec, "diagram"):
        return None
    cfg = pspec.diagram
    slug = layout_slug(normalized.spec)
    ch = cfg.topologies.get(slug) or DiagramTopologyChassis()
    ch = apply_spec_chassis(ch, normalized.spec.chassis)
    if ch.display_w and ch.display_h:
        return int(ch.display_w)
    target = float(ch.display_w or load_diagram_config().get("display_w_default", 740))
    reference = float(ch.width) if ch.width else vb_w
    return round(vb_w * (target / max(reference, vb_w)))


@pytest.mark.parametrize("name", PARITY_NAMES)
def test_engine_parity(name: str) -> None:
    fixture = _fixture(name)
    preset = name  # fixture ≡ preset
    try:
        svg = _render(preset)
    except Exception as exc:  # unknown preset = a parity gap, reported not crashed
        pytest.fail(f"{name}: preset '{preset}' failed to compose: {exc}")
    facts = parse_svg(svg)
    expected_w = _expected_render_w(preset, facts.vb_w) if facts.vb_w else None
    failures = [r for r in geometry_laws(facts, fixture, expected_render_w=expected_w) if not r.ok]
    assert not failures, f"{name} → preset '{preset}':\n" + "\n".join(str(f) for f in failures)


@pytest.mark.parametrize("variant", TWIN_VARIANTS)
def test_twin_tokens(variant: str) -> None:
    fixture = _fixture(f"twin-{variant}")
    faces = fixture["faces"]
    assert isinstance(faces, dict)
    svg = _render(_TWIN_PRESET, variant=variant, palette="adaptive")
    facts = parse_svg(svg)
    engine_faces = css_tokens(facts.style_text)
    failures = [r for r in law_twin_tokens(engine_faces, faces, variant) if not r.ok]
    assert not failures, f"twin '{variant}' vs authored specimen faces:\n" + "\n".join(str(f) for f in failures)


def _geometry_signature(facts: Facts) -> tuple[tuple[object, ...], ...]:
    """Every rect/circle/path reduced to pure geometry (chroma classes
    dropped), sorted into an order-independent multiset — two documents
    with this signature equal drew the identical silhouette."""
    rects = sorted((round(r.x, 2), round(r.y, 2), round(r.w, 2), round(r.h, 2), round(r.rx, 2)) for r in facts.rects)
    circles = sorted((round(c.cx, 2), round(c.cy, 2), round(c.r, 2)) for c in facts.circles)
    paths = sorted(p.d for p in facts.paths)
    return (tuple(rects), tuple(circles), tuple(paths))


@pytest.mark.parametrize(
    "preset",
    [
        pytest.param("model-router", id="card"),
        pytest.param("config-radial-circles", id="circle-hero"),
        pytest.param("hub-panel-orchestrator", id="containerless-text"),
    ],
)
def test_geometry_is_face_invariant(preset: str) -> None:
    """Light and dark renders of the same preset must draw the identical
    rects, circles, and paths — geometry is solved before chroma (the
    kit's own architectural order), so a light/dark substrate swap may
    repaint fill/stroke/class but must never move a coordinate. Spans
    three anatomies so a substrate fork hiding in any one of them would
    surface: model-router (card), config-radial-circles (circle hero — the
    hub topology's own default anatomy), hub-panel-orchestrator
    (containerless text, the anatomy with no rect at all besides its
    hero). ``noir`` is the porcelain genome's dark variant
    (substrate_kind: dark in primer.json's variant_overrides)."""
    light = parse_svg(_render(preset, variant="porcelain"))
    dark = parse_svg(_render(preset, variant="noir"))
    assert _geometry_signature(light) == _geometry_signature(dark), (
        f"{preset}: light/dark geometry diverges — a substrate-only variant swap must never move a coordinate"
    )


def _spine_wires(facts: Facts) -> list[PathEl]:
    """Connector wires (``-branch`` class, primer-content.j2) with an
    endpoint sitting exactly on the hero's own vertical spine (its cx) —
    the N/S family, whichever direction each edge declares (hero source or
    target). W and E leave from the hero's side boundaries, never its
    center, so they never qualify."""
    hero = next(r for r in facts.rects if "hero" in r.cls)
    out = []
    for p in facts.paths:
        if "branch" not in p.cls:
            continue
        ep = p.endpoints()
        if ep is not None and min(abs(ep[0][0] - hero.cx), abs(ep[1][0] - hero.cx)) < 1.0:
            out.append(p)
    return out


def test_axial_sole_satellite_spokes_stay_straight() -> None:
    """A SOLE N/S satellite's spoke is a straight, DEAD-VERTICAL line — never
    a curve, and never merely straight-but-slanted. The satellite's card
    always centers on the spine (no x-nudge), matching pp-verb-ontology.svg's
    own transform/read spokes (dead-straight L commands with zero x-delta:
    ``M 620,350 L 620,184``, ``M 620,470 L 620,634``) despite the specimen's
    own measured text-anchor lean living entirely in the card's icon+text
    layout, never its position. A prior revision nudged the card to chase
    that lean and left the spoke visibly off-vertical (a regression no
    specimen draws); this pins both failure modes at once. A genuinely
    off-spine MULTI-member rank is the opposite case — verb-reads' 4-wide S
    row — and pp-radial.svg's own read row curves those edges (``M 300,671 C
    300,560 556,506.0 556,426.0``, etc.). Both laws must hold at once: a
    routing fix that straightens the sole spoke by disabling curvature
    outright would silently bow the rank the other way."""
    hub_spokes = _spine_wires(parse_svg(_render("hub")))
    assert len(hub_spokes) == 2, f"expected the sole N and S spokes (edit, read); found {len(hub_spokes)}"
    for p in hub_spokes:
        assert "C" not in p.d, f"sole N/S satellite spoke curved instead of straight: {p.d}"
        ep = p.endpoints()
        assert ep is not None, f"spoke carries no endpoints: {p.d}"
        (x0, _y0), (x1, _y1) = ep
        assert abs(x0 - x1) < 0.5, f"sole N/S satellite spoke slanted off the spine (Δx={x0 - x1:.1f}): {p.d}"

    s_rank = _spine_wires(parse_svg(_render("verb-reads")))
    assert len(s_rank) == 4, f"expected verb-reads' 4-wide S rank; found {len(s_rank)}"
    assert all("C" in p.d for p in s_rank), (
        "verb-reads' multi-member S rank must stay curved (pp-radial.svg's own read row curves)"
    )
