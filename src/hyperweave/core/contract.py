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

# The narrative head of /llms.txt — hand-authored teaching prose. The
# ``## Surfaces`` block is NOT hard-coded here: it is generated from the
# capability registry at request time (see surfaces/discover.py:render_llms_txt),
# so the surface enumeration cannot drift from the code as CLI/HTTP/MCP
# reachability changes. The full doc (/llms-full.txt) appends the SKILL body and
# the per-capability index to this same head.
LLMS_TXT_HEAD = """# HyperWeave

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
"""


# Where each caller-supplied string lands, per frame. A frame whose text all
# draws where you'd expect has no entry — the map exists for the surprises.
#
# The diagram entry is the one that cost an agent a turn: `title` is accepted,
# reaches <title>/<desc>/the payload/the markdown lead, and draws as the caption
# ONLY when `subtitle` is empty, because the artifact has no masthead — the host
# page owns the heading. Passing both looks like the title was dropped.
_TEXT_ROLES: dict[str, dict[str, str]] = {
    "diagram": {
        "title": "the artifact's name — <title>, <desc>, the payload, and the markdown lead; "
        "draws as the caption only when subtitle is empty",
        "subtitle": "the caption line drawn at the base",
    },
}


def text_roles(frame_type: str) -> dict[str, str]:
    """Where this frame's caller-supplied strings land. Empty when unremarkable."""
    return dict(_TEXT_ROLES.get(frame_type, {}))


# A question the deterministic field map actually resolves for this frame, so
# the printed `query` call returns a real field rather than falling through to
# the intent string. "what is this" is the universal answer (envelope intent).
_QUERY_EXAMPLES: dict[str, str] = {
    "diagram": "how many nodes",
    "matrix": "how many rows",
}


def next_commands(handle: str, frame_type: str = "") -> list[dict[str, str]]:
    """The verbs that operate on a just-composed artifact, as runnable commands.

    Built from the same verb names ``SELF_INSTRUCT`` embeds and
    :func:`discover_verbs` documents, so the artifact's own text, the terminal
    hint, and this list cannot drift apart. ``handle`` is whatever the caller
    can pass back in — the file they just wrote, or a stored-artifact url.

    Frame-aware, because a suggestion that errors is worse than no suggestion:
    ``transform`` is offered only on the frames it accepts (its own allowlist is
    the source), and the ``query`` example is one the field map resolves.
    """
    from hyperweave.verbs.transform import transformable_frames

    question = _QUERY_EXAMPLES.get(frame_type, "what is this")
    commands = [
        {"verb": "extract", "command": f"hyperweave extract {handle} --respond payload"},
        {"verb": "query", "command": f'hyperweave query {handle} "{question}"'},
    ]
    if frame_type in transformable_frames():
        commands.append(
            {
                "verb": "transform",
                "command": (
                    f"hyperweave transform {handle} "
                    '--patch-json \'[{"op":"replace","path":"/title","value":"New title"}]\' -o next.svg'
                ),
            }
        )
    commands.append({"verb": "verify", "command": f"hyperweave verify {handle}"})
    commands.append({"verb": "discover", "command": "hyperweave discover verbs"})
    return commands


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
            "2_extract": "hw_extract(source=svg, respond='payload') → the full MatrixSpec seed",
            "3_transform": (
                "hw_transform(source=svg, mutations=[{'op':'replace','path':'/rows/0/cells/1/value',"
                "'value':'9.99'}]) → new {envelope, url, lineage}"
            ),
            "4_verify": "hw_verify(source=new_svg) → {valid: true}",
        },
    }
