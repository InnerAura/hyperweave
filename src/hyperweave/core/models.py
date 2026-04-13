"""Domain models -- all frozen Pydantic BaseModels."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hyperweave.core.enums import (
    DividerVariant,
    FrameType,
    GenomeId,
    GlyphMode,
    ProfileId,
    Regime,
)


class FrozenModel(BaseModel):
    """Base model with strict, frozen semantics.

    All domain models inherit from this instead of repeating ConfigDict.
    ``frozen=True`` makes instances immutable after creation.
    ``extra="forbid"`` rejects unknown fields at construction time.
    ``use_attribute_docstrings=True`` lets field docstrings serve as descriptions.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", use_attribute_docstrings=True)


class SlotContent(FrozenModel):
    """A single content slot within a frame zone."""

    zone: str = Field(description="Zone identifier (e.g. 'identity', 'value', 'status')")
    value: str = Field(default="", description="Text content for the zone")
    data: dict[str, object] | None = Field(default=None, description="Structured data payload")


class ReasoningFields(FrozenModel):
    """Reasoning metadata fields embedded in SVG metadata at tier 4.

    Validated at metadata emission time only -- NOT enforced on ComposeSpec
    so that programmatic construction with empty reasoning is allowed.
    """

    intent: str = Field(description="Why this artifact was created")
    approach: str = Field(description="Key design decision")
    tradeoffs: str = Field(min_length=21, description="What was NOT done (>20 chars for tier 4)")


# Genome -> profile resolution map (matches data/genomes/*.json).
_GENOME_PROFILE_MAP: dict[str, str] = {
    GenomeId.BRUTALIST_EMERALD: ProfileId.BRUTALIST,
    GenomeId.CHROME_HORIZON: ProfileId.CHROME,
}


class ComposeSpec(FrozenModel):
    """Complete specification for composing an artifact."""

    # -- Core identity --
    type: FrameType = Field(description="Frame type: badge, strip, banner, icon, divider, marquee-*, receipt, etc.")
    frame_id: str = Field(default="", description="Resolved frame identifier")
    # NOTE: relaxed from GenomeId StrEnum to str in Session 2A+2B so that
    # --genome-file can load arbitrary genome slugs not in the built-in registry.
    # GenomeId enum remains valid for internal defaults and type-hinting.
    genome_id: str = Field(
        default=GenomeId.BRUTALIST_EMERALD.value,
        description="Genome slug (built-in or custom from --genome-file)",
    )
    profile_id: str = Field(default="", description="Profile ID (resolved from genome if empty)")

    @model_validator(mode="before")
    @classmethod
    def _resolve_profile_from_genome(cls, data: object) -> object:
        """Auto-resolve profile_id from genome_id when not explicitly set."""
        if not isinstance(data, dict):
            return data
        profile = data.get("profile_id", "")
        if not profile:
            # Try map lookup; if genome_override has a profile field, use it.
            override = data.get("genome_override") or {}
            if isinstance(override, dict) and override.get("profile"):
                data["profile_id"] = str(override["profile"])
                return data
            genome_raw = str(data.get("genome_id", GenomeId.BRUTALIST_EMERALD.value))
            data["profile_id"] = _GENOME_PROFILE_MAP.get(genome_raw, ProfileId.BRUTALIST)
        return data

    # -- Content --
    slots: list[SlotContent] = Field(default_factory=list, description="Content filling frame zones")
    state: str = Field(default="active", description="Semantic state: active, warning, critical, passing, etc.")
    motion: str = Field(default="static", description="Animation primitive (genome.compatible_motions)")
    glyph: str = Field(default="", description="Glyph identifier")
    glyph_mode: GlyphMode = Field(default=GlyphMode.AUTO, description="Glyph rendering mode: auto, fill, wire, none")
    custom_glyph_svg: str = Field(default="", description="Raw SVG for custom glyphs")
    variant: str = Field(default="default", description="Frame variant: default, compact")
    shape: str = Field(default="", description="Icon frame shape: square, circle")

    # -- Governance --
    regime: Regime = Field(default=Regime.NORMAL, description="Policy lane: normal, permissive, ungoverned")

    # -- Text content --
    title: str = Field(default="", description="Primary text (badge label, strip identity, banner title)")
    value: str = Field(default="", description="Secondary text (badge value, strip metrics, banner subtitle)")

    # -- Reasoning (L4 metadata) --
    intent: str = Field(default="", description="Why this artifact was created")
    approach: str = Field(default="", description="Key design decision")
    tradeoffs: str = Field(default="", description="What was NOT done (>20 chars for tier 4)")

    # -- Data-bound --
    numeric_value: str = Field(default="", description="Numeric value for threshold evaluation")
    threshold_id: str = Field(default="", description="Threshold rule set identifier")

    # -- Metadata --
    generation: int = Field(default=1, ge=1, description="Artifact generation counter")
    metadata_tier: int = Field(default=3, description="Metadata richness: 0-4, default 3 (resonant)")
    series: str = Field(default="core", description="core, scholarly, velocity, social, telemetry")
    platform: str = Field(default="github-readme", description="Target platform")

    # -- Telemetry --
    telemetry_data: dict[str, object] | None = Field(
        default=None, description="Session data contract JSON (telemetry frames only)"
    )

    # -- Divider-specific --
    divider_variant: DividerVariant = Field(
        default=DividerVariant.ZEROPOINT, description="block, current, takeoff, void, zeropoint"
    )

    # -- Marquee-specific --
    marquee_direction: str = Field(default="ltr", description="Scroll direction: ltr, rtl, up, down")
    marquee_rows: int = Field(default=1, description="Counter variant: number of rows")
    marquee_speeds: list[float] | None = Field(default=None, description="Counter: speed per row")

    # -- Session 2A+2B additions --
    # Inline genome dict that bypasses the built-in registry. Set by --genome-file.
    # Resolver's _load_genome() checks this first before looking up genome_id.
    genome_override: dict[str, Any] | None = Field(
        default=None,
        description="Inline genome dict (bypasses registry). Set by --genome-file.",
    )
    # Pre-fetched external data (GitHub API response, etc.). Network I/O happens
    # at CLI/HTTP layer before compose() is called. Used by stats, chart frames.
    connector_data: dict[str, Any] | None = Field(
        default=None,
        description="Pre-fetched external connector data (stats, chart, live)",
    )
    # Timeline frame items list.
    timeline_items: list[dict[str, Any]] | None = Field(
        default=None,
        description="Timeline nodes: [{title, subtitle, status, date}, ...]",
    )
    # Stats/chart frame parameters.
    stats_username: str = Field(default="", description="GitHub username for stats frame")
    chart_owner: str = Field(default="", description="GitHub owner for chart frame")
    chart_repo: str = Field(default="", description="GitHub repo for chart frame")


class ArtifactMetadata(FrozenModel):
    """Resolved metadata returned in ComposeResult."""

    type: FrameType
    # Relaxed from GenomeId to str in Session 2A+2B to support custom genomes
    # loaded via --genome-file that are not members of the built-in registry.
    genome: str
    profile: str
    divider_variant: DividerVariant
    motion: str
    state: str
    regime: Regime
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    metadata_tier: int
    duration_ms: float
    generation: int = Field(ge=1)
    series: str


class ComposeResult(FrozenModel):
    """Output of the compose pipeline."""

    svg: str = Field(description="Self-contained SVG string")
    metadata: ArtifactMetadata | None = Field(default=None, description="Structured metadata")
    width: int = Field(description="Artifact width in pixels")
    height: int = Field(description="Artifact height in pixels")


class ResolvedArtifact(FrozenModel):
    """Typed output from resolver.resolve() -- replaces the untyped dict.

    genome and profile stay as ``dict[str, Any]`` because they are YAML-loaded
    and their schema varies per genome/profile. frame_context carries
    frame-specific rendering data that varies per frame type.
    """

    genome: dict[str, Any] = Field(description="Full genome config dict (YAML-loaded)")
    profile: dict[str, Any] = Field(description="Full profile config dict (YAML-loaded)")
    profile_id: str = Field(description="Resolved profile identifier")
    category: str = Field(description="Genome category: dark or light")
    width: int = Field(ge=1, description="Resolved artifact width in pixels")
    height: int = Field(ge=1, description="Resolved artifact height in pixels")
    frame_template: str = Field(description="Jinja2 template path (e.g. 'frames/badge.svg.j2')")
    frame_context: dict[str, Any] = Field(default_factory=dict, description="Frame-specific rendering context")
    motion: str = Field(default="static", description="Resolved motion identifier")
    glyph_id: str = Field(default="", description="Resolved glyph identifier")
    glyph_path: str = Field(default="", description="SVG path data for the glyph")
    glyph_viewbox: str = Field(default="", description="SVG viewBox for the glyph")


class ZoneDef(FrozenModel):
    """A zone within a frame layout."""

    id: str = Field(description="Zone identifier")
    name: str = Field(description="Human-readable zone name")
    x: float = Field(description="X offset in pixels")
    y: float = Field(description="Y offset in pixels")
    width: float = Field(description="Zone width in pixels")
    height: float = Field(description="Zone height in pixels")


class FrameDef(FrozenModel):
    """Structural definition of a frame type."""

    id: str = Field(description="Frame type identifier")
    name: str = Field(description="Human-readable name")
    default_width: int = Field(description="Default width in pixels")
    default_height: int = Field(description="Default height in pixels")
    zones: list[ZoneDef] = Field(default_factory=list, description="Zone layout")


class ProfileConfig(FrozenModel):
    """Structural skeleton for artifact rendering."""

    id: str = Field(description="Profile identifier")
    name: str = Field(description="Human-readable name")

    # -- Typography --
    fonts: dict[str, str] = Field(description="Font stacks keyed by role: title, value, mono")
    identity_size: int = Field(description="Identity text size in px")
    identity_weight: int = Field(description="Identity text weight")
    identity_letter_spacing: str = Field(description="Identity letter-spacing in em")
    value_size: int = Field(description="Value text size in px")
    value_weight: int = Field(description="Value text weight")
    label_size: int = Field(description="Label text size in px")
    label_weight: int = Field(description="Label text weight")
    label_letter_spacing: str = Field(description="Label letter-spacing in em")
    badge_value_size: int = Field(description="Badge value text size in px")
    badge_value_weight: int = Field(description="Badge value text weight")

    # -- Geometry --
    strip_corner: float = Field(description="Strip corner radius")
    badge_corner: float = Field(description="Badge corner radius")
    strip_accent_width: float = Field(description="Left accent bar width in px")
    strip_metric_pitch: int = Field(description="Pixels between metric cells")
    strip_divider_mode: str = Field(description="Divider rendering: full or minimal")
    badge_frame_height: int = Field(description="Badge height: 22 or 20")

    # -- Glyph --
    glyph_backing: str = Field(description="none, circle, square, rounded-square")
    glyph_backing_rx: float = Field(description="Glyph backing corner radius")

    # -- Status --
    status_shape: str = Field(description="Status indicator shape: circle or square")

    # -- Motion --
    easing: str = Field(description="CSS easing function")

    # -- Banner (Tier 1A parametric) --
    banner_height: int = Field(default=600, description="Full banner height in px")

    # -- Badge parametric (Tier 1A) --
    badge_sep_width: int = Field(default=2, description="Badge separator width in px")
    badge_seam_width: int = Field(default=3, description="Badge seam gap width in px")
    badge_inset: int = Field(default=0, description="Badge content inset in px")
    badge_indicator_size: int = Field(default=8, description="Badge status indicator size in px")
    badge_indicator_pad_r: int = Field(default=8, description="Badge indicator right padding in px")
    badge_label_uppercase: bool = Field(default=True, description="Uppercase badge labels")
    badge_use_mono: bool = Field(default=True, description="Use monospace font for badge labels")
    badge_text_y_factor: float = Field(default=0.69, description="Badge text vertical position factor")

    # -- Strip parametric (Tier 1A) --
    strip_glyph_size: int = Field(default=20, description="Strip glyph size in px")
    strip_glyph_fill: str = Field(default="var(--dna-signal)", description="Strip glyph fill color")
    strip_identity_weight: int = Field(default=900, description="Strip identity text weight")
    strip_identity_fill: str = Field(default="var(--dna-brand-text)", description="Strip identity text fill")
    strip_identity_letter_spacing: str = Field(default="0.18em", description="Strip identity letter spacing")
    strip_metric_label_size: int = Field(default=7, description="Strip metric label font size")
    strip_metric_label_fill: str = Field(default="var(--dna-ink-muted)", description="Strip metric label fill")
    strip_metric_label_letter_spacing: str = Field(default="0.2em", description="Strip metric label letter spacing")
    strip_metric_label_y: int = Field(default=18, description="Strip metric label y position")
    strip_metric_value_weight: int = Field(default=900, description="Strip metric value font weight")
    strip_metric_value_fill: str = Field(default="var(--dna-ink-primary)", description="Strip metric value fill")
    strip_metric_value_y: int = Field(default=36, description="Strip metric value y position")
    strip_metric_value_skew: int = Field(default=0, description="Strip metric value skewX degrees")
    strip_identity_font: str = Field(
        default="var(--dna-font-mono, 'SF Mono', monospace)",
        description="Strip identity font",
    )
    strip_metric_label_font: str = Field(
        default="var(--dna-font-mono, 'SF Mono', monospace)",
        description="Strip metric label font",
    )
    strip_divider_color: str = Field(
        default="var(--dna-border)",
        description="Strip vertical divider stroke color",
    )
    strip_divider_opacity: float = Field(
        default=1.0,
        description="Strip vertical divider opacity (0.0-1.0)",
    )

    # -- Marquee parametric (Tier 1A) --
    marquee_separator: str = Field(default="■", description="Marquee item separator character")
    marquee_separator_color: str = Field(default="var(--dna-border)", description="Marquee separator color")
    marquee_separator_opacity: str = Field(default="", description="Marquee separator opacity")
    marquee_divider_width: float = Field(default=1.5, description="Marquee divider stroke width")
    marquee_dot_shape: str = Field(default="rect", description="Marquee dot indicator shape")
    marquee_clip_x: int = Field(default=6, description="Marquee clip region x offset")
    marquee_clip_w: int = Field(default=788, description="Marquee clip region width")
    marquee_font_family: str = Field(
        default="var(--dna-font-mono, ui-monospace, monospace)",
        description="Marquee scroll text font",
    )

    # -- Counter marquee (Tier 1A closure) --
    marquee_counter_row_ys: list[int] = Field(default=[6, 48, 90], description="Counter row Y positions")
    marquee_counter_row_hs: list[int] = Field(default=[36, 36, 38], description="Counter row heights")
    marquee_counter_text_ys: list[int] = Field(default=[30, 72, 115], description="Counter text Y positions")
    marquee_counter_divider_ys: list[int] = Field(default=[44, 88], description="Counter divider Y positions")
    marquee_counter_brand_color_even: str = Field(
        default="var(--dna-signal)",
        description="Counter brand item color for even indices",
    )
    marquee_counter_brand_color_odd: str = Field(
        default="var(--dna-ink-primary)",
        description="Counter brand item color for odd indices",
    )
    marquee_counter_metric_label_color: str = Field(
        default="var(--dna-label-text, var(--dna-signal-dim))",
        description="Counter metric label color",
    )
    marquee_counter_metric_value_font: str = Field(
        default="",
        description="Counter metric value font family override (empty = inherit)",
    )
    marquee_counter_gap_r1: int = Field(default=28, description="Counter row 1 gap in px")
    marquee_counter_letter_spacing_r1: str = Field(default="4", description="Counter row 1 letter spacing")
    marquee_counter_letter_spacing_r2: str = Field(default="1.5", description="Counter row 2 letter spacing")
    marquee_counter_letter_spacing_r3: str = Field(default="1", description="Counter row 3 letter spacing")
    marquee_counter_text_start_x: int = Field(default=20, description="Counter text start x offset")
    marquee_counter_status_dot_color: str = Field(
        default="var(--dna-status-passing-core)",
        description="Counter status dot color",
    )
    marquee_counter_status_diamond_color: str = Field(
        default="var(--dna-signal)",
        description="Counter status diamond color",
    )
    marquee_counter_divider_x_inset: int = Field(default=6, description="Counter divider x inset")
    marquee_counter_divider_stroke_width: str = Field(default="1.5", description="Counter divider stroke width")
    marquee_counter_divider_stroke_opacity: str = Field(default=".2", description="Counter divider stroke opacity")
    marquee_counter_fade_inset: int = Field(default=5, description="Counter fade gradient inset")
    marquee_counter_fade_w: int = Field(default=36, description="Counter fade gradient width")
    marquee_counter_fade_rx: str = Field(default="", description="Counter fade gradient corner radius")
    marquee_counter_show_rivets: bool = Field(default=True, description="Show counter rivet decorations")
    marquee_counter_show_beacon: bool = Field(default=True, description="Show counter beacon pulse")

    # -- Horizontal marquee (Tier 1A closure) --
    marquee_horizontal_clip_inset_y: int = Field(default=4, description="Horizontal marquee clip Y inset")
    marquee_horizontal_clip_inset_x: int = Field(default=4, description="Horizontal marquee clip X inset")
    marquee_horizontal_show_accent_lines: bool = Field(default=True, description="Show horizontal accent lines")
    marquee_horizontal_bold_pattern: str = Field(
        default="even",
        description="Horizontal bold pattern: 'even' or 'first'",
    )

    # -- Vertical marquee (Tier 1A closure) --
    marquee_vertical_status_label_offset: int = Field(default=18, description="Vertical status label right offset")
    marquee_vertical_bottom_accent_type: str = Field(
        default="bar",
        description="Vertical bottom accent: 'bar' or 'hairline'",
    )
    marquee_vertical_warn_color: str = Field(
        default="var(--dna-status-warning-core)",
        description="Vertical warn status color",
    )
    marquee_vertical_status_ts_color: str = Field(
        default="var(--dna-label-text, var(--dna-signal-dim))",
        description="Vertical status timestamp color",
    )
