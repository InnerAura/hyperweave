"""
Pydantic models for Badge generation requests and responses.

Based on FastAPI HTTP API Spec v3.3 and MCP Server Spec v3.3.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from hyperweave.models.ontology import BadgeState

# Re-export BadgeState for backwards compatibility
__all__ = [
    "BadgeState",
    "ThemeDNA",
    "BadgeContent",
    "BadgeRequest",
    "SpecimenRequest",
    "BadgeValidationRequest",
    "BadgeValidationResponse",
    "HyperWeaveMetadata",
    "BadgeResponse",
    "OntologyCategoryResponse",
]


class ThemeDNA(BaseModel):
    """
    Theme fingerprint for reproducibility (v7 architecture).

    Captures theme identity and configuration used to generate an artifact.
    Replaces primitive-based fingerprint with theme-centric approach.
    """

    theme: str = Field(description="Theme ID from ontology")
    tier: str = Field(description="Theme tier (industrial, flagship, scholarly, etc.)")
    series: str = Field(description="Theme series (core, five-scholars, etc.)")
    motion: str | None = Field(None, description="Motion applied (if any)")
    ontology_version: str = "7.0.0"


class BadgeContent(BaseModel):
    """Badge content configuration."""

    label: str = Field(description="Left segment text")
    value: str = Field(description="Right segment text")
    state: BadgeState | None = Field(None, description="Badge state for color theming")
    icon: str | None = Field(None, description="Brand icon (github, npm, discord, etc.)")
    glyph: str | None = Field(None, description="Semantic glyph (dot, check, cross, etc.)")


class BadgeRequest(BaseModel):
    """
    Request model for badge generation (v7 theme-centric architecture).

    Breaking change from v2: Replaces primitive composition with atomic themes.

    Example:
        >>> request = BadgeRequest(
        ...     theme="chrome",
        ...     content=BadgeContent(label="version", value="1.0.0", state="passing"),
        ...     motion="sweep"
        ... )
    """

    # Core fields (v7 theme-driven)
    theme: str = Field(description="Theme ID from ontology (e.g., 'chrome', 'codex', 'neon')")
    content: BadgeContent = Field(description="Badge text content")

    # Optional overrides
    motion: str | None = Field(
        None, description="Animation type (must be compatible with theme's compatibleMotions)"
    )
    size: Literal["sm", "md", "lg", "xl"] = Field(default="md", description="Badge size")

    # Metadata tier
    artifact_tier: Literal["NAKED", "BASIC", "FULL"] = Field(
        default="FULL", description="Metadata completeness level"
    )

    # XAI reasoning
    reasoning: dict[str, str] | None = Field(
        None, description="Design reasoning: intent, approach, tradeoffs"
    )


class SpecimenRequest(BaseModel):
    """Request model for generating badge from validated specimen."""

    specimen_id: str = Field(description="Pre-validated specimen ID from ontology")
    content: BadgeContent = Field(description="Badge text content")
    size: Literal["sm", "md", "lg", "xl"] = Field(default="md", description="Badge size")
    reasoning: dict[str, str] | None = Field(None, description="Design reasoning")


class BadgeValidationRequest(BaseModel):
    """Request model for validating badge configuration."""

    finish_label: str | None = None
    finish_value: str | None = None
    seam: str
    series: str | None = None


class BadgeValidationResponse(BaseModel):
    """Response model for badge validation."""

    valid: bool
    violations: list[str] = Field(default_factory=list)
    ontology_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class HyperWeaveMetadata(BaseModel):
    """HyperWeave Living Artifact Protocol metadata."""

    artifact_type: str = "badge"
    series: str | None = None
    version: str = "1.0.0"
    ontology_version: str = "7.0.0"

    # Provenance
    generator: str = "Claude Sonnet 4.5 (InnerAura Labs) [claude-sonnet-4-5-20250929]"
    created: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    human_directed: bool = True

    # Reasoning (XAI)
    intent: str | None = None
    approach: str | None = None
    tradeoffs: str | None = None

    # Spec
    size: str
    performance: str = "composite-only"
    theme: str = "adaptive"
    a11y: str = "WCAG-AA"

    # Theme DNA
    theme_dna: ThemeDNA | None = None


class BadgeResponse(BaseModel):
    """Response model for badge generation."""

    svg: str = Field(description="Generated SVG artifact")
    metadata: HyperWeaveMetadata = Field(description="Artifact metadata")
    theme_dna: ThemeDNA = Field(description="Complete primitive fingerprint")
    url: str | None = Field(None, description="Canonical URL for this artifact")


class OntologyCategoryResponse(BaseModel):
    """Response for querying ontology categories."""

    category: str
    count: int
    items: list[dict[str, Any]]
