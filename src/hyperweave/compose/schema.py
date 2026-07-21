"""Normalized connector input contracts for frame resolvers.

Connectors intentionally return provider-shaped dictionaries. Resolver code
coerces those dictionaries here, at the compose boundary, so templates and
layout code never need to know connector-specific field names.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import Field

from hyperweave.core.models import ComposeSpec, FrozenModel

FrameStatus = Literal["fresh", "stale", "empty"]
ActivityType = Literal["bars_52w", "sparkline_30d", "compact_bars_12w"]
DeltaDirection = Literal["up", "down", "neutral"]


class MetricSlot(FrozenModel):
    """Display-ready metric with optional raw numeric value."""

    label: str
    value: str
    delta: str | None = None
    raw_value: int | float | None = None
    emphasis: str | None = None


class StripMetricSlot(MetricSlot):
    """Strip metric slot with directional state."""

    delta_dir: DeltaDirection = "neutral"
    state: str = ""


class ProportionalSegment(FrozenModel):
    """A proportional segment such as a language share."""

    label: str
    pct: float


class SeriesPoint(FrozenModel):
    """A single time-series point."""

    date: str
    count: int | float


class HeatmapCellInput(FrozenModel):
    """Contribution heatmap cell normalized from connector data."""

    date: str = ""
    count: int = 0
    level: int = 0


class ActivityData(FrozenModel):
    """Normalized activity data for stats sub-zones."""

    type: ActivityType
    points: list[float]
    peak_label: str | None = None
    peak_value: int | float | None = None


class FrameInput(FrozenModel):
    """Base contract shared by connector-consuming frames."""

    hero: MetricSlot
    identity: str
    identity_subtitle: str = ""
    provider: str = ""
    source_url: str = ""
    status: FrameStatus = "fresh"


class StatsInput(FrameInput):
    """Normalized stats-card input."""

    metrics: list[MetricSlot] = Field(default_factory=list)
    bio: str = ""
    top_language: str = ""
    repo_count: int = 0
    stale_fields: list[str] = Field(default_factory=list)
    activity: ActivityData | None = None
    heatmap: list[HeatmapCellInput] = Field(default_factory=list)
    proportional_bar: list[ProportionalSegment] = Field(default_factory=list)
    series_points: list[SeriesPoint] = Field(default_factory=list)
    metric_layout: Literal["inline"] = "inline"


class ChartInput(FrameInput):
    """Normalized chart-frame input."""

    series_points: list[SeriesPoint] = Field(default_factory=list)
    series_label: str = ""
    cause: str = ""
    """Connector failure cause (rate_limited | not_found | auth_error |
    upstream_error) — empty when data arrived. Rides beside the 3-state
    ``status`` contract, never replaces it."""
    retry_seconds: int = 0
    """Upstream Retry-After when the cause is a rate limit; 0 = no hint."""


class StripInput(FrameInput):
    """Normalized strip-frame input."""

    metrics: list[StripMetricSlot] = Field(default_factory=list)


def format_count(value: object) -> str:
    """Format a count using HyperWeave compact display rules."""
    number = _number(value)
    if number is None:
        return "—"
    if number <= 0:
        return "0"
    if number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.1f}B".rstrip("0").rstrip(".")
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M".rstrip("0").rstrip(".")
    if number >= 10_000:
        return f"{number / 1_000:.1f}K".rstrip("0").rstrip(".")
    return f"{int(number):,}"


def coerce_stats_input(connector_data: Mapping[str, object] | None, spec: ComposeSpec) -> StatsInput:
    """Coerce provider-shaped stats connector data into ``StatsInput``."""
    raw = connector_data or {}
    token_metrics = _metrics_from_tokens(spec.data_tokens)
    stale_fields = _stale_fields(raw)
    status: FrameStatus = "stale" if (not raw and not token_metrics) or stale_fields else "fresh"

    explicit_hero = _explicit_hero(raw, default_label="STARS")
    if explicit_hero is not None:
        hero = explicit_hero
    else:
        stars_raw = _value_or_none(raw, stale_fields, "stars_total", "current_stars")
        if (
            _present(stars_raw)
            or "stars_total" in raw
            or "current_stars" in raw
            or stale_fields.intersection({"stars_total", "current_stars"})
        ):
            hero = MetricSlot(label="STARS", value=format_count(stars_raw), raw_value=_number(stars_raw))
        elif token_metrics:
            hero = token_metrics[0]
            token_metrics = token_metrics[1:]
        else:
            hero = MetricSlot(label="STARS", value="—", raw_value=None)

    username = _string(_first(raw, "identity", "username"), spec.stats_username or spec.title or "anonymous")
    top_language = _string(_first(raw, "top_language"), "")
    repo_count_raw = _value_or_none(raw, stale_fields, "repo_count")
    repo_count = int(_number(repo_count_raw) or 0)
    subtitle = _string(_first(raw, "identity_subtitle"), "")
    if not subtitle and top_language:
        subtitle = f"{top_language} / {repo_count} repos"

    metrics = [*_stats_metrics(raw, stale_fields), *token_metrics][:6]
    heatmap = _heatmap(raw.get("heatmap_grid"))
    activity = _activity(raw.get("activity"), heatmap)
    proportional = _proportional_segments(_first(raw, "language_breakdown", "proportional_bar", "languages"))
    series_points = _series_points(_first(raw, "series_points", "points", "star_history"))

    return StatsInput(
        hero=hero,
        identity=username,
        identity_subtitle=subtitle,
        provider=_combined_provider(raw, spec.data_tokens),
        source_url=_source_url(raw),
        status=status,
        metrics=metrics,
        bio=_string(_first(raw, "bio"), ""),
        top_language=top_language,
        repo_count=repo_count,
        stale_fields=sorted(stale_fields),
        activity=activity,
        heatmap=heatmap,
        proportional_bar=proportional,
        series_points=series_points,
    )


def coerce_chart_input(connector_data: Mapping[str, object] | None, spec: ComposeSpec) -> ChartInput:
    """Coerce provider-shaped chart connector data into ``ChartInput``."""
    raw = connector_data or {}
    explicit_hero = _explicit_hero(raw, default_label="STARS")
    if explicit_hero is None:
        stars_raw = _first(raw, "current_stars", "stars_total")
        stars_number = _number(stars_raw)
        hero = MetricSlot(label="STARS", value=format_count(stars_raw), raw_value=stars_number)
    else:
        hero = explicit_hero
        stars_number = hero.raw_value
    series_points = _series_points(_first(raw, "series_points", "points", "star_history"))

    if connector_data is None:
        status: FrameStatus = "stale"
    elif not series_points and hero.label == "STARS" and stars_number == 0:
        status = "empty"
    elif not series_points:
        status = "stale"
    else:
        status = "fresh"

    identity = _string(_first(raw, "identity", "username", "repo"), f"{spec.chart_owner}/{spec.chart_repo}".strip("/"))
    if not identity:
        identity = "star history"

    return ChartInput(
        hero=hero,
        identity=identity,
        provider=_combined_provider(raw, spec.data_tokens),
        source_url=_source_url(raw),
        status=status,
        series_points=series_points,
        series_label=_string(_first(raw, "series_label"), hero.label),
        cause=_string(_first(raw, "cause"), ""),
        retry_seconds=int(_number(_first(raw, "retry_seconds")) or 0),
    )


def coerce_strip_input(connector_data: Mapping[str, object] | None, spec: ComposeSpec) -> StripInput:
    """Coerce strip connector aliases and metric slots into ``StripInput``."""
    raw = connector_data or {}
    metrics = _strip_metrics(spec)
    hero = metrics[0] if metrics else StripMetricSlot(label="", value="")
    subtitle = _string(_first(raw, "repo_slug", "repo", "identity_subtitle"), "")

    return StripInput(
        hero=hero,
        identity=spec.title or "",
        identity_subtitle=subtitle,
        provider=_provider(raw),
        source_url=_source_url(raw),
        status="fresh" if raw else "empty",
        metrics=metrics,
    )


def stats_metric_map(input_data: StatsInput) -> dict[str, MetricSlot]:
    """Return stats metrics keyed by lowercase label for resolver compatibility."""
    return {metric.label.lower(): metric for metric in input_data.metrics}


def _stats_metrics(raw: Mapping[str, object], stale_fields: set[str]) -> list[MetricSlot]:
    explicit = _metrics_from_raw(raw.get("metrics"))
    if explicit:
        return explicit

    fields: tuple[tuple[str, str], ...] = (
        ("COMMITS", "commits_total"),
        ("PRS", "prs_total"),
        ("ISSUES", "issues_total"),
        ("CONTRIB", "contrib_total"),
        ("STREAK", "streak_days"),
    )
    metrics: list[MetricSlot] = []
    for label, field in fields:
        if field not in raw and field not in stale_fields:
            continue
        raw_value = _value_or_none(raw, stale_fields, field)
        display = _format_streak(raw_value) if field == "streak_days" else format_count(raw_value)
        metrics.append(MetricSlot(label=label, value=display, raw_value=_number(raw_value)))
    return metrics


def _strip_metrics(spec: ComposeSpec) -> list[StripMetricSlot]:
    metrics: list[StripMetricSlot] = []
    for slot in spec.slots:
        if not slot.zone.startswith("metric"):
            continue
        parts = slot.value.split(":", 1) if ":" in slot.value else [slot.zone, slot.value]
        label = parts[0].upper()
        value = parts[1] if len(parts) > 1 else slot.value
        state = ""
        if slot.zone == "metric-state":
            state = str((slot.data or {}).get("state", spec.state))
        metrics.append(StripMetricSlot(label=label, value=value, delta="", delta_dir="neutral", state=state))

    if not metrics and spec.value:
        for pair in spec.value.split(","):
            pair = pair.strip()
            if ":" not in pair:
                continue
            label, value = pair.split(":", 1)
            metrics.append(
                StripMetricSlot(
                    label=label.strip().upper(),
                    value=value.strip(),
                    delta="",
                    delta_dir="neutral",
                    state="",
                )
            )
    return metrics


def _metrics_from_raw(value: object) -> list[MetricSlot]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    metrics: list[MetricSlot] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        label = _string(item.get("label"), "").upper()
        display = _string(item.get("value"), "")
        if not label or not display:
            continue
        raw_value = _number(item.get("raw_value"))
        metrics.append(
            MetricSlot(
                label=label,
                value=display,
                delta=_optional_string(item.get("delta")),
                raw_value=raw_value,
            )
        )
    return metrics


def _explicit_hero(raw: Mapping[str, object], *, default_label: str) -> MetricSlot | None:
    value = raw.get("hero")
    if isinstance(value, Mapping):
        label = _string(value.get("label"), default_label).upper()
        display = _string(value.get("value"), "")
        raw_value = _number(_first(value, "raw_value", "count"))
        if not display and raw_value is not None:
            display = format_count(raw_value)
        if display:
            return MetricSlot(label=label, value=display, raw_value=raw_value)

    label = _string(_first(raw, "hero_label"), default_label).upper()
    display_value = _first(raw, "hero_value")
    raw_value_obj = _first(raw, "hero_raw_value")
    if not _present(display_value) and not _present(raw_value_obj) and "hero_label" not in raw:
        return None
    raw_number = _number(raw_value_obj if _present(raw_value_obj) else display_value)
    display = _string(display_value, "") if _present(display_value) else format_count(raw_number)
    return MetricSlot(label=label, value=display or "—", raw_value=raw_number)


def _metrics_from_tokens(value: object) -> list[MetricSlot]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    metrics: list[MetricSlot] = []
    for item in value:
        kind = _string(getattr(item, "kind", ""), "")
        if kind == "text":
            continue
        label = _stats_token_label(item)
        display = _string(getattr(item, "value", ""), "")
        if not label or not display:
            continue
        raw_value = _number(getattr(item, "raw_value", None))
        metrics.append(
            MetricSlot(
                label=label,
                value=format_count(raw_value) if raw_value is not None else display,
                raw_value=raw_value,
            )
        )
    return metrics


def _stats_token_label(token: object) -> str:
    kind = _string(getattr(token, "kind", ""), "")
    if kind == "kv":
        return _string(getattr(token, "label", ""), "").upper()
    provider = _normalize_provider(_string(getattr(token, "provider", ""), ""))
    metric = _string(getattr(token, "metric", ""), "").lower()
    display = _string(getattr(token, "label", ""), metric.upper()).upper()
    if provider == "github":
        return f"GH {display}"
    if provider == "pypi":
        return "PYPI DL" if metric == "downloads" else f"PYPI {display}"
    if provider == "npm":
        return "NPM DL" if metric == "downloads" else f"NPM {display}"
    if provider == "huggingface":
        if metric == "downloads":
            return "HF DL"
        if metric == "likes":
            return "HF LIKES"
        return f"HF {display}"
    if provider == "docker":
        return "PULLS" if metric == "pull_count" else f"DOCKER {display}"
    if provider == "arxiv":
        if metric == "title":
            return "PAPER"
        if metric == "categories":
            return "ARXIV CAT"
        return f"ARXIV {display}"
    return display


def _series_points(value: object) -> list[SeriesPoint]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    points: list[SeriesPoint] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        date = _string(item.get("date"), "")
        count = _number(item.get("count"))
        if not date or count is None:
            continue
        points.append(SeriesPoint(date=date, count=count))
    return points


def _heatmap(value: object) -> list[HeatmapCellInput]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    cells: list[HeatmapCellInput] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        count = int(_number(item.get("count")) or 0)
        level = int(_number(item.get("level")) or 0)
        cells.append(HeatmapCellInput(date=_string(item.get("date"), ""), count=count, level=level))
    return cells


def _activity(value: object, heatmap: Sequence[HeatmapCellInput]) -> ActivityData | None:
    if isinstance(value, Mapping):
        activity_type = _activity_type(value.get("type"))
        points = _float_points(value.get("points"))
        if points:
            peak_value = _number(value.get("peak_value"))
            return ActivityData(
                type=activity_type,
                points=points,
                peak_label=_optional_string(value.get("peak_label")),
                peak_value=peak_value,
            )

    if not heatmap:
        return None

    weekly_counts: list[float] = []
    for idx in range(0, len(heatmap), 7):
        weekly_counts.append(float(sum(cell.count for cell in heatmap[idx : idx + 7])))
    weekly_counts = weekly_counts[:52]
    peak = max(weekly_counts, default=0.0)
    if peak <= 0:
        return ActivityData(type="bars_52w", points=[0.0 for _ in weekly_counts], peak_label="0/WK PEAK", peak_value=0)
    points = [round(count / peak, 4) for count in weekly_counts]
    return ActivityData(type="bars_52w", points=points, peak_label=f"{int(peak)}/WK PEAK", peak_value=peak)


def _activity_type(value: object) -> ActivityType:
    if value == "sparkline_30d":
        return "sparkline_30d"
    if value == "compact_bars_12w":
        return "compact_bars_12w"
    return "bars_52w"


def _float_points(value: object) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    points: list[float] = []
    for item in value:
        number = _number(item)
        if number is not None:
            points.append(float(number))
    return points


def _proportional_segments(value: object) -> list[ProportionalSegment]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    segments: list[ProportionalSegment] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        label = _string(_first(item, "label", "name"), "")
        pct = _number(item.get("pct"))
        if label and pct is not None:
            segments.append(ProportionalSegment(label=label, pct=float(pct)))
    return segments


def _provider(raw: Mapping[str, object]) -> str:
    direct = _string(_first(raw, "provider", "source", "provider_source", "platform"), "")
    if direct:
        return _normalize_provider(direct)
    for key in ("url", "html_url", "repo_url", "source_url"):
        value = _string(raw.get(key), "").lower()
        if "huggingface.co" in value:
            return "huggingface"
        if "github.com" in value:
            return "github"
    return "github"


def _source_url(raw: Mapping[str, object]) -> str:
    return _string(_first(raw, "source_url", "url", "html_url", "repo_url"), "")


def _combined_provider(raw: Mapping[str, object], tokens: object) -> str:
    providers: list[str] = []
    if raw:
        providers.append(_provider(raw))
    for provider in _token_providers(tokens):
        if provider not in providers:
            providers.append(provider)
    return "+".join(providers) if providers else "github"


def _token_providers(tokens: object) -> list[str]:
    if not isinstance(tokens, Sequence) or isinstance(tokens, str | bytes | bytearray):
        return []
    providers: list[str] = []
    for token in tokens:
        provider = _normalize_provider(_string(getattr(token, "provider", ""), ""))
        if provider and provider not in providers:
            providers.append(provider)
    return providers


def _normalize_provider(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"gh", "github", "github-core", "github-graphql"}:
        return "github"
    if lowered in {"hf", "huggingface", "hugging-face"}:
        return "huggingface"
    return lowered


def _stale_fields(raw: Mapping[str, object]) -> set[str]:
    value = raw.get("_stale_fields")
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return set()
    return {str(item) for item in value}


def _value_or_none(raw: Mapping[str, object], stale_fields: set[str], *keys: str) -> object:
    for key in keys:
        if key in stale_fields:
            return None
        value = raw.get(key)
        if _present(value):
            return value
    return None


def _first(raw: Mapping[str, object], *keys: str) -> object:
    for key in keys:
        value = raw.get(key)
        if _present(value):
            return value
    return None


def _present(value: object) -> bool:
    return value is not None and value != ""


def _string(value: object, default: str) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    if isinstance(value, int | float):
        return str(value)
    return default


def _optional_string(value: object) -> str | None:
    text = _string(value, "")
    return text if text else None


def _number(value: object) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", "")
    if not text:
        return None
    multiplier = 1.0
    suffix = text[-1:].lower()
    if suffix == "k":
        multiplier = 1_000.0
        text = text[:-1]
    elif suffix == "m":
        multiplier = 1_000_000.0
        text = text[:-1]
    elif suffix == "b":
        multiplier = 1_000_000_000.0
        text = text[:-1]
    try:
        number = float(text) * multiplier
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _format_streak(value: object) -> str:
    number = _number(value)
    if number is None:
        return "—"
    return f"{int(number)}d"
