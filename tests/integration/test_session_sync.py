"""Integration tests for ``hyperweave session sync``.

The sync path is intentionally file-system oriented: it scans an agent
runtime's transcript directory and materializes missing or stale receipt
SVGs into the current project's ``.hyperweave/receipts`` directory.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from hyperweave.cli import app
from tests.conftest import FIXTURES_DIR


def _patch_home(monkeypatch, home: Path) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))


def _copy_antigravity_fixture(home: Path) -> Path:
    brain = home / ".gemini" / "antigravity" / "brain" / "workspace"
    brain.mkdir(parents=True)
    transcript = brain / "session.jsonl"
    transcript.write_text((FIXTURES_DIR / "antigravity_session.jsonl").read_text())
    return transcript


def test_session_sync_antigravity_renders_missing_receipt(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    _copy_antigravity_fixture(home)
    _patch_home(monkeypatch, home)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["session", "sync", "--runtime", "antigravity"])

    assert result.exit_code == 0
    assert "Synced antigravity receipts: 1 rendered, 0 up-to-date, 0 failed" in result.stdout
    receipts = list((tmp_path / ".hyperweave" / "receipts").glob("*.svg"))
    assert len(receipts) == 1
    svg = receipts[0].read_text()
    assert 'data-hw-glyph="antigravity-glyph"' in svg


def test_session_sync_antigravity_skips_up_to_date_receipt(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    _copy_antigravity_fixture(home)
    _patch_home(monkeypatch, home)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    first = runner.invoke(app, ["session", "sync", "--runtime", "antigravity"])
    second = runner.invoke(app, ["session", "sync", "--runtime", "antigravity"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Synced antigravity receipts: 0 rendered, 1 up-to-date, 0 failed" in second.stdout
    assert len(list((tmp_path / ".hyperweave" / "receipts").glob("*.svg"))) == 1


def test_session_sync_rejects_unsupported_runtime() -> None:
    result = CliRunner().invoke(app, ["session", "sync", "--runtime", "codex"])

    assert result.exit_code == 1
    assert "session sync currently supports: antigravity" in result.stderr
