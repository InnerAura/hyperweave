"""
URL Grammar Router - Tier 1: Simple GET-based badge generation.

Implements the HyperWeave URL Grammar v1.0 specification for Tier 1:
    /{data-source}/{theme}.{motion}.{format}

Example:
    GET /github.readme-ai.eli64s.stars/chrome.pulse.svg
    → Fetches stars for eli64s/readme-ai
    → Applies chrome theme
    → Adds pulse animation
    → Returns Living SVG badge
"""


import httpx
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse

from hyperweave.core.generator import BadgeGenerator
from hyperweave.core.ontology import OntologyLoader
from hyperweave.models.badge import BadgeContent, BadgeRequest, BadgeState

router = APIRouter()

# Shared instances
_ontology: OntologyLoader | None = None
_generator: BadgeGenerator | None = None
_http_client: httpx.AsyncClient | None = None


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


def get_http_client() -> httpx.AsyncClient:
    """Get or initialize HTTP client for API calls."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


# ─────────────────────────────────────────────────────────────
# THEME & MOTION VALIDATION (v7 - Dynamic Loading)
# ─────────────────────────────────────────────────────────────


def get_theme_config(theme_id: str) -> dict:
    """
    Load theme configuration dynamically from ontology.

    Args:
        theme_id: Theme identifier (e.g., 'chrome', 'codex', 'neon')

    Returns:
        Theme configuration dict

    Raises:
        HTTPException: If theme not found in ontology
    """
    ontology = get_ontology()
    try:
        return ontology.get_theme(theme_id)
    except KeyError:
        available_themes = ontology.get_all_theme_ids()
        available = ", ".join(sorted(available_themes))

        # Get suggestion using Levenshtein distance
        from difflib import get_close_matches

        suggestions = get_close_matches(theme_id, available_themes, n=1, cutoff=0.6)
        suggestion = suggestions[0] if suggestions else None

        error_detail = {
            "error": "Theme not found",
            "theme": theme_id,
            "available_themes": sorted(available_themes),
        }
        if suggestion:
            error_detail["suggestion"] = suggestion

        raise HTTPException(
            status_code=404,
            detail=error_detail,
        )


def validate_motion(theme: dict, motion_id: str | None) -> str:
    """
    Validate motion compatibility with theme.

    Args:
        theme: Theme configuration dict
        motion_id: Motion identifier (or None for default)

    Returns:
        Validated motion identifier

    Raises:
        HTTPException: If motion incompatible with theme
    """
    compatible_motions = theme.get("compatibleMotions", ["static"])

    # Use default if no motion specified
    if motion_id is None:
        return compatible_motions[0]  # First compatible motion is default

    # Validate compatibility
    if motion_id not in compatible_motions:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Motion incompatible with theme",
                "theme": theme["id"],
                "motion": motion_id,
                "compatible_motions": compatible_motions,
            },
        )

    return motion_id


# ─────────────────────────────────────────────────────────────
# DATA FETCHERS
# ─────────────────────────────────────────────────────────────


async def fetch_github_metric(owner: str, repo: str, metric: str) -> dict:
    """
    Fetch GitHub repository metric.

    Args:
        owner: Repository owner
        repo: Repository name
        metric: Metric to fetch (stars, forks, issues, watchers)

    Returns:
        {"label": str, "value": str, "state": BadgeState}
    """
    client = get_http_client()

    try:
        # Fetch repo data from GitHub API
        response = await client.get(f"https://api.github.com/repos/{owner}/{repo}")
        response.raise_for_status()
        data = response.json()

        # Extract metric
        metric_map = {
            "stars": ("stargazers_count", "stars"),
            "forks": ("forks_count", "forks"),
            "issues": ("open_issues_count", "issues"),
            "watchers": ("watchers_count", "watchers"),
        }

        if metric not in metric_map:
            raise HTTPException(status_code=400, detail=f"Unknown metric: {metric}")

        field_name, label = metric_map[metric]
        value = data.get(field_name, 0)

        # Format large numbers
        if value >= 1000:
            value_str = f"{value / 1000:.1f}k"
        else:
            value_str = str(value)

        return {"label": label, "value": value_str, "state": BadgeState.NEUTRAL}

    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {e}")


async def fetch_static_value(value: str) -> dict:
    """
    Return static value as-is.

    Args:
        value: Static value to display

    Returns:
        {"label": str, "value": str, "state": BadgeState}
    """
    # Infer label from common patterns
    state_map = {
        "passing": BadgeState.PASSING,
        "failed": BadgeState.FAILING,
        "warning": BadgeState.WARNING,
        "active": BadgeState.ACTIVE,
    }

    label = "status"
    state = state_map.get(value.lower(), BadgeState.NEUTRAL)

    return {"label": label, "value": value, "state": state}


# ─────────────────────────────────────────────────────────────
# URL GRAMMAR PARSER
# ─────────────────────────────────────────────────────────────


def parse_data_source(data_source: str) -> tuple[str, dict]:
    """
    Parse data source segment.

    Patterns:
        github.{owner}.{repo}.{metric}
        npm.{package}.{metric}
        static.{value}

    Args:
        data_source: Data source string

    Returns:
        (provider, params) tuple
    """
    parts = data_source.split(".")

    if parts[0] == "github":
        if len(parts) != 4:
            raise HTTPException(status_code=400, detail="GitHub pattern: github.owner.repo.metric")
        return "github", {"owner": parts[1], "repo": parts[2], "metric": parts[3]}

    elif parts[0] == "npm":
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="npm pattern: npm.package.metric")
        return "npm", {"package": parts[1], "metric": parts[2]}

    elif parts[0] == "static":
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Static pattern: static.value")
        return "static", {"value": parts[1]}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {parts[0]}")


def parse_style_chain(style_chain: str) -> tuple[str, str | None, str]:
    """
    Parse style chain segment.

    Patterns:
        {theme}.{motion}.{format}
        {theme}.{format}

    Args:
        style_chain: Style chain string

    Returns:
        (theme, motion, format) tuple
    """
    parts = style_chain.split(".")

    if len(parts) == 3:
        # theme.motion.format
        return parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        # theme.format (no motion)
        return parts[0], None, parts[1]
    else:
        raise HTTPException(
            status_code=400, detail="Style chain pattern: theme.motion.format or theme.format"
        )


# ─────────────────────────────────────────────────────────────
# TIER 1 ENDPOINT
# ─────────────────────────────────────────────────────────────


@router.get("/{data_source:path}/{style_chain}")
async def generate_badge_tier1(data_source: str, style_chain: str) -> Response:
    """
    Tier 1: Simple GET-based badge generation.

    URL Pattern:
        /{data-source}/{theme}.{motion}.{format}

    Examples:
        GET /github.readme-ai.eli64s.stars/chrome.pulse.svg
        GET /npm.fastmcp.downloads/glass.svg
        GET /static.passing/neon.sweep.svg

    Args:
        data_source: Data source (github.owner.repo.metric, npm.package.metric, static.value)
        style_chain: Style specification (theme.motion.format or theme.format)

    Returns:
        SVG badge or JSON response based on format
    """
    # Parse data source
    provider, params = parse_data_source(data_source)

    # Parse style chain
    theme_id, motion_id, format_type = parse_style_chain(style_chain)

    # Load theme from ontology (dynamic loading)
    theme = get_theme_config(theme_id)

    # Validate motion compatibility
    validated_motion = validate_motion(theme, motion_id)

    # Validate format
    if format_type not in ["svg", "json", "png"]:
        raise HTTPException(
            status_code=400, detail=f"Unsupported format: {format_type}. Use: svg, json, png"
        )

    # Fetch data
    if provider == "github":
        content_data = await fetch_github_metric(params["owner"], params["repo"], params["metric"])
    elif provider == "static":
        content_data = await fetch_static_value(params["value"])
    else:
        raise HTTPException(status_code=501, detail=f"Provider not implemented: {provider}")

    # Build badge request (v7 theme-centric)
    generator = get_generator()

    badge_request = BadgeRequest(
        theme=theme_id,  # Single theme field replaces all primitive fields
        content=BadgeContent(
            label=content_data["label"],
            value=content_data["value"],
            state=content_data["state"],
        ),
        motion=validated_motion,
        size="md",
        artifact_tier="FULL",
        reasoning={
            "intent": f"Display {content_data['label']} metric from {provider}",
            "approach": f"Using {theme_id} theme ({theme['tier']} tier) with {validated_motion} motion",
            "tradeoffs": f"Chose {theme_id} from {theme['series']} series for visual coherence; "
            f"opted for URL-based generation over POST API for simplicity",
        },
    )

    # Generate badge
    response = generator.generate(badge_request)

    # Return based on format
    if format_type == "json":
        return JSONResponse(
            content={
                "svg_content": response.svg,
                "theme_dna": response.theme_dna.model_dump(),
                "metadata": response.metadata.model_dump(),
                "url": f"/{data_source}/{style_chain}",
            }
        )
    else:
        return Response(
            content=response.svg,
            media_type="image/svg+xml",
            headers={
                "Content-Type": "image/svg+xml; charset=utf-8",
                "X-Theme": theme_id,
                "X-Theme-Tier": theme["tier"],
                "X-Theme-Series": theme["series"],
                "X-Motion": validated_motion,
                "X-Ontology-Version": "7.0.0",
                "Cache-Control": "public, max-age=300",
            },
        )
