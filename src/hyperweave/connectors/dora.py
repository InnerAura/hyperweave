"""GitHub Actions DORA metrics — computed delivery-performance aggregates.

The four DORA metrics (deploy frequency, lead time for changes, change failure
rate, mean time to recovery) are *computed* from a 30-day window of GitHub
Deployments (primary) or Actions runs (fallback), not read from a single field.

Data source
-----------
**Primary: Deployments API.** ``GET /repos/{o}/{r}/deployments?per_page=100``
(newest first) + a per-deployment ``/deployments/{id}/statuses`` call whose
latest entry is the current state. **Fallback** (zero in-window deployments):
``GET /repos/{o}/{r}/actions/runs?branch={default}&per_page=100`` — each
completed run is treated as a deploy via ``conclusion``; ``head_commit.timestamp``
is inline so the Actions path needs no per-run commit lookup. The
"workflow-run-as-deploy" proxy is a documented assumption — revisit for stricter
deploy semantics.

Cost & isolation
----------------
**Breaker domain ``github-actions``** (a 4th github failure domain, see
``base.py``) keeps DORA's paginated fan-out from tripping the badge/star
``github-core`` breaker. **Fetch-once:** the aggregate is cached under
``dora:{id}:w{N}`` and all four metric tokens read it. Lead-time commit lookups
are capped at the most recent ~30 in-window deploys to bound cost. Needs
``HW_GITHUB_TOKENS`` set — the unauth 60/hr ceiling exhausts fast under
pagination. Both upstream ops run under one pinned token for a consistent view.

Window
------
Default 30 days. The ``provider:id.metric`` token grammar has no window slot, so
a non-default window is out of scope for v0.3.12 (a future ``?window=`` would
thread through the spec, not the token). ``fetch_metric(id, metric,
window_days=30)`` keeps the 2-arg dispatch contract.
"""

from __future__ import annotations

import asyncio
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from hyperweave.connectors.base import (
    CircuitOpenError,
    ConnectorError,
    fetch_json,
    pin_github_token,
)
from hyperweave.connectors.cache import get_cache

PROVIDER = "dora"
# Separate breaker domain so DORA's pagination can't trip badge/star endpoints.
_BREAKER = "github-actions"
CACHE_TTL = 3600
DORA_DEFAULT_WINDOW_DAYS = 30
# Cap commit lookups (lead time) to bound the /commits fan-out per repo.
LEAD_TIME_SAMPLE_CAP = 30
_PER_PAGE = 100
_NA = "n/a"

_METRICS: tuple[str, ...] = ("deploy_frequency", "lead_time", "change_failure_rate", "mttr")
# Conclusions that count as a failed delivery (vs success). cancelled / skipped
# / neutral / None are non-outcomes and excluded from the deploy population.
_FAILURE_CONCLUSIONS: frozenset[str] = frozenset({"failure", "timed_out", "startup_failure"})
_TERMINAL_DEPLOY_STATES: frozenset[str] = frozenset({"success", "failure", "error"})


@dataclass(frozen=True)
class _DeployEvent:
    """One delivery in the window, normalized across both data sources."""

    completed_at: datetime
    success: bool
    authored_at: datetime | None  # head-commit author time, for lead time


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _commit_authored_at(owner: str, repo: str, sha: Any, token: str | None) -> datetime | None:
    if not isinstance(sha, str) or not sha:
        return None
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"
    try:
        data = await fetch_json(url, provider=_BREAKER, auth_token=token)
    except (ConnectorError, CircuitOpenError):
        return None
    commit = data.get("commit") if isinstance(data, dict) else None
    author = commit.get("author") if isinstance(commit, dict) else None
    return _parse_dt(author.get("date")) if isinstance(author, dict) else None


async def _deployment_events(owner: str, repo: str, cutoff: datetime, token: str | None) -> list[_DeployEvent]:
    """Build deploy events from the Deployments API (primary path)."""
    url = f"https://api.github.com/repos/{owner}/{repo}/deployments?per_page={_PER_PAGE}"
    try:
        deployments = await fetch_json(url, provider=_BREAKER, auth_token=token)
    except (ConnectorError, CircuitOpenError):
        return []
    if not isinstance(deployments, list):
        return []

    in_window = [
        dep
        for dep in deployments
        if isinstance(dep, dict) and (created := _parse_dt(dep.get("created_at"))) is not None and created >= cutoff
    ]
    if not in_window:
        return []

    async def _resolve_status(dep: dict[str, Any]) -> tuple[dict[str, Any], str, datetime] | None:
        dep_id = dep.get("id")
        surl = f"https://api.github.com/repos/{owner}/{repo}/deployments/{dep_id}/statuses?per_page=10"
        try:
            statuses = await fetch_json(surl, provider=_BREAKER, auth_token=token)
        except (ConnectorError, CircuitOpenError):
            return None
        if not isinstance(statuses, list) or not statuses or not isinstance(statuses[0], dict):
            return None
        latest = statuses[0]  # statuses are newest-first; latest is the current state
        state = latest.get("state")
        if state not in _TERMINAL_DEPLOY_STATES:
            return None  # in_progress / queued / waiting — not yet a delivery
        completed = _parse_dt(latest.get("created_at")) or _parse_dt(dep.get("updated_at"))
        if completed is None:
            return None
        return dep, str(state), completed

    resolved = await asyncio.gather(*[_resolve_status(dep) for dep in in_window])
    settled = [r for r in resolved if r is not None]

    # Lead time needs the head commit's author time — one /commits call each.
    # Cap to the most recent N (settled is newest-first, mirroring the page order).
    sha_lookups = [
        _commit_authored_at(owner, repo, dep.get("sha"), token) for dep, _, _ in settled[:LEAD_TIME_SAMPLE_CAP]
    ]
    authored = await asyncio.gather(*sha_lookups)

    events: list[_DeployEvent] = []
    for idx, (_dep, state, completed) in enumerate(settled):
        authored_at = authored[idx] if idx < len(authored) else None
        events.append(_DeployEvent(completed, state == "success", authored_at))
    return events


async def _actions_events(owner: str, repo: str, cutoff: datetime, token: str | None) -> list[_DeployEvent]:
    """Build deploy events from Actions runs on the default branch (fallback)."""
    try:
        repo_data = await fetch_json(
            f"https://api.github.com/repos/{owner}/{repo}", provider=_BREAKER, auth_token=token
        )
    except (ConnectorError, CircuitOpenError):
        return []
    default_branch = repo_data.get("default_branch", "main") if isinstance(repo_data, dict) else "main"

    runs_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs?branch={default_branch}&per_page={_PER_PAGE}"
    try:
        runs_data = await fetch_json(runs_url, provider=_BREAKER, auth_token=token)
    except (ConnectorError, CircuitOpenError):
        return []
    runs = runs_data.get("workflow_runs") if isinstance(runs_data, dict) else None
    if not isinstance(runs, list):
        return []

    events: list[_DeployEvent] = []
    for run in runs:
        if not isinstance(run, dict) or run.get("status") != "completed":
            continue
        conclusion = run.get("conclusion")
        if conclusion != "success" and conclusion not in _FAILURE_CONCLUSIONS:
            continue  # cancelled / skipped / neutral — not a delivery outcome
        completed = _parse_dt(run.get("updated_at"))
        if completed is None or completed < cutoff:
            continue
        head_commit = run.get("head_commit")
        authored = _parse_dt(head_commit.get("timestamp")) if isinstance(head_commit, dict) else None
        events.append(_DeployEvent(completed, conclusion == "success", authored))
    return events


def _compute_dora(events: list[_DeployEvent], window_days: int) -> dict[str, Any]:
    """Compute the four DORA metrics from a normalized event list."""
    if not events:
        return {"deploy_frequency": 0.0, "lead_time": _NA, "change_failure_rate": 0.0, "mttr": _NA}

    total = len(events)
    successes = [e for e in events if e.success]
    failures = [e for e in events if not e.success]

    deploy_frequency = round(len(successes) / window_days, 3)

    lead_samples = [
        (e.completed_at - e.authored_at).total_seconds() / 3600.0
        for e in events
        if e.authored_at is not None and e.completed_at >= e.authored_at
    ]
    lead_time: Any = round(statistics.median(lead_samples), 2) if lead_samples else _NA

    change_failure_rate = round(100.0 * len(failures) / total, 1)

    # MTTR: mean gap from each failure to the next success (chronological).
    # A failure with no following success in-window is excluded.
    chron = sorted(events, key=lambda e: e.completed_at)
    recovery_hours: list[float] = []
    for i, event in enumerate(chron):
        if event.success:
            continue
        for later in chron[i + 1 :]:
            if later.success:
                recovery_hours.append((later.completed_at - event.completed_at).total_seconds() / 3600.0)
                break
    mttr: Any = round(statistics.mean(recovery_hours), 2) if recovery_hours else _NA

    return {
        "deploy_frequency": deploy_frequency,
        "lead_time": lead_time,
        "change_failure_rate": change_failure_rate,
        "mttr": mttr,
    }


async def _aggregate(identifier: str, window_days: int) -> dict[str, Any]:
    """Fetch + cache the full DORA aggregate once for ``owner/repo``."""
    cache = get_cache()
    cache_key = f"{PROVIDER}:{identifier}:w{window_days}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    owner, repo = identifier.split("/", 1)
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    # Pin one token across the whole windowed op so /deployments, /statuses, and
    # /commits see a consistent view (token rotation happens BETWEEN ops).
    token = pin_github_token()

    events = await _deployment_events(owner, repo, cutoff, token)
    source = "deployments"
    if not events:
        events = await _actions_events(owner, repo, cutoff, token)
        source = "actions"

    result = _compute_dora(events, window_days)
    result["source"] = source
    result["window_days"] = window_days
    result["ttl"] = CACHE_TTL
    cache.set(cache_key, result, CACHE_TTL)
    return result


async def fetch_metric(identifier: str, metric: str, window_days: int = DORA_DEFAULT_WINDOW_DAYS) -> dict[str, Any]:
    """Fetch a single DORA metric for ``owner/repo``.

    All four metrics share one cached aggregate (one paginated fan-out per repo
    per window). Edge cases: zero deploys → freq ``0``, lead/mttr ``"n/a"``;
    zero failures → cfr ``0``, mttr ``"n/a"``.
    """
    if "/" not in identifier:
        raise ValueError(f"DORA identifier must be 'owner/repo', got {identifier!r}")
    if metric not in _METRICS:
        raise ValueError(f"Unknown DORA metric {metric!r}. Available: {', '.join(_METRICS)}")

    aggregate = await _aggregate(identifier, window_days)
    return {
        "provider": PROVIDER,
        "identifier": identifier,
        "metric": metric,
        "value": aggregate.get(metric),
        "ttl": CACHE_TTL,
    }
