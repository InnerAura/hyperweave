"""Context-window resolution + reset classification — the v0.4 parser fixes.

These pin behavior the prior fixtures missed (and the visual review caught):
the 1M-window models resolve to 1M, a genuine 200K session sitting at its
ceiling stays 200K (a tolerance, not promote-on-any-overshoot), and a lone
``isCompactSummary`` marker classifies as an auto-compaction — not a manual
``/compact`` — so the burn curve draws the auto glyph for auto-compacted runs.
"""

from __future__ import annotations

import pathlib

import pytest

from hyperweave.telemetry.context import window_for_model
from hyperweave.telemetry.contract import build_receipt_contract
from hyperweave.telemetry.models import CommandResetKind
from hyperweave.telemetry.parser import _detect_context_events, _model_window

_FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"


@pytest.mark.parametrize(
    "model,window",
    [
        ("claude-fable-5", 1_000_000),
        ("claude-opus-4-8", 1_000_000),
        ("claude-opus-4-7", 1_000_000),
        ("claude-opus-4-6", 1_000_000),
        ("claude-sonnet-4-6", 1_000_000),
        ("claude-sonnet-4-5", 200_000),
        ("claude-haiku-4-5", 200_000),
        ("claude-opus-4-7-1m", 1_000_000),  # explicit 1M id marker
        ("gpt-5.5", 258_400),
        ("", 200_000),
        (None, 200_000),
    ],
)
def test_window_for_model_baseline(model: str | None, window: int) -> None:
    """The doc-sourced table resolves each model to its real baseline window."""
    assert window_for_model(model) == window


def test_genuine_200k_at_ceiling_stays_200k() -> None:
    """A real 200K model reading slightly over 200K at its ceiling (cache +
    token-accounting overhead) is NOT promoted to 1M — the tolerance is the fix,
    not the old promote-on-any-overshoot that drew a full session as ~20% full."""
    assert _model_window("claude-haiku-4-5", 203_600) == 200_000
    assert _model_window("claude-haiku-4-5", 215_000) == 200_000


def test_1m_beta_promotes_from_observed_occupancy() -> None:
    """A 200K-default model whose occupancy clearly exceeds 200K used the 1M beta."""
    assert _model_window("claude-sonnet-4-5", 500_000) == 1_000_000


def test_1m_model_window_independent_of_occupancy() -> None:
    """A 1M-baseline model is 1M whether it used 203K or 999K — no spurious
    promotion, and never a shrink that would overshoot the drawn ceiling."""
    assert _model_window("claude-opus-4-7", 203_600) == 1_000_000
    assert _model_window("claude-opus-4-7", 999_427) == 1_000_000


def _assistant(occ: int) -> dict[str, object]:
    """A minimal assistant line carrying ``occ`` tokens of context (cache_read)."""
    return {
        "type": "assistant",
        "timestamp": "2026-01-01T00:00:00Z",
        "message": {"usage": {"cache_read_input_tokens": occ}},
    }


def test_lone_compact_summary_classifies_as_auto() -> None:
    """An ``isCompactSummary`` marker with no adjacent ``/compact`` command is an
    auto-compaction — the harness compacted at the ceiling on its own."""
    raw = [
        _assistant(180_000),
        {
            "type": "user",
            "isCompactSummary": True,
            "timestamp": "2026-01-01T00:01:00Z",
            "message": {"content": "summary"},
        },
        _assistant(30_000),
    ]
    events, _peak = _detect_context_events(raw, 200_000)
    assert [e.kind for e in events] == [CommandResetKind.AUTO]


def test_adjacent_compact_command_downgrades_summary_to_manual() -> None:
    """A manual ``/compact`` emits a command envelope AND a summary; the pair
    folds to a single COMPACT (the explicit command wins over the auto inference)."""
    raw = [
        _assistant(180_000),
        {
            "type": "user",
            "timestamp": "2026-01-01T00:01:00Z",
            "message": {"content": "<command-name>/compact</command-name>"},
        },
        {
            "type": "user",
            "isCompactSummary": True,
            "timestamp": "2026-01-01T00:01:20Z",
            "message": {"content": "summary"},
        },
        _assistant(30_000),
    ]
    events, _peak = _detect_context_events(raw, 200_000)
    assert [e.kind for e in events] == [CommandResetKind.COMPACT]


def test_fixture_auto_compaction_classified() -> None:
    """The compact_session.jsonl fixture (a lone summary) reports an auto reset
    end-to-end through ``build_receipt_contract``."""
    payload = build_receipt_contract(str(_FIXTURES / "compact_session.jsonl"))
    assert "auto" in [e["cmd"] for e in payload["context"]["events"]]
