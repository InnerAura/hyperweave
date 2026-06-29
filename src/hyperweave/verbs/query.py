"""query — envelope-bound Q→A from the compact digest, no SVG re-read.

Binds to the ENVELOPE (the ~150-token actionable digest) — this is where the
envelope earns its keep: cheap, not faithful ("what is this / does it already
show X / what did it cost"). Ships a deterministic field-map (zero dependency);
an LLM fallback over the envelope is a lazily-imported seam, only used when a
provider is configured, so ``pip install hyperweave`` stays zero-LLM-dep.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hyperweave.verbs.parse import extract_embedded, load_artifact


@dataclass(frozen=True)
class QueryResult:
    answer: str
    field: str = ""
    mechanism: str = "deterministic"
    confidence: str = "exact"

    def to_dict(self) -> dict[str, Any]:
        return {"answer": self.answer, "field": self.field, "mechanism": self.mechanism, "confidence": self.confidence}


def _data(env: dict[str, Any]) -> dict[str, Any]:
    d = env.get("data")
    return d if isinstance(d, dict) else {}


def _resolve(env: dict[str, Any], q: str) -> tuple[str, str] | None:
    """Map a normalized question to (answer, field) from envelope fields."""
    data = _data(env)
    prov = env.get("prov") or {}
    frames = env.get("frames") or []

    if any(w in q for w in ("how many", "count", "number of")):
        if "node" in q and "n" in data:
            return str(data["n"]), "data.n"
        if "row" in q and "rows_total" in data:
            return str(data["rows_total"]), "data.rows_total"
        if "frame" in q:
            return str(len(frames)), "frames"
        for key in ("n", "rows_total", "items_total", "points_total", "metrics_total"):
            if key in data:
                return str(data[key]), f"data.{key}"
    if "pattern" in q and "pattern" in data:
        return str(data["pattern"]), "data.pattern"
    if "hero" in q and "hero" in data:
        return str(data["hero"]), "data.hero"
    if any(w in q for w in ("genome", "genome", "skin", "style")):
        return str(prov.get("genome", "")), "prov.genome"
    if any(w in q for w in ("state", "status", "passing", "failing")):
        return str(env.get("state", "")), "state"
    if "kind" in q or "frame type" in q or "what type" in q:
        return str(env.get("k", "")), "k"
    if any(w in q for w in ("title", "name", "called")):
        return str(env.get("title", "")), "title"
    if any(w in q for w in ("what is this", "what does", "intent", "purpose", "about")):
        return str(env.get("intent", "") or env.get("title", "")), "intent"
    return None


def query(source: str, question: str) -> QueryResult:
    """Answer a question about an artifact from its envelope."""
    env = extract_embedded(load_artifact(source)).envelope
    hit = _resolve(env, question.lower().strip())
    if hit is not None:
        answer, fieldname = hit
        return QueryResult(answer=answer, field=fieldname, mechanism="deterministic", confidence="exact")
    # No deterministic field — surface the intent as the best cheap answer.
    return QueryResult(
        answer=str(env.get("intent", "") or env.get("title", "") or "(no answer in the envelope digest)"),
        field="",
        mechanism="deterministic",
        confidence="inferred",
    )
