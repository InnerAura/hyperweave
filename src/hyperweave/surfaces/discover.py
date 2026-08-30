"""Discovery core — the shared data behind ``hw_discover`` and the CLI/HTTP faces.

One implementation so the surfaces cannot drift. ``what="capabilities"`` renders
the registry roster (name, summary, per-surface reachability) — the living
capability index a cold agent reads to learn what HyperWeave can do and where.
"""

from __future__ import annotations

from typing import Any


def _orientation_summary() -> str:
    """Which orientations each topology accepts, DERIVED from the legality
    config the solver refuses against.

    Hand-maintained, this string went stale the moment a topology gained an
    axis: it advertised "everything else horizontal" while `dag` and `pipeline`
    had `vertical`, `cycle` had no horizontal at all, and `fanout`'s `downward`
    was missing. An agent reads this to decide what to ask for, so a wrong
    answer here is a wrong request everywhere downstream."""
    from hyperweave.config.loader import load_diagram_config
    from hyperweave.core.diagram import Topology

    legality: dict[str, list[str]] = load_diagram_config().get("orientation_legality") or {}
    parts: list[str] = []
    for topo in (t.value for t in Topology):
        legal = legality.get(topo) or ["horizontal"]
        if legal != ["horizontal"]:
            parts.append(f"{topo}: {' | '.join(legal)}")
    single = [t.value for t in Topology if (legality.get(t.value) or ["horizontal"]) == ["horizontal"]]
    if single:
        parts.append(f"horizontal only: {', '.join(single)}")
    return "; ".join(parts)


def capability_index() -> list[dict[str, Any]]:
    """The registry roster as a reachability table (for ``what="capabilities"``)."""
    from hyperweave.surfaces.registry import all_capabilities

    rows: list[dict[str, Any]] = []
    for cap in all_capabilities():
        rows.append(
            {
                "name": cap.name,
                "summary": cap.summary,
                "output": cap.output_note,
                "reachable": {
                    "cli": cap.cli_command,
                    "http": cap.http_path,
                    "mcp": cap.mcp_tool,
                },
                "note": cap.mcp_note,
            }
        )
    return rows


def render_surfaces_section() -> str:
    """The ``## Surfaces`` block for /llms.txt — derived from the registry.

    Grouping each capability's declared reachability into the MCP / HTTP / CLI
    lines the same way the hand-maintained block did, but from the registry so
    the enumeration cannot drift as surfaces are added. ``artifact`` fetch is not
    a registered dispatch capability (it is a byte-fetch), so the HTTP digest URL
    is named explicitly here as the one non-registry surface fact.
    """
    from hyperweave.surfaces.registry import all_capabilities

    caps = all_capabilities()
    mcp = [c.mcp_tool for c in caps if c.mcp_tool]
    http = [c.http_path for c in caps if c.http_path]
    cli = [c.cli_command for c in caps if c.cli_command]
    lines = ["## Surfaces", ""]
    lines.append("  MCP:  " + " · ".join(mcp))
    lines.append("  HTTP: " + " · ".join(http) + " · GET /v1/a/{digest}")
    lines.append("  CLI:  " + " · ".join(f"hyperweave {c}" for c in cli))
    return "\n".join(lines)


def render_llms_txt() -> str:
    """Assemble /llms.txt: the hand-authored head + the registry-derived surfaces
    block + a pointer to the full doc (llms.txt convention: the index links to
    the full document)."""
    from hyperweave.core.contract import LLMS_TXT_HEAD

    return (
        LLMS_TXT_HEAD
        + "\n"
        + render_surfaces_section()
        + "\n\n## Full reference\n\n"
        + "  /llms-full.txt — this contract + the verb SKILL + the full capability index.\n"
    )


def _skill_body() -> str:
    """The SKILL.md body with its YAML frontmatter stripped.

    The skill file itself stays where it is (the real, shippable skill); this
    reads its content for inclusion in /llms-full.txt. Frontmatter is the leading
    ``---`` … ``---`` block; the body (which may itself contain ``---`` rules) is
    everything after the second delimiter.
    """
    from hyperweave.config.loader import _data_path

    path = _data_path("skills/hyperweave-verbs/SKILL.md")
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        # Drop the leading line, find the closing delimiter, keep the remainder.
        rest = text.split("\n", 1)[1] if "\n" in text else ""
        end = rest.find("\n---")
        if end != -1:
            body = rest[end + len("\n---") :]
            return body.lstrip("\n").rstrip() + "\n"
    return text.rstrip() + "\n"


def _render_capability_index() -> str:
    """The per-capability index for /llms-full.txt — generated from the registry.

    One block per capability: name, summary, output shape, and per-surface
    reachability. This is the doc anti-drift surface — every registered
    capability appears here by construction, so a new capability cannot ship
    undocumented (pinned by test)."""
    lines = ["## Capability index", ""]
    lines.append("Every capability, and where each is reachable (generated from the registry):")
    lines.append("")
    for row in capability_index():
        reach = row["reachable"]
        parts: list[str] = []
        if reach["cli"]:
            parts.append(f"CLI `hyperweave {reach['cli']}`")
        if reach["http"]:
            parts.append(f"HTTP `{reach['http']}`")
        if reach["mcp"]:
            parts.append(f"MCP `{reach['mcp']}`")
        where = " · ".join(parts) if parts else "(surface-specific)"
        lines.append(f"### {row['name']}")
        lines.append(f"{row['summary']}")
        lines.append(f"- reachable: {where}")
        lines.append(f"- returns: {row['output']}")
        if row["note"]:
            lines.append(f"- note: {row['note']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_idiom_tier() -> str:
    """The idiom-tier reference for /llms-full.txt — generated from the idiom
    registry (data/registries/idioms.yaml), so the discovery prose cannot
    drift from what the engine renders. Scope + rhetoric ride each entry:
    scope says where an idiom is legal, rhetoric feeds extract/query."""
    from hyperweave.config.loader import load_idioms

    idi = load_idioms()
    lines = ["## Idiom tier (primitives -> idioms -> topologies)", ""]
    lines.append(
        "Line idioms are RELATIONS — `edge.relation` names what an edge MEANS and binds a "
        "default dress from the existing vocabulary. Any two co-present relations differ on "
        ">=1 dress channel. Box idioms: `node.chips` (in-card pill row), `edge.label_style: chip` "
        "(pill riding the wire), micro-label (bare edge label). `node.kind` resolves a core "
        "glyph (brand -> kind -> nothing)."
    )
    lines.append("")
    for k, v in (idi.get("line") or {}).items():
        dress = v.get("dress") or {}
        dressed = ", ".join(f"{dk}={dv}" for dk, dv in dress.items())
        use = f" — use when: {v['use_when']}" if v.get("use_when") else ""
        lines.append(f"- relation `{k}` ({v.get('rhetoric', '')}): {dressed}{use}")
    for k, v in (idi.get("class-native") or {}).items():
        lines.append(f"- class-native `{k}` [{v.get('class', '')}]: {v.get('meaning', '')}")
    return "\n".join(lines).rstrip() + "\n"


_TOPOLOGY_GUIDE: dict[str, str] = {
    "pipeline": "a linear chain of stages (horizontal rows | vertical = the operator stack)",
    "fanout": "one source to many peers (horizontal | bilateral | upward | downward | radial)",
    "fanin": "many inputs fanning into one mouth (the fan family, direction reversed)",
    "cycle": "the CLOSED loop family — endless rhythm, no branch logic (orbit = phases around a hero "
    "axis | ring = equal stages, empty centre); a loop with guards, exits, or terminals is topology loop",
    "loop": "the procedural directed loop — process stations on a spine, exclusive decisions with guard "
    "chips, terminal exits, and a return rail (vertical = spine + margin rail, the default | horizontal "
    "= row + underslung return); devices are structural: two decisions = retry, tap edges = supervised "
    "loop, a scope node = nested loop, accumulates on the return = flywheel",
    "tree": "a root branching to leaves (radial at depth >= 2 = the mindmap form)",
    "comparison": "exactly two cards, before/after",
    "sequence": "lifelines exchanging ordered messages",
    "dag": "ranked causal/temporal strata with fan-out AND fan-in",
    "state-machine": "states + transitions (self-loops, back-edges)",
    "hub": "one nucleus with role-driven satellites (axial default; compass opt-in)",
    "lanes": "category bands sharing a datum rule",
}

# Structural edge legality per topology — mirrors the DiagramSpec validators in
# core/diagram.py so the constraint is knowable BEFORE compose (the validator
# stays the enforcement). Only topologies carrying a structural edge rule
# appear; `any` states the global laws every topology shares.
_TOPOLOGY_EDGE_RULES: dict[str, str] = {
    "any": "edges reference declared node ids; at most one directed edge per node pair per direction",
    "hub": "every edge touches the hub — the first node declared; a satellite-to-satellite relation "
    "needs a free-graph topology — recompose with dag or lanes",
    "tree": "every non-root node has exactly one parent edge; the root has none; cross-links need dag",
    "dag": "free graph — any node-to-node edge; a cycle renders as a state machine instead of erroring",
    "state-machine": "free graph including self-loops and back-edges; a self-loop cannot be bidirectional",
    "sequence": "messages connect lifelines in declaration order; edge kind (call/return) is sequence-only semantics",
    "lanes": "every node declares a category (its lane); edges may cross lanes freely",
    "loop": "exactly one outer circuit:return edge closes the loop; tap-in/tap-out edges touch a "
    "station:external node; a decision spends exactly two exits; scope members declare enclosure and "
    "stay wholly inside their scope",
}


def _render_diagram_frame() -> str:
    """The diagram-frame authoring reference for /llms-full.txt — topology
    menu with selection guidance, the per-class capacity table (generated
    from the engine caps, so it cannot drift), field notes the cold-agent
    dogfood found missing, and one complete example spec."""
    from hyperweave.config.loader import load_diagram_config

    engine = load_diagram_config()
    layouts = (engine.get("caps") or {}).get("layouts") or {}
    lines = ["## Diagram frame (authoring reference)", ""]
    lines.append(
        "Spec shape: {topology, title, subtitle?, nodes: [{id, label, desc?, kind?, glyph?, chips?, "
        "category?, role?, embed?}], edges: [{source, target, label?, relation?, label_style?, role?}]}. "
        "Edges reference node IDS via `source`/`target`. `validate` accepts a bare spec or the "
        "{type, spec} envelope; compose is the same gate."
    )
    lines.append(
        "Text placement: `title` is the artifact's NAME — it fills <title>, <desc>, the payload, and the "
        "markdown shadow's lead, and it draws as the caption only when `subtitle` is empty. `subtitle` is "
        "the one caption line drawn at the base. There is no drawn heading; the host page owns that."
    )
    lines.append("")
    lines.append("Topologies (pick by shape of the story; capacities are hard bands):")
    for slug, guide in _TOPOLOGY_GUIDE.items():
        band = layouts.get(slug) or {}
        cap = f" [{band.get('min', '?')}-{band.get('max', '?')} nodes]" if band else ""
        lines.append(f"- `{slug}`{cap}: {guide}")
    dag_band = layouts.get("dag") or {}
    lines.append(
        f"dag adds: <= {dag_band.get('max_ranks')} ranks, <= {dag_band.get('max_per_rank')} per rank, "
        f"at most {dag_band.get('max_skip_edges')} skip edges (authored `rank` overrides exist; forward edges "
        "need source rank < target rank). Model a too-deep chain as a labeled flow edge instead. "
        "`orientation: vertical` flows the same graph top-to-bottom, with its own band of the same caps."
    )
    lines.append("")
    lines.append(
        "Node identity: `glyph` = explicit brand slug (never inferred from the label); `kind` = generic "
        "systems mark (database, server, ... — discover glyphs lists glyph_kinds); ladder is "
        "glyph -> kind -> nothing, and an unresolved kind warns. `role` (default | hero | muted) is "
        "caller rhetoric on any topology; hub edge roles (in | out | read | edit) drive the axial cross."
    )
    lines.append(
        "Rendered note: `rendered.edge_motion/track` report the artifact's MOTION channel; a declared "
        "`relation` overrides the wire's dress independently (assert renders solid + a drawn chevron — "
        "markers are drawn paths, never marker-end refs)."
    )
    lines.append("")
    lines.append("Example (composes as-is):")
    lines.append("```json")
    lines.append(
        '{"topology": "dag", "title": "Checkout",\n'
        '  "nodes": [{"id": "web", "label": "Web", "kind": "globe"},\n'
        '            {"id": "api", "label": "API", "kind": "server"},\n'
        '            {"id": "db", "label": "Postgres", "kind": "database"},\n'
        '            {"id": "events", "label": "Analytics", "kind": "chart-line"}],\n'
        '  "edges": [{"source": "web", "target": "api", "relation": "assert", "label": "calls"},\n'
        '            {"source": "api", "target": "db", "relation": "drift", "label": "reads"},\n'
        '            {"source": "api", "target": "events", "relation": "flow", "label": "emits",\n'
        '             "label_style": "chip"}]}'
    )
    lines.append("```")
    return "\n".join(lines).rstrip() + "\n"


def render_llms_full_txt() -> str:
    """Assemble /llms-full.txt: the contract head + registry-derived surfaces +
    the verb SKILL body + the generated per-capability index + the idiom tier.
    The living reference a cold agent reads to learn the full protocol from
    one document."""
    from hyperweave.core.contract import LLMS_TXT_HEAD

    sections = [
        LLMS_TXT_HEAD.rstrip(),
        render_surfaces_section(),
        "## Verb skill\n\n" + _skill_body().rstrip(),
        _render_capability_index().rstrip(),
        _render_idiom_tier().rstrip(),
        _render_diagram_frame().rstrip(),
    ]
    return "\n\n".join(sections) + "\n"


def _discover_schema(selector: str) -> dict[str, Any]:
    """``schema:<id>`` → the frame's published JSON Schema (matrix/1, diagram/1)."""
    from hyperweave.core.errors import HwError, HwErrorCode
    from hyperweave.verbs.schemas import frame_schema_for, known_schema_ids

    model = frame_schema_for(selector)
    if model is None:
        raise HwError(
            HwErrorCode.TYPE_UNKNOWN,
            f"unknown schema id {selector!r}",
            fix=f"known schemas: {', '.join(known_schema_ids())} (discover schemas)",
        )
    return {"id": selector, "json_schema": model.model_json_schema()}


def _diagram_worked_example() -> dict[str, str]:
    """The diagram-frame worked example for ``verbs.worked_example`` — the
    onboarding loop the diagram IR needs (a bundled preset -> compose ->
    extract -> mutate -> recompose), matching the matrix example's weight.
    ``gateway`` is a real bundled preset (pinned by
    ``test_diagram_worked_example_preset_is_bundled``); the mutation appends
    a node and an edge, the shape a cold agent needs for the diagram IR's
    array fields (matrix's example only replaces a scalar)."""
    return {
        "0_discover_preset": (
            "hw_discover(what='example:diagram/pipeline-row') → {field: 'diagram', value: <DiagramSpec>} — "
            "a bundled preset, ready to compose or mutate"
        ),
        "1_compose": "hw_compose(type='diagram', genome='primer', diagram=value) → {envelope, url}",
        "2_extract": (
            "hw_extract(source=svg, respond='payload') → {spec, rendered} — "
            "the full DiagramSpec seed under payload.spec"
        ),
        "3_transform": (
            "hw_transform(source=svg, mutations=[{'op':'add','path':'/nodes/-','value':"
            "{'id':'logger','label':'Audit log','kind':'database'}}, "
            "{'op':'add','path':'/edges/-','value':"
            "{'source':'server','target':'logger','label':'writes'}}]) → new {envelope, url, lineage}"
        ),
        "4_verify": "hw_verify(source=new_svg) → {valid: true}",
    }


def genome_deep_dive(genome_id: str) -> dict[str, Any]:
    """``genome:<id>`` → the role-structured deep-dive (tokens grouped by intent).

    The ONE extraction behind both faces: ``discover genome:<id>`` and the CLI's
    ``genomes <id> --explain`` — shared so the two can never drift.
    """
    from hyperweave.config.loader import get_loader
    from hyperweave.core.errors import HwError, HwErrorCode

    loader = get_loader()
    genome = loader.genomes.get(genome_id)
    if genome is None:
        raise HwError(
            HwErrorCode.GENOME_UNKNOWN,
            f"unknown genome {genome_id!r}",
            fix=f"known genomes: {', '.join(sorted(loader.genomes))} (discover genomes)",
        )
    roles = genome.get("roles") or {}
    variant_names = sorted(
        set(genome.get("variants") or [])
        | set((genome.get("variant_overrides") or {}).keys())
        | set((genome.get("variant_tones") or {}).keys())
    )
    return {
        "id": genome_id,
        "name": genome.get("name", genome_id),
        "category": genome.get("category", "dark"),
        "default_surface": genome.get("default_surface", ""),
        "roles": {role: {t: genome.get(t, "") for t in tokens} for role, tokens in roles.items()},
        "variants": variant_names,
        "paradigms": sorted(k for k, v in (genome.get("paradigms") or {}).items() if v),
    }


def _discover_example(frame_type: str, name: str) -> dict[str, Any]:
    """``example:<frame_type>/<name>`` → the full bundled spec content.

    Frame-type-scoped addressing matches ``--spec-file`` and the URL grammar;
    ``resolve_bundled_spec`` already raises the well-shaped unknown-name errors
    (its ``fix`` names the known preset menu).
    """
    from hyperweave.compose.bundled_specs import resolve_bundled_spec

    bundled = resolve_bundled_spec(frame_type, name)
    return {"frame_type": frame_type, "name": name, "field": bundled.field, "value": bundled.value}


# Every `what in ("all", <section>)` condition in discover() — kept in lockstep
# by the every-listed-selector-answers guard; a section missing here would 404
# the moment anything selects it.
_SECTION_SELECTORS = (
    "all",
    "schemas",
    "genomes",
    "motions",
    "glyphs",
    "idioms",
    "frames",
    "verbs",
    "capabilities",
    "matrix",
    "diagram",
    "url_grammar",
)


def _normalize_selector(what: str) -> str:
    """Accept the ``what=`` spelling as an alias for the positional selector.

    ``discover what='glyphs'`` pasted into a shell hands the CLI the literal
    string ``what='glyphs'`` — strip the key and quotes so the pasted form of
    an MCP-style hint answers instead of silently missing every section.
    """
    what = what.strip()
    if what.startswith("what="):
        what = what.removeprefix("what=").strip().strip("'\"")
    return what


def agent_capsule(topology: str = "") -> dict[str, Any]:
    """The compact agent contract — single-digit kilobytes, derived from the
    same enums, legality config, and registries the solver refuses against;
    no hand-maintained prose. Carries a content digest so an agent can cache
    it and skip the rediscovery ritual. The full JSON Schema stays the exact
    contract beside it (``discover schema:diagram/1``); the capsule is the
    summary, never a replacement."""
    import hashlib
    import json as _json
    from typing import get_args

    from hyperweave import __version__
    from hyperweave.config.loader import load_diagram_config, load_diagram_presets
    from hyperweave.core.diagram import (
        DiagramEdge,
        DiagramSpec,
        EdgeKind,
        EdgeMotion,
        NodeRole,
        NodeStyle,
        Topology,
    )
    from hyperweave.core.errors import HwError, HwErrorCode

    engine = load_diagram_config()
    legality: dict[str, list[str]] = engine.get("orientation_legality") or {}
    caps = dict((engine.get("caps") or {}).get("layouts") or {})
    topos = [t.value for t in Topology]
    if topology:
        if topology not in topos:
            raise HwError(
                HwErrorCode.TOPOLOGY_UNKNOWN,
                f"unknown topology {topology!r}",
                fix="one of: " + ", ".join(topos),
            )
        topos = [topology]
    presets = load_diagram_presets()
    families: dict[str, Any] = {}
    for topo in topos:
        slugs = sorted(s for s in caps if s == topo or s.startswith(topo + "-"))
        families[topo] = {
            "caps": {s: caps[s] for s in slugs},
            "orientations": legality.get(topo) or ["horizontal"],
            "edge_rule": _TOPOLOGY_EDGE_RULES.get(topo) or _TOPOLOGY_EDGE_RULES.get("any", ""),
            "presets": sorted(n for n, spec in presets.items() if spec.get("topology") == topo),
        }
    scalar_caps = {k: v for k, v in (engine.get("caps") or {}).items() if not isinstance(v, dict)}
    body: dict[str, Any] = {
        "schema": "capsule/1",
        "engine": __version__,
        "scope": topology or "all",
        "families": families,
        "shared_caps": scalar_caps,
        "vocabulary": {
            "edge_motion": [m.value for m in EdgeMotion if m.value],
            "node_styles": [s.value for s in NodeStyle if s.value],
            "edge_kinds": [k.value for k in EdgeKind if k.value],
            "roles": [r.value for r in NodeRole if r.value],
            "relations": [v for v in get_args(DiagramEdge.model_fields["relation"].annotation) if v],
            "motion_registers": [v for v in get_args(DiagramSpec.model_fields["motion_register"].annotation) if v],
        },
        "compose": {
            "cli": "hw compose diagram --spec-file spec.json -o out.svg [--proof]",
            "http": "POST /v1/compose",
            "mcp": "hw_compose(diagram=...)",
            "exact_contract": "discover schema:diagram/1",
        },
    }
    digest = "sha256:" + hashlib.sha256(_json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()
    return {**body, "digest": digest}


def discover(what: str = "all") -> dict[str, Any]:
    """Return discovery data for the ``what`` selector.

    Mirrors the ``hw_discover`` sections (genomes/motions/glyphs/frames/verbs/
    matrix/diagram/url_grammar) and adds ``capabilities`` from the registry,
    plus the deep selectors: ``schema:<id>`` (a frame's published JSON Schema)
    and ``example:<frame_type>/<name>`` (a full bundled spec, compose-ready).
    An unknown selector raises with the menu — never a silent empty dict.
    """
    from hyperweave.config.loader import get_loader
    from hyperweave.core.enums import FrameType
    from hyperweave.core.errors import HwError, HwErrorCode

    what = _normalize_selector(what)

    if what.startswith("schema:"):
        return {"schema": _discover_schema(what.removeprefix("schema:"))}
    if what.startswith("example:"):
        frame_type, _, name = what.removeprefix("example:").partition("/")
        return {"example": _discover_example(frame_type, name)}
    if what.startswith("genome:"):
        return {"genome": genome_deep_dive(what.removeprefix("genome:"))}
    if what == "agent" or what.startswith("agent:"):
        return {"capsule": agent_capsule(what.partition(":")[2])}

    if what not in _SECTION_SELECTORS:
        raise HwError(
            HwErrorCode.TYPE_UNKNOWN,
            f"unknown discover selector {what!r}",
            fix="valid selectors: "
            + " | ".join(_SECTION_SELECTORS)
            + " — plus agent[:<topology>] (the compact capsule), schema:<id>, example:<frame_type>/<name>, genome:<id>",
        )

    loader = get_loader()
    result: dict[str, Any] = {}

    if what in ("all", "schemas"):
        from hyperweave.verbs.schemas import known_schema_ids

        result["schemas"] = list(known_schema_ids())

    if what in ("all", "genomes"):
        result["genomes"] = [
            {
                "id": gid,
                "name": g.get("name", gid),
                "category": g.get("category", "dark"),
                "profile": g.get("profile", "flat"),
                "compatible_motions": g.get("compatible_motions", ["static"]),
            }
            for gid, g in loader.genomes.items()
        ]

    if what in ("all", "motions"):
        result["motions"] = [
            {
                "id": mid,
                "name": m.get("name", mid),
                "type": m.get("type", "unknown"),
                "applies_to": m.get("applies_to", m.get("frames", [])),
                "cim_compliant": m.get("cim_compliant", True),
            }
            for mid, m in loader.motions.items()
        ]

    if what in ("all", "glyphs"):
        result["glyphs"] = sorted(k for k in loader.glyphs if not k.startswith("kind:"))
        # The CORE set (Lucide-derived stroke marks) a node ``kind`` resolves;
        # brand slugs stay the more specific claim (brand -> kind -> nothing).
        result["glyph_kinds"] = sorted(k.removeprefix("kind:") for k in loader.glyphs if k.startswith("kind:"))

    if what in ("all", "idioms"):
        from hyperweave.config.loader import load_idioms

        idi = load_idioms()
        result["idioms"] = {
            "line": {
                k: {"dress": v.get("dress", {}), "scope": v.get("scope", ""), "rhetoric": v.get("rhetoric", "")}
                for k, v in (idi.get("line") or {}).items()
            },
            "box": {
                k: {"scope": v.get("scope", ""), "rhetoric": v.get("rhetoric", "")}
                for k, v in (idi.get("box") or {}).items()
            },
            "class_native": {
                k: {"class": v.get("class", ""), "meaning": v.get("meaning", "")}
                for k, v in (idi.get("class-native") or {}).items()
            },
            "notes": "Line idioms are RELATIONS (edge.relation) binding existing dress vocabulary — "
            "relation:flow names meaning, edge-motion:flow names dress; two co-present relations must "
            "differ on >=1 dress channel. Box idioms: chips (node.chips = in-card pill row), edge-chip "
            "(edge.label_style='chip' = pill riding the wire), micro-label (a bare edge label).",
        }

    if what in ("all", "frames"):
        result["frames"] = [ft.value for ft in FrameType]

    if what in ("all", "verbs"):
        from hyperweave.core.contract import discover_verbs

        verbs = discover_verbs()
        # discover_verbs() ships one worked example (matrix-flavored) — split
        # it into a per-frame mapping so a cold agent learning the diagram IR
        # gets an equal-weight loop instead of the matrix-only onboarding.
        verbs["worked_example"] = {"matrix": verbs["worked_example"], "diagram": _diagram_worked_example()}
        result["verbs"] = verbs

    if what in ("all", "capabilities"):
        result["capabilities"] = capability_index()

    if what in ("all", "matrix"):
        from hyperweave.compose.matrix.input import matrix_preset_names
        from hyperweave.core.matrix import CellKind

        result["matrix"] = {
            "cell_kinds": [k.value for k in CellKind if k.value != "auto"],
            "inferred_kinds": "text | check | dot... auto-inference covers check/chip/glyph/pill/numeric/text; "
            "bar and dot are caller-only (declare column.kind explicitly)",
            "presets": list(matrix_preset_names()),
            "rhetoric_fields": "hero_column, headline, summary_row, emphasis — caller-only, never inferred",
            "projections": "SVG + hw:payload (matrix/1) + hwz/1 envelope + GFM markdown "
            "(render_target='markdown' or ComposeResult.markdown)",
        }

    if what in ("all", "diagram"):
        from hyperweave.compose.diagram import registered_slugs
        from hyperweave.compose.diagram.input import diagram_preset_names
        from hyperweave.core.diagram import EdgeMotion, NodeStyle, Topology

        result["diagram"] = {
            "topologies": [t.value for t in Topology],
            "layout_slugs": registered_slugs(),
            "edge_rules": dict(_TOPOLOGY_EDGE_RULES),
            "orientations": _orientation_summary(),
            "edge_motion": " | ".join(m.value for m in EdgeMotion if m.value)
            + " — the closed kit set (genome allowlist enforced); tiers derive from the motion_tiers "
            "table: dash marches stroke-dashoffset (paint-ok), particle rides composited "
            "(composite-only), beam animates its gradient window (paint-ok) and degrades to particle "
            "on composite-only surfaces",
            "motion_register": "turn | drift | laps | budget | accumulate — the artifact-scoped "
            "choreography register; loop defaults to turn (a pulse walks the circuit in acts, arrival "
            "halos flash each station, guard chips flash when their branch fires), drift is the quiet "
            "standing face, and the meter registers perform a declared gauge (laps grows and resets, "
            "budget drains and refills, accumulate grows and holds); override via "
            "--motion-register / ?motion_register= / MCP motion_register",
            "node_styles": " | ".join(s.value for s in NodeStyle if s.value)
            + " — caller-chosen, never inferred. card+label inverts the default card: a small tracked "
            "label over a stack of display values, any glyph/kind demoted to a corner mark that reserves "
            "no column; pill is the capsule card (card+glyph anatomy with capsule ends — the terminal/"
            "advance silhouette); text drops the box entirely (the type IS the node)",
            "roles": "default | hero | muted — hero gets the signal ring; muted is the comparison-left grammar",
            "hub": "focal node = slot 0. hub_policy: '' | compass | axial — explicit wins; compass when any "
            "member speaks compass vocabulary (zone/angle/anchor/distribution); AXIAL is the default for "
            "role-driven hubs: the hero sits on a spine crossing, roles map to half-planes (edit->N, in->W, "
            "read->S) and the out family fans east from a gather point on tangent curves. Compass sector "
            "precedence: edge.angle > node.anchor > edge.zone > role default > direction default. "
            "distribution: even | golden | balanced | crossing-minimized. spec.zones: up to two group "
            "headers (first reads ink at the content's left edge, second reads accent at its right).",
            "relations": "edge.relation: assert (solid + arrow) | drift (petite dash + dot terminal) | "
            "flow (marching dash + particle riders) | bypass (dash, routed around). Relations are MEANING "
            "binding existing dress; explicit per-edge fields override channels; particles never ride "
            "accent strokes (invisible-riders).",
            "chips": "node.chips = in-card pill row (any card topology); edge.label_style='chip' "
            "renders the edge label as a pill riding the wire midpoint.",
            "kinds": "node.kind resolves a CORE glyph (database, server, queue-ish marks — "
            "discover glyphs lists glyph_kinds); ladder: node.glyph (brand) -> node.kind -> nothing.",
            "lanes": "every node declares a category; categories become bands (first-appearance order). "
            "edge.route: '' (auto by lane distance) | bus (adjacent bands only) | around (perimeter channel "
            "for long hauls). Same category shares a palette slot.",
            "self_loops": "a v->v edge is a revise-in-place arc on state-machine/dag/hub/lanes/sequence; "
            "edge.exit picks the side. A cyclic topology:dag auto-promotes to state-machine (a warning names "
            "the cycle); the payload keeps the declared dag.",
            "presets": list(diagram_preset_names()),
            "projections": "SVG + hw:payload (diagram/1: {spec, rendered}) + hwz/1 envelope "
            "(pattern + n + content) + markdown shadow (render_target='markdown')",
        }

    if what in ("all", "url_grammar"):
        result["url_grammar"] = _url_grammar()

    return result


def _url_grammar() -> dict[str, Any]:
    """The URL-grammar reference block, rendered from data/config/url-grammar.yaml.

    Patterns, query parameters and examples come from the same file
    ``surfaces/addressing.py`` builds real URLs with, so the reference cannot
    describe a route the addresser does not produce. Variant vocabulary is
    filled from ``load_genomes()`` at render time — the previous hand-written
    copy of this block spelled out the chrome and automata rosters inline and
    went stale every time a variant shipped.
    """
    from hyperweave.config.loader import load_genomes, load_url_grammar

    genomes = load_genomes()
    rosters = ", ".join(f"{gid}: {' | '.join(cfg.variants)}" for gid, cfg in sorted(genomes.items()) if cfg.variants)
    pair_genomes = sorted(gid for gid, cfg in genomes.items() if len(cfg.variants) > 1)
    tokens = {
        "variants": rosters,
        "pairs": (
            "Second solo tone for bifamily frames (strip, divider) — composed at request time, "
            f"e.g. ?variant=teal&pair=violet. Declared by {', '.join(pair_genomes)}; "
            "other frame types silently ignore it."
        ),
        "data": (
            "Comma-separated tokens: text:STRING | kv:KEY=VALUE | gh:owner/repo.metric | "
            "pypi:pkg.metric | npm:pkg.metric | hf:org/model.metric | arxiv:id.metric | "
            "docker:owner/image.metric | crates:pkg.metric | scorecard:owner/repo.metric | "
            "dora:owner/repo.metric. Embedded commas in text/kv payloads escape as \\,."
        ),
    }

    def _fill(text: str) -> str:
        for token, value in tokens.items():
            text = text.replace("{" + token + "}", value)
        return text

    grammar = load_url_grammar()
    block: dict[str, Any] = {}
    for frame, route in grammar["routes"].items():
        entry: dict[str, Any] = {
            "pattern": route["pattern"],
            "query_params": {
                name: _fill(str(decl.get("doc", ""))) for name, decl in (route.get("query") or {}).items()
            },
            "example": route.get("example", ""),
        }
        if alias := route.get("alias"):
            entry["alias"] = f"{alias} (permanent — same handler, no redirect)"
        if note := route.get("note"):
            entry["note"] = note
        for name, decl in (route.get("segments") or {}).items():
            if doc := decl.get("doc"):
                entry.setdefault("path_params", {})[name] = doc
        block[str(route.get("doc_key", frame))] = entry
    for frame, reason in grammar["unrouted"].items():
        block[frame] = {"pattern": "POST /v1/compose", "query_params": {}, "note": reason}
    return block
