"""Coverage for the v0.3.4 ``hyperweave doctor`` diagnostic command.

Doctor is read-only — it never modifies any config. Assertions probe
the rendered stdout against fixture filesystem state set up under
``tmp_path``. ``Path.home`` and ``shutil.which`` are stubbed so the
command never touches real ``~/.claude`` / ``~/.codex`` directories.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from typer.testing import CliRunner

from hyperweave.cli import app

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def _patch_home(monkeypatch: MonkeyPatch, home: Path) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))


def _patch_which(monkeypatch: MonkeyPatch, binaries: dict[str, str | None]) -> None:
    def _which(name: str, *_: Any, **__: Any) -> str | None:
        return binaries.get(name)

    monkeypatch.setattr(shutil, "which", _which)


def _write_claude_settings_with_hook(home: Path, command: str) -> None:
    settings_dir = home / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings = {"hooks": {"SessionEnd": [{"hooks": [{"type": "command", "command": command, "timeout": 10}]}]}}
    (settings_dir / "settings.json").write_text(json.dumps(settings, indent=2))


def _write_codex_hook(
    home: Path,
    command: str,
    *,
    with_feature_flag: bool = True,
) -> None:
    codex_dir = home / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    hooks = {"Stop": [{"type": "command", "command": command, "timeout": 10}]}
    (codex_dir / "hooks.json").write_text(json.dumps(hooks, indent=2))
    config_lines = ["[features]", "codex_hooks = true"] if with_feature_flag else ["[other]", "key = 1"]
    (codex_dir / "config.toml").write_text("\n".join(config_lines) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Doctor — runtime detection states
# ─────────────────────────────────────────────────────────────────────────────


def test_doctor_neither_runtime_detected(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "✗ claude-code: not detected" in result.stdout
    assert "✗ codex: not detected" in result.stdout


def test_doctor_codex_initialized_with_hook_and_feature_flag(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    _write_codex_hook(tmp_path, "hyperweave session receipt --genome telemetry-voltage")
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "✓ codex: hook registered" in result.stdout
    assert "hyperweave session receipt --genome telemetry-voltage" in result.stdout


def test_doctor_codex_initialized_but_no_hook(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """The user's actual bug scenario: ~/.codex exists but no hyperweave hook."""
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    (tmp_path / ".codex").mkdir()

    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "✗ codex: initialized but no hyperweave hook" in result.stdout
    assert "hyperweave install-hook --runtime codex" in result.stdout


def test_doctor_codex_hook_registered_but_feature_flag_missing(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Codex Stop hook only fires when [features] codex_hooks = true is set."""
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    _write_codex_hook(tmp_path, "hyperweave session receipt", with_feature_flag=False)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "⚠ codex" in result.stdout
    assert "codex_hooks" in result.stdout


def test_doctor_codex_binary_only_state(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Fresh Codex install: CLI is on PATH but ~/.codex/ hasn't been created."""
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": "/usr/local/bin/codex"})
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "⚠ codex: CLI on PATH at /usr/local/bin/codex" in result.stdout
    assert "not initialized" in result.stdout


def test_doctor_both_runtimes_initialized_with_hooks(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    _write_claude_settings_with_hook(tmp_path, "hyperweave session receipt")
    _write_codex_hook(tmp_path, "hyperweave session receipt")
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "✓ claude-code: hook registered" in result.stdout
    assert "✓ codex: hook registered" in result.stdout


# ─────────────────────────────────────────────────────────────────────────────
# Doctor — transcripts + receipts sections
# ─────────────────────────────────────────────────────────────────────────────


def test_doctor_reports_transcript_counts_when_present(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})

    codex_sessions = tmp_path / ".codex" / "sessions" / "2026" / "05"
    codex_sessions.mkdir(parents=True)
    (codex_sessions / "rollout-a.jsonl").write_text("{}\n")
    (codex_sessions / "rollout-b.jsonl").write_text("{}\n")

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "codex: 2 transcript(s)" in result.stdout


def test_doctor_reports_receipt_count_when_directory_exists(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})

    receipts_dir = tmp_path / ".hyperweave" / "receipts"
    receipts_dir.mkdir(parents=True)
    (receipts_dir / "20260513_test_one.svg").write_text("<svg/>")
    (receipts_dir / "20260513_test_two.svg").write_text("<svg/>")

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "2 receipt(s) in last 7 days, 2 total" in result.stdout
    # One of the two filenames surfaces as the most-recent line.
    assert "most recent: 20260513_test_" in result.stdout


def test_doctor_reports_no_receipts_directory(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "no receipts directory in cwd" in result.stdout


def test_doctor_always_exits_zero(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Doctor is purely diagnostic — broken state must not exit non-zero."""
    _patch_home(monkeypatch, tmp_path)
    _patch_which(monkeypatch, {"claude": None, "codex": None})

    # Malformed claude settings.json + codex hooks.json should not crash.
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("not json")
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "hooks.json").write_text("not json")

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    # Both runtimes report the malformed state via ⚠ markers, not crashes.
    assert "malformed" in result.stdout
