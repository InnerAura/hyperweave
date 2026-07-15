"""CLI compose delivery — --format projection + stdout/file/blit routing.

The delivery contract: a file always gets raw bytes; stdout gets text for
svg/svg-static, and for png/webp either a kitty blit (interactive + capable
terminal), a redirect hint (interactive + non-capable — never binary at a TTY),
or raw bytes (piped). Tests drive ``_deliver_projection`` directly with a fake
stdout so no real terminal is needed, plus a CLI end-to-end for the file path.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
import typer
from typer.testing import CliRunner

from hyperweave import cli
from hyperweave.cli import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


class _FakeStdout:
    """Stand-in for sys.stdout with a controllable isatty() and a byte buffer."""

    def __init__(self, *, tty: bool) -> None:
        self._tty = tty
        self.buffer = io.BytesIO()
        self.text = io.StringIO()

    def isatty(self) -> bool:
        return self._tty

    def write(self, s: str) -> int:
        return self.text.write(s)


def _drive_delivery(
    monkeypatch: pytest.MonkeyPatch, data: bytes, *, is_text: bool, tty: bool, capable: bool
) -> _FakeStdout:
    fake = _FakeStdout(tty=tty)
    monkeypatch.setattr(cli.sys, "stdout", fake)
    monkeypatch.setattr("hyperweave.delivery.kitty.terminal_supports_graphics", lambda env=None: capable)
    cli._deliver_projection(data, is_text=is_text, output=None, width=10, height=10)
    return fake


def test_svg_text_to_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _drive_delivery(monkeypatch, b"<svg/>", is_text=True, tty=True, capable=False)
    assert fake.text.getvalue() == "<svg/>"


def test_raster_piped_is_raw_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """not-a-tty (piped/redirected) always streams raw bytes — the ls/git rule."""
    fake = _drive_delivery(monkeypatch, b"\x89PNG", is_text=False, tty=False, capable=True)
    assert fake.buffer.getvalue() == b"\x89PNG"


def test_raster_tty_capable_blits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Interactive + graphics-capable terminal → a kitty APC blit, not raw bytes."""
    fake = _drive_delivery(monkeypatch, b"\x89PNG\r\n\x1a\n", is_text=False, tty=True, capable=True)
    out = fake.buffer.getvalue()
    assert out.startswith(b"\x1b_G")


def test_raster_tty_non_capable_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Interactive but non-capable terminal → a stderr hint + exit, never binary."""
    fake = _FakeStdout(tty=True)
    monkeypatch.setattr(cli.sys, "stdout", fake)
    monkeypatch.setattr("hyperweave.delivery.kitty.terminal_supports_graphics", lambda env=None: False)
    with pytest.raises(typer.Exit):
        cli._deliver_projection(b"\x89PNG", is_text=False, output=None, width=10, height=10)
    assert fake.buffer.getvalue() == b""  # nothing binary hit the TTY


def test_compose_png_to_file(tmp_path: Path) -> None:
    """End-to-end: --format png -o writes a real PNG file (needs the raster extra)."""
    from hyperweave.formats import raster_available

    if not raster_available():
        pytest.skip("raster extra not installed")
    out = tmp_path / "b.png"
    result = runner.invoke(
        app,
        [
            "compose",
            "badge",
            "STARS",
            "1234",
            "-g",
            "primer",
            "--variant",
            "porcelain",
            "--format",
            "png",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
