"""Lane-alignment, row-order pinning, and plateau laws (the dag figure grammar).

Lane law: a rank does not center independently around the canvas mid — it
reads the rows already placed one rank left. A single-source node snaps to
its source's row; a multi-source node centers on the midpoint of its
sources' rows unless one inbound is chip-labeled (the chip is a vote — the
node snaps to the labeled source's row, first label by declaration order);
a gather node always takes the midpoint (its trunk chip is furniture on the
knot, never a vote); a source designated by more than one member snaps
nobody (a fan distributes around its mouth). The service-dependencies
billing transform is the enrolling specimen (pp-service-deps-billing.svg:
stores ride their service lanes, three straight rails); gateway-balanced is
the no-op anchor (its funnel midpoint and lane-member sink reproduce
unchanged).

Pin law: ``layout.rank_orders`` carries an authored vertical order — the
solver honors it in place of the barycenter sweep, survivors keep their
relative order, and unpinned insertions append at their rank's extent.

Plateau law: a chip edge that must bend rides bow, flat, bow, the flat run at
least the chip's own run, the rail in the gap band adjacent to the source
row toward the target (the writes chip seats below the cache row); the chip
parts the flat stroke at its midpoint. Unlabeled bends keep the pure S.
"""

from __future__ import annotations

import itertools
import re
from typing import Any

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import coerce_diagram_input
from hyperweave.config.loader import load_diagram_config, load_glyphs, load_paradigms
from hyperweave.core.models import ComposeSpec
from hyperweave.core.paradigm import ParadigmDiagramConfig

ENGINE = load_diagram_config()
_pspec = load_paradigms()["primer"]
PARADIGM: ParadigmDiagramConfig = _pspec.diagram if _pspec is not None else ParadigmDiagramConfig()
GLYPHS = load_glyphs()


def _layout(spec_dict: dict[str, Any]) -> Any:
    cs = ComposeSpec(
        type="diagram", genome_id="primer", variant="porcelain", ground="bare", palette="adaptive", diagram=spec_dict
    )
    spec = coerce_diagram_input(cs.connector_data, cs).spec
    return compute_diagram_layout(spec, paradigm=PARADIGM, engine=ENGINE, palette_len=6, glyph_registry=GLYPHS)


def _rows(lay: Any) -> dict[str, float]:
    return {p.node_id: p.box.y + p.box.h / 2 for p in lay.nodes}


def _boxes(lay: Any) -> dict[str, Any]:
    return {p.node_id: p.box for p in lay.nodes}


def _fan_spec(services: int, stores: int) -> dict[str, Any]:
    """web → gateway → N services → M stores, store i grounded on service i."""
    nodes: list[dict[str, Any]] = [
        {"id": "web", "label": "web"},
        {"id": "gw", "label": "gateway", "role": "hero"},
    ]
    edges: list[dict[str, Any]] = [{"source": "web", "target": "gw"}]
    for i in range(services):
        nodes.append({"id": f"svc{i}", "label": f"svc {i}"})
        edges.append({"source": "gw", "target": f"svc{i}"})
    for i in range(stores):
        nodes.append({"id": f"db{i}", "label": f"db {i}"})
        edges.append({"source": f"svc{i}", "target": f"db{i}"})
    return {"topology": "dag", "title": "fan", "nodes": nodes, "edges": edges}


def test_single_source_stores_ride_their_service_lanes() -> None:
    """Every 1:1-grounded store shares its service's row exactly — the
    straight rails the billing specimen enrolls — across fan widths and
    store counts, including the unbalanced ranks that used to half-pitch."""
    for services in (2, 3, 4):
        for stores in range(1, services + 1):
            rows = _rows(_layout(_fan_spec(services, stores)))
            for i in range(stores):
                assert abs(rows[f"db{i}"] - rows[f"svc{i}"]) < 0.5, (
                    f"{services}v{stores}: store {i} off its lane: {rows[f'db{i}']} vs {rows[f'svc{i}']}"
                )


def test_grid_never_overlaps_after_snapping() -> None:
    """No two cards share vertical space in a column — the snap chain's
    min-pitch guarantee — on every generated shape."""
    for services in (2, 3, 4):
        for stores in range(1, services + 1):
            boxes = _boxes(_layout(_fan_spec(services, stores)))
            cols: dict[float, list[Any]] = {}
            for box in boxes.values():
                cols.setdefault(round(box.x, 1), []).append(box)
            for col in cols.values():
                col.sort(key=lambda b: b.y)
                for a, b in itertools.pairwise(col):
                    assert a.y + a.h <= b.y + 0.01, f"overlap at x={a.x}: {a} vs {b}"


def test_shared_designation_snaps_nobody() -> None:
    """Two stores grounded on ONE service both designate it — a fan, so
    neither steals the row: they distribute, keep declaration order top to
    bottom, and hold the rank pitch apart."""
    spec = _fan_spec(2, 0)
    spec["nodes"] += [{"id": "dbA", "label": "db A"}, {"id": "dbB", "label": "db B"}]
    spec["edges"] += [{"source": "svc0", "target": "dbA"}, {"source": "svc0", "target": "dbB"}]
    rows = _rows(_layout(spec))
    assert rows["dbA"] < rows["dbB"], "declaration order inverted"
    assert abs(rows["dbA"] - rows["svc0"]) > 1.0 or abs(rows["dbB"] - rows["svc0"]) > 1.0
    assert rows["dbB"] - rows["dbA"] > 60.0, "conflict pair collapsed below pitch"


def test_gather_funnel_centers_even_with_a_labeled_spoke() -> None:
    """A gather funnel takes the midpoint of its sources' rows even when one
    converging edge carries a chip — the trunk chip is furniture, not a
    vote (the kv-cache funnel held when its label was the tiebreak's only
    candidate)."""
    spec = _fan_spec(3, 0)
    spec["nodes"].append({"id": "cache", "label": "cache", "gather": True})
    spec["edges"] += [
        {"source": "svc0", "target": "cache", "label": "cache", "label_style": "chip"},
        {"source": "svc1", "target": "cache"},
        {"source": "svc2", "target": "cache"},
    ]
    rows = _rows(_layout(spec))
    midpoint = (rows["svc0"] + rows["svc2"]) / 2
    assert abs(rows["cache"] - midpoint) < 0.5, f"funnel apex off midpoint: {rows['cache']} vs {midpoint}"
    assert abs(rows["cache"] - rows["svc0"]) > 1.0, "funnel snapped to its labeled spoke"


def test_labeled_edge_votes_on_a_plain_multi_source_node() -> None:
    """A NON-gather multi-source node with one chip-labeled inbound snaps to
    the labeled source's row — the chip-is-a-vote branch, distinct from the
    gather's chip-is-furniture branch."""
    spec = _fan_spec(2, 0)
    spec["nodes"].append({"id": "store", "label": "store"})
    spec["edges"] += [
        {"source": "svc0", "target": "store"},
        {"source": "svc1", "target": "store", "label": "writes", "label_style": "chip"},
    ]
    rows = _rows(_layout(spec))
    assert abs(rows["store"] - rows["svc1"]) < 0.5, f"vote lost: {rows['store']} vs svc1 {rows['svc1']}"


def test_pinned_orders_replace_the_barycenter() -> None:
    """layout.rank_orders is honored verbatim: the authored vertical order
    renders even where the barycenter would re-shuffle, and a node absent
    from the pins appends at its rank's extent."""
    spec = _fan_spec(3, 3)
    spec["layout"] = {"rank_orders": [["web"], ["gw"], ["svc2", "svc0"], ["db2", "db0", "db1"]]}
    rows = _rows(_layout(spec))
    assert rows["svc2"] < rows["svc0"] < rows["svc1"], "pinned survivors + extent append violated"
    assert rows["db2"] < rows["db0"] < rows["db1"], "pinned store order violated"


_PLATEAU_RUN = re.compile(r"C [-0-9. ,]+ ([-0-9.]+),([-0-9.]+) L ([-0-9.]+),\2 C")


def test_plateau_carries_the_chip_on_a_flat_run() -> None:
    """A chip edge that must bend EVEN AFTER alignment (its target's row is
    claimed by an earlier labeled vote — the billing shape: reads wins the
    store, writes reaches up from the fan's extent) rides bow, flat, bow: a
    flat leg at the rail, the rail a half-pitch off the SOURCE row toward
    the target (the below-the-cache-row seat), the chip box centered on the
    run."""
    spec = _fan_spec(4, 1)
    spec["edges"][-1] = {"source": "svc0", "target": "db0", "label": "reads", "label_style": "chip"}
    spec["edges"].append({"source": "svc3", "target": "db0", "label": "writes", "label_style": "chip"})
    lay = _layout(spec)
    rows = _rows(lay)
    assert abs(rows["db0"] - rows["svc0"]) < 0.5, "first labeled vote lost the store"
    assert abs(rows["db0"] - rows["svc3"]) > 60.0, "spec no longer bends the writes edge"
    chips = [a for a in lay.annotations if a.kind == "edge-chip" and a.lines and a.lines[0].text == "writes"]
    assert chips, "writes chip missing"
    chip = chips[0]
    ccx, ccy = chip.box.x + chip.box.w / 2, chip.box.y + chip.box.h / 2
    flat = None
    for c in lay.connectors:
        m = _PLATEAU_RUN.search(c.path_d)
        if m and abs(float(m.group(2)) - ccy) < 0.5:
            flat = (float(m.group(1)), float(m.group(3)), float(m.group(2)))
    assert flat is not None, "no flat run under the writes chip"
    x0, x1, rail = flat
    assert x0 <= ccx <= x1, "chip off its own flat run"
    assert x1 - x0 >= chip.box.w, "flat run shorter than the chip"
    toward = -1.0 if rows["db0"] < rows["svc3"] else 1.0
    assert (rail - rows["svc3"]) * toward > 0, "rail not on the target side of the source row"
    assert abs(rows["svc3"] - rail) <= 60.0, "rail left the source's own gap band"


def test_unlabeled_bends_keep_the_pure_bow() -> None:
    """An unlabeled edge that bends (its multi-source target midpoints
    between rows) stays a single S-cubic — the plateau is chip
    infrastructure, never a general re-route (the reach is information)."""
    spec = _fan_spec(2, 0)
    spec["nodes"].append({"id": "store", "label": "store"})
    spec["edges"] += [{"source": "svc0", "target": "store"}, {"source": "svc1", "target": "store"}]
    lay = _layout(spec)
    rows = _rows(lay)
    assert abs(rows["store"] - rows["svc0"]) > 1.0 and abs(rows["store"] - rows["svc1"]) > 1.0
    assert not any(_PLATEAU_RUN.search(c.path_d) for c in lay.connectors), "a plateau appeared with no chip to carry"


def test_elbow_corridor_wraps_a_later_rank() -> None:
    """An authored under-elbow (exit bottom, entry right) computes its climb
    against the actual boxes in its span — the rightmost obstacle plus
    clearance, never just the target's face. With a fourth rank seated east
    of the entry face (the store archives to s3), the climb threads the gap
    corridor between the columns instead of cutting the archive card, and
    every polyline point keeps card clearance."""
    spec = _fan_spec(4, 3)
    spec["nodes"].append({"id": "archive", "label": "Archive", "desc": "s3"})
    spec["edges"] += [
        {"source": "db0", "target": "archive"},
        {
            "source": "svc3",
            "target": "db0",
            "label": "writes",
            "label_style": "chip",
            "exit": "bottom",
            "entry": "right",
        },
    ]
    lay = _layout(spec)
    boxes = _boxes(lay)
    elbows = [c for c in lay.connectors if c.path_d.count("Q") == 3 and "C" not in c.path_d]
    assert elbows, "authored elbow route missing"
    climb_xs = {float(m.group(1)) for m in re.finditer(r"L ([-0-9.]+),[-0-9.]+ Q", elbows[0].path_d)}
    rise_x = max(climb_xs)
    store_right = boxes["db0"].x + boxes["db0"].w
    assert store_right + 17.0 <= rise_x <= boxes["archive"].x - 17.0, (
        f"climb corridor left the gap: {rise_x} vs store right {store_right}, archive left {boxes['archive'].x}"
    )
    pts = [(float(a), float(b)) for a, b in re.findall(r"([-0-9.]+),([-0-9.]+)", elbows[0].path_d)]
    for box in boxes.values():
        for px, py in pts:
            inside_x = box.x + 1.0 < px < box.x + box.w - 1.0
            inside_y = box.y + 1.0 < py < box.y + box.h - 1.0
            assert not (inside_x and inside_y), f"elbow cuts a card at ({px},{py}) in {box}"


def test_gateway_balanced_placements_reproduce() -> None:
    """The second reference render: gateway-balanced already obeys the lane
    law by hand — the funnel apex dead on the middle tier's row, the
    telemetry sink riding its rail below the grid — so the pass reproduces
    it as a no-op."""
    bs = resolve_bundled_spec("diagram", "gateway-balanced")
    rows = _rows(_layout(dict(bs.value)))
    assert abs(rows["cache"] - rows["deep"]) < 0.5, "funnel apex off the middle tier"
    midpoint = (rows["fast"] + rows["vision"]) / 2
    assert abs(rows["cache"] - midpoint) < 0.5
    assert rows["metrics"] > rows["vision"] + 30.0, "telemetry sink left its rail"
