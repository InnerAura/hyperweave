"""verify — recompute the hash, prove the artifact verifiably IS its data.

Promotes the conformance census's ``hash_valid`` check to a first-class runtime
verb: an agent verifies a received artifact before trusting or mutating it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hyperweave.core.envelope import envelope_id
from hyperweave.verbs.parse import extract_embedded, load_artifact


@dataclass(frozen=True)
class VerifyResult:
    hash_valid: bool
    expected_id: str
    computed_id: str
    schema: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.hash_valid,
            "id": self.computed_id,
            "expected_id": self.expected_id,
            "schema": self.schema,
        }


def verify(source: str) -> VerifyResult:
    """Confirm ``envelope.id == sha256(payload)`` for an artifact."""
    emb = extract_embedded(load_artifact(source))
    computed = envelope_id(emb.payload_json)
    expected = str(emb.envelope.get("id", ""))
    return VerifyResult(
        hash_valid=bool(expected) and computed == expected,
        expected_id=expected,
        computed_id=computed,
        schema=emb.schema,
    )
