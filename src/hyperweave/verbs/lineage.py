"""hw:lineage — the append-only edit history written by ``transform``.

Each entry is ``{parent_id, op, patch, ts}`` (+ optional ``intent``). The chain
rides inside the hashed payload, so it is tamper-evident, and every
``transform → diff`` pair is a labelled trajectory — the refinement-sequence
corpus the spatial model trains on. ``op`` is an OPEN enum (``transform`` today;
``reskin``/``ai-edit`` join later) so new op kinds need no payload migration.
"""

from __future__ import annotations

from typing import Any


def build_lineage_entry(
    parent_id: str,
    op: str,
    patch: list[dict[str, Any]] | dict[str, Any],
    ts: str,
    intent: str = "",
) -> dict[str, Any]:
    """Construct one append-only lineage entry."""
    entry: dict[str, Any] = {
        "parent_id": parent_id,
        "op": op,
        "patch": [patch] if isinstance(patch, dict) else list(patch),
        "ts": ts,
    }
    if intent:
        entry["intent"] = intent
    return entry
