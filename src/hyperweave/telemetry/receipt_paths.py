"""Receipt filename construction and on-disk resolution.

Receipt artifacts are saved as ``{YYYYMMDD}_{slug}_{handle}.svg``:

* the date is the session START (first transcript line), not the regenerate
  clock — a session resumed days later keeps its original date prefix;
* the slug is the session's CURRENT name, falling back to the first user
  prompt for runtimes that have no naming concept (Codex 0.149.0 emits none);
* the handle is the leading block of the session id, and it is what makes the
  mutable slug safe.

The handle turns the filename into its own index. A session's existing receipt
is found by globbing ``*_{handle}.svg`` — no directory read, no sidecar, no
index file to keep in sync. So a mid-session rename is an ``os.replace`` onto
the new name rather than a second file, and because every session owns a
filename no other session can address, concurrent SessionEnd hooks across
parallel sessions cannot collide.

Earlier versions keyed the filename to immutable signals only and excluded the
session name outright, because a rename would otherwise strand the previous
file holding stale numbers. That constraint is lifted, not forgotten: the
orphan it guarded against is now prevented by rewriting the old file instead of
abandoning it (see :func:`resolve_receipt_path`, which also migrates receipts
written before the handle existed).

Slug priority: session name → first-prompt text → ``"receipt"``. Identity
always lives in the SVG metadata (``data-hw-id``, ``hw:artifact id``, and the
``receipt/1`` payload's ``session``); the filename is for human browsing.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

# Match characters that are unsafe in filenames on common filesystems.
# Intentionally aggressive — anything outside [a-z0-9_] becomes an underscore.
_SLUG_REPLACE = re.compile(r"[^a-z0-9]+")
_UNDERSCORE_COLLAPSE = re.compile(r"_+")
_SLUG_MAX_LEN = 80
# Leading block of a session id. Both runtimes emit UUID-shaped ids whose first
# hyphen-delimited group is 8 chars (Claude Code UUIDv4, Codex UUIDv7), which is
# collision-free within a receipts directory while staying readable.
_HANDLE_LEN = 8


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


def session_handle(session_id: str) -> str:
    """Leading block of a session id, slugified — the filename's identity segment.

    Returns ``""`` for an empty or unusable id, in which case the filename
    carries no handle and :func:`resolve_receipt_path` cannot rewrite in place.
    """
    return slugify_session_name(session_id[:_HANDLE_LEN])


def receipt_filename(
    timestamp: datetime,
    session_id: str = "",
    title: str = "",
    prompt_text: str = "",
) -> str:
    """Build a human-readable receipt filename.

    Format: ``{YYYYMMDD}_{slug}_{handle}.svg``. ``timestamp`` is the session
    START, so a resume hours or days later still lands on the same date prefix.
    ``title`` is the session's live name and MAY change between regenerates —
    :func:`resolve_receipt_path` is what keeps that from stranding a file.
    Local time is assumed; the SVG metadata carries the canonical UTC stamp.

    Slug priority: ``title`` → ``prompt_text[:40]`` → ``"receipt"``. The session
    id is not a slug source — the handle already carries that identity.
    """
    slug = slugify_session_name(title) or slugify_session_name(prompt_text[:40]) or "receipt"
    date_part = timestamp.strftime("%Y%m%d")
    handle = session_handle(session_id)
    return f"{date_part}_{slug}_{handle}.svg" if handle else f"{date_part}_{slug}.svg"


def _find_by_handle(receipts_dir: Path, handle: str) -> Path | None:
    """Locate this session's receipt by its filename handle."""
    matches = sorted(receipts_dir.glob(f"*_{handle}.svg"))
    return matches[0] if matches else None


def _find_legacy(receipts_dir: Path, session_id: str) -> Path | None:
    """Locate a receipt written before the handle existed, by embedded session id.

    Pre-handle filenames carry no identity, so the id has to be read out of the
    artifact — it appears in the ``receipt/1`` payload, the ``hwz/1`` envelope
    and the footer line, so a plain substring search is enough and stays robust
    to JSON spacing. Runs only on a handle miss, and the rename it triggers
    means it never runs twice for the same session.
    """
    if not session_id:
        return None
    for candidate in sorted(receipts_dir.glob("*.svg")):
        try:
            if session_id in candidate.read_text(errors="ignore"):
                return candidate
        except OSError:
            continue
    return None


def resolve_receipt_path(
    receipts_dir: Path,
    timestamp: datetime,
    session_id: str = "",
    title: str = "",
    prompt_text: str = "",
) -> Path:
    """Return where this session's receipt belongs, moving any prior file there.

    Guarantees one receipt per session: if the session already has a receipt
    under a different name — because it was renamed, or because it predates the
    handle — that file is renamed onto the new path rather than left behind as
    a stale duplicate. ``os.replace`` within one directory is atomic, and the
    handle scopes every operation to a single session, so parallel hooks ending
    different sessions never touch the same path.
    """
    desired = receipts_dir / receipt_filename(
        timestamp=timestamp, session_id=session_id, title=title, prompt_text=prompt_text
    )
    handle = session_handle(session_id)
    if not handle:
        return desired

    existing = _find_by_handle(receipts_dir, handle) or _find_legacy(receipts_dir, session_id)
    if existing is not None and existing != desired:
        os.replace(existing, desired)
    return desired
