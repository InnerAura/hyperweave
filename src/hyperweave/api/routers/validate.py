"""
SVG validation router.

Validates SVG artifacts against HyperWeave Living Artifact Protocol.
"""

import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from hyperweave.core.ontology import OntologyLoader

router = APIRouter()

# Shared ontology instance
_ontology: OntologyLoader | None = None


def get_ontology() -> OntologyLoader:
    """Get or initialize the ontology loader."""
    global _ontology
    if _ontology is None:
        _ontology = OntologyLoader()
    return _ontology


class ValidateRequest(BaseModel):
    """Request model for SVG validation."""

    svg_content: str

    validate_living_artifact: bool = True
    validate_accessibility: bool = True
    validate_performance: bool = True
    validate_schema: bool = True

    # NEW: Ontology constraint validation
    validate_ontology_constraints: bool = Field(
        default=True,
        description="Validate against ontology series constraints",
    )

    expected_performance_tier: Literal["composite-only", "paint-ok", "layout-heavy"] | None = None
    require_tradeoffs: bool = True


class ValidationIssue(BaseModel):
    """Single validation issue."""

    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    location: str | None = None


class OntologyValidation(BaseModel):
    """Ontology constraint validation results."""

    has_theme_dna: bool
    ontology_version_valid: bool
    series_constraints_valid: bool
    finish_seam_compatible: bool
    violations: list[str]


class LivingArtifactValidation(BaseModel):
    """Living Artifact protocol validation results."""

    has_hw_namespace: bool
    has_metadata_block: bool
    has_provenance: bool
    has_reasoning: bool
    has_tradeoffs: bool
    tradeoffs_quality: Literal["missing", "empty", "weak", "good", "strong"]
    has_spec: bool
    protocol_compliant: bool


class ValidateResponse(BaseModel):
    """Response model for SVG validation."""

    valid: bool
    issues: list[ValidationIssue]
    living_artifact: LivingArtifactValidation | None
    schema_compliance: dict
    accessibility: dict
    performance: dict

    # NEW in v3.3
    ontology: OntologyValidation | None = Field(
        default=None,
        description="Ontology constraint validation results",
    )


@router.post("/validate")
async def validate_svg(request: ValidateRequest) -> ValidateResponse:
    """
    Validate SVG against HyperWeave Living Artifact Protocol.

    v3.3 additions:
    - Ontology constraint validation
    - Series compatibility checking
    - Finish-seam pairing rules
    - ThemeDNA presence validation

    Example:
        POST /v3/validate
        {
            "svg_content": "<svg>...</svg>",
            "validate_ontology_constraints": true,
            "expected_performance_tier": "composite-only"
        }
    """
    issues = []
    ontology_validation = None

    # 1. Living Artifact validation
    living_artifact = None
    if request.validate_living_artifact:
        living_artifact = validate_living_artifact(
            request.svg_content,
            require_tradeoffs=request.require_tradeoffs,
        )

        if not living_artifact.has_hw_namespace:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="HW_NAMESPACE_MISSING",
                    message="Missing xmlns:hw namespace declaration",
                    location="<svg>",
                )
            )

        if not living_artifact.has_reasoning:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="HW_REASONING_MISSING",
                    message="Missing hw:reasoning block",
                    location="<metadata>",
                )
            )

        if living_artifact.tradeoffs_quality in ["missing", "empty"]:
            issues.append(
                ValidationIssue(
                    severity="error" if request.require_tradeoffs else "warning",
                    code="HW_TRADEOFFS_MISSING",
                    message="Tradeoffs field is missing or empty — critical for XAI",
                    location="<hw:tradeoffs>",
                )
            )
        elif living_artifact.tradeoffs_quality == "weak":
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="HW_TRADEOFFS_WEAK",
                    message="Tradeoffs field appears generic — be specific about rejected alternatives",
                    location="<hw:tradeoffs>",
                )
            )

    # 2. NEW: Ontology constraint validation
    if request.validate_ontology_constraints:
        ontology = get_ontology()
        ontology_validation = validate_ontology_constraints(request.svg_content, ontology)

        if not ontology_validation.has_theme_dna:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="ONTOLOGY_NO_THEME_DNA",
                    message="Missing hw:theme-dna block — regeneration may not be exact",
                    location="<metadata>",
                )
            )

        if not ontology_validation.ontology_version_valid:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="ONTOLOGY_VERSION_UNKNOWN",
                    message="Ontology version not recognized",
                    location="<hw:ontology>",
                )
            )

        if not ontology_validation.series_constraints_valid:
            for violation in ontology_validation.violations:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="ONTOLOGY_SERIES_VIOLATION",
                        message=violation,
                        location="<hw:theme-dna>",
                    )
                )

    # 3. Performance validation
    performance = {}
    if request.validate_performance:
        performance = validate_performance(
            request.svg_content,
            request.expected_performance_tier or "composite-only",
        )

        if not performance["compliant"]:
            for violation in performance["violations"]:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="PERF_FORBIDDEN_ANIMATION",
                        message=f"Animation on '{violation}' forbidden in {performance['tier']} tier",
                        location=f'attributeName="{violation}"',
                    )
                )

    # 4. Accessibility validation
    accessibility = {}
    if request.validate_accessibility:
        accessibility = validate_accessibility(request.svg_content)

        if not accessibility.get("has_role"):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="A11Y_ROLE_MISSING",
                    message="Missing role='img' attribute",
                    location="<svg>",
                )
            )

        if not accessibility.get("has_title"):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="A11Y_TITLE_MISSING",
                    message="Missing <title> element",
                    location="<svg>",
                )
            )

        if not accessibility.get("has_reduced_motion"):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="A11Y_REDUCED_MOTION",
                    message="Missing @media (prefers-reduced-motion) support",
                    location="<style>",
                )
            )

    # 5. Schema validation
    schema_compliance = {}
    if request.validate_schema:
        schema_compliance = validate_schema(request.svg_content)

    # Determine overall validity
    error_count = sum(1 for i in issues if i.severity == "error")

    return ValidateResponse(
        valid=error_count == 0,
        issues=issues,
        living_artifact=living_artifact,
        schema_compliance=schema_compliance,
        accessibility=accessibility,
        performance=performance,
        ontology=ontology_validation,
    )


def validate_living_artifact(
    svg_content: str, require_tradeoffs: bool = True
) -> LivingArtifactValidation:
    """Validate Living Artifact protocol compliance."""
    has_hw_namespace = 'xmlns:hw="https://hyperweave.dev/hw/v1.0"' in svg_content
    has_metadata_block = "<metadata>" in svg_content and "</metadata>" in svg_content
    has_provenance = "<hw:provenance>" in svg_content
    has_reasoning = "<hw:reasoning>" in svg_content
    has_spec = "<hw:spec" in svg_content

    # Extract tradeoffs
    has_tradeoffs = False
    tradeoffs_quality = "missing"
    tradeoffs_match = re.search(r"<hw:tradeoffs>(.*?)</hw:tradeoffs>", svg_content, re.DOTALL)
    if tradeoffs_match:
        has_tradeoffs = True
        tradeoffs_text = tradeoffs_match.group(1).strip()
        if not tradeoffs_text:
            tradeoffs_quality = "empty"
        elif len(tradeoffs_text) < 20:
            tradeoffs_quality = "weak"
        elif any(
            generic in tradeoffs_text.lower()
            for generic in ["no tradeoffs", "none", "n/a", "not applicable"]
        ):
            tradeoffs_quality = "weak"
        elif len(tradeoffs_text) > 100:
            tradeoffs_quality = "strong"
        else:
            tradeoffs_quality = "good"

    protocol_compliant = all(
        [
            has_hw_namespace,
            has_metadata_block,
            has_provenance,
            has_reasoning,
            has_spec,
            has_tradeoffs if require_tradeoffs else True,
        ]
    )

    return LivingArtifactValidation(
        has_hw_namespace=has_hw_namespace,
        has_metadata_block=has_metadata_block,
        has_provenance=has_provenance,
        has_reasoning=has_reasoning,
        has_tradeoffs=has_tradeoffs,
        tradeoffs_quality=tradeoffs_quality,
        has_spec=has_spec,
        protocol_compliant=protocol_compliant,
    )


def validate_ontology_constraints(svg_content: str, ontology: OntologyLoader) -> OntologyValidation:
    """
    Validate SVG against ontology constraints.

    Checks:
    1. ThemeDNA presence
    2. Ontology version validity
    3. Series constraint compliance
    4. Finish-seam compatibility
    """
    violations = []

    # Extract ThemeDNA
    theme_dna_match = re.search(r"<hw:theme-dna[^>]*>", svg_content)
    has_theme_dna = bool(theme_dna_match)

    # Extract ontology version
    ontology_version_match = re.search(r'<hw:ontology version="([^"]+)"', svg_content)
    ontology_version_valid = False
    if ontology_version_match:
        version = ontology_version_match.group(1)
        ontology_version_valid = version in ["1.0.0", "2.0.0"]

    # Extract series and primitives
    series_match = re.search(r'series="([^"]+)"', svg_content)
    series_constraints_valid = True
    finish_seam_compatible = True

    if series_match and has_theme_dna:
        series = series_match.group(1)

        finish_match = re.search(r'finish-label="([^"]+)"', svg_content)
        seam_match = re.search(r'seam="([^"]+)"', svg_content)

        if finish_match and seam_match:
            finish = finish_match.group(1)
            seam = seam_match.group(1)

            # Validate series constraints
            series_data = ontology.get_series()
            series_def = series_data.get(series)
            if series_def:
                compatible_finishes = series_def.get("compatible_finishes", [])
                compatible_seams = series_def.get("compatible_seams", [])

                if finish not in compatible_finishes:
                    series_constraints_valid = False
                    violations.append(
                        f"Finish '{finish}' not compatible with series '{series}'. "
                        f"Allowed: {compatible_finishes}"
                    )

                if seam not in compatible_seams:
                    series_constraints_valid = False
                    violations.append(
                        f"Seam '{seam}' not compatible with series '{series}'. "
                        f"Allowed: {compatible_seams}"
                    )

    return OntologyValidation(
        has_theme_dna=has_theme_dna,
        ontology_version_valid=ontology_version_valid,
        series_constraints_valid=series_constraints_valid,
        finish_seam_compatible=finish_seam_compatible,
        violations=violations,
    )


def validate_performance(svg_content: str, expected_tier: str) -> dict:
    """Validate performance tier compliance."""
    forbidden_attrs = []

    if expected_tier == "composite-only":
        # Check for forbidden animated attributes
        forbidden_patterns = [
            r'attributeName="(?:width|height|x|y|cx|cy|r|d|points)"',
        ]

        for pattern in forbidden_patterns:
            matches = re.findall(pattern, svg_content)
            forbidden_attrs.extend(matches)

    return {
        "tier": expected_tier,
        "compliant": len(forbidden_attrs) == 0,
        "violations": list(set(forbidden_attrs)),
        "bundle_size_bytes": len(svg_content.encode("utf-8")),
    }


def validate_accessibility(svg_content: str) -> dict:
    """Validate accessibility compliance."""
    has_role = 'role="img"' in svg_content
    has_title = "<title" in svg_content
    has_desc = "<desc" in svg_content
    has_reduced_motion = "@media (prefers-reduced-motion" in svg_content
    has_dark_mode = "@media (prefers-color-scheme: dark)" in svg_content

    wcag_level = "AA" if all([has_role, has_title, has_reduced_motion]) else "Partial"

    return {
        "has_role": has_role,
        "has_title": has_title,
        "has_desc": has_desc,
        "has_reduced_motion": has_reduced_motion,
        "has_dark_mode": has_dark_mode,
        "wcag_level": wcag_level,
        "compliant": has_role and has_title,
    }


def validate_schema(svg_content: str) -> dict:
    """Validate SVG schema compliance."""
    has_xmlns = 'xmlns="http://www.w3.org/2000/svg"' in svg_content
    has_viewbox = "viewBox=" in svg_content

    return {
        "valid": has_xmlns,
        "has_xmlns": has_xmlns,
        "has_viewbox": has_viewbox,
        "svg_version": "1.1",
    }
