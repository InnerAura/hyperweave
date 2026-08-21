"""Per-frame reasoning loader (v0.3.2).

Loads ``data/reasoning/{genome}.yaml`` and resolves (genome_id, frame_type,
substrate_kind) -> ReasoningFields. The ReasoningFields model at
``hyperweave.core.models`` enforces ``min_length=21`` on tradeoffs at
construction, so any reasoning entry that violates the quality bar fails
loud at compose time rather than silently emitting empty hw:reasoning.

Keyed on the RENDERED face — ``light`` / ``dark`` for a committed scheme,
``adaptive`` for a twin or inlay that carries both. Fallback chain when an
exact match is missing:
  1. reasoning[genome][frame_type][face]
  2. reasoning[genome][frame_type]["light"]  (an adaptive artifact's base scope
     is always the light face — surface_modes invariant 3 — so an unauthored
     `adaptive` block degrades to describing the scope a reader sees first)
  3. reasoning[genome][frame_type]["dark"]  (face-agnostic fallback)
  4. None  (resolver-side; metadata template emits empty hw:reasoning)

The loader is genome-agnostic — chrome.yaml and automata.yaml drop into
``data/reasoning/`` and slot in via the same code path with zero edits here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from hyperweave.core.models import ReasoningFields

_DATA_DIR: Path = Path(__file__).parent.parent / "data" / "reasoning"


@lru_cache(maxsize=8)
def _load_yaml_for_genome(genome_id: str) -> dict[str, Any]:
    """Read and cache the per-genome reasoning YAML. Empty dict if absent."""
    yaml_path = _DATA_DIR / f"{genome_id}.yaml"
    if not yaml_path.exists():
        return {}
    with yaml_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        return {}
    return data


def load_reasoning(
    genome_id: str,
    frame_type: str,
    face: str = "dark",
) -> ReasoningFields | None:
    """Resolve (genome_id, frame_type, rendered face) -> ReasoningFields.

    ``face`` is what the artifact renders as — ``light``/``dark`` for a
    committed scheme, ``adaptive`` for a twin or inlay carrying both.

    Returns None when no entry exists at any level of the fallback chain so the
    metadata template emits empty hw:reasoning fields rather than erroring.
    Construction of ReasoningFields enforces the quality bar (min_length=21
    on tradeoffs) so malformed entries fail loud — silent acceptance was the
    v0.2.x bug.
    """
    if not genome_id or not frame_type:
        return None
    genome_data = _load_yaml_for_genome(genome_id)
    if not genome_data:
        return None
    # Strip the top-level genome key (per-file structure: {genome_id: {frames}}).
    frames = genome_data.get(genome_id) or {}
    frame_entry = frames.get(frame_type)
    if not isinstance(frame_entry, dict):
        return None

    # Fallback chain: exact face -> "light" (an adaptive base scope) -> "dark"
    for key in (face, "light", "dark"):
        block = frame_entry.get(key)
        if isinstance(block, dict) and block.get("intent") and block.get("approach") and block.get("tradeoffs"):
            return ReasoningFields(
                intent=block["intent"].strip(),
                approach=block["approach"].strip(),
                tradeoffs=block["tradeoffs"].strip(),
            )
    return None


def load_transform_note(genome_id: str, frame_type: str) -> str:
    """The per-genome transform-delta template (empty when unauthored).

    Substrate-agnostic by design — the note describes an EDIT (what the patch
    changed and where the insertion seated), which is the same fact on every
    paper. It rides beside the substrate blocks under the frame entry; the
    caller fills the ``{delta}``/``{seat}`` slots from the lineage record."""
    if not genome_id or not frame_type:
        return ""
    frames = _load_yaml_for_genome(genome_id).get(genome_id) or {}
    frame_entry = frames.get(frame_type)
    if not isinstance(frame_entry, dict):
        return ""
    return str(frame_entry.get("transform_note") or "").strip()
