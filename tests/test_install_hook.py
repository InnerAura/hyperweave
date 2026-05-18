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
    stop_groups = hooks["hooks"]["Stop"]
    inner_handlers = [handler for group in stop_groups for handler in group.get("hooks", [])]
    assert any(
        "hyperweave session receipt --genome telemetry-voltage" in str(handler.get("command", ""))
        for handler in inner_handlers
    ), f"expected genome-pinned command under wrapper.Stop, got {stop_groups!r}"
    assert not (tmp_path / ".claude").exists()


def test_install_hook_codex_strips_legacy_codex_hooks_feature_flag(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Codex v0.130.0 renamed the feature gate from ``codex_hooks`` to ``hooks``.

    Re-running install-hook over a config that still carries the legacy key
    must strip it and write the new ``hooks = true`` in its place, while
    preserving any unrelated sections so user trust_level / model settings
    survive the upgrade.
    """
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(
        'model = "gpt-5.5"\n\n[projects."/repo"]\ntrust_level = "trusted"\n\n[features]\ncodex_hooks = true\n'
    )

    runner = CliRunner()
    result = runner.invoke(app, ["install-hook", "--runtime", "codex"])
    assert result.exit_code == 0

    config_text = (codex_dir / "config.toml").read_text()
    assert "codex_hooks" not in config_text, f"legacy codex_hooks key was not stripped:\n{config_text}"
    assert "hooks = true" in config_text, f"new hooks gate was not written:\n{config_text}"
    assert 'model = "gpt-5.5"' in config_text, "unrelated top-level key was dropped"
    assert '[projects."/repo"]' in config_text, "unrelated section was dropped"


def test_install_hook_codex_lifts_legacy_flat_hooks_json(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Codex v0.129.0 (hooks GA) changed hooks.json from flat to wrapped+matcher.

    Re-running install-hook over a pre-GA flat config must:
    1. Lift every legacy top-level event key under the new ``hooks`` wrapper.
    2. Wrap each bare-command entry in a ``{matcher: "*", hooks: [...]}`` group.
    3. Preserve unrelated hook commands (other tools' entries must survive).
    4. Produce exactly one hyperweave entry.
    5. Be idempotent — a second run does not double-wrap or stack entries.
    """
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    # Pre-GA flat shape: bare-command entries directly under top-level event keys,
    # plus an unrelated PreToolUse hook that must survive the migration.
    flat_hooks = {
        "Stop": [
            {
                "type": "command",
                "command": "hyperweave session receipt --genome telemetry-codex",
                "timeout": 10,
            },
            {"type": "command", "command": "/usr/local/bin/some-other-hook", "timeout": 30},
        ],
        "PreToolUse": [
            {"type": "command", "command": "/usr/local/bin/preuse-hook", "timeout": 5},
        ],
    }
    (codex_dir / "hooks.json").write_text(json.dumps(flat_hooks, indent=2))

    runner = CliRunner()
    result = runner.invoke(app, ["install-hook", "--runtime", "codex"])
    assert result.exit_code == 0

    out = json.loads((codex_dir / "hooks.json").read_text())
    # No legacy top-level event keys remain.
    assert "Stop" not in out, f"legacy flat Stop key still at top level: {out!r}"
    assert "PreToolUse" not in out, f"legacy flat PreToolUse key still at top level: {out!r}"
    # GA wrapper exists and is a dict.
    assert isinstance(out.get("hooks"), dict), f"GA wrapper missing or wrong shape: {out!r}"
    wrapper = out["hooks"]
    assert "Stop" in wrapper, f"Stop not lifted under wrapper: {wrapper!r}"
    assert "PreToolUse" in wrapper, f"PreToolUse not lifted under wrapper: {wrapper!r}"
    # Each lifted entry is in {matcher, hooks: [...]} shape.
    for event_name, groups in wrapper.items():
        for group in groups:
            assert "matcher" in group, f"{event_name} lifted entry missing matcher: {group!r}"
            assert isinstance(group.get("hooks"), list), (
                f"{event_name} lifted entry missing inner hooks list: {group!r}"
            )
    # The unrelated commands survive the migration.
    all_commands = [
        h.get("command", "") for groups in wrapper.values() for group in groups for h in group.get("hooks", [])
    ]
    assert any("some-other-hook" in c for c in all_commands), f"unrelated Stop hook was dropped: {all_commands!r}"
    assert any("preuse-hook" in c for c in all_commands), f"unrelated PreToolUse hook was dropped: {all_commands!r}"
    # Exactly one hyperweave entry under wrapper.Stop.
    hyperweave_handlers = [
        h
        for group in wrapper["Stop"]
        for h in group.get("hooks", [])
        if "hyperweave session" in str(h.get("command", ""))
    ]
    assert len(hyperweave_handlers) == 1, (
        f"expected exactly one hyperweave handler post-migration, got {hyperweave_handlers!r}"
    )

    # Re-run is idempotent — no double-wrapping, no stacking.
    result2 = runner.invoke(app, ["install-hook", "--runtime", "codex"])
    assert result2.exit_code == 0
    out2 = json.loads((codex_dir / "hooks.json").read_text())
    hyperweave_handlers2 = [
        h
        for group in out2["hooks"]["Stop"]
        for h in group.get("hooks", [])
        if "hyperweave session" in str(h.get("command", ""))
    ]
    assert len(hyperweave_handlers2) == 1, f"re-run stacked or double-wrapped: {hyperweave_handlers2!r}"


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
    stop_groups = codex_hooks["hooks"]["Stop"]
    hyperweave_handlers = [
        handler
        for group in stop_groups
        for handler in group.get("hooks", [])
        if "hyperweave session" in str(handler.get("command", ""))
    ]
    assert len(hyperweave_handlers) == 1, (
        f"expected exactly one hyperweave Stop hook after two invocations, got {hyperweave_handlers!r}"
    )


def test_install_hook_unknown_runtime_exits_one(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})

    runner = CliRunner()
    result = runner.invoke(app, ["install-hook", "--runtime", "bogus"])
    assert result.exit_code == 1
    assert "unknown runtime 'bogus'" in result.stderr
