"""The card+label anatomy and partition-pair chromatics.

card+label inverts the default card: a small tracked mono label over a stack of
display values, with any glyph/kind demoted to a corner annotation that reserves
NO column. Its hero register restacks the same two slots as the crown — an
identity row over a centred display block.

Constants are cited from the hand specimen
(``v04/v040/v042/diagram-prototypes/hub-expressions/hub-bilateral.svg``),
whose four satellites (188x114 / 188x92 / 188x92 / 196x92) and crown (220x184)
agree on one rhythm: label baseline +26, first value +50, pitch 22, bottom air
20; crown label +40, display from +86 at pitch 33.
"""

from __future__ import annotations

import math
import re
from typing import Any

import pytest

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import resolve_auto_roles
from hyperweave.compose.diagram.sizing import (
    CARD_LABEL_HERO_LABEL_DY,
    CARD_LABEL_HERO_PITCH,
    CARD_LABEL_HERO_VALUE_DY,
    CARD_LABEL_LABEL_DY,
    CARD_LABEL_MARK,
    CARD_LABEL_MARK_HEALTH_GAP,
    CARD_LABEL_MARK_INSET_R,
    CARD_LABEL_MARK_INSET_Y,
    CARD_LABEL_PAD_BOTTOM,
    CARD_LABEL_PAD_X,
    CARD_LABEL_VALUE_DY,
    CARD_LABEL_VALUE_PITCH,
)
from hyperweave.config.loader import load_diagram_config, load_glyphs, load_paradigms
from hyperweave.core.diagram import DiagramSpec

ENGINE = load_diagram_config()
PRESET = "hub-bilateral"


def solve(**kw: Any) -> Any:
    paradigm = load_paradigms()["primer"].diagram
    spec = resolve_auto_roles(DiagramSpec.model_validate(kw))
    return compute_diagram_layout(spec, paradigm=paradigm, engine=ENGINE, palette_len=8, glyph_registry=load_glyphs())


_MIN_SATELLITES = 4
"""The bilateral cell's own floor (diagram-frame.yaml: source + 3..10). Tests
that care about ONE card pad to it with fillers rather than shrinking the cell,
so every case runs through the real solver instead of a special-cased one."""


def _wings(nodes: list[dict[str, Any]], *, hub: dict[str, Any] | None = None, **extra: Any) -> Any:
    """A bilateral fan carrying ``nodes`` as its satellites — the cell the
    anatomy's specimen is authored in — padded to the cell's node floor."""
    padded = list(nodes)
    while len(padded) < _MIN_SATELLITES:
        padded.append({"id": f"pad{len(padded)}", "label": f"pad{len(padded)}", "desc": "filler"})
    spec: dict[str, Any] = dict(
        topology="fanout",
        orientation="bilateral",
        node_style="card+label",
        nodes=[hub or dict(id="hub", label="hub", desc="one\ntwo", role="hero"), *padded],
        edges=[{"source": "hub", "target": n["id"]} for n in padded],
    )
    spec.update(extra)
    return solve(**spec)


def _node(lay: Any, node_id: str) -> Any:
    return next(n for n in lay.nodes if n.node_id == node_id)


# ── anatomy ──────────────────────────────────────────────────────────────────


def test_spec_level_style_reaches_every_node() -> None:
    """``node_style`` is the artifact-level anatomy: the crown renders the hero
    register and the satellites the standard one, with no per-node style. The
    crown is spec-PINNED here (the author's citation), so the register holds
    regardless of the light filler satellites' mass — the dominance band has
    its own pins below."""
    lay = _wings([{"id": "a", "label": "alpha", "desc": "one value"}], chassis={"hero": {"w": 220, "h": 184}})
    assert _node(lay, "hub").label.cls == "hlbl"
    assert [t.cls for t in _node(lay, "hub").desc_lines] == ["hval", "hval"]
    assert _node(lay, "a").label.cls == "nlbl"
    assert [t.cls for t in _node(lay, "a").desc_lines] == ["nval"]


def test_crown_register_bounded_by_sibling_mass() -> None:
    """The system-wide balance law: a center-seat hero keeps the CROWN
    register only while the crown stays inside ``CROWN_DOMINANCE_MAX`` of
    its standard siblings' median box (the specimen's own proportion).
    Light satellites demote the crown to the standard register with hero
    dress; substantial ones carry it; a spec-PINNED crown is the author's
    ruling and always keeps it."""
    light = _wings([{"id": "a", "label": "a", "desc": "v"}])
    assert _node(light, "hub").label.cls == "nlbl"
    heavy = _wings(
        [
            {"id": f"s{i}", "label": f"unit {i}", "desc": "gathers sources\nextracts claims\ncites everything"}
            for i in range(4)
        ]
    )
    assert _node(heavy, "hub").label.cls == "hlbl"
    pinned = _wings([{"id": "a", "label": "a", "desc": "v"}], chassis={"hero": {"w": 220, "h": 184}})
    assert _node(pinned, "hub").label.cls == "hlbl"


def test_per_node_style_mixes_with_the_other_anatomies() -> None:
    """Anatomy is orthogonal to topology AND to its siblings: one diagram may
    hold a card, a card+glyph and a card+label at once."""
    lay = solve(
        topology="fanout",
        orientation="bilateral",
        nodes=[
            {"id": "hub", "label": "hub", "desc": "one", "role": "hero"},
            {"id": "plain", "label": "plain", "desc": "a desc", "style": "card"},
            {"id": "marked", "label": "marked", "desc": "a desc", "style": "card+glyph", "kind": "database"},
            {"id": "valued", "label": "valued", "desc": "a value", "style": "card+label"},
        ],
        edges=[{"source": "hub", "target": t} for t in ("plain", "marked", "valued")],
    )
    assert _node(lay, "plain").label.cls == "name"
    assert _node(lay, "marked").label.cls == "name"
    assert _node(lay, "valued").label.cls == "nlbl"


def test_label_case_is_a_register_fact() -> None:
    """The rendered string IS the measured string — never a CSS
    text-transform, which no rasterizer is obliged to honour. And case is a
    REGISTER fact: the satellite label is a tracked kicker (.14em) and
    uppercases; the crown's identity row is a signature line (.06em) and keeps
    its authored case. Both conventions are the specimen's own — ``CPU`` beside
    ``apple silicon`` in the same hand file."""
    lay = _wings(
        [{"id": "a", "label": "researcher", "desc": "v"}],
        hub={"id": "hub", "label": "apple silicon", "desc": "M4 Pro", "role": "hero"},
        # Crown pinned (author's citation) so the register — and its case
        # convention — holds beside the light filler satellites.
        chassis={"hero": {"w": 220, "h": 184}},
    )
    assert _node(lay, "a").label.text == "RESEARCHER"
    assert _node(lay, "hub").label.text == "apple silicon"


@pytest.mark.parametrize("count", [1, 2, 3, 4])
def test_value_stack_rhythm_is_the_specimen_s(count: int) -> None:
    """Every card hangs its stack from the label kicker at one fixed rhythm,
    whatever the value count — the anatomy's whole point."""
    desc = "\n".join(f"value {i}" for i in range(count))
    lay = _wings([{"id": "a", "label": "a", "desc": desc}])
    n = _node(lay, "a")
    top = n.box.y
    assert n.label.y - top == pytest.approx(CARD_LABEL_LABEL_DY)
    assert [t.y - top for t in n.desc_lines] == pytest.approx(
        [CARD_LABEL_VALUE_DY + i * CARD_LABEL_VALUE_PITCH for i in range(count)]
    )


def test_authored_line_breaks_are_preserved_verbatim() -> None:
    """A value stack is authored, not reflowed: three declared lines render as
    three, never merged because they would have fit on fewer."""
    lay = _wings([{"id": "a", "label": "a", "desc": "one\ntwo\nthree"}])
    assert [t.text for t in _node(lay, "a").desc_lines] == ["one", "two", "three"]


def test_crown_rhythm_and_centring() -> None:
    """The hero register: identity row over a display block centred on the
    card axis (the specimen's crown, 220x184 with lines at +86/+119/+152)."""
    lay = _wings(
        [{"id": "a", "label": "a", "desc": "v"}],
        hub={"id": "hub", "label": "hub", "desc": "plan\ndispatch\nmerge", "role": "hero"},
        chassis={"hero": {"w": 220, "h": 184, "rx": 16}},
    )
    n = _node(lay, "hub")
    assert (n.box.w, n.box.h) == (220.0, 184.0)
    assert n.label.y - n.box.y == pytest.approx(CARD_LABEL_HERO_LABEL_DY)
    assert [t.y - n.box.y for t in n.desc_lines] == pytest.approx(
        [CARD_LABEL_HERO_VALUE_DY + i * CARD_LABEL_HERO_PITCH for i in range(3)]
    )
    for t in n.desc_lines:
        assert t.anchor == "middle"
        assert t.x == pytest.approx(n.box.x + n.box.w / 2)


# ── the corner mark ──────────────────────────────────────────────────────────


def test_corner_mark_reserves_no_column() -> None:
    """The mark is an ANNOTATION, not an identity slot: values start at the
    same x with or without one. A reserved left column is what would turn this
    anatomy back into card+glyph."""
    marked = _wings([{"id": "a", "label": "a", "desc": "a value", "kind": "database"}])
    bare = _wings([{"id": "a", "label": "a", "desc": "a value"}])
    for lay in (marked, bare):
        n = _node(lay, "a")
        assert n.label.x - n.box.x == pytest.approx(CARD_LABEL_PAD_X)
        for t in n.desc_lines:
            assert t.x - n.box.x == pytest.approx(CARD_LABEL_PAD_X)
    assert _node(marked, "a").glyph is not None
    assert _node(bare, "a").glyph is None


def test_unresolved_glyph_costs_nothing() -> None:
    """Icon-or-nothing stays total: a kind that resolves to no mark leaves the
    box byte-identical to a markless card — it must not reserve clearance for
    something that never draws."""
    unknown = _wings([{"id": "a", "label": "a", "desc": "a value", "kind": "not-a-real-kind-slug"}])
    bare = _wings([{"id": "a", "label": "a", "desc": "a value"}])
    assert _node(unknown, "a").glyph is None
    assert (_node(unknown, "a").box.w, _node(unknown, "a").box.h) == (
        _node(bare, "a").box.w,
        _node(bare, "a").box.h,
    )


def test_corner_mark_seats_top_right_inside_the_card() -> None:
    lay = _wings([{"id": "a", "label": "a", "desc": "a value", "kind": "database"}])
    n = _node(lay, "a")
    art = n.glyph
    assert art is not None
    assert art.cx == pytest.approx(n.box.x + n.box.w - CARD_LABEL_MARK_INSET_R + CARD_LABEL_MARK / 2)
    assert art.cy == pytest.approx(n.box.y + CARD_LABEL_MARK_INSET_Y + CARD_LABEL_MARK / 2)
    assert art.cx + art.size / 2 <= n.box.x + n.box.w
    assert art.cy - art.size / 2 >= n.box.y


def test_long_label_never_runs_under_its_mark() -> None:
    """The mark imposes header-row CLEARANCE even though it opens no column:
    the label must end before the mark begins, at any label length."""
    lay = _wings([{"id": "a", "label": "a very long subsystem label indeed", "desc": "v", "kind": "database"}])
    n = _node(lay, "a")
    from hyperweave.compose.diagram.sizing import card_label_voices
    from hyperweave.compose.matrix.cells import measure_voice

    label_voice, _ = card_label_voices(load_paradigms()["primer"].diagram, hero=False)
    label_right = n.label.x + measure_voice(n.label.text, label_voice)
    assert n.glyph is not None
    assert label_right <= n.glyph.cx - n.glyph.size / 2 + 0.51


def test_health_dot_and_corner_mark_share_the_corner_without_overlap() -> None:
    """The two top-right channels COMPOSE: the anatomy-owned mark yields
    (shifts left) when the generic health dot occupies the corner, holding
    the optical gap between their envelopes — the health channel itself
    never moves (its seat is every anatomy's contract, not this one's)."""
    lay = _wings([{"id": "a", "label": "a", "desc": "a value", "kind": "database", "health": "vulnerable"}])
    n = _node(lay, "a")
    assert n.glyph is not None
    assert n.health_dot is not None
    dot_r = float(ENGINE["health"]["dot_r"])
    assert n.health_dot[0] == pytest.approx(n.box.x + n.box.w - float(ENGINE["health"]["dot_inset_x"]))
    mark_right = n.glyph.cx + n.glyph.size / 2
    dot_left = n.health_dot[0] - dot_r
    assert mark_right + CARD_LABEL_MARK_HEALTH_GAP <= dot_left + 0.01
    # The label-row clearance follows the shifted mark: still no run-under.
    from hyperweave.compose.diagram.sizing import card_label_voices
    from hyperweave.compose.matrix.cells import measure_voice

    label_voice, _ = card_label_voices(load_paradigms()["primer"].diagram, hero=False)
    assert n.label.x + measure_voice(n.label.text, label_voice) <= n.glyph.cx - n.glyph.size / 2 + 0.51


def test_health_shifts_the_mark_only_when_both_channels_resolve() -> None:
    """Byte-identity everywhere the collision cannot happen: a healthy marked
    card keeps the specimen's own mark seat, and an unhealthy MARKLESS card's
    box matches its healthy twin — the clearance never reserves space for a
    mark that does not draw."""
    healthy = _wings([{"id": "a", "label": "a", "desc": "a value", "kind": "database"}])
    hn = _node(healthy, "a")
    assert hn.glyph is not None
    assert hn.glyph.cx == pytest.approx(hn.box.x + hn.box.w - CARD_LABEL_MARK_INSET_R + CARD_LABEL_MARK / 2)
    sick_bare = _wings([{"id": "a", "label": "a", "desc": "a value", "health": "outdated"}])
    well_bare = _wings([{"id": "a", "label": "a", "desc": "a value"}])
    assert (_node(sick_bare, "a").box.w, _node(sick_bare, "a").box.h) == (
        _node(well_bare, "a").box.w,
        _node(well_bare, "a").box.h,
    )


# ── growth ───────────────────────────────────────────────────────────────────


def test_values_grow_the_box_instead_of_truncating() -> None:
    """A value is data — it never ellipsizes. An unbreakable token wider than
    the card grows the card."""
    token = "supercalifragilistic-throughput-per-second"
    lay = _wings([{"id": "a", "label": "a", "desc": token}])
    n = _node(lay, "a")
    assert [t.text for t in n.desc_lines] == [token]
    assert "…" not in n.desc_lines[0].text


def test_breakable_values_never_rewrap_the_authored_stack() -> None:
    """A value is a DATUM, breakable or not: the engine never re-breaks one.
    A long space-separated run stays a single value line and the box grows
    to hold its full ink — line structure is the caller's semantic rhythm
    (authored ``\\n`` only), width is the engine's (distinct from the
    authored-break pin and the unbreakable-token growth pin)."""
    words = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    lay = _wings([{"id": "a", "label": "a", "desc": words}])
    n = _node(lay, "a")
    assert [t.text for t in n.desc_lines] == [words]
    from hyperweave.compose.diagram.sizing import card_label_voices
    from hyperweave.compose.matrix.cells import measure_voice

    _, value_voice = card_label_voices(load_paradigms()["primer"].diagram, hero=False)
    for t in n.desc_lines:
        assert t.x + measure_voice(t.text, value_voice) <= n.box.x + n.box.w - CARD_LABEL_PAD_X + 0.51


def test_text_stays_inside_the_card() -> None:
    lay = _wings(
        [
            {"id": "a", "label": "a", "desc": "gathers sources\nextracts claims", "kind": "search"},
            {"id": "b", "label": "b", "desc": "one"},
        ]
    )
    for node_id in ("a", "b"):
        n = _node(lay, node_id)
        assert n.label.y > n.box.y
        for t in (n.label, *n.desc_lines):
            assert n.box.x <= t.x <= n.box.x + n.box.w
            assert n.box.y <= t.y <= n.box.y + n.box.h
        assert n.desc_lines[-1].y + CARD_LABEL_PAD_BOTTOM <= n.box.y + n.box.h + 0.51


def test_sliver_guard_widens_instead_of_stacking() -> None:
    """The wrap guard: a card may never become a sliver — text that would wrap
    into something taller than it is wide widens the box instead."""
    lay = _wings(
        [{"id": "a", "label": "a", "desc": "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"}]
    )
    n = _node(lay, "a")
    assert n.box.w >= n.box.h


def test_standard_label_row_card_uses_the_same_sliver_guard() -> None:
    """The ruling belongs to cards, not only the new anatomy."""
    lay = solve(
        topology="pipeline",
        nodes=[
            {"id": "a", "label": "a", "desc": "alpha beta gamma delta epsilon zeta eta theta"},
            {"id": "b", "label": "b", "desc": "short"},
            {"id": "c", "label": "c", "desc": "short"},
        ],
    )
    assert all(n.box.w >= n.box.h for n in lay.nodes)


def test_head_anatomy_stays_portrait() -> None:
    """The guard is scoped: the stacked portrait column is DELIBERATELY taller
    than wide (frame-engine-hub's 124x124 tiles), so it must not be widened."""
    lay = solve(
        topology="tree",
        node_anatomy="head",
        nodes=[
            {"id": "root", "label": "root", "desc": "the root", "role": "hero"},
            {"id": "leaf", "label": "leaf", "desc": "a leaf node with a reasonably long description"},
            {"id": "leaf2", "label": "leaf two", "desc": "another leaf with its own long description"},
        ],
        edges=[{"source": "root", "target": "leaf"}, {"source": "root", "target": "leaf2"}],
    )
    assert any(n.box.h > n.box.w for n in lay.nodes)


# ── partition-pair chromatics ────────────────────────────────────────────────


def _hues(lay: Any) -> dict[str, int]:
    return {n.node_id: n.accent_index for n in lay.nodes}


def test_partition_compiles_one_hue_per_group() -> None:
    """Membership compilation, not per-node painting: every member of zone 0
    shares one tone and every member of zone 1 the other. The focal node is in
    neither — it is what the partition divides."""
    lay = _wings(
        [{"id": i, "label": i, "desc": "v"} for i in ("a", "b", "c", "d")],
        zones=["build", "ship"],
        partition_chroma="zone",
    )
    hues = _hues(lay)
    assert hues["a"] == hues["b"] == -1
    assert hues["c"] == hues["d"] == 0
    assert hues["hub"] == -1
    assert len({hues[k] for k in ("a", "b", "c", "d")}) == 2


def test_hue_follows_a_node_across_the_partition() -> None:
    """Hue is a function of membership, so re-declaring a node on the other
    side of the midpoint moves its hue with it — nothing is pinned per node."""
    order = ["a", "b", "c", "d"]
    lay = _wings(
        [{"id": i, "label": i, "desc": "v"} for i in order],
        zones=["build", "ship"],
        partition_chroma="zone",
    )
    moved = _wings(
        [{"id": i, "label": i, "desc": "v"} for i in ["c", "a", "b", "d"]],
        zones=["build", "ship"],
        partition_chroma="zone",
    )
    assert _hues(lay)["c"] == 0  # second half
    assert _hues(moved)["c"] == -1  # first half


def test_partition_binds_labels_marks_and_wires_together() -> None:
    """One group decision, three channels: the accent group's labels take the
    hue, its wires take it, and the neutral group's wires stroke ink."""
    lay = _wings(
        [{"id": i, "label": i, "desc": "v", "kind": "database"} for i in ("a", "b", "c", "d")],
        zones=["build", "ship"],
        partition_chroma="zone",
    )
    assert _node(lay, "c").label_accent and _node(lay, "d").label_accent
    assert not _node(lay, "a").label_accent and not _node(lay, "b").label_accent
    ink = [c for c in lay.connectors if c.ink_wire]
    hued = [c for c in lay.connectors if c.accent_index >= 0]
    assert len(ink) == 2 and len(hued) == 2
    assert not any(c.ink_wire and c.accent_index >= 0 for c in lay.connectors)


def test_partition_requires_two_zones() -> None:
    """A loud refusal, never a silent no-op: hue compiled from a partition the
    spec never declared would name nothing the reader can see."""
    with pytest.raises(Exception, match="zone"):
        _wings([{"id": "a", "label": "a", "desc": "v"}], zones=["only one"], partition_chroma="zone")


def test_partition_refuses_layouts_with_no_structural_split() -> None:
    with pytest.raises(Exception, match="partition_chroma is legal on"):
        solve(
            topology="pipeline",
            zones=["before", "after"],
            partition_chroma="zone",
            nodes=[{"id": "a", "label": "a"}, {"id": "b", "label": "b"}],
        )


def test_undeclared_partition_leaves_wires_untouched() -> None:
    """The knob is opt-in: a bilateral spec that does not declare it keeps its
    previous dress exactly (reverse-etl shares this cell). The ink class is
    emitted into the defs unconditionally like every other flow class — what
    must not happen is any ELEMENT binding to it."""
    import re

    from hyperweave.compose.engine import compose
    from hyperweave.core.models import ComposeSpec

    lay = solve(**resolve_bundled_spec("diagram", "fanout-bilateral").value)
    assert not any(c.ink_wire for c in lay.connectors)
    svg = compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="bare",
            palette="fixed",
            surface_face="light",
            diagram=resolve_bundled_spec("diagram", "fanout-bilateral").value,
        )
    ).svg
    assert not [c for c in re.findall(r'class="([^"]*)"', svg) if "flink" in c]


# ── the shipped composition ──────────────────────────────────────────────────


def test_preset_composition_pins() -> None:
    """The bilateral wings composition, as the specimen draws it."""
    lay = solve(**resolve_bundled_spec("diagram", PRESET).value)
    cards = [n for n in lay.nodes if n.shape == "rect"]
    heroes = [n for n in cards if n.role == "hero"]
    assert len(cards) == 5
    assert len(heroes) == 1
    assert (heroes[0].box.w, heroes[0].box.h) == (220.0, 184.0)
    assert len(lay.connectors) == 4
    assert all(c.marker_d for c in lay.connectors)
    assert sum(1 for c in lay.connectors if c.ink_wire) == 2
    assert sum(1 for c in lay.connectors if c.accent_index >= 0) == 2
    assert sum(1 for n in cards if n.glyph is not None) == 5
    assert sorted(n.box.h for n in cards if n.role != "hero") == [92.0, 92.0, 92.0, 114.0]


def test_compass_satellites_solve_their_own_snug_widths() -> None:
    """Per-card snug widths (owner ruling, superseding the shared ring
    width): a compass satellite's width is its own content's, never inflated
    to the widest sibling — the hand file measures 188/188/188/196, MEM
    earning its extra 8px from its own ink. Heights already solved per
    member; the box is the anatomy's own on both axes."""
    lay = solve(**resolve_bundled_spec("diagram", PRESET).value)
    widths = {n.node_id: n.box.w for n in lay.nodes if n.role != "hero" and n.shape == "rect"}
    assert len(set(widths.values())) > 1, "satellite widths equalized — the superseded uniform ring width"
    assert max(widths.values()) > min(widths.values())
    assert widths["writer"] == max(widths.values())


def test_classic_compass_ring_stays_width_aligned() -> None:
    """The snug ruling is the card+label anatomy's own: a classic card ring
    keeps the aligned shared box, byte-for-byte."""
    lay = solve(
        topology="hub",
        hub_policy="compass",
        nodes=[
            {"id": "core", "label": "core", "desc": "the hub", "role": "hero"},
            {"id": "a", "label": "alpha", "desc": "short", "anchor": "W"},
            {"id": "b", "label": "beta", "desc": "a much longer description run", "anchor": "E"},
        ],
        edges=[{"source": "core", "target": "a"}, {"source": "core", "target": "b"}],
    )
    widths = {n.box.w for n in lay.nodes if n.role != "hero" and n.shape == "rect"}
    assert len(widths) == 1


def test_square_arrivals_are_straight_for_one_marker_length() -> None:
    """The visible wire under the head, not merely the t=1 derivative, must
    agree with the arrow axis.  The final path segment is at least the cited
    13px head length and is exactly collinear with its card-face normal."""
    from hyperweave.compose.diagram.paths import sample_path

    lay = solve(**resolve_bundled_spec("diagram", PRESET).value)
    for conn in lay.connectors:
        points = sample_path(conn.path_d)
        assert len(points) >= 2
        (x0, y0), (x1, y1) = points[-2:]
        assert math.hypot(x1 - x0, y1 - y0) >= 13.0 - 0.1
        assert abs(y1 - y0) <= 0.1


def test_corner_exit_launch_stays_diagonal() -> None:
    """The spoke LAUNCHES off the crown's corner, not along its face.

    This is the assertion whose absence let a green suite hide a real
    regression: a generic square-arrival helper was swapped in, which departs
    along the card face at 0deg/180deg, and every existing test still passed
    because they all graded the ARRIVAL. The hand file leaves its four corners
    at -122.5 / +120.7 / -60.9 / +59.3 degrees — steeply diagonal, never
    axis-aligned. An axis-aligned launch here means the corner construction has
    been replaced by an S-curve again.
    """
    lay = solve(**resolve_bundled_spec("diagram", PRESET).value)
    hero = next(n for n in lay.nodes if n.role == "hero")
    launches = []
    for conn in lay.connectors:
        nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", conn.path_d)]
        launches.append(math.degrees(math.atan2(nums[3] - nums[1], nums[2] - nums[0])))
    assert len(launches) == 4
    for deg in launches:
        off_axis = min(abs(((deg - a + 180) % 360) - 180) for a in (0.0, 180.0, -180.0, 90.0, -90.0))
        # 20deg is the separator, not a taste band: the regression launched at
        # EXACTLY 0/180 (along the face) while the hand file's own corners sit
        # 29-33deg off their nearest axis. Anything under 20 is a face launch.
        assert off_axis >= 20.0, f"spoke launches at {deg:.1f}deg — that is along a face, not off a corner"
        # ...and within reach of the hand file's own measured corner launches.
        assert min(abs(((deg - a + 180) % 360) - 180) for a in (-122.5, 120.7, -60.9, 59.3)) <= 12.0
    # The launch also starts INSIDE the crown, never on its vertex.
    for conn in lay.connectors:
        nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", conn.path_d)]
        sx, sy = nums[0], nums[1]
        assert hero.box.x <= sx <= hero.box.x + hero.box.w
        assert hero.box.y <= sy <= hero.box.y + hero.box.h


@pytest.mark.parametrize("orientation", ["upward", "downward"])
def test_vertical_fan_arrivals_follow_the_visible_curve(orientation: str) -> None:
    """The head must agree with the last head-length of visible wire, not
    merely with an analytic endpoint derivative.  The hand specimen tolerates
    about 22 degrees while the retired upward route missed by 74.5 degrees."""
    from hyperweave.compose.diagram.paths import sample_path

    nodes = [
        {"id": "soc", "label": "apple silicon", "desc": "M4 Pro", "role": "hero"},
        *({"id": f"n{i}", "label": f"unit {i}", "desc": "ready"} for i in range(4)),
    ]
    if orientation == "downward":
        nodes[0]["gather"] = True
    lay = solve(
        topology="fanout",
        orientation=orientation,
        node_style="card+label",
        marker="arrow",
        nodes=nodes,
        edges=[{"source": "soc", "target": f"n{i}", "marker": "arrow"} for i in range(4)],
    )

    for conn in lay.connectors:
        points = sample_path(conn.path_d)
        end_x, end_y = points[-1]
        remaining = 13.0
        approach_x, approach_y = points[0]
        for (x0, y0), (x1, y1) in zip(reversed(points[:-1]), reversed(points[1:]), strict=True):
            segment = math.hypot(x1 - x0, y1 - y0)
            if segment >= remaining:
                t = remaining / segment
                approach_x = x1 + (x0 - x1) * t
                approach_y = y1 + (y0 - y1) * t
                break
            remaining -= segment
        off_axis = math.degrees(math.atan2(abs(end_x - approach_x), abs(end_y - approach_y)))
        assert off_axis <= 25.0


def test_forced_plate_callers_preserve_card_label_anatomy() -> None:
    """Lanes, axial and convergence constrain the outer plate, not the
    caller's requested rectangular anatomy."""
    lanes = solve(
        topology="lanes",
        lanes=["ingest", "serve"],
        node_style="card+label",
        nodes=[
            {"id": "queue", "label": "queue", "desc": "18 waiting\np95 2.4s", "category": "ingest"},
            {"id": "parser", "label": "parser", "desc": "8 workers\n62% busy", "category": "ingest"},
            {"id": "api", "label": "api", "desc": "4 replicas\np95 84ms", "category": "serve"},
            {"id": "cache", "label": "cache", "desc": "91% hits\n38 GB", "category": "serve"},
        ],
        edges=[
            {"source": "queue", "target": "parser"},
            {"source": "parser", "target": "api"},
            {"source": "api", "target": "cache"},
        ],
    )
    assert {n.label.cls for n in lanes.nodes} == {"nlbl"}

    axial = solve(
        topology="hub",
        hub_policy="axial",
        node_style="card+label",
        nodes=[
            {"id": "core", "label": "control plane", "desc": "plan\ndispatch\nmerge", "role": "hero"},
            {"id": "write", "label": "writer", "desc": "12 drafts"},
            {"id": "read", "label": "reader", "desc": "48 sources"},
        ],
        edges=[
            {"source": "write", "target": "core", "role": "edit"},
            {"source": "core", "target": "read", "role": "read"},
        ],
    )
    # The anatomy survives the forced plate — and the dominance band (this
    # composition's satellites are light, so the core renders the STANDARD
    # card+label register with hero dress, never the legacy name/desc card).
    assert _node(axial, "core").label.cls == "nlbl"
    assert [t.cls for t in _node(axial, "core").desc_lines] == ["nval", "nval", "nval"]

    convergence = solve(
        topology="fanin",
        node_style="card+label",
        nodes=[
            {"id": "tests", "label": "tests", "desc": "4472 passed"},
            {"id": "types", "label": "types", "desc": "strict"},
            {"id": "lint", "label": "lint", "desc": "0 findings"},
            {
                "id": "verdict",
                "label": "release verdict",
                "desc": "all required quality gates satisfied without suppressing regressions",
            },
        ],
    )
    # The band demotes this focal too (a display-voice run of that sentence
    # would dwarf the three light inputs) — the anatomy holds, the values
    # ride the standard voice, and every run still fits its own box.
    focal = _node(convergence, "verdict")
    assert focal.label.cls == "nlbl"
    value_voice = load_paradigms()["primer"].diagram.card_value_voice
    from hyperweave.compose.matrix.cells import measure_voice

    assert all(measure_voice(t.text, value_voice) <= focal.box.w + 0.51 for t in focal.desc_lines)


def test_muted_text_and_crown_identity_glyph_emit_semantic_classes() -> None:
    from hyperweave.compose import compose
    from hyperweave.core.models import ComposeSpec

    diagram = {
        "topology": "hub",
        "hub_policy": "compass",
        "node_style": "card+label",
        # The crown is spec-pinned so its identity-mark promotion renders
        # even beside these light satellites (the dominance band would
        # otherwise demote the register — pinned = the author's ruling).
        "chassis": {"hero": {"w": 220, "h": 184}},
        "nodes": [
            {"id": "core", "label": "control plane", "desc": "plan\nmerge", "role": "hero", "kind": "workflow"},
            {"id": "old", "label": "retired", "desc": "0 traffic", "role": "muted", "kind": "server", "anchor": "W"},
            {"id": "live", "label": "active", "desc": "12k rpm", "kind": "server", "anchor": "E"},
        ],
        "edges": [{"source": "core", "target": "old"}, {"source": "core", "target": "live"}],
    }
    svg = compose(ComposeSpec(type="diagram", genome_id="primer", diagram=diagram)).svg
    assert re.search(r'class="[^"]*-nlbl [^"]*-nmuted"', svg)
    assert re.search(r'class="[^"]*-nval [^"]*-nmuted"', svg)
    assert re.search(r'<g[^>]+class="[^"]*-fl(?:ps|s)"[^>]*>\s*<path', svg)


def test_preset_cites_the_specimen_s_edge_dress() -> None:
    """The heavier fan is a chassis CITATION scoped to this preset — the kit
    default and every other bilateral spec are untouched."""
    from hyperweave.compose.diagram import render_chassis
    from hyperweave.compose.diagram.input import coerce_diagram_input
    from hyperweave.core.models import ComposeSpec

    cfg = load_paradigms()["primer"].diagram
    mine = coerce_diagram_input(
        ComposeSpec(type="diagram", genome_id="primer", diagram=resolve_bundled_spec("diagram", PRESET).value).diagram,
        ComposeSpec(type="diagram", genome_id="primer", diagram=resolve_bundled_spec("diagram", PRESET).value),
    ).spec
    ch = render_chassis(mine, cfg)
    assert (ch.wire_w, ch.marker_size) == (2.5, 13.0)
    assert ENGINE["connector"]["stroke_width"] == 1.5
    assert ENGINE["connector"]["marker_size"] == 8


def test_renamed_preset_refusal_teaches_the_new_id() -> None:
    """Hard break with a teaching refusal: the retired id stops resolving, and
    the error names its replacement instead of a forty-item menu."""
    from hyperweave.core.errors import HwError

    with pytest.raises(HwError) as exc:
        resolve_bundled_spec("diagram", "hub-panel-orchestrator")
    assert "hub-text" in exc.value.fix


# ── refusals: authored content is never silently dropped ─────────────────────


def test_chips_on_card_label_refuse() -> None:
    """card+label's slots are the label and the value stack — it hosts no chip
    row. Dropping an authored row silently is the unsafe outcome."""
    with pytest.raises(Exception, match="no chip row"):
        _wings([{"id": "a", "label": "a", "desc": "v", "chips": ("one", "two")}])


def test_embed_on_card_label_refuses() -> None:
    with pytest.raises(Exception, match="reserves no"):
        _wings(
            [
                {
                    "id": "a",
                    "label": "a",
                    "desc": "v",
                    "embed": {
                        "topology": "pipeline",
                        "nodes": [{"id": "i", "label": "i"}, {"id": "j", "label": "j"}],
                    },
                }
            ]
        )


def test_per_node_accent_under_partition_refuses() -> None:
    """One hue per GROUP: a member that opted out would carry a label hue
    disagreeing with its own group-derived wire."""
    with pytest.raises(Exception, match="ONE hue per group"):
        solve(
            topology="fanout",
            orientation="bilateral",
            node_style="card+label",
            zones=["build", "ship"],
            partition_chroma="zone",
            nodes=[
                {"id": "hub", "label": "hub", "desc": "x", "role": "hero"},
                {"id": "a", "label": "a", "desc": "v", "accent": 2},
                {"id": "b", "label": "b", "desc": "v"},
                {"id": "c", "label": "c", "desc": "v"},
                {"id": "d", "label": "d", "desc": "v"},
            ],
            edges=[{"source": "hub", "target": t} for t in ("a", "b", "c", "d")],
        )


def test_muted_card_label_keeps_the_muted_dash() -> None:
    """The dashed border is the MUTED family's signal, not a card-anatomy
    detail — a muted card+label that dropped it would read active."""
    lay = _wings([{"id": "a", "label": "a", "desc": "v", "role": "muted"}])
    assert _node(lay, "a").stroke_dasharray


def test_partition_hue_reaches_the_corner_mark() -> None:
    """The contract says the group's hue spans label, MARK and wire. A generic
    kind mark collapses to ink unless the partition lifts its tint selection,
    so this pins the mark specifically — the channel a label/wire-only
    assertion cannot see."""
    lay = _wings(
        [{"id": i, "label": i, "desc": "v", "kind": "database"} for i in ("a", "b", "c", "d")],
        zones=["build", "ship"],
        partition_chroma="zone",
    )
    ink = _node(lay, "a").glyph
    hued = _node(lay, "c").glyph
    assert ink is not None and hued is not None
    assert hued.tint == "hue" and hued.accent_index >= 0
    assert ink.tint == "ink"
