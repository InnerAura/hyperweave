"""Kitty graphics-protocol blit — framing, chunking, and terminal detection."""

from __future__ import annotations

import base64
import io

from hyperweave.delivery import kitty

# A payload larger than one chunk (4096 b64 chars ≈ 3072 raw bytes) so the
# multi-chunk m=1/m=0 sequence is exercised.
_BIG = bytes(range(256)) * 40  # 10240 bytes → 13656 b64 chars → 4 chunks


def test_single_chunk_framing() -> None:
    """A small PNG becomes one APC sequence with a=T,f=100,m=0 and the payload."""
    seqs = list(kitty.blit_iter(b"\x89PNG\r\n\x1a\n"))
    assert len(seqs) == 1
    seq = seqs[0]
    assert seq.startswith(b"\x1b_Ga=T,f=100,m=0;")
    assert seq.endswith(b"\x1b\\")
    body = seq[len(b"\x1b_Ga=T,f=100,m=0;") : -len(b"\x1b\\")]
    assert base64.standard_b64decode(body) == b"\x89PNG\r\n\x1a\n"


def test_multi_chunk_control_keys_only_on_first() -> None:
    """Control keys ride the first chunk only; middles carry m=1, last m=0."""
    seqs = list(kitty.blit_iter(_BIG))
    assert len(seqs) >= 3
    assert seqs[0].startswith(b"\x1b_Ga=T,f=100,m=1;")
    for mid in seqs[1:-1]:
        assert mid.startswith(b"\x1b_Gm=1;")
        assert b"a=T" not in mid and b"f=100" not in mid
    assert seqs[-1].startswith(b"\x1b_Gm=0;")


def test_chunks_reassemble_to_payload() -> None:
    """Concatenated chunk payloads base64-decode back to the original bytes."""
    seqs = list(kitty.blit_iter(_BIG))
    b64 = b""
    for seq in seqs:
        body = seq[seq.index(b";") + 1 : -len(b"\x1b\\")]
        b64 += body
    assert base64.standard_b64decode(b64) == _BIG


def test_non_last_chunks_are_multiple_of_four() -> None:
    """The protocol requires every non-last chunk's size to be a multiple of 4."""
    seqs = list(kitty.blit_iter(_BIG))
    for seq in seqs[:-1]:
        body = seq[seq.index(b";") + 1 : -len(b"\x1b\\")]
        assert len(body) % 4 == 0


def test_blit_writes_to_stream_and_newline() -> None:
    buf = io.BytesIO()
    kitty.blit(b"\x89PNG\r\n\x1a\n", buf)
    out = buf.getvalue()
    assert out.startswith(b"\x1b_G")
    assert out.endswith(b"\n")


def test_empty_payload_yields_nothing() -> None:
    assert list(kitty.blit_iter(b"")) == []


def test_terminal_detection_kitty_window_id() -> None:
    assert kitty.terminal_supports_graphics({"KITTY_WINDOW_ID": "1"})


def test_terminal_detection_term_names() -> None:
    assert kitty.terminal_supports_graphics({"TERM": "xterm-kitty"})
    assert kitty.terminal_supports_graphics({"TERM_PROGRAM": "ghostty"})
    assert kitty.terminal_supports_graphics({"TERM": "wezterm"})


def test_terminal_detection_negative() -> None:
    assert not kitty.terminal_supports_graphics({"TERM": "xterm-256color"})
    assert not kitty.terminal_supports_graphics({})
