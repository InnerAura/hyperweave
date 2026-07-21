"""FastMCP v3 server -- MCP tools and resources for HyperWeave.

Tools: compose, validate, discover + 3 resources (schema, genomes, motions).
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

from hyperweave import __version__

mcp = FastMCP(
    name="HyperWeave",
    version=__version__,
    instructions=(
        "Compositor API for self-contained SVG artifacts from semantic parameters. "
        "Use hw_compose for any artifact type (returns {envelope, url}, never inline SVG). "
        "Use hw_validate to check a spec without rendering. "
        "Use hw_discover to see available genomes, motions, glyphs, and frame types."
    ),
)


# ── Tools ────────────────────────────────────────────────────────────


@mcp.tool()
async def hw_compose(
    type: str = "badge",
    title: str = "",
    value: str = "",
    genome: str = "brutalist",
    state: str = "active",
    motion: str = "static",
    glyph: str = "",
    glyph_mode: str = "auto",
    regime: str = "normal",
    size: str = "default",
    shape: str = "",
    variant: str = "",
    pair: str = "",
    state_glyph_shape: str = "",
    divider_variant: str = "zeropoint",
    direction: str = "ltr",
    speeds: list[float] | None = None,
    data: str = "",
    telemetry_data: dict[str, Any] | None = None,
    genome_override: dict[str, Any] | None = None,
    connector_data: dict[str, Any] | None = None,
    stats_username: str = "",
    chart_owner: str = "",
    chart_repo: str = "",
    matrix: dict[str, Any] | None = None,
    diagram: dict[str, Any] | None = None,
    glyph_tint: str = "",
    performance: str = "",
    edge_motion: str = "",
    surface: str = "",
    ground: str = "",
    palette: str = "",
    faces: bool = False,
    face: str = "",
    render_target: str = "svg",
    format: str = "svg",
    respond: str = "envelope",
) -> dict[str, Any] | str:
    """Compose a HyperWeave artifact.

    Returns ``{envelope, url, width, height, genome, variant}`` — the actionable
    hwz/1 envelope plus a content-addressed handle to the pixels. The SVG bytes
    are cached and served at ``url``; they never travel inline (emit ``![](url)``,
    not tens of KB of markup). With ``render_target='markdown'`` returns the text
    shadow string instead. Set ``respond='svg'`` to get the raw SVG markup inline
    instead of the ``{envelope, url}`` handle — for a caller that must embed the
    pixels directly (the artifact is still cached under ``url``).

    type: badge | strip | icon | divider | marquee |
          receipt | stats | chart | matrix | diagram

    genome: primer (the on-ramp — light/dark, 8 variants noir/carbon/space/anvil/
              porcelain/cream/dusk/petrol; the ONLY diagram-capable genome) |
            brutalist (dark, sharp corners, emerald accent) |
            chrome (dark, metallic, 5 named variants: horizon/abyssal/lightning/graphite/moth) |
            automata (cellular, 16 solo tones: violet/teal/bone/steel/amber/jade/magenta/
              cobalt/toxic/solar/abyssal/crimson/sulfur/indigo/burgundy/copper
              — pair any two via ?pair=...)
            — or pass ``genome_override`` as an inline genome dict to bypass
              the built-in registry (equivalent to CLI ``--genome-file``).

    Content by frame type:
      badge:    title="STARS" value="12345" (two-panel badge)
                — or title="STARS" data="gh:owner/repo.stars" (data-driven)
      strip:    title="readme-ai" value="STARS:2.9k,FORKS:278" (metric strip)
                — or strip with data="gh:owner/repo.stars,gh:owner/repo.forks"
      icon:     glyph="github" (64x64 icon frame)
      divider:  divider_variant=block|current|takeoff|void|zeropoint|dissolve
      marquee:  title="ITEM1 | ITEM2" (pipe-separated for raw text)
                — or data="text:NEW,gh:owner/repo.stars,text:DOWNLOAD"
      receipt:  telemetry_data={session data contract dict}
      stats:    stats_username="eli64s" + connector_data={stars_total, ...}
      chart:    chart_owner/chart_repo + connector_data={points, current_stars}
      matrix:   matrix={"title": ..., "columns": [{"id","label","kind"?}...],
                "rows": [{"label","cells":[{...}]}...]} — the universal table
                IR. Columns declare kind: text|check|dot|bar|pill|numeric|
                chip|glyph (omit for auto-inference; bar/dot are caller-only).
                Cells carry value | state (full/partial/none/on/off) |
                chips[] | glyph (registry id). Optional rhetoric (caller-only):
                hero_column, headline {value,label}, summary_row, sections,
                row_glyph_tint=ink|brand. Or use
                connector_data={"matrix_adapter": "connector-registry"} for
                the generated connector matrix, or data= tokens for a simple
                metric/value table.
      diagram:  diagram={"topology": "pipeline|fanout|convergence|flywheel|
                stack|tree|comparison|sequence|dag|state-machine",
                "orientation": "horizontal|bilateral|upward|radial" (fanout;
                tree takes radial for depth>=2 mindmaps), "title": ...,
                "nodes": [{"label","desc"?,"role"?,"glyph"?,"short"?}...],
                "edges": [{"source","target","label"?,"kind"?,"direction"?}]
                — edges are required for sequence/dag/state-machine (they
                ARE the content), optional direction overlays elsewhere.
                edge_motion: dash|particle (the closed kit pair; the
                grammar is compositor-only by construction). Or use a
                server preset via the GET URL grammar.

    The ``data`` parameter is the unified data-token grammar. Forms:
      text:STRING          — raw display text
      kv:KEY=VALUE         — static literal, role-tagged
      gh:owner/repo.metric — GitHub
      pypi:pkg.metric      — PyPI
      npm:pkg.metric / hf:org/model.metric / arxiv:id.metric / docker:owner/image.metric
      crates:pkg.metric / scorecard:owner/repo.metric / dora:owner/repo.metric

    Multiple tokens are separated by ``,``. Embedded commas in text/kv
    payloads escape as ``\\,``. When ``data`` is set, this tool fetches live
    values inline (network I/O), so callers don't need to pre-fetch via
    ``connector_data``. For stats/chart frames, ``connector_data`` remains
    the pre-fetched payload pathway and is preferred when the caller already
    has the data.

    motion (badge/strip/icon): chromatic-pulse | corner-trace | dual-orbit |
                                entanglement | rimrun
    state: active | passing | building | warning | critical | failing | offline
    glyph_mode: auto | fill | wire | none
    size: default | compact
    shape: square | circle (icon frame shape, genome-dependent)
    variant: chrome → horizon | abyssal | lightning | graphite | moth
             automata → violet | teal | bone | steel | amber | jade | magenta |
                        cobalt | toxic | solar | abyssal | crimson | sulfur |
                        indigo | burgundy | copper (16 solo tones)
             empty = frame default flagship variant (cellular default = teal)
    pair: cellular paradigm pairing modifier (automata only). Composes any two
          solo tones — e.g. variant="teal" pair="violet". Bifamily frames
          (strip, divider) consume the pair; other frames silently ignore it.
          Empty = solo render.
    state_glyph_shape: badge state-indicator shape override: square | circle |
          diamond. Empty = genome/paradigm default (brutalist dark=square /
          light=circle, chrome=diamond, cellular=square).
    render_target: svg (default) | markdown (matrix: the GFM table shadow;
          diagram: the topology text shadow) | html (reserved seam — not
          implemented until v0.5).
    format: byte format of the artifact — svg (default) | svg-static (vars
          flattened, motion stripped) | png | webp. png/webp are served at
          `url` (never inline); svg-static/png/webp of an adaptive artifact are
          rejected (use faces). Orthogonal to render_target (which picks svg vs
          the markdown shadow).
    glyph_tint: glyph fill selection: ink | brand | full. Empty defers to
          the genome default; per-slot IR declarations outrank it.
          Degrades full -> gradient -> brand -> ink, never errors.
    performance: '' (paint-ok, default) | 'composite-only' — the kit grammar
          is compositor-only by construction, so both values render the same
          artifact; the payload's rendered block records the tier.
    edge_motion: '' (use the spec/preset's own) | dash | particle —
          artifact-level override of the diagram's edge motion (per-edge IR
          declarations still outrank it). Parity with the HTTP ?edge_motion=.
    surface (matrix/diagram): '' (plate) | plate | inlay | twin — how the
          artifact meets the host: plate carries its own ground, inlay borrows
          the host + adapts to its theme, twin bakes a light+dark pair.
          ground/palette are the raw axes if you'd rather set them directly.
    faces: twin only — also bake the light + dark faces; returns their URLs
          under faces:{light,dark} (the <picture> pair for a README).
    face (matrix/diagram): '' (default) | light | dark — bake ONE scheme:
          commits palette=fixed for this face, overriding an adaptive
          surface/palette request (the face wins). No 'auto' — that's
          CLI-only terminal (OSC 11) detection; MCP takes only the explicit,
          scriptable values. Exclusive with faces.
    """
    from hyperweave.compose.surface import SpecEnvelope, compose_surface
    from hyperweave.config.settings import get_settings

    if render_target not in ("svg", "markdown"):
        if render_target == "html":
            raise ValueError("render_target 'html' is a reserved seam — not implemented until v0.5")
        raise ValueError(f"unknown render_target {render_target!r} (svg | markdown)")

    # Artifact-level edge-motion override — mirrors the HTTP ?edge_motion= query
    # and the CLI --edge-motion: replaces the diagram spec's edge_motion before
    # compose (per-edge IR declarations still outrank it). Closed 2x2.
    if edge_motion:
        from hyperweave.core.diagram import EdgeMotion

        if edge_motion not in {e.value for e in EdgeMotion}:
            allowed = " | ".join(e.value for e in EdgeMotion)
            raise ValueError(f"edge_motion must be one of: {allowed}")
        if diagram is not None:
            diagram = {**diagram, "edge_motion": edge_motion}

    # Live data-token resolution (async, frame-aware) — the shared path; the
    # rich MCP params below pack into the SpecEnvelope's `spec` dict, which the
    # unified core maps onto the ComposeSpec.
    final_value = value
    data_tokens_resolved: list[Any] | None = None
    if data:
        from hyperweave.connectors.data_tokens import (
            format_for_value,
            parse_data_tokens,
            resolve_data_tokens,
        )

        tokens = parse_data_tokens(data)
        resolved, _ttl = await resolve_data_tokens(tokens)
        if type in {"marquee", "stats", "matrix"}:
            data_tokens_resolved = list(resolved)
        else:
            formatted = format_for_value(resolved)
            if formatted:
                final_value = formatted

    # Surface preset/axes → the two ComposeSpec axes. `surface` is a preset name
    # (no ComposeSpec field), so expand it here; ground/palette pack into `content`
    # and forward through compose_surface's field partition. A bad preset/axis or
    # the bare+fixed trap raises ValueError (surfaced to the MCP caller).
    surface_ground, surface_palette = "", ""
    if surface or ground or palette:
        from hyperweave.core.surface_spec import expand_surface_preset

        resolved_surface = expand_surface_preset(surface, ground, palette)
        surface_ground = resolved_surface.ground.value
        surface_palette = resolved_surface.palette.value

    # face wins: an explicit face commits palette=fixed even over an adaptive
    # surface/palette request just resolved above (CLI --face parity; no
    # 'auto' here — that's CLI-only terminal detection).
    if face:
        if face not in ("light", "dark"):
            raise ValueError(f"face must be 'light' or 'dark' (got {face!r})")
        if faces:
            raise ValueError("face (one baked scheme) and faces (the twin pair) are exclusive")
        surface_palette = "fixed"

    # markdown render_target wants the text shadow, not a byte projection — emit
    # `md` and return it directly (the compose_surface md path preserves the
    # existing "no markdown projection" error). `faces` (twin only) adds the
    # face-bake target so the response carries the light/dark URL pair.
    if render_target == "markdown":
        emit: tuple[str, ...] = ("md",)
    else:
        emit = ("svg", "compressed", "faces") if faces else ("svg", "compressed")

    if type in {"matrix", "diagram"}:
        # The IR schema PLUS the ComposeSpec-level params a matrix/diagram caller
        # may set (matrix's connector-registry adapter; diagram's performance
        # tier). compose_surface's envelope mapping lifts these back out to
        # top-level ComposeSpec fields, so every hw_compose param survives the
        # round-trip regardless of frame type (the forwarding contract).
        content: dict[str, Any] = dict((matrix if type == "matrix" else diagram) or {})
        content["performance"] = performance
        # glyph_tint's diagram-IR field is enum-strict (no ''), so forward only a
        # real selection; a matrix caller's lands as the top-level ComposeSpec
        # field (MatrixSpec has no glyph_tint) where '' is a valid default.
        if glyph_tint:
            content["glyph_tint"] = glyph_tint
        if connector_data is not None:
            content["connector_data"] = connector_data
        if genome_override is not None:
            content["genome_override"] = genome_override
    else:
        content = {
            "title": title,
            "value": final_value,
            "state": state,
            "motion": motion,
            "glyph": glyph,
            "glyph_mode": glyph_mode,
            "regime": regime,
            "size": size,
            "shape": shape,
            "pair": pair,
            "state_glyph_shape": state_glyph_shape,
            "divider_variant": divider_variant,
            "marquee_direction": direction,
            "glyph_tint": glyph_tint,
            "performance": performance,
        }
        if speeds is not None:
            content["marquee_speeds"] = speeds
        if telemetry_data is not None:
            content["telemetry_data"] = telemetry_data
        if genome_override is not None:
            content["genome_override"] = genome_override
        if connector_data is not None:
            content["connector_data"] = connector_data
        if stats_username:
            content["stats_username"] = stats_username
        if chart_owner:
            content["chart_owner"] = chart_owner
        if chart_repo:
            content["chart_repo"] = chart_repo

    # Surface axes forward as top-level ComposeSpec fields via the partition.
    if surface_ground:
        content["ground"] = surface_ground
    if surface_palette:
        content["palette"] = surface_palette
    if face:
        content["surface_face"] = face

    env = SpecEnvelope(type=type, genome=genome, variant=variant, spec=content, format=format, emit=emit)
    response = compose_surface(env, base_url=get_settings().public_base_url, data_tokens=data_tokens_resolved)

    if render_target == "markdown":
        if not response.md:
            raise ValueError(f"frame type {type!r} has no markdown projection")
        return response.md

    # {envelope, url} contract — the SVG bytes never enter the agent's context: it
    # emits ![](url) (~10 tokens), not tens of KB of markup. `respond='svg'` opts
    # into inline pixels; the artifact is cached under `url` either way.
    if respond == "svg":
        return response.svg
    result: dict[str, Any] = {
        "envelope": response.envelope,
        "url": response.url,
        "width": response.width,
        "height": response.height,
        "genome": response.genome,
        "variant": response.variant,
    }
    if response.faces is not None:
        result["faces"] = response.faces
    return result


@mcp.tool()
async def hw_validate(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate a spec envelope without rendering — returns a {valid, ...} report.

    spec: the canonical spec envelope, e.g.
        {"type": "matrix", "genome": "primer", "variant": "porcelain",
         "spec": {...frame IR...}}
    On failure the report carries the structured error envelope
    (``{"valid": false, "error": {code, message, fix, detail}}``).
    """
    from hyperweave.compose.surface import SpecEnvelope, validate_surface

    return validate_surface(
        SpecEnvelope(
            type=str(spec.get("type", "")),
            genome=str(spec.get("genome", "primer")),
            variant=str(spec.get("variant", "")),
            spec=dict(spec.get("spec") or {}),
        )
    )


async def _dispatch(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a capability on the MCP surface, rendering HwError to an envelope.

    The MCP tool bodies are one-line calls to this: the registry (not each tool)
    owns validation and the error contract, so CLI / HTTP / MCP cannot drift.
    """
    from hyperweave.config.settings import get_settings
    from hyperweave.core.errors import HwError
    from hyperweave.surfaces.registry import CallContext, dispatch

    ctx = CallContext(surface="mcp", base_url=get_settings().public_base_url)
    try:
        return await dispatch(name, payload, ctx)
    except HwError as exc:
        return exc.envelope()


@mcp.tool()
async def hw_extract(source: str, respond: str = "envelope") -> dict[str, Any]:
    """Extract the seed at a depth — envelope (compact digest) | payload (lossless) | markdown.

    ``source`` is an artifact SVG string, a /v1/a/{digest} url, or a digest/id
    (the same input the HTTP/CLI extract verbs take). The payload replants to a
    byte-identical artifact; the envelope is the ~200-token actionable read.
    ``hw_compress`` is the alias for envelope depth.
    """
    return await _dispatch("extract", {"source": source, "respond": respond})


@mcp.tool()
async def hw_compress(source: str) -> dict[str, Any]:
    """Alias for hw_extract(respond='envelope') — the kept name for the envelope-depth read."""
    return await _dispatch("extract", {"source": source, "respond": "envelope"})


@mcp.tool()
async def hw_verify(source: str) -> dict[str, Any]:
    """Recompute the hash; prove the artifact verifiably IS its data (id == sha256(payload)).

    ``source`` is an artifact SVG string, a /v1/a/{digest} url, or a digest/id.
    ``valid`` is the seed's hash proof; ``well_formed`` reports whether the SVG
    container parses as XML — independent checks, report-only.
    """
    return await _dispatch("verify", {"source": source})


@mcp.tool()
async def hw_transform(source: str, mutations: list[dict[str, Any]], respond: str = "envelope") -> dict[str, Any] | str:
    """Mutate an artifact via structural JSON patch → a new artifact.

    ``source`` is an artifact SVG string, a /v1/a/{digest} url, or a digest/id.
    Returns a handle {envelope, url, lineage, parent_id, new_id} by default —
    the SVG is cached, never inlined; fetch the ``url`` to render it. Pass
    ``respond="svg"`` for the raw markup inline (hw_compose parity).
    ``mutations`` is a list of RFC-6902 ops (add/remove/replace/move/copy/test); a
    patch that breaks the frame schema fails cleanly as SPEC_INVALID.
    """
    result = await _dispatch("transform", {"source": source, "mutations": mutations, "respond": respond})
    if respond == "svg":
        return str(result.get("svg", ""))
    return result


@mcp.tool()
async def hw_diff(a: str, b: str) -> dict[str, Any]:
    """Payload-bound structured delta between two artifacts (added/removed/changed).

    ``a`` and ``b`` are each an artifact SVG string, a /v1/a/{digest} url, or a digest/id.
    """
    return await _dispatch("diff", {"a": a, "b": b})


@mcp.tool()
async def hw_query(source: str, question: str) -> dict[str, Any]:
    """Answer a question about an artifact from its compact envelope (cheap, not faithful).

    ``source`` is an artifact SVG string, a /v1/a/{digest} url, or a digest/id.
    """
    return await _dispatch("query", {"source": source, "question": question})


@mcp.tool()
async def hw_discover(
    what: str = "all",
) -> dict[str, Any]:
    """Discover available HyperWeave components.

    what: all | genomes | motions | glyphs | frames | verbs | capabilities |
          matrix | diagram | url_grammar | schemas — plus the deep selectors
          schema:<id> (published JSON Schema, e.g. schema:diagram/1),
          example:<frame_type>/<name> (a full bundled spec, compose-ready), and
          genome:<id> (role-structured token deep-dive).
    Returns structured data about available options for hw_compose. The
    ``capabilities`` view is the living registry roster (name, summary,
    per-surface reachability) — what HyperWeave can do and where.
    """
    # One implementation of the discovery body lives in surfaces.discover so
    # the MCP / HTTP / CLI faces cannot drift (they served hand-copied dicts
    # that fell out of sync — the diagram mechanism prose and the card rename
    # landed on one face only). Routed through the registry like every other
    # adapter, so reachability claims and dispatch stay registry-truthful.
    return await _dispatch("discover", {"what": what})


# ── Resources ────────────────────────────────────────────────────────


@mcp.resource("hyperweave://schema")
async def schema_resource() -> str:
    """ComposeSpec parameter reference for hw_compose.

    Lists all valid parameter values and their constraints. For a frame BODY's
    structural JSON Schema (matrix/diagram IR), use hw_discover(what="schema:diagram/1").
    """
    from hyperweave.core.enums import (
        ArtifactStatus,
        DividerVariant,
        FrameType,
        GenomeId,
        GlyphMode,
        MotionId,
        Regime,
    )

    schema = {
        "type": [ft.value for ft in FrameType],
        "genome": [g.value for g in GenomeId],
        "motion": [m.value for m in MotionId],
        "state": [s.value for s in ArtifactStatus],
        "glyph_mode": [g.value for g in GlyphMode],
        "regime": [r.value for r in Regime],
        "divider_variant": [d.value for d in DividerVariant],
    }
    return json.dumps(schema, indent=2)


@mcp.resource("hyperweave://genomes")
async def genomes_resource() -> str:
    """Full genome configurations with colors, motions, and profiles."""
    from hyperweave.config.loader import get_loader

    loader = get_loader()
    return json.dumps(
        {gid: g for gid, g in loader.genomes.items()},
        indent=2,
    )


@mcp.resource("hyperweave://motions")
async def motions_resource() -> str:
    """Motion primitives with frame compatibility and CIM compliance."""
    from hyperweave.config.loader import get_loader

    loader = get_loader()
    return json.dumps(
        {mid: m for mid, m in loader.motions.items()},
        indent=2,
    )


@mcp.resource("hyperweave://artifact/{digest}")
async def artifact_resource(digest: str) -> str:
    """Fetch a cached artifact's SVG by content digest.

    The artifact-fetch capability as an MCP resource (not a tool) — resources
    don't flood the tool context. ``digest`` is the bare hex (or ``sha256:...``)
    of a composed artifact; resolves against the in-process LRU + the durable
    ``HW_ARTIFACT_CACHE_DIR`` disk tier, mirroring ``GET /v1/a/{digest}``. An
    uncached digest returns a short miss note (recompose to repopulate).
    """
    from hyperweave.compose.artifact_store import get_artifact

    svg = get_artifact(digest.rsplit("/", 1)[-1])
    if svg is None:
        return f"artifact {digest} not in cache — recompose (the content cache is per-process)"
    return svg


if __name__ == "__main__":
    mcp.run(transport="stdio")
