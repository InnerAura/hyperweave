"""transform — the write half. ``artifact + structural mutation → new artifact``.

Pipeline: extract the embedded seed → verify the hash (never patch a corrupt
seed) → apply the structural JSON patch (for a diagram, on ``spec`` only — the
``rendered`` block is regenerated, never patched) → re-validate against the frame
model → append a lineage entry INTO the hashed payload → recompose. The agent
passes an id and a diff; it never reconstructs a spec. Every transform→diff pair
is a labelled trajectory for the spatial-model corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from hyperweave.compose.artifact_store import store_artifact
from hyperweave.compose.diagram.pinning import child_rank_orders
from hyperweave.compose.engine import compose
from hyperweave.compose.surface import build_artifact_url
from hyperweave.core.envelope import envelope_id, extract_envelope
from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.verbs.lineage import build_lineage_entry
from hyperweave.verbs.parse import extract_embedded, load_artifact
from hyperweave.verbs.patch import apply_json_patch
from hyperweave.verbs.recompose import payload_to_compose_spec
from hyperweave.verbs.schemas import frame_schema_for

_TRANSFORMABLE = ("matrix/1", "diagram/1")

Mutation = list[dict[str, Any]] | dict[str, Any]


@dataclass(frozen=True)
class TransformResult:
    svg: str
    envelope: dict[str, Any]
    url: str
    lineage: list[dict[str, Any]]
    parent_id: str
    new_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope,
            "url": self.url,
            "lineage": self.lineage,
            "parent_id": self.parent_id,
            "new_id": self.new_id,
        }


def transform(
    source: str,
    mutation: Mutation,
    *,
    relation: str = "transform",
    intent: str = "",
    ts: str = "",
    base_url: str = "",
) -> TransformResult:
    """Extract → verify → patch → re-validate → lineage → recompose."""
    emb = extract_embedded(load_artifact(source))

    # verify-hash-first — never mutate a corrupt seed
    declared = str(emb.envelope.get("id", ""))
    parent_id = envelope_id(emb.payload_json)
    if declared and declared != parent_id:
        raise HwError(
            HwErrorCode.ENVELOPE_CORRUPT,
            f"artifact hash mismatch: envelope says {declared}, payload hashes to {parent_id}",
            fix="the artifact was tampered with or truncated; re-extract from a trusted source",
        )

    if emb.schema not in _TRANSFORMABLE:
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            f"transform supports {' and '.join(_TRANSFORMABLE)}, not {emb.schema!r}",
            fix="transform a matrix or diagram artifact",
        )

    # diagram: patch the spec, regenerate rendered. matrix: the payload IS the spec.
    is_diagram = emb.schema == "diagram/1"
    spec_dict = emb.payload.get("spec", {}) if is_diagram else emb.payload

    patched = apply_json_patch(spec_dict, mutation)
    if not isinstance(patched, dict):
        raise HwError(HwErrorCode.SPEC_INVALID, "a patch that replaces the whole spec must yield an object")

    model = frame_schema_for(emb.schema)
    if model is not None:
        try:
            model.model_validate(patched)
        except Exception as exc:
            raise HwError(
                HwErrorCode.SPEC_INVALID,
                f"patched {emb.schema} fails validation: {exc}",
                detail={"schema": emb.schema},
            ) from exc

    # Row-order pins: the child inherits the parent's rendered order, so the
    # figure survives the edit — survivors keep their rows, insertions seat at
    # their rank's extent. Inherited from the parent's own pins when it was
    # itself a transform child, else from its deterministic re-solve; written
    # INTO the hashed payload beside lineage so chains read rendered truth.
    # Dag-only: no other topology has a rank grid to pin, and a cyclic patch
    # that promotes to state-machine ignores pins at the solver.
    if is_diagram and str(patched.get("topology", "")) == "dag":
        patched["layout"] = {"rank_orders": child_rank_orders(spec_dict, patched)}

    # append lineage INTO the hashed payload, so the new id covers the chain
    entry = build_lineage_entry(parent_id, relation, mutation, ts or datetime.now(UTC).isoformat(), intent)
    new_lineage = [*list(patched.get("lineage", [])), entry]
    patched["lineage"] = new_lineage

    spec = payload_to_compose_spec(emb.schema, patched, emb.envelope.get("prov", {}))
    result = compose(spec)
    new_env = extract_envelope(result.svg) or {}
    new_id = str(new_env.get("id", ""))
    url = ""
    if new_id:
        store_artifact(new_id, result.svg)
        url = build_artifact_url(new_id, base_url)

    return TransformResult(
        svg=result.svg, envelope=new_env, url=url, lineage=new_lineage, parent_id=parent_id, new_id=new_id
    )
