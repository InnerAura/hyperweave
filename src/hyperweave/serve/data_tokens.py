"""Universal data-token grammar.

A single comma-separated DSL for ``?data=`` (HTTP), ``--data`` (CLI), and
``data=`` (MCP). Every artifact that ingests data parses tokens through
the same code path here.

Token forms
-----------

``text:STRING``
    Raw display text. Marquee-horizontal scrolls these as bullets.

``kv:KEY=VALUE`` (optionally ``kv:KEY=VALUE~WINDOW``)
    Static literal, role-tagged. Useful when a frame slot needs a labeled
    value with no live fetch (e.g. ``kv:VERSION=0.6.9``). A trailing
    ``~WINDOW`` records a period qualifier for download-type cells
    (``kv:DOWNLOADS=847K~ALL-TIME``) so the marquee can render the window
    subtitle deterministically across all three transport paths — the live
    path derives the same window from ``(provider, metric)``. ``~`` is an
    RFC-3986 unreserved char (survives URL-quoting); a VALUE that must
    contain a literal ``~`` is not currently expressible (no download value
    uses one).

``<provider>:<identifier>.<metric>``
    Live token. Resolved through :func:`hyperweave.connectors.fetch_metric`.
    Providers: ``gh`` / ``github``, ``pypi``, ``npm``, ``hf`` /
    ``huggingface``, ``arxiv``, ``docker``, ``crates`` / ``cargo``,
    ``scorecard`` (OpenSSF supply-chain trust), ``dora`` (GitHub Actions
    delivery metrics). The identifier may contain slashes (``owner/repo``);
    the parser splits on the **last** ``.`` to separate identifier from
    metric so ``arxiv:2310.06825.citations`` parses correctly.

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
from dataclasses import dataclass, field
from typing import Any, Literal

_DEFAULT_TTL = 300
_FAILURE_TTL = 60

_PROVIDERS: frozenset[str] = frozenset(
    {
        "gh",
        "github",
        "pypi",
        "npm",
        "hf",
        "huggingface",
        "arxiv",
        "docker",
        "crates",
        "cargo",
        "scorecard",
        "dora",
    }
)

_PROVIDER_ALIASES: dict[str, str] = {"gh": "github", "hf": "huggingface", "cargo": "crates"}


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
    window: str = ""
    """Period qualifier for download-type cells. For ``kv``: parsed from a
    trailing ``~WINDOW`` on the value. For ``live``: populated by the resolver
    from :data:`_DOWNLOAD_WINDOWS`. Empty for non-download cells."""


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
    provider: str = field(default="", compare=False)
    """Canonical provider key for live tokens; empty for text/kv tokens."""
    identifier: str = field(default="", compare=False)
    """Provider identifier for live tokens; empty for text/kv tokens."""
    metric: str = field(default="", compare=False)
    """Raw provider metric for live tokens; empty for text/kv tokens."""
    raw_value: object = field(default=None, compare=False)
    """Unformatted connector value for live tokens when available."""
    window: str = field(default="", compare=False)
    """Period qualifier ("ALL-TIME", "30D", "7D", "90D") for download-type
    cells — rendered as a dim subtitle after the value in the marquee. Derived
    from :data:`_DOWNLOAD_WINDOWS` for live tokens, or carried from a kv token's
    ``~WINDOW`` suffix. Empty for every non-download cell."""


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
        # Optional trailing ``~WINDOW`` period qualifier (download cells):
        # ``kv:DOWNLOADS=847K~ALL-TIME`` → value="847K", window="ALL-TIME".
        window = ""
        if "~" in value:
            value, window = value.rsplit("~", 1)
        return DataToken(kind="kv", key=key, literal_value=value, window=window)

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
    "pull_requests": "PRS",
    "last_push": "LAST PUSH",
    "latest_release": "VERSION",
    "last_modified": "UPDATED",
    "citation_count": "CITATIONS",
    "citations_count": "CITATIONS",
    # crates.io
    "recent_downloads": "RECENT",
    # HuggingFace (audit-surfaced)
    "gated": "GATED",
    # OpenSSF Scorecard — short labels for the noisy snake_case check names.
    "score": "TRUST",
    "code_review": "REVIEW",
    "vulnerabilities": "VULNS",
    "branch_protection": "BRANCH",
    "dangerous_workflow": "WORKFLOW",
    "pinned_dependencies": "PINNED-DEPS",
    "token_permissions": "TOKEN-PERMS",
    "security_policy": "SEC-POLICY",
    "dependency_update": "DEP-UPDATE",
    # OpenSSF Scorecard (v0.3.13) — remaining checks that previously fell
    # through to raw-key uppercasing (e.g. "CII_BEST_PRACTICES").
    "cii_best_practices": "CII-BP",
    "fuzzing": "FUZZING",
    "packaging": "PACKAGING",
    "sast": "SAST",
    "signed_releases": "SIGNED-REL",
    "license": "LICENSE",
    "ci_tests": "CI-TESTS",
    "contributors": "CONTRIBS",
    # GitHub Actions DORA
    "deploy_frequency": "DEPLOY FREQ",
    "lead_time": "LEAD TIME",
    "change_failure_rate": "CFR",
    "mttr": "MTTR",
}


def _display_label(metric: str) -> str:
    """Map a connector's raw metric name to a user-facing display label.

    Normalizes the lookup key (lowercase, strip), checks the table, and
    falls back to the raw uppercased metric for any unmapped name.
    """
    key = (metric or "").strip().lower()
    return _METRIC_DISPLAY_LABELS.get(key, key.upper())


# Period qualifier for download-type metrics, keyed by (provider, metric). The
# window is a fixed property of which API/endpoint the connector reads — making
# the otherwise-ambiguous download count self-describing. pypi routes through
# pepy.tech total_downloads (all-time; the pypistats month fallback is a rare
# degraded path); crates `downloads` is the all-time crate total while
# `recent_downloads` is its 90-day window; npm's point API reads last-week.
# Any (provider, metric) absent here yields no window — non-download cells stay
# subtitle-free.
_DOWNLOAD_WINDOWS: dict[tuple[str, str], str] = {
    ("pypi", "downloads"): "ALL-TIME",
    ("crates", "downloads"): "ALL-TIME",
    ("crates", "recent_downloads"): "90D",
    ("npm", "downloads"): "7D",
}


def _download_window(provider: str, metric: str) -> str:
    """Period qualifier for a live download metric, or empty for non-downloads."""
    return _DOWNLOAD_WINDOWS.get(((provider or "").strip().lower(), (metric or "").strip().lower()), "")


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
                    window=tok.window,
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
                    provider=tok.provider,
                    identifier=tok.identifier,
                    metric=tok.metric,
                    window=_download_window(tok.provider, tok.metric),
                )
            )
            min_ttl = min(min_ttl, _FAILURE_TTL)
            continue

        raw_value = result.get("value", "n/a")
        value = str(raw_value)
        ttl = int(result.get("ttl", _DEFAULT_TTL))
        resolved.append(
            ResolvedToken(
                kind="live",
                label=_display_label(tok.metric),
                value=value,
                ttl=ttl,
                provider=tok.provider,
                identifier=tok.identifier,
                metric=tok.metric,
                raw_value=raw_value,
                window=_download_window(tok.provider, tok.metric),
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
            "metric": "stars" | "" (token-grammar metric; empty for text/kv),
        }

    ``metric`` carries the live token's grammar metric (``gh:o/r.stars`` →
    ``"stars"``) so the marquee resolver can categorize cells (volume /
    activity / identity) by exact metric key rather than fuzzy label matching.
    """
    items: list[dict[str, Any]] = []
    for tok in tokens:
        if tok.kind == "text":
            items.append({"text": tok.value, "role": "text", "label": "", "raw_value": "", "metric": ""})
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
                "metric": tok.metric,
                "window": tok.window,
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
