"""Cross-runtime dispatch correctness for ``contract.parse_transcript_auto``.

These tests assert the v0.2.23 dispatcher routes each transcript shape
to its matching parser without false-positive cross-routing. A Claude
Code transcript should NEVER sniff as Codex (and vice versa); the
detection rules in ``data/telemetry/runtimes/*.yaml`` are mutually
exclusive by construction, but tests guard the invariant.
"""

from __future__ import annotations

from hyperweave.telemetry.contract import build_contract, parse_transcript_auto

CLAUDE_FIXTURE = "tests/fixtures/session.jsonl"
CODEX_FIXTURE = "tests/fixtures/codex_session.jsonl"
CODEX_PATCHES_FIXTURE = "tests/fixtures/codex_session_patches.jsonl"


def test_claude_fixture_routes_to_claude_parser() -> None:
    """Claude Code JSONL → claude-code parser → SessionTelemetry.runtime='claude-code'."""
    t = parse_transcript_auto(CLAUDE_FIXTURE)
    assert t.runtime == "claude-code"


def test_codex_fixture_routes_to_codex_parser() -> None:
    """Codex envelope JSONL → codex parser → SessionTelemetry.runtime='codex'."""
    t = parse_transcript_auto(CODEX_FIXTURE)
    assert t.runtime == "codex"


def test_codex_patches_fixture_routes_to_codex_parser() -> None:
    """Patches fixture also routes correctly; second fixture cross-checks first."""
    t = parse_transcript_auto(CODEX_PATCHES_FIXTURE)
    assert t.runtime == "codex"


def test_build_contract_stamps_runtime_in_session_dict() -> None:
    """The resolver reads session.runtime; ``build_contract`` must propagate it."""
    claude = build_contract(CLAUDE_FIXTURE)
    codex = build_contract(CODEX_FIXTURE)
    assert claude["session"]["runtime"] == "claude-code"
    assert codex["session"]["runtime"] == "codex"


def test_dispatchers_extract_distinct_tools_per_runtime() -> None:
    """Sanity: parsers extract their respective tool sets, not the wrong runtime's."""
    claude = build_contract(CLAUDE_FIXTURE)
    codex = build_contract(CODEX_FIXTURE)
    # Claude fixture should have at least one Claude tool name
    claude_tools = set(claude["tools"])
    assert claude_tools & {"Read", "Bash", "Edit", "Write", "Glob", "Grep"}, (
        f"claude fixture missing canonical Claude tools: {claude_tools}"
    )
    # Codex fixture should have codex tool names, not Claude tool names
    codex_tools = set(codex["tools"])
    assert codex_tools & {"exec_command", "write_stdin", "web_search", "apply_patch"}, (
        f"codex fixture missing canonical codex tools: {codex_tools}"
    )
    assert not (codex_tools & {"Read", "Bash", "Edit"}), f"codex fixture leaked Claude tool names: {codex_tools}"
