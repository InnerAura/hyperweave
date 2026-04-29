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

from pydantic import Field

from hyperweave.core.models import FrozenModel


class ParadigmChartConfig(FrozenModel):
    """Chart frame config within a paradigm."""

    viewport_x: int = 80
    viewport_y: int = 150
    viewport_w: int = 760
    viewport_h: int = 245
    chart_width: int = 900
    """Overall chart SVG width (brutalist/chrome: 900; cellular: 900)."""
    chart_height: int = 500
    """Overall chart SVG height. Cellular specimen is 600 to fit footer."""
    line_animate: bool = False
    """When True, emit a one-shot stroke-dashoffset draw animation on the
    polyline/path. Cellular paradigm opts in to reproduce the specimen's
    line-draws-on-load feel; brutalist/chrome keep the line static so the
    chart reads as instrument, not demo."""


class ParadigmStatsConfig(FrozenModel):
    """Stats frame config within a paradigm."""

    card_height: int = 260
    embeds_chart: bool = False
    """When True, resolve_stats composes a compact star-history strip
    beneath the metric row (chrome paradigm). When False, stats card is
    self-contained (brutalist paradigm)."""
    embed_viewport_x: int = 240
    embed_viewport_y: int = 170
    embed_viewport_w: int = 220
    embed_viewport_h: int = 70


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
    divider_render_mode: Literal["gradient", "class"] = "class"
    """``gradient`` routes through chrome-defs ``url(#{uid}-sep)`` stroke;
    ``class`` uses a flat CSS-class-colored divider."""
    status_shape_rendering: Literal["crispEdges", "geometricPrecision"] = "crispEdges"
    show_status_indicator: bool = True
    """When False, the status-indicator zone (56px reserve) collapses to
    zero width -- strip omits the right-edge diamond/ring entirely. Set
    False for paradigms/compositions where the state carrier lives
    elsewhere (e.g. inside a metric-state cell)."""
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


class ParadigmBadgeConfig(FrozenModel):
    """Badge frame config within a paradigm."""

    label_font_family: str = "Inter"
    value_font_family: str = "Inter"
    label_font_size: int = 11
    value_font_size: int = 11
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
    """Additional left-side offset for the glyph, used by paradigms that render
    a decorative element (cellular: 3-col pattern strip) in the far-left region.
    Brutalist/chrome: 0. Cellular: 18 (default) / 12 (compact)."""
    glyph_offset_left_compact: int = 0
    """Compact-variant glyph offset. Empty (0) falls back to glyph_offset_left."""
    glyph_size: int = 14
    """Glyph render box. Brutalist/chrome: 14. Cellular default: 12."""
    glyph_size_compact: int = 0
    """Compact-variant glyph size. Empty (0) falls back to glyph_size."""
    text_y_factor: float = 0.69
    """Vertical placement of label/value text baseline as fraction of
    frame_height. Brutalist/chrome: 0.69. Cellular specimen: 0.656 (y=21 at
    height=32), which aligns the indicator visually with the text center."""


class ParadigmBannerConfig(FrozenModel):
    """Banner frame config within a paradigm."""

    hero_font_family: str = "Inter"
    hero_font_weight: int = 800
    hero_skew_deg: float = 0.0
    hero_italic: bool = False
    width_default: int = 1200
    """Default banner width when ``variant != "compact"`` (1200 for brutalist/chrome).
    Cellular specimen is 800x220 — the paradigm can override both variants
    to the same specimen dims. Zero fallback to 1200."""
    height_default: int = 600
    """Default banner height when ``variant != "compact"`` (600 for brutalist/chrome)."""
    width_compact: int = 800
    """Compact-variant banner width (800 for brutalist/chrome; cellular too)."""
    height_compact: int = 220
    """Compact-variant banner height (220 for brutalist/chrome; cellular too)."""


class ParadigmIconConfig(FrozenModel):
    """Icon frame config within a paradigm."""

    supported_shapes: list[str] = Field(default_factory=lambda: ["square", "circle"])
    default_shape: str = "square"


class ParadigmMarqueeConfig(FrozenModel):
    """Marquee frame config within a paradigm.

    Captures the discrete values that a marquee in this paradigm uses for
    separator glyphs, per-item color cycle (bifamily-tspan), and live-block
    layout behavior. Resolvers read from this so adding a new bifamily-tspan
    paradigm is a YAML change — never a Python edit.

    Default values match the brutalist/chrome-era hardcoded behavior, so
    paradigms that don't declare marquee config still render correctly.
    """

    tspan_palette: list[str] = Field(default_factory=list)
    """Per-item color cycle for bifamily-tspan marquees. Resolver assigns
    color = palette[i % len(palette)] for the i-th item. Empty list keeps
    the default ``ink-primary/ink-secondary`` alternation."""
    separator_glyph: str = "■"
    """Separator character between scroll items. Cellular: ◆. Default: ■."""
    separator_color: str = ""
    """Separator color (hex). Empty string falls back to the resolver's
    profile-driven ``var(--dna-border)`` default."""
    suppress_live_block: bool = False
    """When True, marquee-horizontal collapses the LIVE label block so the
    scroll track uses full width. Cellular bifamily: True (specimen has no
    LIVE panel — pure hairline chrome); brutalist/chrome: False."""


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
    banner: ParadigmBannerConfig = Field(default_factory=ParadigmBannerConfig)
    chart: ParadigmChartConfig = Field(default_factory=ParadigmChartConfig)
    stats: ParadigmStatsConfig = Field(default_factory=ParadigmStatsConfig)
    icon: ParadigmIconConfig = Field(default_factory=ParadigmIconConfig)
    marquee: ParadigmMarqueeConfig = Field(default_factory=ParadigmMarqueeConfig)

    requires_genome_fields: list[str] = Field(default_factory=list)
    """Genome field names that must be non-empty when a genome opts into
    this paradigm for any frame type. Enforced at load time by
    :func:`hyperweave.compose.validate_paradigms.validate_genome_against_paradigms`.
    """

    frame_family_defaults: dict[str, str] = Field(default_factory=dict)
    """Per-frame default for ``ComposeSpec.family`` when the user leaves it
    empty. Cellular paradigm declares ``{badge: blue, strip: bifamily, ...}``
    so monofamily artifacts (badge/icon) pick blue by default and bifamily
    artifacts (strip/banner/marquee/divider) show both palettes simultaneously.
    Non-cellular paradigms leave this empty — resolvers fall back to ``blue``."""
