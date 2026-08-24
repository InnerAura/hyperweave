"""Tests for receipt filename construction and on-disk resolution.

Pin slug discipline (lowercase, underscores, max 80 chars, fs-safe,
dots stripped) and the priority chain: title → prompt_text → "receipt".
Filename shape locked at YYYYMMDD_{slug}_{handle}.svg (v0.3.3 dropped the
HHMM segment — full UTC timestamp survives in the SVG metadata).

The resolution tests run against a real directory rather than the pure
function alone. The invariant that matters to a caller is "one receipt per
session, named for the session's current title" — that is a property of the
directory after a rename cycle, and a filename-only assertion cannot see a
stranded duplicate sitting next to the new file.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from hyperweave.telemetry.receipt_paths import (
    receipt_filename,
    resolve_receipt_path,
    session_handle,
    slugify_session_name,
)

if TYPE_CHECKING:
    from pathlib import Path

# --------------------------------------------------------------------------- #
# slugify_session_name                                                        #
# --------------------------------------------------------------------------- #


def test_slugify_lowercases_and_underscores_words() -> None:
    assert slugify_session_name("Hello World") == "hello_world"


def test_slugify_collapses_underscores_to_single_underscore() -> None:
    """customTitle uses underscores; we want a clean single-underscore slug."""
    assert slugify_session_name("chrome_automata_variants_v03") == "chrome_automata_variants_v03"


def test_slugify_strips_filesystem_invalid_chars() -> None:
    """Cross-platform invalid chars (:/\\?*\"<>|) become underscores."""
    raw = 'project: "fix/parser" <v0.2.26>?*'
    out = slugify_session_name(raw)
    for c in ':/\\?*"<>|':
        assert c not in out, f"invalid char {c!r} survived: {out!r}"
    # Hyphens are NOT separators in the v0.3.3 slug shape — they collapse to underscore.
    assert "-" not in out


def test_slugify_collapses_consecutive_separators() -> None:
    """Multiple non-alphanumerics collapse to a single underscore."""
    assert slugify_session_name("foo___bar   baz") == "foo_bar_baz"


def test_slugify_truncates_to_80_chars() -> None:
    long_input = "a" * 200
    assert len(slugify_session_name(long_input)) == 80


def test_slugify_truncate_does_not_leave_trailing_underscore() -> None:
    """Truncation at an underscore boundary should still produce a clean slug."""
    raw = "a" * 79 + "_tail"
    out = slugify_session_name(raw)
    assert not out.endswith("_")


def test_slugify_returns_empty_for_all_invalid_input() -> None:
    """Pure punctuation has no surviving alphanumerics — empty string."""
    assert slugify_session_name("!!!---___") == ""


def test_slugify_returns_empty_for_empty_input() -> None:
    assert slugify_session_name("") == ""


def test_slugify_strips_dots_without_separator() -> None:
    """Version strings like v0.2.26 strip dots entirely (no separator emitted)."""
    assert slugify_session_name("v0.2.26") == "v0226"


def test_slugify_dot_stripping_does_not_drop_alphanumerics() -> None:
    """Dot stripping only removes '.'; surrounding alphanumerics survive."""
    assert slugify_session_name("Receipt Debug v0.2.26") == "receipt_debug_v0226"


def test_slugify_hyphen_collapses_to_underscore() -> None:
    """Hyphens were the separator pre-v0.3.3; now they collapse like any non-alphanumeric."""
    assert slugify_session_name("foo-bar-baz") == "foo_bar_baz"


# --------------------------------------------------------------------------- #
# receipt_filename                                                            #
# --------------------------------------------------------------------------- #


def _ts(year: int = 2026, month: int = 5, day: int = 7, hour: int = 13, minute: int = 36) -> datetime:
    return datetime(year, month, day, hour, minute, 0)


def test_filename_uses_first_prompt() -> None:
    """The slug is the first prompt, sliced to 40 chars then slugified."""
    name = receipt_filename(
        _ts(),
        prompt_text="Build the new auth flow with OAuth and JWT",
    )
    assert "build_the_new_auth_flow" in name


def test_filename_prefers_title_over_prompt() -> None:
    """The session's live name outranks the first prompt as the slug source."""
    name = receipt_filename(
        _ts(),
        session_id="855a060a-9f3c-49d3-a4ef-cbd381b14f74",
        title="hw_agent_skills",
        prompt_text="AUDIT: is this skill referenced anywhere",
    )
    assert name == "20260507_hw_agent_skills_855a060a.svg"


def test_filename_falls_back_to_prompt_without_title() -> None:
    """Runtimes with no naming concept (Codex) still get a readable slug."""
    name = receipt_filename(
        _ts(),
        session_id="01a02201-8a15-7ee1-8c8b-5e308a948772",
        prompt_text="AUDIT ONLY: what is needed to implement",
        title="",
    )
    assert name == "20260507_audit_only_what_is_needed_to_implement_01a02201.svg"


def test_filename_falls_back_to_literal_keeping_the_handle() -> None:
    """No title and no prompt → the handle still carries identity.

    The session id is no longer a slug source; slugifying it produced the
    unreadable full-UUID filenames that shipped for Codex sessions.
    """
    name = receipt_filename(_ts(), session_id="5748cb2b-6dc5-4cda-a498-aea13bcfecfc")
    assert name == "20260507_receipt_5748cb2b.svg"


def test_handle_is_the_leading_id_block() -> None:
    assert session_handle("855a060a-9f3c-49d3-a4ef-cbd381b14f74") == "855a060a"
    assert session_handle("") == ""


def test_filename_uses_receipt_literal_when_all_empty() -> None:
    """All inputs empty → 'receipt' literal preserves a valid filename."""
    name = receipt_filename(_ts())
    assert name == "20260507_receipt.svg"


def test_filename_is_stable_when_nothing_changed() -> None:
    """Same inputs → same filename, so a plain regenerate rewrites in place."""
    first = receipt_filename(_ts(), session_id="abc12345", title="closing out alpha4")
    again = receipt_filename(_ts(), session_id="abc12345", title="closing out alpha4")
    assert first == again == "20260507_closing_out_alpha4_abc12345.svg"


def test_filename_compact_date_no_separators_inside_date() -> None:
    """YYYYMMDD: no dashes, no underscores INSIDE the date prefix."""
    name = receipt_filename(_ts(year=2026, month=1, day=8), prompt_text="x")
    # date prefix is exactly 8 digits, followed by a single underscore separator
    assert name.startswith("20260108_")
    # First underscore must be the slug separator, not inside the date.
    date_segment = name.split("_", 1)[0]
    assert date_segment == "20260108"
    assert "-" not in date_segment


def test_filename_date_is_start_not_regenerate_clock() -> None:
    """Same date, different times → same filename (date prefix only, no HHMM).

    A resume hours later re-fires the hook; because the date prefix is the
    session START, the regenerate lands on the same file.
    """
    early = receipt_filename(datetime(2026, 5, 7, 0, 59), prompt_text="abc")
    late = receipt_filename(datetime(2026, 5, 7, 23, 1), prompt_text="abc")
    assert early == late == "20260507_abc.svg"


def test_filename_slugifies_prompt_dots_and_spaces() -> None:
    """A versiony first prompt slugifies cleanly (dots dropped, spaces → _)."""
    name = receipt_filename(
        datetime(2026, 5, 8, 0, 59),
        prompt_text="Receipt Debug v0.2.26",
    )
    assert name == "20260508_receipt_debug_v0226.svg"


def test_filename_extension_is_svg() -> None:
    name = receipt_filename(_ts(), prompt_text="x")
    assert name.endswith(".svg")


# --------------------------------------------------------------------------- #
# resolve_receipt_path — one receipt per session, on a real directory          #
# --------------------------------------------------------------------------- #

_SID = "855a060a-9f3c-49d3-a4ef-cbd381b14f74"
_OTHER_SID = "bc50a441-2a68-47ea-ad5b-3ae38a9002ab"


def _write(path: Path, session_id: str = _SID) -> Path:
    """Stand in for a rendered receipt — the session id is what identifies it."""
    path.write_text(f'<svg><hw:payload>{{"session":"{session_id}"}}</hw:payload></svg>')
    return path


def test_resolve_renames_the_previous_receipt_instead_of_duplicating(tmp_path: Path) -> None:
    """A mid-session rename must move the file, never strand a stale twin.

    This is the invariant the old immutable-filename law protected by refusing
    to use the title at all; the handle lets the title move without the orphan.
    """
    before = resolve_receipt_path(tmp_path, _ts(), session_id=_SID, title="hw_agent_skills")
    _write(before)

    after = resolve_receipt_path(tmp_path, _ts(), session_id=_SID, title="receipt_index_json")

    assert after.name == "20260507_receipt_index_json_855a060a.svg"
    assert sorted(p.name for p in tmp_path.glob("*.svg")) == [after.name]
    assert _SID in after.read_text(), "renamed file must be the original artifact"


def test_resolve_migrates_a_receipt_written_before_the_handle(tmp_path: Path) -> None:
    """Legacy names carry no handle, so the session id is read out of the file."""
    legacy = _write(tmp_path / "20260507_audit_is_src_hyperweave_data_skills_hyp.svg")

    resolved = resolve_receipt_path(tmp_path, _ts(), session_id=_SID, title="hw_agent_skills")

    assert not legacy.exists(), "legacy file should be renamed, not left beside the new one"
    assert sorted(p.name for p in tmp_path.glob("*.svg")) == ["20260507_hw_agent_skills_855a060a.svg"]
    assert resolved.name == "20260507_hw_agent_skills_855a060a.svg"


def test_resolve_keeps_same_titled_sessions_apart(tmp_path: Path) -> None:
    """Two sessions sharing a title must not resolve onto one path.

    Without the handle these collide and the second write clobbers the first.
    """
    one = resolve_receipt_path(tmp_path, _ts(), session_id=_SID, title="v043_dev")
    _write(one, _SID)
    two = resolve_receipt_path(tmp_path, _ts(), session_id=_OTHER_SID, title="v043_dev")
    _write(two, _OTHER_SID)

    assert one != two
    assert len(list(tmp_path.glob("*.svg"))) == 2


def test_resolve_is_idempotent(tmp_path: Path) -> None:
    """Re-resolving an unchanged session returns the same path and moves nothing.

    The Codex Stop hook fires every turn, so this is the common path.
    """
    first = resolve_receipt_path(tmp_path, _ts(), session_id=_SID, title="hw_agent_skills")
    _write(first)
    again = resolve_receipt_path(tmp_path, _ts(), session_id=_SID, title="hw_agent_skills")

    assert first == again
    assert len(list(tmp_path.glob("*.svg"))) == 1


def test_resolve_leaves_other_sessions_untouched(tmp_path: Path) -> None:
    """Resolution is scoped by handle — a parallel session's file is not read or moved."""
    stranger = _write(tmp_path / "20260507_other_work_bc50a441.svg", _OTHER_SID)
    resolve_receipt_path(tmp_path, _ts(), session_id=_SID, title="hw_agent_skills")

    assert stranger.exists()


def test_resolve_without_session_id_still_names_a_file(tmp_path: Path) -> None:
    """No id → no handle and no rewrite, but a valid path (compose -o, no transcript id)."""
    resolved = resolve_receipt_path(tmp_path, _ts(), session_id="", title="orphan")
    assert resolved.name == "20260507_orphan.svg"
