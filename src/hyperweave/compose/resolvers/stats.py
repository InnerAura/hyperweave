"""Stats card frame resolver — GitHub profile summary.

Consumes ``spec.connector_data`` (produced by ``fetch_user_stats``) and
routes the rendering context to one of the declared stats paradigms:

    brutalist  → brutalist hero-left layout (emerald mockups)
    chrome     → chrome-horizon material stack layout

For the ``chrome`` paradigm the resolver also calls the shared chart engine
to produce an embedded compact chart fragment (star history strip) that the
template drops into its bottom zone. This is the mechanism that makes the
stats card a COMPOSITION of stats + chart, not two separate artifacts.
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, Any

from hyperweave.render.chart_engine import Viewport, build_chart_svg

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec


_STATS_WIDTH = 495
_STATS_HEIGHTS: dict[str, int] = {"brutalist": 280, "chrome": 260}


def _format_count(n: int) -> str:
    """Compact integer formatting: 2850 → '2,850', 12847 → '12.8K', 1203 → '1,203'."""
    if n is None:
        return "—"
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "—"
    if n <= 0:
        return "0"
    if n >= 10000:
        return f"{n / 1000:.1f}K".rstrip("0").rstrip(".")
    return f"{n:,}"


def _build_activity_bars(heatmap_grid: list[dict[str, Any]]) -> list[dict[str, int]]:
    """Aggregate daily heatmap cells into 52 weekly totals.

    Returns a list of ``{"week": 0..51, "count": N}`` entries.
    """
    if not heatmap_grid:
        return []
    # Group by week (every 7 consecutive days).
    weeks: list[dict[str, int]] = []
    for i in range(0, len(heatmap_grid), 7):
        chunk = heatmap_grid[i : i + 7]
        total = sum(int(c.get("count", 0) or 0) for c in chunk)
        weeks.append({"week": len(weeks), "count": total})
    return weeks[:52]  # cap at 52 weeks


def _placeholder_languages() -> list[dict[str, Any]]:
    return [
        {"name": "Python", "pct": 62.0, "count": 31},
        {"name": "TypeScript", "pct": 22.0, "count": 11},
        {"name": "Rust", "pct": 16.0, "count": 8},
    ]


def resolve_stats(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    **_kw: Any,
) -> dict[str, Any]:
    """Build the stats card context for the chosen paradigm."""
    connector = spec.connector_data or {}
    stale = not bool(connector)

    stars_total = connector.get("stars_total")
    commits_total = connector.get("commits_total")
    prs_total = connector.get("prs_total")
    issues_total = connector.get("issues_total")
    contrib_total = connector.get("contrib_total")
    streak_days = connector.get("streak_days")

    languages_raw = connector.get("language_breakdown") or _placeholder_languages()
    heatmap_grid = connector.get("heatmap_grid") or []
    username = connector.get("username") or spec.stats_username or "anonymous"
    bio = connector.get("bio") or ""
    top_language = connector.get("top_language") or ""
    repo_count = connector.get("repo_count") or 0

    # Aggregate 365 daily cells into 52 weekly totals for the activity bar chart.
    activity_bars = _build_activity_bars(heatmap_grid)
    activity_peak = max((b["count"] for b in activity_bars), default=0)

    stats_context: dict[str, Any] = {
        "stats_username": username,
        "stats_bio": bio,
        "stats_top_language": top_language,
        "stats_repo_count": repo_count,
        "stats_repo_label": f"{top_language} / {repo_count} repos" if top_language else "",
        "stars_display": _format_count(stars_total or 0),
        "stars_raw": int(stars_total or 0),
        "stars_delta_display": "",
        "commits_display": _format_count(commits_total or 0),
        "prs_display": _format_count(prs_total or 0),
        "issues_display": _format_count(issues_total or 0),
        "contrib_display": _format_count(contrib_total or 0),
        "streak_display": f"{int(streak_days or 0)}d",
        "languages": languages_raw[:4],
        "heatmap_grid": heatmap_grid,
        "activity_bars": activity_bars,
        "activity_peak": activity_peak,
    }

    if stale:
        stats_context["data_hw_status"] = "stale"
        stats_context["status"] = "stale"

    # Embedded compact chart for the chrome paradigm (and any future
    # paradigm that wants one). The chart engine is pure — no I/O — so we
    # can call it inside the resolver without violating Invariant 1.
    paradigm = genome.get("paradigms", {}).get("stats", "brutalist")
    if paradigm == "chrome":
        embed_vp = Viewport(x=240, y=170, w=220, h=70)
        chart_points = (
            connector.get("points")
            or connector.get("star_history")
            or _synthetic_series_from_total(int(stars_total or 1200))
        )
        embed = build_chart_svg(
            chart_points,
            embed_vp,
            genome.get("structural") or {},
        )
        stats_context["embedded_chart_defs"] = embed["defs"]
        stats_context["embedded_chart_area"] = embed["area"]
        stats_context["embedded_chart_polyline"] = embed["polyline"]
        stats_context["embedded_chart_markers"] = embed["markers"]
        stats_context["embedded_chart_viewport_x"] = embed_vp.x
        stats_context["embedded_chart_viewport_y"] = embed_vp.y
        stats_context["embedded_chart_viewport_w"] = embed_vp.w
        stats_context["embedded_chart_viewport_h"] = embed_vp.h

    return {
        "width": _STATS_WIDTH,
        "height": _STATS_HEIGHTS.get(paradigm, 260),
        "template": "frames/stats.svg.j2",
        "context": stats_context,
    }


def _synthetic_series_from_total(total: int) -> list[dict[str, Any]]:
    """Generate a six-point monotonic curve that ends at ``total``.

    Used when connector_data lacks a full star history (e.g. a stats fetch
    succeeded but the caller didn't also run fetch_stargazer_history). The
    shape is plausible but deterministic — no randomness, so cached renders
    are identical.
    """
    from datetime import datetime, timedelta

    today = datetime.now(UTC)
    fractions = (0.08, 0.18, 0.34, 0.52, 0.76, 1.0)
    months_ago = (360, 300, 240, 180, 120, 60)
    return [
        {
            "date": (today - timedelta(days=days)).isoformat(),
            "count": max(1, int(total * frac)),
        }
        for days, frac in zip(months_ago, fractions, strict=True)
    ]
