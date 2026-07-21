"""Paradigm specifications -- declarative frame-level config overrides.

A paradigm is a cross-cutting aesthetic family (chrome, brutalist, default)
that selects template partials and supplies layout dimensions + typography
sizes to resolvers. Genomes opt into paradigms per frame type via their
``paradigms`` dict:

    {"badge": "chrome", "strip": "chrome", "stats": "brutalist"}

Templates dispatch via slug interpolation:

    {% include "frames/stats/" ~ paradigm ~ "-content.j2" %}

Resolvers consume the typed sub-config (``paradigm_spec.strip.value_font_size``)
instead of comparing paradigm strings (``if paradigm == "chrome"``).

Scoping rule (Architectural Decision):
    ParadigmSpec owns layout + dispatch choices that are identical across
    every genome opting into the paradigm (viewport dims, font sizes,
    divider render mode). GenomeSpec owns chromatic identity and any
    per-genome structural choice (envelope_stops, data_point_shape).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from hyperweave.core.models import FrozenModel


class ParadigmChartConfig(FrozenModel):
    """Chart frame config within a paradigm."""

    viewport_x: int = 80
    viewport_y: int = 150
    viewport_w: int = 760
    viewport_h: int = 245
    chart_width: int = 900
    """Overall chart SVG width (brutalist/chrome: 900; cellular v0.3.0 refresh: 680)."""
    chart_height: int = 500
    """Overall chart SVG height. Cellular v0.3.0 refresh: 380."""
    line_animate: bool = False
    """When True, emit a one-shot stroke-dashoffset draw animation on the
    polyline/path. Cellular paradigm opts in to reproduce the specimen's
    line-draws-on-load feel; brutalist/chrome keep the line static so the
    chart reads as instrument, not demo."""
    axis_accent: bool = False
    """When True (primer), the top Y-tick label and the trailing (current) X-tick
    label render in the genome accent, and vertical gridlines drop at every X-tick.
    Matches the porcelain chart specimen's blue axis details + full grid. ``False``
    (brutalist/chrome/cellular) keeps uniform muted ticks and horizontal-only grid,
    so those charts stay byte-identical."""
    cell_size: int = 0
    """Cellular substrate cell stride in pixels. Zero defers to the chart
    engine's internal default. Cellular v0.3.0 refresh: 19 (cell width 18,
    1px gap)."""
    header_band_height: int = 0
    """Height of the HUD-style header band rendered as a solid rect at the
    top of the chart (paradigm-specific). Zero disables the band entirely.
    Cellular v0.3.0 refresh: 64 (band houses repo identifier, title, and
    hero metric inside a tone-specific dark mid-band fill)."""
    identity_font_family: str = "JetBrains Mono"
    """Font family for the chart header identity slot. Chrome uses the same
    Orbitron identity typography as its badge label."""
    identity_font_size: float = 12
    """Font size for the chart header identity slot."""
    identity_font_weight: int = 700
    """Font weight for the chart header identity slot."""
    identity_letter_spacing_em: float = 0.06
    """CSS letter-spacing for the chart header identity slot."""
    y_tick_target: int = 4
    """Target number of Y-axis tick intervals. Cellular uses a denser target."""
    label_collision_font_family: str = "JetBrains Mono"
    """Font family used when chart_engine measures milestone/x-axis label collisions."""
    label_collision_font_size: float = 9
    """Font size used for collision measurement."""
    label_collision_font_weight: int = 800
    """Font weight used for collision measurement."""
    label_collision_letter_spacing_em: float = 0.12
    """Letter spacing used for collision measurement."""
    axis_y_label_x_offset: int = -8
    """Y-axis label x offset relative to viewport_x."""
    axis_y_label_y_offset: int = 4
    """Y-axis label baseline offset relative to the tick y."""
    x_axis_label_y: int = 420
    """Standalone chart x-axis label baseline."""
    milestone_label_y_offset: int = -24
    """Generic milestone label offset from the crossing point."""
    header_identity_gap: int = 12
    """Minimum breathing gap between same-row header identity/description text."""
    header_identity_max_right_margin: int = 24
    """Right margin for header identity text when it is right anchored."""


class ParadigmStatsConfig(FrozenModel):
    """Stats frame config within a paradigm."""

    card_height: int = 260
    card_width: int = 0
    """Stats card width in pixels. Zero defers to the resolver's default
    (495). Cellular v0.3.0 refresh: 530."""
    embeds_chart: bool = False
    """When True, resolve_stats composes a compact star-history strip
    beneath the metric row (chrome paradigm). When False, stats card is
    self-contained (brutalist paradigm)."""
    embed_viewport_x: int = 240
    embed_viewport_y: int = 170
    embed_viewport_w: int = 220
    embed_viewport_h: int = 70
    # v0.3.0 cellular refresh — paradigm-level genome-independent constants.
    # Routed to template context as named variables (not raw hex) so the
    # variant-blind hex gate stays effective and other paradigms can override
    # without touching genome JSON.
    streak_green: str = ""
    """Color for the streak metric (.mvg class) — genome-independent positive
    signal. Cellular v0.3.0: '#3FB950' (GitHub green). Empty disables the
    .mvg class fill rule."""
    mid_gray: str = ""
    """Mid-tone gray for medium metrics (.mvm/.mvs classes). Cellular v0.3.0:
    '#6B7A88'. Empty falls back to the cell's CSS default."""
    hero_white: str = ""
    """Bright white for the hero metric (.mvh class). Cellular v0.3.0:
    '#ECF2F8'. Empty falls back to the genome's value_text."""
    # Heatmap geometry — cellular paradigm only consumes these. Other paradigms
    # leave them at zero and skip the heatmap zone entirely.
    heatmap_rows: int = 0
    """Heatmap row count. Cellular v0.3.0: 7."""
    heatmap_cols: int = 0
    """Heatmap column count. Cellular v0.3.0: 42."""
    heatmap_cell_size: float = 0
    """Heatmap square cell side length in pixels. Cellular v0.3.0: 11.080."""
    heatmap_cell_gap: float = 0
    """Heatmap inter-cell gap in pixels (used for both x and y). Cellular v0.3.0: 1.2."""
    heatmap_zone_height: float = 0
    """Heatmap zone height available for cells + gaps; assertion test
    enforces ``rows*cell + (rows-1)*gap <= heatmap_zone_height + 0.5``.
    Cellular v0.3.0: ~84.76 (matches 7x11.080 + 6x1.2)."""
    header_band_height: int = 0
    """Header band height in pixels at the top of the stats card. Zero
    disables. Cellular v0.3.0: 39 (band houses username + bio + brand stamp
    against a dark gradient fill)."""
    identity_x: int = 0
    """Left edge (px) of the username/identity text in the stat card header.
    The resolver derives ``identity_zone_width`` from neighboring layout —
    ``bio_x - identity_x - identity_padding`` — instead of carrying a magic
    number that has to be re-tuned every time ``bio_x`` shifts. Cellular: 20.
    Brutalist: 44. Chrome: 0 (chrome has no competing header label, so the
    derived zone width is 0 and shrink-to-fit is disabled)."""
    bio_x: int = 0
    """Left edge (px) of the bio/repo_label text in the stat card header.
    Used both to position the template element (replacing hardcoded x="110"
    / x="122" template literals) and to derive ``identity_zone_width``.
    Cellular: 110. Brutalist: 122. Chrome: 0 (no header bio)."""
    identity_padding: int = 0
    """Breathing gap (px) reserved between a clamped username's right edge
    and ``bio_x``. Prevents the shrunk username from butting directly
    against the bio text. Cellular: 2. Brutalist: 8."""
    identity_breathing_margin: int = 0
    """Gap (px) between the username's visible-ink end and the bio text
    in ADAPTIVE bio_x mode. The resolver computes
    ``adaptive_bio_x = identity_x + identity_ink_width + identity_breathing_margin``
    using per-glyph ink measurement (measure_text_ink_width from the v0.3.9
    LUT extraction). Short usernames snap bio close (tight visual); when
    the identity gets clamped via textLength, the same formula with
    ``identity_zone_w`` substituted reproduces the v0.3.8 fixed bio_x
    automatically. StatsLayout enforces an 8px visible-gap floor so header
    identity and bio text cannot visually collide. Brutalist: 8 (reproduces
    v0.3.8 bio_x=122 for clamped identities, gives tight snap for short like
    ELI64S). Cellular: 8."""
    bio_collision_clamp: bool = False
    """When True, the resolver measures the bio's natural rendered width and
    emits ``bio_text_length`` so the template applies SVG ``textLength``
    shrink-to-fit when the bio would visually collide with the right-edge
    HYPERWEAVE branding element. Cellular: True (bio and branding share the
    header band row, so long bios collide). Brutalist: False (branding lives
    in the footer row, no collision). v0.3.9: addresses the karpathy-bio /
    HYPERWEAVE overlap reported in visual review."""
    identity_font_family: str = "Inter"
    """Font family used by the paradigm's stats username/identity CSS class.
    The resolver passes this to ``measure_text`` so the measured natural width
    matches what the template renders. The resolver previously measured with
    Inter while paradigms rendered Orbitron / JetBrains Mono / etc., producing
    under-measured widths and missed overflow clamps. Cellular: 'Orbitron'.
    Brutalist: 'JetBrains Mono'. Chrome: 'Orbitron'."""
    identity_font_size: float = 13
    """Font size (px) for the username/identity CSS class. Brutalist: 11.
    Cellular: 13. Chrome: 13."""
    identity_font_weight: int = 700
    """Font weight for the username/identity CSS class. Brutalist: 800.
    Cellular: 700. Chrome: 700."""
    identity_letter_spacing_em: float = 0.0
    """CSS letter-spacing (em) for username/identity. Brutalist: 0.22.
    Cellular: 0.16. Chrome: 0.16. ``measure_text`` applies ``(N-1) * size * em``
    so the reserved width matches actual render — a 0.16em spacing on 8 chars
    at 13px adds 13.4px that the previous Inter-13/700/0 measurement missed."""
    identity_text_transform: Literal["none", "uppercase"] = "none"
    """Text transform applied by the stats template before render. The resolver
    must measure the transformed text, otherwise lower-case connector data
    underestimates templates that render ``{{ stats_username | upper }}``."""
    metric_layout_mode: Literal["brutalist_grid", "chrome_columns", "cellular_inline", "primer_editorial"] = (
        "brutalist_grid"
    )
    """Stats metric slot layout algorithm selected by config, never by paradigm slug."""
    metric_value_font_family: str = "Inter"
    metric_value_font_size: float = 20
    metric_value_font_weight: int = 700
    metric_value_letter_spacing_em: float = 0.0
    metric_value_budget: float = 112.0
    """Shrink-to-fit budget for centered stat metric values."""
    metric_label_font_family: str = "JetBrains Mono"
    metric_label_font_size: float = 6.5
    metric_label_font_weight: int = 500
    metric_label_letter_spacing_em: float = 0.22
    cellular_metric_value_font_family: str = "Chakra Petch"
    cellular_metric_y: float = 72.8
    cellular_metric_left_x: float = 20.0
    cellular_metric_right_margin: float = 20.0
    cellular_metric_value_label_gap: float = 4.0
    cellular_metric_inter_slot_gap: float = 12.0
    activity_bar_baseline_y: float = 246.0
    activity_bar_max_h: float = 26.0
    activity_bar_min_h: float = 4.0
    activity_bar_w: float = 7.0
    activity_bar_start_x: float = 22.0
    activity_bar_stride: float = 9.0
    activity_bar_opacity_min: float = 0.43
    activity_bar_opacity_max: float = 0.93
    activity_bar_opacity_min_light: float = 0.28
    activity_bar_opacity_max_light: float = 0.75
    language_zone_x: float = 6.0
    language_zone_y: float = 252.0
    language_zone_h: float = 12.0
    language_label_offset_x: float = 8.0
    language_label_y_dark: float = 260.5
    language_label_y_light: float = 260.5
    language_segment_opacities: list[float] = Field(default_factory=lambda: [0.55, 0.40, 0.25, 0.10])
    language_segment_opacities_light: list[float] = Field(default_factory=lambda: [0.12, 0.06, 0.04, 0.02])
    inline_language_zone_left: float = 20.0
    inline_language_zone_right_margin: float = 20.0
    inline_language_swatch_w: float = 5.0
    inline_language_swatch_h: float = 5.0
    inline_language_swatch_rx: float = 1.0
    inline_language_swatch_text_gap: float = 4.0
    inline_language_entry_gap: float = 24.0
    inline_language_swatch_y: float = 216.0
    inline_language_label_y: float = 221.0
    heatmap_x0: float = 20.0
    heatmap_y0: float = 114.0
    heatmap_cell_rx: float = 1.5
    heatmap_legend_xs: list[float] = Field(default_factory=lambda: [467.0, 476.0, 485.0, 494.0, 503.0])
    heatmap_legend_y: float = 101.0
    heatmap_legend_size: float = 7.0
    heatmap_legend_rx: float = 1.5


class ParadigmStripConfig(FrozenModel):
    """Strip frame config within a paradigm."""

    strip_height: int = 52
    """Total strip height in px. Brutalist/chrome: 52; cellular specimen: 48."""
    value_font_size: float = 18
    value_font_family: str = "Inter"
    label_font_size: float = 7
    label_font_family: str = "JetBrains Mono"
    # Identity text zone (left side, between glyph and first divider).
    # resolve_strip MUST measure identity with these paradigm values so
    # first_divider_x matches the rendered text width — no hardcoded JBMono
    # that silently diverges when a paradigm uses Orbitron or Chakra Petch
    # for identity.
    identity_font_family: str = "JetBrains Mono"
    identity_font_size: float = 11
    identity_font_weight: int = 700
    identity_letter_spacing_em: float = 0.18
    # Subtitle under identity (paradigm opts in). Cellular strip v10 renders
    # "eli64s/readme-ai" beneath "README-AI".
    show_subtitle: bool = False
    subtitle_font_family: str = "JetBrains Mono"
    subtitle_font_size: float = 6.5
    subtitle_letter_spacing_em: float = 0.0
    # Icon box — structural frame around glyph (cellular specimen: 28x28 at
    # flank_end + 8). Brutalist/chrome glyph renders bare (no box).
    show_icon_box: bool = False
    icon_box_size: int = 28
    icon_box_pad: int = 8
    strip_glyph_ratio: float = 0.346
    """Identity glyph size as fraction of strip height. Computed value:
    ``strip_glyph_size = round(strip_height * strip_glyph_ratio)``. Default
    0.346 yields 18px at strip_height=52 — the design constant established in
    v0.3.9 (brutalist's specimen-derived 18px in a 52px strip). Changing this
    field changes the proportional glyph across every paradigm uniformly;
    changing strip_height in one paradigm produces a correctly-scaled glyph
    without per-paradigm re-tuning. v0.3.9 replaces the previous hand-synced
    pair (chrome ``glyph_size: 22`` + brutalist ``identity_glyph_size: 18``)
    that had to stay in proportional agreement by manual update."""
    divider_render_mode: Literal["gradient", "class", "paired-rect"] = "class"
    """``gradient`` routes through ``url(#{uid}-sep)`` stroke (chrome's etched
    sep); ``class`` uses a flat CSS-class-colored divider; ``paired-rect``
    (primer) carves the divider as two adjacent 1px rects — a groove (dark on
    dark substrates, ink-tinted on light) and a shine (white at substrate-tuned
    opacity) — positioned by ``divider_y``/``divider_h``."""
    divider_inset: int = 8
    """Vertical inset (px) of the inter-zone dividers from the strip's top and
    bottom edges (``y1 = inset``, ``y2 = height - inset``). Used by the
    ``gradient``/``class`` divider modes; the flat-profile default 8 keeps
    chrome/cellular/default dividers unchanged."""
    divider_y: float = 0.0
    """Card-relative top y of ``paired-rect`` dividers. Primer: 10 (a 24px
    groove vertically breathing inside the 46px card). Unused by other modes."""
    divider_h: float = 0.0
    """Height of ``paired-rect`` dividers. Primer: 24."""
    canvas_pad_x: int = 0
    """Horizontal canvas margin (px) on each side of the strip card. ``> 0``
    (primer: 8) insets the card in a wider canvas so its drop shadow renders
    instead of clipping at the viewBox; the shared zone pipeline is wrapped in
    a ``translate(canvas_pad_x, canvas_pad_top)`` group so all zone coordinates
    stay card-space. ``0`` keeps card == canvas (chrome/cellular/default)."""
    canvas_pad_top: int = 0
    """Canvas margin above the card. Primer: 6."""
    canvas_pad_bottom: int = 0
    """Canvas margin below the card — larger than the top pad when the shadow
    falls downward (primer: 8, for the dy-positive feDropShadow falloff)."""
    glyph_inset: int = 12
    """Card-relative left inset of the bare identity glyph (no icon box).
    Default 12 is the value previously hardcoded in ``compute_strip_zones``;
    primer's specimen places the 18px glyph at x=18."""
    glyph_text_gap: int = 9
    """Gap between the bare glyph's right edge and the identity text. Default 9
    is the previously hardcoded value; primer declares 11."""
    identity_baseline_y: float = 0.0
    """Card-relative identity-text baseline. ``> 0`` (primer: 28) overrides the
    computed single-line baseline so the rendered baseline matches the specimen
    exactly. ``0`` keeps the computed placement for every other paradigm."""
    metric_label_baseline_y: float = 0.0
    """Card-relative metric-label baseline within the cell group. ``> 0``
    (primer: 16.5) overrides the profile default. Float counterpart of the
    owns-strip-only int ``metric_label_y``."""
    metric_value_baseline_y: float = 0.0
    """Card-relative metric-value baseline within the cell group. ``> 0``
    (primer: 33) overrides the profile default."""
    status_right_inset: float = 0.0
    """Distance from the card's right edge to the status-mark center. ``> 0``
    (primer: 18) pins the status pulse at ``content_width - inset`` instead of
    midpoint-centering it in the reserved status zone. ``0`` keeps the
    midpoint placement (chrome/cellular/default byte-identical)."""
    status_glyph_r: float = 0.0
    """Status-glyph housing radius override for the strip's state mark. ``> 0``
    (primer: 5.3 → ping core r 3.4 / ring stroke 1.6 via the shared ratio
    table) overrides the default 5.5. ``0`` defers to the default."""
    plate_corner: int = 0
    """Corner radius (px) of the strip plate as a rounded material card. ``> 0``
    (primer: 10) makes the content partial paint a rounded plate + bevel-edge
    stroke + perimeter hairline + drop shadow (a polished physical card). ``0``
    (chrome/cellular/brutalist) keeps the existing flat/owns-strip plate — the
    bevel/perimeter/shadow geometry the resolver emits is consumed only by content
    partials that opt in, so this is a pure no-op for the shipped genomes."""
    status_shape_rendering: Literal["crispEdges", "geometricPrecision"] = "crispEdges"
    show_status_indicator: bool = True
    """When False, the status-indicator zone (56px reserve) collapses to
    zero width -- strip omits the right-edge diamond/ring entirely. Set
    False for paradigms/compositions where the state carrier lives
    elsewhere (e.g. inside a metric-state cell)."""
    status_always: bool = False
    """When True, the editorial ACTIVE status light renders on EVERY strip
    regardless of stateless/stateful mode (primer's telemetry strip carries a
    universal live dot — numbers are heroes, state is a quiet annotation). When
    False (default), the stateless gate suppresses it so a STARS|FORKS|VERSION
    strip shows no indicator — preserving chrome/cellular/default behaviour."""
    flank_width: int = 0
    """Bifamily chromatic flank width in pixels (e.g. automata strips render
    36px teal/amethyst cell columns at left and right). Zero disables."""
    flank_cell_size: int = 12
    """Cell size for bifamily flank grids in pixels."""
    metric_text_x: int = 0
    """Pixel inset from the cell edge for metric label+value text. Read
    by :func:`compute_cell_layout` only when ``metric_text_anchor`` is
    ``start`` (inset from the left edge) or ``end`` (inset from the
    right edge). For the default ``middle`` anchor the text centers at
    ``cell_w / 2`` and this field is unused."""
    metric_text_anchor: Literal["start", "middle", "end"] = "middle"
    """SVG ``text-anchor`` for metric label+value. ``middle`` is the
    canonical strip layout shared across all production paradigms
    (brutalist, chrome, cellular). ``start`` / ``end`` flush text to
    the cell edge plus ``metric_text_x`` inset. One knob drives both
    label and value so they share the same anchor grid."""
    label_font_weight: int = 400
    """CSS-rendered weight for metric labels. The resolver measures with
    this weight via :func:`compute_cell_layout`; if the template's CSS
    class renders heavier or lighter, cells will be miscut."""
    label_letter_spacing_em: float = 0.0
    """CSS-rendered ``letter-spacing`` for metric labels in em units.
    The resolver MUST measure with the same value the CSS class applies
    — otherwise long labels (DOWNLOADS, COMMITS) bleed past the right
    divider while measurement reports the cell as fitting."""
    value_font_weight: int = 700
    """CSS-rendered weight for metric values. Brutalist/chrome render
    900; cellular renders Chakra Petch at 700. Resolver measures at
    this weight so cell width matches actual render."""
    value_letter_spacing_em: float = 0.0
    """CSS-rendered ``letter-spacing`` for metric values in em units."""
    cell_pad: int = 20
    """Horizontal breathing room inside each metric cell.
    ``cell_w = ceil(content_w + cell_pad)``."""
    cell_min_width: int = 0
    """Aesthetic floor for cell width. Brutalist legacy was 106 (kept
    cells from collapsing when values were short); cellular defers to
    content sizing (0)."""
    strip_pad: int = 16
    """Single shared padding source for ``owns_strip`` (brutalist) grammar.
    The identity zone right-pad = ``strip_pad`` and each metric ``cell_pad
    = 2 * strip_pad`` (pad on both sides). One knob moves the identity
    inset, inter-cell gap, and metric padding together — change it and
    every gap moves (the canary test pins this). Non-owns paradigms keep
    their own ``cell_pad``/``cell_min_width`` and ignore this field."""

    # v0.3.2 Phase C brutalist strip grammar — brutalist-only fields. When
    # ``owns_strip`` is True the parent ``strip.svg.j2`` skips its shared zone
    # pipeline (icon-box / glyph / identity / metric cells / status indicator)
    # and the paradigm's content partial assumes full responsibility for body
    # composition. Default zero / False preserves byte-equal output for chrome,
    # cellular, default paradigms. Adding ``owns_strip: true`` to a paradigm
    # YAML requires populating every strip-grammar field below to non-zero.
    owns_strip: bool = False
    """Strip-composition ownership flag. True: paradigm content-partial
    renders brand panel + dividers + metric cells + status zone itself; the
    parent template wraps its shared zone pipeline in
    ``{% if not paradigm_owns_strip %}`` to defer entirely."""
    brand_panel_x: int = 0
    """Brand panel left edge (px). Brutalist: 6."""
    brand_panel_width: int = 0
    """Brand panel width (px). Brutalist: 156."""
    triple_divider_x: int = 0
    """ACCENT-VOID-ACCENT / INK-SEAM-INK triple divider start x.
    Brutalist: 162 (= brand_panel_x + brand_panel_width)."""
    triple_divider_bar_width: int = 0
    """Width of the outer ink/accent bars in the triple divider. Brutalist: 3."""
    triple_divider_void_width: int = 0
    """Width of the middle void/seam bar in the triple divider. Brutalist: 2."""
    ornament_x: int = 0
    """Identity ornament left edge. Brutalist: 22."""
    ornament_y: int = 0
    """Identity ornament top edge. Brutalist: 19."""
    ornament_size: int = 0
    """Identity ornament side length. Brutalist: 14. This field also sizes
    the right-edge bookend placeholder square (rendered via
    brutalist-{dark,light}-content.j2). To resize the left identity GitHub
    glyph independently, set ``identity_glyph_size`` instead."""
    ornament_inner_inset: int = 0
    """Ornament inner-cutout inset (so inner = ornament_size - 2*inset).
    Brutalist: 3 (8x8 inner cutout in 14x14 outer)."""
    bookend_x: int = 0
    """Bookend ornament center x. Brutalist: 520."""
    brand_divider_x: int = 0
    """First metric-cell seam x (= triple_divider_x + 2*bar_w + void_w).
    Brutalist: 170."""
    metric_cell_width: int = 0
    """Uniform metric cell pitch (px). Brutalist: 100."""
    metric_label_y: int = 0
    """Metric label baseline y. Brutalist: 17."""
    metric_value_y: int = 0
    """Metric value baseline y. Brutalist: 36."""
    identity_text_x: int = 0
    """HYPERWEAVE identity text x. Brutalist: 50."""
    identity_text_y: int = 0
    """HYPERWEAVE identity text y. Brutalist: 30."""
    strip_width: int = 0
    """Total strip canvas width. Brutalist: 560."""

    strip_min_width: int = 0
    """Minimum total strip canvas width in pixels. When ``> 0``, the layout
    engine clamps the strip's total width to at least this value and pads the
    trailing edge after the bookend. Chrome: 320 (prevents 1-metric strips
    from aspect-warping in README columns). Zero (default) means no clamp —
    width grows additively from cells."""
    stretch_cells_to_min_width: bool = False
    """When True, adaptive strips distribute strip_min_width slack across
    metric cells instead of leaving transparent trailing canvas. Primer uses
    this to keep the specimen's full editorial rail while preserving measured
    per-cell text placement through the shared strip engine."""


class ParadigmBadgeConfig(FrozenModel):
    """Badge frame config within a paradigm."""

    default_size: Literal["default", "compact"] = "default"
    """Size class used when a request leaves ``ComposeSpec.size`` at
    ``"default"``. Cellular sets ``compact`` so automata badges use the
    small badge form by default while still allowing an explicit non-compact
    size request to use ``frame_height``."""
    label_font_family: str = "Inter"
    value_font_family: str = "Inter"
    label_font_size: float = 11
    value_font_size: float = 11
    label_font_weight: int = 700
    """CSS font-weight used by the rendered badge label. Resolver measurement
    must match template typography or centered ink bounds drift from the SVG."""
    value_font_weight: int = 700
    show_indicator: bool = True
    """When False, the status-indicator zone collapses. Cellular paradigm
    sets this False for version-mode badges and True for state-mode."""
    frame_height: int = 20
    """Default badge height when ``variant != "compact"``. Brutalist/chrome
    keep 20; cellular's XL class is 32."""
    frame_height_compact: int = 20
    """Height when ``variant == "compact"`` — defaults 20 (small-badge class)."""
    glyph_offset_left: int = 0
    """Legacy additional left-side offset for the glyph. Prefer
    ``left_adornment_*`` fields when a paradigm renders real bookend geometry,
    because those fields let the layout engine position content from the
    rendered adornment boundary instead of from an inverse offset."""
    glyph_offset_left_compact: int = 0
    """Compact-variant glyph offset. Empty (0) falls back to glyph_offset_left."""
    center_text_factor: float = 0.0
    """When ``> 0`` (primer: 0.35), the text baseline is COMPUTED to vertically
    centre the value at any badge height: ``text_y = height/2 + value_font_size *
    center_text_factor``. One scale-invariant rule, replacing a per-size
    ``text_y_factor`` that reads top-heavy when the badge shrinks. ``0`` falls back
    to the fixed ``text_y_factor``."""
    label_center_text_factor: float = 0.0
    """When ``> 0`` (primer: 0.4) the LABEL gets its own centred baseline
    ``height/2 + label_font_size * factor``, distinct from the value baseline.
    A smaller mono label optically centres ~0.5px higher than the larger value
    text at the same baseline, so the specimen sets label y=14.2 / value y=15.2 in
    a 22px frame. ``0`` falls back to the shared value baseline (one text_y)."""
    glyph_size: int = 14
    """Fallback glyph render box when no proportional ratio is declared."""
    glyph_size_compact: int = 0
    """Compact-variant glyph size. Empty (0) falls back to glyph_size."""
    glyph_size_ratio: float = 0.0
    """When >0, derive the glyph render box from ``frame_height * ratio``.
    This is the preferred path for paradigms that should share one visual
    glyph weight at the same badge height."""
    glyph_size_compact_ratio: float = 0.0
    """Compact-variant ratio. Empty (0) falls back to glyph_size_ratio."""
    glyph_size_max: int = 0
    """Optional upper bound for derived badge glyph sizes. Useful for taller
    badge variants that should keep the canonical compact identity weight."""
    text_y_factor: float = 0.69
    """Vertical placement of label/value text baseline as fraction of
    frame_height. Brutalist/chrome: 0.69. Cellular specimen: 0.656 (y=21 at
    height=32), which aligns the indicator visually with the text center."""
    sep_w: int = 0
    """Optional paradigm-specific separator width (left-panel boundary).
    When ``> 0``, overrides the profile's ``badge_sep_width``. Cellular
    paints a 1px gradient seam at ``x=lp_w`` (sep_w=1) but inherits the
    brutalist profile (badge_sep_width=2) — without this override, the
    resolver assumes 2px separator + 3px seam and places ``value_zone_left``
    1px past where the cellular template actually paints the value slab,
    drifting the centered text 1.5px right of the slab center."""
    seam_w: int = 0
    """Optional paradigm-specific seam width. ``> 0`` overrides
    profile's ``badge_seam_width``. Provided for symmetry with ``sep_w``;
    no current paradigm needs it but keeps the override surface uniform."""
    light_indicator_inner_ratio: float = 0.0
    """Inner status-dot radius as a fraction of the outer housing radius on the
    light circle indicator. ``> 0`` (primer: 0.5 — a status-light core inside a
    surface housing) overrides the legacy ``outer / 3`` dot. ``0`` keeps the
    brutalist-light proportion so that genome is unchanged."""
    right_canvas_inset: int = 0
    """Pixels between ``total_w`` and the value slab's right edge.
    Brutalist/chrome: 0 (slab spans to total_w). Cellular: 2 (inner canvas
    at ``x=2..width-2`` per cellular-content.j2:9). Without this override,
    ``value_zone_right`` lands ``right_canvas_inset`` past the actual slab
    edge and drifts the centered value text right by half that amount."""
    left_adornment_width: float = 0.0
    """Rendered right edge of the optional left adornment measured from x=0.
    Cellular large: 20 (= pattern x 2 + 3 cols * 6px). Zero disables
    adornment-aware placement."""
    left_adornment_width_compact: float = 0.0
    """Compact-variant rendered adornment right edge. Zero falls back to
    ``left_adornment_width``."""
    left_adornment_gap: float = 4.0
    """Gap between the rendered left adornment's right edge and the glyph.
    Only applies when ``left_adornment_width`` resolves above zero."""
    glyph_label_gap: float = 0.0
    """Optional gap between glyph right edge and label left edge. Zero falls
    back to the normal badge ``pad`` rhythm. Cellular sets this to match the
    bookend→glyph gap so the identity cluster reads symmetrically."""
    visual_gap: float = 0.0
    """Optional visible-ink gap used by centered-text paradigms. When ``> 0``,
    ``compute_badge_zones`` balances bookend/glyph/label/seam/value/right-edge
    transitions using rendered ink bounds instead of advance-box padding.
    Cellular uses this because its visible bookend makes the old 8px pad rhythm
    look asymmetric at compact badge scale."""
    left_adornment_start_x: int = 0
    """Left x-coordinate of optional rendered left adornment cells."""
    left_adornment_start_y: int = 0
    """Top y-coordinate for optional left adornment cells."""
    left_adornment_cols: int = 0
    """Column count for optional left adornment cells. Zero disables the
    adornment geometry contract."""
    left_adornment_rows: int = 0
    """Row count for optional left adornment cells."""
    left_adornment_cell_w: int = 0
    """Default cell width for optional left adornment geometry."""
    left_adornment_cell_h: int = 0
    """Default cell height for optional left adornment geometry."""
    left_adornment_cell_w_compact: int = 0
    """Compact-variant cell width. Zero falls back to ``left_adornment_cell_w``."""
    left_adornment_cell_h_compact: int = 0
    """Compact-variant cell height. Zero falls back to ``left_adornment_cell_h``."""
    indicator_size: int = 0
    """Optional paradigm-specific indicator side length. ``> 0`` overrides
    the profile's ``badge_indicator_size``. Brutalist v0.3.3 sets 10 to
    match the v16 badge matrix prototype (concentric 10x10 outline + 6x6
    inner bit). Zero (default) defers to the profile."""
    indicator_pad_r: int = 0
    """Optional paradigm-specific right padding for the indicator. ``> 0``
    overrides the profile's ``badge_indicator_pad_r``. Brutalist v0.3.3
    sets 10 so the 10x10 indicator anchors at x=138 in a 158px badge
    (matches prototype's ``translate(138,5)``). Zero defers to the profile."""
    indicator_stroke_width: float = 0.0
    """Optional paradigm-specific outer-ring stroke width for the indicator.
    ``> 0`` overrides the layout-engine default (1.2). Brutalist v0.3.3
    sets 1.5 to match the prototype's heavier ring weight. Zero defers
    to the default."""
    indicator_inner_bit_ratio: float = 0.0
    """Optional paradigm-specific inner-bit/outer-ring side-length ratio.
    ``> 0`` overrides the layout-engine default (0.5 — bit half of outer).
    Brutalist v0.3.3 sets 0.6 (10→6) to match the prototype's heavier
    inner mark. Zero defers to the default."""
    indicator_cap_ratio: float = 0.0
    """Indicator size as a fraction of the value-font size (its cap height), so
    the status glyph reads as one proportional accent sized to the text — square
    side, circle diameter, and diamond diagonal all equal ``value_font_size *
    cap_ratio``. ``> 0`` overrides the default 0.72 (Orbitron / JetBrains Mono cap
    height ≈ 0.72em). Replaced the fixed ``indicator_size`` / profile
    ``badge_indicator_size`` so the accent never exceeds the cap height."""
    indicator_shape: str = ""
    """Default state-indicator shape for this paradigm: ``square`` / ``circle``
    / ``diamond``. Selects the ``indicators/<shape>-indicator.j2`` partial via
    slug interpolation. chrome sets ``diamond``; brutalist/cellular leave it
    empty (the resolver coerces empty → ``square``). Genome ``state_glyph_shape``
    (per-variant or request-time ``?state_glyph_shape=``) overrides this."""
    content_center_geometric: bool = False
    """When True (primer), the brand glyph and state indicator centre on the badge
    MIDLINE (height/2) rather than the text-ink reading line. The value baseline
    already carries optical centring; the badge specimen places both marks
    geometrically at y=height/2. ``False`` keeps every other paradigm's reading-line
    anchoring byte-identical."""
    indicator_leads_value: bool = False
    """When True, the state indicator is placed at the LEFT of the value zone
    (leading the value text) instead of trailing it at the right edge. Primer's
    status-glyph reads as a pill ``[icon] value`` — the icon directly annotates
    the state word, matching the badge-matrix specimen. ``False`` (brutalist /
    chrome / cellular) keeps the trailing indicator, so those genomes stay
    byte-identical. The cursor walk in ``compute_badge_zones`` reserves the
    indicator slot before the value when set; ``indicator_center_x`` and the
    value zone shift accordingly with zero template arithmetic."""
    label_letter_spacing_em: float = 0.0
    """CSS-rendered ``letter-spacing`` for the label text. Resolver passes
    this to ``measure_text`` so the layout reserves the actual rendered
    width. Pre-v0.3.3 the resolver hardcoded ``0.06 if use_mono else 0.0``;
    paradigm-driven now so brutalist (0.06) and chrome (0.12) declare the
    measurement value alongside the template's ``letter-spacing`` attribute."""
    value_letter_spacing_em: float = 0.0
    """CSS-rendered ``letter-spacing`` for the value text. Brutalist's value
    text declares ``letter-spacing="0.04em"`` in the template; before this
    field landed the resolver passed ``0.0`` to measure_text and the badge
    layout under-reserved width by ``(n-1) * font_size * 0.04`` — visible as
    the value text overflowing the value zone by ~2.6px on a 7-char value."""
    rhythm_gap: int = 0
    """When ``> 0``, the badge layout engine uses a uniform interior rhythm:
    every interior gap (accent→glyph, glyph→label, label→seam, seam→value,
    value→indicator, indicator→right border) equals ``rhythm_gap`` pixels.
    Forces ``label_start = accent_w + rhythm_gap``, ``label_pad_r = rhythm_gap``,
    ``val_pad_l = rhythm_gap``, ``glyph_gap = rhythm_gap``, and disables the
    uppercase shy-from-seam adjustment. Zero (default) preserves legacy
    layout for chrome/cellular/default paradigms; brutalist sets 8 to match
    the v16 prototype's symmetric composition."""

    pad: int = 8
    """Equal-spacing constant (px) used by ``compute_badge_zones``. Every gap
    between PRESENT zones equals ``pad`` — left edge → glyph (when present),
    glyph → label (when present), label → panel separator, panel separator →
    value, value → state indicator (when present), state indicator → right
    edge. Absent zones collapse entirely so a glyph-less badge has no phantom
    slot. Brutalist 5, cellular 8, chrome 7. Independent from ``rhythm_gap``.

    Half-gap rule for seam: when ``seam_render_w > 0`` (chrome etched seam),
    the seam consumes ``pad/2`` on each side. Without this rule, a literal
    label+pad+seam+pad+value walk would produce ``2*pad + seam`` between
    label-end and value-start instead of the prototype's ``pad + seam``."""

    text_anchor: Literal["start", "middle"] = "middle"
    """SVG ``text-anchor`` value for label and value text. ``middle`` (default,
    brutalist + cellular) — layout emits center x positions. ``start`` (chrome
    paradigm) — layout emits first-character x positions, matching chrome's
    Orbitron typography with letter-spacing where centered alignment causes
    visual drift in narrow frames."""

    seam_render_w: float = 0.0
    """Width (px) of the etched seam slot between label and value zones. When
    ``> 0`` (chrome paradigm declares 1.0), the layout engine reserves this
    slot in the cursor walk and emits ``seam_left_x`` + ``seam_specular_x``
    for the chrome etched-groove rendering (two hairlines: dark cut + specular
    catch). When ``0`` (brutalist + cellular), the panel separator instead
    uses ``sep_w + seam_w`` (structural stroke + mark) at the panel boundary
    — the conventional brutalist/cellular badge composition."""

    seam_specular_offset: float = 0.0
    """Horizontal offset (px) of the specular-catch hairline from the dark-cut
    hairline in the etched seam. Chrome declares 0.6 to match the spatial
    study prototype. Only used when ``seam_render_w > 0``."""

    seam_gap_left: float = 0.0
    """Explicit gap (px) between the label's right edge and the seam slot.
    ``> 0`` (primer: 7) overrides the half-gap rule (``pad/2``) on the seam's
    label side, letting a paradigm declare an asymmetric label|seam|value
    rhythm. ``0`` keeps the half-gap rule (chrome byte-identical). Only used
    when ``seam_render_w > 0``."""

    seam_gap_right: float = 0.0
    """Explicit gap (px) between the seam slot and the value zone. ``> 0``
    (primer: 8) overrides the half-gap rule on the seam's value side. ``0``
    keeps the half-gap rule. Only used when ``seam_render_w > 0``."""

    rail_start_pad: float = 0.0
    """Explicit left-edge → first-zone gap (px). ``> 0`` (primer: 7) overrides
    the default ``pad`` for the leading gap only, so a paradigm can run a
    tighter entry than its interior rhythm. ``0`` keeps the uniform pad."""

    rail_end_pad: float = 0.0
    """Explicit last-zone → right-edge gap (px). ``> 0`` (primer: 8) overrides
    the default ``pad`` for the trailing gap only. ``0`` keeps the uniform
    pad."""

    accent_w: int = -1
    """Width (px) of the left accent bar zone. ``-1`` (default) defers to the
    resolver's flat-profile constant (4). Primer sets 0 — its rail starts at
    the badge edge with no accent column."""

    badge_corner: float = 0.0
    """Badge frame corner radius (px). ``> 0`` (primer: 4) overrides the genome
    ``corner`` for the badge clip + border geometry, so a paradigm can run a
    tighter chip radius than the genome's card radius. ``0`` defers to the
    genome value."""

    glyph_y_offset: float = 0.0
    """Per-paradigm vertical offset (px) applied to glyph_y AFTER frame-center
    placement. Addresses the perception that the glyph sits "too high"
    relative to label text. The frame-center calculation
    (height - glyph_size) / 2 produces a geometrically-centered glyph, but
    text visual-center may not equal frame center — chrome uses
    dominant-baseline=central (text visual center == y attr), brutalist and
    cellular use the default alphabetic baseline (visual center sits ~0.35 *
    font_size above baseline y). For paradigms where these differ, declare
    a positive offset to push the glyph down to the text visual center.
    Cellular default (h=32, font 9): 2.0. Brutalist: 0. Chrome: 0."""

    glyph_y_offset_compact: float = 0.0
    """Compact-variant override for glyph_y_offset. The text-visual-center vs
    frame-center delta scales with frame height and label font size —
    cellular's +2px offset at h=32 with 9px font is
    ~+0.67px at h=20 with smaller compact font. Applying the same offset
    verbatim to compact overshoots by ~1.3px (glyph sits below text). Set
    to 0 for compact variants where the text-baseline difference is
    negligible. Zero (default) inherits the main glyph_y_offset value."""

    min_total_width: int = 0
    """Aesthetic floor (px) for the total badge width. Zero defers to the
    layout engine's default (60). Chrome paradigm declares a smaller floor
    (40) because chrome's identity is content-driven shrinkage — a single-
    character X/1 badge should render as a tight chip, not a 60px block with
    visible dead space. Brutalist/cellular keep the 60px floor for chunkier
    legibility on small content."""
    text_visual_center_offset_em: float = 0.3
    """Distance from the label baseline to its visual center in em units.
    Alphabetic-baseline text uses ~0.3em. Paradigms that render badge text
    with dominant-baseline=central set this to 0 so glyphs align to the same
    center line the text uses."""


class ParadigmIconConfig(FrozenModel):
    """Icon frame config within a paradigm."""

    supported_shapes: list[str] = Field(default_factory=lambda: ["square", "circle"])
    default_shape: str = "square"
    viewbox_w: int = 0
    """Internal coordinate system width for the icon's ``viewBox``. Zero means
    "use the resolver's rendered ``width``" (default behavior — viewBox matches
    rendered size). Chrome paradigm sets 120 so the chrome icon templates can
    render the chrome icon specimen's 120-unit material discipline (r=46/r=42 bezel,
    96x96 card, 6-unit rail, 0.6-unit hairlines) at a 64px rendered size."""
    viewbox_h: int = 0
    """Internal coordinate system height for the icon's ``viewBox``. Zero means
    "use the resolver's rendered ``height``"."""
    # v0.3.0 cellular icon refresh — 48x48 with 5x5 living cell grid.
    # Cell + frame geometry pulled out of the template into paradigm config
    # so dimension changes don't require template edits and so render/glyphs.py
    # can read glyph_size + glyph_inset from a single source of truth.
    card_width: int = 0
    """Icon canvas width in pixels. Zero defers to resolver default (64).
    Cellular v0.3.0: 48."""
    card_height: int = 0
    """Icon canvas height in pixels. Zero defers to resolver default (64).
    Cellular v0.3.0: 48."""
    cell_grid_cols: int = 0
    """Cellular substrate grid column count. Zero disables substrate.
    Cellular v0.3.0: 5."""
    cell_grid_rows: int = 0
    """Cellular substrate grid row count. Zero disables substrate.
    Cellular v0.3.0: 5."""
    cell_size: int = 0
    """Substrate cell side length in pixels. Cellular v0.3.0: 8."""
    cell_gap: int = 0
    """Substrate inter-cell gap in pixels. Cellular v0.3.0: 1."""
    cell_rx: int = 0
    """Substrate cell corner radius. Cellular v0.3.0: 1 (rounded)."""
    inner_canvas_inset: float = 0
    """Distance from icon edge to inner canvas rect (left/top). Cellular v0.3.0: 10.08."""
    inner_canvas_size: float = 0
    """Inner canvas rect side length. Cellular v0.3.0: 27.84."""
    inner_canvas_rx: int = 0
    """Inner canvas corner radius. Cellular v0.3.0: 4."""
    glyph_inset: float = 0
    """Distance from icon edge to glyph SVG rect (left/top). Cellular v0.3.0:
    13.44 (centers the 21.12 glyph in the 48 canvas)."""
    glyph_size: float = 0
    """Glyph render box side length. Cellular v0.3.0: 21.12."""
    outer_border_rx: int = 0
    """Outer border corner radius. Cellular v0.3.0: 6."""


class ParadigmMarqueeConfig(FrozenModel):
    """Marquee frame config within a paradigm.

    Captures the discrete values that a marquee in this paradigm uses for
    dimensions, typography, separator rendering, and per-item text-fill
    behavior. Resolvers read from this so adding a new paradigm is a YAML
    change — never a Python edit.

    Default values match the v0.2.14-era 800x40 brutalist/chrome behavior, so
    paradigms that don't declare marquee config still render correctly.
    """

    width: int = 800
    """Marquee canvas width in pixels. Chrome: 1040. Brutalist: 720."""
    height: int = 40
    """Marquee canvas height in pixels. Chrome: 56. Brutalist: 32."""
    font_size: int = 13
    """Scroll-text VALUE font size in pixels. Chrome: 11 (Orbitron). Automata: 16."""
    label_font_size: int = 0
    """Ribbon LABEL font size in pixels (smaller than the value per the
    prototypes — chrome 6, automata 9). Zero falls back to ``font_size`` (label
    and value share one size). Module layout uses ``module_label_font_size``."""
    font_weight: str = ""
    """Scroll-text font weight. Empty string falls back to per-item override
    (resolver's bold-pattern logic). Chrome: '900'. Brutalist: '800'."""
    letter_spacing: str = ".5"
    """Scroll-text letter-spacing as a CSS string. May be ``"<n>px"`` or
    ``"<n>em"`` — the resolver converts em→px using ``font_size`` when
    measuring content width via ``measure_text``. Chrome: '0.18em'.
    Brutalist: '0.28em'."""
    font_family: str = ""
    """Scroll-text font-family CSS string. Empty falls back to profile's
    ``marquee_font_family`` (typically a mono stack). Chrome: Orbitron stack.
    Brutalist: JetBrains Mono stack."""
    tspan_palette: list[str] = Field(default_factory=list)
    """Per-item color cycle for bifamily-tspan marquees (genome-sourced hexes
    take priority — see resolver). Empty list keeps the default
    ``ink-primary/ink-secondary`` alternation."""
    separator_glyph: str = "■"
    """Separator character when ``separator_kind == "glyph"``. Cellular: ▪
    (neutral, label-sized). Default: ■. (Chrome no longer uses a glyph — its
    item_layout is ``module``, whose dividers replace inter-item glyphs.)"""
    separator_color: str = ""
    """Separator color (hex). Empty string falls back to the resolver's
    profile-driven ``var(--dna-border)`` default. Only consulted when
    ``separator_fill`` is unset (it is the fallback inside the
    ``var(--dna-signal, …)`` wrapper)."""
    separator_fill: str = ""
    """Explicit separator paint expression, bypassing the default
    ``var(--dna-signal, separator_color)`` wrapper. Set this when a paradigm's
    separators must NOT follow the variant signal accent — cellular uses
    ``var(--dna-ink-muted)`` so its bullets recede like the bone prototype's
    neutral ▪ instead of popping as a gold/cyan accent. Empty = use the
    signal-following wrapper (brutalist's per-variant emerald divider)."""
    separator_kind: Literal["glyph", "rect"] = "glyph"
    """How separators render: ``glyph`` emits a ``<tspan>`` of the
    ``separator_glyph`` character; ``rect`` emits a square ``<rect>`` of size
    ``separator_size`` x ``separator_size`` filled with ``separator_color``.
    Brutalist target uses 6x6 emerald rects between scroll items."""
    separator_size: int = 6
    """Edge length in px for ``separator_kind == "rect"`` bullet squares.
    Brutalist target: 6."""
    text_fill_mode: Literal["per_item", "gradient", "cycle"] = "per_item"
    """How scroll-text fill is computed: ``per_item`` lets the resolver assign
    per-item colors via the existing bifamily/ink-alternation logic;
    ``gradient`` applies a single gradient URL (``text_fill_gradient_id``) to
    every item — chrome target uses this with the chrome-text gradient;
    ``cycle`` rotates through ``text_fill_cycle`` colors per item position —
    brutalist target uses this with ``[ink, info]`` alternation."""
    text_fill_gradient_id: str = ""
    """When ``text_fill_mode == "gradient"``, this gradient ID is referenced
    by every scroll item's ``fill="url(#...)"``. Templates emit the gradient
    in ``{paradigm}-defs.j2`` and the ID is paradigm-defined. Chrome: ``ct``
    (chrome-text). The full ``url(#{{ uid }}-{{ text_fill_gradient_id }})``
    construction happens in the resolver."""
    text_fill_cycle: list[str] = Field(default_factory=list)
    """When ``text_fill_mode == "cycle"``, items rotate through these hex
    colors per position. Brutalist: ``["#D1FAE5", "#34D399"]`` (ink, info)."""
    clip_inset_left: int = 0
    """Left-edge clip inset for the scroll-track in pixels. Excludes the
    perimeter zones from text rendering so scrolling characters can't appear
    visibly on top of the frame chrome (env-rail, accent bar, bezel). Chrome
    paradigm: 4 (chrome bezel width). Brutalist: 4 (accent bar width).
    Default: 0 (no clip — full viewport)."""
    clip_inset_right: int = 0
    """Right-edge clip inset. Chrome: 4 (chrome bezel). Brutalist: 1 (perimeter)."""
    clip_inset_top: int = 0
    """Top-edge clip inset. Chrome: 4 (chrome bezel). Cellular: 1 (top hairline)."""
    clip_inset_bottom: int = 0
    """Bottom-edge clip inset. Chrome: 4 (chrome bezel). Cellular: 1 (bottom hairline)."""
    clip_rx: float = 0
    """Corner radius for the scroll-track clip rect. Chrome: 2.6 (matches well
    rx). Brutalist/cellular: 0 (sharp corners)."""

    # ── v0.3.12 scroll-item layout dispatch ──────────────────────────────
    # The scroll-item layout is selected by this CONFIG VALUE, never by a
    # paradigm-slug branch (Invariant 12). The template resolves
    # `frames/marquee/item-{item_layout}.j2`, so chrome + cellular
    # both pick `item-ribbon.j2` while brutalist picks `item-module.j2`. Two
    # paradigms can resolve to the same partial.
    item_layout: Literal["ribbon", "module"] = "ribbon"
    """``ribbon``: inline label+value at one absolute x (chrome/cellular).
    ``module``: a fixed-width cast cell — small mono label stacked over a
    bold condensed value, bounded by a full-height divider (brutalist
    instrument-panel grammar). Dispatches the item partial; never branch on
    the paradigm slug."""
    hero_font_size: int = 0
    """Font size (px) for the hero (first volume) cell's value. Zero defers
    to ``font_size`` (no hero emphasis). Brutalist module: 22 (vs 20 body)."""
    # Module-layout geometry (consumed only when item_layout == "module").
    module_min_width: int = 0
    """Aesthetic floor for the computed uniform module pitch (px). The engine
    sizes the module from MEASURED content (widest label/value + 2*inset),
    then clamps up to this floor. Brutalist: 110. Zero disables the floor."""
    module_text_inset: int = 16
    """Left inset (px) of the label/value text from the module's left edge."""
    module_label_y: int = 14
    """Baseline y of the module's small mono label."""
    module_value_y: int = 35
    """Baseline y of the module's bold condensed value (stacked below label)."""
    module_label_font_size: int = 8
    """Font size (px) of the module label. Brutalist: 8."""
    module_label_font_family: str = ""
    """Module label font stack (mono). Empty falls back to ``font_family``."""
    module_label_letter_spacing: str = "0.12em"
    """CSS letter-spacing for the module label."""
    module_value_font_family: str = ""
    """Module value font stack. Brutalist: Barlow Condensed (an instrument-
    panel condensed face distinct from the genome's mono identity — a
    paradigm-level typographic choice, like ParadigmBadgeConfig.value_font_family).
    Empty falls back to ``font_family``. Measured with its first component so
    the uniform module pitch matches the rendered value width."""
    module_divider_w: int = 2
    """Width (px) of the full-height divider at each module's right boundary."""
    module_divider_y: int = 6
    """Top y of the module divider."""
    module_divider_h: int = 32
    """Height (px) of the module divider."""
    module_divider_opacity: float = 1.0
    """Opacity of the module divider. Primer uses 0.12 (a low-opacity cobalt
    hairline at the gap midpoint, not a hard full-opacity bar). Default 1.0 keeps
    brutalist's opaque divider byte-equal."""
    cap_kind: Literal["none", "identity"] = "none"
    """Left identity cap rendered ABOVE the scroll track. ``identity`` (primer)
    paints a fixed head band carrying the brand glyph, a scope label (spec.title),
    a quiet ``LIVE`` mark, and a single breathing pulse dot — the signature the
    porcelain marquee specimen leads with. ``none`` (chrome/brutalist/cellular)
    keeps their existing decorative liveness (diamond / strobe-cube). The cap zone
    is reserved by ``clip_inset_left`` so modules scroll under the cap seam."""
    hero_color_role: str = ""
    """Color role for the hero (first volume) value when the paradigm declares no
    text-fill gradient. Empty = the legacy ``var(--dna-ink-primary)`` ink hero.
    ``signal`` routes the hero to ``var(--dna-signal)`` (primer's cobalt hero —
    the one accent-colored value). Gated so chrome's gradient hero + brutalist's
    ink hero stay byte-equal."""
    state_value_stop: Literal["bright", "core"] = "bright"
    """Which state-cascade stop the activity (stateful) cell values use.
    ``bright`` (default) → ``var(--hw-state-value)`` (the bright stop, tuned for
    dark substrates). ``core`` (primer) → ``var(--hw-state-signal)`` (the deeper
    core stop, readable on light grounds — forest/sienna/red vs lime/orange/coral)."""
    module_label_color: str = ""
    """CSS fill for module category labels. Empty (chrome/brutalist) keeps the
    legacy ``var(--dna-ink-muted)``. Primer sets ``var(--dna-label-text)`` so the
    marquee column label resolves to the SAME genome chromatic label value as the
    badge label, stats card label, and strip column header — one label system."""


class MatrixVoice(FrozenModel):
    """One named type voice for the matrix frame.

    Voices are defined once in the paradigm defs CSS (``.{uid}-{voice}``)
    and referenced by ``CellPlacement.cls``; the layout solver measures
    text with the same family/size/weight tuple the CSS renders, keeping
    measurement and rendering coupled.
    """

    family: str = "JetBrains Mono"
    size: float = 11.0
    weight: int = 400
    tracking_em: float = 0.0


class ParadigmMatrixConfig(FrozenModel):
    """Matrix frame chassis config within a paradigm.

    Defaults are extracted from the six porcelain-final matrix specimens
    (matrix design targets, all 900 wide). Cell-kind geometry and
    the semantic palette are frame-generic and live in ``data/config/matrix-frame.yaml``
    instead — the paradigm owns the chassis, the engine config owns the
    cells.
    """

    width: int = 900
    """Matrix width CEILING. The frame adapts to its content: the solved
    width is ``clamp(content width, min_width, width)`` — 900 is the
    maximum, not a constant. Bar matrices pin to the ceiling (a shared
    magnitude axis wants room); height is always content-solved."""
    min_width: int = 600
    """Width floor. High enough that a proofset of adaptive matrices reads
    as ONE design system (600-900 band), not a scatter of card sizes —
    and narrow tables keep room to breathe."""
    card_radius: float = 14.0
    margin_x: float = 34.0
    masthead_h: float = 93.0
    """Masthead block height; the ink rail sits at its bottom edge — 20
    below the descriptor baseline (the g-generation specimens' rhythm:
    title 54, descriptor 73, rail 93)."""
    masthead_collapsed_h: float = 18.0
    """Masthead height when the spec carries NO title, subtitle, or
    headline: the zone collapses to breathing room and the rail, scan, and
    legend are suppressed — empty slots release their space (the stats-card
    slot-removal principle, handled once in the spatial engine)."""
    colheader_h: float = 33.0
    """Column-header block height; the header rule closes it."""
    row_pitch: float = 40.0
    row_pitch_compact: float = 34.0
    """Tightened pitch applied past the soft row cap."""
    content_row_base: float = 46.0
    """Minimum row height in content (chip-wrapping) mode."""
    section_band_h: float = 28.0
    """Section band height — a full-bleed wash flush at the section top
    (tiers specimen: 28px tall, x=8 to width-8)."""
    section_band_opacity: float = 0.024
    """Section band ink wash (specimen 0.024) — slightly more present than
    zebra stripes so groups read as structure."""
    summary_h: float = 61.0
    axis_h: float = 30.0
    footer_h: float = 44.0
    footer_gap: float = 16.0
    """Minimum clear gap between the footer notes (left, start-anchored) and
    the brand mark (right, end-anchored). When the notes outrun the available
    span the layout truncates them to preserve this gap — a clearance rule, so
    notes and brand never collide for ANY notes length or table width."""
    label_col_min: float = 140.0
    label_col_max_ratio: float = 0.4
    """Label column ceiling as a fraction of the content width."""
    max_col: float = 240.0
    """Per-column width ceiling for content-sized (non-flexible) columns."""
    cell_pad_x: float = 12.0
    hero_tab_ratio: float = 0.52
    """Hero cap-tab width as a fraction of the hero column width."""
    hero_tab_h: float = 3.0
    section_indent: float = 10.0
    """Left indent applied to section-member row labels so grouped fields
    step in under their section header (the tiers-prototype hierarchy:
    member labels at x=44 against the band header's 34)."""
    desc_line_h: float = 19.0
    """Height of the masthead descriptor line (the subtitle baseline sits
    this far below the title's). A spec without a subtitle releases it —
    the rail rides up and the title-to-table gap collapses."""
    hero_lane_opacity: float = 0.055
    stripe_opacity: float = 0.012
    """Zebra/section band wash. Quiet by design — rows must never compete
    with the metric cells for the eye."""
    guide_opacity: float = 0.06
    scan_duration: str = "6.472s"
    """Masthead scan-rail period (4φ x rhythm base)."""
    scan_w: float = 220.0
    scan_h: float = 1.4
    title_voice: MatrixVoice = Field(
        default_factory=lambda: MatrixVoice(family="Inter", size=29, weight=800, tracking_em=-0.02)
    )
    """One title size at every width — 29px holds its own on a 600px card
    without shouting at 900."""
    desc_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=10.5))
    colhead_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=8.5, weight=700, tracking_em=0.12))
    colhead_sub_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=6.5))
    row_label_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=12.0, weight=700))
    row_label_sub_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=11.0, weight=600))
    """Section-member row labels: quiet field names, secondary to the cell
    pattern (tiers specimen: mono 600 at 11px) — one step down from the
    primary row-title voice flat tables use."""
    row_sub_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=9.0))
    cell_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=11.0, weight=600))
    cell_strong_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=12.5, weight=700))
    section_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=9.5, weight=700, tracking_em=0.1))
    axis_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=8.0))
    chip_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=9.0))
    pill_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(family="Inter", size=11.0, weight=700))
    foot_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=9.0))
    foot_brand_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=9.0, tracking_em=0.22))
    """Brand mark voice — the ``.foot-brand`` CSS adds ``letter-spacing: 0.22em``
    (primer-defs.j2), so the mark renders wider than plain ``foot_voice``.
    Measuring the brand at its true tracked width is what makes the footer
    clearance honest rather than a fudged offset; keep ``tracking_em`` in sync
    with that CSS rule."""
    headline_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=9.5, weight=700))
    summary_value_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=14.5, weight=700))
    summary_hero_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=16.5, weight=700))
    summary_qual_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=8.5))
    summary_text_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=9.0, weight=600))
    """Summary cells holding phrases rather than scores (tiers' USE-FOR
    row): quiet mono 600 at 9px — numbers are heroes, words annotate."""


class DiagramRhythm(FrozenModel):
    """System-wide vertical rhythm for one node class (default / hero) — the
    paradigm ROOT law every topology family inherits when its own block
    doesn't cite an override (the post-load merge in
    ``ParadigmDiagramConfig._resolve_topology_rhythm``, ``node``/``hero``
    fields below). Values are the primer_diagram_language sheet's own
    measured law, not a geometry-agnostic guess: ``node`` is the uniform
    165x76 satellite (model-router's own preset citation: pad_y 22,
    label_desc_gap 7.5); ``hero`` is the 206x104 router hero (fanout-
    horizontal's own topology citation: pad_y 25.5, label_desc_gap 8.5,
    desc_line_pitch 18). A family whose OWN hand specimen measures a
    different rhythm (dag/state-machine's 62-tall two-row cards) cites its
    own override on that family's ``node:``/``hero:`` block; every other
    family inherits this without ever touching a number.

    Every field is REQUIRED (no default) — an incomplete root declaration is
    a Pydantic validation error at paradigm load, naming the missing field,
    never a silent fallback to a bare geometry-agnostic constant."""

    pad_y: float
    label_desc_gap: float
    desc_line_pitch: float
    max_desc_lines: int


class DiagramNodeChassis(FrozenModel):
    """Card-anatomy geometry for one node class (default / hero / ring-2).

    Offsets are from the card TOP edge; the solver anchors hero text from
    the card CENTER instead (role logic, not chassis data). Glyph-circle
    anatomy lives on the topology chassis (``circle_r`` family) because the
    radius is a per-topology read, not a per-class one.
    """

    w: float = 160.0
    h: float = 64.0
    rx: float = 13.0
    dot_inset_x: float = 20.0
    """Accent-dot center inset from the card left edge."""
    dot_dy: float = 26.0
    label_dy: float = 30.0
    desc_dy: float = 47.0
    desc_line_pitch: float = -1.0
    """Desc-line-to-desc-line pitch for a wrapped multi-line desc. ``-1``
    (an impossible pitch) inherits the paradigm ROOT rhythm
    (``ParadigmDiagramConfig.node``/``.hero``, resolved by node class at
    paradigm load) — no family ever falls to a bare geometry-agnostic
    constant, and no consumer ever sees the sentinel; a family whose own
    hand specimen measures a different pitch cites its own override."""
    max_desc_lines: int = -1
    """Desc wrap ceiling for this node class. ``-1`` inherits the paradigm
    ROOT rhythm, same law as ``desc_line_pitch``."""
    label_gap: float = 14.0
    """Dot-center to label-start gap."""
    glyph_inset_x: float = 22.0
    """Content-anchor law: the glyph column's LEFT inset from the card edge.
    A card's content group LEFT-ANCHORS here and slack accrues on the right —
    never per-card centering, which makes the text column a function of
    sibling text variance (primer_diagram_language's providers all seat their
    glyph at card+22 / text at card+60 down a 6-card column;
    pp-dag-serving-v2's rank cards measure the same 664→686→724). Also the
    symmetric minimum pad the width solve reserves each side, so a snug card
    reads balanced and a pinned-wide card pools its slack right like every
    wide hand specimen (pp-gateway-refined's 210 tiers, both convergence
    sets)."""
    glyph_label_gap: float = 14.0
    """Glyph ink-edge to text-column gap (primer_diagram_language providers:
    869.5+24 → 907.5; pp-dag-serving-v2: 686+24 → 724). The axial nucleus
    declares its own wider pair (32/18.4 — the verb-algebra sheet's 232x112
    crown measures text at card+82)."""
    pad_x: float = 12.0
    """Horizontal text padding used by truncation."""
    pad_y: float | None = None
    """Vertical ink-block pad for content-solved heights. ``None`` inherits
    the paradigm ROOT rhythm (``ParadigmDiagramConfig.node``/``.hero``,
    resolved by node class at paradigm load — never the bare geometry-
    agnostic ``min_pad_y``). The hub nucleus declares its own: the
    verb-reads specimen (92 tall, two rows) and the hub specimen (120 tall,
    three rows) both measure ~28px of air above and below the block."""
    label_desc_gap: float | None = None
    """Name-baseline to first-desc-baseline air for THIS node class — every
    anatomy reads it through one resolver (``sizing.label_desc_gap_for``):
    CARD/HERO via ``solve_card_box`` / ``place_card``'s ``_slot_vertical``,
    HEAD via ``solve_head_box``/``place_head``. ``None`` inherits the
    paradigm ROOT rhythm (resolved at paradigm load, same law as ``pad_y``).
    The primer_diagram_language sheet's own two hero families disagree even
    though they share hero voices (17/11): the router hero (206x104, name
    38.6, name->desc gap 21) measures ~9; the axial nucleus (232x112, name
    40, gap 24) measures ~12 — a wider crown, more generous air, not a
    font-size ratio. The uniform 165x76 satellite (name 33.9, gap 19,
    name/desc 15/11) measures ~7.5 — that satellite figure (rounded to 7.5)
    plus its own pad_y (22) IS the paradigm root's ``node`` rhythm; the
    router hero's 25.5/8.5/18 is root's ``hero`` rhythm. The citations here
    are what let a hero without an explicit ``hero.h`` reach the sheet's
    generous rhythm on content alone."""
    glyph_w: float = 0.0
    """Identity-mark advance override for THIS node class (0 = the style
    default GLYPH_MARK_W). The language specimen: only the AXIAL nucleus carries the 32 glyph
    (verb-algebra); the fanout hub keeps the standard 24 — a global hero-32
    truncated the router's identity inside its 206 chassis."""
    head_pad_y: float | None = None
    """Vertical air above/below the HEAD anatomy's glyph+text stack
    (``sizing.solve_head_box`` / ``chrome.place_head`` only — the label-row
    / portrait CARD anatomies read the separate ``pad_y`` above). ``None``
    keeps the kit's box-centering baseline (rag-pipeline/tree/flywheel-orbit
    render byte-identically); a declared value anchors the stack at this
    FIXED pad instead of splitting a chassis pin's slack in half, falling
    back to centering if the declared pad plus snug content would overflow
    the box."""
    head_glyph_gap: float | None = None
    """Glyph-bottom to name-top gap for the HEAD anatomy's stacked block.
    ``None`` keeps ``HEAD_GLYPH_GAP`` (7px — the rag-pipeline/tree/flywheel-
    orbit measurement). The hub-panel-02-orchestrator specimen's compass
    hero measures a 26.42px gap here (icon [380,401] to name baseline 440,
    box top 352, 22px icon, 17px/700 Inter name at .74 ascent) — a chassis
    pin (136) taller than the snug glyph+text stack (135.3 at this gap)
    puts its extra air BETWEEN the icon and the identity block, not at the
    pad: the icon rides close to the card's top edge while name+desc anchor
    low with their own tight rhythm."""


class DiagramTopologyChassis(FrozenModel):
    """Per-layout-slug geometry. A union chassis: each solver reads the
    fields its algorithm consumes (documented per field); the rest keep
    defaults. Constants are extracted from the topology specimens
    (``v04/specimens/diagrams/diagram-topologies/``) canon.
    """

    aspect: str = "banner"
    """banner | square | portrait — the embedding contract."""
    width: int = 760
    """Canvas width. Tree and sequence treat it as a ceiling/solve target;
    everything else renders it fixed."""
    height: int = 0
    """Canvas height; 0 = solved from content (fan columns, stacks)."""
    display_w: int = 0
    display_h: int = 0
    """Rendered width/height attributes; 0 = same as the canvas. Banners
    display at <=760 so a README column never downscales type."""
    width_floor: bool = False
    """Whether ``width`` is a hard canvas floor (canvas = max(width, content))
    or only the SCALE REFERENCE (canvas hugs content + margins; the render
    scale holds display_w/width so cards keep ONE physical size across node
    counts, with no phantom centering slack — the content-fit law). True only where the
    specimen wants a fixed/near-fixed frame (stack, comparison, the fan
    family, flywheel, tree-radial)."""
    zone_content_gap: float | None = None
    """Zone-header air: kicker baseline to content-ink top, px. None reads
    the engine-wide ``annotate.zone_header_gap`` (48, cited to the
    verb-algebra sheet) — a single-family constant that under-provisions
    every other family's masthead air (the ring hand file holds ~4x it)."""
    caption_gap: float | None = None
    """Caption air: the content region's bottom margin before the caption
    band, px. None keeps the engine defaults (24, or 40 above a band
    annotation) — calibrated so the RENDERED content-ink-to-caption band
    matches the family's hand file; the parity plate law grades the output,
    this input steers it."""
    caption_pad: float | None = None
    """Caption-to-canvas-edge pad, px. None reads the engine-wide
    ``annotate.caption_bottom_pad`` (44, the v4 reference sheets) — the v3
    prototype sheets pad tighter (24-36), per family."""
    focal_run: float = 0.0
    """Edge-run citation for the fan-linear families: the FACE-TO-FACE run
    between the member column and the focal card (convergence: members'
    right edges to the hero's west face — the gathered-seed hand file runs
    524). When set, positions and the canvas DERIVE from cards + this run
    (gaps are the citation, never node x/y); 0 keeps the legacy fixed-frame
    placement."""
    margin_x: float = 40.0
    margin_top: float = 24.0
    header_mode: str = "left"
    """left | center | none."""
    header_h: float = 80.0
    """Vertical band the title/subtitle occupy before content starts."""
    footer_h: float = 44.0
    footer_dy: float = 16.0
    """Footer baseline rises this far above the canvas bottom."""
    node: DiagramNodeChassis = Field(default_factory=DiagramNodeChassis)
    hero: DiagramNodeChassis = Field(default_factory=lambda: DiagramNodeChassis(w=188.0, rx=16.0))
    hero_declared: frozenset[str] = Field(default_factory=frozenset)
    """Which ``hero`` fields a PRESET explicitly set (``apply_spec_chassis``
    populates this from the preset's own ``chassis.hero`` dict — never from
    the paradigm-level default, which always constructs ``hero.w``/``.h``
    too, making ``model_fields_set`` unable to tell citation from default).
    ``"w" in hero_declared`` marks ``hero.w`` a specimen citation: a hard
    floor a solver should honor regardless of measured dominance. Undeclared,
    a hero's floor is content + measured dominance (G3), never the paradigm
    archetype width/height a caller never asked for."""
    node2: DiagramNodeChassis = Field(default_factory=lambda: DiagramNodeChassis(w=120.0, h=40.0, rx=12.0))
    """Ring-2 node class (tree-radial grandchildren)."""
    circle_r: float = -1.0
    """Glyph-circle radius for default nodes. ``-1`` (an impossible radius)
    inherits the paradigm ROOT radius (``ParadigmDiagramConfig.circle_r``,
    resolved at paradigm load — the bilateral canon,
    hw-diagram-alpha3-canon.html "Integration Hub v2": satellites r=30) —
    never the bare geometry-agnostic 24, and no consumer ever sees the
    sentinel. A family whose own hand specimen measures a different radius
    (flywheel-circles' r44 medallions, a PRESET-level citation) cites its
    own override."""
    hero_circle_r: float = -1.0
    """Glyph-circle radius for the hero/hub node. ``-1`` inherits the
    paradigm ROOT radius (``ParadigmDiagramConfig.hero_circle_r`` — the same
    canon citation: hub r=44), same law as ``circle_r``."""
    circle_label_dy: float = 18.0
    """Label baseline offset below a glyph-circle's bottom edge."""
    node_style: str = ""
    """Per-topology default anatomy; empty falls back to card."""
    join_trunk: float = 44.0
    """AND-join trunk length (dag specimens): >=2 edges converging on one mouth
    meet at a gather knot floated this many px before the sink; one solid
    trunk carries them home."""
    join_trunk_bare: float = 0.0
    """Chipless join-trunk length — the join mirror of ``depart_trunk_bare``:
    when NO converging edge carries a chip, the trunk collapses to this
    (default 0 = FLUSH: members run to the mouth, the gather ring seats ON
    the sink's face — half occluded by the card, exactly like a trunk-less
    depart's knot — and no bare arrowed trunk dangles). ``join_trunk``
    stays the cargo case's citation floor."""
    depart_trunk: float = 0.0
    """Depart-trunk length (router specimens): the fan leaves its source on ONE
    wire to a knot floated this many px out, then spreads. 0 = no trunk;
    only topologies whose specimen carries the trunk declare it. This is the
    CHIP-BEARING length (chip_along + balanced stubs); a chipless fan uses
    ``depart_trunk_bare``."""
    depart_trunk_bare: float = 0.0
    """Chipless depart-trunk length: when NO fan edge carries a chip, the trunk
    shrinks to this shorter departure gesture so a bare wire doesn't dangle
    (Eli: "when the edge chip isnt there, the long line still remains and looks
    awkward"). 0 = fall back to ``depart_trunk`` (no cargo rule)."""
    hero_min_w: float = 0.0
    """Hero WIDTH floor (0 = content-carried). The specimens split: some
    crowns enlarge beyond their content (convergence's 280 nucleus),
    others sit at sibling size (kernel-bottleneck); a topology/preset that wants
    the guaranteed crown declares the floor here."""
    edge_label_cls: str = "elbl"
    """Class for SOLVER-ANCHORED edge labels (sequence messages, SM
    transitions): "elbl" = the tracked floating micro-label (piece 8,
    census-counted); "msg" = native message text (auth-sequence's uncounted
    seq-msg voice). Fallback-floated labels are always micro-labels."""
    node_anatomy: str = ""
    """Card LAYOUT variant for the card/card+glyph styles: "" = label-row
    (mark left of the name), "head" = the stacked portrait column (glyph
    centered ABOVE the name, desc lines beneath — rag-pipeline stages,
    tree rows, flywheel-orbit phases, the sequence participant head)."""
    desc_voice_size: float = 0.0
    """Per-topology desc voice size override (0 = the paradigm desc voice).
    Lands at ONE seam (``effective_diagram_cfg``) so measurement and the
    emitted CSS agree. The obi-engine specimen's node descs are 10px against the kit's
    11 — at 11 three obi descs wrap and the swimlane widens past its own
    specimen."""
    desc_voice_tracking_em: float | None = None
    """Per-topology desc tracking override (None = the paradigm desc voice).
    The obi-engine specimen declares no desc letter-spacing where the kit tracks
    0.01em — on a 37-char desc that is the 3.7px between fitting the
    specimen's envelope and wrapping."""
    width_policy: str = "free"
    channel_run_min: float = 0.0
    """Wire-major compositions (K3): when EVERY edge is a reciprocal pair,
    the channel is the subject — each lane run must show enough dash
    periods to read as a conversation. 0 keeps the node-major solve."""
    return_inset: float = 60.0
    """Pipeline return-sweep (artifact-roundtrip): control-point x inset from each
    endpoint — the symmetric flat-bottom cubic's horizontal reach."""
    return_depth: float = 168.0
    """Pipeline return-sweep: base dip depth below the deepest card the
    sweep passes under (G7 bisection extends it further if that's not
    enough clearance)."""
    """free | aligned (G3 slack rule). Free topologies content-solve each
    card — slack never exceeds the symmetric pads; aligned topologies (rank
    and row cohesion) share the max over members, and the centered content
    group splits the remaining slack evenly."""
    gap: float = 60.0
    """Pipeline connector gap / tree leaf gap / stack layer gap."""
    pitch: float = 64.0
    """Fan/convergence column pitch; bilateral side pitch."""
    hero_ratio: float = 1.175
    """Pipeline hero width as a multiple of the solved unit width."""
    card_min_w: float = 120.0
    leaf_min_w: float = 140.0
    leaf_max_w: float = 220.0
    bottom_m: float = 32.0
    ring_r: float = 172.0
    """Flywheel phase-card ring / radial-fan dest ring base radius."""
    arc_r: float = 178.0
    arc_clear_deg: float = 1.2
    """Extra angular clearance past each card's angular half-width."""
    ring_gap: float = 80.0
    """Radial perimeter spacing driving R growth past the base radius."""
    src_gap: float = 40.0
    """Upward fan: gap between the last dest row and the source card."""
    row_cap: int = 3
    row_gap: float = 54.0
    op_r: float = 11.0
    """Stack inter-layer operator ring radius (stack)."""
    op_cross: float = 4.0
    """Stack inter-layer operator cross half-span (stack)."""
    lifeline_gap: float = 85.0
    """Sequence: horizontal gap between lifeline header cards."""
    msg_pitch: float = 56.0
    first_msg_dy: float = 34.0
    """First message drops this far below the lifelines' top."""
    act_w: float = 8.0
    act_pad_top: float = 12.0
    act_pad_bottom: float = 4.0
    legend_dy: float = 24.0
    """Sequence key-legend baseline above the footer line."""
    rank_gap: float = 145.0
    """DAG: horizontal gap between rank columns (card edge to card edge)."""
    rank_pitch_max: float = 120.0
    skip_drop: float = 6.0
    """DAG skip-edge channel clearance below the content band."""
    port_stagger: float = 12.0
    """Shared-east-face in/out separation: when an authored under-elbow ENTERS a
    node's east face while a plain edge EXITS that same face, the exit sits
    half this above center and the elbow lands half below — two distinct wires,
    never one fused ~18px cable (calibrated on the shared-face stagger probe in
    tests/compose/test_diagram_port_stagger.py; step matches _fan_offsets' 12px)."""
    skip_stack: float = 12.0
    over_arc_clear: float = 18.0
    """DAG over-top skip: the channel run's clearance ABOVE the shallowest card
    top. The service-dependencies specimen draws it 16px over the top rank, but the run passes a
    NON-incident card, so it holds the structural min_clearance (18) floor —
    2px over the specimen, imperceptible, and the G7 clearance law stays intact
    rather than being exempted for the idiom."""
    over_arc_r: float = 7.0
    """DAG over-top skip: the orthogonal corner radius where the vertical riser
    meets the horizontal channel run — the specimen's crisp 7px Q corners, not
    a wide cubic sweep."""
    chain_gap: float = 55.0
    drop_gap: float = 50.0
    """State machine: branch drop length from baseline pill bottom."""
    drop_dy: float = 92.0
    """Below-baseline pill center offset from the baseline center."""
    loop_dx: float = 75.0
    loop_dy: float = 20.0
    stub_len: float = 14.0
    tag_dy: float = 14.0
    r1: float = 160.0
    ring_chord_gap: float = 44.0
    """tree-radial packing: minimum chord clearance between ring siblings
    (G6) — angular entitlement is need x this, never the full circle."""
    """Tree-radial ring-1 radius."""
    r2: float = 280.0
    # ── Content-sized card bounds (G3 extension) ────────────────────────
    h_max: float = 0.0
    """Card height ceiling for desc-wrapped content sizing; 0 = no ceiling
    (fall back to the node chassis ``h``)."""
    w_max: float = 0.0
    """Card width ceiling for content sizing; 0 = fall back to node ``w``."""
    # ── Hub union-chassis fields ────────────────────────────────────────
    hero_circle_r_hub: float = 44.0
    """Hub center-node circle radius (square aspect, fanout-radial
    precedent)."""
    ring_r_hub: float = 210.0
    """Hub spoke ring base radius (per-zone growth stacks outward)."""
    hub_clearance: float = 170.0
    """Compass spoke air: edge-to-edge clearance between the hub RECT and a
    satellite rect along the spoke direction. The specimens hold this
    near-uniform per axis (hub 167-220, verb-reads 230) — a
    center-radius ring collapsed E/W clearance to ~44px beside a wide hub
    while N/S kept ~170, the massive-hub/short-arrows read."""
    # ── Lanes union-chassis fields ──────────────────────────────────────
    lane_header_h: float = 44.0
    """Lanes: height of a category band's header strip."""
    gutter_w: float = 86.0
    """Lanes: width of the inter-lane gutter the adjacent-bus router uses."""
    row_pitch: float = 80.0
    """Lanes: vertical pitch between stacked rows within a band."""
    lane_w_min: float = 150.0
    lane_w_max: float = 244.0
    """Lanes: content-solved lane width clamp bounds."""
    lane_pad: float = 12.0
    """Lanes: inner padding between a band edge and its node boxes."""
    channel_gap: float = 24.0
    """Lanes: clearance a long-haul perimeter channel keeps below the bands
    (stacking like DAG skip channels; the canvas grows to hold them)."""
    channel_stack: float = 12.0
    """Lanes: vertical stacking step between stacked long-haul channels."""
    # ── Lanes policy knobs (the obi-engine delta review) ────────────────
    lane_ground: str = "typographic"
    """Lanes ground treatment (D1): 'typographic' dissolves the band box into
    header + count + one hairline rule spanning the card column (grouping by
    alignment/proximity); 'panel' keeps the contained band rect."""
    lane_rule_dy: float = 10.0
    """Lanes (D2): header baseline → hairline rule distance (typographic)."""
    lane_rule_to_row: float = 15.0
    """Lanes (D2): hairline rule → first card row distance (typographic)."""
    legend_home: str = "masthead"
    """Lanes legend home (D3): 'masthead' (top-right, inline with the title
    row) or 'footer' (the footer band; footer-growth reserves it)."""
    bus_bundling: str = "shared-rail"
    """Lanes gutter routing (D6): 'shared-rail' dedupes coincident gutter
    verticals into one rail with arrowless joins; 'per-edge' keeps full
    per-edge elbows."""
    morph_mark_r: float = 4.0
    """Lanes category-by-SHAPE mark radius (obi-engine' morphology idiom).
    The mark LEADS the label row (obi-engine) — its advance is
    ``2·morph_mark_r + ink_gap``, reserved via place_card's bullet lead."""


def _diagram_topology_defaults() -> dict[str, DiagramTopologyChassis]:
    """Specimen-extracted chassis for all 14 layout slugs."""
    n = DiagramNodeChassis
    return {
        "pipeline": DiagramTopologyChassis(
            width_policy="aligned",
            width=896,
            height=216,
            display_w=760,
            display_h=183,
            margin_x=24.0,
            gap=60.0,
            node=n(w=160.0, h=64.0),
            hero=n(w=188.0, h=64.0, rx=16.0),
            footer_h=44.0,
        ),
        "fanout-horizontal": DiagramTopologyChassis(
            width_policy="aligned",  # dest column shares one solved width (group-uniform)
            width=760,
            display_w=740,
            margin_x=30.0,
            header_h=92.0,
            footer_h=78.0,
            pitch=64.0,
            node=n(w=156.0, h=54.0, dot_dy=24.0, label_dy=28.0, desc_dy=44.0),
            hero=n(w=210.0, h=96.0, rx=16.0),
        ),
        "fanout-bilateral": DiagramTopologyChassis(
            width_policy="aligned",  # both dest columns share one solved width
            width=820,
            display_w=760,
            margin_x=40.0,
            header_h=80.0,
            pitch=120.0,
            node=n(w=156.0, h=54.0, dot_dy=24.0, label_dy=28.0, desc_dy=44.0),
            hero=n(w=200.0, h=96.0, rx=16.0),
        ),
        "fanout-upward": DiagramTopologyChassis(
            width_policy="aligned",  # dest row shares one solved width
            width=560,
            display_w=545,
            header_mode="none",
            header_h=0.0,
            margin_top=40.0,
            margin_x=20.0,
            footer_h=0.0,
            bottom_m=20.0,
            row_cap=3,
            row_gap=54.0,
            src_gap=40.0,
            node=n(w=150.0, h=56.0, dot_dy=24.0, label_dy=28.0, desc_dy=44.0),
            hero=n(w=220.0, h=80.0, rx=16.0),
        ),
        "fanout-radial": DiagramTopologyChassis(
            aspect="square",
            width_policy="aligned",  # ring card dests share one solved width
            width=600,
            display_w=480,
            margin_x=24.0,
            header_h=0.0,
            header_mode="left",
            footer_h=0.0,
            ring_r=230.0,
            ring_gap=80.0,
            node=n(w=150.0, h=54.0, dot_dy=24.0, label_dy=28.0, desc_dy=44.0),
            hero=n(w=184.0, h=80.0, rx=16.0),
            hero_circle_r=44.0,
        ),
        "convergence": DiagramTopologyChassis(
            width_policy="aligned",  # the arrivals column shares one solved width
            width=820,
            display_w=760,
            margin_x=40.0,
            header_h=88.0,
            pitch=92.0,
            bottom_m=32.0,
            node=n(w=190.0, h=64.0),
            hero=n(w=190.0, h=100.0, rx=16.0),
        ),
        "flywheel": DiagramTopologyChassis(
            aspect="square",
            width=600,
            height=600,
            display_w=480,
            header_mode="center",
            ring_r=172.0,
            arc_r=178.0,
            node=n(w=150.0, h=56.0, dot_dy=24.0, label_dy=28.0, desc_dy=44.0),
            hero=n(w=132.0, h=46.0, rx=16.0),
            circle_r=26.0,
        ),
        "stack": DiagramTopologyChassis(
            width_policy="aligned",
            aspect="portrait",
            width=480,
            display_w=392,
            margin_x=56.0,
            header_mode="center",
            header_h=90.0,
            footer_h=54.0,
            gap=34.0,
            src_gap=44.0,
            node=n(w=300.0, h=58.0),
            hero=n(w=368.0, h=78.0, rx=16.0),
        ),
        "tree": DiagramTopologyChassis(
            width_policy="aligned",
            width=720,
            height=320,
            margin_x=30.0,
            header_h=56.0,
            gap=30.0,
            pitch=200.0,
            leaf_min_w=140.0,
            leaf_max_w=220.0,
            node=n(w=200.0, h=76.0, dot_dy=24.0, label_dy=28.0, desc_dy=46.0, max_desc_lines=2),
            hero=n(w=180.0, h=60.0, rx=16.0),
        ),
        "tree-radial": DiagramTopologyChassis(
            aspect="square",
            width=720,
            display_w=576,
            header_mode="left",
            header_h=0.0,
            footer_h=0.0,
            margin_x=24.0,
            r1=160.0,
            r2=280.0,
            node=n(w=140.0, h=48.0, dot_dy=20.0, label_dy=24.0, desc_dy=38.0),
            node2=n(w=120.0, h=40.0, rx=12.0, dot_dy=18.0, label_dy=22.0, desc_dy=34.0),
            hero=n(w=160.0, h=56.0, rx=16.0),
            hero_circle_r=34.0,
        ),
        "comparison": DiagramTopologyChassis(
            width_policy="aligned",
            width=720,
            height=240,
            margin_x=48.0,
            node=n(w=268.0, h=72.0),
            hero=n(w=268.0, h=72.0, rx=16.0),
        ),
        "sequence": DiagramTopologyChassis(
            width_policy="aligned",
            width=760,
            display_w=740,
            margin_x=40.0,
            header_h=72.0,
            footer_h=48.0,
            lifeline_gap=85.0,
            msg_pitch=56.0,
            first_msg_dy=34.0,
            node=n(w=170.0, h=46.0, rx=13.0, dot_dy=23.0, label_dy=27.0, desc_dy=35.0),
            hero=n(w=170.0, h=46.0, rx=16.0, dot_dy=23.0, label_dy=20.0, desc_dy=35.0),
        ),
        "dag": DiagramTopologyChassis(
            width_policy="aligned",
            width=760,
            height=360,
            display_w=740,
            margin_x=40.0,
            header_h=66.0,
            footer_h=54.0,
            rank_gap=145.0,
            rank_pitch_max=120.0,
            node=n(w=130.0, h=50.0, rx=13.0, dot_inset_x=18.0, dot_dy=21.0, label_dy=25.0, desc_dy=40.0),
            hero=n(w=130.0, h=50.0, rx=16.0, dot_inset_x=18.0, dot_dy=21.0, label_dy=25.0, desc_dy=40.0),
        ),
        "state-machine": DiagramTopologyChassis(
            width=760,
            height=300,
            display_w=740,
            margin_x=40.0,
            header_h=88.0,
            footer_h=40.0,
            chain_gap=55.0,
            drop_gap=50.0,
            drop_dy=92.0,
            loop_dx=75.0,
            loop_dy=20.0,
            stub_len=14.0,
            tag_dy=14.0,
            node=n(w=130.0, h=42.0),
            hero=n(w=120.0, h=42.0),
        ),
        # Hub: a square canvas (the fanout-radial precedent), center circle +
        # spokes on a ring distributed by compass sector. The solver lands in
        # a later slice; the chassis is here so the union-chassis contract and
        # the "no solver registered" guard have their geometry.
        "hub": DiagramTopologyChassis(
            aspect="square",
            width=640,
            display_w=512,
            header_h=0.0,
            footer_h=0.0,
            margin_x=24.0,
            width_policy="aligned",  # spokes share one solved box (a regular ring)
            hero_circle_r_hub=44.0,
            ring_r_hub=210.0,
            card_min_w=120.0,
            w_max=200.0,
            h_max=96.0,
            node=n(w=150.0, h=54.0, dot_dy=24.0, label_dy=28.0, desc_dy=44.0),
            hero=n(w=160.0, h=56.0, rx=16.0),
        ),
        # Lanes: a swimlane banner — category bands with headers, content-sized
        # lane widths, gutter-bus adjacency + a perimeter channel for long
        # hauls. Solver lands in a later slice.
        "lanes": DiagramTopologyChassis(
            width=760,
            display_w=740,
            margin_x=30.0,
            header_h=80.0,
            footer_h=48.0,
            width_policy="aligned",  # a band's cards share its clamped width
            lane_header_h=44.0,
            gutter_w=86.0,
            row_pitch=80.0,
            lane_w_min=150.0,
            lane_w_max=244.0,
            lane_pad=12.0,
            channel_gap=24.0,
            channel_stack=12.0,
            node=n(w=150.0, h=54.0, dot_dy=24.0, label_dy=28.0, desc_dy=44.0),
            hero=n(w=160.0, h=56.0, rx=16.0),
        ),
    }


class ParadigmDiagramConfig(FrozenModel):
    """Diagram frame chassis + kinetic-channel config within a paradigm.

    The paradigm owns the cards, type voices, and the kinetic channel
    (edge-motion default/allowlist, track mapping, entrance); the engine
    config (``data/config/diagram-frame.yaml``) owns the flow grammar — caps, orientation
    legality, connector/particle constants. Chassis
    constants restate the topology specimens; primer.yaml carries the
    load-bearing values per Invariant 5.
    """

    text_ascent_ratio: float = 0.74
    """Line-metric ascent as a fraction of font size (Inter/JBM family
    average) — node text blocks are measured with these and vertically
    centered; chassis label_dy/desc_dy are superseded by the metric
    engine (clipping is never legal)."""
    text_descent_ratio: float = 0.22
    label_desc_gap: float = 6.0
    """Vertical gap between the label line box and the desc block."""
    min_pad_y: float = 7.0
    """Minimum clearance between any text ink and the card edge; desc
    lines drop (never clip) when the block would breach it."""
    dot_align_ratio: float = 0.31
    # One speed of light (K1): particles and beam comets travel at constant
    # VELOCITY — per-edge dur = clamp(length / v_target, dur_min, dur_max).
    # Slot-locked choreographies (beam relay, sequence replay) keep their
    # semantic clocks. All phi-family genome motion data.
    motion_v_target: float = 144.0
    motion_dur_min: float = 2.618
    motion_dur_max: float = 4.236
    track_overtake_floor: float = 2.5
    """A particle riding a marching track must run at least this multiple
    of the track's phase speed — it overtakes the texture, never glues."""
    """Accent-dot center sits this fraction of the label size above its
    baseline (optical cap-height centering)."""
    edge_motion_default: str = "particle"
    """Genome-declared default edge motion (the specimen-true primer
    treatment is particle over a dash-march track — two named things)."""
    edge_motion_allowlist: list[str] = Field(default_factory=lambda: ["dash", "particle"])
    """Validated allowlist: a per-edge or per-spec request outside it is a
    DiagramInputError. Motion-opting-out genomes (vellum -> [dash]) must
    declare a static direction device — see ``direction_device``."""
    track_default_by_motion: dict[str, str] = Field(
        default_factory=lambda: {"dash": "dash-march", "particle": "dash-march"}
    )
    """Track (the line itself) per motion value: composite values ride a
    marching dashed track (specimen-true); beam/flow run over a static tube
    (a marching tube beneath animated light is noise). P3: a meaning-bearing
    dasharray (sequence returns, SM loops) always resolves the track static."""
    entrance: Literal["fade", "none"] = "fade"
    """Genome entrance channel: fade | none. Validated at config load — a typo
    or an unlanded value (draw-on is the vellum genome session's choreography)
    raises instead of silently no-opping to no entrance."""
    direction_device: str = "motion"
    """motion | arrowhead. A genome whose allowlist carries no animated
    value must declare 'arrowhead' (drawn, genome-filtered — never
    <marker>); enforcement seam documented in validate_paradigms."""
    genome_defs_include: str = ""
    """Optional template path injected into the diagram defs block
    (turbulence/displacement filters for material genomes)."""
    title_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(family="Inter", size=16, weight=700))
    subtitle_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(family="Inter", size=11, weight=400))
    label_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(family="Inter", size=13, weight=600))
    desc_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=9.5, weight=500))
    hero_name_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(family="Inter", size=15, weight=700))
    hero_desc_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=10, weight=500))
    muted_name_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(family="Inter", size=14, weight=400))
    op_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(family="Inter", size=13, weight=600))
    edge_label_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=9.5, weight=400))
    """Rendered edge labels (sequence, state-machine) are user content that
    can carry -> and check marks: the whole slot is mono structurally (the
    standing U+2192 rule), never a mono_triggers special case."""
    legend_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=8.0, weight=400, tracking_em=0.04))
    tag_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=8.0, weight=400, tracking_em=0.06))
    short_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=12.0, weight=700))
    """Mono identity text inside standard glyph-circles ('hw')."""
    hub_short_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=16.0, weight=700))
    circle_label_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=9.5, weight=400))
    foot_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=7.0, weight=400, tracking_em=0.1))
    caption_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(family="Inter", size=14.0, weight=400))
    """The base caption sentence (every specimen's ``-cap``: 14px Inter,
    sans, centered at the foot). Larger and sans — NOT the 7px tracked-mono
    brand foot the retired card-chrome era stamped."""
    annotation_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=9.5, weight=500))
    """Callout / aside / badge / legend annotation text — mono, one step below
    a card desc so an overlay reads as chrome, not primary content."""
    lane_header_voice: MatrixVoice = Field(
        default_factory=lambda: MatrixVoice(family="Inter", size=11.0, weight=700, tracking_em=0.08)
    )
    """Lanes category-band header — display face, tracked, the band's title."""
    count_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=8.0, weight=700, tracking_em=0.04))
    """Lanes member-count badge — small mono numeral."""
    region_label_voice: MatrixVoice = Field(default_factory=lambda: MatrixVoice(size=9.0, weight=400, tracking_em=0.14))
    """Compound-region band header (gateway-balanced's MODEL POOL, pp-gateway-
    balanced.svg .gw-cnt): a wide-tracked mono chip label, distinct from
    lanes' tight count_voice numeral."""
    node: DiagramRhythm = Field(
        default_factory=lambda: DiagramRhythm(pad_y=22.0, label_desc_gap=7.5, desc_line_pitch=19.0, max_desc_lines=1)
    )
    """Paradigm ROOT rhythm for default (non-hero) nodes — every topology's
    ``node``/``node2`` inherits this when its own block doesn't cite
    pad_y/label_desc_gap/desc_line_pitch/max_desc_lines (see
    ``DiagramRhythm``'s own docstring for the sheet citation). Resolved onto
    ``topologies`` by this model's own ``_resolve_topology_rhythm``
    validator immediately after paradigm load — by the time any solver
    reads ``ch.node.pad_y``, it is never ``None``."""
    hero: DiagramRhythm = Field(
        default_factory=lambda: DiagramRhythm(pad_y=25.5, label_desc_gap=8.5, desc_line_pitch=18.0, max_desc_lines=2)
    )
    """Paradigm ROOT rhythm for hero nodes — every topology's ``hero``
    inherits this when its own block doesn't cite an override, same law as
    ``node`` above."""
    circle_r: float = 30.0
    """Paradigm ROOT glyph-circle radius for default nodes — every
    topology's ``circle_r`` inherits this when uncited (the bilateral canon,
    hw-diagram-alpha3-canon.html "Integration Hub v2": satellites r=30)."""
    hero_circle_r: float = 44.0
    """Paradigm ROOT glyph-circle radius for hero/hub nodes — same law as
    ``circle_r`` (the canon's hub r=44)."""
    topologies: dict[str, DiagramTopologyChassis] = Field(default_factory=_diagram_topology_defaults)
    """Chassis per layout slug (14). A paradigm YAML may restate any subset;
    missing slugs keep the specimen defaults."""

    @model_validator(mode="after")
    def _resolve_topology_rhythm(self) -> ParadigmDiagramConfig:
        """Root-then-family merge (the "no bare defaults" law): every
        topology's node/hero/node2 pad_y/label_desc_gap/desc_line_pitch/
        max_desc_lines, and every topology's own circle_r/hero_circle_r,
        resolve HERE — once, at paradigm load — to the family's own citation
        if it has one, else this paradigm's root rhythm (``self.node``/
        ``self.hero``/``self.circle_r``/``self.hero_circle_r``, themselves
        REQUIRED fields a caller cannot leave unset). Every downstream
        solver (``sizing.solve_card_box``, ``solve_head_box``, the
        glyph-circle dispatch in ``solve_node_box``, ...) reads an
        already-resolved chassis; none of them can silently fall through to
        the bare Pydantic class defaults (7/6/15/1/24/28) this fix retires.
        A future topology added without its own rhythm keys is BORN
        inheriting the sheet's law — it cannot render at an uncited number."""

        def resolve_node(nch: DiagramNodeChassis, root: DiagramRhythm) -> DiagramNodeChassis:
            update: dict[str, float | int] = {}
            if nch.pad_y is None:
                update["pad_y"] = root.pad_y
            if nch.label_desc_gap is None:
                update["label_desc_gap"] = root.label_desc_gap
            if nch.desc_line_pitch < 0:
                update["desc_line_pitch"] = root.desc_line_pitch
            if nch.max_desc_lines < 0:
                update["max_desc_lines"] = root.max_desc_lines
            return nch.model_copy(update=update) if update else nch

        resolved: dict[str, DiagramTopologyChassis] = {}
        for slug, tch in self.topologies.items():
            tch_update: dict[str, object] = {
                "node": resolve_node(tch.node, self.node),
                "hero": resolve_node(tch.hero, self.hero),
                # node2 (tree-radial's outer ring, tree's deepest row) has no
                # dedicated root citation — it inherits the same root.node
                # rhythm as the primary node class, the closest sibling.
                "node2": resolve_node(tch.node2, self.node),
            }
            if tch.circle_r < 0:
                tch_update["circle_r"] = self.circle_r
            if tch.hero_circle_r < 0:
                tch_update["hero_circle_r"] = self.hero_circle_r
            resolved[slug] = tch.model_copy(update=tch_update)
        # Mutate in place rather than `return self.model_copy(...)`: Pydantic
        # warns that an "after" validator returning a DIFFERENT instance is
        # unsupported when the model validates via `__init__` (exactly the
        # `ParadigmSpec(**raw)` path `load_paradigms()` uses). `object.
        # __setattr__` bypasses this FrozenModel's own frozen check — the
        # documented escape hatch for a validator that needs to finish
        # shaping an otherwise-immutable model — so identity stays `self`.
        object.__setattr__(self, "topologies", resolved)
        return self


class ParadigmSpec(FrozenModel):
    """A declarative paradigm: frame-level config + required genome fields.

    Loaded from ``data/paradigms/*.yaml`` by
    :func:`hyperweave.config.loader.load_paradigms`. Consumed by frame
    resolvers via ``paradigm_spec.{frame}.{key}`` attribute access.
    """

    id: str
    """Paradigm slug (matches YAML filename stem)."""
    name: str
    """Human-readable name."""
    description: str = ""

    badge: ParadigmBadgeConfig = Field(default_factory=ParadigmBadgeConfig)
    strip: ParadigmStripConfig = Field(default_factory=ParadigmStripConfig)
    chart: ParadigmChartConfig = Field(default_factory=ParadigmChartConfig)
    stats: ParadigmStatsConfig = Field(default_factory=ParadigmStatsConfig)
    icon: ParadigmIconConfig = Field(default_factory=ParadigmIconConfig)
    marquee: ParadigmMarqueeConfig = Field(default_factory=ParadigmMarqueeConfig)
    matrix: ParadigmMatrixConfig = Field(default_factory=ParadigmMatrixConfig)
    diagram: ParadigmDiagramConfig = Field(default_factory=ParadigmDiagramConfig)

    requires_genome_fields: list[str] = Field(default_factory=list)
    """Genome field names that must be non-empty when a genome opts into
    this paradigm for any frame type. Enforced at load time by
    :func:`hyperweave.compose.validate_paradigms.validate_genome_against_paradigms`.
    """

    frame_variant_defaults: dict[str, str] = Field(default_factory=dict)
    """Per-frame default for ``ComposeSpec.variant`` when the user leaves it
    empty. Cellular paradigm can declare a per-frame default tone or pair
    (e.g. ``{badge: violet, strip: violet-teal}``) so monofamily artifacts pick
    a solo tone and paired artifacts render bifamily. Non-cellular paradigms
    leave this empty — resolvers fall back to the genome's flagship variant."""
