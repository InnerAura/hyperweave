"""Receipt filename construction.

Receipt artifacts are saved as ``{YYYYMMDD}_{slug}.svg`` keyed entirely to
signals that are IMMUTABLE across a session's lifetime, so every regenerate
lands on the same file:

* the date is the session START (first transcript line), not the regenerate
  clock — a session resumed days later keeps its original date prefix;
* the slug is the FIRST user prompt, not the session name.

The mutable session name is deliberately NOT a slug source. A mid-session
rename (Claude /rename, Codex thread naming) would otherwise repoint the
filename and orphan the prior receipt on the next regenerate. The live name
renders in the footer identity line instead (read at render time).

Slug priority: first-prompt text → ``session_id`` → ``"receipt"``.
Filename construction is centralized here so CLI / hook / future MCP write
paths share one slug discipline. UUID identity always lives in the SVG
metadata (``data-hw-id`` and ``hw:artifact id``); the filename is for human
browsing only.
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
    session_id: str = "",
    prompt_text: str = "",
) -> str:
    """Build a stable, human-readable receipt filename.

    Format: ``{YYYYMMDD}_{slug}.svg``. Both inputs are IMMUTABLE across a
    session's lifetime, so the filename is identical on every regenerate
    (resume re-fires the SessionEnd hook; the per-turn Codex Stop hook
    rewrites in place): ``timestamp`` is the session START and ``prompt_text``
    is the first user prompt. The mutable session name is intentionally absent
    so a rename never repoints the file. Local time is assumed; the SVG
    metadata carries the canonical UTC timestamp.

    Slug source priority: ``prompt_text[:40]`` → ``session_id`` → ``"receipt"``.
    """
    slug = slugify_session_name(prompt_text[:40]) if prompt_text else ""
    if not slug and session_id:
        slug = slugify_session_name(session_id)
    if not slug:
        slug = "receipt"
    date_part = timestamp.strftime("%Y%m%d")
    return f"{date_part}_{slug}.svg"
