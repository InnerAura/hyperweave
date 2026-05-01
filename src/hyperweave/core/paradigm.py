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


class ParadigmIconConfig(FrozenModel):
    """Icon frame config within a paradigm."""

    supported_shapes: list[str] = Field(default_factory=lambda: ["square", "circle"])
    default_shape: str = "square"
    viewbox_w: int = 0
    """Internal coordinate system width for the icon's ``viewBox``. Zero means
    "use the resolver's rendered ``width``" (default behavior — viewBox matches
    rendered size). Chrome paradigm sets 120 so the chrome icon templates can
    render the v2 specimen's 120-unit material discipline (r=46/r=42 bezel,
    96x96 card, 6-unit rail, 0.6-unit hairlines) at a 64px rendered size."""
    viewbox_h: int = 0
    """Internal coordinate system height for the icon's ``viewBox``. Zero means
    "use the resolver's rendered ``height``"."""


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
    """Scroll-text font size in pixels. Chrome: 22 (Orbitron). Brutalist: 12 (JBM)."""
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
    """Separator character when ``separator_kind == "glyph"``. Cellular: ◆.
    Chrome: ·. Default: ■."""
    separator_color: str = ""
    """Separator color (hex). Empty string falls back to the resolver's
    profile-driven ``var(--dna-border)`` default."""
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

    requires_genome_fields: list[str] = Field(default_factory=list)
    """Genome field names that must be non-empty when a genome opts into
    this paradigm for any frame type. Enforced at load time by
    :func:`hyperweave.compose.validate_paradigms.validate_genome_against_paradigms`.
    """

    frame_family_defaults: dict[str, str] = Field(default_factory=dict)
    """Per-frame default for ``ComposeSpec.family`` when the user leaves it
    empty. Cellular paradigm declares ``{badge: blue, strip: bifamily, ...}``
    so monofamily artifacts (badge/icon) pick blue by default and bifamily
    artifacts (strip/marquee/divider) show both palettes simultaneously.
    Non-cellular paradigms leave this empty — resolvers fall back to ``blue``."""
