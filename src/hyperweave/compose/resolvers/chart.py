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

from hyperweave.compose.chart.layout import compute_chart_layout, position_x_labels, position_y_labels
from hyperweave.compose.schema import coerce_chart_input
from hyperweave.render.chart_engine import Viewport, build_chart_svg

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec


# Default milestones for star/download charts. These are resolver-level
# opt-in thresholds; build_chart_svg(None) intentionally emits no milestones.
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

    input_data = coerce_chart_input(spec.connector_data, spec)
    status = input_data.status
    raw_points: list[dict[str, object]] = [point.model_dump() for point in input_data.series_points]
    if status == "empty":
        raw_points = []
        empty_message: str | None = "NEW REPO · NO STARS YET"
    elif status == "stale":
        raw_points = []
        # Cause-aware degradation: state WHY when the connector told us —
        # the retry hint appears only when the upstream sent Retry-After
        # (truthful, never fabricated).
        if input_data.cause == "rate_limited":
            minutes = max(1, round(input_data.retry_seconds / 60)) if input_data.retry_seconds else 0
            empty_message = f"RATE LIMITED · RETRY ~{minutes}M" if minutes else "RATE LIMITED"
        elif input_data.cause == "not_found":
            empty_message = "REPO NOT FOUND"
        elif input_data.cause == "auth_error":
            empty_message = "AUTH · CHECK TOKEN SCOPES"
        else:
            empty_message = "DATA UNAVAILABLE" if input_data.hero.raw_value is None else "HISTORY UNAVAILABLE"
    else:
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

    repo = input_data.identity
    chart_header_label = _chart_header_label(repo=repo, provider=input_data.provider)
    chart_series_title = _chart_series_title(input_data.series_label)
    chart_hero_label = _chart_hero_label(input_data.hero.label)
    chart_hero_suffix = _chart_hero_suffix(hero_label=input_data.hero.label, series_label=input_data.series_label)
    chart_subject_url = _chart_subject_url(
        provider=input_data.provider,
        identity=repo,
        source_url=input_data.source_url,
    )
    chart_layout = (
        compute_chart_layout(chart=paradigm_spec.chart, repo=repo, header_label=chart_header_label)
        if paradigm_spec is not None
        else None
    )
    label_metrics = chart_layout.label_metrics if chart_layout is not None else None
    y_tick_target = paradigm_spec.chart.y_tick_target if paradigm_spec is not None else 4
    milestone_label_y_offset = paradigm_spec.chart.milestone_label_y_offset if paradigm_spec is not None else -24

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
        label_metrics=label_metrics,
        milestone_label_y_offset=milestone_label_y_offset,
    )

    # Hero identity strings shown at top + right of the standalone chart.
    title_upper = (repo or "star history").upper()
    current_display = input_data.hero.value

    # Footer date range — "Mon YYYY — Mon YYYY" bookending the data we actually
    # plotted. Cellular paradigm consumes this; other paradigms ignore it and
    # fall back to repo slug via the template's | default chain. Empty string
    # when we have no points (stale/empty states keep the repo slug).
    date_range = _format_date_range(raw_points)
    chart_subtitle_label = _chart_subtitle_label(input_data.series_label)

    # Primer editorial chart: mixed-case voice + metrics derived from the REAL
    # series (division-safe, schema-agnostic) for the metric triptych footer
    # (CURRENT / DELTA / WINDOW) and the floating glass growth callout — replacing
    # the brutalist milestone annotations the prior pass carried. Other paradigms
    # ignore these context keys.
    def _fmt_compact(n: float) -> str:
        n = abs(n)
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
        if n >= 1_000:
            return f"{n / 1_000:.1f}K".replace(".0K", "K")
        return f"{round(n)}"

    def _num(x: object) -> float:
        try:
            return float(x)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0

    _pt_vals = [(_num(p.get("count")) or _num(p.get("value"))) for p in raw_points]
    _baseline = _pt_vals[0] if _pt_vals else 0.0
    _first_nz = next((v for v in _pt_vals if v > 0), _baseline)
    _last_val = _pt_vals[-1] if _pt_vals else 0.0
    _net = max(0.0, _last_val - _baseline)
    if _first_nz >= 10:
        _delta_pct = round((_last_val - _first_nz) / _first_nz * 100)
        chart_primer_delta = f"+{_delta_pct}%"
        _mult = _last_val / _first_nz
        chart_primer_callout_value = f"{_mult:.0f}\u00d7" if _mult >= 2 else f"+{_fmt_compact(_net)}"
        chart_primer_callout_label = "GROWTH" if _mult >= 2 else "GAINED"
    else:
        chart_primer_delta = f"+{_fmt_compact(_net)}"
        chart_primer_callout_value = f"+{_fmt_compact(_net)}"
        chart_primer_callout_label = "GAINED"

    def _ym(point: dict[str, object]) -> tuple[int, int] | None:
        d = str(point.get("date") or "")
        return (int(d[0:4]), int(d[5:7])) if len(d) >= 7 and d[0:4].isdigit() and d[5:7].isdigit() else None

    _yms = [v for v in (_ym(p) for p in raw_points) if v is not None]
    if len(_yms) >= 2:
        _months = (_yms[-1][0] - _yms[0][0]) * 12 + (_yms[-1][1] - _yms[0][1])
        chart_primer_window = f"{_months}mo" if _months < 24 else f"{_months // 12}y"
    else:
        chart_primer_window = f"{len(raw_points)}pts"
    _series_lc = (input_data.series_label or "trend").strip()
    chart_primer_title = repo or _series_lc
    chart_primer_subtitle = f"{_series_lc} · {date_range}" if date_range else _series_lc
    chart_primer_current = current_display
    # Optional chart-header identity glyph (the provider mark, e.g. github),
    # resolved by the dispatcher and threaded via glyph_data. When present the
    # title shifts right to make room (chart_title_x); else it stays flush left.
    _chart_glyph = _kw.get("glyph_data") or {}
    chart_glyph_path = str(_chart_glyph.get("path", ""))
    chart_glyph_viewbox = str(_chart_glyph.get("viewBox", "") or "0 0 64 64")
    chart_glyph_fill_rule = str(_chart_glyph.get("fill_rule", ""))
    chart_has_glyph = bool(chart_glyph_path)
    chart_glyph_size = 20
    chart_title_x = 132.0 if chart_has_glyph else 100.0

    # Cellular v0.3.0 refresh: surface info_accent / mid_accent / header_band
    # from the variant's primary tone to the template context. info_accent
    # carries the chart title + hero metric color and the polyline drop-shadow
    # glow tint; mid_accent renders axis labels at lower opacity; header_band
    # fills the HUD-style header rect at y=0..header_band_height.
    chart_info_accent = primary_tone.get("info_accent", "") if primary_tone else ""
    chart_mid_accent = primary_tone.get("mid_accent", "") if primary_tone else ""
    chart_header_band = primary_tone.get("header_band", "") if primary_tone else ""
    chart_y_labels = (
        position_y_labels(chart_fragments["y_labels"], chart_layout)
        if chart_layout is not None
        else chart_fragments["y_labels"]
    )
    chart_x_labels = (
        position_x_labels(chart_fragments["x_labels"], chart_layout.x_axis_y)
        if chart_layout is not None
        else chart_fragments["x_labels"]
    )
    # Primer axis accents + vertical gridlines (per the porcelain chart specimen):
    # the top Y-tick label and the trailing (current) X-tick label render in the
    # genome accent, and a vertical gridline drops at every X-tick. Gated by
    # paradigm.chart.axis_accent so other paradigms keep uniform muted ticks and
    # horizontal-only grid (byte-identical).
    # Positioned labels are TextSpec objects (immutable); pass the accent POSITIONS
    # and let the template compare. Top Y-tick = min y (highest on screen); current
    # X-tick = max x (rightmost). Vertical gridlines drop at every X-tick.
    chart_axis_accent = paradigm_spec.chart.axis_accent if paradigm_spec is not None else False
    chart_x_gridlines: list[dict[str, Any]] = []
    chart_accent_y: float | None = None
    chart_accent_x: float | None = None
    if chart_axis_accent and chart_layout is not None and chart_y_labels and chart_x_labels:
        chart_accent_y = min(label.y for label in chart_y_labels)
        chart_accent_x = max(label.x for label in chart_x_labels)
        chart_x_gridlines = [
            {
                "x1": label.x,
                "y1": vp.y,
                "x2": label.x,
                "y2": vp.y + vp.h,
                "accent": label.x == chart_accent_x,
            }
            for label in chart_x_labels
        ]
    identity_font_family = paradigm_spec.chart.identity_font_family if paradigm_spec is not None else "JetBrains Mono"
    identity_font_size = paradigm_spec.chart.identity_font_size if paradigm_spec is not None else 12.0
    identity_font_weight = paradigm_spec.chart.identity_font_weight if paradigm_spec is not None else 700
    identity_letter_spacing_em = paradigm_spec.chart.identity_letter_spacing_em if paradigm_spec is not None else 0.06
    header_identity_text_length = chart_layout.header_identity_text_length if chart_layout is not None else 0.0

    # Profile visual context (envelope/well/specular/chrome text gradients)
    # is injected universally by the dispatcher at resolver.resolve(), so
    # this resolver only builds chart-specific context.
    ctx: dict[str, Any] = {
        "chart_repo": repo,
        "chart_title": title_upper,
        "chart_header_label": chart_header_label,
        "chart_current_stars": current_display,
        "chart_series_title": chart_series_title,
        "chart_hero_label": chart_hero_label,
        "chart_hero_suffix": chart_hero_suffix,
        "chart_subtitle_label": chart_subtitle_label,
        # Primer editorial voice + derived metrics (triptych + glass callout).
        "chart_primer_title": chart_primer_title,
        "chart_primer_subtitle": chart_primer_subtitle,
        "chart_primer_current": chart_primer_current,
        "chart_primer_delta": chart_primer_delta,
        "chart_primer_window": chart_primer_window,
        "chart_primer_callout_value": chart_primer_callout_value,
        "chart_primer_callout_label": chart_primer_callout_label,
        "chart_glyph_path": chart_glyph_path,
        "chart_glyph_viewbox": chart_glyph_viewbox,
        "chart_glyph_fill_rule": chart_glyph_fill_rule,
        "chart_has_glyph": chart_has_glyph,
        "chart_glyph_size": chart_glyph_size,
        "chart_title_x": chart_title_x,
        "chart_subject_url": chart_subject_url,
        "chart_brand_label": f"HYPERWEAVE · {chart_series_title}",
        "hero_label": input_data.hero.label,
        "hero_value": input_data.hero.value,
        "hero_raw_value": input_data.hero.raw_value,
        "identity": input_data.identity,
        "provider_label": input_data.provider,
        "series_points": [point.model_dump() for point in input_data.series_points],
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
        "chart_y_labels": chart_y_labels,
        "chart_x_labels": chart_x_labels,
        "chart_x_gridlines": chart_x_gridlines,
        "chart_axis_accent": chart_axis_accent,
        "chart_accent_y": chart_accent_y,
        "chart_accent_x": chart_accent_x,
        "chart_empty_state": chart_fragments["empty_state"],
        "chart_date_range": date_range,
        "data_hw_status": status,
        "chart_line_animate": line_animate,
        # Cellular paradigm area-fill substrate.
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
        "identity_font_family": identity_font_family,
        "identity_font_size": identity_font_size,
        "identity_font_weight": identity_font_weight,
        "identity_letter_spacing_em": identity_letter_spacing_em,
        "chart_layout": chart_layout,
        "chart_header_identity_text_length": header_identity_text_length,
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


def _chart_header_label(*, repo: str, provider: str) -> str:
    """Compose the chart header identity from project slug and data provider."""
    project = (repo.rsplit("/", 1)[-1] if repo else "project").strip() or "project"
    return f"{project.upper()} · {provider.upper()}"


def _chart_series_title(series_label: str) -> str:
    """Return the visible chart title for a generic time series."""
    label = (series_label or "SERIES").strip().upper()
    if "STAR" in label:
        return "STAR HISTORY"
    if "DOWNLOAD" in label:
        return "DOWNLOAD TREND"
    return f"{label} TREND"


def _chart_hero_label(hero_label: str) -> str:
    """Return the visible hero label for a generic time series."""
    label = (hero_label or "VALUE").strip().upper()
    if label == "STARS":
        return "TOTAL STARS"
    if label.startswith("DOWNLOAD"):
        return f"TOTAL {label}"
    return label


def _chart_hero_suffix(*, hero_label: str, series_label: str) -> str:
    """Return the context-specific hero-label suffix."""
    label = (hero_label or "").strip().upper()
    series = (series_label or "").strip().upper()
    if label == "STARS" or "STAR" in series:
        return " · LIFETIME"
    return ""


def _chart_subtitle_label(series_label: str) -> str:
    """Return the secondary title line without assuming star-history semantics."""
    label = (series_label or "SERIES").strip().upper()
    if "STAR" in label:
        return "LIFETIME GROWTH"
    if "DOWNLOAD" in label:
        return "DOWNLOAD TREND"
    return f"{label} TREND"


def _chart_subject_url(*, provider: str, identity: str, source_url: str = "") -> str:
    """Format a footer source label without assuming GitHub."""
    if source_url:
        return source_url
    primary_provider = provider.split("+", 1)[0]
    if primary_provider == "github":
        return f"github.com/{identity}"
    if primary_provider == "pypi":
        return f"pypi.org/project/{identity}"
    if primary_provider == "huggingface":
        return f"huggingface.co/{identity}"
    if primary_provider == "arxiv":
        return f"arxiv.org/abs/{identity}"
    if primary_provider == "docker":
        return f"hub.docker.com/r/{identity}"
    return identity


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
