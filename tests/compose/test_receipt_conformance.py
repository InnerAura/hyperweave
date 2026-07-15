"""Conformance census for the receipt frame (build brief §6).

Asserts the agent-legibility contract across **all primer variants + the raw
chassis** over one session's data:

* ``envelope.id == sha256(embedded payload bytes)`` on every variant + raw.
* The embedded ``hw:payload`` is compact, single-line, **data-only** (no display
  strings: no ``$``, no interpunct-joined labels, no comma-grouped numerals).
* The payload **self-discloses the estimate** (``cost_basis`` + ``estimate``) —
  guaranteed by the frame even when the input payload omits it.
* Per-variant ``data-hw-mode`` tracks ``substrate_kind`` (a dark variant says
  ``dark``; the metadata never lies about the chassis it rendered).
* Both chassis carry the byte-identical payload + envelope id for one session.
"""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

_PRIMER_DARK = ("noir", "carbon", "space", "anvil")
_PRIMER_LIGHT = ("porcelain", "cream", "dusk", "petrol")
_ALL: list[tuple[str, str]] = [("primer", v) for v in _PRIMER_DARK + _PRIMER_LIGHT] + [("raw", "")]

# A complete receipt/1 payload (the locked v0.4 shape) carrying the disclosure.
_PAYLOAD: dict[str, object] = {
    "session": "398ce70f",
    "model": "opus-4.7",
    "cost_usd": 175.01,
    "dominant": "opus-4.7",
    "cost_basis": "public per-token rates",
    "estimate": True,
    "models": [
        {"name": "opus-4.7", "role": "main thread", "cost_usd": 128.0, "cost_pct": 73},
        {"name": "sonnet-4.6", "role": "subagent", "cost_usd": 39.0, "cost_pct": 22},
        {"name": "haiku-4.5", "role": "2 subagents", "cost_usd": 8.01, "cost_pct": 5},
    ],
    "tokens": {
        "total": 262400000,
        "in": 157500,
        "out": 867300,
        "cache_read": 257600000,
        "cache_write": 3800000,
        "working": 1024800,
    },
    "calls": 562,
    "stages": 55,
    "turns": 31,
    "errors": 15,
    "active_min": 157,
    "context": {
        "window": 200000,
        "peak_ctx": 196000,
        "events": [
            {"min": 31, "cmd": "compact", "to": 38000},
            {"min": 62, "cmd": "clear", "to": 6000},
            {"min": 92, "cmd": "auto", "to": 40000},
            {"min": 138, "cmd": "compact", "to": 38000},
        ],
        "note": "occupancy modelled from per-stage activity; resets at slash-command and auto-compaction",
    },
    "tools": [
        {"name": "Edit", "tok": 709300, "calls": 242, "err": 6, "class": "mutate"},
        {"name": "Bash", "tok": 116400, "calls": 162, "err": 2, "class": "execute"},
        {"name": "Read", "tok": 94600, "calls": 116, "err": 1, "class": "explore"},
        {"name": "TaskUpdate", "calls": 18},
    ],
}

_PAYLOAD_RE = re.compile(r'schema="receipt/1"[^>]*><!\[CDATA\[(.*?)\]\]>', re.DOTALL)
_ENV_RE = re.compile(r'(?:schema|format)="hwz/1"[^>]*><!\[CDATA\[(.*?)\]\]>', re.DOTALL)


def _render(genome: str, variant: str, payload: dict[str, object] | None = None) -> str:
    spec = ComposeSpec(type="receipt", genome_id=genome, variant=variant, telemetry_data=payload or _PAYLOAD)
    return compose(spec).svg


def _payload_str(svg: str) -> str:
    m = _PAYLOAD_RE.search(svg)
    assert m is not None, "no hw:payload schema=receipt/1 in output"
    return m.group(1)


def _envelope(svg: str) -> dict[str, object]:
    m = _ENV_RE.search(svg)
    assert m is not None, "no hwz/1 envelope in output"
    result: dict[str, object] = json.loads(m.group(1))
    return result


@pytest.mark.parametrize("genome,variant", _ALL)
def test_envelope_id_is_sha256_of_payload(genome: str, variant: str) -> None:
    """The hwz/1 envelope id hashes the exact embedded payload bytes."""
    svg = _render(genome, variant)
    payload_str = _payload_str(svg)
    expected = "sha256:" + hashlib.sha256(payload_str.encode()).hexdigest()
    assert _envelope(svg)["id"] == expected


@pytest.mark.parametrize("genome,variant", _ALL)
def test_payload_is_compact_data_only(genome: str, variant: str) -> None:
    """The embedded payload is single-line and carries no formatted display strings."""
    payload_str = _payload_str(_render(genome, variant))
    assert "\n" not in payload_str, "payload must be single-line"
    assert "$" not in payload_str, "no dollar-formatted figures in the payload"
    assert "·" not in payload_str, "no interpunct-joined display labels in the payload"
    assert re.search(r"\d,\d\d\d", payload_str) is None, "no comma-grouped numerals"
    json.loads(payload_str)  # parses as JSON


@pytest.mark.parametrize("genome,variant", _ALL)
def test_payload_self_discloses_estimate(genome: str, variant: str) -> None:
    """Every receipt discloses that its cost is a public-rate estimate."""
    payload = json.loads(_payload_str(_render(genome, variant)))
    assert payload["cost_basis"] == "public per-token rates"
    assert payload["estimate"] is True


def test_disclosure_guaranteed_when_input_omits_it() -> None:
    """A caller payload missing the disclosure still produces a disclosing receipt."""
    stripped = {k: v for k, v in _PAYLOAD.items() if k not in ("cost_basis", "estimate")}
    payload = json.loads(_payload_str(_render("primer", "porcelain", stripped)))
    assert payload["cost_basis"] == "public per-token rates"
    assert payload["estimate"] is True


@pytest.mark.parametrize("variant", _PRIMER_DARK)
def test_dark_variant_mode_is_dark(variant: str) -> None:
    """A dark substrate variant labels itself data-hw-mode=dark."""
    svg = _render("primer", variant)
    mode = re.search(r'data-hw-mode="([^"]*)"', svg)
    assert mode is not None and mode.group(1) == "dark"


@pytest.mark.parametrize("variant", _PRIMER_LIGHT)
def test_light_variant_mode_is_light(variant: str) -> None:
    """A light substrate variant labels itself data-hw-mode=light."""
    svg = _render("primer", variant)
    mode = re.search(r'data-hw-mode="([^"]*)"', svg)
    assert mode is not None and mode.group(1) == "light"


@pytest.mark.parametrize("genome,width", [("primer", 800), ("raw", 300)])
def test_chassis_width_is_fixed(genome: str, width: int) -> None:
    """Each chassis pins its WIDTH (800 card / 300 tape); the height is
    content-aware (the cursor stacks present zones), so the viewBox width is the
    chassis-identity invariant, not the height."""
    variant = "noir" if genome == "primer" else ""
    svg = _render(genome, variant)
    vb = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    assert vb is not None
    assert int(vb.group(1)) == width
    # Height tracks content within a sane band (no fixed-canvas dead space).
    height = int(vb.group(2))
    assert 300 <= height <= 900


def test_full_session_reaches_specimen_height() -> None:
    """A maximal multi-model session (3 per-model cost rows + 5 tool rows +
    overflow + all zones) renders a tall content-aware card — the height band's
    upper anchor. The per-model cost rows lift it past the single-legend 578px
    of the original single-model receipt specimen, in step with the multi-agent
    specimens (cream/2-model 594, porcelain/4-model 615)."""
    full = dict(_PAYLOAD)
    # Pad tools to the 5-row maximum (4 token tools + a collapsed overflow).
    full["tools"] = [
        {"name": "Edit", "tok": 709300, "calls": 242, "err": 6, "class": "mutate"},
        {"name": "Bash", "tok": 116400, "calls": 162, "err": 2, "class": "execute"},
        {"name": "Read", "tok": 94600, "calls": 116, "err": 1, "class": "explore"},
        {"name": "TaskCreate", "tok": 30200, "calls": 9, "class": "coordinate"},
        {"name": "TaskUpdate", "calls": 18},
        {"name": "Write", "calls": 3},
    ]
    svg = _render("primer", "noir", full)
    assert 'viewBox="0 0 800 621"' in svg


def test_both_chassis_share_payload_and_envelope_id() -> None:
    """The primer card and its raw twin carry an identical payload + envelope id."""
    primer = _render("primer", "porcelain")
    raw = _render("raw", "")
    assert _payload_str(primer) == _payload_str(raw)
    assert _envelope(primer)["id"] == _envelope(raw)["id"]
