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


def _format_count(n: int) -> str:
    """Compact integer formatting with K/M/B cascade.

    0..9,999       → '2,850'   (comma-grouped)
    10K..999,999   → '12.8K'
    1M..999M       → '45.3M'
    1B+            → '2.1B'
    """
    if n is None:
        return "—"
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "—"
    if n <= 0:
        return "0"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B".rstrip("0").rstrip(".")
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".rstrip("0").rstrip(".")
    if n >= 10_000:
        return f"{n / 1_000:.1f}K".rstrip("0").rstrip(".")
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
    paradigm_spec: Any = None,
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

    # Profile visual context (envelope/well/chrome+hero text gradients) is
    # now injected universally by the dispatcher at resolver.resolve(), so
    # per-frame resolvers no longer need to call _genome_material_context.

    # Spatial layout math: measure each metric value at the nominal font
    # size (20px Orbitron, bold) and cap with SVG textLength when a value
    # would overflow its column budget. Prevents "409457.1K" from blowing
    # past the PRS column on torvalds-tier accounts. Budget = column_width
    # minus 12px breathing room (124px columns, 112px interior).
    from hyperweave.core.text import measure_text

    _VALUE_FONT_SIZE = 20
    _COLUMN_BUDGET = 112
    # Stats value font family comes from paradigm config (chrome → Orbitron,
    # brutalist → Inter). Phase 3 extended measure_text to be font-aware;
    # Phase 4A routes the decision through paradigm_spec instead of an
    # inline ``genome.paradigms.stats == "chrome"`` branch.
    _stats_value_family = "Inter"
    if paradigm_spec is not None:
        # Chrome paradigm declares Orbitron for its hero value size zone.
        # For paradigms without a dedicated stats.value_font_family we use
        # the badge value font family as a sensible proxy (same display font).
        _stats_value_family = paradigm_spec.badge.value_font_family
    for key in ("commits", "prs", "issues", "streak"):
        display = stats_context[f"{key}_display"]
        natural = measure_text(
            display,
            font_family=_stats_value_family,
            font_size=_VALUE_FONT_SIZE,
            font_weight=700,
        )
        stats_context[f"{key}_text_length"] = _COLUMN_BUDGET if natural > _COLUMN_BUDGET else 0
    # Username identity (13px, bold) — same overflow guard for the header. Always Inter.
    identity_natural = measure_text(username, font_family="Inter", font_size=13, font_weight=700)
    stats_context["identity_text_length"] = 260 if identity_natural > 260 else 0

    # Embedded compact chart — enablement flag + viewport sourced from
    # paradigm YAML. Chrome paradigm embeds; brutalist does not. Zero
    # string comparisons in Python; adding a new paradigm that also wants
    # an embed is purely a YAML change.
    embeds_chart = bool(paradigm_spec.stats.embeds_chart) if paradigm_spec is not None else False
    if embeds_chart:
        ec = paradigm_spec.stats
        embed_vp = Viewport(x=ec.embed_viewport_x, y=ec.embed_viewport_y, w=ec.embed_viewport_w, h=ec.embed_viewport_h)
        # Zero-guard: never default to a 1200-star synthetic curve. When
        # stars_total is zero, the truthful state is an empty embedded chart.
        stars_int = int(stars_total or 0)
        real_points = connector.get("points") or connector.get("star_history")
        if real_points:
            chart_points: list[dict[str, Any]] = list(real_points)
        elif stars_int > 0:
            # Only synthesize when we know the total — this approximates a
            # plausible growth curve rather than fabricating it from nothing.
            chart_points = _synthetic_series_from_total(stars_int)
        else:
            chart_points = []
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

    card_height = paradigm_spec.stats.card_height if paradigm_spec is not None else 260
    return {
        "width": _STATS_WIDTH,
        "height": card_height,
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
