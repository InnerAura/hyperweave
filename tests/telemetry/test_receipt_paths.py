"""Tests for receipt filename construction.

Pin slug discipline (lowercase, underscores, max 80 chars, fs-safe,
dots stripped) and the priority chain: session_name → prompt_text →
session_id → "receipt". Filename shape locked at YYYYMMDD_{slug}.svg
(v0.3.3 dropped the HHMM segment — full UTC timestamp survives in
the SVG metadata).
"""

from __future__ import annotations

from datetime import datetime

from hyperweave.telemetry.receipt_paths import receipt_filename, slugify_session_name

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


def test_filename_falls_back_to_session_id() -> None:
    """Empty prompt → use session_id slugified."""
    name = receipt_filename(
        _ts(),
        prompt_text="",
        session_id="5748cb2b-6dc5-4cda-a498-aea13bcfecfc",
    )
    assert name == "20260507_5748cb2b_6dc5_4cda_a498_aea13bcfecfc.svg"


def test_filename_uses_receipt_literal_when_all_empty() -> None:
    """All inputs empty → 'receipt' literal preserves a valid filename."""
    name = receipt_filename(_ts())
    assert name == "20260507_receipt.svg"


def test_filename_is_stable_across_rename_and_resume() -> None:
    """Same start date + first prompt → same filename, no matter the session name.

    The filename keys only on immutable signals, so a mid-session /rename or a
    resume on a later day never repoints the file (the resume-orphan + Codex
    rename fix). The session name is not even an input.
    """
    first = receipt_filename(_ts(), prompt_text="closing out alpha4 for tag", session_id="abc")
    again = receipt_filename(_ts(), prompt_text="closing out alpha4 for tag", session_id="abc")
    assert first == again == "20260507_closing_out_alpha4_for_tag.svg"


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
