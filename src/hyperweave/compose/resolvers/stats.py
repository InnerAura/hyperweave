"""Stats card frame resolver — GitHub profile summary.

Consumes ``spec.connector_data`` (produced by ``fetch_user_stats``) and
routes the rendering context to one of the declared stats paradigms:

    brutalist  → brutalist hero-left layout (emerald mockups)
    chrome     → chrome material stack layout

For the ``chrome`` paradigm the resolver also calls the shared chart engine
to produce an embedded compact chart fragment (star history strip) that the
template drops into its bottom zone. This is the mechanism that makes the
stats card a COMPOSITION of stats + chart, not two separate artifacts.
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, Any

from hyperweave.compose.schema import ActivityData, coerce_stats_input, format_count
from hyperweave.compose.stats_layout import compute_stats_card_height, compute_stats_layout
from hyperweave.core.text import measure_text
from hyperweave.render.chart_engine import Viewport, build_chart_svg

if TYPE_CHECKING:
    from hyperweave.compose.stats_layout import StatsLayout
    from hyperweave.core.models import ComposeSpec
    from hyperweave.core.paradigm import ParadigmStatsConfig


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
    return format_count(n)


def _build_activity_bars(activity: ActivityData | None) -> list[dict[str, int]]:
    """Convert normalized activity points into layout bar counts.

    Returns a list of ``{"week": 0..51, "count": N}`` entries.
    """
    if activity is None or activity.type == "sparkline_30d":
        return []
    weeks: list[dict[str, int]] = []
    peak = activity.peak_value if isinstance(activity.peak_value, int | float) else None
    limit = 12 if activity.type == "compact_bars_12w" else 52
    for idx, point in enumerate(activity.points[:limit]):
        count = round(point * peak) if peak and peak > 0 and point <= 1.0 else round(point)
        weeks.append({"week": idx, "count": count})
    return weeks


def _build_activity_sparkline(activity: ActivityData | None, layout: StatsLayout) -> str:
    """Build a compact SVG polyline point string for sparkline activity."""
    if activity is None or activity.type != "sparkline_30d" or not activity.points:
        return ""
    zone = layout.zones["activity"]
    if zone.h <= 0:
        return ""
    x0 = 22.0
    x1 = float(layout.width - 22)
    y0 = zone.y + 24.0
    h = max(10.0, zone.h - 30.0)
    peak = max(activity.points) or 1.0
    points: list[str] = []
    denom = max(1, len(activity.points) - 1)
    for idx, raw in enumerate(activity.points):
        ratio = max(0.0, min(1.0, raw / peak if peak > 1.0 else raw))
        x = x0 + ((x1 - x0) * idx / denom)
        y = y0 + h - (ratio * h)
        points.append(f"{x:.2f},{y:.2f}")
    return " ".join(points)


def _activity_peak_label(activity: ActivityData | None, activity_peak: int) -> str:
    if activity is None:
        return "—"
    if activity.type == "sparkline_30d":
        if activity.peak_label:
            return activity.peak_label.removesuffix(" PEAK")
        if isinstance(activity.peak_value, int | float) and activity.peak_value > 0:
            return format_count(activity.peak_value)
        return "—"
    return f"{activity_peak}/WK" if activity_peak > 0 else "—"


def _layout_metric_entries(
    metrics: list[dict[str, Any]],
    *,
    provider: str,
    metric_layout_mode: str,
) -> list[dict[str, Any]]:
    """Select the metric slots a paradigm is designed to render."""
    if metric_layout_mode == "cellular_inline":
        return metrics

    by_label = {str(metric.get("label") or "").upper(): metric for metric in metrics}
    provider_key = provider.lower()
    is_github_full = (not provider_key or "github" in provider_key) and {"COMMITS", "PRS", "ISSUES", "STREAK"}.issubset(
        by_label
    )
    if is_github_full:
        return [by_label[label] for label in ("COMMITS", "PRS", "ISSUES", "STREAK")]
    if metric_layout_mode == "brutalist_grid":
        return metrics[:4]
    return metrics


def _fit_identity_display(username: str, stats: ParadigmStatsConfig) -> str:
    display = username.upper() if stats.identity_text_transform == "uppercase" else username
    budget = max(0.0, float(stats.bio_x - stats.identity_x - stats.identity_padding))
    if budget <= 0:
        return display
    measured = measure_text(
        display,
        font_family=stats.identity_font_family,
        font_size=stats.identity_font_size,
        font_weight=stats.identity_font_weight,
        letter_spacing_em=stats.identity_letter_spacing_em,
    )
    if measured <= budget:
        return display
    candidate = display
    while len(candidate) > 4:
        text = candidate + "..."
        measured = measure_text(
            text,
            font_family=stats.identity_font_family,
            font_size=stats.identity_font_size,
            font_weight=stats.identity_font_weight,
            letter_spacing_em=stats.identity_letter_spacing_em,
        )
        if measured <= budget:
            return text
        candidate = candidate[:-1]
    return display[:4] + "..."


def _truncate_to_width(
    text: str,
    *,
    budget: float,
    font_family: str,
    font_size: float,
    font_weight: int,
    letter_spacing_em: float,
) -> str:
    """Return ``text`` or a right-truncated ``...`` variant within ``budget``."""
    if not text or budget <= 0:
        return ""
    measured = measure_text(
        text,
        font_family=font_family,
        font_size=font_size,
        font_weight=font_weight,
        letter_spacing_em=letter_spacing_em,
    )
    if measured <= budget:
        return text

    suffix = "..."
    suffix_w = measure_text(
        suffix,
        font_family=font_family,
        font_size=font_size,
        font_weight=font_weight,
        letter_spacing_em=letter_spacing_em,
    )
    if suffix_w > budget:
        return suffix

    lo = 0
    hi = len(text)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid].rstrip()
        display = f"{candidate}{suffix}" if candidate else suffix
        width = measure_text(
            display,
            font_family=font_family,
            font_size=font_size,
            font_weight=font_weight,
            letter_spacing_em=letter_spacing_em,
        )
        if width <= budget:
            best = display
            lo = mid + 1
        else:
            hi = mid - 1
    return best or suffix


def _truncate_subtitle_context(
    *,
    context: dict[str, Any],
    layout: StatsLayout,
    stats: ParadigmStatsConfig,
    full_text: str,
) -> None:
    """Truncate rendered subtitle text before it can bleed past the card edge."""
    if not full_text:
        return

    if stats.metric_layout_mode == "cellular_inline":
        anchor = layout.texts["cellular_bio"].x
        font_size = 8.5
        letter_spacing = 0.03
    elif stats.metric_layout_mode == "brutalist_grid":
        anchor = layout.texts["bio"].x
        font_size = 8.5
        letter_spacing = 0.12
    else:
        return

    edge_budget = max(0.0, float(layout.width) - float(anchor) - 20.0)
    budget = float(layout.bio_text_length) if layout.bio_text_length > 0 else edge_budget
    fitted = _truncate_to_width(
        full_text,
        budget=budget,
        font_family="JetBrains Mono",
        font_size=font_size,
        font_weight=400,
        letter_spacing_em=letter_spacing,
    )
    if fitted != full_text:
        context["stats_repo_label"] = fitted
        context["stats_bio"] = ""
        context["bio_text_length"] = 0.0


def resolve_stats(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    paradigm_spec: Any = None,
    **_kw: Any,
) -> dict[str, Any]:
    """Build the stats card context for the chosen paradigm."""
    input_data = coerce_stats_input(spec.connector_data, spec)
    stale_fields: set[str] = set(input_data.stale_fields)
    stale = input_data.status == "stale"
    metric_by_label = {metric.label.upper(): metric for metric in input_data.metrics}

    def _metric_display(label: str) -> str:
        metric = metric_by_label.get(label)
        return metric.value if metric is not None else "—"

    def _raw_int(value: int | float | None) -> int:
        return int(value) if isinstance(value, int | float) else 0

    hero_raw_value = input_data.hero.raw_value
    username = input_data.identity
    bio = input_data.bio
    top_language = input_data.top_language
    repo_count = input_data.repo_count
    languages_raw = [{"name": segment.label, "pct": segment.pct} for segment in input_data.proportional_bar]
    heatmap_grid = [cell.model_dump() for cell in input_data.heatmap]
    activity_bars = _build_activity_bars(input_data.activity)
    activity_peak = max((b["count"] for b in activity_bars), default=0)
    activity_peak_label = _activity_peak_label(input_data.activity, activity_peak)
    activity_type = input_data.activity.type if input_data.activity is not None else ""
    metric_entries = [metric.model_dump() for metric in input_data.metrics]

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

    streak_display = _metric_display("STREAK")

    # Cellular v0.3.0 refresh: surface paradigm constants (genome-independent)
    # and per-tone accent stops. Constants flow as named template variables
    # so the variant-blind hex gate stays effective and overrides apply via
    # paradigm config rather than hex spelunking. Cellular palette (info_accent
    # / mid_accent / header_band) injected by the dispatcher via _kw.
    cellular_palette: dict[str, Any] = _kw.get("cellular_palette") or {}
    primary_tone: dict[str, Any] = cellular_palette.get("primary") or {}
    stats_info_accent = primary_tone.get("info_accent", "")
    stats_mid_accent = primary_tone.get("mid_accent", "")
    stats_header_band = primary_tone.get("header_band", "")

    if paradigm_spec is not None:
        ps = paradigm_spec.stats
        streak_green = ps.streak_green
        mid_gray = ps.mid_gray
        hero_white = ps.hero_white
        header_band_height = int(ps.header_band_height)
        heatmap_rows = int(ps.heatmap_rows) if ps.heatmap_rows else 0
        heatmap_cols = int(ps.heatmap_cols) if ps.heatmap_cols else 0
        heatmap_cell_size = float(ps.heatmap_cell_size) if ps.heatmap_cell_size else 0.0
        heatmap_cell_gap = float(ps.heatmap_cell_gap) if ps.heatmap_cell_gap else 0.0
        heatmap_zone_height = float(ps.heatmap_zone_height) if ps.heatmap_zone_height else 0.0
    else:
        streak_green = ""
        mid_gray = ""
        hero_white = ""
        header_band_height = 0
        heatmap_rows = 0
        heatmap_cols = 0
        heatmap_cell_size = 0.0
        heatmap_cell_gap = 0.0
        heatmap_zone_height = 0.0

    stats_context: dict[str, Any] = {
        "stats_username": username,
        "stats_bio": bio,
        "stats_top_language": top_language,
        "stats_repo_count": repo_count,
        "stats_repo_label": input_data.identity_subtitle,
        "stars_display": input_data.hero.value,
        "stars_raw": _raw_int(hero_raw_value),
        "commits_display": _metric_display("COMMITS"),
        "prs_display": _metric_display("PRS"),
        "issues_display": _metric_display("ISSUES"),
        "contrib_display": _metric_display("CONTRIB"),
        "streak_display": streak_display,
        "languages": languages_raw[:4],
        "heatmap_grid": heatmap_grid,
        "stats_heatmap_year": str(heatmap_year),
        "activity_bars": activity_bars,
        "activity_peak": activity_peak,
        "activity_peak_label": activity_peak_label,
        "stale_fields": sorted(stale_fields),
        # v0.3.0 cellular refresh — paradigm constants + per-tone accents.
        "stats_info_accent": stats_info_accent,
        "stats_mid_accent": stats_mid_accent,
        "stats_header_band": stats_header_band,
        "streak_green": streak_green,
        "mid_gray": mid_gray,
        "hero_white": hero_white,
        "stats_header_band_height": header_band_height,
        "heatmap_rows": heatmap_rows,
        "heatmap_cols": heatmap_cols,
        "heatmap_cell_size": heatmap_cell_size,
        "heatmap_cell_gap": heatmap_cell_gap,
        "heatmap_zone_height": heatmap_zone_height,
        "hero_label": input_data.hero.label,
        "hero_caption": _stats_hero_caption(input_data.hero.label),
        "hero_value": input_data.hero.value,
        "hero_raw_value": input_data.hero.raw_value,
        "identity": input_data.identity,
        "identity_subtitle": input_data.identity_subtitle,
        "provider_label": input_data.provider,
        "subject_url": _stats_subject_url(
            provider=input_data.provider,
            identity=input_data.identity,
            source_url=input_data.source_url,
        ),
        "metric_slots": [metric.model_dump() for metric in input_data.metrics],
        "activity": input_data.activity.model_dump() if input_data.activity is not None else None,
        "proportional_bar": [segment.model_dump() for segment in input_data.proportional_bar],
        "series_points": [point.model_dump() for point in input_data.series_points],
    }
    if paradigm_spec is not None:
        stats_context.update(
            {
                "identity_font_family": paradigm_spec.stats.identity_font_family,
                "identity_font_size": paradigm_spec.stats.identity_font_size,
                "identity_font_weight": paradigm_spec.stats.identity_font_weight,
                "identity_letter_spacing_em": paradigm_spec.stats.identity_letter_spacing_em,
            }
        )

    if stale:
        stats_context["data_hw_status"] = "stale"
        stats_context["status"] = "stale"

    # Profile visual context (envelope/well/chrome+hero text gradients) is
    # now injected universally by the dispatcher at resolver.resolve(), so
    # per-frame resolvers no longer need to call _genome_material_context.

    if paradigm_spec is not None and paradigm_spec.stats.card_width > 0:
        card_width = paradigm_spec.stats.card_width
    else:
        card_width = _STATS_WIDTH
    stats_cfg = paradigm_spec.stats if paradigm_spec is not None else None
    layout_metric_entries = (
        _layout_metric_entries(
            metric_entries,
            provider=input_data.provider,
            metric_layout_mode=stats_cfg.metric_layout_mode,
        )
        if stats_cfg is not None
        else metric_entries
    )
    if stats_cfg is not None:
        if stats_cfg.metric_layout_mode == "cellular_inline":
            display_username = _fit_identity_display(username, stats_cfg)
        else:
            display_username = username
        stats_context["stats_username"] = display_username
        card_height = compute_stats_card_height(
            stats=stats_cfg,
            metric_count=len(layout_metric_entries),
            activity_type=activity_type,
            has_activity=input_data.activity is not None,
            has_heatmap=bool(input_data.heatmap),
            has_proportional_bar=bool(input_data.proportional_bar),
        )
    else:
        card_height = 260
    if stats_cfg is not None:
        repo_label_str = input_data.identity_subtitle or (
            f"{top_language} / {repo_count} repos" if top_language else ""
        )
        bio_full = f"{repo_label_str} · {bio}" if repo_label_str and bio else repo_label_str or bio
        area_tiers_obj = primary_tone.get("area_tiers", []) if primary_tone else []
        area_tiers = [str(color) for color in area_tiers_obj] if isinstance(area_tiers_obj, list) else []
        stats_layout = compute_stats_layout(
            stats=stats_cfg,
            card_width=card_width,
            card_height=card_height,
            username=display_username,
            bio_text=bio_full,
            displays={
                "stars": stats_context["stars_display"],
                "commits": stats_context["commits_display"],
                "prs": stats_context["prs_display"],
                "issues": stats_context["issues_display"],
                "contrib": stats_context["contrib_display"],
                "streak": stats_context["streak_display"],
            },
            metric_entries=layout_metric_entries,
            hero_label=input_data.hero.label,
            activity_bars=activity_bars,
            activity_peak=activity_peak,
            activity_type=activity_type,
            languages=languages_raw[:4],
            heatmap_grid=heatmap_grid,
            area_tiers=area_tiers,
            has_activity=input_data.activity is not None,
            has_heatmap=bool(input_data.heatmap),
            has_proportional_bar=bool(input_data.proportional_bar),
            substrate_kind=str(genome.get("substrate_kind") or "dark"),
        )
        stats_context.update(
            {
                "stats_layout": stats_layout,
                "identity_x": stats_layout.identity_x,
                "bio_x": stats_layout.bio_x,
                "identity_text_length": stats_layout.identity_text_length,
                "bio_text_length": stats_layout.bio_text_length,
                "metric_layouts": stats_layout.metric_slots,
                "metric_y": stats_layout.metric_slots[0].value_y if stats_layout.metric_slots else 0.0,
                "activity_bar_layouts": stats_layout.activity_bars,
                "language_segments": stats_layout.language_segments,
                "language_layout": stats_layout.inline_language_entries,
                "heatmap_cells": stats_layout.heatmap_cells,
                "heatmap_legend_cells": stats_layout.heatmap_legend_cells,
                "activity_sparkline_polyline": _build_activity_sparkline(input_data.activity, stats_layout),
                "stats_brand_x": card_width - 20,
                "commits_text_length": stats_layout.commits_text_length,
                "prs_text_length": stats_layout.prs_text_length,
                "issues_text_length": stats_layout.issues_text_length,
                "streak_text_length": stats_layout.streak_text_length,
            }
        )
        _truncate_subtitle_context(
            context=stats_context,
            layout=stats_layout,
            stats=stats_cfg,
            full_text=bio_full,
        )

    # Embedded compact chart — enablement flag + viewport sourced from
    # paradigm YAML. Chrome paradigm embeds; brutalist does not. Zero
    # string comparisons in Python; adding a new paradigm that also wants
    # an embed is purely a YAML change.
    embeds_chart = bool(paradigm_spec.stats.embeds_chart) if paradigm_spec is not None else False
    if embeds_chart:
        ec = paradigm_spec.stats
        embed_vp = Viewport(x=ec.embed_viewport_x, y=ec.embed_viewport_y, w=ec.embed_viewport_w, h=ec.embed_viewport_h)
        # Zero-guard: never default to a 1200-star synthetic curve. When
        # the hero metric is zero, the truthful state is an empty embedded chart.
        # Stale-guard: when the hero metric is ``None`` (sub-fetch failed),
        # the embedded chart is empty too — synthesizing a curve from a
        # known-bad value would compound the silent-zero misrepresentation.
        stars_int = _raw_int(hero_raw_value)
        real_points = [point.model_dump() for point in input_data.series_points]
        if real_points:
            chart_points: list[dict[str, Any]] = list(real_points)
        elif stars_int > 0 and hero_raw_value is not None:
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

    return {
        "width": card_width,
        "height": card_height,
        "template": "frames/stats.svg.j2",
        "context": stats_context,
    }


def _stats_hero_caption(hero_label: str) -> str:
    label = (hero_label or "STARS").strip().upper()
    if label == "STARS":
        return "TOTAL STARS · LIFETIME"
    if label in {"DOWNLOADS/MO", "DOWNLOADS/MONTH", "DOWNLOADS MONTHLY"}:
        return "DOWNLOADS · MONTHLY"
    return label


def _stats_subject_url(*, provider: str, identity: str, source_url: str = "") -> str:
    if source_url:
        return source_url
    primary_provider = provider.split("+", 1)[0]
    if primary_provider == "github":
        return f"github.com/{identity.lower()}"
    if primary_provider == "pypi":
        return f"pypi.org/project/{identity}"
    if primary_provider == "huggingface":
        return f"huggingface.co/{identity}"
    if primary_provider == "arxiv":
        return f"arxiv.org/abs/{identity}"
    if primary_provider == "docker":
        return f"hub.docker.com/r/{identity}"
    return identity


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
