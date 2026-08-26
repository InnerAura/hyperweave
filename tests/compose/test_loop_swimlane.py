"""The swimlane loop — lane-membership allocation, asserted at every seam.

The corpus's construction (the shuttle's role lanes): declared lanes become
full-width bands in order; every station centers in its lane; work moves
along the flow within a lane and crosses at the handoff column; a
cross-lane terminal drops in place at its source's rank; the return rides
the gutter adjacent to its target's lane at the gutter's own midline; and
the two directions' guards never collide — the crossing chip covers the one
declared crossing, the channel chip seats on its longest clear run.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec
from tests.compose.test_loop_solver import solve


def swimlane() -> dict[str, Any]:
    return {
        "topology": "loop",
        "orientation": "horizontal",
        "title": "Revise and resubmit",
        "lanes": ["agent", "human", "merged"],
        "nodes": [
            {"id": "draft", "label": "Draft", "desc": "agent writes v(n)", "category": "agent"},
            {"id": "review", "label": "Review", "desc": "human reads the diff", "category": "human"},
            {"id": "appr", "label": "Approve?", "station": "decision", "category": "human"},
            {
                "id": "ship",
                "label": "Shipped",
                "desc": "merged to main",
                "station": "terminal",
                "partition": "advance",
                "category": "merged",
            },
        ],
        "edges": [
            {"from": "draft", "to": "review", "label": "hands over", "label_style": "chip"},
            {"from": "review", "to": "appr"},
            {"from": "appr", "to": "ship", "label": "approved", "label_style": "chip"},
            {"from": "appr", "to": "draft", "label": "changes requested", "label_style": "chip", "circuit": "return"},
        ],
    }


def test_lanes_declare_and_members_belong() -> None:
    solve(swimlane())  # legal
    missing = swimlane()
    del missing["nodes"][0]["category"]
    with pytest.raises(ValidationError, match="every station lives in one"):
        solve(missing)
    stray = swimlane()
    stray["nodes"][0]["category"] = "robot"
    with pytest.raises(ValidationError, match="is not in the declared lanes"):
        solve(stray)


def test_every_station_centers_in_its_own_band() -> None:
    lay = solve(swimlane())
    assert len(lay.lane_bands) == 3
    by_id = {n.node_id: n for n in lay.nodes}
    lane_of = {"draft": 0, "review": 1, "appr": 1, "ship": 2}
    for nid, band_i in lane_of.items():
        band = lay.lane_bands[band_i].box
        n = by_id[nid]
        cy = n.box.y + n.box.h / 2
        assert band.y < cy < band.y + band.h, f"{nid} strays from its lane"
        assert abs(cy - (band.y + band.h / 2)) < 1.0, f"{nid} off its lane's centerline"


def test_cross_lane_terminal_drops_in_place() -> None:
    """The at-rank exit law spoken vertically: Shipped descends at its own
    Approve?'s major, never a rank later."""
    lay = solve(swimlane())
    by_id = {n.node_id: n for n in lay.nodes}
    appr, ship = by_id["appr"], by_id["ship"]
    assert abs((appr.box.x + appr.box.w / 2) - (ship.box.x + ship.box.w / 2)) < 1.0


def test_return_rides_the_gutter_midline() -> None:
    lay = solve(swimlane())
    agent = lay.lane_bands[0].box
    human = lay.lane_bands[1].box
    gutter_mid = (agent.y + agent.h + human.y) / 2
    ret = lay.connectors[3]
    import re

    ys = [float(m) for m in re.findall(r"[\d.]+,([\d.]+)", ret.path_d)]
    assert any(abs(y - gutter_mid) < 1.0 for y in ys), "the return channel rides the gutter's own midline"


def test_the_two_guards_never_collide() -> None:
    """The crossing chip covers the declared crossing; the channel chip
    seats on its longest clear run — their boxes stay disjoint."""
    lay = solve(swimlane())
    chips = [a.box for a in lay.annotations if a.kind == "edge-chip" and a.box is not None]
    for i, a in enumerate(chips):
        for b in chips[i + 1 :]:
            sep_x = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
            sep_y = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
            assert sep_x <= 0 or sep_y <= 0, "guard chips overlap"


def test_swimlane_composes_under_the_turn_register() -> None:
    svg = compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="opaque",
            palette="fixed",
            diagram={**swimlane(), "motion_register": "turn"},
        )
    ).svg
    assert "-ch0" in svg  # the register performs
    assert svg.count("AGENT") >= 1 and svg.count("MERGED") >= 1
