"""arXiv connector."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from hyperweave.connectors.base import fetch_text
from hyperweave.connectors.cache import get_cache

PROVIDER = "arxiv"
CACHE_TTL = 1800

# Atom namespace used by arXiv API responses
_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"


def _parse_entry(xml_text: str) -> dict[str, Any]:
    root = ET.fromstring(xml_text)

    entry = root.find(f"{{{_ATOM_NS}}}entry")
    if entry is None:
        raise ValueError("No entry found in arXiv response")

    def _text(tag: str, ns: str = _ATOM_NS) -> str:
        el = entry.find(f"{{{ns}}}{tag}")
        return (el.text or "").strip() if el is not None else ""

    # Authors are repeated <author><name> elements
    authors: list[str] = []
    for author_el in entry.findall(f"{{{_ATOM_NS}}}author"):
        name_el = author_el.find(f"{{{_ATOM_NS}}}name")
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())

    # Categories from <category term="..."/>
    categories: list[str] = []
    for cat_el in entry.findall(f"{{{_ATOM_NS}}}category"):
        term = cat_el.get("term", "")
        if term:
            categories.append(term)

    return {
        "title": _text("title"),
        "authors": authors,
        "published": _text("published"),
        "categories": categories,
        "summary": _text("summary"),
    }


async def fetch_metric(identifier: str, metric: str) -> dict[str, Any]:
    """Fetch a single metric from arXiv."""
    cache = get_cache()
    cache_key = f"{PROVIDER}:{identifier}:{metric}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    url = f"https://export.arxiv.org/api/query?id_list={identifier}"
    xml_text = await fetch_text(url, provider=PROVIDER)

    parsed = _parse_entry(xml_text)

    if metric not in parsed:
        raise ValueError(f"Unknown arXiv metric {metric!r}. Available: {sorted(parsed)}")

    value = parsed[metric]

    result: dict[str, Any] = {
        "provider": PROVIDER,
        "identifier": identifier,
        "metric": metric,
        "value": value,
        "ttl": CACHE_TTL,
    }
    cache.set(cache_key, result, CACHE_TTL)
    return result
