"""The text-fit contract: uncapped demand, endpoint-inclusive width search,
and a defined terminal state for every policy."""

from __future__ import annotations

import pytest

from hyperweave.compose.geometry.text import (
    ELLIPSIS,
    WIDTH_QUANTUM,
    fit,
    fit_box,
    fit_line,
    measure_voice,
    required_lines,
    truncate_to_width,
    width_candidates,
    wrap_natural,
    wrap_text_lines,
)
from hyperweave.core.paradigm import MatrixVoice

VOICE = MatrixVoice(family="Inter", size=12.0, weight=500)
MONO = MatrixVoice(family="JetBrains Mono", size=10.0, weight=400)
TEXT = "central cli engine coordinating repository analysis and document synthesis"


def test_natural_wrap_reports_demand_not_permission() -> None:
    """The capped wrapper says three lines fit; the natural wrap says how many the text needs."""
    avail = 120.0
    capped = wrap_text_lines(TEXT, avail, VOICE, max_lines=3)
    natural = wrap_natural(TEXT, VOICE, avail)
    assert len(capped) == 3
    assert len(natural.lines) > 3
    assert natural.unbreakable_overflow is False
    assert required_lines(TEXT, VOICE, avail) == len(natural.lines)


def test_required_lines_is_non_increasing_in_width() -> None:
    widths = [60 + 10 * k for k in range(40)]
    counts = [required_lines(TEXT, VOICE, w) for w in widths]
    assert counts == sorted(counts, reverse=True)


def test_unbreakable_run_is_reported_never_split() -> None:
    natural = wrap_natural("supercalifragilistic word", VOICE, 30.0)
    assert natural.unbreakable_overflow is True
    assert "supercalifragilistic" in natural.lines


def test_authored_breaks_survive_the_natural_wrap() -> None:
    natural = wrap_natural("plan\ndispatch\nmerge", VOICE, 400.0)
    assert natural.lines == ("plan", "dispatch", "merge")


def test_width_candidates_always_include_both_exact_bounds() -> None:
    assert width_candidates(100.1, 100.3) == [100.1, 100.3]
    assert width_candidates(100.0, 100.0) == [100.0]
    grid = width_candidates(99.7, 101.2)
    assert grid[0] == 99.7 and grid[-1] == 101.2
    assert all(abs(w / WIDTH_QUANTUM - round(w / WIDTH_QUANTUM)) < 1e-9 for w in grid[1:-1])
    assert width_candidates(120.0, 100.0) == width_candidates(100.0, 120.0)


def test_fit_box_picks_the_narrowest_lawful_width_and_revalidates() -> None:
    w, result = fit_box(TEXT, VOICE, w_min=100.0, w_max=400.0, max_lines=3)
    assert result.overflow is False and result.truncated is False
    assert result.required_lines <= 3
    assert result.runs == wrap_natural(TEXT, VOICE, w).lines
    below = w - WIDTH_QUANTUM
    if below >= 100.0:
        assert required_lines(TEXT, VOICE, below) > 3


def test_fit_box_fits_at_an_off_grid_w_max() -> None:
    """A legal bound that misses the half-pixel grid is still a candidate: the
    answer is the narrowest candidate at or above the ink, which may be the
    exact ``w_max`` itself when no grid point sits between them."""
    ink = measure_voice("alpha beta", VOICE)
    w_min, w_max = ink - 0.2, ink + 0.1
    w, result = fit_box("alpha beta", VOICE, w_min=w_min, w_max=w_max, max_lines=1)
    assert result.overflow is False
    assert w == min(c for c in width_candidates(w_min, w_max) if c >= ink)
    assert w_max in width_candidates(w_min, w_max)


def test_fit_box_reports_overflow_only_when_w_max_itself_fails() -> None:
    w, result = fit_box(TEXT, VOICE, w_min=40.0, w_max=60.0, max_lines=1)
    assert w == 60.0
    assert result.overflow is True
    assert result.truncated is True
    assert result.shown_lines == 1
    assert result.runs[0].endswith(ELLIPSIS)


def test_fit_box_with_equal_bounds_still_answers() -> None:
    w, result = fit_box("alpha", VOICE, w_min=200.0, w_max=200.0, max_lines=2)
    assert w == 200.0
    assert result.runs == ("alpha",)


def test_grow_never_ellipsizes() -> None:
    result = fit(TEXT, VOICE, avail=80.0, max_lines=1, policy="grow")
    assert result.overflow is True
    assert result.truncated is False
    assert result.shown_lines == result.required_lines
    assert not any(ELLIPSIS in run for run in result.runs)


@pytest.mark.parametrize("policy", ["report", "ellipsize"])
def test_report_and_ellipsize_cap_the_runs_with_one_ellipsis(policy: str) -> None:
    result = fit(TEXT, VOICE, avail=120.0, max_lines=2, policy=policy)  # type: ignore[arg-type]
    assert result.shown_lines == 2
    assert result.required_lines > 2
    assert result.overflow is True and result.truncated is True
    assert result.runs[-1].endswith(ELLIPSIS)
    assert all(measure_voice(run, VOICE) <= 120.0 for run in result.runs)


def test_fit_returns_natural_runs_when_everything_fits() -> None:
    result = fit("plan dispatch merge", VOICE, avail=400.0, max_lines=2, policy="report")
    assert result.runs == ("plan dispatch merge",)
    assert result.overflow is False and result.truncated is False


def test_degenerate_budget_renders_nothing_and_reports() -> None:
    result = fit(TEXT, VOICE, avail=0.0, max_lines=2)
    assert result.runs == () and result.overflow is True
    assert fit_line("anything", VOICE, 0.0) == ""
    assert fit_line("anything", VOICE, -5.0) == ""
    assert fit_line("", VOICE, 100.0) == ""


def test_fit_line_returns_the_text_or_an_ellipsized_prefix() -> None:
    assert fit_line("alpha", VOICE, 400.0) == "alpha"
    short = fit_line(TEXT, MONO, 90.0)
    assert short.endswith(ELLIPSIS)
    assert measure_voice(short, MONO) <= 90.0


def test_legacy_truncate_keeps_its_contract() -> None:
    assert truncate_to_width("alpha", VOICE, 400.0) if False else truncate_to_width("alpha", 400.0, VOICE) == "alpha"
    assert truncate_to_width("alpha", 0.0, VOICE) == "alpha"
    cut = truncate_to_width(TEXT, 100.0, VOICE)
    assert cut.endswith(ELLIPSIS) and measure_voice(cut, VOICE) <= 100.0


def test_no_room_for_the_ellipsis_renders_nothing() -> None:
    """Below the ellipsis' own width nothing fits: the run is empty and the
    fit reports overflow, never a lone ``…`` wider than its budget."""
    ellipsis_w = measure_voice(ELLIPSIS, VOICE)
    assert fit_line("abc", VOICE, 1.0) == ""
    assert truncate_to_width("abc", ellipsis_w / 2, VOICE) == ""
    assert truncate_to_width("abc", ellipsis_w, VOICE) == ELLIPSIS
    result = fit("abc", VOICE, avail=1.0, max_lines=1)
    assert result.runs == ("",)
    assert result.overflow and result.truncated
