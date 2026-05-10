"""Receipt filename construction.

Receipt artifacts are saved as `{YYYY-MM-DD}_{HHMM}_{slug}.svg`. The slug
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
# Intentionally aggressive — anything outside [a-z0-9-] becomes a hyphen.
_SLUG_REPLACE = re.compile(r"[^a-z0-9]+")
_HYPHEN_COLLAPSE = re.compile(r"-+")
_SLUG_MAX_LEN = 80


def slugify_session_name(raw: str) -> str:
    """Lowercase, collapse non-alphanumerics to single hyphens, trim to 80 chars.

    Returns ``""`` when the input has no surviving alphanumeric characters,
    letting callers fall back to the next priority signal.
    """
    if not raw:
        return ""
    lowered = raw.lower()
    hyphenated = _SLUG_REPLACE.sub("-", lowered)
    collapsed = _HYPHEN_COLLAPSE.sub("-", hyphenated).strip("-")
    if not collapsed:
        return ""
    return collapsed[:_SLUG_MAX_LEN].rstrip("-")


def receipt_filename(
    timestamp: datetime,
    session_name: str = "",
    session_id: str = "",
    prompt_text: str = "",
) -> str:
    """Build a human-readable receipt filename.

    Format: ``{YYYY-MM-DD}_{HHMM}_{slug}.svg``. Local time is assumed; the
    receipt SVG metadata carries the canonical UTC timestamp.

    Slug source priority: ``session_name`` → ``prompt_text[:40]`` →
    ``session_id``. Empty input at every stage falls back to ``"receipt"``
    (date/time prefix still preserves uniqueness).
    """
    slug = slugify_session_name(session_name)
    if not slug and prompt_text:
        slug = slugify_session_name(prompt_text[:40])
    if not slug and session_id:
        slug = slugify_session_name(session_id)
    if not slug:
        slug = "receipt"
    date_part = timestamp.strftime("%Y-%m-%d")
    time_part = timestamp.strftime("%H%M")
    return f"{date_part}_{time_part}_{slug}.svg"
