"""Receipt filename construction.

Receipt artifacts are saved as ``{YYYYMMDD}_{slug}.svg``. The slug
priority chain is:

1. ``session_name`` slugified — the parser-extracted human-readable name
   (Claude Code: latest customTitle; Codex: latest thread_name).
2. First-prompt text slugified — falls back to "what was the user actually
   doing?" when the runtime didn't surface a session title.
3. ``session_id`` — last-resort UUID, matches the pre-v0.3.1 behavior.

Filename construction is centralized here so CLI / hook / future MCP
write paths share one slug discipline. UUID identity always lives in the
SVG metadata (``data-hw-id`` and ``hw:artifact id``); the filename is for
human browsing only.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

# Match characters that are unsafe in filenames on common filesystems.
# Intentionally aggressive — anything outside [a-z0-9_] becomes an underscore.
_SLUG_REPLACE = re.compile(r"[^a-z0-9]+")
_UNDERSCORE_COLLAPSE = re.compile(r"_+")
_SLUG_MAX_LEN = 80


def slugify_session_name(raw: str) -> str:
    """Lowercase, collapse non-alphanumerics to single underscores, trim to 80 chars.

    Dots are stripped (no separator emitted), so version strings like
    ``v0.2.26`` collapse to ``v0226`` instead of ``v0-2-26``. All other
    non-alphanumeric runs collapse to a single underscore; consecutive
    underscores collapse further so ``foo___bar baz`` becomes ``foo_bar_baz``.

    Returns ``""`` when the input has no surviving alphanumeric characters,
    letting callers fall back to the next priority signal.
    """
    if not raw:
        return ""
    lowered = raw.lower()
    # Strip dots BEFORE collapsing other separators so version strings like
    # "v0.2.26" become "v0226" (concatenated) rather than "v0_2_26".
    dot_stripped = lowered.replace(".", "")
    underscored = _SLUG_REPLACE.sub("_", dot_stripped)
    collapsed = _UNDERSCORE_COLLAPSE.sub("_", underscored).strip("_")
    if not collapsed:
        return ""
    return collapsed[:_SLUG_MAX_LEN].rstrip("_")


def receipt_filename(
    timestamp: datetime,
    session_name: str = "",
    session_id: str = "",
    prompt_text: str = "",
) -> str:
    """Build a human-readable receipt filename.

    Format: ``{YYYYMMDD}_{slug}.svg``. Local time is assumed; the
    receipt SVG metadata carries the canonical UTC timestamp. The HHMM
    time segment was dropped in v0.3.3 — the YYYYMMDD prefix plus a
    human-readable slug is sufficient identity for filesystem browsing,
    and the full UTC timestamp survives in the SVG metadata.

    Slug source priority: ``session_name`` → ``prompt_text[:40]`` →
    ``session_id``. Empty input at every stage falls back to ``"receipt"``
    (date prefix still preserves uniqueness within a day).
    """
    slug = slugify_session_name(session_name)
    if not slug and prompt_text:
        slug = slugify_session_name(prompt_text[:40])
    if not slug and session_id:
        slug = slugify_session_name(session_id)
    if not slug:
        slug = "receipt"
    date_part = timestamp.strftime("%Y%m%d")
    return f"{date_part}_{slug}.svg"
