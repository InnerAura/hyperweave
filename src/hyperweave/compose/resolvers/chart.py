"""Chart frame resolver — star history / time-series visualization.

Reads pre-fetched connector data from ``spec.connector_data`` and delegates
the actual SVG math to :mod:`hyperweave.render.chart_engine`. Graceful
degradation: if ``connector_data`` is ``None`` (API failure upstream), renders
with a short placeholder series and emits ``data-hw-status="stale"``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from hyperweave.render.chart_engine import Viewport, build_chart_svg

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec


# Default milestones for star charts (shown when values cross these thresholds).
_DEFAULT_MILESTONES: list[int] = [500, 1000, 2000, 5000, 10000]


def _placeholder_points() -> list[dict[str, Any]]:
    """Six synthetic points spanning the last ~12 months.

    Used when ``connector_data`` is missing or malformed so the template still
    renders a readable chart shape. Templates set ``data-hw-status="stale"``
    to mark this visually.
    """
    today = datetime.now(UTC)
    return [
        {"date": (today - timedelta(days=d)).isoformat(), "count": v}
        for d, v in zip(
            (360, 300, 240, 180, 120, 60, 0),
            (120, 240, 380, 520, 720, 980, 1200),
            strict=True,
        )
    ]


def resolve_chart(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve the ``chart`` frame into width/height/template/context."""
    width, height = 900, 500

    # Viewport insets: leave room for hero title at top, axis labels on left,
    # date labels at bottom, and hero value at right.
    # Dimensions match the target SVGs in tier2/genomes/.
    paradigm = genome.get("paradigms", {}).get("chart", "brutalist")
    vp = Viewport(x=80, y=160, w=750, h=250) if paradigm == "chrome" else Viewport(x=80, y=150, w=760, h=245)

    # Extract raw point data from connector_data (injected at HTTP/CLI layer).
    stale = False
    connector = spec.connector_data or {}
    raw_points = connector.get("points") or connector.get("star_history") or []
    if not raw_points:
        raw_points = _placeholder_points()
        stale = True

    current_stars = connector.get("current_stars") or connector.get("stars_total")
    if current_stars is None and raw_points:
        # Fall back to the last point's count.
        last_entry = raw_points[-1]
        if isinstance(last_entry, dict):
            current_stars = last_entry.get("count", last_entry.get("value", 0))

    # Structural hints come from the resolver injection in compose/resolver.py,
    # but we also read directly from the genome here because this file is
    # imported before _resolve_paradigm has run (resolvers run INSIDE resolve()).
    structural = genome.get("structural") or {}

    chart_fragments = build_chart_svg(
        raw_points,
        vp,
        structural,
        milestones=_DEFAULT_MILESTONES,
    )

    repo = connector.get("repo") or f"{spec.chart_owner}/{spec.chart_repo}".strip("/")

    # Hero identity strings shown at top + right of the standalone chart.
    title_upper = (repo or "star history").upper()
    current_display = _format_compact(int(current_stars or 0))

    ctx: dict[str, Any] = {
        "chart_repo": repo,
        "chart_title": title_upper,
        "chart_current_stars": current_display,
        "chart_viewport_x": vp.x,
        "chart_viewport_y": vp.y,
        "chart_viewport_w": vp.w,
        "chart_viewport_h": vp.h,
        "chart_defs": chart_fragments["defs"],
        "chart_axes": chart_fragments["axes"],
        "chart_gridlines": chart_fragments["gridlines"],
        "chart_area": chart_fragments["area"],
        "chart_polyline": chart_fragments["polyline"],
        "chart_markers": chart_fragments["markers"],
        "chart_milestones": chart_fragments["milestones"],
        "data_hw_status": "stale" if stale else "fresh",
    }
    # Surface stale state via the document-level data-hw-status attribute as
    # well as the chart-specific data_hw_status. This is the PRD-mandated
    # graceful-degradation marker consumed by clients/tests.
    if stale:
        ctx["status"] = "stale"

    return {
        "width": width,
        "height": height,
        "template": "frames/chart.svg.j2",
        "context": ctx,
    }


def _format_compact(n: int) -> str:
    """Render an integer as a compact string (2850 → '2,850', 12847 → '12.8K')."""
    if n >= 10000:
        return f"{n / 1000:.1f}K".rstrip("0").rstrip(".")
    return f"{n:,}"
