"""The verb gallery — the algebra as three agentic workflow chains.

Deliberately NOT built on :mod:`scripts.examples.manifest`. Every other gallery
is a set of artifacts each composed from one spec, which is exactly what a
``Gallery`` models. A verb chain is not that: its artifacts are the OUTPUT of
operations on other artifacts — a transform child derives from the parent
rendered a step earlier, and its lineage has to chain to the artifact that
actually exists. Forcing that into a spec-per-artifact manifest would make two
structurally different things look interchangeable, and the resemblance would
be the lie.

So this module keeps its own shape: run the verbs for real, embed each
operation beside the artifact it produced. The convention it holds to is that
no step is described in prose without the render that proves it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.examples.render import OUTPUTS, REPO, render
from scripts.examples.render import spec as _spec
from scripts.examples.render import write as _write


def _compose(frame_type: str, genome: str, *args: Any, **kwargs: Any) -> str:
    """Compose through the shared gallery seam (CDN fonts, canonical spec)."""
    return render(_spec(frame_type, genome, *args, **kwargs))


VERBS_ROOT = OUTPUTS / "verbs"


def _verb_appendix() -> list[str]:
    """The per-surface error model + name-divergence tables (the doc's appendix).

    These survive from the first README_VERB cut as reference — the chains above
    are the spine (operations paired with rendered artifacts); this closes the
    file with the flat contract a scripter checks when moving across surfaces.
    """
    return [
        "",
        "## Appendix — surface contract",
        "",
        "The chains above run the verbs for real and embed what they produce. This"
        " appendix is the flat reference: the error model and how each surface names"
        " the same input.",
        "",
        "### Error model",
        "",
        "| Surface | Success | Bad request field | Business-logic reject |",
        "| --- | --- | --- | --- |",
        "| CLI | exit `0`, JSON on stdout | usage error, exit `2` | `HwError.cli_text()` on stderr, exit `1` |",
        "| HTTP | `200` | `422` (Pydantic — missing/typed field) | `400` + `{error:{code,message,fix}}` |",
        "| MCP | tool result dict | tool-arg error | `SPEC_INVALID` in the result envelope |",
        "",
        "The HTTP layering: a **`422`** means the body was malformed (a required field"
        " like `source`/`mutations` absent); a **`400`** means it parsed but the"
        " operation was invalid (mismatched frame types, a source with no payload, a"
        " patch that breaks the schema). The `400` body always carries `code` +"
        " `message` + `fix`.",
        "",
        "### Surface vocabulary",
        "",
        "One capability core, three thin adapters — results agree byte-for-byte. The"
        " HTTP body and MCP params share ONE vocabulary (`source`, `a`/`b`,"
        " `mutations`); the CLI differs only in surface idiom — positional arguments"
        " and `--patch` as a file-path convenience.",
        "",
        "| Verb | CLI | HTTP body | MCP params |",
        "| --- | --- | --- | --- |",
        "| extract | `SOURCE`, `--respond` | `source`, `respond` | `source`, `respond` |",
        "| verify | `SOURCE` | `source` | `source` |",
        "| diff | `A` `B`, `--exit-code` | `a`, `b` | `a`, `b` |",
        "| query | `SOURCE` `QUESTION` | `source`, `question` | `source`, `question` |",
        "| transform | `SOURCE`, `--patch`/`--patch-json` | `source`, `mutations` | `source`, `mutations` |",
        "",
        "- **The only naming difference is the CLI idiom**: positional `SOURCE`/`A`/`B`"
        " arguments, and `--patch`/`--patch-json` (a file-path/inline convenience) vs"
        " the HTTP/MCP `mutations` field — the RFC-6902 op-list content is identical.",
        "- **`source` accepts more than a file** on the CLI: `-` (stdin), a path, an"
        " `http(s)` URL, a raw `<svg…>`, or a `/v1/a/{digest}` handle (resolved over"
        " the render tier; format suffixes stripped first).",
        "- **transform returns a handle on every surface** — `{envelope, url, lineage,"
        " …}`, never raw bytes; the SVG is cached, so fetch the `url` to render it.",
        "",
    ]


def emit() -> None:
    """Emit outputs/README.md — the verb algebra as agentic workflow chains.

    Not a per-verb reference (that is the appendix): the spine is three chains of
    REAL operations over VISIBLE artifacts, following the proofset convention that
    every operation is paired with its rendered SVG so depth is verified by eye,
    never asserted in prose. The verbs run for real here — Chain A/B via the
    in-process Python API, Chain C additionally through the CLI (subprocess) and
    HTTP (in-process ASGI) to PROVE byte-equal digests across surfaces. Renders
    are written under ``outputs/verbs/`` with paths relative to this
    README's directory.
    """
    import json as _json

    from hyperweave.compose.artifact_store import store_artifact
    from hyperweave.core.envelope import extract_envelope
    from hyperweave.verbs import diff, extract, query, transform, verify

    out_dir = VERBS_ROOT
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.svg"):
        stale.unlink()
    rel = "."

    def _short_id(env: dict[str, Any]) -> str:
        """The envelope id trimmed to a readable prefix (full ids are 64 hex)."""
        raw = str(env.get("id", ""))
        body = raw.split(":", 1)[1] if ":" in raw else raw
        return f"sha256:{body[:12]}…" if body else "(none)"

    lines: list[str] = [
        "# HyperWeave Verbs — agentic workflow chains",
        "",
        "Every HyperWeave artifact carries its own spec: an embedded `hw:payload`"
        " (lossless) and an `hwz/1` envelope (the ~200-token actionable digest). The"
        " **verbs** — `extract`, `verify`, `diff`, `query`, `transform` (plus"
        " `compose`/`validate`) — are the read/write algebra over that contract,"
        " served identically across CLI / HTTP / MCP by one registry.",
        "",
        "This doc is a **proof, not a reference**: each chain below is a real agentic"
        " workflow, every operation paired with the artifact it produced so you can"
        " *see* that the depth is real — the transformed cell actually changed, the"
        " added node actually appears, the two surfaces actually agree. The artifacts"
        " and this file are emitted by `python -m scripts.examples` (the verbs run"
        " for real), never hand-authored. The flat per-surface contract is the"
        " [appendix](#appendix--surface-contract).",
        "",
        "---",
    ]

    # ══ Chain A — artifact lifecycle over a real status matrix ═══════════════
    tiers = _json.loads((REPO / "tests" / "fixtures" / "matrix" / "tiers.json").read_text())
    parent_svg = _compose("matrix", "primer", variant="porcelain", matrix=tiers)
    parent_env = extract_envelope(parent_svg) or {}
    parent_digest = str(parent_env.get("id", ""))
    if parent_digest:
        store_artifact(parent_digest, parent_svg)
    _write(out_dir / "chainA-1-parent.svg", parent_svg)

    # query — a real question answered from the envelope (deterministic, exact).
    q_rows = query(parent_svg, "how many rows does this matrix have?")
    q_title = query(parent_svg, "what is the title?")

    # transform — flip a real cell: the "chromatic · motion" row's Naked column
    # (off → on) via an RFC-6902 replace on the payload path. Row 3 (index 3),
    # column 0 (Naked). This is a genuine content edit, not a title tweak.
    patch = [{"op": "replace", "path": "/rows/3/cells/0/state", "value": "on"}]
    t = transform(parent_svg, patch)
    child_svg = t.svg
    _write(out_dir / "chainA-2-child.svg", child_svg)

    # diff — parent vs child: the structured delta (payload-bound, not pixels).
    d = diff(parent_svg, child_svg)

    # verify — both artifacts prove id == sha256(payload).
    vp = verify(parent_svg)
    vc = verify(child_svg)

    lines += [
        "",
        "## Chain A — artifact lifecycle",
        "",
        "*compose → query → transform → diff → verify.* An agent mints a status"
        " matrix, asks it a question, patches one cell, proves what changed, and"
        " confirms both artifacts are internally consistent — the read/write loop an"
        " agent actually runs.",
        "",
        "**1. compose** — a real metadata-tier matrix (9 rows, 4 columns, sectioned;"
        " `tests/fixtures/matrix/tiers.json`):",
        "",
        f"![Chain A parent matrix]({rel}/chainA-1-parent.svg)",
        "",
        f"<sub>`{_short_id(parent_env)}` · schema `{vp.to_dict().get('schema', 'matrix/1')}`</sub>",
        "",
        "**2. query** — answered from the envelope digest, deterministic and exact:",
        "",
        "```",
        '$ hyperweave query tiers.svg "how many rows does this matrix have?"',
        f'→ {{"answer": "{q_rows.answer}", "field": "{q_rows.field}",'
        f' "mechanism": "{q_rows.mechanism}", "confidence": "{q_rows.confidence}"}}',
        '$ hyperweave query tiers.svg "what is the title?"',
        f'→ {{"answer": "{q_title.answer}", "field": "{q_title.field}"}}',
        "```",
        "",
        "**3. transform** — patch the `chromatic · motion` row's *Naked* cell"
        " `off → on` (RFC-6902 on the payload), yielding a NEW artifact:",
        "",
        "```json",
        _json.dumps(patch),
        "```",
        "",
        f"![Chain A transformed matrix]({rel}/chainA-2-child.svg)",
        "",
        f"<sub>parent `{_short_id(parent_env)}` → child `{_short_id(t.envelope)}`"
        f" · lineage depth {len(t.lineage)}</sub>",
        "",
        "The two renders side by side ARE the proof: the third row's first dot fills"
        " in the child. The change is content-addressed — a different payload hashes"
        " to a different id.",
        "",
        "**4. diff** — the structured delta (payload-bound, not pixel diffing):",
        "",
        "```json",
        _json.dumps(d.to_dict(), indent=2)[:900],
        "```",
        "",
        "**5. verify** — both artifacts prove `id == sha256(payload)`:",
        "",
        "```",
        f'$ hyperweave verify parent.svg → {{"valid": {str(vp.to_dict()["valid"]).lower()},'
        f' "schema": "{vp.to_dict().get("schema", "")}"}}',
        f'$ hyperweave verify child.svg  → {{"valid": {str(vc.to_dict()["valid"]).lower()},'
        f' "schema": "{vc.to_dict().get("schema", "")}"}}',
        "```",
        "",
        "---",
    ]

    # ══ Chain B — diagram evolution ══════════════════════════════════════════
    # A real DAG (explicit nodes + edges) so adding a node + wiring an edge is a
    # genuine structural edit the layout solver must re-rank on recompose.
    dag = _json.loads((Path("tests/fixtures/diagram/dag.json")).read_text())
    dia_parent_svg = _compose("diagram", "primer", variant="porcelain", diagram=dag)
    dia_parent_env = extract_envelope(dia_parent_svg) or {}
    if dia_parent_env.get("id"):
        store_artifact(str(dia_parent_env["id"]), dia_parent_svg)
    _write(out_dir / "chainB-1-pipeline.svg", dia_parent_svg)

    # transform — append a node and wire an edge into it. For diagram/1 the patch
    # is relative to the spec, so nodes/edges grow directly; the solver re-runs.
    last_id = dag["nodes"][-1].get("id") or f"n{len(dag['nodes']) - 1}"
    dia_patch = [
        {"op": "add", "path": "/nodes/-", "value": {"id": "audit", "label": "Audit"}},
        {"op": "add", "path": "/edges/-", "value": {"source": last_id, "target": "audit"}},
    ]
    dt = transform(dia_parent_svg, dia_patch)
    dia_child_svg = dt.svg
    _write(out_dir / "chainB-2-evolved.svg", dia_child_svg)

    # extract markdown shadow — the plain-text projection shown next to the render.
    md_shadow = extract(dia_child_svg, respond="markdown").to_dict().get("markdown", "")
    child_env_excerpt = _json.dumps(dt.envelope, indent=2)

    lines += [
        "",
        "## Chain B — diagram evolution",
        "",
        "*compose → transform (add node + edge) → extract markdown shadow.* An agent"
        " grows a topology by patching its structure, then reads back the text shadow"
        " an LLM would consume instead of the pixels.",
        "",
        "**1. compose** — a real DAG (7 nodes, 7 edges; `tests/fixtures/diagram/dag.json`):",
        "",
        f"<sub>`primer.porcelain | plate | {dag['topology']} — {dag['subtitle']}`</sub>",
        "",
        f"![Chain B source DAG]({rel}/chainB-1-pipeline.svg)",
        "",
        "**2. transform** — append an `Audit` node and an edge into it:",
        "",
        "```json",
        _json.dumps(dia_patch, indent=2),
        "```",
        "",
        f"<sub>`primer.porcelain | plate | {dag['topology']} — the same graph, an Audit node"
        f" and its edge appended` · parent `{_short_id(dia_parent_env)}` →"
        f" child `{_short_id(dt.envelope)}`"
        f" · the solver re-ran; the new terminal node and its edge appear</sub>",
        "",
        f"![Chain B evolved pipeline]({rel}/chainB-2-evolved.svg)",
        "",
        "**3. extract** — the evolved diagram's markdown shadow (what an agent reads"
        " instead of the SVG), shown next to the render above:",
        "",
        "```",
        md_shadow.strip()[:600],
        "```",
        "",
        "The envelope excerpt — the ~200-token actionable digest the child carries:",
        "",
        "```json",
        child_env_excerpt[:700],
        "```",
        "",
        "---",
    ]

    # ══ Chain D — promotion under the verb algebra ═══════════════════════════
    # The cyclic-dag promotion proven THROUGH the verbs: the payload
    # keeps the caller's declared topology, the envelope carries the rendered
    # pattern, and a transform that removes the cycle un-promotes the child —
    # the seam is a pure function of the spec, reversible by patch.
    from hyperweave.compose.engine import compose as _engine_compose
    from hyperweave.core.models import ComposeSpec as _CS

    # The preset library is the kit prototypes only, so the cyclic-dag
    # promotion demo carries its own inline spec (a release train: a flake
    # self-loop at index 1 and a requeue back-edge at index 4).
    train = {
        "topology": "dag",
        "title": "Release train",
        "subtitle": "a flake self-loop and a requeue cycle promote the declared dag",
        "nodes": [
            {"id": "build", "label": "build"},
            {"id": "test", "label": "test"},
            {"id": "stage", "label": "stage"},
            {"id": "ship", "label": "ship", "role": "hero"},
        ],
        "edges": [
            {"source": "build", "target": "test"},
            {"source": "test", "target": "test", "label": "flake"},
            {"source": "test", "target": "stage"},
            {"source": "stage", "target": "ship"},
            {"source": "ship", "target": "build", "label": "requeue"},
        ],
    }
    train_result = _engine_compose(_CS(type="diagram", genome_id="primer", variant="porcelain", diagram=train))
    train_svg = train_result.svg
    train_env = extract_envelope(train_svg) or {}
    if train_env.get("id"):
        store_artifact(str(train_env["id"]), train_svg)
    _write(out_dir / "chainD-1-promoted.svg", train_svg)
    train_payload = extract(train_svg, respond="payload").to_dict().get("payload", {})
    train_spec_topology = str(train_payload.get("spec", {}).get("topology", ""))
    train_pattern = str((train_env.get("data") or {}).get("pattern", "?"))

    # Remove the requeue back-edge (index 4) THEN the flake self-loop (index 1)
    # — both cycles gone, the same declared dag now renders as a dag.
    unpromote_patch = [{"op": "remove", "path": "/edges/4"}, {"op": "remove", "path": "/edges/1"}]
    ut = transform(train_svg, unpromote_patch)
    _write(out_dir / "chainD-2-unpromoted.svg", ut.svg)
    child_env = ut.envelope
    child_pattern = str((child_env.get("data") or {}).get("pattern", "?"))
    ud = diff(train_svg, ut.svg)

    lines += [
        "",
        "## Chain D — promotion, proven through the verbs",
        "",
        "*compose (cyclic dag) → extract → transform (remove the cycle) → diff.*"
        " The release-train spec declares `topology: dag`, but its flake self-loop and"
        " revert cycle have no rank — the input seam promotes it to state-machine"
        " with a warning. The verbs make the whole mechanism legible:",
        "",
        "**1. compose** — the declared dag renders as a state machine:",
        "",
        f"<sub>`primer.porcelain | plate | {train_pattern} — a flake self-loop and requeue cycle"
        f" promote the declared dag` · `{_short_id(train_env)}` ·"
        f" warning: `{'; '.join(train_result.warnings) or '(none)'}`</sub>",
        "",
        f"![Chain D promoted release train]({rel}/chainD-1-promoted.svg)",
        "",
        "**2. extract** — the payload keeps the CALLER's declaration; the envelope"
        " carries the RENDERED pattern (declared vs rendered never silently merge):",
        "",
        "```",
        f"payload spec.topology  → {train_spec_topology!r}   (the caller's dag, preserved)",
        f"envelope data.pattern  → {train_pattern!r}   (what actually rendered)",
        "```",
        "",
        "**3. transform** — remove the two cycle-closing edges; the SAME declared"
        " topology now renders as a plain dag (no promotion, no warning):",
        "",
        "```json",
        _json.dumps(unpromote_patch),
        "```",
        "",
        f"<sub>`primer.porcelain | plate | {child_pattern} — cycle edges removed, no promotion` ·"
        f" parent `{_short_id(train_env)}` → child `{_short_id(child_env)}` ·"
        f" child pattern `{child_pattern}` — promotion is a pure"
        " function of the spec, reversible by patch</sub>",
        "",
        f"![Chain D un-promoted release train]({rel}/chainD-2-unpromoted.svg)",
        "",
        "**4. diff** — the structured delta names exactly the removed edges:",
        "",
        "```json",
        _json.dumps(ud.to_dict(), indent=2)[:700],
        "```",
        "",
        "---",
    ]

    # ══ Chain C — cross-surface byte-equality ════════════════════════════════
    # The SAME spec composed through the CLI (subprocess) and HTTP (in-process
    # ASGI); the embedded envelope ids must match byte-for-byte (Invariant 9).
    c_lines = _emit_verb_chain_c(out_dir, rel)
    lines += c_lines

    lines += _verb_appendix()

    _write(VERBS_ROOT / "README.md", "\n".join(lines) + "\n")
    print(f"  verb proofset: {len(list(out_dir.glob('*.svg')))} artifacts + README.md")


def _emit_verb_chain_c(out_dir: Path, rel: str) -> list[str]:
    """Chain C — the same artifact through CLI then HTTP, digests proven equal.

    Runs `hyperweave compose` as a real subprocess and the HTTP compose handler
    in-process (ASGI), then extracts both envelope ids and asserts equality. The
    byte-equality is COMPUTED at generation time — if the surfaces diverged, this
    raises and the proofset build fails (the claim can't rot into stale prose).
    """
    import subprocess
    import sys as _sys

    from hyperweave.core.envelope import extract_envelope

    badge_args = ["badge", "STARS", "1234", "-g", "primer", "--variant", "porcelain"]

    # CLI surface — a real subprocess writing the SVG to stdout.
    cli_proc = subprocess.run(
        [_sys.executable, "-m", "hyperweave", "compose", *badge_args],
        capture_output=True,
        text=True,
        check=True,
    )
    cli_svg = cli_proc.stdout
    _write(out_dir / "chainC-cli.svg", cli_svg)
    cli_env = extract_envelope(cli_svg) or {}

    # HTTP surface — the in-process ASGI app, respond=svg (the image path).
    import asyncio

    from httpx import ASGITransport, AsyncClient

    from hyperweave.serve.app import app

    async def _http_compose() -> str:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://proofset") as client:
            resp = await client.post(
                "/v1/compose",
                json={"type": "badge", "title": "STARS", "value": "1234", "genome": "primer", "variant": "porcelain"},
            )
            resp.raise_for_status()
            return resp.text

    http_svg = asyncio.run(_http_compose())
    _write(out_dir / "chainC-http.svg", http_svg)
    http_env = extract_envelope(http_svg) or {}

    cli_id = str(cli_env.get("id", ""))
    http_id = str(http_env.get("id", ""))
    # Fail the build if the surfaces diverge — the parity claim is computed, not asserted in prose.
    if not cli_id or cli_id != http_id:
        raise AssertionError(f"cross-surface digest divergence: CLI {cli_id!r} != HTTP {http_id!r}")

    short = f"sha256:{cli_id.split(':', 1)[-1][:12]}…"
    return [
        "",
        "## Chain C — cross-surface identity",
        "",
        "*the same spec, composed through the CLI then HTTP.* The content-addressed"
        " envelope id is computed at generation time on both surfaces and asserted"
        " equal — if they diverged, this doc would fail to build. Parity is proven,"
        " not claimed.",
        "",
        "```",
        "# CLI (subprocess)",
        f"$ hyperweave compose {' '.join(badge_args)} > cli.svg",
        "",
        "# HTTP (POST /v1/compose)",
        '$ curl -s .../v1/compose -d \'{"type":"badge","title":"STARS",'
        '"value":"1234","genome":"primer","variant":"porcelain"}\' > http.svg',
        "```",
        "",
        "| surface | rendered | envelope id |",
        "| --- | --- | --- |",
        f"| CLI | ![CLI]({rel}/chainC-cli.svg) | `{short}` |",
        f"| HTTP | ![HTTP]({rel}/chainC-http.svg) | `{short}` |",
        "",
        f"Both surfaces produced the identical id `{short}` — same input, same"
        " content, same address. The pixels are the same artifact; the digest proves"
        " it without a byte-by-byte compare.",
        "",
        "---",
    ]
