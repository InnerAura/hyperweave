"""Dotted ``--genome g.variant`` sugar (task #18).

``--genome primer.porcelain`` is shorthand for ``--genome primer --variant
porcelain`` — split on the FIRST dot, applied to both the compose path and every
receipt genome-resolution entry point. A dotted form plus a contradicting
``--variant`` is a clean error; bare names pass through unchanged.
"""

from __future__ import annotations

import re

import pytest

from hyperweave.cli import _resolve_receipt_genome, _split_dotted_genome

# ── compose-path split (_split_dotted_genome) ──────────────────────────────


def test_dotted_splits_into_genome_and_variant() -> None:
    assert _split_dotted_genome("primer.porcelain", "") == ("primer", "porcelain")


def test_dotted_splits_on_first_dot_only() -> None:
    # a second dot stays in the variant portion (genome slug is the head)
    assert _split_dotted_genome("primer.a.b", "") == ("primer", "a.b")


def test_dotted_with_agreeing_explicit_variant_ok() -> None:
    assert _split_dotted_genome("primer.cream", "cream") == ("primer", "cream")


def test_bare_genome_passes_through() -> None:
    assert _split_dotted_genome("brutalist", "") == ("brutalist", "")
    assert _split_dotted_genome("automata", "teal") == ("automata", "teal")


def test_dotted_conflicting_variant_raises_naming_both() -> None:
    with pytest.raises(ValueError) as exc:
        _split_dotted_genome("primer.porcelain", "cream")
    msg = str(exc.value)
    assert "porcelain" in msg and "cream" in msg  # names both


# ── receipt-path split (_resolve_receipt_genome) ───────────────────────────


def test_receipt_dotted_genome() -> None:
    assert _resolve_receipt_genome("primer.cream") == ("primer", "cream")


def test_receipt_bare_variant_shorthand_unchanged() -> None:
    # the pre-existing bare primer-variant shorthand still resolves
    assert _resolve_receipt_genome("cream") == ("primer", "cream")


def test_receipt_genome_slug_unchanged() -> None:
    assert _resolve_receipt_genome("primer") == ("primer", "")
    assert _resolve_receipt_genome("raw") == ("raw", "")


def test_receipt_empty_unchanged() -> None:
    assert _resolve_receipt_genome("") == ("", "")


# ── end-to-end through the CLI ─────────────────────────────────────────────

_FONT = re.compile(r"data:[^;]*;base64,[A-Za-z0-9+/=]+")
_TS = re.compile(r"\d{4}-\d{2}-\d{2}T[0-9:.+]+")


def _norm(svg: str) -> str:
    return _TS.sub("TS", _FONT.sub("FONT", svg))


def test_cli_dotted_equals_explicit(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from typer.testing import CliRunner

    from hyperweave.cli import app

    runner = CliRunner()
    dotted = tmp_path / "dotted.svg"
    explicit = tmp_path / "explicit.svg"
    r1 = runner.invoke(app, ["compose", "badge", "BUILD", "passing", "--genome", "primer.porcelain", "-o", str(dotted)])
    r2 = runner.invoke(
        app,
        ["compose", "badge", "BUILD", "passing", "--genome", "primer", "--variant", "porcelain", "-o", str(explicit)],
    )
    assert r1.exit_code == 0 and r2.exit_code == 0
    # dotted sugar produces the same artifact as the explicit pair (modulo provenance)
    assert _norm(dotted.read_text()) == _norm(explicit.read_text())


def test_cli_dotted_conflict_exits_2(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from typer.testing import CliRunner

    from hyperweave.cli import app

    result = CliRunner().invoke(
        app,
        [
            "compose",
            "badge",
            "BUILD",
            "passing",
            "--genome",
            "primer.porcelain",
            "--variant",
            "cream",
            "-o",
            str(tmp_path / "x.svg"),
        ],
    )
    assert result.exit_code == 2
    assert "porcelain" in result.output and "cream" in result.output
