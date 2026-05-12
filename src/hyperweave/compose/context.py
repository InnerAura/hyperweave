"""Frame context builders — per-frame template variable construction.

Each builder produces the COMPLETE context dict for its frame type's Jinja2
template.  Common variables (uid, css, metadata, content) come from
``_base_context()``.  Frame-specific defaults are only set for their frame.

Motion SVG is injected by ``_inject_motion()`` after the context is built.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from hyperweave import __version__
from hyperweave.core.enums import ArtifactStatus, FrameType, MotionId

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec, ResolvedArtifact

from hyperweave.compose.assembler import fonts_for_frame, frame_needs_fonts
from hyperweave.compose.reasoning import load_reasoning
from hyperweave.render.fonts import load_font_face_css

_CtxBuilder = Callable[["ComposeSpec", "ResolvedArtifact", dict[str, str]], dict[str, Any]]


def _compose_font_stack(resolved: ResolvedArtifact) -> str:
    """Compose the metadata `font_stack` string from the resolved genome.

    Light-substrate variants pair the scholar heading font (Barlow Condensed) with
    the body monospace; dark variants get the display + mono pair. Empty genomes
    fall back to "system-ui" as a last resort.
    """
    genome = resolved.genome
    substrate = genome.get("substrate_kind") or genome.get("category", "dark")
    mono = genome.get("font_mono") or (genome.get("typography") or {}).get("mono_font", "")
    display = genome.get("font_display") or (genome.get("typography") or {}).get("hero_font", "")
    if substrate == "light":
        heading = genome.get("scholar_heading_font") or display
        return ", ".join(p for p in (heading, mono) if p) or "system-ui"
    return ", ".join(p for p in (display, mono) if p) or "system-ui"


def _hex_to_relative_luminance(hex_color: str) -> float | None:
    """Compute relative luminance for a #RRGGBB hex color (WCAG formula)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return None
    try:
        r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return None

    def _channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def _resolve_reasoning_context(spec: ComposeSpec, resolved: ResolvedArtifact) -> dict[str, str]:
    """Resolve per-frame reasoning strings into context fields.

    Per-request overrides (spec.intent/approach/tradeoffs) take precedence over
    YAML-loaded defaults, matching the Phase 9 design — escape hatch for
    bespoke artifacts. Empty per-request fields fall through to the YAML loader.
    Returns context fragment with reasoning_* keys; missing reasoning emits
    empty strings so the metadata template's default-fallback fires cleanly.
    """
    substrate = resolved.genome.get("substrate_kind") or resolved.genome.get("category", "dark")
    yaml_reasoning = load_reasoning(spec.genome_id, spec.type, substrate)
    intent = spec.intent or (yaml_reasoning.intent if yaml_reasoning else "")
    approach = spec.approach or (yaml_reasoning.approach if yaml_reasoning else "")
    tradeoffs = spec.tradeoffs or (yaml_reasoning.tradeoffs if yaml_reasoning else "")
    return {
        "reasoning_intent": intent,
        "reasoning_approach": approach,
        "reasoning_tradeoffs": tradeoffs,
    }


def _compute_contrast_ratio(fg_hex: str, bg_hex: str) -> str:
    """Return WCAG contrast ratio like "7.2:1" or empty if inputs unusable."""
    if not fg_hex or not bg_hex:
        return ""
    fg_lum = _hex_to_relative_luminance(fg_hex)
    bg_lum = _hex_to_relative_luminance(bg_hex)
    if fg_lum is None or bg_lum is None:
        return ""
    lighter = max(fg_lum, bg_lum)
    darker = min(fg_lum, bg_lum)
    ratio = (lighter + 0.05) / (darker + 0.05)
    return f"{ratio:.1f}:1"


def _load_font_faces(genome: dict[str, Any], frame_type: str) -> str:
    """Load embedded font CSS for ``frame_type``, filtered to slugs the frame
    actually renders.

    Intersects the genome's declared ``fonts`` list with the per-frame allowlist
    returned by :func:`fonts_for_frame`. A genome that declares all 3 fonts
    (chakra-petch, orbitron, jetbrains-mono) will only embed Orbitron when the
    frame is a marquee, saving ~55KB per artifact. Frames absent from the
    allowlist (icon, divider) get an empty allowed set and embed zero fonts.

    The intersection is order-preserving against the genome's declared list so
    @font-face declarations render in genome-author intent order.
    """
    declared = genome.get("fonts") or ["jetbrains-mono"]
    if not isinstance(declared, list):
        declared = ["jetbrains-mono"]
    allowed = fonts_for_frame(frame_type)
    if not allowed:
        return ""
    filtered = [slug for slug in declared if slug in allowed]
    return load_font_face_css(filtered)


def build_context(
    spec: ComposeSpec,
    resolved: ResolvedArtifact,
    css_bundle: dict[str, str],
) -> dict[str, Any]:
    """Dispatch to the per-frame context builder."""
    _BUILDERS: dict[str, _CtxBuilder] = {
        FrameType.BADGE: _ctx_badge,
        FrameType.STRIP: _ctx_strip,
        FrameType.ICON: _ctx_icon,
        FrameType.DIVIDER: _ctx_divider,
        FrameType.MARQUEE_HORIZONTAL: _ctx_marquee,
        FrameType.RECEIPT: _ctx_receipt,
        FrameType.RHYTHM_STRIP: _ctx_rhythm_strip,
        FrameType.MASTER_CARD: _ctx_master_card,
        FrameType.CATALOG: _ctx_catalog,
        FrameType.STATS: _ctx_stats,
        FrameType.CHART: _ctx_chart,
    }
    builder = _BUILDERS.get(spec.type, _ctx_badge)
    ctx = builder(spec, resolved, css_bundle)
    _inject_motion(ctx, spec, resolved)
    return ctx


# ── Base context (shared by all frames) ──────────────────────────────


def _base_context(
    spec: ComposeSpec,
    resolved: ResolvedArtifact,
    css_bundle: dict[str, str],
) -> tuple[dict[str, Any], str, str]:
    """Build the shared context dict. Returns (context, uid, artifact_id)."""
    artifact_id = str(uuid.uuid7()) if hasattr(uuid, "uuid7") else str(uuid.uuid4())
    uid = f"hw-{artifact_id[:8]}"

    css_parts = [
        css_bundle["genome"],
        css_bundle.get("bridge", ""),
        css_bundle["expression"],
        css_bundle["status"],
        css_bundle["accessibility"],
        css_bundle.get("telemetry", ""),
        css_bundle.get("motion", ""),
    ]
    # Debug comment listing included CSS modules (Tier 1B). Per-frame font gate
    # surfaces here too so `grep "hw:css-modules"` across outputs/proofset/ can
    # confirm fonts were correctly excluded for icons/dividers.
    module_names = [k for k, v in css_bundle.items() if v]
    if frame_needs_fonts(spec.type):
        module_names.append("fonts")
    css_debug = f"/* hw:css-modules: {','.join(module_names)} */"
    css_assembled = css_debug + "\n" + "\n".join(p for p in css_parts if p)

    profile = resolved.profile

    ctx: dict[str, Any] = {
        # Identity
        "uid": uid,
        "artifact_id": artifact_id,
        "contract_id": artifact_id,
        "frame_type": spec.type,
        "genome_id": spec.genome_id,
        "genome_category": resolved.genome.get("category", "dark"),
        # v0.3.2: variant + substrate_kind plumbed through to templates.
        # substrate_kind drives the brutalist split-template dispatcher
        # (`brutalist-{substrate_kind}-content.j2`). When a variant override
        # declares substrate_kind it's already merged onto resolved.genome
        # by the resolver, so a single getattr suffices. Empty/missing falls
        # back to "dark" (current and all pre-v0.3.2 genome behavior).
        "variant": resolved.resolved_variant,
        "substrate_kind": resolved.genome.get("substrate_kind", "dark"),
        # v0.3.2 Phase D: panel_gradient_stops + seam_color exposed to templates
        # so light-substrate defs.j2 can render the dark academic panel gradient
        # (`url(#{{ uid }}-panel)`) and per-variant gold seam color. Variants
        # declare these in genome.json variant_overrides → merged into genome by
        # resolver → plumbed here. Dark variants return None / "" (gradient
        # rendering gated by template `{% if panel_gradient_stops %}` guard).
        "panel_gradient_stops": resolved.genome.get("panel_gradient_stops") or [],
        "seam_color": resolved.genome.get("seam_color", ""),
        "profile_id": resolved.profile_id,
        "_genome_raw": resolved.genome,
        "divider_variant": spec.divider_variant,
        "status": spec.state,
        "state": spec.state,
        "regime": spec.regime,
        "size": spec.size,
        "motion_id": resolved.motion,
        "motion": resolved.motion,
        "metadata_tier": spec.metadata_tier,
        # Dimensions
        "width": resolved.width,
        "height": resolved.height,
        # CSS
        "css": css_assembled,
        # Content
        "title": spec.title,
        "label": spec.title,
        "value": spec.value,
        "description": spec.value,
        "slots": [s.model_dump() for s in spec.slots],
        "numeric_value": spec.numeric_value,
        "data_hw_value": spec.numeric_value,
        # v0.2.25: SVG-root attribute that gates threshold-CSS auto-tinting.
        # Default "off" = stateless; resolvers override via frame_context.
        # Values: "off" (stateless), "auto" (stateful, threshold-CSS may fire),
        # "explicit" (?state= set; user owns the state, no auto-inference).
        "data_hw_statemode": "off",
        # Profile
        "profile": profile,
        "badge_corner": profile.get("badge_corner", 3.33),
        "strip_corner": profile.get("strip_corner", 5),
        "accent_bar_width": profile.get("strip_accent_width", 0),
        "status_shape": profile.get("status_shape", "circle"),
        # Glyph
        "glyph_id": resolved.glyph_id,
        "glyph_path": resolved.glyph_path,
        "glyph_viewbox": resolved.glyph_viewbox or "0 0 640 640",
        "glyph_mode": spec.glyph_mode,
        "has_glyph": bool(resolved.glyph_id),
        "glyph_svg": _build_glyph_svg(
            resolved,
            spec.glyph_mode,
            resolved.frame_context.get("glyph_fill", "var(--dna-signal)"),
        ),
        # Metadata / accessibility
        "title_text": _aria_title(spec),
        "desc_text": _aria_desc(spec),
        # Document-level attributes (used by document.svg.j2 base template)
        "terminal_id": "",
        "rule_id": "",
        # Motion SVG placeholders
        "motion_svg": "",
        "motion_border_defs": "",
        "motion_border_overlay": "",
        # Telemetry
        "telemetry": spec.telemetry_data or {},
        # Timestamp
        "created": datetime.now(UTC).isoformat(),
        "created_at": datetime.now(UTC).isoformat(),
        # Version -- read by templates/components/metadata.svg.j2
        "version": __version__,
        # v0.3.2 Phase 8b: metadata-pipeline context wiring. Every field below
        # was previously hardcoded as a Jinja2 `default('...')` fallback in
        # metadata.svg.j2 — meaning the template silently emitted the same
        # values regardless of genome or variant. Now sourced from genome JSON
        # / spec / resolved-motion so every artifact emits accurate metadata.
        # MUST land before metadata.svg.j2 drops its fallbacks (Phase 8c) or
        # StrictUndefined will crash every render.
        "series": spec.series,
        "platform": spec.platform,
        # Stratum: ontological Ring classification (002-TRIBE for brutalist).
        # Empty string for genomes that haven't declared one yet (chrome,
        # automata) — metadata block omits the field via `{% if stratum %}` gate.
        "stratum": resolved.genome.get("stratum", ""),
        # Theme category — variant-aware: a brutalist artifact rendered with
        # the `pulse` variant emits "light" because the variant overrides
        # substrate_kind; a `celadon` variant emits "dark"; a chrome artifact
        # falls back to the base genome's `category` field.
        "theme_category": resolved.genome.get("substrate_kind") or resolved.genome.get("category", "dark"),
        # Palette identifier — variant-aware. Empty string when no variant is
        # active (bare URL), else the variant slug. Lets a training corpus
        # distinguish chrome.abyssal from chrome.horizon in `hw:aesthetic`.
        "palette": resolved.resolved_variant or resolved.genome.get("id", ""),
        # Rhythm base — pulled from genome's `rhythm_base` field (e.g.
        # "2.618s"). Empty falls through to template default for genomes that
        # don't declare it.
        "rhythm_base": resolved.genome.get("rhythm_base", ""),
        # Font stack — substrate-aware. Light scholar artifacts get the
        # scholar heading font alongside the mono body; dark artifacts get
        # the display + mono pair.
        "font_stack": _compose_font_stack(resolved),
        # Material depth — from genome.material.depth nested dict (e.g.
        # "flat", "deep"). Empty falls back to template default.
        "material_depth": (resolved.genome.get("material") or {}).get("depth", ""),
        # Form language — from genome.structural.data_layout (e.g.
        # "brutalist", "geometric"). Indicates the artifact's compositional
        # grammar for metadata consumers.
        "form_language": (resolved.genome.get("structural") or {}).get("data_layout", ""),
        # Contrast ratio — simple WCAG-style approximation of ink-on-surface.
        # Empty when ink or surface_0 missing.
        "contrast_ratio": _compute_contrast_ratio(resolved.genome.get("ink", ""), resolved.genome.get("surface_0", "")),
        # CIM compliance — placeholder. Motion-side helper (cim_compliant
        # check against MotionId vocabulary) not yet extracted; refactoring
        # to read the actual motion compliance bit is queued for v0.3.3.
        "cim_compliant": "true",
        # Reasoning — per-frame x per-substrate intent/approach/tradeoffs
        # sourced from data/reasoning/{genome}.yaml. ReasoningFields min_length
        # enforced at load time; missing entries return None and the metadata
        # template emits empty hw:reasoning fields gracefully.
        **_resolve_reasoning_context(spec, resolved),
        # Embedded fonts (base64 @font-face CSS) — gated per frame_type via
        # frame_needs_fonts() and filtered per frame's font allowlist via
        # fonts_for_frame(). Icons / dividers receive empty string (not in
        # _NEEDS_FONTS dict) so template-level {{ font_faces }} renders
        # nothing. Marquee receives Orbitron only; chart receives Orbitron +
        # JetBrains Mono. The frame-aware filtering mirrors the per-frame CSS
        # module pattern at assembler.py:14-32.
        "font_faces": _load_font_faces(resolved.genome, spec.type) if frame_needs_fonts(spec.type) else "",
    }
    return ctx, uid, artifact_id


# ── Per-frame builders ───────────────────────────────────────────────


def _ctx_badge(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_strip(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_icon(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx["icon_variant"] = "brutalist-square"  # safe default; resolver overrides
    ctx["glyph_svg_inline"] = ""
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_divider(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_marquee(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    """Context defaults for the marquee-horizontal frame.

    v0.2.16: LIVE label panel removed entirely. The shared template now
    expects paradigm-driven typography (font_size, font_weight,
    letter_spacing, scroll_font_family) and structural separator config
    (separator_kind, separator_size, separator_glyph, separator_color)
    plus text-fill-mode dispatch (text_fill_mode, text_fill_gradient_id)
    that mirror the keys emitted by ``_resolve_horizontal``. Defaults
    here cover paradigms that don't declare ``marquee:`` in their YAML
    (StrictUndefined would otherwise raise on the first missing key).
    """
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx["scroll_items"] = []
    ctx["scroll_distance"] = 1000
    ctx["scroll_dur"] = 11.09
    ctx["scroll_start_x"] = 16
    ctx["font_size"] = 13
    ctx["font_weight"] = ""
    ctx["letter_spacing"] = ".5"
    ctx["scroll_font_family"] = "var(--dna-font-mono, ui-monospace, monospace)"
    ctx["separator_kind"] = "glyph"
    ctx["separator_size"] = 6
    ctx["separator_glyph"] = "■"
    ctx["separator_color"] = "var(--dna-border)"
    ctx["text_fill_mode"] = "per_item"
    ctx["text_fill_gradient_id"] = ""
    ctx["clip_x"] = 0
    ctx["clip_y"] = 0
    ctx["clip_w"] = 800
    ctx["clip_h"] = 40
    ctx["clip_rx"] = 0
    ctx["direction"] = spec.marquee_direction
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_receipt(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx["hero_profile"] = ""
    ctx["hero_tool_class"] = "explore"
    ctx["hero_headline"] = ""
    ctx["hero_subline"] = ""
    ctx["hero_right_stats"] = []
    ctx["treemap_legend"] = []
    ctx["treemap_cells"] = []
    ctx["stage_count"] = 0
    ctx["duration_minutes"] = 0
    ctx["rhythm_bars"] = []
    ctx["bar_area_h"] = 92
    ctx["phase_legend"] = []
    ctx["dominant_profile"] = ""
    ctx["tools"] = []
    ctx["stages"] = []
    ctx["metadata_left"] = ""
    ctx["metadata_right"] = ""
    ctx["footer_left"] = ""
    ctx["footer_right"] = ""
    ctx["receipt_items"] = []
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_rhythm_strip(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx["session_id_short"] = ""
    ctx["call_number"] = 0
    ctx["elapsed_label"] = ""
    ctx["token_summary"] = ""
    ctx["velocity_value"] = ""
    ctx["stages"] = []
    ctx["loop_detected"] = False
    ctx["loop_elevated"] = False
    ctx["loop_label"] = "NOMINAL"
    ctx["loop_detail"] = "no loop"
    ctx["profile_label"] = ""
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_master_card(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx["mc_title"] = "Session Summary"
    ctx["mc_subtitle"] = ""
    ctx["mc_total_tokens"] = ""
    ctx["mc_total_cost"] = ""
    ctx["mc_session_count"] = 0
    ctx["mc_sessions"] = []
    ctx["mc_sparkline_points"] = ""
    ctx["mc_skills"] = []
    ctx["mc_heatmap"] = []
    ctx["session_entries"] = []
    ctx["history_svg"] = ""
    ctx["burn_svg"] = ""
    ctx["heatmap_svg"] = ""
    ctx["tools"] = []
    ctx["stages"] = []
    ctx["loop_detected"] = False
    ctx["loop_elevated"] = False
    ctx["velocity"] = {}
    ctx["footer_left"] = ""
    ctx["footer_right"] = ""
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_catalog(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx["catalog_title"] = spec.title or "Genome Catalog"
    ctx["catalog_subtitle"] = ""
    ctx["catalog_items"] = []
    ctx["catalog_footer_left"] = ""
    ctx["catalog_footer_right"] = ""
    ctx.update(resolved.frame_context)
    return ctx


# ── Session 2A+2B frames ─────────────────────────────────────────────


def _ctx_chart(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    """Context builder for the ``chart`` frame (star history)."""
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    # Pre-populate defaults so Jinja StrictUndefined never fires on missing
    # connector data — resolver fills these when points are present.
    ctx["chart_repo"] = ""
    ctx["chart_title"] = "STAR HISTORY"
    ctx["chart_current_stars"] = "0"
    ctx["chart_viewport_x"] = 0
    ctx["chart_viewport_y"] = 0
    ctx["chart_viewport_w"] = 0
    ctx["chart_viewport_h"] = 0
    ctx["chart_defs"] = ""
    # Post-v0.2.8: axes / gridlines / milestones / markers all return structured
    # lists; polyline / area / empty_state are dicts or None so templates can
    # use ``{% if %}`` to guard includes without a StrictUndefined trap.
    ctx["chart_axes"] = []
    ctx["chart_gridlines"] = []
    ctx["chart_area"] = None
    ctx["chart_polyline"] = None
    ctx["chart_markers"] = []
    ctx["chart_milestones"] = []
    ctx["chart_empty_state"] = None
    ctx["data_hw_status"] = "fresh"
    # Cellular automata chart substrate (Round 13). Three layers: dormant
    # softens void→data clip boundary, active cells under polyline, markers
    # progress through chart_levels. Empty defaults so StrictUndefined never
    # fires on non-cellular paradigms.
    ctx["cellular_area_cells"] = []
    ctx["cellular_area_clip_d"] = ""
    ctx["cellular_marker_colors"] = []
    ctx["cellular_dormant_cells"] = []
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_stats(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    """Context builder for the ``stats`` frame (GitHub profile card)."""
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    # Safe defaults for every field the stats templates may read.
    ctx["stats_username"] = spec.stats_username or ""
    ctx["stats_bio"] = ""
    ctx["stats_repo_label"] = ""
    ctx["stars_display"] = "—"
    ctx["stars_delta_display"] = ""
    ctx["commits_display"] = "—"
    ctx["prs_display"] = "—"
    ctx["issues_display"] = "—"
    ctx["contrib_display"] = "—"
    ctx["streak_display"] = "—"
    ctx["languages"] = []
    ctx["heatmap_grid"] = []
    ctx["activity_bars"] = []
    ctx["activity_peak"] = 0
    ctx["data_hw_status"] = "fresh"
    # Embedded compact chart fragments (populated for chrome paradigm).
    ctx["embedded_chart_defs"] = ""
    ctx["embedded_chart_area"] = ""
    ctx["embedded_chart_polyline"] = ""
    ctx["embedded_chart_markers"] = []
    ctx.update(resolved.frame_context)
    return ctx


# ── Motion injection ─────────────────────────────────────────────────


def _inject_motion(ctx: dict[str, Any], spec: ComposeSpec, resolved: ResolvedArtifact) -> None:
    """Populate motion_border_defs/overlay or motion_svg in the context."""
    motion_id = ctx.get("motion_id", "static")
    if motion_id == MotionId.STATIC:
        return

    try:
        from hyperweave.render.motion import build_border_overlay

        uid = ctx["uid"]
        w = ctx["width"]
        h = ctx["height"]
        rx = ctx.get("badge_corner", ctx.get("strip_corner", 3.33))

        # Panel geometry for rimrun seam-tracing
        seam_positions: list[int] = []
        if spec.type == FrameType.STRIP:
            seam_positions = [int(x) for x in ctx.get("seam_positions", [])]
            seam_x = int(ctx.get("first_divider_x", 0))
            lp_w = seam_x
            right_x_val = seam_x
        else:
            lp_w = int(ctx.get("left_panel_width", 0))
            right_x_val = int(ctx.get("right_panel_x", 0))

        defs_svg, overlay_svg = build_border_overlay(
            motion_id,
            uid,
            w,
            h,
            rx,
            lp_w=lp_w,
            right_x=right_x_val,
            seam_positions=seam_positions,
        )
        if defs_svg or overlay_svg:
            ctx["motion_border_defs"] = defs_svg
            ctx["motion_border_overlay"] = overlay_svg
    except Exception:
        pass  # motion SVG generation must never break compose


# ── Helpers ──────────────────────────────────────────────────────────


def _build_glyph_svg(
    resolved: ResolvedArtifact,
    glyph_mode: str = "fill",
    glyph_fill_color: str = "var(--dna-signal)",
) -> str:
    if not resolved.glyph_path:
        return ""
    vb = resolved.glyph_viewbox or "0 0 640 640"
    from hyperweave.render.templates import render_template

    return render_template(
        "components/glyph-inline.svg.j2",
        {
            "glyph_viewbox": vb,
            "glyph_path": resolved.glyph_path,
            "glyph_mode": glyph_mode,
            "glyph_fill_color": glyph_fill_color,
        },
    )


def _aria_title(spec: ComposeSpec) -> str:
    if spec.title and spec.value:
        return f"{spec.title}: {spec.value}"
    if spec.title:
        return spec.title
    return f"HyperWeave {spec.type} artifact"


def _aria_desc(spec: ComposeSpec) -> str:
    parts = [f"A {spec.type} artifact"]
    if spec.genome_id:
        parts.append(f"using {spec.genome_id} genome")
    if spec.state != ArtifactStatus.ACTIVE:
        parts.append(f"in {spec.state} state")
    return ", ".join(parts) + "."
