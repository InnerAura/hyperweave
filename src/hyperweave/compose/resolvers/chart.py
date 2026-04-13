"""Chart frame resolver — star history / time-series visualization.

Reads pre-fetched connector data from ``spec.connector_data`` and delegates
the actual SVG math to :mod:`hyperweave.render.chart_engine`.

Three-state truthfulness contract:
    - ``connector_data is None``         → ``data-hw-status="stale"``, "DATA UNAVAILABLE" overlay
    - ``current_stars == 0`` (new repo)  → ``data-hw-status="empty"``, "NEW REPO · NO STARS YET" overlay
    - real points + current_stars > 0    → ``data-hw-status="fresh"``, live chart

The chart never fabricates data. There is no placeholder series — a zero-star
repo is a legitimate state, and upstream failure is rendered truthfully as
unavailable rather than masked with demo data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hyperweave.render.chart_engine import Viewport, build_chart_svg

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec


# Default milestones for star charts (shown when values cross these thresholds).
_DEFAULT_MILESTONES: list[int] = [500, 1000, 2000, 5000, 10000]


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
    vp = (
        Viewport(x=80, y=160, w=750, h=250)
        if paradigm == "chrome"
        else Viewport(x=80, y=150, w=760, h=245)
    )

    # Three-state machine. "fresh" preserved (not renamed to "live") for
    # backward compat with the existing data-hw-status contract; "empty" is
    # new and specifically marks a truthful zero-star state.
    connector = spec.connector_data
    raw_points: list[Any]
    empty_message: str | None
    if connector is None:
        # Upstream API failure — no data to trust.
        status = "stale"
        raw_points = []
        current_stars = 0
        empty_message = "DATA UNAVAILABLE"
    else:
        current_stars = int(
            connector.get("current_stars") or connector.get("stars_total") or 0
        )
        raw_points = list(
            connector.get("points") or connector.get("star_history") or []
        )
        if current_stars == 0:
            # Truthful zero-star state (brand-new repo) — render empty, don't fabricate.
            status = "empty"
            raw_points = []
            empty_message = "NEW REPO · NO STARS YET"
        elif not raw_points:
            # Has stars but no history — shouldn't happen after the connector
            # fix, but degrade truthfully rather than synthesize.
            status = "stale"
            empty_message = "HISTORY UNAVAILABLE"
        else:
            status = "fresh"
            empty_message = None

    # Structural hints come from the resolver injection in compose/resolver.py,
    # but we also read directly from the genome here because this file is
    # imported before _resolve_paradigm has run (resolvers run INSIDE resolve()).
    structural = genome.get("structural") or {}

    chart_fragments = build_chart_svg(
        raw_points,
        vp,
        structural,
        milestones=_DEFAULT_MILESTONES,
        empty_message=empty_message,
    )

    repo = connector.get("repo") if connector else None
    repo = repo or f"{spec.chart_owner}/{spec.chart_repo}".strip("/")

    # Hero identity strings shown at top + right of the standalone chart.
    title_upper = (repo or "star history").upper()
    current_display = _format_compact(int(current_stars))

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
        "chart_y_labels": chart_fragments["y_labels"],
        "chart_x_labels": chart_fragments["x_labels"],
        "chart_empty_state": chart_fragments["empty_state"],
        "data_hw_status": status,
    }
    # Surface non-fresh states via the document-level data-hw-status attribute.
    # "fresh" stays implicit (live data is the default, no status marker needed).
    if status != "fresh":
        ctx["status"] = status

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
