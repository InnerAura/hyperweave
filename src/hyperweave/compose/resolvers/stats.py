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


def _format_count(n: int | None) -> str:
    """Compact integer formatting with K/M/B cascade.

    0..9,999       → '2,850'   (comma-grouped)
    10K..999,999   → '12.8K'
    1M..999M       → '45.3M'
    1B+            → '2.1B'

    ``None`` is the staleness sentinel: it renders as ``"—"`` (em dash) so
    a failed sub-fetch surfaces visibly instead of being misrepresented as
    a real zero.
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
    # ``_stale_fields`` is populated by ``fetch_user_stats`` when sub-fetches
    # fail (rate limits, breaker open, network errors). Stale fields render
    # as ``—`` rather than misrepresenting failure as a real ``0`` — the bug
    # that produced v0.2.10's silent COMMITS=0/PRS=0 readings under search-
    # API quota exhaustion. Empty list / missing key → fully live data.
    stale_fields: set[str] = set(connector.get("_stale_fields") or ())
    stale = not bool(connector) or bool(stale_fields)

    def _value_or_none(field: str) -> Any:
        """Pass through ``None`` for stale fields, raw value otherwise.

        ``_format_count(None)`` already returns ``"—"``, so this is the only
        change needed at the formatting layer to surface staleness visually.
        """
        if field in stale_fields:
            return None
        return connector.get(field)

    stars_total = _value_or_none("stars_total")
    commits_total = _value_or_none("commits_total")
    prs_total = _value_or_none("prs_total")
    issues_total = _value_or_none("issues_total")
    contrib_total = _value_or_none("contrib_total")
    streak_days = _value_or_none("streak_days")

    # Stars delta annotation — production cellular stat card shows
    # "▲ 2,431 /yr" beside the hero STARS value to communicate momentum.
    # Source priority:
    #   1. ``connector["stars_last_year"]`` — explicit value from connector
    #   2. ``connector["points"]`` — diff latest count vs the earliest
    #      point inside the last 365 days
    # When neither is available the delta annotation renders blank, which
    # matches the "no data" edge case rather than fabricating zero growth.
    stars_delta_raw = connector.get("stars_last_year")
    if stars_delta_raw is None:
        pts = connector.get("points") or connector.get("star_history") or []
        if pts:
            from datetime import datetime, timedelta

            now = datetime.now(UTC)
            cutoff = now - timedelta(days=365)
            try:
                # Points are typically sorted oldest→newest; the latest point
                # is the current cumulative star count. Find the earliest
                # point on/after the cutoff to compute the year-over-year
                # delta. Defensive parsing handles ISO dates with or without
                # timezone, and tolerates plain YYYY-MM-DD strings.
                latest_count = int(pts[-1].get("count", 0))
                older_count = latest_count
                for p in pts:
                    raw_date = p.get("date")
                    if not isinstance(raw_date, str):
                        continue
                    try:
                        d = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    if d.tzinfo is None:
                        d = d.replace(tzinfo=UTC)
                    if d >= cutoff:
                        older_count = int(p.get("count", 0))
                        break
                stars_delta_raw = max(latest_count - older_count, 0)
            except (TypeError, KeyError, ValueError):
                stars_delta_raw = None
    stars_delta_display = _format_count(stars_delta_raw) if stars_delta_raw else ""

    languages_raw = connector.get("language_breakdown") or _placeholder_languages()
    heatmap_grid = connector.get("heatmap_grid") or []
    username = connector.get("username") or spec.stats_username or "anonymous"
    bio = connector.get("bio") or ""
    top_language = connector.get("top_language") or ""
    repo_count_raw = _value_or_none("repo_count")
    repo_count = repo_count_raw if isinstance(repo_count_raw, int) else 0

    # Aggregate 365 daily cells into 52 weekly totals for the activity bar chart.
    activity_bars = _build_activity_bars(heatmap_grid)
    activity_peak = max((b["count"] for b in activity_bars), default=0)

    # Heatmap year label — cellular "CONTRIBUTIONS YYYY" caption. Prefer the
    # tail of the heatmap_grid (most recent cell date) so the label stays
    # truthful when the connector returns a back-dated series. Falls back
    # to current calendar year when the grid is empty or unparseable.
    import contextlib
    from datetime import datetime

    heatmap_year = datetime.now(UTC).year
    if heatmap_grid:
        tail = heatmap_grid[-1]
        if isinstance(tail, dict):
            tail_date = tail.get("date")
            if isinstance(tail_date, str) and len(tail_date) >= 4:
                with contextlib.suppress(ValueError):
                    heatmap_year = int(tail_date[:4])

    # Streak rendering: ``"47d"`` for live, ``"—"`` for stale. Don't coerce
    # ``None`` to ``0`` — that's the silent-zero anti-pattern this whole
    # change exists to eliminate.
    streak_display = "—" if streak_days is None else f"{int(streak_days)}d"

    stats_context: dict[str, Any] = {
        "stats_username": username,
        "stats_bio": bio,
        "stats_top_language": top_language,
        "stats_repo_count": repo_count,
        "stats_repo_label": f"{top_language} / {repo_count} repos" if top_language else "",
        "stars_display": _format_count(stars_total),
        "stars_raw": int(stars_total) if isinstance(stars_total, int) else 0,
        "stars_delta_display": stars_delta_display,
        "commits_display": _format_count(commits_total),
        "prs_display": _format_count(prs_total),
        "issues_display": _format_count(issues_total),
        "contrib_display": _format_count(contrib_total),
        "streak_display": streak_display,
        "languages": languages_raw[:4],
        "heatmap_grid": heatmap_grid,
        "stats_heatmap_year": str(heatmap_year),
        "activity_bars": activity_bars,
        "activity_peak": activity_peak,
        "stale_fields": sorted(stale_fields),
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
        # Stale-guard: when ``stars_total`` is ``None`` (sub-fetch failed),
        # the embedded chart is empty too — synthesizing a curve from a
        # known-bad value would compound the silent-zero misrepresentation.
        stars_int = int(stars_total) if isinstance(stars_total, int) else 0
        real_points = connector.get("points") or connector.get("star_history")
        if real_points:
            chart_points: list[dict[str, Any]] = list(real_points)
        elif stars_int > 0 and "stars_total" not in stale_fields:
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
