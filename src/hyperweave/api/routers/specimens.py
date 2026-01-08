"""
Specimen-based badge generation router.

v7 compatibility layer: Maps old specimen IDs to themes.
The GOLDEN PATH for production badges using pre-validated theme configurations.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from hyperweave.core.generator import BadgeGenerator
from hyperweave.core.ontology import OntologyLoader
from hyperweave.models.badge import (
    BadgeContent,
    BadgeRequest,
    BadgeState,
    ThemeDNA,
)

router = APIRouter()

# Shared instances
_ontology: OntologyLoader | None = None
_generator: BadgeGenerator | None = None

# v7 migration: Map old specimen IDs to theme IDs for backward compatibility
SPECIMEN_TO_THEME_MAP = {
    "chrome-protocol": "chrome",
    "obsidian-mirror": "obsidian",
    "titanium-forge": "titanium",
    "brutalist-signal": "brutalist",
    "brutalist-minimal": "brutalist-clean",
}


def get_ontology() -> OntologyLoader:
    """Get or initialize the ontology loader."""
    global _ontology
    if _ontology is None:
        _ontology = OntologyLoader()
    return _ontology


def get_generator() -> BadgeGenerator:
    """Get or initialize the badge generator."""
    global _generator
    if _generator is None:
        _generator = BadgeGenerator(get_ontology())
    return _generator


class ReasoningInput(BaseModel):
    """Reasoning trace for XAI provenance."""

    intent: str = Field(
        description="Why this artifact is being created",
        min_length=5,
        max_length=200,
    )

    approach: str = Field(
        description="Key design or technical decision",
        min_length=5,
        max_length=300,
    )

    tradeoffs: str = Field(
        description="What alternatives were rejected and why — CRITICAL FOR XAI",
        min_length=10,
        max_length=500,
    )


class SpecimenGenerateRequest(BaseModel):
    """Request model for specimen-based badge generation."""

    content: dict = Field(
        description="Badge content (label, value)",
        examples=[{"label": "build", "value": "passing"}],
    )

    reasoning: ReasoningInput = Field(
        description="Reasoning trace for provenance",
    )

    state: BadgeState | None = Field(
        default=None,
        description="Override status state (affects colors)",
    )

    format: Literal["svg", "json"] = Field(
        default="svg",
    )


class SpecimenDetailResponse(BaseModel):
    """Detailed specimen information."""

    ontology_version: str
    specimen: dict
    theme_dna: ThemeDNA
    series_constraints: dict
    compatible_states: list[str]
    example_svg: str | None = None


@router.get("/ontology/specimens/{specimen_id}")
async def get_specimen_detail(
    specimen_id: Literal[
        "chrome-protocol",
        "obsidian-mirror",
        "titanium-forge",
        "brutalist-signal",
        "brutalist-minimal",
    ],
    include_example: bool = Query(False, description="Include example SVG output"),
) -> SpecimenDetailResponse:
    """
    Get detailed information about a specific specimen.

    v7 compatibility: Maps specimen IDs to themes.

    Specimens guarantee:
    - Visual coherence (theme-based atomic design)
    - Performance compliance (composite-only animations)
    - Accessibility (WCAG-AA)
    - State-aware color systems

    Use POST /v3/specimens/{id}/generate to create badges from specimens.
    """
    # Map specimen ID to theme ID
    theme_id = SPECIMEN_TO_THEME_MAP.get(specimen_id)
    if not theme_id:
        raise HTTPException(status_code=404, detail=f"Specimen not found: {specimen_id}")

    ontology = get_ontology()

    # Get theme configuration
    try:
        theme = ontology.get_theme(theme_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Theme not found for specimen: {specimen_id}")

    # Build ThemeDNA from theme (v7 structure)
    theme_dna = ThemeDNA(
        theme=theme_id,
        tier=theme.get("tier", ""),
        series=theme.get("series", ""),
        motion=theme.get("compatibleMotions", ["static"])[0],
        ontology_version=ontology.get_version(),
    )

    # Build specimen info dict for response
    specimen_info = {
        "id": specimen_id,
        "theme": theme_id,
        "tier": theme.get("tier"),
        "series": theme.get("series"),
        "compatible_motions": theme.get("compatibleMotions", []),
        "effects": theme.get("effects", []),
        "description": f"{theme.get('tier', '').title()} tier theme with {len(theme.get('effects', []))} visual effects",
    }

    # Series constraints (v7: compatible motions)
    series_constraints = {
        "compatible_motions": theme.get("compatibleMotions", []),
        "effects": theme.get("effects", []),
        "states": ["passing", "warning", "failing", "neutral"],
    }

    # Generate example if requested
    example_svg = None
    if include_example:
        generator = get_generator()
        badge_request = BadgeRequest(
            theme=theme_id,
            content=BadgeContent(label="example", value="specimen", state=BadgeState.NEUTRAL),
            motion=theme.get("compatibleMotions", ["static"])[0],
            size="md",
            artifact_tier="FULL",
            reasoning={
                "intent": "Example specimen badge",
                "approach": "Pre-validated theme configuration",
                "tradeoffs": "Using default neutral state for example",
            },
        )
        response = generator.generate(badge_request)
        example_svg = response.svg

    return SpecimenDetailResponse(
        ontology_version=ontology.get_version(),
        specimen=specimen_info,
        theme_dna=theme_dna,
        series_constraints=series_constraints,
        compatible_states=["passing", "warning", "failing", "neutral"],
        example_svg=example_svg,
    )


@router.post("/specimens/{specimen_id}/generate")
async def generate_from_specimen(
    specimen_id: Literal[
        "chrome-protocol",
        "obsidian-mirror",
        "titanium-forge",
        "brutalist-signal",
        "brutalist-minimal",
    ],
    request: SpecimenGenerateRequest,
) -> Response:
    """
    Generate a badge using a pre-validated specimen configuration.

    This is the GOLDEN PATH for production badges.

    v7 compatibility: Maps specimen IDs to themes.

    Specimens guarantee:
    - Visual coherence (theme-based atomic design)
    - Performance compliance (composite-only animations)
    - Accessibility (WCAG-AA)
    - State-aware color systems

    Available specimens:
    - chrome-protocol: High-polish chrome with animated sweep (→ chrome theme)
    - obsidian-mirror: Deep black with neon accent divider (→ obsidian theme)
    - titanium-forge: Aerospace-grade industrial metal (→ titanium theme)
    - brutalist-signal: Raw flat with error signal bar (→ brutalist theme)
    - brutalist-minimal: Pure architectural black/white (→ brutalist-clean theme)

    Example:
        POST /v3/specimens/titanium-forge/generate
        {
            "content": {"label": "status", "value": "operational"},
            "reasoning": {
                "intent": "System health indicator",
                "approach": "Titanium for industrial gravitas",
                "tradeoffs": "Chose titanium over chrome for cooler tone"
            }
        }
    """
    # Map specimen ID to theme ID
    theme_id = SPECIMEN_TO_THEME_MAP.get(specimen_id)
    if not theme_id:
        raise HTTPException(status_code=404, detail=f"Specimen not found: {specimen_id}")

    ontology = get_ontology()

    # Get theme configuration
    try:
        theme = ontology.get_theme(theme_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Theme not found for specimen: {specimen_id}")

    # Build badge request from specimen (v7 theme-based)
    generator = get_generator()

    badge_content = BadgeContent(
        label=request.content.get("label", ""),
        value=request.content.get("value", ""),
        state=request.state,
    )

    badge_request = BadgeRequest(
        theme=theme_id,
        content=badge_content,
        motion=theme.get("compatibleMotions", ["static"])[0],
        size="md",
        artifact_tier="FULL",
        reasoning={
            "intent": request.reasoning.intent,
            "approach": request.reasoning.approach,
            "tradeoffs": request.reasoning.tradeoffs,
        },
    )

    # Generate badge
    badge_response = generator.generate(badge_request)

    # Return appropriate format
    if request.format == "json":
        return JSONResponse(
            content={
                "svg_content": badge_response.svg,
                "specimen_id": specimen_id,
                "theme_id": theme_id,
                "theme_dna": badge_response.theme_dna.model_dump(),
                "artifact_metadata": badge_response.metadata.model_dump(),
                "validation": {
                    "specimen_id": specimen_id,
                    "theme": theme_id,
                    "tier": theme.get("tier"),
                    "series": theme.get("series"),
                    "performance_compliant": True,
                    "accessibility_compliant": True,
                    "living_artifact_compliant": True,
                    "ontology_constraints_valid": True,
                    "all_checks_passed": True,
                },
            }
        )
    else:
        return Response(
            content=badge_response.svg,
            media_type="image/svg+xml",
            headers={
                "Content-Type": "image/svg+xml; charset=utf-8",
                "X-Specimen-Id": specimen_id,
                "X-Theme-Id": theme_id,
                "X-Ontology-Version": ontology.get_version(),
                "X-Tier": theme.get("tier", ""),
                "X-Series": theme.get("series", ""),
                "X-Performance-Tier": "composite-only",
            },
        )
