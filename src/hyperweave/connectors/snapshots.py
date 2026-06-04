"""Provider snapshots for stats/chart frames.

Scalar connectors return one ``{metric, value}`` result at a time. Snapshot
helpers aggregate a provider's richer API response into the generic
``connector_data`` shape consumed by stats/chart schema coercion.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from urllib.parse import quote

from hyperweave.compose.schema import format_count
from hyperweave.connectors.arxiv import _parse_entry as _parse_arxiv_entry
from hyperweave.connectors.base import fetch_json, fetch_text
from hyperweave.connectors.cache import get_cache

SNAPSHOT_TTL = 1800


async def fetch_hf_snapshot(identifier: str) -> dict[str, Any]:
    """Fetch a Hugging Face model or organization snapshot for stats cards."""
    normalized = identifier.strip()
    if not normalized:
        raise ValueError("Hugging Face snapshot requires an org or org/model identifier")
    cache = get_cache()
    cache_key = f"huggingface:{normalized}:snapshot"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    if "/" in normalized:
        result = await _fetch_hf_model_snapshot(normalized)
    else:
        result = await _fetch_hf_org_snapshot(normalized)
    cache.set(cache_key, result, SNAPSHOT_TTL)
    return result


async def fetch_pypi_snapshot(package: str) -> dict[str, Any]:
    """Fetch PyPI package metadata and PyPIStats downloads for stats/chart frames."""
    normalized = package.strip()
    if not normalized:
        raise ValueError("PyPI snapshot requires a package name")
    cache = get_cache()
    cache_key = f"pypi:{normalized}:snapshot"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    quoted = quote(normalized, safe="")
    metadata = await fetch_json(f"https://pypi.org/pypi/{quoted}/json", provider="pypi")
    # v0.3.13: hero + sparkline share ONE source — the with-mirrors `overall`
    # daily series — so the headline (trailing-30-day sum) and the chart (those
    # same 30 points) reconcile BY CONSTRUCTION. v0.3.12 split them: the hero
    # read recent.last_month (with mirrors, ~6.1M for vllm) while the sparkline
    # read overall?mirrors=false (without mirrors, ~half), so the chart rendered
    # a flat line at half the headline magnitude. with-mirrors is the figure
    # users recognise (pypistats.org / shields PyPI badges). Sourcing both from
    # one series also drops the separate /recent call — a recurring 429 source.
    overall = await fetch_json(
        f"https://pypistats.org/api/packages/{quoted}/overall?mirrors=true",
        provider="pypistats",
    )

    info = _mapping(metadata.get("info") if isinstance(metadata, Mapping) else None)
    series = _download_series(overall.get("data") if isinstance(overall, Mapping) else None)
    recent30 = series[-30:]
    last_month = sum(int(point["count"]) for point in recent30)
    last_day = int(recent30[-1]["count"]) if recent30 else 0
    sparkline_points = _normalized_points([point["count"] for point in recent30])
    peak = max((int(point["count"]) for point in recent30), default=0)

    result: dict[str, Any] = {
        "provider": "pypi",
        "identity": normalized,
        "username": normalized,
        "identity_subtitle": "PyPI package",
        "hero": {
            "label": "DOWNLOADS/MO",
            "value": format_count(last_month),
            "raw_value": last_month,
            "provider": "pypi",
        },
        "metrics": [
            {"label": "VERSION", "value": str(info.get("version") or "unknown"), "provider": "pypi"},
            {"label": "PYTHON", "value": _python_requires(info.get("requires_python")), "provider": "pypi"},
            {"label": "DAILY", "value": format_count(last_day), "raw_value": last_day, "provider": "pypi"},
        ],
        "activity": {
            "type": "sparkline_30d",
            "points": sparkline_points,
            "peak_label": format_count(peak) if peak else "—",
            "peak_value": peak,
        },
        "series_points": series,
        "series_label": "DOWNLOADS",
        "top_language": "Python",
        "source_url": f"https://pypi.org/project/{normalized}/",
        "ttl": SNAPSHOT_TTL,
    }
    cache.set(cache_key, result, SNAPSHOT_TTL)
    return result


async def fetch_arxiv_snapshot(paper_id: str) -> dict[str, Any]:
    """Fetch arXiv paper metadata for stats cards."""
    normalized = paper_id.strip()
    if not normalized:
        raise ValueError("arXiv snapshot requires a paper id")
    cache = get_cache()
    cache_key = f"arxiv:{normalized}:snapshot"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    xml_text = await fetch_text(
        f"https://export.arxiv.org/api/query?id_list={quote(normalized, safe='')}",
        provider="arxiv",
    )
    parsed = _parse_arxiv_entry(xml_text)
    authors = [author for author in _list_of_strings(parsed.get("authors")) if author and author != ":"]
    categories = _list_of_strings(parsed.get("categories"))
    published = _month_year(str(parsed.get("published") or ""))
    title = " ".join(str(parsed.get("title") or normalized).split())
    author_label = _author_label(authors)
    result: dict[str, Any] = {
        "provider": "arxiv",
        "identity": title,
        "username": title,
        "identity_subtitle": normalized,
        "bio": f"{author_label} · {' · '.join(categories[:3])}" if categories else author_label,
        "hero": {"label": "PAPER", "value": normalized, "provider": "arxiv"},
        "metrics": [
            {"label": "AUTHORS", "value": str(len(authors)), "raw_value": len(authors), "provider": "arxiv"},
            {"label": "CATEGORIES", "value": ", ".join(categories[:2]) or "unknown", "provider": "arxiv"},
            {"label": "PUBLISHED", "value": published or "unknown", "provider": "arxiv"},
        ],
        "top_language": categories[0] if categories else "",
        "source_url": f"https://arxiv.org/abs/{normalized}",
        "ttl": SNAPSHOT_TTL,
    }
    cache.set(cache_key, result, SNAPSHOT_TTL)
    return result


def merge_stats_sources(*sources: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge multiple provider snapshots into one stats ``connector_data`` dict."""
    cleaned = [dict(source) for source in sources if source]
    if not cleaned:
        return {}

    merged: dict[str, Any] = dict(cleaned[0])
    metrics = _source_metrics(merged)
    providers: list[str] = []
    for source in cleaned:
        provider = str(source.get("provider") or "")
        if provider and provider not in providers:
            providers.append(provider)

    for source in cleaned[1:]:
        hero_metric = _demote_hero_to_metric(source)
        if hero_metric:
            metrics.append(hero_metric)
        metrics.extend(_source_metrics(source))
        for key in ("activity", "heatmap_grid", "proportional_bar", "language_breakdown", "series_points", "points"):
            if not merged.get(key) and source.get(key):
                merged[key] = source[key]

    merged["metrics"] = metrics[:6]
    if providers:
        merged["provider"] = "+".join(providers)
    return merged


async def _fetch_hf_model_snapshot(identifier: str) -> dict[str, Any]:
    data = await fetch_json(f"https://huggingface.co/api/models/{quote(identifier, safe='/')}", provider="huggingface")
    model = _mapping(data)
    author = str(model.get("author") or identifier.split("/", 1)[0])
    downloads = _int_value(model.get("downloads"))
    likes = _int_value(model.get("likes"))
    siblings_value = model.get("siblings")
    spaces_value = model.get("spaces")
    files = len(siblings_value) if isinstance(siblings_value, list) else 0
    spaces = len(spaces_value) if isinstance(spaces_value, list) else 0
    library = str(model.get("library_name") or model.get("pipeline_tag") or "model")
    return {
        "provider": "huggingface",
        "identity": identifier,
        "username": author,
        "identity_subtitle": library,
        "hero": {
            "label": "DOWNLOADS/MO",
            "value": format_count(downloads),
            "raw_value": downloads,
            "provider": "huggingface",
        },
        "metrics": [
            {"label": "LIKES", "value": format_count(likes), "raw_value": likes, "provider": "huggingface"},
            {"label": "FILES", "value": format_count(files), "raw_value": files, "provider": "huggingface"},
            {"label": "SPACES", "value": format_count(spaces), "raw_value": spaces, "provider": "huggingface"},
        ],
        "top_language": library,
        "source_url": f"https://huggingface.co/{identifier}",
        "ttl": SNAPSHOT_TTL,
    }


async def _fetch_hf_org_snapshot(org: str) -> dict[str, Any]:
    quoted = quote(org, safe="")
    models = await fetch_json(
        f"https://huggingface.co/api/models?author={quoted}&limit=100&expand=downloads&expand=likes",
        provider="huggingface",
    )
    datasets = await fetch_json(
        f"https://huggingface.co/api/datasets?author={quoted}&limit=100",
        provider="huggingface",
    )
    spaces = await fetch_json(f"https://huggingface.co/api/spaces?author={quoted}&limit=100", provider="huggingface")
    model_items = _list_of_mappings(models)
    dataset_items = _list_of_mappings(datasets)
    space_items = _list_of_mappings(spaces)
    downloads = sum(_int_value(item.get("downloads")) for item in model_items)
    likes = sum(_int_value(item.get("likes")) for item in model_items)
    return {
        "provider": "huggingface",
        "identity": org,
        "username": org,
        "identity_subtitle": "Hugging Face org",
        "hero": {
            "label": "DOWNLOADS/MO",
            "value": format_count(downloads),
            "raw_value": downloads,
            "provider": "huggingface",
        },
        "metrics": [
            {"label": "LIKES", "value": format_count(likes), "raw_value": likes, "provider": "huggingface"},
            {
                "label": "MODELS",
                "value": format_count(len(model_items)),
                "raw_value": len(model_items),
                "provider": "huggingface",
            },
            {
                "label": "DATASETS",
                "value": format_count(len(dataset_items)),
                "raw_value": len(dataset_items),
                "provider": "huggingface",
            },
            {
                "label": "SPACES",
                "value": format_count(len(space_items)),
                "raw_value": len(space_items),
                "provider": "huggingface",
            },
        ],
        "top_language": "huggingface",
        "source_url": f"https://huggingface.co/{org}",
        "ttl": SNAPSHOT_TTL,
    }


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _source_metrics(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    provider = str(source.get("provider") or "")
    metrics: list[dict[str, Any]] = []
    for item in _list_of_mappings(source.get("metrics")):
        metric = dict(item)
        if provider and not metric.get("provider"):
            metric["provider"] = provider
        metrics.append(metric)
    return metrics


def _list_of_strings(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.replace(",", "")))
        except ValueError:
            return 0
    return 0


def _download_series(value: object) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    for item in _list_of_mappings(value):
        date = str(item.get("date") or "")
        count = _int_value(item.get("downloads"))
        if date:
            series.append({"date": date, "count": count})
    series.sort(key=lambda point: str(point["date"]))
    return series


def _normalized_points(values: Sequence[int]) -> list[float]:
    peak = max(values, default=0)
    if peak <= 0:
        return [0.0 for _value in values]
    return [round(value / peak, 4) for value in values]


def _python_requires(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"

    parsed = _python_version_bounds(text)
    if parsed is None:
        return text.replace(",", ", ")
    lower, upper = parsed
    if lower and upper:
        lower_op, lower_version = lower
        upper_op, upper_version = upper
        lower_display = lower_version if lower_op == ">=" else f"{lower_op}{lower_version}"
        upper_display = _exclusive_python_upper(upper_version) if upper_op == "<" else upper_version
        if upper_display:
            return f"{lower_display}-{upper_display}"
        return f"{lower_display}-{upper_op}{upper_version}"
    if lower:
        lower_op, lower_version = lower
        return f"{lower_op}{lower_version}"
    if upper:
        upper_op, upper_version = upper
        return f"{upper_op}{upper_version}"
    return text.replace(",", ", ")


def _python_version_bounds(specifier: str) -> tuple[tuple[str, str] | None, tuple[str, str] | None] | None:
    parts = [part.strip() for part in specifier.split(",") if part.strip()]
    if not parts:
        return None
    lower: tuple[str, str] | None = None
    upper: tuple[str, str] | None = None
    for part in parts:
        match = re.fullmatch(r"(<=|>=|<|>|==)\s*([0-9]+(?:\.[0-9]+){0,2})", part)
        if match is None:
            return None
        op, version = match.groups()
        if op in {">=", ">"}:
            lower = (op, version)
        elif op in {"<", "<="}:
            upper = (op, version)
    return lower, upper


def _exclusive_python_upper(version: str) -> str:
    parts = version.split(".")
    if len(parts) < 2:
        return ""
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return ""
    if numbers[-1] <= 0:
        return ""
    numbers[-1] -= 1
    return ".".join(str(number) for number in numbers)


def _month_year(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%b %Y")
    except ValueError:
        return value[:10]


def _author_label(authors: Sequence[str]) -> str:
    if not authors:
        return "arXiv"
    if len(authors) == 1:
        return authors[0]
    return f"{authors[0]} et al."


def _demote_hero_to_metric(source: Mapping[str, Any]) -> dict[str, Any] | None:
    hero = source.get("hero")
    if isinstance(hero, Mapping):
        label = str(hero.get("label") or "").upper()
        value = hero.get("value")
        if label and value is not None:
            return {
                "label": _prefixed_hero_label(str(source.get("provider") or ""), label),
                "value": str(value),
                "raw_value": hero.get("raw_value"),
                "provider": source.get("provider"),
            }
    label = str(source.get("hero_label") or "").upper()
    value = source.get("hero_value")
    if label and value is not None:
        return {
            "label": _prefixed_hero_label(str(source.get("provider") or ""), label),
            "value": str(value),
            "provider": source.get("provider"),
        }
    return None


def _prefixed_hero_label(provider: str, label: str) -> str:
    if provider == "huggingface" and label.startswith("DOWNLOADS"):
        return "HF DL"
    if provider == "pypi" and label.startswith("DOWNLOADS"):
        return "PYPI DL"
    if provider == "npm" and label == "DOWNLOADS":
        return "NPM DL"
    if provider == "docker" and label in {"PULLS", "PULL_COUNT"}:
        return "PULLS"
    if provider == "arxiv":
        return "ARXIV"
    return label
