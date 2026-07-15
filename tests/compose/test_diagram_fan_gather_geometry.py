"""Fan-family gather geometry: flush departure, beam staging, hero sizing,
convergence join-trunk run law.

Pins four related fixes to the fan solvers (fanout-horizontal, bilateral,
plus the shared ``_place``/``knot_collapse`` machinery every fan direction
rides): an unlabeled gather departs FLUSH off the source's face
(``v04/alpha/v04a6/primer-diagrams/primer-fanout-refined.html``) instead of a
floating 26px knot; a flush fan's beam runs its doors as one shared window
instead of N sequential stages; a bilateral fan's beams stage as two side
waves (west converges, a beat at the hub, east emerges) instead of firing
one edge at a time; and a hero (marked or markless) content-solves its
height instead of flooring at the archetype crown's height, UNLESS its own
preset explicitly cites that height (``chassis: { hero: { h: ... } }`` —
model-router's citation of primer.yaml's "hub 206x104 with the 32 glyph and
centered block" is real; a bare inline spec that merely resembles that
content never earned it).

A fifth, unrelated defect lives at the bottom: ``fan._join_trunk_len``'s
safety cap read 0.5 (half the natural member-to-mouth run) against a
docstring that already claimed "~20%" — pp-convergence-flow.svg's own join
trunk spends 19% of its run. Every convergence gather on the DEFAULT,
uncited chassis (context-merge, flag-evaluation, gate-verdicts, glyph-merge —
the common case, not an edge case) rode the loose cap to a 42-53% bare-wire
trunk; convergence-arrivals' own cited chassis never hit the cap either way
(``needed`` was already negative there), so the bug was invisible against
the one preset the corpus actually diffs by eye.
"""

from __future__ import annotations

from typing import Any

import pytest

from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import resolve_auto_roles
from hyperweave.config.loader import load_diagram_config, load_paradigms
from hyperweave.core.diagram import DiagramSpec
from hyperweave.core.paradigm import ParadigmDiagramConfig

ENGINE = load_diagram_config()
_pspec = load_paradigms()["primer"]
PARADIGM: ParadigmDiagramConfig = _pspec.diagram if _pspec is not None else ParadigmDiagramConfig()


def _layout(**kw: Any) -> Any:
    spec = resolve_auto_roles(DiagramSpec(**kw))
    return compute_diagram_layout(spec, paradigm=PARADIGM, engine=ENGINE, palette_len=6)


# ── Defect 1: flush gather (unlabeled fan departs at the mouth) ─────────────


def test_unlabeled_horizontal_fan_departs_flush_at_the_mouth() -> None:
    """primer-fanout-refined.html: an unlabeled fan's curves start AT the
    hero's face point (+/-1px) — no stub, no floating knot — and the gather
    bezel marks that same point (finish_layout's existing GatherPoint law:
    >=2 shared endpoints render the ring+core ornament, unmodified here)."""
    lay = _layout(
        topology="fanout",
        title="T",
        nodes=[{"label": "hub", "gather": True}, {"label": "a"}, {"label": "b"}, {"label": "c"}],
    )
    hero = next(n for n in lay.nodes if n.role == "hero")
    mouth_x = hero.box.x + hero.box.w
    mouth_y = hero.box.y + hero.box.h / 2
    assert not [c for c in lay.connectors if " L " in c.path_d], "a flush fan has no straight trunk segment"
    for c in lay.connectors:
        sx, sy = (float(v) for v in c.path_d.split(" ")[1].split(","))
        assert abs(sx - mouth_x) < 1.0
        assert abs(sy - mouth_y) < 1.0
    assert len(lay.gathers) == 1
    assert abs(lay.gathers[0].x - mouth_x) < 1.0
    assert abs(lay.gathers[0].y - mouth_y) < 1.0


def test_labeled_horizontal_fan_keeps_the_trunk_and_knot() -> None:
    """A trunk-cargo fan (any edge declaring a label) keeps today's
    trunk+knot law untouched — the parity-beam/model-router fixtures pin it,
    this just guards the cargo branch didn't regress alongside the bare one."""
    lay = _layout(
        topology="fanout",
        title="T",
        nodes=[
            {"id": "hub", "label": "hub", "gather": True},
            {"id": "a", "label": "a"},
            {"id": "b", "label": "b"},
            {"id": "c", "label": "c"},
        ],
        edges=[
            {"source": "hub", "target": "a", "label": "route", "label_style": "chip"},
            {"source": "hub", "target": "b"},
            {"source": "hub", "target": "c"},
        ],
    )
    trunks = [c for c in lay.connectors if " L " in c.path_d]
    assert len(trunks) == 1
    ch = PARADIGM.topologies["fanout-horizontal"]
    hero = next(n for n in lay.nodes if n.role == "hero")
    trunk_end_x = float(trunks[0].path_d.rsplit(" ", 1)[1].split(",")[0])
    assert abs(trunk_end_x - (hero.box.x + hero.box.w) - ch.depart_trunk) < 1.0


# ── Defect 2: beam single-stage on a flush (trunk-less) fan ─────────────────


def test_flush_fan_beam_runs_the_doors_as_one_window() -> None:
    """A flush (chipless) fan's beam has no trunk to stage trunk-then-doors
    on — the doors fire as ONE shared near-full sweep instead of N
    sequential stages burning the clock on a stub that no longer exists
    (artifact-fanout-beam: "the comet stalls at the knot then re-bursts")."""
    lay = _layout(
        topology="fanout",
        title="T",
        edge_motion="beam",
        nodes=[{"label": "hub", "gather": True}, {"label": "a"}, {"label": "b"}, {"label": "c"}],
    )
    beams = [c for c in lay.connectors if c.beam]
    assert len(beams) == 3, [c.motion for c in lay.connectors]
    windows = {c.beam[0].animate.keytimes for c in beams}
    assert len(windows) == 1, windows


def test_labeled_fan_beam_keeps_trunk_then_doors_staging() -> None:
    """A real trunk (cargo-bearing) still stages trunk-then-doors (the
    parity-beam 2-stage family) — untouched by the flush-fan fix: the trunk
    fires its own window, every door shares a DIFFERENT, later window."""
    lay = _layout(
        topology="fanout",
        title="T",
        edge_motion="beam",
        nodes=[
            {"id": "hub", "label": "hub", "gather": True},
            {"id": "a", "label": "a"},
            {"id": "b", "label": "b"},
            {"id": "c", "label": "c"},
        ],
        edges=[
            {"source": "hub", "target": "a", "label": "route", "label_style": "chip"},
            {"source": "hub", "target": "b"},
            {"source": "hub", "target": "c"},
        ],
    )
    trunk = next(c for c in lay.connectors if " L " in c.path_d)
    doors = [c for c in lay.connectors if c is not trunk and c.beam]
    assert trunk.beam
    door_windows = {c.beam[0].animate.keytimes for c in doors}
    assert len(door_windows) == 1
    assert trunk.beam[0].animate.keytimes != next(iter(door_windows))


# ── Addendum: bilateral beam choreography (west converges, east emerges) ────


def test_bilateral_beams_stage_as_two_side_waves() -> None:
    """West beams (flow_side 0) share one window, east beams (flow_side 1)
    share a later one — "west converges as one wave, a beat at the hub, east
    emerges as the next" — not one edge at a time."""
    lay = _layout(
        topology="fanout",
        orientation="bilateral",
        title="T",
        edge_motion="beam",
        nodes=[
            {"id": "hub", "label": "hub", "role": "hero"},
            {"id": "a", "label": "a"},
            {"id": "b", "label": "b"},
            {"id": "c", "label": "c"},
            {"id": "d", "label": "d"},
        ],
    )
    beams = [c for c in lay.connectors if c.beam]
    assert len(beams) == 4
    windows = {c.beam[0].animate.keytimes for c in beams}
    assert len(windows) == 2, windows


def test_bilateral_beam_windows_match_the_derived_relay_shape() -> None:
    """The bilateral family's two windows are ``relay``'s own n=2 shape
    (lead/gap/rest, no bilateral specimen exists to cite a different span),
    capped at ``relay_span_cap`` (.30 — the wider of the two beam specimens'
    own citations) so a 2-stage wave gets the same ~1.5s duration a trunk/
    branch stage gets — west 0.02-0.32, east 0.38-0.68 on the 5.236s clock —
    rather than the raw by-count division (.42, ~2.2s) ballooning past what
    either specimen ever licensed."""
    bcfg = ENGINE.get("beam") or {}
    from hyperweave.compose.diagram.motion import beam_windows

    windows = beam_windows(2, bcfg, family="bilateral")
    assert windows == [(0.02, 0.32), (0.38, 0.68)]


# ── Defect 4: fan hero vertical slack ────────────────────────────────────────


def test_markless_hero_content_solves_height() -> None:
    """A plain 'card' style hero (no glyph mark — variant-fan's 'primer' /
    'the seed') never earned the archetype crown's citation ('hub 206x104
    with the 32 glyph and centered block') and content-solves instead of
    flooring at 104, removing the large empty band above/below its rows."""
    lay = _layout(
        topology="fanout",
        title="T",
        node_style="card",
        nodes=[
            {"id": "primer", "label": "primer", "desc": "the seed", "role": "hero", "gather": True},
            {"id": "a", "label": "porcelain", "desc": "paper light"},
            {"id": "b", "label": "carbon", "desc": "graphite dark"},
        ],
    )
    ch = PARADIGM.topologies["fanout-horizontal"]
    hero = next(n for n in lay.nodes if n.role == "hero")
    # The pad_y/label_desc_gap citations that make a 2-line hero
    # content-solve to 104 NATURALLY (primer_diagram_language's own
    # generous ~26px vertical air) also raise a 1-line hero's floor —
    # padding is constant regardless of line count, so this lands at
    # ~0.83 of the citation (86.38), not the old tight pad_y's ~0.45.
    assert hero.box.h < ch.hero.h * 0.9, hero.box.h


def test_marked_hero_keeps_the_cited_archetype_height() -> None:
    """A card+glyph hero whose PRESET explicitly cites the archetype height
    (model-router's own ``chassis: { hero: { h: 104 } }`` pin — a specimen
    citation, not a bare 'this content resembles the specimen' guess) keeps
    the full chassis floor — byte-identical. Marked alone is no longer
    enough (see ``test_marked_hero_content_solves_height_when_uncited``
    below): being a glyph-bearing hero doesn't itself earn the citation."""
    lay = _layout(
        topology="fanout",
        title="T",
        node_style="card+glyph",
        chassis={"hero": {"h": 104}},
        nodes=[
            {
                "id": "router",
                "label": "model router",
                "desc": "capability-routed",
                "role": "hero",
                "gather": True,
                "kind": "router",
            },
            {"id": "a", "label": "Claude", "desc": "long-context", "glyph": "anthropic"},
            {"id": "b", "label": "Gemini", "desc": "multimodal", "glyph": "gemini"},
        ],
    )
    ch = PARADIGM.topologies["fanout-horizontal"]
    hero = next(n for n in lay.nodes if n.role == "hero")
    assert abs(hero.box.h - ch.hero.h) < 0.01


def test_marked_hero_content_solves_height_when_uncited() -> None:
    """The SAME card+glyph content as above, but from a bare spec whose
    preset never cited the archetype height — G3 now content-solves it
    (a glyph row participates in content height exactly like a label row
    does), never floors at an uncited paradigm default. Marked-ness alone
    used to earn the floor; only an explicit citation does now."""
    lay = _layout(
        topology="fanout",
        title="T",
        node_style="card+glyph",
        nodes=[
            {
                "id": "router",
                "label": "model router",
                "desc": "capability-routed",
                "role": "hero",
                "gather": True,
                "kind": "router",
            },
            {"id": "a", "label": "Claude", "desc": "long-context", "glyph": "anthropic"},
            {"id": "b", "label": "Gemini", "desc": "multimodal", "glyph": "gemini"},
        ],
    )
    ch = PARADIGM.topologies["fanout-horizontal"]
    hero = next(n for n in lay.nodes if n.role == "hero")
    # The pad_y/label_desc_gap citations that make a 2-line hero
    # content-solve to 104 NATURALLY (primer_diagram_language's own
    # generous ~26px vertical air) also raise a 1-line hero's floor —
    # padding is constant regardless of line count, so this lands at
    # ~0.83 of the citation (86.38), not the old tight pad_y's ~0.45.
    assert hero.box.h < ch.hero.h * 0.9, hero.box.h


def test_markless_hero_stays_centered_on_the_member_column() -> None:
    """The hero's box center matches the dest column's true center even
    though its solved height differs from the chassis-assumed floor — the
    center-based placement call sites (``_hero_center_h``) pre-solve height
    before computing y, so a markless hero doesn't drift off-center once the
    archetype floor no longer pads its box out to the old assumed height."""
    lay = _layout(
        topology="fanout",
        title="T",
        node_style="card",
        nodes=[
            {"id": "primer", "label": "primer", "desc": "the seed", "role": "hero", "gather": True},
            {"id": "a", "label": "porcelain"},
            {"id": "b", "label": "carbon"},
            {"id": "c", "label": "dusk"},
        ],
    )
    hero = next(n for n in lay.nodes if n.role == "hero")
    dests = [n for n in lay.nodes if n.role != "hero"]
    member_center = (min(n.box.y for n in dests) + max(n.box.y + n.box.h for n in dests)) / 2
    hero_center = hero.box.y + hero.box.h / 2
    assert abs(hero_center - member_center) < 0.5


# ── Defect 5: convergence join-trunk run law ─────────────────────────────────


def _convergence_layout(
    *, nodes: list[dict[str, Any]], edges: list[dict[str, Any]], chassis: dict[str, Any] | None = None
) -> Any:
    kw: dict[str, Any] = dict(topology="convergence", title="T", node_style="card+glyph", nodes=nodes, edges=edges)
    if chassis:
        kw["chassis"] = chassis
    return _layout(**kw)


def _trunk_and_run(lay: Any) -> tuple[float, float]:
    """(join-trunk length, natural member-to-mouth run) for a converged
    layout — the same two quantities ``fan._join_trunk_len`` reasons in,
    read back from the solved record instead of the private formula."""
    hero = next(n for n in lay.nodes if n.role == "hero")
    members = [n for n in lay.nodes if n.role != "hero"]
    natural_run = hero.box.x - max(n.box.x + n.box.w for n in members)
    trunk = next(c for c in lay.connectors if " L " in c.path_d)
    return trunk.length, natural_run


def test_thin_uncited_gather_keeps_its_trunk_under_the_specimen_band() -> None:
    """context-merge's own shape (a 3-in gather on the DEFAULT, uncited
    convergence chassis, one chip-labeled edge): the trunk must stay near
    pp-convergence-flow.svg's own 19%-of-run citation, not the prior 0.5 cap
    (which parked this exact shape at 338px, 50% of its 676px run)."""
    nodes = [
        {"id": "genome", "label": "genome", "desc": "chromatic DNA", "kind": "droplet"},
        {"id": "spec", "label": "spec", "desc": "the request", "kind": "file-text"},
        {"id": "layout", "label": "layout", "desc": "solved geometry", "kind": "layout-grid"},
        {
            "id": "ctx",
            "label": "context",
            "desc": "one dict\nStrictUndefined",
            "role": "hero",
            "kind": "braces",
            "gather": True,
        },
    ]
    edges = [
        {"source": "genome", "target": "ctx", "label": "merge", "label_style": "chip"},
        {"source": "spec", "target": "ctx", "label": "no defaults"},
        {"source": "layout", "target": "ctx"},
    ]
    lay = _convergence_layout(nodes=nodes, edges=edges)
    trunk, natural_run = _trunk_and_run(lay)
    # Edge-run law re-pin: the cited 524 members→hero run replaced the old
    # fixed-frame's longer natural run, so a CHIP-bound trunk (chip_run_min
    # is documented to grow past the bare cap) now sits at ~25% of the run
    # instead of under 20% — the BARE cap still governs chipless trunks
    # (they collapse flush entirely), and the chip trunk stays far under
    # the retired half-the-run ceiling.
    assert trunk < 0.30 * natural_run, (trunk, natural_run)


def test_four_in_uncited_gather_matches_the_three_in_band() -> None:
    """flag-evaluation's own 4-in shape on the SAME default chassis as the
    3-in case above: a near-identical spec must land in the SAME
    proportional band — near-identical specs read as near-identical
    canvases, never a function of which uncited story declared 3 vs 4
    members (the regression this whole defect was filed against: two
    structurally-similar convergence stories rendering wildly different
    bare-trunk runs)."""
    nodes = [
        {"id": "config", "label": "config", "desc": "defaults", "kind": "settings"},
        {"id": "cohort", "label": "cohort", "desc": "user segment", "kind": "users"},
        {"id": "kill", "label": "kill switch", "desc": "overrides all", "kind": "zap"},
        {"id": "rollout", "label": "rollout", "desc": "percent ramp", "kind": "activity"},
        {
            "id": "flag",
            "label": "the flag",
            "desc": "one boolean out",
            "role": "hero",
            "kind": "shield-check",
            "gather": True,
        },
    ]
    edges = [
        {"source": "config", "target": "flag", "relation": "drift", "label": "evaluate", "label_style": "chip"},
        {"source": "cohort", "target": "flag", "relation": "drift"},
        {"source": "kill", "target": "flag", "relation": "drift"},
        {"source": "rollout", "target": "flag", "relation": "drift"},
    ]
    lay = _convergence_layout(nodes=nodes, edges=edges)
    trunk, natural_run = _trunk_and_run(lay)
    # Edge-run law re-pin (see the chip-bound note above): the cited run is
    # shorter than the retired frame's, so the chip trunk reads ~25%.
    assert trunk < 0.30 * natural_run, (trunk, natural_run)


def test_low_arity_chipless_gather_collapses_flush() -> None:
    """glyph-merge's own 2-in shape, re-ruled (the ``depart_trunk_bare``
    mirror): a CHIPLESS join draws no trunk at all — members run to the
    mouth, the gather ring seats ON the sink's face, and no bare arrowed
    wire dangles before the card (the earlier grows-past-the-citation pin
    described the dangling-trunk defect this ruling retires)."""
    nodes = [
        {"id": "brands", "label": "glyphs.json", "desc": "385 brand marks", "kind": "box"},
        {"id": "core", "label": "glyphs-core.json", "desc": "kind marks", "kind": "boxes"},
        {
            "id": "reg",
            "label": "the registry",
            "desc": "merged lookup",
            "role": "hero",
            "kind": "search",
            "gather": True,
        },
    ]
    edges = [
        {"source": "brands", "target": "reg", "relation": "flow"},
        {"source": "core", "target": "reg", "relation": "flow"},
    ]
    lay = _convergence_layout(nodes=nodes, edges=edges)
    hero = next(n for n in lay.nodes if n.role == "hero")
    mouth = (hero.box.x, hero.box.y + hero.box.h / 2)
    # No synthetic trunk geo: every connector is an authored member ending
    # AT the mouth, arrowless (the knot is the terminus), and the gather
    # ring seats on the sink's own face.
    assert len(lay.connectors) == 2, [c.path_d for c in lay.connectors]
    for c in lay.connectors:
        end = c.path_d.split()[-1]
        ex, ey = (float(v) for v in end.split(","))
        assert abs(ex - mouth[0]) < 0.6 and abs(ey - mouth[1]) < 0.6, (end, mouth)
        assert not c.marker_d, f"flush member kept an arrowhead: {c.path_d[:60]}"
    assert any(abs(g.x - mouth[0]) < 0.6 and abs(g.y - mouth[1]) < 0.6 for g in lay.gathers), lay.gathers


def test_convergence_arrivals_citation_is_unaffected_by_the_run_cap() -> None:
    """convergence-arrivals' own cited chassis (card_min_w 210, hero
    280x120, pitch 148, margin_x 86 — its own pp-convergence-flow.svg
    reproduction) already satisfies the run-cap law before its chip is even
    considered (``_join_trunk_len`` alone floors at the 100px citation there
    — ``needed`` solves negative on this wide a spread). The fix is a no-op
    on this preset, byte-identical to before it: ``chip_run_min``'s own
    max() already carried this trunk to 122.96px regardless of which cap
    ``_join_trunk_len`` used underneath it."""
    nodes = [
        {"id": "payload", "label": "payload", "desc": "the seed data", "kind": "braces"},
        {"id": "genome", "label": "genome", "desc": "aesthetic dna", "kind": "shuffle"},
        {"id": "frame", "label": "frame", "desc": "the skeleton", "kind": "box"},
        {"id": "spec", "label": "spec", "desc": "size · platform", "kind": "file-text"},
        {
            "id": "artifact",
            "label": "the artifact",
            "desc": "payload + envelope\none seed, every surface",
            "role": "hero",
            "glyph": "hyperweave",
            "gather": True,
        },
    ]
    edges = [
        {"source": "payload", "target": "artifact", "relation": "drift", "label": "compose", "label_style": "chip"},
        {"source": "genome", "target": "artifact", "relation": "drift"},
        {"source": "frame", "target": "artifact", "relation": "drift"},
        {"source": "spec", "target": "artifact", "relation": "drift"},
    ]
    chassis = {"card_min_w": 210, "hero": {"w": 280, "h": 120, "max_desc_lines": 2}, "pitch": 148, "margin_x": 86}
    lay = _convergence_layout(nodes=nodes, edges=edges, chassis=chassis)
    trunk, _natural_run = _trunk_and_run(lay)
    assert trunk == pytest.approx(122.96, abs=0.5)
