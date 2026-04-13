"""Unit tests for the GitHub contribution calendar HTML scraper.

The parser is tested against a pinned synthetic HTML fixture so it does NOT
break on GitHub markup churn without surfacing a clear test failure. The live
drift canaries live in test_github_scrape_live.py (opt-in via -m network).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hyperweave.connectors.github import (
    _USERNAME_RE,
    _fetch_contribution_data,
    parse_contribution_html,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "github_contributions"


@pytest.fixture()
def synthetic_html() -> str:
    return (FIXTURE_DIR / "synthetic.html").read_text()


# ── parse_contribution_html ────────────────────────────────────────────


def test_parse_counts_tooltip_integers(synthetic_html: str) -> None:
    """Exact counts from <tool-tip> elements are preserved byte-for-byte."""
    parsed = parse_contribution_html(synthetic_html)
    # 0 + 2 + 7 + 14 + 32 + 1203 + 0 + 0 + 4 + 9 + 11 = 1282
    assert parsed["contrib_total"] == 1282


def test_parse_no_contributions_is_zero(synthetic_html: str) -> None:
    parsed = parse_contribution_html(synthetic_html)
    # The first row's first cell is "No contributions" → count 0 → level 0.
    first = parsed["heatmap_grid"][0]
    assert first["date"] == "2025-01-01"
    assert first["count"] == 0
    assert first["level"] == 0


def test_parse_handles_four_digit_counts(synthetic_html: str) -> None:
    """Dense accounts like vercel have 4-digit counts; parser must not truncate."""
    parsed = parse_contribution_html(synthetic_html)
    dense = next(c for c in parsed["heatmap_grid"] if c["date"] == "2025-01-06")
    assert dense["count"] == 1203
    assert dense["level"] == 4


def test_parse_streak_walks_backwards(synthetic_html: str) -> None:
    """Trailing non-zero streak of 3 days (Jan 9, 10, 11)."""
    parsed = parse_contribution_html(synthetic_html)
    assert parsed["streak_days"] == 3


def test_parse_streak_grace_day_for_empty_today() -> None:
    """The most-recent cell may be zero without breaking the streak.

    GitHub renders today's empty cell at the rightmost position before the
    user has committed today. A morning stats check on an otherwise active
    contributor should NOT report streak=0 just because today hasn't happened
    yet. Subsequent zeros still break the streak.
    """
    html = (
        '<td class="ContributionCalendar-day" data-date="2025-04-08" data-level="0">&nbsp;</td>'
        '<td class="ContributionCalendar-day" data-date="2025-04-09" data-level="2">&nbsp;</td>'
        '<td class="ContributionCalendar-day" data-date="2025-04-10" data-level="3">&nbsp;</td>'
        '<td class="ContributionCalendar-day" data-date="2025-04-11" data-level="4">&nbsp;</td>'
        '<td class="ContributionCalendar-day" data-date="2025-04-12" data-level="0">&nbsp;</td>'
        '<tool-tip>No contributions on April 8</tool-tip>'
        '<tool-tip>5 contributions on April 9</tool-tip>'
        '<tool-tip>12 contributions on April 10</tool-tip>'
        '<tool-tip>30 contributions on April 11</tool-tip>'
        '<tool-tip>No contributions on April 12</tool-tip>'
    )
    parsed = parse_contribution_html(html)
    # Today (Apr 12) is empty → grace. Apr 11 (30), Apr 10 (12), Apr 9 (5) are
    # all non-zero → streak = 3. Apr 8 is zero → break.
    assert parsed["streak_days"] == 3


def test_parse_streak_two_consecutive_zeros_break() -> None:
    """Grace applies to the single most-recent cell only, not cumulative."""
    html = (
        '<td class="ContributionCalendar-day" data-date="2025-04-10" data-level="3">&nbsp;</td>'
        '<td class="ContributionCalendar-day" data-date="2025-04-11" data-level="0">&nbsp;</td>'
        '<td class="ContributionCalendar-day" data-date="2025-04-12" data-level="0">&nbsp;</td>'
        '<tool-tip>12 contributions on April 10</tool-tip>'
        '<tool-tip>No contributions on April 11</tool-tip>'
        '<tool-tip>No contributions on April 12</tool-tip>'
    )
    parsed = parse_contribution_html(html)
    # Today (Apr 12) is grace-zero, Apr 11 is also zero → streak breaks.
    assert parsed["streak_days"] == 0


def test_parse_chronological_order(synthetic_html: str) -> None:
    parsed = parse_contribution_html(synthetic_html)
    dates = [c["date"] for c in parsed["heatmap_grid"]]
    assert dates == sorted(dates)
    assert len(dates) == 11


def test_parse_empty_html_is_safe() -> None:
    """Malformed / empty markup → zero totals, empty grid, no exceptions."""
    result = parse_contribution_html("<html></html>")
    assert result["contrib_total"] == 0
    assert result["streak_days"] == 0
    assert result["heatmap_grid"] == []


def test_parse_partial_markup_falls_back_to_level_estimate() -> None:
    """When the tooltip count is missing, fall back to the level estimate."""
    html = (
        '<td class="ContributionCalendar-day" data-date="2025-04-01" data-level="2">&nbsp;</td>'
        '<td class="ContributionCalendar-day" data-date="2025-04-02" data-level="4">&nbsp;</td>'
    )
    parsed = parse_contribution_html(html)
    # level 2 → estimate 4, level 4 → estimate 20.
    assert parsed["contrib_total"] == 24
    assert parsed["heatmap_grid"][0]["level"] == 2
    assert parsed["heatmap_grid"][1]["level"] == 4


# ── Username sanitization ──────────────────────────────────────────────


def test_username_regex_accepts_real_usernames() -> None:
    for ok in ("eli64s", "vercel", "JuliusBrussee", "a", "user-name-with-hyphens"):
        assert _USERNAME_RE.match(ok), f"Should accept {ok!r}"


def test_username_regex_rejects_injection_attempts() -> None:
    for bad in (
        "../etc/passwd",
        "user;rm -rf /",
        "",
        "a" * 40,  # too long (>39)
        "user/repo",
        "user name",
        "user$name",
    ):
        assert not _USERNAME_RE.match(bad), f"Should reject {bad!r}"


@pytest.mark.asyncio
async def test_fetch_contribution_data_rejects_bad_username() -> None:
    with pytest.raises(ValueError):
        await _fetch_contribution_data("../etc/passwd")


@pytest.mark.asyncio
async def test_fetch_contribution_data_uses_cache(
    synthetic_html: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second call for the same username should hit the in-memory cache."""
    from hyperweave.connectors import cache as cache_module
    from hyperweave.connectors import github as github_module

    cache_module.get_cache().clear()

    call_count = 0

    async def fake_fetch_text(url: str, provider: str = "", headers: dict[str, str] | None = None) -> str:
        nonlocal call_count
        call_count += 1
        return synthetic_html

    monkeypatch.setattr(github_module, "fetch_text", fake_fetch_text)

    r1 = await _fetch_contribution_data("eli64s")
    r2 = await _fetch_contribution_data("eli64s")
    assert r1 == r2
    assert call_count == 1  # second call served from cache


@pytest.mark.asyncio
async def test_fetch_contribution_data_graceful_on_fetch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network failure → returns zeros, never raises."""
    from hyperweave.connectors import cache as cache_module
    from hyperweave.connectors import github as github_module

    cache_module.get_cache().clear()

    async def failing_fetch_text(url: str, provider: str = "", headers: dict[str, str] | None = None) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr(github_module, "fetch_text", failing_fetch_text)

    result = await _fetch_contribution_data("eli64s")
    assert result["contrib_total"] == 0
    assert result["streak_days"] == 0
    assert result["heatmap_grid"] == []
