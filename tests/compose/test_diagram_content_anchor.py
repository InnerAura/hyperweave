"""Content-anchor and detour-route laws (the card slot model + orthogonal skips).

Content-anchor law: a card's content group LEFT-ANCHORS at the chassis
``glyph_inset_x`` and the text column sits at ``inset + mark + glyph_label_gap``
— a chassis fact, never a function of the card's own slack or its siblings'
text variance. The language sheet's providers seat glyph at card+22 / text at
card+60 down the whole column; the serving hand file measures the same; the
nucleus family declares its own wider pair. Column uniformity (stacked cards
sharing ONE text edge) follows by construction.

Detour law: edge geometry is per-edge-class. Relational edges own the bow
family; a detour/bypass route is ORTHOGONAL — straight axis-aligned legs
joined by tight fixed-radius quarter-turn fillets (``ch.over_arc_r``), the
fillet a fixed px value, never a fraction of run length. The gateway hand
file's telemetry pins the family (drop leg, r=7 fillet, flat run, r=7
fillet, rise leg). Enrolled across both directions (under-route bottom→bottom
and the default right→left) and the over-route already carried by the
service-dependencies direct-read.
"""

from __future__ import annotations

import itertools
import re
from typing import Any

import pytest

from hyperweave.compose.bundled_specs import resolve_bundled_spec
from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.input import coerce_diagram_input, resolve_auto_roles
from hyperweave.compose.diagram.sizing import GLYPH_MARK_W
from hyperweave.compose.diagram.solver import apply_spec_chassis
from hyperweave.config.loader import load_diagram_config, load_glyphs, load_paradigms
from hyperweave.core.diagram import DiagramSpec, layout_slug
from hyperweave.core.models import ComposeSpec
from hyperweave.core.paradigm import DiagramTopologyChassis, ParadigmDiagramConfig

ENGINE = load_diagram_config()
_pspec = load_paradigms()["primer"]
PARADIGM: ParadigmDiagramConfig = _pspec.diagram if _pspec is not None else ParadigmDiagramConfig()
GLYPHS = load_glyphs()


def _preset_spec(name: str) -> DiagramSpec:
    spec_dict = dict(resolve_bundled_spec("diagram", name).value)
    cs = ComposeSpec(type="diagram", genome_id="primer", variant="porcelain", ground="bare", diagram=spec_dict)
    return coerce_diagram_input(cs.connector_data, cs).spec


def _preset_layout(name: str) -> Any:
    return compute_diagram_layout(
        _preset_spec(name), paradigm=PARADIGM, engine=ENGINE, palette_len=6, glyph_registry=GLYPHS
    )


def _resolved_chassis(spec: DiagramSpec) -> DiagramTopologyChassis:
    ch = PARADIGM.topologies.get(layout_slug(spec)) or DiagramTopologyChassis()
    return apply_spec_chassis(ch, spec.chassis)


# ── Content-anchor law ──────────────────────────────────────────────────────

_ANCHOR_PRESETS = ("model-router", "convergence", "convergence-arrivals", "model-gateway-tiers", "frontier-serving")


def test_card_glyph_content_anchors_at_chassis_inset() -> None:
    """Every rect card with a glyph seats the mark's LEFT edge at
    ``box.x + glyph_inset_x`` and its label at ``box.x + inset + mark +
    glyph_label_gap`` — for heroes and standard cards alike."""
    for preset in _ANCHOR_PRESETS:
        spec = _preset_spec(preset)
        ch = _resolved_chassis(spec)
        lay = compute_diagram_layout(spec, paradigm=PARADIGM, engine=ENGINE, palette_len=6, glyph_registry=GLYPHS)
        checked = 0
        for p in lay.nodes:
            if p.shape != "rect" or p.glyph is None or not p.glyph.size:
                continue
            nch = ch.hero if p.role == "hero" else ch.node
            inset = nch.glyph_inset_x
            mark = nch.glyph_w or GLYPH_MARK_W
            glyph_left = p.glyph.cx - p.glyph.size / 2
            assert abs(glyph_left - (p.box.x + inset)) < 0.51, (
                f"{preset}/{p.node_id}: glyph left {glyph_left - p.box.x:.2f} from card edge, law says {inset}"
            )
            assert abs(p.label.x - (p.box.x + inset + mark + nch.glyph_label_gap)) < 0.51, (
                f"{preset}/{p.node_id}: text column {p.label.x - p.box.x:.2f} from card edge, "
                f"law says {inset + mark + nch.glyph_label_gap}"
            )
            checked += 1
        assert checked >= 2, f"{preset}: anchor law never exercised (no card+glyph placements found)"


def test_stacked_cards_share_one_text_column() -> None:
    """Column uniformity: standard cards sharing a column x seat their labels
    on ONE text edge (the retired per-card centering wobbled the column with
    each card's own slack)."""
    for preset in _ANCHOR_PRESETS:
        lay = _preset_layout(preset)
        by_col: dict[float, list[float]] = {}
        for p in lay.nodes:
            if p.shape != "rect" or p.role == "hero":
                continue
            by_col.setdefault(round(p.box.x, 1), []).append(p.label.x - p.box.x)
        for col_x, insets in by_col.items():
            if len(insets) < 2:
                continue
            assert max(insets) - min(insets) < 0.51, (
                f"{preset}: column at x={col_x} carries {len(insets)} cards with text insets {insets}"
            )


def test_same_crown_spec_solves_same_width_everywhere() -> None:
    """Ruling 4 (snug-width, 2026-07-14): 'the artifact' is ONE concept —
    an identical crown spec (label + desc + mark) solves the identical
    width in every topology. Under content-solve this holds by
    construction; this pin catches any future per-preset width citation
    quietly re-inflating one copy of a shared crown."""
    from collections import defaultdict

    from hyperweave.compose.diagram.input import diagram_preset_names

    by_spec: dict[tuple[str, str, str], set[tuple[str, float]]] = defaultdict(set)
    for preset in sorted(diagram_preset_names()):
        spec = _preset_spec(preset)
        lay = compute_diagram_layout(spec, paradigm=PARADIGM, engine=ENGINE, palette_len=6, glyph_registry=GLYPHS)
        for p in lay.nodes:
            node = spec.nodes[p.index]
            if p.role != "hero" or p.shape != "rect":
                continue
            key = (node.label, node.desc or "", node.glyph or node.kind or "")
            by_spec[key].add((preset, p.box.w))
    for key, entries in by_spec.items():
        widths = {w for _, w in entries}
        assert len(widths) == 1, f"crown spec {key} solves {len(widths)} widths: {sorted(entries)}"


def test_text_ink_stays_inside_its_card() -> None:
    """No text run may cross its card's right edge (the render sweep's
    text-in-card check, promoted to the board): every label and desc row of
    every rect card, across EVERY bundled preset — the axial crown's payload
    desc escaped by 14px when the hero desc budget forgot the text-column
    lead, and only the gallery sweep caught it."""
    from hyperweave.compose.diagram.input import diagram_preset_names
    from hyperweave.compose.diagram.sizing import voice_for
    from hyperweave.compose.diagram.solver import effective_render_cfg
    from hyperweave.compose.matrix.cells import measure_voice

    overflows: list[str] = []
    for preset in sorted(diagram_preset_names()):
        spec = _preset_spec(preset)
        cfg = effective_render_cfg(spec, PARADIGM)
        lay = compute_diagram_layout(spec, paradigm=PARADIGM, engine=ENGINE, palette_len=6, glyph_registry=GLYPHS)
        for p in lay.nodes:
            if p.shape != "rect":
                continue
            right = p.box.x + p.box.w
            for run in (p.label, *p.desc_lines):
                if run.anchor != "start" or not run.text:
                    continue
                end = run.x + measure_voice(run.text, voice_for(cfg, run.cls))
                if end > right + 0.6:
                    overflows.append(f"{preset}/{p.node_id}: {run.text[:24]!r} ends {end - right:.1f}px past the card")
    assert not overflows, "\n".join(overflows)


def test_edge_run_citations_hold_independent_of_card_widths() -> None:
    """Edge-run law (2026-07-14): pitch/margin/canvas citations describe
    FACE-TO-FACE runs, never node positions — when cards change width the
    neighbors pull in to preserve the cited gap and the canvas derives.
    Comparison's hand pair runs 220 between faces; the convergence family's
    gathered-seed envelope runs 524 members→hero."""
    for preset, want in (("comparison", 220.0), ("convergence", 524.0), ("convergence-arrivals", 524.0)):
        lay = _preset_layout(preset)
        hero = next(p for p in lay.nodes if p.role == "hero")
        members = [p for p in lay.nodes if p.role != "hero" and p.shape == "rect"]
        run = hero.box.x - max(p.box.x + p.box.w for p in members)
        assert abs(run - want) <= 0.6, f"{preset}: face-to-face run {run} vs cited {want}"


def test_s_rank_fan_follows_the_angle_family() -> None:
    """Polar case of the edge-run law: verb-reads' S fan cites its
    SPREAD-TO-DROP construction (row pitch = 0.87 x the 245 face-to-face
    gap, symmetric about the south port) — seats re-derive from the angle
    family whenever card widths change, and no member ever goes near-flat
    (the disconnected-spoke floor)."""
    import math

    lay = _preset_layout("verb-reads")
    hero = next(p for p in lay.nodes if p.role == "hero")
    port = (hero.box.x + hero.box.w / 2, hero.box.y + hero.box.h)
    rank = sorted((p for p in lay.nodes if p.node_id in ("extract", "verify", "diff", "query")), key=lambda p: p.box.x)
    spreads = [p.box.x + p.box.w / 2 - port[0] for p in rank]
    drops = [p.box.y - port[1] for p in rank]
    assert all(abs(d - 245.0) <= 0.6 for d in drops), drops
    ratios = [s / d for s, d in zip(spreads, drops, strict=True)]
    assert ratios == pytest.approx([-1.305, -0.435, 0.435, 1.305], abs=0.02), ratios
    for s_, d_ in zip(spreads, drops, strict=True):
        angle = math.degrees(math.atan2(d_, abs(s_)))
        assert angle >= 30.0, f"near-flat spoke: {angle:.1f}° at spread {s_:+.0f}"


def test_legend_seats_at_its_declared_corner() -> None:
    """Chrome law: the legend renders at its DECLARED corner (paradigm
    default right-anchored column; ``placement: left`` the cited per-preset
    flip) and never overlaps content ink; any collision displacement is
    logged, never silent."""
    for preset, corner in (("dep-audit", "right"), ("dep-audit-radial", "left")):
        lay = _preset_layout(preset)
        legends = [a for a in lay.annotations if a.kind == "legend"]
        assert legends, f"{preset}: no legend rendered"
        box = legends[0].box
        mid = lay.width / 2
        if corner == "right":
            assert box.x + box.w / 2 > mid, f"{preset}: legend at x={box.x}, expected the right corner"
        else:
            assert box.x + box.w / 2 < mid, f"{preset}: legend at x={box.x}, expected the left corner"
        for p in lay.nodes:
            ix = min(box.x + box.w, p.box.x + p.box.w) - max(box.x, p.box.x)
            iy = min(box.y + box.h, p.box.y + p.box.h) - max(box.y, p.box.y)
            assert not (ix > 0.5 and iy > 0.5), f"{preset}: legend overlaps {p.node_id}"


# ── Detour-route law ────────────────────────────────────────────────────────

_ORTHO_ROUTE = re.compile(
    r"^M (?P<pts>[-0-9.,]+)"
    r"(?P<body>( (L [-0-9.,]+|Q [-0-9.,]+ [-0-9.,]+))+)$"
)


def _segments(d: str) -> list[tuple[str, list[tuple[float, float]]]]:
    out: list[tuple[str, list[tuple[float, float]]]] = []
    for cmd, args in re.findall(r"([MLQ]) ((?:[-0-9.,]+ ?)+)", d):
        pts = [tuple(float(v) for v in pair.split(",")) for pair in args.split()]
        out.append((cmd, [(p[0], p[1]) for p in pts]))
    return out


def _assert_orthogonal_detour(d: str, r: float, *, context: str) -> None:
    """The route is straight axis-aligned L legs + Q quarter-fillets whose
    radius is the fixed chassis value (shrunk only when a leg cannot host
    the diameter) — never a cubic, never a run-proportional sweep."""
    assert "C" not in d, f"{context}: detour route emits a cubic sweep: {d}"
    assert _ORTHO_ROUTE.match(d), f"{context}: detour route is not an L/Q orthogonal chain: {d}"
    segs = _segments(d)
    cursor = segs[0][1][0]
    for cmd, pts in segs[1:]:
        if cmd == "L":
            end = pts[0]
            assert abs(end[0] - cursor[0]) < 0.01 or abs(end[1] - cursor[1]) < 0.01, (
                f"{context}: L leg {cursor}->{end} is not axis-aligned in {d}"
            )
            cursor = end
        elif cmd == "Q":
            ctrl, end = pts
            r_in = abs(ctrl[0] - cursor[0]) + abs(ctrl[1] - cursor[1])
            r_out = abs(end[0] - ctrl[0]) + abs(end[1] - ctrl[1])
            assert r_in <= r + 0.01 and r_out <= r + 0.01, (
                f"{context}: fillet spans {r_in:.1f}/{r_out:.1f}px, past the fixed {r}px law in {d}"
            )
            cursor = end


def _skip_connectors(lay: Any) -> list[Any]:
    """Connectors whose path carries a Q fillet AND a flat run — the detour
    class (relational bows are pure cubics; straight rank wires carry no Q)."""
    return [c for c in lay.connectors if "Q" in c.path_d and c.path_d.startswith("M")]


def test_under_route_detours_are_orthogonal_with_fixed_fillet() -> None:
    """Bottom-face under-routes (the gateway/serving telemetry class) run
    straight legs with the chassis fillet."""
    for preset in ("model-gateway-tiers", "frontier-serving"):
        spec = _preset_spec(preset)
        ch = _resolved_chassis(spec)
        lay = compute_diagram_layout(spec, paradigm=PARADIGM, engine=ENGINE, palette_len=6, glyph_registry=GLYPHS)
        routes = _skip_connectors(lay)
        assert routes, f"{preset}: expected at least one detour route"
        for c in routes:
            _assert_orthogonal_detour(c.path_d, ch.over_arc_r, context=preset)


def test_default_under_route_is_orthogonal_both_orientations() -> None:
    """The hint-less rank-skip (source RIGHT face → target LEFT face) rides
    the same law — five legs, four fillets — in both left→right and
    right→left compositions (rank order reversed)."""
    for ids in (("a", "b", "c"), ("c", "b", "a")):
        spec = resolve_auto_roles(
            DiagramSpec(
                topology="dag",
                title="skip",
                nodes=[
                    {"id": ids[0], "label": "Alpha"},
                    {"id": ids[1], "label": "Beta"},
                    {"id": ids[2], "label": "Gamma"},
                ],
                edges=[
                    {"source": ids[0], "target": ids[1]},
                    {"source": ids[1], "target": ids[2]},
                    {"source": ids[0], "target": ids[2]},
                ],
            )
        )
        ch = apply_spec_chassis(PARADIGM.topologies["dag"], spec.chassis)
        lay = compute_diagram_layout(spec, paradigm=PARADIGM, engine=ENGINE, palette_len=6)
        routes = _skip_connectors(lay)
        assert routes, "expected the rank-skip to route through the under-channel"
        for c in routes:
            _assert_orthogonal_detour(c.path_d, ch.over_arc_r, context=f"default-under-route {ids}")


# ── Gateway rank rhythm (even-rise family) ──────────────────────────────────


def test_gateway_tiers_rank_rhythm_matches_citation() -> None:
    """model-gateway-tiers reproduces its hand file's rhythm: every card 62
    tall, tier column at pitch 92, and the converging fan reading as ONE
    family — the even-join law. Amended with the corrected topology
    (pp-gateway-balanced.svg: every tier converges on the shared cache, the
    funnel apex on the middle tier's row): the family read is now the
    BILATERAL one — the flush center rides its lane straight while every
    bent convergent crosses the same rise, mirrored about the apex."""
    lay = _preset_layout("model-gateway-tiers")
    cards = [p for p in lay.nodes if p.shape == "rect"]
    assert {round(p.box.h) for p in cards} == {62}
    tiers = sorted(p.box.y for p in cards if p.node_id in ("fast", "deep", "vision"))
    assert [round(b - a) for a, b in itertools.pairwise(tiers)] == [92, 92]
    tier_right = max(p.box.x + p.box.w for p in cards if p.node_id in ("fast", "deep", "vision"))
    curve_rises = [round(abs(ty - sy), 1) for sy, ty in _curve_endpoints_y(lay, min_sx=tier_right - 1)]
    bent = [r for r in curve_rises if r]
    assert bent and len(set(bent)) == 1, f"converging rises diverge: {curve_rises}"
    assert len(bent) % 2 == 0, f"bent convergents must mirror about the apex: {curve_rises}"


def _curve_endpoints_y(lay: Any, *, min_sx: float) -> list[tuple[float, float]]:
    """(start_y, end_y) for each pure-cubic S-curve crossing between the tier
    and sink ranks (the converging family — straight wires and detours are
    other classes)."""
    out: list[tuple[float, float]] = []
    for c in lay.connectors:
        if "Q" in c.path_d or "C" not in c.path_d:
            continue
        m = re.match(r"M ([-0-9.]+),([-0-9.]+) C .* ([-0-9.]+),([-0-9.]+)$", c.path_d)
        if not m:
            continue
        sx, sy, ty = float(m.group(1)), float(m.group(2)), float(m.group(4))
        if sx >= min_sx:  # tier→sink crossings only (east of the tier column)
            out.append((sy, ty))
    return out
