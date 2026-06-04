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


def test_filename_uses_session_name_when_present() -> None:
    name = receipt_filename(_ts(), session_name="chrome_automata_variants_v03")
    assert name == "20260507_chrome_automata_variants_v03.svg"


def test_filename_falls_back_to_prompt_text() -> None:
    """Empty session_name → use first 40 chars of prompt_text slugified."""
    name = receipt_filename(
        _ts(),
        session_name="",
        prompt_text="Build the new auth flow with OAuth and JWT",
    )
    # "Build the new auth flow with OAuth and JWT" → first 40 chars sliced first,
    # then slugified.
    assert "build_the_new_auth_flow" in name


def test_filename_falls_back_to_session_id() -> None:
    """Empty session_name and prompt → use session_id slugified."""
    name = receipt_filename(
        _ts(),
        session_name="",
        prompt_text="",
        session_id="5748cb2b-6dc5-4cda-a498-aea13bcfecfc",
    )
    assert name == "20260507_5748cb2b_6dc5_4cda_a498_aea13bcfecfc.svg"


def test_filename_uses_receipt_literal_when_all_empty() -> None:
    """All inputs empty → 'receipt' literal preserves a valid filename."""
    name = receipt_filename(_ts())
    assert name == "20260507_receipt.svg"


def test_filename_priority_session_name_wins_over_prompt() -> None:
    """session_name takes precedence even when prompt_text is also present."""
    name = receipt_filename(
        _ts(),
        session_name="primary_name",
        prompt_text="some other prompt",
    )
    assert "primary_name" in name
    assert "some_other_prompt" not in name


def test_filename_compact_date_no_separators_inside_date() -> None:
    """YYYYMMDD: no dashes, no underscores INSIDE the date prefix."""
    name = receipt_filename(_ts(year=2026, month=1, day=8), session_name="x")
    # date prefix is exactly 8 digits, followed by a single underscore separator
    assert name.startswith("20260108_")
    # First underscore must be the slug separator, not inside the date.
    date_segment = name.split("_", 1)[0]
    assert date_segment == "20260108"
    assert "-" not in date_segment


def test_filename_no_hhmm_segment() -> None:
    """v0.3.3 dropped the HHMM time segment — date prefix only."""
    # Same date, different times — same filename (only date + slug count).
    early = receipt_filename(datetime(2026, 5, 7, 0, 59), session_name="abc")
    late = receipt_filename(datetime(2026, 5, 7, 23, 1), session_name="abc")
    assert early == late == "20260507_abc.svg"


def test_filename_target_shape_receipt_debug_v0226() -> None:
    """Lock the exact v0.3.3 target shape from the bug report."""
    name = receipt_filename(
        datetime(2026, 5, 8, 0, 59),
        session_name="Receipt Debug v0.2.26",
    )
    assert name == "20260508_receipt_debug_v0226.svg"


def test_filename_extension_is_svg() -> None:
    name = receipt_filename(_ts(), session_name="x")
    assert name.endswith(".svg")
