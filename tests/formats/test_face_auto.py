"""§12.3 --face auto — OSC 11 reply parsing (the detection's pure core).

The tty round-trip needs an interactive terminal; CI pins the parser and
the luminance split. ``detect_terminal_face`` refuses (never guesses) off
a tty — pinned via the non-tty error path.
"""

from __future__ import annotations

import pytest

from hyperweave.core.errors import HwError
from hyperweave.delivery.face_detect import detect_terminal_face, parse_osc11_reply


class TestOsc11Parsing:
    @pytest.mark.parametrize(
        ("reply", "want"),
        [
            (b"\x1b]11;rgb:0d0d/1117/1a1a\x07", "dark"),  # GitHub dark-ish, BEL-terminated
            (b"\x1b]11;rgb:ffff/ffff/f0f0\x1b\\", "light"),  # ST-terminated, 16-bit
            (b"\x1b]11;rgb:ff/ff/f0\x07", "light"),  # 8-bit channels
            (b"\x1b]11;rgb:0000/0000/0000\x07", "dark"),
            (b"\x1b]11;rgb:1e1e/2e2e/3e3e\x07", "dark"),
        ],
    )
    def test_luminance_split(self, reply: bytes, want: str) -> None:
        assert parse_osc11_reply(reply) == want

    def test_garbage_refuses(self) -> None:
        with pytest.raises(ValueError):
            parse_osc11_reply(b"\x1b]10;rgb:ffff/ffff/ffff\x07")


class TestDetectionGuards:
    def test_non_tty_refuses_with_explicit_fix(self, capsys: pytest.CaptureFixture[str]) -> None:
        # pytest's captured streams are not ttys — detection must refuse,
        # never default (auto is a detection, not a guess).
        with pytest.raises(HwError) as exc:
            detect_terminal_face()
        assert "--face light" in (exc.value.fix or "")
