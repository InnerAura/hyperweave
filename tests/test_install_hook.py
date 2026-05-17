"""Coverage for the v0.3.4 install-hook auto-detect path.

`hyperweave install-hook` resolves a target runtime list via three modes:

* ``--runtime ""`` (default) — calls ``_detect_installed_runtimes`` and
  registers for every detected runtime; empty detection → exit 1.
* ``--runtime all`` — both runtimes regardless of detection state.
* ``--runtime <name>`` — single runtime (legacy explicit form).

Detection uses a dual signal: config dir under ``$HOME`` OR CLI binary
on PATH. ``Path.home`` and ``shutil.which`` are both monkeypatched so
the tests never touch the real ``~/.claude`` / ``~/.codex`` directories.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from typer.testing import CliRunner

from hyperweave.cli import _detect_installed_runtimes, app

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def _patch_home(monkeypatch: MonkeyPatch, home: Path) -> None:
    """Redirect ``Path.home`` so installer + detection writes go to ``home``."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))


def _patch_which(monkeypatch: MonkeyPatch, binaries: dict[str, str | None]) -> None:
    """Stub ``shutil.which`` to return mapped paths (or ``None``) by binary name."""

    def _which(name: str, *_: Any, **__: Any) -> str | None:
        return binaries.get(name)

    monkeypatch.setattr(shutil, "which", _which)


# ─────────────────────────────────────────────────────────────────────────────
# _detect_installed_runtimes — pure detection logic
# ─────────────────────────────────────────────────────────────────────────────


def test_detect_returns_empty_when_neither_dir_nor_binary_present(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    assert _detect_installed_runtimes() == []


def test_detect_claude_dir_only(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    (tmp_path / ".claude").mkdir()
    assert _detect_installed_runtimes() == [("claude-code", "initialized")]


def test_detect_codex_dir_only(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    (tmp_path / ".codex").mkdir()
    assert _detect_installed_runtimes() == [("codex", "initialized")]


def test_detect_both_dirs_present(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".codex").mkdir()
    assert _detect_installed_runtimes() == [
        ("claude-code", "initialized"),
        ("codex", "initialized"),
    ]


def test_detect_codex_binary_only(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Fresh Codex install: CLI is on PATH but ~/.codex/ hasn't been created."""
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": "/usr/local/bin/codex"})
    assert _detect_installed_runtimes() == [("codex", "binary_only")]


def test_detect_claude_binary_only(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": "/opt/homebrew/bin/claude", "codex": None})
    assert _detect_installed_runtimes() == [("claude-code", "binary_only")]


def test_detect_dir_takes_precedence_over_binary(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """When both signals fire, ``initialized`` wins — the dir is the stronger evidence."""
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": "/opt/homebrew/bin/claude", "codex": None})
    (tmp_path / ".claude").mkdir()
    assert _detect_installed_runtimes() == [("claude-code", "initialized")]


# ─────────────────────────────────────────────────────────────────────────────
# install_hook Typer command — wiring + idempotency
# ─────────────────────────────────────────────────────────────────────────────


def test_install_hook_no_runtime_no_detection_exits_one(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    runner = CliRunner()
    result = runner.invoke(app, ["install-hook"])
    assert result.exit_code == 1
    assert "no agent runtime detected" in result.stderr


def test_install_hook_auto_detect_only_claude(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    (tmp_path / ".claude").mkdir()

    runner = CliRunner()
    result = runner.invoke(app, ["install-hook"])
    assert result.exit_code == 0
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert not (tmp_path / ".codex").exists()


def test_install_hook_auto_detect_only_codex(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    (tmp_path / ".codex").mkdir()

    runner = CliRunner()
    result = runner.invoke(app, ["install-hook"])
    assert result.exit_code == 0
    assert (tmp_path / ".codex" / "hooks.json").exists()
    assert (tmp_path / ".codex" / "config.toml").exists()
    assert not (tmp_path / ".claude").exists()


def test_install_hook_auto_detect_both_runtimes(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".codex").mkdir()

    runner = CliRunner()
    result = runner.invoke(app, ["install-hook"])
    assert result.exit_code == 0
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / ".codex" / "hooks.json").exists()


def test_install_hook_auto_detect_codex_binary_only_creates_dir(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Binary-only detection still installs — the codex installer creates ~/.codex."""
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": "/usr/local/bin/codex"})

    runner = CliRunner()
    result = runner.invoke(app, ["install-hook"])
    assert result.exit_code == 0
    assert (tmp_path / ".codex").is_dir()
    assert (tmp_path / ".codex" / "hooks.json").exists()
    assert (tmp_path / ".codex" / "config.toml").exists()


def test_install_hook_runtime_all_forces_both(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """``--runtime all`` registers for both runtimes even when neither is detected."""
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})

    runner = CliRunner()
    result = runner.invoke(app, ["install-hook", "--runtime", "all"])
    assert result.exit_code == 0
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / ".codex" / "hooks.json").exists()


def test_install_hook_runtime_codex_with_genome_pins_command(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Explicit ``--runtime codex --genome telemetry-voltage`` pins the genome
    into the registered hook command and leaves claude-code untouched.
    """
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})

    runner = CliRunner()
    result = runner.invoke(app, ["install-hook", "--runtime", "codex", "--genome", "telemetry-voltage"])
    assert result.exit_code == 0
    hooks = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    stop_entries = hooks["Stop"]
    assert any(
        "hyperweave session receipt --genome telemetry-voltage" in str(entry.get("command", ""))
        for entry in stop_entries
    ), f"expected genome-pinned command in Stop hooks, got {stop_entries!r}"
    assert not (tmp_path / ".claude").exists()


def test_install_hook_is_idempotent(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Running install-hook twice replaces — never stacks — the hyperweave entry."""
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".codex").mkdir()

    runner = CliRunner()
    runner.invoke(app, ["install-hook", "--runtime", "all"])
    runner.invoke(app, ["install-hook", "--runtime", "all"])  # second invocation

    claude_settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    session_end_hyperweave = [
        h
        for entry in claude_settings["hooks"]["SessionEnd"]
        for h in entry.get("hooks", [])
        if "hyperweave session" in str(h.get("command", ""))
    ]
    assert len(session_end_hyperweave) == 1, (
        f"expected exactly one hyperweave SessionEnd hook after two invocations, got {session_end_hyperweave!r}"
    )

    codex_hooks = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    stop_hyperweave = [entry for entry in codex_hooks["Stop"] if "hyperweave session" in str(entry.get("command", ""))]
    assert len(stop_hyperweave) == 1, (
        f"expected exactly one hyperweave Stop hook after two invocations, got {stop_hyperweave!r}"
    )


def test_install_hook_unknown_runtime_exits_one(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})

    runner = CliRunner()
    result = runner.invoke(app, ["install-hook", "--runtime", "bogus"])
    assert result.exit_code == 1
    assert "unknown runtime 'bogus'" in result.stderr
