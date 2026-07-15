"""Context-window occupancy modelling for the ``receipt/1`` payload.

The receipt's burn-curve renders how much of the model's context window was
occupied over a session and where it was reset (``/compact``, ``/clear``, or
auto-compaction). This module owns two concerns:

* **Window resolution** (`window_for_model`) — map a model id to its context
  window in tokens. Imported by the parsers so the occupancy series and its
  ceiling agree.
* **Summary assembly** (`build_context_summary`) — fold the parser's detected
  reset events, peak occupancy, and window into the compact ``context`` dict
  the payload embeds: ``{window, peak_ctx, events[], note}``.

It is a pure data layer: no SVG, no geometry. The curve *geometry* (paths,
axis ticks, glyph placement) is a separate render-side concern that consumes
this summary. The note is carried verbatim from the hand-authored specimen so
the artifact self-discloses that occupancy is modelled, not measured.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import ToolOutcome

if TYPE_CHECKING:
    from .models import SessionTelemetry

# Default context window when a model id is unknown. 200K is the floor across
# the current Claude line; resolving lower would draw a curve that overshoots
# its own ceiling, which the receipt must never do.
DEFAULT_CONTEXT_WINDOW = 200_000

# Window in tokens for the extended-context (-1m / [1m]) tier.
_EXTENDED_WINDOW = 1_000_000

# Self-disclosure carried verbatim from the receipt specimen. The receipt
# embeds this in the context block so a reader knows the curve is a model of
# occupancy from per-turn activity, not a billed measurement.
CONTEXT_NOTE = (
    "occupancy modelled from per-stage activity; resets at slash-command and auto-compaction; absolute scale disclosed"
)


# Doc-sourced context windows (Anthropic, July 2026). In Claude Code, Opus
# 4.6/4.7/4.8, Fable 5, Mythos 5, Sonnet 5, and Sonnet 4.6 run a 1M window
# (with usage credits); Haiku 4.5, Sonnet 4.5 (default — 1M is an opt-in beta)
# and the legacy lines are 200K. Matched by longest id prefix. The Sonnet-4.5
# beta and any future 1M usage is recovered from observed occupancy by the
# parser's tolerance backstop, so this table is the BASELINE, not the last word.
_MODEL_WINDOWS: dict[str, int] = {
    "claude-opus-4-8": _EXTENDED_WINDOW,
    "claude-opus-4-7": _EXTENDED_WINDOW,
    "claude-opus-4-6": _EXTENDED_WINDOW,
    "claude-fable-5": _EXTENDED_WINDOW,
    "claude-mythos-5": _EXTENDED_WINDOW,
    "claude-sonnet-5": _EXTENDED_WINDOW,
    "claude-sonnet-4-6": _EXTENDED_WINDOW,
    "claude-sonnet-4-5": DEFAULT_CONTEXT_WINDOW,
    "claude-haiku-4-5": DEFAULT_CONTEXT_WINDOW,
    "gpt-5": 258_400,  # codex fallback; codex_parser reads the real window inline
}


def window_for_model(model: str | None) -> int:
    """Resolve a model id to its BASELINE context window in tokens.

    Precedence: an explicit 1M marker in the id (``-1m`` / ``[1m]`` / ``_1m`` /
    bare ``1m``) → 1,000,000; else the doc-sourced :data:`_MODEL_WINDOWS` table
    (longest-prefix match); else the 200,000 default. This is the *baseline* —
    the parser's tolerance backstop (``parser._model_window``) promotes a
    genuinely-200K model to 1M only when observed occupancy clearly exceeds
    200K (the Sonnet-4.5 1M beta); a few-K ceiling overshoot is NOT a promotion.

    A ``None`` or empty id returns the default window.
    """
    if not model:
        return DEFAULT_CONTEXT_WINDOW
    normalized = model.lower()
    for marker in ("-1m", "[1m]", "_1m", " 1m"):
        if marker in normalized:
            return _EXTENDED_WINDOW
    if normalized.endswith("1m") and not normalized[:-2].rstrip().endswith(tuple("0123456789")):
        return _EXTENDED_WINDOW
    for prefix in sorted(_MODEL_WINDOWS, key=len, reverse=True):
        if normalized.startswith(prefix):
            return _MODEL_WINDOWS[prefix]
    return DEFAULT_CONTEXT_WINDOW


def _elapsed_span_minutes(t: SessionTelemetry) -> int:
    """Elapsed wall-clock span of the session in minutes (first activity → last).

    The burn-curve x-axis runs on this span, NOT the active-work sum
    (``active_min``): reset events are timestamped on the wall clock, so a session
    resumed across days (large span, few active minutes) must place its glyphs on
    the same clock or they crush onto the right rail. Computed as the latest
    activity timestamp (tool call / reset / subagent end) minus the session start,
    floored at ``duration_minutes`` and 1 so the extent always covers the curve.
    """
    latest = t.timestamp
    for tc in t.tool_calls:
        if tc.timestamp > latest:
            latest = tc.timestamp
    for ev in t.command_events:
        if ev.timestamp > latest:
            latest = ev.timestamp
    for a in t.agents:
        if a.end_time is not None and a.end_time > latest:
            latest = a.end_time
    span = (latest - t.timestamp).total_seconds() / 60.0
    return max(round(span), round(t.duration_minutes), 1)


def build_context_summary(t: SessionTelemetry) -> dict[str, object]:
    """Assemble the compact ``context`` dict for the ``receipt/1`` payload.

    Produces ``{window, peak_ctx, span_min, events[], error_min[], note}`` where each event is
    ``{min, cmd, to}`` — minutes from session start, reset kind, and the
    modelled occupancy after the reset. Raw values only (no formatted
    strings); the payload is a hashed contract.

    ``window`` prefers the parser-resolved ``context_window``; when the parser
    could not determine one (0), it falls back to the model-keyed default so
    the curve always has a ceiling. ``peak_ctx`` is the parser's observed peak,
    clamped to the window (a modelled peak can momentarily read above the
    nominal window on the turn that triggers auto-compaction).
    """
    window = t.context_window or window_for_model(t.model)
    peak = min(t.peak_context_tokens, window) if t.peak_context_tokens else 0

    events: list[dict[str, object]] = []
    for ev in t.command_events:
        minutes = max((ev.timestamp - t.timestamp).total_seconds() / 60.0, 0.0)
        events.append(
            {
                "min": round(minutes),
                "cmd": ev.kind.value,
                "to": ev.occupancy_after,
            }
        )

    # Real minutes of each MAIN-THREAD error (the tool call's wall-clock offset),
    # for the burn curve's error ticks — anchored to WHEN, like reset events.
    # BLOCKED is a denial, not a failure; a subagent erroring in its own context
    # is not an event on this main-thread timeline.
    error_min = sorted(
        round(max((c.timestamp - t.timestamp).total_seconds() / 60.0, 0.0))
        for c in t.tool_calls
        if c.outcome is ToolOutcome.ERROR and not c.is_subagent
    )

    return {
        "window": window,
        "peak_ctx": peak,
        "span_min": _elapsed_span_minutes(t),
        "events": events,
        "error_min": error_min,
        "note": CONTEXT_NOTE,
    }
