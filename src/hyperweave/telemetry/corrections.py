"""Correction Detector -- Four-Category User Message Classification.

Classifies user messages using dual signals:

1. **Lexical signal**: Keyword patterns in user message text
2. **Behavioral signal**: Tool patterns in subsequent assistant actions

Categories:
    - correction:   User is telling the system it made a mistake
    - redirection:  User is changing the task/approach
    - elaboration:  User is adding requirements to the current task
    - continuation: Default -- normal conversational flow

Design choice: High precision over high recall. Better to miss a
correction than to falsely label normal dialogue.

Ported from aura-research/systems/hooks/hw_claude_code_hook/correction_detector.py.
Lexical patterns are logic (stay in Python), not config.
"""

from __future__ import annotations

import re

from .models import (
    ConfidenceLevel,
    ToolCall,
    UserEvent,
    UserEventCategory,
)

# --------------------------------------------------------------------------- #
# LEXICAL PATTERNS
# --------------------------------------------------------------------------- #

CORRECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bno[,.]?\s", re.IGNORECASE), "no,"),
    (re.compile(r"\bthat'?s\s+wrong\b", re.IGNORECASE), "that's wrong"),
    (re.compile(r"\brevert\b", re.IGNORECASE), "revert"),
    (re.compile(r"\bundo\b", re.IGNORECASE), "undo"),
    (re.compile(r"\bdon'?t\b", re.IGNORECASE), "don't"),
    (re.compile(r"\bstop\b", re.IGNORECASE), "stop"),
    (re.compile(r"\bwrong\b", re.IGNORECASE), "wrong"),
    (re.compile(r"\bactually[,.]?\s", re.IGNORECASE), "actually"),
    (re.compile(r"\binstead\b", re.IGNORECASE), "instead"),
    (re.compile(r"\bnot what\b", re.IGNORECASE), "not what"),
]

REDIRECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\blet'?s\s+switch\b", re.IGNORECASE), "let's switch"),
    (re.compile(r"\bnew approach\b", re.IGNORECASE), "new approach"),
    (re.compile(r"\bnow let'?s\b", re.IGNORECASE), "now let's"),
    (re.compile(r"\bmoving on\b", re.IGNORECASE), "moving on"),
    (re.compile(r"\bdifferent\s+(approach|direction|way)\b", re.IGNORECASE), "different approach"),
    (re.compile(r"\bforget\s+(about|that)\b", re.IGNORECASE), "forget that"),
    (re.compile(r"\bchange\s+(of\s+)?plan\b", re.IGNORECASE), "change of plan"),
]

ELABORATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\balso[,.]?\s", re.IGNORECASE), "also,"),
    (re.compile(r"\badditionally\b", re.IGNORECASE), "additionally"),
    (re.compile(r"\bone more thing\b", re.IGNORECASE), "one more thing"),
    (re.compile(r"\band also\b", re.IGNORECASE), "and also"),
    (re.compile(r"\bplus\b", re.IGNORECASE), "plus"),
    (re.compile(r"\boh and\b", re.IGNORECASE), "oh and"),
]


def _lexical_classify(text: str) -> tuple[UserEventCategory | None, str | None]:
    """Classify text using lexical patterns."""
    for pattern, keyword in CORRECTION_PATTERNS:
        if pattern.search(text):
            return UserEventCategory.CORRECTION, keyword

    for pattern, keyword in REDIRECTION_PATTERNS:
        if pattern.search(text):
            return UserEventCategory.REDIRECTION, keyword

    for pattern, keyword in ELABORATION_PATTERNS:
        if pattern.search(text):
            return UserEventCategory.ELABORATION, keyword

    return None, None


# --------------------------------------------------------------------------- #
# BEHAVIORAL PATTERNS
# --------------------------------------------------------------------------- #


def _behavioral_classify(
    preceding_calls: list[ToolCall],
    subsequent_calls: list[ToolCall],
) -> tuple[UserEventCategory | None, str | None]:
    """Classify based on tool patterns before and after the user message."""
    if not preceding_calls or not subsequent_calls:
        return None, None

    pre_was_mutating = any(tc.tool_name in {"Edit", "Write"} for tc in preceding_calls)
    post_is_reading = any(tc.tool_name == "Read" for tc in subsequent_calls)
    post_is_mutating = any(tc.tool_name in {"Edit", "Write"} for tc in subsequent_calls)

    if pre_was_mutating and post_is_reading and post_is_mutating:
        return UserEventCategory.CORRECTION, "re-edit after read"

    if pre_was_mutating and post_is_reading and not post_is_mutating:
        return UserEventCategory.CORRECTION, "re-read after edit"

    pre_tool_names = {tc.tool_name for tc in preceding_calls}
    post_tool_names = {tc.tool_name for tc in subsequent_calls}
    if "Glob" in post_tool_names and "Glob" not in pre_tool_names:
        return UserEventCategory.REDIRECTION, "new file discovery"

    return None, None


# --------------------------------------------------------------------------- #
# MAIN CLASSIFIER
# --------------------------------------------------------------------------- #


def classify_user_events(
    events: list[UserEvent],
    all_tool_calls: list[ToolCall],
) -> list[UserEvent]:
    """Classify user events using dual-signal approach.

    Parameters
    ----------
    events
        Pre-extracted user events with timestamps and message previews.
    all_tool_calls
        Ordered list of all tool calls in the session.

    Returns
    -------
    list[UserEvent]
        Events with updated category, signals, and confidence.
    """
    if not events:
        return events

    sorted_calls = sorted(all_tool_calls, key=lambda tc: tc.timestamp)

    for event in events:
        text = event.message_preview

        lex_category, lex_keyword = _lexical_classify(text)

        before = [tc for tc in sorted_calls if tc.timestamp < event.timestamp][-5:]
        after = [tc for tc in sorted_calls if tc.timestamp > event.timestamp][:5]
        beh_category, beh_signal = _behavioral_classify(before, after)

        if lex_category and beh_category and lex_category == beh_category:
            event.category = lex_category
            event.lexical_signal = lex_keyword
            event.behavioral_signal = beh_signal
            event.confidence = ConfidenceLevel.HIGH
        elif lex_category:
            event.category = lex_category
            event.lexical_signal = lex_keyword
            event.confidence = ConfidenceLevel.MEDIUM
        elif beh_category:
            event.category = beh_category
            event.behavioral_signal = beh_signal
            event.confidence = ConfidenceLevel.LOW
        else:
            event.category = UserEventCategory.CONTINUATION
            event.confidence = ConfidenceLevel.HIGH

    return events
