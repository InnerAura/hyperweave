"""verify — recompute the hash, prove the artifact verifiably IS its data.

Promotes the conformance census's ``hash_valid`` check to a first-class runtime
verb: an agent verifies a received artifact before trusting or mutating it.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from hyperweave.core.envelope import envelope_id
from hyperweave.verbs.parse import extract_embedded, load_artifact


@dataclass(frozen=True)
class VerifyResult:
    hash_valid: bool
    well_formed: bool
    expected_id: str
    computed_id: str
    schema: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.hash_valid,
            "well_formed": self.well_formed,
            "id": self.computed_id,
            "expected_id": self.expected_id,
            "schema": self.schema,
        }


def _parses_as_xml(svg: str) -> bool:
    try:
        ET.fromstring(svg)
    except (ET.ParseError, ValueError):
        return False
    return True


def verify(source: str) -> VerifyResult:
    """Confirm ``envelope.id == sha256(payload)`` and that the container parses.

    ``hash_valid`` proves the seed is intact — extraction stays byte-exact regex
    (never an XML parse) so the hash is stable. ``well_formed`` reports whether
    the surrounding SVG parses as XML at all: the corruption class a hash check
    cannot see. The two are independent by design; neither gates the other.
    """
    svg = load_artifact(source)
    emb = extract_embedded(svg)
    computed = envelope_id(emb.payload_json)
    expected = str(emb.envelope.get("id", ""))
    return VerifyResult(
        hash_valid=bool(expected) and computed == expected,
        well_formed=_parses_as_xml(svg),
        expected_id=expected,
        computed_id=computed,
        schema=emb.schema,
    )
