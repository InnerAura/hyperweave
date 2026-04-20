"""Diagnostic probe: call fetch_stargazer_history against real repos and dump the results.

Usage:
    uv run python scripts/probe_star_history.py [owner/repo ...]

If no arguments are provided, probes the three canonical test repos.
Requires HW_GITHUB_TOKENS or GITHUB_TOKEN for the authenticated 5K/hr cap
(unauth runs fail quickly against the 60/hr limit).
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime

from hyperweave.connectors.github import fetch_stargazer_history


async def probe(identifier: str) -> None:
    owner, repo = identifier.split("/", 1)
    print(f"\n{'=' * 70}\nREPO: {identifier}\n{'=' * 70}")

    try:
        result = await fetch_stargazer_history(owner, repo)
    except Exception as exc:
        print(f"FETCH FAILED: {type(exc).__name__}: {exc}")
        return

    print(f"current_stars={result['current_stars']}  points={len(result['points'])}")
    for p in result["points"]:
        print(f"  {p['date']}  count={p['count']}")

    points = result["points"]
    if len(points) >= 2:
        t0 = datetime.fromisoformat(points[0]["date"].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(points[-1]["date"].replace("Z", "+00:00"))
        span_days = (t1 - t0).days
        counts = [p["count"] for p in points]
        print(f"\nspan={span_days}d  count range: {min(counts)}..{max(counts)}")


async def main() -> None:
    repos = sys.argv[1:] or [
        "eli64s/readme-ai",
        "JuliusBrussee/caveman",
        "openclaw/openclaw",
    ]
    for repo in repos:
        await probe(repo)


if __name__ == "__main__":
    asyncio.run(main())
