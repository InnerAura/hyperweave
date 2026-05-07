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

from hyperweave.core.text import measure_text

# Receipt detail text is rendered via class="m" in the receipt template,
# which the assembler maps to ``font-family: var(--dna-font-mono)``. Across
# all four shipped telemetry skins (voltage / claude-code / cream / codex)
# that resolves to JetBrains Mono — the LUT we have a metric file for.
# Unknown families fall back to Inter per the ``measure_text`` contract,
# so a future skin with a different mono won't crash, just measure
# approximately.
_DETAIL_FONT_FAMILY = "JetBrains Mono"

# Horizontal padding budget reserved on each side of the detail line
# inside its cell (template renders detail at x=10 for tier-2/3 and x=14
# for tier-1; both leave at least 10px on the right). The width gate
# subtracts twice this so detail can never butt either edge.
_DETAIL_HORIZONTAL_PADDING = 20


@dataclass(frozen=True)
class TreemapCell:
    """One cell in the receipt's token treemap.

    Geometry (``x``/``y``/``w``/``h``) is content-area-relative — the
    receipt template applies a ``translate()`` to position the panel
    inside the SVG. v0.2.23 pushed all label/detail positioning out of
    the template (which previously had hardcoded y-offsets per tier)
    into per-cell fields here, so geometry decisions live in the compose
    layer and the template stays a dumb stamp.
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
    label_y: int
    """Y-offset of the label baseline within the cell."""
    label_size: float
    """Font size of the label in pixels."""
    detail_y: int
    """Y-offset of the detail baseline within the cell."""
    detail_size: float
    """Font size of the detail line in pixels."""
    show_detail: bool
    """False when the cell can't fit both label and detail without overflow."""
    pct_y: int
    """Y-offset of the tier-1 hero percentage baseline. Zero on non-hero cells."""
    pct_size: float
    """Font size of the tier-1 hero percentage. Zero on non-hero cells."""
    is_overflow: bool
    """True for the synthesized ``+N more`` cell."""
    accent_w: int
    """Accent bar width — equals ``w`` for top accent, fixed 3-4px for left accent."""
    accent_h: float
    """Accent bar height — 1.5px for top accent, equals ``h`` for left accent."""
    accent_position: str
    """``"top"`` (v0.2.21 risograph) or ``"left"`` (v9 codex specimen)."""
    is_hero: bool
    """True for tier-1 cells; drives the hero percentage rendering in the template."""


# ── Per-tier typography ──
# Label baseline y is tier-anchored (top-of-cell positioning).
# Detail baseline y is COMPUTED ADAPTIVELY via _TIER_BOTTOM_PAD below.
_TIER_LABEL_Y: dict[int, int] = {1: 22, 2: 13, 3: 12}
_TIER_LABEL_SIZE: dict[int, float] = {1: 13.0, 2: 9.5, 3: 9.0}
_TIER_DETAIL_SIZE: dict[int, float] = {1: 10.0, 2: 8.0, 3: 8.0}

# Per-tier baseline distance from cell BOTTOM. The detail line always
# anchors to the cell's lower edge: ``detail_y = cell.h - bottom_pad``.
# v0.2.22 baseline (preserved exactly):
#   tier-1 h=88 bottom_pad=8  → detail_y=80
#   tier-2 h=32 bottom_pad=6  → detail_y=26
#   tier-3 h=24 bottom_pad=2  → detail_y=22
# Width overflow is handled by :func:`_fit_detail_to_width`, which
# ellipsizes the detail STRING in place — never drops the line.
# A snug-but-readable detail beats a missing one; truncation preserves
# the leading numeric (``"4.2K · 1…"``) where dropping discards it.
_TIER_BOTTOM_PAD: dict[int, int] = {1: 8, 2: 6, 3: 2}

# Tier-1 hero percentage — matches v0.2.22 template hardcode (y=66 size=38).
_TIER1_PCT_Y: int = 66
_TIER1_PCT_SIZE: float = 38.0

# Per-tier character widths used by :func:`_truncate_label`.
_TIER_CHAR_W: dict[int, int] = {1: 8, 2: 6, 3: 6}


def _fit_detail_to_width(cell_w: int, detail_text: str, detail_size: float) -> str:
    """Truncate ``detail_text`` with an ellipsis to fit ``cell_w`` minus padding.

    Returns the original string when it already fits; otherwise returns
    the longest prefix that fits alongside a trailing ``…``. Trailing
    whitespace is stripped from the prefix so we get ``"4.2K · 1…"``
    rather than ``"4.2K · 1 …"``. Empty input returns an empty string.

    Architectural intent: a cell showing partial information
    (``"4.2K · 1…"``) is more useful than an empty cell. An earlier
    revision of this gate dropped detail entirely on cells that didn't
    fit; the v0.2.22 baseline kept detail on every cell, sometimes
    browser-clipped. This function makes truncation explicit and
    ellipsized rather than silently clipped or dropped — and removes
    the height gate that mistakenly suppressed tier-3 detail.

    Width measurements come from real per-font-family LUTs in
    :mod:`hyperweave.core.text` — no ``len(text) * 0.6 * font_size``
    magic multipliers. The receipt template renders detail with
    ``class="m"`` → ``var(--dna-font-mono)``, which all four shipped
    telemetry skins resolve to JetBrains Mono. Unknown families fall
    back to Inter metrics with a one-shot warning (per the
    ``measure_text`` contract), so a future skin with a different mono
    font truncates approximately rather than crashing.
    """
    if not detail_text:
        return ""
    available = cell_w - _DETAIL_HORIZONTAL_PADDING
    if available <= 0:
        return ""
    full_w = measure_text(
        detail_text,
        font_family=_DETAIL_FONT_FAMILY,
        font_size=detail_size,
    )
    if full_w <= available:
        return detail_text
    ellipsis = "…"
    ellipsis_w = measure_text(
        ellipsis,
        font_family=_DETAIL_FONT_FAMILY,
        font_size=detail_size,
    )
    if available < ellipsis_w:
        return ""
    # Linear scan from the longest viable prefix downward. O(n²) on
    # length, but n ≤ ~30 for token/call labels — a binary search would
    # add code without measurable gain. Linear order also stops at the
    # first fit, so the typical narrow-cell case (~10 chars) is fast.
    for length in range(len(detail_text) - 1, 0, -1):
        prefix = detail_text[:length]
        prefix_w = measure_text(
            prefix,
            font_family=_DETAIL_FONT_FAMILY,
            font_size=detail_size,
        )
        if prefix_w + ellipsis_w <= available:
            return prefix.rstrip() + ellipsis
    return ellipsis


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
    label_y = _TIER_LABEL_Y[tier]
    label_size = _TIER_LABEL_SIZE[tier]
    detail_size = _TIER_DETAIL_SIZE[tier]
    # ── Truncate, never drop ──
    # Visual baseline (v0.2.22) kept detail on every cell; the height
    # gate that briefly replaced this was an over-correction. A snug
    # tier-3 line (h=24) is more useful than a missing one. Width is
    # the only real overflow risk now, and we resolve it by ellipsizing
    # the detail string in place rather than dropping the whole line.
    detail = _fit_detail_to_width(w, detail, detail_size)
    show_detail = bool(detail)
    detail_y = h - _TIER_BOTTOM_PAD[tier]
    pct_y = _TIER1_PCT_Y if tier == 1 else 0
    pct_size = _TIER1_PCT_SIZE if tier == 1 else 0.0
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
        label_y=label_y,
        label_size=label_size,
        detail_y=detail_y,
        detail_size=detail_size,
        show_detail=show_detail,
        pct_y=pct_y,
        pct_size=pct_size,
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
                label_y=_TIER_LABEL_Y[3],
                label_size=_TIER_LABEL_SIZE[3],
                detail_y=h - _TIER_BOTTOM_PAD[3],
                detail_size=_TIER_DETAIL_SIZE[3],
                show_detail=False,
                pct_y=0,
                pct_size=0.0,
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
