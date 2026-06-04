"""Spec resolver -- resolves genome, profile, frame, glyph, motion for each frame type."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hyperweave.compose.assembler import compute_variant_inline_style
from hyperweave.compose.bar_chart import compute_time_axis_ticks, layout_bar_chart
from hyperweave.compose.palette import resolve_cellular_palette
from hyperweave.compose.treemap import compute_treemap_layout
from hyperweave.core.enums import (
    FrameType,
    GlyphMode,
    MotionId,
    ProfileId,
    Regime,
)

# NOTE: ProfileId import kept for icon resolver (BRUTALIST variant mapping).
# Marquee resolvers no longer reference ProfileId directly.
from hyperweave.core.models import ResolvedArtifact
from hyperweave.telemetry.runtimes import classify_tool, get_runtime

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec


def _resolve_telemetry_genome(spec: ComposeSpec, telemetry_data: dict[str, Any]) -> str:
    """Resolve telemetry genome via precedence: explicit override → JSONL runtime → voltage fallback.

    Empty-string fallback is deliberate. Pre-patch JSONL has no runtime field; those
    sessions route to voltage (the explicit fallback) rather than auto-classifying as
    claude-code. Explicit signal → specific skin; absent signal → fallback.

    Non-receipt-capable genome overrides (e.g. brutalist) silently fall through to
    runtime detection rather than raising — the install-hook CLI handles fail-loud
    validation upstream; here we keep compose() forgiving so a stale --genome flag
    on a session command doesn't crash the receipt write.
    """
    if spec.genome_id and _genome_supports_receipts(spec.genome_id):
        return spec.genome_id
    runtime = telemetry_data.get("session", {}).get("runtime") or ""
    if runtime:
        try:
            return get_runtime(runtime).genome
        except KeyError:
            # Unknown runtime falls through to voltage — receipts still render
            # under the generic skin even if the agent identity is unrecognized.
            pass
    return "telemetry-voltage"


def _genome_supports_receipts(genome_id: str) -> bool:
    """Return True when a genome declares paradigms.receipt, gating receipt eligibility."""
    try:
        g = _load_genome(genome_id)
    except GenomeNotFoundError:
        return False
    return "receipt" in (g.get("paradigms") or {})


def resolve_variant(spec: ComposeSpec, genome: dict[str, Any], paradigm_spec: Any = None) -> str:
    """Resolve the chromatic variant via Path B precedence chain.

    1. spec.variant (explicit user input)
    2. paradigm_spec.frame_variant_defaults[spec.type] (paradigm per-frame default)
    3. genome.flagship_variant (genome's default)
    4. "" (no variant)

    When the genome declares a non-empty `variants` whitelist, the resolved
    value must be in that list (or empty). Raises ValueError on violation —
    moved here from the Pydantic field_validator at v0.2.19 (Path B grammar)
    so genomes can declare their own allowed variants without Python edits.
    """
    resolved = spec.variant
    if not resolved and paradigm_spec is not None:
        defaults = getattr(paradigm_spec, "frame_variant_defaults", {}) or {}
        resolved = defaults.get(spec.type, "")
    if not resolved:
        resolved = str(genome.get("flagship_variant", ""))

    allowed = list(genome.get("variants") or [])
    if allowed and resolved and resolved not in allowed:
        msg = f"variant '{resolved}' not in genome.variants {allowed}"
        raise ValueError(msg)
    return resolved


def resolve(spec: ComposeSpec) -> ResolvedArtifact:
    """Resolve a ComposeSpec into a typed ResolvedArtifact."""
    # Telemetry frames flow through _resolve_telemetry_genome() precedence chain:
    # explicit --genome override → JSONL runtime field → telemetry-voltage fallback.
    if spec.type in {FrameType.RECEIPT, FrameType.RHYTHM_STRIP}:
        tel: dict[str, Any] = dict(spec.telemetry_data or {})
        genome_id = _resolve_telemetry_genome(spec, tel)
        genome = _load_genome(genome_id)
        profile = _load_profile(genome.get("profile", "brutalist"))
    else:
        # Session 2A+2B: genome_override bypasses the registry (used by --genome-file).
        genome = _load_genome(spec.genome_id, override=spec.genome_override)
        profile = _load_profile(genome.get("profile", spec.profile_id))
    glyph_data = _resolve_glyph(spec)
    motion = _resolve_motion(spec, genome)

    # Stats and chart resolvers live in compose/resolvers/ per Invariant 10.
    from hyperweave.compose.resolvers.chart import resolve_chart
    from hyperweave.compose.resolvers.stats import resolve_stats

    # Dispatch to frame-specific resolver
    frame_resolvers: dict[str, Any] = {
        "badge": resolve_badge,
        "strip": resolve_strip,
        "icon": resolve_icon,
        "divider": resolve_divider,
        "marquee-horizontal": resolve_marquee,
        "receipt": resolve_receipt,
        "rhythm-strip": resolve_rhythm_strip,
        "chart": resolve_chart,
        "stats": resolve_stats,
    }

    resolver_fn = frame_resolvers.get(spec.type, resolve_badge)

    # Resolve the paradigm spec for this frame type and hand it to the
    # resolver as a typed kwarg. Phase 4A: eliminates in-resolver
    # ``if paradigm == "chrome"`` string comparisons — resolvers read
    # ``paradigm_spec.{frame}.{key}`` directly. A genome's paradigms dict
    # routes the frame type to a paradigm slug; unknown slugs fall back
    # to the ``default`` paradigm so compose never crashes on a typo.
    from hyperweave.config.registry import get_paradigms

    paradigm_slug = _resolve_paradigm(genome, spec.type, default="default")
    all_paradigms = get_paradigms()
    paradigm_spec = all_paradigms.get(paradigm_slug) or all_paradigms["default"]

    # v0.3.0 centralization: variant resolution + cellular palette + inline-style
    # emission computed BEFORE the per-frame resolver runs so resolvers that
    # need bifamily semantics (marquee) can consume cellular_palette directly
    # as a kwarg rather than recomputing or branching on raw genome fields.
    # Per-frame resolvers no longer call resolve_variant() — the dispatcher
    # computes once and propagates via kwargs + frame_context + ResolvedArtifact.
    resolved_variant = resolve_variant(spec, genome, paradigm_spec)

    # Merge variant_overrides into the genome dict so templates reading baked
    # fields directly (envelope_stops, well_top, well_bottom, specular_light,
    # glyph_inner) also see the variant. Inline-style emission still works
    # for the CSS-var subset; this merge unlocks variant differentiation for
    # the chrome strip/badge/icon visual structure that doesn't go through
    # CSS variables. No-op when no override entry exists (bare/horizon paths).
    if resolved_variant:
        _vo = (genome.get("variant_overrides") or {}).get(resolved_variant) or {}
        if _vo:
            genome = {**genome, **_vo}

    inline_style_overrides = compute_variant_inline_style(genome, resolved_variant)
    if spec.type == FrameType.BADGE and resolved_variant and genome.get("highlight_color"):
        _safe_specular = str(genome["highlight_color"]).replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
        _specular_decl = f"--dna-specular:{_safe_specular};"
        inline_style_overrides = (
            f"{inline_style_overrides} {_specular_decl}".strip() if inline_style_overrides else _specular_decl
        )
    cellular_palette = resolve_cellular_palette(genome, resolved_variant, pair=spec.pair)

    # Cellular paradigm: append --hw-state-tone + --hw-state-value-tone CSS
    # vars to the SVG-root inline style so the building/offline state indicator
    # AND its value text color flow through the variant's primary tone instead
    # of genome-static --dna-signal + --dna-badge-value-text (both teal for
    # automata regardless of ?variant=). expression.css:126-133 reads both with
    # genome-level fallbacks — chrome/brutalist genomes leave these CSS vars
    # unset so they fall back to pre-v0.3 behavior.
    _cp_primary_for_tone = cellular_palette.get("primary") or {}
    _cellular_tone_decls: list[str] = []
    if _cp_primary_for_tone.get("seam_mid"):
        _cellular_tone_decls.append(f"--hw-state-tone:{_cp_primary_for_tone['seam_mid']};")
    if _cp_primary_for_tone.get("value_text"):
        _cellular_tone_decls.append(f"--hw-state-value-tone:{_cp_primary_for_tone['value_text']};")
        # Override --dna-ink-primary so marquee scroll text + any legacy
        # var(--dna-ink-primary) references inside cellular SVGs shift with
        # variant. Without this, automata's --dna-ink-primary stays at its
        # genome-level "#ededed" white-gray and marquees render variant-blind.
        _cellular_tone_decls.append(f"--dna-ink-primary:{_cp_primary_for_tone['value_text']};")
    if _cp_primary_for_tone.get("cellular_cells"):
        _cells = _cp_primary_for_tone["cellular_cells"]
        if _cells:
            # Override --dna-ink-muted/--dna-ink-secondary so secondary text
            # (separators, secondary tspan alternation in solo marquees) also
            # shifts with variant. cellular_cells[0] is the variant's muted
            # primary tone — perceptually close to "ink-muted" semantics.
            _cellular_tone_decls.append(f"--dna-ink-muted:{_cells[0]};")
            _cellular_tone_decls.append(f"--dna-ink-secondary:{_cells[0]};")
            # Override --dna-signal so chart-marker partials (var(--dna-signal)),
            # milestone-line color, and any other genome-static signal reference
            # shifts with cellular variant. Without this, automata's chart
            # markers stayed teal (#1E849A) regardless of ?variant=. Chrome
            # paradigm has its own variant_overrides[accent] cascade, so
            # non-cellular genomes are unaffected.
            _cellular_tone_decls.append(f"--dna-signal:{_cells[0]};")
    if _cellular_tone_decls:
        _decls_str = " ".join(_cellular_tone_decls)
        inline_style_overrides = (
            f"{inline_style_overrides} {_decls_str}".strip() if inline_style_overrides else _decls_str
        )

    frame_result = resolver_fn(
        spec,
        genome,
        profile,
        glyph_data=glyph_data,
        paradigm_spec=paradigm_spec,
        resolved_variant=resolved_variant,
        cellular_palette=cellular_palette,
    )

    # Session 2A+2B: inject paradigm + structural hints into every frame_context
    # (Principle 26 dispatch + Principle 24 template-genome interface).
    # Templates read `paradigm` to resolve {frame_type}/{paradigm}-content.j2,
    # and `structural` for per-frame layout hints (stroke_linejoin, etc.).
    ctx = dict(frame_result.get("context", {}))
    # v0.2.6 centralization: profile visual context (envelope/well/specular/
    # chrome+hero text gradients) applied universally at the dispatcher.
    # Replaces manual _genome_material_context(...) calls previously scattered
    # across badge/strip/icon/divider/marquee/stats/chart resolvers —
    # the forgetting of which caused Bug D (stats + chart rendered chrome
    # envelopes regardless of genome). setdefault semantics: a frame resolver
    # that legitimately pre-computes one of these keys still wins.
    for _k, _v in _genome_material_context(genome, profile).items():
        ctx.setdefault(_k, _v)
    ctx.setdefault("paradigm", _resolve_paradigm(genome, spec.type, default="default"))
    ctx.setdefault("structural", genome.get("structural") or {})
    ctx.setdefault("genome_typography", genome.get("typography") or {})
    ctx.setdefault("genome_material", genome.get("material") or {})
    ctx.setdefault("variant", resolved_variant)
    ctx.setdefault("inline_style_overrides", inline_style_overrides)
    ctx.setdefault("cellular_palette", cellular_palette)

    # Cellular paradigm overrides glyph_fill from cellular_palette.primary.seam_mid
    # so the strip's left-zone glyph (and chrome-defs typography classes that
    # read glyph_fill) shift with variant. Without this, glyph_fill stays at
    # genome.glyph_inner — variant-agnostic — and the strip's identity zone
    # reads teal regardless of ?variant=. Non-cellular genomes have empty
    # cellular_palette so primary is {} and the override doesn't fire.
    _cp_primary = cellular_palette.get("primary") or {}
    if _cp_primary.get("seam_mid"):
        ctx["glyph_fill"] = _cp_primary["seam_mid"]

    # Cellular paradigm: override variant-blind ctx keys with cellular_palette-
    # derived values so the strip's metric-cell seams + subtitle text + content
    # panel border shift with variant. Mirrors the glyph_fill override pattern
    # above; non-cellular paradigms have empty cellular_palette so the overrides
    # don't fire. divider_color = primary.cellular_cells[0] (variant's deepest
    # cell); subtitle_color = primary.seam_mid (variant's mid-saturation accent).
    # border_tint also routes through divider_color so the cellular content
    # panel outline (rendered at 0.28 opacity) shifts with variant rather than
    # leaking genome.border_tint (#1E849A static teal for automata).
    if cellular_palette.get("divider_color"):
        ctx["strip_divider_color"] = cellular_palette["divider_color"]
        ctx["border_tint"] = cellular_palette["divider_color"]
    if cellular_palette.get("subtitle_color"):
        ctx["ink_sub"] = cellular_palette["subtitle_color"]

    return ResolvedArtifact(
        genome=genome,
        profile=profile,
        profile_id=genome.get("profile", spec.profile_id or "brutalist"),
        category=genome.get("category", "dark"),
        width=frame_result["width"],
        height=frame_result["height"],
        frame_template=frame_result["template"],
        frame_context=ctx,
        resolved_variant=resolved_variant,
        inline_style_overrides=inline_style_overrides,
        motion=motion,
        glyph_id=glyph_data.get("id", ""),
        glyph_path=glyph_data.get("path", ""),
        glyph_viewbox=glyph_data.get("viewBox", ""),
    )


# Frame resolvers


def resolve_badge(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    paradigm_spec: Any = None,
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve badge dimensions and layout.

    Two rendering modes driven by profile:
      standard (brutalist, clinical, etc.)  -- two-panel, sep+seam, sharp
      chrome                                -- envelope gradient, well, bevel filter
    """
    from hyperweave.core.text import measure_text_ink_metrics

    badge_cfg_for_height = paradigm_spec.badge if paradigm_spec else None
    # Height + size class: paradigm-driven default or compact variant.
    # Cellular can make its default request resolve through the compact
    # geometry by declaring badge.default_size=compact. Explicit non-default
    # size values still use frame_height, which keeps the larger artifact
    # reachable without a paradigm-specific branch.
    compact = spec.size == "compact" or (
        spec.size == "default" and badge_cfg_for_height is not None and badge_cfg_for_height.default_size == "compact"
    )
    if badge_cfg_for_height is not None:
        height = badge_cfg_for_height.frame_height_compact if compact else badge_cfg_for_height.frame_height
    else:
        height = profile.get("badge_frame_height", 20)
    use_mono = profile.get("badge_use_mono", True)
    label_uppercase = profile.get("badge_label_uppercase", True)

    # Layout constants
    font_size = 11  # kept for letter-spacing math (chrome/brutalist default)
    accent_w = 4
    # Glyph-size: paradigm-driven, compact variant may override.
    badge_cfg_for_glyph_size = paradigm_spec.badge if paradigm_spec else None
    if badge_cfg_for_glyph_size is not None:
        from hyperweave.compose.layout import compute_badge_glyph_size

        glyph_ratio = (
            badge_cfg_for_glyph_size.glyph_size_compact_ratio
            if compact and badge_cfg_for_glyph_size.glyph_size_compact_ratio > 0
            else badge_cfg_for_glyph_size.glyph_size_ratio
        )
        if glyph_ratio > 0:
            glyph_size = compute_badge_glyph_size(
                height,
                glyph_ratio,
                badge_cfg_for_glyph_size.glyph_size_max,
            )
        elif compact and badge_cfg_for_glyph_size.glyph_size_compact > 0:
            glyph_size = badge_cfg_for_glyph_size.glyph_size_compact
        else:
            glyph_size = badge_cfg_for_glyph_size.glyph_size
    else:
        glyph_size = 14

    glyph_data = _kw.get("glyph_data") or {}
    glyph_path = str(glyph_data.get("path", ""))
    glyph_viewbox = str(glyph_data.get("viewBox", ""))
    glyph_id = str(glyph_data.get("id", ""))
    glyph_visual_w = float(glyph_size)
    glyph_render_viewbox = glyph_viewbox
    glyph_render_ink_w = glyph_visual_w
    glyph_render_ink_h = glyph_visual_w
    glyph_optical_scale = 1.0
    if glyph_path:
        from hyperweave.render.glyph_metrics import compute_glyph_render_metrics

        glyph_render_metrics = compute_glyph_render_metrics(glyph_id, glyph_path, glyph_viewbox, float(glyph_size))
        glyph_visual_w = glyph_render_metrics.rendered_ink_w
        glyph_render_viewbox = glyph_render_metrics.render_viewbox
        glyph_render_ink_w = glyph_render_metrics.rendered_ink_w
        glyph_render_ink_h = glyph_render_metrics.rendered_ink_h
        glyph_optical_scale = glyph_render_metrics.optical_scale

    # Paradigm may override profile-level seam structure. Cellular declares
    # sep_w=1 because its template paints a 1px gradient seam where
    # brutalist would paint a 2px separator — without the override, the
    # resolver's value_zone_left lands 1px past the actual slab and the
    # centered value text drifts 1.5px right of the slab visual center.
    badge_cfg_for_seam = paradigm_spec.badge if paradigm_spec else None
    sep_w = (
        badge_cfg_for_seam.sep_w
        if badge_cfg_for_seam and badge_cfg_for_seam.sep_w > 0
        else profile.get("badge_sep_width", 2)
    )
    seam_w = (
        badge_cfg_for_seam.seam_w
        if badge_cfg_for_seam and badge_cfg_for_seam.seam_w > 0
        else profile.get("badge_seam_width", 3)
    )
    # Indicator geometry. ``indicator_size`` (the proportional accent size) is
    # derived from the value-font cap height AFTER the value size is resolved
    # below — see ``indicator_size = ...`` near ``_value_size``. Stroke + inner-bit
    # ratio remain paradigm-tunable here.
    badge_cfg_for_indicator = paradigm_spec.badge if paradigm_spec else None
    indicator_stroke_width = (
        badge_cfg_for_indicator.indicator_stroke_width
        if badge_cfg_for_indicator and badge_cfg_for_indicator.indicator_stroke_width > 0
        else 1.2
    )
    indicator_inner_bit_ratio = (
        badge_cfg_for_indicator.indicator_inner_bit_ratio
        if badge_cfg_for_indicator and badge_cfg_for_indicator.indicator_inner_bit_ratio > 0
        else 0.5
    )
    # State-indicator shape cascade: request override > genome/variant default >
    # paradigm default > substrate default. Reading paradigm_spec.badge.indicator_shape
    # is config field access, not a paradigm-string comparison (Invariant 12). The
    # substrate default keys off substrate_kind (a substrate axis, not a paradigm):
    # light substrates default to the soft ring (circle), dark to the angular bit
    # (square) — preserving the brutalist dark=square / light=circle pairing
    # without a per-variant config edit. chrome sets indicator_shape=diamond in
    # paradigm config, short-circuiting before the substrate default. The chosen
    # slug selects indicators/<shape>-indicator.j2 in the content template.
    _substrate_default_shape = "circle" if str(genome.get("substrate_kind", "dark")) == "light" else "square"
    _paradigm_indicator_shape = (
        badge_cfg_for_indicator.indicator_shape
        if badge_cfg_for_indicator and badge_cfg_for_indicator.indicator_shape
        else _substrate_default_shape
    )
    indicator_shape = spec.state_glyph_shape or genome.get("state_glyph_shape") or _paradigm_indicator_shape
    inset = profile.get("badge_inset", 0)
    # text_y_factor from paradigm (cellular uses 0.656 matching spec y=21 at
    # h=32; brutalist/chrome use 0.69 baseline). One place drives the math.
    text_y_factor = (
        badge_cfg_for_glyph_size.text_y_factor
        if badge_cfg_for_glyph_size is not None
        else profile.get("badge_text_y_factor", 0.69)
    )

    # Text content
    label_raw = spec.title or ""
    value_raw = spec.value or ""
    label_display = label_raw.upper() if label_uppercase else label_raw

    # Per-zone font family + size come from paradigm config. Compact variant
    # scales sizes down by ~78% (matches cellular sm-vs-xl specimen ratio).
    # chrome paradigm: JetBrains Mono + Orbitron @ 11/11; cellular: Orbitron
    # + Chakra Petch @ 9/12 (default) or 7/9 (compact).
    _label_family = paradigm_spec.badge.label_font_family if paradigm_spec else "Inter"
    _value_family = paradigm_spec.badge.value_font_family if paradigm_spec else "Inter"
    _label_weight = paradigm_spec.badge.label_font_weight if paradigm_spec else 700
    _value_weight = paradigm_spec.badge.value_font_weight if paradigm_spec else 700
    _label_size = paradigm_spec.badge.label_font_size if paradigm_spec else font_size
    _value_size = paradigm_spec.badge.value_font_size if paradigm_spec else font_size
    if compact:
        _label_size = max(round(_label_size * 0.78), 6)
        _value_size = max(round(_value_size * 0.78), 7)

    # Indicator size = the value-font cap height, so the status glyph reads as one
    # proportional accent sized to the text (never a fixed oversized block). Every
    # shape derives from this: square side, circle diameter, and diamond diagonal
    # all equal indicator_size (see circle/diamond geometry below). cap_ratio ≈
    # 0.72 (Orbitron / JetBrains Mono cap height ≈ 0.72em); paradigm-tunable.
    _cap_ratio = (
        badge_cfg_for_indicator.indicator_cap_ratio
        if badge_cfg_for_indicator and badge_cfg_for_indicator.indicator_cap_ratio > 0
        else 0.72
    )
    indicator_size = max(4, round(_value_size * _cap_ratio))

    # Letter-spacing values come from the paradigm's badge config so
    # measure_text reserves the exact width the template will render. The
    # paradigm's declared values are the canonical source; the
    # ``0.06 if use_mono else 0.0`` fallback preserves pre-v0.3.3 behavior
    # for paradigms (cellular, default) that haven't declared their badge
    # letter-spacing yet. measure_text applies ``(max(0, N-1) * font_size
    # * em)`` internally — single source of truth in core/text.py.
    _label_ls_em = (
        paradigm_spec.badge.label_letter_spacing_em
        if paradigm_spec and paradigm_spec.badge.label_letter_spacing_em > 0
        else (0.06 if use_mono else 0.0)
    )
    _value_ls_em = paradigm_spec.badge.value_letter_spacing_em if paradigm_spec else 0.0
    label_metrics = (
        measure_text_ink_metrics(
            label_display,
            font_family=_label_family,
            font_size=_label_size,
            font_weight=_label_weight,
            letter_spacing_em=_label_ls_em,
        )
        if label_display
        else None
    )
    value_metrics = (
        measure_text_ink_metrics(
            value_raw,
            font_family=_value_family,
            font_size=_value_size,
            font_weight=_value_weight,
            letter_spacing_em=_value_ls_em,
        )
        if value_raw
        else None
    )
    lw = label_metrics.advance_width if label_metrics is not None else 0.0
    vw = value_metrics.advance_width if value_metrics is not None else 0.0
    label_ink_w = label_metrics.ink_width if label_metrics is not None else 0.0
    value_ink_w = value_metrics.ink_width if value_metrics is not None else 0.0
    label_start_bearing = label_metrics.leading_bearing if label_metrics is not None else 0.0
    value_start_bearing = value_metrics.leading_bearing if value_metrics is not None else 0.0

    has_glyph = bool(glyph_path or glyph_data.get("custom_svg"))
    badge_cfg = paradigm_spec.badge if paradigm_spec else None

    # Legacy glyph-left offset fallback. Paradigms with rendered left
    # adornment geometry declare left_adornment_* below, so the layout engine
    # can position content from the actual bookend edge.
    badge_cfg_for_glyph = badge_cfg
    if badge_cfg_for_glyph is not None:
        if compact and badge_cfg_for_glyph.glyph_offset_left_compact > 0:
            glyph_left_offset = badge_cfg_for_glyph.glyph_offset_left_compact
        else:
            glyph_left_offset = badge_cfg_for_glyph.glyph_offset_left
    else:
        glyph_left_offset = 0

    # v0.2.25: three-mode state architecture. badge_mode drives indicator
    # rendering AND data-hw-statemode (which gates threshold-CSS auto-tinting).
    # Replaces the prior is_state_badge ad-hoc value-mirrors-state inference
    # with a title-allowlist + explicit-state precedence chain.
    from hyperweave.compose.layout import (
        compute_badge_zones,
        data_hw_statemode_for,
        resolve_badge_mode,
    )
    from hyperweave.config.loader import load_badge_modes

    badge_mode = resolve_badge_mode(spec, load_badge_modes())
    paradigm_show_indicator = paradigm_spec.badge.show_indicator if paradigm_spec is not None else True
    effective_show_indicator = paradigm_show_indicator and badge_mode != "stateless"

    # Paradigm-specific right-canvas-inset (cellular: 2px, brutalist/chrome: 0).
    right_canvas_inset = badge_cfg_for_seam.right_canvas_inset if badge_cfg_for_seam else 0

    # Unified additive badge layout: single cursor walk across all paradigms.
    # Paradigm-specific structural differences flow through ParadigmBadgeConfig
    # (pad, text_anchor, seam_render_w, seam_specular_offset). Half-gap rule
    # for etched seam (chrome) when seam_render_w > 0; structural separator
    # (sep_w + seam_w) for paradigms with seam_render_w == 0.
    pad = paradigm_spec.badge.pad if paradigm_spec else 8
    text_anchor = badge_cfg.text_anchor if badge_cfg else "middle"
    seam_render_w = badge_cfg.seam_render_w if badge_cfg else 0.0
    seam_specular_offset = badge_cfg.seam_specular_offset if badge_cfg else 0.0
    cellular_pattern_cols = badge_cfg.left_adornment_cols if badge_cfg else 0
    cellular_pattern_rows = badge_cfg.left_adornment_rows if badge_cfg else 0
    cellular_pattern_cell_w = 0
    cellular_pattern_cell_h = 0
    cellular_pattern_start_x = badge_cfg.left_adornment_start_x if badge_cfg else 0
    cellular_pattern_start_y = badge_cfg.left_adornment_start_y if badge_cfg else 0
    left_adornment_width = 0.0
    left_adornment_gap = 0.0
    glyph_label_gap = badge_cfg.glyph_label_gap if badge_cfg else 0.0
    visual_gap = badge_cfg.visual_gap if badge_cfg else 0.0
    if badge_cfg and cellular_pattern_cols > 0 and cellular_pattern_rows > 0:
        cellular_pattern_cell_w = (
            badge_cfg.left_adornment_cell_w_compact
            if compact and badge_cfg.left_adornment_cell_w_compact > 0
            else badge_cfg.left_adornment_cell_w
        )
        cellular_pattern_cell_h = (
            badge_cfg.left_adornment_cell_h_compact
            if compact and badge_cfg.left_adornment_cell_h_compact > 0
            else badge_cfg.left_adornment_cell_h
        )
        if cellular_pattern_cell_w > 0 and cellular_pattern_cell_h > 0:
            configured_adornment_width = (
                badge_cfg.left_adornment_width_compact
                if compact and badge_cfg.left_adornment_width_compact > 0
                else badge_cfg.left_adornment_width
            )
            left_adornment_width = float(
                configured_adornment_width
                if configured_adornment_width > 0
                else cellular_pattern_start_x + cellular_pattern_cols * cellular_pattern_cell_w
            )
            left_adornment_gap = float(badge_cfg.left_adornment_gap if badge_cfg.left_adornment_gap > 0 else pad)
    # Algorithmic bearing correction. Start-anchored chrome uses trailing
    # bearings to place seams at the visible ink edge. Centered cellular can
    # opt into full visual-gap layout, which also needs leading bearings so
    # the SVG middle anchor lands where the visible ink bounds require.
    use_visual_bearings = text_anchor == "start" or visual_gap > 0
    label_end_bearing = label_metrics.trailing_bearing if use_visual_bearings and label_metrics is not None else 0.0
    value_end_bearing = value_metrics.trailing_bearing if use_visual_bearings and value_metrics is not None else 0.0
    # Compact variant uses glyph_y_offset_compact when declared. The
    # text-visual-vs-frame-center delta scales with font size: cellular's
    # +2px at h=32/9px font becomes near zero at h=20/compact font.
    if compact and badge_cfg:
        glyph_y_offset = badge_cfg.glyph_y_offset_compact
    else:
        glyph_y_offset = badge_cfg.glyph_y_offset if badge_cfg else 0.0
    center_glyph_on_text_ink = (
        label_metrics is not None and badge_cfg is not None and badge_cfg.text_visual_center_offset_em != 0
    )
    text_ink_center_offset_y = label_metrics.ink_center_offset_y if label_metrics is not None else 0.0
    # Paradigm-aware min badge width. Zero defers to the layout engine's
    # default (60); chrome declares 40 for content-driven shrinkage.
    min_total_w = badge_cfg.min_total_width if badge_cfg and badge_cfg.min_total_width > 0 else 60
    zones = compute_badge_zones(
        height=height,
        pad=pad,
        measured_label_w=lw,
        measured_value_w=vw,
        has_glyph=has_glyph,
        has_state_indicator=effective_show_indicator,
        accent_w=accent_w,
        glyph_size=glyph_size,
        glyph_left_offset=glyph_left_offset,
        sep_w=sep_w,
        seam_w=seam_w,
        indicator_size=indicator_size,
        right_canvas_inset=right_canvas_inset,
        min_total_w=min_total_w,
        text_y_factor=text_y_factor,
        label_font_size=_label_size,
        value_font_size=_value_size,
        inner_bit_ratio=indicator_inner_bit_ratio,
        text_anchor=text_anchor,
        seam_render_w=seam_render_w,
        seam_specular_offset=seam_specular_offset,
        label_end_bearing=label_end_bearing,
        value_end_bearing=value_end_bearing,
        measured_label_ink_w=label_ink_w,
        measured_value_ink_w=value_ink_w,
        label_start_bearing=label_start_bearing,
        value_start_bearing=value_start_bearing,
        glyph_y_offset=glyph_y_offset,
        text_visual_center_offset_em=badge_cfg.text_visual_center_offset_em if badge_cfg else 0.3,
        text_ink_center_offset_y=text_ink_center_offset_y,
        center_glyph_on_text_ink=center_glyph_on_text_ink,
        glyph_visual_w=glyph_visual_w,
        left_adornment_width=left_adornment_width,
        left_adornment_gap=left_adornment_gap,
        glyph_label_gap=glyph_label_gap,
        visual_gap=visual_gap,
    )

    indicator_center_x = zones.indicator_x + zones.indicator_size / 2 if zones.show_indicator else 0.0
    # Single source: the indicator vertical center is computed once in
    # compose/layout.py (geometric, height/2) and consumed here so square,
    # circle, and diamond all anchor to the same midline regardless of paradigm.
    indicator_center_y = zones.indicator_center_y
    # Diamond is a rotated square: its vertical/horizontal extent is the DIAGONAL.
    # Side = indicator_size / sqrt(2) so the diamond's diagonal == indicator_size —
    # the same bounding height as the square and circle (one proportional accent
    # across shapes). Inner bit stays 0.55 of the side.
    diamond_outer_size = round(indicator_size / 1.41421356, 1)
    diamond_outer_half = round(diamond_outer_size / 2, 1)
    diamond_inner_size = round(max(1.0, diamond_outer_size * 0.55), 1)
    diamond_inner_half = round(diamond_inner_size / 2, 1)

    cellular_pattern_cells: list[dict[str, object]] = []
    cellular_color_grid = ((0, 2, 1, 0), (1, 0, 2, 1), (2, 1, 0, 2))
    cellular_class_grid = (("cz1", "czd", "cz3", "czf"), ("cz2", "cz4", "czd", "cz1"), ("czd", "czf", "cz2", "czd"))
    for col in range(cellular_pattern_cols):
        color_column = cellular_color_grid[col % len(cellular_color_grid)]
        class_column = cellular_class_grid[col % len(cellular_class_grid)]
        for row in range(cellular_pattern_rows):
            cellular_pattern_cells.append(
                {
                    "x": cellular_pattern_start_x + col * cellular_pattern_cell_w,
                    "y": cellular_pattern_start_y + row * cellular_pattern_cell_h,
                    "w": cellular_pattern_cell_w,
                    "h": cellular_pattern_cell_h,
                    "color_index": color_column[row % len(color_column)],
                    "css_class": class_column[row % len(class_column)],
                }
            )
    cellular_content_start_x = left_adornment_width + 6 if left_adornment_width > 0 else 0
    cellular_label_slab_x = left_adornment_width if left_adornment_width > 0 else 0
    cellular_value_slab_x = zones.left_panel_w + 1 + seam_w
    cellular_value_slab_w = zones.width - cellular_value_slab_x - 2
    right_panel_draw_x = zones.right_panel_x - 1
    right_panel_draw_w = zones.right_panel_w + 1
    light_perimeter_w = zones.width - 1
    light_perimeter_h = height - 1
    light_overlap_sep_x = zones.left_panel_w - 1
    seam_gap_x = zones.left_panel_w + sep_w
    chrome_well_w = zones.width - 4
    chrome_well_h = height - 4
    chrome_highlight_w = zones.width - 16
    chrome_separator_y2 = height - 5
    badge_origin_x = 0
    badge_origin_y = 0
    chrome_inner_inset = 1
    chrome_well_inset = 2
    chrome_inner_rx = 3
    chrome_well_rx = 2
    chrome_rail_w = 4
    chrome_highlight_x = 8
    chrome_highlight_y = 2
    chrome_highlight_h = 0.5
    chrome_highlight_rx = 0.25
    chrome_separator_y1 = 5
    chrome_seam_y1 = 4.5
    chrome_seam_y2 = height - 4.5
    chrome_diamond_outer_rx = 0.7
    chrome_diamond_inner_rx = 0.3
    chrome_diamond_stroke_width = 0.5
    cellular_inner_inset = 1
    cellular_canvas_inset = 2
    cellular_top_highlight_h = 1
    cellular_bottom_highlight_h = 0.5
    cellular_seam_w = 1
    light_perimeter_inset = 0.5
    light_badge_ink_divider_w = 4
    light_badge_seam_w = 2
    # Circle: diameter == indicator_size (radius = size/2), so it matches the
    # square side and diamond diagonal — one proportional accent across shapes.
    # Inner dot ~1/3 of the radius (the brutalist-light dot proportion), min 0.6.
    light_indicator_outer_r = round(indicator_size / 2, 1)
    light_indicator_inner_r = round(max(0.6, light_indicator_outer_r / 3), 1)
    light_indicator_stroke_width = 1.2

    # Variant resolution and profile visual context (envelope, well, specular,
    # chrome text gradients) are now applied universally by the dispatcher at
    # resolve() via _genome_material_context and resolve_variant — no
    # per-resolver call needed. The dispatcher's setdefault populates
    # frame_context["variant"] before ResolvedArtifact construction.
    return {
        "width": zones.width,
        "height": zones.height,
        "template": "frames/badge.svg.j2",
        "context": {
            "label": label_raw,
            "label_display": label_display,
            "value": value_raw,
            "label_font_family": f"'{_label_family}',sans-serif",
            "value_font_family": f"'{_value_family}',sans-serif",
            "left_panel_width": zones.left_panel_w,
            "right_panel_x": zones.right_panel_x,
            "right_panel_w": zones.right_panel_w,
            "right_panel_draw_x": right_panel_draw_x,
            "right_panel_draw_w": right_panel_draw_w,
            # v0.3.13 light badge: the GROUND panel butts directly against the
            # ink left panel (x = left_panel_width) and the 2px accent seam draws
            # on top — no separator-zone gap (the prototype has no gap; the dark
            # badge reserves the zone for its ink+state separator). Width spans
            # to the panel's right edge.
            "light_right_panel": {
                "x": zones.left_panel_w,
                "w": zones.right_panel_x + zones.right_panel_w - zones.left_panel_w,
            },
            "badge_origin_x": badge_origin_x,
            "badge_origin_y": badge_origin_y,
            "light_perimeter_w": light_perimeter_w,
            "light_perimeter_h": light_perimeter_h,
            "light_perimeter_inset": light_perimeter_inset,
            "light_overlap_sep_x": light_overlap_sep_x,
            "light_badge_ink_divider_w": light_badge_ink_divider_w,
            "light_badge_seam_w": light_badge_seam_w,
            "light_indicator_outer_r": light_indicator_outer_r,
            "light_indicator_inner_r": light_indicator_inner_r,
            "light_indicator_stroke_width": light_indicator_stroke_width,
            "seam_gap_x": seam_gap_x,
            "chrome_inner_inset": chrome_inner_inset,
            "chrome_well_inset": chrome_well_inset,
            "chrome_inner_rx": chrome_inner_rx,
            "chrome_well_rx": chrome_well_rx,
            "chrome_rail_w": chrome_rail_w,
            "chrome_well_w": chrome_well_w,
            "chrome_well_h": chrome_well_h,
            "chrome_highlight_x": chrome_highlight_x,
            "chrome_highlight_y": chrome_highlight_y,
            "chrome_highlight_w": chrome_highlight_w,
            "chrome_highlight_h": chrome_highlight_h,
            "chrome_highlight_rx": chrome_highlight_rx,
            "chrome_separator_y1": chrome_separator_y1,
            "chrome_separator_y2": chrome_separator_y2,
            "chrome_seam_y1": chrome_seam_y1,
            "chrome_seam_y2": chrome_seam_y2,
            "chrome_diamond_outer_rx": chrome_diamond_outer_rx,
            "chrome_diamond_inner_rx": chrome_diamond_inner_rx,
            "chrome_diamond_stroke_width": chrome_diamond_stroke_width,
            "text_y": zones.text_y,
            "glyph_x": zones.glyph_x,
            "glyph_y": zones.glyph_y,
            "glyph_render_size": glyph_size,
            "glyph_render_viewbox": glyph_render_viewbox,
            "glyph_render_ink_w": glyph_render_ink_w,
            "glyph_render_ink_h": glyph_render_ink_h,
            "glyph_optical_scale": glyph_optical_scale,
            "label_x": zones.label_x,
            "value_x": zones.value_x,
            "label_text_length": zones.label_text_length,
            "value_text_length": zones.value_text_length,
            # Chrome etched-seam coordinates.
            "seam_left_x": zones.seam_left_x,
            "seam_specular_x": zones.seam_specular_x,
            "seam_right_x": zones.seam_right_x,
            "text_anchor": zones.text_anchor,
            "value_zone_left": zones.value_zone_left,
            "value_zone_right": zones.value_zone_right,
            "value_zone_width": zones.value_zone_width,
            "indicator_x": zones.indicator_x,
            "indicator_y": zones.indicator_y,
            "indicator_center_x": indicator_center_x,
            "indicator_center_y": indicator_center_y,
            "sep_width": sep_w,
            "seam_width": seam_w,
            "indicator_size": zones.indicator_size,
            "inner_bit_w": zones.inner_bit_w,
            "inner_bit_offset": zones.inner_bit_offset,
            "diamond_outer_x": -diamond_outer_half,
            "diamond_outer_y": -diamond_outer_half,
            "diamond_outer_size": diamond_outer_size,
            "diamond_inner_x": -diamond_inner_half,
            "diamond_inner_y": -diamond_inner_half,
            "diamond_inner_size": diamond_inner_size,
            "indicator_stroke_width": indicator_stroke_width,
            "indicator_shape": indicator_shape,
            # Root data-hw-state-shape mirrors the rendered shape, but only when an
            # indicator actually paints (stateless badges reclaim the zone, so they
            # carry no shape). Empty string => document.svg.j2 omits the attribute.
            "data_hw_state_shape": indicator_shape if zones.show_indicator else "",
            "accent_bar_width": accent_w,
            "has_glyph": has_glyph,
            "show_indicator": zones.show_indicator,
            "use_mono": use_mono,
            "label_uppercase": label_uppercase,
            "badge_label_font_size": _label_size,
            "badge_value_font_size": _value_size,
            "inset": inset,
            "badge_mode": badge_mode,
            "data_hw_statemode": data_hw_statemode_for(badge_mode),
            # Backward-compat for cellular template's value-text class branch
            # (cellular-content.j2:104). Will be removed once cellular template
            # is updated to read badge_mode directly.
            "is_state_badge": badge_mode != "stateless",
            "compact": compact,
            "cellular_pattern_cells": cellular_pattern_cells,
            "cellular_inner_inset": cellular_inner_inset,
            "cellular_canvas_inset": cellular_canvas_inset,
            "cellular_top_highlight_h": cellular_top_highlight_h,
            "cellular_bottom_highlight_h": cellular_bottom_highlight_h,
            "cellular_seam_w": cellular_seam_w,
            "cellular_content_start_x": cellular_content_start_x,
            "cellular_label_slab_x": cellular_label_slab_x,
            "cellular_label_slab_w": zones.left_panel_w - cellular_label_slab_x,
            "cellular_seam_shadow_x": zones.left_panel_w + 1,
            "cellular_value_slab_x": cellular_value_slab_x,
            "cellular_value_slab_w": cellular_value_slab_w,
            "cellular_inner_stroke_w": zones.width - 2,
            "cellular_inner_stroke_h": height - 2,
            "cellular_inner_stroke_width": 0.5 if compact else 0.7,
            "cellular_canvas_w": zones.width - 4,
            "cellular_canvas_h": height - 4,
            "cellular_content_w": zones.width - cellular_content_start_x - 4,
            "cellular_bottom_y": height - 2.5,
        },
    }


def resolve_strip(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    *,
    glyph_data: dict[str, Any] | None = None,
    paradigm_spec: Any = None,
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve strip dimensions and layout.

    Layout: accent_bar | glyph_zone | identity_text | [divider | metric_cell]* | divider | status_zone
    Width = first_divider_x + n_metrics * pitch + status_zone

    When no glyph is present, the glyph zone (~36px) collapses and all
    downstream positions shift left so there's no dead space.
    """
    # Inline imports follow the convention in this file (see resolve_badge,
    # resolve_marquee): each resolver pulls only what it needs at the call site.
    from dataclasses import asdict

    from hyperweave.compose.schema import coerce_strip_input
    from hyperweave.core.cell_layout import TextSpec, compute_cell_layout
    from hyperweave.core.text import measure_text

    # Strip paradigm config is read here (once) so every downstream
    # measurement — identity, subtitle, metric labels, metric values —
    # uses the SAME paradigm fonts. No hardcoded fonts in this resolver.
    strip_cfg = paradigm_spec.strip if paradigm_spec else None
    height = strip_cfg.strip_height if strip_cfg else 52

    # Algorithmic strip glyph sizing. The identity glyph derives from
    # ``strip_height * strip_glyph_ratio`` so paradigms scale uniformly
    # instead of carrying hand-synced magic numbers.
    from hyperweave.compose.layout import compute_strip_glyph_size

    strip_glyph_size = compute_strip_glyph_size(height, strip_cfg.strip_glyph_ratio) if strip_cfg else 18

    input_data = coerce_strip_input(spec.connector_data, spec)
    metrics = [metric.model_dump() for metric in input_data.metrics]
    # min_metric_pitch is the brutalist-era aesthetic floor (106px) that
    # prevents cells from collapsing when metrics are short. When a paradigm
    # declares show_icon_box, it has its own structural chrome and font
    # discipline (cellular specimen: 82px widest cell at label 5.5 + value
    # 16), so the brutalist floor overshoots. Per-cell measurement plus the
    # 20px cell_pad below guarantees visual breathing in paradigms that opt
    # out of the legacy floor.
    show_icon_box_early = strip_cfg.show_icon_box if strip_cfg else False
    min_metric_pitch = 0 if show_icon_box_early else profile.get("strip_metric_pitch", 106)
    # Cell layout: every cell's group origin sits AT its left divider seam, so
    # the text inside (rendered at x_local=12 for cellular flush-left or
    # x_local=cell_w//2 for centered paradigms) gets a uniform gutter from
    # the seam. cell_widths[i] is the FULL seam-to-seam distance, content +
    # 20px pad split as 12 left + 8 right. There is NO extra cell-0 offset
    # — that bug shifted cell-0's text 24px past seam[0] while cells 1+ had
    # only 12px, producing visibly more black space on the left of the first
    # metric than the rest.

    # Glyph zone layout:
    #   paradigm opts into icon box (cellular):
    #     icon_box at (flank_end + icon_box_pad), size icon_box_size
    #     glyph centered inside icon box
    #   otherwise (brutalist/chrome): glyph floats at (accent_w + 12 + glyph_size/2)
    has_glyph = bool(glyph_data and glyph_data.get("path"))
    show_icon_box = strip_cfg.show_icon_box if strip_cfg else False
    icon_box_size = strip_cfg.icon_box_size if strip_cfg else 28
    icon_box_pad = strip_cfg.icon_box_pad if strip_cfg else 8
    # Accent bar vs. icon box are mutually exclusive identity-zone chromes:
    # a paradigm that opts into show_icon_box (cellular) uses the 28px box
    # as left-edge structural chrome; the 6px accent bar from the parent
    # profile (brutalist) would be phantom reserved width that shifts every
    # downstream coordinate by 6px without rendering anything.
    accent_w = 0 if show_icon_box else profile.get("strip_accent_width", 0)

    # Glyph zone width, glyph render coordinates, identity_x, identity zone
    # width, and first_divider_x all flow from compute_strip_zones below.
    # The inline arithmetic that used to live here is now centralized.

    # Compute identity zone width from actual text content. measure_text
    # absorbs letter-spacing via its ``letter_spacing_em`` kwarg using the
    # correct (N-1)-gap math; the previous "measure then add len * em"
    # idiom over-counted by one gap and silently disagreed with the
    # rendered width by ~1 char of letter-spacing.
    identity = spec.title or ""

    _id_family = strip_cfg.identity_font_family if strip_cfg else "JetBrains Mono"
    _id_size = strip_cfg.identity_font_size if strip_cfg else 11
    _id_weight = strip_cfg.identity_font_weight if strip_cfg else 700
    _id_ls_em = strip_cfg.identity_letter_spacing_em if strip_cfg else 0.18
    id_text_w = measure_text(
        identity.upper(),
        font_family=_id_family,
        font_size=_id_size,
        font_weight=_id_weight,
        letter_spacing_em=_id_ls_em,
    )

    # Subtitle (paradigm opts in): measured to potentially push identity
    # zone wider if subtitle is longer than identity. Fallback chain:
    # explicit normalized subtitle > spec.title uppercased (the project name
    # the user already provided) > genome.name
    # uppercased (last resort). Suppress subtitle entirely when it would
    # duplicate the identity text.
    show_subtitle = strip_cfg.show_subtitle if strip_cfg else False
    subtitle_raw = ""
    subtitle_w = 0.0
    if show_subtitle and strip_cfg is not None:
        subtitle_raw = input_data.identity_subtitle
        if not subtitle_raw and spec.title:
            subtitle_raw = str(spec.title).upper()
        if not subtitle_raw:
            subtitle_raw = str(genome.get("name") or genome.get("id") or "").upper()
        # Suppress duplicate subtitle: when derived subtitle equals the identity
        # text the strip would render two copies of the same string stacked
        # vertically. Empty subtitle_raw → template's {% else %} branch renders
        # single-line identity centered (no stack).
        if subtitle_raw and spec.title and subtitle_raw.upper() == spec.title.upper():
            subtitle_raw = ""
        if subtitle_raw:
            _sub_size = strip_cfg.subtitle_font_size
            subtitle_w = measure_text(
                subtitle_raw,
                font_family=strip_cfg.subtitle_font_family,
                font_size=_sub_size,
                font_weight=400,
                letter_spacing_em=strip_cfg.subtitle_letter_spacing_em,
            )

    # ── Per-cell adaptive widths via core/cell_layout.py ──
    # Single source of truth: every parameter that affects rendered cell
    # width (font family, size, weight, letter-spacing, cell_pad,
    # min_cell_w, anchor, text_inset) is read from the paradigm YAML and
    # passed once to ``compute_cell_layout``. The legacy split — where
    # the resolver measured at weight=700 and ls=0 while the template
    # rendered at weight=900 and ls=0.22em via CSS class — is removed.
    # Adding a new paradigm now requires zero Python edits to keep cells
    # sized to render-truth (Invariant 12).
    #
    # Each ``CellLayout`` carries the cell's pitch and the in-cell text x
    # for the configured anchor. Templates render coordinates verbatim;
    # no template-side ``cell_w // 2`` arithmetic.

    # Typography params sourced from paradigm config — font sizes, families,
    # weights, letter-spacing, padding, and aesthetic floor all come from
    # data/paradigms/{slug}.yaml. The legacy fallback (no strip_cfg) keeps
    # brutalist behavior: weight 700 labels, weight 900 values, no
    # letter-spacing, 20px pad, 106px floor.
    if strip_cfg is not None:
        value_size = strip_cfg.value_font_size
        label_size = strip_cfg.label_font_size
        value_family = strip_cfg.value_font_family
        label_family = strip_cfg.label_font_family
        label_weight = strip_cfg.label_font_weight
        label_ls_em = strip_cfg.label_letter_spacing_em
        value_weight = strip_cfg.value_font_weight
        value_ls_em = strip_cfg.value_letter_spacing_em
        # owns_strip (brutalist) derives cell_pad from the single strip_pad
        # source — 2*strip_pad is the pad on each side, so the inter-cell
        # content gap is a constant 2*strip_pad. Non-owns paradigms keep their
        # own cell_pad. v0.3.13 content-aware retune.
        cell_pad = 2 * strip_cfg.strip_pad if strip_cfg.owns_strip else strip_cfg.cell_pad
        cell_min_w = strip_cfg.cell_min_width
        text_anchor = strip_cfg.metric_text_anchor
        text_inset = strip_cfg.metric_text_x
    else:
        value_size = profile.get("strip_metric_value_size", 18)
        label_size = profile.get("strip_metric_label_size", 7)
        value_family = "Inter"
        label_family = "JetBrains Mono"
        label_weight = 700
        label_ls_em = 0.2
        value_weight = 900
        value_ls_em = -0.01
        cell_pad = 20
        cell_min_w = min_metric_pitch
        text_anchor = "middle"
        text_inset = 0

    cell_layouts_records: list[dict[str, Any]] = []
    for metric in metrics:
        raw_value = str(metric.get("value", ""))
        raw_label = str(metric.get("label", "")).upper()
        layout = compute_cell_layout(
            label=TextSpec(
                text=raw_label,
                font_family=label_family,
                font_size=label_size,
                font_weight=label_weight,
                letter_spacing_em=label_ls_em,
            ),
            value=TextSpec(
                text=raw_value,
                font_family=value_family,
                font_size=value_size,
                font_weight=value_weight,
                letter_spacing_em=value_ls_em,
            ),
            cell_pad=cell_pad,
            anchor=text_anchor,
            text_inset=text_inset,
            min_cell_w=cell_min_w,
        )
        cell_layouts_records.append(asdict(layout))

    # Backward-compatible scalar lists. ``cell_widths`` feeds the seam
    # cumulator below; ``metric_pitch`` is the widest-cell scalar kept
    # for any consumer that wants a uniform fallback.
    cell_widths: list[int] = [rec["cell_w"] for rec in cell_layouts_records]
    metric_pitch = max(cell_widths) if cell_widths else max(min_metric_pitch, cell_min_w)

    # v0.2.25: strip mode rolls up from metric labels via the badge
    # allowlist. STARS|FORKS|VERSION (all stateless) → no indicator,
    # no data-hw-statemode, no threshold-CSS auto-tinting. BUILD|STARS
    # (BUILD allowlisted) → strip is "auto" stateful and the right-edge
    # indicator renders. Explicit ?state= overrides everything.
    from hyperweave.compose.layout import data_hw_statemode_for, decide_strip_mode
    from hyperweave.config.loader import load_badge_modes

    strip_mode = decide_strip_mode(
        [m.get("label") for m in metrics],
        spec,
        load_badge_modes(),
    )

    # Status-indicator zone: tight-fit around the 14px indicator geometry.
    # Algorithmic sizing (pre_gap + indicator_size + post_gap) replaces the
    # former hardcoded 56px reserve, which left ~26px of dead black space
    # between the indicator and the right flank. Now: 16 pre-gap (matches
    # spec strip v10: last_seam=400 → frame_x=416) + 14 indicator + 4 post-gap.
    paradigm_show_status_indicator = strip_cfg.show_status_indicator if strip_cfg else True
    show_status_indicator = paradigm_show_status_indicator and strip_mode != "stateless"

    # Bifamily flank zones: paradigm declares flank_width > 0 when chromatic
    # flanking cells render at left/right edges (automata strips: 36px of
    # teal cells left, 36px amethyst right). Zero disables.
    flank_width = strip_cfg.flank_width if strip_cfg else 0
    flank_cell_size = strip_cfg.flank_cell_size if strip_cfg else 12
    has_flanks = flank_width > 0

    # v0.3.9: ALL strip geometry centralized in compute_strip_zones.
    # Replaces inline arithmetic for glyph zone, identity zone, first divider,
    # cell positions, seams, status indicator, bookend, flank shifts, and
    # strip_min_width clamp. Templates consume zone fields verbatim.
    from hyperweave.compose.layout import compute_strip_zones

    paradigm_owns_strip = bool(strip_cfg and strip_cfg.owns_strip)
    _post_indicator_gap = 16 if show_icon_box else 4
    # v0.3.13 brutalist-light: the right terminus becomes a fixed-width INK
    # bookend (matching the left identity panel) holding a breathing/state
    # square. Reserve its width here and suppress the separate status-zone
    # reservation — the bookend itself carries the indicator. Dark is untouched.
    strip_is_light = paradigm_owns_strip and str(genome.get("substrate_kind") or "dark") == "light"
    _light_bookend_w = 28
    # Light strips ALWAYS reserve the terminus (even stateless) so the ink
    # bookend has room: the owns_strip terminus path sets width = bookend_x +
    # bookend_pad_right. Dark keeps its state-driven reclaim. The light content
    # partial draws its own bookend, so the shared status include is dropped.
    strip_status_for_zones = True if strip_is_light else show_status_indicator
    zones = compute_strip_zones(
        height=height,
        owns_strip=paradigm_owns_strip,
        accent_w=accent_w,
        show_icon_box=show_icon_box,
        icon_box_size=icon_box_size,
        icon_box_pad=icon_box_pad,
        has_identity_glyph=has_glyph,
        strip_glyph_size=strip_glyph_size,
        brand_panel_x=strip_cfg.brand_panel_x if strip_cfg else 0,
        brand_panel_width=strip_cfg.brand_panel_width if strip_cfg else 0,
        identity_text_x=strip_cfg.identity_text_x if strip_cfg else 0,
        identity_panel_pad=strip_cfg.strip_pad if strip_cfg else 8,
        brand_divider_x=strip_cfg.brand_divider_x if strip_cfg else 0,
        triple_divider_bar_width=strip_cfg.triple_divider_bar_width if strip_cfg else 3,
        triple_divider_void_width=strip_cfg.triple_divider_void_width if strip_cfg else 2,
        bookend_x_fallback=strip_cfg.bookend_x if strip_cfg else 0,
        # v0.3.13: tight right margin = strip_pad after the terminus box
        # (status/ornament is ornament_size, centered at bookend_x). Replaces
        # the legacy 40px trailing that left dead space on the right edge.
        bookend_pad_right=_light_bookend_w
        if strip_is_light
        else (strip_cfg.ornament_size // 2 + strip_cfg.strip_pad)
        if (strip_cfg and strip_cfg.owns_strip)
        else 40,
        ornament_x=strip_cfg.ornament_x if strip_cfg else 0,
        ornament_y=strip_cfg.ornament_y if strip_cfg else 0,
        ornament_size=strip_cfg.ornament_size if strip_cfg else 14,
        ornament_inner_inset=strip_cfg.ornament_inner_inset if strip_cfg else 3,
        identity_w=id_text_w,
        subtitle_w=subtitle_w,
        subtitle_text=subtitle_raw,
        cell_widths=cell_widths,
        cell_layouts_records=cell_layouts_records,
        metric_pitch_fallback=metric_pitch,
        has_status_indicator=strip_status_for_zones,
        status_indicator_post_gap=_post_indicator_gap,
        flank_width=flank_width,
        flank_cell_size=flank_cell_size,
        strip_min_width=strip_cfg.strip_min_width if strip_cfg else 0,
    )
    width = zones.width
    content_width = zones.content_width
    content_right = zones.content_right
    first_divider_x = zones.first_divider_x
    seams = zones.seam_positions
    status_x = zones.status_x
    glyph_zone_x_offset = zones.glyph_zone_x_offset
    identity_clip_x = accent_w + glyph_zone_x_offset
    identity_clip_width = max(0.0, first_divider_x - identity_clip_x)

    ctx: dict[str, Any] = {
        "strip_zones": zones,
        "identity": identity,
        "identity_subtitle": input_data.identity_subtitle,
        "metric_slots": [metric.model_dump() for metric in input_data.metrics],
        "identity_font_family": _id_family,
        "identity_font_size": _id_size,
        "identity_letter_spacing_em": _id_ls_em,
        "identity_text_length": zones.identity_text_length,
        "subtitle_text": subtitle_raw,
        "show_subtitle": show_subtitle,
        "subtitle_font_family": strip_cfg.subtitle_font_family if strip_cfg else "JetBrains Mono",
        "subtitle_font_size": strip_cfg.subtitle_font_size if strip_cfg else 6.5,
        "subtitle_letter_spacing_em": strip_cfg.subtitle_letter_spacing_em if strip_cfg else 0.0,
        "show_icon_box": show_icon_box,
        "icon_box_size": icon_box_size,
        "icon_box_pad": icon_box_pad,
        # v0.3.9 algorithmic strip glyph sizing — derived from
        # ``strip_height * strip_glyph_ratio`` rather than per-paradigm magic
        # numbers. Both ``paradigm_strip_glyph_size`` (consumed by the parent
        # strip.svg.j2 dispatcher) and ``strip_glyph_size`` (consumed by
        # owns_strip paradigm content templates) carry the same computed
        # value so chrome/cellular shared-pipeline and brutalist owns_strip
        # paths render glyphs at the same proportional size.
        "paradigm_strip_glyph_size": strip_glyph_size,
        "metrics": metrics,
        "metric_pitch": metric_pitch,
        # Per-cell adaptive widths — sized to each metric's own content
        # (value or label, whichever is wider) + cell_pad. The strip
        # template iterates this list with a running x-offset so cells
        # sit flush-left against their content rather than padded inside
        # a uniform widest-cell pitch. See resolver.py per-cell-widths
        # section for rationale.
        # cell_widths + cell_layouts come from compute_strip_zones so strip
        # min-width stretching updates per-cell widths and re-centers
        # middle-anchored text. Local cell_widths / cell_layouts_records are
        # only the inputs to the zone engine.
        "cell_widths": zones.cell_widths,
        "cell_layouts": zones.cell_layouts_records,
        # first_divider_x is already shifted into the flank-aware coordinate
        # frame by compute_strip_zones. Identity, dividers, and metric cells
        # all operate in the same reference frame.
        "first_divider_x": first_divider_x,
        "seam_positions": seams,
        "status_x": status_x,
        "status_cy": height / 2,
        "indicator_size": 14,
        "strip_origin_x": 0,
        "strip_origin_y": 0,
        "strip_perimeter_inset": 0.5,
        "strip_metric_delta_y": 48,
        "strip_metric_local_origin_x": 0,
        "strip_metric_local_origin_y": 0,
        "strip_identity_clip_y": 0,
        "strip_chrome_inner_inset": 1,
        "strip_chrome_well_inset": 2,
        "strip_chrome_well_rx": 2,
        "strip_chrome_highlight_x": 8,
        "strip_chrome_highlight_y": 2,
        "strip_chrome_highlight_h": 0.5,
        "strip_chrome_highlight_rx": 0.25,
        "strip_cellular_panel_y": 2,
        "content_right": content_right,
        "glyph_zone_x_offset": glyph_zone_x_offset,
        "icon_box_x": zones.icon_box_x,
        "icon_box_y": zones.icon_box_y,
        "strip_glyph_cx": zones.glyph_cx,
        "strip_glyph_cy": zones.glyph_cy,
        "strip_glyph_render_size": zones.glyph_size,
        "identity_x": zones.identity_x,
        "identity_clip_x": identity_clip_x,
        "identity_clip_width": identity_clip_width,
        "identity_single_y": height / 2 + 4,
        "identity_stack_y": height / 2 - 4,
        "subtitle_y": height / 2 + 9,
        "strip_divider_y1": 8,
        "strip_divider_y2": height - 8,
        "strip_perimeter_w": zones.perimeter_w,
        "strip_perimeter_h": zones.perimeter_h,
        "strip_half_h": zones.half_h,
        "strip_glyph_svg_x": zones.glyph_svg_x,
        "strip_glyph_svg_y": zones.glyph_svg_y,
        "show_status_indicator": show_status_indicator,
        # Brutalist-light ink bookend geometry (right terminus). When present the
        # light content partial paints an ink rect with a breathing square
        # (stateless) or a double-square state indicator (stateful) inside.
        "light_strip_bookend": strip_is_light,
        "light_bookend_ink": {"x": width - _light_bookend_w, "y": 0, "w": _light_bookend_w, "h": height},
        "light_bookend_edge": {"x": width - _light_bookend_w, "y": 0, "w": 2, "h": height},
        "light_bookend_square": {
            "x": width - _light_bookend_w / 2 - 4.5,
            "y": height / 2 - 4.5,
            "w": 9,
            "h": 9,
        },
        "light_bookend_state_outer": {
            "x": width - _light_bookend_w / 2 - 5.5,
            "y": height / 2 - 5.5,
            "w": 11,
            "h": 11,
        },
        "light_bookend_state_inner": {
            "x": width - _light_bookend_w / 2 - 2.5,
            "y": height / 2 - 2.5,
            "w": 5,
            "h": 5,
        },
        "light_bookend_has_state": show_status_indicator,
        "strip_mode": strip_mode,
        "data_hw_statemode": data_hw_statemode_for(strip_mode),
        # content_width is where visible strip content ends. When strip_min_width
        # clamps the SVG viewBox, content_width < width; chrome envelope/well/
        # rail render at content_width so trailing pixels past content stay
        # transparent with no internal dead space.
        "content_width": content_width,
        "has_flanks": has_flanks,
        "flank_width": flank_width,
        "flank_cell_size": flank_cell_size,
        "strip_corner": profile.get("strip_corner", 5),
        # accent_width/accent_bar_width/has_accent reflect the same rule as
        # the local accent_w above: paradigms with show_icon_box zero out
        # the accent bar so downstream computed coordinates stay aligned with
        # the specimen.
        "accent_width": accent_w,
        "accent_bar_width": accent_w,
        "divider_mode": profile.get("strip_divider_mode", "full"),
        "has_accent": accent_w > 0,
        "strip_glyph_size": strip_glyph_size,
        "strip_glyph_fill": profile.get("strip_glyph_fill", "var(--dna-signal)"),
        "strip_identity_weight": profile.get("strip_identity_weight", 900),
        "strip_identity_fill": profile.get("strip_identity_fill", "var(--dna-brand-text)"),
        "strip_identity_letter_spacing": profile.get("strip_identity_letter_spacing", "0.18em"),
        # Paradigm-driven label size (cellular: 5.5) takes precedence over
        # the profile default (brutalist: 7). The resolver MEASURES at this
        # size too (line ~442) — keeping a single source of truth prevents
        # measurement/render drift that overflows cells.
        "strip_metric_label_size": (
            strip_cfg.label_font_size if strip_cfg else profile.get("strip_metric_label_size", 7)
        ),
        "strip_metric_label_fill": profile.get("strip_metric_label_fill", "var(--dna-ink-muted)"),
        "strip_metric_label_letter_spacing": profile.get("strip_metric_label_letter_spacing", "0.2em"),
        "strip_metric_label_y": profile.get("strip_metric_label_y", 18),
        "strip_metric_value_weight": profile.get("strip_metric_value_weight", 900),
        "strip_metric_value_fill": profile.get("strip_metric_value_fill", "var(--dna-ink-primary)"),
        "strip_metric_value_y": profile.get("strip_metric_value_y", 36),
        "strip_metric_value_skew": profile.get("strip_metric_value_skew", 0),
        # Metric cell alignment — paradigm declares the text-anchor + x-offset
        # so the shared metric loop in strip.svg.j2 doesn't need per-paradigm
        # branches. Cellular → flush-left via ``start`` + inset 12;
        # brutalist/chrome → centered via ``middle`` + fallback x (pitch//2).
        "strip_metric_text_x": (strip_cfg.metric_text_x if strip_cfg else 0),
        "strip_metric_text_anchor": (strip_cfg.metric_text_anchor if strip_cfg else "middle"),
        "strip_identity_font": profile.get("strip_identity_font", "var(--dna-font-mono, 'SF Mono', monospace)"),
        "strip_metric_label_font": profile.get("strip_metric_label_font", "var(--dna-font-mono, 'SF Mono', monospace)"),
        "strip_divider_color": profile.get("strip_divider_color", "var(--dna-border)"),
        "strip_divider_opacity": profile.get("strip_divider_opacity", 1.0),
        "strip_status_outer_x": zones.status_outer_x,
        "strip_status_outer_y": zones.status_outer_y,
        "strip_status_inner_x": zones.status_inner_x,
        "strip_status_inner_y": zones.status_inner_y,
        "strip_status_inner_w": zones.status_inner_w,
        "strip_status_inner_h": zones.status_inner_h,
        "cellular_status_inner_x": zones.status_cellular_inner_x,
        "cellular_status_inner_y": zones.status_cellular_inner_y,
        "cellular_status_inner_w": zones.status_cellular_inner_w,
        "cellular_status_inner_h": zones.status_cellular_inner_h,
        "strip_status_chrome_outer_x": zones.status_chrome_outer_x,
        "strip_status_chrome_outer_y": zones.status_chrome_outer_y,
        "strip_status_chrome_outer_size": zones.status_chrome_outer_size,
        "strip_status_chrome_outer_rx": zones.status_chrome_outer_rx,
        "strip_status_chrome_inner_x": zones.status_chrome_inner_x,
        "strip_status_chrome_inner_y": zones.status_chrome_inner_y,
        "strip_status_chrome_inner_size": zones.status_chrome_inner_size,
        "strip_status_chrome_inner_rx": zones.status_chrome_inner_rx,
        "strip_chrome_inner_w": zones.chrome_inner_w,
        "strip_chrome_inner_h": zones.chrome_inner_h,
        "strip_chrome_well_w": zones.chrome_well_w,
        "strip_chrome_well_h": zones.chrome_well_h,
        "strip_chrome_accent_h": zones.chrome_accent_h,
        "strip_chrome_highlight_w": zones.chrome_highlight_w,
        "cellular_left_flank_cells": zones.cellular_left_flank_cells or [],
        "cellular_right_flank_cells": zones.cellular_right_flank_cells or [],
        "cellular_panel_x": zones.cellular_panel_x,
        "cellular_panel_w": zones.cellular_panel_w,
        "cellular_panel_h": zones.cellular_panel_h,
    }
    # Phase 4A: surface paradigm-driven divider/status rendering context so
    # templates branch on resolved values (``divider_render_mode``,
    # ``status_shape_rendering``) instead of comparing ``paradigm == "chrome"``.
    if strip_cfg is not None:
        ctx["divider_render_mode"] = strip_cfg.divider_render_mode
        ctx["status_shape_rendering"] = strip_cfg.status_shape_rendering
    else:
        ctx["divider_render_mode"] = "class"
        ctx["status_shape_rendering"] = "crispEdges"
    # Profile visual context now injected centrally by the dispatcher.

    # v0.3.2 Phase C brutalist strip grammar — owns_strip flag + geometry
    # plumbing. When the paradigm declares owns_strip=true (brutalist v0.3.2),
    # the parent strip.svg.j2 wraps its shared zone pipeline in
    # ``{% if not paradigm_owns_strip %}`` and the paradigm content-partial
    # renders brand panel + triple divider + ornament + metric cells + bookend
    # itself. The geometry fields below feed that partial. Unconditional
    # assignment guarantees StrictUndefined never trips on chrome / cellular /
    # default paradigms (which leave owns_strip at the schema default of False).
    ctx["paradigm_owns_strip"] = paradigm_owns_strip
    if paradigm_owns_strip and strip_cfg is not None:
        # brand_panel_x/w, triple_divider_x, brand_divider_x all come from
        # compute_strip_zones (content-driven, brand_panel_width
        # treated as MAX ceiling). YAML values pass into zone computation; zone
        # outputs flow into context. Short identities (N8N) render with a
        # shrunken panel; long identities (AUTOGPT) shrink-to-fit via textLength
        # while panel stays at MAX.
        ctx["brand_panel_x"] = zones.brand_panel_x
        ctx["brand_panel_w"] = zones.brand_panel_w
        ctx["triple_divider_x"] = zones.triple_divider_x
        ctx["triple_divider_void_x"] = zones.triple_divider_void_x
        ctx["triple_divider_right_x"] = zones.triple_divider_right_x
        ctx["triple_divider_bar_w"] = strip_cfg.triple_divider_bar_width
        ctx["triple_divider_void_w"] = strip_cfg.triple_divider_void_width
        ctx["ornament_x"] = strip_cfg.ornament_x
        ctx["ornament_y"] = strip_cfg.ornament_y
        ctx["ornament_size"] = strip_cfg.ornament_size
        ctx["ornament_inner_inset"] = strip_cfg.ornament_inner_inset
        ctx["identity_glyph_x"] = zones.identity_glyph_x
        ctx["identity_glyph_y"] = zones.identity_glyph_y
        ctx["ornament_inner_x"] = zones.ornament_inner_x
        ctx["ornament_inner_y"] = zones.ornament_inner_y
        ctx["ornament_inner_w"] = zones.ornament_inner_w
        ctx["ornament_inner_h"] = zones.ornament_inner_h
        ctx["bookend_outer_x"] = zones.bookend_outer_x
        ctx["bookend_outer_y"] = zones.bookend_outer_y
        ctx["bookend_inner_x"] = zones.bookend_inner_x
        ctx["bookend_inner_y"] = zones.bookend_inner_y
        ctx["bookend_inner_w"] = zones.bookend_inner_w
        ctx["bookend_inner_h"] = zones.bookend_inner_h
        ctx["metric_rule_y1"] = zones.metric_rule_y1
        ctx["metric_rule_y2"] = zones.metric_rule_y2
        # v0.3.9 algorithmic strip glyph: the LEFT identity glyph is sized
        # via ``strip_glyph_size`` (derived from strip_height * ratio),
        # distinct from the right-edge bookend square sized by ornament_size.
        # Both sizes are now derived rather than carrying independent magic
        # numbers — previous identity_glyph_size field has been removed.
        ctx["bookend_x"] = zones.bookend_x
        ctx["identity_text_x"] = strip_cfg.identity_text_x
        ctx["identity_text_y"] = strip_cfg.identity_text_y
        ctx["identity_text_length"] = zones.identity_text_length
        ctx["metric_label_y"] = strip_cfg.metric_label_y
        ctx["metric_value_y"] = strip_cfg.metric_value_y
        # Brand panel fill (dark variants) / panel gradient stops (light variants)
        # already merged onto the genome dict by the resolver; expose directly
        # so the content partials can paint the panel without re-reading genome.
        ctx["brand_panel_fill"] = genome.get("brand_panel_fill", "")

    return {
        "width": width,
        "height": height,
        "template": "frames/strip.svg.j2",
        "context": ctx,
    }


def resolve_icon(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    paradigm_spec: Any = None,
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve icon dimensions.

    Four frame variants selected by icon_variant:
      - brutalist-circular: concentric rings, glyph-dominant, no label
      - brutalist-square: top accent bar, heavy border, no label
      - binary-circular: chrome envelope ring, circle frame
      - binary-square: chrome envelope fill, rounded-rect frame

    Shape selection: paradigm declares supported shapes and default;
    ``spec.shape`` overrides the default when valid.
    """
    icon_label = spec.glyph or spec.title or ""
    profile_id = profile.get("id", "brutalist")

    # Shape availability + default now live in data/paradigms/{slug}.yaml —
    # no more hardcoded profile→shapes map in Python.
    if paradigm_spec is not None:
        supported = list(paradigm_spec.icon.supported_shapes)
        default_shape = paradigm_spec.icon.default_shape
    else:
        supported = ["square", "circle"]
        default_shape = "square"
    raw_shape = spec.shape if spec.shape else default_shape
    shape = raw_shape if raw_shape in supported else default_shape

    # Map (profile, shape) -> icon_variant for template branching
    _BRUTALIST_VARIANT = {"circle": "brutalist-circular", "square": "brutalist-square"}
    if profile_id == ProfileId.BRUTALIST:
        icon_variant = _BRUTALIST_VARIANT[shape]
    elif shape == "circle":
        icon_variant = "binary-circular"
    else:
        icon_variant = "binary-square"

    # Paradigm-driven viewBox + card dim override. Chrome paradigm sets
    # viewbox_w/h=120 (120-unit material discipline at 64px rendered size).
    # Cellular paradigm v0.3.0 refresh sets card_width/height=48 and exposes
    # cell grid + inner canvas geometry so the template stamps pre-computed
    # values rather than carrying its own dimension constants.
    icon_cfg = paradigm_spec.icon if paradigm_spec is not None else None
    viewbox_w = getattr(icon_cfg, "viewbox_w", 0) if icon_cfg is not None else 0
    viewbox_h = getattr(icon_cfg, "viewbox_h", 0) if icon_cfg is not None else 0
    # Card dimensions — paradigm config overrides the historic 64x64. Cellular
    # v0.3.0 uses 48x48 with a 5x5 living cell grid; brutalist/chrome stay at
    # the 64x64 default.
    card_w = int(icon_cfg.card_width) if icon_cfg is not None and getattr(icon_cfg, "card_width", 0) > 0 else 64
    card_h = int(icon_cfg.card_height) if icon_cfg is not None and getattr(icon_cfg, "card_height", 0) > 0 else 64

    # Cellular icon geometry — read from paradigm config so the template stays
    # arithmetic-free per CLAUDE.md "Compose owns geometry, template renders".
    if icon_cfg is not None:
        icon_grid_cols = int(getattr(icon_cfg, "cell_grid_cols", 0))
        icon_grid_rows = int(getattr(icon_cfg, "cell_grid_rows", 0))
        icon_cell_size = int(getattr(icon_cfg, "cell_size", 0))
        icon_cell_gap = int(getattr(icon_cfg, "cell_gap", 0))
        icon_cell_rx = int(getattr(icon_cfg, "cell_rx", 0))
        icon_inner_inset = float(getattr(icon_cfg, "inner_canvas_inset", 0) or 0)
        icon_inner_size = float(getattr(icon_cfg, "inner_canvas_size", 0) or 0)
        icon_inner_rx = int(getattr(icon_cfg, "inner_canvas_rx", 0))
        icon_glyph_inset = float(getattr(icon_cfg, "glyph_inset", 0) or 0)
        icon_glyph_size = float(getattr(icon_cfg, "glyph_size", 0) or 0)
        icon_outer_rx = int(getattr(icon_cfg, "outer_border_rx", 0))
    else:
        icon_grid_cols = icon_grid_rows = icon_cell_size = icon_cell_gap = icon_cell_rx = 0
        icon_inner_inset = icon_inner_size = 0.0
        icon_inner_rx = 0
        icon_glyph_inset = icon_glyph_size = 0.0
        icon_outer_rx = 0

    # Cellular palette accent fields — surface info_accent / mid_accent /
    # header_band so the cellular icon template can fill the cell grid + glyph
    # + borders without consulting the genome dict directly.
    cellular_palette = _kw.get("cellular_palette") or {}
    primary_tone = cellular_palette.get("primary") or {}
    icon_info_accent = primary_tone.get("info_accent", "")
    icon_mid_accent = primary_tone.get("mid_accent", "")
    icon_header_band = primary_tone.get("header_band", "")
    icon_cell_stride = icon_cell_size + icon_cell_gap
    chart_levels = primary_tone.get("chart_levels") or []
    icon_dark_active = chart_levels[1] if len(chart_levels) > 1 else icon_mid_accent
    icon_slot_table = [
        2,
        4,
        0,
        3,
        1,
        0,
        1,
        4,
        2,
        3,
        3,
        2,
        1,
        4,
        0,
        4,
        0,
        3,
        1,
        2,
        1,
        3,
        2,
        0,
        4,
    ]
    icon_cell_classes = ["cz1", "cz2", "cz3", "cz4", "czd"]
    icon_cell_fills = [icon_dark_active, icon_mid_accent, icon_info_accent, icon_mid_accent, icon_header_band]
    icon_cells: list[dict[str, Any]] = []
    if icon_grid_cols > 0 and icon_grid_rows > 0 and icon_cell_size > 0:
        for row in range(icon_grid_rows):
            for col in range(icon_grid_cols):
                slot = icon_slot_table[row * icon_grid_cols + col]
                icon_cells.append(
                    {
                        "x": col * icon_cell_stride,
                        "y": row * icon_cell_stride,
                        "size": icon_cell_size,
                        "rx": icon_cell_rx,
                        "class_name": icon_cell_classes[slot],
                        "fill": icon_cell_fills[slot],
                    }
                )

    icon_geometry = {
        "chrome_square_group_x": 6,
        "chrome_square_group_y": 6,
        "chrome_square_outer_w": 96,
        "chrome_square_outer_h": 96,
        "chrome_square_outer_rx": 6,
        "chrome_square_inner_x": 1.5,
        "chrome_square_inner_y": 1.5,
        "chrome_square_inner_w": 93,
        "chrome_square_inner_h": 93,
        "chrome_square_inner_rx": 4.5,
        "chrome_square_well_x": 3,
        "chrome_square_well_y": 3,
        "chrome_square_well_w": 90,
        "chrome_square_well_h": 90,
        "chrome_square_well_rx": 3.2,
        "chrome_square_rail_x": 3,
        "chrome_square_rail_y": 3,
        "chrome_square_rail_w": 6,
        "chrome_square_rail_h": 90,
        "chrome_square_accent_x": 14,
        "chrome_square_accent_y": 3,
        "chrome_square_accent_w": 76,
        "chrome_square_accent_h": 0.6,
        "chrome_square_glyph_x": 30,
        "chrome_square_glyph_y": 30,
        "chrome_square_glyph_size": 36,
        "chrome_circle_group_x": 54,
        "chrome_circle_group_y": 54,
        "chrome_circle_outer_r": 46,
        "chrome_circle_well_r": 42,
        "chrome_circle_glyph_x": -24,
        "chrome_circle_glyph_y": -24,
        "chrome_circle_glyph_size": 48,
        # v0.3.13 icon geometry matches the brutalist-light prototype and is
        # shared by BOTH substrates: ink disc r=30 with a thin accent EDGE ring
        # at r=29 (an inset border at the perimeter — not the prior small inner
        # ring at r=24), a larger centered glyph, and a 6px accent square cap.
        "brutalist_circle_cx": 32,
        "brutalist_circle_cy": 32,
        "brutalist_circle_r": 30,
        "brutalist_circle_rim_r": 29,
        "brutalist_circle_glyph_x": 16,
        "brutalist_circle_glyph_y": 16,
        "brutalist_circle_glyph_size": 32,
        "brutalist_square_x": 2,
        "brutalist_square_y": 2,
        "brutalist_square_w": 60,
        "brutalist_square_h": 60,
        "brutalist_square_border_x": 1.25,
        "brutalist_square_border_y": 1.25,
        "brutalist_square_border_w": 61.5,
        "brutalist_square_border_h": 61.5,
        "brutalist_square_accent_h": 6,
        "brutalist_square_glyph_x": 16,
        "brutalist_square_glyph_y": 18,
        "brutalist_square_glyph_size": 32,
        "cellular_border_x": 0.5,
        "cellular_border_y": 0.5,
    }

    ctx: dict[str, Any] = {
        "icon_shape": shape,
        "icon_rx": 0,
        "icon_label": icon_label,
        "icon_variant": icon_variant,
        "icon_geometry": icon_geometry,
        # Raw genome hex colors for gradient stops (CSS var() doesn't work in SVG stops)
        "genome_signal": genome.get("accent", "#845ef7"),
        "genome_surface": genome.get("surface_0", "#000000"),
        "genome_ink": genome.get("ink", "#ffffff"),
        "genome_border": genome.get("stroke", "#000000"),
        "genome_signal_dim": genome.get("accent_complement", "#A78BFA"),
        # viewBox overrides — zero means "use width/height" (handled by template default).
        "viewbox_w": viewbox_w,
        "viewbox_h": viewbox_h,
        # Cellular icon geometry (paradigm-driven; zero on non-cellular paradigms).
        "icon_grid_cols": icon_grid_cols,
        "icon_grid_rows": icon_grid_rows,
        "icon_cell_size": icon_cell_size,
        "icon_cell_gap": icon_cell_gap,
        "icon_cell_rx": icon_cell_rx,
        "icon_inner_inset": icon_inner_inset,
        "icon_inner_size": icon_inner_size,
        "icon_inner_rx": icon_inner_rx,
        "icon_glyph_inset": icon_glyph_inset,
        "icon_glyph_size": icon_glyph_size,
        "icon_outer_rx": icon_outer_rx,
        "icon_cells": icon_cells,
        "icon_outer_w": card_w - 1,
        "icon_outer_h": card_h - 1,
        "icon_surface_fill": genome.get("surface_0", "var(--dna-surface)"),
        # Cellular accent stops.
        "icon_info_accent": icon_info_accent,
        "icon_mid_accent": icon_mid_accent,
        "icon_header_band": icon_header_band,
    }
    # Profile visual context now injected centrally by the dispatcher.

    return {
        "width": card_w,
        "height": card_h,
        "template": "frames/icon.svg.j2",
        "context": ctx,
    }


def _divider_stop(offset: str, color: str, opacity: str | None = None) -> dict[str, str]:
    """Return a divider gradient stop record for stencil templates."""
    stop = {"offset": offset, "color": color}
    if opacity is not None:
        stop["opacity"] = opacity
    return stop


def _divider_geometry_context(
    *,
    variant: str,
    width: int,
    height: int,
    cellular_palette: dict[str, Any],
) -> dict[str, Any]:
    """Compute legacy divider geometry and specimen palettes outside Jinja."""
    cy = height // 2
    cx = width // 2
    block_size = 20
    block_half = block_size // 2
    block_spread = int(width * 0.257)
    current_points = {
        "p1": int(width * 0.125),
        "p2": int(width * 0.25),
        "p3": int(width * 0.375),
        "p4": int(width * 0.5),
        "p5": int(width * 0.625),
        "p6": int(width * 0.75),
        "p7": int(width * 0.875),
    }
    current_amp = int(height * 0.33)
    takeoff_rx = cx
    takeoff_dip = int(height * 0.3)
    aura_rx = int(width * 0.45)
    filament_x = int(width * 0.05)
    bridge = cellular_palette.get("bridge") or {}
    primary_main = str(bridge.get("primary_main") or "")
    primary_deep = str(bridge.get("primary_alt") or "")
    secondary_main = str(bridge.get("secondary_main") or "")
    secondary_deep = str(bridge.get("secondary_alt") or "")
    dissolve_left_cells: list[dict[str, object]] = []
    dissolve_right_cells: list[dict[str, object]] = []
    for col in range(4):
        for row in range(2):
            dissolve_left_cells.append(
                {
                    "x": col * 12,
                    "y": 2 + row * 12,
                    "w": 12,
                    "h": 12,
                    "fill": primary_main if (col + row) % 2 == 0 else primary_deep,
                }
            )
            dissolve_right_cells.append(
                {
                    "x": width - 48 + col * 12,
                    "y": 2 + row * 12,
                    "w": 12,
                    "h": 12,
                    "fill": secondary_main if (col + row) % 2 == 0 else secondary_deep,
                }
            )
    dissolve_left_scatter = [
        {"x": x, "y": y, "size": size, "opacity": opacity}
        for x, y, size, opacity in (
            (56, 7, 8, 0.85),
            (68, 10, 6, 0.7),
            (80, 5, 7, 0.55),
            (94, 11, 5, 0.45),
            (108, 8, 5, 0.3),
            (122, 12, 3, 0.2),
            (58, 17, 6, 0.7),
            (70, 18, 5, 0.55),
            (84, 16, 7, 0.4),
            (100, 15, 4, 0.25),
        )
    ]
    dissolve_right_scatter = [
        {"x": width - offset, "y": y, "size": size, "opacity": opacity}
        for offset, y, size, opacity in (
            (124, 12, 3, 0.2),
            (110, 8, 5, 0.3),
            (96, 11, 5, 0.45),
            (84, 5, 7, 0.55),
            (72, 10, 6, 0.7),
            (62, 7, 8, 0.85),
            (102, 15, 4, 0.25),
            (88, 18, 5, 0.4),
            (76, 16, 7, 0.55),
            (64, 17, 6, 0.7),
        )
    ]
    seam_y = height // 2
    seam_gap = 16
    seam_segment_edges = [0, 152, 168, 312, 328, 472, 488, 632, 648, width]
    seam_segments = [
        {"x1": seam_segment_edges[i], "x2": seam_segment_edges[i + 1], "y": seam_y}
        for i in range(0, len(seam_segment_edges), 2)
    ]
    seam_joints = [{"x": x, "y1": seam_y - 4, "y2": seam_y + 4} for x in seam_segment_edges[1:-1]]
    # Sigil divider (brutalist light default, 800x34): two ink rules with end
    # caps flanking a SOLID ink center block (the diamond is filled solid,
    # continuous with the block — no cutout/outline/gap), plus two accent spot
    # marks bracketing the block and an accent top cap on the block. Ink uses
    # accent_complement (=P), spots/cap use accent (=A) — both already in ctx.
    sigil_cx = width // 2
    sigil_block = 26
    sigil_block_x = sigil_cx - sigil_block // 2
    sigil_block_y = (height - sigil_block) // 2
    sigil_rule_h = 4
    sigil_rule_y = (height - sigil_rule_h) // 2
    sigil_rule_gap = 57  # block <-> rule gap houses the spot mark
    sigil_left_rule_w = sigil_block_x - sigil_rule_gap
    sigil_right_rule_x = sigil_block_x + sigil_block + sigil_rule_gap
    sigil_cap_w, sigil_cap_h = 6, 10
    sigil_cap_y = (height - sigil_cap_h) // 2
    sigil_spot_w, sigil_spot_h = 14, 6
    sigil_spot_y = (height - sigil_spot_h) // 2
    sigil_spot_offset = 53  # center distance, symmetric about sigil_cx
    ctx: dict[str, Any] = {
        "divider_variant": variant,
        "divider_w": width,
        "divider_h": height,
        "divider_cx": cx,
        "divider_cy": cy,
        "divider_pattern_x": 0,
        "divider_pattern_y": 0,
        "divider_pattern_w": 20,
        "divider_pattern_h": 20,
        "divider_dot_cx": 10,
        "divider_dot_cy": 10,
        "divider_dot_r": 0.5,
        "divider_rule_fade_stops": [
            _divider_stop("0%", "#000000", "0"),
            _divider_stop("20%", "#000000", "1"),
            _divider_stop("50%", "#000000", "1"),
            _divider_stop("80%", "#000000", "1"),
            _divider_stop("100%", "#000000", "0"),
        ],
        "divider_dot_color": "#000000",
        "divider_rainbow_stops": [
            _divider_stop("0%", "#ff0000"),
            _divider_stop("20%", "#0000ff"),
            _divider_stop("40%", "#ff8c00"),
            _divider_stop("60%", "#00fa9a"),
            _divider_stop("80%", "#4b0082"),
            _divider_stop("100%", "#ff0000"),
        ],
        "divider_escape_stops": [
            {
                "offset": "0%",
                "color": "#FF6B6B",
                "values": "#FF6B6B;#FF4444;#FF0000;#FF6B6B",
            },
            {
                "offset": "50%",
                "color": "#FFA500",
                "values": "#FFA500;#FF8C00;#FFD700;#FFA500",
            },
            {
                "offset": "100%",
                "color": "#FFFF00",
                "values": "#FFFF00;#FFD700;#FFFFFF;#FFFF00",
            },
        ],
        "divider_flux_stops": [
            _divider_stop("0%", "#3b82f6", "0"),
            _divider_stop("20%", "#3b82f6", "0.8"),
            _divider_stop("40%", "#8b5cf6", "1"),
            _divider_stop("50%", "#ec4899", "1"),
            _divider_stop("60%", "#f59e0b", "1"),
            _divider_stop("80%", "#10b981", "0.8"),
            _divider_stop("100%", "#10b981", "0"),
        ],
        "block_size": block_size,
        "block_rect_x": 0,
        "block_y": cy - block_half,
        "block_rule_y": cy - 2,
        "block_rule_x": 0,
        "block_rule_h": 4,
        "block_offset": int(width * 0.357),
        "block_spread": block_spread,
        "block_center_x": block_spread // 2,
        "block_center_rect_x": -30,
        "block_center_rect_y": -8,
        "block_center_rect_w": 60,
        "block_center_rect_h": 16,
        "block_symbol_x": 0,
        "block_symbol_y": 4,
        "block_gold_y": cy - 4,
        "block_gold_size": 8,
        "block_gold_left_x": int(width * 0.214),
        "block_gold_right_x": int(width * 0.774),
        "block_label_x": cx,
        "block_label_y": cy + 25,
        "block_red": "#DC143C",
        "block_blue": "#0047AB",
        "block_gold": "#FFD700",
        "block_white": "#FFFFFF",
        "block_black": "#000000",
        "block_label_color": "#999999",
        "current_path": (
            f"M0,{cy} C{current_points['p1']},{cy - current_amp} "
            f"{current_points['p2']},{cy + current_amp} {current_points['p3']},{cy} "
            f"C{current_points['p4']},{cy - current_amp} {current_points['p5']},{cy + current_amp} "
            f"{current_points['p6']},{cy} C{current_points['p7']},{cy - current_amp} {width},{cy} {width},{cy}"
        ),
        "takeoff_trajectory_path": f"M0,{cy} Q{width // 4},{cy - takeoff_dip} {takeoff_rx},{cy} T{width},{cy}",
        "takeoff_motion_path": f"M-{takeoff_rx},0 Q-{width // 4},-{takeoff_dip} 0,0 T{takeoff_rx},0",
        "takeoff_warning_x": 0,
        "takeoff_warning_y": cy - 5,
        "takeoff_warning_h": 10,
        "takeoff_rocket_x": takeoff_rx,
        "takeoff_rocket_y": cy,
        "takeoff_body_x": -10,
        "takeoff_body_y": 0,
        "takeoff_body_w": 20,
        "takeoff_body_h": 15,
        "takeoff_left_booster_cx": -15,
        "takeoff_right_booster_cx": 15,
        "takeoff_booster_cy": 10,
        "takeoff_booster_r": 2,
        "takeoff_warning_label_x": width - 50,
        "takeoff_warning_label_y": int(height * 0.2),
        "takeoff_trajectory_color": "#FF4444",
        "takeoff_nose_color": "#FF3333",
        "takeoff_body_color": "#CC0000",
        "takeoff_booster_color": "#FF0000",
        "aura_cx": cx,
        "aura_cy": cy,
        "aura_rx": aura_rx,
        "aura_ry": 4,
        "filament_x": filament_x,
        "filament_y": cy - 1,
        "filament_w": int(width * 0.9),
        "filament_h": 1.5,
        "filament_rx": 1,
        "dissolve_line_x1": 48,
        "dissolve_line_y": 14,
        "dissolve_line_x2": width - 48,
        "dissolve_left_cells": dissolve_left_cells,
        "dissolve_right_cells": dissolve_right_cells,
        "dissolve_left_scatter": dissolve_left_scatter,
        "dissolve_right_scatter": dissolve_right_scatter,
        "dissolve_primary_main": primary_main,
        "dissolve_secondary_main": secondary_main,
        "zeropoint_line_x": 0,
        "zeropoint_line_h": 2,
        "zeropoint_line_y": cy - 1,
        "zeropoint_outer_r": 4,
        "zeropoint_inner_r": 2,
        "zeropoint_label_x": cx,
        "zeropoint_label_y": cy + 14,
        "zeropoint_label_color": "#666666",
        "band_rect_x": 0,
        "band_rect_y": 6,
        "band_rect_h": 4,
        "band_rect_rx": 0.8,
        "seam_segments": seam_segments,
        "seam_joints": seam_joints,
        "seam_gap": seam_gap,
        "sigil_left_rule": {"x": 0, "y": sigil_rule_y, "w": sigil_left_rule_w, "h": sigil_rule_h},
        "sigil_right_rule": {
            "x": sigil_right_rule_x,
            "y": sigil_rule_y,
            "w": width - sigil_right_rule_x,
            "h": sigil_rule_h,
        },
        "sigil_left_cap": {"x": 0, "y": sigil_cap_y, "w": sigil_cap_w, "h": sigil_cap_h},
        "sigil_right_cap": {"x": width - sigil_cap_w, "y": sigil_cap_y, "w": sigil_cap_w, "h": sigil_cap_h},
        "sigil_block": {"x": sigil_block_x, "y": sigil_block_y, "w": sigil_block, "h": sigil_block},
        "sigil_block_cap": {"x": sigil_block_x, "y": sigil_block_y, "w": sigil_block, "h": 4},
        "sigil_spots": [
            {
                "x": sigil_cx - sigil_spot_offset - sigil_spot_w // 2,
                "y": sigil_spot_y,
                "w": sigil_spot_w,
                "h": sigil_spot_h,
            },
            {
                "x": sigil_cx + sigil_spot_offset - sigil_spot_w // 2,
                "y": sigil_spot_y,
                "w": sigil_spot_w,
                "h": sigil_spot_h,
            },
        ],
    }
    return ctx


def resolve_divider(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve divider dimensions + template selection.

    v0.2.19 split:
      - 5 editorial generics (block/current/takeoff/void/zeropoint) + automata's
        dissolve render via the legacy multi-branch template `frames/divider.svg.j2`.
      - Genome-themed dividers (band, seam) live in `frames/divider/<genome>-<slug>.svg.j2`
        and are dispatched via slug interpolation.
      - Validation: the (slug, genome) pairing must be in `genome.dividers` for
        compositor-route requests. Editorial generics bypass this check.
    """
    _editorial_generics = {"block", "current", "takeoff", "void", "zeropoint"}
    _all_known_variants = _editorial_generics | {"dissolve", "band", "seam", "sigil"}
    variant: str
    if spec.divider_variant in _all_known_variants:
        variant = spec.divider_variant
    elif genome.get("dividers"):
        # Genome-themed default: the substrate picks the family divider.
        # Brutalist light defaults to sigil (ink rules + solid center block);
        # dark keeps seam (concrete expansion-joint). Both stay explicitly
        # selectable via ?divider=seam|sigil.
        _allowed = list(genome.get("dividers") or [])
        if genome.get("substrate_kind") == "light" and "sigil" in _allowed:
            variant = "sigil"
        elif "seam" in _allowed:
            variant = "seam"
        else:
            variant = _allowed[0]
    else:
        variant = "zeropoint"

    # (slug, genome) pairing validator — only enforced for non-editorial slugs
    # (editorial generics are intentionally genome-agnostic, served via /a/inneraura/).
    if variant not in _editorial_generics:
        allowed = list(genome.get("dividers") or [])
        if variant not in allowed:
            msg = f"divider_variant '{variant}' not in genome.dividers {allowed}"
            raise ValueError(msg)

    variant_dims: dict[str, tuple[int, int]] = {
        "block": (700, 80),
        "current": (700, 40),
        "takeoff": (700, 100),
        "void": (700, 40),
        "zeropoint": (700, 30),
        "dissolve": (800, 28),
        "band": (800, 22),
        "seam": (800, 16),
        "sigil": (800, 34),
    }
    w, h = variant_dims.get(variant, (700, 30))

    # Slug-interpolation template dispatch: genome-themed dividers live at
    # frames/divider/<genome>-<slug>.svg.j2. Falls back to the multi-branch
    # legacy template (handles editorial generics + dissolve).
    from hyperweave.render.templates import template_exists  # late import: avoid cycle

    genome_specific = f"frames/divider/{spec.genome_id}-{variant}.svg.j2"
    template = genome_specific if template_exists(genome_specific) else "frames/divider.svg.j2"

    cellular_palette = _kw.get("cellular_palette") or {}
    ctx: dict[str, Any] = {
        "divider_label": spec.value or "",
        "variant": spec.variant or "",
        # Pass through chrome chromosomes so chrome-band template's envelope_stops
        # for-loop has data. brutalist-seam needs accent + accent_complement (was
        # accent_signal pre-v0.3.3 — see brutalist-seam.svg.j2 header for the
        # chromatic-register rationale). zeropoint (editorial default) needs
        # accent + accent_complement + surface_deep to drive its variant-aware
        # aurora gradient + nexus beacon without hardcoded chromatic literals.
        # accent_signal stays in context for backward-compat — currently no
        # divider template reads it but other surfaces may grow into the field.
        "envelope_stops": genome.get("envelope_stops", []),
        "accent": genome.get("accent", ""),
        "accent_complement": genome.get("accent_complement", ""),
        "accent_signal": genome.get("accent_signal", ""),
        "surface_deep": genome.get("surface_2", ""),
    }
    ctx.update(
        _divider_geometry_context(
            variant=variant,
            width=w,
            height=h,
            cellular_palette=cellular_palette,
        )
    )
    # Profile visual context now injected centrally by the dispatcher.

    return {
        "width": w,
        "height": h,
        "template": template,
        "context": ctx,
    }


def resolve_marquee(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    paradigm_spec: Any = None,
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve marquee-horizontal dimensions and scroll content.

    Single variant after v0.2.14: 800x40 LIVE ticker. The genome's family
    palette (cellular: paired primary/secondary tones) and the paradigm's
    marquee config (separator glyph, live-block suppression) drive aesthetic
    dispatch inside ``_resolve_horizontal``. cellular_palette flows in as a
    kwarg from the dispatcher so paired-mode tspan alternation reads the
    structured tone dict instead of branching on raw genome fields.
    """
    cellular_palette = _kw.get("cellular_palette") or {}
    primary_tone = cellular_palette.get("primary") or {}
    secondary_tone = cellular_palette.get("secondary") or {}

    # ``_resolve_horizontal`` only needs signal_hex/surface_hex as hex-resolved
    # carriers for ``<stop>`` attributes (var() is unreliable inside SVG stops).
    # Bifamily cellular marquees additionally carry primary/secondary info
    # hexes so ``_resolve_horizontal`` can generate tspan-alternation
    # scroll_items. is_paired tells the downstream code whether to alternate.
    #
    # v0.3.0 cellular marquee refresh — primary_info_accent + primary_mid_accent
    # surface to the template via chrome_ctx merge. info_accent fills scroll
    # text (Orbitron 11px 700), mid_accent fills the bullet separators and the
    # top/bottom hairlines drawn by cellular-overlay.j2. The marquee is
    # monofamily for paired variants too — the 0.5px hairlines at 0.2 opacity
    # would not perceptually communicate a bifamily split, so paired-variant
    # signature is reserved for stat card / chart / icon where the chromatic
    # bandwidth is larger.
    primary_info_accent = primary_tone.get("info_accent", "")
    primary_mid_accent = primary_tone.get("mid_accent", "")
    _is_light_substrate = genome.get("substrate_kind") == "light"
    _ink_hex = genome.get("ink", genome.get("ink_primary", "#0A0A0A"))
    _surface_hex = genome.get("surface_0", genome.get("surface", "#0A0A0A"))
    _accent_hex = genome.get("accent", "#10B981")
    chrome_ctx: dict[str, Any] = {
        "signal_hex": _accent_hex,
        "surface_hex": _surface_hex,
        # v0.3.13 light-scholar cohesion: on light substrates the bookend caps
        # carry INK MASS (not paper), with a PAPER-knockout liveness cube/seal
        # and an INK frame perimeter (structure); accent stays a spot (cap
        # rails + bottom foundation rail). Dark substrates keep surface caps +
        # accent cube/perimeter, so these resolve byte-equal there. Substrate-
        # aware in the resolver (mirrors the glyph_fill routing at ~4300) so the
        # shared brutalist overlay needs no per-substrate template split — the
        # light/dark elements are identical in structure, only their fill
        # differs (unlike the icon, which needed a true structural split).
        "cap_fill_hex": _ink_hex if _is_light_substrate else _surface_hex,
        "cube_fill_hex": _surface_hex if _is_light_substrate else _accent_hex,
        "marquee_perimeter_hex": _ink_hex if _is_light_substrate else _accent_hex,
        "primary_seam_mid": primary_tone.get("seam_mid", ""),
        "secondary_seam_mid": secondary_tone.get("seam_mid", ""),
        "primary_info_accent": primary_info_accent,
        "primary_mid_accent": primary_mid_accent,
        "is_paired": cellular_palette.get("is_paired", False),
        # Genome fonts for genome-aware measurement (v0.3.12): a marquee
        # font_family of var(--dna-font-display) must measure with the GENOME's
        # display face (brutalist JetBrains Mono, chrome/automata Orbitron),
        # not a hardcoded Orbitron — else measured≠rendered (the cram bug).
        "genome_display_font": genome.get("font_display", ""),
        "genome_mono_font": genome.get("font_mono", ""),
    }

    # Paradigm-declared marquee config — separator glyph, palette, live-block
    # suppression. Routed through ParadigmMarqueeConfig (defaults match the
    # historic brutalist/chrome behavior, so paradigms that don't declare
    # marquee config still render correctly).
    marquee_cfg = paradigm_spec.marquee if paradigm_spec is not None else None

    result = _resolve_horizontal(spec, chrome_ctx, profile, marquee_cfg)

    # Cellular variant override: when the active variant declares a mid_accent,
    # use it for separator_color so each variant's accent flows through bullet
    # separators (rather than the static paradigm-config default which is a
    # single hex frozen at amber's #B89800). The paradigm fallback is preserved
    # for non-cellular paradigms.
    if primary_mid_accent and "context" in result:
        result["context"]["separator_color"] = primary_mid_accent

    # v0.3.12 — state cascade fields so the marquee's included
    # state-signal-cascade.j2 binds data-hw-status → var(--hw-state-value) from
    # each genome's state_* hexes (used by stateful activity cells). Genome
    # state_* fields are unchanged from badges/strips — marquee state colors
    # are approximate vs the prototype by design (exact per-variant harmony is
    # schema-blocked and deferred).
    if "context" in result:
        for status in ("passing", "warning", "critical", "building", "offline"):
            result["context"][f"state_{status}_core"] = genome.get(f"state_{status}_core", "")
            result["context"][f"state_{status}_bright"] = genome.get(f"state_{status}_bright", "")

    return result


# Uniform marquee reading rate (px/s) — chrome's prototype rate
# (loop_distance 892 ÷ duration 30.0 = 29.7), applied to EVERY genome so a
# brutalist module stream and a chrome ribbon scroll at the same calm reading
# pace. ``scroll_dur = scroll_distance ÷ CHROME_PX_PER_SEC``. Prototype `dur`
# literals (brutalist 33s, automata 23.5s) are NOT copied.
CHROME_PX_PER_SEC: float = 29.7


def _first_font(font_stack_css: str) -> str:
    """Return the first concrete component of a CSS font stack.

    ``"'Barlow Condensed','Oswald',sans-serif"`` → ``"Barlow Condensed"``.
    Empty string in → empty string out (caller supplies the fallback).
    """
    s = (font_stack_css or "").strip()
    if not s:
        return ""
    return s.split(",")[0].strip().strip("'\"")


def _resolve_font_for_measurement(
    font_family_css: str,
    *,
    genome_display_font: str = "",
    genome_mono_font: str = "",
) -> str:
    """Map a CSS font-family expression to a registry-resolvable font name.

    The browser resolves ``var(--dna-font-mono, ui-monospace, monospace)`` at
    runtime to the actual font (via the genome's CSS bridge), but
    :func:`hyperweave.core.text.measure_text` can't see CSS variables. If a
    paradigm doesn't declare an explicit ``font_family`` in its marquee
    config, the resolver falls back to the profile's CSS-var-bearing default,
    measure_text fails to resolve it, and silently uses Inter metrics — which
    are ~20-30% narrower than monospace fonts. Layout positions then come out
    too tight, producing visible bullet-vs-text overlap (the "cram" bug).

    This helper closes that gap. It detects ``var(--dna-font-X, ...)``
    expressions and maps them to the actual font the browser will resolve to.
    v0.3.12: GENOME-AWARE — ``--dna-font-display`` resolves to the GENOME's
    declared display font (``genome_display_font``), not a hardcoded
    ``Orbitron``. Brutalist's display is JetBrains Mono, chrome/automata's is
    Orbitron; measuring with the wrong face reintroduces the cram bug. The
    hardcoded names remain only as the no-genome-supplied fallback.

      ``var(--dna-font-display, ...)`` → genome_display_font OR ``Orbitron``
      ``var(--dna-font-mono, ...)``    → genome_mono_font    OR ``JetBrains Mono``
      anything else                    → first non-var fallback OR ``Inter``

    Non-var inputs pass through unchanged (first stack component). Called at
    the boundary inside the marquee layout helpers so every layout call
    benefits.
    """
    s = (font_family_css or "").strip()
    if not s:
        return "Inter"
    if not s.startswith("var("):
        # Already a real font stack — return first comma-separated component
        # for measure_text (which handles the rest of the stack lookup).
        return s.split(",")[0].strip().strip("'\"")
    # var(--name, fallback...) — map by var name first, genome font preferred.
    if "--dna-font-display" in s:
        return _first_font(genome_display_font) or "Orbitron"
    if "--dna-font-mono" in s:
        return _first_font(genome_mono_font) or "JetBrains Mono"
    # Generic var() with a non-DNA name — extract the CSS fallback list.
    open_paren = s.find("(")
    close_paren = s.rfind(")")
    if open_paren < 0 or close_paren <= open_paren:
        return "Inter"
    inner = s[open_paren + 1 : close_paren]
    parts = inner.split(",", 1)
    if len(parts) < 2:
        return "Inter"
    fallback = parts[1].strip()
    first = fallback.split(",")[0].strip().strip("'\"")
    # Map generic CSS keywords to the closest registered font.
    if first in ("ui-monospace", "monospace"):
        return "JetBrains Mono"
    if first in ("system-ui", "sans-serif", "-apple-system", "BlinkMacSystemFont"):
        return "Inter"
    return first or "Inter"


def _parse_letter_spacing_px(letter_spacing: str, font_size: float) -> float:
    """Parse a CSS ``letter-spacing`` value to pixels.

    Accepts ``"0.18em"``, ``"3.4px"``, or a bare number (assumed px). Empty
    or unparseable strings return 0. Used by the marquee layout helper so the
    same em string the template renders to CSS is also fed into measure_text
    for content-width computation — keeping browser layout and resolver
    layout in lockstep.
    """
    s = (letter_spacing or "").strip()
    if not s:
        return 0.0
    if s.endswith("em"):
        try:
            return float(s[:-2]) * font_size
        except ValueError:
            return 0.0
    if s.endswith("px"):
        try:
            return float(s[:-2])
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


# Intra-cell tspan-flow gaps, single-sourced so the resolver's reserved width
# always equals the template's rendered ``dx`` — a mismatch would desync the
# seamless-loop period. Used for width accounting in _layout_marquee_* AND
# emitted to the template context (item-ribbon/item-module render the dx).
_MARQUEE_LABEL_VALUE_GAP = 8  # label tspan -> value tspan (ribbon)
_MARQUEE_WINDOW_GAP = 4  # value -> download-window subtitle tspan (ribbon + module)


def _layout_marquee_items(
    items: list[dict[str, Any]],
    *,
    font_family: str,
    font_size: int,
    font_weight: int,
    letter_spacing_px: float,
    item_gap: int,
    label_value_gap: int,
    start_x: int,
    separator_kind: str,
    separator_size: int,
    separator_glyph: str,
    label_font_size: int = 0,
    genome_display_font: str = "",
    genome_mono_font: str = "",
) -> tuple[list[dict[str, Any]], int]:
    """Lay out marquee scroll items at absolute x positions.

    Each input item is ``{role, label, value, value_color, label_color,
    font_weight, gradient_value}``. Output is a flat sequence interleaving
    text items and separators, each with an explicit ``x`` so the template
    emits absolute positions (no relative ``dx`` math, no font-metric drift
    between resolver math and template render).

    Returns ``(laid_out, content_end_x)``. A separator is emitted AFTER EVERY
    item (including the last). This is critical for seamless looping — the
    boundary between Set-A's trailing separator and Set-B's first item then
    has the same ``item_gap`` as every within-set separator-to-item gap, so
    SMIL's frame-boundary jump from ``translate(-sd, 0)`` back to
    ``translate(0, 0)`` is visually invisible. ``content_end_x`` is the x
    past that final ``[item_gap, separator, item_gap]`` block, so the caller
    sets ``scroll_distance = content_end_x - start_x`` for a perfect
    period-equals-period seamless cycle.

    Separator handling:
      * ``separator_kind == "glyph"``: emit ``{type: "separator-glyph", x,
        text: separator_glyph}``; advance x by glyph width + item_gap.
      * ``separator_kind == "rect"``: emit ``{type: "separator-rect", x}``;
        advance x by separator_size + item_gap. The template renders a
        ``<rect width=size height=size>`` filled with separator_color.
    """
    from hyperweave.core.text import measure_text

    # Architectural fix (v0.2.16-fix2): resolve CSS var() expressions to the
    # actual registry-resolvable font name BEFORE measurement. Without this,
    # paradigms that fall through to the profile's var(--dna-font-mono) default
    # measure with Inter (silent fallback), then render with JetBrains Mono at
    # runtime — the 20-30% width mismatch causes visible bullet/text overlap.
    measurement_font = _resolve_font_for_measurement(
        font_family, genome_display_font=genome_display_font, genome_mono_font=genome_mono_font
    )

    laid: list[dict[str, Any]] = []
    x = float(start_x)

    def _w(text: str, size: int) -> float:
        # Wrap measure_text so call-sites stay short. font_weight is a single
        # value across the whole marquee (paradigm declares it); per-item
        # font-weight overrides are applied via the rendered tspan, not via
        # measurement (which doesn't change appreciably between 700 and 900).
        # The label is measured at label_font_size, the value at font_size, so a
        # smaller label (chrome 6px / automata 9px) reserves its true width.
        return measure_text(
            text,
            font_family=measurement_font,
            font_size=float(size),
            font_weight=font_weight,
            letter_spacing_em=letter_spacing_px / float(font_size) if font_size else 0.0,
        )

    label_size = label_font_size or font_size
    for item in items:
        label = item.get("label", "")
        value = item["value"]
        # Each item — whether single-tspan (text role) or label+value pair —
        # gets ONE absolute x. The template emits child tspans inside a single
        # <text> element at this x; sibling tspans flow naturally with dx.
        laid.append({"type": "text", "x": int(x), "item": item})

        # Width contribution: label + (gap + value) when label present, else value alone.
        if label:
            x += _w(label, label_size) + label_value_gap + _w(value, font_size)
        else:
            x += _w(value, font_size)
        # Download-window subtitle trails the value as a small dim tspan
        # (item-ribbon.j2 renders it at label_size with a 4px dx). Reserve its
        # measured width so the period label never crams the separator.
        window = str(item.get("window", "") or "")
        if window:
            x += _MARQUEE_WINDOW_GAP + _w(window, label_size)
        # Inter-item breathing room (before separator).
        x += item_gap

        # Separator after EVERY item (including last). The trailing separator
        # is what makes the loop boundary feel like just another inter-item
        # rhythm beat — Set-B's first item then sits one item_gap past Set-A's
        # trailing separator, which is exactly the within-set sep-to-item gap.
        laid.append({"type": "separator-" + separator_kind, "x": int(x)})
        if separator_kind == "rect":
            x += separator_size + item_gap
        else:
            # Glyph separators render at the LABEL size (item-ribbon.j2 uses
            # ``lfs``), not the value size — the bone prototype's ▪ is 10px
            # against a 16px value. Measure at label_size so the advance matches
            # the rendered width (a 16px-measured ▪ would over-reserve, drifting
            # the next cell right and breaking the seamless loop period).
            x += _w(separator_glyph, label_size) + item_gap

    return laid, int(x)


_CATEGORY_RANK: dict[str, int] = {"volume": 0, "activity": 1, "identity": 2}


def _annotate_marquee_items(structured: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tag each scroll item with category / per-cell state / hero, then group.

    Genome-neutral. Category comes from ``marquee_classes.yaml`` keyed by the
    token-grammar metric (live tokens) or the lowercased label (kv tokens).
    Per-cell state reuses ``core.state.infer_state`` — the exact classifier
    strips use — gated by the ``badge_modes.yaml`` stateful allowlist, applied
    ONLY to activity cells. Items are stable-sorted volume→activity→identity
    (order only), and the first volume cell (kv/live, not raw text) becomes the
    hero. No color is assigned here — that's a role→CSS-var decision in
    ``_resolve_horizontal``; this keeps classification genome-neutral and the
    color path on the per-genome cascade bridge.
    """
    from hyperweave.compose.layout import normalize_title
    from hyperweave.config.loader import load_badge_modes, load_marquee_classes
    from hyperweave.core.state import infer_state

    metric_to_category, default_category = load_marquee_classes()
    allowlist = load_badge_modes()

    annotated: list[dict[str, Any]] = []
    for item in structured:
        metric = str(item.get("metric") or "").strip().lower()
        label = str(item.get("label") or "").strip().lower()
        key = metric or label
        category = metric_to_category.get(key, default_category)

        # Per-cell state: activity cells only, gated by the stateful allowlist.
        state = ""
        item_label = str(item.get("label") or "")
        if category == "activity" and item_label and normalize_title(item_label) in allowlist:
            inferred = infer_state(item_label, str(item.get("value", "")))
            if inferred != "active":
                state = inferred

        annotated.append({**item, "category": category, "state": state})

    # Stable sort by category rank — governs ORDER only (volume → activity →
    # identity). Within a category, input order is preserved.
    annotated.sort(key=lambda it: _CATEGORY_RANK.get(str(it.get("category")), 0))

    # Hero = first volume cell carrying real data (kv/live), brightest-ink
    # treatment downstream. Raw-text items are not hero-eligible.
    hero_assigned = False
    for it in annotated:
        is_hero = not hero_assigned and it.get("category") == "volume" and it.get("role") != "text"
        it["is_hero"] = is_hero
        if is_hero:
            hero_assigned = True
    return annotated


def _layout_marquee_modules(
    items: list[dict[str, Any]],
    *,
    label_font: str,
    label_font_size: int,
    label_letter_spacing_px: float,
    value_font: str,
    value_font_size: int,
    hero_font_size: int,
    value_weight: int,
    value_letter_spacing_px: float,
    inset: int,
    start_x: int,
    min_width: int,
    divider_w: int,
) -> tuple[list[dict[str, Any]], int, int]:
    """Lay out items as fixed-width cast MODULES (brutalist instrument panel).

    Each module is a uniform-width cell: a small mono label stacked over a bold
    condensed value (both left-aligned at ``module_left + inset``), bounded by a
    full-height divider at the module's right boundary. The uniform module pitch
    is computed from MEASURED content — ``max(widest label, widest value) +
    2*inset`` clamped to ``min_width`` — so the prototype's 136px is reproduced
    for its content but the layout adapts to any token set (the cram-proof
    cast-repetition principle: short values just leave left-aligned air inside
    their module). Returns ``(laid, content_end_x, module_width)``.
    """
    from hyperweave.core.text import measure_text

    widest = 0.0
    for it in items:
        label = str(it.get("label", "") or "")
        value = str(it.get("value", ""))
        vfs = hero_font_size if (it.get("is_hero") and hero_font_size) else value_font_size
        lw = measure_text(
            label,
            font_family=label_font,
            font_size=float(label_font_size),
            font_weight=600,
            letter_spacing_em=label_letter_spacing_px / label_font_size if label_font_size else 0.0,
        )
        vw = measure_text(
            value,
            font_family=value_font,
            font_size=float(vfs),
            font_weight=value_weight,
            letter_spacing_em=value_letter_spacing_px / value_font_size if value_font_size else 0.0,
        )
        # Download-window subtitle trails the value (item-module.j2 renders it at
        # label_font_size with a 4px dx — the same gap the ribbon uses, and in
        # the label font). Fold its width into the value-row width so the module
        # pitch widens to hold it — the cram-proof clamp covers it.
        window = str(it.get("window", "") or "")
        if window:
            vw += _MARQUEE_WINDOW_GAP + measure_text(
                window,
                font_family=label_font,
                font_size=float(label_font_size),
                font_weight=600,
                letter_spacing_em=label_letter_spacing_px / label_font_size if label_font_size else 0.0,
            )
        widest = max(widest, lw, vw)

    import math

    module_width = max(math.ceil(widest) + 2 * inset, min_width)

    laid: list[dict[str, Any]] = []
    x = start_x
    for it in items:
        module_left = x
        vfs = hero_font_size if (it.get("is_hero") and hero_font_size) else value_font_size
        laid.append(
            {
                "type": "module",
                "x": module_left + inset,
                "divider_x": module_left + module_width - divider_w,
                "label": it.get("label", ""),
                "value": it.get("value", ""),
                "value_color": it.get("value_color", ""),
                "label_color": it.get("label_color", ""),
                "data_hw_status": it.get("data_hw_status", ""),
                "value_font_size": vfs,
                "font_weight": it.get("font_weight", ""),
                "is_hero": it.get("is_hero", False),
                "window": str(it.get("window", "") or ""),
            }
        )
        x += module_width
    return laid, x, module_width


def _resolve_horizontal(
    spec: ComposeSpec,
    chrome_ctx: dict[str, Any],
    profile: dict[str, Any] | None = None,
    marquee_cfg: Any = None,
) -> dict[str, Any]:
    """Horizontal scrolling marquee: brand items scrolling left.

    Two input modes (mutually exclusive — ``data_tokens`` wins when both
    are set):

    1. **Data-token mode** (``spec.data_tokens`` non-empty): each
       :class:`hyperweave.serve.data_tokens.ResolvedToken` becomes a
       scroll item. ``text`` tokens render single-tspan; ``kv`` / ``live``
       tokens render label+value tspans sharing one absolute x.
    2. **Raw text mode** (``spec.title`` only): ``title`` is split on
       ``|`` (or ``·``) into single-tspan items.

    Layout (v0.2.16): items are laid out at ABSOLUTE x positions computed
    from font metrics via :func:`_layout_marquee_items`. ``scroll_distance``
    equals one full content cycle (``content_end_x - start_x``, where
    content_end_x already includes a trailing separator after the last item),
    floored at viewport width for short content. The trailing-separator-after-
    every-item layout makes the boundary spacing identical to the within-set
    sep-to-item rhythm, so SMIL's frame-boundary jump from translate(-sd, 0)
    back to translate(0, 0) is visually invisible — no perceptible "lag" or
    "restart" feel. The LIVE label panel was removed in v0.2.16 — paradigm
    content fills the entire frame.

    Paradigm config (from ``marquee_cfg``) drives:
      * ``width``/``height`` — viewport dimensions (chrome 1040x56,
        brutalist 720x32, default 800x40).
      * ``font_size``/``font_weight``/``letter_spacing``/``font_family`` —
        scroll-text typography. Same values feed measure_text and the
        rendered ``<text>`` attributes.
      * ``separator_kind`` (``glyph``|``rect``) and ``separator_size`` /
        ``separator_glyph`` / ``separator_color`` — between-item separator
        rendering.
      * ``text_fill_mode`` (``per_item``|``gradient``|``cycle``) and
        ``text_fill_gradient_id`` / ``text_fill_cycle`` — per-item color
        assignment. ``per_item`` keeps the legacy bifamily/ink alternation;
        ``gradient`` applies one gradient URL to every item; ``cycle``
        rotates through a hex list.
    """
    _prof = profile or {}

    # Marquee dimensions, typography, separator config — paradigm-driven via
    # ParadigmMarqueeConfig. Defaults (800x40, 13/.5 typography, ■ glyph)
    # preserve historic behavior for paradigms that don't declare marquee.
    if marquee_cfg is not None:
        width = int(marquee_cfg.width) or 800
        height = int(marquee_cfg.height) or 40
        font_size = int(marquee_cfg.font_size) or 13
        label_font_size = int(marquee_cfg.label_font_size) or font_size
        font_weight_str = marquee_cfg.font_weight or ""
        letter_spacing_css = marquee_cfg.letter_spacing or ".5"
        font_family = marquee_cfg.font_family or _prof.get(
            "marquee_font_family", "var(--dna-font-mono, ui-monospace, monospace)"
        )
        separator_kind = marquee_cfg.separator_kind or "glyph"
        separator_size = int(marquee_cfg.separator_size) or 6
        separator_glyph = marquee_cfg.separator_glyph or "■"
        separator_color = marquee_cfg.separator_color or _prof.get("marquee_separator_color", "var(--dna-border)")
        separator_fill_override = marquee_cfg.separator_fill or ""
        text_fill_mode = marquee_cfg.text_fill_mode or "per_item"
        text_fill_gradient_id = marquee_cfg.text_fill_gradient_id or ""
        clip_inset_left = int(marquee_cfg.clip_inset_left)
        clip_inset_right = int(marquee_cfg.clip_inset_right)
        clip_inset_top = int(marquee_cfg.clip_inset_top)
        clip_inset_bottom = int(marquee_cfg.clip_inset_bottom)
        clip_rx = float(marquee_cfg.clip_rx)
        # v0.3.12 — scroll-item layout dispatch (ribbon | module) + module geom.
        item_layout = marquee_cfg.item_layout or "ribbon"
        hero_font_size = int(marquee_cfg.hero_font_size)
        module_min_width = int(marquee_cfg.module_min_width)
        module_text_inset = int(marquee_cfg.module_text_inset)
        module_label_y = int(marquee_cfg.module_label_y)
        module_value_y = int(marquee_cfg.module_value_y)
        module_label_font_size = int(marquee_cfg.module_label_font_size)
        module_label_font_family = marquee_cfg.module_label_font_family or font_family
        module_label_letter_spacing = marquee_cfg.module_label_letter_spacing or "0"
        module_value_font_family = marquee_cfg.module_value_font_family or font_family
        module_divider_w = int(marquee_cfg.module_divider_w)
        module_divider_y = int(marquee_cfg.module_divider_y)
        module_divider_h = int(marquee_cfg.module_divider_h)
    else:
        width, height = 800, 40
        font_size = 13
        label_font_size = 13
        font_weight_str = ""
        letter_spacing_css = ".5"
        font_family = _prof.get("marquee_font_family", "var(--dna-font-mono, ui-monospace, monospace)")
        separator_kind = "glyph"
        separator_size = 6
        separator_glyph = _prof.get("marquee_separator", "■")
        separator_color = _prof.get("marquee_separator_color", "var(--dna-border)")
        separator_fill_override = ""
        text_fill_mode = "per_item"
        text_fill_gradient_id = ""
        clip_inset_left = clip_inset_right = clip_inset_top = clip_inset_bottom = 0
        clip_rx = 0.0
        item_layout = "ribbon"
        hero_font_size = 0
        module_min_width = 0
        module_text_inset = 16
        module_label_y = 14
        module_value_y = 35
        module_label_font_size = 8
        module_label_font_family = font_family
        module_label_letter_spacing = "0"
        module_value_font_family = font_family
        module_divider_w = 2
        module_divider_y = 6
        module_divider_h = 32

    # Genome fonts for measurement (genome-aware font resolution, v0.3.12).
    genome_display_font = chrome_ctx.get("genome_display_font", "")
    genome_mono_font = chrome_ctx.get("genome_mono_font", "")

    # Item ingestion: data-tokens preferred, title fallback.
    if spec.data_tokens:
        from hyperweave.serve.data_tokens import format_for_marquee

        formatted = format_for_marquee(spec.data_tokens)
        structured = [
            {
                "role": item["role"],
                "label": item["label"],
                "value": item["raw_value"] or item["text"],
                "metric": item.get("metric", ""),
                "window": item.get("window", ""),
            }
            for item in formatted
            if item.get("text")
        ]
        if not structured:
            structured = [{"role": "text", "label": "", "value": "HYPERWEAVE", "metric": ""}]
    else:
        items_text = spec.title or ""
        raw_items = [s.strip() for s in items_text.replace("·", "|").split("|") if s.strip()]
        if not raw_items:
            raw_items = [items_text] if items_text else ["HYPERWEAVE"]
        structured = [{"role": "text", "label": "", "value": t, "metric": ""} for t in raw_items]

    # v0.3.12 — auto-group (volume→activity→identity ORDER) + per-cell state +
    # role-based hero. Genome-neutral classification; color comes from the
    # cascade bridge below.
    structured = _annotate_marquee_items(structured)

    # Content-aware layout (v0.3.12-fix). The module/stacked grammar exists to
    # stack a LABEL over a VALUE — it only makes sense for DATA cells (kv/live
    # label+value pairs). A free-text marquee ("HYPERWEAVE | LIVING ARTIFACTS")
    # has no label to stack, so forcing it into uniform module cells produced
    # the oversized, unevenly-spaced cells. When no item carries a label, fall
    # back to the inline ribbon for every genome — text scrolls as a clean flow.
    # Genomes already on ribbon (automata) are unaffected.
    if item_layout == "module" and not any(str(it.get("label") or "") for it in structured):
        item_layout = "ribbon"

    # Role-based per-item coloring (v0.3.12). Category + state + hero drive the
    # value color through the genome's cascade bridge — never a per-paradigm hex
    # pick, never a `paradigm ==` branch. Single-channel: only activity cells
    # carry data-hw-status; volume/identity get role color only.
    #   hero (first volume) → chrome-text gradient if the paradigm declares one,
    #                         else brightest ink (rendered at hero_font_size)
    #   volume              → brightest ink (var(--dna-ink-primary))
    #   activity (stateful) → var(--hw-state-value) + data-hw-status="<state>"
    #   identity            → muted ink (var(--dna-ink-muted))
    measure_weight = int(font_weight_str) if font_weight_str.isdigit() else 700
    item_weight = font_weight_str or "700"

    items_for_layout: list[dict[str, Any]] = []
    for item in structured:
        category = item.get("category", "volume")
        state = item.get("state", "")
        is_hero = bool(item.get("is_hero", False))
        data_hw_status = state if (category == "activity" and state) else ""

        if is_hero and text_fill_gradient_id:
            value_color = ""  # gradient sentinel — template emits url(#uid-{id})
        elif data_hw_status:
            value_color = "var(--hw-state-value)"
        elif category == "identity":
            value_color = "var(--dna-ink-muted)"
        else:  # volume / hero-without-gradient
            value_color = "var(--dna-ink-primary)"

        items_for_layout.append(
            {
                "role": item["role"],
                "label": item["label"],
                "value": item["value"],
                "value_color": value_color,
                "label_color": "var(--dna-ink-muted)",
                "font_weight": item_weight,
                "data_hw_status": data_hw_status,
                "is_hero": is_hero,
                # Download-window subtitle ("ALL-TIME" / "30D" / "7D" / "90D").
                # Rendered as a dim trailing tspan after the value; both layout
                # engines reserve its measured width so the period label never
                # crams the next cell.
                "window": str(item.get("window", "") or ""),
            }
        )

    import math

    letter_spacing_px = _parse_letter_spacing_px(letter_spacing_css, float(font_size))
    clip_width = max(width - clip_inset_left - clip_inset_right, 1)

    if item_layout == "module":
        # MODULE layout (brutalist instrument panel): uniform-width cast cells
        # with a per-module divider, the pitch sized from MEASURED content.
        # Start at the clip's left edge so modules fill the readout window
        # between the end-caps. Value font (Barlow Condensed) and label font
        # (mono) are resolved genome-aware before measurement.
        module_start_x = clip_inset_left
        value_meas_font = _resolve_font_for_measurement(
            module_value_font_family, genome_display_font=genome_display_font, genome_mono_font=genome_mono_font
        )
        label_meas_font = _resolve_font_for_measurement(
            module_label_font_family, genome_display_font=genome_display_font, genome_mono_font=genome_mono_font
        )
        value_ls_px = _parse_letter_spacing_px(letter_spacing_css, float(font_size))
        label_ls_px = _parse_letter_spacing_px(module_label_letter_spacing, float(module_label_font_size or 8))

        def _module_layout(items_in: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
            return _layout_marquee_modules(
                items_in,
                label_font=label_meas_font,
                label_font_size=module_label_font_size,
                label_letter_spacing_px=label_ls_px,
                value_font=value_meas_font,
                value_font_size=font_size,
                hero_font_size=hero_font_size,
                value_weight=measure_weight,
                value_letter_spacing_px=value_ls_px,
                inset=module_text_inset,
                start_x=module_start_x,
                min_width=module_min_width,
                divider_w=module_divider_w,
            )

        laid_out, content_end_x, module_width = _module_layout(items_for_layout)
        single_period = max(content_end_x - module_start_x, 1)
        # +1 extra repetition so the window stays full as Set-A scrolls off.
        repetitions = max(1, math.ceil(clip_width / single_period) + 1)
        if repetitions > 1:
            laid_out, content_end_x, module_width = _module_layout(items_for_layout * repetitions)
        start_x = module_start_x
        # Set-B mirrors Set-A per cell — color is content-derived, not cycled.
        for entry in laid_out:
            entry["value_color_set_b"] = entry.get("value_color", "")
            entry["label_color_set_b"] = entry.get("label_color", "")
    else:
        # RIBBON layout (chrome / cellular / default): inline label+value at one
        # absolute x with separators between, measured genome-aware.
        module_width = 0
        item_gap = 20  # historical inter-item breathing room
        label_value_gap = _MARQUEE_LABEL_VALUE_GAP  # label -> value tspan gap (ribbon)
        start_x = 16  # left padding inside the scroll viewport

        def _ribbon_layout(items_in: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
            return _layout_marquee_items(
                items_in,
                font_family=font_family,
                font_size=font_size,
                font_weight=measure_weight,
                letter_spacing_px=letter_spacing_px,
                item_gap=item_gap,
                label_value_gap=label_value_gap,
                start_x=start_x,
                separator_kind=separator_kind,
                separator_size=separator_size,
                separator_glyph=separator_glyph,
                label_font_size=label_font_size,
                genome_display_font=genome_display_font,
                genome_mono_font=genome_mono_font,
            )

        laid_out, content_end_x = _ribbon_layout(items_for_layout)
        single_period = max(content_end_x - start_x, 1)
        repetitions = max(1, math.ceil(width / single_period))
        if repetitions > 1:
            laid_out, content_end_x = _ribbon_layout(items_for_layout * repetitions)
        # Set-B mirrors Set-A per cell. State/role colors are content-derived
        # (not position-cycled), so the loop boundary needs no color shift.
        for entry in laid_out:
            if entry.get("type") == "text":
                inner = entry["item"]
                inner["value_color_set_b"] = inner.get("value_color", "")
                inner["label_color_set_b"] = inner.get("label_color", "")

    speed = spec.marquee_speeds[0] if spec.marquee_speeds else 1.0
    scroll_distance = content_end_x - start_x
    # Uniform reading rate across every genome (chrome's px/s) — NOT each
    # prototype's hardcoded dur (brutalist 33s, automata 23.5s).
    scroll_dur = round(scroll_distance / (CHROME_PX_PER_SEC * speed), 2)
    # Paradigms whose separators must NOT follow the variant signal accent
    # (cellular's neutral ▪) set separator_fill explicitly; everyone else gets
    # the signal-following wrapper (brutalist's per-variant emerald divider).
    separator_fill = separator_fill_override or f"var(--dna-signal, {separator_color})"
    # v0.3.12-fix — frame geometry reconciled to marquee-dense-chrome.svg's
    # actual construction (not just dims). Prototype well inset = 2px (was 4px),
    # left edge sliver = 3.5px (was a 6px rail), inner hairline at 1.5px. The
    # heavy feSpecularLighting bevel that brightened the border is replaced by a
    # flat drop shadow in chrome-defs.j2, and the prototype's static milled
    # detail (top specular line, white sheen, bottom shadow band, corner rivets)
    # is added below.
    chrome_well_w = max(0, width - 4)
    chrome_well_h = max(0, height - 4)
    chrome_inner_w = max(0, width - 3)
    chrome_inner_h = max(0, height - 3)
    chrome_specular_w = max(0, width - 8)
    chrome_sheen_w = max(0, width - 4)
    chrome_shadow_band_w = max(0, width - 4)
    marquee_geom = {
        "chrome_outer_rx": 4,
        "chrome_well_x": 2,
        "chrome_well_y": 2,
        "chrome_well_rx": 2.5,
        "chrome_rail_x": 2,
        "chrome_rail_y": 2,
        "chrome_rail_w": 3.5,
        "chrome_inner_x": 1.5,
        "chrome_inner_y": 1.5,
        "chrome_inner_rx": 3,
        "chrome_specular_x": 4,
        "chrome_specular_y": 2.5,
        "chrome_specular_h": 1,
        "chrome_sheen_x": 2,
        "chrome_sheen_y": 2,
        "chrome_sheen_h": 0.4,
        "chrome_shadow_band_x": 2,
        "chrome_shadow_band_y": height - 4,
        "chrome_shadow_band_h": 2,
        "chrome_rivet_size": 1,
        "chrome_rivets": [
            {"x": 6.5, "y": 5},
            {"x": 6.5, "y": height - 6},
            {"x": width - 8.5, "y": 5},
            {"x": width - 8.5, "y": height - 6},
        ],
        "brutalist_border_x": 0.5,
        "brutalist_border_y": 0.5,
        "brutalist_accent_x": 0,
        "brutalist_accent_y": 0,
        "brutalist_accent_w": 4,
        "cellular_hairline_x": 0,
        "cellular_top_hairline_y": 0,
        "cellular_hairline_h": 0.5,
    }

    # v0.3.12 — DECORATIVE liveness geometry, computed here so the {paradigm}
    # liveness partials carry zero coordinate arithmetic / literals (spatial
    # stencil contract). Module → brutalist end-caps + engineering grid;
    # ribbon → chrome LIVE+diamond + cellular wave-rail.
    live_mid = height // 2
    cap_r_x = clip_inset_left + clip_width
    rail_y = height - 3
    liveness: dict[str, Any] = {
        "origin": 0,
        "grid_line_w": 1,
        "diamond_rx": 0.5,
        "diamond_inner_rx": 0.3,
        # Brutalist module end-caps (left strobe-node, right seal) + bottom rail.
        "cap_l_w": clip_inset_left,
        "cap_r_x": cap_r_x,
        "cap_r_w": width - cap_r_x,
        "cap_h": rail_y,
        "cap_l_rail_x": clip_inset_left - 3,
        "cap_rail_w": 3,
        "cube_outer_x": 12,
        "cube_outer_y": 14,
        "cube_outer_w": 14,
        "cube_inner_x": 16,
        "cube_inner_y": 18,
        "cube_inner_w": 6,
        "seal_x": cap_r_x + 14,
        "seal_y": 16,
        "seal_w": 10,
        "bottom_rail_y": rail_y,
        "bottom_rail_h": 3,
        "perimeter_x": 0.5,
        "perimeter_y": 0.5,
        "perimeter_w": width - 1,
        "perimeter_h": height - 1,
        "grid_y": 2,
        "grid_h": height - 4,
        # Chrome ribbon LIVE wordmark + pulsing diamond.
        "live_text_x": 36,
        "live_text_y": live_mid + 4,
        "diamond_cx": 66,
        "diamond_cy": live_mid,
        "diamond_housing_x": -3.5,
        "diamond_housing_y": -3.5,
        "diamond_housing_w": 7,
        "diamond_inner_x": -2,
        "diamond_inner_y": -2,
        "diamond_inner_w": 4,
        "sep_x": 82,
        "sep_y1": 6,
        "sep_y2": height - 6,
        # Cellular wave-rail baseline.
        "rail_cell_y": height - 2,
        "rail_cell_w": 5,
        "rail_cell_h": 2,
    }
    # Vertical engineering-grid hairlines (module layout), 88px pitch.
    liveness_grid = [{"x": i * 88} for i in range(1, width // 88 + 1)] if item_layout == "module" else []
    # Travelling-wave rail cells (ribbon layout), 6px pitch, phase-delayed by x.
    _wv_n = width // 6
    liveness_rail = (
        [{"x": i * 6 + 2, "delay": round(i * 3.2 / _wv_n, 3)} for i in range(_wv_n)]
        if (item_layout != "module" and _wv_n)
        else []
    )

    ctx: dict[str, Any] = {
        "direction": spec.marquee_direction,
        "scroll_items": laid_out,
        "marquee_geom": marquee_geom,
        "scroll_distance": scroll_distance,
        "scroll_dur": scroll_dur,
        "scroll_start_x": start_x,
        # Paradigm-driven typography (template renders these as <text> attrs).
        "font_size": font_size,
        "label_font_size": label_font_size,
        # Intra-cell tspan-flow gaps (single-sourced; templates render as dx so
        # rendered width can't drift from the resolver's reserved width).
        "label_value_gap": _MARQUEE_LABEL_VALUE_GAP,
        "window_gap": _MARQUEE_WINDOW_GAP,
        "font_weight": font_weight_str,
        "letter_spacing": letter_spacing_css,
        "scroll_font_family": font_family,
        # Separator config (template branches on separator_kind).
        "separator_kind": separator_kind,
        "separator_size": separator_size,
        "separator_glyph": separator_glyph,
        "separator_color": separator_color,
        "separator_fill": separator_fill,
        "marquee_baseline_y": height // 2,
        "separator_rect_y": (height - separator_size) // 2,
        "marquee_perimeter_w": width - 1,
        "marquee_perimeter_h": height - 1,
        "chrome_well_w": chrome_well_w,
        "chrome_well_h": chrome_well_h,
        "chrome_inner_w": chrome_inner_w,
        "chrome_inner_h": chrome_inner_h,
        "chrome_rail_h": chrome_well_h,
        "chrome_specular_w": chrome_specular_w,
        "chrome_sheen_w": chrome_sheen_w,
        "chrome_shadow_band_w": chrome_shadow_band_w,
        "cellular_bottom_hairline_y": height - 0.5,
        # Text-fill mode (template uses text_fill_gradient_id when item.value_color is "").
        "text_fill_mode": text_fill_mode,
        "text_fill_gradient_id": text_fill_gradient_id,
        # Scroll-track clip rect: paradigm-driven inset from each edge so text
        # physically can't render on top of the perimeter chrome (chrome bezel,
        # accent bar, hairlines). Combined with the layered render order
        # (background -> text -> overlay), this makes characters disappear
        # cleanly under the perimeter as they scroll past the edges.
        "clip_x": clip_inset_left,
        "clip_y": clip_inset_top,
        "clip_w": width - clip_inset_left - clip_inset_right,
        "clip_h": height - clip_inset_top - clip_inset_bottom,
        "clip_rx": clip_rx,
        # v0.3.12 — scroll-item layout dispatch + module geometry. The template
        # includes item-{item_layout}.j2 (ribbon | module); module fields are
        # consumed only by item-module.j2.
        "item_layout": item_layout,
        "module_width": module_width,
        "module_label_y": module_label_y,
        "module_value_y": module_value_y,
        "module_divider_y": module_divider_y,
        "module_divider_h": module_divider_h,
        "module_divider_w": module_divider_w,
        "module_value_font_family": module_value_font_family,
        "module_label_font_family": module_label_font_family,
        "module_label_font_size": module_label_font_size,
        "module_label_letter_spacing": module_label_letter_spacing,
        "hero_font_size": hero_font_size,
        # Decorative liveness geometry (paradigm partials consume named values).
        "liveness": liveness,
        "liveness_grid": liveness_grid,
        "liveness_grid_y": liveness["grid_y"],
        "liveness_grid_h": liveness["grid_h"],
        "liveness_rail": liveness_rail,
        "liveness_rail_y": liveness["rail_cell_y"],
        "liveness_rail_w": liveness["rail_cell_w"],
        "liveness_rail_h": liveness["rail_cell_h"],
    }
    ctx.update(chrome_ctx)
    return {"width": width, "height": height, "template": "frames/marquee-horizontal.svg.j2", "context": ctx}


def _fmt_tok(n: int) -> str:
    """Format token count: 500 -> '500', 1500 -> '1.5K', 1500000 -> '1.5M'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


# ── Provider identity (runtime-keyed, v0.2.21 visual-fidelity-v2) ──
# Identity is keyed by the JSONL ``runtime`` field — NOT the skin. Skin and
# identity are orthogonal: skin chooses palette, runtime is the agent that
# produced the receipt. A user pinning ``--genome telemetry-voltage`` on a
# Claude Code session sees the voltage palette + Claude Code identity (glyph
# + label), because they chose a palette, not a different agent. As of
# v0.2.23 the (label, glyph) pair lives on each runtime's registry rather
# than in a hardcoded dict here.


def _resolve_provider(runtime: str) -> tuple[str, str | None]:
    """Map JSONL runtime field to (provider_label, glyph_id) for the hero brand line.

    Returns (``"HyperWeave"``, ``None``) when runtime is empty or unknown —
    the glyph slot stays empty and the brand line falls back to the project
    name. Branded runtimes (``claude-code``, ``codex``) carry an explicit
    identity package regardless of which palette skin is active. The
    identity package is sourced from the runtime registry's
    ``provider_label`` + ``glyph`` fields.
    """
    if not runtime:
        return ("HyperWeave", None)
    try:
        r = get_runtime(runtime)
    except KeyError:
        return ("HyperWeave", None)
    return (r.provider_label, r.glyph)


def _truncate_path_left(
    path: str,
    max_w: float,
    *,
    font_size: float = 9.0,
    letter_spacing_em: float = 0.04,
) -> str:
    """Truncate ``path`` from the LEFT (drop prefix, keep filename end) so the
    result fits inside ``max_w`` pixels at 9pt JetBrains Mono.

    Receipt footer paths take one of two shapes depending on the caller:
    the CLI write path emits a human-readable basename like
    ``20260508_receipt_debug_v0226.svg`` (set via
    ``ComposeSpec.receipt_filename_hint``); HTTP / MCP callers without the
    hint emit the legacy ``.hyperweave/receipts/<uuid>.svg`` shape. In both
    cases the *end* of the string carries the most identifying information
    (the slug or the UUID), and any leading prefix is the lower-signal
    portion to drop. Left-truncation emits ``…<unique-suffix>`` so a
    footer line that would otherwise collide with the right-aligned
    session date stays inside the content track.

    Returns the input unchanged when it already fits. Returns the empty
    string when ``max_w`` is too small even for a single ellipsis. Width
    measurements use the JetBrains Mono LUT in :mod:`hyperweave.core.text`
    — same font the receipt template renders the footer with.
    """
    from hyperweave.core.text import measure_text

    if not path:
        return ""
    full_w = measure_text(
        path,
        font_family="JetBrains Mono",
        font_size=font_size,
        letter_spacing_em=letter_spacing_em,
    )
    if full_w <= max_w:
        return path
    ellipsis = "…"
    ellipsis_w = measure_text(
        ellipsis,
        font_family="JetBrains Mono",
        font_size=font_size,
        letter_spacing_em=letter_spacing_em,
    )
    if ellipsis_w > max_w:
        return ""
    # Find the longest suffix that fits with a leading ellipsis. Linear
    # scan from the front; receipt paths are ~60 chars so n is tiny.
    for start in range(1, len(path)):
        suffix_w = measure_text(
            path[start:],
            font_family="JetBrains Mono",
            font_size=font_size,
            letter_spacing_em=letter_spacing_em,
        )
        if suffix_w + ellipsis_w <= max_w:
            return ellipsis + path[start:]
    return ellipsis


def _measure_text_width(text: str, font_size: int, weight: int = 400) -> float:
    """Approximate text width in pixels for sans-serif (Söhne / OpenAI Sans / Inter).

    Used by hero-zone layout to compute adaptive offsets — short provider
    names ("Codex") shouldn't leave dead space where the template assumed
    longer ones ("Claude Code"). The model label x-position is derived
    from this measurement, not hardcoded.

    Per-character width approximations (calibrated against v9 specimen at
    font-size 14 weight 760 where "Codex" measures 46.56px and against
    Inter at weight 700 where "Claude Code" measures ~89px):
        narrow (i, l, t, f, .)   : 0.32 x font_size
        space                    : 0.32 x font_size
        uppercase + numerals     : 0.65 x font_size
        lowercase                : 0.55 x font_size
    Bold weights (>=700) add ~10% width.
    """
    narrow = set("iltf.,;:!|")
    width = 0.0
    for ch in text:
        if ch in narrow or ch == " ":
            width += font_size * 0.32
        elif ch.isupper() or ch.isdigit():
            width += font_size * 0.65
        else:
            width += font_size * 0.55
    if weight >= 700:
        width *= 1.10
    return width


def _format_model_label(model: str) -> str:
    """Display-format a model identifier ("claude-opus-4-7" → "opus-4.7").

    Strips the vendor prefix and rewrites the trailing major-minor pair
    so "claude-opus-4-7" reads as "opus-4.7" — matching the v9 specimen
    convention. Falls back to the raw model string when it doesn't fit
    the recognized vendor-prefixed pattern.

    XML safety: strips angle brackets and ampersands. Claude Code's synthetic
    test transcripts carry ``model = "<synthetic>"`` as a marker token; when
    injected raw into the SVG ``<text>`` body it breaks XML parsing (Jinja2
    autoescape is off for SVG generation, so the template's text body inherits
    whatever the resolver hands it).
    """
    if not model:
        return ""
    # Strip XML-unsafe characters defensively. The known case is
    # ``"<synthetic>"`` from Claude Code synthetic transcripts; this also
    # protects against any future angle-bracket-wrapped identifier.
    label = model.replace("<", "").replace(">", "").replace("&", "").strip()
    if not label:
        return ""
    for prefix in ("claude-", "anthropic/"):
        if label.startswith(prefix):
            label = label[len(prefix) :]
            break
    parts = label.split("-")
    # Pattern: family-major-minor (e.g. "opus-4-7") → "opus-4.7".
    if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
        head = "-".join(parts[:-2])
        return f"{head}-{parts[-2]}.{parts[-1]}"
    return label


def _active_window_minutes(
    stages: list[dict[str, Any]],
    fallback_m: float,
    turn_duration_m: float | None = None,
) -> float:
    """Active work duration in minutes.

    Primary source is ``turn_duration_m`` — the parser's sum of per-turn
    compute durations from ``system.turn_duration`` events (Claude Code).
    This measures agent compute time directly and never absorbs idle gaps
    that the stage detector failed to break on (a multi-hour break inside
    a same-class working stretch silently inflates a stage's span).

    Fallback is ``min(sum_of_stage_durations, wall_clock_first_to_last)``
    when the runtime emits no per-turn duration events (Codex) or when
    stages lack ISO timestamps (mock fixtures):
      * Sum_of_stages collapses inter-stage idle in sessions left open
        across multiple bursts over days.
      * Wall-clock cap defends against any future stage detector that
        produces overlapping spans (today's partition algorithm cannot,
        but the cap costs nothing).

    The wall-clock cap applies to the turn-duration source too — defensive
    against malformed turn_duration values exceeding the session span.

    Returns ``fallback_m`` when stages lack ISO timestamps (mock data) or
    when parsing fails.
    """
    if not stages:
        if turn_duration_m is not None and turn_duration_m > 0:
            return max(turn_duration_m, 1.0)
        return fallback_m
    starts: list[datetime] = []
    ends: list[datetime] = []
    durations: list[float] = []
    for s in stages:
        start = s.get("start")
        end = s.get("end")
        if not start or not end:
            if turn_duration_m is not None and turn_duration_m > 0:
                return max(turn_duration_m, 1.0)
            return fallback_m
        try:
            t0 = datetime.fromisoformat(start)
            t_end = datetime.fromisoformat(end)
        except (ValueError, TypeError):
            if turn_duration_m is not None and turn_duration_m > 0:
                return max(turn_duration_m, 1.0)
            return fallback_m
        starts.append(t0)
        ends.append(t_end)
        durations.append((t_end - t0).total_seconds() / 60.0)
    wall_clock_m = (max(ends) - min(starts)).total_seconds() / 60.0
    if turn_duration_m is not None and turn_duration_m > 0:
        # Cap defensively at wall-clock so a runtime emitting impossibly
        # large turn_duration values can't make the chart disagree with
        # itself; in practice turn_duration_m << wall_clock_m always.
        return max(min(turn_duration_m, wall_clock_m), 1.0)
    sum_m = sum(durations)
    return max(min(sum_m, wall_clock_m), 1.0)


def _wall_clock_minutes(stages: list[dict[str, Any]], fallback_m: float) -> float:
    """Wall-clock span minutes from earliest stage start to latest stage end.

    Used as the ``total`` value in the hero divergence flag — a sensible
    upper bound on session duration when the parser's ``duration_minutes``
    underestimates (sessions where async tool calls extend past the last
    visible message).
    """
    if not stages:
        return fallback_m
    starts: list[datetime] = []
    ends: list[datetime] = []
    for s in stages:
        start = s.get("start")
        end = s.get("end")
        if not start or not end:
            return fallback_m
        try:
            starts.append(datetime.fromisoformat(start))
            ends.append(datetime.fromisoformat(end))
        except (ValueError, TypeError):
            return fallback_m
    if not starts or not ends:
        return fallback_m
    return max((max(ends) - min(starts)).total_seconds() / 60.0, 1.0)


def resolve_receipt(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve telemetry receipt — specimen-faithful 3-panel layout.

    Computes all visual layout from telemetry data:
    - Panel 1: Hero row with formatted stats
    - Panel 2: Token treemap (3-tier, area proportional to tokens)
    - Panel 3: Session rhythm bars (width=stage proportion, hue=phase)
    """
    tel: dict[str, Any] = dict(spec.telemetry_data or {})
    session: dict[str, Any] = tel.get("session", {})
    profile_data: dict[str, Any] = tel.get("profile", {})
    tools_raw = tel.get("tools", {})
    stages_raw: list[dict[str, Any]] = tel.get("stages", [])
    user_events: list[dict[str, Any]] = tel.get("user_events", [])
    agents: list[dict[str, Any]] = tel.get("agents", [])

    # ── Normalize tools: contract produces dict keyed by name, templates need list ──
    if isinstance(tools_raw, dict):
        tools: list[dict[str, Any]] = [{"name": name, **data} for name, data in tools_raw.items()]
    else:
        tools = list(tools_raw)

    # ── Normalize stages: contract produces {label, dominant_class, start, end, tools, tokens, errors} ──
    # Phase C added per-stage tokens + errors to the contract; Phase B's bar_chart
    # consumes them for variable-height bars and error-tick markers. Templates
    # also still see the legacy {name, pct, tool_class} shape.
    total_stage_tools = sum(s.get("tools", 1) for s in stages_raw) or 1
    stages: list[dict[str, Any]] = [
        {
            "name": s.get("dominant_class", s.get("label", "explore")),
            "pct": round(s.get("tools", 1) / total_stage_tools * 100),
            "label": s.get("label", ""),
            "tool_class": s.get("dominant_class", "explore"),
            "dominant_class": s.get("dominant_class", "explore"),
            "start": s.get("start"),
            "end": s.get("end"),
            "tokens": s.get("tokens", 0),
            "errors": s.get("errors", 0),
            "tools": s.get("tools", 0),
        }
        for s in stages_raw
    ]

    # ── Derive numeric values ──
    total_input = profile_data.get("total_input_tokens", 0)
    total_output = profile_data.get("total_output_tokens", 0)
    total_cache_read = profile_data.get("total_cache_read_tokens", 0)
    total_cache_create = profile_data.get("total_cache_creation_tokens", 0)
    total_tok = total_input + total_output + total_cache_read + total_cache_create
    total_cost = profile_data.get("total_cost", 0)
    # v0.3.5 hero decomp strip: IN / OUT / CACHED / WRITTEN cells beneath the hero.
    # Zero buckets render as em-dash in muted ink — fires unconditionally on the
    # WRITTEN cell for every Codex session (Codex has no cache_create concept;
    # codex_parser.py:355 always emits cache_create_tokens=0).
    decomp_cells = [
        {"label": label, "value": _fmt_tok(value) if value else "—", "is_zero": not value}
        for label, value in (
            ("IN", total_input),
            ("OUT", total_output),
            ("CACHED", total_cache_read),
            ("WRITTEN", total_cache_create),
        )
    ]
    duration_m = session.get("duration_minutes", 0)
    turn_duration_m = session.get("turn_duration_minutes")
    # Active window: prefers the parser's per-turn compute sum (Claude
    # Code's `system.turn_duration` events) and falls back to
    # min(stage-span sum, wall-clock) when the runtime emits no per-turn
    # signal (Codex) or stages lack timestamps. Same value drives the
    # chart geometry AND the hero subline, so they always agree.
    active_duration_m = _active_window_minutes(
        stages,
        float(duration_m),
        float(turn_duration_m) if turn_duration_m is not None else None,
    )
    wall_clock_m = _wall_clock_minutes(stages, float(duration_m))
    # ``total`` for the divergence flag: max of parser-reported duration and
    # the stage-derived wall-clock. The parser may overstate (idle tail) or
    # understate (async stages); max() picks whichever is more honest.
    total_duration_m = max(float(duration_m), wall_clock_m)
    model = session.get("model", profile_data.get("model", "Claude Session"))
    calls = sum(t.get("count", 0) for t in tools)

    # ── Tool-class fallback for tools that arrive without a tool_class field ──
    # Real session contracts always carry tool_class on each tool dict (set by
    # contract._assemble); this fallback only fires for hand-built test mocks
    # whose tools[] entries lack the field. The single source of truth is the
    # runtime registry — no Python dict drifting from data/telemetry/runtimes/.
    _runtime_name = session.get("runtime", "")
    try:
        _registry = get_runtime(_runtime_name) if _runtime_name else None
    except KeyError:
        _registry = None

    def _classify_tool_name(name: str) -> str:
        if not _registry:
            return "explore"  # mocks without runtime stay backward-compatible
        return classify_tool(_registry, name).value

    # ── Dominant phase (drives hero badge + bottom-right phase label) ──
    # Using stages[0] was the old bug — for a session where the first 2-minute
    # stage classified as "validation" but the dominant (45% of tool calls)
    # was "implementation", the hero badge lied. When no single stage owns
    # at least 20% of the tool calls, fall back to "MIXED" to avoid
    # overclaiming a dominant phase that doesn't exist.
    dominant = max(stages, key=lambda s: s.get("pct", 0)) if stages else None
    dominant_label = (dominant.get("label") or dominant.get("name") or "") if dominant else ""
    dominant_pct = dominant.get("pct", 0) if dominant else 0

    # ── Hero row ──
    # Phase B canonical layout for ALL skins: [glyph] {Provider} · {model} ......... [PHASE PILL]
    # Skin-driven identity: voltage/cream resolve to ("HyperWeave", None) so the
    # glyph slot renders empty even when the JSONL runtime is "claude-code". Branded
    # skins (claude-code, codex) always carry their identity package regardless of
    # runtime — the skin precedence chain already mapped runtime → skin upstream.
    provider_label, glyph_id = _resolve_provider(session.get("runtime", ""))
    model_label = _format_model_label(model)

    # Adaptive hero-zone spacing: model_label_x depends on the actual
    # provider_label width. Hardcoded x="142" assumed "Claude Code" sizing
    # and left an awkward gap for short labels like "Codex". The glyph sits
    # at x=24, the provider label starts at x=50; we measure the provider
    # label's pixel width at its render font (size 14, weight 700) and place
    # the model dot-separator immediately after it with a 8px gap.
    provider_label_x = 50
    if provider_label:
        provider_label_w = _measure_text_width(provider_label, font_size=14, weight=700)
        model_label_x = int(provider_label_x + provider_label_w + 8)
    else:
        model_label_x = provider_label_x  # no provider → no gap

    # v0.2.21 risograph hero treatment: split headline into tokens part +
    # signal-colored cost part so the template can render them as separate
    # tspans (cost in var(--dna-signal) per the spec).
    headline_tokens = f"{_fmt_tok(total_tok)} token volume · "
    headline_cost = f"${total_cost:.2f}"
    hero_headline = f"{headline_tokens}{headline_cost}"  # legacy single-string for fallback
    # v0.3.5: hero_subline retired. The duration + calls/stages information
    # now lives in hero-right rows 1 + 2 where it doesn't visually compete
    # with the hero number, and the decomp_cells strip takes over the y=82
    # position the subline used to occupy.
    if not dominant:
        hero_profile = "SESSION"
    elif dominant_pct < 20:
        hero_profile = "MIXED"
    else:
        hero_profile = dominant_label.upper()
    hero_tool_class = dominant["tool_class"] if dominant else "explore"
    # Phase pill: width estimated at ~7px/char + 16px padding (font-size 9 mono
    # with 0.28em letter-spacing per the v9 specimens). Right-aligned with the
    # 24px outer margin: pill_x = receipt_w - margin - pill_w.
    # v0.2.21 pill geometry: rx=4 with letter-spacing-aware width.
    # Char width 7px at font-size 9 with 0.28em letter-spacing means each
    # char effectively consumes ~7 * 1.28 = 8.96px of horizontal extent;
    # add 14px (~7px each side) of horizontal padding so the text sits
    # comfortably inside the pill and never clips at edges.
    pill_label = hero_profile.upper()
    pill_w = int(len(pill_label) * 7 * 1.28) + 14
    pill_x = 800 - 24 - pill_w
    # user_events is the unfiltered series of human-authored prose turns
    # (continuations + corrections + redirects + elaborations). Tool errors
    # count failing/blocked tool calls; the red ✗N cell marks reconcile to this.
    n_user_turns = len(user_events)
    n_tool_errors = sum(t.get("errors", 0) + t.get("blocked", 0) for t in tools)
    # n_agents = len(agents)  # was used by old footer; v0.2.21 footer is 4-quadrant.
    _ = agents  # keep the extraction for forward use without lint warnings
    # v0.3.5 hero-right: session-shape rows replace token-by-type rows. The
    # token decomposition now lives in the decomp_cells strip beneath the hero;
    # this column carries orthogonal "session shape" information (duration,
    # calls / stages, and friction signals).
    #
    # Row 1 (y=56): "Xm active · Ym total" — both values always shown when there
    # is any duration data, so receipts read consistently regardless of session
    # shape. Hiding "total" when it's close to "active" creates per-receipt
    # variance ("did the session have an idle tail or not?") and asks the
    # reader to interpret absence; matching values are positive signal (no
    # idle tail), not noise. Em-dash if no duration data is available.
    duration_row = f"{int(active_duration_m)}m active · {int(total_duration_m)}m total" if active_duration_m else "—"
    # Row 2 (y=70): call count + stage count — the session-shape spine.
    shape_row = f"{calls} calls · {len(stages)} stages"
    # Row 3 (y=84): turns + errors joined by " · ", failing-core fill when
    # errors > 0. Both counters render whenever there's any session activity —
    # "0 tool errors" is positive signal ("this session ran clean"), and
    # reading "6 user turns" alone makes a reader wonder whether errors were
    # tracked at all. The duplicated copy in footer_bl is replaced by the
    # cost-estimate disclaimer in this version — pushback info lives only here.
    pushback_parts: list[str] = []
    if n_user_turns or n_tool_errors:
        pushback_parts.append(f"{n_user_turns} user turn{'s' if n_user_turns != 1 else ''}")
        pushback_parts.append(f"{n_tool_errors} tool error{'s' if n_tool_errors != 1 else ''}")
    hero_right: list[dict[str, Any]] = [
        {"text": duration_row, "accent": ""},
        {"text": shape_row, "accent": ""},
    ]
    if pushback_parts:
        hero_right.append(
            {
                "text": " · ".join(pushback_parts),
                "accent": "failing" if n_tool_errors else "",
            },
        )

    # Pre-compute hero-right y-offsets so the template doesn't need loop math.
    # v0.3.5: rows at 64/78/92 with consistent 14-unit cadence. The starting
    # y=64 grounds the column near the bottom of the hero zone — row 3 lands
    # at y=92, baseline-aligned with the decomp strip on the left, so both
    # columns end at the same y close to the rule at y=104. This gives the
    # hero zone a unified bottom band instead of the right side floating
    # near the phase pill.
    for i, stat in enumerate(hero_right):
        stat["y"] = 64 + (i * 14)

    # ── Receipt geometry constants — single source of truth ──
    # left_margin is propagated to the template via context so every
    # left-anchored element (glyph, hero, decomp, dividers, group transforms,
    # footer lines) references the same value. Cell-internal text padding
    # (x=10/x=14 inside treemap cells) is cell layout, not receipt margin.
    left_margin = 24
    content_w = 800 - 2 * left_margin  # 752

    # ── Treemap layout — delegated to compose/treemap.py ──
    # Centralized in v0.2.21 to fix two arithmetic bugs that caused tier-3
    # cells (TaskCreate / ExitPlanMode / AskUserQuestion) to clip the right
    # edge of the receipt. The helper also applies label truncation and
    # synthesizes a "+N more" cell when the tool count exceeds what fits
    # at the tier-3 minimum width. See compose/treemap.py for the algorithm.
    classified_tools = [
        {**t, "tool_class": t.get("tool_class") or _classify_tool_name(t.get("name", ""))} for t in tools
    ]
    # v0.2.21 risograph-canonical: tier_y=(22, 118, 154), tier_h=(88, 32, 24).
    # The template's treemap zone now hosts the TOKEN MAP header inside it
    # (header at y=12, tier-1 at y=22, just below). Tier-3 cells are uniform
    # 90x24 (8 cells across the 752px track + 7 gaps x 4 = 748 ≤ 752).
    # Accent stripe position is genome-driven via the ``treemap_accent_side``
    # token: claude-code v9 specimen uses vertical stripes on the LEFT edge
    # (4px tier-1, 3px tier-2/3); voltage (titanium spec) and cream (risograph
    # spec) use horizontal stripes across the TOP (full-width x 1.5px). Each
    # specimen's accent treatment is part of its visual identity, declared in
    # the genome JSON — never inferred from a hardcoded skin-id check here.
    treemap_accent_position = genome.get("treemap_accent_side", "top")
    treemap_cells = compute_treemap_layout(
        classified_tools,
        content_w=content_w,
        accent_position=treemap_accent_position,
    )

    # ── Adaptive treemap zone height (v0.3.5) ──
    # Treemap reserves vertical space for up to 3 tiers (each with fixed
    # height); when a session populates fewer tiers, the zone collapses
    # so the rhythm header doesn't float far below the last cell row.
    # bottom_divider_y, rhythm_group_y, and panel_h all derive from the
    # max populated tier so the rhythm legend stays anchored at y=430 and
    # the footer at y=452/470/487 — receipt height stays 500.
    _max_tier = max((c.tier for c in treemap_cells), default=3) if treemap_cells else 3
    # Relative y where each tier's last cells end (tier_y + tier_h):
    #   tier-1: y=22, h=88 → bottom y=110
    #   tier-2: y=114, h=32 → bottom y=146
    #   tier-3: y=150, h=24 → bottom y=174
    _tier_bottoms_relative = {1: 110, 2: 146, 3: 174}
    _treemap_group_y = 108  # absolute y of treemap group transform
    _treemap_bottom_absolute = _treemap_group_y + _tier_bottoms_relative.get(_max_tier, 174)
    bottom_divider_y = _treemap_bottom_absolute + 8  # 8-unit gap below content
    rhythm_group_y = bottom_divider_y + 16  # 16-unit gap = rule-to-header parity

    # ── Rhythm panel — risograph-canonical structure (v0.2.21) ──
    # The bar_chart helper returns a BarChartLayout dataclass bundling
    # bars + error_ticks (separate band) + peak_marker + grid_lines +
    # header labels + counts. All geometry derives from the panel_h
    # parameter (single source of truth) so the y=-1 overflow bug from
    # Phase D's independently-hardcoded constants can't recur.
    # panel_h expands when treemap collapses so the legend (at relative
    # baseline_y + 16 with baseline_y = panel_h - 22) stays at absolute
    # y=430. Math: legend_y = rhythm_group_y + panel_h - 22 + 16 = 430
    # → panel_h = 436 - rhythm_group_y. For 3-tier sessions this yields
    # the canonical panel_h=130.
    panel_h = 436 - rhythm_group_y
    bar_layout = layout_bar_chart(
        stages,
        area_w=content_w,
        area_h=panel_h,
        duration_m=active_duration_m,
    )
    rhythm_bars = bar_layout.bars
    rhythm_error_ticks = bar_layout.error_ticks
    rhythm_peak_marker = bar_layout.peak_marker
    rhythm_grid_lines = bar_layout.grid_lines
    rhythm_total_label = bar_layout.total_tokens_label
    rhythm_peak_label = bar_layout.peak_tokens_label
    original_count = bar_layout.original_count
    shown_count = bar_layout.shown_count
    bar_baseline_y = bar_layout.baseline_y
    bar_area_h = panel_h
    time_axis_ticks = compute_time_axis_ticks(active_duration_m, area_w=content_w)

    # ── Legend entries (risograph-canonical) ──
    # treemap_cells are TreemapCell dataclasses; access via attribute, not key.
    used_classes = sorted({c.tool_class for c in treemap_cells}) if treemap_cells else ["explore"]
    treemap_legend = [{"tool_class": tc, "label": tc} for tc in used_classes]

    # v0.3.5: "TOKEN MAP ·" composed at the data layer so the · separator is
    # consistent with the other header strings (`Claude Code · opus-4.7`,
    # `SESSION RHYTHM · N STAGES · HEIGHT ≈ TOKENS`). The chip-to-chip
    # boundaries don't need · separators — the colored chip indicators
    # already carry the visual segmentation between class labels.
    # v0.3.5: "TOKEN MAP ·" composed at the data layer so the · separator
    # matches the rest of the receipt's header strings (`Claude Code · opus-4.7`,
    # `SESSION RHYTHM · N STAGES · HEIGHT ≈ TOKENS`). The legend chips flow
    # inline in the template via tspans — no absolute x's needed. Chips carry
    # just (tool_class, label); the template renders a colored ▍ indicator
    # followed by the label, with uniform dx gaps between chips.
    treemap_header_label = "TOKEN MAP ·"
    # Always renders all four standard classes (coordinate/execute/explore/mutate)
    # so the legend is stable across sessions; absent classes still appear so
    # cross-session comparison stays consistent.
    treemap_header_chips = [
        {"tool_class": "coordinate", "label": "coordinate"},
        {"tool_class": "execute", "label": "execute"},
        {"tool_class": "explore", "label": "explore"},
        {"tool_class": "mutate", "label": "mutate"},
    ]

    # Rhythm-panel legend: 4 tool swatches + error-tick swatch + DOMINANT label.
    # Each entry has pre-computed x-offset for the template to consume directly.
    phase_legend: list[dict[str, Any]] = [
        {"id": "coordinate", "label": "coordinate", "x": 0, "text_x": 10, "kind": "tool"},
        {"id": "execute", "label": "execute", "x": 82, "text_x": 92, "kind": "tool"},
        {"id": "explore", "label": "explore", "x": 152, "text_x": 162, "kind": "tool"},
        {"id": "mutate", "label": "mutate", "x": 220, "text_x": 230, "kind": "tool"},
        {"id": "error_tick", "label": "error tick", "x": 290, "text_x": 296, "kind": "error"},
    ]
    # DOMINANT label right-aligned (template renders this separately due to anchor).
    rhythm_dominant_label = f"{dominant_label.upper()} · {dominant_pct}%" if dominant_label and dominant else "SESSION"

    # Treemap subtitle: "BY TOOL · N SOURCES".
    treemap_subtitle = f"BY TOOL · {len(tools)} SOURCES" if tools else "BY TOOL"

    # Rhythm header composite (v0.2.21 risograph-canonical):
    # LEFT: "SESSION RHYTHM · N STAGES · HEIGHT ≈ TOKENS" — when bar_chart's
    #   merge_consecutive_same_class compacted N stages into M < N bars,
    #   the header surfaces it as "N STAGES (M SHOWN)" so the rendered bar
    #   count never silently diverges from the user's actual stage count.
    # RIGHT: "{total} · PEAK {peak}" — the bar_layout already formatted these.
    if shown_count != original_count:
        rhythm_header_left = f"SESSION RHYTHM · {original_count} STAGES ({shown_count} SHOWN) · HEIGHT ≈ TOKENS"
    else:
        rhythm_header_left = f"SESSION RHYTHM · {original_count} STAGES · HEIGHT ≈ TOKENS"
    rhythm_header_right = f"{rhythm_total_label} · {rhythm_peak_label}"

    # ── Provenance + footer 4-quadrant ──
    session_id = session.get("id", "")
    session_id_short = session_id[:8].rstrip("-") if session_id else ""
    git_branch = session.get("git_branch", "")
    project_path = session.get("project_path", "")
    project_name = Path(project_path).name if project_path else "session"
    # Footer filepath token: prefer the CLI-supplied human-readable basename
    # (matches the file the user sees on disk — e.g. "20260508_receipt_debug_v0226.svg").
    # Fall back to the legacy UUID path so HTTP / MCP callers that don't set
    # receipt_filename_hint keep rendering rather than blanking the footer.
    if spec.receipt_filename_hint:
        receipt_path = spec.receipt_filename_hint
    elif session_id:
        receipt_path = f".hyperweave/receipts/{session_id}.svg"
    else:
        receipt_path = ""

    start_iso = session.get("start", "")
    start_formatted = ""
    if start_iso:
        try:
            start_formatted = datetime.fromisoformat(start_iso).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            start_formatted = ""

    # Footer 4-quadrant per the risograph specimen convention:
    #   TL: repo · branch · receipts/<id>.svg
    #   TR: session <id> · <start_date>
    #   BL: {N} user turns · {N} tool errors  (was "generated by hyperweave.app")
    #   BR: hyperweave.app                    (was "agent session receipt")
    footer_tl_parts = [project_name]
    if git_branch:
        footer_tl_parts.append(git_branch)
    if receipt_path:
        footer_tl_parts.append(receipt_path)
    footer_tl = " · ".join(footer_tl_parts)

    footer_tr_parts: list[str] = []
    if session_id_short:
        footer_tr_parts.append(f"session {session_id_short}")
    if start_formatted:
        footer_tr_parts.append(start_formatted)
    footer_tr = " · ".join(footer_tr_parts)

    # ── Footer overlap guard ──
    # footer_tl is left-aligned at x=24, footer_tr right-aligned at the
    # 776 content edge. With long session IDs + branch names the two
    # strings collide at ~y=470 (production bug from claude-code 37.4M
    # receipt). Measure both at 9pt JetBrains Mono w/ 0.04em letter-
    # spacing (matches receipt.svg.j2's rendering), and if they would
    # overlap, truncate the receipt path from the LEFT — the
    # ``.hyperweave/receipts/`` prefix is identical across sessions, so
    # dropping it preserves all the unique information.
    if receipt_path:
        from hyperweave.core.text import measure_text

        _footer_gap = 16
        _tl_w = measure_text(footer_tl, font_family="JetBrains Mono", font_size=9.0, letter_spacing_em=0.04)
        _tr_w = measure_text(footer_tr, font_family="JetBrains Mono", font_size=9.0, letter_spacing_em=0.04)
        if _tl_w + _footer_gap + _tr_w > content_w:
            _prefix_parts = footer_tl_parts[:-1]
            _prefix = (" · ".join(_prefix_parts) + " · ") if _prefix_parts else ""
            _prefix_w = measure_text(_prefix, font_family="JetBrains Mono", font_size=9.0, letter_spacing_em=0.04)
            _max_for_path = content_w - _footer_gap - _tr_w - _prefix_w
            if _max_for_path > 0:
                footer_tl = _prefix + _truncate_path_left(receipt_path, _max_for_path)

    # v0.3.5 footer-bl: universal cost-estimate disclaimer. Matches Anthropic's
    # own SDK disclaimer language ("client-side estimate, not authoritative
    # billing data"). Turns/errors info lives in hero_right row 3, where the
    # failing-core color signal carries more semantic weight than down here.
    footer_bl = "Cost is an estimate based on public per-token rates."
    footer_br = "hyperweave.app"
    card_inset = int(genome.get("card_inset", 0))
    receipt_w = 800
    receipt_h = 500
    card_inner_w = receipt_w - (2 * card_inset)
    card_inner_h = receipt_h - (2 * card_inset)
    receipt_geom = {
        "card_rx": 5.5,
        "card_inner_rx": 3,
        "card_top_highlight_h": 32,
        "glyph_y": 16,
        "glyph_size": 18,
        "provider_y": 31,
        "model_y": 31,
        "pill_group_y": 14,
        "pill_h": 22,
        "pill_inner_x": 2,
        "pill_inner_y": 2,
        "pill_inner_h": 18,
        "pill_rule_top_y": 2,
        "pill_rule_bottom_y": 19,
        "pill_rule_h": 1,
        "pill_text_y": 14,
        "hero_headline_y": 66,
        "decomp_y": 92,
        "hero_rule_y": 104,
        "treemap_group_y": _treemap_group_y,
        "treemap_header_y": 12,
        "treemap_cell_hero_text_x": 14,
        "treemap_cell_text_x": 10,
        "hero_error_rect_x": -24,
        "hero_error_rect_y": -10,
        "hero_error_rect_w": 22,
        "hero_error_rect_h": 14,
        "hero_error_text_x": -13,
        "hero_error_text_y": 0,
        "rhythm_header_right_y": 0,
        "axis_tick_y": 20,
        "grid_y1": 30,
        "track_x1": 0,
        "bar_rx": 0.3,
        "legend_group_x": 0,
        "legend_marker_y": 0,
        "legend_error_w": 2,
        "legend_marker_w": 6,
        "legend_marker_h": 6,
        "legend_text_y": 6,
        "legend_dominant_y": 6,
        "footer_rule_y": 452,
        "footer_top_y": 470,
        "footer_bottom_y": 487,
        "card_top_strip_x": 0,
        "card_top_strip_y": 0,
        "card_top_strip_h": 2,
        "card_border_x": 0.5,
        "card_border_y": 0.5,
    }

    return {
        "width": receipt_w,
        "height": receipt_h,
        "template": "frames/receipt.svg.j2",
        "context": {
            "telemetry": tel,
            "receipt_geom": receipt_geom,
            # Hero zone (v0.2.21 risograph-canonical)
            "provider_label": provider_label,
            "provider_label_x": provider_label_x,
            "glyph_id": glyph_id,
            "has_glyph": bool(glyph_id),
            "model_label": model_label,
            "model_label_x": model_label_x,
            # Atmosphere backdrop (v0.2.23, codex skin) — empty list for skins
            # that don't declare a backdrop, so the template falls through to
            # the existing full-canvas substrate.
            "atmosphere_stops": genome.get("atmosphere_stops", []),
            "atmosphere_blooms": genome.get("atmosphere_blooms", []),
            "card_top_highlight": bool(genome.get("card_top_highlight", False)),
            "card_inset": card_inset,
            "card_inner_w": card_inner_w,
            "card_inner_h": card_inner_h,
            "hero_profile": hero_profile,
            "hero_tool_class": hero_tool_class,
            "hero_headline": hero_headline,
            "headline_tokens": headline_tokens,
            "headline_cost": headline_cost,
            "decomp_cells": decomp_cells,
            "hero_right_stats": hero_right,
            "pill_label": pill_label,
            "pill_w": pill_w,
            "pill_x": pill_x,
            "pill_inner_w": pill_w - 4,
            "pill_center_x": pill_w // 2,
            # Pill corner radius — genome-token driven (0=square, 11=full pill).
            # SVG2 auto-clamps rx to min(rx, height/2): inner rect (h=18) caps
            # at 9, outer rect (h=22) caps at 11. Both fully rounded at half-h.
            "pill_rx": genome.get("pill_rx", 4),
            "content_w": content_w,
            # Treemap panel
            "treemap_subtitle": treemap_subtitle,
            "treemap_legend": treemap_legend,
            "treemap_header_label": treemap_header_label,
            "treemap_header_chips": treemap_header_chips,
            "treemap_cells": treemap_cells,
            # Rhythm panel — v0.2.21 risograph-canonical structure
            "stage_count": len(stages),
            "rhythm_original_count": original_count,
            "rhythm_shown_count": shown_count,
            "rhythm_bars": rhythm_bars,
            "rhythm_error_ticks": rhythm_error_ticks,
            "rhythm_peak_marker": rhythm_peak_marker,
            "rhythm_grid_lines": rhythm_grid_lines,
            "rhythm_total_label": rhythm_total_label,
            "rhythm_peak_label": rhythm_peak_label,
            "rhythm_header_left": rhythm_header_left,
            "rhythm_header_right": rhythm_header_right,
            "rhythm_dominant_label": rhythm_dominant_label,
            "rhythm_baseline_y": bar_baseline_y,
            "rhythm_legend_y": bar_baseline_y + 16,
            "bar_area_h": bar_area_h,
            "time_axis_ticks": time_axis_ticks,
            "duration_minutes": int(duration_m),
            "phase_legend": phase_legend,
            "dominant_profile": f"{dominant_label} ({dominant_pct}%)",
            # Geometric constants pre-computed for the v0.2.21 thin-render template.
            # All derive from panel_h=130 in compose/bar_chart.py (single source).
            # left_margin (24) is the single source of truth for left-anchored
            # element positioning across the receipt template; see the geometry
            # constants block above for its definition.
            "left_margin": left_margin,
            "content_right_x": receipt_w - left_margin,
            # Adaptive zone boundaries — collapse when treemap has fewer tiers.
            "bottom_divider_y": bottom_divider_y,
            "rhythm_group_y": rhythm_group_y,
            "inner_w": receipt_w - 1,
            "inner_h": receipt_h - 1,
            "axis_tick_top_y": bar_area_h,
            "axis_tick_bottom_y": bar_area_h + 6,
            "axis_label_y": bar_area_h + 18,
            "legend_y": bar_area_h + 30,
            # Footer 4-quadrant
            "footer_tl": footer_tl,
            "footer_tr": footer_tr,
            "footer_bl": footer_bl,
            "footer_br": footer_br,
            # Backwards-compat fields kept until callers migrate.
            "metadata_left": footer_tl,
            "metadata_right": footer_tr,
            "footer_left": footer_bl,
            "footer_right": footer_br,
            "tools": tools,
            "stages": stages,
        },
    }


def resolve_rhythm_strip(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve rhythm-strip-v2 — 4-zone layout (identity / velocity / rhythm / status).

    Specimen: ``tier2/telemetry/receipt-types/receipts-pr-strips/rhythm-strip-v2.svg``
    600x92 strip, 4 zones separated by thin vertical dividers:

    * IDENTITY  (16-190px):  session id + call/duration/stages + tokens/cost +
                              4-chip tool legend.
    * VELOCITY  (200-264px): VEL label + big tok/min number + 8-bucket sparkline +
                              0m/{duration}m axis labels.
    * RHYTHM    (268-510px): variable-height bars + peak marker + 0m/{duration}m
                              labels + density hint.
    * STATUS    (522-600px): pulsing OK/WARN/ERR dot + dominant tool class +
                              percent-time.
    """
    from hyperweave.compose.rhythm_strip import (
        compute_dominant_phase,
        compute_session_velocity,
        compute_status_dot,
        compute_velocity_sparkline,
    )

    tel: dict[str, Any] = dict(spec.telemetry_data or {})
    session: dict[str, Any] = tel.get("session", {})
    profile_data: dict[str, Any] = tel.get("profile", {})
    tools_raw = tel.get("tools", {})
    stages_raw: list[dict[str, Any]] = tel.get("stages", [])

    # ── Normalize tools (dict→list) ──
    if isinstance(tools_raw, dict):
        tools: list[dict[str, Any]] = [{"name": n, **d} for n, d in tools_raw.items()]
    else:
        tools = list(tools_raw)

    # ── Normalize stages — same shape as resolve_receipt so bar_chart can consume ──
    stages: list[dict[str, Any]] = [
        {
            "label": s.get("label", ""),
            "tool_class": s.get("dominant_class", "explore"),
            "dominant_class": s.get("dominant_class", "explore"),
            "start": s.get("start"),
            "end": s.get("end"),
            "tokens": s.get("tokens", 0),
            "errors": s.get("errors", 0),
            "tools": s.get("tools", 0),
        }
        for s in stages_raw
    ]

    total_input = profile_data.get("total_input_tokens", 0)
    total_output = profile_data.get("total_output_tokens", 0)
    total_cache_read = profile_data.get("total_cache_read_tokens", 0)
    total_cache_create = profile_data.get("total_cache_creation_tokens", 0)
    total_tok = total_input + total_output + total_cache_read + total_cache_create
    total_cost = profile_data.get("total_cost", 0)
    duration_m = session.get("duration_minutes", 0)
    # Active window mirrors resolve_receipt — bounded by sum-of-stages and
    # wall-clock span. The strip's chart and identity zone both use this so
    # they agree without showing the parser's potentially-stale duration_m.
    active_duration_m = _active_window_minutes(stages, float(duration_m))
    calls = sum(t.get("count", 0) for t in tools)
    n_errors = sum(int(t.get("errors", 0)) + int(t.get("blocked", 0)) for t in tools)

    sid = session.get("id", "session")
    sid_short = sid[:8].rstrip("-") if len(sid) > 8 else sid

    # ── Identity zone (16-190px) ──
    # Session info + 4 tool-legend chips. The chips render alphabetically with
    # 28px stride matching the specimen.
    identity_chips = [
        {"tool_class": "explore", "label": "EXP", "x": 0, "text_x": 8},
        {"tool_class": "execute", "label": "EXE", "x": 28, "text_x": 36},
        {"tool_class": "mutate", "label": "MUT", "x": 56, "text_x": 64},
        {"tool_class": "coordinate", "label": "CRD", "x": 84, "text_x": 92},
    ]

    # ── Velocity zone (200-264px) ──
    # Big tok/min number + 8-bucket sparkline. Sparkline runs from x=210 to x=256
    # within the strip (panel-relative; template translates the zone).
    _, velocity_label = compute_session_velocity(stages, active_duration_m)
    sparkline = compute_velocity_sparkline(
        stages,
        duration_m=active_duration_m,
        x_left=210,
        x_right=256,
        y_top=56,
        y_bottom=68,
    )

    # ── Rhythm zone (268-510px) ──
    # Variable-height bars baseline-aligned to y=78 within the strip. Bars
    # max-height 28px (full ~28px track). No error band — errors surface in
    # the status zone via the dot color, not inline marks.
    bar_area_w = 510 - 268
    bar_layout = layout_bar_chart(
        stages,
        area_w=bar_area_w,
        baseline_y_override=78,
        bar_max_h_override=28,
        emit_error_ticks=False,
        duration_m=active_duration_m,
    )

    # ── Status zone (522-600px) ──
    status_indicator = compute_status_dot(n_errors=n_errors, total_calls=calls)
    dominant_phase = compute_dominant_phase(stages, active_duration_m)
    rhythm_strip_geom = {
        "card_rx": 5,
        "identity_x": 16,
        "identity_y": 0,
        "identity_title_y": 22,
        "identity_info_y": 38,
        "identity_token_y": 52,
        "chip_y": 0,
        "chip_w": 6,
        "chip_h": 6,
        "chip_rx": 1,
        "chip_text_y": 5.5,
        "divider_y1": 14,
        "divider_y2": 78,
        "identity_divider_x": 190,
        "velocity_x": 200,
        "velocity_y": 0,
        "velocity_divider_x": 264,
        "velocity_text_x": 10,
        "velocity_label_y": 18,
        "velocity_value_y": 38,
        "velocity_unit_y": 49,
        "sparkline_dot_r": 1.5,
        "sparkline_label_left_x": 210,
        "sparkline_label_right_x": 256,
        "sparkline_label_y": 76,
        "rhythm_x": 268,
        "rhythm_y": 0,
        "rhythm_title_x": 0,
        "rhythm_title_y": 46,
        "rhythm_baseline_x1": 0,
        "rhythm_baseline_y": 78,
        "bar_rx": 0.3,
        "time_label_x": 0,
        "time_label_y": 87,
        "density_x": -2,
        "density_y": 52,
        "density_transform": "rotate(-90, -2, 52)",
        "status_divider_x": 510,
        "status_x": 522,
        "status_y": 0,
        "status_dot_cx": 6,
        "status_dot_cy": 20,
        "status_dot_r": 3.5,
        "status_word_x": 14,
        "status_word_y": 23,
        "status_errors_y": 38,
        "status_dominant_label_y": 54,
        "status_dominant_y": 67,
        "status_pct_y": 79,
        "edge_x": 1,
        "edge_top_y": 0,
        "edge_h": 0.8,
        "border_x": 0.5,
        "border_y": 0.5,
        "border_rx": 4.5,
    }

    return {
        "width": 600,
        "height": 92,
        "template": "frames/rhythm-strip.svg.j2",
        "context": {
            "telemetry": tel,
            "rhythm_strip_geom": rhythm_strip_geom,
            # IDENTITY zone
            "session_id_short": sid_short,
            "call_number": calls,
            "duration_label": f"{int(active_duration_m)}m" if active_duration_m else "—",
            "stage_count": len(stages),
            "token_total_label": _fmt_tok(total_tok),
            "cost_label": f"${total_cost:.2f}",
            "identity_chips": identity_chips,
            # VELOCITY zone
            "velocity_label": velocity_label,
            "sparkline_points": sparkline.points,
            "sparkline_start_point": sparkline.points[0] if sparkline.points else None,
            "sparkline_end_point": sparkline.points[-1] if sparkline.points else None,
            "sparkline_fill_path": sparkline.fill_path,
            "sparkline_stroke_path": sparkline.stroke_path,
            "sparkline_label_left": sparkline.label_left,
            "sparkline_label_right": sparkline.label_right,
            # RHYTHM zone
            "rhythm_bars": bar_layout.bars,
            "rhythm_peak_marker": bar_layout.peak_marker,
            "rhythm_total_label": bar_layout.total_tokens_label,
            "rhythm_peak_label": bar_layout.peak_tokens_label,
            "rhythm_baseline_y": bar_layout.baseline_y,
            "rhythm_label_left": "0m",
            "rhythm_label_right": f"{int(active_duration_m)}m" if active_duration_m else "0m",
            "rhythm_axis_w": bar_area_w,
            "rhythm_strip_inner_w": 598,
            "rhythm_strip_bottom_highlight_y": 91.2,
            "rhythm_strip_inner_h": 91,
            # STATUS zone
            "status_word": status_indicator.word,
            "status_severity": status_indicator.severity,
            "status_color_var": status_indicator.color_var,
            "n_errors": n_errors,
            "dominant_label": dominant_phase.label,
            "dominant_tool_class": dominant_phase.tool_class,
            "dominant_pct_time": dominant_phase.pct_time,
            # Backwards-compat fields kept until callers migrate.
            "stages": bar_layout.bars,
            "elapsed_label": f"{int(duration_m)}m" if duration_m else "—",
            "token_summary": f"{_fmt_tok(total_tok)} tok · ${total_cost:.2f}",
            "velocity_value": velocity_label,
            "loop_detected": False,
            "loop_elevated": False,
            "loop_label": status_indicator.word,
            "loop_detail": f"{n_errors} err" if n_errors else "no loop",
            "profile_label": (f"{dominant_phase.label} {dominant_phase.pct_time}%" if dominant_phase.label else ""),
            # v0.2.23: atmosphere backdrop tokens — empty for skins that don't
            # declare them, so the strip falls through to the original solid
            # substrate paint. Codex skin uses these to keep its rhythm strip
            # visually coherent with its receipt.
            "atmosphere_stops": genome.get("atmosphere_stops", []),
            "atmosphere_blooms": genome.get("atmosphere_blooms", []),
        },
    }


# Helpers


class GenomeNotFoundError(KeyError):
    """Raised when a genome ID is requested but not registered.

    Distinct from generic ``KeyError`` so the HTTP layer can map it to a
    404 SVG fallback (see :func:`hyperweave.serve.app._classify_compose_exception`).
    Inherits from ``KeyError`` so callers that already write ``except KeyError``
    continue to catch it -- existing silent-fallback contracts that rely on
    Mapping-style ``.get()`` semantics still hold by walking through
    ``override`` or by handling ``KeyError`` explicitly.
    """

    def __init__(self, genome_id: str) -> None:
        super().__init__(genome_id)
        self.genome_id = genome_id

    def __str__(self) -> str:
        return f"Genome {self.genome_id!r} not found"


def _load_genome(genome_id: str, override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load a genome dict by slug, or return the override if provided.

    Session 2A+2B: when ``override`` is a dict, it is returned verbatim.
    This is the ``--genome-file`` path — the CLI loads JSON, validates via
    ``GenomeSpec``, and passes the resulting dict through ``ComposeSpec.genome_override``.
    The resolver trusts the caller to have validated.

    Raises:
        GenomeNotFoundError: when ``genome_id`` is not registered and no
            override is supplied. The HTTP layer maps this to a 404 SVG
            fallback via the SMPTE NO SIGNAL error badge so a broken
            ``<img>`` URL renders as a branded error state instead of a
            browser broken-image icon.
    """
    if override is not None:
        return override
    try:
        from hyperweave.config.loader import get_loader
    except ImportError:
        # Bootstrap-only path: loader can't be imported (partial install /
        # circular dep during early startup). Fall back to the safe default
        # so the bootstrap continues; production paths always have a loader.
        return _default_genome(genome_id)
    loader = get_loader()
    genome = loader.genomes.get(genome_id)
    if genome is None:
        raise GenomeNotFoundError(genome_id)
    return genome


def _resolve_paradigm(genome: dict[str, Any], frame_type: str, default: str = "default") -> str:
    """Return the paradigm slug for a frame type from the genome's paradigms dict.

    Implements Principle 26 dispatch. Missing entries default to ``"default"``.
    """
    paradigms = genome.get("paradigms") or {}
    if not isinstance(paradigms, dict):
        return default
    value = paradigms.get(frame_type, default)
    return str(value) if value else default


def _default_genome(genome_id: str) -> dict[str, Any]:
    return {
        "id": genome_id,
        "name": genome_id,
        "category": "dark",
        "profile": "brutalist",
        "surface_0": "#1C1C1C",
        "ink": "#E4E4E7",
        "accent": "#B31B1B",
        "compatible_motions": ["static"],
    }


def _load_profile(profile_id: str) -> dict[str, Any]:
    try:
        from hyperweave.config.loader import get_loader

        loader = get_loader()
        return loader.profiles.get(profile_id, _default_profile())
    except (ImportError, Exception):
        return _default_profile()


def _default_profile() -> dict[str, Any]:
    return {
        "id": "brutalist",
        "badge_frame_height": 22,
        "badge_corner": 3.33,
        "strip_corner": 5,
        "strip_accent_width": 0,
        "strip_metric_pitch": 100,
        "strip_divider_mode": "full",
        "glyph_backing": "none",
        "status_shape": "circle",
        "easing": "ease-in-out",
        "fonts": {
            "title": "'Inter', system-ui, sans-serif",
            "value": "'Inter', system-ui, sans-serif",
            "mono": "'SF Mono', 'JetBrains Mono', monospace",
        },
    }


def _resolve_glyph(spec: ComposeSpec) -> dict[str, Any]:
    if spec.glyph_mode == GlyphMode.NONE:
        return {}

    try:
        from hyperweave.config.settings import get_settings
        from hyperweave.render.glyphs import infer_glyph, load_glyphs

        settings = get_settings()
        glyphs = load_glyphs(settings.data_dir / "glyphs.json")

        glyph_id = spec.glyph
        if glyph_id and glyph_id in glyphs:
            return _glyph_payload(glyph_id, glyphs)
        if spec.custom_glyph_svg:
            return {
                "id": "custom",
                "path": "",
                "viewBox": "",
                "custom_svg": spec.custom_glyph_svg,
            }

        inferred = _infer_glyph_id(spec, glyphs, infer_glyph)
        if inferred and inferred in glyphs:
            return _glyph_payload(inferred, glyphs)
        # Strip-scoped default: when no explicit glyph, custom SVG, or inferred
        # provider resolves, strips fall back to the HyperWeave sigil so the
        # identity zone carries the brand mark instead of an empty/ornament-only
        # bookend. Other frames keep their no-glyph behavior (badges stay clean).
        # ``--glyph none`` → glyph_mode NONE (returned above) still suppresses.
        if spec.type == "strip" and "hyperweave" in glyphs:
            return _glyph_payload("hyperweave", glyphs)
    except (ImportError, Exception):
        pass

    if spec.custom_glyph_svg:
        return {
            "id": "custom",
            "path": "",
            "viewBox": "",
            "custom_svg": spec.custom_glyph_svg,
        }

    return {}


def _glyph_payload(glyph_id: str, glyphs: Mapping[str, Mapping[str, object]]) -> dict[str, Any]:
    glyph = glyphs[glyph_id]
    return {
        "id": glyph_id,
        "path": str(glyph.get("path", "")),
        "viewBox": str(glyph.get("viewBox", "0 0 640 640")),
    }


def _infer_glyph_id(spec: ComposeSpec, glyphs: Mapping[str, object], infer_glyph: Callable[[str], str]) -> str:
    votes, hero_provider = _glyph_provider_votes(spec)
    if votes:
        top_count = max(votes.values())
        winners = [provider for provider, count in votes.items() if count == top_count]
        dominant = hero_provider if hero_provider in winners else winners[0]
        glyph_id = _glyph_id_for_provider(dominant, glyphs, infer_glyph)
        if glyph_id:
            return glyph_id

    text_candidates = [
        spec.title,
        spec.stats_username,
        spec.chart_owner,
        spec.chart_repo,
    ]
    raw = spec.connector_data
    if isinstance(raw, Mapping):
        for key in ("identity", "username", "repo", "repo_slug", "source_url", "url", "html_url", "repo_url"):
            value = raw.get(key)
            if isinstance(value, str):
                text_candidates.append(value)
    return infer_glyph(" ".join(part for part in text_candidates if part))


def _glyph_id_for_provider(provider: str, glyphs: Mapping[str, object], infer_glyph: Callable[[str], str]) -> str:
    if not provider:
        return ""
    if provider in glyphs:
        return provider
    glyph_id = infer_glyph(provider)
    return glyph_id if glyph_id in glyphs else ""


def _glyph_provider_votes(spec: ComposeSpec) -> tuple[dict[str, int], str]:
    votes: dict[str, int] = {}
    hero_provider = ""

    def vote(provider: str, amount: int = 1) -> None:
        if provider:
            votes[provider] = votes.get(provider, 0) + amount

    raw = spec.connector_data
    if isinstance(raw, Mapping):
        direct_providers = _providers_from_mapping(raw)
        direct_single = direct_providers[0] if len(direct_providers) == 1 else ""
        hero = raw.get("hero")
        if isinstance(hero, Mapping):
            hero_parts = _providers_from_mapping(hero) or ([direct_single] if direct_single else [])
            if hero_parts:
                hero_provider = hero_parts[0]
                vote(hero_provider)
        elif direct_single and any(key in raw for key in ("hero_label", "hero_value", "stars_total", "current_stars")):
            hero_provider = direct_single
            vote(hero_provider)

        metric_value = raw.get("metrics")
        if isinstance(metric_value, Sequence) and not isinstance(metric_value, str | bytes | bytearray):
            for item in metric_value:
                if not isinstance(item, Mapping):
                    continue
                metric_providers = _providers_from_mapping(item)
                if not metric_providers and direct_single:
                    metric_providers = [direct_single]
                for provider in metric_providers[:1]:
                    vote(provider)

        if not votes:
            for provider in direct_providers:
                vote(provider)
            if direct_providers and not hero_provider:
                hero_provider = direct_providers[0]

    token_value = spec.data_tokens
    if isinstance(token_value, Sequence) and not isinstance(token_value, str | bytes | bytearray):
        for token in token_value:
            provider = _normalize_glyph_provider(str(getattr(token, "provider", "") or ""))
            if provider:
                if not hero_provider:
                    hero_provider = provider
                vote(provider)

    return votes, hero_provider


def _providers_from_mapping(value: Mapping[str, object]) -> list[str]:
    direct_value = _first_mapping_value(value, ("provider", "source", "provider_source", "platform"))
    return _split_provider_chain(direct_value)


def _first_mapping_value(value: Mapping[str, object], keys: Sequence[str]) -> str:
    for key in keys:
        item = value.get(key)
        if item is not None and item != "":
            return str(item)
    return ""


def _split_provider_chain(value: str) -> list[str]:
    if not value:
        return []
    providers: list[str] = []
    for part in value.replace(",", "+").split("+"):
        provider = _normalize_glyph_provider(part)
        if provider and provider not in providers:
            providers.append(provider)
    return providers


def _normalize_glyph_provider(value: str) -> str:
    return value.strip().lower()


def _resolve_motion(spec: ComposeSpec, genome: dict[str, Any]) -> str:
    motion = spec.motion
    compatible = genome.get("compatible_motions", ["static"])

    if motion == MotionId.STATIC:
        return MotionId.STATIC

    if motion in compatible:
        return motion

    # Ungoverned regime allows any motion
    if spec.regime == Regime.UNGOVERNED:
        return motion

    return MotionId.STATIC


def _parse_metrics(spec: ComposeSpec) -> list[dict[str, Any]]:
    """Parse metric slots from ComposeSpec.

    Slot zones understood:
      ``metric``        — regular numeric/text metric (label + value)
      ``metric-state``  — hybrid cell where the value is itself a status
                          word (passing/warning/etc.). Carries an optional
                          ``state`` key populated from ``slot.data['state']``
                          or falling back to ``spec.state``. Consumed by the
                          cellular paradigm strip for the BUILD-style cell.

    Falls back to comma-separated ``spec.value`` when no metric slots are
    present (``"STARS:2.9k,FORKS:278"`` pattern).
    """
    metrics: list[dict[str, Any]] = []

    # Try slots first. Both ``metric`` and ``metric-state`` produce entries;
    # the latter carries an optional ``state`` field so templates can branch
    # on whether this is a state-carrier cell.
    for slot in spec.slots:
        if slot.zone.startswith("metric"):
            parts = slot.value.split(":", 1) if ":" in slot.value else [slot.zone, slot.value]
            entry: dict[str, Any] = {
                "label": parts[0].upper(),
                "value": parts[1] if len(parts) > 1 else slot.value,
            }
            if slot.zone == "metric-state":
                slot_data = slot.data or {}
                entry["state"] = str(slot_data.get("state", spec.state))
            metrics.append(entry)

    # Fallback: parse from description
    if not metrics and spec.value:
        for pair in spec.value.split(","):
            pair = pair.strip()
            if ":" in pair:
                k, v = pair.split(":", 1)
                metrics.append(
                    {
                        "label": k.strip().upper(),
                        "value": v.strip(),
                        "delta": "",
                        "delta_dir": "neutral",
                    }
                )

    # Ensure all metrics have delta fields (and a default empty state key so
    # templates can check ``metric.state`` without Jinja2 StrictUndefined errors).
    for m in metrics:
        m.setdefault("delta", "")
        m.setdefault("delta_dir", "neutral")
        m.setdefault("state", "")

    return metrics


def _genome_material_context(genome: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Project the genome's material/chromatic fields into template context.

    After the Phase 2 strict-fallback refactor, every chrome-paradigm
    required field (envelope_stops, well_top, well_bottom,
    chrome_text_gradient, hero_text_gradient, highlight_color) is
    validated at load time for genomes that opt into the chrome
    paradigm, so chrome-defs templates no longer carry specimen-color
    ``| default(...)`` fallbacks. Non-chrome genomes simply don't
    route through chrome templates, so empty values here are benign.

    Renamed from ``_profile_visual_context`` — the function has always
    read from ``genome``, not ``profile``. The old name was misleading.
    """

    def _stop_color(stops: object, offset: str) -> str:
        if not isinstance(stops, list):
            return ""
        for stop in stops:
            if isinstance(stop, dict) and stop.get("offset") == offset:
                return str(stop.get("color") or "")
        return ""

    corner_raw = str(genome.get("corner", "4px")).replace("px", "")
    envelope_stops = genome.get("envelope_stops", [])
    chrome_text_gradient = genome.get("chrome_text_gradient", [])
    return {
        "envelope_stops": envelope_stops,
        "well_top": genome.get("well_top", ""),
        "well_bottom": genome.get("well_bottom", ""),
        # Icon-specific well colors (v0.2.16): chrome icons use a more saturated
        # navy (#0C1E2E -> #06101A per v2 spec) than the wider marquee/strip
        # well (#020617 -> #0B1121). Falls back to well_top/well_bottom when not
        # declared, so non-chrome genomes don't need these fields.
        "icon_well_top": genome.get("icon_well_top", "") or genome.get("well_top", ""),
        "icon_well_bottom": genome.get("icon_well_bottom", "") or genome.get("well_bottom", ""),
        "specular_light": genome.get("highlight_color", ""),
        "chrome_rim_soft": genome.get("chrome_rim_soft", "") or _stop_color(envelope_stops, "50%"),
        "chrome_rim_core": genome.get("chrome_rim_core", "") or _stop_color(chrome_text_gradient, "50%"),
        "chrome_icon_inner_stroke": genome.get("chrome_icon_inner_stroke", ""),
        "chrome_icon_top_accent": genome.get("chrome_icon_top_accent", "") or _stop_color(envelope_stops, "44%"),
        "highlight_opacity": genome.get("highlight_opacity", ""),
        "bevel_shadow_color": genome.get("shadow_color", ""),
        "bevel_shadow_opacity": genome.get("shadow_opacity", ""),
        "chrome_corner": corner_raw,
        "chrome_text_gradient": chrome_text_gradient,
        "hero_text_gradient": genome.get("hero_text_gradient", []),
        "chrome_rhythm": genome.get("rhythm_base", ""),
        # Provider glyph fill = the genome's glyph_inner role, both substrates.
        # v0.3.13: every brutalist glyph zone (badge/strip/icon left panel, icon
        # body) is an INK mass, so the glyph is a CREAM knockout — which is
        # exactly what glyph_inner already holds for light variants (and the
        # accent for dark, which renders accent-on-dark). The earlier light
        # override to `ink` was written for the superseded cream-left-panel badge
        # (ink-on-paper); on the current ink panels it rendered ink-on-ink
        # (invisible glyph). One field, no substrate branch.
        "glyph_fill": genome.get("glyph_inner", ""),
        "light_mode": genome.get("light_mode"),
        # Cellular paradigm palette/pulse config. The 22 flat variant_blue_*/
        # variant_purple_*/variant_bifamily_bridge_* fields previously surfaced
        # here moved into cellular_palette (resolve_cellular_palette() in
        # compose/palette.py) — templates now consume cellular_palette.primary,
        # .secondary, .bridge instead of the flat fields. Pulse config stays
        # because it's structural (cell animation timings + opacity), not
        # tone-specific.
        "cellular_pulse_base_duration": genome.get("cellular_pulse_base_duration", "6s"),
        "cellular_pulse_fast_duration": genome.get("cellular_pulse_fast_duration", "3s"),
        "cellular_pattern_opacity": genome.get("cellular_pattern_opacity", "0.78"),
        # State palette (consumed by templates/partials/state-signal-cascade.j2).
        "state_passing_core": genome.get("state_passing_core", ""),
        "state_passing_bright": genome.get("state_passing_bright", ""),
        "state_warning_core": genome.get("state_warning_core", ""),
        "state_warning_bright": genome.get("state_warning_bright", ""),
        "state_critical_core": genome.get("state_critical_core", ""),
        "state_critical_bright": genome.get("state_critical_bright", ""),
        "state_building_core": genome.get("state_building_core", ""),
        "state_building_bright": genome.get("state_building_bright", ""),
        "state_offline_core": genome.get("state_offline_core", ""),
        "state_offline_bright": genome.get("state_offline_bright", ""),
    }


def _lighten_hex(hex_color: str) -> str:
    """Lighten a hex color by blending 50% toward white."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = (r + 255) // 2
    g = (g + 255) // 2
    b = (b + 255) // 2
    return f"#{r:02x}{g:02x}{b:02x}"
