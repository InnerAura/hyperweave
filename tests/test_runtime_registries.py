"""Validation tests for the v0.2.23 per-runtime tool registry architecture.

The registry system replaced the empirical ``data/telemetry/tool-classes.yaml``
+ the divergent ``_TOOL_CLASS`` shadow at ``compose/resolver.py:1624`` with
``data/telemetry/runtimes/{runtime}.yaml`` files dispatched through
``telemetry.runtimes``. These tests assert structural invariants that
prevent the same drift from re-emerging:

* Every YAML loads cleanly.
* Every ``tools.*`` value is a valid ``ToolClass``.
* Every runtime's ``parser_module`` actually resolves.
* Every runtime's ``genome`` is a real file in ``data/genomes/``.
* Detection rules across runtimes are mutually exclusive — a Claude line
  can't sniff as Codex and vice versa.
* Unknown-tool policy emits a warning when triggered (not silent).
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

import pytest

from hyperweave.telemetry.models import ToolClass
from hyperweave.telemetry.runtimes import (
    RuntimeRegistry,
    classify_tool,
    detect_runtime,
    load_all_runtimes,
)

_GENOMES_DIR = Path(__file__).resolve().parent.parent / "src" / "hyperweave" / "data" / "genomes"


# --------------------------------------------------------------------------- #
# Loading + structure                                                         #
# --------------------------------------------------------------------------- #


def test_all_registered_runtimes_load() -> None:
    """Both v0.2.23-shipped runtimes are present and instantiable."""
    runtimes = load_all_runtimes()
    assert {"claude-code", "codex"} <= set(runtimes), f"expected claude-code and codex; got {sorted(runtimes)}"


def test_every_registry_has_complete_metadata() -> None:
    """Every loaded registry exposes the full RuntimeRegistry contract."""
    for name, reg in load_all_runtimes().items():
        assert isinstance(reg, RuntimeRegistry), name
        assert reg.runtime == name
        assert reg.parser_module, f"{name}: parser_module empty"
        assert reg.genome, f"{name}: genome empty"
        assert reg.glyph, f"{name}: glyph empty"
        assert reg.provider_label, f"{name}: provider_label empty"
        assert reg.detection.shape in ("flat", "envelope"), name
        assert reg.detection.required_keys, f"{name}: required_keys empty"
        assert reg.detection.type_values, f"{name}: type_values empty"
        assert reg.tools, f"{name}: tools empty"
        assert reg.unknown_tool_policy in ("warn", "error"), name


def test_every_tools_value_is_a_valid_toolclass() -> None:
    """No registry can declare a tool with an invalid class string."""
    for name, reg in load_all_runtimes().items():
        for tool, cls in reg.tools.items():
            assert isinstance(cls, ToolClass), f"{name}.{tool}: {cls!r}"


def test_every_pattern_class_is_a_valid_toolclass() -> None:
    """Pattern-fallback classes must also be valid ToolClass values."""
    for name, reg in load_all_runtimes().items():
        for pat in reg.patterns:
            assert isinstance(pat.tool_class, ToolClass), f"{name}: {pat.prefix} -> {pat.tool_class!r}"


# --------------------------------------------------------------------------- #
# Parser + genome resolution                                                  #
# --------------------------------------------------------------------------- #


def test_every_parser_module_imports() -> None:
    """Each runtime's ``parser`` field points to an importable module."""
    for name, reg in load_all_runtimes().items():
        # codex.yaml points at hyperweave.telemetry.codex_parser which is
        # added in Phase B; skip its import check there until B1 lands.
        if name == "codex" and not _module_exists(reg.parser_module):
            pytest.skip(f"{reg.parser_module} added in v0.2.23 Phase B (B1)")
        importlib.import_module(reg.parser_module)


def test_every_genome_file_exists() -> None:
    """Each runtime's ``genome`` field references a real file in data/genomes/."""
    for name, reg in load_all_runtimes().items():
        # telemetry-codex.json is authored in v0.2.23 Phase B (B2); skip until then.
        if name == "codex" and not (_GENOMES_DIR / f"{reg.genome}.json").is_file():
            pytest.skip(f"{reg.genome}.json authored in v0.2.23 Phase B (B2)")
        path = _GENOMES_DIR / f"{reg.genome}.json"
        assert path.is_file(), f"{name}: {path} not found"


# --------------------------------------------------------------------------- #
# Detection rules                                                             #
# --------------------------------------------------------------------------- #


def test_claude_code_line_detects_as_claude_code() -> None:
    """A canonical Claude Code session line resolves to the claude-code registry."""
    line = {"sessionId": "abc-123", "type": "user", "message": {"role": "user"}}
    assert detect_runtime(line).runtime == "claude-code"


def test_codex_line_detects_as_codex() -> None:
    """A canonical Codex envelope line resolves to the codex registry."""
    line = {"timestamp": "2026-05-04T00:00:00Z", "type": "session_meta", "payload": {}}
    assert detect_runtime(line).runtime == "codex"


def test_detection_rules_are_mutually_exclusive() -> None:
    """A line valid under one registry must NOT match any other registry's rule.

    This is the architectural invariant that lets the dispatcher trust the
    first match — no need to disambiguate. Future runtimes added to
    ``data/telemetry/runtimes/`` must extend this guarantee or detection
    breaks for everyone.
    """
    runtimes = load_all_runtimes()
    canonical_lines = {
        "claude-code": {"sessionId": "x", "type": "user"},
        "codex": {"timestamp": "x", "type": "session_meta", "payload": {}},
    }
    for source_runtime, line in canonical_lines.items():
        for target_name, target_reg in runtimes.items():
            matched = target_reg.detection.matches(line)
            if target_name == source_runtime:
                assert matched, f"{source_runtime} line should match its own rule"
            else:
                assert not matched, f"{source_runtime} line accidentally matches {target_name} rule"


def test_no_match_raises() -> None:
    """A line that matches no registry raises ValueError loud."""
    with pytest.raises(ValueError, match="No runtime registry matches"):
        detect_runtime({"foo": "bar"})


# --------------------------------------------------------------------------- #
# Classification semantics                                                    #
# --------------------------------------------------------------------------- #


def test_exact_match_classification() -> None:
    """Tools listed in ``tools`` table classify by their declared ToolClass."""
    cc = load_all_runtimes()["claude-code"]
    assert classify_tool(cc, "Read") == ToolClass.EXPLORE
    assert classify_tool(cc, "Edit") == ToolClass.MUTATE
    assert classify_tool(cc, "Bash") == ToolClass.EXECUTE
    assert classify_tool(cc, "Task") == ToolClass.COORDINATE


def test_pattern_match_classification() -> None:
    """Tools matching a prefix pattern fall through to the pattern's class."""
    cc = load_all_runtimes()["claude-code"]
    # mcp__ → coordinate
    assert classify_tool(cc, "mcp__github__create_issue") == ToolClass.COORDINATE
    # Bash( → execute (parameterized Bash variants)
    assert classify_tool(cc, "Bash(git status)") == ToolClass.EXECUTE


def test_unknown_tool_warns_not_silent(caplog: pytest.LogCaptureFixture) -> None:
    """v0.2.23 invariant: unknown tools log a WARNING, not silent EXPLORE fallback.

    The pre-v0.2.23 ``TOOL_CLASS_MAP.get(name, ToolClass.EXPLORE)`` swallowed
    every unmapped tool with no audit trail. The new policy MUST surface the
    name + runtime so the YAML can be patched.
    """
    cc = load_all_runtimes()["claude-code"]
    with caplog.at_level(logging.WARNING):
        cls = classify_tool(cc, "TotallyMadeUpToolName")
    assert cls == ToolClass.EXPLORE  # graceful fallback
    assert any("unknown_tool" in r.message and "TotallyMadeUpToolName" in r.message for r in caplog.records), (
        f"expected unknown_tool warning, got: {[r.message for r in caplog.records]}"
    )


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _module_exists(dotted: str) -> bool:
    """True iff ``dotted`` can be imported without raising."""
    try:
        importlib.import_module(dotted)
    except ImportError:
        return False
    return True
