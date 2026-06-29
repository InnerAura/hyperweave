---
name: hyperweave-verbs
description: Read, verify, mutate, and round-trip HyperWeave living artifacts via the verb algebra instead of vision-parsing the SVG.
---

# HyperWeave verbs

A HyperWeave artifact is a polyglot container: a branded SVG whose data also
travels as a structured payload in `<metadata>`. Reason about the data; never
parse pixels.

Two seeds are embedded in every artifact:

- **`hw:payload`** — the lossless spec. Replant it (compose) → byte-identical artifact.
- **`hw:envelope`** — the compact `hwz/1` digest. `id = sha256(payload)`. ~200 tokens, actionable.

## The algebra

| Verb | Binds to | Use it to |
|---|---|---|
| `extract(artifact, respond=envelope\|payload\|markdown)` | either | pull the seed at a depth |
| `verify(artifact)` | envelope | prove `id == sha256(payload)` before trusting it |
| `transform(artifact, mutations)` | payload | RFC-6902 patch → a new artifact |
| `diff(a, b)` | payload | structured delta (added/removed/changed) |
| `query(artifact, question)` | envelope | a cheap answer without re-reading the SVG |

`compose` and `transform` return `{envelope, url}` — embed `![](url)`; the pixels
never enter your context.

## Worked loop

1. `hw_compose(type="matrix", genome="primer", matrix={…})` → `{envelope, url}`
2. `hw_extract(svg, respond="payload")` → the full `MatrixSpec` seed
3. `hw_transform(svg, [{"op":"replace","path":"/rows/0/cells/1/value","value":"9.99"}])` → new `{envelope, url, lineage}`
4. `hw_verify(new_svg)` → `{valid: true}`

Mutations are RFC-6902 ops (`add`/`remove`/`replace`/`move`/`copy`/`test`). A
patch that breaks the frame schema fails cleanly as `SPEC_INVALID`; a tampered
artifact fails as `ENVELOPE_CORRUPT` before any mutation. `transform` and `diff`
support `matrix` and `diagram`.

Full contract: `https://hyperweave.app/llms.txt`.
