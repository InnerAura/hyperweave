"""hwz/1 envelope — the shared, frame-agnostic emitter.

This module is the SINGLE source of the hwz/1 shape. Artifacts self-emit
their envelope through :func:`build_envelope` at compose time, and the
``hw_compress`` tool (Session 6) extracts envelopes through the SAME
function — self-emitted equals extracted by construction. Nothing
frame-specific lives at the top level; frame digests nest under ``data``.

Canonical top-level shape (key order is emission order)::

    {
        "v": "hwz/1",
        "id": "sha256:...",  # sha256 of the canonical hw:payload JSON
        "k": "matrix",  # artifact kind (frame type / "visual-doc")
        "title": "...",
        "intent": "...",
        "state": "...",  # optional
        "ref": "hw://... | https://...",  # optional — only when addressable
        "data": {...},  # frame digest; capped lists carry *_total
        "frames": [{"t": "matrix", "l": "..."}],
        "prov": {"by": "hyperweave", "ver": "...", "genome": "...", "ts": "..."},
    }

Determinism pins:

- ``id`` is recomputable from the embedded ``hw:payload`` string alone.
- ``prov.ts`` is the artifact's ``hw:created`` value — never a second
  clock read, so envelope and metadata always agree.
- No ``ttok`` field: token counts decay with tokenizers and prices; the
  envelope's value is being actionable, not small (PRD §6).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

ENVELOPE_VERSION = "hwz/1"

# Extraction patterns — match the CDATA bodies byte-for-byte (no XML parse, so
# the payload bytes stay hash-stable for id recomputation). The payload schema
# is captured so callers route the seed to the right frame model.
_PAYLOAD_RE = re.compile(
    r'<hw:payload[^>]*\bschema="([^"]+)"[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>',
    re.DOTALL,
)
_ENVELOPE_RE = re.compile(r"<hw:envelope[^>]*><!\[CDATA\[(.*?)\]\]></hw:envelope>", re.DOTALL)

REQUIRED_KEYS: frozenset[str] = frozenset({"v", "id", "k", "title", "intent", "data", "frames", "prov"})
OPTIONAL_KEYS: frozenset[str] = frozenset({"state", "ref"})
PROV_KEYS: frozenset[str] = frozenset({"by", "ver", "genome", "ts"})


def envelope_id(payload_json: str) -> str:
    """Content id: sha256 of the canonical payload JSON text."""
    return "sha256:" + hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def extract_payload(svg: str) -> tuple[str, str] | None:
    """Return ``(schema, payload_json)`` from an artifact's ``hw:payload``.

    ``None`` when the artifact carries no payload. The payload JSON is the exact
    embedded bytes, so ``envelope_id(payload_json)`` recomputes the id.
    """
    m = _PAYLOAD_RE.search(svg)
    return (m.group(1), m.group(2)) if m else None


def extract_envelope(svg: str) -> dict[str, Any] | None:
    """Return the parsed ``hw:envelope`` dict from an artifact, or ``None``."""
    m = _ENVELOPE_RE.search(svg)
    if not m:
        return None
    try:
        parsed = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def cdata_safe_json(text: str) -> str:
    """Make JSON text safe to embed inside ``<![CDATA[...]]>`` verbatim.

    ``]]>`` can only occur inside a JSON string literal, so rewriting it to
    the parse-equivalent ``]]\\u003e`` escape never changes the parsed
    value — and keeps the embedded bytes canonical (hash-stable).
    """
    return text.replace("]]>", "]]\\u003e")


def build_envelope(
    *,
    kind: str,
    title: str,
    intent: str,
    data: Mapping[str, Any],
    frames: Sequence[Mapping[str, str]],
    payload_json: str,
    genome_label: str,
    version: str,
    created: str,
    state: str = "",
    ref: str = "",
) -> dict[str, Any]:
    """Assemble a canonical hwz/1 envelope dict (insertion-ordered)."""
    envelope: dict[str, Any] = {
        "v": ENVELOPE_VERSION,
        "id": envelope_id(payload_json),
        "k": kind,
        "title": title,
        "intent": intent,
    }
    if state:
        envelope["state"] = state
    if ref:
        envelope["ref"] = ref
    envelope["data"] = dict(data)
    envelope["frames"] = [dict(f) for f in frames]
    envelope["prov"] = {"by": "hyperweave", "ver": version, "genome": genome_label, "ts": created}
    return envelope


def envelope_json(envelope: Mapping[str, Any]) -> str:
    """Compact JSON text of an envelope (the embedded representation)."""
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)


def validate_envelope(envelope: Mapping[str, Any]) -> None:
    """Schema gate: exact top-level key set, prov shape, frames shape.

    Raises ``ValueError`` on any deviation. Used by the self-emission
    tests and, in Session 6, by ``hw_compress`` round-trip verification.
    """
    keys = set(envelope.keys())
    missing = REQUIRED_KEYS - keys
    unknown = keys - REQUIRED_KEYS - OPTIONAL_KEYS
    if missing:
        raise ValueError(f"hwz/1 envelope missing required keys: {sorted(missing)}")
    if unknown:
        raise ValueError(f"hwz/1 envelope has unknown top-level keys: {sorted(unknown)}")
    if envelope["v"] != ENVELOPE_VERSION:
        raise ValueError(f"hwz/1 envelope version is {envelope['v']!r}, expected {ENVELOPE_VERSION!r}")
    if not str(envelope["id"]).startswith("sha256:"):
        raise ValueError("hwz/1 envelope id must be a sha256: digest of the payload JSON")
    prov = envelope.get("prov")
    if not isinstance(prov, dict) or set(prov.keys()) != set(PROV_KEYS):
        raise ValueError(f"hwz/1 envelope prov must carry exactly {sorted(PROV_KEYS)}")
    frames = envelope.get("frames")
    if not isinstance(frames, list) or not all(isinstance(f, dict) and {"t", "l"} <= set(f) for f in frames):
        raise ValueError("hwz/1 envelope frames must be a list of {t, l} entries")
    if not isinstance(envelope.get("data"), dict):
        raise ValueError("hwz/1 envelope data must be an object")
