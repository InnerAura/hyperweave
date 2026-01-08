"""
HyperWeave Badge Generator - Theme-Centric Architecture (v7).

Generates Living SVG Artifacts using theme-driven approach.
Replaces primitive-based composition with atomic theme units.
"""

import hashlib
import html
from datetime import datetime
from typing import Any

from hyperweave.core.effect_registry import EffectRegistry
from hyperweave.core.ontology import OntologyLoader
from hyperweave.models.badge import (
    BadgeContent,
    BadgeRequest,
    BadgeResponse,
    HyperWeaveMetadata,
    ThemeDNA,
)


class BadgeGenerator:
    """
    Theme-driven SVG badge generator for Living Artifact Protocol v7.

    Architecture:
        Badge = Theme(state) × Content × Motion_Override?

    Usage:
        >>> ontology = OntologyLoader()
        >>> generator = BadgeGenerator(ontology)
        >>> request = BadgeRequest(
        ...     theme="chrome",
        ...     content=BadgeContent(label="version", value="1.0.0", state="passing"),
        ...     motion="sweep"
        ... )
        >>> response = generator.generate(request)
    """

    def __init__(self, ontology: OntologyLoader) -> None:
        """
        Initialize generator with ontology and effect registry.

        Args:
            ontology: OntologyLoader instance for theme access
        """
        self.ontology = ontology
        self.effect_registry = EffectRegistry(ontology)

    def generate(self, request: BadgeRequest) -> BadgeResponse:
        """
        Generate SVG badge from theme-driven request.

        Flow:
            1. Load theme from ontology
            2. Validate motion compatibility
            3. Apply state overrides
            4. Render effects
            5. Build SVG
            6. Build metadata

        Args:
            request: BadgeRequest with theme ID, content, motion

        Returns:
            BadgeResponse with complete SVG and metadata

        Raises:
            KeyError: If theme not found or motion incompatible
        """
        # 1. Load theme from ontology
        theme = self.ontology.get_theme(request.theme)

        # 2. Validate motion compatibility
        motion = self._validate_motion(theme, request.motion)

        # 3. Apply state overrides (modify theme for this state)
        theme_with_state = self._apply_state_overrides(theme, request.content.state)

        # 4. Get layout configuration
        layout = self.ontology.get_layout()
        size_config = layout["dimensions"]
        width = size_config["width"]
        height = size_config["height"]

        # Adjust width for icon if present (14px icon + 5px gap = 19px)
        if request.content.icon:
            width += 19

        # 5. Generate unique ID for this artifact
        uid = self._generate_uid(request)

        # 6. Build SVG
        svg = self._generate_svg(
            theme=theme_with_state,
            content=request.content,
            motion=motion,
            width=width,
            height=height,
            uid=uid,
            artifact_tier=request.artifact_tier,
            reasoning=request.reasoning,
        )

        # 7. Build Theme DNA
        theme_dna = ThemeDNA(
            theme=request.theme,
            tier=theme["tier"],
            series=theme["series"],
            motion=motion,
            ontology_version="7.0.0",
        )

        # 8. Build metadata
        metadata = HyperWeaveMetadata(
            series=theme["series"],
            size=f"{width}x{height}",
            theme_dna=theme_dna,
        )

        if request.reasoning:
            metadata.intent = request.reasoning.get("intent")
            metadata.approach = request.reasoning.get("approach")
            metadata.tradeoffs = request.reasoning.get("tradeoffs")

        return BadgeResponse(
            svg=svg,
            metadata=metadata,
            theme_dna=theme_dna,
        )

    def _validate_motion(self, theme: dict[str, Any], motion: str | None) -> str:
        """
        Validate motion compatibility with theme.

        Args:
            theme: Theme configuration dict
            motion: Requested motion or None for default

        Returns:
            Validated motion ID

        Raises:
            ValueError: If motion incompatible with theme
        """
        compatible_motions = theme.get("compatibleMotions", ["static"])

        if motion is None:
            # Use first compatible motion as default
            return compatible_motions[0]

        if motion not in compatible_motions:
            raise ValueError(
                f"Motion '{motion}' not compatible with theme '{theme['id']}'. "
                f"Compatible motions: {', '.join(compatible_motions)}"
            )

        return motion

    def _apply_state_overrides(self, theme: dict[str, Any], state: str | None) -> dict[str, Any]:
        """
        Apply state-specific overrides to theme.

        Creates a modified copy of theme with state colors applied.

        Args:
            theme: Base theme configuration
            state: State identifier (passing, warning, failing, neutral) or None

        Returns:
            Theme dict with state overrides applied
        """
        # Create a copy to avoid mutating original
        import copy

        theme_copy = copy.deepcopy(theme)

        if not state:
            return theme_copy

        # Get state overrides from theme
        states = theme.get("states", {})
        state_override = states.get(state)

        if not state_override:
            return theme_copy

        # Apply value overrides
        value_override = state_override.get("value", {})
        if value_override.get("useDefault") is not True:
            # Replace value section with state-specific config
            if "gradient" in value_override:
                theme_copy["value"]["gradient"] = value_override["gradient"]
            if "fill" in value_override:
                theme_copy["value"]["fill"] = value_override["fill"]
            if "text" in value_override:
                theme_copy["value"]["text"] = value_override["text"]

        # Apply glyph color override
        glyph_color = state_override.get("glyph")
        if glyph_color:
            theme_copy["glyphColor"] = glyph_color

        # Apply theme-specific overrides (rim, signal, accent)
        if "rim" in state_override:
            theme_copy["rim"]["colors"] = state_override["rim"]

        if "signal" in state_override:
            theme_copy["signal"]["color"] = state_override["signal"]

        if "accent" in state_override:
            theme_copy["accent"] = state_override["accent"]

        return theme_copy

    def _generate_uid(self, request: BadgeRequest) -> str:
        """
        Generate unique ID for this artifact.

        Args:
            request: BadgeRequest

        Returns:
            Short unique ID (8 chars)
        """
        data = f"{request.theme}{request.content.label}{request.content.value}{datetime.utcnow().isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()[:8]

    def _generate_svg(
        self,
        theme: dict[str, Any],
        content: BadgeContent,
        motion: str,
        width: int,
        height: int,
        uid: str,
        artifact_tier: str,
        reasoning: dict[str, Any] | None,
    ) -> str:
        """
        Generate complete SVG following svgTemplate structure.

        Args:
            theme: Theme configuration with state overrides applied
            content: Badge content (label, value, state)
            motion: Validated motion ID
            width: SVG width
            height: SVG height
            uid: Unique artifact ID
            artifact_tier: NAKED, BASIC, or FULL
            reasoning: Optional XAI reasoning

        Returns:
            Complete SVG string
        """
        svg_parts = []

        # Get layout configuration (needed throughout)
        layout = self.ontology.get_layout()

        # 1. SVG Root with namespaces
        svg_parts.append(self._build_svg_root(width, height, theme, content))

        # 2. Title and Description (accessibility)
        svg_parts.append(f'  <title id="hw-title">{content.label}: {content.value}</title>')
        svg_parts.append(
            f'  <desc id="hw-desc">HyperWeave badge showing {content.label} with value {content.value}</desc>'
        )

        # 3. Metadata (if BASIC or FULL tier)
        if artifact_tier in ["BASIC", "FULL"]:
            svg_parts.extend(
                self._generate_metadata(
                    theme, content, reasoning, width, height, artifact_tier == "FULL"
                )
            )

        # 4. Defs section (gradients, filters, clip-paths)
        svg_parts.append("  <defs>")

        # Render effects for this theme
        effects = self.effect_registry.render_effects_for_theme(theme, uid)

        # Add clipPath for unified badge shape
        svg_parts.extend(self._build_clip_path(uid, width, height, layout["corners"]["radius"]))

        # Add gradients from theme configuration
        svg_parts.extend(self._build_gradients(theme, uid))

        # Add effects (filters and gradients from effect registry)
        svg_parts.extend(["    " + line for line in effects["filters"]])
        svg_parts.extend(["    " + line for line in effects["gradients"]])

        svg_parts.append("  </defs>")

        # 5. Style block with CSS
        svg_parts.append("  <style>")

        # Typography base
        typography = layout["typography"]
        svg_parts.append(
            f"    text {{ font-family: {typography['fontFamily']}; font-weight: {typography['fontWeight']}; font-size: {typography['fontSize']}px; }}"
        )

        # Typography hierarchy (Living Artifact Protocol v2)
        svg_parts.append(
            "    .hw-mono { font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace; }"
        )
        svg_parts.append(
            "    .hw-sans { font-family: 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif; }"
        )
        svg_parts.append("    .hw-title { font-size: 13px; font-weight: 700; }")
        svg_parts.append("    .hw-value { font-size: 11px; font-weight: 600; }")
        svg_parts.append(
            "    .hw-label { font-size: 11px; font-weight: 400; text-transform: uppercase; letter-spacing: 0.5px; }"
        )

        # Motion animations from effect registry
        svg_parts.extend(["    " + line for line in effects["animations"]])

        # Reduced motion support
        accessibility = self.ontology.get_accessibility_config()
        if accessibility.get("reducedMotion", {}).get("respectPreference", True):
            svg_parts.append("    @media (prefers-reduced-motion: reduce) {")
            svg_parts.append("      * { animation: none !important; }")
            svg_parts.append("    }")

        svg_parts.append("  </style>")

        # 6. Badge geometry (background, text, glyph)
        svg_parts.extend(self._build_badge_geometry(theme, content, width, height, uid))

        svg_parts.append("</svg>")

        return "\n".join(svg_parts)

    def _build_protocol_v2_attributes(
        self, theme: dict[str, Any], content: BadgeContent, chromatic_system: str = "neutral-mono"
    ) -> str:
        """
        Build Living Artifact Protocol v2.0 data-hw-* attributes.

        Implements Layer 3 (State) + Layer 4 (Governance) of protocol architecture.
        Zero coupling - pure function for testability.

        Args:
            theme: Theme configuration dict
            content: Badge content with optional state
            chromatic_system: Chromatic color system ID (default: neutral-mono)

        Returns:
            String of space-separated data-hw-* attributes

        Example:
            >>> attrs = self._build_protocol_v2_attributes(theme, content, "carbon-crimson")
            >>> 'data-hw-version="2.0.0" data-hw-theme="chrome" data-hw-chromatic="carbon-crimson" data-hw-status="passing"'
        """
        # Protocol version (always 2.0.0)
        attrs = ['data-hw-version="2.0.0"']

        # Theme identifier
        theme_id = theme.get("id", "unknown")
        attrs.append(f'data-hw-theme="{theme_id}"')

        # Chromatic system (theme-agnostic color management)
        attrs.append(f'data-hw-chromatic="{chromatic_system}"')

        # Status (badge state for machine-readable state management)
        if content.state:
            # Extract enum value if it's a BadgeState enum, otherwise use as-is
            status_value = content.state.value if hasattr(content.state, "value") else content.state
            attrs.append(f'data-hw-status="{status_value}"')

        return " ".join(attrs)

    def _build_svg_root(
        self, width: int, height: int, theme: dict[str, Any], content: BadgeContent
    ) -> str:
        """
        Build SVG root element with namespaces and Living Artifact Protocol v2 attributes.

        Args:
            width: SVG width
            height: SVG height
            theme: Theme configuration
            content: Badge content

        Returns:
            SVG opening tag string with protocol v2 compliance

        Note:
            Includes data-hw-* attributes for machine-readable state management.
            Maintains backward compatibility with legacy data-state attribute.
        """
        # Legacy data-state attribute (backward compatibility)
        state_attr = f'data-state="{content.state}"' if content.state else ""

        # Living Artifact Protocol v2.0 attributes
        protocol_attrs = self._build_protocol_v2_attributes(theme, content)

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:hw="https://hyperweave.dev/hw/v1.0" '
            f'width="{width}" '
            f'height="{height}" '
            f'viewBox="0 0 {width} {height}" '
            f'role="img" '
            f'aria-labelledby="hw-title hw-desc" '
            f"{protocol_attrs} "
            f"{state_attr}>"
        )

    def _generate_metadata(
        self,
        theme: dict[str, Any],
        content: BadgeContent,
        reasoning: dict[str, Any] | None,
        width: int,
        height: int,
        include_reasoning: bool,
        chromatic_system: str = "neutral-mono",
    ) -> list[str]:
        """
        Build hw:artifact metadata following metadataTemplate with RDF/Dublin Core.

        Args:
            theme: Theme configuration
            content: Badge content
            reasoning: Optional XAI reasoning
            width: SVG width
            height: SVG height
            include_reasoning: Whether to include hw:reasoning and RDF/DC (FULL tier only)
            chromatic_system: Chromatic color system ID (default: neutral-mono)

        Returns:
            List of metadata XML strings
        """
        meta_parts = []
        meta_parts.append("  <metadata>")

        # RDF/Dublin Core metadata (FULL tier only)
        if include_reasoning:
            # Create badge title from label and value
            badge_title = f"{content.label}: {content.value}"
            iso_timestamp = datetime.utcnow().isoformat() + "Z"
            theme_id = theme.get("id", "unknown")

            # XML escape all user-provided content
            escaped_title = html.escape(badge_title, quote=True)
            escaped_theme_id = html.escape(theme_id, quote=True)
            escaped_chromatic = html.escape(chromatic_system, quote=True)

            meta_parts.append(
                '    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
            )
            meta_parts.append('             xmlns:dc="http://purl.org/dc/elements/1.1/"')
            meta_parts.append('             xmlns:hw="https://hyperweave.dev/hw/v1.0">')
            meta_parts.append("      <rdf:Description>")
            meta_parts.append(f"        <dc:title>{escaped_title}</dc:title>")
            meta_parts.append("        <dc:creator>HyperWeave v7.0.0</dc:creator>")
            meta_parts.append(f"        <dc:date>{iso_timestamp}</dc:date>")
            meta_parts.append("        <hw:artifact-class>badge</hw:artifact-class>")
            meta_parts.append(f"        <hw:theme>{escaped_theme_id}</hw:theme>")
            meta_parts.append(
                f"        <hw:chromatic-system>{escaped_chromatic}</hw:chromatic-system>"
            )

            # Include reasoning in RDF/DC if available
            if reasoning:
                escaped_intent = html.escape(reasoning.get("intent", ""), quote=True)
                escaped_approach = html.escape(reasoning.get("approach", ""), quote=True)
                escaped_tradeoffs = html.escape(reasoning.get("tradeoffs", ""), quote=True)

                meta_parts.append("        <hw:reasoning>")
                meta_parts.append(f"          <hw:intent>{escaped_intent}</hw:intent>")
                meta_parts.append(f"          <hw:approach>{escaped_approach}</hw:approach>")
                meta_parts.append(f"          <hw:tradeoffs>{escaped_tradeoffs}</hw:tradeoffs>")
                meta_parts.append("        </hw:reasoning>")

            meta_parts.append("      </rdf:Description>")
            meta_parts.append("    </rdf:RDF>")

        # HyperWeave artifact metadata
        meta_parts.append('    <hw:artifact type="badge" version="1.0.0">')

        # Provenance
        meta_parts.append("      <hw:provenance>")
        meta_parts.append("        <hw:generator>Claude Sonnet 4.5 (InnerAura Labs)</hw:generator>")
        meta_parts.append(f"        <hw:created>{datetime.utcnow().isoformat()}Z</hw:created>")
        meta_parts.append("        <hw:human-directed>true</hw:human-directed>")
        meta_parts.append("      </hw:provenance>")

        # Reasoning (FULL tier only)
        if include_reasoning and reasoning:
            # XML escape reasoning fields for hw:artifact block
            escaped_intent = html.escape(reasoning.get("intent", ""), quote=True)
            escaped_approach = html.escape(reasoning.get("approach", ""), quote=True)
            escaped_tradeoffs = html.escape(reasoning.get("tradeoffs", ""), quote=True)

            meta_parts.append("      <hw:reasoning>")
            meta_parts.append(f"        <hw:intent>{escaped_intent}</hw:intent>")
            meta_parts.append(f"        <hw:approach>{escaped_approach}</hw:approach>")
            meta_parts.append(f"        <hw:tradeoffs>{escaped_tradeoffs}</hw:tradeoffs>")
            meta_parts.append("      </hw:reasoning>")

        # Spec
        meta_parts.append(
            f'      <hw:spec size="{width}x{height}" performance="composite-only" theme="adaptive" a11y="WCAG-AA"/>'
        )

        meta_parts.append("    </hw:artifact>")
        meta_parts.append("  </metadata>")

        return meta_parts

    def _build_gradients(self, theme: dict[str, Any], uid: str) -> list[str]:
        """
        Build label and value gradients from theme configuration.

        Args:
            theme: Theme configuration
            uid: Unique artifact ID

        Returns:
            List of gradient SVG strings
        """
        gradients = []

        # Label gradient
        label_config = theme.get("label", {})
        if "gradient" in label_config and label_config["gradient"]:
            gradient = label_config["gradient"]
            gradients.extend(self._build_gradient_def("grad-label", gradient))

        # Value gradient
        value_config = theme.get("value", {})
        if "gradient" in value_config and value_config["gradient"]:
            gradient = value_config["gradient"]
            gradients.extend(self._build_gradient_def("grad-value", gradient))

        return gradients

    def _build_gradient_def(
        self, gradient_id: str, gradient_config: dict[str, Any] | list[str]
    ) -> list[str]:
        """
        Build SVG gradient definition from gradient config.

        Args:
            gradient_id: ID for this gradient
            gradient_config: Gradient configuration - either:
                - Dict with "direction" and "stops" keys (full config)
                - List of color strings (shorthand for vertical gradient)

        Returns:
            List of SVG gradient strings
        """
        parts = []

        # Handle shorthand format (just a list of colors)
        if isinstance(gradient_config, list):
            direction = "vertical"
            stops = gradient_config
        else:
            # Full config format
            direction = gradient_config.get("direction", "vertical")
            stops = gradient_config.get("stops", [])

        # Direction mappings
        direction_map = {
            "vertical": ("0%", "0%", "0%", "100%"),
            "horizontal": ("0%", "0%", "100%", "0%"),
            "diagonal": ("0%", "0%", "100%", "100%"),
        }

        x1, y1, x2, y2 = direction_map.get(direction, ("0%", "0%", "0%", "100%"))

        parts.append(
            f'    <linearGradient id="{gradient_id}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
        )

        for idx, stop in enumerate(stops):
            if isinstance(stop, str):
                # Stop is just a color string - calculate offset evenly
                offset = f"{(idx / (len(stops) - 1) * 100):.1f}%" if len(stops) > 1 else "0%"
                color = stop
                opacity = None
            else:
                # Stop is a dict with offset/color/opacity
                offset = stop.get("offset", "0%")
                color = stop.get("color", "#000000")
                opacity = stop.get("opacity")

            if opacity is not None:
                parts.append(
                    f'      <stop offset="{offset}" stop-color="{color}" stop-opacity="{opacity}"/>'
                )
            else:
                parts.append(f'      <stop offset="{offset}" stop-color="{color}"/>')

        parts.append("    </linearGradient>")

        return parts

    def _build_clip_path(self, uid: str, width: int, height: int, radius: int) -> list[str]:
        """
        Build clipPath for unified badge shape with rounded corners.

        This creates a single rounded rectangle that serves as a clipping mask,
        allowing inner rectangles to have square corners while the overall badge
        maintains rounded corners. This eliminates the seam gap issue.

        Args:
            uid: Unique artifact ID
            width: Badge width
            height: Badge height
            radius: Corner radius

        Returns:
            List of clipPath SVG strings
        """
        return [
            f'    <clipPath id="badge-clip-{uid}">',
            f'      <rect width="{width}" height="{height}" rx="{radius}" ry="{radius}"/>',
            "    </clipPath>",
        ]

    def _build_badge_geometry(
        self,
        theme: dict[str, Any],
        content: BadgeContent,
        width: int,
        height: int,
        uid: str,
    ) -> list[str]:
        """
        Build badge visual geometry (backgrounds, text, glyph).

        Args:
            theme: Theme configuration
            content: Badge content
            width: SVG width
            height: SVG height
            uid: Unique artifact ID

        Returns:
            List of SVG geometry strings
        """
        parts = []

        # Get layout configuration
        layout = self.ontology.get_layout()
        sections = layout["sections"]
        corners = layout["corners"]
        typography = layout["typography"]

        # Calculate section positions (icon-aware)
        # Add space for icon if present: 14px icon + 5px gap = 19px
        icon_space = 19 if content.icon else 0
        label_width = sections["label"]["width"] + icon_space
        value_x = label_width

        # Border radius
        radius = corners["radius"]

        # Main group with clipPath for unified rounded shape
        parts.append(f'  <g class="badge" clip-path="url(#badge-clip-{uid})">')

        # Label background (square corners - clipping provides rounding)
        label_config = theme.get("label", {})
        label_fill = self._get_fill_value(label_config, "grad-label")
        parts.append(
            f'    <rect x="0" y="0" width="{label_width}" height="{height}" fill="{label_fill}"/>'
        )

        # Value background (square corners - clipping provides rounding)
        value_config = theme.get("value", {})
        value_fill = self._get_fill_value(value_config, "grad-value")
        value_width = width - label_width
        parts.append(
            f'    <rect x="{value_x}" y="0" width="{value_width}" height="{height}" '
            f'fill="{value_fill}"/>'
        )

        # Machined seam lines (dark + highlight pair for industrial aesthetic)
        parts.append(
            f'    <line x1="{value_x}" y1="0" x2="{value_x}" y2="{height}" '
            f'stroke="rgba(0,0,0,0.2)" stroke-width="1"/>'
        )
        parts.append(
            f'    <line x1="{value_x + 1}" y1="0" x2="{value_x + 1}" y2="{height}" '
            f'stroke="rgba(255,255,255,0.1)" stroke-width="1"/>'
        )

        # Render effect visual elements (overlays, highlights, accent bars)
        parts.extend(self._render_effect_visual_elements(theme, width, height, uid))

        # Border (if specified)
        border_config = theme.get("border")
        if border_config:
            border_width = border_config.get("width", 1)
            border_color = border_config.get("color", "#000000")
            parts.append(
                f'    <rect x="{border_width / 2}" y="{border_width / 2}" '
                f'width="{width - border_width}" height="{height - border_width}" '
                f'rx="{radius}" ry="{radius}" '
                f'fill="none" stroke="{border_color}" stroke-width="{border_width}"/>'
            )

        # Brand icon (if specified) - rendered on label side
        if content.icon:
            label_text_color = label_config.get("text", "#ffffff")
            icon_svg = self._generate_icon(content.icon, label_text_color)
            if icon_svg:
                parts.append(icon_svg)

        # Label text (adjust X position if icon is present)
        label_section = sections["label"]
        label_text_color = label_config.get("text", "#ffffff")
        # Shift label text right by full icon space when icon is present to avoid overlap
        label_text_x = label_section["textX"] + icon_space
        parts.append(
            f'    <text x="{label_text_x}" y="{label_section["textY"]}" '
            f'text-anchor="{typography.get("textAnchor", "middle")}" class="label hw-label hw-sans" fill="{label_text_color}">{content.label}</text>'
        )

        # Value text
        value_section = sections["value"]
        value_text_color = value_config.get("text", "#ffffff")
        parts.append(
            f'    <text x="{value_section["textX"]}" y="{value_section["textY"]}" '
            f'text-anchor="{typography.get("textAnchor", "middle")}" class="value hw-value hw-mono" fill="{value_text_color}">{content.value}</text>'
        )

        # Glyph (indicator) - positioned in top-right corner of badge
        glyph_config = theme.get("glyph", {})
        glyph_type = glyph_config.get("type", "none")

        if glyph_type != "none":
            # Dynamic glyph positioning based on actual badge width
            # Top-right corner: width - margin - (glyph_size / 2)
            glyph_size = layout["glyph"].get("r", 2.5) * 2  # diameter
            glyph_margin = 5
            glyph_layout_dynamic = {
                "cx": width - glyph_margin - (glyph_size / 2),
                "cy": glyph_margin + (glyph_size / 2),
                "r": layout["glyph"].get("r", 2.5),
            }
            glyph_svg = self._generate_glyph(
                glyph_type,
                theme.get("glyphColor", value_text_color),
                glyph_layout_dynamic,
                uid,
            )
            if glyph_svg:
                parts.append(glyph_svg)

        parts.append("  </g>")

        return parts

    def _get_fill_value(self, section_config: dict[str, Any], gradient_id: str) -> str:
        """
        Get fill value for section (gradient URL or solid color).

        Args:
            section_config: Label or value configuration
            gradient_id: Gradient ID to use if gradient exists

        Returns:
            Fill value string (url(#...) or color)
        """
        if "gradient" in section_config and section_config["gradient"]:
            return f"url(#{gradient_id})"

        if "fill" in section_config:
            return section_config["fill"]

        return "#6b7280"  # Default fallback

    def _render_effect_visual_elements(
        self, theme: dict[str, Any], width: int, height: int, uid: str
    ) -> list[str]:
        """
        Render visual elements for theme effects (overlays, highlights, accent bars).

        Effects like specularHighlight define gradients in <defs>, but we need to
        actually render the visual elements that USE those gradients.

        Args:
            theme: Theme configuration
            width: Badge width
            height: Badge height
            uid: Unique artifact ID

        Returns:
            List of SVG element strings for effect visual layers
        """
        parts = []
        effects = theme.get("effects", [])

        for effect_id in effects:
            # Specular highlight overlay (mirror reflection)
            if effect_id == "specularHighlight":
                parts.append(
                    f'    <rect x="0" y="0" width="{width}" height="{height}" '
                    f'fill="url(#spec-{uid})" pointer-events="none"/>'
                )

            # Sweep highlight overlay (animated light sweep)
            elif effect_id == "sweepHighlight":
                parts.append(
                    f'    <rect x="0" y="0" width="{width}" height="{height}" '
                    f'fill="url(#sweep-{uid})" pointer-events="none"/>'
                )

            # Edge highlights (razor lines top/bottom)
            elif effect_id == "edgeHighlights":
                # Top edge highlight
                parts.append(
                    f'    <line x1="0" y1="0.5" x2="{width}" y2="0.5" '
                    f'stroke="rgba(255,255,255,0.3)" stroke-width="1"/>'
                )
                # Bottom edge highlight
                parts.append(
                    f'    <line x1="0" y1="{height - 0.5}" x2="{width}" y2="{height - 0.5}" '
                    f'stroke="rgba(255,255,255,0.2)" stroke-width="1"/>'
                )

            # Accent divider (vertical neon line at seam)
            elif effect_id in ["accentBar", "accentDivider"]:
                # Get seam position from layout
                layout = self.ontology.get_layout()
                seam_x = layout["sections"]["label"]["width"]

                # Use accent color from theme (may be overridden by state)
                accent_color = theme.get("accent", "#ff006a")  # Default pink

                # Render vertical accent line at seam
                parts.append(
                    f'    <line x1="{seam_x}" y1="0" x2="{seam_x}" y2="{height}" '
                    f'stroke="{accent_color}" stroke-width="2" opacity="0.9" pointer-events="none"/>'
                )

        return parts

    def _generate_glyph(
        self, glyph_type: str, color: str, glyph_layout: dict[str, Any], uid: str
    ) -> str:
        """
        Generate glyph (indicator) SVG from ontology definition.

        Args:
            glyph_type: Glyph type (dot, check, cross, star, etc.)
            color: Glyph color
            glyph_layout: Glyph positioning from layout config
            uid: Unique artifact ID for class names

        Returns:
            Glyph SVG string or empty string if type is "none"
        """
        if glyph_type == "none":
            return ""

        try:
            glyph_def = self.ontology.get_glyph_definition(glyph_type)
        except KeyError:
            return ""  # Glyph not found, skip silently

        svg_template = glyph_def.get("svg")
        if not svg_template:
            return ""

        # Interpolate template with positioning
        cx = glyph_layout.get("cx", 130)
        cy = glyph_layout.get("cy", 10)
        r = glyph_layout.get("r", 3)

        return f"    {svg_template.format(cx=cx, cy=cy, r=r, color=color, uid=uid)}"

    def _generate_icon(
        self, icon_type: str, color: str, x: int = 6, y: int = 4, size: int = 14
    ) -> str:
        """
        Generate brand icon SVG from ontology definition.

        Icons are placed on the label side of the badge at fixed positions.

        Args:
            icon_type: Icon type (github, npm, discord, etc.)
            color: Icon color (usually label text color)
            x: X position (default: 6)
            y: Y position (default: 4)
            size: Icon size (default: 14)

        Returns:
            Icon SVG string or empty string if type is "none" or not found
        """
        if icon_type is None or icon_type == "none":
            return ""

        try:
            icon_def = self.ontology.get_icon_definition(icon_type)
        except (KeyError, AttributeError):
            return ""  # Icon not found, skip silently

        svg_template = icon_def.get("svg")
        viewBox = icon_def.get("viewBox", "0 0 16 16")

        if not svg_template:
            return ""

        # Wrap icon in SVG element with transform for positioning
        icon_svg = f'    <svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="{viewBox}">'
        icon_svg += f"\n      {svg_template.format(color=color)}"
        icon_svg += "\n    </svg>"

        return icon_svg
