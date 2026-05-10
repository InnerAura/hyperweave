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
    paradigm_spec: Any = None,
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve the ``chart`` frame into width/height/template/context."""
    # Chart dimensions + viewport live in data/paradigms/{slug}.yaml.
    # Cellular v0.3.0 refresh: 680x380 with viewport (72,80) size 580x246 and
    # cell stride 19 (cell width 18, 1px gap) yielding a 30-col x 13-row grid.
    # Brutalist and chrome keep 900x500 with their own viewport. Header band
    # height drives the HUD-style header zone in the cellular template.
    if paradigm_spec is not None:
        cc = paradigm_spec.chart
        width, height = cc.chart_width, cc.chart_height
        vp = Viewport(x=cc.viewport_x, y=cc.viewport_y, w=cc.viewport_w, h=cc.viewport_h)
        line_animate = bool(cc.line_animate)
        cellular_cell_size = int(cc.cell_size) if cc.cell_size > 0 else 40
        chart_header_band_height = int(cc.header_band_height)
    else:
        width, height = 900, 500
        vp = Viewport(x=80, y=150, w=760, h=245)
        line_animate = False
        cellular_cell_size = 40
        chart_header_band_height = 0

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
        current_stars = int(connector.get("current_stars") or connector.get("stars_total") or 0)
        raw_points = list(connector.get("points") or connector.get("star_history") or [])
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

    # Cellular paradigm chart substrate: pull chart_levels (6 colors,
    # darkest→brightest) from the variant's primary tone via the dispatcher-
    # supplied cellular_palette kwarg. brutalist + chrome don't pass a
    # cellular_palette, so cellular_chart_levels stays None and build_chart_svg
    # returns an empty cellular_area dict (template skips rendering cells).
    cellular_palette: dict[str, Any] = _kw.get("cellular_palette") or {}
    cellular_chart_levels: list[str] | None = None
    cellular_dormant_range: list[str] | None = None
    primary_tone = cellular_palette.get("primary") or {}
    if primary_tone:
        levels = primary_tone.get("chart_levels")
        if isinstance(levels, list) and len(levels) == 6:
            cellular_chart_levels = levels
        dormant = primary_tone.get("dormant_range")
        if isinstance(dormant, list) and len(dormant) == 2:
            cellular_dormant_range = dormant

    # Cellular charts target a denser Y-tick set (6 labels: 3K/2K/1.5K/1K/0.5K/0)
    # to match the cobalt-sapphire reference's axis prominence. Brutalist and
    # chrome stay at 4 labels — their chart aesthetic doesn't need the extra
    # granularity. Detected via cellular_palette presence (only cellular
    # paradigm passes it).
    y_tick_target = 6 if cellular_chart_levels else 4

    chart_fragments = build_chart_svg(
        raw_points,
        vp,
        structural,
        milestones=_DEFAULT_MILESTONES,
        empty_message=empty_message,
        cellular_chart_levels=cellular_chart_levels,
        cellular_dormant_range=cellular_dormant_range,
        cellular_cell_size=cellular_cell_size,
        y_tick_target=y_tick_target,
    )

    repo = connector.get("repo") if connector else None
    repo = repo or f"{spec.chart_owner}/{spec.chart_repo}".strip("/")

    # Hero identity strings shown at top + right of the standalone chart.
    title_upper = (repo or "star history").upper()
    current_display = _format_compact(int(current_stars))

    # Footer date range — "Mon YYYY — Mon YYYY" bookending the data we actually
    # plotted. Cellular paradigm consumes this; other paradigms ignore it and
    # fall back to repo slug via the template's | default chain. Empty string
    # when we have no points (stale/empty states keep the repo slug).
    date_range = _format_date_range(raw_points)

    # Cellular v0.3.0 refresh: surface info_accent / mid_accent / header_band
    # from the variant's primary tone to the template context. info_accent
    # carries the chart title + hero metric color and the polyline drop-shadow
    # glow tint; mid_accent renders axis labels at lower opacity; header_band
    # fills the HUD-style header rect at y=0..header_band_height.
    chart_info_accent = primary_tone.get("info_accent", "") if primary_tone else ""
    chart_mid_accent = primary_tone.get("mid_accent", "") if primary_tone else ""
    chart_header_band = primary_tone.get("header_band", "") if primary_tone else ""

    # Profile visual context (envelope/well/specular/chrome text gradients)
    # is injected universally by the dispatcher at resolver.resolve(), so
    # this resolver only builds chart-specific context.
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
        "chart_date_range": date_range,
        "data_hw_status": status,
        "chart_line_animate": line_animate,
        # Cellular paradigm v2 area-fill substrate (Round 6 / Issue G).
        # cellular_area_cells: list of {x, y, w, h, fill, anim_class} dicts
        # rendered as <rect> children inside the clipPath group. Empty list
        # for non-cellular paradigms (brutalist/chrome charts skip the
        # area-cells block entirely via {% if cellular_area_cells %}).
        "cellular_area_cells": chart_fragments["cellular_area"]["cells"],
        "cellular_area_clip_d": chart_fragments["cellular_area"]["clip_path_d"],
        "cellular_marker_colors": chart_fragments["cellular_area"]["marker_colors"],
        "cellular_dormant_cells": chart_fragments["cellular_area"]["dormant_cells"],
        # Cellular v0.3.0 chart refresh — header band + accent stops.
        "chart_header_band_height": chart_header_band_height,
        "chart_header_band_fill": chart_header_band,
        "chart_info_accent": chart_info_accent,
        "chart_mid_accent": chart_mid_accent,
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


def _format_date_range(points: list[Any]) -> str:
    """Derive a 'Mon YYYY — Mon YYYY' bookend string from the first and last
    point dates.

    Returns an empty string when points are missing or dates don't parse —
    the template falls back to the repo slug in that case so the footer never
    renders blank.
    """
    if not points:
        return ""
    from contextlib import suppress
    from datetime import datetime

    def _parse(p: Any) -> datetime | None:
        if not isinstance(p, dict):
            return None
        d = p.get("date")
        if not isinstance(d, str):
            return None
        with suppress(ValueError):
            return datetime.fromisoformat(d.replace("Z", "+00:00"))
        return None

    first = _parse(points[0])
    last = _parse(points[-1])
    if first is None or last is None:
        return ""
    return f"{first.strftime('%b %Y')} — {last.strftime('%b %Y')}"
