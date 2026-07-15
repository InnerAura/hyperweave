"""Discovery core — the shared data behind ``hw_discover`` and the CLI/HTTP faces.

One implementation so the surfaces cannot drift. ``what="capabilities"`` renders
the registry roster (name, summary, per-surface reachability) — the living
capability index a cold agent reads to learn what HyperWeave can do and where.
"""

from __future__ import annotations

from typing import Any


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
    "pipeline": "a linear chain of stages, left to right",
    "fanout": "one source to many peers (horizontal | bilateral | upward | radial)",
    "convergence": "many inputs merging into one target",
    "flywheel": "a self-reinforcing cycle of phases",
    "stack": "layers beneath one result (deps, tiers)",
    "tree": "a root branching to leaves (radial at depth >= 2 = mindmap)",
    "comparison": "exactly two cards, before/after",
    "sequence": "lifelines exchanging ordered messages",
    "dag": "ranked causal/temporal strata with fan-out AND fan-in",
    "state-machine": "states + transitions (self-loops, back-edges)",
    "hub": "one nucleus with role-driven satellites (axial default; compass opt-in)",
    "lanes": "category bands sharing a datum rule",
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
    lines.append("")
    lines.append("Topologies (pick by shape of the story; capacities are hard bands):")
    for slug, guide in _TOPOLOGY_GUIDE.items():
        band = layouts.get(slug) or {}
        cap = f" [{band.get('min', '?')}-{band.get('max', '?')} nodes]" if band else ""
        lines.append(f"- `{slug}`{cap}: {guide}")
    caps = engine.get("caps") or {}
    lines.append(
        f"dag adds: <= {caps.get('dag_max_ranks')} ranks, <= {caps.get('dag_max_per_rank')} per rank, "
        f"at most {caps.get('dag_max_skip_edges')} skip edges (authored `rank` overrides exist; forward edges "
        "need source rank < target rank). Model a too-deep chain as a labeled flow edge instead."
    )
    lines.append("")
    lines.append(
        "Node identity: `glyph` = explicit brand slug (never inferred from the label); `kind` = generic "
        "systems mark (database, server, ... — discover what='glyphs' lists glyph_kinds); ladder is "
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


def discover(what: str = "all") -> dict[str, Any]:
    """Return discovery data for the ``what`` selector.

    Mirrors the ``hw_discover`` sections (genomes/motions/glyphs/frames/verbs/
    matrix/diagram/url_grammar) and adds ``capabilities`` from the registry.
    """
    from hyperweave.config.loader import get_loader
    from hyperweave.core.enums import FrameType

    loader = get_loader()
    result: dict[str, Any] = {}

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

        result["verbs"] = discover_verbs()

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
        from hyperweave.core.diagram import Topology

        result["diagram"] = {
            "topologies": [t.value for t in Topology],
            "layout_slugs": registered_slugs(),
            "orientations": "fanout: horizontal | bilateral | upward | radial; tree: horizontal | radial "
            "(radial requires depth >= 2 — the mindmap); everything else horizontal",
            "edge_motion": "dash | particle — the closed kit pair, compositor-only by construction "
            "(genome allowlist enforced)",
            "node_styles": "card | glyph-circle | card+glyph — caller-chosen, never inferred",
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
            "discover what='glyphs' lists glyph_kinds); ladder: node.glyph (brand) -> node.kind -> nothing.",
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
    """The URL-grammar reference block (unchanged from the MCP server's copy)."""
    data_grammar = (
        "Comma-separated tokens: text:STRING | kv:KEY=VALUE | "
        "gh:owner/repo.metric | pypi:pkg.metric | npm:pkg.metric | "
        "hf:org/model.metric | arxiv:id.metric | docker:owner/image.metric | "
        "crates:pkg.metric | scorecard:owner/repo.metric | dora:owner/repo.metric. "
        "Embedded commas in text/kv payloads escape as \\,."
    )
    variant_note = (
        "chrome: horizon | abyssal | lightning | graphite | moth. "
        "automata: 16 solo tones (violet/teal/bone/steel/amber/jade/magenta/"
        "cobalt/toxic/solar/abyssal/crimson/sulfur/indigo/burgundy/copper)."
    )
    pair_note = (
        "automata only — second solo tone for bifamily strip + divider. "
        "Composes any two tones at request time (e.g. ?variant=teal&pair=violet). "
        "Other frame types silently ignore the parameter."
    )
    return {
        "badge (static)": {
            "pattern": "/v1/badge/{title}/{value}/{genome}.{motion}",
            "query_params": {
                "glyph": "Glyph identifier (e.g. github, python)",
                "glyph_mode": "auto | fill | wire | none",
                "state": "active | passing | building | warning | critical | failing | offline",
                "regime": "normal | permissive | ungoverned",
                "size": "default | compact",
                "variant": variant_note,
                "pair": pair_note,
                "t": "Title override (use when title contains slashes)",
            },
            "example": "/v1/badge/build/passing/brutalist.static",
        },
        "badge (data-driven)": {
            "pattern": "/v1/badge/{title}/{genome}.{motion}?data=...",
            "query_params": {
                "data": data_grammar,
                "glyph": "Glyph identifier",
                "glyph_mode": "auto | fill | wire | none",
                "state": "Semantic state",
                "variant": variant_note,
                "pair": pair_note,
            },
            "example": "/v1/badge/STARS/brutalist.static?data=gh:anthropics/claude-code.stars",
        },
        "strip": {
            "pattern": "/v1/strip/{title}/{genome}.{motion}",
            "query_params": {
                "value": "Static metrics: STARS:2.9k,FORKS:278",
                "data": data_grammar,
                "subtitle": "Subtitle under identity (cellular paradigm)",
                "glyph": "Glyph identifier",
                "state": "Semantic state",
                "variant": variant_note,
                "pair": pair_note,
                "t": "Title override (use when title contains slashes)",
            },
            "example": "/v1/strip/readme-ai/brutalist.static?data=gh:eli64s/readme-ai.stars,gh:eli64s/readme-ai.forks",
        },
        "icon": {
            "pattern": "/v1/icon/{glyph}/{genome}.{motion}",
            "query_params": {
                "shape": "square | circle",
                "glyph_mode": "auto | fill | wire | none",
                "state": "Semantic state",
                "variant": variant_note,
                "pair": pair_note,
            },
            "example": "/v1/icon/github/chrome.static?shape=circle",
        },
        "divider": {
            "pattern": "/v1/divider/{divider_slug}/{genome}.{motion}",
            "query_params": {
                "divider_slug (path)": "block | current | takeoff | void | zeropoint | dissolve | seam | band",
                "variant": variant_note,
                "pair": "automata only — second solo tone for bifamily dissolve divider.",
            },
            "example": "/v1/divider/dissolve/automata.static?variant=teal&pair=violet",
        },
        "marquee": {
            "pattern": "/v1/marquee/{title}/{genome}.{motion}",
            "query_params": {
                "data": data_grammar + " When set, drives the scroll directly and ignores title.",
                "direction": "ltr | rtl",
                "speeds": "Single float scroll speed multiplier",
                "variant": variant_note,
                "pair": pair_note,
                "t": "Title override (use when title contains slashes)",
            },
            "example": "/v1/marquee/SCROLL/brutalist.static?data=text:NEW%20RELEASE,gh:anthropics/claude-code.stars",
        },
        "card": {
            "pattern": "/v1/card/{username}/{genome}.{motion}",
            "alias": "/v1/stats/{username}/{genome}.{motion} (permanent — same handler, no redirect)",
            "query_params": {
                "data": "Optional live data tokens appended as card metric slots.",
                "variant": variant_note,
                "pair": "automata only — silently ignored on card (kept for URL grammar uniformity).",
            },
            "example": "/v1/card/GLM-5/chrome.static?data=github:zai-org/GLM-5.stars,hf:zai-org/GLM-5.1.downloads",
        },
        "matrix": {
            "pattern": "/v1/matrix/{preset}/{genome}.{motion}",
            "query_params": {
                "variant": "primer: noir | carbon | space | anvil | porcelain | cream | dusk | petrol",
                "spec": (
                    "base64url-encoded MatrixSpec JSON (preset must be 'custom'; decoded cap 8 KB). "
                    "Presets: connectors — the generated connector-registry matrix. Arbitrary tables "
                    "also ship via POST /v1/compose with a `matrix` body."
                ),
            },
            "example": "/v1/matrix/connectors/primer.static?variant=porcelain",
        },
        "chart-stars": {
            "pattern": "/v1/chart/stars/{owner}/{repo}/{genome}.{motion}",
            "query_params": {
                "variant": variant_note,
                "pair": "automata only — silently ignored on chart (kept for URL grammar uniformity).",
            },
            "example": "/v1/chart/stars/eli64s/readme-ai/automata.static?variant=bone",
        },
    }
