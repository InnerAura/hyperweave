"""Spec resolver -- resolves genome, profile, frame, glyph, motion for each frame type."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hyperweave.compose.rhythm import layout_rhythm_bars
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


_TELEMETRY_FRAMES: frozenset[str] = frozenset({FrameType.RECEIPT, FrameType.RHYTHM_STRIP, FrameType.MASTER_CARD})


def resolve(spec: ComposeSpec) -> ResolvedArtifact:
    """Resolve a ComposeSpec into a typed ResolvedArtifact."""
    # Telemetry frames always use the telemetry-void genome (specimen palette).
    # Genome skinning is deferred until templates faithfully reproduce specimens.
    if spec.type in _TELEMETRY_FRAMES:
        genome = _load_genome("telemetry-void")
        profile = _load_profile(genome.get("profile", "brutalist"))
    else:
        # Session 2A+2B: genome_override bypasses the registry (used by --genome-file).
        genome = _load_genome(spec.genome_id, override=spec.genome_override)
        profile = _load_profile(genome.get("profile", spec.profile_id))
    glyph_data = _resolve_glyph(spec)
    motion = _resolve_motion(spec, genome)

    # Session 2A+2B: new resolvers live in compose/resolvers/ per Invariant 10.
    from hyperweave.compose.resolvers.chart import resolve_chart
    from hyperweave.compose.resolvers.stats import resolve_stats
    from hyperweave.compose.resolvers.timeline import resolve_timeline

    # Dispatch to frame-specific resolver
    frame_resolvers: dict[str, Any] = {
        "badge": resolve_badge,
        "strip": resolve_strip,
        "banner": resolve_banner,
        "icon": resolve_icon,
        "divider": resolve_divider,
        "marquee-horizontal": resolve_marquee,
        "marquee-vertical": resolve_marquee,
        "marquee-counter": resolve_marquee,
        "receipt": resolve_receipt,
        "rhythm-strip": resolve_rhythm_strip,
        "master-card": resolve_master_card,
        "catalog": resolve_catalog,
        "chart": resolve_chart,
        "stats": resolve_stats,
        "timeline": resolve_timeline,
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
    # Replaces 8 manual _genome_material_context(...) calls previously scattered
    # across badge/strip/banner/icon/divider/marquee/stats/chart resolvers —
    # the forgetting of which caused Bug D (stats + chart rendered chrome-horizon
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
    compact = spec.variant == "compact"
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
    resolved_family = spec.family
    if not resolved_family and paradigm_spec is not None:
        family_defaults = getattr(paradigm_spec, "frame_family_defaults", {}) or {}
        resolved_family = family_defaults.get(spec.type, "")

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
            "family": resolved_family,
            "is_state_badge": is_state_badge,
            "compact": spec.variant == "compact",
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
    # resolve_banner, resolve_marquee): each resolver pulls only what it
    # needs at the call site.
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
    # Family resolution: user-specified ``--family`` wins; empty falls back
    # to paradigm's frame_family_defaults (cellular → bifamily for strip).
    resolved_family = spec.family
    if not resolved_family and paradigm_spec is not None:
        family_defaults = getattr(paradigm_spec, "frame_family_defaults", {}) or {}
        resolved_family = family_defaults.get(spec.type, "")

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
        "family": resolved_family,
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


def resolve_banner(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    paradigm_spec: Any = None,
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve banner dimensions.

    Full variant: 1200x600, 3-column editorial grid, 160px hero text.
    Compact variant: 800x220, no grid, 42px text.
    """
    compact = spec.variant == "compact"
    # Banner dims: paradigm-driven (cellular specimen is 800x220 for both
    # variants; brutalist/chrome keep 1200x600 full / 800x220 compact).
    banner_cfg = paradigm_spec.banner if paradigm_spec else None
    if banner_cfg is not None:
        w = banner_cfg.width_compact if compact else banner_cfg.width_default
        h = banner_cfg.height_compact if compact else banner_cfg.height_default
    else:
        w = 800 if compact else 1200
        h = 220 if compact else profile.get("banner_height", 600)

    genome_name = genome.get("name", spec.genome_id)
    footer = genome_name.upper()

    from hyperweave.core.text import measure_text

    title = spec.title or "HYPERWEAVE"
    base_fs = 42 if compact else 160
    max_width = (w - 80) if compact else (w - 120)  # margin each side

    # Scale font size down if title overflows available width
    text_w = measure_text(title, font_family="Inter", font_size=base_fs, font_weight=700)
    ls_reduction = 0.04 * base_fs * max(len(title) - 1, 0)  # -0.04em letter-spacing
    effective_w = text_w - ls_reduction
    title_fs = max(int(base_fs * max_width / effective_w), 42) if effective_w > max_width else base_fs

    # Family resolution (cellular banner: bifamily default).
    resolved_family = spec.family
    if not resolved_family and paradigm_spec is not None:
        family_defaults = getattr(paradigm_spec, "frame_family_defaults", {}) or {}
        resolved_family = family_defaults.get(spec.type, "")

    ctx: dict[str, Any] = {
        "banner_title": title,
        "banner_subtitle": spec.value or "subtitle",
        "banner_label": footer,
        "banner_variant": "compact" if compact else "full",
        "title_font_size": title_fs,
        "family": resolved_family,
    }
    # Profile visual context now injected centrally by the dispatcher.

    return {
        "width": w,
        "height": h,
        "template": "frames/banner.svg.j2",
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
    resolved_family = spec.family
    if not resolved_family and paradigm_spec is not None:
        family_defaults = getattr(paradigm_spec, "frame_family_defaults", {}) or {}
        resolved_family = family_defaults.get(spec.type, "")

    ctx: dict[str, Any] = {
        "icon_shape": shape,
        "icon_rx": 0,
        "icon_label": icon_label,
        "icon_variant": icon_variant,
        "family": resolved_family,
        # Raw genome hex colors for gradient stops (CSS var() doesn't work in SVG stops)
        "genome_signal": genome.get("accent", "#845ef7"),
        "genome_surface": genome.get("surface_0", "#000000"),
        "genome_ink": genome.get("ink", "#ffffff"),
        "genome_border": genome.get("stroke", "#000000"),
        "genome_signal_dim": genome.get("accent_complement", "#A78BFA"),
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
    """Resolve divider dimensions using specimen variants."""
    _specimen_variants = {"block", "current", "takeoff", "void", "zeropoint", "cellular-dissolve"}
    variant = spec.divider_variant if spec.divider_variant in _specimen_variants else "zeropoint"
    variant_dims: dict[str, tuple[int, int]] = {
        "block": (700, 80),
        "current": (700, 40),
        "takeoff": (700, 100),
        "void": (700, 40),
        "zeropoint": (700, 30),
        "cellular-dissolve": (800, 28),
    }
    w, h = variant_dims.get(variant, (700, 30))

    ctx: dict[str, Any] = {
        "divider_variant": variant,
        "divider_label": spec.value or "",
        "family": spec.family or "bifamily",
    }
    # Profile visual context now injected centrally by the dispatcher.

    return {
        "width": w,
        "height": h,
        "template": "frames/divider.svg.j2",
        "context": ctx,
    }


def resolve_marquee(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    paradigm_spec: Any = None,
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve marquee dimensions and content.

    Three variants:
      counter    — 800x140, tri-band R/L/R, per-row heterogeneous content
      vertical   — 400x268, telemetry feed with timestamped events
      horizontal — 800x40,  LIVE ticker with brand items
    """
    # Family resolution (cellular marquee-horizontal: bifamily default).
    resolved_family = spec.family
    if not resolved_family and paradigm_spec is not None:
        family_defaults = getattr(paradigm_spec, "frame_family_defaults", {}) or {}
        resolved_family = family_defaults.get(spec.type, "")

    # Marquee sub-resolvers only need signal_hex/surface_hex as hex-resolved
    # carriers for <stop> attributes (var() is unreliable inside SVG stops).
    # The rest of the profile visual context (envelope/well/etc.) is merged
    # universally by the dispatcher, so no longer needed here. Bifamily
    # cellular marquees additionally carry family-specific info hexes so
    # _resolve_horizontal can generate tspan-alternation scroll_items.
    chrome_ctx: dict[str, Any] = {
        "signal_hex": genome.get("accent", "#10B981"),
        "surface_hex": genome.get("surface_0", genome.get("surface", "#0A0A0A")),
        "family": resolved_family,
        "family_blue_info": genome.get("family_blue_seam_mid", ""),
        "family_purple_info": genome.get("family_purple_seam_mid", ""),
    }

    # Paradigm-declared marquee config — separator glyph, palette, live-block
    # suppression. Routed through ParadigmMarqueeConfig (defaults match the
    # historic brutalist/chrome behavior, so paradigms that don't declare
    # marquee config still render correctly). All three sub-resolvers read
    # from this config, not from hardcoded paradigm-coupled values.
    marquee_cfg = paradigm_spec.marquee if paradigm_spec is not None else None

    if spec.type == FrameType.MARQUEE_COUNTER:
        return _resolve_counter(spec, chrome_ctx, profile, marquee_cfg)

    if spec.type == FrameType.MARQUEE_VERTICAL:
        return _resolve_vertical(spec, chrome_ctx, profile, marquee_cfg)

    return _resolve_horizontal(spec, chrome_ctx, profile, marquee_cfg)


def _measure_row_content_width(row: dict[str, Any]) -> float:
    """Estimate the pixel width of a marquee row's content stream.

    Accounts for text width, letter-spacing, gaps, and separators.
    Used to set scroll_distance so Set B aligns seamlessly with Set A.
    """
    from hyperweave.core.text import measure_text

    fs = float(row.get("font_size", 12))
    ls_px = float(row.get("letter_spacing", "0") or "0")
    gap = float(row.get("gap", 28))
    row_family_raw = row.get("font_family", "")
    start_x = float(row.get("text_start_x", 20))
    sep = row.get("separator", "")

    # Row family is passed directly to measure_text; unknown families fall
    # back to Inter + one-shot warning via FontRegistry — no manual
    # font_scale heuristic. When cells override font_family, their value wins.
    total = start_x
    for i, cell in enumerate(row.get("cells", [])):
        text = cell.get("text", "")
        cell_fs = float(cell.get("font_size", fs))
        cell_family = cell.get("font_family", row_family_raw) or "Inter"
        cell_bold = int(cell.get("font_weight", row.get("font_weight", "400")) or "400") >= 700
        w = measure_text(
            text,
            font_family=cell_family,
            font_size=cell_fs,
            font_weight=700 if cell_bold else 400,
        )
        # Add letter-spacing between characters (applied per-tspan, not parent <text>)
        if len(text) > 1:
            w += ls_px * (len(text) - 1)
        total += w

        # Add gap/dx before this cell (except first)
        if i > 0:
            total += float(cell.get("dx", gap))

        # Add separator + gap after cell (if separator between cells)
        # Separator tspans have NO letter-spacing (architectural fix: ls on word tspans only)
        if sep and i < len(row.get("cells", [])) - 1:
            sep_w = measure_text(sep, font_family=cell_family, font_size=fs)
            total += gap + sep_w

    return total


def _apply_content_aware_scroll(rows: list[dict[str, Any]], base_speed: float, speed: float, frame_width: int) -> None:
    """Set scroll_distance and scroll_dur per row based on actual content width.

    scroll_distance = content_width + trailing_gap. The trailing gap creates
    breathing room between the end of Set A and the start of Set B. Without it,
    the last word of Set A and the first word of Set B are immediately adjacent
    and overlap during the scroll animation.
    """
    for row in rows:
        content_w = _measure_row_content_width(row)
        trailing_gap = float(row.get("gap", 28)) * 2
        sd = max(content_w + trailing_gap, float(frame_width))
        row["scroll_distance"] = int(sd)
        row["scroll_dur"] = round(sd / (base_speed * speed), 2)


def _resolve_counter(
    spec: ComposeSpec,
    chrome_ctx: dict[str, Any],
    profile: dict[str, Any] | None = None,
    marquee_cfg: Any = None,
) -> dict[str, Any]:
    """Counter-scroll tri-band: 3 rows with distinct content types.

    Brutalist and chrome genomes produce different aesthetic DNA:
    - Brutalist: monospace, ■ separators, bold accent colors, thick dividers
    - Chrome: display+mono mix, ● separators at 25% opacity, muted palette, thin hairlines
    - Cellular bifamily: tspan_palette teal/amethyst alternation, ◆ separators
      at #606878, hairline row dividers (no thick rule chrome).
    """
    _prof = profile or {}
    width, height = 800, 140
    base_speed = 90.2  # px/s (1000 / 11.09)
    # Speed override: marquee_speeds[0] scales all rows uniformly
    speed = spec.marquee_speeds[0] if spec.marquee_speeds else 1.0

    # Parse brand items from title (pipe-separated for phrases, fallback to space-split)
    title_raw = spec.title or ""
    if "|" in title_raw or "·" in title_raw:
        brand_items = [s.strip() for s in title_raw.replace("·", "|").split("|") if s.strip()]
    else:
        brand_items = [s.strip() for s in title_raw.split() if s.strip()]
    brand_items = brand_items or ["HYPERWEAVE"]

    metric_items = _parse_counter_metrics(spec.value or "")

    # ── Profile-driven layout parameters ──
    brand_color_even = _prof.get("marquee_counter_brand_color_even", "var(--dna-signal)")
    brand_color_odd = _prof.get("marquee_counter_brand_color_odd", "var(--dna-ink-primary)")
    metric_label_color = _prof.get("marquee_counter_metric_label_color", "var(--dna-label-text, var(--dna-signal-dim))")
    metric_value_font = _prof.get("marquee_counter_metric_value_font", "")
    row_ys = _prof.get("marquee_counter_row_ys", [6, 48, 90])
    row_hs = _prof.get("marquee_counter_row_hs", [36, 36, 38])
    text_ys = _prof.get("marquee_counter_text_ys", [30, 72, 115])
    divider_ys = _prof.get("marquee_counter_divider_ys", [44, 88])
    gap_r1 = _prof.get("marquee_counter_gap_r1", 28)
    letter_spacing_r1 = _prof.get("marquee_counter_letter_spacing_r1", "4")
    letter_spacing_r2 = _prof.get("marquee_counter_letter_spacing_r2", "1.5")
    letter_spacing_r3 = _prof.get("marquee_counter_letter_spacing_r3", "1")
    text_start_x = _prof.get("marquee_counter_text_start_x", 20)
    separator = _prof.get("marquee_separator", "■")
    separator_color = _prof.get("marquee_separator_color", "var(--dna-border)")
    separator_opacity = _prof.get("marquee_separator_opacity", "")
    font_family = _prof.get("marquee_font_family", "var(--dna-font-mono, ui-monospace, monospace)")
    mono_font = f"var(--dna-font-mono, {_prof.get('fonts', {}).get('mono', 'monospace')})"

    # Bifamily palette dispatch — when family == "bifamily" and the paradigm
    # declares a tspan_palette, the three rows alternate teal/amethyst/teal
    # so the tri-band reads as a cellular substrate rather than three
    # discrete telemetry feeds. Brutalist/chrome rows keep the original
    # ink-primary/ink-secondary alternation.
    fam = chrome_ctx.get("family", "")
    teal_info = chrome_ctx.get("family_blue_info", "")
    amethyst_info = chrome_ctx.get("family_purple_info", "")
    is_bifamily = (
        fam == "bifamily"
        and bool(teal_info)
        and bool(amethyst_info)
        and marquee_cfg is not None
        and bool(marquee_cfg.tspan_palette)
    )
    # Per-row dominant color when bifamily: teal → amethyst → teal.
    row_palette = [teal_info, amethyst_info, teal_info] if is_bifamily else [None, None, None]

    # ── Row 1: Brand items ──
    row1_cells: list[dict[str, Any]] = []
    for i, text in enumerate(brand_items):
        cell_color = row_palette[0] if is_bifamily else (brand_color_even if i % 2 == 0 else brand_color_odd)
        row1_cells.append({"text": text, "color": cell_color})

    # ── Row 2: Metric label/value pairs ──
    row2_cells: list[dict[str, Any]] = []
    for m in metric_items:
        row2_label_color = row_palette[1] if is_bifamily else metric_label_color
        row2_value_color = row_palette[1] if is_bifamily else "var(--dna-ink-primary)"
        row2_cells.append(
            {
                "text": m["label"],
                "color": row2_label_color,
                "font_weight": "700",
            }
        )
        value_cell: dict[str, Any] = {
            "text": m["value"],
            "color": row2_value_color,
            "font_size": "15",
            "font_weight": "800",
            "dx": "6",
        }
        if metric_value_font:
            value_cell["font_family"] = metric_value_font
        row2_cells.append(value_cell)
        if m.get("delta"):
            arrow = "▲" if m.get("delta_dir") == "positive" else "▼"
            # In bifamily, deltas keep their amethyst row color rather than
            # switching to passing/failing greens — chromatic family wins
            # over status semantics in cellular counter (consistent with
            # vertical's row palette override).
            color = (
                row_palette[1]
                if is_bifamily
                else (
                    "var(--dna-status-passing-core)"
                    if m.get("delta_dir") == "positive"
                    else "var(--dna-status-failing-core)"
                )
            )
            row2_cells.append(
                {
                    "text": f"{arrow}{m['delta']}",
                    "color": color,
                    "font_size": "9",
                    "dx": "4",
                }
            )

    # ── Row 3: Status indicators ──
    status_items = _build_counter_status_items(spec, _prof)
    if is_bifamily:
        # Override every status cell color to row_palette[2] (teal). The
        # cellular counter doesn't render distinct ●/◆ chromatic accents —
        # the rhythm is row-level, not cell-level.
        for cell in status_items:
            cell["color"] = row_palette[2]

    # Paradigm-declared separator (cellular: ◆ / #606878). Falls back to
    # profile-driven separator for brutalist/chrome.
    paradigm_sep_glyph = marquee_cfg.separator_glyph if marquee_cfg is not None else "■"
    paradigm_sep_color = marquee_cfg.separator_color if marquee_cfg is not None else ""
    resolved_sep_r1 = paradigm_sep_glyph if (is_bifamily and paradigm_sep_glyph != "■") else separator
    resolved_sep_color_r1 = paradigm_sep_color if (is_bifamily and paradigm_sep_color) else separator_color

    all_rows = [
        {
            "cells": row1_cells,
            "scroll_distance": 0,
            "scroll_dur": 0,
            "direction": "rtl",
            "separator": resolved_sep_r1,
            "separator_color": resolved_sep_color_r1,
            "separator_opacity": separator_opacity,
            "gap": gap_r1,
            "font_size": 14,
            "font_weight": "800",
            "letter_spacing": letter_spacing_r1,
            "font_family": font_family,
            "text_start_x": text_start_x,
            "row_y": row_ys[0],
            "row_h": row_hs[0],
            "text_y": text_ys[0],
        },
        {
            "cells": row2_cells,
            "scroll_distance": 0,
            "scroll_dur": 0,
            "direction": "ltr",
            "separator": "",
            "separator_color": "",
            "separator_opacity": "",
            "gap": 32,
            "font_size": 11,
            "font_weight": "700",
            "letter_spacing": letter_spacing_r2,
            "font_family": mono_font,
            "text_start_x": text_start_x,
            "row_y": row_ys[1],
            "row_h": row_hs[1],
            "text_y": text_ys[1],
        },
        {
            "cells": status_items,
            "scroll_distance": 0,
            "scroll_dur": 0,
            "direction": "rtl",
            "separator": "",
            "separator_color": "",
            "separator_opacity": "",
            "gap": 24,
            "font_size": 10,
            "font_weight": "500",
            "letter_spacing": letter_spacing_r3,
            "font_family": mono_font,
            "text_start_x": text_start_x,
            "row_y": row_ys[2],
            "row_h": row_hs[2],
            "text_y": text_ys[2],
        },
    ]

    n_rows = spec.marquee_rows if spec.marquee_rows > 1 else 3
    all_rows = all_rows[:n_rows]

    # Calculate per-row scroll_distance from actual content width
    _apply_content_aware_scroll(all_rows, base_speed, speed, width)

    # Use the widest row's scroll_distance as the global fallback
    _sds: list[int] = [r["scroll_distance"] for r in all_rows]
    scroll_distance = max(_sds) if _sds else 1000
    scroll_dur = round(scroll_distance / (base_speed * speed), 2)

    # ── Data-driven parametric vars (profile YAML) ──
    divider_x_inset = _prof.get("marquee_counter_divider_x_inset", 6)
    divider_x1 = divider_x_inset
    divider_x2 = width - divider_x_inset
    # Cellular bifamily counter uses a thinner, more transparent row divider
    # so the rhythm reads as instrument-grade chrome rather than brutalist
    # rule-bars. 0.5px @ 0.15 opacity matches the hairline vocabulary.
    if is_bifamily:
        divider_stroke_width = "0.5"
        divider_stroke_opacity = "0.15"
    else:
        divider_stroke_width = _prof.get("marquee_counter_divider_stroke_width", "1.5")
        divider_stroke_opacity = _prof.get("marquee_counter_divider_stroke_opacity", ".2")
    fade_inset = _prof.get("marquee_counter_fade_inset", 5)
    fade_x = fade_inset
    fade_y = fade_inset
    fade_w = _prof.get("marquee_counter_fade_w", 36)
    fade_h = height - fade_inset * 2
    fade_right_x = width - fade_inset - fade_w
    fade_rx = _prof.get("marquee_counter_fade_rx", "")
    # Cellular bifamily marquee has no rivets/beacon — pure hairline chrome
    # per the no-edge-cell-slabbing rule. Brutalist/chrome retain rivets.
    if is_bifamily:
        show_rivets = False
        show_beacon = False
    else:
        show_rivets = _prof.get("marquee_counter_show_rivets", True)
        show_beacon = _prof.get("marquee_counter_show_beacon", True)

    ctx: dict[str, Any] = {
        "rows": all_rows,
        "scroll_distance": scroll_distance,
        "scroll_dur": scroll_dur,
        "bezel": 4,
        "surface_inset": 5,
        "accent_bar_w": 4,
        "rivet_size": 6,
        "rivet_opacity": 0.4,
        "fade_width": fade_w,
        "beacon_pulse_dur": "2.618s",
        "divider_ys": divider_ys[: n_rows - 1],
        "clip_x": _prof.get("marquee_clip_x", 6),
        "clip_w": _prof.get("marquee_clip_w", 788),
        "direction": spec.marquee_direction,
        # Data-driven parametric vars for profile-dispatched template
        "divider_x1": divider_x1,
        "divider_x2": divider_x2,
        "divider_stroke_width": divider_stroke_width,
        "divider_stroke_opacity": divider_stroke_opacity,
        "fade_x": fade_x,
        "fade_y": fade_y,
        "fade_h": fade_h,
        "fade_right_x": fade_right_x,
        "fade_rx": fade_rx,
        "show_rivets": show_rivets,
        "show_beacon": show_beacon,
    }
    ctx.update(chrome_ctx)
    return {"width": width, "height": height, "template": "frames/marquee-counter.svg.j2", "context": ctx}


def _resolve_vertical(
    spec: ComposeSpec,
    chrome_ctx: dict[str, Any],
    profile: dict[str, Any] | None = None,
    marquee_cfg: Any = None,
) -> dict[str, Any]:
    """Vertical telemetry feed: timestamped event rows with status indicators.

    Dot shape, status colors, and accent styling read from profile YAML.
    Cellular bifamily marquees alternate row dot/label colors using the
    paradigm's tspan_palette (teal/amethyst) — read from ``marquee_cfg``.
    """
    _prof = profile or {}
    width, height = 400, 268
    header_h = 33
    row_height = 30
    base_dur = 23.42  # default at speed=1.0
    speed = spec.marquee_speeds[0] if spec.marquee_speeds else 1.0
    scroll_dur = round(base_dur / speed, 2)
    fade_h = 18

    raw_items = [s.strip() for s in (spec.title or "").split() if s.strip()] or ["HYPERWEAVE"]
    scroll_rows = _build_vertical_rows(
        raw_items,
        warn_color=_prof.get("marquee_vertical_warn_color", "var(--dna-status-warning-core)"),
        status_ts_color=_prof.get("marquee_vertical_status_ts_color", "var(--dna-label-text, var(--dna-signal-dim))"),
    )

    # Bifamily palette dispatch — when family == "bifamily" AND the paradigm
    # declares a non-empty tspan_palette, override per-row dot/label/timestamp
    # colors with the genome's family info hexes (teal/amethyst). Status
    # semantics (passing/warning/err) become subordinate to chromatic family
    # in this paradigm: state is encoded via the message text, not color.
    fam = chrome_ctx.get("family", "")
    teal_info = chrome_ctx.get("family_blue_info", "")
    amethyst_info = chrome_ctx.get("family_purple_info", "")
    has_tspan_palette = bool(marquee_cfg is not None and marquee_cfg.tspan_palette)
    if fam == "bifamily" and teal_info and amethyst_info and has_tspan_palette:
        palette = [teal_info, amethyst_info]
        for i, row in enumerate(scroll_rows):
            color = palette[i % len(palette)]
            row["dot_color"] = color
            row["timestamp_color"] = color
            row["label_color"] = color

    item_count = len(scroll_rows)
    content_h = item_count * row_height

    ctx: dict[str, Any] = {
        "direction": spec.marquee_direction,
        "header_label": "SYSTEM TELEMETRY",
        "header_right_label": "",
        "marquee_label": "LIVE",
        "scroll_rows": scroll_rows,
        "scroll_items": [{"text": r["message"]} for r in scroll_rows],
        "header_h": header_h,
        "row_height": row_height,
        "item_count": item_count,
        "content_h": content_h,
        "scroll_dur": scroll_dur,
        "fade_h": fade_h,
        "dot_shape": _prof.get("marquee_dot_shape", "rect"),
        "dot_size": 4,
        "dot_x": 14,
        "text_x": 26,
        "status_label_x": width - _prof.get("marquee_vertical_status_label_offset", 18),
        "bottom_accent_h": 3,
        "live_dot_size": 8,
        "pulse_dur": "2.618s",
        "divider_y": header_h + 5,
        "bezel": 4,
        "surface_inset": 5,
        # Data-driven parametric var for profile-dispatched template
        "bottom_accent_type": _prof.get("marquee_vertical_bottom_accent_type", "bar"),
    }
    ctx.update(chrome_ctx)
    return {"width": width, "height": height, "template": "frames/marquee-vertical.svg.j2", "context": ctx}


def _resolve_horizontal(
    spec: ComposeSpec,
    chrome_ctx: dict[str, Any],
    profile: dict[str, Any] | None = None,
    marquee_cfg: Any = None,
) -> dict[str, Any]:
    """Horizontal LIVE ticker: brand items scrolling left.

    Separator glyph, separator color, and live-block suppression are read
    from ``marquee_cfg`` (ParadigmMarqueeConfig). Per-item color cycle
    (bifamily tspan palette) is sourced from the genome's family info hexes
    when ``family == "bifamily"`` and the paradigm declares a tspan_palette.
    """
    _prof = profile or {}
    width, height = 800, 40
    scroll_distance = 1000
    base_speed = 90.2
    speed = spec.marquee_speeds[0] if spec.marquee_speeds else 1.0
    scroll_dur = round(scroll_distance / (base_speed * speed), 2)

    items_text = spec.title or ""
    raw_items = [s.strip() for s in items_text.replace("·", "|").split("|") if s.strip()]
    if not raw_items:
        raw_items = [items_text] if items_text else ["HYPERWEAVE"]

    bold_pattern = _prof.get("marquee_horizontal_bold_pattern", "even")
    separator = _prof.get("marquee_separator", "■")
    separator_color = _prof.get("marquee_separator_color", "var(--dna-border)")
    separator_opacity = _prof.get("marquee_separator_opacity", "")
    font_family = _prof.get("marquee_font_family", "var(--dna-font-mono, ui-monospace, monospace)")

    # Bifamily palette dispatch — when family == "bifamily" AND the paradigm
    # declares a non-empty tspan_palette, scroll items cycle through that
    # palette. Specimen cellular-automata-marquee-current.svg cycles
    # teal/amethyst info hexes; the palette is sourced from genome
    # chromosomes (family_blue_seam_mid / family_purple_seam_mid) so a
    # genome-level chromatic change propagates without paradigm edits.
    fam = chrome_ctx.get("family", "")
    teal_info = chrome_ctx.get("family_blue_info", "")
    amethyst_info = chrome_ctx.get("family_purple_info", "")
    has_tspan_palette = bool(marquee_cfg is not None and marquee_cfg.tspan_palette)
    if fam == "bifamily" and teal_info and amethyst_info and has_tspan_palette:
        # Genome-sourced palette wins over paradigm-declared palette so
        # chromatic identity stays in genome chromosomes (Invariant 11).
        # Paradigm tspan_palette length signals "bifamily-tspan capable" —
        # the actual hex values come from the genome.
        palette = [teal_info, amethyst_info]
        scroll_items = [
            {
                "text": t,
                "color": palette[i % len(palette)],
                "font_weight": "700",
            }
            for i, t in enumerate(raw_items)
        ]
    else:
        scroll_items = [
            {
                "text": t,
                "color": "var(--dna-ink-primary)" if i % 2 == 0 else "var(--dna-ink-secondary, var(--dna-ink-muted))",
                "font_weight": (
                    "700" if (bold_pattern == "first" and i == 0) or (bold_pattern == "even" and i % 2 == 0) else ""
                ),
            }
            for i, t in enumerate(raw_items)
        ]

    # Live-block suppression and separator glyph come from ParadigmMarqueeConfig.
    # Defaults (bool False, glyph "■", color "") preserve the historic
    # brutalist/chrome behavior, so paradigms without a marquee block render
    # exactly as before.
    suppress_live_block = bool(marquee_cfg.suppress_live_block) if marquee_cfg is not None else False
    paradigm_sep_glyph = marquee_cfg.separator_glyph if marquee_cfg is not None else "■"
    paradigm_sep_color = marquee_cfg.separator_color if marquee_cfg is not None else ""
    # Resolved separator: paradigm declaration (when non-default) wins over
    # profile YAML; this lets cellular force ◆ without each genome restating
    # marquee_separator in its profile config.
    resolved_sep = paradigm_sep_glyph if paradigm_sep_glyph != "■" else separator
    resolved_sep_color = paradigm_sep_color or separator_color

    # Data-driven parametric vars for profile-dispatched template.
    clip_inset_y = _prof.get("marquee_horizontal_clip_inset_y", 4)
    clip_inset_x = _prof.get("marquee_horizontal_clip_inset_x", 4)
    show_accent_lines = _prof.get("marquee_horizontal_show_accent_lines", True)

    ctx: dict[str, Any] = {
        "direction": spec.marquee_direction,
        "scroll_items": scroll_items,
        "scroll_distance": scroll_distance,
        "scroll_dur": scroll_dur,
        "label_panel_width": 0 if suppress_live_block else 130,
        "clip_x": 0 if suppress_live_block else 132,
        "divider_w": 0 if suppress_live_block else 2,
        "fade_width": 80 if suppress_live_block else 24,
        "accent_line_opacity": 0.0 if suppress_live_block else 0.2,
        "separator": resolved_sep,
        "separator_color": resolved_sep_color,
        "separator_opacity": separator_opacity,
        "marquee_label": "" if suppress_live_block else "LIVE",
        "suppress_live_block": suppress_live_block,
        "item_dx": 20,
        "item_start_x": 20 if suppress_live_block else 148,
        "scroll_font_family": font_family,
        # Data-driven parametric vars for profile-dispatched template
        "clip_inset_y": clip_inset_y,
        "clip_inset_x": clip_inset_x,
        "show_accent_lines": show_accent_lines,
    }
    ctx.update(chrome_ctx)
    return {"width": width, "height": height, "template": "frames/marquee-horizontal.svg.j2", "context": ctx}


# ── Marquee content builders ──


def _parse_counter_metrics(value: str) -> list[dict[str, str]]:
    """Parse label:value pairs from value string for counter row 2."""
    metrics: list[dict[str, str]] = []
    if not value:
        # Default metrics
        return [
            {"label": "STARS", "value": "2.9K", "delta": "340", "delta_dir": "positive"},
            {"label": "FORKS", "value": "278"},
            {"label": "COVERAGE", "value": "94.7%"},
        ]
    for pair in value.replace(";", ",").split(","):
        pair = pair.strip()
        if ":" in pair:
            k, v = pair.split(":", 1)
            metrics.append({"label": k.strip().upper(), "value": v.strip()})
    return metrics or [{"label": "STATUS", "value": "NOMINAL"}]


def _build_counter_status_items(
    spec: ComposeSpec,
    profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build status indicator items for counter row 3."""
    _prof = profile or {}
    dot_color = _prof.get("marquee_counter_status_dot_color", "var(--dna-status-passing-core)")
    diamond_color = _prof.get("marquee_counter_status_diamond_color", "var(--dna-signal)")
    return [
        {"text": "●", "color": dot_color, "font_weight": "700", "dx": "20"},
        {"text": "ONLINE", "color": "var(--dna-ink-secondary, var(--dna-ink-muted))", "font_weight": "500", "dx": "6"},
        {"text": "●", "color": dot_color, "font_weight": "700", "dx": "24"},
        {
            "text": "CDN EDGE 14ms",
            "color": "var(--dna-ink-secondary, var(--dna-ink-muted))",
            "font_weight": "500",
            "dx": "6",
        },
        {"text": "◆", "color": diamond_color, "font_weight": "700", "dx": "24"},
        {
            "text": "CIM COMPLIANT",
            "color": "var(--dna-ink-secondary, var(--dna-ink-muted))",
            "font_weight": "500",
            "dx": "6",
        },
        {"text": "◆", "color": diamond_color, "font_weight": "700", "dx": "24"},
        {
            "text": "WCAG AA PASS",
            "color": "var(--dna-ink-secondary, var(--dna-ink-muted))",
            "font_weight": "500",
            "dx": "6",
        },
    ]


def _build_vertical_rows(
    raw_items: list[str],
    *,
    warn_color: str = "var(--dna-status-warning-core)",
    status_ts_color: str = "var(--dna-label-text, var(--dna-signal-dim))",
) -> list[dict[str, Any]]:
    """Build structured telemetry rows from raw text items."""
    default_events = [
        ("ok", "compositor.compose() → badge", "OK"),
        ("ok", 'genome.load("brutalist-emerald")', "OK"),
        ("info", "frame.render(strip, 560x52)", "2.1KB"),
        ("warn", 'cache.miss("cdn-edge-sjc")', "WARN"),
        ("ok", 'mcp.tool_call("compose_badge")', "OK"),
        ("ok", "validator.cim_check() → PASS", "OK"),
        ("info", 'metadata.tier("resonant")', "T2"),
        ("ok", "a11y.wcag_aa() → 4.7:1", "PASS"),
        ("err", "animate.cx() → CIM VIOLATION", "ERR"),
        ("ok", "compositor.compose() → banner", "OK"),
        ("info", 'cdn.purge("edge-*") → 14ms', "14ms"),
        ("ok", 'genome.register("tokyo-street")', "OK"),
    ]

    _status_dot = {
        "ok": "var(--dna-status-passing-core)",
        "info": "var(--dna-signal)",
        "warn": warn_color,
        "err": "var(--dna-status-failing-core)",
    }
    _status_ts = {
        "ok": status_ts_color,
        "info": status_ts_color,
        "warn": warn_color,
        "err": "var(--dna-status-failing-core)",
    }
    _status_label_color = {
        "ok": "var(--dna-status-passing-core)",
        "info": "var(--dna-ink-primary)",
        "warn": warn_color,
        "err": "var(--dna-status-failing-core)",
    }

    # Use raw_items as event messages if they look like events, otherwise use defaults
    if len(raw_items) >= 4 and any(c in " ".join(raw_items) for c in ["(", "→", "."]):
        events = [("ok", item, "OK") for item in raw_items]
    else:
        events = default_events

    rows: list[dict[str, Any]] = []
    minute = 0
    for i, (status, message, label) in enumerate(events):
        minute += 4 + (i % 3) * 2
        rows.append(
            {
                "status": status,
                "timestamp": f"{minute // 60:02d}:{minute % 60:02d}",
                "message": message,
                "status_label": label,
                "dot_color": _status_dot.get(status, _status_dot["ok"]),
                "timestamp_color": _status_ts.get(status, _status_ts["ok"]),
                "label_color": _status_label_color.get(status, _status_label_color["ok"]),
            }
        )
    return rows


def _fmt_tok(n: int) -> str:
    """Format token count: 500 -> '500', 1500 -> '1.5K', 1500000 -> '1.5M'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


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

    # ── Normalize stages: contract produces {label, dominant_class, start, end, tools} ──
    # Templates need {name, pct, tool_class}; start/end are preserved so
    # :func:`layout_rhythm_bars` can lay out time-proportional x/w.
    total_stage_tools = sum(s.get("tools", 1) for s in stages_raw) or 1
    stages: list[dict[str, Any]] = [
        {
            "name": s.get("dominant_class", s.get("label", "explore")),
            "pct": round(s.get("tools", 1) / total_stage_tools * 100),
            "label": s.get("label", ""),
            "tool_class": s.get("dominant_class", "explore"),
            "start": s.get("start"),
            "end": s.get("end"),
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
    hero_headline = f"{_fmt_tok(total_tok)} tokens billed · ${total_cost:.2f}"
    dur_label = f"{int(duration_m)}m" if duration_m else "—"
    hero_subline = f"{model} · {dur_label} · {calls} calls"
    if not dominant:
        hero_profile = "SESSION"
    elif dominant_pct < 20:
        hero_profile = "MIXED"
    else:
        hero_profile = dominant_label.upper()
    hero_tool_class = dominant["tool_class"] if dominant else "explore"
    # Split "pushbacks" into distinct signals so the card stops labeling them
    # as one opaque "N corrections" lie. user_events counts every non-continuation
    # user turn (corrections + redirects + elaborations); tool errors count
    # failing/blocked tool calls (the red ✗N cell marks reconcile to this).
    n_user_turns = len(user_events)
    n_tool_errors = sum(t.get("errors", 0) + t.get("blocked", 0) for t in tools)
    n_agents = len(agents)
    hero_right: list[dict[str, str]] = [
        {"text": f"{_fmt_tok(total_input)} in / {_fmt_tok(total_output)} out"},
    ]
    if total_cache_read or total_cache_create:
        hero_right.append({"text": f"{_fmt_tok(total_cache_read)} cached / {_fmt_tok(total_cache_create)} written"})
    if n_user_turns:
        hero_right.append({"text": f"{n_user_turns} user turn{'s' if n_user_turns != 1 else ''}"})
    if n_tool_errors:
        hero_right.append({"text": f"{n_tool_errors} tool errors", "accent": "failing"})

    # ── Treemap layout (3-tier, 752px wide, token-proportional) ──
    content_w = 752
    sorted_tools = sorted(tools, key=lambda t: t.get("total_tokens", t.get("count", 0)), reverse=True)
    total_tool_tokens = sum(t.get("total_tokens", t.get("count", 0)) for t in sorted_tools) or 1

    treemap_cells: list[dict[str, Any]] = []
    if sorted_tools:
        # Tier 1: dominant tool — full width, 88px tall
        top = sorted_tools[0]
        top_tokens = top.get("total_tokens", top.get("count", 0))
        pct = round(top_tokens / total_tool_tokens * 100)
        tc = top.get("tool_class", _TOOL_CLASS.get(top.get("name", ""), "explore"))
        treemap_cells.append(
            {
                "tier": 1,
                "x": 0,
                "y": 26,
                "w": content_w,
                "h": 88,
                "name": top.get("name", ""),
                "pct": pct,
                "detail": f"{_fmt_tok(top_tokens)} · {top.get('count', 0)} calls",
                "tool_class": tc,
                "errors": top.get("blocked", 0) + top.get("errors", 0),
            }
        )

        # Tier 2: next tools — proportional widths, 32px tall
        mid_tools = sorted_tools[1:4]
        if mid_tools:
            mid_total = sum(t.get("total_tokens", t.get("count", 0)) for t in mid_tools) or 1
            x = 0
            for t in mid_tools:
                t_tokens = t.get("total_tokens", t.get("count", 0))
                share = t_tokens / mid_total
                w = max(int(content_w * share) - 4, 40)
                tc = t.get("tool_class", _TOOL_CLASS.get(t.get("name", ""), "execute"))
                treemap_cells.append(
                    {
                        "tier": 2,
                        "x": x,
                        "y": 118,
                        "w": w,
                        "h": 32,
                        "name": t.get("name", ""),
                        "pct": round(t_tokens / total_tool_tokens * 100),
                        "detail": f"{_fmt_tok(t_tokens)} · {t.get('count', 0)} calls",
                        "tool_class": tc,
                        "errors": t.get("blocked", 0) + t.get("errors", 0),
                    }
                )
                x += w + 4

        # Tier 3: remaining tools — small boxes, 24px tall
        tail_tools = sorted_tools[4:]
        if tail_tools:
            x = 0
            for t in tail_tools:
                w = max(80, int(content_w / len(tail_tools)) - 4)
                tc = t.get("tool_class", _TOOL_CLASS.get(t.get("name", ""), "coordinate"))
                treemap_cells.append(
                    {
                        "tier": 3,
                        "x": x,
                        "y": 154,
                        "w": min(w, 180),
                        "h": 24,
                        "name": t.get("name", ""),
                        "pct": 0,
                        "detail": f"{t.get('count', 0)} calls",
                        "tool_class": tc,
                        "errors": t.get("blocked", 0) + t.get("errors", 0),
                    }
                )
                x += min(w, 180) + 4

    # ── Rhythm bars ──
    # Delegated to the shared helper so receipt + rhythm-strip can't drift.
    # See src/hyperweave/compose/rhythm.py for the two-pass algorithm.
    bar_area_h = 92
    rhythm_bars = layout_rhythm_bars(stages, area_w=content_w, area_h=bar_area_h)

    # ── Legend entries ──
    used_classes = sorted({c["tool_class"] for c in treemap_cells}) if treemap_cells else ["explore"]
    treemap_legend = [{"tool_class": tc, "label": tc} for tc in used_classes]

    # ── Metadata band (v0.4): provenance row between rhythm legend and footer ──
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

    metadata_left_parts = [project_name]
    if git_branch:
        metadata_left_parts.append(git_branch)
    if receipt_path:
        metadata_left_parts.append(receipt_path)
    metadata_left = " · ".join(metadata_left_parts)

    metadata_right_parts = []
    if session_id_short:
        metadata_right_parts.append(f"session {session_id_short}")
    if start_formatted:
        metadata_right_parts.append(f"started {start_formatted}")
    metadata_right = " · ".join(metadata_right_parts)

    # ── Footer: session stats (left) + brand anchor (right) ──
    # Same split as hero so nothing in the card claims "corrections" anymore.
    footer_parts = []
    if n_user_turns:
        footer_parts.append(f"{n_user_turns} user turn{'s' if n_user_turns != 1 else ''}")
    if n_tool_errors:
        footer_parts.append(f"{n_tool_errors} tool error{'s' if n_tool_errors != 1 else ''}")
    if n_agents:
        footer_parts.append(f"{n_agents} agent{'s' if n_agents != 1 else ''}")
    footer_left = " · ".join(footer_parts) if footer_parts else ""
    footer_right = "hyperweave.app"

    return {
        "width": 800,
        "height": 500,
        "template": "frames/receipt.svg.j2",
        "context": {
            "telemetry": tel,
            "hero_profile": hero_profile,
            "hero_tool_class": hero_tool_class,
            "hero_headline": hero_headline,
            "hero_subline": hero_subline,
            "hero_right_stats": hero_right,
            "treemap_legend": treemap_legend,
            "treemap_cells": treemap_cells,
            "stage_count": len(stages),
            "duration_minutes": int(duration_m),
            "rhythm_bars": rhythm_bars,
            "bar_area_h": bar_area_h,
            "phase_legend": [{"id": tc, "label": tc} for tc in used_classes],
            "dominant_profile": f"{dominant_label} ({dominant_pct}%)",
            "metadata_left": metadata_left,
            "metadata_right": metadata_right,
            "footer_left": footer_left,
            "footer_right": footer_right,
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
    """Resolve telemetry rhythm strip — specimen-faithful layout.

    Computes: left stats, velocity, rhythm bar positions, loop status.
    Specimen: specs/telemetry-artifacts/rhythm-strip.svg
    """
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

    # ── Normalize stages ──
    # start/end preserved so :func:`layout_rhythm_bars` can lay out
    # time-proportional widths when the contract carries them.
    total_stage_tools = sum(s.get("tools", 1) for s in stages_raw) or 1
    stages: list[dict[str, Any]] = [
        {
            "name": s.get("dominant_class", s.get("label", "explore")),
            "pct": round(s.get("tools", 1) / total_stage_tools * 100),
            "tool_class": s.get("dominant_class", "explore"),
            "start": s.get("start"),
            "end": s.get("end"),
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
    calls = sum(t.get("count", 0) for t in tools)

    # Rhythm bars — must match template bar_w = sw - stats_w - right_w - 16.
    # With sw=800, stats_w=180, right_w=120: bar_area_w = 484.
    # Delegated to the shared helper — see src/hyperweave/compose/rhythm.py.
    bar_area_w = 484
    bar_area_h = 42
    rhythm_bars = layout_rhythm_bars(stages, area_w=bar_area_w, area_h=bar_area_h)

    # Velocity estimate
    vel = int(total_tok / max(duration_m, 1)) if duration_m else 0

    # Session ID (strip trailing hyphen so synthetic "session-001" renders as "session"
    # rather than "session-", while UUIDs like "3449fc3d-030c-..." are unaffected)
    sid = session.get("id", "session")
    sid_short = sid[:8].rstrip("-") if len(sid) > 8 else sid

    # Dominant phase
    dominant = max(stages, key=lambda s: s.get("pct", 0)) if stages else {"name": "", "pct": 0}

    return {
        "width": 800,
        "height": 60,
        "template": "frames/rhythm-strip.svg.j2",
        "context": {
            "telemetry": tel,
            "session_id_short": sid_short,
            "call_number": calls,
            "elapsed_label": f"{int(duration_m)}m" if duration_m else "—",
            "token_summary": f"{_fmt_tok(total_tok)} tok · ${total_cost:.2f}",
            "velocity_value": _fmt_tok(vel),
            "stages": rhythm_bars,
            "loop_detected": False,
            "loop_elevated": False,
            "loop_label": "NOMINAL",
            "loop_detail": "no loop",
            "profile_label": f"{dominant['name'].upper()} {dominant['pct']}%" if dominant.get("name") else "",
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
        "family_blue_rim_stops": genome.get("family_blue_rim_stops", []),
        "family_blue_pattern_cells": genome.get("family_blue_pattern_cells", []),
        "family_blue_seam_mid": genome.get("family_blue_seam_mid", ""),
        "family_blue_label_slab_fill": genome.get("family_blue_label_slab_fill", ""),
        "family_blue_label_text": genome.get("family_blue_label_text", ""),
        "family_blue_value_text": genome.get("family_blue_value_text", ""),
        "family_blue_canvas_top": genome.get("family_blue_canvas_top", ""),
        "family_blue_canvas_bottom": genome.get("family_blue_canvas_bottom", ""),
        "family_purple_rim_stops": genome.get("family_purple_rim_stops", []),
        "family_purple_pattern_cells": genome.get("family_purple_pattern_cells", []),
        "family_purple_seam_mid": genome.get("family_purple_seam_mid", ""),
        "family_purple_label_slab_fill": genome.get("family_purple_label_slab_fill", ""),
        "family_purple_label_text": genome.get("family_purple_label_text", ""),
        "family_purple_value_text": genome.get("family_purple_value_text", ""),
        "family_purple_canvas_top": genome.get("family_purple_canvas_top", ""),
        "family_purple_canvas_bottom": genome.get("family_purple_canvas_bottom", ""),
        "bifamily_bridge_teal_mid": genome.get("bifamily_bridge_teal_mid", ""),
        "bifamily_bridge_teal_deep": genome.get("bifamily_bridge_teal_deep", ""),
        "bifamily_bridge_amethyst_core": genome.get("bifamily_bridge_amethyst_core", ""),
        "bifamily_bridge_amethyst_bright": genome.get("bifamily_bridge_amethyst_bright", ""),
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
