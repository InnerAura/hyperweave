"""Tests for the v0.2.21 multi-skin telemetry resolution chain.

Phase D removed the ``_TELEMETRY_FRAMES`` force-to-``telemetry-void`` block and
replaced it with :func:`hyperweave.compose.resolver._resolve_telemetry_genome`,
a precedence chain that reads (in order):

1. ``spec.genome_id`` (when the genome declares ``paradigms.receipt``)
2. ``telemetry_data["session"]["runtime"]`` (auto-detect, Phase C contract patch)
3. ``"telemetry-voltage"`` (explicit fallback)

The empty-string fallback for runtime is deliberate. Pre-Phase-C JSONL has no
``runtime`` field; those sessions route to voltage rather than auto-classifying
as claude-code. Explicit signal → specific skin; absent signal → fallback.

Removing ``_TELEMETRY_FRAMES`` also routes rhythm-strip through the same
precedence chain — the chromatic skin propagates so a session captured under
Claude Code renders both its receipt and its rhythm-strip in the same warm
cream palette.
"""

from __future__ import annotations

from typing import Any

from hyperweave.cli import _normalize_genome_slug
from hyperweave.compose.resolver import (
    _genome_supports_receipts,
    _resolve_telemetry_genome,
)
from hyperweave.core.models import ComposeSpec

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _spec(frame_type: str, genome_id: str = "", telemetry_data: dict[str, Any] | None = None) -> ComposeSpec:
    """Build a minimal ComposeSpec for resolution testing."""
    return ComposeSpec(
        type=frame_type,
        genome_id=genome_id,
        telemetry_data=telemetry_data,
    )


def _tel(runtime: str | None = None) -> dict[str, Any]:
    """Build a minimal telemetry_data dict; pass ``runtime=None`` to omit the session.runtime key."""
    if runtime is None:
        return {"session": {}}
    return {"session": {"runtime": runtime}}


# --------------------------------------------------------------------------- #
# Precedence chain                                                            #
# --------------------------------------------------------------------------- #


def test_explicit_genome_override_wins_over_runtime() -> None:
    """A user-pinned --genome that supports receipts beats the JSONL runtime field."""
    spec = _spec("receipt", genome_id="telemetry-cream")
    assert _resolve_telemetry_genome(spec, _tel("claude-code")) == "telemetry-cream"


def test_runtime_claude_code_auto_detects_skin() -> None:
    """No --genome flag + runtime=claude-code → auto-pick telemetry-claude-code."""
    spec = _spec("receipt")
    assert _resolve_telemetry_genome(spec, _tel("claude-code")) == "telemetry-claude-code"


def test_unknown_runtime_falls_back_to_voltage() -> None:
    """Codex / opencode / unknown runtimes fall through to telemetry-voltage in v0.2.21."""
    spec = _spec("receipt")
    for unknown in ("codex", "opencode", "gemini", "unknown-runtime"):
        assert _resolve_telemetry_genome(spec, _tel(unknown)) == "telemetry-voltage"


def test_pre_patch_jsonl_no_runtime_field_routes_to_voltage() -> None:
    """Pre-Phase-C JSONL has no session.runtime — must fall back to voltage, not claude-code."""
    spec = _spec("receipt")
    # Empty runtime ("" after the `or ""` fallback) → voltage.
    assert _resolve_telemetry_genome(spec, _tel("")) == "telemetry-voltage"
    # Missing runtime key entirely → voltage.
    assert _resolve_telemetry_genome(spec, _tel(None)) == "telemetry-voltage"
    # Empty telemetry_data with no session → voltage.
    assert _resolve_telemetry_genome(spec, {}) == "telemetry-voltage"


def test_unsupported_genome_falls_through_to_runtime() -> None:
    """Pinning a non-receipt genome (e.g. brutalist) silently falls through to runtime detection.

    The receipt CLI is forgiving here — fail-loud validation lives in the install-hook
    CLI, which catches the bad pin BEFORE the hook is written. Compose() must not crash
    on a stale --genome flag mid-session.
    """
    spec = _spec("receipt", genome_id="brutalist")
    assert _resolve_telemetry_genome(spec, _tel("claude-code")) == "telemetry-claude-code"
    assert _resolve_telemetry_genome(spec, _tel("")) == "telemetry-voltage"


# --------------------------------------------------------------------------- #
# _genome_supports_receipts                                                   #
# --------------------------------------------------------------------------- #


def test_genome_supports_receipts_for_telemetry_skins() -> None:
    """All 3 telemetry skins declare paradigms.receipt → True."""
    assert _genome_supports_receipts("telemetry-voltage") is True
    assert _genome_supports_receipts("telemetry-claude-code") is True
    assert _genome_supports_receipts("telemetry-cream") is True


def test_genome_supports_receipts_returns_false_for_brutalist() -> None:
    """brutalist genome doesn't declare paradigms.receipt — must return False."""
    assert _genome_supports_receipts("brutalist") is False
    assert _genome_supports_receipts("chrome") is False
    assert _genome_supports_receipts("automata") is False


def test_genome_supports_receipts_returns_false_for_unknown_genome() -> None:
    """Unknown slug raises GenomeNotFoundError internally; helper returns False, not raises."""
    assert _genome_supports_receipts("xyzbogus") is False
    assert _genome_supports_receipts("") is False


# --------------------------------------------------------------------------- #
# Rhythm-strip propagation (the load-bearing Phase D side effect)             #
# --------------------------------------------------------------------------- #


def test_rhythm_strip_propagates_skin_from_runtime() -> None:
    """Rhythm-strip ALSO routes through _resolve_telemetry_genome.

    Before Phase D, _TELEMETRY_FRAMES forced rhythm-strip to telemetry-void
    regardless of session runtime. After Phase D, it picks up the same skin
    as the session's receipt — claude-code session → warm cream rhythm-strip,
    not dark fallback.
    """
    spec = _spec("rhythm-strip")
    assert _resolve_telemetry_genome(spec, _tel("claude-code")) == "telemetry-claude-code"


def test_rhythm_strip_honors_explicit_genome_pin() -> None:
    """Pinning --genome on rhythm-strip works the same as on receipt."""
    spec = _spec("rhythm-strip", genome_id="telemetry-cream")
    assert _resolve_telemetry_genome(spec, _tel("claude-code")) == "telemetry-cream"


def test_master_card_propagates_skin_from_runtime() -> None:
    """Master-card flows through the same precedence chain as receipt + rhythm-strip."""
    spec = _spec("master-card")
    assert _resolve_telemetry_genome(spec, _tel("claude-code")) == "telemetry-claude-code"
    assert _resolve_telemetry_genome(spec, _tel("")) == "telemetry-voltage"


# --------------------------------------------------------------------------- #
# CLI slug normalization (install-hook + session ergonomics)                  #
# --------------------------------------------------------------------------- #


def test_short_form_genome_slug_expands_to_telemetry_prefix() -> None:
    """``cream`` → ``telemetry-cream``; same for the other 2 v0.2.21 skins."""
    assert _normalize_genome_slug("cream") == "telemetry-cream"
    assert _normalize_genome_slug("voltage") == "telemetry-voltage"
    assert _normalize_genome_slug("claude-code") == "telemetry-claude-code"


def test_full_slug_passes_through_unchanged() -> None:
    """Already-prefixed slugs are returned verbatim."""
    assert _normalize_genome_slug("telemetry-cream") == "telemetry-cream"
    assert _normalize_genome_slug("telemetry-voltage") == "telemetry-voltage"


def test_non_telemetry_slug_passes_through_unchanged() -> None:
    """Non-telemetry slugs (brutalist, chrome, automata) skip the prefix expansion.

    Forward-compat with v0.2.22's ``brutalist`` receipt support: when brutalist
    starts declaring paradigms.receipt, the install-hook validation will accept
    it. The slug normalizer mustn't auto-prefix it to ``telemetry-brutalist``
    (which doesn't exist).
    """
    assert _normalize_genome_slug("brutalist") == "brutalist"
    assert _normalize_genome_slug("chrome") == "chrome"
    assert _normalize_genome_slug("automata") == "automata"


def test_empty_slug_returns_empty() -> None:
    """Empty input returns empty (caller's responsibility to interpret as auto-detect)."""
    assert _normalize_genome_slug("") == ""
