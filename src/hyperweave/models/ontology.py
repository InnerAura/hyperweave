"""
Pydantic models for Ontology primitives.

Based on spec v3.3 and consolidated ontology.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel


class OntologyVersion(str, Enum):
    """Supported ontology versions."""

    V1_0 = "1.0.0"
    V2_0 = "2.0.0"


class FinishFamily(str, Enum):
    """Finish primitive families."""

    VOID = "void"
    CHROME = "chrome"
    INDUSTRIAL_METALS = "industrial-metals"
    GLASS = "glass"
    NEON = "neon"
    HOLOGRAPHIC = "holographic"
    BRUTALIST = "brutalist"


class SeamFamily(str, Enum):
    """Seam primitive families."""

    GEOMETRIC = "geometric"
    CRAFT = "craft"
    INDUSTRIAL_METALS = "industrial-metals"
    BRUTALIST = "brutalist"


class Series(str, Enum):
    """Design series with compatibility constraints."""

    FIERCE_WHITE = "fierce-white"
    HERCULEAN_CHROME = "herculean-chrome"
    COSMIC = "cosmic"


class PerformanceTier(str, Enum):
    """Animation performance tiers."""

    COMPOSITE_ONLY = "composite-only"
    PAINT_OK = "paint-ok"
    LAYOUT_HEAVY = "layout-heavy"


class BadgeState(str, Enum):
    """Badge state types."""

    PASSING = "passing"
    WARNING = "warning"
    FAILING = "failing"
    NEUTRAL = "neutral"
    ACTIVE = "active"
    LIVE = "live"
    PROTECTED = "protected"


class BadgeShape(str, Enum):
    """Badge shape types."""

    STANDARD = "standard"
    PILL = "pill"
    SQUARE = "square"


# ─────────────────────────────────────────────────────────────
# THEME-CENTRIC ENUMS (v7 Architecture)
# ─────────────────────────────────────────────────────────────


class ThemeTier(str, Enum):
    """
    Theme tiers for v7 theme-centric architecture.

    Tiers represent aesthetic categories with distinct visual characteristics:
    - minimal: Clean, void-based designs
    - flagship: High-impact, polished finishes (neon, glass, holo)
    - premium: Luxurious depth effects (depth, glossy)
    - industrial: Metallic, engineered aesthetics (chrome, titanium, obsidian)
    - brutalist: Raw, architectural designs
    - cosmology: Space-inspired aesthetics (sakura, aurora, singularity)
    - scholarly: Academic, intellectual themes (codex, theorem, archive, symposium, cipher)
    - arcade: Retro gaming console themes
    """

    MINIMAL = "minimal"
    FLAGSHIP = "flagship"
    PREMIUM = "premium"
    INDUSTRIAL = "industrial"
    BRUTALIST = "brutalist"
    COSMOLOGY = "cosmology"
    SCHOLARLY = "scholarly"
    ARCADE = "arcade"


class ThemeSeries(str, Enum):
    """
    Theme series for grouping related themes.

    Series represent design families with shared visual language:
    - core: Foundational themes across all tiers (15 themes)
    - five-scholars: Academic themes for research/documentation (5 themes)
    - retro-console: Arcade gaming console themes (5 themes)
    """

    CORE = "core"
    FIVE_SCHOLARS = "five-scholars"
    RETRO_CONSOLE = "retro-console"


class OntologyCategory(str, Enum):
    """
    Queryable ontology categories for MCP and API.

    Categories available for ontology queries:
    - themes: 25 visual themes across 8 tiers
    - motions: 8 animation primitives (breathe, pulse, sweep, etc.)
    - glyphs: 10 semantic indicators (dot, check, cross, star, etc.)
    - effects: Visual effect definitions (shadows, glows, borders)
    """

    THEMES = "themes"
    MOTIONS = "motions"
    GLYPHS = "glyphs"
    EFFECTS = "effects"


# ─────────────────────────────────────────────────────────────
# PRIMITIVE SUMMARY MODELS (for API responses)
# ─────────────────────────────────────────────────────────────


class GradientStop(BaseModel):
    """Single gradient stop definition."""

    offset: str
    color: str
    opacity: float | None = None


class FinishSummary(BaseModel):
    """Finish primitive summary for API response."""

    id: str
    family: str | None = None
    series: str | None = None
    description: str
    gradient_type: str | None = None
    complexity: int | None = None
    luminance: str | None = None
    pairs_with: str | None = None


class SeamSummary(BaseModel):
    """Seam primitive summary for API response."""

    id: str
    family: str | None = None
    series: str | None = None
    heritage: str | None = None
    semantics: str | None = None
    description: str | None = None
    aesthetic: str | None = None
    composable: bool = False


class ShadowSummary(BaseModel):
    """Shadow primitive summary for API response."""

    id: str
    family: str | None = None
    series: str | None = None
    compound: bool = False
    aesthetic: str


class MotionSummary(BaseModel):
    """Motion primitive summary for API response."""

    id: str
    description: str
    duration: str | None = None
    timing: str | None = None
    properties: list[str] | None = None


class IndicatorSummary(BaseModel):
    """Indicator primitive summary for API response."""

    id: str
    description: str
    animated: bool = False
    viewBox: str | None = None


class BorderSummary(BaseModel):
    """Border primitive summary for API response."""

    id: str
    family: str | None = None
    stroke: str
    width: float
    radius: float
    inset: float


class SpecimenSummary(BaseModel):
    """Specimen configuration summary."""

    id: str
    series: str
    finish_label: str | None = None
    finish_value: str | None = None
    finish_base: str | None = None
    finish_overlay: str | None = None
    seam: str
    shadow: str | None = None
    border: str | None = None
    motion: str | None = None
    indicator: str | None = None
    radius: int
    layout: dict[str, Any]


class SeriesSummary(BaseModel):
    """Series definition summary."""

    id: str
    description: str
    philosophy: str
    compatible_finishes: list[str]
    compatible_seams: list[str]
    compatible_shadows: list[str]
    border_style: str
    luminance_range: list[str]


class ValidationIssue(BaseModel):
    """Validation issue report."""

    rule_id: str
    severity: str = "error"
    message: str
    field: str | None = None


class OntologyQueryResponse(BaseModel):
    """Response for ontology query endpoints."""

    category: str
    count: int
    items: list[dict[str, Any]]
