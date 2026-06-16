"""Rhythm-bar layout: time-proportional x/w with uniform heights.

Shared between :func:`resolve_receipt` and :func:`resolve_rhythm_strip`
so the receipt's "79-stage bars overflow the track" bug can't diverge
from rhythm-strip's correct two-pass algorithm.

Algorithm (two passes):
    1. Reserve a gap budget up front so ``n_bars x gap_px`` never steals
       from the width budget. Compute a minimum bar width floor based on
       ``n_bars`` so each bar is still visible under extreme stage counts.
    2. Raw widths: time-proportional when every stage carries ISO
       ``start``/``end`` timestamps (preferred — the time-axis labels
       then agree with the bar positions); fall back to tool-call-share
       pct when timestamps are missing (legacy contract).
    3. Post-hoc uniform rescale if the raw sum still exceeds the gap
       budget (happens when the min-bar-width floor dominates).
    4. Emit ``{x, y, w, h, tool_class}`` with ``h = BAR_HEIGHT`` uniform.

Uniform height is intentional. The old resolver's
``h = max(int(bar_area_h * (pct / 50)), 8)`` made ~76 of 79 bars hit
the 8px floor, implying a signal dimension the data didn't carry.
Three channels (time x category x color) is already enough; the
fourth (height) had no clear semantic and was therefore noise.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

BAR_HEIGHT = 14
"""Uniform rhythm-bar height. Shared by receipt (area_h=92) and rhythm-strip
(area_h=42): both align the bars flush to the bottom of their track."""


def layout_rhythm_bars(
    stages: list[dict[str, Any]],
    area_w: int,
    area_h: int,
    gap_px: int = 2,
) -> list[dict[str, Any]]:
    """Lay out rhythm bars into a bounded track with a gap budget + rescale.

    Args:
        stages: Normalized stage dicts. Each MAY carry ``start``/``end``
            ISO strings for time-proportional layout; otherwise layout
            falls back to ``pct`` (tool-call share).
        area_w: Track width in pixels.
        area_h: Track height in pixels. Used only for ``y`` (bars align
            bottom-flush); ``h`` is always :data:`BAR_HEIGHT`.
        gap_px: Inter-bar gap in pixels. Reserved upfront in the budget
            so many-stage sessions don't overflow into adjacent panels.

    Returns:
        One dict per stage: ``{x, y, w, h, tool_class}``. Empty list when
        ``stages`` is empty.
    """
    if not stages:
        return []

    n = len(stages)
    gap_budget = gap_px * max(n - 1, 0)
    # Cap the worst case: never give up more than half the track to gaps.
    available_w = max(area_w - gap_budget, area_w // 2)

    has_timestamps = all(s.get("start") and s.get("end") for s in stages)
    if has_timestamps:
        t0 = datetime.fromisoformat(stages[0]["start"])
        t_end = datetime.fromisoformat(stages[-1]["end"])
        total_s = max((t_end - t0).total_seconds(), 1.0)
        raw_w = [
            max(
                int(
                    available_w
                    * (datetime.fromisoformat(s["end"]) - datetime.fromisoformat(s["start"])).total_seconds()
                    / total_s
                ),
                2,
            )
            for s in stages
        ]
    else:
        total_pct = sum(s.get("pct", 0) for s in stages) or 100
        # Per-bar minimum: 1/3 of the equal-share width so tiny stages
        # stay visible without swallowing the whole budget.
        min_bar_w = max(2, available_w // max(n, 1) // 3)
        raw_w = [max(int(available_w * s.get("pct", 0) / total_pct), min_bar_w) for s in stages]

    # Post-hoc uniform rescale: if the floor pressure drove the sum over budget.
    raw_total = sum(raw_w)
    if raw_total > available_w and raw_total > 0:
        scale = available_w / raw_total
        raw_w = [max(int(w * scale), 2) for w in raw_w]

    y = area_h - BAR_HEIGHT
    bars: list[dict[str, Any]] = []
    rx = 0
    for s, w in zip(stages, raw_w, strict=True):
        bars.append(
            {
                "x": rx,
                "y": y,
                "w": w,
                "h": BAR_HEIGHT,
                "tool_class": s.get("tool_class", s.get("dominant_class", "explore")),
            }
        )
        rx += w + gap_px
    return bars
