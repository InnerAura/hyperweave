"""The dag family exhibit — `outputs/diagrams/topologies/dag/`.

First consumer of the per-family gallery seam. `outputs/` is gitignored, so
THIS module is the committed deliverable: the README is composed, never
hand-written, and every artifact in it is a live engine render.

Six sections, in the order a reader needs them:

1. **Specimens** — each hand file beside the engine's render of the same graph.
2. **The axis grid** — every cell the engine can produce: flow x region, with
   the 1,N,1 and asymmetric shapes side by side, so "compose across the axes"
   is visible rather than asserted.
3. **Real scenarios** — HyperWeave's own graphs, every one checkable against
   the tree (no invented systems, no invented numbers), with real brand glyphs.
4. **Capability edges** — gathers, skips, self-loops, rank pins, crowns,
   partition chroma, chip grammar, on BOTH flows.
5. **Boundaries** — cap refusals as rendered evidence plus their literal text.
6. **Gaps** — what the family cannot express, named.

Faces are baked porcelain light (`palette="fixed"`, `surface_face="light"`):
the viewer's theme cannot flip an exhibit.
"""

from __future__ import annotations

import pathlib
from typing import Any

from hyperweave.compose.engine import compose
from hyperweave.core.diagram import DiagramCapacityError, DiagramInputError
from scripts.examples.render import gallery_spec

_REPO = pathlib.Path(__file__).resolve().parents[3]
FAMILY = "dag"
"""The Topology value this exhibit reviews. The output directory, the
subcommand and every message derive from it — the family word is written
once, so a per-family tree can never disagree with the slug it exhibits."""

# The exhibit's DOCUMENT and its FIGURES live apart: the gallery root holds
# what there is to read, and every raw render sits under one renders/ roof.
_DIAGRAMS = _REPO / "outputs" / "diagrams"
OUT = _DIAGRAMS / "renders" / "topologies" / FAMILY
SPECIMEN_DIR = _REPO / "v04" / "v040" / "v043" / "diagram-prototypes" / "dag-expressions"

Exhibit = tuple[str, str, dict[str, Any]]
"""(slug, one-line what-it-shows, DiagramSpec dict)."""


# ── 0. dag vs fanout ─────────────────────────────────────────────────────────
# The question this exhibit gets asked most, answered with renders instead of
# prose: a 1->N graph is a fanout SHAPE and also a legal dag, so the word alone
# never settles it. What settles it is what each model can hold.

_SAME_CONTENT_NODES = [
    {"id": "src", "label": "Dispatcher", "desc": "route by kind", "role": "hero", "kind": "shuffle"},
    {"id": "w1", "label": "Images", "desc": "raster", "kind": "image"},
    {"id": "w2", "label": "Text", "desc": "extract", "kind": "file-text"},
    {"id": "w3", "label": "Audio", "desc": "transcribe", "kind": "mic"},
]


def _as_fanout() -> dict[str, Any]:
    """1->N declared as what it is. `fanout` DERIVES its edges from node order."""
    return {
        "title": "Declared as fanout",
        "subtitle": "1 to N, edges derived from order",
        "topology": "fanout",
        "node_style": "card+glyph",
        "nodes": [dict(n) for n in _SAME_CONTENT_NODES],
    }


def _as_dag_star() -> dict[str, Any]:
    """The same 1->N declared as a dag — legal, and the WRONG family for it."""
    return {
        "title": "The same graph as dag",
        "subtitle": "legal, but the wrong family word",
        "topology": "dag",
        "node_style": "card+glyph",
        "nodes": [dict(n) for n in _SAME_CONTENT_NODES],
        "edges": [{"source": "src", "target": f"w{i}"} for i in range(1, 4)],
    }


def _only_a_dag() -> dict[str, Any]:
    """One edge more than a fanout can hold — the reconvergence."""
    return {
        "title": "One edge fanout cannot hold",
        "subtitle": "the workers rejoin",
        "topology": "dag",
        "node_style": "card+glyph",
        "nodes": [
            *[dict(n) for n in _SAME_CONTENT_NODES],
            {"id": "idx", "label": "Index", "desc": "one manifest", "kind": "database"},
        ],
        "edges": [{"source": "src", "target": f"w{i}"} for i in range(1, 4)]
        + [{"source": f"w{i}", "target": "idx"} for i in range(1, 4)],
    }


# ── 1. Specimens ─────────────────────────────────────────────────────────────
# Each hand file's own graph, composed by the engine. The band specimen's
# constants are the chassis citation (rank_gap 166, member pitch 240); the
# render is what the engine makes of the same declaration.

_MAPREDUCE_NODES = [
    {"id": "orch", "label": "Orchestrator", "desc": "plan · dispatch ×3", "role": "hero", "kind": "git-branch"},  # noqa: RUF001 — kit typography (prime/multiplication), deliberate
    {"id": "web", "label": "Web researcher", "desc": "search · extract", "kind": "globe"},
    {"id": "data", "label": "Data analyst", "desc": "structured db", "kind": "database"},
    {"id": "code", "label": "Code sandbox", "desc": "python exec", "kind": "terminal"},
    {"id": "syn", "label": "Synthesis", "desc": "merge · report", "kind": "layers"},
]
_MAPREDUCE_EDGES = [
    {"source": "orch", "target": "web"},
    # The chip rides the STRAIGHT centre thread, at its midpoint, with equal
    # wire either side — the specimen's own seating (chip centre 440,241 on a
    # thread running 148 -> 334). A chip on a curved flank has no such balance.
    {"source": "orch", "target": "data", "label": "map ×3", "label_style": "chip"},  # noqa: RUF001 — kit typography (prime/multiplication), deliberate
    {"source": "orch", "target": "code"},
    {"source": "web", "target": "syn"},
    {"source": "data", "target": "syn", "label": "reduce", "label_style": "chip"},
    {"source": "code", "target": "syn"},
]


def _mapreduce(orientation: str | None, region_kind: str | None) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "title": "Map-reduce plan",
        "subtitle": "orchestrator fans to three workers and reconverges",
        "topology": "dag",
        "nodes": [dict(n) for n in _MAPREDUCE_NODES],
        "edges": [dict(e) for e in _MAPREDUCE_EDGES],
    }
    if orientation:
        spec["orientation"] = orientation
    if region_kind:
        spec["regions"] = [{"label": "Parallel map space", "members": ["web", "data", "code"], "kind": region_kind}]
    return spec


SPECIMENS: list[tuple[str, str, str, dict[str, Any]]] = [
    (
        "dag-vertical-mapreduce-band",
        "dag-vertical-mapreduce-band.svg",
        "The vertical hourglass with a filled band on the middle rank — the chassis' constant source.",
        _mapreduce("vertical", "band"),
    ),
    (
        "dag-vertical-mapreduce-enclosure",
        "dag-vertical-mapreduce-enclosure.svg",
        "Same graph, same flow, dashed enclosure instead of a band — one axis value apart.",
        _mapreduce("vertical", "enclosure"),
    ),
    (
        "dag-mapreduce-enclosure",
        "dag-mapreduce-enclosure.svg",
        "The same declaration flowing right. Symmetry is emergent here too — nothing declares it.",
        _mapreduce(None, "enclosure"),
    ),
]


# ── 2. The axis grid ─────────────────────────────────────────────────────────
# flow x region x shape. The point of the section: one declaration changes one
# axis value and the artifact changes accordingly, with no new topology word.

_BRANCH_NODES = [
    {"id": "push", "label": "Push", "desc": "commit lands", "kind": "git-commit-horizontal"},
    {"id": "build", "label": "Build", "desc": "compile · package", "kind": "package"},
    {"id": "checks", "label": "Checks", "desc": "tests · lint · types", "kind": "circle-check"},
    {"id": "fix", "label": "Fix forward", "desc": "patch · re-run", "kind": "wrench"},
    {"id": "deploy", "label": "Deploy", "desc": "ship it", "role": "hero", "kind": "rocket"},
]
_BRANCH_EDGES = [
    {"source": "push", "target": "build"},
    {"source": "build", "target": "checks"},
    {"source": "checks", "target": "deploy", "label": "pass", "label_style": "chip"},
    {"source": "checks", "target": "fix", "label": "fail", "label_style": "chip"},
    {"source": "fix", "target": "deploy"},
]


def _branch(orientation: str | None) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "title": "Branch and reconverge",
        "subtitle": "a decision that rejoins — the shape a rooted tree cannot hold",
        "topology": "dag",
        "nodes": [dict(n) for n in _BRANCH_NODES],
        "edges": [dict(e) for e in _BRANCH_EDGES],
    }
    if orientation:
        spec["orientation"] = orientation
    return spec


def _axis_grid() -> list[Exhibit]:
    grid: list[Exhibit] = []
    for flow, word in (("horizontal", "flowing right"), ("vertical", "flowing down")):
        orientation = None if flow == "horizontal" else flow
        grid.append(
            (
                f"grid-{flow}-symmetric-none",
                f"1,N,1 {word}, no region — symmetry emerges from rank sizes and centering.",
                _mapreduce(orientation, None),
            )
        )
        for kind in ("band", "enclosure"):
            grid.append(
                (
                    f"grid-{flow}-symmetric-{kind}",
                    f"1,N,1 {word}, {kind} on the middle rank.",
                    _mapreduce(orientation, kind),
                )
            )
        grid.append(
            (
                f"grid-{flow}-asymmetric",
                f"Branching and reconverging {word} — the common flowchart shape.",
                _branch(orientation),
            )
        )
    return grid


# ── 3. Real scenarios ────────────────────────────────────────────────────────
# Every graph below is HyperWeave's own structure and is checkable against the
# tree. No invented systems, no invented metrics. Provenance is stated per
# exhibit in the README so a reader can verify rather than trust.

_SCENARIOS: list[tuple[str, str, str, dict[str, Any]]] = [
    (
        "real-compose-pipeline",
        "src/hyperweave/compose/engine.py + compose/resolvers/",
        "How a request becomes an artifact. Every node is a module in the tree.",
        {
            "title": "Compose pipeline",
            "subtitle": "ComposeSpec to bytes",
            "topology": "dag",
            "orientation": "vertical",
            "nodes": [
                {"id": "spec", "label": "ComposeSpec", "desc": "validated IR", "role": "hero", "kind": "braces"},
                {"id": "resolver", "label": "Resolver", "desc": "frame context", "kind": "component"},
                {"id": "layout", "label": "Solver", "desc": "geometry only", "kind": "frame"},
                {"id": "tmpl", "label": "Jinja template", "desc": "all SVG lives here", "kind": "file-code"},
                {"id": "svg", "label": "Artifact", "desc": "self-contained SVG", "kind": "image"},
            ],
            "edges": [
                {"source": "spec", "target": "resolver"},
                {"source": "resolver", "target": "layout", "label": "no SVG", "label_style": "chip"},
                {"source": "layout", "target": "tmpl"},
                {"source": "tmpl", "target": "svg"},
            ],
        },
    ),
    (
        "real-surface-parity",
        "src/hyperweave/surfaces/capabilities.py (Invariant 9)",
        "One capability registry, three thin adapters — the invariant drawn as a graph.",
        {
            "title": "Surface parity",
            "subtitle": "one registry, three adapters",
            "topology": "dag",
            "nodes": [
                {"id": "cli", "label": "CLI", "desc": "typer", "kind": "terminal"},
                {"id": "http", "label": "HTTP", "desc": "fastapi", "kind": "router"},
                {"id": "mcp", "label": "MCP", "desc": "fastmcp", "glyph": "anthropic"},
                {
                    "id": "caps",
                    "label": "Capability registry",
                    "desc": "one source of truth",
                    "role": "hero",
                    "kind": "boxes",
                    "gather": True,
                },
                {"id": "frames", "label": "Frames", "desc": "diagram · matrix · badge", "kind": "layers"},
            ],
            "edges": [
                {"source": "cli", "target": "caps"},
                {"source": "http", "target": "caps"},
                {"source": "mcp", "target": "caps", "label": "parity", "label_style": "chip"},
                {"source": "caps", "target": "frames"},
            ],
            "regions": [{"label": "Adapters", "members": ["cli", "http", "mcp"], "kind": "enclosure"}],
        },
    ),
    (
        "real-telemetry-receipt",
        "src/hyperweave/telemetry/runtimes/ + compose/resolvers/receipt.py",
        "The two runtimes that actually ship a registry today, through to a receipt.",
        {
            "title": "Session receipt",
            "subtitle": "transcript to artifact",
            "topology": "dag",
            "orientation": "vertical",
            "nodes": [
                {"id": "cc", "label": "Claude Code", "desc": "JSONL transcript", "glyph": "claudecode"},
                {"id": "cx", "label": "Codex", "desc": "JSONL transcript", "glyph": "openai"},
                {
                    "id": "registry",
                    "label": "Runtime registry",
                    "desc": "YAML drop-in per runtime",
                    "role": "hero",
                    "kind": "boxes",
                    "gather": True,
                },
                {"id": "receipt", "label": "Receipt", "desc": "eight pinned zones", "kind": "file-text"},
            ],
            "edges": [
                {"source": "cc", "target": "registry"},
                {"source": "cx", "target": "registry", "label": "detect", "label_style": "chip"},
                {"source": "registry", "target": "receipt"},
            ],
        },
    ),
    (
        "real-ci-gate",
        "the repo's own gate: pytest + ruff check + ruff format --check + ty",
        "The four-command gate, with the real tools. Every check must pass to tag.",
        {
            "title": "Release gate",
            "subtitle": "four commands, all green",
            "topology": "dag",
            "nodes": [
                {"id": "push", "label": "Push", "desc": "branch lands", "glyph": "github"},
                {"id": "tests", "label": "pytest", "desc": "unit + guards", "kind": "shield-check"},
                {"id": "lint", "label": "ruff", "desc": "check + format", "kind": "sparkle"},
                {"id": "types", "label": "ty", "desc": "strict", "glyph": "python"},
                {
                    "id": "tag",
                    "label": "Tag",
                    "desc": "annotated, follow-tags",
                    "role": "hero",
                    "kind": "flag",
                    "gather": True,
                },
            ],
            "edges": [
                {"source": "push", "target": "tests"},
                {"source": "push", "target": "lint"},
                {"source": "push", "target": "types"},
                {"source": "tests", "target": "tag"},
                {"source": "lint", "target": "tag"},
                {"source": "types", "target": "tag", "label": "all green", "label_style": "chip"},
            ],
            "regions": [{"label": "The gate", "members": ["tests", "lint", "types"], "kind": "band"}],
        },
    ),
]


# Graphs whose attach points are not settled yet: a detour edge and a plain
# edge share one face at one point, so the wires fuse where they land. Measured
# on BOTH flows in each case, which is what rules the axis out as the cause.
# The law that parts them is composition — how far outboard a detour sits,
# which way, and what two detours sharing a face do — and it waits on a hand
# specimen rather than being settled by eye.
UNSETTLED = {"monorepo-build-graph", "rag-index-and-query", "request-to-pod"}


# ── 3b. The shipped corpus, both flows ───────────────────────────────────────
# The 19 dag stories already in README_TOPOLOGIES.md are the real corpus: hand
# composed, brand-marked, and considerably richer than anything written for this
# exhibit. This section is what v0.4.3 MEANS for them — each one renders
# unchanged on its own flow and gains a second one for free, or refuses for a
# reason worth reading.


def _corpus_stories() -> list[tuple[str, dict[str, Any]]]:
    """The shipped dag stories, imported rather than re-invented."""
    import sys

    sys.path.insert(0, str(_REPO / "scripts"))
    from scripts.examples.diagrams import SECTIONS

    for topo, stories in SECTIONS:
        if topo == "dag":
            return [(slug, spec) for slug, _src, spec in stories]
    return []


# ── 4. Capability edges ──────────────────────────────────────────────────────


def _capabilities() -> list[Exhibit]:
    out: list[Exhibit] = []
    for flow in ("horizontal", "vertical"):
        orientation = None if flow == "horizontal" else flow
        base: dict[str, Any] = {"topology": "dag"}
        if orientation:
            base["orientation"] = orientation

        out.append(
            (
                f"cap-{flow}-crown",
                "A hero crown beside standard cards — dominance is bounded, not unlimited.",
                {
                    **base,
                    "title": "Hero crown",
                    "subtitle": "one focal card, bounded growth",
                    "nodes": [
                        {"id": "a", "label": "Ingest", "desc": "raw events", "kind": "download"},
                        {
                            "id": "b",
                            "label": "Decision engine",
                            "desc": "policy · scoring · routing",
                            "role": "hero",
                            "kind": "cpu",
                        },
                        {"id": "c", "label": "Emit", "desc": "downstream", "kind": "upload"},
                    ],
                    "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
                },
            )
        )
        # A self-loop promotes the graph to state-machine at the input seam, and
        # state-machine has no vertical cell — so this device exhibits on the
        # horizontal flow only. The interaction is documented under Boundaries
        # rather than hidden.
        if flow == "horizontal":
            out.append(
                (
                    f"cap-{flow}-selfloop",
                    "A revise-in-place self-loop — the arc bows out of the content band.",
                    {
                        **base,
                        "title": "Revise in place",
                        "subtitle": "a self-loop is its own arc",
                        "nodes": [
                            {"id": "draft", "label": "Draft", "desc": "first pass", "kind": "file-text"},
                            {"id": "review", "label": "Review", "desc": "critique", "kind": "eye"},
                            {"id": "ship", "label": "Ship", "desc": "publish", "kind": "rocket"},
                        ],
                        "edges": [
                            {"source": "draft", "target": "review"},
                            {"source": "review", "target": "review", "label": "revise", "label_style": "chip"},
                            {"source": "review", "target": "ship"},
                        ],
                    },
                )
            )
        out.append(
            (
                f"cap-{flow}-gather",
                "A declared gather: arrivals collapse at a knot and one trunk carries them home.",
                {
                    **base,
                    "title": "AND-join",
                    "subtitle": "a gather knots its arrivals",
                    "nodes": [
                        {"id": "a", "label": "Schema", "desc": "types", "kind": "braces"},
                        {"id": "b", "label": "Fixtures", "desc": "corpus", "kind": "database"},
                        {"id": "c", "label": "Config", "desc": "YAML", "kind": "settings"},
                        {
                            "id": "j",
                            "label": "Build",
                            "desc": "all inputs required",
                            "role": "hero",
                            "kind": "package",
                            "gather": True,
                        },
                    ],
                    "edges": [
                        {"source": "a", "target": "j"},
                        {"source": "b", "target": "j", "label": "join", "label_style": "chip"},
                        {"source": "c", "target": "j"},
                    ],
                },
            )
        )
        out.append(
            (
                f"cap-{flow}-skip",
                "A rank-skipping edge rides its own channel outside the content band, "
                "chip on the run — never a wire cutting across the cards.",
                {
                    **base,
                    "title": "Rank-skip channel",
                    "subtitle": "a long edge takes the channel, not the shortcut",
                    "nodes": [
                        {"id": "a", "label": "Parse", "desc": "tokens", "kind": "braces"},
                        {"id": "b", "label": "Resolve", "desc": "bindings", "kind": "link"},
                        {"id": "c", "label": "Solve", "desc": "geometry", "kind": "frame"},
                        {"id": "d", "label": "Emit", "desc": "bytes", "kind": "file-code"},
                    ],
                    "edges": [
                        {"source": "a", "target": "b"},
                        {"source": "b", "target": "c"},
                        {"source": "c", "target": "d"},
                        {"source": "a", "target": "d", "label": "cached", "label_style": "chip"},
                    ],
                },
            )
        )
        out.append(
            (
                f"cap-{flow}-wide",
                "The widest lawful rank, reconverged — a graph `fanout` cannot hold, because it "
                "derives its edges from one source and has nowhere to put the second half.",
                {
                    **base,
                    "title": "Wide rank",
                    "subtitle": "four abreast, one crown",
                    "nodes": [
                        {
                            "id": "src",
                            "label": "Dispatcher",
                            "desc": "route by kind",
                            "role": "hero",
                            "kind": "shuffle",
                        },
                        {"id": "w1", "label": "Images", "desc": "raster", "kind": "image"},
                        {"id": "w2", "label": "Text", "desc": "extract", "kind": "file-text"},
                        {"id": "w3", "label": "Audio", "desc": "transcribe", "kind": "mic"},
                        {"id": "w4", "label": "Video", "desc": "keyframes", "kind": "play"},
                        {"id": "idx", "label": "Index", "desc": "one manifest", "kind": "database"},
                    ],
                    "edges": [{"source": "src", "target": f"w{i}"} for i in range(1, 5)]
                    + [{"source": f"w{i}", "target": "idx"} for i in range(1, 5)],
                    "regions": [{"label": "Workers", "members": ["w1", "w2", "w3", "w4"], "kind": "band"}],
                },
            )
        )
    return out


# ── 5. Boundaries ────────────────────────────────────────────────────────────
# Refusals are exhibited as TEXT (there is no artifact to show — that is the
# point), each produced by actually calling compose and catching the error.


def _rank_chain(n: int, orientation: str | None) -> dict[str, Any]:
    """An n-rank probe that BRANCHES at every other rank.

    A straight n-node chain would hit the same cap, but it renders as a
    pipeline — and a reader cannot tell a linear dag from one. Widening the
    odd ranks keeps the probe unmistakably a dag while the rank COUNT (what
    the cap measures) stays exactly n."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    prev: list[str] = []
    for i in range(n):
        wide = i % 2 == 1 and i != n - 1
        ids = [f"r{i}a", f"r{i}b"] if wide else [f"r{i}"]
        for k, nid in enumerate(ids):
            nodes.append({"id": nid, "label": f"Stage {i}{'ab'[k] if wide else ''}", "desc": "step"})
        edges += [{"source": q, "target": nid} for q in prev for nid in ids]
        prev = ids
    spec: dict[str, Any] = {
        "title": f"{n} ranks",
        "subtitle": "cap probe",
        "topology": "dag",
        "nodes": nodes,
        "edges": edges,
    }
    if orientation:
        spec["orientation"] = orientation
    return spec


def _wide_rank(k: int, orientation: str | None) -> dict[str, Any]:
    """A k-wide RANK, reconverged.

    A bare 1->k star would hit the same cap, but it is a fanout shape and reads
    as one — the family word would be doing all the work. Adding the join makes
    it a graph only `dag` can hold (fanout derives edges from one source and
    cannot carry the second half), so the probe demonstrates its own family
    while the per-rank COUNT the cap measures stays exactly k."""
    spec: dict[str, Any] = {
        "title": f"{k} per rank",
        "subtitle": "cap probe",
        "topology": "dag",
        "node_style": "card+glyph",
        "nodes": [
            {"id": "src", "label": "Shard", "desc": "split by key", "kind": "shuffle"},
            *[{"id": f"w{i}", "label": f"Worker {i}", "desc": "task", "kind": "cpu"} for i in range(k)],
            {"id": "sink", "label": "Merge", "desc": "reassemble", "role": "hero", "kind": "layers"},
        ],
        "edges": [{"source": "src", "target": f"w{i}"} for i in range(k)]
        + [{"source": f"w{i}", "target": "sink"} for i in range(k)],
    }
    if orientation:
        spec["orientation"] = orientation
    return spec


def _long_labels(orientation: str | None) -> dict[str, Any]:
    """The legibility tail: long labels widen cards, which is what actually
    drives the display scale down — not the node count."""
    spec: dict[str, Any] = {
        "title": "Long labels",
        "subtitle": "scale is a property of content, not of a count",
        "topology": "dag",
        "nodes": [
            {"id": "a", "label": "Ingestion and normalization", "desc": "schema inference across sources"},
            {"id": "b", "label": "Deduplication and enrichment", "desc": "entity resolution pass"},
            {"id": "c", "label": "Aggregation and rollup", "desc": "windowed materialization"},
            {"id": "d", "label": "Publication and notification", "desc": "downstream fan-out"},
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
            {"source": "c", "target": "d"},
        ],
    }
    if orientation:
        spec["orientation"] = orientation
    return spec


def _hostile() -> dict[str, Any]:
    """Invariant 14: raw text never breaks entity or tag syntax."""
    return {
        "title": 'Ampersands & <angles> — "quoted"',
        "subtitle": "hostile label sweep",
        "topology": "dag",
        "orientation": "vertical",
        "nodes": [
            {"id": "a", "label": "A & B", "desc": "<not a tag>"},
            {"id": "b", "label": '"quoted"', "desc": "it's fine"},
            {"id": "c", "label": "x > y < z", "desc": "& more"},
        ],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}],
    }


# ── render + README ──────────────────────────────────────────────────────────


def _assert_tokens_resolve() -> None:
    """Every `glyph` / `kind` an exhibit declares must exist in the registry.

    A token that does not resolve renders a plain card with no mark — silently.
    The exhibit would still "pass" while the point it makes (real brand marks,
    never geometric substitutes) quietly stopped being true, so the gallery
    refuses to build instead."""
    import json

    from hyperweave.config.loader import load_glyphs

    brands = set(load_glyphs())
    core_path = _REPO / "src" / "hyperweave" / "data" / "registries" / "glyphs-core.json"
    core = {k for k in json.loads(core_path.read_text()) if not k.startswith("_")}
    unresolved: set[tuple[str, str]] = set()
    for spec in _all_specs():
        for node in spec.get("nodes", []):
            if node.get("glyph") and node["glyph"] not in brands:
                unresolved.add(("glyph", node["glyph"]))
            if node.get("kind") and node["kind"] not in core:
                unresolved.add(("kind", node["kind"]))
    if unresolved:
        listed = ", ".join(f"{k}:{v}" for k, v in sorted(unresolved))
        raise SystemExit(f"gallery_{FAMILY}: unresolved registry tokens — {listed}")


def _all_specs() -> list[dict[str, Any]]:
    return (
        [sp for _, _, _, sp in SPECIMENS]
        + [sp for _, _, sp in _axis_grid()]
        + [sp for _, _, _, sp in _SCENARIOS]
        + [sp for _, _, sp in _capabilities()]
    )


SECTION_DIRS = ("why", "specimens", "axis-grid", "scenarios", "corpus", "capabilities", "boundaries")


def _render(slug: str, spec: dict[str, Any], section: str) -> str:
    # The dag chassis has no glyph slot by default (unlike state-machine), so a
    # `kind`/`glyph` declaration renders nothing on a plain card. Every exhibit
    # here that names marks asks for the anatomy that can carry them.
    if "node_style" not in spec and any(n.get("kind") or n.get("glyph") for n in spec.get("nodes", [])):
        spec = {**spec, "node_style": "card+glyph"}
    svg = compose(
        gallery_spec(
            type="diagram",
            genome_id="primer",
            variant="porcelain",
            ground="bare",
            palette="fixed",
            surface_face="light",
            diagram=spec,
        )
    ).svg
    (OUT / section / f"{slug}.svg").write_text(svg)
    return svg


def _refusal(spec: dict[str, Any]) -> str:
    """Compose and return the refusal sentence — or flag a cap that did not
    bite, which is a finding, not a pass."""
    try:
        compose(
            gallery_spec(
                type="diagram",
                genome_id="primer",
                variant="porcelain",
                ground="bare",
                palette="fixed",
                surface_face="light",
                diagram=spec,
            )
        )
    except (DiagramCapacityError, DiagramInputError) as exc:
        return str(exc)
    except Exception as exc:
        return f"UNEXPECTED {type(exc).__name__}: {exc}"
    return "NO REFUSAL — the cap did not bite"


def _section(lines: list[str], title: str, blurb: str) -> None:
    lines += [f"## {title}", "", blurb, ""]


def _exhibit(lines: list[str], slug: str, what: str, spec: dict[str, Any], section: str, *, note: str = "") -> int:
    _render(slug, spec, section)
    lines += [f"#### `{slug}` — {spec.get('title', slug)}", "", what, ""]
    if note:
        lines += [f"*{note}*", ""]
    lines += [f"![{slug}](../renders/topologies/{FAMILY}/{section}/{slug}.svg)", ""]
    return 1


def _scale_of(svg: str) -> str:
    import re

    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    w = re.search(r'\bwidth="([\d.]+)"', svg)
    if not m or not w:
        return "?"
    return f"{float(w.group(1)) / float(m.group(1)):.3f}"


def build_dag() -> int:
    """Compose the dag family exhibit. Returns the artifact count."""
    _assert_tokens_resolve()
    OUT.mkdir(parents=True, exist_ok=True)

    for stale in OUT.glob("*.svg"):
        stale.unlink()  # flat-layout leftovers from before the sections existed
    for stale in OUT.glob("*.png"):
        stale.unlink()
    for sub in SECTION_DIRS:
        (OUT / sub).mkdir(exist_ok=True)
        for stale in (OUT / sub).glob("*.svg"):
            stale.unlink()  # a renamed exhibit must not leave its old render behind

    total = 0
    lines: list[str] = [
        "# dag — the layered family, every cell the engine can produce",
        "",
        "`dag` is the family whose edges ARE its content: node order carries no",
        "structure, so every relationship is declared. Its expression axis is",
        "**flow** — which screen axis the ranks advance along — and one solver",
        "serves both cells through an axis map.",
        "",
        "Symmetry is never declared anywhere below. Where a graph reads",
        "symmetric it is emergent, from rank sizes plus barycenter centering.",
        "",
        "Every artifact is a live engine render on the baked porcelain light",
        "face; nothing here is hand-drawn, and the viewer's theme cannot flip it.",
        "",
        "**Everything in this directory is `topology: dag`** — no other family",
        "appears. Some exhibits nonetheless *read* like a pipeline, and that is a",
        "true observation about the shapes rather than a mix-up: a dag whose",
        "every rank holds one node draws exactly like a linear chain. The",
        "difference is declarative, not visual — `pipeline` DERIVES its edges",
        "from node order, while `dag` requires every edge to be declared. Where a",
        "probe only needed a rank count, it branches anyway so the family stays",
        "legible.",
        "",
    ]

    _section(
        lines,
        "0 · Is this a dag or a fanout?",
        "The shapes overlap, so the render never settles it on its own — a 1->N "
        "graph is a fanout shape AND a legal dag. What settles it is what each "
        "model can HOLD.\n\n"
        "`fanout` **derives** its edges: `derive_edges` returns `(0, j)` for every "
        "j, so the graph is always exactly one source to N targets, always two "
        "ranks. Nothing else is expressible — there is no place to put a second "
        "rank or a rejoin.\n\n"
        "`dag` **requires** declared edges and accepts any acyclic graph: two to "
        "five ranks, skips, meshes, reconvergence.\n\n"
        "That difference is also why they are sized differently, which is the "
        "other half of the confusion. `fanout`'s chassis pins a **fixed 920 frame** "
        "(`width_floor: true`) because a 1->N graph is always the same shape, so "
        "the slack spreads into the fan and the channel opens to ~620px. `dag` "
        "declares **no width floor**, so a sparse dag hugs its own span and the "
        "same content renders at 454px with a 150px channel. Neither is wrong; "
        "a dag cannot pin a frame because it does not know its shape in advance.\n\n"
        "**Rule of thumb: if the graph is 1->N and nothing rejoins, it is a "
        "fanout — declaring it `dag` is using the wrong word for it.** Everything "
        "below this section is a graph fanout could not hold.",
    )
    total += _exhibit(lines, "why-as-fanout", "Three targets, one source, declared as what it is.", _as_fanout(), "why")
    total += _exhibit(
        lines,
        "why-as-dag-star",
        "Byte-for-byte the same GRAPH declared as a dag. Legal, tighter (no width "
        "floor), and the wrong family word — every edge had to be spelled out to "
        "say what the order already said.",
        _as_dag_star(),
        "why",
    )
    total += _exhibit(
        lines,
        "why-only-a-dag",
        "Add the rejoin and fanout is out of the running: its derived edge set has "
        "no second half. THIS is the family's own territory.",
        _only_a_dag(),
        "why",
    )

    _section(
        lines,
        "1 · Specimens",
        "The hand files that gated this family, each beside the engine's render of "
        "the same declaration. Metric deltas are expected and documented: pads come "
        "from config, not from the specimens (owner ruling 2026-08-21), so a band's "
        "leading pad reads +6px against the hand file — the engine's chip is 26 tall "
        "where the drawn one was 20.",
    )
    for slug, source, what, spec in SPECIMENS:
        note = f"hand file: `{source}`" if (SPECIMEN_DIR / source).exists() else f"hand file (renamed): `{source}`"
        total += _exhibit(lines, slug, what, spec, "specimens", note=note)

    _section(
        lines,
        "2 · The axis grid",
        "One declaration, one axis value changed at a time. No new topology word "
        "appears anywhere in this section — the family word stays `dag` and the "
        "`orientation` axis selects the cell.",
    )
    lines += ["| flow | shape | region | exhibit |", "| --- | --- | --- | --- |"]
    for slug, _what, spec in _axis_grid():
        flow = spec.get("orientation", "horizontal")
        shape = "branching" if slug.endswith("asymmetric") else "1,N,1"
        region = (spec.get("regions") or [{}])[0].get("kind", "none")
        lines.append(f"| {flow} | {shape} | {region} | [{slug}](../renders/topologies/{FAMILY}/axis-grid/{slug}.svg) |")
    lines.append("")
    for slug, what, spec in _axis_grid():
        total += _exhibit(lines, slug, what, spec, "axis-grid")

    _section(
        lines,
        "3 · Real scenarios",
        "Every graph here is HyperWeave's own structure, checkable against the tree. "
        "No invented systems and no invented numbers — each exhibit names where it "
        "comes from so a reader can verify rather than trust. Brand marks are real "
        "registry glyphs, never geometric substitutes.",
    )
    for slug, provenance, what, spec in _SCENARIOS:
        total += _exhibit(lines, slug, what, spec, "scenarios", note=f"source: `{provenance}`")

    corpus = _corpus_stories()
    _section(
        lines,
        "3b · Every dag graph in the tree",
        f"The remaining {len(corpus)} dag graphs the engine holds, each on both "
        "flows. This is inventory, not an appendix: the point of this directory is "
        "to review **every dag HyperWeave can produce**, so nothing gets to sit "
        "outside it. These graphs currently also feed the flat "
        "`README_TOPOLOGIES.md`, which this per-family tree is the start of "
        "replacing.\n\n"
        "Both flows are rendered for each because the family has two cells and a "
        "review that showed one would be a review of half the family. Where a "
        "graph refuses on a flow the reason is printed — a refusal is coverage "
        "information, not an omission.\n\n"
        f"**{len(UNSETTLED)} graphs are marked unsettled and are not review-ready.** "
        "In each, a detour edge and a plain edge land on one face at one point, so "
        "the two wires fuse where they attach. It is not an axis defect — the same "
        "graphs fuse on **both** flows — and the law that parts them settles how far "
        "outboard a detour sits and what happens when two share a face, which is "
        "composition with no reference yet. They stay in the inventory because the "
        "point of this directory is that nothing sits outside it; they are labelled "
        "so the exhibit stops presenting unfinished work as finished.",
    )
    lines += ["| story | authored | other flow |", "| --- | --- | --- |"]
    corpus_rows: list[tuple[str, str, str]] = []
    for slug, spec in corpus:
        authored = str(spec.get("orientation") or "horizontal")
        other = "vertical" if authored == "horizontal" else "horizontal"
        flipped = (
            {**spec, "orientation": other}
            if other == "vertical"
            else {k: v for k, v in spec.items() if k != "orientation"}
        )
        try:
            _render(f"corpus-{slug}-{authored}", spec, "corpus")
            total += 1
            a_cell = f"[{authored}](../renders/topologies/{FAMILY}/corpus/corpus-{slug}-{authored}.svg)"
        except Exception as exc:
            a_cell = f"refuses — {type(exc).__name__}"
        try:
            _render(f"corpus-{slug}-{other}", flipped, "corpus")
            total += 1
            o_cell = f"[{other}](../renders/topologies/{FAMILY}/corpus/corpus-{slug}-{other}.svg)"
        except Exception as exc:
            o_cell = f"refuses — `{str(exc).split(chr(10))[0][:90]}`"
        corpus_rows.append((slug, a_cell, o_cell))
        mark = " ⚠ unsettled" if slug in UNSETTLED else ""
        lines.append(f"| `{slug}`{mark} | {a_cell} | {o_cell} |")
    flipped_ok = sum(1 for _s, _a, o in corpus_rows if o.startswith("["))
    lines += [
        "",
        f"**{flipped_ok} of {len(corpus_rows)} compose on the second flow with no edit to their declaration.**",
        "",
        "Every one of them, rendered — a review that only linked its subjects",
        "would not be a review:",
        "",
    ]
    for slug, spec in corpus:
        authored = str(spec.get("orientation") or "horizontal")
        other = "vertical" if authored == "horizontal" else "horizontal"
        lines += [f"#### `{slug}` — {spec.get('title') or slug}", ""]
        if spec.get("subtitle"):
            lines += [str(spec["subtitle"]), ""]
        if slug in UNSETTLED:
            lines += [
                "> **Unsettled — not review-ready.** A detour edge and a plain edge attach at "
                "one point on one face, so the two wires fuse where they land. Present on "
                "both flows, so the axis is not the cause; the law that parts them is "
                "composition and waits on a specimen.",
                "",
            ]
        row = next(r for r in corpus_rows if r[0] == slug)
        for flow, cell in ((authored, row[1]), (other, row[2])):
            if (OUT / "corpus" / f"corpus-{slug}-{flow}.svg").exists():
                lines += [
                    f"*{flow}*",
                    "",
                    f"![corpus-{slug}-{flow}](../renders/topologies/{FAMILY}/corpus/corpus-{slug}-{flow}.svg)",
                    "",
                ]
            else:
                lines += [f"*{flow}* — {cell}", ""]

    _section(
        lines,
        "4 · Capability edges",
        "The devices the family owns, exercised on BOTH flows so the axis is shown "
        "to carry them rather than asserted to.",
    )
    for slug, what, spec in _capabilities():
        total += _exhibit(lines, slug, what, spec, "capabilities")

    _section(
        lines,
        "5 · Boundaries",
        "Caps are refusal contracts. Here is each one at its edge — the last "
        "artifact that composes, then the literal sentence the next one gets. "
        "Legibility is separate: the display scale is a function of canvas WIDTH "
        "(`scale = min(0.8043, 740 / width)`), so it tracks content, not counts.",
    )
    for flow in ("horizontal", "vertical"):
        orientation = None if flow == "horizontal" else flow
        lines += [f"### {flow}", ""]
        total += _exhibit(
            lines,
            f"bound-{flow}-ranks-5",
            "Five ranks — the cap, and the last one that composes.",
            _rank_chain(5, orientation),
            "boundaries",
        )
        lines += ["Six ranks refuses:", "", "```", _refusal(_rank_chain(6, orientation)), "```", ""]
        total += _exhibit(
            lines,
            f"bound-{flow}-per-rank-4",
            "Four members on one rank — the cap.",
            _wide_rank(4, orientation),
            "boundaries",
        )
        lines += ["Five refuses:", "", "```", _refusal(_wide_rank(5, orientation)), "```", ""]
        svg = _render(f"bound-{flow}-long-labels", _long_labels(orientation), "boundaries")
        total += 1
        lines += [
            "#### Long labels",
            "",
            "The legibility tail. Same node count as a comfortable graph; long "
            f"labels widen the cards, the canvas grows, and the display scale falls to **{_scale_of(svg)}**.",
            "",
            f"![bound-{flow}-long-labels](../renders/topologies/{FAMILY}/boundaries/bound-{flow}-long-labels.svg)",
            "",
        ]
    total += _exhibit(
        lines,
        "bound-hostile-labels",
        "Ampersands, angle brackets and quotes in every text slot — Invariant 14 "
        "says the artifact stays well-formed XML and the escaping lives in the template.",
        _hostile(),
        "boundaries",
    )
    lines += [
        "An illegal orientation names the legal set:",
        "",
        "```",
        _refusal({**_mapreduce(None, None), "orientation": "radial"}),
        "```",
        "",
        "A cyclic dag is not refused as a dead end — it is promoted:",
        "",
        "```",
        _refusal(
            {
                "title": "Cyclic",
                "topology": "dag",
                "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
                "edges": [
                    {"source": "a", "target": "b"},
                    {"source": "b", "target": "c"},
                    {"source": "c", "target": "a"},
                ],
            }
        ),
        "```",
        "",
    ]

    _section(
        lines,
        "6 · Gaps",
        "What this family cannot express today, stated plainly so nobody has to discover it by trying.",
    )
    lines += [
        "- **Role eyebrows.** The vertical specimens print a `SUB-AGENT` kicker above "
        "each worker's name. `DiagramNode` has no field for it — `chips` renders pills "
        "*beneath* the desc, not above the name — so the engine's cards are one text "
        "row shorter than the hand files. This is why the chassis cites the specimen's "
        "card WIDTH (196) but not its height (84).",
        "- **Boxed band labels.** A `band` region draws its label as centred uppercase "
        "text on the leading edge. The vertical specimen draws it as a boxed chip in the "
        "top-left corner; the seating constants are enrolled (`band_label_inset`, "
        "`band_label_gap`) but the chip dress is not built.",
        "- **Self-loops flowing down.** A self-loop makes the graph cyclic, and the "
        "input seam promotes a cyclic dag to `state-machine` — which has no vertical "
        "cell, so the compose refuses. The device therefore exhibits on the horizontal "
        "flow only. Nothing is wrong with either rule; they simply do not compose yet.",
        "- **Cycles.** A cyclic graph is not a dag; the input seam promotes it to "
        "`state-machine` rather than refusing (see the promotion message above).",
        "- **Depth past five ranks.** A deeper chain refuses rather than compressing. A "
        "depth-compression rule would buy more ranks inside the same height budget, but "
        "it is new vocabulary and needs its own specimen.",
        "- **Cross-family composition.** A fan *inside* a rank (parallel work per stage) "
        "is not a dag device; it is a composition layer across families.",
        "",
    ]

    # The gestalt rule holds for the deep exhibit too: renders of this family
    # owned by a gallery organised on another axis — the specimen board, the
    # card+label slots — are embedded here so the family reads in one scroll.
    from scripts.examples.topologies.exhibit import _elsewhere_section

    lines += _elsewhere_section(FAMILY)

    lines += [
        "## Coverage",
        "",
        "| section | exhibits |",
        "| --- | --- |",
        f"| specimens | {len(SPECIMENS)} |",
        f"| axis grid | {len(_axis_grid())} |",
        f"| real scenarios | {len(_SCENARIOS)} |",
        f"| shipped corpus (both flows) | {len(_corpus_stories()) * 2} |",
        f"| capability edges | {len(_capabilities())} |",
        f"| **total artifacts** | **{total}** |",
        "",
    ]

    from scripts.examples.diagrams import family_doc

    doc = family_doc(FAMILY)
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("\n".join(lines))
    return total


def main() -> None:
    n = build_dag()
    print(f"_topologies/{FAMILY}: README.md + {n} renders (baked porcelain light)")


if __name__ == "__main__":
    main()
