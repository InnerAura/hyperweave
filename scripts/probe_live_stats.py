"""Live probe: detect the silent-zero regression in deployed stats cards.

Fetches the live stats endpoint, parses the rendered SVG, and asserts the
post-fix invariants:

* If the user has any non-zero signal (stars or contributions), the four
  metric columns (COMMITS, PRS, ISSUES, STREAK) must NOT all be ``0``.
  Multiple zeros next to a real-looking stars total is the v0.2.10
  silent-zero shape — that is exactly what this probe is here to catch.

* ``data-hw-status="stale"`` is acceptable transiently (a search-API
  burst hit the breaker). It is **not** acceptable persistently — if
  back-to-back probes both show ``stale``, something is keeping the
  failure-cache hot longer than the 30s ``FAILURE_CACHE_TTL``.

Usage:
    uv run python scripts/probe_live_stats.py [endpoint] [user/genome.variant]

Defaults probe https://hyperweave.app against ``eli64s/chrome.static``.
Exit code 0 on pass, 1 on fail (suspicious-zero, missing markers, HTTP error).
A ``stale`` marker emits a warning but does not fail the probe on a single run.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time

import httpx

DEFAULT_ENDPOINT = "https://hyperweave.app"
DEFAULT_TARGET = "eli64s/chrome.static"

# Anchor on the label text — both paradigms emit <text>LABEL</text> followed
# immediately by the value text element. Chrome uses data-hw-zone + mval
# class; brutalist uses paradigm-specific class names. The label-anchored
# pattern works for both without paradigm-aware branches.
_METRIC_LABELS = ("COMMITS", "PRS", "ISSUES", "STREAK")
_METRIC_RE = re.compile(
    r">(" + "|".join(_METRIC_LABELS) + r")</text>\s*<text[^>]*>([^<]+)</text>",
    re.DOTALL,
)
# Hero stars: chrome marks it with data-hw-zone="hero-value", brutalist
# with a class ending in "-hero-value". Match either to stay paradigm-blind.
_HERO_RE = re.compile(
    r'(?:data-hw-zone="hero-value"|class="[^"]*hero-value")[^>]*>([^<]+)<',
    re.DOTALL,
)
# Negative lookbehind on ``[`` keeps us from matching CSS attribute selectors
# inside <style> blocks (e.g. `[data-hw-status="critical"] { ... }`) — only
# the actual SVG element attributes count toward "is this artifact stale?".
_STATUS_RE = re.compile(r'(?<!\[)data-hw-status="([^"]+)"')


async def _fetch_svg(endpoint: str, target: str) -> str:
    """GET the rendered SVG. Cache-bust with a unix-timestamp query param."""
    url = f"{endpoint.rstrip('/')}/v1/stats/{target}?_={int(time.time())}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


def _looks_like_zero(value: str) -> bool:
    """Return True for ``0``, ``0d`` (streak), or whitespace variants."""
    cleaned = value.strip().rstrip("d").rstrip(",")
    return cleaned in ("0", "")


def _looks_like_stale(value: str) -> bool:
    """Em dash is the staleness sentinel surfaced by the resolver."""
    return value.strip() == "—"


def _extract_metrics(svg: str) -> list[tuple[str, str]]:
    """Pull (label, value) pairs by anchoring on the label text element.

    Works for chrome (``mlabel``/``mval`` class pair) and brutalist
    (``field-label``/``field-value`` class pair) without paradigm-aware
    branches — both emit the value as the text element immediately
    following the label.
    """
    matches = _METRIC_RE.findall(svg)
    return [(label.strip(), value.strip()) for label, value in matches]


def _extract_hero_stars(svg: str) -> str | None:
    match = _HERO_RE.search(svg)
    return match.group(1).strip() if match else None


def probe(svg: str) -> int:
    """Return exit code: 0 = pass, 1 = fail. Side effects: prints diagnostics."""
    metrics = _extract_metrics(svg)
    if not metrics:
        print("FAIL: no metric zones found in SVG (markup contract drift?)")
        return 1

    statuses = _STATUS_RE.findall(svg)
    is_stale = "stale" in statuses
    hero_stars = _extract_hero_stars(svg)

    print(f"hero_stars={hero_stars!r}  status={statuses}")
    for label, value in metrics:
        print(f"  {label:<8} = {value!r}")

    zero_count = sum(1 for _label, value in metrics if _looks_like_zero(value))
    stale_count = sum(1 for _label, value in metrics if _looks_like_stale(value))

    # Suspicious-zero heuristic: stars is non-zero AND ALL four metrics are
    # zero. That's the exact v0.2.10 fingerprint — search-API quota hit, all
    # three search-derived counts coerced to 0, streak comes from contrib
    # which also failed → 0d. A new account legitimately reads 0 across the
    # board, so we anchor the check to a non-zero stars signal.
    if hero_stars and not _looks_like_zero(hero_stars) and zero_count == len(metrics):
        print(
            "\nFAIL: all four metrics are 0 while hero stars is non-zero. "
            "This is the v0.2.10 silent-zero shape — investigate."
        )
        return 1

    if stale_count and not is_stale:
        print(
            f"\nFAIL: {stale_count} metric(s) render as em-dash without "
            'matching data-hw-status="stale" — resolver/template drift.'
        )
        return 1

    if is_stale:
        print(
            '\nWARN: data-hw-status="stale" present. Acceptable transiently '
            "(search breaker tripped); rerun in ~30s to confirm self-heal."
        )

    print("\nPASS: stats card looks healthy.")
    return 0


async def main() -> int:
    endpoint = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ENDPOINT
    target = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_TARGET
    print(f"GET {endpoint}/v1/stats/{target}\n")
    try:
        svg = await _fetch_svg(endpoint, target)
    except httpx.HTTPError as exc:
        print(f"FAIL: HTTP error: {exc}")
        return 1
    return probe(svg)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
