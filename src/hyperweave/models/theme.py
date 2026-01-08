"""
HyperWeave v7 Theme Models - Living Artifact Protocol.

Pydantic models for theme-centric badge generation.
Themes are self-contained atomic units with all visual properties.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GradientConfig(BaseModel):
    """
    Gradient configuration for label/value sections.

    Attributes:
        direction: Gradient orientation (vertical, horizontal, diagonal)
        stops: List of color stops (hex color strings)
    """

    direction: Literal["vertical", "horizontal", "diagonal"] = Field(
        description="Gradient direction"
    )
    stops: list[str] = Field(
        description="Color stops as hex strings (e.g., ['#FF0000', '#0000FF'])"
    )


class LabelConfig(BaseModel):
    """
    Label section visual configuration.

    Can use either gradient OR solid fill.
    Text color is always specified.

    Attributes:
        gradient: Optional gradient configuration
        fill: Optional solid fill color
        text: Text color (hex string)
    """

    gradient: GradientConfig | None = Field(
        None, description="Gradient configuration (mutually exclusive with fill)"
    )
    fill: str | None = Field(
        None, description="Solid fill color (mutually exclusive with gradient)"
    )
    text: str = Field(description="Label text color (hex string)")


class ValueConfig(BaseModel):
    """
    Value section visual configuration.

    Can use either gradient OR solid fill.
    Text color is always specified.

    Attributes:
        gradient: Optional gradient configuration
        fill: Optional solid fill color
        text: Text color (hex string)
    """

    gradient: GradientConfig | None = Field(
        None, description="Gradient configuration (mutually exclusive with fill)"
    )
    fill: str | None = Field(
        None, description="Solid fill color (mutually exclusive with gradient)"
    )
    text: str = Field(description="Value text color (hex string)")


class ShadowConfig(BaseModel):
    """
    Drop shadow configuration.

    Attributes:
        color: Shadow color (rgba or hex)
        blur: Blur radius in pixels
        y: Vertical offset in pixels
        x: Horizontal offset in pixels (default 0)
    """

    color: str = Field(description="Shadow color (rgba() or hex)")
    blur: float = Field(description="Blur radius (stdDeviation)")
    y: float = Field(description="Vertical offset (dy)")
    x: float = Field(default=0, description="Horizontal offset (dx)")


class BorderConfig(BaseModel):
    """
    Border/stroke configuration.

    Can use either solid color OR gradient.

    Attributes:
        color: Optional solid border color
        gradient: Optional gradient color stops
        width: Stroke width in pixels
        radius: Corner radius in pixels
        animated: Whether border is animated
    """

    color: str | None = Field(
        None, description="Solid border color (mutually exclusive with gradient)"
    )
    gradient: list[str] | None = Field(
        None, description="Gradient color stops (mutually exclusive with color)"
    )
    width: float = Field(description="Stroke width in pixels")
    radius: int = Field(description="Corner radius in pixels")
    animated: bool = Field(default=False, description="Whether border has animated gradient")


class GlyphConfig(BaseModel):
    """
    Glyph (indicator) configuration.

    Specifies which glyph to render and whether it's animated.

    Attributes:
        type: Glyph type (none, dot, check, cross, star, etc.)
        animation: Whether glyph is animated
        duration: Optional animation duration
    """

    type: Literal[
        "none", "dot", "check", "cross", "star", "arrow-up", "arrow-down", "warning", "info", "live"
    ] = Field(description="Glyph type from glyphs ontology")
    animation: bool = Field(default=False, description="Whether glyph has animation")
    duration: str | None = Field(None, description="Animation duration (e.g., '2.618s')")


class StateOverride(BaseModel):
    """
    State-specific visual overrides.

    Each theme defines complete overrides for all 4 states.
    Overrides can change value colors and glyph colors.

    Attributes:
        value: Value section override (can specify gradient or useDefault)
        glyph: Glyph color override
        rim: Optional rim colors (for clarity theme)
        signal: Optional signal color (for brutalist theme)
        accent: Optional accent override (for obsidian theme)
    """

    value: dict[str, Any] = Field(
        description="Value section override (gradient, fill, text, or useDefault: true)"
    )
    glyph: str = Field(description="Glyph color (hex string)")
    rim: list[str] | None = Field(None, description="Rim gradient colors (clarity theme only)")
    signal: str | None = Field(None, description="Signal bar color (brutalist theme only)")
    accent: Any | None = Field(None, description="Accent color override (obsidian theme)")


class Theme(BaseModel):
    """
    Complete theme specification - atomic unit in v7 architecture.

    Each theme is self-contained with all visual properties, effects,
    and state overrides. No composition from primitives required.

    This is the core data structure that replaces the v1/v2 primitive system.

    Attributes:
        id: Theme identifier (chrome, neon, codex, etc.)
        tier: Visual/technical tier classification
        series: Design series grouping
        description: Human-readable theme description
        compatibleMotions: List of allowed motion types
        structure: Structural paradigm hint
        intent: XAI - Why this theme exists
        approach: XAI - Key design decisions
        tradeoffs: XAI - What was NOT done and why
        label: Label section visual config
        value: Value section visual config
        border: Optional border configuration
        effects: Ordered array of effect IDs to apply
        shadow: Optional drop shadow config
        glyph: Glyph/indicator configuration
        states: Complete state overrides for all 4 states
        sweep: Optional sweep highlight config
        specular: Optional specular highlight config
        glow: Optional glow config
        signal: Optional signal bar config (brutalist)
        accent: Optional accent config (obsidian)
        rim: Optional rim orbit config (clarity)
        filters: Optional filter parameters (clarity liquid)
        latin: Optional Latin motto (scholarly themes)
    """

    model_config = ConfigDict(extra="allow")

    # Core identification
    id: str = Field(description="Theme identifier (e.g., 'chrome', 'codex')")
    tier: Literal[
        "minimal", "flagship", "premium", "industrial", "brutalist", "cosmology", "scholarly"
    ] = Field(description="Visual/technical tier classification")
    series: str = Field(description="Design series (e.g., 'core', 'five-scholars')")
    description: str = Field(description="Human-readable theme description")
    compatibleMotions: list[str] = Field(description="Allowed motion types for this theme")
    structure: str = Field(description="Structural paradigm (flat, chrome-shield, glass, etc.)")

    # XAI reasoning (Living Artifact Protocol)
    intent: str = Field(description="Why this theme exists - design intent")
    approach: str = Field(description="Key design decisions - how it works")
    tradeoffs: str = Field(description="What was NOT done and why - deliberation proof")

    # Visual specification
    label: LabelConfig = Field(description="Label section visual configuration")
    value: ValueConfig = Field(description="Value section visual configuration")
    border: BorderConfig | None = Field(None, description="Optional border/stroke configuration")
    effects: list[str] = Field(
        default_factory=list, description="Ordered array of effect IDs to apply"
    )
    shadow: ShadowConfig | None = Field(None, description="Optional drop shadow configuration")
    glyph: GlyphConfig = Field(description="Glyph/indicator configuration")

    # State overrides (complete specifications for each state)
    states: dict[Literal["neutral", "passing", "warning", "failing"], StateOverride] = Field(
        description="Complete state-specific visual overrides"
    )

    # Optional theme-specific properties
    sweep: dict[str, Any] | None = Field(
        None, description="Sweep highlight configuration (if theme uses sweep effect)"
    )
    specular: dict[str, Any] | None = Field(
        None, description="Specular highlight configuration (chrome themes)"
    )
    glow: dict[str, Any] | None = Field(
        None, description="Glow configuration (neon/glass themes)"
    )
    signal: dict[str, Any] | None = Field(
        None, description="Signal bar configuration (brutalist themes)"
    )
    accent: dict[str, Any] | None = Field(
        None, description="Accent configuration (obsidian themes)"
    )
    rim: dict[str, Any] | None = Field(
        None, description="Rim orbit configuration (clarity theme)"
    )
    filters: dict[str, Any] | None = Field(
        None, description="SVG filter parameters (clarity liquid filter)"
    )

    # Scholarly theme properties
    latin: str | None = Field(None, description="Latin motto (scholarly themes only)")


class EffectDefinition(BaseModel):
    """
    Effect definition from ontology.

    Attributes:
        type: Effect type (filter, gradient, animation)
        id: Template ID with placeholders
        template: Optional SVG template string (for filters)
        direction: Optional gradient direction
        stops: Optional gradient stops
        keyframes: Optional CSS keyframes
        css: Optional CSS animation rules
    """

    model_config = ConfigDict(extra="allow")

    type: Literal["filter", "gradient", "animation"] = Field(description="Effect type")
    id: str | None = Field(None, description="Effect ID template with {uid} placeholders")
    template: str | None = Field(None, description="SVG template string (for filter effects)")
    direction: str | None = Field(None, description="Gradient direction (for gradient effects)")
    stops: list[dict[str, Any]] | None = Field(
        None, description="Gradient stops (for gradient effects)"
    )
    keyframes: str | None = Field(
        None, description="CSS @keyframes definition (for animation effects)"
    )
    css: str | None = Field(None, description="CSS animation rules (for animation effects)")
    target: str | None = Field(None, description="CSS selector target (for animation effects)")
    willChange: str | None = Field(None, description="will-change hint (for animation effects)")


class MotionDefinition(BaseModel):
    """
    Motion definition from ontology.

    Attributes:
        effects: List of effect IDs to apply
        duration: Optional animation duration
        keyframes: Optional CSS keyframes
        css: Optional CSS rules
        target: Optional CSS selector target
    """

    model_config = ConfigDict(extra="allow")

    effects: list[str] = Field(
        default_factory=list, description="Effect IDs to apply for this motion"
    )
    duration: str | None = Field(None, description="Animation duration (e.g., '5s')")
    keyframes: str | None = Field(None, description="CSS @keyframes definition")
    css: str | None = Field(None, description="CSS animation rules")
    target: str | None = Field(None, description="CSS selector target")
    description: str | None = Field(None, description="Human-readable description")


class GlyphDefinition(BaseModel):
    """
    Glyph definition from ontology.

    Attributes:
        svg: SVG template string with placeholders
        semantic: Semantic meaning of the glyph
        animation: Optional animation reference
    """

    model_config = ConfigDict(extra="allow")

    svg: str | None = Field(
        None, description="SVG template with {cx}, {cy}, {r}, {color} placeholders"
    )
    semantic: str = Field(description="Semantic meaning (e.g., 'active/online/live')")
    animation: str | None = Field(
        None, description="Animation effect reference (e.g., 'pulseDot')"
    )
    note: str | None = Field(None, description="Additional notes")
