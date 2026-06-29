"""diff — payload-bound typed delta between two artifacts.

Binds to the PAYLOAD (the lossless seed), never the envelope: an envelope diff is
lossy by construction and silently drops per-field edits (proven — it once missed
a matrix cell flip). The ``lineage`` field is excluded from the content delta
(else every transformed artifact shows a phantom "lineage changed"); descent and
genome changes are reported separately. Read-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.verbs.parse import extract_embedded, load_artifact


@dataclass(frozen=True)
class DiffResult:
    same: bool
    schema: str
    title_changed: tuple[str, str] | None = None
    genome_changed: tuple[str, str] | None = None
    added: dict[str, list[str]] = field(default_factory=dict)
    removed: dict[str, list[str]] = field(default_factory=dict)
    changed: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "same": self.same,
            "schema": self.schema,
            "title_changed": list(self.title_changed) if self.title_changed else None,
            "genome_changed": list(self.genome_changed) if self.genome_changed else None,
            "added": self.added,
            "removed": self.removed,
            "changed": self.changed,
        }


def _content(payload: dict[str, Any], schema: str) -> dict[str, Any]:
    """The comparable content: the spec minus lineage; for diagram, minus rendered."""
    spec = dict(payload.get("spec", payload)) if schema == "diagram/1" else dict(payload)
    spec.pop("lineage", None)
    return spec


def _prov_genome(env: dict[str, Any]) -> str:
    return str((env.get("prov") or {}).get("genome", ""))


def _diff_matrix(
    a: dict[str, Any], b: dict[str, Any]
) -> tuple[dict[str, list[str]], dict[str, list[str]], list[dict[str, Any]]]:
    rows_a = {str(r.get("label", i)): r for i, r in enumerate(a.get("rows", []))}
    rows_b = {str(r.get("label", i)): r for i, r in enumerate(b.get("rows", []))}
    added = {"rows": [k for k in rows_b if k not in rows_a]}
    removed = {"rows": [k for k in rows_a if k not in rows_b]}
    changed: list[dict[str, Any]] = []
    for key in rows_a.keys() & rows_b.keys():
        ca, cb = rows_a[key].get("cells", []), rows_b[key].get("cells", [])
        for i, (x, y) in enumerate(zip(ca, cb, strict=False)):
            if x != y:
                changed.append({"row": key, "cell": i, "from": x, "to": y})
    cols_a = [c.get("id") for c in a.get("columns", [])]
    cols_b = [c.get("id") for c in b.get("columns", [])]
    added["columns"] = [c for c in cols_b if c not in cols_a]
    removed["columns"] = [c for c in cols_a if c not in cols_b]
    return added, removed, changed


def _diff_diagram(
    a: dict[str, Any], b: dict[str, Any]
) -> tuple[dict[str, list[str]], dict[str, list[str]], list[dict[str, Any]]]:
    def _nodes(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {str(n.get("id", n.get("label", i))): n for i, n in enumerate(spec.get("nodes", []))}

    def _edges(spec: dict[str, Any]) -> set[str]:
        return {f"{e.get('source')}->{e.get('target')}" for e in spec.get("edges", [])}

    na, nb = _nodes(a), _nodes(b)
    ea, eb = _edges(a), _edges(b)
    added = {"nodes": [k for k in nb if k not in na], "edges": sorted(eb - ea)}
    removed = {"nodes": [k for k in na if k not in nb], "edges": sorted(ea - eb)}
    changed = [{"node": k, "from": na[k], "to": nb[k]} for k in na.keys() & nb.keys() if na[k] != nb[k]]
    return added, removed, changed


def diff(source_a: str, source_b: str) -> DiffResult:
    """Structured delta between two artifacts (payload-bound)."""
    ea = extract_embedded(load_artifact(source_a))
    eb = extract_embedded(load_artifact(source_b))
    if ea.schema != eb.schema:
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            f"cannot diff different frame types: {ea.schema} vs {eb.schema}",
            fix="diff two artifacts of the same frame type",
        )

    ca, cb = _content(ea.payload, ea.schema), _content(eb.payload, eb.schema)
    title_changed = None
    ta, tb = str(ca.get("title", "")), str(cb.get("title", ""))
    if ta != tb:
        title_changed = (ta, tb)
    la, lb = _prov_genome(ea.envelope), _prov_genome(eb.envelope)
    genome_changed = (la, lb) if la != lb else None

    if ea.schema == "matrix/1":
        added, removed, changed = _diff_matrix(ca, cb)
    elif ea.schema == "diagram/1":
        added, removed, changed = _diff_diagram(ca, cb)
    else:
        # generic key-level delta for content frames
        keys = set(ca) | set(cb)
        changed = [{"field": k, "from": ca.get(k), "to": cb.get(k)} for k in keys if ca.get(k) != cb.get(k)]
        added, removed = {}, {}

    has_struct = any(added.values()) or any(removed.values()) or bool(changed)
    same = not has_struct and title_changed is None and genome_changed is None
    return DiffResult(
        same=same,
        schema=ea.schema,
        title_changed=title_changed,
        genome_changed=genome_changed,
        added={k: v for k, v in added.items() if v},
        removed={k: v for k, v in removed.items() if v},
        changed=changed,
    )
