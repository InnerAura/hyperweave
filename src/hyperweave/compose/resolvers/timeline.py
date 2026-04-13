"""Timeline frame resolver — vertical roadmap node chain.

Reads ``spec.timeline_items`` and precomputes per-item layout, shape, and
opacity values so the Jinja template is a simple loop over pre-rendered rows.
The opacity cascade (``1.0 → 0.7 → 0.5 → 0.35 → 0.25``) expresses temporal
depth: earlier/completed items render at full opacity, future items fade.

Node shape is derived from the genome's ``structural.data_point_shape``:
    ``square``  → ``<rect>``
    ``circle``  → ``<circle>``
    ``diamond`` → rotated ``<rect>``

Status determines the fill color (passing/active/warning/failing via CSS vars).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec


_TIMELINE_WIDTH = 800
_HEADER_OFFSET = 80  # top padding for title + axis
_ROW_HEIGHT = 80
_FOOTER_OFFSET = 40
_LEFT_GUTTER = 120  # space for the timeline spine + node column


_STATUS_COLOR_VAR: dict[str, str] = {
    "passing": "var(--dna-status-passing-core)",
    "active": "var(--dna-signal)",
    "building": "var(--dna-status-warning-core)",
    "warning": "var(--dna-status-warning-core)",
    "critical": "var(--dna-status-failing-core)",
    "failing": "var(--dna-status-failing-core)",
    "offline": "var(--dna-ink-muted)",
}


def _compute_opacity(index: int, total: int) -> float:
    """Opacity cascade: earlier items full, later items fade toward 0.25.

    Uses ``max(0.25, 1.0 - (i / total) * 0.6)`` so the first item is 1.0 and
    the last item clamps at 0.4 for any ``total >= 1``. Floor is 0.25 which
    keeps future items readable under light-mode overlays.
    """
    if total <= 1:
        return 1.0
    raw = 1.0 - (index / total) * 0.6
    return max(0.25, round(raw, 3))


def _placeholder_items() -> list[dict[str, Any]]:
    """Three-item fallback used when spec.timeline_items is None.

    Same shape the CLI reads from ``--data ./items.json``.
    """
    return [
        {"title": "v0.1", "subtitle": "Foundation", "status": "passing", "date": "2025-10"},
        {"title": "v0.2", "subtitle": "Stats Card", "status": "active", "date": "2026-04"},
        {"title": "v0.3", "subtitle": "Storage", "status": "building", "date": "2026-07"},
    ]


def resolve_timeline(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    **_kw: Any,
) -> dict[str, Any]:
    """Compute timeline dimensions and per-node layout context."""
    items = spec.timeline_items or _placeholder_items()
    total = len(items)
    height = _HEADER_OFFSET + (_ROW_HEIGHT * total) + _FOOTER_OFFSET

    structural = genome.get("structural") or {}
    node_shape = str(structural.get("data_point_shape", "square"))

    # Precompute everything the template needs so the Jinja loop stays trivial.
    rows: list[dict[str, Any]] = []
    for i, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        y = _HEADER_OFFSET + (i * _ROW_HEIGHT) + (_ROW_HEIGHT // 2)
        status = str(raw.get("status", "active"))
        rows.append(
            {
                "index": i,
                "y": y,
                "title": str(raw.get("title", "") or ""),
                "subtitle": str(raw.get("subtitle", "") or ""),
                "date": str(raw.get("date", "") or ""),
                "status": status,
                "opacity": _compute_opacity(i, total),
                "node_shape": node_shape,
                "node_fill": _STATUS_COLOR_VAR.get(status, "var(--dna-signal)"),
                "is_first": i == 0,
                "is_last": i == total - 1,
            }
        )

    ctx: dict[str, Any] = {
        "timeline_items": rows,
        "timeline_title": spec.title or "ROADMAP",
        "timeline_left_gutter": _LEFT_GUTTER,
        "timeline_spine_x": _LEFT_GUTTER - 40,
        "timeline_node_cx": _LEFT_GUTTER - 40,
        "timeline_total": total,
    }

    return {
        "width": _TIMELINE_WIDTH,
        "height": height,
        "template": "frames/timeline.svg.j2",
        "context": ctx,
    }
