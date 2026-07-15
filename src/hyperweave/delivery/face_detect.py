"""``--face auto`` — terminal background detection via OSC 11 (§12.3).

Opt-in ONLY: the caller writes ``--face auto``; nothing is ever detected
behind an explicit ``--face light|dark`` (which stays the documented,
scriptable path). The query writes ``OSC 11 ; ? ST`` to the controlling
tty and reads the reply (``rgb:RRRR/GGGG/BBBB``); relative luminance picks
the face. Non-tty, timeout, or an unparseable reply raises with the
explicit-flag fix — auto never guesses.
"""

from __future__ import annotations

import os
import re
import select
import sys

from hyperweave.core.errors import HwError, HwErrorCode

_OSC11_QUERY = b"\x1b]11;?\x1b\\"
_REPLY = re.compile(rb"\]11;rgb:([0-9a-fA-F]+)/([0-9a-fA-F]+)/([0-9a-fA-F]+)")

_FIX = "pass --face light or --face dark explicitly (auto needs an OSC 11-capable interactive terminal)"


def parse_osc11_reply(reply: bytes) -> str:
    """``light`` or ``dark`` from an OSC 11 color reply.

    Channels arrive as 4/8/12/16-bit hex; each normalizes by its own width.
    The split is relative luminance (Rec. 709 weights) at 0.5 — the same
    midpoint the Surface Modes ground targets straddle."""
    m = _REPLY.search(reply)
    if m is None:
        raise ValueError(f"not an OSC 11 color reply: {reply!r}")
    channels = []
    for raw in m.groups():
        width = len(raw)
        channels.append(int(raw, 16) / (16**width - 1))
    r, g, b = channels
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "light" if luminance >= 0.5 else "dark"


def detect_terminal_face(timeout: float = 0.35) -> str:
    """Query the controlling terminal's background; return ``light|dark``.

    Raises ``HwError(SPEC_INVALID)`` when there is no tty to ask or the
    terminal stays silent — auto is a detection, never a default."""
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        raise HwError(HwErrorCode.SPEC_INVALID, "--face auto needs an interactive terminal", fix=_FIX)
    try:
        import termios
        import tty as _tty

        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
        try:
            old = termios.tcgetattr(fd)
            try:
                _tty.setcbreak(fd, termios.TCSANOW)
                os.write(fd, _OSC11_QUERY)
                reply = b""
                while True:
                    ready, _, _ = select.select([fd], [], [], timeout)
                    if not ready:
                        break
                    reply += os.read(fd, 256)
                    if b"\x07" in reply or b"\x1b\\" in reply[2:]:
                        break
                return parse_osc11_reply(reply)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        finally:
            os.close(fd)
    except HwError:
        raise
    except (OSError, ValueError) as exc:
        raise HwError(HwErrorCode.SPEC_INVALID, f"terminal background detection failed ({exc})", fix=_FIX) from exc
