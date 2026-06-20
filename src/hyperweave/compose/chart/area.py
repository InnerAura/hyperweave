"""Context-load burn-curve area layout for the receipt's occupancy panel.

This module produces the geometry for a **context-window occupancy curve** — a
filled area + stroke line tracing how much of a model's context window is
consumed over a session, punctuated by *reset events* (``/compact``, ``/clear``,
auto-compaction) where the occupancy drops vertically.

Pure geometry, no chrome
========================
The layout emits ``d`` path strings, marker coordinates, tick positions, and
text labels — **no colors, no SVG strings, no genome logic**. The plot box and
every fill/stroke is supplied by the caller (resolver → template). This is the
reusable down-payment the brief calls for: the receipt consumes it now, the
future chart-frame ``area`` kind consumes the same code later.

The occupancy curve is MODELLED, not sampled
============================================
Transcripts don't record per-minute occupancy — they record *reset events*
(``{min, cmd, to}``) and a global ``peak_ctx``. The curve between two resets is
synthesised: a smooth cubic-bezier rise from the post-reset ``to`` value toward
the window ceiling, then a vertical ``L`` jump down to the next segment's ``to``
at the reset minute. The segment that contains the global peak reaches exactly
``peak_ctx``; the others rise proportionally less. This matches the hand-authored
specimen at
``v04/specimens/receipts/receipts-v3/receipt_primer-noir-v3.svg`` (lines 188-189),
whose path rises via beziers and drops via ``L`` at each reset x.

Coordinate model (group-local, the receipt translates this to (24,350))
=======================================================================
Two linear maps, both pinned by the specimen::

    y(occ) = plot_top + (1 - occ / window) * plot_h     # occ=window→top, occ=0→bottom
    x(min) = plot_left + (min / span_min) * plot_w     # min=0→left, min=span_min→right

For the default ``plot_box=(34, 22, 718, 116)`` the inner plot area is
``x∈[34, 752]`` and ``y∈[38, 138]`` (a 16px top inset so the ceiling sits inside
the panel with breathing room above; zero bottom inset, so the baseline rides the
panel's bottom edge and the error/time ticks extend below it), so ``y(window)=38``
and ``y(0)=138``. The curve has no on-panel peak marker — it rises to its apex and
ends; the header's '{peak} PEAK' carries the value.

``span_min`` is the session's **elapsed wall-clock span** (first activity → last),
NOT the active-work sum: reset events are timestamped on the wall clock, so the
x-axis must run on the same clock or events logged after a long idle gap crush
onto the right rail. A session resumed across days has a large span but few
active minutes (the hero carries that separate "active" stat).

Extremes (the explicit quality bar)
===================================
* **0 resets** → one smooth rising segment to ``peak_ctx``, no vertical drop.
* **Many resets** → reset glyphs are min-spaced; when two events fall within
  :data:`MIN_GLYPH_GAP_PX` the later glyph is nudged right so the marks never
  overlap (the curve's drop x is unchanged — only the glyph's draw x moves).
* **span_min small/large** → time ticks adapt: a 120m tick is only emitted
  when ``span_min >= 120``; the terminal ``span_min`` tick is always emitted
  (and absorbs a regular tick that would collide with it).
* **no errors** → empty ``error_ticks``. Many errors are de-collided to
  :data:`MIN_ERROR_GAP_PX`; if they can't fit the plot width, the overflow is
  reported as :attr:`ContextLoadLayout.dropped_errors` rather than silently
  clipped (the caller surfaces a disclosure).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, TypedDict

from hyperweave.core.text import format_duration, measure_text

LegendKind = Literal["line", "compact", "clear", "auto", "error"]
"""Swatch glyph selector for a legend item."""

# --------------------------------------------------------------------------- #
# Module constants                                                            #
# --------------------------------------------------------------------------- #

ResetKind = Literal["compact", "clear", "auto"]
"""The three context-reset event kinds. ``compact`` = ``/compact`` (chevron),
``clear`` = ``/clear`` (hollow circle), ``auto`` = auto-compaction (diamond)."""

_CMD_TO_KIND: dict[str, ResetKind] = {
    "compact": "compact",
    "clear": "clear",
    "auto": "auto",
}
"""Maps a payload event's ``cmd`` to its glyph kind. Unknown commands fall back
to ``compact`` (the most common reset) so an unexpected slash-command still
renders a mark rather than crashing."""

PLOT_TOP_INSET = 16.0
"""Vertical inset from the panel's top edge to the window-ceiling line — a top
margin so the ceiling line sits *inside* the panel with breathing room above it
(an apex that brushes the ceiling doesn't crowd the panel's top edge).
``plot_box.y + inset`` = ``y(window)``."""

PLOT_BOTTOM_INSET = 0.0
"""Inset from the panel's bottom edge to the baseline (occ=0) rule — zero: the
baseline sits ON the panel's bottom edge, and the error + time ticks extend below
it into the axis margin. The default box (y22, h116) → ceiling y38, baseline y138."""

HEADER_Y = 10.0
"""Baseline y of the header text row ('CONTEXT LOAD · …K WINDOW · …m')."""

TICK_LABEL_Y_GAP = 12.0
"""Gap below the baseline to the time-tick label baseline (baseline y + this)."""

TICK_MARK_LEN = 4.5
"""Length of a time-tick mark below the baseline (specimen: 126→130.5)."""

AXIS_LABEL_X = 28.0
"""Right-anchored x for the left y-axis labels (window / mid / 0)."""

AXIS_LABEL_FONT = "Inter"
AXIS_LABEL_SIZE = 7.5
"""Font for left y-axis + header labels — drives real text measurement so the
header right-block lays out without overlap regardless of digit count."""

TICK_LABEL_SIZE = 8.0
"""Font size for the time-tick labels along the bottom axis."""

TICK_TARGET_COUNT = 5
"""Target number of interior+origin ticks the adaptive interval aims for. The
chosen 'nice' step yields roughly this many evenly-spaced labels regardless of
``span_min`` (5 ticks reads cleanly from a 1-minute to a multi-day session)."""

TICK_NICE_STEPS_MIN: tuple[float, ...] = (
    1.0,
    2.0,
    5.0,
    10.0,
    15.0,
    30.0,
    60.0,  # 1h
    120.0,  # 2h
    180.0,  # 3h
    300.0,  # 5h
    600.0,  # 10h
    720.0,  # 12h
    1440.0,  # 1d
    2880.0,  # 2d
    7200.0,  # 5d
    14400.0,  # 10d
)
"""Clean tick-interval candidates (minutes). The adaptive selector snaps the
ideal ``span_min / TICK_TARGET_COUNT`` step up to the nearest of these so axis
labels land on readable boundaries (whole hours/days), spanning 1m → 10d."""

MIN_TICK_GAP_PX = 34.0
"""Minimum horizontal spacing between adjacent time-tick label centres. The
adaptive selector guarantees the regular interval clears this; the terminal-
collision guard drops a regular tick that lands within this of the terminal."""

MIN_GLYPH_GAP_PX = 10.0
"""Minimum horizontal spacing between adjacent reset-glyph draw centres. When
two events crowd closer, the later glyph is nudged right to this floor."""

MIN_ERROR_GAP_PX = 3.0
"""Minimum horizontal spacing between adjacent error ticks — small (the ticks are
thin) so clustered errors stay near their real times rather than spreading."""

ERROR_TICK_LEN = 5.5
"""Length of an error tick — a short vertical mark in the axis margin BELOW the
baseline. Errors are time-events (anchored to WHEN, like reset glyphs), so they
rise from the time axis rather than sit on the occupancy-value baseline, where
baseline dots collided with the low curve at session start."""

ERROR_TICK_WIDTH = 1.4
"""Stroke width of an error tick."""

GLYPH_CHEVRON_W = 3.5
"""Half-width of a compact chevron's 3-point polyline (specimen: ±3.5 about x)."""

GLYPH_CHEVRON_H = 4.0
"""Vertical drop of a compact chevron's middle vertex."""

GLYPH_CIRCLE_R = 2.6
"""Radius of a clear-event hollow circle (specimen: r=2.6)."""

GLYPH_DIAMOND_R = 2.0
"""Half-diagonal of an auto-event diamond glyph."""

GLYPH_LIFT = 6.0
"""How far above the curve point a reset glyph's *anchor* sits, before the
per-kind offset. Keeps the mark clear of the stroke (specimen chevron tip rides
~6px above the curve vertex)."""

LEGEND_SWATCH_Y = 3.0
"""Legend row: swatch/glyph y offset below the legend baseline group origin."""

LEGEND_LABEL_GAP = 4.0
"""Gap between a legend swatch's right edge and its text label."""

LEGEND_ITEM_GAP = 18.0
"""Horizontal gap between the end of one legend item's label and the next swatch."""

LEGEND_FONT = "Inter"
LEGEND_FONT_SIZE = 8.5
"""Font for legend item labels."""

LEGEND_LINE_SWATCH_W = 10.0
"""Width of the 'context' legend's line swatch."""


# --------------------------------------------------------------------------- #
# Input shape                                                                 #
# --------------------------------------------------------------------------- #


class ResetEvent(TypedDict):
    """One context-reset event from the ``receipt/1`` payload's ``context.events``.

    ``min`` — minutes into the session the reset fired.
    ``cmd`` — one of ``compact`` / ``clear`` / ``auto`` (other values → compact).
    ``to``  — context occupancy (absolute tokens) immediately *after* the reset.
    """

    min: float
    cmd: str
    to: float


# --------------------------------------------------------------------------- #
# Output dataclasses                                                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AxisLine:
    """A horizontal y-axis gridline + its right-anchored label.

    ``dashed`` selects the stroke style (window ceiling + mid gridlines are
    dashed, the occ=0 baseline is solid). ``emphatic`` flags the window-ceiling
    line so the template can render it brighter (specimen: ceiling at 0.35 vs
    mid at 0.07 opacity)."""

    y: float
    x1: float
    x2: float
    label: str
    label_x: float
    label_y: float
    dashed: bool
    emphatic: bool


@dataclass(frozen=True, slots=True)
class TimeTick:
    """A vertical time-tick: a short mark below the baseline + a label.

    ``label_anchor`` is ``"start"`` for the 0m tick, ``"end"`` for the terminal
    ``span_min`` tick, ``"middle"`` for interior ticks — matching the specimen
    so edge labels don't overhang the plot."""

    x: float
    mark_y1: float
    mark_y2: float
    label: str
    label_y: float
    label_anchor: Literal["start", "middle", "end"]
    gridline: bool
    """True when this tick also draws a faint full-height gridline up the plot."""
    gridline_y1: float
    gridline_y2: float


@dataclass(frozen=True, slots=True)
class ResetMarker:
    """A typed reset glyph riding on the occupancy curve.

    ``x`` is the curve's drop x (the true event position, used for the vertical
    path jump); ``draw_x`` is where the *glyph* is centred after de-collision —
    equal to ``x`` unless an earlier crowded neighbour pushed it right.
    ``y`` is the curve y at the pre-reset peak (the top of the segment the glyph
    annotates). ``kind`` selects the glyph shape in the template."""

    x: float
    draw_x: float
    y: float
    kind: ResetKind
    minute: float
    to_value: float


@dataclass(frozen=True, slots=True)
class ErrorTick:
    """One error tick — a short vertical mark in the axis margin at the error's
    real minute (de-collided along x). ``y1``→``y2`` is the tick's vertical span
    just below the baseline."""

    x: float
    y1: float
    y2: float


@dataclass(frozen=True, slots=True)
class LegendItem:
    """One legend entry: a typed swatch + a measured-width text label.

    ``kind`` selects the swatch glyph: ``line`` (context), ``compact``/``clear``/
    ``auto`` (the reset glyphs), ``error`` (red dot). ``swatch_x`` is the swatch's
    left edge / centre per kind; ``label_x`` is measured so labels never collide
    with the next item's swatch."""

    kind: LegendKind
    swatch_x: float
    label: str
    label_x: float


@dataclass(frozen=True, slots=True)
class HeaderText:
    """The header row strings + their x anchors.

    Left block: an eyebrow ('CONTEXT LOAD') + a continuation
    ('· {window}K WINDOW · {span_min}m'). Right block (end-anchored, laid out
    right-to-left via measurement): '{peak}K PEAK' + a dim '·' + '{N} RESETS'.
    When ``resets == 0`` the reset clause is suppressed (``resets_label`` empty)."""

    eyebrow: str
    eyebrow_x: float
    detail: str
    detail_x: float
    peak_label: str
    peak_label_x: float
    sep_x: float
    resets_label: str
    resets_label_x: float
    y: float


@dataclass(frozen=True, slots=True)
class ContextLoadLayout:
    """Complete geometry for the context-load burn-curve panel.

    Every coordinate is group-local (the receipt translates the whole panel to
    ``(24, 350)``). The template stamps these values and supplies all colour.
    """

    area_path: str
    """``d`` for the filled area (rises via beziers, drops via ``L``, closed to
    the baseline)."""
    line_path: str
    """``d`` for the stroke line (same rise/drop, open — not closed)."""
    ceiling_line: AxisLine
    """The window-ceiling line (dashed, emphatic) + its label."""
    gridlines: list[AxisLine]
    """Interior horizontal gridlines (e.g. the mid 100K line) + labels."""
    baseline: AxisLine
    """The occ=0 baseline rule + its '0' label."""
    time_ticks: list[TimeTick]
    """Bottom-axis time ticks (0m … span_min), de-collided at the terminal."""
    reset_markers: list[ResetMarker]
    """Typed reset glyphs on the curve, de-collided in draw_x."""
    error_ticks: list[ErrorTick]
    """Time-axis error ticks, de-collided; count may be < the error total (see dropped)."""
    dropped_errors: int
    """How many error ticks couldn't fit the plot width after de-collision. The
    caller surfaces this as a disclosure rather than silently clipping."""
    legend: list[LegendItem]
    """Legend row items (context / window-ceiling / compact / clear / auto / error)."""
    legend_y: float
    """Baseline y of the legend row (group-local)."""
    header: HeaderText
    """Header text strings + x anchors."""
    plot_left: float
    plot_right: float
    plot_top: float
    plot_bottom: float
    """The inner plot rectangle the curve lives in (group-local)."""


# --------------------------------------------------------------------------- #
# Coordinate maps                                                             #
# --------------------------------------------------------------------------- #


def _format_k(tokens: float) -> str:
    """Format an occupancy value as a compact 'NK' / 'NM' label.

    Context windows are reported in thousands; values are rounded to the nearest
    1K below 1M and 0.1M above, matching the specimen's '200K' / '196K' labels.
    """
    if tokens >= 1_000_000:
        m = tokens / 1_000_000
        return f"{m:.0f}M" if m >= 10 else f"{m:.1f}M"
    return f"{round(tokens / 1000)}K"


def _y_for_occ(occ: float, plot_top: float, plot_h: float, window: float) -> float:
    """Map an occupancy (absolute tokens) to a group-local y coordinate.

    Linear: ``occ=window`` → ``plot_top``; ``occ=0`` → ``plot_top + plot_h``.
    Values above the window clamp to the ceiling (a post-reset ``to`` should
    never exceed the window, but a malformed payload shouldn't punch through).
    """
    frac = occ / window if window > 0 else 0.0
    frac = max(0.0, min(1.0, frac))
    return plot_top + (1.0 - frac) * plot_h


def _x_for_min(minute: float, plot_left: float, plot_w: float, span_min: float) -> float:
    """Map a session minute to a group-local x coordinate.

    Linear: ``min=0`` → ``plot_left``; ``min=span_min`` → ``plot_left + plot_w``.
    Clamped to the plot so a malformed minute past ``span_min`` still lands on the
    right edge rather than overshooting (the span is sized to cover every event,
    so a real reset never clamps).
    """
    frac = minute / span_min if span_min > 0 else 0.0
    frac = max(0.0, min(1.0, frac))
    return plot_left + frac * plot_w


# --------------------------------------------------------------------------- #
# Occupancy modelling                                                         #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _Segment:
    """One inter-reset segment of the modelled curve (in data space).

    ``start_min`` / ``end_min`` bound the segment; ``start_occ`` is the post-reset
    occupancy it rises from; ``peak_occ`` is the occupancy it reaches at
    ``end_min`` (just before the next reset, or the session end). ``has_drop`` is
    True when a reset fires at ``end_min`` (the curve jumps down to the next
    segment's ``start_occ``)."""

    start_min: float
    end_min: float
    start_occ: float
    peak_occ: float
    has_drop: bool


def _build_segments(
    events: list[ResetEvent],
    window: float,
    peak_ctx: float,
    span_min: float,
) -> list[_Segment]:
    """Partition the session into rising segments separated by reset drops.

    Walks the sorted events: each segment runs from the previous reset minute
    (occupancy = previous ``to``, or 0 at session start) to the next reset minute,
    rising to a per-segment peak. The segment whose span contains the global peak
    minute reaches exactly ``peak_ctx``; the rest rise to a proportional fraction
    of the window scaled by their share of the run-up, so the curve reads as a
    plausible burn even though only the resets are recorded.

    With **no events** this returns a single segment rising from 0 to
    ``peak_ctx`` over the whole span — the smooth-curve extreme.
    """
    sorted_events = sorted(events, key=lambda e: float(e["min"]))
    # Boundaries: session start (0) → each reset minute → session end.
    boundaries = [0.0, *[float(e["min"]) for e in sorted_events], span_min]
    # Post-reset occupancy entering each segment: 0 at start, then each ``to``.
    seg_starts = [0.0, *[float(e["to"]) for e in sorted_events]]

    # Which segment owns the global peak? The longest run-up that ends in the
    # tallest pre-reset rise. We approximate: the peak lands in the segment with
    # the largest (duration * headroom) product, biased to reach peak_ctx there.
    n_segments = len(boundaries) - 1
    spans = [(boundaries[i + 1] - boundaries[i], window - seg_starts[i]) for i in range(n_segments)]
    # Score each segment by run-up "energy" (time available * headroom to ceiling).
    scores = [max(dur, 0.0) * max(head, 0.0) for dur, head in spans]
    peak_seg = scores.index(max(scores)) if scores and max(scores) > 0 else n_segments - 1

    segments: list[_Segment] = []
    for i in range(n_segments):
        start_min = boundaries[i]
        end_min = boundaries[i + 1]
        start_occ = seg_starts[i]
        if i == peak_seg:
            peak_occ = peak_ctx
        else:
            # Rise to a fraction of the ceiling proportional to this segment's
            # energy relative to the peak segment — always above start_occ, never
            # above the window. Shorter / higher-floored segments rise less.
            ratio = scores[i] / scores[peak_seg] if scores[peak_seg] > 0 else 0.0
            target = start_occ + (peak_ctx - start_occ) * ratio
            peak_occ = max(start_occ, min(window, target))
        has_drop = i < len(sorted_events)  # a reset fires at this segment's end
        segments.append(
            _Segment(
                start_min=start_min,
                end_min=end_min,
                start_occ=start_occ,
                peak_occ=peak_occ,
                has_drop=has_drop,
            )
        )
    return segments


def _bezier_rise(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    n: int = 12,
) -> str:
    """Emit a smooth cubic-bezier rise from ``(x0,y0)`` to ``(x1,y1)``.

    The specimen draws each segment as a chain of short cubic beziers with a
    slight ease (control points pulled toward the midpoint), producing an organic
    rise rather than a straight ramp. We subdivide into ``n`` cubic spans and ease
    the y with a smoothstep so the curve flattens slightly as it approaches the
    pre-reset peak — visually identical to the hand-authored path.

    Returns the path body *excluding* the initial ``M`` (the caller has already
    positioned the cursor at ``(x0, y0)``).
    """

    def smooth(t: float) -> float:
        # Smoothstep ease — gentle acceleration then deceleration.
        return t * t * (3.0 - 2.0 * t)

    parts: list[str] = []
    prev_x, prev_y = x0, y0
    for k in range(1, n + 1):
        t = k / n
        tx = x0 + (x1 - x0) * t
        ty = y0 + (y1 - y0) * smooth(t)
        # Control points: a third of the way along each end, biased to ease.
        c1x = prev_x + (tx - prev_x) / 3.0
        c1y = prev_y + (ty - prev_y) / 3.0
        c2x = prev_x + 2.0 * (tx - prev_x) / 3.0
        c2y = prev_y + 2.0 * (ty - prev_y) / 3.0
        parts.append(f"C {c1x:.1f},{c1y:.1f} {c2x:.1f},{c2y:.1f} {tx:.1f},{ty:.1f}")
        prev_x, prev_y = tx, ty
    return " ".join(parts)


def _build_paths(
    segments: list[_Segment],
    *,
    plot_left: float,
    plot_w: float,
    plot_top: float,
    plot_h: float,
    window: float,
    span_min: float,
) -> tuple[str, str]:
    """Build the ``(area_path, line_path)`` ``d`` strings from the segments.

    The line path rises through each segment via :func:`_bezier_rise`, then drops
    vertically (``L``) at each reset to the next segment's start occupancy. The
    area path is the line path closed down to the baseline and back along it.
    """
    baseline_y = plot_top + plot_h

    def px(minute: float) -> float:
        return _x_for_min(minute, plot_left, plot_w, span_min)

    def py(occ: float) -> float:
        return _y_for_occ(occ, plot_top, plot_h, window)

    first = segments[0]
    start_x, start_y = px(first.start_min), py(first.start_occ)
    line_parts: list[str] = [f"M {start_x:.1f},{start_y:.1f}"]

    for seg in segments:
        x0, y0 = px(seg.start_min), py(seg.start_occ)
        x1, y1 = px(seg.end_min), py(seg.peak_occ)
        line_parts.append(_bezier_rise(x0, y0, x1, y1))
        if seg.has_drop:
            # Vertical drop to the next segment's start occupancy at the same x.
            # (The next segment's start_occ == this reset's ``to``.)
            drop_y = py(_next_start_occ(segments, seg))
            line_parts.append(f"L {x1:.1f},{drop_y:.1f}")

    line_path = " ".join(line_parts)

    # Area = line, then down to baseline at the right edge, across to the left
    # edge, and closed.
    right_x = px(segments[-1].end_min)
    left_x = px(segments[0].start_min)
    area_path = f"{line_path} L {right_x:.1f},{baseline_y:.1f} L {left_x:.1f},{baseline_y:.1f} Z"
    return area_path, line_path


def _next_start_occ(segments: list[_Segment], seg: _Segment) -> float:
    """Return the start occupancy of the segment following ``seg`` (the reset ``to``)."""
    idx = segments.index(seg)
    if idx + 1 < len(segments):
        return segments[idx + 1].start_occ
    return seg.peak_occ  # no following segment → no drop (defensive)


# --------------------------------------------------------------------------- #
# De-collision                                                                #
# --------------------------------------------------------------------------- #


def _decollide(xs: list[float], min_gap: float, lo: float, hi: float) -> tuple[list[float], int]:
    """Spread sorted x positions so neighbours are ≥ ``min_gap`` apart.

    Single left-to-right pass: each x is pushed to at least
    ``previous + min_gap``. Positions that would exceed ``hi`` after pushing are
    dropped (reported as the overflow count) rather than piling up on the edge.
    Inputs are assumed pre-sorted ascending.

    Returns ``(kept_positions, dropped_count)``.
    """
    kept: list[float] = []
    dropped = 0
    cursor = lo - min_gap  # so the first item isn't forced right of its position
    for x in xs:
        nx = max(x, cursor + min_gap)
        if nx > hi:
            dropped += 1
            continue
        kept.append(nx)
        cursor = nx
    return kept, dropped


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #


def layout_context_load(
    *,
    events: list[ResetEvent],
    window: float,
    peak_ctx: float,
    span_min: float,
    error_minutes: list[float],
    plot_box: tuple[float, float, float, float] = (34.0, 22.0, 718.0, 116.0),
) -> ContextLoadLayout:
    """Lay out the context-load burn-curve panel as pure geometry.

    Args:
        events: Reset events from the ``receipt/1`` payload's ``context.events``
            (``{min, cmd, to}`` each). May be empty (→ one smooth segment).
        window: Context-window size in absolute tokens (the y-axis ceiling).
        peak_ctx: Peak occupancy reached during the session (absolute tokens).
        span_min: Elapsed wall-clock span in minutes (the x-axis extent) — the
            session timeline reset events are placed on. Distinct from the
            active-work sum; a session resumed across days has a large span but
            few active minutes.
        error_minutes: Real minutes (from session start) of each main-thread
            error, plotted as time-axis ticks (not occupancy-baseline dots).
        plot_box: ``(x, y, w, h)`` of the panel rectangle, group-local. The inner
            plot area insets by :data:`PLOT_TOP_INSET` / :data:`PLOT_BOTTOM_INSET`.

    Returns:
        A :class:`ContextLoadLayout` with the area/line paths, axis lines, ticks,
        typed reset markers, de-collided error ticks (+ a
        ``dropped_errors`` disclosure), the legend, and header text — all
        group-local, colour-free.
    """
    box_x, box_y, box_w, box_h = plot_box
    plot_left = box_x
    plot_w = box_w
    plot_right = box_x + box_w
    plot_top = box_y + PLOT_TOP_INSET
    plot_bottom = box_y + box_h - PLOT_BOTTOM_INSET
    plot_h = plot_bottom - plot_top
    baseline_y = plot_bottom

    window = max(window, 1.0)
    span_min = max(span_min, 1.0)
    peak_ctx = max(0.0, min(peak_ctx, window))

    # ---- occupancy curve -------------------------------------------------- #
    segments = _build_segments(events, window, peak_ctx, span_min)
    area_path, line_path = _build_paths(
        segments,
        plot_left=plot_left,
        plot_w=plot_w,
        plot_top=plot_top,
        plot_h=plot_h,
        window=window,
        span_min=span_min,
    )

    # ---- y-axis lines (ceiling, mid gridline, baseline) ------------------- #
    ceiling_line = AxisLine(
        y=plot_top,
        x1=plot_left,
        x2=plot_right,
        label=_format_k(window),
        label_x=AXIS_LABEL_X,
        label_y=plot_top + 2.7,
        dashed=True,
        emphatic=True,
    )
    baseline = AxisLine(
        y=baseline_y,
        x1=plot_left,
        x2=plot_right,
        label="0",
        label_x=AXIS_LABEL_X,
        label_y=baseline_y + 2.7,
        dashed=False,
        emphatic=False,
    )
    gridlines = _build_gridlines(window, plot_left, plot_right, plot_top, plot_h)

    # ---- time ticks ------------------------------------------------------- #
    time_ticks = _build_time_ticks(
        span_min,
        plot_left=plot_left,
        plot_w=plot_w,
        plot_top=plot_top,
        baseline_y=baseline_y,
    )

    # ---- reset markers (typed, de-collided in draw_x) --------------------- #
    reset_markers = _build_reset_markers(
        events,
        segments,
        plot_left=plot_left,
        plot_w=plot_w,
        plot_top=plot_top,
        plot_h=plot_h,
        plot_right=plot_right,
        window=window,
        span_min=span_min,
    )

    # ---- error ticks (real times, de-collided, capped with disclosure) ----- #
    error_ticks, dropped_errors = _build_error_ticks(
        error_minutes,
        span_min=span_min,
        plot_left=plot_left,
        plot_w=plot_w,
        plot_right=plot_right,
        baseline_y=baseline_y,
    )

    # ---- legend ----------------------------------------------------------- #
    legend = _build_legend()
    legend_y = box_y + box_h + 23.4  # panel bottom 138 → legend baseline 161.4

    # ---- header ----------------------------------------------------------- #
    header = _build_header(
        window=window,
        peak_ctx=peak_ctx,
        span_min=span_min,
        reset_count=len(events),
        plot_right=plot_right,
    )

    return ContextLoadLayout(
        area_path=area_path,
        line_path=line_path,
        ceiling_line=ceiling_line,
        gridlines=gridlines,
        baseline=baseline,
        time_ticks=time_ticks,
        reset_markers=reset_markers,
        error_ticks=error_ticks,
        dropped_errors=dropped_errors,
        legend=legend,
        legend_y=legend_y,
        header=header,
        plot_left=plot_left,
        plot_right=plot_right,
        plot_top=plot_top,
        plot_bottom=plot_bottom,
    )


# --------------------------------------------------------------------------- #
# Section builders                                                            #
# --------------------------------------------------------------------------- #


def _build_gridlines(
    window: float,
    plot_left: float,
    plot_right: float,
    plot_top: float,
    plot_h: float,
) -> list[AxisLine]:
    """Interior horizontal gridlines at clean round-number occupancies.

    Picks a single mid gridline at the round value nearest ``window/2`` (so a
    200K window draws 100K, a 1M window draws 500K), matching the specimen's one
    interior line. Skips the line if it would land on the ceiling or baseline.
    """
    mid = _round_nice(window / 2.0)
    if mid <= 0 or mid >= window:
        return []
    y = _y_for_occ(mid, plot_top, plot_h, window)
    return [
        AxisLine(
            y=y,
            x1=plot_left,
            x2=plot_right,
            label=_format_k(mid),
            label_x=AXIS_LABEL_X,
            label_y=y + 2.7,
            dashed=True,
            emphatic=False,
        )
    ]


def _round_nice(value: float) -> float:
    """Round to a clean 1/2/5 x 10^k value for gridline labels."""
    if value <= 0:
        return 0.0
    exp = math.floor(math.log10(value))
    base = 10.0**exp
    frac = value / base
    if frac < 1.5:
        nice = 1.0
    elif frac < 3.5:
        nice = 2.0
    elif frac < 7.5:
        nice = 5.0
    else:
        nice = 10.0
    return nice * base


def _select_tick_interval(span_min: float, plot_w: float) -> float:
    """Pick a clean tick interval (minutes) scaled to ``span_min``.

    Snaps the ideal step ``span_min / TICK_TARGET_COUNT`` up to the nearest
    :data:`TICK_NICE_STEPS_MIN` candidate, so a 130m session steps by 30m and a
    3334m session steps by ~720m (12h) rather than cramming the old fixed
    0/30/60/90/120 candidates into the left edge. Also enforces the pixel-gap
    floor: if a candidate's on-screen spacing would fall below
    :data:`MIN_TICK_GAP_PX`, the next larger candidate is taken. Falls back to
    the largest candidate for absurd spans so the loop always terminates.
    """
    if span_min <= 0:
        return TICK_NICE_STEPS_MIN[0]
    ideal = span_min / TICK_TARGET_COUNT
    for step in TICK_NICE_STEPS_MIN:
        if step < ideal:
            continue
        px_gap = plot_w * step / span_min
        if px_gap >= MIN_TICK_GAP_PX:
            return step
    return TICK_NICE_STEPS_MIN[-1]


def _build_time_ticks(
    span_min: float,
    *,
    plot_left: float,
    plot_w: float,
    plot_top: float,
    baseline_y: float,
) -> list[TimeTick]:
    """Bottom-axis time ticks at an adaptive 'nice' interval scaled to span_min.

    The interval comes from :func:`_select_tick_interval` so the labels stay
    evenly spaced and readable for ``span_min`` from 1 minute to several days
    (the old fixed 0/30/60/90/120 candidates collapsed into the left edge for the
    thousand-minute codex sessions). Ticks emit at ``0, interval, 2·interval, …``
    up to ``span_min``, plus the terminal ``span_min`` tick (always present,
    end-anchored). A regular tick within :data:`MIN_TICK_GAP_PX` of the terminal
    is dropped so labels never collide. Labels read as h/d via
    :func:`format_duration`. Interior ticks carry a faint full-height gridline.
    """
    mark_y1 = baseline_y
    mark_y2 = baseline_y + TICK_MARK_LEN
    label_y = baseline_y + TICK_LABEL_Y_GAP

    def x_of(m: float) -> float:
        return _x_for_min(m, plot_left, plot_w, span_min)

    interval = _select_tick_interval(span_min, plot_w)
    terminal_x = x_of(span_min)
    ticks: list[TimeTick] = []

    # Regular ticks at 0, interval, 2*interval, … strictly below span_min.
    m = 0.0
    while m < span_min:
        x = x_of(m)
        # Drop a regular tick that sits too close to the terminal label (the 0m
        # origin always stays — it anchors the left edge).
        if m != 0.0 and abs(terminal_x - x) < MIN_TICK_GAP_PX:
            m += interval
            continue
        anchor: Literal["start", "middle", "end"] = "start" if m == 0.0 else "middle"
        ticks.append(
            TimeTick(
                x=x,
                mark_y1=mark_y1,
                mark_y2=mark_y2,
                label=format_duration(m),
                label_y=label_y,
                label_anchor=anchor,
                gridline=0.0 < m < span_min,
                gridline_y1=plot_top,
                gridline_y2=baseline_y,
            )
        )
        m += interval

    # Terminal span_min tick (always present, end-anchored) unless a regular
    # tick already landed exactly on it.
    if not any(abs(t.x - terminal_x) < 0.5 for t in ticks):
        ticks.append(
            TimeTick(
                x=terminal_x,
                mark_y1=mark_y1,
                mark_y2=mark_y2,
                label=format_duration(span_min),
                label_y=label_y,
                label_anchor="end",
                gridline=False,
                gridline_y1=plot_top,
                gridline_y2=baseline_y,
            )
        )
    ticks.sort(key=lambda t: t.x)
    return ticks


def _build_reset_markers(
    events: list[ResetEvent],
    segments: list[_Segment],
    *,
    plot_left: float,
    plot_w: float,
    plot_top: float,
    plot_h: float,
    plot_right: float,
    window: float,
    span_min: float,
) -> list[ResetMarker]:
    """Place typed reset glyphs at each event's curve drop, de-colliding draw_x.

    Each glyph's ``x`` is the true event x (the curve's vertical drop); its ``y``
    is the curve y at the *pre-reset peak* (the top of the segment ending at that
    event). ``draw_x`` is de-collided so crowded events don't overlap — only the
    glyph moves, the path drop stays put.
    """
    sorted_events = sorted(events, key=lambda e: float(e["min"]))
    raw_xs = [_x_for_min(float(e["min"]), plot_left, plot_w, span_min) for e in sorted_events]
    draw_xs, _dropped = _decollide(raw_xs, MIN_GLYPH_GAP_PX, plot_left, plot_right)
    # _decollide may drop trailing crowded glyphs; pad with clamped positions so
    # every event still gets a (possibly edge-pinned) glyph — resets are
    # load-bearing semantics, never silently omitted.
    while len(draw_xs) < len(sorted_events):
        draw_xs.append(plot_right)

    markers: list[ResetMarker] = []
    for i, (event, raw_x, draw_x) in enumerate(zip(sorted_events, raw_xs, draw_xs, strict=True)):
        # The segment ending at this event is segment i (peak before the drop).
        peak_occ = segments[i].peak_occ if i < len(segments) else peak_ctx_fallback(segments)
        y = _y_for_occ(peak_occ, plot_top, plot_h, window)
        kind = _CMD_TO_KIND.get(str(event["cmd"]).lower(), "compact")
        markers.append(
            ResetMarker(
                x=raw_x,
                draw_x=draw_x,
                y=y,
                kind=kind,
                minute=float(event["min"]),
                to_value=float(event["to"]),
            )
        )
    return markers


def peak_ctx_fallback(segments: list[_Segment]) -> float:
    """Return the tallest segment peak — defensive fallback for marker y."""
    return max((s.peak_occ for s in segments), default=0.0)


def _build_error_ticks(
    error_minutes: list[float],
    *,
    span_min: float,
    plot_left: float,
    plot_w: float,
    plot_right: float,
    baseline_y: float,
) -> tuple[list[ErrorTick], int]:
    """Place error ticks at their REAL minutes in the axis margin, de-collided.

    Each main-thread error's wall-clock minute maps to an x via the same time
    map the reset glyphs use, so the ticks read as "errors happened at these
    times" — anchored to WHEN, not to an occupancy value, and living BELOW the
    baseline so they never collide with the (low-at-start) curve. Ticks are
    de-collided to :data:`MIN_ERROR_GAP_PX`; overflow that can't fit the plot
    width is returned as ``dropped`` so the caller can disclose 'N errors (+M)'
    rather than silently clipping.
    """
    if not error_minutes:
        return [], 0
    raw_xs = sorted(_x_for_min(m, plot_left, plot_w, span_min) for m in error_minutes)
    kept, dropped = _decollide(raw_xs, MIN_ERROR_GAP_PX, plot_left, plot_right)
    y1 = baseline_y
    y2 = baseline_y + ERROR_TICK_LEN
    return [ErrorTick(x=x, y1=y1, y2=y2) for x in kept], dropped


def _build_legend() -> list[LegendItem]:
    """Lay out the legend row with measured label widths so items never overlap.

    Walks left-to-right from x=0: each item places its swatch, measures its label
    width via :func:`measure_text`, and advances the cursor past
    label-end + :data:`LEGEND_ITEM_GAP`. The legend keys only the marks that
    aren't self-evident — the context curve, the three reset glyphs, and the
    error tick. The window-ceiling line is NOT keyed: its '1.0M' label and top
    position already read as the window limit, so a key would only crowd the row."""
    specs: list[tuple[LegendKind, str, float]] = [
        ("line", "context", LEGEND_LINE_SWATCH_W),
        ("compact", "compact", 2 * GLYPH_CHEVRON_W),
        ("clear", "clear", 2 * GLYPH_CIRCLE_R),
        ("auto", "auto-compact", 2 * GLYPH_DIAMOND_R),
        ("error", "error", ERROR_TICK_WIDTH + 1.0),
    ]
    items: list[LegendItem] = []
    cursor = 0.0
    for kind, label, swatch_w in specs:
        swatch_x = cursor
        label_x = cursor + swatch_w + LEGEND_LABEL_GAP
        label_w = measure_text(label, font_family=LEGEND_FONT, font_size=LEGEND_FONT_SIZE, font_weight=400)
        items.append(LegendItem(kind=kind, swatch_x=swatch_x, label=label, label_x=label_x))
        cursor = label_x + label_w + LEGEND_ITEM_GAP
    return items


def _build_header(
    *,
    window: float,
    peak_ctx: float,
    span_min: float,
    reset_count: int,
    plot_right: float,
) -> HeaderText:
    """Build the header row: left eyebrow + detail, right peak + reset clause.

    The right block lays out right-to-left from ``plot_right`` via measurement:
    '{peak}K PEAK' is end-anchored at the right edge; when ``reset_count > 0`` a
    dim '·' separator and '{N} RESETS' are placed to its left, each end-anchored
    at a measured x so the three runs don't overlap. ``reset_count == 0``
    suppresses the reset clause entirely (empty ``resets_label``).
    """
    eyebrow = "CONTEXT LOAD"
    eyebrow_w = measure_text(
        eyebrow, font_family=AXIS_LABEL_FONT, font_size=7.0, font_weight=700, letter_spacing_em=0.22
    )
    detail = f"· {_format_k(window)} WINDOW · {format_duration(span_min)}"
    detail_x = eyebrow_w + 1.0

    peak_label = f"{_format_k(peak_ctx)} PEAK"
    peak_label_x = plot_right

    if reset_count > 0:
        peak_w = measure_text(
            peak_label,
            font_family=AXIS_LABEL_FONT,
            font_size=AXIS_LABEL_SIZE,
            font_weight=700,
            letter_spacing_em=0.06,
        )
        sep_x = plot_right - peak_w - 6.0
        resets_label = f"{reset_count} RESET{'S' if reset_count != 1 else ''}"
        sep_w = measure_text("·", font_family=AXIS_LABEL_FONT, font_size=AXIS_LABEL_SIZE)
        resets_label_x = sep_x - sep_w - 3.0
    else:
        sep_x = plot_right
        resets_label = ""
        resets_label_x = plot_right

    return HeaderText(
        eyebrow=eyebrow,
        eyebrow_x=0.0,
        detail=detail,
        detail_x=detail_x,
        peak_label=peak_label,
        peak_label_x=peak_label_x,
        sep_x=sep_x,
        resets_label=resets_label,
        resets_label_x=resets_label_x,
        y=HEADER_Y,
    )
