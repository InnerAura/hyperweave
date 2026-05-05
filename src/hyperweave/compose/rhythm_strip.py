"""Rhythm-strip v2 layout helpers.

Sibling to :mod:`hyperweave.compose.bar_chart`. The bar chart in the
rhythm zone of the v2 strip reuses :func:`bar_chart.layout_bar_chart`
verbatim — same algorithm, different panel dimensions. This module
adds the helpers that are unique to the strip:

* :func:`compute_session_velocity` — total tokens / minute summary.
* :func:`compute_velocity_sparkline` — 8-bucket token-rate timeline
  rendered as fill+stroke SVG paths for the velocity zone.
* :func:`compute_status_dot` — OK/WARN/ERR threshold mapping for the
  pulsing status indicator.
* :func:`compute_dominant_phase` — picks the dominant tool class and
  renders the percent-time label for the status zone.

The strip's specimen is at
``tier2/telemetry/receipt-types/receipts-pr-strips/rhythm-strip-v2.svg``
(600x92, 4 zones: identity / velocity / rhythm / status). The substrate
gradient and tool palette swap per skin via ``var(--dna-*)``; the
geometry is fixed across skins.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

# --------------------------------------------------------------------------- #
# Status thresholds                                                           #
# --------------------------------------------------------------------------- #

WARN_ERROR_RATE = 0.02
"""Above 2% error rate (errors / total_calls), strip status flips to WARN."""

ERR_ERROR_RATE = 0.10
"""Above 10% error rate, strip status flips to ERR."""

WARN_ABS_THRESHOLD = 5
"""Even at low error rates, ≥5 absolute errors trigger WARN."""


# --------------------------------------------------------------------------- #
# Dataclasses                                                                 #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class VelocitySparkline:
    """Token-rate sparkline for the velocity zone.

    The strip's velocity zone (200-264px in the spec) shows a small
    line chart of token-rate over time — 8 sample buckets across the
    session duration, rendered as a fill area below + stroke line above.

    Geometry is panel-relative: x in ``[x_left, x_right]`` and y in
    ``[0, area_h]`` where smaller y means higher velocity (SVG y-axis
    is inverted vs the conceptual chart).
    """

    points: list[tuple[float, float]]
    """List of ``(x, y)`` sample points, panel-relative coords."""
    fill_path: str
    """SVG path string for the gradient fill below the line (closed Z)."""
    stroke_path: str
    """SVG path string for the line stroke (M-L sequence, no Z)."""
    label_left: str
    """Time-axis left label, e.g. ``"0m"``."""
    label_right: str
    """Time-axis right label, e.g. ``"209m"``."""


@dataclass(frozen=True)
class StatusIndicator:
    """Status dot + label for the strip's right-hand status zone."""

    word: str
    """Display word: ``"OK"`` / ``"WARN"`` / ``"ERR"``."""
    severity: str
    """Severity slug for CSS: ``"ok"`` / ``"warn"`` / ``"err"``. Drives the
    ``var(--dna-*)`` token used for the dot fill."""
    color_var: str
    """CSS custom property name (without ``var()``), e.g. ``"--dna-status-passing-core"``."""


@dataclass(frozen=True)
class DominantPhase:
    """Dominant tool-class summary for the strip's status zone."""

    label: str
    """Display label, e.g. ``"EXPLORE"``."""
    tool_class: str
    """Tool class slug for CSS color via ``var(--dna-tool-{tool_class})``."""
    pct_time: int
    """Percent of session time this class dominated."""


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _format_tokens_compact(n: int) -> str:
    """Compact token formatter for the velocity number (e.g. ``492K``, ``1.2M``)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K" if n >= 10_000 else f"{n / 1_000:.1f}K"
    return str(n)


def _stage_tokens(s: dict[str, Any]) -> int:
    """Tokens for a stage with same fallback chain as bar_chart._stage_tokens."""
    if "tokens" in s:
        return int(s["tokens"])
    return int(s.get("tools", 0))


def _stage_class(s: dict[str, Any]) -> str:
    return str(s.get("dominant_class") or s.get("tool_class") or "explore")


def _stage_duration_m(s: dict[str, Any]) -> float:
    """Stage duration in minutes from start/end ISO timestamps. 0.0 if absent."""
    start, end = s.get("start"), s.get("end")
    if not start or not end:
        return 0.0
    try:
        t0 = datetime.fromisoformat(start)
        t_end = datetime.fromisoformat(end)
        return (t_end - t0).total_seconds() / 60.0
    except (ValueError, TypeError):
        return 0.0


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def compute_session_velocity(
    stages: list[dict[str, Any]],
    duration_m: float,
) -> tuple[int, str]:
    """Return ``(velocity_tokens_per_min, formatted_label)`` for the velocity zone.

    Args:
        stages: Normalized stage dicts.
        duration_m: Session duration in minutes.

    Returns:
        ``(velocity, label)`` where ``velocity`` is the integer
        tokens-per-minute over the session, and ``label`` is the compact
        display string (``"492K"``, ``"1.2M"``). Zero-duration sessions
        return ``(0, "0")``.
    """
    if duration_m <= 0:
        return 0, "0"
    total_tokens = sum(_stage_tokens(s) for s in stages)
    velocity = int(total_tokens / duration_m)
    return velocity, _format_tokens_compact(velocity)


def compute_velocity_sparkline(
    stages: list[dict[str, Any]],
    duration_m: float,
    *,
    x_left: float,
    x_right: float,
    y_top: float,
    y_bottom: float,
    n_buckets: int = 8,
) -> VelocitySparkline:
    """Bucket stages into ``n_buckets`` time slices, plot tokens/min per bucket.

    The output paths are panel-relative — the template embeds them inside
    a ``<g transform>`` for the velocity zone. Smaller y means higher
    velocity (SVG y-axis inverted vs conceptual chart).

    Args:
        stages: Normalized stage dicts. Must carry ``start`` + ``end``
            timestamps for accurate bucketing; falls back to even
            distribution when timestamps absent.
        duration_m: Session duration in minutes.
        x_left, x_right: Horizontal extent of the sparkline (panel coords).
        y_top, y_bottom: Vertical extent — values closer to ``y_top``
            represent higher velocity.
        n_buckets: Number of time buckets. The specimen uses 8.

    Returns:
        :class:`VelocitySparkline` with 8 ``(x, y)`` points and the SVG
        fill + stroke path strings. When stages are empty or duration is
        zero, returns paths that draw a flat baseline.
    """
    label_left = "0m"
    label_right = f"{int(duration_m)}m" if duration_m > 0 else "0m"

    if not stages or duration_m <= 0 or n_buckets < 2:
        flat_y = y_bottom
        flat_points: list[tuple[float, float]] = [
            (x_left + (x_right - x_left) * i / (n_buckets - 1 if n_buckets > 1 else 1), flat_y)
            for i in range(max(n_buckets, 2))
        ]
        return VelocitySparkline(
            points=flat_points,
            fill_path=_compose_fill_path(flat_points, y_bottom),
            stroke_path=_compose_stroke_path(flat_points),
            label_left=label_left,
            label_right=label_right,
        )

    # Bucket session timeline into n_buckets slices.
    bucket_duration_m = duration_m / n_buckets
    bucket_tokens = [0] * n_buckets

    has_timestamps = all(s.get("start") and s.get("end") for s in stages)
    if has_timestamps:
        # Distribute each stage's tokens across the buckets it spans.
        try:
            t0 = datetime.fromisoformat(stages[0]["start"])
        except (ValueError, TypeError):
            t0 = None
        if t0 is not None:
            for s in stages:
                try:
                    s_start = (datetime.fromisoformat(s["start"]) - t0).total_seconds() / 60.0
                    s_end = (datetime.fromisoformat(s["end"]) - t0).total_seconds() / 60.0
                except (ValueError, TypeError):
                    continue
                tokens = _stage_tokens(s)
                # Place tokens proportionally into the buckets the stage spans.
                stage_span = max(s_end - s_start, 0.001)
                for b in range(n_buckets):
                    b_start = b * bucket_duration_m
                    b_end = (b + 1) * bucket_duration_m
                    overlap = max(0.0, min(s_end, b_end) - max(s_start, b_start))
                    if overlap > 0:
                        bucket_tokens[b] += int(tokens * (overlap / stage_span))
    else:
        # Even distribution across buckets.
        per_bucket = sum(_stage_tokens(s) for s in stages) // n_buckets
        bucket_tokens = [per_bucket] * n_buckets

    # Convert bucket tokens to tokens/min, then normalize to sparkline y range.
    bucket_velocities = [bt / max(bucket_duration_m, 0.001) for bt in bucket_tokens]
    max_v = max(bucket_velocities) if bucket_velocities else 0
    max_v = max_v or 1.0  # divide-by-zero guard

    points: list[tuple[float, float]] = []
    span_x = x_right - x_left
    span_y = y_bottom - y_top
    for i, v in enumerate(bucket_velocities):
        x = x_left + span_x * i / max(n_buckets - 1, 1)
        # Inverted y: high velocity → small y (closer to y_top).
        y = y_bottom - span_y * (v / max_v)
        points.append((round(x, 2), round(y, 2)))

    return VelocitySparkline(
        points=points,
        fill_path=_compose_fill_path(points, y_bottom),
        stroke_path=_compose_stroke_path(points),
        label_left=label_left,
        label_right=label_right,
    )


def _compose_stroke_path(points: list[tuple[float, float]]) -> str:
    """Build an SVG path string for the line stroke (M-L sequence)."""
    if not points:
        return ""
    parts = [f"M{points[0][0]},{points[0][1]}"]
    parts.extend(f"L{x},{y}" for x, y in points[1:])
    return " ".join(parts)


def _compose_fill_path(points: list[tuple[float, float]], y_baseline: float) -> str:
    """Build a closed SVG path for the gradient fill below the stroke."""
    if not points:
        return ""
    parts = [f"M{points[0][0]},{points[0][1]}"]
    parts.extend(f"L{x},{y}" for x, y in points[1:])
    parts.append(f"L{points[-1][0]},{y_baseline}")
    parts.append(f"L{points[0][0]},{y_baseline}")
    parts.append("Z")
    return " ".join(parts)


def compute_status_dot(
    n_errors: int,
    total_calls: int,
) -> StatusIndicator:
    """Map error count + call volume to (severity word, CSS color var).

    Thresholds:
        * ``error_rate >= ERR_ERROR_RATE`` (10%) → ERR
        * ``error_rate >= WARN_ERROR_RATE`` (2%) OR ``n_errors >= WARN_ABS_THRESHOLD`` (5) → WARN
        * Otherwise → OK

    Returns:
        :class:`StatusIndicator` with the word, severity slug, and CSS
        custom-property name used to fill the dot.
    """
    if total_calls <= 0:
        return StatusIndicator(word="OK", severity="ok", color_var="--dna-status-passing-core")
    rate = n_errors / total_calls
    if rate >= ERR_ERROR_RATE:
        return StatusIndicator(word="ERR", severity="err", color_var="--dna-status-failing-core")
    if rate >= WARN_ERROR_RATE or n_errors >= WARN_ABS_THRESHOLD:
        return StatusIndicator(word="WARN", severity="warn", color_var="--dna-status-warning-core")
    return StatusIndicator(word="OK", severity="ok", color_var="--dna-status-passing-core")


def compute_dominant_phase(
    stages: list[dict[str, Any]],
    duration_m: float,
) -> DominantPhase:
    """Identify the dominant tool class by total time spent.

    Args:
        stages: Normalized stage dicts (``start``/``end`` ISO timestamps
            preferred for accurate time-share; falls back to call-count
            share when timestamps missing).
        duration_m: Total session duration in minutes (denominator for
            the percent calculation).

    Returns:
        :class:`DominantPhase` with the tool class, display label, and
        percent-time. Empty session returns ``("", "explore", 0)``.
    """
    if not stages:
        return DominantPhase(label="", tool_class="explore", pct_time=0)

    by_class: dict[str, float] = {}
    has_timestamps = all(s.get("start") and s.get("end") for s in stages)

    if has_timestamps and duration_m > 0:
        for s in stages:
            cls = _stage_class(s)
            by_class[cls] = by_class.get(cls, 0.0) + _stage_duration_m(s)
        if not by_class:
            return DominantPhase(label="", tool_class="explore", pct_time=0)
        dom_class, dom_minutes = max(by_class.items(), key=lambda kv: kv[1])
        # Normalize against total classified time (always sums to 100%) rather
        # than the full session duration, which can leave the ratio >100% when
        # stages overlap or active window < session window.
        total_classified_m = sum(by_class.values()) or 1.0
        pct = round(100.0 * dom_minutes / total_classified_m)
    else:
        # Fallback: count-based weighting.
        for s in stages:
            cls = _stage_class(s)
            by_class[cls] = by_class.get(cls, 0.0) + s.get("tools", 1)
        if not by_class:
            return DominantPhase(label="", tool_class="explore", pct_time=0)
        dom_class, dom_count = max(by_class.items(), key=lambda kv: kv[1])
        total = sum(by_class.values()) or 1
        pct = round(100.0 * dom_count / total)

    return DominantPhase(label=dom_class.upper(), tool_class=dom_class, pct_time=pct)
