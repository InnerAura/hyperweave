"""Hub + lanes solver invariants.

Hub: spokes QUANTIZE to canonical compass slots (the rose's 22.5° half-step
grid) — one member takes its sector cardinal exactly, multiples take
symmetric uniform-pitch arrangements about it, contention resolves to the
next canonical arrangement (never a free angle); explicit angle/zone/anchor
overrides win by precedence; the hub paints last (emanation mask). The
quantization laws are verified as PROPERTIES over generated specs (3-12
spokes, varied labels, skewed sector loads) — verb_algebra's 0/45/90 shape
is one named case among many, not the objective. Lanes: categories → bands
(first-appearance order) with content-solved widths, a gutter bus between
adjacent bands, and a perimeter channel below all bands for long hauls that
never cuts a band interior; ``route:'bus'`` non-adjacent is illegal.
"""

from __future__ import annotations

import itertools
import math

import pytest

from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.hub import _support
from hyperweave.compose.diagram.input import resolve_auto_roles
from hyperweave.config.loader import load_diagram_config, load_paradigms
from hyperweave.core.diagram import DiagramCapacityError, DiagramInputError, DiagramSpec

ENGINE = load_diagram_config()


def solve(**kw: object) -> object:
    paradigm = load_paradigms()["primer"].diagram
    spec = resolve_auto_roles(DiagramSpec.model_validate(kw))
    return compute_diagram_layout(spec, paradigm=paradigm, engine=ENGINE, palette_len=5)


def _hub_center(lay: object) -> tuple[float, float]:
    """The hub disc's center — the canvas crops to CONTENT (R3), so the hub
    is no longer the canvas center; recover it from the placed circle."""
    hub = next(n for n in lay.nodes if n.shape == "circle")  # type: ignore[attr-defined]
    return (hub.box.x + hub.box.w / 2, hub.box.y + hub.box.h / 2)


def _angle_from_center(lay: object, node_id: str) -> float:
    """The compass angle (deg, 0=E clockwise) of a node's center about the
    HUB center (the spoke's bearing)."""
    hx, hy = _hub_center(lay)
    n = next(n for n in lay.nodes if n.node_id == node_id)  # type: ignore[attr-defined]
    cx = n.box.x + n.box.w / 2
    cy = n.box.y + n.box.h / 2
    return math.degrees(math.atan2(cy - hy, cx - hx))


def _hub_spec(policy: str = "", n_out: int = 3) -> dict[str, object]:
    """A hub with ``n_out`` 'out' spokes (all in the E sector; keep n_out ≤ the
    hub_max_per_zone cap of 3)."""
    nodes: list[dict[str, object]] = [{"id": "core", "label": "CORE", "role": "hero"}]
    edges: list[dict[str, object]] = []
    for i in range(n_out):
        nodes.append({"id": f"o{i}", "label": f"out{i}"})
        edges.append({"source": "core", "target": f"o{i}", "role": "out"})
    kw: dict[str, object] = dict(topology="hub", title="T", hub_policy="compass", nodes=nodes, edges=edges)
    if policy:
        kw["distribution"] = policy
    return kw


def _hub_spec_mixed() -> dict[str, object]:
    """A hub with spokes split across sectors (2 out → E, 2 in → W), so no
    single zone exceeds the per-zone cap — for canvas/determinism checks."""
    return dict(
        topology="hub",
        hub_policy="compass",
        title="T",
        nodes=[
            {"id": "core", "label": "CORE", "role": "hero"},
            {"id": "a", "label": "a"},
            {"id": "b", "label": "b"},
            {"id": "c", "label": "c"},
            {"id": "d", "label": "d"},
        ],
        edges=[
            {"source": "core", "target": "a", "role": "out"},
            {"source": "core", "target": "b", "role": "out"},
            {"source": "c", "target": "core", "role": "in"},
            {"source": "d", "target": "core", "role": "in"},
        ],
    )


class TestHubZoneResolution:
    def test_out_role_defaults_east(self) -> None:
        # role_zones.out = E (center 0°). Three 'out' spokes take the
        # preferred symmetric 45°-pitch arrangement about the cardinal —
        # the authored 0/±45 shape, exactly (never free angles).
        lay = solve(**_hub_spec(n_out=3))
        angles = sorted(_angle_from_center(lay, f"o{i}") for i in range(3))
        assert angles == pytest.approx([-45.0, 0.0, 45.0], abs=0.1)

    def test_in_role_defaults_west(self) -> None:
        lay = solve(
            topology="hub",
            hub_policy="compass",
            title="T",
            nodes=[
                {"id": "core", "label": "CORE", "role": "hero"},
                {"id": "a", "label": "a"},
                {"id": "b", "label": "b"},
            ],
            edges=[
                {"source": "a", "target": "core", "role": "in"},
                {"source": "b", "target": "core", "role": "in"},
            ],
        )
        # Two 'in' spokes pack about W (180°) at the measured pair splay
        # (±27.5 — fe2's S-pair card centers; hub.pair_splay), not the ±45
        # grid slots the quantizer once spread them to (atan2 folds
        # 152.5/207.5 to ±152.5).
        assert sorted(abs(_angle_from_center(lay, nid)) for nid in ("a", "b")) == pytest.approx([152.5, 152.5], abs=0.1)

    def test_explicit_angle_overrides_sector(self) -> None:
        # An explicit angle wins over the role default: send an 'out' spoke to
        # -90 (due N) despite role_zones.out = E.
        lay = solve(
            topology="hub",
            hub_policy="compass",
            title="T",
            nodes=[
                {"id": "core", "label": "CORE", "role": "hero"},
                {"id": "a", "label": "a"},
                {"id": "b", "label": "b"},
            ],
            edges=[
                {"source": "core", "target": "a", "role": "out", "angle": -90.0},
                {"source": "core", "target": "b", "role": "out"},
            ],
        )
        assert _angle_from_center(lay, "a") == pytest.approx(-90.0, abs=1.0)

    def test_zone_overrides_role_default(self) -> None:
        # An explicit zone (S = 90°) beats the role default (out → E); a
        # single member takes the sector's cardinal axis EXACTLY.
        lay = solve(
            topology="hub",
            hub_policy="compass",
            title="T",
            nodes=[
                {"id": "core", "label": "CORE", "role": "hero"},
                {"id": "a", "label": "a"},
                {"id": "b", "label": "b"},
            ],
            edges=[
                {"source": "core", "target": "a", "role": "out", "zone": "S"},
                {"source": "core", "target": "b", "role": "out"},
            ],
        )
        assert _angle_from_center(lay, "a") == pytest.approx(90.0, abs=0.1)
        assert _angle_from_center(lay, "b") == pytest.approx(0.0, abs=0.1)


class TestHubQuantization:
    def test_policies_converge_to_canonical_slots(self) -> None:
        # Quantization supersedes fractional distribution: every policy
        # yields the SAME canonical angles (crossing-minimized retains only
        # member→slot ordering, which is declaration order on a pure hub).
        expected = [-45.0, 0.0, 45.0]
        for policy in ("even", "golden", "balanced", "crossing-minimized"):
            lay = solve(**_hub_spec(policy, n_out=3))
            angles = sorted(_angle_from_center(lay, f"o{i}") for i in range(3))
            assert angles == pytest.approx(expected, abs=0.1), (policy, angles)

    def test_determinism(self) -> None:
        a = solve(**_hub_spec_mixed())
        b = solve(**_hub_spec_mixed())
        assert [n.box.x for n in a.nodes] == [n.box.x for n in b.nodes]  # type: ignore[attr-defined]


_SWEEP_ZONES: dict[str, list[str]] = {
    "spread": ["E", "W", "N", "S", "NE", "SW", "SE", "NW"],
    "opposed": ["E", "W"],
    "cardinal-packed": ["E", "S", "W", "N"],
}

# (pattern, n) cells: spoke counts 3-12, loads from round-robin spread to
# adjacent-cardinal packing; 'opposed' stops at 6 (3-per-zone cap on 2 zones).
_SWEEP = [
    *[("spread", n) for n in (3, 5, 8, 12)],
    *[("opposed", n) for n in (2, 4, 6)],
    *[("cardinal-packed", n) for n in (6, 9, 12)],
]


def _generated_zone(i: int, pattern: str) -> str:
    zones = _SWEEP_ZONES[pattern]
    return zones[i // 3] if pattern == "cardinal-packed" else zones[i % len(zones)]


def _sweep_spec(n: int, pattern: str) -> dict[str, object]:
    """A generated hub: n spokes with varied label/desc lengths, sectors
    assigned per the load pattern (never exceeding the 3-per-zone cap)."""
    labels = ["API", "ingest-service", "TRANSFORM LAYER", "db", "queue-worker", "auth"]
    descs = ["", "wraps into a long descriptive support line", "short", ""]
    nodes: list[dict[str, object]] = [{"id": "core", "label": "CORE", "role": "hero"}]
    edges: list[dict[str, object]] = []
    for i in range(n):
        node: dict[str, object] = {"id": f"s{i}", "label": f"{labels[i % len(labels)]}-{i}"}
        if descs[i % len(descs)]:
            node["desc"] = descs[i % len(descs)]
        nodes.append(node)
        edges.append({"source": "core", "target": f"s{i}", "role": "out", "zone": _generated_zone(i, pattern)})
    return dict(topology="hub", title="T", hub_policy="compass", nodes=nodes, edges=edges)


def _spoke_angles(lay: object) -> dict[str, float]:
    """Compass bearing (deg, normalized 0-360) of every spoke center about
    the HUB center (content-fit canvases are not hub-centered)."""
    hx, hy = _hub_center(lay)
    out: dict[str, float] = {}
    for nd in lay.nodes:  # type: ignore[attr-defined]
        if nd.node_id == "core":
            continue
        out[nd.node_id] = math.degrees(math.atan2(nd.box.y + nd.box.h / 2 - hy, nd.box.x + nd.box.w / 2 - hx)) % 360.0
    return out


def _zone_offsets(lay: object, n: int, pattern: str) -> dict[str, list[float]]:
    """Signed angular offsets (deg, sorted) of each generated zone's members
    from that zone's cardinal."""
    centers = ENGINE["hub"]["zone_centers"]
    angles = _spoke_angles(lay)
    out: dict[str, list[float]] = {}
    for i in range(n):
        zone = _generated_zone(i, pattern)
        diff = (angles[f"s{i}"] - float(centers[zone]) + 180.0) % 360.0 - 180.0
        out.setdefault(zone, []).append(diff)
    return {z: sorted(v) for z, v in out.items()}


class TestHubQuantizationProperties:
    """The quantization laws as PROPERTIES over generated specs — general
    solver policy, never fixture calibration (a rule that only holds at n=5
    is wrong). These pins are also the first computable entries of the
    layout-scoring objective (census: computable-gestalt ledger)."""

    @pytest.mark.parametrize(("pattern", "n"), _SWEEP)
    def test_every_spoke_on_a_canonical_slot(self, pattern: str, n: int) -> None:
        # Never free angles: every non-explicit spoke sits on the rose's
        # 22.5° half-step grid — OR at the measured pair splay (±27.5 off a
        # cardinal, fe2's S-pair; hub.pair_splay), the one ratified
        # off-grid slot a 2-occupant sector packs to.
        lay = solve(**_sweep_spec(n, pattern))
        for nid, ang in _spoke_angles(lay).items():
            frac = ang % 22.5
            on_grid = min(frac, 22.5 - frac) < 0.1
            off_cardinal = min(abs((ang - c + 180.0) % 360.0 - 180.0) for c in (0.0, 90.0, 180.0, 270.0))
            on_pair_splay = abs(off_cardinal - 27.5) < 0.1
            assert on_grid or on_pair_splay, (pattern, n, nid, ang)

    @pytest.mark.parametrize(("pattern", "n"), _SWEEP)
    def test_single_member_sectors_take_the_cardinal_exactly(self, pattern: str, n: int) -> None:
        lay = solve(**_sweep_spec(n, pattern))
        for zone, offs in _zone_offsets(lay, n, pattern).items():
            if len(offs) == 1:
                assert offs[0] == pytest.approx(0.0, abs=0.1), (pattern, n, zone, offs)

    @pytest.mark.parametrize(("pattern", "n"), _SWEEP)
    def test_within_sector_neighbor_gaps_equal(self, pattern: str, n: int) -> None:
        # Uniform pitch inside every sector — equal gaps by construction.
        lay = solve(**_sweep_spec(n, pattern))
        for zone, offs in _zone_offsets(lay, n, pattern).items():
            if len(offs) < 3:
                continue
            gaps = {round(b - a, 1) for a, b in itertools.pairwise(offs)}
            assert len(gaps) == 1, (pattern, n, zone, offs)

    @pytest.mark.parametrize(("pattern", "n"), _SWEEP)
    def test_balanced_sectors_mirror(self, pattern: str, n: int) -> None:
        # Equal-occupancy opposite sectors carry mirrored offset sets.
        lay = solve(**_sweep_spec(n, pattern))
        by_zone = _zone_offsets(lay, n, pattern)
        for a, b in (("E", "W"), ("N", "S"), ("NE", "SW"), ("SE", "NW")):
            if a in by_zone and b in by_zone and len(by_zone[a]) == len(by_zone[b]):
                mirrored = sorted(-o for o in by_zone[b])
                assert by_zone[a] == pytest.approx(mirrored, abs=0.1), (pattern, n, a, b, by_zone)

    @pytest.mark.parametrize(("pattern", "n"), _SWEEP)
    def test_spoke_clearance_per_axis(self, pattern: str, n: int) -> None:
        # The clearance law (sixth-review supersession of the one-ring pin):
        # hub-EDGE to card-edge air along EVERY spoke holds the chassis
        # hub_clearance minimum. The old equidistant law measured center to
        # center, so a wide hub rect ate the E/W air (~44px beside a 280
        # hub) while N/S kept ~170 — the massive-hub/short-arrows read.
        lay = solve(**_sweep_spec(n, pattern))
        hub = next(nd for nd in lay.nodes if nd.node_id == "core")  # type: ignore[attr-defined]
        hx, hy = _hub_center(lay)
        hub_clear = float(load_paradigms()["primer"].diagram.topologies["hub"].hub_clearance)
        for nd in lay.nodes:  # type: ignore[attr-defined]
            if nd.node_id == "core":
                continue
            cx, cy = nd.box.x + nd.box.w / 2, nd.box.y + nd.box.h / 2
            theta = math.degrees(math.atan2(cy - hy, cx - hx))
            dist = math.hypot(cx - hx, cy - hy)
            clear = dist - _support(hub.box.w, hub.box.h, theta) - _support(nd.box.w, nd.box.h, theta)
            assert clear >= hub_clear - 0.5, (pattern, n, nd.node_id, clear)

    @pytest.mark.parametrize(("pattern", "n"), _SWEEP)
    def test_ring_radius_carries_no_slack(self, pattern: str, n: int) -> None:
        # The anti-inflation LAW, per-axis edition: every spoke sits at its
        # clearance base — max(chassis ring floor, hub support + clearance +
        # card support along the spoke) — except where the neighbor-pair
        # chord law raised the smaller of a crowding pair; a raise never
        # exceeds one pair-need, and at least one spoke anchors the base.
        lay = solve(**_sweep_spec(n, pattern))
        hub = next(nd for nd in lay.nodes if nd.node_id == "core")  # type: ignore[attr-defined]
        hx, hy = _hub_center(lay)
        ch = load_paradigms()["primer"].diagram.topologies["hub"]
        spokes = [nd for nd in lay.nodes if nd.node_id != "core"]  # type: ignore[attr-defined]
        pair_allow = math.hypot(max(nd.box.w for nd in spokes), max(nd.box.h for nd in spokes)) + 24.0
        pair_allow += float(ENGINE["min_clearance"])
        # Anti-inflation as LOCAL MINIMALITY: a spoke sits at its clearance
        # base, or it was raised by a pair constraint that still BINDS (some
        # neighbor within one pair-need of it). No third force may inflate
        # the ring — a raise that left every pair slack would be slack.
        centers = {nd.node_id: (nd.box.x + nd.box.w / 2, nd.box.y + nd.box.h / 2) for nd in spokes}
        for nd in spokes:
            cx, cy = centers[nd.node_id]
            theta = math.degrees(math.atan2(cy - hy, cx - hx))
            dist = math.hypot(cx - hx, cy - hy)
            base = max(
                float(ch.ring_r_hub),
                _support(hub.box.w, hub.box.h, theta) + float(ch.hub_clearance) + _support(nd.box.w, nd.box.h, theta),
            )
            assert dist >= base - 1.0, (pattern, n, nd.node_id, dist, base)
            binding = any(
                math.hypot(ox - cx, oy - cy) <= pair_allow + 2.0
                for oid, (ox, oy) in centers.items()
                if oid != nd.node_id
            )
            assert dist <= base + 1.0 or binding, (pattern, n, nd.node_id, dist, base)

    @pytest.mark.parametrize(("pattern", "n"), _SWEEP)
    def test_presence_bands(self, pattern: str, n: int) -> None:
        # Density/proportion stays in band regardless of node count (the
        # round-1 presence-defect class): spoke:card ratio bounded, content
        # mass never collapses into whitespace.
        # Measured sweep envelope: ratio 0.36-2.72, mass 3.1%-12.1%. The
        # floor sits under the lawful-dense worst case (two adjacent FULL
        # cardinals force 22.5° gaps, so the ring buys separation with
        # canvas) — no-slack above is the true anti-whitespace law; this
        # band is the smoke alarm for regressions of the round-1 defect
        # (5 cards on a 994² canvas at 3.9% WITH slack).
        lay = solve(**_sweep_spec(n, pattern))
        card_w = max(nd.box.w for nd in lay.nodes if nd.node_id != "core")  # type: ignore[attr-defined]
        mean_spoke = sum(cn.length for cn in lay.connectors) / len(lay.connectors)  # type: ignore[attr-defined]
        assert 0.3 <= mean_spoke / card_w <= 3.2, (pattern, n, mean_spoke / card_w)
        mass = sum(nd.box.w * nd.box.h for nd in lay.nodes) / (lay.width * lay.height)  # type: ignore[attr-defined]
        assert mass >= 0.028, (pattern, n, mass)

    def test_verb_algebra_named_case(self) -> None:
        # The authored reference — one assertion case among the sweep, not
        # the objective: 3 out E + 2 in W → every spoke on a 45° multiple.
        lay = solve(
            topology="hub",
            hub_policy="compass",
            title="T",
            nodes=[{"id": "core", "label": "CORE", "role": "hero"}]
            + [{"id": f"o{i}", "label": f"out{i}"} for i in range(3)]
            + [{"id": f"i{i}", "label": f"in{i}"} for i in range(2)],
            edges=[{"source": "core", "target": f"o{i}", "role": "out"} for i in range(3)]
            + [{"source": f"i{i}", "target": "core", "role": "in"} for i in range(2)],
        )
        angles = sorted(round(v, 1) for v in _spoke_angles(lay).values())
        # The out trio holds the E grid run (0/±45); the in PAIR packs at
        # the measured splay about W (180 ± 27.5 — hub.pair_splay), no
        # longer the ±45 grid slots.
        assert angles == [0.0, 45.0, 152.5, 207.5, 315.0]


class TestHubNucleusLego:
    """The card-lego law (sixth review): a nucleus adjusts to its content —
    width floors at the ring member box (dominance is a step over the
    family, never a fixed 280 frame), height solves from the content rows
    over the chassis pad_y band (the verb-reads two-row 92 / the hub
    three-row 120)."""

    @staticmethod
    def _nucleus_spec(desc: str) -> dict[str, object]:
        return dict(
            topology="hub",
            hub_policy="compass",
            title="T",
            nodes=[
                {"id": "core", "label": "the artifact", "desc": desc, "role": "hero", "style": "card"},
                {"id": "a", "label": "compose", "desc": "spec in"},
                {"id": "b", "label": "transform", "desc": "patch out"},
            ],
            edges=[{"source": "a", "target": "core"}, {"source": "core", "target": "b"}],
        )

    def test_nucleus_height_tracks_content_rows(self) -> None:
        # A two-row nucleus must render SHORTER than a three-row one — the
        # archetype chassis h floored both at 120 (the phantom-row slack).
        # Three-row hubs carry an AUTHORED break (the hub specimen's
        # "payload + envelope" / "re-renderable seed"): hero descs never
        # auto-wrap — the never-clip rule widens the column instead.
        # "payload" stays under the compass hero aspect cap (1.36 — the
        # frame-engine-hub specimen ratio); a wider one-line desc now wraps
        # via the aspect law (an authored break at solve time), which would
        # legitimately equal the three-row case and mask the phantom-floor
        # regression this test guards.
        two = solve(**self._nucleus_spec("payload"))
        three = solve(**self._nucleus_spec("payload + envelope\nre-renderable seed"))
        h2 = next(nd for nd in two.nodes if nd.node_id == "core").box.h  # type: ignore[attr-defined]
        h3 = next(nd for nd in three.nodes if nd.node_id == "core").box.h  # type: ignore[attr-defined]
        assert h2 < h3, (h2, h3)
        assert 78 <= h2 <= 100, h2  # verb-reads band (92)
        assert 100 < h3 <= 134, h3  # hub band (120)

    def test_nucleus_width_floors_at_member_box(self) -> None:
        # Short content sits AT the ring member width — never below (the
        # family step), never at the half-empty 280 archetype.
        lay = solve(**self._nucleus_spec("payload + envelope"))
        core = next(nd for nd in lay.nodes if nd.node_id == "core")  # type: ignore[attr-defined]
        member = next(nd for nd in lay.nodes if nd.node_id == "a")  # type: ignore[attr-defined]
        assert core.box.w >= member.box.w - 0.5, (core.box.w, member.box.w)
        assert core.box.w <= member.box.w + 60.0, (core.box.w, member.box.w)


class TestHubStructure:
    def test_hub_paints_last(self) -> None:
        # Paint order is the emanation mask: the hub (slot 0) is the LAST node
        # painted so its card masks the inner spoke stubs.
        lay = solve(**_hub_spec(n_out=3))
        assert lay.nodes[-1].node_id == "core"  # type: ignore[attr-defined]

    def test_per_zone_cap(self) -> None:
        # Four spokes forced into one zone exceeds hub_max_per_zone (3).
        with pytest.raises(DiagramCapacityError, match="per zone"):
            solve(
                topology="hub",
                hub_policy="compass",
                title="T",
                nodes=[{"id": "core", "label": "C", "role": "hero"}]
                + [{"id": f"n{i}", "label": f"n{i}"} for i in range(4)],
                edges=[{"source": "core", "target": f"n{i}", "zone": "E"} for i in range(4)],
            )

    def test_canvas_fits_content(self) -> None:
        # R3 content-fit law: the canvas hugs the content bbox + chrome
        # bands — an unoccupied compass arc never leaves a dead quadrant.
        paradigm = load_paradigms()["primer"].diagram
        ch = paradigm.topologies["hub"]
        lay = solve(**_hub_spec_mixed())
        boxes = [n.box for n in lay.nodes]  # type: ignore[attr-defined]
        min_x = min(b.x for b in boxes)
        max_x = max(b.x + b.w for b in boxes)
        min_y = min(b.y for b in boxes)
        max_y = max(b.y + b.h for b in boxes)
        # Under the page-scale floor the content CENTERS in the canvas; the
        # anti-dead-quadrant law becomes symmetry + a margin floor, not an
        # exact margin pin.
        right_gap = lay.width - max_x  # type: ignore[attr-defined]
        assert min_x == pytest.approx(right_gap, abs=2.0)
        assert min_x >= ch.margin_x - 1.0
        # §2: content starts below the MEASURED masthead region, not a
        # chassis band constant.
        content = next(r for r in lay.regions if r.id == "content")  # type: ignore[attr-defined]
        assert min_y == pytest.approx(content.y, abs=1.0)
        # Bottom pad = footer band, plus up to the hub under-label allowance
        # when the hub is the lowest element.
        # +48 = under-label allowance (28) + the caption law's extra air (44-24)
        assert ch.footer_h - 1.0 <= lay.height - max_y <= ch.footer_h + 48.0  # type: ignore[attr-defined]


class TestLanesBands:
    def _obi(self) -> object:
        return solve(
            topology="lanes",
            title="Obi",
            nodes=[
                {"id": "a", "label": "Ingest", "category": "Source"},
                {"id": "b", "label": "Parse", "category": "Transform"},
                {"id": "c", "label": "Store", "category": "Sink"},
                {"id": "d", "label": "Validate", "category": "Transform"},
            ],
            edges=[
                {"source": "a", "target": "b"},
                {"source": "b", "target": "c"},
                {"source": "a", "target": "c", "route": "around"},
                {"source": "b", "target": "d"},
            ],
        )

    def test_bands_first_appearance_order(self) -> None:
        lay = self._obi()
        headers = [b.header.text for b in lay.lane_bands]  # type: ignore[attr-defined]
        assert headers == ["SOURCE", "TRANSFORM", "SINK"]  # first-appearance, uppercased

    def test_band_count_badges(self) -> None:
        lay = self._obi()
        counts = {b.header.text: b.count.text for b in lay.lane_bands}  # type: ignore[attr-defined]
        assert counts == {"SOURCE": "1", "TRANSFORM": "2", "SINK": "1"}

    def test_category_shares_accent(self) -> None:
        # Same category → same flow-palette slot (band, its nodes' dots, and
        # legend share it): band accents are distinct per category, from 0.
        lay = self._obi()
        accents = [b.accent_index for b in lay.lane_bands]  # type: ignore[attr-defined]
        assert accents == [0, 1, 2]

    def test_nodes_within_their_band(self) -> None:
        lay = self._obi()
        bands = {b.header.text: b.box for b in lay.lane_bands}  # type: ignore[attr-defined]
        # Every card sits inside some band's x-extent.
        for n in lay.nodes:  # type: ignore[attr-defined]
            inside = any(box.x - 0.5 <= n.box.x and n.box.x + n.box.w <= box.x + box.w + 0.5 for box in bands.values())
            assert inside, (n.node_id, n.box.x)

    def test_lane_width_clamped(self) -> None:
        # Band widths clamp to [lane_w_min, lane_w_max].
        paradigm = load_paradigms()["primer"].diagram
        ch = paradigm.topologies["lanes"]
        lay = self._obi()
        for b in lay.lane_bands:  # type: ignore[attr-defined]
            assert ch.lane_w_min - 0.5 <= b.box.w <= ch.lane_w_max + 0.5


class TestLanesRouting:
    def test_long_haul_clears_bands(self) -> None:
        # The route:'around' edge runs on a perimeter channel BELOW every band.
        lay = solve(
            topology="lanes",
            title="T",
            nodes=[
                {"id": "a", "label": "A", "category": "S"},
                {"id": "b", "label": "B", "category": "T"},
                {"id": "c", "label": "C", "category": "U"},
                {"id": "d", "label": "D", "category": "T"},
            ],
            edges=[
                {"source": "a", "target": "b"},
                {"source": "b", "target": "c"},
                {"source": "a", "target": "c", "route": "around"},
                {"source": "b", "target": "d"},
            ],
        )
        band_bottom = max(b.box.y + b.box.h for b in lay.lane_bands)  # type: ignore[attr-defined]
        long_haul = lay.connectors[2]  # type: ignore[attr-defined]
        ys = [float(p.split(",")[1]) for p in long_haul.path_d.replace("M", "").replace("L", "").split()]
        assert max(ys) > band_bottom  # the channel run is below all bands

    def test_adjacent_gutter_bus(self) -> None:
        # Adjacent-band edges (Δlane == 1) route across the gutter, not the
        # perimeter — their path stays within the band vertical span.
        lay = solve(
            topology="lanes",
            title="T",
            nodes=[
                {"id": "a", "label": "A", "category": "S"},
                {"id": "b", "label": "B", "category": "T"},
                {"id": "c", "label": "C", "category": "U"},
                {"id": "d", "label": "D", "category": "T"},
            ],
            edges=[{"source": "a", "target": "b"}, {"source": "b", "target": "c"}, {"source": "b", "target": "d"}],
        )
        band_bottom = max(b.box.y + b.box.h for b in lay.lane_bands)  # type: ignore[attr-defined]
        for c in lay.connectors:  # type: ignore[attr-defined]
            ys = [float(p.split(",")[1]) for p in c.path_d.replace("M", "").replace("L", "").split()]
            assert max(ys) <= band_bottom + 0.5  # no adjacent edge dips to a channel

    def test_bus_non_adjacent_rejected(self) -> None:
        with pytest.raises(DiagramInputError, match="adjacent-only"):
            solve(
                topology="lanes",
                title="T",
                nodes=[
                    {"id": "a", "label": "A", "category": "S"},
                    {"id": "b", "label": "B", "category": "T"},
                    {"id": "c", "label": "C", "category": "U"},
                    {"id": "d", "label": "D", "category": "S"},
                ],
                edges=[
                    {"source": "a", "target": "b"},
                    {"source": "b", "target": "c"},
                    {"source": "d", "target": "b"},
                    {"source": "a", "target": "c", "route": "bus"},
                ],
            )

    def test_long_haul_cap(self) -> None:
        # More than lanes_max_long_haul (3) perimeter edges raises.
        nodes = [
            {"id": "a", "label": "A", "category": "S"},
            {"id": "b", "label": "B", "category": "T"},
            {"id": "c", "label": "C", "category": "U"},
            {"id": "e", "label": "E", "category": "S"},
            {"id": "f", "label": "F", "category": "T"},
            {"id": "g", "label": "G", "category": "U"},
        ]
        edges = [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
            {"source": "a", "target": "c", "route": "around"},
            {"source": "e", "target": "g", "route": "around"},
            {"source": "f", "target": "a", "route": "around"},
            {"source": "g", "target": "a", "route": "around"},
        ]
        with pytest.raises(DiagramCapacityError, match="long-haul"):
            solve(topology="lanes", title="T", nodes=nodes, edges=edges)


def _obi_lanes() -> object:
    return solve(
        topology="lanes",
        title="Obi",
        nodes=[
            {"id": "a", "label": "Ingest", "category": "Source"},
            {"id": "b", "label": "Parse", "category": "Transform"},
            {"id": "c", "label": "Store", "category": "Sink"},
            {"id": "d", "label": "Validate", "category": "Transform"},
        ],
        edges=[{"source": "a", "target": "b"}, {"source": "b", "target": "c"}, {"source": "b", "target": "d"}],
    )


class TestLanesAutoLegend:
    def test_auto_legend_one_entry_per_category(self) -> None:
        # The category legend is morphology-SHAPE, never hue
        # (obi-engine) — no caller legend and no node declares
        # ``morphology``, so it falls back to one shape per band, first-
        # appearance order (Source, Transform, Sink), cycling the idiom
        # registry's [disc, ring, diamond, square].
        lay = _obi_lanes()
        legends = [a for a in lay.annotations if a.kind == "legend"]  # type: ignore[attr-defined]
        assert len(legends) == 1
        entries = [(e.text.text, e.swatch_shape, e.accent_index) for e in legends[0].entries]
        assert entries == [("Source", "disc", -1), ("Transform", "ring", -1), ("Sink", "diamond", -1)]

    def test_caller_legend_suppresses_auto(self) -> None:
        # A caller-declared legend wins: the auto one is not emitted.
        lay = solve(
            topology="lanes",
            title="T",
            nodes=[
                {"id": "a", "label": "A", "category": "S"},
                {"id": "b", "label": "B", "category": "T"},
                {"id": "c", "label": "C", "category": "U"},
                {"id": "d", "label": "D", "category": "T"},
            ],
            edges=[{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
            annotations=[{"text": "MY LEGEND", "kind": "legend", "region": "canvas"}],
        )
        legends = [a for a in lay.annotations if a.kind == "legend"]  # type: ignore[attr-defined]
        assert len(legends) == 1  # only the caller's, auto suppressed
        assert [e.text.text for e in legends[0].entries] == ["MY LEGEND"]

    def test_category_shares_accent_via_assign_accents(self) -> None:
        # The consolidated solver.py:assign_accents category-groups: two nodes
        # in the same category share a slot (b and d are both Transform).
        lay = _obi_lanes()
        by_id = {n.node_id: n.accent_index for n in lay.nodes}  # type: ignore[attr-defined]
        assert by_id["b"] == by_id["d"]
        assert by_id["a"] != by_id["b"]  # distinct categories, distinct slots


class TestHubZoneRegions:
    def test_zone_callout_anchors_in_sector(self) -> None:
        # A region:zone:E callout is placed (the zone region is registered);
        # unknown region refs would raise, so placement proves registration.
        lay = solve(
            topology="hub",
            hub_policy="compass",
            title="T",
            nodes=[
                {"id": "core", "label": "CORE", "role": "hero"},
                {"id": "x", "label": "x"},
                {"id": "y", "label": "y"},
            ],
            edges=[
                {"source": "core", "target": "x", "role": "out"},
                {"source": "core", "target": "y", "role": "out"},
            ],
            annotations=[{"text": "outputs", "kind": "callout", "region": "zone:E"}],
        )
        callouts = [a for a in lay.annotations if a.kind == "callout"]  # type: ignore[attr-defined]
        assert len(callouts) == 1
        assert any(t.text == "outputs" for a in callouts for t in a.lines)

    def test_unknown_region_ref_raises(self) -> None:
        # A callout to an unregistered region names the registered set.
        with pytest.raises(DiagramInputError, match="region"):
            solve(
                topology="hub",
                hub_policy="compass",
                title="T",
                nodes=[
                    {"id": "core", "label": "CORE", "role": "hero"},
                    {"id": "x", "label": "x"},
                    {"id": "y", "label": "y"},
                ],
                edges=[
                    {"source": "core", "target": "x", "role": "out"},
                    {"source": "core", "target": "y", "role": "out"},
                ],
                annotations=[{"text": "nope", "kind": "callout", "region": "zone:NOPE"}],
            )


class TestLanesAccentConsolidation:
    """The lanes accent grouping moved from a lanes.py local pre-pass into
    solver.py:assign_accents (same category→slot logic). These pins prove the
    move is OUTPUT-IDENTICAL to the deleted pre-pass — accents match the exact
    first-appearance formula, and the lanes layout is deterministic (the
    consolidation added no order-dependence). Full-SVG bytes carry known
    provenance volatility (timestamps → content-address digest) orthogonal to
    accents, so the proof lives at the accent + layout level."""

    def test_consolidated_accents_match_category_first_appearance(self) -> None:
        # assign_accents reproduces the deleted local pre-pass EXACTLY: category
        # → slot by first-appearance order, k % palette_len, node.accent kept.
        from hyperweave.compose.bundled_specs import resolve_bundled_spec
        from hyperweave.compose.diagram.solver import assign_accents

        spec = resolve_auto_roles(DiagramSpec.model_validate(resolve_bundled_spec("diagram", "obi-engine").value))
        order: list[str] = []
        for n in spec.nodes:
            if n.category not in order:
                order.append(n.category)
        slot = {c: (k % 5) for k, c in enumerate(order)}
        expected = tuple(n.accent if n.accent is not None else slot[n.category] for n in spec.nodes)
        assert assign_accents(spec, 5) == expected

    def test_lanes_layout_deterministic(self) -> None:
        # The lanes layout (accents, bands, geometry) is byte-stable — the
        # consolidation added no order-dependence. Layout records carry no
        # timestamps, so this is exact (unlike full-SVG bytes).
        from hyperweave.compose.bundled_specs import resolve_bundled_spec

        kw = resolve_bundled_spec("diagram", "obi-engine").value
        assert solve(**kw) == solve(**kw)

    def test_node_accent_override_survives_consolidation(self) -> None:
        # An explicit node.accent still wins over the category slot.
        from hyperweave.compose.diagram.solver import assign_accents

        spec = resolve_auto_roles(
            DiagramSpec.model_validate(
                dict(
                    topology="lanes",
                    nodes=[
                        {"id": "a", "label": "A", "category": "S", "accent": 4},
                        {"id": "b", "label": "B", "category": "T"},
                        {"id": "c", "label": "C", "category": "U"},
                        {"id": "d", "label": "D", "category": "S"},
                    ],
                    edges=[{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
                )
            )
        )
        accents = assign_accents(spec, 5)
        assert accents[0] == 4  # 'a' takes its explicit override
        assert accents[3] == 0  # 'd' (also category S, no override) takes the S category slot (first category → 0)


class TestAlignedGroupContentEdge:
    @staticmethod
    def _ink_pads(lay: object, cfg: object) -> list[tuple[str, float, float]]:
        from hyperweave.compose.diagram.chrome import voice_for
        from hyperweave.compose.matrix.cells import measure_voice

        out: list[tuple[str, float, float]] = []
        for n in lay.nodes:  # type: ignore[attr-defined]
            if n.shape != "rect" or n.role == "hero":
                continue
            il = min(
                [n.label.x]
                + [d.x for d in n.desc_lines]
                + ([n.glyph.cx - n.glyph.size / 2] if n.glyph is not None else [])
            )
            ir = max(
                [n.label.x + measure_voice(n.label.text, voice_for(cfg, n.label.cls))]
                + [d.x + measure_voice(d.text, voice_for(cfg, d.cls)) for d in n.desc_lines]
            )
            out.append((n.node_id, il - n.box.x, n.box.x + n.box.w - ir))
        return out

    def test_aligned_group_members_anchor_their_content(self) -> None:
        # Content-anchor law (supersedes the Item-2 per-card centering): an
        # aligned group shares the card WIDTH, and every plain member seats
        # its content-left at the chassis ``glyph_inset_x`` — a chassis fact,
        # so the column is uniform by construction and slack pools right (the
        # hand corpus: providers/serving/gateway columns all sit at one x).
        # Per-card centering made the column a function of each member's own
        # slack: near-identical cards aligned differently.
        cfg = load_paradigms()["primer"].diagram
        lay = solve(
            topology="convergence",
            title="T",
            nodes=[
                {"id": "a", "label": "alpha", "desc": "one very wide descriptive line of text"},
                {"id": "b", "label": "b", "desc": "tiny"},
                {"id": "c", "label": "gamma-service", "desc": "mid width row"},
                {"id": "core", "label": "CORE", "role": "hero"},
            ],
            edges=[
                {"source": "a", "target": "core"},
                {"source": "b", "target": "core"},
                {"source": "c", "target": "core"},
            ],
        )
        pads = self._ink_pads(lay, cfg)
        insets = {node_id: lp for node_id, lp, _rp in pads}
        assert all(abs(lp - 22.0) <= 0.6 for lp in insets.values()), insets
        # Slack pools RIGHT: the short member's right pad exceeds its left.
        rp_by_id = {node_id: rp for node_id, _lp, rp in pads}
        assert rp_by_id["b"] > insets["b"] + 10, rp_by_id

    def test_hub_ring_members_anchor_their_content(self) -> None:
        # Ring cards seat content at the chassis anchor (content-anchor law;
        # supersedes the Item-2 centering) — one shared column by
        # construction, never a per-card slack split.
        cfg = load_paradigms()["primer"].diagram
        nodes = [{"id": "core", "label": "CORE", "role": "hero"}] + [
            {"id": f"o{i}", "label": f"out{i}", "desc": d}
            for i, d in enumerate(("payload out", "spec check", "patch apply"))
        ]
        edges = [{"source": "core", "target": f"o{i}", "role": "out"} for i in range(3)]
        lay = solve(topology="hub", title="T", hub_policy="compass", nodes=nodes, edges=edges)
        for node_id, lp, _rp in self._ink_pads(lay, cfg):
            assert abs(lp - 22.0) <= 0.6, (node_id, lp)


class TestLanesChromeHomes:
    def test_auto_legend_homes_in_masthead_right(self) -> None:
        # legend_home knob, masthead default: the auto category legend
        # coalesces top-right in the HEADER band, inline with the title row
        # (the obi-engine placement) — never floating over the graph mid-canvas.
        lay = _obi_lanes()
        legends = [a for a in lay.annotations if a.kind == "legend"]  # type: ignore[attr-defined]
        assert len(legends) == 1
        box = legends[0].box
        assert box is not None
        # Header legends no longer reserve a masthead REGION (they share the
        # zone-header corner instead of buying a band above it) — the law is
        # the placement itself: above every lane band, never over the graph.
        band_top = min(b.box.y for b in lay.lane_bands)  # type: ignore[attr-defined]
        assert box.y + box.h <= band_top, (box, band_top)  # never over the graph
        # Right-aligned: the row's right edge hugs the canvas's right side.
        assert box.x + box.w > lay.width * 0.7, (box, lay.width)  # type: ignore[attr-defined]

    def test_typographic_lane_headers_derive_from_the_rule(self) -> None:
        # D1/D2 typographic ground (the default): no band panel; the header
        # baseline sits lane_rule_dy above the hairline rule, which sits
        # lane_rule_to_row above the first card row; the rule spans EXACTLY
        # the card column; header and count share the baseline.
        paradigm = load_paradigms()["primer"].diagram
        ch = paradigm.topologies["lanes"]
        lay = _obi_lanes()
        for band in lay.lane_bands:  # type: ignore[attr-defined]
            assert band.ground == "typographic"
            assert band.rule is not None
            # Region-relative (§2): the band's own top anchors the strip.
            rows_top = band.box.y + ch.lane_header_h
            assert band.rule.y1 == pytest.approx(rows_top - ch.lane_rule_to_row)
            assert band.header.y == pytest.approx(band.rule.y1 - ch.lane_rule_dy)
            assert band.count.y == pytest.approx(band.header.y)  # shared baseline
            assert band.rule.x1 == pytest.approx(band.box.x)  # spans exactly
            assert band.rule.x2 == pytest.approx(band.box.x + band.box.w)  # the card column

    def test_declared_lanes_order_and_empty_lane(self) -> None:
        # The spec-level 'lanes' knob: declared order wins over first
        # appearance, and a declared-but-unpopulated lane renders as an
        # EMPTY band (width floor, count 0, no rows).
        lay = solve(
            topology="lanes",
            title="T",
            lanes=["Sink", "Source", "Hold", "Transform"],
            nodes=[
                {"id": "a", "label": "A", "category": "Source"},
                {"id": "b", "label": "B", "category": "Transform"},
                {"id": "c", "label": "C", "category": "Sink"},
                {"id": "d", "label": "D", "category": "Source"},
            ],
            edges=[{"source": "a", "target": "b"}],
        )
        headers = [b.header.text for b in lay.lane_bands]  # type: ignore[attr-defined]
        assert headers == ["SINK", "SOURCE", "HOLD", "TRANSFORM"]  # declared, not appearance
        counts = {b.header.text: b.count.text for b in lay.lane_bands}  # type: ignore[attr-defined]
        assert counts["HOLD"] == "0"  # the empty lane

    def test_lanes_wires_solid_bypass_dashed(self) -> None:
        # D5 (obi-engine): lanes IS in the wire-solid set — ordinary rails
        # read solid + arrowed, same as the specimen's gutter bus. The bypass
        # long-haul (route=around) carries its own semantic, meaning-bearing
        # dash and stays static too (dress is independent of the D5 default).
        lay = solve(
            topology="lanes",
            title="T",
            nodes=[
                {"id": "a", "label": "A", "category": "S"},
                {"id": "b", "label": "B", "category": "T"},
                {"id": "c", "label": "C", "category": "U"},
                {"id": "d", "label": "D", "category": "S"},
            ],
            edges=[
                {"source": "a", "target": "b"},
                {"source": "d", "target": "b"},
                {"source": "b", "target": "c"},
                {"source": "a", "target": "c", "route": "around"},
            ],
        )
        conns = list(lay.connectors)  # type: ignore[attr-defined]
        # Every edge resolves static now — ordinary rails solid, the bypass
        # dashed via its own semantic texture.
        static = [c.index for c in conns if c.track == "static"]
        assert static == [0, 1, 2, 3], static
        assert conns[3].static_dash == "2 7"
        assert all(c.static_dash == "" for c in conns[:3])
        assert not any(c.track == "dash-march" for c in conns)
        # Ordinary rails draw a terminal arrow; the D6 fan-in rule (lanes.py)
        # keeps exactly one arrow per shared entry point (edge 1 merges into
        # "b" arrowless behind edge 0's). The bypass lands on its own
        # rail-join stub past the entry gutter (obi-engine: 608 vs mouth
        # 669) — a distinct landing, so it keeps its terminal.
        assert [bool(c.marker_d) for c in conns] == [True, False, True, True]


class TestAxialHeroProminence:
    """Ink-bound nucleus law: the axial nucleus is content-bounded and bilaterally centered.
    The golden nucleus (primer_diagram_language.html verb-algebra) is
    content-fit at 232 — prominence keeps its height meaning and the family
    floor keeps presence, but the area formula never widens the card into a
    dead band, and slack always splits both sides of the block."""

    @staticmethod
    def _preset_layout(preset: str) -> object:
        from hyperweave.compose.bundled_specs import resolve_bundled_spec

        return solve(**dict(resolve_bundled_spec("diagram", preset).value))

    def test_verb_reads_hero_snug_and_identical_to_hub(self) -> None:
        # Snug-width ruling 2026-07-14: the pp-radial 280 hand rect is a
        # CEILING — the crown solves to its own ink (194), left/right slack
        # within ~10px of each other by fit, not centering. And ruling 4:
        # the SAME crown spec (label 'the artifact', desc 'hw:payload ·
        # hwz/1', the family diamond) solves the SAME width in every
        # topology — verb-reads' and hub's crowns are the byte-same box
        # width by construction now.
        lay = self._preset_layout("verb-reads")
        hero = next(n for n in lay.nodes if n.role == "hero")  # type: ignore[attr-defined]
        assert hero.box.w == 194.0, hero.box.w
        assert hero.box.h >= 92.0, hero.box.h  # cited crown height floor holds

    def test_hero_text_column_anchors_at_chassis_inset(self) -> None:
        # Content-anchor law (supersedes the bilateral hero centering): the
        # crown's text column is a CHASSIS fact — ``glyph_inset_x`` plus the
        # mark slot plus ``glyph_label_gap`` — never re-derived from the
        # crown's own slack. The hand crowns anchor left and read
        # ragged-right (pp-radial's +45 column with its wide right slack; the
        # convergence-flow crown's +56).
        from hyperweave.compose.bundled_specs import resolve_bundled_spec
        from hyperweave.compose.diagram.input import coerce_diagram_input as _cdi
        from hyperweave.compose.diagram.sizing import GLYPH_MARK_W
        from hyperweave.compose.diagram.solver import apply_spec_chassis as _asc
        from hyperweave.core.diagram import layout_slug as _slug
        from hyperweave.core.models import ComposeSpec as _CS
        from hyperweave.core.paradigm import DiagramTopologyChassis as _DTC

        paradigm = load_paradigms()["primer"].diagram
        for preset in ("verb-reads", "axial", "hub"):
            spec_d = dict(resolve_bundled_spec("diagram", preset).value)
            cs = _CS(type="diagram", genome_id="primer", variant="porcelain", ground="bare", diagram=spec_d)
            nspec = _cdi(cs.connector_data, cs).spec
            ch = _asc(paradigm.topologies.get(_slug(nspec)) or _DTC(), nspec.chassis)
            lay = solve(**spec_d)
            hero = next(n for n in lay.nodes if n.role == "hero")  # type: ignore[attr-defined]
            if hero.shape != "rect":
                continue
            lead = ((ch.hero.glyph_w or GLYPH_MARK_W) + ch.hero.glyph_label_gap) if hero.glyph is not None else 0.0
            expected = ch.hero.glyph_inset_x + lead
            left = hero.label.x - hero.box.x
            assert abs(left - expected) <= 0.6, f"{preset}: text column at +{left:.1f}, chassis law says +{expected:g}"

    def test_hero_content_never_clips(self) -> None:
        # A deliberately long two-line desc: the floor still protects — the
        # box grows past the family width rather than clipping ink.
        spec = dict(
            topology="hub",
            hub_policy="axial",
            title="T",
            nodes=[
                {
                    "id": "core",
                    "label": "the artifact",
                    "desc": "a deliberately very long subtitle line\nand a second long wrapped line here",
                    "role": "hero",
                },
                {"id": "n", "label": "transform", "desc": "patch out"},
                {"id": "s", "label": "read", "desc": "extract"},
                {"id": "w", "label": "the spec", "desc": "the recipe"},
                {"id": "e", "label": "documents", "desc": "many into one"},
            ],
            edges=[
                {"source": "w", "target": "core", "role": "in"},
                {"source": "core", "target": "n"},
                {"source": "core", "target": "s", "role": "read"},
                {"source": "core", "target": "e"},
            ],
        )
        lay = solve(**spec)
        hero = next(n for n in lay.nodes if n.role == "hero")  # type: ignore[attr-defined]
        assert hero.box.w > 240.0, hero.box.w  # grew past the snap-breath band for real ink
        assert len(hero.desc_lines) == 2  # both authored lines render

    def test_satellite_axis_width_locked(self) -> None:
        # Regression guard for the audited-correct behavior: stacked same-axis
        # satellites share one x and one width (the golden documents/surfaces
        # pair), while different axes keep their own solved widths.
        lay = self._preset_layout("axial")
        docs = next(n for n in lay.nodes if n.node_id == "documents")  # type: ignore[attr-defined]
        surf = next(n for n in lay.nodes if n.node_id == "surfaces")  # type: ignore[attr-defined]
        assert math.isclose(docs.box.x, surf.box.x, abs_tol=0.01)
        assert math.isclose(docs.box.w, surf.box.w, abs_tol=0.01)


class TestLanesDescContainment:
    """Lanes containment law: every lanes desc is contained when measured with the RENDER's
    own effective voice (lanes overrides desc to 10px untracked,
    cited to the obi-engine specimen). The gallery sweep's text-in-card law had graded
    lanes with the generic kit voice — phantom 6-20px 'bleeds' — and excluded
    the topology entirely; the sweep now parses each render's own CSS, the
    exclusion is gone, and this pins the engine side of the law."""

    def test_obi_engine_descs_contained(self) -> None:
        from hyperweave.compose.bundled_specs import resolve_bundled_spec
        from hyperweave.compose.diagram.input import resolve_auto_roles as _rar
        from hyperweave.compose.diagram.sizing import measure_voice
        from hyperweave.compose.diagram.solver import effective_render_cfg
        from hyperweave.core.diagram import DiagramSpec as _DS

        spec_d = dict(resolve_bundled_spec("diagram", "obi-engine").value)
        lay = solve(**spec_d)
        cfg = effective_render_cfg(_rar(_DS.model_validate(spec_d)), load_paradigms()["primer"].diagram)
        checked = 0
        for n in lay.nodes:  # type: ignore[attr-defined]
            for d in n.desc_lines:
                right = d.x + measure_voice(d.text, cfg.desc_voice)
                assert right <= n.box.x + n.box.w + 0.5, (
                    f"{n.node_id}: desc {d.text!r} ink ends {right:.1f} past card right {n.box.x + n.box.w:.1f}"
                )
                checked += 1
        assert checked >= 10  # obi-engine is desc-dense; an empty pass is a parse bug

    def test_long_desc_wraps_within_lane_cap(self) -> None:
        # A desc wider than lane_w_max wraps to the chassis w_max ceiling
        # (sizing solves width to the ceiling and height to the wrapped desc)
        # instead of bleeding past the band clamp.
        spec = dict(
            topology="lanes",
            title="T",
            nodes=[
                {"id": "a", "label": "intake", "desc": "requests arrive", "category": "ingest"},
                {
                    "id": "b",
                    "label": "transform",
                    "desc": "a deliberately very long description that cannot fit one lane line",
                    "category": "process",
                },
                {"id": "c", "label": "serve", "desc": "responses leave", "category": "serve"},
                {"id": "d", "label": "archive", "desc": "history kept", "category": "serve"},
            ],
            edges=[
                {"source": "a", "target": "b"},
                {"source": "b", "target": "c"},
                {"source": "c", "target": "d"},
            ],
        )
        lay = solve(**spec)
        b = next(n for n in lay.nodes if n.node_id == "b")  # type: ignore[attr-defined]
        assert b.box.w <= 244.0 + 0.5, f"card {b.box.w:.1f} exceeded the lane cap"
        assert len(b.desc_lines) >= 2, "an over-cap desc must wrap, not bleed"


def test_hub_hero_text_stays_inside_the_padded_interior() -> None:
    """Layer pin (the board graded green through this): the aspect-clamped
    hub hero once solved its box for a TWO-line desc, then placement re-wrapped
    the original single line into it — text hugged the left pad and ran 31px
    past the right one. Solve and place must share one text decision: every
    hero run stays inside the padded interior, both sides."""
    from hyperweave.compose.diagram.sizing import voice_for
    from hyperweave.compose.matrix.cells import measure_voice

    spec = {
        "topology": "hub",
        "hub_policy": "compass",
        "title": "The breaker table",
        "node_style": "card+glyph",
        "nodes": [
            {"id": "table", "label": "breakers", "desc": "per-domain state", "role": "hero", "kind": "shield-check"},
            {"id": "core", "label": "core", "kind": "server", "anchor": "N"},
            {"id": "search", "label": "search", "kind": "search", "anchor": "E"},
            {"id": "graphql", "label": "graphql", "kind": "boxes", "anchor": "W"},
        ],
        "edges": [
            {"source": "core", "target": "table"},
            {"source": "search", "target": "table"},
            {"source": "graphql", "target": "table"},
        ],
    }
    lay = solve(**spec)
    from hyperweave.config.loader import load_paradigms

    cfg = load_paradigms()["primer"].diagram
    hero = next(n for n in lay.nodes if n.role == "hero")
    pad = cfg.topologies["hub"].hero.pad_x or 32.0
    for run in (hero.label, *hero.desc_lines):
        if run is None or not run.text:
            continue
        ink = measure_voice(run.text, voice_for(cfg, run.cls))
        assert run.x >= hero.box.x + pad - 0.5, (run.text, run.x)
        assert run.x + ink <= hero.box.x + hero.box.w - pad + 0.5, (run.text, run.x + ink, hero.box.w)
