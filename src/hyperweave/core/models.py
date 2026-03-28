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
    genome_id: GenomeId = Field(default=GenomeId.BRUTALIST_EMERALD, description="Genome slug")
    profile_id: str = Field(default="", description="Profile ID (resolved from genome if empty)")

    @model_validator(mode="before")
    @classmethod
    def _resolve_profile_from_genome(cls, data: object) -> object:
        """Auto-resolve profile_id from genome_id when not explicitly set."""
        if not isinstance(data, dict):
            return data
        profile = data.get("profile_id", "")
        if not profile:
            genome_raw = str(data.get("genome_id", GenomeId.BRUTALIST_EMERALD))
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


class ArtifactMetadata(FrozenModel):
    """Resolved metadata returned in ComposeResult."""

    type: FrameType
    genome: GenomeId
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
