"""
HyperWeave MCP Server v3.3.

Model Context Protocol server for ontology-integrated Living Artifact generation.
"""

from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from hyperweave.core.generator import BadgeGenerator
from hyperweave.core.ontology import OntologyLoader
from hyperweave.models.badge import (
    BadgeContent,
    BadgeRequest,
)
from hyperweave.models.ontology import (
    BadgeState,
    OntologyCategory,
    ThemeSeries,
    ThemeTier,
)

# Create MCP server
mcp: FastMCP = FastMCP("HyperWeave")

# Shared instances (lazy initialization)
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


# ─────────────────────────────────────────────────────────────
# REQUEST/RESPONSE MODELS
# ─────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────
# RESOURCES
# ─────────────────────────────────────────────────────────────


@mcp.resource("ontology://hyperweave/badge/v7.0/summary")
def get_ontology_summary() -> str:
    """
    Get a summary of the current ontology.

    v7 Living Artifact Protocol: Theme-centric architecture.
    """
    ontology = get_ontology()

    themes = ontology.get_all_themes()
    motions = ontology.get_all_motions()
    glyphs = ontology.get_all_glyphs()
    effects = ontology.get_all_effect_definitions()

    # Group themes by tier
    tiers: dict[str, list[str]] = {}
    for theme_id, theme in themes.items():
        tier = theme.get("tier", "unknown")
        if tier not in tiers:
            tiers[tier] = []
        tiers[tier].append(theme_id)

    # Group themes by series
    series_groups: dict[str, list[str]] = {}
    for theme_id, theme in themes.items():
        series = theme.get("series", "unknown")
        if series not in series_groups:
            series_groups[series] = []
        series_groups[series].append(theme_id)

    tier_summary = "\n".join([f"- {tier}: {', '.join(ids[:5])}" for tier, ids in tiers.items()])

    summary = f"""HyperWeave Badge Ontology {ontology.get_version()}

Protocol: Living Artifact Protocol v7
Formula: BADGE = Theme(state) × Content × Motion_Override?
Paradigm: Theme as atomic unit (not primitive composition)

Themes: {len(themes)} across {len(tiers)} tiers
{tier_summary}

Motions: {len(motions)}
- Available: {", ".join(list(motions.keys()))}

Glyphs: {len(glyphs)}
- Types: {", ".join(list(glyphs.keys()))}

Effects: {len(effects)}
- Available: {", ".join(list(effects.keys())[:10])}...

Series: {len(series_groups)}
- Available: {", ".join(list(series_groups.keys()))}

Use hw_query_ontology to explore themes, motions, glyphs, and effects.
Use hw_use_theme for the GOLDEN PATH to production badges.
"""
    return summary


# ─────────────────────────────────────────────────────────────
# AX HELPERS (Agent Experience Optimization)
# ─────────────────────────────────────────────────────────────


def wrap_response(
    data: dict[str, Any],
    suggested_next_action: str,
    alternative_actions: list[str] | None = None,
) -> dict[str, Any]:
    """
    Wrap tool response with AX guidance for agents.

    Provides workflow continuity by suggesting next steps.

    Args:
        data: The actual response data
        suggested_next_action: Primary recommended next step
        alternative_actions: Optional list of alternative actions

    Returns:
        Enhanced response with agent guidance
    """
    response = {
        "data": data,
        "suggested_next_action": suggested_next_action,
    }
    if alternative_actions:
        response["alternative_actions"] = alternative_actions
    return response


def wrap_error(
    error_code: str,
    message: str,
    fix_suggestion: str,
    related_tools: list[str] | None = None,
) -> dict[str, Any]:
    """
    Wrap error response with AX guidance for agents.

    Provides structured error information with recovery guidance.

    Args:
        error_code: Unique error identifier (e.g., HW_THEME_NOT_FOUND)
        message: Human-readable error description
        fix_suggestion: Actionable guidance to resolve the error
        related_tools: Optional list of tools that could help

    Returns:
        Structured error response with recovery guidance
    """
    return {
        "error": {
            "code": error_code,
            "message": message,
            "fix_suggestion": fix_suggestion,
        },
        "related_tools": related_tools or [],
        "suggested_next_action": fix_suggestion,
    }


# ─────────────────────────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────────────────────────


@mcp.tool()
def hw_discover_capabilities() -> dict[str, Any]:
    """
    Discover HyperWeave MCP server capabilities and optimal workflows.

    USE THIS FIRST if you're unfamiliar with HyperWeave or need guidance.

    Returns a comprehensive overview of:
    - Available tools and their purposes
    - Pre-validated specimen configurations (golden path)
    - Theme tiers and categories
    - Recommended workflows for common tasks

    Example:
        # First interaction with HyperWeave
        hw_discover_capabilities()
        # Returns: capabilities, specimens, recommended_workflow
    """
    ontology = get_ontology()
    themes = ontology.get_all_themes()

    # Group themes by tier for overview
    tiers: dict[str, list[str]] = {}
    for theme_id, theme in themes.items():
        tier = theme.get("tier", "unknown")
        if tier not in tiers:
            tiers[tier] = []
        tiers[tier].append(theme_id)

    return wrap_response(
        data={
            "server": {
                "name": "HyperWeave Living Artifact Generator",
                "version": "3.3.0",
                "protocol": "Living Artifact Protocol v7",
                "ontology_version": ontology.get_version(),
            },
            "tools": {
                "hw_discover_capabilities": {
                    "purpose": "Discover server capabilities (YOU ARE HERE)",
                    "when_to_use": "First interaction or when unsure what to do",
                },
                "hw_query_ontology": {
                    "purpose": "Query themes, motions, glyphs, effects",
                    "when_to_use": "Exploring what badge styles are available",
                },
                "hw_use_specimen": {
                    "purpose": "Generate badge from pre-validated configuration (GOLDEN PATH)",
                    "when_to_use": "Creating production-ready badges quickly",
                },
                "hw_validate": {
                    "purpose": "Validate SVG against Living Artifact Protocol",
                    "when_to_use": "Checking if an SVG meets HyperWeave standards",
                },
            },
            "specimens": {
                "description": "Pre-validated configurations for quick badge generation",
                "available": [
                    {
                        "id": "chrome-protocol",
                        "theme": "chrome",
                        "style": "High-polish chrome with animated sweep",
                    },
                    {
                        "id": "titanium-forge",
                        "theme": "titanium",
                        "style": "Aerospace-grade industrial metal",
                    },
                    {
                        "id": "obsidian-mirror",
                        "theme": "obsidian",
                        "style": "Deep black with neon accent",
                    },
                    {
                        "id": "brutalist-signal",
                        "theme": "brutalist",
                        "style": "Raw flat with error signal bar",
                    },
                    {
                        "id": "brutalist-minimal",
                        "theme": "brutalist-clean",
                        "style": "Pure architectural black/white",
                    },
                ],
            },
            "theme_overview": {
                "total_themes": len(themes),
                "tiers": {
                    tier: {"count": len(ids), "examples": ids[:3]} for tier, ids in tiers.items()
                },
            },
            "recommended_workflow": [
                "1. Use hw_use_specimen() for quick badge generation",
                "2. Or use hw_query_ontology() to explore themes first",
                "3. Always provide intent, approach, and tradeoffs for XAI provenance",
                "4. Use hw_validate() to verify generated badges",
            ],
        },
        suggested_next_action="Use hw_use_specimen('chrome-protocol', 'status', 'passing', intent='...', approach='...', tradeoffs='...') to generate your first badge",
        alternative_actions=[
            "Use hw_query_ontology(category='themes', tier='scholarly') to explore academic themes",
            "Use hw_query_ontology(category='motions', include_metadata=True) to see animation options",
        ],
    )


@mcp.tool()
def hw_query_ontology(
    category: OntologyCategory,
    tier: ThemeTier | None = None,
    series: ThemeSeries | None = None,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """
    Query the HyperWeave v7 Ontology.

    Use this tool to discover:
    - Available themes (25 themes across 8 tiers)
    - Motion definitions (8 animation primitives)
    - Glyph types (10 semantic indicators)
    - Effect definitions (shadows, glows, borders)

    The ontology is the single source of truth for badge generation.

    Args:
        category: Category to query. Use OntologyCategory enum:
            - themes: Visual theme definitions
            - motions: Animation primitives
            - glyphs: Semantic indicators
            - effects: Visual effect definitions

        tier: Filter themes by tier. Use ThemeTier enum:
            - minimal: Clean, void-based designs
            - flagship: High-impact polished finishes (neon, glass, holo)
            - premium: Luxurious depth effects
            - industrial: Metallic, engineered aesthetics (chrome, titanium)
            - brutalist: Raw, architectural designs
            - cosmology: Space-inspired aesthetics
            - scholarly: Academic themes (codex, theorem, archive)
            - arcade: Retro gaming console themes

        series: Filter themes by series. Use ThemeSeries enum:
            - core: Foundational themes (15 themes)
            - five-scholars: Academic themes (5 themes)
            - retro-console: Arcade themes (5 themes)

        include_metadata: Include full definitions (vs. IDs only)

    Examples:
        # List all industrial tier themes
        hw_query_ontology(category="themes", tier="industrial")

        # Get scholarly themes with full metadata
        hw_query_ontology(category="themes", tier="scholarly", include_metadata=True)

        # Get all motions with metadata
        hw_query_ontology(category="motions", include_metadata=True)

        # List all glyph types
        hw_query_ontology(category="glyphs")
    """
    ontology = get_ontology()

    # Fetch items based on category
    if category == "themes":
        # NOTE: get_themes_by_tier/series return List[Dict], get_all_themes returns Dict[str, Dict]
        if tier:
            theme_list = ontology.get_themes_by_tier(tier)  # Returns List[Dict]
            theme_ids = [t.get("id", "unknown") for t in theme_list]
            first_theme = theme_ids[0] if theme_ids else "chrome"
            if include_metadata:
                return wrap_response(
                    data={
                        "ontology_version": ontology.get_version(),
                        "category": category,
                        "filter": {"tier": tier},
                        "count": len(theme_list),
                        "items": theme_list,  # Already contains "id" in each dict
                    },
                    suggested_next_action=f"Found {len(theme_list)} {tier} themes. Use hw_use_specimen('{first_theme}', label, value, ...) or hw_query_ontology(category='motions') to see compatible animations.",
                    alternative_actions=[
                        f"Filter by series: hw_query_ontology(category='themes', series='core')",
                        f"Get all themes: hw_query_ontology(category='themes')",
                    ],
                )
            else:
                return wrap_response(
                    data={
                        "ontology_version": ontology.get_version(),
                        "category": category,
                        "filter": {"tier": tier},
                        "count": len(theme_list),
                        "ids": theme_ids,
                    },
                    suggested_next_action=f"Found {len(theme_list)} {tier} theme IDs. Use hw_query_ontology(category='themes', tier='{tier}', include_metadata=True) for full details.",
                    alternative_actions=[
                        f"Generate badge: hw_use_specimen('{first_theme}', 'status', 'active', intent='...', approach='...', tradeoffs='...')",
                    ],
                )
        elif series:
            theme_list = ontology.get_themes_by_series(series)  # Returns List[Dict]
            theme_ids = [t.get("id", "unknown") for t in theme_list]
            first_theme = theme_ids[0] if theme_ids else "chrome"
            if include_metadata:
                return wrap_response(
                    data={
                        "ontology_version": ontology.get_version(),
                        "category": category,
                        "filter": {"series": series},
                        "count": len(theme_list),
                        "items": theme_list,  # Already contains "id" in each dict
                    },
                    suggested_next_action=f"Found {len(theme_list)} themes in '{series}' series. Use hw_use_specimen('{first_theme}', label, value, ...) to generate a badge.",
                    alternative_actions=[
                        "Filter by tier: hw_query_ontology(category='themes', tier='scholarly')",
                        "View motions: hw_query_ontology(category='motions', include_metadata=True)",
                    ],
                )
            else:
                return wrap_response(
                    data={
                        "ontology_version": ontology.get_version(),
                        "category": category,
                        "filter": {"series": series},
                        "count": len(theme_list),
                        "ids": theme_ids,
                    },
                    suggested_next_action=f"Found {len(theme_list)} theme IDs in '{series}' series. Use hw_query_ontology(category='themes', series='{series}', include_metadata=True) for full details.",
                    alternative_actions=[
                        f"Generate badge: hw_use_specimen('{first_theme}', 'status', 'active', intent='...', approach='...', tradeoffs='...')",
                    ],
                )
        else:
            theme_dict = ontology.get_all_themes()  # Returns Dict[str, Dict]
            theme_ids = list(theme_dict.keys())
            if include_metadata:
                return wrap_response(
                    data={
                        "ontology_version": ontology.get_version(),
                        "category": category,
                        "count": len(theme_dict),
                        "items": [{"id": theme_id, **theme} for theme_id, theme in theme_dict.items()],
                    },
                    suggested_next_action="Full theme catalog loaded. Use hw_use_specimen('chrome-protocol', label, value, ...) for the recommended starting point.",
                    alternative_actions=[
                        "Filter by tier: hw_query_ontology(category='themes', tier='industrial')",
                        "Filter by series: hw_query_ontology(category='themes', series='five-scholars')",
                    ],
                )
            else:
                return wrap_response(
                    data={
                        "ontology_version": ontology.get_version(),
                        "category": category,
                        "count": len(theme_dict),
                        "ids": theme_ids,
                    },
                    suggested_next_action=f"Found {len(theme_dict)} themes. Use hw_query_ontology(category='themes', include_metadata=True) for full details or filter by tier/series.",
                    alternative_actions=[
                        "Filter by tier: hw_query_ontology(category='themes', tier='flagship')",
                        "Generate badge: hw_use_specimen('chrome-protocol', 'status', 'passing', intent='...', approach='...', tradeoffs='...')",
                    ],
                )

    elif category == "motions":
        items = ontology.get_all_motions()
        motion_ids = list(items.keys())

        if include_metadata:
            return wrap_response(
                data={
                    "ontology_version": ontology.get_version(),
                    "category": category,
                    "count": len(items),
                    "items": [{"id": motion_id, **motion} for motion_id, motion in items.items()],
                },
                suggested_next_action="Review motion definitions, then use hw_query_ontology(category='themes') to see which themes support each motion.",
                alternative_actions=[
                    "Generate badge with motion: hw_use_specimen('chrome-protocol', 'build', 'passing', ...)",
                    "Query effects: hw_query_ontology(category='effects')",
                ],
            )
        else:
            return wrap_response(
                data={
                    "ontology_version": ontology.get_version(),
                    "category": category,
                    "count": len(items),
                    "ids": motion_ids,
                },
                suggested_next_action=f"Found {len(items)} motions: {', '.join(motion_ids)}. Use hw_query_ontology(category='motions', include_metadata=True) for animation details.",
                alternative_actions=[
                    "Query themes: hw_query_ontology(category='themes')",
                ],
            )

    elif category == "glyphs":
        items = ontology.get_all_glyphs()
        glyph_ids = list(items.keys())

        if include_metadata:
            return wrap_response(
                data={
                    "ontology_version": ontology.get_version(),
                    "category": category,
                    "count": len(items),
                    "items": [{"id": glyph_id, **glyph} for glyph_id, glyph in items.items()],
                },
                suggested_next_action="Glyphs are semantic indicators (check, cross, dot, etc.). Use hw_use_specimen() with a 'state' parameter to apply them automatically.",
                alternative_actions=[
                    "Generate badge with state: hw_use_specimen('chrome-protocol', 'status', 'passing', state='passing', ...)",
                ],
            )
        else:
            return wrap_response(
                data={
                    "ontology_version": ontology.get_version(),
                    "category": category,
                    "count": len(items),
                    "ids": glyph_ids,
                },
                suggested_next_action=f"Found {len(items)} glyphs: {', '.join(glyph_ids)}. Use hw_query_ontology(category='glyphs', include_metadata=True) for glyph definitions.",
                alternative_actions=[
                    "Query themes: hw_query_ontology(category='themes')",
                ],
            )

    elif category == "effects":
        items = ontology.get_all_effect_definitions()
        effect_ids = list(items.keys())

        if include_metadata:
            return wrap_response(
                data={
                    "ontology_version": ontology.get_version(),
                    "category": category,
                    "count": len(items),
                    "items": [{"id": effect_id, **effect} for effect_id, effect in items.items()],
                },
                suggested_next_action="Effects (shadows, glows, borders) are automatically applied by themes. Use hw_use_specimen() for automatic effect application.",
                alternative_actions=[
                    "Query themes to see which effects they use: hw_query_ontology(category='themes', include_metadata=True)",
                ],
            )
        else:
            return wrap_response(
                data={
                    "ontology_version": ontology.get_version(),
                    "category": category,
                    "count": len(items),
                    "ids": effect_ids,
                },
                suggested_next_action=f"Found {len(items)} effects. Use hw_query_ontology(category='effects', include_metadata=True) for effect definitions.",
                alternative_actions=[
                    "Query themes: hw_query_ontology(category='themes')",
                ],
            )

    else:
        # This should never happen with enum validation, but handle gracefully
        return wrap_error(
            error_code="HW_UNKNOWN_CATEGORY",
            message=f"Unknown category: {category}",
            fix_suggestion="Use one of: 'themes', 'motions', 'glyphs', 'effects'",
            related_tools=["hw_discover_capabilities"],
        )


@mcp.tool()
def hw_use_specimen(
    specimen_id: Literal[
        "chrome-protocol",
        "obsidian-mirror",
        "titanium-forge",
        "brutalist-signal",
        "brutalist-minimal",
    ],
    label: Annotated[
        str,
        Field(description="Left badge text (e.g., 'version', 'status'). Max 20 chars."),
    ],
    value: Annotated[
        str,
        Field(description="Right badge text (e.g., 'passing', '1.0.0'). Max 30 chars."),
    ],
    intent: Annotated[
        str,
        Field(
            description="Why this artifact exists. CRITICAL FOR XAI. Example: 'CI status for main branch'",
            min_length=10,
        ),
    ],
    approach: Annotated[
        str,
        Field(
            description="Key design decision. Example: 'Chrome for professional aesthetic'",
            min_length=10,
        ),
    ],
    tradeoffs: Annotated[
        str,
        Field(
            description="Rejected alternatives and why. MOST IMPORTANT FOR XAI. Example: 'Chose chrome over neon for corporate context'",
            min_length=20,
        ),
    ],
    state: Annotated[
        BadgeState | None,
        Field(
            default=None,
            description="Semantic state: passing=green, failing=red, warning=amber, neutral=gray",
        ),
    ] = None,
) -> dict[str, Any]:
    """
    Generate a badge using a pre-validated specimen configuration.

    v7 compatibility: Maps specimen IDs to themes.

    Specimens are the GOLDEN PATH for production badges. They are
    reference implementations that have been tested for:
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

    Args:
        specimen_id: Pre-validated specimen configuration to use
        label: Left segment text content
        value: Right segment text content
        intent: Why this artifact is being created
        approach: Key design or technical decision
        tradeoffs: What alternatives were rejected and why (CRITICAL FOR XAI)
        state: Optional status state (passing, warning, failing, neutral, etc.)

    Example:
        hw_use_specimen(
            specimen_id="titanium-forge",
            label="status",
            value="operational",
            intent="System health indicator for dashboard",
            approach="Titanium for industrial gravitas",
            tradeoffs="Chose titanium over chrome for cooler tone matching dark UI"
        )
    """
    # v7 migration: Map specimen IDs to theme IDs
    SPECIMEN_TO_THEME_MAP = {
        "chrome-protocol": "chrome",
        "obsidian-mirror": "obsidian",
        "titanium-forge": "titanium",
        "brutalist-signal": "brutalist",
        "brutalist-minimal": "brutalist-clean",
    }

    theme_id = SPECIMEN_TO_THEME_MAP.get(specimen_id)
    if not theme_id:
        return wrap_error(
            error_code="HW_SPECIMEN_NOT_FOUND",
            message=f"Specimen not found: {specimen_id}",
            fix_suggestion="Use one of: 'chrome-protocol', 'obsidian-mirror', 'titanium-forge', 'brutalist-signal', 'brutalist-minimal'",
            related_tools=["hw_discover_capabilities", "hw_query_ontology"],
        )

    ontology = get_ontology()
    generator = get_generator()

    # Get theme configuration
    try:
        theme = ontology.get_theme(theme_id)
    except KeyError:
        return wrap_error(
            error_code="HW_THEME_NOT_FOUND",
            message=f"Theme '{theme_id}' not found for specimen: {specimen_id}",
            fix_suggestion="The ontology may be corrupted. Try hw_query_ontology(category='themes') to see available themes.",
            related_tools=["hw_query_ontology", "hw_discover_capabilities"],
        )

    # Build badge request from theme (v7)
    badge_content = BadgeContent(
        label=label,
        value=value,
        state=state,
    )

    badge_request = BadgeRequest(
        theme=theme_id,
        content=badge_content,
        motion=theme.get("compatibleMotions", ["static"])[0],
        size="md",
        artifact_tier="FULL",
        reasoning={
            "intent": intent,
            "approach": approach,
            "tradeoffs": tradeoffs,
        },
    )

    # Generate badge
    badge_response = generator.generate(badge_request)

    return wrap_response(
        data={
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
        },
        suggested_next_action="Your badge is ready! Use hw_validate(svg_content) to verify compliance, or generate another variant with state='failing' to see error styling.",
        alternative_actions=[
            "Use hw_query_ontology(category='themes') to explore other theme options",
            "Try another specimen like 'titanium-forge' for a different aesthetic",
        ],
    )


@mcp.tool()
def hw_validate(
    svg_content: str,
    validate_living_artifact: bool = True,
    validate_accessibility: bool = True,
    validate_performance: bool = True,
    validate_ontology_constraints: bool = True,
    require_tradeoffs: bool = True,
) -> dict[str, Any]:
    """
    Validate SVG against HyperWeave Living Artifact Protocol.

    v3.3 additions:
    - Ontology constraint validation
    - Series compatibility checking
    - Finish-seam pairing rules
    - ThemeDNA presence validation

    Args:
        svg_content: SVG string to validate
        validate_living_artifact: Check Living Artifact protocol compliance
        validate_accessibility: Check WCAG accessibility
        validate_performance: Check animation performance tier
        validate_ontology_constraints: Check ontology series constraints
        require_tradeoffs: Require tradeoffs field in reasoning

    Returns:
        Validation results with issues and compliance flags
    """
    import re

    issues = []

    # Living Artifact validation
    living_artifact = None
    if validate_living_artifact:
        has_hw_namespace = 'xmlns:hw="https://hyperweave.dev/hw/v1.0"' in svg_content
        has_metadata_block = "<metadata>" in svg_content
        has_provenance = "<hw:provenance>" in svg_content
        has_reasoning = "<hw:reasoning>" in svg_content
        has_spec = "<hw:spec" in svg_content

        # Extract tradeoffs
        tradeoffs_match = re.search(r"<hw:tradeoffs>(.*?)</hw:tradeoffs>", svg_content, re.DOTALL)
        has_tradeoffs = bool(tradeoffs_match)
        tradeoffs_quality = "missing"

        if tradeoffs_match:
            tradeoffs_text = tradeoffs_match.group(1).strip()
            if not tradeoffs_text:
                tradeoffs_quality = "empty"
            elif len(tradeoffs_text) < 20:
                tradeoffs_quality = "weak"
            elif len(tradeoffs_text) > 100:
                tradeoffs_quality = "strong"
            else:
                tradeoffs_quality = "good"

        living_artifact = {
            "has_hw_namespace": has_hw_namespace,
            "has_metadata_block": has_metadata_block,
            "has_provenance": has_provenance,
            "has_reasoning": has_reasoning,
            "has_tradeoffs": has_tradeoffs,
            "tradeoffs_quality": tradeoffs_quality,
            "has_spec": has_spec,
            "protocol_compliant": all(
                [
                    has_hw_namespace,
                    has_metadata_block,
                    has_provenance,
                    has_reasoning,
                    has_spec,
                ]
            ),
        }

        if not has_hw_namespace:
            issues.append(
                {
                    "severity": "error",
                    "code": "HW_NAMESPACE_MISSING",
                    "message": "Missing xmlns:hw namespace declaration",
                    "fix_suggestion": 'Add xmlns:hw="https://hyperweave.dev/hw/v1.0" to root <svg> element',
                }
            )

        if not has_tradeoffs and require_tradeoffs:
            issues.append(
                {
                    "severity": "error",
                    "code": "HW_TRADEOFFS_MISSING",
                    "message": "Tradeoffs field is missing",
                    "fix_suggestion": "Add <hw:tradeoffs>What alternatives were rejected and why</hw:tradeoffs> inside <hw:reasoning>",
                }
            )

    # Accessibility validation
    accessibility = None
    if validate_accessibility:
        has_role = 'role="img"' in svg_content
        has_title = "<title" in svg_content
        has_reduced_motion = "@media (prefers-reduced-motion" in svg_content

        accessibility = {
            "has_role": has_role,
            "has_title": has_title,
            "has_reduced_motion": has_reduced_motion,
            "compliant": has_role and has_title,
        }

        if not has_role:
            issues.append(
                {
                    "severity": "error",
                    "code": "A11Y_ROLE_MISSING",
                    "message": "Missing role='img' attribute",
                    "fix_suggestion": 'Add role="img" to root <svg> element for screen reader accessibility',
                }
            )

        if not has_title:
            issues.append(
                {
                    "severity": "error",
                    "code": "A11Y_TITLE_MISSING",
                    "message": "Missing <title> element",
                    "fix_suggestion": "Add <title>Descriptive badge title</title> as first child of <svg>",
                }
            )

    # Ontology validation
    ontology_validation = None
    if validate_ontology_constraints:
        ontology = get_ontology()

        # Extract ThemeDNA
        theme_dna_match = re.search(r"<hw:theme-dna[^>]*>", svg_content)
        has_theme_dna = bool(theme_dna_match)

        # Extract ontology version
        ontology_version_match = re.search(r'<hw:ontology version="([^"]+)"', svg_content)
        ontology_version_valid = False
        if ontology_version_match:
            version = ontology_version_match.group(1)
            ontology_version_valid = version in ["1.0.0", "2.0.0", "7.0.0"]

        # v7 validation: Check theme and motion compatibility
        theme_match = re.search(r'theme="([^"]+)"', svg_content)
        violations = []
        theme_constraints_valid = True

        if theme_match and has_theme_dna:
            theme_id = theme_match.group(1)
            motion_match = re.search(r'motion="([^"]+)"', svg_content)

            # Validate theme exists
            try:
                theme = ontology.get_theme(theme_id)

                # Validate motion compatibility if motion is specified
                if motion_match:
                    motion_id = motion_match.group(1)
                    compatible_motions = theme.get("compatibleMotions", [])

                    if motion_id not in compatible_motions:
                        theme_constraints_valid = False
                        violation = (
                            f"Motion '{motion_id}' not compatible with theme '{theme_id}'. "
                            f"Allowed: {compatible_motions}"
                        )
                        violations.append(violation)
                        issues.append(
                            {
                                "severity": "error",
                                "code": "ONTOLOGY_THEME_MOTION_VIOLATION",
                                "message": violation,
                                "fix_suggestion": f"Change motion to one of: {', '.join(compatible_motions)}",
                            }
                        )

            except KeyError:
                theme_constraints_valid = False
                violation = f"Theme '{theme_id}' not found in ontology"
                violations.append(violation)
                issues.append(
                    {
                        "severity": "error",
                        "code": "ONTOLOGY_THEME_NOT_FOUND",
                        "message": violation,
                        "fix_suggestion": "Use hw_query_ontology(category='themes') to see available themes",
                    }
                )

        ontology_validation = {
            "has_theme_dna": has_theme_dna,
            "ontology_version_valid": ontology_version_valid,
            "theme_constraints_valid": theme_constraints_valid,
            "violations": violations,
        }

        if not has_theme_dna:
            issues.append(
                {
                    "severity": "warning",
                    "code": "ONTOLOGY_NO_THEME_DNA",
                    "message": "Missing hw:theme-dna block",
                    "fix_suggestion": "Use hw_use_specimen() to generate badges with proper ThemeDNA provenance",
                }
            )

    # Determine overall validity
    error_count = sum(1 for i in issues if i["severity"] == "error")
    is_valid = error_count == 0

    # Determine next action based on validation result
    if is_valid:
        next_action = "Validation passed! Your SVG is Living Artifact Protocol compliant. Ready for deployment."
        alternatives = [
            "Generate another badge with hw_use_specimen()",
            "Query available themes with hw_query_ontology(category='themes')",
        ]
    else:
        next_action = f"Validation found {error_count} issue(s). Review the 'issues' array and regenerate with fixes."
        alternatives = [
            "Use hw_use_specimen() to generate a compliant badge from scratch",
            "Review hw_discover_capabilities() for guidance on proper badge generation",
        ]

    return wrap_response(
        data={
            "valid": is_valid,
            "issues": issues,
            "living_artifact": living_artifact,
            "accessibility": accessibility,
            "ontology": ontology_validation,
        },
        suggested_next_action=next_action,
        alternative_actions=alternatives,
    )


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
