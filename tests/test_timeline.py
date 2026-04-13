"""Tests for the timeline frame (Session 2A+2B Phase 6).

Covers resolver math (opacity cascade, node shape dispatch) and end-to-end
compose with both a custom item list and the placeholder fallback.
"""

from __future__ import annotations

from hyperweave.compose.engine import compose
from hyperweave.compose.resolvers.timeline import _compute_opacity, resolve_timeline
from hyperweave.core.models import ComposeSpec

SAMPLE_ITEMS = [
    {"title": "v0.1", "subtitle": "Foundation", "status": "passing", "date": "2025-10"},
    {"title": "v0.2", "subtitle": "Stats Card", "status": "active", "date": "2026-04"},
    {"title": "v0.3", "subtitle": "Storage", "status": "building", "date": "2026-07"},
    {"title": "v0.4", "subtitle": "Genome Blitz", "status": "warning", "date": "2026-09"},
]


# ── Opacity cascade math ──────────────────────────────────────────────


def test_opacity_cascade_clamps_at_floor() -> None:
    from itertools import pairwise

    # 10 items → later items still readable at the 0.25 floor.
    total = 10
    opacities = [_compute_opacity(i, total) for i in range(total)]
    assert opacities[0] == 1.0
    assert opacities[-1] >= 0.25
    # monotonically decreasing (tolerate 0.001 floating-point slack)
    assert all(a >= b - 0.001 for a, b in pairwise(opacities))


def test_opacity_single_item_is_full() -> None:
    assert _compute_opacity(0, 1) == 1.0


def test_opacity_two_items_range() -> None:
    # First item full, second item somewhere between floor and 1.0.
    assert _compute_opacity(0, 2) == 1.0
    assert 0.25 <= _compute_opacity(1, 2) <= 1.0


# ── Resolver output ────────────────────────────────────────────────────


def test_resolve_timeline_uses_placeholder_when_items_missing() -> None:
    spec = ComposeSpec(type="timeline", genome_id="brutalist-emerald")
    # Load a minimal genome dict to avoid hitting the registry singleton.
    genome = {"structural": {"data_point_shape": "square"}}
    profile = {"id": "brutalist"}
    result = resolve_timeline(spec, genome, profile)

    items = result["context"]["timeline_items"]
    assert len(items) == 3  # placeholder fallback
    assert items[0]["opacity"] == 1.0


def test_resolve_timeline_custom_items() -> None:
    spec = ComposeSpec(type="timeline", timeline_items=SAMPLE_ITEMS)
    genome = {"structural": {"data_point_shape": "circle"}}
    profile = {"id": "brutalist"}
    result = resolve_timeline(spec, genome, profile)

    items = result["context"]["timeline_items"]
    assert len(items) == 4
    # Circle node shape propagated from structural hint.
    assert all(it["node_shape"] == "circle" for it in items)
    # First item is `is_first`, last is `is_last`.
    assert items[0]["is_first"] is True
    assert items[-1]["is_last"] is True
    # Opacity cascade is strictly decreasing.
    opacities = [it["opacity"] for it in items]
    assert opacities == sorted(opacities, reverse=True)


def test_resolve_timeline_height_scales_with_items() -> None:
    spec_short = ComposeSpec(type="timeline", timeline_items=SAMPLE_ITEMS[:2])
    spec_long = ComposeSpec(type="timeline", timeline_items=SAMPLE_ITEMS)
    genome = {"structural": {}}
    profile = {"id": "brutalist"}
    short = resolve_timeline(spec_short, genome, profile)
    long_ = resolve_timeline(spec_long, genome, profile)
    assert long_["height"] > short["height"]
    assert short["width"] == long_["width"] == 800


def test_resolve_timeline_status_colors() -> None:
    spec = ComposeSpec(type="timeline", timeline_items=SAMPLE_ITEMS)
    genome = {"structural": {}}
    profile = {"id": "brutalist"}
    rows = resolve_timeline(spec, genome, profile)["context"]["timeline_items"]
    fills = {r["status"]: r["node_fill"] for r in rows}
    # Status→color mapping is stable.
    assert "passing" in fills
    assert "active" in fills
    assert fills["warning"] != fills["passing"]  # warning ≠ passing fill


# ── End-to-end compose ─────────────────────────────────────────────────


def test_timeline_compose_renders_placeholder() -> None:
    spec = ComposeSpec(type="timeline", genome_id="brutalist-emerald")
    result = compose(spec)
    svg = result.svg
    assert 'data-hw-frame="timeline"' in svg
    # Placeholder items include "Foundation", "Stats Card", "Storage".
    assert "Foundation" in svg or "FOUNDATION" in svg
    assert result.width == 800


def test_timeline_compose_renders_custom_items() -> None:
    spec = ComposeSpec(type="timeline", genome_id="brutalist-emerald", timeline_items=SAMPLE_ITEMS)
    result = compose(spec)
    svg = result.svg
    # Every item title appears in the SVG.
    for item in SAMPLE_ITEMS:
        assert item["title"] in svg
    # Opacity cascade → at least one non-1.0 opacity attribute present.
    assert 'opacity="0.' in svg


def test_timeline_compose_uses_node_shape_from_genome_structural() -> None:
    """brutalist-emerald declares data_point_shape=square → rect nodes."""
    spec = ComposeSpec(type="timeline", genome_id="brutalist-emerald", timeline_items=SAMPLE_ITEMS)
    svg = compose(spec).svg
    # Default brutalist shape is square → rect nodes (not circles or rotated rects).
    assert "<rect" in svg

    spec2 = ComposeSpec(type="timeline", genome_id="chrome-horizon", timeline_items=SAMPLE_ITEMS)
    svg2 = compose(spec2).svg
    # chrome-horizon declares data_point_shape=diamond → rotated rects.
    assert "rotate(45" in svg2


def test_timeline_compose_contains_flow_animation() -> None:
    """Timeline spine uses stroke-dasharray + animation for the flow effect."""
    spec = ComposeSpec(type="timeline", genome_id="brutalist-emerald", timeline_items=SAMPLE_ITEMS)
    svg = compose(spec).svg
    assert "stroke-dasharray" in svg
    # prefers-reduced-motion override is mandatory (Invariant from CLAUDE.md).
    assert "prefers-reduced-motion" in svg
