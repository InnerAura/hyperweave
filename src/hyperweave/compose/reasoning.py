"""Per-frame reasoning loader (v0.3.2).

Loads ``data/reasoning/{genome}.yaml`` and resolves (genome_id, frame_type,
substrate_kind) -> ReasoningFields. The ReasoningFields model at
``hyperweave.core.models`` enforces ``min_length=21`` on tradeoffs at
construction, so any reasoning entry that violates the quality bar fails
loud at compose time rather than silently emitting empty hw:reasoning.

Fallback chain when an exact match is missing:
  1. reasoning[genome][frame_type][substrate_kind]
  2. reasoning[genome][frame_type]["dark"]  (substrate-agnostic fallback)
  3. None  (resolver-side; metadata template emits empty hw:reasoning)

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
    substrate_kind: str = "dark",
) -> ReasoningFields | None:
    """Resolve (genome_id, frame_type, substrate_kind) -> ReasoningFields.

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

    # Fallback chain: exact substrate -> "dark" -> nothing
    for key in (substrate_kind, "dark"):
        block = frame_entry.get(key)
        if isinstance(block, dict) and block.get("intent") and block.get("approach") and block.get("tradeoffs"):
            return ReasoningFields(
                intent=block["intent"].strip(),
                approach=block["approach"].strip(),
                tradeoffs=block["tradeoffs"].strip(),
            )
    return None
