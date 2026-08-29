"""The authored grouping device, across every topology that can host it.

`regions:` used to validate on any spec and DRAW on three slugs, so every other
family accepted the key and rendered nothing — the accept-and-ignore this
matrix exists to keep closed. Each cell either draws lawfully or refuses by
name; nothing is allowed to accept silently again.
"""

from __future__ import annotations

from typing import Any

import pytest

from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import coerce_diagram_input, resolve_auto_roles, resolve_diagram_preset
from hyperweave.config.loader import load_diagram_config, load_paradigms
from hyperweave.core.diagram import DiagramInputError, DiagramSpec
from hyperweave.core.models import ComposeSpec

ENGINE = load_diagram_config()


def _solve(**kw: Any) -> Any:
    paradigm = load_paradigms()["primer"].diagram
    return compute_diagram_layout(
        resolve_auto_roles(DiagramSpec(**kw)), paradigm=paradigm, engine=ENGINE, palette_len=5
    )


def _nodes(n: int) -> list[dict[str, Any]]:
    return [{"id": c, "label": c} for c in "abcdefg"[:n]]


# One shape per family, plus the members that sit TOGETHER in it. A grouping
# whose members are scattered through the figure is a different question (the
# suppression law owns it) and is tested separately below.
CASES: dict[str, tuple[dict[str, Any], list[str]]] = {
    "pipeline": (
        dict(topology="pipeline", nodes=_nodes(4), edges=[{"source": s, "target": t} for s, t in ("ab", "bc", "cd")]),
        ["a", "b"],
    ),
    "pipeline-vertical": (
        dict(
            topology="pipeline",
            orientation="vertical",
            nodes=_nodes(4),
            edges=[{"source": s, "target": t} for s, t in ("ab", "bc", "cd")],
        ),
        ["a", "b"],
    ),
    "tree": (
        dict(topology="tree", nodes=_nodes(4), edges=[{"source": s, "target": t} for s, t in ("ab", "ac", "cd")]),
        ["c", "d"],
    ),
    "fanout": (
        dict(topology="fanout", nodes=_nodes(4), edges=[{"source": "a", "target": t} for t in "bcd"]),
        ["b", "c", "d"],
    ),
    "fanin": (
        dict(topology="fanin", nodes=_nodes(4), edges=[{"source": s, "target": "d"} for s in "abc"]),
        ["a", "b", "c"],
    ),
    "hub": (
        dict(topology="hub", nodes=_nodes(4), edges=[{"source": "a", "target": t} for t in "bcd"]),
        ["b", "c"],
    ),
    "sequence": (
        dict(topology="sequence", nodes=_nodes(4), edges=[{"source": s, "target": t} for s, t in ("ab", "bc", "cd")]),
        ["b", "c"],
    ),
    "fanout-radial": (
        dict(
            topology="fanout",
            orientation="radial",
            nodes=_nodes(4),
            edges=[{"source": "a", "target": t} for t in "bcd"],
        ),
        ["b", "c"],
    ),
    "cycle-ring": (
        dict(
            topology="cycle",
            orientation="ring",
            nodes=_nodes(4),
            edges=[{"source": s, "target": t} for s, t in ("ab", "bc", "cd", "da")],
        ),
        ["a", "b"],
    ),
    "dag": (
        dict(topology="dag", nodes=_nodes(4), edges=[{"source": s, "target": t} for s, t in ("ab", "bc", "cd")]),
        ["a", "b"],
    ),
    "dag-vertical": (
        dict(
            topology="dag",
            orientation="vertical",
            nodes=_nodes(4),
            edges=[{"source": s, "target": t} for s, t in ("ab", "bc", "cd")],
        ),
        ["a", "b"],
    ),
    "state-machine": (
        dict(
            topology="state-machine", nodes=_nodes(4), edges=[{"source": s, "target": t} for s, t in ("ab", "bc", "cd")]
        ),
        ["a", "b"],
    ),
}


@pytest.mark.parametrize("family", sorted(CASES))
@pytest.mark.parametrize("kind", ["band", "enclosure"])
def test_every_topology_draws_an_authored_region(family: str, kind: str) -> None:
    """The matrix. A region over members that sit together draws its box, on
    every family, in both kinds — and the box holds every one of them."""
    kw, members = CASES[family]
    lay = _solve(title="T", regions=[{"label": "alpha", "members": members, "kind": kind}], **kw)
    bands = [b for b in lay.lane_bands if b.region_id == "alpha"]
    assert bands, f"{family}/{kind} accepted `regions:` and drew nothing"
    box = bands[0].box
    for n in lay.nodes:
        if n.node_id in members:
            assert box.x <= n.box.x and box.y <= n.box.y, f"{family}/{kind}: {n.node_id} escapes its region"
            assert box.x + box.w >= n.box.x + n.box.w, f"{family}/{kind}: {n.node_id} escapes its region"
            assert box.y + box.h >= n.box.y + n.box.h, f"{family}/{kind}: {n.node_id} escapes its region"


@pytest.mark.parametrize("family", sorted(CASES))
def test_region_frames_never_cross(family: str) -> None:
    """Two regions either nest or stand clear — never partially overlap. The
    compositor cannot emit a crossing, which is what makes the render sweep's
    own version of this law a regression guard rather than an author's trap."""
    kw, members = CASES[family]
    others = [n["id"] for n in kw["nodes"] if n["id"] not in members]
    if not others:
        pytest.skip("no second group available in this shape")
    lay = _solve(
        title="T",
        regions=[
            {"label": "alpha", "members": members, "kind": "band"},
            {"label": "omega", "members": others, "kind": "enclosure"},
        ],
        **kw,
    )
    rects = [b.box for b in lay.lane_bands if b.region_id]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            a, b = rects[i], rects[j]
            if min(a.x + a.w, b.x + b.w) - max(a.x, b.x) <= 0 or min(a.y + a.h, b.y + b.h) - max(a.y, b.y) <= 0:
                continue
            holds = (a.x <= b.x and a.y <= b.y and a.x + a.w >= b.x + b.w and a.y + a.h >= b.y + b.h) or (
                b.x <= a.x and b.y <= a.y and b.x + b.w >= a.x + a.w and b.y + b.h >= a.y + a.h
            )
            assert holds, f"{family}: two region frames cross without containment"


def test_lanes_refuses_regions_by_name() -> None:
    """The one topology that already groups its nodes. A second grouping over
    the first is ambiguous, so it refuses rather than drawing both."""
    with pytest.raises(DiagramInputError, match="already groups its nodes"):
        _solve(
            title="T",
            topology="lanes",
            nodes=[{"id": c, "label": c, "category": "x" if c < "c" else "y"} for c in "abcd"],
            edges=[{"source": "a", "target": "b"}],
            regions=[{"label": "alpha", "members": ["a", "b"], "kind": "band"}],
        )


def test_interleaved_members_draw_nothing_and_name_both() -> None:
    """Members that alternate along the flow have no pair of rectangles. Both
    regions are suppressed and the note names the member to move — an absent
    box plus a sentence, never two boxes asserting a containment nobody
    declared."""
    lay = _solve(
        title="T",
        topology="pipeline",
        nodes=_nodes(4),
        edges=[{"source": s, "target": t} for s, t in ("ab", "bc", "cd")],
        regions=[
            {"label": "odd", "members": ["a", "c"], "kind": "band"},
            {"label": "even", "members": ["b", "d"], "kind": "enclosure"},
        ],
    )
    assert not [b for b in lay.lane_bands if b.region_id], "an interleaved pair drew a box"
    notes = [w for w in lay.rendered.warnings if "region" in w]
    assert notes, "an interleaved pair was suppressed silently"
    assert "'odd'" in notes[0] and "'even'" in notes[0], f"the note names neither region: {notes[0]}"


def test_declared_subset_nests_and_geometry_never_decides() -> None:
    """Containment is read off MEMBERSHIP. The inner sits fully inside the
    outer; two regions whose boxes merely intersect are not a nest."""
    lay = _solve(
        title="T",
        topology="pipeline",
        nodes=_nodes(4),
        edges=[{"source": s, "target": t} for s, t in ("ab", "bc", "cd")],
        regions=[
            {"label": "outer", "members": ["a", "b", "c"], "kind": "enclosure"},
            {"label": "inner", "members": ["a", "b"], "kind": "band"},
        ],
    )
    boxes = {b.region_id: b.box for b in lay.lane_bands if b.region_id}
    assert set(boxes) == {"outer", "inner"}, f"a declared nest did not draw: {sorted(boxes)}"
    o, i = boxes["outer"], boxes["inner"]
    assert o.x <= i.x and o.y <= i.y and o.x + o.w >= i.x + i.w and o.y + o.h >= i.y + i.h, (
        "the declared outer does not contain its inner"
    )


@pytest.mark.parametrize("preset", ["dag-balanced", "sm-loop", "sm-recursive"])
def test_region_labels_read_in_one_voice(preset: str) -> None:
    """One piece, one voice (owner ruling). Every grouping box names itself in
    the region voice — `lane` and the swimlane eyebrow are lane TITLES and keep
    their own."""
    cs = ComposeSpec(type="diagram", genome_id="primer", diagram=resolve_diagram_preset(preset))
    spec = coerce_diagram_input(cs.connector_data, cs).spec
    paradigm = load_paradigms()["primer"].diagram
    lay = compute_diagram_layout(spec, paradigm=paradigm, engine=ENGINE, palette_len=5)
    for band in lay.lane_bands:
        if band.region_id:
            assert band.header.cls == "rcnt", f"{preset}: region label reads {band.header.cls!r}"


def test_dag_builds_its_regions_once() -> None:
    """dag and state-machine build upstream because the under-channel needs
    each band's bottom edge before it can route. The shared pass recognises
    that by the `region_id` those bands carry — this pins that it does not
    build a second set on top."""
    lay = _solve(
        title="T",
        topology="dag",
        nodes=_nodes(4),
        edges=[{"source": s, "target": t} for s, t in ("ab", "bc", "cd")],
        regions=[{"label": "alpha", "members": ["a", "b"], "kind": "band"}],
    )
    assert [b.region_id for b in lay.lane_bands if b.region_id] == ["alpha"]


def test_label_style_moves_the_box_by_a_stated_amount() -> None:
    """The coupling `label_style` -> pad -> box height, stated as a number.

    A strip seats its label inside the TRAILING edge, so that pad holds it and
    the box is taller; a chip rides the border and seats nothing, so both pads
    stay at base. Correct, and it was invisible: the two pads are cited
    constants read through a branch, so nothing said that flipping the label
    moves the box — and the box moves the content bbox, which moves the
    caption. Four hops, each locally right, no guard between them. Only the
    specimen-parity gate noticed, and only for presets that have a fixture.
    """
    rb = ENGINE["region_band"]
    delta = float(rb["enclosure_bottom_pad"]) - float(rb["enclosure_top_pad"])
    kw = dict(
        title="T",
        topology="pipeline",
        nodes=_nodes(3),
        edges=[{"source": s, "target": t} for s, t in ("ab", "bc")],
    )
    heights = {}
    for style in ("chip", "strip"):
        lay = _solve(regions=[{"label": "g", "members": ["a", "b"], "label_style": style}], **kw)
        heights[style] = next(b.box.h for b in lay.lane_bands if b.region_id == "g")
    assert heights["strip"] - heights["chip"] == pytest.approx(delta), (
        f"strip {heights['strip']} vs chip {heights['chip']}: the box should differ by exactly "
        f"the trailing-pad delta ({delta}), which is the label's own seating"
    )


def _region_pads(lay: Any, member_ids: list[str]) -> tuple[float, float, float, float]:
    """Left/right/top/bottom air between a region's box and its member hull."""
    box = next(b.box for b in lay.lane_bands if b.region_id)
    mem = [p.box for p in lay.nodes if p.node_id in member_ids]
    return (
        round(min(m.x for m in mem) - box.x, 1),
        round(box.x + box.w - max(m.x + m.w for m in mem), 1),
        round(min(m.y for m in mem) - box.y, 1),
        round(box.y + box.h - max(m.y + m.h for m in mem), 1),
    )


@pytest.mark.parametrize(
    ("orientation", "small", "large"),
    [("horizontal", 4, 9), ("upward", 4, 7), ("downward", 4, 7)],
)
def test_region_pads_do_not_change_when_members_are_added(orientation: str, small: int, large: int) -> None:
    """A region's pads answer to the FLOW, so widening the fan cannot move them.

    The flow axis used to be measured from the placed bounding box, which grows
    with member count: a nine-way `fanout-horizontal` spans 826px down against
    769 across, reads as a vertical family, and its band swaps the along-flow
    pads for the across-flow ones — pads (26, 12) become (56, 38), reserving
    over-arc clearance a horizontal fan has no return edge to need. Nothing was
    red, because no corpus fanout is wide enough and no corpus fanout authors a
    region. `fanout-upward` was wrong at every size, its flow being vertical
    while its members spread across the full canvas width.

    Adding a member is the falsifier because it changes only the thing the old
    instrument read and nothing the answer depends on.
    """
    ids = lambda n: [f"n{i}" for i in range(1, n)]  # noqa: E731 - member ids, one expression
    pads = {}
    for n in (small, large):
        lay = _solve(
            title="T",
            topology="fanout",
            orientation=orientation,
            nodes=[{"id": f"n{i}", "label": f"node {i}"} for i in range(n)],
            edges=[{"source": "n0", "target": f"n{i}"} for i in range(1, n)],
            regions=[{"label": "workers", "members": ids(n), "kind": "band"}],
        )
        pads[n] = _region_pads(lay, ids(n))
    assert pads[small] == pads[large], (
        f"fanout-{orientation}: {small} members pad {pads[small]}, {large} members pad {pads[large]} — "
        f"the flow axis is a constant of the solver, so member count must not reach it"
    )
