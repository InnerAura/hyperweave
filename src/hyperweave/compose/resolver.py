"""Spec resolver -- resolves genome, profile, frame, glyph, motion for each frame type."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    frame_result = resolver_fn(spec, genome, profile, glyph_data=glyph_data)

    # Session 2A+2B: inject paradigm + structural hints into every frame_context
    # (Principle 26 dispatch + Principle 24 template-genome interface).
    # Templates read `paradigm` to resolve {frame_type}/{paradigm}-content.j2,
    # and `structural` for per-frame layout hints (stroke_linejoin, etc.).
    ctx = dict(frame_result.get("context", {}))
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
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve badge dimensions and layout.

    Two rendering modes driven by profile:
      standard (brutalist, clinical, etc.)  -- two-panel, sep+seam, sharp
      chrome                                -- envelope gradient, well, bevel filter
    """
    from hyperweave.core.text import measure_text

    height = profile.get("badge_frame_height", 20)
    use_mono = profile.get("badge_use_mono", True)
    label_uppercase = profile.get("badge_label_uppercase", True)

    # Layout constants
    font_size = 11
    accent_w = 4
    glyph_size = 14
    glyph_gap = 4

    sep_w = profile.get("badge_sep_width", 2)
    seam_w = profile.get("badge_seam_width", 3)
    indicator_size = profile.get("badge_indicator_size", 8)
    ind_pad_r = profile.get("badge_indicator_pad_r", 8)
    inset = profile.get("badge_inset", 0)
    text_y_factor = profile.get("badge_text_y_factor", 0.69)

    # Text content
    label_raw = spec.title or ""
    value_raw = spec.value or ""
    label_display = label_raw.upper() if label_uppercase else label_raw

    # Measure rendered text widths
    lw = (
        measure_text(
            label_display,
            font_size=font_size,
            bold=not use_mono,
            monospace=use_mono,
        )
        if label_display
        else 0.0
    )
    vw = measure_text(value_raw, font_size=font_size, bold=True, monospace=use_mono) if value_raw else 0.0

    # Monospace labels get letter-spacing 0.06em
    if use_mono and label_display:
        lw += len(label_display) * font_size * 0.06

    # System fonts (non-mono) are wider than the Inter LUT
    if not use_mono:
        lw *= 1.15
        vw *= 1.10

    has_glyph = bool(spec.glyph or spec.custom_glyph_svg)

    # Glyph pixel position
    if has_glyph:
        glyph_x = (inset + accent_w + 4) if inset else (accent_w + 3)
        glyph_y = round((height - glyph_size) / 2, 1)
    else:
        glyph_x, glyph_y = 0, 0.0

    # Label area starts after glyph (or after accent)
    label_start = (glyph_x + glyph_size + glyph_gap) if has_glyph else (accent_w + 6)

    # Left panel width
    label_pad_r = 9 if use_mono else 8
    left_panel = round(label_start + lw + label_pad_r)
    left_panel = max(left_panel, 30)

    # Label text center (midpoint of label area)
    label_area_end = left_panel - (6 if label_uppercase else 0)
    label_x = round((label_start + label_area_end) / 2, 1)

    # Total width: left + sep/seam + right panel
    val_pad_l = 3
    val_min_gap = 3
    # Non-mono value text has letter-spacing .4 — add overshoot buffer
    ls_extra = len(value_raw) * 0.4 if not use_mono and value_raw else 0
    right_panel = val_pad_l + vw + ls_extra + 2 * val_min_gap + indicator_size + ind_pad_r
    total_w = round(left_panel + sep_w + seam_w + right_panel)
    total_w = max(total_w, 60)

    # Derived positions
    right_x = left_panel + sep_w + seam_w
    indicator_x = total_w - ind_pad_r - indicator_size
    value_x = round((right_x + val_pad_l + indicator_x) / 2, 1)
    text_y = round(height * text_y_factor, 1)

    # Profile-specific rendering context (envelope, well, specular, etc.)
    profile_ctx = _profile_visual_context(genome, profile)

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
            "sep_width": sep_w,
            "seam_width": seam_w,
            "indicator_size": indicator_size,
            "accent_bar_width": accent_w,
            "has_glyph": has_glyph,
            "show_indicator": True,
            "use_mono": use_mono,
            "label_uppercase": label_uppercase,
            "inset": inset,
            **profile_ctx,
        },
    }


def resolve_strip(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    *,
    glyph_data: dict[str, Any] | None = None,
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve strip dimensions and layout.

    Layout: accent_bar | glyph_zone | identity_text | [divider | metric_cell]* | divider | status_zone
    Width = first_divider_x + n_metrics * pitch + status_zone

    When no glyph is present, the glyph zone (~36px) collapses and all
    downstream positions shift left so there's no dead space.
    """
    height = 52

    metrics = _parse_metrics(spec)
    metric_pitch = profile.get("strip_metric_pitch", 106)
    cell_offset = 12  # gap between first divider and first metric cell
    status_zone = 56  # 14px indicator + padding

    # Glyph zone is ~36px (12 pad + 24 glyph + gap).  Collapse when absent.
    has_glyph = bool(glyph_data and glyph_data.get("path"))
    accent_w = profile.get("strip_accent_width", 0)
    glyph_zone = 36 if has_glyph else 0
    identity_x = accent_w + glyph_zone + 14

    # Compute identity zone width from actual text content (algorithmic, not hardcoded)
    identity = spec.title or ""
    from hyperweave.core.text import measure_text

    id_text_w = measure_text(identity.upper(), font_size=11, bold=True, monospace=True)
    # Account for letter-spacing 0.18em on identity text
    id_text_w += len(identity) * 11 * 0.18
    first_divider_x = max(int(identity_x + id_text_w + 14), 80)  # 14px right padding, min 80
    n = max(len(metrics), 1)
    width = first_divider_x + cell_offset + n * metric_pitch + status_zone

    # Seam positions: all vertical divider x-coordinates for rimrun multi-seam tracing
    seams = [first_divider_x]
    cell_start = first_divider_x + cell_offset
    for i in range(n):
        seams.append(cell_start + (i + 1) * metric_pitch)

    ctx: dict[str, Any] = {
        "identity": identity,
        "metrics": metrics,
        "metric_pitch": metric_pitch,
        "first_divider_x": first_divider_x,
        "seam_positions": seams,
        "strip_corner": profile.get("strip_corner", 5),
        "accent_width": profile.get("strip_accent_width", 0),
        "divider_mode": profile.get("strip_divider_mode", "full"),
        "has_accent": profile.get("strip_accent_width", 0) > 0,
        "strip_glyph_size": profile.get("strip_glyph_size", 20),
        "strip_glyph_fill": profile.get("strip_glyph_fill", "var(--dna-signal)"),
        "strip_identity_weight": profile.get("strip_identity_weight", 900),
        "strip_identity_fill": profile.get("strip_identity_fill", "var(--dna-brand-text)"),
        "strip_identity_letter_spacing": profile.get("strip_identity_letter_spacing", "0.18em"),
        "strip_metric_label_size": profile.get("strip_metric_label_size", 7),
        "strip_metric_label_fill": profile.get("strip_metric_label_fill", "var(--dna-ink-muted)"),
        "strip_metric_label_letter_spacing": profile.get("strip_metric_label_letter_spacing", "0.2em"),
        "strip_metric_label_y": profile.get("strip_metric_label_y", 18),
        "strip_metric_value_weight": profile.get("strip_metric_value_weight", 900),
        "strip_metric_value_fill": profile.get("strip_metric_value_fill", "var(--dna-ink-primary)"),
        "strip_metric_value_y": profile.get("strip_metric_value_y", 36),
        "strip_metric_value_skew": profile.get("strip_metric_value_skew", 0),
        "strip_identity_font": profile.get("strip_identity_font", "var(--dna-font-mono, 'SF Mono', monospace)"),
        "strip_metric_label_font": profile.get("strip_metric_label_font", "var(--dna-font-mono, 'SF Mono', monospace)"),
        "strip_divider_color": profile.get("strip_divider_color", "var(--dna-border)"),
        "strip_divider_opacity": profile.get("strip_divider_opacity", 1.0),
    }
    ctx.update(_profile_visual_context(genome, profile))

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
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve banner dimensions.

    Full variant: 1200x600, 3-column editorial grid, 160px hero text.
    Compact variant: 800x220, no grid, 42px text.
    """
    compact = spec.variant == "compact"
    w = 800 if compact else 1200
    h = 220 if compact else profile.get("banner_height", 600)

    genome_name = genome.get("name", spec.genome_id)
    footer = genome_name.upper()

    from hyperweave.core.text import measure_text

    title = spec.title or "HYPERWEAVE"
    base_fs = 42 if compact else 160
    max_width = (w - 80) if compact else (w - 120)  # margin each side

    # Scale font size down if title overflows available width
    text_w = measure_text(title, font_size=base_fs, bold=True)
    ls_reduction = 0.04 * base_fs * max(len(title) - 1, 0)  # -0.04em letter-spacing
    effective_w = text_w - ls_reduction
    title_fs = max(int(base_fs * max_width / effective_w), 42) if effective_w > max_width else base_fs

    ctx: dict[str, Any] = {
        "banner_title": title,
        "banner_subtitle": spec.value or "subtitle",
        "banner_label": footer,
        "banner_variant": "compact" if compact else "full",
        "title_font_size": title_fs,
    }
    ctx.update(_profile_visual_context(genome, profile))

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
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve icon dimensions.

    Four frame variants selected by icon_variant:
      - brutalist-circular: concentric rings, glyph-dominant, no label
      - brutalist-square: top accent bar, heavy border, no label
      - binary-circular: chrome envelope ring, circle frame
      - binary-square: chrome envelope fill, rounded-rect frame

    Shape selection: profile defines supported shapes, spec.shape overrides.
    """
    icon_label = spec.glyph or spec.title or ""
    profile_id = profile.get("id", "brutalist")

    # Genome-aware shape defaults (specimen-backed only)
    _PROFILE_SHAPES: dict[str, tuple[list[str], str]] = {
        "brutalist": (["circle", "square"], "square"),
        "chrome": (["square", "circle"], "circle"),
    }
    supported, default_shape = _PROFILE_SHAPES.get(profile_id, (["square", "circle"], "square"))
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

    ctx: dict[str, Any] = {
        "icon_shape": shape,
        "icon_rx": 0,
        "icon_label": icon_label,
        "icon_variant": icon_variant,
        # Raw genome hex colors for gradient stops (CSS var() doesn't work in SVG stops)
        "genome_signal": genome.get("accent", "#845ef7"),
        "genome_surface": genome.get("surface_0", "#000000"),
        "genome_ink": genome.get("ink", "#ffffff"),
        "genome_border": genome.get("stroke", "#000000"),
        "genome_signal_dim": genome.get("accent_complement", "#A78BFA"),
    }
    ctx.update(_profile_visual_context(genome, profile))

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
    _specimen_variants = {"block", "current", "takeoff", "void", "zeropoint"}
    variant = spec.divider_variant if spec.divider_variant in _specimen_variants else "zeropoint"
    variant_dims: dict[str, tuple[int, int]] = {
        "block": (700, 80),
        "current": (700, 40),
        "takeoff": (700, 100),
        "void": (700, 40),
        "zeropoint": (700, 30),
    }
    w, h = variant_dims.get(variant, (700, 30))

    ctx: dict[str, Any] = {
        "divider_variant": variant,
        "divider_label": spec.value or "",
    }
    ctx.update(_profile_visual_context(genome, profile))

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
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve marquee dimensions and content.

    Three variants:
      counter    — 800x140, tri-band R/L/R, per-row heterogeneous content
      vertical   — 400x268, telemetry feed with timestamped events
      horizontal — 800x40,  LIVE ticker with brand items
    """
    chrome_ctx = _profile_visual_context(genome, profile)
    # Resolved hex colors for gradient stops (var() is unreliable inside <stop>)
    chrome_ctx["signal_hex"] = genome.get("accent", "#10B981")
    chrome_ctx["surface_hex"] = genome.get("surface_0", genome.get("surface", "#0A0A0A"))

    if spec.type == FrameType.MARQUEE_COUNTER:
        return _resolve_counter(spec, chrome_ctx, profile)

    if spec.type == FrameType.MARQUEE_VERTICAL:
        return _resolve_vertical(spec, chrome_ctx, profile)

    return _resolve_horizontal(spec, chrome_ctx, profile)


def _measure_row_content_width(row: dict[str, Any]) -> float:
    """Estimate the pixel width of a marquee row's content stream.

    Accounts for text width, letter-spacing, gaps, and separators.
    Used to set scroll_distance so Set B aligns seamlessly with Set A.
    """
    from hyperweave.core.text import measure_text

    fs = float(row.get("font_size", 12))
    ls_px = float(row.get("letter_spacing", "0") or "0")
    gap = float(row.get("gap", 28))
    is_mono = "mono" in row.get("font_family", "").lower()
    start_x = float(row.get("text_start_x", 20))
    sep = row.get("separator", "")

    # Display/serif fonts (Georgia, Impact, Arial Black) are wider than the Inter LUT.
    # Scale measured widths to match actual rendering. Mono fonts are already calibrated.
    font_family_raw = row.get("font_family", "").lower()
    if is_mono:
        font_scale = 1.0  # mono LUT already calibrated at 7.2px
    elif "display" in font_family_raw or "serif" in font_family_raw or "impact" in font_family_raw:
        font_scale = 1.30  # display/serif fonts are ~30% wider than Inter
    else:
        font_scale = 1.15  # system-ui / sans-serif are ~15% wider than Inter

    total = start_x
    for i, cell in enumerate(row.get("cells", [])):
        text = cell.get("text", "")
        cell_fs = float(cell.get("font_size", fs))
        cell_mono = is_mono and "font_family" not in cell
        cell_bold = int(cell.get("font_weight", row.get("font_weight", "400")) or "400") >= 700
        w = measure_text(text, font_size=cell_fs, bold=cell_bold, monospace=cell_mono)
        # Apply font-family-aware scale for non-mono fonts
        if not cell_mono:
            w *= font_scale
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
            sep_w = measure_text(sep, font_size=fs, monospace=cell_mono)
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
) -> dict[str, Any]:
    """Counter-scroll tri-band: 3 rows with distinct content types.

    Brutalist and chrome genomes produce different aesthetic DNA:
    - Brutalist: monospace, ■ separators, bold accent colors, thick dividers
    - Chrome: display+mono mix, ● separators at 25% opacity, muted palette, thin hairlines
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

    # ── Row 1: Brand items ──
    row1_cells: list[dict[str, Any]] = []
    for i, text in enumerate(brand_items):
        row1_cells.append(
            {
                "text": text,
                "color": brand_color_even if i % 2 == 0 else brand_color_odd,
            }
        )

    # ── Row 2: Metric label/value pairs ──
    row2_cells: list[dict[str, Any]] = []
    for m in metric_items:
        row2_cells.append(
            {
                "text": m["label"],
                "color": metric_label_color,
                "font_weight": "700",
            }
        )
        value_cell: dict[str, Any] = {
            "text": m["value"],
            "color": "var(--dna-ink-primary)",
            "font_size": "15",
            "font_weight": "800",
            "dx": "6",
        }
        if metric_value_font:
            value_cell["font_family"] = metric_value_font
        row2_cells.append(value_cell)
        if m.get("delta"):
            arrow = "▲" if m.get("delta_dir") == "positive" else "▼"
            color = (
                "var(--dna-status-passing-core)"
                if m.get("delta_dir") == "positive"
                else "var(--dna-status-failing-core)"
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

    all_rows = [
        {
            "cells": row1_cells,
            "scroll_distance": 0,
            "scroll_dur": 0,
            "direction": "rtl",
            "separator": separator,
            "separator_color": separator_color,
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
    divider_stroke_width = _prof.get("marquee_counter_divider_stroke_width", "1.5")
    divider_stroke_opacity = _prof.get("marquee_counter_divider_stroke_opacity", ".2")
    fade_inset = _prof.get("marquee_counter_fade_inset", 5)
    fade_x = fade_inset
    fade_y = fade_inset
    fade_w = _prof.get("marquee_counter_fade_w", 36)
    fade_h = height - fade_inset * 2
    fade_right_x = width - fade_inset - fade_w
    fade_rx = _prof.get("marquee_counter_fade_rx", "")
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
) -> dict[str, Any]:
    """Vertical telemetry feed: timestamped event rows with status indicators.

    Dot shape, status colors, and accent styling read from profile YAML.
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
) -> dict[str, Any]:
    """Horizontal LIVE ticker: brand items scrolling left.

    Separator, font family, and colors read from profile YAML.
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

    # Data-driven parametric vars for profile-dispatched template
    clip_inset_y = _prof.get("marquee_horizontal_clip_inset_y", 4)
    clip_inset_x = _prof.get("marquee_horizontal_clip_inset_x", 4)
    show_accent_lines = _prof.get("marquee_horizontal_show_accent_lines", True)

    ctx: dict[str, Any] = {
        "direction": spec.marquee_direction,
        "scroll_items": scroll_items,
        "scroll_distance": scroll_distance,
        "scroll_dur": scroll_dur,
        "label_panel_width": 130,
        "clip_x": 132,
        "divider_w": 2,
        "fade_width": 24,
        "accent_line_opacity": 0.2,
        "separator": separator,
        "separator_color": separator_color,
        "separator_opacity": separator_opacity,
        "marquee_label": "LIVE",
        "item_dx": 20,
        "item_start_x": 148,
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
    corrections: list[dict[str, Any]] = tel.get("corrections", [])
    agents: list[dict[str, Any]] = tel.get("agents", [])

    # ── Normalize tools: contract produces dict keyed by name, templates need list ──
    if isinstance(tools_raw, dict):
        tools: list[dict[str, Any]] = [{"name": name, **data} for name, data in tools_raw.items()]
    else:
        tools = list(tools_raw)

    # ── Normalize stages: contract produces {label, dominant_class, start, end, tools} ──
    # Templates need {name, pct, tool_class} with percentage proportions
    total_stage_tools = sum(s.get("tools", 1) for s in stages_raw) or 1
    stages: list[dict[str, Any]] = [
        {
            "name": s.get("dominant_class", s.get("label", "explore")),
            "pct": round(s.get("tools", 1) / total_stage_tools * 100),
            "label": s.get("label", ""),
            "tool_class": s.get("dominant_class", "explore"),
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

    # ── Hero row ──
    hero_headline = f"{_fmt_tok(total_tok)} tokens billed · ${total_cost:.2f}"
    dur_label = f"{int(duration_m)}m" if duration_m else "—"
    hero_subline = f"{model} · {dur_label} · {calls} calls"
    hero_profile = stages[0]["label"].upper() if stages else "SESSION"
    hero_tool_class = stages[0]["tool_class"] if stages else "explore"
    n_corrections = len(corrections)
    n_agents = len(agents)
    hero_right = [
        f"{_fmt_tok(total_input)} in / {_fmt_tok(total_output)} out",
    ]
    if total_cache_read or total_cache_create:
        hero_right.append(f"{_fmt_tok(total_cache_read)} cached / {_fmt_tok(total_cache_create)} written")
    if n_corrections:
        hero_right.append(f"{n_corrections} correction{'s' if n_corrections != 1 else ''}")

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

    # ── Rhythm bars (scale stages to 752px) ──
    total_stage_pct = sum(s.get("pct", 0) for s in stages) or 100
    rhythm_bars: list[dict[str, Any]] = []
    rx = 0
    bar_area_h = 92
    for s in stages:
        pct = s.get("pct", 0)
        w = max(int(content_w * pct / total_stage_pct), 6)
        h = max(int(bar_area_h * (pct / 50)), 8)
        y = bar_area_h - h
        tc = s.get("tool_class", s.get("name", "explore"))
        rhythm_bars.append({"x": rx, "y": y, "w": w, "h": h, "tool_class": tc})
        rx += w + 2

    # ── Legend entries ──
    used_classes = sorted({c["tool_class"] for c in treemap_cells}) if treemap_cells else ["explore"]
    treemap_legend = [{"tool_class": tc, "label": tc} for tc in used_classes]

    # ── Dominant phase ──
    dominant = max(stages, key=lambda s: s.get("pct", 0)) if stages else {"name": "", "pct": 0}
    dominant_label = dominant.get("label", dominant.get("name", ""))
    dominant_pct = dominant.get("pct", 0)

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
    footer_parts = []
    if n_corrections:
        footer_parts.append(f"{n_corrections} corrections")
    if n_agents:
        footer_parts.append(f"{n_agents} agents")
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
            "hero_right_stats": [{"text": t} for t in hero_right],
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
    total_stage_tools = sum(s.get("tools", 1) for s in stages_raw) or 1
    stages: list[dict[str, Any]] = [
        {
            "name": s.get("dominant_class", s.get("label", "explore")),
            "pct": round(s.get("tools", 1) / total_stage_tools * 100),
            "tool_class": s.get("dominant_class", "explore"),
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
    # Budget accounts for 2px gaps between bars so many-stage sessions don't
    # overflow into the right-side loop-status panel.
    bar_area_w = 484
    bar_area_h = 42
    gap_px = 2
    n_stages = len(stages)
    gap_budget = gap_px * max(n_stages - 1, 0)
    available_w = max(bar_area_w - gap_budget, bar_area_w // 2)
    min_bar_w = max(2, available_w // max(n_stages, 1) // 3) if n_stages else 6
    total_stage_pct = sum(s.get("pct", 0) for s in stages) or 100

    raw_bars: list[dict[str, Any]] = []
    for s in stages:
        pct = s.get("pct", 0)
        w = max(int(available_w * pct / total_stage_pct), min_bar_w)
        h = max(int(bar_area_h * (pct / 50)), 6)
        y = bar_area_h - h
        tc = s.get("tool_class", "explore")
        raw_bars.append({"w": w, "h": h, "y": y, "tool_class": tc})

    # Post-hoc uniform scale if floor-pressure still exceeds budget
    raw_total = sum(b["w"] for b in raw_bars)
    if raw_total > available_w and raw_total > 0:
        scale = available_w / raw_total
        for b in raw_bars:
            b["w"] = max(int(b["w"] * scale), 2)

    rhythm_bars: list[dict[str, Any]] = []
    rx = 0
    for b in raw_bars:
        rhythm_bars.append({"x": rx, "y": b["y"], "w": b["w"], "h": b["h"], "tool_class": b["tool_class"]})
        rx += b["w"] + gap_px

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


def _load_genome(genome_id: str, override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load a genome dict by slug, or return the override if provided.

    Session 2A+2B: when ``override`` is a dict, it is returned verbatim.
    This is the ``--genome-file`` path — the CLI loads JSON, validates via
    ``GenomeSpec``, and passes the resulting dict through ``ComposeSpec.genome_override``.
    The resolver trusts the caller to have validated.
    """
    if override is not None:
        return override
    try:
        from hyperweave.config.loader import get_loader

        loader = get_loader()
        return loader.genomes.get(genome_id, _default_genome(genome_id))
    except (ImportError, Exception):
        return _default_genome(genome_id)


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


def _parse_metrics(spec: ComposeSpec) -> list[dict[str, str]]:
    metrics: list[dict[str, str]] = []

    # Try slots first
    for slot in spec.slots:
        if slot.zone.startswith("metric"):
            parts = slot.value.split(":", 1) if ":" in slot.value else [slot.zone, slot.value]
            metrics.append(
                {
                    "label": parts[0].upper(),
                    "value": parts[1] if len(parts) > 1 else slot.value,
                }
            )

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

    # Ensure all metrics have delta fields
    for m in metrics:
        m.setdefault("delta", "")
        m.setdefault("delta_dir", "neutral")

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


def _profile_visual_context(genome: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Build profile-specific visual rendering context from genome data.

    Returns envelope, well, specular, and material properties that the genome
    defines. Templates guard on data presence ({% if envelope_stops %}), not
    on profile identity. A genome without envelope_stops gets no envelope —
    regardless of which profile it belongs to.
    """
    env_stops = genome.get("envelope_stops", [])
    corner_raw = str(genome.get("corner", "4px")).replace("px", "")
    ctx = {
        "envelope_stops": env_stops,
        "well_top": genome.get("well_top", ""),
        "well_bottom": genome.get("well_bottom", ""),
        "specular_light": genome.get("highlight_color", ""),
        "specular_sweep_dur": genome.get("specular_sweep_dur", ""),
        "specular_sweep_peak": genome.get("specular_sweep_peak", ""),
        "highlight_opacity": genome.get("highlight_opacity", ""),
        "bevel_shadow_opacity": genome.get("shadow_opacity", ""),
        "chrome_corner": corner_raw,
        "chrome_text_gradient": genome.get("chrome_text_gradient", []),
        "chrome_rhythm": genome.get("rhythm_base", ""),
        "glyph_fill": genome.get("glyph_inner", ""),
        "light_mode": genome.get("light_mode"),
    }
    # Badge bevel extras -- only when genome provides bevel config
    if genome.get("highlight_color"):
        ctx["bevel_spec_constant"] = genome.get("bevel_spec_constant", "0.8")
        ctx["bevel_spec_exponent"] = genome.get("bevel_spec_exponent", "25.0")
        ctx["chrome_rhythm"] = genome.get("rhythm_base", "6s")
        ctx["light_mode"] = genome.get("light_mode")
    return ctx


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
