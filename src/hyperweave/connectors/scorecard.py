"""OpenSSF Scorecard connector — supply-chain trust scores.

Keyless and repo-scoped (``owner/repo``). ``api.securityscorecards.dev`` serves
a weekly-refreshed aggregate score plus per-check sub-scores for repositories in
the OpenSSF scan set.

Fetch-once: the full payload is cached under ``scorecard:{id}:payload`` and every
metric token reads from it, so N metric tokens for one repo cost 1 API call (the
same two-layer-cache shape as ``github.py``'s build-status path).

Score semantics (verified live against ``tokio-rs/tokio``): each check and the
aggregate range **0-10**, EXCEPT ``-1`` which means "the check did not run /
inconclusive" → surfaced as ``"n/a"``, never a negative gauge value. The
``checks[]`` array is **variable-length per repo** — a check ABSENT on a repo is
``"n/a"`` too, not ``0``. The check-name strings below are copied verbatim from a
live response (Title-Case-Hyphenated); a wrong name silently resolves to
``"n/a"`` on every repo (the v0.2.10 broken-shape failure mode).
"""

from __future__ import annotations

from typing import Any

from hyperweave.connectors.base import fetch_json
from hyperweave.connectors.cache import get_cache

PROVIDER = "scorecard"
# 6h — Scorecard recomputes weekly, so a long TTL never serves meaningfully
# stale data while still collapsing repeated dashboard loads to one call.
CACHE_TTL = 21600

_NA = "n/a"

# snake_case metric token → exact Scorecard check name. The top-level ``score``
# aggregate is handled separately (it is not a member of ``checks[]``).
_CHECK_NAMES: dict[str, str] = {
    "maintained": "Maintained",
    "code_review": "Code-Review",
    "dangerous_workflow": "Dangerous-Workflow",
    "branch_protection": "Branch-Protection",
    "security_policy": "Security-Policy",
    "token_permissions": "Token-Permissions",
    "pinned_dependencies": "Pinned-Dependencies",
    "binary_artifacts": "Binary-Artifacts",
    "cii_best_practices": "CII-Best-Practices",
    "fuzzing": "Fuzzing",
    "packaging": "Packaging",
    "sast": "SAST",
    "signed_releases": "Signed-Releases",
    "license": "License",
    "vulnerabilities": "Vulnerabilities",
    "dependency_update": "Dependency-Update-Tool",
    "ci_tests": "CI-Tests",
    "contributors": "Contributors",
}


def _require_slash(identifier: str) -> None:
    if "/" not in identifier:
        raise ValueError(f"Scorecard identifier must be 'owner/repo', got {identifier!r}")


def _score_or_na(raw: Any) -> Any:
    """Map a Scorecard numeric score to a value or ``"n/a"``.

    ``-1`` (check did not run / inconclusive) and any non-numeric value become
    ``"n/a"`` so a negative score never reaches a gauge.
    """
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return _NA
    if raw < 0:
        return _NA
    return raw


async def _fetch_payload(identifier: str) -> dict[str, Any]:
    """Fetch + cache the full Scorecard payload once for ``owner/repo``."""
    cache = get_cache()
    cache_key = f"{PROVIDER}:{identifier}:payload"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    owner, repo = identifier.split("/", 1)
    url = f"https://api.securityscorecards.dev/projects/github.com/{owner}/{repo}"
    payload: dict[str, Any] = await fetch_json(url, provider=PROVIDER)
    cache.set(cache_key, payload, CACHE_TTL)
    return payload


async def fetch_metric(identifier: str, metric: str) -> dict[str, Any]:
    """Fetch a single Scorecard metric for ``owner/repo``.

    Every metric for one repo shares a single upstream call via the cached
    payload. A repo absent from the weekly scan set 404s → ``ConnectorError``
    → the token layer renders the empty-state ``"--"``.
    """
    _require_slash(identifier)
    payload = await _fetch_payload(identifier)

    if metric == "score":
        value = _score_or_na(payload.get("score"))
    else:
        check_name = _CHECK_NAMES.get(metric)
        if check_name is None:
            available = ["score", *sorted(_CHECK_NAMES)]
            raise ValueError(f"Unknown Scorecard metric {metric!r}. Available: {', '.join(available)}")
        by_name = {c.get("name"): c.get("score") for c in payload.get("checks", []) if isinstance(c, dict)}
        # Absent check (variable-length array) → n/a; present but -1 → n/a.
        value = _score_or_na(by_name[check_name]) if check_name in by_name else _NA

    return {
        "provider": PROVIDER,
        "identifier": identifier,
        "metric": metric,
        "value": value,
        "ttl": CACHE_TTL,
    }
