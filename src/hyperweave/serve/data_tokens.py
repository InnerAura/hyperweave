"""Universal data-token grammar.

A single comma-separated DSL for ``?data=`` (HTTP), ``--data`` (CLI), and
``data=`` (MCP). Every artifact that ingests data parses tokens through
the same code path here.

Token forms
-----------

``text:STRING``
    Raw display text. Marquee-horizontal scrolls these as bullets.

``kv:KEY=VALUE``
    Static literal, role-tagged. Useful when a frame slot needs a labeled
    value with no live fetch (e.g. ``kv:VERSION=0.6.9``).

``<provider>:<identifier>.<metric>``
    Live token. Resolved through :func:`hyperweave.connectors.fetch_metric`.
    Providers: ``gh`` / ``github``, ``pypi``, ``npm``, ``hf`` /
    ``huggingface``, ``arxiv``, ``docker``. The identifier may contain
    slashes (``owner/repo``); the parser splits on the **last** ``.`` to
    separate identifier from metric so ``arxiv:2310.06825.citations``
    parses correctly.

Comma escaping
--------------

The multi-token separator is ``,``. Inside ``text:`` payloads and the
VALUE portion of ``kv:KEY=VALUE``, embedded commas escape as ``\\,`` and
embedded backslashes as ``\\\\``. The parser splits on **unescaped**
commas first, then unescapes per token. URL-encoding the comma
(``%2C``) does not work as an escape because URL decoding happens at
the HTTP layer before the token parser runs — the backslash escape
survives URL decoding intact.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

_DEFAULT_TTL = 300
_FAILURE_TTL = 60

_PROVIDERS: frozenset[str] = frozenset({"gh", "github", "pypi", "npm", "hf", "huggingface", "arxiv", "docker"})

_PROVIDER_ALIASES: dict[str, str] = {"gh": "github"}


@dataclass(frozen=True)
class DataToken:
    """A parsed token, before any live values are fetched."""

    kind: Literal["text", "kv", "live"]
    payload: str = ""
    """For ``text``: the unescaped string. Empty for other kinds."""
    key: str = ""
    """For ``kv``: the KEY portion. For ``live``: the metric name (uppercased)."""
    literal_value: str = ""
    """For ``kv``: the unescaped VALUE portion. Empty for other kinds."""
    provider: str = ""
    """For ``live``: canonical provider key (post-alias resolution)."""
    identifier: str = ""
    """For ``live``: the identifier (e.g. ``owner/repo``, ``2310.06825``)."""
    metric: str = ""
    """For ``live``: the metric (e.g. ``stars``, ``downloads``)."""


@dataclass(frozen=True)
class ResolvedToken:
    """A token after live fetches have completed."""

    kind: Literal["text", "kv", "live"]
    label: str
    """Uppercased key for ``kv`` / ``live``; empty for ``text``."""
    value: str
    """Fetched value, literal value, or text payload."""
    ttl: int = 0
    """Cache TTL in seconds. ``0`` for non-live tokens."""


def _split_unescaped_commas(data: str) -> list[str]:
    """Split ``data`` on commas, treating ``\\,`` and ``\\\\`` as escapes.

    Unescaping happens during the split: each emitted segment has
    ``\\,`` replaced with ``,`` and ``\\\\`` with ``\\``. A trailing
    unescaped backslash is a parse error.
    """
    segments: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(data)
    while i < n:
        ch = data[i]
        if ch == "\\":
            if i + 1 >= n:
                raise ValueError("trailing backslash in --data; escape sequences are \\, and \\\\")
            nxt = data[i + 1]
            if nxt == ",":
                buf.append(",")
                i += 2
                continue
            if nxt == "\\":
                buf.append("\\")
                i += 2
                continue
            raise ValueError(f"invalid escape sequence '\\{nxt}' (only \\, and \\\\ are allowed)")
        if ch == ",":
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    segments.append("".join(buf))
    return segments


def _parse_one(raw: str) -> DataToken:
    """Parse a single (already-comma-split, already-unescaped) token."""
    if ":" not in raw:
        raise ValueError(f"token missing ':' kind separator: {raw!r}")

    kind_str, payload = raw.split(":", 1)
    kind_str = kind_str.strip()
    if not kind_str:
        raise ValueError(f"empty token kind: {raw!r}")

    if kind_str == "text":
        if not payload:
            raise ValueError("text: token has empty payload")
        return DataToken(kind="text", payload=payload)

    if kind_str == "kv":
        if "=" not in payload:
            raise ValueError(f"kv: token missing '=' separator: {raw!r}")
        key, value = payload.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"kv: token has empty KEY: {raw!r}")
        return DataToken(kind="kv", key=key, literal_value=value)

    # Anything else is a live token: provider:identifier.metric
    if kind_str not in _PROVIDERS:
        raise ValueError(f"unknown token kind {kind_str!r}; expected text | kv | {' | '.join(sorted(_PROVIDERS))}")

    if "." not in payload:
        raise ValueError(f"live token missing '.' metric separator: {raw!r}")

    identifier, metric = payload.rsplit(".", 1)
    identifier = identifier.strip()
    metric = metric.strip()
    if not identifier or not metric:
        raise ValueError(f"live token missing identifier or metric: {raw!r}")

    canonical_provider = _PROVIDER_ALIASES.get(kind_str, kind_str)
    return DataToken(
        kind="live",
        provider=canonical_provider,
        identifier=identifier,
        metric=metric,
    )


def parse_data_tokens(data: str) -> list[DataToken]:
    """Parse a comma-separated ``?data=`` / ``--data`` / ``data=`` string.

    Returns a list of :class:`DataToken`. Raises ``ValueError`` on any
    structural problem (unknown kind, missing separator, bad escape,
    empty payload).
    """
    if not data:
        return []
    raw_segments = _split_unescaped_commas(data)
    return [_parse_one(seg) for seg in raw_segments if seg.strip()]


# Metric-name to display-label mapping (v0.2.16-fix2).
#
# Connector authors expose API field names verbatim (Docker Hub: ``pull_count``,
# GitHub: ``stargazers_count``) so the underlying connector code is grep-able
# against the upstream API docs. But those raw field names look noisy in user-
# facing labels — ``PULL_COUNT`` reads as a SQL column, not a metric. This map
# normalizes common API field names to short uppercase display labels.
#
# Lives here (not in connectors/) because it's a presentation concern — the
# connector should keep returning ``pull_count`` so the field name stays
# greppable; only the marquee/badge/strip rendering needs the friendlier label.
# Add new entries as connectors are added; missing entries fall back to the
# raw uppercased metric name (current behavior, never breaks).
_METRIC_DISPLAY_LABELS: dict[str, str] = {
    "pull_count": "PULLS",
    "stargazers": "STARS",
    "stargazers_count": "STARS",
    "forks_count": "FORKS",
    "watchers_count": "WATCHERS",
    "subscribers_count": "WATCHERS",
    "open_issues": "ISSUES",
    "open_issues_count": "ISSUES",
    "latest_release": "VERSION",
    "last_modified": "UPDATED",
    "citation_count": "CITATIONS",
    "citations_count": "CITATIONS",
}


def _display_label(metric: str) -> str:
    """Map a connector's raw metric name to a user-facing display label.

    Normalizes the lookup key (lowercase, strip), checks the table, and
    falls back to the raw uppercased metric for any unmapped name.
    """
    key = (metric or "").strip().lower()
    return _METRIC_DISPLAY_LABELS.get(key, key.upper())


async def resolve_data_tokens(tokens: list[DataToken]) -> tuple[list[ResolvedToken], int]:
    """Resolve a list of tokens, fetching live values concurrently.

    Returns ``(resolved, min_ttl)``. ``min_ttl`` is the minimum TTL
    across any live tokens, or :data:`_DEFAULT_TTL` if there are no
    live tokens. Failed live fetches degrade to ``value="--"`` with
    :data:`_FAILURE_TTL`.
    """
    from hyperweave.connectors import fetch_metric

    live_indices: list[int] = []
    fetch_tasks: list[Any] = []
    for i, tok in enumerate(tokens):
        if tok.kind == "live":
            live_indices.append(i)
            fetch_tasks.append(fetch_metric(tok.provider, tok.identifier, tok.metric))

    fetch_results: list[Any] = []
    if fetch_tasks:
        fetch_results = list(await asyncio.gather(*fetch_tasks, return_exceptions=True))

    resolved: list[ResolvedToken] = []
    min_ttl = _DEFAULT_TTL
    fetch_index = 0

    for tok in tokens:
        if tok.kind == "text":
            resolved.append(ResolvedToken(kind="text", label="", value=tok.payload, ttl=0))
            continue
        if tok.kind == "kv":
            resolved.append(
                ResolvedToken(
                    kind="kv",
                    label=tok.key.upper(),
                    value=tok.literal_value,
                    ttl=0,
                )
            )
            continue

        # live
        result = fetch_results[fetch_index]
        fetch_index += 1
        if isinstance(result, BaseException):
            resolved.append(
                ResolvedToken(
                    kind="live",
                    label=_display_label(tok.metric),
                    value="--",
                    ttl=_FAILURE_TTL,
                )
            )
            min_ttl = min(min_ttl, _FAILURE_TTL)
            continue

        value = str(result.get("value", "n/a"))
        ttl = int(result.get("ttl", _DEFAULT_TTL))
        resolved.append(
            ResolvedToken(
                kind="live",
                label=_display_label(tok.metric),
                value=value,
                ttl=ttl,
            )
        )
        min_ttl = min(min_ttl, ttl)

    return resolved, min_ttl


def format_for_value(tokens: list[ResolvedToken]) -> str:
    """Format resolved tokens as a ``"K1:V1,K2:V2"`` string.

    Drop-in replacement for the legacy ``_fetch_live_metrics`` output.
    Used by badge and strip resolvers, which read ``spec.value`` and
    parse ``LABEL:VALUE`` pairs into per-cell metric entries.

    ``text`` tokens contribute their payload directly (no label prefix);
    ``kv`` and ``live`` tokens contribute ``LABEL:VALUE``.
    """
    parts: list[str] = []
    for tok in tokens:
        if tok.kind == "text":
            if tok.value:
                parts.append(tok.value)
        else:
            parts.append(f"{tok.label}:{tok.value}")
    return ",".join(parts)


def format_for_badge(tokens: list[ResolvedToken]) -> str:
    """Format resolved tokens for a badge's single-value slot.

    Returns just the **value** of the first resolved token. Badge has one
    value field (the title is in the path, the second slot is the rendered
    string), so the ``LABEL:VALUE`` pair shape that ``format_for_value``
    produces for strip's multi-cell layout would render as
    ``"VERSION:0.2.14"`` in a badge — wrong twice (label leaks into the
    value, and badges don't parse colon-pairs anyway).

    If the caller passes multiple tokens to a badge, only the first
    contributes — additional tokens are silently dropped because badge
    has no slot for them. Callers wanting multi-metric output should
    use strip instead.

    Empty token list returns the empty string so the badge route can
    fall back to a path-segment value.
    """
    for tok in tokens:
        if tok.kind == "text":
            return tok.value
        # kv / live: drop the label, keep the resolved value.
        return tok.value
    return ""


def format_for_marquee(tokens: list[ResolvedToken]) -> list[dict[str, Any]]:
    """Format resolved tokens as marquee-horizontal scroll items.

    Each item carries the displayed text plus a role tag the resolver
    uses to pick chromatic / weight treatment from the genome's
    palette. The resolver — not this formatter — owns the visual
    styling, since palette decisions depend on the genome family
    (cellular bifamily, brutalist, chrome).

    Returned shape per item::

        {
            "text": "displayed string",
            "role": "text" | "kv" | "live",
            "label": "STARS" | "" (empty for text role),
            "raw_value": "1234" | "" (empty for text role),
        }
    """
    items: list[dict[str, Any]] = []
    for tok in tokens:
        if tok.kind == "text":
            items.append({"text": tok.value, "role": "text", "label": "", "raw_value": ""})
            continue
        # kv / live render as "LABEL VALUE" by default; resolvers may
        # split label+value into separate tspans for two-stop chromatic
        # treatment (info hex on label, primary ink on value).
        items.append(
            {
                "text": f"{tok.label} {tok.value}".strip(),
                "role": tok.kind,
                "label": tok.label,
                "raw_value": tok.value,
            }
        )
    return items


__all__ = [
    "DataToken",
    "ResolvedToken",
    "format_for_badge",
    "format_for_marquee",
    "format_for_value",
    "parse_data_tokens",
    "resolve_data_tokens",
]
