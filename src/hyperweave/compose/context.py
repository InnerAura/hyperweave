"""Frame context builders — per-frame template variable construction.

Each builder produces the COMPLETE context dict for its frame type's Jinja2
template.  Common variables (uid, css, metadata, content) come from
``_base_context()``.  Frame-specific defaults are only set for their frame.

Motion SVG is injected by ``_inject_motion()`` after the context is built.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from hyperweave import __version__
from hyperweave.core.enums import ArtifactStatus, FrameType, MotionId
from hyperweave.core.envelope import ENVELOPE_VERSION, build_envelope, cdata_safe_json, envelope_json

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec, ResolvedArtifact

from hyperweave.compose.assembler import fonts_for_frame, frame_needs_fonts
from hyperweave.compose.reasoning import load_reasoning
from hyperweave.core.color import hex_to_rgb_triplet
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


def _load_font_faces(
    genome: dict[str, Any],
    frame_type: str,
    char_set: frozenset[str] | None = None,
) -> str:
    """Load embedded font CSS for ``(frame_type, genome.id)``.

    Intersects the genome's declared ``fonts`` list with the per-(genome,
    frame) allowlist returned by :func:`fonts_for_frame`. The allowlist
    is genome-aware (v0.3.7): the brutalist badge embeds JetBrains Mono
    only even though the brutalist genome declares Barlow Condensed for
    its stats/strip/chart frames. Frames whose ``(genome, frame)`` row
    is empty (icons, dividers, error badges) embed zero fonts.

    When ``char_set`` is provided each surviving font is subset to only
    the codepoints the artifact actually renders. ``None`` embeds full
    fonts (legacy behavior, ``_error_badge``).

    The intersection is order-preserving against the genome's declared
    list so ``@font-face`` declarations render in genome-author intent
    order.
    """
    declared = genome.get("fonts") or ["jetbrains-mono"]
    if not isinstance(declared, list):
        declared = ["jetbrains-mono"]
    genome_id = genome.get("id", "")
    allowed = fonts_for_frame(frame_type, genome_id)
    if not allowed:
        return ""
    filtered = [slug for slug in declared if slug in allowed]
    return load_font_face_css(filtered, char_set)


# Per-frame text-field maps for glyph subsetting. Each entry lists the
# context keys whose string content reaches a rendered <text> element
# and therefore must be present in the font subset. Glyph SVG paths,
# reasoning metadata, ARIA strings, and version/created/contract_id
# render via different paths (paths render as <path>, metadata renders
# in <hw:*> blocks read by no browser font) and stay outside the
# extraction surface.
_TEXT_FIELDS_BY_FRAME: dict[str, tuple[str, ...]] = {
    "badge": ("title", "value", "label", "description"),
    "strip": ("title", "value", "label", "description"),
    "stats": (
        "stats_username",
        "stats_bio",
        "stats_repo_label",
        "stars_display",
        "stars_delta_display",
        "commits_display",
        "prs_display",
        "issues_display",
        "contrib_display",
        "streak_display",
        "languages",
        "activity_bars",
    ),
    "chart": (
        "chart_repo",
        "chart_title",
        "chart_current_stars",
        "chart_axes",
        "chart_milestones",
        "chart_empty_state",
    ),
    "marquee": ("scroll_items",),
    "matrix": ("matrix_text_surface",),
    "diagram": ("diagram_text_surface",),
    "receipt": (
        "hero_headline",
        "hero_subline",
        "hero_right_stats",
        "treemap_legend",
        "metadata_left",
        "metadata_right",
        "footer_left",
        "footer_right",
        "dominant_profile",
        "phase_legend",
    ),
}

# Conservative baseline character set. Always included even when the
# template's resolved text is sparse — covers axis tick labels, %
# suffixes, numeric formatters, paren-wrapped clarifiers, and unicode
# arrows / dots used in chrome/brutalist label glyphs.
_SAFE_BASELINE: frozenset[str] = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .:,;-_/·→×%+()[]"  # noqa: RUF001  middle-dot / right-arrow / multiplication-sign are deliberate
)


def _collect_text(value: Any, chars: set[str]) -> None:
    """Recursively walk ``value`` and absorb every string codepoint into ``chars``.

    Lists, tuples, and dicts (keys + values) are traversed; ``None`` and
    non-string scalars (numbers, bools) are skipped. The recursive shape
    keeps the collector resilient against future context-field additions
    that wrap text in additional dict/list layers — a new ``chart_axes``
    entry shape doesn't need a corresponding extractor edit.
    """
    if value is None:
        return
    if isinstance(value, str):
        chars.update(value)
        return
    if isinstance(value, list | tuple):
        for item in value:
            _collect_text(item, chars)
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str):
                chars.update(k)
            _collect_text(v, chars)


def _extract_char_set(ctx: dict[str, Any], frame_type: str) -> frozenset[str]:
    """Return the union of the safe baseline and every rendered text char.

    Reads the per-frame text-field map at :data:`_TEXT_FIELDS_BY_FRAME`
    and recursively flattens each context value to its component codepoints.
    Frames not in the map fall back to the baseline only.

    Run AFTER the per-frame builder populates ``ctx`` (which means the
    resolver-emitted text fields like ``chart_milestones`` and
    ``stats_username`` are visible) — see the ordering note on
    :func:`build_context`.
    """
    chars: set[str] = set(_SAFE_BASELINE)
    for field in _TEXT_FIELDS_BY_FRAME.get(frame_type, ()):
        _collect_text(ctx.get(field), chars)
    return frozenset(chars)


def build_context(
    spec: ComposeSpec,
    resolved: ResolvedArtifact,
    css_bundle: dict[str, str],
) -> dict[str, Any]:
    """Dispatch to the per-frame context builder, then wire font subsetting.

    Per-frame builders fill ``ctx`` with the safe defaults and then merge
    ``resolved.frame_context`` (resolver output: ``chart_milestones``,
    ``stats_username``, ``scroll_items[*].text``, etc.). Only after that
    merge runs does the rendered text surface become observable — which is
    why v0.3.7 moves the ``font_faces`` assignment OUT of ``_base_context``
    and INTO this post-builder step. The extractor at :func:`_extract_char_set`
    then walks the fully-populated ctx and the subsetter at
    :func:`_load_font_faces` emits a payload tuned to the actual glyph set.
    """
    _BUILDERS: dict[str, _CtxBuilder] = {
        FrameType.BADGE: _ctx_badge,
        FrameType.STRIP: _ctx_strip,
        FrameType.ICON: _ctx_icon,
        FrameType.DIVIDER: _ctx_divider,
        FrameType.MARQUEE: _ctx_marquee,
        FrameType.RECEIPT: _ctx_receipt,
        FrameType.STATS: _ctx_stats,
        FrameType.CHART: _ctx_chart,
        FrameType.MATRIX: _ctx_matrix,
        FrameType.DIAGRAM: _ctx_diagram,
    }
    builder = _BUILDERS.get(spec.type, _ctx_badge)
    ctx = builder(spec, resolved, css_bundle)
    _inject_motion(ctx, spec, resolved)
    genome_id = resolved.genome.get("id", "")
    if frame_needs_fonts(spec.type, genome_id):
        char_set = _extract_char_set(ctx, spec.type)
        ctx["font_faces"] = _load_font_faces(resolved.genome, spec.type, char_set)
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
    if frame_needs_fonts(spec.type, resolved.genome.get("id", "")):
        module_names.append("fonts")
    css_debug = f"/* hw:css-modules: {','.join(module_names)} */"
    css_assembled = css_debug + "\n" + "\n".join(p for p in css_parts if p)

    profile = resolved.profile
    glyph_viewbox = resolved.glyph_viewbox or "0 0 640 640"
    glyph_render_viewbox = str(resolved.frame_context.get("glyph_render_viewbox") or glyph_viewbox)
    glyph_viewbox_cx, glyph_viewbox_cy = _viewbox_center(glyph_viewbox)

    ctx: dict[str, Any] = {
        # Identity
        "uid": uid,
        "artifact_id": artifact_id,
        "contract_id": artifact_id,
        "frame_type": spec.type,
        "genome_id": resolved.genome.get("id", spec.genome_id),
        "genome_category": resolved.genome.get("category", "dark"),
        # v0.3.2: variant + substrate_kind plumbed through to templates.
        # substrate_kind drives the brutalist split-template dispatcher
        # (`brutalist-{substrate_kind}-content.j2`). When a variant override
        # declares substrate_kind it's already merged onto resolved.genome
        # by the resolver, so a single getattr suffices. Empty/missing falls
        # back to genome `category` — consistent with theme_category (below),
        # _compose_font_stack and _resolve_reasoning_context — so a category:light
        # genome with no substrate_kind (e.g. primer's no-variant flagship path)
        # resolves "light", not a hardcoded "dark".
        "variant": resolved.resolved_variant,
        "substrate_kind": resolved.genome.get("substrate_kind") or resolved.genome.get("category", "dark"),
        # v0.3.2 Phase D: panel_gradient_stops + seam_color exposed to templates
        # so light-substrate defs.j2 can render the dark academic panel gradient
        # (`url(#{{ uid }}-panel)`) and per-variant gold seam color. Variants
        # declare these in genome.json variant_overrides → merged into genome by
        # resolver → plumbed here. Dark variants return None / "" (gradient
        # rendering gated by template `{% if panel_gradient_stops %}` guard).
        "panel_gradient_stops": resolved.genome.get("panel_gradient_stops") or [],
        "seam_color": resolved.genome.get("seam_color", ""),
        # Ink as an "r,g,b" triplet so templates derive substrate-tinted alpha
        # layers (light badge label tint rgba({{ ink_rgb }},0.03), seam groove
        # rgba({{ ink_rgb }},0.09), strip edge-highlight bottom tint) without
        # hex math in Jinja2. Empty string when the genome field is missing.
        "ink_rgb": hex_to_rgb_triplet(str(resolved.genome.get("ink", ""))),
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
        "spatial_aspect_ratio": f"{resolved.width / resolved.height:.2f}" if resolved.height else "0.00",
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
        "glyph_fill_rule": resolved.glyph_fill_rule,
        "glyph_viewbox": glyph_viewbox,
        "glyph_render_viewbox": glyph_render_viewbox,
        "glyph_viewbox_cx": glyph_viewbox_cx,
        "glyph_viewbox_cy": glyph_viewbox_cy,
        "glyph_mode": spec.glyph_mode,
        "has_glyph": bool(resolved.glyph_id),
        "glyph_svg": _build_glyph_svg(
            resolved,
            spec.glyph_mode,
            resolved.frame_context.get("glyph_fill", "var(--dna-signal)"),
            # Paradigm-declared glyph_size flows to the inline SVG. Chrome=11
            # matches _spatial_study.svg prototype; brutalist default=14
            # preserves the v16 prototype. Previously the inline template
            # hardcoded 14 and ignored paradigm config.
            int(resolved.frame_context.get("glyph_render_size") or resolved.frame_context.get("glyph_size") or 14),
            glyph_render_viewbox,
        ),
        # Metadata / accessibility
        "title_text": _aria_title(spec),
        "desc_text": _aria_desc(spec),
        # Chrome material gradients intentionally overrun the SVG extent.
        "gradient_y_neg_010": -0.1,
        "gradient_y_090": 0.9,
        "gradient_y_neg_005": -0.05,
        "gradient_y_095": 0.95,
        "gradient_c_mid": 0.5,
        "gradient_cy_upper": 0.4,
        "gradient_r_medium": 0.6,
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
        # hw:payload / hwz envelope projections + sub-variant root attribute.
        # Set by data-carrying frame builders (matrix); empty strings
        # suppress the metadata blocks / attribute entirely on other frames.
        "payload_json": "",
        "payload_schema": "",
        "envelope_json": "",
        "envelope_format": "",
        "data_hw_subvariant": "",
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
        # Material filter chain — from genome.material.filter_chain (e.g.
        # "specular-bevel", "none"). Templates conditionally emit
        # feSpecularLighting + feComposite when set to "specular-bevel"
        # (chrome v0.3.9 Bug H — restores the specular pass on chart bevels
        # that the chart template had silently dropped to a plain feDropShadow).
        "material_filter_chain": (resolved.genome.get("material") or {}).get("filter_chain", "none"),
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
        # Embedded fonts (base64 @font-face CSS) — placeholder. The real
        # assignment lands in build_context() AFTER the per-frame builder
        # merges resolver text fields into ctx, so the glyph subsetter
        # at _extract_char_set + _load_font_faces sees the full rendered
        # text surface (chart milestone labels, stats username, marquee
        # scroll items, etc.). Setting the empty default here keeps
        # Jinja's StrictUndefined happy for any code path that bypasses
        # build_context (none exist today, but the default is defense
        # against future drift).
        "font_faces": "",
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
    """Context defaults for the marquee frame.

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
    ctx["separator_fill"] = "var(--dna-signal, var(--dna-border))"
    ctx["marquee_baseline_y"] = 20
    ctx["separator_rect_y"] = 17
    ctx["marquee_perimeter_w"] = 799
    ctx["marquee_perimeter_h"] = 39
    ctx["chrome_well_w"] = 792
    ctx["chrome_well_h"] = 32
    ctx["chrome_inner_w"] = 798
    ctx["chrome_inner_h"] = 38
    ctx["chrome_rail_h"] = 32
    ctx["chrome_top_accent_w"] = 752
    ctx["cellular_bottom_hairline_y"] = 39.5
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
    # Cellular automata chart substrate. Three layers: dormant cells soften
    # the void→data clip boundary, active cells sit under the polyline, and
    # markers progress through chart_levels. Empty defaults prevent
    # StrictUndefined on non-cellular paradigms.
    ctx["cellular_area_cells"] = []
    ctx["cellular_area_clip_d"] = ""
    ctx["cellular_marker_colors"] = []
    ctx["cellular_dormant_cells"] = []
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_matrix(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    """Context builder for the ``matrix`` frame (structured comparison table)."""
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    # StrictUndefined-safe defaults; the matrix resolver fills all of these.
    ctx["matrix_layout"] = None
    ctx["matrix_cfg"] = None
    ctx["matrix_title"] = ""
    ctx["matrix_subtitle"] = ""
    ctx["matrix_notes"] = ""
    ctx["matrix_subvariant"] = ""
    ctx["semantic_palette"] = {}
    ctx["matrix_voices"] = []
    ctx["matrix_glyph_gradients"] = []
    ctx["matrix_scan_travel"] = 0
    ctx["matrix_text_surface"] = []
    ctx["matrix_envelope_data"] = {}
    ctx["matrix_intent"] = ""
    ctx.update(resolved.frame_context)

    payload_json = str(ctx.get("payload_json") or "")
    if payload_json:
        # Content-derived identity: byte-identical re-renders are the
        # contract (ETag / Camo caching / diff / the round-trip thesis).
        # Same payload+genome+variant+version => same uid; different specs
        # on one page never collide.
        digest = hashlib.sha256(
            "|".join(
                (
                    payload_json,
                    str(ctx.get("genome_id", "")),
                    str(ctx.get("variant", "")),
                    str(ctx.get("version", "")),
                )
            ).encode("utf-8")
        ).hexdigest()
        ctx["uid"] = f"hw-{digest[:8]}"
        ctx["artifact_id"] = f"matrix-{digest[:16]}"
        ctx["contract_id"] = ctx["artifact_id"]
        # hwz/1 envelope assembled HERE — where created_at exists — so
        # prov.ts == hw:created with no second clock read.
        genome_id = str(ctx.get("genome_id", ""))
        variant = str(ctx.get("variant", ""))
        envelope = build_envelope(
            kind="matrix",
            title=str(ctx.get("matrix_title", "")),
            intent=str(ctx.get("matrix_intent", "")),
            data=dict(ctx.get("matrix_envelope_data") or {}),
            frames=[{"t": "matrix", "l": str(ctx.get("matrix_title", ""))}],
            payload_json=payload_json,
            genome_label=f"{genome_id}.{variant}" if variant else genome_id,
            version=str(ctx.get("version", "")),
            created=str(ctx.get("created_at", "")),
            state=str(spec.state or ""),
        )
        ctx["envelope_json"] = cdata_safe_json(envelope_json(envelope))
        ctx["envelope_format"] = ENVELOPE_VERSION
    return ctx


def _ctx_diagram(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    """Context builder for the ``diagram`` frame (topology graph)."""
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    # StrictUndefined-safe defaults; the diagram resolver fills all of these.
    ctx["diagram_layout"] = None
    ctx["diagram_cfg"] = None
    ctx["diagram_flow"] = []
    ctx["diagram_style"] = {}
    ctx["diagram_voices"] = []
    ctx["diagram_glyph_gradients"] = []
    ctx["diagram_envelope_data"] = {}
    ctx["diagram_intent"] = ""
    ctx["diagram_title"] = ""
    ctx["diagram_text_surface"] = []
    ctx["data_hw_topology"] = ""
    ctx["performance_tier"] = "composite-only"
    ctx["motion_vocabulary"] = "static"
    ctx.update(resolved.frame_context)

    payload_json = str(ctx.get("payload_json") or "")
    if payload_json:
        # Content-derived identity (the matrix recipe): same payload +
        # genome + variant + version => same uid. The payload includes the
        # RENDERED motion record, so the envelope id is ARTIFACT identity —
        # the same spec under a different edge_motion hashes differently
        # (P4), exactly as a different genome or variant already does.
        digest = hashlib.sha256(
            "|".join(
                (
                    payload_json,
                    str(ctx.get("genome_id", "")),
                    str(ctx.get("variant", "")),
                    str(ctx.get("version", "")),
                )
            ).encode("utf-8")
        ).hexdigest()
        ctx["uid"] = f"hw-{digest[:8]}"
        ctx["artifact_id"] = f"diagram-{digest[:16]}"
        ctx["contract_id"] = ctx["artifact_id"]
        genome_id = str(ctx.get("genome_id", ""))
        variant = str(ctx.get("variant", ""))
        envelope = build_envelope(
            kind="diagram",
            title=str(ctx.get("diagram_title", "") or ctx.get("title_text", "")),
            intent=str(ctx.get("diagram_intent", "")),
            data=dict(ctx.get("diagram_envelope_data") or {}),
            frames=[{"t": "diagram", "l": str(ctx.get("diagram_title", "") or ctx.get("title_text", ""))}],
            payload_json=payload_json,
            genome_label=f"{genome_id}.{variant}" if variant else genome_id,
            version=str(ctx.get("version", "")),
            created=str(ctx.get("created_at", "")),
            state=str(spec.state or ""),
        )
        ctx["envelope_json"] = cdata_safe_json(envelope_json(envelope))
        ctx["envelope_format"] = ENVELOPE_VERSION
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
        h = ctx["height"]
        rx = ctx.get("badge_corner", ctx.get("strip_corner", 3.33))

        # Border motions trace the visible envelope, not the SVG viewBox.
        # For chrome strips with strip_min_width clamping the canvas wider
        # than content, content_width < width.
        # The motion path must follow content_width so the animated border
        # doesn't extend into the transparent trailing zone. Brutalist's
        # owns_strip path sets content_width == width so it's unchanged.
        # Badges have no canvas/content split — content_width unset → fall
        # back to width.
        w = int(ctx.get("content_width") or ctx["width"])

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
    glyph_size: int = 14,
    glyph_viewbox: str = "",
) -> str:
    if not resolved.glyph_path:
        return ""
    vb = glyph_viewbox or resolved.glyph_viewbox or "0 0 640 640"
    from hyperweave.render.templates import render_template

    return render_template(
        "components/glyph-inline.svg.j2",
        {
            "glyph_viewbox": vb,
            "glyph_path": resolved.glyph_path,
            "glyph_fill_rule": resolved.glyph_fill_rule,
            "glyph_mode": glyph_mode,
            "glyph_fill_color": glyph_fill_color,
            "glyph_size": glyph_size,
        },
    )


def _viewbox_center(viewbox: str) -> tuple[float, float]:
    parts = viewbox.split()
    if len(parts) < 4:
        return (320.0, 320.0)
    try:
        return (float(parts[2]) / 2.0, float(parts[3]) / 2.0)
    except ValueError:
        return (320.0, 320.0)


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
