"""Treemap layout for the receipt's token-map panel.

Three-tier layout matching the risograph specimen
(``tier2/telemetry/telemetry-redesign/receipt-genome-risograph.svg``):

* Tier 1 — dominant tool, full content width (752px), 88px tall, hero
  metric (38pt percentage in tool-class color).
* Tier 2 — tools[1:4], **proportional widths** from token share,
  uniform 32px tall. Specimen widths 288/238/212 are illustrations of
  what proportional math produces for that specific distribution —
  hardcoding them would break for other token distributions.
* Tier 3 — tools[4:], **uniform 90x24 cells** (max 8 across the track:
  8x90 + 7x4 = 748 ≤ 752). Beyond 8 tools, a ``+N more`` overflow cell
  collapses the tail.

Each cell carries a full-width 1.5px **top accent** in the tool-class
color (replacing the older left-side 4px accent). The accent geometry
fields (``accent_w``, ``accent_h``, ``accent_position``) are populated
here so the template stays pure-render.

Two cell-shape additions from v0.2.21:

* ``is_hero``: True only for tier-1, drives the 38pt percentage and
  larger label font in the template.
* ``accent_w``/``accent_h``/``accent_position``: full-width top accent
  bar geometry. Always ``"top"`` for risograph-canonical structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TreemapCell:
    """One cell in the receipt's token treemap.

    Geometry (``x``/``y``/``w``/``h``) is content-area-relative — the
    receipt template applies a ``translate()`` to position the panel
    inside the SVG. The ``text_y`` field carries the label y-offset
    that previously lived as an inline tier branch in the template.
    """

    tier: int
    x: int
    y: int
    w: int
    h: int
    name: str
    """Raw tool name (also used by ``data-hw-tool`` attributes)."""
    label: str
    """Display label, ellipsized to fit the cell width."""
    pct: int
    detail: str
    tool_class: str
    errors: int
    text_y: int
    """Tier-derived label y-offset. Was inline ``y="22 if tier==1 else 13 ..."``."""
    is_overflow: bool
    """True for the synthesized ``+N more`` cell."""
    accent_w: int
    """Top accent bar width — always equals cell ``w`` (full-width risograph treatment)."""
    accent_h: float
    """Top accent bar height — always 1.5px for risograph spec."""
    accent_position: str
    """Always ``"top"`` for v0.2.21 risograph-canonical structure."""
    is_hero: bool
    """True for tier-1 cells; drives the 38pt hero percentage rendering in the template."""


# Tier-derived label y-offsets — were template-side branches before centralization.
_TIER_TEXT_Y: dict[int, int] = {1: 22, 2: 13, 3: 12}

# Per-tier character widths used by :func:`_truncate_label`.
# Matches the receipt template's font-size mapping (tier 1 = 13px, others = 9px).
_TIER_CHAR_W: dict[int, int] = {1: 8, 2: 6, 3: 6}


def _format_tokens(n: int) -> str:
    """Format a token count for compact display (``1500 → '1.5K'``).

    Mirrors :func:`hyperweave.compose.resolver._fmt_tok`. Kept private
    here so the helper has no resolver dependency and unit tests can run
    against ``compose/treemap.py`` in isolation.
    """
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


def _truncate_label(text: str, cell_w: int, char_w: int = 6, padding: int = 24) -> str:
    """Ellipsize ``text`` so it fits within ``cell_w`` pixels.

    Args:
        text: Source label.
        cell_w: Cell width in pixels.
        char_w: Estimated character width at the target font size
            (~6 for font-size 9, ~8 for font-size 13 in SF Pro / Inter).
        padding: Combined left+right cell padding plus a safety margin
            so the ellipsis never butts against the cell border.

    Returns:
        The original ``text`` if it already fits, otherwise the longest
        prefix that fits with a trailing ``…``. Returns the empty string
        when ``cell_w`` cannot accommodate even one character.
    """
    available = cell_w - padding
    if available < char_w:
        return ""
    max_chars = available // char_w
    if max_chars < 2:
        return text[:1] if text else ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


_LEFT_ACCENT_W: dict[int, int] = {1: 4, 2: 3, 3: 3}
"""Per-tier accent stripe width for left-position rendering. Matches the
claude-code v9 specimen: tier-1 cells get a 4px stripe, tier-2/3 get 3px."""


def _make_cell(
    *,
    tier: int,
    tool: dict[str, Any],
    x: int,
    y: int,
    w: int,
    h: int,
    pct: int,
    detail: str,
    accent_position: str = "top",
) -> TreemapCell:
    """Build a :class:`TreemapCell` from a normalized tool dict."""
    name = tool.get("name", "")
    if accent_position == "left":
        # Vertical stripe on the LEFT edge spanning full cell height.
        accent_w_val = _LEFT_ACCENT_W.get(tier, 3)
        accent_h_val: float = float(h)
    else:
        # Horizontal stripe across the TOP edge spanning full cell width.
        accent_w_val = w
        accent_h_val = 1.5
    return TreemapCell(
        tier=tier,
        x=x,
        y=y,
        w=w,
        h=h,
        name=name,
        label=_truncate_label(name, w, char_w=_TIER_CHAR_W[tier]),
        pct=pct,
        detail=detail,
        tool_class=tool.get("tool_class", "coordinate"),
        errors=int(tool.get("blocked", 0)) + int(tool.get("errors", 0)),
        text_y=_TIER_TEXT_Y[tier],
        is_overflow=False,
        accent_w=accent_w_val,
        accent_h=accent_h_val,
        accent_position=accent_position,
        is_hero=(tier == 1),
    )


def _layout_tier3(
    tail_tools: list[dict[str, Any]],
    *,
    content_w: int,
    y: int,
    h: int,
    gap_px: int,
    cell_w: int,
    accent_position: str = "top",
) -> list[TreemapCell]:
    """Lay out tier-3 cells at a uniform 90x24 (cell_w x h) and emit ``+N more`` overflow.

    Risograph-canonical structure: every tier-3 cell is the same size; the
    track holds at most ``max_cells = (content_w + gap) // (cell_w + gap)``
    cells (8 at the default 752/90/4 budget). Beyond that, a ``+N more``
    cell collapses the tail. The trailing right-edge gap stays empty when
    there are fewer cells than max — preserves the spec's grid feel
    rather than stretching a 5-tool tail across the whole row.
    """
    n_tail = len(tail_tools)
    if n_tail == 0:
        return []

    max_cells = (content_w + gap_px) // (cell_w + gap_px)
    if max_cells < 1:
        max_cells = 1

    if n_tail > max_cells:
        # Reserve the last visible slot for a "+N more" cell.
        visible = list(tail_tools[: max_cells - 1])
        overflow_count = n_tail - len(visible)
    else:
        visible = list(tail_tools)
        overflow_count = 0

    cells: list[TreemapCell] = []
    x = 0
    for t in visible:
        cells.append(
            _make_cell(
                tier=3,
                tool=t,
                x=x,
                y=y,
                w=cell_w,
                h=h,
                pct=0,
                detail=f"{t.get('count', 0)} calls",
                accent_position=accent_position,
            ),
        )
        x += cell_w + gap_px

    if overflow_count:
        if accent_position == "left":
            ov_accent_w = _LEFT_ACCENT_W.get(3, 3)
            ov_accent_h: float = float(h)
        else:
            ov_accent_w = cell_w
            ov_accent_h = 1.5
        cells.append(
            TreemapCell(
                tier=3,
                x=x,
                y=y,
                w=cell_w,
                h=h,
                name=f"+{overflow_count} more",
                label=f"+{overflow_count} more",
                pct=0,
                detail="",
                tool_class="coordinate",
                errors=0,
                text_y=_TIER_TEXT_Y[3],
                is_overflow=True,
                accent_w=ov_accent_w,
                accent_h=ov_accent_h,
                accent_position=accent_position,
                is_hero=False,
            ),
        )

    return cells


def compute_treemap_layout(
    tools: list[dict[str, Any]],
    content_w: int = 752,
    *,
    tier_y: tuple[int, int, int] = (22, 118, 154),
    tier_h: tuple[int, int, int] = (88, 32, 24),
    gap_px: int = 4,
    cell_w_tier3: int = 90,
    accent_position: str = "top",
) -> list[TreemapCell]:
    """Lay out the receipt's three-tier token treemap (risograph-canonical).

    Args:
        tools: Normalized tool dicts. Each tool MUST carry ``name``
            (str), ``count`` (int), and either ``total_tokens`` (preferred
            for sizing) or fallback to ``count``. Optional fields:
            ``tool_class`` (str — defaults to ``"coordinate"``),
            ``errors``/``blocked`` (int).
        content_w: Track width in pixels. The default 752 matches the
            receipt's 800px canvas with 24px horizontal margins.
        tier_y: Y offsets per tier (1, 2, 3) inside the panel. Defaults
            match the risograph specimen: tier-1 at y=22 (just below
            the header row), tier-2 at y=118 (88+8 gap), tier-3 at y=154.
        tier_h: Heights per tier. Defaults match the spec: 88/32/24.
        gap_px: Inter-cell gap. Reserved upfront in the budget so the
            rightmost cell can never overflow the track.
        cell_w_tier3: Uniform tier-3 cell width. Default 90 yields
            ``max_cells = (752+4) // (90+4) = 8`` visible cells across
            the track — matches the risograph spec's 8-cell tail row.

    Returns:
        List of :class:`TreemapCell` with all geometry and display strings
        computed. Empty list when ``tools`` is empty.
    """
    if not tools:
        return []

    sorted_tools = sorted(
        tools,
        key=lambda t: t.get("total_tokens", t.get("count", 0)),
        reverse=True,
    )
    total_tool_tokens = sum(t.get("total_tokens", t.get("count", 0)) for t in sorted_tools) or 1

    cells: list[TreemapCell] = []

    # Tier 1 — dominant tool, full width.
    top = sorted_tools[0]
    top_tokens = top.get("total_tokens", top.get("count", 0))
    cells.append(
        _make_cell(
            tier=1,
            tool=top,
            x=0,
            y=tier_y[0],
            w=content_w,
            h=tier_h[0],
            pct=round(top_tokens / total_tool_tokens * 100),
            detail=f"{_format_tokens(top_tokens)} · {top.get('count', 0)} calls",
            accent_position=accent_position,
        ),
    )

    # Tier 2 — tools[1:4], proportional widths.
    # Bug fix: gap budget reserved once (n-1)*gap, not subtracted per cell.
    mid_tools = sorted_tools[1:4]
    if mid_tools:
        n = len(mid_tools)
        total_gaps = (n - 1) * gap_px
        usable = content_w - total_gaps
        mid_total = sum(t.get("total_tokens", t.get("count", 0)) for t in mid_tools) or 1

        x = 0
        for i, t in enumerate(mid_tools):
            t_tokens = t.get("total_tokens", t.get("count", 0))
            share = t_tokens / mid_total
            w = max(int(usable * share), 40)
            cells.append(
                _make_cell(
                    tier=2,
                    tool=t,
                    x=x,
                    y=tier_y[1],
                    w=w,
                    h=tier_h[1],
                    pct=round(t_tokens / total_tool_tokens * 100),
                    detail=f"{_format_tokens(t_tokens)} · {t.get('count', 0)} calls",
                    accent_position=accent_position,
                ),
            )
            x += w + (gap_px if i < n - 1 else 0)

    # Tier 3 — tools[4:], uniform 90x24 with "+N more" overflow.
    tail_tools = sorted_tools[4:]
    if tail_tools:
        cells.extend(
            _layout_tier3(
                tail_tools,
                content_w=content_w,
                y=tier_y[2],
                h=tier_h[2],
                gap_px=gap_px,
                cell_w=cell_w_tier3,
                accent_position=accent_position,
            ),
        )

    return cells
