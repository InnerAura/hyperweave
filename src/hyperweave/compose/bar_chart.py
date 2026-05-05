"""Variable-height bar-chart layout for the receipt's rhythm panel.

Sibling to :mod:`hyperweave.compose.rhythm`, NOT a replacement. The
``layout_rhythm_bars`` helper still produces uniform-height bars for any
caller that wants the older treatment; this module produces variable
heights — bar height encodes per-stage token density — for the receipt's
rhythm panel and (via reuse) for the rhythm-strip v2 artifact.

Risograph-canonical structure (matches
``tier2/telemetry/telemetry-redesign/receipt-genome-risograph.svg``):

* Bars are baseline-aligned, growing upward from ``BASELINE_Y``.
* Each bar carries an ``opacity`` (0.78 regular / 0.85 peak) and an
  ``is_peak`` flag identifying the max-tokens stage.
* The peak bar gets a 1.5px signal-color tick at its top — emitted
  separately as a :class:`PeakMarker` so the template doesn't branch.
* Error ticks live in a **dedicated band** at ``ERROR_BAND_Y`` (above the
  bars), not inline above each bar. One :class:`ErrorTick` per stage
  with ``errors > 0``.
* Time axis: labels render ABOVE the bars at major intervals (5m for
  short sessions, 30m otherwise). Grid lines run vertically across the
  bar track at the same major positions.

Single source of truth — derive everything from ``panel_h``
=========================================================

Independently-hardcoded geometry constants are a bug pattern (the
v0.2.21 Phase D y=-1 overflow came from ``BAR_MAX_H=60`` exceeding the
panel's effective track). Here every position is derived from the
``panel_h`` parameter passed to :func:`layout_bar_chart`::

    HEADER_H        = 12     (header text band, module constant)
    TIME_AXIS_H     = 18     (time labels at y=20 within band, module constant)
    ERROR_BAND_H    = 5      (red ticks 1.2x5px, module constant)
    LEGEND_H        = 22     (legend at panel bottom, module constant)
    BAR_TOP_Y       = HEADER_H + TIME_AXIS_H        = 30
    ERROR_BAND_Y    = HEADER_H + 14                 = 26   (between header and bars)
    BASELINE_Y      = panel_h - LEGEND_H            (parametric)
    BAR_TRACK_H     = BASELINE_Y - BAR_TOP_Y        (parametric)
    BAR_MAX_H       = int(BAR_TRACK_H * 0.46)       (parametric, ~36 for panel_h=130)
    LEGEND_Y        = BASELINE_Y + 16               (parametric)

Change ``panel_h`` and every position adjusts coherently. The constraint
``BAR_MAX_H + ERROR_BAND_Y < BASELINE_Y`` is true by construction, so the
old overflow bug can't recur.

Sessions with more than ``max_bars`` stages collapse via
:func:`merge_consecutive_same_class`, which coalesces adjacent stages of
the same dominant class. The :class:`BarChartLayout` header label encodes
the original-vs-shown count so the merge is visible to the reader.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

# --------------------------------------------------------------------------- #
# Module constants — the parts of the panel geometry that don't depend on    #
# panel_h. Position values for the header/time-axis/error-band sit ABOVE the  #
# bar track regardless of panel size; only baseline + bar height scale.       #
# --------------------------------------------------------------------------- #

HEADER_H = 12
"""Vertical band reserved for the rhythm header line ('SESSION RHYTHM ...')."""

TIME_AXIS_H = 18
"""Vertical band for time-axis labels (rendered at y=20 within this band)."""

ERROR_BAND_H = 5
"""Height of the error-tick row (between header and bars). Ticks are 1.2x5px."""

LEGEND_H = 22
"""Vertical band reserved for the legend at panel bottom."""

BAR_TOP_Y = HEADER_H + TIME_AXIS_H
"""Y-coordinate where the bar track starts (panel-relative)."""

ERROR_BAND_Y = HEADER_H + 14
"""Y-coordinate of the error-tick row. Sits between header (12) and bars (30)."""

BAR_MIN_H = 5
"""Minimum bar height — keeps zero-token stages visible regardless of panel_h."""

BAR_MIN_W = 6
"""Minimum bar width — short stages (<1% of session) still render at this floor
so they're perceptible against a dominant peak. Was 2px previously, but a 3px
bar against a 746px peak at 0.78 opacity is essentially invisible. 6px reads
as a clear "boundary mark" without distorting proportions for normal-mix sessions."""

ERROR_TICK_W = 1.2
"""Error-tick horizontal extent (px)."""

ERROR_TICK_H = ERROR_BAND_H
"""Error-tick vertical extent — equals the band height."""

PEAK_MARKER_H = 1.5
"""Peak-marker tick height (signal-color rect at top of max-tokens bar)."""

BAR_OPACITY = 0.78
"""Fill-opacity for regular bars (matches risograph specimen)."""

PEAK_OPACITY = 0.85
"""Fill-opacity for the peak bar (slightly stronger than regular)."""

DEFAULT_PANEL_H = 130
"""Default panel height. The receipt's rhythm zone allocates 130px vertically."""

# Backwards-compat constants kept so existing imports don't break. Tests +
# rhythm-strip use these. ``BAR_MAX_H`` resolves to the value derived from
# ``DEFAULT_PANEL_H`` so callers that read it directly still get a sensible
# number — but ``layout_bar_chart`` recomputes per-call from its area_h arg.
ERROR_TICK_GAP = 3
"""Legacy: vertical gap between bar top and error-tick. Unused under v0.2.21
band-based error tick model — kept exported so test_compose_bar_chart's
backwards-compat imports don't break. The new layout puts ticks in a fixed
band at ``ERROR_BAND_Y`` regardless of bar height."""


def _derive_panel_geometry(panel_h: int) -> tuple[int, int, int]:
    """Return ``(baseline_y, bar_track_h, bar_max_h)`` from ``panel_h``.

    Every other position constant is independent of ``panel_h``. This helper
    centralizes the parametric derivation so :func:`layout_bar_chart` and
    the (future) rhythm-strip layout can share the same math.
    """
    baseline_y = panel_h - LEGEND_H
    bar_track_h = baseline_y - BAR_TOP_Y
    bar_max_h = int(bar_track_h * 0.46)
    return baseline_y, bar_track_h, bar_max_h


# Default values exposed for callers that want to inspect or override.
_DEFAULT_BASELINE_Y, _DEFAULT_BAR_TRACK_H, _DEFAULT_BAR_MAX_H = _derive_panel_geometry(DEFAULT_PANEL_H)
BASELINE_Y = _DEFAULT_BASELINE_Y
"""Default baseline y-coordinate (= 108 for the canonical 130px panel)."""

BAR_TRACK_H = _DEFAULT_BAR_TRACK_H
"""Default bar track height (= 78 for the canonical 130px panel)."""

BAR_MAX_H = _DEFAULT_BAR_MAX_H
"""Default tallest bar height (= 35 for the canonical 130px panel).

Caveat: under the new derivation, callers passing a non-default ``area_h``
get a different per-call value computed inside :func:`layout_bar_chart`.
This module-level constant exists for the canonical 130px receipt panel
and for convenience in tests."""

LEGEND_Y = BASELINE_Y + 16
"""Default y-coordinate where the legend renders (= 124 for the canonical panel)."""


# --------------------------------------------------------------------------- #
# Dataclasses                                                                 #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BarChartCell:
    """One bar in the receipt's rhythm panel.

    Geometry is panel-relative — the receipt template translates the rhythm
    zone before consuming this. ``opacity`` and ``is_peak`` drive the
    risograph-canonical visual treatment (regular bars at 0.78, peak at 0.85
    with a signal-color tick on top).
    """

    x: int
    y: int
    w: int
    h: int
    tool_class: str
    tokens: int
    errors: int
    is_peak: bool
    opacity: float
    error_tick_y: int
    """Legacy: y-coord above this bar where the old per-bar error tick rendered.

    The v0.2.21 layout emits :class:`ErrorTick` records in a separate dedicated
    band (``ERROR_BAND_Y``) rather than per-bar. This field is preserved for
    backwards compatibility and is computed as ``y - ERROR_TICK_GAP - ERROR_TICK_H``
    so existing template snippets that consume it still render correctly."""


@dataclass(frozen=True)
class TimeAxisTick:
    """One tick on the rhythm panel's time axis (label band above the bars)."""

    x: int
    label: str
    """Text label for major ticks; empty for minor ticks."""
    is_major: bool


@dataclass(frozen=True)
class ErrorTick:
    """One error-tick mark in the dedicated band above the bars.

    Risograph specimen treatment: red 1.2x5px rect at ``y=ERROR_BAND_Y``,
    horizontally aligned to the center of the corresponding bar. Stages with
    ``errors == 0`` produce no :class:`ErrorTick`.
    """

    x: int
    y: int
    w: float
    h: int
    count: int
    """Number of errors in the corresponding stage (currently only used for
    accessibility / data-hw-* attributes; the visual is a single tick)."""


@dataclass(frozen=True)
class PeakMarker:
    """Signal-color tick at the top of the max-tokens bar.

    Spans the peak bar's full width at 1.5px height. The risograph specimen
    uses ``var(--signal)`` for the fill; the receipt template emits a single
    rect from this dataclass.
    """

    x: int
    y: int
    w: int
    h: float


@dataclass(frozen=True)
class GridLine:
    """One vertical grid line in the bar track at a major time interval."""

    x: int


@dataclass(frozen=True)
class BarChartLayout:
    """Complete layout output from :func:`layout_bar_chart`.

    Bundles every geometry list the template needs to render the rhythm
    panel — bars, error band, peak marker, grid, header labels, and the
    original-vs-shown stage counts.
    """

    bars: list[BarChartCell]
    error_ticks: list[ErrorTick]
    peak_marker: PeakMarker | None
    grid_lines: list[GridLine]
    total_tokens_label: str
    """Formatted total-token count for the header right-side label, e.g. ``"209M"``."""
    peak_tokens_label: str
    """Formatted peak-tokens label, e.g. ``"PEAK 38M"``."""
    original_count: int
    shown_count: int
    baseline_y: int
    """Computed baseline y-coordinate for this panel — exposed so the template
    can render the baseline rule without re-deriving."""
    bar_max_h: int
    """Computed max bar height for this panel."""


# --------------------------------------------------------------------------- #
# Layout helpers                                                              #
# --------------------------------------------------------------------------- #


def _stage_class(s: dict[str, Any]) -> str:
    """Extract the dominant class from a stage dict."""
    return str(s.get("dominant_class") or s.get("tool_class") or "explore")


def _stage_tokens(s: dict[str, Any]) -> int:
    """Tokens for a stage, with fallback chain.

    Distinguishes "field absent" (pre-v0.2.21 transcript) from "field
    present but zero" (post-patch transcript with a stage that genuinely
    burned no billable tokens — e.g. a pure user-event boundary stage).

    * Pre-patch (no ``tokens`` key) → fall back to ``tools`` (call count)
      so the bars still size proportionally to call volume.
    * Post-patch (``tokens`` key present, value ``0``) → return ``0``,
      which produces a ``BAR_MIN_H`` bar via the height-normalization fallback.
    """
    if "tokens" in s:
        return int(s["tokens"])
    return int(s.get("tools", 0))


def _format_tokens_short(n: int) -> str:
    """Format token count for the rhythm header, e.g. ``209M``, ``42M``, ``815K``."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f}M" if n >= 10_000_000 else f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K" if n >= 10_000 else f"{n / 1_000:.1f}K"
    return str(n)


def merge_consecutive_same_class(
    stages: list[dict[str, Any]],
    max_bars: int = 60,
) -> list[dict[str, Any]]:
    """Coalesce adjacent stages sharing dominant class until ``len <= max_bars``.

    For pathologically long sessions (12-hour runs, 200+ stages),
    rendering one bar per stage produces inter-bar gaps that collapse
    to sub-pixel widths and make the panel unreadable. Merging
    same-class neighbours preserves visual structure: color sequencing
    and time proportions are unchanged, the bars are just thicker.

    Args:
        stages: Normalized stage dicts (the contract's ``stages`` list).
            Each MUST carry ``dominant_class`` (or ``tool_class``).
            Optional: ``start``/``end`` ISO strings, ``tokens``, ``errors``,
            ``tools`` (call count).
        max_bars: Target maximum bar count after merging.

    Returns:
        New list with adjacent same-class stages coalesced. Sums tokens,
        errors, and tools across runs; preserves the start of the first
        run member and the end of the last. When already at or below
        ``max_bars``, returns the input unchanged (greedy: only merges
        until the budget is met).
    """
    if not stages or len(stages) <= max_bars:
        return list(stages)

    merged: list[dict[str, Any]] = []
    for s in stages:
        cls = _stage_class(s)
        if merged and _stage_class(merged[-1]) == cls:
            prev = merged[-1]
            merged[-1] = {
                **prev,
                "end": s.get("end", prev.get("end", "")),
                "tokens": int(prev.get("tokens", 0)) + int(s.get("tokens", 0)),
                "errors": int(prev.get("errors", 0)) + int(s.get("errors", 0)),
                "tools": int(prev.get("tools", 0)) + int(s.get("tools", 0)),
            }
        else:
            merged.append(dict(s))

    # Decimation fallback for inputs where every stage has a different class
    # and a single greedy pass can't get under max_bars.
    if len(merged) > max_bars:
        k = (len(merged) + max_bars - 1) // max_bars
        merged = [merged[i] for i in range(0, len(merged), k)]

    return merged


def layout_bar_chart(
    stages: list[dict[str, Any]],
    area_w: int,
    area_h: int = DEFAULT_PANEL_H,
    *,
    bar_min_h: int = BAR_MIN_H,
    gap_px: int = 2,
    max_bars: int = 60,
    duration_m: float | None = None,
    baseline_y_override: int | None = None,
    bar_max_h_override: int | None = None,
    emit_error_ticks: bool = True,
) -> BarChartLayout:
    """Lay out variable-height rhythm bars + error band + peak marker + grid.

    Width is time-proportional when every stage carries ISO timestamps,
    otherwise falls back to ``tokens`` (preferred) or ``tools`` count.
    Height is normalized to the per-call ``bar_max_h`` derived from
    ``area_h`` so the tallest stage fills the track and shorter ones taper
    toward ``bar_min_h``.

    Args:
        stages: Normalized stage dicts (the contract's ``stages`` list).
        area_w: Track width in pixels.
        area_h: Panel height in pixels (the full rhythm zone, not just the
            bar track). All position constants derive from this — unless
            explicit overrides are passed.
        bar_min_h: Minimum bar height (zero-token stages still visible).
        gap_px: Inter-bar gap. Reserved upfront in the width budget.
        max_bars: Trigger ``merge_consecutive_same_class`` when input
            exceeds this count.
        duration_m: Total session duration in minutes. When provided,
            drives grid-line and time-axis tick computation (5m majors
            for short sessions, 30m otherwise). Without it, no grid
            lines are emitted (caller can compute axis ticks separately
            via :func:`compute_time_axis_ticks`).
        baseline_y_override: Optional explicit baseline y-coordinate.
            Used by the rhythm-strip-v2 layout (small ~28px bar track)
            to bypass the receipt's panel derivation. When provided,
            ``area_h`` is ignored for geometry — only width math uses it.
        bar_max_h_override: Optional explicit max bar height. Required
            when ``baseline_y_override`` is supplied so the caller can
            choose the bar height proportional to its own panel.
        emit_error_ticks: When False, no :class:`ErrorTick` records are
            emitted (the rhythm-strip-v2 doesn't render an error band —
            errors surface via the status zone instead).

    Returns:
        :class:`BarChartLayout` with bars + error_ticks + peak_marker +
        grid_lines + header labels + counts. ``original_count`` is
        ``len(stages)`` before any merge; ``shown_count`` is the visible
        bar count after merging.
    """
    if baseline_y_override is not None and bar_max_h_override is not None:
        baseline_y = baseline_y_override
        bar_max_h = bar_max_h_override
    else:
        baseline_y, _bar_track_h, bar_max_h = _derive_panel_geometry(area_h)

    if not stages:
        return BarChartLayout(
            bars=[],
            error_ticks=[],
            peak_marker=None,
            grid_lines=[],
            total_tokens_label="0",
            peak_tokens_label="PEAK 0",
            original_count=0,
            shown_count=0,
            baseline_y=baseline_y,
            bar_max_h=bar_max_h,
        )

    original_count = len(stages)

    # Stage 1: collapse extreme stage counts into a tractable bar count.
    working = merge_consecutive_same_class(stages, max_bars=max_bars)
    shown_count = len(working)

    # Stage 2: width allocation (time-proportional or token/call fallback).
    n = shown_count
    gap_budget = gap_px * max(n - 1, 0)
    available_w = max(area_w - gap_budget, area_w // 2)

    has_timestamps = all(s.get("start") and s.get("end") for s in working)
    if has_timestamps:
        # Width per bar is stage_duration / sum_of_stage_durations. The sum
        # (rather than wall-clock first→last) collapses inter-stage idle gaps
        # to zero, so a session left open across multiple bursts over days
        # renders bars proportional to actual work time, not dead-air. For
        # contiguous-stage sessions (the common case) this equals wall-clock
        # span exactly, so the result is identical.
        durations_s = [
            max(
                (datetime.fromisoformat(s["end"]) - datetime.fromisoformat(s["start"])).total_seconds(),
                0.0,
            )
            for s in working
        ]
        total_s = max(sum(durations_s), 1.0)
        raw_w = [max(int(available_w * d / total_s), BAR_MIN_W) for d in durations_s]
    else:
        weights = [_stage_tokens(s) for s in working]
        total = sum(weights) or 1
        min_bar_w = max(BAR_MIN_W, available_w // max(n, 1) // 3)
        raw_w = [max(int(available_w * w / total), min_bar_w) for w in weights]

    # Post-hoc rescale if the floor pressure pushed the sum over budget.
    raw_total = sum(raw_w)
    if raw_total > available_w and raw_total > 0:
        scale = available_w / raw_total
        raw_w = [max(int(w * scale), 2) for w in raw_w]

    # Stage 3: height allocation (token-density normalized).
    token_values = [_stage_tokens(s) for s in working]
    max_tokens = max(token_values) if token_values else 0
    max_tokens = max_tokens or 1  # divide-by-zero guard for all-zero sessions
    peak_index = token_values.index(max_tokens) if max_tokens > 1 else -1

    bars: list[BarChartCell] = []
    error_ticks: list[ErrorTick] = []
    rx = 0
    # Adjacent same-class bars share color; alternating opacity makes the
    # boundary visible. Without this, a single-dominant-class session (e.g.
    # 2 mutate stages) renders as one continuous rectangle.
    prev_class: str | None = None
    prev_opacity = BAR_OPACITY
    for i, (s, w, tok) in enumerate(zip(working, raw_w, token_values, strict=True)):
        h = max(int((tok / max_tokens) * bar_max_h), bar_min_h)
        y = baseline_y - h
        errors = int(s.get("errors", 0))
        is_peak = i == peak_index
        cls = _stage_class(s)

        if is_peak:
            opacity = PEAK_OPACITY
        elif prev_class == cls:
            opacity = PEAK_OPACITY if prev_opacity == BAR_OPACITY else BAR_OPACITY
        else:
            opacity = BAR_OPACITY

        bars.append(
            BarChartCell(
                x=rx,
                y=y,
                w=w,
                h=h,
                tool_class=cls,
                tokens=tok,
                errors=errors,
                is_peak=is_peak,
                opacity=opacity,
                error_tick_y=y - ERROR_TICK_GAP - ERROR_TICK_H,
            ),
        )
        if errors > 0 and emit_error_ticks:
            error_ticks.append(
                ErrorTick(
                    x=rx + w // 2,
                    y=ERROR_BAND_Y,
                    w=ERROR_TICK_W,
                    h=ERROR_TICK_H,
                    count=errors,
                ),
            )
        rx += w + gap_px
        prev_class = cls
        prev_opacity = opacity

    # Peak marker: 1.5px signal-color tick spanning the peak bar's width.
    peak_marker: PeakMarker | None = None
    if peak_index >= 0 and bars:
        peak_bar = bars[peak_index]
        peak_marker = PeakMarker(
            x=peak_bar.x,
            y=peak_bar.y - int(PEAK_MARKER_H),
            w=peak_bar.w,
            h=PEAK_MARKER_H,
        )

    # Header labels: total billed tokens + peak-stage tokens.
    total_billed = sum(token_values)
    total_tokens_label = _format_tokens_short(total_billed)
    peak_tokens_label = f"PEAK {_format_tokens_short(max_tokens if max_tokens > 1 else 0)}"

    # Grid lines: vertical strokes at major time intervals across the bar track.
    grid_lines: list[GridLine] = []
    if duration_m and duration_m > 0:
        major_interval = 5 if duration_m < 30 else 30
        t = float(major_interval)
        while t < duration_m:
            grid_lines.append(GridLine(x=int(area_w * t / duration_m)))
            t += major_interval

    return BarChartLayout(
        bars=bars,
        error_ticks=error_ticks,
        peak_marker=peak_marker,
        grid_lines=grid_lines,
        total_tokens_label=total_tokens_label,
        peak_tokens_label=peak_tokens_label,
        original_count=original_count,
        shown_count=shown_count,
        baseline_y=baseline_y,
        bar_max_h=bar_max_h,
    )


def compute_time_axis_ticks(
    duration_m: float,
    area_w: int,
    *,
    short_session_threshold_m: float = 30.0,
) -> list[TimeAxisTick]:
    """Generate major + minor ticks for the rhythm panel's time axis.

    Args:
        duration_m: Session duration in minutes.
        area_w: Track width in pixels (ticks span 0 → area_w).
        short_session_threshold_m: Below this duration, use 5-minute
            major intervals; otherwise 30-minute.

    Returns:
        List of :class:`TimeAxisTick`, ordered left-to-right, with major
        ticks labeled (``"0m"``, ``"30m"``, ..., ``"{duration}m"``) and
        minor ticks unlabeled. The terminal tick (rightmost) is always
        major and labeled with the actual session duration.
    """
    if duration_m <= 0 or area_w <= 0:
        return []

    major_interval = 5 if duration_m < short_session_threshold_m else 30
    minor_interval = major_interval // 3 if major_interval >= 3 else 1

    ticks: list[TimeAxisTick] = []

    # Major ticks at 0, interval, 2*interval, ..., up to duration_m.
    t = 0.0
    while t < duration_m:
        x = int(area_w * t / duration_m)
        ticks.append(TimeAxisTick(x=x, label=f"{int(t)}m", is_major=True))
        t += major_interval

    # Terminal tick at x=area_w with the actual duration label. If the last
    # major sits within MIN_LABEL_GAP_PX of the terminal, replace its
    # position+label with the terminal so we don't render "420m437m"
    # overlapping. Threshold sized for ~"999m" at font-size 8 plus margin.
    min_label_gap_px = 35
    terminal = TimeAxisTick(x=area_w, label=f"{round(duration_m)}m", is_major=True)
    if ticks and (area_w - ticks[-1].x) < min_label_gap_px:
        ticks[-1] = terminal
    else:
        ticks.append(terminal)

    # Minor ticks (unlabeled) between majors.
    minor_ticks: list[TimeAxisTick] = []
    t = float(minor_interval)
    while t < duration_m:
        if t % major_interval != 0:
            x = int(area_w * t / duration_m)
            minor_ticks.append(TimeAxisTick(x=x, label="", is_major=False))
        t += minor_interval

    ticks.extend(minor_ticks)
    ticks.sort(key=lambda tk: (tk.x, not tk.is_major))
    return ticks
