"""Spec resolver -- resolves genome, profile, frame, glyph, motion for each frame type."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hyperweave.compose.bar_chart import compute_time_axis_ticks, layout_bar_chart
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
    if runtime == "claude-code":
        return "telemetry-claude-code"
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
    if spec.type in {FrameType.RECEIPT, FrameType.RHYTHM_STRIP, FrameType.MASTER_CARD}:
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
        "master-card": resolve_master_card,
        "catalog": resolve_catalog,
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
    frame_result = resolver_fn(spec, genome, profile, glyph_data=glyph_data, paradigm_spec=paradigm_spec)

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

    return ResolvedArtifact(
        genome=genome,
        profile=profile,
        profile_id=genome.get("profile", spec.profile_id or "brutalist"),
        category=genome.get("category", "dark"),
        width=frame_result["width"],
        height=frame_result["height"],
        frame_template=frame_result["template"],
        frame_context=ctx,
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
    from hyperweave.core.text import measure_text

    # Height + size class: paradigm-driven default or compact variant.
    # Cellular badges render at 32px default / 20px compact; brutalist/chrome
    # stay at 20px. ``compact`` flows into text-measurement scaling and
    # template pattern-cell geometry.
    compact = spec.size == "compact"
    badge_cfg_for_height = paradigm_spec.badge if paradigm_spec else None
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
        if compact and badge_cfg_for_glyph_size.glyph_size_compact > 0:
            glyph_size = badge_cfg_for_glyph_size.glyph_size_compact
        else:
            glyph_size = badge_cfg_for_glyph_size.glyph_size
    else:
        glyph_size = 14
    glyph_gap = 4

    sep_w = profile.get("badge_sep_width", 2)
    seam_w = profile.get("badge_seam_width", 3)
    indicator_size = profile.get("badge_indicator_size", 8)
    ind_pad_r = profile.get("badge_indicator_pad_r", 8)
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
    _value_weight = paradigm_spec.badge.value_font_weight if paradigm_spec else 700
    _label_size = paradigm_spec.badge.label_font_size if paradigm_spec else font_size
    _value_size = paradigm_spec.badge.value_font_size if paradigm_spec else font_size
    if compact:
        _label_size = max(round(_label_size * 0.78), 6)
        _value_size = max(round(_value_size * 0.78), 7)

    lw = (
        measure_text(
            label_display,
            font_family=_label_family,
            font_size=_label_size,
            font_weight=400 if use_mono else 700,
        )
        if label_display
        else 0.0
    )
    vw = (
        measure_text(
            value_raw,
            font_family=_value_family,
            font_size=_value_size,
            font_weight=_value_weight,
        )
        if value_raw
        else 0.0
    )

    # Monospace labels get letter-spacing 0.06em (CSS declared in chrome-defs).
    if use_mono and label_display:
        lw += len(label_display) * font_size * 0.06

    has_glyph = bool(spec.glyph or spec.custom_glyph_svg)

    # Glyph-left offset: paradigms that render decoration on the left edge
    # (cellular pattern strip at x=2..~20) need the glyph pushed rightward so
    # it doesn't overlap. Brutalist/chrome declare 0 (no offset).
    badge_cfg_for_glyph = paradigm_spec.badge if paradigm_spec else None
    if badge_cfg_for_glyph is not None:
        if compact and badge_cfg_for_glyph.glyph_offset_left_compact > 0:
            glyph_left_offset = badge_cfg_for_glyph.glyph_offset_left_compact
        else:
            glyph_left_offset = badge_cfg_for_glyph.glyph_offset_left
    else:
        glyph_left_offset = 0

    # Glyph pixel position
    if has_glyph:
        glyph_x = (inset + accent_w + 4) if inset else (accent_w + 3)
        glyph_x += glyph_left_offset
        glyph_y = round((height - glyph_size) / 2, 1)
    else:
        glyph_x, glyph_y = 0, 0.0

    # Label area starts after glyph (or after accent + paradigm left-edge decoration).
    # When a paradigm declares ``glyph_left_offset`` (cellular: 18 default, 12 compact)
    # it reserves a left-edge zone for decoration (cellular pattern strip at x=2..~20).
    # The with-glyph branch already clears that zone via glyph_x. The no-glyph
    # branch must also respect it — otherwise label text overlaps the decoration.
    # Brutalist/chrome are unaffected: glyph_left_offset=0.
    label_start = (glyph_x + glyph_size + glyph_gap) if has_glyph else (accent_w + 6 + glyph_left_offset)

    # Left panel width
    label_pad_r = 9 if use_mono else 8
    left_panel = round(label_start + lw + label_pad_r)
    left_panel = max(left_panel, 30)

    # Label text center (midpoint of label area)
    label_area_end = left_panel - (6 if label_uppercase else 0)
    label_x = round((label_start + label_area_end) / 2, 1)

    # Indicator zone: reserved ONLY when this is a state-mode badge. Even
    # when the paradigm opts into indicators (show_indicator=True), version-
    # mode badges (pypi v0.2.5, etc.) don't render a ring+bit — reserving
    # the 16px allocation creates dead black space on the right side.
    # State-mode badges get the full allocation.
    badge_cfg = paradigm_spec.badge if paradigm_spec else None
    show_indicator = badge_cfg.show_indicator if badge_cfg is not None else True
    # State-mode inference happens below; pre-compute for indicator_alloc.
    state_set = {"passing", "warning", "critical", "building", "offline", "failing"}
    _is_state = spec.state in state_set and (not value_raw or value_raw == spec.state)
    indicator_alloc = (indicator_size + ind_pad_r) if (show_indicator and _is_state) else 0

    # Total width: left + sep/seam + right panel
    val_pad_l = 3
    val_min_gap = 3
    # Non-mono value text has letter-spacing .4 — add overshoot buffer
    ls_extra = len(value_raw) * 0.4 if not use_mono and value_raw else 0
    right_panel = val_pad_l + vw + ls_extra + 2 * val_min_gap + indicator_alloc
    total_w = round(left_panel + sep_w + seam_w + right_panel)
    total_w = max(total_w, 60)

    # Derived positions
    right_x = left_panel + sep_w + seam_w
    indicator_x = total_w - ind_pad_r - indicator_size
    value_x = round((right_x + val_pad_l + indicator_x) / 2, 1)
    text_y = round(height * text_y_factor, 1)
    # Indicator vertical center — pinned to value-text visual midline.
    # Cap height ≈ 70% of font size across Chakra Petch, Inter, and Orbitron
    # (validated against font metrics in data/font-metrics/), so the visual
    # center of uppercase glyphs = baseline (text_y) - 0.3 * font_size. The
    # indicator box is square; its top-y = visual_center - size/2. Computing
    # here (resolver) instead of in each paradigm template means every new
    # paradigm inherits correct vertical centering without re-deriving.
    indicator_y = round(text_y - _value_size * 0.3 - indicator_size / 2, 1)

    # State-badge inference: when state matches an ArtifactStatus and value
    # canonically mirrors state (value == state or empty), the badge is in
    # state-mode. Cellular templates branch on is_state_badge to render the
    # ring+bit indicator block and route value text through the state cascade.
    state_set = {"passing", "warning", "critical", "building", "offline", "failing"}
    is_state_badge = spec.state in state_set and (not value_raw or value_raw == spec.state)

    # Family resolution: user wins; empty falls back to paradigm default.
    resolved_variant = resolve_variant(spec, genome, paradigm_spec)

    # Profile visual context (envelope, well, specular, chrome text gradients)
    # is now applied universally by the dispatcher at resolve() via
    # _genome_material_context — no per-resolver call needed.
    return {
        "width": total_w,
        "height": height,
        "template": "frames/badge.svg.j2",
        "context": {
            "label": label_raw,
            "label_display": label_display,
            "value": value_raw,
            "left_panel_width": left_panel,
            "right_panel_x": right_x,
            "text_y": text_y,
            "glyph_x": glyph_x,
            "glyph_y": glyph_y,
            "glyph_render_size": glyph_size,
            "label_x": label_x,
            "value_x": value_x,
            "indicator_x": indicator_x,
            "indicator_y": indicator_y,
            "sep_width": sep_w,
            "seam_width": seam_w,
            "indicator_size": indicator_size,
            "accent_bar_width": accent_w,
            "has_glyph": has_glyph,
            "show_indicator": show_indicator,
            "use_mono": use_mono,
            "label_uppercase": label_uppercase,
            "inset": inset,
            "variant": resolved_variant,
            "is_state_badge": is_state_badge,
            "compact": spec.size == "compact",
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

    from hyperweave.core.cell_layout import TextSpec, compute_cell_layout
    from hyperweave.core.text import measure_text

    # Strip paradigm config is read here (once) so every downstream
    # measurement — identity, subtitle, metric labels, metric values —
    # uses the SAME paradigm fonts. No hardcoded fonts in this resolver.
    strip_cfg = paradigm_spec.strip if paradigm_spec else None
    height = strip_cfg.strip_height if strip_cfg else 52

    metrics = _parse_metrics(spec)
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
    cell_offset = 0

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
    if show_icon_box and has_glyph:
        # Icon box renders: pad + box + 8px post-box gap. Mirrors the
        # template's coordinate flow at strip.svg.j2:38-43, so the divider
        # x sits a consistent 14px past identity-text-end regardless of
        # whether the resolver or the template was the source of truth.
        glyph_zone = icon_box_pad + icon_box_size + 8
    elif show_icon_box:
        # No glyph: collapse the entire icon-box reservation; identity sits
        # flush at accent_w + icon_box_pad. Removes the empty 28x28 pocket
        # that used to render on glyphless cellular strips.
        glyph_zone = icon_box_pad
    elif has_glyph:
        glyph_zone = 36  # legacy brutalist/chrome: 12 pad + 24 glyph + gap
    else:
        glyph_zone = 0
    identity_x = accent_w + glyph_zone + (0 if show_icon_box else 14)

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
    # zone wider if subtitle is longer than identity.
    show_subtitle = strip_cfg.show_subtitle if strip_cfg else False
    subtitle_raw = ""
    subtitle_w = 0.0
    if show_subtitle and strip_cfg is not None:
        # Subtitle comes from connector_data.repo_slug / spec.value fallback.
        conn = spec.connector_data or {}
        subtitle_raw = str(conn.get("repo_slug") or conn.get("repo") or "")
        if subtitle_raw:
            _sub_size = strip_cfg.subtitle_font_size
            subtitle_w = measure_text(
                subtitle_raw,
                font_family=strip_cfg.subtitle_font_family,
                font_size=_sub_size,
                font_weight=400,
                letter_spacing_em=strip_cfg.subtitle_letter_spacing_em,
            )

    identity_zone_w = max(id_text_w, subtitle_w)
    first_divider_x = max(int(identity_x + identity_zone_w + 14), 80)  # 14px right padding, min 80

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
        cell_pad = strip_cfg.cell_pad
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

    # Status-indicator zone: tight-fit around the 14px indicator geometry.
    # Algorithmic sizing (pre_gap + indicator_size + post_gap) replaces the
    # former hardcoded 56px reserve, which left ~26px of dead black space
    # between the indicator and the right flank. Now: 16 pre-gap (matches
    # spec strip v10: last_seam=400 → frame_x=416) + 14 indicator + 4 post-gap.
    show_status_indicator = strip_cfg.show_status_indicator if strip_cfg else True
    _indicator_size = 14
    _indicator_pre_gap = 16
    # Post-indicator breathing. Paradigms with icon-boxes (cellular) now
    # mirror the pre-gap so the 14px indicator sits centered inside its
    # 46px status_zone — a consequence of dropping the ACTIVE text subtitle,
    # which previously required 29px of clearance for its 21px-wide glyphs.
    # Brutalist/chrome bare-diamond strips keep the tight 4px trailing gap.
    _indicator_post_gap = 16 if show_icon_box else 4
    status_zone = (_indicator_pre_gap + _indicator_size + _indicator_post_gap) if show_status_indicator else 0

    # Bifamily flank zones: paradigm declares flank_width > 0 when chromatic
    # flanking cells render at left/right edges (automata strips: 36px of
    # teal cells left, 36px amethyst right). Zero disables.
    flank_width = strip_cfg.flank_width if strip_cfg else 0
    flank_cell_size = strip_cfg.flank_cell_size if strip_cfg else 12
    has_flanks = flank_width > 0
    # Family resolution: user-specified ``--variant`` wins; empty falls back
    # to paradigm's frame_variant_defaults (cellular → bifamily for strip).
    resolved_variant = resolve_variant(spec, genome, paradigm_spec)

    n = max(len(metrics), 1)
    # If flanks are present, metric zones shift right by flank_width on each side
    # (flanks live OUTSIDE the content panel; width grows accordingly).
    flank_total = 2 * flank_width if has_flanks else 0
    metrics_zone_w = sum(cell_widths) if cell_widths else n * metric_pitch
    width = first_divider_x + cell_offset + metrics_zone_w + status_zone + flank_total

    # Seam positions: cumulative cell-edge x-coordinates for rimrun multi-seam tracing
    # AND for the per-cell trailing-divider lines emitted in strip.svg.j2. With
    # per-cell widths, seams are NOT evenly spaced; iterate cumulative widths.
    seam_offset = flank_width if has_flanks else 0
    seams = [first_divider_x + seam_offset]
    cell_start = first_divider_x + cell_offset + seam_offset
    _running = 0
    for cw in cell_widths:
        _running += cw
        seams.append(cell_start + _running)
    # Pad seams when cell_widths is empty (zero-metric strips) to preserve the
    # legacy single-divider seam list and avoid IndexError downstream.
    if not cell_widths:
        seams.append(cell_start + metric_pitch)

    # Status-indicator x-position: spec cellular-automata-strip-v10 places
    # the hw-state-frame at last_seam + 16 (NOT centered between last_seam
    # and content_right — that would leave a wide black gap in the flanked
    # layout). For genomes without flanks, last_seam + 16 still reads as
    # anchored-to-right-edge-of-metrics. content_right stays in context for
    # templates that want flank-boundary awareness for other uses.
    last_seam_x = seams[-1] if seams else first_divider_x
    content_right = width - (flank_width if has_flanks else 0)
    status_x = last_seam_x + 16 if show_status_indicator else 0

    # Glyph-zone x-offset: when bifamily flanks are present, the glyph must
    # be pushed past the left flank so it doesn't overlap pattern cells.
    # brutalist/chrome strips have flank_width=0 → no offset → unchanged.
    glyph_zone_x_offset = flank_width if has_flanks else 0

    ctx: dict[str, Any] = {
        "identity": identity,
        "identity_font_family": _id_family,
        "identity_font_size": _id_size,
        "identity_letter_spacing_em": _id_ls_em,
        "subtitle_text": subtitle_raw,
        "show_subtitle": show_subtitle,
        "subtitle_font_family": strip_cfg.subtitle_font_family if strip_cfg else "JetBrains Mono",
        "subtitle_font_size": strip_cfg.subtitle_font_size if strip_cfg else 6.5,
        "subtitle_letter_spacing_em": strip_cfg.subtitle_letter_spacing_em if strip_cfg else 0.0,
        "show_icon_box": show_icon_box,
        "icon_box_size": icon_box_size,
        "icon_box_pad": icon_box_pad,
        "metrics": metrics,
        "metric_pitch": metric_pitch,
        # Per-cell adaptive widths — sized to each metric's own content
        # (value or label, whichever is wider) + cell_pad. The strip
        # template iterates this list with a running x-offset so cells
        # sit flush-left against their content rather than padded inside
        # a uniform widest-cell pitch. See resolver.py per-cell-widths
        # section for rationale.
        "cell_widths": cell_widths,
        # Resolved per-cell layout records (one dict per metric, keyed by
        # CellLayout fields: cell_w, label_x, value_x, text_anchor, label_w,
        # value_w, content_w). The template renders these coordinates
        # verbatim — no template-side ``cell_w // 2`` arithmetic, no
        # paradigm-specific text-x branching. Adding a new paradigm with a
        # different text alignment is YAML-only.
        "cell_layouts": cell_layouts_records,
        # Shift into flank-shifted space so templates that render identity,
        # dividers, and metric cells all operate in the same coordinate system.
        # Seams already include the offset; first_divider_x previously didn't,
        # which caused the first divider to slice through the identity text
        # in bifamily strips (identity rendered at _gz_offset + accent + ...
        # in the template, but first_divider_x stayed flank-less). Adding
        # seam_offset reconciles both returns to the same frame-of-reference.
        "first_divider_x": first_divider_x + seam_offset,
        "seam_positions": seams,
        "status_x": status_x,
        "content_right": content_right,
        "glyph_zone_x_offset": glyph_zone_x_offset,
        "variant": resolved_variant,
        "show_status_indicator": show_status_indicator,
        "has_flanks": has_flanks,
        "flank_width": flank_width,
        "flank_cell_size": flank_cell_size,
        "strip_corner": profile.get("strip_corner", 5),
        # accent_width/accent_bar_width/has_accent reflect the same rule as
        # the local accent_w above: paradigms with show_icon_box zero out
        # the accent bar so downstream template math (identity_x, icon_box_x)
        # stays aligned with the specimen.
        "accent_width": accent_w,
        "accent_bar_width": accent_w,
        "divider_mode": profile.get("strip_divider_mode", "full"),
        "has_accent": accent_w > 0,
        "strip_glyph_size": profile.get("strip_glyph_size", 20),
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

    # Family resolution (cellular icon: monofamily, default blue).
    resolved_variant = resolve_variant(spec, genome, paradigm_spec)

    # Paradigm-driven viewBox override. Chrome paradigm sets viewbox_w/h=120
    # so the chrome icon templates can use the v2 specimen's 120-unit material
    # discipline at a 64px rendered size. Brutalist + others leave them at 0,
    # which document.svg.j2 falls back to width/height (viewBox = rendered size).
    icon_cfg = paradigm_spec.icon if paradigm_spec is not None else None
    viewbox_w = getattr(icon_cfg, "viewbox_w", 0) if icon_cfg is not None else 0
    viewbox_h = getattr(icon_cfg, "viewbox_h", 0) if icon_cfg is not None else 0

    ctx: dict[str, Any] = {
        "icon_shape": shape,
        "icon_rx": 0,
        "icon_label": icon_label,
        "icon_variant": icon_variant,
        "variant": resolved_variant,
        # Raw genome hex colors for gradient stops (CSS var() doesn't work in SVG stops)
        "genome_signal": genome.get("accent", "#845ef7"),
        "genome_surface": genome.get("surface_0", "#000000"),
        "genome_ink": genome.get("ink", "#ffffff"),
        "genome_border": genome.get("stroke", "#000000"),
        "genome_signal_dim": genome.get("accent_complement", "#A78BFA"),
        # viewBox overrides — zero means "use width/height" (handled by template default).
        "viewbox_w": viewbox_w,
        "viewbox_h": viewbox_h,
    }
    # Profile visual context now injected centrally by the dispatcher.

    return {
        "width": 64,
        "height": 64,
        "template": "frames/icon.svg.j2",
        "context": ctx,
    }


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
    _all_known_variants = _editorial_generics | {"dissolve", "band", "seam"}
    variant = spec.divider_variant if spec.divider_variant in _all_known_variants else "zeropoint"

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
    }
    w, h = variant_dims.get(variant, (700, 30))

    # Slug-interpolation template dispatch: genome-themed dividers live at
    # frames/divider/<genome>-<slug>.svg.j2. Falls back to the multi-branch
    # legacy template (handles editorial generics + dissolve).
    from hyperweave.render.templates import template_exists  # late import: avoid cycle

    genome_specific = f"frames/divider/{spec.genome_id}-{variant}.svg.j2"
    template = genome_specific if template_exists(genome_specific) else "frames/divider.svg.j2"

    ctx: dict[str, Any] = {
        "divider_variant": variant,
        "divider_label": spec.value or "",
        "variant": spec.variant or "bifamily",
        # Pass through chrome chromosomes so chrome-band template's envelope_stops
        # for-loop has data. brutalist-seam needs accent + accent_signal.
        "envelope_stops": genome.get("envelope_stops", []),
        "accent": genome.get("accent", ""),
        "accent_signal": genome.get("accent_signal", ""),
    }
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
    palette (cellular: bifamily teal/amethyst) and the paradigm's marquee
    config (separator glyph, live-block suppression) drive aesthetic dispatch
    inside ``_resolve_horizontal``.
    """
    # Family resolution (cellular marquee-horizontal: bifamily default).
    resolved_variant = resolve_variant(spec, genome, paradigm_spec)

    # ``_resolve_horizontal`` only needs signal_hex/surface_hex as hex-resolved
    # carriers for ``<stop>`` attributes (var() is unreliable inside SVG stops).
    # The rest of the profile visual context (envelope/well/etc.) is merged
    # universally by the dispatcher. Bifamily cellular marquees additionally
    # carry family-specific info hexes so ``_resolve_horizontal`` can generate
    # tspan-alternation scroll_items.
    chrome_ctx: dict[str, Any] = {
        "signal_hex": genome.get("accent", "#10B981"),
        "surface_hex": genome.get("surface_0", genome.get("surface", "#0A0A0A")),
        "variant": resolved_variant,
        "variant_blue_info": genome.get("variant_blue_seam_mid", ""),
        "variant_purple_info": genome.get("variant_purple_seam_mid", ""),
    }

    # Paradigm-declared marquee config — separator glyph, palette, live-block
    # suppression. Routed through ParadigmMarqueeConfig (defaults match the
    # historic brutalist/chrome behavior, so paradigms that don't declare
    # marquee config still render correctly).
    marquee_cfg = paradigm_spec.marquee if paradigm_spec is not None else None

    return _resolve_horizontal(spec, chrome_ctx, profile, marquee_cfg)


def _resolve_font_for_measurement(font_family_css: str) -> str:
    """Map a CSS font-family expression to a registry-resolvable font name.

    The browser resolves ``var(--dna-font-mono, ui-monospace, monospace)`` at
    runtime to the actual font (via the genome's CSS bridge — typically
    JetBrains Mono for chrome/brutalist/cellular genomes), but
    :func:`hyperweave.core.text.measure_text` can't see CSS variables. If a
    paradigm doesn't declare an explicit ``font_family`` in its marquee
    config, the resolver falls back to the profile's CSS-var-bearing default,
    measure_text fails to resolve it, and silently uses Inter metrics — which
    are ~20-30% narrower than monospace fonts. Layout positions then come out
    too tight, producing visible bullet-vs-text overlap.

    This helper closes that gap. It detects ``var(--dna-font-X, ...)``
    expressions and maps them to the actual font the browser will resolve to
    (per the genome's CSS bridge convention shipped in compose/assembler.py):

      ``var(--dna-font-display, ...)`` → ``Orbitron``
      ``var(--dna-font-mono, ...)``    → ``JetBrains Mono``
      anything else                    → first non-var fallback OR ``Inter``

    Non-var inputs pass through unchanged. Called at the boundary inside
    :func:`_layout_marquee_items` so EVERY layout call benefits — paradigms
    that already declare explicit fonts (chrome, brutalist) are unaffected;
    paradigms that fall through to the var() default (cellular, future ones)
    automatically get correct measurement.
    """
    s = (font_family_css or "").strip()
    if not s:
        return "Inter"
    if not s.startswith("var("):
        # Already a real font stack — return first comma-separated component
        # for measure_text (which handles the rest of the stack lookup).
        return s.split(",")[0].strip().strip("'\"")
    # var(--name, fallback...) — map by var name first.
    if "--dna-font-display" in s:
        return "Orbitron"
    if "--dna-font-mono" in s:
        return "JetBrains Mono"
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
    measurement_font = _resolve_font_for_measurement(font_family)

    laid: list[dict[str, Any]] = []
    x = float(start_x)

    def _w(text: str) -> float:
        # Wrap measure_text so call-sites stay short. font_weight is a single
        # value across the whole marquee (paradigm declares it); per-item
        # font-weight overrides are applied via the rendered tspan, not via
        # measurement (which doesn't change appreciably between 700 and 900).
        return measure_text(
            text,
            font_family=measurement_font,
            font_size=float(font_size),
            font_weight=font_weight,
            letter_spacing_em=letter_spacing_px / float(font_size) if font_size else 0.0,
        )

    for item in items:
        label = item.get("label", "")
        value = item["value"]
        # Each item — whether single-tspan (text role) or label+value pair —
        # gets ONE absolute x. The template emits child tspans inside a single
        # <text> element at this x; sibling tspans flow naturally with dx.
        laid.append({"type": "text", "x": int(x), "item": item})

        # Width contribution: label + (gap + value) when label present, else value alone.
        if label:
            x += _w(label) + label_value_gap + _w(value)
        else:
            x += _w(value)
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
            x += _w(separator_glyph) + item_gap

    return laid, int(x)


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
        font_weight_str = marquee_cfg.font_weight or ""
        letter_spacing_css = marquee_cfg.letter_spacing or ".5"
        font_family = marquee_cfg.font_family or _prof.get(
            "marquee_font_family", "var(--dna-font-mono, ui-monospace, monospace)"
        )
        separator_kind = marquee_cfg.separator_kind or "glyph"
        separator_size = int(marquee_cfg.separator_size) or 6
        separator_glyph = marquee_cfg.separator_glyph or "■"
        separator_color = marquee_cfg.separator_color or _prof.get("marquee_separator_color", "var(--dna-border)")
        text_fill_mode = marquee_cfg.text_fill_mode or "per_item"
        text_fill_gradient_id = marquee_cfg.text_fill_gradient_id or ""
        text_fill_cycle = list(marquee_cfg.text_fill_cycle)
        tspan_palette = list(marquee_cfg.tspan_palette)
        clip_inset_left = int(marquee_cfg.clip_inset_left)
        clip_inset_right = int(marquee_cfg.clip_inset_right)
        clip_inset_top = int(marquee_cfg.clip_inset_top)
        clip_inset_bottom = int(marquee_cfg.clip_inset_bottom)
        clip_rx = float(marquee_cfg.clip_rx)
    else:
        width, height = 800, 40
        font_size = 13
        font_weight_str = ""
        letter_spacing_css = ".5"
        font_family = _prof.get("marquee_font_family", "var(--dna-font-mono, ui-monospace, monospace)")
        separator_kind = "glyph"
        separator_size = 6
        separator_glyph = _prof.get("marquee_separator", "■")
        separator_color = _prof.get("marquee_separator_color", "var(--dna-border)")
        text_fill_mode = "per_item"
        text_fill_gradient_id = ""
        text_fill_cycle = []
        tspan_palette = []
        clip_inset_left = clip_inset_right = clip_inset_top = clip_inset_bottom = 0
        clip_rx = 0.0

    # Item ingestion: data-tokens preferred, title fallback.
    if spec.data_tokens:
        from hyperweave.serve.data_tokens import format_for_marquee

        formatted = format_for_marquee(spec.data_tokens)
        structured = [
            {"role": item["role"], "label": item["label"], "value": item["raw_value"] or item["text"]}
            for item in formatted
            if item.get("text")
        ]
        if not structured:
            structured = [{"role": "text", "label": "", "value": "HYPERWEAVE"}]
    else:
        items_text = spec.title or ""
        raw_items = [s.strip() for s in items_text.replace("·", "|").split("|") if s.strip()]
        if not raw_items:
            raw_items = [items_text] if items_text else ["HYPERWEAVE"]
        structured = [{"role": "text", "label": "", "value": t} for t in raw_items]

    # Per-item fills computed by mode. Each item gets its own value_color
    # (and label_color when label is present). Gradient mode emits the empty
    # string sentinel — the template substitutes the gradient URL.
    bold_pattern = _prof.get("marquee_horizontal_bold_pattern", "even")
    fam = chrome_ctx.get("variant", "")
    teal_info = chrome_ctx.get("variant_blue_info", "")
    amethyst_info = chrome_ctx.get("variant_purple_info", "")
    bifamily_active = fam == "bifamily" and bool(teal_info) and bool(amethyst_info) and bool(tspan_palette)

    # Default font_weight for measurement: paradigm-level value when set,
    # else 700 for items the bold-pattern picks (matches historic behavior).
    measure_weight = int(font_weight_str) if font_weight_str.isdigit() else 400

    items_for_layout: list[dict[str, Any]] = []
    for i, item in enumerate(structured):
        # Mode dispatch — determines value_color / label_color / font_weight.
        if text_fill_mode == "gradient":
            # Single uniform gradient applied to every item; the template
            # constructs `fill="url(#{uid}-{text_fill_gradient_id})"` when
            # `value_color` is the empty string.
            value_color = ""
            label_color = ""
            fw = font_weight_str
        elif text_fill_mode == "cycle" and text_fill_cycle:
            value_color = text_fill_cycle[i % len(text_fill_cycle)]
            label_color = value_color  # cycle paradigms use one color per item
            fw = font_weight_str
        elif bifamily_active:
            palette = [teal_info, amethyst_info]
            value_color = palette[i % len(palette)]
            label_color = value_color
            fw = font_weight_str or "700"
        else:
            # per_item legacy: ink-primary/secondary alternation, label muted.
            value_color = "var(--dna-ink-primary)" if i % 2 == 0 else "var(--dna-ink-secondary, var(--dna-ink-muted))"
            label_color = "var(--dna-ink-muted)"
            fw = font_weight_str or (
                "700" if (bold_pattern == "first" and i == 0) or (bold_pattern == "even" and i % 2 == 0) else ""
            )

        items_for_layout.append(
            {
                "role": item["role"],
                "label": item["label"],
                "value": item["value"],
                "value_color": value_color,
                "label_color": label_color,
                "font_weight": fw,
            }
        )

    # Layout: compute absolute x positions + content_end_x.
    letter_spacing_px = _parse_letter_spacing_px(letter_spacing_css, float(font_size))
    item_gap = 20  # historical inter-item breathing room
    label_value_gap = 8  # gap between label tspan and value tspan within a kv/live item
    start_x = 16  # left padding inside the scroll viewport (matches chrome specimen translate(16, …))
    laid_out, content_end_x = _layout_marquee_items(
        items_for_layout,
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
    )

    # Seamless-loop sizing: repeat items inside Set-A enough times that
    # Set-A's content_end_x covers the viewport. The single-cycle layout
    # above tells us the natural period; if that period is smaller than the
    # viewport, we'd otherwise have a visible empty gap at the loop boundary
    # (Set-A scrolls off, viewport shows empty space until Set-B catches up).
    # Repeating items so layout_width >= viewport_width keeps the viewport
    # full at all times; scroll_distance still equals the full layout width
    # (R x single_period) so Set-B at translate(scroll_distance, 0) picks up
    # exactly one full Set-A worth of content past Set-A's trailing separator.
    import math

    single_period = max(content_end_x - start_x, 1)
    repetitions = max(1, math.ceil(width / single_period))
    if repetitions > 1:
        items_repeated = items_for_layout * repetitions
        laid_out, content_end_x = _layout_marquee_items(
            items_repeated,
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
        )

    # scroll_distance: one full Set-A worth = content_end_x - start_x =
    # R x single_period. The layout helper added a trailing separator after
    # every item, so the boundary gap (last sep end to Set-B first item start)
    # equals item_gap — identical to every within-set sep-to-item gap. SMIL's
    # frame-boundary jump from translate(-sd, 0) back to translate(0, 0) is
    # visually invisible because the periodic strip pattern looks identical
    # at both states.
    base_speed = 90.2
    speed = spec.marquee_speeds[0] if spec.marquee_speeds else 1.0
    scroll_distance = content_end_x - start_x
    scroll_dur = round(scroll_distance / (base_speed * speed), 2)

    ctx: dict[str, Any] = {
        "direction": spec.marquee_direction,
        "scroll_items": laid_out,
        "scroll_distance": scroll_distance,
        "scroll_dur": scroll_dur,
        "scroll_start_x": start_x,
        # Paradigm-driven typography (template renders these as <text> attrs).
        "font_size": font_size,
        "font_weight": font_weight_str,
        "letter_spacing": letter_spacing_css,
        "scroll_font_family": font_family,
        # Separator config (template branches on separator_kind).
        "separator_kind": separator_kind,
        "separator_size": separator_size,
        "separator_glyph": separator_glyph,
        "separator_color": separator_color,
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
# + label), because they chose a palette, not a different agent. Phase D's
# skin-keyed mapping conflated these two axes; this reverts to runtime-keyed.
_PROVIDER_BY_RUNTIME: dict[str, tuple[str, str | None]] = {
    "claude-code": ("Claude Code", "claude-glyph"),
    "codex": ("Codex", "codex-glyph"),
}


def _resolve_provider(runtime: str) -> tuple[str, str | None]:
    """Map JSONL runtime field to (provider_label, glyph_id) for the hero brand line.

    Returns (``"HyperWeave"``, ``None``) when runtime is empty or unknown —
    the glyph slot stays empty and the brand line falls back to the project
    name. Branded runtimes (``claude-code``, ``codex``) carry an explicit
    identity package regardless of which palette skin is active.
    """
    return _PROVIDER_BY_RUNTIME.get(runtime, ("HyperWeave", None))


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


def _active_window_minutes(stages: list[dict[str, Any]], fallback_m: float) -> float:
    """Active work duration in minutes, bounded by both sum and wall-clock.

    Returns ``min(sum_of_stage_durations, wall_clock_first_to_last)``:
      * Sum_of_stages handles idle gaps — sessions left open across multiple
        bursts over days resolve to actual work hours, not wall-clock days.
      * Wall-clock cap handles overlapping/async stages — when stage end
        timestamps extend past the last visible session message (async tool
        completion), the sum can exceed the wall-clock first→last span.
        Without the cap, the chart axis disagrees with the hero subline.

    Both are stage-derived, so the chart and hero see the same number from
    the same primary source (stage timestamps) — never from the parser's
    ``duration_minutes`` which can be unreliable.

    Returns ``fallback_m`` when stages lack ISO timestamps (mock data) or
    when parsing fails.
    """
    if not stages:
        return fallback_m
    durations: list[float] = []
    starts: list[datetime] = []
    ends: list[datetime] = []
    for s in stages:
        start = s.get("start")
        end = s.get("end")
        if not start or not end:
            return fallback_m
        try:
            t0 = datetime.fromisoformat(start)
            t_end = datetime.fromisoformat(end)
        except (ValueError, TypeError):
            return fallback_m
        starts.append(t0)
        ends.append(t_end)
        durations.append((t_end - t0).total_seconds() / 60.0)
    sum_m = sum(durations)
    wall_clock_m = (max(ends) - min(starts)).total_seconds() / 60.0
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


# ── Tier styling table for the treemap (Phase B template thinness) ──
# All tier-derived font sizes, x offsets, and accent widths live here so
# the receipt template iterates cells without branching on tier. The
# values are derived from tier 1 / 2 / 3 visual hierarchy in the v9
# specimens (claude-code-ledger as the canonical reference).
_TREEMAP_TIER_STYLES: dict[int, dict[str, Any]] = {
    1: {
        "accent_w": 4,
        "label_x": 14,
        "label_size": 13,
        "detail_x": 14,
        "detail_y": 72,
        "detail_size": 10,
        "error_size": 9,
        "error_pad": 8,
        "pct_size": 36,
        "pct_y": 58,
    },
    2: {
        "accent_w": 3,
        "label_x": 10,
        "label_size": 10,
        "detail_x": 10,
        "detail_y": 24,
        "detail_size": 8,
        "error_size": 8,
        "error_pad": 8,
        "pct_size": 0,  # tier 2/3 omit the big-pct block
        "pct_y": 0,
    },
    3: {
        "accent_w": 3,
        "label_x": 9,
        "label_size": 9,
        "detail_x": 9,
        "detail_y": 19,
        "detail_size": 8,
        "error_size": 8,
        "error_pad": 7,
        "pct_size": 0,
        "pct_y": 0,
    },
}


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
    duration_m = session.get("duration_minutes", 0)
    # Active window: bounded by both sum-of-stages (collapses idle gaps) and
    # wall-clock span (caps overlapping/async stages). Same value drives the
    # chart geometry AND the hero subline, so they always agree.
    active_duration_m = _active_window_minutes(stages, float(duration_m))
    wall_clock_m = _wall_clock_minutes(stages, float(duration_m))
    # ``total`` for the divergence flag: max of parser-reported duration and
    # the stage-derived wall-clock. The parser may overstate (idle tail) or
    # understate (async stages); max() picks whichever is more honest.
    total_duration_m = max(float(duration_m), wall_clock_m)
    model = session.get("model", profile_data.get("model", "Claude Session"))
    calls = sum(t.get("count", 0) for t in tools)

    # ── Tool class mapping ──
    _TOOL_CLASS: dict[str, str] = {
        "Read": "explore",
        "Glob": "explore",
        "Grep": "explore",
        "Bash": "execute",
        "Edit": "mutate",
        "Write": "mutate",
        "Agent": "coordinate",
        "Task": "coordinate",
        "TaskCreate": "coordinate",
        "TaskUpdate": "coordinate",
        "Spawn": "coordinate",
        "Send": "coordinate",
    }

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

    # v0.2.21 risograph hero treatment: split headline into tokens part +
    # signal-colored cost part so the template can render them as separate
    # tspans (cost in var(--dna-signal) per the spec).
    headline_tokens = f"{_fmt_tok(total_tok)} tokens billed · "
    headline_cost = f"${total_cost:.2f}"
    hero_headline = f"{headline_tokens}{headline_cost}"  # legacy single-string for fallback
    # Divergence flag: when active work is < half the total session window,
    # surface both numbers so "session left open" cases are honest. Otherwise
    # the chart's axis (active_duration_m) and the hero label always agree.
    if total_duration_m and active_duration_m < 0.5 * total_duration_m:
        dur_label = f"{int(active_duration_m)}m active · {int(total_duration_m)}m total"
    elif active_duration_m:
        dur_label = f"{int(active_duration_m)}m"
    else:
        dur_label = "—"
    hero_subline = f"{dur_label} · {calls} calls · {len(stages)} stages"
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
    # Split "pushbacks" into distinct signals so the card stops labeling them
    # as one opaque "N corrections" lie. user_events counts every non-continuation
    # user turn (corrections + redirects + elaborations); tool errors count
    # failing/blocked tool calls (the red ✗N cell marks reconcile to this).
    n_user_turns = len(user_events)
    n_tool_errors = sum(t.get("errors", 0) + t.get("blocked", 0) for t in tools)
    # n_agents = len(agents)  # was used by old footer; v0.2.21 footer is 4-quadrant.
    _ = agents  # keep the extraction for forward use without lint warnings
    hero_right: list[dict[str, Any]] = [
        {"text": f"{_fmt_tok(total_input)} in / {_fmt_tok(total_output)} out", "accent": ""},
    ]
    if total_cache_read or total_cache_create:
        hero_right.append(
            {
                "text": f"{_fmt_tok(total_cache_read)} cached / {_fmt_tok(total_cache_create)} written",
                "accent": "",
            },
        )
    pushback_parts: list[str] = []
    if n_user_turns:
        pushback_parts.append(f"{n_user_turns} user turn{'s' if n_user_turns != 1 else ''}")
    if n_tool_errors:
        pushback_parts.append(f"{n_tool_errors} tool errors")
    if pushback_parts:
        hero_right.append(
            {
                "text": " · ".join(pushback_parts),
                "accent": "failing" if n_tool_errors else "",
            },
        )

    # Pre-compute hero-right y-offsets so the template doesn't need loop math.
    for i, stat in enumerate(hero_right):
        stat["y"] = 56 + (i * 14)

    # ── Treemap layout — delegated to compose/treemap.py ──
    # Centralized in v0.2.21 to fix two arithmetic bugs that caused tier-3
    # cells (TaskCreate / ExitPlanMode / AskUserQuestion) to clip the right
    # edge of the receipt. The helper also applies label truncation and
    # synthesizes a "+N more" cell when the tool count exceeds what fits
    # at the tier-3 minimum width. See compose/treemap.py for the algorithm.
    content_w = 752
    classified_tools = [
        {**t, "tool_class": t.get("tool_class") or _TOOL_CLASS.get(t.get("name", ""), "explore")} for t in tools
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

    # ── Rhythm panel — risograph-canonical structure (v0.2.21) ──
    # The bar_chart helper returns a BarChartLayout dataclass bundling
    # bars + error_ticks (separate band) + peak_marker + grid_lines +
    # header labels + counts. All geometry derives from the panel_h
    # parameter (single source of truth) so the y=-1 overflow bug from
    # Phase D's independently-hardcoded constants can't recur.
    panel_h = 130
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

    # Treemap header row chips: 4 fixed-position 2x8 swatches + labels per spec.
    # Always renders all four standard classes (coordinate/execute/explore/mutate)
    # so the legend is stable across sessions; absent classes still appear so
    # cross-session comparison stays consistent.
    treemap_header_chips = [
        {"tool_class": "coordinate", "label": "coordinate", "x": 96},
        {"tool_class": "execute", "label": "execute", "x": 170},
        {"tool_class": "explore", "label": "explore", "x": 232},
        {"tool_class": "mutate", "label": "mutate", "x": 292},
    ]

    # Rhythm-panel legend: 4 tool swatches + error-tick swatch + DOMINANT label.
    # Each entry has pre-computed x-offset for the template to consume directly.
    phase_legend: list[dict[str, Any]] = [
        {"id": "coordinate", "label": "coordinate", "x": 0, "kind": "tool"},
        {"id": "execute", "label": "execute", "x": 82, "kind": "tool"},
        {"id": "explore", "label": "explore", "x": 152, "kind": "tool"},
        {"id": "mutate", "label": "mutate", "x": 220, "kind": "tool"},
        {"id": "error_tick", "label": "error tick", "x": 290, "kind": "error"},
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
    receipt_path = f".hyperweave/receipts/{session_id}.svg" if session_id else ""

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

    # v0.2.21 footer swap: BL now reflects session work intensity (user turns +
    # tool errors), BR carries the brand mark. Matches the risograph spec layout.
    footer_bl_parts: list[str] = []
    if n_user_turns:
        footer_bl_parts.append(f"{n_user_turns} user turn{'s' if n_user_turns != 1 else ''}")
    if n_tool_errors:
        footer_bl_parts.append(f"{n_tool_errors} tool error{'s' if n_tool_errors != 1 else ''}")
    footer_bl = " · ".join(footer_bl_parts) if footer_bl_parts else ""
    footer_br = "hyperweave.app"

    return {
        "width": 800,
        "height": 500,
        "template": "frames/receipt.svg.j2",
        "context": {
            "telemetry": tel,
            # Hero zone (v0.2.21 risograph-canonical)
            "provider_label": provider_label,
            "glyph_id": glyph_id,
            "has_glyph": bool(glyph_id),
            "model_label": model_label,
            "hero_profile": hero_profile,
            "hero_tool_class": hero_tool_class,
            "hero_headline": hero_headline,
            "headline_tokens": headline_tokens,
            "headline_cost": headline_cost,
            "hero_subline": hero_subline,
            "hero_right_stats": hero_right,
            "pill_label": pill_label,
            "pill_w": pill_w,
            "pill_x": pill_x,
            # Pill corner radius — genome-token driven (0=square, 11=full pill).
            # SVG2 auto-clamps rx to min(rx, height/2): inner rect (h=18) caps
            # at 9, outer rect (h=22) caps at 11. Both fully rounded at half-h.
            "pill_rx": genome.get("pill_rx", 4),
            "content_w": content_w,
            # Treemap panel
            "treemap_subtitle": treemap_subtitle,
            "treemap_legend": treemap_legend,
            "treemap_header_chips": treemap_header_chips,
            "treemap_cells": treemap_cells,
            "tier_styles": _TREEMAP_TIER_STYLES,
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
            "bar_area_h": bar_area_h,
            "time_axis_ticks": time_axis_ticks,
            "duration_minutes": int(duration_m),
            "phase_legend": phase_legend,
            "dominant_profile": f"{dominant_label} ({dominant_pct}%)",
            # Geometric constants pre-computed for the v0.2.21 thin-render template.
            # All derive from panel_h=130 in compose/bar_chart.py (single source).
            "content_right_x": 800 - 24,
            "inner_w": 800 - 1,
            "inner_h": 500 - 1,
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
        {"tool_class": "explore", "label": "EXP", "x": 0},
        {"tool_class": "execute", "label": "EXE", "x": 28},
        {"tool_class": "mutate", "label": "MUT", "x": 56},
        {"tool_class": "coordinate", "label": "CRD", "x": 84},
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

    return {
        "width": 600,
        "height": 92,
        "template": "frames/rhythm-strip.svg.j2",
        "context": {
            "telemetry": tel,
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
        },
    }


def resolve_master_card(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve telemetry master card — specimen-faithful layout.

    Computes: hero summary, session history sparkline, burn curve,
    codebase heatmap, skill tracker.
    Specimen: specs/telemetry-artifacts/mastercard.svg (800x900)
    """
    tel: dict[str, Any] = dict(spec.telemetry_data or {})
    session: dict[str, Any] = tel.get("session", {})
    tokens_data: dict[str, Any] = tel.get("tokens", {})
    cost_data: dict[str, Any] = tel.get("cost", {})
    tools: list[dict[str, Any]] = tel.get("tools", [])
    sessions: list[dict[str, Any]] = tel.get("sessions", [])
    files: list[dict[str, Any]] = tel.get("files", [])
    skills: list[dict[str, Any]] = tel.get("skills", [])

    total_tok = tokens_data.get("input", 0) + tokens_data.get("output", 0)
    total_cost = cost_data.get("total", 0)
    calls = sum(t.get("count", 0) for t in tools) if tools else 0
    n_sessions = len(sessions) if sessions else 1
    model = session.get("model", "Claude Session")

    # ── Session history sparkline bars (752px wide) ──
    content_w = 752
    history_bars: list[dict[str, Any]] = []
    if sessions:
        max_tok = max(s.get("tokens", 0) for s in sessions) or 1
        bar_w = max(int(content_w / len(sessions)) - 3, 4)
        for i, s in enumerate(sessions):
            tok = s.get("tokens", 0)
            h = max(int(144 * tok / max_tok), 2)
            health = "signal" if s.get("corrections", 0) == 0 else "warning"
            if tok > max_tok * 0.8:
                health = "failing"
            history_bars.append(
                {
                    "x": i * (bar_w + 3),
                    "y": 144 - h,
                    "w": bar_w,
                    "h": h,
                    "health": health,
                    "label": s.get("label", ""),
                }
            )

    # ── Heatmap rows ──
    heatmap_rows: list[dict[str, Any]] = []
    if files:
        max_reads = max(f.get("reads", 0) for f in files) or 1
        for f in files[:10]:
            reads = f.get("reads", 0)
            writes = f.get("writes", 0)
            intensity = min(int(reads / max_reads * 4), 4)
            heatmap_rows.append(
                {
                    "path": f.get("path", ""),
                    "reads": reads,
                    "writes": writes,
                    "bar_w": int(200 * reads / max_reads),
                    "intensity": intensity,
                    "last": f.get("last", ""),
                }
            )

    # ── Skill bars ──
    skill_bars: list[dict[str, Any]] = []
    for s in skills:
        attempts = s.get("attempts", 0)
        accepted = s.get("accepted", 0)
        pct = round(accepted / attempts * 100, 1) if attempts > 0 else 0
        skill_bars.append(
            {
                "name": s.get("name", ""),
                "lang": s.get("lang", ""),
                "attempts": attempts,
                "accepted": accepted,
                "pct": pct,
                "state": s.get("state", "learning"),
                "bar_w": int(336 * pct / 100),
            }
        )

    return {
        "width": 800,
        "height": 900,
        "template": "frames/master-card.svg.j2",
        "context": {
            "telemetry": tel,
            "mc_title": f"{_fmt_tok(total_tok)} tokens · ${total_cost:.2f}",
            "mc_subtitle": f"{model} · {n_sessions} sessions",
            "mc_total_tokens": f"{calls} calls",
            "mc_total_cost": f"${total_cost:.2f} total",
            "mc_session_count": n_sessions,
            "session_entries": sessions,
            "history_bars": history_bars,
            "burn_session_id": session.get("id", session.get("model", "latest")),
            "heatmap_file_count": len(files),
            "heatmap_rows": heatmap_rows,
            "skills": skill_bars,
            "footer_left": "hyperweave.app",
            "footer_right": f"{model}",
        },
    }


def resolve_catalog(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve editorial catalog."""
    return {
        "width": 800,
        "height": 400,
        "template": "frames/catalog.svg.j2",
        "context": {},
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
    try:
        from hyperweave.config.settings import get_settings
        from hyperweave.render.glyphs import infer_glyph, load_glyphs

        settings = get_settings()
        glyphs = load_glyphs(settings.data_dir / "glyphs.json")

        glyph_id = spec.glyph
        if not glyph_id and spec.glyph_mode != GlyphMode.NONE:
            glyph_id = infer_glyph(spec.title or "")

        if glyph_id and glyph_id in glyphs:
            g = glyphs[glyph_id]
            return {
                "id": glyph_id,
                "path": g["path"],
                "viewBox": g.get("viewBox", "0 0 640 640"),
            }
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


def _load_terminal(terminal_id: str) -> dict[str, Any]:
    try:
        from hyperweave.config.loader import get_loader

        loader = get_loader()
        return loader.terminals.get(terminal_id, {"id": terminal_id, "svg_fragment": ""})
    except (ImportError, Exception):
        return {"id": terminal_id, "svg_fragment": ""}


def _load_rule(rule_id: str) -> dict[str, Any]:
    try:
        from hyperweave.config.loader import get_loader

        loader = get_loader()
        return loader.rules.get(rule_id, {"id": rule_id, "svg_fragment": ""})
    except (ImportError, Exception):
        return {"id": rule_id, "svg_fragment": ""}


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
    corner_raw = str(genome.get("corner", "4px")).replace("px", "")
    return {
        "envelope_stops": genome.get("envelope_stops", []),
        "well_top": genome.get("well_top", ""),
        "well_bottom": genome.get("well_bottom", ""),
        # Icon-specific well colors (v0.2.16): chrome icons use a more saturated
        # navy (#0C1E2E -> #06101A per v2 spec) than the wider marquee/strip
        # well (#020617 -> #0B1121). Falls back to well_top/well_bottom when not
        # declared, so non-chrome genomes don't need these fields.
        "icon_well_top": genome.get("icon_well_top", "") or genome.get("well_top", ""),
        "icon_well_bottom": genome.get("icon_well_bottom", "") or genome.get("well_bottom", ""),
        "specular_light": genome.get("highlight_color", ""),
        "highlight_opacity": genome.get("highlight_opacity", ""),
        "bevel_shadow_opacity": genome.get("shadow_opacity", ""),
        "chrome_corner": corner_raw,
        "chrome_text_gradient": genome.get("chrome_text_gradient", []),
        "hero_text_gradient": genome.get("hero_text_gradient", []),
        "chrome_rhythm": genome.get("rhythm_base", ""),
        "glyph_fill": genome.get("glyph_inner", ""),
        "light_mode": genome.get("light_mode"),
        # Automata bifamily palettes (surfaced for cellular paradigm templates).
        "variant_blue_rim_stops": genome.get("variant_blue_rim_stops", []),
        "variant_blue_pattern_cells": genome.get("variant_blue_pattern_cells", []),
        "variant_blue_seam_mid": genome.get("variant_blue_seam_mid", ""),
        "variant_blue_label_slab_fill": genome.get("variant_blue_label_slab_fill", ""),
        "variant_blue_label_text": genome.get("variant_blue_label_text", ""),
        "variant_blue_value_text": genome.get("variant_blue_value_text", ""),
        "variant_blue_canvas_top": genome.get("variant_blue_canvas_top", ""),
        "variant_blue_canvas_bottom": genome.get("variant_blue_canvas_bottom", ""),
        "variant_purple_rim_stops": genome.get("variant_purple_rim_stops", []),
        "variant_purple_pattern_cells": genome.get("variant_purple_pattern_cells", []),
        "variant_purple_seam_mid": genome.get("variant_purple_seam_mid", ""),
        "variant_purple_label_slab_fill": genome.get("variant_purple_label_slab_fill", ""),
        "variant_purple_label_text": genome.get("variant_purple_label_text", ""),
        "variant_purple_value_text": genome.get("variant_purple_value_text", ""),
        "variant_purple_canvas_top": genome.get("variant_purple_canvas_top", ""),
        "variant_purple_canvas_bottom": genome.get("variant_purple_canvas_bottom", ""),
        "variant_bifamily_bridge_teal_mid": genome.get("variant_bifamily_bridge_teal_mid", ""),
        "variant_bifamily_bridge_teal_deep": genome.get("variant_bifamily_bridge_teal_deep", ""),
        "variant_bifamily_bridge_amethyst_core": genome.get("variant_bifamily_bridge_amethyst_core", ""),
        "variant_bifamily_bridge_amethyst_bright": genome.get("variant_bifamily_bridge_amethyst_bright", ""),
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
