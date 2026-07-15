r"""Kitty graphics-protocol blit — render a PNG inline in a capable terminal.

The compose CLI writes raw bytes to stdout/file by default. But raw PNG bytes to
an *interactive* terminal are line noise, never the wanted behavior — so when
``--format png`` targets a TTY, this module blits the image instead. Detection is
automatic (no ``--show`` flag): piped/redirected output (``not isatty``) always
stays raw bytes, so scripts are unaffected; only an interactive, graphics-capable
terminal triggers the blit. An interactive but non-capable terminal gets a short
stderr hint — never binary spewed at the TTY.

The protocol is an Application Programming Command (APC) most terminals ignore:
``ESC _ G <control keys> ; <base64 payload chunk> ESC \``. The PNG is base64-
encoded whole, split into <=4096-byte chunks; the control keys (``a=T`` transmit
+ display, ``f=100`` PNG) ride only the first chunk, and ``m=1``/``m=0`` mark
more/last. base64 output is always a multiple of 4, so 4096-byte slices satisfy
the "all but the last chunk must be a multiple of 4" rule for free.
"""

from __future__ import annotations

import base64
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import IO

# APC framing and the per-blit chunk size (protocol max).
_APC_START = b"\x1b_G"
_APC_END = b"\x1b\\"
_CHUNK = 4096

# TERM substrings for terminals that speak the kitty graphics protocol. kitty
# itself also exports KITTY_WINDOW_ID; ghostty and wezterm implement the protocol.
_CAPABLE_TERMS = ("kitty", "ghostty", "wezterm")


def terminal_supports_graphics(env: dict[str, str] | None = None) -> bool:
    """True when the environment looks like a kitty-graphics-capable terminal.

    Reads ``KITTY_WINDOW_ID`` (kitty sets it) or a ``TERM``/``TERM_PROGRAM``
    naming kitty | ghostty | wezterm. Detection is intentionally conservative:
    an unknown terminal returns False so the caller falls back to a stderr hint
    rather than risking binary at the TTY.
    """
    env = env if env is not None else dict(os.environ)
    if env.get("KITTY_WINDOW_ID"):
        return True
    haystack = f"{env.get('TERM', '')} {env.get('TERM_PROGRAM', '')}".lower()
    return any(name in haystack for name in _CAPABLE_TERMS)


def _chunks(payload: bytes) -> Iterator[bytes]:
    for i in range(0, len(payload), _CHUNK):
        yield payload[i : i + _CHUNK]


def blit_iter(png: bytes) -> Iterator[bytes]:
    """Yield the raw APC escape sequences that transmit+display ``png``.

    The first sequence carries ``a=T,f=100``; every sequence carries the ``m``
    flag (1 for more, 0 for the last). Empty input yields nothing.
    """
    encoded = base64.standard_b64encode(png)
    if not encoded:
        return
    parts = list(_chunks(encoded))
    for idx, chunk in enumerate(parts):
        last = idx == len(parts) - 1
        control = (f"a=T,f=100,m={0 if last else 1}" if idx == 0 else f"m={0 if last else 1}").encode("ascii")
        yield _APC_START + control + b";" + chunk + _APC_END


def blit(png: bytes, stream: IO[bytes]) -> None:
    """Write the kitty blit sequences for ``png`` to a binary ``stream``."""
    for seq in blit_iter(png):
        stream.write(seq)
    stream.write(b"\n")
    stream.flush()
