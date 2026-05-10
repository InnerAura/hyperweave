"""Tests for receipt filename construction.

Pin slug discipline (lowercase, hyphens, max 80 chars, fs-safe) and
the priority chain: session_name → prompt_text → session_id → "receipt".
"""

from __future__ import annotations

from datetime import datetime

from hyperweave.telemetry.receipt_paths import receipt_filename, slugify_session_name

# --------------------------------------------------------------------------- #
# slugify_session_name                                                        #
# --------------------------------------------------------------------------- #


def test_slugify_lowercases_and_hyphenates_words() -> None:
    assert slugify_session_name("Hello World") == "hello-world"


def test_slugify_collapses_underscores_to_hyphens() -> None:
    """customTitle uses underscores; we want filename hyphens."""
    assert slugify_session_name("chrome_automata_variants_v03") == "chrome-automata-variants-v03"


def test_slugify_strips_filesystem_invalid_chars() -> None:
    """Cross-platform invalid chars (:/\\?*\"<>|) become hyphens."""
    raw = 'project: "fix/parser" <v0.2.26>?*'
    out = slugify_session_name(raw)
    for c in ':/\\?*"<>|':
        assert c not in out, f"invalid char {c!r} survived: {out!r}"


def test_slugify_collapses_consecutive_separators() -> None:
    """Multiple non-alphanumerics collapse to a single hyphen."""
    assert slugify_session_name("foo___bar   baz") == "foo-bar-baz"


def test_slugify_truncates_to_80_chars() -> None:
    long_input = "a" * 200
    assert len(slugify_session_name(long_input)) == 80


def test_slugify_truncate_does_not_leave_trailing_hyphen() -> None:
    """Truncation at a hyphen boundary should still produce a clean slug."""
    raw = "a" * 79 + "-tail"
    out = slugify_session_name(raw)
    assert not out.endswith("-")


def test_slugify_returns_empty_for_all_invalid_input() -> None:
    """Pure punctuation has no surviving alphanumerics — empty string."""
    assert slugify_session_name("!!!---___") == ""


def test_slugify_returns_empty_for_empty_input() -> None:
    assert slugify_session_name("") == ""


def test_slugify_preserves_alphanumerics_with_dots() -> None:
    """Version strings like v0.2.26 lose dots (treated as separator)."""
    assert slugify_session_name("v0.2.26") == "v0-2-26"


# --------------------------------------------------------------------------- #
# receipt_filename                                                            #
# --------------------------------------------------------------------------- #


def _ts(year: int = 2026, month: int = 5, day: int = 7, hour: int = 13, minute: int = 36) -> datetime:
    return datetime(year, month, day, hour, minute, 0)


def test_filename_uses_session_name_when_present() -> None:
    name = receipt_filename(_ts(), session_name="chrome-automata-variants-v03")
    assert name == "2026-05-07_1336_chrome-automata-variants-v03.svg"


def test_filename_falls_back_to_prompt_text() -> None:
    """Empty session_name → use first 40 chars of prompt_text slugified."""
    name = receipt_filename(
        _ts(),
        session_name="",
        prompt_text="Build the new auth flow with OAuth and JWT",
    )
    # "Build the new auth flow with OAuth and JWT" → first 40 chars sliced first,
    # then slugified.
    assert "build-the-new-auth-flow" in name


def test_filename_falls_back_to_session_id() -> None:
    """Empty session_name and prompt → use session_id slugified."""
    name = receipt_filename(
        _ts(),
        session_name="",
        prompt_text="",
        session_id="5748cb2b-6dc5-4cda-a498-aea13bcfecfc",
    )
    assert name == "2026-05-07_1336_5748cb2b-6dc5-4cda-a498-aea13bcfecfc.svg"


def test_filename_uses_receipt_literal_when_all_empty() -> None:
    """All inputs empty → 'receipt' literal preserves a valid filename."""
    name = receipt_filename(_ts())
    assert name == "2026-05-07_1336_receipt.svg"


def test_filename_priority_session_name_wins_over_prompt() -> None:
    """session_name takes precedence even when prompt_text is also present."""
    name = receipt_filename(
        _ts(),
        session_name="primary-name",
        prompt_text="some other prompt",
    )
    assert "primary-name" in name
    assert "some-other-prompt" not in name


def test_filename_zero_padded_minute() -> None:
    """09:05 must format as 0905, not 95."""
    ts = datetime(2026, 5, 7, 9, 5, 0)
    name = receipt_filename(ts, session_name="x")
    assert "_0905_" in name


def test_filename_extension_is_svg() -> None:
    name = receipt_filename(_ts(), session_name="x")
    assert name.endswith(".svg")
