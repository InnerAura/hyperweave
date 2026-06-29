"""The agent contract — how a cold agent discovers the protocol from an artifact.

A self-instruction comment is injected into every artifact at compose time; it
points at ``/llms.txt`` and names the verbs. The gate is not "the verbs exist" —
it is "an agent that has never seen HyperWeave finds the contract from the
artifact alone and round-trips it."
"""

from __future__ import annotations

SELF_INSTRUCT = (
    "agents: this is a HyperWeave living artifact. Its data is in <metadata> — "
    "hw:payload (lossless seed, replant to regenerate) and hw:envelope (compact "
    "hwz/1 digest, ~200 tokens, actionable). Verbs over the seed: extract · "
    "verify · transform · diff · query. Contract: https://hyperweave.app/llms.txt"
)

LLMS_TXT = """# HyperWeave

HyperWeave artifacts are polyglot containers: a branded SVG whose data also
travels as a structured payload, so agents reason about them instead of
vision-parsing pixels. Every artifact embeds two seeds in its <metadata>:

  hw:payload   — the lossless spec. Replant it (compose) → byte-identical artifact.
  hw:envelope  — the compact hwz/1 digest. id = sha256(payload). ~200 tokens, actionable.

## The verb algebra

  extract(artifact, respond=envelope|payload|markdown)  pull the seed at a depth
  verify(artifact)                                       prove id == sha256(payload)
  transform(artifact, mutations)                         RFC-6902 patch → new artifact
  diff(a, b)                                             payload-bound structured delta
  query(artifact, question)                              cheap answer from the envelope

transform/diff bind to the payload (lossless); query/verify use the envelope
(compact). compose and transform return {envelope, url} — never inline SVG.

## Round-trip

  create → embed → extract → transform → re-embed. Semantic identity is the
  guarantee: the geometry is reproducible from payload + genome; the payload is
  the source of truth, the visual is one projection.

## Surfaces

  MCP:  hw_compose · hw_extract · hw_verify · hw_transform · hw_diff · hw_query · hw_discover
  HTTP: POST /v1/{compose,validate,extract,verify,transform,diff,query} · GET /v1/a/{digest}
  CLI:  hyperweave compose|validate
"""


def discover_verbs() -> dict[str, object]:
    """The ``hw_discover(what='verbs')`` section: signatures + a worked example."""
    return {
        "binding": (
            "transform/diff → payload (lossless); query/verify → envelope (compact). "
            "compose/transform return {envelope, url}."
        ),
        "extract": (
            "extract(artifact, respond=envelope|payload|markdown) → the seed at a depth. "
            "hw_compress is the alias for envelope depth."
        ),
        "verify": "verify(artifact) → {valid, id} — recompute sha256(payload), confirm it equals the envelope id.",
        "transform": (
            "transform(artifact, mutations) → {envelope, url, lineage}. mutations is an RFC-6902 "
            "patch list (add/remove/replace/move/copy/test). matrix and diagram supported."
        ),
        "diff": (
            "diff(a, b) → {added, removed, changed, title_changed, genome_changed}. "
            "Excludes lineage. Same frame type only."
        ),
        "query": "query(artifact, question) → {answer, field}. Deterministic field lookup over the envelope.",
        "worked_example": {
            "1_compose": "hw_compose(type='matrix', genome='primer', matrix={...}) → {envelope, url}",
            "2_extract": "hw_extract(svg, respond='payload') → the full MatrixSpec seed",
            "3_transform": (
                "hw_transform(svg, [{'op':'replace','path':'/rows/0/cells/1/value','value':'9.99'}]) "
                "→ new {envelope, url, lineage}"
            ),
            "4_verify": "hw_verify(new_svg) → {valid: true}",
        },
    }
