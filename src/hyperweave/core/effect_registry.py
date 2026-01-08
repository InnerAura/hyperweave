"""
HyperWeave Effect Registry - Effect Rendering Engine for v7.

Manages effect definitions and template interpolation for SVG generation.
Renders filters, gradients, and animations from effectDefinitions ontology.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hyperweave.core.ontology import OntologyLoader


class EffectRegistry:
    """
    Effect rendering engine for v7 architecture.

    Manages effect definitions and template interpolation.
    Renders three types of effects:
    - Filter effects (dropShadow, glowFilter, liquidFilter)
    - Gradient effects (specularHighlight, sweepHighlight)
    - Animation effects (pulseDot, rimOrbit, hueRotate)

    Usage:
        >>> from hyperweave.core.ontology import OntologyLoader
        >>> ontology = OntologyLoader()
        >>> registry = EffectRegistry(ontology)
        >>> theme = ontology.get_theme("chrome")
        >>> effect_svg = registry.render_effect("dropShadow", ontology.get_effect_definition("dropShadow"), theme, "uid123")
    """

    def __init__(self, ontology: OntologyLoader) -> None:
        """
        Initialize effect registry with ontology.

        Args:
            ontology: OntologyLoader instance
        """
        self.ontology = ontology
        self.effect_definitions = ontology.get_all_effect_definitions()

    def render_effect(
        self, effect_id: str, effect_def: dict[str, Any], theme: dict[str, Any], uid: str
    ) -> list[str]:
        """
        Render effect to SVG elements.

        Args:
            effect_id: Effect identifier (e.g., "dropShadow")
            effect_def: Effect definition from ontology
            theme: Current theme configuration
            uid: Unique ID for this artifact

        Returns:
            List of SVG string fragments (lines)

        Example:
            >>> effect_lines = registry.render_effect(
            ...     "dropShadow",
            ...     ontology.get_effect_definition("dropShadow"),
            ...     theme,
            ...     "hw123"
            ... )
            >>> print("\\n".join(effect_lines))
            <filter id="shadow-hw123">...</filter>
        """
        effect_type = effect_def.get("type")

        if effect_type == "filter":
            return self._render_filter_effect(effect_id, effect_def, theme, uid)
        elif effect_type == "gradient":
            return self._render_gradient_effect(effect_id, effect_def, theme, uid)
        elif effect_type == "animation":
            return self._render_animation_effect(effect_id, effect_def, theme, uid)
        else:
            # Unknown effect type - skip silently
            return []

    def _render_filter_effect(
        self, effect_id: str, effect_def: dict[str, Any], theme: dict[str, Any], uid: str
    ) -> list[str]:
        """
        Render filter effect (dropShadow, glowFilter, liquidFilter).

        Args:
            effect_id: Effect identifier
            effect_def: Effect definition with template string
            theme: Theme configuration for parameter extraction
            uid: Unique artifact ID

        Returns:
            List of SVG filter element strings
        """
        template = effect_def.get("template", "")

        # Extract parameters from theme based on effect type
        params = self._extract_filter_params(effect_id, theme)
        params["uid"] = uid

        # Template interpolation
        try:
            rendered = template.format(**params)
            return [rendered]
        except KeyError:
            # Missing parameter - return empty
            return []

    def _extract_filter_params(self, effect_id: str, theme: dict[str, Any]) -> dict[str, Any]:
        """
        Extract filter parameters from theme specification.

        Args:
            effect_id: Filter effect identifier
            theme: Theme configuration

        Returns:
            Dictionary of template parameters
        """
        if effect_id == "dropShadow":
            shadow = theme.get("shadow")
            if shadow:
                return {
                    "shadowColor": shadow.get("color", "rgba(0,0,0,0.3)"),
                    "shadowBlur": shadow.get("blur", 3),
                    "shadowY": shadow.get("y", 2),
                    "shadowX": shadow.get("x", 0),
                }
            return {"shadowColor": "rgba(0,0,0,0.3)", "shadowBlur": 3, "shadowY": 2, "shadowX": 0}

        elif effect_id == "glowFilter":
            glow = theme.get("glow")
            if glow:
                return {
                    "glowColor": glow.get("color", "rgba(0,255,255,0.3)"),
                    "glowRadius": glow.get("radius", 2),
                }
            return {"glowColor": "rgba(0,255,255,0.3)", "glowRadius": 2}

        elif effect_id == "liquidFilter":
            # Clarity theme specific
            filters = theme.get("filters", {})
            if filters:
                turbulence = filters.get("turbulence", {})
                displacement = filters.get("displacement", {})
                specular = filters.get("specular", {})

                return {
                    "baseFrequency": turbulence.get("baseFrequency", 0.024),
                    "numOctaves": turbulence.get("numOctaves", 1),
                    "displacementScale": displacement.get("scale", 1.5),
                    "surfaceScale": specular.get("surfaceScale", 2),
                    "specularConstant": specular.get("specularConstant", 1),
                    "specularExponent": specular.get("specularExponent", 28),
                }

            return {
                "baseFrequency": 0.024,
                "numOctaves": 1,
                "displacementScale": 1.5,
                "surfaceScale": 2,
                "specularConstant": 1,
                "specularExponent": 28,
            }

        return {}

    def _render_gradient_effect(
        self, effect_id: str, effect_def: dict[str, Any], theme: dict[str, Any], uid: str
    ) -> list[str]:
        """
        Render gradient effect (specularHighlight, sweepHighlight).

        Args:
            effect_id: Gradient effect identifier
            effect_def: Effect definition with gradient configuration
            theme: Theme configuration
            uid: Unique artifact ID

        Returns:
            List of SVG gradient element strings
        """
        gradient_id = effect_def.get("id", f"{effect_id}-{uid}").format(uid=uid)
        direction = effect_def.get("direction", "vertical")
        stops = effect_def.get("stops", [])

        # Extract params from theme
        params = self._extract_gradient_params(effect_id, theme)
        params["uid"] = uid

        # Build gradient
        direction_map = {
            "vertical": ("0%", "0%", "0%", "100%"),
            "horizontal": ("0%", "0%", "100%", "0%"),
        }
        x1, y1, x2, y2 = direction_map.get(direction, ("0%", "0%", "0%", "100%"))

        lines = []
        lines.append(f'<linearGradient id="{gradient_id}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">')

        for stop in stops:
            offset = stop["offset"]

            # Interpolate color with params
            color = stop["color"]
            if isinstance(color, str) and "{" in color:
                color = color.format(**params)

            # Interpolate opacity with params
            opacity = stop.get("opacity", "1")
            if isinstance(opacity, str) and "{" in opacity:
                opacity = opacity.format(**params)

            # Build stop element
            if opacity != "1" and opacity != 1:
                lines.append(
                    f'  <stop offset="{offset}" stop-color="{color}" stop-opacity="{opacity}"/>'
                )
            else:
                lines.append(f'  <stop offset="{offset}" stop-color="{color}"/>')

        lines.append("</linearGradient>")

        return lines

    def _extract_gradient_params(self, effect_id: str, theme: dict[str, Any]) -> dict[str, Any]:
        """
        Extract gradient parameters from theme.

        Args:
            effect_id: Gradient effect identifier
            theme: Theme configuration

        Returns:
            Dictionary of template parameters
        """
        if effect_id == "specularHighlight":
            specular = theme.get("specular")
            if specular:
                return {
                    "specHighColor": specular.get("highColor", "#ffffff"),
                    "specHighOpacity": specular.get("highOpacity", "0.7"),
                    "specMidColor": specular.get("midColor", "#ffffff"),
                    "specMidOpacity": specular.get("midOpacity", "0.2"),
                    "specLowColor": specular.get("lowColor", "#ffffff"),
                }
            return {
                "specHighColor": "#ffffff",
                "specHighOpacity": "0.7",
                "specMidColor": "#ffffff",
                "specMidOpacity": "0.2",
                "specLowColor": "#ffffff",
            }

        elif effect_id == "sweepHighlight":
            sweep = theme.get("sweep")
            if sweep:
                return {
                    "sweepColor": sweep.get("color", "#ffffff"),
                    "sweepOpacity": sweep.get("opacity", "0.5"),
                    "duration": sweep.get("duration", "5s"),
                }
            return {"sweepColor": "#ffffff", "sweepOpacity": "0.5", "duration": "5s"}

        return {}

    def _render_animation_effect(
        self, effect_id: str, effect_def: dict[str, Any], theme: dict[str, Any], uid: str
    ) -> list[str]:
        """
        Render animation effect (pulseDot, rimOrbit, hueRotate).

        Animations are CSS-based, not SVG elements.
        Returns CSS keyframes and rules.

        Args:
            effect_id: Animation effect identifier
            effect_def: Effect definition with keyframes and CSS
            theme: Theme configuration
            uid: Unique artifact ID

        Returns:
            List of CSS strings (keyframes and animation rules)
        """
        keyframes = effect_def.get("keyframes", "")
        css = effect_def.get("css", "")

        # Extract animation parameters
        params = {"uid": uid}

        # Get duration from theme
        if effect_id == "pulseDot":
            glyph = theme.get("glyph", {})
            params["duration"] = glyph.get("duration", "2.618s")
        elif effect_id == "rimOrbit":
            rim = theme.get("rim", {})
            params["duration"] = rim.get("duration", "2.4s")
            params["dashArray"] = rim.get("dashArray", "12 88")
        elif effect_id == "hueRotate":
            params["duration"] = "8s"  # Fixed for spectrum effect

        # Interpolate templates using replace (to avoid conflicts with CSS braces)
        keyframes_rendered = keyframes
        css_rendered = css

        for key, value in params.items():
            keyframes_rendered = keyframes_rendered.replace(f"{{{key}}}", str(value))
            css_rendered = css_rendered.replace(f"{{{key}}}", str(value))

        result = []
        if keyframes_rendered:
            result.append(keyframes_rendered)
        if css_rendered:
            result.append(css_rendered)

        return result

    def render_effects_for_theme(self, theme: dict[str, Any], uid: str) -> dict[str, list[str]]:
        """
        Render all effects for a theme.

        Args:
            theme: Theme configuration
            uid: Unique artifact ID

        Returns:
            Dictionary with effect categories:
            - filters: List of filter SVG elements
            - gradients: List of gradient SVG elements
            - animations: List of CSS animation strings

        Example:
            >>> effects = registry.render_effects_for_theme(theme, "hw123")
            >>> defs_section = "\\n".join(effects["filters"] + effects["gradients"])
            >>> style_section = "\\n".join(effects["animations"])
        """
        effects_list = theme.get("effects", [])

        filters = []
        gradients = []
        animations = []

        for effect_id in effects_list:
            # Get effect definition from ontology
            try:
                effect_def = self.ontology.get_effect_definition(effect_id)
            except KeyError:
                # Effect not found - skip
                continue

            # Render effect
            rendered = self.render_effect(effect_id, effect_def, theme, uid)

            # Categorize by type
            effect_type = effect_def.get("type")
            if effect_type == "filter":
                filters.extend(rendered)
            elif effect_type == "gradient":
                gradients.extend(rendered)
            elif effect_type == "animation":
                animations.extend(rendered)

        return {"filters": filters, "gradients": gradients, "animations": animations}

    def get_effect_type(self, effect_id: str) -> str:
        """
        Get effect type for an effect ID.

        Args:
            effect_id: Effect identifier

        Returns:
            Effect type ("filter", "gradient", "animation", or "unknown")
        """
        try:
            effect_def = self.ontology.get_effect_definition(effect_id)
            return str(effect_def.get("type", "unknown"))
        except KeyError:
            return "unknown"
