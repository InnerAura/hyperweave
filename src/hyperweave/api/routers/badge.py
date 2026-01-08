"""
Badge generation router.

Direct badge generation endpoints (non-specimen path).
"""

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from hyperweave.core.generator import BadgeGenerator
from hyperweave.core.ontology import OntologyLoader
from hyperweave.models.badge import BadgeRequest, BadgeResponse

router = APIRouter()

# Shared instances
_ontology: OntologyLoader | None = None
_generator: BadgeGenerator | None = None


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


@router.post("/badge")
async def generate_badge(request: BadgeRequest) -> Response:
    """
    Generate a badge from a complete badge request.

    This endpoint allows full customization of all badge parameters.
    For production use, prefer the specimen-based generation endpoints
    which use pre-validated configurations.

    The request must include:
    - content: label and value text
    - Optional: shape, finishes, seam, shadow, border, motion, indicator
    - Optional: reasoning for XAI provenance (required if artifact_tier=FULL)

    Example:
        POST /v3/badge
        {
            "content": {"label": "build", "value": "passing", "state": "passing"},
            "shape": "standard",
            "finish_label": "chrome-metal",
            "finish_value": "chrome-dark",
            "seam": "vertical",
            "size": "md",
            "artifact_tier": "FULL",
            "reasoning": {
                "intent": "CI/CD status indicator",
                "approach": "Chrome finish for high contrast",
                "tradeoffs": "Chose vertical seam over diagonal for simpler maintenance"
            }
        }
    """
    generator = get_generator()

    # Validate reasoning if artifact_tier is FULL
    if request.artifact_tier == "FULL" and not request.reasoning:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Bad Request",
                "detail": "reasoning is required when artifact_tier is FULL",
            },
        )

    # Generate badge
    badge_response: BadgeResponse = generator.generate(request)

    # Return SVG
    return Response(
        content=badge_response.svg,
        media_type="image/svg+xml",
        headers={
            "Content-Type": "image/svg+xml; charset=utf-8",
            "X-Ontology-Version": "2.0.0",
            "X-Series": badge_response.theme_dna.series or "",
            "X-Performance-Tier": "composite-only",
        },
    )


@router.post("/badge/json")
async def generate_badge_json(request: BadgeRequest) -> BadgeResponse:
    """
    Generate a badge and return complete JSON response with metadata.

    Same as POST /v3/badge but returns JSON with:
    - svg: The complete SVG string
    - metadata: HyperWeave artifact metadata
    - theme_dna: Complete primitive fingerprint
    - url: Canonical regeneration URL

    This is useful for debugging, storing badge configurations,
    or integrating with systems that need structured metadata.
    """
    generator = get_generator()

    # Validate reasoning if artifact_tier is FULL
    if request.artifact_tier == "FULL" and not request.reasoning:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Bad Request",
                "detail": "reasoning is required when artifact_tier is FULL",
            },
        )

    # Generate badge
    badge_response = generator.generate(request)

    return badge_response
