"""One owner for text fit: measure → wrap → fit → truncate.

Identity text (names, headers, titles) fits with ``policy="grow"`` and never
ellipsizes — the caller widens or refuses. Descriptions fit with
``policy="report"``: the anatomy's line cap holds, the last shown line
carries the one ellipsis, and ``FitResult.overflow`` feeds the density
advisory. ``policy="ellipsize"`` is the same rendering without the report,
for cell text whose home has no advisory channel yet.

:func:`fit_box` chooses a width *before* committing to it — the narrowest
lawful width on a half-pixel grid whose natural (uncapped) wrap fits the
cap. Its feasibility predicate is :func:`wrap_natural`; it must never be
:func:`text_lines_needed`, which counts an already-capped result.

``wrap_text_lines`` / ``text_lines_needed`` / ``truncate_to_width`` are the
legacy capped trio the matrix and diagram callers still use verbatim. They
stay until every caller fits through :func:`fit` and :func:`fit_box`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from hyperweave.core.text import measure_text

if TYPE_CHECKING:
    from hyperweave.core.paradigm import MatrixVoice

ELLIPSIS = "…"
WIDTH_QUANTUM = 0.5
"""Widths are searched on this grid so the narrowest lawful width is byte-stable."""

Policy = Literal["grow", "report", "ellipsize"]


@dataclass(frozen=True, slots=True)
class Natural:
    """An uncapped greedy wrap: what the text needs, not what it was allowed."""

    lines: tuple[str, ...]
    unbreakable_overflow: bool
    """A single run wider than the available width — reported, never split."""


@dataclass(frozen=True, slots=True)
class FitResult:
    runs: tuple[str, ...]
    required_lines: int
    shown_lines: int
    ink_w: float
    overflow: bool
    truncated: bool


def measure_voice(text: str, voice: MatrixVoice) -> float:
    """Measure ``text`` in a named type voice."""
    return measure_text(
        text,
        font_family=voice.family,
        font_size=voice.size,
        font_weight=voice.weight,
        letter_spacing_em=voice.tracking_em,
    )


def truncate_to_width(text: str, max_w: float, voice: MatrixVoice) -> str:
    """Longest prefix of ``text`` that fits ``max_w``, ellipsized.

    Measurement-based (per-font LUTs), so the ellipsis lands where the ink
    actually runs out. The untruncated string stays in the payload by
    construction — truncation only affects the rendered run. A non-positive
    budget returns the text unchanged (legacy contract; :func:`fit_line`
    defines the degenerate case).
    """
    if not text or max_w <= 0 or measure_voice(text, voice) <= max_w:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = text[:mid].rstrip() + ELLIPSIS
        if measure_voice(candidate, voice) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    if lo == 0:
        return ELLIPSIS
    return text[:lo].rstrip() + ELLIPSIS


def fit_line(text: str, voice: MatrixVoice, avail: float) -> str:
    """One run that fits ``avail``: the text itself, its ellipsized prefix, or
    nothing at all when there is no room — the shared degenerate rule."""
    if not text or avail <= 0:
        return ""
    return truncate_to_width(text, avail, voice)


def wrap_natural(text: str, voice: MatrixVoice, avail: float) -> Natural:
    """Greedy word wrap with no line cap, honoring authored line breaks.

    A run wider than ``avail`` sits alone on its line and is *reported*
    through ``unbreakable_overflow``; it is never split or ellipsized here.
    """
    if not text:
        return Natural((), False)
    lines: list[str] = []
    overflow = False
    for para in text.split("\n"):
        current = ""
        for word in para.split(" "):
            candidate = word if not current else f"{current} {word}"
            if not current or measure_voice(candidate, voice) <= avail:
                current = candidate
            else:
                lines.append(current)
                current = word
            if measure_voice(word, voice) > avail:
                overflow = True
        lines.append(current)
    return Natural(tuple(lines), overflow)


def required_lines(text: str, voice: MatrixVoice, avail: float) -> int:
    return len(wrap_natural(text, voice, avail).lines)


def _widest(lines: tuple[str, ...] | list[str], voice: MatrixVoice) -> float:
    return max((measure_voice(line, voice) for line in lines), default=0.0)


def fit(text: str, voice: MatrixVoice, *, avail: float, max_lines: int, policy: Policy = "ellipsize") -> FitResult:
    """Fit ``text`` into ``avail`` by ``max_lines`` under one policy.

    Terminal states when the natural wrap does not fit:

    * ``grow`` — the natural runs come back untouched with ``overflow=True``;
      the caller widens another axis or raises a typed refusal. Nothing is
      ellipsized under ``grow``.
    * ``report`` / ``ellipsize`` — the first ``max_lines`` runs render, the
      last shown run absorbs the remainder and carries one ellipsis, any run
      wider than ``avail`` is truncated to fit, ``truncated=True``. ``report``
      is the caller's cue to emit the density advisory; the runs are identical.
    * ``avail <= 0`` — nothing renders, ``overflow=True``.
    """
    if not text:
        return FitResult((), 0, 0, 0.0, False, False)
    cap = max(1, max_lines)
    if avail <= 0:
        return FitResult((), len(text.split("\n")), 0, 0.0, True, False)
    natural = wrap_natural(text, voice, avail)
    required = len(natural.lines)
    if required <= cap and not natural.unbreakable_overflow:
        return FitResult(natural.lines, required, required, _widest(natural.lines, voice), False, False)
    if policy == "grow":
        return FitResult(natural.lines, required, required, _widest(natural.lines, voice), True, False)
    shown = list(natural.lines[:cap])
    truncated = required > cap
    if truncated:
        shown[-1] = truncate_to_width(" ".join(natural.lines[cap - 1 :]), avail, voice)
    for i, line in enumerate(shown):
        if measure_voice(line, voice) > avail:
            shown[i] = truncate_to_width(line, avail, voice)
            truncated = True
    return FitResult(tuple(shown), required, len(shown), _widest(shown, voice), True, truncated)


def width_candidates(w_min: float, w_max: float) -> list[float]:
    """``{w_min}``, the interior half-pixel grid, and ``{w_max}`` — both exact bounds
    are always candidates, so a legal off-grid bound can never read as
    overflow."""
    lo, hi = min(w_min, w_max), max(w_min, w_max)
    first = math.ceil(lo / WIDTH_QUANTUM)
    last = math.floor(hi / WIDTH_QUANTUM)
    interior = {k * WIDTH_QUANTUM for k in range(first, last + 1)}
    return sorted({lo, hi} | {w for w in interior if lo < w < hi})


def fit_box(text: str, voice: MatrixVoice, *, w_min: float, w_max: float, max_lines: int) -> tuple[float, FitResult]:
    """Wrap before width: the narrowest width in ``[w_min, w_max]`` whose
    natural wrap fits ``max_lines`` with no unbreakable run.

    Greedy first-fit line count is non-increasing in width and unbreakable
    overflow is monotone, so a binary search over :func:`width_candidates`
    is exact; the winning candidate is re-validated by :func:`fit`. When
    even ``w_max`` fails, the result is ``w_max`` with ``overflow=True``.
    """
    lo, hi = min(w_min, w_max), max(w_min, w_max)
    if not text:
        return lo, fit(text, voice, avail=lo, max_lines=max_lines, policy="report")
    cap = max(1, max_lines)
    candidates = width_candidates(lo, hi)

    def feasible(w: float) -> bool:
        natural = wrap_natural(text, voice, w)
        return len(natural.lines) <= cap and not natural.unbreakable_overflow

    left, right = 0, len(candidates)
    while left < right:
        mid = (left + right) // 2
        if feasible(candidates[mid]):
            right = mid
        else:
            left = mid + 1
    width = candidates[left] if left < len(candidates) else hi
    return width, fit(text, voice, avail=width, max_lines=cap, policy="report")


def wrap_text_lines(text: str, max_w: float, voice: MatrixVoice, *, max_lines: int) -> list[str]:
    """Greedy word wrap into at most ``max_lines`` runs (the legacy capped wrapper).

    Wrapping is the default overflow behavior for text cells — the
    ellipsis appears only on the final permitted line, when content
    genuinely exceeds the cap (or a single word outruns the column).
    """
    if not text:
        return []
    # Honor AUTHORED line breaks first, then greedy-wrap each paragraph into
    # the remaining budget — an explicit break beats the heuristic, so a
    # two-phrase subtitle can declare exactly where it splits. Paragraphs
    # never drop (boxes grow to hold what the author wrote; max_lines is the
    # WRAP cap for one long paragraph, never a paragraph-count cap): the
    # effective budget floors at the authored paragraph count, and each
    # paragraph's own slice reserves one line for every paragraph still to
    # come, so an early long paragraph can no longer eat the whole budget
    # and silently erase a later one.
    if "\n" in text:
        paras = text.split("\n")
        n = len(paras)
        effective_max_lines = max(max_lines, n)
        out: list[str] = []
        for k, para in enumerate(paras):
            reserve = n - k - 1
            budget = max(1, effective_max_lines - len(out) - reserve)
            out.extend(wrap_text_lines(para, max_w, voice, max_lines=budget))
        return out[:effective_max_lines]
    if max_lines <= 1 or measure_voice(text, voice) <= max_w:
        return [truncate_to_width(text, max_w, voice)]
    words = text.split(" ")
    lines: list[str] = []
    i = 0
    while i < len(words):
        if len(lines) == max_lines - 1:
            lines.append(truncate_to_width(" ".join(words[i:]), max_w, voice))
            return lines
        current = words[i]
        i += 1
        while i < len(words) and measure_voice(current + " " + words[i], voice) <= max_w:
            current = current + " " + words[i]
            i += 1
        lines.append(truncate_to_width(current, max_w, voice))
    return lines


def text_lines_needed(text: str, max_w: float, voice: MatrixVoice, *, max_lines: int) -> int:
    """Line count :func:`wrap_text_lines` will produce — keeps the
    row-height pre-pass and the cell builder coupled. Counts a CAPPED result;
    never a feasibility predicate (use :func:`required_lines`)."""
    return max(1, len(wrap_text_lines(text, max_w, voice, max_lines=max_lines)))
