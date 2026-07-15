"""sec 8 cross-topology idiom sweep + §1 axial policy pins (diagrams-v2).

The idiom registry (data/registries/idioms.yaml) is UNIVERSAL chrome: the
relations (assert/drift/flow/bypass), the chip-row, the edge-chip, and
the dot terminal render on EVERY topology — registry/chrome vocabulary,
never solver-local code. The sweep is the first-customer proof: axial
consumes the same vocabulary every other topology already renders.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from hyperweave.core.diagram import DiagramCapacityError
from tests.compose.test_diagram_layout import CASES, solve

# ── Sweep matrices ───────────────────────────────────────────────────────────

# Topologies that accept DECLARED edges (the relation/edge-chip idioms bind
# to declared edges; synthesized-edge topologies have nothing to dress).
_EDGE_CASES: dict[str, dict[str, Any]] = {
    "pipeline": dict(
        topology="pipeline",
        title="T",
        nodes=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
        edges=[{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
    ),
    "sequence": copy.deepcopy(CASES["sequence"]),
    "dag": dict(
        topology="dag",
        title="T",
        nodes=[
            {"id": "a", "label": "A"},
            {"id": "b", "label": "B"},
            {"id": "c", "label": "C"},
            {"id": "d", "label": "D"},
        ],
        edges=[
            {"source": "a", "target": "b"},
            {"source": "a", "target": "c"},
            {"source": "b", "target": "d"},
            {"source": "c", "target": "d"},
        ],
    ),
    "state-machine": dict(
        topology="state-machine",
        title="T",
        nodes=[{"id": "s0", "label": "Idle"}, {"id": "s1", "label": "Run"}, {"id": "s2", "label": "Done"}],
        edges=[
            {"source": "s0", "target": "s1", "label": "start"},
            {"source": "s1", "target": "s2", "label": "finish"},
        ],
    ),
    "hub-compass": copy.deepcopy(CASES["hub"]),
    "hub-axial": dict(
        topology="hub",
        title="T",
        nodes=[
            {"id": "core", "label": "CORE", "role": "hero"},
            {"id": "w", "label": "west"},
            {"id": "n", "label": "north"},
            {"id": "s", "label": "south"},
            {"id": "e", "label": "east"},
        ],
        edges=[
            {"source": "w", "target": "core", "role": "in"},
            {"source": "core", "target": "n", "role": "edit"},
            {"source": "core", "target": "s", "role": "read"},
            {"source": "core", "target": "e", "role": "out"},
        ],
    ),
    "lanes": copy.deepcopy(CASES["lanes"]),
}

# Chips are node-level CARD chrome — they sweep every topology whose nodes
# render a card body. State-machine pills are TOKENS (single-line identity
# marks, no card body); sequence participant HEADS are a fixed glyph-above-
# name anatomy with no text-block row a chip could append to. Both are
# structural no-ops, pinned separately below (test_token_topologies_have_no_chip_surface).
_CHIP_CASES: dict[str, dict[str, Any]] = {
    **{k: copy.deepcopy(v) for k, v in CASES.items() if k != "sequence"},
    "dag": copy.deepcopy(_EDGE_CASES["dag"]),
}

# Expected dress per relation. assert is the one still relation (dress
# motion "none" → static solid rail); drift/flow/bypass all carry a MARCHING
# dash channel (track dash-march), so their static_dash reads empty while
# marching — the dash texture only surfaces as a static_dash literal when a
# dressed edge resolves inert (diagrams-v3 kit).
_DRESS = {
    "assert": {"dash": "", "marker": "chevron", "track": "static"},
    "drift": {"dash": "", "marker": "dot", "track": "dash-march"},
    "flow": {"dash": "", "marker": "", "track": "dash-march"},
    "bypass": {"dash": "", "marker": "dot", "track": "dash-march"},  # piece 4: skips end in a terminal dot
}


def _with_relation(case: dict[str, Any], relation: str) -> dict[str, Any]:
    spec = copy.deepcopy(case)
    spec["edges"][0]["relation"] = relation
    return spec


def _marker_kind(marker_d: str) -> str:
    if not marker_d:
        return ""
    return "dot" if " A " in f" {marker_d} " or ",0 1,0 " in marker_d else "chevron"


class TestRelationSweep:
    """sec 3 line idioms are relations binding EXISTING dress vocabulary —
    identical output contract on every edge-declaring topology."""

    @pytest.mark.parametrize("slug", sorted(_EDGE_CASES))
    @pytest.mark.parametrize("relation", sorted(_DRESS))
    def test_relation_dress_on_every_topology(self, slug: str, relation: str) -> None:
        # (The old sequence-flow crash — replay_idx built from the pre-dress
        # motion table — is fixed: wiring.py resolves post-dress effective
        # motions in one pre-pass shared by the choreography orders.)
        lay = solve(**_with_relation(_EDGE_CASES[slug], relation))
        conns = [c for c in lay.connectors if c.index == 0]
        assert conns, (slug, relation)
        want = _DRESS[relation]
        for c in conns:
            assert c.relation == relation, (slug, relation)
            assert c.static_dash == want["dash"], (slug, relation, c.static_dash)
            assert c.track == want["track"], (slug, relation, c.track)
        if relation == "flow":
            # L3 flow: particle riders ON the dressed edge.
            assert any(p.connector_index == 0 for p in lay.particles), slug
        # The terminal rides the last segment reaching the target.
        marked = [c for c in conns if c.marker_d]
        if want["marker"]:
            assert marked, (slug, relation)
            assert _marker_kind(marked[-1].marker_d) == want["marker"], (slug, relation)
        else:
            assert not marked, (slug, relation, [c.marker_d for c in marked])

    @pytest.mark.parametrize("slug", sorted(_EDGE_CASES))
    def test_relation_stills_the_wire(self, slug: str) -> None:
        # drift's dress motion is "dash" (a marching rail, no rider) — only
        # motion=particle spawns particles, so the dressed edge never carries
        # one, whatever the artifact's edge-motion would have done.
        spec = _with_relation(_EDGE_CASES[slug], "drift")
        lay = solve(**spec)
        assert all(p.connector_index != 0 for p in lay.particles), slug


class TestChipRowSweep:
    """Chip-row: in-card pills on ANY topology's cards (universal chrome
    solved by solve_card_box/place_card, consumed by axial as one customer)."""

    @pytest.mark.parametrize("slug", sorted(_CHIP_CASES))
    def test_chips_render_on_every_topology(self, slug: str) -> None:
        spec = copy.deepcopy(_CHIP_CASES[slug])
        spec["nodes"][1]["chips"] = ["alpha", "beta"]
        lay = solve(**spec)
        chipped = [n for n in lay.nodes if n.index == 1]
        assert chipped and len(chipped[0].chip_boxes) == 2, slug
        assert len(chipped[0].chip_texts) == 2, slug
        # Pills live inside their card box.
        card = chipped[0].box
        for b in chipped[0].chip_boxes:
            assert b.x >= card.x - 0.5 and b.x + b.w <= card.x + card.w + 0.5, slug
            assert b.y >= card.y - 0.5 and b.y + b.h <= card.y + card.h + 0.5, slug

    @pytest.mark.parametrize("slug", ["sequence"])
    def test_token_topologies_have_no_chip_surface(self, slug: str) -> None:
        # Sequence participant HEADS are a fixed glyph-above-name anatomy —
        # no card body a chip row could append to. A declared chip row is
        # structurally absent, never a crash. (State-machine left this list
        # with the retired pill anatomy: its rx-13 cards host chips like any
        # other card.)
        spec = copy.deepcopy(_EDGE_CASES[slug])
        spec["nodes"][1]["chips"] = ["alpha"]
        lay = solve(**spec)
        assert all(len(n.chip_boxes) == 0 for n in lay.nodes), slug


class TestEdgeChipSweep:
    """Edge-chip: a pill riding ON the wire midpoint wherever an edge
    label declares label_style=chip."""

    @pytest.mark.parametrize("slug", sorted(_EDGE_CASES))
    def test_edge_chip_on_every_topology(self, slug: str) -> None:
        spec = copy.deepcopy(_EDGE_CASES[slug])
        spec["edges"][0]["label"] = "hwz/1"
        spec["edges"][0]["label_style"] = "chip"
        lay = solve(**spec)
        chips = [a for a in lay.annotations if a.kind == "edge-chip"]
        if not chips:
            # Balance rule (cicd-machine hw:approach): a run too short to
            # show wire both sides of the pill floats its label as a
            # micro-label instead — the chip demotes, it never crams.
            floats = [a for a in lay.annotations if a.kind == "label" and a.lines and a.lines[0].text == "hwz/1"]
            assert floats, slug
            geo = next(c for c in lay.connectors if c.index == 0)
            from hyperweave.compose.diagram.sizing import solve_chip_box
            from hyperweave.config.loader import load_paradigms

            chip_w = solve_chip_box("hwz/1", load_paradigms()["primer"].diagram)[0]
            assert geo.length < chip_w + 2 * 18, (slug, geo.length)
            return
        chip = chips[0]
        # Edge-chip is the SAME rounded-rect pill as a node chip (hub
        # draws both at h=26 rx=8), never a full pill.
        from hyperweave.compose.diagram.sizing import CHIP_H, CHIP_RX

        assert chip.box is not None and chip.box.rx == CHIP_RX and chip.box.h == CHIP_H, slug
        assert chip.lines and chip.lines[0].text == "hwz/1", slug


# ── §1 axial policy pins ─────────────────────────────────────────────────────


def _axial_spec(**over: Any) -> dict[str, Any]:
    spec = copy.deepcopy(_EDGE_CASES["hub-axial"])
    spec.update(over)
    return spec


def _center(n: Any) -> tuple[float, float]:
    return (n.box.x + n.box.w / 2, n.box.y + n.box.h / 2)


class TestAxialPolicy:
    def test_partition_roles_to_half_planes(self) -> None:
        lay = solve(**_axial_spec())
        by_id = {n.node_id: n for n in lay.nodes}
        hx, hy = _center(by_id["core"])
        assert _center(by_id["w"])[0] < hx  # in → W
        assert _center(by_id["n"])[1] < hy  # edit → N
        assert _center(by_id["s"])[1] > hy  # read → S
        assert _center(by_id["e"])[0] > hx  # out → E fan

    def test_nucleus_prominence_factor(self) -> None:
        # §11.4a: hero area ≥ ledger factor x satellite area (264x100 vs
        # 220x64 ~= 1.9), aspect held — never a guess.
        lay = solve(**_axial_spec())
        by_id = {n.node_id: n for n in lay.nodes}
        hero = by_id["core"].box
        sat = by_id["e"].box
        assert hero.w * hero.h >= 1.9 * sat.w * sat.h - 0.5

    def test_destination_fan_is_accent_bound_tangent_curves(self) -> None:
        lay = solve(**_axial_spec())
        fan = [c for c in lay.connectors if c.index == 3]
        assert fan, "out edge missing"
        c = fan[0]
        assert " C " in c.path_d  # tangent bezier, never a straight spoke
        assert c.accent_wire and c.relation == "assert"
        assert c.static_dash == "" and c.marker_d  # solid accent assert + arrow
        # invisible-riders: nothing rides the accent stroke.
        assert all(p.connector_index != 3 for p in lay.particles)

    def test_read_edge_wears_drift(self) -> None:
        lay = solve(**_axial_spec())
        read = [c for c in lay.connectors if c.index == 2]
        assert read and read[0].relation == "drift"
        # drift marches (track dash-march) — static_dash is empty while
        # marching; the dash texture only bakes in when the edge is inert.
        assert read[0].static_dash == ""
        assert read[0].track == "dash-march"
        assert _marker_kind(read[0].marker_d) == "dot"

    def test_policy_resolution_ladder(self) -> None:
        # role-only → axial (hero renders as a CARD on the spine).
        lay = solve(**_axial_spec())
        assert all(n.shape != "circle" for n in lay.nodes)
        # compass vocabulary (zone) → compass (hub disc returns).
        zoned = _axial_spec()
        zoned["edges"][0]["zone"] = "W"
        lay2 = solve(**zoned)
        assert any(n.shape == "circle" for n in lay2.nodes)
        # explicit hub_policy beats the vocabulary inference.
        forced = _axial_spec(hub_policy="axial")
        forced["edges"][0]["zone"] = "W"
        lay3 = solve(**forced)
        assert all(n.shape != "circle" for n in lay3.nodes)

    def test_zone_headers_from_spec_zones_and_default_none(self) -> None:
        # Two SEMANTIC group headers via the ONE zone-header law (spec.zones
        # data — the retired zone_headers:"corners" flag carried hardcoded
        # Python strings, against Invariant 5). First zone reads ink left;
        # second reads accent right-anchored.
        lay = solve(**_axial_spec(zones=["operations", "destinations"]))
        headers = sorted(b.header.text for b in lay.lane_bands)
        assert headers == ["DESTINATIONS", "OPERATIONS"]
        cls = {b.header.text: b.header.cls for b in lay.lane_bands}
        assert cls["DESTINATIONS"] == "zoneha" and cls["OPERATIONS"] == "zoneh"
        assert solve(**_axial_spec()).lane_bands == ()

    def test_fan_capacity(self) -> None:
        nodes = [{"id": "core", "label": "CORE", "role": "hero"}]
        edges = []
        for i in range(9):
            nodes.append({"id": f"d{i}", "label": f"dest{i}"})
            edges.append({"source": "core", "target": f"d{i}", "role": "out"})
        with pytest.raises(DiagramCapacityError):
            solve(topology="hub", title="T", nodes=nodes, edges=edges)

    def test_determinism(self) -> None:
        assert solve(**_axial_spec()) == solve(**_axial_spec())
