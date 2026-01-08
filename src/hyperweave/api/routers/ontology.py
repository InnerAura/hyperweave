"""
Ontology query router.

Endpoints for discovering and querying HyperWeave v7 Living Artifact Ontology.
Theme-centric architecture with 20 themes across 6 tiers.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from hyperweave.core.ontology import OntologyLoader

router = APIRouter(prefix="/ontology")

# Shared ontology instance
_ontology: OntologyLoader | None = None


def get_ontology() -> OntologyLoader:
    """Get or initialize the ontology loader."""
    global _ontology
    if _ontology is None:
        _ontology = OntologyLoader()
    return _ontology


@router.get("")
async def get_ontology_summary():
    """
    Get a high-level summary of the HyperWeave v7 Ontology.

    Returns counts and available IDs for themes, motions, glyphs, and effects.
    Theme-centric architecture with 20 themes across 6 tiers.

    The ontology is the single source of truth for badge generation.
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

    return {
        "version": ontology.get_version(),
        "protocol": "HyperWeave Living Artifact Protocol v7",
        "formula": {
            "canonical": "BADGE = Theme(state) × Content × Motion_Override?",
            "paradigm": "Theme as atomic unit (not primitive composition)",
        },
        "themes": {
            "total": len(themes),
            "by_tier": {tier: len(ids) for tier, ids in tiers.items()},
            "tiers": list(tiers.keys()),
            "examples": list(themes.keys())[:5],
        },
        "motions": {
            "total": len(motions),
            "available": list(motions.keys()),
        },
        "glyphs": {
            "total": len(glyphs),
            "types": list(glyphs.keys()),
        },
        "effects": {
            "total": len(effects),
            "available": list(effects.keys())[:10],
        },
        "series": {
            "total": len(series_groups),
            "available": list(series_groups.keys()),
        },
    }


@router.get("/themes")
async def list_themes(
    tier: str | None = Query(None, description="Filter by tier (e.g., 'industrial', 'flagship')"),
    series: str | None = Query(None, description="Filter by series (e.g., 'core', 'scholarly')"),
    include_full: bool = Query(False, description="Include full theme definitions"),
) -> dict[str, Any]:
    """
    List all themes with optional filters.

    Examples:
    - GET /ontology/themes
    - GET /ontology/themes?tier=industrial
    - GET /ontology/themes?series=scholarly
    - GET /ontology/themes?tier=flagship&include_full=true
    """
    ontology = get_ontology()

    # Apply filters
    # NOTE: get_themes_by_tier/series return List[Dict], get_all_themes returns Dict[str, Dict]
    if tier:
        theme_list = ontology.get_themes_by_tier(tier)  # Returns List[Dict]
        if include_full:
            return {
                "count": len(theme_list),
                "themes": theme_list,  # Already has "id" in each dict
            }
        else:
            return {
                "count": len(theme_list),
                "themes": [
                    {
                        "id": theme.get("id"),
                        "tier": theme.get("tier"),
                        "series": theme.get("series"),
                        "compatible_motions": theme.get("compatibleMotions", []),
                        "effects": theme.get("effects", []),
                    }
                    for theme in theme_list
                ],
            }
    elif series:
        theme_list = ontology.get_themes_by_series(series)  # Returns List[Dict]
        if include_full:
            return {
                "count": len(theme_list),
                "themes": theme_list,  # Already has "id" in each dict
            }
        else:
            return {
                "count": len(theme_list),
                "themes": [
                    {
                        "id": theme.get("id"),
                        "tier": theme.get("tier"),
                        "series": theme.get("series"),
                        "compatible_motions": theme.get("compatibleMotions", []),
                        "effects": theme.get("effects", []),
                    }
                    for theme in theme_list
                ],
            }
    else:
        themes = ontology.get_all_themes()  # Returns Dict[str, Dict]
        if include_full:
            return {
                "count": len(themes),
                "themes": [
                    {
                        "id": theme_id,
                        **theme,
                    }
                    for theme_id, theme in themes.items()
                ],
            }
        else:
            return {
                "count": len(themes),
                "themes": [
                    {
                        "id": theme_id,
                        "tier": theme.get("tier"),
                        "series": theme.get("series"),
                        "compatible_motions": theme.get("compatibleMotions", []),
                        "effects": theme.get("effects", []),
                    }
                    for theme_id, theme in themes.items()
                ],
            }


@router.get("/themes/{theme_id}")
async def get_theme_detail(theme_id: str) -> dict[str, Any]:
    """
    Get detailed configuration for a specific theme.

    Returns complete theme definition including:
    - Visual properties (label/value gradients, colors)
    - State overrides (passing, warning, failing, neutral)
    - Compatible motions
    - Effects array
    - Metadata (tier, series, XAI reasoning)

    Example:
    - GET /ontology/themes/chrome
    """
    ontology = get_ontology()

    try:
        theme = ontology.get_theme(theme_id)
        return {
            "id": theme_id,
            **theme,
        }
    except KeyError:
        available = ontology.get_all_theme_ids()
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Theme not found",
                "theme": theme_id,
                "available": available,
                "suggestion": f"Did you mean one of: {', '.join(available[:5])}?",
            },
        )


@router.get("/motions")
async def list_motions() -> dict[str, Any]:
    """
    List all motion definitions.

    Returns motion metadata including duration, timing functions, and descriptions.

    Example:
    - GET /ontology/motions
    """
    ontology = get_ontology()
    motions = ontology.get_all_motions()

    return {
        "count": len(motions),
        "motions": [
            {
                "id": motion_id,
                **motion,
            }
            for motion_id, motion in motions.items()
        ],
    }


@router.get("/glyphs")
async def list_glyphs() -> dict[str, Any]:
    """
    List all glyph definitions.

    Returns glyph type configurations for status indicators.

    Example:
    - GET /ontology/glyphs
    """
    ontology = get_ontology()
    glyphs = ontology.get_all_glyphs()

    return {
        "count": len(glyphs),
        "glyphs": [
            {
                "id": glyph_id,
                **glyph,
            }
            for glyph_id, glyph in glyphs.items()
        ],
    }


@router.get("/effects")
async def list_effects() -> dict[str, Any]:
    """
    List all effect definitions.

    Returns effect configurations including filters, gradients, and animations.

    Example:
    - GET /ontology/effects
    """
    ontology = get_ontology()
    effects = ontology.get_all_effect_definitions()

    return {
        "count": len(effects),
        "effects": [
            {
                "id": effect_id,
                **effect,
            }
            for effect_id, effect in effects.items()
        ],
    }
