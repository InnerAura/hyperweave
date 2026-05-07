"""Tests for :mod:`hyperweave.compose.treemap`.

Locks the layout invariants the inline resolver implementation violated:

* No cell ever extends past ``content_w`` (the production overflow bug
  on `TaskCreate` / `ExitPlanMode` / `AskUserQuestion`).
* Tier-2 widths sum + gaps fit inside ``content_w`` exactly (the
  cumulative gap-subtraction bug).
* Tier-3 emits a synthesized "+N more" cell when the tool count exceeds
  what fits at ``min_w_tier3``.
* Labels are ellipsized to fit their cell.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from hyperweave.compose.treemap import (
    TreemapCell,
    _format_tokens,
    _truncate_label,
    compute_treemap_layout,
)

# --------------------------------------------------------------------------- #
# Fixtures: representative tool dicts                                         #
# --------------------------------------------------------------------------- #


def _tool(name: str, tokens: int, count: int, tool_class: str = "explore", errors: int = 0) -> dict[str, Any]:
    """Build a tool dict matching the resolver's normalized shape."""
    return {
        "name": name,
        "total_tokens": tokens,
        "count": count,
        "tool_class": tool_class,
        "errors": errors,
        "blocked": 0,
    }


# --------------------------------------------------------------------------- #
# Empty + single-tool baselines                                               #
# --------------------------------------------------------------------------- #


def test_empty_tools_returns_empty_list() -> None:
    assert compute_treemap_layout([]) == []


def test_single_tool_renders_only_tier_one() -> None:
    cells = compute_treemap_layout([_tool("Edit", 1_000_000, 50, "mutate")])
    assert len(cells) == 1
    cell = cells[0]
    assert cell.tier == 1
    assert cell.x == 0
    assert cell.w == 752
    assert cell.h == 88
    assert cell.pct == 100
    assert cell.tool_class == "mutate"
    assert cell.is_overflow is False


# --------------------------------------------------------------------------- #
# Multi-tier layouts                                                          #
# --------------------------------------------------------------------------- #


def test_four_tools_fills_tiers_one_and_two() -> None:
    """Four tools: one at tier-1, three at tier-2, none at tier-3."""
    tools = [
        _tool("Edit", 800_000, 200, "mutate"),
        _tool("Bash", 300_000, 100, "execute"),
        _tool("Read", 200_000, 80, "explore"),
        _tool("Write", 100_000, 50, "mutate"),
    ]
    cells = compute_treemap_layout(tools)
    by_tier = {c.tier: [x for x in cells if x.tier == c.tier] for c in cells}
    assert len(by_tier[1]) == 1
    assert len(by_tier[2]) == 3
    assert 3 not in by_tier


def test_seven_tools_fills_all_three_tiers() -> None:
    tools = [_tool(f"Tool{i}", 1000 - i * 50, 30 - i, "explore") for i in range(7)]
    cells = compute_treemap_layout(tools)
    tiers = {c.tier for c in cells}
    assert tiers == {1, 2, 3}


# --------------------------------------------------------------------------- #
# Right-edge invariant: NO cell ever extends past content_w                   #
# --------------------------------------------------------------------------- #


def test_no_cell_exceeds_content_w_with_many_tail_tools() -> None:
    """Regression for the production bug: 12 tail tools used to push
    the rightmost tier-3 cell past 752px.
    """
    tools = [_tool(f"Tool{i:02d}", max(10_000 - i * 200, 100), max(50 - i, 1)) for i in range(12)]
    cells = compute_treemap_layout(tools)
    assert max(c.x + c.w for c in cells) <= 752


def test_no_cell_exceeds_content_w_at_max_overflow_count() -> None:
    """30 tools must collapse into max_cells visible + a +N-more cell,
    and the rightmost edge must still fit inside 752px.
    """
    tools = [_tool(f"Tool{i:02d}", max(5000 - i * 50, 50), max(10 - i, 1)) for i in range(30)]
    cells = compute_treemap_layout(tools)
    assert max(c.x + c.w for c in cells) <= 752


def test_tier2_widths_plus_gaps_fit_content_w() -> None:
    """Tier-2 cumulative-gap bug: with three cells the old code subtracted
    the gap from each cell's allocation independently, so the row was
    always under-utilized. The fix uses a single (n-1)*gap reserve.
    """
    tools = [
        _tool("Edit", 800_000, 200, "mutate"),
        _tool("Bash", 300_000, 100, "execute"),
        _tool("Read", 200_000, 80, "explore"),
        _tool("Write", 100_000, 50, "mutate"),
    ]
    cells = compute_treemap_layout(tools)
    tier2 = [c for c in cells if c.tier == 2]
    last = max(tier2, key=lambda c: c.x + c.w)
    assert last.x + last.w <= 752


# --------------------------------------------------------------------------- #
# Floor-pressure rescale (v0.2.24 — tier-2 budget invariant)                  #
# --------------------------------------------------------------------------- #


def test_tier2_budget_invariant_under_floor_pressure() -> None:
    """Reproduces production receipt overflow: tier-2 share distribution
    95% / 3% / 2% pushed the rightmost cell past 752px because the 2%
    cell hit the 40px readability floor without a corresponding rescale
    of its larger siblings. The post-hoc rescale must restore the bound.
    """
    tools = [
        _tool("Bash", 5_000_000, 500, "execute"),  # tier-1
        _tool("Edit", 950_000, 200, "mutate"),
        _tool("Read", 30_000, 50, "explore"),
        _tool("Write", 20_000, 30, "mutate"),
    ]
    cells = compute_treemap_layout(tools)
    tier2 = [c for c in cells if c.tier == 2]
    assert len(tier2) == 3, f"expected 3 tier-2 cells, got {len(tier2)}"
    last = max(tier2, key=lambda c: c.x + c.w)
    assert last.x + last.w <= 752, f"production overflow regression: last cell ends at {last.x + last.w}"


def test_tier2_extreme_skew_triggers_rescale() -> None:
    """3 tools at 99% / 0.5% / 0.5% — both small cells hit the 40 floor
    and the largest cell would push raw_total well past usable. The
    rescale must activate, and the post-rescale sum + gaps must fit
    inside content_w. Asserts the budget bound explicitly so a future
    regression where the rescale floor of 24 breaks the bound surfaces
    as a test failure rather than a silent overflow.
    """
    tools = [
        _tool("Bash", 10_000_000, 1000, "execute"),  # tier-1
        _tool("Edit", 990_000, 100, "mutate"),
        _tool("Read", 5_000, 5, "explore"),
        _tool("Write", 5_000, 5, "mutate"),
    ]
    cells = compute_treemap_layout(tools)
    tier2 = [c for c in cells if c.tier == 2]
    assert len(tier2) == 3

    # Rescale activates: the largest cell shrinks below its un-rescaled
    # proportional width (744 * 0.99 ≈ 736).
    largest = max(tier2, key=lambda c: c.w)
    assert largest.w < 736, f"expected rescaled largest cell, got w={largest.w}"

    # Post-rescale sum invariant: sum of cell widths plus inter-cell gaps
    # must fit inside content_w. This is the budget bound; provably tight
    # when usable >= n * 24 (holds for content_w >= 80; default 752 has ~10* headroom).
    gap_px = 4
    total = sum(c.w for c in tier2) + (len(tier2) - 1) * gap_px
    assert total <= 752, f"tier-2 budget invariant broken: cells={[c.w for c in tier2]}, sum+gaps={total}"


def test_tier2_balanced_distribution_no_rescale() -> None:
    """Balanced 50/30/20 distribution — no cell hits the 40 floor, so
    the rescale path doesn't run. Guards against regressions where the
    rescale runs unnecessarily and shrinks balanced cells.
    """
    tools = [
        _tool("Bash", 5_000_000, 500, "execute"),  # tier-1
        _tool("Edit", 500_000, 200, "mutate"),
        _tool("Read", 300_000, 100, "explore"),
        _tool("Write", 200_000, 50, "mutate"),
    ]
    cells = compute_treemap_layout(tools)
    tier2 = [c for c in cells if c.tier == 2]
    assert len(tier2) == 3

    # No cell at the 40 floor → rescale didn't run → proportional widths
    # are preserved (modulo integer rounding).
    assert all(c.w > 40 for c in tier2), f"cells={[c.w for c in tier2]}"

    # Order matches descending token rank.
    assert tier2[0].name == "Edit"
    assert tier2[1].name == "Read"
    assert tier2[2].name == "Write"
    assert tier2[0].w > tier2[1].w > tier2[2].w

    # Budget invariant still holds.
    gap_px = 4
    total = sum(c.w for c in tier2) + (len(tier2) - 1) * gap_px
    assert total <= 752


def test_tier3_uniform_budget_invariant_under_max_cells() -> None:
    """Tier-3 uses uniform 90px cells with max_cells=8. Verify the budget
    invariant at maximum cell count and that the +N more overflow cell
    occupies the last visible slot. Defensive test: tier-3 is provably
    safe today (8*90 + 7*4 = 748 ≤ 752), but a future refactor that
    breaks the uniform-cell contract should fail this test.
    """
    # 1 tier-1 + 3 tier-2 + 12 tier-3 (12 > max_cells=8 → triggers +N more).
    tools = [_tool(f"Tool{i:02d}", 100_000 - i * 100, 50 - i, "coordinate") for i in range(16)]
    cells = compute_treemap_layout(tools)
    tier3 = [c for c in cells if c.tier == 3]
    assert len(tier3) <= 8, f"tier-3 exceeded max_cells: got {len(tier3)}"

    overflow = [c for c in tier3 if c.is_overflow]
    assert len(overflow) == 1, f"expected 1 +N more cell, got {len(overflow)}"

    # Budget invariant: rightmost cell edge ≤ content_w.
    rightmost = max(c.x + c.w for c in tier3)
    assert rightmost <= 752, f"tier-3 budget broken: rightmost={rightmost}"


# --------------------------------------------------------------------------- #
# Overflow handling — "+N more" cell                                          #
# --------------------------------------------------------------------------- #


def test_overflow_cell_appears_when_tools_exceed_max_cells() -> None:
    """min_w_tier3=70 + gap=4 means at content_w=752, max_cells = 10."""
    tools = [_tool(f"Tool{i:02d}", 1000 - i * 10, 5, "coordinate") for i in range(20)]
    cells = compute_treemap_layout(tools)
    overflow = [c for c in cells if c.is_overflow]
    assert len(overflow) == 1
    assert overflow[0].label.startswith("+")
    assert overflow[0].label.endswith("more")


def test_overflow_count_includes_all_hidden_tools() -> None:
    """If 20 tools and max_cells=10, last visible slot is the overflow cell,
    so 9 cells are visible and the overflow encodes 20-9 = 11 hidden."""
    tools = [_tool(f"Tool{i:02d}", 100, 1, "coordinate") for i in range(4 + 20)]  # 4 head + 20 tail
    cells = compute_treemap_layout(tools)
    tier3 = [c for c in cells if c.tier == 3]
    overflow = [c for c in tier3 if c.is_overflow]
    visible = [c for c in tier3 if not c.is_overflow]
    assert len(overflow) == 1
    # +N where N = total_tail - visible_count
    n_label = int(overflow[0].label.lstrip("+").split(" ")[0])
    assert n_label == 20 - len(visible)


def test_no_overflow_when_tools_fit_at_min_width() -> None:
    """5 tail tools at content_w=752, min_w=70 — well within max_cells=10."""
    tools = [_tool(f"Tool{i}", 100, 1, "execute") for i in range(4 + 5)]
    cells = compute_treemap_layout(tools)
    assert not any(c.is_overflow for c in cells)


# --------------------------------------------------------------------------- #
# Label truncation                                                            #
# --------------------------------------------------------------------------- #


def test_long_tier3_labels_get_ellipsized() -> None:
    """`AskUserQuestion`/`ExitPlanMode`/`TaskCreate` clipped in production.
    Verify they get truncated rather than overflowing the cell."""
    tools = [
        _tool("Edit", 1_000_000, 100, "mutate"),
        _tool("Bash", 500_000, 50, "execute"),
        _tool("Read", 300_000, 40, "explore"),
        _tool("Write", 200_000, 30, "mutate"),
        _tool("AskUserQuestion", 1000, 5, "coordinate"),
        _tool("ExitPlanMode", 1000, 5, "coordinate"),
        _tool("TaskCreate", 1000, 5, "coordinate"),
    ]
    cells = compute_treemap_layout(tools)
    tier3 = [c for c in cells if c.tier == 3]
    assert tier3, "expected tier-3 cells from this tool set"
    long_named = [c for c in tier3 if c.name in {"AskUserQuestion", "ExitPlanMode", "TaskCreate"}]
    for cell in long_named:
        # Either the label fits as-is or it's been ellipsized.
        if cell.label != cell.name:
            assert cell.label.endswith("…")
        # The label should never exceed the original name length + 1 (ellipsis).
        assert len(cell.label) <= len(cell.name) + 1


def test_truncate_label_preserves_short_names() -> None:
    assert _truncate_label("Read", cell_w=100, char_w=6) == "Read"


def test_truncate_label_ellipsizes_long_names() -> None:
    out = _truncate_label("ExtremelyLongToolName", cell_w=70, char_w=6)
    assert out.endswith("…")
    assert len(out) < len("ExtremelyLongToolName")


def test_truncate_label_handles_zero_width() -> None:
    assert _truncate_label("Edit", cell_w=10, char_w=6) == ""


# --------------------------------------------------------------------------- #
# Per-tier invariants                                                         #
# --------------------------------------------------------------------------- #


def test_tier_label_y_offsets_match_v0_2_22_baseline() -> None:
    """v0.2.22 positions: tier-1 label y=22, tier-2 y=13, tier-3 y=12.

    v0.2.23 pushed positioning out of the template into TreemapCell so
    geometry decisions live in compose/treemap.py. The VALUES match
    v0.2.22 (the architectural change is structural, not visual);
    v9-specimen-faithful tier dimensions are deferred to v0.2.24 as
    a per-genome override.
    """
    tools = [_tool(f"Tool{i}", 1000 - i * 50, 30 - i, "explore") for i in range(7)]
    cells = compute_treemap_layout(tools)
    by_tier = {c.tier: c.label_y for c in cells}
    assert by_tier[1] == 22
    assert by_tier[2] == 13
    assert by_tier[3] == 12


def test_fit_detail_to_width_returns_input_when_already_fits() -> None:
    """Wide cells leave the detail string untouched."""
    from hyperweave.compose.treemap import _fit_detail_to_width

    out = _fit_detail_to_width(cell_w=200, detail_text="4.2K · 1 calls", detail_size=8.0)
    assert out == "4.2K · 1 calls"


def test_fit_detail_to_width_truncates_with_ellipsis_on_narrow_cell() -> None:
    """Production bug (codex-small write_stdin): cell_w=68 with detail
    "4.2K · 1 calls" overflowed the cell's right edge. Per the visual
    brief, narrow cells truncate to a leading prefix + "…" rather than
    drop entirely — a partial number ("4.2K · 1…") is more useful than
    an empty cell.

    The function uses the JetBrains Mono LUT, so the result is bound to
    real font metrics rather than ``len * 0.6 * size`` multipliers.
    Trailing whitespace in the prefix is stripped so we get
    ``"4.2K · 1…"`` not ``"4.2K · 1 …"``.
    """
    from hyperweave.compose.treemap import _fit_detail_to_width

    out = _fit_detail_to_width(cell_w=68, detail_text="4.2K · 1 calls", detail_size=8.0)
    # Truncation produces an ellipsis-terminated prefix, never the full string
    assert out.endswith("…"), f"expected ellipsis-truncated string, got {out!r}"
    assert out != "4.2K · 1 calls"
    # The truncated string starts with the leading numeric (most-informative byte)
    assert out.startswith("4.2K"), f"truncation should preserve the leading numeric, got {out!r}"
    # Trailing whitespace was stripped before the ellipsis
    assert " …" not in out, f"trailing space before ellipsis is not allowed, got {out!r}"


def test_fit_detail_to_width_handles_empty_and_pathological_cells() -> None:
    """Empty input → empty output. A cell so narrow even an ellipsis
    won't fit returns empty string (template skips the line)."""
    from hyperweave.compose.treemap import _fit_detail_to_width

    assert _fit_detail_to_width(cell_w=200, detail_text="", detail_size=8.0) == ""
    # Width below 20 (padding) leaves nothing to draw
    assert _fit_detail_to_width(cell_w=10, detail_text="anything", detail_size=8.0) == ""


def test_tier3_renders_detail_at_v0_2_22_baseline() -> None:
    """v0.2.22 rendered tier-3 detail (h=24) on every cell. The brief
    height gate that suppressed it was a regression. Tier-3 cells must
    show detail again — truncated when the width is too narrow, never
    dropped because the cell is "too short".
    """
    tools = [_tool(f"Tool{i}", 1000 - i * 50, 30 - i, "explore") for i in range(7)]
    cells = compute_treemap_layout(tools)
    tier3 = [c for c in cells if c.tier == 3 and not c.is_overflow]
    assert tier3, "expected tier-3 cells from this fixture"
    for cell in tier3:
        assert cell.show_detail is True, f"tier-3 cell '{cell.name}' h={cell.h}: detail must render (v0.2.22 baseline)"
        assert cell.detail_y == 22, f"tier-3 cell '{cell.name}': detail_y must anchor to h - bottom_pad = 22"
        assert cell.detail, f"tier-3 cell '{cell.name}': detail string must be non-empty"


def test_narrow_tier2_cell_truncates_detail_instead_of_dropping() -> None:
    """Production bug (codex-small write_stdin, cell_w=68): the narrow
    cell's detail string overflowed horizontally. The fix is truncation,
    not deletion — show what fits, ellipsize the rest.

    Distribution pushes the third tier-2 cell to the ~64px range that
    reproduced the bug. Both sibling cells stay wide enough to render
    detail untruncated.
    """
    tools = [
        _tool("ExecCommand", 5_000_000, 200, "execute"),  # tier-1
        _tool("ViewImage", 600_000, 100, "explore"),  # tier-2 wide
        _tool("WriteStdin", 250_000, 50, "execute"),  # tier-2 mid
        _tool("ApplyPatch", 80_000, 1, "mutate"),  # tier-2 NARROW
    ]
    cells = compute_treemap_layout(tools)
    tier2 = sorted([c for c in cells if c.tier == 2], key=lambda c: c.x)
    assert len(tier2) == 3
    wide, mid, narrow = tier2
    assert narrow.w < 80, f"fixture should produce a narrow cell; got {narrow.w}px"
    # Narrow cell shows truncated detail with an ellipsis — NOT empty
    assert narrow.show_detail is True, (
        f"narrow tier-2 cell '{narrow.name}' (w={narrow.w}) must render detail (truncated)"
    )
    assert narrow.detail.endswith("…"), f"narrow tier-2 detail should be ellipsis-truncated, got {narrow.detail!r}"
    assert narrow.detail_y == narrow.h - 6, "tier-2 detail anchors to h - 6 (bottom_pad)"
    # Wider tier-2 cells render the full untruncated detail
    assert wide.show_detail is True
    assert not wide.detail.endswith("…"), f"wide cell should not be truncated, got {wide.detail!r}"
    assert mid.show_detail is True
    assert not mid.detail.endswith("…"), f"mid cell should not be truncated, got {mid.detail!r}"


def test_detail_y_anchors_to_cell_bottom_for_all_non_overflow_cells() -> None:
    """Architectural property: ``cell.detail_y == cell.h - _TIER_BOTTOM_PAD[tier]``
    on every non-overflow cell, regardless of whether the detail string
    was truncated.

    Detail baseline is COMPUTED from cell.h, not hardcoded. The width
    truncation gate operates on the detail STRING, not on the y-anchor —
    so the line position stays predictable across all skin variants.
    """
    from hyperweave.compose.treemap import _TIER_BOTTOM_PAD

    tools = [_tool(f"Tool{i}", 1000 - i * 50, 30 - i, "explore") for i in range(7)]
    cells = compute_treemap_layout(tools)
    for cell in cells:
        if cell.is_overflow:
            continue
        expected = cell.h - _TIER_BOTTOM_PAD[cell.tier]
        assert cell.detail_y == expected, (
            f"tier-{cell.tier} cell h={cell.h}: detail_y={cell.detail_y} should be h - bottom_pad ({expected})"
        )


def test_tier1_pct_uses_total_token_share() -> None:
    tools = [
        _tool("Edit", 800, 200, "mutate"),
        _tool("Bash", 200, 50, "execute"),
    ]
    cells = compute_treemap_layout(tools)
    tier1 = next(c for c in cells if c.tier == 1)
    # 800/(800+200) = 80%
    assert tier1.pct == 80


def test_errors_field_sums_blocked_and_errors() -> None:
    tools = [{"name": "Edit", "total_tokens": 1000, "count": 50, "tool_class": "mutate", "errors": 3, "blocked": 2}]
    cells = compute_treemap_layout(tools)
    assert cells[0].errors == 5


def test_token_skewed_distribution_gives_dominant_tier1() -> None:
    """If one tool dominates token usage (90%), it should land at tier-1."""
    tools = [
        _tool("Edit", 9_000_000, 500, "mutate"),
        _tool("Bash", 500_000, 100, "execute"),
        _tool("Read", 300_000, 80, "explore"),
        _tool("Write", 200_000, 60, "mutate"),
    ]
    cells = compute_treemap_layout(tools)
    tier1 = next(c for c in cells if c.tier == 1)
    assert tier1.name == "Edit"
    assert tier1.pct == 90


# --------------------------------------------------------------------------- #
# Format helper                                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "0"),
        (500, "500"),
        (999, "999"),
        (1000, "1.0K"),
        (1500, "1.5K"),
        (999_999, "1000.0K"),
        (1_000_000, "1.0M"),
        (1_500_000, "1.5M"),
        (183_600_000, "183.6M"),
    ],
)
def test_format_tokens(n: int, expected: str) -> None:
    assert _format_tokens(n) == expected


# --------------------------------------------------------------------------- #
# Type discipline                                                             #
# --------------------------------------------------------------------------- #


def test_treemap_cells_are_frozen_dataclasses() -> None:
    """Frozen dataclasses raise FrozenInstanceError on attribute assignment."""
    cells = compute_treemap_layout([_tool("Edit", 1000, 50, "mutate")])
    cell = cells[0]
    assert isinstance(cell, TreemapCell)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cell.x = 999  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# v0.2.21 risograph-canonical structure                                       #
# --------------------------------------------------------------------------- #


def test_tier1_carries_hero_flag_and_full_width_accent() -> None:
    """Tier-1 cells drive the 38pt hero rendering — is_hero=True, accent_w=cell_w."""
    cells = compute_treemap_layout([_tool("Edit", 1_000_000, 50, "mutate")])
    tier1 = cells[0]
    assert tier1.tier == 1
    assert tier1.is_hero is True
    assert tier1.accent_w == tier1.w == 752
    assert tier1.accent_h == 1.5
    assert tier1.accent_position == "top"


def test_tier2_and_tier3_cells_are_not_hero() -> None:
    """Only tier-1 carries the hero flag; tier-2/3 stay as standard cells."""
    tools = [_tool(f"Tool{i}", 10_000 - i * 500, 30 - i, "explore") for i in range(7)]
    cells = compute_treemap_layout(tools)
    for c in cells:
        if c.tier in (2, 3):
            assert c.is_hero is False
            assert c.accent_w == c.w
            assert c.accent_h == 1.5
            assert c.accent_position == "top"


def test_tier2_widths_proportional_to_token_share_skewed() -> None:
    """Asymmetric distribution: tier-2 widths reflect token share, not equal thirds.

    With Bash=80% / Read=15% / Write=5% of tier-2 tokens, the widths
    should be roughly 590/111/37 (within rounding tolerance).
    """
    tools = [
        _tool("Edit", 5_000_000, 100, "mutate"),  # tier-1
        _tool("Bash", 800_000, 50, "execute"),  # tier-2: 80%
        _tool("Read", 150_000, 30, "explore"),  # tier-2: 15%
        _tool("Write", 50_000, 10, "mutate"),  # tier-2: 5%
    ]
    cells = compute_treemap_layout(tools)
    tier2 = sorted([c for c in cells if c.tier == 2], key=lambda c: c.x)
    assert len(tier2) == 3
    # Bash (80%) should dominate; Read (15%) middle; Write (5%) narrowest.
    assert tier2[0].name == "Bash"
    assert tier2[1].name == "Read"
    assert tier2[2].name == "Write"
    # Bash > Read > Write by a wide margin
    assert tier2[0].w > 5 * tier2[2].w  # Bash >> Write
    assert tier2[0].w > 4 * tier2[1].w  # Bash > 4x Read


def test_tier2_widths_proportional_specimen_distribution() -> None:
    """Risograph specimen has Glob 182K / Write 151K / Edit 135K → 39%/32%/29%.
    Algorithm should produce widths near 288/238/212 (within rounding).
    """
    tools = [
        _tool("Read", 411_000, 343, "explore"),  # tier-1
        _tool("Glob", 182_000, 84, "explore"),  # 39%
        _tool("Write", 151_000, 58, "mutate"),  # 32%
        _tool("Edit", 135_000, 176, "mutate"),  # 29%
    ]
    cells = compute_treemap_layout(tools)
    tier2 = sorted([c for c in cells if c.tier == 2], key=lambda c: c.x)
    # Within ±15px of specimen widths (rounding + 40px floor tolerance).
    assert abs(tier2[0].w - 288) <= 15, f"Glob width {tier2[0].w}, expected ~288"
    assert abs(tier2[1].w - 238) <= 15, f"Write width {tier2[1].w}, expected ~238"
    assert abs(tier2[2].w - 212) <= 15, f"Edit width {tier2[2].w}, expected ~212"


def test_tier2_widths_equal_thirds_for_equal_distribution() -> None:
    """When tier-2 tokens are equal, widths are equal thirds."""
    tools = [
        _tool("Edit", 1_000_000, 100, "mutate"),  # tier-1
        _tool("Bash", 100_000, 50, "execute"),  # tier-2: 33.3%
        _tool("Read", 100_000, 50, "explore"),
        _tool("Write", 100_000, 50, "mutate"),
    ]
    cells = compute_treemap_layout(tools)
    tier2 = sorted([c for c in cells if c.tier == 2], key=lambda c: c.x)
    assert len(tier2) == 3
    # All widths within 2px of each other (int truncation noise).
    widths = [c.w for c in tier2]
    assert max(widths) - min(widths) <= 2


def test_tier3_uniform_90px_width() -> None:
    """All tier-3 cells render at exactly cell_w_tier3=90 (uniform grid)."""
    # 7 tools = tier-1 + 3 tier-2 + 3 tier-3
    tools = [_tool(f"Tool{i}", 1000 - i * 50, 5, "coordinate") for i in range(7)]
    cells = compute_treemap_layout(tools)
    tier3 = [c for c in cells if c.tier == 3]
    assert all(c.w == 90 for c in tier3), f"tier-3 widths: {[c.w for c in tier3]}"


def test_tier3_max_cells_is_eight_at_default_cell_width() -> None:
    """At cell_w=90 + gap=4, (752+4)//(90+4) = 8 visible cells max."""
    tools = [_tool(f"Tool{i}", 100, 1, "coordinate") for i in range(4 + 9)]  # 4 head + 9 tail
    cells = compute_treemap_layout(tools)
    tier3 = [c for c in cells if c.tier == 3]
    # 9 tail > 8 max → 7 visible + 1 overflow = 8 cells total.
    assert len(tier3) == 8
    overflow = [c for c in tier3 if c.is_overflow]
    visible = [c for c in tier3 if not c.is_overflow]
    assert len(overflow) == 1
    assert len(visible) == 7
    # Overflow encodes the hidden count: 9 tail - 7 visible = 2.
    n_label = int(overflow[0].label.lstrip("+").split(" ")[0])
    assert n_label == 2


def test_overflow_cell_carries_top_accent_metadata() -> None:
    """The synthesized +N more cell must populate accent_* fields like every other cell."""
    tools = [_tool(f"Tool{i}", 100, 1, "coordinate") for i in range(4 + 12)]  # forces overflow
    cells = compute_treemap_layout(tools)
    overflow = next(c for c in cells if c.is_overflow)
    assert overflow.accent_w == 90
    assert overflow.accent_h == 1.5
    assert overflow.accent_position == "top"
    assert overflow.is_hero is False
