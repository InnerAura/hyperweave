"""Diagram frame resolver — coerce → cap/legality → solve → project.

Mirrors ``resolvers/matrix.py``: returns ``{"width", "height", "template",
"context"}`` and never touches SVG. The solver works in symbolic hues
(``@flow{i}`` / ``@signal`` / ``@signal2``) and accent INDICES; this
resolver substitutes the genome's ``diagram_flow`` palette and accent
family into the frozen records, so layout stays genome-blind and the
templates stamp literal values (gradients) or palette classes (dots,
branches, particles).
"""

from __future__ import annotations

import re as _re
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram import compute_diagram_layout, effective_render_cfg
from hyperweave.compose.diagram.chrome import VOICE_CLASSES, resolve_node_glyph
from hyperweave.compose.diagram.contrast import apply_glyph_contrast
from hyperweave.compose.diagram.input import coerce_diagram_input
from hyperweave.compose.diagram.palette import derive_diagram_flow
from hyperweave.compose.diagram.project import (
    PAYLOAD_SCHEMA,
    derive_subvariant,
    diagram_desc,
    diagram_envelope_data,
    diagram_payload_json,
    to_markdown,
)
from hyperweave.compose.surface_modes import flip_token, stamp_surface, surface_from_props
from hyperweave.config.loader import load_diagram_config, load_glyphs, load_surface_modes
from hyperweave.core.matrix import GlyphTint
from hyperweave.core.paradigm import MatrixVoice, ParadigmDiagramConfig

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hyperweave.compose.diagram.records import DiagramLayout
    from hyperweave.core.diagram import DiagramSpec
    from hyperweave.core.models import ComposeSpec

_MOTION_VOCAB = {
    "dash": "dash-march",
    "particle": "directional-particle",
    "beam": "gradient-window-beam",
}


_FONT_FACE = _re.compile(r"@font-face\s*\{[^}]*\}")


def _compose_embeds(dspec: Any, spec: ComposeSpec, engine: Mapping[str, Any]) -> tuple[dict[int, dict[str, Any]], Any]:
    """sec 12.1 nested composition: each ``node.embed`` composes RECURSIVELY as
    a full bare-chrome artifact of the same genome/variant (the laws recurse
    by construction), then scales into the container's content box via the
    ``embed`` engine knob. Returns (markup by node index, dspec with display
    dims stamped on the container nodes). The inner document keeps its own
    uid-scoped styles and metadata (it IS a lawful artifact riding inside
    the outer one); only its @font-face payload strips — the outer document
    provides the identical faces, so the bytes would be pure duplication."""
    if not any(n.embed is not None for n in dspec.nodes):
        return {}, dspec
    from hyperweave.compose.engine import compose as _compose_entry
    from hyperweave.core.models import ComposeSpec as _CS

    knob = engine.get("embed") or {}
    max_w = float(knob.get("max_w", 360))
    max_h = float(knob.get("max_h", 240))
    markup: dict[int, dict[str, Any]] = {}
    nodes = list(dspec.nodes)
    for i, node in enumerate(nodes):
        if node.embed is None:
            continue
        # The inner artifact rides the outer face IN FULL — variant alone is
        # not identity (a noir/dark outer story once embedded a light-faced
        # inner hub: white cards floating in the dark container).
        inner_cs = _CS(
            type="diagram",
            genome_id=spec.genome_id,
            variant=spec.variant,
            palette=spec.palette,
            ground=spec.ground,
            surface_face=spec.surface_face,
            font_mode=spec.font_mode,
            performance=spec.performance,
            chrome="bare",
            diagram=node.embed,
        )
        svg = _compose_entry(inner_cs).svg
        root_end = svg.index(">", svg.index("<svg"))
        head = svg[: root_end + 1]
        body = _FONT_FACE.sub("", svg[root_end + 1 : svg.rindex("</svg>")])
        # The nested <svg> re-projects the inner document, so its viewBox must
        # be the inner artifact's OWN viewBox — width/height are DISPLAY dims,
        # and under the content-fit law display != viewBox: using them here
        # clipped the inner body (cards past the phantom frame vanished).
        vbm = _re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', head)
        if vbm is None:
            raise ValueError("embedded artifact root carries no viewBox")
        vw, vh = float(vbm.group(1)), float(vbm.group(2))
        s = min(1.0, max_w / vw if vw else 1.0, max_h / vh if vh else 1.0)
        idm = _re.search(r'data-hw-id="([^"]+)"', head)
        nodes[i] = node.model_copy(update={"embed_dims": (round(vw * s, 1), round(vh * s, 1))})
        markup[i] = {"body": body, "vw": vw, "vh": vh, "id": idm.group(1) if idm else ""}
    return markup, dspec.model_copy(update={"nodes": tuple(nodes)})


def resolve_diagram(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    paradigm_spec: Any = None,
    surface_adapt: bool = False,
    far_palette: dict[str, Any] | None = None,
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve a diagram artifact into template + frame context."""
    paradigms_map = genome.get("paradigms") or {}
    if "diagram" not in paradigms_map:
        raise ValueError(
            f"diagram frame is not supported by genome '{genome.get('id', spec.genome_id)}' "
            "(no paradigms.diagram entry)"
        )
    cfg: ParadigmDiagramConfig = (
        paradigm_spec.diagram
        if paradigm_spec is not None and hasattr(paradigm_spec, "diagram")
        else ParadigmDiagramConfig()
    )
    engine = load_diagram_config()
    glyphs = load_glyphs()
    normalized = coerce_diagram_input(spec.connector_data, spec)
    # ``dspec`` is the RENDERED spec (a promoted cyclic dag becomes
    # state-machine); the payload keeps the caller's declared topology.
    dspec = normalized.spec
    payload_spec = normalized.payload_spec
    # LAW 3 (palette derivation): hue is variant-derived, never a universal
    # constant in effect. The DEFAULT communication palette is the variant
    # ACCENT alone — particles and dots render a single hue, tonal with the
    # muted wire. The multi-hue flow palette engages ONLY when the spec
    # declares roles (hub edge roles/zones), categories (lanes), or explicit
    # per-node accents — declared semantics earn categorical color.
    # Semantic Chromatics: ONE accent bound to the spine (see solver.
    # spine_members / assign_accents). The multi-hue flow palette survives
    # ONLY for lanes, whose category membership is a legitimate second axis;
    # every other topology gets a single accent so hue encodes the main
    # sequence, never per-node identity. Explicit per-node ``accent`` indices
    # still address the flow palette (an authored exception).
    from hyperweave.core.diagram import Topology as _Topo

    # LAW 3 palette derivation: the flow cycle is DERIVED from the variant
    # accent (compose/diagram/palette.py), never a per-variant array — a copied
    # array leaks one variant's hue onto another (the cobalt-on-cream bug where
    # porcelain's blue rendered on every light variant). A genome MAY still
    # author an explicit ``diagram_flow`` to opt out; absent that, derive.
    # flow[0] is the accent verbatim, so the spine reads in the variant's OWN
    # identity on every ground (cream brown, carbon orange, petrol teal), and
    # slots 1+ are the in-family tint ramp lanes read as category tints.
    authored_flow = [str(h) for h in (genome.get("diagram_flow") or [])]
    flow = authored_flow or derive_diagram_flow(genome, engine.get("flow_derivation") or {})
    accent_hex = flow[0]
    # A reciprocal edge pair (declared via `direction: both` sugar OR two
    # explicit opposite-direction edges) always earns its lane_hues.forward/
    # reverse slots (connector_accents, unconditionally) — those slots must
    # therefore exist in the palette, or the connector's class references a
    # -fl{i}/-flp{i} rule the defs never emitted (invisible stroke: fill:none
    # from -branch, no matching stroke rule at all). uses_flow must fire
    # whenever such a pair is present, independent of the LANES/explicit-
    # accent triggers above.
    from hyperweave.compose.diagram import motion as _mo
    from hyperweave.core.diagram import resolved_edges as _resolved_edges

    has_reciprocal_lanes = any(_mo.detect_lanes(_resolved_edges(dspec), float(engine.get("lane_offset", 4))))
    uses_flow = dspec.topology is _Topo.LANES or any(n.accent is not None for n in dspec.nodes) or has_reciprocal_lanes
    palette = flow if (uses_flow and flow) else [accent_hex]
    # The diagram's SIGNAL is its spine accent: the nucleus ring, glyph, and
    # subtext (all --dna-signal) must bind to the same blue the destination
    # titles and fan carry. The genome's general ``accent`` is a per-variant
    # identity (grey noir, orange carbon) — the wrong hue for the spine — so
    # rebind signal to the diagram-tuned accent for the CSS layer.
    if flow:
        genome = {**genome, "signal": accent_hex}
    # Connector-palette knob (chrome): 'muted' quiets STATIC/DASH wires to the
    # genome's neutral (diagram_conn_muted) while flowing particles keep the
    # colored flow palette. beam/flow edges keep the hue (their identity IS the
    # hue) — such an edge under muted stays colored and warns. Pure chrome: the
    # palette selection never touches geometry.
    conn_muted, conn_warnings = _resolve_connector_palette(dspec, genome)
    # Surface Modes: diagram_flow and diagram_conn_muted are RESOLVER-computed
    # (not plain genome-scalar fields), so the generic flip_palette() projection
    # never sees them — an adaptive far face needs its own re-derivation, reusing
    # the far ground/accent flip_palette() already solved for this genome (passed
    # in as `far_palette`). diagram_flow is a communication palette whose HUE
    # identity holds (like --dna-signal already does) but whose LIGHTNESS must
    # re-target the far substrate's legibility band — held byte-identical it goes
    # near-invisible wherever a chip/label/dot riding an explicit accent index
    # sits on a background that ALSO flips (an edge-chip's `-tag` text loses the
    # cascade to its `-flp{i}` accent-hijack class, and diagram_flow[i] never
    # changed on the far face: contrast collapsed to ~1.1 on cream). Both stay
    # empty when not adaptive — zero cost, zero template branching for plate.
    diagram_flow_far: list[str] = []
    diagram_conn_muted_far = ""
    if surface_adapt and far_palette and far_palette.get("accent"):
        far_substrate = (
            "dark" if str(genome.get("substrate_kind") or genome.get("category") or "light") == "light" else "light"
        )
        diagram_flow_far = derive_diagram_flow(
            {"accent": far_palette["accent"], "substrate_kind": far_substrate}, {"slots": len(palette)}
        )
        conn_muted_hex = str(genome.get("diagram_conn_muted", ""))
        near_ground = str(genome.get("surface_0") or "")
        far_ground = str(far_palette.get("surface_0") or "")
        if conn_muted_hex and near_ground and far_ground:
            diagram_conn_muted_far = flip_token(
                conn_muted_hex, near_ground, far_ground, role="border", cfg=load_surface_modes()
            )
    embed_markup, dspec = _compose_embeds(dspec, spec, engine)
    selections = _glyph_selections(dspec, spec, genome)
    layout = compute_diagram_layout(
        dspec,
        paradigm=cfg,
        engine=engine,
        palette_len=len(palette),
        composite_only=spec.performance == "composite-only",
        # The composition's own chrome mode wins (obi's captionless sheet);
        # the compose-level value covers the rest — including 'bare', which
        # only the recursive embed seam sets.
        chrome=dspec.chrome or spec.chrome,
        glyph_registry=glyphs,
        glyph_selections=selections,
        warnings=normalized.warnings,
    )
    # sec 6: the compiler teaches — advisory diagnostics measured on the
    # solved layout, surfaced on every surface, never a refusal.
    from hyperweave.compose.diagram.diagnostics import run_diagnostics

    diagnostics = run_diagnostics(dspec, layout, genome=genome, engine=engine, palette_len=len(palette))
    layout = apply_glyph_contrast(
        layout,
        genome=genome,
        registry=glyphs,
        engine=engine,
        rebuild=lambda glyph_id, tint, cx, cy, size: resolve_node_glyph(
            glyph_id, glyphs, tint, cx=cx, cy=cy, size=size
        ),
        # Twin awareness: far_palette is the sparse flip_palette() dict (surface_0/
        # surface_1 among its fields), empty for a plate render — a brand/full mark
        # that reads fine on the near card but goes invisible on the twin's far
        # card (the anthropic/openai near-black wordmark bug) now degrades toward
        # ink instead of shipping a literal hex that never re-inks with the face.
        far_genome=far_palette,
    )
    # Subvariant tracks what RENDERED (the promoted slug); the payload keeps
    # the caller's spec so a re-render reproduces exactly what was declared.
    subvariant = derive_subvariant(dspec)
    # Stamp the resolved surface (plate/inlay/twin) onto the PAYLOAD spec before
    # the dump — the content address derives from the payload, so a non-plate
    # surface must ride there to give each surface a distinct address. Plate
    # leaves it untouched (surface=None), keeping pre-existing payloads
    # byte-identical.
    payload_spec = stamp_surface(
        payload_spec,
        surface_from_props(spec.ground, spec.palette, spec.surface_face),
        genome,
        "diagram",
        load_surface_modes(),
    )
    payload_json = diagram_payload_json(payload_spec, layout.rendered)
    # §2/§10.1a AMENDED: the region map is PUBLIC anatomy but CHROME-VARIANT
    # (masthead/footer bboxes exist only under card chrome), and the payload
    # must stay chrome-invariant — the envelope digest is artifact identity
    # and chrome sits outside it (P4, pinned on the serve surface). The map
    # therefore rides its own sidecar block, like hw:envelope.
    import json as _json

    regions_json = _json.dumps([r.as_payload() for r in layout.regions], separators=(",", ":"))

    # Scheme-keyed material gate (surface invariance): the rendered look is a
    # pure function of (spec, genome, variant, scheme) — never of the delivery
    # mechanism. A baked face commits its scheme; a fixed palette renders the
    # variant's native substrate; an adaptive palette is light-base +
    # dark-@media-branch (normalized ordering — surface_modes invariant 3), so
    # the material rides the media block: fill/stroke/filter are CSS
    # presentation properties, url(#…) material flips where
    # var()-in-stop-color cannot.
    native_dark = str(genome.get("substrate_kind") or genome.get("category") or "light") == "dark"
    if spec.surface_face:
        dark_scheme = spec.surface_face == "dark"
        dark_branch = False
    elif surface_adapt:
        dark_scheme = False
        dark_branch = True
    else:
        dark_scheme = native_dark
        dark_branch = False
    diagram_dark = genome.get("diagram_dark") if (dark_scheme or dark_branch) else None
    if diagram_dark:
        # Card-ramp ruling: the face is a 3-stop EASED ramp — card_mid is
        # DERIVED (hi mixed toward lo by the chassis fraction), never authored
        # per variant, so every variant's crown falls at the same eased rate.
        mix_t = float((engine.get("material") or {}).get("ramp_mid_mix", 0.58))
        card_mid = _mix_hex(str(diagram_dark["card_hi"]), str(diagram_dark["card_lo"]), mix_t)
        diagram_dark = {**diagram_dark, "card_mid": card_mid}

    context: dict[str, Any] = {
        "diagram_layout": layout,
        "diagram_chrome": spec.chrome,
        # Hero-ring ruling (2026-07-13): role:hero rings in the genome accent by
        # default; 'quiet' opts a spec back into the flat family border (herobg/
        # herocirclebg dispatch in primer-defs.j2).
        "hero_ring_quiet": dspec.hero_ring == "quiet",
        "diagram_cfg": cfg,
        "viewbox_w": layout.width,
        "viewbox_h": layout.height,
        "diagram_flow": palette,
        # Far-face counterparts (see the Surface Modes note above `conn_muted`'s
        # resolution) — empty lists/strings when not adaptive.
        "diagram_flow_far": diagram_flow_far,
        # Muted-connector chrome: the flag drives the template's static/dash
        # connectors onto the neutral class; particles + beam/flow keep `palette`.
        "conn_muted": conn_muted,
        # Dark plate physics (primer_diagram_language): the variant's
        # extracted material block — cf/es gradients + seat shadow + the dark
        # ink family — applies on every render whose resolved scheme includes
        # the dark face: baked dark face, fixed dark-substrate variant, or the
        # dark branch of an adaptive render.
        "diagram_dark": diagram_dark,
        # True when the material belongs to the adaptive DARK BRANCH rather
        # than the committed base scheme — the template ships the override
        # block inside @media (prefers-color-scheme: dark).
        "diagram_dark_adaptive": bool(diagram_dark) and dark_branch,
        "diagram_conn_muted": str(genome.get("diagram_conn_muted", "")),
        "diagram_conn_muted_far": diagram_conn_muted_far,
        "diagram_style": _style_params(engine),
        # Voice CSS emits from the SAME topology-adjusted config the solver
        # measured with (chassis voice overrides, e.g. lanes' 10px descs) —
        # emitted font sizes can never drift from measured geometry.
        "diagram_voices": _voice_params(effective_render_cfg(dspec, cfg)),
        "diagram_glyph_gradients": _used_glyph_gradients(layout, glyphs),
        # Beam paint (motion == beam): each beam edge's (body, front) gradient
        # window pair, flattened for the defs loop; the beam's stroke stack
        # references them by id. Empty on every beam-free artifact.
        "diagram_beam_gradients": [g for c in layout.connectors for g in c.beam],
        "payload_json": payload_json,
        "regions_json": regions_json,
        "embed_markup": embed_markup,
        "diagnostics": [d.as_dict() for d in diagnostics],
        "payload_schema": PAYLOAD_SCHEMA,
        "diagram_envelope_data": diagram_envelope_data(dspec),
        "diagram_intent": spec.intent or f"topology diagram: {dspec.title or dspec.topology.value}",
        "markdown_shadow": to_markdown(dspec),
        "title_text": dspec.title or f"{dspec.topology.value} diagram",
        "desc_text": diagram_desc(dspec, subvariant=subvariant),
        "data_hw_subvariant": subvariant,
        "data_hw_topology": dspec.topology.value,
        # Honesty (P6a): the root data-hw-motion flag and hw:spatial-notes must
        # describe the RENDERED artifact, not a genome-default guess. Both derive
        # from the solved layout — motion from what actually animates, notes from
        # the real canvas + layout_slug orientation. They override the base
        # context's defaults via ctx.update(resolved.frame_context).
        "data_hw_motion": "animated" if _layout_animates(layout) else "static",
        "spatial_notes": _spatial_notes(layout, engine),
        "performance_tier": layout.rendered.performance,
        "motion_vocabulary": _motion_vocabulary(layout),
        "diagram_title": dspec.title,
        "diagram_text_surface": _text_surface(layout),
        # Normalization warnings (e.g. cyclic-dag promotion) + the muted-knob's
        # beam/flow applicability warning flow to the engine's
        # ComposeResult.warnings and the CLI's stderr. Empty for a clean input,
        # so the common path keeps a byte-identical payload.
        "warnings": [*layout.rendered.warnings, *conn_warnings],
    }
    return {
        "width": layout.display_w,
        "height": layout.display_h,
        "template": "frames/diagram.svg.j2",
        "context": context,
    }


def _glyph_selections(dspec: DiagramSpec, spec: ComposeSpec, genome: dict[str, Any]) -> tuple[GlyphTint, ...]:
    """The tint selection chain: per-slot > artifact IR > caller param >
    genome per-frame default > ink. Degradation through what each registry
    entry carries happens at placement; the rendered mode lands in the
    payload's ``rendered.glyph_tint``."""
    frame_default = spec.glyph_tint or str((genome.get("glyph_tint") or {}).get("diagram", "")) or "ink"
    artifact = dspec.glyph_tint or GlyphTint(frame_default)
    return tuple(node.glyph_tint or artifact for node in dspec.nodes)


def _resolve_connector_palette(dspec: DiagramSpec, genome: dict[str, Any]) -> tuple[bool, list[str]]:
    """Resolve the connector-palette knob to (active, warnings).

    MUTED IS THE DEFAULT: STATIC/DASH wires quiet to the genome's
    ``diagram_conn_muted`` neutral unless the caller opts back into hue with
    ``connector_palette='colored'`` (the five-color wire rainbow is opt-in
    chrome, not the baseline). beam/flow edges keep the colored flow palette
    under muted (their identity is the hue) — an EXPLICIT ``'muted'`` request
    with such edges triggers a single warning naming them (per-edge
    applicability); the silent default does not warn, because colored motion
    wires under a muted baseline are the design, not a surprise. The knob is
    a no-op unless the genome supplies ``diagram_conn_muted`` — a missing
    value is caught loudly at config load, not here.
    """

    if dspec.connector_palette == "colored":
        return False, []
    if not str(genome.get("diagram_conn_muted", "")):
        return False, []

    # The beam's identity is a FIXED blue/purple pair (never accent- or
    # genome-derived) and every other kit motion keeps the muted connector
    # palette cleanly, so a 'muted' request needs no colored-edge warning
    # sweep. (Flow, the hue-carrying tube, stays retired.)
    return True, []


def _mix_hex(a: str, b: str, t: float) -> str:
    """``a`` mixed toward ``b`` by ``t`` in sRGB, rounded once per channel —
    the card-ramp mid stop derivation (compose owns the color math; the
    template stamps the result)."""
    ar, ag, ab = (int(a.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    br, bg, bb = (int(b.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    mr, mg, mb = round(ar + (br - ar) * t), round(ag + (bg - ag) * t), round(ab + (bb - ab) * t)
    return f"#{mr:02X}{mg:02X}{mb:02X}"


def _style_params(engine: dict[str, Any]) -> dict[str, Any]:
    """The scalar style constants the defs CSS stamps (engine-config
    sourced; the chassis paints arrive as --dna-* roles instead)."""
    conn = engine["connector"]
    track = engine["track"]
    entrance = engine["entrance"]
    return {
        "stroke_width": conn["stroke_width"],
        "dash": conn["dash"],
        "linecap": conn["linecap"],
        "ants_dur": conn["ants_dur"],
        "ants_dur_bypass": conn.get("ants_dur_bypass", conn["ants_dur"]),
        "ants_offset_to": conn["ants_offset_to"],
        "gather_ring_r": conn.get("gather_ring_r", 5),
        "gather_core_r": conn.get("gather_core_r", 2.5),
        "gather_pulse_dur": conn.get("gather_pulse_dur", "2.6s"),
        "health_dot_r": (engine.get("health") or {}).get("dot_r", 5),
        "health_pulse_dur": (engine.get("health") or {}).get("pulse_dur", "2.618s"),
        # Dark-face card material (card-ramp ruling): eased ramp midpoint +
        # the strip-recipe grain scalars the material filters stamp.
        "ramp_mid_offset": (engine.get("material") or {}).get("ramp_mid_offset", "0.4"),
        "grain_base_frequency": (engine.get("material") or {}).get("grain_base_frequency", "1.6"),
        "grain_octaves": (engine.get("material") or {}).get("grain_octaves", "2"),
        "grain_seed": (engine.get("material") or {}).get("grain_seed", "19"),
        "grain_tint": (engine.get("material") or {}).get("grain_tint", "0.04"),
        "grain_alpha": (engine.get("material") or {}).get("grain_alpha", "0.08"),
        "march_opacity": track["march_opacity"],
        "return_drift_dash": track["return_drift_dash"],
        "return_drift_dur": track["return_drift_dur"],
        "return_drift_offset": track["return_drift_offset"],
        "legend_dash": track.get("legend_dash", "5 5"),
        "fade_dur": entrance["fade_dur"],
        "fade_ease": entrance["fade_ease"],
        # Beam layer constants (the reference-specimen recipe) — the 5-stroke stack the
        # template stamps: glass conduit (casing + rail) under glow/core/front.
        "beam_casing_w": (engine.get("beam") or {}).get("casing", {}).get("width", 6),
        "beam_casing_op": (engine.get("beam") or {}).get("casing", {}).get("opacity", 0.07),
        "beam_rail_w": (engine.get("beam") or {}).get("rail", {}).get("width", 1.5),
        "beam_rail_op": (engine.get("beam") or {}).get("rail", {}).get("opacity", 0.26),
        "beam_rail_reduced_op": (engine.get("beam") or {}).get("reduced_motion_rail_opacity", 0.5),
        "beam_glow_w": (engine.get("beam") or {}).get("glow", {}).get("width", 5),
        "beam_glow_op": (engine.get("beam") or {}).get("glow", {}).get("opacity", 0.55),
        "beam_glow_blur": (engine.get("beam") or {}).get("glow", {}).get("blur_stddev", 2.2),
        "beam_core_w": (engine.get("beam") or {}).get("core", {}).get("width", 2),
        "beam_front_w": (engine.get("beam") or {}).get("front", {}).get("width", 1.15),
        "beam_blur_x": (engine.get("beam") or {}).get("blur_region", {}).get("x", "-20%"),
        "beam_blur_y": (engine.get("beam") or {}).get("blur_region", {}).get("y", "-400%"),
        "beam_blur_w": (engine.get("beam") or {}).get("blur_region", {}).get("width", "140%"),
        "beam_blur_h": (engine.get("beam") or {}).get("blur_region", {}).get("height", "900%"),
    }


def _voice_params(cfg: ParadigmDiagramConfig) -> list[dict[str, Any]]:
    """Type-voice CSS parameters — the same family/size/weight tuples the
    solver measured with (the chrome VOICE_CLASSES registry is the single
    coupling point)."""

    def stack(family: str) -> str:
        if family == "Inter":
            return "var(--dna-font-display, 'Inter', system-ui, sans-serif)"
        return "var(--dna-font-mono, 'JetBrains Mono', ui-monospace, monospace)"

    out: list[dict[str, Any]] = []
    for name, attr in VOICE_CLASSES:
        voice = getattr(cfg, attr)
        assert isinstance(voice, MatrixVoice)
        out.append(
            {
                "name": name,
                "stack": stack(voice.family),
                "size": voice.size,
                "weight": voice.weight,
                "tracking": voice.tracking_em,
            }
        )
    return out


def _used_glyph_gradients(layout: DiagramLayout, glyphs: dict[str, Any]) -> list[dict[str, Any]]:
    """One linearGradient def per brand-gradient mark the layout placed."""
    ids: list[str] = []
    for node in layout.nodes:
        if node.glyph is not None and node.glyph.gradient and node.glyph.gradient not in ids:
            ids.append(node.glyph.gradient)
    gradients: list[dict[str, Any]] = []
    for glyph_id in ids:
        gradient = (glyphs.get(glyph_id) or {}).get("gradient")
        if isinstance(gradient, dict):
            gradients.append({"id": glyph_id, **gradient})
    return gradients


def _layout_animates(layout: DiagramLayout) -> bool:
    """Does the RENDERED diagram actually animate? (honesty.motion-flag)

    Mirrors, condition-for-condition, what ``primer-defs.j2`` /
    ``primer-content.j2`` emit: a rendered beam sweeps its gradient windows
    (``animateTransform`` — real motion, the beam reference specimens' own
    motion="animated" declaration); a particle rides an ``<animateMotion>``;
    the CSS ``@keyframes``/``animation`` blocks are each gated on one layout
    fact — entrance fade, a gather pulse, a live dash-march track, or a
    dash-drift (sequence return) track. If none of those hold, no keyframes
    and no SMIL reach the document and the artifact is genuinely static."""
    if any(c.beam for c in layout.connectors if not c.inert):
        return True
    if layout.particles:
        return True
    if layout.entrance == "fade":
        return True
    if layout.gathers:
        return True
    for c in layout.connectors:
        if c.track == "dash-march" and not c.inert:
            return True
        if c.track == "dash-drift":
            return True
    return False


def _spatial_notes(layout: DiagramLayout, engine: Mapping[str, Any]) -> str:
    """The MEASURED hw:spatial-notes clause (honesty.notes-*): real canvas
    (the viewBox the document stamps), render size, layout-slug orientation,
    and the node/edge census. No fabricated rhetoric — every token is read off
    the solved layout, so the numbers match the geometry and the orientation
    phrase never says 'left-to-right' on a radial layout."""
    phrases = engine.get("orientation_phrases") or {}
    orient = str(phrases.get(layout.layout_slug, layout.layout_slug))
    return (
        f"{layout.width}x{layout.height}, render {layout.display_w}x{layout.display_h}; "
        f"{orient}; {len(layout.nodes)} nodes, {len(layout.connectors)} edges"
    )


def _motion_vocabulary(layout: DiagramLayout) -> str:
    """Specimen-derived motion names for ``hw:motion vocabulary``."""
    names: list[str] = []
    replay = layout.layout_slug == "sequence"
    for m, c in zip(layout.rendered.edge_motion, layout.connectors, strict=False):
        if c.inert:
            continue
        word = _MOTION_VOCAB.get(m, m)
        if m == "particle" and replay:
            word = "ordered-replay-particle"
        if word not in names:
            names.append(word)
        if c.track == "dash-march" and "dash-march" not in names:
            names.append("dash-march")
    return " ".join(names) if names else "static"


def _text_surface(layout: DiagramLayout) -> list[str]:
    """Every string the SVG renders — feeds the font subsetter."""
    strings: list[str] = []
    if layout.header.title is not None:
        strings.append(layout.header.title.text)
    if layout.header.subtitle is not None:
        strings.append(layout.header.subtitle.text)
    for n in layout.nodes:
        strings.append(n.label.text)
        strings.extend(line.text for line in n.desc_lines)
        if n.short is not None:
            strings.append(n.short.text)
        if n.tag is not None:
            strings.append(n.tag.text)
    # Annotation chrome (subsumed edge labels + caller callouts/badges/pins/
    # asides/legends) — every run the annotate pass placed. Edge labels moved
    # here from ConnectorPlacement.label_lines; the subsetter must still see
    # them or a migrated label would render with missing glyphs.
    for a in layout.annotations:
        strings.extend(line.text for line in a.lines)
        strings.extend(e.text.text for e in a.entries)
    for band in layout.lane_bands:
        strings.append(band.header.text)
        if band.count is not None:
            strings.append(band.count.text)
    # Operator marks (stack) are drawn geometry (ring + cross) — no glyphs to subset.
    if layout.legend is not None:
        strings.append(layout.legend.text)
    if layout.footer is not None:
        strings.append(layout.footer.text)
    return [s for s in strings if s]
